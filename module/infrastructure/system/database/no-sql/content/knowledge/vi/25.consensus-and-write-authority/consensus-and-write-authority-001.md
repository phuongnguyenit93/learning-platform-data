# Bài toán thống nhất trạng thái khi có lỗi hoặc mất liên lạc

Một hệ NoSQL có ba bản sao của cùng một nhóm dữ liệu. Trong điều kiện bình thường, client ghi `Order O-100 = CONFIRMED`, các bản sao nhận cập nhật và cùng trả kết quả. Sau đó mạng bị chia làm hai phía: một máy không còn liên lạc với hai máy kia. Cả hai phía đều còn tiến trình đang chạy; một số client vẫn gửi request tới phía bị cô lập. **Ai có quyền chấp nhận lệnh ghi tiếp theo? Khi mạng nối lại, bản sao nào đại diện cho lịch sử đúng?**

Đây là **bài toán thống nhất trạng thái khi có lỗi hoặc mất liên lạc** trong chương *Đồng thuận và quyền ghi*. Bài toán không chỉ là “sao chép dữ liệu đủ nhanh”; nó liên quan đến việc nhiều node phải **thống nhất một quyết định**, dù chúng có thể gặp crash, chậm mạng, mất thông điệp, timeout, failover hoặc thay đổi thành viên.

Nếu hai node tự nhận mình là nguồn ghi có thẩm quyền, có thể xảy ra:

~~~text
Node A nhận: Order O-100 -> CONFIRMED.
Node B nhận: Order O-100 -> CANCELED.

Client của cả hai phía đều nhận SUCCESS.

Mạng hồi phục:
    Hai lịch sử cùng tồn tại.
    Chọn một bản bằng timestamp có thể phủ nhận
    điều đã hứa với client ở phía còn lại.
~~~

Với dữ liệu như catalog, comment hoặc telemetry, ta có thể chấp nhận một số trạng thái tạm thời khác nhau rồi hòa giải. Với **quyền sở hữu khóa, số dư, tồn kho, quota, phiên bản cấu hình hoặc thứ tự lệnh giao dịch**, hai nguồn đồng thời ra quyết định có thể làm sai bất biến nghiệp vụ.

Các giao thức **đồng thuận phân tán (distributed consensus)** giải quyết nhu cầu thống nhất này trong một phạm vi và failure model xác định. Chúng giúp một nhóm bản sao thống nhất các quyết định hoặc thứ tự lệnh, thay vì từng node tùy ý quyết định theo trạng thái cục bộ. Tuy nhiên, đồng thuận không làm cho mọi request luôn thành công khi mạng bị chia, không thay thế transaction business và không tự bảo đảm một external payment chỉ chạy một lần.

> **Phạm vi bài học:** Tập trung vào cơ chế đồng thuận và quyền ghi áp dụng cho hệ thống NoSQL phân tán. Các mô hình Raft, Paxos, consensus KV, leader–follower, leaderless và multi-region được dùng để giải thích nguyên lý. Một tên sản phẩm cụ thể không tự nói lên phạm vi atomicity/isolation/durability hay cách election của mọi phiên bản. Khi thiết kế production phải kiểm chứng cấu hình, API, topology và failure model từ tài liệu chính thức.

## 1. Thống nhất trạng thái là thống nhất điều gì?

Có nhiều loại “thống nhất”:

| Mục tiêu | Ví dụ | Đòi hỏi gì? |
|---|---|---|
| **Thống nhất giá trị một key** | Cấu hình `featureEnabled=true` | Không trả lời mâu thuẫn với hợp đồng đọc/ghi |
| **Thống nhất quyền ghi** | Ai là leader của partition P? | Chỉ một authority hợp lệ được commit ghi mạnh |
| **Thống nhất thứ tự lệnh** | `Reserve`, rồi `Cancel` | Các bản sao áp dụng cùng thứ tự logic |
| **Thống nhất quyết định commit** | Transaction nhiều participants | Không nơi nào commit khi nơi khác coi đã abort |
| **Thống nhất membership** | Loại node hỏng, thêm node mới | Quorum cũ/mới chuyển đổi an toàn |
| **Hội tụ dữ liệu** | Replicas nhận update bất đồng bộ | Cuối cùng đạt trạng thái phù hợp theo merge rules |

Hai hàng cuối không đồng nghĩa nhau. **Eventual convergence** có thể làm các replica giống nhau về sau, nhưng không nhất thiết đã bảo vệ một quyết định trước đó được client xác nhận. **Consensus** nhấn mạnh tính nhất quán của quyết định/lịch sử trong failure model; khi không thể phối hợp, một số request phải chờ hoặc thất bại.

### 1.1. Ví dụ cấu hình mang ý nghĩa điều khiển

Một dịch vụ đặt lịch có `activeLeaderForRoom = booking-node-A`. Nếu mạng bị chia và phía kia tự đổi sang `booking-node-B`, hai worker có thể cùng xác nhận hai booking cho một phòng/khung giờ.

Chỉ việc cả hai đọc một cache “leader hiện tại” rồi đồng ý với chính mình không đủ. Quyền ghi phải được ràng buộc vào một giao thức hoặc nguồn có thẩm quyền mà cả hai không thể độc lập vượt qua.

### 1.2. Một bản sao dữ liệu đúng không nhất thiết có quyền ghi

Follower có thể đã chứa toàn bộ committed log nhưng không được phép tự commit một lệnh mới khi chưa có quyền leader/quorum. **Data freshness**, **role** và **write authority** là những thuộc tính khác nhau.

### 1.3. Một node có quyền leader không bảo đảm mọi lệnh đã durable

Quyền leader cho phép điều phối các lệnh ghi theo protocol; việc một lệnh được ACK lúc nào còn phụ thuộc **commit condition, replication và durability**. Một lệnh mới chỉ nằm trong buffer của leader không đồng nghĩa đã được toàn nhóm chấp nhận.

## 2. Vì sao lỗi phân tán khó hơn lỗi một máy?

Trong một chương trình đơn máy, nếu một thread không phản hồi thì ứng dụng có thể kiểm tra trạng thái cục bộ. Trong mạng phân tán, khi node B không trả lời, node A thường **không thể biết chắc nguyên nhân**:

- B đã crash.
- B còn sống nhưng mạng A–B bị partition.
- B đang pause vì GC hoặc IO stall.
- Gói tin tới B bị mất hoặc tới rất chậm.
- Phản hồi từ B bị mất dù B đã xử lý xong.
- DNS, proxy, connection pool hoặc load balancer đang lỗi.

### 2.1. Timeout là nghi ngờ, không phải bằng chứng chết

~~~text
T0: A gửi heartbeat tới B.
T1: Không có response trong 2 giây.
T2: A đánh dấu B "suspected down".
T3: B vẫn đang chạy, chỉ bị partition.
~~~

Nếu A và B dựa vào timeout cục bộ để tự tuyên bố mình là leader, chúng có thể cùng có quyền ghi. Vì vậy **failure detector** chỉ giúp kích hoạt election hoặc recovery, không thay thế các điều kiện an toàn của giao thức.

### 2.2. Partial failure

Một hệ nhiều node có thể gặp **lỗi một phần**: node A/B vẫn phục vụ, node C hỏng; network từ A tới B hoạt động nhưng B tới C chập chờn. Đây khác tình trạng toàn bộ máy ngừng hoạt động.

### 2.3. Network partition không cần node chết

~~~mermaid
flowchart LR
    subgraph LEFT["Phía mạng 1"]
      A["Replica A"]
      B["Replica B"]
    end
    subgraph RIGHT["Phía mạng 2"]
      C["Replica C"]
    end
    A <--> B
    A -. "mất liên lạc" .- C
    B -. "mất liên lạc" .- C
~~~

Node C vẫn có thể trả lời các client gần nó, nhưng không thể biết chắc liệu A/B đã chấp nhận những ghi mới hay chưa. Câu hỏi “có tiếp tục ghi được không?” phải được trả lời theo **quyền ghi và hợp đồng consistency**, không chỉ theo tiến trình còn sống.

### 2.4. Thời gian hệ thống không đáng tin tuyệt đối

Clock skew, NTP step, pause dài hoặc đo thời gian ở hai máy khác nhau có thể làm một lease tự chế mất an toàn. Giao thức lease dựa trên thời gian cần giả định rõ về clock và cách thực thi fencing.

## 3. Hai mục tiêu nền tảng: safety và liveness

**Safety:** Không xảy ra trạng thái xấu bị cấm. Ví dụ, hai lệnh được ghi nhận là committed không tạo hai lịch sử mâu thuẫn đối với cùng một replicated state machine.

**Liveness:** Hệ có thể tiến triển và hoàn tất quyết định khi những điều kiện cần thiết cuối cùng được thỏa. Ví dụ, khi một quorum có thể trao đổi thông điệp ổn định đủ lâu, cluster có thể bầu leader mới và commit các lệnh mới.

| Thuộc tính | Câu hỏi | Ví dụ |
|---|---|---|
| Safety | Điều sai có thể xảy ra không? | Có hai leader cùng commit hai giá trị xung đột? |
| Liveness | Hệ có thể tiếp tục không? | Sau lỗi một node, còn quorum để ghi? |
| Availability | Yêu cầu được hoàn tất ở đâu/khi nào? | Minority có thể đáp ứng strong write? |
| Durability | Quyết định đã ACK có sống qua lỗi? | Ghi commit có còn sau election? |

### 3.1. Ưu tiên safety có thể giảm availability

Với một consensus group ba voting replicas, nếu chỉ còn một node có thể liên lạc với chính nó, node này thường **không đủ quorum để commit strong writes**. Từ chối ghi lúc ấy giữ safety, không nhất thiết là bug.

### 3.2. Ưu tiên availability có thể yêu cầu bảo đảm yếu hơn

Một hệ có thể vẫn trả dữ liệu local cũ hoặc nhận **ý định PENDING** trong partition. Nhưng không được trả `RESERVED` như thể ghi đã committed nếu nguồn có thẩm quyền chưa xác nhận.

### 3.3. Không thể giải bằng retry vô hạn

Nếu quorum chưa có, gửi lệnh `COMMIT` mỗi 10 ms không tạo thêm votes hợp lệ. Retry storm còn làm tăng tải và kéo dài recovery. Cần backoff, timeout budget và trạng thái công khai chính xác.

## 4. CAP đặt bài toán vào ngữ cảnh nào?

Trong cách phát biểu CAP kinh điển:

- **C (Consistency)** liên quan tới single-copy/linearizable behavior của những thao tác được xét.
- **A (Availability)** yêu cầu node không lỗi trả phản hồi hợp lệ cho các request trong mô hình.
- **P (Partition tolerance)** xét khả năng mạng chia tách hoặc trì hoãn/làm mất thông điệp vô hạn.

Khi mạng phân hoạch, không thể vừa cho **mọi phía độc lập hoàn tất những thao tác mâu thuẫn**, vừa giữ một lịch sử linearizable duy nhất. Hệ phải giới hạn availability của thao tác mạnh hoặc nới lỏng tính nhất quán/đưa vào bước hòa giải.

### 4.1. CAP không phải “chọn hai ô rồi xong”

Một cluster có thể:

~~~text
Majority side:
    strong write -> accepted and committed
    strong read  -> available

Minority side:
    strong write -> unavailable
    stale read   -> may be available if API supports it
~~~

**Cùng hệ thống** có thể có nhiều chế độ theo từng API và failure state. Không gắn nhãn CP/AP bất biến cho mọi thao tác.

### 4.2. CAP consistency khác ACID consistency

ACID C là invariant/constraint ở tầng transaction. CAP C liên quan thứ tự và visibility của các operation phân tán. Một key–value store có linearizable single-key operations vẫn không tự cung cấp transaction nguyên tử giữa Account A và Account B.

### 4.3. Không có partition vẫn có đánh đổi

Đồng thuận cần network round trips, replicated log, fsync và election. Ngay cả lúc mạng khỏe, bảo đảm mạnh có chi phí latency/throughput. PACELC là một cách tư duy bổ sung: khi có partition xét availability–consistency, còn khi mạng bình thường vẫn có consistency–latency tradeoff.

## 5. Trực giác về giới hạn bất đồng bộ: FLP

Trong mô hình mạng **hoàn toàn bất đồng bộ**, không có chặn trên được đảm bảo cho độ trễ thông điệp hay tốc độ tiến trình. Kết quả FLP nói rằng một giao thức đồng thuận **tất định** không thể bảo đảm luôn kết thúc trong tất cả các lịch thực thi nếu có khả năng xảy ra chỉ một crash, cùng các giả định của bài toán.

### 5.1. FLP không có nghĩa consensus là bất khả thi trong thực tế

Nó chỉ ra giới hạn của **bảo đảm termination vô điều kiện** trong mô hình ấy. Các hệ thực tế dùng:

- Giả định **partial synchrony**: sau một thời điểm nào đó độ trễ đủ ổn định.
- Timeouts và failure detectors để kích hoạt election.
- Randomization hoặc các cơ chế hỗ trợ progress.
- Quorum và giao thức giữ safety cả khi election bất ổn.

Một hệ có thể bị lặp election khi mạng chập chờn nhưng vẫn **không commit hai lịch sử trái nhau**.

### 5.2. Timeouts ảnh hưởng liveness nhiều hơn safety

Timeout quá ngắn có thể tạo leader flapping; timeout quá dài làm failover chậm. Nhưng việc đổi timeout không được làm mất quy tắc voting, log freshness, term hoặc fencing đã thiết kế để giữ safety.

### 5.3. Không “phát hiện chắc chắn B chết” chỉ bằng heartbeat

Trong mạng bất đồng bộ, A không phân biệt được B chết với response của B bị delay rất lâu. Sự nghi ngờ dùng để **bắt đầu election**, không phải để tự cấp quyền commit một mình.

## 6. Replicated state machine: cách thống nhất lịch sử thay vì chỉ giá trị

Một mô hình mạnh là **replicated state machine (RSM)**:

1. Các node giữ một trạng thái ban đầu tương thích.
2. Nhóm thống nhất một thứ tự log commands.
3. Mỗi node áp dụng **cùng commands theo cùng thứ tự**.
4. Nếu hàm áp dụng state là tất định, kết quả logic của các node nhất quán khi áp dụng cùng prefix log.

~~~mermaid
flowchart LR
    CLIENT["Client commands"] --> CONS["Consensus / ordered log"]
    CONS --> A["Replica A: Apply 1,2,3"]
    CONS --> B["Replica B: Apply 1,2,3"]
    CONS --> C["Replica C: Apply 1,2,3"]
~~~

Ví dụ:

~~~text
Committed log:
  index 21: CreateOrder(O-100)
  index 22: ConfirmOrder(O-100)
  index 23: CancelOrder(O-101)

Replica A applies 21,22,23.
Replica B applies 21,22,23.
Replica C currently applies through 22, then catches up.
~~~

### 6.1. Đồng thuận trên thứ tự lệnh

Đôi khi hai mutations giao hoán, nhưng nhiều lệnh không:

~~~text
SetBalance(100)
Withdraw(80)
~~~

khác với:

~~~text
Withdraw(80)
SetBalance(100)
~~~

Chỉ đồng thuận “cuối cùng balance giống nhau” sau hòa giải không đủ nếu mỗi client đã được hứa một kết quả theo thứ tự khác nhau.

### 6.2. State machine phải tất định ở những chỗ quyết định

Sai:

~~~text
Apply CreateOrder:
    total = remotePricingApi.getCurrentPrice()
    id = randomUUID()
    timestamp = localClock.now()
~~~

Mỗi replica có thể nhận giá, UUID và thời điểm khác nhau khi replay cùng command.

Tốt hơn:

~~~text
Command carries:
    stable orderId
    validated pricing terms or version
    agreed amount
    deterministic transition parameters
~~~

Logic phụ thuộc external service hoặc random value cần được **xử lý và ghi nhận quyết định theo protocol** trước hoặc ngoài state machine, không tự phát sinh không đồng bộ khi apply.

### 6.3. Determinism không thay cho business validation

Ba replica có thể nhất quán cùng áp dụng một phép trừ kho sai và cùng tạo stock âm. Consensus bảo vệ **thống nhất lịch sử**, không tự sửa quy tắc nghiệp vụ. Check-and-update phải được thiết kế nguyên tử/serializable theo domain invariant.

### 6.4. Không phải mọi NoSQL sử dụng RSM cho mọi dữ liệu

Một số hệ có consensus cho metadata/leader election nhưng dùng replication protocol khác cho data. Phải phân biệt **consensus control plane** với **data replication/transaction guarantees**.

## 7. Quorum: vì sao đa số giúp các quyết định giao nhau?

Trong nhóm \(N\) voting members ổn định, majority:

\[
Q=\left\lfloor\frac{N}{2}\right\rfloor+1
\]

Ví dụ:

| Voting members | Majority | Có thể thiếu tối đa bao nhiêu voters mà vẫn có majority? |
|---:|---:|---:|
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

Hai tập majority của cùng một membership phải giao nhau:

~~~text
N = 5
Q1 = {A, B, C}
Q2 = {C, D, E}
Q1 ∩ Q2 = {C}
~~~

Nếu kết hợp với quy tắc vote/log đúng, tính giao nhau giúp đảm bảo quyết định đã commit không bị một majority khác bỏ qua.

### 7.1. Tính giao nhau chưa tự đủ

Nếu C biết committed entry mới nhưng sẵn sàng bỏ phiếu cho ứng viên có log thiếu entry ấy, quorum overlap một mình chưa bảo vệ lịch sử. Giao thức cần election/log eligibility, durable votes/terms và commit rules.

### 7.2. Quorum không nhất thiết là đa số mọi node vật lý

Phân biệt:

- Voting members với data-bearing members.
- Một consensus group với toàn cluster.
- Một region với global topology.
- Quorum cho election với quorum cho data write.
- Majority quorum với flexible quorum có điều kiện khác.

Không áp công thức N=5 cho toàn hệ có 5.000 nodes nếu mỗi shard thực sự chỉ có 3 voters.

### 7.3. Witness/arbiter

Một member chỉ bỏ phiếu có thể giúp election nhưng không chứa dữ liệu application đầy đủ. **Voting majority** không đương nhiên là **số bản sao dữ liệu bền** đủ để cứu acknowledged writes khi mất data node.

### 7.4. Hai phía partition không thể đều có majority của cùng group

Với N=3, phía A/B có 2 votes, phía C có 1. Không thể cùng lúc có hai tập voting majority tách rời trong membership cố định. Nếu một hệ cho phép cả hai phía tự commit strong writes bất chấp quy tắc ấy, nó đang áp dụng mô hình khác hoặc đã phá invariant quorum.

## 8. Bầu leader không đơn giản là chọn node khỏe nhất

Với một nhóm replication có leader:

~~~text
Term 7:
    Leader A
    Followers B, C

A becomes unreachable.

Term 8:
    B and C can communicate.
    A is isolated.
    Eligible candidate receives a valid majority vote.
~~~

Chọn leader mới phải đảm bảo **thẩm quyền** và **tính liên tục của committed history**.

### 8.1. Quyền ghi gắn với term/epoch

Term hoặc epoch là thế hệ leadership. Các node từ chối message không hợp lệ thuộc term cũ khi đã biết term mới, theo protocol. Leader cũ muốn tiếp tục commit phải thỏa điều kiện quorum/term hiện hành, không chỉ vì trước đó nó từng là leader.

### 8.2. Không được bầu leader thiếu committed history

Một candidate có latency thấp nhưng log đã quá cũ không đủ điều kiện nếu election làm mất committed entries. Giao thức như Raft có quy tắc xem **last log term và last log index** để xác định up-to-date log.

### 8.3. Election và data readiness là hai mốc

Node có thể vừa được bầu leader nhưng cần áp dụng các committed log entries trước khi phục vụ reads theo mode mạnh. `leaderElected=true` không tương đương `allStrongReadsReady=true`.

### 8.4. Những entry chưa commit có thể bị thay

Một old leader có thể có log entry chưa đạt commit rule. New leader có thể ghi đè/truncate phần đuôi chưa commit theo protocol. Vì thế ACK **local append** không có cùng nghĩa với ACK **committed**.

## 9. Ví dụ ba replicas khi một node bị cô lập

Ban đầu:

~~~text
Replication group: A, B, C
Leader: A
Committed index: 40
Client writes to A.
~~~

Mạng bị chia thành `{A}` và `{B,C}`. A không chết, vẫn có thể nghe client.

~~~mermaid
sequenceDiagram
    participant U1 as Client near A
    participant A as Old leader A
    participant B as Replica B
    participant C as Replica C
    participant U2 as Client near B
    Note over A,C: Partition: A cannot contact B/C
    U1->>A: Write W41
    A->>A: May locally append
    Note over A: No majority, cannot commit strong write
    B->>C: Start election in newer term
    C-->>B: Valid vote
    Note over B,C: B becomes leader if protocol allows
    U2->>B: Write W42
    B->>C: Replicate W42
    C-->>B: ACK
    B-->>U2: Commit success
~~~

### 9.1. Điều gì được phép ở A?

A có thể giữ một log entry chưa commit trong memory/disk, nhưng **không được báo thành công của một strong committed write** nếu nó không đáp ứng quorum. Tùy API, nó có thể trả timeout, lỗi unavailable hoặc trạng thái ambiguous; không được tự nhận thành công vì `append` xong.

### 9.2. Điều gì xảy ra khi mạng hồi phục?

A nhận term/leadership mới, đồng bộ với lịch sử có thẩm quyền và xử lý những uncommitted entries theo protocol. Một uncommitted entry của A có thể bị bỏ. Nếu client đã nhận timeout, cần đối soát request theo `commandId`.

### 9.3. Không thể giả định A đã chết để bỏ qua A vĩnh viễn

Nếu failure chỉ là partition tạm thời, A sẽ trở lại. Hệ phải **fence old authority** và đồng bộ log; không để A xuất hiện rồi tiếp tục trả ACK như leader cũ.

### 9.4. Khi B/C cũng mất kết nối?

Không phía nào có quorum ổn định. Hệ có thể không commit strong writes, giữ safety nhưng giảm liveness/availability. Retry liên tục không thay đổi thực tế mạng.

## 10. Safety của replicated log: committed, appended và applied

Một entry có thể có các mốc:

~~~text
received by leader
  -> appended to local log
  -> replicated to some followers
  -> committed under consensus rule
  -> applied to local state machine
  -> visible to an eligible read
~~~

Không được đánh đồng các mốc:

| Mốc | Khái niệm | Chưa bảo đảm |
|---|---|---|
| Received | Node nhận request | Write được giữ bền |
| Appended | Có entry trong log | Entry đã committed |
| Replicated | Follower nhận entry | Commit rule đã đạt |
| Committed | Đạt quy tắc consensus | Mọi follower đã applied |
| Applied | State machine đã chuyển trạng thái | Cache/index ngoài DB đã cập nhật |
| Client ACK | Client nhận response | Mức chắc chắn phụ thuộc setting/API |

### 10.1. Ghi chưa committed có thể biến mất

Nếu node trả ACK local append trước quorum, client có thể thấy `SUCCESS` nhưng entry không nằm trong lịch sử mà leader mới chọn. Cần đọc **write acknowledgment contract** chứ không suy từ HTTP 200.

### 10.2. Committed entry không được mất sau election hợp lệ

Trong một consensus protocol an toàn và failure model đã công bố, entry đã được committed phải hiện diện trong các leader hợp lệ về sau, kể cả nếu một follower đang tạm lag/apply chậm.

### 10.3. Durability của votes và log là điều kiện cần

Nếu node bỏ phiếu/ACK log nhưng không lưu bền metadata cần thiết rồi tất cả cùng mất điện, giả định protocol có thể bị vi phạm. Không suy rằng majority network responses tự đủ chống mọi dạng power loss.

### 10.4. Leader completeness không chỉ dựa trên số log index

Hai candidates có lastIndex=100 nhưng lastTerm khác nhau. Quy tắc eligibility có thể ưu tiên term mới hơn, không đơn thuần là node có nhiều records. Phải dùng đúng protocol, không viết “max(index) wins” tự chế.

## 11. Raft: mô hình trực quan về đồng thuận log

**Raft** là một giao thức consensus tổ chức quanh leader, term, log replication và election.

Một bản ghi log khái niệm:

~~~text
LogEntry:
    index
    term
    command
~~~

Giao thức gồm:

1. Leader được bầu theo term thông qua majority votes hợp lệ.
2. Leader tiếp nhận và append commands.
3. Leader truyền log tới followers.
4. Dựa trên quy tắc commit, leader công bố committed prefix.
5. Các replicas áp dụng committed entries theo cùng thứ tự.
6. Follower bắt kịp khi lag hoặc phục hồi.

### 11.1. Vote một lần trong term theo quy tắc

Một voter không được tùy tiện cấp quyền cho hai ứng viên khác nhau trong cùng term. Việc lưu bền vote/term theo protocol giúp tránh cấp trùng quyền sau crash/restart.

### 11.2. Log matching

Nếu hai logs có entry cùng index và term theo giả định protocol, những entry trước đó phải khớp. Cơ chế điều chỉnh conflicting suffix giúp follower trở lại một committed history hợp lệ.

### 11.3. Leader completeness

Một entry đã committed phải xuất hiện trong leaders của các term tiếp theo. Quorum overlap chỉ là một thành phần; election rules và commit rules làm thành cơ chế bảo vệ.

### 11.4. Commit entry từ term cũ có nuance

Trong Raft, không đơn giản lấy mọi entry của term cũ chỉ vì thấy ở majority rồi lập tức nâng commit index. Quy tắc commit chú ý entry thuộc current term và các điều kiện liên quan để suy ra committed prefix an toàn.

### 11.5. Read mạnh cần đúng protocol

Đọc state của leader hiện tại không tự bảo đảm linearizable nếu leader đã mất quyền nhưng chưa biết. Một số triển khai dùng read-index/quorum confirmation hoặc leader lease có giả định an toàn riêng. Không tự biến local read thành strong read chỉ bằng `isLeader=true` cũ.

## 12. Paxos: đồng thuận không nhất thiết trông giống Raft

**Paxos** giải bài toán các participants thống nhất một giá trị/decision trong những điều kiện giả định cụ thể. Một trực giác phổ biến:

- **Proposer** đề xuất giá trị với proposal/ballot number.
- **Acceptors** tham gia quá trình promise/accept theo quy tắc.
- **Learners** biết giá trị đã được lựa chọn.
- Các quorum phù hợp giao nhau để không thể chọn hai giá trị mâu thuẫn cho cùng một instance.

### 12.1. Single-decree và nhiều lệnh

Một instance có thể chọn một giá trị. Để tạo replicated log nhiều entries cần một cơ chế multi-instance/multi-decree (ví dụ Multi-Paxos) và các quy tắc ordering/leadership tương ứng.

### 12.2. Ballot/term không phải timestamp dữ liệu

Proposal number phải có ordering theo protocol, không chỉ dùng wall-clock timestamp từng máy. Timestamp lớn nhất theo đồng hồ không tự chứng minh candidate có history đúng.

### 12.3. Raft và Paxos cùng giải nhóm vấn đề

Cả hai hướng đều quan tâm đến **chọn một lịch sử/decision an toàn khi node có thể lỗi**. Chúng không thể thay thế một business transaction nếu dữ liệu nằm ngoài phạm vi consensus group, cũng không tự làm external effects exactly once.

### 12.4. Không suy equivalence của các triển khai

Các biến thể Raft/Paxos hoặc consensus nội bộ sản phẩm có những điều kiện commit, durability và membership khác nhau. Đừng chọn một câu giải thích từ Raft rồi áp nguyên xi lên mọi sản phẩm sử dụng từ “Paxos”.

## 13. Fencing: ngăn zombie leader và zombie worker

Ngay cả khi B được bầu leader mới, A có thể vẫn chạy và gửi lệnh ra hệ khác. Đây là trường hợp **zombie leader**.

Một cách bảo vệ là **fencing token** tăng đơn điệu:

~~~text
Owner A receives epoch = 21.
Owner B becomes new owner, epoch = 22.

Downstream resource:
    reject write with epoch < 22.
~~~

### 13.1. Lease timeout một mình không đủ

~~~text
A obtains lease for 10 seconds.
A pauses for 30 seconds.
Lease expires and B obtains authority.
A resumes, believing old operation can continue.
~~~

Nếu storage/downstream không xác minh fencing token, A vẫn có thể thực hiện một thao tác muộn sau khi B bắt đầu. Nguồn có thẩm quyền phải **enforce** token hoặc quy tắc term/epoch tương đương ở điểm ghi.

### 13.2. Fencing token phải đi tới nơi có side effect

Worker xử lý object storage hoặc message delivery có thể không đi qua database router. Nếu cần một owner duy nhất, các thao tác ở downstream cũng phải kiểm tra epoch hoặc áp dụng giao thức idempotent/conditional thích hợp.

### 13.3. Không tạo hai epoch song song

Một counter epoch trong hai cơ sở dữ liệu độc lập có thể cấp `22` ở hai phía partition. Epoch phải được sinh từ **nguồn có khả năng phối hợp và bảo vệ thứ tự**.

### 13.4. Fencing khác authorization

Token epoch chứng minh độ mới của quyền owner, không chứng minh user có quyền truy cập tenant khác. Vẫn cần xác thực, phân quyền và kiểm tra tenant scope.

## 14. Reconfiguration: thay đổi thành viên không được phá quyết định cũ

Cluster không tồn tại mãi với tập node cố định. Operator sẽ thêm, xóa, thay node, chuyển region hoặc đổi replication factor.

### 14.1. Rủi ro khi chuyển từ N=3 sang N=3 khác

~~~text
Old members: {A, B, C}
New members: {D, E, F}
~~~

Nếu hai nhóm tự hoạt động theo hai cấu hình không có protocol chuyển tiếp, old majority `{A,B}` và new majority `{D,E}` **không giao nhau**. Cả hai có thể tin mình có quyền quyết định.

### 14.2. Chuyển cấu hình an toàn

Giao thức consensus thường có quy tắc committed configuration, joint consensus hoặc một cơ chế chuyển đổi tương đương, để quyết định trong config mới không bỏ qua history đã commit ở config cũ.

Không tự chỉnh config file trên nhiều node để “cứu quorum” mà bỏ qua quy trình chính thức.

### 14.3. Thêm voter chưa catch up

Một node mới cần được đồng bộ và đạt điều kiện eligibility thích hợp trước khi tính như thành viên có thể giúp bảo vệ committed history. Chỉ thêm địa chỉ của nó vào cấu hình không làm nó có dữ liệu cần thiết.

### 14.4. Witness/arbiter cần hiểu data durability

Một voting witness có thể cấp vote nhưng không giữ toàn bộ application log. Khi thiết kế fault tolerance phải xét **có bao nhiêu data-bearing copies thực sự bền**, không chỉ số phiếu.

### 14.5. Recovery cần giữ committed prefix

Một follower được khôi phục từ snapshot cũ phải catch up những quyết định đã commit hoặc nhận snapshot trạng thái phù hợp; không được trở thành nguồn ghi mạnh khi còn thiếu history.

## 15. Đồng thuận và transaction: hai bài toán không đồng nghĩa

Một consensus group có thể cung cấp thứ tự bền cho các lệnh trên một shard. Nhưng transaction có thể cần commit atomically trên **hai nhóm shard độc lập**.

~~~text
Shard X: Order O-100.
Shard Y: Inventory SKU-A.

X consensus commits CreateOrder.
Y consensus commits DecrementStock.
~~~

Hai commits riêng **không tự tạo all-or-nothing**. Nếu X thành công còn Y thất bại, checkout có thể ở trạng thái dở dang.

### 15.1. Atomicity khác agreement

- **Consensus:** một group thống nhất decision/order trong phạm vi của nó.
- **Transaction atomic commit:** một tập thao tác được quyết định commit hoặc abort cùng nhau theo contract.
- **Isolation:** các transaction đồng thời được quan sát/commit theo mức nào.
- **Durability:** decision đã ACK sống qua failure model nào.

Một hệ có consensus ở replication layer nhưng chỉ hỗ trợ single-document atomic writes vẫn không tự có multi-document ACID.

### 15.2. Two-phase commit (2PC) khác consensus

Một transaction coordinator có thể yêu cầu participants:

~~~text
PREPARE:
    Participants persist prepared state / lock relevant resources.

DECISION:
    Coordinator chooses COMMIT or ABORT.

FINALIZE:
    Participants apply the decision.
~~~

2PC giải quyết atomic commit trong mô hình của nó, nhưng **coordinator mất liên lạc sau prepare** có thể làm participants phải chờ quyết định. Dùng consensus để sao chép durable decision/transaction metadata có thể tăng khả năng phục hồi coordinator; bản thân 2PC không thay thế mọi yêu cầu consensus.

### 15.3. Consensus không xóa write skew

Hai transactions snapshot-isolated trên hai records khác nhau có thể cùng commit và vi phạm invariant chung dù replication mỗi shard dùng consensus đúng. Cần serializable isolation, guard record hoặc thiết kế invariant owner phù hợp.

### 15.4. Saga không là một global transaction

Khi Order, Inventory và Payment thuộc nhiều service, có thể cần saga:

~~~text
Reserve inventory -> Confirm order -> Capture payment
                 -> compensate on failure
~~~

Saga dùng trạng thái workflow, idempotency, compensation và reconciliation. Nó không biến các bước đã commit thành một giao dịch nguyên tử toàn cục.

## 16. Quyền ghi ở nhiều shard: không có một leader toàn hệ

Một database có thể có hàng nghìn consensus groups:

~~~text
Shard P1: Leader A, followers B,C.
Shard P2: Leader D, followers E,F.
Shard P3: Leader B, followers C,D.
~~~

### 16.1. Leader theo partition

Một node có thể là leader của P1 nhưng follower của P3. Câu “node B là leader” không đủ thông tin; cần chỉ rõ **partition, epoch và membership**.

### 16.2. Một partition mất quorum không làm mọi partition mất quorum

Nếu P1 vẫn có A/B nhưng P2 bị mất D/E, strong writes trên P1 có thể còn, trên P2 có thể unavailable. Từ góc ứng dụng, một số khách hàng/keys gặp lỗi trong khi các tenant khác vẫn hoạt động.

### 16.3. Routing phải biết authority hiện hành

Client/SDK có thể cache leader per partition. Khi leader đổi, server trả redirect/not-leader/term mismatch theo protocol; client cập nhật route rồi xử lý retry đúng outcome. Không dùng một cache leader không có expiry/fencing làm nguồn chân lý.

### 16.4. Đổi shard key có thể đổi consensus scope

Khi di chuyển entity từ partition P1 sang P2, quyền ghi và transaction scope thay đổi. Migration phải đảm bảo một owner tại một thời điểm, data catch-up và route epoch; không chỉ copy record rồi đổi DNS.

## 17. Leaderless replication: bài toán hội tụ khác đồng thuận thứ tự toàn phần

Không phải NoSQL nào cũng có một leader cho mỗi key. Hệ **leaderless/Dynamo-style** có thể nhận write thông qua coordinator, gửi tới nhiều replicas rồi reconcile dữ liệu.

~~~mermaid
flowchart LR
    CL["Client"] --> CO["Coordinator"]
    CO --> R1["Replica A"]
    CO --> R2["Replica B"]
    CO --> R3["Replica C"]
    R1 -. "repair/anti-entropy" .- R2
    R2 -. "repair/anti-entropy" .- R3
~~~

### 17.1. N, R, W

Trong mô hình replica set cố định:

- N: replication factor.
- R: số replica responses phục vụ một read.
- W: số ACKs để một write đạt configured consistency level.

\[
R+W>N
\]

bảo đảm **tập read và write giao nhau** dưới giả định cùng membership và quorum được chọn đúng.

### 17.2. Quorum intersection chưa đủ có linearizability

Vẫn cần xét concurrent writes, conflict resolution, timestamps, sloppy quorum/hinted handoff, durability, topology changes và read repair. Một node thuộc giao tập có thể chưa đủ để quyết định giá trị nào đúng theo real-time order.

### 17.3. Last-write-wins có thể làm mất một quyết định nghiệp vụ

Nếu A ghi `Order=CONFIRMED`, B ghi `Order=CANCELED`, chọn timestamp lớn hơn có thể làm một phản hồi thành công bị phủ nhận. Hội tụ state cuối không chứng minh invariant đã được giữ tại mọi thời điểm.

### 17.4. CRDT là một chiến lược khác

Một số CRDT được thiết kế để merge các thay đổi độc lập theo quy tắc hội tụ mà không cần đồng thuận trên mọi operation. Phù hợp với counter/growing sets trong những ngữ nghĩa nhất định, nhưng không có nghĩa mọi invariant đều giải được:

~~~text
Counter increments can be merged.
But "do not exceed remaining stock" requires
additional authority/escrow/coordination.
~~~

Một CRDT counter cộng được từ hai region có thể cuối cùng hiển thị tổng 16, trong khi stock chỉ 10; merge đúng toán học không làm hai reservations đã hứa trở thành hợp lệ.

### 17.5. Leaderless vẫn có thể dùng consensus cho một số operations

Một hệ wide-column có thể dùng normal writes leaderless và conditional lightweight transaction (LWT) theo protocol Paxos-like trong phạm vi hỗ trợ. Không dán nhãn một sản phẩm “không đồng thuận” cho mọi API chỉ vì write path phổ biến là leaderless.

## 18. Multi-region: có thể vừa available vừa bảo vệ invariant bằng phân bổ quyền

Giả sử tổng tồn kho SKU-A là 10, hai region A và B bị partition.

~~~text
Region A sees stock=10.
Region B sees stock=10.

Each region independently accepts reserve 8.
=> total confirmed reservations = 16.
~~~

Nếu đòi invariant **không oversell**, không thể cho hai phía tự quyết định dựa trên cùng một bản sao tổng chưa được phân chia quyền.

### 18.1. Single-writer authority

Chọn region A làm authority cho SKU-A. Khi B không liên lạc được với A, B có thể trả `PENDING` hoặc unavailable cho reservation. Chọn consistency của invariant, giảm write availability của B trong partition.

### 18.2. Escrow/quota phân bổ trước

Có thể phân quyền:

~~~text
Region A gets 6 units.
Region B gets 4 units.
Total allocated authority = 10.
~~~

Mỗi region chỉ cấp trong quota được sở hữu; trong partition, không được lấy quota region khác nếu chưa chuyển quyền an toàn. Điều này tăng availability **cho thao tác trong quota cục bộ**, nhưng chi phí là quota không được dùng hết ở vùng khác.

### 18.3. Phân quyền không được double-allocate

Chuyển 2 units từ B sang A phải có protocol idempotent và quyết định một nguồn bền; nếu cả A/B đều tin sở hữu cùng 2 units, invariant lại bị phá.

### 18.4. Không tự kết luận từ tên “multi-region”

Multi-region replication có thể đồng bộ hoặc bất đồng bộ, single-writer hoặc multi-writer, conflict resolution khác nhau. Một write ACK ở một region không tự nghĩa đã được globally committed trên tất cả regions.

### 18.5. Thứ tự thực tại giữa regions

Ngay cả khi hai region hội tụ, thứ tự lệnh thực tế do client quan sát có thể không được tôn trọng nếu protocol chỉ eventual. Với yêu cầu global linearizability, phải xem contract về authority/quorum/real-time order.

## 19. Membership, region failure và quorum placement

Giả sử 5 voters:

~~~text
Region A: A1, A2, A3
Region B: B1, B2
Majority: 3/5
~~~

Nếu Region A mất toàn bộ, B chỉ có 2 votes: không đủ majority. Đây là một **hậu quả topology**; cluster có thể không commit strong writes dù B còn hai máy khỏe.

### 19.1. Bố trí theo failure domains

Cần xem AZ/rack/region/network routes, không chỉ số replicas. Nhiều votes cùng một nguồn điện tạo correlated failure.

### 19.2. Witness không thay data copy

Vị trí witness có thể giúp election, nhưng nếu witness không có application data, không thể dùng nó như một bản sao durable của Order sau khi các data nodes mất.

### 19.3. Async DR khác consensus group trải vùng

Một primary cluster replicate async sang DR cluster khác không có chung quorum commit/election. Khi primary mất, DR có thể chưa có acknowledged writes gần đây. Cần RPO contract, reconciliation và failback plan riêng.

### 19.4. RPO và RTO

- **RPO:** mức mất dữ liệu chấp nhận được sau loại lỗi xác định.
- **RTO:** thời gian mục tiêu để dịch vụ phục vụ đúng trở lại.

Quorum consensus trong một failure model có thể cho RPO mạnh hơn local-only ACK, nhưng có thể giảm availability/tăng latency khi mất quorum. RTO gồm detection, election, catch-up, routing, apply readiness và client recovery.

## 20. Unknown commit outcome: client không biết quyết định cuối

Giả sử:

~~~text
T0: Client gửi ConfirmOrder(commandId=C-100).
T1: Leader tiếp nhận.
T2: Quorum commits C-100.
T3: Leader crash trước khi gửi ACK tới client.
T4: Client thấy timeout.
T5: New leader tiếp tục phục vụ.
~~~

Client không thể suy:

~~~text
timeout -> chắc chắn transaction rollback
~~~

Quyết định có thể đã bền trên committed log dù response bị mất.

### 20.1. Stable commandId

~~~json
{
  "commandId": "confirm-order-100",
  "orderId": "O-100",
  "expectedVersion": 7,
  "operation": "CONFIRM"
}
~~~

Retry cùng ý định phải giữ `commandId` và immutable payload. Nguồn có thẩm quyền cần lưu hoặc tra cứu outcome của command theo cơ chế idempotency phù hợp.

### 20.2. Đối soát bằng read đủ mạnh

Một read từ eventual secondary/index không thấy commandId **không phải bằng chứng** command chưa commit. Phải tra trong nguồn có authority và consistency phù hợp với quyết định cần xác nhận.

### 20.3. Phân loại kết quả

| Tình huống | Biết đã commit? | Hướng xử lý |
|---|---|---|
| ACK committed thành công | Có | Trả kết quả cuối |
| Abort/conflict đã xác nhận | Biết chưa commit | Có thể retry toàn unit of work theo policy |
| Business rule không đạt | Không commit như yêu cầu | Trả business rejection |
| Mất response khi commit | Không | Resolve theo commandId/protocol |
| Không có quorum để tra cứu | Chưa rõ | Trả PENDING/UNKNOWN, đối soát khi authority phục hồi |

### 20.4. Consensus không tạo exactly-once external effects

Một Payment worker có thể đọc cùng committed event hai lần sau crash/restart. Dù event được ghi đúng một lần vào replicated log, lời gọi HTTP tới gateway có thể xảy ra lặp. Cần `paymentId`, gateway idempotency và reconciliation.

## 21. Ví dụ Java: hợp đồng quyền ghi có fencing

Mã sau là **interface thiết kế**, không phải triển khai consensus. Nó minh họa application phải làm rõ quyền owner, thời điểm ACK và việc đối soát.

~~~java
public record Command(
    String commandId,
    String tenantId,
    String entityId,
    String action,
    long expectedVersion
) {}

public record AuthorityLease(
    String partitionId,
    long epoch,
    String ownerId
) {}

public record CommitReceipt(
    String commandId,
    String partitionId,
    long committedVersion,
    long authorityEpoch
) {}

public sealed interface CommandOutcome
    permits CommandOutcome.Committed,
            CommandOutcome.Rejected,
            CommandOutcome.Pending {

    record Committed(CommitReceipt receipt)
        implements CommandOutcome {}

    record Rejected(String reason)
        implements CommandOutcome {}

    record Pending(String commandId)
        implements CommandOutcome {}
}

public interface AuthoritativeCommandStore {
    CommandOutcome apply(
        Command command,
        AuthorityLease authority
    );

    // Must consult an authoritative, sufficiently consistent source.
    CommandOutcome resolveByCommandId(String commandId);
}
~~~

### 21.1. Fencing phải được kiểm tra tại commit boundary

~~~java
public final class CommandService {
    private final AuthoritativeCommandStore store;

    public CommandService(AuthoritativeCommandStore store) {
        this.store = store;
    }

    public CommandOutcome execute(
        Command command, AuthorityLease currentAuthority
    ) {
        CommandOutcome outcome =
            store.apply(command, currentAuthority);

        if (outcome instanceof CommandOutcome.Pending) {
            return store.resolveByCommandId(command.commandId());
        }
        return outcome;
    }
}
~~~

**Cảnh báo quan trọng:** Việc truyền `AuthorityLease` vào method **không tự tạo fencing**. Implementation của `store.apply` phải từ chối epoch lỗi thời tại nguồn ghi có thẩm quyền, dùng một giao thức hoặc primitive được DB thực sự hỗ trợ. Nếu `resolveByCommandId` không thể xác định outcome ngay, nó có thể tiếp tục trả `Pending`; workflow cần xử lý sau đó một cách bền vững.

### 21.2. Không đưa authority vào biến global tùy tiện

Nếu một `AtomicLong currentEpoch` chỉ tồn tại trong memory của service, hai process bị partition có thể đều có giá trị riêng và tự nhận quyền ghi. Epoch cần gắn với một quyết định hoặc authority source có contract an toàn.

### 21.3. Không tự tạo ID khác khi retry

Một lệnh `INCREMENT` có thể đã commit nhưng client timeout. Đổi sang `commandId` khác ở lần retry có thể áp dụng hai lần. Dùng stable IDs và lưu kết quả để trả lại cho cùng command.

### 21.4. Nghiệp vụ vẫn cần điều kiện

`expectedVersion` bảo vệ state transition theo optimistic concurrency nếu implementation kiểm tra nó atomically. Consensus không ngăn business code cố `CONFIRM` một Order đã `CANCELED` trừ khi invariant được mã hóa và bảo vệ trong apply transaction.

## 22. Ví dụ Java: replicated state machine thuần chức năng

Phần logic state machine nên có đầu vào và trạng thái rõ:

~~~java
import java.util.Map;
import java.util.HashMap;

public record OrderState(String status, long version) {}

public record OrderCommand(
    String commandId,
    String orderId,
    String expectedStatus,
    String newStatus
) {}

public final class OrderStateMachine {
    private final Map<String, OrderState> orders = new HashMap<>();
    private final Map<String, String> outcomes = new HashMap<>();

    // Called by one ordered state-machine apply loop.
    public String apply(OrderCommand c) {
        String previous = outcomes.get(c.commandId());
        if (previous != null) {
            return previous;
        }

        OrderState current = orders.getOrDefault(
            c.orderId(), new OrderState("PENDING", 0)
        );

        String outcome;
        if (!current.status().equals(c.expectedStatus())) {
            outcome = "REJECTED_STATE_CHANGED";
        } else {
            orders.put(
                c.orderId(),
                new OrderState(c.newStatus(), current.version() + 1)
            );
            outcome = "COMMITTED";
        }
        outcomes.put(c.commandId(), outcome);
        return outcome;
    }

    public OrderState get(String orderId) {
        return orders.get(orderId);
    }
}
~~~

Đây chỉ là **một state machine trong memory** để minh họa deterministic apply và command dedupe. Bản thân class không cung cấp thread safety, durable log, consensus, authentication, snapshot/recovery hoặc transaction. Trong hệ thật, `apply` được gọi tuần tự bởi ordered log executor, và state lẫn dedupe metadata phải được lưu/khôi phục cùng một lịch sử bền.

### 22.1. Vì sao lưu outcomes?

Khi request trùng `commandId` được log hoặc gateway gửi lại, state machine có thể trả kết quả cũ thay vì chuyển trạng thái thêm lần nữa. Nhưng lưu outcomes in-memory sẽ mất sau restart; cần persistent snapshot/log replay hoặc store durable tương ứng.

### 22.2. Kết quả business phụ thuộc thứ tự log

Nếu `Confirm` trước `Cancel`, kết quả khác `Cancel` trước `Confirm` theo quy tắc transition. Các replicas cùng áp dụng **một thứ tự** để đi tới cùng state.

### 22.3. Non-determinism cần được kiểm soát

Không gọi `System.currentTimeMillis()` hoặc `UUID.randomUUID()` trong mỗi replica khi apply nếu giá trị ảnh hưởng state. Nếu cần timestamp/id, đưa một giá trị đã được quyết định vào command cùng chính sách validate thích hợp.

### 22.4. Không nhầm replay với external effect

Replay log sau restart không được tự động gửi lại email/charge từ trong `apply`. Outbox/event worker cần idempotency và checkpoint riêng.

## 23. Lỗi khiến hệ không đạt agreement hoặc làm progress gián đoạn

| Failure | Nguy cơ | Cách tiếp cận |
|---|---|---|
| Node crash | Thiếu votes / thiếu bản sao | Quorum còn lại, recovery log |
| Network partition | Hai phía nhìn khác nhau | Fencing, chỉ quorum authority commit |
| Message delay | Election chập chờn | Timeouts, retry, partial synchrony |
| Lost ACK | Client không biết commit | Stable commandId và reconciliation |
| Stale leader | Zombie writer | Term/epoch enforcement |
| Stale read | Follower chưa applied | Read consistency/routing |
| Log corruption | State có thể không phục hồi | Checksums, backups, durable storage |
| Membership sai | Quorums không còn giao nhau | Safe reconfiguration |
| Clock skew | Lease/timestamp sai | Không tự dùng wall-clock làm authority |
| Region outage | Không đủ voters / mất async data | Placement, RPO/RTO, DR |
| SDK retry trùng | Double business effect | Idempotency và bounded retry |
| Hot consensus group | Contention, p99 cao | Partitioning/ownership/quota |

### 23.1. Crash-stop khác Byzantine

Phần lớn các giao thức consensus phổ biến trong database NoSQL thương mại giả định node có thể crash hoặc network lỗi, nhưng **không phải chống lại node cố ý gửi thông tin sai theo Byzantine fault model**. Nếu threat model yêu cầu Byzantine tolerance, cần giao thức và quorum assumptions khác.

### 23.2. Disk failure khác process kill

Kill tiến trình không chứng minh log mất khi power loss. Để kiểm tra durability cần fault model storage phù hợp và môi trường được cấp phép.

### 23.3. Một node đọc sai chưa chắc consensus sai

Nếu read API cho phép đọc follower lag/local stale, việc trả giá trị cũ có thể đúng contract. Cần so committed state với read consistency thực trước khi kết luận có hai committed histories mâu thuẫn.

## 24. Các ví dụ NoSQL cần đọc theo từng đường API

| Hệ/họ | Cơ chế liên quan | Không được suy ra |
|---|---|---|
| **etcd và KV kiểu Raft** | Consensus log, election, quorum, tuyến đọc mạnh/yếu | Mọi local read đều linearizable |
| **MongoDB replica set** | Primary election, replication, write/read concerns, rollback | ACK từ primary luôn sống qua mọi election |
| **Cassandra/ScyllaDB** | Leaderless replication cho nhiều writes, LWT/Paxos-like cho conditional operations | `QUORUM` của normal write là globally serializable transaction |
| **DynamoDB** | Managed replication, conditional/transaction APIs, global table modes | Một regional ACK tự là global consensus commit |
| **Redis primary–replica** | Async replication, promotion, persistence và các lệnh hỗ trợ | `WAIT` tự biến replication thành consensus commit |
| **Cosmos DB for NoSQL** | Account/region consistency, write region mode, transaction scope | Strong read level mở rộng atomicity ra mọi partition |
| **Couchbase** | Active/replica, durability levels, transactions, failover | Mọi timeout luôn có outcome abort chắc chắn |

### 24.1. Consensus có thể nằm ở control plane

Một database có thể dùng consensus để thống nhất **metadata hoặc topology**, trong khi data path được replicate theo cơ chế khác. Vì vậy “sản phẩm dùng Raft” không đủ để khẳng định **mọi application write** đều quorum-committed theo Raft.

### 24.2. MongoDB

Primary election và write concern là hai câu hỏi khác nhau. Một write được ACK ở mức local/primary có thể có failure window khác write concern majority theo contract. Read concern/read preference còn quyết định reader có thấy trạng thái mới ngay không. Để đánh giá acknowledged write qua failover, phải xét đúng topology, journaling, election và rollback semantics.

### 24.3. Cassandra/ScyllaDB

Normal writes trong mô hình leaderless có thể dùng nhiều consistency levels; một conditional update `IF` dùng LWT/serial consistency theo scope riêng. Không mô tả mọi thao tác CQL như một consensus log toàn cluster.

### 24.4. DynamoDB và global modes

Transaction/conditional write có bảo đảm ở phạm vi API hỗ trợ; cross-region replication và conflict resolution còn phụ thuộc mode triển khai. Không lấy regional strong read hoặc ACK làm bằng chứng multi-region inventory invariant được bảo vệ.

### 24.5. Redis

Một lệnh/script atomic trên primary không có nghĩa follower đã nhận hoặc đã fsync. Khi follower được promote sau crash primary, có thể có acknowledged local writes chưa được sao chép. Persistence và replication ACK phải được đọc riêng; fencing/idempotency không thay thế lựa chọn durability thích hợp.

### 24.6. Cosmos DB/Couchbase

Các mức consistency, transaction, durability và failover được cung cấp theo tài nguyên/chế độ/SDK cụ thể. Không tự dùng từ consensus để bỏ qua logical partition limits, multi-region conflict policy hoặc ambiguous commit outcomes.

## 25. Test: chứng minh hai phía không cùng commit lịch sử trái nhau

Một test hữu ích phải ghi lịch sử request và kết quả thay vì chỉ kiểm tra cụm sau khi hồi phục.

~~~text
Before partition:
    agree current epoch, committed version/index.

Inject partition:
    majority side and minority side cannot communicate.

During partition:
    submit conflicting commands on both sides.
    capture every ACK, timeout and error.

After heal:
    recover authoritative committed history.
    compare ACKed commands and safety invariant.
~~~

### 25.1. Expected với strong consensus group

Trong một nhóm có majority rules phù hợp, hai phía tách rời không được **đồng thời** commit những quyết định xung đột với cùng log index/authority. Phía minority có thể từ chối hoặc chờ.

### 25.2. Không xem PENDING là committed

Nếu minority lưu yêu cầu vào một durable queue riêng, response `202 PENDING` chỉ xác nhận **tiếp nhận ý định**. Không được báo `CONFIRMED` khi global authority chưa commit.

### 25.3. Phải ghi cả unknown outcomes

Một client timeout có thể đã commit trước khi mất response. Không đặt nó vào nhóm “chắc chắn thất bại”; đối soát theo commandId và committed state.

### 25.4. Fencing old leader

Sau election, cố gửi write tới old leader/worker còn chạy. Xác minh nguồn có thẩm quyền từ chối stale term/epoch, kể cả khi client giữ connection pool cũ.

### 25.5. Test lagging candidate

Tạo follower thiếu uncommitted hoặc committed log rồi kích hoạt election trong môi trường test. Kiểm tra candidate eligibility/catch-up theo giao thức, không tự giả định chọn node có ping thấp nhất.

### 25.6. Test đồng hồ lệch

Nếu sản phẩm dùng lease, thử network delay/pause dài/clock offsets trong fault model được cho phép. Kiểm tra lease và downstream fencing, không chỉ timeout ở client.

### 25.7. Test reconfiguration

Chuyển membership theo phương thức chính thức khi có write workload, rồi chèn crash/partition. Kiểm tra committed history không bị split khi quorum chuyển thế hệ.

### 25.8. Không thử chaos bừa trên production

Phá network, kill leader, làm đầy disk hoặc giả lập mất điện phải diễn ra trên môi trường được cấp quyền, có dữ liệu giả, guardrails và rollback. Ghi rõ fault model để không suy quá mức từ test.

## 26. Java/JUnit: khung kiểm thử authority và ACK

Một integration-test adapter:

~~~java
public interface ConsensusContractTestAdapter {
    void resetNamespace(String namespace);

    WriteOutcome write(
        String namespace,
        String commandId,
        String key,
        String value
    );

    void isolateFormerLeaderFromMajority();
    void recoverAndStabilize();

    // Must read from an authoritative, contract-appropriate path.
    String authoritativeRead(String namespace, String key);
}

public enum WriteOutcome {
    ACK_COMMITTED,
    KNOWN_REJECTED,
    UNKNOWN
}
~~~

JUnit 5 skeleton:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import java.util.LinkedHashMap;
import org.junit.jupiter.api.Test;

class ConsensusWriteSafetyTest {
    private final ConsensusContractTestAdapter db =
        TestEnvironment.consensusAdapter();

    @Test
    void committedAcknowledgmentsSurviveSupportedFailover() {
        String ns = "consensus-test-348";
        db.resetNamespace(ns);
        Map<String, String> committed = new LinkedHashMap<>();

        for (int i = 0; i < 100; i++) {
            String key = "order-" + i;
            String value = "confirmed";
            String commandId = "command-" + i;

            WriteOutcome outcome =
                db.write(ns, commandId, key, value);

            if (outcome == WriteOutcome.ACK_COMMITTED) {
                committed.put(key, value);
            }
            // UNKNOWN must be reconciled separately by commandId.
        }

        db.isolateFormerLeaderFromMajority();
        db.recoverAndStabilize();

        for (var e : committed.entrySet()) {
            assertEquals(
                e.getValue(),
                db.authoritativeRead(ns, e.getKey())
            );
        }
    }
}
~~~

**Chú ý:** `TestEnvironment` là fixture giả định; skeleton không chạy nếu chưa có adapter và môi trường test. `ACK_COMMITTED` phải map tới cam kết thật của database (không được gán cho local acceptance). Test cần đảm bảo fault nằm trong failure model được công bố và `authoritativeRead` đủ mạnh để so dữ liệu đã commit.

### 26.1. Test state machine deterministic

Với `OrderStateMachine` ở mục trên, replay cùng sequence commands nhiều lần từ cùng snapshot và kiểm tra kết quả state/outcomes giống nhau. Nếu có ID/timestamp ngẫu nhiên phát sinh trong apply, test sẽ bộc lộ divergence.

### 26.2. Test nhiều client đồng thời

Tạo hai client ở hai phía partition cùng ghi một key với `expectedVersion` giống nhau. Thu kết quả `ACK_COMMITTED`, `REJECTED`, `UNKNOWN`; đối soát thứ tự committed và invariant. Không kết luận chỉ vì cả hai method đã trả response.

### 26.3. Test visibility sau failover

Một follower chưa applied tới committed index có thể đọc cũ ở weak mode. Test strong read phải yêu cầu protocol đáp ứng freshness trước khi return. Phân biệt visibility lag với mất acknowledged data.

## 27. Quan sát hệ đồng thuận trong production

| Metric | Câu hỏi |
|---|---|
| Current leader per group | Ai có quyền ghi partition này? |
| Term/epoch changes | Election có flapping không? |
| Voting quorum health | Có đủ votes để commit không? |
| Replication lag | Follower nào bị trễ? |
| Commit index / applied index | Entry committed đã được apply chưa? |
| Durable log sync latency | ACK cần đợi storage bao lâu? |
| Not-leader/stale-term errors | Router hoặc worker nào dùng quyền cũ? |
| Election/failover duration | RTO thực tế tới lúc API usable? |
| Strong read unavailability | Minority/quorum failure ảnh hưởng ra sao? |
| Unknown commit backlog | Có commands chưa đối soát không? |
| Duplicate commands prevented | Idempotency hoạt động không? |
| Membership changes | Có cấu hình chuyển tiếp không an toàn? |
| Region replication lag | DR RPO có vượt ngưỡng không? |
| Business invariant violations | Có oversell/duplicate charge/mất Order? |

### 27.1. Metric theo consensus group

Một cluster có hàng nghìn groups có thể chỉ một số groups bị lỗi. Không chỉ giám sát một `clusterUp=true`; cần phát hiện partition/shard không có leader, thiếu quorum hoặc follower trễ bất thường.

### 27.2. Không biến IDs thành label cardinality vô hạn

Per-commandId metrics có thể làm hệ monitoring quá tải. Dùng trace/logs cho command cụ thể, histogram/aggregates cho nhóm và top-K hotspots. Bảo vệ thông tin tenant/khách hàng trong log.

### 27.3. Quorum hiện có không chứng minh khả năng chịu thêm lỗi

Nếu group còn đúng 2/3 voters khỏe, vẫn commit được nhưng chỉ cần thêm một node lỗi là mất quorum. Cần báo động giảm **redundancy headroom**, không chỉ khi hệ đã ngừng phục vụ.

### 27.4. Tách RTO và RPO

Sau failover, leader bầu nhanh chưa chắc application request đã dùng được; còn catch-up, apply, index/routing và idempotency reconciliation. RPO phải đo trên acknowledged writes theo mode, không chỉ trên số bytes khôi phục.

## 28. Quy trình xử lý sự cố leader/quorum

Một runbook khái niệm:

1. **Xác định phạm vi:** consensus group/partition, tenant/region, API bị ảnh hưởng.
2. **Tìm authority hiện tại:** term/epoch, member set, leader state và quorum health.
3. **Phân biệt crash với partition:** không suy từ heartbeat timeout rằng node đã chết vĩnh viễn.
4. **Ngăn split brain:** kiểm tra fencing, stale routes, old leader và background workers.
5. **Bảo toàn bằng chứng:** log index/term, committed/applied positions, write ACK modes và client outcomes.
6. **Không force leader tùy tiện:** chỉ dùng công cụ recovery chính thức có hiểu rõ data-loss tradeoff.
7. **Khôi phục quorum:** xử lý network/storage/node theo procedure được hỗ trợ.
8. **Xác minh committed history:** không nhầm uncommitted suffix hoặc stale follower với lịch sử đã commit.
9. **Đối soát unknown commands:** tra commandId, trả kết quả cũ hoặc trạng thái PENDING.
10. **Mở lại strong operations:** chỉ khi owner/readiness phù hợp với contract.
11. **Bắt kịp replicas:** giảm log/apply lag, theo dõi redundancy.
12. **Kiểm tra downstream:** outbox, CDC, search, payment workflows và các business invariants.
13. **Báo cáo RTO/RPO:** ghi rõ fault model và phạm vi, không tuyên bố “không mất gì” chỉ từ tổng số records.
14. **Phân tích nguyên nhân:** routing, election storm, quorum layout, storage latency, timeout policy.

### 28.1. Không xóa log để “sửa replication nhanh”

Committed log và transaction metadata có vai trò an toàn. Xóa thủ công các tệp vì thấy “cũ” có thể làm mất durable decisions. Dùng công cụ repair/recovery được nhà cung cấp hướng dẫn.

### 28.2. Không ép quorum bằng thay vote config trên từng node

Reconfiguration không đúng có thể tạo hai membership groups đều tự tin rằng mình là majority. Nếu đã mất majority vĩnh viễn, recovery có thể cần thủ tục đặc biệt và chấp nhận đánh đổi dữ liệu; phải được đánh giá, phê duyệt, có backup và ghi nhận rõ.

### 28.3. Trả trạng thái nghiệp vụ trung thực

Nếu không thể xác minh đã reserve stock, nên trả `PENDING`/`UNAVAILABLE` theo API contract, không báo `RESERVED` vì request đã được lưu vào queue ở một node.

## 29. Những ngộ nhận phổ biến

### “Node không trả lời nghĩa là node đã chết”

Sai. Có thể là network partition, process pause, IO stall hoặc lost message.

### “Có ba replica là đã giải quyết consensus”

Không. Cần giao thức vote/log/commit, durability và phục hồi.

### “Quorum giao nhau tự ngăn mọi vấn đề”

Chưa đủ. Election eligibility, terms, log completeness và safe reconfiguration cũng thiết yếu.

### “Bầu được leader mới nghĩa là dữ liệu đã an toàn”

Chưa đủ. Phải kiểm tra committed history, catch-up, read readiness và acknowledged writes.

### “Old leader nhận được client thì vẫn có quyền ghi”

Không. Nó có thể bị mất quorum/quyền từ term mới và phải bị fence.

### “Lease hết hạn chắc chắn process cũ ngừng ghi”

Không. Worker bị pause có thể tiếp tục với lease cũ nếu downstream không kiểm tra epoch.

### “ACK local append là committed”

Không. Entry có thể chưa đạt quorum commit và bị loại sau election.

### “Quorum committed nghĩa là mọi follower đã apply”

Không. Commit index và applied index là hai mốc.

### “Một read cũ chứng minh đã mất write”

Không. Có thể đang đọc follower, cache hoặc index lag.

### “Timeout nghĩa là lệnh chưa được commit”

Không. ACK có thể mất sau successful commit.

### “Consensus tạo exactly-once HTTP payment”

Không. External effects cần idempotency/reconciliation riêng.

### “Raft/Paxos tự cung cấp transaction giữa mọi shard”

Không. Consensus trong từng group không tự tạo global atomicity.

### “Leaderless QUORUM luôn linearizable nếu R+W>N”

Không. Còn concurrent writes, conflict resolution, sloppy quorum, clock skew và membership.

### “CRDT merge được mọi invariant”

Không. Hội tụ counter không ngăn oversell khi hai vùng cấp từ cùng quota chưa chia quyền.

### “Strong read là serializable transaction nhiều record”

Không. Read freshness và transaction isolation là hai câu hỏi khác nhau.

### “Chuyển membership là sửa danh sách IP”

Không. Cần chuyển quorum an toàn và đảm bảo log của member mới đủ điều kiện.

### “Một hệ dùng Raft tức mọi application write đều dùng Raft”

Không. Consensus có thể chỉ cho metadata hoặc một subset operations.

### “Tăng timeout sẽ chữa split brain”

Không. Timeout có thể giảm election flapping nhưng không thay thế fencing và quorum safety.

### “Mọi lỗi của node đều là crash-stop”

Không. Storage corruption, bug, node gửi dữ liệu sai hoặc compromised node có threat model khác, đôi khi cần Byzantine assumptions riêng.

### “Mạng hồi phục là mọi sai lệch tự sửa thành đúng”

Không. Convergence có thể chọn một version và làm mất nghĩa vụ đã ACK; cần protocol và business reconciliation.

## 30. Checklist thiết kế đồng thuận và quyền ghi

| Câu hỏi | Quyết định cần ghi |
|---|---|
| State/invariant nào cần agreement? | Leader/lease, key, log, transaction decision |
| Consensus scope là gì? | Key, partition, shard, metadata group |
| Failure model? | Node crash, disk loss, network partition, region outage |
| Voting/data members? | N, quorum, witness, failure domains |
| Election rules? | Term/epoch, vote durability, log eligibility |
| Commit rules? | Replication, durability, ACK semantics |
| Read behavior? | Linearizable/session/stale read path |
| Fencing? | Old leader/worker bị chặn tại nguồn ghi |
| State machine deterministic? | Command inputs và replay assumptions |
| Membership changes? | Reconfiguration đúng protocol |
| No quorum behavior? | Reject, wait, PENDING, local stale read |
| Unknown commit? | Stable commandId, authoritative reconciliation |
| Cross-shard invariants? | Transaction coordinator, guard, saga |
| Multi-region? | Single/multi-writer, replication, RPO/RTO |
| Test evidence? | Partition/election/replay/ACK-loss/history |
| Observability? | Term, quorum, commit/apply lag, retries |

### 30.1. Mẫu hợp đồng kỹ thuật

~~~yaml
workload: inventory-reservation
invariant: "never confirm more reservations than authorized stock"
consensusScope: "<partition or authority group>"
authority:
  leaderSelection: "<documented election/ownership protocol>"
  fencing: "<term/epoch enforcement point>"
replication:
  votingMembers: "<configured count>"
  dataBearingMembers: "<configured count>"
  failureDomains: "<AZ/region layout>"
  commitRule: "<documented condition>"
  ackDurability: "<documented mode>"
read:
  authoritativeMode: "<supported consistency/API>"
  staleReadAllowedForDisplay: true
partitionBehavior:
  majoritySide: "<expected>"
  minoritySide: "<expected>"
recovery:
  commandId: "stable across retries"
  ambiguousCommit: "reconcile before new business effect"
  membershipChange: "<official procedure>"
evidence:
  productVersion: "<exact version>"
  tests: "<run IDs>"
  documentation: "<official versioned references>"
~~~

Không thay placeholder bằng suy đoán. Hợp đồng phải dựa trên version, configuration và topology thực tế.

## 31. Bài tập thực hành

### Bài 1 — Timeout không chứng minh crash

A không nhận heartbeat từ B trong 3 giây. Liệt kê bốn khả năng khiến B không phản hồi nhưng vẫn hoạt động. Giải thích vì sao A không thể tự tuyên bố mình có quyền commit toàn cluster chỉ dựa vào timeout.

### Bài 2 — Safety và liveness

Cluster A/B/C chia thành `{A}` và `{B,C}`. Dưới majority consensus, phía nào có thể commit strong writes? Điều gì xảy ra ở A? Phân biệt điều kiện safety và liveness.

### Bài 3 — Quorum intersection

Với N=5, liệt kê hai quorum có ba voters và chứng minh chúng giao nhau. Vì sao còn cần election log eligibility?

### Bài 4 — Old leader zombie

A bị cô lập, B trở thành leader term 9, A vẫn gửi write term 8. Thiết kế epoch/fencing ở storage và nêu lý do chỉ kiểm tra lease trong process A chưa đủ.

### Bài 5 — Append vs commit

Leader A append entry index 42 và ACK local; B/C chưa nhận. A chết vĩnh viễn. Write 42 có thể mất không? So sánh với trường hợp entry 42 đã quorum-committed theo protocol đủ điều kiện.

### Bài 6 — Read sau failover

Leader mới có committed log index 42 nhưng applied index 41. Một follower đọc Order vẫn thấy trạng thái cũ. Làm sao phân biệt stale read với committed data loss?

### Bài 7 — Raft term/index

Hai candidates cùng lastIndex=100 nhưng lastTerm khác nhau. Vì sao không chọn theo index lớn nhất hoặc CPU khỏe nhất? Mô tả tính chất leader completeness.

### Bài 8 — Paxos

Giải thích roles proposer/acceptor/learner và vì sao intersecting quorums cùng ballot/proposal rules giúp không chọn hai giá trị khác nhau cho một instance. Phân biệt một instance với replicated log nhiều entries.

### Bài 9 — FLP

Tóm tắt giả định asynchronous, deterministic và một crash trong FLP. Vì sao giới hạn đó không đồng nghĩa các hệ Raft/Paxos production không thể tiến triển trong mạng thực?

### Bài 10 — 2PC và consensus

Order shard và Inventory shard đều dùng consensus riêng. Vì sao hai commits vẫn không tạo atomic checkout? Phác thảo quyết định transaction coordinator và trường hợp coordinator crash sau PREPARE.

### Bài 11 — Leaderless QUORUM

Cho N=3, R=2, W=2. Giải thích overlap và liệt kê các tình huống khiến không thể suy linearizability trực tiếp từ công thức, gồm concurrent writes, sloppy quorum và timestamp skew.

### Bài 12 — Region quota

Tồn tổng 10, hai regions mất liên lạc, mỗi nơi muốn giữ 8. Đề xuất single-writer hoặc escrow quota; mô tả tradeoff availability và cách ngăn double-allocation.

### Bài 13 — Unknown commit

Client gửi ConfirmOrder rồi mất response ngay sau majority commit. Thiết kế API `GET /commands/{commandId}` hoặc equivalent source lookup, phân biệt COMMITTED, REJECTED và PENDING.

### Bài 14 — Deterministic apply

Một state machine gọi random UUID và pricing API khi apply log. Mô tả cách ba replicas có thể phân kỳ; thiết kế command chứa inputs để replay cho cùng kết quả.

### Bài 15 — Membership change

Chuyển config `{A,B,C}` sang `{D,E,F}`. Vì sao không được để hai majorities tách rời cùng có quyền ghi? Đề xuất bước chuyển giao/consensus reconfiguration theo protocol.

### Bài 16 — Fault-injection history

Thiết kế test trong môi trường cô lập: partition cũ leader, bầu leader mới, gửi hai lệnh xung đột ở hai phía, ghi committed ACKs, heal network, đối soát log và test fencing.

### Bài 17 — NoSQL sản phẩm

Chọn một trong MongoDB, Cassandra/ScyllaDB, DynamoDB, Redis, Cosmos DB hoặc Couchbase. Tìm trong tài liệu đúng phiên bản: data-path replication, write ACK/durability, read consistency, failover behavior và phạm vi transaction. Giải thích vì sao không suy tất cả từ chữ “quorum”.

### Bài 18 — Phân quyền theo partition

Cluster có 1.000 shards, mỗi shard có voting group riêng. Một AZ mất mạng và 80 shards thiếu quorum. Đề xuất dashboard/alert theo shard, API behavior, routing recovery và cách không làm ảnh hưởng quá mức 920 shards còn lại.

### Bài 19 — External side effects

Order event đã committed trong replicated log nhưng consumer gọi payment gateway rồi chết trước khi ACK job. Hãy thiết kế paymentId và outbox/consumer idempotency để tránh charge hai lần.

### Bài 20 — Review tuyên bố kỹ thuật

Một tài liệu viết: “Hệ có ba replicas, timeout hai giây là biết node đã chết, node sống nào cũng có thể lên leader, `R+W>N` bảo đảm không bao giờ mất ghi, và mọi callback giao dịch chỉ chạy một lần.” Hãy chỉ ra các thiếu sót về failure detection, quorum, log eligibility, durability, leaderless conflict, commit outcome và retry.

---

**Kết luận:** Khi lỗi hoặc mất liên lạc, bài toán trọng tâm không chỉ là sao chép đủ nhiều bản dữ liệu mà là **làm cho các node thống nhất ai có quyền ra quyết định và lịch sử nào được coi là committed**. Đồng thuận phân tán bảo vệ safety bằng quorum, log ordering, term/epoch, bầu leader đủ điều kiện, fencing và chuyển membership an toàn; liveness phụ thuộc điều kiện mạng và quorum thực tế. Một node không trả lời **chưa chắc đã chết**, một log entry đã append **chưa chắc committed**, và một client timeout **chưa chắc giao dịch đã abort**. Bên cạnh đó, consensus trên một shard không tự tạo transaction xuyên service, cũng không bảo đảm external effects exactly once. Thiết kế NoSQL vững chắc phải nêu rõ **phạm vi quyền ghi, ACK/durability, read consistency, failure model, idempotency và quy trình recovery**, rồi kiểm thử các lịch lỗi tương ứng thay vì chỉ kiểm tra happy path.
