# Vai trò leader, term/epoch và quá trình bầu chọn

Trong một hệ **Database No SQL phân tán**, nhiều node cùng giữ bản sao dữ liệu nhưng không phải node nào cũng có quyền quyết định ghi vào cùng một tập dữ liệu tại mọi thời điểm. Ở nhiều kiến trúc, một **leader** điều phối thứ tự thay đổi, gửi log tới follower và xác định khi nào có thể thông báo thành công theo giao thức. Khi leader mất liên lạc hoặc lỗi, hệ thống phải **bầu chọn** người điều phối mới mà vẫn bảo toàn những thay đổi đã commit.

Tình huống tưởng đơn giản: A là leader, B và C là follower. A bị tách khỏi B và C. B, C bầu B làm leader mới. Trong khi đó, A chưa nhận được thông báo thay đổi và vẫn tự coi mình là leader. Nếu các client hoặc hệ thống bên ngoài tin cả A lẫn B đều có quyền ghi, dữ liệu có thể bị xung đột hoặc side effect bị lặp.

Bài thuộc chương **Đồng thuận và quyền ghi** của **Database No SQL**. Nội dung đi từ khái niệm leader, majority và term/epoch tới **quá trình bầu chọn**, điều kiện log đủ mới, commit, phân vùng mạng, split-brain, fencing token, MongoDB replica set, Paxos/LWT, đọc từ leader, timeout và idempotency.

> Quyền leader không được quyết định chỉ bằng cờ `isLeader=true` ở một node. Nó phải được xác lập bằng một giao thức có quyền biểu quyết, thế hệ logic và những quy tắc bảo toàn lịch sử đã commit.

## 1. Leader là gì?

Trong một **replicated state machine** dùng leader, một node đảm nhiệm việc điều phối các thay đổi cho một tập replica.

~~~mermaid
flowchart LR
    Client["Application"] --> L["Leader A"]
    L --> B["Follower B"]
    L --> C["Follower C"]
    B -. "Replication ACK" .-> L
    C -. "Replication ACK" .-> L
~~~

Trong những giao thức kiểu Raft, leader có thể:

1. Nhận command từ client.
2. Ghi command vào log có thứ tự.
3. Sao chép entry tới follower.
4. Theo dõi acknowledgments.
5. Quyết định commit index theo protocol.
6. Hướng dẫn follower áp dụng committed entries.
7. Gửi heartbeat và theo dõi trạng thái replication.
8. Từ chối hoặc chuyển hướng request khi mất authority.

Leader không nhất thiết là node duy nhất phục vụ đọc. Một số hệ cho follower reads với consistency khác nhau. Cũng không phải mọi NoSQL đều có mô hình leader cố định cho mọi write.

## 2. Phạm vi của leader

Leadership có thể gắn với:

- Một replica set.
- Một shard dữ liệu.
- Một partition hoặc range.
- Một consensus group lưu metadata.
- Một nhóm worker xử lý queue.
- Một resource cần độc quyền quyền ghi.

Ví dụ:

~~~text
Shard 1 -> leader A1, followers B1/C1
Shard 2 -> leader B2, followers A2/C2
Shard 3 -> leader C3, followers A3/B3
~~~

Ba leader cùng tồn tại hoàn toàn bình thường vì **chúng sở hữu ba phạm vi độc lập**. Split-brain đáng lo là hai phía cùng hành xử như quyền ghi của một phạm vi có thể được commit trái nhau.

Khi phân tích log lỗi, phải luôn ghi cùng lúc:

~~~text
groupId
leaderId
termOrEpoch
memberConfiguration
commitPosition
~~~

Chỉ một giá trị `leaderId` không đủ mô tả authority.

## 3. Leader khác primary, coordinator và owner

| Vai trò | Ý nghĩa | Có luôn là leader đồng thuận không? |
|---|---|---|
| Leader | Điều phối log/decision trong nhóm đồng thuận | Theo loại giao thức |
| Primary | Node nhận write chính trong hệ primary–secondary | Không đồng nghĩa chi tiết Raft |
| Coordinator | Node nhận request và liên lạc các replica | Có thể không giữ leadership lâu dài |
| Partition owner | Thành phần chịu trách nhiệm một partition | Có thể dùng lease/epoch hoặc protocol khác |
| Cluster manager | Điều phối metadata/topology | Không tự là leader cho mọi shard |
| Transaction coordinator | Phối hợp transaction | Không tự là data leader |
| Lock holder | Worker đang giữ lock | Không tự có majority quyền ghi |

MongoDB dùng khái niệm **primary** trong replica set; Cassandra dùng **coordinator** cho read/write thông thường mà không có một primary duy nhất toàn cluster. Bởi vậy không thể dùng một sơ đồ election áp nguyên xi cho mọi NoSQL.

## 4. Vì sao phải bầu lại leader?

Một node có thể:

- Crash hoặc ngừng process.
- Mất network tới đa số member.
- Bị tạm dừng vì GC hoặc disk stall.
- Bị bảo trì và chủ động step down.
- Mất eligibility sau thay đổi membership.
- Bị thay theo priority/placement policy.
- Không đủ khả năng duy trì quorum để commit.

Nếu không thể thay người điều phối, cluster sẽ dừng ghi dù vẫn còn đủ node khỏe. Bầu chọn giúp tiếp tục tiến trình khi điều kiện quorum cho phép.

Nhưng **bầu nhanh** không có nghĩa **bầu an toàn**. Một node có log quá cũ có thể không đủ điều kiện làm leader dù nó phản hồi nhanh nhất.

## 5. Safety, liveness và availability

**Safety:** những entry đã commit không được bị thay thế bằng lịch sử trái với bảo đảm đồng thuận. Hai phía không được commit các quyết định mâu thuẫn cho cùng state machine nếu protocol và fault model được tuân thủ.

**Liveness:** nếu đủ node hoạt động và mạng đủ ổn định, hệ cuối cùng có thể bầu leader và tiếp tục commit.

**Availability:** một request cụ thể có được phục vụ trong deadline hay không.

Dưới network partition, một nhóm không có quorum có thể phải từ chối ghi để giữ safety. Điều này làm giảm availability của nhóm đó nhưng không nhất thiết là bug.

Cần tách:

~~~text
Node is alive   != node has leadership
Node is leader  != node has reachable quorum
Write received  != write committed
Read local      != linearizable read
~~~

## 6. Term là gì?

**Term** trong Raft là một số nguyên logic tăng qua những vòng bầu cử của **một consensus group**.

Ví dụ:

~~~text
Term 12: leader A
Term 13: leader C
Term 14: leader B
~~~

Term không phải timestamp; term 13 không có nghĩa bầu cử diễn ra lúc 13 giờ.

Term giúp:

- Nhận diện thông điệp từ thế hệ cũ.
- Phát hiện candidate hoặc leader bị lỗi thời.
- Gắn thế hệ với log entry.
- Cho node biết khi nào phải cập nhật trạng thái và step down.
- Phục vụ phân tích failover và lịch sử election.

Mỗi group có logic term riêng; term 9 của Shard X không tự so sánh authority với term 9 của Shard Y.

## 7. Epoch có nghĩa thế nào?

**Epoch** là tên tổng quát hơn cho một **thế hệ logic** của quyền sở hữu, leader hoặc cấu hình.

Các hệ có thể dùng:

- Leader epoch.
- Election epoch.
- Configuration epoch.
- Generation/owner epoch.
- Fencing token.
- Ballot number.

Những khái niệm này giống nhau ở trực giác **thế hệ mới hơn vượt thế hệ cũ**, nhưng quy tắc cấp và so sánh tùy giao thức. Không khẳng định mọi “epoch” trong mọi database có chính xác semantics của Raft `currentTerm`.

Một epoch muốn bảo vệ quyền ghi phải:

1. Được cấp bởi nguồn có thẩm quyền.
2. Tăng/tiến theo thứ tự không bị đảo ngược tùy tiện.
3. Gắn đúng resource/group.
4. Được kiểm tra khi thực hiện operation.
5. Sống sót qua crash/restart theo protocol.

## 8. Term khác log index và commit index

Trong Raft có các khái niệm:

| Trường | Vai trò |
|---|---|
| `currentTerm` | Term mới nhất mà node biết |
| `votedFor` | Candidate mà node đã bỏ phiếu trong term |
| `log[index].term` | Term của leader đã tạo log entry đó |
| `commitIndex` | Entry index cao nhất đã commit theo protocol |
| `lastApplied` | Entry index cao nhất được áp vào state machine |
| `leaderId` | Leader mà node đang tin là hợp lệ theo trạng thái local |

Ví dụ log:

~~~text
Index  :  41  42  43  44  45
Term   :   8   8   9   9  10
Command:   A   B   C   D   E
~~~

Một leader term 10 vẫn có thể chứa entry được tạo ở term 8 và 9. **Tăng term không làm index bắt đầu lại từ 0 và không xóa log đã commit.**

## 9. Điều gì được lưu bền vững?

Trong thuật toán Raft, những state như `currentTerm`, `votedFor` và log phải được persist theo các quy tắc protocol trước khi một số response được gửi.

Tại sao?

Giả sử node C bỏ phiếu cho B trong term 20 rồi crash. Nếu sau restart C quên phiếu đó và bỏ phiếu cho D cùng term 20, quy tắc “một phiếu mỗi term” đã bị phá.

Không được triển khai election thực chỉ bằng những biến RAM không có persistence tương ứng. Việc khôi phục từ snapshot/backup cũng không được làm node quên generation theo cách cho phép vote lại không hợp lệ.

## 10. Các role của Raft

Mô hình lõi:

- **Follower:** theo leader, nhận append/heartbeat và xét phiếu bầu.
- **Candidate:** bắt đầu election khi timeout theo điều kiện.
- **Leader:** đạt majority và điều phối replication trong term.

~~~mermaid
stateDiagram-v2
    [*] --> Follower
    Follower --> Candidate: election timeout
    Candidate --> Leader: majority votes
    Candidate --> Candidate: timeout / term mới
    Candidate --> Follower: nhận authority term cao hơn
    Leader --> Follower: thấy term cao hơn hoặc step down
~~~

Một process đang offline không phải role Raft lõi thứ tư. Nó là trạng thái vận hành ngoài state machine election.

## 11. Heartbeat để làm gì?

Leader gửi thông điệp replication/AppendEntries có thể không mang entry mới, thường gọi là **heartbeat**.

~~~text
Leader A -> Follower B: heartbeat(term=12)
Leader A -> Follower C: heartbeat(term=12)
~~~

Heartbeat giúp follower biết leader vẫn liên lạc và thường reset election timeout khi hợp lệ.

Nhưng:

- Heartbeat không phải bằng chứng mọi write đã commit.
- HTTP health check không thay thế heartbeat protocol.
- Node có thể trả health check OK dù mất quorum.
- GC pause, disk stall và network jitter có thể làm heartbeat đến muộn.
- Một heartbeat cũ mang term thấp không có authority khi node đã biết term cao hơn.

## 12. Election timeout và split vote

Nếu hai follower timeout gần như đồng thời, cả hai có thể trở thành candidate:

~~~text
B tự vote cho B
C tự vote cho C
Chưa ai đạt majority
~~~

Raft dùng **randomized election timeout** để giảm khả năng các candidate bắt đầu cùng thời điểm và chia phiếu lặp lại.

Timeout quá thấp dễ làm election storm khi network dao động; timeout quá cao làm failover chậm. Không có giá trị mili giây phổ quát tối ưu cho mọi cluster. Cần đo thực tế latency, GC pause, storage stalls và fault model.

Randomized timeout chủ yếu cải thiện **liveness**, không tự thay thế các luật safety.

## 13. Bầu leader mới trong group ba voter

Giả sử A là leader term 7; B và C không nhận heartbeat hợp lệ từ A.

~~~mermaid
sequenceDiagram
    participant A as Leader A
    participant B as Follower B
    participant C as Follower C
    Note over B,C: A mất liên lạc
    B->>B: Timeout, currentTerm=8
    B->>B: Vote cho B
    B->>C: RequestVote(term 8, log metadata)
    C-->>B: Vote nếu đủ điều kiện
    B->>B: Majority 2/3
    B->>C: AppendEntries / heartbeat term 8
    Note over A: A có thể chưa biết term mới
~~~

Nếu C cấp phiếu hợp lệ và B có log đủ mới, B có thể trở thành leader term 8. A vẫn có thể nghĩ mình là leader term 7 vì thông điệp bị ngắt, nhưng **A một mình không có majority hai trên ba để commit write mới theo Raft**.

## 14. Majority cần bao nhiêu phiếu?

Với N voter trong membership cố định:

\[
Q=\left\lfloor\frac{N}{2}\right\rfloor+1
\]

| Số voter N | Majority Q | Voter có thể không phản hồi theo phép đếm |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |

Đây là tính toán quorum trong nhóm cố định, không phải cam kết availability dưới mọi network partition, topology hoặc timeout.

Hai tập majority của cùng membership luôn giao nhau. Nếu mỗi node chỉ bỏ một phiếu trong một term, hai candidate khác nhau không thể cùng thu được hai majority hợp lệ trong **cùng term** theo luật election.

## 15. Vì sao phiếu bầu cần điều kiện log freshness?

Nếu chỉ bầu node có IP nhỏ nhất hoặc phản hồi nhanh nhất, có thể chọn node có log thiếu những thay đổi đã commit.

RequestVote trong Raft thường mang:

~~~text
candidateId
candidateTerm
lastLogIndex
lastLogTerm
~~~

Voter xét:

1. Term candidate hợp lệ không?
2. Voter đã bỏ phiếu cho ai trong term này?
3. Log candidate có đủ mới theo quy tắc Raft không?

Raft xét `lastLogTerm` trước, sau đó mới xét `lastLogIndex` nếu term bằng nhau.

Ví dụ:

~~~text
Candidate X: lastLogTerm=8, lastLogIndex=30
Voter Y:     lastLogTerm=7, lastLogIndex=45
~~~

Theo phép so Raft, log X được xem là mới hơn Y vì term cuối lớn hơn, dù index thấp hơn. Còn việc được bỏ phiếu vẫn phụ thuộc các điều kiện khác.

Không dùng thời điểm tường `updatedAt` từ các máy khác nhau làm tiêu chí thay thế log freshness.

## 16. Quy tắc từ chối term cũ

Follower có `currentTerm=15` nhận AppendEntries từ node tự xưng leader với `term=14`.

~~~text
request.term = 14
follower.currentTerm = 15
=> reject stale request theo protocol
~~~

Nếu một node nhận term cao hơn term local, nó cập nhật state và chuyển vai trò theo quy tắc. Một leader term thấp khi phát hiện term mới phải step down, không tiếp tục xử lý như leader hợp lệ.

**Term chỉ có tác dụng khi mọi đường ghi có liên quan thực hiện kiểm tra và transition theo giao thức.**

## 17. Leader Completeness: entry đã commit phải được giữ

Một tính chất quan trọng của Raft: những entry đã commit ở term trước phải có mặt trong log của leader được bầu ở các term sau theo quy tắc bảo toàn lịch sử.

Trực giác kết hợp:

- Majority commit.
- Majority election luôn có giao nhau trong membership cố định.
- Voter chỉ cấp phiếu cho log đủ mới.
- Log matching và commit rules đảm bảo lịch sử đã commit không bị thay thế trái protocol.

Không nhầm tính chất này với “mọi entry đã được gửi tới follower đều vĩnh viễn tồn tại”. **Entry chưa commit của leader cũ có thể được thay thế trong quá trình reconcile log**.

## 18. Received, replicated, committed, applied là bốn mốc

Một command có thể đi qua:

~~~text
Client sends write
    ↓
Leader receives command
    ↓
Leader appends local log
    ↓
Followers append log entry
    ↓
Commit rule satisfied
    ↓
State machine applies command
    ↓
Client receives outcome
~~~

| Mốc | Có nghĩa là gì? | Có phải success bền vững cuối cùng? |
|---|---|---|
| Received | Leader nhận request | Chưa |
| Appended local | Entry có trong log leader | Chưa |
| Replicated | Một hoặc nhiều follower nhận entry | Chưa đủ |
| Committed | Entry đạt quy tắc commit của protocol | Có bảo đảm phù hợp theo fault model |
| Applied | State machine đã áp command | Có thể client vẫn chưa nhận response |
| Response delivered | Client biết outcome | Có thể mất do mạng |

Quorum acknowledgment liên quan commit nhưng không thể tự triển khai bằng phép đếm đơn giản mà bỏ qua term và log consistency.

## 19. Chi tiết quan trọng của commit rule trong Raft

Trong Raft chuẩn, leader có thể trực tiếp nâng commit index tới vị trí N khi entry tại N **thuộc term hiện tại** và đã được lưu trên majority theo quy tắc tương ứng.

Entry từ term cũ có thể được commit **gián tiếp** khi một entry current-term ở vị trí sau được commit.

Ví dụ:

~~~text
Leader currentTerm=10
index 51: entryTerm=9
index 52: entryTerm=10
~~~

Khi index 52 được commit hợp lệ, những entry trước đó trong cùng log cũng được commit theo thứ tự.

Điểm này là lý do không thể viết một phiên bản “Raft” chỉ bằng công thức:

~~~text
if acknowledgments >= majority:
    committed = true
~~~

mà không xét term, log matching và protocol state.

## 20. AppendEntries và log matching

Thông điệp AppendEntries trong Raft thường có các thành phần logic:

~~~text
term
leaderId
prevLogIndex
prevLogTerm
entries[]
leaderCommit
~~~

Follower so sánh entry trước đó với log local. Nếu không khớp, follower từ chối để leader điều chỉnh điểm đồng bộ.

~~~text
Leader   : [A][B][C][D]
Follower : [A][B][X]
                   ^ khác nhau
~~~

Mục tiêu là để các node cùng có tiền tố log hợp lệ và không áp những lịch sử đã commit xung đột.

Không được dùng một replication job tùy ý để truncate log đã commit.

## 21. Partition 3–2 trong group năm voter

Membership `{A,B,C,D,E}`, majority=3.

~~~text
Partition X: {A,B}
Partition Y: {C,D,E}
~~~

Giả sử A là leader term 20 trước sự cố.

- X chỉ có hai voter; không đủ majority để commit write mới theo Raft.
- Y có thể bầu leader term 21 nếu điều kiện log/vote thỏa.
- A chưa biết term 21 nên có thể vẫn tự cho mình là leader term 20.
- Khi mạng hồi phục, A phải nhận diện term cao hơn và step down.
- Entry chưa commit ở phía A có thể được reconcile; entry đã commit phải được bảo toàn.

~~~mermaid
flowchart LR
    G["Group 5 voters"] --> X["A, B: minority"]
    G --> Y["C, D, E: majority"]
    X --> NO["Không đủ quyền commit"]
    Y --> YES["Có thể bầu và commit"]
~~~

**Node còn sống không đồng nghĩa node còn authority.** Khi mạng tách, một node có thể “healthy” theo health check nhưng không reachable tới quorum.

## 22. Split-brain được hiểu như thế nào?

Có hai hiện tượng khác nhau:

**Perceived split-brain:** hai node cùng tin mình là leader do thông tin trễ.

**Unsafe split-brain:** hai phía cùng commit những lịch sử mâu thuẫn trong cùng phạm vi authoritative state machine.

Một giao thức consensus an toàn nhằm ngăn tình huống thứ hai theo fault model. Nó không thể bảo đảm mọi node biết ngay leader mới dưới mạng bất đồng bộ.

Nếu một dịch vụ bên ngoài tin lời A “tôi đang là leader” mà không xác minh epoch, tình trạng perceived split-brain vẫn có thể gây **side effect trái quyền** ở hệ ngoài. Đây là lý do cần fencing hoặc idempotency bên ngoài log.

## 23. Fencing token chống stale owner

Giả sử hệ thống cấp token/generation tăng đơn điệu:

~~~text
A sở hữu resource R, epoch=41
A bị pause 40 giây
Lease A hết hạn
B nhận quyền mới, epoch=42
B ghi với epoch=42
A tỉnh lại, cố ghi với epoch=41
~~~

Nếu storage đích kiểm tra thế hệ cao nhất đã chấp nhận, nó có thể từ chối lệnh cũ của A.

Một mô hình khái niệm:

~~~text
write(resource, epoch, command):
    atomically at target:
        reject if epoch is older than accepted ownership
        validate business preconditions
        record updated epoch/ownership
        apply command
~~~

Nhưng việc chấp nhận `epoch >= maxEpoch` đơn giản vẫn chưa đủ cho mọi tình huống: command trùng trong cùng epoch, chuyển quyền chưa hoàn tất và authorization cần được xử lý riêng.

**Fencing hiệu quả khi đích của side effect thực sự kiểm tra token một cách có thẩm quyền và nguyên tử theo contract.**

## 24. Term của Raft có tự là fencing token cho hệ khác?

Term là mốc leader generation trong **một Raft group**. Khi truyền ra một resource bên ngoài, phải đảm bảo:

- Resource thuộc đúng group.
- Không nhầm term cùng số từ các group khác.
- Token không bị client giả mạo.
- Resource lưu/kiểm tra thế hệ quyền.
- Phép kiểm tra và ghi được phối hợp nguyên tử khi cần.
- Những lệnh cùng term được xử lý theo version/operation ID.
- Sau restore, term/generation không reset nguy hiểm.

Không phải mọi payment API hay object storage đều hỗ trợ fencing. Nếu hệ ngoài không hỗ trợ, cần thiết kế idempotency, command serialization, transactional outbox, compensation hoặc reconciliation phù hợp.

## 25. Lease không tự ngăn worker cũ chạy

Lease là quyền có thời hạn theo chính sách. Nó có thể giúp tối ưu read/ownership trong những hệ phù hợp, nhưng khi một worker bị pause lâu hơn lease, **mã worker cũ vẫn có thể tiếp tục sau khi được resume**.

~~~text
t0 A nhận lease 30 giây
t1 A bị stop-the-world GC 40 giây
t2 Lease hết, B nhận quyền
t3 A tỉnh lại và gửi request cũ
~~~

Redis `SET NX PX`, TTL hoặc key expiry không tự khiến side effect cũ bị hủy. Cần xem fencing, epoch check, business invariant và idempotency ở hệ đích.

## 26. Không thể bầu leader chỉ bằng heartbeat timeout

Một thuật toán ngây thơ:

~~~text
if noHeartbeatFor(500ms):
    self.isLeader = true
~~~

có thể khiến nhiều node cùng nhận leader role khi network delay hoặc GC pause.

Một election đúng phải có:

- Voter membership.
- Term/epoch.
- Vote record/persistence.
- Majority.
- Log freshness.
- Role transition.
- Commit rules.
- Reconfiguration protocol.

“Không nghe thấy node A” **không chứng minh A đã chết**. Nó chỉ nói node hiện tại chưa nhận thông điệp đúng hạn.

## 27. Pre-vote và các tối ưu bầu cử

Một số biến thể/implementation có **pre-vote**: node thăm dò khả năng nhận phiếu trước khi tăng term thật. Điều này có thể giảm term churn khi node cô lập quay lại.

Những tối ưu khác tùy engine:

- Random election timeout.
- Check-quorum.
- Controlled leadership transfer.
- Priority/electability rules.
- Election throttling/backoff.
- Witness/arbiter theo sản phẩm.

Không coi pre-vote là bước bắt buộc của mọi thuật toán Raft nguyên thủy, cũng không giả định election priority luôn thắng bất kể log freshness và quorum.

## 28. Đắc cử chưa hẳn sẵn sàng phục vụ mọi request

Một leader mới có thể cần:

- Xác định commit point hợp lệ.
- Đồng bộ/reconcile log.
- Append current-term entry theo protocol khi cần.
- Đợi state machine apply đủ committed state.
- Xác minh quorum/read barrier.
- Cập nhật routing metadata.
- Khởi tạo partition owner và resource phụ trợ.
- Sẵn sàng nhận client traffic.

Phân biệt các tín hiệu:

~~~text
processAlive = true
role = leader
hasQuorum = ?
commitIndex = ?
lastApplied = ?
canAcceptWrites = ?
canServeLinearizableReads = ?
~~~

Chỉ nhìn HTTP liveness hoặc biến `role` không đủ để quyết định một API nhạy cảm đã sẵn sàng.

## 29. Client viết vào follower sẽ được xử lý ra sao?

Tùy cơ sở dữ liệu:

- Follower trả `NOT_LEADER` và có thể kèm leader hint.
- Router tự chuyển request tới primary.
- Follower proxy đến leader.
- Follower chỉ cho read theo consistency của nó.
- Trong leaderless protocol, coordinator có thể nhận write mà không là leader dữ liệu.

Client nên xử lý discovery/redirect theo driver chính thức, bounded retry với backoff, timeout và operation ID. Không cache leader hint vô thời hạn hoặc gửi retry vô điều kiện sau mỗi lỗi mạng.

## 30. Client timeout khi leader đã commit

~~~text
t0 Client gửi CreateOrder(K) cho leader A
t1 A commit command hợp lệ
t2 Response thành công bị mất
t3 A crash, B được bầu
t4 Client timeout rồi retry CreateOrder(K)
~~~

Client không biết outcome t1, dù B có thể kế thừa committed log.

Nếu retry không có idempotency, ứng dụng có thể tạo hai Order từ cùng một ý định.

Thiết kế cần:

- Idempotency/operation key ổn định.
- Lưu mapping key → kết quả trong state có bảo đảm thích hợp.
- Kiểm tra payload trùng key có giống không.
- Trả lại outcome đã commit khi retry.
- Reconcile khi outcome chưa biết.
- Không kết luận “timeout nghĩa là chưa ghi”.

**Consensus đảm bảo quyết định trong log; idempotency bảo vệ ý định nghiệp vụ khỏi việc gửi lặp.**

## 31. Write concern yếu và rủi ro rollback

Trong một số hệ primary-secondary, write có thể được acknowledgment trước khi đủ replica cần thiết cho một mức bền vững mạnh.

Ví dụ trực giác:

~~~text
A là primary
A nhận W11 và ACK theo policy local
B, C chưa nhận W11
A crash
B/C bầu primary mới
W11 có thể không thuộc lịch sử mới
~~~

Không phải mọi ACK đều có cùng guarantee khi failover.

Cần tách:

- Write đã nhận.
- Write đã ghi local journal/WAL.
- Write đã replicate.
- Write đã majority-committed theo engine.
- Write đã visible với read concern cụ thể.
- Response đã tới client.

Trong những engine có rollback của write chưa majority-committed, client có thể đã nhận ACK theo policy yếu nhưng dữ liệu biến mất sau primary election. Hãy cấu hình acknowledgment/durability theo yêu cầu nghiệp vụ thay vì mặc định mọi success đều sống sót qua mọi lỗi.

## 32. MongoDB replica set: primary và election

MongoDB replica set có **primary** và những **secondary**. Primary thường nhận các write của replica set; secondary áp dụng replication log theo cơ chế engine và có thể phục vụ read tùy read preference.

Khi primary lỗi, các thành viên đủ điều kiện bầu primary mới theo replica-set election protocol.

Những khái niệm cần hiểu:

- Voting members.
- Electable members.
- Priority.
- Oplog freshness.
- Majority election.
- Election term/metadata.
- Member state transitions.
- Majority write concern.
- Read concern và read preference.
- Retryable writes/session behavior.

Không tự tuyên bố MongoDB triển khai thuật toán Raft nguyên bản. Các khái niệm tương tự majority/term/log hữu ích để hiểu, nhưng chi tiết protocol MongoDB phải xem theo version/topology cụ thể.

## 33. Voting member khác data-bearing member

Ví dụ cấu hình:

~~~text
A: data-bearing voter
B: data-bearing voter
C: arbiter voter
~~~

Một arbiter có thể tham gia vote nhưng **không giữ bản dữ liệu như secondary**.

Điều đó có nghĩa:

- Majority voter count không tự bằng số data copies.
- Election availability và write durability phải phân tích riêng.
- Placement theo availability zone của các data-bearing member rất quan trọng.
- Không coi arbiter như backup hoặc replica phục vụ read.
- Write concern majority/journaling semantics cần kiểm chứng bằng tài liệu engine.

Nếu chỉ đọc dashboard thấy “ba member” rồi tuyên bố “ba bản sao dữ liệu”, kết luận có thể sai.

## 34. MongoDB: cách quan sát trạng thái

Trong môi trường MongoDB có quyền phù hợp, các thao tác đọc thông tin như:

~~~javascript
rs.status();
rs.conf();
db.hello();
~~~

có thể hỗ trợ xem primary/member states, cấu hình, term/election metadata và replica health theo phiên bản.

Lưu ý:

- Output field có thể thay đổi giữa version.
- Kết quả phản ánh node và thời điểm được hỏi.
- Một node tự tin mình là primary chưa chắc còn majority reachable.
- Secondary có thể còn lag sau khi primary mới được bầu.
- Không dùng `rs.stepDown()` hoặc `rs.reconfig()` tùy tiện trên production để thử election.

Nên ghi event timeline bằng timestamp, node ID, election term, state changes, quorum availability và write/read errors.

## 35. MongoDB: majority read không phải latest linearizable read

Các khái niệm:

- **Write concern majority:** write được xác nhận theo semantics majority của replica set.
- **Read preference:** chọn primary hay secondary theo policy.
- **Read concern majority:** liên quan majority-committed state có thể quan sát.
- **Read concern linearizable:** có phạm vi/điều kiện mạnh hơn cho operation được hỗ trợ.
- **Causal session:** giúp bảo toàn những phụ thuộc như read-your-writes nếu dùng read/write concern/session phù hợp.

Một secondary có thể trả bản cũ ngay sau write majority ở primary, tùy lag và read contract. Một primary đã step down có thể trả stale nếu ứng dụng đọc sai đường trong một tình huống lỗi.

Để API hứa mạnh hơn, cần hiểu driver topology discovery, session context và các điều kiện của read concern cụ thể. Không chỉ “đọc từ node báo primary” rồi gọi đó là linearizable read.

## 36. Đối chiếu Raft và MongoDB có giới hạn

| Khía cạnh | Raft (mô hình) | MongoDB replica set |
|---|---|---|
| Node ghi chính | Leader | Primary |
| Election generation | Term | Term/election metadata theo engine |
| Quorum | Majority voter | Replica-set election theo cấu hình |
| Log | Ordered replicated log | Oplog/replication protocol |
| Commit | Raft commit rule | Write concern/majority commit semantics |
| Follower/secondary read | Phụ thuộc read protocol | Read preference/read concern |
| Member roles | Raft voter/nonvoter theo variant | Data-bearing, voter, arbiter |
| Reconfiguration | Theo protocol đồng thuận | Replica-set config change |
| Failover | Leader election | Primary election/driver rediscovery |

Bảng là **so sánh khái niệm**, không phải ánh xạ một-một về API, thuật toán hoặc guarantees.

## 37. Cassandra không có primary toàn cluster cho write thường

Apache Cassandra thường được mô tả là leaderless đối với các read/write thông thường. Một coordinator nhận request và trao đổi với replica theo consistency level; coordinator không trở thành leader duy nhất cho mọi dữ liệu chỉ vì nó nhận request.

Ví dụ:

~~~text
Client -> Coordinator -> Replica A/B/C
Read/Write CL quyết định số xác nhận hợp lệ
~~~

Cassandra còn hỗ trợ Lightweight Transactions dùng Paxos-style coordination cho một số conditional operations như `IF NOT EXISTS`, nhưng điều đó không biến toàn bộ Cassandra thành cluster có một leader cố định.

Phân biệt:

- Coordinator per request.
- Replica owner/token placement.
- Paxos ballot/proposal trong conditional writes.
- Membership và token ring.

**Không lấy Raft election làm mẫu bắt buộc cho mọi NoSQL**.

## 38. Paxos ballot khác Raft term nhưng có trực giác tương tự

Trong các biến thể Paxos, proposal/ballot number giúp acceptor phân biệt các vòng đề xuất. Acceptors ghi nhớ promise và accepted value theo protocol; proposer mới phải tôn trọng giá trị có khả năng đã được chọn.

Trực giác:

~~~text
Proposer đề nghị ballot cao hơn
Acceptors promise theo protocol
Proposer xem các accepted values trước
Quorum acceptors tham gia chọn một value hợp lệ
~~~

Những điều không được nhầm:

- Ballot không phải đồng hồ thời gian thực.
- Proposer không tự là leader cố định.
- Multi-Paxos có thể dùng stable leader để tối ưu.
- Không tự bỏ bước xác minh accepted value.
- Quorum overlap là một phần chứng minh, không phải toàn bộ protocol.

Cơ chế này cho thấy **đồng thuận có thể dùng thế hệ logic mà không nhất thiết có cùng state machine election của Raft**.

## 39. DynamoDB là managed service, không cho đoán leader nội bộ

DynamoDB công bố các write/read APIs, conditional writes, transactions và consistency modes theo phạm vi được hỗ trợ.

Người dùng không có quyền chọn một `currentTerm`/`leaderId` nội bộ cho physical partition giống khi tự vận hành Raft cluster.

Không nên đoán:

- N bao nhiêu, W bao nhiêu ở nội bộ DynamoDB.
- Election timeout của storage partition.
- Term/epoch có format ra sao.
- Strong read trong một region tự mạnh trên mọi Global Tables region.
- GSI có cùng consistency với base table.

Hãy chọn giải pháp dựa trên **guarantees dịch vụ công bố**, không trên mô hình tưởng tượng của replication bên trong.

## 40. Leader của metadata khác leader của shard dữ liệu

Một số hệ NoSQL/search phân tán có cluster manager/master quản lý metadata và đồng thời mỗi shard có primary/replica riêng.

Khi cluster manager lỗi, metadata coordination có thể ảnh hưởng cluster; khi một shard primary lỗi, chỉ một số write path có thể bị gián đoạn. Hai loại leadership này khác phạm vi.

Vì vậy:

- Một node “master” không tự nhận mọi data write.
- Một shard có thể có primary mới mà cluster manager không đổi.
- Election/quorum của metadata và replication của data có thể khác nhau.
- Routing table cần được cập nhật sau failover.
- Search read có thể có stale/refresh semantics riêng.

Ghi đúng loại leader trong incident report để tránh chẩn đoán sai.

## 41. External side effects không thuộc Raft log tự động

Một Inventory leader nhận lệnh đặt hàng rồi gọi payment gateway. Khi leader đổi, side effect ở hệ ngoài có thể bị lặp hoặc đến trễ:

~~~text
A epoch 50 chuẩn bị charge
A bị pause
B epoch 51 nhận quyền và charge
A tỉnh lại, cũng charge
~~~

Nếu gateway không hiểu fencing epoch, chỉ có election ở Inventory không đủ.

Thiết kế có thể cần:

- Stable payment operation ID.
- Idempotency key được gateway hỗ trợ.
- Durable state transition trước side effect.
- Transactional outbox cho message.
- Reconciliation và trạng thái pending/unknown.
- Saga/compensation theo domain.
- Fencing ở đích nếu được hỗ trợ và cần thiết.

**Một command được log đúng một lần không tự làm external API được gọi đúng một lần**.

## 42. Partition owner epoch

Khi một partition chuyển owner do rebalancing:

~~~text
Partition P
  epoch 15 -> owner A
  epoch 16 -> owner B
~~~

Các yêu cầu quan trọng:

1. Epoch mới được cấp bởi nguồn có thẩm quyền.
2. Owner mới có state/checkpoint phù hợp trước khi nhận write.
3. Request của epoch cũ không thể áp side effect trái phép.
4. In-flight commands có trạng thái và retry rõ ràng.
5. Mỗi epoch gắn đúng partition ID.
6. Recovery từ backup không tái sử dụng epoch cũ nguy hiểm.
7. Source đích kiểm tra owner/generation khi commit.

Nếu không, một leader cũ có thể tiếp tục gửi lệnh hợp lệ về cú pháp nhưng đã mất quyền.

## 43. Snapshot và log compaction

Khi replicated log dài, hệ có thể tạo snapshot và compact những entry trước checkpoint:

~~~text
snapshot.lastIncludedIndex = 100
snapshot.lastIncludedTerm = 7
remainingLog begins after index 100
~~~

Follower mới hoặc rất chậm có thể cần nhận snapshot thay vì replay tất cả entry từ đầu.

Những nguyên tắc:

- Snapshot đi kèm index/term metadata phù hợp.
- Log đã committed không được thay thế trái safety.
- State persist/vote/term cần được khôi phục theo protocol.
- Membership metadata có thể nằm trong snapshot/log theo implementation.
- Compaction không tự đồng nghĩa reset term.

Không dùng một snapshot cũ để ghi đè state authoritative mới khi cluster đang hoạt động.

## 44. Reconfiguration membership

Membership cũ:

~~~text
{A,B,C}
~~~

Membership mới:

~~~text
{B,C,D}
~~~

Chứng minh majority overlap trong **một tập cố định** không tự bảo đảm giao nhau trong giai đoạn có nhiều cấu hình.

Các protocol an toàn có cách chuyển cấu hình được thiết kế, ví dụ joint consensus trong mô tả Raft cổ điển hoặc phương pháp khác được chứng minh.

Cần xem:

- Entry/config mới được commit lúc nào.
- Ai có quyền vote ở từng giai đoạn.
- Node mới đã nhận đủ log chưa.
- Leader cũ có phải step down không.
- Còn majority trong từng giai đoạn không.
- Bootstrap và replica placement đã hoàn tất chưa.

**Reconfiguration là thay đổi authority**, không đơn thuần chỉnh một danh sách IP.

## 45. Election storm và leadership flapping

Khi network jitter, GC pauses hoặc disk stalls kéo dài, cluster có thể liên tục timeout/bầu lại:

~~~text
term 100 -> candidate A
term 101 -> candidate B
term 102 -> leader C
term 103 -> election lại
...
~~~

Triệu chứng:

- Term/epoch tăng nhanh.
- Leader thay đổi thường xuyên.
- Write timeout/NotLeader nhiều.
- Replication lag và commit/apply lag tăng.
- Client retry gây thêm tải.
- P95/P99 latency xấu đi.
- CPU/network dùng nhiều cho election.

Nguyên nhân có thể là timeout quá thấp, follower overload, clock/timer issues, network packet loss hoặc không đủ quorum.

Không “chữa” bằng cách tắt quorum validation. Hãy xem nguyên nhân, topology và cấu hình được engine hỗ trợ.

## 46. Leader bottleneck và multi-leader theo shard

Một leader phải xử lý nhiều write nên có thể là bottleneck về:

- Log append/fsync.
- Replication network.
- Ordering và serialization.
- Transaction coordination.
- Apply throughput.
- Client ingress.
- Memory/queue pressure.

Có thể dùng nhiều consensus groups/shards với leader khác nhau để phân tán tải:

~~~text
Shard 1 leader on Node A
Shard 2 leader on Node B
Shard 3 leader on Node C
~~~

Thêm follower vào một group không tự tăng write throughput của leader; còn có thể tăng replication cost. Cần benchmark theo workload và topology.

## 47. Linearizable read từ leader không đơn giản là đọc RAM

Một node tự cho mình là leader có thể đã mất quorum nhưng chưa biết term mới.

Nếu nó đọc từ local state và trả GET thành công như linearizable, client có thể nhận bản cũ so với một write đã commit ở phía majority mới.

Để trả linearizable read, protocol cần phương pháp xác minh authority và read barrier: chẳng hạn xác minh liên lạc quorum/read-index, hoặc leader lease được chứng minh an toàn trong fault model cùng cơ chế áp dụng commit index.

Không suy:

~~~text
isLeader == true
=> read is always latest
~~~

Một số read có thể cố ý cho phép stale, một số phải mạnh. Contract của API phải xác định rõ mức đọc và hành vi khi không thể đáp ứng.

## 48. ReadIndex và commit/apply barrier

Một phương pháp kiểu Raft cho linearizable read có thể:

1. Đảm bảo leader có trạng thái phù hợp trong current term.
2. Xác minh authority theo quorum protocol.
3. Xác định read index/barrier hợp lệ.
4. Đợi state machine apply tới mốc đó.
5. Đọc state local.

Một số hệ có thể tối ưu bằng leader lease khi đồng hồ/timer assumptions đủ mạnh. Không tự áp dụng quy tắc “heartbeat chưa quá 500 ms là chắc chắn latest” như công thức chung.

## 49. Quan sát election trong production

Các metric quan trọng:

| Nhóm | Metric |
|---|---|
| Leadership | Current term/epoch, leader ID, leader change count |
| Election | Election attempts, election duration, failed elections |
| Heartbeat | Heartbeat latency, timeout, follower reachability |
| Log | Last log index/term, commit index, last applied |
| Replication | Follower lag, snapshot install, replication backlog |
| Quorum | Majority availability, no-quorum intervals |
| Write | Commit latency, unknown outcomes, retry count |
| Read | Linearizable-read failures, stale/session-read violations |
| External | Fencing rejects, duplicate side-effect attempts |
| Client | NotLeader, primary-stepdown, timeout, p99 |
| Operations | Membership changes, priority changes, storage stalls |

Term tăng đột biến chỉ là tín hiệu. Cần ghép với log, quorum, network và API errors để kết luận nguyên nhân.

## 50. Fault injection có kiểm soát

| Kịch bản | Điều cần xác minh |
|---|---|
| Kill leader khi còn majority | Bầu được leader mới, commit tiếp tục |
| Kill trước khi entry commit | Entry chưa commit được xử lý đúng |
| Mất response sau commit | Client retry không tạo duplicate effect |
| Partition 2–1 của group 3 voter | Nhóm hai có thể bầu/commit, nhóm một không |
| Partition 3–2 của group 5 voter | Nhóm ba có thể tiến triển nếu log đủ mới |
| Leader cũ nối lại mạng | Step down và log reconcile hợp lệ |
| Candidate có log quá cũ | Voter từ chối khi cần |
| Hai candidate timeout cùng lúc | Split vote và retry không phá safety |
| Follower thấy term cao hơn | Node chuyển role đúng |
| GC pause dài | Không có hai lịch sử commit xung đột |
| Disk stall ở voter | Tail latency và election behavior |
| Membership reconfiguration | Quorum overlap được giữ |
| Restore snapshot | Term, vote, log state không bị reset sai |
| Read ở leader cũ | Strong read không trả stale thành công |
| Worker cũ gửi side effect | Fencing/idempotency bảo vệ đích |

Không chạy các lệnh cưỡng bức election/chaos trên production nếu không có quy trình cho phép, đánh giá ảnh hưởng và rollback.

## 51. Timeline mẫu N=5

Group `{A,B,C,D,E}`, majority=3:

~~~text
t0 Term 17, A leader, commitIndex=100
t1 A append index=101, term=17
t2 A replicate tới B,C, theo rule có thể commit 101
t3 A mất kết nối với C,D,E
t4 C,D,E có thể bầu D term=18 nếu log đủ mới
t5 A vẫn tin mình là leader 17 nhưng chỉ liên lạc B
t6 A không đủ majority 3 để commit entry mới
t7 Mạng hồi phục, A phát hiện term=18 và step down
t8 Log reconcile; entry đã commit ở 101 được bảo toàn
~~~

Các câu hỏi:

- D có log đủ mới để đắc cử không?
- D có entry đã commit 101 theo Leader Completeness không?
- A trả gì cho write ở t5?
- Client timeout ở t2 tra outcome ra sao?
- API có chặn strong read từ A sau t4 không?

Ví dụ phục vụ lập luận về protocol; không phải dự báo mốc thời gian cụ thể của MongoDB.

## 52. Bài tập A — Majority

Có 7 voter. Cần bao nhiêu phiếu để leader được bầu? Có thể thiếu mấy voter theo phép đếm?

**Hướng giải:** `floor(7/2)+1=4`. Có thể thiếu ba voter nếu bốn voter còn lại reachable và đủ điều kiện.

## 53. Bài tập B — Hai candidate cùng term

Group N=5; candidate A và B cùng term 10. Mỗi voter chỉ bỏ một phiếu trong một term.

**Hỏi:** cả hai có thể cùng giành ba phiếu hợp lệ không?

**Hướng giải:** không. Hai majority ba trong năm luôn giao nhau; voter chung không thể cấp hai phiếu trái nhau cùng term.

## 54. Bài tập C — Candidate log freshness

Candidate X: lastLogTerm=8, lastLogIndex=30; voter Y: lastLogTerm=7, lastLogIndex=45.

**Hỏi:** log X mới hơn theo so sánh Raft không?

**Hướng giải:** có, vì term cuối 8 lớn hơn 7. Còn cấp phiếu cần xét các điều kiện khác.

## 55. Bài tập D — Stale AppendEntries

Follower term 15 nhận AppendEntries term 14.

**Hỏi:** thao tác đó có được chấp nhận không?

**Hướng giải:** từ chối request stale term theo Raft, không append vô điều kiện.

## 56. Bài tập E — Minority partition

N=3; A leader term 7; B,C bầu B term 8 khi A bị cô lập.

**Hỏi:** A có thể commit ghi mới bằng một mình nó không?

**Hướng giải:** không, nếu không đạt quorum hai trên ba theo Raft.

## 57. Bài tập F — Entry chưa commit

A append entry X nhưng chưa đạt quorum; B được bầu term sau.

**Hỏi:** X phải được bảo toàn trong mọi log sau đó không?

**Hướng giải:** không. Entry chưa commit có thể bị thay thế. Entry đã commit phải được bảo toàn theo protocol safety.

## 58. Bài tập G — Lease và GC pause

A giữ lease 30 giây, bị pause 40 giây. B đã nhận ownership epoch cao hơn. A tỉnh dậy gọi external API.

**Hỏi:** TTL có tự chặn lời gọi cũ không?

**Hướng giải:** không. Cần fencing/permission check tại đích hoặc thiết kế idempotency/coordination thích hợp.

## 59. Bài tập H — Retry sau commit

CreateOrder đã commit nhưng response mất. Client retry không có idempotency key.

**Hỏi:** có an toàn không?

**Hướng giải:** không. Client cần stable operation ID để truy kết quả và không thực thi lại ý định như mới.

## 60. Bài tập I — MongoDB arbiter

Replica set có hai data-bearing members và một arbiter đều bỏ phiếu.

**Hỏi:** có ba bản dữ liệu như nhau không?

**Hướng giải:** không. Arbiter không giữ bản sao dữ liệu như một secondary, vì vậy election voters và data durability phải xét riêng.

## 61. Bài tập J — Cassandra coordinator

Một người nói Cassandra có coordinator nên nó là leader toàn cluster.

**Hỏi:** nhận định đúng không?

**Hướng giải:** không. Coordinator phục vụ request theo consistency level, không phải leader cố định toàn bộ data. LWT dùng Paxos-style coordination riêng.

## 62. Bài tập K — Leader local read

A bị partition, vẫn giữ `isLeader=true` trong RAM và trả local read.

**Hỏi:** có thể gọi read đó linearizable không?

**Hướng giải:** không tự động. Cần protocol xác minh authority/read barrier phù hợp.

## 63. Bài tập L — Reset epoch sau restore

Hệ ngoài đã nhận epoch 100. Service restore backup cũ rồi cấp epoch 3.

**Hỏi:** điều gì có thể sai?

**Hướng giải:** epoch mới không còn cao hơn generation đã biết; fencing có thể từ chối các thao tác hợp lệ hoặc bị phá nếu so sánh/reset sai. Cần giữ monotonic generation qua recovery.

## 64. Bài tập M — Reconfiguration

Membership cũ `{A,B,C}`, mới `{B,C,D}`.

**Hỏi:** vì sao không chỉ đổi file cấu hình của từng node thủ công?

**Hướng giải:** overlap giữa các quorum cần được bảo vệ trong giai đoạn nhiều cấu hình cùng tồn tại; dùng reconfiguration protocol an toàn.

## 65. Bài tập N — Election không chống overselling tự động

Leader đã hợp lệ, hai client đều đọc tồn kho còn một sản phẩm và sau đó ghi giảm vô điều kiện.

**Hỏi:** election có tự ngăn bán hai lần không?

**Hướng giải:** không. Cần điều kiện domain ở command/atomic update hoặc transaction tại nguồn cùng idempotency cho retry.

## 66. Checklist thiết kế leader election và quyền ghi

1. **Scope:** leader của cluster, shard, partition hay group nào?
2. **Voters:** ai được bầu và ai lưu dữ liệu?
3. **Quorum:** majority tính theo membership nào?
4. **Term/epoch:** được cấp/persist/tăng đơn điệu ra sao?
5. **Votes:** có một phiếu mỗi term và log freshness không?
6. **Messages:** stale term bị từ chối ở đâu?
7. **Log:** entry, index, term và matching rules rõ chưa?
8. **Commit:** write được coi committed lúc nào?
9. **Apply:** commit index và last applied có ý nghĩa gì?
10. **Failover:** khi mất leader, client route/retry ra sao?
11. **Old leader:** có thể gửi side effect sau khi mất quyền không?
12. **Fencing:** đích có kiểm tra generation atomically không?
13. **Lease:** những giả định timer/clock nào được sử dụng?
14. **Reads:** follower, snapshot và linearizable path có contract gì?
15. **Unknown outcome:** idempotency và reconciliation đã có chưa?
16. **Membership changes:** có quy trình an toàn không?
17. **Snapshot/restore:** term/vote/log/generation được bảo toàn không?
18. **Multi-region:** authority và quorum ở đâu?
19. **Security:** các thông điệp bầu cử được xác thực không?
20. **Observability:** term, leader changes, quorum, lag và retry có đo?
21. **Testing:** partition, crash, pause, timeout sau commit đã thử?
22. **Operations:** có runbook xử lý election storm mà không tắt safety?

Một hợp đồng kiến trúc minh họa:

~~~yaml
system: InventoryNoSQL
leadership:
  scope: perPartitionConsensusGroup
  voters: 5
  electionRule: majority
  epochSource: persistedConsensusState
  staleMessagePolicy: rejectLowerTerm
  membershipChanges: consensusManaged
writes:
  authoritativePath: currentLeader
  commitRule: verifiedByProtocol
  conditionalInvariant: required
  idempotencyKey: required
reads:
  strongPath: protocolVerifiedLeaderRead
  followerPath: explicitlyWeakerContract
failure:
  unavailableWithoutQuorum: true
  boundedRetry: true
  reconcileUnknownOutcome: required
externalEffects:
  outbox: whenApplicable
  fencingAtTarget: whenSupportedAndRequired
monitoring:
  - currentTerm
  - leaderChangeRate
  - electionAttempts
  - quorumUnavailable
  - commitApplyLag
  - staleOwnerRejects
  - unknownWriteOutcomes
validation:
  - minorityCannotCommit
  - oldLeaderStepsDown
  - committedHistoryPreserved
  - retryDoesNotDuplicateEffects
~~~

YAML chỉ là **mẫu tài liệu thiết kế**, không phải cấu hình mà MongoDB, Cassandra hay một Raft implementation tự áp dụng. Những bảo đảm phải được hiện thực qua API, protocol và deployment thật.

## 67. Kết luận

Trong một hệ NoSQL leader-based, **leader** điều phối việc ghi cho đúng phạm vi dữ liệu; **term/epoch** đánh dấu thế hệ authority; **election** dùng voter/quorum và quy tắc log freshness để chọn người điều phối tiếp theo.

An toàn đến từ **tổng thể giao thức**, không riêng majority hoặc một cờ leader:

- Term/vote state được persist.
- Stale messages bị từ chối.
- Log matching và commit rule giữ lịch sử.
- Leader cũ không thể commit trái quorum.
- Read có kiểm tra authority khi cần strong consistency.
- External side effects được fence hoặc idempotent.
- Membership change và recovery không làm reset thế hệ nguy hiểm.
- Client xử lý timeout và unknown outcome đúng.

> **Một leader cũ có thể chưa biết mình đã mất quyền. Term/epoch giúp đánh dấu thế hệ mới; quorum và log protocol giữ lịch sử commit an toàn; fencing và idempotency bảo vệ những hành động vượt ra ngoài consensus group.**

Hiểu đúng các khái niệm đó giúp giải thích vì sao cluster tạm từ chối ghi khi mất quorum, vì sao không thể đo safety bằng thời gian bầu chọn đơn thuần, và vì sao kiểm thử failover cần chứng minh **tính đúng đắn của dữ liệu và nghiệp vụ**, không chỉ thấy một leader mới xuất hiện.
