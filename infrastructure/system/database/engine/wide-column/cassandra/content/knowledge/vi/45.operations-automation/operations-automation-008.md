# Điều phối bootstrap/decommission mà không lặp thao tác nguy hiểm trong Apache Cassandra

## 1. Mục tiêu và ranh giới an toàn

Trong Cassandra, **bootstrap** đưa một node mới vào topology và phân phối dữ liệu/tokens cho nó; **decommission** loại một node đang tham gia ring theo cơ chế được phiên bản hỗ trợ, thường có streaming để các replica còn lại tiếp nhận dữ liệu. Đây là các thay đổi **topology có trạng thái**, không phải hai HTTP API idempotent mà client cứ retry khi timeout.

Bài học thuộc chương **Tự động hóa vận hành** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Mục tiêu module bao gồm kiến trúc wide-column phân tán, partition keys, replication, consistency, compaction, repair và Java/CQL. Chính các yếu tố này quyết định một node có thể an toàn vào/ra cluster và khi nào automation được phép chuyển sang bước tiếp theo.

Sau bài học, bạn có thể:

1. Phân biệt bootstrap, decommission, replacement, restart, join/leave, removenode và cleanup ở mức **ý nghĩa vận hành**.
2. Biết vì sao **retry mù một lệnh topology** có thể tạo hai node, di chuyển tokens sai, mất dữ liệu hoặc giảm khả năng đáp ứng consistency level.
3. Thiết kế **operation ID**, expected target state, immutable change manifest, durable journal, leader lease và quyền sở hữu một thao tác.
4. Vận dụng **fencing/epoch** để ngăn controller mới và cũ cùng điều phối, đồng thời hiểu giới hạn khi Cassandra không nhận fencing token vào lệnh quản trị.
5. Dùng reconcile read-only để xác định tiến trình sau crash, timeout hoặc mất phản hồi mà **không phát lại command**.
6. Xác minh **DC/rack, RF/CL, replica availability, token ownership, streaming, disk/GC/network**, schema agreement và truy vấn CQL.
7. Xây dựng chính sách stop/rollback/escalation với trạng thái **PASS/FAIL/UNKNOWN** thay vì suy diễn thành công từ một dòng `UN`.
8. Viết state-machine pseudocode, Java Driver probe, runbook sự cố, ma trận kiểm thử và checklist để kiểm soát thay đổi.

**Phạm vi phiên bản:** hành vi bootstrap/decommission, lệnh `nodetool`, option startup, seed discovery, vnode/tokens, host ID, `system.peers_v2`, metadata và sự tương thích giữa Cassandra 3.x/4.x/5.x hoặc distribution có thể khác. Bài mô tả các nguyên tắc an toàn chung; mọi thao tác thực tế phải được đối chiếu **release, cluster topology và SOP được phê duyệt**.

**Giới hạn của bước viết:** không chạy lệnh Cassandra, không thay topology, không chạy Java/Gradle, không mở file repo khác. Mọi commands trong bài chỉ là mẫu để người học hiểu quy trình.

## 2. Vì sao bootstrap/decommission không phải công việc có thể retry tự do?

### 2.1. Hai lệnh cùng tên không đồng nghĩa một hành động lặp an toàn

Giả sử automation điều phối bỏ node `A`:

~~~text
10:00  Controller-1 xác nhận PRECHECK PASS.
10:01  Controller-1 gửi decommission tới node A.
10:02  Network của controller timeout.
10:03  Cassandra node A vẫn streaming dữ liệu và rời ring.
10:04  Controller-2 được khởi động lại.
10:05  Controller-2 thấy "request timeout", gửi decommission lần hai.
~~~

Controller-2 **không biết** command trước được nhận hay chưa. Tùy trạng thái Cassandra/release, lặp command có thể bị từ chối, gây xung đột, hoặc che lỗi thực tế. Quan trọng hơn, nếu automation **chọn lại target dựa trên IP đã được reuse**, lần hai thậm chí có thể tác động vào **node khác**.

**Quy tắc:** timeout nghĩa **outcome chưa biết**, không nghĩa thao tác chưa bắt đầu hoặc đã rollback.

### 2.2. Cần phân biệt retry của lệnh và lặp bước quan sát

| Hoạt động | Đặc điểm | Tự retry khi timeout? |
|---|---|---|
| Đọc `nodetool status` | Quan sát state; có rủi ro stale/partial | Có giới hạn, với freshness checks |
| Đọc `nodetool netstats` | Quan sát streaming | Có giới hạn |
| Đọc metrics GC/disk/CQL | Quan sát sức khỏe | Có giới hạn |
| Query CQL bounded read-only | Kiểm dữ liệu/CL | Có giới hạn, có timeout budget |
| Bootstrap node lần đầu | Thay đổi membership/ownership qua startup | **Không tự phát lại** khi chưa reconcile |
| Decommission node | Thay đổi ring và dữ liệu replica | **Không retry mù** |
| Removenode/replace | Thay đổi membership với rủi ro cao | Human/SOP control |
| Cleanup/repair/compact | Công việc I/O/resource/đôi khi dữ liệu | Không chạy như điều kiện health |
| Reimage/recreate VM/PVC | Có thể làm mất identity/commitlog/data | Không lặp nếu chưa xác minh identity |

Có thể retry **phép đọc trạng thái**, nhưng không bảo đảm kết quả đúng nếu chỉ quan sát một node hoặc một snapshot; cần đối chiếu nhiều nguồn và expected topology.

### 2.3. Không thể hứa “exactly-once” bằng try/catch

Một controller lưu `started=true` **trước** gửi command có thể crash khi chưa gửi; lưu **sau** khi gửi có thể crash trước khi ghi. Không có transaction nguyên tử chung giữa journal của controller và thao tác Cassandra.

Vì vậy, thiết kế thực tế là:

- **At-most-one in-flight intent** do một controller active kiểm soát.
- Mỗi topology change gắn **operation ID bất biến**.
- Trước phát command, ghi durable record: target identity, operation type, checkpoint và quyền.
- Sau mất kết nối, **read-only reconcile** rồi quyết định manual resume/continue theo state.
- Không tự tuyên bố đảm bảo exactly-once nếu Cassandra không cung cấp một idempotency key thực sự cho command ấy.

## 3. Bootstrap, decommission và các thao tác dễ nhầm

### 3.1. Thuật ngữ và mục đích

| Hoạt động | Mục tiêu | Rủi ro nếu chọn sai |
|---|---|---|
| Bootstrap | Node **mới** tham gia cluster, nhận tokens/data | Duplicate identity, streaming pressure |
| Restart | Node hiện hữu dừng/chạy lại, **giữ identity/data** | Rebootstrap nhầm, mất availability |
| Replace | Thay node lỗi bằng node mới theo cơ chế release hỗ trợ | Trùng host ID/tokens hoặc mất data nếu thao tác sai |
| Decommission | Node **còn có thể tham gia** rời cluster có kiểm soát | RF/CL unsafe, streaming dang dở |
| Removenode | Loại metadata của node không còn sẵn sàng theo SOP/version | Mất replica metadata/data nếu dùng nhầm |
| Cleanup | Dọn SSTables không còn thuộc node sau topology change | Xóa dữ liệu sớm/IO pressure |
| Rebuild | Tái đồng bộ dữ liệu từ nguồn theo công cụ release | Network/disk pressure |
| Repair | Đồng bộ/sửa lệch replica ranges | I/O/disk/CPU và lịch trình riêng |

**Không dùng `decommission` như thay thế `removenode`** cho một node đã chết mà version không hỗ trợ cách đó. Cũng không khởi tạo một node cũ giữ data với identity mới mà gọi đó là restart.

### 3.2. Bootstrap không phải một command `nodetool bootstrap` phổ quát

Trong nhiều bản Cassandra, bootstrap diễn ra khi **node mới được khởi động với cấu hình tham gia cluster**, kết nối seeds/peers và lựa chọn tokens theo chính sách (`auto_bootstrap`/replace/initial_token/vnodes tùy version).

Vì vậy một controller không nên viết:

~~~text
Run a made-up universal command:
  nodetool bootstrap

Assume every Cassandra release supports that action.
~~~

Thay vào đó, controller phải gọi **cluster management operator/SOP** được phiên bản hỗ trợ, điều khiển node creation/startup có approval, rồi **quan sát state Joining → Normal** và streaming. Không tự tạo cơ chế nguy hiểm bằng việc ép sửa token metadata.

### 3.3. Decommission một node sống khác remove một node chết

Decommission thông thường cần node còn hoạt động đủ để thực hiện chuyển giao ownership/streaming. Với node chết, luồng xử lý khác và có rủi ro mất các bản sao cần thiết. Automation phải phân loại:

~~~text
Target is Up, Normal, healthy:
    Consider approved decommission preflight.

Target is Down/unreachable:
    STOP; invoke node-failure/removal/replace SOP.

Target is already Leaving or absent:
    DO NOT send decommission again.
    Reconcile history and ring views.

Target identity changed:
    STOP; investigate recycled IP/PVC/host ID.
~~~

Không để script nhìn thấy `DN` rồi gọi decommission như một hành động “sửa lỗi”.

## 4. Mô hình identity: địa chỉ IP không phải ID đủ an toàn

### 4.1. Các trường nên có trong operation manifest

~~~yaml
# Ví dụ manifest đầu vào: KHÔNG phải cấu hình Cassandra.
change_id: CHG-2026-1121-008
operation_id: "f25be1dc-58ba-4d11-af04-0c7c80080008"
operation_type: DECOMMISSION
cluster_id: "cassandra-telemetry-production"
expected_cluster_version: "approved-release"
target:
  host_id: "11111111-2222-3333-4444-555555555555"
  node_address: "cassandra-a.example.invalid"
  datacenter: "dc1"
  rack: "rack2"
  persistent_volume_identity: "approved-storage-identity"
expected_before:
  membership: NORMAL
  target_up: true
expected_after:
  membership: ABSENT
guardrails:
  no_parallel_topology_change: true
  require_operator_approval: true
  require_healthy_quorum: true
  require_sufficient_disk: true
  observation_window_seconds: 900
~~~

Đây là manifest minh họa. Giá trị `operation_id` phải bền vững qua **retries của controller**, không cấp UUID mới mỗi lần worker được chạy lại.

**Phân biệt theo action:** Manifest trên là ví dụ **DECOMMISSION**, khi host ID của node hiện hữu đã biết. Với **BOOTSTRAP node hoàn toàn mới**, Cassandra có thể chỉ tạo host ID sau lần khởi động đầu tiên. Trước dispatch phải khóa **cluster, instance/PVC identity, DC/rack và generation**; khi host ID xuất hiện lần đầu, ghi nhận nó bằng journal CAS rồi xác minh không trùng với member hiện hữu. Không bịa một host ID cố định trước startup hoặc thay node mới bằng node khác khi reconcile.

### 4.2. Identity cần được xác minh theo nhiều lớp

- **Cluster ID/name** của kết nối đang điều khiển, tránh gọi nhầm staging/production.
- **Host ID** của target từ metadata Cassandra, không chỉ IP/DNS.
- **DC/rack placement** và failure domain.
- **Current membership state** (Normal/Joining/Leaving/Down/absent).
- **Persistent data/volume identity**, đặc biệt khi Kubernetes StatefulSet/PVC hoặc VM replacement.
- **Token/vnode assignment** và policy của bản Cassandra.
- **Version/config baseline** cho node mới hoặc node đang rời.
- **Change manifest revision** được ký/approved.

Một IP hoặc pod name có thể được tái sử dụng sau replace. Nếu host ID trong live cluster không khớp manifest, **không “tự điều chỉnh target”**; xuất `UNKNOWN/FAIL` và yêu cầu operator điều tra.

### 4.3. Không để mutable target selector chọn node mới

Anti-pattern:

~~~text
for every node with hostname prefix cassandra-a:
    if node unhealthy:
        run decommission
~~~

Quy tắc chọn target phải **resolve một lần trước approval**: với **decommission**, khóa host ID/cluster; với **bootstrap mới**, khóa instance/PVC/cluster và pin host ID được quan sát sau startup. Sau đó mỗi lần reconcile xác minh “đây vẫn là đúng thực thể”. Nếu node đã bị thay thì operation cũ **không được chuyển sang node khác**.

## 5. Hard gates trước thay đổi topology

### 5.1. Chỉ preflight PASS khi đủ dữ kiện

| Gate | Bootstrap | Decommission |
|---|---|---|
| Change approved, operation ID duy nhất | Bắt buộc | Bắt buộc |
| Không có operation khác cùng scope | Bắt buộc | Bắt buộc |
| Cluster/DC/rack inventory nhất quán | Bắt buộc | Bắt buộc |
| Target identity và lifecycle đúng | Node mới, chưa tham gia ring | Node cũ, Up/Normal theo SOP |
| RF/CL sau change khả thi | Kiểm disk/replica distribution | Kiểm không mất replica/quorum |
| Không có unrelated unexpected DOWN nodes | Bắt buộc | Bắt buộc |
| Schema/token metadata ổn định | Bắt buộc | Bắt buộc |
| Streaming/repair/backup conflict? | Phải kiểm | Phải kiểm |
| Disk/network/GC/CPU headroom | Streaming nhận/gửi | Streaming và peers tiếp nhận |
| App CQL & SLO baseline đáng tin | Bắt buộc | Bắt buộc |
| Rollback/abort strategy rõ | Phải có | Phải có, nhưng không hứa rollback luôn khả thi |
| Observation and recovery owner | Bắt buộc | Bắt buộc |

Nếu thiếu metric cần thiết, trả **UNKNOWN** và dừng, không gán “0 errors” cho kết nối monitoring bị lỗi.

### 5.2. Cluster health không chỉ là `UN`

Một cluster có tất cả nodes `UN` vẫn có thể:

- Disk gần đầy, compaction pending tăng.
- Repair/hints/streaming đang tiêu thụ I/O.
- JVM GC pause khiến CQL p99 vượt SLO.
- CQL native TLS/auth không hoạt động với Java clients.
- Schema disagreement/driver prepared query incompatibility.
- Một DC/rack thiếu dự phòng cho RF/CL.
- Hot partitions khiến một số replica quá tải.

Health gates cần cả **status từ nhiều observers**, metrics trên node nóng nhất, và representative CQL probes theo CL cần kiểm.

### 5.3. Không đếm `UN` thay vì so inventory

Ví dụ expected 8 nodes nhưng `nodetool status` chỉ in 7 dòng, tất cả là `UN`. Script tìm chuỗi `DN` không thấy rồi PASS là sai: **một node vắng khỏi output**.

So sánh **expected host IDs, DC/rack, state** và các thay đổi cho phép bởi manifest. Đối với bootstrap, expected count **tăng theo giai đoạn**; đối với decommission expected count **giảm khi kết thúc**. Không buộc pre/post node list giống nhau nếu operation chính là thay đổi topology.

## 6. RF/CL, token ownership và sự an toàn khi rời node

### 6.1. Một ví dụ local quorum

Giả sử `NetworkTopologyStrategy` với `RF(dc1)=3`, app dùng `LOCAL_QUORUM`. Thông thường một write/read cần đủ **2 phản hồi replica trong dc1** cho partition liên quan.

Nếu một node trong dc1 DOWN, request vẫn có thể hoàn tất khi replica set khác còn đủ phản hồi, nhưng **không thể mặc nhiên decommission thêm một node khác**. Một cluster vẫn phục vụ đang bị suy giảm không đồng nghĩa vẫn an toàn cho topology changes.

### 6.2. Không đánh giá bằng “3 node trong DC” một cách máy móc

Cassandra dùng token ring/replica placement; RF=3 không có nghĩa mọi partition trong mọi topology đều có cùng ba node tùy ý. Cần xác minh:

- DC nào đặt replication factor bao nhiêu.
- Node count/rack placement và số bản sao trong **replica set** của từng token range.
- Các node hiện hữu có dữ liệu cần thiết trước khi target rời không.
- Repair history và tình trạng replica out-of-sync.
- Không có node UP nhưng native transport/streaming không phục vụ được.
- Transient replication/đặc tính version nếu cluster sử dụng.

Một check `nodetool status` không đủ để chứng minh consistency khi token ownership thay đổi.

### 6.3. Capacity sau decommission

Một node rời cluster nghĩa dữ liệu và request phải phân bố lên số node còn lại. Ví dụ giả định:

~~~text
dc1: 6 nodes, mỗi node đang lưu khoảng 2 TiB SSTables
decommission 1 node
=> tổng dữ liệu logic/replica phải phân bố trên 5 nodes;
   dung lượng tăng đều chỉ là ước lượng thô.

Không được suy:
  "mỗi node tăng chính xác 20% và chắc chắn đủ disk"
vì token ownership, RF, SSTable size, compaction/streaming,
skew và dữ liệu tạm có thể khác.
~~~

Tính budget phải gồm **peak streaming và compaction temporary space**, disks/volume limits, bytes per token range, hotspots và failover headroom. Không chờ disk full mới coi preflight FAIL.

### 6.4. Capacity khi bootstrap

Bootstrap node mới làm các source peers stream dữ liệu, thay ownership và có thể ảnh hưởng caches/disk/network. Node mới `UN` chưa chắc đã warming xong, còn peers có thể chưa cleanup/dữ liệu chưa rebalance theo kỳ vọng. Phải kiểm **streaming complete, expected token/rack/host IDs và traffic p99** trước bước kế.

### 6.5. Không hạ consistency để “làm bước bảo trì chạy được”

Nếu production dùng `LOCAL_QUORUM` mà probe chỉ dùng `ONE`, một node đang mất quorum có thể vẫn báo CQL PASS. Mức CL kiểm chứng cần tương thích SLO/correctness của ứng dụng. Không sửa bằng cách hạ CL production để tránh preflight FAIL.

## 7. State machine tách ý định khỏi kết quả quan sát

### 7.1. Các trạng thái tối thiểu

~~~mermaid
flowchart TD
    A["NEW"] --> B["APPROVED"]
    B --> C["PREFLIGHT"]
    C -->|PASS| D["RESERVED"]
    C -->|FAIL/UNKNOWN| H["HOLD"]
    D --> E["COMMAND_INTENT_RECORDED"]
    E --> F["COMMAND_DISPATCH_UNCERTAIN"]
    F --> G["RECONCILING_READ_ONLY"]
    G -->|Active| I["IN_PROGRESS"]
    G -->|Not resolved| H
    G -->|Expected target reached| J["VERIFYING"]
    I --> G
    J -->|PASS| K["COMPLETED"]
    J -->|FAIL/UNKNOWN| H
    H --> L["HUMAN_REVIEW / RECOVERY"]
~~~

Tên `COMMAND_DISPATCH_UNCERTAIN` **không có nghĩa request luôn thất bại**: nó phản ánh rằng controller không thể thực hiện commit nguyên tử cùng Cassandra. Ngay cả khi transport trả ack, vẫn phải quan sát ring/data movement và kiểm kết quả sau.

### 7.2. Từng state có output rõ

| State | Ý nghĩa | Có thể dispatch topology command? |
|---|---|---|
| NEW | Manifest chưa phê duyệt | Không |
| APPROVED | Scope/owner/change ID cố định | Không |
| PREFLIGHT | Đang đọc trạng thái và kiểm safety gates | Không |
| RESERVED | Giữ exclusive right theo scope | Chưa, phải ghi intent |
| COMMAND_INTENT_RECORDED | Durable checkpoint trước side effect | Một lần có kiểm soát |
| COMMAND_DISPATCH_UNCERTAIN | May have been accepted/started | **Không phát lại** |
| IN_PROGRESS | Cassandra đã được quan sát đang join/leave/stream | Không |
| RECONCILING_READ_ONLY | Thu live evidence, so expected state | Không |
| VERIFYING | Target state quan sát xong, kiểm CQL/metrics | Không |
| HOLD | Gate fail/missing evidence | Không |
| HUMAN_REVIEW | Operator ra quyết định theo SOP | Không tự động |
| COMPLETED | Postconditions đạt, audit commit | Không |

Controller chỉ lưu `COMPLETED` khi có đủ bằng chứng, không vì process `nodetool` exit code 0 hoặc sau một khoảng sleep cố định.

### 7.3. Transitions phải có invariant

Các bất biến thực dụng:

- Trong một scope cluster/topology, **không quá một mutation có nguy cơ va chạm** đang được điều phối.
- Operation đã ghi `COMMAND_INTENT_RECORDED` không được dispatch thêm command lần hai trên recovery chỉ vì journal thiếu “completed”.
- Mỗi observation có source node/UTC timestamp/freshness.
- Target cluster/host ID/DC/rack **không đổi** so với manifest approved.
- Mỗi change phase có expected topology khác nhau, không dùng chung invariant cho bootstrap và decommission.
- `FAIL` hoặc `UNKNOWN` phải chặn bước tiếp khi policy fail-closed.
- Controller chỉ chịu trách nhiệm orchestration; không tự thay các thao tác repair/recovery được SOP quy định.

## 8. Lock, lease và fencing: cần đủ nhưng không nên hứa quá mức

### 8.1. Chọn nơi lưu operation journal

Journal cần:

- **Durable**, read-after-write consistency/transaction guarantees phù hợp.
- Chứa `operation_id`, manifest revision, target identity, state, command intent và evidence references.
- Cho phép **compare-and-swap (CAS)** hay optimistic version control để chặn hai controllers cùng nâng state.
- Không mất state khi worker process chết.
- Có quyền/audit và retention rõ.

Có thể dùng một control-plane store chuyên dụng như Kubernetes Lease/etcd + DB giao dịch, hoặc một hệ lưu trữ có semantics phù hợp. **Không mặc định lưu lock duy nhất trong chính Cassandra cluster đang gặp sự cố**: nếu Cassandra không reachable, controller sẽ không biết có đang giữ lock hay không.

### 8.2. Lease hết hạn không tự làm lệnh topology dừng

~~~text
Controller A owns lease epoch=41.
A launches decommission; command vẫn chạy ở Cassandra.
A loses network, lease expires.
Controller B acquires lease epoch=42.

Sai:
  B dispatches decommission again.

Đúng:
  B sees durable command intent and no verified outcome,
  RECONCILES read-only, then HOLD/HUMAN_REVIEW if uncertain.
~~~

Fencing token/epoch chỉ hiệu quả với hệ nhận và kiểm token. **Cassandra `nodetool decommission` không có một fencing token phổ quát được bảo đảm ở giao diện lệnh**. Vì vậy việc tăng epoch ở control-plane **không tự hủy** command cũ.

### 8.3. Biện pháp ngăn split-brain controller

1. **Leader election** theo scope cluster/topology (không chỉ theo pod).
2. **CAS trên journal revision** khi ghi state.
3. **Single dispatch authority** gắn với lease/epoch còn hiệu lực.
4. Chặn stale worker chạy side effect nếu không xác minh epoch/scope trước dispatch.
5. **Dispatch intent tồn tại lâu dài** dù lease expire.
6. New owner chỉ reconcile, không phát lệnh topology lần hai.
7. Hạn chế kênh quản trị trực tiếp: operator/script/manual access đều phải được quản lý theo change.
8. Khi không chắc ai đang thực thi lệnh, **HOLD và escalate**.

Nếu một công cụ vận hành có thể bị gọi ngoài controller (ví dụ kỹ sư chạy thủ công từ terminal), lock nội bộ controller **không còn độc quyền**. Cần kết hợp quy trình quyền, audit và change freeze.

### 8.4. “Retry-safe” khác “idempotent”

Một thao tác an toàn khi retry là thao tác có **idempotency contract được hệ đích xác nhận**, không chỉ một method Java được gắn `@Retryable`.

Dùng retry có backoff cho **read-only reconcile** có deadline; command topology nên có dispatch policy *at-most-once per approved intent*, và mọi trạng thái không chắc chắn phải được chứng minh an toàn trước khi operator cho phép tiếp tục.

## 9. Bảng phân loại lệnh quan sát và lệnh thay đổi trạng thái

### 9.1. Không dùng command exit code làm source of truth duy nhất

| Công cụ/lệnh minh họa | Mục đích | Loại | Chính sách automation |
|---|---|---|---|
| `nodetool status` | Membership/ring view | Quan sát | Retry bounded, so inventory |
| `nodetool info` | Node memory/load/uptime | Quan sát | Có freshness và source |
| `nodetool gossipinfo` | Gossip peer states | Quan sát | Diễn giải theo version |
| `nodetool netstats` | SSTable streaming | Quan sát | So progress nhiều samples |
| `nodetool tpstats` | Pending/active/dropped stages | Quan sát | Chú ý counter reset |
| `nodetool compactionstats` | Compaction tasks/backlog | Quan sát | Không đòi pending=0 tuyệt đối |
| `nodetool describecluster` | Metadata/schema views | Quan sát | Không đồng nghĩa CQL app healthy |
| `nodetool tablestats` | Table-level SSTables/memtables | Quan sát | Có IO/permissions costs |
| `nodetool decommission` | Rời ring có kiểm soát | **Topology mutation** | Một approved dispatch, không blind retry |
| Node first startup với bootstrap config | Tham gia ring/stream data | **Topology mutation** | Một lifecycle intent, không tạo node thứ hai |
| Node replacement theo SOP | Thay identity/token ownership | **Topology mutation** | Approval riêng, đúng node/volume |
| `nodetool removenode` | Loại metadata node không hoạt động | **Topology mutation** | Không tự thay cho decommission |
| `nodetool cleanup` | Dọn dữ liệu không còn sở hữu | Storage mutation | Không tự gọi trong health loop |
| `nodetool repair` | Repair replica ranges | Resource-heavy/data operation | Lịch riêng, không tự chạy do UNKNOWN |
| Restart/recreate PVC | Đổi process hoặc storage identity | Có side effect | SOP riêng, kiểm persistent data |

Output, tên lệnh và options phải kiểm trên release được vận hành. Việc liệt kê một lệnh **không** phải chỉ thị thực thi nó trên cluster thật.

### 9.2. Ví dụ các lệnh chỉ đọc

~~~bash
# Chỉ người được cấp quyền, từ môi trường vận hành hợp lệ.
nodetool status
nodetool info
nodetool gossipinfo
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool describecluster
~~~

`nodetool` thường giao tiếp qua JMX; một lệnh chạy được không chứng minh native CQL TLS/auth của Java app còn hoạt động. Các phiên bản có thể khác về flags, file output, permissions và các subcommands.

### 9.3. Không đưa topology command vào retry wrapper

~~~text
# ANTI-PATTERN — pseudocode, không phải shell được phép chạy.
retry(5, operation = decommission(target))

# ĐÚNG VỀ Ý TƯỞNG
record intent once
dispatch once under exclusive authorization
on timeout:
    mark outcome UNKNOWN
    read cluster state/streaming evidence
    hold until reconciled or human decision
~~~

Không gọi `nodetool decommission` ở mỗi vòng polling, không gọi lại khi process của controller bị SIGTERM và đừng “đổi host” để thử command khác.

## 10. Quy trình bootstrap: từ node chưa có identity đến member Normal

### 10.1. Giai đoạn A — chuẩn bị trước khi node mới khởi động

**Preflight phải xác minh:**

1. Change manifest có approved target DC/rack, capacity, version/config, volume và networking.
2. No other topology mutation đang chạy trong scope liên quan.
3. Không có node bất ngờ DOWN hoặc stream/repair overload.
4. Existing RF/CL và capacity đủ phục vụ trong khi node bootstrap.
5. Node mới **không mang data/system tables của node khác** trừ khi đây là **replacement plan được duyệt**.
6. Persistent disk/volume identity đúng target; không reuse PVC chứa Cassandra state của host ID khác.
7. Seed list và internode/TLS/config khớp cluster thật; seeds là discovery contacts, **không phải danh sách duy nhất của cluster**.
8. Gossip/broadcast/listen/native transport addresses và DNS/SAN phù hợp.
9. JVM/memory/disk/network/FD/CPU headroom, rack/DC placement và release compatibility.
10. Có telemetry và quyền quan sát để thấy node joining, streaming và recovery.

**Không khởi động đồng thời nhiều bootstrap nodes** nếu SOP cluster không cho phép; song song stream có thể làm nguồn dữ liệu và mạng bão hòa.

### 10.2. Giai đoạn B — ghi intent, sau đó tạo/start node đúng một lần

~~~text
Journal:
  operation_id = op-2026-008
  operation_type = BOOTSTRAP
  target_node_instance = immutable cloud/PVC identity
  target_cluster = cassandra-prod-example
  state = COMMAND_INTENT_RECORDED
  generation = 27
  approved_manifest_hash = ...
  command_dispatch_count = 0

Controller:
  CAS state -> COMMAND_DISPATCH_UNCERTAIN
  provision/start approved node once
  record dispatch metadata best effort
  begin read-only reconcile
~~~

Sơ đồ chỉ diễn tả ý tưởng. Trong crash window sau CAS nhưng trước provision, controller có thể không biết lệnh đã được gọi. Khi resume vẫn không tự tạo instance mới; phải kiểm infrastructure API, PVC/VM identity, node logs và ring membership để biết hành động đã xảy ra hay chưa.

### 10.3. Giai đoạn C — theo dõi Join/Streaming theo điều kiện

~~~mermaid
flowchart TD
    A["Approved node start intent"] --> B["New process discovered"]
    B --> C["Gossip membership Joining or equivalent phase"]
    C --> D["Streaming/token range movement"]
    D --> E["Normal membership + expected host ID/DC/rack"]
    E --> F["Native CQL + schema + data/latency probes"]
    F --> G{"All postconditions satisfied?"}
    G -->|Yes| H["COMPLETED"]
    G -->|No/Unknown| I["HOLD; diagnose/recover"]
~~~

Node có thể chuyển qua các trạng thái theo release khác nhau; không lấy sơ đồ làm cam kết các bước nội bộ chính xác. Poll `status`/`netstats` cùng logs/metrics với deadline và backoff.

Một node mới hiện `UN` có thể cần thêm thời gian cache warm-up, driver peer discovery, compaction/repair scheduling và metric stabilization. `UN` là **điều kiện cần**, chưa đủ để PASS.

### 10.4. Giai đoạn D — xác minh hậu bootstrap

| Check | Điều kiện đạt |
|---|---|
| Membership | Expected new host ID hiện diện và ở Normal/Up |
| Address/DC/rack | Khớp manifest, không quảng bá peer IP sai |
| Token ownership | Metadata theo plan; không có duplicate token/host ID |
| Source peers | Không có unexpected DN hoặc mất RF/CL |
| Streaming | Bootstrap transfers hoàn tất theo release/state evidence |
| Data | Expected replica ranges có thể phục vụ CQL representative queries |
| Schema | App prepares/executes CQL trên các nodes cần thiết |
| Workload | p95/p99/error không vượt SLO, retries không tạo storm |
| Resources | Source/destination disk/GC/network và compaction ổn định |
| Maintenance | Không có operation conflict; observer evidence còn mới |

Không gọi `cleanup` ngay trên mọi source nodes như bước “dọn bắt buộc” nếu chưa xác minh topology, ownership và hướng dẫn version. Cleanup có thể xóa dữ liệu không còn được sở hữu và tốn I/O; yêu cầu gate và plan riêng.

### 10.5. Khi bootstrap đứng yên

Trước khi thử lại node startup:

1. Kiểm node mới vẫn đang chạy hay process chỉ khởi động lại.
2. Kiểm status Joining/Normal và streaming activity nhiều lần.
3. So host ID/token/volume identity với operation manifest.
4. Kiểm logs có báo data directory/identity conflict không.
5. Kiểm disk/network/TLS/gossip/seed/DC/rack và compatibility.
6. Đặt trạng thái `UNKNOWN/IN_PROGRESS/HOLD` tùy evidence.
7. Chỉ operator theo SOP quyết định resume/restart/replace; **không tạo node thứ hai** để “thử cho nhanh”.

## 11. Quy trình decommission: rời ring chỉ khi an toàn

### 11.1. Giai đoạn A — xác nhận target có thể được decommission

Với node sống dự kiến rời cluster:

- Host ID đúng, node Up/Normal, identity không bị replace.
- DC/rack/cluster topology khớp approved manifest.
- RF theo DC và **số node còn lại** hợp với chính sách replication/availability sau change.
- Replica ranges có đường streaming/recovery khả thi.
- Disk/network capacity trên peers tiếp nhận đủ.
- Không còn repair/streaming/topology operation xung đột.
- App CQL tại CL production và baseline SLO đạt.
- Có quy trình khi decommission thất bại hoặc node rơi xuống DOWN giữa chừng.
- Có backup/snapshot/retention và rollback constraints rõ.
- Người duyệt hiểu **decommission không phải một phép thử liveness**.

### 11.2. Giai đoạn B — một lần dispatch với audit

~~~text
1. Validate target host ID and cluster in real time.
2. Verify no active/journaled conflicting operation.
3. Obtain exclusive authority and persist command intent.
4. Cross-check approval revision and safety gate freshness.
5. Dispatch supported decommission action ONCE.
6. Record transport response or lack thereof.
7. Enter read-only observe/reconcile loop.
8. Never send command again merely because controller timed out.
~~~

Nếu dùng `nodetool decommission`, lệnh **phải chạy trên đúng target sống**, theo công cụ/SOP của release. Một request có thể tiếp tục ảnh hưởng ring sau khi client điều khiển bị ngắt kết nối; trạng thái CLI không phản ánh toàn bộ operation.

### 11.3. Giai đoạn C — quan sát Leaving và chuyển dữ liệu

~~~text
Target A: Normal -> Leaving -> absent from membership
Others:  continue serving clients + receive streams
Control: observe ring, netstats, status, logs, CQL, resources
Decision: continue waiting / HOLD / escalate
~~~

Thứ tự và biểu diễn chính xác khác theo release. **Không đoán số % streaming từ một field duy nhất**; một node có thể đang replay hints/compaction hoặc đợi điều kiện khác ngoài streaming visible.

### 11.4. Giai đoạn D — xác minh node đã rời thật

Sau decommission:

- Host ID mục tiêu **không còn trong membership** theo nhiều observers (với khoảng thời gian lan truyền hợp lý).
- Node count/DC/rack bằng expected-after manifest.
- Không có replacement node ngoài kế hoạch.
- Token metadata/ownership ổn định theo expected.
- Những nodes còn lại healthy, không mất RF/CL yêu cầu.
- Streaming data transfer đã hoàn tất theo evidence được hỗ trợ.
- Representative CQL reads/writes (trong phạm vi được phép) vẫn đúng.
- Application native connections/driver metadata không giữ endpoint không hợp lệ vượt window.
- Disk/compaction/hints/retries/p95/p99 và error budget vẫn trong SLO.
- Audit record chứa command outcome, source evidence, human approval nếu cần.

**Không xem `node absent` từ một observer là bằng chứng duy nhất**; node có thể chỉ mất liên lạc tạm. Kết luận phải kết hợp membership views và lịch sử dispatch.

### 11.5. Không “lấp chỗ trống” bằng bootstrap tự động ngoài plan

Sau khi một node decommission thành công, việc cần thêm node mới là **operation riêng** với ID, target identity và approval riêng. Không tự tạo node mới chỉ vì inventory count giảm: chính decommission dự kiến làm count giảm.

Nếu workload đòi thay thế một node, xem **replacement SOP** và migration plan; không mặc định “decommission old rồi bootstrap new” có cùng consistency/capacity semantics với replace.

## 12. Bẫy khi kết hợp add/remove để giữ size cluster

### 12.1. Không để controller đồng thời đổi hai phía của topology

Đối với một change gồm thêm B, bỏ A, thứ tự phụ thuộc RF, rack placement và resource capacity. Mô hình an toàn là:

~~~text
Step 1: Bootstrap B with operation ID op-B
  -> verify B Normal, streaming, tokens, CQL, resources
  -> close bootstrap scope.

Step 2: Re-evaluate cluster and replica layout.
  -> only if approved change demands and gates pass:

Step 3: Decommission A with NEW operation ID op-A
  -> verify A absent, RF/CL, data, app SLO.
~~~

Đây là **một ví dụ cho kịch bản expansion-then-shrink được SOP duyệt**, không phải phương pháp duy nhất và không thay thế cơ chế Cassandra replace node. Thứ tự có thể khác do distribution/version/capacity; phải kiểm recipe riêng.

### 12.2. “Node replacement” có semantics riêng

Khi A chết, áp dụng decommission như khi A còn sống có thể không khả thi. Một số Cassandra versions/distributions hỗ trợ replace address/replace node operation qua startup/config. Các rủi ro gồm:

- Hai processes cùng quảng bá cùng token/identity.
- Data dir/PVC reuse sai hoặc tạo host ID mới không chủ ý.
- Counter/commitlog/hints/convergence không được đối soát.
- Seed/gossip state cũ tiếp tục quảng bá node chết.
- Replica ownership chưa ổn nhưng controller đã cleanup.

**Không** cố tự xây quy trình replacement bằng chuỗi tự động `removenode` → `bootstrap` → `cleanup` nếu chưa có SOP version-specific và approval.

### 12.3. Scale-in làm RF không thể đáp ứng

Nếu DC đang có 3 nodes và RF=3, cố scale-in xuống 2 nodes mà giữ RF=3 là **sai capacity/replication policy**. Không tự thay RF từ 3 xuống 2 để “cho decommission qua”. RF change yêu cầu đánh giá consistency, fault tolerance, data movement/repair và change riêng.

### 12.4. Multi-DC không chỉ là tổng node toàn cluster

RF được cấu hình theo DC với `NetworkTopologyStrategy`. Một DC có đủ replica không chứng minh DC khác đủ. Nếu operation nhắm dc1, health checks phải xác minh local DC availability, inter-DC streaming/network, app failover và `LOCAL_QUORUM` riêng theo từng region.

## 13. Đo streaming và tiến độ: chống kết luận giả

### 13.1. Các phép đo read-only

~~~bash
# Minh họa; kiểm tài liệu công cụ theo release.
nodetool status
nodetool netstats
nodetool tpstats
nodetool compactionstats
nodetool info
~~~

Phải lấy samples theo timestamps, node identity và observation window. `netstats` chủ yếu biểu diễn **SSTable streaming**; không được dùng để suy mọi CQL replication/repair/commitlog đều kết thúc.

### 13.2. Progress không phải elapsed time

Một job có thể:

- Stream bytes tăng nhưng tasks pending còn lớn.
- Ngừng streaming tạm do backpressure, chờ disk.
- Đổi source peers khi một node lỗi.
- Hoàn thành stream nhưng còn compaction/cache warm-up.
- Hiện trạng thái `UN` trong khi application p99 vẫn cao.

Do đó không đặt rule “sau 10 phút thì COMPLETE”. Đặt **condition-based deadline** với các trạng thái `IN_PROGRESS`, `STALL_SUSPECTED`, `UNKNOWN` và escalation.

### 13.3. Một “stall” cần được đánh giá có ngữ cảnh

Ví dụ giả định:

| UTC | Streamed GiB | Pending tasks | Disk await | App p99 | Interpretation |
|---|---:|---:|---:|---:|---|
| 10:00 | 100 | 12 | 5 ms | 120 ms | Đang tiến |
| 10:05 | 118 | 8 | 7 ms | 130 ms | Đang tiến |
| 10:10 | 118 | 8 | 100 ms | 900 ms | Nghi disk stall |
| 10:15 | 118 | 8 | 110 ms | 1.300 ms | HOLD/escalate theo policy |

Số liệu chỉ minh họa. Đừng coi một gauge bằng 0 hoặc trùng giá trị trong một lần đọc là bằng chứng **mất dữ liệu** hay **lệnh chưa chạy**.

### 13.4. Metrics quan trọng khác

| Nhóm | Tín hiệu | Nguy cơ |
|---|---|---|
| Topology | Node states/host IDs/DC-rack | Membership sai |
| Streaming | Active sessions, bytes, progress | Chuyển dữ liệu chưa xong |
| Storage | Disk free, SSTables, compaction pending | Source/destination full |
| JVM | GC pause, heap/off-heap, thread count | Coordinator/replica stalls |
| OS | CPU quota, disk await, network retransmit | Slow streams/latency |
| CQL | Read/write timeout, unavailable, p99 | RF/CL mất hiệu lực |
| Driver | Pool connections, retries, wrong peer addresses | Ứng dụng chưa hồi phục |
| Hints/repair | Backlog, jobs, errors | Data convergence chưa xong |
| Schema | Version agreement, prepared CQL | Client incompatibility |

Không chỉ xem cluster average; worst-node có thể mất hết headroom khi một replica chuyển gánh tải.

## 14. Kiểm CQL bằng Java: evidence có phạm vi

### 14.1. Vì sao `nodetool status` chưa đủ?

`nodetool` thường dùng JMX, trong khi Java Driver đi native CQL qua TLS/auth/connection pools. Một node `UN` vẫn có thể:

- Không nhận connection từ application namespace.
- Certificate SAN/truststore không tương thích.
- App role thiếu quyền `SELECT`/`MODIFY`.
- Schema/prepared CQL không tương thích sau thay đổi.
- Có read/write timeouts ở `LOCAL_QUORUM`.
- Có p99 xấu do streaming/GC/disk.

Cần **new connection canary** từ vùng ứng dụng, dùng role/CL đúng, với truy vấn bounded theo full partition key.

### 14.2. Probe schema lab/được chuẩn bị từ trước

~~~cql
-- Chỉ chạy DDL ở môi trường được phép, trước maintenance.
-- dc1 phải là tên datacenter thật theo release/config.
CREATE KEYSPACE IF NOT EXISTS topology_probe
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
} AND durable_writes = true;

CREATE TABLE IF NOT EXISTS topology_probe.probes_by_run (
    run_id uuid,
    check_id text,
    expected_value text,
    PRIMARY KEY ((run_id), check_id)
);
~~~

**Không tạo keyspace/table mới trong lúc đang decommission**; DDL có thể thay schema agreement và tạo thêm rủi ro. Với multi-DC, khai báo RF per DC theo policy. Nếu cluster có 1 node trong lab, RF/CL phải tương thích lab riêng; không sao chép `dc1:3`.

### 14.3. CQL read/write probe idempotent theo giá trị

~~~cql
-- run_id/check_id/value được cố định trong mỗi lần kiểm.
INSERT INTO topology_probe.probes_by_run
  (run_id, check_id, expected_value)
VALUES (?, ?, ?)
USING TTL 3600;

SELECT expected_value
FROM topology_probe.probes_by_run
WHERE run_id = ?
  AND check_id = ?;
~~~

Không dùng counter increment hay LWT side effect để làm smoke check. TTL có thể được refresh bởi retry, nên `idempotent` phải được định nghĩa theo semantics của **health probe**, không hứa mutation byte-for-byte hay expiry tuyệt đối giống nhau.

### 14.4. Ví dụ Java Driver 4.x có kiểm tra read-back

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.util.UUID;

public final class TopologyHealthProbe {
    private final CqlSession session;
    private final PreparedStatement put;
    private final PreparedStatement get;

    public TopologyHealthProbe(CqlSession session) {
        this.session = session;
        this.put = session.prepare(
            "INSERT INTO topology_probe.probes_by_run " +
            "(run_id, check_id, expected_value) " +
            "VALUES (?, ?, ?) USING TTL ?");
        this.get = session.prepare(
            "SELECT expected_value FROM topology_probe.probes_by_run " +
            "WHERE run_id = ? AND check_id = ?");
    }

    public boolean check(UUID runId, String checkId, String expected) {
        if (runId == null || checkId == null || expected == null)
            throw new IllegalArgumentException("Required probe values");

        BoundStatement write = put.bind(
                runId, checkId, expected, 3600)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(5))
            .setIdempotent(true);

        session.execute(write);

        BoundStatement read = get.bind(runId, checkId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(5))
            .setIdempotent(true);

        Row row = session.execute(read).one();
        return row != null
            && expected.equals(row.getString("expected_value"));
    }
}
~~~

Code minh họa các APIs thường có trong Java Driver 4.x, kiểm signature và JDK compatibility của artifact thực. `CqlSession` phải được truyền từ application với đúng local DC, contact points, TLS/auth; **tái sử dụng session**, không tạo một session mỗi probe.

Write timeout có thể là outcome chưa chắc chắn; nếu không đủ bằng chứng read-back/replica health thì gate `UNKNOWN/FAIL`, không tự retry mãi. Người vận hành phải thiết lập **retry budget tổng** cho app, driver và controller.

### 14.5. Những gì probe không chứng minh

- Một `run_id` chỉ nằm trong một replica set, không phủ hết token ring.
- `LOCAL_QUORUM` trong dc1 không tự chứng minh dc2 đã hội tụ.
- Một row nhỏ không đại diện mọi bảng có wide partitions/tombstones.
- Read-back đúng sau write không chứng minh không có duplicate side effects trong bảng khác.
- Một connection thành công chưa chứng minh mọi peer addresses còn đúng sau bootstrap.
- Không thay thế inventory/token metadata/streaming gates.

Để tăng coverage, có thể thử nhiều partition keys có chủ đích và representative business reads, vẫn phải giới hạn QPS/bytes, không query full-table scans.

## 15. Postconditions có thể xác minh độc lập

### 15.1. Bootstrap và decommission khác điều kiện kết thúc

| Điều kiện | Bootstrap PASS | Decommission PASS |
|---|---|---|
| Target host ID | Có và đúng node mới | Không còn là ring member |
| Expected node count | Tăng theo manifest | Giảm theo manifest |
| Target membership | Up/Normal | Absent theo nhiều views |
| DC/rack placement | Đúng target | Peers còn lại đúng |
| Token ownership | Đã thêm/rebalance theo policy | Đã transfer ownership theo policy |
| Streaming | Bootstrap complete | Decommission transfers complete |
| Unplanned nodes DOWN | Không | Không |
| RF/CL và CQL | Business CL/probes PASS | Business CL/probes PASS |
| Application peer discovery | Nhận được node mới/compatible | Không route tới departed node quá window |
| Resource/SLO | Stable / within envelope | Stable / within envelope |
| Hints/repair/compaction | Có kế hoạch follow-up rõ | Có kế hoạch follow-up rõ |
| Operation journal | COMPLETED với evidence | COMPLETED với evidence |

Không sử dụng một event “process exited” hay “nodetool command completed” để thay thế các postconditions.

### 15.2. Expected topology thay đổi theo pha

~~~text
Bootstrap:
  before: 6 known members
  joining: 6 normal + 1 joining (tùy observer/version)
  after: 7 normal, node new host ID confirmed

Decommission:
  before: 7 normal
  leaving: 6 normal + 1 leaving (tùy observer/version)
  after: 6 normal, target host ID absent
~~~

Các con số và giai đoạn chỉ minh họa. Không hardcode `expected_nodes=6` cho mọi phase. Với replace, node count có thể không đơn giản tăng/giảm như vậy.

### 15.3. “Absent” cần nhiều nguồn và lịch sử

Nếu node target không hiện trong status một lần:

- Có thể chỉ bị gossip unreachable.
- Có thể observer chưa đồng bộ topology.
- Có thể automation đang kết nối nhầm cluster.
- Có thể node address bị đổi, còn host ID vẫn tồn tại.
- Có thể node đã decommission xong thật.

Đòi **host ID + expected changes + nhiều observer views + operation journal + streaming evidence**, không coi một trường rỗng là proof.

## 16. Khi controller crash: reconcile trước, không dispatch lại

### 16.1. Recovery decision tree

~~~mermaid
flowchart TD
    A["Controller restart; journal has command intent"] --> B["Acquire exclusive control lease"]
    B --> C["Verify cluster, target identity, manifest revision"]
    C --> D{"Target already at expected AFTER state?"}
    D -->|Yes| E["VERIFYING: CQL, RF/CL, metrics, evidence"]
    D -->|No| F{"Joining/Leaving/streaming observed?"}
    F -->|Yes| G["IN_PROGRESS; poll read-only"]
    F -->|No| H{"Confident command never dispatched?"}
    H -->|No/Unknown| I["HOLD; human review"]
    H -->|Yes| J["Only approved operator can decide re-dispatch"]
    E --> K{"All gates PASS?"}
    K -->|Yes| L["COMPLETED"]
    K -->|No| I
    G --> D
~~~

**Quan trọng:** ngay cả khi chưa quan sát joining/leaving, vẫn có thể tồn tại một pending command hoặc stale observer. Không tự kết luận “chưa chạy” từ việc thiếu một chỉ số.

### 16.2. Những trường hợp cần HOLD chắc chắn

- Journal nói có intent nhưng cluster không thể truy cập.
- Không đọc được expected host ID/metadata của target.
- Hai controllers cùng khẳng định đang sở hữu cùng operation.
- Node đổi identity/IP/PVC mà manifest chưa cập nhật.
- Một số observers nói Leaving, số khác nói Normal quá lâu không có reconciliation.
- Streaming không có progress và metrics disk/network thiếu.
- Một thao tác topology khác xuất hiện ngoài change plan.
- CQL quorum/unavailable hoặc data correctness fail.
- Sơ đồ token/replica sau change không đáp ứng RF/CL.
- Release/tools có hành vi khác runbook và operator chưa xác nhận.

Trả `UNKNOWN` là một hành động bảo vệ dữ liệu, không phải lỗi hệ thống báo cáo.

### 16.3. Khác nhau giữa retry lệnh quản trị và retry kiểm tra

Sau controller crash, được retry các **read-only status fetches** với backoff. Không được replay:

~~~text
decommission target A
bootstrap replacement B
removenode target A
cleanup all nodes
repair all ranges
~~~

Chỉ vì báo cáo cũ chưa có `COMPLETED`. Mỗi action trên có preconditions, side effects và recovery SOP riêng.

## 17. Controller pseudocode: tách dispatcher khỏi observer

### 17.1. Hai quyền khác nhau

Một controller an toàn nên có **hai thành phần tách biệt**:

- **Observer:** chỉ đọc status, metadata, stream progress, metrics và CQL; được retry bounded.
- **Dispatcher:** có quyền topology mutation, chỉ dùng một lần khi operation state, approval và leader epoch hợp lệ; không thể bị gọi từ vòng reconcile sau crash.

Đường code có side effect phải nổi bật và được code review độc lập.

### 17.2. Java-style interfaces cho operation journal

~~~java
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

enum Action { BOOTSTRAP, DECOMMISSION }
enum State {
    NEW, APPROVED, PREFLIGHT, RESERVED,
    COMMAND_INTENT_RECORDED, COMMAND_DISPATCH_UNCERTAIN,
    IN_PROGRESS, VERIFYING, HOLD, HUMAN_REVIEW, COMPLETED
}
enum Gate { PASS, FAIL, UNKNOWN }

record NodeIdentity(
    UUID hostId,
    String datacenter,
    String rack,
    String instanceId) {}

record Operation(
    UUID operationId,
    String clusterId,
    Action action,
    NodeIdentity target,
    State state,
    long revision,
    long leaderEpoch,
    Instant updatedAt) {}

interface OperationStore {
    Optional<Operation> load(UUID id);

    // Atomic compare-and-swap ở control-plane.
    boolean compareAndSet(
        UUID id, long expectedRevision, Operation next);
}

interface ReadOnlyTopologyObserver {
    ClusterSnapshot observe(String clusterId);
}

interface ClusterSnapshot {
    boolean hasFreshObservers();
    boolean targetIdentityMatches(NodeIdentity expected);
    boolean targetJoiningOrLeaving(NodeIdentity expected);
    boolean targetAtExpectedAfterState(Operation op);
    Gate healthAndCqlPostconditions(Operation op);
}
~~~

Đây là **mẫu kiến trúc**, chưa có implementation production. Phải kiểm `OperationStore` thực sự atomic/durable; khai báo một interface CAS **không tự cung cấp** các tính chất ấy. Mẫu `NodeIdentity` thể hiện decommission với host ID đã biết; implementation bootstrap thực tế cần biểu diễn host ID **chưa được cấp** một cách tường minh (ví dụ optional) và chỉ pin immutable khi quan sát được, không diễn giải `null` như identity đã xác minh.

### 17.3. Hàm quyết định sau crash không được gây side effect

~~~java
final class SafeReconciler {
    static State nextOnRecovery(
            Operation op, ClusterSnapshot snap) {

        if (!snap.hasFreshObservers())
            return State.HOLD;

        if (!snap.targetIdentityMatches(op.target()))
            return State.HOLD;

        if (snap.targetAtExpectedAfterState(op)) {
            Gate post = snap.healthAndCqlPostconditions(op);
            if (post == Gate.PASS) return State.COMPLETED;
            if (post == Gate.FAIL) return State.HOLD;
            return State.VERIFYING;
        }

        if (snap.targetJoiningOrLeaving(op.target()))
            return State.IN_PROGRESS;

        // Không chứng minh được command chưa dispatch.
        return State.HUMAN_REVIEW;
    }
}
~~~

Không có dòng nào trong `nextOnRecovery` gọi bootstrap/decommission. Đây chỉ là hàm **phân loại observation**; khi chưa biết, nó trả `HUMAN_REVIEW` thay vì phát lệnh mới.

### 17.4. Dispatcher phải kiểm quyền trước khi side effect

~~~text
function dispatchOnce(approvedOperation):
    assert target == immutableManifestTarget
    assert preflight == PASS with fresh evidence
    assert maintenance lease is owned at current epoch
    assert no conflicting topology operation intent
    CAS operation from RESERVED to COMMAND_INTENT_RECORDED
    CAS operation to COMMAND_DISPATCH_UNCERTAIN
    invoke approved version-specific topology operation ONCE
    record response best effort
    return to READ-ONLY reconciliation

on timeout or crash:
    DO NOT invoke again
    acquire authority and inspect journal + live cluster
    OBSERVE / VERIFY / HOLD / HUMAN_REVIEW
~~~

Có một **crash gap** giữa CAS và invoke. Nếu controller chết đúng chỗ đó, không thể tự biết command có được gửi hay chưa. Cần human review và bằng chứng từ hạ tầng/Cassandra, không tự lấy `dispatch_count=0` làm lý do gửi lại.

### 17.5. Mọi tầng retry phải được kiểm

- CI pipeline có thể tự chạy lại job khi process exit khác 0.
- Kubernetes Job/Controller có thể restart container trong lúc side effect còn chạy.
- HTTP SDK hoặc proxy có thể tự retry request quản trị.
- Một on-call engineer có thể bấm re-run change khi không có response.
- Hai workflows có thể cùng chạy trên một cluster nếu scope lock sai.

Không chỉ tắt vòng retry trong một hàm Java. **Topology dispatcher phải dùng adapter retry-disabled + durable dedupe + quyền độc quyền**, còn observer dùng retry bounded.

## 18. Gates theo phase và fail-closed

### 18.1. Preflight cho BOOTSTRAP

~~~text
[ ] Cluster ID, manifest hash, change approval đúng.
[ ] Node mới và volume identity chưa thuộc ring.
[ ] Không mang system.local data/identity của node khác.
[ ] DC/rack/token/seed/TLS/network config đúng.
[ ] Expected existing members đầy đủ và healthy.
[ ] RF/CL và user CQL SLO đạt.
[ ] Không có JOIN/LEAVE/REPLACE hoặc repair xung đột.
[ ] Disk/network/GC/CPU trên source/destination đủ headroom.
[ ] Journal/lease/revision hoạt động an toàn.
[ ] Có operator và recovery runbook rõ.
~~~

Nếu target đã xuất hiện `UJ` mà journal nói NEW, phải **HOLD**: có thể runner khác đã start hoặc journal sai. Không khởi động node thứ hai.

### 18.2. Preflight cho DECOMMISSION

~~~text
[ ] Exact host ID đang Up/Normal, đúng DC/rack.
[ ] Không đã Leaving/decommissioning/absent.
[ ] Không có unexpected node DOWN.
[ ] Remaining DC/rack nodes đáp ứng RF/CL/fault tolerance.
[ ] Peers tiếp nhận streaming có disk/network headroom.
[ ] Repair/hints/compaction workload được xem xét.
[ ] App CQL ở CL production đạt SLO.
[ ] No conflicting topology operation.
[ ] Approval và target identity đã khóa.
[ ] Có kế hoạch khi node chết giữa decommission.
~~~

### 18.3. Khi đang chạy

~~~text
if observation source stale:
    HOLD next mutation; request fresh evidence
if target identity/topology changed unexpectedly:
    HOLD, human review
if replica availability or app CQL hard gate FAIL:
    stop next step and invoke recovery SOP
if streaming still advancing and resources safe:
    continue read-only observation
if target expected end-state and health checks PASS:
    verify stable observation window, then COMPLETE
~~~

HOLD thường nghĩa **ngừng dispatch các thay đổi mới**, không tự kill Cassandra process đang chuyển dữ liệu. Khả năng cancel/abort tùy release/SOP, không giả định an toàn.

### 18.4. Postflight

| Gate | BOOTSTRAP | DECOMMISSION |
|---|---|---|
| Identity | New host ID Up/Normal | Exact host ID absent |
| Node count | Expected increased | Expected decreased |
| Placement | New DC/rack/token correct | Peers placement correct |
| Streaming | Completed/accepted | Completed/accepted |
| RF/CL | No regression | Remaining replicas meet policy |
| CQL | Read/write probes and business query | Read/write probes and business query |
| Resource/SLO | Source/destination stable | Remaining nodes stable |
| Journal | Audited completed evidence | Audited completed evidence |

## 19. Timeouts, backoff và observation window

### 19.1. Phân biệt các deadline

| Mốc | Ý nghĩa | Không được suy |
|---|---|---|
| CLI/transport timeout | Caller chưa nhận response | Topology command chưa bắt đầu |
| Lease expiry | Owner không renew lease | Cassandra đã dừng operation |
| Read-only poll timeout | Observer không nhận một sample | Node chắc chắn down |
| Operation deadline | Vượt ngân sách thời gian | An toàn tự hủy command |
| Observation window | Đủ samples để kết luận ổn định | Toàn cluster chắc chắn perfect |

Vượt deadline → `HOLD`, cảnh báo và human review theo policy; **không tạo lần dispatch thứ hai**.

### 19.2. Poll observation có backoff

~~~text
initialDelay = policy-controlled interval
nextDelay = min(maxDelay, exponentialBackoff * jitter)
overallDeadline = change-specific
maxConcurrentObservers = bounded per DC
allObservations = timestamped, source-identified
~~~

Không cho PASS vì đã đợi số phút cố định; không poll JMX hàng trăm lần/giây. Nếu observation không còn fresh thì kết luận `UNKNOWN`.

### 19.3. Hysteresis với điều kiện an toàn

Có thể yêu cầu nhiều samples và observers khớp nhau trước PASS. Tuy nhiên **hard FAIL** như đúng host ID biến mất sai plan, RF/CL mất quorum hoặc data corruption suspicion phải chặn ngay, không đợi histogram đủ sample mới tạm dừng.

## 20. Audit trail đủ để đối soát sau restart

### 20.1. Audit event có source và revision

~~~yaml
# Ví dụ report record, không phải file/config production.
event_id: "audit-043"
operation_id: "f25be1dc-58ba-4d11-af04-0c7c80080008"
change_id: "CHG-2026-1121-008"
timestamp_utc: "2026-11-21T10:10:00Z"
controller_epoch: 42
journal_revision: 9
cluster_id: "cassandra-telemetry-production"
operation_type: DECOMMISSION
target_host_id: "11111111-2222-3333-4444-555555555555"
target_datacenter: dc1
target_rack: rack2
event_kind: OBSERVATION
state_before: COMMAND_DISPATCH_UNCERTAIN
state_after: IN_PROGRESS
evidence:
  sources: ["approved-observer-A", "approved-observer-B"]
  detail: "Leaving observed, streaming active"
decision: WAIT_AND_RECONCILE
actor: "authorized-controller"
~~~

Audit cần ghi **intent trước khi side effect**, identity/cluster/scope, transport outcome hoặc UNKNOWN, observations, human approvals và final postconditions. Không ghi JMX passwords, tokens, private keys hay data của khách hàng.

### 20.2. Durable storage phải thực sự durable

Một file `audit.log` trong container ephemeral có thể mất khi pod reschedule. Journal cần storage bền vững bên ngoài process, có transaction/CAS được chứng minh, backup, ACL và retention. Gắn `journal_revision`/`controller_epoch` để phân biệt hai worker tranh quyền.

Cần mô hình hóa hai crash windows:

1. **Sau khi persist intent, trước dispatch:** có thể chưa phát side effect nhưng journal đã ghi “uncertain”.
2. **Sau dispatch, trước persist response:** Cassandra có thể đang thay ring dù journal chưa biết.

Nếu hệ không thể chứng minh exact outcome, hãy **HUMAN_REVIEW** thay vì gỡ cờ “uncertain” bằng cách xóa journal.

### 20.3. Evidence và inference khác nhau

| Ghi nhận | Được phép kết luận |
|---|---|
| `nodetool status` ở observer A thấy `UL` | Observer A nhìn thấy target Leaving ở thời điểm đó |
| CLI timeout | Controller không có response đáng tin |
| Streamed bytes tăng qua nhiều samples | Có tiến độ streaming trên metric ấy |
| Target không hiện trong một status output | Chưa đủ khẳng định decommission complete |
| Node Up/Normal + CQL read PASS | Chỉ một phần liveness/query đúng |
| p99 đo 10 requests thấp | Không đủ mẫu cho SLO production |
| Journal state=COMPLETED nhưng cluster state khác | **Inconsistency: HOLD**, kiểm audit và live evidence |

### 20.4. Mẫu report kết thúc

~~~text
Change and operation IDs
Action: BOOTSTRAP / DECOMMISSION
Cluster ID, target host ID, DC/rack, volume/instance identity
Manifest hash/revision, approver, controller epoch
Dispatch intent count, request response (ACK/TIMEOUT/UNKNOWN)
Observed phase timeline with node/source/time
Before vs after expected membership/token ownership
Streaming/repair/hints/compaction observations
CQL probes with CL, local DC and representative query results
Resource/SLO p95/p99, retries, error/timeout rate
Final: COMPLETED or HOLD/HUMAN_REVIEW, limitations, owner
~~~

Không tạo `SUCCESS` tổng quát khi thiếu source/UTC timestamp, hoặc `UNKNOWN` bị ghi đè bằng một sample cũ.

## 21. Kubernetes, VM và service discovery không thay thế topology gates

### 21.1. Kubernetes StatefulSet/PVC và operator

Kubernetes `StatefulSet`, pod ordinal, PV/PVC và readiness probes giúp quản lý process/storage nhưng không tự bảo đảm Cassandra đã join/leave ring an toàn.

Cần đề phòng:

- Pod ordinal và tên DNS được tái dùng.
- PVC chứa data/system tables của node khác.
- Readiness chỉ kiểm TCP port, không kiểm RF/CL.
- Node mới đã `UN` nhưng streaming/compaction chưa phục hồi.
- Hai controllers cùng scale StatefulSet hoặc cạnh tranh operator.
- Operator bị restart trong lúc Cassandra vẫn Joining/Leaving.

Nếu cluster có **Cassandra operator hỗ trợ bootstrap/decommission**, ưu tiên API/state machine và SOP chính thức của operator, **không chạy script ngoài cạnh tranh quyền topology**. Tên custom resources/fields tùy operator/distribution.

### 21.2. Service discovery và gossip không cùng dữ liệu

Cassandra gossip có thể thấy node `UN`, nhưng Java Driver/client chưa khám phá peer, network policy chặn native port, TLS SAN không khớp DNS hoặc Kubernetes Service chưa cập nhật endpoints.

Sau decommission, driver có thể còn stale peer connections cho node cũ; điều đó không có nghĩa decommission thất bại, nhưng postflight cần xác minh **các kết nối mới và các đường CQL chủ chốt** đã phục hồi trong thời gian policy cho phép.

### 21.3. VM/bare-metal provisioning

Một cloud API timeout sau lệnh tạo VM không chứng minh VM chưa được tạo. Cần kiểm instance ID/resource state bằng API đọc, đối chiếu volume/host IDs và journal. Không tạo VM thứ hai chỉ vì request tạo VM chưa nhận response.

Đặc biệt, automation không nên chọn disk hoặc machine mới bằng selector dạng `first available` sau crash. Target storage identity phải khóa theo approved manifest.

## 22. Quyền vận hành và an toàn secret

### 22.1. Least privilege

| Principal | Quyền cần | Tránh mặc định |
|---|---|---|
| Read-only observer | JMX/metrics/metadata read theo policy | Decommission/removenode |
| Operation journal writer | CAS state/audit | SSH/root trên mọi Cassandra nodes |
| Dispatcher | Một action đã approve, đúng cluster/target | Wildcard admin access |
| Human approver | Phê duyệt change và exception | Tự ký tự thực thi thiếu dual control |
| CQL probe role | `SELECT`/`MODIFY` trên probe table | Cassandra superuser |
| Report viewer | Redacted logs/metrics | Raw secrets/heap dumps |

`nodetool` thường qua JMX với authentication/TLS riêng; một CQL role có SELECT không tự được quyền quản lý JMX. Đừng cấp quyền admin cho toàn bộ controller chỉ để health probe đọc được dữ liệu.

### 22.2. Command injection và target substitution

~~~text
# ANTI-PATTERN pseudocode - KHÔNG dùng thực tế.
shell("nodetool -h " + userSuppliedHost + " decommission")
~~~

Dùng typed arguments của công cụ được hỗ trợ, allowlist host ID/cluster, approved manifest revision và không nhận flags/shell fragments từ user input. Cần kiểm identity ngay **trước dispatch**, không chỉ khi mở change ticket.

### 22.3. Mất quan sát vì rotate secret giữa chừng

Nếu JMX/TLS/auth credentials được rotate khi decommission đang chạy, controller có thể mất kết nối trong khi Cassandra vẫn streaming.

Phản ứng an toàn:

1. Ghi `UNKNOWN` cho observation.
2. Không retry topology command.
3. Khôi phục trust/secret theo runbook riêng.
4. Đọc lại journal và xác minh target host ID.
5. Tiếp tục read-only reconcile; không tự kết luận “command failed”.
6. Nếu có split-brain control plane, HOLD và human review.

### 22.4. Giữ cluster hoạt động dù controller đã thất bại

Khi controller không còn authority, cần dừng phát **các thay đổi mới**. Không tự kill JVM/node trên production chỉ để “giải phóng lock”: side effect đang chạy trong Cassandra không được bảo đảm dừng ngay. Revoke admin access hoặc lock để **ngăn dispatch tiếp** phải được lên kế hoạch mà không làm hỏng ongoing streaming.

## 23. Runbook A — Bootstrap timeout, controller muốn tạo node lần hai

**Tình huống:** Cloud API timeout sau yêu cầu provision/start node B. Controller không có `created=true` nhưng node B có thể đã start và đang streaming.

1. **HOLD dispatch**: không tạo node/VM/pod/PVC mới.
2. Đọc durable operation ID, approved manifest, instance/volume identity và command intent.
3. Hỏi infrastructure API **read-only**: B có tồn tại/đang pending không?
4. Thu `nodetool status`, gossip và streaming evidence từ nhiều observers.
5. So host ID/DC/rack/token với manifest, không chỉ DNS/IP.
6. Nếu B Joining/streaming, đánh `IN_PROGRESS`, poll read-only.
7. Nếu B Up/Normal, chuyển `VERIFYING` để kiểm CQL, RF/CL, p99 và resources.
8. Nếu B không quan sát được nhưng intent có thể đã gửi, đánh `HUMAN_REVIEW`.
9. Chỉ owner theo SOP quyết định recovery khi có bằng chứng; không tự provision lần nữa.
10. RCA: provider idempotent request IDs, durable journal và test crash window.

**Không dùng hostname/IP khác làm “retry bootstrap”**: đó có thể là một node mới trái kế hoạch.

## 24. Runbook B — Lease hết hạn giữa decommission

**Tình huống:** Controller A gọi decommission, mất network khi streaming; B lấy lease với epoch mới.

1. B đọc journal thấy `COMMAND_INTENT_RECORDED`/`COMMAND_DISPATCH_UNCERTAIN`.
2. B **không** gọi decommission lần hai.
3. B xác minh cluster/host ID/manifest revision và owner epoch.
4. B quan sát `status/netstats`, JMX/logs/metrics qua approved observers.
5. Target đang Leaving/streaming → `IN_PROGRESS`, tiếp tục quan sát.
6. Target absent → kiểm đủ postconditions rồi `COMPLETED`.
7. Target Normal nhưng không rõ command đã gửi → `HUMAN_REVIEW`.
8. Ngăn stale worker A được cấp quyền dispatch mới; epoch không tự hủy Cassandra side effects.
9. Kiểm không có topology mutation ngoài plan đang xen vào.
10. Test lại lease expiry/reconcile sau incident, lưu audit chronology.

**Lease chọn người điều phối, không hủy decommission đã đến Cassandra.**

## 25. Runbook C — Host ID, PVC hoặc IP không khớp manifest

**Tình huống:** Live host ID tại địa chỉ target khác host ID đã phê duyệt, hoặc node bootstrap mount volume chứa dữ liệu của node khác.

1. Dừng dispatch, giữ nguyên journal/approval/evidence.
2. So cluster ID, host ID, DC/rack, VM/pod/PVC và node address.
3. Kiểm có replacement, reimage, rescheduling hoặc manual action ngoài kế hoạch.
4. Không dùng IP/DNS/ordinal làm lý do cập nhật target tự động.
5. Đọc metadata read-only, không sửa `system.local/system.peers_v2` bằng tay.
6. Không xóa data directory/`system` keyspace để ép bootstrap.
7. Bảo toàn logs và disk identity cho replacement SOP.
8. Operator phải duyệt manifest/change mới nếu thực thể mục tiêu khác.
9. Re-run RF/CL/topology/CQL gates sau khi xử lý identity.
10. Thêm cảnh báo host ID/PVC mismatch vào preflight.

**Identity mismatch = hard STOP**, không được bypass để đạt node count.

## 26. Runbook D — Bootstrap/decommission streaming đứng yên

**Tình huống:** Streamed bytes không tăng trong nhiều samples, disk await/GC tăng, app p99 xấu.

1. Xác định action, node, token ranges và source/destination.
2. So multi-sample streaming progress; một snapshot đứng yên chưa đủ gọi stall.
3. Kiểm disk free/await, network RTT/retransmits, internode TLS/gossip và logs.
4. Kiểm `tpstats`, `compactionstats`, GC, hints và repair contention.
5. Kiểm thêm bất ngờ node DOWN hoặc RF/CL unavailable không.
6. Không chạy thêm topology, major compaction, repair hoặc cleanup để “kích tiến độ”.
7. Giảm background load không thiết yếu theo SOP, giữ business traffic SLO.
8. Theo dõi progress/metrics trong deadline; phân loại `IN_PROGRESS`/`HOLD`.
9. Nếu cần abort/recovery, áp dụng lệnh release-specific qua approval; không mặc định kill -9 là rollback.
10. RCA capacity, network, retry storm và streaming thresholds.

**CLI accepted chưa nghĩa data movement đã hoàn tất.**

## 27. Runbook E — Target decommission đã DOWN hoặc absent

**Tình huống:** Node A chuyển `DN` trước dispatch, hoặc status không còn row tương ứng.

1. Dừng controller; không gửi decommission vào IP bất kỳ.
2. Phân biệt DOWN, unreachable, Leaving, đã absent hay observer stale.
3. So exact host ID, cluster/DC/rack và journal history.
4. Kiểm RF/CL, replica health và CQL errors trên remaining nodes.
5. Xác định node có thể phục hồi với cùng identity/data không.
6. Nếu đã decommission xong, postflight đầy đủ; không phát lại.
7. Nếu chết trước operation, chuyển sang **node-failure/replace/removal SOP**.
8. Không tự `removenode` chỉ vì decommission không dùng được.
9. Không hạ RF/CL để làm pipeline xanh.
10. Audit phạm vi action mới và human approval nếu cần.

**Clean decommission của node sống khác loại bỏ node đã chết.**

## 28. Runbook F — Operation thứ hai xuất hiện ngoài kế hoạch

**Tình huống:** B đang bootstrap thì workflow khác decommission A hoặc một kỹ sư chạy lệnh topology thủ công.

1. Dừng toàn bộ **dispatch mới** trong cluster scope.
2. Xác định operations nào đã gây side effects theo journal/logs/ring.
3. Không tự gửi lệnh đối nghịch để “undo”.
4. Kiểm token/replica sets, DC/rack và RF/CL của các changes liên quan.
5. Theo dõi p99/CPU/GC/disk/network và giới hạn nonessential workloads nếu cần.
6. Kiểm lease/epoch, approvals, RBAC và external admin access.
7. Với transfer đang chạy, quan sát read-only; chưa gọi operation khác.
8. Human incident commander quyết định thứ tự recovery theo SOP.
9. Sau ổn định, re-run preflight với operation IDs và approval mới.
10. RCA scope lock, CI retry, operator competition và quyền truy cập.

**Không thể có hai điều phối viên độc lập cùng cho phép đổi ring và vẫn gọi đó là serialized maintenance.**

## 29. Runbook G — Topology đạt nhưng LOCAL_QUORUM/p99 thất bại

**Tình huống:** Node B `UN` hoặc A đã absent, nhưng Java Driver `LOCAL_QUORUM` timeout, data mismatch hoặc p99 tăng.

1. Giữ `VERIFYING`/`HOLD`, chưa đánh `COMPLETED`.
2. Kiểm RF/CL/DC/rack và replica placement của workload bị lỗi.
3. Kiểm client local DC, peer discovery, native TLS/auth/port.
4. Thử CQL probe read/write trong table riêng và representative bounded business query.
5. Phân loại `Unavailable`, timeout, schema/codec và auth, không gộp thành “node down”.
6. So worst-node resources, compaction/streaming/hints và retry rate.
7. Không hạ CL hoặc tăng timeout vô hạn để tạo PASS giả.
8. Với data mismatch, điều tra TTL, day bucket, replicas và repair policy.
9. Nếu postflight không đạt, human owner kích hoạt recovery/rollback SOP nếu còn khả thi.
10. Chỉ close khi CQL correctness/error/p99/capacity và remaining replicas đạt.

**Một key canary PASS không kiểm hết token ranges hay tất cả DCs.**

## 30. Runbook H — Autoscaler/CI tự chạy lại topology step

**Tình huống:** Jenkins job được retry hoặc Kubernetes autoscaler xóa pod cùng lúc controller đang đổi ring.

1. Pause competing autoscale/maintenance pipelines theo quyền vận hành.
2. So `operation_id`, retries, CI attempt IDs và leadership epochs.
3. So desired count của orchestrator với actual Cassandra membership/host IDs.
4. Không scale count chỉ vì pod/node count thấp.
5. Nếu operation active/uncertain, reconcile read-only và HOLD.
6. Kiểm startup hooks, job restart policy và HTTP/JMX SDK auto retry.
7. Dùng một dispatcher authority và lock scope cluster/topology theo SOP.
8. Re-run job phải cùng operation ID, không tạo intent mới.
9. Diễn tập crash, API timeout, lease expiry, duplicate workflow và stale worker trong lab.
10. Chỉ bật lại automation khi không còn concurrent actors và cluster đạt postconditions.

**Pod scaling không tự di chuyển token ownership an toàn cho Cassandra.**

## 31. Ma trận kiểm thử controller và topology gates

Dùng unit tests với mock observer/journal cho state logic, integration lab cho CQL, và **cluster fault lab riêng** cho node membership/streaming. Không gây node failure hoặc decommission production chỉ để kiểm thử.

| ID | Tình huống | Kết quả an toàn |
|---|---|---|
| T01 | NEW chưa approved | Không dispatch |
| T02 | APPROVED nhưng preflight UNKNOWN | HOLD |
| T03 | Node DN ngoài kế hoạch | FAIL/HOLD |
| T04 | Status chỉ 5/6 nodes nhưng đều UN | Inventory mismatch |
| T05 | Bootstrap target đã tồn tại trong infrastructure | Reconcile, không tạo instance mới |
| T06 | New node host ID trùng member cũ | Hard STOP |
| T07 | Node mới vào sai DC/rack | FAIL/HOLD |
| T08 | B đã Joining trước intent dispatch | Không dispatch lần nữa |
| T09 | B UN nhưng streaming chưa verified | VERIFY/HOLD |
| T10 | Provision API timeout | COMMAND_DISPATCH_UNCERTAIN |
| T11 | Crash sau journal intent, trước command | Human review nếu không chứng minh outcome |
| T12 | Crash sau command, trước persist response | Read-only reconcile |
| T13 | Lease hết hạn khi streaming vẫn chạy | Owner mới không dispatch |
| T14 | Worker epoch cũ cố ghi state | CAS/epoch reject |
| T15 | Hai controllers reserve cùng scope | Chỉ một có quyền |
| T16 | Same operation ID được CI retry | Không tạo intent mới |
| T17 | Khác operation ID nhưng cùng cluster đang active | Block conflict |
| T18 | Admin manual command không qua journal | HOLD/escalate |
| T19 | Decommission target không Up/Normal | Không dispatch |
| T20 | Target đã Leaving | Observe, không dispatch |
| T21 | Target absent chỉ từ một observer | Không COMPLETE |
| T22 | Target absent nhưng CQL FAIL | HOLD |
| T23 | IP reuse/host ID đổi | Identity hard STOP |
| T24 | PVC chứa Cassandra identity khác | Không provision/start |
| T25 | RF=3 nhưng DC dự kiến chỉ còn 2 nodes | Reject/plan riêng |
| T26 | Replica DOWN trước decommission | HOLD theo fault budget |
| T27 | CQL ONE PASS nhưng LOCAL_QUORUM FAIL | CQL hard gate FAIL |
| T28 | TLS/new connection fail sau bootstrap | Postflight FAIL |
| T29 | Write/read canary PASS, business query timeout | Không COMPLETE |
| T30 | p99 vượt absolute SLO dù target UN | HOLD |
| T31 | Disk free thấp trước streaming | Preflight FAIL |
| T32 | Streamed bytes đứng yên một sample | Cần thêm evidence |
| T33 | Streaming stall lâu và disk await cao | HOLD/escalate |
| T34 | netstats trống nhưng target Leaving | Không tự COMPLETE |
| T35 | Schema agreement fail | HOLD |
| T36 | Java prepared query error sau upgrade | Compatibility FAIL |
| T37 | Metrics/JMX missing | UNKNOWN, không zero |
| T38 | Observer samples stale | UNKNOWN |
| T39 | nodetool output format không parse được | UNKNOWN |
| T40 | Job/SDK tự retry decommission step | Dispatcher chặn |
| T41 | Provider API tự retry VM provision | Idempotency ID hoặc block |
| T42 | Repair/compaction đang vượt resource budget | HOLD |
| T43 | Replacement operation ngoài plan xuất hiện | Human review |
| T44 | Journal CAS/persist fail | Không dispatch |
| T45 | CLI exit=0 nhưng target vẫn Leaving | IN_PROGRESS/HOLD |
| T46 | Overall deadline hết trong khi transfer đang chạy | Escalate, không retry |
| T47 | Counter reset sau restart | Không tính nhầm progress |
| T48 | Bootstrap đúng end state + CQL/resource PASS | COMPLETE |
| T49 | Decommission đúng end state + CQL/resource PASS | COMPLETE |
| T50 | Missing hard gate trong postflight | UNKNOWN/HOLD, không COMPLETE |

### 31.1. Tầng test và giới hạn

- **Unit:** immutable manifest validation, CAS/lease/epoch conflicts, state machine, no-dispatch recovery, inventory equality, stale observer handling.
- **Integration:** durable journal, infrastructure API mock, CQL probe, metrics parser, controller cancellation.
- **Cluster lab:** Joining/Leaving/streaming, quorum under node fault, multi-DC local routing, disk pressure, node replacement.
- **Failure-injection controller:** crash windows trước/sau dispatcher, timeout, lost network, two leaders, duplicate CI jobs, force-stop observer.

Một lab Cassandra single-node RF=1 không thể chứng minh RF=3/LOCAL_QUORUM trong multi-rack/multi-DC. Không coi test “no exception” là đủ; cần assert số lần topology command được phát.

### 31.2. Điều kiện dừng fault test

~~~text
[ ] Unexpected node down hoặc membership khác plan.
[ ] RF/CL không còn đạt trong lab.
[ ] Disk/memory/GC/IO pressure vượt guardrails.
[ ] Journal/lease consistency không xác định.
[ ] Hai actors có khả năng cùng dispatch.
[ ] Observations stale, missing hoặc parser hỏng.
[ ] Data correctness probe fail.
[ ] Recovery plan không còn khả thi trong giới hạn lab.
~~~

**Dừng test vì guardrail là một kết quả hợp lệ.**

## 32. JUnit: kiểm reconcile không dispatch lại

### 32.1. Các test quan trọng

Ví dụ JUnit 5 giả định các records/interfaces `Operation`, `ClusterSnapshot`, `SafeReconciler` đã định nghĩa ở mục 17; cần JDK hỗ trợ Java records, không dùng làm code production trực tiếp.

~~~java
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SafeReconcilerTest {
    private Operation operation() {
        return new Operation(
            UUID.randomUUID(), "cluster-lab",
            Action.DECOMMISSION,
            new NodeIdentity(
                UUID.randomUUID(), "dc1", "rack1", "vm-A"),
            State.COMMAND_DISPATCH_UNCERTAIN,
            5L, 42L, Instant.EPOCH);
    }

    private ClusterSnapshot observed(
            boolean fresh, boolean sameIdentity,
            boolean moving, boolean after, Gate post) {

        return new ClusterSnapshot() {
            public boolean hasFreshObservers() {
                return fresh;
            }
            public boolean targetIdentityMatches(
                    NodeIdentity id) {
                return sameIdentity;
            }
            public boolean targetJoiningOrLeaving(
                    NodeIdentity id) {
                return moving;
            }
            public boolean targetAtExpectedAfterState(
                    Operation op) {
                return after;
            }
            public Gate healthAndCqlPostconditions(
                    Operation op) {
                return post;
            }
        };
    }

    @Test void staleEvidenceHolds() {
        assertEquals(State.HOLD, SafeReconciler.nextOnRecovery(
            operation(), observed(false, true, false, false,
                                   Gate.UNKNOWN)));
    }

    @Test void activeStreamDoesNotRetrigger() {
        assertEquals(State.IN_PROGRESS,
            SafeReconciler.nextOnRecovery(
                operation(), observed(true, true, true, false,
                                      Gate.UNKNOWN)));
    }

    @Test void uncertainDispatchGoesToHuman() {
        assertEquals(State.HUMAN_REVIEW,
            SafeReconciler.nextOnRecovery(
                operation(), observed(true, true, false, false,
                                      Gate.UNKNOWN)));
    }

    @Test void afterStateRequiresCqlAndHealth() {
        assertEquals(State.HOLD, SafeReconciler.nextOnRecovery(
            operation(), observed(true, true, false, true,
                                  Gate.FAIL)));
    }

    @Test void verifiedAfterStateCompletes() {
        assertEquals(State.COMPLETED,
            SafeReconciler.nextOnRecovery(
                operation(), observed(true, true, false, true,
                                      Gate.PASS)));
    }
}
~~~

### 32.2. Test bất biến quan trọng nhất

~~~text
Given:
  Stored journal state COMMAND_DISPATCH_UNCERTAIN;
  controller restarts, leader epoch changes;
  snapshot shows target Leaving.

When:
  reconcile called 100 times, including transient poll errors.

Then:
  topologyCommandAdapter.invocationCount == 0
  operation stays IN_PROGRESS / HOLD / VERIFYING
  no extra VM/pod/PVC instance is created.
~~~

Unit test chứng minh code branch của controller, **không chứng minh không có admin nào gọi lệnh ngoài controller**. Cần RBAC/audit/control-plane process để đạt exclusivity.

## 33. Câu hỏi luyện tập có đáp án

### Câu 1 — Timeout của lệnh decommission

Controller gửi decommission rồi timeout. Điều này chứng minh command chưa được Cassandra nhận chưa?

**Đáp án:** Không. Lệnh có thể đã làm target Leaving/streaming. Ghi outcome UNKNOWN và reconcile read-only; không dispatch lại.

### Câu 2 — `nodetool bootstrap`

Một script có thể gọi `nodetool bootstrap` chung cho mọi Cassandra version không?

**Đáp án:** Không. Bootstrap thường xảy ra khi node mới startup với cấu hình join; API/flags và khả năng vận hành tùy release/operator.

### Câu 3 — Restart và identity

Node cũ restart với data directory có host ID sẵn. Có nên cấp host ID mới?

**Đáp án:** Không. Restart phải giữ đúng data/identity; đổi identity có thể tạo member khác, cần replacement SOP.

### Câu 4 — IP reuse

IP target A đã được pod B dùng lại. Có thể decommission chỉ dựa trên IP trong ticket cũ?

**Đáp án:** Không. Cần exact host ID/cluster/DC/rack/PVC/instance từ manifest được duyệt.

### Câu 5 — Lease expiry

Controller A mất lease khi Cassandra vẫn decommission. B được lease epoch mới có nên gửi lại lệnh?

**Đáp án:** Không. Lease chỉ đổi owner điều phối, không hủy side effect Cassandra đang chạy.

### Câu 6 — Fencing

Fencing epoch 42 trong journal có ngăn một command Cassandra đã gửi bởi epoch 41 không?

**Đáp án:** Không có bảo đảm phổ quát. Management command không nhất thiết nhận/kiểm epoch; cần ngăn dispatch mới và read-only reconciliation.

### Câu 7 — Crash gap

Intent đã ghi nhưng controller crash ngay trước dispatch. Controller B phải làm gì?

**Đáp án:** Thu bằng chứng từ infrastructure API, Cassandra ring, logs và journal. Nếu không biết command thực sự đã gửi hay chưa, HOLD/HUMAN_REVIEW.

### Câu 8 — Exit code

`nodetool decommission` exit 0 nghĩa target đã rời và app hết lỗi?

**Đáp án:** Chưa đủ. Kiểm exact host ID absent theo nhiều observers, token/replica placement, streaming, RF/CL, CQL correctness, p99 và resources.

### Câu 9 — Một observer

Node A không hiện trong output `nodetool status` của observer X. Có thể đánh COMPLETE?

**Đáp án:** Không. Có thể gossip view stale, network partition hoặc nhầm cluster. Cần nhiều nguồn và operation history.

### Câu 10 — Node DN

Decommission target đã DOWN. Có nên gọi lại lệnh trên một node khác?

**Đáp án:** Không. Clean decommission khác node-failure removal/replacement; chuyển SOP có phê duyệt.

### Câu 11 — RF và scale-in

DC có 3 nodes RF=3, muốn giảm còn 2 mà giữ RF=3. Có an toàn không?

**Đáp án:** Không. Phải thiết kế lại replication/fault tolerance/capacity bằng change riêng, không tự hạ CL/RF để bypass gate.

### Câu 12 — Quorum

RF=3, app LOCAL_QUORUM, một replica DOWN nhưng requests vẫn thành công. Có thể tự động restart thêm một replica không?

**Đáp án:** Không mặc định. Khả năng có đủ ACK hiện tại không có nghĩa còn headroom để mất thêm node.

### Câu 13 — Rack placement

Node mới `UN` nhưng nằm sai rack. Có PASS bootstrap không?

**Đáp án:** Không. Failure domain/replica placement có thể sai manifest; cần HOLD và kiểm token/rack/DC policy.

### Câu 14 — Streaming một sample

Streamed bytes không tăng trong một sample. Có chứng minh operation treo?

**Đáp án:** Không. Cần window nhiều samples, disk/network/GC, log và phase-specific observations.

### Câu 15 — `netstats`

`nodetool netstats` trống nghĩa mọi hints/repair/replication traffic đều xong?

**Đáp án:** Không. Công cụ chủ yếu phản ánh SSTable streaming; dùng metrics riêng cho hints, repair và CQL.

### Câu 16 — Source resource

Node mới có disk trống nhưng peers source đầy disk/compaction backlog. Có nên bootstrap?

**Đáp án:** Không tự PASS. Bootstrap stream từ peers nên cần headroom ở cả nguồn và đích.

### Câu 17 — CQL probe CL

Node `UN`, probe `ONE` PASS nhưng app `LOCAL_QUORUM` timeout. Overall?

**Đáp án:** FAIL/HOLD. Probe chưa đại diện CL của workload nghiệp vụ.

### Câu 18 — Một probe key

Một `run_id` write/readback PASS chứng minh mọi token range khỏe chưa?

**Đáp án:** Không. Key thuộc một replica set; cần topology/coverage/representative reads và per-DC checks.

### Câu 19 — Cleanup

Bootstrap vừa xong. Có nên tự chạy cleanup toàn cluster ngay để giảm disk?

**Đáp án:** Không. Cleanup là operation storage có side effect, cần ownership/retention/version/capacity gates và SOP riêng.

### Câu 20 — Repair

Decommission đang chậm. Có nên tự chạy repair toàn cluster để “đẩy stream”?

**Đáp án:** Không. Repair có thể làm I/O pressure nặng hơn; điều tra nguyên nhân trước.

### Câu 21 — CQL no row

CQL canary query theo event day trả 0 row nhưng node healthy. Đã chứng minh mất dữ liệu sau bootstrap?

**Đáp án:** Chưa. Có thể sai partition key/day bucket, TTL expire, fixture chưa được ghi hoặc consistency lag theo policy.

### Câu 22 — Kubernetes

Scale StatefulSet từ 6 xuống 5 có bảo đảm clean Cassandra decommission không?

**Đáp án:** Không. Pod count khác ring membership, token ownership và streaming correctness.

### Câu 23 — Hai controller

CI và Cassandra operator cùng có quyền thay topology. Chỉ khóa CI pipeline có đủ?

**Đáp án:** Không. Lock/quy trình phải bao phủ tất cả actors có side-effect privilege; cần ownership và audit.

### Câu 24 — Snapshot stale

Preflight 30 phút trước PASS nhưng giờ metrics không reachable. Có tiếp tục decommission?

**Đáp án:** Không. Khi không có fresh evidence, đánh UNKNOWN/HOLD.

### Câu 25 — Rollback

Decommission giữa chừng, controller muốn kill -9 JVM để “undo”. Có an toàn?

**Đáp án:** Không mặc định. Các replica đã có thể chuyển data/tokens; recovery/abort theo release SOP và human approval.

### Câu 26 — Schema

Node mới Up/Normal nhưng Java prepared CQL query fail. Bootstrap đã hoàn tất ở cấp app?

**Đáp án:** Chưa. Giữ VERIFYING/HOLD, kiểm schema, codec, native TLS/auth và local DC.

### Câu 27 — Ephemeral journal

Journal chỉ lưu trong container và mất sau restart. Có thể bảo đảm một lần dispatch không?

**Đáp án:** Không. Cần durable journal/CAS, audit và read-only recovery.

### Câu 28 — Mất JMX trong lúc Leaving

Có thể suy decommission đã fail và gọi lại vì observer hết credentials?

**Đáp án:** Không. Mất observability là UNKNOWN; khôi phục JMX/trust rồi reconcile.

### Câu 29 — Unit tests

Unit test của `SafeReconciler` không dispatch đủ để chứng minh admin khác không can thiệp không?

**Đáp án:** Không. Nó kiểm code path nội bộ; cần RBAC/lock/audit cho các actors bên ngoài.

### Câu 30 — COMPLETE

Điều kiện đóng operation topology thành công là gì?

**Đáp án:** Exact target identity đúng expected after-state, replica/token/streaming và RF/CL an toàn, CQL/Java correctness và error/p99/resource budget đạt, observation window và audit evidence đầy đủ; thiếu hard gate → HOLD.

## 34. Checklist trước, trong, sau bootstrap/decommission

### 34.1. Chuẩn bị change

~~~text
[ ] Change ID, operation ID và approved manifest tồn tại.
[ ] Cluster ID, target host ID, DC/rack, node/PVC/instance identity cố định.
[ ] Cassandra release/operator/SOP tương thích được xác minh.
[ ] Loại action đúng: BOOTSTRAP, DECOMMISSION, REPLACE hay REMOVENODE.
[ ] Không có topology operation nào khác theo cluster/scope lock.
[ ] Durable journal/CAS và leader lease/fencing epoch được kiểm.
[ ] SDK/CI/operator retry policy trên topology dispatcher bị vô hiệu hóa.
[ ] Có approved operator, rollback/forward recovery plan rõ.
[ ] No unintended node DOWN, schema/topology metadata nhất quán.
[ ] RF/CL, rack/DC fault tolerance và app SLA đã xác nhận.
[ ] Disk/network/GC/CPU và compaction/repair/streaming headroom đủ.
[ ] Native CQL probes và baseline workload đang khỏe.
[ ] Tất cả evidence có UTC time/source/freshness.
~~~

### 34.2. Gate riêng cho bootstrap

~~~text
[ ] New node không có identity/token trùng existing member.
[ ] Volume/data dir identity đúng; không reuse PVC sai.
[ ] Seed/gossip/internode/client TLS/native config chuẩn.
[ ] DC/rack placement và data-center RF policy phù hợp.
[ ] Source peers có streaming capacity.
[ ] Controller persist intent trước khi provision/start.
[ ] Không tạo VM/pod/node lần thứ hai sau timeout.
[ ] Quan sát Joining/streaming từ nhiều sources.
[ ] Khi Normal, kiểm tokens, schema, CQL và Java peer discovery.
[ ] Không cleanup/repair tự động thiếu SOP.
[ ] Application errors/p99 và source/dest resources đạt.
~~~

### 34.3. Gate riêng cho decommission

~~~text
[ ] Exact target đang Up/Normal, chưa Leaving/absent.
[ ] Remaining nodes/DC/rack đủ RF/CL/fault tolerance.
[ ] Streaming recipients có disk/network/IO headroom.
[ ] Không xung đột repair/replacement/other topology actions.
[ ] Intent ghi durable; action chỉ dispatch một lần.
[ ] Timeout không làm command bị replay.
[ ] Theo dõi Leaving và streaming/metrics bằng read-only observer.
[ ] Target absent theo nhiều views, đúng expected host ID.
[ ] Token ownership, schema và remaining nodes đúng plan.
[ ] CQL CL của app và business data/read-back đạt.
[ ] Không tự restart/decommission node kế khi chưa hoàn tất.
~~~

### 34.4. Recovery khi mất phản hồi

~~~text
[ ] Journal/intent/epoch/revision đã đọc lại.
[ ] Không tồn tại hai active topology dispatchers.
[ ] Cluster/target identity khớp approved manifest.
[ ] Có fresh observations từ nhiều nodes/sources.
[ ] Nếu target Joining/Leaving, chỉ đọc/monitor.
[ ] Nếu target absent/new Normal, thực hiện postflight, không gọi lại.
[ ] Nếu không chứng minh được outcome, HUMAN_REVIEW/HOLD.
[ ] Không sửa system tables, xóa data dir hoặc removenode mù.
[ ] Human action/approval có audit, operation ID mới khi đổi scope.
[ ] Không đóng change bằng một CLI exit code.
~~~

### 34.5. Đóng change

~~~text
[ ] Expected after-topology verified, exact identities matching.
[ ] RF/CL và app read/write CQL queries đạt.
[ ] Schema/JDK/driver/native TLS/auth compatibility đạt.
[ ] Streaming/recovery state rõ, pending jobs có owner.
[ ] Worst-node disk/GC/CPU/network headroom trong policy.
[ ] CQL/app p95/p99, timeouts/errors/retries trong SLO.
[ ] Observation window đủ dài, metrics không stale.
[ ] Durable audit report, limitations và owner signoff đã lưu.
[ ] Controller không giữ stale lease/admin privileges.
[ ] Không chạy Content QA chuyên môn STEP 6 ở bước viết này.
~~~

## 35. Những anti-pattern cần chặn trong code review

| Anti-pattern | Rủi ro | Quy tắc thay thế |
|---|---|---|
| Retry topology command sau timeout | Side effect đã bắt đầu có thể bị lặp | Read-only reconcile |
| Tạo operation ID mới khi job restart | Mất dedupe | Reuse durable ID |
| Chỉ khóa pod, không khóa cluster | Hai controllers khác nhau cùng dispatch | Scope lock theo topology |
| Lease expiry = command cancelled | Sai về side effects ở Cassandra | Fencing + journal + reconcile |
| Dựa vào IP thay host ID | IP reuse tác động node khác | Immutable identity |
| Reimage + xóa system tables để bootstrap | Mất data/identity metadata | Release-specific replacement SOP |
| Bỏ qua expected node inventory | Missing node vẫn PASS | Compare host IDs/DC/rack |
| Node UN = operation complete | Stream/queries/resources còn có thể lỗi | Multi-layer postflight |
| CLI exit 0 = data safely moved | Không kiểm replica/CL | Expected after state + CQL |
| Poll every second forever | JMX/CPU/monitoring pressure | Bounded backoff/deadline |
| Auto-continue on UNKNOWN | Missing evidence bị giấu | Fail closed |
| Repair/cleanup như health check | Có side effects/I/O | Operation riêng |
| CQL probe ONE khi app QUORUM | Che lỗi replica | CL theo workload |
| Một probe key đại diện ring | Không phủ tất cả replica sets | Topology coverage |
| Scale StatefulSet như decommission | Pod lifecycle khác ring lifecycle | Operator/SOP |
| Chạy add/remove song song | Token/data movement conflict | Serialize steps |
| Tắt TLS để check nhanh | Mất security | Approved SSL/auth config |
| Grant superuser cho controller probe | Blast radius lớn | Least privilege |
| Giảm RF khi cluster đã degraded | Thay correctness/fault tolerance | Plan capacity/replication riêng |
| Kết luận stall từ một sample | False alarm | Time-series + metrics |
| Không xét node source disk khi bootstrap | Streaming làm peers quá tải | Capacity cả hai phía |
| Restart node kế khi node trước chưa ổn | Mất quorum và headroom | Per-node health gate |
| Lưu journal trong pod ephemeral | Mất dispatch history | Durable CAS store |
| Có lock nhưng admin ngoài vẫn chạy lệnh | Controller không còn exclusive | RBAC + audit + change freeze |
| Log password/volume secrets | Rò dữ liệu | Redaction và ACL |

## 36. Tổng kết

Điều phối **bootstrap/decommission mà không lặp thao tác nguy hiểm** đòi hỏi tư duy như một hệ thống giao dịch phân tán có **side effects không có idempotency key toàn cục**, không phải một vòng script retry.

1. **Định danh exact target** bằng cluster ID, host ID, DC/rack, instance/PVC và approved manifest. Không chỉ dựa IP/pod name.
2. **Phân biệt bootstrap, decommission, replace, removenode và restart**; mỗi loại có preconditions và SOP khác nhau.
3. **Ghi durable command intent trước side effect**, dùng operation ID ổn định và CAS/revision ở journal.
4. **Chỉ một dispatcher được quyền thay ring tại một thời điểm** theo scope; lease/epoch hữu ích nhưng không tự dừng lệnh Cassandra đã chạy.
5. **Không retry lệnh topology sau timeout/crash**. Retry có giới hạn chỉ dành cho observation; outcome không rõ → HOLD/HUMAN_REVIEW.
6. **State machine có phase-aware postconditions**: bootstrap Joining/Normal và transfer; decommission Leaving/absent và transfer.
7. **Preflight kiểm RF/CL, replica/fault-domain, storage/streaming/network headroom** trước khi cho node vào hoặc ra.
8. **Postflight so expected inventory/host IDs, token ownership, CQL correctness, latency/resources**, không chỉ `UN`/CLI exit code.
9. **Cross-DC và Java Driver là gate riêng**; read/write probe có CL đúng workload và phạm vi rõ.
10. **Không tự gọi repair/cleanup/removenode để “chữa” operation chưa hoàn tất**; đây là thao tác riêng có rủi ro.
11. **Audit và observability phải đủ mới/đúng nguồn** để operator tiếp quản không đoán.
12. **Duy trì fail-closed policy**: thiếu bằng chứng hoặc lệch identity được xử lý như lý do dừng, không phải điều kiện cho phép retry.

Câu hỏi cuối cùng trước mỗi bước không phải **“Lệnh trước đã trả success chưa?”**, mà là **“Side effect có thể đã được thực hiện chưa, đúng node và đúng cluster chưa, Cassandra đang ở phase nào, RF/CL và dữ liệu có an toàn không, và có đủ bằng chứng để tiến lên mà không phát lệnh thay ring lần thứ hai không?”**.

Nếu chưa trả lời được bằng bằng chứng hiện thời, **dừng dispatch, tiếp tục quan sát và chuyển cho operator theo SOP** là lựa chọn an toàn.


