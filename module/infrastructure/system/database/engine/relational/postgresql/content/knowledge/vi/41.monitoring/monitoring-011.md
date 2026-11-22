# Thu thập chỉ số với exporter và dashboard trong PostgreSQL

Để vận hành PostgreSQL ổn định, đội ngũ cần quan sát được sức khỏe database, workload, dung lượng, kết nối, truy vấn, replication, WAL, vacuum và khả năng phục hồi. Các truy vấn kiểm tra thủ công hữu ích khi điều tra một sự cố, nhưng không đủ để theo dõi liên tục hoặc nhận cảnh báo trước khi người dùng bị ảnh hưởng.

Một hệ thống metrics phổ biến kết hợp PostgreSQL với **postgres_exporter**, **Prometheus** và **Grafana**. Exporter đọc các statistics views và system catalogs rồi công bố metrics qua HTTP. Prometheus định kỳ scrape endpoint, lưu time series và đánh giá alert rules. Grafana truy vấn Prometheus để hiển thị dashboard theo cluster, instance, database và workload.

~~~text
             PostgreSQL primary / standby
             ----------------------------
             pg_stat_database
             pg_stat_activity
             pg_stat_replication
             pg_stat_wal
             pg_stat_user_tables
             pg_stat_archiver
                       |
                       | SQL queries
                       v
                postgres_exporter
                -----------------
                /metrics :9187
                       |
                       | HTTP scrape
                       v
                   Prometheus
                   ----------
                TSDB / rules
                  /       \
                 /         \
                v           v
          Grafana       Alertmanager
          --------      ------------
          Dashboards   Route / group
          Explore      Silence / notify
                |
                v
        Operator / on-call engineer
~~~

Exporter, Prometheus và Grafana có trách nhiệm khác nhau. Exporter thu thập và chuyển đổi số liệu; Prometheus lưu trữ, truy vấn và đánh giá rule; Grafana trình bày dữ liệu. Alertmanager xử lý việc nhóm, định tuyến và gửi thông báo từ các alert do Prometheus phát ra.

Bài này thuộc chương **Giám sát** của module *Database Engine Relational PostgreSQL*, tập trung vào cách thu thập metrics với exporter, thiết kế dashboard có ích và vận hành pipeline giám sát an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích kiến trúc exporter, Prometheus, Grafana và Alertmanager.
2. Phân biệt metric, label, sample, time series và scrape target.
3. Triển khai postgres_exporter cho một PostgreSQL instance.
4. Tạo monitoring role với quyền tối thiểu cần thiết.
5. Cấu hình kết nối exporter qua DSN hoặc environment variables.
6. Kiểm tra endpoint metrics và trạng thái scrape.
7. Cấu hình Prometheus scrape job và target labels.
8. Dùng service discovery hoặc static targets cho nhiều instance.
9. Chọn collectors phù hợp với workload và phiên bản PostgreSQL.
10. Thu thập metrics về transactions, sessions, cache, I/O và tuples.
11. Theo dõi locks, wait events, deadlocks và long-running transactions.
12. Theo dõi WAL, archiver, replication và replication lag.
13. Theo dõi vacuum, dead tuples, table growth và index usage.
14. Mở rộng exporter bằng custom queries có kiểm soát.
15. Thiết kế labels ổn định và tránh cardinality bùng nổ.
16. Viết PromQL cho rates, ratios, gauges và recording rules.
17. Thiết kế dashboard tổng quan, workload, capacity và replication.
18. Viết alert rules và định tuyến cảnh báo.
19. Phân biệt exporter down với PostgreSQL down.
20. Bảo vệ credentials, metrics endpoint và dữ liệu nhạy cảm.
21. Giám sát nhiều database, nhiều cluster và HA roles.
22. Xử lý stats reset, metric gaps và khác biệt giữa các major versions.
23. Kiểm tra độ chính xác của dashboard bằng SQL đối chiếu.
24. Xây dựng runbook giám sát và cải tiến liên tục.

## 2. Vì sao cần metrics liên tục?

PostgreSQL có nhiều statistics views, nhưng các con số chỉ thực sự hữu ích khi được quan sát theo thời gian và gắn với tác động của ứng dụng.

### 2.1. Phát hiện sự cố sớm

Connections có thể tiến gần giới hạn, WAL archive có thể bắt đầu thất bại, replication lag có thể tăng, disk có thể sắp đầy hoặc dead tuples có thể tích lũy. Dashboard giúp nhìn xu hướng trước khi sự cố trở thành outage.

### 2.2. Hiểu workload

Transaction rate, commits, rollbacks, block reads, cache hits, temporary bytes và active sessions cho biết hệ thống đang xử lý loại workload nào.

### 2.3. Điều tra bottleneck

CPU cao có thể đến từ query, I/O wait, vacuum hoặc quá nhiều backend. Metrics cần được kết hợp với pg_stat_activity, wait events, OS metrics và query statistics.

### 2.4. Đo hiệu quả thay đổi

Sau khi thêm index, đổi connection pool, điều chỉnh autovacuum hoặc nâng cấp PostgreSQL, so sánh trước và sau theo cùng workload window.

### 2.5. Theo dõi SLA và SLO

Availability, latency, error rate, replication freshness và backup status có thể được chuyển thành SLI/SLO phù hợp. Metrics của database là một phần trong bức tranh dịch vụ, không thay thế metrics ở application layer.

### 2.6. Giảm thao tác thủ công

Prometheus scrape định kỳ và dashboard tập trung giúp đội ngũ không phải đăng nhập từng server để chạy cùng một bộ truy vấn mỗi ngày.

## 3. Các thành phần của monitoring stack

| Thành phần | Trách nhiệm | Câu hỏi nó trả lời |
| --- | --- | --- |
| PostgreSQL | Cung cấp statistics và trạng thái nội bộ | Database đang làm gì? |
| postgres_exporter | Đọc số liệu và xuất Prometheus metrics | Có thể scrape những chỉ số nào? |
| Prometheus | Scrape, lưu time series, chạy PromQL và rules | Chỉ số thay đổi theo thời gian ra sao? |
| Grafana | Dashboard, Explore và visualization | Người vận hành cần nhìn gì? |
| Alertmanager | Group, route, silence và notification | Ai cần nhận cảnh báo? |
| node_exporter | Metrics của hệ điều hành | CPU, RAM, disk, network có vấn đề không? |
| Application instrumentation | Metrics từ ứng dụng | Người dùng đang chịu ảnh hưởng thế nào? |

### 3.1. PostgreSQL statistics

PostgreSQL duy trì nhiều statistics views như pg_stat_database, pg_stat_activity, pg_stat_replication, pg_stat_wal và pg_stat_user_tables. Các view này là nguồn dữ liệu cho exporter.

### 3.2. Exporter

Exporter chạy như một process hoặc container. Nó kết nối tới PostgreSQL bằng một role giám sát và cung cấp endpoint HTTP, thường là cổng 9187 theo cấu hình phổ biến.

### 3.3. Prometheus

Prometheus chủ động gọi endpoint exporter theo scrape interval. Nó lưu các samples với timestamp và labels vào time-series database.

### 3.4. Grafana

Grafana dùng Prometheus làm data source, gửi PromQL và hiển thị kết quả dưới dạng stat, time series, table, heatmap hoặc alert view.

### 3.5. Alertmanager

Prometheus đánh giá alert rules và gửi trạng thái alert tới Alertmanager. Alertmanager nhóm cảnh báo, loại bỏ trùng lặp, áp dụng silence/inhibition và gửi tới kênh đã cấu hình.

### 3.6. Node exporter

postgres_exporter không thay thế node_exporter. Muốn theo dõi CPU, RAM, filesystem, disk I/O và network của host PostgreSQL, cần thu thập OS metrics riêng.

## 4. Metric, label và time series

Prometheus tổ chức dữ liệu thành các time series.

### 4.1. Metric

Metric là tên một đại lượng, ví dụ số transaction commit, số connection hoặc lượng WAL đã tạo.

### 4.2. Sample

Một sample gồm giá trị số và timestamp. Prometheus lưu nhiều samples theo thời gian cho một series.

### 4.3. Label

Label bổ sung chiều phân loại, ví dụ cluster, instance, database hoặc state.

### 4.4. Time series identity

Một time series được xác định bởi metric name và tập label values. Nếu label value thay đổi, Prometheus tạo một series khác.

### 4.5. Ví dụ

~~~text
pg_stat_database_xact_commit{
  cluster="orders-prod",
  instance="db-a",
  datname="orders"
} 125400
~~~

Metric trên thể hiện số transaction commit trong database orders ở instance db-a thuộc cluster orders-prod tại thời điểm sample.

### 4.6. Counter

Counter tăng đơn điệu cho tới khi process/statistics reset. Dùng rate() hoặc increase() để phân tích tốc độ/tổng thay đổi trong một khoảng thời gian.

### 4.7. Gauge

Gauge có thể tăng hoặc giảm, ví dụ số connections hiện tại, số dead tuples ước lượng hoặc replication lag.

### 4.8. Histogram

Histogram chia observations vào các buckets và cung cấp count/sum. Một số exporter không tạo histogram latency query mặc định; có thể cần application instrumentation hoặc custom collector.

### 4.9. Metric type và semantics

Tên metric chưa đủ để biết cách tính. Kiểm tra HELP/TYPE ở endpoint metrics và tài liệu phiên bản exporter. Đừng áp dụng rate() cho gauge hoặc cộng các giá trị không cùng đơn vị.

## 5. Cài đặt và chạy postgres_exporter

postgres_exporter là exporter dành cho PostgreSQL, thường được phát hành trong hệ sinh thái Prometheus community.

### 5.1. Chọn bản phát hành

Chọn binary/container phù hợp hệ điều hành, kiến trúc CPU và PostgreSQL version đang dùng. Ghi nhận version exporter trong inventory để dễ đối chiếu khi nâng cấp.

### 5.2. Chạy bằng binary

Một cách triển khai là cài binary vào host database hoặc một monitoring host có network access tới PostgreSQL. Exporter có thể chạy bằng system service với user OS riêng.

### 5.3. Chạy bằng container

Có thể chạy exporter trong container riêng, publish endpoint metrics tới Prometheus và inject credentials qua secret mechanism.

### 5.4. Cổng mặc định

Cổng HTTP phổ biến là 9187. Cổng thực tế được điều khiển bởi cấu hình web listen address của exporter.

### 5.5. Endpoint metrics

Endpoint mặc định thường là /metrics:

~~~bash
curl http://127.0.0.1:9187/metrics
~~~

Trong môi trường production, giới hạn endpoint bằng firewall, private network hoặc reverse proxy có authentication/TLS nếu cần.

### 5.6. Health check

Exporter có thể cung cấp endpoint health/readiness tùy phiên bản. Kiểm tra help và tài liệu của binary đang dùng; Prometheus scrape target state vẫn là tín hiệu quan trọng.

### 5.7. Chạy exporter riêng

Tách exporter process khỏi PostgreSQL process giúp cập nhật và restart độc lập. Tuy vậy, exporter vẫn phụ thuộc database connectivity và có thể tạo thêm connections.

## 6. Tạo monitoring role trong PostgreSQL

Không nên dùng superuser làm credential mặc định của exporter. Tạo một login role riêng cho giám sát.

### 6.1. Tạo role

~~~sql
CREATE ROLE postgres_exporter
    LOGIN
    PASSWORD 'replace-with-secret';
~~~

Password ở đây chỉ là placeholder cho lab. Production nên dùng secret manager hoặc cơ chế cấp credential có kiểm soát.

### 6.2. Cấp pg_monitor

Trên PostgreSQL có predefined role pg_monitor:

~~~sql
GRANT pg_monitor TO postgres_exporter;
~~~

Role này cấp quyền đọc nhiều thông tin monitoring/statistics cần thiết mà không cần biến exporter thành superuser.

### 6.3. Kiểm tra version

Predefined roles và quyền trên statistics views thay đổi theo major version. Trên phiên bản cũ hơn, cần xem tài liệu quyền tương ứng và cấp quyền hẹp theo collector thực tế.

### 6.4. Không cấp quyền ghi

Exporter chỉ cần đọc dữ liệu giám sát. Không cấp INSERT, UPDATE, DELETE, CREATE hoặc quyền quản trị không cần thiết.

### 6.5. Custom query permissions

Nếu custom query đọc bảng ứng dụng hoặc schema riêng, chỉ cấp SELECT cho đúng object và schema cần thiết. Không mở quyền đọc toàn bộ dữ liệu nghiệp vụ chỉ để thêm một metric.

### 6.6. Giới hạn kết nối

Dùng connection limit phù hợp nếu exporter hoặc nhiều collectors có thể mở nhiều sessions. Không đặt quá thấp tới mức scrape thường xuyên bị từ chối.

### 6.7. Xác minh role

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolreplication,
    rolconnlimit
FROM pg_roles
WHERE rolname = 'postgres_exporter';
~~~

## 7. Kết nối exporter tới PostgreSQL

Exporter cần một connection string hoặc bộ biến môi trường tương đương.

### 7.1. DSN

Ví dụ một connection string:

~~~text
postgresql://postgres_exporter:secret@db-a.internal:5432/postgres?sslmode=verify-full
~~~

Tên database dùng để kết nối ban đầu có thể là postgres hoặc database monitoring riêng. Một số collectors truy vấn thống kê cluster-wide; collectors khác có thể cần kết nối từng database.

### 7.2. Environment variables

Tùy phiên bản postgres_exporter, có thể dùng DATA_SOURCE_NAME hoặc các biến DATA_SOURCE_URI, DATA_SOURCE_USER và DATA_SOURCE_PASS. Kiểm tra tài liệu đúng version trước khi cấu hình.

### 7.3. Không đặt password trên command line

Command line có thể xuất hiện trong process list, shell history hoặc logs. Ưu tiên secret store, protected environment file, .pgpass hoặc container secrets.

### 7.4. TLS

Dùng sslmode phù hợp, ví dụ verify-full khi có CA và hostname validation. Không hạ TLS verification để khắc phục tạm lỗi certificate trong production.

### 7.5. pg_hba.conf

Cho phép đúng exporter host/network:

~~~conf
hostssl postgres postgres_exporter 10.30.0.0/24 scram-sha-256
~~~

Nếu exporter kết nối nhiều database, cần rule phù hợp với database names hoặc all databases theo policy.

### 7.6. Network path

Kiểm tra routing, firewall, DNS, security groups và TLS trước khi debug query collector.

### 7.7. Kiểm tra trực tiếp

~~~bash
psql "host=db-a.internal port=5432 dbname=postgres user=postgres_exporter sslmode=verify-full" -c "SELECT pg_is_in_recovery();"
~~~

Nếu kết nối trực tiếp thất bại, exporter cũng khó có thể scrape thành công.

## 8. Cấu hình exporter và collectors

Exporter có thể bật nhiều collectors mặc định và hỗ trợ custom collectors tùy phiên bản.

### 8.1. Default collectors

Các nhóm phổ biến bao gồm database statistics, activity, replication, WAL, archiver, table statistics, locks và một số thông tin hệ thống. Danh sách chính xác phụ thuộc version và build.

### 8.2. Collector không cần thiết

Không bật mọi collector chỉ vì chúng tồn tại. Collector truy vấn nhiều object hoặc database có thể tăng thời gian scrape và load lên PostgreSQL.

### 8.3. Database discovery

Một số phiên bản có khả năng tự phát hiện và kết nối từng database. Điều này hữu ích khi cần metrics riêng theo database nhưng cũng có thể làm số connection và thời gian scrape tăng.

### 8.4. Exclude databases

Có thể loại template hoặc database không cần theo dõi nếu exporter hỗ trợ option tương ứng. Đừng loại database hệ thống nếu dashboard/collector phụ thuộc dữ liệu từ đó mà chưa kiểm tra.

### 8.5. Collector flags

Tên flags, default collectors và cách bật/tắt có thể đổi theo version. Xem --help của binary đang chạy và lưu cấu hình đã kiểm chứng cùng version.

### 8.6. Scrape duration

Đo thời gian exporter thực hiện scrape. Nếu query collectors kéo dài hơn scrape interval, có thể xuất hiện scrape overlap, timeout hoặc dữ liệu chậm.

### 8.7. Phân chia collector

Collectors cơ bản có thể chạy thường xuyên; collector nặng như table/index inventory hoặc query-level statistics có thể được scrape chậm hơn hoặc tách thành job riêng.

## 9. Các nhóm metrics PostgreSQL quan trọng

Không có một dashboard duy nhất phù hợp mọi workload. Hãy nhóm metrics theo câu hỏi vận hành.

| Nhóm | Nguồn dữ liệu tiêu biểu | Điều cần quan sát |
| --- | --- | --- |
| Availability | exporter scrape, pg_up | Exporter và database có truy cập được không? |
| Connections | pg_stat_activity | Số session, state, wait events |
| Transactions | pg_stat_database | Commit, rollback, transaction rate |
| Cache/I/O | pg_stat_database, pg_stat_io | Buffer hits, reads, I/O |
| Locks | pg_locks, pg_stat_activity | Blocking, waiting, deadlocks |
| Replication | pg_stat_replication, pg_stat_wal_receiver | WAL send/write/flush/replay |
| WAL/archive | pg_stat_wal, pg_stat_archiver | WAL generation và archive failures |
| Vacuum | pg_stat_user_tables, progress views | Dead tuples, vacuum/analyze |
| Table/index | pg_stat_user_tables, pg_stat_user_indexes | Scan, tuple changes, index use |
| Query | pg_stat_statements | Query calls, time, rows, I/O |
| Host | node_exporter | CPU, RAM, disk, filesystem, network |

### 9.1. Availability

Theo dõi Prometheus scrape health và trạng thái database connection từ exporter. Đây là hai tín hiệu khác nhau.

### 9.2. Workload

Transaction rate, session count, active queries và tuple changes giúp xác định tải thực tế.

### 9.3. Capacity

Connections, disk usage, WAL retention, table growth và dead tuples giúp dự báo giới hạn tài nguyên.

### 9.4. Performance

Query latency, block I/O, waits, locks và cache behavior giúp tìm bottleneck.

### 9.5. Replication

Receive/replay progress, sender state, lag và slot retention quan trọng với HA và read replicas.

## 10. pg_stat_database và transaction metrics

pg_stat_database cung cấp statistics theo database.

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    tup_inserted,
    tup_updated,
    tup_deleted,
    deadlocks,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
~~~

### 10.1. Transaction commits

xact_commit là số transaction commit được ghi nhận kể từ lần reset statistics. Đây là counter, nên quan sát rate thay vì chỉ đọc tổng.

### 10.2. Rollbacks

xact_rollback tăng khi transaction rollback. Rollback rate tăng có thể phản ánh application errors, constraint violations, explicit rollback hoặc retry logic.

### 10.3. Transaction rate

Một PromQL minh họa:

~~~promql
sum by (cluster, datname) (
  rate(pg_stat_database_xact_commit[5m])
)
~~~

Tên metric thực tế phụ thuộc phiên bản exporter. Kiểm tra endpoint /metrics và HELP/TYPE trước khi dùng dashboard.

### 10.4. Commit/rollback ratio

Có thể so sánh rate commit với rate rollback để phát hiện thay đổi bất thường. Không coi rollback tự thân luôn là lỗi; một số ứng dụng dùng rollback có chủ đích.

### 10.5. Temporary files

temp_files và temp_bytes tăng nhanh có thể chỉ ra sort/hash spill ra disk, work_mem không đủ cho query pattern hoặc workload thay đổi.

### 10.6. Deadlocks

deadlocks là counter. Alert nên dựa trên rate/delta và tác động, không chỉ tổng tích lũy từ khi cluster khởi động.

### 10.7. Stats reset

stats_reset giúp giải thích counter đột ngột về thấp. Khi process/database reset statistics, rate có thể tạm thời không ổn định.

## 11. Connections và pg_stat_activity

pg_stat_activity là nguồn quan trọng để hiểu backend đang hoạt động ra sao.

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event
ORDER BY sessions DESC;
~~~

### 11.1. Số connections

So sánh số client backends với max_connections và reserved slots. Chừa headroom cho admin, replication và các thao tác sự cố.

### 11.2. Active sessions

Active sessions đang thực thi query. Nhiều active backends không tự động có nghĩa database quá tải; cần xem CPU, I/O, waits và query duration.

### 11.3. Idle sessions

Idle sessions đang chờ client gửi lệnh. Số lượng cao có thể bình thường khi dùng connection pool, nhưng cần đối chiếu giới hạn connections và pool configuration.

### 11.4. Idle in transaction

Backend idle in transaction có thể giữ locks và snapshot, làm chậm vacuum hoặc gây contention. Đây là trạng thái cần theo dõi riêng.

### 11.5. Wait events

wait_event_type và wait_event cho biết backend đang chờ lock, I/O, client, IPC hoặc tài nguyên khác. Tên wait events thay đổi theo version.

### 11.6. Query age

Có thể tính now() - query_start cho query đang chạy. Transaction age cần được theo dõi riêng vì transaction có thể mở lâu dù query hiện tại ngắn.

### 11.7. Query text

Query text có thể chứa literal values hoặc dữ liệu nhạy cảm. Tránh xuất raw query thành label Prometheus hoặc hiển thị rộng rãi trong dashboard.

### 11.8. PID cardinality

PID thay đổi liên tục. Không đưa PID vào labels cho metrics tổng hợp lâu dài nếu không có lý do rõ ràng; cardinality và churn sẽ tăng nhanh.

## 12. Connections và saturation

Một database có thể bị ảnh hưởng trước khi đạt max_connections.

### 12.1. Connection utilization

Tỷ lệ connections sử dụng trên giới hạn cần tính cả reserved slots và connection roles đặc biệt. Dùng metric gauge từ pg_stat_activity và cấu hình server.

### 12.2. Pool saturation

Theo dõi application pool metrics như active, idle, waiting clients và acquire latency. PostgreSQL exporter không nhìn thấy toàn bộ hàng đợi ở tầng application pool.

### 12.3. Connection churn

Connections tạo/hủy liên tục có thể tăng authentication overhead và process startup cost. So sánh connection count với application pool behavior.

### 12.4. Alert threshold

Ngưỡng cảnh báo cần dựa trên headroom và peak pattern. Ví dụ alert warning khi utilization vượt 75% trong vài phút và critical khi vượt 90%, nhưng phải điều chỉnh theo reserved connections và operational policy.

### 12.5. Không tăng max_connections tùy tiện

Nhiều backend làm tăng memory pressure và scheduling overhead. Trước tiên kiểm tra pooling, query concurrency và workload.

## 13. Cache, block reads và I/O

pg_stat_database có blks_hit và blks_read.

### 13.1. Buffer hit

blks_hit là số block được tìm thấy trong PostgreSQL shared buffers.

### 13.2. Block read

blks_read là số block PostgreSQL phải yêu cầu đọc. Những block này có thể được phục vụ từ OS page cache; không đồng nghĩa tất cả đều là physical disk reads.

### 13.3. Hit ratio

Công thức tham khảo:

\[
\text{Hit ratio} =
\frac{\text{blks\_hit}}
{\text{blks\_hit}+\text{blks\_read}}
\]

### 13.4. PromQL minh họa

~~~promql
sum by (cluster, instance) (
  rate(pg_stat_database_blks_hit[5m])
)
/
clamp_min(
  sum by (cluster, instance) (
    rate(pg_stat_database_blks_hit[5m])
    + rate(pg_stat_database_blks_read[5m])
  ),
  1
)
~~~

Tên metric cần được xác nhận từ exporter đang dùng.

### 13.5. Hit ratio không phải toàn bộ I/O health

Hit ratio cao không bảo đảm query nhanh. Một workload có thể đọc nhiều pages nhưng vẫn hit cache, hoặc bị CPU/lock bottleneck. Hit ratio thấp cũng cần xem working set và OS cache.

### 13.6. pg_stat_io

Trên các PostgreSQL version hỗ trợ pg_stat_io, có thể quan sát I/O theo backend/object/context. View và columns khác nhau theo major version; dùng exporter/custom query tương thích.

### 13.7. Node exporter

Kết hợp disk read/write throughput, latency, queue depth và filesystem utilization từ OS exporter để xác định physical storage bottleneck.

## 14. Locks, blocking và deadlocks

### 14.1. pg_locks

pg_locks hiển thị locks được giữ hoặc đang chờ. Đây là dữ liệu có thể có cardinality cao nếu đưa từng lock object vào labels.

### 14.2. Blocked sessions

Một truy vấn chẩn đoán có thể tìm blocked backend và blocker:

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.datname,
    blocked.application_name,
    now() - blocked.query_start AS blocked_duration,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_application,
    left(blocked.query, 200) AS blocked_query_sample
FROM pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
    ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid;
~~~

### 14.3. Blocking duration

Theo dõi thời gian session chờ lock. Một lock wait ngắn có thể bình thường; wait kéo dài hoặc tăng theo thời gian có thể gây user-visible latency.

### 14.4. Deadlocks

Deadlock counter tăng cho biết PostgreSQL đã phát hiện deadlock. Logs thường cần được bật/định cấu hình để có chi tiết transaction liên quan.

### 14.5. Dashboard aggregate

Dashboard nên tập trung số blocked sessions, max wait age, deadlock rate và top wait types. Chi tiết PID/query nên truy cập qua trang điều tra có quyền hạn phù hợp, không biến mỗi PID thành một time series.

## 15. Replication và WAL metrics

Với physical replication, theo dõi cả sender trên primary và receiver/replay trên standby.

### 15.1. pg_stat_replication

Trên primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    sync_state
FROM pg_stat_replication;
~~~

### 15.2. WAL stages

- sent_lsn: vị trí WAL đã gửi.
- write_lsn: vị trí WAL standby đã ghi.
- flush_lsn: vị trí WAL standby đã flush.
- replay_lsn: vị trí WAL standby đã replay.

### 15.3. Byte gap

Có thể tính khoảng cách WAL từ primary current LSN tới replay LSN:

~~~sql
SELECT
    application_name,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_gap_bytes
FROM pg_stat_replication
WHERE replay_lsn IS NOT NULL;
~~~

### 15.4. Lag time fields

write_lag, flush_lag và replay_lag là các thống kê độ trễ gần đây, không phải lúc nào cũng biểu diễn chính xác thời gian catch-up hiện tại. Khi primary idle, giá trị có thể null hoặc không thay đổi.

### 15.5. pg_stat_wal_receiver

Trên standby, view này cho biết WAL receiver status, sender host, written/flushed LSN và latest end LSN. Chỉ có row khi receiver hoạt động theo trạng thái phù hợp.

### 15.6. Replication role

Kết hợp pg_is_in_recovery() để biết instance đang ở primary hay standby. Khi failover, role thay đổi; dashboard cần thể hiện trạng thái hiện tại.

### 15.7. Replication slots

Theo dõi restart_lsn, wal_status, active và retained WAL. Slot giữ WAL cho consumer chậm, nhưng có thể làm đầy disk primary nếu không giới hạn/giám sát.

## 16. WAL generation và archive

### 16.1. pg_stat_wal

View pg_stat_wal cung cấp số liệu WAL records, full page images, bytes, writes, syncs và thời gian I/O theo version.

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

### 16.2. WAL bytes rate

Nếu exporter xuất WAL bytes counter, dùng rate() để quan sát tốc độ WAL generation. So sánh với baseline theo giờ/ngày.

### 16.3. Full page images

Tỷ lệ WAL full page images có thể tăng sau checkpoint hoặc khi workload thay đổi. Theo dõi WAL bytes và FPI cùng nhau.

### 16.4. pg_stat_archiver

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

### 16.5. Archive failures

failed_count tăng là dấu hiệu archive_command gặp lỗi. Kiểm tra logs, disk, credentials, network và quyền ghi archive.

### 16.6. Archive age

Theo dõi thời gian từ last_archived_time và WAL generation. Một timestamp cũ khi cluster idle không nhất thiết là lỗi; cần kết hợp WAL activity.

### 16.7. Không chỉ theo dõi số segment

WAL archive có thể có nhiều file cũ nhưng không chứa segment mới nhất cần thiết. Kiểm tra continuity và backup/restore process riêng.

## 17. Vacuum, dead tuples và table health

Vacuum giữ MVCC cleanup và transaction ID health. Exporter có thể giúp phát hiện table churn và vacuum không theo kịp.

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    seq_scan,
    seq_tup_read,
    idx_scan,
    idx_tup_fetch,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

### 17.1. Dead tuples

n_dead_tup là ước lượng. Tăng kéo dài có thể chỉ ra vacuum chưa theo kịp hoặc transaction horizon giữ tuple cũ.

### 17.2. Live/dead trend

Theo dõi xu hướng theo table/database. Một snapshot lớn không đủ kết luận bloat vì statistics có thể ước lượng và thay đổi sau analyze/vacuum.

### 17.3. Autovacuum timestamps

last_autovacuum và last_autoanalyze giúp thấy lần gần nhất autovacuum/analyze hoàn thành theo statistics.

### 17.4. Vacuum progress

pg_stat_progress_vacuum cung cấp tiến độ của vacuum đang chạy. Dùng để phân biệt vacuum chưa bắt đầu, đang chạy hay không thể bắt kịp.

### 17.5. Table size

Kết hợp pg_total_relation_size và filesystem metrics để theo dõi growth. Query size inventory quá thường xuyên có thể tốn tài nguyên; scrape chậm hơn hoặc chạy riêng.

### 17.6. Transaction ID age

Theo dõi age(datfrozenxid) và database-level freeze risk. Đây là tín hiệu capacity/availability quan trọng vì transaction ID wraparound có thể buộc PostgreSQL vào chế độ bảo vệ.

### 17.7. Vacuum dashboard

Hiển thị dead tuple estimates, autovacuum recency, vacuum progress, transaction ID age và table growth theo nhóm database.

## 18. Index usage và table scans

### 18.1. pg_stat_user_indexes

View cung cấp idx_scan, idx_tup_read và idx_tup_fetch theo index.

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC
LIMIT 30;
~~~

### 18.2. Unused index

idx_scan thấp không tự chứng minh index vô ích. Index có thể được dùng hiếm nhưng quan trọng cho một query nghiệp vụ hoặc uniqueness/constraint.

### 18.3. Sequential scans

Seq scans cao có thể hợp lý với table nhỏ hoặc analytical scans. So sánh với table size, rows fetched và query plans.

### 18.4. Index write overhead

Mỗi index có thể làm tăng chi phí INSERT/UPDATE/DELETE và storage. Đánh giá lợi ích đọc cùng write overhead.

### 18.5. Reset statistics

Index counters có thể reset hoặc database được restore/restart. Không xóa index chỉ dựa vào một cửa sổ ngắn sau reset.

## 19. Query metrics với pg_stat_statements

pg_stat_statements tổng hợp statistics của các câu lệnh SQL đã thực thi.

### 19.1. Extension

Trên nhiều triển khai, cần thêm pg_stat_statements vào shared_preload_libraries và restart server trước khi CREATE EXTENSION trong database.

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

### 19.2. Các trường hữu ích

- calls: số lần thực thi.
- total_exec_time: tổng thời gian thực thi.
- mean_exec_time: thời gian trung bình.
- rows: số rows trả về/thay đổi theo query.
- shared_blks_hit/read: block accesses.
- temp_blks_read/written: temporary block I/O.
- plans/planning time: có thể có tùy cấu hình/version.

### 19.3. Top total time

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    left(query, 200) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

### 19.4. Top mean latency

Sắp xếp theo mean_exec_time để tìm query chậm trung bình. Cần xem calls; một query chậm hiếm và một query hơi chậm nhưng chạy hàng triệu lần có tác động khác nhau.

### 19.5. Top calls

Query có calls rất cao có thể chiếm tổng CPU dù latency mỗi lần thấp. Kết hợp calls với total time và mean time.

### 19.6. Query text và privacy

Query text có thể chứa dữ liệu hoặc thông tin nhạy cảm tùy cách parameterize. Không đưa raw query thành Prometheus label; dùng dashboard có access control hoặc chỉ hiển thị queryid/fingerprint.

### 19.7. Reset pg_stat_statements

Statistics có thể reset. Ghi nhận reset time và không so sánh hai cửa sổ không cùng baseline.

## 20. Custom queries trong postgres_exporter

Default collectors không phải lúc nào cũng cung cấp đúng metric mà dashboard cần. postgres_exporter hỗ trợ custom query configuration theo phiên bản.

### 20.1. Khi nào cần custom query?

- Metric đặc thù của ứng dụng.
- Connection count theo state.
- Replication gap theo bytes.
- Table-level metric giới hạn trong schema cần thiết.
- SLO hoặc business metric có nguồn trực tiếp từ database.

### 20.2. Nguyên tắc thiết kế

Custom query nên:
- Chạy nhanh và có execution plan dễ dự đoán.
- Trả về số cột và kiểu dữ liệu ổn định.
- Dùng labels có tập giá trị giới hạn.
- Không trả raw SQL, user identifiers hoặc PID làm labels.
- Chỉ đọc những view/table cần thiết.
- Có quyền tối thiểu rõ ràng.
- Được thử nghiệm trên production-like data volume.

### 20.3. Ví dụ query sessions

Một truy vấn aggregate có thể nhóm backend theo database và state:

~~~sql
SELECT
    COALESCE(datname, 'shared') AS datname,
    state,
    count(*)::bigint AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, state;
~~~

### 20.4. Ví dụ cấu hình query file

Cấu trúc custom query file phụ thuộc version postgres_exporter. Một cấu hình kiểu YAML thường có dạng:

~~~yaml
pg_app_sessions:
  query: |
    SELECT
      COALESCE(datname, 'shared') AS datname,
      state,
      count(*)::bigint AS sessions
    FROM pg_stat_activity
    WHERE backend_type = 'client backend'
    GROUP BY datname, state
  metrics:
    - datname:
        usage: "LABEL"
        description: "Database name"
    - state:
        usage: "LABEL"
        description: "Backend state"
    - sessions:
        usage: "GAUGE"
        description: "Current client sessions"
~~~

Kiểm tra schema custom query đúng với version exporter đang chạy. Không copy cấu hình từ version khác mà chưa validate.

### 20.5. Nạp query file

Một số version dùng flag hoặc environment variable như --extend.query-path để trỏ tới query file. Xác nhận tên flag bằng --help và restart/reload exporter theo cách được hỗ trợ.

### 20.6. Metric naming

Tên metric cuối cùng được tạo theo exporter conventions và có thể thêm prefix. Xem /metrics để xác nhận tên, HELP, TYPE và labels thực tế.

### 20.7. Test custom query độc lập

Chạy SQL trực tiếp bằng monitoring role. Đo latency, kiểm tra NULL values, row counts và permissions trước khi thêm vào scrape path.

## 21. Thiết kế custom metrics an toàn

### 21.1. Aggregate thay vì row-level

Tạo một series cho tổng sessions theo state thường hữu ích hơn một series cho từng PID.

### 21.2. Label dimensions

Database, state, application class hoặc replication application_name có thể phù hợp nếu tập giá trị ổn định và nhỏ.

### 21.3. Tránh raw query label

Query text có thể rất đa dạng, chứa secrets và tạo cardinality lớn. Dùng queryid hoặc nhóm query được kiểm soát nếu cần.

### 21.4. Tránh user_id/customer_id

Business identifiers có thể có hàng triệu giá trị. Không dùng chúng làm labels; tổng hợp theo nhóm nghiệp vụ ở tầng phù hợp.

### 21.5. Tránh PID và transaction ID

PID và transaction IDs thay đổi liên tục, tạo series churn. Chỉ dùng trong công cụ điều tra tức thời, không dùng làm dimensions time-series dài hạn.

### 21.6. Scrape cost

Custom query chạy mỗi lần scrape. Query inventory toàn bộ tables/indexes có thể nặng; tăng scrape interval hoặc tách job riêng.

### 21.7. Timeout

Đặt statement_timeout phù hợp cho monitoring role hoặc custom query connection nếu cơ chế exporter hỗ trợ. Một query metrics không được phép treo và chiếm connection vô hạn.

## 22. Prometheus scrape configuration

Prometheus scrape config xác định job, target, interval, timeout và labels.

~~~yaml
scrape_configs:
  - job_name: postgresql
    scrape_interval: 30s
    scrape_timeout: 10s
    static_configs:
      - targets:
          - db-a.internal:9187
          - db-b.internal:9187
        labels:
          cluster: orders-prod
          environment: production
~~~

### 22.1. Job name

Job name nhóm các targets cùng loại. Có thể tách job theo môi trường hoặc vai trò nếu policy và discovery yêu cầu.

### 22.2. Scrape interval

Interval 30 giây là ví dụ. Chọn dựa trên yêu cầu phát hiện, scrape cost và số lượng targets.

### 22.3. Scrape timeout

Timeout phải nhỏ hơn hoặc bằng scrape interval. Nếu exporter không trả kịp, Prometheus ghi scrape failure và target có thể bị đánh dấu down.

### 22.4. Static configs

Static targets phù hợp hệ thống nhỏ hoặc node address ổn định.

### 22.5. Service discovery

Với cloud, Kubernetes hoặc hạ tầng thay đổi thường xuyên, dùng service discovery để cập nhật targets mà không sửa file thủ công.

### 22.6. Relabeling

Relabeling có thể chuẩn hóa cluster, environment, region, role hoặc instance labels. Đảm bảo cùng một database luôn có labels nhất quán.

### 22.7. External labels

External labels nhận diện Prometheus server/cluster khi gửi dữ liệu tới remote storage hoặc federation. Không nhầm chúng với target labels.

### 22.8. Kiểm tra target state

Prometheus UI tại trang Targets cho biết endpoint được scrape thành công, lần scrape gần nhất và lỗi gần nhất.

## 23. Service discovery và nhiều PostgreSQL instances

### 23.1. Một exporter mỗi instance

Mô hình phổ biến là một exporter endpoint gắn với một PostgreSQL instance. Điều này giúp phân biệt source of metrics và giảm phụ thuộc vào một exporter trung tâm.

### 23.2. Exporter trung tâm

Một exporter có thể kết nối tới nhiều database/instance trong một số cấu hình. Cách này giảm số process nhưng tạo một điểm tập trung và cần quản lý credentials/discovery phức tạp hơn.

### 23.3. Kubernetes

Trong Kubernetes, exporter có thể chạy sidecar hoặc deployment riêng. Prometheus Operator thường dùng ServiceMonitor/PodMonitor để phát hiện targets; schema và labels phụ thuộc CRD/version.

### 23.4. Stable labels

Dùng cluster, environment, service và instance. Labels phải được chuẩn hóa giữa Prometheus, Grafana và alert rules.

### 23.5. Primary/standby role

Role có thể thay đổi khi failover. Thu thập role từ PostgreSQL state thay vì hardcode hostname thành primary vĩnh viễn.

### 23.6. Failover endpoint

Nếu application endpoint chuyển sang primary mới, monitoring vẫn cần scrape từng node riêng để thấy trạng thái node cũ và mới.

### 23.7. Duplicate scraping

Tránh scrape cùng exporter qua nhiều job với labels khác nhau nếu không có mục đích. Duplicate series làm dashboard đếm hai lần và tăng storage.

## 24. Labels và cardinality

Cardinality là số lượng time series khác nhau. Nó ảnh hưởng trực tiếp tới RAM, CPU, disk và query performance của Prometheus.

### 24.1. Cardinality tăng theo tổ hợp

Một metric có 5 clusters, 10 instances, 20 databases và 6 states có thể tạo nhiều series theo tổ hợp labels.

### 24.2. Stable labels

Labels tốt thường là:
- cluster
- environment
- instance
- region
- database name nếu số lượng database được kiểm soát
- application_name nếu danh sách hữu hạn và có quy ước

### 24.3. High-cardinality labels

Tránh:
- raw SQL/query text
- PID
- transaction ID
- user/customer ID
- request ID
- file path thay đổi
- arbitrary client address từ workload lớn

### 24.4. Label churn

Một label value thay đổi liên tục tạo series mới. Series cũ vẫn chiếm storage cho tới khi retention và compaction xử lý.

### 24.5. Metric design review

Trước khi thêm custom metric, ước lượng số giá trị label tối đa và số series tổng. Kiểm tra cả số targets và scrape interval.

### 24.6. Không nhồi metadata vào labels

Nếu cần mô tả chi tiết object, có thể lưu inventory ở một hệ thống khác hoặc dùng dashboard table theo truy vấn chậm. Metrics nên tập trung vào số liệu tổng hợp có ý nghĩa vận hành.

## 25. PromQL cơ bản cho PostgreSQL

PromQL truy vấn time series đã scrape.

### 25.1. Instant vector

Lấy giá trị gần nhất của một metric:

~~~promql
pg_up
~~~

### 25.2. Range vector

Lấy samples trong một cửa sổ:

~~~promql
pg_stat_database_xact_commit[5m]
~~~

### 25.3. Rate

Dùng rate() cho counter để tính tốc độ trung bình mỗi giây:

~~~promql
rate(pg_stat_database_xact_commit[5m])
~~~

### 25.4. Increase

Dùng increase() để ước lượng tổng tăng trong cửa sổ:

~~~promql
increase(pg_stat_database_deadlocks[1h])
~~~

### 25.5. Sum by

Tổng hợp theo cluster/database:

~~~promql
sum by (cluster, datname) (
  rate(pg_stat_database_xact_commit[5m])
)
~~~

### 25.6. Max by

Tìm instance có giá trị lớn nhất:

~~~promql
max by (cluster, instance) (
  pg_exporter_scrape_duration_seconds
)
~~~

Tên metric ví dụ cần được xác nhận trong exporter thực tế.

### 25.7. Clamp

clamp_min() hoặc clamp_max() giúp tránh chia cho zero hoặc giới hạn giá trị hiển thị.

### 25.8. Absent

absent() có thể giúp phát hiện metric không còn xuất hiện, nhưng alert target availability thường nên dùng built-in up metric và service discovery state.

## 26. Rate, counter reset và thống kê PostgreSQL

### 26.1. Counter reset

PostgreSQL statistics có thể reset khi server/database restart, stats reset function được gọi hoặc theo hành vi version. Exporter process restart cũng có thể làm thay đổi một số metric process-local.

### 26.2. Dùng rate trước aggregation

Với counter nhiều instances, thường tính rate từng series rồi mới sum để Prometheus xử lý reset đúng cho từng series.

~~~promql
sum by (cluster) (
  rate(pg_stat_database_xact_commit[5m])
)
~~~

### 26.3. Không rate gauge

Connection count, dead tuple estimate và lag hiện tại là gauges. Không dùng rate() trực tiếp trừ khi đang phân tích thay đổi theo thời gian có chủ đích.

### 26.4. Scrape gaps

Nếu scrape bị gián đoạn, rate/increase có thể không ổn định hoặc thiếu dữ liệu. Dashboard cần hiển thị target availability song song.

### 26.5. Stats reset markers

Lưu ý stats_reset trong PostgreSQL. Một dashboard tốt có thể annotate restart/reset events để giải thích đường biểu đồ thay đổi đột ngột.

### 26.6. Baseline theo workload

Transaction rate và I/O thay đổi theo giờ/ngày. Alert nên dựa trên baseline, SLO và mức ảnh hưởng thay vì một threshold tuyệt đối dùng cho mọi thời điểm.

## 27. Dashboard tổng quan PostgreSQL

Dashboard overview nên trả lời nhanh: instance có hoạt động không, tải hiện tại ra sao và có dấu hiệu nguy hiểm nào?

### 27.1. Stat panels

Các stat panels nên gồm:
- PostgreSQL availability.
- Exporter scrape health.
- Instance role: primary hay standby.
- Connections hiện tại và utilization.
- Transaction rate.
- Replication lag/bytes behind.
- Disk free.
- WAL archive failures.
- Deadlocks trong cửa sổ gần nhất.

### 27.2. Time series panels

Hiển thị:
- Transactions commit/rollback rate.
- Active/idle/waiting sessions.
- Block reads/hits.
- WAL bytes per second.
- Replication receive/replay progress.
- Dead tuple trend.
- Disk latency và filesystem usage.

### 27.3. Table panels

Dùng bảng cho:
- Top databases theo transaction rate.
- Top tables theo dead tuple estimates.
- Replicas theo state/lag.
- Top query fingerprints theo total execution time.

### 27.4. Variables

Dashboard variables có thể lọc cluster, instance, database và environment. Tránh variables có hàng chục nghìn giá trị.

### 27.5. Thresholds

Màu threshold nên gắn với operational policy. Không dùng màu đỏ cho một counter tích lũy lớn nếu không có rate hoặc baseline.

### 27.6. Panel descriptions

Mô tả đơn vị, nguồn metric, công thức và caveats. Người trực ca cần biết một con số là bytes, seconds, ratio hay cumulative count.

## 28. Dashboard workload và connections

### 28.1. Transaction throughput

Vẽ commit và rollback rates theo database. So sánh với request rate ở application layer.

### 28.2. Session state

Stacked time series cho active, idle, idle in transaction và các state khác. Định nghĩa state labels phải thống nhất.

### 28.3. Connection utilization

Hiển thị current connections, max_connections và reserved capacity. Thêm cảnh báo headroom thấp.

### 28.4. Wait events

Phân nhóm wait_event_type để nhận biết Lock, IO, Client, LWLock và các nhóm khác. Tên cụ thể tùy PostgreSQL version.

### 28.5. Long-running transactions

Bảng điều tra có query age, transaction age, application_name và wait event. Hạn chế hiển thị query text cho người không có quyền.

### 28.6. Connection pool

Đưa application pool metrics vào dashboard cùng database metrics. PostgreSQL không biết toàn bộ request đang chờ ở pool phía ứng dụng.

## 29. Dashboard cache, I/O và query performance

### 29.1. Cache hit ratio

Hiển thị ratio cùng absolute block read rate. Không dùng một tỷ lệ đơn lẻ để kết luận performance.

### 29.2. Disk throughput

Kết hợp node_exporter disk metrics với pg_stat_io hoặc database block reads.

### 29.3. Query total time

Dùng pg_stat_statements để xem query fingerprints chiếm nhiều tổng execution time.

### 29.4. Mean latency

Hiển thị mean execution time và calls. Với latency distribution, cần histogram/instrumentation phù hợp thay vì chỉ dùng mean.

### 29.5. Temp I/O

Temp bytes/files tăng có thể báo hiệu spill. Đối chiếu với query, work_mem và disk capacity.

### 29.6. Index usage

Dùng table panels để tìm indexes ít được scan, nhưng không tự động xóa dựa trên dashboard. Kiểm tra constraint dependencies và workload dài hạn.

### 29.7. Query plan

Dashboard metrics chỉ chỉ ra nơi cần điều tra. Dùng EXPLAIN (ANALYZE, BUFFERS) trong môi trường phù hợp để phân tích query plan.

## 30. Dashboard replication và HA

### 30.1. Role

Hiển thị trạng thái pg_is_in_recovery cho mỗi instance. Role có thể thay đổi khi promotion.

### 30.2. Sender state

Trên primary, hiển thị state, sync_state, sent/write/flush/replay LSN của từng standby.

### 30.3. Replay gap

Hiển thị bytes behind. Nếu cần lag seconds, tính từ WAL generation rate hoặc metric có semantics phù hợp, không suy ra chỉ từ một LSN gap.

### 30.4. Receiver state

Trên standby, hiển thị receiver status, sender host và latest_end_lsn.

### 30.5. Synchronous replication

Hiển thị sync_state và trạng thái synchronous standbys. Theo dõi số synchronous standbys sẵn sàng theo policy.

### 30.6. Replication slots

Hiển thị active, restart_lsn, wal_status và retained WAL estimate. Alert khi slot giữ WAL quá nhiều hoặc có nguy cơ invalidation.

### 30.7. Timeline

Role/replication dashboard không thay thế timeline history inspection khi failover. Ghi nhận timeline và system identifier trong incident tooling hoặc inventory.

### 30.8. Standby conflicts

Nếu có hot standby workload, theo dõi pg_stat_database_conflicts và replay lag để phát hiện query cancellation do recovery.

## 31. Dashboard vacuum, storage và capacity

### 31.1. Database size

Theo dõi dung lượng database theo thời gian. Size query có thể tốn thời gian nếu chạy trên nhiều objects; cân nhắc scrape interval dài.

### 31.2. Table growth

Theo dõi top tables/indexes theo size và growth rate. Kết hợp application release để giải thích thay đổi schema.

### 31.3. Dead tuples

Hiển thị estimates theo table/database và xu hướng qua nhiều lần scrape.

### 31.4. Autovacuum activity

Theo dõi last_autovacuum, vacuum progress, number of active workers và transaction ID age.

### 31.5. Freeze age

Đặt cảnh báo theo ngưỡng phù hợp với autovacuum_freeze_max_age và policy vận hành. Không chờ sát giới hạn mới hành động.

### 31.6. Disk capacity

Filesystem usage phải lấy từ node_exporter hoặc hệ thống host monitoring. Database size không cho biết dung lượng filesystem còn trống.

### 31.7. WAL disk

Theo dõi pg_wal directory usage, replication slots, archive queue và free disk. WAL retention có thể tăng nhanh khi standby/consumer lag.

## 32. Alerting: từ metric đến hành động

Dashboard giúp người vận hành nhìn dữ liệu; alert giúp phát hiện điều kiện cần hành động.

### 32.1. Alert condition

Một alert rule có expression, pending duration, labels và annotations.

### 32.2. Severity

Dùng severity như warning/critical theo mức ảnh hưởng và thời gian cần phản hồi.

### 32.3. For duration

Thêm for: để tránh cảnh báo từ một spike ngắn không có ý nghĩa. Giá trị phụ thuộc tốc độ phát hiện mong muốn.

### 32.4. Annotations

Alert nên chứa summary, description, instance, cluster và runbook URL/path theo hệ thống nội bộ.

### 32.5. Alertmanager

Alertmanager grouping giúp gộp nhiều instance alerts thành một incident, routing theo cluster/team/severity và silence trong maintenance window.

### 32.6. Alert quality

Mỗi alert cần có owner, hành động tiếp theo và cách xác định false positive. Alert không có người nhận hoặc không có runbook sẽ nhanh chóng bị bỏ qua.

## 33. Alert rules minh họa

Tên metric cụ thể phải được kiểm tra từ phiên bản exporter. Các rule dưới đây minh họa cấu trúc và cần điều chỉnh theo môi trường.

~~~yaml
groups:
  - name: postgresql-availability
    rules:
      - alert: PostgreSQLExporterTargetDown
        expr: up{job="postgresql"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL exporter target is unreachable"
          description: "Prometheus cannot scrape this exporter endpoint."

      - alert: PostgreSQLDatabaseUnavailable
        expr: pg_up{job="postgresql"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Exporter cannot collect PostgreSQL metrics"
          description: "Check database connectivity, authentication and exporter logs."
~~~

### 33.1. Exporter target down

Built-in up bằng 0 có nghĩa Prometheus không scrape được endpoint exporter. Có thể do exporter process, network, TLS hoặc scrape timeout.

### 33.2. Database unavailable

Nếu exporter endpoint vẫn scrape được nhưng metric pg_up cho biết database connection thất bại, vấn đề nằm ở kết nối exporter tới PostgreSQL hoặc trạng thái database.

### 33.3. Deadlocks

Ví dụ alert khi deadlock rate lớn hơn zero trong một cửa sổ có ý nghĩa. Tên metric và kiểu dữ liệu phải xác nhận trước.

~~~yaml
      - alert: PostgreSQLDeadlocksDetected
        expr: increase(pg_stat_database_deadlocks[10m]) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "PostgreSQL deadlocks detected"
          description: "Review database logs and transaction lock ordering."
~~~

### 33.4. Connection saturation

Alert theo tỷ lệ connections trên max_connections và reserved capacity. Tạo metric ratio riêng nếu exporter không xuất max_connections theo labels mong muốn.

### 33.5. Replication lag

Alert theo bytes behind hoặc một lag metric đã xác định semantics. Threshold phải gắn với RPO và workload WAL rate.

### 33.6. Archive failure

Theo dõi delta của failed_count hoặc last_failed_time. Một counter cũ không nên tạo alert liên tục sau khi lỗi đã được xử lý.

### 33.7. Disk space

Dùng node filesystem metrics và alert theo free space/forecast. Disk full là rủi ro ảnh hưởng toàn cluster.

## 34. Recording rules và dashboard efficiency

### 34.1. Recording rule

Recording rule lưu kết quả PromQL thường dùng thành time series mới để dashboard không phải tính lại query nặng mỗi lần mở.

~~~yaml
groups:
  - name: postgresql-recording
    interval: 30s
    rules:
      - record: cluster:postgresql_commits_per_second:rate5m
        expr: |
          sum by (cluster, datname) (
            rate(pg_stat_database_xact_commit[5m])
          )
~~~

### 34.2. Dùng lại logic

Dashboard, alert và SLO có thể dùng cùng recording metric, giảm khác biệt công thức giữa các panel.

### 34.3. Không ghi mọi thứ

Recording rules làm tăng số series được lưu. Chỉ ghi các metric có giá trị sử dụng lặp lại.

### 34.4. Rule evaluation

Chọn evaluation interval phù hợp với scrape interval và alert latency. Không đánh giá alert nhanh hơn mức dữ liệu có thể được scrape một cách hữu ích.

### 34.5. Kiểm thử rules

Dùng promtool check rules và unit tests cho alert rules khi môi trường hỗ trợ. Kiểm tra cả no data, counter reset và label matching.

## 35. Bảo mật monitoring stack

Metrics không phải lúc nào cũng vô hại. Chúng có thể tiết lộ database names, usernames, application names, query fingerprints, topology và thông tin vận hành.

### 35.1. Monitoring role

Dùng role riêng, pg_monitor khi phù hợp và quyền SELECT tối thiểu cho custom queries.

### 35.2. Network isolation

Chỉ cho phép Prometheus truy cập exporter endpoint. Không expose /metrics trực tiếp ra public internet.

### 35.3. TLS và authentication

Bảo vệ exporter endpoint bằng private network, TLS, authentication hoặc reverse proxy tùy threat model. Prometheus cũng cần xác minh TLS khi scrape HTTPS.

### 35.4. Secret storage

Lưu database passwords trong secret manager, protected files hoặc orchestration secrets. Không commit credentials vào Git hoặc dashboard JSON.

### 35.5. Grafana access

Phân quyền dashboard/data source theo team. Hạn chế quyền Explore nếu người dùng có thể truy vấn dữ liệu nhạy cảm.

### 35.6. Query text

Không export raw SQL hoặc bind values thành labels. Nếu hiển thị query text, giới hạn người xem và áp dụng masking phù hợp.

### 35.7. Audit

Ghi nhận ai thay đổi scrape config, dashboards, alert rules, credentials và access policy.

## 36. Theo dõi exporter và monitoring stack

Monitoring system cũng cần được giám sát.

### 36.1. Prometheus up

Theo dõi Prometheus process, scrape duration, scrape samples, TSDB head series và disk usage.

### 36.2. Exporter scrape duration

Scrape duration tăng có thể báo hiệu custom query chậm, database load cao hoặc network latency.

### 36.3. Scrape samples

Số samples tăng bất thường có thể đến từ cardinality bùng nổ hoặc collector mới.

### 36.4. Scrape errors

Theo dõi target up, scrape errors, timeouts và exporter logs.

### 36.5. Grafana availability

Dashboard không có dữ liệu có thể do Grafana, data source, Prometheus hoặc exporter. Theo dõi từng thành phần riêng.

### 36.6. Alert delivery

Kiểm tra Alertmanager notification pipeline, receiver health, retries và silence state. Không giả định alert được gửi chỉ vì Prometheus rule firing.

### 36.7. Backup monitoring data

Nếu Prometheus là nguồn audit/SLO quan trọng, xác định retention, remote storage, backup và restore strategy của monitoring stack.

## 37. Khác biệt phiên bản PostgreSQL và exporter

Metrics phụ thuộc PostgreSQL version, exporter version, enabled collectors và quyền role.

### 37.1. Statistics views thay đổi

Columns và views có thể được thêm, đổi hoặc bỏ qua các major versions. Ví dụ I/O statistics và checkpoint/background writer statistics có thay đổi giữa các phiên bản.

### 37.2. PostgreSQL 16 trở lên

pg_stat_io có sẵn từ PostgreSQL 16. Không dùng query/view này trên server cũ hơn nếu không có compatibility handling.

### 37.3. Checkpoint statistics

Các phiên bản mới có thể tách checkpoint statistics khỏi một số trường trong pg_stat_bgwriter. Kiểm tra view/column thực tế trên major version đang chạy.

### 37.4. Exporter compatibility

Exporter có thể có collectors riêng cho từng version và metrics names khác nhau. Không copy dashboard từ một exporter version mà không xác nhận metric names.

### 37.5. Feature detection

Có thể kiểm tra schema view qua information_schema hoặc catalog queries, rồi triển khai custom query theo version. Tốt hơn là quản lý query files theo compatibility matrix.

### 37.6. Version labels

Ghi PostgreSQL version và exporter version trong inventory/metadata. Có thể thêm info metric nếu exporter hỗ trợ.

## 38. Troubleshooting metrics và dashboard

### Lỗi 1. Prometheus target down

Kiểm tra exporter process, port, network, firewall, TLS, DNS và scrape timeout.

### Lỗi 2. Exporter chạy nhưng pg_up bằng 0

Kiểm tra DSN, database role, pg_hba.conf, password, SSL và PostgreSQL availability.

### Lỗi 3. Endpoint /metrics trả lỗi query

Xem exporter logs, collector gây lỗi, PostgreSQL permissions và custom query compatibility.

### Lỗi 4. Thiếu metric

Kiểm tra collector có được bật không, version exporter có hỗ trợ không, database có statistics view tương ứng và scrape có lỗi không.

### Lỗi 5. Metric name khác dashboard

Đọc trực tiếp /metrics và cập nhật PromQL/dashboard theo HELP/TYPE thực tế. Không đoán tên từ blog hoặc dashboard cũ.

### Lỗi 6. Dashboard hiển thị No data

Kiểm tra time range, datasource, labels, metric existence, scrape target và PromQL selector.

### Lỗi 7. Giá trị counter về zero

Kiểm tra PostgreSQL restart, stats reset, exporter restart hoặc target label thay đổi. Dùng rate() và reset-aware analysis.

### Lỗi 8. Cache hit ratio bằng NaN

Có thể mẫu không có block accesses hoặc denominator bằng zero. Dùng clamp_min và hiển thị No traffic khi không có dữ liệu.

### Lỗi 9. Scrape timeout

Giảm custom query cost, tách collector nặng, tăng timeout trong giới hạn interval hoặc giảm target load.

### Lỗi 10. PostgreSQL load tăng sau khi bật exporter

Đếm connections và query frequency từ exporter. Giảm collectors, scrape interval hoặc chuyển inventory query sang job chậm hơn.

### Lỗi 11. Cardinality tăng mạnh

Tìm metric/label có số series lớn, bỏ PID/raw query/user IDs và aggregate dữ liệu trước khi export.

### Lỗi 12. Alert lặp lại sau khi đã xử lý

Kiểm tra expression, pending duration, counter reset, stale series, labels và Alertmanager grouping/inhibition.

### Lỗi 13. Replication dashboard không có standby

Kiểm tra exporter target trên standby, pg_stat_wal_receiver, primary pg_stat_replication và service discovery.

### Lỗi 14. Lag metric không đổi khi primary idle

Lag time fields có thể null hoặc giữ giá trị gần đây khi không có WAL mới. Dùng LSN gap và workload context.

### Lỗi 15. Table metrics thiếu database

Kiểm tra database discovery, connection permissions, collector configuration và cách exporter scrape nhiều databases.

### Lỗi 16. Query text lộ dữ liệu

Gỡ query text khỏi labels/dashboard không cần thiết, hạn chế quyền và điều chỉnh custom collector.

### Lỗi 17. Exporter password hết hạn

Kiểm tra secret rotation, exporter restart/reload behavior và authentication logs.

### Lỗi 18. Grafana panel chậm

Tối ưu PromQL, giảm cardinality, dùng recording rules, giảm range query resolution hoặc giới hạn dashboard variables.

### Lỗi 19. Prometheus disk đầy

Kiểm tra retention, scrape volume, WAL/TSDB compaction, remote storage và filesystem capacity.

### Lỗi 20. Metric reset gây alert sai

Alert dựa trên rate/increase và reset-aware query; dùng for duration và kiểm tra reset timestamp.

## 39. Quy trình triển khai monitoring

~~~text
Inventory
   |
   v
Create monitoring role
   |
   v
Install postgres_exporter
   |
   v
Configure DSN / TLS / secret
   |
   v
Test database access
   |
   v
Inspect /metrics
   |
   v
Configure Prometheus target
   |
   v
Verify scrape and labels
   |
   v
Build Grafana dashboards
   |
   v
Add alert rules / Alertmanager
   |
   v
Validate against SQL and incident scenarios
   |
   v
Document ownership and runbooks
~~~

### 39.1. Inventory

Liệt kê clusters, instances, primary/standby roles, databases, PostgreSQL versions, exporter versions và network boundaries.

### 39.2. Role and connectivity

Tạo monitoring role, cấp pg_monitor hoặc quyền cần thiết, kiểm tra TLS và pg_hba.

### 39.3. Exporter

Cài exporter, cấu hình secret, collectors, listen address và service supervision.

### 39.4. Endpoint validation

Kiểm tra /metrics, scrape duration, database connectivity và metrics expected.

### 39.5. Prometheus

Cấu hình scrape jobs/service discovery, labels, interval, timeout và retention.

### 39.6. Grafana

Tạo data source, dashboard variables, panels, units, thresholds và descriptions.

### 39.7. Alerting

Tạo alert rules, route, receivers, grouping, silence policy và runbook references.

### 39.8. Acceptance test

Đối chiếu metrics với SQL trực tiếp, tạo một vài tình huống lab như exporter stop hoặc connection failure, kiểm tra alert flow.

### 39.9. Handover

Ghi owner, escalation path, secret rotation, update cadence và troubleshooting steps.

## 40. Runbook vận hành hằng ngày

1. Kiểm tra Prometheus targets và scrape errors.
2. Kiểm tra exporter availability và PostgreSQL connection health.
3. Kiểm tra primary/standby roles và replication state.
4. Xem connections utilization và active/waiting sessions.
5. Xem transaction rate, rollback rate và deadlocks.
6. Xem WAL generation, archive failures và replication slot retention.
7. Xem replication receive/replay lag.
8. Xem dead tuples, autovacuum recency và transaction ID age.
9. Xem database filesystem free space và WAL directory usage.
10. Kiểm tra alert firing, pending, silences và notification delivery.
11. Ghi nhận các thay đổi lớn so với baseline.
12. Điều tra các metric bất thường bằng SQL/logs/OS metrics.
13. Ghi incident, nguyên nhân, tác động và hành động khắc phục.
14. Xác nhận dashboard/alert sau thay đổi cấu hình.

## 41. Bài tập thực hành

Các bài tập dùng PostgreSQL lab và monitoring stack riêng. Không cố tình làm cạn disk, kill production exporter hoặc tạo tải nặng trên production để thử alert.

### Bài 1. Architecture

Nêu vai trò của postgres_exporter, Prometheus và Grafana.

### Bài 2. Alertmanager

Alertmanager làm gì sau khi Prometheus phát hiện alert?

### Bài 3. Node exporter

Vì sao postgres_exporter không thay thế node_exporter?

### Bài 4. Metric

Phân biệt metric, sample và time series.

### Bài 5. Label

Label nào phù hợp để phân loại cluster/instance?

### Bài 6. Cardinality

Vì sao PID và raw SQL không nên dùng làm labels?

### Bài 7. Monitoring role

Tạo role exporter và cấp pg_monitor bằng SQL nào?

### Bài 8. Superuser

Vì sao không nên dùng superuser làm credential exporter?

### Bài 9. DSN

Một DSN PostgreSQL cần các thông tin nào?

### Bài 10. Endpoint

Endpoint metrics phổ biến của postgres_exporter là gì?

### Bài 11. Scrape

Prometheus chủ động scrape hay exporter push metrics tới Prometheus trong mô hình thông thường?

### Bài 12. up

Prometheus metric up bằng 0 biểu thị điều gì?

### Bài 13. pg_up

pg_up khác up như thế nào?

### Bài 14. Counter

Vì sao dùng rate() cho transaction commit counter?

### Bài 15. Gauge

Connection count là counter hay gauge?

### Bài 16. Cache hit

Nêu công thức tham khảo cho buffer hit ratio và một hạn chế của nó.

### Bài 17. Transactions

View nào cung cấp commits và rollbacks theo database?

### Bài 18. Activity

View nào cung cấp trạng thái backend, wait events và query start time?

### Bài 19. Locks

Hàm nào giúp tìm PID đang block một backend?

### Bài 20. Replication

View nào trên primary cung cấp sent/write/flush/replay LSN?

### Bài 21. Receiver

View nào trên standby cung cấp trạng thái WAL receiver?

### Bài 22. WAL

View nào cung cấp WAL records/bytes/write statistics?

### Bài 23. Archiver

View nào cung cấp archived_count và failed_count?

### Bài 24. Vacuum

View nào cung cấp dead tuple estimates theo table?

### Bài 25. Query statistics

Extension nào cung cấp aggregated query statistics?

### Bài 26. Custom query

Nêu ba nguyên tắc thiết kế custom exporter query.

### Bài 27. Scrape interval

Vì sao scrape interval quá ngắn có thể làm tăng database load?

### Bài 28. Timeout

Scrape timeout cần quan hệ thế nào với scrape interval?

### Bài 29. PromQL rate

Viết PromQL tính commit rate theo database trong 5 phút.

### Bài 30. Recording rule

Recording rule có lợi ích gì?

### Bài 31. Dashboard

Nêu năm panel hữu ích cho dashboard overview.

### Bài 32. Alert

Vì sao alert nên có for duration và runbook?

### Bài 33. Security

Nêu bốn biện pháp bảo vệ exporter endpoint và credentials.

### Bài 34. Version

Vì sao phải kiểm tra metric names theo exporter/PostgreSQL version?

### Bài 35. Stats reset

Điều gì có thể làm counter về thấp và ảnh hưởng rate?

### Bài 36. No data

Nêu các bước điều tra khi Grafana panel hiển thị No data.

### Bài 37. Replication lag

Vì sao replay_lag time field không phải lúc nào cũng là catch-up duration hiện tại?

### Bài 38. Cardinality

Một custom query theo PID và raw SQL có thể gây hậu quả gì?

### Bài 39. Monitoring validation

Nêu các bước đối chiếu exporter metrics với SQL trực tiếp.

### Bài 40. Thiết kế

Đề xuất monitoring stack cho một cluster có một primary và hai standbys, gồm dashboard và alerts quan trọng.

## 42. Lời giải tham khảo

### Bài 1–6. Architecture và metrics

postgres_exporter đọc statistics từ PostgreSQL và xuất metrics; Prometheus scrape/lưu/truy vấn/đánh giá rules; Grafana trình bày dashboard; Alertmanager nhóm và định tuyến notifications. node_exporter thu thập OS metrics. Metric là đại lượng, sample là giá trị kèm timestamp, time series là chuỗi samples cùng metric/labels. Dùng labels cluster, environment và instance. PID/raw SQL tạo cardinality lớn, churn và nguy cơ lộ dữ liệu.

### Bài 7–13. Role và scrape

~~~sql
CREATE ROLE postgres_exporter LOGIN PASSWORD 'replace-with-secret';
GRANT pg_monitor TO postgres_exporter;
~~~

Superuser có quyền quá rộng. DSN cần host, port, database, user, authentication và TLS settings. Endpoint thường là /metrics trên cổng 9187. Prometheus chủ động scrape. up=0 nghĩa scrape endpoint thất bại; pg_up=0 thường cho biết exporter không thu thập được PostgreSQL theo metric semantics của exporter.

### Bài 14–18. Counters và activity

rate() biến counter tích lũy thành tốc độ. Connection count là gauge. Hit ratio tham khảo là blks_hit/(blks_hit+blks_read), nhưng blks_read không đồng nghĩa physical disk reads và ratio không thể hiện mọi bottleneck. pg_stat_database có commits/rollbacks; pg_stat_activity có backend state, waits và query timing.

### Bài 19–25. Locks, replication và query

pg_blocking_pids(pid) tìm blockers. pg_stat_replication ở primary có send/write/flush/replay LSN. pg_stat_wal_receiver ở standby. pg_stat_wal có WAL stats. pg_stat_archiver có archive counts. pg_stat_user_tables có dead tuple estimates. pg_stat_statements cung cấp aggregated query stats.

### Bài 26–30. Custom query và PromQL

Custom query nên nhanh, chỉ đọc, trả schema ổn định và dùng labels giới hạn. Scrape quá ngắn làm query/connection overhead tăng. scrape_timeout phải nhỏ hơn hoặc bằng scrape_interval. Ví dụ:

~~~promql
sum by (cluster, datname) (
  rate(pg_stat_database_xact_commit[5m])
)
~~~

Recording rules lưu kết quả truy vấn phổ biến để dashboard/alerts dùng chung và giảm chi phí query lặp.

### Bài 31–35. Dashboard và bảo mật

Overview panels có availability, exporter health, connections, transaction rate, replication lag, disk free và deadlocks. Alert cần for duration để lọc spike và runbook để hướng dẫn hành động. Bảo vệ bằng network isolation, TLS, secret manager, role tối thiểu, Grafana RBAC và không xuất raw SQL labels. Metric names khác theo version nên kiểm tra /metrics. Restart/stats reset có thể làm counters về thấp.

### Bài 36–40. Troubleshooting và thiết kế

No data: kiểm tra time range, data source, PromQL, labels, metric existence, Prometheus target và exporter logs. replay_lag là thống kê gần đây, có thể null/không thay đổi khi primary idle; đối chiếu LSN. PID/raw SQL labels tạo series churn/cardinality và lộ dữ liệu. Đối chiếu bằng cách chạy cùng SQL với monitoring role, so sánh timestamp, đơn vị, labels, counter/gauge semantics và reset time.

Với một primary và hai standbys, triển khai exporter cho cả ba node, scrape bằng labels cluster/instance/environment, thêm node_exporter cho mỗi host, dashboard overview/workload/replication/vacuum/storage và alerts cho exporter/database down, connection saturation, deadlocks, replication lag, slot retained WAL, archive failures, disk low và transaction ID age. Theo dõi role động bằng pg_is_in_recovery() và kiểm thử failover để xác nhận dashboard nhận biết primary mới.

## 43. Bảng tra cứu nhanh

| Nhu cầu | Nguồn / công cụ |
| --- | --- |
| Export PostgreSQL metrics | postgres_exporter |
| Scrape và lưu time series | Prometheus |
| Dashboard và Explore | Grafana |
| Alert grouping/routing | Alertmanager |
| OS metrics | node_exporter |
| Database commits/rollbacks | pg_stat_database |
| Backend state/waits | pg_stat_activity |
| Blocking PIDs | pg_blocking_pids() |
| Locks | pg_locks |
| Replication sender | pg_stat_replication |
| WAL receiver | pg_stat_wal_receiver |
| WAL generation | pg_stat_wal |
| WAL archive | pg_stat_archiver |
| Table statistics | pg_stat_user_tables |
| Index statistics | pg_stat_user_indexes |
| Vacuum progress | pg_stat_progress_vacuum |
| Query aggregates | pg_stat_statements |
| I/O statistics | pg_stat_io (PostgreSQL 16+) |
| Exporter endpoint | /metrics |
| Prometheus target health | up |
| Database scrape health | pg_up (exporter metric; verify version) |
| Counter rate | rate() |
| Counter delta | increase() |
| Reusable PromQL | Recording rules |
| Rule validation | promtool check rules |

## 44. Checklist triển khai exporter và dashboard

1. Inventory clusters, instances, databases và PostgreSQL major versions.
2. Ghi nhận postgres_exporter version và deployment model.
3. Tạo monitoring role riêng.
4. Cấp pg_monitor hoặc quyền tối thiểu tương đương theo version.
5. Không dùng superuser cho exporter.
6. Cấu hình DSN/secret qua secret mechanism.
7. Dùng TLS và xác minh server identity phù hợp.
8. Giới hạn network tới exporter endpoint.
9. Chọn collectors theo nhu cầu và đo scrape duration.
10. Kiểm tra custom query permissions và execution cost.
11. Tránh PID/raw SQL/user ID làm labels.
12. Kiểm tra /metrics, HELP và TYPE của metrics.
13. Cấu hình Prometheus job, interval, timeout và stable labels.
14. Kiểm tra Prometheus Targets và scrape errors.
15. Scrape từng instance để quan sát node cũ sau failover.
16. Kết hợp node_exporter cho CPU, RAM, disk và network.
17. Tạo Grafana data source và dashboard variables.
18. Thiết kế overview, workload, connection, I/O, replication và vacuum panels.
19. Ghi rõ đơn vị, metric semantics và caveats trong panel descriptions.
20. Dùng rate/increase cho counters và gauge query cho trạng thái hiện tại.
21. Đối chiếu metric với SQL trực tiếp.
22. Kiểm tra stats reset và restart behavior.
23. Tạo alert cho exporter/database availability.
24. Tạo alert cho connection saturation, deadlocks và blocking.
25. Tạo alert cho replication lag, slot retention và archive failures.
26. Tạo alert cho disk capacity, WAL usage và transaction ID age.
27. Thêm for duration, severity, owner và runbook cho từng alert.
28. Cấu hình Alertmanager routing, grouping, silence và notification test.
29. Theo dõi Prometheus/Grafana/Alertmanager health và storage.
30. Review cardinality, scrape load và retention định kỳ.
31. Kiểm tra dashboard sau failover và role changes.
32. Xoay vòng credentials và audit access.
33. Lưu version/configuration/dashboard definitions trong quy trình quản lý thay đổi.
34. Chỉ coi monitoring hoàn tất sau khi kiểm thử được alert end-to-end.

## 45. Tổng kết

postgres_exporter biến statistics của PostgreSQL thành Prometheus metrics; Prometheus scrape và lưu các time series; Grafana trình bày dashboard; Alertmanager định tuyến cảnh báo. Khi ghép thêm node_exporter và application metrics, đội ngũ có thể liên kết database health với host resources và user-visible service behavior.

Một bộ metrics hữu ích cần bao phủ availability, connections, transactions, cache/I/O, locks, WAL, archiving, replication, vacuum, table/index growth và query statistics. pg_stat_database, pg_stat_activity, pg_stat_replication, pg_stat_wal_receiver, pg_stat_wal, pg_stat_archiver, pg_stat_user_tables và pg_stat_statements là những nguồn quan trọng. Các view và metric names có thể thay đổi theo PostgreSQL/exporter version, vì vậy hãy kiểm tra endpoint /metrics và xác nhận bằng SQL trực tiếp.

Dashboard tốt cho người vận hành biết tình trạng hiện tại, xu hướng, headroom và nơi cần điều tra. Alert tốt chỉ kích hoạt khi có điều kiện cần hành động, có thời gian pending phù hợp, owner và runbook. Đừng chỉ hiển thị counters tích lũy; dùng rate/increase cho counters, đơn vị đúng cho gauges và ghi nhận statistics reset.

Monitoring stack cũng cần được bảo vệ và giám sát. Dùng role tối thiểu, secret management, TLS/network isolation, Grafana access control và labels có cardinality thấp. Tránh đưa raw query, PID hoặc business identifiers vào labels. Cuối cùng, đối chiếu metrics với SQL, thử exporter failure/database failure và kiểm tra notification pipeline để biết dashboard và alerts thực sự hoạt động khi có sự cố.
