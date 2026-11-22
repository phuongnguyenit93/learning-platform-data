# Khởi động, dừng và xác định trạng thái phục vụ của nút

## 1. Mở đầu: process chạy không đồng nghĩa nút đã phục vụ được

Một cụm NoSQL có ba nút, ứng dụng Java dùng connection pool để đọc và ghi dữ liệu. Đội vận hành khởi động lại `db-node-2`. Sau 10 giây, hệ điều hành báo process `active`, cổng TCP đã mở và container hiển thị `Running`. Load balancer lập tức đưa nút này trở lại danh sách phục vụ.

Ngay sau đó, một số requests timeout vì nút vẫn đang khôi phục dữ liệu từ log, tải snapshot và bắt kịp replica. Những lỗi này làm driver retry sang các nút còn lại; cả cụm chậm theo.

~~~text
10:00:00 Process được khởi động
10:00:03 TCP port mở
10:00:05 TLS handshake thành công
10:00:08 Nút đăng ký vào cluster membership
10:00:40 Replica vẫn đang đồng bộ dữ liệu
10:01:15 Nút bắt kịp mức lag cho phép
10:01:30 Read/write readiness được xác nhận
~~~

**Không có lý do gì để coi sáu mốc trên là một thời điểm.**

Một tình huống còn nguy hiểm hơn: node báo `UP`, nhưng cụm đã mất đủ số thành viên để commit theo mức nhất quán yêu cầu; API có thể kết nối được nhưng các thao tác ghi quan trọng vẫn phải từ chối.

Bài học **“Khởi động, dừng và xác định trạng thái phục vụ của nút”** thuộc chương **Vận hành cụm** trong module **Database No SQL**. Mục tiêu là xây một quy trình vận hành xác định đúng lúc nút được đưa vào lưu lượng, lúc có thể dừng nó, và khi nào phải hoãn thao tác để không phá dữ liệu hoặc làm mất khả năng phục vụ.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt trạng thái **process, network, TLS, membership, replication, data recovery, read readiness và write readiness**.
2. Giải thích *liveness*, *startup*, *readiness* và *cluster health* không phải một phép đo.
3. Mô tả các bước bootstrap, restart, recovery, rolling restart, graceful shutdown và decommission.
4. Kiểm tra những điều kiện an toàn liên quan quorum, leader, replication lag và data ownership trước khi dừng nút.
5. Phân tích trạng thái nút theo Cassandra, MongoDB replica set, Redis Sentinel/Cluster, Elasticsearch/OpenSearch, Couchbase và dịch vụ managed như DynamoDB.
6. Thiết kế startup/readiness/liveness probes cho Kubernetes mà không tạo restart loop.
7. Phân biệt driver/server-selection thành công với thao tác đọc/ghi nghiệp vụ thực sự thành công.
8. Lập runbook có điều kiện tiến hành, tạm dừng, rollback và kiểm chứng cuối.
9. Xây một mô hình Java biểu diễn trạng thái phục vụ với lý do từ chối.
10. Thiết kế fault-injection tests xác minh cụm không phục vụ dữ liệu không an toàn khi nút mới khởi động hoặc đang ngừng hoạt động.

---

## 2. “Trạng thái nút” có nhiều lớp

| Lớp | Câu hỏi | Ví dụ tín hiệu |
|---|---|---|
| **Process** | Tiến trình có chạy không? | `systemctl is-active`, process/container status |
| **Transport** | Cổng dịch vụ có kết nối được không? | TCP connect |
| **Security** | TLS peer hợp lệ và xác thực thành công không? | TLS handshake, certificate identity |
| **Protocol** | Server hiểu request của client không? | Ping/hello/health command |
| **Membership** | Node thuộc cụm đúng không? | Gossip/cluster topology/replica-set membership |
| **Ownership** | Node đang sở hữu/shard/range nào? | Token ranges, slot ownership, shard allocation |
| **Recovery** | WAL/oplog/replay/checkpoint/flush đã đủ chưa? | Recovery/sync progress |
| **Replication** | Node bắt kịp dữ liệu đến mức policy cho phép chưa? | Lag, sync state, applied position |
| **Role** | Node là leader/primary, follower/secondary hay replica? | Role state, term/epoch |
| **Read eligibility** | Node có thể trả loại read được yêu cầu không? | Read preference, consistency, shard availability |
| **Write eligibility** | Node có thể nhận/commit write theo contract không? | Primary/leader, quorum, slots, disk/ACL |
| **End-to-end service** | Ứng dụng còn đạt SLO/đúng dữ liệu không? | Successful request rate, p99, error budget |

Một lệnh kiểm tra không thể thay toàn bộ bảng này. Đặc biệt, `ping` có thể thành công ngay cả khi node đang recovery hoặc mất khả năng phục vụ một phần keyspace.

### 2.1. Sẵn sàng là một phát biểu có điều kiện

Thay vì nói “node đã ready”, cần nói rõ:

> “Nút này đủ điều kiện nhận **point reads** với consistency và read preference đã cấu hình, cho những partitions mà nó phục vụ, tại thời điểm kiểm tra.”

Hay:

> “Cụm hiện có thể commit writes theo write concern/consistency level của ứng dụng, không có recovery hoặc reconfiguration trái chính sách.”

Readiness phụ thuộc **loại thao tác**, không chỉ process.

### 2.2. Sức khỏe của nút khác sức khỏe cụm

Ba nút đều chạy nhưng không thấy nhau do network partition có thể tạo một cụm không có quorum; một nút báo unavailable nhưng những nút khác vẫn phục vụ được nhiều thao tác.

---

## 3. Mô hình vòng đời nút

Một state machine khái quát:

~~~mermaid
flowchart TD
    OFF["STOPPED"] --> START["STARTING"]
    START --> NET["TRANSPORT_READY"]
    NET --> JOIN["JOINING_CLUSTER"]
    JOIN --> REC["RECOVERING / CATCHING_UP"]
    REC --> READY["SERVING_ELIGIBLE"]
    READY --> DEG["DEGRADED"]
    DEG --> READY
    READY --> DRAIN["DRAINING"]
    DEG --> DRAIN
    DRAIN --> OFF
    START --> FAIL["FAILED"]
    JOIN --> FAIL
    REC --> FAIL
    DRAIN --> FAIL
    FAIL --> START
~~~

Đây là **mô hình tư duy**, không phải tên trạng thái chuẩn của tất cả NoSQL engines.

### 3.1. `STARTING`

Process đọc config, xác thực secret, mở storage, khôi phục metadata, thiết lập log và listener. Nhiều engines có thể chưa mở port khi ở bước này.

### 3.2. `TRANSPORT_READY`

Có TCP/TLS kết nối được nhưng chưa chắc node đã join, bắt kịp replica hoặc được phép nhận write.

### 3.3. `JOINING_CLUSTER`

Node giao tiếp membership/discovery, nhận role/ownership và có thể đợi election hoặc metadata consistency.

### 3.4. `RECOVERING/CATCHING_UP`

Replay WAL/commit log, tải snapshot, đồng bộ shard, phục hồi index, tham gia anti-entropy hoặc áp replicated writes còn thiếu.

### 3.5. `SERVING_ELIGIBLE`

Đường vận hành xác nhận node có thể nhận những request classes đã định nghĩa. Có thể chỉ ready đọc, chưa ready ghi; hoặc chỉ ready một số shards.

### 3.6. `DEGRADED`

Node hoạt động nhưng không đáp ứng toàn bộ tiêu chí: replica lag cao, disk gần đầy, thiếu shard, bị throttled hoặc mất kết nối tới một phần cluster.

### 3.7. `DRAINING`

Node ngừng nhận yêu cầu mới theo cơ chế phù hợp, đợi/thông báo những tác vụ đang chạy, xử lý log/flush và chuẩn bị rời khỏi lưu lượng hoặc topology.

### 3.8. `FAILED/STOPPED`

`STOPPED` có thể là kết quả có kế hoạch; `FAILED` là lỗi chưa được khôi phục. Đừng coi hai trạng thái tương đương trong alerting và incident response.

---

## 4. Liveness, startup và readiness: ba mục đích riêng

### 4.1. Liveness: có nên khởi động lại process?

Liveness phải phát hiện process bị treo và không thể tự phục hồi. Một `livenessProbe` quá nghiêm có thể restart node trong lúc nó đang bootstrap hoặc xử lý compaction bình thường, tạo **crash loop**.

### 4.2. Startup: có đang còn trong thời gian khởi động hợp lệ?

Startup probe cho những hệ cần thời gian dài replay log hoặc tải SSTables/segments. Nó giúp hệ điều phối không áp yêu cầu liveness quá sớm trong pha khởi động.

### 4.3. Readiness: có nên đưa lưu lượng vào node?

Readiness có thể báo `false` trong khi process vẫn chạy bình thường và đang bắt kịp dữ liệu. Đây là tình huống **đúng mong đợi**, không nhất thiết là sự cố cần restart.

### 4.4. Readiness không phải số 0/1 tuyệt đối cho mọi thao tác

Một replica có thể ready eventual reads nhưng không được phép nhận writes hoặc strongly consistent reads. Load balancer và driver phải hiểu endpoint role/consistency thay vì dùng một dấu `healthy` chung.

### 4.5. Cụm có thể phục vụ dù một node không ready

Availability là tính chất của topology/quorum và access pattern. Không nên tự đánh dấu **toàn bộ** API unavailable chỉ vì một node bị drain, nếu cluster vẫn đáp ứng contract.

---

## 5. Các điều kiện tối thiểu trước khi một node nhận traffic

Một tập kiểm tra hợp lý tùy engine:

1. Process chạy bằng đúng binary/version đã phê duyệt.
2. Config và identity là của **đúng cluster/environment**.
3. Không có lỗi storage corruption/recovery đang chặn serving.
4. TCP/protocol endpoint hoạt động và TLS certificate được xác minh.
5. Authentication, authorization, role mapping đúng.
6. Membership/topology không đang bất nhất.
7. Ownership của shard/slot/range được xác nhận.
8. Role đáp ứng loại read/write theo driver.
9. Recovery/bắt kịp replication đạt ngưỡng policy.
10. Đủ peer/quorum cho consistency/write concern tương ứng.
11. Disk/memory/CPU/IO headroom không ở mức nguy hiểm.
12. Không có maintenance lock hoặc routing drain đang yêu cầu tránh nút.
13. Driver có thể khám phá node đúng advertised address.
14. Một thao tác canary **không gây side effect nguy hiểm** thành công theo định nghĩa.
15. Metrics/alerts không có dấu hiệu dữ liệu cũ, stuck recovery hoặc retry storm.

Không cần mọi engine expose tất cả metric; điều quan trọng là **không bịa guarantee nếu không có tín hiệu tương ứng**.

---

## 6. Quorum và vai trò: nút sống chưa chắc ghi được

### 6.1. Replica groups dùng consensus

Với nhóm **5 thành viên có quyền bầu phiếu**, quorum đa số là:

\[
q=\left\lfloor\frac{5}{2}\right\rfloor+1=3.
\]

Nếu chỉ còn 2 voting members có kết nối tới nhau, nhóm không thể đạt quorum của giao thức consensus thông thường dù cả hai process đều phản hồi ping.

### 6.2. Không gộp mọi NoSQL vào Raft

- MongoDB replica set có election/voting và write concern semantics riêng.
- Cassandra dùng replication/consistency levels và cơ chế membership riêng, không phải một global leader cho mọi partition.
- Redis Sentinel/Cluster có failure-detection/failover riêng; asynchronous replication không đồng nghĩa durable quorum commit.
- Elasticsearch có cluster-manager election và shard-level allocation/replica behavior.
- DynamoDB là managed service; người dùng không tự vận hành storage-node quorum.

### 6.3. Quorum của từng thao tác khác trạng thái nút

Ví dụ một key có RF=3 với Cassandra và operation yêu cầu `LOCAL_QUORUM`: nếu không có đủ replicas tương ứng trong local DC, write có thể unavailable. Một node khác trong cluster không tự thay thế ngay replica đúng key/range.

### 6.4. Readiness phải phản ánh hợp đồng thực

Một follower có thể phục vụ local eventual read, nhưng không thể hứa linearizable read chỉ vì nó đang online. Với leader-based systems, đọc mạnh có thể cần leader hoặc protocol xác thực freshness.

### 6.5. Không tắt quorum để “cứu availability” tùy tiện

Giảm write concern/consistency làm thay đổi durability và consistency contract, có thể tạo acked-but-lost writes. Đây là quyết định nghiệp vụ/rủi ro, không phải một bước bình thường của runbook restart.

---

## 7. Khởi động node: những bước nội bộ thường gặp

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant N as NoSQL node
    participant P as Cluster peers
    participant M as Monitoring/Driver
    O->>N: Start process
    N->>N: Validate config, secrets, storage
    N->>N: WAL/journal/checkpoint recovery
    N->>P: Discover membership/topology
    P-->>N: Role/range/shard metadata
    N->>P: Replication catch-up / streaming
    N->>N: Warm caches / indexes as needed
    N-->>M: Readiness eligible by policy
    M->>N: Bounded canary operation
    N-->>M: Success
    Note over N,P: Node can begin serving approved workload
~~~

Thứ tự chính xác khác nhau theo engine; nhiều thao tác chạy song song.

### 7.1. Kiểm version và storage compatibility

Nút có thể từ chối mở files nếu binary/disk format không tương thích. Không đổi binary thủ công để “bỏ qua” migration guard.

### 7.2. Đọc credentials/certificates

Nếu TLS truststore, private key hoặc secret sai, node có thể mở process nhưng không bắt tay với peers. Một readiness check cần phân biệt lỗi peer-auth với data recovery.

### 7.3. Replay log

Crash recovery có thể replay journal/WAL/commit log trước khi cho phép nhận writes. Thời gian phụ thuộc log size, disk speed và trạng thái checkpoint trước đó.

### 7.4. Khôi phục membership

Nút cần biết cluster ID, peer addresses, epoch/term, shard ownership và replication role. Nếu nó join sai cluster, process running vẫn là sự cố nghiêm trọng.

### 7.5. Bắt kịp dữ liệu

Một replica offline 6 giờ có thể cần replay nguồn còn lịch sử hoặc full resync/snapshot. Port mở không chứng minh nó đã đủ dữ liệu.

### 7.6. Warm-up không phải luôn điều kiện tuyệt đối

Cache lạnh có thể làm p99 kém, nhưng không phải mọi hệ cần đợi toàn bộ working set vào RAM mới ready. Đặt ngưỡng dựa trên SLO, capacity và safety.

---

## 8. Phân biệt restart, bootstrap, replace và rejoin

| Hành động | Ý nghĩa | Rủi ro/điều kiện |
|---|---|---|
| **Restart node cũ** | Process tắt/mở lại với data volume và identity cũ | WAL recovery, stale replica, cert/version |
| **Bootstrap node mới** | Nút mới nhận dữ liệu/ownership | Streaming, disk/network, token/shard assignment |
| **Rejoin** | Nút từng là member quay lại | Membership epoch, stale logs, cluster identity |
| **Replace node** | Nút mới thay identity/ownership của member hỏng theo protocol | Có thể cần re-seed; tránh trùng owner |
| **Decommission** | Loại node khỏi topology có kiểm soát | Data migration và capacity của peers |
| **Force remove** | Xử lý member không còn phục hồi được bằng quy trình riêng | Data availability/durability risk |
| **Disaster restore** | Khôi phục data/cluster từ backups/logs | RPO/RTO, replay, consistency, deletion state |

**Đừng coi `stop` + xóa data directory + `start` là restart thông thường.** Nó có thể tạo một node mới, phá storage identity hoặc làm mất durable data.

### 8.1. Restart có thể không làm đổi membership

Một node tạm offline rồi trở lại có thể giữ ownership; vẫn cần kiểm thời gian offline, token/shard ownership, replica history và trạng thái mới nhất.

### 8.2. Bootstrap cần dung lượng phía nguồn và đích

Nút mới tải dữ liệu từ những peers còn khỏe; source peers tiêu thụ disk/network/CPU thêm trong quá trình streaming.

### 8.3. Replace phải theo engine

MongoDB, Cassandra, Elasticsearch, Redis Cluster và Couchbase có quy tắc khác nhau. Không copy thao tác “replace token/node ID” giữa các sản phẩm.

---

## 9. Quy trình khởi động có kiểm soát

### 9.1. Trước khi bắt đầu

- Xác định change/incident ID, owner, maintenance window.
- Biết cluster topology và replication placements.
- Kiểm không có recovery/decommission/upgrade khác gây xung đột.
- Kiểm backup/restore path và mức độ dữ liệu cần bảo vệ.
- Kiểm disk headroom của nút lẫn peers.
- Kiểm cert, secret, port, DNS và advertised addresses.
- Kiểm binary/config/feature compatibility.
- Xác định **điều kiện thành công** và **điều kiện dừng**.

### 9.2. Khởi động process

Dùng service manager/orchestrator theo deployment, không tạo process thủ công ngoài supervision khiến node chạy hai instance trên cùng data directory.

### 9.3. Theo dõi startup progress

Xem logs có cấu trúc, membership, recovery, replication progress, I/O saturation, memory/GC, network và lỗi handshake. Không chỉ chờ `sleep 30`.

### 9.4. Xác minh data/role

Chỉ đưa vào routing khi node đủ điều kiện cho operation classes dự kiến.

### 9.5. Mở lưu lượng từng bước

Nếu load balancing/driver hỗ trợ, tăng traffic dần; giám sát p95/p99, errors, retries, per-node CPU/IO và cache warm-up.

### 9.6. Kết luận theo bằng chứng

Ghi lại thời điểm process start, join, catch-up, eligible và đạt SLO. Nếu node không đủ điều kiện, báo degraded/blocker thay vì ghi “startup success”.

---

## 10. Dừng nút: stop, drain và decommission là ba ý khác nhau

### 10.1. Stop

Ngừng process, ví dụ service manager gửi signal đúng. Cluster có thể tạm coi member offline. Data ownership/membership có thể vẫn giữ nguyên.

### 10.2. Drain

Yêu cầu nút ngừng nhận request mới hoặc hoàn tất những tác vụ nội bộ theo protocol. Có thể gồm:

- Đưa node khỏi load balancer hoặc driver routing.
- Dừng nhận writes mới.
- Đợi in-flight requests trong deadline.
- Flush buffer/log tùy engine.
- Ngắt kết nối clients có kiểm soát.
- Phối hợp với peers và leader/replica roles.

**Từ “drain” có nghĩa cụ thể khác nhau theo công cụ.** Ví dụ, Cassandra `nodetool drain` tập trung vào ngừng nhận writes và flush memtables khi chuẩn bị shutdown; nó **không đồng nghĩa** một generic HTTP load balancer drain hay topology decommission.

### 10.3. Decommission

Loại nút khỏi cụm theo protocol, thường có bước di chuyển ownership/data và cập nhật membership. Nó có thể tốn nhiều network/disk và thay đổi topology lâu dài.

### 10.4. Xóa pod/VM không phải decommission

Nếu chỉ xóa VM chứa node mà không điều chỉnh membership/ownership đúng, cluster có thể giữ “ghost member” hoặc mất shards/replicas chưa khôi phục.

### 10.5. Khi nào chỉ cần stop?

Rolling restart một member có data volume/identity được giữ, với topology đủ redundancy, thường khác với muốn loại vĩnh viễn node khỏi cluster.

---

## 11. Graceful shutdown: điều gì phải xảy ra?

~~~mermaid
flowchart TD
    A["Maintenance approved"] --> B["Check cluster quorum / redundancy"]
    B --> C["Prevent new traffic to target"]
    C --> D["Wait for inflight work / transfer role"]
    D --> E["Engine-specific drain / checkpoint"]
    E --> F["Stop service process"]
    F --> G["Verify peers continue serving"]
    G --> H["Start or decommission according to plan"]
~~~

### 11.1. Quiesce không phải “kill bất ngờ”

Một server có thể nhận stop signal rồi tiếp tục hoàn thành requests trong khoảng grace period. Nếu orchestrator cắt process ngay lập tức, những thao tác đang chạy có thể bị bỏ dở.

### 11.2. Timeout có nghĩa gì?

Có thể có:

- HTTP/gRPC request deadline của ứng dụng.
- Database driver socket/read timeout.
- Connection-pool drain timeout.
- Kubernetes termination grace period.
- Database engine shutdown timeout.
- Replication/leadership transfer timeout.

Không dùng một timeout 5 giây chung cho tất cả. Đặc biệt, một write đã được source commit nhưng client bị ngắt trước response có trạng thái **outcome unknown**, không được retry mù quáng nếu có side effect.

### 11.3. Chuyển role trước khi stop

Trong leader/primary architectures, có thể dùng cơ chế step-down/leadership transfer **được engine hỗ trợ** để giảm disruption. Nó phải tuân thủ quorum/lag conditions; không cưỡng bức election khi các peers chưa sẵn sàng.

### 11.4. Flush không tương đương commit

Một số engines dùng WAL durability, checkpoints và memtable flush với semantics khác nhau. Không hứa “shutdown graceful = RPO 0 trong mọi failure mode”.

### 11.5. Sau stop

Theo dõi cluster trong thời gian quan sát đủ dài: role election, replica lag, routing, errors, p99 và disk/network. Một node stop thành công nhưng peer workload quá tải vẫn là thay đổi vận hành chưa đạt mục tiêu.

---

## 12. Forced stop và crash recovery

### 12.1. Các trường hợp không thể drain

- Process không phản hồi.
- Host mất điện.
- Disk/controller failure.
- Network partition.
- Bị OOM kill.
- VM/Pod bị cưỡng bức thu hồi.

Lúc đó cần **recovery runbook**, không coi process dừng “sạch”.

### 12.2. WAL/journal replay

Sau restart, storage engine có thể dùng log và checkpoint để phục hồi những dữ liệu đã được commit theo durability contract.

### 12.3. Unknown write outcome

Một request:

~~~text
Client -> node: write transaction K
Node commits write
Node crashes before ACK reaches client
Client observes timeout
~~~

Client không được suy “write chắc chắn thất bại” và tạo một business operation mới không có idempotency key.

### 12.4. Tránh restart storm

Nếu liveness quá nhạy, process liên tục crash/restart trong lúc đang replay recovery. Mỗi lần restart có thể kéo dài RTO và tăng I/O trên peers.

### 12.5. Không xóa log để start nhanh

Xóa WAL/commit log/oplog/SSTables thủ công có thể làm mất dữ liệu hoặc recovery point. Chỉ sử dụng công cụ/procedure được engine hỗ trợ theo sự cho phép của DBA/SRE.

---

## 13. Rolling restart: nguyên tắc “mỗi lần một nhóm an toàn”

Một cụm có đủ redundancy có thể cập nhật từng node thay vì dừng tất cả cùng lúc.

### 13.1. Trước mỗi nút

1. Kiểm cluster healthy theo operation contract.
2. Không có mất quorum/replica đang thiếu cần thiết.
3. Không có maintenance khác ở cùng failure domain.
4. Xác định vai trò target và impact khi mất target.
5. Kiểm capacity phục vụ trên phần còn lại.
6. Kiểm rollback và data format compatibility.

### 13.2. Mỗi vòng

~~~text
Check gates -> Drain target -> Stop -> Start
            -> Join -> Recover -> Ready -> Observe
            -> Proceed to next node
~~~

### 13.3. Không “một nút/lần” một cách mù quáng

Nếu một shard có đúng hai copies và một copy đã hỏng, dừng copy còn lại là nguy hiểm dù technically chỉ dừng một node. Safety gate phải dựa trên **placement và replica health thực tế**.

### 13.4. Không đổi đồng thời tất cả voter nodes

Đối với consensus clusters, việc stop quá nhiều voting members có thể mất khả năng elect leader/commit writes.

### 13.5. Khi nào hoãn vòng tiếp?

Nếu replica lag chưa giảm, node chưa nhận ownership đầy đủ, write p99 không đạt SLO hoặc cluster còn thiếu shard copies, **không chuyển sang nút kế tiếp**.

---

## 14. Ví dụ lập ngân sách duy trì availability

Giả sử một nhóm replica có RF=3, ứng dụng yêu cầu 2 replica phản hồi theo protocol cụ thể.

~~~text
Replica A: healthy
Replica B: healthy
Replica C: healthy
~~~

Nếu dừng A để restart, B+C có thể vẫn đáp ứng yêu cầu hai replicas trong giả định networking/placement phù hợp.

Nhưng khi A chưa bắt kịp, lại dừng B:

~~~text
Replica A: recovering
Replica B: down
Replica C: healthy
~~~

Chỉ một replica có thể tham gia. Dù A process alive, không chắc writes/reads theo consistency policy còn đáp ứng.

### 14.1. Cần kiểm theo data range

Một node có nhiều partitions với replica placements khác nhau. Công thức chỉ dựa trên tổng số nodes có thể bỏ sót keyspace bị thiếu.

### 14.2. `R+W>N` không tự chứng minh linearizability

Quorum overlap là một thành phần của nhiều thiết kế nhất quán; cần thêm protocol xử lý writes/read versions, membership và commit semantics.

### 14.3. Cho phép graceful degraded hay không?

Một số nghiệp vụ chấp nhận stale reads/temporary write unavailability; một số không. Runbook phải dựa trên SLO/consistency policy, không tự hạ bảo đảm vì cần hoàn tất maintenance.

---

## 15. Cassandra: `UP`, `NORMAL` và thực tế phục vụ

Trong Cassandra, các lệnh `nodetool` giúp nhìn membership/ownership, nhưng cần đọc theo phiên bản và topology.

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
nodetool tpstats
~~~

Các lệnh minh họa để chẩn đoán; cấu trúc output và quyền phụ thuộc deployment.

### 15.1. Ký hiệu trong `nodetool status`

Thông thường hiển thị hai loại ký hiệu cạnh nhau:

- Trạng thái sống: `U` (Up), `D` (Down).
- Trạng thái membership: `N` (Normal), `J` (Joining), `L` (Leaving), `M` (Moving) tùy phiên bản/protocol.

Ví dụ:

~~~text
UN  10.0.0.11  ...
UJ  10.0.0.12  ...
DN  10.0.0.13  ...
~~~

`UN` là Up/Normal theo gossip, **không chứng minh** mọi read/write tại tất cả consistency levels đều thành công hay mọi replica đã sửa xong dữ liệu.

### 15.2. Joining và bootstrap

`UJ` báo node đang join; data streaming/ownership thay đổi có thể vẫn diễn ra. Không đưa node vào một workload nặng trước khi xác nhận trạng thái đã đúng theo runbook.

### 15.3. Netstats và streaming

`nodetool netstats` giúp quan sát bootstrap/repair/streaming hoạt động. Kiểm thông lượng, pending streams và source nodes đang chịu tải.

### 15.4. Các trạng thái cần xét thêm

- Gossip reachability và schema agreement.
- Pending compaction/flush.
- Read/write latencies và dropped messages.
- Disk pressure.
- Replication consistency.
- TLS internode/client status.
- Repair/snapshot health.

### 15.5. `nodetool drain`

Cassandra có lệnh `nodetool drain` chuẩn bị dừng node bằng ngừng nhận một số writes và flush memtables theo semantics của engine. Sau drain, không coi node còn eligible để nhận writes bình thường; dùng đúng procedure stop/start của Cassandra version.

### 15.6. `nodetool decommission`

Decommission rút node khỏi ring và stream ownership phù hợp. **Không dùng decommission thay drain** khi mục đích chỉ là rolling restart.

### 15.7. Node offline lâu

Nếu một Cassandra node offline vượt các giới hạn tombstone/repair an toàn, không đơn giản start lại và cho nó nhập dữ liệu cũ; có thể cần replace/rebuild theo repair/runbook để tránh zombie data.

---

## 16. Cassandra: read/write readiness theo consistency level

Một node `UN` vẫn có thể không phục vụ được thao tác vì:

- Nó không có replica cho partition được truy vấn.
- Required replicas không đủ.
- Một replica ở remote DC unavailable.
- Compaction/disk/GC gây request timeout.
- Client native port chưa cấu hình đúng.
- Authentication/TLS hoặc schema khác.
- Coordinator có thể nhận request nhưng không hoàn thành consistency requirement.

### 16.1. Health ở coordinator khác replica state

Client kết nối vào một coordinator còn khỏe; coordinator có thể phải liên lạc các replicas khác. TCP connection tới coordinator thành công **không chứng minh operation hoàn tất**.

### 16.2. `LOCAL_QUORUM` là theo local DC

Thấy ba nodes còn sống toàn cluster không đủ nếu hai nodes ở DC khác và local DC chỉ có một replica cần thiết.

### 16.3. Không làm test bằng `SELECT` toàn bảng

Readiness probe nên nhẹ, bounded và không gây scans/compaction stress. Query phải đúng partition key và có deadline.

### 16.4. Benchmark sau restart

Sau bootstrap, SSTables/page caches lạnh và repair có thể làm p99 cao. Đo sustained performance trước khi tuyên bố đã phục hồi toàn diện.

---

## 17. MongoDB replica set: PRIMARY, SECONDARY và RECOVERING

MongoDB replica set có vai trò/trạng thái cụ thể. Một số công cụ:

~~~javascript
rs.status()
db.hello()
db.serverStatus()
~~~

Một `hello` response có thể mô tả server role và khả năng phục vụ theo driver protocol; `rs.status()` cung cấp trạng thái các members cho việc vận hành.

### 17.1. PRIMARY

Primary thường nhận writes của replica set và các strong/read preference mặc định phù hợp. Nhưng readiness ghi còn phụ thuộc write concern, majority availability, disk, authentication và transactions.

### 17.2. SECONDARY

Secondary đang replicate/applied log; có thể phục vụ reads khi client chọn read preference hỗ trợ, nhưng có khả năng **staleness**. Secondary không mặc định nhận writes như primary.

### 17.3. STARTUP, STARTUP2, RECOVERING

Node có thể đang khởi tạo, initial sync hoặc phục hồi; process/TCP healthy không đồng nghĩa eligible writes/reads.

### 17.4. ROLLBACK hoặc resync

Nếu xảy ra diverged history sau failover, node có thể rollback/khôi phục state. Không routing reads cần freshness nghiêm ngặt chỉ vì TCP port mở.

### 17.5. ARBITER

Arbiter có thể tham gia voting theo cấu hình nhưng **không giữ bản sao dữ liệu**. Không đếm arbiter như một data-bearing replica đủ để phục vụ reads/writes.

### 17.6. Majority election

Nếu primary step-down, client sẽ gặp một khoảng thời gian election/server selection; driver cần retry/backoff đúng loại thao tác. Một process mongo có thể vẫn sống nhưng không phải primary.

### 17.7. Oplog window

Secondary offline quá lâu có thể không còn oplog history để catch up và cần initial sync. Đừng cho node phục vụ từ dữ liệu cũ mà bỏ qua trạng thái recovery.

---

## 18. MongoDB: read/write readiness phải theo client contract

Một ví dụ:

~~~text
Primary: healthy
Secondary A: lag 2 seconds
Secondary B: lag 90 minutes
Client readPreference: secondaryPreferred
```

Nếu ứng dụng có SLO read freshness dưới 5 giây, Secondary B không nên được coi như nguồn đọc đủ điều kiện chỉ vì role `SECONDARY`.

### 18.1. Các tín hiệu

- Primary/secondary state.
- Election term và topology changes.
- Replication lag theo member.
- Majority availability và write concern.
- Storage recovery/index readiness.
- WiredTiger cache/IO pressure.
- Read preference, read concern, session semantics.

### 18.2. Driver server selection

MongoDB Java driver có topology discovery và server selection. Cần kiểm application error rates như server selection timeout, retryable reads/writes và unknown write outcome.

### 18.3. Không failover bằng cách dừng primary vô kế hoạch

Một thao tác `stepDown`/maintenance có thể ảnh hưởng toàn cụm. Chỉ thực hiện khi candidate secondary đủ điều kiện và election/majority safety được xác nhận.

### 18.4. Canaries

Một read canary có consistency phù hợp và hạn chế side effects giúp kiểm end-to-end; nó không thay replica status/lag metrics.

---

## 19. Redis: standalone, Sentinel và Cluster có trạng thái khác nhau

### 19.1. Standalone Redis

`PING` trả `PONG` cho biết một connection đã đến Redis và server có thể phản hồi command đó. Nó không chứng minh persistence đang tốt, memory còn chỗ, replication đủ hoặc application keyspace đầy đủ.

### 19.2. Sentinel

Redis Sentinel giám sát primary/replicas và điều phối failover theo quy tắc. Kiểm discovery của client, primary được Sentinel công nhận, replicas, replica lag và replication links.

### 19.3. Redis Cluster

Redis Cluster phân phối hash slots và có roles masters/replicas. Công cụ quan sát:

~~~text
INFO replication
CLUSTER INFO
CLUSTER NODES
CLUSTER SHARDS
```

Lệnh `CLUSTER SHARDS` có ở những phiên bản Redis hỗ trợ; cần xem version.

### 19.4. `cluster_state:ok` nói gì?

Một tín hiệu cluster-state bình thường theo rule của Redis Cluster, nhưng **không tự chứng minh** mọi cache key còn nguyên, những writes trước failover đã bền hoặc client có thể resolve đúng redirect.

### 19.5. Hash slots

Client có thể nhận `MOVED` hoặc `ASK` trong reconfiguration. Nếu một slot/owner unavailable, một phần keys có thể lỗi dù các nodes khác vẫn trả `PONG`.

### 19.6. Redis Cluster topology change

Khi node rời/được thay, failover hoặc resharding cần quản lý slot ownership; dừng master khi replica chưa đủ điều kiện có thể làm mất availability cho slots.

### 19.7. Replication không đồng nghĩa durability tuyệt đối

Redis replication phổ biến có tính bất đồng bộ. Sau failover, một số writes ACK trên primary cũ có thể chưa tới replica mới; không dùng `PING`, `ROLE` hay Sentinel promotion để suy RPO=0.

---

## 20. Redis: graceful stop và ứng dụng phụ thuộc cache

Một Redis instance có thể giữ:

~~~text
product:*        -> derived cache
session:*        -> session state
ratelimit:*      -> security counters
idempotency:*    -> deduplication data
queue:*          -> pending work
```

Nếu restart làm mất keys do persistence policy, tác động của từng namespace khác nhau.

### 20.1. Cache derived

Cold cache có thể tăng tải NoSQL source hàng chục lần; cần admission control và cache warm-up.

### 20.2. State duy nhất

Nếu session, rate-limit, idempotency hoặc queue chỉ có ở Redis, một stop/crash/restore không an toàn có thể là mất dữ liệu nghiệp vụ hoặc bảo mật, không còn là “restart cache vô hại”.

### 20.3. Lệnh tắt

Redis có shutdown behavior, save/persistence options và service-manager integration theo deployment; không dùng tùy tiện các lệnh bỏ qua persistence để khởi động nhanh. Phải hiểu RDB/AOF/replication/RPO.

### 20.4. Cache nóng lại không đồng nghĩa cụm đã an toàn

Redis `PONG` và hit rate tăng chưa xác nhận idempotency ledger, revoked tokens và pending jobs còn đúng. Cần đối soát business state.

---

## 21. Elasticsearch/OpenSearch: node lên nhưng shards chưa phục vụ đủ

Trong Elasticsearch/OpenSearch, node khởi động rồi join cluster; data shards có thể cần recovery/relocation trước khi các indexes đủ điều kiện.

Một số API quan sát:

~~~text
GET /_cluster/health
GET /_cat/nodes?v
GET /_cat/shards?v
GET /_cat/recovery?v
GET /_cluster/allocation/explain
```

Endpoint/field chi tiết tùy version.

### 21.1. `green`, `yellow`, `red`

- **Green:** primary và replica shards được phân bổ theo cluster health semantics.
- **Yellow:** primary shards được phân bổ nhưng một số replica shards chưa sẵn sàng.
- **Red:** có primary shard không được phân bổ.

Không đánh đồng Yellow với “mọi truy vấn đều thất bại”: nhiều queries vẫn có thể phục vụ nhưng redundancy giảm. Red cũng có thể ảnh hưởng **một phần indexes**, không phải mọi request đến cluster đều lỗi.

### 21.2. Cluster-manager health và data-node health

Cluster-manager election, cluster metadata và shard allocation ảnh hưởng ability to route/recover. Một data node có process khỏe nhưng không có shards ready hoặc chưa join không được coi là service-ready theo index target.

### 21.3. Disk watermarks

Disk gần đầy có thể ngăn shard allocation hoặc gây write restrictions theo engine/config. Health status và filesystem metrics phải xem cùng nhau.

### 21.4. Search vs indexing

Một node có thể phục vụ search trên primary shards nhưng write/indexing path đang throttled hoặc bị block. Thử đúng operation class.

### 21.5. Không ép force merge hoặc shard relocate để chữa mọi readiness failure

Các thao tác đó tốn I/O, disk/network; phải xác định nguyên nhân recovery/allocation và có runbook. Một node restart có thể cần thời gian recover shards mà không phải lỗi cần can thiệp phá dữ liệu.

---

## 22. Couchbase: process, service, bucket và rebalance

Couchbase có thể chạy nhiều services: Data/KV, Query, Index, Search, Analytics, v.v. Một node tham gia cluster **không tự đảm bảo mọi service trên node đã phục vụ được**.

### 22.1. Membership và service role

Kiểm đúng services được gán cho node, cluster state và khả năng routing tới bucket/index tương ứng.

### 22.2. Warm-up

Data service có thể cần warm-up caches/indexes từ storage; ứng dụng có thể gặp latency hoặc service availability khác nhau trong lúc warm-up theo version/architecture.

### 22.3. Rebalance

Add/remove node có thể yêu cầu rebalance. Chỉ dừng process không thực hiện mọi công việc chuyển ownership/replicas.

### 22.4. Failover

Một số topology/protocol cho phép failover và sau đó rebalance/recovery. Tình trạng node `healthy` phải đi cùng vBucket/replica placement.

### 22.5. Quan sát

Có thể dùng Couchbase management UI, SDK diagnostics/ping, node/service metrics và CLI/REST theo version; cần kiểm data/replica service readiness, không chỉ web management port.

---

## 23. Managed NoSQL: khác phạm vi vận hành

Với **Amazon DynamoDB**, người dùng không trực tiếp start/stop storage nodes nội bộ. Điều có thể quan sát/quản lý là:

- Table lifecycle như `CREATING`, `ACTIVE`, `UPDATING`, `DELETING` theo API.
- GSI creation/backfill trạng thái phù hợp.
- Request success/latency/throttling.
- Region, endpoint, IAM/TLS.
- Global tables replication state/lag theo mode.
- Backup/export/restore status.

### 23.1. Table ACTIVE không thay end-to-end health

Table active có thể vẫn gặp hot partitions, throttling, IAM denied, SDK timeout hoặc GSI eventual lag.

### 23.2. Không sáng tác nút lưu trữ nội bộ

Không viết runbook `systemctl restart dynamodb-node` vì khách hàng không có quyền vận hành hạ tầng managed như self-hosted cluster.

### 23.3. Managed cache vẫn có node/failover riêng

Các dịch vụ managed Redis-like hoặc search service có những controls và operations riêng; khả năng client retry/routing và restore RPO vẫn cần kiểm contract.

---

## 24. Kubernetes: process/container Running khác Pod Ready

Một StatefulSet chứa database có thể báo:

~~~text
Pod phase: Running
Container state: Running
Readiness: False
Startup probe: in progress
Storage replay: 75%
```

Đây có thể là **trạng thái bình thường** trong quá trình khôi phục.

### 24.1. Startup probe

Cho phép quá trình bootstrap dài hơn trước khi áp liveness policy, tránh liveness restart process giữa replay.

### 24.2. Readiness probe

Quyết định Pod có là endpoint phục vụ trong Service theo chính sách hay không. Nút database cần tránh nhận traffic không phù hợp khi đang recovery. Nhưng cần nhớ driver có thể sử dụng **direct node addresses** ngoài Kubernetes Service, nên readiness ở Service không tự chặn mọi client.

### 24.3. Liveness probe

Nên nhắm tới process bị kẹt **không tự phục hồi**. Không bắt buộc `liveness = overall cluster healthy`, nếu không một network partition có thể khiến toàn bộ replicas tự restart đồng thời.

### 24.4. Termination grace

`terminationGracePeriodSeconds` cần đủ cho signal/drain/recovery expectation phù hợp; cài quá ngắn có thể làm process bị kill trước khi hoàn thành shutdown path.

### 24.5. preStop hook

Có thể dùng hook để phối hợp drain/endpoint removal, nhưng Kubernetes termination có deadline tổng và hook cũng có thể bị ngắt. Không thiết kế an toàn dữ liệu chỉ dựa vào `sleep 20` trong preStop.

### 24.6. PodDisruptionBudget

PDB giúp quản lý một số **voluntary disruptions** qua eviction policy, nhưng không cứu node khỏi crash, OOM hoặc host failure; cũng không tự hiểu topology quorum của database.

### 24.7. Stateful identity/PersistentVolume

StatefulSet, PVC/PV mapping và node identity rất quan trọng. Pod mới gắn nhầm volume cũ hoặc xóa PVC để “sửa startup” có thể gây data corruption/loss. Chỉ thao tác storage theo playbook được phê duyệt.

---

## 25. Kubernetes YAML minh họa probe separation

Một đoạn cấu hình **mang tính định hướng**, không phải YAML cài đặt chạy được cho mọi NoSQL:

~~~yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: nosql-node
spec:
  serviceName: nosql-headless
  replicas: 3
  selector:
    matchLabels:
      app: nosql-node
  template:
    metadata:
      labels:
        app: nosql-node
    spec:
      terminationGracePeriodSeconds: 120
      containers:
        - name: nosql
          image: example.invalid/nosql:approved-version
          ports:
            - containerPort: 9042
          startupProbe:
            exec:
              command:
                - /bin/sh
                - -c
                - /opt/ops/startup-check
            failureThreshold: 60
            periodSeconds: 5
          readinessProbe:
            exec:
              command:
                - /bin/sh
                - -c
                - /opt/ops/readiness-check
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            exec:
              command:
                - /bin/sh
                - -c
                - /opt/ops/liveness-check
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 6
~~~

### 25.1. Các script không được giả lập

`/opt/ops/*-check` là placeholder. Trong production phải triển khai dựa trên database version, protocol, topology và security context; không lấy script chỉ `exit 0` làm health check.

### 25.2. Không đặt command nặng trong probe

Không dùng full table scan, `nodetool repair`, rebuild index hoặc truy vấn đắt mỗi 5 giây. Probes chạy trên nhiều nodes sẽ tạo một lượng tải đáng kể.

### 25.3. Readiness quá chặt cũng gây cascading failure

Nếu readiness đòi mọi peer healthy, một peer rớt có thể làm **tất cả Pod Ready=False**, mặc dù đa số có thể phục vụ. Dùng tiêu chí đúng operation contract, tránh điều kiện phụ thuộc vòng.

### 25.4. Readiness quá lỏng cũng nguy hiểm

TCP port mở lúc node còn `JOINING` có thể đưa requests vào khi nó chưa có shard ownership ổn định.

---

## 26. VM/systemd: giám sát đúng service và actual protocol

Trên VM, các công cụ khái quát:

~~~bash
systemctl status nosql-service
systemctl is-active nosql-service
journalctl -u nosql-service --since "15 minutes ago"
ss -ltn
~~~

Tên `nosql-service` là placeholder. Những lệnh này **chỉ mô tả service/process và sockets**, không thay database-native health checks.

### 26.1. Dùng supervisor nhất quán

Không chạy thêm một instance thủ công nếu systemd/container supervisor đã quản lý data directory; double process có thể gây file lock hoặc corruption.

### 26.2. Log có ích nhưng phải tránh secret

TLS/private key/database credentials không được in ra logs. Debug chỉ bật trong thời gian/đối tượng được phê duyệt.

### 26.3. Cổng mở không đủ

Kết nối TCP thành công không chứng minh node đã join đúng cluster, có shard ownership hoặc đủ quorum.

---

## 27. Thiết kế health-check theo operation class

Một schema gợi ý:

~~~text
HealthSnapshot:
  nodeProcess
  transportTls
  membership
  role
  recovering
  replicationLag
  ownsTargetData
  readEligible
  writeEligible
  clusterQuorum
  capacitySafe
  timestamp
  reasons
```

### 27.1. Read probe

Có thể dùng point read đối với một **sentinel record** đã biết, ở partition/dataset test phù hợp, tránh PII. Tuy nhiên một điểm đọc thành công không chứng minh mọi partitions đều phục vụ được.

### 27.2. Write probe

Một write probe có side effect cần thiết kế an toàn: namespace chuyên dụng, TTL/cleanup, bounded rate, unique IDs, idempotency và tránh phá consistency. Không tạo write canary vào dữ liệu nghiệp vụ thật tùy tiện.

### 27.3. Server status API có ích

Engine-native status là nguồn quan trọng để biết role/lag/topology. Không chỉ dùng canary rồi bỏ qua election/quorum metrics.

### 27.4. Health có độ trễ

Mọi snapshot đều có timestamp; node có thể thay đổi vai trò ngay sau khi probe thành công. Client operations vẫn cần deadline, retry/idempotency và xử lý topology changes.

### 27.5. Phân biệt `UNKNOWN` và `HEALTHY`

Nếu không đọc được metric replication lag, không được ghi `lag=0` hay “healthy”. Dùng trạng thái `UNKNOWN` và policy bảo thủ với operation critical.

---

## 28. Java: mô hình trạng thái có giải thích lý do

Ví dụ Java 17 sau là **lớp chính sách minh họa** để biểu diễn readiness, không thay phép kiểm thật của từng NoSQL driver.

~~~java
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class NodeReadinessPolicy {

    public enum Phase {
        STARTING, JOINING, RECOVERING,
        SERVING, DRAINING, STOPPED, FAILED
    }

    public enum Role {
        PRIMARY, SECONDARY, COORDINATOR,
        DATA_NODE, UNKNOWN
    }

    public enum Decision {
        READY, NOT_READY, UNKNOWN
    }

    public record Snapshot(
        String nodeId,
        Phase phase,
        Role role,
        boolean transportAuthenticated,
        boolean clusterMember,
        boolean dataRecovered,
        boolean eligibleForRead,
        boolean eligibleForWrite,
        boolean quorumSatisfiedForWrite,
        boolean capacitySafe,
        Duration replicationLag,
        boolean replicationLagKnown
    ) {
        public Snapshot {
            Objects.requireNonNull(nodeId);
            Objects.requireNonNull(phase);
            Objects.requireNonNull(role);
        }
    }

    public record Result(
        Decision decision,
        List<String> reasons
    ) {
        public Result {
            reasons = List.copyOf(reasons);
        }
    }

    // Ví dụ policy: 5s là ngưỡng của ứng dụng demo.
    // Không áp mặc định cho mọi Cassandra/MongoDB/Redis.
    private static final Duration MAX_READ_LAG =
        Duration.ofSeconds(5);

    public Result readReady(Snapshot state) {
        List<String> reasons = baseReasons(state);

        if (!state.eligibleForRead()) {
            reasons.add("NOT_READ_ELIGIBLE");
        }

        if (!state.replicationLagKnown()) {
            reasons.add("REPLICATION_LAG_UNKNOWN");
            return new Result(Decision.UNKNOWN, reasons);
        }

        if (state.replicationLag() == null ||
                state.replicationLag().isNegative()) {
            reasons.add("INVALID_REPLICATION_LAG");
            return new Result(Decision.UNKNOWN, reasons);
        }

        if (state.replicationLag().compareTo(MAX_READ_LAG) > 0) {
            reasons.add("REPLICATION_LAG_TOO_HIGH");
        }

        return new Result(
            reasons.isEmpty() ? Decision.READY
                              : Decision.NOT_READY,
            reasons
        );
    }

    public Result writeReady(Snapshot state) {
        List<String> reasons = baseReasons(state);

        if (!state.eligibleForWrite()) {
            reasons.add("NOT_WRITE_ELIGIBLE");
        }

        if (!state.quorumSatisfiedForWrite()) {
            reasons.add("WRITE_QUORUM_NOT_SATISFIED");
        }

        return new Result(
            reasons.isEmpty() ? Decision.READY
                              : Decision.NOT_READY,
            reasons
        );
    }

    private List<String> baseReasons(Snapshot state) {
        List<String> reasons = new ArrayList<>();

        if (state.phase() != Phase.SERVING) {
            reasons.add("PHASE_" + state.phase());
        }
        if (!state.transportAuthenticated()) {
            reasons.add("TRANSPORT_NOT_AUTHENTICATED");
        }
        if (!state.clusterMember()) {
            reasons.add("NOT_IN_EXPECTED_CLUSTER");
        }
        if (!state.dataRecovered()) {
            reasons.add("RECOVERY_INCOMPLETE");
        }
        if (!state.capacitySafe()) {
            reasons.add("CAPACITY_UNSAFE");
        }

        return reasons;
    }
}
~~~

### 28.1. Vì sao trả `reasons`?

Một boolean `ready=false` không giải thích nên sửa TLS, đợi recovery, sửa membership hay tăng capacity. Structured reasons giúp metrics/runbooks hữu ích.

### 28.2. `UNKNOWN` quan trọng

Trong code, khi lag không đo được, chính sách đọc trả `UNKNOWN` thay vì mặc định `READY`. Production có thể phân loại riêng unavailable/missing metrics và phải có alert phù hợp.

### 28.3. Vai trò chỉ là metadata

Ở ví dụ, `Role` không tự quyết định read/write; **adapter theo từng engine** phải xác định `eligibleForRead/Write` đúng theo consistency/read preference/placement.

### 28.4. Ngưỡng lag không áp dụng đồng loạt

Mức 5 giây minh họa một eventual-read contract, không dùng để xác nhận linearizable read hoặc financial transaction.

### 28.5. Snapshot có thể stale

Ngay sau khi policy trả `READY`, node có thể step-down. Client luôn phải xử lý server selection, retries và unknown outcome đúng cách.

---

## 29. Java JUnit 5: các tình huống readiness cơ bản

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import org.junit.jupiter.api.Test;

public class NodeReadinessPolicyTest {

    private final NodeReadinessPolicy policy =
        new NodeReadinessPolicy();

    private NodeReadinessPolicy.Snapshot snapshot(
            NodeReadinessPolicy.Phase phase,
            boolean writeQuorum,
            Duration lag) {

        return new NodeReadinessPolicy.Snapshot(
            "db-2",
            phase,
            NodeReadinessPolicy.Role.SECONDARY,
            true,  // TLS/authenticated
            true,  // cluster member
            true,  // recovery completed
            true,  // read eligible
            false, // secondary not writable in this demo
            writeQuorum,
            true,  // capacity safe
            lag,
            true   // lag known
        );
    }

    @Test
    void transportAliveButRecoveringIsNotReady() {
        var state = snapshot(
            NodeReadinessPolicy.Phase.RECOVERING,
            true,
            Duration.ofSeconds(1)
        );

        assertEquals(
            NodeReadinessPolicy.Decision.NOT_READY,
            policy.readReady(state).decision()
        );
    }

    @Test
    void readEligibleSecondaryCanBeReadReady() {
        var state = snapshot(
            NodeReadinessPolicy.Phase.SERVING,
            true,
            Duration.ofSeconds(2)
        );

        assertEquals(
            NodeReadinessPolicy.Decision.READY,
            policy.readReady(state).decision()
        );
        assertEquals(
            NodeReadinessPolicy.Decision.NOT_READY,
            policy.writeReady(state).decision()
        );
    }

    @Test
    void replicationLagBlocksFreshnessSensitiveRead() {
        var state = snapshot(
            NodeReadinessPolicy.Phase.SERVING,
            true,
            Duration.ofMinutes(2)
        );

        assertEquals(
            NodeReadinessPolicy.Decision.NOT_READY,
            policy.readReady(state).decision()
        );
    }

    @Test
    void missingLagMeasurementIsNotHealthy() {
        var state = new NodeReadinessPolicy.Snapshot(
            "db-2",
            NodeReadinessPolicy.Phase.SERVING,
            NodeReadinessPolicy.Role.SECONDARY,
            true, true, true, true, false,
            true, true, null, false
        );

        assertEquals(
            NodeReadinessPolicy.Decision.UNKNOWN,
            policy.readReady(state).decision()
        );
    }

    @Test
    void drainingNodeMustNotReceiveNewWork() {
        var state = snapshot(
            NodeReadinessPolicy.Phase.DRAINING,
            true,
            Duration.ZERO
        );

        assertEquals(
            NodeReadinessPolicy.Decision.NOT_READY,
            policy.readReady(state).decision()
        );
    }
}
~~~

### 29.1. Test này kiểm điều gì?

Nó kiểm mô hình policy của Java, **không kiểm** driver Cassandra/MongoDB/Redis đã báo đúng role hoặc lag. Integration tests phải nối vào server/cluster test environment và quan sát lỗi thật.

### 29.2. Không dùng kết quả test làm bằng chứng phân tán

Unit test không chứng minh cluster đạt quorum, election safety, consistency hoặc không mất ACKed writes sau crash.

---

## 30. Đo readiness ở ứng dụng Java

Một service Java có thể cần hai loại health khác nhau:

1. **Process/application readiness:** có thể nhận HTTP requests và xử lý những dependency cần thiết theo API contract.
2. **Database client readiness:** có thể chọn server, xác thực, truy vấn đúng consistency/read preference và nhận kết quả trong deadline.

### 30.1. Không dùng DB read nặng cho mỗi HTTP readiness request

Nếu có 500 app instances và mỗi instance kiểm DB mỗi giây bằng query đắt, health system trở thành workload đáng kể và có thể gây sự cố thứ hai.

### 30.2. Caching health snapshot

Có thể lấy database-native health theo nhịp có giới hạn rồi phục vụ readiness nhanh từ snapshot với TTL ngắn. Nhưng nếu snapshot hết hạn, phải báo UNKNOWN/NOT_READY theo policy; không duy trì “green” vô hạn từ trạng thái cũ.

### 30.3. Đừng biến toàn bộ app liveness thành DB health

Nếu database tạm unavailable, restart tất cả Java apps có thể tạo connection storm. Liveness nên hỏi process còn khả năng chạy không; readiness và circuit breaker chịu trách nhiệm điều chỉnh traffic.

### 30.4. Driver pool

Connection pool còn vài connections nhưng không chọn được writable server có thể gây timeout. Đo pool acquisition wait, server selection latency, topology changes và retry attempts.

### 30.5. Canary operation và permissions

Canary account nên có quyền tối thiểu, không dùng admin credentials; nếu cần write canary, hãy thiết kế idempotency/cleanup và đặt deadline.

---

## 31. Driver topology: client có thể biết khác với node

Một database node có thể đã được promote nhưng Java driver vẫn giữ topology cache cũ trong thời gian ngắn.

### 31.1. DNS/advertised address

Node gửi advertised IP/hostname không reachable từ Java workload khiến client connection thất bại dù server cổng nội bộ đã mở.

### 31.2. TLS identity

Client kết nối tới discovered node address nhưng SAN của certificate không phù hợp: handshake fail. Không tắt hostname verification để hoàn tất rolling restart.

### 31.3. Failover

Sau primary election hoặc slot/shard movement, driver cần nhận topology updates và route theo role/ownership mới. Một API cần deadline/retry budget để sống qua khoảng chuyển tiếp.

### 31.4. Connection pooling

Pool connections cũ có thể lỗi khi node shutdown; client phải bỏ broken connections và không tự mở vô hạn connections mới.

### 31.5. Phân biệt client failure và node failure

Nếu chỉ một application deployment không kết nối được, còn những clients khác chạy bình thường, kiểm driver/version/truststore/DNS/ACL trước khi khởi động lại database node.

---

## 32. Startup bị chậm: những nhóm nguyên nhân phổ biến

| Hiện tượng | Nguyên nhân có thể | Tín hiệu giúp phân biệt |
|---|---|---|
| Process không lên | Config/permission/binary/storage lock | Service logs, exit code |
| Port không mở | Bind address/port conflict/startup chưa tới | Listener status, logs |
| TLS fail | Cert hết hạn, SAN mismatch, CA trust | Handshake diagnostic |
| Không join cluster | DNS/gossip/quorum/cluster ID | Membership/peer logs |
| Join nhưng không ready | Streaming/initial sync/recovery | Lag, recovery progress |
| Disk bận kéo dài | WAL replay/compaction/repair | IOPS, disk await |
| JVM repeatedly restarts | Heap/GC/OOM/probe timeout | GC logs, OOM events |
| Primary không được bầu | Voting quorum/candidate not eligible | Election state |
| Reads chậm sau start | Cold caches/index warmup | Cache hit, p99 |
| Nút lên sai dữ liệu | Wrong PV/volume/cluster ID | Storage identity, restore logs |
| Node không sở hữu shard | Routing/slot allocation issue | Shard/slot owner map |
| Nút không phục vụ writes | Read-only role, disk watermark, no quorum | Role, capacity metrics |
| Nút lâu không khỏi `JOINING` | Streaming issues/bandwidth/peer overload | Network, netstats |
| Chỉ vài clients fail | Driver DNS/TLS/topology cache | Client logs and endpoints |
| Nút xuống sau vài phút | Readiness/liveness loop hoặc health policy sai | Probe failures/events |

Không vội “xóa data directory để sạch sẽ”. Nguyên nhân là cluster identity hoặc lag thì xóa dữ liệu có thể biến một lỗi phục hồi được thành data loss.

---

## 33. Monitoring: nhìn cùng lúc node, cụm và ứng dụng

| Nhóm | Metric/biến quan sát | Ý nghĩa |
|---|---|---|
| Process | Uptime, restart count, exit code | Node vừa crash hay planned restart? |
| Startup | Time to listen/join/recover/ready | Xác định bottleneck boot |
| Membership | Joined members, failed peers | Health của topology |
| Role | Primary/secondary/leader/replica changes | Phát hiện election/failover |
| Replication | Lag, applied position, sync status | Freshness và khả năng bắt kịp |
| Ownership | Available shards/slots/ranges | Data coverage |
| Quorum | Voting availability / required replicas | Commit/read availability |
| Service | Read/write success, p95/p99, errors | User-visible impact |
| Routing | Server selection, redirects, retries | Driver thích nghi topology? |
| Storage | Disk free, IOPS, pending compaction | Resource constraints |
| Security | TLS handshake errors, cert expiry | Cluster access blockers |
| Kubernetes | Pod readiness/liveness/startup events | Orchestrator behavior |
| Recovery | Initial sync/rebalance/repair progress | ETA và backlog |
| Capacity | N+1 headroom, remaining replicas | Có an toàn khi stop node tiếp? |

### 33.1. Metrics phải phân biệt scheduled stop và crash

Một planned rolling restart cần change ID và maintenance annotation để tránh incident noise nhưng không được ẩn tình trạng mất quorum thực sự.

### 33.2. Không dùng ready count một mình

`3/3 nodes ready` chưa chứng minh p99 tốt, majority writes thành công, không có stale replicas hoặc data shards đầy đủ.

### 33.3. Per-node và per-shard

Average replication lag 2 giây có thể che một shard lag 20 phút. SLO đọc dựa trên worst affected key range.

### 33.4. Không tạo high-cardinality labels

Tránh đưa customer ID, document ID hoặc request ID không giới hạn vào Prometheus labels. Dùng node ID, role, DC, operation class, failure reason và bounded cohort.

---

## 34. Một bộ chỉ số readiness tổng hợp

Thay vì một “healthy bit”, vận hành có thể công bố:

~~~json
{
  "nodeId": "db-2",
  "phase": "RECOVERING",
  "processAlive": true,
  "transportAuthenticated": true,
  "memberOfExpectedCluster": true,
  "role": "SECONDARY",
  "readEligible": false,
  "writeEligible": false,
  "replicationLagSeconds": 145,
  "reasonCodes": [
    "REPLICATION_LAG_TOO_HIGH",
    "RECOVERY_NOT_COMPLETE"
  ]
}
~~~

Đây là schema minh họa, không phải output của engine.

### 34.1. Node-level and cluster-level fields

`writeEligible` cho một node và `clusterWriteAvailable` cho toàn cụm không nên gộp nếu client có thể route qua node khác.

### 34.2. Bổ sung thời điểm đo

Một status phải có `observedAt`/age. Không coi response đã cache 10 phút là bằng chứng current readiness.

### 34.3. Bảo vệ endpoint health

Không nên cho anonymous Internet clients đọc toàn bộ member IPs, cluster roles hoặc replication metadata. Internal monitoring cần access control.

### 34.4. Snapshot lỗi

Khi health collector không thể truy vấn engine, báo `UNKNOWN` thay vì dựng số 0 hoặc giữ trạng thái cũ vô hạn.

---

## 35. Phân tích một lần rolling restart sai

~~~text
Cluster: 3 voting data-bearing members
Node A: PRIMARY
Node B: SECONDARY, caught up
Node C: SECONDARY, behind 30 minutes
```

Người vận hành dừng B để bảo trì vì B không phải primary. Ngay sau đó A gặp host failure, chỉ còn C với dữ liệu lag cao.

### 35.1. Lỗi quyết định

“B là secondary nên dừng được” không đủ. Phải xét remaining voting/data-bearing topology và khả năng C bắt kịp, write concern, election candidacy và recovery RPO.

### 35.2. An toàn hơn

- Xác nhận C healthy/eligible và lag trong policy trước khi dừng B.
- Chỉ dừng một target sau khi quorum/replica-placement gates đạt.
- Theo dõi B khi quay lại đầy đủ trước bảo trì A/C.
- Có rollback khi replication lag tăng hoặc primary election mất ổn định.

### 35.3. Thêm ví dụ với shard cluster

Một cluster 12 nodes có thể đủ tổng replica count nhưng một shard chỉ còn một active copy. Dừng node chứa copy đó làm shard unavailable. Cần check theo shard/range, không chỉ tổng nodes.

---

## 36. Runbook A: rolling restart có kế hoạch

### Pha A — Preflight

1. Xác nhận change authorization và owner.
2. Ghi topology, roles, version, shard/replica placement.
3. Xác nhận cluster đáp ứng current read/write SLO.
4. Kiểm quorum/consistency requirements với target removed.
5. Kiểm source/target disk và recovery capacity.
6. Kiểm replication lag, pending streaming và repair.
7. Xác nhận backups/restore path, log history.
8. Xem TLS cert/secret/version compatibility.
9. Xác định target và cách rollback không xóa data.

### Pha B — Traffic drain

10. Đưa target khỏi new-traffic routing theo engine/driver.
11. Với primary/leader, dùng role transfer được engine hỗ trợ nếu phù hợp.
12. Đợi in-flight requests; áp timeout/idempotency policy.
13. Xác nhận peers đang nhận thêm tải vẫn dưới SLO.

### Pha C — Stop

14. Dùng engine/service-manager graceful shutdown.
15. Xác minh process thực sự dừng, storage không còn ghi.
16. Không xóa data volume hoặc metadata membership.
17. Theo dõi read/write availability trên cluster còn lại.

### Pha D — Start

18. Khởi động lại đúng identity, binary/config/PV.
19. Theo dõi recovery, join, sync, compaction/disk.
20. Kiểm TLS, authentication, topology, schema.
21. Đợi role/ownership và replica-lag policy đạt.
22. Chạy canary reads/writes được phê duyệt.
23. Mở traffic từng bước và đo p99/retries.

### Pha E — Gate trước node tiếp theo

24. Node đã được eligible theo policy?
25. Cluster không còn under-replicated/shard-missing ngoài phạm vi cho phép?
26. Quorum/write concern vẫn đạt?
27. Replication lag và queue về mức chấp nhận?
28. Error budget/p99 không bị ảnh hưởng bất thường?
29. Nếu chưa: **dừng vòng bảo trì**, xử lý blocker.
30. Nếu đạt: ghi lại evidence rồi mới sang nút tiếp theo.

---

## 37. Runbook B: node crash bất ngờ

### Bước 1 — Bảo vệ dữ liệu và traffic

- Kiểm current leader/primary/replicas và quorum.
- Giảm optional queries/backfill và retries không cần thiết.
- Ưu tiên writes/reads quan trọng trong capacity còn lại.
- Xác nhận client timeout và unknown write outcomes.

### Bước 2 — Xác minh loại crash

- Process crash, OOM, host power, disk failure hay network partition?
- Node thật sự down hay chỉ một monitoring path unreachable?
- Nó có bị fencing/isolation để tránh split-brain theo protocol không?

### Bước 3 — Xác nhận có thể restart trên storage cũ

- Data volume có nguyên vẹn?
- Cluster identity, node ID, token/slot ownership còn đúng?
- Tình trạng backup/log history có đủ?
- Node offline có vượt recovery/tombstone/oplog window không?

### Bước 4 — Chọn restart hay replace

Nếu storage/identity tốt và history đủ, engine có thể rejoin bằng recovery. Nếu disk mất hoặc replica quá cũ, dùng **replace/reseed/resnapshot** theo engine procedure.

### Bước 5 — Quan sát recovery

WAL/journal, initial sync, replica lag, shard allocation, disk pressure, TLS, process restarts và recovery logs.

### Bước 6 — Readiness gate

Không đưa node mới phục hồi vào full load cho tới khi eligibility và stability tests đạt.

### Bước 7 — Đối soát outcome

Kiểm acked writes, unknown commits, deleted records, lost cache state, consistency và việc client retry side effects.

---

## 38. Runbook C: toàn cụm restart hoặc mất điện

Một outage toàn cụm khác hẳn rolling restart.

### 38.1. Đừng khởi động ngẫu nhiên mọi bản sao

Một số engine có recovery order, quorum election hoặc persistent metadata phải thận trọng. Quy trình phải dựa trên engine/version và recovery state chứ không chỉ “start tất cả service cùng lúc”.

### 38.2. Xác định nguồn có thẩm quyền

- Node nào có commit history mới nhất?
- Snapshots/backups nào có thể restore?
- WAL/oplog/commit logs còn không?
- Quorum/consensus metadata thế nào?
- Có split-brain/double primary risk không?
- Có region khác còn serving không?

### 38.3. Recovery phải theo protocol engine

MongoDB majority elections, Cassandra ring/bootstrap, Redis promotion, Elasticsearch cluster-manager/shard recovery và managed services có thủ tục riêng. Không “force promote” bằng thao tác tự chế.

### 38.4. Chỉ mở traffic sau các mốc

1. Control plane/member election ổn định.
2. Data ownership/replica availability được xác nhận.
3. Committed source state đủ theo RPO.
4. Tối thiểu read/write contract đạt.
5. App drivers đã refresh topology.
6. Warm-up/compaction không phá nguồn.
7. Security/certificates hợp lệ.

### 38.5. Restore có thể hồi sinh dữ liệu đã xóa

Nếu restore từ backup cũ, phải replay deletion events/tombstones theo protocol trước khi phục vụ, đặc biệt với dữ liệu cá nhân hoặc revocation.

---

## 39. Nguyên tắc chọn restart, wait hay stop tiếp

| Tình trạng | Phản ứng mặc định |
|---|---|
| Process DOWN, peers healthy và target storage nguyên vẹn | Chẩn đoán rồi restart theo runbook |
| Process UP, startup/recovery đang tiến triển | Đợi và theo dõi; không restart loop |
| Process UP, join bị lỗi truststore/cluster ID | Sửa identity/config, không bypass security |
| Replica lag cao | Không routing freshness-critical reads; chờ catch-up hoặc rebuild |
| Cluster thiếu quorum | Hoãn planned node stops, khôi phục quorum theo protocol |
| Disk gần đầy | Bảo vệ capacity, không khởi động compaction/rebuild mù quáng |
| One shard không có active copy | Kiểm allocation/replication; không claim cluster fully ready |
| Node `DRAINING` quá lâu | Kiểm in-flight/recovery, deadline; không kill tùy tiện |
| Client không connect nhưng native node health tốt | Kiểm DNS/TLS/driver topology/ACL |
| Node offline vượt tombstone/oplog retention | Re-seed/resnapshot, không incremental join tùy tiện |
| Backup restore đang chạy | Không đưa traffic sớm, đợi source correctness validation |
| Cluster healthy sau vòng restart | Ghi evidence; sang vòng tiếp nếu gates còn đạt |

---

## 40. Ma trận fault-injection cho vòng đời nút

| ID | Tình huống | Điều cần chứng minh |
|---|---|---|
| N01 | Process start, TCP chưa mở | Startup vẫn có thời gian hợp lệ |
| N02 | TCP mở, membership chưa join | Readiness false |
| N03 | TLS certificate sai SAN | Từ chối peer sai |
| N04 | Secret/database identity sai | Không join nhầm cluster |
| N05 | WAL replay kéo dài | Startup probe không restart liên tục |
| N06 | Disk recovery hết dung lượng | Alert và không claim healthy |
| N07 | Node `JOINING` nhận traffic thử | Routing gate bảo vệ |
| N08 | Replica lag 10 phút | Freshness-sensitive reads blocked |
| N09 | Replica lag metric mất | UNKNOWN, không tự coi zero |
| N10 | Primary step-down có kế hoạch | Driver chuyển role an toàn |
| N11 | Primary crash trước ACK | Unknown outcome/idempotency đúng |
| N12 | Election không đủ quorum | Writes bị từ chối theo contract |
| N13 | One Cassandra replica down | CL-dependent availability |
| N14 | Cassandra node offline quá grace/repair window | Rebuild/reseed không zombie |
| N15 | MongoDB secondary initial sync | Không phục vụ writes như primary |
| N16 | MongoDB rollback state | Không routing wrong freshness |
| N17 | Redis Cluster one master lost | Slot failover/redirect đúng |
| N18 | Redis replica được promote nhưng lag | Không hứa giữ mọi ACKed cache write |
| N19 | Elasticsearch node joins but shards unassigned | Index readiness đúng |
| N20 | Elasticsearch yellow cluster | Phân loại degraded vs unavailable |
| N21 | Couchbase node warmup/rebalance | KV/index service readiness riêng |
| N22 | Kubernetes liveness quá chặt | Không crash loop |
| N23 | Kubernetes readiness quá chặt | Không đưa cả cụm thành unready vì một peer |
| N24 | Pod bị kill trước termination grace | Recovery và data safety đúng |
| N25 | PV mount sai/cluster ID sai | Không import dữ liệu vào cluster nhầm |
| N26 | Inter-node TLS fail sau cert rotation | Trust overlap/runbook |
| N27 | Node DNS đổi nhưng driver giữ topology cũ | Driver refresh/retry bounded |
| N28 | Rolling restart khi một replica đã lỗi | Preflight gate hoãn stop |
| N29 | Rebalance đang chạy khi dừng target | Maintenance safety gate |
| N30 | All nodes crash, restore from backup | RPO/replay/deletion correctness |
| N31 | Read canary pass nhưng writes fail | Phân biệt read/write eligibility |
| N32 | Node process healthy, API p99 xấu do compaction | Không claim SLO recovered |
| N33 | Readiness probe tạo workload lớn | Probe budget giới hạn |
| N34 | Node chỉ mất network tới một DC | Phân biệt regional quorum |
| N35 | Graceful stop với in-flight write | Commit/unknown result xử lý đúng |
| N36 | Node restarted repeatedly by orchestration | Liveness/startup policies được sửa |

Chỉ thực hiện deliberate crash, network partition, disk-full, quorum loss và certificate failure trong staging/disposable test environment được phê duyệt, hoặc một chaos program có quy tắc an toàn rõ.

---

## 41. Bài tập 1: phân loại bảy mức “ready”

Một node cho báo cáo:

~~~text
Process alive:       YES
TCP listener:        YES
TLS handshake:       PASS
Cluster joined:      YES
Data recovery:       65%
Replication lag:     8 minutes
Role:                SECONDARY
```

Hãy trả lời:

1. Node có **live** không?
2. Có nên coi startup hoàn tất?
3. Có nên route writes?
4. Có nên route strongly consistent reads?
5. Eventual reads có thể được phép nếu SLO freshness thế nào?
6. Readiness check nên trả lý do nào?
7. Nếu liveness restart node 30 giây/lần thì hậu quả gì?

---

## 42. Bài tập 2: safety gate cho rolling restart

Cụm có năm voting members và chỉ ba đang sẵn sàng đáp ứng consensus. Một trong ba cần bảo trì.

1. Tính majority quorum.
2. Dừng thêm một voter có làm mất quorum không?
3. Một replica process alive nhưng không voting-eligible có được tính không?
4. Tại sao `systemctl is-active` không đủ?
5. Điều kiện nào cần đạt trước khi restart?
6. Nếu không có cách đạt điều kiện, cần hoãn hay giảm consistency contract?
7. Thiết kế 10 preflight checks.

---

## 43. Bài tập 3: Cassandra `UN`, `UJ`, `DN`

Cho output giả lập:

~~~text
UN node-a
UN node-b
UJ node-c
DN node-d
```

1. Ký hiệu `U/D` khác `N/J` thế nào?
2. Node-c đang join có thể được coi fully ready không?
3. Nếu RF=3, `LOCAL_QUORUM` có thể thành công cho mọi partitions không? Cần biết gì thêm?
4. Khi nào dùng `nodetool drain`?
5. Khi nào dùng `nodetool decommission`?
6. Nếu node-d offline quá lâu, cần xem tombstone/repair horizon gì?
7. Metrics nào chứng minh compaction/streaming đã ổn định?

---

## 44. Bài tập 4: MongoDB election và replication lag

Replica set:

~~~text
db-1 PRIMARY
db-2 SECONDARY, lag 1 second
db-3 SECONDARY, lag 40 minutes
```

1. Có nên dừng db-2 trước khi sửa db-3 không?
2. Nếu db-1 đột ngột chết, điều gì có thể xảy ra?
3. Khác nhau giữa PRIMARY, SECONDARY, RECOVERING và ARBITER?
4. Khi nào một Secondary đủ điều kiện cho stale-tolerant read?
5. Có thể kiểm những gì bằng `rs.status()` và `db.hello()`?
6. Vì sao majority write concern và election quorum không chỉ là “TCP sống”?
7. Thiết kế một canary failover có idempotency.

---

## 45. Bài tập 5: Kubernetes probes

Một StatefulSet có:

~~~text
Startup recovery requires 4 minutes.
Liveness starts at 30 seconds.
Liveness fails after 3 probes every 10 seconds.
Readiness is only TCP port open.
```

1. Hậu quả của probe hiện tại?
2. Sửa startup probe thế nào?
3. Readiness cần kiểm gì mà không tạo full scans?
4. Nếu một peer hỏng, có nên đánh dấu mọi node unready?
5. `terminationGracePeriodSeconds` liên quan gì đến shutdown?
6. PDB giúp gì và không giúp được gì?
7. Tại sao readiness ở Kubernetes Service không chặn mọi native-driver direct connections?

---

## 46. Bài tập 6: Redis Cluster và failover

Một Redis Cluster có nhiều masters/replicas. Master sở hữu một số slots bị crash.

1. Vì sao `PING` của master khác không bảo đảm key trên slots bị ảnh hưởng đọc được?
2. Xem `CLUSTER INFO`/`CLUSTER NODES` để biết điều gì?
3. Client cần xử lý `MOVED`/`ASK` thế nào?
4. Replica được promote có chắc giữ mọi write đã ACK ở master cũ không?
5. Nếu Redis chỉ chứa cache derived, kế hoạch warm-up ra sao?
6. Nếu chứa idempotency ledger duy nhất, risk khác gì?
7. Lệnh dừng/maintenance cần khác decommission slot ownership thế nào?

---

## 47. Bài tập 7: dựng dashboard readiness

Thiết kế dashboard cho 12-node NoSQL cluster:

- Process start/restart count.
- Liveness/startup/readiness.
- Role and leader changes.
- Replication lag theo shard/replica.
- Quorum availability.
- Disk/compaction/streaming.
- TLS/certificate errors.
- Client server-selection latency.
- Query p95/p99, errors và retries.
- Change ID và planned maintenance annotations.
- Time from process start to serving.
- Capacity N+1 sau khi dừng target.

Giải thích vì sao dashboard không thể chỉ có một gauge `healthy_nodes=12`.

---

## 48. Bài tập 8: viết hai runbooks khác nhau

Viết:

**Runbook A:** rolling restart một node trong cụm production có quorum, backup và replica placement đủ.

**Runbook B:** khôi phục một node đã offline vượt source-log/repair horizon, có khả năng stale data.

Mỗi runbook cần có:

1. Điều kiện bắt đầu.
2. Người chịu trách nhiệm/phê duyệt.
3. Impact tới read/write SLO.
4. Bằng chứng membership/role/quorum.
5. Các lệnh quan sát không phá dữ liệu.
6. Stop/drain/replace/decommission decision.
7. Biện pháp bảo vệ in-flight requests.
8. Recovery/reseed/restore strategy.
9. Readiness gates và canary.
10. Dấu hiệu phải rollback/escalate.
11. Correctness checks.
12. Post-incident/change record.

---

## 49. Những hiểu lầm thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Process Running là node ready.” | Chưa chắc join/recover/replica eligible |
| “TCP mở nghĩa database đọc/ghi được.” | Có thể chỉ transport ready |
| “TLS handshake thành công nghĩa role đúng.” | Security identity khác cluster role |
| “`PING` trả OK nghĩa mọi partitions khỏe.” | Ping chỉ kiểm một endpoint/protocol path |
| “Node UP nghĩa quorum đủ.” | Cần group/range/consistency evidence |
| “Cụm có 5 nodes, 3 nodes up luôn đủ cho mọi read.” | Tùy replica placement và protocol |
| “Secondary có thể nhận writes như primary.” | Leader-based roles khác nhau |
| “Mọi Secondary reads đều fresh.” | Replica lag/read preference khác |
| “Redis Sentinel là consensus durable write.” | Failover không biến async replication thành durable quorum |
| “Redis Cluster PONG nghĩa mọi hash slots available.” | Slot coverage/owner phải kiểm |
| “Elasticsearch Yellow nghĩa toàn bộ unavailable.” | Primary shards có thể phục vụ, redundancy giảm |
| “Elasticsearch Green nghĩa API p99 chắc tốt.” | Disk/cache/indexing errors vẫn có thể |
| “`UN` Cassandra chứng minh mọi CL thành công.” | Cần replicas/consistency và source health |
| “`nodetool drain` và `decommission` như nhau.” | Chuẩn bị stop khác rút membership |
| “Dừng VM là decommission hoàn tất.” | Ownership/metadata có thể còn |
| “Restart xóa data directory là sạch sẽ.” | Có thể thành data loss/rebootstrap sai |
| “Mọi NoSQL có cùng lệnh stop.” | Engine/version/deployment khác nhau |
| “Node online nhưng lag cao vẫn dùng làm nguồn strong read.” | Chỉ khi protocol/contract đảm bảo |
| “Read canary pass nghĩa writes pass.” | Read/write eligibility khác |
| “Kubernetes liveness nên phụ thuộc mọi peers.” | Có thể restart loop toàn cụm |
| “Kubernetes readiness chỉ cần TCP.” | Có thể đưa traffic tới recovering node |
| “PDB ngăn mọi node failure.” | Chỉ bao phủ một số voluntary disruptions |
| “preStop sleep đủ bảo vệ writes.” | Cần engine drain/in-flight protocol |
| “Graceful stop chắc chắn mọi ACKed write đã bền.” | Tùy durability/replication contract |
| “Node mới join thì có thể dừng node khác ngay.” | Cần recovery/catch-up gates |
| “Rolling restart cứ lần lượt mọi node là an toàn.” | Cần kiểm placements/quorum từng vòng |
| “Một node crash, cứ restart liên tục cho tới khi được.” | Có thể phá recovery và tăng tải |
| “Thay CA cert có thể bỏ hostname verification tạm.” | Sửa certificate/trust/endpoint, không hạ security |
| “Client reconnect lỗi thì chắc DB chết.” | Có thể là TLS/DNS/driver topology |
| “Thấy lag metric thiếu nghĩa lag bằng 0.” | UNKNOWN không là HEALTHY |
| “Backup restore thành công nghĩa deleted data vẫn đúng.” | Cần deletion replay/reconciliation |
| “Managed DynamoDB có storage node restart command.” | Không trong phạm vi khách hàng |
| “Node status xanh là incident đã kết thúc.” | Cần p99/goodput/correctness đạt SLO |

---

## 50. Checklist vận hành trước khi dừng hoặc đưa nút trở lại phục vụ

- [ ] Xác định đúng environment, cluster ID, node ID và owner.
- [ ] Có change/incident record, maintenance window và rollback plan.
- [ ] Biết node role, voters, replication factor, shard/slot ownership.
- [ ] Kiểm đủ quorum/replica placements khi target tạm unavailable.
- [ ] Không có một replica/shard khác đang unavailable khiến stop target nguy hiểm.
- [ ] Phân biệt restart, replace, bootstrap, decommission và full restore.
- [ ] Biết trạng thái process, transport, TLS, membership, recovery, read/write eligibility.
- [ ] Không dùng TCP/PING như bằng chứng phục vụ đầy đủ.
- [ ] Kiểm startup probe tránh crash loop, liveness không phụ thuộc cluster global.
- [ ] Readiness có tiêu chí theo operation contract.
- [ ] Driver topology/discovered endpoints và TLS identities đúng.
- [ ] Node disk/memory/CPU/network đủ headroom.
- [ ] Peers đủ capacity gánh traffic khi stop.
- [ ] Replication lag/initial sync/recovery theo ngưỡng SLO.
- [ ] Backup/log history/restore path được xác minh khi cần.
- [ ] Graceful drain/leadership transfer theo engine.
- [ ] In-flight writes có idempotency/unknown-outcome handling.
- [ ] Không xóa data volume, WAL, SSTables hoặc oplog tùy tiện.
- [ ] Không hạ consistency/quorum contract để maintenance dễ hơn.
- [ ] Không tắt TLS hostname/CA verification để join cluster.
- [ ] Chờ data ownership/slot/shard readiness sau start.
- [ ] Không stop node kế tiếp trước khi gates phục hồi đầy đủ.
- [ ] Có metrics p95/p99, error rate, retries và goodput.
- [ ] Có per-shard/per-node health, không chỉ cluster average.
- [ ] Có cảnh báo trạng thái UNKNOWN/stale health snapshot.
- [ ] Có kịch bản node offline quá tombstone/oplog/repair horizon.
- [ ] Failover/DR endpoints được kiểm tra, không chỉ node primary.
- [ ] Quá trình phục hồi không hồi sinh data đã xóa trái policy.
- [ ] Runbook ghi rõ điều kiện tạm dừng/escalate.
- [ ] Sau restart kiểm đúng business data và ứng dụng SLO.
- [ ] Report trạng thái theo bằng chứng, không chỉ lệnh start trả code 0.

---

## 51. Tổng kết

**Khởi động và dừng nút trong cụm NoSQL là thao tác lên một hệ phân tán, không chỉ lên một process.** Một nút có thể chạy nhưng chưa join, đã join nhưng chưa có dữ liệu mới, có dữ liệu nhưng không đủ role/quorum, hoặc phục vụ reads mà chưa thể nhận writes.

Những nguyên tắc cốt lõi:

1. **Phân tách trạng thái** process, transport, security, membership, recovery, role, ownership và read/write eligibility.
2. **Liveness nhằm phát hiện process hỏng; readiness nhằm quyết định nhận traffic.** Startup probe giúp bảo vệ pha phục hồi dài.
3. **Quorum và replication placement quyết định availability thực tế**, không chỉ số node đang online.
4. **Startup phải xác minh join, recover, catch-up và SLO**, không chỉ cổng TCP mở.
5. **Graceful stop/drain khác decommission**; node rút khỏi topology có thể đòi streaming và thay đổi ownership.
6. **Rolling restart phải có preflight và gate từng vòng**. Không dừng node tiếp theo khi cụm còn degraded.
7. **Mỗi NoSQL có trạng thái và công cụ riêng**: Cassandra `UN/UJ/DN`, MongoDB PRIMARY/SECONDARY/RECOVERING, Redis role/slots, Elasticsearch shards và Couchbase services.
8. **Kubernetes/VM service status không thay engine-native health**; probe đặt sai có thể biến một lần restart thành cascading outage.
9. **Crash và stop giữa write có thể gây unknown outcome**; ứng dụng cần idempotency/reconciliation theo business contract.
10. **Thành công được xác nhận end-to-end** bằng read/write correctness, replication/quorum, p99/goodput và khả năng phục hồi tiếp, không phải chỉ process đã chạy lại.

**Câu cần nhớ: “Nút NoSQL chỉ được coi là sẵn sàng khi nó đủ điều kiện phục vụ đúng loại thao tác mà ứng dụng yêu cầu, với dữ liệu, vai trò và quorum phù hợp. Hãy xác minh điều đó trước khi đưa traffic vào — và trước khi dừng nút kế tiếp.”**
