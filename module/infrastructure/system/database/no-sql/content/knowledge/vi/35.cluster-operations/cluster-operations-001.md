# Lập cấu trúc cụm (topology) và phân bổ nút theo miền lỗi

Trong hệ thống NoSQL phân tán, **ba bản sao dữ liệu** không đồng nghĩa với **chịu được mất một Availability Zone (AZ)**. Nếu cả ba replicas nằm chung một rack, một storage controller hoặc một AZ, một sự cố ở đúng miền lỗi đó vẫn có thể làm mất toàn bộ khả năng đọc/ghi. Ngược lại, đặt replicas trải nhiều AZ có thể cải thiện khả năng chịu lỗi, nhưng **quorum, bandwidth, latency, dung lượng dự phòng, vị trí ổ đĩa, metadata nodes và quy trình failover** vẫn có thể khiến dịch vụ không hoạt động sau khi một AZ mất.

Bài học này thuộc chương **Vận hành cụm** của module **Database No SQL**, tập trung vào cách thiết kế và kiểm chứng topology: **số nodes, shards/partitions, replication factor, voter/metadata roles, placement theo failure domains, topology-aware scheduling, capacity N+1/N+AZ và multi-region disaster recovery**. Các ví dụ áp dụng cho những kiến trúc NoSQL thường gặp như document stores, wide-column databases, key-value stores, search clusters và managed cloud databases; không giả định mọi sản phẩm có cùng replication semantics.

> **Nguyên tắc trung tâm:** Hãy thiết kế topology từ **lỗi có thể xảy ra và mức dịch vụ cần giữ khi lỗi ấy xảy ra**, không bắt đầu bằng việc chọn một số lượng máy tùy ý rồi chia đều. Bản sao chỉ có ý nghĩa khi chúng tồn tại trong những failure domains thích hợp, đủ dữ liệu và quyền quyết định để phục vụ yêu cầu theo consistency contract đã công bố.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **host, process, VM, node, rack, power domain, storage domain, AZ, region và provider**.
2. Vẽ topology chỉ rõ **data nodes, replicas, shards/partitions, leaders/coordinators, voters/metadata nodes và client routes**.
3. Tính giới hạn chịu lỗi của **majority/quorum** dưới các giả định phù hợp; giải thích vì sao placement quyết định số failure domains chịu được.
4. Nhận diện **correlated failures**: nhiều nodes cùng mất vì nguồn điện, mạng, storage, AZ hoặc cấu hình vận hành chung.
5. Thiết kế **replica placement, anti-affinity và topology spread** trong VM/bare metal/Kubernetes.
6. Tính **capacity sau khi mất một node hoặc một AZ**, gồm CPU, RAM, storage, network và lưu lượng read/write/repair.
7. Phân biệt **data replication**, **metadata/control-plane quorum** và **client discovery/routing**.
8. Giải thích trade-off giữa **availability, consistency, latency, RPO, RTO và chi phí liên AZ/liên region**.
9. Hiểu giới hạn sản phẩm khi triển khai MongoDB, Cassandra/ScyllaDB, Redis, Elasticsearch/OpenSearch và managed NoSQL.
10. Lập **runbook**, thiết kế thí nghiệm mất node/AZ và xác minh quorum, correctness, p99, recovery và placement sau failover.

## 2. Tình huống xuyên suốt: Order Service cần chịu mất một AZ

Giả sử một Order Service chạy Java, lưu Orders trong NoSQL. Đội vận hành có yêu cầu:

~~~text
Business:
  - Khách hàng vẫn tạo và xem đơn trong giờ cao điểm.
  - Mất một server không được gây mất khả năng phục vụ kéo dài.
  - Một AZ mất hoàn toàn, hệ vẫn cần nhận các writes quan trọng.
  - Các writes đã ACK theo durability contract không được mất.
  - Có thời gian khôi phục và độ trễ p99 được định nghĩa.

Infrastructure:
  - Cloud Region R có ba AZ: A, B, C.
  - Database cluster tự quản (self-managed) hoặc managed tương đương.
  - Application Java có replicas trải cả ba AZ.
~~~

**Yêu cầu quan trọng nhất phải định nghĩa được**: “Vẫn phục vụ khi mất một AZ” có nghĩa bao nhiêu phần trăm requests thành công, trong bao lâu, ở write concern/consistency level nào, với RTO/RPO nào? Một topology có thể còn hai data copies nhưng chỉ cho read-only; điều đó không đáp ứng yêu cầu **accept critical writes**.

### 2.1. Một cách đặt ba replicas sai

~~~mermaid
flowchart TB
    C["Java Order API"] --> AZA
    subgraph AZA["AZ A"]
      P["Primary / Leader"]
      R1["Replica 1"]
      R2["Replica 2"]
    end
    B["AZ B — empty"]:::faint
    D["AZ C — empty"]:::faint
    classDef faint fill:#f5f5f5,color:#555
~~~

Có ba copies nhưng **chung failure domain AZ A**. Nếu AZ A mất, toàn bộ copies mất cùng lúc.

### 2.2. Một cách đặt tốt hơn cho mô hình majority ba thành viên

~~~mermaid
flowchart TB
    APP["Java application — deployed across zones"]
    subgraph A["AZ A"]
       N1["Node A: replica/voter"]
    end
    subgraph B["AZ B"]
       N2["Node B: replica/voter"]
    end
    subgraph C["AZ C"]
       N3["Node C: replica/voter"]
    end
    APP --> N1
    APP --> N2
    APP --> N3
    N1 <--> N2
    N2 <--> N3
    N1 <--> N3
~~~

Với một nhóm **ba voting members** cần **majority 2/3**, mất trọn một AZ vẫn có hai voters ở hai AZ còn lại. **Điều này mới nói nhóm còn quorum**; còn phải kiểm tra hai nodes ấy có đầy đủ data/role/eligibility, có đủ CPU/disk/network và client có kết nối được tới chúng hay không.

### 2.3. Vì sao không chỉ “đủ quorum” là xong?

Ví dụ:

- Two voters remain, nhưng một chỉ là **witness/arbiter không chứa dữ liệu**; write ACK requirement có thể không đạt.
- Data replicas còn hai, nhưng **metadata/cluster-manager quorum** đã mất.
- Quorum còn nhưng CPU sau mất AZ đạt 140%, p99 timeout hàng loạt.
- Storage volume/attachments cùng một storage failure domain, mất cùng lúc.
- Cluster đủ data nhưng Java client chỉ cấu hình IP của node đã chết.
- Load balancer/API tier nằm ở AZ chết, không còn requests đến database.
- Network partition cô lập phần còn quorum khỏi ứng dụng, mặc dù quorum vẫn có trên giấy.

**Topology là thiết kế hệ thống end-to-end**, không chỉ biểu đồ đặt ba database pods.

## 3. Phân cấp miền lỗi (failure domains)

Một **failure domain** là một phạm vi mà một sự cố chung có thể làm nhiều thành phần ngừng hoạt động đồng thời. Miền lỗi không luôn lồng nhau hoàn hảo; có những phụ thuộc chéo như shared KMS/DNS/IAM hoặc storage control plane.

| Miền lỗi | Sự cố ví dụ | Nguyên tắc phân bổ |
| --- | --- | --- |
| Process/container | Crash, OOM, deadlock | Restart/health check; không coi nhiều containers cùng host là HA độc lập |
| VM/host | Kernel panic, NIC failure, host reboot | Replicas khác hosts/VMs |
| Rack | Top-of-rack switch, nguồn điện rack | Replicas khác racks khi on-prem |
| Power/cooling | PDU hoặc cooling segment | Phân tán theo power/cooling domains thực |
| Storage | SAN controller, storage pool, disk enclosure | Tránh cùng storage failure domain dù khác VMs |
| Network segment | Switch, route, firewall, VLAN | Đường replication/client không cùng single point of failure |
| Availability Zone | Một địa điểm hạ tầng trong region bị ảnh hưởng | Replicas/voters khác AZ |
| Region | Regional control plane, network hoặc power outage | Multi-region DR/replication nếu business yêu cầu |
| Cloud/provider | Sự cố IAM/DNS/provider rộng hơn | Multi-provider chỉ khi có yêu cầu và đủ vận hành |
| Cấu hình/triển khai | Bad rollout/schema change/script đồng loạt | Staged rollouts, blast-radius controls, immutable backups |
| Bảo mật | Compromised credentials/ransomware | Isolated backup/credentials, deletion protections |

### 3.1. Khác host nhưng cùng AZ

Hai VMs khác nhau là độc lập ở cấp host, **không độc lập ở cấp AZ**. Nếu yêu cầu chịu mất AZ, anti-affinity host-level là **cần nhưng chưa đủ**.

### 3.2. Khác AZ nhưng cùng region

Nhiều AZ trong một region giảm rủi ro lỗi hạ tầng cấp zone, nhưng không giải quyết hoàn toàn **regional dependencies**. Một sự cố region-wide, sai chính sách IAM hoặc thay đổi ứng dụng đồng loạt có thể ảnh hưởng cả ba AZ.

### 3.3. Khác region nhưng cùng cấu hình xấu

Một migration phá schema được tự động triển khai tới mọi regions là **correlated logical failure**. Multi-region không thay thế backups, staged deployment, quyền hạn giới hạn và khả năng khôi phục point-in-time.

### 3.4. Một câu hỏi để tìm miền lỗi thật

> Nếu rút điện hoặc chặn network của một thành phần hạ tầng duy nhất, **những nodes/roles nào sẽ biến mất cùng nhau?**

Áp câu hỏi cho power, storage, network, scheduler, DNS, secrets, certificates, cluster-management nodes và backup pipeline.

### 3.5. Failure domains có thể do scheduler vô tình tạo ra

Ở Kubernetes, ba StatefulSet pods có thể chạy trên ba nodes khác nhau nhưng tất cả nodes thuộc **một AZ** nếu không có zone spread/anti-affinity được áp và đủ capacity. Một storage volume được bind vào AZ A cũng có thể khiến pod **không di chuyển được** sang AZ B sau node loss.

## 4. Nền tảng topology: replication và sharding khác nhau

### 4.1. Replication

**Replication** tạo nhiều copies của cùng logical data để tăng availability, durability và đôi khi read capacity:

~~~text
Shard S1:
  replica S1-A in AZ A
  replica S1-B in AZ B
  replica S1-C in AZ C
~~~

Nếu chỉ mất một replica, vẫn còn những copies khác.

### 4.2. Sharding / partitioning

**Sharding** chia data thành nhiều partitions để scale storage/throughput:

~~~text
Orders shard S1: keys hash range 0..33%
Orders shard S2: keys hash range 33..66%
Orders shard S3: keys hash range 66..100%
~~~

Shard S1, S2, S3 **không phải ba copies của cùng dữ liệu**. Nếu mỗi shard chỉ có một bản sao, mất node giữ S2 có thể khiến một phần dataset không khả dụng.

### 4.3. Kết hợp replication + sharding

~~~text
Shard S1 -> A, B, C
Shard S2 -> B, C, A
Shard S3 -> C, A, B
~~~

Mỗi shard có ba replicas trải ba AZ. Có thể xoay leader/coordinator placement để phân tán tải nếu engine hỗ trợ và phù hợp với routing/replication protocol.

### 4.4. Roles không đồng nghĩa machine

Một physical/virtual node có thể chứa:

- Nhiều partition replicas.
- Primary role ở shard S1 nhưng follower ở shard S2.
- Coordinator/query router role.
- Cluster-manager/voter role.
- CDC/backup agent.

Vì vậy đánh giá topology cần **placement của từng replica group và control-plane group**, không chỉ số đếm nodes tổng.

### 4.5. Một replica không phải một backup

Replication truyền cả những thay đổi xấu như accidental deletes, corrupted application writes, ransomware operations trong nhiều thiết kế. Backup/PITR cần **đường khôi phục riêng, retention và quyền truy cập độc lập**.

## 5. Quorum: đặt replicas ở đâu quan trọng bằng có bao nhiêu

Với **majority voting group** có \(N\) voters và cần hơn một nửa:

\[
Q_{\mathrm{majority}} =
\left\lfloor\frac{N}{2}\right\rfloor+1
\]

Số voters có thể mất mà vẫn giữ majority nếu các voters còn lại reachable/eligible:

\[
F_{\mathrm{voter}}=
N-Q_{\mathrm{majority}}
\]

Ví dụ:

| Voting members \(N\) | Majority \(Q\) | Mất tối đa bao nhiêu voters mà còn majority |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |

**Lưu ý:** Bảng chỉ mô tả một **majority voting group**, không phải toàn bộ durability/write-availability của mọi NoSQL engine. Data replicas, metadata voters, consistency levels và protocol may differ.

### 5.1. Vì sao ba voters ở ba AZ hữu ích?

~~~text
AZ A: voter A
AZ B: voter B
AZ C: voter C
~~~

Mất một AZ ⇒ còn hai voters ⇒ giữ majority 2/3 **nếu hai voters có thể liên lạc**.

### 5.2. Ba voters nhưng phân bổ 2–1–0

~~~text
AZ A: voter A1, voter A2
AZ B: voter B1
AZ C: none
~~~

Nếu mất AZ A ⇒ chỉ còn voter B1 ⇒ không có majority. Cùng ba voters nhưng **fault tolerance theo AZ khác hoàn toàn**.

### 5.3. Bốn voters không tự chịu được mất hai members

N=4 cần majority 3; mất 2 chỉ còn 2 ⇒ không có quorum. Vì vậy dùng một voting group **odd-sized** thường tránh một voter thừa không tăng số faults chịu được trong majority voting. Nhưng số voters tối ưu còn phụ thuộc sản phẩm, role constraints và placement.

### 5.4. Năm voters và phân bố AZ

Nếu 5 voters phân bố A:2, B:2, C:1, mất bất kỳ **một AZ**:

- Mất A còn 3 voters ⇒ majority 3/5.
- Mất B còn 3 voters ⇒ majority.
- Mất C còn 4 voters ⇒ majority.

Vẫn chịu mất 1 AZ. Nhưng mất đồng thời A và B còn 1 voter ⇒ không có majority. **Đừng nhầm chịu 2 voter failures với chịu 2 AZ failures**.

### 5.5. Quorum không đồng nghĩa có đủ data

Một số hệ có **witness/arbiter** tham gia bầu leader nhưng không chứa full data copy. Nếu data availability/write acknowledgment cần đủ data-bearing replicas, chỉ đủ votes chưa đủ. Cần đánh giá **data quorum và voting quorum cùng lúc**.

### 5.6. “Quorum intersection” cần điều kiện

Trong một replicated log/consensus model, majority quorums giao nhau, hỗ trợ bảo toàn thứ tự quyết định dưới protocol. Nhưng với leaderless NoSQL, công thức `R + W > RF` không tự chứng minh linearizability trong mọi lỗi hoặc concurrent writes; cần xét engine semantics, conflict resolution, sloppy quorum, hinted handoff, repair và timestamp ordering.

## 6. Split-brain và fencing

**Split-brain** xảy ra khi hai nhóm thành viên tin rằng mình có quyền thực hiện thao tác primary/leader hoặc ghi cùng tài nguyên mà không có coordination đủ mạnh.

### 6.1. Một network partition ví dụ

~~~text
AZ A      |          AZ B + AZ C
Leader A  |          Follower B, Follower C
          X  network partition
~~~

Trong mô hình majority 2/3, phía B+C có thể elect new leader; phía A **không còn majority** nên không được tiếp tục commit writes cần quorum. Nếu application vẫn gửi writes tới A và A ACK như thể thành công, system có thể tạo diverging histories nếu protocol/fencing không ngăn.

### 6.2. Fencing token/term

Consensus systems thường dùng **term/epoch/generation** hoặc lease và admission rules để ngăn leader cũ tiếp tục ghi sau khi mất quyền. Không tự “tự chọn leader” bằng biến cấu hình trên từng node mà không có fencing an toàn.

### 6.3. DNS/IP failover chưa phải fencing

Đổi DNS sang leader mới không ngăn một client dùng connection cũ tiếp tục ghi vào old leader. Hệ phải kiểm soát **write authority ở server/storage/protocol**, không chỉ chỉnh client routing.

### 6.4. Safety và availability

Trong network partition, hệ có thể **từ chối writes ở phía không có quorum** để bảo vệ consistency. Đó là hành vi đúng theo contract mạnh, không phải bug “cứ có node là phải ghi được”.

### 6.5. Multi-region split-brain phức tạp hơn

Hai regions active-active nhận concurrent writes hợp lệ trong partition có thể cần **domain conflict resolution/CRDT/authority routing**, không phải chỉ chọn max wall-clock timestamp. Cần xác định bất biến nghiệp vụ trước khi cho mọi region ghi đồng thời.

## 7. Kiến trúc minh họa: ba AZ, nhiều shards và replicas

Giả sử cluster gồm sáu data nodes: mỗi AZ hai nodes. Dữ liệu chia thành ba logical shards, mỗi shard có **ba copies ở ba AZ**:

~~~text
Region R
┌──────────────────── AZ A ────────────────────┐
│ Node A1: S1 replica, S3 replica             │
│ Node A2: S2 replica                         │
└──────────────────────────────────────────────┘
┌──────────────────── AZ B ────────────────────┐
│ Node B1: S1 replica, S2 replica             │
│ Node B2: S3 replica                         │
└──────────────────────────────────────────────┘
┌──────────────────── AZ C ────────────────────┐
│ Node C1: S1 replica, S3 replica             │
│ Node C2: S2 replica                         │
└──────────────────────────────────────────────┘

Each shard S1/S2/S3 has one replica in each AZ.
~~~

Đây là **mô hình placement**, không phải một config có sẵn. Một số engines tạo partition replication tự động theo policy; số shards, lượng dữ liệu và leader roles thực tế có thể khác xa sơ đồ này.

### 7.1. Vì sao cần ánh xạ theo từng shard?

Một bảng tổng số có thể báo “cluster=6 nodes, replicationFactor=3”, nhưng nếu shard S2 có ba copies đều ở AZ C, mất C vẫn khiến S2 không khả dụng. **Fault-tolerance check phải duyệt placement của từng replication group**, không chỉ đếm tổng data nodes.

### 7.2. Phân bổ leaders

Trong leader–follower/sharded systems, có thể muốn:

~~~text
S1 leader -> AZ A
S2 leader -> AZ B
S3 leader -> AZ C
~~~

Điều này giảm khả năng mọi writes phải đi qua một AZ, nhưng phải cân nhắc **hot keys**, load distribution, client affinity, failover và leader placement controls mà engine thật sự hỗ trợ.

### 7.3. Cách hiểu node-count

Sơ đồ trên có **sáu data nodes**, **chín shard copies**. Một node có thể lưu nhiều shard copies. Chín shard copies không có nghĩa chín máy và cũng không có nghĩa cluster giữ được mọi shard khi mất bất kỳ ba nodes: nếu ba nodes bị mất đúng nơi chứa các copies của một shard, shard đó vẫn không khả dụng.

### 7.4. Data placement và metadata placement độc lập

Ngoài các data shards, nhiều engines có:

- Cluster-manager/control-plane voting members.
- Configuration servers.
- Schema/catalog metadata.
- Router/coordinator services.
- Service discovery.

Nếu metadata quorum chỉ ở AZ A trong khi data replicas trải cả ba AZ, mất AZ A có thể vẫn **ngừng xử lý thay đổi topology, shard routing hoặc một số operations**. Cần vẽ control plane như một nhóm cần bảo vệ riêng.

## 8. Capacity N+1 và N+AZ: đủ sống sót chưa đủ phục vụ tốt

**N+1 capacity**: hệ có thể tiếp tục đáp ứng SLO khi mất một đơn vị tài nguyên đã xác định, thường là một node. **N+AZ capacity**: còn đủ tài nguyên sau khi mất toàn bộ nodes/resources trong AZ lớn nhất mà workload có thể cần.

### 8.1. Một công thức bắt đầu

Giả sử \(N\) nodes đồng đều, mỗi node có capacity hữu ích \(C\), workload yêu cầu tổng \(W\). Khi mất \(F\) nodes:

\[
\mathrm{utilizationAfterFailure}
\approx \frac{W}{(N-F)\,C}
\]

Trong trạng thái thường:

\[
\mathrm{utilizationNormal}\approx\frac{W}{N\,C}
\]

Kết hợp:

\[
u_{\mathrm{after}}\approx
u_{\mathrm{normal}}\cdot\frac{N}{N-F}
\]

**Đây là mô hình phân tải đồng đều lý tưởng**. Với shards nóng, leaders cố định, per-partition throughput caps và replication work tăng sau failover, áp lực thực tế có thể cao hơn.

### 8.2. Ví dụ sáu nodes, mất một AZ hai nodes

~~~text
3 AZ: A, B, C
2 data nodes per AZ
Total nodes N=6
Worst single-AZ loss F=2
~~~

Nếu normal utilization trung bình là 55%:

\[
u_{\mathrm{after}}\approx
55\%\times\frac{6}{4}=82{,}5\%
\]

82,5% trung bình có thể không đủ headroom cho bursts, rebuilding, compaction và quorum overhead. Nếu muốn mục tiêu sau lỗi **không vượt 70%** trong mô hình:

\[
u_{\mathrm{normal}}\le
70\%\times\frac{4}{6}
\approx46{,}7\%
\]

Đây là **bài tính sơ bộ**, không có nghĩa mọi engine phải chạy dưới 46,7% CPU. Tải có thể không phân phối lại hoàn hảo; cần test theo throughput/latency SLO, per-shard metrics và nguồn lực I/O/memory.

### 8.3. Sizing phải theo tài nguyên giới hạn thực

Nên tính riêng:

| Tài nguyên | Câu hỏi sau mất AZ |
| --- | --- |
| CPU | Remaining nodes xử lý tăng reads/writes, replication và compaction được không? |
| RAM/cache | Working set có bị dồn, cache miss tăng không? |
| Network | Cross-AZ links/egress, client routing và replication có bị bão hòa? |
| Disk IOPS | Quorum writes, random reads, rebalancing tăng bao nhiêu? |
| Disk throughput | Rebuild/snapshot có chiếm hết bandwidth? |
| Storage free | Có space để tái tạo replicas/SSTables không? |
| Connection limits | Clients chuyển qua nodes sống có vượt max connections không? |
| Metadata quorum | Nodes còn lại có đủ voters/roles để điều phối không? |
| Application | API pods còn lại có phục vụ lưu lượng không? |

Một cluster có CPU còn dư nhưng storage hết free space khi rebuilding vẫn không đạt khả năng phục hồi.

### 8.4. N+1 node khác mất một AZ

Nếu cluster có 3 AZ với 10 nodes tập trung 8 ở AZ A, 1 ở B, 1 ở C, mất một node bình thường là nhẹ; mất AZ A làm mất 80% capacity. **Cần sizing theo AZ có blast radius lớn nhất**, không chỉ một node.

### 8.5. Data capacity và replication factor

Nếu logical live data là \(D\), replication factor \(RF\), phần dữ liệu replicated thô có thể khoảng:

\[
D_{\mathrm{raw}}\approx D\times RF
\]

Đây chỉ là phần **copies**, chưa gồm indexes, WAL, tombstones, compaction workspace, compression variability, backups, temporary snapshots, replication logs và metadata.

Ví dụ logical 10 TiB với RF=3 cần khoảng **30 TiB raw replica payload** trước overhead. Dung lượng phân bổ **theo AZ và theo node** còn quyết định khả năng chịu lỗi. Không đặt 30 TiB trên một storage pool rồi coi đã bảo vệ khỏi pool failure.

### 8.6. Trong lúc mất AZ, có khôi phục RF ngay không?

Giả sử một shard có một copy ở mỗi AZ A/B/C, AZ A mất. B/C còn hai copies:

- Một số systems vẫn phục vụ reads/writes theo quorum/consistency contract.
- Tạo **copy thứ ba ở B hoặc C** có thể làm trùng failure domain, không khôi phục đa dạng AZ.
- Chờ AZ A trở lại có thể giữ RF tạm dưới mục tiêu, tăng rủi ro nếu thêm failure.
- Nếu cluster có AZ D hoặc plan chuyển sang khác region, cần đánh giá network/placement/consistency.

Không giả định replica operator tự xây lại cùng RF trong khi giữ nguyên mọi failure-domain guarantees.

## 9. Data loss, durability, availability: ba bài toán tách biệt

### 9.1. Availability

Hệ có trả lời operations trong thời hạn/SLO sau lỗi không?

### 9.2. Durability/RPO

Những writes đã được source ACK theo mức nào có thể mất sau lỗi?

### 9.3. Consistency

Khi còn hoạt động, reads và writes tuân thủ causal/order/transaction contract nào?

Một topology có thể **available nhưng eventual/stale**, hoặc **giữ consistency bằng cách từ chối writes** khi quorum mất. Không dùng từ “highly available” chung chung mà không nói behavior của critical reads/writes.

### 9.4. RPO và RTO

- **Recovery Point Objective (RPO):** Mức mất dữ liệu tối đa chấp nhận được, thường biểu diễn theo thời gian hoặc committed operations theo nghiệp vụ.
- **Recovery Time Objective (RTO):** Thời gian phục hồi dịch vụ tới mức được xác định.

RPO=0 với acknowledged critical writes là yêu cầu khó, phụ thuộc replication/durability protocol và failure model; multi-region **asynchronous** thông thường không tự cung cấp RPO=0 khi toàn source region bị mất.

### 9.5. RTO khác failover detection

Nếu node loss được phát hiện trong 5 giây nhưng election mất 15 giây, Java driver reconnect mất 10 giây và data catch-up 2 phút, **user-visible RTO không bằng 5 giây**. Cần đo end-to-end từ outage tới operations ổn định và đúng.

### 9.6. Availability và quorum trong outage

Một majority-based cluster mất quorum có thể cho một số reads từ snapshot/local state theo cấu hình, nhưng từ chối leader writes. Điều đó có thể vẫn đúng safety contract; vận hành phải thiết kế **error modes, client fallback và runbook** thay vì cố ép writes tiếp tục.

## 10. Các topology mẫu và đánh đổi

### 10.1. Một node, một AZ

~~~text
AZ A: data node + app
~~~

Ưu điểm: đơn giản, ít chi phí. Nhược điểm: host/AZ outage gây downtime; chỉ phù hợp môi trường học, development hoặc workload chấp nhận rủi ro rõ ràng.

### 10.2. Hai nodes, hai AZ

~~~text
AZ A: data/voter A
AZ B: data/voter B
~~~

Với **majority của 2**, cần 2/2; mất một node sẽ mất quorum. Một số sản phẩm dùng witness/arbiter hoặc chế độ failover khác; nhưng điều đó không tự đảm bảo data-bearing quorum/durability.

**Đừng xem 2 replicas tự động là high availability cho consistent writes.**

### 10.3. Ba voting data nodes, ba AZ

~~~text
AZ A: A
AZ B: B
AZ C: C
~~~

Phù hợp để phân tích majority 2/3 và một-AZ fault tolerance. Nhưng throughput, storage và recovery policy phải được đo. Một data-heavy cluster có thể cần nhiều hơn ba machines và placements cho mọi shard.

### 10.4. Nhiều data nodes, mỗi AZ nhiều nodes

~~~text
AZ A: A1 A2 A3
AZ B: B1 B2 B3
AZ C: C1 C2 C3
~~~

Dùng replication-aware partitioning để mỗi shard có replicas ở các AZ khác nhau, đồng thời **phân phối leader/hot partitions/capacity**. Chỉ thêm nodes không bảo đảm placement correct nếu scheduler/engine vẫn có thể đặt nhiều copies cùng AZ.

### 10.5. Hai regions active–passive

~~~mermaid
flowchart LR
    APP["Java app"] --> RA["Region A — active cluster"]
    RA -->|asynchronous DR replication| RB["Region B — standby"]
    RB --> REC["Region failover after policy check"]
~~~

Ưu điểm: DR/region-failure plan, đọc/ghi thường xuyên ở một authority. Đánh đổi: asynchronous replication có **RPO lớn hơn 0 trong một số failure windows**, failover cần fencing và kiểm tra trạng thái standby.

### 10.6. Hai regions active–active

~~~text
Region A accepts writes <---- cross-region replication ----> Region B accepts writes
~~~

Ưu điểm: latency gần người dùng và có thể phục vụ writes ở nhiều regions. Đánh đổi: concurrent writes/conflicts, duplicate business actions, failover/routing, cross-region egress và semantics phức tạp. **Không coi active-active là nâng cấp “chỉ đổi config” từ active-passive.**

### 10.7. Three-region quorum / witness arrangement

Một topology có hai data regions và vùng thứ ba cho voting/witness có thể giải quyết một số election ambiguity, tùy engine. Nhưng:

- Witness không lưu data copy.
- Mất một data region có thể không còn data quorum cho writes.
- Cross-region round trips làm write latency tăng.
- Một region có multiple voters có thể tạo fault-domain imbalance.

Phải phân tích **quorum về votes và data** theo từng failure case, không chỉ vẽ ba chấm trên bản đồ.

## 11. Latency và chi phí liên AZ/liên region

Synchronous replication/quorum acknowledgement có thể cần **ít nhất một hoặc nhiều round trips** giữa các replicas. Latency bị quyết định bởi **critical quorum path**, không chỉ độ trễ tới node gần nhất.

### 11.1. Ví dụ logical

~~~text
Client -> leader: 3 ms
Leader -> replica same AZ: 1 ms
Leader -> replica other AZ: 3 ms
Leader -> replica other region: 75 ms
~~~

Nếu write ACK đòi một remote-region vote/replica trong critical path, p99 có thể tăng đáng kể so với same-region quorum. Những số trên chỉ là minh họa; actual network path/protocol sẽ khác.

### 11.2. Đừng tự đổi consistency để lấy benchmark đẹp

Giảm write concern từ majority/durable sang one/async có thể giảm latency nhưng thay đổi **rủi ro mất acknowledged writes**. Đó là một quyết định về product/data contract, không phải một tuning CPU vô hại.

### 11.3. Tính egress

Nếu source phát 50 MiB/s logical writes cần chuyển sang hai remote replicas, traffic replication payload có thể có quy mô hàng trăm MiB/s sau protocol overhead, index/compaction/tracing và topology routing. Cloud providers có thể tính phí cross-AZ/region data transfer. Phải đo **actual replication bytes, ACK path và egress charges**, không chỉ logical application bytes.

### 11.4. Read locality và cache

Ứng dụng Java ở AZ A đọc replica ở AZ C có thể tăng RTT; một load balancer route sang stale follower vì nearest policy có trade-off freshness. Thực tế cần kết hợp **replica eligibility, source consistency và network proximity**, không tự pin mọi reads vào một node.

### 11.5. Region failover khác AZ failover

AZ failover thường diễn ra trong cùng region với cơ chế cluster nội bộ. Region failover có thể liên quan DNS, global load balancing, data replication modes, regional identities, application endpoint changes và thủ tục kiểm tra RPO. Không dùng cùng một RTO/RPO mặc định cho cả hai.

## 12. MongoDB: replica set, shard placement và config server

MongoDB có **replica sets** và, khi sharding, có **shards là replica sets**, **config servers** và **mongos routers** theo deployment model được hỗ trợ.

### 12.1. Replica set ba data-bearing members

Một topology minh họa:

~~~text
AZ A: mongod member A (voting, data-bearing)
AZ B: mongod member B (voting, data-bearing)
AZ C: mongod member C (voting, data-bearing)
~~~

Một replica set với ba voting members cần majority 2/3 để elect primary. Nếu mất một AZ, hai members còn lại có thể duy trì election quorum **khi đủ điều kiện bình chọn, dữ liệu/ưu tiên hợp lệ và kết nối còn hoạt động**.

### 12.2. Election quorum không bằng durable data quorum

MongoDB có **write concern**, journaling/durability và majority commit semantics. Nếu một member là **arbiter**, member ấy có thể vote nhưng **không lưu data copy**. Một mô hình `primary + secondary + arbiter` không tương đương ba full data replicas khi một data-bearing member mất.

Để đáp ứng yêu cầu writes acknowledged dưới một durability contract, cần xét **số data-bearing members sẵn sàng nhận/ack writes**, không chỉ số voters.

### 12.3. Secondary read preference

Nếu Java client đọc from secondary, vị trí replica ảnh hưởng:

- RTT/locality.
- Replication freshness.
- Eligibility sau election/recovery.
- Read concern và session semantics.

Một secondary ở AZ gần app có thể trả reads nhanh nhưng **lag**; topology phải đi cùng read policy và metrics.

### 12.4. Sharded MongoDB: placement theo từng shard

~~~text
MongoDB sharded cluster:
  Shard S1 replica set: A, B, C
  Shard S2 replica set: B, C, A
  Shard S3 replica set: C, A, B

  Config server replica set: A, B, C
  mongos routers:           A, B, C
~~~

Nếu data shards đã spread nhưng **config server replica set** chỉ ở AZ A, topology vẫn có một failure-domain weakness. Routers cũng phải có service discovery/load balancing và placement đủ đáp ứng sau AZ failure.

### 12.5. Zone sharding không đồng nhất replica-AZ placement

MongoDB sharding có khái niệm **zones** để gán data ranges/shards theo yêu cầu placement. Không tự đồng nhất “MongoDB zone” với “cloud Availability Zone”: một là quy tắc placement/shard tagging, một là hạ tầng lỗi. Cần đối chiếu physical location của từng shard replica set member và config server member.

### 12.6. Priority/hidden/delayed members

Một số replica set members có thể có election priority thấp/zero, hidden hoặc delayed theo config. Không tính một member “còn sống” như **ứng viên primary** nếu nó không được phép elect; delayed members cũng có role về recovery khác với synchronous serving replicas.

### 12.7. Khi một AZ mất

Kiểm tra:

1. Primary có nằm trong AZ mất?
2. Remaining voting majority?
3. Remaining data-bearing members thỏa write concern?
4. Config server majority và router availability?
5. Java driver discovery/reselect primary?
6. Secondary reads có route sang member chưa caught up?
7. Disk/network capacity còn đủ cho query và replication?
8. Khi AZ trở lại, resync/rollback cần bao nhiêu I/O/time?

### 12.8. Không giả định “primary down = toàn bộ cluster down”

Nếu majority và eligible secondary vẫn còn, election có thể tạo primary mới. Nhưng trong một khoảng failover có **transient read/write errors/timeouts**; API phải có timeout, retry có giới hạn và idempotency/unknown outcome handling cho writes.

## 13. Cassandra/ScyllaDB: replication theo datacenter/rack/token range

Cassandra/ScyllaDB dùng **peer-to-peer/token-range replication** với topology và consistency levels riêng, không có một leader duy nhất cho toàn cluster như một replica set đơn giản.

### 13.1. Data center và rack awareness

Một kiến trúc Cassandra thường mô tả:

~~~text
Datacenter DC1 (Cloud Region R):
  Rack/AZ A: N1, N2
  Rack/AZ B: N3, N4
  Rack/AZ C: N5, N6
~~~

Cloud-aware snitch/rack configuration được dùng để xác định DC/rack mapping mà replication strategy sử dụng. **Phải chắc nhãn rack tương ứng failure domain thật**, không gán mọi nodes vào cùng `rack1` dù VMs ở ba AZ.

### 13.2. NetworkTopologyStrategy và RF theo DC

Trong các versions hỗ trợ, ví dụ CQL khái niệm:

~~~cql
CREATE KEYSPACE orders
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'DC1': 3
};
~~~

RF=3 tại DC1 nghĩa mỗi token range/partition có ba replicas **trong DC1 theo strategy**, không có nghĩa cả cluster chỉ có ba nodes. Rack-aware placement hướng tới phân tán copies theo racks nếu topology đủ điều kiện.

### 13.3. Có ba racks nhưng mapping sai thì sao?

Nếu physical AZ A/B/C tồn tại nhưng cấu hình rack labels đều `rack1`, replication strategy không có thông tin đúng để ưu tiên cross-AZ placement. Đo/kiểm tra placements thực tế cho các token ranges để xác nhận fault isolation.

### 13.4. `LOCAL_QUORUM` cần hiểu RF theo DC

Với RF=3 trong một DC, `LOCAL_QUORUM` tương ứng majority local replicas cho operation trong DC theo contract. Khi mất một AZ chứa đúng một copy cho partition, hai local copies có thể còn, **nếu network/resources đủ**. Với RF per DC khác nhau, quorum count thay đổi.

### 13.5. Không tự đọc `QUORUM` là mạnh tuyệt đối

Quorum read/write intersection giúp nhiều guarantees nhưng còn timing, hinted handoff, repair, concurrent writes/timestamps và product semantics. Không biến “còn quorum” thành tuyên bố transactional linearizability cho mọi workload.

### 13.6. Coordinator routing trong Java

Java driver có thể chọn coordinator theo datacenter locality và token-aware policy, đồng thời các replicas chịu read/write consistency. Đặt application gần local DC thường giảm latency; **driver config phải dùng chính xác tên DC do cluster công bố**.

### 13.7. Seed nodes không phải master database

Seed nodes phục vụ discovery/gossip/bootstrap theo cơ chế engine; không tự là single leader hoặc authority cho reads/writes. Nhưng nếu tất cả seed endpoints đặt trong một AZ, **restart/scale/discovery khi AZ ấy mất** có thể khó dù existing cluster vẫn phục vụ. Phân bổ seed/discovery endpoints hợp lý.

### 13.8. Bootstrap/decommission và token movement

Thêm node hoặc thay rack/placement có thể cần stream large token ranges, tăng disk/network/compaction pressure. Khi scale, xem:

- Current token ownership.
- Expected replica placement.
- Data movement bytes.
- Network egress.
- Disk free space.
- Repair/cleanup requirements.
- Application consistency SLO.

Không thay rack/DC label tùy tiện trên node đã vận hành rồi tin rằng engine tự di chuyển toàn bộ replicas an toàn; dùng thủ tục topology migration của sản phẩm.

### 13.9. Multi-region Cassandra

Ví dụ replication per DC:

~~~cql
CREATE KEYSPACE orders_global
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'DC1': 3,
  'DC2': 3
};
~~~

`LOCAL_QUORUM` trong mỗi region có scope local RF, trong khi remote replication có latency và conflict semantics. Mô hình multi-DC có thể giúp locality/DR, nhưng **không tự là synchronous cross-region RPO=0** đối với mọi failure. Chọn CL theo operation contract.

### 13.10. Repair và topology

Replica availability ngắn hạn không đảm bảo data đã converge hoàn toàn sau outage dài. Cần repair/anti-entropy, TTL/tombstone retention policy và kiểm chứng consistency. Một AZ mất lâu hơn retention có thể đặt ra recovery procedure đặc biệt.

## 14. Redis: primary/replica, Sentinel và Redis Cluster

Redis deployments có nhiều mô hình **khác nhau**; đừng nói chung “Redis cluster ba nodes” nếu chưa phân biệt:

- Một primary và replicas, không có automated failover.
- Sentinel-assisted monitoring/failover.
- Redis Cluster sharding theo hash slots với primaries và replicas.
- Managed Redis-compatible service có topology/semantics riêng.

### 14.1. Redis primary và replica

~~~text
AZ A: primary P
AZ B: replica R1
AZ C: replica R2
~~~

Redis replication thông thường là **asynchronous**. Khi primary chết, replica promotion có thể xảy ra tùy HA mechanism, nhưng **acknowledged writes mới nhất có thể chưa tới replica được promote** theo failure window. Điều này quan trọng với RPO/business correctness.

### 14.2. Sentinel quorum

Redis Sentinel có monitoring/failover election/quorum semantics riêng. Một thiết kế với Sentinels trải ba AZ giúp giảm tương quan lỗi. Nhưng **Sentinel quorum không đồng nghĩa dữ liệu đã synchronous majority persisted**. Kiểm tra cả:

- Sentinel availability/votes.
- Primary/replica links.
- Replication offset/backlog.
- Promotion eligibility.
- Client failover discovery.

### 14.3. Redis Cluster và hash slots

Redis Cluster chia dữ liệu theo hash slots và các primary nodes sở hữu slot ranges; replicas của từng primary phải được đặt ở **AZ khác primary** nếu mục tiêu chịu AZ failure.

~~~text
AZ A: Primary P1, Replica of P2, Replica of P3
AZ B: Primary P2, Replica of P1, Replica of P3
AZ C: Primary P3, Replica of P1, Replica of P2
~~~

Đây là mô hình logical placement. Tùy memory capacity, có thể cần nhiều machines để tránh một host chứa quá nhiều processes và biến thành correlated failure domain.

### 14.4. Một replica cho mỗi primary chưa chắc chịu mất AZ

Nếu primary và replica của P1 đều ở AZ A, mất AZ A làm slot ranges của P1 không khả dụng dù những primaries khác vẫn chạy.

### 14.5. Redis Cluster failover và majority

Cluster failover có protocol/majority dựa trên master nodes và eligibility, nhưng **không đồng nhất với Raft majority của từng data shard**. Đọc chính xác phiên bản và cluster config; không áp công thức 2/3 per shard như máy móc.

### 14.6. `WAIT` và write safety

Redis có các cơ chế chờ replicas acknowledge offsets; điều đó có thể giảm nguy cơ replication delay nhưng **không chuyển toàn bộ Redis replication thành một distributed strongly-consistent transaction**. Với dữ liệu critical, cần thiết kế durability/idempotency/source-of-truth theo contract sản phẩm, không dùng Redis cache replication làm ledger duy nhất nếu không phù hợp.

### 14.7. Sizing RAM sau failover

Khi primary chết, replica có thể promote, và read/write traffic chuyển tới node mới. Nếu node vừa làm primary của một shard vừa giữ replicas khác, memory/cpu/network có thể quá tải. Placement cần tính **role capacity sau failover**, không chỉ bình thường.

### 14.8. Client discovery

Java Lettuce/Jedis/Sentinel/Cluster clients cần danh sách seeds/discovery endpoints phân tán. Không hard-code primary IP đã chết hoặc chỉ một Sentinel ở AZ A. Bảo đảm driver version/connection lifetimes/refresh topologies phù hợp.

## 15. Elasticsearch/OpenSearch: shard copies, awareness và cluster manager

Elasticsearch/OpenSearch chia indexes thành **primary shards và replica shards**, và có nhóm **master-eligible/cluster-manager-eligible nodes** (thuật ngữ tùy sản phẩm/version).

### 15.1. Data shard allocation

Một shard có primary + hai replicas:

~~~text
Shard S:
  primary in AZ A
  replica 1 in AZ B
  replica 2 in AZ C
~~~

Nếu mất một AZ, còn hai shard copies. Nhưng cluster cần **allocation/health**, remaining nodes đủ disk/CPU và cluster-manager quorum để xử lý node removal/relocation.

### 15.2. Allocation awareness

Các tính năng **shard allocation awareness/forced awareness** có thể dùng zone attributes để hướng dẫn đặt copies across failure domains theo engine. Cần hiểu:

- Node attribute phản ánh AZ thật.
- Rule phân bố primary/replicas.
- Behavior khi một AZ mất.
- Có tự đặt thêm replicas cùng AZ khác không.
- Disk watermarks và relocation limits.

Forced awareness có thể tránh dồn replicas vào failure domain còn lại khi AZ vắng mặt, đổi lại có thể giữ shards under-replicated/unassigned theo policy. Phải hiểu trade-off trước khi bật.

### 15.3. Control-plane/quorum nodes

Nếu cluster manager/voters chỉ ở AZ A, mất A có thể ngăn cluster tiến hành state updates dù data shard copies tồn tại ở B/C. Một thiết kế có eligible control-plane nodes trải ba AZ thường tránh failure-domain concentration.

### 15.4. Không nhầm shard replica với search cache

Hai shard copies không bảo đảm search query latest nếu indexing refresh chưa xảy ra. Topology và freshness cần metrics riêng:

- Shard health/assignment.
- Replication/recovery progress.
- Index refresh delay.
- Query latency/queue.
- Read routing/caches.

### 15.5. Disk watermark và recovery

Sau AZ loss, remaining nodes có thể chạm **disk watermarks**, ngăn relocation/replica allocation. Sizing dung lượng và temporary overhead quan trọng không kém số shards.

### 15.6. Shards quá nhỏ/quá nhiều

Một index có hàng nghìn shards rất nhỏ có thể tăng heap/metadata/coordinator overhead; quá ít shards lớn có thể kéo dài recovery/hotspot. Chọn shard sizing và replica count dựa trên workload, disk, recovery objectives và vendor constraints, không chọn chỉ để “mỗi AZ có một shard”.

### 15.7. Query availability sau mất AZ

Ngay cả khi còn primary/replica copy đủ để phục vụ, p99 có thể tăng do:

- Read QPS dồn lên ít copies.
- Search threadpool queue/rejections.
- Rebalancing/segment recovery.
- Cache cold.
- Cross-AZ data transfer.

Phải load test **degraded mode**, không chỉ thấy cluster state `yellow/green` rồi kết luận đạt SLO.

## 16. DynamoDB, Cosmos DB và managed NoSQL: topology được dịch vụ quản lý

Với **managed NoSQL services**, bạn thường **không điều khiển trực tiếp từng storage replica/pod/rack**. Nhà cung cấp có thể triển khai replication/placement trong một Region hoặc AZ theo service contract; ứng dụng vẫn phải thiết kế **region choice, partition key, request routing, quotas, durability, regional DR và multi-region consistency**.

### 16.1. DynamoDB trong một Region

Người dùng cấu hình table, capacity mode, partition key, indexes, APIs và consistency options; service quản lý nhiều hạ tầng bên dưới. Không cần tự tạo ba VMs trong ba AZ để làm replicas cho cùng một DynamoDB table.

Những thứ application/team vẫn quyết định:

- Region chứa table.
- Partition-key distribution/hot partition.
- Global Secondary Index design.
- Strong vs eventual read options theo API.
- SDK region endpoints và retry budget.
- Data backup/PITR và regional recovery needs.
- Multi-region Global Tables nếu phù hợp.

### 16.2. Global Tables không phải “AZ thứ tư”

Global Tables replicates giữa **Regions** theo mode/contract được sử dụng. Nó giải quyết cấp fault domain lớn hơn AZ, nhưng thêm:

- Replication lag hoặc consistency constraints.
- Region-specific routing.
- Concurrent write conflict semantics trong modes tương ứng.
- Egress/capacity cost.
- Global failover workflow.

Không tự suy mọi Global Table mode hỗ trợ cùng tính nhất quán hoặc RPO/RTO. Chọn theo nhu cầu và tài liệu của phiên bản dịch vụ đang triển khai.

### 16.3. Azure Cosmos DB for NoSQL

Cosmos DB cung cấp khái niệm **Regions, availability zones khi được hỗ trợ/cấu hình, consistency levels, partition keys và multi-region write/replication**. Cần kiểm tra:

- Account region configuration.
- Zone redundancy availability/setting ở Region.
- Single-region vs multi-region writes.
- Chế độ consistency và session tokens.
- Region failover priority/routing.
- RU/s và per-logical-partition hotness.

Nếu chỉ bật nhiều regions mà ứng dụng client vẫn hard-code một regional endpoint hoặc không có session/consistency handling, user-visible RTO/freshness có thể không đạt mục tiêu.

### 16.4. Cloud vendor guarantees có phạm vi

Một service có thể cam kết chịu lỗi AZ cho **data plane** nhưng outage ở control plane có thể ảnh hưởng operations quản trị. SLA/durability của backup cũng khác read/write availability. Khi viết architecture decision, trích rõ **product/mode/region/replication scope, RPO/RTO assumptions** thay vì suy từ marketing “multi-AZ”.

### 16.5. Managed DB không xóa hot partition

Ngay cả khi provider quản lý replicas tốt, một partition key nhận 90% writes vẫn có thể chạm giới hạn per-partition/throughput. Topology plan phải bao gồm **logical partition distribution**, không chỉ vật lý/region placement.

### 16.6. External dependencies

Managed NoSQL có thể dựa vào:

- IAM/service principals.
- VPC endpoints/private links.
- Encryption keys/KMS.
- DNS.
- Network egress/gateway.
- Quotas và organization policies.

Nếu tất cả application pods trải AZ nhưng traffic DB chỉ đi qua **một NAT gateway/endpoint** ở AZ A, hệ vẫn có correlated failure. Các thành phần bên ngoài DB cũng thuộc **fault-domain map**.

## 17. Kubernetes: scheduler không tự hiểu mục tiêu HA của database

Kubernetes có các khả năng quản lý pods/volumes/placement; nhưng **vị trí pods** có thể không đồng nghĩa **vị trí replica data** nếu operator không quản lý membership/replication đúng.

### 17.1. Node labels phải đúng

Ở Kubernetes hiện đại, các well-known topology labels thường gồm:

~~~text
topology.kubernetes.io/region
topology.kubernetes.io/zone
kubernetes.io/hostname
~~~

Phải kiểm tra cloud provider/node bootstrap điền đúng labels. Không lấy tên node/pod làm proxy cho AZ nếu nó có thể thay đổi.

### 17.2. Pod anti-affinity theo hostname

Một policy có thể tránh đặt hai database pods cùng một Kubernetes node:

~~~yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: nosql-db
        topologyKey: kubernetes.io/hostname
~~~

Đây là **một đoạn PodSpec minh họa**. Với cùng `app=nosql-db`, rule này có thể trải mọi pods nhóm, nhưng **không tự biết các pods là replicas của cùng shard hay khác shard**. Chọn labels/selectors theo operator/data-placement goals để tránh over-constraining cluster.

### 17.3. Anti-affinity theo AZ

Nếu có đúng ba pods cần một pod mỗi AZ:

~~~yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: orders-metadata-voter
        topologyKey: topology.kubernetes.io/zone
~~~

Với đủ ba AZ và matching pods, rule có thể buộc mỗi voter ở AZ khác. **Nếu chỉ có hai AZ hoặc thiếu capacity, pod thứ ba sẽ Pending**, điều này có thể là lựa chọn đúng để không vi phạm fault-domain guarantee, nhưng cần kế hoạch capacity và rollout.

### 17.4. Topology spread constraints

Ví dụ giảm lệch phân bố một nhóm pods:

~~~yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: orders-db
~~~

`maxSkew: 1` giúp điều phối pod counts theo eligible topology domains theo semantics của scheduler/version. Nhưng nó **không bảo đảm hai replicas của từng partition nằm ở AZ khác nhau** khi database operator có nhiều logical shard groups. Database replication placement phải được điều phối ở cấp engine.

### 17.5. `ScheduleAnyway` vs `DoNotSchedule`

- `DoNotSchedule`: Giữ constraint, pod có thể Pending nếu không thể đặt hợp lệ.
- `ScheduleAnyway`: Cố gắng cân bằng nhưng có thể vẫn đặt lệch vì ưu tiên scheduling khác.

Nếu SLO đòi chắc chắn tách voters across AZ, một soft preference có thể không đủ. Nếu AZ lỗi kéo dài, một hard constraint có thể ngăn khởi động replacement; cần runbook cho điều kiện bất khả thi và quyết định điều nào quan trọng hơn.

### 17.6. StatefulSet và stable identity

StatefulSet cung cấp danh tính pod/volume ổn định để chạy stateful applications. Nhưng:

- Pod name ổn định không đảm bảo placement vẫn ở AZ thích hợp.
- Chạy StatefulSet không tự tạo data replication.
- Rolling update order không thay DB membership/drain rules.
- PVC có thể bị bind vào zone và không di chuyển được.

Một database operator hiểu engine topology/membership có thể cần thiết hơn một StatefulSet tự viết đơn giản.

### 17.7. Persistent Volumes và topology

Nhiều block volumes được provision theo AZ. Nếu volume ở AZ A, pod gắn volume ấy **không thể đơn giản reschedule sang AZ B** khi A mất, trừ storage hỗ trợ di chuyển/cross-zone attach theo contract.

Điều này là điểm cốt lõi: **tính bền nằm trong replicated data copies across zones**, không phải kỳ vọng Kubernetes sẽ di chuyển một AZ-local disk sang AZ khác khi toàn AZ hỏng.

### 17.8. `WaitForFirstConsumer`

Với một StorageClass thích hợp, `volumeBindingMode: WaitForFirstConsumer` có thể giúp volume được provision phù hợp placement của pod, giảm nguy cơ bind volume vào zone trước khi scheduler quyết định. Không tự sửa StorageClass production mà chưa hiểu CSI driver, reclaim policy và storage topology.

Ví dụ minh họa:

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: zone-aware-storage-example
provisioner: example.csi.driver
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Retain
allowVolumeExpansion: true
~~~

`example.csi.driver` là placeholder, không phải một provisioner chạy được. `Retain`/expansion policies cần được quyết định theo data lifecycle và vận hành riêng.

### 17.9. PodDisruptionBudget không ngăn AZ outage

PodDisruptionBudget (PDB) điều tiết **voluntary disruptions** đi qua Eviction API theo policy, ví dụ drain/upgrade. Nó **không ngăn involuntary failures** như node crash/AZ outage và không bảo đảm replication quorum sau disaster.

Một PDB ví dụ:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-voters-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-metadata-voter
~~~

Chỉ đúng nếu nhóm có ba pods và cần giữ hai eligible members **theo semantics mà Kubernetes có thể quan sát**. PDB không biết node còn data latest, replica đã caught up hay đã bầu được leader. Không tự dùng PDB thay database-specific safe drain.

### 17.10. Hard constraints và deadlock rollout

Giả sử có ba database pods, ba AZ, hard zone anti-affinity, một pod đã mất vì AZ A outage. Nếu scheduler vẫn đòi replacement ở AZ khác pod còn sống, pod mới có thể không lên được vì AZ A không khả dụng. **Không tự gỡ affinity để cưỡng ép copy cùng AZ** nếu không đánh giá rủi ro mất failure-domain diversity và write safety.

### 17.11. Rolling deployments không đồng nghĩa database rolling upgrades

Application Deployment có thể rolling upgrade bằng `maxUnavailable`, nhưng database may require:

- Step-down leader trước restart.
- Drain connections.
- Wait for replica catch-up.
- Quorum and cluster-manager health checks.
- Version compatibility/upgrade path.
- One member at a time.
- Fencing against stale leader.

Một `kubectl rollout restart statefulset` không tự chứng minh mọi bước đó được thực hiện an toàn.

### 17.12. Node autoscaling và placement drift

Cluster Autoscaler/node pool changes có thể tạo những nodes mới không ở AZ đã định, hoặc làm pod không reschedule vì PVC pinned. Cần kiểm tra:

- Node groups trải nhiều AZ.
- Minimum capacity per AZ.
- Node taints/tolerations đúng.
- StorageClass zone affinity.
- Pod topology constraints.
- Operator replica placement after reschedule.
- Quorum/availability trong lúc scale down.

## 18. Kubernetes: ví dụ manifest minh họa cho metadata voters

Giả sử có một nhóm **ba metadata-voter pods** trên ba AZ và operator biết khởi tạo membership. Một phần PodSpec (không phải full Kubernetes manifest):

~~~yaml
metadata:
  labels:
    app: orders-metadata-voter
spec:
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - labelSelector:
            matchLabels:
              app: orders-metadata-voter
          topologyKey: topology.kubernetes.io/zone
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: DoNotSchedule
      labelSelector:
        matchLabels:
          app: orders-metadata-voter
  terminationGracePeriodSeconds: 120
  containers:
    - name: voter
      image: "example/metadata-voter:documented-version"
      ports:
        - containerPort: 7000
~~~

Các trường `image`, role, port và `terminationGracePeriodSeconds` chỉ minh họa; không thể triển khai một metadata quorum chỉ với manifest này. Cần service/operator lifecycle, membership/bootstrap, health/readiness và storage semantics của **sản phẩm cụ thể**.

### 18.1. Vì sao không copy nguyên ví dụ vào production?

- Thiếu volume claims, Service, securityContext, probes, resource requests/limits, TLS, secrets.
- Mỗi NoSQL engine cần metadata membership/consensus configuration riêng.
- `requiredDuringSchedulingIgnoredDuringExecution` **không liên tục evict** pods đã chạy nếu topology labels thay đổi sau scheduling.
- Nếu tất cả nodes trong một AZ, hard constraints tạo Pending chứ không sinh thêm AZ.
- Pod health không đồng nghĩa replica synced/eligible.

### 18.2. Database operator nên làm gì?

Một operator phù hợp nên:

1. Hiểu replica group/shard/role.
2. Áp placement theo failure domains thật.
3. Kiểm tra quorum/eligibility trước rolling actions.
4. Quản lý bootstrap, promote, replica replacement.
5. Theo dõi PVC/volume identities.
6. Không xóa thành viên cuối của một quorum group.
7. Tái cân bằng khi nodes/AZ hồi phục.
8. Phát health/metrics đủ để thấy placement drift.

### 18.3. Kubernetes scheduler và database planner cần phối hợp

Scheduler chỉ biết pods/nodes/labels/resources. Database planner biết **những pods chứa cùng shard và những pods có thể thay thế nhau**. Nếu hai tầng có chính sách không khớp, cluster có thể có pods hợp lệ về scheduler nhưng replication placement sai hoặc ngược lại.

## 19. Placement constraints trong bare metal/VM

Không dùng Kubernetes vẫn cần cùng nguyên lý:

~~~yaml
nodes:
  - id: db-01
    region: r1
    zone: a
    rack: rack-a1
    powerDomain: pdu-a1
    storageDomain: local-nvme-a1
  - id: db-02
    region: r1
    zone: b
    rack: rack-b1
    powerDomain: pdu-b1
    storageDomain: local-nvme-b1
  - id: db-03
    region: r1
    zone: c
    rack: rack-c1
    powerDomain: pdu-c1
    storageDomain: local-nvme-c1
~~~

Đây là **inventory model**. Các node labels phải được điền từ hạ tầng thật, không dựa vào tên máy nếu host được di chuyển.

### 19.1. On-prem rack awareness

Nếu datacenter chỉ có hai racks nhưng một replication group cần ba failure domains độc lập ở cấp rack, **không thể đạt mục tiêu chỉ bằng config**. Cần bổ sung hạ tầng hoặc thay failure model/SLO, không dán một nhãn “rack-C” giả lên node trong rack-A.

### 19.2. Storage controller là failure domain độc lập

Ba VMs có thể trên ba hypervisors nhưng tất cả disks nằm trên cùng SAN. Mất SAN controller vẫn khiến cả ba replicas unavailable. Đánh giá **physical storage dependencies** chứ không chỉ compute.

### 19.3. Shared load balancer/NAT/DNS

Nếu database endpoints chỉ được truy cập qua một load balancer instance hoặc một NAT gateway có single-AZ affinity, sự cố đúng ở gateway có thể làm cả cluster không reachable với client. Một topology diagram hoàn chỉnh phải đánh dấu **network ingress/egress và discovery control points**.

## 20. Java client topology awareness và failover

Ngay cả khi database topology tốt, ứng dụng Java vẫn có thể là **điểm lỗi đơn** nếu connection/discovery/region routing sai.

### 20.1. Seed list không đồng nghĩa danh sách mọi server mãi mãi

Nhiều NoSQL drivers khám phá cluster topology từ một tập seed/contact points. Nhưng:

- Nếu **mọi seeds nằm trong một AZ**, service mới restart trong lúc AZ chết có thể không bootstrap được kết nối.
- Driver có thể lưu topology cache; failover cần refresh/discovery.
- DNS/proxy có thể không phản ánh trực tiếp state/roles ở DB.
- Một node có thể còn TCP open nhưng không còn **leader/eligible**.

Phân bổ discovery endpoints và kiểm tra **start from cold** khi mất AZ, không chỉ kiểm tra app đã kết nối trước outage.

### 20.2. Một cấu trúc cấu hình Java logic

~~~yaml
nosql:
  topology:
    region: "region-r1"
    preferredDatacenter: "dc-r1"
    discoveryEndpoints:
      - "db-a.example.internal:9042"
      - "db-b.example.internal:9042"
      - "db-c.example.internal:9042"
  client:
    operationDeadlineMs: 800
    connectTimeoutMs: 1000
    maxRetryAttempts: 2
    retryJitter: true
  routing:
    preferLocalDatacenter: true
    requireEligibleReplica: true
~~~

Đây là **mô hình cấu hình minh họa**, không phải YAML có thể nạp chung cho MongoDB/Cassandra/Redis. Port 9042 chỉ minh họa kiểu CQL; sản phẩm khác dùng ports và SDK settings khác.

### 20.3. MongoDB Java driver

Một connection string có thể cung cấp multiple hosts và replica set identity cho topology discovery:

~~~text
mongodb://db-a.example:27017,db-b.example:27017,db-c.example:27017/orders?replicaSet=orders-rs
~~~

Cần cấu hình TLS, credentials, timeout, retry, readPreference và read/write concerns đúng deployment. **Không giả định chỉ liệt kê ba hosts sẽ ép database đặt ba members ở ba AZ**; đó là việc của server/infra placement.

### 20.4. Cassandra Java driver

Một `CqlSession` thường có thể bootstrap từ contact points và local datacenter metadata. Tên datacenter phải trùng với cluster topology; driver có policy lựa chọn coordinator/replica phù hợp. Tránh tạo một session per request, vì mỗi session có topology discovery, pools và overhead.

### 20.5. Redis Java clients

Redis Sentinel/Cluster clients thường có cơ chế discovery khác một standalone Redis client. Nếu chỉ tạo client kết nối cứng tới primary P1, khi P1 failover sang replica P2, application có thể mất kết nối mãi cho tới khi restart/manual config. Dùng đúng Sentinel/Cluster mode và kiểm tra refresh topology.

### 20.6. Timeouts và retries cần một ngân sách

Trong failover, có thể xảy ra:

~~~text
old leader becomes unavailable
  -> connection error / timeout
  -> discovery/election
  -> client retries
  -> new leader receives request
~~~

Nếu gateway, service và SDK **đều retry nhiều lần**, một outage có thể nhân tải lên remaining nodes. Cần:

- Shared overall request deadline.
- Bounded retry attempts.
- Exponential backoff + jitter khi phù hợp.
- Circuit breaker/load shedding.
- Per-operation idempotency/unknown outcome semantics cho writes.
- Observability phân biệt logical requests và attempts.

### 20.7. Unknown write outcome

Java client nhận socket timeout sau khi gửi write:

~~~text
Client sent reserveInventory(requestId=R42).
Leader committed the write.
Connection reset before ACK reaches client.
~~~

**Timeout không chứng minh write thất bại.** Retry với một request ID khác có thể double-reserve. Failover-safe ứng dụng cần idempotency key, conditional mutation hoặc transaction/outcome lookup theo domain.

### 20.8. Cold-start test

Một test bắt buộc:

1. Giả lập AZ A bị mất trong môi trường test.
2. **Khởi động mới một Java pod** ở AZ B.
3. Driver discovery từ seeds còn sống.
4. Khởi tạo connection pools.
5. Đọc/ghi theo consistency yêu cầu.
6. Xác nhận không hard-code host/region đã chết.

Chỉ chạy một Java process đã có warm connections trước khi AZ mất sẽ không phát hiện nhiều lỗi discovery/credential/DNS.

### 20.9. Driver locality không đồng nghĩa replica safety

Chọn “nearest replica” giảm RTT, nhưng nearest có thể đang apply lag hoặc recovering. Read preference phải phối hợp **consistency, replica eligibility và session context** để tránh stale reads nếu business không chấp nhận.

## 21. Phân bổ ứng dụng cùng topology DB

Nếu database trải A/B/C nhưng toàn bộ Java API pods ở A, mất A làm toàn dịch vụ ngừng dù DB còn quorum. Cần một fault-domain map gồm **app, ingress, cache, message broker, DB, control plane và backup**.

### 21.1. Cấu trúc ví dụ

~~~mermaid
flowchart TB
    CLIENT["Clients"] --> LB["Regional load-balancing / ingress"]
    subgraph ZA["AZ A"]
      AA["Java API pods A"]
      DA["NoSQL replicas A"]
    end
    subgraph ZB["AZ B"]
      AB["Java API pods B"]
      DB["NoSQL replicas B"]
    end
    subgraph ZC["AZ C"]
      AC["Java API pods C"]
      DC["NoSQL replicas C"]
    end
    LB --> AA
    LB --> AB
    LB --> AC
    AA --> DA
    AB --> DB
    AC --> DC
    DA <--> DB
    DB <--> DC
    DA <--> DC
~~~

Ingress, DNS và credentials cũng cần phân bố/resilience đúng contract; sơ đồ không thể hiện mọi dependencies.

### 21.2. API autoscaling tăng total DB connections

Giả sử:

~~~text
10 Java pods bình thường
30 Java pods trong rollout/autoscale
maxPoolConnections = 50 per pod
~~~

Upper bound cơ học từ một pool mỗi pod:

\[
30\times50=1500\text{ connections}
\]

Nhưng nếu SDK tạo **pool per server** hoặc nhiều HTTP transports, tổng có thể khác. Sau AZ failure, số pods còn lại có thể tăng và số in-flight DB operations tăng, khiến nodes còn sống chịu thêm áp lực.

### 21.3. Global budget

Cần tính:

~~~text
Max pods during rollout × per-pod connection pools
  + batch/CDC/backup clients
  + admin/monitoring
  + leader/replica internal communication
  <= verified connection/resource budgets by endpoint
~~~

Đây là **mối quan hệ cần kiểm tra**, không phải một phép cộng connections chính xác cho mọi driver/protocol. Connection count không phải measure duy nhất; phải xét DB in-flight operations, CPU/IO/partition caps.

### 21.4. Cache layer có cùng fault domain không?

Nếu API pods ở A/B/C nhưng distributed cache chỉ ở A, loss A có thể gây:

- Cache outage.
- Database cache stampede.
- Spike in reads trên remaining DB nodes.
- Latency vượt SLO dù DB quorum còn.

Cần thiết kế **cache fail-open/fail-closed theo nghiệp vụ**, rate limits và cache warm-up để không tạo sự cố thứ cấp.

## 22. Phân tích sự cố đơn và sự cố tương quan

| Failure scenario | Tác động kỳ vọng nếu topology đúng | Điều cần kiểm chứng |
| --- | --- | --- |
| Một data process crash | Một replica copy unavailable, cluster tiếp tục | Auto restart, quorum, replica eligibility |
| Một host chết | Các pods/replicas trên host mất | Không mất đủ copies cùng shard |
| Một rack/power domain chết | Nhiều hosts cùng mất | Rack awareness, shared storage |
| Một AZ mất | Mất toàn bộ nodes AZ ấy | Quorum, capacity N+AZ, app ingress |
| Một region mất | Regional data/compute/control plane unavailable | DR mode, RPO/RTO, fencing |
| Inter-AZ network partition | Một phần nodes bị cách ly | Safety, election/term, write refusal |
| WAN partition multi-region | Regions có thể không liên lạc | Authority/conflict resolution |
| Bad schema migration | Replicas đều áp thay đổi sai | Backups, staged rollout |
| Delete nhầm dataset | Replication nhân delete | PITR/backup recovery |
| Stolen credentials | Writes/deletes có thể tác động mọi replicas | IAM isolation, audit, immutable backups |
| Voluntary node drain | Pod eviction/restart | PDB, db-aware drain, quorum |
| Disk full trên một node | Replica slow/unavailable | Free-space/compaction headroom |
| Connection/DNS failure | Clients không tìm được nodes khỏe | Multiple seeds/endpoint resiliency |
| Hot partition | Một subset shard saturated | Partition placement, key design |
| Driver retry storm | Remaining nodes overloaded | Admission, deadlines, idempotency |

### 22.1. Fault model phải nêu những gì không chịu được

Ví dụ cluster RF3 ở ba AZ có thể tuyên bố “chịu mất một AZ trong khi cluster và mạng còn lại khỏe”, nhưng **không** có nghĩa nó chịu được:

- Hai AZ mất đồng thời.
- Một AZ + một voter khác mất đúng lúc.
- Region-wide network outage.
- Corruption được replica qua cả ba copies.
- KMS credential bị thu hồi đồng loạt.
- Storage full ở remaining nodes.

Một architecture decision tốt nêu **assumptions và giới hạn**, không chỉ “HA=yes”.

## 23. Thực hành placement audit trước khi deploy

Một deployment plan nên được kiểm tra ở hai lớp:

**Lớp hạ tầng:** Những nodes ở đâu, phụ thuộc power/network/storage nào?

**Lớp database:** Những partition replicas/leader/voter roles nào thực sự nằm trên các nodes ấy?

### 23.1. Inventory mẫu

~~~yaml
cluster: orders-nosql-r1
region: r1
nodes:
  - id: A1
    az: a
    rack: rack-a1
    roles: [data, voter]
  - id: B1
    az: b
    rack: rack-b1
    roles: [data, voter]
  - id: C1
    az: c
    rack: rack-c1
    roles: [data, voter]
replicationGroups:
  - id: order-shard-01
    replicationFactor: 3
    members: [A1, B1, C1]
  - id: metadata
    votingMembers: [A1, B1, C1]
~~~

Đây là data structure tự xây để audit, không phải config vận hành được của database engine.

### 23.2. Điều kiện đơn giản kiểm tra AZ spread

Với mỗi replication group cần chịu mất một AZ và không có nguồn khôi phục tức thời:

~~~text
For every group G:
    collect all data-bearing members of G
    map each member to its actual AZ
    verify enough copies remain under loss of each AZ
    verify the remaining copies satisfy operation quorum

For metadata/voter groups:
    verify election/management quorum under each AZ failure
~~~

Không chỉ kiểm tra `distinctAZCount >= 3` rồi kết luận đủ. Ví dụ RF5 phân bố 3–1–1 có ba AZ nhưng mất AZ chứa ba copies chỉ còn hai, có thể không đạt majority data quorum 3/5.

### 23.3. Placement drift

Sau 6 tháng, vì sự cố node/rebalancing/scheduler, replicas có thể bị đặt lệch:

~~~text
Initial S1: A, B, C
After incident recovery S1: B1, B2, C
~~~

Nếu “B1, B2” cùng AZ B, mất B khiến S1 chỉ còn C. Cần **periodic placement audit**, alert cho under-replication và policy repair.

### 23.4. Data and voter roles need separate reports

Một audit report nên liệt kê:

- Logical data replicas by shard/range.
- Voting/control-plane members.
- Source/leader ownership by AZ.
- Healthy/eligible state.
- Storage volume AZ and disk free space.
- Read/write traffic by AZ.
- Connection endpoints/seed distribution.

### 23.5. Negative testing: giả lập mất từng AZ

Chạy mô phỏng trên inventory:

~~~text
Remove all nodes in AZ A -> enough copies/voters/capacity?
Remove all nodes in AZ B -> enough copies/voters/capacity?
Remove all nodes in AZ C -> enough copies/voters/capacity?
~~~

Sau đó đo lỗi thật bằng một thí nghiệm staging an toàn, vì phép mô phỏng **không dự đoán chính xác election duration, network behavior hoặc storage load**.

## 24. Quy trình bảo trì và thay đổi topology

Một topology đúng trên sơ đồ vẫn có thể mất quorum vì **hai thao tác vận hành trùng nhau**: một node đang được upgrade, node khác bất ngờ crash, hoặc operator cùng lúc di chuyển replicas ở hai AZ.

### 24.1. Nguyên tắc một lần thay đổi có kiểm soát

Trước một thay đổi trên data/voter node:

1. Kiểm tra cluster health và no ongoing degraded replica groups.
2. Xác nhận voters/data copies còn đủ khi node dự kiến tạm rời cụm.
3. Dừng hoặc hạn chế background rebalance/backup khi cần.
4. Drain traffic/step-down leadership theo product-specific procedure.
5. Gỡ một node khỏi serving path hoặc thực hiện rolling upgrade.
6. Đợi node restart, rejoin và **catch up tới mốc hợp lệ**.
7. Kiểm tra data/metadata quorum, read/write SLO và replica placement.
8. Chỉ sau đó mới tác động node tiếp theo.

Không áp điều kiện “mỗi lần một node” một cách mù với tất cả sản phẩm: một số rolling operations cần coordinated transition và những replica groups khác nhau có thể được nâng cấp song song **nếu engine chứng minh an toàn**.

### 24.2. Bảo trì theo failure domain

Đừng vô tình upgrade **tất cả nodes ở AZ A**, rồi tiếp tục upgrade B khi A vẫn chưa phục hồi. Quy tắc thực hành:

~~~text
Before touching any node:
  evaluate remaining quorum under planned removal
  evaluate unplanned extra node/AZ failure margin
  verify recovery/catch-up from previous step
~~~

Nếu hệ đang mất một AZ và chỉ còn majority sát ngưỡng, có thể cần **đóng băng bảo trì** cho tới khi redundancy được khôi phục.

### 24.3. Application rollout cũng ảnh hưởng database

Rollout từ 10 lên 20 Java pods có thể gây:

- Connection creation burst.
- TLS/auth load.
- Topology discovery requests.
- Retry storms nếu endpoints thay đổi.
- Cache cold miss burst.

Thời điểm database đang re-replicating sau node loss, application rollout có thể làm quorum còn lại quá tải. Lập lịch/limit cả **app và DB**.

### 24.4. Scale up: thêm node không tự tăng capacity ngay

Một node mới có thể:

1. Join membership.
2. Nhận token/partition assignments.
3. Stream/restore data.
4. Build indexes.
5. Catch up change log.
6. Trở thành healthy/eligible.
7. Nhận read/write routing.

Trong lúc này, nó có thể **tiêu tốn tài nguyên** của nodes hiện tại hơn là tăng useful capacity ngay lập tức.

### 24.5. Scale down: decommission trước khi xóa VM

Không xóa VM/pod đang giữ shard cuối hoặc majority member chỉ vì CPU thấp. Quy trình thường cần **decommission/drain/relocate data** rồi verify replicas/votes; API/CLI chính xác phụ thuộc engine.

### 24.6. Replace failed node vs move volume

Khi AZ A chết, không thể trông chờ volume AZ-local của node A được attach ở B nếu CSI/cloud contract không hỗ trợ. Có thể tạo **node mới và rebuild replica từ surviving copies** theo engine, cần capacity/bandwidth/free space đủ và chính sách bảo toàn failure domains.

### 24.7. Stop/start cluster theo trật tự

Tắt toàn cluster rồi khởi động lại có thể có semantics khác rolling restart: leader election, snapshots, WAL recovery, bootstrap seeds và quorum. Dùng runbook/automation theo vendor; không coi tất cả nodes có thể restart đồng loạt mà không downtime.

## 25. Recovery capacity và thời gian tái tạo bản sao

Một cluster cần không chỉ chịu lỗi mà còn **phục hồi redundancy trước khi sự cố tiếp theo xảy ra**.

### 25.1. Ước tính thời gian truyền dữ liệu

Giả sử cần rebuild một replica 8 TiB, effective sustained copy throughput 250 MiB/s:

\[
T_{\mathrm{copy}}
\approx \frac{8\times1024\times1024\ \mathrm{MiB}}
{250\ \mathrm{MiB/s}}
\approx33\,554\text{ s}\approx9{,}32\text{ giờ}
\]

Đây là lower-bound thô theo transfer bytes/throughput, **chưa tính compaction, index building, throttling, catch-up writes, consistency checks, retry hoặc storage read contention**. Recovery thật có thể lâu hơn nhiều.

### 25.2. Tại sao rebuild có thể làm RTO/SLO xấu hơn?

Khi một node chết:

- Các nodes còn lại gánh read/write workload.
- Đồng thời chúng phải **stream dữ liệu cho node mới**.
- Disk/network/cache cùng chịu tải.
- p99 tăng dù số nodes chưa còn ít hơn sau khi replacement đã join.

Tăng tốc rebuild tối đa không phải lúc nào cũng tốt; có thể làm **critical user traffic timeout**. Cần recovery bandwidth budget.

### 25.3. Catch-up sau copy

Nếu snapshot/rebuild mất 9 giờ nhưng source tiếp tục ghi, new replica phải replay những changes trong giai đoạn copy. Log retention/backlog buffer cần đủ, hoặc reinitialization/rebuild có thể lặp lại.

### 25.4. Workload có hot partitions

Một shard 10 TiB có thể mất nhiều giờ rebuild; những shards khác nhỏ. Recovery time nên đo theo **largest shard/replica group và slowest critical path**, không lấy trung bình data per node.

### 25.5. Giới hạn network inter-AZ

Truyền 8 TiB qua link hiệu dụng 1 Gbit/s sẽ mất lâu hơn nhiều so với 250 MiB/s. Nếu cloud charges/egress quota/instance bandwidth giới hạn, hiệu quả thực cần benchmark. Tính cùng lúc replication traffic bình thường và backup/rebalance.

### 25.6. Capacity trong lúc AZ vẫn chết

Nếu RF3 trải ba AZ và một AZ mất, không thể khôi phục ba distinct AZ copies trong chỉ hai AZ sống. Một giải pháp chấp nhận **temporarily under-replicated** với monitoring và no-further-failure assumption; một giải pháp khác có fourth AZ/region theo thiết kế. Quyết định phải gắn với business risk, durability và storage cost.

### 25.7. Backup/PITR bổ sung cho replication

Nếu tất cả replicas cùng áp logical delete sai, re-replication chỉ tái tạo **trạng thái sai**. Đường phục hồi cần:

- Backups có retention hợp lệ.
- Recovery test định kỳ.
- Object storage/backup account isolation.
- Point-in-time restore khi sản phẩm hỗ trợ.
- RPO/RTO đối với accidental deletion/corruption.

**Replication chịu lỗi hạ tầng; backup giải quyết nhiều tình huống mất dữ liệu logic.**

## 26. Các SLO vận hành phải kiểm tra sau mất miền lỗi

Một topology không nên chỉ được chấp nhận vì mọi containers `Ready=true`. Đặt SLO cụ thể:

~~~yaml
availability:
  criticalWriteSuccessRateDuringSingleAzLoss: ">=99.9%"
  criticalReadSuccessRateDuringSingleAzLoss: ">=99.9%"
  maxUserVisibleFailoverSeconds: 30

latency:
  criticalReadP99MsAfterStabilization: 250
  criticalWriteP99MsAfterStabilization: 500

durability:
  acknowledgedCriticalWriteLoss: "none under documented single-AZ failure model"

capacity:
  maxNodeCpuAfterAzLossPercent: 75
  maxDiskUtilAfterAzLossPercent: 80
  requiredStorageFreeForRecoveryGiB: 500
~~~

Các ngưỡng trên là **ví dụ business objectives**, không phải khuyến nghị chung hoặc một file vendor config chạy được. Chỉ có thể cam kết “no loss” khi durability protocol và failure model thật được chứng minh.

### 26.1. Failover interruption và steady-state degraded SLO

Phân biệt:

- **Impact window:** Khoảng election/reconnect có thể có errors/timeouts.
- **Degraded steady state:** Cluster đã ổn định nhưng còn ít capacity.
- **Recovery window:** Rebuild/rebalance trong lúc vẫn phục vụ.

Một hệ có 10 giây failover và 3 giờ p99 vượt SLO trong rebuild có thể **không đáp ứng mục tiêu kinh doanh**, dù RTO “lên lại” chỉ 10 giây.

### 26.2. Read-only degradation

Nếu còn read availability nhưng write quorum mất, có thể trình bày mode rõ ràng:

~~~text
criticalWriteStatus: UNAVAILABLE_DUE_TO_QUORUM
readStatus: AVAILABLE_WITH_CONSISTENCY_LIMITS
~~~

Không tự ACK writes vào local buffer không bền rồi coi đó là committed order/payment.

### 26.3. Replica eligibility

Sau AZ phục hồi, node có thể:

- Alive/reachable.
- Nhưng còn resync/initial sync.
- Chưa eligible để serve reads.
- Chưa eligible để vote/be primary.
- Chưa bắt kịp log.

Chỉ mark recovery complete khi kiểm tra **data/metadata readiness theo engine**, không chỉ TCP health check.

### 26.4. Failover drill có thể tiết lộ cấu hình sai

Ví dụ một database cluster có leader P trong A và followers ở B/C, nhưng Java API pods dùng **primary-only IP** thay vì replica-set discovery. Khi mất A, database elect new leader nhưng app vẫn lỗi. Đây là **end-to-end topology failure**, không phải DB quorum failure.

## 27. Một ma trận thử nghiệm lỗi

| Test trong môi trường được cấp quyền | Cái gì bị tắt/giới hạn | Kết quả phải kiểm chứng |
| --- | --- | --- |
| Process crash | Một data process | Restart, membership, no data corruption |
| Host outage | Một VM/node | Per-shard copies còn phục vụ |
| AZ A failure | Tất cả nodes/apps tại A | Quorum, API availability, SLO, reconnect |
| AZ B failure | Tất cả nodes/apps tại B | Tương tự; không chỉ test leader AZ |
| AZ C failure | Tất cả nodes/apps tại C | Tương tự |
| Leader loss | Leader node | Election/fencing, unknown write outcomes |
| Network partition | Chia voting group thành 1+2 | Minority writes refused, no split-brain |
| Slow disk | Một replica fsync/IO throttled | Apply lag, quorum p99, failover policy |
| Disk full | Một replica gần đầy | No unexpected data loss/compaction deadlock |
| Cold new node | Empty replacement node | Rebuild time, bandwidth, catch-up |
| Metadata voter loss | Một control-plane node | State changes/election still safe |
| Client cold-start | App process mới lúc AZ chết | Seed discovery/reconnect/credentials |
| PDB rolling eviction | Evict one node/pod | No quorum lost during planned changes |
| Autoscale burst | 10→30 app pods | DB connection/IO budgets không bị vượt |
| Region DR | Disable primary Region in lab | RPO/RTO/fencing/routing |
| Expired credentials/DNS | Một discovery dependency lỗi | Không thành single point of failure |
| Bad migration | Staged incompatible config | Rollback/restore plan |
| Restore from backup | Isolated restore environment | PITR/RTO và data integrity |

### 27.1. Assertions quan trọng

Trong mỗi thí nghiệm, ghi:

~~~text
Election/leader state and term/epoch
All data/voter groups still meeting required quorum?
Every shard/key range reachable?
Write outcome for all acknowledged operations?
Transient errors and timeouts during failover
HTTP p50/p95/p99 and success rate
DB read/write throughput after failure
Per-node CPU, memory, IOPS, disk free, network
Client reconnect / topology refresh
Recovery time and bytes transferred
Final replica placement across AZ
~~~

### 27.2. Don't conflate fault injection with outage creation

Không dùng các thao tác network partition/disk kill trên production trừ khi có quy trình được phê duyệt và giới hạn blast radius. Một staging cluster có data distribution và topology gần production sẽ giúp kiểm tra an toàn hơn.

### 27.3. Mất AZ khi cluster đang degraded

Nếu một replica đã offline để bảo trì, rồi AZ khác mất, hệ có thể mất quorum dù topology bình thường chịu được một AZ. Test **sequential failures** với trạng thái đang degraded để xác định chính sách freeze maintenance/alert.

### 27.4. Restored AZ không đồng nghĩa hết sự cố

Sau khi AZ trở lại:

- Một node có thể có stale term/data.
- Replicas cần resync.
- Shard placement có thể drift.
- Temporary double capacity/rebalance áp lực.
- Cache cold và app connection churn.

Cần một **recovery-complete gate** trước khi tiếp tục upgrades hoặc scale down.

## 28. Runbook khi một AZ của cụm NoSQL ngừng hoạt động

### Bước 1 — Xác nhận lỗi và blast radius

- AZ nào bị ảnh hưởng? Có lỗi region/shared network không?
- Những nodes/data/metadata votes nào mất?
- API pods/load balancer/seeds/KMS/DNS có bị ảnh hưởng?
- Có recently deployed change gây outage logic không?

Đừng mặc định “lỗi AZ” chỉ từ một node không phản hồi.

### Bước 2 — Bảo vệ safety

- Xác định term/leader/quorum state.
- Không ép hai primaries cùng nhận writes.
- Không override votes/quorum configuration tùy tiện.
- Dừng maintenance/decommission đang chạy.
- Giữ idempotency/outcome reconciliation cho writes timeout.

### Bước 3 — Xác định khả năng phục vụ

Kiểm tra read/write operations thực theo consistency contract:

~~~text
critical read path
critical write path
per-shard coverage
unknown write outcomes
application error and latency SLO
~~~

Nếu quorum mất, **trả trạng thái unavailable minh bạch** cho critical writes thay vì ghi local ở một nhánh chưa được phép.

### Bước 4 — Chuyển traffic an toàn

- Loại nodes unreachable/unready khỏi read/write routing.
- Dùng driver topology discovery và healthy endpoints.
- Kiểm tra app pods ở B/C còn capacity.
- Kiểm tra cache/ingress/gateway.
- Không gửi tất cả retries đồng thời vào remaining leader.

### Bước 5 — Bảo vệ degraded capacity

- Throttle background analytics/reindex/backups.
- Áp admission/bulkhead để không overload remaining nodes.
- Theo dõi hot shards/partitions, disk free, compaction, network.
- Chặn risky schema migrations/rollouts.

### Bước 6 — Phục hồi AZ/replacement nodes

Theo runbook sản phẩm:

1. Xác minh AZ/storage/links ổn định.
2. Rejoin/recreate members đúng identity/generation.
3. Resync/rebuild data safely.
4. Đợi catch-up và eligibility.
5. Kiểm tra placements trở lại theo failure domains.
6. Giảm rebalance/repair pressure theo SLO.

Không mang một stale node vào cluster như “leader cũ” nếu fencing/epoch rules chưa rõ.

### Bước 7 — Recovery complete

Đóng incident chỉ sau khi:

- Tất cả critical shard groups đạt redundancy kỳ vọng.
- Metadata/control plane healthy.
- No unexpected divergence/lost acknowledged writes.
- Application cold-start/read/write tests pass.
- Resource/latency metrics về mức an toàn.
- Backup/PITR và recovery plans còn hợp lệ.
- Không còn pending maintenance có thể làm mất quorum.

### Bước 8 — Postmortem

Ghi root cause, thời lượng, AZ and service impact, lỗi consistency/durability, RTO/RPO, số retries, recovery bandwidth/time, drift, những điều cần sửa ở placement/capacity/automation.

## 29. Bảng chống lỗi thường gặp khi thiết kế topology

| Anti-pattern | Vì sao nguy hiểm | Hướng khắc phục |
| --- | --- | --- |
| Ba replicas trong cùng AZ | Một sự cố AZ làm mất cả ba | Per-replica AZ spread |
| Ba pods trên ba hosts cùng rack | Rack switch/power lỗi chung | Rack/power awareness |
| Voters trải AZ nhưng data copies không | Election có thể sống, writes vẫn lỗi | Kiểm tra data quorum |
| Data shards khỏe nhưng metadata ở một AZ | Control-plane outage | Metadata quorum spread |
| Dùng 2-node majority group và tin chịu 1 node | Majority 2/2 | Quorum design phù hợp |
| Đặt quorum trong hai Regions mà không witness/fencing plan | WAN partition ambiguity | Product-supported DR/election |
| Một witness được tính như full replica | Không chứa data | Tách votes/data copies |
| RF=3 được coi tự chịu 1 AZ | Placement có thể cùng zone | Kiểm tra per-group placements |
| Chỉ kiểm CPU bình thường | Degraded mode quá tải | N+AZ capacity testing |
| Auto-reschedule stateful pod qua AZ | PVC AZ-local không attach được | Replicated data/operator-aware restore |
| `PodDisruptionBudget` xem như bảo vệ mất AZ | PDB chỉ voluntary eviction | Fault-domain resilience thực |
| `ScheduleAnyway` nhưng đòi hard isolation | Scheduler có thể vi phạm spread | Hard placement rule khi cần |
| Hard anti-affinity không có capacity | Pods Pending, rollout stuck | Spare AZ/node budget |
| Node mới được xem healthy ngay | Chưa copy/catch up dữ liệu | Readiness by replica state |
| Roll nhiều voters đồng thời | Mất quorum | Sequential safe maintenance |
| Client chỉ một seed ở AZ A | Cold-start fail sau loss A | Multi-AZ discovery |
| Hard-code old primary IP | Failover không được nhận biết | Driver-supported topology |
| Retry mọi write timeout | Double business effect | Idempotency/outcome lookup |
| Chỉ cần RF không cần backup | Logical delete/corruption replicate | PITR/offline immutable backup |
| Gộp multiple shards trên một host | Correlated failure của copies | Per-shard anti-affinity |
| Tăng nodes nhưng hot key không đổi | Partition bottleneck vẫn còn | Data/key distribution |
| Quên cross-AZ egress | Chi phí/latency surprise | Network budget/cost |
| Chỉ đo election time | RTO user lâu hơn | End-to-end API recovery |
| Test node crash, không test AZ loss | Bỏ sót correlated failures | Per-AZ fault injection |
| Quên capacity của app/cache | Database còn quorum nhưng service down | End-to-end topology map |
| Di chuyển PVC mà không hiểu CSI | Volume không attach được | StorageClass topology |
| Không audit placement sau recovery | Replica group drift | Periodic placement checks |
| Tự ép read/write khi minority partition | Split-brain/data loss | Fencing/quorum compliance |

## 30. Bài tập thực hành

### Bài 1 — Ba replicas nhưng một AZ

Cluster có ba data nodes đều trong AZ A. Mỗi node giữ một copy dữ liệu, replication factor RF=3.

1. Chịu mất một host không?
2. Chịu mất AZ A không?
3. Thay đổi physical placement tối thiểu để chịu mất một AZ?
4. Ngoài việc đổi placement, cần kiểm tra điều gì trước khi hứa critical writes vẫn hoạt động?

### Bài 2 — Majority với ba voters

Một nhóm Raft-like có ba voting data-bearing members ở AZ A, B, C.

1. Majority là bao nhiêu?
2. Mất AZ B, còn đủ voters không?
3. Mất A và B đồng thời, còn quorum không?
4. Nếu A là leader và mất, các điều kiện nào để B/C elect leader mới?

### Bài 3 — Số voting members chẵn

Tính majority và số voters có thể mất cho N=2, N=4, N=5, N=6.

1. Vì sao từ 3 lên 4 voters không tăng mức chịu mất voters theo majority?
2. Có phải “chẵn thì sai” trong mọi consensus/protocol không?
3. Vì sao nên cân nhắc voter count với topology và roles thay vì chỉ chọn số lớn?

### Bài 4 — Năm voters trải ba AZ

Voters phân bố A:2, B:2, C:1. Yêu cầu chịu mất một AZ.

1. Majority bao nhiêu?
2. Mất AZ A, còn quorum?
3. Mất AZ C, còn quorum?
4. Mất đồng thời A và B, còn quorum?
5. Nếu hai voters ở A không có data, data availability còn đảm bảo không?

### Bài 5 — Placement sai trong một shard

Có sáu data nodes, hai mỗi AZ. Shard S1 có replicas trên A1, A2 và B1; shard S2 có copies trên A1, B1, C1.

1. Nếu AZ A mất, shard nào còn bao nhiêu copies?
2. Có thể kết luận toàn cluster chịu một-AZ loss chỉ từ RF=3 không?
3. Đề xuất placement cho S1.
4. Một placement auditor cần duyệt nhóm nào?

### Bài 6 — N+AZ capacity

Cluster có 12 nodes, đều ở ba AZ (bốn nodes/AZ). Normal average utilization 48% với workload được phân bố đồng đều.

1. Mất một AZ còn mấy nodes?
2. Suy utilization after-failure theo mô hình đơn giản.
3. Nếu mục tiêu degraded utilization ≤70%, cấu hình này còn headroom?
4. Những yếu tố nào khiến phép chia đều không đúng?

### Bài 7 — Maximum normal utilization

Cluster sáu nodes, hai nodes/AZ. Muốn giữ utilization sau mất một AZ ≤65%.

1. Tính giới hạn utilization normal theo giả định chia đều.
2. Nếu một shard chiếm 30% traffic, có dùng kết quả đó làm cam kết không?
3. Cần đo thêm storage và network gì?

### Bài 8 — Storage RF3

Logical data 12 TiB, RF=3. Các indexes/WAL/compaction làm raw overhead tăng ngoài copied payload.

1. Tính replicated raw payload ban đầu.
2. Nếu mỗi node usable storage 8 TiB, tối thiểu bao nhiêu nodes về mặt payload thuần?
3. Vì sao số nodes tối thiểu theo bytes không đủ để chọn topology?
4. Tính temporary free space cần dựa trên những yếu tố nào?

### Bài 9 — Data voters và witness

Một cụm có primary data A, replica data B và witness C.

1. Có bao nhiêu data copies?
2. Có bao nhiêu votes nếu cả ba được cấu hình voting?
3. Khi B chết, A+C có thể giữ election quorum không?
4. Việc này có đủ đáp ứng một majority **data-bearing write ACK** không?
5. Những điều kiện nào cần xem theo engine?

### Bài 10 — Network partition 1+2

Leader A bị tách mạng khỏi followers B/C trong một majority-based group.

1. Phía nào còn quorum?
2. A có được tiếp tục acknowledge quorum writes không?
3. Nếu clients vẫn giữ connection tới A, cần fencing thế nào?
4. Vì sao DNS switch sang B/C chưa là biện pháp safety đủ?

### Bài 11 — Khả năng chịu AZ khi control plane đặt lệch

Data replicas S1/S2/S3 đều trải ba AZ, nhưng metadata voting members đều nằm ở A.

1. Mất A, data copies còn bao nhiêu?
2. Metadata quorum còn không?
3. Những operations nào có thể bị ảnh hưởng?
4. Sửa topology metadata thế nào?

### Bài 12 — MongoDB arbiter

Một MongoDB replica set có primary data ở A, secondary data ở B và arbiter ở C.

1. Mất C ảnh hưởng những gì?
2. Mất B, một data copy và arbiter còn; nên suy durable majority writes thế nào?
3. Tại sao arbiter không thay thế một data-bearing replica?
4. Với requirement no loss of acknowledged writes dưới single-AZ failure, nên đánh giá configuration nào?

### Bài 13 — MongoDB sharded cluster

Shards có replica sets trải A/B/C. Config server replica set và mongos routers lại chỉ ở A.

1. Mất A, data copies còn sống có đủ kết luận hệ HA không?
2. Vai trò config servers/routers?
3. Nên phân bổ chúng ra sao?
4. Java connection string phải xử lý topology discovery thế nào?

### Bài 14 — Cassandra rack awareness

Cluster Cassandra 9 nodes, mỗi AZ 3 nodes. Cấu hình tất cả nodes là `rack1`, NetworkTopologyStrategy RF3.

1. Vì sao rack label sai làm giảm chất lượng placement?
2. RF3 có đảm bảo ba distinct AZ nếu rack mapping sai không?
3. Cần audit partition token ranges thế nào?
4. Khi sửa rack labels trong cluster đang chạy cần chú ý gì?

### Bài 15 — Cassandra LOCAL_QUORUM

DC1 RF=3, replica của mỗi partition ở A/B/C; một AZ mất.

1. Local quorum cần bao nhiêu replicas?
2. Hai replicas còn lại có thể phục vụ writes không theo assumptions đã cho?
3. Nếu app dùng CL ALL thì sao?
4. Tại sao không tuyên bố mọi read linearizable chỉ từ RF3 và LOCAL_QUORUM?

### Bài 16 — Redis Cluster

Ba primary P1/P2/P3 ở AZ A/B/C. Replica R1 của P1 cũng ở A, R2 của P2 ở C, R3 của P3 ở A.

1. Mất AZ A, chuyện gì xảy ra với P1 và R1?
2. Mất AZ C, primary nào có thể promote replica?
3. Có đủ slot coverage và failover election không?
4. Phân bố replicas sao cho không cùng AZ với primary?

### Bài 17 — Elasticsearch/OpenSearch

Một index có 5 primary shards và 1 replica cho mỗi primary; cluster có 3 AZ.

1. Hai copies của mỗi shard có thể phân bố trên mấy AZ?
2. Có đảm bảo chịu mất *bất kỳ* một AZ không nếu replicas được đặt đúng khác AZ?
3. Nếu cần chịu mất một AZ mà vẫn đủ 2 copies, cần suy tính replica count thế nào?
4. Metadata/cluster-manager roles đặt ở đâu?
5. Vì sao disk watermarks ảnh hưởng relocation sau AZ loss?

### Bài 18 — Kubernetes spread

Một StatefulSet có 3 pods và `topologySpreadConstraints` maxSkew=1 nhưng toàn bộ workers chỉ ở AZ A.

1. Kubernetes có thể tạo AZ B/C không?
2. Cần node pools/capacity gì?
3. Một `required` zone anti-affinity có thể gây trạng thái gì?
4. Topology spread của pods có đủ chứng minh shard replica placement không?

### Bài 19 — PVC pinned to AZ

Pod data ở AZ A dùng block volume chỉ gắn được trong A. AZ A chết.

1. Scheduler có thể tự attach volume đó ở B không?
2. Recovery khác gì với replicated database copy đã ở B/C?
3. `WaitForFirstConsumer` giúp giai đoạn provision nào?
4. Vì sao không nên coi StatefulSet là bản sao dữ liệu?

### Bài 20 — PodDisruptionBudget

Có ba metadata-voter pods, PDB `minAvailable: 2`.

1. Một voluntary drain tác động thế nào?
2. AZ outage involuntary có bị PDB chặn không?
3. Có thể scheduler thấy pod Ready nhưng database voter không caught up không?
4. Cần thêm safe-drain hook nào theo sản phẩm?

### Bài 21 — Java client seeds

Java service có ba DB seeds nhưng cả ba FQDN đều trỏ tới AZ A.

1. Khi A chết, một Java pod mới có bootstrap được không?
2. Java process đã kết nối từ trước có thể vẫn chạy không? Điều gì quyết định?
3. Sửa discovery endpoints và DNS dependencies thế nào?
4. Cold-start failover test nên chạy ra sao?

### Bài 22 — Java retry storm

Sau leader failover, 2.000 logical writes/s; gateway retry 3 lần, app retry 3 lần và SDK retry 2 lần.

1. Worst-case attempts multiplier theo mô hình nhân các tầng?
2. Tốc độ attempts/s tối đa lý thuyết?
3. Điều gì xảy ra với nodes còn lại?
4. Làm sao phối hợp attempt/deadline budgets?
5. Tại sao write timeout cần idempotency?

### Bài 23 — Recovery throughput

Một replica 8 TiB cần rebuild, effective copy throughput 250 MiB/s.

1. Thời gian truyền raw payload tối thiểu?
2. Vì sao index rebuild/compaction/catch-up kéo dài?
3. Nếu tăng copy throughput lên 500 MiB/s có chắc tốt hơn cho người dùng không?
4. Cần network/IO budget và max lag nào?

### Bài 24 — Mất AZ trong giờ cao điểm

Cluster 3 AZ với hai nodes/AZ, normal CPU 60%. Mất một AZ khi traffic đang ở peak.

1. CPU sau lỗi theo mô hình chia đều?
2. Nếu remaining nodes có disk IOPS sát giới hạn, hiện tượng gì?
3. Có nên tăng connection pool để “giúp throughput” không?
4. Thiết kế admission/load shedding thế nào?
5. Nếu critical writes cần quorum, có được đổi sang write ONE để xử lý sự cố không?

### Bài 25 — Hai regions và RPO

Region A active, Region B standby qua asynchronous replication.

1. Nếu A mất đột ngột, có chắc RPO=0 không?
2. B có thể được promote nếu vẫn đang thiếu writes không?
3. Cần biết source positions và data correctness nào trước failover?
4. Làm thế nào fence A khi mạng phục hồi?
5. Trong lúc B phục vụ, client DNS/session routing thay thế thế nào?

### Bài 26 — Active–active conflict

Region A và B cùng cho sửa inventory SKU1, mỗi nơi bán đơn vị cuối cùng trong network partition.

1. Cross-region replication sau partition có tự sửa oversell không?
2. LWW theo wall clock có đủ domain invariant không?
3. Có thể dùng single authority/escrow/reservation model thế nào?
4. Topology availability cần tương thích business invariants ra sao?

### Bài 27 — Placement drift

Ban đầu shard S1 ở A/B/C. Sau khi sửa node lỗi, S1 ở B1/B2/C1.

1. Distinct AZ count còn bao nhiêu?
2. Nếu B mất thì còn bao nhiêu copies?
3. Data quorum 2/3 có còn không?
4. Automation/alert nào phát hiện drift?
5. Có nên tự động di chuyển một copy về A ngay khi A vẫn lỗi không?

### Bài 28 — Backup vs replication

Một script xóa nhầm toàn bộ Orders, delete được replicate tới ba AZ.

1. Có thể khôi phục bằng cách “đọc từ follower” không nếu mọi replicas đều đã apply delete?
2. Vì sao RF3 chưa phải DR cho logical errors?
3. Backups/PITR cần isolation và retention gì?
4. Nên test restore thế nào?

### Bài 29 — Full topology review

Thiết kế cho dịch vụ NoSQL có các yêu cầu:

~~~text
Regions: 1 primary region, 3 AZ
Peak: 25,000 point reads/s + 4,000 writes/s
Logical live data: 18 TiB
Must survive any one AZ failure
Critical write RPO under defined single-AZ failure: 0
Read p99 degraded-mode goal: <250ms
Write p99 degraded-mode goal: <500ms
Java API autoscale: 12 to 36 pods
~~~

Hãy đề xuất:

1. Topology data nodes/shards/replication groups.
2. Metadata/control-plane/voter placement.
3. Maximum normal utilization theo degraded capacity model.
4. Disk usable/copy capacity, compaction and re-replication headroom.
5. AZ-aware application/ingress/caches.
6. Java driver discovery/read consistency/retry/deadlines.
7. Backup/PITR/RPO/RTO plan.
8. Dashboard và test matrix trước production.

### Bài 30 — Phản biện proposal

Một proposal ghi:

> “Dựng 6 database pods trên Kubernetes, bật RF=3 và PDB minAvailable=5. Scheduler tự chia AZ. App chỉ kết nối db-0. Khi có sự cố, tăng pool và tăng timeout. Storage dùng cùng một SAN để dễ vận hành. Có replicas nên không cần backup.”

Hãy tìm **ít nhất mười vấn đề hoặc assumptions chưa được chứng minh**, rồi viết lại topology/operations plan bảo vệ single-AZ failure, data safety và end-to-end API availability.

## 31. Gợi ý lời giải cho các bài quan trọng

### 31.1. Bài 1 — Ba copies cùng AZ

RF3 trên ba hosts AZ A có thể chịu lỗi **một host** theo giả định các host độc lập, replica quorum/placement hỗ trợ, nhưng **không** chịu mất AZ A. Di chuyển/sắp xếp replicas sang A/B/C là bước cần thiết; sau đó vẫn phải kiểm tra data/metadata quorum, read/write concern, failover và degraded capacity.

### 31.2. Bài 2 — Majority ba voters

\[
Q=\lfloor3/2\rfloor+1=2
\]

Mất một AZ chứa một voter còn 2/3 ⇒ majority. Mất hai AZ chỉ còn 1/3 ⇒ không có majority. Nếu leader A chết, B/C phải còn kết nối, đủ điều kiện bầu leader và đáp ứng safety log/term rules; không chỉ “hai máy còn ping được”.

### 31.3. Bài 3 — Voters chẵn/lẻ

| N | Majority | Failures tolerated |
| ---: | ---: | ---: |
| 2 | 2 | 0 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |

Đối với majority voting groups, N=4 không tốt hơn N=3 về số voter failures chịu được. Nhưng một số protocols có weighted votes, witnesses, different quorums hoặc role constraints; không biến “chọn odd number” thành luật bất biến cho mọi NoSQL.

### 31.4. Bài 4 — Năm voters, A:2/B:2/C:1

Majority 3/5:

- Mất A ⇒ còn 3 ⇒ giữ majority.
- Mất B ⇒ còn 3 ⇒ giữ majority.
- Mất C ⇒ còn 4 ⇒ giữ majority.
- Mất A+B ⇒ chỉ còn 1 ⇒ mất majority.

Nếu một số members là non-data witnesses, **write durability/data quorum** cần tính riêng.

### 31.5. Bài 5 — Shard S1 lệch AZ

S1 ở A1/A2/B1. Mất AZ A còn **một copy** ở B1. S2 ở A1/B1/C1 còn **hai copies** ở B/C. Với một data majority 2/3 theo giả định, S1 không đủ nhưng S2 có thể đủ. Sửa S1 thành A1/B1/C1 hoặc placement tương đương.

### 31.6. Bài 6 — N+AZ với 12 nodes

Mất bốn nodes còn tám:

\[
u_{\mathrm{after}}=0{,}48\times\frac{12}{8}
=0{,}72=72\%
\]

Vượt mục tiêu 70% trong mô hình chia đều; chưa kể query skew, replication/repair và hardware nonuniformity.

### 31.7. Bài 7 — Normal headroom cho 6 nodes

Hai nodes/AZ, mất AZ còn bốn. Để \(u_{\mathrm{after}}\le65\%\):

\[
u_{\mathrm{normal}}\le65\%\times\frac46
\approx43{,}33\%
\]

Con số này không áp trực tiếp cho per-shard hot key/cold cache hoặc resource bottleneck khác; phải đo degraded-mode p99.

### 31.8. Bài 8 — 12 TiB RF3

\[
12\times3=36\ \mathrm{TiB}
\]

Nếu mỗi node có usable 8 TiB, lower-bound bytes-only:

\[
\lceil36/8\rceil=5\text{ nodes}
\]

Nhưng **năm nodes có thể không cho đúng data-placement/headroom/three-AZ capacity**, và không chừa index/WAL/compaction free space. Không dùng `ceil` thuần để quyết định số máy production.

### 31.9. Bài 9 — Arbiter/witness

Primary A và replica B là hai data copies; C là witness không chứa full data. Khi B chết, A+C có thể giữ voting majority trong một số protocols, nhưng không tự đáp ứng majority **data-bearing durable acknowledgments**. Phải đọc election, write concern và data safety contract của engine.

### 31.10. Bài 10 — Network partition 1+2

Phía B+C còn majority; phía A là minority, không được commit writes yêu cầu majority theo safety protocol. **Term/epoch/fencing** bảo vệ khỏi old leader writes. DNS update không chặn một client còn giữ stale connection tới A.

### 31.11. Bài 15 — Cassandra LOCAL_QUORUM

Với RF=3 tại một datacenter:

\[
\mathrm{LOCAL\_QUORUM}=\lfloor3/2\rfloor+1=2
\]

Mất một AZ chứa một replica cho partition, còn hai có thể đáp ứng local quorum nếu healthy/reachable và replica placement đúng. CL ALL đòi đủ ba, nên có thể không available. `LOCAL_QUORUM` không tự là strict linearizability cho mọi concurrent updates.

### 31.12. Bài 17 — Elasticsearch replicas

Một primary + 1 replica = **2 copies** của mỗi shard; nếu được đặt ở hai AZ khác nhau, mất bất kỳ một AZ đơn lẻ vẫn có ít nhất một copy (với những assumptions về assignment/management). Nhưng nếu yêu cầu **còn hai full copies sau mất một AZ**, cần xem một primary + 2 replicas trải ba AZ, kèm storage/capacity/cluster-manager quorum.

### 31.13. Bài 20 — PDB

`minAvailable:2` có thể chặn voluntary eviction khiến matching Ready pods tụt dưới 2, nhưng không ngăn node/AZ crash. Kubernetes readiness chỉ là health signal được cấu hình; **không tự chứng minh database voter caught up** nếu probes không kiểm tra engine state. Cần database-specific drain/step-down/catch-up.

### 31.14. Bài 22 — Retry nhiều tầng

Nếu “3 lần”, “3 lần”, “2 lần” đều được định nghĩa là **tổng số attempts tại mỗi tầng**, worst-case multiplier:

\[
3\times3\times2=18
\]

Với 2.000 logical writes/s:

\[
2000\times18=36\,000\text{ deep attempts/s}
\]

Thực tế phụ thuộc retry reasons, timeouts và pipeline structure. Nếu “retry 3 lần” nghĩa **3 retries sau lần đầu**, phải đổi multiplier thành 4 ở tầng đó. Luôn định nghĩa rõ `maxAttempts` vs `maxRetries`.

### 31.15. Bài 23 — Recovery 8 TiB

\[
T=\frac{8\times1024\times1024}{250}
\approx33\,554\text{ s}=9{,}32\text{ giờ}
\]

Đây là **thời gian tối thiểu theo throughput payload thô**, không tính rebuild indexes, stream catch-up, compaction và resource contention. Tăng tốc copy có thể làm user p99 xấu nếu disk/network shared capacity đã bão hòa.

### 31.16. Bài 24 — CPU sau mất AZ

\[
u_{\mathrm{after}}=60\%\times\frac64=90\%
\]

90% theo mô hình đồng đều là rủi ro saturation rất cao khi còn rebuild/repair. Nên ưu tiên admission/queue bounded, throttle background workloads, bảo vệ quorum/correctness và scale capacity nếu có. **Không hạ consistency/durability tùy tiện để che lỗi**.

### 31.17. Bài 25 — Active–passive RPO

Asynchronous replication từ A sang B có thể chưa chuyển những writes vừa ACK khi A mất; **RPO=0 không được bảo đảm mặc định**. Cần kiểm tra replay/source positions, dữ liệu thiếu, runbook promotion và fencing old region khi phục hồi. Nếu business đòi no-loss, phải thiết kế synchronous/transactional authority phù hợp hoặc thay business workflow.

### 31.18. Bài 27 — Placement drift

S1 ở B1/B2/C1 ⇒ **2 distinct AZ**. Mất B còn một copy ở C. Với data majority 2/3, không đủ. Placement checker nên cảnh báo **group-level under-diversity**, không chỉ node count. Nếu A vẫn outage, không thể tạo replica tại A; có thể tạm hoạt động degraded với policy/extra AZ phù hợp.

### 31.19. Bài 28 — Delete sai

Khi mọi replicas đã apply logical delete, replication không cung cấp bản cũ làm nguồn khôi phục. Cần backup/PITR được kiểm thử, retention và quyền truy cập cách ly. Thử restore **trong isolated environment**, đối chiếu logical checksums/business invariants trước khi cutover.

### 31.20. Bài 30 — Phê bình proposal

Những lỗ hổng chính:

1. Không khai báo AZ/rack labels và per-shard replica placement.
2. RF=3 không chứng minh các copies khác fault domain.
3. PDB không chống AZ outage.
4. `minAvailable:5` có thể ngăn voluntary upgrade nhưng không bảo đảm database majority.
5. Pods có thể cùng AZ nếu topology constraints thiếu.
6. Stateful volumes có thể AZ-pinned.
7. Shared SAN là single storage failure domain.
8. Không có metadata/control-plane voters placement.
9. Không có N+AZ CPU/memory/IO/storage capacity model.
10. App chỉ kết nối `db-0`, single discovery point.
11. Tăng connection pool sau failure có thể overload remaining nodes.
12. Tăng timeout không sửa election/fencing và có thể giữ connections lâu hơn.
13. Không có bounded retry và idempotent writes.
14. Không có backup/PITR để sửa logical deletes/corruption.
15. Không có cold-start/AZ fault tests hoặc recovery SLO.

Sửa bằng một **end-to-end topology plan** gồm data/voter group per-zone placement, storage-domain isolation, client discovery resilient, N+AZ headroom, backup/PITR, safe maintenance, fault injection và runbook.

## 32. Checklist thiết kế và triển khai topology

### 32.1. Mục tiêu và failure model

1. Đã ghi rõ **single-host, rack, AZ, region, network partition** nào hệ phải chịu không?
2. Có phân biệt khả năng **đọc**, khả năng **ghi** và độ bền acknowledged writes không?
3. Có SLO p95/p99/error rate trong degraded steady state không?
4. Có RPO/RTO riêng cho AZ loss và region loss không?
5. Có nêu điều kiện lỗi **không** được hỗ trợ không?
6. Có thiết kế backup/PITR cho logical corruption/delete không?

### 32.2. Data và quorum placement

7. Có inventory host/rack/AZ/region/storage/power/network dependencies không?
8. Mỗi replication group có số data-bearing copies đúng RF không?
9. Các copies của **từng shard/partition** có trải failure domains cần thiết không?
10. Có tính quorum cho từng failure scenario không?
11. Data quorum và metadata/voting quorum đã được đánh giá riêng không?
12. Witness/arbiter có bị đếm nhầm là full data replica không?
13. Leaders/coordinators có bị tập trung ở một AZ không?
14. Có term/epoch/fencing chống split-brain không?
15. Có hiểu read/write concern và failure behavior của engine không?
16. Có audit group placements sau failover/rebalance không?

### 32.3. Capacity

17. Normal utilization có chừa N+1 và N+AZ headroom không?
18. Có đo capacity theo **CPU/RAM/cache/disk IOPS/throughput/network** không?
19. Có test p99 khi mất AZ vào **peak load** không?
20. Có tính hot shards/partition skew thay vì chia đều hoàn toàn không?
21. Có đủ storage free space/compaction headroom để rebuild không?
22. Có giới hạn replication/rebalance bandwidth để không phá user SLO không?
23. Có tính index/WAL/tombstone/snapshot/backup overhead không?
24. Có dự phòng connection quotas và API autoscale rollout không?
25. Có đủ app/ingress/cache capacity sau AZ loss không?

### 32.4. Kubernetes / hạ tầng

26. `topology.kubernetes.io/zone` và hạ tầng labels có khớp AZ thật không?
27. Có anti-affinity/topology spread đúng **replica group labels** không?
28. Hard scheduling constraints có đủ node/AZ capacity để tránh Pending không?
29. StatefulSet/PVC/CSI StorageClass có zone affinity phù hợp không?
30. Có hiểu `WaitForFirstConsumer` và storage provisioning timing không?
31. Có hiểu PDB chỉ kiểm soát voluntary disruptions không?
32. Database operator có biết cluster membership/quorum/readiness không?
33. Rolling upgrade/decommission có kiểm tra catch-up trước khi sang node kế tiếp không?
34. Seed/DNS/credentials/KMS/routers có single-AZ point of failure không?
35. Có kiểm tra VM/SAN/power domains ngoài scheduler không?

### 32.5. Java client và correctness

36. Driver có discovery endpoints ở nhiều AZ và đúng topology mode không?
37. Có test **Java cold-start khi một AZ đã mất** không?
38. Read policies có phân biệt latency locality và stale-replica eligibility không?
39. Writes có deadlines và retry budget phối hợp giữa gateway/app/SDK không?
40. Có idempotency/conditional mutation/outcome lookup cho write timeout không?
41. Có metrics logical requests vs DB attempts và connection creation storms không?
42. Có giới hạn requests in-flight/bounded queue khi failover không?
43. Client có tránh hard-coded old primary IP không?

### 32.6. Multi-region và recovery

44. Có phân biệt AZ HA với region DR không?
45. Cross-region replication sync/async và actual RPO có được hiểu đúng không?
46. Có region promotion, fencing và rollback/reconciliation procedure không?
47. Active-active conflicts có domain resolution và authority rule không?
48. Có giới hạn cross-AZ/cross-region latency và egress cost không?
49. Có measured rebuild/catch-up time, không chỉ estimated copy time không?
50. Có kiểm tra recovery after AZ returns và placement drift không?

### 32.7. Quan sát và kiểm thử

51. Có dashboard per-shard copies/health/leader AZ không?
52. Có dashboard voter/data quorum và metadata health không?
53. Có network latency/loss/replication backlog per route không?
54. Có per-node disk free, IOPS, fsync, compaction và memory metrics không?
55. Có alert khi replica placement mất diversity không?
56. Có fault matrix **mất từng AZ**, không chỉ AZ chứa leader không?
57. Có test network partition 1+2 và safety/fencing không?
58. Có test voluntary maintenance khi cluster đã degraded không?
59. Có test regional recovery và backup/PITR isolated restore không?
60. Có on-call runbook/owner xác định khi quorum hoặc AZ bị ảnh hưởng không?

## 33. Kết luận

Thiết kế topology NoSQL đúng không phải chọn số lượng nodes theo cảm tính. Đó là việc phân bổ **các bản sao dữ liệu, voting/control-plane members và application dependencies** qua những **miền lỗi thật sự độc lập**, đồng thời chứng minh hệ còn đáp ứng consistency và capacity sau một lỗi đã cam kết chịu được.

Những điều cốt lõi:

- **Replication không đồng nghĩa fault isolation.** Ba copies trong một AZ vẫn cùng thất bại nếu AZ ấy mất.
- **Sharding không đồng nghĩa replication.** Mỗi shard cần placement và quorum riêng.
- **Quorum phụ thuộc voters, data-bearing members, roles và placement.** Đủ votes không luôn đủ durability/write capacity.
- **Miền lỗi không chỉ là VM.** Rack, power, network, storage controller, AZ, region, credentials và cấu hình vận hành đều tạo correlated risks.
- **N+AZ capacity là yêu cầu vận hành.** Cụm có quorum nhưng còn 90% CPU hoặc disk full không thể cam kết latency/availability SLO.
- **Multi-region DR không đồng nghĩa synchronous no-loss.** Active–passive async có RPO window; active–active cần conflict resolution.
- **Kubernetes labels, anti-affinity, topology spread, PDB và StatefulSets chỉ giải quyết một phần vấn đề.** Cần database-aware replication/membership và storage topology.
- **Java clients phải topology-aware.** Multiple seed endpoints, driver discovery, bounded retries và idempotency quyết định end-to-end failover.
- **Bảo trì, scale và recovery có thể tự làm mất HA** nếu chưa kiểm tra quorum/catch-up sau mỗi bước.
- **Backup/PITR vẫn cần thiết** vì replicas thường lan truyền cả logical deletes/corruption.
- **Kiểm thử thật mất từng AZ** cùng peak workload, cold-start, node rebuild và network partition mới kiểm chứng được resilience.

Trước khi phê duyệt một cụm NoSQL, hãy trả lời bằng sơ đồ và bằng chứng đo:

> **“Nếu mất bất kỳ một miền lỗi đã cam kết chịu được, mỗi shard còn bao nhiêu bản sao dữ liệu; metadata/voting groups còn đủ quorum không; application còn kết nối được đến thành viên hợp lệ không; và capacity còn lại có đáp ứng SLO trong cả failover lẫn phục hồi không?”**

Khi trả lời đủ câu hỏi đó, topology mới là **một thiết kế chịu lỗi có thể kiểm chứng**, không chỉ một cụm có nhiều máy.
