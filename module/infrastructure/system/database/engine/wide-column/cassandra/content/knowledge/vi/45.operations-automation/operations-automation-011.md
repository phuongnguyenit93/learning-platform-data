# Cảnh báo, sổ tay ứng phó và lưu nhật ký thao tác quản trị

> **Chương:** Tự động hóa vận hành  
> **Phạm vi module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra phân tán và mô hình wide-column; partition key, thiết kế bảng theo truy vấn, replication, consistency đọc/ghi, compaction, repair, bảo trì và ứng dụng Java.

Giả sử lúc 10:42 UTC, Java API ghi sự kiện bắt đầu tăng `WriteTimeoutException`. Dashboard Cassandra báo `PendingCompactions` cao, một node gần đầy disk, còn lịch sử terminal chỉ cho biết ai đó chạy `nodetool` trước đó vài phút. Đội trực ca có ba câu hỏi không thể trả lời ngay:

1. Cảnh báo nào thực sự cho thấy **người dùng bị ảnh hưởng** và cần đánh thức người trực, thay vì chỉ xuất hiện một metric xấu?
2. Sổ tay ứng phó nào giúp chọn **phép kiểm tra an toàn**, xác định phạm vi lỗi rồi xin phê duyệt khi cần thay đổi trạng thái cluster?
3. Ai đã làm gì, trên node nào, với tham số gì, vì lý do nào và kết quả ra sao — kể cả khi thao tác qua SSH, JMX, `nodetool`, CQL hoặc automation?

Một hệ Cassandra vận hành được không chỉ cần dashboard. Nó cần vòng kín **tín hiệu → cảnh báo có ngữ cảnh → runbook → hành động được kiểm soát → bằng chứng → xác minh phục hồi → cải tiến**. Bài này thiết kế vòng kín ấy bằng các cơ chế có thể thực hành trong cluster lab, nhấn mạnh sự khác nhau giữa **Cassandra audit logging**, **nhật ký hoạt động quản trị cấp hệ điều hành/automation** và **application request tracing**.

**Phạm vi ví dụ:** Cassandra 4.1 và 5.0, Java Driver 4.x, JMX/metrics exporter, Prometheus/Alertmanager kiểu minh họa, CLI `nodetool`, `cqlsh` và hệ thống ghi nhật ký có kiểm soát. Metric names ở Prometheus tùy exporter; bất kỳ tên chuẩn hóa nào được tự đặt trong bài đều phải gắn mapping trước khi dùng. Không khẳng định đã triển khai hoặc kiểm thử trên cluster thực tế.

> **Rào chắn an toàn:** Không chạy `repair`, `cleanup`, `rebuild`, `decommission`, `drain`, `truncatehints`, `clearsnapshot`, thay RF/CL, dừng node hoặc tắt TLS trên production để “làm theo bài”. Lệnh chỉ đọc cũng có thể tạo tải/JMX overhead nên phải có giới hạn. Mọi tình huống và số đo trong bài là **dữ liệu giả lập**, chỉ chạy thí nghiệm trên cluster học tập cách ly.

## 1. Mục tiêu và nguyên tắc thiết kế

Sau bài học, người học có thể:

1. Xây dựng danh mục cảnh báo từ **SLI/SLO và rủi ro dữ liệu**, thay vì chỉ đặt ngưỡng CPU.
2. Phân biệt metrics Cassandra theo node/coordinator/table/DC với metrics Java Driver và HTTP/gateway.
3. Đề xuất threshold/điều kiện tồn tại, phụ thuộc RF/CL, xử lý thiếu telemetry và alert fatigue.
4. Viết alert có `owner`, `severity`, `runbook_url`, phạm vi ảnh hưởng và cơ chế xác minh.
5. Thiết kế một runbook Cassandra theo các pha **quan sát → giả thuyết → kiểm tra → phê duyệt → can thiệp → xác minh → bàn giao**.
6. Nhận diện thao tác chỉ đọc, thao tác thay đổi trạng thái và thao tác phá hủy/khó hoàn tác của `nodetool`/CQL.
7. Bật, lọc và kiểm tra **audit logging CQL** trong Cassandra 4.x/5.x, hiểu điểm mạnh và giới hạn.
8. Giải thích tại sao audit log Cassandra **không tự ghi** `nodetool`, chỉnh `cassandra.yaml`, SSH, Kubernetes/cloud changes.
9. Đề xuất audit wrapper/automation ledger với actor, approval, command fingerprint, before/after, exit code và evidence links.
10. Giữ log đủ toàn vẹn, retention và bảo mật, tránh lộ passwords, query literal, PII và private keys.
11. Thiết kế phê duyệt hai người, quyền tối thiểu, idempotency và kill switch cho remediation có điều kiện.
12. Thực hành một ca tabletop và phân biệt mitigation tức thời với xác minh consistency/data integrity.

**Definition of Done cho một cảnh báo:** cảnh báo có người nhận, ngữ cảnh/scope, hành động kiểm tra ban đầu, điều kiện escalations, và kiểm thử notification/clear. **Definition of Done cho một hành động quản trị:** có người và lý do, thẩm quyền, chính xác node/command, timestamp UTC, kết quả, before/after state và bản ghi audit không dễ sửa. Không dùng “lệnh chạy exit 0” đồng nghĩa “sự cố đã giải quyết”.

## 2. Ba lớp tín hiệu cần kết nối

### 2.1. Người dùng, driver và Cassandra không đo cùng một thứ

~~~mermaid
flowchart LR
    U["User / API SLI"] --> A["Service + gateway metrics"]
    A --> D["Java Driver metrics and exception types"]
    D --> C["Coordinator CQL metrics"]
    C --> R["Replicas / storage / compaction"]
    R --> H["Host / disk / network / JVM"]
    X["Change + audit ledger"] --> A
    X --> C
    X --> H
    A --> I["Incident timeline and evidence"]
    D --> I
    C --> I
    H --> I
    X --> I
~~~

| Lớp | Tín hiệu | Bẫy khi suy luận |
|---|---|---|
| API/gateway | Success rate, p95/p99, requests/s, business transactions | 504 có thể xảy ra trước khi gửi CQL |
| Java Driver | `DriverTimeoutException`, `ReadTimeoutException`, `WriteTimeoutException`, pool in-flight, throttling | Driver timeout khác coordinator timeout; failed write có outcome không chắc chắn |
| Coordinator | `ClientRequest.Read/Write.Timeouts`, `Unavailables`, `Latency` | Coordinator nhận error không chứng minh replica nào là nguyên nhân |
| Replica/table | `SSTablesPerReadHistogram`, `TombstoneScannedHistogram`, disk/compaction | Chậm ở một table/partition có thể không làm mọi API chậm |
| Host/JVM | disk free, IO await, GC pause, NIC packet loss, heap | CPU cao không tự chứng minh user impact |
| Control plane | deploy, schema/grant change, nodetool, SSH, TLS cert, config diff | Những sự kiện này có thể **không nằm trong Cassandra CQL audit log** |

Để biết một incident bắt đầu **trước hay sau một thao tác**, phải chuẩn hóa timestamp về UTC, lưu source clock và sai lệch đồng hồ. Không dùng thời điểm alert fire như thời điểm lỗi bắt đầu; còn thời gian `for`, scrape interval và ingestion lag.

### 2.2. Metric type quyết định cách đặt alert

| Kiểu dữ liệu | Ví dụ từ Cassandra | Cách đọc |
|---|---|---|
| Counter | `ClientRequest.Read.Timeouts`, `Storage.Exceptions` | Theo tốc độ tăng/hiệu số trong window, xử lý reset khi restart |
| Gauge | `Compaction.PendingTasks`, `ThreadPools.PendingTasks` | Giá trị hiện tại/trend, không `rate` mù |
| Histogram | `Table.SSTablesPerReadHistogram`, `TombstoneScannedHistogram` | Phân phối, tail; mapping bucket của exporter là quan trọng |
| Timer/Latency | `ClientRequest.Read.Latency` | Đơn vị và observation window; không lấy mean của p99 các node |
| Meter | `DroppedMessage.Dropped`, `HintsService.HintsFailed` | Số sự kiện/tốc độ, semantics theo type và exporter |
| State/event | Node Down/Up, schema agreement, audit action | Dữ liệu rời rạc, có thể mất do log rotation hoặc network |

Cassandra dùng Dropwizard Metrics, nhiều chỉ số được phơi qua JMX và gom bởi exporter. Tên như `org.apache.cassandra.metrics:type=ClientRequest scope=Read name=Timeouts` mô tả dữ liệu ở **node**, không phải một metric cluster duy nhất. Với Prometheus, exporter quyết định tên, nhãn, unit và việc chuyển counter sang `_total`.

### 2.3. Đừng để thiếu telemetry bị coi là “hệ khỏe”

Một node chết có thể ngừng phát metric cùng lúc lỗi thực sự tăng. Vì vậy cần **meta-monitoring**:

- `up` hoặc chỉ số exporter scrape health và số targets đúng như inventory.
- Bản đồ expected vs observed nodes/DCs, phát hiện series mất hẳn.
- Clock skew, remote-write lag, scrape interval và data retention.
- Độ trễ/độ đầy của log ingestion, audit log drops/rotation/retention.
- Synthetic request/canary tại CL phù hợp để xác nhận availability từ phía user.

Một đồ thị “WriteTimeout rate = 0” khi exporter của ba node đều Down **không phải bằng chứng** hết lỗi. Không ghép kết luận từ một dashboard xanh với “cluster khỏe” khi không biết coverage và nguồn thực của dữ liệu.

## 3. Xây danh mục cảnh báo theo ảnh hưởng và hành động

### 3.1. Phân cấp severity theo mục đích

| Mức | Khi nào | Hành động |
|---|---|---|
| **SEV1 / page ngay** | API trọng yếu mất availability, data corruption có bằng chứng, hoặc cluster không thể đáp ứng consistency CL bắt buộc | Mở incident, điều phối on-call và owner dữ liệu |
| **SEV2 / page** | Error budget cháy nhanh, một DC lỗi nhưng dự phòng còn, disk sẽ cạn trước khi kịp can thiệp | Triage theo deadline đã cam kết |
| **Warning / ticket** | Compaction backlog kéo dài, node flapping, repair/snapshot trễ chưa chạm SLO | Khảo sát trong giờ làm việc |
| **Info / dashboard** | Nhiễu ngắn hạn, restart theo bảo trì, tăng CPU có kiểm soát | Lưu bối cảnh, tránh đánh thức người trực |

Mức thực tế cần dựa trên SLA/SLO và business impact. Một node `DN` trong RF3 có thể vẫn cho phép `LOCAL_QUORUM` nếu hai natural replicas còn sống, nhưng đã mất một lớp dự phòng; trong RF1, cùng `DN` có thể làm request unavailable. Phải xét token ownership, RF, DC và CL trước khi tăng severity.

### 3.2. Danh mục nguồn cảnh báo và runbook

| Nhóm | Tín hiệu chính | Triage đầu tiên |
|---|---|---|
| API availability | Error rate theo endpoint/service, số samples | Gateway hay driver hay coordinator? |
| API latency | p95/p99 cùng timeout/error rate | So deployments, query class và CQL calls/request |
| Cassandra request errors | `ClientRequest.Read/Write.Timeouts,Failures,Unavailables` | CL/RF/DC, replica liveness, server exception |
| Membership | Expected node missing/Down, theo nhiều views | Gossip, JVM/host/network, topology changes |
| Disk | Bytes free, positive growth slope, time-to-full | Data/commitlog/hints/snapshot/log directories |
| Commitlog | `PendingTasks`, `WaitingOnCommit` | Fsync/disk latency, offered writes |
| Compaction | `Compaction.PendingTasks` + read p99/disk IO | Table strategy, backlog growth, throughput |
| Thread pool | `ThreadPools.PendingTasks/TotalBlockedTasks` | Stages đang nghẽn, request load |
| Dropped messages | `DroppedMessage.Dropped` per type | Request class, packet/network/queues |
| Hints | `HintsService.HintsFailed/TimedOut`, not-stored | Hints holders, target health, max hint window |
| Repair schedule | Last successful complete repair + range coverage | Grace window, owner, preflight health |
| Backup/restore | Last verified restore, actual RPO/RTO, evidence gaps | Manifest, validation gate và recovery owner |
| Audit logging | Disabled/archiving failure, retention gap | Security owner, node runtime setting |
| Security | Unauthorized logins, unscheduled DDL/DCL | CQL audit + change-control correlation |
| Telemetry | Exporter missing, scrape gaps, clock skew | Expected inventory và log ingestion |

Một metric đơn lẻ như `PendingCompactions=20` chưa đủ để kết luận outage; phải so baseline, mức tăng, IO/GC, latency và offered traffic. Các cảnh báo nên có owner, severity, runbook và escalation; không phát cùng một page cho mọi nguyên nhân độc lập.

### 3.3. Hợp đồng của một cảnh báo có thể hành động

~~~yaml
alert_id: CASS-READ-ERROR-BURN
objective: "events-api read success >= 99.9% over 30 days"
scope: "service + dc + query-class"
signal: "user-facing error rate correlated with Cassandra exception types"
window: "5m fast detection and 1h confirmation (illustrative)"
traffic_floor: "enough requests for a meaningful ratio"
severity: "page on sustained multi-window burn"
owner: "DB-oncall + service-oncall"
runbook_url: "https://runbooks.example.invalid/cassandra/read-errors"
stop_condition: "change only with matching approval and rollback plan"
verify: "success, p99 and required consistency semantics recovered"
data_risk: "unknown write outcomes and read freshness assessed"
~~~

URL là **placeholder**, không phải runbook đã tồn tại. Cảnh báo thực cần liên kết đến trang có version, owner, on-call rotation và mục “không được làm”.

### 3.4. SLO burn rate và ngưỡng thực tế

Với SLO thành công 99,9%, error budget là 0,1% tổng requests. Một tỷ lệ lỗi 1,44% cho burn-rate:

\[
\frac{0.0144}{0.001}=14.4.
\]

**Multi-window burn-rate** kết hợp window ngắn để xác nhận lỗi đang diễn ra và window dài để lọc nhiễu. Khi traffic rất thấp, vài lỗi cũng làm % tăng mạnh; phải có traffic floor hoặc chính sách riêng cho những transactions quan trọng hiếm khi xảy ra.

Không dùng p99 của requests thành công làm SLO duy nhất: những request chậm nhất có thể timeout và không còn trong histogram, làm p99 trông tốt hơn trong lúc error rate tăng. Luôn hiển thị traffic, success/error rate và latency cùng lúc.

### 3.5. Cảnh báo disk dựa trên thời gian còn lại

Disk 85% đầy lúc nhiều compaction/repair/streaming có thể rủi ro hơn disk 92% nhưng hoàn toàn idle, tùy headroom bắt buộc của cluster. Xem:

~~~text
disk free bytes / total bytes
positive growth slope and estimated time-to-full
data/commitlog/hints/audit/snapshot volumes
ongoing compaction, hints, repair and streaming
available inodes / filesystem mount health
~~~

Nếu snapshots dùng hardlinks, `du -sh snapshots/` không nhất thiết bằng dung lượng thực có thể giải phóng khi xóa. Không tự chạy `clearsnapshot` hoặc dọn commitlog để “sửa” disk alert. Chỉ chuyển sang thay đổi trạng thái theo runbook có đánh giá retention, backup và khả năng mất dữ liệu.

## 4. Cấu hình cảnh báo với Prometheus/Alertmanager

### 4.1. Tên metrics được chuẩn hóa, không phải mapping mặc định

Các ví dụ dưới đây dùng **tên minh họa do telemetry pipeline tự chuẩn hóa**:

~~~text
cassandra_client_read_timeouts_total
cassandra_client_write_timeouts_total
cassandra_node_disk_free_bytes
cassandra_node_disk_total_bytes
cassandra_compaction_pending_tasks
cassandra_audit_logging_enabled
service_http_requests_total
service_http_errors_total
~~~

Chúng **không phải metric names mà Cassandra/JMX exporter nhất thiết xuất ra**. Trước khi triển khai phải kiểm JMX exporter mapping, unit, counters, nhãn `{cluster,dc,node,service}`, và xem những series đó có thật. Thuộc tính JMX `AuditLogEnabled` cần mapping hoặc collector riêng. “Không có series” khác “giá trị bằng 0”.

### 4.2. Prometheus alerts minh họa

~~~yaml
groups:
  - name: cassandra-observability-example
    interval: 30s
    rules:
      - alert: CassandraExporterDown
        expr: up{job="cassandra-jmx"} == 0
        for: 2m
        labels:
          severity: warning
          team: database
        annotations:
          summary: "JMX exporter unavailable"
          description: "Check node inventory, export process and host reachability"
          runbook_url: "https://runbooks.example.invalid/cassandra/telemetry"

      - alert: CassandraReadTimeoutsSustained
        expr: |
          sum by (cluster, dc) (
            rate(cassandra_client_read_timeouts_total[5m])
          ) > 0.1
        for: 5m
        labels:
          severity: warning
          team: database
        annotations:
          summary: "Coordinator read timeout rate increased"
          description: "Correlate with API errors and request CL/RF"
          runbook_url: "https://runbooks.example.invalid/cassandra/reads"

      - alert: CassandraDiskHeadroomLow
        expr: |
          (
            cassandra_node_disk_free_bytes
            /
            cassandra_node_disk_total_bytes
          ) < 0.12
        for: 10m
        labels:
          severity: warning
          team: database
        annotations:
          summary: "Disk headroom below illustrative threshold"
          runbook_url: "https://runbooks.example.invalid/cassandra/disk"

      - alert: CassandraAuditLoggingDisabled
        expr: cassandra_audit_logging_enabled == 0
        for: 5m
        labels:
          severity: security
          team: security
        annotations:
          summary: "Audit logging disabled on an expected node"
          runbook_url: "https://runbooks.example.invalid/cassandra/audit"
~~~

Ngưỡng `0.1 timeout/s`, `12% disk free` và thời gian `for` **chỉ dùng để dạy cú pháp**, không phải policy cho mọi cluster. Alert `up==0` phát hiện target **còn trong discovery nhưng không scrape được**; nếu target biến mất khỏi discovery, cần inventory comparison hoặc heartbeat khác. Alert audit `enabled==0` sẽ không phát nếu metric bị mất hoàn toàn, do đó cần meta-alert cho exporter/collector.

### 4.3. Lọc lỗi bằng mẫu số và traffic floor

Một biểu thức cho normalized service metrics:

~~~promql
(
  sum by (service) (rate(service_http_errors_total[5m]))
  /
  clamp_min(
    sum by (service) (rate(service_http_requests_total[5m])),
    0.000001
  )
) > 0.0144
and on (service)
sum by (service) (rate(service_http_requests_total[5m])) > 1
~~~

Đây mới là **một window 5 phút** với ngưỡng giả định, chưa phải multi-window alert hoàn chỉnh. Chỉ có ý nghĩa khi request numerator/denominator được đo với cùng filter/labels, không đếm lỗi hai lần và **không bỏ sót timeouts**.

### 4.4. Nhãn, grouping, inhibition và silence

Chọn labels đủ để hành động `cluster, dc, service, alertname, severity, team`. Không đưa `user_id, partition_key, request_id` lên label vì cardinality sẽ tăng khổng lồ, đồng thời có nguy cơ lộ riêng tư.

Alertmanager hỗ trợ grouping theo cluster/DC, route theo nhóm DB/SRE/Security, và inhibition giữa alerts. Nhưng **không inhibit mọi sự cố Cassandra chỉ vì exporter Down**: absence of telemetry có thể che một disk outage thật. Silence trong maintenance phải có `change_id, actor, scope, UTC start/end, expiry`; không silence vô thời hạn để làm dashboard xanh.

### 4.5. Kiểm thử alerts như kiểm code

1. Xác minh mapping/units của metric từ JMX tới exporter.
2. Dùng recorded series / unit tests để giả lập counter reset, node reboot, missing scrape, no traffic.
3. Kiểm `for`, grouping và các quy tắc escalation với RF1, RF3 và multi-DC.
4. Kiểm Alertmanager route tới người trực và runbook link không bị 404.
5. Đo false positives và false negatives dưới baseline/peak traffic.
6. Lưu Git commit, diff, approval, deployment timestamp, rollback cho alert rules.

Kết quả kiểm thử phải ghi được **một event bắn alert, một event nhận thông báo, một event xác nhận và một event clear**. Việc rule được Prometheus parse thành công **không chứng minh** người trực sẽ nhận thông tin đúng và có thể làm theo runbook.

## 5. Vòng đời một incident Cassandra: từ page đến kết luận

### 5.1. Sáu mốc có ý nghĩa khác nhau

~~~text
T_last_good      last bucket/request known healthy
T_first_bad      first bucket/request observed failing
T_alert_fire     alert evaluation + for duration completed
T_ack            human on-call acknowledged
T_mitigated      user impact reduced by a verified mitigation
T_resolved       SLO and correctness and residual risks handled
~~~

**Không gọi `T_alert_fire` là onset**. Scrape/remote-write/aggregation và `for: 5m` có thể tạo chậm trễ. Lưu timezone/clock offset per source; nếu chỉ có bucket 5 phút, dùng cửa sổ “first-known-bad between 10:40–10:45Z” chứ không bịa thời điểm đến một giây.

### 5.2. Trong 0–5 phút

- Xác nhận **ảnh hưởng tới người dùng**: error/success, business operations, read/write, CL, RF, DC, traffic.
- Xác định nhóm sự cố có thể mất dữ liệu: unresolved write outcomes, deletes, disk full, unavailable toàn bộ, corrupted SSTables.
- Tạo incident ID, severity, commander, người phụ trách DB và communication channel.
- Lưu những biểu đồ ứng dụng/Driver/coordinator/host đầu tiên **trước khi restart hoặc đổi config**, nếu không gây chậm mitigation khẩn cấp.
- Xem alert đang là symptom hay còn dấu hiệu telemetry missing.
- Nếu không có node quorum hoặc disk critical, thực hiện escalation theo runbook ưu tiên an toàn dữ liệu.

### 5.3. Trong 5–15 phút

Chia **ma trận ảnh hưởng** thay vì kết luận “Cassandra đang hỏng”:

| Chiều | Affected | Healthy controls | Chưa biết |
|---|---|---|---|
| Service/deployment | v28 API events | v27 cùng AZ | Versions ở DC khác |
| CQL shape | latest-N with pageSize 100 | point read by PK | Full range queries |
| Keyspace/table | `events_by_device_day` | `metadata_by_device` | Bảng khác |
| Consistency | `LOCAL_QUORUM` write | `LOCAL_ONE` read | Retry/CL override |
| DC/rack/node | dc1/N2 | dc2 controls | N2 token/replica overlap |
| Time | first-bad 10:42–10:45Z | 10:35–10:40Z | Clock skew |

So những thay đổi **có hiệu lực** trước first-bad: app/config deploy, CQL schema/role, TLS key, RF/CL, node join/leave, compaction/repair/backups, network/DNS/load burst và TTL cohort. Không có deploy mới **không có nghĩa** workload hay dữ liệu không thay đổi.

### 5.4. Trong 15–30 phút: giả thuyết có thể bác bỏ

Mỗi giả thuyết phải có predicted observations, falsifier, test risk:

~~~text
H1: N2 disk saturation raises coordinator write p99.
Expected: N2 IO await/commitlog stalls increase before errors;
          requests involving N2 more affected.
Falsifier: nodes have healthy IO during same UTC window,
           and only new app deployment shows driver queue pressure.
Low-risk probe: host/JMX metrics, nodetool info/tpstats,
                node/replica routing evidence.
Risk: diagnostic overhead; no repair/restart yet.
~~~

Đánh dấu `OBSERVED` / `INFERRED` / `NOT_COLLECTED` và confidence. Chọn phép thử phân biệt được nhiều giả thuyết với ít tác động nhất; tránh chạy một thao tác ghi dữ liệu để “xem có hết lỗi không” khi chưa có rollback.

### 5.5. Quyết định mitigation và xác minh

Một mitigation được xét theo:

1. **Business invariant:** Có làm mất consistency, data retention hay authorization không?
2. **Scope:** Node, DC, table, cluster, service version nào sẽ bị tác động?
3. **Blast radius:** Nếu thao tác fail, những replicas nào bị mất availability?
4. **Approval:** Ai là incident commander/DB owner/second approver?
5. **Before evidence:** Lưu snapshot tối thiểu của metrics, config và trạng thái dữ liệu.
6. **Stop/rollback:** Nếu p99/error/disk/repair pending xấu thêm, dừng khi nào?
7. **After evidence:** So cùng window/labels/traffic, không chỉ nhìn alert cleared.

Sau mitigation, phân biệt `MITIGATED` (user impact đã giảm) với `RESOLVED` (root cause/risks/consistency được xử lý). Giảm offered traffic từ 5.000 xuống 500 requests/s có thể làm p99 giảm mà nguyên nhân quá tải vẫn còn.

### 5.6. Handoff không làm người sau điều tra lại từ đầu

~~~text
Incident / severity / owner / next update UTC:
Last good - first bad UTC with uncertainty:
Affected and healthy cohorts:
Write/read CL and RF/DC:
Errors by gateway / driver / coordinator:
Current best hypotheses and falsifiers:
Evidence IDs / dashboards / log gaps:
Actions already taken (actor, UTC, change ID):
Actions explicitly NOT taken:
Data integrity / UNKNOWN writes / repair state:
Next safe check and stop condition:
~~~

**Không thể đóng incident chỉ vì pager ngừng reo** nếu dashboard mất telemetry, dữ liệu đã xóa xuất hiện lại, write timeout chưa được reconcile hoặc repair đã bị gián đoạn mà không có owner.

## 6. Chuẩn hóa sổ tay ứng phó (runbook) có thể thi hành

### 6.1. Một runbook có cấu trúc tối thiểu

~~~markdown
# RB-CASS-READ-ERRORS — Version 2

Owner: DB SRE | Reviewed UTC: YYYY-MM-DD
Triggers: alert IDs, thresholds, exceptions
Scope: Cassandra 4.1/5.0, keyspace/table/DC/service
User impact: SLI/SLO and data correctness risk
Required access: read-only JMX/metrics/log access
Preconditions: verified environment/cluster ID and maintenance state

## First 5 minutes
- Confirm business impact, node health, metrics coverage
- Save exact UTC window + request CL and error class

## Read-only checks
- Command/query, rationale, expected output, limits
- Healthy and affected comparison

## Decision tree
- Symptoms -> hypotheses -> falsifiers
- Evidence needed before choosing any action

## Controlled mitigations (not automatic)
- Approval, commands with exact scope, dry-run where supported
- Risk, before snapshot, stop and rollback condition

## Verification and exit
- User SLO at representative traffic
- Correct read/write semantics and data integrity
- Audit record and communication link

## Escalation and handoff
- DB, app, infra, security owners + contact procedures
~~~

Một runbook **không** phải danh sách 20 lệnh `nodetool`. Nó là decision document có giới hạn quyền, điều kiện dùng lệnh và tiêu chí xác minh.

### 6.2. Phân loại lệnh theo hậu quả

| Cấp | Ví dụ | Yêu cầu |
|---|---|---|
| **READ / quan sát** | `nodetool status`, `info`, `tpstats`, `compactionstats`, `netstats`, `tablestats` | Node/source/UTC, read-only credentials, rate limit |
| **READ nhưng tốn tải** | `tablehistograms` nhiều tables, tracing có mẫu, `repair --preview` | CPU/IO budget, change window, stop gate |
| **STATE_CHANGE có thể đảo ngược** | Bật/tắt một runtime feature, đổi logging level, điều chỉnh throttle | Approval, expiry và cách restore config |
| **STATE_CHANGE tốn tải** | `repair`, `cleanup`, `rebuild`, compaction, bootstrap operations | Topology health, concurrency, data integrity review |
| **DESTRUCTIVE/khó đảo ngược** | `truncatehints`, `clearsnapshot`, `decommission`, CQL `TRUNCATE/DROP` | Dual approval, backup/recovery plan, blast radius |

Một số lệnh **đọc** cũng tốn nhiều CPU/IO (ví dụ `repair --preview` phải xây Merkle trees). Ngược lại, lệnh đổi runtime settings tuy có lệnh đảo ngược vẫn có thể gây mất durability/availability trong thời gian ngắn. Phân loại theo **tác động thực** với release và workload.

### 6.3. Bộ lệnh quan sát trong incident

~~~bash
# Quan sát trên host được cấp quyền; kiểm nodetool help theo release.
date -u +"%Y-%m-%dT%H:%M:%SZ"
nodetool status
nodetool describecluster
nodetool info
nodetool tpstats
nodetool proxyhistograms
nodetool compactionstats
nodetool netstats
nodetool tablestats incident_lab.events_by_device_day
~~~

Ghi chính xác node đã hỏi: `status` trên N1 và N3 có thể khác nhau khi gossip/network partition. `netstats` phản ánh streaming, không phải counter backlog hints; `proxyhistograms` là coordinator latency, không phải API p99. Không lấy trung bình p99 giữa nodes hoặc cộng p99 các lớp thành end-to-end p99.

### 6.4. Dùng help và credential handling đúng cách

~~~bash
nodetool help status
nodetool help repair
nodetool help enableauditlog
~~~

Không đưa mật khẩu qua tùy chọn `-pw` trên command line nếu có thể xuất hiện trong process list/history. Khi JMX auth yêu cầu credentials, dùng password file/secret injection được quản lý an toàn; đảm bảo mode của file và log redaction. Không gửi raw terminal outputs chứa IP/username hay nội dung queries nhạy cảm lên hệ thống public.

### 6.5. Tiêu chí runbook sẵn sàng

- Có owner và version/last-reviewed date.
- Đã qua review của DBA/SRE/Security tương ứng và tập dượt một lần trong lab.
- Các link dashboard/logs và on-call rotation hoạt động.
- Phản ánh Cassandra release, DC/RF/CL và topology thật, có bảo vệ data.
- Có preflight, command, output expected, failure branch, stop và rollback.
- Không hardcode admin password, private key hoặc production endpoint.
- Mọi update được code review/approval và có change ID.

Một checklist ghi “restart tất cả nodes” hoặc “chạy repair toàn cluster” mà không xét quorum, scope và failure modes **chưa phải runbook an toàn**.

## 7. Ba playbook cốt lõi: quorum, disk và repair

### 7.1. RB-1: Read/WriteTimeout hoặc Unavailable tăng

**Trigger:** user-facing error rate tăng; Java logs phân loại `DriverTimeoutException` / `ReadTimeoutException` / `WriteTimeoutException` / `UnavailableException`.

**Quan sát trước can thiệp:**

1. Lập UTC timeline cho first-bad, changes và `T_alert_fire`.
2. Tách HTTP/gateway timeout, Driver deadline và coordinator READ/WRITE_TIMEOUT. Không gộp mọi lỗi thành một counter “timeout”.
3. Kiểm RF/DC/CL của query và liveness của **natural replicas** (khác với coordinator).
4. Thu node status từ nhiều nodes nếu có dấu hiệu gossip disagreement.
5. Kiểm client pool/throttler, retry/speculative execution; total CQL attempts có thể vượt HTTP requests.
6. Xem disk/GC/network/table tombstones/compaction và chọn giả thuyết có thể bác bỏ.

**Không tự làm:** giảm CL để bỏ unavailable, tăng retries nhiều tầng, tăng request timeout vô hạn, restart nhiều replicas cùng lúc.

**Exit:** successful reads/writes ở CL bắt buộc, error rate trong SLO với traffic đại diện, unknown writes được reconcile hoặc assigned, topology và data integrity đủ bằng chứng.

### 7.2. RB-2: Disk headroom critical

**Trigger:** estimated time-to-full thấp hơn thời gian cần để can thiệp an toàn, hoặc free disk dưới mức bảo vệ compaction/commitlog.

**Các bước an toàn:**

1. Phân biệt mount data, commitlog, hints, snapshots, logs/audit, remote backup staging.
2. Thu disk bytes/inodes + growth trend, compaction/streaming/hints/backup jobs.
3. Kiểm nguồn tăng sau deploy, TTL expiration, write burst, repair concurrency.
4. Ước lượng headroom cần cho **ongoing compaction/streaming**; disk % thấp chưa chắc có chỗ cho thao tác mới.
5. Nếu phải giảm offered write rate hoặc hoãn job, xin phê duyệt theo SLA, có rollback.
6. Kiểm cảnh báo audit log archival cũng có thể chạm quota; không vô hiệu audit để lấy dung lượng tùy tiện.

**Không tự làm:** xóa commitlog, SSTable, hints, snapshots chưa kiểm backup/retention; major compaction để “dọn” khi disk đã gần đầy.

**Exit:** disk free/growth headroom ổn định, CQL write success, commitlog/compaction/backup/audit paths không còn tắc và data invariants giữ.

### 7.3. RB-3: Repair schedule bị trễ hoặc inconsistency

**Trigger:** last successful repair vượt policy, `gc_grace_seconds` risk, hoặc hints không được lưu/replica divergence có bằng chứng.

**Preflight:**

- Phân biệt hinted handoff, read repair và anti-entropy repair.
- Xem RF/DC, natural replicas Up, target topology Normal, repair history.
- Chọn full/incremental, ranges/tables, concurrency, disk/network budget.
- Với `-pr`, lịch sửa toàn cluster cần bao phủ primary ranges của các nodes/DC theo runbook; một command trên một node **không** là full cluster repair.
- Nếu nghi tombstones đã purged và data resurrection, **không repair mù** có thể phát tán dữ liệu stale.
- `--preview` có thể tốn tài nguyên dù không stream; phải có budget/approval.

**Exit:** repair job success theo scope đã cam kết, SSTable/streaming errors được đối chiếu, dữ liệu mẫu và application consistency hợp lệ. Không suy từ `nodetool status` thấy `UN` rằng replicas đã hội tụ.

### 7.4. RB-4: Authentication/authorization errors sau change

**Trigger:** `UnauthorizedException`, failed logins hoặc CQL DCL changes ngoài maintenance window.

**Quan sát:** audit log CQL `AUTH/DCL/ERROR` trên mọi coordinators liên quan; deployment identity, certificate/truststore/KMS metadata, schema/role grants, system_auth RF/repair state. Tách TLS handshake failures (trước CQL) khỏi CQL login/authz. Xác nhận app đúng local DC/identity/role.

**Không tự làm:** tắt TLS hoặc authentication, cấp superuser cho app, log passwords, gửi private keys tới incident chat. Dùng rollout/rollback được kiểm soát theo security runbook.

### 7.5. Tình huống hai vấn đề trùng thời điểm

Nếu compaction pending tăng đúng lúc deploy Java v28, chưa đủ bằng chứng v28 **gây compaction** hoặc compaction **gây timeout**. Hãy so cùng query shape/CL trên v27/v28 và per-node IO/GC. Một correlation theo phút không chứng minh causality. Runbook cần ép responder viết **dự đoán phân biệt hai giả thuyết** thay vì nhảy đến restart hay thay compaction strategy.

## 8. Cassandra audit logging: ghi CQL và xác thực

### 8.1. Cassandra 4.0+ ghi được và không ghi được gì?

Apache Cassandra có **Audit Logging** từ bản 4.0, cấu hình qua `audit_logging_options` hoặc `nodetool enableauditlog` ở **từng node**. Nó có thể ghi CQL requests thành công và thất bại, authentication/authorization events, theo categories và filters.

| Loại | CQL audit capture khi filter cho phép? | Ví dụ |
|---|---|---|
| DDL | Có | `CREATE TABLE`, `ALTER KEYSPACE`, `DROP INDEX`, `TRUNCATE` |
| DCL | Có | `GRANT`, `REVOKE`, `CREATE ROLE`, `ALTER ROLE` |
| DML | Có | `UPDATE`, `DELETE`, `INSERT` và batches theo taxonomy của release |
| QUERY/PREPARE | Có | `SELECT`, prepared requests |
| AUTH/ERROR | Có | Login success/failure, unauthorized attempt, request failure |
| `nodetool repair` / `cleanup` / `disablehandoff` | **Không** | Đây là JMX/management operations |
| Thay `cassandra.yaml` / `logback.xml` | **Không** | Thao tác filesystem/deployment |
| SSH/sudo, container/Kubernetes/cloud | **Không** | Hoạt động ngoài native CQL protocol |

**Điểm then chốt:** Cassandra audit log không phải nhật ký đầy đủ của DBA/operator. Tài liệu chính thức nêu rõ nó **không chứa `nodetool` commands hoặc chỉnh `cassandra.yaml`**. Muốn biết ai chạy repair, thay RF, drain hoặc restart, phải lưu thêm một **administrative action ledger** độc lập.

### 8.2. Trường thông tin của một CQL audit entry

Tùy implementation, bản ghi có:

~~~text
timestamp        Unix timestamp của request theo nguồn
user             CQL role
source           client IP + port
host             node/coordinator nhận request
keyspace         keyspace liên quan
scope            table/aggregate/function/role nếu áp dụng
category/type    DDL, DCL, DML, QUERY, PREPARE, AUTH, ERROR
operation        CQL command hoặc tên operation
batch            batch identifier nếu có
state/options    request state và options theo logger/version
~~~

**Audit record được ghi trên coordinator xử lý CQL**, không nhân bản theo RF như data. Trong RF3, một `UPDATE` ACK bởi hai replicas có thể chỉ có một audit record trên coordinator. Vì vậy phải thu audit từ **mọi node có thể làm coordinator**, không chỉ natural replicas của table.

### 8.3. Implementations và lưu ý bảo mật

| Logger | Đặc điểm | Cân nhắc |
|---|---|---|
| `BinAuditLogger` | Binary Chronicle Queue segments | Dùng `auditlogviewer`, cần roll/archive/permissions |
| `FileAuditLogger` | Text trong file logging framework | Dễ đọc nhưng performance/retention khác |
| `NoOpAuditLogger` | Không ghi audit | Không phù hợp policy bắt buộc lưu audit |

Không bật **Full Query Logging (FQL)** thay audit một cách mù quáng: FQL hỗ trợ replay/debug/performance và có semantics/chi phí/PII risk khác; audit phục vụ CQL và auth events, không nhằm replay tất cả business operations.

**Quyền riêng tư:** CQL text có thể chứa literal nhạy cảm; prepared statement audit không nhất thiết ghi bound values trong EXECUTE, nhưng **không được giả định log luôn an toàn**. Câu sai cú pháp, query literals và custom loggers có thể lộ dữ liệu. Cassandra che passwords theo một số DCL patterns, không thay thế redaction và kiểm thử trường hợp câu sai cú pháp. Cần encryption/retention, quyền truy cập và audit quyền đọc chính logs.

### 8.4. Cấu hình Cassandra 5.0 minh họa

~~~yaml
# cassandra.yaml CHỈ trên isolated lab; cần approval/rollout theo node.
audit_logging_options:
  enabled: true
  logger:
    - class_name: BinAuditLogger
  audit_logs_dir: /srv/cassandra-audit-lab
  included_categories: AUTH,ERROR,DDL,DCL,PREPARE
  excluded_keyspaces: system,system_schema,system_virtual_schema
  roll_cycle: HOURLY
  block: true
  max_queue_weight: 268435456
  max_log_size: 17179869184
~~~

**Phạm vi:** lọc `included_categories` như trên **không thu mọi DML/QUERY**; đây chỉ là policy lab tập trung vào CQL quản trị và auth, không thể tuyên bố “audit tất cả CQL”. Nếu compliance yêu cầu mọi thao tác, phải review filters/retention/cost/PII. `max_log_size` có thể làm segments cũ bị xóa khi đạt giới hạn; cần archive đúng policy và dung lượng.

Cassandra cho phép `archive_command` để chuyển logs khỏi ephemeral disk. Lệnh archive do process Cassandra thực thi cần threat model về quyền shell/script, file lifecycle và không cấp quyền JMX cho tác nhân không tin cậy. Cấu hình runtime via `nodetool enableauditlog` có thể **override** giá trị file `cassandra.yaml` trên node đó; cần kiểm trạng thái thực.

### 8.5. Quan sát audit logging an toàn

~~~bash
# Đọc config runtime, cú pháp tùy bản Cassandra:
nodetool getauditlog

# Có thể đối chiếu JMX StorageService AuditLogEnabled.

# Trên bản sao binary log thuộc isolated lab:
auditlogviewer /srv/cassandra-audit-lab
~~~

Đối chiếu `nodetool help getauditlog` / `auditlogviewer --help` theo release. Không bật `enableauditlog` hoặc tắt `disableauditlog` trên production chỉ để thử khi chưa đánh giá storage/performance/security. Một node enabled không chứng minh các nodes khác đã bật hoặc collector đã chuyển files tới audit store độc lập.

### 8.6. Kiểm thử CQL audit filter trong cluster học tập

Trong isolated cluster có datacenter thực tên `dc1`, schema lab:

~~~sql
CREATE KEYSPACE IF NOT EXISTS audit_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 1
};

CREATE TABLE IF NOT EXISTS audit_lab.action_probe (
    id uuid PRIMARY KEY,
    note text
);

INSERT INTO audit_lab.action_probe (id, note)
VALUES (11111111-1111-4111-8111-111111111111, 'lab-check');

SELECT note FROM audit_lab.action_probe
WHERE id = 11111111-1111-4111-8111-111111111111;
~~~

Với `included_categories` chỉ `AUTH,ERROR,DDL,DCL,PREPARE`, `CREATE TABLE` có thể xuất hiện, nhưng `INSERT/SELECT` **không nằm trong danh sách**; đó là **negative control** để chứng minh filters hoạt động. `CREATE KEYSPACE IF NOT EXISTS` khi đã tồn tại không tạo object mới dù request có thể vẫn được audit.

Sau test, xem binary logs từ **coordinator thật** và kiểm fields, thời gian, categories, archive. Không yêu cầu ba bản audit vì RF3. Nếu không thấy event, kiểm `enabled`, filters, node, UTC, logdir/collector trước khi suy rằng command không chạy.

## 9. Nhật ký quản trị phải vượt ra ngoài CQL audit

### 9.1. Bằng chứng cho mỗi kênh thao tác

| Kênh | Ví dụ | Nguồn bằng chứng |
|---|---|---|
| CQL native | `ALTER TABLE`, `GRANT`, `TRUNCATE` | Audit CQL trên coordinator + change ticket |
| JMX/`nodetool` | `repair`, `disablehandoff`, `drain` | Command wrapper + host process audit + change ID |
| SSH/sudo | Service restart, sửa file/mount | OS auditd/sudo logs, session recording khi phù hợp |
| Kubernetes | Scale StatefulSet, rollout config/restart pod | Kubernetes API audit, deployment events |
| Cloud platform | Resize disk, firewall, KMS/secrets | IAM/cloud activity trail |
| Configuration repository | `cassandra.yaml`, JVM flags, logging | Git commit, review, signed build/rollout |
| CI/CD scheduler | Automated repair/backup/cert rollout | Workflow run ID, identity, approvals |
| Alertmanager | Silence/inhibition, threshold change | Ruleset commit, silence actor/expiry |

**Một loại log không thay loại khác.** Cassandra thấy `ALTER TABLE` không chứng minh ai restart Kubernetes pod; OS thấy process `nodetool` không chứng minh command đã repair toàn cluster; change ticket ghi ý định nhưng chưa chứng minh thực thi.

### 9.2. Trường tối thiểu trong administrative action ledger

~~~text
action_id              unique, stable across retries
incident_id/change_id  approved reason and operator context
actor_principal        human/service identity via SSO/workload identity
approver_principal     independent approval for high-risk operations
host_identity          exact host ID and data center
cluster_identity       cluster and environment allowlist
operation_class        READ / CONFIG_CHANGE / REPAIR / DESTRUCTIVE
command_name           nodetool repair, CQL ALTER TABLE, ...
sanitized_argv         structured arguments, secrets REDACTED
command_fingerprint    digest of safe canonical command and target
planned_time_utc       approval time
started_time_utc       actual execution start
finished_time_utc      observed finish or UNKNOWN
exit_code              integer or NO_RESULT
before_evidence_ids    metrics/config/status snapshots
after_evidence_ids     same UTC filters and data checks
rollback_or_stop       planned and observed status
audit_storage_ref      immutable log or object version ID
~~~

Không ghi toàn bộ raw stdin/stdout nếu có thể chứa secrets, partition values hoặc user tokens. Giới hạn output size, redaction và audit access. `sanitized_argv` phải còn đủ ý nghĩa command nhưng không lộ mật khẩu.

### 9.3. Ý định, thực thi và hệ quả là ba events

~~~text
10:41:10Z  APPROVED  CHG-42: repair table X on node N2
10:42:01Z  EXECUTED  ACT-87: nodetool repair -pr X
10:58:31Z  VERIFIED  repair completed for selected scope
~~~

Nếu APPROVED nhưng job không chạy, không ghi EXECUTED. Khi process bị kill/mất output, trạng thái là `EXECUTION_OUTCOME_UNKNOWN`. `exit_code=0` không chứng minh full-cluster repair hoặc đã trả data đúng cho mọi client.

### 9.4. Bốn tính chất của audit ledger

1. **Attribution:** con người/workload identity chịu trách nhiệm; không chỉ shared OS account.
2. **Integrity:** append-only, tamper-evident signatures hoặc object lock; actor không được tự xóa bằng chứng.
3. **Completeness:** đường chạy hợp lệ đi qua wrapper/CI/JIT access; phát hiện bypass bằng host/cloud logs.
4. **Correlation:** action ID liên kết incident/change/cluster/node, thời gian UTC và metrics.

Nếu audit chỉ lưu trên chính node Cassandra đang disk-full, nó có thể mất đúng lúc cần. Ship sang audit store độc lập và kiểm được retention/restore của log.

### 9.5. Desired state khác runtime state

Sau một GitOps rollout, `cassandra.yaml` trên disk có thể đã đổi nhưng Cassandra process chưa restart; hoặc JMX override đã thay một runtime option. Ghi riêng:

~~~text
desired_config_hash
deployed_file_hash
observed_runtime_JMX_values
restart_required
last_rollout_success_utc
nodes_not_converged
~~~

Một Git commit **không** chứng minh mọi node áp dụng. Action audit nên liên kết commit/build digest, deployment phase, per-node success và kiểm trạng thái runtime tương ứng.

## 10. Lược đồ nhật ký và kiểm soát toàn vẹn

### 10.1. JSONL event đề xuất

~~~json
{
  "schema_version": 1,
  "action_id": "ACT-20261121-0087",
  "run_id": "RUN-20261121-04",
  "incident_id": "INC-20261121-11",
  "change_id": "CHG-42",
  "event_type": "ACTION_FINISHED",
  "actor": "workload:db-maintenance-runner",
  "approver": "role:db-second-approver",
  "cluster": "cass-lab-a",
  "environment": "isolated-lab",
  "datacenter": "dc1",
  "node_id": "node-2",
  "command": "nodetool",
  "argv_redacted": ["repair", "-pr", "audit_lab", "action_probe"],
  "category": "STATE_CHANGE",
  "started_utc": "2026-11-21T10:42:01Z",
  "finished_utc": "2026-11-21T10:58:31Z",
  "exit_code": 0,
  "result": "COMMAND_COMPLETED_VERIFICATION_PENDING",
  "before_evidence": ["EV-001", "EV-002"],
  "after_evidence": ["EV-010"],
  "evidence_ref": "audit://runs/RUN-20261121-04/action-ACT-0087"
}
~~~

Đây là **bản ghi giả lập**, không phải Cassandra API mặc định. `audit://` chỉ là nội bộ minh họa. Triển khai thực còn cần `actor_identity_source`, `approval_expires_utc`, binary/script digest, exit signal, stdout/stderr redacted digest, node host ID và trạng thái collector.

### 10.2. Không lưu audit ledger chỉ trong Cassandra đang gặp sự cố

Nếu action ledger được ghi **chỉ vào cluster Cassandra đang sửa**, lúc unavailable hoặc disk full sẽ không ghi được đúng sự kiện quan trọng. Cần **external durable audit sink** như append-only object storage, SIEM hoặc secured log service. Có thể tạo index/query copy nhưng audit durability không nên phụ thuộc một mình vào source đang outage.

Quy tắc fail-closed:

- Không có approval/lease/audit sink cho hành động nguy hiểm thì **không chạy**.
- Emergency break-glass phải theo cơ chế đã phê duyệt sẵn, có session recording, offline evidence và backfill mang nhãn `BREAK_GLASS`.
- Người có quyền chạy command không được có quyền xóa/sửa evidence.
- Audit sink outage là sự cố observability/security và cần escalation riêng.

### 10.3. Hash chain có trusted anchor

Một thiết kế tamper-evident:

~~~text
event_hash_i = SHA256(canonical_json(event_i) || event_hash_(i-1))
signed_checkpoint = SIGN_KMS(event_hash_i, UTC, run_id)
storage = immutable object versions + restricted delete privileges
~~~

Hash chain giúp phát hiện sửa đổi khi có **trusted anchor** bên ngoài. Nếu người tấn công thay được cả chain và anchor, chỉ SHA-256 không bảo vệ được. Kết hợp KMS signatures, object lock, separation of duties, retention và kiểm soát quyền đọc audit.

### 10.4. Timestamp và bằng chứng có thể đối chiếu

~~~text
event_time_utc         timestamp do agent đo
received_at_utc        collector ingest time
clock_offset_estimate  nếu biết
monotonic_duration_ms  thời lượng đo trong một process
source_host_id         source of evidence
collector_version      log schema/mapping
~~~

Nếu node lệch đồng hồ 90 giây, không sắp lệnh và lỗi theo timestamp thô rồi khẳng định quan hệ nhân quả. Ghi uncertainty khi không có nguồn thời gian đáng tin và giữ evidence IDs/links để người khác kiểm lại.

## 11. Automation wrapper: cho phép ít, ghi bằng chứng trước và sau

### 11.1. Hợp đồng một thao tác

Một wrapper không nên chỉ gọi `ssh host "nodetool repair ..."` rồi lưu exit code. Nó phải có **điều kiện trước** và **điều kiện sau**:

~~~mermaid
flowchart TD
    A["Alert hoặc change request"] --> B{"Target thuộc allowlist?"}
    B -->|Không| X["BLOCKED + audit event"]
    B -->|Có| C{"Action trong policy?"}
    C -->|Không| X
    C -->|Có| D{"Approval + lease + audit sink OK?"}
    D -->|Không| X
    D -->|Có| E["Lưu BEFORE + planned action"]
    E --> F["Exec argv, no shell, bounded timeout"]
    F --> G["Lưu exit/signal/output digest"]
    G --> H["Verify expected SLO and data invariants"]
    H --> I["Immutable AFTER event + release lease"]
~~~

Không có nhánh cho phép bỏ qua BEFORE/approval vì collector chậm mà vẫn ghi PASS. Trường hợp khẩn cấp cần **break-glass policy** được duyệt từ trước.

### 11.2. Operation registry theo rủi ro

~~~yaml
environment: isolated-cassandra-lab
allowed_cluster_ids: ["cass-lab-a"]
operations:
  status:
    executable: nodetool
    argv_template: ["status"]
    risk: READ
    approval: false
    max_duration_seconds: 60
  compactionstats:
    executable: nodetool
    argv_template: ["compactionstats"]
    risk: READ
    approval: false
    max_duration_seconds: 60
  repair_selected_table:
    executable: nodetool
    argv_template: ["repair", "-pr", "{keyspace}", "{table}"]
    risk: STATE_CHANGE
    approval: two_person
    max_duration_seconds: 7200
  truncatehints:
    risk: DESTRUCTIVE
    enabled: false
~~~

Đây là **schema thiết kế riêng**, không phải cấu hình Cassandra/runner đọc tự động. Template parameters phải được validate bằng allowlist của keyspaces/tables; tuyệt đối không ghép chuỗi vào shell. Rủi ro phụ thuộc topology, nên một action được approve trên lab không tự cho phép chạy production.

### 11.3. Pseudocode khung runner

~~~text
function execute_change(request):
    action_id = allocate_unique_id()
    require(request.cluster_id in approved_clusters)
    require(request.environment == "isolated-lab")
    require(validate_operation_and_args(request))
    require(valid_change_id_and_not_expired(request))
    require(approval_for_risk_class(request))
    lease = acquire_cluster_operation_lock(request.cluster_id)
    if lease unavailable:
        emit_audit(BLOCKED, "another change in progress")
        return BLOCKED

    try:
        require(audit_sink_is_writable())
        before = collect_bounded_read_only_evidence(request)
        emit_audit_durably(PLANNED, action_id, before, redacted_args)
        result = exec_without_shell(
            argv=validated_fixed_executable_and_args,
            timeout=request.deadline,
            cwd=controlled_working_directory,
            env=allowlisted_environment)
        emit_audit_durably(EXECUTION_FINISHED, result.code, output_hash)
        after = collect_bounded_read_only_evidence(request)
        verify = verify_postconditions_and_data_invariants(after)
        emit_audit_durably(VERIFIED_OR_FAILED, verify, after)
        return verify
    catch error:
        safe_capture_and_notify(error)
        return FAILED_OR_UNKNOWN
    finally:
        release_lease(lease)
~~~

Đây là **pseudocode**, chưa có authentication, durable transport, crash recovery, signal/exit handling hay secret management. Không dùng làm runner production nguyên xi. Nếu process bị kill sau khi command đã chạy nhưng trước event FINISHED, external watchdog phải đối chiếu host audit/server state và báo `OUTCOME_UNKNOWN`; không retry destructive command chỉ vì thiếu log.

### 11.4. Retry và idempotency

| Trường hợp | Chính sách | Lý do |
|---|---|---|
| `nodetool status` lỗi TCP transient | Retry có giới hạn và backoff | Chỉ đọc |
| Audit sink 503 | Retry trước command; vẫn fail thì BLOCKED | Không thay đổi khi không ghi evidence |
| `repair` mất kết nối trong khi chạy | Không lặp mù; query server job state | Có thể job vẫn chạy |
| `cleanup` timeout | Xác minh trước retry | SSTables có thể đã bị thay đổi |
| `ALTER TABLE` timeout | Đọc schema agreement trước khi gửi lại | DDL có thể đã được áp dụng |
| KMS/credentials bị từ chối | Fail và escalate | Không hạ bảo mật để tiếp tục |
| Wrong cluster ID | ABORT ngay | Lỗi safety, không cứu bằng retry |

### 11.5. Không tự động “chữa” nguyên nhân chưa biết

Một auto-remediator nguy hiểm:

~~~text
WHEN ReadTimeout > threshold:
  restart all Cassandra nodes
  lower consistency level
  run full repair
~~~

Những hành động này có thể làm mất quorum, tăng stale reads, tạo IO saturation, xóa dấu vết cần điều tra. Automation an toàn có thể **thu snapshots metrics/logs, gom alerts, tạo ticket, chuẩn bị action proposal**; thao tác đổi trạng thái cần approval và safety policy theo risk class.

### 11.6. Concurrency budget và stop conditions

- Lease theo cluster/DC/token-range, không có hai repairs chồng phạm vi nếu runbook cấm.
- Budget disk/inode/IOPS/network/CPU/GC và giới hạn tác động tới user.
- Rollback theo **version/config hash trước đó**, không mặc định đặt về stock defaults.
- Per-stage timeout, canary first, stop khi SLO/host safety xấu đi.
- Không chạy action khi schema disagreement/topology moving nếu operation cần stable token ownership.

Một hệ automation tốt phải biết **khi nào không được chạy**, chứ không chỉ biết command syntax.

## 12. Phân quyền, bảo mật, retention và khả năng kiểm toán

### 12.1. Quyền tối thiểu theo vai trò

| Vai trò | Được làm | Không nên được phép |
|---|---|---|
| Observer/on-call cấp 1 | Xem SLO/JMX/host logs đã redact, `nodetool status/info` | `repair`, `TRUNCATE`, sửa schema/RF |
| DBA operator | Approved scoped maintenance | Xóa audit evidence hoặc tự duyệt action high-risk |
| Change approver | Duyệt plan/risk, giám sát | Impersonate runner, thay audit logs |
| Security auditor | Đọc audit CQL/OS/cloud và signed records | CQL admin mutation |
| Automation runner | Fixed argv/cluster trong registry, TTL-limited identity | Arbitrary shell/root/all-cluster access |
| Evidence collector | Append/ship events vào audit store | Xóa/sửa segments đã seal |
| Break-glass operator | Emergency action theo policy | Bỏ MFA/after-action review tùy tiện |

JMX có khả năng quản lý mạnh; không coi mọi JMX read API như sandbox nếu permissions không giới hạn. CQL grants không hạn chế quyền của privileged SSH/root. Tách identity SSO, cloud/Kubernetes, OS/JMX và CQL; tránh shared accounts lâu hạn.

### 12.2. Log nội dung gì và tránh nội dung gì?

**Nên:** action/actor/target/UTC, operation class, keyspace/table scope, sanitized arguments, desired vs actual version, exit/signal, before/after metrics, approval, change ID và evidence ref.

**Không mặc định:** raw CQL bound values, customer IDs, passwords/JMX secrets, TLS private keys, token-bearing URLs, full STDOUT của data queries. Muốn đối chiếu một key thật có thể dùng **keyed HMAC** hoặc ID fixture được phép; hash không khóa của ID dễ đoán không đủ bảo vệ.

CQL audit có thể che passwords theo một số DCL patterns nhưng không chắc với câu sai cú pháp; test chính sách redaction trong lab. Không gửi audit segments hay logs production lên public issue tracker.

### 12.3. Queue và availability tradeoff

- **Block/backpressure** khi audit queue đầy có thể tăng request latency nhưng giảm nguy cơ bỏ log, tùy implementation.
- **Drop-on-overload** có thể giữ throughput nhưng mất evidence, không phù hợp mọi compliance policy.

Không suy `block: true` tự bảo đảm log sẽ không mất khi disk/node crash hoặc archive thất bại. Cần thử capacity/performance trên lab, theo dõi queue/disk/archiver, thiết kế retention và alert riêng cho logging failures.

### 12.4. Retention và quản lý khóa

Ví dụ policy nội bộ:

~~~text
hot audit search: 7-30 days
immutable archive: 90-365+ days where required
incident legal hold: longer when authorized
KMS key version: retained for full evidence lifetime
read access: SSO/JIT/MFA with access logs
deletion: approved, logged, separated from action operator
~~~

Các thời hạn **chỉ minh họa**, không phải mặc định Cassandra hay yêu cầu luật định. Retention phải đáp ứng privacy policy, giảm dữ liệu không cần thiết và giữ decrypt keys/permissions suốt vòng đời.

### 12.5. Audit logging “enabled” chưa đủ

Một cuộc kiểm tra coverage:

1. `AuditLogEnabled` trên từng node, kể cả node vừa join sau maintenance.
2. Categories/keyspaces/users include/exclude đúng policy.
3. Có output files thực và segments được chuyển tới independent store.
4. Kiểm archive failures, disk/log rotation/retention và tốc độ sản sinh log.
5. Clock sync, collector uptime, missing-node detection và log gaps.
6. CQL sample được phép xuất hiện đúng coordinator với fields dự kiến.
7. `nodetool`/SSH/cloud được audit **qua đường ngoài Cassandra**.

Một node báo `AuditLogEnabled=true` nhưng không ship log, hoặc exclude cả role của DBA, **không đạt yêu cầu kiểm toán**.

### 12.6. Thay audit policy cũng là privileged change

Đổi `included_categories` hoặc `max_log_size` có thể làm lượng log tăng nhanh hoặc giảm coverage. Cần capacity plan, policy owner, staged rollout, xác minh per-node events, rollback và alert khi thay đổi ngoài window. Thay đổi này phải được ghi trong **action ledger độc lập**, vì CQL audit có thể không tự ghi chính thao tác điều chỉnh logging.

### 12.7. Các loại log bổ sung cho nhau

| Nguồn | Trả lời câu hỏi | Giới hạn |
|---|---|---|
| Cassandra audit | CQL/auth requests nào tới coordinator? | Không ghi `nodetool`/config/SSH |
| OS/JMX wrapper | Ai chạy lệnh quản trị, trên host nào? | Không chứng minh replicas hội tụ |
| Kubernetes/cloud audit | Ai đổi infrastructure hoặc rollout? | Không giải thích data semantics của CQL |
| Git/change ticket | Ý định và approval | Không bảo đảm rollout hoàn tất |
| Full Query Logging | Query replay/debug/performance | Khác CQL audit, có overhead và sensitive data |
| Application traces | Business request và CQL attempts | Không bao phủ tác nhân ngoài application |

Trong một incident, có thể phải join **nhiều nguồn** bằng UTC, actor, host, request ID và change ID. Nếu một nguồn không tồn tại, ghi `EVIDENCE_GAP`; không tự tạo câu chuyện nhân quả từ phỏng đoán.

## 13. Lab: kiểm thử alert → runbook → audit evidence

### 13.1. Mục tiêu và môi trường

Lab có hai đường:

- **Tabletop không cần Cassandra:** dùng chuỗi metrics/events giả lập, thiết kế alert conditions, incident timeline, action ledger và evidence report.
- **Cassandra isolated lab nếu có:** tạo một keyspace/table synthetic, bật audit trong môi trường test theo capacity policy, gửi một DDL và kiểm record trên coordinator; sau đó chạy một lệnh `nodetool status` để thấy CQL audit **không** ghi lệnh đó.

Điều kiện tối thiểu:

~~~text
Cluster: cass-lab-a, Cassandra 4.1/5.0
DC: actual name confirmed (e.g., dc1)
Table: audit_lab.action_probe
Data: synthetic UUID, no production/customer records
Actors: CQL lab role, observer JMX identity, audit collector
Time: synchronized UTC within known tolerance
Expected output: incident report + action/evidence ledger
Forbidden: stop node, disable auth/TLS, production keys,
           delete hints/snapshots, force repair without lab approval
~~~

Nếu cluster chỉ một node thì dùng RF1; **không dùng lab RF1 chứng minh khả năng đạt quorum RF3 khi node Down**. Người không có quyền bật audit logging có thể làm phần tabletop bằng log mẫu, không cần xin credentials DBA production.

### 13.2. P0 — baseline và metrics coverage

Trên lab chỉ đọc:

~~~bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
nodetool info
nodetool status
nodetool describecluster
nodetool tpstats
nodetool compactionstats
nodetool getauditlog
~~~

Điền: source host/DC, Cassandra release, keyspace RF, số expected nodes vs JMX exporter targets, audit enabled/filter/dir, log collector heartbeat, last successful test alert notification, alert ruleset Git digest.

Mục đích P0 là có baseline và xác nhận đúng lab; không đưa `nodetool status` vào trigger tự động làm restart node.

### 13.3. P1 — chứng minh CQL audit

Dùng schema synthetic ở mục 8.6, trong môi trường có permission:

~~~sql
-- Bảng chỉ có trong isolated lab:
CREATE TABLE IF NOT EXISTS audit_lab.action_probe (
  id uuid PRIMARY KEY, note text
);

-- Một DDL có kiểm soát để test audit category DDL:
ALTER TABLE audit_lab.action_probe ADD audit_marker text;
~~~

**Chỉ chạy một lần khi column chưa tồn tại.** `ALTER TABLE` có tác động schema nên phải có lab approval và preflight `DESCRIBE TABLE`; không dùng trên shared/production keyspace. Nếu không được sửa schema, dùng `CREATE TABLE` mới với tên run-specific thay cho ALTER trên table đã có.

Thu:

1. Actual coordinator hostname và UTC trong CQL client session nếu có.
2. Cassandra audit record category `DDL` với user/scope/operation đã redact.
3. Command wrapper/CI approval và source terminal/session logs.
4. Schema agreement/metadata sau thao tác và mismatch nếu có.
5. Khi sử dụng filter chỉ DDL/DCL/AUTH, xác minh các `SELECT`/`INSERT` thông thường không xuất hiện như đã thiết kế; đó là coverage decision, không phải lỗi.

### 13.4. P2 — chứng minh nodetool không nằm trong CQL audit

Chạy `nodetool status` **qua approved READ wrapper** trong lab. Dự kiến:

~~~text
ACTION_LEDGER:
  action_id=ACT-LAB-002, type=READ, command=nodetool status
  actor=observer, target=cass-lab-a/N1, result=SUCCESS

CASSANDRA_CQL_AUDIT:
  no corresponding nodetool command event expected

HOST_OR_WRAPPER_AUDIT:
  actor, process, invocation time, exit code present
~~~

**Không tìm thấy record ở CQL audit là hành vi đúng thiết kế, không phải chứng minh nodetool không được chạy.** Chỉ khi wrapper/host audit cũng không có event mới đánh dấu `ADMIN_AUDIT_GAP`. Dữ kiện từ shell history đơn lẻ không đủ làm bằng chứng compliance vì có thể bị sửa/xóa và không ghi đầy đủ stdin/actor.

### 13.5. P3 — kiểm cảnh báo bằng chuỗi metric giả lập

Không cần dừng node thật: dùng Prometheus rule unit test hoặc replay sample time series vào môi trường sandbox. Ví dụ:

| UTC | API traffic | HTTP error rate | Cassandra read timeouts/s | Exporter Up | Dự đoán |
|---|---:|---:|---:|---:|---|
| 10:00 | 2.000/s | 0,02% | 0,00 | 1 | Không page |
| 10:05 | 2.100/s | 0,10% | 0,02 | 1 | Điều tra baseline |
| 10:10 | 2.000/s | 2,00% | 0,40 | 1 | Error budget burn, responder notified |
| 10:12 | 2.100/s | 2,20% | 0,43 | 1 | Confirm sustained condition |
| 10:17 | 2.050/s | 0,03% | 0,00 | 1 | Chờ clear per window/for |
| 10:20 | 0/s | N/A | N/A | 0 | Telemetry unavailable, **không** kết luận healthy |

Giá trị hoàn toàn **giả lập** để kiểm logic. With `for: 5m`, cảnh báo timeout không nhất thiết fire ngay 10:10:00Z; phụ thuộc lúc evaluation và time series đủ window, không suy độ chính xác giây từ bảng.

Thu evidence của test notification: labels, severity, runbook link, receiver, fired/ack/clear UTC. Nếu alert không đến owner, test FAIL ngay cả khi PromQL expression đúng.

### 13.6. P4 — negative test fail-closed

Trong môi trường giả lập/chỉ lab:

- Cố submit change với `cluster_id=production` ngoài allowlist → `BLOCKED_WRONG_TARGET`, không tạo process.
- Cố chạy approved action sau khi approval hết hạn → `BLOCKED_APPROVAL_EXPIRED`.
- Mất audit sink trước EXECUTE → `BLOCKED_AUDIT_UNAVAILABLE`, không làm thay đổi.
- Mất connection giữa action start và command result → `OUTCOME_UNKNOWN`, không đánh dấu PASS.
- Một node không export audit logs sau rotate → cảnh báo `AUDIT_INGEST_GAP`, không tự xóa segments.

**Không tạo negative test bằng cách phá audit của production**. Dùng mock/fake transports trong runner test suite hoặc isolated lab objects có thể dọn.

### 13.7. Phiếu thực hành

| Evidence ID | Nguồn | UTC / scope | Điều chứng minh | Hạn chế |
|---|---|---|---|---|
| EV-01 | Target inventory | _điền_ | Lab target ID đúng | Không chứng minh permission |
| EV-02 | Prometheus unit test | _điền_ | Rule fire/clear theo samples | Không chứng minh prod exporter |
| EV-03 | Alertmanager receiver log | _điền_ | Notification đến đúng người | Không chứng minh mitigation |
| EV-04 | Cassandra audit | _điền_ | Lab DDL trên coordinator | Không chứa nodetool |
| EV-05 | Wrapper/OS audit | _điền_ | Actor chạy nodetool status | Không chứng minh data consistency |
| EV-06 | Change approval | _điền_ | Action có quyền và scope | Không chứng minh đã thực thi |
| EV-07 | Negative fail-closed | _điền_ | Wrong target/sink error bị chặn | Chỉ môi trường kiểm thử |

**PASS của lab** đòi đủ 7 loại bằng chứng hoặc lý do skip được thừa nhận cùng ảnh hưởng coverage; không ghi PASS nếu missing telemetry/notification. Câu trả lời chuẩn phải nêu được ranh giới giữa Cassandra CQL audit và action audit bên ngoài.

## 14. Sáu tình huống xử lý sự cố có lời giải

### 14.1. Case A — Quorum vẫn đạt nhưng một node Down

**Giả định:** RF3 trong dc1. N2 Down, N1/N3 vẫn trả ghi ở `LOCAL_QUORUM`. Node-down alert firing 2 phút, API p99 và success chưa bị ảnh hưởng.

**Đánh giá:** không nhất thiết là SEV1 vì hiện tại 2/3 natural replicas còn có thể đáp ứng quorum, nhưng đã mất một lớp dự phòng; nếu thêm một replica mất khả năng phục vụ thì write/read quorum có thể unavailable. Escalation theo tuổi outage, lịch hints/repair, write volume, node disk/GC và RTO khôi phục. Thu `nodetool status` từ nhiều nodes; không restart N1/N3 khi đang chỉ còn hai replicas phục vụ.

**Evidence:** node views, RF/CL, lost-redundancy alert, repair/backup/DB owner, incident status. **Không** ghi “node Down = data loss chắc chắn”.

### 14.2. Case B — Deployment mới và compaction backlog trùng thời điểm

**Giả định:** v28 tăng page size và số CQL requests/request; cùng lúc `Compaction.PendingTasks` trên N2 tăng. API v28 có p99 xấu, v27 tốt.

**Đánh giá:** lập affected/healthy cohorts theo app version, DC, query, coordinator, partition. Kiểm CQL attempts/request, driver throttling, N2 disk/GC và change timeline. H1: query regression ở v28; H2: N2 IO saturation; cả hai có thể đồng thời đúng. Trước khi auto-resolve bằng compaction throttle, kiểm giả thuyết H1 bằng canary/rollback được approve.

**Evidence:** deployment digest, CQL fingerprint không bind values, UTC p99/error, compaction metrics, approved mitigation, after checks. **Không** chọn root cause chỉ dựa temporal correlation.

### 14.3. Case C — CQL DCL thay đổi ngoài window

**Giả định:** app bắt đầu nhận `UnauthorizedException` sau 11:03Z. CQL audit thấy `REVOKE SELECT ON KEYSPACE ...` từ role operator trên một coordinator lúc 11:02Z, nhưng không có change ticket.

**Đánh giá:** xác định event có thật, actor/source IP, role/grants, affected service; đối chiếu SSO/cloud/OS và authorization changes. Raise security incident nếu thao tác ngoài quyền; cần approver trước khi restore permissions. Tránh cấp superuser rộng để giải quyết tạm.

**Evidence:** CQL DCL audit, external action ledger (nếu có), role/grant state, approvals, service recovery. **Không** log mật khẩu hoặc query literals nhạy cảm trong incident chat.

### 14.4. Case D — Audit logging “enabled” nhưng evidence mất

**Giả định:** JMX `AuditLogEnabled=true` trên N1, nhưng collector không ship được segments, local log quota đã quay vòng và xóa record 2 ngày trước. Alert chỉ nhìn enablement nên không bắn.

**Đánh giá:** cải tiến audit monitoring thành **enabled + ingestion lag + archive success + expected node coverage + oldest retained timestamp**. Review `max_log_size`, roll cycle, archive command, disk, KMS/permissions. Khôi phục observability theo security runbook; record `EVIDENCE_GAP` minh bạch.

**Không** kết luận “audit đủ” vì một Boolean, và không sửa/xóa audit files để dựng timeline giả.

### 14.5. Case E — Một DBA chạy nodetool repair bằng SSH riêng

**Giả định:** sau deployment, latency tăng; shell history một host có `nodetool repair -pr ks table`, Cassandra CQL audit không thấy record tương ứng.

**Đánh giá:** Cassandra audit không ghi `nodetool`, vì vậy absence of CQL audit **đúng thiết kế**. Thu OS/sudo/session recorder, process event, change ticket, JMX/repair logs và metrics. Kiểm repair scope, job status và IO impact. Nếu dùng shared OS identity, cần điều tra attribution bằng SSO/JIT logs chứ không đổ lỗi cho người có tên trong `sudoers`.

**Cải tiến:** bắt buộc privileged JMX actions qua wrapper/automation ledger, giảm direct SSH và phát hiện bypass. Không tạo giả event CQL để làm “đủ” compliance.

### 14.6. Case F — Cảnh báo im lặng vì thiếu dữ liệu

**Giả định:** exporter down 10 phút, Prometheus panel cho ReadTimeouts = 0 sau phép `or vector(0)` trong dashboard; API vẫn trả 504. On-call tưởng Cassandra đã khỏe.

**Đánh giá:** phép `or vector(0)` có thể thay missing series bằng zero; không dùng nó như bằng chứng healthy nếu chưa chứng minh node đã scrape thành công. Tạo alert inventory mismatch/`up==0` và synthetic service requests; trong incident ghi `TELEMETRY_UNAVAILABLE`.

**Điểm học:** hệ giám sát là hệ thống phân tán thứ hai, có thể thất bại cùng Cassandra; “sự vắng mặt của dữ liệu” cần được quan sát riêng.

### 14.7. So sánh nhanh

| Case | Đâu là tín hiệu ban đầu? | Cần chứng cứ nào ngoài Cassandra metrics? |
|---|---|---|
| A | N2 Down, quorum còn | RF/CL, on-call notes, repair/backup state |
| B | p99 v28 + compaction | Deployment/code diff, driver traces, approvals |
| C | Unauthorized error | CQL audit DCL, SSO/role/change ticket |
| D | Missing audit archives | Collector/KMS/cloud audit, archive health |
| E | Repair qua SSH | Host/JMX/SSH process audit, repair status |
| F | Dashboard fake green | Exporter inventory, scrape gaps, API SLO |

## 15. Báo cáo incident, postmortem và kiểm soát runbook

### 15.1. Mẫu báo cáo thực tế

~~~markdown
# INC-... — Cassandra symptom / remediation audit

## Summary
- Severity/status: INVESTIGATING / MITIGATED / RESOLVED
- Last known good UTC: ... (source and uncertainty)
- First known bad UTC: ... (source and uncertainty)
- Alert firing/acknowledgement UTC: ...
- User impact: service/error%/p99/affected operations

## Technical scope
- Cassandra version, cluster, DC/rack/node IDs:
- RF, effective read/write CL, Java Driver/execution profile:
- Keyspace/table/CQL fingerprint (redacted):
- Affected vs healthy control cohorts:
- Telemetry health and missing series:

## Hypotheses
- H1: prediction / falsifier / evidence / confidence
- H2: prediction / falsifier / evidence / confidence

## Administration changes
- Change ID, requester, approver, approved window:
- Operation type, sanitized args, target host ID:
- Execution start/end UTC, exit/signal, action_id:
- BEFORE/AFTER evidence, stop/rollback outcome:
- Cassandra CQL audit vs external action logs:

## Verification
- User SLO at representative offered traffic:
- CL/replica health, repair/hints/backup state:
- Unknown writes, TTL/tombstone risks:
- Audit/metrics/log ingestion gaps:

## Next steps
- Owners, deadlines, runbook/change links:
- Residual risks and next scheduled update:
~~~

Không khẳng định `root cause=confirmed` chỉ vì latency giảm sau restart, khi chưa kiểm mechanism và các biến đồng thời. Một báo cáo tốt chỉ rõ **đã quan sát gì, suy gì, chưa biết gì**.

### 15.2. Khi nào incident được coi RESOLVED?

| Trục | Điều kiện kiểm |
|---|---|
| Người dùng | Error/success + latency SLO hồi phục với traffic đại diện |
| Client | Retry/throttle/pool errors ổn, request CL phù hợp |
| Cassandra | Node/DC health, pending tasks, disk/GC/network headroom |
| Dữ liệu | UNKNOWN writes, stale reads, repair/TTL risks xử lý hoặc có owner |
| Audit | Action evidence sealed, critical gaps được ghi và escalated |
| Vận hành | Mitigation config có owner/expiry/rollback, runbook cập nhật |

**Alert cleared ≠ incident resolved.** Một sự cố consistency có thể còn tiếp diễn dù API trả 200; node `UN` không chứng minh mọi replica đồng bộ và repair một table không bảo đảm tất cả keyspaces.

### 15.3. Mười câu hỏi postmortem

1. Phát hiện trễ bao lâu so với first-bad? Do `for`, scrape/ingestion, silence hay thiếu coverage?
2. Page có đủ owner, cluster/DC, RF/CL, runbook không?
3. Dashboard có unit/labels sai hoặc p99 được average sai không?
4. Thay đổi có approval nhưng không có execution record, hoặc ngoài window?
5. Có shared accounts làm attribution không rõ?
6. Cassandra audit filter quá hẹp hoặc mất logs do local quota?
7. Có thiếu admin/JMX/SSH/Kubernetes events không?
8. Mitigation đã chứng minh data integrity hay chỉ giảm traffic?
9. Runbook nào lỗi thời/không đúng Cassandra version?
10. Action items nào có fixture test và owner để kiểm lại?

Postmortem nên **không đổ lỗi cá nhân** mà cải thiện controls, training, runbooks và automation. Nếu không biết root cause, công bố `ROOT_CAUSE_UNRESOLVED` cùng hypotheses còn lại.

### 15.4. Đo mức trưởng thành của chương trình

| Chỉ số | Vì sao quan trọng |
|---|---|
| % paging alerts có valid runbook URL + owner | Page phải hành động được |
| MTTD / MTTA / MTTR theo service tier | Phân biệt phát hiện, xác nhận, phục hồi |
| False-page rate / repeat incidents | Giảm noise mà không che sự cố |
| % privileged actions có change/action IDs | Audit coverage control plane |
| % high-risk actions có dual approval | Enforcement thực thay vì policy |
| Audit ingestion lag / missing-node count | Đo completeness của bằng chứng |
| % runbooks reviewed/tested trong window | Tránh tri thức lỗi thời |
| % incidents có user impact + integrity gate | Không đóng sự cố vì metric xanh |

MTTR thấp nhờ giảm CL hoặc tắt security không phải thành tích nếu data integrity bị vi phạm. Mọi KPI đi cùng guardrails safety, error budget và sampling coverage.

### 15.5. Version hóa runbook sau incident

~~~text
Observe: one triage step was misleading or unsafe
Propose: runbook diff with a test incident fixture
Review: DBA + SRE + Security for privileged changes
Simulate: isolated lab/tabletop with observed output
Release: signed version, changelog, on-call notification
Measure: lower time-to-diagnosis without higher data risk
~~~

Không chuyển một workaround từ incident cũ thành auto-remediation cho mọi request cùng exception class. `WriteTimeoutException` không có nghĩa mutation chưa được áp dụng; retry không idempotent có thể làm sai dữ liệu.

## 16. Bài tập, câu hỏi tình huống và checklist trực ca

### Bài 1 — Cassandra audit có ghi nodetool không?

DBA chạy `nodetool repair -pr ks table`; CQL audit không có entry tương ứng. Có thể kết luận lệnh không chạy?

**Đáp án:** không. Cassandra audit logging ghi CQL/auth trên coordinator, **không ghi `nodetool`**. Cần external action ledger, host OS/JMX/session logs và repair status để xác định tác nhân/thao tác/kết quả.

### Bài 2 — Một node Down là SEV1?

Cluster RF3 một DC, N2 Down, service ghi `LOCAL_QUORUM` vẫn thành công. Cảnh báo node Down nhất định phải là SEV1?

**Đáp án:** không tự động. Dự phòng đã suy giảm, nhưng quorum có thể còn đáp ứng. Severity phụ thuộc business SLO, remaining replicas, repair/hints/downtime và rủi ro node thứ hai mất; cần escalations theo thời gian và khả năng phục hồi.

### Bài 3 — Dashboard xanh vì missing data

Exporter Down, mọi Cassandra timeouts series biến mất và panel mặc định hiển thị zero. Có thể đóng incident?

**Đáp án:** không. Phải ghi `TELEMETRY_UNAVAILABLE`, xác minh exporter/inventory, xem user-facing SLI, logs và synthetic requests; không đánh đồng missing series với zero events.

### Bài 4 — Average của p99

N1 p99 12ms với 20.000 requests; N2 p99 500ms với 100 requests. Operator lấy (12+500)/2 để công bố cluster p99.

**Đáp án:** sai toán học. Percentile của hỗn hợp phải tính từ phân phối/histogram samples có cùng semantics; không lấy trung bình các p99 hoặc cộng p99 driver + coordinator + network.

### Bài 5 — CQL role bị REVOKE ngoài lịch

App gặp UnauthorizedException, CQL audit DCL có `REVOKE` trước first-bad nhưng thiếu change ticket. Hành động đầu tiên?

**Đáp án:** bảo quản audit record/source/UTC, xác minh role/grants và attribution, mở security/change incident, kiểm approved state, rồi rollback permissions theo policy nếu được duyệt. Không cấp superuser tùy tiện hoặc lộ passwords.

### Bài 6 — HintsSucceeded và data convergence

Node vừa trở lại `UN`, `HintsSucceeded` tăng. Điều đó chứng minh mọi replica đã đồng bộ?

**Đáp án:** chưa. Hints là best effort; có thể không được lưu do max hint window, failed delivery, hoặc còn mismatch ngoài vùng đọc. Cần kiểm holders/targets, repair history, data/CL semantics và integrity.

### Bài 7 — Audit log chỉ ở một node

Cassandra RF3, CQL INSERT được ACK bởi hai replicas; auditor đòi ba audit entries, mỗi replica một bản. Đúng?

**Đáp án:** sai. CQL audit event được ghi trên coordinator tiếp nhận request; nó không được replication theo RF. Cần thu log từ mọi coordinators có thể nhận request, không theo natural replica count.

### Bài 8 — Bật audit trên N1 là đủ?

`nodetool getauditlog` tại N1 cho thấy enabled, còn N2/N3 không biết. Cluster có thể tuyên bố audit coverage đầy đủ?

**Đáp án:** chưa. Audit setting và runtime enablement **per-node**; phải kiểm mỗi coordinator, filters, logdir, archive/collector và retention. Một Boolean enabled không chứng minh evidence có thể truy xuất.

### Bài 9 — Retry repair sau runner crash

CI runner chạy `nodetool repair`, sau đó mất kết nối và không nhận exit code. Có nên auto-retry toàn bộ lệnh ngay?

**Đáp án:** không. Repair có thể vẫn chạy hoặc đã hoàn tất phần dữ liệu; cần đọc server-side repair logs/job state, action ledger và resource budget. Báo `OUTCOME_UNKNOWN`, không duplicate workload mù.

### Bài 10 — Disk alert và snapshot hardlink

Dashboard nói thư mục snapshots “500 GiB”, disk chỉ còn 5 GiB; operator đề xuất `clearsnapshot` để lấy lại 500 GiB.

**Đáp án:** không thể suy dung lượng sẽ được giải phóng vì SSTable hardlinks chia sẻ blocks. Cần xác minh backups/retention, compaction needs và disk accounting; việc xóa snapshot chỉ theo runbook có approval.

### Bài 11 — Page sau khi for 5 phút

First-bad ở bucket 10:00–10:01Z; alert fire 10:06Z. Ghi onset 10:06Z có hợp lệ?

**Đáp án:** không. Đây là notification time sau evaluation và for; onset được ước lượng theo last-good/first-bad và độ phân giải metrics, ghi uncertainty.

### Bài 12 — Silence trong maintenance

Nhóm tắt toàn bộ alerts Cassandra trong một tháng để tránh nhiễu lúc migration. Hậu quả?

**Đáp án:** có thể che disk/full replica failures không liên quan migration, bỏ lỡ SLO breach và ảnh hưởng compliance. Silence phải hẹp theo cluster/alert/window, có approval/change ID, owner/expiry và alert đặc biệt cho mất telemetry.

### Bài 13 — Lệnh thành công nhưng người dùng vẫn lỗi

`nodetool cleanup` trả exit code 0, nhưng API 5xx và p99 vẫn vượt SLO; có được ghi incident RESOLVED?

**Đáp án:** không. Exit 0 là kết quả của command trong scope, không phải xác minh end-to-end service readiness. Phải kiểm app/driver/coordinator metrics, actual CL, offered traffic và correctness.

### Bài 14 — Kết quả CQL audit thiếu PREPARE hoặc bound values

Ứng dụng dùng prepared statement; audit có CQL lúc prepare nhưng không có literal bind values. Có phải lỗi parser?

**Đáp án:** không nhất thiết. Audit logging prepared statements có semantics không ghi bound values trong EXECUTE; kiểm docs release/logger/filter. Đừng bật full query log trên toàn production chỉ để lấy PII. Muốn business identity, dùng operation ID/hashes được thiết kế an toàn ở application layer.

### Bài 15 — Audit enabled nhưng archive thất bại

Node đã bật audit, nhưng local segments cũ bị rotation trước khi collector lấy. Compliance có thể tuyên bố “không mất log”?

**Đáp án:** không. Phải ghi evidence gap, điều tra archiver/disk/retention/collector, sửa pipeline theo security approval và test query từ mọi coordinator. Monitoring cần phát hiện **ingestion lag và missing segments**, không chỉ enabled state.

### Bài 16 — Break-glass nhưng không có change ticket

Một node disk full nghiêm trọng, on-call cần thao tác cấp cứu nhưng approval service tạm unavailable. Cách đúng?

**Đáp án:** thực hiện theo **break-glass process đã được phê duyệt trước**, xác nhận actor/target, ghi session/offline evidence tối đa có thể, có escalation, hạn quyền và post-facto review. Không dùng “khẩn cấp” như quyền bỏ qua mọi audit và không tạo log giả sau đó.

### Checklist cho tác giả cảnh báo

- [ ] Tín hiệu liên quan user SLO, data correctness hoặc nguy cơ vận hành cụ thể.
- [ ] Có owner, severity, labels gọn, runbook URL hoạt động.
- [ ] Đã phân biệt app, Driver và Cassandra exception/latency semantics.
- [ ] Threshold/for/traffic floor dựa baseline, không dùng con số minh họa.
- [ ] Mapping JMX→exporter, units, counter reset được xác minh.
- [ ] Không lộ customer/partition/request IDs trong metric labels.
- [ ] Test no-traffic, missing-series, node restart, scrape gap, stale metrics.
- [ ] Test Alertmanager route, ack, escalation, silence expiry.
- [ ] Có meta-monitoring cho audit collector và exporter.
- [ ] Alert rule change có Git diff, reviewer, rollback.

### Checklist cho người trực ca

- [ ] Ghi UTC, last-known-good/first-known-bad và window uncertainty.
- [ ] Xác minh user-facing impact: errors, p95/p99, traffic và data risk.
- [ ] Biết RF/CL/DC, cluster/release/node IDs và affected cohorts.
- [ ] So CQL error classes, Driver pool/timeout, coordinator metrics.
- [ ] Thu before evidence ở mức đủ mà không làm chậm mitigation khẩn cấp.
- [ ] Xem changes/deploys và admin actions có hiệu lực trong incident window.
- [ ] Viết giả thuyết với prediction/falsifier, không khẳng định từ correlation.
- [ ] Không tự restart nhiều replicas, giảm CL, xóa hints/snapshots hay repair mù.
- [ ] Nếu action state-changing, kiểm allowlist, approval, rollback và audit sink.
- [ ] Ghi EXECUTED và VERIFIED riêng, không coi exit 0 bằng data correctness.
- [ ] Đảm bảo alert clear đi cùng SLO/consistency và telemetry healthy.
- [ ] Bàn giao root cause confidence, residual risks, owner và next update.

### Checklist cho người kiểm toán

- [ ] Thu CQL audit từ **mọi coordinators**, không chỉ một node.
- [ ] Kiểm runtime enabled, category/role/keyspace filters, archive và retention.
- [ ] Đối chiếu `nodetool`/JMX/SSH/Kubernetes/cloud qua external audit sources.
- [ ] Liên kết change ID, action ID, actor, approver, target, UTC và command fingerprint.
- [ ] Kiểm privileges tối thiểu, no shared admin identities khi có thể.
- [ ] Có evidence BEFORE/AFTER và log output được redact đúng policy.
- [ ] Báo mọi EVIDENCE_GAP, clock skew hoặc missing-node metrics.
- [ ] Audit store có integrity, retention, key recovery và separation of duties.
- [ ] Có record khi policy audit/silence thay đổi và khi emergency break-glass.
- [ ] Báo cáo PASS/FAIL có scope/limitations, không suy rộng từ sample lab.

## 17. Tài liệu tham khảo

Các đường dẫn là **tài liệu chính thức hoặc trang thông số của công cụ liên quan**. Cần chọn đúng Cassandra release/Java Driver/Prometheus version đang vận hành trước khi áp dụng cú pháp. Không sao chép ví dụ cấu hình lab thành production policy mà chưa có review.

1. Apache Cassandra — [Audit Logging (4.0+)](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/auditlogging.html): scope CQL/auth, **không ghi nodetool/cassandra.yaml**, coordinator-only audit, filters, `BinAuditLogger`, archive và viewer.
2. Apache Cassandra — [Audit Logging (overview)](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/audit_logging.html): categories `DDL/DCL/DML/AUTH/ERROR/PREPARE/QUERY` và prepared statements.
3. Apache Cassandra — [Monitoring Metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): Dropwizard/JMX metrics theo node, ClientRequest, ThreadPools, Compaction, CommitLog, DroppedMessages, table histograms.
4. Apache Cassandra — [cassandra.yaml Configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `audit_logging_options`, runtime/config options, JVM/storage parameters.
5. Apache Cassandra — [nodetool Overview](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/nodetool.html): phân biệt các lệnh status/metrics và lệnh làm thay đổi cluster.
6. Apache Cassandra — [nodetool help](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/help.html): cú pháp command theo đúng phiên bản.
7. Apache Cassandra — [nodetool getauditlog](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/getauditlog.html): kiểm cấu hình audit logging runtime.
8. Apache Cassandra — [nodetool enableauditlog](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/enableauditlog.html) và [disableauditlog](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/disableauditlog.html): thay trạng thái audit cần approval/rollout theo node.
9. Apache Cassandra — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy, incremental/full repair, primary ranges, IO và `gc_grace_seconds`.
10. Apache Cassandra — [nodetool repair](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/repair.html): `--full`, `-pr`, `--preview`, `--validate`, phạm vi và rủi ro.
11. Apache Cassandra — [Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hinted handoff best effort, failure/backlog và delivery metrics.
12. Apache Cassandra — [Compaction and Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): TTL/deletion/grace, tránh repair mù khi có nguy cơ resurrection.
13. Apache Cassandra Java Driver 4.19 — [Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): phân biệt timeouts, unavailable và unknown write outcomes.
14. Apache Cassandra Java Driver 4.19 — [Metrics](https://apache.github.io/cassandra-java-driver/4.19.0/core/metrics/): session/node metrics, pool capacity và disabled-by-default metrics.
15. Apache Cassandra Java Driver 4.19 — [Tracing](https://apache.github.io/cassandra-java-driver/4.19.0/core/tracing/): request/query trace và overhead khi lấy mẫu.
16. Prometheus — [Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): expressions, `for`, `keep_firing_for`, labels/annotations.
17. Prometheus — [Alerting Best Practices](https://prometheus.io/docs/practices/alerting/): symptom-based alerts, user-visible impact và tránh noise.
18. Prometheus — [PromQL Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate`, `increase`, handling counter reset và histogram functions.
19. Prometheus Alertmanager — [Configuration](https://prometheus.io/docs/alerting/latest/configuration/): routing, grouping, inhibition và receiver configuration.
20. Kubernetes — [Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/): API request audit events cho thao tác scale/rollout/cluster resources nằm ngoài Cassandra native audit.

**Tổng kết:** Một cảnh báo tốt phải gắn với **đúng triệu chứng, đúng người nhận, đúng runbook và đủ telemetry**. Một runbook tốt phải có **preflight, phép kiểm tra ít tác động, ranh giới phê duyệt, stop/rollback và kiểm chứng data correctness**. Một hành động quản trị tốt phải để lại **chuỗi chứng cứ độc lập** — ai phê duyệt, ai thực thi, trên target nào, lúc nào, kết quả ra sao và ảnh hưởng tới người dùng. Cassandra CQL audit chỉ là **một thành phần** trong chuỗi đó; không thể tự thay thế ghi nhật ký `nodetool`, hệ điều hành, CI/CD và control plane.
