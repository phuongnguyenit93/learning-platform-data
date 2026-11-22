# Failover, lựa chọn bản sao mới và ghi đã được xác nhận

Một cơ sở dữ liệu NoSQL có ba bản sao đang phục vụ bình thường. Client gửi lệnh tạo đơn hàng, nhận phản hồi **thành công**, rồi node đang nhận ghi bất ngờ chết. Hệ thống chọn một bản sao khác để tiếp tục phục vụ. Khi truy vấn lại, đơn hàng vừa tạo không còn xuất hiện.

Đó có thể là một lỗi ứng dụng, nhưng cũng có thể là hậu quả của **hợp đồng ghi và failover được hiểu sai**: node cũ đã xác nhận thao tác trước khi các bản sao đủ điều kiện để được chọn làm leader mới nhận và giữ bền thay đổi đó.

Ngược lại, nếu một hệ dùng giao thức replication có điều kiện **quorum commit** và **bầu leader an toàn**, một thay đổi đã được commit theo protocol phải được bảo toàn sau những lỗi nằm trong failure model được hỗ trợ, ngay cả khi leader cũ chết. Sự khác biệt giữa hai trường hợp không nằm ở câu “có ba replica”, mà nằm ở **ACK được gửi khi nào, bản sao nào thực sự có dữ liệu, một bản ghi được coi là committed khi nào, và điều kiện lựa chọn leader mới là gì**.

Trong chương **Sao chép và quorum** của Database No SQL, bài này sẽ phân tích các cơ chế ấy bằng sơ đồ, timeline, tình huống network partition, quorum, log sequence/term, ứng dụng Java và các phép kiểm thử. Trọng tâm là bảo vệ các **ghi đã được xác nhận** trong quá trình failover, không chỉ làm cho dịch vụ chạy lại.

> **Phạm vi:** Các hệ NoSQL có thể dùng leader–follower, leaderless replication, consensus log, multi-leader replication hoặc những tổ hợp khác. Các ví dụ về MongoDB, Cassandra/ScyllaDB, DynamoDB, Redis, Cosmos DB, Couchbase và consensus KV là minh họa về hướng kiểm tra hợp đồng, không phải cam kết đồng nhất cho mọi phiên bản, cấu hình, cloud tier hoặc topology. Những giới hạn cụ thể phải được xác minh bằng tài liệu chính thức của sản phẩm đang triển khai.

## 1. Failover là gì và điều gì thực sự cần khôi phục?

**Failover** là quá trình chuyển trách nhiệm phục vụ từ thành phần đang hoạt động sang thành phần thay thế khi hệ phát hiện hoặc nghi ngờ thành phần cũ không còn đáp ứng. Trong cơ sở dữ liệu, trách nhiệm đó có thể là:

- Nhận các lệnh ghi cho một partition/shard.
- Phục vụ các phép đọc cần tính mới nhất.
- Điều phối transaction hoặc quorum.
- Quản lý thứ tự log và trạng thái commit.
- Duy trì các session/lease hoặc tuyến truy cập tới nguồn có thẩm quyền.

Một quy trình failover thường có nhiều giai đoạn:

~~~mermaid
flowchart TD
    DET["Phát hiện lỗi / mất heartbeat"] --> DEC["Xác định quorum và quyền bầu chọn"]
    DEC --> CAND["Đánh giá các bản sao ứng viên"]
    CAND --> ELECT["Chọn leader/owner mới"]
    ELECT --> FENCE["Vô hiệu hóa quyền ghi cũ bằng epoch/term"]
    FENCE --> REC["Khôi phục log, commit state và catch-up"]
    REC --> ROUTE["Cập nhật routing / reconnect client"]
    ROUTE --> VERIFY["Kiểm chứng dữ liệu và tiếp tục phục vụ"]
~~~

Từng sản phẩm có thể thực hiện những bước trên theo thứ tự/giao thức khác nhau, và một số mô hình leaderless không thực hiện **bầu leader** kiểu này. Nhưng mọi thiết kế vẫn phải trả lời: **ai có quyền quyết định trạng thái mới và những ghi nào phải được giữ lại?**

### 1.1. Khôi phục dịch vụ không đồng nghĩa khôi phục mọi ghi

Một cluster có thể mở lại API sau vài giây và đạt thời gian downtime thấp, nhưng lại làm mất một số write đã ACK. Đó là hai tính chất khác nhau:

| Mục tiêu | Câu hỏi |
|---|---|
| **Availability / RTO** | Dịch vụ phục vụ lại sau bao lâu? |
| **Durability / RPO** | Có mất write đã ACK hay không, và mất trong phạm vi nào? |
| **Consistency** | Sau failover, các reader có quan sát đúng thứ tự các ghi đã commit không? |
| **Safety** | Có hai nguồn cùng được tin là leader và chấp nhận ghi xung đột không? |
| **Liveness** | Khi đủ điều kiện, cluster có thể bầu thành phần mới và tiếp tục tiến lên không? |

Failover nhanh nhưng mất dữ liệu đã được cam kết là kết quả không phù hợp với workload yêu cầu RPO bằng không theo fault model ấy.

### 1.2. Crash, partition và chậm mạng không giống nhau

Node có thể thực sự mất điện, nhưng cũng có thể chỉ bị chặn mạng hoặc tạm dừng rất lâu. Từ phía các node khác, cả hai đều có thể biểu hiện thành **không nhận heartbeat**. Một timeout không đủ chứng minh node cũ đã ngừng chạy.

Do đó, bầu leader mới phải kèm cơ chế khiến leader cũ **không thể tiếp tục ghi như nguồn có thẩm quyền** nếu nó xuất hiện trở lại.

### 1.3. Failover có thể xảy ra ở phạm vi shard

Một cluster có 1.000 partitions không nhất thiết có một leader chung cho toàn bộ dữ liệu. Shard S1 có thể mất leader trong khi S2 vẫn hoạt động. Cần theo dõi **quorum và quyền sở hữu theo đúng partition hoặc nhóm replication**, không chỉ một trạng thái “database healthy”.

## 2. Các trạng thái khác nhau của một lệnh ghi

Hãy xét lệnh:

~~~json
{
  "commandId": "confirm-order-9001",
  "orderId": "O-100",
  "action": "CONFIRM",
  "expectedVersion": 7
}
~~~

Trong một hệ có replication, lệnh đó có thể đi qua nhiều mốc:

~~~text
Received by server
  -> accepted in process memory
  -> appended to local log
  -> local log synced/durable (theo cấu hình)
  -> replicated to some followers
  -> committed by replication/consensus protocol
  -> applied to state machine / memtable
  -> visible through eligible reads
  -> propagated to remote region/index/cache
~~~

Các bước không phải lúc nào cũng diễn ra theo đúng thứ tự tuyến tính, và không phải hệ nào cũng tách tất cả trạng thái. Một leader có thể áp dụng mutation trong RAM trước khi log sync; follower có thể nhận log nhưng chưa apply. Vì vậy cần phân biệt khái niệm.

| Trạng thái | Ý nghĩa khái quát | Điều **chưa thể** tự kết luận |
|---|---|---|
| **Accepted / received** | Node đã nhận request | Ghi đã bền hoặc được replicate |
| **Appended** | Bản ghi đã được thêm vào log/buffer | Đã fsync, đã quorum commit |
| **Locally durable** | Lưu bền tại một node theo storage contract | Node khác có dữ liệu để failover |
| **Replicated** | Một số node khác đã nhận trạng thái | Số node/độ bền đủ cho failover an toàn |
| **Quorum committed** | Đạt quy tắc commit của giao thức quorum | Mọi follower đã apply hoặc mọi vùng đã có |
| **Applied** | State machine/data model của node đã phản ánh log | Mọi replica đã theo kịp |
| **Client ACK** | Client nhận phản hồi thành công | Mốc mạnh đến đâu phụ thuộc API, write concern và config |

**ACK** là lời hứa của hệ đối với client tại một thời điểm. Nó không tự là một bước kỹ thuật thống nhất giữa mọi NoSQL.

### 2.1. “ACK đã ghi” khác “ACK đã commit”

Một hệ có thể trả ACK sau khi leader nhận thay đổi; hệ khác đợi majority commit. Hai kiểu trả lời đều có thể có HTTP status 200 hoặc gRPC OK, nhưng mức bảo vệ khác nhau.

### 2.2. “Đã replicate” khác “đã lưu bền”

Một follower có thể ACK rằng đã nhận bản ghi trong RAM hoặc OS cache. Nếu nó mất điện, bản ghi đó có thể mất, tùy protocol và storage. Không suy rằng **hai replica đã nhận** đồng nghĩa **hai bản sao bền trên hai thiết bị độc lập**.

### 2.3. “Đã commit” khác “đã apply”

Một follower có thể giữ log committed nhưng state machine chưa kịp apply. Một local read trực tiếp từ follower có thể cũ nếu API cho phép; strong read có thể phải chờ apply hoặc theo một read protocol khác.

### 2.4. “Đã apply” khác “index/search đã cập nhật”

Một ghi Order đã committed và applied trong source database có thể chưa tới search index, cache hay downstream projection. Không được xem độ trễ projection là bằng chứng failover làm mất dữ liệu nguồn.

## 3. Ví dụ đầu tiên: ghi đã ACK vẫn có thể mất

Cluster có ba data-bearing replicas A, B, C. A là leader nhận ghi. Cấu hình minh họa: **leader trả ACK ngay sau khi local write được chấp nhận**, không đợi follower xác nhận.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant A as Leader A
    participant B as Follower B
    participant C as Follower C
    U->>A: Create Order O-100
    A->>A: Local append/write
    A-->>U: ACK success (leader-only)
    Note over A,C: Chưa replicate O-100 tới B/C
    A-xA: Crash / mất vĩnh viễn
    B->>C: Bầu/chọn node có dữ liệu cũ
    Note over B,C: O-100 không nằm ở bản sao tiếp tục phục vụ
~~~

Timeline:

~~~text
T0: A, B, C đều có Order version 7.
T1: A nhận update version 8.
T2: A trả ACK theo cấu hình leader-only.
T3: A chết vĩnh viễn trước khi gửi update đến B/C.
T4: B hoặc C được chọn phục vụ.
T5: Client đọc lại và chỉ thấy version 7.
~~~

Nếu fault model cho phép mất node A vĩnh viễn và hợp đồng chỉ hứa ACK local, đây có thể là **rủi ro đúng theo cấu hình**, không nhất thiết là vi phạm protocol. Vấn đề nằm ở việc ứng dụng đã hiểu ACK local như ACK bền sau failover.

### 3.1. Nếu A chỉ mất tiến trình rồi khởi động lại?

Trường hợp này khác mất toàn bộ node. Nếu log của A đã bền, A có thể vẫn giữ write version 8. Nhưng trong quá trình cluster chọn leader mới, phiên bản ấy **chưa chắc đã được commit toàn cluster**; hệ có thể phải rollback/truncate entry chưa committed theo giao thức hoặc hòa giải trạng thái.

Do đó “local durable” chưa đủ để kết luận write sẽ sống sót **sau một failover sang replica khác**.

### 3.2. Nếu A phục hồi sau khi B đã thành leader?

A phải nhận ra quyền leader cũ đã hết, catch up với nguồn mới và xử lý những bản ghi riêng chưa được commit. Nếu cho A tiếp tục tự nhận ghi từ client, có nguy cơ split brain.

### 3.3. Điều gì cần hỏi về ACK?

Không chỉ “writeConcern có bật không?” mà là:

~~~text
ACK after:
    one node accepted?
    local journal/fsync?
    multiple replicas?
    majority quorum?
    replicas have durable log?
    cluster consensus commit?
    remote region persistence?
~~~

Mỗi mốc cần được ghép với loại lỗi mà sản phẩm cam kết chịu được.

## 4. Majority quorum và vì sao bản sao mới phải đủ điều kiện

Với \(N\) voting members trong một consensus group ổn định, một majority thường là:

\[
Q=\left\lfloor\frac{N}{2}\right\rfloor+1.
\]

Ví dụ:

| N voting members | Majority quorum Q | Số voting members có thể thiếu mà vẫn còn quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

Đây là **quorum cho tập voting members của một mô hình majority thông thường**. Nếu dùng witnesses, arbiters, members không giữ dữ liệu, flexible quorum hoặc cấu hình đặc biệt, cần đọc cách commit và election thực sự sử dụng các thành viên ấy.

### 4.1. Tính chất giao nhau của majority

Với N=3, mọi tập majority hai node đều giao nhau:

~~~text
Q1 = {A, B}
Q2 = {B, C}
Intersection = {B}
~~~

Với N=5, hai quorum ba node cũng giao nhau:

~~~text
Q1 = {A, B, C}
Q2 = {C, D, E}
Intersection = {C}
~~~

Đó là nền tảng quan trọng: một tập commit và một tập election cùng nằm trong cấu hình quorum tương thích **không thể hoàn toàn tách rời**.

### 4.2. Quorum intersection là cần nhưng chưa đủ

Không thể kết luận chỉ nhờ có một node giao nhau rằng bản sao được bầu leader chắc chắn giữ toàn bộ committed entries. Giao thức bầu chọn còn cần **điều kiện về độ mới của log, term/epoch, commit rules và cách thay đổi membership**.

Một node nằm trong quorum có dữ liệu mới nhất nhưng lại bỏ phiếu cho một ứng viên thiếu committed log, nếu protocol cho phép như vậy, vẫn có thể mất dữ liệu. Consensus protocol an toàn phải ngăn tình huống ấy.

### 4.3. Điều kiện của lời hứa majority

Một phát biểu đúng hơn:

> Nếu bản ghi được commit theo một consensus protocol an toàn, bản ghi và vote/term được lưu bền theo điều kiện của protocol, quorum và quy tắc election/reconfiguration được tuân thủ, thì một leader được bầu hợp lệ sau đó không được làm mất bản ghi committed ấy trong failure model đã công bố.

Đây là phát biểu **có điều kiện**, không phải “có ba server nên không mất dữ liệu”.

### 4.4. Quorum read/write kiểu leaderless là vấn đề liên quan nhưng khác

Trong một số hệ leaderless, ta dùng R/W counts và quy tắc reconcile; không có một bước election leader duy nhất như Raft. Quorum overlap có thể giúp tăng khả năng đọc phiên bản mới, nhưng tự nó không bảo đảm linearizability dưới mọi concurrency, clock skew và sloppy quorum. Phần đó sẽ được phân tích riêng.

## 5. Ví dụ thứ hai: majority commit bảo vệ ghi qua failover

Giả sử một consensus group A, B, C có leader A. Protocol yêu cầu majority 2/3 cho commit và chỉ cho bầu một leader đủ điều kiện theo log/term.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant A as Leader A
    participant B as Follower B
    participant C as Follower C
    U->>A: Write Order v8
    A->>A: Append log entry E8
    A->>B: Replicate E8
    B-->>A: ACK log per protocol
    Note over A,B: Majority A+B đủ điều kiện commit
    A-->>U: Success after commit
    A-xA: Leader fails
    B->>C: Election theo term + log eligibility
    Note over B,C: Leader mới không được loại bỏ committed E8
~~~

Timeline:

~~~text
T0: A/B/C có committed log tới index 41.
T1: A tạo entry E8 ở index 42.
T2: A và B giữ entry E8 theo protocol.
T3: E8 đạt điều kiện committed của consensus.
T4: Client nhận ACK.
T5: A chết.
T6: Một leader hợp lệ được chọn theo quorum/election rules.
T7: Entry E8 vẫn là một phần lịch sử committed.
~~~

Điều kiện **leader mới không được loại bỏ E8** không chỉ đến từ việc có hai bản sao. Nó cần giao thức đảm bảo **leader completeness** hoặc tính chất tương đương.

### 5.1. Nếu C không có E8, C có thể trở thành leader không?

Không thể trả lời bằng quy tắc “node nào sống thì làm leader”. Trong một giao thức kiểu Raft với election up-to-date rules, ứng viên có log thiếu committed entry không thể giành majority hợp lệ theo những điều kiện an toàn của protocol; node có thể bắt kịp rồi mới tham gia phù hợp.

Không được đơn giản lấy “latest timestamp”, “số bản ghi nhiều nhất” hoặc “độ trễ ping thấp nhất” để bầu leader khi đó không phải quy tắc của giao thức.

### 5.2. Cập nhật trạng thái máy sau commit có thể chậm hơn

Follower B đã có committed log nhưng chưa apply vào bảng dữ liệu. Trong quá trình khôi phục, B có thể phải apply log/catch up trước khi phục vụ một strong read cho version 8.

### 5.3. Nếu client timeout ngay trước ACK?

E8 có thể đã commit nhưng phản hồi chưa đến client. Từ phía client, outcome là **không xác định**. Retry command một lần nữa mà không idempotency có thể tạo hiệu ứng nghiệp vụ trùng, dù consensus vẫn giữ an toàn log.

## 6. Các điều kiện bầu bản sao mới

Trong mô hình leader–follower, nhiều lựa chọn bầu leader cần cùng được xem xét:

1. **Eligibility:** node có phải voting/data-bearing member đủ điều kiện trong config hiện hành?
2. **Connectivity:** node có thể liên lạc với quorum và được bỏ phiếu hợp lệ?
3. **Log freshness:** log có đủ mới theo tiêu chí protocol, không thiếu committed history?
4. **Epoch/term:** nhiệm kỳ mới có thứ tự rõ và được lưu/kiểm tra đúng?
5. **Durability:** những entries cần thiết có đạt mốc bền theo protocol?
6. **Role/fencing:** leader cũ có bị loại quyền xử lý ghi sau khi term thay đổi?
7. **Readiness:** node có hoàn tất recovery/catch-up cần thiết trước khi phục vụ các API có bảo đảm mạnh?
8. **Topology constraints:** region, availability zone, priority, data placement và policy của sản phẩm có cho node làm leader không?

Không phải mọi hệ gọi những trường này bằng cùng một tên, nhưng các câu hỏi là thiết yếu.

### 6.1. “Replica mới nhất” có nhiều nghĩa

~~~text
Replica A:
    last appended index = 108
    committed index = 105
    applied index = 104

Replica B:
    last appended index = 107
    committed index = 105
    applied index = 105

Replica C:
    last appended index = 105
    committed index = 105
    applied index = 105
~~~

Không thể chọn A chỉ vì last appended lớn nhất: entries 106–108 có thể **chưa commit**, thuộc một leader cũ và có thể bị thay thế theo protocol. Cũng không chọn C chỉ vì applied index cao nếu điều đó bỏ qua term/log ordering.

### 6.2. Entry chưa commit có thể bị loại

Consensus log thường phân biệt **committed prefix** và phần log chưa commit. Một ứng viên mới có thể có log hợp lệ nhưng không chứa mọi entry chưa commit của leader cũ. Những entry chưa commit có thể được ghi đè/truncate theo protocol, miễn không làm mất lịch sử đã committed.

Vì vậy client không được coi “leader đã append entry” là “entry chắc chắn sẽ sống sau failover” nếu API chưa xác nhận committed.

### 6.3. Chọn theo độ trễ mạng là chưa đủ

Một replica gần client nhưng chậm replication không nên tự được nâng lên làm leader nếu thiếu điều kiện an toàn. Một số sản phẩm cho cấu hình priority cho node ứng viên, nhưng priority không được phép phá invariant của protocol.

### 6.4. Data-bearing replica và voting-only member

Một witness/arbiter có thể giúp quá trình election hoặc xác định quorum theo thiết kế, nhưng **không nhất thiết giữ bản sao dữ liệu đầy đủ**. Đếm số phiếu và đếm số bản sao dữ liệu bền là hai việc khác. Cần xác minh write concern và khả năng lưu sống sót sau lỗi, nhất là khi một nhóm có witness.

## 7. Term, epoch và fencing: ngăn leader cũ ghi tiếp

Giả sử leader A bị cô lập mạng nhưng tiến trình vẫn chạy. B và C không thấy A nên bầu B. Client cũ vẫn còn kết nối trực tiếp với A.

Nếu A tiếp tục nhận ghi như leader, có thể xuất hiện:

~~~text
Leader A (old):
    Order O-100 -> CONFIRMED

Leader B (new):
    Order O-100 -> CANCELED
~~~

Đây là nguy cơ **split brain**. Một giải pháp cần:

- Gắn quyền leader với **term/epoch/generation** tăng dần.
- Node/server nhận write kiểm tra epoch hiện hành.
- Leader cũ không đủ quorum không được commit các thao tác yêu cầu quorum.
- Khi term mới xuất hiện, các message/lease của term cũ bị từ chối.
- Client phải cập nhật routing và không được coi response từ nguồn cũ là successful commit nếu không đạt protocol.

### 7.1. Fencing token

Trong một workflow dùng lease:

~~~text
Owner A obtains fenceToken = 41.
Lease expires or is superseded.
Owner B obtains fenceToken = 42.

Downstream storage must reject operations
with fenceToken < 42.
~~~

Nếu hệ ngoài không kiểm tra fencing token, A có thể tiếp tục ghi do chưa biết lease đã hết. Chỉ kiểm tra lease trong ứng dụng **không đủ** khi tiến trình bị pause rất lâu hoặc network delay.

### 7.2. Lease dựa trên thời gian cần giả định rõ

Leader lease có thể giảm chi phí một số read, nhưng an toàn phụ thuộc vào protocol và giả định clock/time bounds. Không tự xây hệ election bằng `now() < leaseExpiresAt` trên các máy có đồng hồ không đồng bộ rồi suy ra có một leader duy nhất.

### 7.3. Epoch không chỉ là metadata hiển thị

Một số hệ đặt epoch/term trong log record hoặc replication messages. Việc so sánh epoch phải thực hiện trên **đường ghi thật**, không chỉ ghi vào log ứng dụng và hy vọng writer cũ tự dừng.

### 7.4. Zombie writers

Một worker cũ bị pause hoặc partition có thể phục hồi sau hàng phút và cố ghi bằng quyền cũ. Test failover phải kiểm tra khả năng **từ chối write từ zombie leader/worker**, không chỉ kiểm tra leader mới online.

## 8. Nhiều bước trong failover: election, catch-up, apply và mở traffic

Một trình tự khái niệm:

~~~text
1. Detect leader unresponsive.
2. Start new election term.
3. Gather votes under quorum + log freshness rules.
4. Establish new leader, fence old term.
5. Reconcile/truncate uncommitted log entries as specified.
6. Commit/apply required entries.
7. Update client routing and session state.
8. Resume reads/writes at supported consistency levels.
9. Catch up remaining followers.
10. Confirm cluster health and durability coverage.
~~~

Những bước này có thể chồng lấn, và một số API có thể phục vụ sớm hơn những API khác. Nhưng không được mở **strong reads** từ một node chưa đáp ứng điều kiện freshness tương ứng.

### 8.1. Leader mới chưa chắc có cache nóng

Dữ liệu có thể đúng nhưng cache và index cục bộ chưa được làm ấm, khiến p99 latency tăng sau failover. Tính đúng đắn và hiệu năng hồi phục là hai mục tiêu phải đo riêng.

### 8.2. Routing đến leader cũ

Client/connection pool có thể giữ địa chỉ cũ. Khi nhận lỗi not-leader/term mismatch, driver cần refresh topology và retry theo semantics của API. Nếu ghi có outcome chưa rõ, retry phải giữ `commandId` để tránh duplicate.

### 8.3. Follower catch-up và log truncation

Một follower bị trễ có thể cần replay log hoặc nhận snapshot mới nếu đoạn log cần thiết đã bị retention loại bỏ. Điều đó ảnh hưởng **thời gian hồi phục redundancy**, không nhất thiết đồng nghĩa dữ liệu committed của cluster đã mất.

### 8.4. Khi không đủ quorum

Một consensus group có thể phải từ chối hoặc chờ những thao tác cần quorum, ưu tiên safety. Một API trả stale local read có thể vẫn hoạt động nếu contract cho phép, nhưng không được hiển thị nó như một read mạnh.

## 9. Quorum election và quorum commit không được trộn lẫn

Một hệ có thể có:

- **Voting quorum:** cần để chọn leader hoặc thay đổi membership.
- **Write/commit quorum:** cần để ACK/commit dữ liệu.
- **Read quorum:** cần cho một số chế độ đọc.
- **Data-bearing quorum:** những bản sao thực sự lưu dữ liệu.
- **Regional quorum:** chỉ xét members trong một datacenter/region.

Các tập quorum này có thể có cấu hình và mục đích khác nhau.

### 9.1. Một ví dụ có arbiter

Giả sử hai data nodes A, B và một arbiter C. C có thể bỏ phiếu nhưng không lưu Order data. Nếu A đã ACK một write local trước khi B nhận, rồi A mất vĩnh viễn, việc B+C đủ phiếu bầu leader **không làm write tự xuất hiện trên B**.

Vì vậy **election majority không thay thế replicated durable majority** khi mục tiêu là giữ những ghi đã ACK.

### 9.2. Không dùng hai số majority mà không xem giao nhau

Hai majority trên **cấu hình membership khác nhau** chưa chắc giao nhau nếu reconfiguration được thực hiện tùy tiện. Một consensus protocol an toàn có bước chuyển cấu hình thích hợp (ví dụ cơ chế joint consensus hoặc quy tắc tương đương) để bảo vệ những committed entries khi thêm/bớt members.

### 9.3. Member đã chết nhưng còn phiếu?

Một member mất hẳn vẫn có thể thuộc cấu hình voting hiện hành cho tới khi có thao tác reconfiguration hợp lệ. Không tự sửa file cấu hình trên mỗi node để “bỏ node chết” nếu điều đó có thể tạo hai cấu hình quorum đối nghịch.

### 9.4. Capacity không tỉ lệ tuyến tính với số replicas

Tăng từ ba lên năm replicas có thể tăng khả năng chịu lỗi voting theo điều kiện, nhưng cũng thêm network, disk, election/catch-up overhead. Nếu cả năm cùng chung một availability zone hoặc power domain, khả năng chịu lỗi thực tế vẫn hạn chế.

## 10. Raft-style replicated log: committed prefix và leader completeness

Một hệ consensus như Raft minh họa rõ mối liên hệ giữa log và leader election:

~~~text
Log entry:
    index
    term
    command

Leader:
    appends entries
    replicates to followers
    advances commit index under protocol rules

Followers:
    persist log/term/vote as required
    apply committed entries in order
~~~

### 10.1. Index không tự đủ

Hai replicas có thể cùng lastIndex=100 nhưng entry ở index 100 thuộc term khác hoặc có dữ liệu khác do phần đuôi chưa commit. Việc so sánh log up-to-date trong Raft phải tính **last log term và index** theo protocol, không chỉ số record.

### 10.2. Raft và commit các entry từ term cũ

Trong Raft, quy tắc tiến commit index có nuance với entries từ term trước; leader dùng các điều kiện của protocol, đặc biệt chú ý việc commit entry trong current term để suy ra những entry trước đó cũng committed. Không đơn giản tuyên bố **mọi entry xuất hiện ở majority đều được commit ngay** bất kể term và quy tắc cụ thể.

### 10.3. Leader completeness

Một property cốt lõi: khi entry đã committed, leader ở các term tương lai phải chứa entry đó, theo các giả định và quy tắc bầu chọn/commit của protocol. Đây là mối nối giữa **ACK commit** và **chọn leader mới an toàn**.

### 10.4. State machine safety

Nếu hai state machines đã apply command tại cùng log index, chúng không được apply các command khác nhau tại vị trí ấy trong một history hợp lệ. Thứ tự apply các committed entries phải được bảo vệ; nếu không, các bản sao có thể cùng ACK nhưng kết quả nghiệp vụ phân kỳ.

### 10.5. Raft không tự giải quyết external side effects

Một log command `CapturePayment` được committed một lần không có nghĩa payment gateway đã nhận chính xác một HTTP call. Retry state machine/worker có thể gọi gateway nhiều lần. Cần application-level idempotency và workflow bền.

## 11. Leaderless replication: không có một leader mới để bầu

Không phải mọi NoSQL sao chép bằng leader–follower. Trong các hệ **leaderless/Dynamo-style**, nhiều replica có thể nhận write qua coordinator, còn hệ dùng consistency level, version metadata, conflict resolution và repair.

~~~mermaid
flowchart LR
    U["Client"] --> CO["Coordinator"]
    CO --> A["Replica A"]
    CO --> B["Replica B"]
    CO --> C["Replica C"]
~~~

Nếu một replica chết, coordinator khác có thể tiếp tục phục vụ theo cấu hình. “Failover” khi đó có thể là **chuyển coordinator, thay thế replica, hinted handoff, streaming repair hoặc thay đổi membership**, không phải bầu một primary duy nhất.

### 11.1. N, R và W

Trong mô hình giản lược:

- N là số replica của key.
- R là số phản hồi cần cho read.
- W là số ACK cần cho write.

Nếu membership cố định:

\[
R+W>N
\]

thì tập read và write giao nhau về mặt tập hợp.

Ví dụ N=3, R=2, W=2: hai tập quorum bất kỳ cùng preference list có ít nhất một node chung.

### 11.2. Overlap không tự là linearizable read

Còn nhiều yếu tố:

- Timestamp và last-write-wins có thể bị clock skew.
- Concurrent writes có thể tạo conflict hoặc last-write-wins mất một cập nhật.
- Hinted handoff/sloppy quorum có thể làm các tập vật lý không đúng preference list.
- Repair và reconciliation có thể cần thời gian.
- Replica ACK có thể chưa durable.
- Thay đổi membership có thể làm các quorum trước/sau không giao nhau như giả định.

Vì vậy không gộp **leaderless QUORUM** và **consensus committed log** thành một công thức bảo đảm giống nhau.

### 11.3. Phiên bản mới và xung đột

Một replica có timestamp lớn nhất chưa chắc là phiên bản đúng theo business semantics. Với đơn hàng `CONFIRMED` và `CANCELED` ghi cạnh tranh, last-write-wins không tự đảm bảo state transition hợp lệ. Cần conditional mutation, ownership hoặc conflict-aware design.

### 11.4. Read repair không quay ngược được lời hứa sai

Repair có thể đưa replicas về cùng state, nhưng nếu client đã được ACK về hai reservation trái ngược, hội tụ state cuối không tự bù được việc đã hứa hàng vượt tồn.

## 12. Điểm ACK phải phù hợp với loại lỗi muốn chịu

| ACK / cam kết (khái niệm) | Khi leader process crash | Khi host mất điện | Khi leader mất vĩnh viễn | Khi mất cả region |
|---|---|---|---|---|
| **Memory-only local ACK** | Có nguy cơ mất | Có nguy cơ mất | Có nguy cơ mất | Không được đảm bảo |
| **Local durable ACK** | Có thể phục hồi local | Tùy storage contract | Có thể mất nếu chưa replicate | Không được đảm bảo |
| **Replica ACK không rõ sync** | Phụ thuộc ACK semantics | Phụ thuộc volatile buffers | Phụ thuộc bản sao còn sống | Không được suy ra |
| **Quorum committed + durability đúng protocol** | Thường mạnh hơn theo fault model | Cần đủ durable nodes | Bảo vệ theo failure threshold đã công bố | Chỉ nếu protocol/failure domain bao phủ |
| **Cross-region durable/consensus commit** | Theo contract | Theo contract | Theo contract | Phụ thuộc đủ vùng độc lập và failure threshold |

Bảng trên diễn tả **điều kiện cần phân tích**, không phải guarantee chung của một tên sản phẩm. Ví dụ “majority acknowledged” có thể có những yêu cầu durability khác nhau theo API và storage options.

### 12.1. RPO = 0 cần ghi rõ đối với lỗi nào

“RPO bằng 0 khi một node leader chết vĩnh viễn trong cluster có quorum còn sống” là phát biểu cụ thể hơn “không bao giờ mất dữ liệu”.

Nếu toàn bộ availability zone, region, storage domain hoặc tất cả replicas cùng hỏng, các giả định có thể không còn thỏa.

### 12.2. RTO không được đánh đổi bằng lời nói

Một hệ có thể cần vài giây để election, thêm thời gian để catch up, warm-up và reconnect. RTO mục tiêu phải đo tới **thời điểm API nghiệp vụ hoạt động đúng**, không chỉ lúc process có status RUNNING.

### 12.3. Phân biệt loss window và visibility lag

Một entry đã được quorum committed nhưng follower chưa apply có thể làm follower read yếu thấy cũ. Đây là **visibility lag**, không nhất thiết **data loss**. Cần so sánh committed history tại nguồn trước khi kết luận mất write.

## 13. Các tình huống gây mất ghi đã ACK

### 13.1. Leader-only ACK trước replication

Leader xác nhận rồi chết vĩnh viễn. Replica được chọn không có write. Đây là ví dụ điển hình của **acknowledged-but-not-replicated**.

### 13.2. Replica ACK trong RAM, nhiều node mất điện

ACK từ nhiều node không đủ nếu storage semantics chỉ giữ trong volatile memory/cache và fault model là mất điện đồng thời. Durability cần được định nghĩa theo tầng lưu trữ.

### 13.3. Multi-region asynchronous replication

Region A ACK local, nhưng B chưa nhận. A mất cả region; failover sang B có thể mất write mới nhất. Đây có thể là RPO được công bố của chế độ async, không phải bảo đảm “zero data loss”.

### 13.4. Unclean leader election

Trong một số log-based systems, để ưu tiên availability, operator có thể cho phép nâng một replica thiếu committed/acknowledged history lên làm leader theo một chế độ không an toàn hoặc cấu hình đặc biệt. Cần hiểu cách hệ định nghĩa committed và cảnh báo về data loss.

Không được áp thuật ngữ `unclean leader election` như một tùy chọn phổ quát của mọi NoSQL.

### 13.5. Sai quy tắc reconfiguration

Nếu thay đổi membership khiến quorum mới không giao với quorum đã commit và không có thủ tục an toàn chuyển cấu hình, ghi cũ có thể bị loại khi bầu leader mới.

### 13.6. Fencing không hiệu lực

Leader cũ phục hồi và tiếp tục xử lý write, trả ACK ngoài quyền hợp lệ. Hai lịch sử có thể phân kỳ, khiến việc chọn state sau failover mất hoặc ghi đè kết quả đã được khách nhìn thấy.

### 13.7. Storage corruption hoặc thao tác vận hành sai

Quorum không thể chữa mọi dạng lỗi: xóa thủ công log, khôi phục snapshot sai, corruption trên nhiều replica hoặc backup không nhất quán có thể làm mất dữ liệu. Cần checksum, backup ở failure domain phù hợp và restore drills.

## 14. Chọn leader mới trong một cluster nhiều region

Giả sử có năm voting replicas:

~~~text
Region A: A1, A2, A3
Region B: B1, B2

Majority vote quorum: 3/5.
~~~

Nếu Region A mất hoàn toàn, B còn 2/5 và không đủ majority trong mô hình này. Cluster có thể phải **không bầu leader mới** dù B còn hai node khỏe và đã nhận nhiều dữ liệu.

### 14.1. Đây có phải “lỗi thiết kế”?

Không nhất thiết. Bố trí 3+2 đã đặt nhiều quyền voting trong một failure domain; cluster không được bảo đảm sống sót khi **mất toàn bộ Region A** trong cấu hình ấy. Đó là vấn đề topology và failure tolerance phải được quyết định trước.

### 14.2. Quorum địa lý cân bằng

Một hệ có thể đặt replicas ở ba vùng độc lập hoặc dùng phương án witness phù hợp để bảo vệ election, nhưng phải đánh giá **data durability**, latency cross-region, connectivity và chính sách leader placement. Thêm witness không tự tạo bản sao Order ở vùng thứ ba.

### 14.3. Regional write ACK vs global durability

Một write ACK tại Region A có thể đã bền trên nhiều AZ của A nhưng chưa tới Region B. Khi A mất toàn bộ, khả năng phục hồi ở B phụ thuộc cross-region replication/commit mode. Không suy từ “multi-AZ replicated” rằng đã đạt “multi-region RPO=0”.

### 14.4. Kết nối mạng giữa các regions bị chia

Nếu cả A và B được phép nhận ghi như hai nguồn độc lập trong partition, cần conflict resolution hoặc quota/ownership để giữ invariant. Nếu muốn single-copy strong consistency, thường phải hạn chế write availability ở phía không có authority/quorum.

### 14.5. Failback không chỉ là đảo DNS

Khi Region A hồi phục, cần xác định history có thẩm quyền, replay/catch-up, fencing, session tokens, version boundaries và test state. Chuyển write traffic về A trước khi đồng bộ có thể tạo lại split brain hoặc hồi sinh state cũ.

## 15. Phân biệt failover leader với failover read routing

Không phải mọi lần đổi đích truy cập đều là bầu leader.

~~~text
Read routing failover:
    A follower không trả lời -> đọc follower khác.

Leader failover:
    quyền nhận write chuyển từ A sang B.

Region failover:
    traffic chuyển giữa failure domains/replication groups.

Service failover:
    ứng dụng chuyển sang một database cluster khác.
~~~

### 15.1. Read routing có thể ảnh hưởng session consistency

Client vừa ghi version 8 ở leader, sau đó driver chuyển đọc sang follower chỉ có version 7. Nếu read mode eventual cho phép, đây là stale read; nếu session read-your-writes được yêu cầu, client cần mang session context hoặc dùng một read path đáp ứng được.

### 15.2. Cross-cluster failover khó hơn

Hai cluster độc lập với replication async không mặc nhiên cùng election quorum. Chuyển DNS có thể làm API phục vụ lại nhưng thiếu write gần đây. Phải có RPO contract và cơ chế đối soát.

### 15.3. Connection routing phải không che lỗi

Một driver có thể tự retry khi nhận `NOT_LEADER`. Nhưng nếu request cũ có thể đã commit, retry ở leader mới phải dùng idempotency hoặc API có retry semantics an toàn. Không xem mọi `connection reset` đều chắc chắn không ghi.

## 16. Client timeout lúc failover: outcome không xác định

Ví dụ:

~~~text
T0: Client gửi ConfirmOrder(commandId=C-100).
T1: Leader A nhận write.
T2: Majority commits.
T3: Leader A chết trước khi response về client.
T4: B được bầu leader.
T5: Client nhận timeout.
~~~

Ở T5, client không biết:

- Write chưa đến server?
- Write đến nhưng chưa commit?
- Write đã committed rồi ACK bị mất?

**Timeout không phải bằng chứng rollback.**

### 16.1. Tại sao retry có thể gây hại?

Nếu gửi lại lệnh `INCREMENT quantity` bằng một command mới, hệ có thể áp dụng lần thứ hai dù lần đầu đã commit. Điều này xảy ra cả ở database có consensus hoàn toàn đúng.

### 16.2. Stable business command ID

~~~json
{
  "commandId": "reserve-SKU-A-7281",
  "sku": "SKU-A",
  "quantity": 2,
  "orderId": "O-100"
}
~~~

Khi retry, giữ nguyên `commandId`, `orderId` và immutable intent. Trong nguồn dữ liệu có thẩm quyền, kết quả của command cần được ghi hoặc nhận diện nguyên tử cùng mutation phù hợp.

### 16.3. Đối soát sau failover

Một luồng khái niệm:

~~~text
on write timeout:
    query committed outcome by commandId
    using an authoritative read path after failover

    if committed:
        return previous result

    if confirmed aborted/not applied:
        retry according to contract with same commandId

    if still unknown:
        return PENDING/UNKNOWN
        schedule a durable reconciliation workflow
~~~

Không dùng một eventual index “không thấy commandId” làm bằng chứng chắc chắn write chưa commit. Trên hệ có replication lag, read ở wrong replica có thể trả absence tạm thời.

### 16.4. Retry transaction body vs retry commit

Một số transaction APIs phân biệt **known abort có thể chạy lại toàn UoW** và **unknown commit result cần tiếp tục protocol commit hoặc đối soát**. Không gộp hai loại vào một catch-all retry.

## 17. Mẫu Java: hợp đồng ACK và failover không rõ kết quả

Mã sau là **abstraction phục vụ thiết kế**, không phải SDK của sản phẩm cụ thể:

~~~java
public enum AcknowledgmentLevel {
    LOCAL_ACCEPTED,
    LOCAL_DURABLE,
    REPLICATED_COMMITTED
}

public record ConfirmCommand(
    String commandId,
    String tenantId,
    String orderId,
    long expectedVersion
) {}

public record WriteReceipt(
    String commandId,
    String orderId,
    long newVersion,
    AcknowledgmentLevel achieved,
    String topologyEpoch
) {}

public sealed interface ConfirmOutcome
    permits ConfirmOutcome.Committed,
            ConfirmOutcome.Rejected,
            ConfirmOutcome.Pending {

    record Committed(WriteReceipt receipt)
        implements ConfirmOutcome {}

    record Rejected(String reason)
        implements ConfirmOutcome {}

    record Pending(String commandId)
        implements ConfirmOutcome {}
}

public interface OrderAuthority {
    ConfirmOutcome confirm(
        ConfirmCommand command,
        AcknowledgmentLevel required
    );

    ConfirmOutcome lookupByCommandId(String commandId);
}
~~~

Các kiểu trên minh họa nhu cầu **khai báo điều kiện ACK và truy vấn outcome theo ID ổn định**. Không được cho rằng mọi NoSQL phân chia chính xác ba enum ấy hoặc hỗ trợ lựa chọn mức ACK động.

### 17.1. Không tự tin vào tên enum

Một adapter triển khai `REPLICATED_COMMITTED` phải thực sự dùng API/setting mà nhà cung cấp cam kết đúng mức, và phải kiểm tra topology/failure model. Trả enum mạnh nhưng chỉ gọi write local là lỗi contract của application.

### 17.2. Không đồng nhất `topologyEpoch` với commit proof

Epoch giúp nhận diện quyền leader, nhưng không tự chứng minh command đã committed. Cần receipt/status theo protocol; có sản phẩm không lộ epoch tới application.

### 17.3. Retry giữ commandId

~~~java
public final class ConfirmOrderService {
    private final OrderAuthority authority;

    public ConfirmOrderService(OrderAuthority authority) {
        this.authority = authority;
    }

    public ConfirmOutcome confirm(ConfirmCommand command) {
        ConfirmOutcome result = authority.confirm(
            command,
            AcknowledgmentLevel.REPLICATED_COMMITTED
        );

        if (result instanceof ConfirmOutcome.Pending) {
            ConfirmOutcome resolved =
                authority.lookupByCommandId(command.commandId());
            return resolved;
        }

        return result;
    }
}
~~~

Đây không phải retry engine production. `lookupByCommandId` có thể tạm trả `Pending` khi chưa đủ quorum/read authority; application cần một workflow bền để đối soát tiếp, bounded retries và error handling. Việc gọi `lookup` một lần không chứng minh kết quả cuối cùng.

### 17.4. Không lẫn durability với business invariant

Một ghi được majority committed vẫn có thể **bền vững lưu một trạng thái sai** nếu application kiểm tra sai số dư hoặc cho phép chuyển Order từ CANCELED sang CONFIRMED. Cần conditional state transitions/transactions phù hợp, không chỉ quorum.

## 18. NoSQL sản phẩm: các câu hỏi cụ thể cần đặt

| Họ/sản phẩm | Cơ chế liên quan | Điều phải kiểm tra trước khi hứa không mất ACK |
|---|---|---|
| **MongoDB replica set** | Primary election, write concern, journaling, rollback semantics | `w:1` vs majority; journal/durability; eligible election candidates; read concern; failover rollback |
| **Cassandra/ScyllaDB** | Leaderless replicas, consistency levels, repair, LWT | `ONE`, `QUORUM`, `LOCAL_QUORUM`, hinted handoff, reconciliation, serial conditions |
| **DynamoDB** | Managed replication, conditional/transaction APIs, regional/global deployment | Scope của write ACK, failover region, global table mode, conflict resolution và idempotency |
| **Azure Cosmos DB** | Replicas/regions, consistency levels, failover policies | Region mode, RPO, session/strong consistency, write conflict/transaction scope |
| **Redis/Sentinel/Cluster** | Primary–replica replication, promotion, AOF/RDB, `WAIT` | Replica lag, promotion policy, ACK vs persistence, failover loss window, key-slot scope |
| **Couchbase** | Active/replica partitions, durability levels, failover/rebalance | Replica durability/ACK, ambiguity handling, promotion/catch-up, transactional guarantees |
| **etcd/consensus KV** | Majority committed log, leader election/term, linearizable reads | Quorum availability, durable log, reads after election, membership change |

Bảng chỉ định hướng đọc tài liệu, không đặt một loại guarantee chung lên mọi sản phẩm hoặc mọi phiên bản.

### 18.1. MongoDB: local ACK có thể khác majority ACK

Với một replica set hỗ trợ các chế độ phù hợp, lựa chọn write concern kiểu **chỉ ACK từ primary** khác ACK majority về rủi ro write chưa replicate khi primary mất. Một write chưa được đa số xác nhận có thể bị rollback khi election/failover theo semantics sản phẩm.

Read concern, write concern, journaling và sessions có nhiệm vụ khác nhau. Để đánh giá bảo đảm của **một transaction đã commit**, phải xét riêng commit write concern/durability và topology thực, không chỉ việc gọi `withTransaction`.

Một câu hỏi quan trọng: **node được bầu primary mới có thể không có write nào, và write ấy đã được ACK ở mức nào?**

### 18.2. Cassandra/ScyllaDB: replica failover không đồng nghĩa leader election

Các hệ wide-column kiểu này thường không dùng một primary duy nhất cho mỗi key theo mô hình replica set MongoDB. Chọn coordinator khác và consistency level khác có thể thay đổi số replica tham gia thao tác.

Một write `ONE` có thể được ACK khi ít replica phản hồi; một write `QUORUM` có điều kiện khác. Nhưng `QUORUM` không mặc nhiên cho transaction serializable xuyên partition, và không tự chứng minh linearizability cho mọi read/write do timestamp reconciliation và các đặc điểm leaderless.

LWT/conditional operations dùng giao thức riêng cho một số bất biến, không nên đánh đồng với writes bình thường.

### 18.3. DynamoDB: local region và global replication

Managed service có cơ chế internal replication/failover không nhất thiết lộ từng replica. Để phân tích ghi đã ACK, xem **hợp đồng của regional API** cùng **cross-region mode của global tables** nếu có. Không tự kết luận global write bền qua mất cả region từ một write thành công tại region nguồn.

Conditional writes và transaction APIs có thể bảo vệ bất biến trong phạm vi hỗ trợ, nhưng cross-region conflict/replication semantics phải được xác minh riêng.

### 18.4. Cosmos DB: consistency level chưa đủ giải thích failover

Strong, Session, Bounded Staleness hoặc Eventual nói về read visibility theo phạm vi được hỗ trợ. Khi đánh giá failover cần thêm **region topology, write-region mode, replication guarantees, RPO và failover policy**.

Một transactional batch cục bộ theo logical partition không tự biến thành transaction nhiều region, dù account có consistency mode mạnh.

### 18.5. Redis: promotion khi replica còn trễ

Với asynchronous primary–replica replication, primary có thể ACK một write trước khi follower nhận; nếu primary chết và follower trễ được promote, write ấy có thể không có trên nguồn mới. Chế độ persistence và các lệnh đợi replica ACK có thể giảm một số cửa sổ rủi ro nhưng **không được mặc định là một consensus commit protocol**.

Giữ một idempotency key cũng không tạo lại write bị mất nếu record command và mutation cùng biến mất khỏi nguồn có thẩm quyền. Nếu hệ yêu cầu không mất write đã ACK khi mất primary, phải chọn kiến trúc/durability phù hợp chứ không chỉ thêm retry.

### 18.6. Couchbase: durability level và ambiguous outcome

Các cơ chế durability và failover có thể cho application lựa chọn tradeoff. Một số lỗi trong thời điểm ACK/commit có thể gây **ambiguous outcome**. Cần đọc SDK error classification và thiết kế commandId/reconciliation thay vì tự giả định thất bại.

### 18.7. Consensus KV: quorum an toàn nhưng minority có thể unavailable

Hệ kiểu etcd/Raft có thể từ chối committed writes hoặc linearizable reads khi không còn quorum, để không tạo hai histories trái nhau. Một local stale read có thể phục vụ theo mode riêng, nhưng đó không phải strong read.

## 19. Quorum với 5 replicas: election và placement

Giả sử:

~~~text
Data replicas: A, B, C, D, E
Majority = 3.

Write W1:
    replicated to A, B, C
    committed under protocol

Immediately after:
    A, B fail
    C, D, E remain
~~~

New voting majority `{C,D,E}` giao với commit majority `{A,B,C}` tại C. Một consensus election protocol đủ an toàn phải sử dụng thông tin log/term để không bầu leader thiếu **committed W1**.

### 19.1. Vì sao không chọn D ngay?

Nếu D thiếu W1 và C có W1, “D là máy khỏe nhất” không phải điều kiện an toàn. C cần đóng vai trò trong election để ngăn lựa chọn làm mất committed log theo rules của protocol.

### 19.2. Nếu C cũng chết?

Chỉ còn D/E, tức 2/5, không đủ majority. Hệ có thể không thể tiếp tục commit strong writes. Điều đó bảo vệ safety, dù availability giảm.

### 19.3. Thay đổi N khi thêm node

Nếu thêm F và reconfigure từ 5 thành 6 members, không chỉ tăng một số trong config rời rạc. Protocol cần bảo vệ continuity giữa các quorum của hai cấu hình để không “quên” committed entries. Operational tooling phải dùng quy trình reconfiguration chính thức.

### 19.4. Hai node cùng một AZ không phải hai failure domains

Nhiều replicas trên cùng host/power source/rack không cung cấp cùng mức chịu lỗi như replicas nằm trên hạ tầng độc lập. Khi lập RPO, phải xét **correlated failure**, không chỉ số lượng replica.

## 20. Khi leader mới có dữ liệu chưa commit từ leader cũ

Một trường hợp khác:

~~~text
A old leader:
    committed indices 1..40
    uncommitted entries 41,42

B new candidate:
    committed indices 1..40
    uncommitted different entry 41 (depending on history)
~~~

Một consensus protocol an toàn phải xử lý phần đuôi log chưa commit theo term/index matching, có thể **truncate/overwrite những entry chưa commit**, đồng thời không làm mất các entry đã committed.

### 20.1. Client có thể thấy gì?

Nếu client đã nhận ACK theo **một hợp đồng chỉ local append**, nó có thể tưởng entry 41 thành công rồi sau failover bị mất. Nếu client chỉ được ACK sau committed majority, entry 41 chưa commit không được hứa bền như một confirmed write theo contract ấy.

### 20.2. Internal log không phải business event stream luôn phát lại

Một entry chưa committed có thể xuất hiện trong log follower nhưng không được phát thành sự kiện nghiệp vụ cuối cùng. Không dùng “có log record ở một node” làm bằng chứng Order đã CONFIRMED.

### 20.3. Log compaction/snapshot không phá committed prefix

Một consensus KV có thể snapshot state và compact log cũ. An toàn phụ thuộc snapshot gồm các committed entries tương ứng và metadata log/term được giữ đúng. Không xóa log hoặc snapshot bằng tay chỉ vì “node đã bắt kịp”.

## 21. Reconfiguration, bảo trì và rolling restart

Failover không chỉ xảy ra do crash. Operator có thể:

- Restart/upgrade một node.
- Bảo trì một availability zone.
- Drain leader và chuyển leadership.
- Thêm/bớt replica.
- Di chuyển partition giữa nodes.
- Đổi write concern hoặc replication factor.

### 21.1. Thứ tự bảo trì quan trọng

Với quorum 3/5, không nên tắt tùy tiện ba voting members cùng lúc rồi mong strong writes vẫn chạy. Phải biết node nào currently healthy, committed/applied lag và topology placement trước mỗi bước.

### 21.2. Planned switchover khác unplanned failover

Với planned switchover, hệ có thể chủ động dừng nhận write mới, chờ follower catch up tới mốc được hứa, chuyển epoch/leadership rồi cập nhật routing. Cách này thường giảm unknown outcomes hơn crash đột ngột, nhưng vẫn phải kiểm chứng protocol.

### 21.3. Retry ở thời điểm chuyển leader

Một client có thể gửi command ngay khi routing thay đổi. Lệnh có thể được committed bởi leader cũ hoặc mới, tùy thời điểm. `commandId` và fencing logic phải đảm bảo một ý định không được áp dụng hai lần.

### 21.4. Đừng chỉnh trực tiếp membership metadata

Nếu consensus protocol yêu cầu thay đổi membership qua một lệnh đã committed, sửa file config ở từng máy có thể tạo các quorum không tương thích. Cần dùng phương tiện quản trị chính thức và đọc hướng dẫn version hiện hành.

## 22. Failover và các transaction nhiều bản ghi

Một transaction gồm:

~~~text
BEGIN
    UPDATE Inventory(SKU-A)
    INSERT Order(O-100)
    INSERT Outbox(OrderCreated:O-100)
COMMIT
~~~

Nếu failover xảy ra giữa commit, câu hỏi không chỉ là **ba mutations có tồn tại trên leader mới không**, mà còn là **transaction đã commit nguyên tử hay chưa, commit decision được lưu bền ở đâu, và reader thấy trạng thái nào**.

### 22.1. Distributed transaction coordinator có thể lỗi

Với transaction trải nhiều shards, một coordinator có thể gặp crash sau khi một số participants đã prepare. Recovery phải xác định quyết định commit/abort theo protocol; không được tự commit một phần ở shard mới và quên phần còn lại.

### 22.2. Quorum của từng shard không tự tạo global atomicity

Order shard có thể có committed write, Inventory shard cũng có committed write, nhưng hai commits độc lập không tự là một transaction chung. Muốn all-or-nothing phải có transaction orchestration/2PC-like protocol được sản phẩm hỗ trợ hoặc thay đổi workflow.

### 22.3. Write concern mạnh không tự tăng isolation

Majority durable ACK giúp bảo vệ dữ liệu sau failover trong phạm vi nào đó. Nó **không tự ngăn write skew**, lost update ở tầng app hoặc split transaction do nhiều service. Atomicity/isolation và durability là các chiều riêng.

### 22.4. Transaction callback có thể retry

Một số SDK tự retry transaction khi conflict hoặc failover. Không gọi payment gateway hay gửi email trực tiếp trong callback có thể thực thi nhiều lần. Dùng outbox và consumer idempotent.

### 22.5. Commit result không rõ

Một transaction có thể commit bền rồi coordinator/leader chết trước khi client nhận response. Ứng dụng cần `transactionId`/`commandId` ổn định và cơ chế tra kết quả. Không kết luận timeout nghĩa là rollback.

## 23. Read after failover: ghi không mất nhưng kết quả vẫn có thể cũ

Client nhận ACK write Order version 8. Cluster failover xong, một GET trả version 7. Có ít nhất ba hướng cần kiểm tra:

1. **Write thực sự chưa được committed trong phạm vi hứa** và bị rollback/lost.
2. **Write đã committed**, nhưng GET đang đọc follower/replica/index còn lag.
3. **Client bị route sai** tới node cũ, cache cũ hoặc region chưa catch up.

Không đủ bằng chứng để kết luận chỉ từ một response GET.

### 23.1. Đọc từ nguồn có thẩm quyền

Để kiểm chứng durable commit, đọc bằng consistency/read concern phù hợp với contract sau failover, đồng thời dùng `commandId`/version để đối soát.

### 23.2. Linearizable read cần giao thức

Trong consensus group, một read mạnh có thể cần đảm bảo leader hiện hành và commit index đã đủ mới (ví dụ read-index/lease protocol được triển khai an toàn). Chỉ đọc state machine của một follower bất kỳ không tự là linearizable.

### 23.3. Read-your-writes qua reconnect

Session token/causal context có thể bị mất khi client reconnect hoặc load balancer chuyển instance. Nếu API hứa session consistency, cần giữ và truyền context đúng; không coi việc “vẫn đăng nhập cùng account” tự mang lại causal session DB.

### 23.4. Async search/index

Một Search API không thấy Order v8 có thể là eventual projection lag. Hãy kiểm tra source Order trước, rồi kiểm tra CDC/outbox/consumer lag. Không thực hiện “repair source” vì search còn cũ.

## 24. RPO, RTO và lựa chọn mức ghi cho nghiệp vụ

**Recovery Point Objective (RPO)** là mức mất dữ liệu tối đa chấp nhận được. **Recovery Time Objective (RTO)** là mục tiêu thời gian khôi phục dịch vụ.

| Dữ liệu | Yêu cầu thường gặp | Gợi ý đánh giá |
|---|---|---|
| Catalog cache | Có thể dựng lại, chấp nhận stale | Replica local/cache và revalidation |
| Cart tạm | Có thể chấp nhận mất một phần tùy sản phẩm | Durability thực và recovery UX |
| Inventory reservation | Không được oversell sau confirmed reservation | Strong conditional write, durable authority |
| Order confirmed | Phải còn sau các lỗi được cam kết | Write ACK/replication/failover phù hợp |
| Payment/ledger | Không được tạo charge trùng hoặc mất kết quả settle | Durable ledger + idempotency + reconciliation |
| Analytics events | Có thể replay từ nguồn bền | Durable upstream log, checkpoint phối hợp |

### 24.1. RPO theo số write hoặc thời gian

Một dịch vụ có thể công bố khả năng mất một khoảng dữ liệu gần nhất khi region disaster trong mode async. Không thể suy ra “mất tối đa 1 giây” chỉ từ cấu hình đồng bộ mỗi giây mà không xét backlog, network và failover mode.

### 24.2. RTO phải tính cả readiness nghiệp vụ

~~~text
Detection time
  + Election time
  + Log catch-up / apply
  + Routing refresh
  + Client retries and reconciliation
  + Warm-up / checks
  = end-to-end recovery duration
~~~

Một leader được bầu nhưng strong read bị treo hoặc mọi checkout vẫn trả `NOT_LEADER` chưa phải RTO đã đạt.

### 24.3. RPO thấp có thể tăng latency hoặc giảm availability

Đợi durable majority/remote region cần coordination, có thể tăng p99 latency. Trong partition, node không đủ quorum không thể tiếp tục cam kết write mạnh. Đây là lựa chọn có chủ đích cho dữ liệu quan trọng.

### 24.4. Không mọi endpoint cần cùng mức

Search có thể trả cache có nhãn `asOf`; ReserveStock cần authoritative commit hoặc trạng thái PENDING chứ không được giả vờ đã giữ hàng. Chọn đúng contract cho từng nghiệp vụ.

## 25. Những chỉ số cần giám sát trước và sau failover

| Nhóm | Metric/field | Ý nghĩa |
|---|---|---|
| Election | Term/epoch, leader changes, election duration | Có flapping hoặc nhiều election không? |
| Quorum | Eligible voters, quorum health, missed heartbeats | Có đủ quyền commit không? |
| Replication | Follower log lag, last appended index | Replica nào bị trễ? |
| Commit | Committed index/sequence, commit lag | Write nào được coi committed? |
| Apply | Applied index, state machine lag | Strong read readiness tới đâu? |
| Durability | Journal/fsync latency, durability failures | Replica ACK có thực sự bền? |
| Write ACK | Counts theo write concern/durability level | Client đang được hứa gì? |
| Read | Strong/weak read latency, stale-read incidents | Sau failover có đọc cũ không? |
| Client | NOT_LEADER, timeouts, unknown outcomes, retries | Routing và idempotency |
| Topology | Replica distribution per AZ/region | Rủi ro correlated failure |
| Data | Reconciliation gaps, rollbacks, invariant violations | Có mất ghi đã xác nhận không? |
| Catch-up | Snapshot transfer, log replay time | Khi nào redundancy phục hồi? |
| Recovery | RTO, RPO observed, restored write count | Đối chiếu SLO/fault model |

### 25.1. Phân biệt lag và data loss

`committedIndex=100` ở nguồn, `appliedIndex=98` ở follower không tự là data loss. Follower có thể còn apply log. Nhưng nếu sau failover history có thẩm quyền chỉ tới 98 dù trước đó client đã nhận ACK committed tới 100, đó là dấu hiệu cần điều tra nghiêm trọng về contract/protocol/config.

### 25.2. Cảnh báo thiếu redundancy

Một cluster còn đúng quorum tối thiểu có thể vẫn phục vụ nhưng chỉ cần thêm một node lỗi sẽ mất khả năng ghi. Cần alert **sắp mất quorum** và tiến độ thay thế/catch-up replicas, không chỉ báo `database up`.

### 25.3. Ghi bằng chứng ACK theo command

Đối với test và nghiệp vụ quan trọng, lưu `commandId`, reply status, durability setting và timestamp/sequence nếu API cho phép. Không dùng timestamp client một mình làm thứ tự commit đáng tin.

### 25.4. Tránh log thông tin nhạy cảm

Trace failover không cần in toàn bộ thông tin thanh toán, mật khẩu hay token session. Ghi nhận ID, term, index, outcome và metadata đã được bảo vệ theo chính sách.

## 26. Fault injection: chứng minh ghi đã ACK sống qua failover

Test đúng cần phát sinh workload có định danh để đối soát:

~~~text
For each write:
    commandId = unique stable identifier
    record whether API returned successful ACK
    record acknowledgment/durability mode

Inject failure at selected point.

After cluster recovers:
    read authoritative state
    compare acknowledged commands
    classify unknown commands separately
~~~

### 26.1. Test 1 — Leader chết sau ACK local

Tạo ghi với chế độ ACK local yếu hơn majority (nếu sản phẩm/harness cho phép), ngắt leader trước khi follower catch up. Quan sát liệu write có còn sau election. Mục tiêu là **hiểu risk window**, không giả định mọi lần test đều mất ghi.

### 26.2. Test 2 — Leader chết sau majority commit

Ghi với ACK được tài liệu xác định là majority committed/durable theo fault model. Khi đã nhận ACK, làm leader chết và khôi phục cluster với đủ quorum còn lại. Đối soát mọi command đã ACK. Nếu mất, kiểm tra config, storage, test harness hoặc vấn đề nghiêm trọng.

### 26.3. Test 3 — Mất ACK sau commit

Cho database commit rồi cắt response network tới client. Client phải giữ stable commandId, tra committed outcome và không tạo một lệnh nghiệp vụ mới.

### 26.4. Test 4 — Old leader vẫn chạy nhưng bị partition

Tạo minority partition khiến leader cũ không còn authority, bầu leader mới ở phía đủ quorum nếu protocol cho phép. Gửi write trực tiếp tới leader cũ và kiểm tra **fencing/term** ngăn acknowledged strong write trái phép.

### 26.5. Test 5 — Stale follower được thử làm ứng viên

Làm chậm replication tới một follower, rồi kích hoạt failover có kiểm soát. Kiểm tra election rules có ngăn ứng viên thiếu committed history được chọn hay không.

### 26.6. Test 6 — Follower có log nhưng chưa apply

Tạo apply lag. Kiểm tra strong read sau failover không trả state trước commit nếu contract cấm, và xác định khi nào node được mở traffic.

### 26.7. Test 7 — Thay đổi membership

Trong môi trường test, thêm/bớt voting members theo quy trình chính thức rồi tạo crash/failover ở các mốc. Kiểm tra quorum continuity và committed writes được bảo vệ qua chuyển cấu hình.

### 26.8. Test 8 — Cross-region outage

Với topology có nhiều region, ghi các command có ACK regional và, nếu có, ACK cross-region mạnh hơn. Mô phỏng mất region nguồn theo fault model được phép. Đo RPO/RTO **riêng cho từng mode**.

### 26.9. Test 9 — Redis/async primary replica

Tạo replica lag có kiểm soát, ghi lên primary và thực hiện promotion. Đọc lại trạng thái trên nguồn mới; xác định loss window theo ACK/persistence/replication của deployment.

### 26.10. Test 10 — Leaderless read/write quorums

Thử N/R/W theo topology hiện hành, chèn network delay, concurrent writes, clock offset giả lập nếu môi trường kiểm thử cho phép và repair. Đừng chỉ kiểm tra một phép tính R+W>N mà bỏ qua conflict resolution.

### 26.11. Test 11 — Client còn dùng routing cũ

Giữ connection pool tới leader cũ sau election, phát write với commandId cũ/mới. Kiểm tra driver phát hiện term/not-leader, cập nhật route và không gửi lại transaction theo cách nhân đôi nghiệp vụ.

### 26.12. Test 12 — Restore backup sau sự cố

Thử restore snapshot/backup và log archive tới một mốc cụ thể, kiểm tra không có gap trong log chain, dữ liệu nhạy cảm không bị hồi sinh trái policy và thứ tự các committed commands phù hợp. WAL live không thay thế backup độc lập.

### 26.13. Kiểm thử trên môi trường được phép

Không kill production leader, ngắt mạng khách hàng, làm đầy disk hay xóa WAL thật chỉ để chứng minh CAP. Dùng staging/chaos environment được phê duyệt, dữ liệu giả, guardrails, rollback và observability đủ để hiểu chính xác lỗi đã chèn.

## 27. JUnit skeleton: kiểm tra những write đã được ACK

Một adapter:

~~~java
public interface FailoverTestAdapter {
    void resetNamespace(String namespace);

    // Must use the configured write concern/durability of the target DB.
    WriteTestResult put(
        String namespace,
        String commandId,
        String key,
        String value
    );

    void failCurrentLeaderAndRecover();

    // Must read authoritative committed state after recovery.
    String authoritativeGet(String namespace, String key);
}

public enum WriteTestResult {
    ACK_COMMITTED,
    KNOWN_REJECTED,
    UNKNOWN_OUTCOME
}
~~~

Test khung:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.Map;

class AcknowledgedWriteFailoverTest {
    private final FailoverTestAdapter db =
        TestEnvironment.failoverAdapter();

    @Test
    void acknowledgedCommittedWritesSurviveSupportedLeaderFailure() {
        String namespace = "failover-test-314";
        db.resetNamespace(namespace);

        Map<String, String> committed = new LinkedHashMap<>();

        for (int i = 0; i < 200; i++) {
            String key = "order-" + i;
            String value = "confirmed-v1";
            String commandId = "cmd-" + i;

            WriteTestResult outcome =
                db.put(namespace, commandId, key, value);

            if (outcome == WriteTestResult.ACK_COMMITTED) {
                committed.put(key, value);
            }
            // UNKNOWN_OUTCOME phải được đối soát riêng.
        }

        db.failCurrentLeaderAndRecover();

        for (var entry : committed.entrySet()) {
            assertEquals(
                entry.getValue(),
                db.authoritativeGet(namespace, entry.getKey())
            );
        }
    }
}
~~~

**Giới hạn của mã:** `TestEnvironment` là fixture giả định. `ACK_COMMITTED` phải thực sự map tới mức ACK có contract bảo vệ trước fault đã chèn; không được đặt tên như vậy nếu adapter chỉ chờ local write. `failCurrentLeaderAndRecover` phải tạo đúng failure model và xác định cluster đã đạt readiness phù hợp. Test không xử lý chi tiết timeout giữa kiểm tra và crash, concurrency, cleanup, secret handling và fault injection permissions; nhóm phải bổ sung.

### 27.1. Cần giữ tập UNKNOWN riêng

Một lệnh timeout trước ACK có thể **đã commit**. Không đưa nó vào tập “chắc chắn mất” hay “chắc chắn chưa commit”. Phải tra bằng commandId và phân loại.

### 27.2. Không chỉ đếm tổng số record

Nếu có 200 ACK và sau failover vẫn có 200 records nhưng một số key cũ bị mất và một số key khác bị ghi trùng, tổng số vẫn bằng nhau. Đối soát **từng commandId, key, version và expected state**.

### 27.3. Kiểm tra topology và fault model

Test chạy trên một node rồi restart không chứng minh bảo đảm majority election. Phải ghi deployment ID, replication factor, voting members, failure domain, write concern và API read dùng để đối soát.

### 27.4. Test thành công không thay thế protocol

Một trăm lần pass hữu ích nhưng không chứng minh mọi lịch phân tán. Kết hợp tài liệu sản phẩm, formal guarantees, configuration evidence và fault testing để đánh giá.

## 28. Một case study: Order được xác nhận nhưng sau failover lại PENDING

Trạng thái ban đầu:

~~~text
Order O-100:
    status = PENDING
    version = 7
~~~

Client gửi `ConfirmOrder(commandId=C-9001)`. Server trả success, nhưng sau leader failover, UI lại hiển thị PENDING.

### 28.1. Bước 1 — Xác định đường đọc

UI đang đọc source Order, follower, cache hay search? Read consistency là gì? Có session token không? Phải tìm trạng thái committed tại **nguồn có thẩm quyền** trước khi gọi đây là rollback.

### 28.2. Bước 2 — Đọc hợp đồng ACK

Write dùng setting nào: leader-only, journal, majority, regional durability? Transaction đã commit ở mốc nào? Có log/receipt/operation ID không?

### 28.3. Bước 3 — Kiểm tra election

Leader cũ chết hay chỉ partition? Node mới có committed log index/term nào? Có rollback/reconciliation nào do product reporting công bố? Có thay đổi membership hay forced promotion không?

### 28.4. Bước 4 — Phân loại kết quả

| Quan sát | Khả năng | Bước kế tiếp |
|---|---|---|
| Source committed v8, UI cache v7 | Stale read model | Làm rõ lag/invalidation |
| New source v7, old leader chỉ ACK local v8 | Rủi ro đã được cấu hình cho phép | Đánh giá RPO/write concern |
| New source v7 dù ACK commit mạnh hợp lệ trong fault model | Có thể vi phạm nghiêm trọng hoặc test/config hiểu sai | Điều tra ngay và giữ bằng chứng |
| Client timeout, source có v8 | Unknown response but committed | Trả kết quả cũ theo commandId |
| Hai nguồn cùng nhận ghi trái nhau | Split brain/fencing failure | Ngăn traffic cũ, điều tra election/epochs |

### 28.5. Bước 5 — Không tự “ghi lại mọi đơn bị mất”

Nếu Order v8 không hiện ra, việc gửi lại `ConfirmOrder` có thể phát lại hiệu ứng ngoài như payment/email. Chỉ retry khi đã xác định outcome và command được thiết kế idempotent. Với Payment, cần đối soát gateway theo paymentId.

### 28.6. Bước 6 — Rà soát phạm vi sự cố

Điều tra các command đã ACK trong cùng khoảng thời gian failover, không chỉ O-100. Nếu một loạt acknowledged writes bị rollback, cần xác định window và ảnh hưởng nghiệp vụ trước khi sửa.

## 29. Một case study: leader đổi nhưng write đã committed vẫn đúng

Một hệ key–value dùng consensus cho reservation:

~~~text
T0: committed index = 100.
T1: CreateReservation(R-9001), entry index=101.
T2: majority commits 101, client nhận ACK.
T3: leader A chết.
T4: leader B được bầu hợp lệ ở term mới.
T5: B apply index 101 và phục vụ reads.
T6: GET Reservation R-9001 -> RESERVED.
~~~

Các điểm bảo vệ:

- Entry đã đạt **commit condition** trước ACK.
- Election quorum và eligibility giữ **committed history**.
- Leader cũ bị **fence**.
- B apply hoặc phục vụ read theo protocol để không trả state trước index 101 khi client yêu cầu linearizable/session guarantee.
- Retry của client dùng cùng reservationId.

### 29.1. Nếu B chưa apply entry 101 ở T4?

Nó có thể cần catch up/apply trước khi trả read mới nhất. Không được coi việc chưa apply tạm thời là entry bị mất.

### 29.2. Nếu client đọc từ C yếu hơn?

C có thể chưa kịp apply và trả giá trị cũ nếu API cho phép stale read. Đây là khác biệt read consistency, không phải bằng chứng committed log bị xóa.

### 29.3. Nếu R-9001 còn phải gọi thanh toán?

Quorum commit cho Reservation không tự bảo đảm Payment được capture. Workflow cần outbox, paymentId idempotent và trạng thái bền riêng.

## 30. Những ngộ nhận phổ biến

### “Có ba replica thì ACK chắc chắn không mất”

Không. ACK có thể xảy ra trước replication, replica có thể chưa durable và election có thể chọn nguồn không có write nếu contract cho phép.

### “Leader đã append log nghĩa là đã committed”

Không. Entry có thể chỉ tồn tại ở leader và bị bỏ sau failover nếu chưa commit theo protocol.

### “Replica có log index lớn nhất chắc chắn làm leader tốt nhất”

Không. Cần term, log freshness và committed prefix theo election protocol.

### “Majority intersection tự đủ bảo đảm an toàn”

Chưa đủ. Cần quy tắc election/commit, durability, membership change và fencing.

### “Bầu được leader mới là đã khôi phục thành công”

Chưa đủ. Cần commit/apply đúng, read readiness, routing, data reconciliation và nghiệp vụ hoạt động.

### “Replica ACK nghĩa là fsync”

Không mặc định. Phải đọc ACK/durability semantics cụ thể.

### “Witness/arbiter giữ một bản sao dữ liệu”

Không nên giả định. Voting member không nhất thiết chứa data.

### “W=QUORUM thì mọi read được linearizable”

Không. Leaderless quorum có giới hạn về clocks, conflict, sloppy quorum và repair.

### “Leader cũ mất heartbeat chắc chắn đã chết”

Không. Nó có thể bị partition hoặc pause; cần fencing/term.

### “Hai leader cùng nhận ghi rồi chọn last-write-wins là đã giữ invariant”

Không. Có thể mất một ghi đã báo thành công, oversell hoặc state transition sai.

### “Majority committed nghĩa là mọi follower đều apply”

Không. Commit index và applied index là các mốc khác nhau.

### “Một follower đọc cũ chứng minh đã mất write”

Không. Có thể là replica lag hoặc read mode yếu hơn.

### “Read concern majority có cùng nghĩa linearizable read”

Không được mặc định. Phải đọc định nghĩa của sản phẩm.

### “Local durable ACK đủ cho failover khi leader mất vĩnh viễn”

Không nếu write chưa có trên nguồn được chọn mới.

### “Đã replicate trong một AZ thì chịu được mất cả region”

Không. Failure domains khác nhau.

### “Quorum election và data quorum là cùng một con số”

Không nhất thiết, nhất là khi có witness/arbiters và cấu hình đặc biệt.

### “Thay membership thủ công không ảnh hưởng lịch sử committed”

Sai. Reconfiguration thiếu protocol có thể phá quorum continuity.

### “Timeout khi COMMIT nghĩa là transaction rollback”

Không. Client có thể chỉ mất ACK sau commit.

### “Retry command ở leader mới không thể trùng”

Không. Consensus commit không tự thay thế business idempotency.

### “Tăng số replica luôn giảm RTO”

Không. Cần xem network, topology, quorum, election và catch-up; thêm replica có thể tăng một số chi phí.

### “Dùng strong write là mọi index/cache đồng bộ ngay”

Không. Derived projections có thể bất đồng bộ.

### “Failover có RTO tốt thì RPO tự bằng không”

Không. Thời gian mở service và mức mất dữ liệu là hai mục tiêu riêng.

### “Test kill process đủ chứng minh power-loss durability”

Không. OS page cache và storage có thể sống sau process kill.

### “Có backup thì write đã ACK không bao giờ mất”

Backup có chu kỳ/retention; nó không thay quorum commit cho write mới và cũng cần restore/log chain để xác định RPO.

## 31. Quy trình lựa chọn và kiểm tra cấu hình failover

1. **Xác định dữ liệu và hậu quả mất ACK.** Order, ledger, cart, cache có yêu cầu khác nhau.
2. **Viết fault model.** Process crash, host failure, node permanent loss, AZ/region outage, network partition.
3. **Chọn RPO/RTO.** Nêu rõ áp dụng cho lỗi nào, không dùng “zero loss” chung chung.
4. **Vẽ topology.** Data replicas, voting members, witnesses, AZs, regions, partitions.
5. **Đọc write ACK contract.** Local accepted, durable log, replica/quorum commit theo sản phẩm.
6. **Đọc election eligibility.** Ai được bầu, kiểm tra log/term/priority thế nào?
7. **Đọc fencing.** Old leader/worker bị từ chối bằng epoch/term/lease ra sao?
8. **Đọc state recovery.** Committed vs uncommitted log, truncate, replay, apply, catch-up.
9. **Đọc read consistency.** Source/secondary, session, linearizable và stale mode.
10. **Kiểm tra thay đổi membership.** Quy trình rolling restart, remove/replace member an toàn.
11. **Kiểm tra cross-region.** Synchronous/async replication, conflict mode, data residency.
12. **Thiết kế commandId/idempotency.** Retry sau timeout và failover không được duplicate.
13. **Đối soát downstream.** Outbox, CDC, index, payment, event ordering.
14. **Chạy fault injection.** ACK trước/sau commit, leader failure, minority partition, lagging replica.
15. **Đo p95/p99 và recovery.** Election time, write latency, apply lag, RTO/RPO observed.
16. **Lưu hồ sơ cấu hình và giới hạn.** Version/SDK/options/failure domains và những gì không hứa.

### 31.1. Mẫu hồ sơ hợp đồng

~~~yaml
workload: confirmed-order-write
businessInvariant:
  - "a successfully confirmed order must remain queryable"
  - "retries must not create duplicate charges"

deployment:
  product: "<database/service>"
  version: "<engine/SDK version>"
  topology: "<replicas, voters, witnesses, partitions>"
  failureDomains: "<AZ/region layout>"

write:
  api: "<specific write/transaction API>"
  acknowledgment: "<precise commit/durability condition>"
  transactionScope: "<item/partition/multi-shard>"

failover:
  electionProtocol: "<documented mechanism>"
  leaderEligibility: "<log/term and candidate rules>"
  fencing: "<epoch/term/lease enforcement>"
  uncommittedEntryBehavior: "<rollback/truncation rules>"
  knownFaultModel: "<failures the contract covers>"
  regionRpo: "<supported regional disaster contract>"

client:
  commandId: "stable across requests and retries"
  timeoutBehavior: "reconcile unknown commit"
  readAfterFailover: "<authoritative consistency mode>"

evidence:
  docs: ["<versioned official references>"]
  configSnapshot: "<safe configuration reference>"
  failoverTest: "<report/run ID>"
  owner: "<team>"
~~~

Không điền các dấu `<...>` bằng giả định. Một hợp đồng kỹ thuật chỉ có giá trị khi mỗi mệnh đề có bằng chứng từ **tài liệu sản phẩm, cấu hình triển khai và kiểm thử đúng failure model**.

## 32. Bài tập thực hành

### Bài 1 — ACK leader-only

Cluster A/B/C, leader A ACK một write sau khi ghi bền local nhưng chưa replicate. A chết vĩnh viễn; B làm leader. Write được client nhận thành công có chắc còn không? Phân biệt process restart và mất node vĩnh viễn.

### Bài 2 — Majority commit và election

N=3, write E42 được committed ở A/B. A chết, B/C còn sống. Giải thích vì sao quorum overlap hữu ích và vì sao election protocol vẫn phải ngăn C thiếu E42 được chọn nếu chưa đáp ứng điều kiện log.

### Bài 3 — Last appended vs committed

Replica A có lastIndex=108, commitIndex=105; B có lastIndex=107, commitIndex=105. Có thể chọn leader chỉ dựa vào lastIndex không? Giải thích vai trò term, committed prefix và entry chưa commit.

### Bài 4 — Five-node quorum

N=5, majority=3. Write đã committed trên A/B/C, rồi A/B chết. C/D/E còn. Phân tích election và durability. Nếu C cũng chết, vì sao D/E không thể tiếp tục strong commit trong mô hình này?

### Bài 5 — Arbiter/witness

Hệ có hai data nodes A/B và arbiter C. A ACK local write chưa tới B rồi chết vĩnh viễn. B+C bầu leader. Việc có quorum vote có cứu được write không? Phân biệt voting quorum và data-bearing quorum.

### Bài 6 — Network partition với zombie leader

Leader A bị partition nhưng không chết, B/C bầu B. Sau 30 giây A kết nối lại và gửi mutation với token cũ. Thiết kế term/epoch/fencing để tránh hai nguồn ghi có thẩm quyền.

### Bài 7 — Unknown commit outcome

Client gửi `ReserveStock(commandId=R-9001)`; leader commit majority rồi chết trước ACK. Client timeout. Thiết kế luồng đối soát trên leader mới, idempotency và trạng thái PENDING khi vẫn chưa xác minh được.

### Bài 8 — Local durability vs region outage

Một ghi đã bền trên ba nodes trong cùng Region A; Region B chỉ có asynchronous copy. Region A mất hoàn toàn trước khi B nhận. RPO của mode này phải được mô tả thế nào? Vì sao nhiều AZ trong A không tự là multi-region RPO=0?

### Bài 9 — Leaderless QUORUM

Với N=3, R=2, W=2, giải thích tính chất overlap và ít nhất bốn lý do không thể suy ra linearizability tuyệt đối, gồm clock skew, concurrent writes, hinted/sloppy quorum và membership change.

### Bài 10 — Read lag sau failover

Order version 8 đã committed. Leader mới có log nhưng state machine đang apply tới version 7. Một GET ở follower trả v7. Làm sao phân biệt visibility lag với data loss và thiết kế strong read đúng contract?

### Bài 11 — MongoDB

So sánh rủi ro failover của write ACK từ primary với write concern majority trong topology phù hợp. Cần kiểm tra thêm journaling, election, read concern và rollback semantics gì trước khi hứa độ bền?

### Bài 12 — Cassandra/ScyllaDB

Trong cluster hai datacenters, write `LOCAL_QUORUM` ở DC1 rồi đọc `ONE` ở DC2 trong lúc replication chậm. Có thể thấy gì? Vì sao trường hợp này khác leader election và không tự là linearizable transaction?

### Bài 13 — Redis

Primary ACK một lệnh giảm Stock, follower chưa nhận. Primary chết và follower được promote. Giải thích loss window, vai trò persistence/replication wait và vì sao script nguyên tử không đủ bảo vệ business command qua failover.

### Bài 14 — Reconfiguration

Quorum từ N=3 được đổi thành N=5. Hãy nêu tại sao hai cấu hình quorum độc lập có thể nguy hiểm nếu reconfiguration không theo protocol, và đề xuất quy trình kiểm thử khi rolling restart/thêm node.

### Bài 15 — Bảo vệ ghi đã ACK

Viết integration-test harness lưu danh sách `commandId` của những writes có ACK committed, kill leader trong môi trường test, đợi failover và đọc đối soát từng key/version. Tách riêng unknown outcomes.

### Bài 16 — CAP và RTO/RPO

Một hệ từ chối strong writes ở minority partition nhưng vẫn trả stale local reads. Phân tích consistency/availability theo **từng thao tác**, rồi nêu cách đo RTO và RPO sau khi mạng nối lại.

### Bài 17 — Cross-shard transaction

Order ở shard X, Inventory ở shard Y. Mỗi shard có majority commit riêng nhưng không có transaction chung. Hãy giải thích vì sao hai majority ACK không tự tạo atomic checkout và đề xuất transaction coordinator hoặc saga.

### Bài 18 — Tình huống điều tra

Sau failover, Search không thấy Order O-100 dù client đã ACK. Hãy xây một cây quyết định phân biệt source data loss, stale read replica, async index lag, wrong routing và unknown commit; nêu những log/metrics cần thu thập.

### Bài 19 — Bố trí theo failure domain

N=5 đặt ba replicas ở Region A và hai ở Region B. Đánh giá khả năng bầu leader khi mất A, khi mất B và khi network partition giữa A/B. Nếu yêu cầu RPO=0 khi mất trọn Region A, cần thay đổi kiến trúc/quorum ra sao?

### Bài 20 — Quyết định ACK theo nghiệp vụ

Cho bốn workload: cache, analytics ingest có nguồn replay, confirmed orders và payment ledger. Lập bảng lựa chọn ACK/durability/replication, failover behavior, idempotency và backup/PITR theo fault model đã định nghĩa; nêu tradeoff latency.

---

**Kết luận:** Failover an toàn không chỉ là bầu được một node mới rồi chuyển traffic. Điều quan trọng là **ghi nào được client xác nhận, ghi nào đã committed và lưu bền theo protocol, replica nào đủ điều kiện làm leader, và quyền leader cũ được vô hiệu hóa ra sao**. Một write đã ACK tại leader nhưng chưa replicate có thể biến mất nếu leader chết vĩnh viễn; ngược lại, một consensus quorum được thiết kế đúng có thể bảo vệ committed history qua leader election trong failure model đã công bố. Quorum intersection cần đi cùng **log freshness, term/epoch, fencing, durability và reconfiguration an toàn**. Với leaderless replication, phải hiểu riêng R/W, version reconciliation và repair; không tự suy tuyến tính từ chữ quorum. Cuối cùng, **ACK bị mất vẫn có thể che giấu một commit thành công**, nên client cần stable commandId, idempotency và đối soát. Một hệ chỉ thực sự đáp ứng nghiệp vụ khi **RPO, RTO, consistency, transaction scope và hành vi failover được định nghĩa theo từng thao tác và kiểm chứng bằng fault injection phù hợp**.
