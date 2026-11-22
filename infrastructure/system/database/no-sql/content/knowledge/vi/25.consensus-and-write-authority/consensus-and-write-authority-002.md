# Phân biệt sao chép dữ liệu với giao thức đồng thuận

## 1. Bài toán: ba bản sao nhưng hai người cùng được xác nhận sở hữu một ghế

Giả sử ứng dụng đặt vé lưu ghế `SEAT-100` trên ba node NoSQL:

```text
                  Ứng dụng đặt vé
                         |
                         v
                    NoSQL Cluster
                   /     |      \
                  v      v       v
                 A       B       C
               FREE    FREE    FREE
```

Tại thời điểm xảy ra chia cắt mạng:

```text
Phía mạng số 1                  Phía mạng số 2
+-----------------+            +-----------------+
| Node A          |     X      | Node B, Node C  |
| Client X        |            | Client Y        |
+-----------------+            +-----------------+
```

Nếu phía A và phía B/C đều có thể độc lập quyết định ghế còn trống, rồi trả `CONFIRMED` cho hai khách X và Y, hệ thống đã vi phạm invariant **một ghế chỉ được xác nhận cho một khách**.

Sau khi mạng hồi phục, các bản sao có thể hội tụ về `owner=X` hoặc `owner=Y` nhờ cơ chế giải quyết xung đột. Nhưng việc hội tụ đó **không hoàn tác được hai thông báo xác nhận hoặc hai khoản tiền đã thu**.

Câu chuyện minh họa hai lớp vấn đề khác nhau:

- **Sao chép dữ liệu (replication):** tạo và duy trì nhiều bản sao, truyền mutation giữa các replica, xử lý độ trễ đồng bộ.
- **Giao thức đồng thuận (consensus protocol):** giúp các thành viên thống nhất một giá trị, một thứ tự quyết định hoặc một người có quyền lãnh đạo, dù một số node gặp lỗi.

Đây là bài học thuộc chương **Đồng thuận và quyền ghi**. Mục tiêu là hiểu khi nào nhiều bản sao là đủ, khi nào cần một authority có bảo đảm quyết định duy nhất, và vì sao ngay cả khi dùng Raft/Paxos vẫn phải xem phạm vi transaction, đường đọc và side effect bên ngoài.

## 2. Sao chép dữ liệu là gì?

**Replication** là kỹ thuật lưu và duy trì nhiều bản sao của một tập dữ liệu trên những máy hoặc vùng khác nhau.

Ví dụ primary–secondary:

```text
Client -> Primary A
              |
              +-- replication --> Secondary B
              |
              +-- replication --> Secondary C
```

Những mục tiêu điển hình:

1. Chịu lỗi khi một node hoặc ổ đĩa hỏng.
2. Cho phép read từ các replica thích hợp.
3. Giảm latency ở vùng gần người dùng.
4. Hỗ trợ bảo trì hoặc nâng cấp từng node.
5. Tăng khả năng phục hồi khi dữ liệu ở nhiều failure domains.
6. Phân phối dữ liệu tới các read models hoặc hệ phân tích.

Nhưng replication **không tự trả lời**:

- Hai nodes cùng nhận một write xung đột thì ai thắng?
- Write nào đã được commit an toàn qua failover?
- Leader mới được chọn bằng nguyên tắc nào?
- Một write đã thành công có xuất hiện ngay khi đọc từ mọi replica không?
- Có thể giữ invariant xuyên hai partition không?
- Mọi replica có quyền nhận ghi hay chỉ một authority?

Để trả lời cần xét **replication topology, write/read acknowledgement, consistency level, leader election, transaction và/hoặc consensus**.

## 3. Đồng thuận là gì?

**Consensus** là lớp giao thức cho các tiến trình trong hệ phân tán thống nhất một quyết định, giá trị hoặc một chuỗi quyết định, trong mô hình lỗi được hỗ trợ.

Một cách sử dụng rất quan trọng là **replicated state machine**:

```text
                     Các command
                          |
                          v
                 Consensus log
                index 1, 2, 3...
                          |
            +-------------+-------------+
            |             |             |
            v             v             v
          Node A        Node B        Node C
         apply 1..3    apply 1..3    apply 1..3
```

Nếu cùng một chuỗi commands được quyết định và mỗi state machine áp dụng commands một cách xác định, các node có thể tái tạo cùng trạng thái logic.

Consensus được sử dụng hoặc làm nền tảng cho:

- Chọn leader có quyền điều phối ghi.
- Thống nhất log entries được commit.
- Quyết định một claim hoặc một cấu hình.
- Quản lý metadata của cụm.
- Thay đổi membership an toàn.
- Điều phối distributed leases/locks.
- Xây dựng strongly consistent key-value/transaction primitives.

**Consensus có thể sử dụng replication để lưu log bền vững. Nhưng replication không tự trở thành consensus chỉ vì tồn tại nhiều bản sao.**

## 4. Bảng so sánh nhanh

| Khía cạnh | Sao chép dữ liệu | Giao thức đồng thuận |
|---|---|---|
| Mục tiêu trực tiếp | Duy trì/truyền dữ liệu qua nhiều bản sao | Thống nhất giá trị, log hoặc quyền quyết định |
| Có thể bất đồng bộ? | Có | Network có thể bất đồng bộ; liveness cần giả định thích hợp |
| Replica có thể tạm chậm? | Có | Có; log committed và trạng thái applied có thể khác mốc |
| Có cần leader? | Không bắt buộc | Tùy thuật toán; Raft có leader |
| Có dùng quorum không? | Có thể dùng read/write quorums | Dùng voting/acceptor quorums theo giao thức |
| Quorum giao nhau đã đủ? | Không để suy ra linearizability | Cần thêm vote/term/log/commit rules |
| Có thể nhận xung đột rồi giải quyết sau? | Có với một số mô hình | Quyết định trong một slot phải tuân thủ agreement |
| Mất mạng | Tùy policy vẫn có thể ghi ở nhiều nơi | Phía thiếu quorum thường không commit quyết định mới |
| Bảo vệ business uniqueness? | Không tự động | Có thể, nếu invariant thuộc authority được bảo vệ |
| Tự tạo transaction nhiều partition? | Không | Không; cần transaction boundary phù hợp |
| Tự bảo vệ external payment/email? | Không | Không |
| Tự thay backup? | Không | Không |

Một sản phẩm có thể dùng **đồng thuận để ghi metadata** nhưng dùng **sao chép bất đồng bộ cho dữ liệu người dùng**. Một sản phẩm khác có thể dùng đồng thuận trong từng partition nhưng sao chép read models riêng. Vì vậy không gắn nhãn một từ cho toàn hệ.

## 5. Ba kiểu replication quan trọng

### 5.1. Single-leader replication

Một primary/leader nhận writes, các followers nhận log hoặc mutations:

```text
                       write
                         |
                         v
                    Leader A
                     /    \
                    v      v
                   B        C
                follower follower
```

Cần kiểm tra:

- Leader ACK khi nào?
- Followers nhận đồng bộ hay bất đồng bộ?
- Read từ follower có thể stale không?
- Primary chết thì có thể rollback writes nào?
- Leader election có dùng consensus không?

**Single leader không tự có nghĩa mọi write phải qua Raft.**

### 5.2. Multi-leader replication

Hai hoặc nhiều regions cùng nhận writes rồi đồng bộ:

```text
Region A: accepts writes <-- replication --> Region B: accepts writes
```

Nếu cùng ghi key K khi mất mạng:

```text
A: K = owner-X
B: K = owner-Y
```

hệ có thể phát hiện xung đột rồi dùng last-writer-wins, merge, CRDT hoặc application-level conflict resolution. Đây là chiến lược phù hợp với **một số** loại dữ liệu, nhưng không tự đáp ứng uniqueness nghiêm ngặt khi cả hai vùng đã ACK.

### 5.3. Leaderless replication

Coordinator phát mutation tới nhiều replicas, có thể dùng read/write consistency levels:

```text
                     Coordinator
                     /    |    \
                    v     v     v
                    A     B     C
```

Dữ liệu có thể tạm lệch, sau đó hội tụ nhờ reconciliation, read repair hoặc anti-entropy repair. Một số regular operations kiểu Dynamo/Cassandra thuộc cách tiếp cận này.

**Read/write quorum trong replica store không đồng nghĩa mỗi mutation được quyết định bằng Raft/Paxos.**

## 6. Eventual convergence khác quyết định nghiệp vụ đúng

Một ví dụ:

```text
T0: East = FREE; West = FREE
T1: Mất kết nối
T2: East -> owner=X, ACK "Đã đặt"
T3: West -> owner=Y, ACK "Đã đặt"
T4: Mạng phục hồi
T5: Conflict resolver chọn owner=Y
T6: East = West = owner=Y
```

Ở T6 các replicas đã **hội tụ**, nhưng nghiệp vụ đã sai ở T2/T3. Hậu quả có thể gồm:

- Hai emails hoặc vé điện tử được phát.
- Hai khoản thu tiền.
- Hai workers xuất kho cùng một món.
- Một người dùng mất quyền sau khi đã nhận xác nhận.

Với dữ liệu công khai, analytics, cache hoặc counters có thể merge, eventual consistency có thể chấp nhận được. Với tài nguyên duy nhất, số dư, quota hoặc quyền truy cập, cần thiết kế **authority và thời điểm ACK** cho business decision.

## 7. Safety, agreement, validity và liveness

Ở mức khái niệm, consensus cần các thuộc tính:

**Agreement:** không có hai tiến trình đúng nào quyết định hai giá trị khác nhau cho cùng một consensus instance/slot.

**Validity:** quyết định phải phù hợp với những giá trị đề xuất hợp lệ và quy tắc thuật toán.

**Termination/liveness:** khi các điều kiện đủ thuận lợi, các tiến trình cuối cùng đạt quyết định.

Trong thực hành, tách:

- **Safety:** không chọn hai lịch sử committed mâu thuẫn.
- **Liveness:** có thể tiếp tục bầu leader, xử lý yêu cầu và commit.

Khi mạng bị chia cắt, giữ safety có thể yêu cầu phía thiếu quorum **không commit**. Liveness phụ thuộc số member còn liên lạc, thời gian election và giả định về mạng.

### 7.1. Không hứa tiến triển vô điều kiện

Trong mạng phân tán hoàn toàn bất đồng bộ với khả năng một node crash, không thể đảm bảo một thuật toán consensus xác định luôn kết thúc trong mọi lịch thực thi. Các hệ thực tế dùng timeouts, stable leadership và giả định mạng cuối cùng đủ ổn định.

### 7.2. Mô hình lỗi không phải Byzantine mặc định

Raft và Paxos cổ điển thường nhắm tới **crash, delay, message loss/partition** chứ không tự bảo vệ mọi thành viên độc hại gửi thông tin giả. Bài toán Byzantine cần thuật toán/threat model khác.

## 8. Majority quorum trong consensus

Với N voting members:

\[
Q=\left\lfloor \frac{N}{2}\right\rfloor+1
\]

| N voters | Majority | Tối đa node crash nếu những node còn lại liên lạc được |
|---:|---:|---:|
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

Hai tập chiếm **hơn một nửa** số voters bắt buộc giao nhau.

Ví dụ N=5:

```text
Quorum 1: {A, B, C}
Quorum 2: {C, D, E}
                  ^
              chung C
```

Nhưng việc giao nhau chỉ hữu ích nếu member tuân thủ **voting/promise/log rules** và lưu metadata theo giao thức.

### 8.1. Network partition 2–1

Với ba voters:

```text
Side A: A, B   ---X---   Side B: C

A/B có majority=2
C chỉ có 1 vote, không đủ
```

Nếu không có lỗi khác, A/B có thể tiếp tục quyết định theo protocol. C có thể vẫn phục vụ một số stale reads theo read mode, nhưng không được độc lập commit một lịch sử xung đột.

### 8.2. Network partition 2–2

Với bốn voters, majority=3. Khi chia 2–2, **không phía nào có majority**.

### 8.3. Voter khác learner

Không phải mọi node hiển thị trong cluster đều có voting power. Learner/read replica có thể lưu dữ liệu nhưng không tham gia quorum như voter. Khi tính khả năng chịu lỗi phải kiểm tra cấu hình thực.

## 9. Read/write quorum không phải voting quorum

Một replicated store có thể dùng:

\[
R + W > RF
\]

Với RF=3, R=2 và W=2, hai tập replica phải giao nhau trong mô hình đơn giản:

```text
Write ACK: {A, B}
Read from: {B, C}
Intersection: B
```

Điều đó tạo điều kiện để read path tìm thấy write mới nếu cơ chế reconciliation phù hợp. Nhưng **chỉ giao nhau về replica chưa chứng minh mọi history là linearizable**.

Vì sao?

1. Hai writes có thể xảy ra đồng thời.
2. Timestamp reconciliation có thể làm kết quả không theo real-time order.
3. Read có thể nhận response từ những replicas đã cũ.
4. Một request có thể timeout ở thời điểm không biết commit.
5. Topology/replication strategy và DC thay đổi tập replicas.
6. Không có một voted log index/term cho mỗi business command.

Trong consensus, quorum còn gắn với:

- Term/ballot hoặc proposal number;
- Promise/voting constraints;
- Quy tắc leader election;
- Log matching;
- Quy tắc commit;
- Bảo đảm persistence và membership.

**Đừng gọi một regular QUORUM write là Paxos chỉ vì cả hai đều nhắc đến “đa số”.**

## 10. Raft: replicated state machine consensus

**Raft** tổ chức một nhóm nodes với leader, followers, terms và replicated log.

Các thành phần:

- **Leader:** nhận đề xuất lệnh từ clients.
- **Follower:** nhận heartbeat/log entries từ leader.
- **Candidate:** xin votes trong một election.
- **Term:** thế hệ bầu chọn có thứ tự.
- **Log index:** vị trí một entry.
- **Commit index:** mốc log đã được quyết định an toàn.
- **Last applied:** mốc state machine đã thực thi.

Sơ đồ:

```text
Client
  |
  | Reserve(SEAT-100, U42)
  v
Leader A (term 7)
  |
  | AppendEntries(index=42, term=7)
  +-------------------------> Follower B
  +-------------------------> Follower C
  |
  <------ sufficient quorum ACKs
  |
  v
Leader xác định entry committed theo Raft
  |
  v
Apply state machine và trả business result
```

Sơ đồ lược bớt các điều kiện khi entry thuộc term trước, persistence và xử lý concurrent requests.

### 10.1. Replicated khác committed

Entry có mặt trên leader và một follower không tự chứng minh đã commit, nếu không biết term/configuration và quy tắc commit tương ứng.

### 10.2. Committed khác applied

```text
Log committed through index 100
Follower C applied through index 97
```

C có thể còn cần áp dụng entries 98–100. Một read trực tiếp tại C có thể stale nếu không có read protocol/chờ mốc phù hợp.

### 10.3. Applied khác external visibility

Search index, cache hoặc analytics ở hệ khác vẫn có pipeline đồng bộ riêng. Raft log commit không cập nhật chúng tức thì.

## 11. Bầu leader trong Raft

Khi follower mất heartbeat đủ lâu, nó có thể tăng term thành candidate rồi xin votes.

Một voter xét:

- Term ứng viên có hợp lệ không?
- Mình đã bỏ phiếu cho ai trong term đó?
- Candidate có log đủ mới theo quy tắc last log term/index không?

Những quy tắc này giúp ngăn một candidate thiếu committed history trở thành leader hợp lệ.

### 11.1. Leader cũ bị cô lập

```text
T0: A leader term 7
T1: A mất kết nối B/C
T2: B/C bầu B leader term 8
T3: B tiếp tục commit với majority
T4: A vẫn nghĩ mình là leader term 7
```

A có thể vẫn xử lý code, nhưng không có majority để commit entry mới theo Raft. Khi nhận term cao hơn nó phải nhường quyền.

### 11.2. Vì sao clock timestamp không thay term?

Đồng hồ có thể lệch/nhảy. Thứ tự timestamp không mã hóa đầy đủ quy tắc voting và log matching. Hệ cần term/epoch gắn với authority và persisted metadata.

### 11.3. Leader cũ vẫn có thể làm hỏng hệ ngoài

Một leader mất quorum không tự mất khả năng gửi HTTP request hoặc write tới MongoDB/S3. Muốn chặn stale owner ở tài nguyên ngoài phải dùng fencing/idempotency ở nơi ghi thật.

## 12. Log matching và commit rule của Raft

### 12.1. Log matching

Follower kiểm tra previous index/term khi nhận AppendEntries. Nếu không khớp, phải điều chỉnh suffix theo protocol để hội tụ về lịch sử hợp lệ.

### 12.2. Entry chưa commit có thể bị thay

Một log suffix chưa commit trên leader cũ có thể bị thay khi leader hợp lệ mới đồng bộ history. Vì vậy không được trả business success chỉ vì **leader đã append vào local disk**.

### 12.3. Raft có điều kiện commit theo term

Không nên rút gọn thành “cứ có entry trên đa số disk thì chắc chắn được commit” trong mọi term. Raft có quy tắc leader dùng quorum để commit các entries thuộc **term hiện tại**; những entries cũ có thể được commit gián tiếp khi entry term mới đạt điều kiện.

Ứng dụng cần tin vào **commit response của implementation**, không tự đếm file log.

### 12.4. State machine deterministic

Nếu log quyết định `INCREMENT counter by 1`, tất cả replicas áp dụng cùng lệnh sẽ cho cùng kết quả logic. Nếu mỗi node tự lấy random number/current clock để tính state khác nhau thì có thể gây divergence. Các yếu tố không xác định cần được đưa vào command/result theo protocol thích hợp.

## 13. Paxos và Multi-Paxos

**Paxos** là họ thuật toán đồng thuận. Trong Classic Paxos có ba vai trò khái niệm:

- **Proposer:** đề xuất giá trị.
- **Acceptor:** tuân thủ ballot/promise và chấp nhận proposal.
- **Learner:** biết giá trị đã được chọn.

Một vòng giản lược:

```text
Proposer -> Prepare(ballot)
Acceptors -> Promise + prior accepted metadata
Proposer -> Chọn value theo quy tắc an toàn
Proposer -> Accept(ballot, value)
Quorum acceptors -> Accepted
Value -> Chosen
```

Các bước “chọn value theo quy tắc an toàn” quan trọng: không được tùy ý chọn giá trị mới nếu có prior accepted value cần bảo toàn.

### 13.1. Hai proposers cạnh tranh

```text
X: propose owner=X, ballot=10
Y: propose owner=Y, ballot=11
```

Promises và proposal numbers giúp không chọn ra hai giá trị mâu thuẫn cho cùng instance theo giao thức.

### 13.2. Multi-Paxos

Một lần Paxos giải một slot; Multi-Paxos tổ chức nhiều slots/log positions, thường tận dụng stable leader để giảm chi phí coordination qua nhiều decisions.

### 13.3. So sánh Raft/Paxos

| Thuộc tính | Raft | Paxos/Multi-Paxos |
|---|---|---|
| Giới thiệu phổ biến | Replicated log | Chọn value hoặc chuỗi values |
| Số thế hệ | Term | Ballot/proposal number |
| Thành phần | Leader, followers, candidates | Proposer, acceptors, learners |
| Bước quan trọng | Election, AppendEntries, commit | Prepare/Promise/Accept/Chosen |
| Quorum | Majority điển hình | Quorums theo biến thể |
| Ứng dụng | etcd và nhiều replicated logs | LWT Cassandra cổ điển, các hệ Paxos-based khác |

Không nên coi tất cả hệ có chữ “quorum” là một implementation Paxos.

## 14. Cassandra: regular write khác LWT

Cassandra thể hiện rõ hai lớp cơ chế.

### 14.1. Regular writes

```sql
UPDATE orders_by_id
SET status = 'PAID'
WHERE order_id = 'O100';
```

Coordinator gửi mutation tới replicas và chờ số ACK theo consistency level, ví dụ `ONE`, `QUORUM`, `LOCAL_QUORUM` hoặc `ALL`.

Điều này **không tự tạo atomicity cho một cặp read-then-write của ứng dụng**.

### 14.2. Race khi giữ ghế

```text
Client X: READ seat.owner = null
Client Y: READ seat.owner = null
Client X: WRITE owner=X with QUORUM
Client Y: WRITE owner=Y with QUORUM
```

Nếu ứng dụng báo success dựa trên snapshot cũ, hai business confirmations có thể mâu thuẫn dù writes được replicate theo CL.

### 14.3. LWT

Với schema phù hợp, claim đầu tiên bằng conditional insert:

```sql
INSERT INTO seat_reservations (
    seat_id, owner_id, state
)
VALUES ('SEAT-100', 'U42', 'RESERVED')
IF NOT EXISTS;
```

Trong Cassandra dùng LWT theo cơ chế Paxos-based, conditional mutation được quyết định theo serial consistency phù hợp. Kết quả có cột `[applied]` báo có thực sự áp dụng không.

```text
[applied] | owner_id
----------+---------
false     | U10
```

Nếu `[applied]=false`, claim không thành công. Không được chỉ dựa vào response transport thành công.

### 14.4. SERIAL/LOCAL_SERIAL

Các consistency levels serial liên quan giai đoạn/semantics LWT, khác regular read/write CL. Phạm vi DC/topology và phiên bản rất quan trọng.

### 14.5. LWT không tự tạo transaction đa hệ

Một LWT bảo vệ điều kiện trong scope hỗ trợ, nhưng không làm việc giảm inventory, tạo Order và charge payment cùng commit nguyên tử qua ba hệ khác nhau.

## 15. Hinted handoff và repair không phải consensus

Cassandra có những cơ chế giúp replicas hội tụ:

- **Hinted handoff:** chuyển các mutations được lưu làm hints khi replica tạm unavailable.
- **Read repair:** sửa một số bất đồng theo read path và semantics/version.
- **Anti-entropy repair:** chủ động so sánh/đồng bộ dữ liệu trong phạm vi repair.

Chúng giải quyết câu hỏi “replica nào còn thiếu mutations?” chứ không giải quyết câu hỏi “hai business requests tranh cùng một ghế, request nào được phép nhận CONFIRMED?”.

Repair có thể làm mọi replica cùng ghi owner Y, nhưng không xóa được thực tế hệ đã thu tiền X nếu workflow không xử lý business reconciliation.

## 16. MongoDB: primary, oplog, write concern và election

MongoDB replica set có primary nhận writes và secondaries sao chép oplog/dữ liệu:

```text
Client -> Primary A
             |
             +----> Secondary B
             +----> Secondary C
```

MongoDB cung cấp write concern, read concern, read preference, sessions, election và multi-document transactions. Không nên gộp tất cả thành “mọi write là một Raft entry”.

### 16.1. w:1

Primary có thể ACK write theo `w:1` trước khi majority replicas đã nhận. Nếu primary hỏng và write chưa replicate đủ, có tình huống write được ACK bị rollback sau failover theo semantics sản phẩm.

```text
T0: Primary A nhận K=v2
T1: A ACK w:1
T2: A chết
T3: B/C chưa có v2
T4: Primary mới có thể giữ K=v1
```

### 16.2. w:"majority"

`w:"majority"` cung cấp acknowledgement khác với `w:1`, giúp những bảo đảm liên quan rollback/durability theo hợp đồng MongoDB. Còn phải xét journaling, topology và version.

### 16.3. Read concern không thay write concern

`readConcern:"majority"` không tự tương đương `readConcern:"linearizable"`. Read preference quyết định nơi read; một secondary có thể trễ.

### 16.4. Transactions

MongoDB multi-document transactions có scope/isolation riêng. Có primary election và majority writes **không tự gom hai `updateOne()` rời thành một transaction**.

## 17. Redis: asynchronous replication và Sentinel

Redis primary–replica trong nhiều cấu hình có sao chép dữ liệu bất đồng bộ:

```text
Client -> Redis Primary A
              |
              +----> Replica B
              +----> Replica C
```

Ví dụ:

```text
T0: SET K=v2 tại A
T1: A ACK
T2: A chết trước khi replica nhận v2
T3: Replica B được promote, vẫn K=v1
```

Do vậy replication ACK và failover data safety cần được phân biệt.

### 17.1. Sentinel quorum không phải data consensus

Redis Sentinel quản lý giám sát/failover và có quorum/majority concepts. Điều đó **không tự khiến mọi lệnh SET được quyết định bằng một Raft quorum trước ACK**.

### 17.2. WAIT không tự tạo Raft

`WAIT` có thể chờ số replica xác nhận đã nhận writes theo semantics Redis, nhưng replica receipt không tự bằng consensus commit qua mọi loại failover và durability assumption.

### 17.3. Distributed lock qua Redis

`SET lock:K token NX PX 30000` có thể tạo một lease ứng dụng. Nhưng worker cũ có thể tiếp tục sau khi TTL hết. Muốn bảo vệ MongoDB hoặc API bên ngoài, tài nguyên đích cần owner/fencing/idempotency protocol thích hợp.

## 18. etcd: ví dụ consensus-backed authority

etcd thường được sử dụng như distributed key-value coordination store, với Raft trong nhóm voting members.

Một application claim có thể dùng compare-and-swap transaction:

```text
IF version("/claims/SEAT-100") == 0:
    PUT "/claims/SEAT-100" = "U42"
ELSE:
    return ALREADY_TAKEN
```

Đây là giả mã, không phải cú pháp lệnh CLI nguyên văn.

### 18.1. Khi mất quorum

Nhóm ba voters chỉ còn một voter reachable không thể commit writes cần majority. Application phải chờ/trả unavailable hoặc tiếp nhận một request **chưa được xác nhận** trong đường durable phù hợp.

### 18.2. Read options

etcd cung cấp các read modes với semantics khác nhau, bao gồm linearizable read và serializable read có thể stale. Không nên suy mọi follower read đều mới chỉ vì backend sử dụng Raft.

### 18.3. Leases

Lease của etcd có thể điều phối owner/leader. Nhưng một owner bị pause sau khi lease hết hạn vẫn có thể tác động external sink, nên cần fencing/authorization ở đích nếu business invariant yêu cầu.

## 19. ZooKeeper và quyền ghi

ZooKeeper sử dụng atomic broadcast/replication cùng session semantics để cung cấp coordination primitives. Ví dụ lock recipe qua ephemeral sequential nodes:

```text
/locks/report/lock-000101 -> Worker A
/locks/report/lock-000102 -> Worker B
/locks/report/lock-000103 -> Worker C
```

Worker có sequence nhỏ nhất theo recipe có thể giữ lock, workers khác watch predecessor.

Nếu A mất ZooKeeper session, node ephemeral có thể bị xóa và B nhận quyền, nhưng A **không chắc đã ngừng tiến trình**. Sink phải từ chối stale generation của A khi cần safety.

Không nên gọi ZooKeeper là Raft nếu sản phẩm dùng cơ chế khác như Zab. Điều quan trọng là **contract về coordination**, không là tên thuật toán tùy tiện.

## 20. Kafka: data replication và metadata consensus khác nhau

Kafka có replicated data partition logs; leader/ISR và producer acknowledgments ảnh hưởng độ bền của messages.

Trong các triển khai dùng KRaft, consensus quorum được dùng cho **cluster/controller metadata**. Không được kết luận “mọi data record ở mọi topic partition đều đi qua cùng một Raft consensus log” chỉ vì thấy chữ KRaft.

### 20.1. acks và min.insync.replicas

Các cấu hình như `acks` và `min.insync.replicas` ảnh hưởng khi producer được ACK, tùy leader/ISR và lỗi. Phải xem contract chính xác trước khi tuyên bố mức durability.

### 20.2. Thứ tự log có phạm vi

Data partition có thứ tự riêng. Không được suy một total order toàn cục cho mọi partitions.

### 20.3. Delivery khác exactly-once external effect

Consumer gửi email thành công rồi crash trước khi commit offset có thể khiến message được xử lý lại. Cần idempotency ngay cả khi metadata/data replication hoạt động đúng.

## 21. Managed NoSQL: dùng API contract, đừng đoán thuật toán nội bộ

Một số cloud NoSQL cung cấp:

- Conditional update/CAS trên item.
- Transactions trong phạm vi được hỗ trợ.
- Strong, session hoặc eventual read consistency.
- Multi-region replication và conflict resolution.

Không cần khẳng định hệ dùng Raft/Paxos nội bộ nếu sản phẩm không công bố.

### 21.1. DynamoDB

`ConditionExpression` cho conditional writes trên item, `TransactWriteItems` cho multi-item transactions trong giới hạn. Global tables có semantics khác nhau theo tính năng/configuration; một conditional write ở một region không mặc định là global consensus commit trên mọi mode.

### 21.2. Cosmos DB for NoSQL

Có strong/bounded-staleness/session/consistent-prefix/eventual consistency models, transactional batch theo scope hỗ trợ, thường gắn logical partition. Session consistency không tự là transaction mạnh xuyên mọi regions/partitions.

### 21.3. Firestore

Có transactions và preconditions, với concurrency behavior theo SDK/backend/cấu hình. Nên chọn primitive dựa trên yêu cầu invariant thay vì đoán chi tiết leader/election nội bộ.

**Quy tắc:** chỉ hứa bảo đảm đúng với API, region, edition và phiên bản đang dùng.

## 22. Consensus không tự làm mọi read linearizable

Một Raft log đã committed tới index 100, nhưng follower C mới apply tới 96:

```text
Leader A:      applied 100
Follower B:    applied 100
Follower C:    applied 96
```

Nếu đọc trực tiếp tại C mà không có yêu cầu đủ mới, client có thể thấy trạng thái cũ.

### 22.1. Leader cũ và stale reads

Leader bị cô lập có thể không biết một leader mới đã được bầu. Muốn linearizable reads, hệ cần read protocol xác nhận quyền/độ mới như ReadIndex hoặc leader lease dưới giả định phù hợp.

### 22.2. Search/cache còn ở ngoài

Một source write đã consensus commit không khiến Elasticsearch, Redis cache hoặc analytical projection tự cập nhật ngay. Mỗi read model có freshness/ordering/reconciliation contract riêng.

### 22.3. Linearizable một key khác serializable nhiều keys

Một update có điều kiện trên key K không tự biến cặp mutation K1/K2 thành một atomic transaction.

## 23. Replicated, committed, applied, visible và durable

| Mốc | Ý nghĩa |
|---|---|
| Accepted | Một node tiếp nhận request |
| Locally written | Mutation/log tồn tại tại một nơi |
| Replicated | Một số bản sao đã nhận mutation/log |
| Committed | Giao thức đã quyết định entry theo safety contract |
| Applied | State machine thực thi entry |
| Visible | Đường read đã thấy kết quả |
| Durable | Write sống sót trước những lỗi đã được cam kết |

Một entry có thể **committed nhưng follower chưa applied**. Một primary có thể **ACK cục bộ nhưng write chưa majority-durable**. Một order có thể **committed ở source nhưng chưa có trong search**.

Khi API trả `200 OK`, cần xác định chính xác mốc nào đã được đạt, và business action nào thực sự hoàn tất.

## 24. Consensus trên một partition không phải transaction nhiều partitions

Ví dụ chuyển tiền:

```text
Account A = 100 (consensus group G1)
Account B = 100 (consensus group G2)
```

Client thực hiện:

```text
G1: debit A by 30 -> committed
G2: credit B by 30 -> timeout
```

Mỗi group có thể giữ một committed history hợp lệ, nhưng tổng A+B chưa chắc được cập nhật nguyên tử.

Giải pháp tùy use case:

- Gom invariant vào một aggregate có authority chung.
- Dùng multi-partition transaction nếu hệ hỗ trợ đúng scope.
- Dùng transaction coordinator phù hợp.
- Dùng ledger/reservation/saga với recovery và reconciliation.
- Dùng idempotency key để không thực hiện một nửa workflow nhiều lần.

### 24.1. 2PC không đồng nghĩa Raft/Paxos

Two-phase commit có prepare/commit để điều phối atomic commit qua participants; consensus giải quyết đồng ý quyết định/chuỗi quyết định theo mô hình lỗi. Có hệ kết hợp chúng, nhưng chúng không là cùng thuật toán.

### 24.2. Snapshot isolation không tự chặn mọi invariant

Ngay cả hệ có transaction snapshot, **write skew** vẫn có thể xảy ra nếu hai transaction ghi vào hai records khác nhau dựa trên cùng một predicate. Cần serializable isolation, aggregate authority hoặc constraint phù hợp.

## 25. Leader/lease và fencing token

Giả sử worker A có quyền xử lý report:

```text
T0: A nhận lease generation=41
T1: A bị pause 60 giây
T2: Lease A hết hạn
T3: B nhận lease generation=42
T4: B ghi report vào sink
T5: A thức dậy và ghi report cũ
```

Consensus/coordination service có thể xác nhận rằng **B là owner hiện hành**, nhưng không ép A đã bị pause phải tự dừng.

### 25.1. Resource-side fencing

Sink lưu `lastAcceptedGeneration=42`:

```text
Write token=41 -> REJECT stale
Write token=42 -> ACCEPT theo điều kiện nghiệp vụ
```

Điều kiện kiểm tra phải **nguyên tử cùng thao tác ghi ở sink**.

### 25.2. Owner token khác generation

- UUID owner: nhận diện một attempt để release/renew đúng holder.
- Fencing generation: số thế hệ tăng đơn điệu để chặn stale owner.
- Business version: phiên bản đối tượng.
- Idempotency key: nhận diện cùng ý định nghiệp vụ khi retry.

Một UUID ngẫu nhiên không tự cho biết ai là owner mới hơn.

### 25.3. Generation phải được cấp an toàn

Nếu counter cấp generation có thể rollback sau failover, không thể mặc định nó luôn tăng. Cần authority có contract phù hợp về thứ tự thế hệ.

## 26. Java: interface minh họa ranh giới authority/sink

```java
import java.time.Instant;
import java.util.Optional;

public interface WriteAuthority {

    record Grant(
            String resourceId,
            String ownerId,
            long generation,
            Instant expiresAt
    ) {}

    Optional<Grant> tryAcquire(
            String resourceId,
            String ownerId
    );

    boolean renew(Grant grant);

    boolean release(Grant grant);
}
```

Một caller minh họa:

```java
import java.util.Optional;
import java.util.UUID;

public final class ReportPublisher {
    private final WriteAuthority authority;
    private final ReportSink sink;

    public ReportPublisher(
            WriteAuthority authority,
            ReportSink sink
    ) {
        this.authority = authority;
        this.sink = sink;
    }

    public void publish(String reportId, String body) {
        String owner = UUID.randomUUID().toString();
        Optional<WriteAuthority.Grant> attempt =
                authority.tryAcquire(reportId, owner);

        if (attempt.isEmpty()) {
            return;
        }

        WriteAuthority.Grant grant = attempt.get();

        try {
            sink.writeIfNewer(
                    reportId,
                    body,
                    grant.generation()
            );
        } finally {
            authority.release(grant);
        }
    }

    public interface ReportSink {
        boolean writeIfNewer(
                String reportId,
                String body,
                long generation
        );
    }
}
```

**Giới hạn:**

- Đây là pseudocode-level architecture, không phải implementation Raft.
- Chưa có heartbeat/renew cho công việc dài.
- Chưa có cancellation khi mất lease.
- Chưa có idempotency/unknown commit.
- `writeIfNewer` phải được sink thực thi bằng một kiểm tra nguyên tử.
- `release` phải chỉ giải phóng đúng owner/generation.

Mục đích là cho thấy quyền được cấp tại coordinator chưa tự bảo vệ write vào một storage khác.

## 27. Đồng thuận không tự tạo exactly-once bên ngoài

```text
T0: Log consensus commit Job J100
T1: Worker A gọi provider, payment thành công
T2: Worker A crash trước khi ghi DONE
T3: Worker B nhận lại Job J100
T4: Worker B có thể gọi provider lần hai
```

Consensus không sai; job vẫn có lịch sử nhất quán. Nhưng payment provider là hệ ngoài transaction/log ấy.

Các biện pháp:

- Idempotency key ổn định ở payment provider.
- Durable workflow state.
- Outbox/inbox cho event delivery.
- Retry có giới hạn.
- Query/reconciliation khi result unknown.
- Compensation theo policy nếu nghiệp vụ cho phép.

**Một database dùng Raft không tự biến mọi email, payment hoặc shipment API thành exactly-once.**

## 28. Timeout không có nghĩa operation chưa commit

```text
Client -> Leader: Reserve(SEAT-100, U42)
Leader -> quorum: commit thành công
Leader -> Client: response bị mất
Client: timeout
```

Client không biết request đã commit hay chưa. Nếu retry thành một business command mới, có thể tạo duplicate side effect.

Dùng operation ID:

```json
{
  "operationId": "RESERVE-REQ-1001",
  "seatId": "SEAT-100",
  "userId": "U42"
}
```

Trong cùng atomic authority:

```text
IF operationId đã có kết quả:
    RETURN recorded result
ELSE:
    kiểm tra điều kiện business
    ghi state + operationId cùng một transaction
```

Nếu hệ trả `UNKNOWN`, API phải có đường tra cứu/reconciliation. Không được tự đổi timeout thành `FAILED` rồi cho user thực hiện payment mới vô điều kiện.

## 29. Thay đổi membership an toàn

Giả sử:

```text
Old voters: {A, B, C}
New voters: {D, E, F}
```

Nếu old/new groups cùng tự xem mình là authority mà không có chuyển đổi được đồng thuận, hai majorities có thể **không giao nhau**.

Raft có kỹ thuật **joint consensus** để chuyển giữa configurations theo quorum rules. Các sản phẩm khác có membership change procedures riêng.

### 29.1. Learners

Một node mới có thể nhận snapshot/log ở vai trò learner trước khi được nâng thành voter, giúp tránh node chưa bắt kịp làm ảnh hưởng voting set.

### 29.2. Không chỉ tăng node count

Thêm voters làm tăng network, disk, heartbeat, membership complexity. Với majority, N=3 và N=4 đều chỉ chịu được một node crash trong mô hình đơn giản. Nên chọn theo failure domains/SLO, không chỉ “nhiều hơn luôn tốt hơn”.

## 30. Snapshot, log compaction và backup

Consensus log có thể được rút gọn bằng snapshot của state machine:

```text
Log entries 1..100000
          |
          v
Snapshot state at index 100000
          |
          +--> log 100001, 100002, ...
```

Snapshot cần mang metadata index/term thích hợp để node mới/khôi phục tiếp tục đúng lịch sử.

Nhưng snapshot của một consensus group **không tự là backup đầy đủ của sản phẩm**. Nó có thể thiếu payment state, external files, read models, partitions khác.

Replication có thể lan truyền một lệnh DELETE sai tới mọi bản sao; consensus còn có thể commit lệnh sai đó rất chính xác. Cần backup/PITR, audit và quy trình recovery riêng.

## 31. Multi-region: placement và tính khả dụng

Ba voters, hai ở region East và một ở West:

```text
East: E1, E2
West: W1
```

Nếu West mất, East vẫn có majority. Nếu East mất hoàn toàn, West chỉ còn một voter, không thể commit theo majority.

Đặt voters qua nhiều regions giúp chịu lỗi failure domains nhưng có thể tăng WAN latency cho quorum commit.

### 31.1. Active–active eventual khác global consensus

Hai regions độc lập ACK local writes rồi resolve conflict về sau không mặc định có total order toàn cục trước ACK.

### 31.2. Quyền tiêu thụ được phân bổ trước

Ví dụ total inventory 100, region A quota 60 và region B quota 40:

```text
Total = 100
A allocation = 60
B allocation = 40
```

Khi liên vùng mất mạng, mỗi vùng chỉ được dùng quota đã cấp. Đây là cách điều chỉnh **mô hình quyền ghi** để cải thiện availability mà vẫn giữ invariant, nếu cấp và chuyển quota an toàn.

### 31.3. Không suy từ tên multi-region

Một managed NoSQL có thể cung cấp eventual, session hoặc strong consistency theo những cấu hình khác nhau. Phải kiểm tra chính xác API/region topology.

## 32. CAP, consistency và suy giảm dịch vụ

Khi mạng chia cắt, một nhóm thiếu consensus quorum có thể phải từ chối writes để giữ safety.

Nhưng một website không cần tắt toàn bộ:

| Chức năng | Khi authority unreachable |
|---|---|
| Catalog công khai | Có thể đọc cache/replica stale có giới hạn |
| Recommendations | Fallback sang nội dung phổ biến |
| Đặt ghế cuối cùng | Không xác nhận ownership mới |
| Inventory reserve | Không dựa vào stale value để commit |
| Payment | PENDING/UNKNOWN và reconciliation |
| ACL/quản trị | Fail closed nếu không kiểm tra được quyền |
| Analytics | Hiển thị watermark/dữ liệu trễ có nhãn |

Nếu dùng `202 Accepted`, request intent phải được lưu đủ bền vững theo hợp đồng; không được thông báo đã tiếp nhận khi request chỉ có trong RAM.

## 33. Latency và chi phí consensus

Quorum commit thường có thêm các bước:

```text
Client -> Leader
Leader -> Followers
Followers -> Leader ACK
Leader -> Client result
```

Chi phí có thể gồm:

- Network RTT và WAN jitter;
- Disk/log persistence;
- Heartbeat/election;
- Leader contention;
- Quorum availability;
- Retry khi term thay đổi;
- Tail latency khi follower chậm.

Không nhất thiết dùng một global consensus group cho mọi read recommendations. Có thể:

- Dùng authority mạnh cho inventory;
- Session consistency cho profile;
- Eventual replication cho catalog;
- Asynchronous projections cho analytics;
- Consensus cho metadata, leases và những business claims cần một quyết định.

**Quorum=2 trong hai hệ khác nhau không đồng nghĩa latency và durability giống nhau**, vì protocol, disk, batching và read path khác nhau.

## 34. Case study: đặt ghế cuối cùng

### Thiết kế sai: nhận xung đột rồi chọn winner sau

```text
East: reserve X -> CONFIRMED
West: reserve Y -> CONFIRMED
Reconnect -> last-writer-wins chọn Y
```

Dữ liệu cuối cùng nhất quán nhưng đã xác nhận sai cho X.

### Thiết kế bằng atomic conditional authority

```text
IF Seat(SEAT-100).owner does not exist:
    owner := userId
    result := CLAIMED
ELSE:
    result := TAKEN
```

Điều kiện và mutation phải là **một atomic operation** tại authority phù hợp.

### Thiết kế bằng consensus log

```text
Command 1: Reserve(SEAT-100, X)
Command 2: Reserve(SEAT-100, Y)
             |
             v
Log consensus decides order
             |
             v
Deterministic state machine:
   first valid claim -> CLAIMED
   subsequent claim -> TAKEN
```

Trả success sau commit/result hợp lệ, không phải khi leader chỉ vừa nhận request.

### Có cần tự viết Raft?

Thông thường không, nếu database cung cấp conditional write/transaction với scope đáp ứng invariant. Tự triển khai consensus là công việc hệ phân tán khó, cần kiểm tra safety, elections, membership, persistence và recovery.

## 35. Case study: ACK rồi mất write sau failover

### Replication mode với ACK sớm

```text
Primary A ghi K=v2
A ACK locally
A hỏng trước khi followers nhận
Follower B được promote
B vẫn có K=v1
```

Tùy hợp đồng, write đã ACK có thể bị rollback.

### Consensus committed log

```text
Leader A đề xuất K=v2
Entry đạt commit condition qua quorum
Client nhận commit ACK
A hỏng
Leader mới duy trì committed history
```

Trong mô hình lỗi được hỗ trợ và implementation đúng, committed history được bảo vệ không bị thay thế bởi history mâu thuẫn.

### Những điều vẫn phải hỏi

- Storage/journal có ghi bền theo contract không?
- Đã vượt fault-tolerance assumptions chưa?
- Read từ follower có cần catch-up không?
- Search/cache có lag không?
- External payment side effect đã thật sự thành công chưa?

## 36. Những ngộ nhận phổ biến

**“Có ba replicas nghĩa là dùng consensus.”** Sai; sao chép có thể bất đồng bộ hoặc giải quyết xung đột sau.

**“Có leader nghĩa mọi writes dùng Raft.”** Sai; nhiều sản phẩm có cơ chế election/replication khác.

**“Có chữ QUORUM nghĩa là Paxos.”** Sai; voting/acceptance protocol gồm nhiều quy tắc hơn đếm ACK.

**“R+W>RF chứng minh mọi concurrent operations linearizable.”** Không tự động.

**“Entry xuất hiện trên một follower là committed.”** Không; phải thỏa commit rule.

**“Consensus luôn available khi có một node sống.”** Không; thiếu majority có thể dừng commit.

**“Timestamp lớn là leader mới.”** Không; clock không thay term/ballot/log matching.

**“Raft làm tất cả follower reads linearizable.”** Không; follower có thể chưa apply.

**“Consensus tạo transaction atomic xuyên mọi partitions.”** Không; cần transaction coordinator/scope.

**“Consensus ngăn external email/payment duplicate.”** Không; cần idempotency.

**“Timeout nghĩa chưa commit.”** Không; response có thể mất sau commit.

**“Redis Sentinel quorum làm mọi SET thành Raft commit.”** Không.

**“MongoDB w:majority khiến mọi secondary read luôn mới nhất.”** Không.

**“Cassandra regular QUORUM đảm bảo check-then-write atomic.”** Không; dùng LWT/conditional operation.

**“Repair sửa hai business confirmations đã phát.”** Không.

**“Global multi-region replication luôn strong toàn cầu.”** Không mặc định.

**“Thêm voters luôn làm hệ chịu lỗi tốt hơn.”** Không nếu majority/placement không đổi mức fault tolerance.

**“Có replication thì không cần backup.”** Không; xóa/corruption được sao chép cũng gây mất dữ liệu.

## 37. Monitoring: biết hệ đang kẹt ở đâu

| Nhóm | Metric gợi ý | Câu hỏi |
|---|---|---|
| Quorum | Số voting members reachable | Còn majority không? |
| Leader | Term, election count/duration | Leader có ổn định không? |
| Log | Proposed, replicated, commit index | Entry có kẹt trước commit không? |
| Apply | Applied index lag | Follower đọc stale vì chưa apply? |
| Replication | Backlog bytes, replica lag | Data copies đã bắt kịp chưa? |
| Storage | WAL/fsync errors | Có rủi ro durability không? |
| Network | RTT, packet loss, partitions | Quorum có bị chia cắt/chậm? |
| API | Timeout, conflict, unknown | Client thấy outcome gì? |
| Fencing | Rejected stale-owner writes | Sink có chặn leader cũ? |
| Membership | Voters/learners changes | Cấu hình có được đổi an toàn? |
| Business | Double booking, double charge | Bất biến có vi phạm không? |
| Projection | Read model version lag | Search/cache có stale không? |

Một dashboard chỉ hiển thị replica lag bằng 0 **không chứng minh business correctness**.

## 38. Kiểm thử replication khác kiểm thử consensus

### 38.1. Kiểm thử replication

1. Ghi K=v2.
2. Ngắt một replica.
3. Quan sát lag.
4. Khôi phục replica.
5. Kiểm tra handoff/repair/backfill.
6. Xác minh trạng thái hội tụ theo hợp đồng.

### 38.2. Kiểm thử consensus

1. Cho nhiều clients đề xuất commands xung đột.
2. Ngắt leader khỏi majority.
3. Bầu leader mới ở phía đủ quorum.
4. Xác minh không có hai committed histories mâu thuẫn.
5. Khôi phục leader cũ.
6. Xác nhận committed entries không bị thay thế.
7. Thử membership changes.
8. Đo tiến triển khi quorum phục hồi.

### 38.3. Kiểm thử stale writer

A có generation 41 rồi bị pause; B được cấp generation 42 và ghi sink; A chạy lại với 41. Sink phải reject stale generation theo contract.

### 38.4. Kiểm thử unknown commit

Server commit request nhưng chặn response. Client timeout rồi retry cùng operation ID; business effect không được nhân đôi.

### 38.5. Kiểm thử external side effect

Worker charge provider thành công rồi crash trước khi ghi DONE. Worker khác retry; provider/ledger phải tránh charge trùng theo idempotency contract.

### 38.6. Hạn chế chaos tests

Không tự ý phân hoạch mạng, restore snapshots cũ hay kill majority trên production. Dùng staging/test environment, dữ liệu giả, rollback và công cụ ghi operation histories.

## 39. Bài tập thực hành

### Bài tập 1 — Replication hay consensus?

A sao chép changes sang B bất đồng bộ, không có voting/term/log commit.

**Câu hỏi:** Đây là gì?

**Gợi ý:** Replication, chưa đủ để gọi consensus.

### Bài tập 2 — Ghế bị xác nhận trùng

East và West cùng trả CONFIRMED rồi LWW chọn East.

**Câu hỏi:** Tại sao kết quả cuối chỉ có một owner vẫn sai?

**Gợi ý:** Hai business confirmations đã mâu thuẫn trước khi hội tụ.

### Bài tập 3 — Quorum N=3

Majority cần mấy votes? Hai quorums có giao nhau không?

**Gợi ý:** 2; mọi tập 2/3 đều giao nhau.

### Bài tập 4 — Quorum N=5

Nhóm chịu tối đa bao nhiêu node crash nếu các node còn lại liên lạc được?

**Gợi ý:** 2; còn 3 tạo majority.

### Bài tập 5 — Partition 2–2

Bốn voters bị chia hai phía 2–2.

**Câu hỏi:** Phía nào được commit theo majority?

**Gợi ý:** Không phía nào.

### Bài tập 6 — Entry chưa commit

Leader append log entry 42 cục bộ rồi mất majority.

**Câu hỏi:** Có thể trả success ngay không?

**Gợi ý:** Không; phải đạt commit rule.

### Bài tập 7 — Follower stale

Log committed tới 100 nhưng follower mới applied tới 97.

**Câu hỏi:** Đọc follower có thể cũ không?

**Gợi ý:** Có nếu không chờ mốc/read protocol thích hợp.

### Bài tập 8 — Leader cũ

A mất lease, B nhận lease mới; A thức dậy vẫn ghi.

**Câu hỏi:** Cần bảo vệ gì?

**Gợi ý:** Fencing token tại sink.

### Bài tập 9 — Cassandra regular QUORUM

Hai clients cùng đọc `owner=null` rồi regular write owner khác nhau với QUORUM.

**Câu hỏi:** Quorum có tự đảm bảo chỉ một claim không?

**Gợi ý:** Không, cần conditional mutation/LWT.

### Bài tập 10 — Cassandra LWT

`INSERT ... IF NOT EXISTS` trả `[applied]=false`.

**Câu hỏi:** Claim có thành công không?

**Gợi ý:** Không.

### Bài tập 11 — MongoDB w:1

Primary ACK w:1 rồi chết trước replication.

**Câu hỏi:** Điều gì có thể xảy ra?

**Gợi ý:** Write có thể bị rollback tùy failover.

### Bài tập 12 — Redis Sentinel

Team nói mọi SET đều là Raft consensus vì Sentinel dùng quorum.

**Câu hỏi:** Sai ở đâu?

**Gợi ý:** Quorum failover khác data mutation consensus.

### Bài tập 13 — etcd CAS

Hai processes cùng muốn tạo một claim key chưa có.

**Câu hỏi:** Vì sao compare-and-put an toàn hơn GET rồi PUT?

**Gợi ý:** Check và ghi là một operation quyết định nguyên tử tại authority.

### Bài tập 14 — Chuyển tiền giữa hai groups

Debit ở G1 commit, Credit ở G2 timeout.

**Câu hỏi:** Hai group đều dùng Raft thì transfer đã atomic chưa?

**Gợi ý:** Chưa, cần transaction/workflow.

### Bài tập 15 — Lost ACK

Server đã commit nhưng client timeout.

**Câu hỏi:** Cách retry nào an toàn?

**Gợi ý:** Operation ID/idempotency, tra kết quả đã commit.

### Bài tập 16 — Payment exactly-once

Worker charge thành công rồi crash, worker mới retry.

**Câu hỏi:** Consensus có ngăn duplicate charge không?

**Gợi ý:** Không; provider idempotency/reconciliation.

### Bài tập 17 — Multi-region uniqueness

Hai regions cùng ACK cùng username trước replication.

**Câu hỏi:** Có thể hứa global uniqueness chưa?

**Gợi ý:** Không nếu chưa có authority/coordination thích hợp.

### Bài tập 18 — Membership change

Chuyển voters A/B/C sang D/E/F bằng sửa config riêng rẽ.

**Câu hỏi:** Nguy cơ gì?

**Gợi ý:** Hai majority không giao nhau; cần membership protocol.

### Bài tập 19 — Backup

Một DELETE nhầm đã consensus commit trên mọi replica.

**Câu hỏi:** Raft có tự lấy lại dữ liệu không?

**Gợi ý:** Không; backup/PITR.

### Bài tập 20 — Mất majority

Nhóm 3 voters chỉ còn 1 node reachable.

**Câu hỏi:** Có thể commit log mới không?

**Gợi ý:** Không theo majority thông thường.

### Bài tập 21 — Đọc stale ở search

Source commit Order=PAID, search chưa refresh.

**Câu hỏi:** Có chứng minh source consensus sai không?

**Gợi ý:** Không, projection có đường đồng bộ riêng.

### Bài tập 22 — Causal ordering

Một comment phải xuất hiện sau bài viết mà nó trả lời.

**Câu hỏi:** Có bắt buộc một global Raft log không?

**Gợi ý:** Không, cân nhắc causal/session guarantee đúng phạm vi.

### Bài tập 23 — Quota vùng

Total inventory=100, A quota=60, B=40. A hết quota khi mất mạng, B còn 20.

**Câu hỏi:** A có thể tự bán thêm không?

**Gợi ý:** Không nếu không có chuyển quota an toàn.

### Bài tập 24 — Read visibility

Một entry đã committed nhưng follower chưa applied.

**Câu hỏi:** Khác biệt giữa commit và visible là gì?

**Gợi ý:** Quyết định đã an toàn chưa đồng nghĩa mọi read path nhìn thấy.

### Bài tập 25 — Thiết kế end-to-end

Một sản phẩm gồm catalog, inventory, payment, analytics và admin permissions.

**Yêu cầu:** Xác định nơi nào có thể eventual, nơi nào cần authority/transaction, nơi nào cần idempotency và nơi nào fail closed.

**Gợi ý:** Catalog/analytics có thể stale theo SLO; inventory cần reservation atomic; payment cần idempotency/ledger; permissions cần authoritative revocation policy.

## 40. Checklist trước production

- [ ] Đã mô tả invariant và phạm vi cần bảo vệ.
- [ ] Đã phân biệt replication với consensus.
- [ ] Biết primary/leader/follower/coordinator thực sự làm gì.
- [ ] Biết ACK ở local write, replica receipt hay commit.
- [ ] Biết replica nào có thể stale.
- [ ] Không coi read/write quorum tự động là Raft/Paxos.
- [ ] Hiểu term/ballot, voting, log matching và commit rules khi dùng consensus.
- [ ] Biết quorum size, voters và failure-domain placement.
- [ ] Có hành vi an toàn khi mất majority.
- [ ] Phân biệt replicated, committed, applied, visible và durable.
- [ ] Có read protocol phù hợp khi cần linearizability.
- [ ] Đã xác định transaction scope có đủ invariant không.
- [ ] Có fencing ở external sink nếu stale leader nguy hiểm.
- [ ] Có operation ID/idempotency cho unknown commit.
- [ ] Có idempotency/reconciliation cho payment/email.
- [ ] Không dùng repair/replication để biện minh business conflicts đã ACK.
- [ ] Có quy trình membership change an toàn.
- [ ] Có backup/PITR độc lập với replication.
- [ ] Có metrics election/quorum/replication/apply lag.
- [ ] Có test partition, failover, old leader, lost ACK.
- [ ] Có test external side effects và retry.
- [ ] Đã đối chiếu bảo đảm với đúng phiên bản/configuration sản phẩm.

## 41. Tổng kết

**Sao chép dữ liệu** giúp một hệ NoSQL lưu dữ liệu ở nhiều nơi để chịu lỗi, giảm latency hoặc phục vụ đọc. Các bản sao có thể chậm, tạm khác nhau hoặc cần conflict resolution.

**Giao thức đồng thuận** như Raft và các biến thể Paxos giúp các thành viên thống nhất một quyết định hoặc một lịch sử có thứ tự trong phạm vi và mô hình lỗi được thiết kế. Consensus thường dùng log replication, nhưng **replication không tự nghĩa consensus**. Khi thiếu quorum, hệ có thể phải ngừng commit để giữ safety.

Những phân biệt quan trọng khi xây NoSQL:

1. **Read/write quorum của replica store** khác **voting/acceptor quorum của consensus**.
2. **Replicated** khác **committed, applied, visible và durable**.
3. **Leader election** khác quyền ghi vào external sink; stale leader có thể cần fencing.
4. **Consensus theo key/partition/log** không tự tạo multi-partition transaction.
5. **Dữ liệu cuối cùng hội tụ** không tự làm đúng những business confirmations trái nhau đã xảy ra.
6. **Log consensus đúng** không tự làm payment/email exactly-once.

Đừng tự triển khai Raft cho mọi tính năng nếu database đã cung cấp conditional write hoặc transaction đáp ứng invariant. Hãy chọn theo **hợp đồng của API thực tế, ranh giới dữ liệu, quyền ghi, failover, đường đọc và side effect**.

**Nguyên tắc cốt lõi:** *Replication trả lời “dữ liệu được sao chép đi đâu”; consensus trả lời “những thành viên được phép thống nhất điều gì, theo thứ tự nào và khi nào quyết định an toàn”.* Mọi ranh giới vượt ngoài bảo đảm đó phải được bảo vệ bằng transaction, fencing, idempotency hoặc workflow phục hồi thích hợp.

