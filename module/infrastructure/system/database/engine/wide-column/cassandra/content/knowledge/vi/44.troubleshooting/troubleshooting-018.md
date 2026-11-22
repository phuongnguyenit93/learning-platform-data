# Đánh giá tác động trước restart, scrub, compact hoặc thay giới hạn

## 1. Một thao tác “sửa nhanh” có thể trở thành sự cố lớn hơn

Một cụm **Apache Cassandra** có sáu node, trải trên hai datacenter, phục vụ ứng dụng Java ghi telemetry và đọc trạng thái thiết bị. Dashboard báo p99 của vài truy vấn tăng mạnh; trên một node xuất hiện log SSTable lỗi checksum, trong khi disk free của các node khác cũng giảm vì compaction backlog. Các đề xuất xuất hiện cùng lúc:

- “Restart node chậm để xóa cache và làm mới kết nối.”
- “Chạy `nodetool scrub` trên bảng có lỗi để Cassandra tự sửa.”
- “Chạy `nodetool compact` toàn bảng cho hết tombstone.”
- “Tăng timeout hoặc ngưỡng tombstone failure để request không lỗi nữa.”

Bốn thao tác này có **mục tiêu, phạm vi, tác dụng phụ và khả năng phục hồi hoàn toàn khác nhau**. Restart không sửa một SSTable đã hỏng trên đĩa. Scrub có thể viết lại dữ liệu và trong những chế độ xử lý corrupt records có thể dẫn tới **mất dữ liệu cục bộ**. Major compaction tiêu nhiều I/O/disk và **không tự bảo đảm tombstone được purge an toàn**. Tăng timeout/threshold có thể biến lỗi nhanh thành truy vấn giữ tài nguyên lâu hơn, đẩy cả cluster vào quá tải.

~~~mermaid
flowchart TD
    A["Phát hiện read timeout / corrupt SSTable / disk pressure"] --> B["Khoanh vùng triệu chứng, nguyên nhân và ảnh hưởng"]
    B --> C{"Đã đủ dữ liệu đánh giá thay đổi?"}
    C -->|Chưa| D["Thu metric, log, RF/CL, SSTable, repair/backup, capacity"]
    D --> C
    C -->|Rồi| E{"Chọn phương án tương ứng nguyên nhân"}
    E --> F["Restart có kiểm soát"]
    E --> G["Scrub một SSTable/table phạm vi hẹp"]
    E --> H["Compaction theo strategy/budget"]
    E --> I["Thay giới hạn/guardrail/timeout"]
    F --> J["Canary + đo + xác minh data correctness"]
    G --> J
    H --> J
    I --> J
    J --> K{"Đạt SLO và safety gates?"}
    K -->|Không| L["Dừng, cô lập tác động và phục hồi theo runbook"]
    K -->|Có| M["Mở rộng từng bước, ghi audit và hậu kiểm"]
~~~

Bài học thuộc chương **Xử lý sự cố** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Mục tiêu mô-đun là hiểu kiến trúc phân tán và wide-column của Cassandra, nhất là **partition key, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và Java Driver**. Vì vậy quyết định vận hành phải liên kết **tín hiệu hạ tầng** với **hợp đồng đọc/ghi của ứng dụng**, không chỉ xem node đã khởi động lại hay lệnh trả exit code 0.

**Sau bài này, người học có thể:**

1. Nêu **tác động dự kiến** của restart, scrub, compact và sửa limits lên availability, durability, consistency, throughput, disk và rollback.
2. Tính sơ bộ quorum cần thiết theo RF/CL, xác định natural replicas và tình trạng các node **trước khi rút một replica khỏi cụm**.
3. Thu baseline có chứng cứ từ `nodetool`, log, JMX, driver, các query mẫu và ledger dữ liệu.
4. Phân biệt **`nodetool scrub`** với **`sstablescrub` offline**, compaction thường với major compaction, các limit bảo vệ với timeout/throughput.
5. Xác định khi nào **không được** restart, scrub, major compact hoặc nới guardrail.
6. Thiết kế canary, stop criteria, backup/repair/restore plan và xác minh sau thao tác phù hợp với đúng phạm vi.
7. Viết test CQL/Java Driver ở môi trường cô lập để phát hiện missing IDs, duplicate writes, consistency regression và retry storm.
8. Viết change record có thể audit, phân biệt **rollback config** với **khôi phục dữ liệu** khi thao tác đã thay SSTables.

**Phạm vi:** Ví dụ dùng Cassandra 4.x/5.x, Java Driver 4.x và CQL thông dụng. Cú pháp `nodetool`, options, config keys, mặc định giới hạn và khả năng hot-reload thay đổi giữa phiên bản, bản phân phối và operator. **Luôn đọc help/tài liệu đúng version trong môi trường được phép trước khi chạy lệnh.** Đây là bài học đánh giá tác động, không phải lệnh yêu cầu thao tác trên production.

## 2. Bốn loại thay đổi: đối tượng chịu tác động và tính đảo ngược

| Thao tác | Phần hệ thống bị tác động | Có thể có mất/đổi dữ liệu? | Phục hồi thực tế |
| --- | --- | --- | --- |
| **Restart một Cassandra node** | Process/JVM, connection, memtable flush/recovery, gossip, cache, client routing, hints catch-up. | Thường không phải thao tác xóa dữ liệu, **nhưng mất availability tạm thời và lộ rủi ro nếu durability/replication đang yếu**. | Start lại process và xác minh node/replica catch-up; không coi việc start thành công là hết sự cố. |
| **`nodetool scrub`** | SSTables của table trên node được chọn; verify/rewrite dữ liệu hỏng theo chế độ/tool. | **Có thể có**: rows/partitions corrupt không cứu được có thể bị bỏ qua trong một số chế độ; SSTables/metadata thay đổi. | Snapshot/backup, bản sao replica khỏe, repair hoặc restore; **không** có undo đơn giản. |
| **`nodetool compact` / major compaction** | SSTables, disk I/O, CPU, compaction debt, read/write amplification và tombstone purge eligibility. | Không nhằm xóa live rows, nhưng tổ chức lại files và có thể dọn tombstones theo điều kiện; sai assumptions về deletion history gây rủi ro. | Không có “uncompact”; muốn về bytes cũ cần snapshot/restore, và thay đổi storage có thể không cần rollback nếu correctness đạt. |
| **Thay giới hạn** | CQL guardrails, tombstone thresholds, timeouts, page/batch/mutation caps, client throttling hoặc compaction throughput. | Thường không sửa dữ liệu trực tiếp, **nhưng thay fail-fast/protection semantics**; có thể dẫn đến OOM, overload, stale reads hoặc side effects do retry. | Revert config/runtime value **đúng từng node/app**, đôi khi cần restart/rolling deployment; undo config không undo mutations đã xảy ra. |

**Tính đảo ngược là một phổ:** restart process có thể hoàn nguyên dễ hơn scrub dữ liệu, nhưng nếu restart gây mất coordinator giữa một write chưa ACK, ứng dụng vẫn phải xử lý **unknown outcome**. Một `rollback` config không khôi phục SSTable cũ sau scrub, và `nodetool stop COMPACTION` không đưa SSTables về trạng thái ban đầu như database transaction rollback.

## 3. Phân loại rủi ro trước khi đề xuất lệnh

### 3.1. Sáu chiều cần đánh giá

| Chiều | Câu hỏi cần có câu trả lời |
| --- | --- |
| **Availability** | Nếu một node down, mỗi `LOCAL_QUORUM`/`QUORUM`/`ALL` còn đủ full replicas để thành công không? Có lỗi thứ hai đang chờ xảy ra? |
| **Correctness / durability** | Hints, repair, commit log, disk và backup có đảm bảo không mất bản duy nhất của dữ liệu/tombstone không? |
| **Latency / throughput** | Thay đổi có làm tăng số SSTables quét, CPU/GC, disk await, network, read/write queue hoặc client retries không? |
| **Storage / headroom** | SSTables được viết lại cần bao nhiêu temporary disk? Snapshot hard links, compaction leftovers, hints và commit log có chiếm cùng filesystem không? |
| **Scope / blast radius** | Một table trên một node, một token range, một DC, toàn cluster, toàn đội client hay tất cả truy vấn dùng chung guardrail? |
| **Reversibility / evidence** | Có snapshot/restore đã thử, rollback plan, test stop criteria, owner, deadline và log đủ xác minh trước–sau không? |

### 3.2. Trạng thái **GO / NO-GO / ESCALATE**

- **GO cho canary hạn chế:** topology khỏe, replica coverage đủ, backups có thể đọc/restore, disk/GC headroom, nguyên nhân đã khoanh vùng, người chịu trách nhiệm rõ, không có job bảo trì chồng lấp.
- **NO-GO:** đang thiếu full replicas cho consistency contract; disk gần đầy không đủ rewrite; không có bản copy/backup của corrupt data; chưa biết scope; tombstones có nguy cơ zombie; metrics và khả năng dừng đều thiếu.
- **ESCALATE:** nghi ngờ nhiều replicas đã corrupt cùng token range, node down quá `gc_grace_seconds`, schema migration chưa ổn định, multi-DC đang partition, các writes có outcome unknown hoặc cơ sở dữ liệu duy nhất của thông tin tuân thủ/pháp lý.

Không coi `nodetool status=UN` là một green light tự động: `UN` nói node **UP/NORMAL theo gossip**, không chứng minh SSTables không lỗi, các replica có cùng live/deleted cells hay repair đã bao phủ đúng token ranges.

## 4. Tiền kiểm topology: tính quorum trước khi restart một replica

### 4.1. RF=3 trong một datacenter

Giả sử `NetworkTopologyStrategy` và ba full replicas cho partition cụ thể trong `dc1`:

~~~text
R1  UN   rack-a
R2  UN   rack-b
R3  UN   rack-c

RF(dc1) = 3
LOCAL_ONE    cần 1 full replica response tại dc1
LOCAL_QUORUM cần floor(3/2)+1 = 2 responses tại dc1
ALL          cần 3 responses (nếu chỉ có dc1)
~~~

| Trạng thái khi rút một node | `LOCAL_ONE` | `LOCAL_QUORUM` | `ALL` |
| --- | --- | --- | --- |
| R1/R2/R3 đều khỏe, dừng R3. | Có thể đáp ứng. | **Có thể đáp ứng** với R1/R2. | Thông thường không đủ ba responses. |
| R2 đã down, định dừng R3. | Có thể còn một replica R1. | **Không** đủ hai replicas. | Không đủ. |
| R2 lên nhưng nhiều read timeouts/disk full. | Có thể thành công tùy key/route. | **Rủi ro cao**, không có đủ năng lực đáp ứng thực tế. | Rủi ro cao. |

**Cần phân biệt full replicas, transient replication và consistency semantics theo version.** Bảng này dành cho **full RF=3** điển hình. Không áp số học này cho topology có transient replicas mà không tính từng loại replica/CL riêng.

### 4.2. Coordinator khác natural replica

Java Driver chọn một node làm **coordinator** cho CQL request; node ấy không nhất thiết sở hữu token của partition. Việc restart coordinator có thể làm các connections/futures phải retry, còn restart **natural replica** ảnh hưởng trực tiếp tới read/write CL của những keys nó sở hữu. Trong cluster lớn hơn RF, **dừng một node ngẫu nhiên không có nghĩa key đang test sẽ mất một replica**.

~~~mermaid
flowchart LR
    A["App CqlSession"] --> B["Coordinator (có thể không là replica)"]
    B --> R1["Natural replica R1"]
    B --> R2["Natural replica R2"]
    B --> R3["Natural replica R3"]
    R1 --> C["CL ACK, độ trễ và timeout"]
    R2 --> C
    R3 --> C
~~~

### 4.3. Multi-datacenter

Keyspace có `dc1:3,dc2:3`: write `LOCAL_QUORUM` ở `dc1` cần **hai full replicas ở dc1**, không lấy bất kỳ hai responses từ cả hai DC. `QUORUM` trên tổng sáu full replicas cần bốn; `EACH_QUORUM` (write) yêu cầu quorum ở từng DC. `ALL` mất khả năng hoàn tất nếu một replica bắt buộc đang down. Khi lập lịch restart, ghi **DC, rack, local coordinator policy, WAN health, RF và CL thực của từng workload**; không dùng bảng của một DC để suy toàn cầu.

### 4.4. Một node down nghĩa giảm khả năng chịu lỗi thêm

Trong RF3/LOCAL_QUORUM, còn hai full replicas khi R3 down có thể đủ phục vụ, nhưng lúc đó **không còn dự phòng cho thêm một replica bất khả dụng** đối với keys ấy. Không bắt đầu thêm restart, scrub, repair tốn tài nguyên hoặc nâng cấp JDK trên R1/R2 cùng lúc chỉ vì các request hiện vẫn trả 200.

## 5. Sự kiện trước/sau thao tác: baseline không được bỏ qua

### 5.1. Thu evidence theo cửa sổ UTC

~~~text
Change ID              : CHG-... (lab/production tùy môi trường)
Incident / hypothesis   : ...
Cluster/DC/keyspace     : ...
Cassandra/JDK/driver    : exact versions ...
Affected node/table     : ...
Observed root symptom   : ...
RF, local CL, serial CL : ...
Start/stop UTC          : ...
Current node/rack health: ...
Last successful repair  : scope/time...
Backup/snapshot tested? : ...
Disk free/GC baseline   : ...
Latency p50/p95/p99     : ...
Offered/achieved QPS    : ...
Timeout/retry counters  : ...
Expected ID/value set   : ...
Operator/rollback owner : ...
~~~

**Có timestamp UTC và version chính xác** để so các metrics trước/sau; không kết luận từ biểu đồ “cảm giác nhanh hơn” nếu throughput và query mix đã thay.

### 5.2. Các lệnh đọc trạng thái thường dùng

~~~bash
# Chỉ trên node/cluster được phép, ưu tiên READ-ONLY:
nodetool status
nodetool info
nodetool tpstats
nodetool netstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats telemetry_ops.events_by_device_day
nodetool tablehistograms telemetry_ops events_by_device_day
~~~

Các lệnh và tên output có thể thay đổi theo Cassandra release. `tablestats` là thống kê node/table, không phải cơ sở để khẳng định **mọi replica có cùng dữ liệu**; `netstats` chỉ phản ánh một số streaming/network operations; `compactionstats` không chứng minh một tombstone được purge an toàn. Nếu node không đáp ứng JMX, thu log/OS metrics và **không coi việc `nodetool` timeout là bằng chứng lệnh bảo trì nên được chạy bừa**.

### 5.3. Đọc server warnings và metrics theo truy vấn

| Tín hiệu | Để xác định |
| --- | --- |
| `system.log`/GC log/OS kernel log | Corrupt SSTable/checksum, OOM, disk errors, GC pauses, startup/shutdown errors. |
| Read/Write `Latency` và `Timeout` counters | Mức độ ảnh hưởng theo node/operation; so app request errors. |
| `TombstoneScannedHistogram`/`LiveScannedHistogram` | Một query có scan nhiều deletion markers không, theo instrumentation/version. |
| `SSTablesPerReadHistogram`, partition-size estimates | Read amplification, partition skew; khác với tổng logical rows. |
| `PendingTasks`/`DroppedTasks` | Compaction/read/write queues đã quá tải chưa. |
| Driver retries/in-flight/coordinator distribution | Ảnh hưởng client khi node thay trạng thái; phát hiện retry storm. |
| Hints pending/delivered, last repair coverage | Khả năng bắt kịp sau node down và rủi ro delete divergence. |

Không đưa `tenant_id`, `device_id`, JWT, raw cursor hay payload vào metric labels high-cardinality; dùng `query_name`, endpoint, DC, environment, error class và sampling logs đã bảo vệ.

## 6. Hệ thống dữ liệu: commit log, hints, repair và tombstones liên quan thế nào?

| Cơ chế | Đảm bảo/tác dụng chính | Cạm bẫy khi làm maintenance |
| --- | --- | --- |
| **Commit log + memtable + SSTable** | Độ bền cục bộ của mutation mà một node đã nhận theo write path/config. | Restart đột ngột có thể cần replay commit log; disk/commitlog failure là câu chuyện khác process restart. |
| **Hinted handoff** | Coordinator có thể lưu và replay một số writes bị missed cho replica vắng mặt, khi hinting được phép. | Best-effort/window/storage bounded; restart quá lâu tăng hints backlog, **không thay repair**. |
| **Read repair** | Một số reads phát hiện và sửa khác biệt trong scope được đọc, tùy CL/version. | Không quét mọi token range hoặc thay full anti-entropy repair. |
| **Anti-entropy repair** | So replicas cùng token ranges, thường qua Merkle trees/streaming. | Tốn CPU/disk/network; repair không thể tái tạo dữ liệu nếu mọi nguồn đều mất. |
| **Tombstone + `gc_grace_seconds`** | Bảo vệ ý định xóa trong lúc replica có thể chưa nhận DELETE. | Lower grace/force purge khi replica miss delete có nguy cơ **zombie data**. |
| **Snapshot/backup** | Khả năng lấy bản sao dữ liệu/SSTable và manifest ở mốc xác định. | Snapshot là hard links cục bộ, không tự là backup off-cluster hay global transaction snapshot. |

**Chốt:** Restart, scrub hoặc compact chỉ hợp lý khi tính cả **trạng thái những replicas còn lại** và **lịch repair/backup**, không chỉ trạng thái file/heap của node định xử lý. Một bản sao hợp lệ ở replica khác có thể giúp repair sau scrub, nhưng không được giả định khi replica ấy cũng đang hỏng/thiếu/đã purge deletion marker.

## 7. Ma trận nhanh: triệu chứng nào dẫn đến quyết định nào?

| Triệu chứng có bằng chứng | Restart? | Scrub? | Compact? | Tăng limit? |
| --- | --- | --- | --- | --- |
| GC pause/JVM stuck, heap leak nghi sau deploy. | **Có thể**, sau xác minh capacity và rollback code/JDK. | Không phải root fix. | Có thể làm I/O tệ hơn. | Tăng heap/timeouts tùy tiện dễ che lỗi. |
| Log xác nhận SSTable checksum corruption trên một node/table. | **Không** sửa corruption trên disk. | **Cân nhắc**, sau backup + xác nhận các replicas/restore source còn sạch. | Không chữa bytes corrupt an toàn. | Không sửa corruption. |
| Một partition quá lớn, CQL query range rộng. | Không đổi data model. | Không giải quyết nguyên nhân. | Không đổi partition key. | Nâng timeout có thể chỉ giữ query nặng lâu hơn. |
| Tombstone scan cao, TTL/range DELETE dày đặc. | Không giảm số markers. | Không dùng scrub để “xóa tombstone”. | Có thể có cleanup khi hợp lệ, nhưng không phải bảo đảm. | Nâng failure threshold có thể gây cluster overload. |
| Compaction backlog do I/O thiếu, disk free thấp. | Restart có thể tăng backlog/cold caches. | **NO-GO** khi không đủ temp disk. | **NO-GO** major compaction khi thiếu headroom. | Throttle/capacity theo kế hoạch, không mở vô hạn. |
| `Unavailable` do thiếu full replicas RF/CL. | Chỉ restart node khác sau khi phục hồi quorum. | Không chạy trên replica duy nhất còn tốt. | Tránh I/O nặng trên replica sống. | Không âm thầm hạ CL để che availability. |
| Warnings vì application `INSERT`/batch quá lớn. | Không sửa producer behavior. | Không phù hợp. | Không giải quyết mutation shape. | Tăng batch/mutation guardrail thường nguy hiểm; redesign writes. |
| Read timeout do client retry storm. | Restart không sửa retry policy. | Không phù hợp. | Có thể làm read load tệ. | Tăng timeout/connection pool có thể khuếch đại tải; bounded retries/backpressure. |

Đây là **bản đồ quyết định ban đầu**, không thay thực chứng. Bước tiếp theo phải trả lời: **lệnh cụ thể có thật sự tác động vào nguyên nhân đã xác định, và thao tác ấy có làm hỏng các invariant dữ liệu hoặc SLO khác không?**

## 8. Restart: sửa process/JVM, không tự sửa dữ liệu bị corrupt

Restart một Cassandra process làm node tạm rời native CQL service, có thể rời gossip/internode networking trong một khoảng thời gian, rồi khởi động lại; driver phải định tuyến/reconnect, còn node có thể cần replay commit log, mở lại SSTables, làm nóng cache và nhận hints bị bỏ lỡ.

### 8.1. Restart có thể giúp khi nào?

- Node bị stuck trong một trạng thái JVM/process được chẩn đoán, sau khi có heap/GC/thread dump và xác định restart là biện pháp phục hồi availability tạm thời.
- Một thay đổi cấu hình **chỉ có hiệu lực khi start process** cần rolling restart sau khi review config diff, theo release notes/version.
- Binary/JDK/certificate/network listener cần apply qua restart, với **compatibility matrix** và phê duyệt riêng.
- Node không xử lý request mới được, nhưng **disk, các replicas khác và bản backup** đủ lành mạnh để chịu một node rời cụm.

### 8.2. Restart **không** sửa gì?

- Một SSTable corrupt trên disk hoặc I/O error vật lý.
- Partition key sai làm một partition phát triển quá lớn.
- Tombstones, `gc_grace_seconds`, repair lag, hints missing.
- CQL `ALLOW FILTERING` hay read path không có clustering range.
- Driver retry storm hoặc application bug ghi `null` ngoài ý muốn.
- Disk thật sự full, commit log corruption nghiêm trọng, dữ liệu duy nhất đã mất.

Nếu restart có tác dụng trong vài phút rồi p99 tăng trở lại, hãy quay về root cause (GC pressure, compaction, disk, query, queue), không tạo **reboot loop** làm cold cache và hint backlog lặp đi lặp lại.

## 9. Runbook rolling restart một node có điểm dừng

### 9.1. Preflight trước mỗi node, không chỉ một lần cho cả cụm

~~~text
Target node    : R3, dc1/rack-c, host-id verified
Scope          : exactly one process, not all pods at once
RF/CL          : full RF=3 in dc1, app LOCAL_QUORUM
Remaining      : R1/R2 healthy, responding, sufficient disk/CPU/GC capacity
In progress?   : no conflicting repair, bootstrap, streaming, major compaction
Hint/repair    : handoff enabled/configured, outage budget within plan
Config/binary  : exact before/after digest, Java/JDK/driver compatible
Rollback      : previous deployed image/config, owner, restore credentials
SLO stop      : read/write errors, p99, R1/R2 queues, disk free
~~~

Nếu R2 đã down hoặc `LOCAL_QUORUM` trên R1/R2 đang timeout, **NO-GO** cho việc restart R3. Đừng coi một `UN` bị nghẽn disk là replica đáng tin để duy trì quorum dưới tải.

### 9.2. Lệnh minh họa trên cluster lab được phê duyệt

~~~bash
# 1) Thu trạng thái TRƯỚC restart từ các peers:
nodetool status
nodetool tpstats
nodetool netstats
nodetool compactionstats

# 2) Trong runbook có chủ đích, có thể dùng:
nodetool drain

# 3) Sau đó người vận hành/orchestrator mới stop/start Cassandra process
#    trên ĐÚNG node; lệnh phụ thuộc systemd/Kubernetes/Docker.
#    Không chạy những câu trên đồng loạt mọi node.
~~~

`nodetool drain` flush memtables và chuyển node tới trạng thái đã drain/không phục vụ bình thường; **cần process restart sau drain**. Nó không phải nút “giảm tải rồi cho node tiếp tục phục vụ không cần restart”. Một số operator/rolling-restart workflows quản lý drain/shutdown tự động; **không chèn drain thêm lần nữa** nếu operator đã có semantics riêng mà chưa kiểm tra.

### 9.3. Thực hiện từng node, đợi đạt hậu điều kiện mới chuyển node tiếp

1. Ghi **change ID + UTC timestamp** và chụp baseline, xác nhận đúng identity host/IP/DC/rack/volume.
2. Bảo đảm **hai replicas còn lại** có thể phục vụ workload ở regular CL đang dùng; ứng dụng báo retries/throttler phù hợp.
3. Drain/stop target theo phương pháp được tổ chức phê duyệt; **không** xóa commit log, hints, data directory hoặc volume.
4. Trong thời gian down, đo p95/p99, error, offered/achieved RPS, pending hints và disk/GC R1/R2.
5. Start lại target với đúng binary, JDK, config, volume/host ID/token; quan sát startup logs và commit-log replay.
6. Chờ peers thấy `UN`, CQL native transport sẵn sàng, schema/ring ổn định và target không còn startup exceptions.
7. Theo dõi hints delivery/catch-up, repair cần thiết, SSTables/compaction và p99 sau cold cache.
8. Xác minh các canary CQL **read/write đủ CL** và expected event IDs/values của test scope; không chỉ thấy `UN`.
9. Chỉ mở rộng tới node tiếp theo sau khi error budget và recovery metrics đạt ngưỡng **ổn định** đã định.

### 9.4. Startup có thể chậm, đừng tự động “restart lại cho nhanh”

Node có thể cần commit log replay, mở SSTables, khởi tạo system metadata, schema agreement và tiếp nhận replay hints/streaming. Nếu probe health chưa qua sau 30 giây, lặp restart liên tục có thể **kéo dài** downtime. Đặt startup deadline đủ theo kích cỡ data/JDK/version, kiểm logs và tiến độ; nếu stuck thật sự, **escalate theo runbook**, không xóa data để node “sạch”.

### 9.5. Kubernetes/operator và kiểm soát concurrency

Với StatefulSet hoặc Cassandra operator, cần review:

- **PodDisruptionBudget / maxUnavailable** có phù hợp RF/CL/availability thực không; PDB không chứng minh disk/data correctness.
- Các **initContainers, readiness/liveness probes** có gây restart loop khi boot/replay hợp lệ chậm không.
- **PersistentVolumeClaim** gắn đúng ordinal/node identity; không vô tình thay node bằng volume mới.
- Operator có **rolling restart orchestration**, repair/streaming coordination và config management riêng không.
- **DC/rack-aware maintenance order**; không rút đồng thời hai natural replicas của cùng key.

**Kubernetes `Ready` không tương đương Cassandra `UN` + full repair/replica convergence**; phải kiểm tra cả hai tầng.

## 10. Những dấu hiệu phải hoãn restart

| NO-GO evidence | Vì sao nguy hiểm | Hành động thay thế |
| --- | --- | --- |
| Chỉ còn hai full replicas khỏe ở RF3/LOCAL_QUORUM và muốn restart thêm một trong hai. | Mất quorum cho những keys đó. | Phục hồi replica còn down trước; không song song maintenance. |
| Disk/commitlog đầy hoặc thiết bị storage có read errors. | Restart không tạo thêm dung lượng và có thể không lên lại. | Khắc phục disk/capacity bằng runbook và backups. |
| Node đang bootstrap/replace/decommission hoặc streaming quan trọng. | Token ownership/replica handoff chưa ổn định. | Hoàn thành/khôi phục topology operation trước. |
| Repair đã trễ gần/vượt `gc_grace_seconds`. | Một replica quay lại có thể giữ deleted rows cũ; rủi ro zombie. | Đánh giá repair/restore/replace đúng chính sách. |
| Không biết replica nào giữ bản sao đúng sau corrupt SSTable. | Rút nhầm bản copy còn tốt làm mất khả năng đọc/khôi phục. | Kiểm backup/replica data, xác định source of truth. |
| `LOCAL_QUORUM` đang timeout thường xuyên trên healthy peers. | Dừng thêm node làm sức chịu tải tệ hơn. | Giảm tải phi thiết yếu, khôi phục node/GC/disk trước. |
| Rollback binary/config/JDK không được kiểm tra. | Restart có thể trở thành nâng cấp tương thích sai. | Kiểm compatibility matrix/schema/driver/release notes. |

## 11. Scrub: khi nào cần và nó **không** làm gì

**Scrub** là công cụ tái xử lý/kiểm tra dữ liệu SSTable cho tình huống corruption/invalid data cụ thể trên **một node và những tables được chọn**. Một số chế độ có thể bỏ qua dữ liệu hỏng không thể khôi phục, vì vậy đây **không phải công cụ làm sạch query tombstones hay bảo trì định kỳ tương đương compaction**.

### 11.1. Những tình huống có thể xem xét

- Cassandra logs hoặc tool xác nhận **SSTable corruption/checksum/serialization error** của table, xác định node/files/extent.
- Một table không thể đọc ở những token ranges nhất định, có kế hoạch dùng các replica **đã được kiểm chứng khỏe** hoặc off-cluster backup để khôi phục phần bị lỗi.
- Một vấn đề SSTable metadata/data format được nhà phát triển/vendor hướng dẫn scrub theo **đúng phiên bản**, không phải suy từ lỗi application `InvalidQuery`.

### 11.2. Tình huống **không** chọn scrub làm biện pháp đầu

- Partition quá lớn hoặc CQL thiếu clustering range: scrub không thay primary key.
- `ReadTimeout` do hot key, driver backpressure hay compaction backlog: scrub thêm read/rewrite load.
- Tombstones nhiều do TTL/delete đúng nghiệp vụ: scrub không được thiết kế để bỏ deletion history trái các điều kiện an toàn.
- Corruption bị nghi ở **tất cả replicas/backup** và chưa có nguồn dữ liệu gốc: scrub có thể giảm khả năng forensic recovery.
- Disk free không đủ để rewrite SSTables hoặc snapshot: scrub có thể đẩy node vào disk full.

### 11.3. `nodetool scrub` khác `sstablescrub` thế nào?

| Công cụ | Kiểu vận hành | Rủi ro chính |
| --- | --- | --- |
| **`nodetool scrub`** | Giao tiếp qua JMX với một Cassandra node đang được quản lý, scrub table(s) theo syntax/version. | Rewrite SSTables trên node đang thuộc cluster; disk/IO/correctness impact. |
| **`sstablescrub`** | Công cụ SSTable **offline**, làm việc trên files khi Cassandra process tương ứng đã dừng theo quy trình. | Dễ chọn nhầm đường/file hoặc làm sai khi node vẫn sử dụng SSTables; cần chỉ định đúng keyspace/table/format/version. |
| **`nodetool verify` / SSTable verification** | Kiểm tra tính hợp lệ/CRC/structures theo options/version; không đồng nghĩa sửa data. | Vẫn có I/O overhead, có thể phát hiện corruption nhưng không thay repair/restore. |

**Không chạy offline `sstablescrub` lên live data files** khi Cassandra còn ghi/compacting. Và **không mặc định hai công cụ có cùng flags**; dùng `nodetool help scrub`, help của executable theo binary chính xác, và tài liệu vận hành cùng release.

## 12. Quy trình đánh giá trước scrub: từ checksum lỗi tới nguồn dữ liệu dự phòng

### 12.1. Khoanh đúng scope

~~~text
Affected node        = R3
Keyspace / table     = telemetry_ops.events_by_device_day
SSTable / generation = ... (from verified logs)
Checksum / format    = ... (from verified logs)
Relevant token range = ...
Replica set for keys = R1/R2/R3 (full RF3 ví dụ)
Other replicas       = R1/R2 integrity and repair status VERIFIED?
Disk free            = ...
Last full backup     = ...
Last successful repair scope/time = ...
Potential missing mutations/deletes = ...
~~~

Một SSTable có corruption có thể chứa **nhiều partition keys**, vì vậy một query ID duy nhất bị lỗi chưa chắc xác định toàn bộ ảnh hưởng. Ghi đúng table, SSTable generations/token ranges và replica set; không chạy scrub “cả keyspace cho chắc” nếu chưa có bằng chứng/plan.

### 12.2. Bảo vệ dữ liệu trước

1. **Đọc logs/metrics và xác nhận nguyên nhân**: checksum/corrupt blocks, disk I/O error vật lý hay driver codec/CQL bug?
2. **Kiểm node/volume health**: nếu storage có read errors, scrub rewrite trên chính ổ hỏng có thể làm rủi ro tăng; xem xét thay đĩa/rebuild/restore plan.
3. **Xác minh R1/R2 còn bản tốt** của ranges liên quan bằng nguồn evidence phù hợp; một `SELECT LOCAL_QUORUM` thành công **không mặc định xác nhận R3 hay từng replica khỏe**.
4. Tạo **snapshot/backup off-node có manifest/checksum** nếu các files còn đọc được. Snapshot local hardlinks có thể **giữ nguyên corruption**; không coi snapshot của dữ liệu hỏng là bản backup tốt duy nhất.
5. Kiểm **repair/TTL/tombstone/grace state**: scrub bỏ corruption mà làm mất tombstone có thể cho dữ liệu cũ từ replica khác xuất hiện.
6. Tính disk headroom cho **old+new SSTables, snapshot hardlinks, compaction/commitlog/hints**; không ước lượng chỉ bằng live CQL row bytes.
7. Có bảng **expected row IDs/values/deletes/TTL**, một nguồn truth/backup/replay và operator chịu trách nhiệm nếu scrub phát hiện corruption không thể cứu.

### 12.3. Ví dụ lệnh trên **cluster test cô lập** có đủ bản sao

~~~bash
# THÍ NGHIỆM được phê duyệt, không thực thi trên production theo bài đọc.
nodetool status
nodetool tablestats telemetry_ops.events_by_device_day
nodetool compactionstats

# Kiểm trợ giúp và version-specific options TRƯỚC:
nodetool help scrub

# Tạo snapshot được quản lý, có tag rõ, rồi copy ngoài node theo runbook:
nodetool snapshot -t before-scrub-chg-001 telemetry_ops
nodetool listsnapshots

# Chỉ SAU phê duyệt và backup:
nodetool scrub telemetry_ops events_by_device_day
~~~

**Cảnh báo:** Syntax options cho snapshot/scrub có thể khác giữa bản Cassandra; ví dụ lệnh kiểm tra trợ giúp và chọn phạm vi, không phải playbook “copy chạy trên mọi cluster”. `nodetool scrub` **không chấp nhận mọi flag giống `sstablescrub`**. Một option kiểu “skip corrupted” có thể **bỏ dữ liệu lỗi**: nếu được sử dụng, phải có approval rõ cho nguy cơ mất record và đối soát sau đó. Không tự bật chế độ bỏ qua corruption chỉ để exit code 0.

### 12.4. Lưu ý quan trọng khi snapshot

Snapshot SSTable tại node là **hard links** sang SSTables hiện hữu, không phải backup đầy đủ cluster hoặc **global time-consistent transaction snapshot**. Nếu snapshot giữ files cũ, disk space có thể **không giải phóng sau compaction/scrub** cho tới khi retention/snapshot cleanup an toàn. **Đừng xóa snapshot chỉ vì disk usage tăng** khi snapshot còn là bản duy nhất cho forensic/rollback.

## 13. Sau scrub: repair/rebuild hay restore?

### 13.1. Bốn kết quả khả dĩ

| Kết quả scrub | Bằng chứng phải có | Bước tiếp |
| --- | --- | --- |
| Hoàn tất, không phát hiện dữ liệu bị mất. | Logs, disk metrics, CQL checks, representative IDs, table behavior. | Repair/validation theo scope/policy; quan sát p99/GC/compactions. |
| Scrub bỏ một số corrupted rows/partitions. | Count/IDs/ranges đã mất, corruption report, approval record. | Dùng **replica khỏe hoặc backup/replay** để phục hồi, sau đó anti-entropy repair phù hợp; không coi scrub thành công là data correctness. |
| Scrub fail vì disk/format/corruption phức tạp. | Exit/error logs, temp files/headroom và snapshot trạng thái. | Dừng thử nghiệm, đánh giá storage/restore/replacement, không lặp vô hạn. |
| Scrub hoàn tất nhưng reads vẫn timeout. | Query shape, tombstone histogram, SSTablesPerRead, client p99. | Kiểm root cause query/data model/overload; scrub không chữa mọi lỗi read. |

### 13.2. Vì sao repair có thể cần nhưng không phải thần dược?

Nếu R1/R2 còn **đủ bản tốt của mỗi cell/tombstone** trong phạm vi, anti-entropy repair có thể streaming differences cho R3. Nhưng nếu mọi replica đã mất một row hoặc tombstone/TTL history đã bị purge, repair **không sáng tạo dữ liệu từ hư không**. Phải dùng **backup/logical source/CDC/replay** hoặc đánh giá dữ liệu không phục hồi. Một lệnh repair trên một node cũng không mặc định bao phủ mọi token range/table/DC.

### 13.3. Không “undo scrub” bằng start lại node

Scrub đã rewrite SSTables không được hoàn tác chỉ bằng `systemctl restart cassandra`. Nếu cần quay lại bytes trước scrub, phải có **snapshot/backup đã kiểm thử** và quy trình restore/replace phù hợp binary/SSTable format, permissions, token placement và replica state. **Không chép SSTables bằng `cp` vào live data directory** rồi cho Cassandra tự nhận như một hot reload.

### 13.4. Báo cáo đúng mức

Nói “scrub hoàn tất trên table X/node R3, 0 errors được ghi trong phạm vi tool, ledger query qua LOCAL_QUORUM khớp và repair token ranges Y đã hoàn tất”, **không** nói “toàn bộ dữ liệu cluster 100% sạch” chỉ vì `nodetool scrub` exit 0.

## 14. Compaction tự động và major compaction thủ công là hai quyết định khác nhau

Cassandra ghi theo cấu trúc LSM: mutation vào commit log/memtable, flush thành SSTables bất biến, compaction chọn các SSTables để merge/rewrite và xử lý versions/tombstones theo điều kiện an toàn. **Automatic compaction** chạy theo strategy (STCS, LCS, TWCS, UCS khi version hỗ trợ); **major compaction** thủ công yêu cầu tái tổ chức phạm vi rộng hơn và có thể tiêu tài nguyên đáng kể.

### 14.1. Các tình huống compaction thủ công có thể cân nhắc

- Một vấn đề read amplification/SSTable layout đã được **xác định rõ** và có bằng chứng compaction sẽ giúp sau khi benchmark.
- Một thao tác data maintenance cụ thể được Cassandra/vendor documentation cho phép, với các SSTables/table/version đúng.
- Cần xử lý dữ liệu cũ sau migration/repair **theo runbook đã duyệt**, có headroom và thời gian maintenance.

### 14.2. Những điều compaction **không tự bảo đảm**

- Không sửa **corrupt SSTable bytes** như một scrub/restore plan có kiểm soát.
- Không chuyển partition per device khổng lồ thành nhiều tokens/buckets.
- Không purge mọi tombstones ngay: `gc_grace_seconds`, overlap, repaired status, shadowed data và compaction strategy còn chi phối.
- Không chắc giải phóng disk ngay nếu old SSTables còn được hard-link bởi snapshots.
- Không vô hại với p99: I/O, CPU, disk, network và GC có thể bị cạnh tranh bởi foreground reads/writes.
- Không tạo snapshot transactional consistency hoặc sửa replica divergence thay anti-entropy repair.

## 15. Compaction strategy quyết định trade-off, không có nút “compact tối ưu”

| Strategy | Hành vi mục tiêu thường thấy | Cần đánh giá trước major compaction |
| --- | --- | --- |
| **STCS** (Size-Tiered) | Nhóm SSTables có kích cỡ tương tự; phù hợp nhiều write-heavy workloads. | Read amplification, số SSTables, mức độ rewrite, temp disk và snapshots. |
| **LCS** (Leveled) | Tổ chức SSTables theo levels, thường giúp giới hạn SSTables/read. | Write amplification, I/O để duy trì levels, đặc tính major compaction theo bản. |
| **TWCS** (Time-Window) | Time-series mostly append-in-order + TTL tương đối đồng nhất; có thể drop whole expired SSTables khi an toàn. | Major compaction/cross-window rewrite có thể ảnh hưởng window separation; late writes, replay và deletes xuyên windows phải được đánh giá kỹ. |
| **UCS** (Unified) | Các workload và cân bằng compaction khi bản Cassandra/distribution hỗ trợ. | Version-specific settings và tuning; không áp công thức STCS/LCS/TWCS nguyên xi. |

Đổi từ STCS sang TWCS/UCS **không phải** thao tác “chỉ sửa config nên nhẹ”: dữ liệu cũ, compaction scheduling và resource profile có thể thay đổi theo thời gian. Trước khi đổi strategy, xác định **kiểu write timestamp (server/client), TTL, late arrival, update/delete patterns**, snapshot và schema/query shape. **Chỉ bucket partition** mới thay nơi các keys được đặt; compaction strategy không đổi partition ownership.

### 15.1. Vì sao major compaction trên TWCS có thể gây bất ngờ?

TWCS thường tách SSTables theo thời gian để những files đã hết hạn toàn bộ có thể được drop khi đủ điều kiện. Một compaction thủ công không phù hợp có thể trộn các dữ liệu/ghi muộn khác windows hoặc thay đổi bố trí SSTable khiến điều kiện whole-SSTable expiration kém thuận lợi. **Không mặc định “nén thành ít file nhất” là tốt** cho mọi table có TTL. Kiểm behavior của Cassandra version/strategy cụ thể và đo sau canary.

### 15.2. Tombstone purge phụ thuộc nhiều điều kiện

~~~mermaid
flowchart TD
    A["Tombstone đã tồn tại"] --> B{"Qua gc grace / retention rule?"}
    B -->|Chưa| C["Tiếp tục giữ marker theo policy"]
    B -->|Rồi| D{"SSTable overlap/old live data còn có thể resurrect?"}
    D -->|Có| E["Không purge tùy tiện"]
    D -->|Không| F["Purge eligibility theo compaction/repair semantics"]
    F --> G["Chỉ khi SSTables được compaction/drop phù hợp"]
~~~

Đây là mô hình khái niệm; logic Cassandra còn xét repaired state, timestamp, shadowed data, compaction options và version. **Không** dùng sơ đồ để kết luận mọi tombstone đủ `gc_grace_seconds` sẽ bị xóa ngay.

## 16. Dự toán tài nguyên trước `nodetool compact`

### 16.1. Disk headroom không thể đo bằng live CQL data bytes

Compaction thường tạo SSTable output mới **trước khi** các input SSTables cũ được giải phóng khi an toàn. Do đó peak disk có thể chứa **input SSTables + output đang tạo + commitlog/hints/snapshots + các compactions khác**. Nếu snapshot hard links tới input, xóa input metadata sau compact chưa chắc trả lại space.

~~~text
Minh họa, không phải công thức chính xác:

Table SSTables inputs       = 420 GiB
Potential rewritten output  = ~350 GiB (ước lượng)
Existing snapshots holding old files = 200 GiB linked data
Commitlog / hints / other compactions = 60 GiB

Peak yêu cầu lưu trữ có thể lớn hơn nhiều so với
giá trị “table hiện tại chỉ có 420 GiB”.
~~~

**Hard links cần được tính đúng:** không cộng mù toàn bộ snapshot hardlink sizes với active SSTables nếu chúng đang tham chiếu cùng blocks; nhưng **sau rewrite** old blocks được snapshots giữ lại, tăng **peak used physical bytes**. Dùng filesystem/free-space counters thật và conservative estimate theo compaction version/strategy; không áp biểu thức xấp xỉ như bảo đảm dung lượng.

### 16.2. CPU, disk I/O và lịch foreground traffic

| Tài nguyên | Rủi ro | Dấu hiệu theo dõi |
| --- | --- | --- |
| Disk bandwidth/await | Compaction read/write tranh với foreground reads/writes. | Disk util/await, Cassandra read/write p99, pending compactions. |
| CPU | Compression/decompression, checksums, merging versions. | CPU saturation, context switches, throttler queue. |
| Heap/GC/direct memory | Buffers, SSTable metadata, read tasks tiếp tục chạy. | GC pauses, OOM risk, off-heap metrics. |
| Free space | Output + snapshots làm đầy data volume. | Disk used/free trend; reserve cho commit log/hints. |
| Network (nếu đồng thời repair/streaming) | Hai maintenance jobs tranh băng thông. | `nodetool netstats`, repair backlog, RTT và retransmits. |
| Recovery time | Major compact kéo dài hoặc bị hủy giữa chừng. | Job progress, artifacts/temp disk, SLO impact. |

### 16.3. Không chạy đồng thời các thao tác nặng

Thực hành thông thường là **một node/table canary** ở một thời điểm, tách compaction nặng khỏi repair/streaming/upgrade/snapshot off-cluster và thời gian cao điểm. Nếu cần nhiều node/ranges, dùng **orchestrator có concurrency cap, pause/abort criteria**, không chạy một script `for all nodes; nodetool compact` không giới hạn.

## 17. Runbook major compaction thủ công có kiểm soát

### 17.1. Trước khi chạy

1. Xác nhận **root cause**: nhiều SSTables/read, compaction debt hoặc vấn đề đúng với thao tác; không chọn major compact vì một warning bất kỳ.
2. Review strategy, version, table TTL/deletes, repaired/unrepaired, snapshot retention và `gc_grace_seconds`.
3. Đo disk/free headroom, OS I/O, GC, `compactionstats`, `tablestats`, client p95/p99 và CL.
4. Chốt **đúng table trên đúng node**, có thể chỉ một table/node trong canary.
5. Kiểm repair schedule và các replicas còn khỏe; nếu một replica đang down, tránh tăng load ở những replica duy nhất phục vụ quorum.
6. Chuẩn bị **backup/rollback data risk** phù hợp và operator có quyền stop/restore, chốt `NO-GO` thresholds.

### 17.2. Lệnh minh họa cho một table trong test cluster

~~~bash
# READ-ONLY first:
nodetool compactionstats
nodetool tablestats telemetry_ops.events_by_device_day
nodetool help compact

# CHỈ khi có thay đổi được duyệt, trên MỘT node:
nodetool compact telemetry_ops events_by_device_day

# Quan sát:
nodetool compactionstats
nodetool tpstats
nodetool gcstats
~~~

Tham số `nodetool compact` có thể hỗ trợ flags như `-s` (split output), user-defined SSTables hoặc chỉ thao tác scoped theo file ở những phiên bản nhất định; **không tự thêm các flags** từ một cheat sheet khác version. Lệnh không nhất thiết “chỉ mất một phút”; tùy size/files/strategy/capacity, có thể kéo dài.

### 17.3. Nếu cần dừng compaction

Một số phiên bản hỗ trợ `nodetool stop COMPACTION` để yêu cầu dừng các tasks compaction thích hợp. Cần kiểm cú pháp, công việc bị tác động, trạng thái file/temp cleanup và hậu điều kiện trong bản đang dùng. **Stop không phải rollback transaction** và có thể để compaction debt/temporary artifacts cần dọn theo runbook. Không kill -9 node rồi xóa files tạm để “hoàn tác” khi đang có lỗi dữ liệu.

### 17.4. Sau compaction

- So **before/after**: SSTablesPerRead, read latency p95/p99, tombstone scanned, disk, GC và compaction queue ở cùng workload.
- Đối chiếu event IDs/values/deletion/TTL trên representative partitions và CL đã định.
- Kiểm snapshots giữ old blocks có làm disk vẫn cao không; cleanup backup chỉ theo retention/approval.
- Nếu performance không cải thiện, xem lại query key/partition, TTL/delete pattern và hot key; không lặp major compact vô hạn.

## 18. “Thay giới hạn” không phải một loại cấu hình duy nhất

### 18.1. Phân loại theo cấp điều khiển

| Loại limit | Ví dụ khái niệm | Khi tăng có thể gây gì? |
| --- | --- | --- |
| **Server protective threshold** | Tombstone warning/failure, guardrail partition-size, query restrictions. | Cho phép query/mutation nguy hiểm chạy lâu hơn, tốn CPU/disk/memory và ảnh hưởng tenants khác. |
| **Request timeout** | Server read/write/range request timeout, driver request timeout. | Request sống lâu, in-flight/queue lớn, retry sau timeout có outcome chưa rõ đối với writes. |
| **Mutation/batch size** | Batch warn/fail threshold, max mutation size, cell/collection/partition caps. | Commit log/memtable, network frames, heap và compaction chịu mutation lớn; **không** sửa data model. |
| **Throughput/capacity throttle** | Compaction throughput, concurrent compactor, hints delivery rate, streaming throttles. | Giảm throttle quá nhiều gây backlog; tăng quá nhiều lấn foreground traffic/disk. |
| **Driver/client throttling** | In-flight requests, pool size, page size, retries, speculative execution. | Retry amplification, hot replica pressure, heap/network và latency tails. |
| **Java/JVM/container limits** | Heap, GC, CPU/memory/pod resource, thread pools. | OOM/killed pod, GC pause, swap/host contention nếu không đo. |

**Hai nhóm dễ nhầm:** tăng **guardrail failure threshold** cho phép workload trước đây bị từ chối đi sâu hơn, còn tăng **timeout** cho phép request chờ lâu hơn. Cả hai có thể làm **blast radius lớn** dù số HTTP 500/timeout giảm ban đầu.

### 18.2. Server limit, driver limit và HTTP limit là ba tầng

~~~mermaid
flowchart LR
    A["Browser / API timeout"] --> B["Java service admission, retry, validation"]
    B --> C["Java Driver request timeout/page size/pool"]
    C --> D["Cassandra server guardrails/timeouts"]
    D --> E["Coordinator + replica CPU/disk/SSTables"]
~~~

Nếu server query đã cần quét hàng trăm nghìn tombstones, tăng **HTTP timeout** không làm replica đọc ít marker hơn. Tăng **driver page size** giảm một số network round-trips nhưng không giải quyết partition lớn và có thể tăng bytes/heap. Chỉ thay một giới hạn của một tầng cũng có thể làm các tầng khác timeout sớm hơn; phải vẽ **end-to-end latency budget**.

### 18.3. Kiểu dữ liệu cấu hình thay đổi theo version

Cassandra 3.x, 4.x và 5.x thay đổi **tên config keys, đơn vị (`_in_ms`, durations, bytes), guardrail availability, hot-reload và defaults**. Không copy `cassandra.yaml` từ bản 5.0 vào 4.0; không suy một `nodetool set...` luôn tồn tại hay persistence qua process restart. Khi thay một setting, ghi:

~~~text
Setting key        : exact name in deployed version
Scope              : node / DC / cluster / application
Old value/unit     : ...
New value/unit     : ...
Source of truth    : cassandra.yaml / operator CRD / JMX runtime / app config
Dynamic?           : verified at this exact version
Persistence        : next restart? config reconciliation?
Rolling restart?   : yes/no per official docs/operator
Rollback command   : ...
Evidence           : before/after effective values on all affected nodes
~~~

## 19. Tombstone warning/failure limit: ví dụ một guardrail phải suy xét kỹ

Trong một số bản Cassandra, `tombstone_warn_threshold` và `tombstone_failure_threshold` giới hạn **số tombstones quét trong một read**, không phải số tombstones còn trên disk. Các giá trị mặc định thường được trích như 1.000/100.000 trong vài release, **không coi là mặc định vĩnh viễn**.

### 19.1. Điều gì xảy ra khi nâng failure threshold?

Giả sử query `SELECT ... LIMIT 20` quét 120.000 tombstones trước khi tìm đủ live rows, vượt limit hiện tại. Nếu tăng threshold lên mức lớn hơn, query có thể tiếp tục — **nhưng vẫn có thể tiêu disk/CPU/heap lâu** và timeout theo budget của server/driver. Cụm có nhiều người dùng có thể bị ảnh hưởng nhiều hơn vì những reads xấu không còn fail-fast.

| Đánh giá | Cần làm |
| --- | --- |
| Query CQL shape | Có full partition key và clustering range hẹp? Có `ALLOW FILTERING` hoặc wide scan? |
| Data lifecycle | Tombstones từ TTL/delete/range/null writes hay partition rất lớn? |
| Read resource | Tombstone/live scanned, SSTablesPerRead, CPU/disk/GC và latency ở cùng partition. |
| Mức ảnh hưởng | Bao nhiêu tenants/requests sử dụng cùng query, retry rate và SLA? |
| Thay thế | Bucket theo thời gian, model theo query, repair/compaction đúng policy. |
| Canary nếu buộc phải nới | Chỉ theo scoped test/limit, có deadline, metrics và rollback được duyệt. |

**Không** dùng một limit rộng hơn để hợp thức hóa query sai. Một cảnh báo hoặc failure threshold thường là **cơ chế phòng vệ cuối**, không phải mức phân trang mong muốn.

## 20. Timeout và batch/mutation size: vì sao “không còn lỗi” chưa chắc tốt hơn

### 20.1. Timeout và Little's Law

Ở trạng thái tương đối ổn định, số request in-flight trung bình có thể xấp xỉ:

\[
L \approx \lambda W
\]

Trong đó `lambda` là số requests hoàn tất mỗi giây, `W` là mean time sống của một request (giây), `L` là in-flight trung bình.

~~~text
Ví dụ giả lập:
500 completed requests/s × 0.05 s mean = 25 in-flight
500 completed requests/s × 0.50 s mean = 250 in-flight
~~~

Nếu tăng timeout khiến **mean request time** tăng gấp 10 ở cùng throughput, in-flight/queue/memory pressure có thể tăng tương ứng. Công thức chỉ áp cho steady state; không dùng **p99** thay mean trong công thức hoặc giả định hệ đã bão hòa vẫn ổn định.

### 20.2. Retry timeout của write có thể có outcome unknown

~~~text
Client gửi INSERT event_id=E1, regular CL=LOCAL_QUORUM
Coordinator chuyển mutation tới một số replicas
Response timeout/mất kết nối

Outcome: có thể mutation đã áp dụng một phần/đủ CL nhưng ACK bị mất.
~~~

Không sinh `UUID` mới rồi retry cùng logical event mà không đối soát; có thể tạo duplicate. Dùng **stable full primary key**, idempotent mutation theo hợp đồng và ledger `ACKed / unknown / definitely rejected`. Với counters, CAS/LWT, TTL, timestamps, batches hoặc side effects liên hệ hệ khác, **không** tự đánh dấu mọi write là idempotent.

### 20.3. Batch size không đồng nghĩa throughput

Cassandra CQL `BATCH` **không phải công cụ nén hàng nghìn events từ nhiều partitions thành transaction nhanh**. Batches lớn/cross-partition có thể tăng coordinator fan-out, batchlog/memtable/network pressure, và điều chỉnh warning/failure limit chỉ làm thí nghiệm rủi ro hơn. Thay vào đó dùng **prepared unbatched writes, bounded async concurrency, event ID ổn định**, chỉ dùng batch khi semantics atomicity/partition scope phù hợp và đã được benchmark.

### 20.4. Timeout phải có ngân sách end-to-end

Ví dụ, nếu API deadline 800 ms nhưng driver request timeout 5 s, một `CompletableFuture` còn chạy sau khi HTTP client bỏ cuộc vẫn có thể tiêu tài nguyên cluster. Thiết kế:

- API deadline tổng và cancellation/backpressure.
- Driver/server timeout theo operation/CL, tránh mâu thuẫn mù giữa các tầng.
- Max attempts + jitter + global retry budget, không retry vô hạn.
- Circuit breaker/admission policy dựa trên capacity thật, không biến lỗi thành empty success.
- Observability **request rate × attempts**, queue, p99, timeout và error class.

## 21. Thay cấu hình: so diff, xác định effective value, canary và rollback

### 21.1. Một cấu hình có thể đến từ nhiều nguồn

Trong triển khai thật, một giá trị có thể được đặt qua:

- `cassandra.yaml` và các files cấu hình node/version.
- Kubernetes operator CRD/Helm/ConfigMap/secret hoặc VM configuration management.
- `nodetool set...`/JMX dynamic setting (khi bản Cassandra hỗ trợ).
- JVM flags, OS limits, container resources và cgroup.
- Java Driver config (application.conf/reference.conf), application overrides và statement options.

**Source of truth quan trọng hơn lệnh chỉnh tay.** Nếu operator reconciles config từ Git, một thay đổi runtime JMX có thể bị ghi đè sau restart/reconciliation; ngược lại, sửa file YAML có thể **chưa có hiệu lực** cho tới khi node restart. Phải ghi **effective before/after**, không chỉ diff trong Git.

### 21.2. Ma trận change plan cho một setting

| Câu hỏi | Ví dụ điền biểu mẫu |
| --- | --- |
| Cụm và version | Cassandra 4.1.x, JDK được chứng nhận, Java Driver 4.x. |
| Setting và đơn vị | Exact property path, milliseconds/seconds/bytes/kB hoặc count; không suy tên. |
| Source of truth | Operator CRD hoặc config file; ai có quyền cập nhật? |
| Dynamic hay restart-only? | Kiểm tài liệu/chính binary; nếu cần restart thì cộng rủi ro **mỗi node down**. |
| Scope | Một canary node, một DC, cả cluster hoặc tất cả Java pods. |
| Behavior bị thay đổi | Fail-fast guardrail, request timeout, compaction throttle, retry/in-flight budget? |
| Risk gates | RF/CL, disk free, p99, queue, safe tombstone/repair policy. |
| Acceptance | Cùng workload, correct IDs/values, tỷ lệ lỗi nằm trong error budget và resource pressure ổn định. |
| Rollback | Giá trị trước, nguồn config, cách quay lại và **thời gian mất hiệu lực**. |

### 21.3. Quy trình rollout

1. Lưu **config diff** và giá trị effective của tất cả nodes/Java services sẽ bị ảnh hưởng.
2. Đánh giá thay đổi có làm **restart** không; nếu có, phải áp riêng **runbook rolling restart** ở mục 9.
3. Thử **staging/load** trên cùng Cassandra version với dữ liệu/query shape đại diện, chốt before/after metrics.
4. Áp trên **scope hẹp** nếu property và architecture cho phép, tránh config drift kéo dài; phối hợp coordinator/replica roles.
5. Quan sát traffic mix, error class, p95/p99, retry attempts, JVM/OS disk/GC, client queue trong một cửa sổ đủ dài.
6. Đo **correctness**: read/write CL, expected event IDs, TTL/delete/liveness, authorization và data retention.
7. Mở rộng node/DC/pod từng lượt, có stop criteria; nếu rollback, **revert cả source config và runtime value**.
8. Đọc lại effective settings sau restart/reconciliation, ghi change ID và loại bỏ override tạm.

### 21.4. Không dùng config canary “một node” sai phạm vi

Một query Cassandra có thể đi qua coordinator và nhiều replicas trên các nodes khác nhau. Nếu chỉ thay guardrail/timeout trên một node, **hành vi request phụ thuộc node được chọn**: có thể tạo lỗi không ổn định khó debug. Canary phải có cách **định tuyến/quan sát chính xác scope** và giới hạn thời gian; khi mở rộng cần đưa nodes về cùng cấu hình được duyệt.

## 22. Java Driver: read/write canary không chỉ là SELECT 1

### 22.1. Một canary theo đầy đủ partition key

Để chứng minh user-visible correctness, tạo **keyspace lab/probe riêng** hoặc partition IDs được phép, không đưa dữ liệu test vào bảng production không có policy. Một canary tốt có:

- **Write với stable event ID/full primary key**, ở `LOCAL_QUORUM`, log ACK/unknown.
- **Read cùng key** ở CL đã định, kiểm **event ID và value**, không chỉ response 200.
- **Bounded query time**, giới hạn row count/payload/page size.
- **Same query shape** trước/sau maintenance; một cặp key probes không đại diện toàn bộ cluster nhưng phát hiện regression thô.
- Metrics theo `query_name`, DC, error type, request attempt, p95/p99; không log raw tenant/device IDs.

### 22.2. CQL schema dành riêng cho thí nghiệm

~~~sql
-- CHỈ trên cluster test có BA full replicas trong dc1:
CREATE KEYSPACE IF NOT EXISTS ops_preflight
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS ops_preflight.events_by_device_day (
  tenant_id text,
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((tenant_id,device_id,event_day),event_time,event_id)
) WITH CLUSTERING ORDER BY (event_time DESC,event_id ASC);
~~~

**Không tạo RF3 trên một node duy nhất** rồi cố test `LOCAL_QUORUM`; quorum thực tế cần đủ full replicas. Để thử Java/CQL cơ bản trong Testcontainers một node, dùng **RF1 tại đúng local DC** và `LOCAL_ONE`, sau đó chạy bài kiểm thử RF3/LOCAL_QUORUM trên cluster nhiều node riêng.

### 22.3. Java Driver 4.x canary (Java 17)

~~~java
// CassandraChangeCanary.java
package example.cassandra.ops;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class CassandraChangeCanary {
    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement lookup;

    public CassandraChangeCanary(CqlSession session) {
        this.session = session; // Managed/lifecycle-shared session.
        this.insert = session.prepare(
            "INSERT INTO ops_preflight.events_by_device_day " +
            "(tenant_id,device_id,event_day,event_time,event_id,event_type,payload) " +
            "VALUES (?,?,?,?,?,?,?)");
        this.lookup = session.prepare(
            "SELECT event_id,payload,event_type " +
            "FROM ops_preflight.events_by_device_day " +
            "WHERE tenant_id=? AND device_id=? AND event_day=? " +
            "AND event_time=? AND event_id=?");
    }

    public void verify(String runId) {
        String tenant = "lab-tenant";
        String device = "canary-" + runId;
        LocalDate day = LocalDate.of(2026, 11, 21);
        Instant at = Instant.parse("2026-11-21T08:00:00Z");
        UUID id = UUID.nameUUIDFromBytes(
            ("change-canary:" + runId).getBytes(
                java.nio.charset.StandardCharsets.UTF_8));
        String expectedPayload = "alive-" + runId;

        BoundStatement write = insert.bind(
                tenant, device, day, at, id, "PROBE", expectedPayload)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(2))
            .setIdempotent(true);
        session.execute(write); // Exception/timeout => outcome classification.

        BoundStatement read = lookup.bind(
                tenant, device, day, at, id)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(2))
            .setPageSize(1);
        ResultSet result = session.execute(read);
        Row actual = result.one();
        if (actual == null
                || !id.equals(actual.getUuid("event_id"))
                || !expectedPayload.equals(actual.getString("payload"))) {
            throw new IllegalStateException("Canary value mismatch");
        }
    }
}
~~~

**Điều kiện của ví dụ:** fixture **không có TTL**, cùng full primary key/values khi retry và không có concurrent writer trên key test riêng, nên khai báo idempotent có thể phù hợp. Driver retry policy vẫn phải được kiểm soát; `WriteTimeout` có thể có **unknown outcome**, không tự sinh `runId` mới cho cùng logical operation trong bước reconcile. `CqlSession` do application quản lý, **không** đóng/tạo mới theo mỗi request. `Duration.ofSeconds(2)` là sample deadline, không phải mức chuẩn cho mọi cluster.

### 22.4. Đừng hiểu canary sai

`SELECT LOCAL_QUORUM` thành công trên một key **không chứng minh replica còn lại đã repair toàn bộ token ranges**. Một canary **không** phát hiện mọi SSTable corruption nếu row test nằm ở file/range khác; cần kết hợp repair/verify/logs và data ledger có coverage. Tương tự, nếu bỏ lỗi bằng `catch(Exception){return List.of();}`, canary sẽ trở nên vô nghĩa.

## 23. Môi trường thí nghiệm an toàn: riêng cụm, không giả lập dữ liệu thật

### 23.1. Cấu hình test

~~~text
Cluster            : dedicated testing Cassandra cluster, no production data
Nodes              : R1, R2, R3 (full replicas, dc1, distinct rack metadata)
NTS RF(dc1)        : 3
Read/write CL      : LOCAL_QUORUM (test 3-node)
Java Driver        : 4.x, one managed session, bounded requests
Table              : ops_preflight.events_by_device_day
Data identity      : stable runId/eventId, predictable event_time
Observability      : per-node metrics/logs, UTC markers, CQL ledger
Storage            : enough headroom, separate snapshots/backup paths
Recovery           : scripted start/stop, verified original volumes
No-go              : accidental prod endpoint/cluster ID mismatch
~~~

Nếu dùng Docker Compose ba node trên một host, thí nghiệm có ba Cassandra **processes/replicas** nhưng **không phải ba failure domains** vật lý; mất Docker host sẽ làm cả ba node mất. Với cluster production-like cần kiểm rack/DC/storage/network thực.

### 23.2. Bốn lượt thử độc lập

| Lượt | Một thay đổi duy nhất | Cần chứng minh |
| --- | --- | --- |
| **R1** | Restart node R3 khi R1/R2 khỏe. | Client CL còn đáp ứng, node restart và catch-up, p99/error/hint backlog trong budget. |
| **R2** | Scrub một **table đã có corruption lab được tạo có chủ đích**, với backup/replica khỏe. | Không phá dữ liệu sống, corruption report được xử lý, repair/restore path khả dụng. |
| **R3** | Major compact một table/test node có dữ liệu đủ lớn nhưng bounded. | Disk headroom, p99/GC không vượt giới hạn, IDs/TTLs/deletes đúng, SSTables impact được đo. |
| **R4** | Nới một guardrail/timeout **trong môi trường test**. | Hiểu khác biệt fail-fast vs load, evidence config scope và rollback, không phá CL/consistency. |

**Không chạy cả bốn cùng lúc.** Giữ data fixture/query/CL và offered rate tương đương để cô lập tác động; nếu thay nhiều biến, kết luận “restart tốt lên” không có cơ sở.

### 23.3. Stop/abort là một phần của bài kiểm thử

- Fault injector phải xác minh **cluster ID** và danh sách nodes cố định; không có quyền dừng một production host.
- Mỗi thao tác có **deadline** và operator owner; `finally`/cleanup khôi phục process/config khi test fail.
- Khi disk xuống dưới headroom, errors p99 tăng vượt budget hoặc mất quorum, dừng mở rộng change và **khôi phục availability trước**.
- Cleanup không được tự động `docker compose down -v` nếu còn cần volumes để forensic/reconcile.
- Không chạy lệnh `nodetool scrub` trên corruption fixture duy nhất nếu chưa có snapshot/backup/copy sạch.

## 24. Kịch bản kiểm thử correctness trước–trong–sau thay đổi

### 24.1. Lập ledger, không chỉ đếm rows

~~~text
run_id:                CHG-001-LAB
operation_id:          stable event UUID
full_partition_key:    (tenant, device, event_day)
full_clustering_key:   (event_time, event_id)
expected_event_type:   PROBE
expected_payload_hash: SHA-256 of payload
write_acked:           true/false/unknown
expected_liveness:     live | deleted | expired
expected_ttl_expiry:   if relevant
consistency_level:     LOCAL_QUORUM
phase:                 baseline | during | recovery | after
~~~

Với `DELETE`, row đã xóa không còn trong kết quả read đúng CL **không** chứng minh mọi replica đã nhận tombstone; cần repair/replica validation theo scope. Với `TTL`, time-based expiration không phải physical SSTable deletion. Một `COUNT(*)` có thể bằng nhau khi ID A mất và ID B bị ghi trùng, nên ledger cần **set IDs + values + delete states**.

### 24.2. Bộ assertions trong một test

| Check | Trước change | Trong change | Sau change |
| --- | --- | --- | --- |
| RF/CL/membership | R1/R2/R3 và token/rack đúng. | Các replicas còn lại đủ CL. | Target `UN`, không còn unexpected down nodes. |
| CQL write/read | Baseline IDs/values match. | ACK/timeout/unavailable được phân loại đúng. | Expected ACKed IDs/values còn đọc được ở CL đã định. |
| TTL/delete | Expiry/deletes theo fixture. | Không giảm grace/để stale copy tái xuất hiện. | Không zombie/retention regression được quan sát trong scope test. |
| Performance | p95/p99, offered/achieved RPS, CPU/disk/GC. | Error/latency trong stop budget. | Về baseline/target khi load tương đương. |
| Maintenance | Không có conflicting jobs. | Task progress/hints/compaction/streaming. | Coverage/cleanup và config values được xác nhận. |
| Rollback | Backup/config trước còn truy xuất được. | Operator có khả năng dừng mở rộng. | Roll forward/restore/revert có evidence thành công. |

### 24.3. Thử negative cases

1. **Một replica đã down trước**: restart replica thứ hai phải bị **NO-GO**.
2. **Disk headroom thiếu**: scrub/major compact phải bị chặn trước khi rewrite.
3. **Backup không restore được**: scrub destructive không được triển khai.
4. **CL=ALL**: một-node outage thay đổi availability rõ rệt; không giả định LOCAL_QUORUM contract.
5. **Write timeout giữa restart**: ledger để `unknown`, retry với **stable full primary key**, không tạo duplicate logical event.
6. **Config drift**: một node dùng tombstone threshold khác; canary phát hiện inconsistent failure behavior.
7. **Unknown `gc_grace_seconds`/repair lag**: không purge/dọn data, escalate.
8. **Node lên nhưng hint backlog còn lớn**: không cho restart node tiếp theo chỉ nhờ `status=UN`.

## 25. Đo tải mà không nhầm offered throughput với achieved throughput

### 25.1. Chọn một workload cố định

~~~text
Query mix   : 70% bounded reads, 30% idempotent inserts (example)
Partition   : telemetry by device/day; representative skew distribution
Row bytes   : fixed distribution, include wide payload tail
CL          : LOCAL_QUORUM, RF=3 full replicas in dc1
Driver      : same version, pool, retry and page size each run
Rate        : fixed bounded arrival rate with backpressure
Duration    : warmup + steady + change + recovery, UTC markers
Evidence    : request rate/offered, completed, errors, p99,
              pending/futures, disk/GC, hints, compaction and ledger
~~~

Các tỷ lệ 70/30 và giá trị rate là **giả định học tập**, không phải chuẩn Cassandra. Thay bằng workload sản phẩm thực tế nhưng không đổi chúng giữa benchmark baseline và canary để tránh confounding.

### 25.2. Closed-loop có thể che overload

Closed-loop client gửi request kế tiếp khi request trước xong; khi Cassandra chậm, **offered rate tự giảm** nên histogram p99 trông có vẻ không tệ như thực tế. Open-loop có lịch phát request độc lập latency nhưng cần **bounded queue/in-flight** để không phá cluster. Đo coordinated omission, offered vs completed rate, rejected/timeout/retry attempts; không chỉ báo RPS của load generator.

### 25.3. KPI phải gồm correctness

Một change không pass nếu p99 cải thiện nhưng:

- `LOCAL_QUORUM` bị thay âm thầm thành `LOCAL_ONE`.
- Event IDs đã ACK bị thiếu, payload sai hoặc deletes được resurrect.
- Scrub bỏ corrupted rows mà không có restore/reconciliation.
- Snapshot/backup không còn có thể restore.
- Config drift khiến request phụ thuộc coordinator ngẫu nhiên.
- Compaction làm disk chạm ngưỡng nguy hiểm và ảnh hưởng đến writes khác.

## 26. Observability: nhìn cùng một timeline, đúng node và scope

~~~mermaid
flowchart TD
    A["Change marker UTC"] --> B["HTTP latency, error, throughput, retry"]
    A --> C["Driver coordinator, in-flight, timeout, queue"]
    A --> D["Node JVM/OS: GC, disk, CPU, network"]
    A --> E["SSTables, compaction, hints, repair"]
    B --> F["Correlate by query_name, CL, node/DC, same time window"]
    C --> F
    D --> F
    E --> F
    F --> G["Data ledger, health gates và quyết định tiếp theo"]
~~~

| Nguồn | Điều ghi nhận | Giới hạn |
| --- | --- | --- |
| API metrics | p50/p95/p99, HTTP timeout, cancellations, calls, bytes, retry decision. | 200 không chứng minh mọi replica đồng bộ. |
| Java Driver | CQL attempts, coordinator distribution, CL, in-flight, throttler, result warnings. | Contact point không nhất thiết là natural replica. |
| Cassandra read/write metrics | Latency, unavailable/timeouts, pending/dropped tasks, tombstone/SSTable histograms. | Một node histogram không đại diện cả cluster. |
| Compaction stats | Active/pending tasks, progress, throughput, SSTables. | Task complete không chứng minh mọi deleted row đã purge an toàn. |
| Hint/repair logs | Hint queue/delivery, token ranges, streaming, repair participants, failures. | Queue rỗng không chứng minh mọi missing mutation từng có hint. |
| OS/JVM | Disk free/await, CPU, GC pauses, off-heap, network RTT. | Không tự cho biết SQL/CQL query nào làm tăng tải. |
| CQL ledger | Expected ACKed IDs/values/liveness theo partition. | Một sampled partition không chứng minh toàn bộ token ranges. |

**Metric cardinality:** dùng `query_name`, `change_id`, `local_dc`, `node`, `operation`, `outcome` ở mức vừa phải; không gắn raw `tenant_id`, `device_id`, UUID mỗi request hay payload vào histogram labels. Forensic IDs được sample/redact và lưu có kiểm soát.

## 27. Sơ đồ chọn thao tác khi đang trực sự cố

~~~mermaid
flowchart TD
    A["Incident: Cassandra errors/p99/disk/GC"] --> B["Lấy evidence: logs, RF/CL, data health, metrics"]
    B --> C{"Đủ full replicas để maintenance một node?"}
    C -->|Không| D["NO-GO: khôi phục availability / data sources trước"]
    C -->|Có| E{"Nguyên nhân đã xác nhận?"}
    E -->|JVM/process stuck| F["Review rolling restart; kiểm binary/config/startup"]
    E -->|SSTable corruption| G["Review backup/replica health, scrub/restore path"]
    E -->|SSTable layout/compaction debt| H["Review compaction strategy, disk/IO headroom"]
    E -->|Guardrail/timeout/batch| I["Review query/data model và resource budget trước khi nới"]
    E -->|Chưa rõ| J["Chạy diagnostic bounded, không đổi nhiều biến"]
    J --> B
    F --> K["Canary một node/table/config scope"]
    G --> K
    H --> K
    I --> K
    K --> L{"Correctness + p99 + headroom + repair gates đạt?"}
    L -->|Không| M["STOP, restore availability / revert / restore data"]
    L -->|Có| N["Mở rộng có điều phối; audit & follow-up"]
~~~

### 27.1. Không biến sơ đồ thành lệnh tự động

Không có rule “log corrupt SSTable → scrub ngay”. Mỗi nhánh còn phải xác minh **replica nào giữ dữ liệu tốt**, có snapshot/backup đã được thử, lệnh phù hợp Cassandra version, và ai phê duyệt nguy cơ bỏ dữ liệu. Tương tự, nhánh restart vẫn yêu cầu **RF/CL** và điều kiện không có maintenance chồng lấp.

## 28. Case study A — Restart một node gần như làm mất quorum

### 28.1. Bối cảnh giả lập

Cluster `dc1` có RF3 cho `telemetry_ops`. `R1=UN`, `R2=UN` nhưng `R2` thường xuyên read timeout do disk latency, `R3=DN` từ một sự cố network. Ứng dụng Java dùng `LOCAL_QUORUM`; một kỹ sư đề nghị **restart R2 để chữa disk stall**.

| Tín hiệu trước thay đổi | Quan sát | Ý nghĩa |
| --- | --- | --- |
| R3 `DN` | Một full replica đã vắng mặt. | Không còn đầy đủ RF3 responses. |
| R1 `UN` | Một replica khỏe. | Chưa đủ `LOCAL_QUORUM` một mình. |
| R2 `UN`, disk await/p99 cao | Replica còn hoạt động nhưng chậm. | Tính khả dụng thực tế yếu. |
| `LOCAL_QUORUM` read/write | Cần hai full responses. | Dừng R2 sẽ làm quorum không đáp ứng. |

**Quyết định:** **NO-GO restart R2** trước khi R3 phục hồi hoặc có kế hoạch availability được phê duyệt. Trước hết giảm workload phi thiết yếu, điều tra disk/network của R2, khôi phục R3 và chứng minh R1/R3 đáp ứng đúng CL, rồi mới đánh giá restart R2.

### 28.2. Nếu ai đó đã restart R2?

- Các writes/read ở `LOCAL_QUORUM` có thể trả `Unavailable` hoặc timeout khi chỉ R1 đủ điều kiện.
- Driver retry vào các coordinators còn sống **không tạo ra replica quorum thứ hai**.
- Thay nhanh CL sang `LOCAL_ONE` có thể tăng availability nhưng **thay hợp đồng nhất quán/durability**, cần decision record riêng và không thay đổi ngầm.
- Khi R2/R3 hồi phục, phải xem hints/repair/commit-log replay và **ledger writes đã ACK/unknown**; `UN` không tự chứng minh dữ liệu đã hội tụ.

### 28.3. Bài học

Một lệnh restart có vẻ đơn giản nhưng **blast radius phụ thuộc topology và CL**, không phụ thuộc mức độ quen tay với `systemctl restart`.

## 29. Case study B — Scrub corruption nhưng không có nguồn phục hồi

Một node `R3` báo checksum error trên một SSTable của table lưu trạng thái thiết bị. Cụm vẫn trả `LOCAL_QUORUM` read thành công ở các query mẫu. Người trực đề xuất `nodetool scrub --skip-corrupted` để loại bỏ file lỗi và cho pager hết báo động.

### 29.1. Điều đang được biết và chưa biết

**Biết:** R3 có một SSTable lỗi; một số quorum reads vẫn chạy.

**Chưa biết:** 

- R1/R2 có đầy đủ cell/tombstone cho **mọi partition/token range** của SSTable lỗi không?
- Các replicas còn bất đồng dữ liệu nào vì hints missing, repair trễ hoặc xóa đã hết grace không?
- Snapshot trước đây và bản backup off-cluster có đọc/restore được không?
- Lỗi là checksum file, disk I/O phần cứng hay metadata format không tương thích?
- Scrub mode được chọn có **bỏ** corrupted partitions không và business có chấp nhận không?

### 29.2. Quyết định

**NO-GO scrub có khả năng bỏ data khi chưa có nguồn tin cậy và rollback plan.** Có thể trước tiên dùng verification/logs/read-only triage, cô lập storage disk nếu cần, bảo vệ files/metadata và xác minh backup/replica sets. Sau khi được phê duyệt, scrub chỉ table/node trong phạm vi, ghi rõ corrupted rows/ranges, rồi dùng anti-entropy/restore/reconciliation theo kế hoạch.

### 29.3. False success

`scrub exit 0` + `nodetool status UN` + `SELECT LIMIT 1` trả dữ liệu **không chứng minh** corrupted rows đã trở về. Cần đối chiếu **expected IDs/values/tombstone states**, logs, repair coverage và những partition/keyspace thực sự bị ảnh hưởng.

## 30. Case study C — Major compaction làm đầy disk dù số SSTables giảm

### 30.1. Dữ liệu giả lập

Một node có table time-series chứa 500 GiB SSTables, data volume còn trống 180 GiB; có snapshots giữ 250 GiB old blocks. P99 của một query tăng do SSTablesPerRead cao, kỹ sư đề nghị major compaction cả table và kỳ vọng số file ít hơn sẽ giảm disk used ngay.

**Rủi ro:**

- Output rewrite có thể cần **hàng trăm GiB** trước khi inputs được thu hồi.
- Snapshots giữ hard links của inputs, khiến old blocks **không được giải phóng** khi compaction hoàn thành.
- Compaction tiêu I/O/CPU, có thể làm write latency tăng và commitlog/hints tiếp tục sử dụng disk.
- Nếu table dùng TWCS/time-window TTL, bố trí SSTable sau major compact cần được đánh giá theo version/workload.

### 30.2. Quyết định

**NO-GO major compaction khi headroom không chứng minh đủ.** Thu `compactionstats`, snapshot list, physical disk usage, observed output ratio, SSTablesPerRead/tombstone metrics, benchmark trên staging. Có thể ưu tiên:

1. Giảm batch/backfill hoặc read queries không cần thiết theo business policy.
2. Điều chỉnh **automatic compaction throughput/concurrency** ở mức đã đo, tránh để compaction backlog tăng vô hạn.
3. Xử lý snapshot retention **sau khi kiểm backup policy**, không xóa bản duy nhất tùy tiện.
4. Tăng headroom/storage hoặc chuyển workload/schema mới với bucket đúng.
5. Chỉ sau đó mới thử scoped compaction nếu trade-off và disk budget đạt.

### 30.3. Bài học

“SSTable file count ít hơn” có thể là chỉ số phụ; **disk, IO, data correctness và p99 của foreground traffic** mới là tiêu chí phê duyệt.

## 31. Case study D — Nới timeout/guardrail làm retry storm khó thấy hơn

Một API Java đọc 20 events nhưng thường phải quét hàng chục nghìn tombstones. `tombstone_failure_threshold` bắt đầu chặn các truy vấn xấu, và HTTP nhận 5xx. Một đề xuất tăng limit lên 10 lần và tăng driver timeout từ 1 giây lên 15 giây.

| Metric giả lập | Trước thay đổi | Sau khi nới limit không sửa query |
| --- | ---: | ---: |
| Offered API requests/s | 600 | 600 |
| Cassandra attempts/s (bao gồm retry) | 750 | 1.450 |
| Mean request lifetime | 120 ms | 850 ms |
| Concurrent requests ước tính nếu ổn định (ở cùng throughput) | Thấp hơn | Cao hơn đáng kể |
| Tombstones mỗi query | Không đổi | Không đổi |
| CPU/disk/GC trên replicas nóng | Cao | Cao hơn |
| HTTP failures | Rõ và nhanh | Có thể ít hơn ban đầu nhưng latency/queue xấu |

**Số liệu hoàn toàn giả lập**, không phải benchmark Cassandra. Khi fail-fast giảm, một truy vấn có thể tiếp tục làm việc rất lâu, trong khi client/HTTP retries tăng do deadline không đồng nhất. Kết quả là **retry amplification** dù số lỗi loại “tombstone failure” giảm.

**Hướng sửa:** audit CQL `WHERE`/clustering range, bucket/partition key, `TTL`/range `DELETE`/mapper `null`, compaction/repair state; giới hạn API requests, projection, page/rows, retries và in-flight. Nếu buộc phải nới ngưỡng tạm, đặt expiry/change ticket, canary scope, p99/error/disk/GC stop criteria và rollback tự động hóa an toàn; không tuyên bố sửa tận gốc.

## 32. Rollback có bốn nghĩa — cần nói chính xác loại nào

| Change đã thực hiện | “Rollback” thực tế | Không được tự hứa |
| --- | --- | --- |
| Restart cùng binary/config | Start node, restore original config/image nếu vừa đổi, kiểm ring, hints, repair và canaries. | Start xong là không mất writes/mutations. |
| Scrub SSTables | Dùng snapshot/backup đã kiểm thử hoặc replica data source để restore/rebuild theo runbook; có thể phải repair/reconcile. | Một lệnh `nodetool undo scrub` hoặc restart tự đưa bytes cũ về. |
| Major compaction | Dừng tiếp tục công việc, xử lý temp artifacts, điều chỉnh automatic compaction/capacity; dữ liệu đúng vẫn dùng được. | `stop COMPACTION` đảo toàn bộ SSTable layout về trước. |
| Runtime guardrail/timeout | Khôi phục effective value trên nodes/app, sửa source-of-truth và xác minh sau restart. | Undo các writes, deletions hay timeouts đã xảy ra lúc limit khác. |
| Thay compaction strategy | Revert schema/config theo version/approval, đánh giá SSTables đã rewrite và lịch compaction mới. | File layout quay tức thì như trước. |
| Dọn snapshots / xoá backup | Chỉ có thể khôi phục nếu còn bản sao ngoài node/retention. | Có “undo delete backup” khi files đã bị purge hoàn toàn. |

### 32.1. Recovery ≠ restart ≠ repair ≠ restore

- **Restart**: phục hồi process availability, không tự tái tạo missing cells.
- **Repair**: so và đồng bộ replicas cùng token ranges khi có nguồn dữ liệu/deletion markers thích hợp, không sinh data đã mất ở mọi bản.
- **Restore**: đưa SSTables/logical data từ backup có source/version/metadata phù hợp, có thể cần import/streaming/reconciliation; không hot-copy files vào node đang ghi.
- **Rebuild/replace**: vận hành topology/node replacement theo version, host ID/token/streaming; không phải cùng một node cũ start lại.
- **Roll back config**: thay behavior từ nay, không quay ngược mutations lịch sử.

### 32.2. Biên bản stop/rollback

~~~text
Reason          : Disk free under threshold / quorum unavailable / mismatch
Change ID       : ...
Time UTC        : ...
Affected scope  : node/table/config key/cluster ...
Action stopped  : ...
Data rewritten? : yes/no/unknown
Backup          : manifest/checksum/restore tested? ...
Restore path    : replica repair / snapshot import / replacement / no action
Owner           : ...
Next safe step  : ...
Evidence        : logs, old/new metrics, expected IDs/values
~~~

**Đừng che thiếu dữ liệu bằng từ “rollback thành công”** nếu mới revert một cấu hình hoặc start lại process. Cần trả lời **trạng thái dữ liệu nào đã được phục hồi và đã đối chiếu tới phạm vi nào**.

## 33. Những phản mẫu cần tránh

| Phản mẫu | Vì sao sai | Biện pháp đúng |
| --- | --- | --- |
| Restart nhiều Cassandra nodes cùng lúc vì “mỗi lần chỉ vài phút”. | Tụt quorum, tạo hint backlog, cold caches và traffic rebalance. | Một node/rack/DC theo RF/CL và gates. |
| Thấy `UN` là cho restart node kế. | Hints/repair/startup load có thể chưa kết thúc. | Kiểm data/replica catch-up và SLO ổn định. |
| `nodetool drain` rồi trông chờ node hoạt động bình thường không restart. | Drain không phải “pause traffic tạm” rồi resume tự động. | Theo full shutdown/restart runbook. |
| Restart để sửa SSTable checksum error. | Corruption trên disk còn nguyên. | Check storage/backup/replica integrity; scrub/restore nếu phù hợp. |
| Chạy scrub mọi tables “để dọn dữ liệu”. | Tốn IO và có nguy cơ bỏ corrupt records, không phải cleanup định kỳ. | Chỉ scrub scope được chẩn đoán có corruption. |
| Chạy offline `sstablescrub` trên data directory live. | Node còn đang flush/compact và file có thể thay đổi. | Stop đúng process và quy trình offline tool/version. |
| Dùng flag skip-corrupted chỉ để thoát lỗi nhanh. | Có thể làm mất rows/partitions. | Approval/data source/ledger và restore plan. |
| Snapshot local hardlinks = backup an toàn khỏi disk hỏng. | Cùng storage có thể mất/corrupt; snapshot có thể giữ corruption. | Off-cluster backup được checksum/restore-test. |
| Major compact toàn cụm khi disk gần đầy. | Rewrite cần temp headroom và snapshots giữ old files. | Capacity/preflight/scoped canary, không chạy đồng thời. |
| Major compact TWCS để “gộp càng ít file càng tốt”. | Có thể hại window-based expiration/IO policy. | Benchmark theo version/late data/TTL. |
| `nodetool stop COMPACTION` = undo SSTables. | Stop task không phải rollback transaction. | Verify file/task state, dùng backup nếu cần. |
| Lower `gc_grace_seconds=0` để giảm tombstones. | Replica miss delete có thể làm zombie data. | Repair cadence và grace policy an toàn. |
| Tăng `tombstone_failure_threshold` cho API hết lỗi. | Chuyển fail-fast thành scan tốn tài nguyên. | Sửa query/retention/partition model. |
| Tăng driver timeout nhưng HTTP deadline nhỏ hơn nhiều. | In-flight queries tiếp tục sau khi caller bỏ cuộc. | Đồng bộ deadlines/cancellation/backpressure. |
| Mở pool/connection count vô hạn để “chữa lỗi”. | Làm hot replicas và queues bão hòa. | Admission, bounded in-flight, retries và capacity plan. |
| Dùng `BATCH` nghìn partitions để tăng throughput. | Batchlog/fan-out/memory cost và size warnings. | Prepared unbatched writes concurrency bounded. |
| Tăng CQL mutation size cap thay vì sửa payload schema. | Rủi ro commitlog/memtable/network/GC. | Chunk/normalize/blob storage theo use case. |
| Thay config bằng JMX nhưng quên source-of-truth. | Operator/restart có thể trả lại giá trị cũ hoặc tạo config drift. | Track effective+desired config, reconcile đầy đủ. |
| Đọc `SELECT LOCAL_QUORUM` đúng = R3 đã phục hồi. | Có thể đọc từ hai replicas khỏe. | Hints/repair/replica-specific validation đúng scope. |
| `COUNT(*)` khớp = dữ liệu đã khôi phục. | Mất ID A + trùng ID B vẫn cùng count. | Ledger full PK/values/delete states. |
| Bật tracing mọi requests khi cluster đang overload. | Tracing tạo thêm IO/metadata overhead. | Selective sampled traces, cấu trúc log hợp lý. |
| Chạy scrub, compact, repair, upgrade cùng một window. | Khó cô lập nguyên nhân và tiêu tài nguyên chồng lấp. | Tách phases, stop criteria và mỗi change một hypothesis. |
| Chỉ báo p99 giảm, bỏ qua offered rate giảm. | Benchmark bị coordinated omission/tải ít hơn. | So cùng query mix, offered/achieved rate, errors. |
| Catch `Exception` rồi trả `[]` cho Cassandra timeout. | Biến lỗi thành “không có dữ liệu”, phá correctness. | Map error classes và retry/HTTP contract đúng. |

## 34. Nhận định đúng/sai để tránh thay đổi sai trong ca trực

| Nhận định | Đúng/sai | Vì sao |
| --- | --- | --- |
| “`nodetool status UN` chứng minh mọi replica đã hội tụ.” | **Sai** | Membership không chứng minh repair/hints/token ranges đúng. |
| “RF3/LOCAL_QUORUM cần hai full replica responses trong local DC.” | **Đúng** | Với một DC có RF3 full replicas và CL tương ứng. |
| “R3 down, R1/R2 còn khỏe; restart R2 vẫn không ảnh hưởng quorum.” | **Sai** | Chỉ còn R1, không đủ LOCAL_QUORUM 2/3. |
| “Restart làm SSTable corrupt tự hồi phục.” | **Sai** | Corruption trên disk cần điều tra storage/verify/scrub/restore. |
| “`nodetool drain` có thể dùng như nút pause/resume mà không restart.” | **Sai** | Drain là bước shutdown/flush có semantics cần restart process. |
| “Scrub có thể rewrite data và cần backup/replica nguồn tin cậy.” | **Đúng** | Có nguy cơ bỏ corrupted rows/partitions theo mode. |
| “Offline `sstablescrub` có thể chạy an toàn khi live process đang compact.” | **Sai** | Cần stop process/quy trình offline đúng. |
| “Snapshot local bảo vệ chắc chắn khỏi hỏng toàn ổ đĩa.” | **Sai** | Hardlinks cùng storage, có thể chứa bytes corrupt. |
| “Khi corruption ở mọi replicas, repair tự khôi phục row đã mất.” | **Sai** | Không có source thì repair không sáng tạo dữ liệu. |
| “Major compaction có thể cần temp disk lớn và làm p99 xấu.” | **Đúng** | Rewrite SSTables tranh disk/CPU/IO và snapshots giữ old blocks. |
| “Compaction tự xóa mọi tombstone sau `gc_grace_seconds`.” | **Sai** | Còn overlap/repaired state/strategy/scheduling. |
| “TWCS lúc nào cũng được lợi khi major compact tất cả files.” | **Sai** | Time-window retention/late writes có trade-off. |
| “Đổi compaction strategy sẽ đổi partition key/hash token.” | **Sai** | Không thay data model. |
| “Một threshold cao hơn có thể tăng blast radius của query tốn tài nguyên.” | **Đúng** | Fail-fast mất tác dụng và request quét lâu hơn. |
| “Driver page size=20 bảo đảm replica chỉ scan 20 tombstones.” | **Sai** | Page size là network hint, không phải storage scan cap. |
| “Tăng driver timeout không làm CQL query tự tối ưu hơn.” | **Đúng** | Chỉ đổi thời gian chờ, có thể tăng in-flight. |
| “CQL BATCH càng lớn thì throughput càng cao.” | **Sai** | Cross-partition batches tăng fan-out/batchlog, không phải bulk-load acceleration. |
| “Timeout write luôn chứng minh mutation chưa apply.” | **Sai** | Outcome unknown, có thể đã có replica apply. |
| “Chỉ cần revert JMX value là mọi mutation bị ảnh hưởng sẽ undo.” | **Sai** | Runtime config không rollback data. |
| “Test correctness cần so IDs/values, không chỉ counts.” | **Đúng** | Đếm bằng nhau có thể che missing/duplicate. |
| “Repair một table/range là full-cluster repair.” | **Sai** | Phải ghi rõ token/table/DC/participants scope. |
| “Một canary sample không chứng minh mọi SSTable sạch.” | **Đúng** | Cần bổ sung verification/repair/coverage. |
| “Thêm node luôn làm một hot partition phân phối trên mọi node.” | **Sai** | Partition token có natural replica set; cần query/schema fix. |
| “Rollback config, khôi phục backup và rebuild node là các hành động khác nhau.” | **Đúng** | Khác scope/cost/data-safety. |

## 35. Bài tập tình huống có đáp án

**Bài 1.** Một DC có RF3 full replicas, application dùng `LOCAL_QUORUM`. R3 down; R1 và R2 còn khỏe. Khi bảo trì phải dừng R2, có thể thực hiện ngay không?

**Đáp án:** **Không.** `LOCAL_QUORUM` cần hai full replicas. Sau khi dừng R2 chỉ còn R1 nên không đủ quorum; phải khôi phục R3 hoặc có maintenance/availability plan được phê duyệt, không tự downgrade CL.

**Bài 2.** Một keyspace RF3 có `CL=ALL` cho write. R3 dừng để rolling restart; R1/R2 còn up. Write có thể đạt ALL không?

**Đáp án:** **Không.** ALL cần đủ ba full replica responses (trong một DC của ví dụ), nên outage một replica làm thay đổi availability. Đây là lý do phải thống kê CL **theo workload** chứ không chỉ số node.

**Bài 3.** Vì sao restart coordinator không đồng nghĩa restart natural replica của một key?

**Đáp án:** Coordinator nhận CQL request và điều phối; natural replica do partition token + replication strategy quyết định. Driver có thể chọn coordinator không giữ key, và coordinator vẫn gửi read/write đến các replicas tương ứng.

**Bài 4.** `nodetool status` hiện ba node `UN`. Có đủ chứng minh dữ liệu đã hội tụ sau một outage dài không?

**Đáp án:** **Không.** `UN` là membership, chưa chứng minh hinted handoff/repair đã hoàn tất hoặc tombstones/delete history an toàn. Cần data ledger, hint/repair evidence đúng ranges/tables/DCs.

**Bài 5.** Trong rollout, vì sao cần chờ node vừa restart hết startup exceptions, hints backlog và p99 ổn định trước khi restart node kế?

**Đáp án:** `UN` có thể xuất hiện khi node vẫn catch up/cold cache/compaction. Restart tiếp sẽ giảm redundancy và làm quá tải replicas còn lại; phải xác minh **quorum và resource headroom thực**.

**Bài 6.** `nodetool drain` xong thì node có tự tiếp tục phục vụ sau vài phút không?

**Đáp án:** **Không.** Drain là bước flush/shutdown semantics, thường yêu cầu process restart để trở lại phục vụ; dùng theo runbook, không coi như pause/resume tạm.

**Bài 7.** SSTable checksum lỗi ở R3, nhưng một `SELECT LOCAL_QUORUM` vẫn trả đúng một key. Đã chắc R1/R2 giữ đủ mọi data của SSTable lỗi chưa?

**Đáp án:** **Chưa.** Quorum read một key không xác minh mọi token range/cell/tombstone. Trước scrub cần kiểm nguồn restore/healthy replicas, backup và scope corruption.

**Bài 8.** Điểm khác nhau quan trọng giữa `nodetool scrub` và `sstablescrub`?

**Đáp án:** `nodetool scrub` điều khiển thao tác qua node/JMX, còn `sstablescrub` là công cụ **offline** cho SSTable files khi process liên quan đã dừng theo quy trình. Cú pháp/options/version khác nhau; cả hai cần backup và kế hoạch dữ liệu.

**Bài 9.** Nếu scrub ở chế độ bỏ dữ liệu corrupt và exit 0, có thể coi dữ liệu đã được khôi phục đầy đủ không?

**Đáp án:** **Không.** Exit 0 có thể chỉ nói tool xử lý xong theo policy, kể cả bỏ một số rows. Phải so expected IDs/values, logs và dùng healthy replica/backup/repair/restore khi cần.

**Bài 10.** Vì sao một local snapshot được tạo trước scrub chưa chắc là backup tốt?

**Đáp án:** Snapshot SSTable thường là hardlinks trên **cùng storage** và có thể giữ **chính bytes đã corrupt**. Cần off-cluster backup/checksum/restore rehearsal hoặc nguồn dữ liệu khỏe khác.

**Bài 11.** Sau scrub, R3 đã mất một row và mọi replicas/backup cũng không còn. Full repair có tái tạo được không?

**Đáp án:** **Không.** Repair chỉ đồng bộ những dữ liệu còn có ở một nguồn; cần nguồn ngoài cluster như CDC/event log/backup hoặc báo mất dữ liệu theo quy trình.

**Bài 12.** Major compact một table 420 GiB SSTables trên ổ chỉ còn 80 GiB trống. Có đủ chỗ không?

**Đáp án:** **Không thể khẳng định đủ** chỉ từ số đó; rewrite output có thể cần nhiều hơn 80 GiB trước khi xóa inputs, còn snapshots/commitlog/hints dùng disk. **NO-GO** đến khi tính và xác minh headroom.

**Bài 13.** Snapshot đang hard-link các old SSTables. Sau major compaction, vì sao disk used có thể không giảm?

**Đáp án:** Snapshot vẫn giữ references tới old blocks. Files cũ có thể không được trả space cho filesystem cho tới khi snapshot được xóa theo retention/approval; không xóa mù bản backup còn cần.

**Bài 14.** Một table có TTL và TWCS. Có nên major compact tất cả SSTables để “còn một file” không?

**Đáp án:** **Không mặc định.** TWCS dựa vào time windows/expired SSTable drop, late writes/deletes và cross-window rewrite có thể ảnh hưởng purge/IO. Phải kiểm behavior version cụ thể và benchmark.

**Bài 15.** Tombstone qua `gc_grace_seconds` đã chắc được xóa khỏi disk chưa?

**Đáp án:** **Chưa.** Còn compaction selection, SSTable overlap, data versions, repaired state và tombstone purge conditions; không có deadline dọn file chính xác từ grace.

**Bài 16.** Một replica chưa nhận DELETE, tombstone ở các replicas khác bị purge quá sớm. Điều gì có thể xảy ra?

**Đáp án:** **Zombie data**, tức row cũ có thể tái xuất hiện khi replica lâu ngày quay lại/anti-entropy. Cần repair coverage và grace policy phù hợp, không giảm grace vô căn cứ.

**Bài 17.** CQL `SELECT ... LIMIT 20` quét 100.000 tombstones. Tăng `tombstone_failure_threshold` có làm scan ít tombstones hơn không?

**Đáp án:** **Không.** Nó chỉ có thể cho query quét tiếp thay vì fail-fast; nguồn tombstone/query vẫn đó, chi phí CPU/disk/latency có thể tăng.

**Bài 18.** Tăng driver request timeout từ 1s lên 15s trong khi API deadline vẫn 800ms có rủi ro gì?

**Đáp án:** CQL requests/in-flight có thể sống lâu hơn request HTTP, tiêu tài nguyên khi caller đã bỏ cuộc; nếu retry thêm, tải bị khuếch đại. Cần end-to-end deadline/cancellation/queuing policy.

**Bài 19.** 400 requests/s, mean response time tăng từ 50ms lên 200ms. Với mô hình ổn định, in-flight trung bình tăng ra sao?

**Đáp án:** Theo Little's Law `L≈λW`, từ `400×0,05=20` lên `400×0,20=80` requests, tăng 4 lần. Đây là **ước tính ổn định**, không dùng p99 thay mean hoặc áp cho hệ đang mất cân bằng.

**Bài 20.** Vì sao gửi `BATCH` hàng nghìn partitions rồi nâng `batch_size_fail_threshold` không phải tối ưu throughput Cassandra?

**Đáp án:** Cross-partition batch tạo fan-out/batchlog/memory/network overhead; nâng guardrail cho phép rủi ro lớn hơn, không sửa workload. Dùng prepared unbatched writes, bounded concurrency và idempotency phù hợp.

**Bài 21.** Một operator sửa `cassandra.yaml`, nhưng không thấy effective value thay đổi. Vì sao?

**Đáp án:** Có thể property chỉ đọc lúc process start hoặc operator/CRD/JMX đang override; phải kiểm dynamic vs restart-only theo version, source-of-truth và rollout/rolling restart đúng RF/CL.

**Bài 22.** Một node dùng threshold mới, các nodes khác dùng threshold cũ. Hệ có thể có hành vi request khác nhau không?

**Đáp án:** **Có.** Coordinator/replica path thay đổi theo routing; config drift có thể tạo lỗi phụ thuộc node. Canary phải xác định scope và đưa cluster về trạng thái cấu hình nhất quán theo plan.

**Bài 23.** `LOCAL_QUORUM` query canary thành công trên partition test. Có đủ xác nhận không còn corrupt SSTables trong table không?

**Đáp án:** **Không.** Query probe chỉ kiểm một scope, có thể đi qua các replicas khác hoặc không chạm tới SSTable lỗi; cần verify/repair/backup/ledger coverage theo affected ranges.

**Bài 24.** `WriteTimeout` trong khi restart coordinator chứng minh mutation chưa được ghi?

**Đáp án:** **Không.** Outcome có thể unknown. Giữ stable full primary key/event ID và reconcile, không sinh UUID mới để retry cùng logical event.

**Bài 25.** Lệnh `nodetool stop COMPACTION` có hoàn tác mọi byte đã rewrite không?

**Đáp án:** **Không.** Nó yêu cầu dừng task theo version; không phải transaction rollback. Phải xem trạng thái temp/input/output files, cleanup và snapshot/restore path nếu dữ liệu cần phục hồi.

**Bài 26.** Một change làm p99 giảm nhưng throughput offered cũng giảm một nửa. Có kết luận hiệu năng tốt hơn không?

**Đáp án:** **Chưa.** So benchmark với cùng offered/achieved rate, query mix, CL, retries và row shape; không để closed-loop/coordinated omission che overload.

**Bài 27.** Vì sao một tool báo repair hoàn tất ở `tableA` không chứng minh `tableB`/remote DC đã hội tụ?

**Đáp án:** Repair có **scope token/table/participants/DC**. Phải ghi ranges và nodes đã xử lý, những nơi ngoài scope cần lịch riêng; không suy full-cluster từ một completion message.

**Bài 28.** `LOCAL_ONE` cho p99 tốt hơn `LOCAL_QUORUM`, có thể đổi CL trong lúc incident mà không cần review không?

**Đáp án:** **Không.** CL thay contract freshness/availability/durability của workload; có thể trả state stale. Phải đánh giá correctness/replica convergence, approval và rollback riêng.

**Bài 29.** Một script `for each node: compact` chạy đồng thời và disk free giảm nhanh. Vấn đề của kế hoạch?

**Đáp án:** Không giới hạn concurrency, thiếu peak disk/output/snapshot estimate và competing repair/streaming; phải stop expansion, đánh giá recovery/IO headroom và canary một node/table.

**Bài 30.** Khi chuẩn bị scrub một bảng có corruption, checklist tối thiểu để quyết định GO?

**Đáp án:** Scope node/SSTable/token được xác nhận; root cause storage vs format; healthy replicas/backup off-cluster và restore đã kiểm; disk headroom; `gc_grace_seconds`/repair status; expected ID/value/deletes; version-specific options; operator, stop criteria và data-loss approval nếu skip corrupted.

**Bài 31.** Tại sao rollback `tombstone_failure_threshold` sau một giờ không undo mọi hậu quả của việc nâng ngưỡng?

**Đáp án:** Revert chỉ đổi behavior request từ thời điểm đó; CPU/GC/disk pressure, timeouts và mutations/cancellation trước đó vẫn đã diễn ra. Cần kiểm data/cluster SLO và retry backlog sau rollback.

**Bài 32.** Một worker báo “thành công vì `nodetool status UN` và HTTP 200”. Thiếu những bằng chứng nào?

**Đáp án:** Thiếu RF/CL availability, hints/repair/compaction coverage, expected IDs/values/TTL/deletes, offered/achieved throughput, p95/p99, disk/GC, backup/restore và rollback state. `UN` và 200 chỉ là một phần điều kiện.

## 36. Checklist trước, trong và sau khi thay đổi

### 36.1. Preflight chung

~~~text
CONTEXT / TOPOLOGY
[ ] Cluster ID, environment, DC/rack/host ID/node ownership chính xác.
[ ] Cassandra/JDK/Driver/operator versions và config source-of-truth đã pin.
[ ] Full RF + regular/serial CL của các workloads được xác minh.
[ ] Natural replica sets cho affected token ranges đã biết.
[ ] Không có replica khác down/slow khiến quorum không đủ khi rút một node.
[ ] Repair/hints/streaming/compaction đang chạy được kiểm tra đầy đủ.

DATA SAFETY
[ ] CQL schema/partition key/query shape và impacted tables xác định rõ.
[ ] Có expected IDs/values, TTL/deleted state và ledger ACK/unknown.
[ ] Last successful repair coverage/token/DC/gc grace được xem xét.
[ ] Snapshot/backup checksum, off-node copy và khả năng restore đã kiểm.
[ ] Không có data source duy nhất sẽ bị xóa/ghi đè trong thao tác.
[ ] Nếu có thể mất corrupted data, có phê duyệt rủi ro/nguồn phục hồi.

CAPACITY / SLO
[ ] Peak disk/output + snapshot hardlinks/hints/commitlog được dự toán.
[ ] CPU, disk await/free, GC, compaction queues và network có headroom.
[ ] Client p50/p95/p99, offered/achieved RPS, retries/errors có baseline.
[ ] Stop criteria và error budget được quyết định trước khi chạy.
[ ] Một node/table/config-scope canary, không chồng lấp nhiều maintenance.

OPERATIONS
[ ] Exact command/options được xác minh trên help/tài liệu đúng version.
[ ] Có change ID, UTC timeline, owner, observer và escalation.
[ ] Có cách dừng mở rộng change và thủ tục khôi phục availability.
[ ] Rollback config/binary và restore data được phân biệt.
[ ] Các logs/metrics/backup keys cần thiết truy cập được nhưng có quyền phù hợp.
~~~

### 36.2. Riêng khi **restart**

~~~text
[ ] Không rút node khiến RF/CL không đủ full replicas.
[ ] Các replicas còn lại không có disk/GC/compaction saturation.
[ ] Binary/JDK/config cũ-mới tương thích; có verified rollback image.
[ ] Quá trình drain/stop/start theo đúng operator/systemd/container runbook.
[ ] Persistent volumes, token/host ID, rack/DC metadata không bị thay.
[ ] Startup deadline phù hợp commit-log replay/cold cache/hint delivery.
[ ] Chờ UN + native transport/schema ổn định + data/SLI validation.
[ ] Không restart node kế khi catch-up/hints/p99 còn chưa ổn.
~~~

### 36.3. Riêng khi **scrub**

~~~text
[ ] Có corruption evidence chính xác của node/SSTable/table/range.
[ ] Đã loại trừ bug CQL/codec/driver không liên quan SSTable bytes.
[ ] Disk hardware health và available replica/backup data sources đã kiểm.
[ ] Có snapshot/off-cluster backup đã kiểm restore, không chỉ hardlinks.
[ ] Scrub online vs sstablescrub offline được chọn đúng.
[ ] Options skip corrupted/no-snapshot/... được hiểu theo version.
[ ] Không bỏ corrupted partitions trừ khi data-loss plan được duyệt.
[ ] Post-scrub ledger IDs/values/deletes và repair/restore coverage được xác minh.
~~~

### 36.4. Riêng khi **major compaction**

~~~text
[ ] Nguyên nhân có bằng chứng liên quan SSTables/read amplification/layout.
[ ] STCS/LCS/TWCS/UCS và TTL/late-writes/delete behavior được review.
[ ] Peak physical disk headroom được tính, có snapshot retention impact.
[ ] Không chạy cùng streaming/repair/upgrade nặng hoặc nhiều nodes song song.
[ ] Chỉ chọn một table/node canary, có disk/GC/p99 stop criteria.
[ ] Không giả định purge toàn bộ tombstones khi qua gc_grace.
[ ] Post-compaction đo SSTablesPerRead, scanned tombstones, p99, disk, IDs.
[ ] Có plan nếu task dừng/fail; stop COMPACTION không được coi là rollback.
~~~

### 36.5. Riêng khi **thay giới hạn**

~~~text
[ ] Setting name/unit/default/version và dynamic/restart-only được xác minh.
[ ] Biết nguồn config: JMX runtime/file/operator/app; tránh drift.
[ ] Phân biệt server guardrail, timeout, batch cap, throughput và driver limits.
[ ] Nếu nới threshold, đã xử lý/đo nguyên nhân query/data model trước.
[ ] Nếu tăng timeout, đo in-flight/retry/resource ở mọi tầng API/Driver/DB.
[ ] Nếu sửa batch/mutation cap, có workload proof và memory/commitlog safety.
[ ] Nếu sửa client retry/pool, có global budget và token/hot-key pressure metrics.
[ ] Config canary không khiến coordinator routing tạo behavior khó dự đoán.
[ ] Effective settings trên từng node/pod được xác nhận sau rollout/rollback.
~~~

### 36.6. Post-change verification

~~~text
[ ] Target node/table/setting hoàn thành đúng scope; không có unexpected errors.
[ ] RF/CL và DC-aware routing như trước hoặc thay đổi được phê duyệt riêng.
[ ] Expected event IDs/values, deleted states, TTL expiry đúng trong phạm vi test.
[ ] Hints/repair/compaction/streaming không còn backlog ngoài ngưỡng.
[ ] p95/p99, offered/achieved RPS, timeout/retry/GC/disk đạt SLO.
[ ] Snapshot/backup/restore recovery path còn đúng và có retention plan.
[ ] Config values/diffs không bị operator reconcile ngược ngoài ý muốn.
[ ] Change ID, timestamps, results, known gaps và follow-up owners được lưu.
[ ] Quyền sở hữu maintenance trả lại cho vận hành bình thường.
~~~

## 37. Tài liệu tham khảo và kết luận

Cần tra cứu đúng **Cassandra version, distribution, JDK/driver và operator** đang dùng. Các nguồn chính thức sau là điểm bắt đầu để đối chiếu options/hành vi cụ thể (không dùng URL của bản `stable` để suy defaults của một bản cũ):

1. [Apache Cassandra — Documentation](https://cassandra.apache.org/doc/stable/): kiến trúc, replication/consistency, cấu hình, vận hành và compatibility theo bản.
2. [Apache Cassandra — nodetool commands](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): `status`, `drain`, `scrub`, `compact`, `repair`, `tablestats`, `tpstats` và cách đọc help tương ứng.
3. [Apache Cassandra — Compaction](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/index.html): STCS, LCS, TWCS/UCS (khi hỗ trợ), tombstone eligibility và compaction costs.
4. [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy, Merkle trees, incremental/full repair và token/DC scope.
5. [Apache Cassandra — Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hinted handoff, hint windows, delivery và giới hạn best-effort.
6. [Apache Cassandra — CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT`, `UPDATE`, `DELETE`, `LIMIT`, TTL và batch semantics.
7. [Apache Cassandra Java Driver 4.18 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/): prepared/bound CQL, reuse và parameters.
8. [Apache Cassandra Java Driver 4.18 — Paging](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/): page size, paging state và tác động fetch trên application.
9. [Spring Data Cassandra — Template](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): persistence/query mapping, generated CQL, entity lifecycle; dùng với BOM cụ thể của dự án.

**Kết luận:** Trước khi **restart**, hãy tính **RF/CL và lượng replica còn phục vụ được**, kiểm JVM/GC/commitlog/hints và có rolling restart stop criteria. Trước khi **scrub**, xác nhận SSTable corruption thật, **backup và nguồn replica khỏe**, giới hạn table/node phạm vi và chấp nhận rằng một số chế độ có thể bỏ dữ liệu hỏng; exit code 0 không phải chứng cứ dữ liệu đã đầy đủ. Trước **major compaction**, tính peak disk với **SSTables cũ/mới và snapshot hardlinks**, xem STCS/LCS/TWCS/UCS, `gc_grace_seconds` và tác động lên foreground p99. Trước khi **nới giới hạn**, phân biệt guardrail, timeout, batch/mutation cap và driver throttling; đổi threshold không giải quyết data model sai hoặc tombstone-heavy query. Một thay đổi chỉ **GO** khi có **tác động dự kiến, nguồn dữ liệu an toàn, canary đúng workload, SLO/correctness gates và kế hoạch khôi phục thực tế**. Đừng nhầm **node `UN`**, một lần read thành công, hoặc config rollback với bằng chứng toàn bộ dữ liệu Cassandra đã hội tụ và sự cố đã được sửa tận gốc.





