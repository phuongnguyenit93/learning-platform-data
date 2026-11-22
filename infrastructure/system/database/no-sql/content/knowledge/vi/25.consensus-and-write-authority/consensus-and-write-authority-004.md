# Tổng quan Raft/Paxos và phạm vi cần hiểu khi dùng hệ quản trị

## 1. Tại sao người sử dụng NoSQL cần biết Raft và Paxos?

Một hệ thống đặt vé có ba máy lưu trạng thái giữ ghế:

~~~text
Node A: ghế S101 chưa được đặt
Node B: ghế S101 chưa được đặt
Node C: ghế S101 chưa được đặt
~~~

Hai người cùng nhấn đặt ghế. Ngay lúc đó mạng giữa các node bị phân vùng:

~~~text
Client X -> Node A: giữ ghế S101 cho X
Client Y -> Node C: giữ ghế S101 cho Y

A <----> B       X       C
~~~

Nếu cả hai phía tự xác nhận thành công, hệ có thể bán một ghế cho hai người. Hệ thống cần một cách để **nhiều node đồng thuận về quyết định hợp lệ**, ngay cả khi node chậm, chết hoặc tin nhắn đến muộn.

Hai họ thuật toán quan trọng là **Raft** và **Paxos**. Chúng giúp giải quyết bài toán đồng thuận trong hệ phân tán, nhưng không phải phép màu biến mọi thao tác NoSQL thành transaction mạnh.

Trong công việc backend hoặc vận hành cơ sở dữ liệu, bạn thường không phải tự viết Raft/Paxos. Tuy nhiên, bạn cần hiểu các khái niệm đủ để trả lời:

- Vì sao một leader có thể tạm từ chối ghi khi cụm mất quorum?
- Vì sao ba replica không đồng nghĩa ba node đều được tự xác nhận một ghi?
- Khi client gặp timeout, có chắc thao tác không được commit?
- Vì sao sau election, node giữ dữ liệu cũ không được tùy tiện trở thành leader?
- Majority ACK bảo vệ điều gì và chưa bảo vệ điều gì?
- Khi nào đọc từ follower có thể stale?
- Tại sao Cassandra có LWT/Paxos trong khi thao tác ghi thông thường lại có ngữ nghĩa khác?
- Tại sao cần hiểu **quyền ghi**, **phiên bản lãnh đạo** và **fencing**, dù database đã quản lý replication?

Bài này thuộc chương **Đồng thuận và quyền ghi** của module **Database No SQL**. Mục tiêu là nắm **mental model của người sử dụng và vận hành** chứ không triển khai đầy đủ giao thức từ đầu.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **consensus**, **replication**, **quorum**, **leader election**, **transaction** và **distributed lock**.
2. Hiểu safety/liveness và vì sao đa số có giao nhau.
3. Theo dõi vòng đời một lệnh trong Raft: election, append log, commit, apply.
4. Nắm trực giác của Paxos: prepare/promise, accept/accepted, chosen, và lý do phải giữ giá trị đã được chấp nhận trước đó.
5. So sánh Raft, Paxos, Multi-Paxos và LWT ở mức ứng dụng.
6. Hiểu giới hạn khi xảy ra partition, crash, failover, clock skew và stale leader.
7. Chọn cách đọc/ghi, timeout/retry, idempotency và consistency theo yêu cầu nghiệp vụ.
8. Quan sát leader changes, commit latency, quorum health, apply lag và test các kịch bản lỗi.

## 2. Đồng thuận thực sự đang giải quyết bài toán gì?

### 2.1. Cùng một quyết định, nhiều bản sao

Giả sử có ba node cùng quản lý một **log lệnh**:

~~~text
Index 1: SET account=A
Index 2: RESERVE seat=S101 user=X
Index 3: CANCEL reservation=R11
~~~

Nếu các node cùng áp dụng **một chuỗi lệnh đã được chọn theo cùng thứ tự**, chúng có thể duy trì cùng trạng thái logic, với điều kiện:

- Trạng thái ban đầu tương ứng.
- Lệnh được áp dụng deterministically.
- Mỗi lệnh được áp dụng đúng quy tắc.
- Các entry đã commit không bị thay bằng entry xung đột.

Khái niệm này dẫn tới **replicated state machine**: hệ duy trì một log thống nhất, rồi mỗi replica áp dụng các entry đã commit vào state machine của mình.

### 2.2. Consensus không chỉ là gửi dữ liệu

Nếu A gửi UPDATE cho B và C theo cách bất đồng bộ, các node có thể có:

~~~text
A: version 12
B: version 11
C: version 10
~~~

Replication chỉ trả lời **dữ liệu được sao chép ra sao**. Consensus bổ sung cơ chế giúp các node có thẩm quyền **chọn cùng một giá trị/quyết định** theo những ràng buộc an toàn, bất kể một số node vắng mặt hoặc thông điệp đến trễ.

Không phải mọi cơ chế replication phải dùng Raft/Paxos. Nhiều NoSQL dùng leader–follower async, quorum reads/writes, anti-entropy hoặc mô hình khác.

### 2.3. Consensus không tự thay transaction ứng dụng

Đồng thuận về một lệnh:

~~~text
RESERVE seat S101 for X
~~~

không tự bảo vệ một transaction xuyên các hệ:

~~~text
Database reservation
Payment gateway
Email provider
Search index
~~~

Payment có thể commit nhưng email gửi thất bại, hoặc client timeout sau khi database đã commit. Cần thiết kế transaction boundary, outbox, idempotency và reconciliation phù hợp.

## 3. Safety và liveness: hai chiều cần đánh giá riêng

### 3.1. Safety

**Safety** là điều không được phép xảy ra.

Ví dụ:

- Hai leader xung đột không được cùng commit hai giá trị khác nhau cho cùng vị trí log đã quyết định.
- Một entry đã commit không được bị thay bởi entry xung đột sau khi leader mới được bầu.
- Không có hai người cùng được xác nhận sở hữu một ghế nếu business invariant yêu cầu ownership duy nhất.

Nói đơn giản: **không tạo kết quả sai**, ngay cả khi hệ bị lỗi.

### 3.2. Liveness

**Liveness** là khả năng tiếp tục tiến triển khi các điều kiện cần thiết được đáp ứng.

Ví dụ:

- Khi đa số các voting nodes còn liên lạc được và hệ đủ ổn định, leader có thể được bầu.
- Các lệnh mới có thể được commit trong điều kiện giao thức cho phép.

Liveness không tự hứa **một giới hạn latency cố định**. Mạng không ổn định, thay leader liên tục hoặc quá tải có thể khiến request timeout.

### 3.3. Một hệ có thể an toàn nhưng không ghi được

~~~text
Quorum không đạt.
Node từ chối mọi ghi cần consensus.
~~~

Trong tình huống này hệ có thể giữ safety nhưng mất write availability. Không nên tắt kiểm tra quorum chỉ để làm đồ thị HTTP success đẹp hơn.

### 3.4. Một hệ trả success nhanh nhưng sai là nguy hiểm hơn?

Nếu hai phía partition cùng tự cấp ghế S101, service có vẻ available, nhưng đã phá safety. Ngay cả khi sau đó dữ liệu eventual hội tụ về một owner, khách còn lại có thể đã được xác nhận và thanh toán.

### 3.5. Safety của giao thức khác safety nghiệp vụ

Raft có thể bảo đảm các replica nhất quán trên một log, nhưng nếu lệnh nghiệp vụ là:

~~~text
SET stock = -5
~~~

và state machine cho phép, mọi replica có thể nhất trí về **giá trị sai đối với nghiệp vụ**. Business rules vẫn phải được kiểm tra trong thao tác/transaction phù hợp.

## 4. Các khái niệm không được đánh đồng

| Khái niệm | Vai trò | Không tự bảo đảm |
|---|---|---|
| Replication | Sao chép dữ liệu tới nhiều node | Một thứ tự quyết định duy nhất, linearizability |
| Quorum | Một tập đủ số phiếu/ACK theo giao thức | Toàn bộ transaction luôn serializable |
| Consensus | Chọn cùng quyết định theo quy tắc an toàn | Mọi API của ứng dụng đều strong |
| Leader election | Chọn node tạm có quyền điều phối | Leader còn hợp lệ mãi mãi |
| Distributed log | Chuỗi lệnh có index/order | Mọi consumer ngoài log xử lý đúng một lần |
| Linearizability | Thao tác trông như xảy ra nguyên tử theo thứ tự tôn trọng thời gian thực | Giao dịch nhiều khóa luôn serializable |
| Serializability | Transaction có thể sắp thành một thứ tự tuần tự tương đương | Tự tôn trọng thứ tự thời gian thực |
| Conditional write | Chỉ ghi nếu điều kiện đúng trong phạm vi operation | Global uniqueness xuyên các datastore |
| Distributed lock | Phối hợp quyền thực thi | Ngăn worker cũ ghi nếu resource không fencing |
| Idempotency | Retry không tạo thêm logical effect | Khả năng commit của cụm dưới partition |

Không suy một bảo đảm từ tên công nghệ. Hãy xem chính xác **đối tượng, operation, consistency level, phạm vi replica và đường đọc**.

## 5. Quorum và lý do các đa số có giao nhau

### 5.1. Ba voting nodes

Với cụm ba thành viên bỏ phiếu:

~~~text
Nodes: A, B, C
Majority: 2 trong 3
~~~

Các tập majority:

~~~text
{A,B}
{A,C}
{B,C}
~~~

Bất kỳ hai tập nào cũng có ít nhất một thành viên chung.

### 5.2. Năm voting nodes

Với năm thành viên:

\[
\text{majority}=\left\lfloor\frac{5}{2}\right\rfloor+1=3.
\]

Nếu mạng chia thành nhóm 3 và nhóm 2, **nhóm 3 có thể đạt majority** nếu liên lạc và các điều kiện giao thức khác được đáp ứng. Nhóm 2 không có đủ phiếu để tự bầu leader hợp lệ trong một cấu hình majority thông thường.

### 5.3. Tại sao giao nhau quan trọng?

Giả sử một quyết định được chấp nhận bởi majority X. Một quyết định khác cho cùng vị trí cũng phải đi qua majority Y. Vì X và Y có ít nhất một node chung, giao thức có cơ hội dùng thông tin đã được lưu/nhìn thấy của node đó để **ngăn hai kết quả xung đột cùng được chọn**.

Tuy nhiên, **giao nhau thôi chưa đủ**. Chính các quy tắc về term, log, ballot, accepted value và durability mới làm lập luận safety hoàn chỉnh.

### 5.4. Majority khác số bản sao dữ liệu

Một hệ có thể có:

- Voting members điều phối metadata.
- Learners/observers không bỏ phiếu.
- Data replicas phục vụ read.
- Shards với replication groups riêng.

Đừng tính majority của cả cluster 50 machines nếu một quyết định chỉ thuộc **voting configuration của một replication group có 3 thành viên**.

### 5.5. Thêm voter có luôn tăng availability?

Không nhất thiết:

~~~text
3 voters -> majority 2, chịu lỗi 1 voter.
4 voters -> majority 3, vẫn chịu lỗi 1 voter.
5 voters -> majority 3, chịu lỗi 2 voters.
~~~

Thêm thành viên có thể tăng network/coordination cost, và một số topology lẻ cân bằng hơn khi chịu lỗi. Cần xem fault domains và cấu hình thực tế.

### 5.6. Tỷ lệ quorum không áp dụng tùy tiện

Với Raft hoặc classic Paxos, majority giao nhau là nền tảng phổ biến. Một số thuật toán/quorum configurations mở rộng có quy tắc riêng. Với Cassandra ordinary read/write quorum, công thức R+W>N cũng không đủ để tuyên bố toàn bộ hoạt động linearizable trong mọi topology.

## 6. Replicated state machine: từ log đến kết quả API

Một kiến trúc Raft điển hình:

~~~mermaid
flowchart TD
    C["Client command"] --> L["Leader"]
    L --> F1["Follower A"]
    L --> F2["Follower B"]
    L --> F3["Follower C"]
    F1 --> Q["Quorum confirmation"]
    F2 --> Q
    F3 --> Q
    Q --> M["Advance commit index"]
    M --> S["Apply committed log entries"]
    S --> R["State machine / response"]
~~~

Hình đơn giản hóa: leader cũng tham gia quorum và từng follower có trạng thái commit/apply riêng. Một implementation có thể trả response theo quy tắc commit và apply của operation cụ thể.

### 6.1. Log entry

Một entry có thể được biểu diễn:

~~~text
Log index = 42
Term = 7
Command = RESERVE(S101, user=X)
~~~

**Index** là vị trí trong log. **Term** phân biệt các epoch lãnh đạo. Hai khái niệm có chức năng khác nhau.

### 6.2. Commit khác apply

**Committed:** Entry được xác nhận theo quy tắc consensus; từ đó nó thuộc phần log đã được chọn và không được thay bằng nội dung xung đột.

**Applied:** State machine local đã thực thi command, làm dữ liệu đọc được thay đổi.

Một follower có thể đã lưu entry nhưng chưa biết entry đã committed; hoặc biết commit index nhưng state machine apply chậm hơn.

### 6.3. Đừng đọc follower như đọc leader một cách mặc định

Follower có thể:

- Thiếu entry mới.
- Đã append nhưng chưa apply.
- Chậm trong việc nhận commit index.

Do đó read từ follower không tự linearizable. Một hệ có thể cung cấp follower read với **read-index, lease, wait-for-apply** hoặc protocol khác; phải xem hợp đồng cụ thể của engine.

## 7. Raft là gì và vì sao thường dễ hình dung?

**Raft** là thuật toán đồng thuận hướng tới việc tổ chức bài toán thành các thành phần tương đối dễ giải thích:

1. **Leader election**: chọn leader qua term và votes.
2. **Log replication**: leader đề xuất một chuỗi entries cho followers.
3. **Safety**: bảo đảm các entry đã commit không bị thay bởi lịch sử xung đột, bao gồm quy tắc chọn leader phù hợp.
4. **Membership changes**: thay tập voting members mà vẫn giữ tính an toàn qua giao thức reconfiguration.

Raft thường xuất hiện trong các hệ điều phối metadata, distributed key-value stores và thành phần control plane. Không phải mọi NoSQL đều dùng Raft cho mọi dữ liệu.

### 7.1. Ba vai trò chính

~~~text
Follower  -> nhận heartbeat/log từ leader, phản hồi RPC.
Candidate -> xin votes trong một term để trở thành leader.
Leader    -> nhận proposals và điều phối log replication.
~~~

Trong một term, mục tiêu của giao thức là có tối đa một leader hợp lệ được bầu theo quy tắc majority. Dù network partition có thể làm một node cũ **nghĩ mình vẫn là leader**, nó không còn được commit thêm các entries mới nếu không có quorum hợp lệ.

### 7.2. Term

Term là **số epoch tăng dần** để phân biệt các vòng lãnh đạo:

~~~text
Term 5: A là leader.
Term 6: B được bầu.
Term 7: C được bầu.
~~~

Nếu một node nhìn thấy thông tin có term cao hơn term hiện tại, nó phải cập nhật trạng thái/nhường quyền theo quy tắc Raft.

**Term không phải timestamp vật lý**; nó là logical epoch.

### 7.3. Randomized election timeout

Followers chờ heartbeat. Nếu quá thời hạn bầu cử, một follower có thể trở thành candidate, tăng term và gửi RequestVote.

Thời hạn ngẫu nhiên giúp giảm khả năng nhiều candidates bắt đầu cùng lúc. Nó không bảo đảm không bao giờ split votes hay election storms.

### 7.4. Heartbeat

Leader gửi AppendEntries rỗng hoặc tương đương để báo đang hoạt động và duy trì lãnh đạo theo protocol.

Heartbeat timeout không chứng minh node đã chết; mạng có thể chậm, overloaded hoặc partition.

## 8. Raft leader election: một lần bầu cử điển hình

Giả sử ba voters A, B, C ban đầu:

~~~text
Term = 8
Leader = A
Followers = B, C
~~~

A bị mất kết nối. B không còn nhận heartbeat và hết election timeout:

~~~text
t1  B chuyển thành candidate.
t2  B tăng term từ 8 lên 9.
t3  B tự bỏ phiếu cho mình.
t4  B gửi RequestVote(term=9, lastLogIndex, lastLogTerm) tới A và C.
t5  C kiểm tra điều kiện và bỏ phiếu cho B.
t6  B có 2/3 phiếu -> trở thành leader của term 9.
t7  B gửi AppendEntries/heartbeats cho followers.
~~~

### 8.1. Mỗi voter bỏ tối đa một phiếu trong một term

Một voter không được cấp phiếu tùy tiện cho hai candidates trong cùng term. Các lựa chọn vote và term cần có tính bền vững theo yêu cầu giao thức để crash/restart không làm nó bỏ phiếu mâu thuẫn.

Nếu hai candidates cùng tranh term 9, có thể xảy ra split vote và phải tổ chức vòng bầu cử term tiếp theo.

### 8.2. Không phải candidate nào cũng có thể thắng

RequestVote có thông tin log cuối cùng:

~~~text
candidateLastLogTerm
candidateLastLogIndex
~~~

Voter chỉ cấp phiếu khi candidate đáp ứng điều kiện **log ít nhất mới bằng log của voter** theo thứ tự so sánh của Raft:

1. So lastLogTerm trước.
2. Nếu term bằng nhau, so lastLogIndex.

Đây là một điều kiện quan trọng để tránh bầu leader thiếu entries đã committed.

### 8.3. Ví dụ log mới hay cũ

~~~text
Node A lastLog = (term=7, index=20)
Node B lastLog = (term=8, index=18)
~~~

Log của B được xem là mới hơn theo quy tắc election vì lastLogTerm=8 lớn hơn 7, dù index=18 thấp hơn 20.

**Không chỉ so số entry**. Từ góc nhìn người vận hành, một replica chứa nhiều record/log entries hơn chưa chắc có lịch sử hợp lệ hơn để làm leader.

### 8.4. Candidate cần bao nhiêu phiếu?

Với 5 voters, cần majority 3/5. Nếu candidate có 2 votes nhưng một node đã chết và hai node khác không liên lạc, nó không thể tự tuyên bố leader hợp lệ chỉ vì đang sống.

### 8.5. Cựu leader nhận term mới

A phục hồi và nhận RPC mang term=9. Nếu A còn cho mình là leader term=8, theo protocol nó cần cập nhật term và trở về follower.

Nếu một hệ có external side effects, resource đích còn cần bảo vệ trước **worker cũ chưa dừng** bằng epoch/fencing hoặc cơ chế thẩm quyền phù hợp.

## 9. Raft log replication: leader đề xuất và followers kiểm tra

Giả sử B là leader term 9. Client gửi:

~~~text
RESERVE seat=S101 for user=X
~~~

B append một entry:

~~~text
index=21
term=9
command=RESERVE(S101,X)
~~~

Sau đó B dùng AppendEntries để đồng bộ những phần log với followers.

### 9.1. PrevLogIndex và PrevLogTerm

AppendEntries chứa thông tin liên kết với log trước đó, thường gồm:

~~~text
term
leaderId
prevLogIndex
prevLogTerm
entries
leaderCommit
~~~

Follower kiểm tra tiền tố log tương ứng tại prevLogIndex có cùng term không. Nếu không, nó từ chối append ở vị trí đó; leader tìm điểm khớp để đồng bộ log.

### 9.2. Log matching

Một thuộc tính quan trọng của Raft: nếu hai logs có cùng index và term tại một entry, thì tiền tố entries trước vị trí đó phải tương ứng theo quy tắc giao thức.

Điều này giúp tiến tới một lịch sử chung, thay vì chắp vá entries chỉ theo thời điểm nhận tin.

### 9.3. Entry chưa commit có thể bị thay

Ví dụ:

~~~text
Old leader A append index 21, term 8, command=RESERVE(X)
nhưng chưa commit vì thiếu quorum.

New leader B có log hợp lệ khác, term 9.
~~~

Trong quá trình đồng bộ, một **uncommitted entry** ở follower có thể bị loại hoặc ghi đè bởi log của leader hợp lệ. Không nên trả lời client rằng một entry chắc chắn bền vững chỉ vì nó đã tồn tại trên một replica.

### 9.4. Committed entry phải được bảo vệ

Raft dùng majority replication, quy tắc leader election và các điều kiện commit để đảm bảo một entry đã commit không thể bị ghi đè bởi entry mâu thuẫn ở cùng index trong một lịch sử hợp lệ.

Đây là ý nghĩa thực sự của việc **node có quyền ghi phải dựa trên quorum**, không chỉ dựa trên một biến boolean isLeader cục bộ.

## 10. Điều kiện commit trong Raft

### 10.1. Tình huống 3 voters

~~~text
Leader B term=9, entry index=21.

B: entry 21 persisted
C: entry 21 persisted, ACK
A: offline
~~~

Hai trong ba members có entry, và nếu đáp ứng các điều kiện commit của Raft, leader có thể advance commitIndex.

### 10.2. Quy tắc quan trọng về term hiện tại

Trong Raft chuẩn, leader không đánh dấu commit một entry từ **term cũ** chỉ bằng cách đếm replicated replicas của entry ấy. Leader đánh dấu commit entry thuộc **term hiện tại** khi entry đã được lưu trên majority; khi đó các entries trước nó trong log được commit theo hệ quả.

Ví dụ:

~~~text
Leader term=9.

Index 20 term=8 (entry cũ)
Index 21 term=9 (entry mới)
~~~

Khi index 21 được commit đúng quy tắc, các entries trước đó trong tiền tố của log cũng được xem là committed.

Chi tiết này quan trọng vì có những lịch sử lỗi/election trong đó một entry term cũ tồn tại trên majority nhưng chưa đủ để tự kết luận đã commit an toàn.

### 10.3. CommitIndex và LastApplied

Một node có thể báo:

~~~text
commitIndex = 21
lastApplied = 19
~~~

Tức node biết tới entry 21 đã committed nhưng state machine local mới áp dụng tới index 19.

Nếu một đường đọc truy vấn state machine mà không bảo đảm đã apply đủ mốc cần thiết, nó có thể trả dữ liệu cũ ngay cả khi log commit đã tiến.

### 10.4. Lệnh deterministically applied

Một state machine không nên tự chọn giá trị ngẫu nhiên, đọc đồng hồ local không kiểm soát hay gọi external API có side effect khác nhau giữa replicas khi apply cùng log entry.

Nếu cần timestamp, ID hoặc input bất định, giao thức ứng dụng thường phải đưa **giá trị đã chọn** vào command log, hoặc xử lý bên ngoài state machine theo mô hình phù hợp.

### 10.5. ACK cho client

Một implementation có thể trả response sau khi entry đã được commit và áp dụng theo semantics của operation; hoặc có cách biểu diễn asynchronous commit riêng.

**Đừng suy từ chữ Raft rằng mọi API ACK ở cùng thời điểm.** Phải xem contract của database: durable, committed, applied, visible, external side effect hay chỉ accepted.

## 11. Raft khi leader mất kết nối nhưng chưa biết mình đã mất quyền

Giả sử:

~~~text
Term 10: A là leader.
Network partition:
   A | B,C
~~~

A còn phục vụ client gần A, nhưng B và C bầu B làm leader term 11.

### 11.1. A có thể vẫn nghĩ mình là leader

Do mạng lỗi, A chưa nhận được RPC term 11. Biến trạng thái trong tiến trình A vẫn là leader term 10. Tuy nhiên A không có majority để commit entry mới theo Raft.

Điều này khác với bảo đảm “không bao giờ có hai node tự cho rằng mình là leader”. Có thể có **hai nhận thức cục bộ**, nhưng chỉ một phía đạt quyền commit theo quorum hợp lệ.

### 11.2. Đường ghi phải chặn commit sai

A có thể append uncommitted entries trong log local trong khi thiếu quorum, tùy implementation và chính sách xử lý request. Nó không được báo committed như một quyết định consensus hợp lệ.

Khi mạng nối lại, A thấy term 11, step down và đồng bộ log; uncommitted entries có thể bị ghi đè.

### 11.3. Đường đọc không được tin isLeader một mình

Nếu A xử lý linearizable GET bằng việc đọc state machine local mà không kiểm tra quyền leadership còn hợp lệ, nó có thể trả dữ liệu cũ sau khi B đã commit mutations mới.

Giải pháp đọc tuyến tính thường dùng những giao thức như **ReadIndex/quorum confirmation** hoặc **leader lease** với các giả định đồng hồ và thời hạn được xác định.

### 11.4. Leader lease cần hiểu đồng hồ

Một leader lease dựa vào thời gian không có nghĩa đồng hồ trên mọi máy luôn đồng bộ hoàn hảo. Implementation phải bảo vệ trước clock drift, pause, suspend, election timeout và các điều kiện an toàn của protocol.

Không tự thêm kiểm tra “leaseExpiresAt > now” bằng đồng hồ ứng dụng rồi coi như linearizable.

## 12. Raft read paths: vì sao ghi mạnh không đồng nghĩa mọi đọc mạnh?

### 12.1. Đọc trực tiếp leader

Nếu request được chuyển đến leader, vẫn cần một cách xác minh leader chưa bị thay bởi term mới hoặc request được thực hiện theo protocol linearizable. Chỉ vì gọi node có vai trò leader cục bộ chưa đủ trong trường hợp partition.

### 12.2. ReadIndex

Một cách phổ biến là leader xác nhận thông qua quorum rằng nó vẫn có thẩm quyền, nhận một **read index** phù hợp, rồi đợi state machine đã apply tới mốc đó trước khi trả kết quả đọc.

ReadIndex là khái niệm trong các triển khai Raft hỗ trợ; chi tiết và tối ưu hóa khác nhau tùy hệ.

### 12.3. Follower read

Follower có thể phục vụ:

- **Stale read** theo policy eventual.
- **Bounded-staleness** theo giới hạn phiên bản/độ trễ được định nghĩa.
- **Linearizable read** nếu tham gia protocol phù hợp và đợi apply đủ trạng thái.

Không có bảo đảm nào trong ba loại được suy chỉ từ chữ “follower”.

### 12.4. Session consistency

Nếu người dùng vừa PUT hồ sơ rồi GET từ follower, có thể thấy bản cũ dù PUT đã được commit.

Một ứng dụng cần read-your-writes nên dùng đường đọc có minimum commit revision/session token hoặc API strong read được database cung cấp.

### 12.5. Linearizable single-key read không tự tạo snapshot xuyên nhiều hệ

Hai API đọc mạnh:

~~~text
GET Order
GET Payment
~~~

nếu gọi vào hai hệ độc lập, không tự hình thành một snapshot nguyên tử xuyên cả hai. Cần transactional/snapshot design tương ứng nếu nghiệp vụ đòi hai phần nhất quán ở cùng thời điểm.

## 13. Raft log compaction và snapshot

### 13.1. Vì sao không thể giữ log vô hạn?

Một cụm chạy nhiều năm có thể có hàng tỷ entries. Nếu lưu mọi entry từ đầu, việc restart/replay sẽ rất tốn thời gian.

### 13.2. Snapshot của state machine

Một snapshot có thể mô tả trạng thái đã apply tới mốc nhất định:

~~~text
Snapshot:
  lastIncludedIndex = 10,000
  lastIncludedTerm = 92
  state = ...
~~~

Sau đó log trước mốc snapshot có thể được compact theo protocol.

### 13.3. Follower tụt quá xa

Nếu follower chỉ có log từ index 1.000 nhưng leader đã compact mọi entry trước 10.000, follower không thể đơn giản yêu cầu lại các entries đã bị loại.

Một cơ chế như **InstallSnapshot** giúp đưa follower tới trạng thái phù hợp rồi tiếp tục đồng bộ log còn lại.

### 13.4. Snapshot phải tương ứng với metadata

Không thể dùng một snapshot application tùy ý mà thiếu thông tin log position/term cần thiết để nối lại lịch sử an toàn.

### 13.5. Kỹ năng vận hành

Khi một node vừa phục hồi sau downtime dài:

- Đừng chỉ nhìn process đã Running.
- Kiểm tra snapshot transfer, catch-up lag và trạng thái voter/learner.
- Theo dõi network/disk I/O trong lúc tải snapshot.
- Không đưa node chưa bắt kịp làm điểm đọc mạnh nếu protocol không bảo đảm.

## 14. Thay đổi thành viên voting group không phải chỉ sửa một danh sách

### 14.1. Membership quyết định ai được bỏ phiếu

Một group có:

~~~text
Old voters: A, B, C
~~~

Muốn thay C bằng D:

~~~text
New voters: A, B, D
~~~

Nếu các nodes cập nhật configuration không đồng thời, có nguy cơ hai tập quyết định quorum khác nhau và tưởng cùng có quyền.

### 14.2. Joint consensus

Raft mô tả kỹ thuật **joint consensus**: chuyển qua configuration trung gian trong đó quorum cần tuân theo cả cấu hình cũ và mới theo protocol, trước khi chuyển hẳn.

~~~text
Old configuration
       |
       v
Joint old + new
       |
       v
New configuration
~~~

Một số implementations dùng kỹ thuật membership change khác hoặc giới hạn một thay đổi thành viên mỗi lần. Không tự áp đặt một lệnh quản trị cụ thể của Raft lên mọi sản phẩm.

### 14.3. Không xóa nhiều voters cùng lúc

Nếu cụm 5 voters cần majority 3 mà operator tắt 3 voters trong quá trình thay node, remaining 2 không thể đạt quorum. Quy trình rolling replacement và health checks là thiết yếu.

### 14.4. Learner/non-voting member

Một learner có thể theo log để catch up nhưng chưa bỏ phiếu. Vai trò này giúp thêm node mới trước khi chuyển voting configuration, tùy implementation.

### 14.5. Mở rộng 3 lên 5 không phải giải pháp chung cho mọi sự cố

Tăng voters giúp chịu lỗi nhiều node hơn trong cấu hình thích hợp, nhưng cũng tăng:

- Message/replication overhead.
- Chi phí khi mạng cross-Region.
- Vấn đề capacity khi snapshot/catch-up.
- Độ phức tạp membership.

Với sharded consensus, mỗi replication group có quorum riêng; thêm tổng số nodes không có nghĩa mọi group được hưởng thêm phiếu.

## 15. Raft: một dòng thời gian hoàn chỉnh

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Leader A
    participant B as Follower B
    participant D as Follower C
    C->>A: Propose RESERVE(S101,X)
    A->>A: Append index=42, term=7
    A->>B: AppendEntries(index=42)
    A->>D: AppendEntries(index=42)
    B-->>A: ACK persisted
    Note over A,B: Majority A+B
    A->>A: Commit index=42
    A->>A: Apply command
    A-->>C: Result according to API contract
    A->>B: LeaderCommit=42
    A->>D: LeaderCommit=42
~~~

Sơ đồ không mô tả mọi chi tiết concurrency, failure, WAL và tối ưu hóa. Nó cho thấy logic căn bản: **leader đề xuất, quorum lưu, entry được commit, rồi state machine áp dụng và client quan sát theo hợp đồng**.

### 15.1. Nếu leader chết trước khi đủ majority?

Entry chưa được commit. Leader mới sẽ đồng bộ theo log hợp lệ và entry đó có thể tồn tại hoặc biến mất.

### 15.2. Nếu leader chết sau commit nhưng trước khi client thấy response?

Operation có thể đã commit. Client không thể suy “timeout = thất bại”.

### 15.3. Nếu client retry?

Retry cùng operationId cần được dedup hoặc thiết kế idempotent. Consensus về log không tự biến hai proposals giống nhau thành một business action.

### 15.4. Nếu follower C có lag?

A+B có thể commit theo quorum trong một cụm 3 voters, còn C catch up sau. Đọc C trước khi áp dụng đủ entry có thể stale nếu hệ cho phép đường đọc đó.

### 15.5. Nếu mạng chia thành A một phía và B+C một phía?

Phía A không thể tiếp tục commit entries mới nếu mất majority. B+C có thể bầu leader hợp lệ theo protocol sau election. Đường ghi ở A phải từ chối/chờ hoặc trả lỗi sau deadline, không tự cho phép ghi local đã commit.

## 16. Paxos: trực giác về chọn một giá trị an toàn

**Paxos** là một họ thuật toán đồng thuận. Bản cơ bản, thường gọi **Single-Decree Paxos**, tập trung vào việc nhiều thành viên đồng thuận về **một giá trị**.

Giả sử hệ cần chọn owner cho một reservation:

~~~text
Key: SEAT#S101
Candidate values:
  owner=X
  owner=Y
~~~

Mục tiêu của consensus là không chọn hai owner xung đột cho cùng một quyết định, dù có proposer cạnh tranh và message đến không theo thứ tự.

### 16.1. Ba vai trò logic

- **Proposer:** Đề xuất một giá trị.
- **Acceptor:** Ghi nhận lời hứa và giá trị được chấp nhận theo ballot.
- **Learner:** Học kết quả đã được chọn.

Các vai trò có thể chạy chung trên một process/node. Không mặc định “proposer là application”, “acceptor là một replica riêng” trong mọi implementation.

### 16.2. Ballot/proposal number

Paxos dùng một thứ tự ballot đủ phân biệt:

~~~text
Ballot 11
Ballot 12
Ballot 13
~~~

Một ballot cao hơn cho phép một proposer tìm cách tiếp tục sau khi proposer trước bị chậm hoặc chết, nhưng không được tùy tiện thay kết quả **đã được chọn**.

Trong thực tế, ballot có thể gồm epoch/counter/node identity để tránh hai proposers tạo số không phân biệt.

### 16.3. Một giá trị được chosen khi nào?

Trong classic majority Paxos, một giá trị được coi là **chosen** khi nó đã được accept bởi majority acceptors theo quy tắc tương ứng.

Một acceptor đơn lẻ nói “accepted X” chưa chứng minh X được chọn.

### 16.4. Paxos có thể không có leader cố định ở mức bản cơ bản

Single-Decree Paxos cho phép nhiều proposers cạnh tranh. Nhưng các hệ production thường dùng leader/primary hoặc tối ưu hóa khác để tránh tranh liên tục và mở rộng sang nhiều log entries.

Không kết luận “Paxos không có leader, còn Raft có” như một phân biệt tuyệt đối giữa toàn bộ họ Paxos và Raft.

## 17. Paxos Phase 1: Prepare và Promise

Giả sử có ba acceptors A, B, C.

Proposer P muốn chọn:

~~~text
Value = RESERVE(S101,X)
Ballot = 12
~~~

### 17.1. Prepare

P gửi:

~~~text
PREPARE(ballot=12) tới A, B, C
~~~

### 17.2. Promise

Nếu acceptor chưa hứa cho ballot lớn hơn, nó có thể trả promise:

~~~text
PROMISE(
    promisedBallot=12,
    previouslyAcceptedBallot=...,
    previouslyAcceptedValue=...
)
~~~

Acceptor hứa không chấp nhận các proposal có ballot nhỏ hơn ballot đã hứa, theo quy tắc giao thức.

### 17.3. Vì sao phản hồi phải mang giá trị đã accept trước?

Giả sử trước đó một proposer khác đã khiến nhiều acceptors accept giá trị Y. Một proposer mới với ballot cao hơn không được chỉ nói “tôi có số mới nhất, tôi chọn X”.

Nó phải xem lịch sử accepted được majority báo về. Trong classic Paxos, nếu có những accepted proposals, proposer chọn giá trị gắn với **accepted ballot cao nhất** trong responses hợp lệ từ phase 1.

Quy tắc này bảo vệ một giá trị đã được chosen khỏi bị proposal mới thay thế.

### 17.4. Chưa có accepted value nào

Nếu phase 1 majority không báo accepted value trước đó, proposer có thể đề xuất giá trị mới của mình theo protocol.

### 17.5. Một majority promise không có nghĩa giá trị đã chosen

Phase 1 chỉ chuẩn bị một ballot. Nó chưa phải quyết định cuối cho business operation.

## 18. Paxos Phase 2: Accept và Accepted

Sau khi P nhận đủ promises và xác định giá trị được phép đề xuất:

~~~text
ACCEPT(ballot=12, value=RESERVE(S101,X))
~~~

được gửi tới acceptors.

### 18.1. Acceptor xử lý

Acceptor có thể accept nếu proposal không vi phạm lời hứa cho ballot cao hơn. Nó ghi trạng thái accepted theo yêu cầu về durability.

~~~text
ACCEPTED(ballot=12, value=RESERVE(S101,X))
~~~

### 18.2. Majority accepted

Nếu A và B accept proposal hợp lệ trong cụm 3 acceptors:

~~~text
A: accepted X at ballot 12
B: accepted X at ballot 12
C: chưa phản hồi
~~~

giá trị X đã được chosen theo classic majority Paxos.

### 18.3. Một acceptor crash sau đó

Nếu A chết sau khi majority đã accept, một proposal tương lai vẫn phải theo rules để không chọn giá trị mâu thuẫn. Lập luận safety dựa vào quorum intersection và việc giữ accepted state/ballot phù hợp qua crash/recovery.

### 18.4. Proposer bị preempt

Nếu acceptor đã promise ballot 13, proposal ballot 12 có thể bị từ chối:

~~~text
NACK / REJECT (higher promised ballot)
~~~

Proposer cần thử lại bằng một ballot phù hợp hoặc nhường cho proposer khác. Không thể ép acceptor chấp nhận ballot cũ chỉ vì client timeout.

### 18.5. Promise có thể ngăn tiến triển tạm thời

Nhiều proposers liên tục nâng ballot có thể làm nhau bị preempt. Paxos bảo vệ safety nhưng liveness thường cần leader election, backoff hoặc cơ chế ổn định proposer.

## 19. Minh họa một vòng Paxos đầy đủ

~~~mermaid
sequenceDiagram
    participant P as Proposer P
    participant A as Acceptor A
    participant B as Acceptor B
    participant C as Acceptor C
    P->>A: Prepare ballot=12
    P->>B: Prepare ballot=12
    P->>C: Prepare ballot=12
    A-->>P: Promise + accepted history
    B-->>P: Promise + accepted history
    Note over P: Majority promises A+B
    P->>A: Accept ballot=12, value=X
    P->>B: Accept ballot=12, value=X
    P->>C: Accept ballot=12, value=X
    A-->>P: Accepted X
    B-->>P: Accepted X
    Note over P: X chosen by majority
~~~

Sơ đồ chỉ mô tả một vòng thành công, không bao quát tất cả retries, concurrent ballots, learn notifications, storage crashes hoặc các biến thể Paxos.

### 19.1. Nếu chỉ A accept?

X chưa được chosen. Một proposer mới có thể tiếp tục protocol và phải xét accepted state mà majority phản hồi. Nó không được tự suy A đã thắng.

### 19.2. Nếu A+B đã accept X, P chết?

X đã được chosen, dù proposer P chưa thông báo kết quả cho application. Một proposer mới có thể học/hoàn tất kết quả theo giao thức, không được chọn Y mâu thuẫn.

### 19.3. Nếu P nhận timeout trước majority?

Client thấy unknown outcome. Không thể suy quyết định chưa chosen vì replies có thể bị mất sau khi acceptors đã lưu.

### 19.4. Nếu proposer khác có ballot 13?

Nó phải chạy phase 1 theo protocol, xét accepted values đã được báo về. Nếu X đã chosen, một value mâu thuẫn không thể được chosen bởi implementation Paxos đúng.

## 20. Vì sao Paxos không đơn giản là bỏ phiếu YES/NO?

Một cơ chế bỏ phiếu ngây thơ:

~~~text
P hỏi A và B: "chấp nhận X không?"
A, B: YES.
~~~

Nếu sau đó một proposer khác lại hỏi B và C về Y và hai nodes vô điều kiện trả YES, hệ có thể chọn cả X và Y.

Paxos bổ sung:

- Ballot numbers có thứ tự.
- Promise không nhận proposals thấp hơn đã hứa.
- Lưu accepted ballot/value.
- Phase 1 xem lịch sử accepted trước khi đề xuất lại.
- Majorities giao nhau.

Nhờ vậy, quorum intersection không chỉ là hình học các tập hợp mà có **thông tin và quy tắc an toàn** để bảo vệ quyết định cũ.

### 20.1. Accepted khác chosen

Một acceptor accept Y không nghĩa Y đã chosen. Một proposer mới vẫn phải xét state accepted để tiếp tục đúng, thay vì chỉ lấy local newest value.

### 20.2. Chosen khác learned

Một value có thể đã chosen nhưng một learner/client chưa nhận thông báo. Điều này tạo trường hợp **write đã commit nhưng response mất**, rất quan trọng khi thiết kế idempotency và xử lý timeout.

### 20.3. Chọn giá trị không tự đồng nghĩa đã thực hiện side effect

Nếu một application chọn “gửi email” làm value rồi mỗi acceptor cùng gửi email khi apply, người nhận có thể nhận nhiều email. Side effect cần được xử lý qua một executor có idempotency/outbox contract, không tùy tiện gửi từ mọi replica.

## 21. Multi-Paxos: từ chọn một giá trị sang một chuỗi lệnh

Single-Decree Paxos giải quyết một quyết định. Database cần hàng triệu quyết định:

~~~text
Slot 1: INSERT user U101
Slot 2: UPDATE user U101
Slot 3: DELETE user U102
...
~~~

**Multi-Paxos** tổ chức nhiều consensus instances/log slots và thường có **stable leader** để giảm chi phí phase 1 lặp lại trong trạng thái ổn định.

### 21.1. Vì sao stable leader hữu ích?

Nếu mỗi entry đều phải tranh ballot và chạy prepare từ đầu, overhead sẽ lớn. Khi leader ổn định và có ballot đủ thẩm quyền theo protocol, hệ có thể tiếp tục đề xuất nhiều log entries với đường đi tối ưu hơn.

### 21.2. Multi-Paxos không chỉ bằng việc chạy nhiều Paxos độc lập

Cần giải quyết thêm:

- Thứ tự log slots.
- Leader changes.
- Gaps ở các slots.
- Reconfiguration.
- Commit/application progress.
- Snapshot/compaction.
- Retry và duplicate proposals.

Vì vậy triển khai một replicated log production có nhiều chi tiết hơn mô hình hai phase của Single-Decree Paxos.

### 21.3. Không nói Paxos lúc nào cũng chậm gấp đôi Raft

Số round trips tùy stable leader, batching, pipelining, topology, tối ưu hóa giao thức và implementation. So sánh hiệu năng chỉ từ sơ đồ Prepare/Accept với AppendEntries là không đủ.

### 21.4. Có nhiều biến thể Paxos

Những tên có thể gặp trong tài liệu:

- Multi-Paxos.
- Fast Paxos.
- EPaxos.
- Flexible Paxos.
- Các giao thức/biến thể được tối ưu cho storage hoặc transaction.

Không có một “Paxos duy nhất” mô tả toàn bộ semantics và performance của mọi database.

## 22. Raft và Paxos giống nhau ở mục tiêu nhưng khác ở mô hình trình bày

| Khía cạnh | Raft | Paxos / Multi-Paxos |
|---|---|---|
| Mục tiêu | Replicated log/state machine an toàn | Đồng thuận về giá trị; mở rộng sang replicated log |
| Khái niệm phiên | Term | Ballot/proposal number |
| Thành phần điển hình | Leader, follower, candidate | Proposer, acceptor, learner; stable leader trong nhiều triển khai |
| Bầu leader | Phần trung tâm, rõ trong giao thức Raft | Không bắt buộc ở Single-Decree; thường được thêm ở Multi-Paxos |
| Chuyển đổi lịch sử | AppendEntries với log-matching | Accepted value/ballot với recovery của slots |
| Kết quả chọn | Commit entries theo quy tắc Raft | Chosen value khi accept majority theo classic Paxos |
| Cơ sở an toàn | Majority intersection + election/log/commit restrictions | Majority intersection + promises/accepted-value rules |
| Thao tác sau client timeout | Có thể committed dù ACK mất | Có thể chosen dù learner/client chưa biết |
| Phạm vi tìm hiểu của DBA | Leader, term, quorum, commit/apply, snapshots | Ballot, promise, accept/chosen, contention, LWT |

Điều chung cần nhớ: **không có quyền quyết định chỉ vì một node còn sống hoặc nhận lệnh nhanh nhất**. Safety đến từ việc các nhóm bỏ phiếu có giao nhau và mọi thành viên tuân theo quy tắc về trạng thái đã chọn.

## 23. Consensus và CAP: tại sao một phía có thể phải ngừng ghi?

Với ba voters A, B, C:

~~~text
Partition 1: A
Partition 2: B + C
~~~

### 23.1. Phía thiểu số

A chỉ có một trong ba phiếu, không thể commit entry mới theo quorum của Raft/Paxos classic.

Nếu A vẫn xác nhận ghi mà không quorum, đó không còn là quyết định được bảo vệ bởi giao thức consensus đang nói đến.

### 23.2. Phía đa số

B+C có thể tiến hành bầu leader hoặc tiếp tục proposals nếu điều kiện khác đáp ứng. Tuy vậy, phải có đủ communication và timeouts thích hợp; không phải cứ có hai node là mọi request lập tức thành công.

### 23.3. Thời điểm leader election

Trong thời gian election, application có thể nhận:

~~~text
Not leader
No leader
Unavailable
Timeout
Redirect
~~~

Một client/driver nên hiểu retryable errors và cập nhật leader routing theo hợp đồng của hệ.

### 23.4. CAP không phải chọn hai trong ba mọi lúc

Khi mạng không bị phân vùng, hệ có thể vừa ghi mạnh vừa phục vụ tốt. Trong partition, đường ghi cần consensus ở phía không đủ quorum có thể tạm unavailable để giữ safety.

### 23.5. Consensus không bảo đảm hệ luôn có leader

Mạng dao động, majority voters không đủ, disk lỗi hoặc clock/timer hành xử bất thường có thể làm election không tiến triển trong một giai đoạn. Consensus ưu tiên không chọn hai kết quả xung đột thay vì luôn phải trả success ở mọi điều kiện.

## 24. FLP và thời gian chờ: hiểu đủ để vận hành

### 24.1. Trực giác

Trong một mô hình phân tán hoàn toàn bất đồng bộ, không có giới hạn trễ thông điệp và một node có thể crash, không thể có thuật toán consensus deterministic bảo đảm luôn kết thúc trong mọi execution.

Kết quả kinh điển này thường được gọi là **FLP impossibility**.

### 24.2. Điều đó không có nghĩa consensus không dùng được

Các hệ thực sử dụng:

- Timeouts.
- Randomized election.
- Những giả định về mạng **eventually ổn định đủ lâu**.
- Failure detectors thực dụng.
- Tối ưu hóa protocol.

Raft/Paxos có thể tiến triển tốt trong mạng thực khi quorum còn hoạt động và điều kiện ổn định thỏa mãn. FLP giải thích vì sao không thể hứa tiến triển vô điều kiện với bất kỳ mạng và lỗi nào.

### 24.3. Timeout không phải bằng chứng node chết

Một leader không nhận heartbeat có thể:

- Chết thật.
- Bị partition.
- Bị GC pause.
- Bị quá tải.
- Gặp disk stall.

Không tự xóa data node hoặc cấp quyền ghi cho node khác chỉ vì một request timed out.

### 24.4. Randomization giảm split vote

Raft randomizes election timeouts giúp candidates ít tranh cùng lúc. Nhưng nếu latency quá lớn, heartbeat mất liên tục hoặc cấu hình timeout sai, election storms vẫn xảy ra.

### 24.5. Clock skew

Logical terms/ballots không phụ thuộc đồng hồ vật lý để xác định thứ tự epoch. Tuy nhiên leader leases, certificate validity, retry deadlines và các tối ưu hóa đọc dựa trên thời gian có thể nhạy cảm với clock skew/clock pauses.

## 25. Quyền ghi và fencing: ngăn leader hoặc worker cũ tác động ra ngoài

### 25.1. Leader consensus chỉ điều phối phạm vi mà nó quản lý

Giả sử một hệ có leader A điều phối log. A từng được quyền xử lý upload:

~~~text
Epoch 41: Worker A giữ quyền xử lý job J101.
Epoch 42: Worker B nhận quyền sau failover.
~~~

Nếu A bị network pause, không nhận thông tin epoch 42, rồi tiếp tục ghi object storage hoặc gọi payment provider, quyền lãnh đạo của cụm database **không tự chặn side effect tại resource ngoài**.

### 25.2. Fencing token

Một kỹ thuật là gắn quyền sở hữu với **số epoch tăng đơn điệu**:

~~~text
Worker A: token=41.
Worker B: token=42.
~~~

Resource đích kiểm tra:

~~~text
if request.token < lastAcceptedToken:
    reject STALE_OWNER
else:
    process according to resource contract
~~~

Với resource thật, kiểm tra token và side effect phải được phối hợp đủ nguyên tử để không có race giữa check và write.

### 25.3. TTL lock không đủ

Một worker có thể giữ Redis lock TTL 30 giây:

~~~text
t0  Worker A lấy lock.
t1  A bị pause 40 giây.
t2  Lock hết hạn.
t3  B lấy lock và bắt đầu ghi.
t4  A thức dậy, vẫn thực hiện side effect.
~~~

Nếu resource không kiểm tra epoch/fencing, A và B có thể cùng thao tác. Không thể suy “lock đã hết hạn nên A chắc chắn dừng chạy”.

### 25.4. Khi dùng hệ quản trị

Hãy xác định:

- Database quản lý leader/epoch cho **replicated data group** nào?
- Ứng dụng có lease/worker ownership bên ngoài không?
- Side effect nào nằm ngoài transaction của database?
- Resource đích có hỗ trợ conditional write/version check/fencing token không?
- OperationId có được giữ để dedup retry không?

### 25.5. Fencing khác optimistic concurrency

**Fencing** ngăn owner cũ dùng quyền đã hết hiệu lực.

**Optimistic concurrency** kiểm tra phiên bản dữ liệu trước khi cập nhật.

Chúng có thể kết hợp. Một operation có thể yêu cầu cả owner epoch hợp lệ và document version mong đợi.

## 26. Client timeout: trạng thái UNKNOWN quan trọng hơn FAILED

### 26.1. Hai tình huống có cùng biểu hiện

Client gửi:

~~~text
PUT /reservations/R101
~~~

Sau 2 giây nhận timeout.

**Trường hợp A:**

~~~text
Leader không đạt quorum.
Entry chưa commit.
Client timeout.
~~~

**Trường hợp B:**

~~~text
Leader đạt quorum, commit và áp dụng.
Response bị mất trên mạng.
Client timeout.
~~~

Trong cả hai trường hợp client chỉ biết **không nhận được kết quả**. Không được tự kết luận chưa có side effect.

### 26.2. Kết quả ba trạng thái

Một API ghi đáng tin cậy nên phân biệt:

~~~text
SUCCESS:      xác nhận committed theo contract.
REJECTED:     xác nhận không được phép/không được thực hiện.
UNKNOWN:      client chưa thể biết kết quả cuối.
~~~

Trong một số API, UNKNOWN được thể hiện bằng timeout, retryable error hoặc operation status PENDING.

### 26.3. Idempotency key

Client tạo operationId ổn định:

~~~json
{
  "operationId": "RESERVE-REQ-101",
  "seatId": "S101",
  "userId": "U17"
}
~~~

Server xử lý:

~~~text
Nếu operationId đã hoàn tất:
    trả lại kết quả trước đó.

Nếu operationId chưa tồn tại:
    thực hiện conditional mutation theo contract.

Nếu operationId đang tiến hành:
    trả PENDING/UNKNOWN hoặc phối hợp hợp lệ.
~~~

**Tối quan trọng:** Dedup state và mutation nghiệp vụ phải có một transaction/atomic relation phù hợp. Nếu ghi dedup marker thành công nhưng reservation thất bại, hoặc ngược lại, cần workflow khôi phục rõ.

### 26.4. Retry không được tạo lệnh mới ngẫu nhiên

Nếu client timeout rồi tạo operationId mới, hai proposals có thể cùng được commit:

~~~text
REQ-101: charge $10.
REQ-102: charge $10.
~~~

Consensus bảo đảm thứ tự các entries, **không tự nhận ra hai entries là cùng ý định thanh toán**.

### 26.5. Read-after-timeout

Client có thể truy vấn:

~~~http
GET /operations/RESERVE-REQ-101
~~~

Đường đọc trạng thái phải có consistency đủ để không trả NOT_FOUND sai trong khi operation đã commit nhưng một read replica còn trễ.

### 26.6. Retry policy

Một retry plan phải có:

- Deadline tổng.
- Số lần thử giới hạn.
- Backoff và jitter.
- Danh sách lỗi retryable theo SDK/engine.
- Idempotency cho side effects.
- Reconciliation khi quá deadline.

Không retry vô hạn một business conflict như username đã tồn tại.

## 27. Cần hiểu read concern, write concern và ACK của chính hệ mình dùng

Một database có thể có nhiều mức:

~~~text
ACCEPTED_BY_COORDINATOR
WRITTEN_TO_LOCAL_LOG
REPLICATED_TO_QUORUM
COMMITTED
APPLIED
VISIBLE_ON_REPLICA
ACKNOWLEDGED_TO_CLIENT
~~~

Các mức không nhất thiết xuất hiện dưới tên đó trong mọi engine, và thứ tự/semantics chi tiết phụ thuộc implementation.

### 27.1. Ghi nhanh nhất không luôn bền nhất

Nếu ACK ngay trên một node, failover trước khi replication có thể khiến thay đổi mất theo policy được chọn.

Nếu chờ majority, có thể tăng durability/consistency cho những lỗi được protocol bao phủ, nhưng latency và khả năng phục vụ khi mất quorum cũng thay đổi.

### 27.2. Majority ACK không nghĩa tất cả replica đã apply

Trong cụm 5 voters, majority 3 là đủ theo quy tắc một số operations. Hai replica còn lại có thể lag, tùy cách đọc của hệ.

### 27.3. Đọc từ follower có thể stale

Một PUT committed trên majority không tự khiến GET từ bất kỳ follower nào lập tức thấy dữ liệu mới.

Nếu API cần RYW, dùng đường đọc được contract bảo đảm, session token/revision hoặc chờ follower bắt kịp theo cơ chế được hỗ trợ.

### 27.4. Strong read không đồng nghĩa transaction xuyên mọi shard

Một operation có thể linearizable trên **một key hoặc replication group** nhưng không có atomicity xuyên nhiều keys ở nhiều shards.

Điều này đặc biệt quan trọng với NoSQL, nơi replication groups có thể tách theo partition/tablet.

### 27.5. Xác định nguồn sự thật

Nếu read model cache/search chạy bất đồng bộ từ outbox:

~~~text
Consensus-backed source commit
         |
         v
CDC / Outbox
         |
         v
Search index / Cache
~~~

Source có thể đã commit mạnh, trong khi search/cache còn eventual. Đừng dùng projection stale để quyết định những invariant phải được bảo vệ ở nguồn.

## 28. Cassandra/ScyllaDB: Paxos trong lightweight transaction

### 28.1. Ghi thông thường và LWT là hai đường khác nhau

Cassandra/ScyllaDB có cơ chế replication/quorum cho những thao tác thường; **không phải mọi INSERT/UPDATE thường đều chạy Paxos**.

Lightweight transaction (LWT) dùng giao thức dựa trên Paxos để hỗ trợ các **conditional statements**, ví dụ:

~~~sql
INSERT INTO username_claims (
    tenant_id,
    username_canonical,
    owner_id
) VALUES (
    'T17',
    'alice',
    101
) IF NOT EXISTS;
~~~

Chỉ một request hợp lệ nên thắng claim cho cùng primary key trong phạm vi bảo đảm của LWT và topology đã cấu hình.

### 28.2. Vì sao đọc rồi ghi không đủ?

Thiết kế sai:

~~~text
Client A: SELECT username=alice -> not found.
Client B: SELECT username=alice -> not found.
Client A: INSERT claim owner=A.
Client B: INSERT claim owner=B.
~~~

Hai reads thấy absent không tạo một điểm quyết định atomic. Conditional mutation giải quyết race trong phạm vi operation.

### 28.3. IF version = expected

Một ví dụ optimistic update:

~~~sql
UPDATE account_settings
SET theme = 'dark', version = 8
WHERE tenant_id = 'T17'
  AND user_id = 101
IF version = 7;
~~~

Câu lệnh mang tính minh họa về expected-version check. Schema, partition key và đặc tính supported CQL phải phù hợp môi trường triển khai.

Nếu hai clients cùng dựa trên version=7, chỉ một mutation có thể thành công theo conditional semantics; bên còn lại cần đọc lại version rồi quyết định merge/retry.

### 28.4. SERIAL và LOCAL_SERIAL

Cassandra có **serial consistency levels** liên quan phase Paxos của conditional statements trong những phạm vi được hỗ trợ.

Điều quan trọng không phải nhớ tên flag rồi dùng bừa, mà là hiểu:

- Quyết định có phạm vi datacenter hay topology nào?
- Request bình thường dùng consistency level nào?
- Conditional read/write áp dụng trong phạm vi primary key/partition ra sao?
- Thao tác có thể timeout nhưng đã apply không?
- Điều gì xảy ra khi client retry cùng condition?

### 28.5. LWT không phải global serializable transaction

Một IF NOT EXISTS trên partition P1 không tự tạo transaction nguyên tử với INSERT trên partition P2 hoặc một gọi HTTP tới payment provider.

Nếu claim username và profile ở hai partitions, cần workflow/transaction design cụ thể; không tuyên bố “đã dùng Paxos nên cả hai cùng commit hoặc rollback”.

### 28.6. Chi phí throughput và latency

LWT thường có nhiều phối hợp hơn ghi thường. Dùng LWT cho mọi view count hoặc telemetry event có thể gây overhead không đáng có.

Đặt LWT ở những nơi thật sự cần atomic conditional decision, chẳng hạn uniqueness claim hoặc compare-and-set.

### 28.7. Phạm vi partition quan trọng hơn một khóa business tùy ý

Nếu hai record có cùng email nhưng được định tuyến đến **hai partition keys khác nhau**, hai lệnh IF NOT EXISTS cục bộ trên mỗi partition đều có thể thành công. Thiết kế unique business key cần khiến các claim của cùng identity hội tụ về **một khóa có thẩm quyền**.

## 29. Etcd và Consul: ví dụ Raft ở control plane

### 29.1. Etcd

Etcd sử dụng Raft cho một distributed key-value store phục vụ nhiều trường hợp coordination/metadata. Khi sử dụng các API phù hợp, người dùng có thể làm việc với revision, compare-and-swap và những transaction operations của etcd trong phạm vi được hỗ trợ.

Một pattern:

~~~text
Read routing owner for tenant T17.
Compare expected revision/owner.
Update owner to shard B atomically if unchanged.
~~~

Nhưng việc cập nhật owner trong etcd **không tự dịch chuyển dữ liệu trên shard B**, cũng không tự khóa worker cũ đang chạy ở hệ bên ngoài.

### 29.2. Consul

Consul dùng Raft trong những thành phần server/control-plane phù hợp để quản lý trạng thái có thẩm quyền. Một client phải phân biệt yêu cầu đọc nhất quán và các đường đọc có thể stale theo API.

Không dùng cụm từ “Consul dùng Raft” để suy tất cả traffic, DNS caching hoặc mọi health-check response đều linearizable.

### 29.3. Consensus cho metadata khác consensus cho toàn bộ payload

Ví dụ:

~~~text
Raft consensus:
  tenant T17 -> owner shard C, epoch 42.

Large data:
  billions of tenant records stored on shard C.
~~~

Raft metadata group có thể chỉ quản lý assignment và fencing epoch, còn dữ liệu nghiệp vụ có replication và transaction model khác.

### 29.4. Điều người vận hành cần đo

- Leader availability/elections.
- Quorum health.
- Read/write p99.
- Applied revision/lag.
- Disk fsync latency.
- Snapshot size/catch-up.
- Revision watch backlog.

Nếu metadata service không khả dụng, router có thể không biết owner mới, dù data shards còn chạy.

### 29.5. Không dùng etcd như kho sự kiện khổng lồ chỉ vì nó có Raft

Một consensus-backed metadata store có ưu thế về các quyết định nhỏ, cần nhất quán, nhưng không mặc định phù hợp cho bulk analytics, log hàng tỷ events hoặc payload lớn.

Chọn store theo access pattern, scale và semantics, không theo tên consensus algorithm.

## 30. MongoDB: election, majority và đường đọc

MongoDB replica set có primary/secondary và cơ chế election; giao thức replication/election của sản phẩm không nên bị đồng nhất máy móc với implementation textbook Raft hoặc Paxos.

### 30.1. Majority write concern

Một write với majority write concern được xác nhận theo mức majority được MongoDB định nghĩa trong cấu hình tương ứng. Điều này liên quan đến bảo vệ commit/durability trước một số kiểu rollback.

### 30.2. Không đủ majority thì sao?

Khi primary không thể đạt mức ghi mong muốn, request có thể chờ, timeout hoặc lỗi. Application phải xử lý tình huống thay vì tự retry ghi không điều kiện vô hạn.

### 30.3. Secondary read

Nếu read preference hướng tới secondary:

~~~text
Primary:   profile version 12
Secondary: profile version 11
~~~

Secondary có thể lag. Majority write concern **không có nghĩa mọi secondary reads ngay lập tức thấy version 12**.

### 30.4. Read concern và causal session

Một số read concerns và session semantics của MongoDB giúp đạt những bảo đảm quan sát nhất định. Nếu cần read-your-writes hoặc snapshot, phải chọn cấu hình phù hợp với API, topology và transaction boundary, không tự suy từ từ “majority”.

### 30.5. Failover

Trong primary election:

- Một số writes có thể timeout.
- Các requests đang bay có unknown outcome.
- Client/driver cần route sang primary mới.
- Replica chưa catch up có thể chưa phục vụ các reads đủ mới.

Ứng dụng cần idempotency và retry policy phù hợp với MongoDB driver, không tự giả định mọi MongoDB update an toàn khi gọi lại.

## 31. DynamoDB: API có tính nguyên tử nhưng đừng suy ra thuật toán nội bộ

DynamoDB có **conditional writes**, **transactions** và các lựa chọn read consistency trong phạm vi được dịch vụ hỗ trợ. Người sử dụng không cần và không nên tự gán một implementation Raft/Paxos cụ thể cho từng API nếu nhà cung cấp không công bố điều đó.

### 31.1. Conditional PutItem

Một claim item:

~~~text
PK = USERNAME#T17#alice
ownerId = U101
~~~

PutItem với condition:

~~~text
attribute_not_exists(PK)
~~~

có thể bảo vệ create-if-absent cho key này trong phạm vi consistency/Region mà API cung cấp.

### 31.2. TransactWriteItems

Nếu cần tạo claim và user record cùng nhau trong một transaction được hỗ trợ:

~~~text
ConditionCheck/Put username claim
Put user profile
~~~

có thể dùng transactional API theo giới hạn và semantics của DynamoDB.

### 31.3. GSI eventual

Một Query tới Global Secondary Index có thể không nhìn thấy một write mới ngay sau khi bảng cơ sở đã ACK.

Không query GSI để quyết định “username chưa tồn tại” rồi Put profile không điều kiện.

### 31.4. Global Tables

Các chế độ Global Tables có consistency/replication semantics khác nhau. Trong chế độ multi-Region eventual, conditional write thành công ở Region A **không tự đảm bảo** global uniqueness nếu Region B đồng thời nhận ghi đối kháng cùng item.

Nếu invariant yêu cầu một owner toàn cầu, cần một kiến trúc/consistency mode được hỗ trợ đúng cho phạm vi đó hoặc một điểm quyết định có thẩm quyền.

### 31.5. Điều cần nắm

Đối với DynamoDB, **contract API** quan trọng hơn phỏng đoán về thuật toán consensus nội bộ. Hãy hỏi thao tác nào được strongly consistent, transaction bao phủ những items nào, GSI có thể trễ bao lâu và multi-Region xử lý concurrent writes ra sao.

## 32. ZooKeeper và những giao thức gần consensus

ZooKeeper cung cấp một dịch vụ coordination có semantics riêng; nó sử dụng **Zab** (ZooKeeper Atomic Broadcast), không phải implementation textbook của Raft hay Paxos.

### 32.1. Vì sao vẫn có liên hệ?

Zab và những giao thức replicated log khác cùng giải quyết nhu cầu:

- Có một thứ tự cập nhật có thẩm quyền.
- Duy trì nhất quán trên nhiều server.
- Phục hồi sau leader change.
- Xử lý partition và quorum.

### 32.2. Không coi mọi API của một coordination service giống nhau

Việc coordination service bảo vệ thứ tự ghi không có nghĩa mọi read từ mọi node luôn linearizable trong mọi mode.

Phải xem session, watch, sync và các consistency guarantees của từng API.

### 32.3. Distributed lock dựa trên coordination

Lock được cấp bởi coordination service có thể giúp một worker giữ vai trò primary, nhưng side effects ngoài service vẫn cần fencing/version hoặc nguyên tắc ownership phù hợp.

### 32.4. Cần ghi nhận session expiry

Một client mất kết nối đủ lâu có thể mất session/lease quyền sở hữu dù process vẫn chạy. Khi kết nối lại, nó không được tiếp tục hành động như thể quyền cũ vẫn còn.

## 33. Một hệ NoSQL có thể dùng nhiều giao thức ở những tầng khác nhau

Một kiến trúc thực tế:

~~~mermaid
flowchart TD
    A["Application"]
    A --> B["Metadata / routing control plane"]
    A --> C["Operational data shards"]
    C --> D["Index / cache / search projections"]
    B --> E["Consensus / leader ownership"]
    C --> F["Replication and transactions per shard"]
    D --> G["Async CDC and eventual updates"]
~~~

Các tầng có thể có bảo đảm khác nhau:

| Tầng | Cần thống nhất điều gì? | Ví dụ tính chất |
|---|---|---|
Metadata | Shard/leader owner, membership | Consensus/epoch |
Business transaction | Ai sở hữu seat/username | Conditional write/transaction |
Data replica | Các mutations được lưu/đọc ra sao | Quorum/async replication |
Search index | Document phản ánh source event | Eventual projection |
Cache | Key có đủ mới không? | TTL/invalidation/version |
Analytics | Tổng hợp qua nhiều shards | Watermark/reconciliation |

**Không có một nhãn “database dùng Raft” nào đủ để suy bảo đảm của toàn bộ kiến trúc**.

## 34. Sharding: mỗi replication group có một quyết định riêng

### 34.1. Một cluster có thể chứa nhiều consensus groups

Giả sử dữ liệu được chia thành ba shards:

~~~text
Shard A voters: A1 A2 A3
Shard B voters: B1 B2 B3
Shard C voters: C1 C2 C3
~~~

Mỗi group có leader và commit progress riêng. Một write tới shard A có thể thành công ngay cả khi shard B đang bầu leader, tùy phụ thuộc và topology.

### 34.2. Quorum nào áp dụng?

Không được tính:

~~~text
Tổng 9 voters -> majority 5.
~~~

rồi suy thao tác ở shard A cần 5 phiếu trên 9 node. Trong mô hình này, majority của group A là 2 trên 3; các group còn lại hoạt động riêng.

### 34.3. Cross-shard transaction

Nếu một transaction cập nhật:

~~~text
Account A trên Shard A
Account B trên Shard B
~~~

thì mỗi group commit độc lập không tự tạo một transaction atomic xuyên hai shards.

Cần một **distributed transaction protocol** phù hợp (ví dụ các biến thể two-phase commit kết hợp consensus-backed participants/coordinator) hoặc một data/workflow design khác bảo toàn invariant.

### 34.4. Two-phase commit khác Paxos Phase 1/2

Đây là nhầm lẫn rất phổ biến:

- **Two-phase commit (2PC):** Giao thức phối hợp commit/abort của một distributed transaction.
- **Paxos Prepare/Accept:** Các phase của thuật toán đồng thuận chọn một value.

Tên đều có “two phase” nhưng giải quyết bài toán khác nhau và không tự thay thế nhau.

2PC đơn giản có nguy cơ blocking khi coordinator hỏng; consensus-backed transaction coordinator/participants có thể giảm một số rủi ro nhưng vẫn cần thiết kế giao dịch đầy đủ.

### 34.5. Một hot shard không được cứu bằng majority của shard khác

Nếu shard A chứa một hot key, các voters B1..C3 còn rảnh không tự chia được atomic writes của hot key ấy. Cần thay data model/partitioning hoặc tối ưu đường truy cập, không chỉ tăng tổng số voters.

## 35. Leader election không giải quyết mọi vấn đề về hiệu năng

### 35.1. Election storm

Các lỗi về network latency, GC pauses, disk stalls hoặc election timeout quá nhạy có thể khiến node liên tục đổi term/leader.

Biểu hiện:

~~~text
term tăng rất nhanh
leader changes liên tục
write timeouts tăng
commit latency p99 tăng
~~~

### 35.2. Leader nóng

Một leader có thể quá tải vì ghi lớn, quá nhiều requests vào một key, snapshot/compaction, follower chậm, network egress hoặc CPU cho state machine.

Chuyển leader sang node khỏe có thể giảm tải tạm thời, nhưng nếu workload vượt khả năng một replication group thì hotspot có thể chuyển theo leader.

### 35.3. Batch/pipeline

Nhiều implementation có batching/pipelining để giảm chi phí round trip consensus.

Đánh đổi: batching có thể tăng throughput; batch lớn có thể tăng chờ cho một request đơn; burst có thể làm queue và p99 tăng.

Đừng tự giả định “mỗi Paxos operation luôn hai RTT còn Raft luôn một RTT” vì đường đi production có thể khác.

### 35.4. Snapshot pressure

Một follower phục hồi cần tải snapshot lớn. Network/disk bận có thể làm latency của leader và các write khác tăng.

Cần quan sát snapshot transfer, compaction, WAL/fsync và replication lag, không chỉ leader count.

### 35.5. Term/ballot tăng không nói lên dữ liệu bị mất

Một leader election có thể hoàn tất an toàn mà không làm mất committed entries. Tuy vậy nó có thể gây transient unavailability hoặc unknown outcomes cho requests đang bay.

Điều cần điều tra là **commit/read guarantees** và những writes nào đã ACK theo contract, không đơn giản lấy số lần đổi term làm số lần mất dữ liệu.

## 36. Chỉ số quan sát khi dùng cơ sở dữ liệu có consensus

| Nhóm | Metric | Điều cần biết |
|---|---|---|
| Quorum | Voting members alive/reachable | Có đủ members để commit/elect không? |
| Election | Leader changes, term changes | Có election storm hoặc mất leadership không? |
| Commit | Commit latency p50/p95/p99 | Quorum ACK và proposal progress có chậm không? |
| Apply | Commit index vs last applied | State machine có bắt kịp không? |
| Replication | Follower match index/lag | Replica nào đang thiếu entries? |
| Storage | WAL/fsync latency, disk saturation | IO có cản consensus ACK không? |
| Network | RTT, dropped RPCs, retransmits | Có partition hoặc high latency không? |
| Read | Linearizable read latency/errors | Đường xác minh leader/read-index có chậm không? |
| Requests | Timeout, not-leader, retry count | Client bị ảnh hưởng thế nào? |
| Reconfiguration | Voting config, learner catch-up | Có membership chuyển dở không? |
| Snapshot | Snapshot bytes/transfer duration | Node phục hồi có bắt kịp không? |
| Business | Duplicate side effects, unknown outcomes | Retry có làm sai nghiệp vụ không? |

Các tên trên là **nhóm metric mang tính khái niệm**. Engine cụ thể có tên metric, endpoint và observability riêng.

### 36.1. Consensus health không chỉ là node count

Trong cụm 5 voters có 4 node sống nhưng network tách thành 2+2 và một node còn lại không liên lạc được, chưa chắc có một majority group có thể phục vụ.

Quan sát **connectivity và quorum reachability**, không chỉ đếm processes.

### 36.2. Applied lag khác replication lag

Một follower có thể đã nhận log index 1.000 nhưng state machine mới apply tới 900. Đường đọc state machine có thể stale dù network replication đã bắt kịp.

### 36.3. Commit latency khác end-to-end latency

Client còn tốn thời gian ở gateway, authentication, queue, serialization và mạng. Nếu commit latency 20 ms nhưng request p99 3 giây, phải trace ngoài consensus.

### 36.4. Error budget và operation category

Read catalog eventual và payment reservation có thể có SLO khác nhau. Không dùng một biểu đồ “cluster available” để kết luận mọi thao tác business đều available.

### 36.5. Độ trễ theo Region

Nếu voting majority trải nhiều Region, consensus commit có thể cần cross-Region RTT. Cần đo tail latency trong giờ peak, không chỉ average ping.

## 37. Một runbook khi mất leader hoặc quorum

### 37.1. Bước 1 — Xác định phạm vi

~~~text
Read vẫn hoạt động?
Write nào bị ảnh hưởng?
Một shard group hay toàn cluster?
Một Region hay nhiều Region?
Có leader không?
Có đủ voting members reachable không?
~~~

### 37.2. Bước 2 — Phân loại lỗi

- Network partition.
- Node crash.
- Disk full/fsync chậm.
- GC pause/CPU saturation.
- Misconfigured timeout.
- Failed membership change.
- Snapshot/catch-up backlog.
- Application retry storm.

### 37.3. Bước 3 — Không tự ép hai phía cùng nhận ghi

Nếu nhóm minority không đạt quorum, không tắt kiểm tra consensus, không “promote” mọi node cũ thành leader chỉ để trả HTTP 200.

Lựa chọn an toàn thường là route tới group có thẩm quyền, chờ phục hồi hoặc thông báo lỗi/tạm dừng thao tác nhạy cảm.

### 37.4. Bước 4 — Kiểm tra leader term và configuration

Từ công cụ chính thức của engine, xem current leader/term, voting membership, node catch-up, quorum connectivity và trạng thái operation.

Không tự sửa file log/metadata quorum bằng tay khi chưa có runbook chính thức.

### 37.5. Bước 5 — Bảo vệ client requests

Giảm retry storm bằng bounded retries, exponential backoff với jitter, per-request deadline, idempotency key và trạng thái UNKNOWN/PENDING khi response không xác định.

### 37.6. Bước 6 — Phục hồi

Cho node phục hồi theo quy trình:

~~~text
Member joins / reconnects.
Snapshot or log catch-up.
Verify applied state.
Restore serving/routing.
Confirm quorum stable.
~~~

### 37.7. Bước 7 — Đối soát

Đối soát những mutations client timeout, external side effects đã xảy ra, duplicate bookings/charges, search/cache projections trễ và operationIds chưa có terminal state.

### 37.8. Bước 8 — Tổng kết sự cố

Ghi các mốc:

~~~text
Leader lost.
Quorum lost/recovered.
Election started/completed.
First successful write.
All critical user journeys recovered.
~~~

Đo cả **RTO**, latency và tác động user SLI, không chỉ thời điểm một process bắt đầu chạy.

## 38. Một bảng quyết định khi thao tác bị timeout

Giả sử ứng dụng có lệnh:

~~~text
POST /reservations
operationId=RESERVE-101
~~~

| Kết quả client thấy | Có thể đã commit? | Hành động |
|---|---|---|
| Success với commit contract rõ | Có | Trả/ghi nhớ kết quả |
| Business condition failed | Không thành công theo condition | Không retry cùng điều kiện vô hạn |
| Not leader / redirect | Có thể chưa xử lý; tùy thời điểm | Refresh route, retry an toàn |
| Quorum unavailable | Thường chưa xác nhận commit; vẫn xét unknown outcome | Query operationId/đợi hợp đồng |
| Timeout sau gửi | Có | Truy vấn trạng thái, retry idempotent |
| Connection reset sau gửi | Có | Không giả định thao tác chưa chạy |
| Follower stale read NOT_FOUND | Có thể item tồn tại ở source | Dùng đường đọc đủ mới |

### 38.1. Đừng chỉ dùng số lần retry

Nếu user vừa thanh toán, việc tự retry 10 lần có thể nghiêm trọng hơn để người dùng kiểm tra trạng thái.

### 38.2. Retrying conditional request

Một conditional write lần đầu đã thành công. Lần retry có thể trả condition failed vì điều kiện không còn đúng. Ứng dụng cần đối chiếu **operationId/owner hiện tại** để phân biệt “chính tôi đã thắng trước đó” với “người khác thắng”.

### 38.3. Idempotency không chỉ cho API ngoài

Worker xử lý event cũng có thể gặp retry sau crash. Nếu consumer đã gọi lệnh Raft-backed increment rồi crash trước checkpoint, phát lại event vẫn có thể tăng lần nữa nếu không dedup.

## 39. Chọn consistency theo invariant nghiệp vụ

| Nhu cầu nghiệp vụ | Bảo đảm đáng xem | Vì sao |
|---|---|---|
| Đếm lượt xem gần đúng | Eventual + aggregation | Chấp nhận trễ/đối soát |
| Xem catalog | Cache eventual có giới hạn | Ưu tiên latency và availability |
| Sửa profile rồi đọc lại | Read-your-writes/session read | Không đọc lại bản cũ |
| Claim username | Conditional create/unique ownership | Không để hai owners thắng |
| Đặt ghế cuối | Atomic reservation/transaction | Không bán trùng |
| Chuyển tiền | Ledger/transaction với invariant | Không tự cập nhật hai số dư độc lập |
| Phân công shard owner | Consensus/epoch/fencing | Một owner có hiệu lực |
| Phối hợp cron job | Lease + fencing/idempotency | Worker cũ có thể sống lại |
| Search index cập nhật | CDC/outbox + version-aware projection | Chấp nhận visibility lag |
| Xóa tài khoản | Revocation gate + deletion workflow | Không phục vụ dữ liệu đã thu hồi |

**Consensus cần thiết ở một số điểm quyết định** không có nghĩa mọi màn hình và mọi analytics query phải qua đường đọc mạnh.

## 40. Mười câu hỏi cần hỏi trước khi chọn một NoSQL database

1. **Phạm vi quyết định:** Consistency mạnh áp dụng cho một item, partition, shard group hay transaction nhiều items?
2. **Leader/quorum:** Operation cần leader hoặc quorum nào? Ai là voter, ai chỉ là learner/replica đọc?
3. **ACK:** Khi ghi trả thành công, entry đã durable/committed/applied ở mức nào?
4. **Read path:** Đọc follower có thể stale không? Có session token, revision, ReadIndex hoặc strong read API không?
5. **Conflict:** Nếu nhiều Region nhận ghi đồng thời, có conflict resolution hay serialization chung?
6. **Timeout:** Client có thể query lại operationId không? SDK tự retry những lỗi nào?
7. **Failover:** Election có thể mất bao lâu? Những request đang bay được báo trạng thái ra sao?
8. **Membership:** Thay node/Region phải đi qua quy trình config change nào? Có snapshot/catch-up không?
9. **Cross-shard:** Transaction xuyên những keys/shards nào thực sự được hỗ trợ?
10. **Business effects:** Làm sao bảo vệ unique, stock, payment và external side effects khỏi duplicate?

Đây là các câu hỏi **về hợp đồng của hệ quản trị**. Không cần đọc toàn bộ paper để triển khai ứng dụng đúng, nhưng không thể bỏ qua chúng chỉ vì provider quảng cáo “strongly consistent”.

## 41. Những hiểu lầm thường gặp

| Hiểu lầm | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| Raft/Paxos chỉ là replication | Chúng còn chọn một quyết định an toàn | Phân biệt replication và consensus |
| Có ba replicas thì mỗi replica được tự commit | Majority/protocol quyết định quyền | Kiểm tra quorum và owner |
| Một node còn sống nghĩa cụm vẫn ghi được | Có thể là minority partition | Xem voting configuration |
| 2/3 votes nghĩa mọi đọc mạnh ngay | Follower có thể chưa apply | Phân biệt commit/apply/read path |
| Raft không bao giờ có hai nodes tự nhận leader | Old leader có thể chưa biết term mới | Chỉ majority commit mới có thẩm quyền |
| Term là timestamp | Term là logical epoch | Không dựa vào wall clock |
| Bầu leader theo số entries nhiều nhất | Raft so lastLogTerm rồi index | Xem log up-to-date rule |
| Entry có ở hai node luôn committed | Với Raft còn quy tắc term hiện tại | Xem commit restriction |
| Một entry đã append luôn tồn tại sau failover | Uncommitted entry có thể bị ghi đè | Không ACK trước contract |
| Timeout nghĩa write chắc chắn chưa làm | Response có thể mất sau commit | UNKNOWN + idempotency |
| Client retry giống hệt là an toàn | Hai proposals có thể thành hai side effects | operationId/conditional dedup |
| Raft giúp email gửi exactly once | Consensus log không bao trùm email provider | Outbox/idempotency |
| Paxos chỉ là majority YES/NO | Có promises/accepted-history rules | Học hai phase và ballot |
| Acceptor accepted nghĩa chosen | Cần quorum accepted | Phân biệt accepted/chosen/learned |
| Ballot cao hơn có quyền chọn value bất kỳ | Phải kế thừa accepted value phù hợp | Preserve safety |
| Paxos không bao giờ có leader | Multi-Paxos thường có stable leader | Phân biệt Paxos variants |
| Raft luôn nhanh hơn Paxos vì ít phase | Tối ưu hóa, batching và topology khác nhau | Đo implementation thực |
| Paxos Phase 1/2 là 2PC | Hai giao thức khác bài toán | Consensus vs distributed transaction |
| Cassandra mọi ghi đều chạy Paxos | LWT là đường conditional chuyên biệt | Ordinary writes khác LWT |
| LWT trên hai partitions là global transaction | Phạm vi bảo đảm có giới hạn | Thiết kế claim/transaction đúng |
| MongoDB mọi read của secondary đều mạnh | Secondary có thể lag | Read concern/preference/session |
| DynamoDB có strong read nên GSI cũng strong | GSI hỗ trợ eventual reads | Đọc source phù hợp |
| Có consensus ở metadata nên data shards chắc chắn strong | Các tầng có giao thức khác nhau | Xem từng operation |
| Distributed lock TTL chặn worker cũ | Worker có thể pause rồi chạy lại | Fencing ở resource đích |
| Fencing chỉ cần kiểm tra epoch trước khi write | Check rồi write có thể race | Atomic check-and-act |
| Read từ leader cục bộ luôn linearizable | Old leader có thể partition | ReadIndex/lease đúng protocol |
| RTO tốt nghĩa không mất dữ liệu | RTO khác RPO | Kiểm tra write durability |
| Nhiều voters luôn cải thiện availability | Majority và fault domains thay đổi | Sizing quorum có chủ đích |
| Cụm tổng 9 nodes cần 5 votes cho mọi key | Shards có groups riêng | Xác định quorum đúng group |
| Consensus đảm bảo business invariant | State machine có thể đồng thuận lệnh sai | Validate invariants |

## 42. Bài tập 1 — đa số và phân vùng mạng

Một cụm có 5 voters A, B, C, D, E.

Mạng bị phân vùng:

~~~text
Nhóm 1: A, B, C
Nhóm 2: D, E
~~~

Yêu cầu:

1. Majority của 5 là bao nhiêu?
2. Nhóm nào có khả năng bầu leader mới?
3. Nhóm D+E còn chạy thì có thể tự commit một lệnh cần consensus không?
4. Nếu D là leader cũ nhưng chưa biết về election mới, có thể tự cho rằng mình là leader không?
5. Điều gì ngăn D commit entry mâu thuẫn theo Raft?

## 43. Bài tập 2 — bầu leader khi log không đều

Có ba nodes:

~~~text
Node A lastLog=(term 7, index 50)
Node B lastLog=(term 8, index 43)
Node C lastLog=(term 8, index 42)
~~~

1. Theo so sánh up-to-date của Raft, B có log mới hơn A không?
2. Tại sao nhiều entries hơn không phải điều kiện duy nhất?
3. Nếu B xin phiếu trong term mới, C có thể chấp nhận theo tiêu chí log không?
4. Ngoài log up-to-date còn những điều kiện vote nào phải xét?
5. Khi A trở lại, nó đồng bộ theo leader thế nào?

## 44. Bài tập 3 — commit index và applied index

Một follower có:

~~~text
lastLogIndex=120
commitIndex=118
lastApplied=114
~~~

Hãy giải thích:

1. Follower đã lưu entries đến đâu?
2. Những entries nào nó biết đã commit?
3. Nó đã áp dụng state machine đến đâu?
4. GET từ follower này có thể stale ở dữ liệu liên quan entries 115..118 không?
5. Một đường đọc yêu cầu minimum revision 118 phải làm gì?

## 45. Bài tập 4 — leader chết trước và sau commit

Hai timeline:

~~~text
Timeline A:
  Leader append entry 42.
  Chỉ một node persist.
  Leader crash.

Timeline B:
  Leader append entry 43.
  Majority persist.
  Leader commit theo quy tắc.
  Response tới client bị mất.
  Leader crash.
~~~

1. Entry nào chắc chắn không được kết luận committed từ thông tin đã cho?
2. Client ở Timeline B nên coi kết quả là FAILED hay UNKNOWN?
3. Nếu client retry cùng operation, cần idempotency ra sao?
4. Tại sao uncommitted entry có thể bị thay sau election?
5. Vì sao majority replication của một entry term cũ chưa phải đầy đủ điều kiện commit trong Raft?

## 46. Bài tập 5 — Paxos Phase 1/2

Ba acceptors A, B, C. Proposer P chọn ballot=15.

~~~text
Prepare(15) -> A, B, C.
A: promise(15), accepted ballot=10,value=X.
B: promise(15), accepted ballot=12,value=X.
C: không phản hồi.
~~~

1. P có đủ promises chưa?
2. P có được tùy ý đề xuất Y ở ballot 15 không?
3. Tại sao phải xét accepted proposal cao nhất?
4. Sau đó A+B accept ballot=15,value=X thì X ở trạng thái nào?
5. Nếu một proposer mới dùng ballot=16, nó phải tôn trọng điều gì?

## 47. Bài tập 6 — accepted và chosen

~~~text
A accepted Y at ballot 8.
B chưa accept Y.
C chưa accept Y.
~~~

1. Y đã chosen chưa?
2. Một proposer mới chạy prepare có thể nhận những state nào?
3. Nếu A+B+C sau đó đều accept X theo một ballot hợp lệ, cần giải thích protocol đã bảo vệ những điều gì?
4. Nếu Y đã được accepted bởi majority trước đó, proposer mới có thể cho X mâu thuẫn thắng không?
5. Phân biệt chosen và learned khi client chưa nhận response.

## 48. Bài tập 7 — Cassandra LWT

Hai users muốn đăng ký cùng username **alice** trong tenant T17.

~~~sql
INSERT INTO username_claims (
    tenant_id, username_canonical, owner_id
) VALUES (
    'T17', 'alice', 101
) IF NOT EXISTS;
~~~

1. Vì sao SELECT rồi INSERT thường có race?
2. LWT dùng Paxos để bảo vệ điều gì?
3. Nếu hai request cùng dùng **một primary key**, kết quả conditional nên thế nào?
4. Nếu application tạo hai claim với **hai primary keys khác nhau**, LWT có tự bảo vệ uniqueness toàn tenant không?
5. Phân biệt LWT và distributed transaction nhiều partitions.
6. LWT timeout có nghĩa condition chắc chắn chưa được apply không?

## 49. Bài tập 8 — Raft leader lease và fencing

~~~text
Worker A có quyền epoch 41.
A bị pause 40 giây.
Lease hết hạn sau 30 giây.
Worker B nhận quyền epoch 42.
A tỉnh lại và muốn ghi kết quả job.
~~~

1. Vì sao TTL lock không đủ?
2. Resource đích cần kiểm tra token/epoch thế nào?
3. Nếu check epoch và write không nguyên tử, còn race gì?
4. Nếu job gọi payment provider không hỗ trợ fencing, idempotency hỗ trợ ở đâu?
5. Điều gì khác giữa leader consensus và worker ownership ngoài database?

## 50. Bài tập 9 — người dùng đọc từ follower

Client:

~~~text
PUT profile version 12 -> ACK.
GET profile qua follower -> version 11.
~~~

1. Điều này có tự chứng minh consensus sai không?
2. Commit khác apply như thế nào?
3. Đường đọc follower có thể được hứa bảo đảm gì?
4. Nếu API cần read-your-writes, nên chọn session token/leader read hay minimum revision ra sao?
5. ReadIndex là gì ở mức khái niệm?

## 51. Bài tập 10 — cross-shard transaction

Một transfer:

~~~text
Debit Account A ở Shard 1.
Credit Account B ở Shard 2.
~~~

Mỗi shard có nhóm Raft riêng.

1. Nếu từng shard commit độc lập, hai bước có tự thành một transaction không?
2. Vì sao Paxos Phase 1/2 không đồng nghĩa transaction 2PC?
3. Nếu debit thành công, credit timeout, rủi ro là gì?
4. Có thể dùng distributed transaction/ledger workflow nào?
5. Cách thiết kế idempotency và reconciliation cho transferId?

## 52. Bài tập 11 — DynamoDB và Global Tables

Một ứng dụng dùng conditional PutItem để claim username ở Region A. Region B có cùng tên người dùng trong hệ Global Tables eventual.

1. Conditional PutItem local bảo vệ phạm vi nào?
2. Vì sao không thể tự suy nó tạo global uniqueness trong mọi cấu hình multi-Region eventual?
3. Nếu hai Region cùng nhận claim, conflict có thể gây hậu quả gì?
4. Đề xuất một authority/hợp đồng consistency global phù hợp.
5. Vì sao Query GSI theo email rồi INSERT không phải giải pháp an toàn?

## 53. Bài tập 12 — thời gian bầu leader và độ trễ người dùng

Trong 5 phút:

~~~text
Leader changes: 120.
Write p99:       8 giây.
Quorum errors:   tăng.
Network RTT:     tăng từ 4 ms lên 600 ms.
CPU:             bình thường.
~~~

1. Có thể đang gặp election storm không?
2. Vì sao CPU bình thường không loại vấn đề mạng?
3. Những metric nào cần xem để xác minh?
4. Có nên giảm election timeout xuống 1 ms không? Vì sao?
5. Nên thu thập trạng thái client retry và unknown outcomes ra sao?

## 54. Bài tập 13 — membership change

Một cụm 3 voters A, B, C chuẩn bị thay C bằng D.

1. Vì sao chỉ sửa một file config trên từng node vào thời điểm khác nhau có rủi ro?
2. Joint consensus giải quyết trực giác nào?
3. Learner có thể giúp gì khi thêm D?
4. Những kiểm tra nào cần trước khi loại C?
5. Nếu trong lúc chuyển C hỏng và D chưa catch up, hệ có thể còn quorum không? Cần xem configuration nào?

## 55. Bài tập 14 — sự cố client timeout

Một request:

~~~text
POST /payments
operationId=PAY-801
amountMinor=50000
~~~

Client timeout sau 2 giây. Database đã commit, nhưng response bị mất.

1. Vì sao retry với operationId mới nguy hiểm?
2. Thiết kế endpoint query status theo operationId.
3. Mô tả cách dedup và payment mutation được phối hợp atomic hoặc qua workflow có đối soát.
4. Nếu API trả UNKNOWN, UI nên truyền đạt thế nào mà không giả vờ FAILED?
5. Nếu một projection eventual chưa thấy PAY-801, có được coi payment chưa xảy ra không?

## 56. Bài tập 15 — so sánh Raft và Paxos

Điền một bảng bằng lời:

1. Term của Raft tương ứng loại khái niệm nào trong Paxos?
2. Vai trò leader/follower/candidate khác proposer/acceptor/learner ra sao?
3. Điều kiện chọn một log entry/value khác nhau ở mức mô tả nào?
4. Tại sao classic Paxos và Multi-Paxos không hoàn toàn cùng phạm vi?
5. Cả hai dùng majority intersection để bảo vệ safety như thế nào?
6. Vì sao không thể so performance bằng việc đếm tên phases đơn giản?

## 57. Bài tập 16 — phân tích contract của hệ quản trị

Giả sử bạn chuẩn bị dùng một NoSQL service cho:

- Profile đọc/ghi nhiều.
- Unique username.
- Reservation một ghế cuối cùng.
- Search index eventual.
- Analytics dashboard.

Hãy lập bảng nêu:

1. Mỗi thao tác cần mức consistency nào?
2. Phạm vi atomic transaction/conditional write được hỗ trợ ở đâu?
3. Client timeout được xử lý thế nào?
4. Những thao tác nào cần read-your-writes?
5. Có đường đọc qua GSI/secondary/search nào eventual?
6. Có external side effect nào cần idempotency/outbox?
7. Quorum/leader failover có thể tác động hành trình nào?

## 58. Bài tập 17 — lập runbook quorum loss

Cụm 5 voting nodes bị chia thành 2+2+1, và không phía nào liên lạc được với đủ majority.

Yêu cầu:

1. Xác định quorum majority.
2. Vì sao có 5 processes còn chạy nhưng toàn bộ writes cần consensus vẫn có thể bị từ chối?
3. Lập checklist đọc leader/term, network RTT, membership và storage.
4. Đề xuất cách giảm retry storm.
5. Xử lý requests đang có outcome chưa rõ.
6. Trình bày điều kiện phục hồi quorum trước khi mở lại giao dịch.
7. Giải thích vì sao không nên tự ép minority leader commit.

## 59. Bài tập 18 — bảng phân tách phạm vi bảo đảm

Một hệ gồm:

~~~text
Raft metadata store -> shard ownership.
Operational NoSQL   -> user/order records.
CDC                 -> search index.
Redis cache         -> read acceleration.
Payment provider    -> external side effect.
~~~

Với mỗi tầng:

1. Dữ liệu nguồn và trạng thái authoritative nằm đâu?
2. Có consensus ở tầng nào?
3. Những đường đọc nào có thể stale?
4. Worker cũ cần fencing không?
5. Retry phải idempotent ở ranh giới nào?
6. Khi recovery, metric nào chứng minh dữ liệu và projection đã hội tụ?

## 60. Tổng kết: hiểu Raft/Paxos ở mức đủ dùng khi vận hành NoSQL

**Raft và Paxos giải quyết bài toán nhiều node cùng chọn quyết định có thẩm quyền trong điều kiện lỗi phân tán.** Chúng là nền tảng quan trọng của nhiều hệ thống lưu trữ và điều phối, nhưng tên thuật toán không tự cho biết toàn bộ bảo đảm của một NoSQL database.

Những điều cốt lõi:

1. **Consensus khác replication.** Replication chuyển dữ liệu; consensus bảo vệ việc chọn một quyết định/chuỗi lệnh với những điều kiện an toàn.
2. **Majority có giao nhau nhưng chưa đủ một mình.** Raft cần quy tắc term/election/log/commit; Paxos cần promise/accepted-value/ballot.
3. **Raft dùng leader và log.** Hiểu follower/candidate/leader, RequestVote, AppendEntries, commitIndex và lastApplied.
4. **Paxos dùng ballot và hai phase.** Prepare/Promise để biết lời hứa và lịch sử; Accept/Accepted để chọn một value theo quorum. Multi-Paxos mở rộng sang log và thường có stable leader.
5. **Quorum mất thì một số thao tác phải dừng.** Đó có thể là hành vi bảo vệ safety trong network partition, không phải lý do để tự bỏ quorum check.
6. **Committed khác applied và visible.** Một follower có thể chưa đọc thấy mutation vừa được commit. Chọn read path theo nhu cầu RYW, linearizability hoặc eventual.
7. **Timeout tạo unknown outcome.** Mutation có thể đã commit dù response bị mất; retry cần operationId/idempotency và reconciliation.
8. **Leader cũ có thể còn chạy.** Consensus bảo vệ quyết định trong group, còn side effects bên ngoài cần fencing/version/ownership phù hợp.
9. **Consensus theo từng scope.** Quorum của một shard khác cluster-wide node count; giao dịch hai shards không tự atomic chỉ vì mỗi shard có Raft.
10. **Không đoán protocol nội bộ của managed service.** Với Cassandra LWT, MongoDB, DynamoDB, etcd, Consul hoặc ZooKeeper, điều quan trọng là API contract và phạm vi đã công bố.
11. **Đo vận hành bằng nhiều lớp.** Leader changes, quorum reachability, commit/apply lag, read latency, client retry, replication và các business invariants đều có giá trị.
12. **Không cần tự viết consensus để dùng NoSQL đúng.** Cần biết khi nào phải dùng conditional write/transaction/strong read và khi nào eventual projection là đủ.

Câu hỏi cuối cùng khi dùng một hệ NoSQL phân tán không chỉ là **“Nó chạy Raft hay Paxos?”**, mà là:

> **“Đối với thao tác này, nhóm node nào có quyền quyết định, khi nào kết quả được coi là committed, đường đọc nào bảo đảm quan sát được quyết định ấy, và khi lỗi mạng hoặc timeout xảy ra thì ứng dụng làm sao tránh xác nhận sai hoặc thực hiện trùng?”**





