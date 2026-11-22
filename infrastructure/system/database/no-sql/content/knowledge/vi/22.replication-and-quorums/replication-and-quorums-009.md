# Replication lag, dữ liệu đọc cũ và theo dõi tiến độ bản sao trong NoSQL

## 1. Tình huống mở đầu: ghi thành công nhưng đọc lại không thấy

Một ứng dụng quản lý đơn hàng có một node ghi chính và hai bản sao phục vụ đọc. Khách hàng chuyển trạng thái đơn từ `DRAFT` sang `SUBMITTED`:

```text
             GHI                              ĐỌC

Client A -----------------> Primary P
                            order v8
                              |
                            ACK OK
                              |
                 +------------+------------+
                 |                         |
                 v                         v
            Replica R1                 Replica R2
            order v8                   order v7
                 ^                         ^
                 |                         |
              GET -> v8              GET -> v7
```

Ứng dụng vừa trả “Đã nộp đơn thành công”, nhưng màn hình lịch sử đơn truy cập R2 lại hiển thị trạng thái cũ. Người dùng tưởng thao tác thất bại và nhấn gửi lại.

Đây là ví dụ về **replication lag** (*độ trễ sao chép*) và **stale read** (*đọc dữ liệu cũ*). Chúng liên quan đến nhau nhưng không đồng nghĩa:

- **Replication lag:** mức độ một bản sao chưa bắt kịp tiến độ thay đổi ở nguồn hoặc leader.
- **Stale read:** một lần đọc thực tế trả phiên bản cũ hơn phiên bản cần thiết theo hợp đồng đọc của ứng dụng.
- **Progress tracking:** theo dõi mốc thay đổi mà mỗi replica đã **nhận, ghi bền, áp dụng và có thể phục vụ**.

Không phải cứ có lag là mọi read sai. Một replica trễ 100 sự kiện vẫn có thể trả đúng dữ liệu của một đơn không thay đổi. Ngược lại, một độ trễ chỉ vài chục mili giây vẫn gây lỗi nghiệp vụ nếu ứng dụng dùng bản sao cũ để quyết định giữ chỗ, thu hồi quyền hoặc thanh toán.

Trong chương **Sao chép và quorum**, mục tiêu là hiểu chính xác bản sao đang ở đâu, vì sao dữ liệu đọc có thể cũ, điều kiện nào một write thực sự được xác nhận, và làm cách nào để quan sát, đặt SLO và khắc phục an toàn.

## 2. Thuật ngữ và mô hình sao chép

Một hệ phân tán có thể có **primary/secondary**, **leader/follower**, hoặc mô hình không có leader đơn nhất. Vì thế trước khi dùng chữ “lag”, cần nêu **so với mốc nào** và **đối với thành phần nào**.

| Thuật ngữ | Diễn giải |
|---|---|
| **Primary/leader** | Node có vai trò điều phối ghi hoặc xác lập thứ tự ở một phạm vi nhất định |
| **Replica/follower** | Node nhận và áp dụng thay đổi từ nguồn hay từ giao thức sao chép |
| **Log position / offset** | Vị trí đơn điệu trong nhật ký thay đổi, khi hệ có log phù hợp |
| **Commit index / majority commit point** | Mốc được coi là đã commit theo giao thức ở những hệ có khái niệm này |
| **Received position** | Vị trí đã nhận qua mạng nhưng chưa chắc đã bền hoặc đã áp dụng |
| **Durable position** | Vị trí đã được ghi bền theo cơ chế lưu trữ của replica |
| **Applied position** | Vị trí đã được áp dụng vào trạng thái để phục vụ thao tác |
| **Visible position** | Mốc có thể quan sát qua một đường đọc cụ thể, có thể chịu thêm refresh/indexing |
| **Watermark** | Dấu mốc cho biết thành phần đã hoàn tất xử lý tới đâu |
| **Staleness/freshness** | Độ cũ hoặc độ mới của dữ liệu mà client quan sát |
| **Replication lag** | Khoảng cách tiến độ giữa bản sao và mốc tham chiếu |
| **Catch-up** | Quá trình replica xử lý các thay đổi bị tồn đọng |
| **Reconciliation/repair** | Phát hiện và sửa khác biệt giữa các bản dữ liệu |

### Không phải mọi NoSQL đều có một “primary”

MongoDB replica set và Redis primary–replica có đường sao chép tương đối dễ hình dung theo leader. Nhưng Cassandra có mô hình nhiều replica, coordinator, consistency level và cơ chế sửa chênh lệch riêng; không có một số `primaryOffset - replicaOffset` phổ quát cho mọi partition.

Trong DynamoDB, người dùng dịch vụ managed không được truy cập tất cả log/offset nội bộ. Đôi khi chỉ có chỉ số replication liên vùng hoặc những phép đo ứng dụng tự xây.

Vì vậy, **không sao chép công thức đo lag của hệ này sang hệ khác** khi không có cùng mô hình dữ liệu hoặc API.

## 3. Bốn giai đoạn cần phân biệt: nhận, bền, áp dụng và nhìn thấy

Một write có thể đi qua nhiều mốc:

```text
Primary/leader
    |
    | 1. Log record được tạo ở nguồn
    v
Network replication
    |
    | 2. Replica RECEIVED
    v
Replica buffer / local log
    |
    | 3. Replica DURABLE theo persistence policy
    v
Replica storage / journal
    |
    | 4. Replica APPLIED vào trạng thái
    v
Read-serving state
    |
    | 5. Index/search REFRESH nếu đường đọc yêu cầu
    v
Client-visible result
```

Sơ đồ là **mô hình khái niệm**, không phải trình tự thực thi chính xác của mọi engine. Một số hệ apply vào memtable trước khi log fsync; một số có snapshot, batching, asynchronous indexing hoặc các checkpoint khác. Điều cần học là **các mốc không đồng nghĩa nhau**.

Giả sử một replica báo:

```text
received position = 108
durable  position = 106
applied  position = 104
visible  position = 104
leader committed  = 110
```

Ta có thể suy luận:

- Replica đã nhận thông tin đến 108.
- Chỉ có thể khẳng định mức bền đến 106 theo định nghĩa metric.
- Read có thể mới nhất đến 104, nếu đó là applied/visible watermark của đường đọc đang dùng.
- Write tại vị trí 109–110 chưa chắc đã tới replica.

**Không được suy luận “replica đã nhận v108 nên GET phải trả v108”.** Dữ liệu có thể chưa apply, chưa refresh hoặc đã được lưu dưới một cơ chế khác.

### Một log có thể có nhiều mốc commit

Ví dụ hệ dựa trên đồng thuận có thể phân biệt:

```text
log appended      = 110
majority committed= 108
replica applied   = 105
```

Các mục log 109–110 chưa chắc được coi là committed và có thể cần xử lý khác khi leader failover. Vì vậy, đo replica lag so với **đầu log chưa commit** có ý nghĩa khác đo so với **commit point**.

## 4. Ba cách đo replication lag và điều kiện áp dụng

### 4.1. Lag theo số phiên bản hoặc vị trí log

Nếu cả nguồn và replica dùng **cùng một không gian offset đơn điệu**:

\[
L_{\text{position}}(r)
=
\operatorname{CommittedPosition}_{source}
-
\operatorname{AppliedPosition}_{r}
\]

Ví dụ:

```text
Source committed = 10,250
Replica applied  = 10,010
Position lag     = 240 entries
```

Đây là **240 mục log**, không phải 240 mili giây. Mỗi mục log có thể chứa khối lượng công việc khác nhau. Nếu hệ dùng byte offsets, khoảng cách có thể tính bằng **bytes**; một offset không nhất thiết tương ứng một business event.

Chỉ trừ offset khi chúng thuộc **cùng log generation/epoch và cùng thứ tự có thể so sánh**. Sau resharding, failover, truncate hoặc đổi nguồn, các con số có thể không còn cùng hệ tọa độ.

### 4.2. Lag theo thời gian của mốc đã áp dụng

Trong hệ có timestamp/optime của từng log entry, một phép đo thường gặp:

\[
L_{\text{time}}(r)
=
\operatorname{Timestamp}_{source\ checkpoint}
-
\operatorname{Timestamp}_{replica\ checkpoint}
\]

Ví dụ giả định:

```text
Timestamp của entry mới nhất ở source: 10:00:12
Timestamp của entry mới nhất applied ở R2: 10:00:08
Reported lag: khoảng 4 giây
```

**Giới hạn:** phải biết timestamp là **logical time, commit timestamp, event time hay wall-clock time**, và các đồng hồ có đồng bộ hay không. Hai node không có đồng hồ đáng tin cậy có thể cho số âm hoặc số dương sai lệch.

Nếu **nguồn không có ghi mới**, thời điểm cuối cùng của replica có thể rất cũ mà replica đã bắt kịp hoàn toàn. Ví dụ source và replica đều apply đến entry 10:00:08, lúc kiểm tra là 10:10:00: “entry cuối cùng đã 9 phút 52 giây” **không phải lag 9 phút 52 giây**.

### 4.3. Lag của một lần đọc theo version nghiệp vụ

Nếu source có version theo aggregate:

```json
{
  "_id": "ORD-1001",
  "tenantId": "T01",
  "status": "SUBMITTED",
  "version": 8
}
```

và replica/read model trả version 7, ta biết **truy vấn đó bị trễ ít nhất một version**. Nhưng không thể suy trực tiếp 1 version tương đương bao nhiêu giây nếu thời gian tạo các version khác nhau.

Trong trường hợp này:

\[
\Delta version = version_{source} - version_{read}
\]

là metric theo **một aggregate có version tăng đơn điệu**, không phải khoảng cách giữa mọi document. Version 8 của `ORD-1001` không thể so tùy ý với version 12 của `ORD-2002`.

### Khi nào dùng loại đo nào?

| Tín hiệu | Phù hợp khi | Không thể kết luận trực tiếp |
|---|---|---|
| Offset/log gap | Có chung log và thứ tự tuyến tính | Độ trễ theo giây, correctness của từng read |
| Timestamp/optime gap | Timestamp có nghĩa rõ và cùng phạm vi | Mọi client đều đang đọc cũ, giới hạn freshness tuyệt đối |
| Applied/commit position | Cần theo dõi catch-up và read barrier | Dữ liệu đã durable, nếu metric chỉ là applied |
| Aggregate version | Một record/read model có version chuẩn | Tiến độ các partition/record khác |
| Synthetic probe latency | Muốn đo thời gian một write hiện ở read path cụ thể | Không chứng minh mọi record đều cập nhật trong đúng thời gian đó |

## 5. Stale read không đồng nghĩa dữ liệu đã mất

Hãy phân biệt ba trường hợp:

### Trường hợp A — Chưa sao chép

```text
P: version 8
R: version 7
Network queue: chứa update v8
```

Replica chưa nhận hoặc chưa áp dụng update. Nếu mạng/worker phục hồi và backlog còn, nó có thể tự bắt kịp.

### Trường hợp B — Đã sao chép nhưng chưa xuất hiện trên đường đọc

```text
Source DB: v8
Search sink: đã index request v8
Search refresh: chưa hoàn tất
_search: vẫn trả v7
```

Đây có thể là **search visibility lag**, không nhất thiết là replication lag của database nguồn. Một số engine search có refresh gần-thời-gian-thực, nên ACK ghi index không tự đồng nghĩa kết quả đã thấy ngay trong search.

### Trường hợp C — Write thực sự không tồn tại sau failover

```text
Primary ACK local write v8
Secondary chưa nhận v8
Primary mất hẳn
Secondary được bầu lại với v7
```

Nếu hợp đồng ACK yếu cho phép rollback của write chưa đạt mức an toàn, v8 có thể không còn trong lịch sử được chọn. Đây không chỉ là “replica vẫn hơi lag”; còn liên quan **durability và failover semantics**.

**Khi điều tra phải hỏi:** “Bản mới chưa đến, đã đến nhưng chưa nhìn thấy, hay không còn trong authoritative history?”

## 6. Timeline một replica chậm và trải nghiệm người dùng

Giả sử A là primary, B và C là secondary. Không có writer cạnh tranh:

| Thời điểm | Primary A | Secondary B | Secondary C | Quan sát |
|---|---|---|---|---|
| 10:00:00.000 | Order v7 | v7 | v7 | Cả hệ đã bắt kịp |
| 10:00:00.010 | Nhận cập nhật v8 | v7 | v7 | Write đang xử lý |
| 10:00:00.030 | ACK theo policy được chọn | v8 | v7 | Write có thể hoàn tất dù C trễ |
| 10:00:00.040 | v8 | v8 | v7 | GET từ C trả v7 |
| 10:00:00.160 | v8 | v8 | v8 | C bắt kịp |

Các mốc là **số minh họa**, không phải benchmark của một engine cụ thể.

Nếu client A ghi xong rồi một request khác bị route tới C, ứng dụng có thể thấy **read-your-writes violation** so với yêu cầu nghiệp vụ. Nếu một người dùng khác chỉ đọc dữ liệu tham khảo và chấp nhận cũ 150 ms, hệ có thể vẫn đáp ứng hợp đồng của API đó.

### Không gộp mọi read path thành một

Một hệ có thể hỗ trợ đồng thời:

```text
GET /orders/{id}/authoritative -> primary/strong path
GET /orders/{id}/fast          -> replica, stale có giới hạn
GET /orders/search             -> search projection, eventual
GET /orders/dashboard          -> aggregation, lag riêng
```

Cùng một đơn hàng nhưng có thể tồn tại **nhiều độ trễ độc lập**. Cần định nghĩa hợp đồng theo API thay vì nói “MongoDB/Redis/Cassandra này strong hay eventual” cho toàn sản phẩm.

## 7. Các hiện tượng thường xuất hiện khi đọc bản sao trễ

### 7.1. Read-your-writes bị phá vỡ

```text
Client A: W(order=v8) -> ACK
Client A: R(order)    -> v7
```

Nếu API cam kết read-your-writes cho cùng session, đây là vấn đề. Một thao tác đọc qua replica khác mà không mang thông tin session có thể gây ra hiện tượng đó.

### 7.2. Monotonic reads bị phá vỡ

```text
Client B: READ từ R1 -> v8
Client B: READ từ R2 -> v6
```

Client đã thấy thông tin mới rồi lại quay về trạng thái cũ. Có thể xảy ra khi load balancer thay replica giữa hai request.

### 7.3. Cross-key inconsistency

Một worker thực hiện:

```text
WRITE approved=true
WRITE published=true
```

Reader từ hai bản sao hoặc hai partition thấy:

```text
READ published -> true
READ approved  -> false
```

Nếu nghiệp vụ yêu cầu không công bố trước phê duyệt, việc đọc các field từ những mốc không tương thích là vấn đề. Giải pháp có thể là **gộp invariant vào một aggregate/transaction**, dùng một consistent snapshot hoặc enforce invariant ở nguồn.

Không được suy rằng thêm một session token cho **một key** tự tạo transaction atomic cho **hai key khác nhau**.

### 7.4. Quyết định nghiệp vụ dựa trên stale data

Ví dụ đáng ngại:

```text
R2 báo ghế A12 AVAILABLE (v7)
Primary đã commit ghế HELD (v8)
API xác nhận giữ ghế dựa vào R2
```

Chỉ **đọc từ replica để hiển thị gợi ý** có thể chấp nhận. Nhưng **xác nhận giữ ghế** phải dùng conditional update hoặc transaction phù hợp ở nguồn có thẩm quyền.

### 7.5. Stale authorization

Nếu quyền đọc tài liệu đã bị thu hồi ở nguồn nhưng cache/search vẫn chứa ACL cũ, việc tiếp tục trả nội dung có thể gây rò rỉ dữ liệu. Với các invariant quyền nghiêm ngặt, đường đọc cần kiểm tra nguồn có thẩm quyền hoặc dùng **fail-closed** khi không xác minh được quyền hiện hành.

**TTL không phải một thay thế an toàn cho quyết định phân quyền tức thời**.

## 8. Lag và nhất quán khác nhau: “ACK majority” chưa nói mọi replica mới nhất

Giả sử replica set có ba thành viên P, R1, R2:

```text
P:  v8 committed
R1: v8 đã tham gia majority
R2: v7 đang trễ
```

Ghi đã đủ **majority 2/3** vẫn **không bắt buộc R2 ngay lập tức cập nhật**. Việc một read từ R2 thấy v7 không tự phủ nhận rằng write đã đạt majority.

### Cần phân biệt ba cam kết

1. **Write acknowledgment:** đã có đủ node/điều kiện để xác nhận write chưa?
2. **Read consistency:** đường đọc có bắt buộc thấy write đã được commit trước đó theo thời gian thực hoặc session không?
3. **Durability:** write ACK tồn tại sau loại crash/failover nào?

Chúng có liên quan nhưng không phải cùng một thuộc tính.

### Quorum read/write và công thức giao nhau

Trong mô hình quorum đơn giản với N replica, nếu các tập đọc/ghi có kích thước R và W:

\[
R+W>N
\]

thì chúng phải có ít nhất một thành viên giao nhau, với điều kiện **cùng tập replica và cùng epoch/topology**.

Ví dụ N=3, R=2 và W=2:

```text
Write ACK: P + R1
Read from: R1 + R2
Intersection: R1
```

Nhưng **quorum intersection không tự chứng minh linearizability**. Hệ còn phải có quy tắc xác định phiên bản mới nhất, xử lý concurrent writers, timestamps, failover, read repair và điều kiện phục vụ response. Đặc biệt ở hệ dùng timestamp/last-write-wins, một replica có thể chứa nhiều phiên bản ứng với những quy tắc phân xử khác nhau.

Ngược lại, một hệ dùng leader/consensus log có thể bảo vệ commit history nhưng vẫn cho phép **local stale reads** như một chế độ đọc riêng.

## 9. Theo dõi mốc tiến độ theo nguồn: reference point phải được xác định

Nếu lấy **mốc leader đang ghi dở** để so với applied position ở replica, đồ thị sẽ khác khi lấy **mốc majority committed**.

Ví dụ:

```text
Leader appended        = 109
Leader committed       = 106
Replica received       = 108
Replica durable        = 105
Replica applied        = 103
```

Ta có thể tính:

```text
Backlog nhận so với appended   = 109 - 108 = 1
Backlog apply so với committed = 106 - 103 = 3
Backlog durable so với commit  = 106 - 105 = 1
```

Những con số này **không hoán đổi được**. Nếu metric chỉ công bố `received`, không được đặt tên “read freshness” cho nó.

### Một số hệ dùng term/epoch

Một index 1.000 trong nhiệm kỳ log mới không thể luôn so thẳng với 1.001 thuộc log cũ đã bị rollback. Mốc tiến độ nên gắn với **log identity/term/epoch** và một nguồn authority ổn định.

Khi reinitialize replica từ snapshot hoặc resharding, việc reset offset có thể tạo lag âm, lag tăng vô hạn hoặc biểu đồ nhảy nếu dashboard không xử lý thay đổi mốc đúng.

## 10. MongoDB: theo dõi optime, replSet status và secondary lag

Trong MongoDB replica set, quá trình sao chép sử dụng oplog và các trạng thái tiến độ tương ứng. Khi làm việc bằng `mongosh`, các lệnh quan sát phổ biến:

```javascript
rs.status();
rs.printSecondaryReplicationInfo();
```

Hoặc dùng database command:

```javascript
db.adminCommand({ replSetGetStatus: 1 });
```

Trong kết quả có thể thấy các thành viên, trạng thái `PRIMARY/SECONDARY`, thời điểm/optime và những thông số liên quan đến replication/heartbeat, tùy phiên bản MongoDB.

### 10.1. Cách đọc optime

Một kết quả **minh họa**, không phải JSON output nguyên văn:

```text
Member        State       Last applied optime
P             PRIMARY     10:00:12
R1            SECONDARY   10:00:12
R2            SECONDARY   10:00:08

R2 is behind P by about 4 seconds (under timestamp-based comparison).
```

Đọc đủ bối cảnh:

- Đây là **applied optime**, durable optime hay một timestamp khác?
- Primary đang có write mới liên tục không?
- Có sự kiện election/failover gần đây không?
- R2 đang INITIAL_SYNC, RECOVERING hay SECONDARY thông thường?
- Oplog ở nguồn còn đủ lịch sử cho R2 bắt kịp không?

### 10.2. Oplog window quan trọng hơn số lag đơn lẻ

Nếu replica trễ lâu hơn khoảng lịch sử oplog mà source còn giữ, nó có thể không thể phát lại mọi thay đổi còn thiếu theo đường incremental bình thường và phải thực hiện **initial sync/resync** theo quy trình của MongoDB.

```text
Oplog retained:
  [position 5,000 ........................ 9,000]

Replica last applied:
   position 4,200

Required entries 4,201..4,999 đã bị loại khỏi oplog
=> Không thể đơn giản replay phần còn lại
```

Oplog window không phải một hằng số giờ được bảo đảm độc lập workload; tốc độ ghi và cấu hình lưu trữ quyết định nó thay đổi thế nào.

### 10.3. Write concern và read preference

Ví dụ ghi có majority:

```javascript
db.orders.insertOne(
  {
    _id: "ORD-1001",
    status: "SUBMITTED",
    version: 8
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

Trong driver/triển khai được hỗ trợ, đọc từ secondary còn lag có thể trả version cũ tùy read concern và session. **Write concern majority không đồng nghĩa tất cả secondary đã apply write**.

MongoDB có **causally consistent sessions** và các mức read/write concern với điều kiện sử dụng riêng, như `majority`, `snapshot` và `linearizable` trên những đường được hỗ trợ. Muốn bảo vệ read-your-writes qua secondary, cần xem **tài liệu session, read concern, write concern và driver phiên bản đang sử dụng**, không chỉ bật `readPreference: secondary` rồi kỳ vọng tự có bảo đảm.

### 10.4. Các tín hiệu chẩn đoán

- Oplog/apply lag và trạng thái thành viên.
- Replication throughput, network latency, election events.
- Disk I/O, CPU, apply backlog, storage pressure.
- Thời gian initial sync, snapshot hoặc catch-up.
- Chênh lệch giữa optime applied và durable nếu metric có.
- Số lượng truy vấn đọc từ secondary và mức stale mà ứng dụng thực sự quan sát.

**Một phép đo optime toàn replica không thay thế kiểm thử read path của ứng dụng** nếu ứng dụng còn đi qua Redis cache hoặc search index.

## 11. Redis: offset replication, ACK replica và rủi ro đọc trễ

Redis hỗ trợ replication từ primary sang replica, thường bất đồng bộ. Quan sát:

```redis
INFO replication
```

Tùy phiên bản, output có thể chứa:

```text
role:master
connected_slaves:2
master_repl_offset:900000
slave0:... offset=899800,lag=0
slave1:... offset=870000,lag=4
```

**Đây là ví dụ minh họa của field/format thường gặp; tên role/slave và trường output có thể thay đổi theo phiên bản hoặc công cụ.**

### 11.1. Offset lag khác time lag

Nếu primary ở offset 900.000 và replica R1 ACK offset 899.800:

\[
L_{\text{offset}} = 900000 - 899800 = 200
\]

Đây là khoảng cách **tiến độ stream theo đơn vị offset**, không phải “200 thao tác nghiệp vụ” hoặc “200 ms”.

Trong các trường `slave0:...lag=N`, con số `lag` thường biểu diễn **thời gian từ lần ACK/heartbeat gần nhất của replica** theo semantics của Redis; không được mặc định nó bằng độ tuổi của mọi key được đọc từ replica.

### 11.2. Replica ACK không mặc nhiên đã fsync

```redis
WAIT 1 1000
```

Lệnh này yêu cầu chờ một số replica xác nhận tiến độ replication của những write trước đó trên kết nối client theo hợp đồng Redis. Kết quả là số replica thực sự đáp ứng; phải kiểm tra kết quả chứ không chỉ kiểm tra lệnh không báo lỗi.

**Giới hạn:** `WAIT` không làm mọi read từ replica linearizable và không tự đồng nghĩa dữ liệu đã bền trên disk. Một số phiên bản hỗ trợ thêm cơ chế chờ persistence riêng; phải kiểm tra phiên bản và thiết lập nếu cần cam kết đó.

### 11.3. Failover và dữ liệu trễ

Trong replication bất đồng bộ, primary có thể ACK `SET` trước khi replica bắt kịp. Nếu primary mất hẳn và replica cũ được nâng vai trò, một số thay đổi local gần nhất có thể không còn theo chính sách failover.

Đó là rủi ro liên quan **ACK, durability và authority**, không chỉ là biểu đồ lag tăng. Không dùng Redis như nguồn duy nhất cho reservation/ledger nhạy cảm khi chưa thiết kế chính sách dữ liệu phù hợp.

### 11.4. Dùng Redis làm cache

Nếu Redis chỉ lưu cache của MongoDB/DynamoDB:

- Lag replication giữa Redis primary/replica là một vấn đề.
- Lag invalidation giữa database nguồn và Redis là **vấn đề khác**.
- TTL và stale-write race ở ứng dụng có thể làm cache cũ **ngay cả khi Redis replica không trễ**.

Phải vẽ đường dữ liệu và theo dõi từng đoạn, không quy mọi cache miss/stale hit cho Redis replication.

## 12. Cassandra/ScyllaDB: không có một global lag của mọi key

Trong mô hình wide-column phân tán, cùng một partition có thể có nhiều replica được phối hợp theo consistency level. Các replica có thể chưa đồng nhất vì:

- Một lần ghi được ACK ở một tập replica nhưng không phải mọi replica.
- Replica tạm unreachable.
- Hinted handoff hoặc repair chưa chạy.
- Một mutation bị trì hoãn do quá tải, compaction hoặc I/O.
- Conflict resolution, timestamps và tombstones khiến kết quả phức tạp hơn “ai có version số lớn nhất”.

### 12.1. Tại sao không chỉ đo `primaryOffset - replicaOffset`?

Cassandra không có một primary log duy nhất cho **toàn bộ keyspace/cluster** theo cách một leader replication stream đơn giản có thể có. Thay vào đó cần hiểu **token ranges, replica placement, coordinator, CL, hints, repair và dữ liệu cụ thể**.

Một node có thể đồng bộ tốt ở partition X nhưng thiếu cập nhật ở partition Y. Chỉ số “cluster lag = 2 giây” thường không có cùng ngữ nghĩa đơn giản như MongoDB secondary optime.

### 12.2. Read/write CL và độ mới

Với RF=3:

```text
Replica A: update v8
Replica B: update v8
Replica C: update v7
```

Một write ở `QUORUM` có thể được xác nhận sau khi đủ replica đáp ứng. Một read ở `ONE` tình cờ đi tới C có thể trả cũ theo semantics của thao tác; read ở `QUORUM` có điều kiện giao nhau nhưng cần xét quy tắc hòa giải các version, concurrent writes, timestamps và thực thi cụ thể.

\[
R+W>RF
\]

cho ta thông tin về **quorum intersection** trong các giả định nhất định, không tự chứng minh mọi workload linearizable hay mọi read không bao giờ cũ.

### 12.3. Những công cụ nên đọc

Tùy phiên bản và môi trường, có thể dùng:

```text
nodetool status
nodetool netstats
nodetool tablestats
```

và JMX/metrics/monitoring của Cassandra hoặc ScyllaDB để quan sát trạng thái node, streaming, hints, repair, timeout, dropped messages, latencies và compaction. Các lệnh trên **không phải một API chuẩn trả trực tiếp freshness của từng key**.

Khi cần chứng minh một aggregate đã xuất hiện trên mọi đường đọc liên quan, có thể thêm **version do ứng dụng cấp** và thực hiện synthetic probes theo partition/tenant, tránh suy luận từ một số queue chung.

### 12.4. Hinted handoff và repair không thay thế backup

Hints có retention/giới hạn; repair phải chạy theo lịch và đúng topology. Nếu tất cả bản sao mất cùng một write đã ACK trước khi được lưu bền, repair giữa những bản sao còn lại không tự tái tạo write đó.

Theo dõi **lag/anti-entropy convergence** khác với bảo đảm **durability sau crash**.

## 13. DynamoDB: base table, GSI và replication giữa region

DynamoDB là dịch vụ managed; không phải mọi log offset nội bộ đều được công khai.

Phân biệt các đường:

| Đường truy cập | Điều cần biết |
|---|---|
| Base table `GetItem` | Có lựa chọn strongly consistent read ở những nơi API hỗ trợ |
| Base table `Query/Scan` | Cần nêu option consistency và phạm vi theo API |
| Local secondary index | Có những lựa chọn đọc khác GSI theo tài liệu |
| Global secondary index (GSI) | Được cập nhật theo cơ chế có thể có độ trễ; read semantics riêng |
| Global Tables | Replication liên vùng có semantics theo loại cấu hình/phiên bản |
| Streams/consumer | Progress của downstream consumer khác freshness base table |

### 13.1. GSI có thể chậm hơn base table

```text
PUT Order v8 -> ACK ở base table
                  |
                  v
             GSI propagation
                  |
                  v
QUERY GSI có thể vẫn thấy v7 hoặc chưa thấy item
```

Một request `ConsistentRead=true` trên API **được hỗ trợ** ở base table không làm GSI query tự trở thành strong read. Cần đọc tài liệu của đúng operation.

### 13.2. Thử độ mới bằng version marker

Trong một môi trường test:

1. Ghi item với `runId`, `version` và thời điểm thử.
2. Đợi ACK.
3. Đọc base table theo đường có consistency được chỉ định.
4. Query GSI có key phù hợp.
5. Ghi thời điểm lần đầu GSI thấy đúng version.
6. Lặp nhiều lần theo vùng, giờ cao điểm và tải khác nhau.

**Đây là phép đo end-to-end visibility của GSI**, không phải thông số “internal replica log lag” của DynamoDB.

### 13.3. Global Tables

Với triển khai multi-region, phải xác định **kiểu Global Tables/consistency mode** đang dùng, vì các chế độ và khả năng hỗ trợ thay đổi theo tính năng/phiên bản. Trong những chế độ replication bất đồng bộ, dữ liệu có thể xuất hiện chậm tại region đích; CloudWatch có thể cung cấp metric liên quan đến replication latency theo phạm vi được dịch vụ hỗ trợ.

Không tự coi **write ACK ở region A** là mọi region đã thấy và có thể trả cùng version ngay. Cũng không nên khẳng định mọi cấu hình Global Tables có chính xác một semantics giống nhau.

### 13.4. Số liệu capacity không phải lag

`ConsumedCapacity`, `Count` và `ScannedCount` phản ánh công việc của request đọc/ghi theo API, **không phải trực tiếp thời gian một bản sao bắt kịp**. Throttling/capacity có thể ảnh hưởng độ trễ pipeline, nhưng phải đo cả đường replication hoặc visibility.

## 14. Search/index projection: độ trễ nhiều chặng

Giả sử MongoDB là nguồn, outbox gửi event qua broker, consumer cập nhật Elasticsearch.

```text
MongoDB source commit
       |
       | L1: outbox relay delay
       v
Event broker accepted
       |
       | L2: consumer backlog / processing
       v
Search index write ACK
       |
       | L3: search refresh / visibility
       v
_search returns new document
```

Độ trễ để người dùng **thấy bản mới qua search** có thể xấp xỉ:

\[
L_{\text{visible}} \approx L_1 + L_2 + L_3 + L_{\text{network/queue}}
\]

Đây là phân rã khái niệm theo timestamp phù hợp; các bước có thể chồng lấn, nên không mặc định cộng những metric không cùng start/end point sẽ bằng chính xác end-to-end latency.

### Theo dõi ba loại checkpoint

1. **Outbox pending age:** event đã commit nhưng chưa phát.
2. **Broker/consumer offset lag:** event đã có trong broker nhưng chưa được consumer xử lý theo checkpoint.
3. **Search visible version:** document đã được tìm thấy với `sourceVersion` mong muốn.

Kafka offset lag, nếu có, thường là **số record/offset chưa xử lý theo partition**, không tự là số giây search lag. Consumer checkpoint có thể được commit trước hoặc sau thao tác index theo policy; cần biết checkpoint diễn đạt **đã đọc, đã xử lý hay đã durable**.

### Refresh không phải durability

Trong Elasticsearch/OpenSearch, một document được index có thể chưa xuất hiện ngay trong `_search` trước refresh, dù thao tác ghi đã ACK. Search visibility khác với translog durability và replica recovery.

Nếu source of truth còn, một index dẫn xuất hỏng có thể rebuild. Nếu mất cả outbox/event log và những thay đổi cần thiết, đường rebuild phải dựa vào snapshot/source thích hợp.

## 15. Tách nguồn dữ liệu và cache ở mức kiến trúc

Một API thường đi qua nhiều tầng:

```text
Mobile/Web
   |
   v
API Gateway / HTTP cache
   |
   v
Application
   |
   +---- Redis cache (có thể stale)
   |
   +---- Database replica (có thể lag)
   |
   +---- Search/read model (có thể refresh trễ)
   |
   +---- Authoritative database write path
```

Khi người dùng thấy cũ, đừng kết luận ngay **database replication lag**. Có thể:

- HTTP cache/CDN chưa hết TTL.
- Redis invalidation bị bỏ lỡ.
- Một reader cũ đưa bản v7 vào Redis sau khi writer invalidate bản v8.
- Database secondary chưa apply write.
- Search projector chậm hoặc đã apply nhưng chưa refresh.
- Client app đang giữ state local chưa cập nhật.

**Root cause analysis phải bám theo request trace** và version ở từng điểm, tránh sửa sai tầng.

## 16. Đặt watermark trên dữ liệu để biết bản nào mới hơn

Một thiết kế thực dụng cho aggregate:

```json
{
  "_id": "ORD-1001",
  "tenantId": "T01",
  "status": "SUBMITTED",
  "version": 8,
  "updatedAt": "2026-11-14T09:00:00Z"
}
```

Trong đó:

- `version` tăng **trong transaction/conditional update của chính aggregate**, không do client tự chọn ngẫu nhiên.
- `updatedAt` giúp logging/UI nhưng không được tự dùng làm thứ tự duy nhất nếu đồng hồ lệch.
- `tenantId` phải được ràng buộc theo principal đã xác thực ở cả write và read.
- Một thao tác delete có thể cần **tombstone/version xóa** để event cũ không hồi sinh document.

### Version phải thuộc cùng một thực thể

Version 8 của order A không thể so trực tiếp với version 5 của order B để kết luận replica bắt kịp toàn database. Nếu có nhiều partition cần một watermark chung, cần log position/commit timestamp/vector hoặc protocol tương ứng.

### Version của source khác version của HTTP cache

Cache có thể có internal revision riêng. Để so freshness, phải truyền **sourceVersion** giữ nguyên ngữ nghĩa từ nguồn, không dùng counter ngẫu nhiên phát sinh tại sink.

## 17. Read-your-writes bằng session token hoặc minimum version

Một lựa chọn thường dùng:

1. Ghi thành công vào nguồn, nhận `orderId` và `version=8`.
2. Trả token cho client biểu thị **mốc đã được xác nhận**.
3. Client gửi token trong request đọc tiếp theo.
4. Backend chỉ trả từ replica đã đạt mốc, chờ có giới hạn hoặc fallback đường đọc authoritative.

```text
WRITE order -> source ACK(version=8)
     |
     v
Client giữ minVersion=8
     |
     v
GET order?minVersion=8
     |
     +--> replica has v8  -> return v8
     |
     +--> replica has v7  -> wait / choose another replica
                             |
                             +--> timeout -> fallback or UNAVAILABLE
```

### Token là hint nhất quán, không phải quyền truy cập

Không dùng `minVersion` do client cung cấp để **bỏ qua authorization**. Client có thể sửa token; nếu token chứa thông tin nội bộ hoặc dùng để điều phối đặc biệt, cần ký/kiểm tra theo thiết kế.

Phải xác nhận read đúng `tenantId/orderId` trước khi trả dữ liệu; minVersion=8 không cấp quyền đọc một đơn khác.

### Không tự giải thích phiên bản “>=” bằng dữ liệu không cùng lịch sử

Sau delete/recreate với ID trùng hoặc đổi epoch, version số lớn có thể thuộc lịch sử khác. Khi cần, token nên gắn **entity generation/epoch/namespace** và đảm bảo version tăng đơn điệu không bị reset trái hợp đồng.

## 18. Ví dụ Java: đọc replica với mốc version tối thiểu

Ví dụ Java 17 mô tả một API cần giữ **read-your-writes cho một đơn**, không phụ thuộc SDK NoSQL cụ thể:

```java
import java.time.Duration;
import java.util.Optional;

record VersionedOrder(
    String tenantId,
    String orderId,
    long version,
    String status
) {}

interface OrderReader {
    Optional<VersionedOrder> readReplica(
        String tenantId, String orderId
    ) throws Exception;

    Optional<VersionedOrder> readAuthoritative(
        String tenantId, String orderId
    ) throws Exception;
}

final class ConsistentOrderRead {
    private final OrderReader reader;

    ConsistentOrderRead(OrderReader reader) {
        this.reader = reader;
    }

    VersionedOrder readAtLeast(
        String authenticatedTenantId,
        String orderId,
        long minVersion,
        Duration maxReplicaWait
    ) throws Exception {
        if (minVersion < 0 || maxReplicaWait.isNegative()) {
            throw new IllegalArgumentException("Invalid version/wait");
        }

        long deadline = System.nanoTime() + maxReplicaWait.toNanos();

        while (true) {
            Optional<VersionedOrder> replica = reader.readReplica(
                authenticatedTenantId, orderId
            );

            if (replica.isPresent()) {
                VersionedOrder order = replica.get();
                if (order.version() >= minVersion) {
                    return order;
                }
            }

            if (System.nanoTime() >= deadline) {
                break;
            }

            Thread.sleep(25); // minh họa bounded wait
        }

        // Đường fallback phải có read guarantee phù hợp.
        return reader.readAuthoritative(
            authenticatedTenantId, orderId
        ).filter(order -> order.version() >= minVersion)
         .orElseThrow(() ->
             new IllegalStateException("Required version unavailable")
         );
    }
}
```

### Các giả định và giới hạn của ví dụ

1. Chỉ minh họa **một aggregate có version tăng không giảm**. Nó chưa xử lý tombstone, recreate và transaction nhiều item.
2. `authenticatedTenantId` phải đến từ identity đáng tin; `OrderReader` phải lọc quyền ở nguồn.
3. `readAuthoritative` cần được triển khai bằng đường đọc thực sự phù hợp với hợp đồng mong muốn. Nếu fallback cũng đọc từ replica stale thì không giải quyết vấn đề.
4. `Thread.sleep` và poll liên tục phù hợp để giải thích thuật toán, **không lý tưởng trong servlet/event-loop ở tải cao**. Production có thể dùng async wait, routing theo applied watermark hoặc retry có backoff.
5. Nếu nguồn không đạt mốc trước deadline, **không trả bản cũ giả làm mới**. Tùy API có thể trả `503`, `409`, `PENDING` hoặc phản hồi khác có semantics rõ ràng.
6. Code chưa xử lý network timeout và cancellation chi tiết; SDK thực tế phải có **deadline tổng thể và retry policy**.

**Một ứng dụng có thể tránh vòng poll bằng API causal session/read barrier bản địa** nếu engine cung cấp. Không nên xây cơ chế version token thủ công khi hệ đã có tính năng đúng nhu cầu và đã được xác minh.

## 19. Read preference: cân bằng độ trễ và độ mới

Các lựa chọn thường gặp:

| Chiến lược đọc | Lợi ích | Rủi ro/chi phí |
|---|---|---|
| Chỉ đọc authoritative leader/đường mạnh | Giảm khả năng stale theo hợp đồng | Tải leader, latency/availability khi mất quorum |
| Đọc replica gần client | Latency thấp, phân tán tải | Có thể stale |
| Sticky replica/session | Giảm một số read regressions | Không tự bảo đảm một replica đã nhận write của session |
| Replica + min watermark | Đọc nhanh khi bắt kịp, chặn bản quá cũ | Có thể chờ hoặc fallback |
| Bounded staleness | Có ngân sách độ cũ, nếu engine hỗ trợ | Phải hiểu cách đo và xử lý khi vượt bound |
| Quorum/strong read | Đảm bảo mạnh hơn trong phạm vi giao thức | Coordination và latency |
| Read-your-writes token | Hỗ trợ trải nghiệm sau ghi | Token/epoch/routing phức tạp hơn |
| Cache eventual + authoritative confirm | Tối ưu UI preview | Không được dùng preview để quyết định cuối |

Không đánh đồng **nearest replica** với **freshest replica**. Một replica gần hơn về mạng có thể trễ xa hơn về dữ liệu do tải apply, I/O hoặc compaction.

## 20. Bounded staleness: “trễ tối đa X giây” có nghĩa gì?

Đặt mục tiêu:

> 99% kết quả đọc danh sách đơn được phép trễ không quá 5 giây so với thời điểm source commit.

Muốn đo đúng cần:

- Một mốc **commitAt** hoặc source sequence đáng tin.
- Đường đọc có `sourceVersion` tương ứng.
- Phương pháp ánh xạ version sang thời điểm commit.
- Quy định rõ các trường hợp **không có cập nhật mới**.
- Cửa sổ đo, tỉ lệ percentile và cách xử lý timeout.

Không thể chỉ đo:

```text
now() - replica.lastAppliedTimestamp
```

và gọi đó là staleness của mọi lần đọc, vì timestamp có thể là **thời điểm ghi cuối cùng**, không phải tiến độ thực sự. Khi không có write mới, phép đo này tăng dù replica hoàn toàn đồng bộ.

### Ví dụ probe đúng mốc

```text
Source commit marker M42 at 10:00:00.000
Replica first returns M42 at 10:00:00.250

Visibility latency for M42 on this path = 250 ms
```

Không suy ra mọi write của mọi partition cũng luôn thấy trong 250 ms. Cần nhiều probes, nhiều tenant/shard và có phân bố được ghi nhận.

### Percentile không phải worst case

`p95 = 500 ms` nghĩa là 95% mẫu trong tập đo không vượt 500 ms theo phương pháp thống kê đã chọn, **không có nghĩa không bao giờ trễ trên 500 ms**. Đối với quyền truy cập, tồn kho hoặc thanh toán, một số quyết định không thể dựa trên việc “95% đủ mới”; cần guard tại điểm commit/authorization.

## 21. Đo replication progress bằng synthetic probes

Khi engine không công bố mốc đủ chi tiết, ứng dụng có thể viết các marker không nhạy cảm vào một môi trường được phép:

```json
{
  "_id": "probe:tenant-demo:run-20261114-001",
  "sourceVersion": 42,
  "emittedAt": "2026-11-14T09:00:00Z",
  "payload": "replication-probe"
}
```

Workflow:

```text
Probe writer:
  write marker M42 to source
  await ACK with chosen write concern
  record monotonic/controlled end time

Probe reader R1:
  repeatedly read marker from intended replica/index path
  record first time sourceVersion=42 visible

Probe reader R2:
  repeat on a different replica/region

Aggregator:
  correlate by probe ID and path
  calculate visibility delay distribution
```

### Lưu ý quan trọng

- **Probe là dữ liệu thử**; không phát tán PII hoặc bí mật.
- Một probe nhỏ không đại diện cho document lớn, write hot partition, batch update hay query phức tạp.
- Nếu write được routing tới partition X, probe chỉ đo **đường đó**, không phải toàn cluster.
- Không chạy probes với QPS cao gây tăng lag hoặc chi phí đáng kể.
- Nếu đo latency xuyên máy, cần đồng bộ đồng hồ hoặc đo bằng controller độc lập với giao thức rõ ràng.
- Có thể tồn tại probe đã ACK nhưng đọc bị time out; log cả **censored/timeout samples**, không chỉ những probe thành công, để tránh tô đẹp kết quả.

### Probe toàn phần khác probe nguồn

Muốn đo lag của **database replica**, đọc marker trực tiếp từ replica. Muốn đo **search projection lag**, đặt marker qua pipeline thực `source → outbox/CDC → broker → projector → search`; hai kết quả không được dùng thay thế cho nhau.

## 22. Phân biệt throughput, backlog và lag

Giả sử trong một phút:

```text
Source writes:  3,000 events / minute
Replica apply: 2,000 events / minute
Backlog tăng:  1,000 events / minute
```

Nếu tốc độ giữ nguyên, backlog sẽ tăng, ngay cả khi network vẫn truyền được. Một công thức gần đúng:

\[
\Delta Q \approx (\lambda_{\text{in}}-\mu_{\text{out}})\Delta t
\]

Trong đó:

- \(\lambda_{\text{in}}\): tốc độ tạo công việc.
- \(\mu_{\text{out}}\): tốc độ replica áp dụng công việc.
- \(Q\): backlog.

Đây là mô hình hàng đợi đơn giản. Trong thực tế, event có kích thước khác nhau, batching, nhiều worker và các giới hạn I/O khiến tốc độ dao động.

### Kịch bản catch-up

```text
Lúc T0: backlog 10,000 events
Source rate giảm xuống 500 events/s
Apply rate hiện tại đạt 700 events/s

Net drain rate khoảng 200 events/s
Ước lượng catch-up ~50 giây nếu các điều kiện giữ nguyên.
```

**Đó chỉ là phép tính kịch bản**, không phải lời hứa recovery thực. Nếu apply rate giảm trong quá trình catch-up, thời gian dài hơn. Nếu đã mất những log entries do retention, replica có thể cần full resync thay vì catch-up bình thường.

### Không dùng duy nhất CPU để kết luận

Replica lag có thể tăng do:

- Network latency hoặc bandwidth.
- Apply thread/workers bị nghẽn.
- Disk I/O và fsync/flush.
- Compaction/GC.
- Dữ liệu có hot partition hoặc tài liệu quá lớn.
- Batch bulk import, index build, snapshot.
- Lock/transaction contention.
- Retry/throttle.
- Replica reinitialization, topology change.
- Dịch vụ đích của read model chậm.

CPU thấp vẫn có thể lag vì đang chờ disk/network; CPU cao không luôn là nguyên nhân chính.

## 23. Thiết kế dashboard theo tiến độ và độ mới

Một dashboard tốt có ít nhất **ba lớp**:

### Lớp A — Replication infrastructure

| Metric | Nên hiển thị |
|---|---|
| Replica role/state | Primary/secondary/initial sync/recovering |
| Received/appended/applied/durable position | Chênh lệch theo từng replica và epoch |
| Reported lag time/bytes | Giữ đơn vị và cách đo của engine |
| Replication throughput | Bytes/s, entries/s theo khả năng hệ |
| Repl network errors | Timeout, disconnect, retry |
| Catch-up progress | Còn bao nhiêu log/position cần áp |
| Retained log window | Còn đủ lịch sử để replay không |

### Lớp B — Khả năng phục vụ truy vấn

| Metric | Cần phân biệt |
|---|---|
| Strong read success/error | Có đáp ứng hợp đồng không |
| Stale read rate | Tần suất thực tế thấy version thấp hơn yêu cầu |
| Read-your-writes failures | Client vừa ghi nhưng đọc không thấy |
| Read fallback rate | Bao nhiêu request phải chuyển sang đường mạnh |
| Read barrier wait time | Chờ replica đạt watermark bao lâu |
| p50/p95/p99 read latency | Theo API, region và route |

### Lớp C — Read model/event pipeline

| Metric | Ý nghĩa |
|---|---|
| Outbox oldest pending age | Ý định cập nhật chưa được relay |
| Broker consumer lag | Backlog sau broker |
| Projector processing time | Thời gian apply event |
| Search-visible sourceVersion | Mốc mới nhất nhìn thấy từ search |
| Cache invalidation lag | Độ trễ từ source commit đến invalidate |
| Reconciliation mismatch | Chênh lệch đã được xác minh |
| Dead-letter/replay backlog | Event cần can thiệp |

### Đừng đánh tráo nhãn metric

Ví dụ `redis_replica_ack_lag_seconds` và `order_search_visibility_lag_seconds` **không đo cùng loại thời gian**; gộp bằng `max()` rồi gọi chung “replication lag” sẽ che giấu nguyên nhân. Nên có tên, đơn vị, phạm vi và dashboard riêng.

### Tránh cardinality quá cao

Không gắn `orderId` hoặc email vào label Prometheus/metrics cho mọi event. Dùng các chiều ổn định: `cluster`, `replica`, `region`, `readPath`, `operationName`, nhóm tenant, và để ID cụ thể trong log/tracing có quyền truy cập phù hợp.

## 24. SLO và cảnh báo: đặt theo tác động tới người dùng

Ví dụ những mục tiêu **minh họa**:

```text
Authoritative order confirmation:
  Không xác nhận hai reservation cho cùng seat.

Order history read-after-write:
  99.9% request sau ACK thấy ít nhất version vừa ghi.

Catalog/search projection:
  99% event trở nên visible trong 5 giây.

Replica health:
  Applied lag p95 < 2 giây trong điều kiện bình thường.
  Không replica nào thiếu log đến mức cần resync ngoài kế hoạch.
```

Các con số chỉ để minh họa phương pháp; không phải SLA mặc định của NoSQL.

### Cảnh báo trên trend, không chỉ snapshot

Một replica có lag 3 giây nhưng đang **giảm đều** có ý nghĩa khác replica đang từ 3 → 10 → 30 giây. Cảnh báo nên xét:

- Lag vượt ngưỡng trong một khoảng liên tục.
- Lag tăng theo slope đáng kể.
- Time-to-overrun của log retention/oplog window.
- Replica state chuyển bất thường.
- Lỗi đọc, fallback và user-visible staleness.
- Ảnh hưởng của quá trình repair/initial sync.

### Khi không có ghi mới

Không được alert “lag tăng” chỉ vì `now - lastWriteTime` tăng trong một cluster idle. Cần dùng metric **source versus replica progress** hoặc heartbeat có nghĩa rõ, không lấy độ tuổi của last event làm chênh lệch replication.

## 25. Runbook điều tra replica lag cao

### Bước 1 — Xác định phạm vi

Hỏi:

- Lag nằm trên một replica, một shard, một region hay toàn cluster?
- Là lag **received**, **durable**, **applied**, hay **visible**?
- Có tác động tới API nào không?
- Có failover/reshard/bulk import gần đây không?

### Bước 2 — Đối chiếu nguồn tham chiếu

Xác định leader/current authority, commit position, log epoch và replica state. Không so offset thuộc hai log generation khác nhau.

### Bước 3 — Kiểm tra chiều nhận

Nếu `received` trễ xa `source appended`:

- Network/replication connection.
- Bandwidth/latency và packet loss.
- Source replication sender/backpressure.
- Firewall/TLS hoặc topology.
- Retry/reconnect và điều kiện authentication.

### Bước 4 — Kiểm tra chiều apply

Nếu replica đã nhận nhiều nhưng `applied` trễ:

- Disk/fsync/compaction.
- CPU/GC/worker pool.
- Index maintenance.
- Large transactions hoặc long-running operations.
- Throttling trên sink.
- Apply queue và checkpoint logic.

### Bước 5 — Kiểm tra visibility

Nếu applied đã mới nhưng client vẫn thấy cũ:

- Read đang đi đúng replica không?
- Có HTTP/Redis cache không?
- Search có refresh chưa?
- Client có giữ state local?
- Read API có dùng snapshot/transaction cũ không?
- Có session token/monotonic read guarantee không?

### Bước 6 — Đánh giá khả năng bắt kịp

So source write rate, replica apply rate và log retention. Nếu backlog tăng và sắp vượt retention, cần escalation theo quy trình để tránh mất khả năng incremental catch-up.

### Bước 7 — Giảm tác động an toàn

Các lựa chọn tùy hệ:

- Tạm route các API cần freshness sang authoritative path.
- Không phục vụ strong read từ replica chưa đạt watermark.
- Giảm tải đọc nặng trên replica.
- Điều chỉnh backlog/concurrency có kiểm soát.
- Giảm tốc job bulk ingest nếu được phép.
- Mở rộng tài nguyên phù hợp hoặc sửa network bottleneck.
- Rebuild/resync replica theo runbook nếu không còn log cần thiết.

**Không tự xóa WAL/oplog, ép secondary thành primary, hoặc tắt bảo vệ write concern chỉ để đồ thị lag đẹp hơn.** Hành động đó có thể gây mất dữ liệu hoặc phá tính đúng.

### Bước 8 — Xác minh phục hồi

Đo:

- Replica đã bắt kịp mốc authoritative.
- Read-after-write hoạt động đúng theo API.
- Không có rollback/duplicate side effect.
- Search/cache và projection hội tụ.
- Độ trễ p95/p99 và error rate về mục tiêu.

Chỉ nhìn trạng thái node “healthy” là chưa đủ.

## 26. Failover: replica bắt kịp nào có thể trở thành leader?

Trong hệ leader replication, lựa chọn leader mới phải theo **giao thức election và committed history**, không đơn giản chọn node có timestamp gần `now()` nhất.

```text
Primary P: committed through 105, appended 107
R1:        applied through 105
R2:        applied through 102
```

Nếu P mất, một protocol có thể chỉ chọn ứng viên đáp ứng điều kiện đủ mới, term/epoch và quorum thích hợp. Những write **appended nhưng chưa committed** có thể không thuộc lịch sử cuối cùng.

### Đừng đánh đồng lag thấp và quyền leader

Một replica có apply timestamp mới hơn nhưng không đủ quorum hoặc log khác term vẫn có thể **không hợp lệ** để làm leader. Conversely, replica được bầu leader theo giao thức có thể cần catch-up/apply trước khi đáp ứng các read.

### Tiêu chí cần theo dõi

- Election term/epoch, current leader.
- Commit index hoặc mốc tương đương.
- Mức lag của ứng viên.
- Write ACK mode và những request timeout.
- Rollback events.
- Thời gian ngừng phục vụ write/read mạnh.

**Một write đã ACK ở chế độ yếu có thể mang rủi ro khác một write đã commit majority.** Replication lag là một tín hiệu rủi ro, nhưng đánh giá RPO cần cả durability và điều kiện commit.

## 27. Xóa dữ liệu, tombstone và event đến trễ

Lag đặc biệt nguy hiểm khi dữ liệu bị xóa. Giả sử:

```text
Product P10 v11: ACTIVE
Product P10 v12: DELETED

Search đã xử lý DELETE v12.
Event UPDATE v11 đến muộn.
```

Nếu projector chỉ ghi vô điều kiện, nó có thể **hồi sinh** P10. Một chiến lược là giữ tombstone logic:

```json
{
  "_id": "P10",
  "sourceVersion": 12,
  "deleted": true
}
```

Event v11 bị từ chối vì cũ hơn v12. Khi dọn tombstone, phải biết thời hạn replay/event retention hoặc có cách khác bảo vệ trước dữ liệu cũ quay lại.

### Delta event còn khó hơn full-state

Nếu event là `INCREMENT 1` hoặc `DECREMENT 2`, chỉ áp event có version lớn hơn không đủ: thiếu một delta sẽ làm tổng sai. Cần **sequence gap detection**, dedup, replay hoặc rebuild từ ledger/source.

Do đó monitor không chỉ đo “lag mấy giây”, mà còn **có mất event, sai thứ tự, gap, duplicate và mismatch nào không**.

## 28. Thử nghiệm có kiểm soát: tạo replica lag và kiểm tra freshness

Không gây network partition, disk pressure hay crash trên production chỉ để học. Sử dụng **lab có dữ liệu giả**, quyền phù hợp và rollback plan.

### 28.1. Chuẩn bị

```text
Cluster: 1 primary + 2 replicas (nếu engine hỗ trợ)
Dataset: orders_demo
Initial state: version=1
Clients: writer, reader-primary, reader-R1, reader-R2
Telemetry: operationId, sessionId, route, version, invoke/complete
```

### 28.2. Baseline

1. Đợi các replica bắt kịp theo metric của engine.
2. Ghi version mới qua source.
3. Chờ ACK với write concern đã xác định.
4. Đọc từ từng replica và ghi thời điểm lần đầu thấy version mới.
5. Lặp nhiều lần để có phân bố, không chỉ một số duy nhất.

### 28.3. Chèn độ trễ sao chép ở lab

Tạo latency/packet loss có kiểm soát **giữa source và một replica**, hoặc tạo apply backlog theo cách môi trường test hỗ trợ.

```text
Source P <---- normal ----> R1
Source P ---- delayed ----> R2

Reader A -> R1
Reader B -> R2
```

So:

- Source position và received/applied position của R2.
- Giá trị read ở R2 trước/sau khi bắt kịp.
- Mức độ phiên đọc bị lùi khi chuyển R1 → R2.
- Fallback/timeout khi yêu cầu minVersion cao hơn R2.
- Thời gian catch-up sau khi bỏ fault.

### 28.4. Kiểm thử failover riêng

Nếu muốn thử mất primary, phải đo **write nào đã ACK**, mode ACK nào, và replica mới có giữ chúng không. Không xem thành công của một phép restart process là bằng chứng an toàn khi mất disk hoặc region.

### 28.5. Kết quả mẫu cần ghi

| Probe | Read path | Source version | First visible version | Visibility delay | Kết luận |
|---|---|---:|---:|---:|---|
| M1 | R1 | 8 | 8 | 20 ms | Ví dụ: nhanh |
| M1 | R2 | 8 | 8 | 240 ms | Ví dụ: replica chậm |
| M1 | Search | 8 | 8 | 950 ms | Ví dụ: pipeline/refresh |

**Số trên chỉ là dữ liệu minh họa**. Chỉ báo cáo như kết quả hệ thật sau khi có log và cách đo xác minh được.

## 29. Đọc kết quả mà không suy luận quá mức

| Quan sát | Kết luận có căn cứ | Không thể kết luận ngay |
|---|---|---|
| Replica offset sau source 500 bytes | Replica chưa bắt kịp trong không gian offset đó | Mọi read trễ 500 ms |
| Last applied timestamp cũ 5 phút, source idle 5 phút | Cần so current source progress | Replica nhất định trễ 5 phút |
| GSI trả v7, base table trả v8 | GSI chưa cập nhật/đường read khác mốc | Source đã mất write |
| MongoDB majority write ACK, secondary trả v7 | Một secondary có thể chưa apply v8 theo mode read | Majority write là giả |
| Redis `WAIT` trả 1 | Một replica đã ACK replication theo hợp đồng lệnh | Write đã fsync ở mọi replica |
| Cassandra CL ONE trả cũ | Đường đọc có thể thấy replica chưa cập nhật | Tất cả quorum reads sẽ cũ |
| Search đã index nhưng chưa thấy qua query | Có thể là refresh/visibility lag | Translog đã hỏng |
| Probe lag p95=500ms | 95% mẫu theo phương pháp đo trong tập thử không vượt 500ms | Không có read nào quá 500ms |
| Worker lag giảm dần | Có thể đang catch-up | Không còn lỗi/data gap nào |
| Client timeout sau write | Kết quả commit có thể không rõ | Write chắc chắn bị rollback |

**Đừng sửa lỗi dựa trên một metric có tên dễ gây hiểu nhầm mà chưa đọc semantics của nó.**

## 30. Một cách viết hợp đồng API có thể kiểm tra

Thay vì:

> Hệ thống luôn đồng bộ dữ liệu theo thời gian thực.

Hãy viết:

```yaml
api: GET /orders/{orderId}
readPath: authoritative-or-version-checked-replica
scope: one order in authenticated tenant
minimumVersion:
  source: version returned by last successful write
  behavior: wait up to configured deadline, then fallback/error
onUnavailableFreshRead:
  response: UNAVAILABLE_OR_PENDING
  neverReturnStaleAsFresh: true
staleAllowed: false for confirmed write follow-up
metrics:
  - read_barrier_wait_duration
  - replica_fallback_count
  - required_version_unavailable_count
  - end_to_end_read_latency
```

Đây là **hợp đồng mẫu**, không phải file cấu hình của một thư viện. Nó buộc nhóm phát triển trả lời:

- Đường đọc nào có thẩm quyền?
- Freshness được đo bằng version nào?
- Client cần truyền token gì?
- Nếu replica không theo kịp thì trả gì?
- Khi nào fallback được và khi nào phải báo lỗi?

Một endpoint catalog có thể cho phép stale tối đa theo SLO và không cần token; endpoint quyền/đặt chỗ có thể yêu cầu điều kiện mạnh hơn.

## 31. Khi nào nên chọn read mạnh thay vì cố rút ngắn lag?

Không phải mọi invariant đều giải quyết bằng cách “replication nhanh hơn”:

### Đặt chỗ và tồn kho

Read replica chỉ giúp **preview**. Tại thời điểm xác nhận, cần conditional update/transaction trên nguồn có thẩm quyền. Dù lag trung bình 1 ms, vẫn có cửa sổ cạnh tranh.

### Thanh toán

Không dựa trên một projection eventually consistent để quyết định giao dịch đã được charge. Cần ledger/transaction ID/idempotency và xác minh trạng thái từ nguồn phù hợp.

### Thu hồi quyền

Không đợi tất cả cache và search hội tụ mới kiểm tra quyền; có thể dùng authoritative ACL check hoặc fail-closed với epoch/version, tùy SLA an toàn.

### Dashboard thống kê

Có thể cho lag vài giây/phút theo yêu cầu, nhưng cần watermark, dedup, reconciliation và hiển thị “cập nhật đến lúc...” nếu người dùng dựa vào số.

### Hiển thị đơn vừa tạo

Có thể dùng session consistency hoặc minVersion token để giữ trải nghiệm read-your-writes mà không cần buộc mọi query analytics global linearizable.

**Thiết kế tốt tách điểm quyết định cần đúng ngay khỏi read model có thể hội tụ sau.**

## 32. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách thay thế |
|---|---|---|
| “Lag=0 tức tất cả read luôn mới” | Một metric có thể chỉ là received, còn cache/search trễ | Xem applied/visible và đường read |
| “Replica ACK nghĩa đã fsync” | Có thể chỉ nhận/apply trong RAM | Đọc chính sách persistence của engine |
| “Majority ACK nghĩa mọi replica bắt kịp” | Minority replica vẫn có thể cũ | Tách write ACK và read concern |
| “Lag 100 offset = 100 ms” | Sai đơn vị | Dùng metadata thời gian/probe |
| “Last write 10 phút trước nghĩa replica trễ 10 phút” | Source có thể đã idle | So source/replica progress |
| “Một version lớn hơn luôn mới hơn trên mọi key” | Version per-aggregate không so global | Dùng scope/version đúng |
| “Read nearest chắc là freshest” | Replica gần có thể nghẽn apply | Route theo watermark khi cần |
| “Sticky session đủ read-your-writes” | Replica cố định có thể chưa nhận write | Causal session/read barrier |
| “Tăng TTL để cache nhất quán” | TTL dài tăng stale | Invalidate/versioned cache |
| “Quorum luôn linearizable” | Còn timestamp/conflict/failover/read protocol | Xem hợp đồng operation |
| “Search chưa thấy = source không commit” | Projector/refresh lag | Đo từng chặng |
| “Redis WAIT là consensus quorum” | Chỉ chờ replication ACK theo lệnh | Hiểu failover/durability |
| “CL QUORUM Cassandra là global serializable” | Không tự bảo vệ transaction đa partition | LWT/transaction phù hợp |
| “Sau failover node xanh là dữ liệu đã đúng” | Có thể rollback/read model mismatch | So history và đối soát |
| “Không có writer thì lag cứ tăng mãi” | Last event age khác progress gap | Sử dụng metric tương thích idle |
| “Khắc phục lag bằng cách tăng retry vô hạn” | Thêm tải, có thể sinh side effect trùng | Backoff/idempotency/fallback |
| “Sửa lag bằng cách bỏ write concern” | Có thể mất write sau failover | Bảo vệ invariant, tăng năng lực hệ |
| “Chỉ test một key chứng minh mọi partition” | Không đại diện skew/hotspot | Probe theo shard/tenant |
| “Probe không thấy lỗi chứng minh toàn hệ strong” | Chưa bao phủ mọi lịch sử | Kết hợp docs, faults, histories |
| “Read model cũ vẫn được dùng để kiểm tra quyền” | Có thể lộ thông tin | Authoritative check/fail-closed |

## 33. Bài tập thực hành

### Bài 1 — Phân biệt received/applied

Một replica báo:

```text
Leader committed = 1000
Replica received = 995
Replica durable  = 992
Replica applied  = 980
```

Hãy tính khoảng cách theo từng mốc, chỉ ra số nào gần nhất với backlog phục vụ read và giải thích vì sao không thể trực tiếp chuyển sang giây.

### Bài 2 — Replica đã bắt kịp nhưng “lag time” lớn

Primary và secondary đều có last applied entry timestamp 10:00. Bây giờ là 10:15 và không có write mới. Một dashboard hiển thị `now-lastAppliedTimestamp=15 phút` rồi phát cảnh báo “replica trễ 15 phút”. Cách đo này sai ở đâu? Nên so sánh với mốc nào?

### Bài 3 — Majority write, minority replica

P và R1 đã xác nhận version 8; R2 vẫn version 7. User đọc R2 và thấy 7. Điều này có bác bỏ write majority không? Hãy nêu read policy có thể làm user thấy 8 hoặc báo chờ.

### Bài 4 — Read-your-writes

Một client submit order và nhận ACK v8, sau đó được router đưa tới replica v7. Hãy thiết kế session token, minVersion check và fallback phù hợp. Những thông tin gì không được dùng như bằng chứng quyền truy cập?

### Bài 5 — Monotonic reads

Client đọc R1 được version 9 rồi R2 được version 6. Nếu không có thao tác xóa/recreate hoặc write mới làm lùi version, đây là loại vi phạm session nào? Có thể dùng sticky routing, watermark hoặc read barrier ra sao?

### Bài 6 — Redis offset

`master_repl_offset=1,200,000`, replica offset 1,175,000. Lag theo offset bao nhiêu? Vì sao không thể nói “trễ 25.000 ms”? `WAIT 1 1000` bảo đảm điều gì và không bảo đảm điều gì?

### Bài 7 — MongoDB oplog retention

Replica còn ở oplog position 4.200, nhưng source chỉ giữ các entry từ 5.000 trở đi. Điều gì cản trở incremental catch-up? Cần thu thập những thông tin vận hành nào trước khi dùng initial sync/resync?

### Bài 8 — Cassandra và quorum

RF=3, hai replica có update mới, một replica cũ. So sánh khả năng quan sát khi read ở CL ONE và CL QUORUM. Giải thích vì sao chỉ dùng \(R+W>RF\) không tự chứng minh linearizability với concurrent writes.

### Bài 9 — DynamoDB GSI

Base table item đã là v8, query GSI thấy v7. Hãy lập kế hoạch đo end-to-end GSI visibility delay. Vì sao `ConsumedCapacity` không phải số đo replication lag?

### Bài 10 — Multi-region

Ứng dụng ghi order ở region A và đọc ở B. Có lúc đọc được v7 sau ACK v8 ở A. Những thông tin nào cần biết về Global Tables/replication mode, read API, region và kiểu write ACK trước khi kết luận lỗi consistency?

### Bài 11 — Pipeline search

Thời điểm minh họa:

```text
Source commit      10:00:00.000
Broker accepted    10:00:00.200
Consumer indexed   10:00:00.350
Search visible     10:00:01.100
```

Tính độ trễ từng chặng và tổng, nêu chặng nào cần điều tra đầu tiên nếu SLO yêu cầu visible trong 500 ms. Vì sao kết quả này không phải replication lag của database nguồn?

### Bài 12 — Tạo synthetic probe

Thiết kế marker theo `runId/sourceVersion`, write source với ACK xác định, đọc từ hai replica và một search index. Cần lưu những trường nào để biết path nào trễ? Làm sao tránh nhầm clock skew và tránh quá tải bằng probes?

### Bài 13 — Theo dõi backlog

Source tạo 3.000 event/phút, replica xử lý 2.000 event/phút. Backlog tăng bao nhiêu mỗi phút? Nếu sau đó tốc độ source giảm còn 500 event/s, apply đạt 700 event/s và backlog 10.000 event, ước lượng thời gian drain dưới giả định tốc độ không đổi.

### Bài 14 — Failover và rollback

Primary ACK write ở chế độ yếu rồi mất trước khi secondary nhận; replica được bầu mới có dữ liệu cũ. Hãy phân biệt stale read tạm thời với write bị loại khỏi lịch sử sau failover. Dùng tín hiệu nào để phân loại?

### Bài 15 — Cache stale-write race

Reader A đọc source v7; writer commit v8 rồi xóa cache; reader B ghi cache v8; reader A ghi v7 sau cùng. Vì sao invalidation không đủ? Hãy mô tả cách dùng sourceVersion và CAS để từ chối stale overwrite.

### Bài 16 — Quyền và dữ liệu cũ

ACL thu hồi quyền đã commit tại nguồn lúc 10:00, nhưng search chưa cập nhật đến 10:00:20. Có thể để user xem nội dung dựa trên search ACL trong 20 giây đó không? Đề xuất một đường kiểm tra quyền có thẩm quyền.

### Bài 17 — Thiết kế alert

Replica R1 có lag 3 giây và đang giảm, R2 có lag 3 → 10 → 30 giây trong 5 phút. Oplog retention còn khoảng 45 phút nếu tốc độ hiện tại giữ nguyên. Hãy đề xuất alert và thứ tự xử lý, không dùng duy nhất một ngưỡng lag tĩnh.

### Bài 18 — Đối soát sau incident

Sau một network partition, leader mới có version 20, replica cũ có version 18; search chứa version 19; cache chứa version 17. Hãy xác định nguồn có thẩm quyền theo protocol, thứ tự bắt kịp, tiêu chí invalidate/rebuild và những request timeout cần kiểm tra idempotency.

## 34. Quy trình nhanh khi thiết kế replica reads

**Bước 1 — Chọn access pattern.** Đọc gần người dùng, đọc sau ghi của chính session, hay đọc để ra quyết định giữ chỗ?

**Bước 2 — Định nghĩa freshness cần thiết.** Có thể stale không; nếu có trễ tối đa bao lâu và tính bằng version/time nào?

**Bước 3 — Chọn đơn vị bảo đảm.** Một key/aggregate, partition, transaction đa key, hay read model theo event?

**Bước 4 — Chọn write ACK.** Ghi được công nhận commit ở đâu, bao nhiêu replica và có yêu cầu persistence không?

**Bước 5 — Chọn read path.** Primary, secondary, nearest, quorum, session-aware hoặc fallback authoritative.

**Bước 6 — Định nghĩa mốc tiến độ.** Received, durable, applied, visible; log epoch, sourceVersion, checkpoint và điều kiện so sánh.

**Bước 7 — Gắn requestId/version.** Giúp kiểm tra read-your-writes, idempotency, ordering và audit.

**Bước 8 — Thiết kế lag monitoring.** Progress metrics, p95/p99 freshness, outbox/search/cache pipeline và cảnh báo khi gần hết retained log.

**Bước 9 — Lập kế hoạch khi replica chậm.** Wait có giới hạn, chuyển đường đọc, báo stale minh bạch hoặc fail-closed.

**Bước 10 — Thử nghiệm failover/catch-up.** Test trên môi trường cô lập, đo recovery và đối soát sau khi kết nối phục hồi.

## 35. Kết luận

**Replication lag** không phải một con số duy nhất áp dụng cho mọi NoSQL. Nó có thể là khoảng cách **log/offset**, **applied position**, **durable position**, **thời gian giữa các checkpoint**, hoặc **độ trễ quan sát của một bản dữ liệu dẫn xuất**. Chỉ số nào đúng phụ thuộc mô hình sao chép và đường API đang dùng.

Những điểm cần ghi nhớ:

1. **Nhận khác áp dụng, áp dụng khác bền, bền khác nhìn thấy qua search.** Chọn đúng mốc khi đo.
2. **Write đã ACK theo quorum không đồng nghĩa mọi replica đã bắt kịp.** Read từ bản sao yếu vẫn có thể thấy dữ liệu cũ.
3. **Lag thấp không tự đảm bảo invariant.** Quyết định đặt chỗ, thanh toán và thu hồi quyền cần nguồn có thẩm quyền hoặc cơ chế nhất quán phù hợp.
4. **Read-your-writes và monotonic reads cần chính sách riêng.** Session token, minVersion, read barrier hoặc routing có thể bảo vệ trải nghiệm.
5. **Mỗi engine có telemetry khác nhau.** MongoDB optime/oplog, Redis replication offsets, Cassandra repair/CL, DynamoDB base table/GSI và search pipeline không thể ép vào cùng một công thức.
6. **Đo tiến độ kèm độ mới người dùng quan sát.** Metrics của node, synthetic probes, versioned reads, trace và SLO nên bổ sung cho nhau.
7. **Lag tăng lâu có thể biến thành vấn đề recovery.** Khi log cần replay đã bị xóa hoặc failover làm đổi authoritative history, cần resync/rebuild, không chỉ chờ.
8. **Sau sự cố phải đối soát.** Replica xanh trở lại chưa chứng minh cache, search, outbox và các tác động nghiệp vụ đã đúng.

Thay vì chỉ hỏi **“replica trễ bao nhiêu giây?”**, hãy hỏi:

> “Replica đã **nhận, ghi bền, áp dụng và có thể phục vụ** đến mốc nào? Read này đòi **phiên bản tối thiểu nào**? Nếu chưa bắt kịp, hệ sẽ **chờ, chuyển đường đọc hay từ chối**, và làm sao chứng minh sau failover mọi lời xác nhận hợp lệ vẫn được tôn trọng?”

Trả lời được các câu hỏi đó giúp quản lý sao chép và quorum theo **hành vi quan sát thực**, thay vì chỉ nhìn một đồ thị lag hoặc tin rằng mọi bản sao đều giống nhau ngay sau ACK.
