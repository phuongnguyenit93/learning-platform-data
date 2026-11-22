# Sao chép đồng bộ, bất đồng bộ và thời điểm xác nhận ghi

Một ứng dụng Java gửi yêu cầu tạo đơn hàng vào một cơ sở dữ liệu NoSQL có ba bản sao. Database trả **thành công**, nhưng vài mili giây sau node vừa nhận ghi bị hỏng. Nếu một bản sao khác lên làm leader, đơn hàng có còn không? Nếu client chỉ nhận **timeout**, có thể kết luận đơn hàng chưa được tạo? Và nếu ghi đã được nhân bản tới hai node, liệu một truy vấn qua search index hoặc replica thứ ba đã nhìn thấy đơn hàng?

Các câu hỏi này đều xoay quanh một quyết định kiến trúc rất cụ thể:

> **Database xác nhận ghi (write acknowledgment) ở thời điểm nào, và lời xác nhận đó bảo đảm điều gì về lưu trữ, bản sao, khả năng đọc và khôi phục?**

Trong chương **Sao chép và quorum** của **Database No SQL**, bài học phân tích **sao chép đồng bộ (synchronous replication)**, **sao chép bất đồng bộ (asynchronous replication)** và các mô hình pha trộn; phân biệt ACK nhận lệnh, ACK ghi log, ACK đã commit, ACK từ replica và ACK có thể đọc được; làm rõ **quorum, độ bền dữ liệu, failover, replica lag, write concern, read consistency, RPO/RTO**, cùng các ví dụ MongoDB, Cassandra, Redis, HBase, DynamoDB và Java.

Tư tưởng cốt lõi: **“Write thành công” không có một ý nghĩa chung cho mọi NoSQL.** Nó phải được diễn giải theo **đúng thao tác, số replica, cơ chế ghi log, mức consistency/durability, phạm vi địa lý và giao thức failover**. Không được suy ra dữ liệu đã tới mọi bản sao, đã được fsync, đã hiện trên search index hoặc không thể bị mất trong mọi loại thảm họa chỉ vì client nhận HTTP 200.

> **Quy ước:** Sơ đồ và các phép tính là mô hình minh họa, không phải phát biểu chung cho mọi sản phẩm. Một số dịch vụ ẩn hoàn toàn đường sao chép và chỉ công bố hợp đồng API. Tên tùy chọn, hành vi mặc định và bảo đảm cụ thể phải được kiểm chứng theo phiên bản, cấu hình và tài liệu của engine thực tế.

## 1. Sao chép dữ liệu giải quyết vấn đề gì?

**Replication (sao chép)** là việc duy trì nhiều bản dữ liệu hoặc log liên quan trên những node, ổ đĩa, zone hoặc region khác nhau.

Những mục tiêu thường gặp:

- **Chịu lỗi:** một node hỏng mà hệ vẫn có đủ bản sao để phục hồi hoặc phục vụ.
- **Tăng khả năng đọc:** một số replica có thể nhận read traffic.
- **Giảm độ trễ địa lý:** phục vụ người dùng từ vùng gần nếu hợp đồng đọc cho phép.
- **Khôi phục:** dữ liệu hoặc log ở replica hỗ trợ recovery sau mất node.
- **Bảo trì:** di chuyển, thay máy và nâng cấp với ít gián đoạn hơn.
- **Tăng khả dụng vùng:** một số topology vẫn vận hành khi một zone/region lỗi.

Replication không tự động bảo đảm mọi mục tiêu ấy cùng lúc. Ví dụ một bản sao **bất đồng bộ** giúp khôi phục khỏi một số lỗi, nhưng có thể bị thiếu những write mới nhất khi leader chết. Một replica phục vụ đọc nhanh có thể trả **stale data**.

### 1.1. Replica, leader, follower và bản sao có thẩm quyền

Trong mô hình **single-leader**:

~~~~text
                Client write
                     |
                     v
                Leader (L)
                /        \
               v          v
          Follower A   Follower B
~~~~

Leader thường là điểm tiếp nhận/điều phối những write cần giữ thứ tự. Follower nhận log hoặc thay đổi rồi áp dụng theo protocol.

Trong **leaderless/quorum-style**, client hoặc coordinator có thể giao tiếp với nhiều replica và đếm phản hồi theo consistency level. Không mặc định có một leader cố định cho mọi write.

Trong **multi-leader**, nhiều nơi có thể chấp nhận write và trao đổi thay đổi sau; cần hiểu thứ tự, xung đột và cách hội tụ.

**“Sao chép đồng bộ” không nhất thiết đồng nghĩa “single-leader”, và “sao chép bất đồng bộ” không nhất thiết đồng nghĩa “leaderless”.** Đây là hai chiều thiết kế khác nhau.

### 1.2. Sao chép và phân mảnh là hai việc khác

- **Replication:** giữ những bản sao của cùng một tập dữ liệu hoặc đơn vị dữ liệu.
- **Sharding/partitioning:** chia tập dữ liệu thành các phần, phân công node phụ trách từng phần.

Một hệ có thể có 100 shard, mỗi shard được sao chép ba lần. Khi nói **RF=3**, cần biết đó là **ba bản của từng shard** hay ba node cho toàn bộ cụm. Nếu shard A thiếu quorum, shard B có thể vẫn hoạt động; tình trạng của từng shard không nhất thiết giống trạng thái toàn cluster.

## 2. Thời điểm xác nhận ghi có nhiều mốc

Một lệnh ghi có thể đi qua chuỗi công việc:

~~~~text
T0 Client phát request
T1 Database node nhận request
T2 Request được validate và đưa vào bộ nhớ/queue
T3 WAL/commit log được append
T4 Log hoặc file đạt mức durable sync theo cấu hình
T5 Replica khác đã nhận hoặc ghi log tương ứng
T6 Protocol xác định thao tác đã commit theo quy tắc
T7 Trạng thái được áp dụng vào dữ liệu phục vụ read
T8 Server gửi ACK
T9 Client nhận ACK
T10 Read replica / index khác trở nên query-visible
~~~~

Đây chỉ là các **mốc khái niệm**, không phải thứ tự chuẩn của mọi NoSQL. Ví dụ một số protocol quyết định commit rồi mới apply vào state machine, hoặc ACK được gửi trước khi có fsync theo cấu hình yếu. Search index có thể cập nhật rất lâu sau T9.

### 2.1. Những câu có thể cùng được gọi là “ghi thành công”

| Mốc xác nhận | Điều có thể đã được thực hiện | Điều chưa tự được bảo đảm |
| --- | --- | --- |
| Request accepted | Node tiếp nhận lệnh | Không chắc đã commit hoặc bền vững |
| In-memory applied | Thay đổi hiện diện ở RAM | Có thể mất khi crash nếu chưa được ghi bền |
| WAL appended | Log đã được ghi vào đường log | Append chưa chắc đã fsync; chưa chắc replica khác có |
| Durable locally | Node đạt mức bền vững cục bộ theo hợp đồng | Chưa chắc survive mất toàn node/zone nếu bản khác chưa có |
| Replicated to one follower | Một follower phản hồi theo protocol | Follower đó đã fsync hay chỉ nhận trong RAM? |
| Quorum acknowledged | Số node đạt điều kiện quorum/consensus | Không có nghĩa mọi replica đều đã apply hoặc searchable |
| Transaction committed | Quyết định commit hợp lệ theo giao thức | Không tự bao trùm external payment/email/index |
| Query-visible | Đường đọc cụ thể đã thấy write | Một read replica khác có thể vẫn stale |
| End-to-end business success | Invariant nghiệp vụ và các bước bắt buộc được xác nhận | Phải được định nghĩa bởi ứng dụng, không chỉ DB ACK |

**Ghi nhớ:** Đếm ACK mà không định nghĩa **ACK xác nhận cái gì** có thể gây ngộ nhận về durability. “Hai node nhận write” khác “hai node đã fsync log” và có thể khác “consensus entry đã committed”.

### 2.2. ACK của database khác HTTP success

~~~~text
Mobile -> API Gateway -> Order Service -> Database
                                           |
                                          ACK
~~~~

Database có thể trả ACK cho Order Service, nhưng gateway timeout trước khi service trả cho mobile. Hoặc service có thể trả **202 Accepted** chỉ vì nhận event vào queue, dù database xử lý nghiệp vụ chưa commit.

Vì vậy cần phân biệt:
- **DB write ACK:** theo hợp đồng database.
- **Service response:** theo hợp đồng nghiệp vụ của service.
- **Client observation:** kết quả được client thực sự nhận.
- **Downstream visibility:** search, cache, báo cáo đã nhìn thấy chưa.

Không lấy status code HTTP làm chứng cứ duy nhất cho write durability.

## 3. Sao chép bất đồng bộ: commit nguồn trước, replica theo sau

Trong kiến trúc sao chép bất đồng bộ phổ biến, leader có thể xác nhận ghi cho client **mà không cần chờ một hoặc nhiều follower theo kịp**.

~~~~mermaid
sequenceDiagram
    participant Client
    participant L as Leader
    participant F as Follower
    Client->>L: WRITE Order O-901
    L->>L: Append/apply according to local contract
    L-->>Client: ACK
    L-->>F: Replication update (later)
    F->>F: Apply replicated update
~~~~

Lợi ích:
- **Đường ghi ngắn hơn:** không đợi round-trip tới follower xa trên critical path.
- **Ít bị chặn bởi follower chậm:** leader có thể tiếp tục nhận ghi theo chính sách.
- **Có thể phù hợp với replication đa vùng:** khu vực xa bắt kịp nền.
- **Tách công việc đồng bộ nền:** có thể batch/compress/pipeline.

Rủi ro:
- **Replication lag:** follower chưa có write mới nhất.
- **RPO dương khi failover:** nếu leader mất trước khi write được nhân bản đủ an toàn, write đã ACK có thể bị mất hoặc cần recovery.
- **Stale reads:** nếu client đọc follower trong lúc lag.
- **Backlog:** follower/stream yếu hơn tốc độ ghi nguồn có thể tụt lại ngày càng xa.
- **Xung đột nếu cho phép nhiều nguồn ghi:** cần resolver và semantics rõ.

### 3.1. Ví dụ mất write sau ACK

~~~~text
T0 Leader L commit/ACK O-901 theo chính sách local.
T1 Client nhận "Order created".
T2 L chưa gửi xong O-901 tới F1, F2.
T3 L hỏng vĩnh viễn, không thể khôi phục log của nó.
T4 F1 được chọn làm leader mới và không có O-901.
~~~~

Nếu giao thức và durability policy cho phép leader xác nhận **trước** khi có bản sao đủ điều kiện được bảo vệ, O-901 có thể biến mất khỏi tập dữ liệu sau failover.

**Đây là rủi ro theo hợp đồng replication/durability đã chọn, không phải hệ nào có follower bất đồng bộ cũng chắc chắn mất dữ liệu.** Một số hệ có cơ chế khác để bảo vệ write đã ACK; phải kiểm chứng đường failover thực tế.

### 3.2. Async replication không có nghĩa “không đáng tin”

Với workload cho phép RPO nhỏ hơn một giới hạn đã định, async có thể là lựa chọn hợp lý:
- Search index/read model.
- Dashboard không cần hoàn toàn mới.
- Dữ liệu logging có thể khôi phục từ một event log bền khác.
- Bản sao báo cáo đa vùng.
- Replica đọc tại khu vực xa.

Điều kiện là cần **xác định dữ liệu nào có thể mất/trễ, cách replay, thời gian bắt kịp và cơ chế đối soát**.

### 3.3. Thời gian truyền trễ không chỉ do khoảng cách

Lag có thể gồm:
- Chậm tạo/phát log từ source.
- Network RTT, bandwidth và packet loss.
- Queue backlog.
- Follower apply/compaction/index I/O.
- Transaction hoặc batch lớn.
- Backpressure/throttling.
- Replica restart, recovery hoặc snapshot bootstrap.

Không suy luận “hai data center cách nhau 50 ms thì lag luôn 50 ms”. Cần đo **commit-to-follower-visible latency** và **oldest unreplicated/apply backlog**.

## 4. Sao chép đồng bộ: ACK phụ thuộc bước xác nhận ở bản sao

Trong một thiết kế đồng bộ, write thường **không được xác nhận thành công cho client** cho đến khi một nhóm bản sao hoặc protocol sao chép đạt điều kiện được công bố.

~~~~mermaid
sequenceDiagram
    participant Client
    participant L as Leader
    participant F1 as Follower 1
    participant F2 as Follower 2
    Client->>L: WRITE Order O-901
    L->>L: Record write/log
    L->>F1: Replicate
    L->>F2: Replicate
    F1-->>L: Replica acknowledgment
    L-->>Client: ACK when configured condition met
    F2-->>L: Maybe catches up later
~~~~

Ở ví dụ trên, điều kiện có thể là leader + follower F1, còn F2 được phép chậm. **Đó là đồng bộ tới quorum**, không phải “đợi tất cả replica”.

Các lợi ích có thể có:
- Giảm rủi ro mất write đã ACK khi một node lỗi trong phạm vi fault model.
- Có cơ sở để bầu leader mới mà vẫn giữ những entry đã committed, nếu protocol consensus/quorum được thiết kế đúng.
- Xác định mốc commit rõ hơn cho những write cần độ bền mạnh.

Các đánh đổi:
- **Write latency** có thể phụ thuộc follower/network chậm hoặc ngưỡng quorum.
- Khi thiếu nhóm node cần thiết, **write availability giảm**.
- Phải quản lý membership, leader election, log recovery và khả năng failover.
- Cross-region RTT có thể nằm trên critical path.
- Sync replication không tự làm những read từ cache/index ngoài database trở thành strong.

### 4.1. Đợi tất cả replica khác đợi một quorum

Ví dụ N=3:
- **All-replica ACK:** có thể yêu cầu cả 3 node đạt điều kiện.
- **Majority/quorum ACK:** thường chỉ cần 2/3 trong giao thức majority.
- **Một bản sao remote:** một dạng cấu hình có thể bảo đảm node leader và một follower cụ thể, nhưng không tự tương đương majority consensus khi membership/failover phức tạp.

Nếu F2 bị offline:
- All-replica write có thể phải chờ hoặc thất bại.
- Majority write có thể vẫn hoạt động với L+F1.
- Async-local write có thể phản hồi theo mốc khác nữa.

**Không gọi mọi trường hợp trên là “sync = 3 replica phải xong”**. Hợp đồng cần ghi chính xác số lượng, vị trí và mức xác nhận.

### 4.2. “Replica ACK” là ACK ở lớp nào?

Một follower có thể ACK:
1. Đã nhận message qua network.
2. Đã ghi vào buffer.
3. Đã append vào WAL.
4. Đã làm log durable theo policy.
5. Đã apply vào trạng thái/query storage.
6. Đã publish index/read view.

Các mức này **không tự đồng nghĩa**. Số node ACK không đủ để kết luận một write tồn tại qua sự cố mất điện đồng thời tại các node nếu protocol chưa cam kết durability tương ứng.

### 4.3. Semi-synchronous hoặc hybrid replication

Một số hệ dùng chiến lược lai:
- Đồng bộ với **một bản sao hoặc majority trong vùng**.
- Bất đồng bộ tới những vùng còn lại.
- Đồng bộ log/commit, nhưng apply read model bất đồng bộ.
- Đợi một nhóm node “nhanh nhất đạt yêu cầu”, phần còn lại tiếp tục sau ACK.
- Chỉ một số transaction quan trọng dùng write concern mạnh.

Ví dụ:

~~~~text
Client VN
   |
   v
Leader VN
   |\
   | \-- Sync follower VN (durability/availability in region)
   |
   +---- Async replication to EU and US
~~~~

Hệ có thể bảo đảm write đã ACK không mất nếu **một node VN hỏng** trong fault model, nhưng vẫn có **RPO khác 0 khi mất toàn vùng VN** trước khi EU/US nhận đủ thay đổi.

**Khi nói “synchronous replication”, luôn hỏi đồng bộ tới đâu về mặt địa lý.**

## 5. Một so sánh theo đường ghi, không phải nhãn tốt/xấu

| Thuộc tính | Replication bất đồng bộ | Replication đồng bộ tới nhóm xác định |
| --- | --- | --- |
| Đường ACK | Có thể trả trước khi follower hoàn tất | Thường đợi điều kiện follower/quorum |
| Write latency | Có thể gần local write path | Thường chịu thêm coordination/RTT |
| Follower chậm | Có thể làm lag/backlog tăng | Có thể kéo dài ACK nếu follower nằm trong nhóm cần thiết |
| Khi follower offline | Leader có thể tiếp tục tùy chính sách | Nếu không đủ nhóm yêu cầu, write có thể bị chặn |
| RPO khi leader mất | Có nguy cơ mất những write đã ACK chưa bảo vệ | Có thể thấp hơn hoặc 0 trong fault model được bảo đảm |
| Read tại replica khác | Có thể stale | Vẫn có thể stale nếu replica đó chưa apply hoặc read mode yếu |
| Network partition | Có thể nhận local write ở nhiều phía nếu thiết kế cho phép | Thường chặn một số phía thiếu quorum/authority |
| Conflict resolution | Quan trọng nếu multi-writer | Vẫn cần khi có multi-leader/offline operations |
| Operational cost | Lag monitoring, replay, reconciliation | Leader/quorum, tail latency, membership, recovery |
| Khả năng phục vụ search | Có thể cập nhật index nền | Không tự cập nhật external search ngay |
| Durability | Phụ thuộc WAL/fsync/replica policy | Cũng phụ thuộc mức durable của ACK |

**Sync không có nghĩa luôn an toàn trong mọi tình huống; async không có nghĩa chắc chắn mất dữ liệu.** Phải định nghĩa *loại sự cố* và *mức ACK* trước khi so sánh.

## 6. WAL, fsync và “đã có trên đĩa”

Để hiểu thời điểm xác nhận, cần tách replication khỏi độ bền cục bộ.

Một đường ghi trong nhiều storage engine:

~~~~text
Write request
  -> WAL/commit log append
  -> In-memory state / memtable
  -> ACK according to durability and replication policy
  -> Flush/checkpoint to persistent data files
  -> Compaction/cleanup later
~~~~

**WAL (write-ahead log)** hỗ trợ phục hồi những update chưa được flush thành file dữ liệu chính. Nhưng ngay cả WAL cũng có nhiều mốc:
- Byte đã được ứng dụng ghi vào buffer.
- Byte đã được hệ điều hành nhận.
- Byte đã được yêu cầu flush/fsync theo policy.
- Hạ tầng lưu trữ xác nhận mức persistence mà nó thực sự hỗ trợ.

### 6.1. Buffered write khác durable write

Một node nhận update và giữ trong RAM có thể:
- Trả ACK rất nhanh.
- Mất dữ liệu nếu process/máy mất điện trước khi log được ghi bền.

Một node sync log trước ACK có thể:
- Tăng thời gian ghi.
- Tăng khả năng phục hồi sau crash trong phạm vi của thiết bị và cơ chế lưu trữ.

Nhưng **fsync một node** không cứu được dữ liệu khi cả đĩa/node/zone của nó hỏng vĩnh viễn. Cần xem replication và backup tương ứng.

### 6.2. Replication khác backup

Ba replica không thay thế cho backup:
- Một lệnh DELETE sai có thể được nhân bản tới cả ba.
- Bug ứng dụng có thể ghi dữ liệu hỏng và lan sang mọi replica.
- Malicious write/ransomware có thể ảnh hưởng nhiều bản đồng thời.
- Replication không cung cấp lịch sử để quay về trạng thái trước một lỗi logic.
- Một cấu hình đa vùng vẫn có thể có common-mode failure.

Backup/snapshot, restore drill, PITR nếu có, retention và bảo mật backup là lớp **phục hồi sự cố logic/vận hành**, còn replication chủ yếu hỗ trợ **độ sẵn sàng và chịu lỗi bản sao**.

### 6.3. WAL retention cũng phụ thuộc replica và CDC

Nếu một follower offline hoặc một change-stream consumer chưa bắt kịp, leader có thể phải giữ log cho tới khi follower/consumer đọc được, hoặc áp dụng retention tối đa và buộc follower bootstrap lại.

Lượng log tồn đọng có thể tăng:
- Disk usage.
- Network replay sau sự cố.
- Recovery time.
- Rủi ro mất khả năng resume CDC nếu cursor quá cũ.

**Một ACK thành công hôm nay không bảo đảm mọi consumer phụ trợ có thể bắt kịp mãi mãi nếu log retention bị vượt qua.**

## 7. Quorum: bao nhiêu bản sao cần xác nhận?

Với một nhóm gồm **N** replica, ta thường gặp:
- **W:** số replica cần xác nhận write.
- **R:** số replica tham gia read.

Trong mô hình quorum đơn giản, nếu:

\[
R+W>N
\]

thì hai tập có ít nhất một replica chung, **khi chúng được lấy từ cùng một tập N ổn định**.

Ví dụ N=3, R=2, W=2:

\[
2+2>3
\]

Điều đó hỗ trợ việc xây cơ chế đọc nhìn thấy dữ liệu mới nếu protocol lựa chọn phiên bản/commit đúng.

### 7.1. Vì sao giao nhau chưa đủ chứng minh linearizable?

Một replica chung có thể:
- Đã nhận update nhưng chưa đánh dấu committed.
- Chưa apply đúng phiên bản cho read.
- Trả dữ liệu cũ vì read algorithm không chọn version hợp lệ.
- Thuộc một membership set khác sau reconfiguration.
- Nhận hinted/sloppy write thay cho replica chủ.
- Có concurrent writes với thứ tự chưa thống nhất.

Muốn có **linearizability**, cần giao thức đúng về **định danh write, version/term/ballot, log/leader, commit, read semantics và membership**. Điều kiện R+W>N là trực giác tập hợp, không phải chứng minh toàn bộ.

### 7.2. Majority replication

Trong một protocol majority với N=3:
- Majority = 2.
- Khi một node chết, hai node còn lại **có thể** tiếp tục đạt majority nếu nối được nhau.
- Khi partition thành nhóm 2 và 1, nhóm 1 không đạt majority.

Với N=5:
- Majority = 3.
- Có thể mất hai voting member mà vẫn đủ 3 nếu các node còn lại liên lạc.
- Mất ba voting member thì không còn majority.

Các ví dụ giả định **membership ổn định và protocol có majority decision**. Không tự suy từ số replica lưu dữ liệu sang số voter/acknowledgment cần thiết nếu hệ có node đặc biệt, witnesses hoặc placement policy.

### 7.3. Tính toán khả năng chịu lỗi có điều kiện

Trong majority replication lý tưởng:

\[
f = \left\lfloor\frac{N-1}{2}\right\rfloor
\]

là số voter có thể hỏng mà vẫn còn đủ majority, **nếu những voter còn lại kết nối và tiếp nhận request đúng cách**.

- N=3 → f=1.
- N=5 → f=2.
- N=7 → f=3.

Đây không phải bảo đảm **mọi request luôn thành công khi mất f node**: leader election, routing, storage latency, vị trí node và cấu hình transaction có thể khiến request bị delay/timeout.

### 7.4. Quorum local và quorum toàn vùng khác nhau

Ví dụ một cluster có 3 replica mỗi vùng và ba vùng:
- **LOCAL_QUORUM:** yêu cầu đủ replica trong datacenter/locality mà protocol định nghĩa.
- **Global quorum:** yêu cầu trên phạm vi rộng hơn theo cấu hình.
- **Cross-region consensus:** có thể đặt RTT giữa các vùng lên đường commit.

Tên consistency level cụ thể phụ thuộc engine. Không được xem mọi tên có chữ **QUORUM** là cùng một quorum set hoặc bảo đảm giống nhau.

### 7.5. N=3, W=1 có nghĩa “chắc chắn mất dữ liệu” không?

Không. W=1 biểu thị một mức xác nhận số bản sao theo mô hình đó, **không phải xác suất mất dữ liệu bằng 100%**. Nếu leader sống và background replication nhanh, dữ liệu có thể được nhân bản đầy đủ. Nhưng nếu fault xảy ra đúng trước khi có thêm bản an toàn, rủi ro tồn tại.

Cần nói: **W=1 cho một số cấu hình có cửa sổ dữ liệu đã ACK nhưng chưa được sao chép đủ để chịu lỗi mục tiêu**.

## 8. Leader ACK, majority commit và thời điểm có thể read

Hãy phân biệt ba khái niệm:
1. Một follower **đã nhận entry**.
2. Entry đã **committed** theo consensus/protocol.
3. Follower đã **applied** entry vào state machine/read view.

Trong một nhóm log-replicated state machine, có thể xảy ra:

~~~~text
Leader L:    log entry 42 committed và applied
Follower F1: log entry 42 stored, chưa apply
Follower F2: đang ở entry 41
~~~~

Leader có thể được phép ACK khi commit condition được bảo đảm, nhưng:
- F1 có thể cần thêm thời gian để apply.
- F2 còn tụt lại.
- Search index nhận CDC còn chưa có event.

Một read gửi tới F2 mà không qua giao thức read đúng mức có thể vẫn thấy trạng thái entry 41.

### 8.1. “Write acknowledged” không đồng nghĩa “mọi replica có thể đọc”

Nếu sản phẩm có read preference tới secondary hoặc local replica, cần xác định:
- Có cho phép stale read không?
- Có cơ chế chờ **read-your-writes** không?
- Có session/causal token hoặc commit index requirement không?
- Read có được định tuyến tới leader/quorum đúng protocol không?
- Một secondary đã nhận log nhưng chưa apply có được tính là đủ mới không?

**ACK từ quorum và query visibility ở một replica khác là hai mốc độc lập.**

### 8.2. Một cách giữ read-your-writes

Sau write được ACK với version/commit index 42, client có thể gửi:

~~~~text
READ key K
requireMinVersion = 42
~~~~

Một hệ hỗ trợ session token hợp lệ có thể:
- Chỉ đọc từ replica đã áp dụng ít nhất 42.
- Chờ replica bắt kịp.
- Route đến leader/replica đủ mới.
- Trả temporarily unavailable nếu không đáp ứng.

Token này là ý tưởng kiến trúc, không phải API chung mọi NoSQL. Không tự so một timestamp rời rạc với commit index của cluster khác.

### 8.3. External index có freshness riêng

~~~~text
Source committed v42
    -> Outbox/CDC
    -> Broker
    -> Indexer
    -> Search refresh
    -> Query searchable v42
~~~~

ACK từ source không bảo đảm index đã query-visible. Một search index bất đồng bộ cần **freshness SLO**, đo commit-to-searchable lag, retry và reconciliation; các quyết định như checkout không được phụ thuộc một cách mù quáng vào giá/tồn kho trên search.

## 9. Đọc sau ghi: bốn trường hợp có kết quả khác nhau

Giả sử người dùng vừa cập nhật giá P-42 từ 1.500.000 xuống 1.390.000.

| Đường đọc tiếp | Có thể thấy giá cũ? | Lưu ý |
| --- | --- | --- |
| Đọc authoritative theo mode bảo đảm read-after-write phù hợp | Không, nếu write đã commit và hợp đồng được đáp ứng | Xác định write/read concern, leader/transaction/session |
| Đọc secondary async đang trễ | Có | Độ trễ replica |
| Đọc GSI/search index nền | Có | Index update + refresh lag |
| Đọc cache TTL | Có | Cache invalidation/TTL không tự đi cùng commit |

### 9.1. Đọc mới nhất khác bảo đảm durable

Một cache có thể đã nhận dữ liệu P-42 v18 rất sớm, trong khi source write chưa đủ mức durability yêu cầu. Nếu source mất write do crash theo cấu hình yếu, cache tạm có thể hiển thị một trạng thái không còn trong nguồn sau failover.

Ngược lại, source có thể đã durable nhưng search còn cũ.

Do đó hai câu:
- **Đã bền vững đến đâu?**
- **Đã nhìn thấy ở đường read nào?**

phải được trả lời riêng.

### 9.2. Monotonic reads qua nhiều replica

Một session vừa thấy v18 từ replica A, rồi request kế tiếp đến replica B chỉ có v17:

~~~~text
Read A -> v18
Read B -> v17
~~~~

Nếu API hứa **monotonic reads**, nó phải dùng context/routing để tránh đi lùi. Không phải mọi chế độ đọc eventual đều hứa điều này.

Cần kiểm tra read consistency **theo phiên**, không chỉ mức ACK của write.

## 10. Khi leader hỏng: những timeline phải phân biệt

### 10.1. Crash trước khi write được nhận

~~~~text
T0 Client send WRITE.
T1 Gói tin chưa tới leader.
T2 Network timeout.
~~~~

Không có write được thực thi tại leader đó. Nhưng client chỉ có thể kết luận chắc khi có bằng chứng phù hợp; một timeout chung không tự cho biết gói đã tới hay chưa.

### 10.2. Write mới ở RAM, chưa durable

~~~~text
T0 Leader nhận WRITE.
T1 Cập nhật bộ nhớ.
T2 Chưa đạt WAL/fsync theo yêu cầu.
T3 Node crash.
~~~~

Theo một cấu hình cho phép ACK sớm, có thể mất update. Nếu chưa ACK, client thấy timeout là phù hợp với trạng thái chưa kết luận.

### 10.3. Local durable, chưa nhân bản

~~~~text
T0 Leader fsync local WAL.
T1 ACK cho client theo policy local.
T2 Leader mất cả ổ đĩa/node.
T3 Replica khác chưa nhận write.
~~~~

Local durability không có nghĩa survivability trước mất vĩnh viễn node; nếu không có recovery từ local disk/backup, write có thể mất.

### 10.4. Đã replicate một follower, chưa đạt commit condition

~~~~text
T0 L gửi entry 42 tới F1.
T1 F1 ACK nhận/store.
T2 Chưa đủ quy tắc commit của protocol.
T3 L crash.
~~~~

Entry ở F1 **không nhất thiết đã committed**. Leader mới có thể quyết định lại lịch sử chưa commit theo protocol; không được dựa vào “F1 từng nhìn thấy entry” để khẳng định client write đã commit.

### 10.5. Đã majority-committed rồi ACK mất

~~~~text
T0 Majority đạt commit condition cho OP-101.
T1 Leader gửi ACK.
T2 Mạng mất ACK.
T3 Client timeout.
T4 Client retry OP-101.
~~~~

Trong hệ consensus đúng và fault model phù hợp, entry đã committed được bảo vệ theo contract. Nhưng client **không biết từ timeout**. Retry phải dùng **cùng logical operation ID/transaction identity**, không tạo một ý định mới.

### 10.6. Đã ACK thành công, follower đọc còn cũ

~~~~text
T0 Majority commit v18.
T1 Client nhận ACK.
T2 Client đọc secondary chưa apply v18.
T3 Secondary trả v17 theo mode eventual.
~~~~

Đây có thể là hành vi **hợp lệ của eventual secondary read**, nhưng sẽ vi phạm nếu endpoint hứa mạnh hơn mà vẫn trả v17.

### 10.7. Partition và split brain

Nếu hai phía tách nhau và mỗi phía chấp nhận write xung đột:
- Protocol cần bảo vệ một leader/commit authority hoặc chấp nhận conflict semantics rõ.
- Một leader cũ mất quorum phải bị ngăn xác nhận write không hợp lệ theo hợp đồng.
- **Term/epoch/fencing token** có thể ngăn writer cũ tiếp tục tác động sau khi leadership đổi.

**Replication count không tự ngăn split brain**. Cần leader election/consensus và rules khi network partition.

## 11. Mất ACK: kết quả ghi là UNKNOWN, không phải tự rollback

Một tình huống quan trọng với NoSQL và Java:

~~~~mermaid
sequenceDiagram
    participant App as Java service
    participant DB as NoSQL cluster
    App->>DB: Reserve stock, operationId=OP-101
    DB->>DB: Commit according to write concern
    DB--xApp: Write ACK bị mất
    App-->>App: Timeout = UNKNOWN outcome
~~~~

Từ góc nhìn client, timeout có thể là:
- Request không đến.
- Server reject.
- Server vẫn đang xử lý.
- Server đã commit và ACK bị mất.

Không thể lấy timeout để khẳng định **“không còn effect”**.

### 11.1. Atomic increment vẫn có thể trùng vì retry

~~~~text
Stock=10.

Attempt 1: DECREMENT 1, committed -> stock=9
ACK bị mất.

Attempt 2: DECREMENT 1 bằng operationId mới
-> stock=8

Một ý định mua nhưng đã trừ hai lần.
~~~~

Từng phép decrement có thể nguyên tử, nhưng **không idempotent**.

### 11.2. OperationId và hàng rào chống lặp

Mỗi ý định nghiệp vụ phải có ID ổn định:

~~~~json
{
  "operationId": "OP-101",
  "customerId": "C-42",
  "sku": "BOOK-42",
  "quantity": 1,
  "requestFingerprint": "sha256:..."
}
~~~~

Một thiết kế tốt khi storage hỗ trợ transaction:

~~~~text
BEGIN TRANSACTION
  IF OP-101 đã COMMITTED:
      return prior result

  IF stock >= 1:
      stock := stock - 1
      create reservation RES-901
      save OperationResult OP-101 -> RES-901
      save OutboxEvent ReservationCreated
  ELSE:
      save operation rejection under appropriate contract
COMMIT
~~~~

Nếu ACK mất, retry **cùng OP-101** có thể tra và trả kết quả đã commit. Hai request song song cùng OP-101 phải chịu một **unique/conditional guard**, không chỉ một lần kiểm tra GET trước insert.

### 11.3. Retry commit khác retry toàn transaction

Trong một số database/driver:
- Lỗi trong transaction có nhãn retriable có thể cho phép thử lại toàn transaction theo contract.
- Lỗi **unknown commit result** có thể yêu cầu thử lại **commit trên chính transaction identity**.
- Retry toàn body có side effect ngoài database có thể gây charge/email trùng.

Không giả định một exception SocketTimeoutException ở mọi SDK có cùng ngữ nghĩa. Cần theo hướng dẫn của đúng driver và dùng application idempotency cho những nghiệp vụ quan trọng.

### 11.4. Một read không thấy record chưa đủ kết luận chưa commit

Nếu client timeout rồi đọc qua replica/GSI/search **eventual**, không thấy OP-101 không chứng minh lệnh chưa commit.

Ngay cả một read mạnh từ source không thấy record **tại thời điểm t1** cũng chưa tự chứng minh request đầu sẽ không commit ở **t2 > t1**, nếu request đang in-flight và thiếu hàng rào chặn effect trùng.

**Cách chắc hơn:** retry với **cùng operationId** dưới unique/conditional guard và có cách truy hồi trạng thái kết quả bền vững.

## 12. Tính thời gian xác nhận: local, quorum và cross-region

Giả sử một write gồm:
- 2 ms validation/serialization.
- 3 ms append/apply local.
- 2 ms sync log local.
- 4 ms round-trip giữa các node trong một zone.
- 70 ms round-trip tới một region khác.
- 2 ms protocol/commit bookkeeping.

Nếu đường commit bắt buộc phải chờ một follower trong cùng zone:

\[
T_{\text{ACK}} \approx
T_{\text{local}} + T_{\text{local-replication}} + T_{\text{coordination}}
\]

Một ước lượng minh họa có thể là:

\[
T_{\text{ACK}}\approx(2+3+2)+4+2=13\text{ ms}
\]

Nếu commit bắt buộc chờ một lượt phản hồi từ vùng xa:

\[
T_{\text{ACK}}\approx7+70+2=79\text{ ms}
\]

**Đây là mô hình cực giản**, không phải công thức đúng cho mọi protocol: các bước có thể chạy song song, follower có thể fsync chậm, mạng có nhiều round trip, request có queue, quorum chờ node nhanh thứ k và tail latency không bằng tổng trung bình.

### 12.1. Majority latency phụ thuộc order statistic

Với 3 replica gồm leader + F1 + F2, chỉ cần leader và một follower đạt ACK:
- Nếu F1 phản hồi 4 ms.
- F2 phản hồi 90 ms.

Quorum có thể hoàn tất theo F1, không phải luôn đợi 90 ms, nếu protocol cho phép.

Nhưng nếu F1 hỏng và F2 ở xa, p99 tăng. Khi đặt replica, cần xem **voter placement, network RTT và failover** thay vì chỉ trung bình số node.

### 12.2. Nhiều RTT vẫn có thể cần thiết

Một consensus/transaction protocol có thể cần:
- Leader election và term synchronization.
- Append log.
- Commit index propagation.
- Read barrier.
- Transaction prepare/commit across shards.

Do đó **synchronous replication latency không phải luôn đúng một RTT**. Chọn sản phẩm bằng benchmark trên cấu hình thật.

### 12.3. Pipelining và batching

Ghi nhiều entry theo pipeline/batch có thể giảm overhead mỗi write, tăng throughput. Nhưng:
- Batch lớn có thể tăng latency của write đợi batch.
- Crash/retry phải xử lý operation identity đúng.
- Batch đến follower có thể được apply chậm.
- Không được coi “đã gửi batch” là “từng operation trong batch đã commit”.

## 13. RPO và RTO: diễn giải từ thời điểm ACK

**RPO (Recovery Point Objective)** là giới hạn mất dữ liệu về thời điểm/khối lượng mà doanh nghiệp chấp nhận sau sự cố mục tiêu.

**RTO (Recovery Time Objective)** là thời gian khôi phục dịch vụ mục tiêu.

Một chính sách ghi sync-to-quorum có thể bảo vệ write đã ACK khỏi mất một số node; nhưng điều đó không tự tạo RPO=0 **trước mọi thảm họa**, ví dụ mất toàn bộ region chứa quorum mà vùng khác chỉ nhận async.

### 13.1. RPO theo loại sự cố

| Kịch bản | Lựa chọn cần đánh giá | Nguy cơ |
| --- | --- | --- |
| Mất một process, disk còn | WAL/fsync/recovery của node | Mất in-memory writes chưa durable |
| Mất một node vĩnh viễn | Replica ACK/placement | Mất những write chỉ ở node đó |
| Mất một zone | Replica trải qua zone nào | Một vùng sync trong cùng zone có thể không đủ |
| Mất một region | Cross-region sync hoặc async | Async lag có thể tạo RPO dương |
| Lỗi DELETE hàng loạt | Backup/PITR/audit | Replication lan lỗi nhanh, không sửa |
| Lỗi logic payment double-charge | Idempotency/ledger/reconcile | RPO không phải thước đo duy nhất |
| Search index bị mất | Rebuild từ source/outbox | Tốn thời gian nhưng source có thể an toàn |

Nói “RF=3 nên RPO=0” là thiếu thông tin. Ba bản nằm **cùng một vùng, cùng nguồn điện hoặc cùng ổ hạ tầng** có rủi ro khác ba bản phân tán đúng failure domain.

### 13.2. Ước lượng dữ liệu có thể chưa nhân bản

Giả sử:
- Ingest 20.000 event/s.
- Payload 1 KiB/event.
- Replica cross-region có lag 5 giây tại thời điểm sự cố.

Một ước lượng thô số event chưa đến replica:

\[
20.000\times5=100.000\text{ events}
\]

Payload:

\[
100.000\times1.024=102.400.000\text{ bytes}
\approx97,66\text{ MiB}
\]

Nếu vùng nguồn bị mất và chỉ có replica xa, **có thể có cửa sổ rủi ro** tương ứng khoảng 100.000 event, tùy lag thực tế và ranh giới ACK. Đây không phải con số thiệt hại chắc chắn: có event chưa được ACK, có event đã tồn tại ở nơi khác, có replay từ producer hoặc log bền khác.

### 13.3. Lag p99 không phải cam kết RPO cứng

Nếu monitoring báo **replication lag p99 dưới 2 giây**:
- Vẫn có 1% tình huống trễ hơn mức đó.
- Một outage có thể làm lag tăng vô hạn nếu không có giới hạn.
- Timestamp có thể đo từ eventTime thay vì source commit.
- Có thể thiếu metric cho message bị mất/kẹt.

Muốn đặt RPO yêu cầu, phải đánh giá **worst credible failure**, khả năng replay/backfill và những mốc đã được xác nhận bền vững.

### 13.4. RTO phụ thuộc recovery, không chỉ replication

Một replica có đủ dữ liệu nhưng:
- Phải replay log vài giờ.
- Phải rebuild index.
- Phải đợi leader election.
- Phải validate consistency/repair.
- Phải warm cache.

thì RTO vẫn dài.

Cần kiểm thử **failover end-to-end dưới tải**, không chỉ đếm replica còn sống.

## 14. Async replication lag, backlog và khả năng bắt kịp

Một follower nhận update nhanh 8.000 event/s, nhưng chỉ apply được 6.000 event/s:

\[
R_{\text{backlog}} = R_{\text{produced}} - R_{\text{applied}}
\]

\[
R_{\text{backlog}}=8.000-6.000=2.000\text{ event/s}
\]

Sau 10 phút:

\[
B=2.000\times600=1.200.000\text{ event}
\]

Giả sử nguồn vẫn phát 8.000 event/s nhưng follower được nâng năng lực lên 12.000 event/s:

\[
R_{\text{net-drain}}=12.000-8.000=4.000\text{ event/s}
\]

Thời gian lý tưởng để xử lý backlog:

\[
T_{\text{catch-up}}=\frac{1.200.000}{4.000}=300\text{ giây}=5\text{ phút}
\]

Chưa tính retry, compaction, network, transaction apply và sự cố khác.

### 14.1. Replica đang online không có nghĩa đã bắt kịp

Một follower có TCP connection ổn nhưng có thể:
- Chậm apply.
- Đang replay WAL.
- Lag sau snapshot bootstrap.
- Bị throttle.
- Có log gap cần repair.

Nên đo **source commit index/offset**, **replica received index**, **replica applied index**, **oldest pending age** và **query-visible version** khi engine cho phép.

### 14.2. Backlog tăng dài hạn là vấn đề năng lực

Nếu average apply throughput **thấp hơn tốc độ ghi nguồn** trong trạng thái ổn định, lag sẽ tiếp tục tăng. Tăng retention log chỉ trì hoãn lúc hết dung lượng; không giải quyết bottleneck.

Các lựa chọn:
- Scale CPU/I/O/network của follower.
- Sửa hot shard hoặc index apply bottleneck.
- Tăng parallelism theo key/partition nếu ordering cho phép.
- Batch/compress phù hợp.
- Cân đối maintenance/compaction.
- Tối ưu payload và snapshot bootstrap.
- Giới hạn nguồn hoặc admission control khi hệ có hợp đồng backpressure.

**Không được tự bỏ event để làm lag giảm** nếu pipeline yêu cầu đầy đủ và không có cách đối soát.

### 14.3. Async pipeline có thể mất khả năng resume

Một source chỉ giữ changelog 24 giờ. Nếu follower/indexer offline 30 giờ, checkpoint có thể quá cũ.

Khi đó:
- Không được giả định resume từ offset cũ sẽ luôn được chấp nhận.
- Có thể phải **re-snapshot/backfill** rồi catch-up.
- Cần bảo vệ update tới trong lúc rebuild.
- Phải kiểm tra xóa, tombstone và version để tránh hồi sinh dữ liệu cũ.

## 15. Kết hợp sync source với async read models

Một kiến trúc thực tế thường dùng cả hai:

~~~~mermaid
flowchart TD
    API["Order API"] --> DB[("Authoritative Order DB")]
    DB --> REPL["Synchronous / quorum replicas"]
    DB --> OUT[("Transactional outbox")]
    OUT --> BUS["CDC / event bus"]
    BUS --> IDX[("Search index")]
    BUS --> ANALYTICS[("Analytics projection")]
    BUS --> NOTIFY["Notification worker"]
~~~~

Một lần tạo order:
1. API kiểm tra điều kiện và commit **Order + OperationResult + Outbox** trong phạm vi transaction hỗ trợ.
2. Database ACK khi đã đạt write concern được chọn.
3. Relay phát outbox event.
4. Search/analytics/notification cập nhật sau.

Ở bước 2, **order được xác nhận ở source theo contract** nhưng **không có nghĩa search hoặc email đã xong**. Các bước sau cần:
- Event ID/version.
- Retry và idempotency.
- Lag monitoring.
- Dead-letter và replay.
- Reconciliation.

### 15.1. Dual write không nguyên tử

Flow:

~~~~text
1. Write Order DB -> ACK.
2. Update Search Index -> timeout.
3. API crash.
~~~~

Source đã có order nhưng search thiếu. Nếu không có outbox/CDC bền vững, thay đổi có thể **không bao giờ được áp dụng vào index**.

Dùng **transactional outbox** giúp ghi dấu cần phát cùng transaction source; nhưng relay có thể publish trùng, nên consumer phải idempotent.

### 15.2. Không bắt checkout đợi search index

Một API thanh toán có thể cần:
- Giá/tồn kho có thẩm quyền và ranh giới atomicity.
- Operation ID chống double charge.
- Bảo đảm durability tương ứng.

Nó thường **không cần** chờ search index trở nên searchable để quyết định thành công. Nếu buộc chờ mọi downstream, p99 checkout sẽ bị kéo theo tốc độ hệ thống chậm nhất mà không cải thiện invariant payment.

### 15.3. Hai loại ACK trong hệ thống event-driven

Một service trả:
- **202 ENQUEUED:** event đã được nhận vào một log/queue theo durability policy.
- **201 COMMITTED:** bản ghi nghiệp vụ đã được xác nhận theo authority policy.

Hai kiểu ACK hợp lệ cho **hai hợp đồng API khác nhau**. Không tráo nhãn để giảm latency và rồi báo người dùng rằng order đã hoàn tất khi chỉ mới nhận ý định.

## 16. MongoDB: write concern, replication và read concern

Trong MongoDB, cần phân biệt:
- **Write concern:** mức xác nhận ghi yêu cầu từ database, bao gồm số member nhận ACK theo cấu hình.
- **Journaling:** yêu cầu liên quan tới ghi vào journal theo các tùy chọn/phiên bản.
- **Read concern:** bảo đảm của trạng thái được đọc.
- **Read preference:** chọn primary hay secondary.
- **Transactions/session:** thêm các ranh giới và semantics khác.

Một ví dụ MongoDB Java driver:

~~~~java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public final class OrderWrites {
    private final MongoCollection<Document> orders;

    public OrderWrites(MongoCollection<Document> source) {
        this.orders = source.withWriteConcern(
                WriteConcern.MAJORITY
                        .withJournal(true)
                        .withWTimeout(5, TimeUnit.SECONDS)
        );
    }

    public void insertOrder(String id, String operationId) {
        orders.insertOne(new Document("_id", id)
                .append("operationId", operationId)
                .append("status", "PENDING"));
    }
}
~~~~

Đây là ví dụ cấu hình có chủ đích, không phải khuyến nghị mặc định áp dụng cho mọi workload. Trong thực tế phải xem driver/replica set, WriteConcern error handling, transaction scope và xung đột ID.

### 16.1. W=majority không có nghĩa tất cả secondary đã đọc được

Một write được ACK với majority write concern có thể vẫn chưa được **một secondary khác** nhận/apply. Query với secondary read preference theo mode yếu có thể còn stale.

Để đạt read-your-writes/causal sessions/stronger read semantics, cần read concern, session và đường đọc phù hợp. **Chỉ đặt W=majority không khiến mọi find() toàn cluster đều linearizable.**

### 16.2. W timeout không phải bằng chứng rollback

Nếu write concern timeout, request có thể đã được áp dụng ở primary hoặc một số member nhưng chưa đạt xác nhận mong muốn trong thời gian chờ. Phải phân biệt:
- Lỗi validation hoặc duplicate key được biết rõ.
- Write concern error.
- Network timeout.
- Unknown transaction commit result.

Không coi mọi timeout là **insert chắc chắn chưa tồn tại**. Dùng **operationId/unique key** và tra/retry theo contract.

### 16.3. Journaling và majority có sắc thái phiên bản/cấu hình

Quan hệ giữa majority write concern, journal commit và các tham số của replica set phụ thuộc phiên bản và cấu hình. Muốn nói chính xác “majority ACK bền qua power loss”, phải kiểm tra hợp đồng journaling và storage hiện hành.

**Không dùng một ví dụ code để tuyên bố mọi triển khai MongoDB đều có RPO=0 trước mọi sự cố.**

### 16.4. Change streams không làm index ngoài hệ đồng bộ ngay

MongoDB Change Streams hoặc outbox có thể chuyển thông tin commit tới consumer, nhưng indexer còn phải xử lý và search refresh. Source majority ACK không chứng minh Elasticsearch/OpenSearch đã searchable.

## 17. Cassandra: consistency level và acknowledgement của replica

Cassandra có mô hình sao chép phân tán và cung cấp các **consistency levels** ở mức đọc/ghi.

Một ví dụ (ngữ nghĩa tổng quan, phụ thuộc replication strategy và datacenter layout):

| Consistency level | Trực giác write ACK | Đánh đổi |
| --- | --- | --- |
| **ONE** | Có phản hồi phù hợp từ một replica theo giao thức | Latency/availability theo điều kiện có thể tốt; chưa bảo vệ như quorum |
| **TWO/THREE** | Yêu cầu số replica tương ứng | Cần nhiều phản hồi hơn |
| **QUORUM** | Yêu cầu quorum theo phạm vi được định nghĩa | Có thể giảm khả năng ghi khi thiếu replica |
| **LOCAL_QUORUM** | Quorum trong datacenter/locality tương ứng | Phù hợp một số topology đa DC |
| **EACH_QUORUM** | Dùng cho write với yêu cầu quorum mỗi DC theo cấu hình | Cross-DC availability/latency cần cân nhắc |
| **ALL** | Yêu cầu tất cả replica có liên quan | Một replica unavailable có thể khiến write fail/timeout |

Các tên mức đọc/ghi và mức serial consistency cho **LWT** có ngữ nghĩa riêng, không được gộp tất cả vào một loại.

### 17.1. Cassandra write path khác single-leader consensus

Một replica Cassandra có thể ghi vào commit log và memtable theo giao thức engine, không phải mọi write thường đều chạy Raft/Paxos consensus. **QUORUM trên normal read/write khác lightweight transaction dùng Paxos/LWT.**

Do đó không được nói:
> “Chọn QUORUM nghĩa là mọi nghiệp vụ đa partition tự serializable.”

Consistency level và atomicity/isolation của LWT/transaction là các khía cạnh khác nhau.

### 17.2. Hinted handoff và read repair không đổi nghĩa ACK đã chọn

Một coordinator có thể sử dụng cơ chế **hints** hoặc repair để hỗ trợ replica bị thiếu update bắt kịp theo khả năng cấu hình. Nhưng việc có hint:
- Không tự thay thế replica ACK theo consistency level đã yêu cầu.
- Không bảo đảm mọi stale read được sửa ngay.
- Không có nghĩa dữ liệu chưa được commit vẫn được giữ mãi nếu node chết.
- Không thay thế repair/anti-entropy phù hợp.

**Hint/repair là cơ chế hội tụ và phục hồi**, không phải một lời hứa độc lập rằng mọi thao tác ONE có độ bền tương đương QUORUM.

### 17.3. LOCAL_QUORUM và cross-region RPO

Một ứng dụng ghi thành công ở local datacenter theo LOCAL_QUORUM có thể chưa có đủ bản ở region khác tại thời điểm ACK. Nếu sự cố mất toàn region xảy ra trước khi remote replica bắt kịp, đánh giá RPO phải dựa trên hợp đồng replication của topology đó, không chỉ tên LOCAL_QUORUM.

### 17.4. LWT và unknown outcome

Khi dùng CAS/LWT để giữ một phòng/slot, coordinator có thể timeout sau khi thao tác đã được quyết định theo protocol. Client không được tự lặp thao tác với ID mới rồi nghĩ chưa từng có write.

Cần lưu **operationId/bookingId trong cùng dữ liệu được bảo vệ**, hoặc một ledger phù hợp, để đối soát kết quả.

## 18. Redis: replication ACK không tự đồng nghĩa fsync

Redis thường cung cấp các lệnh nguyên tử trên instance và có replication cùng các cơ chế persistence tùy cấu hình. Khi một client gửi:

~~~~redis
INCRBY views:post-42 1
~~~~

ACK của lệnh có thể phản ánh việc primary đã thực thi lệnh, không có nghĩa replica sẽ được chọn làm primary sau failover chắc chắn đã nhận nó.

Một số Redis API có thể **đợi replica xác nhận đã nhận writes**, ví dụ **WAIT**:

~~~~redis
INCRBY views:post-42 1
WAIT 1 1000
~~~~

Ý nghĩa tổng quát: chờ một số replica ACK replication trong giới hạn thời gian. Nhưng:

- **WAIT không tự biến Redis thành một hệ thống consensus mạnh hoặc giao dịch tuyến tính hóa qua failover.**
- Replica ACK replication không tự bằng đã fsync AOF trên mọi replica.
- Kết quả WAIT có thể cho biết số replica phản hồi ít hơn yêu cầu; ứng dụng phải xử lý, không mặc định thành công.
- Nếu mất kết nối sau INCRBY trước khi client biết kết quả, retry vẫn có thể **đếm trùng**.

Một số phiên bản có những cơ chế liên quan tới **AOF persistence acknowledgment**. Tên lệnh/khả năng phụ thuộc phiên bản; không suy ra bất kỳ triển khai Redis nào đều cung cấp một hợp đồng durability giống database transactional.

### 18.1. Thí dụ counter không idempotent

~~~~text
INCRBY +1 đã thực thi tại primary.
Client timeout trước khi thấy response.
Client gửi lại +1.
Counter có thể tăng hai lần.
~~~~

Cho những tác vụ chính xác, cần operation ID/ledger hoặc một lệnh nguyên tử có guard phù hợp, và cân nhắc Redis có thực sự đáp ứng yêu cầu bền vững/khôi phục của nghiệp vụ không.

### 18.2. Cache khác nguồn có thẩm quyền

Redis cache có thể được phục vụ tốt khi mạng bị chia; một inventory authority ở hệ khác có thể tạm không đạt quorum. Không được dùng **giá trị stock trong cache** để xác nhận bán hàng khi đường authoritative unavailable.

## 19. HBase: WAL, RegionServer và replication cần phân biệt

HBase có mô hình lưu trữ theo region, RegionServer, MemStore, HFile và **WAL** phục vụ phục hồi. Đường ACK của một Put phải được hiểu cùng:
- Durability setting của thao tác.
- Trạng thái WAL và sync.
- RegionServer nào đang sở hữu region.
- Khả năng replay khi region server hỏng.
- HDFS/storage replication.
- Replication bất đồng bộ giữa cluster nếu có cấu hình.

### 19.1. Storage replication và cross-cluster replication không giống nhau

Một Put có thể được phục vụ bởi RegionServer với dữ liệu dựa vào cơ chế HDFS/WAL trong cluster. Bản sao ở **cluster khác** có thể được đồng bộ theo một pipeline riêng, có lag và RPO riêng.

Không nói:
> “HBase có nhiều HDFS replicas nên mọi cluster ở region khác đã đọc được Put ngay.”

### 19.2. Đồng bộ log và hiển thị query

Ngay cả khi WAL đã đạt durability theo policy, search/read model ngoài HBase vẫn có thể xử lý sau. Ngoài ra, region move/recovery có thể ảnh hưởng latency mà không phải là một sự kiện logic “viết hai lần”.

Cần xem API durability, WAL metrics, region transitions, HDFS health và replication lag, thay vì chỉ nhìn thành công của client Put.

## 20. DynamoDB: table, index và multi-region có hợp đồng riêng

DynamoDB là managed NoSQL service; chi tiết vật lý của việc ghi vào replica không được ứng dụng điều khiển giống cụm tự vận hành.

Những điểm cần tách:
- **Write success trên table** theo contract của API.
- **Read consistency** tại table/LSI khi chế độ hỗ trợ.
- **Global Secondary Index (GSI)** được cập nhật bất đồng bộ và có eventual-read semantics.
- **Global tables/các tùy chọn sao chép đa vùng** có những mô hình consistency/replication riêng tùy tính năng và cấu hình.
- **TransactWriteItems/conditional writes** có hợp đồng atomicity và idempotency riêng.

### 20.1. GSI đọc trễ không chứng minh write ở table thất bại

~~~~text
T0 PutItem Products P-42 -> success
T1 Query GSI CategoryPrice -> chưa có P-42
T2 GSI bắt kịp -> có P-42
~~~~

Điều này có thể là **lag của chỉ mục**. Không dùng việc GSI chưa thấy item để retry Put như một ý định mới.

### 20.2. Global tables cần đọc đúng mode đang bật

Không được khẳng định toàn bộ mọi cấu hình global tables đều có cùng multi-region consistency model. Dịch vụ có những lựa chọn/tính năng phụ thuộc thời điểm và cấu hình; cần ghi rõ **đường ghi nào có authority, vùng nào được phép write, cách resolve conflict và contract đọc**.

Với yêu cầu chuyển tiền hoặc giữ stock toàn cầu, chỉ đọc một tài liệu giới thiệu “global replication” chưa đủ; phải đánh giá điều kiện chặn, latency liên vùng và invariant cụ thể.

### 20.3. Conditional write không tự giải quyết retry sau ACK loss

Một UpdateItem với điều kiện available >= qty có thể ngăn âm, nhưng client timeout rồi gửi lại **cùng phép giảm** có thể tiếp tục trừ một lần nữa nếu còn hàng.

Cần operationId/ledger và, khi cần, một transaction bao trùm những bản ghi nghiệp vụ trong giới hạn dịch vụ. **ClientRequestToken** của một API transaction có cửa sổ và điều kiện idempotency riêng; không thay thế mã nghiệp vụ được giữ lâu dài khi cần.

## 21. Đường commit trong Java: tách kết quả server khỏi kết quả quan sát

Một API Java có thể biểu diễn ba trạng thái chính:

~~~~java
public enum WriteOutcome {
    COMMITTED,
    REJECTED,
    UNKNOWN
}

public record WriteResult(
        String operationId,
        WriteOutcome outcome,
        String resourceId,
        String reason
) {}
~~~~

Mục tiêu là **không chuyển TimeoutException thành REJECTED** khi chưa có bằng chứng rollback.

### 21.1. Hợp đồng repository có ý nghĩa

~~~~java
public interface OrderRepository {
    WriteResult createIdempotently(
            String operationId,
            String requestFingerprint,
            OrderCommand command
    );

    WriteResult findOperationResult(
            String operationId
    );
}
~~~~

Đây là interface kiến trúc; **OrderCommand** do ứng dụng định nghĩa. Implementation phải:
- Dùng nguồn dữ liệu có thẩm quyền.
- Ghi order và ledger với ranh giới atomicity phù hợp.
- Có unique/conditional guard theo operationId.
- Chọn write concern đáp ứng rủi ro đã định.
- Không coi read eventual không thấy record là bằng chứng chưa commit.
- Có đường reconcile khi outcome UNKNOWN.

### 21.2. Ví dụ tầng service

~~~~java
public final class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public WriteResult placeOrder(
            String operationId,
            String fingerprint,
            OrderCommand command
    ) {
        try {
            return repository.createIdempotently(
                    operationId, fingerprint, command);
        } catch (TransportTimeoutException ex) {
            return new WriteResult(
                    operationId,
                    WriteOutcome.UNKNOWN,
                    null,
                    "Result not observed; reconcile by operationId");
        }
    }
}
~~~~

Các kiểu **OrderCommand** và **TransportTimeoutException** là ví dụ của application; đoạn code không biên dịch độc lập nếu chưa được định nghĩa. Mấu chốt là một network error không được tự đánh dấu business failure.

### 21.3. Client tạo operationId trước khi gửi request

~~~~text
Client:
  opId = stable identifier of this business intent
  persist opId locally
  send createOrder(opId)

Nếu timeout:
  query status of opId
  retry same opId under idempotency guard
  stop only after bounded retry budget
  keep UNKNOWN/PENDING when unresolved
~~~~

Không tạo ID mới ở mỗi HTTP retry, vì server có thể coi đó là yêu cầu tạo order hoàn toàn mới.

### 21.4. Đừng chỉ thêm retry ở SDK rồi coi đã xong

Có thể có retry ở:
- HTTP client.
- API gateway.
- Service code.
- Database SDK.
- Message broker.
- Scheduled worker.

Các lớp phải chia sẻ **logical operation identity** hoặc bảo đảm idempotent theo phạm vi. Exponential backoff giảm tải nhưng không ngăn hai lần decrement khi ACK đầu tiên mất.

## 22. Đồng bộ ghi không thay thế transaction đa tài liệu

Giả sử một đơn hàng cần:
- Giảm tồn kho.
- Tạo Order.
- Ghi OperationResult.
- Ghi OutboxEvent.

Ngay cả khi **từng write được nhân bản đồng bộ tới majority**, bốn write rời rạc vẫn có thể **commit một phần** khi service crash giữa chừng.

~~~~text
1. Inventory decrement -> majority ACK.
2. Insert order -> timeout/crash.
3. Ledger chưa ghi.
4. Outbox chưa ghi.
~~~~

Replication chỉ nói về **bản sao của những write đã được thực hiện**, không tự gộp bốn write thành một transaction.

Nếu engine hỗ trợ transaction đủ phạm vi:

~~~~text
BEGIN
  Conditional inventory reserve
  Insert Order
  Insert OperationResult
  Insert OutboxEvent
COMMIT
~~~~

Cần đồng thời xét:
- Transaction atomicity.
- Isolation chống concurrent oversell.
- Commit durability/replication.
- Unknown commit result.
- Read-your-writes sau commit.
- External payment/email side effects.

**Đừng dùng write concern mạnh để bù cho thiếu transaction**, hoặc dùng transaction để giả định data đã nhân bản tới mọi vùng.

## 23. Tác động đến p99, throughput và headroom

### 23.1. Đường sync thêm dependency vào latency

Nếu write ACK phải đợi một follower:
- Follower disk I/O chậm có thể làm p99 tăng.
- Network burst làm queue tăng.
- Leader quorum membership đổi khiến replica cần đợi khác trước.
- Compaction/GC trên follower có thể làm apply/sync latency cao.

Đường async ít phụ thuộc follower trên critical path, nhưng:
- Queue/log tích tụ.
- Replica read freshness giảm.
- Recovery RTO có thể tăng.
- RPO ở sự cố mục tiêu có thể xấu hơn.

**Đổi ACK latency lấy replication lag và rủi ro khôi phục là một đánh đổi cần đo**, không phải công thức “sync tốn đúng 2 lần thời gian”.

### 23.2. Cross-region network bandwidth

Giả sử source ingest payload **50 MiB/s** và phải gửi một bản đầy đủ sang hai region khác:

~~~~text
Source payload throughput: 50 MiB/s
Replication copy to EU:    ~50 MiB/s
Replication copy to US:    ~50 MiB/s
Aggregate outbound data:  ~100 MiB/s
~~~~

Đó chỉ là payload minh họa, chưa tính compression, logs, protocol overhead, retries và cách engine phân phối thực tế.

Nếu đường mạng ổn định chỉ xử lý **70 MiB/s**, queue có thể tăng nếu không nén/batch/scale và nếu source tiếp tục 100 MiB/s outbound. Con số trung bình cần xét với burst, QoS và lỗi mạng.

### 23.3. Replication lag không tương đương consumer apply lag

Các mốc:

~~~~text
source committed
  -> event emitted
  -> follower received
  -> follower durable/appended
  -> follower applied
  -> follower query-visible
~~~~

Nếu một metric chỉ là **network replication lag** nhưng apply queue đang nghẽn, người dùng vẫn có thể đọc dữ liệu cũ. Cần đo đúng mốc phù hợp với read path.

### 23.4. Dung lượng của log và snapshot

Follower chậm có thể khiến source phải giữ nhiều log. Khi bootstrap replica mới, hệ có thể truyền một snapshot lớn và sau đó replay log:
- Disk read bandwidth tăng.
- Network cạnh tranh với foreground requests.
- CPU nén/giải nén tăng.
- Thời gian đạt quorum sau thay node kéo dài.
- Headroom cho compaction/log/snapshot có thể giảm.

Một thiết kế tốt xét **steady state và recovery burst**, không chỉ một benchmark lúc cluster khỏe.

## 24. Dashboard quan sát đúng ACK và replication

Một dashboard nên đặt các nhóm metric cùng trục thời gian:

| Nhóm | Metric cần tìm | Câu hỏi |
| --- | --- | --- |
| Write ACK | p50/p95/p99 DB write latency theo concern | Những write đã được ACK nhanh hay chậm? |
| Rejected/unknown | Timeouts, write concern errors, unknown outcomes | Có thao tác chưa biết đã commit không? |
| Quorum | Healthy voters, reachable replicas, quorum availability | Nhóm nào đủ điều kiện commit? |
| Leader | Term/epoch, election duration, step-down events | Có failover, split-brain risk không? |
| Log | Durable/commit/applied index; WAL/fsync latency | Replica đạt mốc nào? |
| Replication | Source-to-replica receive/apply lag | Bản sao nào tụt lại? |
| Freshness | Commit-to-query-visible p99 theo read path | Người đọc thấy giá trị mới sau bao lâu? |
| Backlog | Pending bytes/events, oldest pending age | Pipeline có theo kịp không? |
| Storage | Disk free, IOPS, throughput, queue, compaction | I/O nền có gây trễ? |
| Network | RTT/packet loss/bandwidth theo link | Có partition hay congestion? |
| Recovery | Replica bootstrap time, log replay, restore RTO | Sau lỗi bao lâu đạt trạng thái an toàn? |
| Durability | RPO thực đo trong drill, retained ACKed writes | Những ghi đã xác nhận có còn không? |
| Business | Duplicate order/debit, negative stock, reconciliation | Bảo đảm nghiệp vụ có bị vi phạm? |

### 24.1. Không dùng một metric “replication delay” chung

Cần chỉ rõ:
- Replica nào, shard nào, region nào.
- Delay từ **source commit** hay từ eventTime phía client.
- Lag receive, durable, apply hay searchable.
- Có bao gồm event chưa xử lý/mất không.
- Metric là mean, p99 hay oldest pending.
- Nếu node restart thì counter/offset reset thế nào.

Hai vùng có “lag 50 ms” có thể đang báo hai khái niệm khác nhau, không thể so trực tiếp.

### 24.2. Synthetic probe đo từ write đến read

Một probe minh họa:

~~~~text
1. Tạo key duy nhất K và version V.
2. Write K=V với consistency/durability mode xác định.
3. Ghi nhận thời điểm ACK hoặc commit.
4. Read từ replica/region/index cần kiểm tra.
5. Chỉ coi "visible" khi query thật thấy đúng V hoặc mới hơn.
6. Ghi latency, timeout và số lần read stale.
~~~~

Nếu đang đo **read-your-writes**, probe phải mang session context/đường đọc đúng. Với update DELETE, phải kiểm tra việc item biến mất khỏi query, không chỉ read theo ID.

Một probe thành công không chứng minh toàn bộ hệ đã đồng bộ; cần nhiều key/shard/zone và fault scenarios.

## 25. Benchmark đồng bộ và bất đồng bộ có đối chứng

Benchmark cần cùng dataset, số replica, failure domains, offered workload và read/write distribution. Không thể so **sync trong một zone** với **async qua ba region** rồi kết luận sự khác biệt hoàn toàn do sync/async.

### 25.1. Thí nghiệm nhiều giai đoạn

1. **Healthy baseline:** đo write p99, read p99, lag, throughput và durability policy.
2. **Follower slow:** giảm I/O/network của một follower trong môi trường thử.
3. **Follower down:** kiểm tra nhóm nào vẫn đạt write ACK.
4. **Network partition:** chia những node còn sống; ghi lịch sử thao tác.
5. **Leader failure:** kill leader trước/sau commit trong môi trường test.
6. **ACK loss:** chặn phản hồi sau khi database commit để thử UNKNOWN/idempotency.
7. **Recovery:** đưa replica trở lại và đo catch-up, headroom, conflict resolution.
8. **Rebalance/rebuild:** đo performance khi replica phải copy snapshot + replay log.
9. **Repeat:** chạy lại với cấu hình khác và cùng seed/offered load.

### 25.2. Ma trận workload

| Kịch bản | Biến thay đổi | Điều phải đo |
| --- | --- | --- |
| ONE/local ACK | Write concern yếu hơn trong hợp đồng cho phép | Latency, lost ACK recovery, RPO |
| Quorum ACK | Yêu cầu nhiều replica | p99, availability, committed history |
| All-replica ACK | Tất cả replica cần phản hồi | Tác động follower chậm/offline |
| Async remote replica | Xa vùng nhưng không nằm trên ACK path | Cross-region lag, RPO/RTO |
| Sync remote replica | Remote nằm trên đường ACK | RTT, throughput và p99 |
| Minority partition | Node còn sống nhưng không đủ quorum | Rejection vs stale read theo mode |
| Leader failover | Leadership đổi trong tải | No lost committed writes trong contract |
| Follower apply backlog | Apply rate thấp hơn ingest | Queue growth và catch-up |
| WAL fsync slow | Tăng durable log latency | ACK p99, stalls |
| Indexer paused | Search không bắt kịp | Source durable vs query-visible |
| Lost ACK | Client timeout sau commit | Retry idempotent không duplicate |
| Restore snapshot | Phục hồi một bản cũ | RPO, replay và reconciliation |
| Mixed read modes | Primary/secondary/search | Read-your-writes và stale-read frequency |
| Cross-shard transaction | Ghi nhiều item | Atomicity, commit p99 và unknown outcome |

### 25.3. Đặc tả benchmark minh họa

~~~~yaml
experiment: sync-async-replication-write-ack
topology:
  regions: [VN, EU, US]
  replicasPerShard: 3
  shardCount: 32
workload:
  offeredWritesPerSecond: 10000
  offeredReadsPerSecond: 30000
  operations:
    - insert_order_with_operation_id
    - conditional_reserve_inventory
    - point_lookup
    - read_after_write
    - query_search_index
ackModes:
  - local_contract
  - quorum_contract
  - all_replicas_if_supported
  - cross_region_if_supported
failureScenarios:
  - healthy
  - slow_follower
  - leader_crash_before_commit
  - leader_crash_after_commit
  - lost_commit_ack
  - minority_partition
  - cross_region_link_down
  - recovery_catch_up
measure:
  - write_ack_p50_p95_p99
  - write_concern_errors
  - unknown_operation_count_and_age
  - source_to_replica_receive_apply_lag
  - commit_to_read_visible_lag
  - acknowledged_writes_preserved_after_failure
  - replica_log_gap_and_replay_time
  - backlog_bytes_and_oldest_age
  - quorum_available_ratio
  - p99_read_and_write_per_region
  - network_disk_cpu_headroom
  - business_invariant_violations
~~~~

Đây là **mẫu thiết kế thử nghiệm**, không phải cấu hình benchmark chạy trực tiếp. Nhiều managed service không cho bật mọi ack mode hoặc can thiệp network giữa replica; chỉ đo và gây lỗi trong phạm vi sản phẩm/môi trường cho phép.

### 25.4. Kết quả giả định

| Mode/kịch bản | p99 ACK | p99 remote read staleness | Write success ở minority | Điểm cần đọc |
| --- | ---: | ---: | --- | --- |
| Local ACK, healthy | 18 ms | 1,5 s | Tùy protocol | Latency thấp, remote lag |
| Majority cùng zone, healthy | 35 ms | 1,3 s | Có thể không | Local durability/quorum mạnh hơn |
| Cross-region quorum, healthy | 160 ms | 0,8 s trên đường read cụ thể | Có thể không | RTT trên ACK path |
| All-replica ACK, một follower mất | Timeout/reject | Không xác định | Có thể không | Availability giảm |
| Async remote link down | 20 ms | Tăng theo outage | Tùy protocol | Remote RPO/backlog tăng |
| Quorum leader failover | p99 tạm tăng mạnh | Phụ thuộc read routing | Theo quorum | Kiểm tra retained committed writes |

**Số liệu giả định để minh họa cách đọc**, không phải giới hạn của engine. Không thể suy từ p99 ACK rằng read đã query-visible trên mọi replica; cũng không thể từ bảng này kết luận một mode luôn tốt nhất.

## 26. Fault injection: test ACK rơi đúng lúc khó

### 26.1. Những sự cố phải kiểm tra

| Thời điểm lỗi | Có thể quan sát | Bằng chứng cần kiểm tra |
| --- | --- | --- |
| Trước khi leader nhận write | Client timeout | Không suy ra trạng thái nếu không có tracing/guard |
| Sau in-memory update, trước durability | Node crash | Khôi phục theo ACK/durability contract |
| Sau local durable, trước replication | Mất node | RPO với node loss |
| Sau follower receive, trước quorum commit | Leader crash | Entry chưa commit xử lý đúng protocol |
| Sau quorum commit, trước client ACK | Client UNKNOWN | Same-op retry không duplicate |
| Sau ACK, trước follower apply | Stale secondary read | Đường đọc phải đúng consistency mode |
| Network partition sau một write | Strong read trên minority | Không trả stale dưới nhãn strong |
| Leader election hai phía | Hai vùng tự nghĩ mình là leader | Fencing/term ngăn double commit |
| Replica restart từ snapshot cũ | Cần log replay | Không mất entry committed |
| Log retention vượt khi replica offline | Resume fail | Snapshot bootstrap/reconcile |
| Search index outage | Source write thành công | Search lag không làm sai checkout |
| Multi-region disaster | Mất vùng source | RPO theo cross-region contract |
| Client retry +1 | ACK lost rồi gửi lại | Idempotency xử lý non-idempotent op |
| Cross-shard partial workflow | Một write commit, write khác lỗi | Transaction/saga đúng trạng thái |

### 26.2. Ghi history theo operation ID

Mỗi write/read trong test cần:
- operationId.
- Key/shard/region.
- Invoke và return time với thứ tự đáng tin.
- Read/write concern yêu cầu.
- Result success/rejected/timeout/unknown.
- Version/commit index nếu được công bố.
- Leader term/epoch và replica offsets nếu có.
- Ràng buộc nghiệp vụ mong đợi.

Sau test:
1. Đối soát những write **đã ACK** với dữ liệu sau failover theo durability contract.
2. Tìm operation UNKNOWN và xác định trạng thái cuối bằng ledger.
3. Kiểm tra không có duplicate booking/decrement.
4. Kiểm tra strong read histories theo model được hứa.
5. Đo recovery time, lag và remaining backlog.

**Không coi mọi timeout là failed write khi xây lịch sử kiểm chứng**; một operation timeout có thể thực sự commit.

### 26.3. Test phải giữ đúng phạm vi bảo đảm

Nếu sản phẩm hứa **RPO=0 cho mất một node** nhưng không hứa mất toàn region, đừng lấy region disaster rồi nói phát hiện bug của hợp đồng mất một node. Ngược lại, nếu business yêu cầu survive mất vùng với RPO=0, cấu hình chỉ bảo vệ một node **không đáp ứng yêu cầu**, dù engine vận hành đúng như thiết kế.

## 27. Runbook: ghi thành công nhưng replica không thấy dữ liệu

Khi có báo cáo “Order API thành công nhưng EU chưa thấy đơn”, hãy phân loại trước khi sửa.

### Bước 1 — Xác minh nguồn

- OperationId/bookingId chính xác là gì?
- Write được ACK với write concern nào?
- Source/leader có bản ghi đã commit không?
- Có unknown commit hoặc write concern timeout không?
- Có transaction/ledger và outbox cùng commit không?

### Bước 2 — Xác định đường đọc gây vấn đề

- EU đọc authoritative DB, follower, GSI, cache hay search?
- Đường read có hứa strong, causal, RYW hay eventual?
- Replica đã **received, durably stored, applied hay query-visible** tới mốc nào?
- Có clock skew khiến số đo lag sai không?

### Bước 3 — Tìm nghẽn replication

- Network link, packet loss, throughput, queue depth?
- Follower CPU/disk IO/compaction?
- Missing log segment hoặc snapshot bootstrap?
- Leader failover/membership/quorum biến động?
- Backlog tăng hay đang rút?

### Bước 4 — Bảo vệ thao tác nhạy cảm

- Checkout phải kiểm tra giá/tồn kho ở authority với conditional guard.
- Nếu commit outcome UNKNOWN, giữ operationId và reconcile.
- Không tạo order mới chỉ vì search ở EU không thấy.
- Với quyền truy cập, không dựa vào policy replica cũ nếu chính sách yêu cầu mạnh.
- Không force failover hoặc bỏ quorum chỉ để có HTTP 200.

### Bước 5 — Khôi phục

- Sửa đường replication/consumer và capacity bottleneck.
- Nếu log gap quá retention, bootstrap/reconcile theo công cụ được hỗ trợ.
- Kiểm tra tombstone/delete và event version trước replay.
- Giảm retry storm, limit bulk backfill nếu cạnh tranh với API.
- Theo dõi lag, backlog, p99 và số operation UNKNOWN tới khi ổn định.

### Bước 6 — Xác nhận

- Write đã ACK trong fault model còn nguyên.
- Read mode phù hợp không trả stale trái hợp đồng.
- Replica/region query-visible đạt freshness SLO.
- Không phát sinh duplicate debit/order.
- RPO/RTO đo thực phù hợp mục tiêu.
- Dashboard phân biệt nguyên nhân DB replication và index downstream.

## 28. Những nhầm lẫn cần tránh

1. **“Write ACK nghĩa là mọi replica đã có dữ liệu.”** Không nếu chỉ yêu cầu local/quorum ACK.
2. **“Sao chép đồng bộ nghĩa là đợi tất cả node.”** Có thể chỉ đồng bộ tới một nhóm/quorum.
3. **“Một follower ACK nghĩa là đã fsync.”** Phải đọc định nghĩa ACK của protocol.
4. **“Đã fsync local là an toàn khi mất cả region.”** Không nếu remote không có bản sao an toàn.
5. **“Async replica luôn mất dữ liệu.”** Không; đó là rủi ro tùy timing/fault model.
6. **“Sync replication đảm bảo không bao giờ mất dữ liệu.”** Không trước mọi sự cố logic, hạ tầng và cấu hình.
7. **“Quorum ACK là linearizable cho mọi API.”** Cần protocol/read path/membership đúng.
8. **“R+W>N là chứng minh đầy đủ nhất quán mạnh.”** Giao tập hợp chưa đủ.
9. **“W=majority nghĩa là mọi secondary đã apply.”** Không nhất thiết.
10. **“Follower online nghĩa là đã catch up.”** Có thể lag receive/apply.
11. **“Search index không thấy write nghĩa DB chưa commit.”** Index bất đồng bộ có visibility lag.
12. **“Replica lag 1 giây nghĩa RPO chắc chắn tối đa 1 giây.”** Lag là chỉ số đo, không phải bảo đảm cứng.
13. **“Replication thay backup.”** Xóa sai/bug được nhân bản; cần backup/PITR.
14. **“WAL append là WAL fsync.”** Không tự đồng nghĩa.
15. **“HTTP 202 nghĩa order committed.”** Có thể chỉ đã enqueue intent.
16. **“Timeout nghĩa rollback.”** Commit ACK có thể bị mất.
17. **“Retry nguyên tử +1 không gây đếm trùng.”** Atomic increment không idempotent.
18. **“Mỗi bản sao đều ở vùng khác vì RF=3.”** Cần kiểm tra placement.
19. **“Local quorum bảo đảm không mất vùng.”** Remote RPO cần tính riêng.
20. **“Chọn ALL luôn tốt nhất.”** Một replica lỗi có thể làm write availability thấp.
21. **“Chọn ONE luôn nhanh nhất trong mọi trường hợp.”** Phụ thuộc topology, cache, contention, protocol.
22. **“Replication đồng bộ bao gồm payment và email.”** Không ngoài transaction/protocol bao trùm.
23. **“Follower chậm chỉ ảnh hưởng follower.”** Nếu follower nằm trên ACK path, p99 nguồn có thể tăng.
24. **“Tăng log retention giải quyết lag mãi mãi.”** Nếu apply chậm hơn ingest, backlog vẫn tăng.
25. **“Leader failover xong là RTO đạt.”** Cần test read correctness, catch-up và traffic.
26. **“Số replica nhiều hơn luôn giảm latency.”** Có thể tăng coordination/cost theo policy.
27. **“Không có packet loss thì không còn đánh đổi.”** PACELC latency/consistency vẫn quan trọng.
28. **“Cassandra QUORUM và MongoDB majority là cùng một giao thức.”** Cơ chế khác, không suy ngang.
29. **“Redis WAIT là fsync/consensus.”** Chờ replication acknowledgement không tự có nghĩa persistence toàn cục.
30. **“Index query-visible là bằng chứng commit durability.”** Visibility và durable storage là hai chiều.
31. **“Có transaction là khỏi cần operationId.”** Retry sau mất ACK vẫn có thể mơ hồ ở phía client.
32. **“Thấy backlog về 0 chứng minh không mất event.”** Cần đối soát offsets/IDs và correctness.

## 29. Bài tập tình huống: đơn hàng nhiều vùng

Một hệ thương mại điện tử dùng Java 21 và NoSQL có:
- Vùng VN là điểm chính cho checkout; EU/US phục vụ người dùng ở xa.
- **10.000 order writes/s** ở giờ cao điểm.
- Payload log trung bình **2 KiB/operation** trước nén và overhead.
- Mỗi shard có **3 bản sao** đặt theo chiến lược failure domains.
- Search index cập nhật bất đồng bộ.
- Có thể chọn local ACK, majority ACK hoặc cross-region ACK theo các khả năng của nền tảng.
- Client deadline 3 giây, retry tự động có backoff.
- Inventory phải không âm và mỗi **operationId** chỉ được giữ stock đúng một lần.
- SLO read p99 dưới 200 ms cho listing; checkout cần giữ dữ liệu đúng theo invariant.
- Business yêu cầu nêu RPO cho **mất một node** và **mất toàn vùng VN**.

### Phần A — Vẽ timeline xác nhận ghi

Vẽ đường:
1. Client gửi write.
2. Leader nhận.
3. WAL append.
4. Local durable milestone.
5. Follower 1 nhận/ack.
6. Follower 2 nhận/ack.
7. Protocol quyết định commit.
8. Server gửi ACK, client nhận.
9. Secondary read/search index nhìn thấy write.

Đánh dấu **mốc nào** của từng ACK mode và tại sao không thể mặc định T5/T6/T9 đồng thời.

### Phần B — Quorum

Với N=3, majority=2:
- Khi một node lỗi và hai node còn kết nối, write có thể tiếp tục không?
- Khi network chia 2–1, phía nào đủ majority?
- Nếu một node ở thiểu số vẫn trả stale read, đó là read mode nào?
- Tại sao một majority write đã ACK không chứng minh mọi GSI/search index có ngay kết quả?
- Tại sao quorum intersection chưa chứng minh toàn bộ transaction đa item là serializable?

### Phần C — RPO theo vùng

Giả sử ingest 10.000 write/s, mỗi write 2 KiB và remote replication lag 8 giây đúng lúc mất VN.

1. Tính số operation có thể còn trong cửa sổ chưa nhân bản: **10.000 × 8 = 80.000 operation**.
2. Tính payload tương ứng: **80.000 × 2 KiB = 160.000 KiB ≈ 156,25 MiB** trước overhead.
3. Giải thích vì sao đây là ước lượng rủi ro, không phải số write chắc chắn mất.
4. Mô tả chiến lược nào có thể giảm RPO remote và chi phí ACK latency tương ứng.
5. Nếu vùng VN chết nhưng majority voter đều ở VN, liệu “majority ACK” tự bảo vệ mất vùng không?

### Phần D — Tính backlog

Nguồn phát 10.000 event/s; replica EU chỉ apply 7.000 event/s trong 20 phút.

1. Backlog tăng bao nhiêu event?
2. Nếu tăng apply throughput lên 16.000 event/s mà nguồn giữ 10.000 event/s, bao lâu để rút hết backlog trong mô hình lý tưởng?
3. Nếu changelog giữ 30 phút và replica outage 45 phút, cần phương án recovery nào?

**Gợi ý:** Backlog **(10.000−7.000)×1.200 = 3.600.000 event**. Net drain **6.000 event/s**, thời gian lý tưởng **600 giây = 10 phút**.

### Phần E — Mất ACK và retry

Operation **OP-101** đã commit reserve stock, ACK bị mất. Java client timeout và chuẩn bị retry.

- Vì sao retry với OP-102 sai?
- Thiết kế **OperationResult/unique guard** nào để OP-101 chỉ reserve một lần?
- Nếu read từ search ở EU chưa thấy OP-101, có được kết luận chưa commit không?
- Khi chưa xác minh được, UI nên hiển thị CONFIRMED, REJECTED hay UNKNOWN/PENDING?

### Phần F — Sync/async theo endpoint

Đề xuất contract cho:
- Search listing.
- Price detail.
- Checkout reserve.
- Payment.
- Audit event ingestion.
- Analytics dashboard.

Với từng endpoint, ghi **đường read/write, ACK milestone, freshness SLO, RPO mong muốn, hành vi khi partition/follower lỗi**. Giải thích vì sao không cần chọn một mode cho toàn bộ hệ.

### Phần G — Fault injection

Thiết kế test:
1. Leader crash trước WAL sync.
2. Leader crash sau local ACK nhưng trước remote replication.
3. Leader crash sau majority commit nhưng trước client ACK.
4. Follower đã nhận log nhưng chưa apply.
5. Cross-region link down 5 phút.
6. Một follower có disk I/O chậm.
7. Network partition 2–1.
8. Search indexer dừng 15 phút.
9. Client retry một decrement không idempotent.
10. Replica bootstrap từ snapshot cũ.

Với từng test, xác định **write concern**, response đã quan sát, source truth sau recovery, rủi ro RPO, độ trễ, kết quả kỳ vọng và phương án đối soát.

### Phần H — Java client và runbook

Xây interface repository trả **COMMITTED / REJECTED / UNKNOWN**. Đảm bảo operationId không đổi giữa retry. Viết runbook trả lời:

> “Khách đặt hàng thấy timeout, 30 giây sau search ở EU vẫn không có order, nhưng email đã được gửi.”

Cần tra ở đâu để biết order đã commit? Email có chứng minh order được ACK bền không? Có nên tạo order thứ hai không? Phải làm gì khi search index/replica EU chậm?

### Hướng giải

Một thiết kế hợp lý có thể:
- Xác nhận checkout từ **nguồn có thẩm quyền** với atomic/conditional reserve và write concern đáp ứng rủi ro mất node mong muốn.
- Dùng **operationId bền vững** để chống double reserve khi ACK bị mất.
- Phân biệt **local/majority/cross-region** khi đặt RPO cho mất vùng.
- Đồng bộ search/analytics qua **outbox/CDC bất đồng bộ** và đo freshness riêng.
- Không cho phép stale search trực tiếp quyết định cấp phát.
- Trong partition, giữ safety bằng cách báo **PENDING/UNKNOWN hoặc tạm từ chối** khi không có điều kiện xác nhận.
- Test thật leader failover, replica lag, mất ACK và recovery trong môi trường thử.

## 30. Các câu hỏi trước khi chọn thời điểm ACK

Trước khi đưa một cấu hình replication vào production, nên trả lời rõ:

1. **Thao tác nào cần bảo vệ?** Một item, nhiều item hay cả workflow?
2. **ACK xảy ra sau bước nào?** Received, WAL append, fsync, quorum commit hay apply?
3. **Replica ACK xác nhận nhận log hay durability?**
4. **Cần bao nhiêu node/voter?** Tập quorum được xác định thế nào?
5. **Replica nằm ở failure domain nào?** Host, rack, zone hay region?
6. **Leader crash sau ACK có giữ write trong fault model mục tiêu không?**
7. **Read sau ACK tới đâu?** Primary, secondary, GSI, search, cache?
8. **Có yêu cầu read-your-writes hay linearizable read không?**
9. **Nếu ACK mất, client tra/retry bằng operationId nào?**
10. **Nếu thiếu quorum, API sẽ chờ, từ chối hay nhận intent cục bộ?**
11. **Sync cross-region tăng p99 bao nhiêu trong benchmark thật?**
12. **Async remote RPO/RTO thực tế bao nhiêu?**
13. **Lag metric đo receive, durable, apply hay searchable?**
14. **Log retention đủ cho outage và bootstrap dự kiến không?**
15. **Có chống duplicate event/counter decrement khi retry không?**
16. **Có transaction/outbox khi một nghiệp vụ ghi nhiều bản ghi không?**
17. **Có backup/restore/PITR cho lỗi logic không?**
18. **Có thử mất node, mất zone, mất region và lost ACK không?**
19. **Có monitor leader term, quorum health và write concern errors không?**
20. **Hành vi trong partition được công bố trung thực tới người dùng không?**

**Kết luận:** **Sao chép đồng bộ và bất đồng bộ khác nhau chủ yếu ở điều kiện phải hoàn tất trước khi một write được xác nhận**, nhưng **mốc ACK còn chịu ảnh hưởng của WAL/fsync, quorum/consensus, topology, transaction và chính sách durability**. ACK có thể xác nhận write tại một node, một quorum hoặc một phạm vi vùng, nhưng không tự chứng minh **mọi replica đã apply, mọi search index đã query-visible hoặc dữ liệu sống sót qua mọi loại thảm họa**. Với NoSQL phân tán, hãy định nghĩa write concern theo **failure domain và RPO**, read consistency theo **đường truy vấn thật**, cùng **operationId/idempotency** để xử lý timeout chưa biết kết quả. Sau đó kiểm chứng bằng **replica lag, p99, quorum availability, failover, crash recovery và những bất biến nghiệp vụ**, thay vì chỉ ghi cấu hình là “sync” hoặc “async”.
