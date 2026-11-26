# Khả năng phục hồi sau failover và giới hạn của yêu cầu độ bền trong Couchbase

> **Chương:** Độ bền ghi  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; phối hợp bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để bảo đảm hiệu năng, nhất quán và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả **failover** từ góc nhìn active vBucket, replica, Data node và routing của Couchbase Java SDK.
2. Phân biệt **hard failover**, **graceful failover**, **automatic failover**, **recovery** và **rebalance**.
3. Giải thích vì sao mutation đã được xác nhận ở `MAJORITY` hoặc persistence level có cơ sở sống sót sau **một số sự cố**, nhưng không có bảo đảm tuyệt đối trong mọi chuỗi lỗi.
4. Phân biệt SyncWrite đang **prepare/pending**, mutation đã **commit**, response đã tới client và trạng thái được promote/rollback khi active owner đổi.
5. Tính majority với bucket 0/1/2 replica; biết rằng Sync Writes trên bucket 3 replicas **không được hỗ trợ** theo tài liệu Couchbase Server hiện hành.
6. Phân tích rủi ro mất mutation mới commit khi **nhiều Data nodes cùng giữ majority bị failover** trước khi bản thứ ba bắt kịp.
7. Hiểu `maxCount`, `failoverPreserveDurabilityMajority` và `durabilityImpossibleFallback` trong các triển khai có hỗ trợ.
8. Thiết kế retry/idempotency, xử lý ambiguous outcome, CAS và business reconciliation cho Spring Data Couchbase.
9. Chọn metrics, failure tests và runbook recovery theo RPO, RTO, SLO rõ ràng.
10. Phân biệt HA/durability trong cluster với backup/restore và DR sau mất site/region.

## 2. Tình huống: API đã báo thành công, active node bất ngờ lỗi

Một hệ thống Spring Boot nhận đơn hàng tại:

~~~text
Bucket: commerce
Scope: sales
Collection: orders
Key: tenant::42::checkout::checkout-abc
~~~

~~~json
{
  "docType": "ORDER",
  "tenantId": "42",
  "checkoutId": "checkout-abc",
  "status": "CONFIRMED",
  "total": 1490000,
  "schemaVersion": 1
}
~~~

Ứng dụng gọi:

~~~java
orders.insert(
    "tenant::42::checkout::checkout-abc",
    orderBody,
    insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

SDK nhận success. Vài giây sau, Data node đang giữ **active vBucket** của document bị lỗi. Ta cần biết:

- Mutation đã được xác nhận trên **những bản dữ liệu nào**?
- Node nào chứa replica hợp lệ để promote thành active?
- Có ai tiếp tục failover những node khác đang giữ mutation mới?
- Có đủ majority cho **những mutation tiếp theo** không?
- Các mutation in-flight có kết quả xác định hay ambiguous?
- Sau failover, cluster đã được rebalance và khôi phục số replica mong muốn chưa?
- Nếu mất toàn cluster, backup/DR đáp ứng RPO/RTO như thế nào?

Đó là phạm vi bài học: **bảo vệ mutation đã xác nhận trong một failure scenario xác định**, không hứa “không bao giờ mất dữ liệu”.

## 3. Vị trí thực của dữ liệu: active và replica vBucket

Couchbase phân phối document ID vào **vBucket**. Mỗi vBucket có một bản **active** và có thể có nhiều **replica** trên các Data node khác nhau.

~~~mermaid
flowchart LR
    App["Spring Data / Java SDK"]
    Router["SDK vBucket routing map"]
    A["Node A<br/>Active V42"]
    B["Node B<br/>Replica V42"]
    C["Node C<br/>Replica V42"]
    App --> Router
    Router -->|"Ghi KV theo ID"| A
    A -->|"Replication"| B
    A -->|"Replication"| C
~~~

Các vBucket khác có thể đặt active ở B hoặc C. Vì thế:

- Couchbase không có một master node duy nhất cho toàn cluster.
- Data Service xử lý KV; Query/Index nodes **không** tính vào majority Data replicas.
- Cấu hình nhiều Data nodes không có nghĩa mỗi document được sao chép lên toàn bộ.
- Một replica bị missing/lagging hoặc node chưa rebalance làm actual placement khác cấu hình.
- SDK cập nhật cluster map sau failover để định tuyến sang active owner mới.

### 3.1. Replica count và actual placement

Một bucket đặt `replicaNumber=2` mong muốn một active và hai replicas cho mỗi vBucket. Nếu thiếu Data nodes, replica chưa được đặt hoặc cluster đang rebalance, số bản thực tế có thể không như mong muốn.

Không suy từ dòng “Replicas: 2” trong UI rằng một mutation hiện có ba copies. Cần kiểm tra **vBucket distribution, replica health và server groups**.

### 3.2. Failure domains

Ba Data nodes cùng nằm trong một rack/nguồn điện không bảo vệ tốt trước mất rack. Các bản cần được bố trí theo failure domains độc lập ở mức topology cho phép. **Server Groups** hỗ trợ nhận biết nhóm đặt node, nhưng không thay thế DR site hoặc backup.

## 4. Failover, recovery và rebalance khác nhau thế nào?

| Khái niệm | Mục đích | Điều cần chú ý |
|---|---|---|
| **Node restart** | Node tạm dừng/khởi động lại | Mất kết nối, ảnh hưởng replica, có thể giữ disk |
| **Hard failover** | Loại node lỗi khỏi membership đang phục vụ | Promote replica, pending mutations, khả năng thiếu redundancy |
| **Graceful failover** | Chuyển vai trò/dữ liệu có kiểm soát khi node còn phục vụ | Có thể ít gián đoạn hơn, vẫn cần theo dõi các mutation đang chạy |
| **Automatic failover** | Cluster tự quyết định failover theo policy | Thời gian phát hiện lỗi, `maxCount`, bảo vệ majority |
| **Recovery** | Đưa node đã failover trở lại theo cách server hỗ trợ | Dữ liệu cũ trên node không tự trở thành nguồn có thẩm quyền |
| **Rebalance** | Phân phối lại active/replica vBuckets | Data movement, change of owner, I/O và network load |
| **Backup/restore** | Khôi phục dữ liệu từ restore point độc lập | RPO/RTO khác với intra-cluster failover |

### 4.1. Hard failover không phải backup

Hard failover giúp cluster dùng replica để tiếp tục phục vụ khi node không hoạt động; nó không cung cấp bản lịch sử trước xóa nhầm hoặc mất toàn site.

### 4.2. Graceful failover không miễn rủi ro network

Graceful failover chuyển giao có kiểm soát khi node còn đủ điều kiện tham gia. Dù vậy, request in-flight có thể chịu routing changes, timeout, hoặc response loss. Không loại bỏ idempotency chỉ vì bảo trì có kế hoạch.

### 4.3. Failover xong chưa phải khôi phục đầy đủ

Sau khi replica được promote thành active, cluster có thể phục vụ trở lại nhưng **đang thiếu một bản replica dự phòng**. Cần recovery/bổ sung node và rebalance để quay về độ chịu lỗi mục tiêu.

## 5. Sync Writes: prepare, commit, response và failure window

Một mutation sử dụng synchronous durability có thể đi qua các mốc logic:

~~~mermaid
sequenceDiagram
    participant Client as Java SDK
    participant A as Active V42
    participant B as Replica V42
    Client->>A: INSERT + DurabilityLevel.MAJORITY
    A->>A: Pending/prepare
    A->>B: Replicate prepare / tiến độ
    B-->>A: Xác nhận
    Note over A,B: Đạt điều kiện durability
    A->>A: Commit
    A-->>Client: MutationResult success
~~~

Sơ đồ chỉ mô tả **quan hệ điều kiện**, không phải thứ tự packet bất biến trong mọi version. Replication, persistence và các bước commit/cleanup có thể diễn ra đồng thời.

### 5.1. Prepare/pending chưa phải ghi đã commit

Khi SyncWrite còn pending, một người đọc có thể thấy **giá trị cũ đã commit**; mutation khác cùng key có thể gặp `SYNC_WRITE_IN_PROGRESS`. Failover hoặc timeout có thể dẫn đến commit/abort/recovery theo protocol.

Không nên trả “đã tạo đơn” dựa trên việc nhận thông tin request đã được active tiếp nhận mà chưa có success theo mức yêu cầu.

### 5.2. Commit và client response là hai mốc khác nhau

Server có thể commit, nhưng response mất do failover/network. SDK báo ambiguous, dù document đã tồn tại.

Ngược lại, khi SDK nhận success với level hiệu lực và không có chính sách làm yếu mức bảo đảm, application có cơ sở theo **contract của durability level**; không suy ra an toàn trước mọi sự cố tương lai.

### 5.3. Sáu vị trí có thể gặp failover

~~~text
A. Client chưa gửi mutation.
B. Request đã tới active nhưng chưa prepare.
C. SyncWrite pending, đang đợi replica/disk.
D. Mutation đủ điều kiện và đã commit.
E. Response đã phát, client chưa nhận.
F. Client nhận success, HTTP đã trả.
~~~

Ở C, có thể abort hoặc outcome bất định. Ở D/E, response loss có thể khiến client không biết server đã commit. Ở F, vẫn cần phân tích **những copies giữ mutation** và các node failover tiếp theo.

## 6. Majority với 0/1/2 replicas, giới hạn với 3

Theo tài liệu Couchbase Server hiện hành, **Sync Writes hỗ trợ bucket cấu hình tối đa hai replica**. Một bucket có thể hỗ trợ ba replicas trong replication thông thường nhưng không được suy ra Sync Writes cũng áp dụng.

| Replica cấu hình | Copies dự kiến | Majority cần | Giới hạn |
|---|---:|---:|---|
| **0** | 1 active | **1** | Không có replica cho failover nếu mất node duy nhất |
| **1** | 1 active + 1 replica | **2** | Majority cần đủ hai bản trong điều kiện bình thường |
| **2** | 1 active + 2 replicas | **2** | Hai bản đủ majority; bản thứ ba có thể chưa bắt kịp |
| **3** | 1 active + 3 replicas | Không áp dụng | **Sync Writes không hỗ trợ** theo docs Server hiện hành |

### 6.1. Majority 1/1 không bảo vệ mất Data node

Với `replicaNumber=0`, `MAJORITY` có thể đạt majority 1/1. Nhưng node duy nhất mất hoàn toàn thì không có bản sao để promote. Không dùng kết quả này để cam kết sống sót sau một node failure.

### 6.2. Một replica: majority 2/2

~~~text
A active + B replica
Cần 2/2.

A/B khỏe: có thể hoàn tất.
B offline: A còn nhưng thiếu quorum.
A lỗi: cần phục vụ từ replica phù hợp sau failover.
~~~

Một số KV read hoặc ghi không đòi sync durability có thể còn hoạt động, trong khi một mutation `MAJORITY` không thể hoàn tất đúng contract.

### 6.3. Hai replicas: majority 2/3

~~~text
A active, B và C replicas.
Cần 2/3.

Mutation M ở A+B: đạt majority dù C còn trễ.
Mutation M ở A+C: đạt majority dù B còn trễ.
Chỉ A có M: chưa đủ majority.
~~~

Thêm replica có thể cải thiện khả năng đạt quorum khi một bản không khả dụng; không có nghĩa chịu được **bất kỳ hai** node failures.

## 7. Sau một active failover: điều gì có thể được bảo vệ?

Giả sử mutation M đã commit với `MAJORITY`:

~~~text
V42:
  A (active): có M
  B (replica): có M
  C (replica): chưa nhận M

SDK đã báo success.
~~~

Nếu **chỉ A** lỗi, bản B còn mutation có cơ sở để phục vụ dữ liệu sau failover khi cluster recovery protocol, promotion và membership cho phép.

~~~mermaid
flowchart LR
    A["A active<br/>có M"]
    B["B replica<br/>có M"]
    C["C replica<br/>chưa có M"]
    Loss["A lỗi"]
    New["Active mới theo recovery protocol"]
    A --> Loss --> New
    B -->|"Bản đã nhận M"| New
    C -.->|"Cần catch-up nếu trễ"| New
~~~

**Không tự lập trình chọn replica mới nhất**; server quyết định owner/trạng thái sau failover theo metadata và giao thức hỗ trợ.

### 7.1. Availability có thể gián đoạn dù dữ liệu còn

SDK có thể mất thời gian cập nhật cluster map, tìm active mới và retry phù hợp. Một HTTP 503/timeout ngay trong lúc failover **không chứng minh** mutation đã được ack trước đó biến mất.

### 7.2. Sau promotion cần khôi phục redundancy

Nếu B trở thành active, số replica dự phòng có thể giảm. Những writes tiếp theo cần được đánh giá theo actual topology và minimum durability; phục vụ được một request đọc không có nghĩa cluster đã trở lại mức HA như T0.

## 8. Giới hạn quan trọng: mất những node chứa toàn bộ majority

Giả sử bucket có hai replicas:

~~~text
A active: có mutation M
B replica: có mutation M
C replica: chưa nhận M

Client đã được báo MAJORITY success nhờ A+B.
~~~

Nếu **cả A và B** bị failover trước khi C nhận mutation, C có thể không có M. Trong trường hợp chỉ C còn phục vụ, mutation đã được báo success trước đó **có thể bị mất**.

Đây là giới hạn then chốt:

- `MAJORITY` yêu cầu **2/3**, không yêu cầu **3/3**.
- `PERSIST_TO_MAJORITY` yêu cầu persist trên majority, **không bắt bản thứ ba đã persist**.
- “Có hai replica” không nghĩa “chịu mất bất kỳ hai Data nodes”.
- Failover nhiều lần có thể khác hẳn một lần failover đơn.
- Một số cấu hình auto-failover được thiết kế nhằm tránh loại bỏ quá nhiều bản giữ durable writes.

### 8.1. Tại sao retry không hồi sinh được dữ liệu đã mất?

Nếu các copies có M đều bị loại hoặc mất vĩnh viễn, client không thể chỉ retry và phục hồi **đầy đủ lịch sử, CAS, business side effects**. Cần chính sách bảo vệ majority, backup/DR, audit log và business reconciliation.

### 8.2. RPO phải được viết bằng failure scenario

“RPO=0 với một Data node loss” khác “RPO=0 khi mất hai Data nodes hoặc toàn AZ”. Độ an toàn cần gắn với **kiểu lỗi và thứ tự lỗi**, không chỉ số copies dự kiến.

## 9. Bốn DurabilityLevel hỗ trợ recovery khác nhau như thế nào?

| Mức | Điều kiện trước success | Điểm cần cân nhắc sau failover |
|---|---|---|
| **`NONE`** | Không yêu cầu synchronous durability bổ sung, trừ bucket minimum | Ghi có thể được ack trước replica/persistence; dễ có cửa sổ rủi ro hơn |
| **`MAJORITY`** | Majority xác nhận mutation | Có thêm copy khi một bản lỗi, nhưng không bắt buộc persistence hoặc full replica catch-up |
| **`MAJORITY_AND_PERSIST_TO_ACTIVE`** | Majority + persistence ở active | Active có bản persisted nhưng có thể mất hẳn node/disk đó; replicas không bắt buộc persist |
| **`PERSIST_TO_MAJORITY`** | Persistence trên majority | Giảm một số rủi ro khi node/process/disk lỗi, vẫn không bảo vệ mọi lỗi nhiều node/site |

### 9.1. Process restart khác disk loss

Nếu node restart nhưng storage còn, bản persisted có thể được khôi phục theo engine semantics. Nếu disk/máy mất vĩnh viễn, dữ liệu persisted chỉ trên thiết bị đã mất không giúp phục vụ ngay; phải có replica còn lại hoặc restore.

### 9.2. Persistence không phải backup

Một lệnh xóa nhầm `remove` hợp lệ với mức durability cao có thể làm chính việc xóa được replicate/persist mạnh hơn. Backup/versioned restore hoặc audit là câu trả lời cho mất dữ liệu do logic, không phải tăng durability.

### 9.3. Capella và self-managed đều cần kiểm chứng

Dịch vụ managed có thể tự quản lý nhiều phần failover và recovery, nhưng application vẫn phải hiểu mức ghi thực sự, replica topology/tier và RPO. Không suy rằng đổi sang Capella tự biến mọi mutation thành mức bền cao nhất.

## 10. Auto-failover: đánh đổi khôi phục sớm với bảo vệ majority

Trong edition/version hỗ trợ, Couchbase có các tùy chọn:

- `maxCount`: giới hạn những lần/node auto-failover liên tiếp theo policy.
- `failoverPreserveDurabilityMajority`: nhằm tránh tự động failover Data node khi việc đó có thể loại bỏ một majority giữ mutation durable mới.

### 10.1. Ví dụ nguy cơ failover liên tiếp

A+B vừa xác nhận M; C chưa có M. Nếu A lỗi, cluster đã suy giảm. Nếu tự failover B ngay khi C chưa theo kịp, có thể loại toàn bộ copies chứa M.

### 10.2. Bảo vệ majority có thể làm giảm availability ngắn hạn

Policy giữ lại node để tránh mất dữ liệu có thể ngăn một số failover hoặc buộc admin can thiệp. Đây là đánh đổi:

| Cách ưu tiên | Lợi ích | Chi phí |
|---|---|---|
| Failover nhanh, tích cực | Có thể giảm thời gian ngừng phục vụ | Có thể loại bỏ nhiều copies mang mutation mới |
| Giới hạn auto-failover | Giữ nhiều copies hơn trong sự cố nối tiếp | Cần can thiệp thủ công sớm hơn |
| Preserve durability majority | Ưu tiên không làm mất các durable writes đã xác nhận | Có thể trì hoãn khả năng phục vụ/failover |
| Manual failover không kiểm tra quorum | Có thể tác động nhanh | Nguy cơ chọn sai node và tăng thiệt hại |

Không đoán giá trị mặc định hoặc ý nghĩa trên mọi edition; phải đối chiếu đúng deployment và tài liệu Server/Capella.

### 10.3. Runbook thao tác thủ công

Trước khi loại Data node thứ hai trong cluster đã suy giảm, DBA/SRE cần biết active/replica placement, node nào có dữ liệu mới nhất, policy preserve-majority, failure logs và RPO nghiệp vụ. Developer không tự yêu cầu hard failover production chỉ để “thử xem”.

## 11. Hard failover và graceful failover không cùng tiền đề

**Hard failover:** thường xảy ra khi node không còn khả năng trao đổi dữ liệu. Những mutation chưa được replicate không thể được “gửi nốt” từ node đã chết.

**Graceful failover:** có thể chuyển giao vai trò theo cách được kiểm soát khi node vẫn hoạt động, phù hợp bảo trì có kế hoạch. Nhưng không miễn hoàn toàn routing changes, timeout và response loss.

Ở cả hai tình huống, ứng dụng phải sẵn sàng cho:

- SDK cluster map cập nhật.
- KV timeout hoặc request cancellation trong cửa sổ chuyển vai trò.
- Mutation đã commit nhưng client nhận ambiguous.
- CAS mismatch khi writer khác vừa cập nhật state.
- Rebalance tạo tải và gián đoạn ngắn.
- Business retry từ HTTP caller.

**Không mặc định graceful failover làm cho mọi pending write không thể ambiguous.**

## 12. Recovery và rebalance sau failover

~~~text
T0: Cluster A/B/C; bucket có 2 replicas.
T1: A lỗi; replica được promote.
T2: SDK nhận cluster map mới và phục vụ lại.
T3: Cluster có thể còn thiếu một Data copy.
T4: DBA/SRE recover hoặc thêm node.
T5: Rebalance tạo lại placement mong muốn.
T6: Xác minh active/replica vBuckets, disk/network và tests.
~~~

Điều đúng:

- **T2 không bằng T6**: traffic phục hồi không có nghĩa redundancy đầy đủ.
- Trong thời gian thiếu bản, durable write mới có thể lỗi vì quorum.
- Rebalance có thể làm routing thay đổi và tăng p95/p99; một số outcome có thể ambiguous.
- Khôi phục node không tự coi dữ liệu cũ trên đó là nguồn có thẩm quyền hơn active mới.
- Cần xem failure-domain placement sau rebalance, không chỉ node count.

### 12.1. Giới hạn tải N-1

Cluster được thiết kế chịu một Data node lỗi cần có CPU/RAM/disk/network headroom trên node còn lại. Nếu không, failover có thể thành công về chức năng nhưng latency/timeout tăng và các ghi quan trọng không đạt SLO.

### 12.2. Tạm giảm tải không đồng nghĩa giảm durability

Có thể hạn chế cache refresh, batch jobs hoặc concurrency khi cluster suy giảm, trong khi giữ nguyên level cho order/payment. Thay level là thay đổi rủi ro dữ liệu, phải được review.

## 13. Durability-impossible fallback và mất hợp đồng majority

Một số phiên bản/triển khai Couchbase có bucket option `durabilityImpossibleFallback` (ví dụ chế độ `fallbackToActiveAck`) để cho phép một số writes được xác nhận dựa trên active ack khi majority không khả dụng.

Điều này **có thể tăng write availability nhưng làm yếu bảo đảm dữ liệu**:

- Client có thể nhận success khi chưa đạt majority đã mong muốn.
- Recovery sau mất active có thể không còn đủ copies giữ mutation đó.
- Bật fallback không chữa mọi sự cố; nếu active owner cũng không phục vụ, nó không sinh node mới.
- Transaction dựa trên durable writes cũng cần được xem xét về bảo đảm trong chế độ fallback.

### 13.1. Fallback không phải retry policy

| Biện pháp | Tác động | Điểm giới hạn |
|---|---|---|
| Khôi phục replica/rebalance | Xây lại điều kiện quorum | Cần thời gian và capacity |
| Thêm Data nodes/placement | Tăng độ chịu lỗi theo topology | Không thay backup |
| Hạ level client | Giảm điều kiện xác nhận | Thay đổi RPO |
| Bật bucket fallback | Có thể ack trong tình trạng thiếu quorum | Không được khẳng định đã đạt majority |
| Tăng timeout | Cho phép chờ lâu hơn | Không tự sửa thiếu replica |
| Queue bền độc lập | Chuyển hợp đồng thành “đã tiếp nhận lệnh” | Cần một workflow mới và idempotency |

Nếu buộc dùng fallback, phải có owner RPO, approval, audit, giới hạn thời gian, metrics, kế hoạch tắt và reconciliation. Không bật như biện pháp mặc định để “cho API hết timeout”.

## 14. Các câu hỏi khác nhau: durability, failover, DR và business outcome

| Câu hỏi | Cơ chế chính | Phạm vi |
|---|---|---|
| Mutation được ack khi đạt level nào? | `DurabilityLevel` / minimum bucket | Trước response success |
| Sau active failure, còn copy chứa mutation không? | Replica state, promotion, failover policy | Trong cluster |
| Sau lỗi nhiều node/site, phục hồi từ đâu? | Backup/restore, DR/XDCR khi hỗ trợ | Ngoài một cluster hoặc ngoài failure domain |
| Response mất, business biết outcome không? | Stable ID, idempotency, reconciliation | Xuyên client, server và hệ thống ngoài |
| Query SQL++ có thấy state mới không? | DCP/GSI và scan consistency | Query/Index Service |
| Writer khác có ghi đè state sai không? | CAS, transaction, business rule | Tầng logic nghiệp vụ |

Một mutation đã `PERSIST_TO_MAJORITY` không tự tạo DR site; `REQUEST_PLUS` không biến mutation trước thành bền hơn; CAS không thay replication.

## 15. Persistence levels và giới hạn khi nguồn dữ liệu hỏng

### 15.1. `MAJORITY_AND_PERSIST_TO_ACTIVE`

Có majority acknowledgement cộng active persistence. Nếu active bị mất **cả disk**, persistence của active không còn sẵn ở node đó, dù có thể còn replica đã nhận mutation. Không mặc định các replica đã persist theo level này.

### 15.2. `PERSIST_TO_MAJORITY`

Yêu cầu persist trên majority; giúp mạnh hơn trước một số tình huống mất bộ nhớ/process. Nhưng bản thứ ba không bắt buộc persist, nên việc mất nhiều copies giữ mutation vẫn có thể vượt phạm vi bảo vệ.

### 15.3. Xóa nhầm hoặc corruption nghiệp vụ

Một mutation xóa/sửa sai có thể được replicate/persist thành công; durability không có chức năng “undo”. Backup/retention, business audit, restore point và quy trình kiểm soát thao tác mới là các lớp cần thiết.

### 15.4. RPO phải gắn kịch bản

Không đặt “RPO=0 cho mọi sự cố” chỉ từ level. Cần phân loại mất một node, hai copies giữ majority, mất một rack/zone, mất site, xóa nhầm và restore từ bản sao khác.

## 16. Timeout ambiguous khi active failover giữa chừng

~~~mermaid
sequenceDiagram
    participant API as Order service
    participant SDK as Couchbase Java SDK
    participant A as Active V42
    participant B as Replica V42
    API->>SDK: INSERT orderId + MAJORITY
    SDK->>A: KV mutation
    A->>B: Replicate / xác nhận
    B-->>A: Đủ điều kiện
    Note over A,B: Có thể đã commit
    A--xSDK: Response mất khi A lỗi
    SDK-->>API: Timeout / ambiguous outcome
~~~

**Timeout không đồng nghĩa chưa ghi**. SDK có thể không chắc server đã commit hay chưa nếu request được dispatch trước khi mất response.

| Kết quả | Có thể kết luận | Ứng xử |
|---|---|---|
| `MutationResult` success | Operation hoàn tất theo effective durability contract | Tiếp tục workflow |
| `AmbiguousTimeoutException` | Chưa biết side effect đã xảy ra không | Reconciliation theo ID |
| `DurabilityAmbiguousException` | Không chắc SyncWrite outcome | Không tự khẳng định rollback |
| `UnambiguousTimeoutException` | SDK có cơ sở xác định request này chưa gây side effect | Retry có budget và kiểm tra business |
| `DurabilityImpossibleException` | Level không thể đạt hiện tại | Kiểm tra bucket/replicas, không hạ level tự động |
| `DocumentExistsException` | Insert gặp ID đã tồn tại | So fingerprint của business request |
| `CasMismatchException` | Phiên bản đã đổi | Đọc lại và tính business transition |
| SQL++ thiếu row | Có thể GSI chưa theo kịp | KV read/query consistency, không coi là mất dữ liệu |

SDK exceptions có thể được Spring Data dịch sang dạng khác; phải kiểm tra **cause chain và version** trong integration test.

### 16.1. Retry sai tạo duplicate

~~~text
Sai:
  Lần 1 insert order::random-A -> ambiguous
  Lần 2 insert order::random-B -> success
  Có thể tạo hai đơn cho một checkout.

Đúng:
  Document ID = tenant::42::checkout::checkout-abc
  Retry giữ nguyên ID và request fingerprint.
  Nếu duplicate, đọc/so khớp nghiệp vụ.
~~~

### 16.2. Một lần not-found không kết thúc đối soát

Khi SyncWrite vẫn pending hoặc cluster đang failover, một lần KV `get(id)` không thấy document không đủ kết luận mutation cũ sẽ không commit sau đó. Đặt deadline cho reconciliation, dùng ID cố định và không phát side effect mới từ sự thiếu chắc chắn.

## 17. Java SDK: yêu cầu độ bền rõ ràng trước khi kiểm thử failover

Couchbase Java SDK 3.x cho phép đặt level và timeout theo mutation. Giả định đối tượng `orders` đã trỏ tới collection `commerce.sales.orders`.

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

import java.time.Duration;
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.MutationResult;

String orderId = "tenant::42::checkout::checkout-abc";

JsonObject orderBody = JsonObject.create()
        .put("docType", "ORDER")
        .put("tenantId", "42")
        .put("checkoutId", "checkout-abc")
        .put("status", "CONFIRMED")
        .put("total", 1490000);

MutationResult result = orders.insert(
        orderId,
        orderBody,
        insertOptions()
                .durability(DurabilityLevel.MAJORITY)
                .timeout(Duration.ofSeconds(8))
);
~~~

Mục tiêu của ví dụ:

- `insert` là operation **create-only**, giúp phát hiện document ID trùng.
- `MAJORITY` yêu cầu SyncWrite đạt majority; **không xác nhận cả ba replicas** trong bucket 2 replicas.
- `timeout(8s)` là deadline SDK per-operation được chọn minh họa, **không phải lời hứa server xong trong tám giây**.
- Khi failover trùng lúc request chạy, outcome có thể không xác định.
- `orderId` ổn định để retry không tạo ID mới.

### 17.1. Nếu muốn persistence trên majority

~~~java
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

orders.upsert(
        "checkpoint::settlement::2026-11-25",
        JsonObject.create().put("status", "DONE"),
        upsertOptions().durability(DurabilityLevel.PERSIST_TO_MAJORITY)
);
~~~

Code yêu cầu storage engine/bucket type, replica count, node availability và server version phù hợp. `upsert` có thể thay document đã có; dùng nó cho checkpoint nếu business logic cho phép, không dùng cho order create-once mà không kiểm soát.

### 17.2. `MAJORITY_AND_PERSIST_TO_ACTIVE` và CAS

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

var previous = orders.get(orderId);
var previousBody = previous.contentAsObject();

if (!"CONFIRMED".equals(previousBody.getString("status"))) {
    throw new IllegalStateException("Không thể chuyển trạng thái");
}

var updated = previousBody.put("status", "FULFILLED");

var saved = orders.replace(
        orderId,
        updated,
        replaceOptions()
                .cas(previous.cas())
                .durability(DurabilityLevel.MAJORITY_AND_PERSIST_TO_ACTIVE)
);
~~~

- CAS phát hiện document đã bị writer khác thay đổi kể từ lần đọc.
- Durability xác nhận replication/persistence theo level.
- Business rule quy định có được chuyển `CONFIRMED → FULFILLED` hay không.
- Sau failover, CAS và trạng thái có thể thay đổi; cần đọc lại khi có conflict, không bỏ CAS rồi ép `upsert`.

### 17.3. SDK tự xử lý routing, không tự xử lý mọi nghiệp vụ

SDK có thể cập nhật cluster map và retry những request phù hợp khi owner thay đổi. Nó không biết “hai lần checkout có phải cùng một nghiệp vụ không” hoặc “payment gateway đã charge chưa”.

**SDK retry/reconnect ≠ business exactly-once.**

## 18. Spring Data Couchbase: entity mapping với durability và CAS

Với phiên bản Spring Data Couchbase hỗ trợ, đặt mức default trên entity:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document(durabilityLevel = DurabilityLevel.MAJORITY)
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String docType;
    private String tenantId;
    private String checkoutId;
    private String status;
    private Long total;
    private String requestFingerprint;

    // Constructors/getters/setters được lược bỏ.
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

~~~java
OrderDocument saved = orderRepository.save(order);
~~~

Khi mutation đi qua mapping Spring Data, `@Document(durabilityLevel = MAJORITY)` là **mức mặc định** theo API được hỗ trợ.

Tuy nhiên:

- Không tạo replica, không tăng Data node, không thay bucket minimum.
- Không bảo đảm mọi mutation bên ngoài repository cũng dùng `MAJORITY`.
- `@Version` là CAS/optimistic locking, không phải durability.
- Một `save` exception sau failover có thể cần phân loại outcome; không suy “không có entity trả về = chắc chắn chưa ghi”.
- Tên SDK exception có thể bị Spring Data dịch/bọc; kiểm tra version và `cause`.

### 18.1. Repository không cho thấy level tại lời gọi

~~~java
OrderDocument result = orderRepository.save(order);
~~~

Đoạn này không có parameter level. Nếu mục tiêu là review từng write quan trọng, dùng **template override** hoặc adapter SDK rõ ràng, kết hợp kiểm tra bucket minimum.

### 18.2. Tạo đơn nên có semantics create-only

Nếu idempotency key bắt buộc không được tạo đơn thứ hai, `save`/upsert có thể chưa phải lựa chọn rõ nhất. Cân nhắc fluent `insertById` hoặc SDK `insert`, rồi xử lý duplicate theo fingerprint.

## 19. CouchbaseTemplate: override mức cho một mutation quan trọng

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public final class CriticalOrderWriter {

    private final CouchbaseTemplate template;

    public CriticalOrderWriter(CouchbaseTemplate template) {
        this.template = template;
    }

    public OrderDocument insertCritical(OrderDocument order) {
        return template
                .insertById(OrderDocument.class)
                .withDurability(DurabilityLevel.PERSIST_TO_MAJORITY)
                .one(order);
    }
}
~~~

Trong những Spring Data versions hỗ trợ fluent template, `withDurability` chọn mức **per-operation** thay vì default từ entity metadata. Bucket minimum vẫn có thể ràng buộc level hiệu lực.

**Lưu ý:** `insertById` phù hợp create-only; nhưng không tự xử lý ambiguous outcome hay quyết định duplicate có thuộc cùng checkout không. Bạn vẫn cần business idempotency.

### 19.1. Đường SDK trực tiếp không đọc annotation Spring

~~~java
// Dùng Collection của Couchbase Java SDK:
orders.insert(orderId, jsonBody);
~~~

Lời gọi này không đọc `@Document(durabilityLevel = ...)` của `OrderDocument`. Nó bị chi phối bởi SDK mutation options, default behavior và bucket minimum. Nếu ứng dụng trộn repository/template với SDK trực tiếp, phải kiểm thử **cả hai đường ghi**.

### 19.2. Đặt level mạnh hơn có thể giảm write availability trong failover

Giả sử entity default `MAJORITY` còn một endpoint chọn `PERSIST_TO_MAJORITY`. Khi disk hoặc replica bị mất trong failover, endpoint mạnh hơn có thể chậm/lỗi nhiều hơn. Đó là đánh đổi thiết kế, không phải bug Java nếu server không thể đáp ứng contract.

## 20. Reactive: failover không khiến retry trở thành exactly-once

Couchbase Java SDK reactive trả `Mono`:

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

import com.couchbase.client.java.kv.MutationResult;
import reactor.core.publisher.Mono;

Mono<MutationResult> write = orders.reactive().insert(
        orderId,
        orderBody,
        insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Publisher chỉ chạy khi subscribe. Nếu dùng `retryWhen`, một subscription mới có thể gửi mutation lại, kể cả mutation trước đó đã commit nhưng response thất lạc.

### 20.1. Ví dụ phản ví dụ với ID ngẫu nhiên trong `Mono.defer`

~~~java
Mono<?> unsafe = Mono.defer(() ->
        orders.reactive().insert(
                java.util.UUID.randomUUID().toString(),
                orderBody,
                insertOptions().durability(DurabilityLevel.MAJORITY)
        )
).retryWhen(reactor.util.retry.Retry.max(3));
~~~

Nếu có retry/resubscribe, lambda trong `Mono.defer` có thể chạy lại và sinh **ID khác**. Một HTTP checkout có thể tạo nhiều order sau timeout.

### 20.2. ID ổn định và retry rất chọn lọc

~~~java
String stableId = "tenant::42::checkout::checkout-abc";

Mono<MutationResult> controlled = orders.reactive()
        .insert(
                stableId,
                orderBody,
                insertOptions().durability(DurabilityLevel.MAJORITY)
        )
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                    2, java.time.Duration.ofMillis(150)
                )
                .filter(error ->
                    error instanceof
                    com.couchbase.client.core.error.UnambiguousTimeoutException
                )
        );
~~~

Đây chỉ là **minh họa filter retry khi SDK đã xác định request này không tạo side effect**. Trong production cần deadline tổng, exception translation, monitoring và xử lý duplicate/ambiguous ở application layer.

**Không retry vô điều kiện một `AmbiguousTimeoutException` hoặc `DurabilityAmbiguousException` bằng cách tạo request/business ID mới.**

### 20.3. Cancellation ở WebFlux không rollback server

`Mono.timeout(...)` hoặc HTTP client rời kết nối có thể hủy subscription ở caller. Nó không bảo đảm Couchbase đã rollback mutation dispatch trước đó. Vì vậy phải có idempotency key xuyên cả WebFlux, service adapter và reconciliation.

## 21. Business idempotency sau failover: bảo vệ điều gì?

Giả sử client gửi `POST /checkout` với:

~~~text
Idempotency-Key: checkout-abc
tenantId: 42

Stable document ID:
tenant::42::checkout::checkout-abc
~~~

Bản ghi nên chứa dữ liệu đối chiếu tối thiểu:

~~~json
{
  "docType": "ORDER",
  "tenantId": "42",
  "checkoutId": "checkout-abc",
  "requestFingerprint": "sha256:...",
  "status": "CONFIRMED",
  "total": 1490000
}
~~~

Nếu lần đầu `insert` ambiguous, lần hai vẫn dùng **cùng ID**. Nếu nhận `DocumentExistsException`:

1. Đọc document theo ID bằng KV.
2. Xác minh tenant, checkout ID và request fingerprint.
3. Nếu khớp, có thể trả kết quả của command đã xử lý theo business rule.
4. Nếu khác fingerprint, trả conflict; không dùng một key để trộn hai commands khác nhau.
5. Nếu không đọc được trong lúc failover, giữ trạng thái **chưa xác minh**, không tự phát payment/side effect mới.

### 21.1. Fingerprint phải canonical

Hash raw JSON có thể khác vì thứ tự field, formatting hoặc dạng số dù ý nghĩa request giống nhau. Hãy canonicalize những trường nghiệp vụ hoặc lưu bộ field so sánh được quy định rõ. Không đưa password/payment token hay PII vào idempotency key/log.

### 21.2. Thời hạn giữ idempotency record

Nếu bản idempotency record hết TTL trước khi client có thể retry muộn, cùng command có thể tạo side effect mới. Chọn retention đủ dài theo SLA/replay window, không đơn giản set TTL 5 phút cho một nghiệp vụ có reconciliation sau nhiều giờ.

### 21.3. Cần phân biệt application retry và external retry

Gateway/mobile có thể gửi `POST` thêm lần nữa sau khi nhận 504; SDK nội bộ cũng có retry theo giao thức. Idempotency phải xuyên **cả hai vòng lặp**, không chỉ cố kiểm soát `RetryStrategy` của SDK.

## 22. Reconciliation workflow cho mutation outcome chưa rõ

Một luồng hợp lý:

~~~mermaid
flowchart TD
    A["Nhận request + idempotency key"]
    B["Tính document ID ổn định và fingerprint"]
    C["INSERT với durability đã chọn"]
    D{"Kết quả?"}
    S["Success rõ ràng"]
    E["Duplicate -> KV get + fingerprint"]
    U["Ambiguous -> KV verify / reconciliation"]
    F["Durability impossible -> báo lỗi hạ tầng"]
    Q{"Có trạng thái business khớp?"}
    Y["Trả kết quả đã có"]
    N["Chưa xác minh -> giữ command để đối soát"]
    X["Fingerprint khác -> conflict"]
    A --> B --> C --> D
    D -->|"Success"| S
    D -->|"Duplicate"| E
    D -->|"Ambiguous"| U
    D -->|"Không đạt level"| F
    E --> Q
    U --> Q
    Q -->|"Có"| Y
    Q -->|"Khác"| X
    Q -->|"Không rõ"| N
~~~

**KV readback không phải một thuật toán chứng minh mọi thứ**. Nếu server vẫn đang có SyncWrite pending hoặc cluster chưa ổn định, một lần `get(id)` không thấy không đủ khẳng định mutation ban đầu sẽ không bao giờ commit.

Reconciliation có thể cần:

- Request ID, stable document ID và fingerprint.
- Trạng thái business command, lần thử và thời gian cuối.
- Thông tin mutation exception/SDK error context.
- Gateway transaction reference hoặc source-of-truth bên ngoài.
- Backoff, tổng deadline, ownership, alert và quy trình đóng case.
- Nơi lưu command **đáng tin cậy** nếu muốn tiếp tục xử lý sau process crash.

### 22.1. Đừng trả `202 Accepted` khi không có nơi giữ command

Nếu Couchbase không thể xác nhận ghi và ứng dụng không có inbox/queue bền độc lập, `202 Accepted` mang nghĩa “đã tiếp nhận để xử lý sau” có thể sai. Hãy trả contract “kết quả chưa xác minh, dùng lại cùng idempotency key” hoặc lỗi phù hợp, không giả vờ đã lưu.

### 22.2. Không charge lại gateway chỉ vì Couchbase timeout

Payment gateway không thuộc một KV mutation Couchbase. Dùng idempotency của gateway và đối soát provider receipt/transaction ID. Durability mạnh không bảo đảm external side effect đúng một lần.

## 23. CAS sau failover: đừng dùng metadata cũ để ép ghi

CAS giúp phát hiện optimistic concurrency. Ví dụ:

~~~text
T0: order.status = CONFIRMED, CAS=V1
T1: Request A đọc V1, chuẩn bị FULFILLED
T2: Request B cũng đọc V1, chuẩn bị CANCELLED
T3: A replace(CAS V1) -> server có thể commit
T4: Response của A mất khi active failover
T5: B hoặc A retry với CAS V1 -> có thể mismatch
~~~

Nếu `CasMismatchException`:

- Không tự kết luận A đã commit hoặc đã thất bại.
- Đọc lại state hiện có và kiểm tra business transition.
- Nếu đã là `FULFILLED` và có đúng command reference của A, có thể xác nhận command đã đạt mục tiêu sau đối chiếu.
- Nếu đang `CANCELLED`, phải tuân thủ state machine, không upsert `FULFILLED` mù quáng.
- Nếu không truy cập được trong incident, tiếp tục reconciliation.

### 23.1. CAS mismatch khác durability failure

CAS mismatch cho biết phiên bản precondition không còn đúng. Một durability error nói điều kiện ack/replication/persistence không đạt hoặc chưa rõ. Hai exception dẫn đến hai đường triage khác nhau.

### 23.2. CAS không thay transaction

CAS bảo vệ một document. Khi phải update order và inventory nguyên tử, cân nhắc Couchbase Transactions theo SDK/server semantics; không thay bằng “hai write đều `PERSIST_TO_MAJORITY`”.

## 24. Transaction nhiều document và failover

Một nghiệp vụ có thể cần:

~~~text
1. Insert order::1001
2. Update inventory::sku-A1
3. Insert payment-record::1001
~~~

Ba KV mutations riêng có durability cao **không tạo atomicity**. Nếu bước 3 lỗi, bước 1/2 có thể đã commit.

Couchbase Transactions cung cấp một boundary nhiều document khi môi trường/API hỗ trợ, nhưng:

- Transaction có timeout, retry/commit semantics và durability configuration **riêng**.
- Callback transaction có thể được chạy lại khi xung đột.
- Failover/network loss có thể làm caller phải đối soát trạng thái transaction.
- Không thực hiện external payment/email/Kafka không idempotent ngay trong callback có thể retry.
- Transaction Couchbase không tự bao trùm hệ thống ngoài.

**Durability bảo vệ mutation được ack; transaction bảo vệ atomicity trong phạm vi của nó; idempotency bảo vệ replay business command.**

## 25. Sau failover, SQL++ có thể chưa thấy mutation đã tồn tại

Data Service và Index Service có đường hồi phục khác nhau. GSI nhận thay đổi qua **DCP** bất đồng bộ, nên sau một KV mutation success:

~~~text
KV get(id) -> document mới đã commit.
SQL++ WHERE status = "CONFIRMED" -> có thể chưa thấy row.
~~~

Sau failover, Index Service còn có thể phải rollback/rebuild snapshot tương thích với owner mới hoặc bắt kịp DCP. Đây là **query freshness/index availability**, không phải bằng chứng mutation durable đã mất.

### 25.1. Chọn đúng API khi đối soát

| Mục tiêu | Cách phù hợp |
|---|---|
| Đã biết ID, kiểm tra document sau timeout/failover | KV `get(id)` và so fingerprint/state |
| Danh sách chấp nhận trễ | SQL++ `NOT_BOUNDED` |
| Query cần index bắt kịp mốc request | `REQUEST_PLUS` |
| Query cần thấy mutation token đã biết | `consistentWith(MutationState)` |
| Khôi phục bản xóa nhầm | Backup/restore/audit, không dùng query consistency |

### 25.2. Không lấy `REQUEST_PLUS` làm bằng chứng persistence

`REQUEST_PLUS` chờ index mới ở mốc query; nó không xác nhận replica đã persist trước success của mutation. Ngược lại, `PERSIST_TO_MAJORITY` không tự buộc GSI theo kịp.

### 25.3. Query cũng có thể timeout vì failover

Nếu Index Service đang catch-up, một query `REQUEST_PLUS` có thể chậm hoặc timeout dù Data Service đã lưu mutation an toàn. Cần đo p99/query timeout khác với KV durable timeout.

## 26. TTL và delete có thể làm kết quả đối soát thay đổi

Một document session/order có TTL/expiry metadata có thể hết hạn hợp lệ. Failover không tự vô hiệu hóa TTL.

- `expiry` quyết định vòng đời.
- `DurabilityLevel` quyết định điều kiện ack mutation.
- `@Version`/CAS quyết định precondition update.
- Index scan consistency quyết định độ mới GSI.

Với idempotency record hoặc audit metadata, phải chọn TTL đủ dài cho cửa sổ retry và reconciliation. Một document bị xóa hoặc expire sau khi mutation thành công **không có nghĩa durability thất bại**.

### 26.1. Xóa nhầm có thể “rất bền”

Nếu lệnh `remove` sai đã được commit và replicate/persist, các replicas có thể cùng phản ánh việc xóa. Chỉ có backup, audit, retention và restore policy phù hợp mới giúp quay lại trạng thái trước xóa.

## 27. Backup, XDCR và DR: phạm vi ngoài failover nội cluster

| Cơ chế | Bảo vệ trước điều gì? | Không được coi là |
|---|---|---|
| Data replicas | Mất một Data node/vBucket active theo topology | Backup lịch sử |
| Synchronous durability | Mutation được ack theo majority/persistence | Zero data loss trước mọi kiểu lỗi |
| Auto-failover | Giảm downtime khi node không phục vụ được | Phục hồi sau mất toàn site |
| Rebalance/recovery | Khôi phục placement và redundancy | Tự sửa mọi business duplicate |
| Backup/restore | Phục hồi từ restore point khi dữ liệu bị mất/xóa/corrupt | Không có RPO/RTO nếu chưa kiểm thử |
| XDCR/replication liên cluster (khi hỗ trợ) | DR, đồng bộ dữ liệu giữa cluster theo semantics riêng | Một SyncWrite transaction/quorum xuyên region |
| Business reconciliation | Đối chiếu trạng thái đơn/payment sau response loss | Thay server-enforced durability |

### 27.1. RPO theo node failure khác RPO sau mất region

Ứng dụng có thể đặt mục tiêu không mất những mutation đã ack trong một Data node failure, nhưng muốn không mất một giao dịch nào khi **toàn region mất** cần giải pháp DR đáp ứng RPO đó. XDCR thường có replication bất đồng bộ, cần đo replication lag và khả năng failover sang cluster khác.

### 27.2. Restore test là bằng chứng cần thiết

Không được suy từ “backup job success” rằng restore sẽ đúng RPO/RTO. Cần test restore sang môi trường riêng, kiểm tra integrity và business reconciliation; tránh restore thử trực tiếp đè production.

## 28. Observability: theo dõi phục hồi dữ liệu và sẵn sàng ghi riêng biệt

### 28.1. Phía ứng dụng và SDK

- Số mutation theo keyspace và requested durability.
- KV write p50/p95/p99 trước, trong và sau failover.
- Tỷ lệ `AmbiguousTimeout`, `DurabilityAmbiguous`, `DurabilityImpossible`, CAS conflict và duplicate.
- SDK retry attempts/reasons, total operation elapsed time.
- Số business commands trong `NEEDS_RECONCILIATION`.
- HTTP 5xx/timeout, caller retry rate, duplicate-order/double-charge.
- Error budget còn lại, số critical writes tạm dừng.

### 28.2. Phía cluster

- Data nodes availability và vBucket active/replica placement.
- Under-replicated/missing replicas, pending recovery/rebalance.
- Auto-failover events, `maxCount`, preserve-majority policy.
- Bucket minimum durability và fallback state nếu có.
- Disk I/O latency, CPU/memory/network, queue/backlog.
- Index/DCP health để phân biệt query lag sau failover.
- Backup success, restore RPO/RTO và DR replication state.

Tên metric và endpoint cụ thể tùy Couchbase Server/Capella và SDK version; cần tìm dashboard đã có thay vì tự khẳng định một tên metric không tồn tại.

### 28.3. Log có thể đối soát và không lộ secrets

~~~text
timestamp=2026-11-25T03:10:00Z
service=order-service
operation=KV_INSERT
keyspace=commerce.sales.orders
requestId=checkout-abc
documentIdHash=redacted
durabilityRequested=MAJORITY
outcome=AMBIGUOUS
attempt=1
sdkException=AmbiguousTimeoutException
latencyMs=...
clusterEvent=failover-observed
reconciliationStatus=OPEN
~~~

Đây là format minh họa, không khẳng định SDK tự cung cấp mọi trường. Không log passwords, raw payment tokens hoặc document body có PII.

## 29. Runbook vận hành: failover vừa xảy ra

Runbook cần được tùy chỉnh bởi người sở hữu hệ thống. Đây là khung **kiểm tra và quyết định**, không phải lệnh tự hard-failover production.

### Pha A — phát hiện và khoanh vùng

1. Xác định thời điểm node failure, node/service bị ảnh hưởng.
2. Xác định những buckets và vBuckets có active/replica trên node đó.
3. Phân loại hard/graceful/auto failover; lưu topology và cấu hình policy.
4. Ghi nhận ongoing rebalances và mọi lỗi mutation ngay trước/sau sự kiện.
5. Phân biệt Data Service unavailability với Index/Query-only failure.

### Pha B — bảo vệ dữ liệu mới commit

1. Kiểm tra replicas còn lại, active promotion, quorum và missing copies.
2. **Trước failover thêm node**, xem có nguy cơ loại bỏ cả majority chứa mutation mới không.
3. Đối chiếu `failoverPreserveDurabilityMajority`, `maxCount` và runbook manual intervention.
4. Không bật `durabilityImpossibleFallback` theo thói quen; nếu đề xuất phải có owner RPO approval.
5. Không tuyên bố critical writes đã thành công khi chỉ có timeout/ambiguous response.

### Pha C — phục hồi dịch vụ và redundancy

1. Phục hồi Data node hoặc bổ sung node đủ capacity theo quy trình.
2. Rebalance để active/replica distribution đạt topology dự kiến.
3. Kiểm tra disk/network load và write p95/p99 trong recovery.
4. Kiểm tra Index Service/GSI sau Data failover nếu ứng dụng phụ thuộc SQL++.
5. Chạy smoke tests `insert/get/replace` trên keyspace cần thiết với durability đúng.
6. Kiểm chứng backup/DR nếu lỗi vượt phạm vi cluster.

### Pha D — hậu kiểm nghiệp vụ

1. Lấy danh sách request ambiguous quanh thời điểm failover.
2. Chạy reconciliation theo stable IDs, fingerprint và gateway references.
3. Phát hiện duplicate, lost update, order missing, double charge.
4. Ghi lại RPO/RTO thực tế so với mục tiêu.
5. Sửa capacity, topology, alarms và retry budgets nếu phát hiện lỗ hổng.

## 30. Kiểm thử failover trên staging có kiểm soát

**Không** hard-failover production để hoàn thành bài tập. Các tests cần môi trường được phép cô lập node/network, có DBA/SRE phụ trách và rollback.

| Test | Topology/điều kiện | Điều phải xác minh |
|---|---|---|
| **0 replica** | Một Data node, `MAJORITY` | 1/1 không cho copy để promote khi node mất |
| **1 replica healthy** | Hai Data nodes | Majority 2/2; đo latency và status |
| **1 replica offline** | Node giữ replica mất liên lạc | Durable writes có thể không đạt quorum, không tự báo success |
| **2 replicas healthy** | Ba Data nodes | Majority 2/3; một replica trễ có thể vẫn đạt |
| **Failover một active** | Mutation đã đạt majority, bản khác còn | Kiểm tra trạng thái dữ liệu sau promotion/recovery |
| **Hai node chứa majority cùng bị loại** | Failure drill rất thận trọng | Hiểu giới hạn đã ack nhưng bản thứ ba stale; chỉ mô phỏng trên lab |
| **Response mất sau commit** | Proxy/fault injection trên staging | Không tạo duplicate, reconciliation thành công |
| **Rebalance khi có ghi** | Controlled maintenance | SDK routing, ambiguous outcomes, retry rate |
| **Disk chậm** | Persist levels | p99, timeout và storage metrics |
| **Fallback có phê duyệt trên test** | Majority unavailable | Khẳng định đã thay contract và biết cách disable |
| **Query sau failover** | GSI/DCP phục hồi | Không nhầm index lag với mất KV mutation |
| **Restore DR** | Khôi phục sang cluster riêng | Đo RPO/RTO và business integrity |

### 30.1. Acceptance criteria ở tầng nghiệp vụ

Một bài test thành công phải xác minh:

- Không có hai order cho cùng idempotency key.
- Không có hai charge từ một checkout.
- Request ambiguous không bị ép kết luận “chưa ghi”.
- Nếu failover làm thiếu majority, critical write không tự đổi level.
- Sau recovery/rebalance, active/replica placements đạt mong muốn.
- Có bằng chứng RPO/RTO theo failure scenario được tuyên bố.

### 30.2. Đừng chỉ dừng ứng dụng rồi gọi là failover test

Dừng Java service hoặc đặt HTTP timeout thấp chủ yếu tạo lỗi ở caller; nó không cho biết cluster đã promote active ra sao. Muốn kiểm thử failover đúng, phải có node/vBucket evidence từ DBA/SRE.

## 31. Case study A — một active node lỗi sau khi order đã được ack

**Bối cảnh:** bucket có hai replicas, A active, B/C replica. Mutation M đã đạt `MAJORITY` trên A+B; A lỗi.

Cách đánh giá:

1. B chứa M, có cơ sở bảo vệ mutation trước một node failure.
2. Cluster cần promote owner phù hợp, SDK cập nhật routing.
3. KV read có thể timeout ngắn trong chuyển đổi; không đồng nghĩa document đã mất.
4. Sau failover, cluster cần recovery/rebalance để tạo lại bản dự phòng.
5. N-1 capacity, p99 và health phải được đo.

**Bài học:** recovery của dữ liệu, phục hồi availability và phục hồi redundancy là **ba mốc khác nhau**.

## 32. Case study B — hai bản giữ mutation bị failover

**Bối cảnh:** mutation M được ack trên A+B; C còn trễ. A rồi B bị failover liên tiếp.

Dù request ban đầu đã nhận `MAJORITY` success, C có thể không có M. Điều này vượt ra ngoài kịch bản mất một bản thường được majority bảo vệ.

Những biện pháp giảm rủi ro:

- Bố trí các Data copies theo failure domains độc lập.
- Review auto-failover `maxCount` và preserve-majority policy.
- Tránh manual failover tiếp theo trước khi hiểu replica state.
- Kiểm thử backup/DR cho lỗi nhiều node/site.
- Sau incident, chạy reconciliation business commands đã ack.

**Bài học:** không dùng câu “hai replicas nghĩa là chịu mất hai nodes bất kỳ”.

## 33. Case study C — API timeout khi node promote

**Bối cảnh:** mobile `POST /checkout` với key cố định, SDK gửi mutation `MAJORITY`. Active node lỗi trước khi response tới mobile; API trả timeout.

**Sai lầm:** tạo checkout ID mới và charge gateway lần nữa.

**Đúng:** giữ idempotency key, kiểm tra KV với ID ổn định và fingerprint, phân loại ambiguous, giữ reconciliation nếu chưa chắc. Gateway phải nhận idempotency key của riêng nó.

**Bài học:** server durability không tạo business exactly-once; response loss có thể xảy ra ngay lúc failover.

## 34. Case study D — bật fallback khi replica down

**Bối cảnh:** bucket một replica, replica offline, durable writes báo lỗi. Một đề xuất vận hành là bật `fallbackToActiveAck` để tiếp tục nhận đơn.

Đánh giá:

1. Có thể duy trì ghi nhưng **không còn bảo đảm majority** cho một số success.
2. Nếu order không được phép mất sau node failure, phải có business owner chấp nhận RPO mới.
3. Nếu không chấp nhận, nên trả trạng thái lỗi/chưa tiếp nhận hoặc dùng workflow queue bền độc lập đã được chuẩn bị.
4. Phải có cảnh báo, thời hạn, audit, restore redundancy, tắt fallback và reconciliation.

**Bài học:** tăng availability bằng cách làm yếu durability là quyết định nghiệp vụ, không phải tối ưu code vô hại.

## 35. Bài tập thực hành

### Bài A — vBucket và failover

Vẽ topology A/B/C với active V42 trên A, replicas trên B/C. Khi A lỗi, điều gì cần xảy ra để phục vụ KV theo ID lại? SDK có phải tự chọn node chứa document không?

### Bài B — majority

Với 0, 1, 2 replicas, tính majority. Vì sao bucket 3 replicas không thể mặc định dùng Sync Writes theo docs hiện hành?

### Bài C — bảo đảm khi mất một bản

Mutation M đã đạt `MAJORITY` trên A+B. Nếu A mất và B còn, tại sao có cơ sở để bảo vệ M? Những bước phục hồi service và redundancy nào còn thiếu?

### Bài D — mất cả majority

A+B có M, C chưa có. A+B bị failover. Có thể mất M dù SDK đã nhận success không? Vì sao `PERSIST_TO_MAJORITY` cũng không bắt C đã persist?

### Bài E — chính sách auto-failover

So `maxCount` và `failoverPreserveDurabilityMajority`. Cái nào giới hạn số lần failover, cái nào nhằm bảo vệ majority? Mỗi lựa chọn có thể ảnh hưởng availability ra sao?

### Bài F — hard và graceful

Khi nào có thể dùng graceful failover? Vì sao hard failover không thể yêu cầu node đã chết chuyển nốt pending mutations?

### Bài G — Java SDK

Viết `orders.insert(id, body, insertOptions().durability(MAJORITY))` và `replace` kết hợp CAS với `MAJORITY_AND_PERSIST_TO_ACTIVE`. Nêu hai vấn đề CAS và durability giải quyết.

### Bài H — Spring Data

Entity có `@Document(durabilityLevel=MAJORITY)`. Có thể từ đó suy ra bucket có đủ replicas khỏe không? Nếu một đường SDK direct write không có options, mức nào có thể áp dụng?

### Bài I — reactive retry

Một `Mono.defer` sinh ID mới mỗi lần subscribe rồi retry khi timeout. Điều gì có thể xảy ra nếu lần đầu commit nhưng response mất? Thiết kế ID ổn định và filter retry phù hợp.

### Bài J — timeout ambiguous

`POST /orders` nhận ambiguous. Một lần `get(id)` trả not-found. Có được khẳng định mutation cũ chưa thể commit không? Đề xuất reconciliation workflow.

### Bài K — GSI sau failover

KV `get(id)` thấy body mới nhưng SQL++ `NOT_BOUNDED` chưa thấy. Vì sao điều này không chứng minh durable write thất bại? Khi nào dùng `REQUEST_PLUS`?

### Bài L — DR

Hãy viết hai RPO khác nhau: một cho mất một Data node, một cho mất cả region. Durability nội cluster giải quyết trường hợp nào? Cần backup/XDCR/restore test ở đâu?

### Bài M — cluster đang suy giảm

Sau auto-failover, API đọc hoạt động, nhưng `PERSIST_TO_MAJORITY` writes bị timeout. Hãy nêu cách triage replica/disk/network, retry budget và thời điểm escalation.

### Bài N — runbook

Thiết kế failure drill với A/B/C ở staging: mutation success, failover một node, recovery/rebalance, xác minh redundancy. Cần metric, acceptance criteria, rollback và owner nào?

## 36. Checklist trước production

- [ ] Định nghĩa failure scenario, RPO và RTO được chấp nhận bằng văn bản.
- [ ] Biết Data vBucket active/replica placement, không chỉ node count.
- [ ] Với Sync Writes theo docs hiện hành, dùng bucket 0–2 replicas; không suy đoán 3 replicas được hỗ trợ.
- [ ] Hiểu majority 1/1, 2/2 và 2/3 cùng giới hạn khi thiếu bản.
- [ ] Không hứa 0 replicas bảo vệ được mất Data node duy nhất.
- [ ] Phân biệt pending, commit và response nhận bởi SDK.
- [ ] Không suy từ success `MAJORITY` rằng mọi replica đã nhận/persist.
- [ ] Xem xét rủi ro mất cả tập hợp Data nodes giữ majority.
- [ ] Review auto-failover `maxCount` và `failoverPreserveDurabilityMajority` theo edition/version.
- [ ] Không manual failover thêm node đang giữ mutation mới khi chưa biết rủi ro.
- [ ] Coi `durabilityImpossibleFallback` là suy giảm bảo đảm cần phê duyệt.
- [ ] Sau failover phải recovery/rebalance và kiểm tra actual replica placement.
- [ ] Có N-1 capacity và quan sát disk/network latency trong recovery.
- [ ] Spring Data entity default không thay bucket policy/topology.
- [ ] Kiểm tra SDK direct writes có durability options rõ ràng khi cần.
- [ ] Dùng CAS cho concurrent updates, transaction cho multi-document invariants.
- [ ] Dùng stable IDs, fingerprint và idempotency cho retry sau ambiguous.
- [ ] Không coi HTTP timeout/Reactor cancellation là rollback Couchbase.
- [ ] Không dùng SQL++ `NOT_BOUNDED` làm bằng chứng write chưa tồn tại.
- [ ] Phân biệt Data replicas, GSI replicas, XDCR và backup.
- [ ] Có backup/DR, restore drill và business reconciliation cho lỗi vượt cluster.
- [ ] Đo KV p95/p99, durability errors, failover/rebalance events, under-replication.
- [ ] Diễn tập lỗi chỉ trên môi trường được phép, có owner và rollback.

## 37. Tổng kết

**Failover giúp khôi phục khả năng phục vụ; durability quy định điều kiện mà một mutation phải đạt trước khi được xác nhận.** Trong Couchbase, một mutation đã thành công ở `MAJORITY` thường có thêm bản để chống lỗi một Data node theo topology/protocol phù hợp. Nhưng với bucket hai replicas, majority chỉ là **2/3**: nếu hai node giữ mutation mới bị failover trước khi bản thứ ba bắt kịp, dữ liệu vẫn có thể mất.

Các persistence levels tăng bảo vệ trước một số lỗi nhưng không làm mọi bản sao đã persist, cũng không thay thế backup/DR. Chính sách auto-failover, bảo vệ majority, replica placement, recovery/rebalance và N-1 capacity quyết định khả năng phục hồi trong thực tế.

Với **Spring Data Couchbase**, phải tách `@Document.durabilityLevel`, `CouchbaseTemplate.withDurability`, SDK mutation options và bucket minimum khỏi business idempotency, CAS và transaction. Khi response của một mutation mất trong failover, đừng tự khẳng định thất bại: dùng ID ổn định, đọc/đối chiếu, retry có giới hạn và reconciliation. Một thiết kế đúng không chỉ đặt enum mà còn có **failure scenarios, runbook, metrics, bài diễn tập và RPO/RTO được kiểm chứng**.

## Tài liệu tham khảo chính thức

1. [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): Sync Writes, majority, persistence, bảo đảm và giới hạn khi failover.
2. [Couchbase Server — Auto-Failover Settings](https://docs.couchbase.com/server/current/rest-api/rest-cluster-autofailover-enable.html): policy `maxCount` và `failoverPreserveDurabilityMajority` trong môi trường hỗ trợ.
3. [Couchbase Server — Server Group Awareness](https://docs.couchbase.com/server/current/learn/clusters-and-availability/groups.html): placement và failure domains.
4. [Couchbase Server — Creating and Editing Buckets](https://docs.couchbase.com/server/current/rest-api/rest-bucket-create.html): replica count, durability minimum, fallback trong phiên bản hỗ trợ.
5. [Couchbase Java SDK — KV Data Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): mutation options và DurabilityLevel.
6. [Couchbase Java SDK — Handling Errors](https://docs.couchbase.com/java-sdk/current/howtos/error-handling.html): ambiguous timeout, retry/idempotence và error context.
7. [Spring Data Couchbase — Template and Direct Operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): entity metadata và `withDurability(...)`.

Bài học dùng ví dụ minh họa để hình thành phương pháp thiết kế và vận hành. Trước khi áp dụng, cần xác minh đúng **phiên bản Couchbase Server/Capella, edition, bucket type, topology, Java SDK và Spring Data** của dự án; STEP 6 sẽ thực hiện vòng Content QA học thuật riêng.


