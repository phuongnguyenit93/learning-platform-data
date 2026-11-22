# Bảo trì định kỳ và kiểm tra điều kiện trước thao tác

Một cụm NoSQL có ba bản sao của dữ liệu. Vào lúc 02:00, kỹ sư trực ca dự định khởi động lại một node để cập nhật hệ điều hành. Dashboard đang hiển thị “cluster healthy”, nhưng một replica khác đã mất kết nối gần đây, backup cuối chưa từng được thử khôi phục, và dung lượng đĩa của node còn lại gần đầy. Nếu tiếp tục thao tác theo lịch, hệ có thể mất quorum, tăng độ trễ hoặc ngừng ghi dù trước khi bảo trì mọi API vẫn trả kết quả.

Trường hợp này cho thấy một nguyên tắc quan trọng: **bảo trì cụm không chỉ là thực thi một lệnh đúng, mà là chứng minh hệ còn đủ điều kiện an toàn trước khi thay đổi trạng thái.** Một thao tác đơn lẻ có thể hợp lệ trong cụm khỏe nhưng nguy hiểm trong cụm đã suy giảm.

Bài học thuộc chương **Vận hành cụm**, module **Database No SQL**. Mục tiêu là xây dựng quy trình bảo trì định kỳ có thể lặp lại và **preflight GO/NO-GO**, kết hợp topology, quorum, sức khỏe replica, backup/restore, năng lực tài nguyên, SLO, tác vụ nền, bảo mật và khả năng phục hồi. Bài sử dụng ví dụ ở MongoDB, Cassandra, Redis Cluster, CouchDB, hệ lưu trữ LSM và dịch vụ NoSQL managed. Các ngưỡng và thời gian trong ví dụ là **giả định minh họa**, không phải cấu hình chuẩn áp dụng cho mọi engine hoặc hệ thống.

> **Nguyên tắc:** Chỉ bảo trì khi hiểu rõ **trạng thái hiện tại**, **trạng thái sẽ xảy ra trong thao tác**, **rủi ro nếu thêm một lỗi bất ngờ**, **cách quan sát**, **điều kiện dừng**, và **cách phục hồi**.

## 1. Bảo trì cụm NoSQL bao gồm những gì?

| Nhóm | Công việc thường gặp | Tác động tiềm tàng |
|---|---|---|
| Phần mềm | Rolling restart, upgrade driver/database/OS | Failover, protocol compatibility |
| Hạ tầng | Thay node/volume, tăng RAM/CPU, thay network | Mất replica tạm thời, cache cold |
| Dữ liệu | Repair, compaction, reindex, TTL cleanup | CPU/disk/network load |
| Topology | Add/remove node, rebalance shards/slots | Data movement, hotspots |
| Sao lưu | Backup, snapshot, restore drill | Disk I/O, storage cost, RPO/RTO |
| Bảo mật | Rotate credentials/certificates, IAM/ACL review | Kết nối bị từ chối, quyền thay đổi |
| Vận hành | Kiểm retention, CDC lag, log cleanup, capacity | Gaps, thiếu disk hoặc observability |
| Ứng dụng | Thay query/index/data model, backfill | Read/write contention, consistency |

Không phải mọi việc đều có thể làm rolling hoặc online. Một số thay đổi schema/topology/phiên bản đòi thứ tự hoặc quy trình chuyên biệt theo engine. **Không áp dụng runbook của MongoDB cho Cassandra hay Redis chỉ vì cả ba đều là NoSQL.**

## 2. Phân biệt kiểm tra định kỳ với thao tác thay đổi

**Kiểm tra định kỳ** (inspection):
- Xem sức khỏe replica, shard, partition.
- Theo dõi dung lượng, backup, restore drill.
- Đánh giá version và bảo mật.
- Xác nhận số liệu SLO, lỗi, lag.
- Review retention, query plans và tài nguyên.

**Thao tác thay đổi** (maintenance action):
- Restart node.
- Thay cấu hình hoặc credentials.
- Upgrade database binary.
- Repair hoặc rebalance.
- Rebuild index.
- Di chuyển shard/slot.
- Khôi phục dữ liệu.

Các thao tác có thể gây gián đoạn phải có **preflight trước khi thực hiện**, không phải chỉ chạy healthcheck sau khi đã xong.

## 3. Mục tiêu bảo trì: an toàn, không phải chỉ “xong việc”

Một tác vụ thành công về kỹ thuật vẫn có thể thất bại về vận hành.

Ví dụ:
- Node khởi động lại được nhưng một replica khác mất quorum.
- Version upgrade hoàn tất nhưng driver cũ không tương thích.
- Compaction hoàn tất nhưng disk gần hết và API p99 vượt SLO nhiều giờ.
- Backup tạo file thành công nhưng file không thể restore.
- Certificate mới được phát hành nhưng một service thiếu trust chain.
- Dữ liệu được di chuyển nhưng một shard thiếu bản sao dự phòng.

Thành công thực sự cần đánh giá:
1. Dữ liệu không mất và invariants vẫn đúng.
2. Tính sẵn sàng/consistency không vi phạm policy.
3. Khả năng khôi phục vẫn còn.
4. SLO trong và sau cửa sổ bảo trì được kiểm soát.
5. Các rủi ro mới không bị để lại dưới dạng backlog hoặc replica lag.
6. Có bằng chứng và handoff cho ca tiếp theo.

## 4. Mô hình quyết định GO/NO-GO

~~~mermaid
flowchart TD
    A["Nhận change request và mục tiêu"] --> B["Xác định topology và failure domain"]
    B --> C{"Quorum/replicas còn an toàn nếu đưa 1 node ra?"}
    C -->|"Không"| N["NO-GO: khôi phục redundancy trước"]
    C -->|"Có"| D{"Backup và recovery đã xác minh?"}
    D -->|"Không"| N
    D -->|"Có"| E{"Capacity/SLO/headroom đạt?"}
    E -->|"Không"| N
    E -->|"Có"| F{"Dependencies, versions, observability sẵn sàng?"}
    F -->|"Không"| N
    F -->|"Có"| G["GO: canary/rolling có giám sát"]
    G --> H{"Post-step gates đạt?"}
    H -->|"Không"| STOP["STOP / phục hồi / báo incident"]
    H -->|"Có"| I["Tiếp bước, postflight và bàn giao"]
~~~

GO không có nghĩa bỏ qua rủi ro; nó chỉ là quyết định rằng **các điều kiện đã định nghĩa đang được chứng minh**. Nếu một điều kiện thiết yếu không thể đo, hành vi mặc định an toàn là **NO-GO hoặc yêu cầu thẩm quyền ngoại lệ rõ ràng**, không coi “không thấy lỗi” là bằng chứng đủ.

## 5. Preflight có năm lớp điều kiện

1. **Topology và dữ liệu:** replicas, shard coverage, consistency, quorum, replica lag.
2. **Khả năng khôi phục:** backup/PITR, restore test, snapshot, rollback/rollforward.
3. **Năng lực:** CPU, RAM, disk, IOPS, network, replica headroom khi mất node.
4. **Dịch vụ và phụ thuộc:** latency/error SLO, driver compatibility, CDC, caches, downstream consumers.
5. **Quản trị thay đổi:** owner, approval, lịch, người trực, stop conditions, monitoring, security/communication.

Một checklist chỉ hỏi “node ping được không?” bỏ qua gần như toàn bộ rủi ro quan trọng.

## 6. Thu thập inventory trước khi chạm vào cụm

Một manifest có thể gồm:

~~~yaml
cluster:
  name: commerce-nosql-prod
  engine: example-engine
  engineVersion: "documented-version"
  environment: production
  region: example-region
  failureDomains:
    - zone-a
    - zone-b
    - zone-c
  topology:
    nodes: 6
    shards: 2
    replicationFactor: 3
  owner: database-platform
change:
  id: CHG-2026-503
  objective: rolling-node-maintenance
  targetNode: node-example-2
  startWindow: "2026-11-15T01:00:00Z"
  stopWindow: "2026-11-15T02:00:00Z"
~~~

Các giá trị chỉ minh họa; topology thực phải được xác nhận qua **nguồn có thẩm quyền** như control plane, cluster metadata và health endpoints. Không dựa duy nhất vào một file inventory đã cũ.

Cần biết mỗi node:
- Vai trò leader/follower/primary/replica.
- Zone/rack/failure domain.
- Shards/partitions/slots lưu giữ.
- Software version.
- Data volume và ổ đĩa.
- Trạng thái replica/catch-up.
- Jobs nền đang chạy.
- Tình trạng bảo trì trước đó.

## 7. Failure domain quan trọng hơn số lượng node

Một cụm có 6 nodes nhưng toàn bộ ba replicas của một shard ở cùng rack vẫn dễ mất dữ liệu/khả dụng nếu rack lỗi.

Kiểm:
- Replica placement theo zone/rack.
- Network isolation giữa zones.
- Storage/shared-volume failure domain.
- Các service phụ trợ có cùng điểm lỗi không.
- Một thao tác thay load balancer/firewall có thể ảnh hưởng nhiều nodes cùng lúc không.

**Không đánh đồng “nhiều nodes” với “nhiều fault domains độc lập”.**

## 8. Quorum trước thao tác

Với một nhóm sao chép có \(N\) thành viên bỏ phiếu độc lập, ngưỡng majority thông thường là:

\[
Q=\left\lfloor\frac{N}{2}\right\rfloor+1
\]

Ví dụ:
- \(N=3 \Rightarrow Q=2\).
- \(N=5 \Rightarrow Q=3\).

Nếu nhóm ba thành viên đang có một thành viên không liên lạc được, đưa thêm một thành viên khỏe ra khỏi phục vụ có thể còn **một phiếu khả dụng**, không đủ majority.

Tuy nhiên **không áp dụng công thức majority này cho mọi NoSQL**. Cassandra dùng replication factor và consistency level theo keyspace/datacenter; Redis Cluster có điều kiện availability theo masters/slots/failover; một dịch vụ managed có cơ chế riêng. Preflight phải dựa trên **quy tắc quorum thực của engine và operation**.

## 9. Safety margin sau khi rút node

Ví dụ nhóm 3 replica đang khỏe:

~~~text
Before:
  A=healthy, B=healthy, C=healthy.
  Majority=2.

Maintenance:
  A=offline.
  B=healthy, C=healthy.
  Majority vẫn đạt, nhưng không còn dư cho một lỗi khác.
~~~

Nếu B bất ngờ lỗi, group chỉ còn C và mất majority.

Vậy câu hỏi không chỉ là “có đạt quorum trong thao tác không?” mà còn là:

> **Trong khi một node được chủ động đưa ra khỏi cụm, mức chịu thêm lỗi bất ngờ có còn đáp ứng risk policy không?**

Một số tổ chức cho phép degraded margin trong một cửa sổ ngắn, số khác yêu cầu standby capacity hoặc không cho phép khi replica đã degraded. Quyết định phải được công bố và phê duyệt, không suy từ dashboard màu xanh.

## 10. Cassandra: consistency level liên quan quorum

Với một keyspace replication factor \(RF=3\) trong phạm vi datacenter được xét, `LOCAL_QUORUM` cần quorum tương ứng ở local DC theo cấu hình.

Mô hình đơn giản:
- Ba replicas khả dụng: còn dự phòng.
- Một replica đang down: còn hai, vẫn có thể thỏa local quorum.
- Bảo trì thêm một replica: còn một, không còn đủ cho local quorum.

Trong triển khai đa datacenter, phải kiểm **replication strategy và local datacenter**, không lấy tổng nodes toàn cluster. Điều kiện an toàn còn phụ thuộc topology, coordinator, transient replicas, repair state và mục tiêu consistency thực tế.

**Không chuyển tạm mọi query xuống consistency yếu hơn chỉ để maintenance qua được** nếu ứng dụng cần bất biến đã cam kết.

## 11. Không tin một nhãn “cluster healthy” duy nhất

Health có thể tổng hợp nhưng che:
- Một shard cụ thể thiếu replica.
- Một node liên lạc được nhưng replica lag lớn.
- Một primary có CPU rất cao.
- Một disk đang near-full.
- Một partition đang hot.
- Rebalance/repair còn đang chạy.
- Một certificate sắp hết hạn.
- Backup lâu ngày chưa thử restore.

Preflight phải xem cả **tổng thể lẫn từng shard/replica/failure domain**, cộng các service dependencies và khách hàng.

## 12. Replication lag và catch-up

Một follower có thể báo `UP` nhưng chưa có đủ các writes gần đây.

~~~text
Primary latest source position: P1000.
Follower-1: P999.
Follower-2: P850.
~~~

Nếu cần thay primary, follower ở P850 có thể chưa phù hợp để tiếp quản theo safety/durability requirements.

Cần đo:
- Source write position vs applied/durable position.
- Time lag và byte/entry lag.
- Catch-up throughput.
- Oplog/change-log retention headroom.
- Apply errors, network issues.
- Replica có thực sự voting/eligible hay không.

Không dùng một con số “lag=0 seconds” từ metric bị trễ làm bảo đảm tuyệt đối; kiểm timestamp thu thập và trạng thái nguồn.

## 13. Quorum không tự đảm bảo không mất acknowledged writes

Một write được ACK theo chế độ durability/consistency yếu có thể chưa đến đủ replicas hoặc chưa bền theo yêu cầu.

Khi bảo trì/failover:
- Cần hiểu write concern, consistency level, sync/async replication.
- Kiểm ứng dụng đang dùng ACK mode nào.
- Không tự giả định leader election khiến mọi writes được bảo toàn.
- Xem khả năng rollback/replay và idempotency của client.
- Dùng điều kiện commit/durable xác minh theo engine.

Ví dụ trong MongoDB, write concern và read concern cần phù hợp mục tiêu durability/consistency, không chỉ dựa trên việc có ba nodes.

## 14. Checkpoint và thời điểm phục hồi

Trước bảo trì nên biết:
- Database có đang checkpoint/flush không?
- WAL/oplog/commit log còn đủ cho recovery không?
- Node mới có thể replay trong thời gian chấp nhận?
- Restore cần bao lâu với dataset hiện tại?
- Có encryption keys và credentials để mở bản sao không?

**Snapshot vừa tạo không tự đủ** nếu snapshots thiếu nhất quán, backup chain hỏng hoặc key cần giải mã đã mất.

## 15. Backup tồn tại khác backup khôi phục được

Một bảng điều kiện:

| Kiểm tra | Ý nghĩa |
|---|---|
| Backup job gần đây thành công | Có artifact theo lịch |
| Backup catalog liệt kê đủ shards/collections | Phạm vi dữ liệu không thiếu |
| Integrity/checksum verification | Artifact không bị hỏng theo phép kiểm |
| Encryption keys accessible theo quyền | Có thể mở artifact |
| Restore drill thành công | Khôi phục trong môi trường cô lập |
| Application validation sau restore | Business state thực sự dùng được |
| RPO/RTO thực nghiệm | Khả năng phục hồi đáp ứng yêu cầu |
| PITR/log-chain continuity nếu áp dụng | Có thể khôi phục tới mốc mục tiêu |

**Chỉ xem trạng thái `backup success` chưa chứng minh RTO hay dữ liệu sẽ phục hồi đúng.**

## 16. RPO và RTO trong preflight

- **RPO (Recovery Point Objective):** lượng dữ liệu theo thời gian có thể chấp nhận mất khi phục hồi.
- **RTO (Recovery Time Objective):** thời gian phục hồi dịch vụ đến mức được định nghĩa.

Giả sử:
~~~text
RPO yêu cầu <= 5 phút.
RTO yêu cầu <= 30 phút.
Backup gần nhất: 3 giờ trước.
Không có PITR/log replay.
~~~

Điều này có thể là **NO-GO** cho một thao tác nhiều rủi ro nếu rollback duy nhất là restore backup đó.

Không tự coi RPO bằng khoảng cách thời gian giữa backup jobs nếu có cơ chế log/PITR; phải xem **khả năng khôi phục đã kiểm chứng** theo thiết kế thật.

## 17. Recovery point không phải rollback button

Rollback application code khác restore dữ liệu:
- Binary rollback có thể không đọc được schema/metadata mới.
- Replica set/shard config thay đổi có thể không đảo ngược đơn giản.
- Restore snapshot có thể làm mất writes hợp lệ sau snapshot.
- Key rotation có thể gây tương thích hai chiều.
- Data migration có thể không có phép biến đổi ngược.

Kế hoạch nên ghi:
- **Rollback được hay chỉ roll forward?**
- Điều kiện rollback.
- Điểm không thể quay lại (point of no return).
- Cách bảo toàn writes mới.
- Ai được phép quyết định.
- Thời gian và side effects downstream.

Đừng hứa “sẽ restore backup nếu lỗi” mà không tính dữ liệu phát sinh và business consistency.

## 18. Capacity headroom khi một node dừng

Giả sử ba nodes đang xử lý tải tương đối đồng đều:

~~~text
Mỗi node sử dụng khoảng 55% năng lực tính theo một bottleneck resource.
Một node ra khỏi cụm.
Hai nodes còn lại phải hấp thụ tải đã phân phối lại.
~~~

Trong một mô hình đơn giản:
\[
\mathrm{LoadPerRemainingNode}
\approx\frac{3\times55\%}{2}=82{,}5\%
\]

Đây chỉ là xấp xỉ khi load cân bằng và capacity tuyến tính. Trên thực tế, cache cold, hotspot, compaction, replication và giới hạn mạng có thể làm kết quả tệ hơn nhiều.

Nếu remaining nodes đang ở 85% trước bảo trì, không thể coi việc mất một node là an toàn chỉ dựa vào quorum.

## 19. Disk headroom và compaction

Preflight cần kiểm:
- Free disk, inode/filesystem nếu liên quan.
- Disk read/write latency và saturation.
- WAL/commit log usage.
- Temporary disk cần cho compaction/reindex/repair.
- Snapshot hoặc local backup footprint.
- Data growth trong cửa sổ.
- Recovery/rebalance data copy size.

Một LSM engine có thể cần **temporary disk headroom** khi rewrite SSTables; một node chưa đầy 100% vẫn có thể không đủ không gian cho operation.

Không đặt một tỷ lệ free disk duy nhất cho mọi engine. Tính theo **operation peak usage** và cảnh báo thực nghiệm.

## 20. RAM, cache và cold-node effect

Một node sau restart thường mất:
- JVM JIT cache/warm code paths.
- Driver/internal connection pools.
- Database buffer/block cache.
- Một phần filesystem cache.
- Các indexes/metadata đã nạp.

Ngay cả khi replica bắt kịp data, p99 có thể cao vì page cache lạnh. Preflight phải tính **capacity trong warm-up sau restart**, không chỉ trong trạng thái các nodes đã chạy lâu.

Nếu còn hai nodes vừa quá tải, thêm node cold chưa chắc khiến hệ ngay lập tức về SLO.

## 21. Network và fault domains

Một thao tác:
- Rebalance partitions.
- Replica resync.
- Backup lên object storage.
- Repair nhiều nodes.
- Xây index mới.

có thể tiêu thụ bandwidth rất lớn.

Kiểm:
- Băng thông khả dụng và network error rates.
- Cross-AZ/region traffic cost và limits.
- TLS/cert trust khi đổi kết nối.
- Latency giữa replicas.
- Các job truyền dữ liệu khác đang chạy.

Đừng lên lịch backup full, repair và rebalance lớn đồng thời khi cùng chia một bottleneck network/disk mà không có tính toán.

## 22. Tác vụ nền thường xung đột với bảo trì

| Background task | Nguy cơ chồng lấn |
|---|---|
| Compaction | Disk saturation, write stalls |
| Flush/checkpoint | I/O spikes |
| Repair/anti-entropy | Network/disk load, lock/queue |
| Snapshot/backup | Disk reads và network |
| Reindex | Read scans/CPU/temp disk |
| TTL cleanup | Disk writes, tombstones |
| Shard migration | Replication/copy load |
| CDC catch-up | Log retention/consumer lag |
| Encryption rekey | CPU, key access |
| Large batch import | Hot partitions và backpressure |

Không phải mọi job đều cần dừng; một số là điều kiện duy trì an toàn dữ liệu. **Dừng repair/compaction tùy tiện có thể còn nguy hiểm hơn để chúng chạy.** Preflight quyết định tránh overlap hoặc thay đổi rate/schedule theo runbook riêng đã kiểm chứng.

## 23. Đặt SLO baseline trước khi thay đổi

Ví dụ:
~~~yaml
slo:
  apiP99Millis: 200
  maxErrorRatePercent: 0.1
  maxReplicationLagSeconds: 15
  maxCdcLagSeconds: 60
  minHealthyReplicasPerShard: "per-engine policy"
baseline:
  sampledWindowMinutes: 30
  workload: "production traffic"
~~~

Ngưỡng hoàn toàn minh họa. Những metric cần lưu:
- Client latency p50/p95/p99 theo operation.
- Success/error/timeout rate.
- Offered/completed QPS.
- Per-node CPU, RAM, disk I/O, network.
- Replica/leader health và lag.
- Write stalls/backlog.
- Cache hit/miss, connection pool pending.
- CDC/exporter lag, retry queues.

**Nếu SLO đã vi phạm trước bảo trì, phải giải thích vì sao vẫn GO**, thay vì quy sự cố sau đó cho operation mà không có baseline.

## 24. Change freeze và maintenance window

Một change request nên có:
- Mục đích, rủi ro, tính cấp thiết.
- Cụm/shards/nodes ảnh hưởng.
- Owner/operator và người phê duyệt.
- Người quan sát và contact khi có incident.
- Cửa sổ bắt đầu/kết thúc và múi giờ.
- Chính sách change freeze (đợt bán hàng, payday, campaign).
- Kế hoạch truyền thông nếu có dự kiến ảnh hưởng.
- Thứ tự từng bước, thời gian tối đa.
- Stop conditions và rollback/rollforward.
- Ticket links, snapshot/backup references.
- Kế hoạch postflight và handoff.

Cửa sổ đêm không tự đồng nghĩa hệ rảnh: backup, ETL, compaction hoặc traffic từ region khác có thể đang cao.

## 25. Điểm dừng và quyền ra quyết định

Phải định nghĩa trước:
- Ai có quyền bấm STOP?
- Metric nào vượt ngưỡng là dừng?
- Nếu không nhận được metrics đáng tin thì có được tiếp tục không?
- Khi một bước quá thời gian dự kiến, có thể chạy bước tiếp không?
- Nếu node chưa bắt kịp replication, có được đưa node khác ra không?
- Khi đã qua point of no return, xử lý thế nào?

**Người trực ca không nên phải tự suy điều kiện dừng giữa lúc p99 và replication lag đang tăng.**

## 26. Mẫu preflight checklist

~~~text
[ ] Đã xác minh cluster, môi trường, node/partition đích.
[ ] Change ticket/approval/owner/maintenance window rõ.
[ ] Topology và fault domains hiện tại được xác nhận.
[ ] Số replica/voting members đủ theo từng shard/partition.
[ ] Không có node degraded hoặc lag vượt ngưỡng.
[ ] Quorum/consistency còn đạt nếu target rời cụm.
[ ] Headroom thêm một lỗi phù hợp risk policy.
[ ] Backup gần đây và restore drill phù hợp RPO/RTO.
[ ] Disk/CPU/RAM/IOPS/network đủ khi rút node.
[ ] Không có tác vụ nền xung đột chưa đánh giá.
[ ] Driver/protocol/version compatibility đã xác minh.
[ ] CDC/log retention/replication catch-up còn headroom.
[ ] Credentials/certificates/roles sẵn sàng.
[ ] Baseline SLO và dashboard hoạt động.
[ ] Stop/rollback/rollforward plan có owner.
[ ] Handoff và thông tin incident communication rõ.
~~~

Checkbox chỉ có giá trị khi có **bằng chứng kiểm tra**, chẳng hạn query/metric timestamp và link nội bộ. “Đã tick” không thay số liệu.

## 27. Preflight là kiểm tra gần thời điểm thực hiện

Nếu kiểm tra lúc 09:00 rồi bảo trì lúc 23:00, trạng thái có thể đã thay đổi:
- Replica mới lag.
- Backup thất bại.
- Free disk giảm.
- Một node tự failover.
- Config đổi.
- Một migration lớn bắt đầu.

Nên có ít nhất:
1. **Planning preflight** trước cửa sổ để nhận diện công việc khắc phục.
2. **Immediate preflight** ngay trước thao tác.
3. **Per-step preflight** giữa các nodes trong rolling process.

Không dùng kết quả từ nhiều giờ trước làm proof cụm vẫn khỏe.

## 28. Preflight phải fail-closed cho điều kiện trọng yếu

Pseudocode:

~~~text
function assessMaintenance(cluster, target):
    topology = fetchFreshTopology()
    health = fetchFreshReplicaHealth()
    backup = fetchVerifiedRecoveryEvidence()
    capacity = fetchResourceHeadroom()
    baseline = fetchCurrentSLO()
    dependencies = fetchVersionAndJobStatus()

    if anyRequiredEvidenceMissingOrStale():
        return NO_GO("insufficient evidence")

    if not canRemoveTargetWithoutBreakingRequiredQuorum():
        return NO_GO("quorum risk")

    if not meetsRecoveryObjectives(backup):
        return NO_GO("recovery not proven")

    if not capacityEnoughDuringTargetAbsence(capacity):
        return NO_GO("capacity risk")

    if not baselineWithinAllowedConditions(baseline):
        return NO_GO("SLO already degraded")

    if dependenciesConflictOrJobsUnbounded():
        return NO_GO("unsafe overlap")

    return GO_WITH_GATES
~~~

**Đây là thuật toán minh họa, không phải script production.** Engine-specific rules, telemetry correctness, override authorization và concurrent state changes cần được thiết kế và kiểm chứng riêng. Sau GO, vẫn phải quan sát liên tục vì trạng thái có thể đổi ngay lập tức.

## 29. Không tạo “one-click upgrade” không có guardrails

Automation an toàn nên:
- Mặc định dry-run.
- Yêu cầu xác định environment/cluster/target cụ thể.
- Có approval với thay đổi production.
- Kiểm freshness của health evidence.
- Không chạy song song trên nhiều replicas cùng fault domain.
- Persist checkpoint của từng bước.
- Stop tự động khi SLO/quorum hoặc telemetry xấu đi.
- Có lock để tránh hai jobs bảo trì xung đột.
- Ghi audit operation/owner/result.
- Không chấp nhận broad wildcard targets một cách im lặng.

Không nhầm `--force` hay `ignore_errors` với giải pháp khi preflight không đạt; nó chỉ chuyển rủi ro thành sự cố khó xử lý hơn.

## 30. Rolling maintenance là một state machine

~~~mermaid
flowchart TD
    P["PRECHECK: GO"] --> C["CANARY / một node phù hợp"]
    C --> D["DRAIN / tách khỏi traffic nếu hỗ trợ"]
    D --> M["MAINTAIN: restart/upgrade"]
    M --> R["REJOIN: health và replica catch-up"]
    R --> V{"POST-STEP gates đạt?"}
    V -->|"Không"| STOP["STOP + incident/recovery"]
    V -->|"Có"| N{"Còn node cần bảo trì?"}
    N -->|"Có"| C
    N -->|"Không"| FINAL["POSTFLIGHT + handoff"]
~~~

Các bước drain/rejoin/leader handling khác nhau theo engine và cluster role. Không coi một service process “UP” là đủ qua gate; cần kiểm **replication, query correctness, latency và capacity**.

## 31. Thứ tự node và leader role

Trong nhiều mô hình leader–follower, người vận hành thường ưu tiên xử lý followers/secondaries trước và primary/leader sau **theo runbook phiên bản cụ thể**.

Lý do:
- Giảm số lần chuyển primary sớm.
- Cho phép mỗi follower bắt kịp sau khi restart.
- Tránh giảm voting availability quá mức.
- Kiểm driver ứng dụng tương thích với mixed versions nếu đang upgrade.

Nhưng không tự động áp dụng cho mọi hệ. Một số operations yêu cầu leader change trước; một số managed services kiểm soát việc này. **Bắt buộc tham khảo compatibility và upgrade order chính thức của deployment đang chạy.**

## 32. Per-step checkpoint trước khi qua node tiếp theo

Một node chỉ được đánh dấu `REJOINED` nếu:
- Process/service health đạt.
- Replica membership và role hợp lệ.
- Data catch-up đạt ngưỡng.
- Không có sustained errors.
- Cache/CPU/disk pressure ổn định theo policy.
- Cluster vẫn còn redundancy cần thiết.
- Không có background backlog bất thường.
- Ghi audit timestamp, operator, metric snapshot.

Nếu không đạt, **dừng chuỗi rolling**, không tiếp tục chỉ vì lịch bảo trì gần hết.

## 33. Planned stop khác abrupt failure

Một số hệ hỗ trợ graceful drain/step-down:
- Chặn/tái định tuyến traffic mới.
- Đợi queries đang xử lý hoàn tất theo chính sách.
- Flush/commit dữ liệu cần bền.
- Chuyển leadership nếu cần.
- Đưa node ra service discovery.

Graceful action giảm rủi ro nhưng **không thay backup và quorum check**. Mất nguồn điện hay kernel crash có behavior khác; failure drill có thể kiểm điểm yếu mà rolling maintenance không bộc lộ.

Không áp dụng một lệnh `drain` chung cho tất cả NoSQL vì semantics của MongoDB, Cassandra và Redis khác nhau.

## 34. MongoDB replica set: những điều kiện đặc thù

Với một deployment replica set:
- Kiểm từng thành viên, trạng thái primary/secondary và voting eligibility.
- Kiểm replication lag và oplog headroom.
- Kiểm majority availability sau khi tạm mất target.
- Kiểm write concern/read concern thực tế của ứng dụng.
- Kiểm driver failover handling, retries, connection pools.
- Kiểm FCV/compatibility khi upgrade.
- Bảo đảm backup/restore và sharded components nếu có.

Một lệnh thăm dò đọc-only thường dùng từ môi trường đã được phân quyền:

~~~javascript
rs.status();
~~~

Ví dụ này **chỉ để kiểm trạng thái**, không thay thế preflight đầy đủ. Hãy chọn thứ tự step-down/restart theo hướng dẫn cho đúng MongoDB version và topology, không vô tình rút primary khi secondaries chưa sẵn sàng.

## 35. MongoDB sharded cluster còn có nhiều lớp

Ngoài replica set của từng shard:
- Config servers và quorum.
- Routers (`mongos`) và khả năng routing.
- Shard placement, chunk movement.
- Balancer/migration đang hoạt động.
- Distributed transaction impact.
- Sharded indexes/compatibility.
- Tình trạng của backup bao phủ mọi shards và config metadata.

Một shard “healthy” không đủ nếu config server group degraded. Khi rebalance hoặc thay shard, cần kiểm capacity ở nguồn/đích, migration throttling và consistency/cutover behavior.

Không tắt balancer, chỉnh config servers hoặc di chuyển chunks theo một runbook chung mà không hiểu yêu cầu phiên bản/operation.

## 36. MongoDB driver và failover từ phía ứng dụng

Một replica set có thể phục hồi primary nhưng ứng dụng vẫn có:
- Connection pool stale.
- Server selection timeouts.
- Retry storm.
- Unsupported driver/version interaction.
- Query/read preference không phù hợp.
- Read-your-writes/freshness thay đổi.

Post-step cần đo end-to-end operations và errors, không chỉ `rs.status()`.

Ví dụ smoke test an toàn trong môi trường được duyệt:
~~~text
Read known test document.
Perform idempotent test write in dedicated namespace.
Read back with required consistency settings.
Delete dedicated test artifact per policy.
~~~

Không ghi test dữ liệu trực tiếp vào tài khoản thật chỉ để chứng minh node sống.

## 37. Cassandra: node drain, repair và compaction

Ở Cassandra cần phân biệt:
- Node status/membership.
- Token ranges, datacenter, rack.
- Keyspace replication strategy và per-DC RF.
- Consistency level đang được ứng dụng dùng.
- Pending compaction/flush, disk pressure.
- Repair schedules và anti-entropy status.
- Bootstrap/streaming/decommission progress.
- Tombstone/TTL workload.

Lệnh quan sát đọc-only thường dùng:

~~~text
nodetool status
~~~

Không coi output `UN` của mọi node là đủ để bảo trì: còn phải xét repair, disk, write pressure và phân bố token/keyspace. Các thao tác như drain, restart, repair hoặc decommission có mục đích rất khác nhau; áp dụng đúng runbook engine/version.

## 38. Cassandra không có “primary” duy nhất như leader–follower

Cassandra thường có mô hình nhiều replicas cho một partition, không một primary duy nhất của toàn cluster theo kiểu MongoDB replica set. Do đó:
- Preflight dựa vào RF và consistency level theo datacenter.
- Kiểm mỗi keyspace/partition assignment.
- Tránh đồng thời bảo trì các replicas cần để phục vụ same partition.
- Biết read/write behavior khi coordinator hoặc replica mất.
- Tính streaming/repair load khi node trở lại.

Không dùng sơ đồ “làm secondary trước, primary sau” của MongoDB cho Cassandra.

## 39. Redis Cluster: kiểm slot coverage và replicas

Redis Cluster phân phối hash slots giữa masters và replicas. Khi bảo trì:
- Kiểm tất cả slots được phục vụ theo policy.
- Kiểm master/replica mapping.
- Kiểm trạng thái failover và cluster bus/network.
- Kiểm persistence (AOF/RDB) và durability expectations.
- Kiểm replication offset/lag và backlogs.
- Kiểm client slot map refresh/redirect handling.
- Không làm đồng thời mất master và replica duy nhất của cùng slots.

Các lệnh đọc-only có thể gồm:

~~~text
CLUSTER INFO
CLUSTER NODES
INFO replication
INFO persistence
~~~

Tùy topology/phiên bản/ACL, các lệnh cần quyền thích hợp. Không suy rằng sáu Redis nodes có thể tùy ý dừng hai node: **điều quan trọng là node nào giữ slots và bản sao tương ứng**, không chỉ tổng số node còn sống.

## 40. Redis sentinel và standalone khác Redis Cluster

Với Redis Sentinel, việc bầu master và giám sát primary/replica có cơ chế khác Redis Cluster; một standalone Redis không có automatic multi-node failover tương tự.

Không chạy một checklist chung mà bỏ qua:
- Sentinels có đủ quorum theo cấu hình không?
- Replicas có đủ mới để failover không?
- Application reconnect/failover behavior thế nào?
- AOF/RDB persistence và RPO chấp nhận được không?
- TTL-heavy workloads và memory/eviction impact?

Không dùng `FLUSHALL`, xóa cache hoặc reset persistence như bước bảo trì chuẩn nếu không có change scope rõ; thao tác này có thể làm source database gặp cache miss storm.

## 41. CouchDB: replication, quorum và revision conflicts

Ở CouchDB hoặc các hệ document phân tán tương tự:
- Kiểm node membership, shard placement và replication health.
- Đánh giá consistency/write quorum theo topology thực.
- Theo dõi replication backlog, conflict revisions.
- Kiểm `_changes` checkpoint và retention/replay.
- Phân biệt document deletion, tombstone, purge.

Sau thao tác, không chỉ kiểm document có thể đọc: cần kiểm **replication convergence**, conflict policy, update visibility và quyền truy cập.

Engine có semantics khác nhau; không áp MongoDB oplog hoặc Cassandra repair mechanics trực tiếp sang CouchDB.

## 42. DynamoDB và NoSQL managed services

Với DynamoDB và dịch vụ managed tương tự, người dùng không trực tiếp restart underlying storage nodes theo cách self-managed.

Những việc người dùng **vẫn kiểm soát**:
- Table/index changes, capacity modes và autoscaling.
- Global table replication/access strategy.
- PITR/backup/restore tests.
- Streams and consumers/checkpointing.
- IAM/KMS policies.
- TTL, export/import, backfill.
- SDK retries, client connection pools.
- Service quotas, throttling và alarms.

Preflight trước thay index/bulk import/capacity/security settings vẫn cần:
- Expected workload và quotas.
- Backup recovery.
- Table/index status.
- Cost budget.
- Replication/stream lag.
- Rollout/rollback/rollforward.

Không giả định managed service miễn mọi maintenance risk hoặc tự cung cấp consistency của application-level workflow.

## 43. Không thay đổi consistency/durability để “qua gate”

Khi node degraded, một đội có thể muốn:
- Hạ write concern.
- Dùng consistency level yếu hơn.
- Tắt fsync/durability.
- Tạm bỏ read-repair/repair.
- Tăng timeout vô hạn.

Những thay đổi này có thể làm số success requests tăng nhưng **thay đổi chính hợp đồng dữ liệu** mà ứng dụng dựa vào.

Nếu bắt buộc có degraded-mode chính thức, nó phải được thiết kế, kiểm thử, phê duyệt và truyền thông trước; không phải hành động ứng biến chỉ để checklist chuyển màu xanh.

## 44. Compatibility trước rolling upgrade

Cần xác nhận:
- Database version hiện tại/đích.
- Upgrade path có hỗ trợ nhảy nhiều major versions không.
- Mixed-version cluster có được phép trong giai đoạn rolling không.
- Driver/client library compatibility.
- Protocol/schema compatibility.
- Downgrade restrictions và feature activation.
- Security ciphers, certificates và IAM changes.
- Backup tool/monitoring connector compatibility.
- Node OS/filesystem/storage constraints.

Một số thay đổi bật tính năng ở cluster-level có thể làm **quay lại binary cũ không được hỗ trợ**. Phải nêu **point of no return** trong kế hoạch.

Không dùng “upgrade tuần trước chạy được ở staging” làm bằng chứng duy nhất nếu production khác version/topology/data size.

## 45. Index build và schema/data migration

Preflight cho index/reindex:
- Query workload nào sẽ dùng index mới?
- Dung lượng index dự kiến?
- CPU/RAM/disk và write I/O headroom?
- Build có online hay chặn operations trong engine/version này?
- Có thể pause/cancel không? Side effects?
- Build ảnh hưởng replication/CDC thế nào?
- Có background compaction/backup overlap không?
- Plan cache/query behavior sau build?
- Rollout ứng dụng tương thích schema cũ/mới?

Khi migration nhiều dữ liệu, cân nhắc **expand–migrate–contract**, dual-read/dual-write nếu cần, idempotent backfill và progressive cutover. Không giả định đảo schema là đủ rollback dữ liệu đã biến đổi.

## 46. Backfill và batches cần có giới hạn

Một backfill hợp lý có:
- Cursor/checkpoint ổn định.
- Bounded batch size/concurrency.
- Throttle theo source CPU/disk/latency.
- Idempotent updates.
- Metrics processed/skipped/failed.
- Retry budget và dead-letter/reconciliation.
- Nghĩa của DELETE/TTL trong lúc backfill.
- Stop condition khi SLO hoặc replica lag tăng.

Một bulk job có thể làm cache lạnh, tăng read amplification hoặc ghi đè phiên bản mới nếu không có source version guards.

**Backfill là một công việc vận hành cụm có rủi ro không kém restart**, nhất là khi làm trên data live.

## 47. CDC consumers và retention headroom

Trước bảo trì source hoặc relay:
- Biết cursor/resume tokens và checkpoint đã lưu.
- Kiểm lag/current source log retention.
- Tính khoảng offline tối đa.
- Có snapshot/bootstrap strategy nếu cursor hết hạn.
- Đánh giá connector/SDK schema compatibility.
- Kiểm outbox backlog và consumer idempotency.

Một consumer offline lâu có thể **không resume được từ checkpoint cũ** nếu source log đã bị dọn. Không tự resume từ `latest` và coi projection vẫn đủ dữ liệu; cần rebuild/reconcile.

CDC không phải backup thay thế, còn backup chưa chắc chứa hết history mà consumer cần.

## 48. Backup và bảo mật không được tách rời

Backup có thể chứa toàn bộ tài liệu nhạy cảm. Trước khi tạo/chuyển:
- Kiểm KMS/keys/certificates còn hợp lệ.
- IAM roles tối thiểu.
- Encryption in transit/at rest.
- Data residency/scope.
- Access audit cho exports/restore.
- Retention/legal hold/deletion policy.
- Không copy production PII vào staging thiếu bảo vệ.

Khi rotate credentials hoặc encryption keys, phải xác nhận **backup cũ vẫn giải mã/khôi phục được theo policy**; khóa đã bị hủy có thể khiến backup vô dụng.

## 49. Security preflight cho thay đổi quyền/certificate

Ví dụ thay TLS certificate:
- Kiểm certificate validity/SAN/CA chain.
- Kiểm clients cũ tin CA mới.
- Kiểm thời điểm hết hạn/rotation overlap.
- Kiểm clock drift.
- Kiểm mTLS identities/ACL.
- Kiểm secret deployment tới đúng nodes.
- Có kế hoạch rollback nếu handshake errors tăng.
- Không ghi private keys vào logs/tickets.

Ví dụ rotate DB credentials:
- Xác định mọi services/consumers/jobs dùng credential.
- Hỗ trợ song song old/new identity một thời gian nếu policy cho phép.
- Đổi từng consumer với canary.
- Kiểm connection errors và access denied.
- Thu hồi credential cũ sau khi xác minh.
- Audit đầy đủ thay đổi quyền.

## 50. Đặt lịch bảo trì theo tác động nghiệp vụ

Không chỉ nhìn CPU thấp. Có thể cần tránh:
- Peak traffic theo vùng giờ khác.
- Billing/settlement window.
- Campaign, sale, release, import.
- Data warehouse/ETL batch.
- Quá trình đối soát/backup.
- Người trực chính đang không có mặt.

Một maintenance window tốt có **người chịu trách nhiệm và đường liên lạc**, không phải chỉ khoảng thời gian không có ai theo dõi.

## 51. Canaries và giới hạn blast radius

Nếu một thay đổi có thể áp dụng từng node:
1. Chọn node/cụm thử đại diện nhưng ít rủi ro.
2. Chạy immediate preflight.
3. Thực hiện một đơn vị thay đổi.
4. Đợi đủ rejoin/catch-up và kiểm SLO.
5. Đánh giá metrics/alerts.
6. Mở rộng từng bước nếu đủ điều kiện.

Nếu thay đổi không thể canary (cluster-wide config hoặc irreversible schema feature), phải có **thử nghiệm tương đương ở staging và đánh giá rủi ro mạnh hơn**. Không ép canary giả khi semantics không cho phép.

## 52. Giới hạn song song

Rolling không có nghĩa chạy cùng lúc trên mọi node theo batch.

Cần kiểm:
- Hai nodes có giữ replicas cùng shard?
- Một node ở mỗi AZ có bị down đồng thời không?
- Có đang có fault trong cùng group?
- Có bao nhiêu shards mất quorum nếu một automation job chạy nhanh hơn?
- Rejoin lag của node trước đã về mức chấp nhận chưa?

Một policy ví dụ:
~~~text
maxUnavailablePerReplicaGroup = 1
```

Chỉ là ý tưởng; con số thật phụ thuộc RF, quorum, engine semantics, failure domains, SLO và kế hoạch rủi ro.

## 53. Failure injection và diễn tập

Trước thao tác nhiều rủi ro, nên có bằng chứng từ môi trường thử:
- Replica bất ngờ chết trong khi node khác đang restart.
- Network partition ngắn.
- Disk gần đầy trong compaction.
- Backup source bị hạn chế I/O.
- CDC relay mất checkpoint.
- Client reconnect sau failover.
- Rollback binary/version.
- Khôi phục snapshot trong vùng cô lập.

**Không chạy lỗi phá hoại trên production chỉ để tick checklist** trừ khi có chương trình chaos testing được phê duyệt, phạm vi và safety controls riêng.

## 54. Giám sát trong lúc bảo trì

Một dashboard hữu ích:

| Tầng | Metric/condition |
|---|---|
| API client | Completed QPS, p95/p99, timeout/error |
| Database | Read/write latency, queue, lock/stall |
| Replica | Member state, lag, role, voting/quorum |
| Shards/partitions | Coverage, hotspot, distribution |
| Resources | CPU, memory, disk free, IOPS, network |
| Background | Compaction/repair/rebalance/backup backlog |
| Security | Auth failures, TLS errors, role changes |
| Data pipeline | CDC/outbox consumer lag |
| Application | Cache misses, driver pool pending/retry |
| Business | Known invariant checks, test transaction outcomes |

Dùng alert thresholds **đã định trước**, không chỉ nhìn một biểu đồ rồi quyết định cảm tính.

## 55. Không chỉ nhìn average latency

Một bảo trì có thể khiến:
- p50 vẫn bình thường.
- p99 tăng mạnh lúc failover.
- Một nhóm users/tenant bị timeout.
- Một shard nóng chịu lỗi cục bộ.

Nên phân loại metrics theo operation/cluster/shard có cardinality được kiểm soát, đồng thời xem **tail latency, error rate và per-node/per-tenant impact** theo quyền riêng tư.

Một API trả thành công phần lớn requests vẫn có thể vi phạm SLO nếu số nhỏ requests bị lỗi dài hạn.

## 56. Stop conditions mẫu

Ví dụ, **không phải ngưỡng chuẩn**:

~~~text
STOP nếu:
  - required quorum hoặc replica coverage không còn.
  - bất kỳ write-ack consistency guarantee nào bị vi phạm.
  - p99 hoặc error rate vượt limit trong defined windows.
  - replication/CDC lag vượt threshold hoặc tăng không kiểm soát.
  - disk gần ngưỡng an toàn của operation.
  - node trước chưa rejoin hoàn toàn.
  - backup/recovery evidence bị vô hiệu do thay đổi.
  - telemetry quan trọng mất hoặc không đáng tin.
  - xảy ra security incident.
```

Khi STOP:
1. Dừng bước tiếp theo.
2. Bảo toàn evidence/metrics.
3. Đánh giá rollback hay rollforward.
4. Gọi người chịu trách nhiệm/incident channel.
5. Không tự chạy lệnh “force” không có runbook.

## 57. Restart thành công chưa có nghĩa đã phục hồi

Một service process mới UP chưa bảo đảm:
- Replica đã catch up.
- Shard/slot phục vụ đủ.
- Cache đã nóng.
- Driver application đã reconnect.
- SLO đã ổn định.
- CDC consumers không bị bỏ mất event.
- Backup và observability vẫn hoạt động.

Do đó post-step cần **time-to-first-success**, **time-to-SLO**, **time-to-replication-caught-up** và **background backlog**. Mốc HTTP 200 đầu tiên không đủ kết luận.

## 58. Postflight checklist

~~~text
[ ] Tất cả nodes/shards/replicas expected ở trạng thái đúng.
[ ] Quorum và fault tolerance đã trở lại mục tiêu.
[ ] Data catch-up hoàn tất trong ngưỡng.
[ ] API read/write smoke tests qua đường thật đạt.
[ ] p95/p99/error rate trở về SLO/baseline.
[ ] Driver pools, retry counts và cache health bình thường.
[ ] Disk/CPU/network không bị backlog kéo dài.
[ ] Compaction/repair/backup schedules vẫn hoạt động.
[ ] CDC/outbox/stream consumers không mất checkpoint.
[ ] TLS/credential/IAM hoạt động theo scope được phê duyệt.
[ ] Backup/PITR tiếp tục đúng lịch.
[ ] Application invariants và data counts hợp lý.
[ ] Change ticket ghi timestamps, actual outcomes, exceptions.
[ ] Monitoring/alerts được hoàn nguyên và đã handoff.
~~~

Postflight cũng cần một **khoảng quan sát ổn định**, không chỉ snapshot đúng ngay sau restart.

## 59. Smoke tests phải đúng scope và an toàn

Ví dụ:
- GET một test document trong namespace riêng.
- Conditional update có expected version trên test object.
- Read-after-write theo consistency policy.
- Kiểm TTL/CDC event của test data nếu kịch bản liên quan.
- Kiểm một query index quan trọng.
- Kiểm `AUTHORIZATION_DENIED` cho access không hợp lệ khi được phép test.

Không dùng production customer record để sửa/xóa như một phép thử tùy tiện. Smoke test cần cleanup, idempotency và quyền được cấp rõ ràng.

## 60. Truy vết data correctness sau migration

Một data backfill/migration nên có:
- Record count trước/sau với giải thích biến động.
- Sampling business invariants.
- Hash/checksum/aggregate reconciliation trong phạm vi thích hợp.
- Source version guards.
- Handling của deletes/TTL/updates trong lúc copy.
- Error/dead-letter queue.
- Canaries theo partition/tenant.
- Trạng thái dual-read/dual-write nếu áp dụng.

**Đếm số records bằng nhau không tự chứng minh hai datasets có nội dung giống nhau**, đặc biệt khi có updates đồng thời và denormalization.

## 61. Rollback, rollforward và khôi phục

Ba hướng khác nhau:

| Hướng | Khi phù hợp | Rủi ro |
|---|---|---|
| Rollback config/binary | Version còn hỗ trợ đảo | Schema/feature compatibility |
| Rollforward fix | Đã qua bước không thể đảo | Cần triển khai bản sửa mới |
| Restore/rebuild dữ liệu | State hỏng hoặc mất | Có thể mất writes sau snapshot, cần reconciliation |

Kế hoạch phải xác định **ai ra quyết định**, mức ảnh hưởng, thay đổi downstream và thời gian. Nếu RPO/RTO không đáp ứng khi restore, phải có phương án phòng ngừa mạnh hơn trước GO.

## 62. Các lỗi rất thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
|---|---|---|
| Chỉ xem dashboard xanh | Che shard/replica lag | Per-group checks |
| Quorum đủ trước restart là đủ | Không tính sau khi trừ node | Failure simulation |
| Nhiều nodes đồng nghĩa an toàn | Có thể cùng failure domain | Placement review |
| Backup success = restore được | Chưa test restore | Recovery evidence |
| Chỉ xem disk còn 10% | Compaction cần temp space | Peak operation headroom |
| Lần trước upgrade được | Topology/data/version khác | Fresh preflight |
| Dừng hai replicas một lúc | Mất quorum/slot coverage | Rolling gated |
| Process UP là healthy | Lag/cache/client chưa phục hồi | Post-step gates |
| Không cần kiểm CDC | Consumer có thể mất resume cursor | Retention/catch-up |
| Tắt compaction/repair cho nhẹ | Tích lũy debt/rủi ro consistency | Risk assessment |
| Force khi preflight lỗi | Bỏ cơ chế bảo vệ | NO-GO và escalation |
| Thay consistency cho đỡ lỗi | Đổi hợp đồng dữ liệu | Pre-approved degraded mode |
| Restore backup là rollback đơn giản | Mất writes mới | RPO/reconciliation |
| Quên config servers/routers | Sharded cluster nhiều lớp | Full topology |
| Dùng MongoDB order cho Cassandra | Mô hình replication khác | Engine-specific runbook |
| Dừng Redis node ngẫu nhiên | Mất slots/replica | Slot/role mapping |
| Managed DB không cần preflight | Index/IAM/capacity vẫn có rủi ro | User-controlled changes |
| Checklist từ hôm qua còn đủ | State thay đổi | Immediate preflight |
| Không có STOP conditions | Người trực quyết định trong hoảng loạn | Explicit gates |
| Không lưu evidence | Khó điều tra sự cố | Change log/metrics |
| Chỉ đo mean | Che p99 spike | Tail/error metrics |
| Bảo trì lúc đêm chắc rảnh | Backup/ETL/global traffic | Full schedule |
| Xoá production cache để “warm lại” | Cache miss storm | Throttled prewarm |
| Thao tác bảo mật không cần thử client | TLS/IAM có thể làm lỗi kết nối | Canary/dual-key |
| Không kiểm disk spool/backup privacy | Dữ liệu nhạy bị lộ | IAM/encryption/retention |
| “Đã GO thì làm hết” | State thay đổi mỗi bước | Recheck after each |
| Chạy automation không lock | Hai changes va nhau | Exclusive maintenance lease |

## 63. Một runbook bảo trì điển hình

~~~text
PHASE 0 — PLAN
  Define change, target, window, owner, SLO, rollback, point-of-no-return.
  Review topology, versions, dependencies and failure domains.
  Verify recovery objectives and permissions.

PHASE 1 — IMMEDIATE PREFLIGHT
  Fresh topology, replica/quorum/slot coverage.
  Replica lag, disk/CPU/network headroom.
  Recovery evidence, no conflicting jobs.
  Baseline SLO, alerts, CDC/stream headroom.
  GO/NO-GO decision recorded.

PHASE 2 — CANARY / ONE UNIT
  Drain/stepdown only by engine-specific runbook.
  Apply maintenance to one safe target.
  Rejoin, catch up, warm.
  Check correctness and SLO; STOP on gate failure.

PHASE 3 — ROLL
  Recompute safety margin before every next target.
  Never proceed with unresolved degraded state.
  Record steps, metrics and decisions.

PHASE 4 — POSTFLIGHT
  Validate topology, data, SLO, background queues.
  Verify backups/streams/security.
  Handoff, debrief and update runbook.
~~~

Đây là **khung tư duy**, không thay các lệnh/khuyến cáo chính thức theo engine và phiên bản.

## 64. Bài tập thực hành

### Bài tập 1 — Trạng thái quorum ba bản sao

Nhóm 3 voting replicas cần majority 2. Một node đã down, operator muốn reboot một node còn khỏe. Giải thích GO/NO-GO, ảnh hưởng nếu vẫn làm và điều kiện cần khôi phục trước.

### Bài tập 2 — Rủi ro lỗi thứ hai

Ba replicas đều khỏe, cần reboot một node. Sau khi rút node, hệ còn quorum 2/3. Hãy tính khả năng chịu thêm lỗi và đề xuất risk policy cho thời gian bảo trì.

### Bài tập 3 — Failure domains

Một shard có ba replicas nhưng cả ba nằm cùng AZ. Preflight nào chỉ ra rủi ro và đề xuất placement mới?

### Bài tập 4 — Cassandra LOCAL_QUORUM

RF=3 trong một DC, một replica down và một replica khác dự kiến drain. Giải thích tác động tới `LOCAL_QUORUM`, không trộn replica count của DC khác.

### Bài tập 5 — Redis slots

Redis Cluster có ba masters, mỗi master một replica. Một replica của master A đã down. Nếu reboot master A sẽ ra sao? Cần kiểm gì trước?

### Bài tập 6 — Replication lag

Primary ở position P1000, hai followers P999 và P850. Đề xuất điều kiện leader failover/bảo trì, data catch-up và cách không hứa mất 0 writes nếu write concern yếu.

### Bài tập 7 — Backup vs restore

Backup job báo success nhưng chưa từng restore. Xây checklist chứng minh artifact, encryption keys, RPO/RTO và application data validity.

### Bài tập 8 — RPO/RTO

RPO yêu cầu 5 phút, RTO 30 phút; backup cuối 3 giờ trước, không có PITR. Phân tích GO/NO-GO cho một migration không thể đảo.

### Bài tập 9 — Disk headroom

Một node còn 12% disk trống, compaction/reindex dự kiến cần temporary bytes lớn. Hãy mô tả cách ước tính peak usage và stop conditions, không dùng con số phần trăm tùy ý.

### Bài tập 10 — Capacity khi mất node

Ba nodes mỗi node tải khoảng 55%. Nếu tải chia đều qua hai nodes sau bảo trì, ước tính phần trăm mới và nêu các giả định khiến kết quả thực tế khác.

### Bài tập 11 — Cache lạnh sau restart

Replica đã catch up nhưng p99 vẫn cao vì cache pages lạnh. Đề xuất warm-up/canary và metric để biết khi nào được chuyển sang node tiếp.

### Bài tập 12 — Background overlap

Backup, repair, compaction cùng chạy lúc 02:00. Thiết kế ma trận nguy cơ disk/network và cách thay đổi lịch mà không tắt những job bảo vệ dữ liệu tùy tiện.

### Bài tập 13 — Immediate preflight

Checklist được hoàn tất 12 giờ trước cửa sổ. Vì sao chưa đủ? Thiết kế những kiểm tra cần lấy ngay trước action.

### Bài tập 14 — GO/NO-GO automation

Viết pseudocode fail-closed khi topology, backup evidence, replica lag hoặc SLO metric thiếu/stale. Nêu cách audit ngoại lệ.

### Bài tập 15 — Rolling state machine

Vẽ PRECHECK → DRAIN → MAINTAIN → REJOIN → VALIDATE → NEXT, định nghĩa điều kiện STOP và checkpoint.

### Bài tập 16 — MongoDB replica set

Tạo một preflight cho 3-node replica set có một secondary đang lag. Phân biệt rs.status(), actual write concern và điều kiện upgrade/stepdown.

### Bài tập 17 — MongoDB sharding

Một sharded cluster có shard replicas khỏe nhưng config server group degraded. Vì sao không nên chỉ nhìn shard dashboard?

### Bài tập 18 — MongoDB application behavior

Sau primary switch, driver tạo nhiều timeouts và retries. Các postflight checks nào cần ở tầng Java application?

### Bài tập 19 — Cassandra repair

Vì sao không tắt repair và giảm tombstone grace chỉ để giữ I/O thấp trong kỳ bảo trì? Nêu hậu quả nhất quán.

### Bài tập 20 — Redis Sentinel vs Cluster

So sánh preflight failover/quorum/slots cho Redis Sentinel, Redis Cluster và standalone. Không dùng một lệnh chung cho cả ba.

### Bài tập 21 — Managed database

Nhóm dùng DynamoDB không tự restart nodes. Hãy liệt kê các thao tác index, capacity, backup, Global Tables, IAM, KMS, Streams vẫn cần preflight.

### Bài tập 22 — CDC lag

Consumer sẽ offline trong kỳ nâng cấp, checkpoint gần hết source log retention. Thiết kế cách tránh mất data hoặc khởi động lại bằng snapshot/catch-up.

### Bài tập 23 — Version compatibility

Cluster version X muốn nâng lên Z, bỏ Y. Những câu hỏi nào cần xác minh về mixed versions, FCV, driver và downgrade restrictions?

### Bài tập 24 — Certificate rotation

Thiết kế preflight/canary và rollback cho TLS certificate mới, bao gồm CA trust, expiry, clock drift và ứng dụng chưa cập nhật.

### Bài tập 25 — Schema migration

Một migration chuyển field, backfill 20 triệu documents live. Thiết kế idempotent batches, source version guards, stop conditions và đối soát.

### Bài tập 26 — Failure drill

Trong lúc rolling node restart, một node khác đột ngột lỗi. Dự kiến cluster behavior gì, ai được STOP, khi nào incident escalation?

### Bài tập 27 — Runbook stop

Sau bước thứ hai, replication lag liên tục tăng và p99 vượt ngưỡng. Viết thứ tự hành động dừng, lưu evidence, tìm nguyên nhân, quyết định rollback/rollforward.

### Bài tập 28 — Recovery time

Node khởi động lại trả HTTP 200 sau 15 giây nhưng cần 12 phút mới về p99 SLO. Bạn báo thời gian phục hồi nào và cần metric gì?

### Bài tập 29 — Data correctness

Reindex hoàn tất và record counts bằng nhau. Vì sao vẫn phải kiểm source versions, deletes/TTL và sample business invariants?

### Bài tập 30 — Maintenance governance

Viết change request có owner, approval, scope, window, affected tenants, stop conditions, backup refs và handoff.

### Bài tập 31 — Audit và security

Credentials được rotate nhưng một batch consumer vẫn dùng khóa cũ. Hãy thiết kế overlap, kiểm failure, revoke và audit.

### Bài tập 32 — Khác biệt rollback và restore

Sau migration, dữ liệu mới phát sinh được 45 phút. Vì sao restore snapshot trước migration có thể vi phạm RPO và tạo divergence downstream? Đề xuất cách đối soát.

### Bài tập 33 — Thiết kế bảo trì đa nền tảng

Một nền tảng có MongoDB replica set/sharded data, Cassandra activity store, Redis Cluster cache, DynamoDB managed tables và Java services. Lập kế hoạch:

1. Inventory topology, shard/partition/slot coverage và failure domains.
2. Quorum/consistency safety theo từng engine.
3. Backup, PITR, restore drill, RPO/RTO.
4. Disk/CPU/memory/network headroom.
5. Compaction/repair/backup/CDC interference.
6. Version/driver/TLS/IAM compatibility.
7. Rolling/canary sequence và per-step gates.
8. SLO/error/lag/capacity dashboards.
9. Stop, rollback/rollforward, incident escalation.
10. Postflight integrity checks và handoff.

### Bài tập 34 — Phản biện một kế hoạch sai

Một đội viết:

~~~text
Cluster đang xanh nên có thể restart hai nodes cùng lúc.
Không cần backup vì cloud disks đã có snapshots tự động.
Nếu follower lag lớn, hạ consistency xuống mức yếu nhất.
Compaction và repair tắt để giảm tải.
Nếu mất CDC cursor, resume từ latest.
Sau restart thấy process UP thì coi đã hoàn tất.
Không cần kiểm client driver hoặc p99.
Rollback bằng restore snapshot ba ngày trước.
```

Chỉ ra từng giả định sai, ảnh hưởng, điều kiện GO/NO-GO tương ứng và viết lại kế hoạch bảo trì an toàn.

---

**Kết luận:** Bảo trì định kỳ cho cụm NoSQL phải được xem là **một thay đổi có kiểm soát đối với hệ đang có trạng thái**, không phải danh sách lệnh chạy theo lịch. Trước mỗi thao tác cần xác minh **topology/failure domains, quorum và replica coverage sau khi rút node, data/replication lag, bản sao khôi phục được, RPO/RTO, capacity headroom, SLO, background tasks, compatibility, security và quyền ra quyết định**. Trong khi thực hiện, dùng **canary hoặc rolling có checkpoint**, dừng ngay khi gate không đạt và đánh giá rollback/rollforward theo khả năng thật của engine. Sau đó phải kiểm **dữ liệu, ứng dụng, CDC, backup, security và tail latency**, không chỉ process health. **GO/NO-GO dựa trên bằng chứng cập nhật và runbook engine-specific** giúp bảo trì đúng lịch mà vẫn bảo vệ tính sẵn sàng, độ bền dữ liệu và khả năng phục hồi khi một lỗi bất ngờ xuất hiện.
