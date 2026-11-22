# Ngưỡng cảnh báo, khoảng thời gian lấy mẫu và giảm báo động giả

Giám sát PostgreSQL không chỉ là thu thập metrics và đặt một con số làm ngưỡng. Một cảnh báo hữu ích phải phát hiện điều kiện có ý nghĩa, đủ sớm để người vận hành hành động, đồng thời tránh báo động vì dao động ngắn, tải bình thường, dữ liệu thiếu hoặc một lần đo bất thường. Ba quyết định có ảnh hưởng lớn là **ngưỡng cảnh báo**, **khoảng thời gian lấy mẫu**, và **cách xác nhận một điều kiện trước khi phát cảnh báo**.

Ví dụ, CPU tăng lên 95% trong một lần lấy mẫu có thể chỉ là một truy vấn ngắn. CPU duy trì 95% trong 15 phút kèm query latency tăng, pool queue dài và throughput giảm có thể là sự cố thực sự. Tương tự, replication lag tăng trong vài giây chưa chắc đáng báo động; lag tăng liên tục và vượt RPO mục tiêu thì cần can thiệp.

Bài học này hướng dẫn thiết kế alert cho PostgreSQL theo tác động và hành vi của metric. Nội dung bao gồm static/dynamic thresholds, scrape interval, evaluation interval, range window, pending period, hysteresis, no-data handling, severity, Prometheus/Alertmanager examples, SLO-based alerts, và các kỹ thuật giảm false positives mà vẫn giữ khả năng phát hiện sự cố.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt metric, threshold, condition, alert và notification.
2. Chọn ngưỡng theo SLO, capacity, RPO/RTO và baseline.
3. Phân biệt static threshold và dynamic/anomaly threshold.
4. Chọn sampling/scrape interval phù hợp với tốc độ thay đổi của metric.
5. Phân biệt scrape interval, evaluation interval, range window và pending duration.
6. Dùng rate/increase cho counter thay vì alert trực tiếp trên giá trị counter tích lũy.
7. Thiết kế sustained-breach, hysteresis và recovery threshold.
8. Xử lý no data, stale samples, scrape failures và counter resets.
9. Phân biệt cảnh báo symptom với cảnh báo cause.
10. Thiết kế severity, routing, grouping, inhibition và maintenance windows.
11. Viết alert rules cho PostgreSQL connections, replication lag, disk, locks, WAL và backup.
12. Dùng multi-window/multi-burn-rate alerts cho SLO.
13. Đo false-positive rate và cải thiện alert quality.
14. Xây dựng runbook, escalation và kiểm thử cảnh báo.

> **Phạm vi:** Các ví dụ dùng PostgreSQL và Prometheus/Alertmanager phổ biến. Cú pháp, tính năng và metric names phụ thuộc phiên bản/tool. Luôn xác nhận tài liệu đúng phiên bản và tên metrics exporter thực tế trước khi đưa cấu hình vào production.

## 2. Metric, threshold và alert khác nhau thế nào?

- **Metric** là phép đo theo thời gian, ví dụ CPU utilization, số active connections, WAL bytes hoặc replication lag.
- **Threshold** là ranh giới dùng để đánh giá metric, ví dụ disk utilization lớn hơn 85%.
- **Condition** là biểu thức xác định trạng thái, có thể kết hợp nhiều metrics và nhiều khoảng thời gian.
- **Alert** là trạng thái được tạo khi condition thỏa mãn theo rule.
- **Notification** là thông điệp được gửi tới người hoặc hệ thống xử lý.

Không phải mọi metric vượt threshold đều cần page người trực. Alert chỉ hữu ích khi nó mô tả một rủi ro có ý nghĩa và người nhận biết phải làm gì.

### Ví dụ

Một alert có thể diễn đạt:

> PostgreSQL primary còn dưới 10% dung lượng filesystem, tốc độ tăng dữ liệu hiện tại dự kiến làm đầy disk trong vòng 30 phút. Kiểm tra WAL retention, replication slots, archive và data growth.

Thông điệp này có metric, threshold, thời gian duy trì, impact và hành động ban đầu. Một cảnh báo chỉ nói “disk high” sẽ kém hữu ích hơn.

## 3. Alert dựa trên impact, không chỉ dựa trên metric

Metric là tín hiệu; impact là lý do cần hành động. Trước khi đặt alert, xác định:

1. Tác động nào xảy ra nếu metric tiếp tục xấu đi?
2. Có bao nhiêu thời gian để xử lý trước khi người dùng bị ảnh hưởng?
3. Ai có thể hành động và hành động nào khả thi?
4. Có thể phát hiện cùng sự cố bằng symptom gần người dùng hơn không?
5. Điều kiện nào đủ nghiêm trọng để page ngay?

Ví dụ, CPU 90% không tự động là sự cố. Nếu throughput ổn định, latency tốt và CPU có headroom phù hợp thì có thể chỉ cần dashboard. Nếu CPU 90% kéo dài, request latency vượt SLO và pool queue tăng thì cần alert.

### Alert symptom và cause

- **Symptom alert:** API latency vượt SLO, connection acquisition timeout tăng, replication không theo kịp.
- **Cause alert:** CPU saturation, disk pressure, lock contention, autovacuum bị chặn.

Symptom thường cho biết người dùng đang bị ảnh hưởng. Cause giúp tìm nguyên nhân. Nên có cả hai nhưng tránh page nhiều alert độc lập cho cùng một incident.

## 4. Xác định mục tiêu trước khi đặt threshold

Các nguồn để chọn ngưỡng:

- SLO/SLI của dịch vụ.
- RPO và RTO.
- Connection budget và max_connections.
- Dung lượng filesystem và tốc độ tăng trưởng.
- WAL generation rate và retention policy.
- Replication lag được workload chấp nhận.
- Backup window và restore objective.
- Query latency/throughput baseline.
- Capacity headroom theo giờ cao điểm.

### Ví dụ về RPO

Nếu DR standby phải duy trì RPO 60 giây, alert replication lag nên phát hiện sớm hơn thời điểm vượt 60 giây, có tính tới scrape/evaluation/notification delay và thời gian người trực phản ứng. Đặt threshold đúng bằng 60 giây có thể phát hiện quá muộn.

### Threshold phải có owner

Mỗi alert nên có owner chịu trách nhiệm giải thích threshold, xác nhận nó còn phù hợp sau thay đổi capacity/workload và cập nhật runbook.

## 5. Static threshold

Static threshold là một giá trị cố định:

```text
disk_used_percent > 85
active_connections > 180
replication_lag_seconds > 30
```

### Ưu điểm

- Dễ hiểu và dễ kiểm thử.
- Dễ giải thích cho người trực.
- Phù hợp với hard limits hoặc policy rõ ràng.
- Không cần lịch sử dài để tính baseline.

### Hạn chế

- Có thể quá nhạy với workload thay đổi theo giờ.
- Có thể quá lỏng ở hệ thống nhỏ và quá chặt ở hệ thống lớn.
- Một giá trị không phản ánh tốc độ thay đổi.
- Dễ báo động khi metric bình thường dao động quanh threshold.

Static threshold phù hợp với giới hạn tài nguyên, SLO boundary hoặc policy có ý nghĩa rõ. Nó cần được hiệu chỉnh theo capacity và workload.

## 6. Relative threshold và dynamic baseline

Relative threshold so sánh metric hiện tại với baseline hoặc metric liên quan. Ví dụ:

- Query rate giảm 70% so với cùng khung giờ tuần trước.
- WAL generation tăng gấp 4 lần baseline 30 ngày.
- Connection usage vượt 90% pool budget.
- Latency p95 cao hơn baseline 3 lần.

Dynamic baseline có thể dùng moving average, median, percentile, seasonal baseline hoặc mô hình anomaly detection.

### Cẩn trọng với baseline

- Baseline bị ảnh hưởng bởi sự cố kéo dài có thể học nhầm trạng thái xấu thành bình thường.
- Workload thay đổi theo ngày/giờ cần baseline theo mùa vụ.
- Hệ thống mới thiếu lịch sử đủ dài.
- Một metric có distribution lệch mạnh có thể không phù hợp với mean/stddev.
- Dynamic threshold khó giải thích nếu không hiển thị baseline và confidence.

Không dùng anomaly detection làm lớp bảo vệ duy nhất cho hard capacity limits.

## 7. Threshold theo tỷ lệ và theo lượng tuyệt đối

Disk alert thường cần cả phần trăm và dung lượng còn trống:

- 90% trên volume 20 GB chỉ còn 2 GB.
- 90% trên volume 10 TB còn 1 TB.

Ngược lại, 95% utilization trên một volume nhỏ có thể đầy rất nhanh. Dùng thêm free bytes và growth rate.

Connection alert cũng nên dùng tỷ lệ:

\[
\text{connection utilization} =
\frac{\text{current connections}}{\text{usable connection budget}} \times 100\%
\]

Usable budget cần trừ reserved connections, admin headroom, replication và các pooler/backend consumers khác. Không mặc định max_connections là toàn bộ ngân sách cho ứng dụng.

## 8. Ngưỡng theo tốc độ thay đổi

Một metric ở mức 80% có thể an toàn nếu ổn định, nhưng nguy hiểm nếu tăng 5% mỗi phút. Alert theo tốc độ thay đổi có thể phát hiện vấn đề trước khi chạm hard limit.

Ví dụ:

- Disk free bytes giảm hơn 2 GB trong 10 phút.
- WAL retained distance tăng liên tục.
- Connection count tăng nhanh sau deploy.
- Replication lag tăng theo từng evaluation window.

### Time-to-exhaustion

Ước lượng:

\[
\text{time to full} =
\frac{\text{free capacity}}{\text{positive consumption rate}}
\]

Đây chỉ là dự báo gần đúng. Growth rate có thể đổi đột ngột; cần smoothing, giới hạn tối thiểu cho rate và kiểm tra đủ sample points.

## 9. Sampling interval là gì?

Sampling interval là khoảng cách giữa các lần lấy mẫu metric. Trong Prometheus, scrape interval là chu kỳ Prometheus scrape target. Với agent/monitoring service khác, tên gọi có thể là collection interval hoặc polling interval.

Ví dụ:

- 5 giây: thu thập metric mỗi 5 giây.
- 15 giây: thu thập mỗi 15 giây.
- 60 giây: thu thập mỗi phút.

### Sampling quá thưa

- Có thể bỏ lỡ spike ngắn.
- Phát hiện sự cố muộn hơn.
- Rate calculations có ít sample points.
- Khó phân biệt outage ngắn với metric stale.

### Sampling quá dày

- Tăng load lên exporters, agents và monitoring backend.
- Tăng network/storage/cardinality cost.
- Tạo nhiều data points nhưng không nhất thiết cải thiện quyết định.
- Query/evaluation tốn tài nguyên hơn.

Chọn interval theo tốc độ metric thay đổi và thời gian phản ứng cần thiết, không đặt mọi metric cùng một chu kỳ mà không xem xét.

## 10. Phân biệt scrape, evaluation và notification intervals

Các khoảng thời gian sau có vai trò khác nhau:

| Khoảng thời gian | Ý nghĩa |
|---|---|
| Scrape/collection interval | Bao lâu thu thập sample mới |
| Evaluation interval | Bao lâu đánh giá alert rules |
| Range window | Khoảng lịch sử dùng trong biểu thức, ví dụ 5 phút |
| Pending duration / for | Condition phải liên tục đúng bao lâu trước khi firing |
| Notification group_wait | Chờ gom các alert liên quan trước khi gửi |
| Group_interval | Khoảng cách giữa các notification cập nhật trong group |
| Repeat_interval | Khoảng cách nhắc lại notification chưa resolve |

Ví dụ: scrape mỗi 15 giây, evaluate mỗi 30 giây, biểu thức dùng range 5 phút, và for là 3 phút. Đây không có nghĩa alert chắc chắn phát sau đúng 3 phút kể từ lúc metric bắt đầu xấu; còn có scrape/evaluation alignment, pending state và notification delay.

## 11. Chọn scrape interval

Scrape interval nên đủ nhanh để nhận biết thay đổi quan trọng, nhưng không gây tải không cần thiết.

Một số hướng tham khảo:

| Metric class | Khoảng lấy mẫu tham khảo | Lý do |
|---|---:|---|
| Node/DB availability | 5–15 giây | Phát hiện outage tương đối nhanh |
| Connections, CPU, memory | 15–30 giây | Theo dõi saturation |
| Replication lag | 5–15 giây với RPO chặt; dài hơn nếu workload cho phép | Cần phản ứng theo RPO |
| Backup completion/status | 1–5 phút hoặc theo event | Không cần polling quá dày |
| Capacity growth | 1–5 phút | Quan tâm trend hơn spike |
| Configuration inventory | 5–15 phút hoặc theo event | Ít thay đổi |

Đây là điểm bắt đầu, không phải chuẩn chung. Exporter scrape duration, số targets và backend capacity cũng giới hạn interval thực tế.

## 12. Chọn evaluation interval

Evaluation interval quyết định alert engine đánh giá biểu thức bao lâu một lần. Nếu scrape mỗi 15 giây nhưng evaluate mỗi 2 phút, alert có thể phát hiện chậm hơn dự kiến.

### Quy tắc thực tế

- Evaluation interval không nên quá dài so với response objective.
- Không cần evaluate nhanh hơn nhiều lần so với sample mới.
- Các rule cùng nhóm có thể dùng evaluation group interval phù hợp.
- Cân nhắc query cost nếu rule chạy trên nhiều series/high cardinality.

Một alert phát hiện disk sắp đầy có thể evaluate mỗi 30–60 giây; một trend capacity dài hạn có thể evaluate mỗi vài phút.

## 13. Range window và rolling aggregation

Range window là khoảng lịch sử mà biểu thức dùng để tính toán. Ví dụ rate của counter trên cửa sổ 5 phút tính tốc độ trung bình trong 5 phút đó.

Window ngắn:

- Phản ứng nhanh.
- Nhạy với noise và burst.
- Có thể không đủ samples nếu scrape thưa hoặc có gaps.

Window dài:

- Làm mượt noise.
- Phản ánh trend bền hơn.
- Có thể che spike hoặc phát hiện muộn.

### Chọn window

Chọn theo behavior của metric và impact. Query latency API có thể cần cửa sổ 5 phút và SLO windows dài hơn; disk capacity cần trend 15–60 phút hoặc nhiều giờ; replication lag có thể dùng cả instant value và sustained window.

## 14. Pending duration và sustained condition

Pending duration yêu cầu condition tiếp tục đúng trong một khoảng thời gian trước khi alert chuyển sang firing.

Ví dụ Prometheus:

```yaml
groups:
  - name: postgres-capacity
    rules:
      - alert: PostgresDiskUsageHigh
        expr: postgres_filesystem_used_ratio > 0.85
        for: 10m
        labels:
          severity: warning
```

Condition phải duy trì qua pending period mới firing. Nếu metric giảm xuống dưới threshold trước đó, pending state được reset theo semantics của rule engine.

### Không đặt pending quá dài

Nếu disk chỉ còn 2 phút trước khi đầy, for 15 phút là quá muộn. Pending duration phải tính cùng tốc độ deterioration và thời gian xử lý.

### Không đặt pending quá ngắn

Không có pending period có thể làm alert chớp liên tục khi metric dao động. Dùng sustained condition cho tín hiệu nhiễu, nhưng giữ alert nhanh cho hard failures cần phản ứng ngay.

## 15. Dùng rate cho counter

Counter tăng dần như transaction commits, WAL bytes hoặc query counts không nên so sánh trực tiếp với threshold tuyệt đối qua thời gian. Dùng rate hoặc increase để đo tốc độ/độ tăng trong window.

Ví dụ PromQL:

```promql
rate(pg_stat_database_xact_commit[5m])
```

Đếm số commits trong 5 phút:

```promql
increase(pg_stat_database_xact_commit[5m])
```

### Counter reset

PostgreSQL restart hoặc stats reset có thể làm counter giảm về 0. Prometheus rate xử lý counter reset theo semantics của nó; không viết phép trừ sample hiện tại với sample trước một cách ngây thơ.

### Gauge khác counter

CPU utilization, active connections, disk free bytes và replication lag thường là gauge. Chúng có thể tăng hoặc giảm; dùng comparison/aggregation thích hợp thay vì rate mặc định.

## 16. Percentile và average

Average latency có thể che giấu tail latency. Một hệ thống có nhiều request nhanh và một nhóm request cực chậm vẫn có average chấp nhận được.

Theo dõi:

- p50: trải nghiệm điển hình.
- p95: tail latency phổ biến cho phần lớn requests.
- p99: tail latency nghiêm trọng hơn.
- Error rate và throughput để bổ sung context.

Với histogram Prometheus, dùng histogram_quantile trên bucket rates. Không tính percentile bằng cách lấy trung bình các p95 từ từng instance; cần aggregate bucket counts trước rồi mới tính quantile.

## 17. Threshold theo role và node

Không nên áp dụng cùng một alert cho primary và standby nếu ý nghĩa khác nhau.

Ví dụ:

- Primary connection utilization cao có thể đe dọa nhận writes.
- Standby connection utilization cao có thể ảnh hưởng read traffic nhưng không trực tiếp chặn writes.
- Primary replay lag không phải tín hiệu thông thường như standby replay lag.
- WAL receiver down trên standby có ý nghĩa khác với không có WAL receiver trên primary.

Gắn labels như cluster, node, role, environment và service. Alert expression nên lọc/nhóm theo role phù hợp; không suy luận role từ hostname nếu topology có thể đổi sau failover.

## 18. Threshold cho PostgreSQL connections

pg_stat_activity cho biết sessions; max_connections là giới hạn cấu hình, nhưng ứng dụng không nên tiêu thụ toàn bộ.

Kiểm tra:

```sql
SELECT
    count(*) AS current_connections,
    current_setting('max_connections')::integer AS max_connections,
    count(*) FILTER (WHERE state = 'active') AS active_connections,
    count(*) FILTER (WHERE state = 'idle') AS idle_connections,
    count(*) FILTER (
        WHERE state = 'idle in transaction'
    ) AS idle_in_transaction
FROM pg_catalog.pg_stat_activity;
```

### Threshold gợi ý

- Warning khi utilization vượt khoảng 70–80% usable budget trong vài phút.
- Critical khi vượt khoảng 90% usable budget hoặc xuất hiện connection failures.
- Alert riêng cho idle in transaction kéo dài và số lượng tăng bất thường.

Đây chỉ là điểm khởi đầu. Tính usable budget sau reserved slots, monitoring, replication, pooler và admin reserve. Theo dõi connection acquisition timeout ở ứng dụng để phát hiện impact trực tiếp.

## 19. Threshold cho replication lag

Replication lag cần gắn với RPO và workload. Có thể đo:

- WAL byte distance giữa primary và standby.
- Receive lag: WAL chưa được nhận/flush.
- Replay lag: WAL đã nhận nhưng chưa apply.
- Timestamp của transaction replay gần nhất.
- WAL receiver status và last message receipt time.

Trên standby:

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_last_wal_receive_lsn(),
            pg_last_wal_replay_lsn()
        )::bigint
    ) AS receive_replay_distance,
    pg_last_xact_replay_timestamp() AS last_replay_time;
```

### Cảnh báo theo RPO

Nếu RPO tối đa 60 giây, warning có thể ở 20–30 giây sustained, critical ở 45–50 giây hoặc theo thời gian còn lại để xử lý. Tính delay đo lường và notification vào ngưỡng; không đợi chạm RPO rồi mới page.

### Idle primary caveat

pg_last_xact_replay_timestamp có thể cũ khi primary không có transaction mới. Kết hợp LSN positions, WAL receiver timestamps và workload activity để tránh báo lag giả khi hệ thống idle.

## 20. Threshold cho disk và filesystem

Disk alerts nên dùng cả utilization, free bytes, growth rate và time-to-full.

Ví dụ:

| Severity | Điều kiện tham khảo |
|---|---|
| Warning | Used > 80% sustained 10 phút hoặc free space dưới capacity buffer |
| Critical | Used > 90–95%, hoặc dự báo đầy trước thời gian phản ứng |
| Immediate page | Filesystem read-only, write failures hoặc PostgreSQL không thể ghi WAL |

Ngưỡng phụ thuộc kích thước volume, tốc độ tăng dữ liệu và thời gian cần để mở rộng/cleanup.

### PostgreSQL directories

Theo dõi riêng:

- PGDATA.
- pg_wal.
- Tablespaces.
- WAL archive staging/cache.
- Backup destination.
- Filesystem chứa logs/temp files.

Một filesystem có thể đầy dù tổng disk utilization của host còn thấp. Gắn alert theo mountpoint và service role.

## 21. Threshold cho replication slots và WAL retention

Replication slots có thể giữ WAL khi consumer chậm hoặc inactive. Một slot inactive lâu có thể làm pg_wal tăng tới khi disk đầy.

Trên primary:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_catalog.pg_replication_slots;
```

Một số cột như wal_status và safe_wal_size chỉ có ở các phiên bản PostgreSQL mới hơn; điều chỉnh query theo version.

### Alert design

- Alert slot inactive quá lâu nếu slot được kỳ vọng có consumer.
- Alert retained WAL distance tăng nhanh.
- Alert safe_wal_size thấp khi server hỗ trợ cột này.
- Alert disk free/time-to-full trên filesystem chứa pg_wal.

Không alert chỉ vì slot inactive một vài giây nếu đây là trạng thái bình thường trong workflow. Gắn slot với owner, expected activity và retention policy.

## 22. Threshold cho locks và blocking

Một lock wait ngắn có thể bình thường. Một blocker kéo dài, chặn nhiều transactions và làm request latency tăng là tín hiệu quan trọng.

Query tìm sessions đang chờ lock:

```sql
SELECT
    pid,
    usename,
    application_name,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 200) AS query_text
FROM pg_catalog.pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
```

### Threshold gợi ý

- Warning khi lock wait duration vượt workload SLO trong vài phút.
- Critical khi một blocker giữ nhiều sessions hoặc làm transaction queue tăng.
- Alert riêng cho long-running transaction và idle-in-transaction.

Không page cho mọi lock wait. Cần xét số waiter, tuổi blocker, query impact và loại lock.

## 23. Threshold cho query latency và errors

Query latency nên được đo ở application hoặc database instrumentation có đủ context. Dùng p95/p99 theo endpoint/workload class thay vì một average toàn cluster.

Alert có thể kết hợp:

- p95/p99 latency vượt SLO.
- Error rate vượt budget.
- Throughput giảm trong khi request volume vẫn ổn định.
- Pool acquisition time tăng.
- DB CPU/locks/IO pressure đồng thời tăng.

### Query-level metrics

pg_stat_statements giúp phân tích tổng thời gian, calls, rows và block I/O theo normalized query. Stats có thể reset khi restart/reset; hãy xử lý delta/rate đúng cách và tránh alert trên cumulative totals.

## 24. Threshold cho autovacuum và bloat signals

Không có một metric đơn giản đo chính xác mọi dạng bloat. Theo dõi:

- Dead tuples estimate.
- Tuổi transaction/XID age.
- Autovacuum activity và duration.
- Tables bị vacuum lâu không chạy.
- Long-running transactions giữ old snapshots.
- Table/index growth bất thường.
- Transaction ID wraparound risk.

Một bảng có dead tuple ratio cao trong thời gian ngắn sau bulk update có thể bình thường. Alert nên xét trend, XID age, autovacuum progress và impact lên disk/query latency.

### XID age

Transaction ID age gần giới hạn wraparound là rủi ro nghiêm trọng. Đây là hard safety boundary nên alert theo ngưỡng có headroom lớn, không chỉ dùng anomaly baseline.

## 25. Threshold cho backup và archive

Backup monitoring cần phát hiện:

- Backup job không bắt đầu đúng lịch.
- Backup thất bại hoặc kết thúc bất thường.
- Backup duration vượt backup window.
- WAL archive failure hoặc archive backlog tăng.
- Không có backup gần nhất trong retention policy.
- Restore verification/drill quá hạn.

### Missing success event

Không chỉ alert khi job báo failed. Nếu job không chạy hoặc monitoring không nhận được completion event, cần alert theo expected schedule/deadline.

### Backup freshness

Alert dựa trên thời điểm backup thành công gần nhất và WAL archive continuity. Một backup job “green” không đủ nếu WAL segments sau backup bị thiếu hoặc restore chain không hợp lệ.

## 26. Threshold cho CPU, memory và I/O

CPU:

- Utilization sustained cao.
- CPU steal/pressure nếu chạy virtualized.
- Run queue tăng.
- Query latency/throughput bị ảnh hưởng.

Memory:

- Available memory thấp.
- Swap activity tăng.
- OOM events.
- PostgreSQL memory pressure kết hợp connection count/workload.

Disk I/O:

- Latency/read-write await tăng.
- Queue depth tăng.
- Throughput đạt giới hạn volume.
- Checkpoint/WAL write pressure.

Không page chỉ vì CPU hoặc I/O chạm một tỷ lệ ngắn. Kết hợp saturation duration với user-facing symptom và workload context.

## 27. Threshold theo workload baseline

Workload có tính mùa vụ: traffic ban ngày khác ban đêm, cuối tuần khác ngày thường, batch windows khác giờ API peak.

Baseline có thể được phân nhóm theo:

- Time of day/day of week.
- Service/workload class.
- Primary/standby role.
- Region/environment.
- Deploy version.

### Tránh học nhầm sự cố

Nếu baseline được cập nhật liên tục trong lúc incident diễn ra, hệ thống có thể dần coi trạng thái xấu là bình thường. Freeze baseline trong incident hoặc loại bỏ periods bất thường khỏi training window.

### Dùng robust statistics

Median và percentile thường bền hơn mean khi metric có spikes. Dải median ± k×MAD có thể dùng làm anomaly signal, nhưng cần kiểm tra distribution và seasonality.

## 28. Hysteresis và recovery threshold

Hysteresis dùng hai ngưỡng khác nhau cho alert firing và recovery để tránh trạng thái bật/tắt liên tục quanh một threshold.

Ví dụ:

- Alert khi disk utilization > 85%.
- Resolve khi disk utilization < 80%.

Khoảng chênh lệch tạo vùng ổn định. Alert engine có thể hỗ trợ recovery threshold riêng hoặc cần biểu thức/state logic tương đương.

### Ví dụ state machine

```text
NORMAL
  | metric > 85% sustained
  v
FIRING
  | metric < 80% sustained
  v
NORMAL
```

### Vì sao hữu ích?

Metric dao động 84.9%, 85.1%, 84.8%, 85.2% không làm alert liên tục firing/resolved. Hysteresis giảm notification noise và giữ trạng thái alert ổn định.

## 29. Multi-condition alerts

Một condition đơn lẻ có thể gây false positive. Có thể yêu cầu nhiều tín hiệu cùng xuất hiện:

- CPU high và query latency high.
- Replication lag high và WAL receiver stale.
- Connection utilization high và pool acquisition timeout tăng.
- Disk usage high và free-space burn rate nguy hiểm.

### Không over-correlate

Nếu đòi tất cả signals cùng đúng, alert có thể bỏ lỡ incident khi một exporter bị lỗi hoặc metric khác không có. Dùng multi-condition cho symptom confidence; giữ các hard-limit alerts độc lập.

## 30. No data khác zero

Không có sample không đồng nghĩa metric bằng 0. Exporter down, scrape timeout, network partition hoặc target bị remove có thể làm metric biến mất.

Phân biệt:

- Zero: có sample và giá trị là 0.
- No data: không có sample trong cửa sổ.
- Stale: series không còn được cập nhật hoặc bị đánh dấu stale.
- Scrape failure: Prometheus không lấy được metrics từ target.

### Alert cho monitoring pipeline

Theo dõi up, scrape duration, scrape samples và target discovery. Nếu PostgreSQL exporter biến mất, alert “connections = 0” có thể gây hiểu nhầm; nên có alert riêng cho exporter/target unavailable.

### Missing-data policy

Mỗi alert cần quyết định no data có nghĩa là:

- Unknown/insufficient evidence.
- Target down và cần page.
- Metric không áp dụng cho role này.
- Monitoring pipeline lỗi.

Không tự chuyển no data thành healthy.

## 31. Scrape gaps và sample freshness

Scrape có thể thất bại trong một hoặc vài chu kỳ. Một query dùng range window đủ dài có thể vẫn trả kết quả dựa trên samples cũ. Điều này hữu ích để làm mượt, nhưng có thể che việc target đã ngừng cập nhật.

### Thiết kế

- Theo dõi scrape success độc lập với application metrics.
- Alert khi last sample age vượt giới hạn.
- Dùng range window phù hợp và kiểm tra sample count.
- Phân biệt target intentionally absent với unexpected absence.
- Không dùng or vector(0) một cách tùy tiện để che missing series.

## 32. Scrape timeout và exporter overload

Scrape timeout nên ngắn hơn scrape interval và phù hợp với thời gian exporter query metrics. Exporter truy vấn nhiều catalog/views hoặc pg_stat_statements trên cluster lớn có thể mất lâu.

Theo dõi:

- Scrape duration.
- Scrape timeout/failure count.
- Exporter CPU/memory.
- Số metrics/series.
- PostgreSQL load do monitoring queries.

Nếu scrape duration gần bằng interval liên tục, tăng interval, tối ưu exporter collectors hoặc giảm cardinality trước khi chỉ tăng timeout.

## 33. Cardinality và alert noise

Label cardinality cao làm tăng chi phí lưu trữ/query và có thể tạo hàng nghìn alert instances.

Tránh label theo:

- Raw SQL text hoặc query parameters.
- User ID/request ID.
- Dynamic table names không giới hạn.
- Session PID cho mọi alert kéo dài.
- Error message đầy đủ thay đổi liên tục.

Giữ labels ổn định như cluster, node, role, environment, service và severity. Đưa chi tiết query/session vào dashboard hoặc runbook khi cần điều tra.

## 34. Severity và actionability

Một mô hình đơn giản:

| Severity | Ý nghĩa | Hành động |
|---|---|---|
| Info | Thay đổi đáng chú ý, chưa cần can thiệp | Dashboard/log |
| Warning | Rủi ro đang tăng, cần xử lý trong giờ làm việc | Ticket/chat |
| Critical | User impact hoặc nguy cơ sắp xảy ra | Page on-call |
| Emergency | Dịch vụ mất hoặc data safety bị đe dọa tức thời | Incident response |

Severity phải dựa trên impact và response time, không dựa trên tên metric. Ví dụ disk 80% có thể warning; filesystem read-only trên primary có thể emergency.

### Alert cần có runbook

Mỗi page alert nên chứa:

- Điều kiện đã kích hoạt.
- Cluster/node/role.
- Thời điểm bắt đầu và duration.
- Dashboard liên quan.
- Query/command chẩn đoán.
- Hành động an toàn ban đầu.
- Escalation owner.

## 35. Alert grouping và deduplication

Một incident có thể tạo nhiều alert instances: mỗi database, node hoặc replica đều có thể phát cùng một symptom. Grouping giúp gộp notification theo cluster/service/alertname.

### Group theo labels ổn định

Ví dụ group theo:

- alertname.
- cluster.
- environment.
- service.

Không group quá rộng đến mức gộp hai incidents độc lập, cũng không group quá hẹp khiến mỗi node gửi một page riêng.

### Deduplication

Notification system nên nhận diện cùng alert fingerprint để tránh gửi lặp. Repeat notifications có thể nhắc lại khi alert chưa resolve nhưng cần khoảng thời gian hợp lý và không gây spam.

## 36. Inhibition và dependency suppression

Nếu cả PostgreSQL node và exporter cùng down, alert exporter scrape failure có thể chỉ là hệ quả của node down. Inhibition có thể suppress alert phụ khi alert cấp cao hơn đang firing.

Ví dụ:

- Cluster unavailable suppress per-database query latency alerts.
- Node down suppress node CPU/disk metrics alerts nếu không còn sample.
- Primary failover in progress suppress expected transient connection churn warnings.

### Không suppress quá rộng

Inhibition sai có thể che incident độc lập. Chỉ suppress khi alert nguồn thực sự giải thích alert đích và có scope labels khớp.

## 37. Maintenance windows và silences

Maintenance silence ngăn notification trong một khoảng thời gian đã định, nhưng không làm metric/alert condition biến mất.

Silence nên có:

- Start/end time rõ.
- Scope labels chính xác.
- Owner.
- Ticket/change reference.
- Lý do.

### Không silence vô thời hạn

Silence không có expiry có thể che sự cố thật sau maintenance. Tự động hết hạn và rà soát silences đang hoạt động.

### Maintenance không phải cách sửa false positive

Nếu alert luôn false-positive ngoài maintenance, sửa threshold/window/condition. Không tạo silence định kỳ để che alert noise.

## 38. Prometheus alert rule: CPU và connections

Ví dụ minh họa:

```yaml
groups:
  - name: postgres-saturation
    interval: 30s
    rules:
      - alert: PostgresConnectionsHigh
        expr: |
          postgres_connections_used
          / postgres_connections_usable > 0.80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: PostgreSQL connection budget is high
          description: |
            Connection usage has exceeded 80% for five minutes.
            Check pool queues, idle transactions and connection leaks.

      - alert: PostgresConnectionsCritical
        expr: |
          postgres_connections_used
          / postgres_connections_usable > 0.92
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: PostgreSQL is close to connection exhaustion
          description: |
            Check connection acquisition failures and preserve admin headroom.
```

Tên metric ở ví dụ là metric đã được exporter/recording rule chuẩn hóa; thay bằng tên metric thực tế. Không chia cho zero hoặc coi missing denominator là 0; tạo rule kiểm tra metric availability riêng.

## 39. Prometheus alert rule: replication lag

Ví dụ dùng một metric đã biểu diễn lag seconds:

```yaml
groups:
  - name: postgres-replication
    interval: 15s
    rules:
      - alert: PostgresReplicaLagWarning
        expr: postgres_replication_lag_seconds > 20
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: PostgreSQL replica lag is increasing
          description: |
            Replica lag has remained above 20 seconds.
            Check WAL receiver, network and replay capacity.

      - alert: PostgresReplicaLagCritical
        expr: postgres_replication_lag_seconds > 45
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: PostgreSQL replica is near the RPO limit
          description: |
            Check primary WAL generation, standby replay and slot retention.
```

Các giá trị 20/45 giây chỉ là ví dụ cho một hệ thống có RPO khoảng 60 giây. Chọn lại theo RPO, scrape/evaluation delay, notification latency và response time.

## 40. Prometheus alert rule: scrape health và no data

Ví dụ:

```yaml
groups:
  - name: postgres-monitoring
    rules:
      - alert: PostgresExporterDown
        expr: up{job="postgres-exporter"} == 0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: PostgreSQL exporter is unavailable

      - alert: PostgresExporterTargetMissing
        expr: absent(up{job="postgres-exporter"})
        for: 3m
        labels:
          severity: critical
        annotations:
          summary: PostgreSQL exporter target is missing
```

absent semantics phụ thuộc label selector và target discovery. Nếu có nhiều clusters/targets, cần tạo series/recording rules theo từng cluster để alert không gộp sai. Alert target missing có thể do service discovery config; nó khác với exporter trả up=0.

## 41. Prometheus: rate và multi-window

Ví dụ counter error rate:

```promql
sum(rate(api_requests_total{status=~"5.."}[5m]))
/
sum(rate(api_requests_total[5m]))
```

Biểu thức trên đo tỷ lệ request 5xx trong 5 phút. Cần xử lý trường hợp denominator bằng zero và labels phù hợp với service.

### Multi-window condition

Có thể yêu cầu error ratio vượt ngưỡng trong cả window ngắn và dài:

```promql
(
  sum(rate(api_requests_total{status=~"5.."}[5m]))
  /
  sum(rate(api_requests_total[5m]))
) > 0.05
and
(
  sum(rate(api_requests_total{status=~"5.."}[1h]))
  /
  sum(rate(api_requests_total[1h]))
) > 0.02
```

Window ngắn phát hiện incident đang diễn ra; window dài xác nhận impact kéo dài. Với production, cần thêm denominator guards, service labels và các rule cho traffic thấp.

## 42. SLO burn-rate alerts

Error budget là lượng lỗi được phép trong SLO window. Burn rate đo tốc độ tiêu thụ error budget so với tốc độ cho phép.

Ví dụ SLO availability 99.9% trong 30 ngày có error budget 0.1%. Nếu error ratio cao gấp nhiều lần budget rate, budget có thể cạn sớm.

### Tại sao dùng burn rate?

- Liên hệ trực tiếp alert với user-facing reliability.
- Phát hiện sự cố có impact lớn dù raw error rate có vẻ nhỏ.
- Cho phép multi-window alert để cân bằng tốc độ và độ tin cậy.
- Hạn chế alert trên metric hạ tầng không gây impact.

### Multi-burn-rate

Một pattern phổ biến là kết hợp short window và long window, với burn-rate thresholds khác nhau cho fast-burn và slow-burn incidents. Chọn cửa sổ và threshold theo SLO window, page budget và response model; không sao chép một cấu hình chung cho mọi dịch vụ.

## 43. Notification timing trong Alertmanager

Alertmanager grouping/routing có các timing như:

- group_wait: chờ alert group ban đầu trước notification đầu tiên.
- group_interval: chờ trước khi gửi updates cho group đã có.
- repeat_interval: khoảng cách nhắc lại alert chưa resolve.

Các timing này cộng vào trải nghiệm phát hiện/notification, nhưng không thay pending duration trong rule evaluation.

Ví dụ:

```yaml
route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
```

Chọn timing theo incident urgency. Page critical có thể cần group_wait ngắn; warning/ticket có thể gom lâu hơn.

## 44. Tách alert evaluation delay khỏi response delay

Thời gian từ lúc metric bắt đầu xấu tới lúc người trực nhận page có thể gồm:

1. Chờ sample tiếp theo.
2. Chờ evaluation cycle.
3. Pending duration.
4. Alertmanager group_wait/routing.
5. Notification provider delivery.

Ước lượng:

\[
\text{detection-to-page} \approx
\text{scrape delay} +
\text{evaluation delay} +
\text{pending duration} +
\text{notification delay}
\]

Đây là ước lượng; các thành phần có thể overlap hoặc lệch pha. Đo thực tế bằng synthetic alert/test event để biết end-to-end latency.

### RPO headroom

Nếu RPO là 60 giây, một rule pending 60 giây cộng thêm scrape/evaluation/notification sẽ báo sau khi đã vượt mục tiêu. Alert threshold/pending phải để đủ headroom cho detection và remediation.

## 45. Giảm false positives bằng sustained conditions

Một spike đơn lẻ có thể không cần page. Dùng:

- for duration.
- Moving average/rate.
- Minimum sample count.
- Percentile theo window.
- Multiple conditions.

Ví dụ, cảnh báo CPU utilization trên 90% liên tục 10 phút có thể đáng tin hơn một sample 95%. Tuy nhiên, nếu service down hoặc filesystem read-only thì không chờ 10 phút.

### Chọn duration theo failure mode

- Outage: phát hiện nhanh, duration ngắn hoặc không pending.
- Connection saturation: vài phút để loại burst ngắn.
- Disk exhaustion: dựa time-to-full, không chỉ sustained percentage.
- Backup missed: chờ tới deadline lịch backup.
- Capacity trend: window dài hơn.

## 46. Giảm false positives bằng hysteresis

Nếu alert threshold và recovery threshold giống nhau, metric dao động quanh boundary có thể gây flapping. Tách ngưỡng firing/recovery hoặc dùng recovery duration riêng nếu hệ thống hỗ trợ.

Ví dụ:

- Firing khi lag > 30 giây trong 2 phút.
- Resolve khi lag < 15 giây trong 3 phút.

Điều này tránh resolve rồi fire lại ngay khi lag dao động quanh 30 giây.

### Recovery cũng cần quan sát

Không resolve ngay khi metric có một sample tốt nếu incident vẫn chưa ổn định. Dùng recovery window, nhưng đừng giữ alert firing quá lâu sau khi impact đã hết.

## 47. Giảm false positives bằng context

Kết hợp metric liên quan:

- CPU high + latency high.
- Disk utilization high + free bytes low.
- Lag high + WAL receiver stale.
- Connections high + acquisition timeouts.
- Query errors high + request volume đáng kể.

### Traffic thấp

Error ratio có thể rất cao khi chỉ có một request lỗi. Dùng minimum request volume hoặc error count condition cùng ratio. Nếu traffic thấp nhưng service critical, synthetic probes có thể phù hợp hơn.

## 48. Giảm false positives bằng maintenance và deployment context

Deployment, backup, index build, vacuum, failover và planned maintenance có thể tạo metric spikes.

Biện pháp:

- Gắn deployment/change events vào dashboard.
- Silence theo labels và thời gian có expiry.
- Inhibit symptom alerts khi incident cấp cao đã xác định nguyên nhân.
- Có alert riêng cho maintenance vượt quá expected duration.
- Không suppress hard safety alerts như disk full hoặc XID wraparound risk.

### Silence phải hẹp

Silence đúng cluster/node/alertname và có end time. Tránh silence toàn bộ PostgreSQL alerts vì một maintenance window.

## 49. Giảm false positives bằng baseline theo mùa vụ

Nếu batch job chạy mỗi đêm và tạo WAL/CPU spike bình thường, một static threshold có thể page mỗi ngày. Có thể:

- Định nghĩa maintenance/batch window rõ.
- So sánh với baseline cùng khung giờ.
- Tạo workload-specific alert.
- Alert khi duration/volume vượt expected range.

Không suppress toàn bộ batch window; vẫn cần phát hiện batch kéo dài bất thường hoặc làm user-facing SLO suy giảm.

## 50. False negative và threshold quá lỏng

Giảm false positives không được làm alert mất khả năng phát hiện. Threshold quá cao, pending quá dài hoặc suppression quá rộng có thể tạo false negatives.

Kiểm tra:

- Incident history: alert có fire trước impact không?
- Synthetic failure: alert có phát khi cố tình tạo sự cố không?
- Threshold margin: có đủ thời gian trước hard limit không?
- No-data behavior: exporter mất có bị coi là healthy không?
- Maintenance suppression: alert quan trọng có bị che không?

Mỗi alert cần được test cả condition firing và recovery.

## 51. Alert flapping

Flapping là trạng thái alert liên tục chuyển firing/resolved trong thời gian ngắn.

Nguyên nhân:

- Threshold sát baseline.
- Scrape gaps/noisy samples.
- Evaluation quá nhanh so với metric behavior.
- Thiếu hysteresis.
- Alert expression phụ thuộc series cardinality thay đổi.
- Node role thay đổi khi failover.

Giảm flapping bằng sustained duration, recovery threshold, robust aggregation, stable labels và role-aware rules.

## 52. Alert fatigue và notification policy

Alert fatigue xảy ra khi người trực nhận quá nhiều notifications ít actionable. Hệ quả là critical alerts bị bỏ qua hoặc phản ứng chậm.

Giảm fatigue:

- Page chỉ khi cần phản ứng ngoài giờ.
- Warning tạo ticket/chat thay vì page.
- Group nhiều alerts cùng incident.
- Deduplicate theo fingerprint.
- Inhibit alerts phụ.
- Xóa/điều chỉnh alerts không có owner/runbook.
- Review false-positive/false-negative sau incidents.

Không giải quyết fatigue bằng cách mute mọi alert hoặc tăng threshold đồng loạt.

## 53. Alert quality metrics

Theo dõi chất lượng alert như một phần của observability:

- False-positive rate: tỷ lệ alerts không cần hành động.
- False-negative count: incidents không có alert phù hợp.
- Precision: tỷ lệ alert thực sự chỉ ra vấn đề.
- Time to detect (TTD).
- Time to acknowledge (TTA).
- Time to mitigate/resolve.
- Pages per on-call shift.
- Repeated/flapping alert count.
- Alerts without runbook/owner.

Định nghĩa false positive cần thống nhất: alert không có impact, không cần action hay chỉ là alert được resolve tự động? Ghi lại disposition sau mỗi incident/review.

## 54. Review và tuning threshold

Threshold không phải cấu hình đặt một lần rồi quên. Review sau:

- Workload growth hoặc traffic pattern change.
- Thay đổi max_connections/storage/replica topology.
- Migration hoặc deploy exporter.
- Failover/restore drills.
- Incident thật hoặc false alarm lặp lại.
- SLO/RPO/RTO thay đổi.

### Quy trình tuning

1. Thu thập alert history và metric timeline.
2. Xác định nguyên nhân alert fire.
3. Đối chiếu user impact và thời gian phản ứng.
4. Điều chỉnh threshold/window/for/hysteresis.
5. Replay dữ liệu lịch sử nếu hệ thống hỗ trợ.
6. Test synthetic condition.
7. Deploy rule versioned và theo dõi.
8. Ghi lại owner/rationale.

Không thay nhiều threshold cùng lúc nếu không thể xác định thay đổi nào cải thiện kết quả.

## 55. PostgreSQL exporter và monitoring load

Exporter có thể truy vấn catalog/views để thu metrics. Một collector đắt tiền chạy quá thường xuyên có thể tạo thêm tải trên database đang quá tải.

Theo dõi:

- Exporter query duration.
- Scrape duration và timeouts.
- Số metrics/series.
- PostgreSQL CPU do monitoring queries.
- Locks/waits từ monitoring role.

### Least privilege

Dùng monitoring role với quyền cần thiết, không dùng superuser cho exporter nếu không cần. Một số metrics cần predefined monitoring roles hoặc quyền cụ thể; cấu hình theo tài liệu exporter/PostgreSQL version.

## 56. Prometheus recording rules

Recording rules lưu kết quả biểu thức thường dùng để dashboard/alert không phải tính lại trên nhiều series mỗi lần.

Ví dụ:

```yaml
groups:
  - name: postgres-recording
    interval: 30s
    rules:
      - record: postgres:connection_utilization:ratio
        expr: |
          postgres_connections_used
          / postgres_connections_usable

      - record: postgres:replica_lag:max_seconds
        expr: max by (cluster) (postgres_replication_lag_seconds)
```

Recording rule phải giữ labels đúng và xử lý missing/zero denominator. Đừng aggregate bỏ mất node/role cần cho diagnosis.

## 57. Kiểm thử alert rules

Alert cần được test bằng dữ liệu hoặc tình huống có kiểm soát:

- Unit test PromQL/rule expression.
- Replay time series lịch sử.
- Synthetic metric vượt threshold.
- Tạo exporter outage có chủ đích ở staging.
- Tạo replication lag trong lab.
- Giả lập disk pressure an toàn.
- Kiểm tra firing, notification routing và resolution.

### Không test phá hoại trên production

Không cố làm đầy filesystem, kill primary hoặc xóa WAL production chỉ để xác minh alert. Dùng staging, fault injection có giới hạn hoặc synthetic series.

## 58. Alert rule lifecycle

Một alert nên có:

- Tên ổn định, dễ tìm.
- Mô tả symptom và impact.
- Labels cho severity/cluster/role/service.
- Annotation có runbook/dashboard.
- Owner.
- Threshold rationale.
- Test case.
- Review date hoặc change history.

Khi xóa alert, xác nhận nó không còn được route hoặc được thay bằng alert khác. Không để rule cũ vẫn fire nhưng notification bị mất trong im lặng.

## 59. Runbook: điều tra false positive

1. Ghi lại alert fingerprint, labels, start/end time.
2. Xem raw metric samples quanh thời điểm fire.
3. Kiểm tra scrape gaps, exporter logs và staleness.
4. So sánh với workload/deployment/maintenance events.
5. Xác định threshold, window và pending duration.
6. Kiểm tra có user impact hoặc action thực tế không.
7. Xác định nguyên nhân noise: spike, seasonality, missing data, cardinality hay threshold.
8. Thử điều chỉnh trong staging/replay.
9. Test cả firing và recovery.
10. Cập nhật owner, runbook và rationale.

## 60. Runbook: alert không fire khi có incident

1. Xác định symptom/impact và thời điểm bắt đầu.
2. Kiểm tra metric có được scrape không.
3. Kiểm tra target labels/series identity.
4. Chạy biểu thức alert trực tiếp tại thời điểm incident.
5. Kiểm tra range window và sample count.
6. Kiểm tra pending duration, evaluation interval và rule group errors.
7. Kiểm tra no-data/stale behavior.
8. Kiểm tra inhibition/silence/routing.
9. Replay incident timeline nếu có dữ liệu.
10. Sửa rule và tạo synthetic test chứng minh alert fire.

## 61. Runbook: replication lag alert

1. Xác định cluster, primary và standby bị ảnh hưởng.
2. Kiểm tra pg_stat_wal_receiver/status và last message time.
3. So sánh receive LSN và replay LSN.
4. Kiểm tra WAL sender/pg_stat_replication trên primary.
5. Kiểm tra network, CPU, I/O và long-running standby queries.
6. Kiểm tra replication slot retained WAL và disk free.
7. Đối chiếu lag với RPO và alert threshold.
8. Nếu vượt RPO, thực hiện incident escalation.
9. Xác nhận lag giảm và alert resolve theo recovery threshold.
10. Ghi nhận liệu sampling/pending delay có làm phát hiện muộn không.

## 62. Runbook: disk capacity alert

1. Xác định filesystem/mountpoint và PostgreSQL directory.
2. Kiểm tra free bytes, utilization và growth rate.
3. Kiểm tra pg_wal/replication slots.
4. Kiểm tra archive backlog và failed archive jobs.
5. Kiểm tra tablespace/data growth và temp files.
6. Ước lượng time-to-full.
7. Chọn cleanup/expand action theo runbook đã phê duyệt.
8. Không xóa WAL hoặc database files thủ công.
9. Theo dõi free space và PostgreSQL write health.
10. Điều chỉnh threshold nếu warning không đủ headroom.

## 63. Runbook: alert flapping

1. Xem lịch sử state transitions và raw samples.
2. Xác định threshold boundary có quá sát baseline không.
3. Kiểm tra scrape/evaluation interval.
4. Xác định series/labels có biến mất và xuất hiện lại không.
5. Thêm hysteresis hoặc recovery duration phù hợp.
6. Chọn aggregation/window bền hơn.
7. Giữ hard-failure alerts phản ứng nhanh.
8. Test firing/resolution qua replay.
9. Theo dõi notification volume sau thay đổi.
10. Ghi lại trade-off về detection delay.

## 64. Runbook: no data hoặc exporter down

1. Xác định target có expected tồn tại ở thời điểm đó không.
2. Kiểm tra Prometheus target discovery và scrape status.
3. Kiểm tra network, DNS, TLS và exporter process.
4. Kiểm tra exporter connection tới PostgreSQL.
5. Xem exporter query duration/permissions.
6. Phân biệt database down với exporter down.
7. Khôi phục metrics collection.
8. Kiểm tra các alert phụ không bị suppress sai.
9. Xác nhận sample freshness trở lại bình thường.
10. Đánh giá khoảng mù monitoring trong incident.

## 65. Checklist thiết kế alert

### Ý nghĩa

- Alert gắn với impact/SLO/RPO/capacity.
- Có owner và người nhận.
- Có hành động cụ thể/runbook.
- Severity phản ánh response time.

### Ngưỡng và thời gian

- Static/dynamic threshold được chọn có lý do.
- Sampling interval đủ nhanh nhưng không gây tải.
- Evaluation interval phù hợp detection objective.
- Range window phù hợp metric behavior.
- Pending duration có headroom.
- Hysteresis/recovery condition giảm flapping.

### Dữ liệu

- Counter dùng rate/increase đúng cách.
- No data khác zero.
- Scrape failures/staleness được giám sát.
- Counter resets và missing labels được xử lý.
- Cardinality được giới hạn.

### Notification

- Grouping/deduplication hợp lý.
- Inhibition không che alert độc lập.
- Silences có expiry/owner.
- Critical alerts không bị delay quá mức.

### Vận hành

- Firing và recovery đã được test.
- Alert history được review.
- False-positive/negative được ghi nhận.
- Threshold được cập nhật sau capacity/workload changes.

## 66. Bài tập thực hành

### Bài 1 — Metric và alert

Phân biệt metric, threshold, condition, alert và notification bằng ví dụ PostgreSQL connection usage.

### Bài 2 — Impact

CPU primary đạt 95% trong 20 giây nhưng latency bình thường. Vì sao chưa chắc cần page? Những tín hiệu nào làm alert đáng tin hơn?

### Bài 3 — Static threshold

Nêu ưu điểm và hạn chế của ngưỡng disk usage cố định 85%.

### Bài 4 — Dynamic baseline

Một batch job tạo WAL spike vào 02:00 mỗi ngày. Thiết kế baseline để phát hiện spike bất thường mà không page mỗi ngày.

### Bài 5 — Relative threshold

Query rate giảm 70% so với baseline nhưng traffic cũng giảm 80%. Vì sao cần thêm context trước khi page?

### Bài 6 — Absolute và ratio

Hai volume đều dùng 90%, một volume còn 2 GB và volume kia còn 1 TB. Thiết kế alert kết hợp percent, free bytes và growth rate.

### Bài 7 — Time-to-full

Filesystem còn 12 GB và đang tăng 600 MB mỗi 5 phút. Ước lượng time-to-full và đề xuất warning threshold có headroom.

### Bài 8 — Sampling interval

Chọn scrape interval cho availability, replication lag, backup status và capacity growth. Giải thích trade-off.

### Bài 9 — Evaluation interval

Prometheus scrape mỗi 15 giây nhưng evaluate mỗi 2 phút. Điều này ảnh hưởng detection delay thế nào?

### Bài 10 — Range window

So sánh rate của counter trên window 1 phút và 15 phút về responsiveness và noise.

### Bài 11 — Pending duration

Disk alert dùng pending 20 phút nhưng disk có thể đầy trong 10 phút. Vì sao cấu hình này không an toàn?

### Bài 12 — Counter reset

PostgreSQL restart làm stats counter reset. Vì sao cần rate/increase và không nên tự trừ hai samples?

### Bài 13 — Percentile

Average latency là 50 ms nhưng p99 là 2 giây. Vì sao alert average có thể bỏ sót user impact?

### Bài 14 — Role-aware thresholds

Thiết kế alert khác nhau cho connection saturation trên primary và standby.

### Bài 15 — Connections

Viết SQL tính current connections, active, idle, idle-in-transaction và utilization theo usable budget.

### Bài 16 — Replication lag

Một hệ thống có RPO 60 giây. Đề xuất warning/critical threshold, pending duration và notification headroom.

### Bài 17 — Idle primary

Vì sao pg_last_xact_replay_timestamp cũ không nhất thiết có nghĩa replica lag? Metrics nào cần kết hợp?

### Bài 18 — Replication slots

Thiết kế alert cho slot inactive, retained WAL tăng và safe_wal_size thấp.

### Bài 19 — Disk directories

Liệt kê filesystem PostgreSQL cần theo dõi riêng và giải thích vì sao tổng disk usage của host chưa đủ.

### Bài 20 — Locks

Viết query tìm sessions chờ lock, blocker PIDs và query age. Đề xuất điều kiện page.

### Bài 21 — Autovacuum

Thiết kế alert cho autovacuum chậm và XID age cao. Phân biệt noise với wraparound risk.

### Bài 22 — Backup freshness

Thiết kế alert khi backup không bắt đầu/không hoàn tất đúng lịch và khi WAL archive backlog tăng.

### Bài 23 — No data

Phân biệt metric zero, no data, stale sample và scrape failure. Viết policy cho exporter biến mất.

### Bài 24 — Scrape timeout

Exporter scrape mất 12 giây trong khi interval là 15 giây. Những metrics nào cần xem trước khi giảm interval?

### Bài 25 — Cardinality

Vì sao không nên gắn raw SQL hoặc request ID vào alert labels? Đề xuất labels ổn định.

### Bài 26 — Severity

Phân loại disk 80%, disk 95%, primary read-only, replica lag 20 giây với RPO 60 giây và exporter down.

### Bài 27 — Hysteresis

Thiết kế firing threshold 85% và recovery threshold 80%. Giải thích cách nó giảm flapping.

### Bài 28 — Multi-condition

Tạo alert khi connection utilization cao và pool acquisition timeout tăng. Nêu rủi ro nếu đòi cả hai signals.

### Bài 29 — Error ratio

Một service có một request lỗi trên tổng hai requests. Vì sao error ratio 50% chưa đủ để page? Thiết kế minimum-volume guard.

### Bài 30 — Maintenance silence

Tạo policy silence cho maintenance 30 phút với owner, scope và expiry. Những alerts nào không nên suppress?

### Bài 31 — Grouping

Một cluster có 10 replicas cùng báo lag. Thiết kế Alertmanager group_by để giảm notification noise nhưng vẫn giữ thông tin node.

### Bài 32 — Inhibition

Khi cluster down, exporter-down và query-latency alerts cùng fire. Thiết kế inhibition mà không che incident độc lập.

### Bài 33 — Prometheus rule

Viết alert rule connections > 80% trong 5 phút và critical > 92% trong 2 phút.

### Bài 34 — Multi-window SLO

Thiết kế error-rate alert dùng cửa sổ 5 phút và 1 giờ. Vì sao hai cửa sổ bổ sung cho nhau?

### Bài 35 — Detection-to-page

Scrape 15 giây, evaluate 30 giây, pending 3 phút và group_wait 30 giây. Ước lượng các thành phần delay và giải thích lệch pha.

### Bài 36 — False positive review

Một alert CPU fire mỗi tối trong batch window nhưng không có user impact. Mô tả quy trình điều tra và tuning.

### Bài 37 — False negative

Disk đầy nhưng alert không fire vì exporter mất metrics. Thiết kế no-data/monitoring-pipeline alerts.

### Bài 38 — Alert flapping

Replication lag dao động quanh 30 giây khiến alert fire/resolve liên tục. Thiết kế pending và recovery hysteresis.

### Bài 39 — Alert quality

Đề xuất dashboard đo false-positive rate, TTD, pages per shift, flapping và alerts không có runbook.

### Bài 40 — Thiết kế hệ thống alert PostgreSQL end-to-end

Một hệ thống có:

- Một primary và hai physical standbys.
- RPO DR là 60 giây.
- API availability SLO là 99.9% trong 30 ngày.
- Primary có max_connections 300.
- Disk chứa PGDATA/pg_wal còn 500 GB.
- WAL generation thay đổi mạnh theo giờ.
- Backup chạy mỗi đêm, archive WAL liên tục.
- Exporter scrape có thể mất vài chu kỳ khi database bận.
- Reporting workload có thể gây lag trên một standby.

Hãy thiết kế:

1. Metric inventory và labels cho cluster/node/role/workload.
2. Scrape/evaluation intervals theo metric class.
3. Warning/critical thresholds cho connections, disk, WAL slots và replication lag.
4. Range windows, pending duration và hysteresis.
5. No-data/staleness/exporter alerts.
6. SLO burn-rate alert cho API.
7. Grouping, inhibition, severity và maintenance silences.
8. Runbooks cho lag, disk, backup và pool saturation.
9. Synthetic tests/replay để kiểm tra firing và recovery.
10. Quy trình review false positives/false negatives và điều chỉnh sau capacity growth.

## Kết luận

**Một alert tốt phản ánh rủi ro hoặc user impact, có ngưỡng và thời gian phản ứng được giải thích, đồng thời dẫn người nhận tới hành động cụ thể.** Static thresholds phù hợp với hard limits; dynamic baselines hữu ích với workload có mùa vụ nhưng không thay thế safety limits. Sampling, evaluation, range window, pending duration và notification timing là các thành phần khác nhau, cần được tính cùng nhau để detection không quá chậm hoặc quá nhạy.

Với PostgreSQL, cần thiết kế alert riêng cho primary/standby và các failure modes như connection exhaustion, replication lag, WAL slot retention, disk pressure, locks, autovacuum, backup và exporter availability. Counter cần được chuyển thành rate/increase; gauge cần được đánh giá theo threshold/trend; no data phải được phân biệt với zero. Hysteresis, sustained conditions, multi-signal context, grouping, inhibition và silences có scope/expiry giúp giảm notification noise.

Cuối cùng, tuning alert là một quá trình liên tục. Đo false positives, false negatives, time to detect và page volume; replay incident history; kiểm thử firing lẫn recovery; và cập nhật threshold sau khi workload/capacity/SLO thay đổi. **Mục tiêu là phát hiện đủ sớm để bảo vệ dịch vụ mà không khiến người trực mất niềm tin vào cảnh báo.**
