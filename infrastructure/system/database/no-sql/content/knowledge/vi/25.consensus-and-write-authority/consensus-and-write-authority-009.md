# Thành viên cụm, thay đổi cấu hình và rủi ro chuyển tiếp trong NoSQL

## 1. Vì sao thêm một node có thể làm hệ thống khó ghi hơn?

Một hệ lưu trữ NoSQL có ba thành viên bỏ phiếu `A`, `B`, `C`. Đội vận hành chuẩn bị tăng quy mô cụm bằng cách thêm hai node `D` và `E`.

```text
Trước:

           +-------+
           |   A   | leader
           +---+---+
               |
          +----+----+
          |         |
      +---v---+ +---v---+
      |   B   | |   C   |
      +-------+ +-------+

       3 voters, majority = 2

Sau:

       A     B     C     D     E
       |     |     |     |     |
       +-----+-----+-----+-----+

       5 voters, majority = 3
```

Điều dễ bỏ qua: **tăng số thành viên bỏ phiếu không tự động tăng khả năng phục vụ ngay**. Nếu `D`, `E` chưa đồng bộ, kết nối chập chờn hoặc cấu hình thay đổi sai thứ tự, hệ có thể gặp timeout, election lại nhiều lần hoặc mất quorum tạm thời.

Một tình huống nghiêm trọng hơn xuất hiện khi mạng bị chia cắt đúng lúc thay đổi:

```text
                         NETWORK PARTITION

       A, B, C        X        C?, D, E
  (old configuration)      (new configuration)

       Ai có quyền bầu leader?
       Majority nào được dùng để xác nhận write?
       Hai nhóm có thể cùng trả COMMITTED không?
```

Nếu mỗi phía tự dùng một cấu hình khác nhau mà không có giao thức chuyển tiếp an toàn, hệ có thể tạo **hai nguồn quyền ghi**. Khi kết nối trở lại, không thể đơn giản chọn bên có timestamp mới hơn để coi mọi ACK đều đúng.

Trong chương **Đồng thuận và quyền ghi** của NoSQL, thay đổi thành viên cụm (*membership reconfiguration*) là một bài toán **đồng thuận về ai được tham gia quyết định đồng thuận**. Nó liên quan đến election, quorum, log, durability, routing và chính sách trả kết quả cho client; không chỉ là thêm IP vào danh sách server.

## 2. Mục tiêu học tập và phạm vi

Sau bài này, người học cần phân biệt được:

1. **Membership vật lý, membership bỏ phiếu và replication placement**.
2. **Quorum cũ, quorum mới** và rủi ro hai nhóm không thống nhất cấu hình.
3. **Safe reconfiguration**, ví dụ joint consensus hoặc quy trình đổi một voter mỗi lần theo protocol được hỗ trợ.
4. Vai trò của **learner/non-voting member, log catch-up, leader term, epoch và fencing**.
5. Tác động của thêm/xóa/đổi thành viên đối với **write ACK, khả năng phục vụ và read consistency**.
6. Rủi ro khi **network partition, crash, failover, restore, rolling upgrade hoặc mất coordinator** trong lúc chuyển đổi.
7. Cách quan sát, thử nghiệm và viết runbook để thay cấu hình mà không phá bất biến nghiệp vụ.

Không phải tất cả database NoSQL sử dụng cùng thuật toán. Bài viết sẽ dùng **Raft-style consensus** để giải thích những nguyên tắc an toàn, rồi chỉ ra các mô hình khác như MongoDB replica set, Redis Cluster/Sentinel, Cassandra/ScyllaDB, Elasticsearch và dịch vụ managed. Không được áp nguyên xi thuật toán hoặc lệnh của một sản phẩm cho sản phẩm khác.

## 3. “Thành viên cụm” không phải một khái niệm duy nhất

### 3.1. Node vật lý

Một máy/instance/process đang chạy. Nó có thể đã tồn tại và mở port nhưng **chưa được tham gia bỏ phiếu** hay nhận dữ liệu.

### 3.2. Voting member

Node có quyền tham gia quyết định leader, cấu hình hoặc commit theo giao thức đồng thuận cụ thể. Một thành viên bỏ phiếu **không nhất thiết** giữ toàn bộ dữ liệu application; ví dụ arbiter trong một số hệ có chức năng bỏ phiếu nhưng không giữ bản sao dữ liệu phục vụ đọc như data-bearing member.

### 3.3. Data-bearing replica

Node lưu dữ liệu/log và có thể tham gia replication. Một replica có thể không bỏ phiếu hoặc không đủ điều kiện làm leader cho tới khi bắt kịp.

### 3.4. Learner / non-voting member

Node được thêm để **nhận log, snapshot, đồng bộ và chứng minh sẵn sàng** trước khi trở thành voter. Cơ chế learner được hỗ trợ ở một số hệ dùng Raft; không phải mọi NoSQL có một loại member tên đúng như vậy.

### 3.5. Observer / read replica

Một bản sao có thể phục vụ read hoặc chỉ giám sát, nhưng không quyết định quorum ghi. Quyền đọc dữ liệu mới nhất phụ thuộc vào read protocol, không phải việc node “có bản copy”.

### 3.6. Shard owner / partition replica

Node chịu trách nhiệm một **phần keyspace**. Một cluster có thể có nhiều nhóm replica; thay membership của một nhóm không tự thay toàn bộ cluster.

### 3.7. Routing/control-plane member

Một thành phần lưu **cluster metadata** hoặc điều phối shard ownership. Nó có thể dùng một nhóm đồng thuận riêng với nhóm lưu dữ liệu. Khi control plane mất quorum, một số data-plane reads có thể vẫn chạy qua metadata cache; nhưng thay đổi cấu hình, placement hoặc quyền sở hữu mới có thể bị chặn.

### So sánh nhanh

| Khái niệm | Tham gia election? | Lưu dữ liệu? | Tự quyết định write? |
|---|---|---|---|
| Voting data replica | Tùy protocol, thường có | Có | Chỉ theo giao thức/leader/quorum |
| Learner / non-voter | Không, trước khi promote | Thường có log/data | Không có quyền vote commit như voter |
| Arbiter/witness | Có trong hệ hỗ trợ | Không như replica dữ liệu đầy đủ | Không thay thế durable data replica |
| Read replica | Có thể không | Có | Thường không độc lập xác nhận authoritative writes |
| Shard router | Không nhất thiết | Chủ yếu metadata/cache | Route, không thay thế storage consensus |
| Node vừa chạy lại | Theo membership hiện hành | Có thể giữ state cũ | Chỉ khi được xác nhận đúng epoch/role |

**Quan trọng:** “Có 5 máy” khác “có 5 voters”, và “5 voters” lại khác “5 bản sao dữ liệu đủ điều kiện xác nhận durability”.

## 4. Quorum và quyền ghi: các con số nền tảng

Trong một nhóm đồng thuận có \(N\) voting members với majority:

\[
Q(N) = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

| Voters \(N\) | Majority \(Q\) | Số voter có thể mất tối đa mà nhóm vẫn có majority |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

Các con số giả định **một nhóm majority-voting** và các voter còn lại có thể liên lạc, đủ điều kiện phục vụ. Chúng **không** bao gồm khả năng một node còn sống nhưng lag quá xa, bị từ chối vote, hoặc môi trường không có network connectivity cần thiết.

### Vì sao hai majority giao nhau?

Với cùng một tập \(N\) members, mọi hai tập có số phần tử lớn hơn \(N/2\) đều giao nhau ít nhất một member.

Ví dụ \(N=3\):

```text
Quorum 1: {A, B}
Quorum 2: {B, C}
Intersection: {B}
```

Sự giao nhau cho phép giao thức đồng thuận dùng log/term/vote rules để bảo vệ lịch sử đã commit. **Quorum overlap một mình chưa đủ**: node giao nhau còn phải tuân thủ quy tắc vote, log freshness và commit của protocol.

### Thêm voter có thể tăng majority ngay khi node chưa sẵn sàng

Từ 3 lên 4 voters:

```text
Old: {A, B, C}; majority 2
New: {A, B, C, D}; majority 3
```

Nếu D vừa thêm nhưng không nhận được message, nhóm A+B vẫn chỉ có **2/4**, không thể đáp ứng majority mới. Trước thay đổi, A+B đủ **2/3**.

Đó là lý do nhiều hệ khuyến nghị **thêm non-voting/learner trước, để catch-up và kiểm tra sức khỏe rồi mới promote**, hoặc thao tác theo quy trình reconfiguration được hỗ trợ.

### Thành viên chẵn không phải luôn “sai”, nhưng cần hiểu trade-off

Từ 3 lên 4 voters không tăng số voter có thể mất đồng thời (vẫn chỉ 1), trong khi quorum tăng từ 2 lên 3. Từ 4 lên 5 thì tolerance tăng từ 1 lên 2. Con số **không nói gì về data-bearing/arbiter, địa lý và failure domains**; thêm node ở cùng một máy/rack có thể không cải thiện khả năng chịu một sự cố chung.

## 5. Membership thay đổi từ một cấu hình có commit sang cấu hình khác

Giả sử:

```text
C_old = {A, B, C}
C_new = {C, D, E}
```

Đây không chỉ là việc cập nhật danh sách IP từ:

```json
{"members": ["A", "B", "C"]}
```

sang:

```json
{"members": ["C", "D", "E"]}
```

Vấn đề: **ai xác nhận rằng cấu hình mới đã có hiệu lực?** Nếu nhóm A+B vẫn được phép commit theo \(C_{old}\), còn D+E lại commit theo \(C_{new}\), hai majority này:

```text
Old majority: {A, B}
New majority: {D, E}

Intersection: empty
```

Hai phía có thể cam kết hai lịch sử xung đột nếu không có quy tắc chuyển tiếp an toàn. Việc **hai cấu hình toàn phần có chung C** không tự loại trừ hai majority **không giao nhau**.

### Hai bất biến phải giữ

1. **Election safety:** trong một term/epoch hợp lệ, không có hai leader cùng được protocol chấp nhận như leader có quyền commit những thay đổi mâu thuẫn.
2. **Committed-history safety:** những operation đã commit hợp lệ theo giao thức không bị một cấu hình khác làm mất chỉ vì membership đổi.

Các thuật toán khác nhau có thể có chi tiết chứng minh khác nhau. Ứng dụng không thể thay phép chứng minh đó bằng “lúc bình thường chúng tôi chỉ thấy một leader”.

## 6. Reconfiguration không an toàn: cập nhật danh sách node thủ công

Xét một triển khai giả định không có protocol chuyển membership:

```text
T0: A,B,C đang chạy old config, A là leader.
T1: admin cập nhật file config của D,E,C thành new config.
T2: mạng chia A,B | C,D,E.
T3: A+B tự cho rằng old quorum 2/3 -> commit x=1.
T4: D+E tự cho rằng new quorum 2/3 -> commit x=2.
T5: mạng nối lại.
```

Nếu cả hai write đều được trả `COMMITTED` cho các client, lịch sử có thể không thể giải thích như một quyền ghi duy nhất của cùng object.

**Lỗi nằm ở chính thao tác thay membership ngoài đồng thuận.** Không thể sửa một cách đúng đắn bằng cách so timestamp:

```text
x=1 @ 10:00:01.001
x=2 @ 10:00:01.002
```

Đồng hồ có thể lệch; quan trọng hơn, cả hai ACK đã được hứa theo những authority không tương thích. LWW có thể làm dữ liệu hội tụ nhưng không làm các lời xác nhận trước đó trở nên hợp lệ theo một mô hình linearizable.

### Vì sao deploy tuần tự vẫn chưa đủ?

Deploy A rồi B rồi C rồi D rồi E chỉ tránh việc tất cả process khởi động cùng lúc. Nếu logic membership thực tế vẫn được áp dụng **không thông qua giao thức chuyển cấu hình**, các member có thể đồng thời có những quan điểm khác nhau về quorum.

**Phải dùng membership API/quy trình của engine**, không tự thay file config độc lập rồi hy vọng rolling deployment giải quyết toàn bộ.

## 7. Joint consensus: một cách chuyển cấu hình an toàn

Một cách thường được giải thích trong **Raft** là *joint consensus*. Trong giai đoạn chuyển tiếp, hệ sử dụng cấu hình chung:

\[
C_{joint}=(C_{old}, C_{new})
\]

Một quyết định cần được chấp nhận theo **majority của cấu hình cũ lẫn majority của cấu hình mới**, theo các điều kiện commit/vote cụ thể của giao thức.

Ví dụ:

```text
C_old = {A,B,C}          majority = 2
C_new = {C,D,E}          majority = 2

Joint config:
  need >=2 votes/acks from {A,B,C}
  AND  >=2 votes/acks from {C,D,E}

Valid joint quorum example: {A,B,C,D}
  old votes: A,B,C => 3 >= 2
  new votes: C,D   => 2 >= 2
```

Giai đoạn joint có thể chứa node thuộc cả cấu hình cũ và mới, nhưng **không được hiểu** rằng mỗi phía tự nhận một majority riêng rồi commit độc lập. Các quyết định đều phải đi qua **quy tắc chung**.

### Các pha khái niệm

```text
Configuration C_old
       |
       | commit transition into joint configuration
       v
Configuration C_old,new
       |
       | quorum includes majorities of old AND new
       | finish log synchronization / transfer authority
       v
Configuration C_new
       |
       v
Only new configuration authorizes future decisions
```

### Joint consensus bảo vệ điều gì?

- Một majority cũ không thể tự ý commit đối nghịch với một quyết định được xác nhận theo joint.
- Một majority mới chưa được phép hoạt động như cấu hình cuối khi quá trình chuyển tiếp chưa commit.
- Khi cấu hình mới được áp dụng hợp lệ, lịch sử được bảo vệ phải được mang theo theo các quy tắc log của consensus.

### Chi phí availability trong transition

Nếu kết nối giữa nhóm cũ và nhóm mới bị đứt, có thể **không đủ cả hai majority**, khiến transition không thể hoàn tất. Đây là đánh đổi để không có hai authority độc lập.

Đừng diễn giải “không thể tiếp tục thêm node” như một lỗi consistency. Đôi khi **tạm dừng write/config change là hành vi an toàn**.

### Có phải mọi hệ Raft đều dùng đúng joint consensus?

Không. Có giao thức hiện thực **thay đổi một voting member tại một thời điểm** kèm điều kiện đảm bảo an toàn, hoặc biến thể membership khác. Chỉ mô tả joint consensus như **một phương pháp phổ biến để giải thích nguyên lý**, không gán tự động cho mọi engine.

## 8. Thay đổi từng voter và vì sao thứ tự rất quan trọng

Một số triển khai dựa trên consensus có quy trình thay đổi membership từng bước, thay vì chuyển đồng thời một cấu hình lớn:

```text
Old: A B C
Add D as learner/non-voter
Catch up D
Promote D (if protocol permits)
Remove A (if desired)
...
```

### Tại sao thường không thêm nhiều voter chưa sẵn sàng một lúc?

Giả sử old 3 voters A/B/C, cả D/E bị chặn network nhưng được tính thành voter:

```text
New voters A,B,C,D,E
Majority = 3

If A and B remain online only:
  2/5 < 3 => cannot commit
```

Trước khi thêm, A+B là majority 2/3. Tự nâng quorum bằng những node không sẵn sàng có thể **làm giảm khả năng ghi**, dù mục tiêu ban đầu là tăng resilience.

### Không tự tạo quy tắc “chỉ thay một voter là luôn an toàn”

Việc thay từng voter an toàn **khi đi qua giao thức/điều kiện commit của implementation**. Nếu admin thay đổi danh sách voter bằng cấu hình rời rạc mà mỗi node tự áp, ngay cả một thay đổi cũng có thể tạo thời điểm các node bất đồng quorum.

“Một lần một member” là **thực hành vận hành** hỗ trợ giảm rủi ro; safety cuối cùng thuộc về **reconfiguration protocol** của engine.

## 9. Learner và non-voting member: đồng bộ trước khi bỏ phiếu

Một learner thường có:

```text
Role: LEARNER
Can replicate log/snapshot: YES
Can vote in election: NO
Can be leader: NO
Can count toward voter majority: NO
```

### Quy trình minh họa

1. Tạo node mới `D` và thiết lập kết nối xác thực/tài nguyên.
2. Thêm D vào nhóm với vai trò **learner/non-voter**, nếu engine hỗ trợ.
3. Snapshot/log catch-up tới một mốc phù hợp.
4. Quan sát `received`, `durable`, `applied` và error rate.
5. Kiểm tra D có thể giữ tốc độ replication ổn định trong tải thực tế.
6. Promote D thành voter **bằng membership API có tính đồng thuận**.
7. Xác minh quorum/election sau promote, không chỉ nhìn D báo healthy.

### Vì sao snapshot 100% chưa chứng minh đã sẵn sàng?

```text
Leader committed position: 12,080
D snapshot applied:        11,500
D log received:            12,080
D log durable:             12,000
D log applied:             11,940
```

D đã nhận log tới 12.080 nhưng **chưa apply** toàn bộ và có thể chưa đáp ứng read hoặc leader eligibility. Tùy giao thức, điều kiện được promote không chỉ là một ngưỡng lag tĩnh; phải theo **readiness tiêu chuẩn của engine**.

### Learner quá chậm cũng có chi phí

- Snapshot chiếm I/O/network của leader.
- Replay backlog có thể tăng nhanh hơn tốc độ apply.
- Log retention bị áp lực; learner có thể cần snapshot lại.
- Một learner hỏng không nên bị coi là voter đã sẵn sàng để tăng fault tolerance.

Không promote chỉ vì “đã chạy process và trả ping”.

## 10. Bỏ member cũ: dễ hơn thêm member không?

Không nhất thiết. Bỏ một node có thể làm thay đổi quorum, khả năng election và durability của data copies.

Giả sử cụm:

```text
A,B,C voters (majority 2)
Remove C -> A,B voters (majority 2)
```

Sau khi remove C, A và B **đều phải còn sẵn sàng** để nhóm hai voter đáp ứng majority. Trước đó có thể mất một node; sau đó mất một trong hai là không còn quorum. Việc giảm từ 3 xuống 2 members có thể làm hệ **kém chịu lỗi hơn**.

### Khi member bị remove vẫn còn chạy

Một node C bị xóa khỏi membership có thể:

- Vẫn chạy process.
- Vẫn có snapshot/log dữ liệu cũ.
- Vẫn nhận request do app giữ địa chỉ cũ.
- Vẫn tự nghĩ mình là leader nếu metadata stale hoặc cấu hình thay đổi không đúng.

Nó phải bị **fence** khỏi quyền vote/commit thuộc cấu hình mới. Nếu ứng dụng được phép truy cập trực tiếp một process cũ và chấp nhận local write, tầng app có thể tạo dữ liệu nằm ngoài authoritative history.

### Cleanup không nên đến trước commit removal

Không xóa dữ liệu của C hoặc hủy disk ngay khi thao tác remove vừa được **khởi tạo**. Phải xác minh cấu hình mới đã commit và những replica còn lại đạt độ bền/khả năng phục hồi mong muốn.

Khi rollback cần phân biệt **add C lại như một member theo protocol** với việc bật lại process giữ state cũ; không tự khôi phục quyền ghi bằng cách sửa file.

## 11. Thay leader và thành viên: hai thay đổi khác nhau

### Leadership transfer

Chuyển vai trò leader từ A sang B khi membership vẫn giữ nguyên:

```text
Members: A,B,C
Before:  leader=A
After:   leader=B
```

### Membership reconfiguration

Thay tập voters/data replicas:

```text
Before: {A,B,C}
After:  {B,C,D}
```

Hai thao tác có thể xảy ra gần nhau nhưng **không được đánh đồng**. Một người vận hành muốn loại A cần cân nhắc chuyển leader sang node đủ điều kiện, nhưng **chuyển leader xong không tự xóa A khỏi membership**.

### Chuyển leader trước khi remove leader cũ

Một quy trình thường thuận lợi là:

1. Đảm bảo B có log đủ mới và là ứng viên leader hợp lệ.
2. Sử dụng API leadership transfer phù hợp.
3. Xác nhận leader mới và trạng thái commit.
4. Reconfigure để remove A theo protocol.

Chi tiết tính sẵn sàng và cách điều phối có thể khác; **không tự ép step-down/kill leader production** khi chưa biết API và quorum.

## 12. Term, epoch, config version và quyền ghi

Một số giao thức dùng:

- `term`: nhiệm kỳ leader/election.
- `configVersion`: phiên bản membership.
- `epoch`: generation của authority/routing hoặc nhóm replica.
- `commitIndex`: vị trí log đã commit.
- `logIndex`: vị trí một entry trong log.

Ví dụ:

```text
Current config:
  configVersion=42
  voters=A,B,C,D,E
  leader=B
  leaderTerm=19
  committedIndex=12,080

Old isolated node:
  configVersion=41
  voters=A,B,C
  leader=A?
  leaderTerm=18
  appliedIndex=12,050
```

Node A không được coi là authoritative chỉ vì nó tự báo `leader=true`. Phải đánh giá theo **membership/term/commit protocol đã được cluster chấp nhận**.

### Fencing của leader cũ

Khi B trở thành leader hợp lệ ở term 19, các write thuộc authority term 18 không được tiếp tục commit độc lập nếu sẽ xung đột với lịch sử mới.

```text
Client -> old A: WRITE x=1
A checks leadership validity / quorum
If no valid authority:
  reject / retry-later / redirect
```

Trong một số hệ, leader cũ chỉ biết nó đã mất quyền sau khi nhận thông điệp hoặc khi quorum lease hết hạn. Client/driver cần tránh tin mù quáng vào một endpoint cố định; an toàn dựa vào protocol server chứ không chỉ router.

### Epoch ứng dụng không tự thay consensus term

Ứng dụng có thể thêm version trên document để CAS hoặc cấp fencing token cho lease. Điều đó hữu ích, nhưng **không thay thế term/config membership do consensus layer bảo vệ**.

## 13. Split-brain trong lúc chuyển membership

“Split-brain” thường được dùng khi nhiều phía cùng hành xử như authority của một dữ liệu.

Ví dụ:

```text
Network partition:

Left: A,B believe old config {A,B,C}
Right: C,D,E believe new config {C,D,E}

Left accepts reservation(A12)=U1
Right accepts reservation(A12)=U2

Both return CONFIRMED
```

Nếu cả hai ACK có cùng ý nghĩa **xác nhận độc quyền**, hệ đã tạo một sự kiện nghiệp vụ không thể dễ dàng giải bằng chọn last timestamp.

### Hạn chế quan trọng

**Một giao thức majority consensus được cài đặt đúng** không cho hai bên cùng commit lịch sử xung đột trong phạm vi bảo đảm của nó, dù một node cũ có thể còn tự tin sai về vai trò. Ví dụ trên minh họa **reconfiguration sai/bypass protocol**, không phải hành vi bình thường mà Raft/Paxos được thiết kế chấp nhận.

### Vì sao cần phân biệt “primary tưởng mình còn quyền” với “write committed”?

Một primary cũ có thể nhận một local write trước khi nhận ra mình bị cô lập, nhưng write đó **chưa đạt điều kiện commit**. Nếu client dùng ACK yếu hoặc trực tiếp bypass protocol, ứng dụng có thể tưởng đã thành công. Phải kiểm tra **điểm ACK/commit** chứ không chỉ xem process vẫn nhận TCP request.

## 14. Rủi ro với ACK và durability khi membership đổi

Một write trải qua các mốc:

```text
Client sends W
    |
    v
Leader receives W
    |
    v
Log appended locally
    |
    v
Required quorum / commit condition satisfied
    |
    v
Write committed by protocol
    |
    v
Client receives ACK
```

Đây là mô hình khái niệm. Một số engine có thêm fsync/journal, apply và writeConcern khác nhau; **ACK không phải lúc nào là “quorum commit”**.

### Write chưa commit có thể bị mất

```text
A leader appends W at index 501
B,C chưa nhận/commit W
A isolated
B,C elect new leader
```

Nếu W chỉ nằm trong log chưa commit ở A, giao thức có thể loại hoặc thay W theo lịch sử được chọn. Đừng coi đây là mất write đã **commit bền theo quorum**; trước hết phải xác định ACK nào đã trả cho client.

### Một data-less voter có thể giúp bầu leader nhưng không lưu dữ liệu

Ví dụ replica set có:

```text
Data-bearing: A, B
Arbiter: C
Election voters: A, B, C
```

C có thể bỏ phiếu trong election nhưng không chứa document/log dữ liệu như B. **Majority votes trong election không mặc nhiên là majority data replicas đã giữ một write**. Vì vậy không suy từ “3 votes có majority” thành “write đã có hai bản sao dữ liệu bền”.

### Thay member và RPO

Nếu loại B (bản sao dữ liệu quan trọng) và giữ A+C (arbiter), số bản sao dữ liệu có thể giảm dù số voters trông vẫn đủ. Recovery Point Objective phụ thuộc **mức write ACK, persistence, replica placement và failure domains**, không chỉ số member hiển thị trên dashboard.

## 15. Network partition đúng lúc reconfiguration

Một ma trận giúp phân biệt:

| Giai đoạn | Lỗi mạng | Hành vi an toàn cần tìm |
|---|---|---|
| Trước thay đổi | Old quorum còn | Tiếp tục theo cấu hình cũ |
| Learner catch-up | New node mất kết nối | Giữ learner non-voting; không promote mù |
| Joint transition | Old majority có, new majority không | Transition/write theo joint có thể chờ; không bỏ qua một bên |
| Joint transition | Hai phía nhìn config khác nhau | Tuân thủ commit/vote rules; không tự công nhận config riêng |
| Final config commit | Leader mất ACK tới admin | Kiểm tra trạng thái config đã commit, không tạo một config mới tùy tiện |
| Sau commit new config | Old nodes vẫn chạy | Fence old authority; redirect hoặc remove theo protocol |
| Cleanup | Replica cần log bị mất | Resnapshot/recover từ authority; không dùng stale copy làm leader |

### “Không có phản hồi” không phải luôn “đổi cấu hình thất bại”

Admin gửi lệnh reconfigure, cluster commit cấu hình mới, nhưng network làm mất response:

```text
Admin -> cluster: remove A, config version 42
Cluster -> commit version 42
ACK bị mất
Admin -> timeout
```

Chạy lại mù quáng một lệnh khác có thể thay đổi cluster theo ý định không còn phù hợp. Cần đọc **membership đã được commit**, đối chiếu operation/config version và sử dụng API retry/idempotency được hỗ trợ.

### Không “force” chỉ vì đang timeout

Một số engine có thao tác ép reconfigure hoặc phục hồi quorum trong tình huống đặc biệt. Nó có thể bỏ qua một phần quy trình an toàn thông thường hoặc mang rủi ro rollback/divergence. Chỉ dùng theo **runbook khôi phục được tài liệu chính thức cho phép**, sau khi biết nguồn dữ liệu có thẩm quyền và chấp nhận rõ rủi ro.

## 16. Placement theo failure domain khi tăng member

Một cluster 5 voters nhưng cả 5 nằm trên cùng host hoặc cùng rack **không chịu được lỗi host/rack đó**.

### Ví dụ bố trí chưa tốt

```text
AZ-1: A, B, C, D, E
AZ-2: none
AZ-3: none
```

Nếu AZ-1 mất, không còn majority.

### Ví dụ phân bổ có chủ đích

```text
AZ-1: A, B
AZ-2: C, D
AZ-3: E

5 voting members, majority=3
```

Trong sơ đồ trên, mất một AZ có 2 voters vẫn còn 3, đủ majority nếu các thành viên còn lại liên lạc/đủ điều kiện. Nhưng đừng khẳng định mô hình này có thể chịu **mọi tổ hợp hai AZ**; mất AZ-1 và AZ-2 đồng thời chỉ còn 1 voter.

### Latency và quorum đặt trên WAN

Nếu voters trải nhiều region, majority communication có thể tăng độ trễ commit/election. Đồng thời một partition liên vùng có thể khiến một phía không đủ majority để phục vụ write mạnh.

**Thêm vùng địa lý không tự động “giải CAP”.** Cần cân bằng:

- Chịu lỗi AZ/region.
- Latency p95/p99 của write.
- Chi phí WAN.
- Rủi ro network partition.
- Data residency và quyền truy cập.
- Kiểu workload đọc/ghi, phân tán key.

## 17. Voter count, data replica count và shard RF khác nhau

Một NoSQL cluster có thể có:

```text
Cluster control plane: 3 voters
Shard group ORDERS-1: 3 data replicas
Shard group ORDERS-2: 5 data replicas
Read cache: 6 nodes
Search index: 4 shards x 2 replicas
```

Thêm một node vào cluster không nhất thiết làm **mỗi shard có thêm một voter**, cũng không nhất thiết thay **replication factor (RF)** của mọi phân vùng.

Các chỉ số:

- **Membership của consensus group nào?**
- **Voting quorum của group đó?**
- **RF của data partition nào?**
- **Số bản sao đã bắt kịp?**
- **Read/write consistency level của request nào?**

Nếu không phân biệt các tầng này, một bản thiết kế có thể cho rằng “cụm 5 node cho phép mất 2 node” trong khi một shard chỉ có RF=2, hoặc cả hai bản sao của key nằm trên hai node sẽ mất cùng lúc.

## 18. Control plane mất quorum, data plane sẽ thế nào?

Một số kiến trúc dùng metadata cluster để quản lý:

- Shard routing.
- Placement/ownership.
- Membership và leader election.
- Schema/index lifecycle.
- Rebalance/reshard.

Nếu control plane không có quorum:

- Có thể **không commit được thay đổi metadata**, không thêm/xóa node hoặc phân lại shard.
- Các route/leader đã được biết có thể **tiếp tục phục vụ một số request** nếu data plane còn đủ authority và giao thức cho phép.
- Những đường cần quyết định authority mới có thể bị chặn.

Không có quy tắc chung rằng “metadata cluster down thì mọi GET đều down” hoặc “GET vẫn chạy nên write cũng chắc chắn an toàn”. Cần hiểu kiến trúc cụ thể và xem request nào cần control-plane decision.

### Cẩn thận stale metadata

App A giữ route `range R -> shard S1` ở epoch 41, trong khi authority đã chuyển `R -> S3` ở epoch 42. Server cũ phải **redirect/fence**. Nếu app có quyền gửi write local bypass shard router, metadata cache cũ có thể dẫn tới write ngoài authoritative history.

Membership consensus và shard ownership chuyển tiếp **liên quan nhưng không phải một loại reconfiguration duy nhất**.

## 19. MongoDB replica set: election, voting members và reconfig

MongoDB replica set có member roles, election và tùy chọn cấu hình như `votes`, `priority`, arbiter, hidden/delayed secondary trong phạm vi được tài liệu từng phiên bản hỗ trợ.

### Các câu hỏi khi thêm member

- Member mới là **data-bearing secondary** hay **arbiter**?
- Member có **votes=0/priority=0** trong giai đoạn đồng bộ không?
- Primary có còn majority voters để phục vụ ghi theo write concern cần thiết?
- Oplog window có đủ cho member mới initial sync/catch-up?
- Disk/network/CPU của primary có chịu thêm traffic initial sync không?
- Member mới có được eligible làm primary khi đã đủ dữ liệu không?

### Ví dụ quan sát trạng thái

Trong `mongosh`, trên môi trường có quyền phù hợp:

```javascript
rs.conf();
rs.status();
rs.printSecondaryReplicationInfo();
```

Các lệnh giúp quan sát cấu hình/roles/replication theo deployment và phiên bản; chúng **không phải proof rằng mọi write đã bền hay mọi member sẵn sàng election**.

### Staging một secondary không bỏ phiếu

Một mẫu được sử dụng khi phù hợp là thêm member mới dưới dạng **non-voting, non-electable**, cho đồng bộ trước khi cân nhắc thay cấu hình vote:

```javascript
// Ví dụ minh họa trên môi trường lab; tên host giả.
rs.add({
  host: "db4.example.test:27017",
  votes: 0,
  priority: 0
});
```

Để member trở thành voter, phải dùng cơ chế `rs.reconfig`/API chính thức theo giới hạn phiên bản và quy tắc của MongoDB, không sửa tay config local. Trước mọi thay đổi live, kiểm tra tài liệu version đang chạy; không áp đoạn này mù quáng cho production.

### Arbiter không làm data replica bắt kịp

Nếu có A (primary), B (secondary), C (arbiter), C có vote nhưng không giữ data copy như B. Khi B mất, A+C có thể tạo majority election votes, nhưng điều đó **không làm write mới có thêm một bản sao dữ liệu**. Các write concern có điều kiện acknowledgement riêng; tránh suy từ voter majority sang data durability.

### Forced reconfiguration

Những thao tác **force reconfig** có rủi ro đặc biệt khi cluster đang partition/không có quorum. Có thể xuất hiện lịch sử chưa được đa số lưu bền, rollback hoặc divergent config tùy tình huống. Chỉ thực hiện theo hướng dẫn disaster recovery chính thức và khi đã phân tích dữ liệu đã ACK.

## 20. etcd/Raft như ví dụ rõ về quorum membership

etcd là một distributed key-value store dùng Raft, thường dùng làm **control-plane metadata store** trong hệ thống hạ tầng. Nó giúp minh họa:

- Add/remove members qua API membership được đồng thuận.
- Khái niệm voting members và **learner** trong các phiên bản hỗ trợ.
- Việc tăng kích thước cluster làm đổi majority.
- Yêu cầu quorum để commit và điều phối leader.

### Tình huống 3 -> 4 voters

```text
Old voters: A, B, C     majority=2
Add D as voting member  majority=3

D not responding
B also down

Remaining A,C = 2/4
=> No majority
```

Nếu D được thêm dưới dạng learner rồi catch-up trước khi promote, hệ có thời gian kiểm tra trạng thái và giảm nguy cơ nâng quorum khi một node chưa thật sự có khả năng phục vụ.

### Không tùy tiện restore từ snapshot rồi tự nhập cụm

Một node được dựng lại bằng snapshot cũ có thể giữ **cluster ID/member ID/raft log metadata** không tương thích với cluster đang chạy. Khôi phục theo quy trình chính thức thường phân biệt **member replacement**, **snapshot restore**, **force-new-cluster/recovery** và quá trình rejoin. Không dùng dữ liệu cũ để tự bầu ra một leader ngoài cluster hiện hành.

### Kiểm tra membership an toàn

Một thao tác remove có thể đã commit dù command-line client timeout. Luôn quan sát lại **members và term/leader** qua API của cụm, thay vì lặp một phép remove/add không còn khớp trạng thái hiện tại.

## 21. Redis Sentinel và Redis Cluster: đừng gộp hai cơ chế

### Redis Sentinel

Sentinel giám sát primary/replica và điều phối failover. Các khái niệm như **quorum để xác định subjective/objective down** và số Sentinel cần cho một failover hợp lệ là một phần của protocol Sentinel; chúng **không phải quorum commit log kiểu Raft cho từng lệnh Redis**.

Ví dụ:

```text
Sentinel S1, S2, S3
Redis primary P
Redis replica R1, R2
```

Số Sentinel và quorum detection ảnh hưởng khả năng quyết định failover. Nhưng Redis replication có thể bất đồng bộ; failover **không tự bảo vệ mọi write đã ACK như một Raft majority-committed log**. Muốn đánh giá durability, phải xem `WAIT`, persistence, replication và policy của ứng dụng đúng phiên bản.

### Redis Cluster

Redis Cluster có **hash slots**, master/replica, cluster-bus/gossip và failover semantics riêng. Thêm node vào cluster có thể kéo theo:

- Node join và phân vai.
- Phân phối slot/resharding.
- Cập nhật metadata định tuyến.
- `MOVED/ASK` khi slot đổi owner.
- Replica placement và failover quorum.

Một node joined chưa chắc đã **sở hữu hash slot** hoặc trở thành data replica của slot nào. Việc thay membership vật lý khác với việc đổi **slot ownership**.

### Đừng suy Redis Cluster dùng joint consensus của Raft

Redis Cluster có thuật toán và trade-off riêng, không nên mô tả quá trình đổi slot/membership như một Raft joint-consensus log nếu tài liệu engine không nói vậy. Bảo đảm strong uniqueness/atomic multi-key cũng không tự xuất hiện chỉ vì cluster có majority failover votes.

### Client stale routing

Sau resharding hoặc failover, client phải xử lý `MOVED`, `ASK` và route refresh đúng cách. Một client được đưa tới node cũ có thể nhận redirect; **không nên tự gửi write vào node cũ theo kiểu standalone bypass cluster protocol**.

## 22. Cassandra/ScyllaDB: membership gossip và token ownership khác Raft voter group

Cassandra-style systems có topology theo token ranges, replicas, coordinator, gossip, streaming, hints và repair. Một cụm có thể thêm node bằng **bootstrap**, hoặc bỏ node bằng **decommission**, và một số quá trình có thể dùng cơ chế metadata riêng tùy phiên bản.

**Không nên nói “Cassandra đổi membership bằng Raft joint consensus” như một quy tắc chung**. Ordinary data writes theo consistency levels như `ONE`, `QUORUM`, `LOCAL_QUORUM`, còn lightweight transactions và metadata/topology có các cơ chế khác tùy triển khai.

### Khi bootstrap node

Một số token ranges chuyển phạm vi replica placement. Trong lúc streaming:

- Node mới có thể chưa có đủ dữ liệu cho những token ranges được giao.
- Coordinator cần biết topology hiện hành.
- Hints/repair xử lý các chênh lệch theo cơ chế engine.
- Consistency level ảnh hưởng số replica cần phản hồi và kết quả đọc/ghi.

```text
Before: token range R stored on A,B,C
During bootstrap: D streaming relevant data
After topology transition: ownership/replica placement changes
```

Không cho rằng “D xuất hiện trong `nodetool status`” nghĩa là nó đã sẵn sàng cho mọi read/write của tất cả token ranges.

### Khi decommission

Đảm bảo dữ liệu/replicas cần thiết được chuyển, topology metadata được cập nhật và anti-entropy/repair phù hợp. Nếu loại node trước khi replicas còn lại sẵn sàng, request có thể timeout hoặc đọc bản cũ theo CL.

### Công cụ quan sát

Tùy engine/version:

```text
nodetool status
nodetool netstats
nodetool tablestats
```

Những công cụ này cung cấp trạng thái/streaming/metrics; chúng không phải một global linearizable membership API thống nhất như mọi nhóm Raft. Cần dùng đúng thủ tục bootstrap/decommission của phiên bản.

## 23. Elasticsearch/OpenSearch: voting configuration và shard allocation

Search clusters có các vai trò **cluster-manager/master-eligible**, data nodes và hệ thống quản lý metadata/shard allocation.

Một cluster có thể có:

```text
Cluster-manager eligible: M1, M2, M3
Data nodes: D1, D2, D3, D4
Index shards: distributed across data nodes
```

Thêm D5 có thể tăng năng lực shard placement nhưng **không tự làm thay cluster-manager voting quorum**, nếu D5 không eligible. Ngược lại, đổi số cluster-manager-eligible members ảnh hưởng khả năng bầu/quản lý cluster metadata và có quy trình riêng.

### Trong lúc cluster state chuyển

- Control-plane leader/quorum phải đủ để publish metadata an toàn.
- Shard allocation/relocation có thể tạo temporary recovery/backlog.
- Search/index API có thể có retry, partial result hoặc unavailable theo trạng thái shard.
- Điều kiện index replication/acknowledgment khác với global transaction semantics của một NoSQL transactional store.

Không đánh đồng **“cluster green”**, **“metadata quorum đủ”** và **“mọi search response đọc được version mới nhất của dữ liệu nguồn”**. Search refresh và CDC projection lag là những đường tiến độ khác.

## 24. DynamoDB và managed NoSQL: membership nội bộ không phải một knob của khách hàng

Với managed services, người dùng thường không nhìn thấy hoặc điều khiển trực tiếp membership của các nhóm replication nội bộ.

Các quyết định ứng dụng vẫn phải đưa ra:

- Lựa chọn consistency của read API nơi được hỗ trợ.
- Điều kiện write ACK và conditional/transaction semantics.
- Phân phối partition keys để tránh hotspot.
- Cấu hình multi-region và replication mode.
- Đường đọc qua base table, GSI, Streams/consumer.
- Kế hoạch chuyển traffic hoặc failover ở **cấp ứng dụng**, không phải sửa voter list nội bộ.

### Một sai lầm khi chuyển region

```text
Region A receives order v8 -> ACK
Traffic router switches to Region B
Region B still shows order v7
```

Không thể kết luận “dịch vụ mất majority node” nếu không biết cơ chế managed service. Phải phân biệt **multi-region replication mode**, client consistency setting và failover semantics của phiên bản/tính năng đang dùng.

Một region khác có thể là read replica eventually consistent trong một số cấu hình, và cần cách bảo vệ read-your-writes/authority riêng; không tự suy một write đã ACK tại A lập tức visible ở mọi B.

## 25. Thay đổi membership không đồng nghĩa thay shard key

Hai thao tác thường xảy ra gần nhau:

1. **Membership reconfiguration:** ai thuộc nhóm replica/voter, ai có quyền vote/commit?
2. **Resharding/rebalancing:** dữ liệu/khóa được đặt ở shard hoặc range nào?

Ví dụ:

```text
Add node D as data replica of shard R:
  membership/replica placement changes

Move range [1000,2000) from shard S1 to S3:
  ownership/routing changes

Change shard key tenantId -> (tenantId, userId):
  data partitioning model changes
```

Có thể cần **cả ba thay đổi**, nhưng safety rules khác nhau. Một cluster có majority control plane không tự bảo đảm range migration không bỏ sót write sau snapshot. Một shard đã chuyển owner không tự có leader/quorum đủ trong nhóm replica mới.

Khi thiết kế runbook, phải liệt kê **những nhóm consensus/metadata nào bị tác động** và **những đường read/write nào đổi đích**.

## 26. Client behavior: stale leader, redirect và unknown commit

Một client có thể giữ endpoint primary cũ:

```text
T0: leader=A, term=18, config=41
T1: leader transfers/failover -> B term=19
T2: client still sends WRITE to A
```

Một driver đúng cần khám phá topology mới, nhận redirect/not-leader, hoặc retry theo hợp đồng API. Nhưng có hai loại lỗi phải tách:

### 26.1. Known-not-committed

Server từ chối trước khi bắt đầu commit vì không phải leader:

```text
NOT_LEADER / STALE_CONFIG
=> refresh route, retry same logical operation
```

### 26.2. Unknown commit outcome

Request đã tới leader và có thể commit, response bị mất đúng lúc reconfigure:

```text
Client -> old leader: INCREMENT balance
Server commits through quorum
Response lost
Client timeout
```

Không thể tự xem timeout như chắc chắn không commit. Nếu retry lệnh `increment` mà không có idempotency, có thể áp **hai lần**.

### Thiết kế an toàn

- Stable `operationId` / `idempotencyKey` cho cùng yêu cầu nghiệp vụ.
- Conditional state transition/CAS theo `expectedVersion`.
- Durable request ledger hoặc server-side dedup có thời hạn/semantics phù hợp.
- Bounded retries với backoff/jitter.
- Deadline tổng thể, tránh retry storm khi election.
- Tra cứu outcome đã commit khi nhận unknown.

**Client library không thể tạo exactly-once business effect chỉ bằng reconnect**, nếu operation vốn không idempotent và server không lưu bằng chứng dedup.

## 27. Ví dụ Java 17: route refresh và phân loại retry

Đây là ví dụ minh họa một API write trừu tượng khi cluster chuyển leader. Nó **không phải implementation của Raft** và không thay thế SDK chính thức.

```java
import java.util.Objects;

record LeaderRoute(
    String endpoint,
    long configurationEpoch,
    long leaderTerm
) {}

record WriteRequest(
    String tenantId,
    String accountId,
    String operationId,
    long expectedVersion,
    long delta
) {}

record WriteResult(
    String operationId,
    long newVersion,
    String commitReference
) {}

interface ClusterDirectory {
    LeaderRoute currentLeader(String accountId) throws Exception;
    void invalidate(String accountId);
}

interface WriteTransport {
    // Must check authority and perform durable idempotent commit
    // according to backend's contract.
    WriteResult send(
        LeaderRoute route, WriteRequest command
    ) throws NotLeaderException, UnknownCommitException, Exception;
}

final class NotLeaderException extends Exception {}
final class UnknownCommitException extends Exception {}

final class AccountWriter {
    private final ClusterDirectory directory;
    private final WriteTransport transport;

    AccountWriter(ClusterDirectory directory, WriteTransport transport) {
        this.directory = Objects.requireNonNull(directory);
        this.transport = Objects.requireNonNull(transport);
    }

    WriteResult applyDelta(WriteRequest command) throws Exception {
        if (command.operationId() == null ||
            command.operationId().isBlank()) {
            throw new IllegalArgumentException("Missing operationId");
        }

        for (int attempt = 0; attempt < 3; attempt++) {
            LeaderRoute route =
                directory.currentLeader(command.accountId());

            try {
                return transport.send(route, command);
            } catch (NotLeaderException retryable) {
                // Only safe if this error guarantees no commit
                // occurred at the rejecting endpoint.
                directory.invalidate(command.accountId());
            } catch (UnknownCommitException ambiguous) {
                // Query operation ledger/status before any retry.
                throw ambiguous;
            }
        }

        throw new IllegalStateException(
            "Current leader could not be resolved"
        );
    }
}
```

### Giới hạn và giả định

1. `NotLeaderException` **phải có nghĩa chắc chắn request chưa commit**; nếu API không bảo đảm, phân loại thành unknown.
2. `operationId` chống duplicate **chỉ khi server có dedup/ledger bền** trong vùng authority. Truyền một chuỗi ID không tự làm phép cộng idempotent.
3. `expectedVersion` bảo vệ lost update/CAS trong phạm vi aggregate, nhưng không thay membership protocol.
4. `tenantId` phải được lấy từ identity đã xác thực và kiểm tra quyền trên nguồn; token định tuyến không là chứng chỉ authorization.
5. Production cần tổng deadline, timeout, cancellation, jitter/backoff và quan sát đầy đủ lỗi từng SDK.
6. Một transaction chạm nhiều shard không thể retry bằng từng thao tác rời; phải resolve hoặc retry **toàn transaction** theo contract.

Mục đích của ví dụ là thể hiện **một ranh giới trách nhiệm**: consensus layer quyết định authority; client giữ operation identity và xử lý outcome chính xác.

## 28. Khi config change gặp transaction nhiều partition

Giả sử transaction T chuyển tiền giữa tài khoản A ở shard S1 và B ở shard S2:

```text
T:
  debit(A, 100) on S1
  credit(B, 100) on S2

During T:
  S1 reconfigures voter membership
  S2 leader fails over
```

Những câu hỏi:

- T đã vào phase prepare hay chưa?
- Coordinator đã ghi quyết định COMMIT/ABORT bền chưa?
- S1 có thay leader nhưng giữ log/locks của T không?
- Một participant bị remove có còn là người chịu trách nhiệm recovery T không?
- Client timeout lúc commit có được phép retry tạo transfer mới?

**Reconfiguration protocol của từng shard** phải phối hợp với **transaction coordinator** theo API hỗ trợ. Quorum cho log của S1 không tự nghĩa một transaction hai shard đã atomic commit.

### 2PC không tự cho global consistency toàn hệ

Two-phase commit (2PC) có thể điều phối quyết định atomic commit giữa participants, nhưng:

- Có thể block/in-doubt nếu coordinator/participants mất kết nối.
- Isolation phụ thuộc cơ chế transaction của engine.
- Không bao gồm external payment provider/email broker nếu chúng không tham gia.
- Membership changes có thể làm tăng latency, abort hoặc recovery complexity.

Khi chọn window reconfiguration, cần xét **long-running transactions và read snapshots**. Không vội force-remove node giữ state cần cho quyết định đang chờ.

## 29. Rolling upgrade và membership: đừng thay cả hai thứ cùng lúc nếu không cần

Một đợt nâng cấp có thể bao gồm:

- Đổi binary/database version.
- Đổi cấu hình voters.
- Thêm/bớt node.
- Rebalance data placement.
- Chuyển leader.
- Đổi read/write concerns.

Nếu thực hiện tất cả đồng thời, rất khó xác định lỗi đến từ **protocol incompatibility, lag, election, topology hay schema**.

### Một quy trình tách bước

1. Kiểm tra compatibility matrix và rolling-upgrade procedure theo engine.
2. Xác nhận cluster health/quorum trước thay đổi.
3. Nâng cấp từng member theo thủ tục được hỗ trợ; tránh làm mất majority cùng lúc.
4. Đợi member trở lại healthy/caught up trước bước tiếp theo.
5. Thực hiện membership change riêng nếu cần.
6. Đo read/write SLO, election và client retries.
7. Khi đổi protocol/schema feature cần one-way migration, ghi rõ **rollback compatibility**.

“Rolling upgrade” không có nghĩa mọi phiên bản có thể hoạt động lẫn nhau vô thời hạn. Một số thay đổi cluster metadata hoặc storage format có thể là bước không dễ đảo ngược.

## 30. Restore, disaster recovery và nguy cơ tạo một cụm thứ hai

Một tình huống:

```text
Site A has old cluster snapshot at commitIndex=1000
Site B has live cluster committed through index=1200

Operator restores old snapshot at Site A
Then allows both clusters to accept writes for same IDs
```

Nếu Site A và B hoạt động như hai authority độc lập cho cùng dữ liệu, sẽ có **split-brain cấp vận hành** dù mỗi cụm bên trong đều sử dụng consensus đúng.

### Recovery cần quyết định authority

Phải xác định:

- Cluster nào chứa **lịch sử đã commit** cần giữ.
- Snapshot có index/term/cluster ID nào?
- Có write đã ACK sau snapshot không?
- Có thể replay log/change stream tới đích không?
- Những client nào còn route tới cụm cũ?
- Quy trình cutover/recovery có fencing mạng, credential hoặc authority epoch không?

### Không coi snapshot là member hợp lệ

Một disk image chứa log cũ có thể không thuộc cluster hiện hành. Nó phải được join/restore bằng **quy trình của sản phẩm**, không được tự quảng bá là leader chỉ vì file config nói vậy.

### Backup và consensus khác nhau

Consensus giúp quyết định thứ tự/authority của các operation trong điều kiện được thiết kế; nó không thay backup, không tự sửa xóa nhầm dữ liệu bởi user có quyền và không thay kế hoạch disaster recovery.

## 31. An ninh và quyền thêm member

Một node mới có thể nhận **dữ liệu sao chép đầy đủ**, kể cả những trường nhạy cảm. Membership change vì vậy còn là thao tác bảo mật:

- Chỉ admin/automation có quyền phù hợp được add/remove member.
- Xác thực mutual TLS/certificates giữa các node.
- Xác minh node identity, endpoint và khóa trước khi cho tham gia.
- Kiểm soát data residency, network policy và disk encryption.
- Log audit ai thay voter set, vào lúc nào, theo change ticket nào.
- Rotate/revoke credential của node đã remove theo quy trình.

### Một host giả danh node mới

Nếu hệ chấp nhận thành viên chỉ bằng IP không xác thực mạnh, một host sai có thể nhận dữ liệu hoặc làm rối membership. “Node mới ping được” không phải phép kiểm danh tính.

### Không dùng config epoch thay authorization

Node đã có epoch mới vẫn không được quyền truy cập mọi tenant/application data ngoài policy. **Authority của consensus** và **authorization của người dùng/dịch vụ** là hai lớp riêng.

## 32. Quan sát trước, trong và sau reconfiguration

### 32.1. Consensus và membership

| Metric | Câu hỏi |
|---|---|
| `cluster_config_version` | Cấu hình hiện tại đã commit là gì? |
| `cluster_voting_members` | Có bao nhiêu voters, gồm ai? |
| `cluster_learner_members` | Ai đang catch-up, chưa vote? |
| `leader_id` / `leader_term` | Có leader hợp lệ không, có election liên tục không? |
| `quorum_available` | Nhóm hiện có majority cần thiết không? |
| `election_count` | Thêm member có gây election storm không? |
| `configuration_change_pending` | Có reconfig chưa hoàn tất/in-doubt không? |
| `stale_config_rejections` | Request tới endpoint/epoch cũ nhiều không? |

### 32.2. Replication/readiness

| Metric | Câu hỏi |
|---|---|
| `leader_committed_index` | Mốc đã commit của authority là gì? |
| `member_received_index` | Node mới nhận đến đâu? |
| `member_durable_index` | Node mới ghi bền tới đâu? |
| `member_applied_index` | Node mới đã apply và có thể đọc tới đâu? |
| `snapshot_transfer_bytes` | Snapshot còn bao nhiêu? |
| `log_replay_backlog` | Catch-up có tiến triển không? |
| `log_retention_window` | Có đủ lịch sử để replay? |
| `initial_sync_failures` | Có node mới liên tục phải đồng bộ lại? |

### 32.3. Dịch vụ và dữ liệu

| Metric | Câu hỏi |
|---|---|
| `write_ack_latency_p99` | Commit chậm hơn bao nhiêu? |
| `write_unavailable_rate` | Có request thiếu quorum? |
| `read_staleness_rate` | Read path có trả bản quá cũ? |
| `unknown_commit_outcomes` | Client timeout có kết quả mơ hồ? |
| `idempotent_retry_count` | Retry có tăng đột biến? |
| `transaction_abort_rate` | Transaction xung đột khi đổi leader? |
| `rollback_events` | Có local writes bị loại? |
| `reconciliation_mismatches` | Dữ liệu sau transition có chênh lệch? |

**Tên metric trên là gợi ý mô hình**, không phải danh sách key tồn tại nguyên văn ở MongoDB/etcd/Redis/Cassandra. Khi làm dashboard phải map sang metric được exporter/API thực sự hỗ trợ.

### Cardinality và dữ liệu riêng tư

Không gắn `email`, `userId` hoặc toàn bộ key application vào metric labels. Sử dụng cluster/group/member/config version và trace IDs được phân quyền phù hợp.

## 33. SLO khi thay cấu hình

Ví dụ các mục tiêu **minh họa**, không phải mặc định của sản phẩm:

```yaml
reconfigurationObjectives:
  safety:
    - no_conflicting_committed_leaders
    - no_loss_of_acknowledged_majority_commits
    - no_unauthorized_old_member_writes
  availability:
    - foreground_write_success_rate_above_service_target
    - bounded_leader_election_unavailable_window
  progress:
    - new_member_catches_up_before_promotion
    - config_change_has_a_clear_committed_result
  recovery:
    - interrupted_change_can_resume_or_abort_safely
    - client_unknown_outcomes_are_reconciled
```

### Đừng đổi correctness thành p95

Một bất biến như “không có hai reservation được xác nhận cho cùng ghế” không thể được thỏa bằng việc **99%** giao dịch đúng. Nó là yêu cầu correctness; cần authority/atomic conditional write.

Ngược lại, latency p95/p99 và thời gian bầu leader là **mục tiêu hiệu năng/khả dụng**. Có thể tạm trả unavailable cho một số request để bảo vệ safety, thay vì “thành công” bằng cách xác nhận ghi trên hai phía không liên lạc.

## 34. Runbook thêm member an toàn

Một runbook theo nguyên lý; **luôn thay bằng thủ tục chính thức của engine/version**:

### Bước 1 — Chuẩn bị

Ghi tên cụm, consensus group, current voters, data replicas, leader, quorum, topology và failure domains. Xác nhận backup/restore/recovery plan.

### Bước 2 — Kiểm tra health

- Có leader ổn định.
- Không thiếu quorum.
- Không đang có config change khác.
- Replication lag và log retention đủ.
- p99 latency/timeout ở trạng thái chấp nhận được.

### Bước 3 — Chuẩn bị node mới

Xác thực identity/certificates, disk, network, version tương thích, vị trí failure domain, monitoring và không dùng stale cluster data tùy tiện.

### Bước 4 — Join dưới vai trò phù hợp

Nếu hỗ trợ, thêm learner/non-voter trước; nếu không, dùng procedure add voter được tài liệu yêu cầu. Không tự nâng quorum bằng nhiều node chưa hoạt động.

### Bước 5 — Catch-up

Đợi snapshot/log đồng bộ tới mốc theo protocol; xác minh không chỉ received mà cả durable/applied cần thiết. Đánh giá throughput và khả năng theo kịp write rate.

### Bước 6 — Promote/reconfigure

Gọi API thay membership một cách có đồng thuận; dùng joint consensus hoặc sequential protocol theo implementation. Không deploy một config mới độc lập lên từng node.

### Bước 7 — Xác minh commit

Đọc lại committed membership version, voter set, leader/term và quorum mới. Nếu admin command timeout, **kiểm tra trạng thái** trước khi retry hoặc tạo thay đổi mới.

### Bước 8 — Đo dịch vụ

Kiểm tra write/read latency, error rate, stale config redirects, idempotent retries, transaction abort, duplicate business effects.

### Bước 9 — Dọn và cập nhật tài liệu

Ghi config mới, rollback plan đã thay đổi, routing rules, placement/failure-domain và cảnh báo quorum.

### Bước 10 — Kiểm tra failure tolerance

Xác định rõ cụm sau thay đổi chịu mất **tổ hợp node/AZ nào**, không chỉ suy “tăng N là tốt”.

## 35. Runbook bỏ/thay member an toàn

1. Xác định member cần remove có đang là **leader** hay giữ dữ liệu duy nhất/replica cần thiết không.
2. Kiểm tra remaining voters/replicas có thể đạt quorum và durability target sau remove.
3. Nếu là leader, chuẩn bị leadership transfer theo API chính thức khi phù hợp.
4. Nếu thay host, **thêm member thay thế và catch-up** trước trong phạm vi protocol cho phép.
5. Remove bằng membership API/consensus configuration change.
6. Quan sát reconfig commit version; không dựa vào timeout admin.
7. Kiểm tra member cũ đã bị fence khỏi voting/committing.
8. Refresh routing, driver discovery và firewall/credentials khi cần.
9. Chỉ xóa disk/release host sau khi xác nhận authoritative history đã an toàn.
10. Chạy read/write probes và recovery checks; lưu audit.

### Không được làm tắt

```text
Kill old leader
Delete its disk
Edit peer list on surviving nodes
Start a restored node with an old cluster snapshot
Assume all commits are intact
```

Chuỗi này không phải một procedure an toàn chung. Nó bỏ qua quorum, committed membership, log catch-up và idempotency.

## 36. Nếu reconfiguration bị kẹt

### Triệu chứng A — Không có leader

Kiểm tra:

- Voters đang ở config nào?
- Majority có thể liên lạc không?
- Node mới có bị coi là voter dù chưa online?
- Có election storm hoặc clock/network issues?

Không tự promote một node cũ bằng cách sửa file nếu chưa có recovery protocol.

### Triệu chứng B — New member không catch-up

Kiểm tra network, disk, snapshot progress, log retention, apply throughput, TLS/auth và version compatibility.

Nếu log bắt buộc đã hết retention, có thể cần resnapshot theo engine. Không lấy một snapshot không có checkpoint rõ rồi cố replay bừa.

### Triệu chứng C — Admin change timeout

Đọc committed membership/config version từ authority, xem lệnh có thể đã thành công hay chưa. Chỉ retry theo semantics API, không tự tạo config có số version khác.

### Triệu chứng D — Client writes timeout

Phân biệt `NOT_LEADER`, `NO_QUORUM`, `UNKNOWN_COMMIT`, storage timeout và transaction conflict. Mỗi loại có retry/verification khác nhau.

### Triệu chứng E — Member cũ vẫn nhận request

Kiểm tra driver discovery, DNS/cache, direct node connections, protocol fencing và những API cho phép đọc stale. Ngăn stale leader **ACK commit giả** nếu nó không còn authority.

### Triệu chứng F — Sau reconfig xuất hiện missing/duplicate business effect

Thu thập lịch sử ACK, operation IDs, commit terms, replica positions, failover/rollback và outbox/consumer logs. Đối soát từ nguồn có thẩm quyền, tránh chữa bằng cách chọn timestamp lớn nhất.

## 37. Thử nghiệm fault injection trên lab

Chỉ mô phỏng network partition, crash hoặc kill node trong **lab/staging với dữ liệu giả**, không chạy trên production nếu không có quy trình/ủy quyền rõ.

### Kịch bản 1 — Thêm learner dưới tải ghi

```text
Old voters A,B,C
New learner D
Writer: 100 writes/s (ví dụ)
Reader: read-after-write checks
Fault: D network briefly delayed
```

Quan sát D không làm tăng majority trước promote, leader vẫn commit theo quorum cũ khi protocol cho phép, snapshot/replay bắt kịp và latency của traffic chính.

### Kịch bản 2 — Promote khi learner chưa theo kịp

Ở môi trường test, đưa D vào trạng thái lag và thử quy trình promotion. Hệ/tooling có từ chối hoặc cảnh báo không? Nếu cho phép, availability/readiness bị ảnh hưởng thế nào? **Không mặc định mọi protocol bắt buộc appliedIndex bằng leaderIndex tại thời điểm promote**; so với yêu cầu chính thức.

### Kịch bản 3 — Partition trong joint phase

```text
C_old={A,B,C}
C_new={C,D,E}
Phase=JOINT
Partition: {A,B} | {C,D,E}
```

Kiểm tra những thao tác nào có thể commit theo yêu cầu **majority old AND majority new**; không có phía nào tự biến một old-only/new-only quorum thành một commit hợp lệ.

### Kịch bản 4 — Crash leader khi final config commit

Admin command timeout, leader crash. Sau bầu leader mới, hệ công bố config nào đã commit? Có hai leader cùng commit write xung đột không? Client có cần verify unknown outcome không?

### Kịch bản 5 — Remove leader có session writes

Client ghi version 8, nhận ACK theo concern được chọn. Chuyển leader/remove old member, client đọc lại. Kiểm tra read-your-writes/linearizable read theo API, không tự đánh đồng secondary stale read với source durability.

### Kịch bản 6 — Rejoin node bị remove

Đưa node cũ còn disk/log về mạng. Kiểm tra node không tự reclaim voter/leader role nếu đã bị remove; các kết nối trực tiếp có bị redirect/reject theo protocol?

### Kịch bản 7 — Rolling upgrade và reconfig

Tách riêng test upgrade rồi test membership, sau đó thử kết hợp trên ma trận phiên bản được hỗ trợ. Quan sát election rate, log catch-up và client timeouts.

### Kịch bản 8 — Multi-region latency/partition

Mô phỏng WAN delay làm voter ở region khác không phản hồi đúng hạn. Xác định nhóm nào còn majority và độ trễ commit theo cấu hình.

## 38. History và bằng chứng để phân tích rủi ro chuyển tiếp

Một operation log tối thiểu:

```json
{
  "runId": "membership-test-001",
  "operationId": "OP-42",
  "clientId": "C07",
  "kind": "WRITE",
  "key": "orders/ORD-1001",
  "expectedVersion": 7,
  "returnedVersion": 8,
  "invokedAt": "2026-11-14T10:00:00.100Z",
  "completedAt": "2026-11-14T10:00:00.190Z",
  "result": "COMMITTED",
  "servingNode": "A",
  "knownConfigVersion": 41,
  "knownLeaderTerm": 18
}
```

Một config event:

```json
{
  "runId": "membership-test-001",
  "changeId": "CFG-42",
  "phase": "JOINT_TO_NEW",
  "oldVoters": ["A", "B", "C"],
  "newVoters": ["C", "D", "E"],
  "newConfigVersion": 42,
  "decision": "COMMITTED",
  "commitReference": "term=19,index=12080"
}
```

Đây là **schema logging minh họa**, không phải cấu trúc chính thức của một SDK.

### Nên lưu cả các request lỗi

Nếu chỉ log những write thành công, có thể bỏ sót request timeout đã commit hoặc write bị retry hai lần. Ghi:

- Invoke/complete của request.
- Result: committed, conflict, unavailable, retryable, unknown.
- Config/leader epoch mà client nghĩ đang sử dụng.
- Node thực tế phục vụ.
- Stable operation ID.
- Commit reference/log metadata nếu được API cung cấp.
- Event leader change và membership commit.

### Đồng hồ của hai máy có thể lệch

Để kiểm tra linearizability, không chỉ so hai timestamp từ hai client không đồng bộ. Dùng controller tạo non-overlap rõ ràng: nhận ACK write A rồi mới gửi read B.

Một history không có phản ví dụ **không chứng minh mọi lịch sử đều an toàn**; kiểm thử nên kết hợp contract của protocol, fault injection và quan sát recovery.

## 39. Kiểm tra bằng ví dụ số

### 39.1. Từ 3 sang 5 voters

```text
Old {A,B,C}, Qold=2
New {A,B,C,D,E}, Qnew=3
```

Nếu trong joint phase giao thức yêu cầu old majority **và** new majority, tập `{A,B,C}` có:

- 3 old votes, đủ 2.
- 3 new votes, đủ 3.

Nó có thể thỏa điều kiện số lượng nếu các member còn lại đáp ứng log/term requirements. Tập `{A,B}` chỉ có 2 new votes và **không đủ**.

### 39.2. Từ 3 sang 3 với một member chung

```text
Old {A,B,C}, Qold=2
New {C,D,E}, Qnew=2
```

Tập `{A,B}` có old majority nhưng **không có new majority**. Tập `{D,E}` có new majority nhưng **không có old majority**. Hai nhóm này không được commit độc lập trong joint phase.

Tập `{A,C,D}` thỏa:

```text
Old: A,C = 2/3
New: C,D = 2/3
```

nhưng còn phải tuân thủ protocol log/election, không chỉ đếm ACK.

### 39.3. Từ 3 xuống 2 voters

```text
Old {A,B,C}, majority 2
New {A,B}, majority 2
```

Nếu C được remove, cluster A+B không chịu được việc mất thêm A hoặc B. Người vận hành phải ghi nhận thay đổi **fault tolerance**, không chỉ “chúng ta còn hai node khỏe”.

### 39.4. Hai data voters và một arbiter

```text
Voters A,B,C(arbiter), majority votes 2
Data copies A,B
```

Khi B không có mặt, A+C có thể đáp ứng một số điều kiện election, nhưng **không có hai data copies lưu thay đổi mới**. Vì vậy một ACK yêu cầu sự xác nhận của nhiều data-bearing nodes cần được đánh giá riêng.

## 40. Những hiểu nhầm phổ biến

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
|---|---|---|
| “Thêm node luôn tăng HA ngay” | Majority có thể tăng khi node chưa sẵn sàng | Learner/catch-up rồi promote theo protocol |
| “Một cluster 5 máy có 5 voters” | Có thể có read replicas, observers hoặc arbiters | Phân biệt roles |
| “5 voters nghĩa 5 data copies” | Voter có thể không data-bearing | Kiểm tra durability separately |
| “Hai config có chung node nên an toàn” | Majorities cũ/mới vẫn có thể không giao nhau | Safe reconfiguration protocol |
| “Đổi file peers trên từng máy là đủ” | Các node áp config khác nhau | Membership API có đồng thuận |
| “Joint consensus là OR hai majority” | Cần phối hợp cả hai cấu hình theo protocol | Old AND new quorum trong joint |
| “Mọi Raft implementation đều dùng joint consensus” | Có biến thể single-step với quy tắc riêng | Đọc đúng implementation |
| “Chỉ đổi một node thì khỏi cần protocol” | Vẫn có race config commit | Dùng API chính thức |
| “Learner đã copy snapshot = có thể vote” | Có thể chưa replay/áp log đầy đủ | Readiness theo engine |
| “Leader transfer = remove member” | Membership vẫn có thể giữ nguyên | Tách role change và config change |
| “Ping xanh = voter healthy” | Không nói log/term/commit hay TLS | Quan sát readiness và quorum |
| “Node bị remove vẫn ghi local được vì còn data” | Không còn quyền authoritative | Fencing/redirect |
| “ACK từ primary = quorum commit” | Write concern khác nhau | Đọc đúng ACK semantics |
| “Election majority = durability majority” | Arbiter có vote không có data copy | Phân biệt election và data replication |
| “Network partition có thể force config ngay” | Có nguy cơ split-brain/rollback | Recovery theo protocol |
| “Timeout admin command = config chưa commit” | ACK có thể mất sau commit | Read committed membership |
| “Quorum đủ thì mọi multi-shard transaction an toàn” | Transaction coordinator/isolations khác | Kiểm tra transaction semantics |
| “Cassandra, Redis, MongoDB đều reconfig như Raft” | Giao thức và roles khác nhau | Đọc engine docs theo version |
| “DynamoDB users tự quản voter membership” | Managed service nội bộ trừu tượng | Tập trung API và region semantics |
| “Cluster healthy sau đổi là đã không mất write” | Có thể còn rollback, stale read, side effects | Đối soát ACK history và dữ liệu |
| “Restore snapshot cũ là có member mới hợp lệ” | Cluster identity/log history có thể khác | Join/restore theo procedure |
| “Một bài test không lỗi là chứng minh formal” | Không bao quát mọi partition/failover | Contract + history + faults |

## 41. Bài tập thực hành

### Bài 1 — Majority cơ bản

Tính majority cho 2, 3, 4, 5 và 7 voters. Một cluster 4 voters đang có hai node sống có đủ quorum không? So sánh với cluster 3 voters có hai node sống.

### Bài 2 — Learner

Một cụm A/B/C định thêm D. D mới nhận log tới 10.000, trong khi leader commit tới 10.500 và apply của D mới tới 9.800. Vì sao không nên promote chỉ vì đã copy snapshot? Cần kiểm tra thêm những gì?

### Bài 3 — Hai majority không giao nhau

`C_old={A,B,C}`, `C_new={C,D,E}`. Chỉ ra một majority của mỗi config mà không giao nhau. Giải thích nguy cơ nếu mỗi bên tự commit theo config riêng.

### Bài 4 — Joint consensus

Với old/new ở bài 3, xét các tập `{A,B}`, `{C,D,E}`, `{A,C,D}`. Tập nào đủ điều kiện **majority old và majority new**? Vì sao chỉ đếm majority vẫn chưa đủ nếu log/term không hợp lệ?

### Bài 5 — Đổi config admin timeout

Admin yêu cầu remove A, command timeout nhưng config version mới có thể đã commit. Tại sao không nên ngay lập tức chạy một lệnh force reconfig? Nêu các phép đọc trạng thái cần thực hiện.

### Bài 6 — Remove một member

Một nhóm 3 voters A/B/C muốn remove C và không thay thế. Tính tolerance trước/sau. Nếu B chết sau đó, hệ sẽ xử lý write cần majority ra sao?

### Bài 7 — Election và durability

Một MongoDB replica set gồm hai data-bearing members và một arbiter. Khi một data secondary chết, quorum election và điều kiện majority write có thể khác nhau như thế nào? Vì sao arbiter không thay data replica?

### Bài 8 — Leader cũ rejoin

A là leader term 18, sau partition B được bầu term 19. A vẫn nhận một write từ client cũ. Server/driver phải làm gì để không tạo một authoritative history xung đột?

### Bài 9 — Unknown commit

Client gửi `INCR balance +100`, cluster commit xong nhưng ACK mất khi đổi leader. Thiết kế `operationId`, request ledger và xử lý retry mà không cộng hai lần.

### Bài 10 — Placement AZ

5 voters phân bố AZ-1:2, AZ-2:2, AZ-3:1. Hệ chịu mất một AZ bất kỳ không? Hệ chịu mất đồng thời AZ-1 và AZ-2 không? Vì sao “5 voters” chưa đủ để đánh giá mọi failure domain?

### Bài 11 — Config change gặp partition

Trong joint phase cần old majority 2/3 và new majority 2/3. Mạng tách `{A,B} | {C,D,E}`. Bên nào đáp ứng cả hai majority nếu không trao đổi thông điệp? Hệ nên ưu tiên safety hay xác nhận write sai?

### Bài 12 — MongoDB reconfig

Một admin muốn thêm secondary MongoDB. Nêu những câu hỏi về `votes`, `priority`, oplog, initial sync, write concern và compatibility phải trả lời trước khi biến member mới thành voter.

### Bài 13 — Redis Sentinel vs Raft

Giải thích vì sao quorum Sentinel phục vụ failover không tự tạo Raft-style consensus commit cho mọi Redis `SET`. Những dữ kiện nào cần kiểm tra để biết một write đã ACK có thể mất sau failover?

### Bài 14 — Redis Cluster

Thêm một node Redis Cluster nhưng chưa gán slots; điều gì thay đổi về membership và điều gì **chưa** thay đổi về ownership dữ liệu? Sau khi resharding, client nên xử lý `MOVED`/`ASK` thế nào?

### Bài 15 — Cassandra bootstrap

Một node mới đang streaming token ranges. Những thông tin về replica placement, CL, hints/repair, current topology và tốc độ streaming cần biết để kết luận việc thêm node an toàn?

### Bài 16 — Control plane mất quorum

Một metadata group mất majority, nhưng các data nodes còn tồn tại và có route cached. Những API nào có thể vẫn chạy và những thay đổi nào có thể bị chặn? Vì sao không nên suy một kết luận chung cho mọi request?

### Bài 17 — Multi-shard transaction

Một transaction hai shard đang prepare thì shard S1 đổi leader và remove member. Liệt kê những trạng thái transaction có thể pending/unknown và cách coordinator cần phục hồi quyết định commit.

### Bài 18 — Restore snapshot

Cluster đã commit đến index 1200; một bản snapshot cũ ở index 1000 được restore thành cluster thứ hai có cùng namespace và nhận write. Rủi ro gì xảy ra nếu cả hai cụm được phép nhận yêu cầu? Thiết kế quyền authority và cutover.

### Bài 19 — Rolling upgrade

Một nhóm định vừa nâng phiên bản MongoDB, vừa thêm hai voters và reshard cùng ngày. Hãy tách thứ tự thao tác, điểm xác minh readiness, và những lỗi khó điều tra khi làm tất cả cùng lúc.

### Bài 20 — Lập lịch test và báo cáo

Thiết kế lab với old voters A/B/C và learner D, sau đó promote D, remove A. Chèn network delay, leader crash và một admin timeout. Ghi operation history, config version, term, commit index, write ACK và read result. Viết kết luận **có phạm vi**, không tuyên bố “đã chứng minh không thể có mọi lỗi”.

## 42. Checklist ra quyết định trước mỗi thay đổi thành viên

1. **Đang thay membership của nhóm nào?** Control-plane voters, shard replicas, slot owner hay read replicas?
2. **Cấu hình đã commit hiện tại?** Voter IDs, roles, leader term, version, commit index?
3. **Quorum cũ và mới là bao nhiêu?** Có nguy cơ tăng majority trước khi member sẵn sàng?
4. **Engine dùng reconfiguration protocol nào?** Joint consensus, one-at-a-time hay cơ chế khác?
5. **Node mới đã catch-up chưa?** Received/durable/applied, snapshot và log retention?
6. **Node cần remove có là leader hoặc data replica duy nhất cho phạm vi nào không?**
7. **Failure domains** có thực sự cải thiện sau thay đổi không?
8. **Read/write ACK** ứng dụng đang dùng có phù hợp với quorum/durability target?
9. **Có long-running transactions** hoặc resharding khác đang diễn ra không?
10. **Nếu lỗi mạng ngay trong transition**, protocol cho phép/không cho phép những operation nào?
11. **Khi admin command timeout**, có cách tra committed config rõ ràng không?
12. **Client/driver** có refresh leader, stale metadata, idempotency và unknown commit recovery không?
13. **Backup/recovery** đã xác định cluster authority, membership identity và log history chưa?
14. **TLS/credentials/permissions** của node mới và node cũ có được quản lý không?
15. **Monitoring và runbook** có đo election, quorum, lag, p99, failed writes và dữ liệu sau transition không?

Nếu một câu trả lời quan trọng còn bỏ trống, không nên đổi voter set chỉ dựa vào việc node mới đã online.

## 43. Tổng kết

**Thành viên cụm, thay đổi cấu hình và rủi ro chuyển tiếp** là bài toán an toàn của quyền ghi, không chỉ là vận hành hạ tầng. Cùng một nhóm dữ liệu có thể tồn tại trên nhiều node, nhưng phải có một cơ chế thống nhất về **ai được bỏ phiếu, leader nào có thẩm quyền, quorum nào cam kết write và từ thời điểm nào cấu hình mới có hiệu lực**.

Những điểm cốt lõi:

1. **Node, voter, learner và data-bearing replica là các vai trò khác nhau.** Đếm máy không đủ để đánh giá quorum hay durability.
2. **Majority phụ thuộc cấu hình đã commit.** Thêm voter có thể làm quorum lớn hơn trước khi node mới bắt kịp, gây giảm availability.
3. **Chuyển cấu hình phải qua protocol an toàn.** Joint consensus hoặc quy trình thay member có đồng thuận ngăn old/new majorities độc lập xác nhận lịch sử xung đột.
4. **Catch-up trước promotion** giúp giảm rủi ro; snapshot copy xong không đồng nghĩa node mới đã đủ điều kiện vote/read/lead.
5. **Remove hoặc restore member cần fencing.** Node cũ vẫn chạy không có nghĩa còn quyền ghi; snapshot cũ không tự thành authoritative cluster.
6. **ACK và durability phải được phân biệt.** Local ACK, election majority và majority data replication không đồng nghĩa nhau; arbiter có thể vote nhưng không giữ data copy.
7. **Reconfiguration tác động tới client và transaction.** Stale leader, unknown commit, retry không idempotent, long-running transaction và shard ownership đều cần xử lý riêng.
8. **Không áp một thuật toán cho mọi NoSQL.** MongoDB, etcd, Redis Sentinel/Cluster, Cassandra, Elasticsearch và managed services có membership và failure semantics khác nhau.
9. **Kiểm thử phải bao gồm lỗi giữa chừng.** Network partition đúng lúc joint config, crash leader, admin timeout, stale router, rejoin old node và rollback sau commit mới quan trọng.

Trước khi thêm, bớt hoặc thay một thành viên cụm, hãy trả lời:

> “**Cấu hình nào đang được commit hợp lệ, quorum nào bảo vệ các write đã ACK, node mới đã bắt kịp đến đâu, và nếu mạng đứt ngay trong chuyển tiếp thì có thể tồn tại hai authority cùng cam kết dữ liệu xung đột hay không?**”

Khi những điều này được giải quyết bằng **giao thức membership chính thức, kiểm soát quyền ghi, quan sát tiến độ và recovery có điều kiện**, một cụm NoSQL mới có thể mở rộng hoặc thay thế thành viên mà vẫn giữ tính đúng của lịch sử dữ liệu.
