# Cảnh báo có thể hành động và giảm thông báo trùng không hữu ích trong NoSQL

## 1. Tình huống mở đầu: 2.000 thông báo nhưng không ai biết cần làm gì

Một hệ thống đặt hàng Java sử dụng MongoDB để lưu đơn, Redis làm cache, Cassandra lưu sự kiện và một pipeline CDC cập nhật read model. Trong một sự cố mạng kéo dài 10 phút, hệ giám sát phát:

```text
09:01  CRITICAL mongo_connection_error pod-01
09:01  CRITICAL mongo_connection_error pod-02
09:01  CRITICAL mongo_connection_error pod-03
09:02  CRITICAL api_500_rate pod-01
09:02  CRITICAL api_500_rate pod-02
09:02  WARNING  redis_cache_miss_high pod-03
09:02  CRITICAL cdc_consumer_lag partition-00
09:02  CRITICAL cdc_consumer_lag partition-01
...
09:10  > 2.000 notifications across 30 pods
```

Số lượng thông báo lớn không chứng minh hệ quan sát tốt. Người trực vận hành không biết **tín hiệu nào là nguyên nhân, tín hiệu nào là hậu quả, ai sở hữu sự cố và thao tác đầu tiên là gì**. Đến lúc tìm được vấn đề mạng, hệ đã mất nhiều thời gian phản ứng.

Một cấu hình tốt hơn có thể tạo:

```text
[PAGE] orders-write-path: write availability SLO burning rapidly
   affected: prod / ap-southeast / orders
   impact: 35% write attempts failing for 8 minutes
   suspects: MongoDB primary connectivity / node routing
   owner: Orders On-call
   runbook: /runbooks/orders-write-unavailable
   related: 19 child symptoms grouped under this incident
```

Không phải **mọi lỗi database** đều phải bật chuông lúc 3 giờ sáng. Cảnh báo khẩn chỉ có ích khi người nhận **cần hành động sớm, biết cách kiểm chứng tác động và có quyền/công cụ xử lý**.

Bài học này thuộc chương **Quan sát và chẩn đoán** trong module **Database No SQL**. Trọng tâm là thiết kế **actionable alerts**, định tuyến đúng người, giảm nhiễu và thông báo trùng, nhưng **không làm biến mất những sự cố độc lập hoặc che mất cảnh báo quan trọng**.

## 2. Mục tiêu học tập

Sau bài, bạn cần có thể:

1. Phân biệt metrics, logs, traces, events, dashboards và **alerts**.
2. Viết cảnh báo theo **triệu chứng ảnh hưởng người dùng** thay vì chỉ theo ngưỡng hạ tầng.
3. Xây dựng **SLI/SLO/error budget** phù hợp các luồng NoSQL: đọc/ghi, cache, replication, CDC.
4. Phân loại **page-now, ticket, informational** dựa trên tác động, khẩn cấp và khả năng hành động.
5. Chọn đúng điều kiện, cửa sổ đo, ngưỡng, thời gian duy trì, hysteresis và độ nhạy khi traffic thấp.
6. Thiết kế **grouping, deduplication, inhibition, routing, silencing** và correlation theo quan hệ nguyên nhân–hậu quả.
7. Tránh dùng nhãn metric hoặc alert có cardinality rất lớn như `userId`/`orderId`/raw key.
8. Đặt runbook, owner, dashboard, query và các bước an toàn trong mỗi alert.
9. Hiểu ví dụ NoSQL cụ thể: MongoDB elections, Redis evictions, Cassandra tombstones/compaction, DynamoDB throttling, CDC backlog, search index lag.
10. Kiểm thử cảnh báo trong tình huống failover, mất dữ liệu quan sát, deployment, incident trùng lặp và phục hồi.

## 3. Cảnh báo không phải dashboard có âm thanh

Một metric:

```text
mongodb_connections_current = 300
```

chỉ là một quan sát. Để biến nó thành alert, cần câu trả lời:

- **300 có bất thường với pool/server này không?** Giới hạn và baseline là gì?
- **Ai bị ảnh hưởng?** Số request lỗi hoặc chờ connection có tăng không?
- **Nếu không hành động trong 10 phút, điều gì xảy ra?**
- **Ai chịu trách nhiệm?** Đội database, ứng dụng, networking hay platform?
- **Hành động đầu tiên là gì?** Kiểm tra pool leaks, slow queries, release gần nhất hay scale?
- **Tín hiệu tự hết sau vài giây có cần đánh thức ai không?**

### Phân biệt công cụ quan sát

| Công cụ | Trả lời tốt | Không tự thay thế |
|---|---|---|
| Metric | Mức độ, xu hướng, tần suất, saturation | Nguyên nhân từng request |
| Log | Một sự kiện/lỗi cụ thể, structured context | Đánh giá mọi traffic có bị ảnh hưởng |
| Trace | Request đi qua các dịch vụ và chờ ở đâu | SLO toàn hệ trên mọi request |
| Dashboard | Khám phá và đối chiếu nhiều signals | Quyết định on-call có phải thức dậy |
| Audit/event history | Ai thay đổi cấu hình, failover, migration | Trạng thái tức thời của khách hàng |
| Alert | Khi nào cần con người/hệ tự động can thiệp | Mọi dữ liệu chẩn đoán chi tiết |

**Một dashboard tốt có thể chứa hàng trăm biểu đồ. Một hệ paging tốt nên chỉ có một tập nhỏ tín hiệu thực sự hành động được.**

## 4. Định nghĩa actionable alert

Một cảnh báo có thể hành động nên chứa:

```text
Condition    : Write success rate below SLO / error budget rapidly burning
Scope        : prod, region, service, tenant class (when justified)
Impact       : 24% writes failed for 5m
Severity     : page
Owner        : Orders on-call
Next action  : Check write route, driver pool, DB primary/topology, recent changes
Runbook      : Link with diagnosis, mitigation and rollback
Evidence     : Dashboard, logs/traces exemplar, query labels
Escalation   : If unresolved after policy-defined time
Resolution   : Recovery condition and closure behavior
```

### Một phép thử đơn giản

Hỏi: “Nếu cảnh báo này đến lúc 02:00, người trực có cần và có thể làm gì ngay không?” Nếu câu trả lời là **không**, rất có thể nó nên là:

- Tín hiệu trên dashboard.
- Log hoặc event timeline.
- Ticket được xử lý giờ làm việc.
- Bằng chứng bổ sung trong một incident khác.

Điều này không có nghĩa mọi vấn đề ít khẩn đều bỏ qua. **Đổi kênh xử lý** là khác với xóa tín hiệu.

## 5. Alert từ tác động người dùng trước, hạ tầng sau

Hai câu:

> “Disk usage Redis là 80%.”

> “Cache read p99 tăng gấp ba và database fallback đang gây write latency vượt ngưỡng SLO.”

Câu thứ hai nói rõ hơn **tác động**. Nhưng metric disk ở 80% vẫn rất hữu ích nếu theo dự báo đĩa sẽ đầy trước khi con người kịp xử lý.

### Hai tầng cảnh báo

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| **Symptom/SLO** | Người dùng hoặc pipeline quan trọng đang hỏng không? | Write error ratio, read p99, CDC freshness lag |
| **Cause/capacity** | Điều gì gây ra hoặc sắp gây hỏng? | Disk exhaustion forecast, pool wait, Redis evictions, replica lag |

Symptom thường dùng để **page đội sở hữu service**. Cause/capacity giúp **chẩn đoán, phòng ngừa và route đúng nhóm**. Một capacity alert cũng có thể được page độc lập nếu sự cố sắp xảy ra và cần hành động trước khi người dùng bị ảnh hưởng.

### Không đánh đồng availability với mọi nhu cầu dữ liệu

Một API vẫn trả HTTP 200 nhưng cache trả đơn cũ 30 phút là **freshness incident**. CDC im lặng và MongoDB write path còn hoạt động không có nghĩa analytics/search projection đúng. Phải đo **tính đúng và độ mới theo contract**.

## 6. SLI, SLO và error budget trong NoSQL

**SLI** (*Service Level Indicator*) là phép đo chất lượng; **SLO** (*Service Level Objective*) là mục tiêu; **error budget** là phần sai lệch được phép.

### Ví dụ SLI cho đường đọc

\[
\mathrm{ReadSuccessRatio} =
\frac{\mathrm{successful\ valid\ reads}}
{\mathrm{eligible\ read\ requests}}
\]

Phải định nghĩa “eligible” và “successful”:

- Có tính lỗi caller input 400 vào denominator không?
- Read timeout sau deadline có tính failed không?
- Trả document sai tenant có được tính success không? **Không thể chỉ dựa vào HTTP 200.**
- 404 hợp lệ có tính success của API không?
- Read từ replica stale vượt mức cho phép có tính valid read không?

### Ví dụ latency SLI

```text
99% successful order reads complete within 200 ms
```

Cần đo trên distribution phù hợp và giới hạn scope. SLO latency dạng “tỷ lệ requests dưới threshold” thường dễ tính error budget hơn việc chỉ báo một giá trị p99 đã aggregate sai.

### Ví dụ freshness SLI

```text
99.9% committed order changes appear in search within 60 seconds
```

Cần đo từ source commit/revision đến **search-visible**, không chỉ đến lúc Kafka consumer poll.

### Error budget

Với SLO availability 99.9% trong 30 ngày, error budget theo thời gian tương đương:

\[
30\text{ ngày}\times(1-0.999)=0.03\text{ ngày}
=43.2\text{ phút}
\]

Đây là cách diễn giải theo thời gian **khi mọi khoảng có trọng số như nhau**. SLO dựa trên số requests có error budget theo số requests, không tự đổi thành phút outage nếu traffic biến thiên.

## 7. Burn rate: cảnh báo khi đang tiêu nhanh error budget

Nếu SLO 99.9%, tỷ lệ lỗi ngân sách:

\[
e_{\mathrm{budget}}=1-0.999=0.001
\]

Nếu cửa sổ 5 phút có 1% requests lỗi:

\[
\mathrm{BurnRate} = \frac{0.01}{0.001}=10
\]

Nghĩa là **ngân sách đang bị tiêu với tốc độ gấp 10 lần mức trung bình cho phép** trong cửa sổ đó.

### Vì sao burn rate tốt hơn một ngưỡng 5xx duy nhất?

```text
Service A: 10 errors / 100 requests   = 10%
Service B: 10 errors / 100000 requests = 0.01%
```

Ngưỡng “10 errors” đánh đồng hai tác động. Tỷ lệ phản ánh đúng hơn, nhưng ở traffic rất thấp nó lại dễ nhảy mạnh. Phải dùng **minimum traffic/coverage guard** và cửa sổ phù hợp.

### Multi-window burn-rate alerts

Để giảm nhiễu, một cảnh báo có thể cần **cả cửa sổ ngắn và dài** vượt threshold; ví dụ tham khảo cho SLO 30 ngày:

- Mức nhanh: burn rate cao ở **5 phút và 1 giờ**.
- Mức chậm: burn rate tăng liên tục ở **30 phút và 6 giờ**.
- Kênh xử lý khác nhau theo mức tác động và khả năng can thiệp.

Các ngưỡng như 14.4x hay 6x đôi khi được dùng trong thực hành SRE, nhưng **không là hằng số bắt buộc cho mọi SLO**. Cửa sổ, threshold và page/ticket phải được hiệu chỉnh từ budget, traffic và lịch sử thực.

## 8. Một alert cần định nghĩa mẫu đo trước khi viết ngưỡng

Ví dụ “tỷ lệ timeout tăng” mơ hồ nếu:

- Một request bị retry ba lần và ba lần timeout được tính như ba user requests.
- Cache hit không đi DB nhưng vẫn nằm trong denominator DB attempts.
- Kết quả HTTP 200 chứa application error.
- Query background export trộn chung với interactive query.
- 429 throttling do quota hoặc chủ động rate-limit bị gộp với 5xx database.

### Phân biệt cấp metric

| Metric | Nên hiểu |
|---|---|
| `http_requests_total` | Logical HTTP request nếu instrument đúng |
| `db_attempts_total` | Mỗi lần driver/handler thử DB, gồm retries |
| `db_logical_operations_total` | Logical DB operation của business |
| `db_retries_total` | Retry attempts theo nguyên nhân |
| `db_failures_total` | Thất bại theo phân loại |
| `db_pool_wait_seconds` | Chờ connection trước khi gọi DB |
| `db_command_duration_seconds` | Thời gian command được đo theo instrument |

**Đừng chia error của attempts cho tổng logical requests** nếu muốn một tỷ lệ có ý nghĩa rõ. SLO người dùng thường nên bắt đầu từ logical request / successful business outcome.

## 9. NoSQL có nhiều mức tác động cần phân biệt

Một database có thể “up” nhưng business vẫn hỏng:

```text
Database TCP reachable?                  YES
Read requests successful?                YES
Write quorum available?                  NO
Critical orders fresh enough?            NO
Search read model caught up?             NO
CDC consumer offset advancing?           YES
User can complete checkout?              NO
```

Các chiều đáng đo:

1. **Availability:** client thực hiện read/write hợp lệ được không?
2. **Latency:** p95/p99 có vượt budget?
3. **Durability/acknowledgment:** write concern/quorum và commit outcome có đáp ứng?
4. **Freshness:** dữ liệu đọc/derived views có trễ quá hạn?
5. **Correctness:** checksum, reconciliation, invariant violations.
6. **Capacity:** disk, memory, IOPS, pool saturation, throttling.
7. **Recovery:** backup/PITR và replication/rebuild có còn khả dụng?

Một dashboard healthy CPU không làm các chiều kia tự khỏe.

## 10. Đặt mức độ ưu tiên theo khả năng hành động

Một chính sách minh họa:

| Mức | Điều kiện | Người nhận | Kỳ vọng |
|---|---|---|---|
| **P1 / Page** | Tác động lớn, đang xảy ra, cần can thiệp tức thời | On-call + escalation | Acknowledge và triage ngay |
| **P2 / Page** | Một đường quan trọng suy giảm nhanh hoặc resource sắp cạn trong thời gian rất ngắn | Owner on-call | Điều tra trước khi vượt SLO nghiêm trọng |
| **P3 / Ticket** | Vấn đề có thể xử lý trong giờ làm việc | Team backlog | Có owner và due policy |
| **Informational** | Thay đổi/trạng thái đáng lưu nhưng không cần tác động | Timeline/dashboard | Correlation, không đánh thức |

Đây chỉ là **ví dụ policy**, không phải bảng severity chuẩn toàn ngành. Một số tổ chức dùng SEV1/SEV2 theo mức thiệt hại thay vì urgency, hoặc dùng hệ hai chiều impact×urgency.

### Nguyên tắc

**Priority là hệ quả của tác động và thời gian phải phản ứng**, không phải mức hấp dẫn của metric. “Disk 80%” có thể là ticket; “disk dự kiến đầy sau 5 phút và không còn headroom cho recovery” có thể là page.

## 11. Alert title: không chỉ là “High Redis Memory”

So sánh:

**Kém hữu ích:**

```text
ALERT: Redis memory high
```

**Có thể hành động:**

```text
[P2] prod/checkout: Redis eviction rate rising while
cache hit ratio falls; MongoDB read p99 above 400 ms

Impact: checkout reads degraded
Owner: checkout-oncall
Runbook: /runbooks/cache-eviction
Dashboard: /dashboards/checkout-cache
```

Tên alert nên nói **đối tượng bị ảnh hưởng**, **triệu chứng chính** và **scope** ngắn gọn. Những bằng chứng phụ để trong annotations/runbook, không biến title thành một đoạn văn dài.

### Những trường cần có

- Stable alert name/ID.
- Service/system và environment.
- Cluster/region/shard scope khi thật sự cần.
- Severity, team owner và escalation policy.
- Summary và description sử dụng ngôn ngữ hành động.
- Dashboard, runbook, recent deployment/change timeline.
- Threshold, observed value và khoảng thời gian.
- Correlation key hoặc incident ID khi có.
- Thông tin bảo mật được redacted.

## 12. Owner là điều kiện để alert hữu ích

Một alert “Cassandra compaction backlog high” không có owner sẽ rơi vào nhiều nhóm:

```text
App team:  "DB team phải xem"
DB team:   "App query mới gây tải"
Platform:  "Server health vẫn xanh"
```

### Quy định trách nhiệm

| Loại tín hiệu | First responder minh họa | Có thể phối hợp |
|---|---|---|
| Orders write SLO | Orders on-call | DBA/SRE |
| MongoDB cluster primary unavailable | Database platform on-call | Orders/infra |
| Redis cache dependency degraded | Cache platform hoặc service owner theo hợp đồng | App team |
| Cassandra disk/compaction saturation | Cassandra platform | Ingest owners |
| DynamoDB write throttles | Table/workload owner | Cloud platform |
| CDC backlog and stale search | Pipeline/search owner | Source DB owners |
| Backup verification failure | Data protection owner | DBA/security |

Đây là phân chia tham khảo: **owner thật phải được ghi trong service catalog hoặc incident policy** và cập nhật khi team đổi.

### Alert không có người xử lý

Nếu không biết owner, không nên âm thầm bỏ metric; phải hoàn thiện service ownership/routing trước khi đưa cảnh báo vào kênh paging.

## 13. Runbook là một phần của alert contract

Một runbook tốt trả lời:

1. **Đây là tín hiệu gì?** Công thức, labels, nguồn dữ liệu.
2. **Khi nào báo động?** Threshold, cửa sổ, diễn giải false positives.
3. **Tác động nào?** Endpoints, tenants, consistency/freshness.
4. **Xác minh ra sao?** Dashboard, query, logs, traces, health probes.
5. **Những nguyên nhân thường gặp?** Disk, topology, code release, quota, index.
6. **Giảm tác động an toàn thế nào?** Rate-limit, fallback được phép, rollback, failover theo quy trình.
7. **Những việc không được làm?** Xóa data, flush cache toàn cụm, disable durability để “giải quyết” latency.
8. **Khi nào escalate?** Theo thời gian/symptom/thiếu quyền.
9. **Điều kiện phục hồi?** SLO ổn định, backlog giảm, replica/data correctness được xác minh.
10. **Sau sự cố làm gì?** Follow-up, alert tuning, postmortem.

### Runbook phải vận hành được khi control plane lỗi

Nếu dashboard/SSO/monitoring cùng phụ thuộc database đang hỏng, runbook chỉ trỏ vào dashboard không thể mở sẽ vô dụng. Cần phương án truy cập thông tin và lệnh đọc an toàn, kênh liên lạc độc lập, quyền khẩn cấp có audit.

## 14. Cửa sổ quan sát và thời gian duy trì điều kiện

Metric có thể tăng đột biến vì GC 3 giây, leader election hoặc một batch lớn. Cảnh báo tức thì:

```text
query latency > 300ms for one sample => PAGE
```

có thể gây nhiều false positives.

### Điều kiện bền

```text
latency p99 > threshold for 5 minutes
```

hoặc burn-rate trên hai cửa sổ có thể chống spikes. Nhưng nếu endpoint thanh toán **hoàn toàn ngừng hoạt động**, chờ quá lâu cũng gây hại.

### Cân bằng

- **Critical user-facing SLO:** phát hiện nhanh khi impact lớn.
- **Capacity warning:** cửa sổ dài hơn, dự báo thay vì threshold chớp nhoáng.
- **Election/failover thường lệ:** có thể chờ qua khoảng chuyển trạng thái đã biết.
- **Data corruption/security leak:** có thể page ngay từ một bằng chứng đủ tin cậy.

**Không dùng cùng `for: 5m` cho mọi loại tín hiệu** mà không xét cost of delay.

## 15. Hysteresis, debounce và flapping

Một metric liên tục quanh threshold:

```text
Time:    00 01 02 03 04 05 06
Value:   79 81 79 82 78 81 79
Alarm threshold: 80
```

Nếu mỗi lần crossing đều gửi notification mới, on-call nhận một chuỗi firing/resolved/firing.

### Hysteresis

Ví dụ:

```text
Enter alert: usage > 85% for 10m
Resolve:     usage < 75% for 15m
```

Ngưỡng đi vào và thoát khác nhau giúp giảm flapping. Hysteresis có thể được thực hiện qua rules/recording logic hoặc alert state engine, không phải Prometheus Alertmanager có sẵn một field `resolveThreshold` áp cho mọi nguồn.

### Debounce

Đợi trạng thái tồn tại đủ lâu trước khi gửi. Trong Prometheus rules, `for` là một cách yêu cầu biểu thức duy trì true; một số hệ có `keep_firing_for` để chống resolved quá nhanh sau những lần thiếu/chao metric, tùy phiên bản.

### Không giấu sự cố hồi phục rồi tái phát thật

Nếu alert đã resolved và **có một incident mới sau thời gian đủ dài**, hệ phải lại page đúng. Thiết kế chống flap không nên khóa vĩnh viễn hoặc mute mọi lần tái phát.

## 16. Traffic thấp: tỷ lệ lỗi rất dễ gây báo giả

Nếu 1 request trong 5 phút và request đó lỗi:

\[
\mathrm{errorRatio}=1/1=100\%
\]

Nhưng chỉ có một mẫu; tùy SLO, nó có thể quan trọng hoặc không đáng đánh thức on-call.

### Min-volume guard

Một rule có thể yêu cầu:

```text
errorRatio(5m) > 2%
AND requests(5m) >= 100
```

Nhưng cẩn thận: nếu service đang **mất hoàn toàn traffic do routing/outage**, `requests=0` khiến guard không phát. Cần một **availability/canary probe** hoặc no-traffic alert khi traffic được kỳ vọng phải có.

### Rate vs increase

Prometheus `rate` trên counters yêu cầu khoảng đủ samples và biết cách xử lý resets. `increase` dùng cho tổng số events trong cửa sổ; hai cái tương ứng với những cách diễn giải khác nhau. Với traffic ít, nhìn cả **số lượng** và **tỷ lệ**; không chỉ một tỷ lệ nhiễu.

### Phân khúc quá nhỏ

Alert theo từng user/tenant nhỏ có thể gần như luôn ở 0% hoặc 100%. Nên group theo service/region/tenant tier khi phù hợp, đồng thời có cơ chế phát hiện **tenant lớn bị lỗi riêng** mà không khiến metrics cardinality bùng nổ.

## 17. Ba câu hỏi trước khi giảm thông báo

Một đợt bùng nổ alerts có thể gồm:

1. **Cùng một alert lặp lại:** cùng đối tượng, cùng điều kiện, gửi nhiều lần khi vẫn đang firing.
2. **Nhiều alerts liên quan đến một incident:** một cluster lỗi khiến hàng trăm pods có connection errors.
3. **Những incidents độc lập xảy ra đồng thời:** một region mất kết nối, trong khi region khác bị đầy disk.

Ba trường hợp phải xử lý khác nhau:

| Tình huống | Cơ chế phù hợp | Rủi ro nếu làm sai |
|---|---|---|
| Cùng một instance alert lặp lại | Dedup và repeat interval | Gửi nhắc quá thường xuyên |
| Nhiều triệu chứng cùng một incident | Grouping/correlation/inhibition có điều kiện | Bão thông báo |
| Sự cố độc lập | Giữ incident/notification riêng | Gộp nhầm, che tác động khác |

**Mục tiêu không phải ít thông báo bằng mọi giá.** Mục tiêu là **mỗi thông báo mới mang thông tin hoặc yêu cầu hành động mới**, trong khi không mất khả năng phát hiện sự cố có hậu quả thật.

## 18. Deduplication: cùng một alert chỉ cần một sự kiện đang hoạt động

Một alert instance thường được nhận diện qua **tập labels**:

```text
alertname  = OrdersWriteSLOBurn
service    = orders
environment= prod
region     = ap-southeast
severity   = critical
```

Nếu mỗi lần evaluation gửi cùng một trạng thái firing, notification layer có thể nhận diện là **cùng một cảnh báo vẫn đang mở** và không tạo một page mới ở mỗi chu kỳ.

### Stable alert identity

Không nên cho vào **identity labels** những giá trị liên tục thay đổi:

```text
current_latency=487ms
error_count=172
timestamp=2026-11-14T10:01:23Z
request_id=...
```

Nếu mỗi lần evaluation đổi labels, alert engine có thể coi đây là **instance mới**, làm mất cơ chế `for`, reset state và phá dedup.

### Labels vs annotations

| Dùng cho labels ổn định | Dùng cho annotations/context |
|---|---|
| `service=orders` | `observed_error_ratio=8.2%` |
| `environment=prod` | `runbook_url=...` |
| `region=...` | `diagnostic_query=...` |
| `cluster=orders-mongo` | `observed_pool_wait=...` |
| `severity=critical` | `first_observed_time=...` |

Các giá trị động thường thích hợp ở **annotations**, dashboards và logs. Nhưng annotation thay đổi cũng có thể tạo thông báo update tùy notification policy; nên giới hạn refresh cần thiết.

### Lưu ý fingerprint

Một số alert systems tính fingerprint bằng toàn bộ labels. Thay `severity` từ warning sang critical có thể làm fingerprint khác, khiến hệ phát một instance mới; routing và correlation phải hiểu đây có thể là **cùng incident chuyển mức**, không phải hai lỗi độc lập.

## 19. Grouping: gom nhiều alert instances vào một thông báo

Ví dụ 30 pods cùng báo database errors:

```text
MongoClientConnectionErrors{service=orders,pod=app-01}
MongoClientConnectionErrors{service=orders,pod=app-02}
...
MongoClientConnectionErrors{service=orders,pod=app-30}
```

Nếu grouping theo:

```text
environment + service + region + incident class
```

on-call có thể nhận **một thông báo**:

```text
orders/prod/ap-southeast: 30 pods affected by DB connection errors
```

### Không group quá rộng

```text
group_by: [environment]
```

có thể gộp:

- MongoDB primary unavailable ở service orders.
- Redis eviction ở service recommendations.
- Cassandra disk full ở service analytics.

thành một notification cực dài, khó phân biệt owner và hành động.

### Không group quá chi tiết

```text
group_by: [alertname, pod, container, endpoint, shard, tenantId]
```

lại gần như mỗi alert là một group riêng: không giảm notification storm.

### Nguyên tắc chọn group key

Gom những cảnh báo mà **cùng một responder nên xử lý trong cùng một workflow**, giữ độc lập các scope có root cause hoặc owner khác nhau.

Ví dụ:

```text
group_by = [service, environment, region, alertname]
```

có thể là điểm bắt đầu; nếu alert ảnh hưởng toàn cluster, group theo `cluster` thay vì pod, nếu thật sự cùng owner.

## 20. Inhibition: chặn thông báo triệu chứng khi nguyên nhân đã rõ

Một sơ đồ:

```text
MongoDB primary unavailable
    |
    +--> Mongo connection errors on 30 pods
    |
    +--> Orders write 5xx / latency
    |
    +--> CDC source read failures
```

Khi root-cause alert đã xác nhận, có thể **không gửi page riêng cho một số low-level child alerts** đã được ghi nhận trong cùng incident.

### Hướng dẫn an toàn

- Inhibit những **triệu chứng phụ cùng scope và cùng nguyên nhân chắc chắn**.
- **Không tự động inhibit user-facing SLO alert** nếu nó là bằng chứng duy nhất hệ thật sự đang hỏng hoặc báo cho owner khác.
- Không suppress alert của region/cluster khác.
- Chỉ inhibit khi root alert thực sự firing/đủ tin cậy.
- Có timeout/recovery policy: khi root resolved, các child còn lỗi phải xuất hiện lại.
- Ghi nhận inhibited alerts trong dashboard/timeline dù không page.

### Ví dụ hợp lý

`MongoPrimaryUnavailable` ở `prod/cluster-A` có thể inhibit `MongoClientConnectionErrors` severity warning cùng cluster-A. Nhưng nó **không** nên inhibit `OrdersDataDivergenceDetected` hay `CriticalBackupFailed` chỉ vì các metrics cũng đến từ cluster-A; đây là những nguy cơ độc lập.

### Chú ý labels thiếu

Trong một số alert routers, equality matcher coi hai labels đều thiếu là bằng nhau. Nếu dùng `equal: [cluster]` mà cả source và target đều thiếu `cluster`, có thể inhibit sai scope. Cần bảo đảm alert rules **luôn phát labels cần để so**.

## 21. Silence và maintenance: tạm ngừng có kiểm soát, không xóa cảnh báo

Một scheduled maintenance có thể gây replica restart hoặc planned node replacement. Có thể cần **silence** cụ thể:

```text
Scope      prod / cluster-A / node-03
Reason     planned node replacement
Owner      DBA on-call
Start      approved maintenance window
End        bounded expiration
Ticket     change-123
```

### Silence tốt

- Có ticket/owner và giờ hết hạn bắt buộc.
- Match thật hẹp theo service/cluster/node và loại alert.
- Không tự động mute SLO user-facing nếu business vẫn có thể bị ảnh hưởng.
- Có thể nhìn thấy alerts silenced trong incident tooling.
- Hết maintenance có verify dữ liệu/replication/capacity.

### Silence nguy hiểm

```text
environment=prod, severity=critical, duration=30 days
```

Đây gần như tắt hệ thống báo động production. Đặc biệt không dùng silence để làm dashboards “xanh” hoặc che một sự cố chưa giải quyết.

### Mute vs acknowledge

- **Acknowledge:** responder đã nhận và đang xử lý.
- **Silence:** chặn notifications trong phạm vi/time cụ thể.
- **Inhibit:** chặn notifications phụ thuộc có điều kiện vào alert khác.
- **Resolved:** điều kiện firing đã hết theo rule.
- **Close incident:** process con người xác nhận hoàn tất; không nhất thiết đồng thời với auto resolved.

Các thao tác khác nhau; không đánh đồng acknowledgement với một lệnh không gửi notification nữa.

## 22. Routing: thông báo đúng người, đúng kênh

```text
Alert firing
      |
      v
Match service/environment/severity
      |
      +--> Production critical -> On-call pager
      |
      +--> Production warning -> Team ticket/channel
      |
      +--> Staging issues     -> Dev environment channel
      |
      +--> Information        -> Event timeline only
```

### Thiết kế route dựa trên ownership

Không route mọi thứ về một kênh chung kiểu `#database-alerts` rồi yêu cầu người trực tự đoán team. Cần ánh xạ:

```text
service ownership -> response team -> escalation policy
```

Thực tế có thể một alert phải notify cả service owner và DBA, nhưng chỉ nên có **một incident commander/first responder rõ ràng** để tránh “ai cũng tưởng người khác đã xử lý”.

### Thay đổi ownership

Khi service chuyển team, alert rules và routing config phải chuyển theo. Một incident có page gửi vào on-call cũ là dấu hiệu **service catalog/config drift** cần xử lý như nợ vận hành.

## 23. Prometheus Alertmanager: ví dụ grouping và inhibition

Ví dụ cấu hình **minh họa** cho hệ có Prometheus/Alertmanager. Tên receivers, endpoint và label schema phải được thay bằng tích hợp thật và bảo mật; không copy thẳng lên production.

```yaml
route:
  receiver: team-ticket
  group_by:
    - alertname
    - service
    - environment
    - region
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - environment="prod"
        - severity="critical"
      receiver: service-pager
      group_wait: 10s
      repeat_interval: 2h

receivers:
  - name: service-pager
    webhook_configs:
      - url: "https://pager.internal.invalid/alerts"
        send_resolved: true
  - name: team-ticket
    webhook_configs:
      - url: "https://tickets.internal.invalid/alerts"
        send_resolved: true

inhibit_rules:
  - source_matchers:
      - alertname="MongoPrimaryUnavailable"
      - severity="critical"
    target_matchers:
      - alertname="MongoClientConnectionErrors"
      - severity="warning"
    equal:
      - environment
      - cluster
```

Các URLs `.invalid` là placeholder cố ý, không phải endpoint có thể gọi. Cấu hình thực tế phải có receivers hợp lệ, secrets được quản lý, kiểm soát retry và routing tích hợp.

### Giải thích ba khoảng thời gian

- `group_wait`: đợi một khoảng ngắn khi group mới xuất hiện để gom related alerts.
- `group_interval`: khoảng tối thiểu giữa các thông báo update về **cùng group** theo trạng thái/alerts mới.
- `repeat_interval`: nhắc lại khi cảnh báo vẫn firing và điều kiện notification policy đáp ứng.

Không đặt `group_wait` quá lâu cho incident nghiêm trọng. Việc giảm notification flood không đáng đánh đổi vài phút vô ích khi dịch vụ đã ngừng ghi đơn hàng.

### Receiver của alert không nên biết từng pod

Các nhãn `pod`, `instance` có thể vẫn được giữ để chẩn đoán, nhưng route/group key nên chọn **phạm vi xử lý**. Khi group chứa nhiều instances, nội dung notification nên ghi số lượng và cung cấp link danh sách đầy đủ thay vì gửi toàn bộ stack traces trong một message.

### Hạn chế của ví dụ

Rule `inhibit` áp cho một loại child warning cụ thể, **không** áp cho SLO-critical. Nếu `cluster` không tồn tại ở một số alerts, bổ sung normalization và đảm bảo equality không match nhầm trước khi deploy.

## 24. PromQL: cảnh báo lỗi nghiệp vụ thay vì chỉ CPU

Giả sử Java service xuất counter:

```text
nosql_business_operations_total{
  service="orders",
  environment="prod",
  operation="write",
  outcome="success|error"
}
```

Một biểu thức tỷ lệ lỗi logic theo 5 phút:

```promql
sum by (service, environment) (
  rate(nosql_business_operations_total{
    service="orders",
    environment="prod",
    operation="write",
    outcome="error"
  }[5m])
)
/
clamp_min(
  sum by (service, environment) (
    rate(nosql_business_operations_total{
      service="orders",
      environment="prod",
      operation="write"
    }[5m])
  ),
  1e-9
)
```

Lỗi/denominator cần được instrument nhất quán: counter success/error phải biểu diễn **logical operation kết thúc**, không đếm retry attempts hoặc một phần pipeline khác.

### Thêm volume guard

```promql
(
  sum by (service, environment) (
    rate(nosql_business_operations_total{
      service="orders", environment="prod",
      operation="write", outcome="error"
    }[5m])
  )
  /
  clamp_min(
    sum by (service, environment) (
      rate(nosql_business_operations_total{
        service="orders", environment="prod",
        operation="write"
      }[5m])
    ),
    1e-9
  )
) > 0.02
and
sum by (service, environment) (
  increase(nosql_business_operations_total{
    service="orders", environment="prod",
    operation="write"
  }[5m])
) >= 100
```

Ngưỡng **2% và 100 requests là minh họa**, chưa được hiệu chỉnh SLO thật. Với no-traffic outage, một alert **khác** phải theo dõi expected traffic/blackbox probing; không thể chỉ dựa trên tỷ lệ lỗi đã bị guard che.

## 25. PromQL: đo latency qua histogram đúng ngữ nghĩa

Với histogram `nosql_operation_duration_seconds_bucket`:

```promql
histogram_quantile(
  0.99,
  sum by (le, service, environment) (
    rate(nosql_operation_duration_seconds_bucket{
      service="orders",
      environment="prod",
      operation="write"
    }[5m])
  )
)
```

Biểu thức này áp cho **classic histogram** với label `le` và giả định instrument đúng. Đối với native histograms, cú pháp aggregation/quantile khác. Kết quả quantile là **ước lượng từ buckets**, không phải p99 tuyệt đối. Nếu muốn SLO “99% dưới 200 ms”, có thể trực tiếp dùng tỷ lệ bucket `le="0.2"` so với total count khi instrumentation phù hợp.

### Vì sao không tính p99 của p99?

Lấy p99 riêng từng pod rồi tính trung bình p99 giữa các pods **không bằng p99 của toàn traffic**. Phải aggregate histogram buckets (theo đúng scope) trước khi tính quantile; hoặc dùng phương pháp distribution aggregation được hỗ trợ.

### Không chỉ dùng latency DB

Một endpoint chậm có thể do **pool wait**, serialization, retries hoặc external dependency. Nên đo:

```text
HTTP end-to-end latency
  + connection pool wait
  + DB command execution
  + network/driver response
  + business processing
```

Trong incident, “DB p99 thấp, HTTP p99 cao” là dấu hiệu đáng điều tra **trước DB**, không nhất thiết phải scale database.

## 26. Burn-rate PromQL: hai cửa sổ để giảm spikes

Với recording rules tạo sẵn:

```text
orders:write_error_ratio:rate5m
orders:write_error_ratio:rate1h
```

và availability SLO 99.9%:

```promql
(
  orders:write_error_ratio:rate5m > (14.4 * 0.001)
)
and on (service, environment)
(
  orders:write_error_ratio:rate1h > (14.4 * 0.001)
)
```

Điều kiện này chỉ là ví dụ **fast burn** cho một định nghĩa SLI/SLO cụ thể. Rules tạo hai series phải có nhãn phù hợp và đủ mẫu; nếu số requests rất ít, thêm guard, đồng thời duy trì blackbox/no-data detection độc lập.

### Tại sao cần hai cửa sổ?

Cửa sổ ngắn phản ứng nhanh; cửa sổ dài giúp tránh một spike chỉ vài samples. Nhưng yêu cầu cả hai có thể làm chậm phát hiện những sự cố cực ngắn nhưng nghiêm trọng; phải kiểm chứng bằng historical incidents và SLO budget.

### Burn-rate của availability không đo data loss

Nếu 100% requests trả thành công nhưng CDC làm mất một change event quan trọng, error-ratio HTTP vẫn là 0. Cần **invariant/data reconciliation alerts** cho những loại lỗi mà HTTP SLI không nhìn thấy.

## 27. PromQL alert rules với annotations có hành động

Một rule minh họa:

```yaml
groups:
  - name: orders-nosql-slo
    interval: 30s
    rules:
      - alert: OrdersWriteErrorRatioHigh
        expr: |
          (
            sum by (service, environment) (
              rate(nosql_business_operations_total{
                service="orders",
                environment="prod",
                operation="write",
                outcome="error"
              }[5m])
            )
            /
            clamp_min(
              sum by (service, environment) (
                rate(nosql_business_operations_total{
                  service="orders",
                  environment="prod",
                  operation="write"
                }[5m])
              ),
              1e-9
            )
          ) > 0.02
        for: 5m
        labels:
          severity: critical
          team: orders
          service: orders
          environment: prod
        annotations:
          summary: "Order writes are failing above threshold"
          description: "Validate write SLO impact and database path"
          runbook_url: "https://runbooks.internal.invalid/orders-write"
```

Đây là **cấu trúc cấu hình mẫu**, metrics/labels giả lập, link placeholder. Chưa có volume guard và không đại diện production SLO đầy đủ; muốn dùng thật cần instrument, rule testing, routing và thresholds phù hợp.

### Annotation không phải runbook

Một đường link runbook hỏng hoặc nội dung chỉ ghi “check database” sẽ không hữu ích. Mỗi alert nên có câu lệnh kiểm chứng được, kết quả kỳ vọng, giới hạn an toàn, escalation và owner.

## 28. Nhãn có cardinality cao làm tăng cả metric cost lẫn alert noise

Anti-pattern:

```text
nosql_timeout_total{
  tenantId="T001",
  userId="U123456",
  orderId="O998877",
  queryHash="a-different-value-for-every-request",
  pod="..."
}
```

Nếu mỗi request có user/order khác, số series có thể tăng tới hàng triệu, khiến scrape/storage/query tốn tài nguyên.

### Nhãn nên cân nhắc

| Thường phù hợp | Cần kiểm soát | Thường không nên đặt vào metric labels |
|---|---|---|
| environment | region/cluster | raw orderId |
| service | bounded workload class | email |
| operation | bounded shard/replica | session ID |
| status/error category | tenant tier | request ID |
| database role | top-N tenant when governed | raw cache key |
| version family | endpoint template | query text chứa PII |

Các nhãn “phù hợp” cũng có thể gây cardinality cao nếu giá trị không được kiểm soát; ví dụ endpoint **raw URL path** chứa ID không phải endpoint template.

### Dùng trace/log khi cần root cause của một request

Một request ID được lưu trong **structured log/trace exemplar** phù hợp hơn là tạo một Prometheus time series mới cho mỗi request.

### Hệ quả với dedup

Nếu alert group/fingerprint có `tenantId`/`podId`/`requestId` thay đổi liên tục, notification storm có thể tăng ngay cả khi mọi records có chung root cause.

## 29. Mất metric không phải metric bằng 0

Một exporter chết:

```text
DB metric replication_lag_seconds no longer scraped
```

Không được suy:

```text
replication_lag_seconds = 0 (healthy)
```

Một query PromQL có thể trả **empty vector**, khiến alert biểu thức `lag > 60` không firing. Trong khi sự cố có thể là exporter down, mất quyền query, scrape timeout hoặc label schema thay đổi.

### Giám sát pipeline quan sát

- `up` của exporter/scrape target (khi applicable).
- Exporter scrape duration/errors.
- Series count/staleness.
- Missing data cho những business signals expected.
- Synthetic probes độc lập.
- Prometheus/Alertmanager/metrics store health.
- Notification delivery success/failure.

### Cảnh báo theo hai tầng

```text
Database replication lag high -> data path might be unhealthy
Database replication metrics absent -> visibility lost
```

Hai alert không có cùng ý nghĩa và không nên cả hai tự đóng khi exporter biến mất.

### Không có traffic thì sao?

Nếu không có request hợp lệ, counters `rate` về 0 hoặc trống. Hãy phân biệt **service không được gọi**, **traffic bị chặn ở gateway** và **instrumentation hỏng** qua independent signals.

## 30. Telemetry outage: không để monitoring “xanh giả”

Một phụ thuộc:

```text
Prometheus scrape -> exporter -> NoSQL cluster
```

Khi exporter lỗi vì database chậm, giá trị giám sát không còn cập nhật; dashboard có thể vô tình giữ giá trị cũ hoặc làm mất series.

### Tránh pattern nguy hiểm

```promql
some_critical_metric or vector(0)
```

Biểu thức này đôi khi được dùng cho các metrics tùy chọn, nhưng **không được tùy tiện dùng cho metric critical** vì nó có thể biến “không thấy dữ liệu” thành “giá trị bằng 0, hoàn toàn ổn”.

### Kịch bản riêng cho observability

- Synthetic read/write probes từ ngoài đường scrape.
- Independent monitoring of metrics backend.
- Notification channel health test.
- Đo lag của telemetry ingestion.
- Phân biệt missing, stale và zero.

### Alerting trong chính sự cố monitoring

Nếu hệ Alertmanager itself outage, không thể tự bảo đảm nó page được. Cần **external heartbeat/dead-man switch** hoặc đường giám sát độc lập theo mức độ quan trọng.

## 31. Dependency graph và incident correlation

Một sự cố:

```text
                 Network routing issue
                       |
             +---------+----------+
             |                    |
     MongoDB connection      Redis timeout
             |                    |
        Orders write 5xx     Cache misses
             |                    |
             +-----Checkout p99--+
```

Correlation có thể dùng:

- **Topology:** service phụ thuộc MongoDB/Redis cluster nào.
- **Time:** alerts xuất hiện gần nhau.
- **Scope:** region/AZ/cluster/tenant tier.
- **Recent changes:** deploy, config, failover, node maintenance.
- **Traces:** nhiều failing requests cùng điểm chờ.
- **Impact:** nhóm user paths cùng hỏng.

### Correlation ≠ chứng minh nhân quả

Hai alerts cùng xảy ra lúc 09:01 **không** nhất thiết có cùng root cause. Một job compaction có thể tình cờ trùng một lỗi network. Không suppress incident độc lập chỉ vì timestamp gần nhau.

### Root-cause confidence

Có thể thể hiện:

```text
Suspected root cause: network route to cluster A
Confidence: medium
Evidence: 30 pods timeout to same endpoint; DB process health OK
```

Sau khi xác minh, liên kết child alerts vào incident. Nếu chưa chắc, tiếp tục hiển thị **những symptom SLO-critical** để tránh false suppression.

## 32. Multi-region và multi-AZ: giảm trùng nhưng giữ scope

Một cụm NoSQL phân vùng:

```text
Region A / AZ-1
Region A / AZ-2
Region B / AZ-1
```

Nếu sự cố chỉ ở AZ-1 của Region A mà grouping theo `service=orders` toàn cầu, notification có thể gộp nhầm tác động; on-call khó biết **failover vùng nào hoặc tenants nào bị ảnh hưởng**.

### Hai cấp nhóm

**Tín hiệu địa phương:**

```text
OrdersWriteErrorRate{region=A, az=1}
```

**Tổng hợp global:**

```text
OrdersGlobalAvailabilitySLO
```

Global SLO đo trải nghiệm chung; local metrics giúp xác định scope. Không chỉ dùng global average khi một vùng nhỏ nhưng quan trọng bị hỏng. Nếu region B có traffic gấp 100 lần A, trung bình toàn cầu có thể **che outage hoàn toàn của A**.

### Chính sách page

- Page owner của user-facing path khi SLO theo region quan trọng vi phạm.
- Correlate tất cả node/pod alerts cùng cluster/region.
- Escalate infrastructure/root-cause team khi evidence phù hợp.
- Giữ incident độc lập nếu nhiều regions có nguyên nhân khác nhau.

## 33. MongoDB: primary election và write availability

Một replica set có thể trải qua leader/primary election khi node failover. Driver topology discovery, write retries và read preference ảnh hưởng thời gian ứng dụng bị tác động.

### Không page cho mọi election ngắn

```text
09:00:00 primary stepdown
09:00:05 new primary elected
09:00:08 writes resume
```

Nếu SLO cho phép gián đoạn ngắn và driver phục hồi an toàn, election event có thể là **timeline annotation**, không phải incident mới phải đánh thức DBA mỗi lần.

### Cảnh báo có thể hành động

```text
OrdersWriteAvailabilityDegraded
Condition: user-facing writes exceed allowed failure budget
Scope: prod/orders/cluster-A
Evidence:
  - no writable primary / election repeated
  - majority write errors or timeouts
  - application retry and pool waits rising
Next:
  - inspect topology and recent failover
  - verify quorum and primary eligibility
  - check client driver discovery/retry behavior
```

### Đừng chỉ xem số primary election

Một số elections không gây user-visible errors do client retries; ngược lại một application có DNS/routing lỗi có thể không ghi được dù primary khỏe. SLO symptom, topology health và client errors phải được **đối chiếu**.

### Unknown write outcome

Một timeout sau write không luôn là bằng chứng write chưa commit. Nếu alert đề xuất “retry mọi đơn hàng lỗi” mà không có idempotency, bạn có thể tạo duplicate business effects. Runbook phải yêu cầu **kiểm tra request ledger/transaction outcome**.

## 34. MongoDB: replication lag và read preference

Một read replica có thể chậm 45 giây:

```text
Primary order revision 10
Secondary order revision 8
Reader configured secondaryPreferred
```

Nếu API hiển thị lịch sử không cần mới tức thì, mức lag 45 giây có thể chấp nhận. Nếu API cần đơn hàng cập nhật trong 5 giây, đó là sự cố freshness.

### Rule theo ứng dụng

Không page chỉ vì `replication_lag_seconds > 10` khi không biết workload nào yêu cầu lag nhỏ hơn 10 giây.

Thiết kế:

- **Data freshness SLO:** read model/replica đáp ứng hạn mức?
- **Replication health:** lag tăng liên tục hay đang catch up?
- **Capacity:** oplog history còn đủ cho lagging member?
- **Topology:** có mất quorum, read node hoặc rollback risk?

### Rủi ro metric

Replica lag đo được từ timestamps của operations có thể trở nên khó diễn giải khi workload ít write; cách tính lag/last applied khác nhau theo công cụ. Cần hiểu **nguồn metric và điều kiện low write volume**, không khẳng định phép đo có nghĩa giống nhau trong mọi MongoDB version.

### Correlation

Nếu cùng cluster đang election, low-level lag warnings có thể được group/inhibit theo root cause khi phù hợp. Nhưng một replica đã tụt lag **từ trước khi election** có thể là incident độc lập, không nên tự động bỏ qua.

## 35. MongoDB: connection pool exhaustion

Các số:

```text
Pool max connections = 100
Connections in use   = 100
Wait queue           = 500 requests
Pool acquire p99     = 2 seconds
HTTP read p99        = 3 seconds
```

**Saturation** đáng chú ý vì nó gây trực tiếp chờ connection.

### Không chỉ alert “pool usage 100%”

Một pool đầy trong vài trăm mili giây khi burst có thể bình thường. Nhưng hàng trăm requests chờ, timeout tăng và API SLO bị vi phạm là dấu hiệu hành động.

### Runbook

1. Kiểm tra app có tạo quá nhiều DB clients/pools không.
2. Đọc active vs idle connection counts và wait latency.
3. Tìm long transactions/cursors không đóng.
4. Xem slow queries, indexes, locks, server load.
5. Xem có deployment tăng concurrency hoặc retries không.
6. Giới hạn đầu vào tạm thời nếu backlog tăng mất kiểm soát.
7. Chỉ cân nhắc tăng pool sau khi biết server capacity và root cause.

### Đừng tạo cảnh báo theo từng socket

Một lỗi kết nối trên 100 sockets thường chỉ là một incident cluster/route. Group theo service/cluster và dùng socket-level metrics như evidence.

## 36. Redis: memory, eviction và cache effectiveness

Một Redis cache dùng eviction theo maxmemory policy. Nếu memory tiến gần giới hạn:

```text
used_memory increases
evicted_keys increases
cache_hit_ratio decreases
MongoDB read traffic increases
checkout p99 increases
```

Cảnh báo **có thể hành động** kết hợp memory pressure, eviction rate và downstream impact rõ hơn một ngưỡng memory đơn lẻ.

### Eviction không luôn là incident

Redis cache được thiết kế **có thể evict**, nên một mức eviction nhất định có thể bình thường. Với Redis làm durable queue/coordination store, memory pressure có ý nghĩa khác và có thể nghiêm trọng hơn. **Phải phân biệt role Redis**:

| Role Redis | Đo điều gì? |
|---|---|
| Cache có fallback DB | Hit ratio, DB fallback load, p99, evictions |
| Session store | Session misses/expiry/errors, user impact |
| Redis Streams | Pending entries, consumer lag, retention, durability |
| Rate-limit/locks | Correctness, lock availability, latency |
| Durable-like operational state | Persistence/replication/failover contract và data loss risk |

### Alert root cause và symptom

`RedisEvictionsHigh` có thể là warning/diagnostic. `CheckoutReadSLOBurn` là page. Nếu evictions tăng mà client p99 vẫn tốt và headroom còn, có thể xử lý có kế hoạch thay vì đánh thức.

### Redis fragmentation

`used_memory_rss` và `used_memory` có thể khác vì allocator fragmentation, buffers, replicas, memory accounting. Đừng tự coi chênh lệch là memory leak và hướng dẫn restart Redis trên production; phải kiểm tra các nguyên nhân theo version/config.

## 37. Redis: cache stampede và nguồn NoSQL bị quá tải

Khi cùng lúc hàng triệu keys hết TTL:

```text
Cache hit ratio drops
   |
   v
Many misses to MongoDB
   |
   v
Pool wait rises
   |
   v
Read timeout retries
   |
   v
Even more database load
```

Nếu mỗi pod có alert cache miss, DB timeout, connection wait, bạn không muốn **100 pages riêng**; nhưng cũng không được coi cache miss high là root cause chắc chắn. Có thể:

- Group cùng request path/region.
- Dùng `CheckoutReadSLOBurn` làm symptom page.
- Đưa `CacheHitRatioDrop`, `DbPoolWaitHigh`, recent TTL/config changes vào incident context.
- Inhibit low-level warning **khi nguyên nhân đã xác nhận** và scope khớp.

### Hành động đúng

Kiểm tra TTL đồng loạt, eviction, cache key schema deploy, Redis connectivity, bounded fallback, singleflight/stale-while-revalidate khi freshness cho phép. Không `FLUSHALL` để “làm sạch cache” giữa một stampede.

### Monitor hậu quả của mitigations

Nếu bật rate-limit hoặc stale fallback, SLO lỗi có thể cải thiện nhưng **freshness/correctness** giảm. Alert dashboard phải thể hiện trade-off, không tuyên bố resolved chỉ từ latency.

## 38. Cassandra: compaction, tombstones và p99 đọc

Cassandra có các yếu tố đặc trưng:

- Compaction và SSTable read amplification.
- Tombstones làm read path phải xem qua các deleted markers.
- Large partitions/hot partition keys.
- Pending compactions và disk I/O pressure.
- Coordinator read/write timeouts.
- Replica unavailable hoặc consistency level không đạt.

### Alert tình huống

```text
CassandraReadP99Degraded
  Read p99 > agreed SLO for 15 minutes
  Rows scanned per result and tombstone warnings rising
  Affected: analytics report reads
  Owner: analytics + Cassandra on-call
```

Đừng thiết kế “pending compactions > 100 là page” nếu chưa biết baseline, throughput và disk/memory saturation. Một số compaction backlog tạm thời là bình thường, nhưng backlog **liên tục tăng** trong khi disk gần đầy có thể cần hành động sớm.

### Consistency level

Query với `LOCAL_QUORUM` có yêu cầu availability khác `ONE`. Nếu một node mất nhưng consistency policy vẫn đáp ứng và SLO không suy giảm, không nhất thiết page ứng dụng. Nhưng mất đủ replicas khiến consistency không đạt thì page có thể cần thiết.

### Nguy hiểm: chạy repair/compaction không kiểm soát

Runbook không nên chỉ ghi “chạy repair toàn cluster ngay” khi p99 cao. Repair/major compaction có thể tăng I/O pressure. Cần kiểm tra version, cluster health, disk headroom, workload/time window và hướng dẫn DBA phù hợp.

## 39. Cassandra: disk headroom và nguy cơ mất khả năng phục hồi

Disk usage hiện tại:

```text
Node A: 78%
Node B: 82%
Node C: 94%
```

Nếu node C đã 94% và compaction cần thêm temporary space, rủi ro có thể vượt xa một ngưỡng tĩnh.

### Cảnh báo theo xu hướng

- Free bytes và tốc độ giảm.
- Growth forecast theo workload.
- Compaction backlog/estimated amplification.
- Node placement/replica redundancy.
- Repair/snapshot requirements.
- Mức thời gian còn trước khi hết disk, với uncertainty.

### Headroom dự báo

Nếu disk free = 50 GiB và đang giảm 10 GiB/h, thời gian tuyến tính:

\[
T_{\mathrm{exhaust}}\approx 50/10=5\text{ giờ}
\]

Đây chỉ là **ngoại suy tuyến tính**, sai nếu workload/compaction thay đổi. Cần nhiều cửa sổ, minimum sample và confidence; không page từ forecast kỳ dị tạo bởi một burst vài phút.

### Alert có thể hành động hơn

`DiskCapacityExhaustionImminent` nếu forecast còn rất ít thời gian hơn lead time để mở rộng, compaction/recovery margin không đủ và service có nguy cơ dừng. Đây là alert phòng ngừa hợp lý dù SLO hiện vẫn xanh.

## 40. DynamoDB: throttling và hot partition

DynamoDB có thể từ chối một số reads/writes do throttling, table/index capacity hoặc hot partition; SDK có thể retry với backoff.

### Phân biệt ba tín hiệu

1. **Throttled attempts:** driver/SDK gặp `ProvisionedThroughputExceeded` hoặc loại throttling tương ứng.
2. **End-user failures/latency:** những logical operations hết retry budget.
3. **Capacity behavior:** consumed capacity, on-demand/provisioned settings, partition key skew, quotas.

Một hệ có throttling attempts tăng nhưng retry thành công trong SLO có thể là capacity warning. Nếu retry khiến checkout p99 tăng hoặc writes fail, nên page user-facing owner.

### Một alert hữu ích

```text
[P2] orders/prod: DynamoDB write attempts throttled continuously,
successful write latency approaching SLO, one partition key hot

Check:
  - table/GSI read-write capacity and throttles
  - recent traffic increase / new access pattern
  - hot partition key distribution
  - SDK retry/backoff behavior
  - service's pending work
```

### Không tăng concurrency để “hết chậm”

Nếu server throttle vì capacity/hot key, tăng workers hoặc batch size có thể tạo retry storm. Biện pháp có thể là rate-limit, backoff, adjust capacity, change key distribution, schedule bulk work.

### Metrics khác nhau theo API

Read/write throttling và consumed capacity theo table/GSI/operation có thể khác nhau. Đừng gom table OK với GSI lag/throttle khiến một read model quan trọng bị chậm.

## 41. CDC và event pipelines: alert khi dữ liệu dẫn xuất quá cũ

Pipeline:

```text
NoSQL source
   -> CDC connector
   -> Kafka/stream
   -> consumer
   -> search / materialized view
```

Một consumer có thể có offset lag = 0 nhưng search index chưa refresh hoặc event bị lọc sai. Ngược lại lag offsets lớn trên một topic chứa events nhỏ có thể chưa vượt freshness SLA.

### Các mức lag

| Signal | Trả lời |
|---|---|
| Source connector last committed position | Đã đọc nguồn đến đâu |
| Connector publish failure/lag | Có chuyển bền vào broker không |
| Broker consumer offset lag | Có backlog records chưa được checkpoint không |
| Oldest unprocessed event age | Bao nhiêu thời gian event chưa được áp dụng |
| Projection source revision lag | View tụt bao nhiêu revisions |
| End-to-end freshness lag | Người dùng thấy dữ liệu trễ bao lâu |

### Alert cần hành động

```text
[PAGE] order-search: 99th percentile source-to-visible lag > 120s
for 10m, violating freshness SLO

Evidence:
  Kafka consumer lag increasing
  Projection applied revision behind source
  Search refresh status
Owner: search pipeline
```

### Không page theo từng partition nếu cùng incident

Nếu 100 partitions cùng lag vì sink outage, group theo pipeline/environment/region. Nhưng nếu chỉ một partition chứa **hot key/poison event** và các partitions khác khỏe, phải hiển thị partition ID để không đánh mất root cause.

### Source retention headroom

Một CDC reader đứng yên lâu có thể hết oplog/WAL/stream retention hoặc làm replication slot giữ WAL. Đó có thể là **capacity/page alert riêng** ngay cả khi consumer lag đã được group dưới pipeline outage, bởi mất log có thể làm không thể resume và cần resnapshot.

## 42. Elasticsearch/OpenSearch: search không giống write ACK

Một index update có thể được engine chấp nhận, nhưng query chưa nhìn thấy do refresh semantics. Vì vậy:

```text
Index write accepted        : YES
Search result visible       : NOT YET
Search service available    : YES
```

### Alert theo hợp đồng

- Indexing rejected/throttled.
- Search query p99/errors.
- Unassigned shards/capacity theo khả năng phục vụ.
- Refresh/indexing backlog.
- Source-to-search visible lag.
- Result correctness probes khi cần.

### Không chỉ xem cluster color

Một cluster báo green vẫn có thể có search latency xấu, mapping lỗi, index alias sai hoặc dữ liệu stale. Ngược lại một cluster yellow vì replica unavailable có thể còn trả query nhưng giảm fault tolerance; mức độ page phụ thuộc risk và lead time.

### Deep pagination

Nếu endpoint search đột ngột dùng deep `from+size` thay vì `search_after`/PIT, p99/circuit breakers có thể tăng. Alert nên gắn query class/index và owner, không page riêng mỗi query timeout từ từng pod.

## 43. Backup, restore và cảnh báo không có người dùng trực tiếp bị lỗi

Một ngày nọ backup job thất bại nhưng API vẫn trả 200:

```text
Last verified successful backup: 9 days ago
Restore verification: failed
PITR window: shrinking
Live traffic: healthy
```

Đây có thể là incident vận hành nghiêm trọng, vì **mất khả năng phục hồi** sẽ gây tác động lớn khi xảy ra disaster.

### Cảnh báo có thể hành động

```text
[P1/P2 by policy] Verified recoverability below required objective
Evidence:
  age of last verified restore point
  backup job outcome and duration
  replication/PITR window coverage
Owner: data protection
Actions:
  verify backup destination, credentials, storage quotas
  initiate safe retry or alternate backup per runbook
  do not delete remaining valid backup artifacts
```

### “Backup completed” chưa là “restore works”

Theo dõi:

- Backup đã chạy và upload thành công.
- Integrity/verification.
- Có thể restore với schema/keys/permissions đúng.
- RPO/RTO mục tiêu và lần diễn tập phục hồi gần nhất.
- Bản sao địa lý, encryption/key management.

Một alert `backup_job_failed` là nguyên nhân, còn `no_verified_recovery_point_within_SLO` là tác động gần hơn đến mục tiêu.

## 44. Bất biến dữ liệu và cảnh báo sai lệch

Một số lỗi NoSQL không xuất hiện trong latency/error metrics:

- Search projection thiếu 10.000 documents.
- Event consumer áp cùng `$inc` hai lần.
- Cache trả record tenant A cho tenant B.
- Materialized counter âm dù business invariant không cho phép.
- Read model đã xóa vẫn hiển thị PII do event delete mất.
- Hai replicas có diverging values ngoài consistency contract.

### Alert khi có bằng chứng rõ

```text
[P1] CrossTenantDataExposureDetected
  scope: prod / order-read path
  evidence: verified mismatch between authenticated tenant and record tenant
  action: isolate affected cache path; page security + service owner
```

Một sự kiện có bằng chứng đủ mạnh có thể đòi **page ngay**, không chờ 5 phút hoặc minimum traffic, vì hậu quả riêng tư không phụ thuộc tỷ lệ lớn.

### Đừng log dữ liệu nhạy cảm để chứng minh

Ghi redacted IDs/hashes có quyền, trace IDs, incident references và cách tái hiện an toàn; không gửi payload chứa PII vào public alert channel.

### Kiểm soát false positives

Một checker phải phân biệt:

- Đọc hai bản ở hai thời điểm khác nhau.
- Replica lag được phép.
- Mismatch thật vượt hợp đồng.
- Schema migration đang diễn ra.

Alert data divergence chỉ nên page khi có **bằng chứng và so sánh hợp lệ**, tránh một bộ đo sai trở thành incident storm.

## 45. Alert hướng đến nguyên nhân nhưng không cần đoán tuyệt đối

Runbook có thể cung cấp **hypotheses**:

```text
Symptom: write timeouts exceed SLO.
Hypotheses:
  A. MongoDB primary election / quorum lost
  B. App connection pool exhaustion
  C. Network route failure
  D. Newly deployed unindexed query
```

Thay vì đặt title:

```text
CRITICAL: DATABASE PRIMARY IS BROKEN
```

khi chỉ có bằng chứng write timeout. Overconfidence gây mitigation sai (restart nodes khi vấn đề là app pool).

### Tiến trình chẩn đoán

1. Xác minh user impact.
2. Xác định blast radius.
3. So các layer traces/metrics.
4. Kiểm tra recent changes/topology.
5. Xác nhận hoặc bác giả thuyết.
6. Chọn mitigation ít rủi ro và reversible trước.
7. Theo dõi kết quả trên symptom SLI.

Một alert tốt **khởi động quá trình**, không nhất thiết đã chứng minh root cause.

## 46. Dependency suppression: những lúc không nên inhibit

Giả sử network cluster A lỗi, đồng thời backup đang thất bại vì storage credentials hết hạn. Một rule `cluster=A` tổng quát:

``text
Inhibit ALL warnings when MongoPrimaryUnavailable
```

có thể che mất backup issue độc lập.

### Không nên inhibit những điều sau chỉ vì cùng cluster

- SLO end-user critical nếu đây là kênh duy nhất alert service owner.
- Data corruption/mismatch.
- Security incident.
- Verified backup/recovery gap.
- Disk capacity imminent nếu cần hành động trước failover.
- Replication divergence với nguyên nhân độc lập.
- Alert thiếu telemetry của chính monitoring stack.

### Khi source alert resolved

Nếu child symptom vẫn active sau root alert resolved, nó phải xuất hiện trở lại và được đánh giá độc lập. Nếu phải đợi quá lâu do repeat interval hoặc silence sai, cần sửa routing policy.

### “Root cause” do AI hoặc correlation engine gợi ý

Nếu có hệ tự gom incidents, nên hiển thị confidence và evidence, cho on-call **ungroup/reopen** khi nghi vấn sai. Không để một mô hình suy đoán tự xóa tín hiệu dữ liệu mất mát hoặc bảo mật chỉ để giảm notification count.

## 47. Ứng dụng Java: instrument kết quả **logic** của DB operations

Một thư viện driver thường xuất lệnh/attempt metrics, nhưng service cần bổ sung **logical operation outcome** nếu muốn alert sát với user SLO.

Ví dụ với Micrometer-style API:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.Callable;

public final class DbOperationObserver {
    private final MeterRegistry registry;

    public DbOperationObserver(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T observe(
            String service,
            String operation,
            Callable<T> callback) throws Exception {

        Timer.Sample sample = Timer.start(registry);
        String outcome = "error";

        try {
            T result = callback.call();
            outcome = "success";
            return result;
        } finally {
            Counter.builder("nosql.business.operations")
                .tag("service", service)
                .tag("operation", operation)
                .tag("outcome", outcome)
                .register(registry)
                .increment();

            sample.stop(
                Timer.builder("nosql.business.operation.duration")
                    .tag("service", service)
                    .tag("operation", operation)
                    .tag("outcome", outcome)
                    .register(registry)
            );
        }
    }
}
```

### Giới hạn quan trọng

- Đoạn code là ví dụ minh họa, không phải thư viện production đã chuẩn hóa lỗi.
- Nếu `callback` trả trước khi một **async write** commit, nó sẽ đếm success quá sớm. Với async API, measure ở completion stage tương ứng với durable logical outcome.
- Exception từ `callback` có thể biểu diễn **unknown commit outcome**. Không tự đếm mọi timeout là “chắc chắn business effect thất bại”; metric error nên mô tả **caller không nhận success theo contract**, còn reconciliation/unknown outcome có metric riêng.
- Tên `service` và `operation` phải đến từ **bộ giá trị giới hạn** được định nghĩa trong code/service registry; không lấy raw query/user input.
- Không dùng `orderId`, `userId`, raw tenant ID, full query hoặc request ID làm metric label.
- Query bị caller cancel cần outcome classification riêng nếu SLI yêu cầu; không đếm “success” khi work chưa hoàn tất.
- Nếu transaction callback có retry, instrument logical operation **một lần ở boundary service** thay vì tính mỗi attempt như một user request.

### Phân biệt metrics của SDK và business

```text
business request O1
  -> driver attempt 1: timeout
  -> driver attempt 2: success
  -> business outcome: success
```

Ở đây:

```text
db_attempts_total         += 2
db_attempt_timeouts_total += 1
business_success_total    += 1
```

Nếu alert availability tính 1 timeout / 2 attempts = 50% rồi suy “50% user requests lỗi” là sai.

## 48. Async Java: ghi nhận outcome khi future thực sự hoàn tất

Với API bất đồng bộ, ranh giới quan sát thường ở `CompletionStage`:

```java
import java.util.concurrent.CompletionStage;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class AsyncDbObserver {
    private final MeterRegistry registry;

    public AsyncDbObserver(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> CompletionStage<T> observe(
            String operation,
            CompletionStage<T> stage) {
        Timer.Sample sample = Timer.start(registry);

        return stage.whenComplete((value, error) -> {
            String outcome = (error == null)
                ? "success"
                : "error";

            registry.counter(
                "nosql.business.operations",
                "operation", operation,
                "outcome", outcome
            ).increment();

            sample.stop(Timer.builder(
                "nosql.business.operation.duration")
                .tag("operation", operation)
                .tag("outcome", outcome)
                .register(registry));
        });
    }
}
```

### Cảnh báo về thời điểm bắt đầu

Ví dụ bắt đầu `Timer.Sample` **khi gọi `observe`**, nên phải wrap sát lúc dispatch. Nếu stage đã chạy lâu trước khi `observe` được gọi, latency không bao gồm phần trước đó. Nếu cần đo đúng toàn bộ end-to-end, start sample **trước khi** tạo/gửi async operation.

### `whenComplete` không tự biến timeout thành rollback

Nếu future timeout sau remote write, outcome vẫn có thể unknown. Nên có:

```text
logical_outcome = success | error | canceled | unknown
```

với ý nghĩa nghiệp vụ được tài liệu hóa, không dùng duy nhất nhãn `exceptionClass` chứa tên động/stack trace.

### Event-loop và callback

Instrumentation phải nhẹ; tránh synchronous network logging hoặc truy vấn database trong callback của driver I/O thread. Exemplar/tracing nên được sample phù hợp để không gây overload khi đang incident.

## 49. Alert testing: một rule đúng cú pháp chưa chắc đúng hành vi

Một rule có thể pass config parsing nhưng vẫn:

- Page khi một replica failover hợp lệ.
- Không page khi toàn endpoint ngừng traffic.
- Bị chặn vì exporter chết.
- Gộp hai regions độc lập thành một notification.
- Không group vì thêm `pod` vào group key.
- Flap liên tục khi metric quanh threshold.
- Không route đến on-call đang trực.
- Silence tồn tại vô hạn sau maintenance.

### Các lớp kiểm thử

1. **Rule unit tests:** cho chuỗi metric giả, kiểm tra firing/pending/resolved.
2. **Routing tests:** alert labels đi đúng receiver.
3. **Grouping tests:** 30 child alerts tạo một notification phù hợp.
4. **Inhibition tests:** root + child suppress đúng, sibling independent không bị che.
5. **No-data tests:** exporter chết không tự chuyển sang healthy.
6. **End-to-end delivery tests:** notification thực sự tới kênh/on-call sandbox.
7. **Chaos/game day:** source failover, network partition, cache outage, CDC backlog.
8. **Historical replay:** dùng dữ liệu incident thật đã ẩn PII để đánh giá false alarms/missed incidents.

### Không cần tạo sự cố production để thử

Dùng test environment, simulated metrics, alert labels giả và sandbox receiver. Với game day production được phê duyệt, phải có hạn mức blast radius, rollback plan, communication và quyền phù hợp.

## 50. State machine của alert và notification

Một rule thường có:

```text
INACTIVE
    |
    | expression becomes true
    v
PENDING
    |
    | condition remains true for required duration
    v
FIRING
    |
    | expression becomes false / resolution policy
    v
INACTIVE / RESOLVED notification
```

Trong khi đó incident workflow có thể:

```text
DETECTED -> ACKNOWLEDGED -> INVESTIGATING
         -> MITIGATING -> MONITORING -> CLOSED
```

**Đây là hai state machines khác nhau.**

Một alert firing có thể được acknowledge trong incident tool nhưng vẫn firing về metric. Một alert resolved có thể cần incident tiếp tục mở để xác minh data reconciliation và xử lý backlog.

### Khi nhiều alerts cùng incident

Có thể có:

```text
Incident INC-123
   +-- OrdersWriteSLOBurn (firing -> resolved)
   +-- MongoPrimaryUnavailable (firing -> resolved)
   +-- CDCSourceLagHigh (still firing)
```

Người trực có thể đã khôi phục writes nhưng CDC vẫn lag. **Đừng đóng toàn incident chỉ vì primary availability alert đã resolved.**

## 51. Phục hồi: điều kiện “resolved” cũng phải định nghĩa đúng

Một cảnh báo latency tự resolved khi p99 thấp:

```text
09:00 incident starts
09:05 service rate limits half the traffic
09:06 successful requests p99 drops
09:07 alert auto resolves
```

Nhưng nếu half users bị 429 hoặc request không tới app, availability vẫn suy giảm. Cần xem:

- Traffic offered/received và status codes.
- Success ratio/SLI.
- Retry rates.
- Queue/backlog.
- Data freshness.
- Read/write correctness.

### Recovery verification

Đối với MongoDB:

1. Primary/replica topology ổn định.
2. User writes/read paths đạt SLO.
3. Unknown commit outcomes được đối soát.
4. CDC/backlog/read models đã bắt kịp trong mục tiêu.
5. Noisy child alerts đã hết hoặc có follow-up owner.

**Resolved metric ≠ toàn bộ hậu quả đã khắc phục.**

## 52. Một incident nên có thông báo đầu, cập nhật và kết thúc

Thay vì gửi 200 pages:

```text
09:01 NEW [P1] Orders writes failing in region A.
09:05 UPDATE: primary election confirmed, 3 services affected.
09:12 UPDATE: write path recovered, search index backlog 3 minutes.
09:22 RESOLVED/RECOVERY: SLO healthy, CDC caught up.
```

### Nguyên tắc update

- Chỉ gửi update khi thông tin/action đáng kể thay đổi hoặc cadence policy yêu cầu.
- Không gửi lại cùng biểu đồ/stack trace mỗi phút.
- Giữ incident ID ổn định, link các child alerts.
- Thông báo rõ khi impact mở rộng sang region/tenant khác.
- Bảo đảm escalation nếu không ai acknowledge.

### Repeat interval không phải infinite silence

Một alert critical chưa có owner xử lý vẫn cần nhắc/escalate theo policy. Giảm spam không có nghĩa “gửi một lần rồi quên”. Dùng **acknowledgement-aware escalation**, không chỉ một repeat timer.

## 53. On-call fatigue là rủi ro reliability thực sự

Nếu mỗi ca on-call có 100 notifications, trong đó chỉ 1 cần hành động, người trực có xu hướng:

- Bỏ qua tin mới.
- Dùng broad silence để khỏi bị làm phiền.
- Xử lý theo thói quen mà không xác minh impact.
- Mất thời gian ngủ nghỉ, ảnh hưởng quyết định khi sự cố nghiêm trọng thật.

### Chỉ số chất lượng alerting

| Metric | Ý nghĩa |
|---|---|
| Pages per on-call shift | Khối lượng gián đoạn |
| Actionable page ratio | Tỷ lệ pages cần phản ứng đúng |
| Duplicate notifications per incident | Mức spam |
| Time to acknowledge | Phát hiện và nhận trách nhiệm |
| Time to engage owner | Routing có đúng không |
| Time to mitigation | Alert có hỗ trợ hành động không |
| Missed incident count | Tối ưu noise có bỏ lọt không |
| False positive count | Rule có nhạy quá không |
| Alert flaps per day | Threshold/state ổn định không |
| Unowned alerts | Service catalog/routing nợ |
| Silences expired/overdue | Maintenance có quản trị không |

### Không tối ưu một metric duy nhất

Xóa toàn bộ alerts sẽ làm số pages giảm về 0 nhưng **missed incidents tăng**. Mục tiêu là tăng tín hiệu có ích, không phải chỉ làm biểu đồ notification count đẹp.

## 54. Review alert định kỳ

Một chương trình alert review theo tháng/quý có thể phân loại:

1. **Page hữu ích:** alert phát hiện đúng impact và runbook giúp xử lý.
2. **Page trùng:** cùng incident/root cause; cần grouping/inhibition.
3. **Page không hành động được:** chuyển ticket/metric hoặc viết runbook.
4. **Page nhạy quá:** điều chỉnh window/hysteresis/traffic guard.
5. **Page quá chậm:** giảm detection delay hoặc thêm synthetic probe.
6. **Page sai owner:** sửa routing/service catalog.
7. **Missed incident:** bổ sung SLI hoặc invariant alert.
8. **Stale alert:** service/metric không còn tồn tại; decommission có audit.

### Dùng incident data

Ghi lại:

```text
alertname
incidentId
rootCause
userImpact
firstFiredAt
firstActionTakenAt
falsePositive?
duplicateGroup?
runbookHelpful?
ruleChangeProposal
```

Không phải mọi alert không dẫn đến outage đều vô ích: **capacity alert được xử lý kịp thời chính là một thành công phòng ngừa**.

### Review sau thay đổi

Khi sửa threshold/group key/inhibit, xem các incidents cũ dưới logic mới để đảm bảo không che mất tình huống từng cần page.

## 55. Tự động khắc phục phải an toàn hơn việc chỉ cảnh báo

Một số tổ chức gắn runbook automation:

```text
Alert fires -> automation validates preconditions
             -> executes approved reversible mitigation
             -> checks user-facing SLI
             -> records audit and notifies owner
```

Ví dụ an toàn hơn:

- Tạm giảm concurrency của background export có thể cấu hình rollback.
- Restart một worker bị kẹt **sau khi** kiểm tra checkpoint/idempotency.
- Chuyển traffic theo failover protocol đã diễn tập và có fencing.

Ví dụ rủi ro:

- `FLUSHALL` Redis để giảm memory.
- Xóa Cassandra SSTables khi disk full.
- Force MongoDB primary mà không xét quorum/split-brain risk.
- Replay mọi failed payments bằng operation ID mới.
- Tắt authentication để “sửa 403”.

### Guardrails cho automation

- Preconditions đo được.
- Blast radius hữu hạn.
- Rate-limit/single-flight để tránh nhiều workers cùng chạy.
- Retry/rollback rõ.
- Audit trail và owner.
- Không gây mất dữ liệu/durability.
- Dừng tự động nếu evidence mâu thuẫn hoặc impact tăng.

### Đánh giá sau mitigation

Không báo “fixed” chỉ vì lệnh automation chạy thành công. Đo lại symptom SLI, backlog và data correctness.

## 56. Bảng mẫu cảnh báo NoSQL theo triệu chứng và hành động

Các thresholds trong bảng **không phải ngưỡng cố định nên áp dụng ngay**; phải gắn với SLO, baseline và capacity của ứng dụng.

| Alert | Tín hiệu chính | Mức xử lý minh họa | Hành động đầu tiên |
|---|---|---|---|
| `OrdersWriteSLOBurn` | Logical write failures/error budget tăng nhanh | Page service owner | Xác minh impact, driver errors, DB topology |
| `OrdersReadLatencySLOBurn` | User read latency vượt SLO | Page khi tác động lớn | Tách pool wait, query execution, network |
| `MongoPrimaryUnavailable` | Không có writable primary lâu hơn failover allowance | Page DB/platform | Quorum, election, node/network |
| `MongoReplicaFreshnessExceeded` | Read replica trễ vượt hợp đồng ứng dụng | Page hoặc ticket | Lag trend, routing/read preference |
| `MongoPoolSaturation` | Pool wait p99 và acquisition timeouts kéo dài | Warning/page theo SLO | Leak, concurrency, slow queries |
| `RedisEvictionImpactHigh` | Evictions + cache misses + DB fallback overload | Page service/cache owner | TTL, maxmemory, cache hot keys, fallback |
| `RedisStreamPendingAgeHigh` | Pending entries vượt processing SLA | Page pipeline owner | Dead consumers, retention, claim/replay |
| `CassandraReadP99Degraded` | p99 query vượt SLO | Page app/DB owner | Compaction, tombstones, partition hotspots |
| `CassandraDiskHeadroomLow` | Forecast disk exhaustion gần | Capacity page/ticket | Growth, compaction space, scale plan |
| `DynamoDBThrottlingImpactsWrites` | Throttling đã gây retries/failed writes | Page table owner | Quota, hot keys, backoff, capacity |
| `CDCSourceLogRetentionAtRisk` | Connector lag đe dọa WAL/oplog retention | Page data platform | Publication/checkpoint progress, source headroom |
| `OrderSearchFreshnessSLOBurn` | Source-to-visible index lag vượt SLO | Page search owner | Consumer backlog, sink errors, refresh |
| `NoVerifiedBackupWithinRPO` | Không có recovery point hợp lệ trong giới hạn | Page data protection owner | Backup errors, credentials, restore verification |
| `NoSQLExporterScrapeLost` | Monitoring mất khả năng quan sát | Page/ticket theo criticality | Exporter, network, scrape permissions |
| `CrossTenantMismatchDetected` | Verified data exposure/invariant failure | Immediate incident | Isolate read/cache path, engage security |

### Tránh hai kiểu alert đối nghịch

**Quá mơ hồ:**

```text
NoSQLNotHealthy
```

Không chỉ rõ hệ nào, chiều hỏng nào, ai chịu trách nhiệm.

**Quá chi tiết:**

```text
OrdersMongoConnectionTimeoutPod42Socket381Query13OrderIdO12345
```

Tạo vô số fingerprints, nguy cơ lộ thông tin và khó group. Cần đặt **mức đối tượng vừa đúng**: service/operation/cluster/region (và shard khi root cause cần), còn chi tiết connection/query/request nằm ở traces/logs.

## 57. Runbook mẫu: write availability suy giảm

**Alert ID:** `OrdersWriteSLOBurn`

**Owner:** Orders on-call (first responder), database/platform escalation theo service catalog.

**Tín hiệu:** write SLI vi phạm budget nhiều cửa sổ, môi trường production. **Không** dùng status của một exporter duy nhất như bằng chứng ứng dụng đã lỗi.

### Triage trong vài phút đầu

1. Mở SLO dashboard: error ratio, latency, request count, top failing operations; xác nhận traffic có đủ.
2. Xem scope: region/cluster, tenants/tier bị ảnh hưởng, chỉ writes hay cả reads.
3. Xem timeline: deployment, schema/index changes, DB primary election, network config.
4. Đọc trace samples/redacted logs: pool acquire timeout, server selection timeout, write concern failure, rate limit.
5. Kiểm tra một synthetic write probe **an toàn** trên namespace chuyên dụng (nếu đã thiết kế) và clean up theo policy.
6. Phân biệt driver **timeout với outcome unknown**, không tự replay non-idempotent writes bằng IDs mới.

### Hành động theo nguyên nhân

| Tín hiệu xác minh | Hành động khả dĩ |
|---|---|
| Recent app deploy gây unindexed query/connection leak | Rollback hoặc giảm concurrency theo procedure |
| MongoDB election lặp/mất majority | Engage DBA, kiểm tra topology/quorum/fault domains |
| Pool wait tăng nhưng DB CPU thấp | Kiểm tra pool per client, cursor/transaction leaks |
| DB CPU/disk cao vì workload mới | Throttle background jobs, xem query/index |
| Network route timeout cùng AZ | Engage network platform, scoped traffic failover |
| Write throughput quota/hot partition | Backoff/rate-limit, capacity/key design |

### Không được làm ngay theo phản xạ

- Restart mọi DB nodes cùng lúc.
- Tắt write concern/quorum để tạo biểu đồ xanh.
- Tăng retry attempts vô hạn.
- Xóa request ledger khi gặp duplicate.
- Gửi lại giao dịch tiền mà chưa xác minh commit.
- Broad silence toàn bộ production.

### Phục hồi

1. Write success SLO ổn định qua cửa sổ đã định.
2. Request backlog giảm, pool/DB topology ổn.
3. Known unknown writes được reconciliation theo requestId.
4. CDC/read models bắt kịp nếu bị ảnh hưởng.
5. Ghi incident timeline và follow-up root causes.

## 58. Case study A: một root cause, hàng trăm child alerts

### Trước khi cải tiến

```text
Mongo primary election loop
   -> 20 pods x 2 alerts each
   -> 12 shard/node exporter alerts
   -> 5 services x 3 SLO alerts
   -> 3 paging tools receive repeated alerts
```

Người trực nhận hàng chục pages trong hai phút.

### Sau khi cải tiến

- **Một user-facing SLO incident** đại diện cho checkout/orders impact.
- **Một root cause cluster alert** route đúng database on-call.
- Group `MongoClientConnectionErrors` theo cluster/environment thay vì pod.
- Inhibit low-level warnings cùng cluster khi `MongoPrimaryUnavailable` confirmed.
- Attach SLO, topology, retry/pool lag metrics vào incident.
- Child alerts vẫn được lưu trong event timeline để forensic.
- Giữ backup, data corruption và cross-region independent alerts **không bị inhibit**.

### Điều kiện đánh giá

Không chỉ đếm notifications giảm. Phải xem:

- Thời gian detect impact có tăng không?
- Đúng owner có nhận page không?
- Có mất incident độc lập không?
- Có evidence để root-cause không?
- Sau election, CDC lag còn được xử lý không?

## 59. Case study B: metric thấp nhưng nguy cơ dữ liệu cao

Một connector CDC chậm do schema migration:

```text
Orders API success ratio:        99.99% (healthy)
Orders API latency p99:          110 ms (healthy)
CDC oldest unapplied event age:  20 minutes (bad)
Search freshness SLO:            60 seconds
Source log retention left:       45 minutes
```

Nếu chỉ alert API 5xx, sự cố bị bỏ qua. Nếu chỉ alert “Kafka lag > 10,000” mà connector đang xử lý events nhỏ nhanh, metric đó không đo đúng business freshness.

### Cảnh báo phù hợp

1. `OrderSearchFreshnessSLOBurn` page search/pipeline owner.
2. `CDCSourceLogRetentionAtRisk` page data platform nếu margin không đủ để phục hồi.
3. `KafkaConsumerOffsetLagHigh` làm child context hoặc warning, không nhất thiết một page riêng mỗi partition.
4. `SchemaDecodeFailures` định hướng nguyên nhân, kèm samples đã redacted.

### Hành động

- Chặn/rollback schema incompatible writer nếu an toàn và có policy.
- Fix consumer decoder.
- Tránh checkpoint nhảy qua poison events.
- Bảo đảm source retention còn đủ; resnapshot plan nếu gap không thể replay.
- Xác nhận **end-to-end search visible revision** đã bắt kịp, không chỉ offset lag về 0.

### Điểm rút ra

**Một hệ có availability xanh vẫn có thể hỏng freshness/durability.** Alert phải phản ánh hợp đồng dữ liệu chứ không chỉ host health.

## 60. Case study C: noise tăng vì alert labels thay đổi mỗi lần scrape

Team tạo label:

```text
alertname=MongoPoolWaitHigh
pod=orders-17
current_wait_ms=180
```

Sau 30 giây:

```text
alertname=MongoPoolWaitHigh
pod=orders-17
current_wait_ms=245
```

Nếu fingerprint tính cả `current_wait_ms`, đây là **alert mới**. `for: 5m` có thể mãi không đủ lâu để firing hoặc mỗi thay đổi tạo một notification mới khi expression cấu hình khác.

### Sửa

```text
labels:
  alertname = MongoPoolWaitHigh
  service = orders
  environment = prod
  cluster = mongo-orders

annotations:
  current_wait_ms = ... current query value ...
```

Vẫn cần cân nhắc annotation updates có gây notifications không. Giá trị quan sát chính nên đọc từ dashboard, không phải biến thành identity.

### Kiểm tra sau sửa

Replay một chuỗi metric đổi 180→245→300 khi condition vẫn true. Alert identity phải giữ ổn định; thông báo không lặp mỗi evaluation.

## 61. Case study D: planned maintenance nhưng hai vấn đề độc lập

DBA thay một Mongo replica ở AZ-1, có maintenance silence cho:

```text
environment=prod, cluster=mongo-orders, node=replica-3
alertname=MongoNodeRestarting
```

Cùng lúc search pipeline ở region khác có decode errors do deploy sai.

### Đúng

- Node restart notification của replica-3 bị silence trong maintenance window.
- Orders write SLO vẫn được theo dõi và page nếu thật sự suy giảm.
- Search decoder incident vẫn page pipeline owner.
- Silence hết hạn sau maintenance và DBA xác minh replication health.

### Sai

Silence toàn bộ `environment=prod`, khiến decoder incident lẫn backup failure không báo. Một maintenance phải **giảm nhiễu dự đoán được**, không tắt cảnh báo cho mọi thứ có thể xảy ra.

## 62. Xây alert từ SLO và runbook theo chiều ngược

Thay vì:

```text
Metric -> arbitrarily choose threshold -> page everyone
```

hãy làm:

```text
Business invariant / SLO
       |
       v
Who owns the impact?
       |
       v
What response is required, and by when?
       |
       v
Which observable signal proves it?
       |
       v
Rule, windows, thresholds, coverage
       |
       v
Runbook and escalation
       |
       v
Test incidents / tune / review
```

### Những câu hỏi phải có câu trả lời

- Nếu alert không page, hậu quả có thể xảy ra trước ca làm việc tiếp theo không?
- Nếu alert page, người trực có thể làm gì mà không gây rủi ro hơn?
- Có test nào làm nó firing và test nào xác nhận nó không firing sai không?
- Nếu metric mất, có phát hiện mất visibility không?
- Nếu root cause đã được biết, có bớt notifications phụ nhưng vẫn giữ impact signal không?
- Nếu một incident độc lập xuất hiện cùng thời điểm, rule có che nó không?
- Nếu một alert firing liên tục một ngày, có escalation và update hợp lý không?

### Alert là một sản phẩm vận hành

Giống API hoặc schema, mỗi alert có **owner, hợp đồng, version/change history, tests, runbook và maintenance plan**. Đừng tạo hàng trăm alert rules mà không có vòng đời quản trị.

## 63. Hai mươi lăm bài tập thực hành

### Bài 1 — Cảnh báo nào cần đánh thức on-call?

Một service MongoDB có CPU tăng từ 30% lên 60% trong 2 phút, nhưng read/write SLO vẫn tốt. Một service khác có 20% write attempts thất bại trong 5 phút. Phân loại page, ticket hoặc dashboard cho hai tình huống và giải thích dựa trên tác động.

### Bài 2 — Viết actionable alert

Sửa alert `RedisMemoryHigh` thành một thông báo có tên, phạm vi, impact, observed value, owner, runbook, bước xác minh và điều kiện resolved. Tránh mặc định “memory 80% là sự cố”.

### Bài 3 — Tỷ lệ lỗi và traffic

Service A có 2 lỗi/2 requests; service B có 500 lỗi/100.000 requests trong 5 phút. Tính error ratio của cả hai, nêu những dữ liệu bổ sung cần xem trước khi page.

### Bài 4 — Error budget

Với availability SLO 99.95% trong 30 ngày, tính error budget theo thời gian nếu traffic uniform. Giải thích vì sao phép đổi sang phút không chính xác khi SLO dùng tỷ lệ requests và traffic biến thiên theo giờ.

### Bài 5 — Burn rate

SLO 99.9%, tỷ lệ lỗi 0.5%. Tính burn rate. Nếu tỷ lệ chỉ tồn tại trong 30 giây, nên xem cửa sổ nào để tránh page vì spike nhưng không bỏ sự cố lớn?

### Bài 6 — Logical request vs driver attempts

Một request thanh toán thử write 3 lần, hai lần đầu timeout, lần ba thành công theo hợp đồng. Hãy tính số logical requests, driver attempts, timeout attempts và user-visible failures. Metric nào thuộc availability SLO?

### Bài 7 — Label fingerprint

Alert có label `current_latency_ms` thay đổi mỗi 30 giây. Giải thích tại sao dedup và `for` có thể hỏng. Chuyển dữ liệu nào sang annotations?

### Bài 8 — Grouping pods

30 pods đều có `MongoClientConnectionErrors` vì một cluster unavailable. Thiết kế group key giảm thông báo, nhưng vẫn giữ alerts của region B độc lập với region A.

### Bài 9 — Inhibition

`MongoPrimaryUnavailable` đã firing; 20 child `MongoClientConnectionErrors` warnings xuất hiện. Viết inhibition scope phù hợp. Vì sao không inhibit `OrdersDataDivergenceDetected` cùng cluster?

### Bài 10 — Maintenance silence

DBA nâng cấp replica-3 trong 20 phút. Thiết kế silence matcher, thời hạn, ticket và bước verify. Giải thích rủi ro silence mọi severity critical trong production.

### Bài 11 — Chọn người nhận

Một cảnh báo CDC source log retention còn 30 phút, nhưng nhóm ứng dụng chỉ quan sát Kafka consumer lag. Xác định first responder và supporting team. Vì sao route vào channel chung không đủ?

### Bài 12 — Mất metric

Exporter replication lag chết và metric biến mất. Vì sao rule `lag > 60` có thể không firing? Viết một signal giám sát missing data và mô tả synthetic probe cần thiết.

### Bài 13 — Low traffic

Một API có 1 request/5 phút và request đó 500. Thiết kế kết hợp ratio/volume guard với no-traffic probe để không bỏ outage thật.

### Bài 14 — Hysteresis

Disk usage dao động 79–82% quanh threshold 80%. Đề xuất enter/resolve thresholds và thời gian duy trì, nhưng chỉ ra trường hợp capacity forecast cần page sớm hơn.

### Bài 15 — Mongo primary election

Một election dài 6 giây, retry phía app thành công, write SLO vẫn ổn. Có nên page cả app và DBA không? Nếu elections lặp 10 lần và write errors tăng, chính sách phải thay đổi thế nào?

### Bài 16 — Redis eviction

Redis evicted keys tăng mạnh nhưng cache p99 và backend read p99 vẫn tốt. Một giờ sau MongoDB pool wait tăng và checkout SLO xấu. Hãy phân biệt warning vs page, và nhóm alerts ra sao.

### Bài 17 — Cassandra tombstones

Query trả 20 rows nhưng đọc qua hàng nghìn tombstones; p99 tăng. Vì sao page dựa trên `LIMIT 20` hoặc chỉ CPU có thể bỏ nguyên nhân? Hãy thiết kế diagnostic dashboard/runbook.

### Bài 18 — DynamoDB throttling

SDK retry 5% attempts, cuối cùng 99.99% logical writes thành công trong SLO. Một tuần sau retry storm làm p99 vượt threshold. Khi nào throttling là capacity warning, khi nào là page?

### Bài 19 — CDC backlog

Kafka consumer offset lag bằng 0 nhưng search documents trễ 3 phút. Hãy mô tả metrics/correlation để phân biệt consumer progress và search visibility.

### Bài 20 — Backup failure

API đang healthy, nhưng lần verified restore point gần nhất đã 10 ngày và RPO yêu cầu 24 giờ. Tại sao đây là actionable alert? Ai chịu trách nhiệm, và runbook cần làm gì?

### Bài 21 — Cross-tenant invariant

Một consistency checker xác nhận record tenant A được trả cho principal tenant B. Có nên yêu cầu metric vi phạm liên tục 5 phút hoặc ít nhất 100 requests không? Tại sao?

### Bài 22 — PromQL histogram

Ba pods có p99 lần lượt 100, 500, 50 ms với traffic khác nhau. Giải thích vì sao không thể lấy trung bình ba p99 để kết luận p99 toàn service. Viết cách aggregate histogram buckets thích hợp.

### Bài 23 — Historical alert replay

Chọn một incident giả với ba phút đầu chỉ có driver timeouts, sau đó SLO burn. Đánh giá hai cấu hình: page lỗi driver ngay; page chỉ khi burn window đạt ngưỡng. Đề xuất cân bằng detection delay và notification noise.

### Bài 24 — Incident deduplication

Một alert chuyển warning→critical và thay đổi label `severity`, tạo fingerprint mới. Thiết kế correlation bằng service/cluster/root-cause class và incident ID, nhưng vẫn gửi một escalation khi impact thật tăng.

### Bài 25 — Xây alert policy cho hệ đa NoSQL

Thiết kế catalog cho hệ `Java API -> Redis cache -> MongoDB orders -> CDC -> Kafka -> Elasticsearch` với:

- Hai user-facing SLO alerts.
- Một freshness SLO.
- Ba capacity/diagnostic alerts.
- Một observability pipeline/no-data alert.
- Một data invariant/security alert.
- Grouping/inhibition/silence/routing.
- Owner/runbook/incident escalation.
- Tests cho failover, cache stampede, CDC stuck, low traffic và independent incidents.

Giải thích cảnh báo nào cần page, cái nào tạo ticket, cái nào chỉ làm context cho root incident.

## 64. Checklist trước khi bật paging cho một NoSQL alert

### 64.1. Đúng tác động và đúng ngữ nghĩa

1. Tín hiệu gắn với **business invariant, SLI/SLO hoặc capacity threat** có thể can thiệp được chưa?
2. Có biết khách hàng/endpoint/tenant tier bị ảnh hưởng không?
3. Có phân biệt logical operations và driver retry attempts không?
4. Có phân biệt read/write availability, freshness, durability và correctness không?
5. Có bao nhiêu thời gian để hành động trước khi impact không thể đảo ngược?
6. Nếu một metric mất hẳn, alert có im lặng giả không?
7. Có đo traffic volume, no-traffic và synthetic probes khi cần không?
8. Ngưỡng/cửa sổ có dựa SLO, baseline và incident history không?

### 64.2. Đúng mức độ ưu tiên và ownership

9. Nếu page lúc 03:00, người nhận có cần làm gì ngay không?
10. First responder được xác định trong service catalog chưa?
11. Đội phối hợp/escalation được định nghĩa chưa?
12. Alert title có nói đúng impact, scope và triệu chứng không?
13. Annotation có dashboard, runbook, giá trị và khoảng thời gian không?
14. Runbook có bước xác minh an toàn và những thao tác **không được làm** không?
15. Điều kiện phục hồi có bao gồm backlog/data correctness sau khi latency ổn không?

### 64.3. Chống báo trùng nhưng không che sự cố thật

16. Fingerprint labels có **ổn định** giữa các evaluations không?
17. Có label động như current_value, requestId, timestamp hoặc orderId không?
18. Group key có phản ánh cùng owner/cùng incident scope không?
19. Group có gộp nhầm các services/regions độc lập không?
20. Inhibit có giới hạn theo root cause được xác minh và child alerts thích hợp không?
21. Data-loss, data-corruption, security và backup alerts có tránh bị inhibit sai không?
22. Khi root alert resolved, child còn lỗi có tái hiện không?
23. Silence có owner/ticket/thời hạn/scope hẹp không?
24. Repeat interval/escalation có tránh spam nhưng vẫn nhắc khi chưa ai nhận không?

### 64.4. Khả năng vận hành và kiểm thử

25. Nhãn metric có bounded cardinality và không chứa PII không?
26. Có dashboard phân tầng user SLI, driver, connection pool, server và CDC không?
27. Có test rule pending/firing/resolved và flapping không?
28. Có test notification grouping/routing/inhibition trên sandbox không?
29. Có test exporter down, source lag, quorum loss, low-traffic outage không?
30. Có test **hai independent incidents đồng thời** không?
31. Có kiểm tra alerts sau deploy/maintenance window không?
32. Có theo dõi pages/shift, false positives, duplicates và missed incidents không?
33. Có process review/retire alerts khi service và team thay đổi không?
34. Có backup/heartbeat cho bản thân monitoring/notification pipeline không?
35. Tự động mitigation (nếu có) có guardrails, audit và rollback không?

## 65. Kết luận

Một hệ NoSQL quan sát tốt không phải hệ phát nhiều cảnh báo nhất. Nó là hệ giúp người trực:

1. **Biết sự cố nào ảnh hưởng người dùng hoặc đe dọa dữ liệu.**
2. **Biết ai phải xử lý và hành động nào cần làm trước.**
3. **Phân biệt triệu chứng và giả thuyết nguyên nhân.**
4. **Không bị hàng trăm notifications trùng làm che mất tín hiệu quan trọng.**
5. **Vẫn nhìn thấy sự cố độc lập, mất telemetry và những rủi ro dữ liệu không biểu hiện qua HTTP 5xx.**

Các điểm chính:

- **Cảnh báo phải có hành động.** Mỗi page cần owner, impact, urgency, runbook và điều kiện phục hồi.
- **Dùng SLI/SLO và error-budget burn rate** để đánh giá tác động, nhưng thêm guards cho traffic thấp và probes cho outage không có traffic.
- **Grouping không phải xóa alerts.** Gom nhiều instances thuộc cùng workflow; giữ raw evidence và incident relationships.
- **Dedup phụ thuộc labels ổn định.** Đặt current values trong annotations/dashboard, tránh request IDs và nhãn cardinality lớn.
- **Inhibition phải có quan hệ nhân quả đủ tin.** Không suppress SLO-critical, mất dữ liệu, backup hoặc security alert chỉ vì cùng cluster.
- **Silence cho maintenance có thời hạn và phạm vi hẹp.** Đừng dùng broad mute để che alert fatigue.
- **NoSQL cần tín hiệu đặc thù:** MongoDB elections/replica lag, Redis cache stampede, Cassandra tombstone/compaction, DynamoDB throttling, CDC freshness/retention, search visibility và khả năng restore.
- **Missing metrics khác healthy metrics.** Giám sát cả observability pipeline và notification delivery.
- **Kiểm thử alert như kiểm thử code.** Dùng rule tests, historical replay, fault injection và on-call review để vừa giảm noise vừa không bỏ sót incidents.

Trước khi thêm một alert mới vào kênh paging, hãy hỏi:

> **“Người trực sẽ làm điều gì khác nhờ thông báo này, nó có mang thêm thông tin/action mới so với incident đang mở không, và nếu mình group hoặc tắt thông báo phụ thì có vô tình bỏ qua một sự cố độc lập hay một rủi ro dữ liệu không?”**

Nếu trả lời rõ, có bằng chứng và có runbook thực thi an toàn, đó là một **cảnh báo có thể hành động**. Khi nhiều cảnh báo được thiết kế theo nguyên tắc ấy, đội vận hành có thể nhận ít thông báo hơn nhưng **phát hiện và xử lý sự cố NoSQL đáng tin cậy hơn**.
