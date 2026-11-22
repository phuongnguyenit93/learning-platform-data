# Quorum đồng thuận và điều kiện tiến trình có thể tiếp tục

Một cụm NoSQL gồm năm node bỏ phiếu đang phục vụ đơn hàng. Sau một sự cố mạng, ba node ở vùng A còn liên lạc với nhau, còn hai node ở vùng B chỉ liên lạc với nhau. Cả hai nhóm đều còn sống và đều nhận được request từ người dùng. **Nhóm nào có quyền xác nhận một ghi mới?** Nếu leader cũ nằm trong nhóm hai node, nó có thể tiếp tục tự nhận là leader không? Khi mạng hồi phục, làm thế nào chắc rằng hai nhóm chưa cùng xác nhận hai giá trị mâu thuẫn?

Bản chất của những câu hỏi này là **quorum trong giao thức đồng thuận (consensus quorum)** và điều kiện để hệ thống có thể **tiến triển (make progress)** mà không phá vỡ những quyết định đã đạt được. Đây không chỉ là bài toán chia N cho hai rồi cộng một: phải biết **ai là thành viên bỏ phiếu, quorum nào cần giao nhau, leader có quyền gì, entry nào đã thực sự committed, phần mạng nào còn liên lạc, và điều kiện nào khiến tiến trình phải dừng**.

Trong chương **Đồng thuận và quyền ghi** của **Database No SQL**, bài học đi từ majority quorum tới các cơ chế thường gặp trong Raft/Paxos, phân biệt consensus quorum với quorum đọc/ghi kiểu replica, giải thích **safety so với liveness**, mô hình lỗi phân vùng, leader election, log commit, fencing và thay đổi membership. Bài cũng làm rõ cách chọn topology đa vùng, dự đoán ảnh hưởng đến khả năng phục vụ, xử lý commit chưa xác định ở Java, đo p99 và kiểm thử lỗi mạng.

> **Ý chính:** Một quorum không đơn thuần là “số node có phản hồi”. Trong giao thức đồng thuận, nó là một **tập thành viên đủ điều kiện** mà các giao đoạn bầu chọn hoặc cam kết sử dụng theo những quy tắc bảo đảm **các quyết định xung đột không thể cùng được xác nhận**. Hệ chỉ có thể tiếp tục tiến triển khi có đủ **quorum hợp lệ, liên lạc, điều kiện thời gian/ổn định và năng lực xử lý** của đúng giao đoạn đang diễn ra.

> **Phạm vi:** Các ví dụ dùng Raft và Paxos ở mức khái niệm. Không phải mọi NoSQL dùng cùng một giao thức, cùng loại voter hay cùng semantic ACK. Ví dụ MongoDB, Cassandra, DynamoDB, Redis và HBase ở phần sau chỉ giúp tránh đánh đồng các cơ chế; cần đối chiếu tài liệu theo sản phẩm/phiên bản/cấu hình triển khai thực tế.

## 1. Đồng thuận là thống nhất về điều gì?

**Consensus (đồng thuận)** giải quyết việc những thành viên trong một hệ phân tán thống nhất một hoặc nhiều **quyết định** dù có chậm mạng, node hỏng hoặc message bị giao không đúng thời điểm.

Một số ứng dụng:
- Chọn leader/term hợp lệ.
- Thống nhất thứ tự các entry trong replicated log.
- Quyết định cấu hình thành viên nào có hiệu lực.
- Xác nhận một đề xuất đã được chấp nhận/committed.
- Làm nền cho một state machine được sao chép.

Ví dụ một replicated log:

~~~~text
Index       101              102                 103
        +-----------+  +----------------+  +-----------------+
Entry   | Create A  |  | Reserve B: -1  |  | Mark B confirmed|
        +-----------+  +----------------+  +-----------------+
Term         7                 7                    7
~~~~

Các node không chỉ cần đồng ý rằng “có một entry tại index 102”, mà phải giữ một lịch sử **không cho phép hai giá trị xung đột cùng được xem là committed ở cùng vị trí**, theo những bảo đảm của protocol.

### 1.1. Safety và liveness

Hai lớp yêu cầu khác nhau:

| Thuộc tính | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Safety** | Điều xấu có thể xảy ra không? | Hai leader có thể cùng commit hai entry xung đột tại index 102 không? |
| **Liveness/progress** | Hệ có thể tiếp tục hoàn thành quyết định không? | Một request mới có thể được committed khi còn ba trong năm voter? |

**Safety** phải được giữ trong cả lúc hệ không thể tiến triển: khi thiếu quorum, hành vi đúng có thể là **chờ hoặc từ chối ghi**, không phải tự cấp quyền commit để làm đẹp availability.

**Liveness** cần những giả định khác, ví dụ nhóm quorum có thể giao tiếp ổn định đủ lâu, có leader hợp lệ, lịch xử lý công bằng và storage hoạt động trong những giới hạn mà protocol dựa vào.

### 1.2. Đồng thuận không đồng nghĩa mọi dữ liệu giống nhau ngay

Một log entry được majority committed không có nghĩa:
- Mọi replica đã nhận entry.
- Mọi replica đã apply vào state machine.
- Mọi index/secondary index/search projection đã query-visible.
- Mọi client ở mọi vùng đều biết commit result.
- Email, payment provider và những service bên ngoài đã cùng commit.

**Đồng thuận quyết định một lịch sử hoặc trạng thái theo ranh giới protocol**, còn hiển thị dữ liệu, durability, transaction và external side effects cần hợp đồng riêng.

## 2. Majority quorum: công thức đầu tiên

Với một cấu hình có **N voting members** và mỗi member có một phiếu, đa số nghiêm ngặt là:

\[
Q=\left\lfloor\frac{N}{2}\right\rfloor+1
\]

Một majority có **số phiếu lớn hơn N/2**.

| Số voter N | Majority Q | Số voter có thể mất mà vẫn còn majority, trong điều kiện còn lại liên lạc |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 6 | 4 | 2 |
| 7 | 4 | 3 |
| 9 | 5 | 4 |

Trong mô hình majority ổn định và các node còn lại cùng liên lạc được, số lỗi thành viên tối đa cho phép tiếp tục đạt quorum là:

\[
f=\left\lfloor\frac{N-1}{2}\right\rfloor
\]

Đây **không phải xác suất uptime** hoặc bảo đảm request sẽ luôn thành công: còn phải xét cách đặt node, routing, leader election, disk, network, overload và giao thức commit.

### 2.1. Vì sao phải là đa số nghiêm ngặt?

Với N=5:
- Quorum thứ nhất có ít nhất 3 voter.
- Quorum thứ hai có ít nhất 3 voter.
- Hai tập con kích thước 3 của một tập 5 **không thể rời nhau**.

Bất đẳng thức:

\[
|Q_1|+|Q_2|>N
\]

bảo đảm giao nhau ít nhất một thành viên khi hai quorum được chọn trong **cùng một tập thành viên ổn định**.

Với hai majority size 3 trong N=5:

\[
|Q_1\cap Q_2|\ge3+3-5=1
\]

Một thành viên nằm ở phần giao cung cấp điểm liên kết thông tin, **khi protocol yêu cầu node bảo quản và dùng thông tin ấy đúng cách**. Chỉ giao tập hợp thôi chưa chứng minh toàn bộ hệ an toàn.

### 2.2. Đếm phản hồi khác đếm phiếu hợp lệ

Một cụm có:
- 5 voter.
- 2 read replicas không bỏ phiếu.
- 1 analytics consumer.
- 1 witness chỉ tham gia một số quyết định.

Nói “có 6 node trả ACK” chưa đủ nếu trong số đó chỉ có **2 voter hợp lệ** cho operation cần majority ba phiếu.

Cần hỏi:
- Tập **voting configuration** hiện hành gồm ai?
- Những response nào thuộc **giao đoạn** bầu cử hay ghi log?
- Thành viên nào còn ở term/epoch hiện tại?
- Có thành viên chỉ phục vụ read, learner hay witness không?
- ACK là **received, appended, durable, accepted hay committed**?

## 3. Tại sao quorum phải giao nhau?

Giả sử một hệ có 5 voter: A, B, C, D, E.

~~~~text
Quorum X = {A, B, C}
Quorum Y = {C, D, E}

Giao nhau: {C}
~~~~

Nếu proposal/leader mới cần thu thập thông tin từ quorum Y, C có thể đem theo thông tin về một quyết định trước đó từ X **theo đúng luật giao thức**.

Một cách suy nghĩ:

~~~~text
Decision 1 được xác nhận bởi một quorum.
Decision 2 có thể xung đột với Decision 1.

Muốn ngăn xung đột, protocol phải buộc các vòng quyết định
mới gặp được hoặc kế thừa thông tin bắt buộc từ quyết định cũ.
~~~~

**Quorum intersection là điều kiện cấu trúc quan trọng cho safety**, nhưng một algorithm đúng còn cần:
- Ballot/term/epoch để phân biệt các vòng.
- Quy tắc chấp nhận/loại proposal.
- Quy tắc bảo toàn giá trị đã được chọn.
- Bền vững của trạng thái hứa hẹn/chấp nhận theo fault model.
- Xử lý leader cũ và thông điệp trễ.
- Quản lý membership an toàn.

### 3.1. Nếu hai nhóm không có giao nhau?

Giả sử N=4 nhưng cho phép quorum hai node:

~~~~text
Group 1 = {A, B}
Group 2 = {C, D}
~~~~

Hai nhóm có thể mỗi nhóm chấp nhận một giá trị khác nhau mà **không gặp bất kỳ node chung**. Nếu protocol dựa trên majority nhưng cho phép 2/4 tự commit, đã phá nguyên tắc an toàn.

Vì thế majority của N=4 là **3**, không phải 2.

### 3.2. Majority của hai cấu hình khác nhau không tự giao nhau

Cấu hình cũ:

~~~~text
Old = {A, B, C}
~~~~

Cấu hình mới:

~~~~text
New = {D, E, F}
~~~~

Một majority của Old có thể là {A,B}; một majority của New có thể là {D,E}. Hai tập **không giao nhau**.

Đó là lý do chuyển cấu hình voting membership cần **giao thức reconfiguration**, không chỉ sửa file config cho từng node rồi xem cả hai cluster đều hợp lệ.

## 4. Cụm ba node và quyền được tiếp tục khi lỗi

Với N=3, Q=2.

~~~~text
        Node A
        /    \
     Node B--Node C
~~~~

### 4.1. Một node bị crash

A và B vẫn liên lạc, C chết:
- A+B đạt **2/3**.
- Có thể bầu một leader hợp lệ nếu giao thức và lịch sử log cho phép.
- Có thể commit write mới nếu leader, log, storage và các bước khác hoạt động đúng.
- Một số thao tác có thể timeout trong lúc election hoặc replay.

Nói “có majority” là **điều kiện cần quan trọng**, không phải bằng chứng mỗi request đã hoàn tất.

### 4.2. Phân vùng 2–1

~~~~text
A <----> B       X       C
   Group 2                 Group 1
~~~~

Trong một consensus group majority:
- Nhóm A+B **có khả năng** bầu/duy trì leader và commit theo protocol.
- C đơn độc **không thể** xác nhận write mới đòi majority 2/3.
- Nếu C là leader cũ, nó có thể chưa phát hiện ngay mình mất liên lạc, nhưng **không được có khả năng commit entry mới khi không đạt điều kiện**.
- Client gọi C có thể nhận timeout/redirect/rejection.
- C vẫn có thể trả một số dữ liệu cũ theo read mode yếu nếu ứng dụng chủ động cho phép; **không được tự gọi đó là linearizable read**.

### 4.3. Chỉ còn một node

Một node duy nhất trong cấu hình 3 voter không đạt quorum.
- Không được tự sửa Q từ 2 xuống 1 trong partition để tiếp tục write mà vẫn giữ cùng hợp đồng an toàn.
- Có thể khôi phục khi voter khác quay lại hoặc thực hiện reconfiguration được protocol hỗ trợ và có thẩm quyền.
- “Force bootstrap” hoặc “force new cluster” ngoài quy trình có thể tạo fork hoặc mất lịch sử committed.

**Sự cố mất majority phải được nhận diện là giới hạn khả năng tiến triển**, không phải một tham số timeout cần tăng vô hạn.

## 5. Cụm năm node: hai lỗi chịu được, nhưng không phải mọi cách chia mạng

N=5, Q=3.

### 5.1. Hai node crash

~~~~text
Alive: A, B, C
Down:  D, E
~~~~

A+B+C đủ majority nếu liên lạc được. Hệ có thể tiếp tục quyết định, dù headroom thấp hơn và khả năng chịu thêm lỗi gần như hết.

### 5.2. Phân vùng 3–2

~~~~text
A--B--C      X      D--E
3 voters             2 voters
~~~~

- Phía 3 có thể tiến triển.
- Phía 2 không thể commit theo majority protocol.
- Không phải “cả cụm sẵn sàng” trong nghĩa mọi client ở mọi phía đều thực hiện được strong write.
- Cần routing client tới phía có authority nếu còn đường mạng phù hợp.

### 5.3. Phân vùng 2–2–1

~~~~text
{A,B}       {C,D}       {E}
~~~~

Không nhóm nào có 3 voter **thực sự trao đổi được với nhau**. Dù cả năm node vẫn chạy, không nhóm riêng nào có điều kiện tiến triển.

**Số node sống ≠ số node có thể hình thành quorum.**

### 5.4. Vì sao thêm node không luôn tốt hơn?

Từ N=3 sang N=4:
- Majority tăng 2 → 3.
- Số voter có thể mất mà vẫn còn majority vẫn là 1.
- Có thêm voter cần quản lý và phản hồi trong một số pha, nhưng khả năng chịu lỗi voter không tăng.

Từ N=3 sang N=5:
- Majority 2 → 3.
- Có thể mất 2 voter trong những điều kiện tương ứng.
- Bù lại chi phí replication/coordination, placement, membership và recovery có thể tăng.

**Nên chọn số voter theo failure model và topology**, không theo nguyên tắc “càng nhiều càng nhanh”. Nhiều hệ ưu tiên số voter lẻ để tối ưu số phiếu cho majority với một số mức chịu lỗi, nhưng hệ thống thực còn có witness/learner/region placement và những ràng buộc khác.

## 6. Quorum trong đồng thuận khác quorum của thao tác đọc/ghi bản sao

Một số NoSQL có thể cho cấu hình:
- Replication factor N.
- Read consistency R.
- Write consistency W.

Một điều kiện quen thuộc:

\[
R+W>N
\]

trong mô hình tập replica ổn định cho biết **read quorum và write quorum có phần giao**.

Đây là một lập luận hữu ích nhưng **không tự biến mọi thao tác read/write thành một consensus protocol**.

| Khía cạnh | Consensus quorum | Replica read/write quorum |
| --- | --- | --- |
| Mục tiêu chính | Thống nhất quyết định, leadership hoặc log/giá trị | Xác định số replica cần phản hồi cho read/write |
| Metadata thường gặp | Term, ballot, accepted value, commit index | Replica version, timestamp, digest hoặc policy tương đương |
| Safety | Do thuật toán bảo toàn quyết định đã chọn | Do toàn bộ read/write protocol và conflict semantics |
| Progress | Phụ thuộc nhóm đủ quorum, leader/đề xuất và thời gian | Phụ thuộc consistency level, replica availability và coordinator |
| Quorum giao nhau | Thiết yếu theo quorum design của algorithm | Có thể hỗ trợ đọc bản mới theo giả định thích hợp |
| Concurrent writes | Quyết định bằng ordering/accept rules của consensus | Có thể cần resolver/LWT hoặc policy khác |
| Membership | Reconfiguration phải bảo toàn intersection | Replica set thay đổi cũng cần semantics an toàn |

### 6.1. Quorum intersection chưa đủ cho linearizability

Giả sử write được ACK bởi A và B, read hỏi B và C. Chúng giao ở B, nhưng read algorithm:
- Có dùng thông tin version của B không?
- Có chọn giá trị committed hoặc đủ mới không?
- Có đồng bộ những concurrent writes không?
- Có chấp nhận sloppy quorum trên tập node khác không?
- Có một metadata/lease/term của leader không?
- Có đòi read-after-write theo thời gian thực không?

Chỉ biết “B trả lời cả hai” chưa chứng minh read linearizable. Cần **hợp đồng hoàn chỉnh của giao thức**.

### 6.2. QUORUM trong Cassandra không tự là Raft

Một normal write với consistency level QUORUM trong Cassandra không đồng nghĩa toàn bộ mỗi write đi qua một Raft replicated log của toàn cụm.

Cassandra có replication/consistency levels và các cơ chế riêng cho conditional update/LWT. Những mức bình thường và giao thức CAS/serial consistency phải được phân tích **riêng**, không dùng chung từ quorum để suy ra serializable transaction đa partition.

### 6.3. Majority ACK trong database khác nhau không đồng nghĩa cùng durability

Có thể khác:
- Replica chỉ nhận message hay đã ghi WAL?
- Có fsync/journal trước ACK không?
- Có bảo đảm leader mới chứa entry đã commit không?
- Một write ở region chính đã tới region DR chưa?
- Quorum có gồm chỉ voter, cả data-bearing members hay cả witness?

**Quorum là cấu trúc điều kiện; mức durability là một phần hợp đồng cụ thể của thao tác.**

## 7. Raft: quorum dùng cho election và commit

**Raft** là một thuật toán replicated state machine dễ dùng để minh họa. Một nhóm Raft có:
- **Leader:** điều phối writes và replication.
- **Followers:** nhận log/heartbeat và tham gia bỏ phiếu.
- **Candidates:** xin phiếu khi cần bầu leader.
- **Terms:** các epoch bầu cử tăng dần.
- **Log entries và commit index:** mô tả lịch sử được thống nhất.

### 7.1. Election không chỉ cần đếm số node còn sống

Một candidate trong cấu hình 5 voter cần đa số phiếu hợp lệ, thường là 3/5.

Nhưng:
- Mỗi voter có luật chỉ bỏ phiếu đúng theo term.
- Log của candidate phải đáp ứng quy tắc “đủ mới” của Raft.
- Một candidate lạc hậu không thể được bầu chỉ vì thấy đủ node.
- Network split/timing có thể gây split votes và bầu cử lặp.

~~~~mermaid
sequenceDiagram
    participant C as Candidate
    participant V1 as Voter 1
    participant V2 as Voter 2
    participant V3 as Voter 3
    C->>V1: RequestVote(term, lastLogInfo)
    C->>V2: RequestVote(term, lastLogInfo)
    C->>V3: RequestVote(term, lastLogInfo)
    V1-->>C: Granted if valid
    V2-->>C: Granted if valid
    Note over C: Majority including own vote?
    C-->>C: Become leader if quorum reached
~~~~

Đếm số phiếu phải theo **cấu hình hiện hành và quy tắc protocol**, không lấy số response HTTP 200 bất kỳ.

### 7.2. Commit log entry theo majority

Ví dụ trong cùng term hiện tại:

~~~~text
Leader A: log[105] = Reserve(OP-101)
Follower B: log[105] = Reserve(OP-101)
Follower C: chưa nhận
Follower D: chưa nhận
Follower E: chưa nhận

A+B = 2/5: chưa đủ majority.

Khi C ghi entry theo quy tắc:
A+B+C = 3/5: đạt điều kiện majority replication.
~~~~

Raft còn có quy tắc quan trọng về cách leader **dùng entry ở current term để suy ra commit** những entry từ term cũ. Không đủ chính xác nếu nói **“bất kỳ entry của bất kỳ term xuất hiện trên 3/5 node đều được leader đánh dấu committed ngay”** mà bỏ qua quy tắc này.

### 7.3. Commit và apply là hai mốc khác nhau

~~~~text
log received/appended
    -> committed by protocol
    -> applied to state machine
    -> client result observed
~~~~

Một follower có thể đã nhận entry nhưng chưa apply. Một leader có thể commit entry rồi response bị mất. Một cache/search index ở ngoài Raft group có thể đi sau rất lâu.

**Không được suy rằng ba node nhận byte giống nhau nghĩa mọi API đọc đã có cùng trạng thái.**

### 7.4. Leader cũ mất quorum

Giả sử A là leader term 8, nhưng bị cô lập với chỉ một voter khác. B,C,D hình thành majority ở phía còn lại và có thể bầu leader term 9.

A có thể:
- Tiếp tục nghĩ mình là leader một thời gian.
- Chấp nhận request vào memory/queue trước khi biết mất quorum.
- Không thể commit write mới cần majority theo giao thức.
- Nhận term mới hoặc timeout rồi từ bỏ leadership.

Ứng dụng không được coi **“leader cũ trả ACK nội bộ/đã append local”** là một commit thành công nếu không đạt điều kiện commit mà API hứa.

## 8. Paxos: proposal/ballot và quorum có giao nhau

**Paxos** cũng dùng các tập acceptors/quorum có tính giao nhau để bảo vệ quyết định.

Trong một mô tả khái niệm:
1. Proposer dùng ballot/proposal number mới.
2. Phase 1 thu thập promise và thông tin đã chấp nhận từ quorum.
3. Proposer có thể cần kế thừa giá trị tương ứng theo quy tắc của Paxos.
4. Phase 2 gửi accept request và cần quorum acceptors chấp thuận.
5. Giá trị được xem là **chosen** theo điều kiện protocol.

### 8.1. Vì sao giao nhau giữa các phase quan trọng?

Nếu một value đã được một quorum chấp nhận/chọn, một proposal ở ballot sau không được chọn một value xung đột thay thế. Quorum intersection giúp proposal mới gặp thông tin cần thiết, và luật chọn value giữ safety.

Nhưng **một proposer gửi đi mà thiếu quorum không thể tự tuyên bố value đã chosen**.

### 8.2. Liveness trong Paxos cũng cần điều kiện ổn định

Hai proposers liên tục tranh quyền, tăng ballot và làm nhau thất bại có thể khiến request không hoàn tất dù hệ còn đủ acceptors.

Một cơ chế **leader/đề xuất ổn định** hoặc backoff/coordination thích hợp giúp progress. Điều này minh họa:

> **Có quorum reachable là điều kiện cần, nhưng chưa luôn đủ để bảo đảm tiến trình hoàn tất trong mọi lịch điều phối bất lợi.**

### 8.3. Raft và Paxos không đồng nhất mọi chi tiết

Cả hai dùng quorum/intersection và cơ chế term/ballot, nhưng:
- Cách bầu leader khác nhau.
- Quy tắc commit/read/reconfiguration có biến thể.
- Một số hệ triển khai Multi-Paxos, Raft hoặc protocol chuyên biệt.
- Từ “quorum” có thể xuất hiện ở những pha không cùng hình thức.

Hãy đọc **đúng giao thức được triển khai** trước khi biến các quy tắc ví dụ thành điều kiện vận hành bắt buộc.

## 9. “Tiến trình có thể tiếp tục” nghĩa là gì?

Một thao tác có **progress** khi có khả năng hoàn thành theo những điều kiện mà hệ thống cam kết, thay vì mãi chờ một điều không thể xảy ra.

Có thể tách ba mức:

1. **Reachability:** Có đủ voter đúng cấu hình trao đổi được thông điệp cần thiết không?
2. **Protocol progress:** Có leader/proposer hợp lệ, term/ballot ổn định và đủ điều kiện để đưa quyết định qua protocol không?
3. **Application progress:** Database có thể commit nhưng application có còn capacity, transaction resources, auth và downstream bắt buộc để trả kết quả nghiệp vụ không?

Một kiểm tra “còn 3 trong 5 node ping được” chỉ đánh giá một lát cắt của điều kiện đầu tiên.

### 9.1. Điều kiện cần điển hình của một write cần majority

- Tập voter hợp lệ của cấu hình biết được.
- Ít nhất Q voter còn hoạt động và **liên lạc được theo đường cần thiết**.
- Có khả năng bầu hoặc xác minh một leader hợp lệ nếu protocol cần leader.
- Quorum đáp ứng các RPC log/ballot đúng term.
- Storage/WAL của thành viên cần thiết hoạt động theo durability contract.
- Không có reconfiguration chưa hoàn tất làm thay đổi quorum rules.
- Request được phép theo auth/business guard, không bị overload vô hạn.
- Một khoảng mạng tương đối ổn định đủ để election/replication hoàn tất.

**Quorum reachable ≠ chắc chắn commit xong.** Quorum thiếu ổn định hoặc disk bị kẹt vẫn có thể dẫn đến timeout.

### 9.2. Một hệ không cần “biết tuyệt đối” đã partition

Trong mạng bất đồng bộ, timeout không phân biệt chắc:
- Node chết.
- Node còn sống nhưng bị phân vùng.
- Node tạm pause do GC.
- Node rất chậm.
- Message bị delay.

Protocol dùng timeout để **nghi ngờ** và khởi động election hoặc recovery; safety phải được xây sao cho các nghi ngờ sai không cho phép hai quyết định xung đột cùng commit.

### 9.3. FLP và tính bất khả thi của bảo đảm tiến triển tuyệt đối

Kết quả FLP ở mô hình chuẩn cho thấy **một thuật toán đồng thuận tất định không thể bảo đảm termination trong hệ hoàn toàn bất đồng bộ khi có khả năng ngay cả một process crash**, trong khi vẫn giữ những giả định correctness tương ứng.

Điều này **không có nghĩa Raft/Paxos vô dụng**. Chúng làm progress dưới các giả định thực tế hơn:
- Mạng cuối cùng ổn định đủ lâu (**eventual synchrony/partial synchrony**).
- Có đủ voter hoạt động.
- Leader/proposer có thể ổn định.
- Các điều kiện timing và scheduling cần thiết được đáp ứng.

Bài học vận hành: **không thể hứa mọi write strong sẽ luôn hoàn tất trong mọi lịch delay/partition tùy ý**. Hệ phải có timeout, trạng thái UNKNOWN, health/readiness và phản hồi tạm không khả dụng rõ ràng.

## 10. Quorum availability phụ thuộc topology, không chỉ N

Cùng 5 voter nhưng hai cách đặt:

**Topology A:**

~~~~text
Region VN: A, B, C
Region EU: D
Region US: E
~~~~

**Topology B:**

~~~~text
Region VN: A, B
Region EU: C, D
Region US: E
~~~~

Trong Topology A, nếu mất hoàn toàn VN, còn D+E=2/5, **không đủ majority**.

Trong Topology B:
- Mất VN → C,D,E=3/5, có thể còn quorum.
- Mất EU → A,B,E=3/5, có thể còn quorum.
- Mất US → A,B,C,D=4/5, có thể còn quorum.

Nhưng tính **vùng nào còn kết nối với vùng nào** và **đường leader/write traffic** vẫn quyết định thực tế có thể làm progress hay không.

### 10.1. Majority đặt qua vùng làm tăng độ trễ?

Nếu leader ở VN cần ACK thêm voter ở EU hoặc US để commit, write latency có thể chịu:
- RTT liên vùng.
- Disk log latency tại voter xa.
- Băng thông và packet loss.
- Replica backlog.
- Cơ chế pipeline và batching.

Một majority cùng local zone có thể nhanh hơn, nhưng lại có failure domain hẹp. Không có một topology tối ưu tuyệt đối; cần đặt theo **RPO/RTO, yêu cầu mất vùng, p99 và chi phí mạng**.

### 10.2. Bài toán ba vùng với 3 voter

~~~~text
VN: A
EU: B
US: C
Q=2
~~~~

Nếu một vùng mất:
- Hai vùng còn lại có thể hình thành majority nếu nối được.
- Strong write có thể cần đường liên vùng ngay cả khi ba vùng khỏe.
- Leader failover cũng chịu network timing.

Nếu mất liên kết giữa mỗi vùng (ba nhóm riêng lẻ), **không nhóm nào có 2 voter**, dù tất cả node còn sống.

### 10.3. Witness và arbiter không tự giữ đủ dữ liệu để recovery

Một **witness/arbiter** có thể tham gia một số quyết định bỏ phiếu nhưng **không giữ cùng dữ liệu như data-bearing replica**, tùy sản phẩm.

Ví dụ:
- Hai data nodes A,B và một witness W.
- A mất, B+W có thể đủ vote cho một số quyết định.
- Nhưng W không có log dữ liệu đầy đủ để thay thế A.

Do đó phải tách:
- **Election quorum:** ai có quyền bỏ phiếu?
- **Data durability quorum:** những node dữ liệu nào đã ghi bền entry?
- **Recovery eligibility:** node nào có log/state đủ mới để tiếp quản?
- **Read availability:** node nào thực sự phục vụ được query?

Không tự nói “3 votes nghĩa là ba bản dữ liệu”.

## 11. Minority side không có quyền commit, nhưng có thể làm gì?

Khi một nhóm thiếu quorum:
- Vẫn có thể nhận TCP connections.
- Vẫn có thể giữ memory cache.
- Có thể trả một số eventual/local reads nếu API cho phép.
- Có thể nhận những intent vào **queue cục bộ** với một hợp đồng khác.
- Có thể trả error/redirect khi strong write không thực hiện được.
- Có thể chờ/retry tới khi quorum hồi phục.

### 11.1. Chấp nhận intent khác xác nhận commit

Hai API response:

~~~~json
{
  "operationId": "OP-101",
  "status": "QUEUED",
  "durability": "local-queue-only"
}
~~~~

và:

~~~~json
{
  "operationId": "OP-101",
  "status": "COMMITTED",
  "orderId": "O-901"
}
~~~~

là **hai hợp đồng**. Một minority node có thể bền vững lưu intent cục bộ, nhưng nó **không được giả vờ** write đã được committed ở consensus group khi quorum không đạt.

Nếu hai vùng chấp nhận local intent đồng thời, cần:
- Dedup khi replay.
- Business conflict resolution.
- Không nhận reservation/payment CONFIRMED trước khi authority thực sự quyết định.
- RPO của local queue và cách xử lý mất vùng.

### 11.2. Read stale phải được công bố đúng mode

Một follower không có quorum có thể trả version 41 trong khi majority đã commit version 42.

Nếu endpoint là eventual read, trả 41 có thể phù hợp hợp đồng.

Nếu endpoint hứa linearizable read, trả 41 sau khi 42 đã hoàn tất **không phù hợp**. Endpoint cần giao thức read đúng (leader/quorum/read barrier) hoặc chờ/route/fail.

### 11.3. Tăng retry không tạo ra quorum

Nếu minority bị tách mạng 10 phút:
- Retry mỗi 10 ms không khiến xuất hiện voter thứ ba.
- Nhiều retry chỉ tăng queue, CPU và connection pressure.
- Client cần deadline, bounded backoff+jitter, circuit breaker và phản hồi rõ.

**Mất quorum là điều kiện topology/protocol**, không phải chỉ là lỗi hiệu năng tạm có thể chữa bằng tăng thread count.

## 12. Leader ownership và fencing token

Một leader cũ có thể tiếp tục thực thi code sau khi nhiệm kỳ đã không còn hợp lệ. Trong storage consensus đúng, nó không thể commit entry mới trái protocol, nhưng **external resources** (file system, payment processor, cache hoặc một database khác) có thể không biết term đã đổi.

### 12.1. Ví dụ leader cũ và leader mới

~~~~text
T0 Leader A term=7 xử lý job.
T1 A pause do GC.
T2 Quorum bầu B term=8.
T3 B gửi write tới external storage.
T4 A tỉnh lại và cũng gửi write tới external storage.
~~~~

Nếu external storage chấp nhận cả hai write không có hàng rào, có thể:
- Ghi đè bản mới bằng dữ liệu cũ.
- Thực hiện side effect trùng.
- Phá invariant ngoài consensus group.

### 12.2. Fencing theo epoch

Một resource có thể lưu lastAcceptedEpoch:

~~~~text
write(resource, epoch, payload):
    IF epoch >= lastAcceptedEpoch
        apply according to operation's own guard
        lastAcceptedEpoch := max(lastAcceptedEpoch, epoch)
    ELSE
        reject stale writer
~~~~

Đây là **mô hình khái niệm**. Trong ứng dụng thực, điều kiện/ghi epoch phải được bảo vệ atomically tại resource có thẩm quyền. Chỉ gửi một integer qua API nhưng server không xác minh không có tác dụng.

### 12.3. Term không thay business operationId

- **Term/epoch/fencing:** ngăn writer cũ dùng quyền đã hết.
- **OperationId/idempotency key:** ngăn cùng ý định nghiệp vụ bị thực thi hai lần khi retry.
- **Version/CAS:** ngăn ghi đè trạng thái đã thay đổi.
- **Transaction:** bảo vệ nhiều thay đổi trong scope được hỗ trợ.

Một hệ có thể cần **cả bốn**. Nếu OP-101 đã commit, leader mới không được tạo OP-102 chỉ vì term đổi.

### 12.4. Lease và đồng hồ

Leader leases có thể cải thiện đường đọc/ghi trong một số protocol nhưng cần giả định về:
- Clock drift.
- Lease validity và renewal.
- Pause/GC.
- Fencing của external resource.
- Failover và overlapping leases.

Một Redis TTL lock hoặc một local flag **isLeader=true** không tự là chứng minh quyền ghi an toàn sau partition. Khi business có invariant quan trọng, kiểm tra quyền tại chính điểm side effect.

## 13. Thay đổi thành viên voting: điều kiện tiến trình có thể thay đổi

Khi thêm/bớt voter, không được chỉ sửa N trong dashboard.

Ví dụ:
- Old config = {A,B,C}.
- New config = {B,C,D,E,F}.

Nếu một số node nghĩ Old có hiệu lực, số khác nghĩ New có hiệu lực, những nhóm quyết định có thể không giao nhau theo rules đơn giản. Consensus protocols dùng cơ chế **configuration change** để bảo toàn safety.

### 13.1. Joint consensus và staged reconfiguration

Một cách tiếp cận như trong Raft joint consensus dùng giai đoạn chuyển tiếp với điều kiện quyết định dựa trên cả **old và new configurations**, giúp tránh hai nhóm riêng tự ra quyết định xung đột.

~~~~text
Old configuration
       |
       v
Joint transitional configuration
       |
       v
New configuration
~~~~

Cách cấu hình cụ thể phụ thuộc implementation (có hệ chọn thay từng voter với rules riêng). Điều quan trọng là **không cho hai cấu hình độc lập xác nhận concurrent decisions**.

### 13.2. Progress trong giai đoạn chuyển tiếp có thể khó hơn

Nếu giai đoạn chuyển tiếp đòi quorum old **và** quorum new:
- Một node ở cấu hình old bị mất có thể làm thiếu quorum old.
- Một node mới chưa bắt kịp có thể chưa phù hợp để bỏ phiếu.
- Thay đổi placement/network có thể khiến cả hai quorum không cùng reachable.

Do đó việc thay thành viên cần:
- Đủ healthy voters trước khi bắt đầu.
- Learner/catch-up phase nếu protocol hỗ trợ.
- Kiểm soát các lần thay đổi nối tiếp.
- Monitoring membership state/commit index.
- Không tự sửa config một cách độc lập khi đang partition.

### 13.3. Learner/non-voter

Một replica mới có thể được thêm ở trạng thái **learner**:
- Nhận/sao chép log để bắt kịp.
- Chưa tính vào voting quorum.
- Chỉ sau khi đủ điều kiện mới được promote.

Lợi ích là tránh tăng quorum threshold trước khi node mới thực sự có thể đóng góp. Nhưng tính năng và thao tác promote phụ thuộc sản phẩm.

### 13.4. Reconfiguration không phải nút “bỏ qua majority”

Khi chỉ còn minority của một cấu hình, không được tự tuyên bố chúng là cấu hình mới độc lập chỉ để chấp nhận writes.

Những quy trình emergency recovery có thể cần sự can thiệp có kiểm soát và đánh đổi khả năng giữ lịch sử đã ACK; phải theo tài liệu sản phẩm và runbook có audit. **Không sửa trực tiếp membership metadata production bằng phỏng đoán.**

## 14. Quorum bầu cử và quorum commit cần xem cùng nhau

Một tình huống dễ hiểu nhầm:

~~~~text
Node A vừa là leader cũ vừa giữ entry X.
Node B, C hình thành majority mới.
~~~~

Tại sao B/C không được bầu một leader thiếu những log entries đã committed và rồi ghi đè X?

Trong Raft, quy tắc bầu cử **log up-to-date** và các luật log replication/commit phối hợp để bảo vệ những entry đã committed. Trong Paxos, thông tin promise/accepted ballot và quy tắc chọn giá trị bảo toàn quyết định đã chosen.

**Không phải cứ bầu được 2/3 node là an toàn nếu election protocol bỏ qua lịch sử log.**

### 14.1. Majority election không thể được kiểm tra bằng ping

Một công cụ:

~~~~text
A: responding
B: responding
C: responding
~~~~

chỉ cho biết reachability. Nó không nói:
- Node nào có term mới nhất.
- Node nào có log đủ mới.
- Node nào đã vote trong term này.
- Write nào đã committed.
- Storage nào durable.
- Có candidate nào được bầu hợp lệ không.

Health check phục vụ routing/alert, **không thay chứng cứ protocol**.

### 14.2. Read Index hoặc read barrier

Trong một số triển khai Raft, **leader linearizable read** cần chứng minh leader vẫn có quyền phục vụ read ở thời điểm liên quan, ví dụ bằng **ReadIndex/quorum confirmation** hoặc một lease protocol được chứng minh đúng.

Không thể chỉ đọc từ memory của một node từng là leader mà mặc định đã có strong read. Sau partition, leader cũ có thể đã mất quyền mà chưa biết.

## 15. Khi một quorum còn sống nhưng vẫn không tiến triển

### 15.1. Election liên tục bị chia phiếu

Ba trong năm voter còn liên lạc, nhưng nhiều candidates cùng timeout và giành phiếu:
- Quorum toán học tồn tại.
- Leader không ổn định.
- Requests có thể timeout.

Randomized election timeout, backoff và heartbeat timing có thể giúp, nhưng không có bảo đảm termination tuyệt đối trong mạng bất đồng bộ vô hạn delay.

### 15.2. Log/disk chậm

Majority có thể ping được nhưng:
- WAL append/fsync bị stall.
- Disk full.
- Replica không hoàn tất RPC.
- Checkpoint/recovery mất thời gian.

Nếu commit policy đòi durable ACK, **voter có mặt nhưng không đáp ứng durability condition** không giúp write progress.

### 15.3. Leader không có log đủ mới

Một candidate có thể giao tiếp với majority nhưng bị từ chối vì log lạc hậu. Cần một candidate đủ điều kiện và ổn định để được bầu.

### 15.4. Membership change đang kẹt

Đang chuyển cấu hình, quorum của old/new group có thể không cùng hình thành. Chỉ nhìn N mới không đủ.

### 15.5. Quorum có thể commit log nhưng ứng dụng không thể hoàn thành

Ví dụ Order DB còn quorum nhưng:
- Inventory authority ở shard khác thiếu quorum.
- Payment provider không truy cập được.
- Unique constraint service lỗi.
- Transaction coordinator đang unavailable.

Database consensus group có thể progress nhưng **business workflow phải PENDING/UNKNOWN hoặc từ chối**.

### 15.6. Leader đang overload

Leader chịu:
- Hot key contention.
- Nhiều clients retry.
- Log replication backlog.
- GC pauses.
- Cross-region slow quorum member.

Quorum vẫn tồn tại, nhưng throughput thực đạt rất thấp. Cần phân biệt **không có điều kiện commit** với **có điều kiện nhưng năng lực/latency không đạt SLO**.

## 16. Safety khi partition và CAP

Định lý CAP thường được dùng để diễn giải giới hạn: trong những lịch sử có partition, không thể đồng thời giữ **linearizable consistency** và **availability theo nghĩa mọi request tới node không hỏng đều được đáp ứng hợp lệ** cho đối tượng đang xét.

Một consensus group majority thường **ưu tiên safety** của quyết định:
- Phía có majority có thể tiếp tục.
- Phía thiếu majority phải chặn/không xác nhận những quyết định cần consensus.
- Một số request có thể chờ vô hạn nếu partition không lành.

Đây không phải “hệ luôn unavailable”. Khi mạng khỏe, cluster có thể phục vụ bình thường; trong partition 3–2 của N=5, nhóm 3 có thể vẫn commit.

### 16.1. Cần phân biệt CAP availability với SLO vận hành

| Mục tiêu | Ví dụ | Điều đo |
| --- | --- | --- |
| **CAP A** | Mọi operation ở node không hỏng có phản hồi hợp lệ trong mô hình | Thuộc tính lý thuyết |
| **Operational availability** | 99,95% request thành công dưới deadline | Success rate, error budget |
| **Consensus progress** | Nhóm đủ quorum có commit được log entry không | Election/commit throughput |
| **Business availability** | Khách có đặt hàng thật sự thành công không | Confirmed booking, checkout completion |
| **Data safety** | Không hai booking giữ cùng slot | Invariant violations |
| **Durability** | Write ACK sống sót qua mất node/vùng nào | Recovery drill, RPO |

Một endpoint có thể trả HTTP 202/PENDING rất nhanh và được tính là một API response, nhưng **chưa hứa đã commit booking**. Không được dùng đó như bằng chứng không phải đánh đổi CAP.

### 16.2. “Cho minority ghi tạm” là đổi hợp đồng

Một ứng dụng có thể chấp nhận offline intents cục bộ rồi đồng bộ khi mạng lành. Điều này hợp lý với:
- Drafts.
- Telemetry có dedup/replay.
- Giỏ hàng cho phép merge.
- Tác vụ không đòi invariant toàn cục ngay.

Nhưng với:
- Sản phẩm cuối cùng.
- Một slot đặt phòng duy nhất.
- Số dư ví.
- Thu hồi quyền truy cập tức thời.

thì chỉ nhận intent cục bộ **không đủ để CONFIRM**; cần quyết định hợp lệ ở authority, escrow rights hoặc cơ chế nghiệp vụ khác.

## 17. Quorum và độ bền ghi: failure domain là điều quyết định

Giả sử một quorum gồm ba voter A,B,C cùng nằm ở **một availability zone**, D,E ở các zone khác.

Một write được 3/5 ACK nhưng cả A,B,C mất điện đồng thời:
- Tùy giao thức và nơi dữ liệu còn bền, rủi ro khôi phục có thể khác trường hợp chỉ một voter chết.
- Quorum safety nói về quyết định và lịch sử dưới fault model của protocol, nhưng **deployment placement/common-mode failure** cần được phân tích thêm.
- Nếu những node còn lại thiếu log/không đủ quorum, khả năng phục vụ và recovery chịu ảnh hưởng.

**Không suy “majority ACK = RPO 0 trước mọi thảm họa”**. Cần xác định:
- Replica nào đã ghi log durable?
- Những replica đó nằm ở host/zone/region nào?
- Có witness không data-bearing?
- Backup/PITR ở đâu?
- Một lỗi chung có thể làm mất toàn bộ quorum/log cùng lúc không?

### 17.1. Quorum và backup giải quyết các rủi ro khác nhau

Replication/consensus giúp giữ lịch sử khi một số node lỗi; backup giúp phục hồi khi:
- Operator xóa nhầm.
- Bug ghi sai hàng loạt.
- Dữ liệu bị hỏng logic.
- Ransomware hoặc xóa lan qua mọi replica.
- Cần khôi phục về thời điểm trước đó.

Ba hoặc năm voter không thay thế **backup/restore drill**.

### 17.2. RTO không suy từ số voter

N=5, mất hai node, quorum vẫn đủ, nhưng:
- Leader election mất thời gian.
- Snapshot/log replay chậm.
- Client DNS/routing chưa chuyển.
- Cache lạnh.
- Quorum voter mới đang bắt kịp.

**RTO** là thời gian dịch vụ phục hồi đủ contract, không chỉ thời điểm “có 3/5 node online”.

## 18. Khi nào nên tăng quorum size hoặc số voter?

Tăng số voter có thể:
- Nâng số lỗi voter chịu được.
- Phân tán failure domains.
- Tăng dữ liệu/metadata replication.
- Tăng độ phức tạp election/membership.
- Thay đổi RTT của quorum quyết định.
- Tăng nhu cầu capacity cho recovery.

Điểm quyết định:
- Fault model: mất node, zone, region?
- Topology: voter đặt ở đâu?
- Write latency p99 target?
- Data durability và read consistency?
- Network cost/egress?
- Election/failover stability?
- Bao nhiêu shards/consensus groups độc lập?
- Một tenant hoặc hot key có cần local authority khác?

### 18.1. Không làm N=5 chỉ vì “an toàn hơn”

Nếu năm voter đều ở một rack:
- Một rack failure vẫn có thể hạ cả nhóm.
- N=5 không cải thiện failure-domain isolation so với ba voter phân tán hợp lý.

Nếu muốn survive mất một region, **placement và số voter ở các region còn lại** quan trọng hơn N đơn thuần.

### 18.2. Tăng replication factor không nhất thiết tăng write throughput

Trong một consensus group, write thường đi qua một leader hoặc một cơ chế coordination. Tăng voter:
- Có thể tăng khả năng chịu lỗi.
- Không tự chia load của **một hot key** qua nhiều independent authorities.
- Có thể tăng replication work/network.
- Có thể làm đường majority chậm nếu layout xấu.

Muốn tăng write throughput, có thể cần **sharding thành nhiều consensus groups**, partition key hợp lý hoặc thay mô hình invariant; không mặc định tăng replication factor.

## 19. Nhiều shard: mỗi consensus group có tiến trình riêng

Giả sử:
- 64 shards.
- Mỗi shard có một nhóm replication/consensus riêng.
- Shard 12 đang thiếu quorum; 63 shard khác đủ.

Có thể xảy ra:
- Point writes vào shard 12 bị chặn.
- Writes tới shard khác vẫn hoạt động.
- Một transaction chạm cả shard 12 và shard 30 bị ảnh hưởng.
- Analytics scan tất cả shards chịu tail latency từ shard 12.
- Cluster-wide metadata/control-plane outage có thể ảnh hưởng cả 64 shard nếu phụ thuộc chung.

Do đó **quorum availability theo shard/group**, không phải chỉ một trạng thái “cluster UP”.

### 19.1. Giao dịch nhiều shard có nhiều điểm phải tiến triển

Một transaction:

~~~~text
Reserve SKU-A -> Shard 12
Reserve SKU-B -> Shard 30
Insert Order  -> Shard 48
~~~~

Ngay cả khi Shard 30 và 48 còn quorum, Shard 12 thiếu:
- Không thể xác nhận invariant chung nếu transaction cần cả ba.
- Có thể có transaction coordinator hoặc commit protocol cần xử lý retry/timeout.
- Một số hệ hỗ trợ distributed transaction; một số chỉ bảo đảm mỗi item/partition.

**Quorum của từng shard không tự biến nhiều writes rời rạc thành transaction all-or-nothing.**

### 19.2. Deadlock/timeout không có nghĩa transaction đã rollback

Nếu coordinator timeout sau khi gửi commit đến một số participants:
- Outcome có thể UNKNOWN.
- Cần tra transaction identity/operation ledger.
- Không khởi động một giao dịch nghiệp vụ mới không có dedup guard.

## 20. Quyền ghi và một nguồn có thẩm quyền

Một số hệ thống đặt **single writer authority** cho mỗi aggregate/shard để dễ kiểm soát thứ tự:
- Một leader nhận writes.
- Followers phản hồi log/commit.
- Client phải định tuyến tới leader hợp lệ.

Điểm mạnh:
- Có một đường quyết định rõ ràng.
- Dễ xây sequential log trong phạm vi group.
- Các clients cạnh tranh trên một aggregate gặp cùng authority.

Giới hạn:
- Leader là điểm tập trung write traffic.
- Failover cần election.
- Remote clients chịu RTT.
- External side effects cần fencing.
- Một hot aggregate có thể không được giải quyết bằng thêm followers.

### 20.1. “Có leader” khác “có quyền commit”

Một node có thể:
- Từng được bầu làm leader.
- Tạm mất majority.
- Chưa nhận tin leader mới.
- Vẫn giữ local leader flag.

**Quyền commit mới phải được chứng minh theo protocol ở term hợp lệ**, không chỉ bằng một biến trạng thái trong ứng dụng.

### 20.2. Ownership của ứng dụng ngoài consensus group

Nếu một worker sở hữu shard job bằng lease:
- Lease hết hạn cần có ownership epoch.
- Những write vào target storage phải kiểm tra epoch/fencing khi cần.
- Việc đổi worker phải không nhân đôi business effect.
- Mỗi job có operation ID hoặc effect guard.

Đồng thuận trong control plane có thể chọn owner, nhưng **data plane phải thực thi quyết định ấy**.

## 21. Read consistency trong consensus-backed NoSQL

Có consensus quorum cho log không tự đồng nghĩa mọi read đều linearizable.

Các đường đọc có thể khác:

| Read path | Điều kiện | Rủi ro hoặc đánh đổi |
| --- | --- | --- |
| Leader read có read barrier/quorum validation phù hợp | Xác minh quyền leader/commit visibility | Có coordination latency |
| Leader lease read theo giao thức đúng | Lease và clock assumptions hợp lệ | Phải kiểm tra clock/drift/fencing |
| Follower eventual read | Trả local applied state | Có thể stale |
| Follower read yêu cầu minCommitIndex | Chờ/route tới replica đã apply đủ | Có thể tăng p99 hoặc unavailable |
| Cache | TTL/invalidation | Không tự kế thừa linearizable source semantics |
| Search/read model | CDC/index refresh | Query-visible lag |
| Transaction snapshot | Snapshot/isolation rules | Không tự giống read point-in-time mới nhất toàn cầu |

### 21.1. Read-your-writes

Client viết x=10 thành công ở leader rồi đọc follower chưa apply:
 
~~~~text
Write x=10 -> consensus committed, ACK
Follower read -> x=9
~~~~

Có thể hợp lệ nếu API **cho phép eventual follower reads**. Nếu hứa read-your-writes, phải:
- Route tới source/replica đủ mới.
- Mang session/version/commit-index token được hệ hỗ trợ.
- Chờ follower catch up.
- Hoặc trả trạng thái tạm không đáp ứng thay vì âm thầm trả x=9.

### 21.2. Quorum read không phải phép GET hai replica bất kỳ

Một read linearizable trên Raft không được implement đơn giản bằng “gọi GET tới hai trong ba nodes và lấy giá trị có timestamp cao nhất” nếu không có protocol bảo vệ ordering/leadership/commit state phù hợp.

**Quorum intersection là thành phần của chứng minh an toàn, không phải một thuật toán read đầy đủ.**

## 22. Timeout sau quorum commit: client có thể không biết kết quả

Một tình huống phổ biến:

~~~~mermaid
sequenceDiagram
    participant C as Java client
    participant L as Leader
    participant F1 as Follower 1
    participant F2 as Follower 2
    C->>L: Reserve(OP-101)
    L->>F1: Append entry
    L->>F2: Append entry
    F1-->>L: ACK
    Note over L: Quorum commit reached
    L--xC: Response lost
    Note over C: Timeout, outcome UNKNOWN
~~~~

Khi client timeout, có các trường hợp:
1. Request chưa tới.
2. Leader reject trước khi commit.
3. Request đang xử lý và có thể commit muộn.
4. Request đã committed, ACK mất.

**Không có một kết luận “rollback” chung từ SocketTimeoutException.**

### 22.1. Retry cùng operationId

Một operation nghiệp vụ:

~~~~json
{
  "operationId": "OP-101",
  "tenantId": "T-42",
  "sku": "BOOK-42",
  "quantity": 1,
  "requestFingerprint": "hash-of-canonical-request"
}
~~~~

Nếu retry cùng operationId:
- Khi operation đã committed, hệ trả **kết quả cũ**.
- Khi operation chưa bắt đầu, hệ có thể thực hiện dưới unique/conditional guard.
- Khi đang in-flight, hệ cần chặn/tách để không có hai tác dụng.
- Khi cùng key nhưng payload khác, phải trả conflict.

Cơ chế này cần **ledger hoặc command dedup** được ghi trong ranh giới atomicity/transaction phù hợp với side effect.

### 22.2. Ghi ledger sau write rời rạc là sai

Flow:

~~~~text
1. Decrement stock.
2. Insert processedOperationId.
~~~~

Nếu crash sau 1 trước 2, retry có thể trừ thêm. Đổi thứ tự cũng có thể khiến ledger đã ghi nhưng stock chưa thay đổi.

Để giữ đúng:
- Ghi side effect + ledger atomically khi engine hỗ trợ.
- Hoặc dùng state machine/reservation workflow có compensation/reconciliation rõ.
- Không dựa vào cache/eventual index để chứng minh operation chưa xảy ra.

### 22.3. Quorum commit không giải quyết exactly-once ở payment provider

Một replicated log trong database có thể chắc chắn chỉ apply một command theo protocol, nhưng call tới payment provider ở ngoài group có thể:
- Timeout sau khi provider đã capture.
- Bị worker retry.
- Có side effect độc lập.

Cần **provider idempotency key, operation ledger, outbox và reconciliation**. Quorum của DB không bao trùm external side effect.

## 23. Java 21: tính quorum và điều kiện reachability minh họa

Ví dụ thuần Java để tính majority và số voter có thể liên lạc. Đây **không phải triển khai Raft**, không chứng minh leader hợp lệ và không được dùng thay protocol đồng thuận thật.

~~~~java
import java.util.Objects;
import java.util.Set;

public record VotingConfiguration(Set<String> voters) {
    public VotingConfiguration {
        Objects.requireNonNull(voters, "voters");
        voters = Set.copyOf(voters);
        if (voters.isEmpty()) {
            throw new IllegalArgumentException(
                    "voting configuration must not be empty");
        }
    }

    public int majority() {
        return voters.size() / 2 + 1;
    }

    public boolean hasReachableMajority(
            Set<String> reachableVoterIds
    ) {
        Objects.requireNonNull(reachableVoterIds);
        long count = reachableVoterIds.stream()
                .filter(voters::contains)
                .count();
        return count >= majority();
    }
}
~~~~

Dùng ví dụ:

~~~~java
VotingConfiguration config = new VotingConfiguration(
        Set.of("A", "B", "C", "D", "E")
);

boolean groupABC = config.hasReachableMajority(
        Set.of("A", "B", "C")
); // true: 3/5

boolean groupDE = config.hasReachableMajority(
        Set.of("D", "E")
); // false: 2/5

int quorum = config.majority(); // 3
~~~~

**Giới hạn quan trọng:**
- Reachability là một quan sát tạm thời, có thể thay đổi giữa lệnh kiểm tra và commit.
- Các node đáp ứng ping không nhất thiết chấp nhận term/ballot/log.
- Membership có thể đang reconfigure.
- Disk của node có thể đầy, voter không thể ghi durable.
- Một node có thể reply nhưng không phải voter hợp lệ.
- Không kiểm tra commit index, leader completeness hay fencing.
- Không tự bảo đảm request ở API có quyền ghi.

Code chỉ giúp tránh lỗi tính majority và nhầm non-voters; **không dùng kết quả boolean này để cho phép write bỏ qua consensus engine**.

### 23.1. Trạng thái COMMITTED, REJECTED, UNKNOWN ở tầng service

~~~~java
public enum CommitOutcome {
    COMMITTED,
    REJECTED,
    UNKNOWN
}

public record CommitResult(
        String operationId,
        CommitOutcome outcome,
        String resourceId,
        String message
) {}
~~~~

Repository nghiệp vụ:

~~~~java
public interface ReservationRepository {
    CommitResult reserveIdempotently(
            String tenantId,
            String sku,
            long quantity,
            String operationId
    );

    CommitResult getOperationStatus(
            String tenantId,
            String operationId
    );
}
~~~~

Một API khi thiếu quorum có thể:
- **REJECTED** nếu server có bằng chứng terminal request không được chấp nhận và không thể commit.
- **UNKNOWN** nếu request đã có thể tới backend và kết quả chưa rõ.
- **PENDING** nếu ứng dụng có hợp đồng nhận intent cục bộ riêng.
- **COMMITTED** chỉ khi đạt điều kiện xác nhận đã công bố.

### 23.2. Pseudocode đặt hàng an toàn hơn

~~~~text
POST /reserve {operationId, sku, quantity}

if quantity <= 0:
    return invalid_request

try:
    result = authoritativeStore.reserveAtomically(
        operationId,
        sku,
        quantity
    )

    if committed:
        return CONFIRMED(result.reservationId)

    if known business failure:
        return REJECTED(result.reason)

catch NoQuorumBeforeOperationAccepted:
    return TEMPORARILY_UNAVAILABLE

catch UnknownWriteOutcome:
    return UNKNOWN(operationId)

# UNKNOWN handler:
#   retry/query with same operationId under durable idempotency guard
#   do not create a new booking identity
~~~~

Pseudocode không khẳng định SDK nào có exception đúng tên trên. Trong thực tế phải **phân loại lỗi từ API/driver cụ thể**, vì một network timeout nói chung có thể là UNKNOWN.

## 24. Tính availability quorum dưới giả định xác suất đơn giản

Để hiểu sự khác nhau giữa số node và khả năng còn quorum, giả sử:
- Mỗi voter hoạt động độc lập với xác suất p.
- Network luôn nối được các voter còn sống.
- Không có common-mode failure, routing/leader election/disk issues.
- Ta chỉ xét số voter hoạt động, chưa xét SLO.

Với N=3, Q=2, xác suất có ít nhất hai voter hoạt động:

\[
P_{\ge2}=\binom32p^2(1-p)+p^3
\]

Nếu p=0,99:

\[
P_{\ge2}=3(0{,}99)^2(0{,}01)+(0{,}99)^3
=0{,}999702
\]

Tức khoảng **99,9702%** trong mô hình giả định.

### 24.1. Vì sao tính toán này không phải uptime SLO thực?

Vì production có thể có:
- Cùng power/network zone.
- Phân vùng network dù cả ba node sống.
- Leader election mất thời gian.
- Disk stalls/compaction.
- Routing failure.
- Software bug chung.
- Cross-shard dependency.
- Quorum witness không chứa dữ liệu.

Công thức độc lập **không thay thế fault model và chaos test**.

### 24.2. Với N=5

Xác suất còn majority nếu chỉ có lỗi node độc lập:

\[
P_{\ge3}=
\sum_{k=3}^{5}\binom5k p^k(1-p)^{5-k}
\]

Nhưng nếu cả 5 voter nằm cùng một region, xác suất mất region có thể chi phối kết quả thực. Tính thêm node trong cùng failure domain **không sửa được common-mode risk**.

## 25. Ước lượng write latency quorum

Giả sử một leader có:
- Log append/fsync local: 4 ms.
- Follower F1 phản hồi sau 6 ms.
- Follower F2 phản hồi sau 45 ms.
- Follower F3 phản hồi sau 80 ms.
- Follower F4 phản hồi sau 120 ms.

N=5, Q=3, nếu tính leader là một voter đã đạt điều kiện và cần thêm **hai follower**:
- Các follower nhanh nhất là F1 và F2.
- Trong mô hình đơn giản chạy song song, quorum có thể tới khi follower thứ hai phản hồi: khoảng 45 ms, cộng overhead xử lý/commit/response.

**Không phải luôn chờ 120 ms của follower chậm nhất.**

### 25.1. Quorum latency là thống kê thứ tự

Quorum completion thường phụ thuộc thời gian của **thành viên chậm thứ k cần thiết** sau khi tính điều kiện local/leader, không nhất thiết là trung bình latency của các follower.

Nếu F1 bị mất, leader cần F2+F3 → khoảng 80 ms theo ví dụ. Nếu F1,F2 cùng mất, cần F3+F4 → khoảng 120 ms nếu cả hai còn trả lời.

Đây là xấp xỉ; thuật toán thật có thể cần thêm round trips, log commit rules, batching, disk sync và quorum reconfiguration.

### 25.2. Quorum còn nhưng p99 không đạt SLO

Một cụm 5 node còn 3 voter:
- Safety và tiến trình về mặt protocol có thể giữ.
- Nếu voter thứ ba ở vùng xa 200 ms, p99 write có thể vượt SLO 100 ms.
- Nếu request queue tăng, timeout có thể xảy ra dù cuối cùng log vẫn commit.

Phải đo **availability trong deadline và latency theo quorum topology**, không chỉ “còn quorum = GREEN”.

## 26. Điều kiện tiến trình theo các trạng thái lỗi

| Trạng thái | Có majority? | Có thể commit strong write? | Điểm cần kiểm tra |
| --- | --- | --- | --- |
| 3/3 voter khỏe | Có | Có thể | Leader/term/log/disk |
| 2/3 voter còn liên lạc | Có | Có thể | Election/failover |
| 1/3 voter cô lập | Không | Không theo majority contract | Chỉ weak read/intent nếu cho phép |
| 5 node chia 3–2 | Nhóm 3 có | Nhóm 3 có thể | Minority không confirm |
| 5 node chia 2–2–1 | Không nhóm nào có | Không theo majority | Chờ/heal/recovery |
| 5 node, 3 ping được nhưng disk full | Toán học có 3 | Chưa chắc | ACK durability không hoàn tất |
| 5 node, 3 kết nối nhưng election split | Có thể reachable | Có thể chưa | Leader stabilization |
| Reconfiguration joint bị thiếu old quorum | Không đủ điều kiện chuyển | Có thể kẹt | Old/new quorum rules |
| Leader mất quorum nhưng vẫn ping client | Không có quorum commit | Không được xác nhận | Fencing/redirect |
| Một shard mất quorum, shard khác khỏe | Theo shard | Một số shard có | Transaction fan-out |
| Data source khỏe, payment lỗi | DB có | Business workflow chưa xong | External dependency |
| Quorum ACK xong, client ACK mất | Đã commit nhưng client UNKNOWN | Có thể | Idempotency/reconcile |

### 26.1. Mất quorum không luôn dẫn đến mất dữ liệu

Khi không đủ voter:
- Có thể không commit thêm được.
- Các log entries đã committed trước đó có thể vẫn tồn tại bền ở những node tương ứng.
- Read weak/backup có thể còn hoạt động.
- Khi node quay lại, cluster có thể khôi phục quorum và tiếp tục.

**Không nhầm availability outage với data loss**. Cần xác minh durability và trạng thái log trước khi kết luận.

### 26.2. Còn quorum không luôn dẫn đến “không mất dữ liệu”

Nếu dữ liệu chỉ được ghi theo policy yếu, hoặc placement tập trung trong một failure domain có rủi ro chung, thảm họa ngoài fault model có thể làm mất cả những bản được xem là an toàn trước đó.

**Điều kiện commit và bảo đảm survive failure phải được định nghĩa theo đúng protocol/storage contract.**

## 27. Chọn topology cho nhiều vùng

Một bài toán:
- Ba region VN, EU, US.
- Đơn hàng cần không xác nhận trùng và không mất write đã ACK trong một node failure.
- Người dùng cần p99 checkout phù hợp.
- Mất region là một rủi ro business đáng kể.

Có thể so sánh các hướng:

| Topology minh họa | Ưu điểm | Giới hạn cần đánh giá |
| --- | --- | --- |
| 3 voter cùng VN, async DR tới EU/US | Local quorum nhanh | Mất VN có thể mất quorum/remote RPO |
| 1 voter mỗi region, N=3 | Có thể còn 2/3 khi một region mất | Cross-region RTT trên commit path |
| 5 voter phân bố 2-2-1 | Có thể còn 3/5 khi mất một trong ba region, nếu hai region còn liên lạc | Quorum latency/egress/election |
| 3 voter VN + 2 witness vùng xa | Election topology có thể hữu ích theo engine | Witness không tự bảo đảm data durability |
| Một authority VN + escrow rights cho vùng khác | Một số nghiệp vụ hoạt động cục bộ trong giới hạn quyền | Transfer rights/recovery phức tạp |
| Mỗi region active-write với reconciliation | Có thể nhận writes cục bộ | Không tự giữ uniqueness/quota cứng; cần conflict policy |

Không có lựa chọn tốt nhất nếu chưa đặt:
- RPO cho mất một node/zone/region.
- RTO khi leader failover.
- Write p99 từ mỗi vùng.
- Dữ liệu nào được phép stale.
- Invariant nào phải strong.
- Data residency.
- Cost network/cross-region replication.

### 27.1. Đừng dùng một consensus group toàn cầu cho mọi event nếu không cần

Nếu hàng trăm nghìn tenant có sự kiện độc lập:
- Có thể phân vùng thành nhiều consensus groups hoặc partitions theo owner.
- Chỉ những thao tác cần cùng invariant mới cần cùng một điểm phân xử.
- Read models/analytics có thể eventual.
- Một global metadata/ID service cần được đánh giá riêng về hotspot/blast radius.

Một consensus group ghi mọi event trên toàn hệ có thể tạo leader hotspot và RTT xuyên vùng không cần thiết.

## 28. Quan sát điều kiện tiến triển ở production

Dashboard tối thiểu nên phân biệt:

| Nhóm | Metric | Diễn giải |
| --- | --- | --- |
| Membership | Config version, voting member count, learners | Quorum dựa trên tập nào? |
| Reachability | Per-peer connection/RTT/packet loss | Ai có thể trao đổi với ai? |
| Leader | Leader term, election rate, leader changes | Leadership có ổn định không? |
| Voting | Granted/rejected votes, split elections | Có bầu được leader hợp lệ? |
| Commit | Commit index lag, uncommitted entries age | Log entry có tiến triển? |
| Apply | Applied index vs commit index | State machine có bắt kịp? |
| Durable log | WAL append/fsync latency, disk errors | Replica ACK đạt mức bền? |
| Quorum health | Available voting majority per group | Những shard nào thiếu quorum? |
| Client | Strong write success/timeouts/UNKNOWN | Người dùng nhận kết quả gì? |
| Read | Linearizable read barrier latency, stale read rate | Đường đọc đáp ứng mode không? |
| Replication | Per-replica received/applied lag | Replica nào chưa theo kịp? |
| Topology | Per-zone/per-region voter placement | Có common-mode risk? |
| Reconfiguration | Joint phase age, new learner catch-up | Membership change kẹt không? |
| Recovery | Election duration, log replay, RTO | Failover hoàn tất tới đâu? |
| Business | Oversell/duplicate order/negative balance | Safety ứng dụng còn giữ? |

### 28.1. Chỉ đo “nodes healthy” là không đủ

Một metric **healthyNodes=3** không chứng minh:
- Ba node là voter của cùng một group.
- Ba node thuộc một connected component.
- Đã bầu leader.
- Log đủ mới.
- Disk durable.
- Read path mạnh đã hợp lệ.

Đề xuất dashboard theo **consensus group/shard**, đi kèm leader term, commit progress và request outcomes.

### 28.2. Heartbeat không tự chứng minh liveness

Heartbeat có thể cho thấy một node phản hồi nhưng:
- Nó chưa persist log.
- Nó đang ở term cũ.
- Replica apply backlog lớn.
- Quorum membership khác.
- API path tới leader bị lỗi dù node-to-node khỏe.

Cần synthetic write/read probes trong môi trường/đường an toàn để đo **commit-to-ACK** và **ACK-to-read-visible**, không chỉ ping.

### 28.3. Đừng tạo metric cardinality vô hạn

Nếu có hàng triệu keys/shards/tenants, gắn toàn bộ IDs làm metric labels có thể làm hệ giám sát quá tải. Dùng:
- Per-group aggregate/cell-level metrics.
- Top-N hot groups.
- Sampled traces/logs chứa operationId.
- On-demand per-tenant/per-shard drilldown.
- Retention và bảo vệ thông tin nhạy cảm.

## 29. Kiểm thử consensus: safety và liveness cần hai tập tiêu chí

Một test chỉ kiểm tra API 200 **không chứng minh** consensus an toàn. Một test chỉ kiểm tra không có duplicate cũng **không chứng minh** hệ có thể tiến triển khi còn majority.

### 29.1. Test safety

Cần lịch sử:
- OperationId.
- Value/log index/term khi được công bố.
- Invoke và response times.
- Đường đọc/write mode.
- Kết quả committed/rejected/timeout/unknown.
- Client/session identity.
- Final state sau recovery.

Các bất biến:
- Không hai entry khác nhau cùng được xem committed ở cùng một index trong cùng lịch sử log hợp lệ.
- Entry đã committed không bị một leader mới hợp lệ thay bằng entry mâu thuẫn theo contract.
- Không hai booking cùng giữ một slot.
- Không double debit cùng operationId.
- Strong read không trả trạng thái trái linearizable history được hứa.

### 29.2. Test liveness/progress

Trong một kịch bản đủ voter và network ổn định sau một thời điểm:
- Leader có thể được bầu không?
- Commit index có tiếp tục tăng không?
- Requests có hoàn tất trong deadline mục tiêu không?
- Time to elect/recover bao lâu?
- Backlog/replay có đạt trạng thái ổn định không?
- Một shard hot có làm những shards khác kẹt không?

**Một test không tiến triển khi mạng bị chia 2–2–1 trên N=5 có thể là hành vi đúng**, không phải failure của safety.

### 29.3. Lịch thử mạng

| Kịch bản | Cách tạo trong môi trường test | Kết quả mong muốn |
| --- | --- | --- |
| 3/3 healthy | Không gây lỗi | Strong writes commit và read đúng |
| 2–1 partition, N=3 | Chặn peer traffic giữa nhóm 2 và node 1 | Majority có thể tiến triển; minority không tự commit |
| 3–2 partition, N=5 | Tách hai nhóm còn sống | Chỉ nhóm có majority có thể commit |
| 2–2–1 partition, N=5 | Chia ba nhóm | Không nhóm nào tự commit majority |
| Leader cũ trong minority | Phân vùng quanh leader | Không xác nhận write mới trái quorum |
| Repeated elections | Chèn delay/jitter/packet loss | Safety giữ; đo thời gian ổn định |
| Candidate log cũ | Đưa replica lạc hậu tham gia election | Không bầu trái luật up-to-date |
| Commit ACK lost | Chặn response sau majority commit | Client UNKNOWN, retry cùng ID không double effect |
| Follower durable lag | Chậm fsync một voter | Đo write p99, điều kiện ACK |
| Read từ old leader | Phân vùng và thử strong read | Không trả stale dưới nhãn linearizable |
| Voter down then learner join | Recovery/catch-up | Đúng membership và commit history |
| Reconfiguration mid-fault | Lỗi mạng trong joint transition | Không tạo hai config cùng commit conflict |
| Snapshot restore | Restart từ state cũ | Replay giữ committed history |
| Quorum across regions | Mất một region | Tính đúng reachability/placement |
| External stale writer | GC pause leader cũ rồi gọi storage khác | Fencing từ chối |
| Cross-shard transaction | Một shard thiếu quorum | Không business partial commit ngoài contract |

### 29.4. Không gán timeout thành failed write trong history checker

Nếu request timeout, có thể:
- Không xảy ra.
- Đã xảy ra.
- Vẫn đang in-flight lúc client ngừng chờ.

Trong kiểm tra linearizability, một incomplete/unknown operation cần được xử lý theo phương pháp kiểm tra lịch sử phù hợp; không tự đánh dấu nó là rollback để thu được kết quả đẹp.

### 29.5. Không thử phá quorum trên production tùy tiện

Fault injection (network filters, process kill, disk faults) chỉ thực hiện trong môi trường có thẩm quyền và có kế hoạch an toàn. Cần mô phỏng cả **đường client và node-to-node**, không chỉ ngắt kết nối từ máy kiểm thử đến một API endpoint.

## 30. Benchmark throughput và latency khi thay quorum placement

Một thí nghiệm giả định:

~~~~yaml
experiment: consensus-quorum-progress
topology:
  votingMembers: 5
  placements:
    - all_local
    - two_two_one_across_regions
  replicationGroups: 32
workload:
  writesPerSecond: 10000
  readsPerSecond: 30000
  keyDistribution: zipfian
  operations:
    - point_read
    - conditional_reserve
    - idempotent_order_create
    - linearizable_read
    - follower_eventual_read
faults:
  - healthy
  - one_voter_crash
  - three_two_network_partition
  - two_two_one_partition
  - leader_gc_pause
  - slow_log_fsync
  - lost_commit_ack
  - membership_change
  - region_failure
measure:
  - leader_term_and_elections
  - quorum_reachability_by_group
  - commit_index_progress
  - write_ack_p50_p95_p99
  - client_unknown_outcome_rate
  - read_barrier_p99
  - follower_apply_lag
  - operation_id_duplicates
  - invariant_violations
  - recovery_duration
~~~~

Đây là **spec mô phỏng**, không phải cấu hình chạy trực tiếp cho một sản phẩm NoSQL.

### 30.1. Báo cáo phải theo từng loại request

| Trạng thái giả định | Quorum | Strong write p99 | Follower read | Kết luận hợp lý |
| --- | --- | --- | --- | --- |
| 5/5 connected | Có | 45 ms | Có thể stale theo mode | Healthy baseline |
| 3/5 connected | Có | 95 ms | Có thể stale | Progress nhưng p99 xấu hơn |
| 2/5 isolated | Không | Timeout/reject | Có thể trả local old version nếu cho phép | Safety giữ, availability giảm |
| 2–2–1 | Không nhóm nào có | Không commit | Read tùy hợp đồng | Không được ép minority commit |
| Leader failover | Majority có | Tạm tăng | Tùy routing | Cần election/replay |
| ACK lost sau commit | Đã commit | Client thấy timeout | Read strong có thể kiểm tra | Cần idempotency |
| Slow voter trên quorum path | Có thể | Tăng mạnh | Có thể còn phục vụ | Bottleneck durability/network |

**Các số p99 là giả định**, không phải thực nghiệm. Phải báo riêng:
- Offered vs achieved QPS.
- Success rate vs timeout rate.
- Percentiles với cả request lỗi/chờ theo phương pháp SLO.
- Commit index/leadership stability.
- Safety/correctness invariants.
- P99 theo vùng và group.

### 30.2. Một quorum có thể còn nhưng không đạt business deadline

Nếu service deadline 150 ms còn consensus write p99 = 300 ms:
- Database vẫn có thể commit một số request sau client timeout.
- Tỷ lệ UNKNOWN tăng.
- Retry tạo tải thêm.
- User checkout completion giảm.

Đừng giải thích điều này chỉ bằng “cluster đủ quorum”. **Có điều kiện tiến trình ≠ đáp ứng latency SLO của từng thao tác.**

## 31. Runbook khi database báo “no quorum” hoặc leader election liên tục

### Bước 1 — Xác định consensus group bị ảnh hưởng

- Group/shard nào?
- Voting configuration hiện hành gồm ai?
- Có learner/witness không?
- Majority Q được tính từ bao nhiêu voter hợp lệ?
- Cấu hình có đang chuyển tiếp không?

### Bước 2 — Kiểm tra reachability thực

- Node sống hay đã crash?
- Những voter nào kết nối với nhau?
- Network partition, packet loss, asymmetric link?
- Client route tới leader/authority nào?
- Có một nhóm đủ Q trong cùng connected component không?

### Bước 3 — Xem term/log và durability

- Leader term/current leader là gì?
- Các election có liên tục thất bại không?
- Candidate có log đủ mới?
- Commit index và applied index tiến triển không?
- WAL/fsync/disk/errors có kẹt?
- Có uncommitted entries hoặc snapshots đang replay không?

### Bước 4 — Bảo vệ safety nghiệp vụ

- Không force minority commit.
- Không công bố order CONFIRMED nếu không có bằng chứng.
- Giữ operationId qua retry.
- Những timeout sau khi gửi write phải được xem là UNKNOWN khi chưa xác minh.
- Chặn stale leader/worker bằng fencing ở external storage.
- Không dùng eventual search/cache làm authority để bán hàng hoặc debit.

### Bước 5 — Khôi phục theo runbook của engine

- Sửa network/disk/placement gây thiếu quorum.
- Khôi phục voter hoặc node đúng cấu hình.
- Đợi log catch-up/leader election an toàn.
- Không sửa membership metadata thủ công ngoài quy trình.
- Nếu cần emergency recovery ngoài fault model, đánh giá rõ nguy cơ mất ACKed writes và tính đúng trước khi thực hiện.
- Giới hạn retry storm và background repair traffic.

### Bước 6 — Xác nhận

- Quorum và leader ổn định.
- Commit index tăng trên nhóm yêu cầu.
- Strong write/read đúng contract.
- Operation UNKNOWN đã reconcile.
- Không có duplicate order/slot.
- Replica/apply backlog giảm.
- p99/error budget và RTO đạt mục tiêu.
- Có postmortem về placement, capacity, monitoring và thử lỗi.

## 32. Những nhầm lẫn thường gặp

1. **“Quorum là một nửa số node.”** Majority là lớn hơn một nửa, \(Q=\lfloor N/2\rfloor+1\).
2. **“N=4 thì 2 node đủ ghi.”** Không cho majority: cần 3/4.
3. **“N=5 còn 3 node sống là chắc chắn write thành công.”** Ba node phải liên lạc, đủ điều kiện election/log/durability.
4. **“Node trả ping là voter hợp lệ.”** Không nếu là learner/non-voter hoặc term/config không phù hợp.
5. **“Hai quorum lớn nhưng thuộc hai cấu hình khác nhau chắc chắn giao nhau.”** Không nếu thiếu reconfiguration protocol.
6. **“Giao nhau là đủ tạo consensus.”** Còn cần ballot/term, acceptance, commit và persistence rules.
7. **“R+W>N nghĩa mọi query linearizable.”** Chưa đủ read/write protocol.
8. **“Cassandra QUORUM là cùng giao thức với Raft majority commit.”** Không mặc định.
9. **“Có replication factor ba tức ba voting nodes.”** Có thể khác topology/role.
10. **“Witness giúp tăng số bản dữ liệu.”** Witness có thể không lưu full data.
11. **“Mất quorum là data loss.”** Có thể chỉ mất khả năng commit mới.
12. **“Còn quorum là RPO=0 trước mọi thảm họa.”** Durability và failure domain riêng.
13. **“Minority có leader cũ thì vẫn được commit.”** Không nếu thiếu điều kiện protocol.
14. **“Leader flag còn true là quyền ghi còn hiệu lực.”** Có thể stale, cần fencing/term.
15. **“Có majority thì bầu leader lập tức.”** Network timing/split votes/log-up-to-date có thể cản.
16. **“Heartbeat chứng minh log durable.”** Chỉ là tín hiệu liên lạc, không phải WAL fsync.
17. **“Entry được follower nhận là đã committed.”** Received/append và committed khác nhau.
18. **“Đã committed thì mọi follower query ra ngay.”** Apply lag/read mode khác nhau.
19. **“Read từ node từng là leader luôn linearizable.”** Cần xác minh leadership/read barrier.
20. **“Timeout nghĩa rollback.”** Commit có thể hoàn tất nhưng ACK mất.
21. **“Retry +1 với ID mới an toàn vì consensus.”** Increment không idempotent.
22. **“Quorum của DB tự bao trùm payment provider.”** External side effect ngoài scope.
23. **“Thêm follower luôn tăng write throughput.”** Có thể tăng replication cost/RTT.
24. **“Thêm node lẻ hay chẵn đều tăng fault tolerance một mức.”** N=3 và N=4 đều chịu một voter failure trong majority model.
25. **“Một nhóm 2–2–1 chắc chắn có quorum vì cả năm node sống.”** Không nếu không có 3 liên lạc.
26. **“Quorum availability = HTTP availability.”** Deadline, routing, app dependencies khác.
27. **“Muốn AP chỉ cần đổi Q thành 1 khi partition.”** Có thể phá safety/history.
28. **“Membership change chỉ sửa config file.”** Cần protocol chuyển cấu hình an toàn.
29. **“Leader lease TTL đủ ngăn stale writer.”** Cần giả định clock/epoch/fencing.
30. **“Có three-way replication là không cần backup.”** Replica lan lỗi logic.
31. **“Mọi shard có cùng trạng thái quorum.”** Có thể shard 12 chết, shard 13 khỏe.
32. **“Chỉ test một node crash là đủ.”** Cần partition, ACK loss, stale leader, asymmetric links.
33. **“Không tiến triển trong partition là lỗi algorithm.”** Có thể là hành vi đúng để giữ safety.
34. **“Một read 200 trong minority chứng minh nó strong.”** Có thể là stale local read.
35. **“Quorum latency bằng RTT của node chậm nhất.”** Thường phụ thuộc tập node đủ điều kiện, không nhất thiết tất cả.
36. **“Muốn tiến triển luôn thì bỏ bớt safety checks.”** Có thể gây conflicting commits hoặc mất invariant.

## 33. Bài tập tình huống: đơn hàng NoSQL ba vùng

Một nền tảng booking dùng Java 21 và NoSQL, với giả định:
- Hệ có năm **voting members** A,B,C,D,E.
- Quorum majority = 3.
- Đặt node A,B tại VN; C,D tại EU; E tại US.
- Mỗi shard dữ liệu có consensus group được quản lý theo cơ chế phù hợp.
- Checkout yêu cầu không đặt trùng một slot và cùng operationId không tạo hai reservation.
- Search và dashboard có thể dùng read model eventual.
- SLA checkout p99 dưới 250 ms.
- Client retry khi timeout, gateway cũng có retry policy.
- Có thể xảy ra mất một region, split network và thay đổi membership.

### Phần A — Tính quorum và failure tolerance

1. Tính majority với N=3, 4, 5 và 7.
2. Tính số voter failure tối đa còn đủ majority theo mô hình đơn giản.
3. Nếu N=5 bị chia {A,B,C} và {D,E}, nhóm nào có thể commit?
4. Nếu chia {A,B}, {C,D} và {E}, có nhóm nào đủ quorum không?
5. Vì sao việc cả năm node **alive** không đủ kết luận progress?

**Gợi ý:** N=5 cần 3 voter; nhóm 3 có khả năng tiến triển nếu điều kiện protocol/tiến trình còn đúng; 2–2–1 thì không.

### Phần B — Leader cũ nằm ở minority

A là leader term 14. Mạng bị chia A+B và C+D+E. Nhóm ba bầu C term 15.

1. A có thể tiếp tục nhận TCP request không?
2. A có thể commit new log entry khi chỉ thấy B không?
3. C cần những gì ngoài “có ba node” để được bầu hợp lệ?
4. Nếu A đã gửi side effect tới external payment lúc pause, cần fencing/operationId thế nào?
5. Client ở VN thấy timeout nên trả trạng thái gì?

### Phần C — Giao quorum

Cho:
- Q1={A,B,C}
- Q2={C,D,E}

1. Xác định giao Q1∩Q2.
2. Vì sao giao nhau cần thiết?
3. Nếu Q3={A,B}, Q4={D,E}, tại sao không thể cho cả hai tự commit trong N=5?
4. Nếu cấu hình mới bỏ A,B,C và chỉ còn D,E,F, majority cũ/mới có tự giao nhau không?
5. Giải thích vai trò reconfiguration/joint consensus.

### Phần D — Đọc sau ghi

Leader ở EU majority-commits Order O-901. Client đọc follower tại VN nhưng node này chưa apply entry.

- Khi nào trả bản cũ là hợp lệ?
- Khi nào trả bản cũ vi phạm contract?
- ReadIndex/leader validation hoặc session minVersion giúp gì?
- Search index chưa thấy order có chứng minh write không commit không?

### Phần E — ACK bị mất

Operation OP-101 đã majority-committed, nhưng API client mất response rồi retry.

- Vì sao gọi reserve bằng OP-102 có thể trừ stock hai lần?
- Thiết kế ledger và unique guard ra sao?
- Vì sao GET eventual không thấy OP-101 chưa đủ kết luận rollback?
- Nếu request còn in-flight, một GET mạnh “chưa thấy” có đủ chứng minh operation sẽ không commit muộn không?
- Trạng thái COMMITTED/REJECTED/UNKNOWN xử lý thế nào?

### Phần F — Voter placement

So sánh:
1. N=5 đặt 3 VN, 1 EU, 1 US.
2. N=5 đặt 2 VN, 2 EU, 1 US.

Nếu mất toàn vùng VN, phương án nào vẫn có tối thiểu 3 voter ở các vùng còn lại? Giải thích vì sao **còn đủ số voter** chưa đủ nếu EU–US không liên lạc được.

### Phần G — Cấu hình chuyển tiếp

Cluster muốn thay A bằng F:
- Vai trò learner của F là gì?
- Khi nào có thể promote?
- Vì sao không nên thay nhiều voter cùng lúc ngoài quy trình?
- Nếu old/new quorums không thể cùng hình thành trong một giai đoạn chuyển tiếp, hệ nên làm gì?
- Vì sao không được cố sửa majority xuống 1 chỉ để tiếp tục ghi?

### Phần H — Tính latency

Với leader local append 4 ms và follower ACK times lần lượt 6, 45, 80, 120 ms:
- N=5, leader đã đạt điều kiện local; cần thêm hai follower.
- Thời gian follower thứ hai trả ACK khoảng bao nhiêu?
- Nếu follower nhanh nhất hỏng, ngưỡng thay đổi thế nào?
- Có thể cam kết p99 dưới 50 ms không nếu remote quorum RTT tăng bất thường?
- Vì sao average RTT không đủ dự đoán p99?

### Phần I — Đối chiếu sản phẩm

Lập bảng về:
- MongoDB majority write concern và read preference.
- Cassandra normal QUORUM và LWT.
- Redis WAIT và ý nghĩa replica ACK.
- DynamoDB strongly consistent item read/conditional writes.
- HBase WAL/replication.

Với mỗi sản phẩm, trả lời: **“Từ quorum của API này, có được suy ra Raft-style majority consensus commit cho toàn cụm không?”** Giải thích vì sao không được suy ngang giữa các giao thức.

### Phần J — Fault injection

Thiết kế một test plan gồm:
1. 5/5 healthy.
2. 3–2 partition.
3. 2–2–1 partition.
4. Leader cũ trong minority.
5. Candidate có log cũ xin phiếu.
6. Một voter disk fsync rất chậm.
7. Commit success nhưng client ACK mất.
8. Network hồi phục sau 30 giây.
9. Thay voting member khi có follower lag.
10. Cross-shard transaction có một shard thiếu quorum.
11. Stale leader ghi vào external storage.
12. Search index chậm 15 giây.

Mỗi test phải có:
- Fault model.
- Quorum/term/commit state.
- Expected safety invariant.
- Expected progress hoặc intentional unavailability.
- p99/error/UNKNOWN/recovery metrics.
- Điều kiện pass/fail rõ, không dùng HTTP 200 làm chỉ số duy nhất.

### Hướng giải

Một thiết kế đúng phải tính majority trên **voting configuration hiệu lực**, bảo toàn quorum intersection qua election/commit và reconfiguration, chỉ công bố **committed** khi protocol thật sự đạt điều kiện, ngăn stale leader bằng term/fencing, và dùng operationId để xử lý timeout UNKNOWN. Placement cần bảo vệ đúng failure domain, còn latency được đo theo quorum thực tế và đường request. Đường search/cache có thể eventual, nhưng booking/payment cần atomic/conditional authority đủ mạnh. Hệ có thể **không tiến triển khi thiếu quorum** mà vẫn đang giữ đúng safety; điều cần làm là phân loại outage và phục hồi điều kiện quorum an toàn, không giảm majority tùy tiện.

## 34. Checklist thiết kế quorum và quyền ghi

Trước khi chốt một mô hình đồng thuận cho NoSQL, hãy trả lời:

1. **Consensus group bảo vệ đối tượng/log/metadata nào?**
2. **Có bao nhiêu voting members theo configuration hiện hành?**
3. **Quorum formula là majority hay một quorum family riêng của protocol?**
4. **Member nào là learner, witness, observer hoặc data-bearing replica?**
5. **Những quorum quan trọng có giao nhau trong cùng cấu hình không?**
6. **Reconfiguration bảo toàn giao quorum cũ/mới bằng cách nào?**
7. **Leader election kiểm tra term và log up-to-date thế nào?**
8. **Khi leader cũ bị cô lập, điều gì ngăn nó commit?**
9. **Khi side effect ra ngoài group, có fencing token không?**
10. **Mốc ACK là appended, durable, accepted, committed hay applied?**
11. **Voter còn sống có thực sự liên lạc được với quorum khác không?**
12. **Mất một node/zone/region thì nhóm nào đủ quorum?**
13. **Có common-mode failure giữa đa số voter không?**
14. **Mất quorum thì API trả lỗi gì và hợp đồng nào vẫn được phục vụ?**
15. **Strong read xác minh leadership/commit bằng cơ chế nào?**
16. **Follower/secondary read có được phép stale không?**
17. **Nếu client mất ACK, có operationId và reconciliation không?**
18. **Business transaction có bao nhiêu shards/consensus groups?**
19. **Có rollback/compensation khi external payment lỗi không?**
20. **Leader election và commit p99 có đạt deadline trong giờ cao điểm?**
21. **Voter fsync/log apply/replication backlog được theo dõi chưa?**
22. **Thêm voter mới có learner/catch-up plan không?**
23. **Backup/restore có bảo vệ lỗi logic ngoài replication không?**
24. **Fault injection đã thử 3–2, 2–2–1 và old-leader isolation chưa?**
25. **Có checker kiểm tra lịch sử write/read và invariants không?**
26. **Có phân biệt missing quorum, overloaded quorum và UNKNOWN commit không?**
27. **Có biết sau failover những write đã ACK được bảo vệ trong fault model nào?**
28. **Có chiến lược routing khách tới phía còn quorum mà không phá quyền ghi không?**
29. **Có monitoring per-shard/group và không chỉ “node healthy” không?**
30. **Có runbook emergency recovery tránh force minority writes không?**

**Kết luận:** **Quorum đồng thuận không phải một phép đếm node khỏe độc lập với giao thức.** Majority và khả năng giao nhau của các quorum là cơ sở để bảo vệ những quyết định đã đạt được, nhưng safety còn phụ thuộc **term/ballot, log rules, durability, bầu cử và chuyển cấu hình**. Tiến trình có thể tiếp tục khi **đúng tập voter hợp lệ liên lạc được, có leader/proposer đủ điều kiện, giao thức và lưu trữ tiến triển dưới những giả định mạng ổn định cần thiết**; chỉ cần một điều kiện thiếu, hệ có thể phải chờ hoặc từ chối strong write để không phá lịch sử. Khi xây NoSQL phân tán, hãy tách **consensus quorum** khỏi **replica read/write quorum**, xác định **quyền ghi theo epoch**, xem xét **vị trí voter theo failure domain**, và xử lý **timeout/UNKNOWN bằng idempotency**. Đánh giá bằng **quorum reachability, commit index, election stability, read correctness, p99 và invariant nghiệp vụ**, chứ không chỉ dựa vào số node còn ping được.
