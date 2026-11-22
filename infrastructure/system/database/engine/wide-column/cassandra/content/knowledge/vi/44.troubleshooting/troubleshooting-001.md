# Khoanh vùng thời điểm, phạm vi, thay đổi gần nhất và bằng chứng

> **Chương:** Xử lý sự cố  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — hiểu kiến trúc phân tán và mô hình wide-column Apache Cassandra, khóa phân vùng, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi, CQL, replication, compaction, repair, lỗi phân tán và kết nối ứng dụng Java.

Một dịch vụ Java báo “Cassandra chậm” sau đợt triển khai. Nhóm ứng dụng nhìn thấy HTTP p99 tăng, nhóm database thấy `nodetool status` tất cả node đều `UN`, nhóm hạ tầng thấy disk còn trống. Ba quan sát **đều có thể đúng** nhưng chưa cho biết lỗi bắt đầu lúc nào, chỉ ảnh hưởng truy vấn nào, một DC hay cả cụm, có liên quan đợt triển khai không, hoặc thành phần nào đang tạo độ trễ.

**Troubleshooting tốt bắt đầu bằng bốn câu hỏi có bằng chứng:**

1. **Thời điểm:** triệu chứng xuất hiện từ khi nào; lần cuối chắc chắn bình thường là lúc nào; khoảng chưa biết lớn bao nhiêu?
2. **Phạm vi:** user/API, service version, AZ/DC, keyspace/table, query shape, partition, coordinator hoặc replica set nào bị ảnh hưởng?
3. **Thay đổi gần nhất:** trước đó có deploy, schema migration, thay CL/TTL, tăng tải, node restart, repair, compaction, certificate rotation hoặc network change nào không?
4. **Bằng chứng:** metrics, logs, traces, `nodetool`, dữ liệu CQL, driver errors nào xác thực hoặc bác bỏ giả thuyết; nguồn, timestamp và độ tin cậy của chúng ra sao?

Bài học này xây **quy trình khoanh vùng và lưu giữ bằng chứng**, không phải danh sách lệnh để chạy bừa. Mục tiêu là thu hẹp không gian tìm kiếm và tránh biến một sự cố nhỏ thành outage rộng hơn do thao tác hấp tấp.

> **Phiên bản và an toàn:** ví dụ cho Cassandra 4.x–5.x, Java Driver 4.x (tham chiếu 4.19), Linux và hệ quan sát phổ biến. Lệnh chủ yếu **chỉ đọc**; cú pháp, metrics và log paths thay đổi theo bản đóng gói/exporter. Mọi tên cluster, số liệu, mốc giờ và UUID trong tình huống đều là **minh họa**, không phải kết quả đo hệ thống thực. Với production, tuân thủ incident runbook, quyền truy cập và quy trình thay đổi của tổ chức.

## 1. Mục tiêu học tập

Học xong bài, bạn có thể:

1. Viết một **incident statement có thể kiểm chứng**: dấu hiệu, thời điểm, phạm vi, mức ảnh hưởng và mức chưa chắc chắn.
2. Phân biệt thời điểm **khách hàng thấy lỗi**, **monitor phát hiện**, **deploy**, **node xảy ra lỗi** và **bắt đầu thu thập bằng chứng**.
3. Lập timeline chuẩn UTC với `last-known-good`, `first-known-bad`, độ phân giải của metric và clock skew.
4. Tạo ma trận ảnh hưởng theo service/API, query, partition key, keyspace/table, coordinator, replica set, DC/rack và client version.
5. Dùng `nodetool status/tpstats/proxyhistograms/tablehistograms/tablestats/compactionstats/netstats` đúng mục đích, không đánh đồng một snapshot với toàn bộ sự thật.
6. Đọc `system.log`, `debug.log`, GC logs, driver metrics và query traces **có cửa sổ thời gian** thay vì grep toàn bộ rồi suy nguyên nhân.
7. So recent changes với triệu chứng trên cơ sở **thứ tự thời gian, phạm vi khớp và cơ chế kỹ thuật**; tránh ngụy biện “sau deploy nên do deploy”.
8. Xây evidence ledger với nguồn, thời gian, đơn vị, thao tác thu thập và tác động tới hệ thống.
9. Đề xuất giả thuyết có phép kiểm thử bác bỏ được; phân biệt **quan sát**, **suy luận** và **quyết định giảm thiểu**.
10. Tạo một bản bàn giao incident đủ để người trực tiếp theo ca hoặc hậu kiểm tiếp tục mà không cần lặp lại các bước đã chạy.

## 2. Bốn trục điều tra không được bỏ sót

~~~mermaid
flowchart TD
    A["Tín hiệu: Cassandra chậm / lỗi"] --> B["THỜI ĐIỂM<br/>last good, first bad, window"]
    A --> C["PHẠM VI<br/>client → query → coordinator → replica/DC"]
    A --> D["THAY ĐỔI<br/>deploy, config, schema, capacity, background"]
    A --> E["BẰNG CHỨNG<br/>metrics, logs, traces, nodetool"]
    B --> F["Giả thuyết có thể bác bỏ"]
    C --> F
    D --> F
    E --> F
    F --> G["Kiểm tra ít tác động"]
    G --> H{"Khớp nhiều nguồn độc lập?"}
    H -->|Có| I["Mitigation có kiểm soát + xác minh"]
    H -->|Chưa| J["Thu thập thêm, cập nhật bất định"]
    J --> B
    I --> K["Timeline và post-incident evidence"]
~~~

### 2.1. Bốn câu trả lời phải đi cùng nhau

| Câu hỏi | Câu trả lời thiếu | Câu trả lời có thể hành động |
|---|---|---|
| Khi nào? | “Từ sáng nay” | “p99 bắt đầu vượt SLO trong bucket 09:42–09:43 UTC; last normal 09:40–09:41; alert phát 09:45” |
| Ở đâu? | “Cassandra chậm” | “Chỉ API `GET /devices/{id}/events` từ deployment v28 trong dc1; read p99 ở 2/3 coordinators tăng, dc2 bình thường” |
| Sau thay đổi gì? | “Có deploy” | “v28 lên 20% traffic lúc 09:39; query bắt đầu thiếu event_day trong prepared CQL hoặc bị thêm filtering — **chưa xác minh**” |
| Chứng cứ? | “Dashboard đỏ” | “HTTP p99, DriverTimeoutException count, tracing một mẫu SELECT, server coordinator histograms; timestamps và link artifact” |

Các con số trong ví dụ **không phải SLA chung**. Một incident statement nên có mốc thời gian, query fingerprint, CL và tỷ lệ lỗi, kể cả khi ban đầu chỉ biết “unknown”.

### 2.2. Ba tầng cần phân biệt ngay

1. **Triệu chứng người dùng:** HTTP 5xx, timeout, dữ liệu thiếu, stale read, latency cao.
2. **Tín hiệu driver/coordinator:** connection/pool exhaustion, retry/speculation, request timeout, unavailable, throttling, write/read timeout.
3. **Tình trạng replica/storage:** node Down/Joining, GC, disk queue, tombstone scan, compaction backlog, schema/version mismatch.

Không suy thẳng từ `HTTP 504` ra “replica chết”. HTTP timeout có thể đến từ gateway, queue, auth, service thread pool, Driver throttler, network hay Cassandra. Cũng không suy từ mọi node `UN` rằng mọi query đều khỏe: một partition nóng, nhiều tombstones hoặc pool nghẽn vẫn có thể gây p99 xấu.

## 3. 0–5–15–30 phút: trình tự khoanh vùng ban đầu

### 3.1. Trong 0–5 phút: bảo vệ hiện trạng và đánh giá mức độ

Ghi trước **một dòng trạng thái**:

~~~text
INC-2026-11-21-01 (ví dụ)
Detected: 2026-11-21T09:45:00Z
Symptom: GET /events p99 vượt SLO, 2.7% timeout
Affected: service-events v28, dc1; dc2 chưa rõ
Start: first-bad trong [09:42,09:43] UTC (bucket 1 phút)
Last-known-good: [09:40,09:41] UTC
Change candidates: deploy v28 lúc 09:39; compaction lúc 09:41
Evidence links: dashboard snapshot #1, driver logs #2, node metrics #3
Severity/owner: theo runbook nội bộ
Confidence: LOW; chưa biết nguyên nhân
~~~

**Ưu tiên ngay:** phát hiện nguy cơ mất dữ liệu, ngừng ghi, bảo mật, disk full, nodes Down hàng loạt hoặc vi phạm SLO nghiêm trọng. Có thể cần mitigation song song với điều tra, nhưng vẫn phải lưu **snapshot tối thiểu trước khi thay đổi** nếu an toàn; không trì hoãn hành động khẩn cấp chỉ để có báo cáo đẹp.

### 3.2. Trong 5–15 phút: khoanh vùng phạm vi

- So một **healthy cohort** và một **affected cohort**: cùng query nhưng client version khác, cùng service nhưng DC khác, hoặc cùng DC nhưng table khác.
- Quan sát **last-known-good → first-bad** theo một dashboard dùng cùng timezone.
- Thu `nodetool status` từ **hơn một node** khi nghi gossip/network partition.
- Xem driver/server timeout types, không gộp `DriverTimeoutException` với `ReadTimeoutException`.
- Kiểm tra recent changes có trùng **cửa sổ và phạm vi** không.
- Ghi “chưa kiểm tra” thay vì để ô trống khiến người sau nghĩ đã kiểm tra và bình thường.

### 3.3. Trong 15–30 phút: thử giả thuyết và giảm thiểu có kiểm soát

Tạo tối đa vài giả thuyết có trọng số, mỗi giả thuyết có:

~~~text
Hypothesis H1: v28 tăng page size / query fan-out
Predicts: chỉ v28 bị; rows/page và bytes/request tăng;
          Cassandra coordinator read latency hoặc pool pressure tăng
Falsifier: v27/v28 cùng payload, cùng latency/error, query shape không đổi
Low-risk check: so query fingerprints, metrics per deployment, prepared CQL
Mitigation candidate: rollback/traffic shift có kiểm soát nếu đủ bằng chứng
Owner / timestamp / decision record: ...
~~~

Không bật đồng thời nhiều “fix” như restart nodes, đổi CL, tăng timeout, chạy major compaction và rollback service — sẽ rất khó phân biệt thao tác nào tạo thay đổi, đồng thời có nguy cơ phá cluster.

### 3.4. Khung trách nhiệm

| Vai trò | Cần làm | Tránh |
|---|---|---|
| Incident commander | Phạm vi/severity, quyết định, đồng bộ timeline | Tự suy cause khi chưa có bằng chứng |
| Application owner | HTTP/driver traces, deploy diff, request fingerprints | Đổ lỗi Cassandra từ HTTP 504 |
| Cassandra operator | node/DC, gossip, JMX, storage, logs và repair state | Chạy thao tác phá trạng thái trước khi thu snapshot |
| SRE/Infrastructure | Network, disk, CPU, DNS/TLS, host/container events | Chỉ xem average CPU rồi tuyên máy khỏe |
| Scribe/evidence owner | Timestamp UTC, nguồn, links, tác động thao tác | Ghi “fix xong” nhưng không có before/after |

Quy trình có thể do một người thực hiện trên lab; khi là production incident, trách nhiệm và quyền thay đổi phải tuân thủ runbook vận hành thực.

## 4. Khoanh vùng **thời điểm** bằng độ phân giải đúng

### 4.1. Bốn mốc dễ bị đánh đồng

| Mốc | Giải thích | Cách thu |
|---|---|---|
| `T_last_good` | Bucket/điểm cuối cùng có bằng chứng vẫn bình thường | SLO/error/latency series |
| `T_first_bad` | Bucket/điểm đầu tiên có bằng chứng vượt ngưỡng | Metric raw hoặc histogram theo cửa sổ |
| `T_alert` | Hệ thống cảnh báo phát ra | Alert evaluation time + pending/for duration |
| `T_detected` | Con người/hệ thống ghi nhận incident | Pager/incident channel |
| `T_change` | Một thay đổi có thể liên quan bắt đầu hoặc hoàn tất | Deployment/migration/host event log |
| `T_collection` | Lúc điều tra viên lấy snapshot | Capture time + source clock |

**`T_alert` không nhất thiết bằng `T_first_bad`.** Ví dụ alert chạy mỗi phút và yêu cầu điều kiện kéo dài 5 phút, thời gian phát cảnh báo có thể sau khi lỗi bắt đầu nhiều phút. Nếu chỉ biết “lần đầu bị” trong bucket 09:42–09:43, đừng bịa mốc chính xác 09:42:13.

### 4.2. Luôn dùng UTC trong sổ incident

Trên Linux được phép đọc thời gian:

~~~bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
date +"%Y-%m-%dT%H:%M:%S%z"
timedatectl status
~~~

Logs nhiều ứng dụng dùng local timezone, một số dashboard dùng timezone trình duyệt và Cassandra `system.log` có định dạng riêng theo logback config. Chuyển tất cả về **UTC có offset được ghi rõ**, nhưng giữ nguyên timestamp nguồn trong artifact. Không giả định hai host có đồng hồ đồng bộ hoàn hảo: kiểm tra NTP/chrony và clock offset nếu thứ tự sự kiện lệch bất thường.

### 4.3. Wall clock khác monotonic duration

Để đo **thời gian đã trôi** trong ứng dụng Java, dùng `System.nanoTime()` (monotonic tương đối); để gắn mốc UTC vào log, dùng `Instant.now()` hoặc telemetry timestamp có timezone.

~~~java
import java.time.Instant;
import java.util.concurrent.TimeUnit;

Instant startedUtc = Instant.now();
long begin = System.nanoTime();
try {
    // Gọi repository/driver đã được đo instrumentation ở nơi thực.
} finally {
    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
        System.nanoTime() - begin);
    System.out.printf("started_utc=%s elapsed_ms=%d%n",
        startedUtc, elapsedMs);
}
~~~

Không dùng `Instant.now()` hai lần rồi trừ cho latency rất ngắn nếu clock có thể được điều chỉnh. Ngược lại, giá trị `nanoTime()` **không có nghĩa là một timestamp UTC để đối chiếu giữa các máy**.

### 4.4. Khoảng chưa biết (uncertainty interval)

Nếu metric chỉ có sampling mỗi 60 giây:

~~~text
Last good bucket       09:40–09:41 UTC
First bad bucket       09:42–09:43 UTC
Unknown transition     trong khoảng từ sau last-good tới first-bad
Deploy started         09:39 UTC
Node GC pause observed 09:42:10 UTC (clock offset cần kiểm tra)
~~~

Chưa thể biết deploy gây GC hay GC ngẫu nhiên trùng thời điểm. Thu finer-grained log/traces và kiểm tra lặp lại theo instance để thu hẹp window. **Một timestamp rất chính xác từ log không mặc nhiên đáng tin hơn metric thô** nếu clock source chưa đồng bộ hoặc event diễn ra sau triệu chứng.

### 4.5. Thu hẹp cửa sổ bằng cách nhìn trước và sau

Một cửa sổ hợp lý:

~~~text
T_pre   = last-good trừ 30–60 phút (hoặc một chu kỳ tải nền có nghĩa)
T_fault = first-bad tới thời gian hiện tại
T_post  = sau mitigation / after recovery
~~~

Chọn độ rộng phù hợp lịch sử hệ thống. Với compaction/repair hoặc TTL aging, cần quan sát **trước nhiều giờ/ngày**; với TLS certificate rotation có thể cần mốc expiry cụ thể. Không chỉ lấy 5 phút đỏ, vì mất baseline khiến mọi metric trông “cao” mà không biết cao so với gì.

## 5. Khoanh vùng **phạm vi** theo các lớp Cassandra

### 5.1. Bản đồ từ người dùng tới replica

~~~mermaid
flowchart TD
    A["User/Request/Region"] --> B["Gateway / API instance"]
    B --> C["Repository / CqlSession"]
    C --> D["Driver pool, LB policy, retry, TLS, local DC"]
    D --> E["Coordinator node"]
    E --> F["Replica set theo partition token + RF/DC"]
    F --> G["Memtable / SSTables / tombstones / IO"]
    H["Query shape + partition key + CL + page size"] --> D
    I["Topology/gossip/repair/compaction"] --> E
    I --> F
~~~

Một query có thể được gửi tới coordinator không sở hữu partition key, rồi coordinator liên hệ replicas theo token và replication strategy. **Coordinator chậm không nhất thiết là replica chứa dữ liệu bị lỗi**. Phải thu cả client-side execution info/coordinator và server-side replica observations (nếu có) trước khi kết luận “node X chứa key lỗi”.

### 5.2. Ma trận blast radius bắt buộc

| Chiều | Phân nhóm cần so | Dấu hiệu gợi ý |
|---|---|---|
| **Người dùng** | Tenant/khu vực/loại thiết bị, mức traffic | Một tenant rất nóng hoặc toàn bộ users |
| **API/use case** | GET latest-N vs range export vs INSERT/LWT | Một query pattern/filtering hoặc toàn bộ CQL |
| **Service** | App instance/pod, deployment version, JVM | Lỗi chỉ v28, driver config khác |
| **Đường kết nối** | Source AZ/VPC, LB, TLS/auth, driver pool | Một nhóm instance mất kết nối |
| **CQL** | Prepared fingerprint, table/keyspace, CL, page size | Một keyspace hoặc một statement regression |
| **Dữ liệu** | Partition/bucket age, hot keys, tombstone density | Một vài keys/partitions lớn |
| **Coordinator** | Node được driver chọn | Một node chậm hoặc mọi coordinator |
| **Replicas** | Token range, RF, DC/rack replica placement | Replica-set overlap / DC outage |
| **Hạ tầng** | Disk/device, CPU/GC, network/switch/AZ | Tác động khu vực/nút cụ thể |
| **Thời gian** | Peak hour, repair, compaction, TTL burst | Trùng background task hoặc burst load |

Thứ tự thu hẹp thông dụng: **user/API → app version/DC → query fingerprint → partition → coordinator/replicas → storage/hardware**. Nếu điều tra chỉ ở một tầng, dễ bỏ sót sự cố bên cạnh.

### 5.3. Phân biệt “một node” và “một replica set”

Với keyspace dùng NetworkTopologyStrategy, partition token quyết định replicas; RF/CL ảnh hưởng số replica cần đáp ứng. Một read query thất bại trên một partition dù tất cả nodes `UN` có thể liên quan:

- Partition chứa quá nhiều tombstones, riêng read query đó scan lâu.
- Replica set cho token gặp IO/GC chậm trên một hoặc nhiều node.
- Consistency `LOCAL_QUORUM` không đủ phản hồi trong timeout khi một replica chậm.
- Hot key bão hòa replicas phục vụ key.
- Một coordinator/pool route không ổn định, dù replica khỏe.

Đừng quy mọi lỗi theo `IP của coordinator`, cũng đừng gộp mọi câu truy vấn trong table thành một đường thực thi.

### 5.4. Các so sánh “healthy control” hữu ích

| So sánh | Nếu chỉ nhóm A lỗi | Giả thuyết ưu tiên |
|---|---|---|
| Service v27 vs v28, cùng DC/query | Chỉ v28 | Deploy/config/driver behavior |
| Cùng service/query, dc1 vs dc2 | Chỉ dc1 | DC-local topology/network/CL |
| Cùng table, point lookup vs range scan | Chỉ range | Partition width, pagination, tombstones |
| Cùng query, key nóng vs key lạnh | Chỉ hot | Token/replica skew hoặc hot partition |
| Cùng host, một keyspace vs tất cả | Một keyspace | Schema/index/compaction/query distribution |
| Cùng driver instance, pool node A vs node B | Chỉ A | Connection/node/coordinator behavior |

Không chọn healthy control có traffic/payload/CL hoàn toàn khác rồi coi chênh lệch là bằng chứng nhân quả. Với cross-DC comparison, so cùng query consistency và routing topology trước khi kết luận.

## 6. Khoanh vùng **thay đổi gần nhất** mà không ngụy biện nhân quả

### 6.1. Change inventory nhiều lớp

Không chỉ hỏi “có deploy không?”. Trong cùng khoảng thời gian, Cassandra có thể nhận **thay đổi trực tiếp, thay đổi nền, hoặc thay đổi tải**.

| Lớp | Thay đổi cần đối chiếu | Cơ chế có thể tạo triệu chứng |
|---|---|---|
| Application | API release, query shape, mapping, cache, concurrency, pagination | N+1 queries, page fan-out, SELECT *, hot key |
| Java Driver | Driver version, local DC, timeouts, retry/speculation, pool, TLS | Coordinator selection, pool queues, error amplification |
| CQL schema | CREATE/ALTER, table/index/SAI, UDT, TTL, compaction config | Schema disagreement, index behavior, read/write amplification |
| Keyspace | RF, NetworkTopologyStrategy, CL policy, serial CL | Availability và read/write consistency |
| Cassandra server | Rolling restart/upgrade, JVM flags, heap, native protocol | GC, compatibility, connection reconnection |
| Maintenance | Repair, bootstrap, rebuild, cleanup, compaction, backup/snapshot | Streaming, disk IO, cache churn, network bandwidth |
| Data/workload | Hot tenant mới, TTL expiration burst, import/delete, daily peak | Tombstones, partition skew, writes/s tăng |
| Network/infra | DNS, NAT, firewall, AZ routing, TLS cert rotation, disk resize | Connection handshake, packet loss, disk saturation |
| Observability | Exporter/sampling/metric relabel, dashboard timezone | Chỉ “đỏ” do đo/hiển thị sai, không nhất thiết app lỗi |

**Thay đổi nền** cũng là thay đổi: không có deploy nhưng lượng dữ liệu tăng, TTL cohort hết hạn hoặc một node bắt đầu compaction dài. Ghi rõ “không thấy app deploy” khác “không có thay đổi nào”.

### 6.2. Timeline change có độ dài, không chỉ một dấu chấm

~~~text
09:38  rollout v28 bắt đầu (0% -> 20%)
09:41  compaction backlog tăng trên node N2
09:42  first-bad API p99 trên v28
09:47  rollout v28 đạt 50%
09:48  error rate tăng thêm
09:52  rollback v28 về 0%
09:54  API p99 hồi phục (giả định)
~~~

Nếu rollback và p99 cùng hồi phục, **mối liên hệ trở nên mạnh hơn**, nhưng vẫn cần xác minh: compaction có vừa kết thúc, traffic có vừa giảm, dashboard có dùng aggregate làm dữ liệu chậm xuất hiện? Trên hạ tầng phân tán, **correlation không đủ thay thế cơ chế kỹ thuật**.

### 6.3. Chấm điểm một thay đổi bằng ba phép kiểm tra

1. **Temporal fit:** thay đổi xảy ra **trước** triệu chứng, có đủ độ trễ hợp lý (deployment gradual, TTL age, repair, restart).
2. **Scope fit:** phần hệ thống thay đổi trùng phần bị lỗi (v28 pods trong dc1, một keyspace, một rack); nhóm không thay đổi có khỏe không?
3. **Mechanism fit:** có đường kỹ thuật thuyết phục (page size tăng → nhiều bytes/read → pool/GC; thiếu partition key → query reject; TLS truststore mới → SSL handshake fail).

Một thay đổi chỉ đạt temporal fit nhưng không có scope/mechanism fit là **ứng viên**, không phải root cause.

### 6.4. Tìm thay đổi có dấu vết, không hỏi theo trí nhớ

Thu từ những nguồn sẵn có theo quyền:

- Deployment events: release ID, image digest, config hash, rollout start/end, pods canary, rollback.
- DB migration logs: migration ID, CQL đã chạy, schema agreement và thời điểm.
- Cassandra `system.log`: node join/leave, schema changes, startup, GC messages.
- Infrastructure audit: maintenance, network policy, storage latency incidents, host reboot.
- Workload: QPS, write bytes, input event bursts, export jobs, TTL expiration windows.
- Feature flags: bật/tắt theo tenant/DC, **thời điểm áp dụng thực**, không chỉ thời điểm commit.

Tránh ghi secrets/giá trị credential trong change inventory. Với diff config, giữ **hash, tên setting và giá trị đã redact**; nếu cần giá trị thật để root cause, lưu vào hệ kiểm soát truy cập riêng.

### 6.5. Thử thay đổi từng biến với guardrail

Nếu phát hiện v28 khác v27 ở `pageSize`, ưu tiên so canary hoặc rollback có kiểm soát **trên cùng request cohort**. Nếu nghi compaction, thu metrics trước, **không dừng compaction bừa bãi**. Nếu nghi schema disagreement, xác minh schema và error trước, **không chạy ALTER TABLE thử trên production**.

Phép thử tốt ghi:

~~~text
Hypothesis: v28 tăng số page fetch cho latest-N.
Before: v27 p99 75ms, v28 p99 260ms (ví dụ, cùng query class).
Action: chuyển 10% traffic v28 về v27 theo runbook.
Prediction: lỗi/latency của cohort được chuyển giảm; tổng load thay đổi được tính.
Observation: điền từ metrics thực, không dự đoán.
Decision: rollback tiếp / giữ / kiểm tra khác.
~~~

Không được lặp “đổi CL từ LOCAL_QUORUM xuống ONE” như một A/B test vô hại: nó thay **hợp đồng nhất quán** và có thể tạo read stale. Đổi TTL/gc_grace/compaction cũng có tác động dài hạn, phải qua đánh giá thay đổi.

## 7. **Bằng chứng**: độ tin cậy, nguồn gốc và tác động khi thu thập

### 7.1. Bậc thang bằng chứng

| Mức | Ví dụ | Giới hạn |
|---|---|---|
| A — Quan sát trực tiếp | Driver exception type + timestamp/request ID; node logs; CQL response có CL/trace ID | Một mẫu không đại diện toàn traffic |
| B — Metric có ngữ cảnh | Error rate 1m, p99 per query, JMX per node, disk IO | Cần hiểu bucket, counter reset, units, scrape lag |
| C — Sự kiện thay đổi | Rollout event, schema migration log, node restart record | Gần thời gian lỗi nhưng chưa chứng minh cause |
| D — Suy luận | “Có thể do compaction” từ pending queue | Chỉ là giả thuyết, cần thêm phép kiểm |
| E — Tin đồn/nhớ lại | “Lần trước cũng thế, chắc disk” | Không đủ làm căn cứ thao tác rủi ro |

Không coi A là “đã chứng minh root cause”: một `ReadTimeoutException` xác nhận request đọc không đáp ứng CL trong thời hạn của nó, **không chỉ ra chính xác disk nào gây chậm**. Bằng chứng mạnh thường là **hai hay nhiều nguồn độc lập**, khớp cùng cửa sổ/phạm vi/cơ chế.

### 7.2. Evidence ledger có thể audit

~~~markdown
| Evidence ID | Captured UTC | Source clock / offset | Scope |
|---|---|---|---|
| EV-001 | 09:48:22Z | dashboard scrape 30s | HTTP p99 per v27/v28 |
| EV-002 | 09:49:05Z | node N2 clock +40ms | N2 system.log 09:38–09:49 |
| EV-003 | 09:49:31Z | nodetool run UTC | N1,N2 status views |
| EV-004 | 09:50:12Z | driver app UTC | Errors by class, coordinator |

Mỗi artifact có: URI hạn chế truy cập, collector, query/command,
unit/bucket, checksum nếu cần, độ tin cậy, ảnh hưởng của capture.
~~~

Nên giữ **raw log/metric export** và một bản tóm tắt. Một ảnh screenshot dashboard không đủ nếu thiếu timezone, query filter, trục đơn vị và time window. Nếu người khác bấm vào link sau khi metric retention hết, cần có snapshot/artifact theo chính sách.

### 7.3. Trước và sau một thao tác

Ngay trước mitigation:

~~~text
Timestamp UTC
Node/cluster/version/config state
Error rate, p95/p99, in-flight, CPU/disk, compaction backlog
Các truy vấn và sample IDs đã xác định
Action owner, lý do, rollback plan, dự đoán chỉ số sẽ đổi
~~~

Sau mitigation, thu **cùng bộ metric/filters** trong cửa sổ đủ dài, ghi những thay đổi đồng thời. Không chỉ nói “node xanh trở lại”; cần chứng minh user impact, request success, data consistency và recovery.

### 7.4. Thứ tự thu thập để không làm mất bằng chứng

**Trước:** thu log và event quanh sự cố, metrics/counters, driver errors, status/schema snapshots, topology và disk state. **Sau đó** mới xem xét các thao tác có thể thay hiện trạng như restart, flush, rolling upgrade, repair, changing compaction, schema migration.

Một số thao tác đọc vẫn có tác động:

- `nodetool` dùng JMX, có thể chậm hoặc time out trên node quá tải.
- Tracing CQL ghi thêm hệ thống traces và tạo overhead.
- Debug/TRACE logging làm tăng IO và có thể lộ nội dung nhạy cảm.
- Quét SSTables/heap dump/packet capture tốn tài nguyên và chứa dữ liệu nhạy cảm.

Chọn sampling, số lần thu và khoảng thời gian có giới hạn. Nếu node sắp hết disk, **không** bật logging/tracing ồ ạt làm trầm trọng tình trạng.

### 7.5. Tách evidence với hành động

| Thao tác | Nhóm | Cảnh báo |
|---|---|---|
| `nodetool status`, `tpstats`, `compactionstats` | Chủ yếu quan sát | JMX có overhead, output per-node/per-time |
| `SELECT ... FROM system.local`, `DESCRIBE TABLE` | Đọc metadata | Xác định đúng keyspace/DC |
| Đọc `system.log`, `debug.log`, metrics | Quan sát | Redact secrets, chính xác timezone/rotation |
| Bật tracing một query | Quan sát **có ghi hệ thống** | Chỉ sampling nhỏ, không bật mọi request |
| `setlogginglevel TRACE` | Thay hành vi ghi log | Có thể tăng IO, luôn có kế hoạch hoàn nguyên |
| `flush`, `repair`, `cleanup`, major compaction | **Can thiệp** | IO/disk/topology effects, cần runbook |
| `truncate`, `drop`, xóa SSTables/hints | **Phá dữ liệu** | Không dùng như bước “chẩn đoán” thông thường |
| Restart node | **Can thiệp** | Làm mất volatile evidence, đổi trạng thái cluster |

**Không tự diễn giải một thao tác có vẻ “read-only” là hoàn toàn không tốn tài nguyên**; cần cân nhắc mức tải hiện tại. Phân loại tác động đúng giúp điều phối ưu tiên theo mức nghiêm trọng của incident.

## 8. Thu bằng chứng **Cassandra** ở nhiều node và nhiều tầng

### 8.1. Snapshot trạng thái topology

Trên node được phép quản trị:

~~~bash
nodetool status
nodetool describecluster
nodetool info
nodetool gossipinfo
~~~

`nodetool status` hiển thị Up/Down, Normal/Joining/Leaving/Moving, DC/rack, host ID và load ước lượng; **gossip view là góc nhìn của node mà bạn hỏi**. Khi nghi network partition, so kết quả từ **ít nhất hai node khác vùng** thay vì kết luận từ một node. `UN` không chứng minh các queries đều thành công hoặc replicas đã repair.

`describecluster` giúp xem cluster name, schema/partitioner liên quan; `info` cho trạng thái node và load; `gossipinfo` có thể rất dài và chứa địa chỉ nội bộ. Thu theo cửa sổ có nhãn host/timestamp, không in ra public logs.

### 8.2. Thread pools và backlog

~~~bash
nodetool tpstats
nodetool netstats
nodetool compactionstats
~~~

`tpstats` có thể cho Active/Pending/Completed/Blocked và dropped messages theo thread pools; tên pools thay đổi theo Cassandra version. `netstats` hữu ích khi có streaming/repair/bootstrap và thông tin network streaming; **không phải bằng chứng mọi kết nối native protocol khỏe**. `compactionstats` cho thấy pending/running compactions và tiến độ/ước tính.

**Đừng đọc số Pending từ một snapshot như toàn bộ câu chuyện**: so series thời gian và derivative của Completed/Blocked/Dropped. Queue pending=0 tại lúc chụp vẫn có thể vừa bão hòa 5 phút trước, sau đó đã giảm khi tải rơi hoặc clients timeout.

### 8.3. Phân biệt coordinator latency và local storage latency

~~~bash
nodetool proxyhistograms
nodetool tablehistograms <keyspace> <table>
nodetool tablestats <keyspace>.<table>
~~~

- `proxyhistograms`: latency **ở coordinator** theo loại request (read/write/range/CAS tùy bản).
- `tablehistograms`: thông tin table-local như read/write latency, SSTables per read, partition size/cell count, theo bản Cassandra.
- `tablestats`: bảng thống kê read/write, disk, partition estimate, tombstones và SSTables.

Nếu p99 **client** cao còn coordinator p99 thấp, xem network, driver queue, application thread pools và percentile aggregation trước. Nếu coordinator p99 cao nhưng local table read latency không cao trên node coordinator, câu trả lời có thể nằm ở **replicas khác hoặc network giữa node**, không chỉ một ổ đĩa của coordinator.

**Chú ý đơn vị:** nhiều latency metrics Cassandra là microseconds, exporter có thể đổi sang seconds; driver/HTTP thường là milliseconds. So các series chỉ khi đã chuẩn hóa đơn vị, histogram bucket/window và định nghĩa của latency.

### 8.4. Bằng chứng storage và tombstones

| Tín hiệu | Cách dùng | Bẫy diễn giải |
|---|---|---|
| `EstimatedPartitionSizeHistogram` | Đuôi kích cỡ partition | Là ước lượng, không phải full scan chính xác |
| `SSTablesPerReadHistogram` | Read amplification | Không có nghĩa mỗi SSTable đều chứa row live |
| `TombstoneScannedHistogram` | Độ nặng tombstone theo query/table | Một partition nhỏ cũng có thể scan tombstones nhiều |
| `LiveSSTableCount` | Tăng/giảm SSTables | Thay đổi theo compaction/flush |
| `PendingCompactions` | Compaction backlog | Cần trend và disk/CPU correlation |
| `LiveDiskSpaceUsed`/`TotalDiskSpaceUsed` | Live vs obsolete SSTables | Chưa gồm mọi snapshot/commitlog/hints |
| GC pause/heap usage | Stop-the-world/GC pressure | Heap khỏe không đảm bảo disk/network khỏe |

So per-table/per-node theo cùng thời gian. Không lấy compaction backlog cao **một mình** làm root cause; hãy kiểm tra liệu nó bắt đầu trước p99 tăng, có IO saturation và query impact khớp không.

### 8.5. Đối chiếu logs với timeline

Các bản đóng gói Cassandra thường ghi:

~~~text
<CASSANDRA_HOME>/logs/system.log
<CASSANDRA_HOME>/logs/debug.log
<CASSANDRA_HOME>/logs/gc.log
~~~

Các gói Linux có thể đặt ở `/var/log/cassandra` hoặc gửi tới journald/container logs tùy cấu hình `logback.xml`, JVM GC flags và hạ tầng. **Xác định location thực trước khi chạy lệnh**. File `system.log` chứa startup, exceptions, GCInspector warnings, schema/topology changes; `debug.log` có thể chứa flush/compaction chi tiết và nhiều dòng hơn. Tài liệu: <https://cassandra.apache.org/doc/latest/cassandra/troubleshooting/reading_logs.html>.

~~~bash
# Thí dụ: đã kiểm tra quyền/path và timezone log.
grep -E 'WARN|ERROR|GCInspector|Exception' /var/log/cassandra/system.log
grep -E 'Compaction|Flushing|Gossip|Schema' /var/log/cassandra/debug.log
# Với bản ghi log đã rotate/compress, kiểm tra files liên quan trước.
~~~

**Không chỉ `grep ERROR`.** Ví dụ các GC pauses, status transition, hoặc compaction queue có thể được log ở INFO/WARN. Tuy nhiên, grepping cả năm log rồi thấy một ERROR cũ cũng **không** chứng minh nó liên quan incident; đối chiếu timestamp và node ID.

### 8.6. Snapshot “nhiều node” minh họa

~~~text
N1 at 09:50Z: status N1=UN N2=UN N3=UN
N2 at 09:50Z: status N1=UN N2=DN N3=UN
N3 at 09:50Z: status N1=UN N2=UN N3=UN
~~~

Đây là **gossip view bất đồng trong ví dụ**, đủ để nâng ưu tiên giả thuyết network/gossip/topology mà **chưa đủ** để kết luận N2 thực đã Down cho tất cả clients. Cần so network metrics, logs, driver topology events, host process uptime và thời gian cập nhật membership.

### 8.7. Không dùng lệnh “dọn dẹp” làm bước thu bằng chứng

Tránh hành động khi chưa có runbook và đánh giá:

~~~text
nodetool flush
nodetool cleanup
nodetool repair
nodetool compact
nodetool drain
nodetool stopdaemon
nodetool truncatehints
~~~

Các lệnh trên **có tác động trạng thái hoặc tải**, một số làm mất dữ liệu/availability nếu dùng sai. Bài học này **không yêu cầu chạy** chúng; chúng được nêu để phân biệt với bước quan sát ban đầu.

## 9. Thu bằng chứng **Java Driver và ứng dụng**

### 9.1. Bốn loại “timeout” có thể mang ý nghĩa khác

| Tín hiệu/exception | Phần nào báo? | Câu hỏi tiếp theo |
|---|---|---|
| HTTP/gateway 504 | Gateway hoặc application | Request có vào app? Đã gửi CQL chưa? Budget hết ở đâu? |
| `DriverTimeoutException` | Driver deadline khi không nhận response đúng hạn | Chờ throttler/pool/network/coordinator ở bước nào? |
| `ReadTimeoutException` | Coordinator phản hồi READ_TIMEOUT | Required/received replicas, data present, replica chậm? |
| `WriteTimeoutException` | Coordinator phản hồi WRITE_TIMEOUT | CL, required/received, write type, **unknown outcome**? |
| `UnavailableException` | Coordinator biết không đủ replicas sống cho CL | RF, DC, membership, nodes Down? |
| `RequestThrottlingException` | Driver từ chối enqueue/dispatch theo throttling policy | Client overload, queue max, offered QPS? |
| `AllNodesFailedException` | Các coordinator được thử đều thất bại | Per-node errors là pool, TLS, connectivity hay server? |
| `InvalidQueryException` / `UnauthorizedException` | Server validation/authz | Query/schema/role migration? **Không** tự retry như transient |

Tài liệu Driver 4.19 phân biệt `ReadTimeoutException` (coordinator đã trả lời lỗi) với `DriverTimeoutException` (driver không nhận response trước deadline). `WriteTimeoutException` **không** có nghĩa tất cả replicas chưa áp dụng mutation; ghi có thể đã commit nhưng acknowledgement bị thiếu. Vì vậy phải lưu **exception class thực**, không chỉ chuỗi log “timeout”.

### 9.2. Những trường log đáng thu ở application

Một request log/trace đã redact nên có:

~~~text
request_id, trace_id             : correlation IDs không chứa dữ liệu khách hàng
utc_timestamp, elapsed_ms       : mốc và thời lượng
service_version, instance, AZ/DC: cohort
cql_fingerprint                 : CQL đã chuẩn hóa, KHÔNG bind values
keyspace, table, operation      : phạm vi truy vấn
consistency, serial_consistency : contract thực thi
page_size, pages_consumed       : chi phí paging
driver_timeout_ms               : timeout được cấu hình thực
coordinator_endpoint (nếu có)   : phân tích node-specific
exception_class, error_details  : loại lỗi, không chỉ "database failed"
retry_count, speculative_count  : executions khuếch đại tải
~~~

Với thành công, `ExecutionInfo` cung cấp coordinator, tracing ID (nếu bật), server warnings và thông tin request theo API. Với exception, **không phải lúc nào cũng có ExecutionInfo hoàn chỉnh**, vì query có thể thất bại trước khi chọn coordinator; thu context từ statement, request ID và exception thay vì giả tạo coordinator “unknown IP” như có thật.

### 9.3. Ví dụ Java Driver 4.x ghi metadata của truy vấn có kiểm soát

Giả sử đã có keyspace/table theo bài lab mục 14 và `CqlSession` dùng chung; câu SELECT được prepare một lần trước khi xử lý requests:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import java.time.Duration;
import java.time.LocalDate;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

static void sampleRead(
        CqlSession session, PreparedStatement prepared,
        UUID deviceId, LocalDate eventDay, boolean sampledTrace) {

    BoundStatement statement = prepared.bind(deviceId, eventDay)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofMillis(800))
        .setPageSize(100)
        .setIdempotent(true)
        .setTracing(sampledTrace);

    Instant startedUtc = Instant.now();
    long startedNano = System.nanoTime();
    try {
        ResultSet rs = session.execute(statement);
        int received = 0;
        for (var row : rs) {
            received++;
            // Thực tế: xử lý row/DTO, không log toàn bộ payload.
        }
        ExecutionInfo info = rs.getExecutionInfo();
        System.out.printf(
            "utc=%s elapsed_ms=%d rows=%d coordinator=%s trace_id=%s%n",
            startedUtc,
            TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedNano),
            received,
            info.getCoordinator(),
            info.getTracingId());
    } catch (RuntimeException error) {
        System.err.printf(
            "utc=%s elapsed_ms=%d error_type=%s%n",
            startedUtc,
            TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedNano),
            error.getClass().getName());
        throw error;
    }
}
~~~

Prepared CQL:

~~~java
PreparedStatement prepared = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM triage_lab.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? LIMIT 100");
~~~

**Giới hạn ví dụ:**

- `getExecutionInfo()` của kết quả đồng bộ thường gắn với execution của page được quan sát; khi tiêu thụ nhiều pages, cần thu per-page execution info bằng API tương ứng, không coi một coordinator đại diện mọi page. `getAllExecutionInfo()` có thể dùng với `ResultSet` khi phù hợp Driver version.
- `setTracing(true)` tạo thêm hoạt động server-side; chỉ dùng sample nhỏ trong lab/production có phê duyệt. `getTracingId()` có thể null khi tracing không bật.
- `System.out/err` chỉ để minh họa; production dùng structured logging, sampling, redaction và tránh tạo log trên hot path gây tăng latency.
- Đây là SELECT có PK đã biết. Đừng chạy tracing trên `SELECT *` thiếu partition key hoặc export hàng triệu rows trong incident chỉ để lấy trace.
- `LOCAL_QUORUM` trong lab cần đúng RF/DC; nếu chỉ một node và RF1, thao tác vẫn có quorum=1 nhưng **không kiểm chứng high availability**.

### 9.4. Driver metrics phải bật mới quan sát được

Java Driver 4.x thường **tắt metrics mặc định**. Ví dụ cấu hình tham khảo theo Driver 4.19:

~~~hocon
datastax-java-driver.advanced.metrics {
  session.enabled = [cql-requests]
  node.enabled = [pool.open-connections, pool.in-flight]
}
~~~

Ứng dụng còn cần metrics registry/exporter được tích hợp và label/cardinality hợp lý. Tên/đơn vị metric phụ thuộc registry và mapping; xem driver config API đang dùng. Không assume có `pool.in-flight` trong Prometheus nếu config không bật hoặc exporter chưa nối.

**Khi điều tra:**

- In-flight tăng trước timeout? Có thể requests/queue bị ứ.
- Chỉ một node pool có lỗi? Kiểm tra connections, idle heartbeat, certificate/TLS và node state.
- Retry/speculative executions tăng? Actual CQL attempts có thể lớn hơn incoming HTTP requests.
- `RequestThrottlingException` xuất hiện? Driver có thể từ chối request **trước khi gửi** tới Cassandra.
- p99 server bình thường nhưng HTTP p99 xấu? Xem driver/client queue, GC, thread pool, serialization và network.

**Không bật mọi metric/tracing lúc cluster đã bão hòa** mà chưa đánh giá overhead: một số metrics trackers nằm trên hot path của Driver.

### 9.5. Request được thử nhiều coordinator

Một business request có thể phát sinh nhiều executions do retry/speculation. Vì vậy:

~~~text
HTTP requests/s  = 3.000
Driver CQL attempts/s = 4.800 (giả định)
Cassandra coordinator requests/s = tùy routing/metric
~~~

Chênh lệch có thể do retry/speculation hoặc một HTTP request gọi nhiều CQL; **không tự kết luận** chênh lệch chỉ do retries. Đo attempts per request và N+1 CQL calls trong trace ứng dụng.

Tránh thêm retry ở gateway, service, Spring Retry và Driver đồng thời khi điều tra overload. Mỗi lớp có thể nhân tổng attempts và làm tail latency xấu hơn.

### 9.6. Query trace có giá trị nhưng phải chọn đúng mẫu

Với `Statement.setTracing(true)`, Driver 4.x cung cấp tracing ID qua `ExecutionInfo.getTracingId()`; có thể lấy `getQueryTrace()` để thấy các events liên quan coordinator/replicas. Traces được ghi vào `system_traces` và có overhead/độ trễ khả dụng.

Không bật tracing 100% QPS hoặc log bind values/PII. Hãy:

1. Chọn **một fingerprint, một key mẫu được phép, một CL và một time window**.
2. Đo cùng query không tracing để có đối chứng.
3. Bật tracing cho **một tỷ lệ nhỏ** theo budget đã duyệt.
4. Liên kết trace ID vào incident ledger.
5. Dừng sampling sau khi thu đủ, không để cờ tracing bật lâu ngày.

Nếu query thất bại trước khi coordinator xử lý request, trace server-side có thể **không có**. Absence of trace **không** đủ chứng minh Cassandra khỏe hay lỗi ở client.

## 10. Bằng chứng CQL và data model: khoanh vùng query/partition

### 10.1. Không điều tra query thiếu key bằng cách quét cả table

Trên **cluster lab** hoặc môi trường được phép, có thể đọc metadata:

~~~sql
SELECT cluster_name, data_center, release_version
FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'triage_lab';
~~~

Thao tác này cho biết node trả response và replication metadata, **không tự chứng minh** mọi node cùng schema version hoặc toàn cluster healthy. Với bảng target:

~~~text
cqlsh: DESCRIBE KEYSPACE triage_lab;
cqlsh: DESCRIBE TABLE triage_lab.events_by_device_day;
~~~

Đây là cú pháp `cqlsh`, không phải statement CQL có thể gửi y hệt qua mọi Java API. Trước khi dùng các CQL read samples, kiểm tra PK và clustering để không vô tình tạo full scan/ALLOW FILTERING.

### 10.2. Cùng table nhưng query shapes khác nhau

Ví dụ schema **chỉ dành cho cluster lab riêng**. Nếu lab có ba nodes trong `dc1`, dùng RF3; với lab một node, phải dùng RF1/DC thực tế và không dùng nó để đánh giá fault tolerance:

~~~sql
CREATE KEYSPACE IF NOT EXISTS triage_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS triage_lab.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Tên DC `dc1` phải kiểm tra theo `nodetool status`/metadata thực, không mặc định Cassandra container luôn tên như vậy. `IF NOT EXISTS` không tự sửa schema cũ; kiểm tra `DESCRIBE TABLE` trước khi kết luận query và schema khớp.

Truy vấn phù hợp:

~~~sql
SELECT event_time, event_id, payload
FROM triage_lab.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

Nếu query v27 có `device_id + event_day` và v28 chỉ còn `device_id` hoặc thêm `ALLOW FILTERING`, nó thay đổi phạm vi/chi phí và đôi khi bị CQL từ chối. Một lỗi chỉ xuất hiện với các partition `event_day` rất cũ có thể đến từ TTL/tombstones hoặc compaction, không nhất thiết code deploy.

### 10.3. Kích cỡ partition và lịch sử TTL có thể biến một query thành ngoại lệ

Kiểm tra các dimensions:

~~~text
partition key / clustering range
rows/partition và bytes/partition (p50/p95/p99/max)
TTL và tuổi tombstones
SSTables per read
page size và số pages thực tiêu thụ
filtering/index/SAI có được dùng hay không
RF/CL, DC-local replicas
~~~

Một query latest-N với `LIMIT 20` vẫn có thể scan nhiều tombstones trước khi tìm đủ live rows. Một partition nóng do nhiều read requests có thể gây chậm dù row count nhỏ. **Phân biệt “big partition”, “hot partition”, “tombstone-heavy partition”** — cùng tên bảng nhưng cơ chế và bước xác minh khác nhau.

### 10.4. Khi write lỗi, đừng dùng SELECT để khẳng định rollback

Sau `WriteTimeoutException`, đọc lại một row có thể giúp reconciliation nhưng **không** tự chứng minh một operation chưa áp dụng, đặc biệt khi concurrent writers, TTL, CL thấp hoặc write timestamps cạnh tranh.

Quy trình nghiệp vụ cần:

- Operation ID hoặc idempotency key để nhận diện một mutation logic.
- Key/CL và phạm vi trả lời được phép kiểm tra.
- Trạng thái `SUCCESS / FAILED_VALIDATION / UNKNOWN_TIMEOUT` tách biệt.
- Kiểm tra lại theo consistency/serial semantics phù hợp nếu là LWT.
- Không phát lại list append, counter increment, hoặc TTL reset nếu chưa biết idempotency.

**Sự thật quan sát được**: “trong một SELECT ở CL X lúc T, cột có giá trị Y”. **Không** suy rộng thành “tất cả replicas đã hội tụ” nếu chưa có bằng chứng bổ sung.

## 11. Đọc metrics và logs sao cho không tự tạo sai lệch

### 11.1. Counter, gauge, histogram và timer khác nhau

| Loại | Ví dụ | Cách đọc đúng |
|---|---|---|
| Counter | ClientRequest.Read.Timeouts, bytes flushed | Tốc độ tăng trong window; tính reset sau restart |
| Gauge | PendingCompactions, pool.in-flight, disk free | Snapshot/series theo thời gian, không dùng derivative bừa |
| Histogram | SSTablesPerReadHistogram, partition-size histogram | Đuôi phân phối, cần hiểu bucket/unit và sample count |
| Timer/Latency | ReadLatency, CoordinatorReadLatency | p95/p99/rate theo thư viện/interval, không gộp sai |
| Event log | NodeDown, GC pause, deploy | Thời điểm đơn lẻ, có thể thiếu các sự kiện không được log |

Nếu một counter về 0 sau restart, **không** tính nó là “số lỗi âm”; dùng `rate/increase` có xử lý reset theo exporter và dữ liệu scrape. Nếu một metric không đổi, kiểm tra nó còn được collect và labels/targets còn đúng trước khi suy “hệ thống ổn”.

### 11.2. Không lấy trung bình của các percentile

~~~text
Node N1 p99 = 10ms, 10.000 requests
Node N2 p99 = 500ms, 100 requests

(10 + 500) / 2 = 255ms KHÔNG phải p99 của toàn cluster.
~~~

Percentile của hỗn hợp phải được ước lượng từ phân phối/histogram samples phù hợp (ví dụ merged buckets có định nghĩa chung), không lấy arithmetic mean của các p99 riêng lẻ. Thậm chí cộng p99 của driver + coordinator + network để ra end-to-end p99 cũng **không đúng toán học**.

### 11.3. Mẫu PromQL mang tính mô hình

Metrics names của exporter **khác nhau**; snippet này dùng tên **giả định** và không chạy nguyên văn trừ khi mapping thực sự có tên ấy:

~~~promql
# Counter HTTP errors mỗi giây theo deployment trong 5 phút.
sum by (deployment) (
  rate(http_requests_errors_total{service="events"}[5m])
)

# Tỷ lệ lỗi trên số request, khi có cùng nhãn và dữ liệu:
sum(rate(http_requests_errors_total{service="events"}[5m]))
/
sum(rate(http_requests_total{service="events"}[5m]))
~~~

**Không** dùng `rate(...[5m])` để tìm lỗi tồn tại đúng 5 giây mà không xem raw samples; smoothing có thể che onset. Với Cassandra JMX, metric exporter tùy nơi triển khai, phải đọc mapping thật; không sao chép tên PromQL tưởng tượng vào dashboard production.

### 11.4. Độ trễ giữa incident và metrics

Hệ thống giám sát có thể:

- Scrape mỗi 15–60 giây.
- Đẩy dữ liệu qua remote-write/aggregation vài chục giây.
- Drop samples khi node Down hoặc exporter quá tải.
- Tính alert trên moving windows và có pending period.
- Downsample dữ liệu lịch sử, làm mất spikes ngắn.

Ghi đồng thời **event timestamp** và **ingestion/capture timestamp**. Khi metric time series có gap, đó có thể là missing telemetry, **không** mặc nhiên là không có lỗi.

### 11.5. Lỗi do chính công cụ quan sát

Một dashboard thay label, một exporter đổi metric name, hoặc application mới tắt driver metrics có thể khiến series về zero. Đối chiếu user-facing SLO với **số mẫu và targets UP**. Nếu dashboard “p99 tăng 10 lần” mà latency thô trong app và logs vẫn bình thường, kiểm tra đơn vị giây/mili-giây/micro-giây và query expression.

Không để “monitor khỏe” thành lý do bỏ qua khi khách hàng báo lỗi có thể tái hiện.

## 12. Từ triệu chứng đến giả thuyết có thể bác bỏ

### 12.1. Cây quyết định ban đầu

~~~mermaid
flowchart TD
    A["HTTP latency/error tăng"] --> B{"Driver đã gửi CQL chưa?"}
    B -->|Chưa / không rõ| C["Gateway, queue, thread pool, auth,<br/>driver throttler/connectivity"]
    B -->|Rồi| D{"Cassandra trả response gì?"}
    D -->|Unavailable| E["RF/CL, gossip, replica liveness,<br/>DC/rack topology"]
    D -->|Read/WriteTimeout| F["Coordinator/replica latency,<br/>IO, GC, tombstones, network"]
    D -->|DriverTimeout| G["Driver pool/queue + network<br/>hoặc coordinator không phản hồi"]
    D -->|Validation/Auth| H["Query/schema/role/config diff"]
    D -->|Success nhưng HTTP chậm| I["Paging, mapping, serialization,<br/>post-processing, client network"]
    C --> J["Thu hẹp cohort và cửa sổ thời gian"]
    E --> J
    F --> J
    G --> J
    H --> J
    I --> J
    J --> K["Đối chiếu changes + evidence,<br/>test điều có thể bác bỏ"]
~~~

Đây là **hướng dẫn chọn phép kiểm tra**, không phải thuật toán xác định root cause chắc chắn. Một request có thể đồng thời gặp driver pool pressure và một replica chậm; các nhánh không loại trừ nhau.

### 12.2. Mẫu giả thuyết tốt

~~~text
ID: H-02
Claim: Tombstones trong partition của tenant A khiến latest-N read p99 cao.
Window: first-bad sau khi TTL cohort hết hạn, 09:40–09:45 UTC.
Scope: chỉ query latest-N của tenant A, không ảnh hưởng point read tenant B.
Predictions:
  - table TombstoneScannedHistogram tăng ở các nodes sở hữu token tương ứng
  - query trace mẫu phản ánh scan nhiều rows/tombstones
  - p99 cao khi query cùng partition, ít hơn với healthy partition
Falsifiers:
  - cùng sự cố với mọi partition và mọi table cùng node, không có scan skew
  - query không đọc partition/tombstone-heavy data
Evidence needed: EV-012 tablehistograms, EV-013 trace, EV-014 query fingerprint.
Risks of verification: tracing overhead, PII trong partition key.
Next action: đọc metrics/trace có kiểm soát; chưa chạy compact/repair.
~~~

Độ mạnh của giả thuyết tăng khi một test phân biệt được nó với giả thuyết cạnh tranh. “Có thể do Cassandra” **không phải** giả thuyết đủ sắc.

### 12.3. Hướng dẫn từ lỗi tới bằng chứng đầu tiên

| Tín hiệu chính | Thu thêm ngay | Không vội làm |
|---|---|---|
| Một app deployment lỗi | Version, config hash, query fingerprint, driver metrics | Restart toàn cụm |
| Một DC lỗi, DC khác khỏe | Driver local DC, CL, coordinator, nodetool status ở nhiều nodes | Hạ CL hoặc RF |
| Mọi query chậm, CPU/disk cao | GC, disk IO, queues, memtable/compaction, offered QPS | Tăng timeout vô hạn |
| Chỉ một table/range chậm | Partition histogram, tombstone metrics, paging, data age | Add ALLOW FILTERING |
| ReadTimeout tăng, Unavailable thấp | Replica response/GC/IO, request CL, coordinator | Kết luận đủ replica nên hệ thống khỏe |
| Unavailable tăng | RF/CL, node liveness, DC/rack, network | Blind retry qua mọi node |
| DriverTimeout tăng, server latencies thấp | Driver queue/connection pool/client GC/network | Chỉ tinh chỉnh compaction |
| TLS handshake fail từ một app version | Truststore/CA/SAN, certificate chain, DNS, cert timestamps | Tắt TLS/hostname verification |
| InvalidQuery/Unauthorized tăng sau deploy | CQL schema/role changes, prepared statement, grants | Retry đến khi hết lỗi |
| Write timeout nhưng dữ liệu tồn tại | Outcome ambiguity, write type, idempotency ledger | Ghi lại counter/list append tùy tiện |

**Thời điểm, phạm vi và thay đổi** quyết định bạn đi nhánh nào; exception class chỉ là một phần dữ liệu.

### 12.4. Đừng thay “chưa có bằng chứng” bằng “không có vấn đề”

~~~text
Không thấy GC log                != không có GC pause
Không thấy server ReadTimeout    != mọi read thành công
Một node status UN               != tất cả node cùng gossip view
Không có trace ID                != coordinator không xử lý request
No recent deploy                != không có thay đổi workload/TTL/network
Không có error sau rollback      != data integrity đã được xác minh
~~~

Hãy đánh dấu các nguồn là `NOT_COLLECTED`, `EMPTY_WITH_COVERAGE` hoặc `UNAVAILABLE`. Chỉ khi biết exporter/log hoạt động và bao phủ đúng window mới có thể dùng sự vắng mặt làm bằng chứng hỗ trợ.

## 13. Bốn tình huống điều tra đầu-cuối

### 13.1. Tình huống A — chỉ phiên bản ứng dụng mới bị timeout

**Giả định:**

~~~text
09:39 UTC: API events v28 rollout 20% trong dc1
09:42 UTC: first-bad: v28 read p99 từ 70 lên 270ms
09:43 UTC: DriverTimeoutException tăng ở v28
09:45 UTC: Cassandra nodes vẫn UN
09:47 UTC: deployment v27 trên cùng DC bình thường
~~~

**Khoanh vùng:**

1. So query fingerprint và bind pattern v27/v28, không log user values.
2. So `pageSize`, CL, request timeout, retry/speculation và connection pools.
3. Kiểm tra v28 có thêm CQL calls/request hoặc `Flux` bị subscribe hai lần không.
4. So Driver pool in-flight/pending và coordinator p99. Nếu server p99 không đổi nhưng client p99 tăng, nghi client queue/serialization.
5. Ghi deployment progress thực; canary/rollback chỉ khi có thẩm quyền.

**Giả thuyết cạnh tranh:**

| H | Dự đoán | Phép bác bỏ |
|---|---|---|
| H1: v28 tăng số pages | Rows/pages/request tăng chỉ v28 | Query và page consumption y hệt v27 |
| H2: driver pool v28 cấu hình nhỏ | Pool in-flight/available-streams xấu chỉ v28 | Pool metrics ổn, coordinator p99 tăng cùng lúc |
| H3: compaction N2 | Query các versions qua N2 cùng chậm | v27 trên cùng N2 vẫn bình thường và cùng payload |

**Kết luận đúng dạng:** “Các quan sát hiện tại ủng hộ H1 với confidence MEDIUM; cần A/B cùng query shape để tăng confidence”. Không viết “do Cassandra 100%” hay “do deploy 100%” trước khi có test đủ phân biệt.

### 13.2. Tình huống B — lỗi theo DC, status nhìn không nhất quán

**Giả định:**

~~~text
11:00 UTC: service dc1 có UnavailableException (LOCAL_QUORUM)
11:00 UTC: service dc2 vẫn đọc được keyspace theo CL được cấu hình riêng
11:02 UTC: nodetool status trên N1 thấy N2 UN
11:02 UTC: nodetool status trên N3 thấy N2 DN
11:04 UTC: network packet loss tăng trên một link giữa racks
~~~

**Khoanh vùng:**

1. Xác nhận client local DC/routing, replication trong keyspace và CL thực.
2. Thu `nodetool status/gossipinfo` từ nhiều nodes, ghi source/time.
3. Đối chiếu server `Unavailable` với driver `AllNodesFailed`, coordinator endpoints.
4. Thu network packet loss/latency, GC và host health cùng window.
5. Xem network policy/host maintenance events — không kết luận từ một view `UN`.

**Rủi ro hành động sai:** giảm `LOCAL_QUORUM` xuống `LOCAL_ONE` có thể khiến reads thấy dữ liệu cũ; thay đổi RF trong lúc mạng lỗi càng rủi ro hơn. Việc cân bằng availability/consistency phải thuộc runbook và business invariant.

**Bằng chứng kết thúc cần có:** node views hội tụ, network ổn định, request success theo CL mục tiêu và integrity/repair state được kiểm tra, không chỉ mọi node “xanh”.

### 13.3. Tình huống C — chỉ dữ liệu cũ bị chậm sau đợt TTL

**Giả định:**

~~~text
02:00 UTC: TTL cohort 7 ngày của một batch events hết hạn
02:04 UTC: latest-N queries trên partitions cũ có p99 tăng
02:06 UTC: TombstoneScannedHistogram tăng trên table liên quan
02:07 UTC: compaction backlog tăng; point reads partition mới bình thường
~~~

**Khoanh vùng:**

- Kiểm tra TTL policy/tuổi dữ liệu, không coi `event_time` cũ là TTL đã hết.
- So partitions mới/cũ với cùng query/CL và số live rows tương đương.
- Ghi SSTables/read, tombstone histograms và disk/IO; tránh kết luận từ compaction backlog đơn lẻ.
- Xem có UPDATE lại cells đã có TTL, làm mixed expiration hay không.
- Nếu dùng TWCS/UCS, đối chiếu strategy/maintenance window, repair history.

**Không tự chạy** major compaction/giảm gc_grace để “dọn hết tombstones” trong production. Đây có thể là bước can thiệp nguy hiểm và làm thay đổi bằng chứng; cần strategy review, safety check và test riêng.

### 13.4. Tình huống D — SSL failures sau thay chứng chỉ

**Giả định:**

~~~text
13:10 UTC: truststore của service mới được rollout một phần
13:12 UTC: chỉ pods mới có TLS handshake errors
13:13 UTC: Cassandra cqlsh từ host nội bộ vẫn kết nối bình thường
13:14 UTC: service cũ vẫn query được cùng DC
~~~

**Khoanh vùng:**

1. Phân biệt `SSLHandshakeException`/trust chain errors với `UnauthorizedException` CQL.
2. So fingerprint/expiry/SAN của server certificates, CA chain và truststore versions theo policy (không xuất private keys).
3. Kiểm tra client TLS endpoint verification, hostname vs IP, DNS/SNI và thời gian hệ thống.
4. So source AZ/DC, port 9042, firewall hoặc LB; không dùng cqlsh thành công từ **một host khác** để kết luận mọi app pod có đường mạng/tin cậy giống nhau.
5. Thu thời điểm rollout cert/truststore và first handshake failure, xét cả clock skew.

**Không dùng** “tắt SSL verification tạm” như mitigation mặc định; cần rollback đúng truststore/certificate hoặc sửa cấu hình an toàn theo runbook.

### 13.5. Điều bốn ví dụ cùng dạy

Một dấu hiệu riêng **không đủ**. `UN` không loại bỏ tombstones/GC/network. Một deploy gần thời điểm lỗi không chứng minh deploy gây lỗi. Một timeout không chứng minh write chưa áp dụng. **Thời điểm + phạm vi + thay đổi + bằng chứng từ nhiều tầng** tạo thành một chuỗi nhân quả có thể kiểm thử.

## 14. Lab điều tra: khoanh vùng trước khi đưa ra hành động

### 14.1. Mục tiêu và điều kiện

Lab gồm **phần tabletop không cần cluster** và một phần **Cassandra lab tự chọn** để tập thu những bằng chứng an toàn. **Không thực hiện fault injection trên production**. Nếu không có Cassandra lab, người học vẫn hoàn thành đầy đủ phần phân tích timeline/ma trận và evidence ledger.

Kịch bản:

~~~text
Keyspace: triage_lab
Table: events_by_device_day
3 nodes trong dc1, RF=3, read CL=LOCAL_QUORUM
Service: events-api v27 và v28, Java Driver 4.x
Symptom: GET latest events p99 tăng và timeout ở v28
SLO: p99 <= 200ms; success >= 99.9% (chỉ số giả định cho lab)
~~~

**Nhắc lại:** câu chữ, mốc thời gian và metrics trong lab là **đầu vào giả lập**, không phải quan sát có thật. Không công bố như kết quả benchmark Cassandra.

### 14.2. Bộ dữ kiện tabletop

| UTC window | Cohort | Requests | p99 successful latency | Error % | Bằng chứng |
|---|---|---:|---:|---:|---|
| 09:35–09:40 | v27/dc1 | 15.000 | 78 ms | 0.02% | A1 app metrics |
| 09:40–09:42 | v27/dc1 | 6.000 | 81 ms | 0.02% | A2 app metrics |
| 09:40–09:42 | v28/dc1 | 1.200 | 86 ms | 0.08% | A3 canary metrics |
| 09:42–09:45 | v27/dc1 | 9.000 | 83 ms | 0.03% | A4 app metrics |
| 09:42–09:45 | v28/dc1 | 4.000 | 312 ms | 3.6% | A5 app metrics |
| 09:42–09:45 | v27/dc2 | 5.000 | 90 ms | 0.04% | A6 app metrics |
| 09:42–09:45 | v28/dc2 | 0 | N/A | N/A | Không rollout dc2 |

Change events:

~~~text
09:39:20Z  v28 rollout 0 -> 20% tại dc1
09:41:15Z  N2 compaction pending tasks tăng từ 3 lên 12
09:42:00Z  Bắt đầu bucket first-bad của v28
09:43:10Z  v28 driver throttler queue dài hơn; v27 bình thường
09:45:00Z  Alert fires; pending period 2 phút
09:46:30Z  Scribe bắt đầu thu evidence
~~~

Driver CQL observations:

~~~text
v27: /events -> 1 prepared SELECT with LIMIT 100, pageSize=100
v28: /events -> 1 prepared SELECT with LIMIT 1000, pageSize=100
v27: mean returned rows/request 83
v28: mean returned rows/request 580
v28: requests consume several pages; retry/attempt count tăng
Coordinator proxy read p99: chỉ tăng nhẹ so với before
N2: có compaction backlog cao hơn baseline
~~~

### 14.3. Bài tập A — xác định onset mà không bịa độ chính xác

Yêu cầu:

1. Ghi `last-known-good` và `first-known-bad` theo bucket thực.
2. Ghi `T_alert` và giải thích vì sao nó không bằng `T_first_bad`.
3. Ghi khoảng thời gian chưa xác định chính xác trong transition.
4. Chọn cửa sổ thu log từ trước 09:39 và sau 09:46, giải thích vì sao.
5. Ghi “đây là dữ kiện giả lập” khi nộp báo cáo.

**Gợi ý đáp án:** last normal gồm v28 bucket 09:40–09:42 (theo ngưỡng giả định); first bad 09:42–09:45; alert 09:45 do pending/evaluation. Không thể khẳng định chính xác một giây xảy ra regression từ dữ liệu bucket nhiều phút.

### 14.4. Bài tập B — ma trận ảnh hưởng

Điền:

| Dimension | Affected | Healthy/control | Chưa biết |
|---|---|---|---|
| App version | v28/dc1 | v27/dc1 | phiên bản khác |
| Region/DC | dc1 có v28 | v27/dc2 | v28/dc2 chưa rollout |
| Query shape | LIMIT 1000 và nhiều pages | LIMIT 100 | query khác |
| Table | events_by_device_day | chưa có bảng đối chứng | bảng khác |
| Node | chưa kết luận node gây lỗi | chưa xác định | replica/coordinator mapping |
| Maintenance | N2 compaction backlog tăng | N1/N3 chưa có metrics | causal role |

**Gợi ý:** cơ chế “query trả nhiều rows/pages” khớp cả version/scope/time, nên ưu tiên H1. Compaction backlog N2 trùng thời gian nhưng có thể chỉ là tác nhân phụ hoặc diễn ra độc lập; chưa đủ bằng chứng để chọn “N2 là root cause”.

### 14.5. Bài tập C — xếp hạng giả thuyết

Chấm H1 (query regression), H2 (N2 compaction), H3 (network) theo bảng:

| Giả thuyết | Temporal fit | Scope fit | Mechanism fit | Evidence thiếu |
|---|---|---|---|---|
| H1: query LIMIT/page behavior | Có | Cao | Cao | Per-request pages & bytes, rollback/canary |
| H2: compaction N2 | Có | Chưa rõ | Có thể | Per-node IO/GC, query routing overlap |
| H3: packet loss toàn dc1 | Chưa có | Thấp vì v27 khỏe | Có thể | Network telemetry, driver errors theo node |

Hãy viết **một phép bác bỏ** cho từng H và mức rủi ro của phép kiểm tra. Không cần đưa ra “root cause” khi chứng cứ còn thiếu.

### 14.6. Bài tập D — snapshot Cassandra an toàn trên lab

Nếu có lab Cassandra đã tạo schema của mục 10, chạy lệnh quan sát **trên node test**:

~~~bash
nodetool status
nodetool proxyhistograms
nodetool tpstats
nodetool compactionstats
nodetool tablehistograms triage_lab events_by_device_day
nodetool tablestats triage_lab.events_by_device_day
~~~

Với một lab chỉ một node, các lệnh vẫn giúp học cú pháp/metrics; **không so kết quả như chứng minh outage RF3**. Trước khi chạy, kiểm tra `nodetool help <command>` theo version; một số build/roles có thể chặn remote JMX hoặc chưa có metrics. Không dùng admin credentials trong shell history.

Trong `cqlsh` với quyền chỉ đọc:

~~~sql
SELECT cluster_name, data_center, release_version FROM system.local;
SELECT keyspace_name, replication
FROM system_schema.keyspaces WHERE keyspace_name = 'triage_lab';
~~~

Nếu table chưa có, tạo schema **chỉ trên lab** và seed vài events với partition key mẫu, sau đó chạy SELECT có đầy đủ `device_id, event_day`. Không sinh hàng triệu rows hoặc quét toàn keyspace chỉ để luyện bước triage.

### 14.7. Bài tập E — thu thập và redaction evidence

Tạo bảng:

| ID | Nguồn | Time UTC | Query/filter/command | Scope | Kết luận hỗ trợ | Hạn chế |
|---|---|---|---|---|---|---|
| EV-01 | App metrics | _điền_ | deployment=v28 | dc1 | v28 p99 tăng | Aggregated 3m |
| EV-02 | Driver logs | _điền_ | error_class | v28 | _điền_ | Sampling |
| EV-03 | Node metrics | _điền_ | compaction pending | N2 | _điền_ | Correlation only |
| EV-04 | Deploy audit | _điền_ | image digest | v28 | _điền_ | Không chứng minh cause |

**Không ghi** full bind parameters, raw tenant IDs, access tokens hoặc packet payload không được phép. Với hot partition keys, có thể thay bằng keyed hash (HMAC) với secret key được quản lý đúng policy; hash thuần của một ID dễ đoán **không đủ** để bảo vệ riêng tư.

### 14.8. Bài tập F — mitigation và xác minh

Giả sử được phép giảm traffic v28/canary rollback trong môi trường thử:

1. Lưu before snapshots và rate of v28 requests.
2. Đổi **một biến**: giảm 20% → 0% traffic v28 theo runbook.
3. So p99/error từng cohort, traffic tổng và per-node metrics sau rollback.
4. Chỉ khi metrics thực khớp prediction, nâng confidence về contribution của v28.
5. Vẫn theo dõi TTL/compaction/N2: rollback có thể giảm symptom nhưng một nguy cơ khác tồn tại.
6. Ghi state dữ liệu, in-flight/unknown writes nếu có lỗi ghi — rollback app không tự sửa dữ liệu.

Nếu không thể rollback hoặc chưa có thẩm quyền, chỉ viết **plan + expected observation**, không tuyên bố đã thực hiện.

## 15. Báo cáo incident, bàn giao ca và xác nhận phục hồi

### 15.1. Mẫu báo cáo đủ ngắn để dùng lúc trực ca

~~~markdown
# Incident INC-... — Cassandra read latency trong service ...

## Trạng thái
- Status: INVESTIGATING / MITIGATED / MONITORING / RESOLVED
- Started window (UTC): [last-known-good, first-known-bad]
- Detected / alert time (UTC): ...
- Severity / impact: users, error %, p99, affected operations
- Owner / next update UTC: ...

## Phạm vi đã chứng minh
- Affected: app versions, DCs, keyspaces, tables, CQL fingerprint
- Healthy controls: ...
- Unknown/not yet verified: ...

## Thay đổi gần nhất
- Change ID, effective time, rollout %, app/config/CQL/network/maintenance
- Temporal fit / scope fit / mechanism fit: ...
- Concurrent unrelated changes: ...

## Bằng chứng
- EV-001 ... source, timestamp, query/command, unit, scope, link
- EV-002 ...
- Clock skew/data gaps/sampling: ...

## Giả thuyết
- H1, prediction, falsifier, evidence for/against, confidence
- H2, prediction, falsifier, evidence for/against, confidence

## Hành động và kết quả
- At UTC ... actor ... did ... with approval ...
- Expected ... / observed ... / rollback state ...

## Xác minh phục hồi
- User SLO + error rates back in range for agreed window?
- Same CL / semantics / query results preserved?
- Cluster node/DC + repair/integrity conditions verified?
- Known unknowns and follow-up owners ...
~~~

**Không ghi root cause “CONFIRMED” chỉ vì p99 đã giảm.** Giảm triệu chứng sau rollback có thể là mitigation tạm thời; root cause cần chuỗi chứng cứ và cơ chế được kiểm chứng, đặc biệt khi có nhiều changes trùng thời gian.

### 15.2. Viết incident statement có thể phản bác

So sánh:

> *Yếu:* “Cassandra bị lỗi do deploy và giờ đã ổn.”

> *Tốt hơn:* “Trong dc1, 3.6% requests từ service-events v28 ở 09:42–09:45Z timeout; v27 cùng DC có 0.03%; v28 tăng LIMIT từ 100 lên 1.000 và mean rows/request từ 83 lên 580. Rollback v28 đang được đánh giá. Chưa có bằng chứng node N2 compaction là nguyên nhân trực tiếp.”

Ở bản tốt, từng mệnh đề có **nguồn/UTC/scope**, có thể kiểm tra hoặc bác bỏ. Nếu dữ liệu lấy từ lab giả định, phải ghi **SIMULATED**.

### 15.3. Exit criteria không chỉ là tất cả node UN

Một incident có thể chuyển từ **MITIGATED** sang **RESOLVED** sau khi đáp ứng điều kiện được định nghĩa từ đầu:

| Nhóm | Điều kiện tham khảo | Vì sao |
|---|---|---|
| User impact | Error rate/latency phục hồi trong cửa sổ đủ dài | Đảm bảo symptom thật đã hết |
| Offered traffic | Traffic đã trở về mức đại diện, không chỉ giảm còn 10% | Tránh “khỏe” vì không còn load |
| Driver | Retry/throttling/pool errors đã bình thường | Tránh sự cố ẩn sau queue |
| Cassandra | Node/DC health, latency, disk/GC/compaction xu hướng ổn | Không bỏ qua các nhân tố nền |
| Data integrity | Unknown writes/LWT/TTL và repair/reconciliation được xử lý | Success của API không chứng minh dữ liệu đúng |
| Operational | Mitigation config có owner/expiry, follow-up rõ | Tránh workaround tồn tại vĩnh viễn |

Cửa sổ đo phải dài hơn chu kỳ cảnh báo/scrape, và nếu sự cố liên quan TTL/compaction/repair thì có thể cần theo dõi dài hơn một vài phút. **Không định nghĩa một con số chung cho mọi cluster**; theo SLO, workload và runbook cụ thể.

### 15.4. Bàn giao ca mà không làm người sau điều tra lại từ đầu

~~~text
CURRENT STATE:
  Severity: SEV-... / owner ...
  Scope: v28/dc1 GET latest-N; other cohorts ...
  Last good & first bad: ... UTC, source ...
  Best hypotheses: H1 ..., H2 ..., confidence ...
  Collected evidence: EV-001..EV-012 (links)
  Actions already taken: command/change ID/UTC/outcome
  Explicitly NOT done: repair, major compaction, CL downgrade
  Risks: disk headroom, unknown writes, data integrity ...
  Next safe check: ...; expected result if H1 vs H2
  Rollback/stop condition: ...
  Next status update: ... UTC
~~~

Ghi cả **việc chưa làm** để người nhận không hiểu nhầm rằng đã loại trừ một nhánh. Nếu có nhánh mất quyền truy cập hoặc thiếu telemetry, ghi rõ blocker và người sở hữu quyền đó.

### 15.5. Sau incident: phân tích nguyên nhân và cải thiện khả năng quan sát

Post-incident review không chỉ liệt kê “cần thêm alert”. Nên trả lời:

1. Tại sao thời gian phát hiện lâu hơn first-bad?
2. Vì sao phạm vi khó khoanh vùng — thiếu label query fingerprint, deployment, DC hay coordinator?
3. Change diff có được theo dõi và gắn timestamp hiệu lực không?
4. Evidence nào mất do restart/rotation/retention?
5. Chúng ta có nhầm p99 HTTP với coordinator p99, hoặc đo sai đơn vị?
6. Mitigation có tạo unknown writes/consistency downgrade không?
7. Những test nào tái tạo được cơ chế trong lab, không đòi mang dữ liệu thật?
8. Runbook cần bổ sung câu hỏi/guardrail nào để lần sau nhanh hơn?

Với kết quả không xác định nguyên nhân, ghi **root cause = unresolved với các giả thuyết còn lại** thay vì dựng câu chuyện quá tự tin. Mục tiêu của postmortem là giảm thời gian phát hiện và tác động, không phải truy trách nhiệm cá nhân.

## 16. Câu hỏi tự đánh giá và checklist trực ca

### Bài 1 — Alert đến muộn

Dashboard p99 vượt ngưỡng từ bucket 10:00–10:01Z nhưng pager chỉ phát lúc 10:06Z. Có được ghi “incident bắt đầu 10:06Z” không?

**Đáp án:** không. Phân biệt thời điểm **first-known-bad** và **alert fired**. Alert có evaluation/pending interval, scrape và ingestion lag; onset chính xác còn phụ thuộc độ phân giải nguồn.

### Bài 2 — Hai node thấy hai trạng thái khác nhau

N1 báo N2 `UN`, N3 báo N2 `DN`. Có thể khẳng định toàn cluster đã nhất quán và N2 khỏe không?

**Đáp án:** không. `nodetool status` là góc nhìn gossip của node được hỏi. Thu đa nguồn cùng UTC, kiểm tra mạng, driver topology, host/process và thời gian membership.

### Bài 3 — AllNodesFailed có phải toàn cluster Down?

Một ứng dụng thấy `AllNodesFailedException`. Kết luận cả cluster Cassandra Down là hợp lệ?

**Đáp án:** chưa. Driver có thể không dùng được các coordinators trong query plan do pool, TLS, địa chỉ mạng, throttling/stream exhaustion hoặc server errors. Đọc nguyên nhân trên từng node, so ứng dụng khác, local DC và node health.

### Bài 4 — Coordinator khỏe nhưng HTTP chậm

HTTP p99 800ms; `nodetool proxyhistograms` cho coordinator reads p99 chỉ vài ms. Khẳng định application code kém?

**Đáp án:** chưa. Cần so cùng thời gian/query cohort/percentiles và kiểm tra driver queue, connection pools, network, paging, serialization, callback threads và HTTP gateway. Hai p99 từ hai phân phối không so trực tiếp khi không khớp.

### Bài 5 — Deploy sau khi lỗi bắt đầu

First-bad đáng tin là 09:42Z, một deploy bắt đầu 09:48Z. Có nên gọi deploy là nguyên nhân khởi phát?

**Đáp án:** không, trừ khi timestamp/telemetry sai hoặc deploy có bước trước đó chưa được ghi nhận. Thay đổi xảy ra **sau** onset không thể là nguyên nhân khởi phát theo timeline hiện có; nó có thể làm nặng hoặc giảm lỗi.

### Bài 6 — Cùng một query, chỉ một partition chậm

Cả node status đều `UN`, nhưng partition của tenant A có SELECT p99 2 giây, tenant B cùng bảng 30ms. Hướng kiểm tra?

**Đáp án:** so rows/bytes/tombstones của partition, hot-key request share, token/replica set, clustering range, paging và query trace mẫu. Không restart tất cả node chỉ vì một key chậm.

### Bài 7 — Compaction backlog trùng thời điểm

Compaction pending N2 tăng cùng lúc API lỗi. Đây có phải root cause chắc chắn?

**Đáp án:** không. Cần temporal order, IO/GC correlation, request routing qua N2 và healthy controls; compaction có thể là hệ quả của write burst hoặc một nhân tố phụ.

### Bài 8 — Báo cáo percentile

Một người lấy trung bình p99 của N1 và N2 để báo cluster p99. Vấn đề?

**Đáp án:** percentile không cộng/trung bình được như tổng số requests. Dùng histogram buckets/sample distributions có cùng semantics và thời gian, hoặc báo per-node p99 kèm traffic share.

### Bài 9 — WriteTimeout coi như rollback

App gặp `WriteTimeoutException` rồi tự retry `counter + 1` ba lần. Vì sao nguy hiểm?

**Đáp án:** write outcome có thể đã commit nhưng ACK mất; counter increments không idempotent và có thể bị nhân. Ghi UNKNOWN outcome, dùng operation ID/reconciliation và policy retry được thiết kế.

### Bài 10 — Tracing toàn bộ traffic

Nhóm bật `setTracing(true)` cho 100% CQL requests để “có nhiều bằng chứng hơn”. Có nên làm không?

**Đáp án:** không. Tracing có overhead và ghi thêm vào `system_traces`, có thể làm cluster đang yếu tệ hơn. Lấy mẫu nhỏ được phép, cho fingerprint/CL cụ thể, rồi tắt.

### Bài 11 — Giảm lỗi sau khi giảm tải

Sau khi giảm offered requests/s từ 5.000 xuống 500, p99 hồi phục và không còn timeout. Có nghĩa cluster đã được sửa?

**Đáp án:** chưa. Có thể workload chỉ giảm dưới ngưỡng quá tải. Điều kiện RESOLVED phải xét user SLO **ở mức traffic đại diện**, cùng dữ liệu/integrity/repair state và follow-up root cause.

### Bài 12 — Telemetry không có dữ liệu

Grafana cho thấy số DriverTimeoutException bằng 0 từ khi deploy. Nhưng trong application logs vẫn có exceptions. Hướng điều tra?

**Đáp án:** xem metric có được bật, exporter/label mapping, scrape gaps, process restart và unit/type. “Không có series” hoặc series 0 không chứng minh không có lỗi.

### Checklist 0–5 phút

- [ ] Ghi UTC hiện tại, owner, severity và mức ảnh hưởng tới user.
- [ ] Xác định first known bad/last known good **có khoảng chưa biết**.
- [ ] Không đồng nhất alert time với onset time.
- [ ] Nêu rõ query/service/DC chưa biết, không tự giả định tất cả bị lỗi.
- [ ] Kiểm tra khả năng mất dữ liệu, disk đầy, unavailable hàng loạt và ưu tiên giảm thiểu theo runbook.
- [ ] Thu snapshots tối thiểu **trước** thao tác can thiệp khi an toàn.

### Checklist 5–15 phút

- [ ] So healthy và affected cohorts theo version, DC, API, query, key.
- [ ] Phân loại exception: driver/server/gateway/validation/throttling.
- [ ] So nút coordinator với replica set, không nhầm hai vai trò.
- [ ] Thu status từ nhiều nodes nếu nghi gossip/network partition.
- [ ] Xem logs/metrics cùng cửa sổ và thống nhất timezone, unit.
- [ ] Thu change inventory (deploy, schema, CL, TLS, repair, compaction, network, workload).
- [ ] Lưu evidence IDs/links, source clock/offset, sampling và khoảng thiếu dữ liệu.

### Checklist 15–30 phút và bàn giao

- [ ] Viết tối đa vài giả thuyết với prediction/falsifier/risk.
- [ ] Đánh giá temporal fit, scope fit, mechanism fit.
- [ ] Phân biệt facts với inferences và confidence.
- [ ] Chỉ thử thao tác ít tác động trước, không chạy repair/major compaction/truncate vô cớ.
- [ ] Nếu mitigation, có approval, rollback plan, before/after cùng metric/filters.
- [ ] Đếm error/timeout **song song** với p95/p99; không che lỗi trong latency.
- [ ] Đảm bảo ngữ nghĩa CL/TTL/LWT và unknown writes không bị vi phạm.
- [ ] Báo cáo kết quả đã quan sát, điều chưa biết, người phụ trách bước tiếp.
- [ ] Định nghĩa exit criteria: SLO + traffic đại diện + health + integrity, không chỉ `UN`.

## 17. Tài liệu tham khảo

1. Apache Cassandra — [Troubleshooting](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/): phương pháp khoanh vùng máy/nút, logs và công cụ.
2. Apache Cassandra — [Use Nodetool](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html): `status` theo từng góc nhìn node, `proxyhistograms`, `tablehistograms`, `tpstats`, `compactionstats`.
3. Apache Cassandra — [Reading Cassandra Logs](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/reading_logs.html): `system.log`, `debug.log`, `gc.log`, logback và cách đọc log theo sự kiện.
4. Apache Cassandra — [Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): Table/ClientRequest/DroppedMessage/Compaction/CommitLog/JMX metrics và units.
5. Apache Cassandra — [nodetool Overview](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): tra cứu cú pháp lệnh đúng version và phân biệt thao tác đọc/ghi.
6. Apache Cassandra — [tablehistograms](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablehistograms.html) và [tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html): partition size, SSTables/read, latency và data statistics.
7. Apache Cassandra Java Driver 4.19 — [Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): READ_TIMEOUT, WRITE_TIMEOUT, UNAVAILABLE, error-response classes và retry semantics.
8. Apache Cassandra Java Driver 4.19 — [Metrics](https://apache.github.io/cassandra-java-driver/4.19.0/core/metrics/): cấu hình driver session/node metrics, pooling và đo attempts.
9. Apache Cassandra Java Driver 4.19 — [Tracing](https://apache.github.io/cassandra-java-driver/4.19.0/core/tracing/): per-statement query trace, `ExecutionInfo.getTracingId()` và giới hạn sampling.
10. Apache Cassandra Java Driver 4.19 — [Performance](https://apache.github.io/cassandra-java-driver/4.19.0/core/performance/): Netty hot path, driver tracking, metrics overhead, throttling.
11. Apache Cassandra Java Driver 4.19 — [Throttling](https://apache.github.io/cassandra-java-driver/4.19.0/core/throttling/) và [Speculative Execution](https://apache.github.io/cassandra-java-driver/4.19.0/core/speculative_execution/): driver queue/timeouts và additional executions.
12. Apache Cassandra Java Driver 4.19 — [Statement Attributes](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): immutable statements, CL, tracing, timeout, page size, routing và profile.
13. Apache Cassandra — [Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): partition key, clustering, query-first model và các dấu hiệu partition sai.
14. Apache Cassandra — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) và [Compaction](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html): TTL, deletion markers, repair/grace và read amplification.
