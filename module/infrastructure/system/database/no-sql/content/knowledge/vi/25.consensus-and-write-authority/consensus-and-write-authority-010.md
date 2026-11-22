# Quyền ghi sau failover và các thao tác đang dang dở

## 1. Mở đầu: lệnh ghi thành công hay thất bại khi leader biến mất?

Giả sử một ứng dụng đặt vé ghi vào hệ NoSQL có ba replica:

~~~text
Replica A: leader hiện tại
Replica B: follower
Replica C: follower
~~~

Khách hàng gửi yêu cầu giữ ghế cuối cùng:

~~~text
POST /reservations
Idempotency-Key: hold-cart-9001

{
  "seatId": "concert-42-A01",
  "customerId": "customer-42"
}
~~~

Ngay lúc đó, node A gặp sự cố. Client chỉ nhìn thấy **timeout**. Không ai ở phía ứng dụng biết chắc A đã làm được những gì trước khi mất kết nối:

- A có thể chưa nhận request.
- A đã nhận nhưng chưa ghi vào log.
- A đã ghi vào log riêng nhưng chưa replicate.
- A đã replicate, thỏa điều kiện commit, nhưng chưa trả ACK.
- A đã commit và gửi ACK, nhưng response bị mất trên đường truyền.
- A đã gọi payment hoặc gửi event trước khi transaction được xác nhận, khiến hệ ngoài DB có side effect.
- A không hỏng mà chỉ bị **network partition**; nó có thể vẫn tiếp tục chạy với thông tin quyền ghi đã cũ.

Sau failover, node B hoặc C có thể trở thành leader mới. Câu hỏi không chỉ là *“node nào đang là leader?”* mà là:

**Ai có quyền tiếp tục ghi, lịch sử ghi nào được công nhận, những lệnh đang dang dở được xử lý ra sao, và làm thế nào client retry mà không tạo dữ liệu trùng hoặc vi phạm bất biến?**

Đây là trọng tâm bài **“Quyền ghi sau failover và các thao tác đang dang dở”** trong chương **“Đồng thuận và quyền ghi”** của module Database No SQL.

### 1.1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **failover, leader election, failback, split-brain và fencing**.
2. Hiểu quyền ghi theo **term, epoch, generation, lease hoặc ownership metadata**.
3. Phân biệt các mốc **received, appended, replicated, committed, applied, acknowledged**.
4. Phân loại kết quả **COMMITTED, REJECTED và UNKNOWN** khi request timeout.
5. Giải thích vì sao leader cũ phải mất quyền ghi sau khi leader mới được bầu.
6. Phân tích số phận của log entry đã commit và chưa commit qua failover.
7. Thiết kế retry có **idempotency key**, conditional write/CAS và đối soát.
8. Hiểu giới hạn của Raft, MongoDB replica set, Cassandra, Redis và DynamoDB.
9. Xử lý những side effect ngoài DB bằng outbox, inbox, saga hoặc reconciliation.
10. Viết API Java và kịch bản kiểm thử về thao tác dang dở, failover, retry và split-brain.

---

## 2. Năm khái niệm không nên trộn lẫn

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Leader / Primary** | Node đang được giao quyền điều phối/tiếp nhận ghi theo một protocol | Replica A nhận write của Order |
| **Follower / Replica** | Node lưu/nhận bản sao lịch sử, có thể tham gia quorum | Replica B nhận log entry từ A |
| **Failover** | Chuyển trách nhiệm phục vụ sang node khác sau sự cố hoặc mất quyền | B được bầu thành leader |
| **Failback** | Chuyển lại vị trí phục vụ theo chính sách, không nhất thiết tự động | A hồi phục rồi có thể làm follower |
| **Write authority** | Quyền được quyết định hoặc xác nhận một ghi hợp lệ ở một phạm vi | Leader của group chứa `seat-42` |

Một node **còn sống** không có nghĩa nó còn quyền ghi. Một node **được client gọi là primary** không có nghĩa nó còn giữ vai trò primary theo trạng thái đồng thuận mới nhất.

### 2.1. Failover không chỉ là đổi địa chỉ IP

Một sơ đồ đơn giản:

~~~mermaid
flowchart LR
    C["Client"] --> R["Driver / router"]
    R --> A["Leader A - term 7"]
    A --> B["Follower B"]
    A --> D["Follower C"]
    A -. "Mất liên lạc" .- B
    B --> E["B được bầu term 8"]
    R --> E
~~~

Đổi đường gọi từ A sang B chỉ là phần **routing**. Một failover an toàn còn cần:

- Quyết định leader/owner mới bằng protocol hợp lệ.
- Duy trì những write đã committed.
- Ngăn owner cũ xác nhận write mâu thuẫn.
- Xử lý các entry/request chưa hoàn tất.
- Cập nhật metadata và client driver.
- Khôi phục các replica lệch và kiểm tra side effect ngoài DB.

### 2.2. Quyền ghi có phạm vi

Một cụm sharded có thể có leader riêng cho mỗi partition/consensus group:

~~~text
Partition P1: leader A, followers B/C
Partition P2: leader D, followers E/F
Partition P3: leader G, followers H/I
~~~

Khi A mất quyền ở P1, không thể suy ra D cũng mất quyền ở P2. **Failover cần được phân tích theo key, shard, group, region và topology thực tế.**

### 2.3. Leaderless không có “leader mới” cùng nghĩa

Không phải mọi NoSQL dùng single-leader replication. Một hệ leaderless/multi-leader có thể cho nhiều coordinator tiếp nhận write, với quy tắc quorum, version hoặc conflict resolution riêng.

Do đó những quy tắc **term/leader election** của Raft không được tự áp nguyên xi lên Cassandra regular writes hay mọi chế độ global table.

---

## 3. Phân biệt 6 mốc trong vòng đời một write

Một request có thể đi qua các mốc:

~~~mermaid
flowchart LR
    A["Received"] --> B["Appended locally"]
    B --> C["Replicated"]
    C --> D["Committed"]
    D --> E["Applied"]
    E --> F["ACK to client"]
~~~

Đây là **sơ đồ khái niệm**. Trong một số engine, thứ tự áp dụng, thời điểm ACK, storage flush và replication khác sơ đồ. Phải dựa vào contract sản phẩm để xác định mốc thật.

| Mốc | Điều đã xảy ra | Điều chưa thể tự kết luận |
|---|---|---|
| **Received** | Server nhận request | Đã ghi bất cứ thứ gì |
| **Appended locally** | Node nhận đã lưu entry cục bộ theo protocol | Entry được replica khác chấp nhận |
| **Replicated** | Entry đã tới một số replica | Đã committed, durable theo failure model |
| **Committed** | Giao thức công nhận entry theo quy tắc commit | Client đã biết kết quả; read path đã apply |
| **Applied** | State machine áp dụng thay đổi được commit | Downstream/search/payment đã hoàn tất |
| **ACK sent/received** | Response được tạo hoặc client nhận | Mọi bản sao, cache, index đã đồng bộ |

### 3.1. Append không đồng nghĩa commit

Ví dụ A đã ghi entry `reserve(seat-A01)` vào log riêng rồi mất quyền trước khi entry được committed.

Leader mới theo một consensus protocol đúng có thể không chứa entry ấy và có quyền thay thế phần log **chưa committed** theo quy tắc. Nếu client dựa trên `append` để coi là đã bán ghế, ứng dụng có thể hứa một quyền không còn tồn tại.

### 3.2. Replicated tới nhiều node vẫn cần quy tắc commit

Ở Raft, những điều kiện như **term của entry, log matching, leader completeness và commit index** góp phần quyết định entry nào được công nhận committed. Không được đơn giản phát biểu “mỗi khi có 2 bản ghi trên 3 node thì bất kỳ entry nào cũng đã committed” mà bỏ qua các chi tiết của protocol.

### 3.3. Committed không đồng nghĩa client đã nhận ACK

Ví dụ:

~~~text
T1: A gửi entry đến B.
T2: Điều kiện commit theo protocol được đáp ứng.
T3: A áp dụng thay đổi.
T4: A gửi HTTP response.
T5: Mạng đánh mất response.
T6: Client timeout.
~~~

Ở T6, **database có thể đã commit thành công**. Timeout phía client không được hiểu là transaction đã rollback.

### 3.4. ACK và durability phụ thuộc policy

Một ACK được trả sau write concern/commit level yếu có thể không hứa bảo toàn write qua failover. Một ACK theo majority/commit policy mạnh hơn có thể bảo vệ những write đã committed dưới **mô hình lỗi mà protocol cam kết**.

Cần tách:

- Đã được node nhận.
- Đã được quorum/consensus commit.
- Đã fsync vào durable storage.
- Đã được client ACK.
- Có còn tồn tại sau failover/mất zone/mất region hay không.

Không dùng một từ “success” cho tất cả.

---

## 4. Quyền ghi qua term hoặc epoch

Trong những giao thức đồng thuận có leader, **term/epoch** là thế hệ logic giúp phân biệt nhiệm kỳ lãnh đạo.

~~~text
Term 41:
  A là leader.
  B, C là follower.

A bị cô lập khỏi B/C.

Term 42:
  B được bầu thành leader.
  C chấp nhận B.
  A chưa biết mình đã mất quyền.
~~~

### 4.1. Vì sao cần số nhiệm kỳ tăng?

Nếu các replica chấp nhận mệnh lệnh từ hai leader khác nhau mà không kiểm tra thế hệ, cùng một key có thể nhận hai lịch sử mâu thuẫn.

Một thông điệp có term cũ cần được xử lý theo protocol:

~~~text
Incoming command: term=41, proposed leader A
Replica current term=42

=> Không chấp nhận A như leader hợp lệ của term mới.
~~~

Trong Raft, một server biết term cao hơn sẽ cập nhật term và không tiếp tục hành xử như leader của term cũ. Những chi tiết xử lý message phải theo protocol, không chỉ so một số và tự bỏ qua mọi metadata khác.

### 4.2. Term không đồng nghĩa timestamp

Term là thế hệ **logical** do protocol quyết định. Nó không phải đồng hồ tường (`Date.now()`) hay thứ tự thời gian vật lý từ mỗi máy.

Nếu hai node có đồng hồ lệch vài giây, term vẫn được dùng để quản lý quyền theo consensus. Không tạo term bằng cách lấy giờ hệ thống rồi mặc định đã có leader election an toàn.

### 4.3. Một term tăng chưa đủ nếu không có quorum

Không thể cho một node tự tăng `epoch` trong bộ nhớ rồi tuyên bố mình trở thành owner hợp pháp khi vẫn có node khác đang tiếp tục ghi. Quyền phải đến từ **cơ chế cấp quyền nhất quán** của hệ, bao gồm membership/quorum/metadata store cần thiết.

### 4.4. Fencing token cho tài nguyên bên ngoài

Giả sử A giữ lease thế hệ 41 để xử lý file. A bị pause rất lâu; lease hết hạn. B nhận quyền mới với token 42 rồi ghi vào object store. Sau đó A tỉnh lại, vẫn gửi write cũ.

Nếu object store hoặc service đích không kiểm tra fencing token, A có thể ghi đè dữ liệu mới dù coordinator đã thu hồi lease.

Một cơ chế fencing:

~~~text
Destination's highest accepted token = 42

Write from B (token 42): accepted
Write from A (token 41): rejected as stale
~~~

**Đồng hồ hết hạn lease không thể tự dừng một process đang pause.** Fencing phải được thực thi tại nơi cuối cùng áp dụng side effect hoặc thông qua một protocol có thẩm quyền tương đương.

### 4.5. Fencing khác idempotency

- **Fencing token:** chặn chủ sở hữu cũ hành động sau khi mất quyền.
- **Idempotency key:** chặn cùng một ý định nghiệp vụ được thực hiện nhiều lần khi retry.

Cùng một request ID vẫn có thể được gửi bởi owner cũ không còn quyền; cùng một owner mới vẫn có thể tạo side effect hai lần nếu thiếu idempotency. Nhiều workflow cần **cả hai**.

---

## 5. Split-brain: hai node cùng tin mình được ghi

**Split-brain** là tình huống có hai thành phần cùng cho mình quyền authoritative để nhận/commit thay đổi mâu thuẫn đối với cùng phạm vi dữ liệu.

~~~mermaid
sequenceDiagram
    participant CA as Client ở phía A
    participant A as A (leader cũ, term 8)
    participant B as B (leader mới, term 9)
    participant CB as Client ở phía B

    Note over A,B: Network partition
    CA->>A: Reserve seat-A01
    A-->>CA: "Success" nếu thiếu fencing
    CB->>B: Reserve seat-A01
    B-->>CB: Success
    Note over CA,CB: Hai lời hứa mâu thuẫn cho một ghế
~~~

### 5.1. Quorum ngăn hai phía cùng commit trong mô hình phù hợp

Trong một consensus group N=3, hai quorum majority kích thước 2 luôn giao nhau. Nếu protocol bầu leader, commit và membership được thực thi đúng, phía chỉ có một node không thể tự nhận đa số để commit write mới như leader hợp lệ.

Điều này không có nghĩa **mọi node cũ sẽ lập tức ngừng chạy**; chúng có thể tiếp tục xử lý request cục bộ trước khi nhận biết mất quyền. Chính giao thức **không cho phép chúng xác nhận commit trái lệ** là phần bảo vệ quan trọng.

### 5.2. Stale leader vẫn có thể trả read sai

Một leader cũ bị cô lập có thể còn giữ dữ liệu của mình. Nếu nó trả một linearizable read mà không xác minh còn quyền theo protocol, client có thể thấy state cũ sau khi phía mới đã commit.

Vì vậy một **strong read from leader** trong hệ consensus có thể cần ReadIndex/quorum check, lease hợp lệ với giả định thời gian hoặc cơ chế read barrier khác. “Đọc từ primary” không đủ nếu primary đã lỗi thời.

### 5.3. Availability phải nhường ở phía không đủ quyền

Với cùng một tài nguyên khan hiếm, một bên mạng bị chia không thể vừa xác nhận write độc lập, vừa đảm bảo không có hai lời hứa mâu thuẫn mà không có một thiết kế quyền cấp phát phù hợp.

Khi thiếu quorum/authority, hệ có thể:

- Từ chối write.
- Chờ đến deadline rồi trả lỗi.
- Ghi request **PENDING** không coi là cấp phát đã xác nhận, theo một workflow riêng.
- Chỉ cho read stale nếu sản phẩm cho phép và ghi rõ freshness.

Không được báo `CONFIRMED` khi không có cơ sở authoritative.

### 5.4. Quorum không thay thế business invariant

Ngay cả một hệ leader consensus có linearizable single-key operations, hai request cùng đọc `available=1` rồi cùng ghi `available=0` qua các thao tác rời vẫn có thể tạo hai reservation.

Cần **conditional update/CAS/transaction** cho business operation. Đồng thuận quyết định thứ tự ghi; application phải biến các điều kiện nghiệp vụ thành thao tác nguyên tử phù hợp.

---

## 6. Mô hình các kết quả sau failover

Một API write cần phân biệt ít nhất ba tình huống:

| Outcome | Ý nghĩa | Hành động của client/application |
|---|---|---|
| **COMMITTED** | Có bằng chứng thao tác đã hoàn tất theo commit contract | Trả kết quả cũ khi retry |
| **REJECTED** | Có bằng chứng điều kiện không thỏa hoặc thao tác không được chấp nhận | Trả lỗi nghiệp vụ phù hợp |
| **UNKNOWN** | Client chưa xác minh được thao tác đã commit hay chưa | Dùng ID ổn định, đọc/đối soát hoặc retry idempotent |

Có thể dùng thêm `PENDING` cho workflow chưa tới trạng thái terminal và `COMPENSATING` cho side effect đang được xử lý bù trừ.

### 6.1. HTTP timeout thuộc loại nào?

Thông thường:

~~~text
Socket timeout
Connection reset
Gateway timeout
Broken pipe
~~~

**Không đủ thông tin để kết luận chưa commit.** Kết quả phải được xem là `UNKNOWN` cho tới khi có bằng chứng cụ thể.

### 6.2. Conditional failure có thể là retry đã thành công

Nếu client retry cùng `reservationId`, một conditional insert có thể thất bại vì record đã tồn tại. Cần đọc lại và kiểm tra:

- Cùng business request ID?
- Payload hash có khớp?
- Trạng thái đã `HELD/CONFIRMED`?
- Record có thuộc đúng tenant/người dùng?
- Record có phải xung đột ID của request khác?

Không coi mọi duplicate key là thành công, cũng không coi mọi duplicate key là thất bại mới.

### 6.3. Outcome phải được xác minh từ nguồn phù hợp

Sau failover, một secondary hoặc search index có thể stale. Nếu dùng một stale read trả “không tìm thấy reservation”, client có thể gửi request mới và tạo trùng.

Nên dùng:

- Read API với consistency phù hợp.
- Request ledger/idempotency record ở nguồn authoritative.
- Transaction outcome/status endpoint khi có.
- Cơ chế retry có token được DBMS hỗ trợ.
- Reconciliation khi kết quả vẫn không rõ.

**Một stale `404 Not Found` không phải bằng chứng ghi trước đó chưa commit.**

---

## 7. Những entry nào được giữ lại sau leader failover?

Xét ba replica A, B, C và một log có index:

~~~text
Index:       1   2   3   4   5   6   7
Entry:       a   b   c   d   e   f   g

A (old):     a   b   c   d   e   f   g
B:           a   b   c   d   e   f
C:           a   b   c   d   e
~~~

Giả sử những entry `a..e` đã committed theo protocol. `f` và `g` mới xuất hiện trong một số log, nhưng chưa đủ điều kiện commit trong lịch sử giả định.

### 7.1. Entry committed phải được bảo vệ theo consensus safety

Một giao thức như Raft được thiết kế để leader mới có đầy đủ các entry đã committed, dưới giả định an toàn của protocol về quorum, persistent state và membership.

Vì vậy khi leader A mất quyền, các entry **đã committed** không được tùy tiện bị bỏ/ghi đè bởi một leader mới hợp lệ.

### 7.2. Entry uncommitted có thể tồn tại hoặc biến mất

Entry `f` hoặc `g` chưa committed có thể:

- Được leader mới giữ lại và về sau commit theo protocol.
- Bị thay thế bởi lịch sử mới hợp lệ.
- Xuất hiện ở một follower nhưng không được apply như committed state.
- Cần rollback/cleanup ở một engine có mô hình replica khác.

**Uncommitted không đồng nghĩa chắc chắn bị xóa**, và “đã append trên old primary” không đồng nghĩa chắc chắn được giữ.

### 7.3. Raft có quy tắc đặc biệt khi commit entry từ term cũ

Trong Raft, leader không đơn giản dựa vào số replica chứa một entry từ **term cũ** để trực tiếp kết luận nó đã committed theo quy tắc dành cho current-term entries. Một leader có thể commit entry term hiện tại rồi nhờ log matching/ordering mà các entry trước nó được coi committed.

Đây là lý do không thể dạy rằng “cứ đa số bản sao có entry là mọi entry đều có commit point” mà không hiểu term.

### 7.4. Commit index và applied index

Một server có thể có:

~~~text
lastLogIndex = 120
commitIndex = 118
lastApplied = 117
~~~

Nghĩa khái quát:

- Log đã chứa tới 120.
- Protocol công nhận committed tới 118.
- State machine đã apply tới 117.

Một read muốn thể hiện trạng thái đã commit qua 118 có thể cần đợi apply bắt kịp theo contract. Không được trả entry 120 như thể đã committed chỉ vì nó nằm trên disk.

### 7.5. Không cho side effect từ entry chưa commit

Nếu ứng dụng gửi email hoặc charge tiền khi leader mới **chỉ append một entry chưa committed**, về sau entry bị thay thế thì side effect bên ngoài vẫn tồn tại.

Một cách giảm rủi ro là để side effect phát sinh từ **state committed** hoặc outbox được ghi atomically cùng business transaction, và consumer xử lý idempotent.

---

## 8. Timeline A: request chưa tới server

~~~text
T0 Client gửi Reserve(R1).
T1 Network lỗi trước khi server nhận.
T2 Client timeout.
T3 B được bầu làm leader mới.
~~~

Nếu có bằng chứng chắc chắn server chưa nhận, request chưa được thực hiện. Nhưng từ một timeout thông thường, client **không thể tự xác minh T1 xảy ra ở đâu**.

Do đó trong thiết kế tổng quát, retry với cùng:

~~~text
Idempotency-Key = hold-cart-9001
Reservation ID = res-9001
Payload hash = stable
~~~

Nếu request đã thực thi ở một nhánh khác, cơ chế idempotency cần giúp phát hiện.

---

## 9. Timeline B: leader cũ append, chưa commit

~~~text
T0 Client gửi Reserve(R1) đến leader A.
T1 A append entry #71, chưa đủ quorum.
T2 A mất kết nối với B/C.
T3 B được bầu ở term mới.
T4 Client timeout.
~~~

Tại T4:

- Không được nói `COMMITTED` chỉ vì A có entry.
- Không được tự cho rằng entry #71 chắc chắn biến mất.
- B có thể chưa có #71 hoặc có một trạng thái log khác.
- Retry phải tôn trọng ID nghiệp vụ và protocol của nguồn mới.

Nếu sau này entry #71 bị loại, một retry hợp lệ có thể tạo request trong lịch sử mới. Nếu entry #71 đã được committed hoặc được leader mới giữ lại và commit, retry phải nhận diện cùng một ý định và tránh cấp phát trùng.

### 9.1. Log entry ID khác request ID

Log index và term xác định vị trí trong replication log. `requestId` xác định **ý định nghiệp vụ**.

Khi retry sau failover, cùng request có thể xuất hiện trong một entry/term khác nếu trước đó chưa được commit. Vì vậy không dùng `logIndex` làm idempotency key do client quyết định.

---

## 10. Timeline C: commit xong nhưng response bị mất

~~~mermaid
sequenceDiagram
    participant Client
    participant A as Leader A
    participant B as Follower B
    participant N as Leader B sau failover

    Client->>A: Reserve R1 (idempotency key K)
    A->>B: Replicate transaction
    B-->>A: ACK according to protocol
    Note over A,B: Commit achieved
    A--xClient: Response lost
    Note over Client: Timeout, outcome UNKNOWN
    Note over A,N: A mất quyền, B được bầu
    Client->>N: Retry Reserve R1 với key K
    N-->>Client: Trả kết quả đã commit của K
~~~

Một hệ xử lý idempotent đúng phải trả lại kết quả tương ứng request đã commit, **không giữ thêm một ghế**.

### 10.1. Cần lưu kết quả cùng business effect

Nếu một transaction tạo `reservation` nhưng record idempotency được ghi **sau đó** ở một thao tác riêng, crash giữa hai bước có thể khiến database đã giữ hàng nhưng idempotency ledger không biết.

Nên cân nhắc:

- Dùng **reservation ID ổn định làm primary/unique key** và conditional insert.
- Ghi idempotency record trong cùng transaction với business change.
- Có workflow bù trừ/đối soát nếu backend không có transaction cần thiết.

### 10.2. Payload không được thay trong cùng ID

Client retry `K` nhưng lần đầu yêu cầu 1 ghế, lần hai yêu cầu 2 ghế là xung đột. Server phải so hash hoặc các trường quan trọng, không chấp nhận âm thầm áp payload mới dưới cùng request ID.

### 10.3. Kết quả cũ có thể là lỗi nghiệp vụ

Một idempotency store không chỉ lưu success. Nếu request đầu bị **business reject** một cách xác định, retry cùng key có thể được trả cùng kết quả theo API contract. Cần phân biệt transient error với kết quả terminal đã được lưu.

---

## 11. Timeline D: old leader còn chạy khi new leader đã có quyền

~~~text
Term 10: A leader.
A bị cô lập khỏi quorum nhưng process vẫn hoạt động.

Term 11: B được quorum bầu làm leader.
B commit update x=20.

Client cũ vẫn kết nối tới A và gửi update x=15.
~~~

Nếu A nhận và trả “commit success” dựa trên local memory mà không có quorum/authority, ứng dụng sẽ thấy hai lịch sử mâu thuẫn.

### 11.1. Cơ chế bảo vệ

Một consensus-backed system đúng phải:

1. Ngăn A commit entry mới khi không thỏa protocol.
2. Buộc A lùi về follower khi nhận term mới.
3. Không chấp nhận write với term/epoch cũ ở replicas đã biết term mới.
4. Bảo vệ read khỏi stale leader khi yêu cầu linearizability.
5. Refresh routing metadata và xử lý retry của client.
6. Phân biệt connection vẫn mở với quyền ghi hợp lệ.

### 11.2. Network partition không đồng nghĩa process death

Sự cố network khó hơn crash rõ ràng: A có thể vẫn đọc/ghi local, tiếp tục heartbeat tới một tập nhỏ và chậm phát hiện mất quyền.

Nếu dùng distributed lock dựa trên lease, network delay và pause dài có thể khiến một worker cũ tỉnh lại sau khi lock hết hạn. Không dựa vào giả định “process tự biết nó đã mất quyền” khi external side effect cần fencing.

### 11.3. Không phải cứ bầu leader mới là hai người có quyền

Trong một majority consensus group với membership hợp lệ, các election quorum phải giao nhau. Một giao thức bầu leader đúng sẽ không trao quyền commit an toàn cho cả hai phía đồng thời trong cùng phạm vi, dưới những giả định lý thuyết của nó.

Tuy nhiên, application vẫn có thể tạo split-brain ở **bên ngoài DB** nếu hai worker cùng nghĩ mình được gửi payment hoặc tạo job mà external system không kiểm tra quyền.

---

## 12. Retry cần đúng thứ tự: không phải cứ thấy lỗi là gửi lại

Một chính sách retry đáng tin nên xét:

- Có **stable request ID** hay không?
- Business operation có idempotent không?
- Đã biết outcome chưa?
- Driver/DBMS có cơ chế retryable writes hoặc transaction token không?
- Có thể đọc request ledger ở nguồn authoritative không?
- Có khả năng một side effect bên ngoài đã xảy ra không?
- Retry sẽ đi tới leader mới đúng phạm vi không?
- Có nên backoff trong khi cluster đang failover?
- Còn đủ deadline và retry budget không?

### 12.1. Tránh retry không kiểm soát

Sai:

~~~java
while (true) {
    try {
        createNewReservationWithRandomId();
        break;
    } catch (Exception ex) {
        // Retry với ID mới vô hạn.
    }
}
~~~

Request đầu có thể đã commit. Mỗi retry ID mới có thể giữ thêm hàng.

### 12.2. Retry cùng ý định

Luồng khái niệm:

~~~text
Client sends K.
  |
  +-- COMMITTED -> return response.
  |
  +-- REJECTED_BY_CONDITION -> return business conflict.
  |
  +-- UNKNOWN/TEMPORARY_UNAVAILABLE:
       |
       +-- discover current authority
       +-- query request outcome with strong enough semantics
       +-- if found, return persisted result
       +-- if not found and safe to retry, resend same K
       +-- if still uncertain, return PENDING/UNKNOWN for reconciliation
~~~

### 12.3. Retry write timeout có thể bị duplicate key

Nếu transaction đầu đã tạo `Reservation(K)` và response bị mất, retry `INSERT Reservation(K)` có thể nhận duplicate key. Server nên xác minh record đó là cùng payload/user/tenant rồi trả kết quả cũ thay vì tạo ID khác.

### 12.4. Backoff và jitter

Failover có thể khiến nhiều client cùng retry, tạo **thundering herd** tại leader mới.

Một chính sách có thể dùng exponential backoff với jitter và tổng deadline. Không retry mãi ở tần suất tối đa.

Ví dụ:

~~~text
Attempt 1: immediate
Attempt 2: random wait in [0, 100 ms]
Attempt 3: random wait in [0, 200 ms]
Attempt 4: random wait in [0, 400 ms]
...
Stop at request deadline/retry budget.
~~~

Các con số minh họa; cần đo theo hệ/driver và bảo đảm không phá user SLO.

---

## 13. Java: mô hình hóa trạng thái ghi có kết quả không chắc chắn

Một thiết kế API Java nên cho phép trạng thái `UNKNOWN` thay vì ép mọi exception về `false`.

~~~java
public enum WriteOutcome {
    COMMITTED,
    REJECTED_BY_CONDITION,
    UNKNOWN
}

public record WriteReceipt(
    String requestId,
    WriteOutcome outcome,
    String resourceId,
    String reservationId,
    String message
) {}

public record ReserveCommand(
    String requestId,
    String tenantId,
    String resourceId,
    int quantity,
    String payloadHash
) {}
~~~

### 13.1. Repository contract

~~~java
import java.time.Duration;
import java.util.Optional;

public interface ReservationRepository {

    // Chỉ thực hiện side effect với một requestId duy nhất.
    // Nếu request đã tồn tại với payload khác -> conflict.
    WriteReceipt reserveAtomically(ReserveCommand command);

    // Đọc trạng thái authoritative theo key,
    // với consistency phù hợp sau failover.
    Optional<WriteReceipt> findCommittedRequest(
        String tenantId,
        String requestId
    );

    // Tra cứu leader/topology do driver/DBMS quản lý.
    // Không tự đoán node bằng hostname cố định.
}
~~~

Đây là **interface thiết kế**, không phải thư viện Java sẵn có cho mọi NoSQL.

### 13.2. Service retry có giới hạn

~~~java
import java.time.Duration;
import java.util.Optional;

public final class ReservationService {

    private final ReservationRepository repository;

    public ReservationService(ReservationRepository repository) {
        this.repository = repository;
    }

    public WriteReceipt reserve(ReserveCommand command) {
        if (command.requestId() == null
                || command.requestId().isBlank()
                || command.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Invalid reservation command"
            );
        }

        // Pseudocode: cần deadline, backoff, driver-specific errors,
        // authentication và telemetry trong implementation thật.
        try {
            return repository.reserveAtomically(command);
        } catch (TransientOrUnknownCommitException failure) {

            Optional<WriteReceipt> known =
                repository.findCommittedRequest(
                    command.tenantId(),
                    command.requestId()
                );

            if (known.isPresent()) {
                return known.get();
            }

            // Không tìm thấy ở một lần đọc không phải bằng chứng
            // request đầu chắc chắn chưa commit.
            return new WriteReceipt(
                command.requestId(),
                WriteOutcome.UNKNOWN,
                command.resourceId(),
                null,
                "Outcome needs safe retry/reconciliation"
            );
        }
    }
}
~~~

`TransientOrUnknownCommitException` là **loại exception giả định**; code minh họa ý tưởng, chưa compile độc lập và không thay thế API exception của một driver cụ thể.

### 13.3. Vì sao `findCommittedRequest()` phải đọc đúng nguồn?

Nếu method sử dụng một stale search index, nó có thể trả empty khi write đã commit. Một implementation đúng cần hiểu **read consistency, failover topology và phiên bản dữ liệu** của nơi lưu request ledger.

### 13.4. Retry thực sự nằm ở đâu?

Driver có thể tự retry một số lỗi; application cũng có thể retry. Nếu cả hai tầng retry không có ngân sách chung, số request thực tế có thể nhân lên rất nhanh.

Cần xác định:

- Driver retries: loại lỗi, số lần, idempotency semantics.
- Application retries: deadline, conflict handling, reconciliation.
- Gateway retries: có được tự replay POST không?
- Payment retries: có provider idempotency key riêng không?

---

## 14. CAS và conditional write sau failover

Giả sử client muốn cập nhật profile nếu version đang là 7:

~~~text
Expected version: 7
New value: displayName = "An Nguyễn"
~~~

Một thao tác có điều kiện:

~~~text
UPDATE profile
IF version == 7:
    displayName = "An Nguyễn"
    version = 8
ELSE:
    reject as conflict
~~~

### 14.1. Tác dụng của CAS

CAS giúp **tránh ghi đè dựa trên trạng thái đã cũ**. Sau failover, nếu version 8 đã được committed và client retry write với expected version 7, điều kiện sẽ thất bại.

### 14.2. CAS failure có thể là chính request đã thành công

Nếu client đã update version 7→8 nhưng không nhận ACK, retry với expected version 7 sẽ bị conflict.

Không nên tự kết luận một client khác đã ghi trước. Hãy xác minh `requestId` hoặc nội dung trạng thái:

~~~text
If request K already committed:
    return original success.

Else if version changed by another request:
    return conflict.

Else:
    consider safe retry.
~~~

### 14.3. Điều kiện và thay đổi phải atomic

Đọc version=7 ở Java rồi ghi version=8 bằng hai operation rời **không phải CAS**. Cần dùng conditional update/transaction hoặc API tương đương của DBMS.

### 14.4. Version gắn với phạm vi

Version tăng của profile không tự có thứ tự với Order hoặc một item ở partition khác. Nếu workflow cần CAS xuyên nhiều resource, phải xác định transaction scope hoặc protocol coordinator.

---

## 15. Idempotency ledger: thiết kế để retry sau khi owner đổi

Một request ledger có thể lưu:

~~~json
{
  "tenantId": "tenant-7",
  "requestId": "hold-cart-9001",
  "requestHash": "sha256-of-normalized-payload",
  "resourceId": "seat-42-A01",
  "result": "HELD",
  "reservationId": "res-9001",
  "committedVersion": 52,
  "createdAt": "2026-11-14T08:00:00Z",
  "retainedUntil": "2026-12-14T08:00:00Z"
}
~~~

Đây là **schema minh họa**, không phải cấu hình của một DBMS.

### 15.1. Các bất biến

- Trong phạm vi `(tenantId,requestId)`, tối đa một quyết định nghiệp vụ committed.
- Retry cùng payload trả lại quyết định đã có.
- Retry cùng ID nhưng payload khác bị từ chối.
- Reservation và request ledger cùng commit hoặc được phối hợp bằng protocol có recovery.
- Một callback `CONFIRM` trùng không tăng số lượng sold thêm lần nữa.
- Terminal record không bị xóa trước khi hết cửa sổ retry/callback có thể xảy ra.

### 15.2. State machine của request

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> COMMITTED: Business transaction commits
    RECEIVED --> REJECTED: Deterministic condition fails
    RECEIVED --> UNKNOWN: Result cannot be established
    UNKNOWN --> COMMITTED: Reconcile finds commit
    UNKNOWN --> REJECTED: Authoritative proof of rejection
    UNKNOWN --> RETRYING: Safe retry with same requestId
    RETRYING --> COMMITTED: Commit or existing result
    RETRYING --> REJECTED: Business conflict
~~~

Sơ đồ mô tả trạng thái **quan sát của application**; `UNKNOWN` không nhất thiết là trạng thái vật lý lưu trong DB. Không nên coi `RECEIVED` là persisted transaction nếu hệ chưa ghi nó.

### 15.3. TTL xóa ledger và nguy cơ retry muộn

Nếu sau 5 phút request record bị xóa, nhưng payment callback/retry có thể đến sau một ngày, cùng request ID có thể bị xem như mới.

Phải xác định retention theo:

- Thời gian retry của client/gateway/driver.
- Provider callback window.
- Offline queue.
- Audit/reconciliation policy.
- Những thao tác terminal phải tồn tại lâu hơn.

### 15.4. Unique constraint và quyền tenant

Request ID cần unique trong **phạm vi nghiệp vụ** được chọn. Đừng để người dùng khác dùng request ID của tenant khác để đọc/ghi kết quả; authentication và authorization phải được kiểm tra độc lập.

---

## 16. MongoDB replica set: bầu primary, majority và rollback

MongoDB replica set là ví dụ thực tế về **primary–secondary replication**, failover và mức write concern khác nhau.

### 16.1. Primary có thể mất quyền

Khi replica set không còn primary hiện tại phục vụ được, quá trình election có thể chọn primary mới trong những điều kiện của replica set. Client driver cần phát hiện topology mới và gửi operations tới primary phù hợp.

Trong thời gian election, một số writes có thể timeout/lỗi tạm thời.

### 16.2. Write concern `w:1`

Một write ACK ở primary nhưng chưa được nhiều replica bảo vệ có thể bị **rollback** nếu primary mất quyền và lịch sử của new primary không chứa write ấy.

Ví dụ logic:

~~~text
A primary accepts W1, ACK to client at w:1.
W1 chưa đến B/C.
A bị cô lập.
B được bầu primary mới.
W1 có thể không tồn tại trong majority history.
~~~

Không thể hứa “đã nhận ACK thì write không mất qua failover” mà bỏ qua write concern.

### 16.3. Write concern `majority`

Cấu hình write concern đa số giúp bảo vệ writes đã acknowledged theo quy tắc majority của MongoDB và giả định durability/topology được hỗ trợ.

~~~javascript
db.orders.insertOne(
  {
    _id: "order-9001",
    state: "CREATED"
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

Cần hiểu:

- `w: "majority"` là điều kiện xác nhận từ majority theo MongoDB semantics.
- `j: true` liên quan journaling theo cấu hình/server version.
- `wtimeout` có thể báo chờ ACK vượt thời hạn; không tự chứng minh write chưa được áp dụng.
- Đường đọc, transaction và secondary index có semantics riêng.

### 16.4. Transaction outcome unknown

Một transaction có thể commit ở phía server nhưng client không nhận được kết quả. Các MongoDB drivers có cơ chế/nhãn lỗi liên quan transaction retries và **unknown commit result**.

Không viết:

~~~java
catch (TimeoutException e) {
    startNewTransactionWithNewOrderId();
}
~~~

như một giải pháp mặc định.

Cần theo hướng dẫn driver: retry commit khi lỗi có nhãn thích hợp, giữ stable request ID, phân biệt retry transaction body với retry commit và tránh side effect bên ngoài callback transaction có thể chạy lại.

### 16.5. Read sau failover

Read từ secondary có thể stale; causal session và read/write concerns có thể giúp những bảo đảm theo phiên trong phạm vi hỗ trợ.

Một `find` từ secondary không tự chứng minh write đã commit/được rollback. Để xác minh idempotency record, dùng đường đọc có consistency phù hợp với business contract.

### 16.6. Rollback recovery

Một primary cũ trở lại có thể phải đưa lịch sử local chưa committed về trạng thái phù hợp với nguồn mới. Những write cũ chưa được majority-committed có thể không còn trong trạng thái authoritative.

Đây chính là lý do không dùng ACK yếu làm lời hứa hoàn tất giao dịch giá trị cao mà không có policy durability/recovery phù hợp.

---

## 17. Raft: leader completeness và các operation dang dở

Raft dùng các khái niệm:

- **Term:** nhiệm kỳ logic.
- **Election:** chọn leader qua cơ chế vote/quorum.
- **Log replication:** leader append và gửi entries tới followers.
- **Commit index:** ranh giới entries đã committed.
- **Leader completeness:** các leader mới hợp lệ phải chứa entries đã committed theo safety của Raft.
- **State machine apply:** chỉ áp dụng entries đã committed theo thứ tự.

### 17.1. Một ví dụ log trước crash

~~~text
Term 7, leader A
Entry 81: create order-1   COMMITTED
Entry 82: reserve seat-1  COMMITTED
Entry 83: reserve seat-2  PENDING (not committed)
~~~

A mất kết nối ngay sau append entry 83.

Leader mới theo Raft safety phải bảo vệ entries 81 và 82. Entry 83 có thể được giữ/commit về sau hoặc bị thay thế theo protocol; không thể suy kết quả của request chỉ từ việc nó đã tới A.

### 17.2. Leader mới phải ổn định khả năng commit

Những details như current-term commit rule, term/index match, vote restrictions và cập nhật commit index bảo vệ lịch sử.

**Quorum intersection là một thành phần của chứng minh**, không phải toàn bộ chứng minh. Không dùng tự suy luận `R+W>N` để bỏ qua log ordering/election safety.

### 17.3. ReadIndex và stale leader

Leader cũ có thể chưa biết đã mất quyền. Để cung cấp linearizable reads, một implementation Raft thường cần kiểm tra quyền leader/commit point theo protocol, ví dụ ReadIndex hoặc lease có điều kiện.

Một API `GET` từ “node từng là leader” không tự mạnh khi partition.

### 17.4. Commit vs applied

Nếu commit index đã tới 82 nhưng state machine mới applied tới 81, một read cần trạng thái sau 82 phải đợi apply hoặc dùng cơ chế đọc nhất quán tương ứng.

### 17.5. Exactly-once application không tự đến từ Raft

Raft có thể đảm bảo log/state machine theo protocol nhưng client retry cùng request với ID mới vẫn có thể append **hai command nghiệp vụ** hợp lệ.

Cần request ID + deduplication trong state machine hoặc transaction nghiệp vụ. Consensus **không tự giải quyết ý nghĩa “cùng một ý định người dùng”**.

---

## 18. Cassandra: regular writes và LWT không có cùng semantics quyền ghi

Cassandra thường được thiết kế theo kiểu multi-coordinator/leaderless cho regular reads/writes. Client có thể gửi requests qua nhiều coordinator, mỗi coordinator làm việc với replicas của partition.

### 18.1. Không có một primary duy nhất cho mọi write

Một node coordinator mất kết nối không có nghĩa cluster phải **bầu primary mới** cho regular write như MongoDB/Raft.

Khi retry, driver có thể chọn coordinator khác; tuy nhiên vẫn cần xét:

- Consistency level (`ONE`, `LOCAL_QUORUM`, `QUORUM`, v.v.).
- Replication factor và topology.
- Timestamp/conflict resolution.
- Timeout với **unknown write outcome**.
- Hinted handoff/repair hoặc replica lag.
- Application idempotency.

### 18.2. Write timeout vẫn có thể đã áp một phần

Ví dụ một regular write gửi tới RF=3 ở CL=QUORUM nhưng chỉ một replica phản hồi trước timeout. Client không có ACK theo yêu cầu, song một replica đã lưu mutation.

Retry có thể gửi cùng mutation nhiều lần. Nếu đó là **set một giá trị idempotent** thì tác động có thể ít rủi ro hơn so với một thao tác có side effect/counter/transaction bên ngoài.

Không kết luận `CL timeout -> chắc chắn không node nào ghi`.

### 18.3. Last-write-wins và timestamp

Cassandra sử dụng timestamp-based reconciliation cho nhiều kiểu dữ liệu/operations. Retry cùng logical mutation với timestamp khác có thể tạo semantics khác, đặc biệt dưới concurrent updates hoặc clock skew.

Cần hiểu cách driver tạo timestamp, idempotent statement và conflict semantics; không mặc định “lệnh SET giống nhau” tương đương một transaction business exactly-once.

### 18.4. LWT cho CAS

Khi cần “chỉ một request giành quyền” hoặc “chỉ cập nhật nếu version X”, có thể dùng **Lightweight Transactions (LWT)** trong phạm vi được hỗ trợ.

~~~sql
CREATE TABLE seat_by_id (
  seat_id text PRIMARY KEY,
  state text,
  reservation_id text,
  version bigint
);
~~~

~~~sql
UPDATE seat_by_id
SET state = 'HELD',
    reservation_id = 'res-9001',
    version = 8
WHERE seat_id = 'seat-42-A01'
IF state = 'FREE' AND version = 7;
~~~

Ứng dụng phải kiểm tra trường kết quả **`[applied]`** thay vì chỉ xét request được gửi thành công. Nếu request LWT timeout, cần xử lý outcome unknown và retry/query theo protocol.

### 18.5. Regular QUORUM không thay LWT

Hai client đọc `FREE` rồi cùng write `HELD` ở QUORUM vẫn có thể ghi đè theo conflict semantics nếu không có điều kiện nguyên tử bảo vệ ghế cuối.

Với bài toán quyền ghi business, cần phân biệt **coordinator có thể nhận write** và **một conditional business operation được linearize an toàn**.

---

## 19. Redis Sentinel/Cluster: failover và ghi chưa replicate

Redis primary–replica có thể sử dụng asynchronous replication; Sentinel hoặc Redis Cluster có cơ chế failover/topology riêng.

### 19.1. ACK trên primary chưa chắc tới replica

~~~text
T1: Primary A SET order:9001 = CREATED.
T2: A ACK client.
T3: A chết trước khi write replicate tới B.
T4: B được promote làm primary.
T5: order:9001 có thể chưa tồn tại trên B.
~~~

Điều này cho thấy **atomic command trên một primary** không tự đảm bảo durability/visibility sau failover.

### 19.2. WAIT có tác dụng giới hạn

Redis `WAIT` có thể chờ một số replica nhận các write liên quan theo semantics của lệnh. Nhưng:

- Nhận write không tự đồng nghĩa đã fsync.
- Không thay thế một general consensus commit protocol cho mọi key.
- Không tự bảo đảm mọi replica được bầu ở tương lai có write đó.
- Không làm mọi downstream side effects idempotent.
- Không tự chữa window split-brain của application.

### 19.3. Persistence cần định nghĩa riêng

AOF/RDB, fsync policy và deployment topology ảnh hưởng mức dữ liệu có thể mất qua crash/failover.

Một số workload chỉ dùng Redis làm cache/lease, chấp nhận xây lại state. Nếu dùng Redis làm **nguồn quyết định cấp phát tài nguyên giá trị cao**, phải đánh giá failure model nghiêm ngặt hơn.

### 19.4. Fencing cho lock dựa trên Redis

Một lock với TTL có thể hết hạn trong lúc worker bị stop-the-world pause. Worker cũ tỉnh lại vẫn có thể gửi side effect.

Giữ một Redis lock key **không tự buộc external system từ chối stale worker**. Cần fencing token/generation do một nguồn có thứ tự đáng tin cấp và được nơi nhận thao tác kiểm tra nếu side effect không được phép trùng hoặc lùi.

### 19.5. Cluster MOVED/ASK

Redis Cluster có redirect khi placement/slot owner thay đổi. Driver cần xử lý topology refresh và retry phù hợp. Không hard-code node route và đừng nhầm redirect với bằng chứng write trước thất bại.

---

## 20. DynamoDB: condition, transaction và multi-region không đồng nghĩa một leader toàn hệ

DynamoDB là managed NoSQL; chi tiết election/replica placement nội bộ không được ứng dụng điều khiển như một Raft group tự quản.

### 20.1. Đường ghi theo item

`PutItem`/`UpdateItem` có conditional expressions. Một điều kiện trên item có thể bảo vệ một invariant cục bộ theo API contract, ví dụ chỉ đổi `FREE -> HELD` nếu seat còn trống.

~~~javascript
import { UpdateCommand } from "@aws-sdk/lib-dynamodb";

await documentClient.send(new UpdateCommand({
  TableName: "Seats",
  Key: { seatId: "seat-42-A01" },
  UpdateExpression:
    "SET #s = :held, reservationId = :rid",
  ConditionExpression:
    "#s = :free",
  ExpressionAttributeNames: {
    "#s": "state"
  },
  ExpressionAttributeValues: {
    ":held": "HELD",
    ":free": "FREE",
    ":rid": "res-9001"
  }
}));
~~~

Đây là ví dụ conditional update trên **một item**. Nếu item chưa tồn tại hoặc state khác `FREE`, request không áp dụng như mong muốn.

### 20.2. Multi-item transaction

Khi cần cập nhật Seat và lưu Reservation/Idempotency record cùng atomic, cân nhắc `TransactWriteItems` trong giới hạn và phạm vi hỗ trợ.

Chú ý:

- Client request token của giao thức transaction có semantics/thời hạn riêng.
- Token đó không thay thế vĩnh viễn business request ledger.
- Retry sau timeout cần biết transaction có thể đã commit.
- Conditional failure có thể là xung đột hoặc idempotent replay.
- Transaction không bao phủ payment provider bên ngoài DB.

### 20.3. Global tables

Các chế độ global table có semantics replication/conflict riêng. Không thể coi “sau failover sang region B, condition của region A được duy trì như một linearizable global transaction” mà không kiểm tra đúng chế độ/contract multi-region được dùng.

### 20.4. Strong read và GSI

Một base-table strong read theo đường API được hỗ trợ có semantics khác query GSI eventually consistent. Khi xác minh outcome của một write, **đọc GSI chưa thấy record** không đủ kết luận write chưa commit.

### 20.5. Tóm lại

Hãy phát biểu bảo đảm từ **API item/transaction/region đã công bố**, thay vì tự đặt tên “leader” cho hạ tầng DynamoDB không hiển lộ.

---

## 21. Payment và message broker: thất bại ngoài transaction của DB

Giả sử một checkout có luồng:

~~~text
1. Reserve inventory.
2. Charge payment.
3. Confirm order.
4. Publish OrderPaid.
5. Send email.
~~~

Không có một database transaction thông thường bao phủ payment provider, broker và email.

### 21.1. Rủi ro khi leader failover giữa các bước

~~~text
A đã commit Inventory HELD.
A gọi payment; provider thu tiền thành công.
A crash trước khi cập nhật Order PAID.
B trở thành leader.
Client retry checkout.
~~~

Nếu B chỉ nhìn thấy Order chưa `PAID` rồi gọi charge lại với **payment ID mới**, khách có thể bị thu hai lần.

### 21.2. Payment idempotency

Dùng provider idempotency key ổn định cho cùng ý định thanh toán (theo contract của provider) và lưu mapping:

~~~text
businessPaymentId -> providerPaymentId
requestId -> orderId
orderId -> reservationId
~~~

Khi kết quả payment unknown, truy vấn/đối soát với provider trước khi tạo lần charge mới. Cần hiểu thời hạn idempotency và trạng thái pending/refund/void của provider.

### 21.3. Transactional outbox

Một mẫu:

~~~text
DB transaction:
  UPDATE order state to PAID
  INSERT outbox event OrderPaid(eventId=E1)
COMMIT
~~~

Worker đọc outbox đã committed rồi publish. Nếu worker crash sau publish nhưng trước khi đánh dấu đã gửi, event có thể được publish lại. Consumer phải idempotent theo `eventId`.

### 21.4. Inbox/deduplication

Consumer có thể lưu:

~~~text
ProcessedEvent(eventId, handlerName)
~~~

trong cùng transaction với side effect DB mà nó áp dụng, nếu có thể. Nhờ đó broker redelivery không tạo thay đổi trùng trong cơ sở dữ liệu đích.

Nếu consumer gọi một external API, vẫn cần idempotency protocol của API ấy hoặc reconciliation; **at-least-once delivery + idempotent handler** không biến mọi hệ ngoài DB thành atomic.

### 21.5. Saga và compensation

Khi tài nguyên đã được giữ nhưng payment thất bại, có thể release reservation theo state machine. Nếu payment đã thu nhưng hold hết hạn, workflow cần refund/void hoặc cấp phát lại có điều kiện theo chính sách.

Compensation **không phải rollback nguyên tử tức thời**. Có thể có trạng thái `COMPENSATING`, retry và dead-letter để điều tra.

---

## 22. Bất biến kinh doanh cần bảo vệ khi đổi leader

Một consensus protocol có thể bảo vệ thứ tự log; nhưng ứng dụng phải nêu rõ invariant.

Ví dụ vé đánh số:

\[
\forall seat,\quad
\#\{\text{confirmed allocations for seat}\}\le1.
\]

Ví dụ quota:

\[
available+held+confirmed=capacity
\]

và:

\[
available\ge0,\quad held\ge0,\quad confirmed\ge0.
\]

### 22.1. Chỉ một leader không đủ

Nếu leader A xử lý:

~~~text
Read available=1.
Create Reservation A.
Read available=1 from stale cache.
Create Reservation B.
~~~

một leader vẫn có thể tạo lỗi nghiệp vụ nếu thao tác đọc-kiểm tra-ghi không nguyên tử.

### 22.2. Confirm và expire có thể tranh nhau

Một hold có deadline. Payment callback và expiry worker cùng xử lý:

~~~text
Worker A: HELD -> CONFIRMED
Worker B: HELD -> EXPIRED
~~~

Cần **conditional state transition** atomically cùng cập nhật counter:

~~~text
CONFIRM if state=HELD and deadline valid
EXPIRE  if state=HELD and deadline elapsed
~~~

Chỉ một transition thắng, bất kể owner/leader thay đổi giữa chừng.

### 22.3. Retry không được cấp chỗ lần hai

Sau failover, nếu client retry create-hold với cùng business request ID:

- Nếu hold cũ committed: trả lại hold cũ.
- Nếu hold cũ không tồn tại và protocol cho phép retry: có thể tạo hold mới an toàn với cùng ý định.
- Nếu outcome không thể xác định: giữ `UNKNOWN/PENDING` và đối soát, không tự xác nhận hai hold.

### 22.4. Timestamp client không thay thế fencing/transaction

Client có thể gửi clock lệch hoặc cố tình đặt timestamp mới hơn để ghi đè. Không dùng `clientTime > previousTime` như điều kiện duy nhất xác lập quyền cấp phát hoặc quyền leader mới.

---

## 23. Session continuity sau failover

Người dùng vừa nhận xác nhận cập nhật profile, rồi API đọc được route tới replica khác:

~~~text
Write profile v12 ACK.
Failover.
Read profile -> v11.
~~~

Nếu contract hứa **read-your-writes** hoặc **linearizable read** cho phạm vi đó, đường đọc sau failover không được âm thầm quay về v11.

### 23.1. RYW khác durability

Nếu ACK yếu cho phép write bị rollback, không thể chỉ dùng session token để “bảo tồn” nội dung đã mất. Durability/commit policy và session consistency là hai điều kiện cần phân biệt.

### 23.2. Monotonic reads

Phiên đã thấy v12 rồi đọc lại v11 là hiện tượng đi lùi. Phải giữ session watermark/context hoặc dùng đường đọc đáp ứng yêu cầu.

### 23.3. Cache/search stale

Một authoritative DB có thể giữ v12 nhưng cache hoặc search index vẫn có v11. Ứng dụng cần fallback/wait/invalidate hoặc hiển thị trạng thái đồng bộ tùy business contract.

### 23.4. Replica catch-up và read barrier

Sau khi node mới được bầu, một read có yêu cầu consistency mạnh có thể cần leader xác minh quyền hiện tại và state machine đã apply tới commit point cần thiết. Không dùng stale read từ node vừa phục hồi làm bằng chứng write không tồn tại.

---

## 24. Recovery sau failover: xử lý các request ở trạng thái UNKNOWN

Một job reconciliation có thể duy trì những request cần xác minh:

~~~json
{
  "requestId": "hold-cart-9001",
  "tenantId": "tenant-7",
  "expectedOperation": "RESERVE",
  "resourceId": "seat-42-A01",
  "observedOutcome": "UNKNOWN",
  "lastAttemptAt": "2026-11-14T08:00:00Z",
  "attemptCount": 2
}
~~~

### 24.1. Quy trình khái niệm

~~~text
For each unresolved request:
  1. Xác định authoritative store/topology.
  2. Đọc idempotency ledger và business object nhất quán.
  3. Nếu result committed -> cập nhật outcome COMMITTED.
  4. Nếu có bằng chứng business reject -> REJECTED.
  5. Nếu có pending side effect -> kiểm tra provider/broker.
  6. Nếu có thể retry an toàn -> retry với cùng ID.
  7. Nếu không thể quyết định -> giữ UNKNOWN,
     cảnh báo và chuyển tới xử lý có giám sát.
~~~

### 24.2. Chống xử lý song song cùng một UNKNOWN

Hai reconciliation workers cùng xử lý một request có thể gây duplicate side effect. Cần claim/lease có điều kiện hoặc transaction/idempotent handler.

Nếu worker claim bằng TTL rồi bị pause, worker mới có thể nhận job; khi worker cũ tỉnh lại, fencing hoặc idempotency ở đích vẫn cần thiết.

### 24.3. Pending không nên kéo dài vô hạn

Đặt SLO và policy cho unresolved requests:

- Sau X phút: cảnh báo.
- Sau Y giờ: escalation.
- Nếu có payment captured nhưng chưa confirmed: ưu tiên đối soát.
- Nếu chưa có authoritative outcome: không báo khách “hoàn tất”.
- Nếu đã bù trừ: lưu terminal reason và audit.

Các ngưỡng phải theo nghiệp vụ, không có một con số chung cho mọi service.

### 24.4. Reconciliation phải có audit

Lưu:

~~~text
request ID
resource ID
old/new state
decision evidence
leader/epoch if relevant
payment reference
retry count
trace ID
human/system actor
~~~

Tránh log dữ liệu nhạy cảm không cần thiết; request ID không phải quyền truy cập vào thông tin khách hàng.

---

## 25. Quyền ghi theo lease: điểm dễ sai với đồng hồ

Một hệ có thể dùng **lease** thay vì chỉ election/quorum để giới hạn thời gian quyền owner.

~~~text
Owner A giữ lease đến thời điểm L.
A bị pause 20 giây.
Lease hết hạn.
Owner B nhận lease mới.
A tỉnh lại và tiếp tục thao tác.
~~~

### 25.1. Lease chỉ có ý nghĩa dưới giả định thời gian cụ thể

Một lease-based protocol có thể dựa vào clock monotonic, giới hạn độ lệch đồng hồ, độ trễ và quy tắc renewal. Nếu giả định sai, một owner cũ có thể tưởng lease vẫn hợp lệ.

Không so sánh đơn giản timestamp từ hai máy không đồng bộ để khẳng định an toàn.

### 25.2. Thu hồi quyền trên control plane chưa chặn data plane

Control plane cấp lease mới cho B. Nhưng nếu nơi lưu dữ liệu đích không kiểm tra owner generation, A vẫn có thể gửi lệnh.

Đây là lý do **fencing phải nằm ở điểm thay đổi dữ liệu có thẩm quyền**, hoặc mọi data-plane operation phải đi qua một protocol tự từ chối stale owner.

### 25.3. Không cấp mới quá sớm

Nếu service cấp B quyền khi chưa có điều kiện chứng minh A không thể commit nữa, có thể tạo split-brain. Một lease hết hạn cần được gắn vào toàn bộ safety proof, không phải thay cho majority/election khi hệ cần chúng.

### 25.4. Lock vs business idempotency

Ngay cả khi chỉ một worker giữ lock đúng lúc, cùng request có thể được xử lý lại sau crash giữa side effect và ACK. Do đó lock không thay thế idempotency và outcome ledger.

---

## 26. Membership thay đổi đồng thời với failover

Một cụm ban đầu:

~~~text
Configuration C1: voters {A, B, C}
A là leader.
~~~

Sau đó định chuyển sang:

~~~text
Configuration C2: voters {C, D, E}
~~~

Một election quorum của C1 có thể không giao với một quorum của C2 nếu cấu hình thay đổi tùy tiện.

### 26.1. Reconfiguration cần giao thức

Các hệ consensus có thể dùng joint consensus hoặc một cơ chế reconfiguration an toàn khác để bảo đảm các commit/election quorum giữa hai cấu hình không làm mất lịch sử đã committed.

Không tự viết:

~~~text
Step 1: đổi danh sách voter trong config file.
Step 2: restart tất cả node.
Step 3: mặc định leader mới có toàn bộ write.
~~~

mà không hiểu protocol.

### 26.2. Node mới phải có dữ liệu cần thiết

Một follower mới vừa tham gia có thể chưa bắt kịp log. Không nên cho nó trở thành leader nếu election rule không bảo vệ leader completeness.

### 26.3. Vừa rebalance vừa failover

Một shard đang migrate owner/placement và đồng thời mất leader đặt ra nhiều sự kiện cạnh tranh:

- Migration snapshot đã tới đâu?
- Delta replay có bắt kịp?
- Routing epoch nào là authoritative?
- Owner cũ có được phép nhận write mới?
- Voter set nào quyết định commit?
- Request đang dang dở thuộc đường cũ hay mới?

Hệ phải dựa vào metadata/consensus của engine, không chỉ đặt lại hostname mới cho shard.

### 26.4. Không dọn bản cũ trước khi có chứng cứ an toàn

Một bản dữ liệu được chuyển tới node mới nhưng chưa committed/verified theo migration protocol không phải lý do để xóa bản nguồn.

---

## 27. Availability trong cửa sổ failover

Một mô hình lý tưởng có thể minh họa:

~~~text
T0 Primary hoạt động bình thường.
T1 Mất primary.
T2 Detect failure.
T3 Election/quorum.
T4 New leader established.
T5 Drivers refresh routing.
T6 Clients retry operations.
T7 Background catch-up/reconciliation.
~~~

### 27.1. Không có một “failover duration” duy nhất

Người dùng có thể quan sát:

- Write unavailability.
- Read staleness.
- Transaction timeout.
- Retry spikes.
- P99 latency tăng.
- Background replica lag.
- Pending business requests.

T6 có thể xảy ra trước khi T7 hoàn tất. **Khôi phục nhận write** không nhất thiết bằng **mọi replica đã bắt kịp**.

### 27.2. Quyền ghi cần rõ trong mọi giai đoạn

| Giai đoạn | Có ai được commit write? | Client nên thấy gì? |
|---|---|---|
| Leader cũ còn quorum, trước sự cố | Leader hợp lệ theo protocol | Normal ACK |
| Quorum bị chia/chưa có leader hợp lệ | Có thể không có bên được commit | Retryable unavailable/timeout |
| Leader mới được bầu và đủ điều kiện | Leader mới trong phạm vi group | Route/retry với ID cũ |
| Replica cũ quay lại | Follower/catch-up theo protocol | Không tự nhận quyền ghi |
| Reconciliation | Service idempotent xử lý unknown | Status/PENDING/COMMITTED |

### 27.3. CAP và sự đánh đổi

Khi network partition làm các node không thể phối hợp để duy trì strong single-owner semantics, một phía có thể phải từ chối write. Đó là trade-off để bảo vệ consistency, không phải sự cố cần “sửa” bằng cách cho cả hai bên cùng xác nhận resource cuối.

### 27.4. Lưu request offline

Một API có thể trả `202 Accepted` và giữ intent trong queue ở phía bị cô lập, nhưng cần nói rõ:

- Request **chưa được authoritative commit**.
- Không được trình bày như đã cấp ghế.
- Queue có durability/retention riêng.
- Khi replay phải dùng idempotency key và conditional business operation.
- Nếu hết vé, request có thể bị từ chối sau này.

Không dùng `202 Accepted` như ngụy trang cho lời hứa `CONFIRMED`.

---

## 28. Observability: đo quyền ghi và thao tác dang dở

| Nhóm | Metric/log | Lý do |
|---|---|---|
| Election | Leader changes, term/epoch transitions | Nhận diện failover |
| Quorum | Quorum unavailable, election timeout | Thấy khi không thể commit |
| Routing | Not-primary/stale-owner redirects | Client còn route cũ |
| Write | Attempted, committed, rejected, unknown | Phân biệt outcome |
| Log | Last log index, commit index, applied index | Theo dõi khoảng trống log |
| Replication | Lag bytes/seconds per replica | Replica catch-up |
| Safety | Conflicting leaders/epoch violations | Cảnh báo nghiêm trọng |
| Fencing | Rejected stale token count | Stale worker còn hoạt động |
| API | 5xx, deadline exceeded, p95/p99 | Tác động người dùng |
| Retry | Retries per request ID, retry storms | Nguy cơ tải tăng |
| Idempotency | Duplicate requests with matching/mismatched payload | Bảo vệ business effect |
| Reconciliation | UNKNOWN age/count, pending payments | Những quyết định chưa rõ |
| Durability | Rollback incidents, journal/fsync lag | ACK policy và mất write |
| External | Duplicate charge, provider unknown, outbox backlog | Side effect ngoài DB |
| Consistency | RYW violations, stale index/cache rate | Trải nghiệm sau failover |
| Audit | Seat double-confirm, inventory invariant | Correctness nghiệp vụ |

### 28.1. Alert theo severity

- **Critical:** hai owner cùng commit write mâu thuẫn; double-confirm seat; committed entry biến mất theo contract; external stale worker ghi đè.
- **High:** lượng `UNKNOWN` hoặc paid-but-unconfirmed tăng; replica không bắt kịp; idempotency mismatch.
- **Medium:** election lặp nhiều lần; retry storms; routing redirects tăng; cache stale.
- **Info:** leader changed, replica joined/left, reconciliation completed.

### 28.2. Theo dõi cả trước, trong và sau sự cố

Một dashboard chỉ nhìn “primary healthy” có thể xanh ngay khi leader mới được bầu, nhưng số `UNKNOWN` từ các request trước đó vẫn đang chờ đối soát.

### 28.3. Audit bằng request ID xuyên dịch vụ

Kết nối trace:

~~~text
HTTP request K
DB transaction T
Reservation R
Outbox event E
Payment provider charge P
Notification N
~~~

Khi điều tra duplicate side effect, những ID này quan trọng hơn chỉ nhìn timestamp.

---

## 29. Runbook xử lý failover ở mức ứng dụng

### Bước 1 — Xác định phạm vi sự cố

- Cluster/group/partition nào mất leader?
- Read path nào vẫn phục vụ?
- Những API nào cần authority mạnh?
- Có thay đổi membership hoặc migration đang chạy không?

### Bước 2 — Xác định nguồn quyền hiện tại

Dựa vào driver/DBMS/control plane chính thức và quorum/term/epoch trạng thái; **không chỉ dựa trên node có TCP port còn mở**.

### Bước 3 — Dừng lời hứa không có commit evidence

Khi không đủ authority, từ chối hoặc trả `PENDING/UNKNOWN` phù hợp. Không trả `CONFIRMED` chỉ vì request đã tới old primary.

### Bước 4 — Giữ stable IDs

Mọi retry phải dùng cùng request ID, reservation ID/order ID và payment idempotency key theo policy.

### Bước 5 — Hạn chế retry storm

Cấu hình deadline, backoff, jitter và retry budget; theo dõi load leader mới. Không cho gateway tự replay mọi POST nếu thao tác không idempotent.

### Bước 6 — Kiểm tra authoritative history

Dùng consistency policy phù hợp để xác minh commit point/log/transaction ledger theo DBMS. Không dựa vào GSI/search/cache stale làm bằng chứng không có write.

### Bước 7 — Giải quyết UNKNOWN

- Có committed business object? Trả kết quả và hoàn tất request ledger.
- Có confirmed condition failure? Trả business conflict.
- Có external side effect? Đối soát provider trước khi retry.
- Không thể xác định? Giữ case mở, cảnh báo và không tự nhân side effect.

### Bước 8 — Reconcile những worker cũ

Kiểm tra lease/fencing/epoch. Đảm bảo worker cũ không tiếp tục ghi sau khi mất quyền.

### Bước 9 — Theo dõi hồi phục

Replica lag, retry rate, commit latency, p99, outbox backlog, idempotency duplicates và business invariants.

### Bước 10 — Viết postmortem

Ghi timeline, phạm vi ảnh hưởng, outcome unknown, nguồn evidence, số request cần đối soát, lỗi idempotency, những cam kết dữ liệu đã đạt/chưa đạt.

**Không chỉnh tay commit log, xóa file replica hoặc force promote node trái protocol nếu không có hướng dẫn khôi phục chính thức và chấp thuận của người chịu trách nhiệm.**

---

## 30. Kiểm thử sự cố: phải nhìn lịch sử, không chỉ dữ liệu cuối

Một kịch bản concurrency/failover cần ghi:

~~~text
request ID
client ID
operation type/key
invocation timestamp
response timestamp
outcome
term/epoch
leader/coordinator
replica commit point
business object version
external side-effect ID
~~~

### 30.1. Test 1 — commit rồi mất response

1. Gửi request K.
2. Cho transaction commit theo protocol.
3. Mô phỏng response tới client bị mất.
4. Client retry K sau failover.
5. Kiểm tra chỉ một reservation được tạo.
6. Kiểm tra client nhận kết quả đã persisted của K.

### 30.2. Test 2 — append nhưng chưa commit

1. Gửi command tới leader cũ.
2. Trì hoãn replication đủ để command chưa commit.
3. Failover sang leader mới.
4. Retry cùng K.
5. Xác định có hoặc không có entry cũ trong lịch sử mới.
6. Đảm bảo chỉ một quyết định nghiệp vụ terminal được thực hiện.

### 30.3. Test 3 — old leader còn sống

1. Tách old leader khỏi quorum.
2. Bầu leader mới trên phía đủ quyền.
3. Tiếp tục gửi write và strong read tới old leader.
4. Kiểm tra nó không xác nhận commit/read sai theo contract.
5. Đảm bảo stale worker/external destination từ chối fencing token cũ.

### 30.4. Test 4 — payment callback trùng

1. Provider thực hiện charge P.
2. App crash trước khi đánh dấu Order PAID.
3. Provider gửi callback P hai lần.
4. Client retry checkout K.
5. Kiểm tra chỉ một charge/confirm theo provider+business contract.
6. Nếu hold hết hạn, kiểm tra refund/compensation.

### 30.5. Test 5 — application-level lost update

Ngay cả khi DB chỉ có một leader hợp lệ, chạy 100 request cùng giữ ghế cuối. Kiểm tra **atomic conditional business operation** ngăn oversell.

### 30.6. Test 6 — failover với multi-region/resharding

1. Chuyển placement/membership trong staging.
2. Ghi request có term/epoch rõ.
3. Đồng thời failover có kiểm soát.
4. Kiểm tra retained committed entries, rejected stale owner và routing refresh.
5. Kiểm tra không có double side effect.

Không chủ động gây network partition, crash hoặc mất dữ liệu trên production ngoài quy trình đã được phê duyệt.

---

## 31. Bài tập 1: phân loại trạng thái write

Cho ba replica A/B/C và W=majority trong một hệ leader consensus.

Lịch sử:

~~~text
R1: leader nhận request, chưa append.
R2: leader append locally, chưa replicate.
R3: entry được committed theo protocol, client chưa ACK.
R4: client đã nhận ACK majority.
R5: primary nhận ACK yếu trước replication, rồi failover.
~~~

Hãy phân loại:

| Request | Có thể coi COMMITTED từ phía application? | Có thể UNKNOWN với client? | Có nguy cơ mất qua failover? |
|---|---|---|---|
| R1 | ? | ? | ? |
| R2 | ? | ? | ? |
| R3 | ? | ? | ? |
| R4 | ? | ? | ? |
| R5 | ? | ? | ? |

**Gợi ý:** phân biệt *trạng thái thật của database* với *trạng thái client có bằng chứng*. R3 đã committed nhưng client chưa biết. R5 phụ thuộc policy ACK và failure model, không phải “ACK nào cũng bền”.

## 32. Bài tập 2: nhận diện stale leader

Giả sử:

~~~text
Term 17: A leader.
Network chia A | B,C.
Term 18: B được bầu bởi B,C.
A vẫn nhận request từ client cũ.
~~~

Hãy trả lời:

1. A còn là process đang chạy không?
2. A có được ACK một write mới như authoritative committed nếu không đủ quorum không?
3. Vì sao term tăng và majority election giúp bảo vệ lịch sử?
4. Nếu A có local cache mới hơn B nhưng write chưa commit, A có được trả linearizable read không?
5. Nếu A gửi side effect tới service ngoài DB, cần gì để ngăn?
6. Driver nên xử lý redirect/retry thế nào?
7. Nếu không có quorum hợp lệ ở cả hai phía, có nên cho cả hai bên cùng nhận `CONFIRMED` không?

## 33. Bài tập 3: timeline ACK bị mất

Một client gửi request K:

~~~text
T0: Reserve K.
T1: Seat được đánh dấu HELD và request ledger commit.
T2: Leader gửi 200 OK.
T3: Response mất.
T4: New leader được bầu.
T5: Client retry K.
~~~

1. Outcome thật của K tại T1 là gì?
2. Vì sao timeout của client không phải chứng cứ rollback?
3. Làm thế nào leader mới trả lại reservation cũ?
4. Nếu K retry với quantity khác, xử lý ra sao?
5. Nếu GSI chưa có record nhưng base table đã commit, có được tạo record mới không?
6. Idempotency ledger nên lưu trong cùng transaction với Seat/Reservation như thế nào?
7. Nếu TTL xóa ledger quá sớm, retry muộn có thể gây gì?

## 34. Bài tập 4: log entry chưa committed

Log tại một thời điểm:

~~~text
Index:    1  2  3  4  5  6
A:        a  b  c  d  e  f
B:        a  b  c  d  e
C:        a  b  c  d
Committed through index 4.
~~~

A bị mất quyền, B trở thành leader theo một protocol phù hợp.

Câu hỏi:

1. Entry a–d phải được bảo vệ thế nào?
2. Entry e và f chắc chắn bị xóa không?
3. Vì sao không dùng “entry có trên hai node” làm định nghĩa commit cho mọi term của Raft?
4. Nếu client đã được báo success cho f trước commit, ứng dụng đã mắc lỗi gì?
5. Nếu một read trước đó nhìn thấy f rồi read sau thấy d, nguy cơ linearizability gì xuất hiện?
6. Có nên gửi email dựa trên entry f chưa committed không?

## 35. Bài tập 5: MongoDB write concern

Một hệ có:

~~~text
3-node replica set.
Primary A.
Write concern ban đầu w:1.
Client nhận ACK.
A mất liên lạc với majority trước khi replica khác nhận write.
B được bầu primary.
~~~

Hãy trả lời:

1. Write cũ có thể bị rollback không?
2. Nếu đổi thành `w: "majority"`, thuộc tính nào cải thiện?
3. `j: true` liên quan gì?
4. Nếu `wtimeout` xảy ra, có thể kết luận write chưa áp không?
5. Causal session có thay thế majority durability không?
6. Read secondary sau failover có phù hợp để xác minh business outcome không?
7. Retry transaction commit nên theo semantics driver thế nào?

## 36. Bài tập 6: Cassandra và Redis có gì khác Raft?

So sánh:

| Tình huống | Cassandra regular write | Redis primary/replica | Raft leader group |
|---|---|---|---|
| Có một primary bắt buộc cho mọi write? | ? | ? | ? |
| Failover có leader election theo cùng nghĩa? | ? | ? | ? |
| Write timeout có thể đã áp một phần? | ? | ? | ? |
| Có công cụ CAS/conditional? | ? | ? | ? |
| ACK yếu có thể bị mất khi sự cố? | ? | ? | ? |
| Cần business idempotency khi retry? | ? | ? | ? |
| Một lệnh atomic có tự bao phủ payment? | ? | ? | ? |

**Gợi ý:** không ép mọi hệ vào mô hình term leader. Hãy dùng API/consistency semantics của từng sản phẩm.

## 37. Bài tập 7: thiết kế checkout chống double-charge

Bối cảnh:

~~~text
Inventory authoritative DB
Order DB
External payment provider
Message broker
Email service
Client có thể retry cùng checkout
Failover có thể xảy ra ở mọi bước
~~~

Thiết kế:

1. Stable `checkoutRequestId`, `orderId`, `reservationId`.
2. Stable provider idempotency key.
3. Reservation conditional update.
4. Request ledger/transaction boundary.
5. Outbox event `OrderPaid` và idempotent consumer.
6. Reconciliation khi payment response unknown.
7. State machine `HELD -> CONFIRMED/EXPIRED/CANCELLED`.
8. Policy refund/void khi payment thành công sau expiry.
9. Fencing nếu worker lease có thể bị mất.
10. Metrics `doubleCharge`, `unknownPayments`, `outboxLag`, `duplicateRequest`.

Trình bày timeline ít nhất ba loại crash: trước commit, sau commit trước ACK, sau provider charge trước update Order.

## 38. Bài tập 8: viết runbook cho failover

Một hệ trong staging có:

~~~text
A leader cũ
B leader mới
100 requests gặp timeout
12 payment callbacks đang pending
15 outbox events chưa published
Một replica lag 30 giây
Một background worker đã mất lease
~~~

Yêu cầu:

- Phân loại request nào cần đối soát.
- Chọn authoritative status source.
- Chặn stale worker.
- Điều tiết retry.
- Kiểm tra nghiệp vụ không bị cấp/thu tiền hai lần.
- Xử lý outbox có thể publish trùng.
- Chọn metrics và điều kiện kết thúc incident.
- Viết timeline và postmortem có bằng chứng.

Không thao tác production theo runbook thử nghiệm mà chưa có phê duyệt.

---

## 39. Những ngộ nhận thường gặp

| Ngộ nhận | Hậu quả | Cách hiểu đúng |
|---|---|---|
| “Old primary còn mở port nên còn được ghi.” | Split-brain | Quyền ghi do protocol/epoch/quorum quyết định |
| “Có leader mới thì old leader tự ngừng ngay.” | Stale owner gửi side effect | Term/lease + fencing tại đích |
| “Append local là committed.” | Acknowledge write sẽ bị thay thế | Chờ commit rule thật |
| “Hai replica chứa entry là đủ với mọi Raft term.” | Suy sai commit safety | Hiểu current-term commit rule |
| “Client timeout nghĩa request không chạy.” | Retry tạo trùng | Outcome UNKNOWN, idempotency |
| “ACK nào cũng sống qua failover.” | Mất write đã hứa | Chọn durability/write concern theo contract |
| “Majority ACK nghĩa tất cả replica đã có dữ liệu.” | Replica đọc stale | Read consistency/lag riêng |
| “Commit xong là GSI/search đã thấy.” | Không tìm thấy record mới | Fallback authoritative source |
| “Stale 404 chứng minh write thất bại.” | Tạo object trùng | Verify với nguồn nhất quán |
| “Retry với ID mới là an toàn.” | Duplicate reservation/payment | Stable request ID |
| “CAS retry conflict tức là user khác thay dữ liệu.” | Báo sai outcome của chính request | Tra request ledger |
| “Distributed lock TTL chặn worker cũ.” | Stale worker tiếp tục ghi | Fencing token ở đích |
| “Fencing thay thế idempotency.” | Cùng owner xử lý trùng | Cần cả quyền và dedup |
| “Một leader ngăn mọi overselling.” | Read-then-write race | Atomic conditional business invariant |
| “Raft cung cấp exactly-once cho mọi nghiệp vụ.” | Duplicate command cùng ý định | Dedup theo client request ID |
| “Cassandra QUORUM là Raft leader failover.” | Dùng sai mô hình | Hiểu coordinator/CL/LWT |
| “Redis WAIT bằng transaction quorum toàn hệ.” | Đánh giá sai durability | Hiểu replication/persistence semantics |
| “DynamoDB GSI là đường xác minh strong.” | Đọc stale sau write | Base-table read/transaction status phù hợp |
| “Payment ở trong DB transaction.” | Double-charge khi crash | Provider idempotency + reconciliation |
| “Outbox publish đúng một lần tuyệt đối.” | Consumer side effects trùng | At-least-once + idempotent consumer |
| “Lỗi retry chỉ làm chậm hơn.” | Thundering herd | Backoff/jitter/deadline |
| “Cứ chuyển lại A khi A sống.” | Mất lịch sử mới | A phải catch-up và nhận quyền hợp lệ |
| “Leader healthy nghĩa incident kết thúc.” | UNKNOWN requests vẫn tồn tại | Reconcile và kiểm tra business invariants |
| “Term là timestamp client.” | Sai thứ tự quyền | Logical generation theo protocol |
| “Mọi hệ NoSQL đều bầu primary.” | Thiết kế sai Cassandra/multi-leader | Đọc write authority model từng sản phẩm |

---

## 40. Checklist trước khi đưa failover lên production

1. **Phạm vi:** leader/owner thuộc key, shard, group hay region nào?
2. **Authority:** ai có quyền ghi sau election/cutover, ai có thể thu hồi quyền?
3. **Quorum/membership:** voter set và reconfiguration được bảo vệ thế nào?
4. **Term/epoch:** message stale được phát hiện thế nào?
5. **Fencing:** external side effect có từ chối owner cũ không?
6. **Commit rule:** received/appended/replicated/committed/applied/ACK khác nhau ở đâu?
7. **Durability:** ACK yêu cầu memory, journal, fsync, majority hay điều kiện khác?
8. **Unknown outcome:** timeout được ghi nhận và đối soát thế nào?
9. **Idempotency:** request key ổn định, unique scope, payload hash và retention?
10. **CAS/transaction:** business invariant có nằm trong atomic boundary đúng không?
11. **Retries:** driver/gateway/application phối hợp retry budget thế nào?
12. **Strong read:** outcome được xác minh qua nguồn nào sau failover?
13. **Transaction retries:** callback có side effect ngoài DB không?
14. **External systems:** payment, broker, email có idempotency/reconciliation không?
15. **Outbox/inbox:** publish trùng có an toàn không?
16. **Session consistency:** read-your-writes qua region/cache/replica còn đáp ứng không?
17. **Workload:** leader mới có chịu nổi retry storm không?
18. **Observability:** election, term, unknown requests, log lag và business invariants?
19. **Recovery:** old primary quay lại thành follower và catch-up theo protocol?
20. **Testing:** fault-injection trong staging, commit-before-ACK, stale leader và network partition?
21. **Runbook:** ai được force failover, có rủi ro data loss và thủ tục phê duyệt gì?
22. **Post-incident:** bao nhiêu request được đối soát, side effect bị trùng hoặc mất?

Checklist là công cụ thiết kế; **một bảo đảm chỉ có giá trị trong phạm vi và mô hình sự cố được DBMS hoặc protocol thực sự hỗ trợ**.

---

## 41. Tổng kết

**Quyền ghi sau failover và các thao tác đang dang dở** là hai mặt của cùng một bài toán: một hệ phân tán phải vừa xác định **ai được quyền quyết định ghi**, vừa xác định **lệnh nào thực sự thuộc lịch sử được công nhận** khi node, mạng hoặc leader thay đổi.

Những nguyên tắc quan trọng:

1. **Node còn sống không đồng nghĩa còn quyền ghi.** Leader/owner cần được quyết định bằng term/epoch, quorum, membership hoặc authority protocol thích hợp.
2. **Old leader phải bị vô hiệu hóa trong data plane**, không chỉ xóa tên khỏi routing metadata; external side effects cần fencing nếu có stale worker.
3. **Received, appended, replicated, committed, applied và ACK là các mốc khác nhau.** Không hứa thành công dựa trên mốc yếu hơn commit contract.
4. **Write chưa committed có thể bị thay thế hoặc được giữ lại**, tùy protocol; client không thể suy outcome chỉ từ timeout.
5. **Write đã commit có thể chưa được client biết.** Retry phải dùng stable request ID, deduplication và authoritative outcome verification.
6. **Quorum/consensus không tự làm business operation idempotent hoặc atomic nhiều bước.** Cần CAS/transaction, state machine và request ledger.
7. **Write concern/durability quyết định những gì sống qua failover** theo mô hình lỗi; read concern/session consistency quyết định những gì người dùng quan sát.
8. **Không ép mọi NoSQL vào single-leader.** MongoDB replica set, Cassandra regular write/LWT, Redis primary replication và DynamoDB managed services có semantics khác nhau.
9. **Payment, broker và email nằm ngoài DB transaction.** Dùng outbox, provider idempotency, reconciliation và compensation.
10. **Incident chưa kết thúc khi leader mới đã khỏe.** Phải giải quyết các request UNKNOWN, replica lag, duplicate side effects và mọi invariant nghiệp vụ.

**Câu ghi nhớ: “Sau failover, đừng hỏi chỉ ‘node nào đang nhận write?’. Hãy hỏi ‘ai được phép commit, write nào đã committed, request nào chưa rõ kết quả và cơ chế nào ngăn chủ cũ hoặc retry tạo thêm side effect?’”**
