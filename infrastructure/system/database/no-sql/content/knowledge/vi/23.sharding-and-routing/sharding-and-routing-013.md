# Tra cứu metadata định tuyến và xử lý bản đồ vị trí đã cũ

Trong một hệ NoSQL được **phân mảnh (sharding)**, dữ liệu không còn nằm ở một máy. Trước khi đọc hoặc ghi một Order, User hay Inventory, ứng dụng, driver, proxy hoặc coordinator cần tìm **shard nào đang sở hữu dữ liệu đó** và **replica nào được phép phục vụ yêu cầu**. Thông tin dùng để đưa ra quyết định gọi chung là **routing metadata**: bản đồ từ shard key, hash slot, token range hoặc bucket tới shard, node và quyền sở hữu hiện hành.

Khó khăn xuất hiện khi bản đồ **thay đổi trong lúc hệ đang hoạt động**. Một range được chuyển từ Node A sang Node B, một shard được tách, leader mới được bầu hoặc replica group thay đổi sau lỗi mạng. Router chưa nhận thông báo có thể giữ **bản đồ vị trí đã cũ (stale routing map)** và gửi request đến nơi không còn quyền phục vụ. Với read, hệ có thể tăng độ trễ hoặc trả lỗi; với write, nếu ownership không được kiểm soát, một lỗi định tuyến có thể dẫn đến **hai nơi cùng ghi** hoặc **retry nhân đôi tác động nghiệp vụ**.

Bài học tập trung vào cách **tra cứu routing metadata, phát hiện map cũ, refresh, redirect, retry an toàn và bảo vệ quyền ghi khi chuyển shard**. Các ví dụ dùng MongoDB, Cassandra/ScyllaDB, Redis Cluster, Elasticsearch/OpenSearch và DynamoDB, kèm timeline, sơ đồ, pseudocode và bài tập.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **logical shard**, **physical node**, **replica**, **router** và **metadata authority**.
2. Giải thích cách tra cứu shard bằng range map, hash slots, token ring hoặc directory theo tenant.
3. Nêu nguyên nhân metadata cache cũ: migration, rebalance, split, failover, topology change và sự kiện invalidation bị trễ.
4. Phân biệt **placement epoch**, **leader term**, **metadata revision** và **document version**.
5. Thiết kế luồng **NOT_OWNER → refresh → retry có giới hạn** mà không tạo double write.
6. Hiểu vì sao **timeout sau commit** khác với việc server **từ chối trước mutation**.
7. Dùng request ID/idempotency ledger, ownership fencing và checkpoint khi resharding.
8. Phân biệt redirect Redis Cluster `MOVED` và `ASK`.
9. Phân tích những lớp định tuyến khác nhau của MongoDB, Cassandra, Elasticsearch/OpenSearch và DynamoDB.
10. Thiết kế fault-injection test kiểm chứng route freshness, latency, kết quả ghi và bất biến nghiệp vụ.

## 2. Tình huống xuyên suốt: tenant chuyển từ Shard A sang Shard B

Giả sử Order:

~~~json
{
  "tenantId": "merchant-a",
  "orderId": "O900",
  "status": "PAID",
  "version": 17
}
~~~

Ban đầu, router giữ:

~~~text
tenantId = merchant-a
  -> logicalShard = orders-7
  -> currentOwner = Node A
  -> placementEpoch = 41
~~~

Vì Node A quá tải, hệ thống chuyển `orders-7` sang Node B. Sau khi sao chép dữ liệu, bắt kịp write và thực hiện cutover an toàn, nguồn metadata có thẩm quyền đổi thành:

~~~text
tenantId = merchant-a
  -> logicalShard = orders-7
  -> currentOwner = Node B
  -> placementEpoch = 42
~~~

Tuy nhiên một instance của API vẫn giữ cache epoch 41:

~~~text
              Router R1                      Metadata authority
           cached epoch 41                       epoch 42
                  |                                 |
                  v                                 v
              owner A                           owner B
                  |
                  v
            Request đến A
                  |
          A không còn quyền ghi
~~~

Một router tốt phải có khả năng **nhận diện vị trí cũ, lấy bản đồ mới và gửi lại đúng nơi**. Quan trọng hơn, Node A phải **không được tiếp tục commit** sau khi quyền ghi đã chuyển sang B.

### 2.1. Ba trạng thái không được đánh đồng

| Kết quả ở owner cũ | Điều ta biết | Hành động an toàn |
| --- | --- | --- |
| `NOT_OWNER_BEFORE_APPLY` | Server xác nhận **chưa áp mutation** | Refresh map rồi route lại theo retry policy |
| Timeout/connection reset | Mutation **có thể đã commit** | Tra outcome bằng ID hoặc trả PENDING; không retry mù |
| Old owner vẫn commit sau cutover | Hai owner có thể ghi song song | Lỗi safety; cần fencing và reconciliation |

**Stale routing chỉ nên gây thêm bước refresh hoặc một lỗi có thể phục hồi, không được tự biến thành mất dữ liệu hoặc ghi trùng.**

## 3. Routing metadata chứa gì?

Một record khái niệm:

~~~json
{
  "logicalShardId": "orders-7",
  "keyRange": {
    "startInclusive": "tenant-a",
    "endExclusive": "tenant-g"
  },
  "replicaGroupId": "rg-7",
  "members": ["node-b", "node-c", "node-d"],
  "writeAuthority": "node-b",
  "placementEpoch": 42,
  "directoryRevision": 1084,
  "migrationState": "ACTIVE"
}
~~~

Đây là **mô hình minh họa**, không phải format bắt buộc của một vendor.

| Trường | Vai trò |
| --- | --- |
| `keyRange` / hash slot / token | Xác định những khóa thuộc đơn vị dữ liệu này |
| `logicalShardId` | Định danh shard, có thể giữ nguyên khi đổi physical owner |
| `replicaGroupId` | Nhóm node có các bản sao của shard |
| `members` | Danh sách replica theo topology hiện hành |
| `writeAuthority` | Quyền ghi nếu giao thức dùng leader/owner |
| `placementEpoch` | Thế hệ placement/ownership |
| `directoryRevision` | Phiên bản snapshot/bảng định tuyến |
| `migrationState` | Trạng thái dữ liệu đang chuyển/chưa chuyển |

### 3.1. Ba tầng quyết định

~~~mermaid
flowchart TD
    A["Routing key: tenantId + orderId"] --> B["Tìm logical shard"]
    B --> C["Tra placement: shard -> replica group"]
    C --> D["Chọn leader/quorum/replica theo operation"]
    D --> E["Node xác minh authority và business condition"]
    E --> F["Read hoặc mutation"]
~~~

Tầng 1: `key → logical shard`.

Tầng 2: `logical shard → replica group/physical nodes`.

Tầng 3: `replica group → node được phép phục vụ read/write`.

Khi **split range**, tầng 1 thay đổi. Khi **move shard**, tầng 2 thay đổi. Khi **leader failover**, tầng 3 thay đổi. Một request có thể sai route do một hoặc nhiều tầng.

### 3.2. Logical shard khác physical node

Một Node A có thể chứa nhiều shard; một shard có thể có nhiều bản sao trên A/B/C. Vì vậy:

~~~text
logicalShardId != nodeId
replicaCount    != shardCount
~~~

Không xây directory cố định `orderId → hostname` rồi cho rằng shard không bao giờ chuyển chỗ.

### 3.3. Những version không cùng ý nghĩa

**Document version:** `O900: 17 → 18`, diễn tả thay đổi nội dung Order.

**Placement epoch:** `orders-7: A/41 → B/42`, diễn tả thế hệ quyền sở hữu.

**Metadata revision:** `1083 → 1084`, diễn tả bản cập nhật của directory hoặc cluster state.

**Leader term:** Thế hệ bầu leader của một replica group theo giao thức.

Không được suy:

~~~text
Order.version == placementEpoch == directoryRevision == leaderTerm
~~~

Mỗi token có **scope và quy tắc tăng** riêng. So sánh epoch chỉ có nghĩa nếu chúng thuộc cùng phạm vi mà giao thức định nghĩa.

## 4. Control plane và data plane

**Control plane** quản lý topology, shard placement, metadata version, rebalancing và ownership.

**Data plane** nhận read/write tới các shards và thực thi chúng.

~~~mermaid
flowchart LR
    Client["Application"] --> Router["Driver / Router cache"]
    Router --> DataA["Shard group A"]
    Router --> DataB["Shard group B"]
    Meta["Metadata authority"] -.->|"Placement updates"| Router
    Meta -.->|"Ownership / term"| DataA
    Meta -.->|"Ownership / term"| DataB
~~~

### 4.1. Tại sao không hỏi control plane mỗi request?

Giả sử một ứng dụng có 40.000 reads/s. Nếu mọi request đều cần:

~~~text
read metadata -> resolve shard -> read data
~~~

metadata authority trở thành một nút thắt và thêm round trip vào tất cả request. Do đó nhiều hệ dùng **client/driver/router cache**.

### 4.2. Cache nhanh nhưng không phải authority vĩnh viễn

~~~text
cache["orders-7"] = {owner:"A", epoch:41, fetchedAt:T0}
~~~

Cache chỉ phản ánh kiến thức của router tại T0. Nếu control plane đã commit epoch 42 tại T1, cache có thể stale ngay lập tức dù TTL chưa hết.

**Server-side owner validation/fencing** mới bảo vệ safety khi router chưa kịp cập nhật.

### 4.3. Metadata authority cũng cần nhất quán

Nếu hai metadata servers độc lập có thể cùng xác nhận hai owner khác nhau, client sẽ nhận các kết quả mâu thuẫn. Quyền sở hữu shard quan trọng thường cần **một protocol commit/quorum/consensus hoặc cơ chế điều phối tương đương**, không chỉ hai bản sao của file cấu hình.

## 5. Các cách tra cứu từ key tới shard

### 5.1. Range-based routing

~~~text
[-inf, tenant-g)      -> Shard 0
[tenant-g, tenant-p)  -> Shard 1
[tenant-p, +inf)      -> Shard 2
~~~

Router tìm range chứa `tenantId`. Khi split:

~~~text
OLD:
[tenant-g, tenant-p) -> Shard 1

NEW:
[tenant-g, tenant-m) -> Shard 1
[tenant-m, tenant-p) -> Shard 3
~~~

Router giữ bảng cũ sẽ gửi `tenant-n` tới Shard 1. Đôi khi **logical shard mapping** thay đổi chứ không chỉ physical host.

### 5.2. Hash slots

~~~text
key -> hash slot -> owner node/group
~~~

Hash của key có thể **không đổi** khi slot chuyển từ A sang B. Thay đổi nằm ở `slot → owner`; đây là ý tưởng thấy rõ trong Redis Cluster.

### 5.3. Token ring

Partition key được hash thành token, token ranges được ánh xạ tới replica sets theo topology/replication strategy. Token-aware driver sử dụng metadata để chọn coordinator/replica hợp lý. Node join/leave có thể làm **ring metadata cũ**.

### 5.4. Directory theo tenant/bucket

~~~text
tenant-a / bucket-0 -> Shard 3
tenant-a / bucket-1 -> Shard 5
tenant-b / bucket-0 -> Shard 1
~~~

Directory cho phép điều chuyển tenant hoặc bucket linh hoạt. Tuy nhiên metadata cần version, cache, consistent snapshot và migration safety.

### 5.5. Mapping nhiều tầng

~~~text
tenantId, orderId
   |
bucket = stableHash(orderId) % 16
   |
directory[tenantId,bucket]
   |
logicalShardId
   |
placement[logicalShardId]
   |
replicaGroup / write authority
~~~

**Chọn đúng shard không đồng nghĩa chọn đúng replica.** Một replica thuộc shard nhưng đang lag có thể không đáp ứng read-after-write; một node reachable có thể không còn quyền commit.

## 6. Vì sao metadata bị cũ?

| Nguyên nhân | Bản đồ nào thay đổi? | Hệ quả với router cũ |
| --- | --- | --- |
| Thêm node/rebalance | Shard → node | Extra hop, redirect |
| Split/merge range | Key range → shard | Gửi sai logical shard |
| Move tenant/bucket | Directory mapping | Nhắm owner cũ |
| Leader failover | Replica group → leader | Gửi write tới follower/old leader |
| Node join/leave | Replica membership | Chọn coordinator/replica không tối ưu |
| Network partition | Authority/reachability | Timeout, thiếu quorum |
| Cache TTL | Refresh chưa xảy ra | Tiếp tục dùng snapshot cũ |
| Push notification đến muộn | Revision không mới | Cache áp event sai thứ tự |
| Router restart từ snapshot cũ | Bootstrap metadata cũ | Cần refresh trước khi tin mapping |
| Schema/config rollout | Version của routing algorithm | Client cũ tính shard khác client mới |

### 6.1. TTL ngắn không loại bỏ cửa sổ stale

~~~text
t=0 ms: Router tải epoch 41, TTL 100 ms.
t=1 ms: Control plane commit epoch 42.
t=2 ms: Router gửi request theo epoch 41.
~~~

TTL không ngăn request lúc t=2. Một thiết kế an toàn vẫn cần **old-owner rejection/redirect và authority check**.

### 6.2. Reachability không phải ownership

Node A trả ping tốt không có nghĩa A vẫn là owner. Node B mất kết nối tạm thời không có nghĩa router có quyền chuyển ghi tùy ý sang Node C.

**Reachable ≠ allowed to commit.**

## 7. Timeline: bản đồ epoch 41 dẫn tới Node A đã cũ

Giả sử thời điểm dưới đây chỉ là số liệu minh họa, có cùng một trục thời gian trong lab:

| UTC | Thành phần | Sự kiện | Kết quả |
| --- | --- | --- | --- |
| 09:00:00.000 | Router R1 | Cache map | `orders-7 → A, epoch=41` |
| 09:00:01.000 | Migrator | Hoàn tất catch-up sang B | B có dữ liệu đã xác nhận |
| 09:00:01.050 | Authority | Commit cutover | `orders-7 → B, epoch=42` |
| 09:00:01.060 | Node A | Không còn quyền ghi | Fenced |
| 09:00:01.080 | Client | Gửi mutation `op-810` | Update O900 |
| 09:00:01.085 | R1 | Gửi tới A bằng epoch 41 | Cache stale |
| 09:00:01.090 | A | Trả `NOT_OWNER` | **Không áp mutation** |
| 09:00:01.095 | R1 | Refresh metadata | Nhận epoch 42 |
| 09:00:01.100 | R1 | Gửi tới B | Giữ `op-810` |
| 09:00:01.110 | B | Áp update | Order v17 → v18 |
| 09:00:01.115 | Client | Nhận SUCCESS | Owner B |

### 7.1. Vì sao lịch này có thể an toàn?

- A thực sự từ chối **trước mutation**.
- B có authority khi commit.
- Dữ liệu/changes đã được chuyển tới B đúng mốc.
- Router giữ cùng logical operation ID qua retry.
- B kiểm tra business condition/document version riêng với placement epoch.

### 7.2. Epoch phải được thực thi tại nơi ghi

Request minh họa:

~~~json
{
  "shardId": "orders-7",
  "expectedPlacementEpoch": 41,
  "logicalOperationId": "op-810",
  "orderId": "O900",
  "expectedOrderVersion": 17,
  "newStatus": "SHIPPED"
}
~~~

Token epoch chỉ hữu ích nếu server/giao thức **xác minh ownership khi commit**. Client tự mang epoch 41 trong JSON không ngăn Node A ghi sai nếu A còn nhận write vô điều kiện.

### 7.3. Business conflict khác routing conflict

B có thể là owner đúng nhưng trả `ORDER_VERSION_CONFLICT` vì một worker khác đã chuyển O900 từ v17 lên v18.

Không được xử lý business conflict bằng cách đổi route hoặc ép ghi với version mới. Cần đọc lại entity và kiểm tra ý định nghiệp vụ.

## 8. Timeout sau commit: một lịch khác hoàn toàn

| UTC | Sự kiện |
| --- | --- |
| 09:02:00.000 | Router gửi `reserve(op-900)` tới A, epoch 41 còn hiệu lực |
| 09:02:00.010 | A commit stock 10 → 9 |
| 09:02:00.012 | Response bị mất trên mạng |
| 09:02:00.020 | Cutover sang B với dữ liệu đã catch-up |
| 09:02:00.050 | Router thấy timeout |
| 09:02:00.060 | Router refresh map epoch 42 |

Lúc này **không thể suy write ở A chưa áp**. Nếu gửi mù lệnh decrement tới B, stock có thể giảm 9 → 8 dù chỉ có một ý định `op-900`.

### 8.1. Ma trận xử lý

| Kết quả attempt | Có thể biết đã áp? | Retry như thế nào? |
| --- | --- | --- |
| `NOT_OWNER_BEFORE_APPLY` có bảo đảm rõ | Chưa áp ở server ấy | Refresh/retry theo contract |
| `CONDITIONAL_CHECK_FAILED` | Điều kiện không đạt | Xử lý business conflict; không retry mù |
| `TIMEOUT`/connection reset | **Không rõ** | Tra idempotency/transaction status; PENDING nếu chưa xác minh |
| `SUCCESS` có xác nhận đúng | Đã áp theo mức ack đã hứa | Trả kết quả, không thực thi lại |

### 8.2. Di chuyển cả thông tin chống trùng

Nếu chỉ copy Order/Inventory nhưng bỏ quên **idempotency ledger**, B có thể không biết `op-900` đã được áp trước cutover.

~~~json
{
  "logicalOperationId": "op-900",
  "payloadHash": "hash-of-reservation-intent",
  "state": "SUCCEEDED",
  "reservationId": "R900",
  "appliedOrderVersion": 18
}
~~~

Ledger và mutation phải được phối hợp trong ranh giới giao dịch **hoặc workflow phục hồi được**. Bản ghi chống trùng phải sống đủ lâu cho cửa sổ retry/replay và được xử lý đúng khi shard di chuyển.

### 8.3. Logical request khác attempt

~~~text
logicalOperationId = op-900
  attempt-1 -> gửi tới A -> TIMEOUT (unknown outcome)
  attempt-2 -> gửi tới B -> phải tra dedup/trạng thái
~~~

Không đếm hai attempt thành hai lần giữ hàng độc lập.

## 9. Ownership fencing và tránh split ownership

Giả sử metadata đã chuyển epoch 42 cho B nhưng A bị cô lập khỏi authority và vẫn tin mình ở epoch 41:

~~~text
A: nhận write X, lưu ở bản cũ.
B: nhận write Y, lưu ở bản mới.
~~~

Hai nhánh mutation có thể làm mất cập nhật hoặc vi phạm ràng buộc như “một ghế chỉ được xác nhận cho một khách”.

### 9.1. Fencing token/ownership generation

Ý tưởng:

~~~text
Shard orders-7:
  epoch 41 -> Owner A
  epoch 42 -> Owner B

Sau khi epoch 42 được commit:
  write từ owner cũ/epoch 41 không được commit.
~~~

**Fencing phải được cưỡng chế ở ranh giới commit.** Chỉ gửi notification “A hãy dừng” không đủ nếu notification không tới A do partition.

### 9.2. Healthcheck không chứng minh quyền ghi

`isLeader=true` trong RAM, hoặc endpoint `/health=200`, không có nghĩa process đó còn quorum hay authority. Giao thức leader election, term, lease và consensus cần đủ bảo đảm theo fault model.

### 9.3. Không tự dual-write trong migration

Việc ứng dụng ghi song song:

~~~text
UPDATE A
UPDATE B
~~~

không biến hai write thành transaction. Crash giữa hai lệnh, thứ tự concurrent update hoặc response bị mất có thể tạo divergence. Nếu engine hỗ trợ migration trực tuyến, nên dùng **giao thức/primitive được hỗ trợ** thay vì triển khai dual-write mù.

## 10. Những giai đoạn chuyển shard điển hình

~~~mermaid
flowchart TD
    A["PLANNED: chọn range và owner đích"] --> B["COPYING: sao chép snapshot"]
    B --> C["CATCHING_UP: áp writes sau snapshot"]
    C --> D["CUTOVER_READY: xác minh mốc dữ liệu"]
    D --> E["FENCE old owner và chuyển authority an toàn"]
    E --> F["PUBLISH mapping epoch mới"]
    F --> G["New owner ACTIVE"]
    G --> H["Old owner REDIRECT/DRAIN"]
    H --> I["CLEANUP sau cửa sổ an toàn"]
~~~

Sơ đồ là **mô hình khái niệm**, không phải thuật toán migration chung cho mọi vendor. Trình tự chuyển authority và metadata phải được phối hợp đúng giao thức để không tạo cửa sổ hai owner.

### 10.1. Snapshot không đủ

~~~text
T1: Snapshot O900 v17 copy từ A sang B.
T2: A commit O900 v18.
T3: B bắt đầu làm owner.
~~~

Nếu B chỉ có v17, write v18 có thể bị mất. Cần **catch-up bằng change log/CDC hoặc phương pháp tương đương**, rồi xác định mốc cutover.

### 10.2. Request đang bay

Request có thể đến A khi A còn quyền nhưng response đến client **sau** cutover. Không được suy mutation thuộc epoch nào chỉ từ thời điểm nhận response. Cần commit log/authority evidence.

### 10.3. Old owner có thể redirect nhưng không được ghi độc lập

Trong grace period, A có thể còn giữ bản dữ liệu để redirect hoặc forward an toàn theo giao thức; điều đó **không phải giấy phép nhận write độc lập** sau khi B đã có quyền.

## 11. Các cách phát hiện stale map

| Cách | Ưu điểm | Hạn chế |
| --- | --- | --- |
| TTL | Dễ triển khai | Stale trong thời gian TTL |
| Periodic polling | Có thể hồi phục khi mất notification | Tốn lookup và có độ trễ |
| Watch/push invalidation | Cập nhật nhanh | Event có thể trễ, rớt, watch mất kết nối |
| Epoch/revision | Nhận biết map mới/cũ | Phải so trong scope đúng |
| `NOT_OWNER`/redirect | Refresh đúng lúc cần | Request đầu sau migration có extra hop |
| Trusted metadata lookup | Kiểm tra authority | Có thể tạo bottleneck nếu gọi mọi request |
| Router/coordinator trung gian | Client đơn giản hơn | Thêm hop và phụ thuộc router |

### 11.1. Kết hợp nhiều chiến lược

Một hệ có thể:

1. Tải snapshot metadata khi startup.
2. Cache trong driver/router.
3. Nhận watch thông báo topology change.
4. Poll định kỳ để hồi phục sau khi bỏ sót event.
5. Refresh ngay khi nhận stale-route response.
6. Dù vậy, server vẫn xác minh ownership lúc commit.

### 11.2. Negative cache cũng có thể cũ

Router từng cache `tenant-x NOT_FOUND`; sau đó tenant được tạo. Nếu negative entry sống quá lâu, client vẫn bị báo không tồn tại. Cần TTL/invalidation/version policy cho cả **kết quả không có mapping**.

### 11.3. Snapshot metadata pha trộn

Revision 10:

~~~text
[a,m) -> A
[m,z) -> B
~~~

Revision 11:

~~~text
[a,g) -> A
[g,z) -> C
~~~

Nếu router lấy entry đầu từ revision 10 và entry sau từ revision 11, khoảng `[g,m)` có thể được ánh xạ chồng lấn hoặc thiếu tùy cách ghép. Cần **snapshot nhất quán hoặc delta có revision/sequence**; không áp những entry rời rạc theo thứ tự nhận mạng mà không kiểm tra.

## 12. Redirect, refresh và retry có giới hạn

~~~mermaid
flowchart TD
    A["Operation với routing key"] --> B["Resolve cached route"]
    B --> C["Gửi tới endpoint"]
    C --> D{"Response?"}
    D -->|SUCCESS| E["Trả kết quả"]
    D -->|NOT_OWNER trước mutation| F["Invalidate/refresh metadata"]
    F --> G{"Map mới và còn retry budget?"}
    G -->|Có| B
    G -->|Không| H["Routing unavailable"]
    D -->|Timeout / unknown outcome| I["Tra logical operationId"]
    I --> J{"Đã áp?"}
    J -->|Có| E
    J -->|Chưa có bằng chứng áp| F
    J -->|Không rõ| K["PENDING / reconciliation"]
    D -->|Business conflict| L["Trả conflict, không ép ghi"]
~~~

### 12.1. Khi nào có thể route lại?

Route lại có thể phù hợp khi server có response đáng tin **bảo đảm không áp mutation**, và client có retry budget. Không thể sử dụng một lỗi kết nối tổng quát như bằng chứng không ghi.

### 12.2. Không lặp vô hạn

~~~text
maxRouteRetries = 3       (ví dụ)
deadline = 800 ms         (ví dụ)
backoff = exponential with jitter
refresh on newer epoch
detect repeated endpoint+epoch
~~~

Giá trị thực tế phụ thuộc SLO và database. Nếu A bảo B là owner, B lại bảo A là owner, router phải **phát hiện loop và dừng**, không làm control plane hoặc client nghẽn vô hạn.

### 12.3. Hint không phải chân lý không cần kiểm chứng

Redirect có thể chứa endpoint/revision mới. Client chỉ nên dùng endpoint thuộc **cluster/namespace tin cậy** và metadata đáng xác minh. Không mở kết nối tùy ý tới host do một response chưa được xác thực gợi ý.

## 13. Java pseudocode của routing retry

Mã dưới đây dùng các interface giả định, minh họa **logic phân nhánh**, không phải client chính thức của một NoSQL cụ thể:

~~~java
WriteResult routeWrite(WriteRequest request, Deadline deadline) {
    if (request.logicalOperationId() == null) {
        throw new IllegalArgumentException("Missing operation ID");
    }

    Set<String> visited = new HashSet<>();

    for (int attempt = 0; attempt < 4; attempt++) {
        deadline.throwIfExpired();
        Route route = directory.resolveCached(request.routingKey());
        String hop = route.owner() + "@" + route.epoch();

        if (!visited.add(hop)) {
            directory.forceRefresh(request.routingKey());
            continue;
        }

        try {
            return rpc.write(
                route.owner(),
                request.withPlacementEpoch(route.epoch()),
                deadline
            );
        } catch (NotOwnerBeforeApplyException ex) {
            // Server bảo đảm mutation chưa được áp.
            directory.invalidateIfEpochNotNewer(
                request.routingKey(), route.epoch()
            );
            directory.forceRefresh(request.routingKey());
        } catch (UnknownWriteOutcomeException ex) {
            // Không được tự gửi lại mutation có thể đã commit.
            return operationTracker.resolveOrPending(
                request.logicalOperationId(),
                request.payloadHash(),
                deadline
            );
        }
    }

    throw new RoutingUnavailableException("Too many redirects");
}
~~~

Những giả định bắt buộc:

- `NotOwnerBeforeApplyException` chứng minh **không có mutation được áp ở attempt này**.
- `logicalOperationId` ổn định qua retry; `attemptId` riêng có thể ghi trong trace.
- Server thực thi **ownership fencing**, router không tự bảo vệ write safety.
- `operationTracker` dựa trên dedup ledger/transaction authority đủ tin cậy.
- `directory.forceRefresh` lấy metadata nhất quán, không ghi đè cache mới bằng epoch cũ.
- Deadline bao cả lookup, RPC và retry.

## 14. Singleflight để ngăn thundering herd

Một shard vừa chuyển chỗ, 5.000 request cùng có cache epoch 41. Nếu tất cả request tự gọi control plane:

~~~text
5.000 NOT_OWNER responses
  -> 5.000 metadata lookups
  -> overload control plane
  -> refresh chậm
  -> stale errors tiếp tục tăng
~~~

**Singleflight** gộp nhiều refresh của cùng shard/range:

~~~text
Request đầu: khởi tạo refresh future.
Các request sau: đợi cùng future.
Metadata lookup: chỉ một lần trong cửa sổ gộp.
Khi hoàn tất: các request nhận chung snapshot mới.
~~~

Trong Java có thể dùng `ConcurrentHashMap<ShardId, CompletableFuture<Route>>` hoặc cơ chế tương đương. Phải có timeout, xử lý failure và dọn future sau hoàn tất; không cache mãi một future lỗi.

### 14.1. Không hạ epoch

Nếu cache đã epoch 43, nhưng notification epoch 42 đến muộn:

~~~text
cached epoch = 43
incoming hint = 42
=> không downgrade
~~~

Chỉ so version nếu cùng phạm vi mà giao thức định nghĩa, và metadata phải từ nguồn tin cậy. Với delta events, cần phát hiện **revision bị nhảy/gap** rồi tải snapshot đầy đủ.

### 14.2. TTL quá dài và quá ngắn

- TTL quá dài: nhiều request đi qua old owner.
- TTL quá ngắn: tăng metadata QPS, cache misses và p95.
- TTL bằng 0: không giải quyết race giữa lookup và commit, nhưng làm control plane bị phụ thuộc trên hot path.

Kết hợp TTL, watch, error-driven refresh và server-side fencing thường hữu ích hơn chỉ giảm TTL.

## 15. Redis Cluster: MOVED và ASK

Redis Cluster giúp thấy rõ một client cache **hash-slot map** rồi cập nhật khi vị trí dữ liệu thay đổi. Không gian khóa Redis Cluster được chia thành **16.384 hash slots**, mỗi slot thuộc về một node owner theo trạng thái cluster.

### 15.1. MOVED — owner slot đã khác với vị trí client dùng

Một phản hồi minh họa:

~~~text
Client -> Node A:
  GET user:42

Node A -> Client:
  -MOVED 12182 10.0.0.2:6379
~~~

Ý nghĩa: lệnh đang liên quan slot `12182` và node A hướng client tới owner thích hợp `10.0.0.2:6379`. Một client cluster-aware có thể **gửi lại request và cập nhật/refresh slot map** để những request sau không tiếp tục đi nhầm.

Số slot và địa chỉ trên là ví dụ, không khẳng định khóa `user:42` thực sự hash ra 12182 trong mọi môi trường.

### 15.2. ASK — redirect tạm thời lúc slot đang chuyển

Khi có slot migration, Redis có thể trả:

~~~text
-ASK 12182 10.0.0.2:6379
~~~

Client cần gửi:

~~~text
Client -> Target:
  ASKING
  GET user:42
~~~

`ASKING` cho phép target xử lý command cụ thể trong khi migration chưa hoàn tất. **ASK không chứng minh owner map đã đổi vĩnh viễn**, nên không được ghi nhớ như MOVED.

| Redirect | Ý nghĩa | Xử lý client |
| --- | --- | --- |
| **MOVED** | Owner/slot map cần được cập nhật | Route lại, cập nhật/refresh mapping |
| **ASK** | Chuyển hướng tạm khi migration | Gửi `ASKING` rồi command đến target; không cập nhật owner map lâu dài chỉ từ ASK |

### 15.3. Retry an toàn cho Redis

- Giới hạn redirect hops và phát hiện loop.
- Chỉ tin endpoint thuộc cluster được phép truy cập.
- Không nhầm lỗi MOVED/ASK với timeout sau commit.
- Lệnh có tác động nghiệp vụ cần idempotency/retry semantics, không tự thực thi lại mù khi outcome không rõ.
- Ưu tiên client Redis Cluster chính thức hoặc thư viện hiểu protocol.

### 15.4. Hash tags và multi-key

Một số multi-key commands Redis Cluster yêu cầu các key thuộc **cùng hash slot**. Hash tags giúp colocate:

~~~text
cart:{tenant-a:user-42}:items
cart:{tenant-a:user-42}:metadata
~~~

Colocation hỗ trợ operation liên quan nhiều key nhưng có thể dồn tải vào cùng một slot nóng. **Khả năng thao tác cùng chỗ và phân phối throughput** là hai mục tiêu cần cân bằng.

## 16. MongoDB: mongos và metadata chunk/range

Trong một MongoDB sharded cluster, ứng dụng thường truy cập qua driver tới **`mongos`**, còn `mongos` dùng shard-key và config metadata để định tuyến.

~~~text
Application / MongoDB driver
          |
        mongos
          |
          +---- Shard A replica set
          +---- Shard B replica set
          +---- Shard C replica set
          |
     Config server metadata
~~~

### 16.1. Khi chunk/range được chuyển

Một phạm vi shard key chuyển từ Shard A sang B trong lúc nhiều `mongos` vẫn hoạt động. Một router còn metadata cũ có thể gửi query tới A và gặp tín hiệu **stale routing/shard version** theo cơ chế của MongoDB.

Router/driver phải cập nhật metadata và gửi lại theo **protocol chính thức**. Ứng dụng không nên tự đặt một bảng `orderId → physical mongod host` để thay thế việc định tuyến của `mongos`.

### 16.2. Không nhầm thiếu shard key với map cũ

Nếu collection shard theo tenant/order, query:

~~~javascript
db.orders.find({ status: "PAID" });
~~~

có thể phải **scatter–gather** tới nhiều shard vì thiếu điều kiện định tuyến. Refresh metadata đúng cũng không làm query này tự thành targeted.

Query mang đủ điều kiện shard-key thích hợp:

~~~javascript
db.orders.find({
  tenantId: "merchant-a",
  orderId: "O900"
});
~~~

thường có cơ hội route tốt hơn, tùy shard-key/index cụ thể.

### 16.3. Routing đúng không thay write concern

Một write có thể được route chính xác nhưng phản hồi không rõ nếu timeout. `writeConcern`, retryable writes, read concern và transaction có bảo đảm riêng. Không giải quyết topology issue bằng cách **tự gửi cùng mutation đến cả shard A và B**.

### 16.4. Metric hữu ích

- Số shard được query chạm tới.
- Stale routing/chunk migrations/resharding.
- Replica set health từng shard.
- Write conflicts, transaction retries, unknown outcomes.
- Latency p95/p99 khi balancer đang chuyển dữ liệu.

## 17. Cassandra và ScyllaDB: token-aware routing

Partition key được hash thành token. Token ranges cùng replication strategy xác định các replicas liên quan. **Token-aware driver** dùng metadata topology để chọn coordinator gần dữ liệu.

~~~text
(tenantId, shopId, dayUtc)
           |
       partition key
           |
         token
           |
      token ring map
           |
    coordinator selected
           |
     replicas contacted
~~~

### 17.1. Driver token map có thể cũ

Khi node join/leave, token ranges/membership có thể thay đổi. Driver giữ thông tin cũ có thể chọn một coordinator không tối ưu.

Khác với Redis Cluster, Cassandra cho phép **coordinator nhận query rồi liên lạc với các replica**. Vì vậy stale token-aware routing không nhất thiết có một lỗi `NOT_OWNER` duy nhất; đôi khi chỉ tạo extra hops, timeout hoặc tail latency.

### 17.2. Cần kiểm tra

- Driver có cập nhật topology/host metadata sau bootstrap/decommission không?
- Token-aware/load-balancing policy có phù hợp data center không?
- Consistency level `ONE`, `QUORUM` hay `LOCAL_QUORUM`?
- Coordinator thực và các replica tham gia là ai?
- Node có đang streaming, repair hoặc gặp compaction pressure không?

### 17.3. Coordinator khác owner duy nhất

Với RF=3, nhiều replica chứa dữ liệu theo replication policy. Coordinator không nhất thiết là một “primary owner” duy nhất. Mỗi consistency level có quy tắc phối hợp đọc/ghi, nên không áp logic “client nhận MOVED rồi đổi slot” của Redis vào Cassandra.

### 17.4. Timeout vẫn có thể là unknown outcome

Khi coordinator hoặc network timeout, request có thể đã được một số replica áp. Chính sách retry cần bám semantics của operation; không tự đổi coordinator rồi gửi lại một side effect không idempotent.

## 18. Elasticsearch/OpenSearch: cluster state và shard routing

Một search index có **primary shards** và **replica shards**. Coordinating node cần biết routing/allocation của shards để gửi operation tới nơi phù hợp.

~~~text
Index + document routing key
            |
       shard number
            |
     cluster state / allocation
            |
    primary / replica location
~~~

### 18.1. Shard relocate và cache topology

Rebalance/failover làm shard chuyển node. Cluster-manager/coordination protocol cập nhật cluster state; các coordinating nodes cần dùng trạng thái phù hợp để tìm shard copy.

Một request có thể gặp transient routing/recovery errors trong lúc relocation. Ứng dụng không nên tự xây `documentId → physical host` thay cho routing của engine.

### 18.2. Custom routing không giống placement map cũ

Nếu index document bằng custom routing key mà lúc GET/UPDATE thiếu hoặc đổi key, document có thể không nằm ở shard được truy cập. Đó là **lỗi truyền routing key**, không chỉ việc cache cluster-state chưa mới.

### 18.3. Concurrency token khác metadata revision

Sequence number/primary term trong những API concurrency có vai trò riêng đối với document mutation và primary lifecycle. Không được đánh đồng chúng tùy ý với một directory revision hoặc placement epoch do ứng dụng tự định nghĩa.

Theo dõi cluster state propagation, relocations, initializing/unassigned shards, retry và latency theo shard.

## 19. DynamoDB: physical routing phần lớn được dịch vụ quản lý

DynamoDB tự quản lý physical partitions và routing bên trong dịch vụ. Ứng dụng chọn partition key/sort key và gọi API qua SDK; không thường có quyền tải bản `physical partition → server` rồi tự redirect như Redis Cluster.

### 19.1. Hot partition khác stale route

Một partition key có write QPS quá lớn có thể gây throttling. Đó là **vấn đề phân phối workload/capacity**, không có nghĩa SDK đang giữ physical partition map cũ.

### 19.2. Directory của ứng dụng vẫn có thể stale

Một SaaS có thể tự ánh xạ:

~~~text
tenant-a -> region-1 / orders-table-a
tenant-b -> region-2 / orders-table-b
~~~

Nếu chuyển tenant sang region/table khác, directory logic do ứng dụng xây dựng vẫn phải xử lý **version, refresh, cutover, fencing/idempotency**. Phải phân biệt directory đó với managed partitioning bên trong DynamoDB.

### 19.3. Read consistency và global tables

Đúng region/endpoint không tự bảo đảm mọi read mạnh hay global transaction. Conditional writes, transactions và global tables có phạm vi/ngữ nghĩa riêng; đánh giá theo API, table/index và cấu hình cụ thể.

## 20. Stale routing khác stale data

**Stale routing:**

~~~text
Router cache: orders-7 -> A / epoch 41
Actual owner: orders-7 -> B / epoch 42
~~~

**Stale data:**

~~~text
Router đúng: replica group RG-7
Primary B: Order O900 version 18
Follower C: Order O900 version 17
~~~

Trường hợp hai là **replication lag/read consistency**, không phải shard map cũ. Refresh placement metadata không làm follower C lập tức có version 18.

| Hiện tượng | Phần cần điều tra |
| --- | --- |
| Route tới old owner | Placement epoch/owner state |
| Read replica thấy value cũ | Replica lag/consistency mode |
| Cache ứng dụng trả status cũ | Cache invalidation/version |
| Driver dùng schema cũ | Schema metadata refresh |
| Quyền truy cập vừa bị thu hồi nhưng vẫn được dùng | Authorization/revocation |

### 20.1. Read-your-writes

Sau write thành công, ứng dụng muốn đọc bản mới có thể:

- Trả dữ liệu/version mới từ kết quả write.
- Đọc đường authority/consistency mạnh phù hợp.
- Mang session/causal context nếu engine hỗ trợ.
- Chờ read model đạt tối thiểu source version đã biết.

Đến đúng shard **chưa đủ** để mọi replica của shard đều phục vụ read-your-writes.

## 21. Security và tenant routing

Nếu caller đã xác thực thuộc `merchant-a` nhưng body gửi `tenantId=merchant-b`, không được dùng input đó để mở quyền truy cập Order của B.

Các tầng cần phân biệt:

1. **Authentication:** Caller là ai?
2. **Authorization:** Được thao tác tenant/entity nào?
3. **Routing:** Entity thuộc shard nào?
4. **Ownership check:** Node này có quyền xử lý operation không?
5. **Business condition:** State/version cho phép mutation không?

### 21.1. Redirect không được biến thành SSRF

Client chỉ kết nối tới endpoints thuộc cluster/namespace tin cậy. Một địa chỉ do redirect chưa được xác minh cung cấp không được trở thành host tùy ý để client nội bộ mở kết nối.

### 21.2. Metadata cần hạn chế quyền truy cập

Directory có thể lộ tenant placement, internal hostnames, region routing. Không xuất toàn bộ metadata qua debug endpoint công khai. Metrics/traces cần được giới hạn thông tin nhạy cảm.

### 21.3. Data residency

Nếu một tenant bị ràng buộc chỉ lưu dữ liệu tại một region, control plane phải kiểm tra placement policy khi chuyển shard. Route đúng tới một node vẫn có thể sai **nghĩa vụ dữ liệu** nếu region không phù hợp.

## 22. Khi metadata authority không reachable

Router cache owner B epoch 42 nhưng control plane tạm không liên lạc được. Có tiếp tục phục vụ không?

**Phụ thuộc operation và giao thức:**

- Nếu B vẫn có thể chứng minh authority/quorum hợp lệ, một số operation tiếp tục mà không cần tra map mỗi request.
- Nếu quyền ghi đã có thể thay đổi nhưng B không có bằng chứng, strong write có thể phải chờ/từ chối.
- Read eventual hoặc immutable data có thể theo chính sách khác.
- Lookup metadata mọi request khiến control plane thành hot path và rủi ro availability.

### 22.1. Notification mất không thay fencing

Old owner A không nhận được thông báo “B đã là owner” vì partition. Nếu A vẫn có thể commit mà không cần điều kiện authority, split ownership vẫn xảy ra.

Do đó, **gửi thông báo không đủ để thu hồi quyền ghi**; cần quorum/lease/fencing với giả định và cách cưỡng chế đúng.

### 22.2. Một metadata authority cũng có thể split-brain

Hai config servers không nên độc lập công bố hai owner có quyền commit cho cùng shard. Nguồn authority cần protocol nhất quán cho việc cập nhật ownership.

## 23. Observability cho stale routing

| Metric | Ý nghĩa |
| --- | --- |
| `route_lookup_total` | Số lần resolve mapping |
| `route_cache_hit_ratio` | Cache có giảm lookup không |
| `route_cache_age_ms` | Tuổi routing entry |
| `metadata_revision_seen` | Router đã thấy revision nào |
| `stale_route_rejection_total` | Request bị old owner từ chối |
| `route_redirect_total` | Số redirects |
| `routing_retry_attempts_total` | Tải tăng bởi retries |
| `routing_retry_exhausted_total` | Hết budget |
| `metadata_refresh_duration_ms` | Chi phí refresh |
| `metadata_refresh_inflight` | Herd/singleflight hiệu quả |
| `redirect_loop_total` | Vòng redirect |
| `ownership_epoch_mismatch_total` | Request mang epoch không hợp lệ |
| `unknown_write_outcome_total` | Timeout cần đối soát |
| `migration_catchup_lag` | Source writes chưa tới new owner |
| `migration_cutover_duration_ms` | Thời gian chuyển quyền |
| `replica_read_staleness` | Data lag, không phải routing lag |

### 23.1. RPC amplification

Giả sử trong một phút:

~~~text
Logical operations:   100.000
Shard RPC attempts:   112.000
~~~

Với cùng định nghĩa attempts:

\[
\text{RPC amplification}=\frac{112000}{100000}=1{,}12
\]

Tức trung bình 1,12 shard RPC attempts cho một logical operation. Con số này chưa chứng minh mọi attempt thêm đều do stale route; nên phân loại retry reason.

### 23.2. Tail latency

Request route stale có thể phải trả:

~~~text
RPC tới old owner
+ NOT_OWNER response
+ metadata refresh
+ RPC tới new owner
~~~

Dù tỷ lệ stale nhỏ, thêm hop/lookup có thể ảnh hưởng p99 đáng kể. Đo theo shard và operation, không chỉ cluster-average.

### 23.3. Metric label cardinality

Không gắn raw `orderId`, `requestId` hoặc mọi `tenantId` vào label của metric time series. Có thể dùng aggregate theo shard, error reason và sampled traces với kiểm soát dữ liệu nhạy cảm.

## 24. Mô phỏng Python: stale route và epoch

Chương trình dùng Python standard library để mô phỏng **một shard, một metadata authority và router cache**. Không có consensus/network thật; đây là ví dụ giáo dục cho luồng reject–refresh–retry.

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    shard: str
    owner: str
    epoch: int


class NotOwnerBeforeApply(Exception):
    pass


class Authority:
    def __init__(self):
        self.route = Route("orders-7", "A", 41)

    def resolve(self):
        return self.route

    def cutover(self, new_owner):
        old = self.route
        self.route = Route(old.shard, new_owner, old.epoch + 1)


class Node:
    def __init__(self, name, authority):
        self.name = name
        self.authority = authority
        self.order_status = "PAID"
        self.applied = {}

    def write(self, epoch, operation_id, new_status):
        route = self.authority.resolve()

        # Chỉ là kiểm tra mô phỏng trên cùng object trong RAM.
        # Hệ thật cần giao thức fencing/commit nghiêm ngặt.
        if route.owner != self.name or route.epoch != epoch:
            raise NotOwnerBeforeApply(
                f"owner={route.owner}, epoch={route.epoch}"
            )

        if operation_id in self.applied:
            return self.applied[operation_id]

        self.order_status = new_status
        result = {"status": "SUCCESS", "owner": self.name}
        self.applied[operation_id] = result
        return result


class Router:
    def __init__(self, authority, nodes):
        self.authority = authority
        self.nodes = nodes
        self.cached = authority.resolve()

    def refresh(self):
        self.cached = self.authority.resolve()

    def write(self, operation_id, new_status):
        for _ in range(3):
            route = self.cached
            try:
                return self.nodes[route.owner].write(
                    route.epoch, operation_id, new_status
                )
            except NotOwnerBeforeApply:
                self.refresh()
        raise RuntimeError("routing retry limit reached")


authority = Authority()
nodes = {
    "A": Node("A", authority),
    "B": Node("B", authority),
}
router = Router(authority, nodes)

print("old cache:", router.cached)

# Demo giả định data đã được copy/catch-up trước cutover.
nodes["B"].order_status = nodes["A"].order_status
authority.cutover("B")

print("new authority:", authority.resolve())
print("result:", router.write("op-810", "SHIPPED"))
print("updated cache:", router.cached)
print("A:", nodes["A"].order_status)
print("B:", nodes["B"].order_status)
~~~

Kết quả dự kiến:

~~~text
old cache: Route(shard='orders-7', owner='A', epoch=41)
new authority: Route(shard='orders-7', owner='B', epoch=42)
result: {'status': 'SUCCESS', 'owner': 'B'}
updated cache: Route(shard='orders-7', owner='B', epoch=42)
A: PAID
B: SHIPPED
~~~

### 24.1. Giới hạn rất quan trọng

- Không có network partition, processes riêng, quorum hoặc WAL.
- Không mô phỏng in-flight write khi cutover.
- Không bảo vệ data/dedup state qua migration thật.
- Không có timeout sau khi commit.
- Các node cùng đọc một authority trong RAM, không thể hiện failure detector/consensus.

Mã cho thấy **router refresh map sau khi old owner từ chối**, không chứng minh thuật toán phân tán production an toàn.

## 25. Kiểm thử migration bằng nhiều client

Chỉ thực hiện fault injection trên môi trường lab riêng; không tự chặn mạng production.

### 25.1. Case A — Redirect trước mutation

1. Khởi tạo O900 v17 tại Shard A, epoch 41.
2. R1 tải map epoch 41.
3. Chuyển dữ liệu sang B, bắt kịp log rồi cutover an toàn.
4. Authority công bố epoch 42, A không còn quyền ghi.
5. R1 gửi PATCH tới A, nhận `NOT_OWNER_BEFORE_APPLY`.
6. R1 refresh và gửi lại cùng logical operation ID tới B.
7. B áp đúng một mutation, trả v18.
8. Read xác minh từ nguồn với consistency phù hợp.

### 25.2. Case B — Timeout sau commit

1. A còn authority, commit `op-900`.
2. Response bị mất.
3. B nhận đủ data và idempotency state rồi cutover.
4. Router timeout, refresh và tra `op-900` ở authority.
5. Trả kết quả cũ hoặc PENDING; **không trừ stock lần thứ hai**.

### 25.3. Case C — Redirect loop

A hướng B/epoch42, B lại hướng A/epoch41. Router phải phát hiện loop, kiểm tra authority và **dừng trong retry budget**, không gửi vô hạn.

### 25.4. Case D — Mixed metadata revision

Cho router nhận các range entries thuộc hai revisions khác nhau. Nó phải tránh dùng snapshot tạo gap/overlap hoặc dựa vào owner checks để không ghi sai, đồng thời refresh snapshot nhất quán.

### 25.5. Case E — Nhiều router cùng stale

Tạo 100 routers epoch41, một router epoch42. Gửi nhiều request sau cutover; đo redirect count, metadata refresh QPS, singleflight hiệu quả, p95/p99 và invariant.

## 26. Assertions cần có

Với Order:

~~~text
One logicalOperationId -> at most one business effect.
No two independent owners commit conflicting writes after cutover.
Acknowledged pre-cutover mutation must not disappear.
Order document version must not regress.
Strong read contract (nếu có) must remain valid.
~~~

Với Inventory:

~~~text
available >= 0
successfulIndependentReservations
  <= initialAvailable + replenishments
retry same requestId does not reserve again
~~~

**Chỉ kiểm tra stock không âm chưa đủ**: hai đơn có thể cùng được xác nhận trong khi stock cuối vẫn bằng 0 do lost update.

### 26.1. Structured trace

~~~json
{
  "logicalOperationId": "op-810",
  "attemptId": "op-810-attempt-1",
  "routingKey": "merchant-a/O900",
  "logicalShardId": "orders-7",
  "routerCachedEpoch": 41,
  "serverCurrentEpoch": 42,
  "routedTo": "node-a",
  "serverOutcome": "NOT_OWNER_BEFORE_APPLY",
  "clientOutcome": "RETRY",
  "invokedAt": "2026-11-14T09:00:01.085Z",
  "completedAt": "2026-11-14T09:00:01.090Z"
}
~~~

Liên kết lần refresh và attempt tới B bằng cùng `logicalOperationId`.

### 26.2. Clock skew

Không chỉ sort timestamp wall-clock của nhiều node rồi coi đó là commit order. Ghi operation IDs, per-shard commit position/term, causal traces, monotonic duration và clock uncertainty khi cần so mốc giữa máy.

## 27. Ma trận chẩn đoán

| Triệu chứng | Có thể do | Điều cần điều tra |
| --- | --- | --- |
| Request đầu sau migration chậm, request sau nhanh | Stale route cache | Redirect, refresh, cache age |
| A ↔ B redirect vòng | Metadata bất đồng | Epoch, authority, loop |
| Đến đúng shard nhưng read cũ | Replica lag | Read mode/source version |
| P99 tăng khi thêm node | Rebalance/extra hops | Migration, refresh |
| Một tenant thường timeout | Hot partition hoặc stale directory | Per-tenant load, mapping |
| Hai bản Order khác nhau sau cutover | Split ownership | Fencing, commit logs |
| Stock giảm hai lần sau timeout | Retry mù/thiếu dedup | Idempotency state |
| Metadata service đột nhiên quá tải | Thundering herd | Singleflight/jitter |
| Search index chưa thấy update | CDC/index lag | Source version, lag |
| Query thiếu shard key chậm | Scatter–gather | Query shape |
| NOT_OWNER dù cache mới | Control/data plane bất đồng | Owner term, authority health |

## 28. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Cache route vĩnh viễn | Sau move vẫn gửi owner cũ | Watch/TTL/error refresh |
| Chỉ dựa vào TTL | Vẫn có race stale | Server-side fencing |
| Dùng hostname làm shard ID | Khó migration và sai mapping | Logical shard độc lập |
| Trộn document version với epoch | Nhầm dữ liệu và vị trí | Token/scope riêng |
| Ghép metadata từ nhiều revisions | Range gap/overlap | Snapshot nhất quán |
| Coi ASK như MOVED | Redis route sai trong migration | ASKING tạm, MOVED refresh |
| Retry mọi timeout | Double business effect | Unknown outcome/idempotency |
| Di chuyển data nhưng không dedup state | Replay áp hai lần | Migrate/reconcile ledger |
| Old owner còn commit sau cutover | Split ownership | Quorum/lease/fencing |
| Dual-write vô điều kiện | Hai bản lệch | Protocol migration chính thức |
| Không giới hạn redirect | Infinite loop | Bounded hops/deadline |
| Mọi thread refresh riêng | Control-plane overload | Singleflight/backoff |
| Trust hostname redirect tùy ý | SSRF/kết nối sai host | Trusted endpoints |
| Trust tenantId trong body | Vượt isolation | Auth + authorization |
| Nhầm replica stale với route stale | Sửa sai nguyên nhân | Replication lag |
| Có secondary index nên luôn target | Query thiếu shard key vẫn fan-out | Access pattern/routing |
| Metadata lookup mỗi read | Hot path chậm | Cache + owner validation |
| Chỉ dùng healthcheck | Không biết node có authority | Shard-level readiness |
| Chỉ xem trạng thái cuối sau heal | Bỏ qua write ack sai trước đó | Thu operation history |

## 29. Bài tập vận dụng

### Bài 1 — Thông tin định tuyến

Một cluster có 8 logical shards và RF=3.

1. Cần dữ kiện gì để route Order theo tenantId/orderId?
2. Vì sao chọn shard khác chọn replica?
3. Placement epoch khác Order.version ở điểm nào?
4. 8 shards với RF3 có phải 24 logical shards không?

### Bài 2 — Router cache epoch cũ

Router giữ `orders-7 → A/41`; authority đã công bố `orders-7 → B/42`.

- Nếu A trả NOT_OWNER_BEFORE_APPLY, router nên làm gì?
- Nếu A timeout, vì sao không kết luận chưa ghi?
- Vì sao B vẫn kiểm tra business condition riêng?
- Cần retry budget và deadline không?

### Bài 3 — Mixed revisions

Rev10: `[a,m)→A` và `[m,z)→B`.

Rev11: `[a,g)→A` và `[g,z)→C`.

Nếu router ghép entry đầu rev10 và entry sau rev11, khoảng nào bị overlap? Thiết kế giải pháp snapshot/delta revision an toàn.

### Bài 4 — TTL race

Router tải epoch41 lúc t=0; authority commit epoch42 lúc t=1 ms; TTL=100 ms.

1. Request t=2 ms có thể route tới đâu?
2. TTL=5 ms có loại bỏ mọi race không?
3. Watch và redirect cải thiện điều gì?
4. Fencing giúp bảo vệ invariant nào?

### Bài 5 — Redis redirect

Giải thích:

~~~text
-MOVED 12182 10.0.0.2:6379
-ASK 12182 10.0.0.2:6379
~~~

Khi nào cập nhật slot map lâu dài? Khi nào gửi `ASKING`? Làm sao chặn redirect loop?

### Bài 6 — MongoDB

Chunk được chuyển Shard A→B trong lúc có nhiều `mongos`. Hãy giải thích:

- Router nào có thể stale?
- Metadata nào cần refresh?
- Query thiếu shard key có thể scatter dù map mới đúng không?
- Ứng dụng có nên tự quản lý `orderId→hostname` không?

### Bài 7 — Cassandra

Node join ring, token map của driver chưa cập nhật.

- Có thể gây extra hop hay không?
- Coordinator khác replica owner thế nào?
- Consistency level nào cần quan sát?
- Nếu timeout, có được gửi lại write tùy ý không?

### Bài 8 — Elasticsearch/OpenSearch

Primary shard relocate giữa hai node.

- Cluster state giúp gì?
- Vì sao custom routing phải nhất quán giữa index và get/update?
- Primary term/seqNo có giống directory revision không?
- Quan sát p99 và shard recovery bằng cách nào?

### Bài 9 — DynamoDB

Một partition key quá nóng trong DynamoDB.

1. Có cần ứng dụng tải internal physical-partition map không?
2. Vì sao throttling không phải bằng chứng stale route?
3. Nếu ứng dụng có directory tenant→region, nó cần giải quyết vấn đề nào?
4. Conditional write và idempotency khác route refresh ở đâu?

### Bài 10 — Timeout đúng lúc cutover

~~~text
T1: A nhận op-10.
T2: A commit, response bị mất.
T3: B trở thành owner sau catch-up.
T4: Router timeout và retry op-10 tới B.
~~~

1. B cần biết gì để không áp op-10 hai lần?
2. Dedup ledger cần chuyển cùng dữ liệu thế nào?
3. Vì sao epoch 42 không tự giải quyết duplicate retry?
4. Nếu outcome không rõ, API nên làm gì?

### Bài 11 — Redirect loop

A nói owner B/42, B nói owner A/41.

- So sánh epoch khi cùng scope thế nào?
- Có được tin một hint endpoint chưa xác thực không?
- Cách phát hiện và dừng loop?
- Nếu authority unavailable, mạnh/yếu có thể có policy khác nhau ra sao?

### Bài 12 — Singleflight

10.000 requests/s cùng gặp stale route.

- Nếu mỗi request refresh riêng, tải metadata tăng thế nào?
- Singleflight giảm lookup bằng cách gì?
- Refresh future lỗi cần được cleanup ra sao?
- Backoff/jitter giúp tránh retry storm thế nào?

### Bài 13 — Tenant isolation

Authenticated tenant=merchant-a nhưng body gửi tenantId=merchant-b.

- Có được dùng field body để cấp quyền không?
- Routing và authorization khác nhau thế nào?
- Redirect hostname có rủi ro gì?
- Data residency ảnh hưởng migration ra sao?

### Bài 14 — Concurrent migration test

100 router caches epoch41, một router epoch42, old owner A còn sống nhưng đã fenced, B là new owner.

Hãy mô tả test 1.000 logical operations, trong đó 100 operations có duplicate retries. Chọn assertions về **số mutation được áp, version không đi lùi, không split ownership**, p99 và metadata refresh QPS.

### Bài 15 — Thiết kế SaaS directory

Hệ có 1.000 tenant nhỏ, 3 tenant rất lớn, 16 shards, RF=3.

1. Chọn routing key và directory granularity.
2. Chọn TTL/watch/error refresh.
3. Thiết kế epoch/fencing khi chuyển tenant/bucket.
4. Bảo vệ in-flight writes và idempotency.
5. Xác định authority khi network partition.
6. Chọn metrics phân biệt stale route, hot shard, stale replica.

## 30. Checklist triển khai và vận hành

~~~mermaid
flowchart TD
    A["Chốt routing key"] --> B["Metadata authority và epoch scope"]
    B --> C["Cache/watch/refresh"]
    C --> D["Server-side ownership validation"]
    D --> E["Redirect có giới hạn"]
    E --> F["Unknown outcome và idempotency"]
    F --> G["Migration/failover tests"]
    G --> H["Metrics và invariant checks"]
~~~

1. Routing key có đủ để xác định shard không?
2. Metadata authority ở đâu, ai được quyền đổi placement?
3. Logical shard có tách khỏi physical hostname không?
4. Epoch, revision và leader term có scope rõ không?
5. Metadata snapshot có được áp theo revision nhất quán không?
6. Cache có TTL, watch, polling hoặc error refresh không?
7. Có singleflight và giới hạn lookup rate không?
8. Old owner có thực sự bị chặn commit sau cutover không?
9. Snapshot/catch-up/cutover có giữ write đã ack không?
10. Temporary/permanent redirect có được phân biệt đúng không?
11. Retry có deadline, budget và loop detection không?
12. Timeout có được ghi UNKNOWN thay vì FAILED chắc chắn không?
13. Dedup ledger/request ID có sống qua migration không?
14. Router có ngăn downgrade epoch từ event cũ không?
15. Endpoint hints có giới hạn trong cluster tin cậy không?
16. Authorization có độc lập với tenant routing không?
17. Read consistency có phù hợp replica đã chọn không?
18. Có fault tests về metadata outage, stale cache và in-flight write không?
19. Có đo p95/p99, stale-route rate, refresh load và business invariant không?

## Kết luận

**Routing metadata** giúp hệ NoSQL phân mảnh xác định dữ liệu thuộc **shard, replica group và authority** nào. Vì topology có thể thay đổi, một client/router giữ bản đồ cũ là tình huống cần được thiết kế trước, không phải điều bất thường chỉ xảy ra khi lỗi nghiêm trọng.

Các nguyên tắc quan trọng:

- **Phân biệt logical shard và physical node**, dùng metadata revision/placement epoch theo scope.
- **Cache để giảm latency** nhưng luôn có cách refresh/redirect khi vị trí thay đổi.
- **TTL ngắn vẫn có cửa sổ stale**; bảo vệ write correctness cần server-side ownership fencing.
- **NOT_OWNER trước mutation khác timeout sau mutation có thể đã commit**. Retry phải dựa trên outcome semantics.
- **Giữ logical operation ID qua các attempt**, bảo vệ dedup state qua migration và có đường đối soát.
- **Không để old/new owner cùng commit độc lập**; cutover cần snapshot, catch-up và giao thức chuyển quyền an toàn.
- **Singleflight, backoff và retry budget** giúp tránh thundering herd khi nhiều client cùng phát hiện map cũ.
- **MOVED khác ASK trong Redis Cluster**; không áp cùng một thuật toán redirect cho mọi database.
- **Stale routing khác stale replica data**: tới đúng shard vẫn có thể đọc bản cũ nếu consistency yếu.
- **Kiểm chứng bằng trace, epoch, commit outcome và invariant nghiệp vụ**, không chỉ healthcheck hoặc trạng thái cuối.

Mục tiêu của một hệ định tuyến tốt không phải bảo đảm không router nào từng dùng map cũ — điều đó khó đạt khi shard thay đổi đồng thời với request. Mục tiêu là **map cũ chỉ tạo thêm redirect/refresh hoặc một lỗi có thể phục hồi, chứ không gây mất write đã xác nhận, ghi trùng ý định hoặc hai owner cùng ghi không kiểm soát**.
