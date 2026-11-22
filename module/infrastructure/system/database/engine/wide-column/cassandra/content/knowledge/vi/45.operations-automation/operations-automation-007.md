# Triển khai lần lượt, giới hạn đồng thời và điều kiện dừng trong Apache Cassandra

> **Chương:** Tự động hóa vận hành  
> **Phạm vi:** Điều phối thay đổi có kiểm soát trên Apache Cassandra: rolling restart, thay đổi cấu hình/phiên bản, triển khai ứng dụng Java Driver, schema migration và các tác vụ bảo trì như repair/streaming. Bài tập trung vào **thứ tự triển khai (rollout order)**, **giới hạn tác vụ đồng thời (concurrency budget)**, **cổng kiểm tra giữa các đợt (health gates)** và **điều kiện tạm dừng/dừng khẩn cấp**. Ví dụ là thiết kế học thuật; không thực thi thao tác restart/repair/replace trên production nếu không có quyền, kế hoạch và quy trình rollback.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao Cassandra cần triển khai **từng đợt** thay vì cập nhật mọi node đồng thời.
2. Phân biệt rolling restart, rolling binary upgrade, rolling configuration change, schema migration, rolling app deployment và node replacement.
3. Suy luận giới hạn concurrency từ **replication factor (RF)**, **consistency level (CL)**, **natural replica set**, trạng thái node hiện tại và phạm vi datacenter/rack.
4. Thiết kế thứ tự xử lý tránh làm hai replicas của cùng hot partition đồng thời không sẵn sàng.
5. Xác định điều kiện **GO/HOLD/ABORT/ROLLBACK**, không chỉ dựa vào thời gian chờ cố định.
6. Viết một rollout manifest chứa topology, change fingerprint, canary, batch size, health gates, deadlines, guardrails và người phê duyệt.
7. Phân biệt các mốc **process started**, **gossip UP/Normal**, **native transport ready**, **driver routing healthy**, **data/CL ready** và **performance recovered**.
8. Đặt giới hạn đồng thời riêng cho restarts, repair/streaming, compaction-heavy maintenance, schema DDL và ứng dụng Java.
9. Sử dụng `nodetool status`, `describecluster`, `netstats`, `tpstats`, `compactionstats` và CQL probes để xây dựng bước preflight và post-change gate.
10. Thiết kế controller tự động **fail closed**, có lock/lease, idempotency, checkpoint, deadline, retry có giới hạn và resume an toàn sau crash.
11. Hiểu vì sao PodDisruptionBudget/StatefulSet readiness hoặc operator “Task Completed” **chưa đủ** chứng minh CL và dữ liệu nghiệp vụ ổn.
12. Viết Java Driver 4.x readiness probe ở CL phù hợp và phân biệt lỗi schema, connection, replica/CL, timeout và data mismatch.
13. Vẽ kịch bản RF3/LOCAL_QUORUM, multi-DC, quorum headroom, một node đã DOWN và các trường hợp phải hạ concurrency về 0.
14. Báo cáo rollout với timestamp, attempt IDs, quan sát trước/sau, kết quả gate, node coverage và unresolved risks.

**Trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`**, token và partition key xác định natural replicas, keyspace quyết định replication strategy và RF, còn CL quyết định số phản hồi cần thiết khi đọc/ghi. Vì vậy tự động hóa vận hành Cassandra phải **bảo vệ khả năng phục vụ ở các replica set**, không chỉ làm từng máy “xanh” trên dashboard. Những ví dụ CQL/Java được dùng để xác minh chính xác **dữ liệu và hành vi của ứng dụng** sau thay đổi.

## 2. “Triển khai lần lượt” là gì?

Rolling deployment là áp dụng một thay đổi cho **một đơn vị nhỏ hoặc một đợt giới hạn**, kiểm tra kết quả, rồi mới mở rộng đến đơn vị kế tiếp:

~~~text
                 Approved change request
                           |
                      PREFLIGHT
                           |
                      CANARY NODE
                           |
                Health + data + SLO gates
                   /            \\
                PASS           FAIL
                 |               |
             WAVE 1             HOLD
                 |               |
           Re-check gates   rollback/escalate
                 |
             WAVE 2
                 |
                ...
                 |
          POST-ROLLOUT SOAK
                 |
              REPORT
~~~

Trong Cassandra, một wave có thể là **một node Cassandra**, **một rack/zone với số node rất nhỏ được phê duyệt**, **một tập application pods** hoặc **một partitioned maintenance task**. Chúng không có cùng concurrency/safety rules. Đừng tự suy luận “batch size 2” an toàn cho mọi loại thao tác.

### 2.1. Tại sao không restart cả RF3 một lúc?

Giả sử keyspace có RF3, natural replicas của một partition là A, B, C, đọc/ghi ở `LOCAL_QUORUM` cần **2/3 replicas** đáp ứng trong cùng DC.

~~~text
Before:
  A UP    B UP    C UP
  quorum 2/3 possible

Restart A only:
  A DOWN  B UP    C UP
  quorum 2/3 still possible (nhưng không dư headroom)

Restart B while A not recovered:
  A DOWN  B DOWN  C UP
  quorum 2/3 NOT possible
~~~

Từ ví dụ suy ra: nếu có **một replica đã không sẵn sàng**, batch tiếp theo không được làm mất thêm replica của cùng key. Không phải chỉ vì cluster có 100 nodes là có thể restart 10 nodes bất kỳ: một hot partition vẫn có thể có đúng ba natural replicas, và hai trong đó có thể nằm trong 10 nodes vừa chọn.

### 2.2. Đổi trạng thái tại một node khác với thay đổi topology

| Hoạt động | Thay đổi chính | Tại sao cần wave riêng? |
|---|---|---|
| Rolling restart Cassandra process | Một node tạm không phục vụ; token/host ID thường giữ | Giữ quorum, cache warm-up/commitlog replay |
| Rolling binary upgrade | Binary/feature compatibility theo phiên bản | Mixed-version restrictions, SSTable/protocol/storage format |
| Rolling config change | Thông số JVM/Cassandra/driver, có thể yêu cầu restart | Restart-safe vs runtime-dynamic, rollback |
| Schema migration | DDL lan tới nhiều nodes; không gắn riêng một replica | Single DDL owner, schema agreement, application compatibility |
| Rolling Java application | Thay code/driver config, không nhất thiết restart Cassandra | Client pool/routing, queries/CL, traffic shift |
| Bootstrap/replace/decommission | Token ownership/natural replicas thay đổi | Streaming, hints/repair, không giống restart |
| Repair/streaming task | Disk/network/CPU nặng, không nhất thiết làm node DOWN | Resource contention, data coverage, overlapping token ranges |

**Tránh nhầm:** `nodetool decommission`/`removenode`/node replace **không phải** cách rolling restart một node thông thường. Những lệnh đó thay topology/data ownership, cần runbook riêng.

### 2.3. “Một node mỗi lần” là mặc định an toàn, không phải chứng minh tuyệt đối

Một node tại một thời điểm vẫn có thể làm dịch vụ lỗi khi:

- Một trong các replicas khác đã DOWN/sluggish, khiến quorum mất ngay khi node đang được restart.
- App sử dụng `ALL`/`EACH_QUORUM` hoặc CL không còn đủ headroom cho một node down.
- Keyspace RF1 hoặc RF2 nhưng contract cần quorum/full replica.
- Node sắp restart là coordinator/replica của hot partitions đang saturating, không còn capacity để fail over.
- Cross-DC network partition hoặc driver chỉ kết nối một endpoint.
- Compaction/repair/streaming từ wave trước còn chiếm disk/network.

**Nguyên tắc:** Trước *mỗi* wave phải đánh giá **current observed state**, không lấy kết quả preflight lúc bắt đầu làm bảo đảm vĩnh viễn.

## 3. Ba giới hạn phải áp dụng đồng thời

Mỗi bước automation chịu ba nhóm giới hạn độc lập:

1. **Replica availability budget:** Có thể tạm mất bao nhiêu natural replicas trên mọi token range để vẫn đạt CL/contract?
2. **Resource budget:** Có thể tạo bao nhiêu công việc cùng lúc trước khi disk, network, CPU, GC, streaming/repair/compaction trở thành bottleneck?
3. **Business error budget:** Một wave có thể làm SLO p95/p99, error rate, timeout, unknown outcomes hoặc backlog xấu đến đâu trước khi dừng?

~~~text
                      Proposed wave W
                             |
            +----------------+----------------+
            |                |                |
          REPLICA          RESOURCE          BUSINESS
          BUDGET           BUDGET            BUDGET
            |                |                |
         PASS?             PASS?             PASS?
            \\                |               /
             \\               |              /
              +--------------+-------------+
                             |
                        ALL PASS?
                       /         \\
                    YES           NO
                     |             |
                  EXECUTE         HOLD/ABORT
~~~

**Không được cộng các budgets thành một số trung bình.** Một wave dùng CPU ít nhưng làm mất quorum vẫn phải bị chặn; một wave giữ quorum nhưng khiến commitlog disk full cũng phải bị chặn.

### 3.1. Budget không giống số nodes tối đa

Ví dụ RF3 + `LOCAL_QUORUM` cho phép **một replica không sẵn sàng trên mỗi natural replica set** nếu tất cả replicas còn lại khỏe. Cluster có hàng trăm token ranges và nhiều keyspaces; một node có thể sở hữu rất nhiều token ranges. Hai nodes khác rack **vẫn có thể cùng là natural replicas** của một số partitions, phụ thuộc token placement/vnodes/rack/DC/routing.

Vì vậy quy tắc “mỗi rack một node cùng lúc” **không tự chứng minh an toàn**. Concurrency phải được ràng buộc bởi replica-set intersection, cùng với tải và failure domains.

### 3.2. Có nhiều keyspaces với RF/CL khác nhau

~~~text
Keyspace orders:     RF3 in dc1, LOCAL_QUORUM
Keyspace telemetry:  RF2 in dc1, LOCAL_ONE
Keyspace audit:      RF3 in dc1, ALL

Wave candidate: restart node A
~~~

Nếu `audit` sử dụng `ALL` và dữ liệu trên node A nằm trong natural replica set của partitions đang cần phục vụ, một node down có thể làm các truy vấn đó không đạt CL. Dù `orders` còn quorum, wave vẫn phải **HOLD** nếu hợp đồng audit yêu cầu tiếp tục hoạt động. Muốn chấp nhận planned downtime cho riêng audit phải có **approval và traffic quiescence** rõ, không âm thầm hạ CL.

### 3.3. Tình trạng thực tế có thể thấp hơn RF trên giấy

`RF=3` nói replication target, không chứng minh mọi replica đã đầy đủ dữ liệu và đang đáp ứng deadline. Node DN, đang bootstrap/rebuild, disk quá tải, chưa nhận hints/repair, hoặc driver không route tới nó đều có thể làm effective budget thấp hơn.

**Kế hoạch chỉ được triển khai khi observed capacity và data/probe chứng minh an toàn.**

## 4. Mô hình trạng thái cho một node/wave

### 4.1. Đừng coi `UN` là điều kiện duy nhất

~~~text
PENDING
   |
PREFLIGHT_OK
   |
INTENT_RECORDED / LEASED
   |
DRAINING (if runbook requires)
   |
PROCESS_RESTARTING
   |
PROCESS_STARTED
   |
GOSSIP_UP_NORMAL
   |
NATIVE_TRANSPORT_READY
   |
SCHEMA_AND_DRIVER_READY
   |
DATA_CL_PROBES_PASS
   |
PERFORMANCE_AND_BACKGROUND_WORK_STABLE
   |
WAVE_VERIFIED
   |
COMMITTED -> NEXT WAVE
~~~

Một wave chỉ tiến tới `COMMITTED` khi **mọi gate áp dụng cho change type** đều PASS. Nếu một gate không có telemetry, coi là **UNKNOWN/HOLD**, không đổi thành PASS vì không thu được số liệu.

### 4.2. Năm loại readiness hay bị gộp nhầm

| Trạng thái | Có thể xác minh bằng | Không bảo đảm |
|---|---|---|
| Process started | PID/container/pod RUNNING, log JVM boot | CQL trả được, schema/data đúng |
| Gossip `UN` | `nodetool status` từ nhiều vantage points | Driver đã route, bootstrap/streaming/repair xong |
| Native transport ready | CQL handshake/`system.local` | RF/CL và dữ liệu business đúng |
| Metadata/driver ready | `CqlSession.getMetadata()`, query prepare | Tất cả data replicas đã bắt kịp |
| Business + performance ready | Sentinel read/write tại CL, latency/error/queue windows | Toàn bộ token/tenant coverage nếu chỉ probe 1 key |

**Một phép SELECT `system.local` thành công không đủ** để tuyên bố ứng dụng dùng `LOCAL_QUORUM` hoặc `EACH_QUORUM` đã sẵn sàng. Cần probes trên keyspaces/token/queries đại diện và tránh thay đổi dữ liệu production không được phép.

### 4.3. State nên được ghi bền vững

Automation cần lưu ít nhất `run_id`, `change_hash`, wave index, node host IDs, timestamp, gate results, failed action/attempt, operator override và rollback status. Khi controller crash, nó phải **reconcile observed state** với checkpoint trước khi retry; không thực hiện lại thao tác có side effect chỉ vì một HTTP/JMX response bị mất.

### 4.4. Rollback không đồng nghĩa restart bản cũ ngay

Nếu binary mới đã chuyển on-disk format hoặc config/protocol feature đã được bật, rollback binary có thể **không được hỗ trợ**. Nếu node đang DOWN hoặc half-upgraded, rollback cần kiểm release-specific compatibility, snapshot/backup và cluster state trước. Vì thế nên có **canary + stop gates sớm** hơn là giả định “đổi image tag ngược lại luôn an toàn”.

## 5. Tính concurrency budget từ RF, CL và natural replicas

### 5.1. Công thức nền tảng cho mỗi replica set

Gọi `S(k, d)` là tập **natural full replicas** phục vụ partition key `k` trong DC `d`. Gọi `A(k, d)` là tập replicas hiện sẵn sàng đáp ứng CQL đúng deadline, `B` là tập nodes sẽ mất khả năng phục vụ khi thực hiện wave. Với `LOCAL_QUORUM` ở DC có RF=`r`:

\[
q_{\mathrm{local}} = \left\lfloor \frac{r}{2}\right\rfloor + 1.
\]

**Điều kiện cần** để wave không làm mất local quorum trên partition đang xét:

\[
\left|(A(k,d)\setminus B)\cap S(k,d)\right|
\geq q_{\mathrm{local}}.
\]

Để một wave được phép chạy trên toàn workload, bất đẳng thức phải đúng cho **mọi replica set/token range, keyspace và DC** có hợp đồng CL cần tiếp tục phục vụ, không chỉ một test key may mắn.

Đây chỉ là **kiểm đếm điều kiện cần**; nó chưa xét replica lag, disk saturation, network partition, client routing hay độ trễ. Automation phải kiểm thêm resource/SLO gates. Khi dùng transient replicas, thay đổi topology hoặc CL khác LOCAL_QUORUM, phải dùng **quy tắc consistency thực của phiên bản/replica type**, không áp máy móc công thức full RF ở trên.

### 5.2. Bảng trực giác cho một DC, full replicas

| Full RF (một DC) | CL | Số phản hồi cần về mặt logic | Số replica tối đa có thể không phục vụ mà CL vẫn *có thể* đạt | Chính sách rollout mặc định gợi ý |
|---:|---|---:|---:|---|
| 1 | `ONE`/`LOCAL_ONE` | 1 | 0 | Không rolling restart zero-downtime; cần planned downtime/HA redesign |
| 2 | `LOCAL_QUORUM` | 2 | 0 | Không tự restart node khi cần liên tục đáp ứng CL |
| 3 | `LOCAL_QUORUM` | 2 | 1 | **Một node tại một thời điểm** nếu tất cả replicas khác khỏe |
| 3 | `ALL` | 3 | 0 | Cần planned downtime/CL contract review |
| 5 | `LOCAL_QUORUM` | 3 | 2 | Vẫn khởi đầu concurrency=1, chỉ mở rộng khi có replica-set proof và headroom |
| 3 | `LOCAL_ONE` | 1 | 2 về số đếm | Không coi hai nodes down là mặc nhiên an toàn cho tính bền vững/latency |

Các cột “có thể đạt” **không** phải SLA/durability guarantee. Với `ONE`, còn một replica hoạt động không chứng minh nó có bản dữ liệu mới nhất hay disk khỏe. Kế hoạch vận hành thường giữ **an toàn bổ sung** thay vì tận dụng sát ngưỡng quorum để tăng tốc.

### 5.3. Vì sao số node cluster không thể thay `S(k,d)`?

~~~text
Cluster dc1 has 12 Cassandra nodes
Keyspace orders RF3

Token range X: natural replicas A, E, J
Token range Y: natural replicas B, F, K
Token range Z: natural replicas A, B, C

Wave {A, B}:
  X loses A -> 2 of 3 remain (possible quorum)
  Y loses B -> 2 of 3 remain (possible quorum)
  Z loses A,B -> 1 of 3 remains (NO quorum)
~~~

Vì token assignment/vnodes không đơn giản bằng “một replica mỗi rack” trong mọi thiết lập, cùng hai nodes có thể chồng replica ranges. Không chọn wave chỉ bằng thứ tự hostname hoặc chỉ cộng `maxUnavailable` của Kubernetes.

### 5.4. Giới hạn theo từng DC và failure domain

Với `NetworkTopologyStrategy`:

~~~text
dc1: RF3, A/B/C
dc2: RF3, D/E/F
App dc1: LOCAL_QUORUM -> needs 2 local replicas
App dc2: LOCAL_QUORUM -> needs 2 local replicas
~~~

Restart một node ở dc1 và một node ở dc2 **có thể** giữ local quorum trong mô hình full replicas khỏe, nhưng không phải cứ thế chạy song song. Nếu có thao tác dùng `QUORUM` trên 6 replicas, cần 4 replies; nếu vừa mất một ở mỗi DC thì đúng 4 còn lại, **không còn headroom** trước tail latency/network. Nếu dùng `EACH_QUORUM`, còn phải đủ quorum **từng DC**. Một policy bảo thủ có thể giữ **cluster-wide concurrent node restarts ≤1** trong giai đoạn đầu, dù lý thuyết cho phép nhiều hơn.

### 5.5. “Một node đã DOWN” thay đổi budget ngay

~~~text
Before:
  RF3, LOCAL_QUORUM, replicas A/B/C all healthy
  Planned restart A is conditionally safe.

At pre-wave gate:
  C is already DOWN or failing reads.

If restart A:
  A and C unavailable -> only B left.
  Do not start wave.
~~~

**Phải tính cả unavailable đã có, không chỉ các nodes bị automation chủ động restart.** Nếu node đã ở `DN` trong keyspace RF3/LQ, automation phải **HOLD/ABORT** đối với mọi wave làm mất replica thứ hai của cùng partition, kể cả wave đó ban đầu đã được duyệt.

### 5.6. Guard cho kết nối Java

Node availability của Cassandra chưa đủ nếu Java Driver:

- Dùng sai `localDatacenter`, chỉ nhận ra các nodes ở DC khác.
- Cấu hình contact points/routing sai nên pool còn quá ít coordinators.
- Gặp thundering herd reconnects khi node trở lại.
- Đang retry/speculate làm logical QPS khác physical attempts.
- Chuẩn bị CQL mới trước khi schema agreement/metadata ổn.

Một rollout đúng cần **check app-side success/error/in-flight** ngoài server-side replica count.

## 6. Thứ tự rollout: canary, một-wave, phân rack/DC và anti-affinity

### 6.1. Bước canary nên được chọn có chủ đích

Không nhất thiết chọn node đầu tiên theo hostname. Chọn canary theo:

- Cùng loại hardware/storage/JDK/Cassandra version cần thay.
- Có lưu lượng đại diện nhưng **không** là replica duy nhất đang khỏe của một critical range.
- Không đang bootstrap, replace, repair hoặc compaction backlog bất thường.
- Có thể thu logs/metrics và rollback với người vận hành trực.
- Có đủ disk/CPU/GC headroom để chịu cache cold/commitlog replay.
- Khi thay đổi ảnh hưởng multi-DC, nên có canary theo **từng DC/role/zone** với gate của ứng dụng tại DC đó.

Canary ít traffic có thể không bộc lộ lỗi hot partition; sau canary vẫn cần **representative token/DC/query-family probes**.

### 6.2. Thứ tự một đợt không chỉ là danh sách IP

~~~text
Plan:
  wave-0: canary node A (dc1/rack-1)
  wave-1: node E (dc1/rack-2)
  wave-2: node J (dc1/rack-3)
  wave-3: nodes in dc2, each gated

Before each wave:
  recompute replica intersection
  check current available nodes
  evaluate critical-keyspace CL
  check disk/streaming/repair/latency
~~~

Đây là **sơ đồ thứ tự minh họa**, không có đủ token maps để chứng minh các node A/E/J thật sự không chồng natural replicas. Plan thật cần lấy metadata topology từ cluster và workload registry/known token ranges, rồi tính safety predicates. Nếu thiếu bằng chứng, đặt `concurrency=1` hoặc **HOLD**, không tự suy an toàn.

### 6.3. Anti-affinity của Cassandra khác anti-affinity của scheduler

Một rack/availability zone thường là failure domain vật lý. Cassandra `GossipingPropertyFileSnitch`/`NetworkTopologyStrategy` có thông tin DC/rack để phân phối replicas phù hợp. Kubernetes `podAntiAffinity`/`topologySpreadConstraints` giúp đặt pods tách hosts/zones. Nhưng hai hệ phân phối này có thể không tương ứng nếu labels, snitch, rack map hoặc topology thay đổi.

**Chỉ khi kiểm topology thực** mới áp dụng được các ràng buộc theo rack vào concurrency. Một ConfigMap “rack=r1” không tự đảm bảo Cassandra thực nhận đúng rack.

### 6.4. Wave đi theo node host ID/tokens, không chỉ pod name

Pod có thể được recreate với tên tương tự nhưng host ID/tokens/storage mount khác. Nếu automation chỉ nhớ `cassandra-2`, một operator có thể vô tình áp rollout lên node vừa được thay thế thay vì restart. Record:

~~~text
planned_node:
  logical_name: cassandra-dc1-rack2-2
  host_id: "expected stable UUID"
  datacenter: "dc1"
  rack: "rack2"
  token_digest: "expected tokens fingerprint"
  storage_identity: "expected PVC/volume identity"
  intended_action: "restart_process"
~~~

Đây là **ví dụ manifest**, không phải cấu hình chuẩn của cass-operator; không ghi identity ngẫu nhiên làm expected host ID cho production. Trước thao tác, xác minh lại expected vs observed; mismatch → **STOP**.

### 6.5. Đừng tự đi tiếp sau watchdog timeout

Một node restart có thể cần thời gian dài do commitlog replay, JVM warm-up hoặc hints/caches. Nếu automation chờ 5 phút rồi hết deadline, **không nên tự restart node kế tiếp**. Time budget hết nghĩa là **HOLD/ABORT và kiểm tra**, không phải “coi node cũ đã xong”.

## 7. Phân biệt các dạng đồng thời trong hệ thống

| Loại concurrency | Đơn vị | Ví dụ guard | Tác động nếu vượt |
|---|---|---|---|
| Node restart | Node đang không phục vụ | 1 trên toàn cluster hoặc theo proof replica set | Mất CL/quorum |
| JVM/config rollout | Node với config mới | One canary, then gated waves | Mixed config/format/routing issues |
| Schema migration | DDL writer | **Một migration owner** | Schema disagreement/DDL races |
| Full repair | Repair sessions/token ranges | Chỉ tác vụ theo resource budget | Disk/network/compaction overload |
| Streaming/replace | Bootstrap/replacement job | Giới hạn rất thấp, per DC/rack/range | Token/data migration risk |
| Major compaction | SSTable rewrite | Per node/IO headroom | Disk full/read p99 tăng |
| App pods | Traffic-serving application instances | maxUnavailable/maxSurge + SLO | Client reconnect storm/query errors |
| Reconciliation workers | Business operations đang unknown | Bounded concurrency/rate | Retry storm/duplicate side effects |

Không đặt một biến `MAX_PARALLEL=5` dùng chung cho tất cả. Một repair task có thể chiếm nhiều I/O hơn một app pod rollout; hai node restarts có thể an toàn theo replica count nhưng **nguy hiểm** nếu cùng chia sẻ đĩa/network saturating.

### 7.1. Một wave có thể gồm nhiều thao tác không đồng thời

~~~text
Within one node wave:
  Acquire lease
     -> Preflight
     -> Drain (if planned)
     -> Stop process
     -> Replace binary/config
     -> Start process
     -> Wait readiness
     -> Verify data/CL
     -> Soak + release lease
~~~

Đây là **một chuỗi thứ tự**. Tăng concurrency nội bộ bằng chạy `drain` và `stop` đồng thời sẽ làm mất ý nghĩa graceful shutdown. Chạy backup/snapshot/repair song song với restart cũng phải được owner/IO budget phê duyệt, không mặc định an toàn.

### 7.2. Concurrency budget theo token ranges

Một controller có thể dựng conflict graph:

~~~text
node A ---- shares critical replica set ---- node B
node A ---- independent enough -----------> node E
node B ---- shares critical replica set ---- node F

Conflict edge A-B:
  must never be offline together under this CL.
~~~

Chọn các nodes của cùng wave từ **independent set** của graph, sau đó áp resource/business budgets. Đây là bài toán thực thi không đơn giản khi có nhiều keyspaces/token ranges; nếu không có metadata chứng minh graph đúng, không tự tính xấp xỉ từ tên rack.

### 7.3. Một node không DOWN vẫn có thể mất capacity

Throttle compaction hoặc chạy repair có thể không làm node `DN` nhưng làm read p99 cao, timeout và hinted handoff tăng. Resource budget vì vậy cần nhìn **busy nodes**, không chỉ `inFlightRestarts`. Ví dụ: restart A trong khi B đang full repair và C đang disk 95% utilization có thể phá quorum latency dù về lý thuyết B/C “UP”.

### 7.4. Đặt giới hạn bảo thủ trước, mở rộng theo bằng chứng

Khuyến nghị thực hành: khi chưa có bộ đánh giá replica-set đầy đủ, bắt đầu với **một node mỗi lần cho việc có downtime** và **không chạy repair nặng đồng thời**. Nhưng đừng nói “một node mỗi lần luôn đảm bảo không downtime”: với RF1/2 hoặc CL ALL, ngay cả một node cũng có thể không an toàn.

## 8. Preflight: có đủ bằng chứng để bắt đầu không?

### 8.1. Xác minh danh tính cluster và change scope

Trước khi chạy, ghi:

- Cluster ID/name, cloud/region, DC/rack và CQL/JMX endpoints theo allowlist.
- Phiên bản Cassandra/JDK/driver/operator hiện tại và phiên bản mục tiêu.
- Danh sách **host IDs, token ownership, network addresses, storage identity** chính xác.
- Keyspaces quan trọng, RF theo DC, CL đọc/ghi/LWT, token ranges/tenant hot.
- Loại thao tác: binary/config restart hay thay topology/data ownership.
- SHA/checksum của package, container image digest, config diff và target state.
- Sở hữu change/approval, maintenance window, contact on-call và rollback authority.
- Thời điểm backup/snapshot/restore tested gần nhất, có thể restore hay không.

**Không** bắt đầu bằng mỗi tên cluster do `nodetool describecluster` trả về; hai môi trường có thể cấu hình cùng tên. Dùng inventory/identity/credentials và network allowlist độc lập.

### 8.2. Các lệnh đọc-only phục vụ preflight

~~~bash
# Chỉ trên Cassandra cluster được phép kiểm tra.
# Mỗi lệnh yêu cầu quyền JMX/host phù hợp.
nodetool status
nodetool describecluster
nodetool info
nodetool tpstats
nodetool netstats
nodetool compactionstats
nodetool gcstats
~~~

Lưu ý:

- `nodetool status` dùng gossip và có thể khác góc nhìn giữa nodes; đọc ở hơn một node khi có nghi vấn partition mạng.
- `describecluster` hiển thị schema versions; agreement không chứng minh data đã repaired.
- `tpstats` cho pending/dropped work trong thread pools.
- `netstats` cho streaming; active streaming không tự động là sự cố nhưng có thể cạnh tranh disk/network.
- `compactionstats` cho active/pending compaction; pending=0 không phải điều kiện bắt buộc cho workload ghi liên tục.
- `gcstats` snapshot GC; nên kết hợp metrics/GC logs liên tục.

### 8.3. CQL kiểm topology và keyspace contract

~~~sql
SELECT cluster_name, data_center, host_id,
       release_version, schema_version
FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name='orders';
~~~

Trong lab có thể thay `orders` bằng keyspace được phép kiểm; không sửa system schema. `system.local` là **view cục bộ của coordinator** đang kết nối, nên nếu cần đối chiếu versions giữa nhiều nodes hãy kết nối trực tiếp đến mỗi node có quyền truy cập.

### 8.4. Sự khác nhau giữa status, availability và readiness

| Chỉ số | Đáng tin để xác nhận | Không đủ để xác nhận |
|---|---|---|
| `UN` ở ring | Node được gossip xem Up/Normal | Mọi app request đạt CL |
| JMX responds | JVM đã cung cấp management endpoint | Native transport CQL phục vụ bình thường |
| Port 9042 open | Có socket listener | CQL auth/schema/query ổn |
| `SELECT system.local` | Query nội bộ cơ bản xử lý được | User keyspace natural replicas đủ CL |
| `SELECT by primary key` ở ONE | Một replica có thể trả dữ liệu | Local quorum/global quorum và dữ liệu đều đủ |
| Driver ready/pool connected | Có thể gửi requests | Schema mới/metadata đúng và p99 ổn |
| K8s Pod Ready | Probe được định nghĩa đạt | Cassandra business readiness nếu probe chỉ kiểm port |

Một rollout gate tin cậy là **hội của nhiều tín hiệu độc lập**. Nếu telemetry của Cassandra/JVM/driver bị mất, không coi là “không có lỗi”, mà là **mất khả năng đánh giá** → HOLD.

### 8.5. Preconditions bất biến

~~~text
Before wave N:
  no unapproved schema migration running
  no unexpected UN->DN transition
  no conflicting backup/restore/repair/bootstrap
  enough replica/CL headroom for chosen wave
  free disk and CPU/network headroom
  app-level baseline SLO within bounds
  controller lease is sole owner
  rollback/recovery path is documented
~~~

Các điều kiện phải được **đánh giá lại sau mỗi wave**. Bất biến với wave trước không đảm bảo còn đúng khi hardware failure xảy ra ở wave hiện tại.

## 9. Manifest của một rollout có thể tái lập

### 9.1. Một mẫu khai báo không phụ thuộc tool

~~~yaml
# PSEUDOCODE/YAML DATA MODEL — không phải manifest cass-operator
run:
  run_id: cassandra-rolling-config-2026-11-21-01
  environment: isolated-staging
  cluster_identity: expected-host-id-set-and-cert-fingerprint
  change_type: cassandra_process_config_restart
  source_version: "4.1.x"
  target_version: "4.1.x"
  change_digest: "sha256-of-reviewed-config-package"
  approved_by: "cassandra-ops-owner"
  start_window_utc: "2026-11-21T01:00:00Z"
  end_window_utc: "2026-11-21T03:00:00Z"
  dry_run_first: true

topology:
  datacenters:
    dc1:
      racks: [rack1, rack2, rack3]
      nodes: 3
      critical_keyspaces:
        - name: orders
          full_rf: 3
          normal_read_cl: LOCAL_QUORUM
          normal_write_cl: LOCAL_QUORUM
  known_degraded_nodes: []

rollout:
  batch_size_initial: 1
  max_global_unavailable_nodes: 1
  max_per_dc_unavailable_nodes: 1
  forbid_replica_set_quorum_loss: true
  forbid_restarts_on_joining_or_replacing_nodes: true
  canary_count: 1
  max_inflight_waves: 1
  cooldown_between_waves_seconds: 120
  max_wave_duration_seconds: 1800

gates:
  require_expected_node_identity: true
  require_cassandra_up_normal: true
  require_native_transport: true
  require_schema_agreement_among_up_nodes: true
  require_expected_token_set: true
  require_cl_data_probes: true
  require_driver_query_probes: true
  error_rate_max_percent_example: 0.5
  p99_latency_ms_max_example: 150
  disk_free_min_percent_example: 25
  steady_windows_required: 5
  window_seconds: 60
  abort_on_new_down_node: true

recovery:
  on_gate_timeout: HOLD
  on_data_mismatch: ABORT
  on_unknown_action_outcome: HOLD_AND_RECONCILE
  rollback_requires_approval: true
~~~

Đây là **mô hình dữ liệu minh họa**. Tên fields như `forbid_replica_set_quorum_loss` hay `steady_windows_required` **không** phải tùy chọn Cassandra YAML, Kubernetes PDB hoặc cass-operator mặc định. Muốn chạy thực phải viết/kiểm implementation của controller và thu metrics. Các ngưỡng 0,5%, 150ms, 25%... chỉ là con số giả định; SLO/guardrails thực phụ thuộc workload, storage, RF/CL và baseline.

### 9.2. Manifest không được chứa secret

Không nhúng password Cassandra, token JMX, private keys hoặc raw customer IDs vào YAML rollout. Thay bằng references tới secret manager/identity có quyền tối thiểu; audit log chỉ lưu hash/ID của thay đổi. **Không chia sẻ** manifest chứa hostnames và topology nhạy cảm ngoài phạm vi vận hành được phê duyệt.

### 9.3. Vì sao cần `change_digest`?

Khi controller crash rồi được resume, nó phải biết artifact/config mục tiêu **vẫn là cùng một phiên bản đã phê duyệt**. Nếu image tag `latest` đổi trong lúc chạy, wave N có thể dùng binary khác wave N+1. Nên pin:

- Docker image digest hoặc binary package checksum.
- Rendered `cassandra.yaml` diff/checksum, không chỉ git branch.
- JVM arguments/JDK version.
- App/driver/sidecar/operator versions.
- Những compatibility feature modes phải đặt theo upgrade guide.

### 9.4. Lưu `run_id`, `action_id` và `node_id` riêng

~~~text
run_id    = one rollout campaign
wave_id   = one bounded group of changes
action_id = one intended side-effect on a specific node
attempt_id= one network/API attempt to perform that action
node_id   = stable Cassandra host ID + expected token/volume identity
~~~

Một HTTP request tới operator timeout không chứng minh action chưa bắt đầu. **Không phát lại `restart node` với action_id mới** cho tới khi reconciler xác định node đang ở state nào và action trước có còn in flight hay không.

### 9.5. Không được dùng batch size đã duyệt để bỏ qua gate

`batch_size=1` là **giới hạn tối đa**, không phải mục tiêu buộc phải thực thi. Nếu trạng thái cluster suy giảm, concurrency được phép có thể giảm về **0**. Controller phải tính `effective_batch_size = min(configured_cap, safety_budget, resource_budget)`, và nếu bằng 0 thì **HOLD**.

## 10. Gate theo thời gian: quan sát xu hướng, không chỉ một snapshot

### 10.1. Sự khác nhau giữa startup, recovery và steady state

~~~text
T0  node process restarted
T1  JVM/Cassandra system tables load
T2  gossip UP / native transport ready
T3  driver reconnect and metadata refresh
T4  CQL at required CL succeeds
T5  cache warms, hints/streaming/repair backlog drains
T6  p99/error/GC/disk trend returns to accepted range
T7  wave declared healthy
~~~

Thời gian T0..T7 phụ thuộc dataset, commitlog replay, JVM warm-up, disk, repair, workload và cluster size; **không có fixed 60 giây** bảo đảm tất cả Cassandra nodes ready. Nếu node cần bootstrap/replace, T5 còn có thể bao gồm streaming/repair theo runbook topology.

### 10.2. Ví dụ rolling-window gate

Giả sử business SLO tại một query family là p99 ≤ 150ms, error rate < 0,5%, QPS mục tiêu 2.000/s (số liệu **minh họa**):

| Gate | Điều kiện ví dụ | Chứng minh |
|---|---|---|
| Availability | Không có node UN→DN mới ngoài node dự kiến | `nodetool status` từ nhiều peers |
| Data correctness | Known-key sentinel ở `LOCAL_QUORUM` trả đúng revision/value | CQL/Java business probe |
| App success rate | Error rate < 0,5% cho 5 windows liên tiếp | End-to-end app metrics |
| Latency | p99 ≤ 150ms cho mỗi query family quan trọng | Histogram đủ samples |
| Throughput | Completed QPS giữ gần offered QPS, không giảm do retries/throttling | Client/generator |
| Background tasks | Repair/streaming/compaction queue không tích lũy | `netstats`/`compactionstats`/JMX |
| Resources | Disk free/GC/network/CPU/await có headroom | Host + Cassandra metrics |
| Driver | Pool connected, in-flight/retries không trôi | Java Driver metrics |

Nếu một query family có chỉ 50 requests mỗi phút, p99 của cửa sổ 60s không đáng tin như 100.000 mẫu; mở cửa sổ hoặc báo raw results/upper bounds. **Đừng dùng percentiles mà không ghi sample count**.

### 10.3. Một cổng giữa các wave tối thiểu

~~~text
For each of 5 consecutive windows:
  available replica sets pass CL contract
  data oracle probes pass
  no new unexpected DOWN node
  app p99 within SLO (with enough samples)
  error/timeouts/retries within budget
  disk/GC/queue/streaming trends acceptable

Only THEN release wave lease and proceed.
~~~

Nếu metric mất hoặc query oracle không có dữ liệu tham chiếu, trạng thái là **UNKNOWN**, không tự tính pass. Nếu nhiều windows thất bại nhưng recovery đang tiến triển, HOLD có deadline; hết deadline → ABORT/escalation.

### 10.4. Compaction luôn có thể đang chạy

Không bắt `PendingCompactions=0` tuyệt đối trên workload write-heavy; Cassandra có thể continuously compact trong steady state. Quan trọng là backlog/bytes/active tasks/IO có **ổn định** hay tăng không giới hạn. Ngược lại, `PendingCompactions=0` ở một thời điểm không chứng minh disk, tombstones hay p99 đều ổn.

### 10.5. Độ trễ bị “đẹp giả” vì request chậm timeout

Một rollout có thể làm p99 success requests giảm do những requests chậm nhất **thất bại và bị loại khỏi histogram**. Gate phải báo **timeouts, cancelled requests, unknown write outcomes, retries/speculative attempts** cùng latency. Không coi p99 success giảm là PASS nếu error rate tăng.

## 11. Phân pha một rolling change: từ canary đến post-soak

### 11.1. P0 — Chuẩn bị

1. Chốt danh sách keyspaces + read/write CL + natural replica sets/critical queries.
2. Kiểm sản phẩm/version/compatibility của binary/config target.
3. Chụp baseline node/gossip/schema/data probes, app SLO và resource headroom.
4. Có backup/snapshot/rollback plan theo loại thay đổi, không giả định snapshot cần restore được ngay.
5. Đặt lock/lease cho cluster và chặn competing maintenance windows.
6. Chọn canary và sắp xếp waves; dry run đánh giá từng candidate.
7. Lấy approval/owner, xác định stop thresholds và maintenance deadline.

### 11.2. P1 — Canary

1. Re-check preflight ngay trước thao tác.
2. Đưa node candidate ra khỏi traffic theo runbook tương ứng (nếu cần), không phá metadata/token ownership.
3. Thực thi một action với stable `action_id` và event log.
4. Theo dõi startup/health/CL/schema/driver probes.
5. Giữ soak window; kiểm data oracle và latency trên representative keys.
6. Nếu PASS, ghi checkpoint `CANARY_VERIFIED`. Nếu FAIL, **không đi tiếp**.

### 11.3. P2 — Các waves tiếp theo

~~~text
for each wave:
  refresh topology and client observed health
  recompute safety budget
  verify no outstanding unknown action
  execute ≤ effective_batch_size
  observe all applicable gates
  checkpoint verified results
  proceed only on explicit GO
~~~

Đây là **pseudocode**, không được dùng để thao tác production trước khi có atomic leases và các API/chính sách đồng nhất. Không lặp mù qua tất cả hostnames khi node trước chưa trở lại phục vụ.

### 11.4. P3 — Post-rollout

Sau node cuối:

- Xác nhận mọi expected host ID/token/rack/DC/state, không có replacement ngoài kế hoạch.
- Kiểm application release/driver metadata/schema compatibility.
- Chạy read/write business probes ở CL đúng contract trên những token ranges đại diện.
- Theo dõi warm-up, GC, flush/compaction/repair/streaming và disk sau khi tải trở lại.
- Thu số liệu error/timeouts/p95/p99 trong soak window.
- Xác minh package/config digest đồng nhất theo **planned compatibility stage**.
- Đánh dấu `COMPLETED` chỉ khi post-rollout gates PASS.

### 11.5. P4 — Audit và postmortem nếu cần

Lưu node/wave timestamps, input manifest checksum, observed health từng gate, hành động operator/manual override, rollback/recovery, duration và unresolved risks. Nếu phải dừng giữa chừng, giữ **resume plan** gồm trạng thái từng node, không bắt đầu lại từ đầu không có kiểm tra.

## 12. Runbook rolling restart Cassandra process

### 12.1. Phân biệt restart thường và node replacement

**Restart thường:** Cùng logical Cassandra node, host ID, token ownership và data directory/volume. Có thể thay JVM options/config hoặc restart service, nhưng không tạo node mới và không chuyển token ownership.

**Replacement:** Một logical node chết/volume mất cần node khác thay; có thể khác host ID, bootstrap/streaming, hints/repair và thay đổi data placement. Đây là một quy trình **topology change riêng**, không gộp vào rolling restart script.

Khi automation thấy unexpected host ID/token digest sau khi pod được recreate, phải **STOP**. Không gán tên pod giống cũ là “restart thành công”.

### 12.2. Kiểm tra trước khi drain

~~~text
Candidate node A:
  - planned host ID/tokens match observed
  - no unexpected DN/UJ/UL/UM nodes elsewhere
  - per-keyspace/token replica budget PASS if A unavailable
  - app QPS/error/p99 baseline acceptable
  - disk free/commitlog/GC/compaction headroom adequate
  - no conflicting repair/replace/backup operations
  - controller holds exclusive lease
  - operator approved the exact config/image digest
~~~

Nếu một replica khác vừa DOWN hoặc `netstats` cho thấy streaming chưa xong, không chạy tiếp chỉ vì maintenance window đang ngắn dần.

### 12.3. `nodetool drain` là thao tác thay đổi trạng thái

Theo tài liệu Cassandra, `nodetool drain` **ngừng nhận writes và flush tất cả tables** để chuẩn bị tắt node. Nó **không phải lệnh quan sát** và không nên chạy để kiểm tra xem node có khỏe không.

~~~bash
# PSEUDOCODE RUNBOOK — chỉ trên node được phép
# 1. Quiesce/redirect traffic if required by deployment design.
# 2. Check topology and all gates first:
nodetool status
nodetool tpstats
nodetool compactionstats

# 3. Immediately before approved graceful shutdown:
nodetool drain

# 4. Stop/start using approved service manager or operator.
#    The exact systemctl/Kubernetes/API action is environment-specific.
~~~

Sau drain, node không nên được coi là phục vụ writes bình thường cho tới khi được restart phù hợp. Nếu drain thành công nhưng stop/restart API timeout, controller phải **reconcile actual process state**, không chuyển sang node khác hay gọi drain lặp liên tục.

### 12.4. Chưa được giả định tất cả nền tảng cần gọi drain thủ công

Một cass-operator/management layer hoặc service shutdown hook có thể đã tích hợp graceful stop/drain đúng thứ tự. Tự gọi drain trước khi operator có kế hoạch khác có thể làm lệch state machine hoặc kéo dài downtime. Xem **runbook của deployment**: một actor duy nhất sở hữu từng lifecycle action.

### 12.5. Sau restart cần nhiều cổng xác nhận

~~~text
Process JVM started
     |
JMX/management API available
     |
Gossip reports node Up/Normal
     |
Native transport CQL + authentication works
     |
Schema metadata and driver route recognize node
     |
Known-key CL reads/writes (where authorized) PASS
     |
No unexpected streaming/repair failures
     |
App SLO / driver retries / GC / disk stabilize
     |
Wave VERIFIED
~~~

`nodetool status UN` là điều kiện quan trọng nhưng **không đủ**. Nếu node vẫn ở `UJ` (joining), `UL` (leaving) hoặc `UM` (moving), đây không phải một restart bình thường đã hoàn tất; cần ngăn wave kế và điều tra topology.

### 12.6. Cảnh báo khi restart khiến cache lạnh

JVM caches/driver connections có thể lạnh; OS page cache có thể vẫn ấm nếu chỉ restart process/container, tùy host/volume. Hints/catch-up, commitlog replay và compaction có thể chiếm I/O sau startup. Do đó không dùng mỗi `sleep 30` hay p99 của một truy vấn `system.local` làm recovery gate.

### 12.7. Nếu restart thất bại thì làm gì?

| Trạng thái | Hành động |
|---|---|
| Node process chưa dừng, action response mất | Reconcile process/host ID; không stop lần hai mù |
| Drain xong nhưng restart chưa chạy | HOLD và owner xử lý node drained |
| Start process nhưng gossip DN | Kiểm logs/internode/JVM/disk; không restart node khác |
| Gossip UN nhưng CQL auth/schema fail | HOLD, điều tra CQL transport/config/DDL |
| CQL PASS nhưng CL data probe fail | HOLD, kiểm replicas/ownership/data |
| CL PASS nhưng p99/GC/disk xấu | HOLD/rollback assessment, không tuyên bố recovered |
| Storage identity/token changed | **ABORT + topology incident** |

### 12.8. Không dùng `removenode`/`decommission` khi restart đơn giản

`nodetool decommission`/`removenode` có thể thay ownership và khởi tạo streaming/data redistribution, **không** phải lệnh “đưa node ra khỏi load balancer để restart”. Dùng sai có thể gây thay đổi topology không mong muốn và repair/cleanup tốn kém. Khi cần thực sự thay node, dùng replacement-specific plan và đọc docs topology của đúng Cassandra version.

## 13. Rolling binary upgrade và cấu hình

### 13.1. Thay binary là việc có điều kiện phiên bản

Rollout Cassandra 4.1.x → 4.1.y trong cùng minor line, 4.1 → 5.0, hoặc đổi JDK/compaction strategy/feature flag **không có cùng quy tắc**. Việc nâng major version cần:

- Xác minh upgrade path và version support của Cassandra + JDK + driver.
- Xác minh tương thích mixed-version cluster trong rolling phase.
- Đảm bảo không dùng CQL/feature/index/compaction option chỉ node mới hiểu khi node cũ còn phục vụ.
- Kiểm hạn chế rollback sau khi on-disk/data format thay đổi.
- Xác nhận repair, schema migration và SSTable upgrade strategy riêng.

Không tự áp các lệnh `nodetool upgradesstables` hay một cấu hình mới cho tất cả nodes ngay khi canary lên; chúng có thể tạo nhiều disk I/O và thay đổi rollback options.

### 13.2. Compatibility modes trong Cassandra 5.x

Tài liệu cấu hình Cassandra 5.0 mô tả `storage_compatibility_mode` với các chế độ tương thích và giai đoạn chuyển `CASSANDRA_4` → `UPGRADING` → `NONE` theo đường nâng cấp được hỗ trợ. Những bước này có thể yêu cầu **nhiều vòng rolling restart**; không gộp ba chế độ trong một wave hoặc bật `NONE` khi cluster còn nodes ở phiên bản chưa tương thích.

Đây là **ví dụ thuộc phiên bản cụ thể**, không phải một recipe áp cho mọi upgrade; hãy kiểm tài liệu Cassandra 5.x và exact supported source version trước khi chạy. Nguồn: [cassandra.yaml reference](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html).

### 13.3. Canary kiểm cả phiên bản và hành vi

~~~text
Before canary:
  source binary hash, JDK, config hash captured
  schema/data/driver baseline captured

After canary:
  expected release_version on node
  same expected host_id and token ownership
  native transport and app CQL probe PASS
  p99, GC, disk, compaction in range
  driver handles mixed-version cluster
  no new warnings/errors from upgraded binary
~~~

Nếu một tính năng mới chỉ dùng được sau khi toàn cluster upgrade xong, **không** bật nó ở canary rồi tuyên bố các nodes cũ tương thích.

### 13.4. Cấu hình dynamic vs restart-required

Một số Cassandra settings có thể được chỉnh bằng nodetool/JMX/runtime API (nếu phiên bản hỗ trợ); số khác yêu cầu process restart; một số thay đổi có **tác động dữ liệu/topology**. Phải phân loại trước:

| Thay đổi | Cách triển khai phù hợp | Cổng bổ sung |
|---|---|---|
| Log level runtime | API runtime có permission | Log volume, disk/CPU |
| Compaction throughput | Runtime/config theo phiên bản | Pending compaction bytes, disk I/O |
| Heap/JVM flags | Rolling process restart | GC pause, OOM risk, startup time |
| Snitch/DC/rack mapping | **Topology-sensitive** | Replica placement/ring; runbook riêng |
| Storage compatibility mode | Version-controlled rolling phases | Binary compatibility and data format |
| RF/keyspace | Schema change + data distribution | Repair/streaming and CL probes |
| Table compaction strategy | DDL + background SSTable rewrite | Disk headroom, read/write p99 |

**Không coi mọi edit `cassandra.yaml` là một thay đổi “config thuần túy”.** Một số là thay đổi hành vi phân tán, restart hoặc data layout.

### 13.5. Rollback phải có bảng khả năng

~~~text
Change A: logging config -> restore previous value
Change B: JVM heap setting -> revert and restart, preserving quorum
Change C: binary major upgrade -> rollback MAY be unsupported
Change D: schema DROP COLUMN -> rollback may lose data
Change E: node replacement -> data/topology procedure, not simple revert
~~~

Người phê duyệt phải biết **cái gì reversible** trước rollout. Không ghi một action `rollback: restart_old_binary` chung cho mọi major-version upgrade mà chưa xác minh tương thích release.

## 14. Rolling application deployment và Java Driver metadata

### 14.1. Vì sao thay Java app cũng có thể gây outage Cassandra?

Ứng dụng mới có thể:

- Dùng câu CQL/keyspace/table/index mới, migration chưa xong.
- Đổi `withLocalDatacenter` hoặc connection pooling khiến driver không tìm được coordinators.
- Tăng request concurrency/retries/speculative execution, tạo tải vật lý cao hơn.
- Gửi LWT ở `SERIAL` thay vì `LOCAL_SERIAL`, thay behavior WAN/latency.
- Sử dụng CL khác, gây `Unavailable` hoặc đọc dữ liệu stale nếu hạ CL.
- Chạy DDL từ mỗi pod startup tạo schema races.
- Tạo prepared statement vào table chưa được áp dụng trên mọi nodes.

Do đó có thể cần rollout app **riêng** với canary/metrics/rollback, không đồng thời rolling restart Cassandra nếu không có joint change plan.

### 14.2. Cổng trước deploy app

~~~text
Versioned DDL migration completed by ONE runner
       |
Schema agreement among relevant UP nodes
       |
Expected table/columns/PK verified
       |
Application vN+1 can PREPARE representative CQL
       |
Driver local DC, auth/TLS, pool/routing validated
       |
Canary app pods serving small traffic percentage
       |
Data/CL + p99/error/retry gates
       |
Expand traffic with bounded maxUnavailable/maxSurge
~~~

`IF NOT EXISTS` trong DDL không xác nhận **existing table definition** giống expected schema. Nếu old/new binaries dùng cùng table khi rolling app deploy, ưu tiên expand–migrate–contract: thêm cột tương thích, backfill, đổi code, rồi mới loại bỏ dependency cũ sau khi xác minh.

### 14.3. Concurrency ứng dụng khác concurrency node

Một app StatefulSet/Deployment `maxUnavailable=1` hoặc `maxSurge=1` giúp hạn chế pod transition, nhưng **không** tự giới hạn concurrent Cassandra requests nếu pod mới tạo nhiều connections hoặc retries. Cần driver/request throttling, backpressure và warm-up gates.

### 14.4. Retry không phải readiness

Nếu driver tự retry 20 lần rồi HTTP request “thành công”, business p99 có thể xấu và Cassandra chịu 20 physical attempts. Theo dõi **logical requests vs node messages/attempts**, timeouts, LWT unknown outcomes, JMX ClientRequest Latency, pools/in-flight. Không dùng “5xx giảm” làm điều kiện duy nhất nếu retries tăng gấp nhiều lần.

### 14.5. Một chẩn đoán `unconfigured table` sau app rollout

~~~text
Old app CQL: orders_by_id (status, revision)
New app CQL: orders_by_id (status, revision, new_field)
Schema migration ADD new_field not yet applied
                         |
                PREPARE/SELECT fails
~~~

**STOP/HOLD** app rollout, kiểm `system_schema.columns`, schema agreement và query strings/driver metadata. Không `DROP TABLE` hay restart Cassandra vô điều kiện để “refresh”.

## 15. Điều phối repair, streaming, backup và compaction

### 15.1. Một tác vụ không làm node DOWN vẫn gây rủi ro

Repair/streaming/compaction/backup có thể giữ node `UN` nhưng làm disk/network/CPU bão hòa. Nếu một wave restart node A đồng thời B đang repair và C đang compaction backlog cao, quorum số đếm B+C vẫn đủ nhưng **latency/ACK có thể không đạt SLO**.

~~~text
RF3 replicas: A, B, C

A: planned restart (unavailable)
B: full repair / streaming at high disk I/O
C: compaction + client writes saturating disk

Logical quorum: B + C = 2
Practical quorum before timeout: maybe not.
~~~

Do đó phải có **maintenance mutual exclusion/IO budgets** trên các natural replica sets, không chỉ `maxUnavailable`.

### 15.2. Repair phải có coverage và ownership

Theo Apache Cassandra, repair đồng bộ các data ranges bằng anti-entropy/streaming; hinted handoff chỉ **best effort**, không thay repair. Repair có thể tốn tài nguyên mạnh và phải được lên lịch. Với các phiên bản sử dụng `nodetool repair -pr` (primary ranges), chạy có kế hoạch để bao phủ ranges toàn cluster, tránh thực hiện trùng lặp việc cho cùng token ranges khi chưa hiểu options.

~~~text
Maintenance plan:
  identify keyspace + token ranges
  identify involved replicas + DC
  choose one bounded repair task
  monitor streaming/anticompaction/IO
  verify coverage and backlog
  then start next task
~~~

**Không** gọi `nodetool repair -pr` trên mỗi node cùng lúc chỉ vì muốn giảm tổng thời gian; trùng resource domains có thể làm cluster mất khả năng phục vụ. Khi full/incremental repair, pending repair sessions hay compaction state khác nhau theo Cassandra version, cần tuân thủ runbook chuyên dụng.

### 15.3. Backup/snapshot không phải trạng thái data recovery

`nodetool snapshot` hoặc backup orchestrator có thể tạo bản sao SSTables, nhưng “snapshot job succeeded” chưa chứng minh **restore works**, commitlog/PITR coverage hay schema manifest đủ. Nếu đang rolling config/binary change rủi ro, xác định snapshot/backup gần nhất và restore test; tránh chạy snapshot đồng thời làm đầy disk.

### 15.4. Streaming sau bootstrap/replace

`nodetool netstats` cho biết streaming progress theo góc nhìn node. Sau topology change:

- Không dựa vào `UN` đơn lẻ để bỏ qua streaming/data verification.
- Kiểm token ownership, RF/DC và natural replicas mới.
- Có thể cần repair theo điều kiện down duration/hints/replacement method của **đúng Cassandra version**.
- Chỉ chạy cleanup trên các nodes mất token ownership khi topology/streaming đã ổn và runbook cho phép.

`cleanup`, `decommission`, `rebuild` và `replace` là thao tác dữ liệu/topology **không được tự thêm vào một rolling restart job**.

### 15.5. Phân loại maintenance trước khi lên lịch

| Task | Được chạy song song với node restart? | Cơ sở quyết định |
|---|---|---|
| Read-only metrics scrape | Thường có, rate-limited | Không tạo áp lực đáng kể |
| Snapshot/backup | Chỉ sau resource/space review | Disk headroom và consistency backup manifest |
| Incremental repair | Cần overlap/range/IO proof | Replicas, streaming, compaction pressure |
| Full repair | Rất hạn chế | Disk/network, data amplification, duration |
| Major compaction | Nên tránh chồng node restart | Rewrite SSTables và free space |
| Bootstrap/replacement | **Tách change plan** | Token ownership/streaming/natural replicas |
| Schema migration | Serial owner, coordination với app | Schema agreement và backward compatibility |

Đây là **risk guidance**, không phải lệnh Cassandra cấm đồng thời. Một vài tác vụ có thể được lên lịch song song khi có evidence/headroom và chuyên gia phê duyệt; mặc định automation phải bảo thủ.

## 16. Kubernetes, StatefulSet và cass-operator: automation không được “đi vòng” controller

### 16.1. PDB chỉ bảo vệ một phần

Kubernetes `PodDisruptionBudget` giới hạn **voluntary evictions** theo các pod matching selector; nó không bảo đảm:

- Cassandra có đủ natural replicas tại required CL.
- Mọi token ranges đều giữ quorum.
- Node thật sự đã chuẩn bị shutdown/drain/streaming an toàn.
- App Java Driver đã route sang replicas còn khỏe.
- Disk/GC/network của những pods còn lại có headroom.

Với `maxUnavailable: 1`, PodDisruptionBudget là **hàng rào bổ sung**, không thay Cassandra-aware rollout gates.

### 16.2. StatefulSet readiness/ordering

Kubernetes StatefulSet có ordered rollout semantics theo policy và readiness. Nhưng nếu readiness probe chỉ kiểm `9042` hoặc container RUNNING, scheduler có thể coi pod READY quá sớm so với Cassandra CL/data/performance. Cần readiness definitions tương thích operator và giám sát Cassandra-native metrics.

### 16.3. cass-operator có lifecycle controller riêng

Trong K8ssandra/cass-operator, Management API và operator quản lý node lifecycle; các bản mới có `CassandraTask` cho nhiều thao tác vận hành, trong đó rolling restart. Một số CRD exposes `fast`/`force` và các controls khác theo release. **Đọc CRD/operator version thực**:

- Đừng bật `fast` chỉ vì muốn triển khai nhanh: một số modes có thể cho phép restart nhiều nodes/rack cùng lúc.
- `force` có thể bỏ qua kiểm tra an toàn của operator; không bật để “vượt gate” khi cluster degraded.
- Một số fields cũ như `rollingRestartRequested` đã bị deprecate ở CRD versions; sử dụng API hiện hành.
- Không gọi `kubectl delete pod --all` hoặc chỉnh trực tiếp StatefulSet trong khi operator đang reconcile một kế hoạch khác.

Tài liệu tham khảo: [K8ssandra cass-operator](https://docs.k8ssandra.io/components/cass-operator/) và [CRD reference](https://docs.k8ssandra.io/reference/crd/cass-operator-crds-latest/index.html).

### 16.4. Một PDB minh họa, không phải safety proof

~~~yaml
# Minh họa Kubernetes PDB; không deploy trực tiếp.
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-example-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: cassandra-lab
~~~

PDB chỉ khớp nếu selector thực sự bao phủ đúng pods; trong operator-managed cluster, operator có thể tạo/quản lý PDB và người vận hành không nên tạo đối tượng trùng. Không giả định chính sách này ngăn pod crash, node failure, force delete hoặc mọi dạng rolling update.

### 16.5. Không nhầm `minReadySeconds` với data recovery

`minReadySeconds` (nếu controller/version hỗ trợ) yêu cầu pod duy trì Ready một thời gian tối thiểu. Nó hữu ích chống “ready flap” nhanh, nhưng vẫn phụ thuộc **định nghĩa Ready probe**; 30 giây Pod Ready không tự chứng minh data repair/hints/compaction và p99 đã ổn.

### 16.6. Operator status và controller riêng cần đồng thuận

Nếu một cluster dùng cass-operator và automation bên ngoài, phải có **single owner** của từng lifecycle action, không phát commands trực tiếp làm operator bất ngờ sửa ngược. Đọc status của CassandraTask/K8ssandraTask và node states **sau** action; nếu Task Completed nhưng CQL/CL data probe FAIL, controller phía application phải **HOLD**.

### 16.7. Bốn trường hợp cần chặn ngay

~~~text
K8s Pod Ready = true, Cassandra node DN   -> HOLD
Operator Task Completed, app LOCAL_QUORUM fails -> HOLD
PDB maxUnavailable=1, another replica already failed -> HOLD
Operator rolling restart in progress, external job requests decommission -> STOP
~~~

Không chỉnh PDB thành `maxUnavailable: 100%` hoặc bật operator `force` chỉ để vượt một stalled rollout. Cần xác định vì sao gate không PASS, thu logs/state và quy trình incident.

## 17. Controller design: idempotency, fencing, lock và recovery

### 17.1. Một state machine có thể audit

~~~text
PLANNED
  |
VALIDATING -----> BLOCKED (preflight fails)
  |
LEASED
  |
ACTION_SUBMITTED
  |
OBSERVING
  |           \\
  |            +----> UNKNOWN_ACTION_OUTCOME
  |                         |
  |                       RECONCILE
  |                         |
  |           +-------------+
  v           v
GATES_PASS  GATES_FAIL ----> HOLD/ABORT
  |
WAVE_COMMITTED
  |
NEXT_WAVE / DONE
~~~

**Không** bỏ qua `UNKNOWN_ACTION_OUTCOME` chỉ vì call đến Kubernetes/JMX/operator API timeout. Tác vụ có thể đã được thực hiện; phải query actual node state/action ID trước khi thử lại.

### 17.2. Lock/lease ở phạm vi cluster hoặc maintenance domain

Controller cần cơ chế loại trừ đồng thời:

~~~text
Lease key = cluster-id + maintenance-domain
Lease owner = rollout-run-id
Fencing epoch = monotonically increasing number
TTL/renewal = bounded and observed
~~~

Nếu một controller mất lease, nó phải **ngừng phát action mới**; nếu lease được cấp cho controller khác, actor cũ không được “phục hồi” và tiếp tục dựa trên state đã cũ. Lease phải được enforce **ở execution boundary** hoặc có fencing token; chỉ kiểm lock trong bộ nhớ không đủ chống split-brain.

### 17.3. Checkpoint trước/sau side effect

~~~text
Persist ACTION_INTENT(node=A, config_hash=X)
  |
Call restart via owner API
  |
API call times out?
  |
Read observed process/pod/node status
  |
Match expected action outcome and identity?
  |
Persist ACTION_VERIFIED or UNKNOWN/HOLD
~~~

Nếu checkpoint chỉ ghi sau khi restart, controller crash ở khoảng giữa có thể không biết đã restart A hay chưa. Nếu retry blindly, A có thể bị restart lần thứ hai trong khi vừa quay lại phục vụ.

### 17.4. Retry cần phân biệt lỗi transient và permanent

| Error | Có retry không? | Trước khi retry |
|---|---|---|
| Metrics API timeout | Có giới hạn | Kiểm nguồn khác, không coi là PASS |
| Operator action submission timeout | **Không replay mù** | Query action ID/controller state/node state |
| Cassandra node down after restart | Chỉ với owner diagnosis | Kiểm logs/data/host ID trước khi restart lại |
| Wrong node identity/config digest | **Không** | STOP và kiểm inventory |
| `InvalidQuery` do schema chưa migration | **Không** | Sửa DDL/order of operations |
| `Unavailable` ở required CL | Không che bằng hạ CL | Restore replicas/availability |
| Repair task failure | Runbook chuyên biệt | Kiểm token/partial streaming/resource/disk |
| Host disk full | **Không** | STOP và recovery |

Backoff/jitter dùng cho các API đọc/poll transient; side-effect retries phải có **idempotency/fencing semantics** rõ và bằng chứng actual state.

### 17.5. Deadline và cancellation

Mỗi wave có:

- `action_deadline`: Thời hạn thao tác điều khiển bắt đầu/hoàn tất.
- `node_ready_deadline`: Thời hạn node vào trạng thái có thể phục vụ.
- `data_cl_deadline`: Thời hạn CQL ở required CL và correctness probe đạt.
- `performance_deadline`: Thời hạn SLO, queues/resource quay lại vùng chấp nhận.
- `maintenance_window_deadline`: Mốc cuối được phép bắt đầu wave mới.

Hết một deadline → **HOLD/ABORT**, không tự giả định thành công hoặc vội restart node tiếp theo. Cancellation có thể chỉ dừng việc **lên lịch wave mới**; một restart/repair đã bắt đầu có thể cần đợi/quản lý kết thúc, không phải lúc nào có thể hủy giữa chừng an toàn.

### 17.6. Đừng lạm dụng optimistic controller retries

Một hệ reconcile loop chạy mỗi 2 giây có thể gọi restart 30 lần nếu nó không lưu `action_id`/observed transitions. Design:

~~~text
Desired state: target config installed on node A
Observed state: node A is restarting
Action record: action-17 already submitted

Controller decision:
  WAIT / OBSERVE,
  not SUBMIT new action.
~~~

**Goal:** Tự động hóa phải giống một người vận hành thận trọng có sổ nhật ký, không phải vòng lặp “nếu chưa xanh thì bấm nút lần nữa”.

## 18. Lab A — CQL: tạo sentinel và kiểm data gate

### 18.1. Mục tiêu và điều kiện

Lab này minh họa cách chuẩn bị **một giá trị tham chiếu có thể kiểm sau rollout**, dùng full primary key và CL. Nó **không** restart node và không thử fault thật.

Yêu cầu:

- Cassandra 4.1/5.0 **một node lab**, `cqlsh` được phép tạo namespace riêng.
- Không dùng production keyspace, không xóa/truncate dữ liệu người khác.
- RF1/`ONE` chỉ đủ dạy CQL/gate, **không** bảo đảm zero-downtime rolling restart.
- Node DC thực xác minh bằng `system.local`.
- Tránh nhầm dữ liệu sentinel với chứng cứ mọi partitions đều đúng; đây là một **probe có phạm vi**.

### 18.2. Tạo keyspace và bảng theo khóa phân vùng

~~~sql
CREATE KEYSPACE IF NOT EXISTS rollout_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS rollout_lab.probe_by_tenant (
  tenant_id text,
  probe_id uuid,
  state text,
  revision int,
  updated_at timestamp,
  PRIMARY KEY ((tenant_id), probe_id)
);

CONSISTENCY ONE;
~~~

Trong lab, `tenant_id` là partition key, `probe_id` là clustering key. Tất cả queries dùng full primary key, không `ALLOW FILTERING` hoặc `COUNT(*)` toàn bảng. Trong nhiều DC production, keyspace nên dùng `NetworkTopologyStrategy` và RF phù hợp; **không** áp `SimpleStrategy RF1` cho hệ cần HA.

### 18.3. Seed một row biết trước

~~~sql
INSERT INTO rollout_lab.probe_by_tenant
  (tenant_id, probe_id, state, revision, updated_at)
VALUES (
  'tenant-lab',
  11111111-1111-1111-1111-111111111111,
  'READY',
  7,
  '2026-11-21T00:00:00Z'
);
~~~

**Expected:** Một row có `state=READY` và `revision=7`. Không dùng `INSERT` này trong automation production vì nó là mutation; với production nên dùng một sentinel record do team sở hữu và policy kiểm tra giá trị riêng, hoặc read-only known keys/strong consistency validation.

### 18.4. Read-only data gate

~~~sql
SELECT state, revision, updated_at
FROM rollout_lab.probe_by_tenant
WHERE tenant_id='tenant-lab'
  AND probe_id=11111111-1111-1111-1111-111111111111;
~~~

Một gate đúng phải assert **giá trị**, không chỉ “SELECT không exception”. Ví dụ:

~~~text
query executed               = true
row exists                   = true
state                        = READY
revision                     = 7
consistency level            = ONE  (RF1 lab)
latency / timeout            = within budget
~~~

Nếu query thành công nhưng row rỗng hoặc revision=6, **data oracle FAIL**. Không tiếp tục wave để “xem node kế tiếp có tự sửa không”.

### 18.5. Kiểm schema và keyspace replication

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name='rollout_lab';

SELECT keyspace_name, table_name
FROM system_schema.tables
WHERE keyspace_name='rollout_lab';

SELECT cluster_name, data_center, host_id,
       release_version, schema_version
FROM system.local;
~~~

Đây là read-only probes. `system.local` chỉ cho **coordinator node hiện tại**; muốn kiểm per-node schema versions, đọc từ nhiều node hoặc `nodetool describecluster` trong multi-node cluster.

### 18.6. Tại sao lab RF1 không thể thử “safe one-node restart”?

RF1 yêu cầu một replica còn sống để đọc/ghi ở ONE. Nếu node duy nhất restart, **0 replicas** còn phục vụ. Không có thao tác quiesce nào biến RF1 thành HA tự động. Bài lab ở đây chỉ chứng minh cách viết CQL/readiness probes. Phép thử rolling restart chịu lỗi đòi cluster thật có RF/CL headroom và data manifest phù hợp.

### 18.7. Canary trên RF3 phải kiểm nhiều sentinel keys

Trong cluster NTS RF3:

~~~text
Probe P1 -> natural replica set {A,B,C}
Probe P2 -> natural replica set {B,D,E}
Probe P3 -> natural replica set {A,E,F}
~~~

Một query sentinel P1 ở `LOCAL_QUORUM` PASS **không chứng minh P2/P3** vẫn phục vụ nếu restart B. Runbook nên có probe coverage theo token ranges/critical tenants và driver routing, không dùng một `SELECT system.local`.

## 19. Lab B — Java Driver 4.x: readiness probe có xác minh dữ liệu

### 19.1. Mục tiêu

Chương trình Java 17 đọc một sentinel với **normal CL chỉ định**, kiểm schema agreement giữa các nodes UP (ở phạm vi driver thấy), expected metadata và expected row/value. Nó **không** khởi động lại node, không chạy DDL, không ghi dữ liệu production và không thay status rollout. Các tín hiệu metrics/compaction/topology phải do controller bổ sung.

Ví dụ dependency Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.apache.cassandra:java-driver-core:4.18.1")
}
~~~

Với driver 4.17.x dùng group/version được hỗ trợ tương ứng; không trộn các driver artifacts của nhiều major versions.

### 19.2. Chương trình Java 17 đầy đủ

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.UUID;

public final class CassandraRolloutProbe {
    private CassandraRolloutProbe() {}

    private static final String KEYSPACE = "rollout_lab";
    private static final String TABLE = "probe_by_tenant";
    private static final UUID PROBE_ID = UUID.fromString(
        "11111111-1111-1111-1111-111111111111");

    public static void main(String[] args) {
        if (args.length != 3) {
            System.err.println(
                "Usage: CassandraRolloutProbe " +
                "<contact-host> <local-dc> <ONE|LOCAL_QUORUM>");
            System.exit(2);
        }

        String contactHost = args[0];
        String localDc = args[1];
        DefaultConsistencyLevel consistency =
            DefaultConsistencyLevel.valueOf(args[2]);

        // Với RF1 lab: ONE.
        // Với RF3 production-like staging: LOCAL_QUORUM.
        // KHÔNG hạ CL của ứng dụng thật để làm gate xanh.
        if (consistency != DefaultConsistencyLevel.ONE
                && consistency != DefaultConsistencyLevel.LOCAL_QUORUM) {
            throw new IllegalArgumentException(
                "Unsupported CL in this example");
        }

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress(contactHost, 9042))
                .withLocalDatacenter(localDc)
                .build()) {

            boolean schemaAgreement =
                session.checkSchemaAgreement();
            if (!schemaAgreement) {
                throw new IllegalStateException(
                    "Schema disagreement among currently UP nodes");
            }

            boolean tableKnown = session.getMetadata()
                .getKeyspace(CqlIdentifier.fromCql(KEYSPACE))
                .flatMap(ks -> ks.getTable(
                    CqlIdentifier.fromCql(TABLE)))
                .isPresent();

            if (!tableKnown) {
                throw new IllegalStateException(
                    "Expected table missing from driver metadata");
            }

            PreparedStatement read = session.prepare(
                "SELECT state, revision " +
                "FROM rollout_lab.probe_by_tenant " +
                "WHERE tenant_id = ? AND probe_id = ?");

            BoundStatement request = read.bind(
                    "tenant-lab", PROBE_ID)
                .setConsistencyLevel(consistency)
                .setIdempotent(true)
                .setTimeout(Duration.ofSeconds(3));

            long started = System.nanoTime();
            ResultSet result = session.execute(request);
            Row row = result.one();
            double elapsedMs =
                (System.nanoTime() - started) / 1_000_000.0;

            if (row == null
                    || !"READY".equals(row.getString("state"))
                    || row.getInt("revision") != 7) {
                throw new IllegalStateException(
                    "Sentinel data oracle mismatch");
            }

            System.out.printf(
                "READINESS_PASS dc=%s cl=%s elapsed_ms=%.3f%n",
                localDc, consistency, elapsedMs);
        }
    }
}
~~~

### 19.3. Cách chạy trong lab

~~~bash
# DC thực xem bằng SELECT data_center FROM system.local
# Lệnh ví dụ khi Java class đã được compile/test:
java example.CassandraRolloutProbe 127.0.0.1 datacenter1 ONE
~~~

Kỳ vọng:

~~~text
READINESS_PASS dc=datacenter1 cl=ONE elapsed_ms=<measured>
~~~

Số `elapsed_ms` là thực tế khi chạy, không có giá trị cố định. Nếu node không truy cập được, metadata/table thiếu, CL không đáp ứng, row rỗng hoặc revision khác, chương trình phải **fail** với exception. Không nên chỉ kiểm result row tồn tại rồi bỏ qua revision.

### 19.4. Điều cần thay trước khi dùng với RF3 staging

1. Tạo keyspace/test sentinel đúng RF3 trong một dedicated multi-node cluster.
2. Giữ known-key/expected values phù hợp, tránh ghi đè production rows.
3. Dùng `LOCAL_QUORUM` khi hợp đồng ứng dụng yêu cầu.
4. Chạy từ mỗi application DC và nhiều token/partition probes.
5. Kết hợp ring/driver pool/host metrics/streaming/GC/SLO để ra gate hoàn chỉnh.
6. Dùng account/role có permission tối thiểu và TLS/auth đúng môi trường.

**Không lấy chương trình này làm readiness daemon sẵn cho production**: nó tạo một `CqlSession` mới mỗi lần chạy, có chi phí connection/auth/metadata. Trong hệ thật, dùng session dài hạn ở service hoặc một diagnostic controller rate-limited, tránh hàng trăm pods cùng mở CQL sessions mỗi giây.

### 19.5. Vì sao không dùng `ExecutionInfo.isSchemaInAgreement()` của SELECT?

Trong Java Driver, cờ `isSchemaInAgreement()` có ý nghĩa liên quan schema-changing DDL; một SELECT thường có thể báo true mặc định. Đây không phải gate schema độc lập. Dùng `session.checkSchemaAgreement()` và driver metadata/server metadata đúng chỗ, rồi xác minh data oracle ở CL phù hợp.

## 20. Lab C — Java 17 kiểm batch size từ các replica sets giả lập

### 20.1. Mục tiêu

Đây là một **pure Java simulation**, không kết nối Cassandra và không restart node. Nó minh họa một kiểm tra điều kiện cần: khi xét candidate wave, những natural replica sets được khai báo có còn đủ live replicas để đáp ứng quorum không?

### 20.2. Chương trình hoàn chỉnh

~~~java
package example;

import java.util.List;
import java.util.Set;

public final class ReplicaBudgetLab {
    private ReplicaBudgetLab() {}

    record ReplicaSet(
        String name, Set<String> replicas, int requiredAcks) {}

    static boolean safeToRestart(
            Set<String> candidates,
            Set<String> healthyNodes,
            List<ReplicaSet> criticalRanges) {

        if (candidates.isEmpty() || criticalRanges.isEmpty()) {
            return false; // Missing plan/coverage -> fail closed
        }
        if (!healthyNodes.containsAll(candidates)) {
            return false; // Candidate already degraded: reconcile
        }

        for (ReplicaSet range : criticalRanges) {
            if (range.replicas().isEmpty()
                    || range.requiredAcks() <= 0
                    || range.requiredAcks() >
                       range.replicas().size()) {
                return false;
            }

            long liveAfterWave = range.replicas().stream()
                .filter(healthyNodes::contains)
                .filter(node -> !candidates.contains(node))
                .count();

            if (liveAfterWave < range.requiredAcks()) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        Set<String> healthy =
            Set.of("A", "B", "C", "D", "E", "F");

        List<ReplicaSet> ranges = List.of(
            new ReplicaSet(
                "range-X", Set.of("A", "B", "C"), 2),
            new ReplicaSet(
                "range-Y", Set.of("B", "D", "E"), 2),
            new ReplicaSet(
                "range-Z", Set.of("A", "B", "F"), 2)
        );

        System.out.println(
            "Restart A only: " +
            safeToRestart(Set.of("A"), healthy, ranges));

        System.out.println(
            "Restart A+B: " +
            safeToRestart(Set.of("A", "B"), healthy, ranges));

        Set<String> degraded =
            Set.of("A", "B", "D", "E", "F"); // C is DOWN

        System.out.println(
            "Restart A while C down: " +
            safeToRestart(Set.of("A"), degraded, ranges));
    }
}
~~~

Kỳ vọng:

~~~text
Restart A only: true
Restart A+B: false
Restart A while C down: false
~~~

Vì:

- Wave `{A}` để lại ít nhất 2 replicas trên tất cả ranges trong ví dụ.
- Wave `{A,B}` để lại chỉ F trên `range-Z`, nhỏ hơn quorum=2.
- Khi C đang DOWN, restart A để lại chỉ B trên `range-X`.

### 20.3. Giới hạn nghiêm trọng của mô phỏng

Đây **không phải production scheduler**. Nó:

- Giả định toàn bộ `criticalRanges` đã được liệt kê và replica map chính xác.
- Giả định các nodes trong `healthyNodes` thực sự đáp ứng CQL đúng deadline.
- Chưa xét nhiều DC, `EACH_QUORUM`/`SERIAL`/transient replicas, CL theo query family.
- Không xét disk/GC/streaming/compaction/backpressure.
- Không có lease, checkpoint, replay protection hoặc health windows.
- Không quan sát errors/data oracle hoặc driver routing.

Một số logical ranges trong lab **không** chứng minh toàn cluster an toàn. Trong controller thật phải dùng nguồn metadata đáng tin cậy, đối chiếu current token/replica placement cho các keyspaces có SLO, rồi kiểm cả ba budgets. **Kết quả `true` ở Java simulation chỉ là “pass kiểm đếm đã mô phỏng”**.

## 21. Kiểm thử controller bằng dry-run và fault simulation

### 21.1. Ba lớp test khác nhau

| Lớp | Mục tiêu | Chạy ở đâu? |
|---|---|---|
| Unit/pure simulation | Chọn wave, tính replica budget, state transitions | CI, không kết nối Cassandra |
| Integration với fake operator/JMX | Checkpoint/retry/lease/action timeout | Test harness isolated, không restart thật |
| Multi-node Cassandra staging | Quorum/driver/data/performance sau restart/fault | Dedicated RF3/multi-DC cluster có approval |

Không cần **chaos trên production** để chứng minh logic “nếu node C đã DOWN thì không restart A”. Phần lớn safety predicates nên test bằng fixtures deterministic; fault-injection thật chỉ để xác minh các hệ tương tác phân tán vốn không mô phỏng hết được.

### 21.2. Bảng test cases cho từng transition

| Case | Preflight / sự kiện | Expected controller decision |
|---|---|---|
| T01 | All 3 replicas UP, RF3/LQ, batch={A} | `GO` nếu resource/business gates PASS |
| T02 | C already DN, batch={A}, A/B/C same natural set | `HOLD` |
| T03 | Batch={A,B}, RF3/LQ same set | `HOLD` |
| T04 | RF1/ONE, restart only replica | `HOLD` hoặc explicit approved downtime path |
| T05 | RF3/ALL, restart one replica | `HOLD` khi không được phép outage |
| T06 | Node unexpectedly UJ/UM/UL | `HOLD`, investigate topology |
| T07 | Expected host ID != observed host ID | `ABORT` và identity incident |
| T08 | Action API timeout after restart submitted | `UNKNOWN_ACTION_OUTCOME` → reconcile |
| T09 | Process UP, CQL at required CL fails | `HOLD` |
| T10 | CQL PASS but p99 above SLO 5 windows | `HOLD/ABORT` per deadline |
| T11 | Metrics collector unavailable | `HOLD`, not PASS |
| T12 | Repair starts on natural replica during node restart | `HOLD` competing maintenance |
| T13 | Controller loses lease/fencing epoch | Stop issuing actions; `HOLD` |
| T14 | Canary package hash differs approved hash | `ABORT` |
| T15 | DC2 app uses wrong local DC | `HOLD` DC2 rollout |
| T16 | Operator Task Completed but data oracle wrong | `HOLD` |
| T17 | One wave returns to UN but streaming not settled | `HOLD` until scoped gate |
| T18 | Application error rate rises despite lower p99 success | `HOLD/ABORT` |
| T19 | Controller restarts after checkpoint before action | Reconcile intent; no duplicate restart |
| T20 | Desired wave complete but manual change altered RF | Recompute/abort stale plan |

**Mục tiêu test:** Mỗi gate có test **PASS, FAIL, UNKNOWN**, không chỉ kiểm happy path. Trong thực tế nhiều outages xuất hiện từ nhánh UNKNOWN: command đã chạy nhưng API không trả response.

### 21.3. Fake operator: lost response sau khi action đã chạy

~~~text
Controller persists action-17: restart A
       |
Fake operator receives action-17
       |
Fake operator sets node A = RESTARTING
       |
Response is deliberately dropped
       |
Controller receives timeout
       |
Expected:
  do NOT submit action-18 restart A
  query operator state by action_id
  observe node/process/host_id
  mark ACTION_OBSERVED or HOLD_UNKNOWN
~~~

Đây là một **unit/integration simulation**, không phải lệnh ngắt mạng thật. Nếu action API hỗ trợ idempotency key, dùng **cùng action_id** khi kiểm/retry theo API contract; nếu API không hỗ trợ idempotent submit, phải reconcile state trước và có owner quyết định.

### 21.4. Fake metrics: mất dashboard giữa canary

~~~text
At T0: p99=60ms, error=0.1%
At T1: Cassandra restart finishes, node UN
At T2: metrics scrape fails (no data)

Expected:
  Gate=UNKNOWN
  Do NOT assume p99=0ms or errors=0
  HOLD next wave until evidence returns or escalate
~~~

Không biến null metrics thành 0 rồi so với SLO. Khi exporter restart, counters reset; phải xử lý gaps, reset và sample-count thresholds.

### 21.5. Fault simulation sau node trở lại

Một test multi-node đúng nên có:

1. Tập critical keyspaces với RF3, `LOCAL_QUORUM` và known sentinel keys trên nhiều replica sets.
2. Một node canary được restart trong dedicated staging.
3. Trong lúc canary down, thử probes ở CL yêu cầu; chấp nhận degradation đã nêu trong SLO, không tự đổi CL.
4. Đợi node UN/native transport/driver.
5. Chạy CL probes và oracle; đo p99/retries/hints/streaming/GC.
6. **Chỉ khi các windows ổn định**, cho thử wave kế.
7. Cố ý làm node khác DOWN (trong lab có approval) để xác minh controller khóa concurrency=0.

Nếu fault injection khiến data sai, disk đầy hoặc cluster không thể phục hồi theo runbook, dừng test và giữ evidence, không tiếp tục các waves chỉ để đủ coverage.

### 21.6. Testing với multiple keyspaces

Test ít nhất một keyspace:

- RF1/ONE hoặc RF2/LQ → không có spare replica để restart không gián đoạn.
- RF3/LQ → tối đa một natural replica vắng mặt trong mô hình khỏe.
- RF3/ALL → không mất được replica nếu giữ availability.
- RF5/LQ → có headroom lý thuyết lớn hơn nhưng resource/SLO budgets có thể chặt hơn.
- NTS multi-DC → kiểm riêng local/each/global quorum và application local DC.

Đừng để scheduler tối ưu theo **keyspace dễ nhất** mà bỏ qua một audit/ledger keyspace có CL chặt hơn.

## 22. Observability và dữ liệu quyết định rollout

### 22.1. Dashboard cần cùng timeline

~~~text
Panel 1  Rollout markers: wave start/drain/stop/start/UN/GO/HOLD
Panel 2  Node states by DC/rack/host ID, unexpected DOWN
Panel 3  CQL client errors, timeouts, unavailables by query family/CL
Panel 4  Client p50/p95/p99, completed QPS, request counts
Panel 5  Driver connections/in-flight/retries/speculation
Panel 6  Cassandra read/write/coordinator latency and thread-pool drops
Panel 7  Disk read/write IOPS, await, throughput, free space
Panel 8  JVM heap, GC pauses, CPU, network RTT/errors
Panel 9  Repair/streaming, compaction pending/active/bytes
Panel 10 Sentinel data oracle and schema/metadata readiness
Panel 11 Unknown action outcomes, reconcile age and maintenance lease
~~~

Không dùng các panel rời time ranges để suy nguyên nhân. Ví dụ p99 xấu lúc T2 nhưng dashboard disk I/O đang nhìn T4 sẽ che mất compaction contention.

### 22.2. Nguồn metrics

| Lớp | Nguồn | Dùng để đo |
|---|---|---|
| Controller | Action/checkpoint/lease logs | Thứ tự wave, last successful gate, unknown attempts |
| Cassandra JMX | ClientRequest, Table, Compaction, ThreadPools, Storage | Latency/queue/errors/SSTable/compaction |
| `nodetool` | `status`, `tpstats`, `netstats`, `compactionstats` | Snapshot node/task state |
| Java Driver 4.x | Session/node metrics | Pool state, retries, per-node response |
| Application/API | Traces/business metrics | End-to-end SLO, data oracle, unknown business outcomes |
| Host/kernel | CPU, disk/FS, network, GC logs | Resource contention |
| Kubernetes/operator | Pod statuses, tasks, events | Controller lifecycle và orchestration attempts |

Không trừ p99 server khỏi p99 client để “tính network latency”: percentiles của hai tập mẫu khác nhau **không cộng/trừ** như means. Cần tracing/measurement cùng một request để phân rã.

### 22.3. Counters, gauges và histograms

| Loại | Ví dụ | Cách xử lý |
|---|---|---|
| Counter | Total request timeouts, bytes compacted | `rate`/`increase`, xử lý reset sau node restart |
| Gauge | Pending compaction, disk free, in-flight | Mức hiện tại và slope |
| Histogram/timer | Read latency, GC pauses | Percentiles + sample counts/precision |
| Boolean/state | Node UN, gate pass | Có timestamp và source viewpoint |
| Derived ratio | Error rate, retry amplification | Count với mẫu số rõ và windows đồng nhất |

Một node được restart sẽ reset nhiều counters; không so raw counters trước/sau rồi tuyên bố “timeouts giảm 90%”. Cần rate theo thời gian, error count theo query family và phối hợp timestamps.

### 22.4. Các chỉ số dẫn dắt và chỉ số trễ

**Leading indicators:** pending compaction/flush queues tăng, disk await tăng, driver in-flight/backpressure tăng, retries tăng, GC pause kéo dài, schema disagreement, replica liveness margin thấp.

**Lagging indicators:** p99 vượt SLO, client timeouts, unavailable errors, stale/data oracle mismatch, business processing backlog.

Nếu chờ lagging indicators bùng nổ mới dừng, wave kế có thể đã bắt đầu và làm tình hình tệ hơn. Controller nên có **early HOLD** khi leading trends xấu dù p99 tạm vẫn trong SLO.

### 22.5. Không mở rộng khi số liệu chỉ “đẹp” trên một node

Node vừa restart có thể báo CPU thấp/caches nóng hơn, nhưng các natural replicas còn lại đang gánh traffic và GC/throttling tăng. Gate phải xem **cả cluster và các nodes cùng phục vụ token ranges của canary**, không chỉ canary. Tương tự, app p99 tổng có thể che query family “checkout” bị timeout.

### 22.6. Một bảng dữ liệu minh họa

~~~text
Window  QPS  p99(ms) errors(%) pendingCompaction unexpectedDN  Action
  1    2000     85       0.1        12                0       HOLD
  2    1990     90       0.2        15                0       HOLD
  3    1980    105       0.3        30                0       HOLD
  4    1920    128       0.5        70                0       HOLD
  5    1800    165       1.1       130                0       ABORT
~~~

Số liệu **giả lập**. Dù không có node nào bất ngờ DOWN, throughput giảm và p99/error/backlog tăng → **không đạt steady state**. Không chạy thêm wave để “xong đúng giờ”.

### 22.7. Tín hiệu an toàn phải có nguồn và độ mới

Một snapshot `nodetool status` được cache từ 15 phút trước không có giá trị cho pre-wave gate hiện tại. Mỗi observation nên có:

~~~text
metric_name, source_node, scope, timestamp_utc,
last_successful_scrape, sample_count, freshness_limit,
value, threshold, evaluation_result
~~~

Nếu dữ liệu hết hạn (stale) hoặc từ sai cluster, gate trả `UNKNOWN`. Đừng coi thiếu telemetry là PASS.

## 23. Hai mươi bốn tình huống thường gặp khi tự động hóa rollout

### Ca 1 — Restart hai nodes thuộc cùng natural replica set

**Hiện tượng:** RF3/`LOCAL_QUORUM`, controller chọn A và B trong một wave; partition P có replicas A/B/C.  
**Nguyên nhân:** Giới hạn theo tổng nodes thay vì theo replica set.  
**Xử lý:** **HOLD**, chỉ cho phép wave không làm mất quorum trên mọi affected ranges; giữ một node active mỗi lần nếu chưa chứng minh graph an toàn.

### Ca 2 — Một node đã DN, batch vẫn giữ `maxUnavailable=1`

**Hiện tượng:** C đã DN, plan restart A; A/C là natural replicas của hot partition.  
**Nguyên nhân:** Controller chỉ đếm nodes mà chính nó sẽ làm unavailable, bỏ qua existing failures.  
**Xử lý:** Budget hiện tại bằng 0 cho những candidate nguy hiểm → **HOLD/ABORT**, phục hồi replica trước.

### Ca 3 — RF1 keyspace làm mọi rolling restart thành outage

**Hiện tượng:** Cluster có RF3 keyspace chính nhưng một audit keyspace RF1.  
**Nguyên nhân:** Safety check chỉ xem keyspace chính.  
**Xử lý:** Kiểm **tất cả critical keyspaces/CL**, không tuyên bố zero-downtime rollout; cần planned downtime hoặc thay replication design trước.

### Ca 4 — Node lên `UN` nhưng CQL tại `LOCAL_QUORUM` timeout

**Hiện tượng:** `nodetool status` tốt, nhưng app read/write vẫn timeout.  
**Nguyên nhân khả dĩ:** Replica chậm, CL không đủ, driver routing, streaming/hints/GC/compaction pressure.  
**Xử lý:** **HOLD**, chạy representative CQL/data oracle và resource diagnostics, không tiếp tục wave.

### Ca 5 — Native port 9042 mở nhưng table mới không đọc được

**Hiện tượng:** Kubernetes readiness PASS, Java PREPARE báo `unconfigured table`.  
**Nguyên nhân:** App rollout trước schema migration, metadata stale hoặc một node chưa schema-agreed.  
**Xử lý:** Pause app release, single migration owner, schema agreement + expected definition + Java probe.

### Ca 6 — PDB ngăn một eviction nhưng admin force-delete pod khác

**Hiện tượng:** Một node đang restart, pod khác bị force delete hoặc host crash.  
**Nguyên nhân:** PDB không kiểm được mọi loại disruption và không phải Cassandra replica budget.  
**Xử lý:** **ABORT** waves mới, tái đánh giá gossip/natural replicas; không dựa vào PDB làm bằng chứng CL.

### Ca 7 — Operator Task Completed nhưng node host ID đã đổi

**Hiện tượng:** Pod được recreate, controller gọi là restart thành công nhưng host ID/token/volume mismatch.  
**Nguyên nhân:** Unintended replacement/missing PVC/identity drift.  
**Xử lý:** **STOP** topology incident, xác minh token placement/streaming; không bắt đầu wave kế.

### Ca 8 — `nodetool drain` được chạy như health check

**Hiện tượng:** Cron job gọi drain mỗi khi test node readiness.  
**Nguyên nhân:** Nhầm lệnh thay đổi trạng thái với lệnh quan sát.  
**Xử lý:** Bỏ drain khỏi probes; chỉ chạy ngay trước graceful shutdown được owner phê duyệt.

### Ca 9 — Drain xong, operator restart API timeout

**Hiện tượng:** Node bị drained, orchestration call không trả response, controller đi tiếp.  
**Nguyên nhân:** Không có UNKNOWN_ACTION_OUTCOME/reconciliation.  
**Xử lý:** **HOLD**, xác minh process/pod/operator action, khôi phục node rồi mới xét wave kế.

### Ca 10 — Hai automation systems cùng quản lý một node

**Hiện tượng:** cass-operator đang rolling restart, external script cũng gọi service stop.  
**Nguyên nhân:** Không có single lifecycle owner/lease.  
**Xử lý:** Một controller sở hữu action, actor còn lại chỉ quan sát; thiết lập maintenance lock và fencing.

### Ca 11 — Cassandra version mới dùng unsupported config ở node cũ

**Hiện tượng:** Canary node mới PASS nhưng schema/feature option được bật khi cluster vẫn mixed-version.  
**Nguyên nhân:** Không kiểm compatibility phase.  
**Xử lý:** HOLD upgrade, quay về compatible feature set theo release-specific plan, không kích hoạt on-disk format không thể rollback mù.

### Ca 12 — Chọn `fast` để rút ngắn cass-operator rolling restart

**Hiện tượng:** Nhiều nodes/rack bị restart song song, CL/latency mất headroom.  
**Nguyên nhân:** Fast/force flags hoặc operator config bỏ qua safety assumptions.  
**Xử lý:** Dừng/giảm concurrency theo runbook phiên bản operator; không bật force khi cluster degraded.

### Ca 13 — Repair nặng chạy song song với restart natural replica khác

**Hiện tượng:** Nodes còn UP nhưng p99 tăng mạnh, CL responses timeout.  
**Nguyên nhân:** Disk/GC/streaming capacity thấp hơn quorum logic.  
**Xử lý:** HOLD restart, điều phối resource budgets/repair windows, không làm cả hai cùng lúc khi thiếu headroom.

### Ca 14 — P99 nhìn đẹp hơn nhưng HTTP 504 tăng

**Hiện tượng:** p99 của success histogram giảm, timeout count tăng.  
**Nguyên nhân:** Slow requests đã bị loại khỏi samples, tạo false positive.  
**Xử lý:** HOLD/ABORT theo error budget, báo p99 + request count + timeouts + retries cùng nhau.

### Ca 15 — Controller nhận metrics null và coi bằng 0

**Hiện tượng:** Scrape bị lỗi, dashboard hiển thị 0 errors, wave auto-advances.  
**Nguyên nhân:** Không phân biệt `NO_DATA` với value 0.  
**Xử lý:** Status `UNKNOWN` → HOLD; yêu cầu nguồn telemetry mới/freshness predicate.

### Ca 16 — Restart xong node vẫn đang commitlog replay/cold GC

**Hiện tượng:** `UN` nhanh, app p99 vẫn cao, GC/disk await dao động.  
**Nguyên nhân:** Time-to-process-up khác performance recovery.  
**Xử lý:** Soak qua nhiều rolling windows, kiểm resource/backlog trước khi wave kế.

### Ca 17 — Controller mất lock nhưng vẫn chạy bằng plan cache

**Hiện tượng:** Lease hết hạn, actor khác nhận quyền điều phối, actor cũ tiếp tục restart.  
**Nguyên nhân:** Lease không fencing tại execution boundary.  
**Xử lý:** Mọi action yêu cầu valid fencing epoch/owner; lease loss → STOP new actions.

### Ca 18 — Retry restarter sau API 504 làm node restart hai lần

**Hiện tượng:** Action đầu đã thực hiện, response mất; script gửi action mới.  
**Nguyên nhân:** Không có persistent action ID/observed-state reconciliation.  
**Xử lý:** Reconcile pod/process/node/action status trước khi retry, giữ cùng intent identity.

### Ca 19 — Tăng wave size vì cần kết thúc trước deadline

**Hiện tượng:** Rollout chậm do drain/repair, operator tăng maxUnavailable gần cuối maintenance window.  
**Nguyên nhân:** Xem deadline là lý do nới safety budget.  
**Xử lý:** Hết window → **HOLD, schedule lại**, không vượt CL/replica/resource gates.

### Ca 20 — Java app deployment tăng speculative retries

**Hiện tượng:** Cassandra server thấy physical requests tăng gấp ba dù HTTP logical QPS không đổi.  
**Nguyên nhân:** Driver retry/speculative config của release mới.  
**Xử lý:** Canary app rollback/adjust config, đo pool/in-flight/retries/CL; không chỉ nhìn success rate.

### Ca 21 — Hai DC có schema khác, nhưng gate chỉ nhìn dc1

**Hiện tượng:** Service dc1 PASS, dc2 PREPARE/SELECT lỗi sau rollout.  
**Nguyên nhân:** Chỉ dùng một `system.local`/driver vantage point.  
**Xử lý:** Per-DC schema agreement/metadata/CQL checks, không mở traffic dc2 khi gate chưa đạt.

### Ca 22 — Node replacement bị xem như restart thường

**Hiện tượng:** Node mới có token/host ID khác và đang streaming; script tiếp tục rolling waves.  
**Nguyên nhân:** Không so inventory/volume/token identity.  
**Xử lý:** STOP, chuyển sang replace/bootstrap/repair runbook, kiểm ownership và data coverage.

### Ca 23 — Full repair được tự chạy để “sửa latency”

**Hiện tượng:** p99 xấu, controller chạy full repair, làm disk/network bão hòa thêm.  
**Nguyên nhân:** Gộp mọi Cassandra issue thành missing data/repair.  
**Xử lý:** Điều tra read path/compaction/GC/driver trước; repair chỉ khi có data synchronization plan và resource budget.

### Ca 24 — Rollout dừng sau wave 2, chạy lại từ wave 0 hôm sau

**Hiện tượng:** Nodes A/B đã chạy target binary, controller không lưu checkpoint, restart lại chúng không cần thiết.  
**Nguyên nhân:** Thiếu durable run/wave/action state và config hash.  
**Xử lý:** Resume bằng reconciliation: xác minh version/config/host IDs/gates hiện tại, chỉ thực hiện steps chưa verified, không bỏ qua mixed-version constraints.

## 24. Runbook GO / HOLD / ABORT / ROLLBACK

### 24.1. Bốn trạng thái quyết định khác nhau

| Quyết định | Ý nghĩa | Hành động được phép |
|---|---|---|
| **GO** | Đủ evidence để thực hiện **wave đã được chọn** | Chỉ action trong wave, tối đa concurrency budget |
| **HOLD** | Có vấn đề có thể phục hồi, dữ liệu/gate chưa đủ | Dừng wave mới, giữ quan sát và deadline |
| **ABORT** | Guardrail vi phạm hoặc không thể tiếp tục an toàn | Dừng rollout mới, activate incident/recovery owner |
| **ROLLBACK** | Quay lại trạng thái được phê duyệt **nếu tương thích** | Chỉ sau đánh giá khả năng rollback từng loại thay đổi |

**HOLD** không có nghĩa đang hủy các action side-effect đã được gửi; có thể cần đợi restart/streaming kết thúc an toàn. **ABORT** không có nghĩa giết Cassandra ngay lập tức. **ROLLBACK** không phải thao tác luôn an toàn; major-version/data format/schema destructive changes có thể không quay lui được.

### 24.2. P0 — Ra quyết định trước chạy

- Có approval và quyền truy cập đúng cluster.
- Node inventory/host IDs/tokens/storage IDs được chốt.
- Keyspaces/CL/SCL/critical query families đã liệt kê.
- RF/DC/rack/replica-set safety được kiểm trên topology quan sát hiện tại.
- Không có node unexpected DN/UJ/UL/UM; degraded cluster cần explicit exception policy.
- Có resource headroom, backup/restore test và rollback strategy phù hợp phiên bản.
- Có một maintenance owner/lease và change digest.
- Có telemetry đủ thời gian, known-key CQL probes, business error budget.
- Có canary, wave plan và hard-stop rules.

**Nếu không trả lời được một điều kiện bắt buộc**, trạng thái là HOLD, không chọn GO bằng “thử một lần xem sao”.

### 24.3. P1 — Pre-wave safe-to-act

~~~text
function safe_to_act(candidate_wave):
  assert approved run_id and immutable change_digest
  assert valid, exclusive lease/fencing epoch
  assert observed host IDs/tokens match manifest
  assert current topology snapshot fresh
  assert no unknown previous action remains
  assert every critical replica set will retain required CL
  assert no conflicting repair/streaming/maintenance
  assert per-node/per-DC resource headroom
  assert app error/latency/QPS baseline within policy
  assert before-window deadline and rollback owner valid
  return GO if all true; else HOLD/ABORT according to guardrail
~~~

Đây là **pseudocode**, không phải lệnh chạy. Kết quả `GO` có hiệu lực cho **một candidate wave tại một snapshot**; nếu node bất ngờ DOWN trong 30 giây sau, executor phải kiểm lại và/hoặc hủy action chưa bắt đầu.

### 24.4. P2 — Thực hiện có checkpoint

~~~text
persist INTENT(action_id, node_ids, expected_state, digest)
    |
submit action to single lifecycle owner
    |
observe action state and Cassandra node health
    |
ACTION COMPLETE? -- no --> HOLD/RECONCILE with deadline
    |
yes
    |
run post-wave CL/data/driver/resource gates
    |
ALL PASS? -- no --> HOLD / ABORT / rollback assessment
    |
yes
    |
persist WAVE_VERIFIED and release maintenance slot
~~~

Phải record outcome trước khi giải phóng slot. Nếu controller crash sau action nhưng trước checkpoint, reconciler phải **đọc actual state**, không gửi lại side effect theo mặc định.

### 24.5. P3 — Tình huống HOLD

HOLD khi:

- Một node chưa UN/native transport chưa ready nhưng vẫn trong recovery deadline.
- Driver metadata chưa hội tụ hoặc schema agreement còn đang propagating sau DDL hợp lệ.
- Repair/compaction backlog tăng nhưng chưa vượt hard-stop, cần quan sát.
- App p99/error chưa đạt **số windows liên tiếp** cần thiết.
- Scraper/JMX/metric store không khả dụng, thiếu bằng chứng.
- Node khác bất ngờ DN; controller cần tính lại replica budget.
- Operator action status không rõ sau timeout.

Trong HOLD, **không mở wave mới**, thông báo owner và tiếp tục đo có giới hạn. Hết deadline hoặc trạng thái xấu hơn → ABORT/escalation.

### 24.6. P4 — Điều kiện ABORT tức thời

ABORT khi:

- Mất quorum tại CL được cam kết trên critical replica sets.
- Một host ID/token/storage identity không còn đúng expected.
- Data oracle trả sai value/version, có dấu hiệu data corruption hoặc unexpected keyspace/table drop.
- Disk full/read-only filesystem, commitlog failures, OOM lặp hoặc compaction failures nghiêm trọng.
- Error/timeout/p99 vượt hard SLO/error budget và đang tác động khách hàng.
- Controller lease/fencing bị mất hoặc phát hiện actor khác cùng thay lifecycle.
- Runbook đang nhắm sai cluster/environment.
- Unknown action outcome bị duplicate execution không thể reconcile an toàn.
- Recovery/rollback có nguy cơ phá compatibility hoặc dữ liệu mà chưa có owner.

**Không dùng “thử thêm wave cho nhanh” như giải pháp xử lý ABORT.** Bảo toàn evidence và chuyển incident ownership rõ ràng.

### 24.7. P5 — Rollback decision tree

~~~text
Change failed / stop gate triggered
            |
Is original binary/config/schema/data state still compatible?
            /                           \\
          YES                            UNKNOWN/NO
           |                               |
  Rollback plan reviewed               HOLD + SME review
           |                               |
  Can we keep required CL through it?  Forward-fix or restore
           |                           under dedicated runbook
   YES ----+---- NO
    |            |
 Execute      Planned downtime/
 one-node     alternate recovery
 guarded      decision
 rollback
    |
 Verify CL/data/SLO again
~~~

Một rollback trên node đã nâng major binary có thể **không được phép** khi storage format/feature flags đã thay. Với schema drop/data migration, “rollback DDL” không tự khôi phục rows. Vì thế mỗi change type cần *reversible?* assessment từ preflight.

### 24.8. P6 — Tiêu chuẩn đóng rollout

~~~text
All planned nodes:
  target artifact/config digest matches
  expected host ID/tokens/volume and DC/rack
  serving CQL native transport

All critical services:
  required consistency level probes PASS
  expected data/schema contract PASS
  app p95/p99/errors/retries within SLO
  repair/streaming/compaction resource stable

Controller:
  no unknown action/outstanding restart
  all waves checkpointed
  lease released correctly
  report and audit trail stored
~~~

Không đóng khi vẫn còn `UNKNOWN_ACTION_OUTCOME` hoặc node A trạng thái `DN` được giải thích bằng “hôm sau sẽ xử lý” mà không có owner/ticket và service risk explicit. Một rollout **partially completed/held** là kết quả hợp lệ cần báo trung thực.

### 24.9. Mẫu incident/handoff report

~~~text
RUN_ID:
CHANGE_ID / APPROVER / WINDOW_UTC:
CLUSTER_ID / ENVIRONMENT:
SOURCE_VERSION / TARGET_VERSION / ARTIFACT_DIGEST:
KEYSPACE_REPLICATION_AND_CL_CONTRACT:
APP_DRIVER_VERSIONS_AND_LOCAL_DCS:
NODE_INVENTORY_HOST_IDS_TOKENS_RACKS:
CONTROLLER_LEASE_AND_FENCING_EPOCH:
CANARY_NODE / RESULT:
WAVES_PLANNED / WAVES_VERIFIED / WAVE_IN_PROGRESS:
LAST_NODE_ACTION_ID / OBSERVED_STATE:
UNEXPECTED_DOWN_NODES / JOINING / STREAMING:
SCHEMA_AGREEMENT_BY_DC:
KNOWN_KEY_DATA_ORACLE_BY_QUERY_FAMILY:
CLIENT_P99_ERROR_TIMEOUT_RETRY:
GC_DISK_NETWORK_COMPACTION_BACKLOG:
STOP_REASON / ROLLBACK_DECISION:
UNKNOWN_ACTION_OUTCOMES / RECONCILIATION:
GO/HOLD/ABORT/ROLLBACK_FINAL_STATE:
NEXT_OWNER / NEXT_REVIEW_UTC:
~~~

Không ghi password, TLS private keys, raw tenant/order IDs hay unredacted query bindings vào logs. Dùng host IDs/opaque correlation IDs trong hệ thống nội bộ có phân quyền.

## 25. Checklist thực thi và code review

### 25.1. Nhận diện và phạm vi

- [ ] Đã xác nhận đúng cluster/environment và maintenance authorization.
- [ ] Có manifest pin binary/config/image checksum, không dùng mutable tag `latest`.
- [ ] Node host IDs/tokens/DC/racks/storage identities được đối chiếu.
- [ ] Đã phân biệt restart, replacement, bootstrap, schema migration và repair.
- [ ] Có upgrade compatibility matrix, bao gồm khả năng rollback.
- [ ] Keyspaces, RF, CL, SERIAL/LOCAL_SERIAL (nếu dùng LWT) đã liệt kê.
- [ ] Không bỏ quên keyspace RF1/ALL có yêu cầu availability nghiêm ngặt.
- [ ] Không tự suy một PDB/StatefulSet policy chứng minh quorum.
- [ ] Canaries đại diện hardware/DC/driver/query workload.
- [ ] Có snapshots/backup verification và recovery owner theo loại change.

### 25.2. Concurrency và thứ tự

- [ ] Wave size chỉ là **trần**, có thể giảm về 0 khi degraded.
- [ ] Từng natural replica set/token range giữ required CL nếu candidate nodes unavailable.
- [ ] Existing DN/slow/streaming nodes đã tính vào observed budget.
- [ ] Resource budget gồm CPU/GC, disk/commitlog, network, repair/compaction.
- [ ] SLO error/p99/data oracle là hard gates độc lập.
- [ ] Không chọn wave chỉ dựa trên hostname hoặc rack labels.
- [ ] Không có concurrent lifecycle owner cho cùng node/cluster.
- [ ] Không khởi động wave sau khi previous wave còn UNKNOWN action.
- [ ] Không tăng concurrency để chạy kịp maintenance deadline.
- [ ] Có cooldown/soak windows dựa trên metrics, không chỉ `sleep` cố định.

### 25.3. Node lifecycle

- [ ] `nodetool drain` chỉ được gọi ngay trước planned graceful shutdown, không phải health check.
- [ ] Operator/service manager có owner duy nhất của stop/start.
- [ ] Node process started, gossip UN, native transport và driver routing đều được xác minh.
- [ ] Expected host ID/token/volume không đổi với ordinary restart.
- [ ] Có gate dữ liệu tại required CL, không chỉ `system.local`.
- [ ] Schema agreement/driver metadata/queries được kiểm sau DDL/app rollout.
- [ ] Streaming/repair/compaction/GC/disk queue được quan sát sau startup.
- [ ] Không dùng decommission/removenode/replace để restart thường.
- [ ] Không đưa node UJ/UL/UM hoặc DN vào `READY` chỉ vì pod Running.
- [ ] Không bắt đầu node tiếp theo khi current node chưa verified.

### 25.4. Controller durability

- [ ] Có exclusive lease với renewal/fencing epoch.
- [ ] Có stable `run_id`, `wave_id`, `action_id`, `attempt_id` riêng.
- [ ] Persist intent trước side effect và checkpoint sau verification.
- [ ] Timeout của control API dẫn đến UNKNOWN + reconciliation, không blind retry.
- [ ] Crash/restart controller không chạy lại actions đã submitted.
- [ ] Kiểm stale metrics và source identity trước khi đánh giá PASS.
- [ ] Có max action/wave/recovery durations và maintenance deadline.
- [ ] HOLD/ABORT rules rõ và có manual owner.
- [ ] Operator tasks/status được dùng đúng API version; không bật force/fast mù.
- [ ] Test cả error path và UNKNOWN telemetry/action outcome.

### 25.5. Java application/data readiness

- [ ] Driver `localDatacenter`/TLS/auth/contact points khớp cluster thực.
- [ ] Keyspace/table/column/PK contract được kiểm bằng current metadata/CQL.
- [ ] Có một migration owner, tránh DDL từ mỗi app pod startup.
- [ ] Read/write CL đúng với production; không hạ xuống ONE chỉ để pass.
- [ ] Known-key sentinel oracle kiểm row value/revision, không chỉ empty exception.
- [ ] Probes bao phủ critical token ranges/query families/DCs theo kế hoạch.
- [ ] P95/p99 có sample count, error/timeout/retry counts cùng dashboard.
- [ ] Driver retries/speculation/pool in-flight không tăng bất thường.
- [ ] Có kiểm cho LWT unknown outcomes nếu app dùng conditional writes.
- [ ] Không mở traffic full-scale khi cache/GC/compaction chưa ổn.

### 25.6. Bảo mật, an toàn và báo cáo

- [ ] Runtime actor có least-privilege access, không lộ JMX/CQL passwords.
- [ ] Không chỉnh `system_schema`, token ownership hoặc Paxos internals thủ công.
- [ ] Không chạy destructive repair/compaction/drop/truncate để chữa lỗi rollout mù.
- [ ] Không inject fault/restart trên production ngoài approved window.
- [ ] Có hard stop khi disk full, data oracle sai, mất quorum, identity drift.
- [ ] Ghi UTC timestamps, decision evidence và source freshness.
- [ ] Có khả năng report **PARTIAL/HOLD** chứ không ép `COMPLETED`.
- [ ] Có người nhận bàn giao cho unresolved nodes/unknown actions.
- [ ] Runbook rollback được kiểm theo phiên bản, không giả định binary downgrade.
- [ ] Các lab Java/CQL chỉ minh họa; production controller phải QA và thử staging.

## 26. Câu hỏi tự đánh giá và gợi ý đáp án

**Câu 1.** Tại sao triển khai đồng thời lên tất cả Cassandra nodes nguy hiểm?  
**Gợi ý:** Có thể làm mất required CL/quorum, streaming/repair/GC cùng quá tải và không có canary.

**Câu 2.** “Rolling deployment” có buộc mỗi wave chứa một node không?  
**Gợi ý:** Không; wave size phụ thuộc change type/replica/resource/business budgets, nhưng một node là baseline bảo thủ.

**Câu 3.** Vì sao một node mỗi lần vẫn có thể gây outage?  
**Gợi ý:** RF1, RF2/LQ, RF3/ALL hoặc một replica khác DOWN/saturating.

**Câu 4.** RF3 `LOCAL_QUORUM` cần bao nhiêu full replicas trả lời trong cùng DC?  
**Gợi ý:** Hai trên ba theo mô hình full replicas.

**Câu 5.** RF3/`ALL` có thể restart một natural replica mà vẫn đạt ALL trên partition đó không?  
**Gợi ý:** Không, nếu không có planned outage/đổi hợp đồng.

**Câu 6.** RF5/`LOCAL_QUORUM` cần bao nhiêu ACK?  
**Gợi ý:** Ba full replicas trong DC đó.

**Câu 7.** Tại sao concurrency không thể tính chỉ từ tổng 100 nodes?  
**Gợi ý:** Mỗi partition có một natural replica set nhỏ hơn; hai nodes bất kỳ có thể cùng thuộc replica set.

**Câu 8.** Điều kiện toán học nào cần thỏa để wave giữ `LOCAL_QUORUM`?  
**Gợi ý:** Live natural replicas còn lại của **mỗi** partition/DC ít nhất `floor(RF/2)+1`.

**Câu 9.** Một node đã DOWN trước rollout phải được tính thế nào?  
**Gợi ý:** Trừ khỏi observed availability budget trước khi chọn wave.

**Câu 10.** `maxUnavailable: 1` trong Kubernetes có tự bảo đảm Cassandra quorum không?  
**Gợi ý:** Không; PDB là disruption guard, không biết natural replica sets và CL.

**Câu 11.** Vì sao rack anti-affinity không thay được replica-set analysis?  
**Gợi ý:** Scheduler labels/snitch/token assignment có thể không trùng, vnodes tạo overlap.

**Câu 12.** Một wave có thể chạy đồng thời với full repair trên natural replica khác không?  
**Gợi ý:** Chỉ khi resource/replica/SLO proof cho phép; mặc định tránh chồng maintenance nặng.

**Câu 13.** “Node `UN`” chứng minh điều gì?  
**Gợi ý:** Gossip xem node Up/Normal; không chứng minh native CQL, CL/data oracle hay p99.

**Câu 14.** Sau restart, cần kiểm những tầng readiness nào?  
**Gợi ý:** JVM/process, JMX, gossip, native transport, schema/driver, CL/data oracle, performance/backlog.

**Câu 15.** `nodetool drain` có phải lệnh đọc-only để chẩn đoán health không?  
**Gợi ý:** Không; nó ngừng nhận writes và flush tables để chuẩn bị graceful shutdown.

**Câu 16.** Drain thành công nhưng restart API timeout, controller phải làm gì?  
**Gợi ý:** HOLD/UNKNOWN_ACTION_OUTCOME, kiểm actual process/operator state, không tiếp tục wave.

**Câu 17.** Có thể dùng `nodetool decommission` để loại node khỏi traffic trước restart không?  
**Gợi ý:** Không; decommission thay topology/ownership, khác graceful restart.

**Câu 18.** Vì sao expected host ID/token digest cần kiểm sau restart?  
**Gợi ý:** Phát hiện unexpected replacement/PVC identity drift thay vì restart cùng logical node.

**Câu 19.** Nếu pod Running nhưng Cassandra còn `UJ`, có thể coi wave hoàn tất không?  
**Gợi ý:** Không; joining/bootstrap là topology/data state chưa xong.

**Câu 20.** Schema agreement có chứng minh toàn bộ historical data đã repaired chưa?  
**Gợi ý:** Không; schema metadata và replica data đồng bộ là hai lớp riêng.

**Câu 21.** Thao tác nào phải có một migration owner duy nhất?  
**Gợi ý:** DDL/schema migrations để tránh nhiều pods đồng thời thay schema.

**Câu 22.** Vì sao `CREATE TABLE IF NOT EXISTS` không đủ làm contract gate?  
**Gợi ý:** Existing table có thể khác PK/types/columns nhưng statement vẫn không tạo mới.

**Câu 23.** Vì sao không rollout app Java cùng lúc với binary/schema nếu không có joint plan?  
**Gợi ý:** Dễ tạo confounders, schema/driver incompatibility và retry/routing storms.

**Câu 24.** Java Driver `localDatacenter` sai gây lỗi gì?  
**Gợi ý:** Routing/connection/availability issues, dù Cassandra nodes ở DC khác vẫn UP.

**Câu 25.** Vì sao `SELECT system.local` không là business readiness oracle?  
**Gợi ý:** Nó không dùng user keyspace/partition/required CL và không kiểm expected data.

**Câu 26.** Sentinel query cần assert điều gì ngoài việc không exception?  
**Gợi ý:** Expected key, row, value/version, CL, deadline, scope và phân bố token keys.

**Câu 27.** Lab RF1/ONE có chứng minh zero-downtime restart không?  
**Gợi ý:** Không; node duy nhất down thì không còn replica để đáp ứng ONE.

**Câu 28.** Tại sao driver readiness probe ở `ONE` không chứng minh `LOCAL_QUORUM` service khỏe?  
**Gợi ý:** ONE cần ít replies hơn và có thể stale; contract khác.

**Câu 29.** P99 success giảm nhưng timeouts tăng, controller nên làm gì?  
**Gợi ý:** HOLD/ABORT, xem censored slow requests; không coi p99 tốt hơn là thắng.

**Câu 30.** Có cần p99 sample count không?  
**Gợi ý:** Có; percentile low-QPS có độ ổn định kém.

**Câu 31.** Vì sao `PendingCompactions=0` không phải steady-state gate duy nhất?  
**Gợi ý:** Read/write/GC/disk/streaming/replicas vẫn có thể bị nghẽn, compaction liên tục có thể bình thường.

**Câu 32.** Điều gì xảy ra khi dữ liệu metrics bị mất giữa wave?  
**Gợi ý:** Gate UNKNOWN → HOLD, không biến null thành 0.

**Câu 33.** Vì sao snapshot metrics từ 15 phút trước không được dùng cho pre-wave?  
**Gợi ý:** Topology/availability có thể đã thay; cần freshness limits.

**Câu 34.** `run_id`, `action_id` và `attempt_id` có giống nhau không?  
**Gợi ý:** Không; campaign, intended side effect và mỗi network/API attempt tách biệt.

**Câu 35.** API restart timeout có chứng minh node chưa bị restart không?  
**Gợi ý:** Không; side effect có thể đã diễn ra, cần reconcile.

**Câu 36.** Vì sao controller cần persist intent trước side effect?  
**Gợi ý:** Để recovery sau crash biết action nào đã submitted và không replay mù.

**Câu 37.** Một maintenance lock chỉ lưu trong RAM có đủ chống split-brain không?  
**Gợi ý:** Không; cần durable lease/renewal/fencing được enforce ở action boundary.

**Câu 38.** Controller mất lease nhưng vẫn nhớ plan cũ, được tiếp tục không?  
**Gợi ý:** Không; stop new actions, actor mới phải reconcile.

**Câu 39.** `batch_size=1` nghĩa luôn phải restart một node sau mỗi 60 giây không?  
**Gợi ý:** Không; là trần, effective batch có thể bằng 0 và readiness phải có evidence.

**Câu 40.** Có nên tăng concurrency để kịp maintenance deadline?  
**Gợi ý:** Không; dừng/chuyển lịch, không vi phạm safety budget.

**Câu 41.** `repair -pr` có tự sửa mọi data ranges nếu chạy trên một node không?  
**Gợi ý:** Không; repair scope theo node/ranges, cần cluster-wide coverage plan.

**Câu 42.** Hint delivery có thay repair hoàn toàn không?  
**Gợi ý:** Không; hinted handoff là best effort, missed writes cần repair/verification.

**Câu 43.** Vì sao node replacement khác rolling restart?  
**Gợi ý:** Token/data ownership và bootstrap/streaming/repair, host ID/volume identity có thể thay.

**Câu 44.** `storage_compatibility_mode` có thể bật `NONE` ngay ở canary Cassandra 5.x không?  
**Gợi ý:** Không tự ý; phải theo supported staged upgrade sequence/compatibility.

**Câu 45.** Khi nào được rollback binary?  
**Gợi ý:** Chỉ khi release/on-disk format/config/schema state vẫn tương thích và runbook có approval.

**Câu 46.** Vì sao operator Task Completed chưa phải GO?  
**Gợi ý:** Operator xác nhận task lifecycle, chưa chứng minh app CL/data/SLO.

**Câu 47.** Nguyên tắc an toàn khi có node DOWN bất ngờ sau wave?  
**Gợi ý:** Recompute headroom; HOLD/ABORT waves mới, không giữ plan cũ.

**Câu 48.** Khi nào có thể kết luận rollout COMPLETED?  
**Gợi ý:** Mọi planned waves verified, expected versions/identities đúng, required CL/data oracle và SLO PASS, background work ổn, không còn unknown actions, có audit report.

## 27. Tổng kết: mỗi wave là một quyết định an toàn mới

~~~text
              CASSANDRA OPERATIONS AUTOMATION
                            |
                   CHANGE CONTRACT
           approved target/config/version + rollback
                            |
                      PREFLIGHT
    topology/RF/CL/token sets + resources + business SLO
                            |
                 COMPUTE SAFE CONCURRENCY
             min(replica, resource, business)
                            |
                +-----------+-----------+
                |                       |
             UNSAFE                   SAFE
                |                       |
           HOLD/ABORT                  CANARY
                                        |
                              Lifecycle action + checkpoint
                                        |
                              Node/process/CQL readiness
                                        |
                               CL + data oracle PASS?
                                /             \\
                              NO              YES
                               |               |
                              HOLD       Resource/SLO windows
                                                |
                                          PASS or FAIL?
                                        /          \\
                                      PASS          FAIL
                                       |             |
                                WAVE_VERIFIED     HOLD/ABORT
                                       |
                             Re-check next wave budget
                                       |
                               ALL WAVES VERIFIED
                                       |
                            POST-SOAK + AUDIT REPORT
~~~

### 27.1. Bảy nguyên tắc bắt buộc nhớ

1. **Replica-set trước batch size:** Số nodes restart không quyết định được an toàn nếu không biết natural replicas và CL của các keyspaces quan trọng.
2. **Một node tại một thời điểm là baseline, không phải theorem:** RF1/2/LQ/ALL hoặc node DOWN có thể khiến ngay cả một restart cũng không an toàn.
3. **Ba budget phải cùng PASS:** replica availability, disk/CPU/network maintenance capacity và business SLO/error budget.
4. **Đừng chỉ nhìn `UN`:** Cần native CQL, schema/driver readiness, CL data oracle, p99/retries/errors và background task trends.
5. **Không nhân side effects khi mất ACK:** Action API timeout → UNKNOWN + reconcile bằng ID/state, không restart lại mù.
6. **Mỗi loại change có lifecycle khác:** Restart, upgrade, schema migration, repair, replace và app deploy không chia sẻ một concurrency/recovery rule.
7. **HOLD là kết quả an toàn:** Khi telemetry thiếu, node identity sai, quorum margin thấp hoặc rollback không rõ, dừng wave mới và bàn giao, không ép COMPLETED.

**Thông điệp cốt lõi:** Tự động hóa vận hành Apache Cassandra không phải “for-loop qua danh sách nodes”. Một rollout đáng tin là **một chuỗi quyết định có bằng chứng**: biết replica ownership/RF/CL, đánh giá trạng thái hiện tại trước từng wave, giới hạn đồng thời theo cả data availability lẫn tài nguyên và SLO, chỉ tiếp tục sau các gate dữ liệu/driver/hiệu năng, và **dừng an toàn** khi có UNKNOWN hoặc điều kiện thay đổi.

### 27.2. Giới hạn nội dung/lab

Lab CQL RF1 chỉ dạy sentinel và CL syntax; Java Driver probe chỉ kiểm một table/key cho đến khi được mở rộng coverage, Java replica-budget simulation chỉ tính trên các sets khai báo. Không có script trong bài tự chạy restart hay fault-injection lên cluster thật. Muốn áp dụng production cần kiểm versioned Cassandra/K8ssandra operator APIs, topology thực, RBAC/TLS, on-call approvals, staging validation và rollback compatibility. Theo quy trình học liệu, **STEP 4 chỉ viết Markdown**, không chạy Gradle/Python hoặc vòng STEP 6 Content QA.

## Tài liệu tham khảo

- [Apache Cassandra — Use nodetool](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html) — `status`, `tpstats`, `netstats`, `compactionstats` và giới hạn của góc nhìn node.
- [Apache Cassandra — Nodetool drain](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/drain.html) — chuẩn bị graceful shutdown: ngừng writes và flush tables.
- [Apache Cassandra — Nodetool status](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/status.html) — trạng thái Up/Down, Normal/Joining/Leaving/Moving và host IDs/racks.
- [Apache Cassandra — Nodetool netstats](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/netstats.html) — theo dõi streaming/transfer state.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — hinted handoff best effort, repair/ranges, incremental/full repair và resource cost.
- [Apache Cassandra — Adding, replacing, moving and removing nodes](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/topo_changes.html) — topology changes, streaming, replacement và cleanup khác restart.
- [Apache Cassandra — Cassandra configuration reference](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — storage compatibility modes và những config cần quan tâm trong nâng cấp.
- [Apache Cassandra — Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — request latency/errors, thread pools, compaction/repair và system metrics.
- [Apache Cassandra — Compaction overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html) — SSTable rewrite, resource contention và maintenance.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — partition/token, natural replicas, replication và consistency levels.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — primary key/partition model và việc thiết kế CQL theo truy vấn.
- [Apache Java Driver 4.18 — Metadata](https://apache.github.io/cassandra-java-driver/4.18.1/core/metadata/) — node/schema/metadata snapshots và driver view.
- [Apache Java Driver 4.18 — Pooling](https://apache.github.io/cassandra-java-driver/4.18.1/core/pooling/) — connections/in-flight streams và multiplexing.
- [Apache Java Driver 4.18 — Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — retries/idempotency và physical request amplification.
- [Apache Java Driver 4.18 — Metrics](https://apache.github.io/cassandra-java-driver/4.18.1/core/metrics/) — driver session/node metrics và latency timers.
- [K8ssandra — Cass Operator](https://docs.k8ssandra.io/components/cass-operator/) — Kubernetes Cassandra lifecycle/management API/operator responsibility.
- [K8ssandra — Cass Operator CRDs](https://docs.k8ssandra.io/reference/crd/cass-operator-crds-latest/index.html) — version-specific operator tasks/configuration.
- [Kubernetes — PodDisruptionBudgets](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/) — voluntary disruptions, PDB scope và giới hạn.
- [Kubernetes — StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/) — ordered rollout, readiness and identity semantics.

