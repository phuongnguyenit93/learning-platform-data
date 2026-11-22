# Kiểm tra sức khỏe trước/sau bảo trì bằng trạng thái và truy vấn trong Apache Cassandra

## 1. Mục tiêu và nguyên tắc vận hành

Trong Apache Cassandra, bảo trì có thể gồm rolling restart, nâng cấp phiên bản, thay đổi cấu hình JVM/TLS, thay node, mở rộng topology, repair, thay disk, cập nhật Java Driver hoặc điều chỉnh schema. Một thao tác bảo trì có thể **thành công ở cấp máy chủ** nhưng vẫn làm giảm khả năng trả lời CQL; ngược lại, một câu `SELECT` thành công có thể che giấu replica đang lỗi, compaction backlog hoặc mất khả năng chịu thêm một node down.

Bài này thuộc chương **Tự động hóa vận hành** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Mục tiêu không chỉ là đọc dòng `UN` trong `nodetool status`, mà là xây dựng **health gate có bằng chứng**:

- Kiểm tra cluster ở trạng thái phù hợp **trước** bảo trì.
- Thiết lập baseline về topology, replication/consistency, query success, latency và tài nguyên.
- Quan sát rủi ro trong lúc bảo trì và **dừng** nếu không đáp ứng điều kiện tiếp tục.
- Kiểm tra **sau** bảo trì bằng trạng thái node, schema, native CQL và truy vấn read/write an toàn.
- Xác nhận hồi phục thực tế: queue, hints, streaming, repair/compaction, disk, CPU/GC và p95/p99.
- Trả kết quả có thể tự động hóa: **PASS**, **FAIL** hoặc **UNKNOWN** với giải thích và bằng chứng.
- Có kế hoạch rollback/recovery; không lấy retry hoặc hạ consistency level để che sự cố.

Bài tập trung vào Cassandra phân tán, mô hình wide-column theo partition key, mức nhất quán theo DC và cách tạo probe từ ứng dụng Java Driver 4.x. Mọi giá trị ngưỡng trong ví dụ chỉ để giải thích phương pháp, **không phải ngưỡng mặc định Cassandra**.

> **Quy tắc an toàn:** Không thực thi lệnh bảo trì, ghi production data, `repair`, `cleanup`, `decommission`, thay schema hay restart node chỉ vì một đoạn ví dụ. Các phép thử write phải dùng keyspace/table dành riêng, role tối thiểu và cửa sổ được phê duyệt. Trong bước viết nội dung này không chạy bất kỳ lệnh nào.

## 2. Health check là kiểm tra điều kiện, không phải một lệnh

### 2.1. Phân tầng bằng chứng

~~~mermaid
flowchart TD
    A["Maintenance controller"] --> B["Preflight"]
    B --> C["Topology & node state"]
    B --> D["Cassandra service & CQL"]
    B --> E["Replica availability + RF/CL"]
    B --> F["Resource/latency baseline"]
    C --> G{"Có đủ điều kiện bảo trì?"}
    D --> G
    E --> G
    F --> G
    G -->|No / Unknown| H["STOP + human review"]
    G -->|Yes| I["Execute approved maintenance"]
    I --> J["Postflight: compare state + query + metrics"]
    J --> K{"Các acceptance gates đạt?"}
    K -->|Yes| L["PASS + release traffic/change"]
    K -->|No / Unknown| M["Hold / rollback / recovery runbook"]
~~~

**Liveness** chỉ nói một service/process còn sống hoặc node được thấy Up. **Readiness** nói node/ứng dụng có thể xử lý workload dự kiến. **Correctness** nói dữ liệu nhận/ghi đúng theo primary key và consistency policy. **Performance** nói tải, tail latency và tài nguyên nằm trong giới hạn.

Bốn chiều này phải được kiểm độc lập. Không quy tất cả thành một flag Boolean `healthy=true` vì thiếu bằng chứng có thể bị nhầm thành PASS.

### 2.2. Bảng scope và nguồn sự thật

| Phạm vi | Ví dụ câu hỏi | Nguồn quan sát |
|---|---|---|
| Node/process | Cassandra process/native listener còn phục vụ? | Service logs, `nodetool info`, native connection |
| Gossip/ring | Node được nhìn nhận như `UN`/`DN`? | `nodetool status` từ nhiều điểm |
| Topology | DC/rack, node count, token distribution đúng? | Status/ring, inventory, cluster metadata |
| Schema | Schema agreement và bảng/column đúng? | `nodetool describecluster`, schema metadata theo release |
| Replication | RF và CL có đủ replica thực tế? | Keyspace replication, node states, request errors |
| Client→node | Java session mở và query được? | CqlSession, driver errors, SSL/auth |
| Read correctness | Query theo partition key trả expected row? | Prepared SELECT canary |
| Write correctness | Mutation được ack và đọc lại? | Prepared INSERT/SELECT trong table probe |
| Performance | p95/p99, retries, throughput, timeouts có hồi phục? | Client & Cassandra metrics |
| Background work | Streaming, hints, compaction, repair có ổn định? | `netstats`, `compactionstats`, metrics/logs |
| OS/JVM | CPU/GC/RAM/disk/headroom an toàn? | JMX, cgroup, device metrics |

**`nodetool` thường đi qua JMX**, không phải native CQL. Vì vậy kết nối JMX được không chứng minh Java Driver có đủ TLS/auth/permissions hoặc contact points đang hoạt động.

## 3. Xác định “trước”, “trong”, “sau” bảo trì

### 3.1. Preflight: không khởi động bảo trì nếu baseline không tin cậy

Trước cửa sổ bảo trì, cần xác định:

1. **Change ID và phạm vi:** một node, rack, DC, tất cả clients, thay topology hay thay certificate?
2. **Expected target:** bao nhiêu nodes/DC, rack, token ownership và software versions sau thay đổi?
3. **RF/CL nghiệp vụ:** ví dụ `NetworkTopologyStrategy`, `LOCAL_QUORUM` hay các CL được phép theo app.
4. **Dependencies:** repair/backup/streaming, batch jobs, schema migrations, Java rollout đang chạy?
5. **Traffic policy:** cách giảm tải, canary, đóng cửa sổ migration, người giữ quyền stop.
6. **Rollback path:** nếu schema/data-format/upgrade không backward-compatible, rollback **có thể không khả thi**; phải xác định trước.
7. **Dữ liệu kỳ vọng:** row canary, keyspace test, role test, query templates representative.
8. **Resources:** disk headroom, CPU/GC, heap/off-heap, compaction, hints, pending queues, network.
9. **Baseline window:** thời gian quan sát đủ đại diện, tránh so giờ cao điểm với giờ thấp điểm.
10. **Exit gates:** trạng thái PASS/FAIL/UNKNOWN và hành động đối với từng trạng thái.

Không nên chọn baseline một phút ngay sau restart hoặc trong lúc bootstrap/repair nếu điều đó không phản ánh trạng thái thông thường.

### 3.2. Trong bảo trì: gate sau từng node/bước

Với rolling maintenance, thứ tự phải tuân topology/DC/rack/RF/CL. Sau mỗi node:

- Xác minh node đã quay lại trạng thái dự kiến.
- Xác minh CQL canary **từ mạng ứng dụng** tới local DC.
- Quan sát p99/error, retries, replica availability.
- Kiểm tra hints/streaming/compaction/GC/disk đang trở lại mức cho phép.
- Đảm bảo không có node khác bất ngờ DOWN.
- Chỉ tiếp tục node kế tiếp sau khi gate đạt; không “điền PASS thủ công” khi dữ liệu đo bị mất.

**Trường hợp bảo trì chính là thay đổi topology**, không đòi số node/token/ownership sau giống hệt trước; phải so với **expected change manifest**.

### 3.3. Postflight: kiểm tra một lần chưa đủ

Sau khi node `UN` và probe `SELECT` thành công, vẫn cần:

- **New native connections** (đặc biệt khi thay TLS, auth, Java driver, port).
- Read/write path đúng theo **CL production** trong từng DC liên quan.
- Không tăng timeout, unavailable, request failure hoặc retry storm.
- Pending queues không tích lũy dài hạn.
- Hints/streaming/compaction/repair phục hồi theo kế hoạch.
- Schema agreement, prepared statement metadata và app compatibility.
- API end-to-end p95/p99 và data correctness.
- Một **observation window** đủ dài để phát hiện lỗi sau reconnect/cache warm-up.

## 4. Kiểm tra trạng thái cluster bằng `nodetool`

### 4.1. Các lệnh read-only thường dùng

~~~bash
# Quan sát topology; cú pháp/output tùy Cassandra release.
nodetool status

# Node stats và local state.
nodetool info

# Trạng thái schema/topology summary theo release.
nodetool describecluster

# Gossip peer view/metadata khi cần điều tra.
nodetool gossipinfo

# JMX checks cho native transport/gossip nếu release hỗ trợ.
nodetool statusbinary
nodetool statusgossip

# Executor stage active/pending/completed/dropped.
nodetool tpstats

# Compactions, streaming và table-level indicators.
nodetool compactionstats
nodetool netstats
nodetool tablestats ops_health.probes_by_run
~~~

**Cú pháp, metric names và sự có mặt của `statusbinary`, `statusgossip`, `describecluster` có thể khác tùy Cassandra 3.x/4.x/5.x và distribution**. Trước khi đưa vào automation, đối chiếu `nodetool help` của chính bản đang chạy.

Không chạy `nodetool repair`, `drain`, `cleanup`, `compact`, `decommission` chỉ như “health check”: đây là tác vụ thay đổi trạng thái/tài nguyên, không phải quan sát vô hại.

### 4.2. Cách đọc status

Một output minh họa có dạng:

~~~text
Datacenter: dc1
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
-- Address       Load       Tokens Owns Host ID                              Rack
UN 10.1.1.11     120 GiB    16     ?    ...                                  rack1
UN 10.1.2.12     118 GiB    16     ?    ...                                  rack2
UN 10.1.3.13     125 GiB    16     ?    ...                                  rack3
~~~

Các địa chỉ, sizes và host IDs là **giả định**; dấu `?` cho ownership có thể xuất hiện nếu cluster nhiều keyspaces/RF làm ownership không biểu diễn bằng một số đơn giản.

- `U`: node được xem là Up từ nơi quan sát.
- `D`: Down theo membership/gossip view.
- `N`: Normal, khác `J` Joining, `L` Leaving, `M` Moving.
- `UN` là điều kiện hữu ích trước rolling maintenance, **không phải chứng nhận API read/write đạt SLO**.
- Node mới có thể tạm `UJ` khi bootstrap hợp lệ; gate phải hiểu expected phase.
- Đọc từ **nhiều seed/observer nodes** để giảm nguy cơ một góc nhìn gossip sai lệch.

Không dùng một phép grep `UN` không có ngữ cảnh làm quyết định sửa topology, vì output và ý nghĩa thay đổi theo DC/phase.

### 4.3. Không tin vào số lượng `UN` mà quên inventory

Ví dụ expected 6 nodes (3/DC), nhưng `nodetool status` chỉ hiện 5 dòng đều `UN`. Một script đơn giản “không thấy DN” sẽ PASS sai vì **một node vắng hoàn toàn**.

Health gate cần so với expected inventory:

- Host ID và địa chỉ/định danh logical của **từng node**.
- DC/rack placement.
- Node count theo DC.
- Token/vnode allocation và trạng thái joining/leaving dự kiến.
- Software version và upgrade status nếu là bảo trì phiên bản.
- Native transport endpoint được quảng bá mà app có thể kết nối.

Đối chiếu metadata/trust source; không dùng một IP cố định như định danh vĩnh viễn khi có node replacement.

## 5. Replication và consistency khi kiểm tính sẵn sàng

### 5.1. RF/CL quyết định “đủ replica” nghĩa là gì

Với `NetworkTopologyStrategy` và `RF(dc1)=3`, một thao tác thông thường ở `LOCAL_QUORUM` thường cần **2 replica ACK** trong local DC. Một node DOWN có thể vẫn đủ điều kiện logic, nhưng:

- Headroom chỉ còn hai replicas.
- Một replica chậm thêm có thể làm request timeout.
- Retry/streaming/hints tăng tải sau phục hồi.
- Bảo trì node tiếp theo có thể làm mất quorum.

Vì vậy preflight không chỉ hỏi **“request hiện tại có thể thành công?”** mà còn hỏi **“có an toàn để ngắt thêm node trong bước tiếp không?”**

### 5.2. Ví dụ ma trận đơn giản

| Trạng thái giả định trong dc1, RF=3 | LOCAL_ONE | LOCAL_QUORUM | Tiếp tục rolling? |
|---|---|---|---|
| 3 replica khỏe, resource headroom đủ | Có thể | Có thể | Cân nhắc PASS nếu các gate khác đạt |
| 2 replica khỏe, 1 DOWN | Có thể | Có thể | Thường HOLD: thiếu dự phòng |
| 1 replica khỏe, 2 DOWN | Có thể theo routing/policy | Không đủ quorum | FAIL cho app LOCAL_QUORUM |
| 3 node `UN` nhưng một node p99 rất xấu | Có thể | Có thể timeout | HOLD/FAIL nếu SLO vượt |
| Node bootstrap/streaming chưa hoàn tất | Phụ thuộc topology | Phụ thuộc topology | Theo gate topology-specific |

Bảng là **mô hình**, không thay thế phép tính replica set thật cho từng partition, DC, rack, transient replication, availability, LWT hay các phiên bản đặc biệt. Không suy rằng 3 nodes toàn DC đều là replicas của mọi partition trong mọi cấu hình.

### 5.3. Chọn consistency cho canary

Nếu workload production dùng `LOCAL_QUORUM`, probe chỉ chạy với `ONE` có thể PASS dù ứng dụng thật đang timeout ở quorum. Canary nên dùng **CL phù hợp workload mục tiêu**, không hạ CL cho tiện.

Trong multi-DC:

- Khởi chạy probe **tại từng local DC/client region** quan trọng.
- Dùng session `localDatacenter` đúng.
- Kiểm read/write theo CL nghiệp vụ của từng đường.
- Đánh giá cross-DC replication, streaming/repair, failover policy nếu có.
- `LOCAL_QUORUM` ở dc1 không tự chứng minh dc2 đã nhận/đọc dữ liệu.

Một probe write+read `LOCAL_QUORUM` trong dc1 chứng minh phạm vi có giới hạn; không phải kiểm tra đồng bộ mọi replicas ở mọi DC.

## 6. Schema, native transport và driver compatibility

### 6.1. Schema agreement là gate riêng

Trước/sau migration hoặc rolling upgrade, so:

- Keyspace/table/types/indexes cần cho ứng dụng.
- Cassandra schema versions/gossip agreement theo release.
- Driver schema metadata và prepared CQL compatibility.
- DDL migration order giữa app cũ/mới.
- Không có unexpected table/column drops hoặc type incompatibilities.

`nodetool describecluster` có thể hiển thị schema versions của các nodes theo release; **không dùng một dòng “schema versions” làm bằng chứng tất cả app đã reprepare hoặc tất cả queries đều hợp lệ**.

`system.local` và `system.peers_v2` (nếu release có) cho local metadata/peer view, không phải source of truth duy nhất hay bảng để sửa thủ công. Không trực tiếp chỉnh `system_schema` để “ép agreement”.

### 6.2. Native CQL phải được thử từ nơi app chạy

`nodetool` có thể kết nối qua JMX dù:

- Native transport port không nghe.
- TLS certificate hết hạn/SAN sai.
- Java truststore thiếu CA.
- CQL user bị mất quyền.
- Firewall/NetworkPolicy chặn pod.
- Driver khám phá peer addresses không reachable.

Do đó cần **new CqlSession/new connection canary**, rồi **prepared CQL**. Cqlsh chạy trên node với credential admin không thay thế một canary dùng Java driver, role và network path của ứng dụng.

### 6.3. Driver exception không đồng nghĩa server DOWN

Một `AllNodesFailedException` bao lỗi theo coordinator candidates, có thể xuất phát từ TLS, DNS, protocol, auth hoặc connection. Khi xử lý:

- Thu `getAllErrors()` theo node/cause trong kênh có quyền.
- Không coi nó là bản đồ replica ACK.
- Phân biệt `InvalidQueryException`, `UnauthorizedException`, timeout, unavailable và codec.
- Không retry mãi các lỗi cấu hình (cert, password, invalid prepared statement).

## 7. Quyết định kiểm tra read-only và read/write

### 7.1. Read-only probes

Read probe có thể dùng một row cố định đã seed, đủ primary key, với expected value ổn định:

~~~cql
SELECT check_id, expected_value
FROM ops_health.probes_by_run
WHERE run_id = ?
  AND check_id = ?;
~~~

Ưu điểm: không tạo mutation mới, dùng role `SELECT`, phù hợp preflight khi cấm write. Nhưng chỉ chứng minh **read path** và dữ liệu probe đó còn tồn tại — không xác minh write/commitlog/quorum write.

### 7.2. Read/write canary riêng

Write+read probe nên dùng:

- **Keyspace/table dành riêng**, tạo bằng schema migration được phê duyệt **trước** bảo trì.
- Partition/key theo **run_id UUID** tránh xung đột với production/user data.
- Stable check_id/value để retry idempotent.
- TTL ngắn/hợp lệ để hạn chế tích tụ dữ liệu; vẫn tạo tombstones, cần retention/compaction planning.
- Quyền `SELECT` và `MODIFY` chỉ trên probe table.
- CL thực tế, timeout/retry budget có giới hạn, latency measurements.
- Không `TRUNCATE`/`DROP TABLE` sau mỗi lần kiểm tra.

Một read-after-write thành công không chứng minh mọi replica trong mọi DC có dữ liệu hoặc không có dữ liệu cũ lệch nhau. Với consistency thích hợp, nó là **bằng chứng có phạm vi**, không phải proof of global convergence.

### 7.3. Tránh probe writes không an toàn

Không ghi vào bảng nghiệp vụ chỉ để test, vì:

- Có thể trigger event consumer/CDC/notifications.
- TTL/timestamp ảnh hưởng semantics.
- Retry có thể tạo side effects.
- Khi chạy nhiều lần, dữ liệu canary có thể bị người dùng nhìn thấy.
- LWT/counter writes có tính không-idempotent/conditional khác.
- Cleanup via bulk delete tạo tombstones/IO không cần thiết.

Không sửa production schema/role tự phát trong cửa sổ health check để có bảng probe; chuẩn bị trước.

## 8. Thiết kế keyspace/table probe thực tế

### 8.1. DDL dành cho môi trường lab/được phê duyệt

~~~cql
-- Ví dụ cho cluster một DC 3 nodes; không copy RF sang
-- cluster khác nếu chưa kiểm topology/availability.
CREATE KEYSPACE IF NOT EXISTS ops_health
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;
~~~

~~~cql
CREATE TABLE IF NOT EXISTS ops_health.probes_by_run (
    run_id uuid,
    check_id text,
    observed_at timestamp,
    expected_value text,
    PRIMARY KEY ((run_id), check_id)
);
~~~

Đối với multi-DC, xác định RF cho từng DC theo policy. Nếu muốn thử cross-DC replication, thiết kế thêm phép kiểm riêng và hiểu các CL/cấu hình failover.

### 8.2. Vì sao partition key là `run_id`?

- Một lần bảo trì có một `run_id` định danh; các probes thuộc run đó trong một partition giới hạn.
- `check_id` phân biệt read-only reference/canary hoặc nhiều loại phép thử trong run.
- Cùng `run_id + check_id` với cùng value cho phép retry **idempotent ở tầng giá trị** khi write là mutation thông thường.
- Cần giới hạn số check_id mỗi run để partition không rộng.
- Cần giới hạn số lần runs; retention TTL có thể tạo tombstones trước khi compaction.

Không dùng `now()` làm primary key mỗi retry nếu muốn đảm bảo không sinh nhiều rows; không dùng counter increment cho một health probe.

### 8.3. CQL smoke write/read

~~~cql
-- Mỗi lần chạy lấy UUID duy nhất do controller sinh,
-- cùng UUID được tái sử dụng cho retries của lần chạy đó.
INSERT INTO ops_health.probes_by_run
    (run_id, check_id, observed_at, expected_value)
VALUES (?, ?, ?, ?)
USING TTL 3600;
~~~

~~~cql
SELECT expected_value, observed_at
FROM ops_health.probes_by_run
WHERE run_id = ?
  AND check_id = ?;
~~~

Dùng một `expected_value` cố định theo lần chạy và so exact string. **TTL 3600 giây là giá trị minh họa**, không phải SLA/retention mặc định; TTL sau renew/rewrite có thể đổi expiration. Nếu preflight cần so sau thời gian dài hơn, dùng reference probe với retention phù hợp và khác check_id/run_id.

### 8.4. Read probe có data fixture ổn định

Nếu chỉ dùng TTL 1 giờ cho reference record, preflight ngày hôm sau sẽ trả empty vì đã hết hạn. Cần **reference data riêng** có tuổi thọ phù hợp, được seed trước và theo dõi expiry. Đừng biến “row expired” thành kết luận “Cassandra READ BROKEN”.

Một kế hoạch tốt có cả:

- Reference read probe với expected stable value và retention được quản lý.
- Ephemeral write-read probe để kiểm mutation path.
- Representative application query (read-only, full partition key, bounded).
- Cross-DC probe riêng nếu cần replica convergence theo policy.

## 9. Baseline và các ngưỡng quyết định

### 9.1. Tách hard gates và soft signals

**Hard gate** thường gồm:

- Bất kỳ node không thuộc expected inventory hoặc bất ngờ `DN`.
- Node ở Joining/Leaving/Moving trái planned phase.
- Không đủ replica/CL theo app.
- Schema incompatibility hoặc CQL role/query fails.
- Probe read/write có kết quả sai hay không được phép thực hiện.
- Disk/memory/headroom thấp hơn safety threshold của tổ chức.
- Có repair/streaming/backup không tương thích với thay đổi sắp thực hiện.
- Dữ liệu observability cần thiết không lấy được → **UNKNOWN**, không tự PASS.

**Soft signals** có thể gồm:

- GC pauses tăng nhẹ nhưng dưới SLO.
- Compaction pending chưa về 0 nhưng ổn định và có kế hoạch drain.
- CPU/disk await tăng ngắn khi cache warm-up.
- Request p99 cao hơn baseline chút ít nhưng vẫn trong budget.

Soft signal không được bỏ qua; cần chính sách tolerance/observation window và người có quyền phê duyệt.

### 9.2. Ví dụ manifest điều kiện trước/sau

~~~yaml
# Chỉ là ví dụ tài liệu, không phải Cassandra config thật.
change_id: MAINT-2026-041
cluster: cassandra-prod-example
local_datacenters: [dc1, dc2]
expected_nodes:
  dc1: 3
  dc2: 3
expected_states_before: ["UN"]
expected_states_after: ["UN"]
allowed_transient_state_during_rolling: ["DN", "UJ"]
replication_policy: "NTS, RF=3 per DC"
read_consistency: LOCAL_QUORUM
write_consistency: LOCAL_QUORUM
hard_gates:
  schema_compatible: true
  app_read_probe: required
  app_write_read_probe: required
  no_unexpected_down_nodes: true
  no_unexpected_topology_changes: true
limits:
  p99_read_ms: 200
  error_rate_pct: 0.5
  minimum_disk_free_pct: 20
observation_window_minutes: 15
~~~

**Các con số chỉ minh họa.** Không coi `p99≤200 ms` hay disk free ≥20% là quy chuẩn Cassandra; phải xuất phát từ SLO và runbook capacity cụ thể.

`allowed_transient_state_during_rolling` chỉ mô tả trạng thái *có thể được plan*, **không cho phép mặc nhiên tiếp tục** nếu node trong kế hoạch đang DOWN mà chưa phục hồi hoặc CL unsafe.

### 9.3. So baseline với postflight đúng cách

Không so một percentile đo trong 30 giây idle với một percentile trong giờ cao điểm rồi quy mọi chênh lệch cho maintenance.

Ghi:

- Workload mix, offered/success QPS, rows/page và payload.
- Thời điểm, duration, sample size và cách tính percentiles.
- CL/RF, client region/DC, driver/JDK versions.
- Node count/rack/token topology.
- Repair/streaming/compaction/background jobs.
- CPU/GC/disk/network/memory headroom.
- **Worst-node** metrics, không chỉ cluster average.

Một kết quả tốt là: hậu bảo trì đạt **absolute SLO** và không regress quá tolerance baseline đã thỏa thuận. Hai điều kiện nên được đánh giá riêng.

## 10. Mô hình cổng kiểm tra `PASS/FAIL/UNKNOWN`

### 10.1. Lý do cần ba trạng thái

~~~text
PASS:
  Có đủ nguồn dữ liệu, cửa sổ quan sát và điều kiện đạt.

FAIL:
  Có bằng chứng cụ thể vi phạm hard gate/SLO.

UNKNOWN:
  Không thu được dữ liệu, window quá ngắn, metric stale,
  thiếu quyền/secret probe hoặc inventory chưa xác nhận.
~~~

Nếu API không cho phép write probe do quyền `SELECT`-only nhưng manifest yêu cầu write/read, kết quả không được PASS. Có thể là `UNKNOWN` do không thể thực thi; nếu chuẩn bị/role vi phạm policy đã xác định, controller có thể đánh `FAIL` theo quy định.

### 10.2. Mã giả về tổng hợp gate

~~~text
function evaluate(gates):
    for gate in gates:
        if gate.status == FAIL:
            return FAIL
    for gate in gates:
        if gate.status == UNKNOWN:
            return UNKNOWN
    if all expected gates present and all == PASS:
        return PASS
    return UNKNOWN
~~~

Logic này ưu tiên FAIL khi đã có violation rõ, nhưng **không coi thiếu gate là PASS**. Nếu business policy yêu cầu stop ngay khi UNKNOWN, áp dụng `stop_on_unknown=true`.

### 10.3. Đừng chỉ kiểm exit code của `nodetool status`

Một lệnh `nodetool status` exit code 0 chỉ nói lệnh chạy/đọc trạng thái thành công theo interface; không đồng nghĩa mọi node đúng expected inventory hoặc đang `UN`.

Nếu automation parse output text, phải:

- Pin Cassandra/nodetool version và locale.
- Parse bảng DC/node có kiểm schema, không grep chuỗi `UN` đơn giản.
- Xác minh expected node set/rack, trạng thái và các view từ nhiều điểm.
- Khi parser không hiểu format mới → **UNKNOWN**.
- Có tests cho missing node, DN, UJ, dc renamed, output truncated.
- Ưu tiên structured metrics/API do tooling chính thức hỗ trợ nếu khả dụng.

## 11. Java Driver 4.x: smoke test read/write có kiểm chứng

### 11.1. Hợp đồng của probe

Java probe nhận **`CqlSession` đã cấu hình sẵn**, thay vì tự lưu password/CA trong code. Session cần:

- Contact points và local datacenter đúng môi trường.
- TLS trust/hostname validation và CQL credentials theo policy.
- Keyspace `ops_health` có bảng `probes_by_run` được tạo **trước** maintenance.
- Role canary có `SELECT` và `MODIFY` chỉ trên bảng probe.
- RF/DC và consistency level phù hợp môi trường.
- Một `UUID runId` được controller tạo **một lần cho mỗi run**, giữ ổn định khi retry.
- Giá trị expected cố định, không dùng một string khác trên mỗi attempt.

### 11.2. Mã Java với prepared statements

~~~java
package example.cassandra.ops;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class CassandraReadWriteProbe {
    private final CqlSession session;
    private final PreparedStatement write;
    private final PreparedStatement read;

    public CassandraReadWriteProbe(CqlSession session) {
        this.session = Objects.requireNonNull(session);

        this.write = session.prepare(
            "INSERT INTO ops_health.probes_by_run " +
            "(run_id, check_id, observed_at, expected_value) " +
            "VALUES (?, ?, ?, ?) USING TTL ?"
        );

        this.read = session.prepare(
            "SELECT expected_value, observed_at " +
            "FROM ops_health.probes_by_run " +
            "WHERE run_id = ? AND check_id = ?"
        );
    }

    public ProbeResult check(
            UUID runId, String checkId, String expected,
            Instant observedAt) {
        Objects.requireNonNull(runId);
        Objects.requireNonNull(checkId);
        Objects.requireNonNull(expected);
        Objects.requireNonNull(observedAt);

        if (checkId.isBlank() || expected.isBlank()) {
            throw new IllegalArgumentException(
                "probe identifiers must be nonempty");
        }

        BoundStatement writeStatement = write
            .bind(runId, checkId, observedAt, expected, 3600)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .setTimeout(Duration.ofSeconds(5));

        long writeStarted = System.nanoTime();
        session.execute(writeStatement);
        long writeNanos = System.nanoTime() - writeStarted;

        BoundStatement readStatement = read
            .bind(runId, checkId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .setTimeout(Duration.ofSeconds(5));

        long readStarted = System.nanoTime();
        Row row = session.execute(readStatement).one();
        long readNanos = System.nanoTime() - readStarted;

        if (row == null) {
            return ProbeResult.fail(
                "READ_RETURNED_NO_ROW", writeNanos, readNanos);
        }

        if (!expected.equals(row.getString("expected_value"))) {
            return ProbeResult.fail(
                "READBACK_MISMATCH", writeNanos, readNanos);
        }

        return ProbeResult.pass(writeNanos, readNanos);
    }

    public record ProbeResult(
            boolean pass,
            String code,
            long writeNanos,
            long readNanos) {

        static ProbeResult pass(long w, long r) {
            return new ProbeResult(true, "PASS", w, r);
        }

        static ProbeResult fail(String code, long w, long r) {
            return new ProbeResult(false, code, w, r);
        }
    }
}
~~~

Ví dụ dùng Java `record` nên cần Java 16+; nếu Cassandra/driver được triển khai trên JDK thấp hơn, thay bằng class POJO. API `setTimeout`, `setIdempotent` và bind values cần được kiểm trên đúng Java Driver 4.x release, JDK và custom codecs.

**Cần chỉnh CL cho cluster lab:** nếu lab chỉ có một node/RF=1, `LOCAL_QUORUM` tương đương một replica trong DC đó theo quorum arithmetic, nhưng chính sách/compatibility vẫn phải được kiểm; ví dụ ở đây nhằm kiểm workload RF=3 của một DC, không phải một lệnh dùng cho mọi môi trường.

### 11.3. Ghi đè cùng key có phải retry an toàn?

Cùng `runId`, `checkId` và `expected` giúp **giữ một key**, không sinh thêm rows. Nhưng:

- Mỗi retry `INSERT` mới có timestamp/TTL nên có thể gia hạn expiration.
- Controller truyền cùng `observedAt` cho các attempts thuộc một run; không lấy `Instant.now()` mới trên mỗi retry. Như vậy giá trị `observed_at` và `expected_value` ổn định.
- Dù payload ổn định, mỗi lần ghi lại có thể làm mới TTL hoặc mutation timestamp theo Cassandra. Chỉ đánh dấu `setIdempotent(true)` khi việc refresh này **không gây side effect nghiệp vụ**; nếu cần idempotency nghiêm ngặt, phải cố định write timestamp/retention policy hoặc bỏ timestamp/TTL khỏi mutation và quản lý cleanup riêng.
- Không suy tính idempotent của counter/LWT từ ví dụ này.

Với production automation, **không retry vô hạn**. Timeout write có thể là uncertain outcome; hãy thử read-back bằng CL phù hợp với cùng key và đối soát, nếu không đủ bằng chứng thì `UNKNOWN` hoặc FAIL theo policy.

### 11.4. Chuyển kết quả exception thành gate

Ví dụ trên ném exception khi driver/CQL lỗi. Controller bao ngoài phải:

1. Phân loại auth/TLS/codec/`InvalidQuery`/unavailable/timeout.
2. Log query template, error family, local DC, UTC time, `runId` và check ID.
3. Không log passwords, raw contact point list khi không được phép, bind values nhạy cảm.
4. Quyết định `FAIL` nếu đã có vi phạm, `UNKNOWN` nếu không thể xác minh do mất observability/role.
5. Giới hạn attempts, latency và cancellation; không tạo storm khi cluster đang degraded.

### 11.5. Không dùng `wasApplied()` cho regular write

`wasApplied()` có ý nghĩa trong conditional statements như `INSERT ... IF NOT EXISTS`. Với `INSERT` thường, **không dùng nó để suy server đã apply tại mọi replica**. Bằng chứng ứng dụng cần:

- Không có exception ở CL được chọn.
- Probe đọc lại đúng giá trị bằng read CL phù hợp.
- Node/replica state và availability gates riêng.
- Metrics liên quan sau write để đảm bảo cluster ổn định.

## 12. Read-only probe theo query nghiệp vụ có kiểm soát

### 12.1. Vì sao cần nhiều hơn bảng `ops_health`?

Probe table thường rất nhỏ, có partition và SSTable đơn giản. Trong khi query production có thể:

- Đọc `(device_id, event_day)` với nhiều clustering rows.
- Gặp TTL/tombstones và SSTable merge.
- Dùng Java codecs/UDTs khác.
- Có ảnh hưởng từ secondary index/SAI hoặc page size.
- Truy cập nhiều DC/tenants và bảng khác.

Một `SELECT` trên `ops_health` PASS không chứng minh mọi query nghiệp vụ hoạt động.

### 12.2. Ví dụ representative query

~~~cql
-- Table nghiệp vụ giả định đã có sẵn.
SELECT event_time, reading_value, status
FROM telemetry.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
ORDER BY event_time DESC
LIMIT 20;
~~~

**Dùng key seeded hoặc một fixture non-sensitive, được phép truy cập.** Nếu query expected 20 rows nhưng data đã TTL expire hoặc writer chuyển day bucket, “row count giảm” không nhất thiết do maintenance. Nên kiểm expected result/shape theo data contract.

Tránh scan table, `ALLOW FILTERING`, `SELECT *` không có partition key hoặc `COUNT(*)` trên partition quá lớn để “test sức khỏe”; các phép thử có thể tự gây latency/GC và false alarms.

### 12.3. Query correctness gates

| Gate | Điều muốn chứng minh | Cần quan sát |
|---|---|---|
| Prepare | Schema/CQL vẫn tương thích | Prepared statement được server chấp nhận |
| Execute read | Read CL và network hoạt động | Request success, exception, latency |
| Result shape | Mapping Java không hỏng | Column types, row mapper, nonnull fields |
| Semantic result | Data fixture đúng | Expected row/key/value/timestamp |
| Pagination | Multi-page không bị lỗi | Fetch next page bounded |
| Authorization | App role còn đủ quyền | Không có unauthorized/auth failures |
| Workload | p99/budget vẫn đạt | Time series & node resource |
| Multi-DC | Regions/DC được phục vụ | Probe riêng theo DC |

Với query cần metadata/schema mới sau upgrade, thử **Java app version cũ và mới** trong giai đoạn compatibility window.

## 13. Kiểm tra partition coverage và local DC

### 13.1. Một key không đại diện cả token ring

Cassandra phân tán theo token của **partition key**. Probe chỉ dùng `run_id` có thể luôn route về cùng một tập replica; một node/rack khác bị lỗi có thể không nằm trong replica set của partition đó.

Để tăng coverage khi cần:

- Thử nhiều `run_id`/partition keys được tạo an toàn.
- Ghi token/target replica mapping bằng tooling được phê duyệt nếu thực sự cần.
- Kiểm trạng thái **tất cả nodes** qua topology gate độc lập.
- Chạy probe ở từng DC/app client region.
- Kiểm CQL requests được driver route tới nhiều coordinators trong test có kiểm soát.
- Giới hạn probe QPS/bytes để không khuếch đại tải.

**Không** tuyên bố “đã kiểm tất cả replica” chỉ vì đã chạy 10 writes; không biết token distribution thì 10 keys có thể rơi vào cùng một số replicas.

### 13.2. CL quorum không thay thế kiểm ứng dụng

Với RF=3/`LOCAL_QUORUM`, một read/write có thể thành công khi một node còn lỗi. Để quyết định bảo trì node tiếp:

- Cần topology inventory và node states.
- Cần headroom trên **replicas còn lại**.
- Cần degraded workload p99/error budget.
- Cần kiểm data correctness theo nghiệp vụ, không chỉ một probe key.
- Cần tránh bắt đầu repair/streaming khác làm mất headroom.

### 13.3. Cross-DC smoke tests

Nếu app có thể chuyển vùng hoặc yêu cầu phục vụ ở dc1 và dc2, một bài kiểm riêng phải rõ:

~~~text
From region A, session localDc=dc1:
  CL=LOCAL_QUORUM, read + write probes, latency/error.

From region B, session localDc=dc2:
  CL=LOCAL_QUORUM, read + write probes, latency/error.

Cross-DC visibility:
  test riêng theo replication/convergence policy;
  không suy từ một LOCAL_QUORUM read ở dc1.
~~~

Không đưa cùng `CqlSession` localDc không đúng vào cả hai vùng rồi suy host/rack từ IP một cách đoán mò. Cần phân biệt **availability local DC** và **inter-DC replication lag/repair**.

## 14. `system.local`, peers và giới hạn của metadata

### 14.1. Query nhỏ để nhận diện node/schema

Một số release hỗ trợ truy vấn:

~~~cql
SELECT host_id, release_version, data_center, rack,
       schema_version
FROM system.local;
~~~

`system.local` là metadata từ **node coordinator mà session truy vấn**; không phải toàn cluster consensus. Các trường có thể thay đổi theo Cassandra release.

Với release có `system.peers_v2`:

~~~cql
SELECT peer, host_id, data_center, rack, schema_version
FROM system.peers_v2;
~~~

Tên bảng/cột và semantics của peers khác giữa Cassandra 3.x/4.x/5.x. **Đừng dựa vào một peer row bị thiếu để kết luận node đã mất dữ liệu**: peer views là trạng thái lan truyền và cần đối chiếu `nodetool status`/inventory.

### 14.2. Không dùng system tables để thay đổi trạng thái

Dù query metadata hữu ích, health automation **không ghi trực tiếp `system.local`, `system.peers_v2`, `system_schema`**. Những thay đổi topology/schema phải đi qua cơ chế Cassandra và runbook được hỗ trợ.

### 14.3. Chọn người quan sát

Nếu query `system.local` qua load balancer, các lần gọi có thể tới coordinator khác, gây khó phân biệt snapshots. Giải pháp quan sát:

- Thu thông tin có định danh node từ các seed observers được phép.
- Ghi host ID/DC/rack và timestamp cho từng sample.
- Không nhầm driver contact point với replica set của partition.
- Xử lý node restart/metadata thay đổi khi topology change.
- Dùng nhiều nguồn đối chiếu thay vì một câu query duy nhất.

## 15. Resource health gates: tránh PASS khi node sắp quá tải

### 15.1. JVM/OS headroom

Cần so theo **node nóng nhất** và tài nguyên có hạn mức thật:

| Resource | Dấu hiệu cần kiểm | Liên hệ maintenance |
|---|---|---|
| CPU per-core/quota | Busy/throttling/steal | Restart làm tải dồn lên peers |
| JVM GC | Pause p95/max, post-GC occupancy | Stop-the-world có thể kéo p99 |
| Heap/off-heap/RSS | Memory pressure, OOM events | Cache/warm-up/compaction tăng footprint |
| Disk free | GiB/% trên đúng data/commitlog volumes | Streaming/compaction cần temporary headroom |
| Disk await/IOPS | Device latency và queue | Flush/repair cạnh tranh read |
| Network | RTT, retransmits, NIC bytes/s | Gossip/streaming/replica traffic |
| File descriptors/threads | Limits, errors | Node có thể `UN` nhưng CQL connections fail |
| Cgroup | `memory.events`/`cpu.stat` | Pod OOMKilled hoặc throttled |
| Native transport | Connection failures/in-flight | TLS/auth/pool reconnect |

Không dùng “heap chỉ 40%” để bỏ qua cgroup OOM hoặc disk free sắp chạm zero. Không dùng trung bình CPU toàn cluster để bỏ qua một replica nóng.

### 15.2. Compaction không phải luôn phải bằng 0

Cassandra thường có compaction/flush nền khi hệ thống khỏe. Gate hợp lý là:

- Active/pending compactions theo workload bình thường?
- Pending backlog có tăng không giới hạn?
- Disk headroom đủ cho quá trình rewrite?
- p99/timeout vẫn trong budget?
- Công việc background dự kiến sau maintenance có hoàn thành đúng kế hoạch?

Một gate “`pending=0` mọi lúc” có thể làm pipeline không thể PASS dù cluster hoạt động bình thường. Nhưng pending tăng liên tục và disk gần full là hard safety signal.

### 15.3. Hints, repair và streaming

- `nodetool netstats` chủ yếu quan sát **SSTable streaming**; `netstats` trống **không** chứng minh tất cả CQL/replication network idle.
- Hints có thể tồn tại/được replay sau node outage, cần metrics/time trend theo release.
- Repair có thể chưa diễn ra ngay sau node comeback; consistency/correctness policy cần kế hoạch repair rõ.
- Bootstrap/replace/decommission có thể thay token/rack placement và streaming trong window; gates phải biết **phases**.
- Một node `UN` chưa chắc hết công việc recovery hoặc mọi SSTable/replica đã đồng bộ.

## 16. Quan sát p95/p99, error và retry một cách nhất quán

### 16.1. Tách nhóm outcome

Đối với CQL/Java probe và query nghiệp vụ:

- Offered logical requests/s.
- Completed/successful requests/s.
- Error rate phân nhóm auth, invalid query, timeout, unavailable, transport.
- Driver retry/speculative attempts/s (nếu metric khả dụng).
- p50/p95/p99 **của successes** cùng tỷ lệ timeout; không xem p99 success đơn độc.
- Client app response p95/p99, không chỉ server read/write latency.
- Worst-node latency/GC/disk và số lượng request samples.

### 16.2. Không average p99

Giả sử node A p99=30 ms, B p99=60 ms, C p99=600 ms; trung bình ba số **không phải** cluster p99. Nếu hệ export histograms, cần aggregate buckets đúng phương pháp và label, có sample count.

Thống kê p99 2 giây của chỉ 4 probe requests không ổn định. **Single probe latency** là điểm canary chứ không phải percentile đáng tin. Cần time-series của workload đủ samples trong observation window.

### 16.3. Ví dụ acceptance rules (giả định)

~~~text
Preflight:
  unexpected_down_nodes = 0
  schema_compatible = true
  CQL read + write probe pass in each required DC
  p99_app_read <= agreed SLO
  error_rate <= agreed budget
  resource headroom >= organization threshold
  no incompatible repair/streaming/topology work

Postflight:
  expected topology/node state reached
  new connections TLS/auth/CQL pass
  CQL read + write probe pass, expected values match
  business query templates pass
  p99_app_read and error_rate within budget
  queues/compaction/hints/streaming stable or on approved track
  no new unexpected OOM/FD/disk pressure
  observation window sufficient
~~~

Các thresholds phải định nghĩa qua SLO/on-call policy, không lấy từ ví dụ. Nếu preflight đã lỗi, phải ghi baseline không đáng tin và **không tự “đánh PASS sau bảo trì vì so với baseline xấu hơn”**.

## 17. Thiết kế pipeline kiểm tra theo giai đoạn

### 17.1. Một pipeline có thể triển khai

~~~mermaid
flowchart LR
    A["Collect inventory + change manifest"] --> B["Read-only preflight"]
    B --> C{"Gate"}
    C -->|PASS| D["Approved operation 1"]
    C -->|FAIL / UNKNOWN| E["STOP + on-call"]
    D --> F["Node/service gate"]
    F --> G{"PASS?"}
    G -->|Yes| H["Next planned operation"]
    G -->|No| E
    H --> I["Postflight cluster + CQL + metrics"]
    I --> J{"SLO & correctness achieved?"}
    J -->|Yes| K["Close change, archive evidence"]
    J -->|No| L["Hold, recovery/rollback"]
~~~

Pipeline **không tự gọi** các lệnh bảo trì nếu chưa có approval/checkpoint. Ví dụ tập trung vào sức khỏe, không thay một SOP rolling upgrade/repair chính thức.

### 17.2. Các artifacts nên lưu

| Artifact | Trường dữ liệu | Dùng để làm gì |
|---|---|---|
| Change manifest | ID, owner, scope, expected deltas | Xác minh mục tiêu |
| Preflight report | Node inventory, DC/rack, schema, probes | Baseline/điều kiện bắt đầu |
| Maintenance timeline | Node steps, times, guardrails | Correlate incidents |
| Postflight report | Actual vs expected, query results, metrics | PASS/FAIL/UNKNOWN |
| Probe receipts | Run UUID, check ID, CL, latency, outcome | Bằng chứng reproducible |
| Resource snapshots | Worst-node CPU/GC/disk/queues | Capacity/safety |
| Rollback log | Decisions, approvals, verification | Recover/audit |
| RCA | Failure root cause, change controls | Ngừa lặp lại |

Không cần copy raw auth secrets, CQL bind values hay toàn bộ production data vào artifacts. Giữ evidence theo retention và permission policy.

### 17.3. Timeouts và cancellation

Một health check có deadline phải có:

- Per-query timeout.
- Per-gate timeout.
- Overall preflight/postflight timeout.
- Max attempts/backoff và tổng request budget.
- Cancellation semantics khi tool/controller bị dừng.
- Policy khi bước nào đó không hoàn tất: **UNKNOWN** hoặc FAIL, không PASS.

Deadline phải phù hợp workload; không đơn thuần nâng timeout để giấu p99 xấu.

## 18. Scheduler, idempotency và tránh probe storm

### 18.1. Nhiều controller chạy cùng lúc

Trong automation, có thể có:

- Hai Jenkins/GitHub Actions workflows trùng change ID.
- Một runner timeout nhưng vẫn còn request in-flight.
- Health probe được autoscaled theo mỗi pod.
- Retries ở controller và ở Java Driver cùng tăng.
- Một on-call engineer kích hoạt lại run vì không thấy kết quả.

Cần **lock/lease hoặc single-owner theo change ID** ở orchestrator; theo dõi trạng thái `running/finalized` và giới hạn số probes/s.

### 18.2. Stable run ID và retry budget

~~~text
change_id = MAINT-2026-041
run_id    = UUID generated once
check_id  = rw-local-dc1
expected  = fixed non-sensitive nonce for this run

Attempt 1 -> timeout while writing
Attempt 2 -> optionally read back same row first
Attempt 3 -> bounded retry only if policy allows
No endless retries, no new run_id per attempt.
~~~

Không biến nonce thành secret hay ngẫu nhiên hóa khác nhau mỗi retry rồi báo mismatch giả. Trong ví dụ `observed_at` thay đổi khi retry, nên phải cân nhắc read-back semantics như mục 11.3.

### 18.3. Backpressure và giới hạn tải

Một health system gây thêm 10.000 CQL requests/s khi cluster đang degraded có thể tự làm sự cố nặng hơn. Đặt:

- Max concurrent probes theo DC.
- Max QPS, bytes/s và time window.
- Max pages/rows per query.
- Priority/throttling để traffic nghiệp vụ được ưu tiên.
- Guardrail dừng nếu p99/failed requests vượt threshold.
- Không tạo client session/TLS handshake mới trên từng request.

**Health probe phải nhẹ hơn workload mà nó đang kiểm.**

## 19. Security, quyền hạn và phạm vi bảo trì

### 19.1. Least privilege

| Tác nhân | Quyền cần | Không nên có mặc định |
|---|---|---|
| Read-only observer | JMX/metrics hoặc `SELECT` metadata được phép | Schema ALTER/role admin |
| CQL read probe | `SELECT` trên probe + fixture | `MODIFY` app tables |
| CQL write probe | `SELECT`/`MODIFY` trên `ops_health.probes_by_run` | ALL PERMISSIONS toàn cluster |
| Maintenance operator | Quyền riêng theo SOP/tool | Account ứng dụng dùng làm admin |
| Report reader | Metrics/logs đã redaction | Raw secrets/heap dumps |

`nodetool` qua JMX có auth/TLS/permissions riêng. Một app role có `SELECT` không tự có quyền JMX `status`; không cố gán mọi tài khoản là superuser để tránh phân biệt.

### 19.2. Xác minh TLS và certificate sau rotate

Nếu maintenance thay certificates/CA:

- Test **new connections** từ đúng app namespace/region, không chỉ pool đã tồn tại.
- Kiểm chain, SAN, NotBefore/NotAfter và truststore/SSLContext của Java.
- Không tắt hostname validation hoặc trust-all.
- Phân biệt client-to-node, internode và JMX TLS.
- Kiểm CA overlap/rolling và recovery khi một node chưa dùng cert mới.
- Có test authentication + authorization cho CQL probe role.

Một `nodetool status` OK không chứng minh native TLS đã khôi phục.

### 19.3. Giữ dữ liệu/probe receipts an toàn

Báo cáo nên ghi:

- Code của outcome, local DC, CL, query template, run UUID.
- Duration và UTC time, release versions, node group.
- Error class đã phân loại và safe explanation.
- Certificate fingerprint/serial **nếu được cho phép**, không private key.
- Links tới metrics bị giới hạn truy cập.

Không ghi password, client cert private keys, raw application tenant IDs, JWT/token, heap dumps hoặc bind values nhạy cảm.

## 20. Kịch bản rolling restart: trạng thái mong đợi thay đổi theo pha

### 20.1. Timeline mẫu

~~~text
T-20m    Inventory + initial baseline + CQL probes.
T-10m    Confirm no unplanned DN/repair/backfill.
T0       Start approved restart of node A.
T+...    Node A may briefly be DOWN during planned window.
T+...    Wait A returns expected state + native CQL reachable.
T+...    Observe queues/retries/resources in recovery.
T+...    Gate A PASS => only then consider node B.
T-end    Postflight all nodes, DCs, read/write/probes/SLO.
T+obs    Sustained monitoring + evidence/close or rollback.
~~~

`T+...` là **mốc phụ thuộc điều kiện**, không phải lời hứa số phút cố định. Không để script chờ một khoảng thời gian cố định rồi cho PASS nếu trạng thái vẫn không đúng.

### 20.2. Gate theo node khác gate toàn cluster

Một node trở lại `UN` chưa đủ để tiếp tục nếu:

- Thông tin DC/rack/host ID khác expected.
- Quorum trong DC khác bị ảnh hưởng.
- Native transport chưa sẵn sàng.
- CQL requests vào node/region có lỗi.
- Hints/streaming/compaction đang overload.
- Disk/GC/network không có headroom.
- Query business correctness không đạt.

### 20.3. Rolling upgrade có kiểm tra tương thích

Ngoài liveness/latency, khi thay Cassandra/JDK/Driver:

- Xác minh mixed-version compatibility trong window được hỗ trợ.
- Kiểm prepared CQL, native protocol, codecs và TLS/auth.
- So schema metadata và system tables sau nâng cấp.
- Đừng chạy schema/data format changes hoặc `upgradesstables` tự phát nếu runbook không yêu cầu.
- Có backout plan, biết thao tác nào làm rollback không khả thi.
- Quan sát nền compaction, hinted handoff và repair.

## 21. Runbook A — Preflight thấy node `DN` hoặc node mất khỏi inventory

**Tình huống:** Chưa bảo trì nhưng một observer thấy 5/6 nodes `UN`, một node `DN` hoặc không xuất hiện trong danh sách.

1. **Dừng thay đổi kế tiếp:** tình trạng hiện tại không đáp ứng expected inventory; gắn `FAIL` hoặc `UNKNOWN` nếu quan sát thiếu.
2. Xác định node nào bị ảnh hưởng bằng host ID, DC/rack và trạng thái dự kiến theo change manifest.
3. Thu `nodetool status` từ ít nhất hai observers được phép, đối chiếu monitoring và node inventory.
4. Phân biệt `DN`, `UJ` trong bootstrap được kế hoạch, node hoàn toàn vắng khỏi ring view.
5. Kiểm service logs, process, disk, network/gossip, native transport và TLS giữa các nodes.
6. Xác minh **RF/CL theo từng DC**; một ứng dụng `LOCAL_QUORUM` có thể vẫn chạy nhưng không còn dự phòng cho restart khác.
7. Nếu node bị replace/decommission trong kế hoạch, so theo **expected topology sau thay đổi**, không bắt buộc giống baseline.
8. Không chạy `nodetool removenode`, `decommission`, `replace` hoặc restart hàng loạt theo phản xạ.
9. Chỉ mở lại gate khi inventory/topology/CL, tài nguyên và query probes đáp ứng policy hoặc có phê duyệt incident riêng.
10. Lưu evidence: node IDs, DC/rack, sample times, observer views và root cause.

**Tránh lỗi phổ biến:** script chỉ kiểm “không có DN” nhưng **không kiểm expected node count**, khiến node biến mất hoàn toàn vẫn PASS.

## 22. Runbook B — `nodetool status` có `UN` nhưng ứng dụng không kết nối CQL

**Tình huống:** Sau thay TLS hoặc rolling restart, `nodetool status` đẹp; Java canary nhận `AllNodesFailedException`.

1. Xác định app pod, region, local DC, driver/JDK version và đúng contact points.
2. Đọc `getAllErrors()` theo coordinator candidates/cause; không suy tất cả replicas DOWN.
3. Phân loại network/TCP, DNS, TLS trust/SAN/expiry, CQL credentials hoặc protocol mismatch.
4. Kiểm native transport/`statusbinary` theo release, nhưng không coi JMX success là native CQL success.
5. Đối chiếu client truststore/SSLContext và server certificate thực sự serve trên endpoint.
6. Kiểm role `LOGIN`, mật khẩu/secret version, quyền `SELECT`/`MODIFY` của probe.
7. Nếu driver khám phá peer addresses khác contact points, kiểm SAN/DNS/routing cho mọi peer cần dùng.
8. Sửa trust/CA/secret/endpoint theo change procedure; **không dùng trust-all manager, không bỏ hostname verification**.
9. Test **new connection** và prepared read/write từ app network ở từng DC bắt buộc.
10. Chỉ PASS khi authentication, authorization, CQL query và resource/SLO gates cùng đạt.

**Không** tăng connection pool/retry vô hạn để chữa lỗi CA hoặc password sai.

## 23. Runbook C — Read probe PASS, write/read probe FAIL

**Tình huống:** `SELECT` từ reference row thành công, nhưng `INSERT` trong `ops_health.probes_by_run` lỗi hoặc đọc lại không khớp.

1. Xác minh đó là **đúng table/role/môi trường**; role có `MODIFY` trên probe table hay chỉ `SELECT`?
2. Đọc class và nguyên nhân: `Unauthorized`, `InvalidQuery`, `WriteTimeout`, `Unavailable`, driver codec hay TLS.
3. Kiểm CL write/read và RF/DC: có đủ replicas cho `LOCAL_QUORUM` không?
4. Kiểm commitlog/disk free, memtable flush, write p99 và `MutationStage Pending` nếu metric có.
5. Kiểm value được viết: `run_id/check_id/expected` phải cố định trong cùng attempt group.
6. Nếu `INSERT` timeout, **không suy mutation đã rollback**; thử read-back có giới hạn bằng key/CL phù hợp, phân loại outcome chưa chắc chắn.
7. Nếu SELECT trả null, kiểm row TTL đã hết hạn, sai UUID/bucket hoặc read-path/query routing.
8. Nếu mismatch, kiểm concurrent runs dùng cùng key hoặc expected thay đổi do retry.
9. Không sửa bằng cách ghi vào bảng nghiệp vụ, xóa data, hạ CL hoặc thêm superuser.
10. HOLD bảo trì, ghi outcome và sửa root cause; chỉ mở lại gate khi write path, read-back và SLO ổn.

**Read thành công không chứng minh commitlog, write coordinator, replicas hay permission ghi đang hoạt động.**

## 24. Runbook D — Schema disagreement hoặc `InvalidQuery` sau upgrade

**Tình huống:** Một số Java pods chuẩn bị CQL được, một số báo unknown column/table hoặc `InvalidQuery` ngay sau DDL/rolling upgrade.

1. Xác định app version và prepared CQL templates bị lỗi.
2. Kiểm đúng keyspace/cluster/DC và table schema ở các observers.
3. Kiểm `nodetool describecluster`/schema agreement theo release.
4. So thứ tự migration: additive DDL có chạy trước app version mới không?
5. Kiểm cột/UDT type, quoted identifiers và CQL syntax compatibility theo Cassandra/driver release.
6. Kiểm `UnpreparedException` và driver reprepare behavior; không nhầm driver cache với Cassandra data loss.
7. **Dừng rollout**, không chạy `DROP/CREATE TABLE` lại trên dữ liệu thật.
8. Nếu rollback schema không tương thích, kích hoạt kế hoạch forward-fix đã duyệt; không giả định có thể hạ version an toàn.
9. Sau sửa, canary prepare+execute các query templates quan trọng bằng cả client versions cần hỗ trợ.
10. PASS chỉ khi schema/driver compatibility, correctness, error và latency đạt.

Không sửa trực tiếp `system_schema` tables, không restart toàn cluster chỉ để đồng bộ metadata theo suy đoán.

## 25. Runbook E — p99 xấu dù state/CQL smoke PASS

**Tình huống:** Sau rolling restart, 6/6 nodes `UN`, canary ghi–đọc đúng, nhưng API read p99 tăng từ 80 lên 700 ms trong cùng workload window.

1. Xác định **absolute SLO** và regression tolerance trước khi đánh giá.
2. So offered/successful QPS, query mix, payload, rows/page và sample count.
3. So worst-node GC pauses, CPU throttling, disk await, network latency.
4. Kiểm cache cold-start sau restart: OS page cache, key/chunk caches và read path.
5. Kiểm compaction/flush pending, hints replay, repair/streaming, SSTables/read.
6. Kiểm driver retry/speculative attempts và connection pool reestablishment.
7. Giảm background jobs không thiết yếu, giữ user traffic priority theo SOP.
8. Không tăng driver timeout để che p99, không coi `nodetool status` là performance gate.
9. Giữ observation window đủ lâu để thấy trend về baseline; không PASS sau một sample thấp.
10. Nếu vượt SLO dai dẳng, HOLD/rollback theo khả năng và bảo toàn evidence.

**Correctness PASS và readiness `UN` không làm performance SLO tự PASS.**

## 26. Runbook F — Hints, compaction hoặc streaming chưa phục hồi

**Tình huống:** Node đã trở lại `UN` sau thay disk/restart, nhưng `compactionstats` pending tăng, streaming chưa xong, hinted handoff còn backlog.

1. Xác định công việc nào được **kế hoạch** trong change (bootstrap/repair/rebuild).
2. Đọc `nodetool compactionstats/netstats` theo release, so time-series metrics.
3. Kiểm disk free, device await, CPU/GC, network và native CQL error rate.
4. Kiểm write/read CL, replica liveness và số requests phải retry.
5. Đối chiếu backlog trend: đang drain ổn định hay tăng nhanh?
6. Không đặt yêu cầu `compaction pending == 0` tuyệt đối cho cluster đang nhận writes bình thường.
7. Nhưng không cho PASS nếu backlog tăng không kiểm soát hoặc disk gần đầy.
8. Không kích hoạt thêm major compaction/repair/cleanup khi resources không có headroom.
9. Có checkpoint và owner cho việc tiếp tục/nối lại repair/streaming theo runbook.
10. Chỉ đóng change khi recovery hoàn tất hoặc nằm trong **accepted recovery envelope** có thể giám sát; không tự đánh `PASS` bằng cách tắt metric.

## 27. Runbook G — Controller thiếu metrics hoặc chạy đồng thời

**Tình huống:** Health dashboard không trả GC/driver metrics; automation vẫn chạy tiếp. Hai runners cùng change ID tạo probe với keys khác nhau và request rate tăng.

1. Dừng thao tác tiếp theo; kiểm `UNKNOWN` vì thiếu evidence.
2. Xác minh collector, scrape timestamp, query window, app version và labels.
3. Không biến timeout của metrics endpoint thành giá trị `0`.
4. Kiểm controller run leases, duplicate workflows và stable `run_id`.
5. Kiểm max concurrent probes/QPS, driver retry budget và deadlines.
6. Kiểm có vô tình tạo một `CqlSession` mới cho mỗi probe request không.
7. Khôi phục observability hoặc dùng kênh dự phòng **được policy chấp nhận**, ghi rõ nguồn.
8. Nếu không có đủ bằng chứng, yêu cầu human approval/hold; không bypass gate im lặng.
9. Sau sửa, test missing/stale metrics và duplicate runs trong CI.
10. Lưu audit trail: vì sao gate UNKNOWN, ai phê duyệt tiếp tục hoặc rollback.

**Không có số liệu là không biết, không phải sức khỏe bằng 100%.**

## 28. Runbook H — Cross-DC failover sau bảo trì

**Tình huống:** dc1 ứng dụng chạy ổn, nhưng sau routing failover sang dc2, client timeout hoặc đọc dữ liệu khác kỳ vọng.

1. Kiểm source và destination DC, client `localDatacenter` của từng region.
2. So RF per DC, replica health và CL của read/write.
3. Kiểm native TLS/auth/network từ **client region mới** tới dc2.
4. Probe read/write `LOCAL_QUORUM` tại dc2 với key/value mới do dc2 ghi.
5. Nếu cần cross-DC visibility, dùng **separate replication/convergence probe** với timing và policy cụ thể.
6. Kiểm multi-DC network traffic, hints, streaming/repair, latency và packet loss.
7. Không đồng nhất `LOCAL_QUORUM` tại dc1 với quorum tại dc2.
8. Nếu app có stale data concern, kiểm timestamps/TTL và consistency requirements, không suy CQL read đúng vì “có một row”.
9. Tạm giữ traffic ở vùng an toàn theo failover SOP hoặc rollback routing khi được phép.
10. Chỉ PASS khi cả **connectivity, correctness, latency và replica recovery** ở vùng mục tiêu đạt.

**Cross-DC failover là một thay đổi đường phục vụ**, không chỉ đổi một contact point.

## 29. Ma trận kiểm thử health-gate automation

Các phép thử sau áp dụng vào CI/lab nhiều node khi cần; **không tự fault-inject vào production**.

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| T01 | Tất cả expected nodes `UN`, probes và SLO đạt | PASS |
| T02 | Một expected node `DN` trước bảo trì | FAIL/HOLD |
| T03 | Một node không xuất hiện trong status | FAIL/UNKNOWN; không PASS |
| T04 | `UJ` trong planned bootstrap phase | Theo phase gate, chưa PASS final |
| T05 | `UJ` ngoài planned phase | FAIL/HOLD |
| T06 | DC/rack khác expected inventory | FAIL hoặc điều tra thay đổi |
| T07 | Node count đúng nhưng host ID sai sau replace | So replace manifest, không PASS vô điều kiện |
| T08 | `nodetool status` exit 0 nhưng có DN | FAIL |
| T09 | JMX OK, native TLS fail | CQL gate FAIL |
| T10 | Java auth sai dù ring UN | CQL auth gate FAIL |
| T11 | Role canary thiếu MODIFY | Write gate FAIL/UNKNOWN theo policy |
| T12 | Reference read expected value đúng | Read gate PASS |
| T13 | Reference row TTL expired | Fixture invalid/UNKNOWN, không gán data loss |
| T14 | Write success, read-back mismatch | FAIL |
| T15 | Write timeout, read-back có value | Outcome phải phân tích, không tự PASS toàn bộ |
| T16 | One-key probe pass nhưng node khác DN | Cluster gate FAIL |
| T17 | Client from dc1 pass, dc2 cannot connect | Multi-DC gate FAIL |
| T18 | New TLS connection sau rotation fail | FAIL dù pool cũ còn chạy |
| T19 | Schema disagreement sau migration | FAIL/HOLD |
| T20 | Prepared CQL invalid trên app mới | FAIL/rollback hoặc forward-fix |
| T21 | p99 vượt absolute SLO với probe success | FAIL |
| T22 | p99 success giảm nhưng timeout tăng | FAIL nếu error budget vượt |
| T23 | Missing metrics trong observation window | UNKNOWN |
| T24 | Counter reset do node restart | Không tính delta xuyên reset |
| T25 | Compaction pending nhẹ, ổn định | Không tự FAIL nếu policy cho phép |
| T26 | Compaction backlog liên tục tăng/disk chật | FAIL/HOLD |
| T27 | Hints replay còn chạy sau node UN | Recovery gate theo policy |
| T28 | Streaming dự kiến chưa hoàn tất | Phase-aware HOLD |
| T29 | Driver retry attempts tăng mạnh | HOLD/FAIL theo budget |
| T30 | Hai workflows cùng change ID | Không chạy đôi; lock/lease |
| T31 | Một probe query bị timeout | Bounded retry, tri-state decision |
| T32 | CqlSession mới cho từng request | Test phát hiện connection storm |
| T33 | Output `nodetool` format không nhận diện | UNKNOWN |
| T34 | No expected node inventory provided | UNKNOWN/stop |
| T35 | Rolling node B khi A chưa recovered | Gate không cho tiếp tục |
| T36 | RF/CL của app không đạt sau node down | FAIL |
| T37 | Schema và state pass nhưng API mapper lỗi | Business probe FAIL |
| T38 | Query test full-table scan bị đề nghị | Guardrail chặn, yêu cầu bounded |
| T39 | Credentials/secret xuất hiện trong logs | Security gate FAIL |
| T40 | Change completed nhưng chưa đủ observation window | UNKNOWN/HOLD, không tự PASS |

### 29.1. Phân lớp kiểm thử

- **Unit:** gate evaluation/tri-state, inventory match, parser failures, threshold window, stale metric, counter reset.
- **Integration một node:** prepared CQL, auth/TLS, probe table TTL, read-back, Java driver code.
- **Cluster nhiều nodes:** RF/CL, one-node downtime, gossip/schema state, after-restart recovery.
- **Multi-DC lab:** localDC routing, failover, inter-DC visibility, auth/trust per region.
- **Load/fault lab:** p95/p99 behavior, retry storm, compaction backlog, cache warmup, capacity headroom.

Một test Cassandra RF=1 trong Testcontainers không xác minh RF=3/LOCAL_QUORUM behavior hay rolling maintenance trong một DC thật.

### 29.2. Fixture cleanup không được gây sự cố

- Dùng TTL để hạn chế bảng probe tăng vô hạn, nhưng theo dõi tombstones/compaction.
- Không `TRUNCATE` sau mỗi lần test, vì có thể ảnh hưởng probes khác.
- Không tạo một table/keyspace mới cho mỗi health check.
- Dùng run IDs cố định cho retry, random cho **run mới**.
- Đừng seed fixture production bằng dữ liệu khách hàng hoặc secrets.
- Đảm bảo test process đóng session đúng lúc, không reconnect storm.

## 30. Mẫu báo cáo sức khỏe trước/sau bảo trì

### 30.1. Dữ liệu phải đủ để đối chiếu

Một bản báo cáo có thể đặt cạnh nhau:

| Nhóm kiểm | Preflight | Expected postflight | Observed postflight | Gate |
|---|---|---|---|---|
| Node inventory dc1 | 3 expected, 3 UN | 3 UN | 3 UN | PASS |
| Node inventory dc2 | 3 expected, 3 UN | 3 UN | 3 UN | PASS |
| Schema agreement | Có | Có | Có | PASS |
| Java new connection/TLS | Có | Có | Có | PASS |
| CQL read probe dc1 | Đúng expected | Đúng | Đúng | PASS |
| CQL write/read dc1 | Đúng expected | Đúng | Đúng | PASS |
| CQL read/write dc2 | Đúng expected | Đúng | Timeout | FAIL |
| Representative business query | p99=90 ms | ≤ SLO | p99=140 ms | Theo SLO |
| Compaction backlog | 4 pending | Không drift | 11 và tăng | HOLD |
| Disk headroom | 35% free | ≥ policy | 31% free | Theo policy |
| Required observation | Đủ 15 phút | Đủ 15 phút | 5 phút | UNKNOWN |

**Các số và trạng thái trong bảng đều giả định.** Nếu `dc2` write/read FAIL hoặc window chưa đủ, **overall không thể PASS** dù phần lớn hàng khác đạt.

### 30.2. Schema báo cáo dạng YAML

~~~yaml
# Mẫu thông tin controller xuất, không phải file cần tạo ở STEP 4.
change_id: MAINT-2026-041
run_id: "7c0a0a4f-2f5a-4f6c-8c0f-b70c0a071111"
stage: postflight
timestamp_utc: "2026-11-21T10:00:00Z"
cluster_id: "approved-logical-cluster-name"
expected_topology:
  dc1: 3
  dc2: 3
checks:
  - id: topology_dc1
    status: PASS
    evidence: "Expected host IDs/racks in UN"
  - id: topology_dc2
    status: PASS
    evidence: "Expected host IDs/racks in UN"
  - id: schema
    status: PASS
    evidence: "Metadata and schema gates passed"
  - id: canary_write_read_dc2
    status: FAIL
    error_family: "READ_TIMEOUT"
    consistency: "LOCAL_QUORUM"
  - id: performance_observation_window
    status: UNKNOWN
    reason: "Only 5 of required 15 minutes"
overall: FAIL
decision: "STOP_NEXT_STEP_AND_ESCALATE"
owner: "operations-oncall"
~~~

- `PASS` chỉ có khi gate đã thật sự quan sát và đạt.
- `FAIL` không bị một check khác PASS ghi đè.
- `UNKNOWN` đòi bổ sung evidence/human review; không tự đổi thành PASS.
- `run_id` định danh một lần kiểm, còn `change_id` có thể bao nhiều lần chạy trước/trong/sau.
- Metrics và source links phải có timestamps, units và sampling windows.
- Báo cáo không chứa secrets/private keys/customer bind values.

### 30.3. Vì sao báo cáo cần hai loại thời gian?

- **UTC wall-clock** để tương quan logs/sự kiện giữa nhiều nodes/regions, kèm kiểm clock drift.
- **Monotonic duration** như Java `System.nanoTime()` để đo elapsed latency trong một process.

Đừng trừ wall timestamps của hai máy rồi gọi đó là request latency chính xác khi đồng hồ chưa đồng bộ. Không dựng p99 bằng trung bình các p99 lẻ từ nodes/windows.

### 30.4. Không biến `PASS` cũ thành giấy phép vô hạn

Một health report PASS lúc 09:00 không bảo đảm cluster còn healthy lúc 11:00 nếu workload hoặc topology đã đổi. Controller nên:

- Có `valid_until`/time-to-live của snapshot/report.
- Phải đo lại trước **bước bảo trì có rủi ro**.
- Invalidate gate nếu có node change hoặc alert mới.
- Gắn cluster/version/change ID vào evidence.
- Chặn việc tái sử dụng báo cáo của DC/cluster khác.

## 31. Unit test mô hình gate: fail closed khi dữ liệu thiếu

### 31.1. Bộ tổng hợp gate đơn giản bằng Java

~~~java
package example.cassandra.ops;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class GatePolicy {

    public enum Status { PASS, FAIL, UNKNOWN }

    public record Check(String id, Status status) {}

    public static Status aggregate(
            Set<String> requiredIds, List<Check> observations) {

        Map<String, Status> received = new HashMap<>();

        for (Check check : observations) {
            if (check == null
                    || check.id() == null
                    || check.status() == null
                    || !requiredIds.contains(check.id())) {
                return Status.UNKNOWN;
            }

            if (received.putIfAbsent(check.id(), check.status())
                    != null) {
                // Duplicate source/check ID: đừng âm thầm lấy sample cuối.
                return Status.UNKNOWN;
            }
        }

        if (received.values().contains(Status.FAIL)) {
            return Status.FAIL;
        }
        if (!received.keySet().containsAll(requiredIds)) {
            return Status.UNKNOWN;
        }
        if (received.values().contains(Status.UNKNOWN)) {
            return Status.UNKNOWN;
        }
        return Status.PASS;
    }
}
~~~

Ví dụ dùng Java records, phù hợp Java 16+; thay POJO nếu JDK thực tế thấp hơn. Một production controller còn phải kiểm **freshness, sample windows, source signatures, exceptions, hysteresis, scopes/DC**. Đây chỉ là logic tổng hợp, không phải health system hoàn chỉnh.

### 31.2. Test các cases quan trọng

~~~java
package example.cassandra.ops;

import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static example.cassandra.ops.GatePolicy.*;

class GatePolicyTest {

    private final Set<String> required =
        Set.of("topology", "schema", "cql");

    @Test
    void allRequiredPass() {
        assertEquals(Status.PASS, aggregate(required, List.of(
            new Check("topology", Status.PASS),
            new Check("schema", Status.PASS),
            new Check("cql", Status.PASS)
        )));
    }

    @Test
    void explicitFailDominatesPass() {
        assertEquals(Status.FAIL, aggregate(required, List.of(
            new Check("topology", Status.PASS),
            new Check("schema", Status.PASS),
            new Check("cql", Status.FAIL)
        )));
    }

    @Test
    void missingEvidenceIsNotPass() {
        assertEquals(Status.UNKNOWN, aggregate(required, List.of(
            new Check("topology", Status.PASS),
            new Check("schema", Status.PASS)
        )));
    }

    @Test
    void duplicateCheckIsNotSilentlyAccepted() {
        assertEquals(Status.UNKNOWN, aggregate(required, List.of(
            new Check("topology", Status.PASS),
            new Check("topology", Status.PASS),
            new Check("schema", Status.PASS),
            new Check("cql", Status.PASS)
        )));
    }
}
~~~

Trong production, nếu có một FAIL nhưng đồng thời duplicate/unrecognized observation, logic trên có thể trả UNKNOWN trước khi xét FAIL. Chính sách có thể ưu tiên FAIL trong mọi hoàn cảnh; điều quan trọng là cả **UNKNOWN và FAIL phải chặn maintenance** khi yêu cầu fail-closed. Tổ chức nên định nghĩa ưu tiên và kiểm thử rõ.

### 31.3. Parser `nodetool` phải có version-contract tests

Nếu controller parse text output, xây fixtures cho:

- 3 nodes `UN` và expected inventory khớp.
- Node `DN`, `UJ`, `UL`, node thiếu hoàn toàn.
- Nhiều DC/rack, tên DC chứa ký tự đặc biệt nếu hỗ trợ.
- Header/spacing thay đổi sau upgrade.
- Empty/partial output hoặc timeout JMX.
- Schema version mismatch.
- Node replacement cùng IP nhưng host ID khác.
- Output có warning hoặc localization khác.

Không dùng pattern `line.startsWith("UN")` đơn độc làm điều kiện an toàn. Khi parser không nhận dạng → UNKNOWN.

## 32. Câu hỏi luyện tập có đáp án

### Câu 1 — Trạng thái UN

Sáu node đều `UN`. Có thể kết luận client Java đọc ghi và p99 khỏe không?

**Đáp án:** Không. `UN` phản ánh ring/gossip view; vẫn cần native TLS/auth, CQL read/write, replica CL, queues/compaction và SLO.

### Câu 2 — Node mất khỏi inventory

Expected sáu nodes, `nodetool status` chỉ hiển thị năm dòng `UN` và không có `DN`. Có PASS không?

**Đáp án:** Không. Thiếu expected node; đối chiếu inventory/host IDs/observer views và HOLD.

### Câu 3 — JMX vs native CQL

`nodetool info` trả kết quả nhưng Java báo TLS handshake failure. Điều này mâu thuẫn không?

**Đáp án:** Không. JMX và native CQL là hai đường kết nối độc lập về network/TLS/auth.

### Câu 4 — RF/CL

DC có RF=3, app dùng `LOCAL_QUORUM`. Một replica down, hai replica còn sống. Có đủ điều kiện logic để một request thành công không?

**Đáp án:** Thường có thể, nếu hai replica đó phù hợp replica set và kịp phản hồi; nhưng **không còn headroom an toàn** để restart thêm một replica.

### Câu 5 — Missing metrics

CQL probe PASS nhưng exporter GC metrics unreachable. Controller nên trả gì?

**Đáp án:** UNKNOWN (hoặc FAIL nếu policy coi mất observability là vi phạm) và chặn bước bảo trì tiếp; không coi missing là 0 lỗi.

### Câu 6 — Read only

Read reference fixture thành công. Có thể khẳng định write/commitlog path cũng khỏe không?

**Đáp án:** Không. Cần write/read canary trong table được phép hoặc bằng chứng write khác tương đương.

### Câu 7 — Write timeout

`INSERT` probe timeout nhưng read-back thấy expected value. Có thể kết luận attempt ban đầu “rollback” không?

**Đáp án:** Không. Timeout là uncertain outcome; đối soát bằng key/CL, giữ gate theo policy và không tự gắn success cho mọi replica.

### Câu 8 — Probe không idempotent

Một retry tạo `run_id` mới và expected khác. Có rủi ro gì?

**Đáp án:** Tăng số rows, khó phân biệt attempts, dễ che outcome/mismatch. Dùng run ID và expected value ổn định trong cùng run.

### Câu 9 — TTL

Reference row seed từ hôm qua dùng TTL một giờ, hôm nay SELECT trả 0 row. Có chắc Cassandra hỏng không?

**Đáp án:** Không. Fixture đã hết hạn. Dùng reference data có retention phù hợp và phân biệt expiry với read failure.

### Câu 10 — Compaction backlog

`compactionstats` pending bằng 4 trong cluster bình thường. Có tự FAIL không?

**Đáp án:** Không nhất thiết. Cần nhìn xu hướng, workload, disk headroom và SLO; compaction là tác vụ nền bình thường.

### Câu 11 — Netstats

`nodetool netstats` trống. Có thể kết luận native CQL traffic bằng 0 không?

**Đáp án:** Không. `netstats` chủ yếu phản ánh SSTable streaming.

### Câu 12 — Schema agreement

`nodetool describecluster` hiển thị schema versions phù hợp. Có thể bỏ prepared Java query test không?

**Đáp án:** Không. Schema agreement không chứng minh driver codecs, role grants hoặc application queries tương thích.

### Câu 13 — Hạ CL để pass

Production dùng LOCAL_QUORUM; probe dùng ONE và PASS. Có đủ xác minh production path không?

**Đáp án:** Không. Probe cần CL tương thích workload/consistency requirement; ONE có thể che vấn đề quorum.

### Câu 14 — P99

Ba nodes báo p99 50, 70, 500 ms. Có thể lấy trung bình và gọi đó là cluster p99 không?

**Đáp án:** Không. Cần histogram/raw samples với aggregation hợp lệ; đồng thời xem worst-node.

### Câu 15 — Success-only bias

Sau bảo trì, p99 các requests thành công giảm nhưng timeout rate tăng 5%. Kết quả tốt hơn không?

**Đáp án:** Không mặc định. SLO phải xét cả latency và error; slow requests có thể bị loại do timeout.

### Câu 16 — Mỗi node một health check

Một probe key `run_id` thành công có chứng minh tất cả replica trong ring khỏe không?

**Đáp án:** Không. Một partition chỉ có replica set cụ thể; dùng inventory + các probe keys/DC có coverage plan.

### Câu 17 — Rolling

Node A đã `UN` nhưng p99 còn vượt SLO, compaction pending tăng. Có nên restart node B ngay?

**Đáp án:** Không. HOLD; đợi/khôi phục resource và CQL/SLO gates trước khi tiếp tục.

### Câu 18 — Cross DC

Probe LOCAL_QUORUM ở dc1 PASS. Có chắc client ở dc2 đọc được cùng dữ liệu không?

**Đáp án:** Không. Cần kiểm dc2 local routing/RF/CL và visibility/convergence riêng.

### Câu 19 — Read vs write role

Read canary thành công nhưng write bị Unauthorized. Là lỗi replica không?

**Đáp án:** Có thể là role thiếu MODIFY. Phân loại authz trước khi điều tra replication; role probe cần quyền tối thiểu đúng table.

### Câu 20 — Test data

Có nên INSERT health marker vào bảng events production để kiểm write path không?

**Đáp án:** Không nếu không có thiết kế/approval rõ. Probe riêng tránh triggers, CDC và tác động người dùng.

### Câu 21 — Baseline

Preflight p99 đo giờ thấp điểm, postflight giờ cao điểm. Có thể quy mọi khác biệt cho maintenance không?

**Đáp án:** Không. Phải kiểm workload mix/QPS/sample window, đồng thời dùng absolute SLO và tolerance có phương pháp.

### Câu 22 — Report reuse

Report PASS hôm qua có thể dùng cho node B restart hôm nay không?

**Đáp án:** Không mặc định. Report có validity window và phải invalidate khi topology/conditions đổi.

### Câu 23 — Parser

Sau Cassandra upgrade, output `nodetool status` thay cột làm parser lỗi. Kết quả nào an toàn?

**Đáp án:** UNKNOWN, chặn tự động; sửa parser và test fixtures theo version.

### Câu 24 — Không đầy đủ observation window

Postflight yêu cầu 15 phút SLO nhưng mới có 3 phút samples. Có PASS không?

**Đáp án:** Không. UNKNOWN/HOLD cho tới khi đủ bằng chứng; không gắn PASS từ một vài request.

### Câu 25 — Maintenance rollback

Schema/data-format upgrade không backward-compatible. Script có nên tự downgrade khi fail gate không?

**Đáp án:** Không. Rollback có thể không an toàn; dùng recovery/forward-fix đã phê duyệt, human escalation và bằng chứng.

### Câu 26 — Native TLS rotation

Existing Java pool vẫn hoạt động sau thay CA. Có đủ bằng chứng clients mới sẽ kết nối không?

**Đáp án:** Không. Cần new connections với đúng truststore/hostname verification, local DC và role.

### Câu 27 — Backlog

Sau node restart, streaming kết thúc nhưng hints backlog còn tăng. Có thể đóng change khi API probe PASS không?

**Đáp án:** Chưa đủ. Kiểm recovery envelope, trends và workload; HOLD/owner signoff theo policy.

### Câu 28 — Query representative

Probe table rất nhỏ PASS. Business `SELECT` trên partition tombstone-heavy timeout. Có thể coi cluster khỏe không?

**Đáp án:** Không cho workload đó. Thêm representative business query bounded, xem data model/tombstones/compaction.

### Câu 29 — Snapshot freshness

Báo cáo disk free 30% từ 6 giờ trước nhưng node đang chạy repair. Có đủ để cho restart không?

**Đáp án:** Không. Cần metric mới, đúng node/device, và safety headroom tại thời điểm quyết định.

### Câu 30 — PASS cuối cùng

Điều kiện tối thiểu để kết thúc bảo trì là gì?

**Đáp án:** Expected topology/replicas, CQL native auth/read/write và business correctness, error/p95/p99/resource headroom, recovery/backlog theo policy, observation window và evidence đều đạt; thiếu bất kỳ hard gate nào thì không tự PASS.

## 33. Checklist kiểm tra trước/sau và bàn giao

### 33.1. Chuẩn bị trước cửa sổ

~~~text
[ ] Có change ID, owner, scope và approval.
[ ] Có expected inventory theo node host ID, DC/rack, token/phase.
[ ] Có Cassandra/JDK/driver versions, schema/migration plan.
[ ] Đã định nghĩa RF/CL cho từng workload và DC.
[ ] Đã xác nhận repair/backup/streaming/backfill đang diễn ra.
[ ] Có rollback/recovery SOP và giới hạn thao tác tự động.
[ ] Có baseline workload/latency/error và resource headroom.
[ ] Có ngưỡng SLO, hard/soft gates, observation window.
[ ] Có keyspace/table probe tạo trước, role tối thiểu và TTL policy.
[ ] Có stable reference row hoặc fixture được phép và không hết hạn.
[ ] Không có secret/password/raw customer data trong script/log.
[ ] Controller có lock/lease và rate limits, budgets, deadlines.
~~~

### 33.2. Preflight gate

~~~text
[ ] nodetool/JMX đọc được từ observers được phép.
[ ] Expected node count, host IDs, DC/rack, state khớp.
[ ] Không có unexpected DN/Joining/Leaving/Moving.
[ ] Schema agreement và driver metadata/query compatibility đạt.
[ ] RF/CL đủ, không có maintenance khác làm mất dự phòng.
[ ] Native TLS/auth mới kết nối được từ app network/regions.
[ ] Read-only fixture query và expected result đúng.
[ ] Write/read probe trên ops_health pass nếu manifest yêu cầu.
[ ] Representative business queries pass với bounded inputs.
[ ] p95/p99, timeout/error và attempts/s đạt policy.
[ ] Worst-node CPU/GC/heap/disk/network/headroom đạt.
[ ] Hints, streaming, compaction, repair không vi phạm gate.
[ ] Mọi check có timestamp/source và không stale.
[ ] Overall PASS; FAIL/UNKNOWN nghĩa dừng và điều tra.
~~~

### 33.3. Trong rolling maintenance

~~~text
[ ] Mỗi node có expected phase và safety boundary theo RF/CL.
[ ] Không bắt đầu bước kế khi gate node trước chưa PASS.
[ ] Quan sát topology từ nhiều seeds, không dựa 1 output text.
[ ] Kiểm CQL new connection, app queries và auth/permission.
[ ] Kiểm latency/errors, retries, queues và disk/GC.
[ ] Dừng nếu có unexpected DN, unavailable, OOM, disk pressure.
[ ] Probe rate/concurrency không tạo storm khi cluster degraded.
[ ] Có người chịu trách nhiệm khi cần rollback/forward-fix.
[ ] Không tự sửa system tables, CL, grants hoặc schema ngoài plan.
~~~

### 33.4. Postflight và đóng change

~~~text
[ ] Actual topology/DC/rack/token đúng expected manifest.
[ ] Nodes đạt trạng thái đích, không còn phase bất ngờ.
[ ] Cassandra/schema/driver/JDK versions theo kế hoạch.
[ ] App new connections, TLS/auth/permissions pass.
[ ] Read & write/readback probes pass ở mọi DC bắt buộc.
[ ] Representative business query, mapper và pagination pass.
[ ] RF/CL, data correctness và multi-DC policy đáp ứng.
[ ] p95/p99, timeout/error, retries trong absolute SLO/budget.
[ ] Node resource/compaction/hints/streaming có trend ổn.
[ ] Observation window đủ dài và sample count đáng tin.
[ ] PASS/FAIL/UNKNOWN, reasons và evidence được lưu.
[ ] Có owner signoff trước khi đóng change.
[ ] Không áp dụng Step 6 Content QA trong bước viết bài này.
~~~

## 34. Những anti-pattern nên kiểm bằng code review

| Anti-pattern | Vì sao có thể gây quyết định sai? | Cách sửa |
|---|---|---|
| `nodetool status` exit 0 = healthy | Chỉ chứng minh lệnh chạy | Parse inventory/state |
| Grep không thấy DN = PASS | Node có thể thiếu khỏi output | So host IDs/nodes expected |
| Chỉ chạy một probe key | Không phủ token/DC/rack | Topology gate + coverage |
| Read-only PASS = write khỏe | Không đụng commitlog/write quorum | Bổ sung write/readback |
| CL ONE thay LOCAL_QUORUM | Che quorum failure | CL theo workload thật |
| Smoke bằng role admin | Che RBAC lỗi của app | Role representative tối thiểu |
| cqlsh trong node thay Java pod | Khác network/TLS/driver | Probe từ app path |
| Dùng existing pool khi rotate cert | Không kiểm reconnect/trust mới | New connection canary |
| Trả `healthy=true` khi exporter timeout | Mất evidence | UNKNOWN, fail closed |
| Gán metric missing = 0 | False healthy | Freshness/source gate |
| Thấy 0 compactions mới PASS | Background compaction bình thường | Trend, disk, SLO |
| Đợi 30 giây cố định rồi PASS | Recovery phụ thuộc tải | Condition-based polling |
| Chạy `repair` như health check | Là mutation/storage-heavy operation | Read-only observability |
| Test bằng full-table scan | Tự gây tài nguyên cao | Query bounded/full partition key |
| Write vào bảng user | Trigger/CDC/side effects | Probe table riêng |
| `TRUNCATE` probe table mỗi lần | Gián đoạn các probe khác | TTL/retention strategy |
| Run UUID mới mỗi retry | Tạo nhiều rows/khó đối soát | Stable ID trong một run |
| Session mới mỗi probe request | TLS/connection storm | Reuse CqlSession |
| Không có QPS cap cho checker | Đè cluster khi degraded | Bounded concurrency/rate |
| Chỉ xem p99 successes | Che timeout failures | Error budget + p99 |
| Average p99 của nodes | Percentile không tuyến tính | Histogram/raw samples |
| So trước/sau khác traffic mix | False regression/fix | So absolute SLO và workload |
| Không kiểm expected topology delta | Topology change bị đánh sai | Change manifest |
| Tự downgrade sau incompatible schema | Có thể mất dữ liệu | Approved recovery SOP |
| Dùng stale PASS làm giấy phép | Health có tính thời điểm | Validity TTL/recheck |
| Log credentials/PKI private key | Rò secret | Redaction/least privilege |

## 35. Tổng kết

Một quy trình **kiểm tra sức khỏe trước/sau bảo trì bằng trạng thái và truy vấn** có chất lượng cần đạt những nguyên tắc sau:

1. **Không đồng nhất Up/Normal với healthy.** `nodetool status` là một nguồn topology/gossip; native CQL, replica CL và p99 phải được kiểm riêng.
2. **So expected inventory**, không chỉ đếm node `UN` hiện diện. Host ID, DC/rack, topology phase và planned changes đều quan trọng.
3. **Đọc tính sẵn sàng qua RF/CL**: đủ quorum cho một request chưa có nghĩa an toàn để restart thêm node hoặc failover.
4. **Preflight và postflight là hai bộ điều kiện có phạm vi/time window**; trạng thái khỏe hôm qua không thay kết quả tại thời điểm maintenance.
5. **Probe read và write/readback bổ sung cho nhau**. Probe phải nhỏ, typed, có role tối thiểu và dùng table riêng; kết quả luôn có phạm vi.
6. **Prepared Java Driver test phải đi qua đúng network/TLS/auth/local DC** và query theo partition key; không dùng cqlsh admin trên node làm đại diện duy nhất.
7. **Kiểm schema/migration và app codec**, đặc biệt với rolling upgrade; schema agreement không đảm bảo mọi prepared query chạy được.
8. **Resource và tail latency là gate độc lập**, gồm CPU/GC/memory/disk/compaction/hints/streaming/retries và cả application API SLO.
9. **Tri-state PASS/FAIL/UNKNOWN bảo vệ automation**; thiếu metric, parser hỏng hoặc window chưa đủ không được biến thành PASS.
10. **Rolling phải condition-based**, gate sau từng node; không tiếp tục theo thời gian chờ cố định hoặc khi vẫn còn node chưa hồi phục.
11. **Lưu evidence có thể kiểm toán** theo change ID, run UUID, CL, DC, query template, UTC time, duration, metric sources và action decisions.
12. **Không tự biến health check thành maintenance operation**: không chạy repair/compact/cleanup, sửa CL/schema, tắt TLS hoặc quyền khi chưa có SOP.

Câu hỏi cốt lõi trước khi cho phép bước bảo trì kế tiếp không phải **“Mọi node có báo UN không?”**, mà là: **“Cluster hiện ở đúng topology dự kiến chưa, liệu ứng dụng Java có thể đọc và ghi đúng theo khóa phân vùng và mức nhất quán yêu cầu, tail latency/tài nguyên có đủ headroom, những công việc phục hồi có ổn định, và mọi kết luận đều dựa trên bằng chứng mới, đáng tin cậy hay không?”**

Chỉ khi các điều kiện bắt buộc thực sự đạt, controller mới có cơ sở xuất **PASS**. Nếu có vi phạm, xuất **FAIL**; nếu còn thiếu bằng chứng, xuất **UNKNOWN** và giữ an toàn cho cluster.



