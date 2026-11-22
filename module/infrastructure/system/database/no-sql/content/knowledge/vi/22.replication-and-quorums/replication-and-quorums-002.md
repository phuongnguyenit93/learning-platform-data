# Leader–follower, nhiều leader và mô hình không có leader cố định

Giả sử một ứng dụng bán vé có ba bản sao của dữ liệu ghế **A12** trên ba máy chủ. Client A gửi yêu cầu giữ ghế, nhận thông báo **thành công**, nhưng Client B đọc từ một bản sao khác và vẫn thấy ghế **AVAILABLE**. Nếu hai người cùng đặt, ai thật sự sở hữu ghế? Nếu máy chủ vừa nhận ghi bị lỗi, dữ liệu đã xác nhận có còn không? Và khi hai khu vực cùng cập nhật ghế, hệ thống phải chọn kết quả nào?

Để trả lời, cần hiểu **kiến trúc sao chép (replication topology)**, không chỉ đếm số bản sao. Trong hệ thống NoSQL phân tán, có ba họ thiết kế quan trọng:

1. **Leader–follower:** một leader có quyền nhận hoặc điều phối ghi cho một phạm vi dữ liệu; follower nhận những thay đổi được truyền từ leader.
2. **Nhiều leader (multi-leader):** hai hoặc nhiều leader có thể chấp nhận ghi cho cùng một logical object trước khi đồng bộ với nhau, tạo khả năng xung đột.
3. **Không có leader cố định (leaderless):** một node coordinator bất kỳ có thể gửi thao tác đến các replica; các replica phối hợp theo chính sách đọc/ghi, thường được giải thích bằng các thông số **N, R, W** trong họ thiết kế kiểu Dynamo.

Tên mô hình mô tả **cách tổ chức quyền ghi và lan truyền dữ liệu**, nhưng không tự xác định toàn bộ **tính nhất quán, atomicity, isolation, durability, độ trễ hoặc tính sẵn sàng**. Một hệ có thể có leader theo từng shard, dùng quorum để xác nhận ghi, dùng consensus cho một số transaction và cho phép đọc eventual từ replica. Vì thế, khi áp dụng vào NoSQL, phải xác định bảo đảm **theo từng API, từng key/partition và từng mode đọc–ghi**.

Mục tiêu của bài học là phân tích luồng ghi/đọc, thời điểm ACK, replication lag, failover, split-brain, multi-leader conflicts, leaderless quorums, hinted handoff, read repair, tombstones, đồng bộ đa vùng, lựa chọn kiến trúc và kiểm thử các lỗi thực tế.

## 1. Sao chép dữ liệu giải quyết vấn đề gì?

**Replication** là duy trì nhiều bản sao của dữ liệu trên các node hoặc miền lỗi khác nhau.

Những mục tiêu phổ biến:

- **Chịu lỗi:** một node hoặc ổ đĩa lỗi không làm mất toàn bộ bản dữ liệu.
- **Tăng khả năng phục vụ đọc:** nếu mode đọc cho phép, follower/replica có thể chia sẻ tải.
- **Giảm độ trễ địa lý:** đặt bản dữ liệu gần người dùng ở những vùng khác nhau.
- **Hỗ trợ bảo trì:** thay hoặc nâng cấp node mà không nhất thiết dừng dịch vụ.
- **Khôi phục:** node mới có thể lấy dữ liệu từ các bản sao còn lành.

Sao chép cũng tạo thêm các câu hỏi:

~~~text
Ai nhận write?
Ai được quyền ACK?
ACK sau khi ghi vào một node hay nhiều node?
Read ở replica khác có cần thấy write vừa ACK?
Nếu hai node mất liên lạc, bên nào có quyền ghi?
Nếu hai replica có phiên bản khác nhau, bên nào đúng?
Nếu đã DELETE ở một nơi, bản cũ ở nơi khác có hồi sinh không?
~~~

**Replication không thay thế backup.** Khi thao tác xóa sai được sao chép khắp cluster, các replica có thể cùng mất dữ liệu. Backup có retention tách biệt và được kiểm thử restore vẫn cần thiết.

## 2. Phân biệt shard, replica, leader và coordinator

| Thuật ngữ | Ý nghĩa | Không được nhầm với |
|---|---|---|
| **Shard/partition** | Phần dữ liệu được chia theo khóa hoặc khoảng khóa | Một replica cụ thể |
| **Replica** | Một bản sao của shard/dữ liệu | Một shard độc lập |
| **Replication factor (RF)** | Số bản sao mục tiêu cho một phần dữ liệu | Tổng node toàn cluster |
| **Leader/primary** | Nút có quyền ghi/quyết định cho một phạm vi trong một nhiệm kỳ | Luôn là một node duy nhất của cả cluster |
| **Follower/secondary** | Nút học và áp dụng thay đổi từ leader | Mặc nhiên đọc được giá trị mới nhất |
| **Coordinator** | Nút tiếp nhận request rồi trao đổi với replica | Luôn là leader |
| **Quorum** | Tập/số lượng node cần đáp ứng theo protocol | Bất kỳ đa số nào cũng đủ bảo đảm mạnh |
| **Epoch/term** | Phiên bản quyền leadership hoặc vòng bầu chọn | Timestamp tường của dữ liệu |
| **Replication lag** | Mức chậm của một bản so với dữ liệu/log tham chiếu | Tự là thước đo đầy đủ tính đúng |

Ví dụ cluster có 12 node, dữ liệu chia thành 20 shard, mỗi shard được sao chép ba lần:

~~~text
Shard S03:
  Replica S03-A
  Replica S03-B
  Replica S03-C

Replication factor của S03 = 3.
Tổng số node cluster có thể là 12.
~~~

Nếu S03 có một leader và S04 có leader khác, hệ thống có **nhiều leader trên toàn cluster**, nhưng vẫn là **single-leader per shard**, không phải multi-leader cùng nhận ghi cho một key.

## 3. Ba mô hình theo đường đi của một request

~~~mermaid
flowchart LR
    subgraph ONE["Leader–follower"]
        C1["Client"] --> L["Leader"]
        L --> F1["Follower A"]
        L --> F2["Follower B"]
    end
    subgraph MANY["Nhiều leader"]
        CA["Client vùng A"] --> LA["Leader A"]
        CB["Client vùng B"] --> LB["Leader B"]
        LA <-->|"Replicate / resolve"| LB
    end
    subgraph NONE["Không leader cố định"]
        C2["Client"] --> CO["Coordinator"]
        CO --> RA["Replica A"]
        CO --> RB["Replica B"]
        CO --> RC["Replica C"]
    end
~~~

Trong sơ đồ:

- Leader–follower đặt **đường write chính** qua leader, nhưng đường read có thể dùng follower.
- Multi-leader có **nhiều nơi chấp nhận write cho cùng dữ liệu**, nên đồng bộ đến muộn có thể phát hiện phiên bản xung đột.
- Leaderless không chỉ định một replica làm **chủ ghi lâu dài**; coordinator có thể thay theo request, còn quorum và resolver xác định cách trả kết quả.

Ba họ mô hình không bao quát mọi biến thể thực tế. Một hệ thống có thể phối hợp nhiều kỹ thuật theo lớp dữ liệu hoặc thao tác.

## 4. Leader–follower: một đường ghi có thẩm quyền

Giả sử order-1001 có trạng thái PENDING. Luồng ghi đơn giản:

~~~text
Client
  |
  | update status=PENDING -> RESERVED
  v
Leader của shard orders
  |
  +-- ghi log/áp dụng mutation
  +-- truyền delta/log sang Follower 1
  +-- truyền delta/log sang Follower 2
  |
  +-- trả ACK theo chính sách
~~~

Các bước thường diễn ra:

1. Router/driver gửi request tới leader có quyền ghi cho key hoặc shard.
2. Leader kiểm tra điều kiện ghi và đặt thao tác vào thứ tự được engine công nhận.
3. Các follower nhận mutation hoặc replication log.
4. Mỗi follower áp dụng dữ liệu theo cơ chế sản phẩm.
5. Client nhận ACK khi các điều kiện xác nhận ghi đã được đáp ứng.

Lợi ích của một leader cho một phạm vi dữ liệu là dễ tạo **thứ tự ghi thống nhất**:

~~~text
log position 501: status=PENDING
log position 502: status=RESERVED
log position 503: status=PAID
~~~

Nhưng thứ tự ấy không thay thế **điều kiện nghiệp vụ**. Nếu hai request không điều kiện liên tục ghi PAID rồi CANCELLED, một leader có thể áp dụng cả hai theo thứ tự mà business invariant vẫn sai. Cần **conditional update, version/CAS hoặc transaction** phù hợp.

## 5. ACK, synchronous và asynchronous replication

**Khi nào một write được xem là thành công?** Đây là câu hỏi khác với việc leader đã nhận request.

| Chính sách ACK khái quát | Khi nào trả thành công? | Lợi ích | Rủi ro/đánh đổi |
|---|---|---|---|
| Ghi cục bộ rồi ACK | Leader đáp ứng ngưỡng nội bộ | Độ trễ thấp | Follower có thể chưa biết write; rủi ro mất ghi tùy failover/durability |
| Chờ một số replica | Đủ số node ACK theo protocol | Tăng độ bền trước một số lỗi | Phải chờ mạng/replica; có thể timeout |
| Chờ mọi replica yêu cầu | Tất cả bản trong tập đích ACK | Có thêm điều kiện đồng bộ | Một replica chậm có thể chặn write |

Các từ **synchronous**, **semi-synchronous**, **asynchronous**, **majority** không có nghĩa đồng nhất trong mọi engine. Khi cấu hình cần làm rõ:

- Replica đã **nhận** mutation hay đã **ghi bền vững**?
- Replica đã **apply** để đọc ra giá trị mới hay mới ghi log?
- ACK có bảo vệ write qua **leader failover** không?
- Nếu một shard đang đổi leader, tập node được tính quorum là tập nào?
- Một transaction nhiều document/shard được ACK ra sao?

**Replica ACK không đồng nghĩa tất cả người đọc ở mọi vùng đã thấy dữ liệu mới.** Một bản có thể đã lưu log nhưng vẫn chưa cung cấp giá trị ấy qua đường đọc hiện tại.

## 6. Follower lag và stale read

Ban đầu x=0 ở leader và follower. Client A ghi x=1:

~~~text
t1: A write(x,1) đến leader.
t2: Leader ACK theo cấu hình.
t3: B bắt đầu read(x) trên follower.
t4: Follower mới nhận/áp dụng x=1.
~~~

Nếu B đọc tại t3 và được trả **0**, nó đã thấy bản cũ.

- Nếu API đọc follower được công bố **eventual consistency**, read cũ có thể nằm trong hợp đồng.
- Nếu API được công bố **linearizable** cho cùng đối tượng, B bắt đầu sau ACK của A mà vẫn thấy 0 (không có write về 0) sẽ trái bảo đảm thời gian thực.
- Nếu read bắt đầu **chồng lấn write**, giá trị cũ không tự chứng minh vi phạm linearizability.

Các chiến lược thường gặp:

1. **Authoritative read:** đọc từ đường mạnh do engine hỗ trợ.
2. **Session token:** ghi nhớ version/log position vừa ghi; chỉ chấp nhận read đạt ít nhất mốc ấy.
3. **Read-your-writes trên session:** driver hoặc ứng dụng gắn tuyến đọc/session theo hợp đồng.
4. **Chấp nhận stale:** thiết kế UI rõ trạng thái đang xử lý, còn quyết định cuối dựa trên conditional write.

**Đọc từ leader không phải lời hứa linearizability tuyệt đối không cần điều kiện**: leader có thể mất quyền, network partition hoặc thay term; protocol và API phải bảo vệ read trong tình huống đó.

## 7. Ví dụ read model và nguồn dữ liệu

Ứng dụng vé có thể cố ý dùng hai đường:

~~~text
GET /shows/07/seats
  -> cache hoặc follower
  -> cho phép stale theo SLO hiển thị

POST /shows/07/seats/A12/claim
  -> conditional write trên nguồn thẩm quyền
  -> chỉ một reservation hợp lệ được công nhận

GET /reservations/res-9001/authoritative
  -> đọc mạnh theo guarantee sản phẩm
~~~

Một màn hình đôi khi vẫn hiển thị **AVAILABLE** sau khi ghế bị giữ. Đó có thể là một đánh đổi UX được chấp nhận. Nhưng khi Client B thực sự **claim**, nguồn phải kiểm tra lại điều kiện, không lấy giá trị từ cache làm bằng chứng.

Điều này cho phép hệ thống mở rộng read-heavy workload mà không lấy **tính đúng của quyết định** ra đánh đổi.

## 8. Leader failover và quyền sở hữu log

Khi leader lỗi, follower có thể được bầu thành leader mới:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant L as Leader cũ
    participant F1 as Follower 1
    participant F2 as Follower 2
    C->>L: write x=1
    L-->>C: ACK theo write concern
    Note over L: Mất liên lạc
    F1->>F2: Election/coordination
    Note over F1,F2: Xác định term và log hợp lệ
    C->>F1: Retry hoặc read
    F1-->>C: Trạng thái theo protocol mới
~~~

Quy trình có thể gồm:

- Nhận biết leader không phản hồi qua heartbeat/timeout.
- Bầu chọn theo điều kiện quorum/term của engine.
- Chọn node có trạng thái/log thích hợp.
- Chuyển tuyến client/driver.
- Kiểm tra những write đã ACK và những thao tác còn UNKNOWN.
- Catch-up hoặc reconcile node cũ khi quay lại.

**Failover không luôn lập tức.** Có thể có khoảng tạm thời không cho write, retry lỗi chuyển tuyến, client timeout và những thao tác chưa xác định kết quả.

## 9. Split-brain và fencing

Giả sử:

~~~text
Trước lỗi:
  L là leader; F1, F2 là follower.

Sau network partition:
  Nhóm 1: L đơn độc.
  Nhóm 2: F1, F2 có thể đạt quorum.
~~~

Nếu **L cũ** vẫn tự ACK write như leader, đồng thời nhóm 2 bầu leader mới và ACK write mâu thuẫn trên cùng key, sẽ có nguy cơ **split-brain**.

Những biện pháp liên quan:

- **Term/epoch:** nhận diện nhiệm kỳ leader mới.
- **Quorum election/commit:** hạn chế bên không đủ quyền tiếp tục commit.
- **Fencing token:** hệ đích từ chối lệnh có quyền sở hữu phiên bản cũ.
- **Log reconciliation:** xử lý các log entry không thuộc lịch sử được công nhận sau khi liên lạc hồi phục.
- **Client routing:** driver không tiếp tục gửi write đến leader cũ.

Một lease có thời hạn không tự ngăn một worker bị tạm dừng lâu, tỉnh dậy rồi tiếp tục thao tác vào hệ ngoài. Nếu việc ghi liên quan payment/storage khác, cần **idempotency hoặc fencing được hệ đích thực thi**.

## 10. Ghi bị mất sau failover khác với stale read

Một lịch sử:

~~~text
L nhận write x=1.
L trả ACK theo mức cục bộ.
L chết trước khi follower nhận ghi.
F1 được bầu leader, còn x=0.
~~~

Khi đó, tùy chính sách sản phẩm, ghi đã ACK ở mức yếu có thể **bị rollback/mất sau failover**. Đây không đơn thuần là follower trễ rồi sẽ bắt kịp.

| Hiện tượng | Dấu hiệu | Cần quan sát |
|---|---|---|
| **Replication lag** | Replica vẫn cũ nhưng có thể bắt kịp | Oplog/log positions, lag, read mode |
| **ACK yếu rồi mất write** | Sau failover không có dữ liệu đã công bố | Durability/write concern, election rules |
| **Unknown outcome** | Client timeout sau khi gửi write | Operation ID, status verification, retry |
| **Conflicting writes** | Nhiều nơi ACK các phiên bản khác nhau | Conflict versions và resolver |

Một giao dịch tài chính không thể chỉ dựa vào “có ba node” rồi mặc định không có rủi ro mất write. Phải chọn đúng **durability và recovery contract**.

## 11. MongoDB replica set là ví dụ leader–follower

Trong MongoDB replica set, **primary** nhận những thao tác ghi thông thường và **secondary** theo dõi thay đổi qua oplog. Đường đọc từ secondary có thể được phép thông qua read preference, nhưng độ mới và read concern có bảo đảm riêng.

Ví dụ một ghi có điều kiện trên một document:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "order-1001",
    tenantId: "shop-a",
    status: "PENDING"
  },
  {
    $set: { status: "RESERVED" }
  },
  {
    writeConcern: { w: "majority" }
  }
);

printjson(result);
~~~

Phân biệt:

- **Atomic updateOne trên một document:** một operation đổi trạng thái document theo điều kiện.
- **Write concern majority:** trả ACK theo sự xác nhận đa số phù hợp cơ chế replica set.
- **Read concern majority:** đọc dữ liệu đã đạt mức commit được bảo đảm theo ngữ nghĩa sản phẩm.
- **Read concern linearizable:** bảo đảm đọc theo thời gian thực trong phạm vi và điều kiện được hỗ trợ; không đồng nghĩa majority.
- **Read preference secondary:** có thể đọc follower, cần hiểu giới hạn stale/failover.

Một lệnh đọc authoritative trên deployment/phiên bản hỗ trợ có thể được minh họa:

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "order-1001" },
  readConcern: { level: "linearizable" },
  maxTimeMS: 5000
});
~~~

Đừng áp dụng bừa readConcern linearizable cho mọi query, collection hoặc secondary: cần kiểm tra phạm vi API, topology, write concern và phiên bản MongoDB. Những lệnh quản trị như step-down/reconfigure phải theo runbook, không dùng tùy tiện để thử trên production.

## 12. Redis primary–replica cũng có nguy cơ đọc cũ

Redis thường triển khai một primary nhận ghi và các replica theo sau. Các command như **SET** và **INCR** được thực hiện theo cơ chế thứ tự của instance.

~~~redis
SET order:order-1001 PENDING
SET order:order-1001 RESERVED
GET order:order-1001
~~~

GET từ primary sau những SET tương ứng có thể thấy trạng thái mới, nhưng GET từ replica lag có thể thấy PENDING.

Replication, Redis Sentinel/Cluster, AOF/RDB persistence và những cơ chế đợi ACK replica là các phần riêng. **ACK từ một replica không tự đồng nghĩa dữ liệu đã fsync bền vững hoặc mọi failover duy trì đầy đủ thứ tự tuyến tính hóa toàn hệ**.

Nếu Redis là cache, có thể xử lý stale bằng cache version/invalidation và lấy lại nguồn. Nếu dùng làm nguồn duy nhất cho quyền giữ tài nguyên, phải cân nhắc kỹ durability, failover, lease/fencing và idempotency thay vì chỉ dựa vào SET NX.

## 13. Multi-leader: nhiều nơi có quyền ghi cùng dữ liệu

Một vùng A và vùng B có thể cùng nhận write:

~~~mermaid
flowchart LR
    UA["Client vùng A"] --> LA["Leader A"]
    UB["Client vùng B"] --> LB["Leader B"]
    LA <-->|"Trao đổi các thay đổi"| LB
    LA --> RA["Follower A"]
    LB --> RB["Follower B"]
~~~

Ví dụ profile ban đầu theme=light:

~~~text
Vùng A:
  update theme=dark -> ACK.

Vùng B:
  chưa thấy update của A;
  update theme=blue -> ACK.

Khi WAN hồi phục:
  A và B trao đổi hai phiên bản.
~~~

Hệ phải quyết định:

- Chọn dark.
- Chọn blue.
- Giữ cả hai phiên bản để người dùng chọn.
- Merge nếu phép gộp có ngữ nghĩa đúng.
- Xác định một vùng có quyền chỉnh sửa field/key đó.

Khác với một leader quyết định một log ghi duy nhất, multi-leader có thể có **hai ý định được công nhận cục bộ trước khi có thứ tự chung**. Điều này rất phù hợp dữ liệu địa lý/offline ở một số ứng dụng, nhưng gây khó với invariants toàn cục.

## 14. Lợi ích và chi phí của multi-leader

Lợi ích:

- Người dùng ghi tới region gần hơn nên giảm độ trễ WAN.
- Các vùng có thể tiếp tục nhận một số ghi khi mất kết nối liên vùng.
- Phù hợp offline-first, local-first hoặc nhiều site.
- Với trường dữ liệu merge được, trải nghiệm ghi cục bộ tốt.

Đánh đổi:

- Conflict trên cùng một logical key có thể được ACK ở nhiều nơi.
- Unique constraint xuyên vùng rất khó bảo đảm nếu hoàn toàn không phối hợp.
- Read ở vùng khác có thể stale sau ACK cục bộ.
- Cần conflict policy, version metadata, dedup, repair và reconciliation.
- Có thể phát sinh chi phí đồng bộ và xử lý lỗi nghiệp vụ.

**Multi-leader không tự bảo đảm mọi request ở mọi vùng luôn thành công.** Một region có thể vẫn cần local quorum, phụ thuộc metadata hoặc policy cụ thể; các tài nguyên có business invariant cứng có thể từ chối ghi khi không đủ điều kiện.

## 15. Một ví dụ conflict nghiệp vụ: PAID và CANCELLED

Order nguồn ban đầu:

~~~javascript
{
  _id: "order-1001",
  tenantId: "shop-a",
  status: "PENDING",
  revision: 7
}
~~~

Hai region mất liên lạc:

~~~text
Region A:
  PENDING -> PAID
  có thể đã capture tiền.

Region B:
  PENDING -> CANCELLED
  có thể đã release stock.
~~~

Sau khi đồng bộ, **chọn trạng thái có timestamp lớn hơn không giải quyết được toàn bộ hậu quả**. Nếu giữ PAID thì stock có thể đã được trả; nếu giữ CANCELLED thì tiền có thể đã bị thu.

Các chiến lược:

1. **Một owner region cho từng order**, chỉ một nơi quyết định chuyển trạng thái.
2. **Conditional write/CAS/transaction** theo nguồn thẩm quyền khi hệ hỗ trợ phối hợp.
3. **Quota hoặc escrow** phân bổ trước khi ghi ở các vùng.
4. **Sổ event và Saga** để giữ dấu vết hiệu ứng thật, bù hoặc hoàn tiền nếu cần.
5. **Reconciliation** với payment provider và kho, không chỉ đối chiếu status string.

Multi-leader có thể phục vụ rất tốt thuộc tính profile, nhưng **không được dùng cùng một policy LWW mù quáng cho tiền/tồn/quyền sở hữu**.

## 16. Những loại xung đột phổ biến

| Loại | Ví dụ | Tác hại |
|---|---|---|
| **Write–write** | Hai vùng sửa email | Mất một edit |
| **Write–delete** | Một vùng sửa, vùng khác xóa | Dữ liệu đã xóa có thể hồi sinh |
| **Create–create** | Cùng tạo username giống nhau | Trùng định danh toàn cục |
| **Counter concurrent** | Hai vùng cộng điểm từ cùng giá trị cũ | LWW làm mất một lần cộng |
| **State transition** | CONFIRM vs CANCEL | Các side effects có thể mâu thuẫn |
| **Schema mismatch** | Vùng A dùng schema mới, B schema cũ | Consumer/merge không tương thích |

Conflict policy nên được thiết kế **theo từng field và ý nghĩa nghiệp vụ**. Có thể cho phép LWW ở displayName nhưng cần append-only ledger cho loyaltyPoints và authoritative transition cho paymentStatus.

## 17. Last-write-wins (LWW) và nguy cơ mất cập nhật

Ban đầu points=100:

~~~text
Region A đọc 100 -> cộng 10 -> ghi 110.
Region B đọc 100 -> cộng 20 -> ghi 120.

Sau LWW:
  chọn 120 hoặc 110.

Ý định nghiệp vụ đúng nếu cả hai lần cộng độc lập:
  130.
~~~

LWW tạo ra một giá trị hội tụ, nhưng **có thể làm mất một trong hai thay đổi**. Timestamp máy A và B có thể lệch, nên “last” có thể chỉ là **timestamp lớn nhất** chứ không phải thao tác xảy ra muộn nhất theo thời gian thực.

Để giải quyết, phải xác định:

- Giá trị nào có thể bị thay thế mà không sao?
- Trường nào nên dùng event/increment thay vì overwrite?
- LWW so sánh timestamp nào, clock skew ra sao?
- Cần giữ **siblings** để ứng dụng giải quyết không?
- Có đang bỏ một side effect thật như payment hoặc stock không?

Một quy tắc LWW đơn giản không cung cấp linearizability hoặc exactly-once business processing.

## 18. Version vector nhận biết cập nhật đồng thời

Các hệ phân tán có thể gắn metadata phiên bản để biết thay đổi nào dựa trên thay đổi nào.

Ví dụ vector hai vùng:

~~~text
Trạng thái gốc:
  {A:2, B:4}

Vùng A ghi mới:
  {A:3, B:4}

Vùng B ghi độc lập:
  {A:2, B:5}
~~~

Không vector nào **lớn hơn hoặc bằng theo tất cả thành phần** so với vector còn lại. Hai phiên bản được xem là **concurrent** trong mô hình version vector thích hợp.

Trong khi đó:

~~~text
{A:3, B:5} >= {A:3, B:4}
~~~

theo từng thành phần, nên vector thứ nhất có thể bao hàm lịch sử thứ hai.

**Vector clock giúp phát hiện quan hệ nhân quả/concurrency, không tự quyết định merge nào đúng.** Nó cũng không phải khả năng mặc định của mọi hệ NoSQL; cách lưu/version vectors, dotted versions và số writer khác nhau theo sản phẩm.

## 19. CRDT: gộp dữ liệu mà không bỏ một thay đổi độc lập

**Conflict-free Replicated Data Type (CRDT)** dùng những cấu trúc có phép gộp được thiết kế để các replica hội tụ khi nhận dữ liệu đủ, bất kể một số thứ tự trao đổi.

Ví dụ G-counter gồm thành phần tăng tại từng replica:

~~~text
Gốc:
  {A:0, B:0}

Region A tăng 3:
  {A:3, B:0}

Region B tăng 2:
  {A:0, B:2}

Merge lấy max từng thành phần:
  {A:3, B:2}

Giá trị tổng:
  5
~~~

LWW chọn 3 hoặc 2 sẽ bỏ mất một phần; G-counter giữ cả hai increment trong ví dụ.

Các họ CRDT khác gồm PN-counter, grow-only set, observed-remove set hoặc map với ngữ nghĩa riêng. Chúng không miễn phí: cần metadata, cơ chế merge, loại dữ liệu và policy xóa phù hợp.

**CRDT counter không tự đảm bảo stock không âm** khi hai vùng cùng trừ số lượng chưa phân bổ. Có thể phải dùng escrow/quota, owner per SKU, conditional writes hoặc transaction. Hợp nhất dữ liệu đúng về mặt cấu trúc không đồng nghĩa mọi business invariant được giữ.

## 20. Tombstone và xóa trong multi-leader

Region A xóa profile trong khi Region B offline còn giá trị cũ:

~~~text
Region A:
  profile = DELETED, version 9

Region B:
  profile = old value, version 8
~~~

Nếu chỉ xóa vật lý ở A mà không lưu bằng chứng xóa, khi B quay lại có thể gửi bản cũ và **hồi sinh** profile. Nhiều hệ sử dụng **tombstone/delete marker** và version để bảo đảm delete cũng được lan truyền.

Phải xét:

- Replica offline bao lâu?
- Tombstone còn đủ lâu để đến các replica?
- Có client offline lưu bản cũ nhiều tháng không?
- Có chính sách merge cho delete và concurrent update?
- Dữ liệu backup và read models có còn giữ thông tin cần xóa không?

Đối với yêu cầu xóa dữ liệu cá nhân, **chỉ một node đã xóa** không đủ để khẳng định hoàn tất việc xóa trên toàn hệ.

## 21. Không có leader cố định: coordinator và replica quorum

Trong họ thiết kế **Dynamo-style leaderless replication**, không có một replica được chỉ định nhận toàn bộ write cho key suốt một nhiệm kỳ. Node nhận request có thể làm coordinator, chuyển thao tác tới các replica mục tiêu.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant CO as Coordinator
    participant A as Replica A
    participant B as Replica B
    participant D as Replica C
    C->>CO: write(K, value)
    par Ghi song song
        CO->>A: write K
        CO->>B: write K
        CO->>D: write K
    end
    A-->>CO: ACK
    B-->>CO: ACK
    Note over CO: Đủ W=2 theo chính sách ví dụ
    CO-->>C: Success
    D-->>CO: ACK muộn hoặc timeout
~~~

Điểm cốt lõi:

- Coordinator có thể thay đổi theo request.
- Replica có thể nhận các mutation ở thời điểm/thứ tự khác nhau.
- Khi đọc, coordinator hỏi một tập replica và chọn/merge version.
- Nếu replica lệch, cần read repair/anti-entropy.
- Nếu replica mất liên lạc, một số hệ cho phép nhận ghi vào node thay thế.

**Leaderless không nghĩa là không có coordinator, metadata, consensus hoặc cơ chế conditional write.** Một sản phẩm có thể dùng leaderless cho ordinary mutations nhưng dùng giao thức khác như Paxos/LWT cho CAS.

## 22. Công thức N, R, W

Trong mô hình quorum đơn giản:

\[
N = \text{số replica mục tiêu của một key/partition}
\]

\[
W = \text{số replica cần ACK cho một write}
\]

\[
R = \text{số replica cần tham gia một read}
\]

Với **N replica cố định**, bất đẳng thức:

\[
R + W > N
\]

bảo đảm một tập R node và một tập W node được chọn từ **cùng N replica** phải giao nhau ít nhất một node.

Ví dụ N=3, W=2, R=2:

~~~text
Write quorum = {A,B}
Read quorum  = {B,C}

Hai tập giao nhau ở B.
~~~

Một read có thể tiếp xúc với bản sao đã nhận write. Nhưng **giao nhau không tự bảo đảm hệ biết phiên bản đúng và trả một kết quả linearizable**.

| N | W | R | R+W>N? | Diễn giải |
|---:|---:|---:|---|---|
| 3 | 1 | 1 | Không | Có thể đọc từ node chưa nhận write |
| 3 | 2 | 2 | Có | Hai tập quorum giao nhau nếu N cố định |
| 3 | 3 | 1 | Có | Ghi cần mọi replica; node lỗi có thể chặn |
| 5 | 3 | 3 | Có | Tập ba trên năm luôn giao nhau |
| 5 | 2 | 2 | Không | Hai tập có thể rời nhau |
| 5 | 4 | 2 | Có | Ghi cần nhiều ACK, read cần ít hơn |

Đây là **số học tập hợp**, không phải đặc tả giao dịch.

## 23. Vì sao R + W > N chưa đủ cho linearizability?

Ngay cả với N=3, R=W=2:

1. **Concurrent writes:** hai write cạnh tranh có thể tới replica theo thứ tự khác nhau; cần protocol xác định thứ tự/phiên bản hợp lệ.
2. **Pending writes:** write đã đến một phần replica nhưng client timeout; read có thể thấy giá trị đó, rồi read khác thấy cũ nếu protocol không bảo vệ.
3. **Read semantics:** nếu read thấy nhiều version, phải biết chọn hoặc ghi trả lại version nào theo bảo đảm.
4. **Sloppy quorum:** write ACK từ node thay thế ngoài tập home replicas, làm giả thiết giao nhau sai.
5. **Topology change:** tập replica mục tiêu thay đổi trong lúc read/write.
6. **Clock skew:** LWW timestamp không tự phản ánh thứ tự real-time.
7. **Durability:** các replica ACK có thể mất dữ liệu theo chính sách lưu trữ/failover.

Một lớp thuật toán register linearizable có thể cần **version ordering, read-back/write-back hoặc phối hợp bổ sung** để tránh read quay ngược sau một write chưa rõ kết quả. Chỉ đặt R+W>N trên slide không chứng minh các bước này.

### Lịch sử minh họa điều cần xem

~~~text
W1 bắt đầu ghi x=1.
Một replica nhận x=1.
Client W1 timeout, outcome UNKNOWN.
R1 đọc và nhìn thấy x=1.
R2 bắt đầu sau R1, đọc lại x=0.
~~~

Nếu không có write hợp lệ về 0 và hai read được hứa linearizable, lịch sử có thể không tuyến tính hóa được. Thuật toán đúng phải ngăn những kết quả như vậy theo đặc tả, kể cả với pending write. **Quorum intersection đơn thuần không phải lời giải toàn bộ**.

## 24. Sloppy quorum và hinted handoff

Giả sử home replicas của key K là A, B, C. Replica C offline:

~~~text
Home:
  A, B, C

Khi C offline:
  A và B nhận write.
  D (node thay thế) giữ bản tạm/hint cho C.
~~~

Trong **sloppy quorum**, một số hệ cho phép node không thuộc tập home replicas nhận write để tăng khả năng phục vụ. **Hinted handoff** chuyển dữ liệu đã giữ tạm về replica đích khi nó quay lại.

Lợi ích là giảm khả năng write bị từ chối do thiếu home replica. Đánh đổi là tập node thực tế ACK có thể không trùng tập N mà read sau đó hỏi, nên **R+W>N trên home set không tự bảo đảm giao nhau như ví dụ lý tưởng**.

Các câu hỏi cần có trong runbook:

- Hint được giữ ở đâu và bao lâu?
- Có bảo đảm hint được replay nếu node thay thế lỗi?
- Khi C trở lại, khi nào handoff hoàn tất?
- Có cần repair định kỳ nếu hint thất lạc hoặc quá hạn không?
- Read nào được phép trả stale trước khi repair?

Không phải mọi hệ leaderless đều triển khai sloppy quorum/hints theo một cách.

## 25. Read repair và anti-entropy

Khi read nhận các version khác nhau:

~~~text
Replica A: version 8
Replica B: version 7
Replica C: version 7
~~~

Coordinator có thể phát hiện lệch, chọn kết quả theo resolver và cập nhật replica chậm. Đó là ý tưởng **read repair**, với chi tiết tùy engine.

**Anti-entropy** là công việc đồng bộ ở nền để phát hiện và sửa các bản sao khác biệt, kể cả dữ liệu lâu không được đọc. Hệ có thể dùng **Merkle tree hoặc các cấu trúc hash/tóm lược** để so sánh tập dữ liệu lớn một cách hiệu quả hơn.

~~~mermaid
flowchart TD
    A["Read/repair task"] --> B["Lấy version từ replicas"]
    B --> C{"Các bản giống nhau?"}
    C -->|"Có"| D["Phục vụ kết quả"]
    C -->|"Không"| E["Resolver xác định bản hợp lệ hoặc conflict"]
    E --> F["Repair/handoff theo policy"]
    F --> G["Hội tụ và giám sát backlog"]
~~~

**Read repair không sửa lại response stale đã trả về trước đó.** Nếu API hứa read mạnh, protocol phải bảo đảm kết quả trong chính request ấy; background repair về sau không đủ.

Read repair/compaction/anti-entropy cũng có chi phí disk I/O, CPU, network và có thể ảnh hưởng p99 latency.

## 26. Tombstone trong leaderless replication

Khi key bị xóa:

~~~text
Replica A: TOMBSTONE
Replica B: TOMBSTONE
Replica C: old value (offline)
~~~

Nếu tombstone bị dọn quá sớm, một replica cũ khi trở lại có thể đẩy bản dữ liệu đã xóa vào cluster. Vì vậy cần:

- Lan truyền delete marker theo ngữ nghĩa engine.
- Xác định thời gian offline tối đa/repair interval.
- Đối soát tombstones trước khi dọn metadata xóa.
- Hiểu tác động TTL tới tombstones và compaction.
- Đảm bảo dữ liệu cũ không được diễn giải như update hợp lệ mới.

Trong hệ lưu trữ kiểu Cassandra/LSM, tombstone còn có thể làm read phải duyệt nhiều mục đã xóa, gây **read amplification** và tăng chi phí compaction.

Không tự thay đổi thời hạn dọn tombstone chỉ để giảm disk mà không có quy trình repair và backup.

## 27. Cassandra: ordinary reads/writes theo coordinator và replica

Apache Cassandra là ví dụ thường dùng cho **mô hình không có leader cố định ở đường dữ liệu thông thường**. Một node client kết nối có thể làm coordinator và liên lạc với replica của partition theo replication strategy.

Ví dụ:

~~~sql
CREATE TABLE order_status_by_id (
    tenant_id text,
    order_id text,
    status text,
    revision bigint,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Trong cqlsh:

~~~sql
CONSISTENCY QUORUM;

SELECT status, revision
FROM order_status_by_id
WHERE tenant_id = 'shop-a'
  AND order_id = 'order-1001';
~~~

**CONSISTENCY QUORUM** là lệnh cài mode cho **cqlsh**, không phải một statement CQL mà mọi SDK dùng như trên. Trong driver, consistency thường được đặt vào statement options.

Các điểm quan trọng:

- **QUORUM, LOCAL_QUORUM, ONE** và các mức khác xác định số/tập replica tham gia theo topology.
- Ordinary read/write ở QUORUM không tự bảo đảm một chuỗi **SELECT rồi UPDATE** là CAS nguyên tử.
- Concurrent writes vào cùng cell có cơ chế xử lý timestamp/conflict riêng, phải hiểu ngữ nghĩa và đồng hồ.
- Repair, hinted handoff và tombstones là thành phần vận hành quan trọng.
- LWT/Paxos có cơ chế điều kiện và consistency scope khác đường ordinary write.

### Lightweight transaction là trường hợp đặc biệt

~~~sql
UPDATE order_status_by_id
SET status = 'RESERVED', revision = 2
WHERE tenant_id = 'shop-a'
  AND order_id = 'order-1001'
IF status = 'PENDING' AND revision = 1;
~~~

Ứng dụng phải đọc trường **[applied]** và xử lý conflict. LWT cho phép phối hợp conditional update trong phạm vi engine hỗ trợ; **không nên nói mọi mutation Cassandra đều cần một leader cố định vì hệ có Paxos/LWT**.

## 28. LOCAL_QUORUM và ghi đa datacenter

Giả sử:

~~~text
DC-A: A1, A2, A3 (RF=3)
DC-B: B1, B2, B3 (RF=3)
~~~

Một ghi dùng **LOCAL_QUORUM** tại DC-A có thể được xác nhận khi đủ replica trong DC-A, trong khi DC-B chưa bắt kịp. Điều đó giúp giảm latency liên vùng nhưng không đồng nghĩa read ở DC-B ngay lập tức thấy mới.

Khi thiết kế cần trả lời:

1. RF của **mỗi datacenter**?
2. Local DC được driver chọn thế nào?
3. Local quorum thuộc **những replica nào**?
4. LWT/transaction có yêu cầu SERIAL hoặc LOCAL_SERIAL không?
5. Nếu WAN bị chia cắt, các read/write ở từng vùng có behavior nào?
6. Khi hai vùng cùng ghi một key, resolver có thể mất update nào?

Đừng dùng chữ **quorum** mà không nói rõ phạm vi. Một local quorum không phải quorum toàn cầu chỉ vì cluster có nhiều DC.

## 29. Dynamo-style và dịch vụ có tên Dynamo không phải đồng nhất

Họ thiết kế Dynamo cổ điển mô tả leaderless replication, quorum, versioning, hinted handoff, anti-entropy và trade-off availability.

Tuy nhiên, **Amazon DynamoDB** là một dịch vụ có API và mode consistency riêng, không cho người dùng mặc nhiên điều chỉnh R/W/N giống một mô hình Dynamo học thuật:

- Base-table reads có lựa chọn eventual/strong trong phạm vi hỗ trợ.
- GSI có đặc điểm đọc eventual.
- Global tables có các chế độ/giới hạn replication đa vùng cần tra đúng tài liệu phiên bản và cấu hình.
- Conditional writes và transaction là những API có hợp đồng riêng.

Không nên lấy tên một sản phẩm rồi kết luận nó triển khai **chính xác** mọi cơ chế trong Dynamo paper. Bài học N/R/W là **mô hình suy luận**, còn production cần cấu hình đúng API sản phẩm.

## 30. Ba mô hình đặt cạnh nhau

| Tiêu chí | Leader–follower | Multi-leader | Leaderless |
|---|---|---|---|
| **Đường ghi chủ đạo** | Một leader/shard | Nhiều leader cho cùng dữ liệu | Coordinator gửi đến replicas |
| **Thứ tự ghi** | Leader/log có thể xếp thứ tự | Có thể có ghi concurrent giữa leaders | Resolver/protocol xử lý versions |
| **Read local** | Follower có thể stale | Read vùng gần có thể stale | Tùy replica set và R |
| **Failover** | Election/term/đổi leader | Sync/owner/region policy | Chọn replica còn đủ ACK |
| **Xung đột** | Ít hơn trên cùng shard khi leader đúng | Đặc trưng trọng tâm | Có thể có concurrent versions |
| **Repair** | Oplog catch-up/resync | Conflict sync/reconciliation | Read repair/anti-entropy/hints |
| **Hotspot** | Leader/shard nóng | Một key nhiều nơi tranh chấp | Replica/partition/coordinator nóng |
| **Bảo vệ invariant** | Conditional write/transaction | Cần owner/coordination/quota | CAS/LWT/transaction phù hợp |
| **Chi phí vận hành** | Elections, lag, replica health | Merge, multi-region, unique conflicts | Repair, tombstone, quorum configs |

Bảng mang tính định hướng, không phải một bảng xếp hạng hiệu năng hoặc lời hứa cho mọi engine.

## 31. Một số trường hợp dễ phân loại sai

~~~text
Shards:
  S1 leader ở A.
  S2 leader ở B.
  S3 leader ở C.
~~~

Đây là **single-leader per shard**. Không gọi multi-leader chỉ vì tổng cluster có nhiều leader.

~~~text
Hai vùng A và B:
  cùng được phép ghi customer-07.profile.theme
  trước khi thấy thay đổi của nhau.
~~~

Đây là ví dụ **multi-leader trên cùng một logical object**.

~~~text
Client gửi write tới node X.
X làm coordinator gửi tới 3 replicas.
Request sau có thể đến node Y, không có owner write cố định.
~~~

Đây là hình thức **leaderless/coordinator-style**.

Một cluster thực có thể có replication leader–follower cho dữ liệu, leader/quorum riêng cho metadata và transaction protocol khác cho conditional updates.

## 32. CAP khi network partition

Trong tình huống hai phía mất liên lạc, một hệ vừa muốn **nhất quán tuyến tính trên cùng key**, vừa muốn **mọi phía đều ACK write**, có thể gặp xung đột yêu cầu.

Ví dụ:

~~~text
Region A: có request claim username "an".
Region B: có request claim username "an".
Hai region không liên lạc.
~~~

Nếu cả hai cùng trả **“đã giữ tên duy nhất toàn cầu”** mà không có phân quyền/quota/đồng thuận nào, cả hai có thể cùng công nhận một username, vi phạm uniqueness.

Các lựa chọn có chủ đích:

- Một phía từ chối hoặc chờ cho đến khi đủ authority.
- Chia ownership/namespace để mỗi tên thuộc một vùng quyết định.
- Cấp trước các quyền/quota không chồng nhau.
- Chấp nhận local claim tạm thời và có quy trình conflict resolution, không tuyên bố uniqueness cuối cùng ngay.

**CAP** mô tả đánh đổi giữa consistency theo nghĩa nhất định và availability trong partition. Không nên biến nó thành khẩu hiệu “database X luôn CP/AP” cho mọi API và mọi tình huống: read modes, per-shard quorums, session guarantees và thao tác điều kiện có thể khác nhau.

## 33. Thiết kế theo dữ liệu và bất biến

| Workload | Điều quan trọng | Hướng ứng viên |
|---|---|---|
| Giữ ghế duy nhất | Chỉ một claim hợp lệ được công nhận | Nguồn authority với conditional write/CAS |
| Thanh toán | Không nhân đôi tiền; kết quả có thể UNKNOWN | Idempotency, ledger, provider reconciliation |
| Lượt xem | Chấp nhận trễ, ghi cao | Counter/CRDT hoặc aggregate theo shard |
| Sở thích UI | Offline/multi-region ghi cục bộ | Multi-leader với merge policy rõ |
| Sensor events | Append-heavy, time-range, retention | Partition/bucket, RF và read levels phù hợp |
| Search index | Tìm kiếm, có thể trễ so với nguồn | Read model có replication/rebuild |
| Báo cáo phút | Phản ánh đủ sau một SLO hội tụ | Eventual/analytics với đối soát |

Một hệ có thể sử dụng nhiều loại replication, miễn mỗi API biết **nguồn dữ liệu có thẩm quyền** và **giới hạn độ mới** của nơi nó đọc.

## 34. Một ví dụ đơn hàng nhiều vùng

Giả sử order có state machine:

~~~text
PENDING -> STOCK_HELD -> PAYMENT_AUTHORIZED -> CONFIRMED
                 \-> CANCELLED
~~~

**Phương án leader–follower per order:**

1. Order được gán home shard/region có quyền ghi.
2. Mọi transition dùng status/version condition.
3. Replicas và read models ở vùng khác được đồng bộ.
4. UI local có thể stale; quyết định confirm/claim đọc và ghi tại nguồn.
5. Leader failover có term/quorum; retry dùng orderId/checkoutRequestId ổn định.

**Phương án multi-leader cho order state:**

1. A và B đều có thể chuyển cùng order.
2. Cần xử lý PAID/CANCELLED conflict, không chỉ LWW.
3. Nếu cần bảo đảm cứng, bổ sung ownership hoặc coordination.
4. Những payment effects thực sự đã áp dụng cần workflow bù/đối soát.

**Phương án ordinary leaderless writes:**

1. Coordinator có thể ghi tới nhiều replica.
2. Quorum và repair giúp hội tụ theo protocol.
3. Không tự đủ để bảo vệ mọi state transition.
4. Dùng CAS/LWT/transaction nơi cần để ngăn hai bước mâu thuẫn.

Trong mọi phương án, **payment provider** là hệ ngoài transaction NoSQL; cần Saga, idempotency và trạng thái UNKNOWN phù hợp.

## 35. Phân biệt consistency, durability và business correctness

Ba câu hỏi:

**Consistency model:** sau một write ACK, read sau đó có phải thấy write ấy không? Một hệ cho phép replica stale bao lâu?

**Durability:** nếu node vừa ACK chết, write có được giữ qua recovery/failover theo cấu hình không?

**Business invariant:** cùng một ghế có được hai khách claim thành công không? Stock có âm không? Payment có bị capture hai lần không?

Ví dụ một lệnh **SET stock=1** có thể được áp dụng nguyên tử và được đọc tuyến tính hóa, nhưng hai checkout đều có thể thông báo “đã giữ 4” nếu cả hai đọc giá trị cũ rồi set không điều kiện. Lỗi nằm ở **logic read–modify–write của ứng dụng**, không nhất thiết ở replication.

Ngược lại, một conditional update đúng trên nguồn có thể đảm bảo **không oversell**, dù một cache hiển thị số tồn cũ. Tính đúng của quyết định và độ mới của màn hình là hai hợp đồng cần tách.

## 36. Versioning và đồng hồ

Các hệ dùng nhiều loại metadata:

- **Wall-clock timestamp:** thuận tiện nhưng chịu clock skew.
- **Lamport logical clock:** bảo vệ một chiều quan hệ happens-before trong thứ tự logic.
- **Version vector:** giúp nhận diện những cập nhật concurrent trong mô hình phù hợp.
- **Hybrid Logical Clock:** phối hợp thành phần thời gian vật lý và logic.
- **Term/log index:** gắn với leader/consensus log và quyền leadership.

Không có loại timestamp nào tự động tạo transaction hoặc linearizability. Một **total order trên timestamps** chưa chứng minh mọi ACK/read tôn trọng thứ tự thực, đặc biệt khi có failover, pending writes và clocks lệch.

Chọn versioning theo **protocol của hệ và bất biến nghiệp vụ**, không chỉ thêm trường updatedAt rồi coi đó là conflict resolver hoàn chỉnh.

## 37. Quan sát các mô hình sau khi triển khai

| Metric | Câu hỏi |
|---|---|
| Replication lag/log position | Follower bắt kịp đến đâu? |
| Leader elections/term changes | Có failover hoặc thay quyền liên tục? |
| Write ACK latency | Chính sách ghi ảnh hưởng p95/p99 thế nào? |
| Read freshness/version | Response có stale quá hợp đồng? |
| Quorum unavailable/timeouts | Thiếu replica hoặc node chậm ở mức nào? |
| Hints/backlog age | Node thay thế còn giữ bao nhiêu dữ liệu tạm? |
| Repair progress | Anti-entropy có hội tụ không? |
| Concurrent conflicts | Bao nhiêu version cần merge/review? |
| Tombstones/compaction | Xóa và TTL gây chi phí đọc nào? |
| Hot partitions | Một key/partition có hút phần lớn traffic? |
| Business invariant violations | Có double claims, âm tồn, sai ledger? |

Chỉ số **replication lag = 0** không tự nói rằng mọi transaction nhiều key đúng hay mọi payment side effect không bị nhân đôi. Giám sát kỹ thuật phải đi kèm đối soát nghiệp vụ.

## 38. Một bảng quyết định thực tế

| Câu hỏi | Nếu câu trả lời là “có” |
|---|---|
| Cùng một key cần một authority bảo vệ invariant? | Cân nhắc single-writer, CAS hoặc transaction |
| Ghi từ nhiều vùng rất quan trọng, có thể merge an toàn? | Đánh giá multi-leader/local-first |
| Chấp nhận các phiên bản tạm thời lệch và có repair tốt? | Đánh giá leaderless theo sản phẩm |
| Đọc UI được trễ nhưng quyết định phải đúng ngay? | Dùng read model eventual + authoritative conditional write |
| Bắt buộc duy nhất toàn cầu khi WAN mất? | Cần quyền sở hữu/coordination hoặc sửa hợp đồng |
| Một node lỗi có thể khiến mất write đã ACK? | Xem write concern, replication/persistence, failover |
| Số replica lớn nhưng repair chưa có runbook? | Chưa đủ an toàn vận hành |
| Hệ multi-leader có nhiều conflict nghiệp vụ? | Phân ownership/đổi data model hoặc workflow |

Không nên đặt mục tiêu “nhiều replica nhất” hoặc “quorum mạnh nhất” mà không xét p99 latency, khả năng phục vụ, dung lượng, chi phí network và business risk.

## 39. Quy trình chọn và vận hành replication

~~~mermaid
flowchart TD
    A["Liệt kê access patterns và invariants"] --> B["Xác định key, shard, vùng đọc/ghi"]
    B --> C{"Một owner cho cùng key?"}
    C -->|"Có"| D["Leader–follower/single-writer per key"]
    C -->|"Không, merge được"| E["Đánh giá multi-leader hoặc leaderless"]
    D --> F["ACK policy, lag, failover, fencing"]
    E --> G["Conflict policy, version, repair, tombstone"]
    F --> H["Chọn consistency mode cho từng API"]
    G --> H
    H --> I["Đo latency, quorum, durability và chi phí"]
    I --> J["Test failover, partition, conflict, UNKNOWN"]
    J --> K["Monitoring, backup, runbook và reconciliation"]
~~~

Các bước:

1. Viết thao tác read, write, CAS và giao dịch cần hỗ trợ.
2. Xác định phạm vi key/partition và replication factor thực tế.
3. Định nghĩa bất biến không được phá.
4. Chọn vùng có quyền ghi hoặc mô hình conflict resolution.
5. Định nghĩa ACK/durability và hành vi khi mất quorum.
6. Chọn read concern/session guarantee hoặc staleness budget.
7. Thiết kế conditional write và idempotency cho retry.
8. Phân tích election, stale leader, topology change và WAN partition.
9. Với multi-leader, định nghĩa per-field merge/tombstone.
10. Với leaderless, định nghĩa quorum, hints, repair và TTL/GC.
11. Đo p95/p99, timeout/conflict, lag và business invariants.
12. Viết runbook xử lý node offline, repair backlog và reconciliation.

## 40. Những hiểu nhầm thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “Ba replica nghĩa là không bao giờ mất ghi” | ACK/durability/failover khác nhau | Xem write concern và recovery |
| “Follower luôn đọc giá trị mới nhất” | Có replication lag | Chọn read guarantee phù hợp |
| “Đọc primary luôn linearizable” | Failover/epoch/read protocol cần điều kiện | Dựa vào API/consistency mode |
| “Nhiều leader trong cluster nghĩa là multi-leader” | Có thể mỗi shard một leader | Xem cùng logical key |
| “Multi-leader tự merge đúng mọi update” | Có conflict nghiệp vụ | Policy theo field và invariant |
| “LWW chọn write đến sau trong thời gian thực” | Timestamp có thể lệch | Định nghĩa thứ tự phiên bản |
| “Version vector giải quyết conflict” | Chỉ nhận diện causality | Cần merge/resolver |
| “CRDT counter bảo vệ stock không âm” | Concurrent decrements có thể vượt quota | Escrow/conditional write |
| “Leaderless là không có coordinator” | Coordinator vẫn nhận request | Phân biệt vai trò tạm và leader |
| “R+W>N bảo đảm linearizable” | Giao quorum chưa đủ protocol | Xem concurrent/pending writes |
| “Quorum nghĩa là toàn cluster” | RF/tập node theo shard/DC | Nêu quorum scope |
| “Sloppy quorum vẫn luôn giao home quorum” | Node thay thế có thể nằm ngoài tập | Xem actual placement/hints |
| “Read repair sửa được response đã stale” | Repair có thể diễn ra sau response | Đặt bảo đảm trong read protocol |
| “TTL xóa một nơi là xóa toàn hệ” | Replica offline có thể giữ bản cũ | Tombstone và repair |
| “DynamoDB cho chỉnh R/W/N như Dynamo paper” | API service có hợp đồng riêng | Cấu hình theo sản phẩm |
| “Replica thay backup” | Lỗi/xóa được nhân bản | Backup và restore test |
| “Timeout nghĩa là write chưa được áp dụng” | Response có thể mất sau commit | UNKNOWN, verify, idempotency |
| “Mỗi API của một database cùng consistency” | Read mode, cache, transaction khác nhau | Định nghĩa theo operation |

## 41. Bài tập thực hành

### Bài tập 1 — Nhận diện phạm vi N

Một cluster có 12 node, 8 shard, mỗi shard RF=3. Giải thích vì sao N thường là 3 đối với một shard, không phải 12. Nếu mỗi shard có leader riêng, đó có phải multi-leader replication cho cùng key không?

### Bài tập 2 — Timeline follower lag

Client A ghi x=1 vào leader và nhận OK; follower B vẫn còn x=0 trong 2 giây. Dựng timeline và nêu khi nào read 0 phù hợp eventual consistency, khi nào trái một API cam kết linearizable.

### Bài tập 3 — ACK và durability

So sánh ghi ACK tại leader cục bộ với ghi ACK sau majority theo bảo đảm engine. Khi leader chết ngay sau ACK, câu hỏi nào cần hỏi về follower log, bền vững và failover?

### Bài tập 4 — Split-brain

Leader L mất liên lạc với hai follower F1, F2 nhưng vẫn nhận ghi; F1/F2 bầu leader mới. Đề xuất cách dùng term, quorum và fencing để tránh hai phía cùng công nhận ghi mâu thuẫn.

### Bài tập 5 — MongoDB

Viết updateOne có điều kiện đổi PENDING sang RESERVED với writeConcern majority. Phân biệt read preference secondary, read concern majority và read concern linearizable.

### Bài tập 6 — Multi-leader profile

Region A đổi theme=dark, B đổi theme=blue trước khi đồng bộ. Thiết kế ba policies: LWW, giữ siblings cho người dùng chọn, owner region. Mỗi policy có trade-off nào?

### Bài tập 7 — Multi-leader và tiền

Region A ghi PAID, Region B ghi CANCELLED cho cùng order. Giải thích vì sao LWW trên status không thể tự hoàn tiền hoặc phục hồi tồn kho, và đề xuất state machine/compensation.

### Bài tập 8 — Lost update

Điểm tích lũy ban đầu 100, hai vùng độc lập cộng 10 và cộng 20. Vì sao LWW có thể cho 110 hoặc 120 thay vì 130? Đề xuất event ledger hoặc counter CRDT.

### Bài tập 9 — Version vector

So sánh {A:3,B:4} và {A:2,B:5}. Hai bản có quan hệ nhân quả nào? Vector {A:3,B:5} biểu thị điều gì trong mô hình vector clock đơn giản?

### Bài tập 10 — CRDT

A tăng G-counter thêm 3, B tăng thêm 2 từ trạng thái ban đầu. Tính merge theo max từng thành phần và giải thích vì sao CRDT không tự bảo đảm không oversell khi hai vùng được trừ cùng stock.

### Bài tập 11 — Tính quorum

N=5, W=3, R=3. Tính R+W và chỉ ra vì sao quorums giao nhau. Nêu ít nhất ba lý do khiến điều này chưa chứng minh linearizability.

### Bài tập 12 — Sloppy quorum

Home replicas A, B, C; C offline; D nhận hint. Phân tích việc một read hỏi home replicas có thể không thấy dữ liệu D đã nhận, và vai trò hinted handoff.

### Bài tập 13 — Read repair

A có version 8, B có version 7, C có version 6. Mô tả resolver và repair. Nếu version 7 và 8 là concurrent chứ không có quan hệ trước–sau, tại sao không chỉ chọn số lớn?

### Bài tập 14 — Tombstone

Hai replica nhận DELETE, một replica offline còn bản cũ. Điều gì có thể xảy ra nếu tombstone bị dọn quá sớm? Tại sao lịch repair/retention quan trọng?

### Bài tập 15 — Cassandra LOCAL_QUORUM

Hai DC, mỗi DC RF=3. Write ở DC-A dùng LOCAL_QUORUM. Một read sớm ở DC-B có thể thấy gì và cần định nghĩa consistency scope thế nào?

### Bài tập 16 — Cassandra LWT

Hai client muốn claim ghế đang AVAILABLE. So sánh đọc QUORUM rồi update thường với UPDATE ... IF state='AVAILABLE'. Vì sao ordinary quorum không tự biến hai lệnh thành một CAS?

### Bài tập 17 — Redis

Redis primary ACK SET x=1, replica chưa nhận, primary chết. Hãy phân tích cơ chế replication/persistence, nguy cơ mất ghi và vì sao một command nguyên tử không tương đương durability sau failover.

### Bài tập 18 — Phân loại topology

Ba shard mỗi shard có một leader; hai region cùng ghi một profile; và một coordinator bất kỳ fan-out write tới ba replica. Phân loại từng trường hợp và giải thích sự khác nhau.

### Bài tập 19 — Chọn mô hình cho workload

Chọn mô hình cho (a) đặt ghế duy nhất, (b) bộ đếm lượt xem, (c) cài đặt người dùng offline đa thiết bị. Với mỗi mô hình, mô tả ACK, read guarantee, conflict policy và recovery.

### Bài tập 20 — Viết hợp đồng API

Viết contract cho POST /reservations: authority, key, replication, write ACK, conditional predicate, authoritative read, retry/idempotency, unknown outcome, failover và metrics.

### Bài tập 21 — Network partition

Chia cluster N=3 thành nhóm một node và nhóm hai node. So sánh một leader–follower majority commit, một multi-leader cho phép local writes và một leaderless W=2. Nhóm nào có thể ACK, request nào có thể timeout hoặc tạo conflict?

### Bài tập 22 — Runbook repair

Một Cassandra replica offline nhiều ngày trong khi các replica khác nhận DELETE/TTL. Viết runbook xem xét thời gian offline, tombstone retention, anti-entropy/repair, nguy cơ resurrect và khi nào phải escalation.

### Bài tập 23 — Benchmark

Thiết kế benchmark so sánh p95/p99 read/write, error rate, quorum timeouts, replication lag, conflict rate, repair overhead và business invariant violations giữa hai chính sách đọc/ghi.

### Bài tập 24 — Retry khi timeout

Coordinator đã ghi xong nhưng response tới client mất. Client muốn INCR lại counter. Hãy mô tả rủi ro nhân đôi hiệu ứng và thiết kế operationId/idempotency/verification để retry an toàn.

### Bài tập 25 — Unique username toàn cầu

Sản phẩm muốn hai region mất WAN vẫn luôn ACK claim cùng username mà không có coordination và vẫn bảo đảm không trùng toàn cầu. Phân tích vì sao yêu cầu có xung đột trong mô hình partition, rồi đề xuất ít nhất hai cách sửa hợp đồng: một owner, chia namespace/quota, chờ quorum hoặc chấp nhận provisional claim.

---

**Kết luận:** Leader–follower, nhiều leader và mô hình không có leader cố định khác nhau trước hết ở **nơi nhận ghi, cách các bản sao biết thay đổi và cách xử lý khi dữ liệu phân kỳ**. Leader–follower giúp xác định một luồng ghi theo leader nhưng cần bảo vệ **ACK, replication lag, election, fencing và failover**. Multi-leader cho phép nhiều vùng nhận ghi cục bộ nhưng phải giải quyết **conflict, unique constraints, delete/tombstone và business effects**. Leaderless dùng coordinator và replica quorums, song **R+W>N chỉ chứng minh tính giao nhau của tập node trong những giả thiết nhất định**, không tự chứng minh linearizability, durability hay transaction. Hãy lựa chọn từ **bất biến nghiệp vụ và hợp đồng đọc/ghi của API**, sau đó kiểm tra **nguồn thẩm quyền, quorum scope, idempotent retries, repair và khả năng khôi phục** bằng lịch sử thao tác và thử nghiệm lỗi có kiểm soát.
