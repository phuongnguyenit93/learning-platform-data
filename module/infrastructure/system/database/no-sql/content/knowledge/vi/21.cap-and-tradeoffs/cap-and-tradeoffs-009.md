# Cùng một hệ có thể có nhiều chế độ và phạm vi bảo đảm

Khi học về **định lý CAP**, người học thường gặp những nhãn đơn giản như “hệ A thuộc CP”, “hệ B thuộc AP” hoặc “NoSQL đánh đổi consistency để lấy availability”. Những nhãn này giúp bắt đầu thảo luận, nhưng dễ trở thành sai lầm khi dùng để thiết kế sản phẩm thật.

**Cùng một hệ cơ sở dữ liệu NoSQL có thể cung cấp nhiều chế độ nhất quán và nhiều phạm vi bảo đảm khác nhau.** Một thao tác đọc trên leader có thể có semantics khác đọc từ follower; một ghi được ACK bởi một replica khác ghi đợi quorum; một transaction nhiều item có thể khác hẳn một thao tác atomic trên một key; một vùng triển khai (region) có thể tiếp tục nhận ghi khi tách mạng, trong khi một vùng khác từ chối; một index hoặc cache có thể cập nhật bất đồng bộ dù dữ liệu nguồn đã commit.

Thay vì hỏi:

~~~text
“Database này là CP hay AP?”
~~~

câu hỏi có ích hơn là:

~~~text
“Với thao tác O, dữ liệu thuộc phạm vi S, topology T,
cấu hình C, client ở vị trí R và loại lỗi F:
 - các giá trị nào có thể được trả về?
 - write được ACK ở mốc nào?
 - thao tác có còn phục vụ khi partition mạng không?
 - transaction có bao trùm invariant nghiệp vụ không?
 - sau failover/timeout, client phải làm gì?”
~~~

Bài học xây dựng cách tư duy đó từ CAP, các mức consistency và các điểm cấu hình thường gặp, rồi minh họa qua một số họ NoSQL. Cuối bài có ma trận lựa chọn, mẫu hợp đồng, ví dụ Java và bài tập tình huống.

> **Lưu ý:** Những ví dụ MongoDB, Cassandra/ScyllaDB, DynamoDB, Azure Cosmos DB, Redis, etcd và các hệ liên quan chỉ minh họa **những chiều bảo đảm cần hỏi**. Tính năng, tên cấu hình, giới hạn, behavior khi multi-region và API có thể thay đổi theo phiên bản/edition/topology. Không suy ra một cam kết production chỉ từ tên sản phẩm hoặc các bảng tóm tắt trong bài; phải xác minh hợp đồng chính thức của đúng chế độ đang sử dụng.

## 1. Đọc đúng CAP trước khi bàn về chế độ

CAP viết tắt:

- **C — Consistency:** trong cách phát biểu CAP kinh điển, liên quan đến **linearizability/single-copy consistency**, không phải mọi nghĩa của từ consistency.
- **A — Availability:** các request được gửi tới node không lỗi trong mô hình xét đến nhận được một phản hồi hợp lệ, không bị hệ chặn vô hạn chỉ vì cần chờ thành phần khác.
- **P — Partition tolerance:** mô hình cho phép thông điệp giữa các nhóm node bị mất hoặc trì hoãn vô hạn, dù các node trong nhóm vẫn hoạt động.

Khi có **network partition**, một hệ phân tán không thể đồng thời bảo đảm linearizable consistency và availability cho **mọi thao tác liên quan** trong mô hình CAP. Hệ phải có quy tắc để chọn thao tác nào tiếp tục, thao tác nào từ chối/chờ, hoặc chấp nhận mức nhìn dữ liệu yếu hơn.

### 1.1. “Consistency” trong CAP không phải mọi loại consistency

Trong thực tế từ *consistency* xuất hiện ở nhiều nơi:

| Thuật ngữ | Nội dung đang bàn |
|---|---|
| **CAP consistency** | Linearizability đối với các thao tác được xét |
| **Read consistency** | Reader được thấy những phiên bản nào, từ nơi nào |
| **Causal consistency** | Các quan hệ nhân–quả giữa thao tác được bảo toàn |
| **Session guarantees** | Read-your-writes, monotonic reads, monotonic writes... |
| **Transaction isolation** | Transaction đồng thời có thể thấy/ghi state như thế nào |
| **ACID consistency** | Các quy tắc dữ liệu/invariant được giữ qua transaction hợp lệ |
| **Convergence** | Các replica cuối cùng tiến tới cùng trạng thái theo điều kiện |

Một sản phẩm nói “eventually consistent read” có thể áp dụng cho một API đọc cụ thể; điều đó **không đồng nghĩa** mọi write, mọi transaction và mọi index của nó đều có cùng bảo đảm.

### 1.2. “Availability” trong CAP khác SLA uptime

Một cụm đạt 99,99% uptime trong năm không tự chứng minh nó giữ **CAP availability dưới mọi partition**. Uptime thực tế đo khoảng thời gian phục vụ theo SLO và môi trường lỗi; CAP xét một tính chất logic của mô hình phân tán.

Ngược lại, một hệ chọn linearizability và **từ chối một số write** khi mất quorum có thể vẫn có uptime vận hành rất cao khi không xảy ra partition nghiêm trọng.

### 1.3. P không phải một nút chọn tùy ý

Trong mạng thực, không thể loại trừ hoàn toàn thông điệp bị gián đoạn giữa các node. Cấu hình một replica duy nhất hoặc chạy các node gần nhau có thể giảm độ phức tạp, nhưng không xóa bỏ sự tồn tại của lỗi truyền thông giữa các thành phần nếu hệ thực sự phân tán.

Do đó “chọn hai trong ba C, A, P” là cách nhớ dễ gây hiểu nhầm. Điều chính xác hơn: **trong một partition, với thao tác cần giữ linearizability, các thành phần không thể đồng thời tiếp tục chấp nhận mọi yêu cầu một cách độc lập mà không phối hợp**.

### 1.4. Ví dụ ba node bị chia thành hai phía

~~~mermaid
flowchart LR
    subgraph L["Phía mạng 1"]
      A["Replica A"]
      B["Replica B"]
    end
    subgraph R["Phía mạng 2"]
      C["Replica C"]
    end
    A <--> B
    B -.-x C
    A -.-x C
~~~

Giả sử dữ liệu có ba replica A, B, C, phía A–B còn liên lạc, phía C bị tách.

- Nếu ghi cần **quorum 2/3** và protocol bảo đảm leader/quorum đúng, phía A–B có thể tiếp tục phục vụ ghi; phía C thiếu quorum nên có thể từ chối write.
- Nếu cả hai phía vẫn nhận ghi cục bộ, hệ cần quy tắc hòa giải khi kết nối trở lại; linearizable single-copy behavior không thể được tự động bảo đảm chỉ vì sau đó dữ liệu hội tụ.
- Một thao tác đọc cũ ở C có thể vẫn trả kết quả khi ghi mới không được phép, nếu API hỗ trợ chế độ đọc yếu hơn.

**Cùng một cụm** trong tình huống trên có thể **available cho read yếu**, **unavailable cho strong write** ở một phía, và **available cho strong write** ở phía khác. Một nhãn CP/AP cho cả hệ làm mất thông tin quan trọng này.

## 2. Đơn vị áp dụng bảo đảm là gì?

Không nên hỏi “database bảo đảm nhất quán tới đâu?” mà không chỉ rõ **đơn vị dữ liệu** và **API**.

~~~mermaid
flowchart TD
    OP["Một thao tác"] --> KEY["Một key/item/document"]
    KEY --> PART["Một logical partition"]
    PART --> SHARD["Nhiều partition/shard"]
    SHARD --> CLUSTER["Một cluster"]
    CLUSTER --> REGION["Nhiều region"]
    REGION --> SERVICES["Nhiều database/service"]
~~~

Các ranh giới thường gặp:

| Phạm vi | Ví dụ | Câu hỏi thiết kế |
|---|---|---|
| **Một key** | Đổi trạng thái Seat A1 | Atomic conditional write có đủ không? |
| **Một document** | Sửa Order với các dòng hàng nhỏ | Cập nhật document có nguyên tử không? |
| **Một logical partition** | Order và OrderLine cùng partition | Batch transaction có bao trùm hai item không? |
| **Nhiều shard** | Order, Inventory ở các shard khác nhau | Transaction phân tán/coordination ở đâu? |
| **Một cluster** | Quorum read/write | Membership, failover và consistency ra sao? |
| **Nhiều region** | Đặt hàng từ châu Á và châu Âu | Có writer duy nhất hay multi-writer/conflict resolution? |
| **Nhiều service** | Order + Payment gateway | Không có transaction chung thì dùng workflow gì? |

### 2.1. Atomic item không chứng minh atomic nhiều item

Một lệnh cập nhật Inventory item có condition `available >= quantity` có thể nguyên tử theo phạm vi item. Nhưng nếu Order nằm ở item khác, một lần ghi Inventory và một lần tạo Order **không tự tạo all-or-nothing**.

### 2.2. Snapshot read không đồng nghĩa serializable transaction

Một transaction có thể đọc snapshot ổn định nhưng vẫn cho phép **write skew** khi hai transaction cập nhật hai bản ghi khác nhau dựa trên một bất biến chung. Phạm vi isolation và mức isolation phải được đọc riêng.

### 2.3. Các partition có thể có owner khác nhau

Một cluster có hàng nghìn partitions. Một partition mất leader/quorum có thể không phục vụ strong write, trong khi các partition khác vẫn bình thường. Vì thế **availability của cluster** không phải một giá trị boolean cho mọi key tại mọi thời điểm.

### 2.4. Cross-region có thể là lớp replication khác

Một write được commit ở primary region có thể được replicate bất đồng bộ sang secondary region. Một regional transaction đúng không nhất thiết được commit nguyên tử xuyên tất cả region. Đọc ở secondary có thể trả snapshot trễ dù dữ liệu nguồn trong primary đã nhất quán.

## 3. Một hệ có thể có nhiều chế độ theo chiều nào?

Các chiều thường tồn tại đồng thời:

| Chiều cấu hình | Lựa chọn ví dụ | Thay đổi điều gì? |
|---|---|---|
| **Read consistency** | Weak/eventual, session, quorum, strong, linearizable theo API | Phiên bản read được phép trả |
| **Write acknowledgment** | Local, leader, multiple replicas, quorum | Mốc ghi được xác nhận |
| **Durability** | Buffer, journal/fsync, replicated durable | Chịu được loại crash nào |
| **Read location** | Leader, follower, nearest replica | Staleness, latency, routing |
| **Transaction API** | Single-item, conditional, multi-item, partition-local | Atomicity/isolation của nhóm thao tác |
| **Partition scope** | Một partition, nhiều shards | Coordination cần thiết |
| **Region topology** | Single writer, multiple writers, active–passive | Partition behavior và conflict resolution |
| **Session state** | Có/không causal token/bookmark | Khả năng đọc lại write của chính client |
| **Index/read model** | Primary record, secondary index, search cache | Propagation lag/visibility |
| **Failure state** | Bình thường, replica lag, partition, failover | Nhóm API nào tiếp tục phục vụ |

Các chiều có thể **độc lập một phần**, nhưng không phải mọi tổ hợp đều được sản phẩm hỗ trợ. Ví dụ muốn strong read từ một replica bất kỳ trong mọi vùng có thể bị hạn chế; một số transaction yêu cầu read/write concern hoặc cluster mode cụ thể.

### 3.1. Cấu hình mặc định chưa chắc là cấu hình đang được dùng

Một dịch vụ có default read eventual, nhưng client có thể chọn strong read cho một request được hỗ trợ. Một team có thể dùng default SDK mà không biết setting đã được admin thay đổi. Cần ghi cả **server configuration và client request options**.

### 3.2. Thuật ngữ giống nhau nhưng semantics khác nhau

Từ `quorum`, `strong`, `majority`, `snapshot`, `serializable` có thể xuất hiện ở nhiều sản phẩm, nhưng ràng buộc và điều kiện khác nhau. Không thể sao chép một config từ Cassandra sang MongoDB rồi giả định cùng linearizability.

### 3.3. Một endpoint có thể kết hợp nhiều mode

Ví dụ:

~~~text
GET /products
    -> search index eventually updated

GET /inventory/{sku}
    -> strongly consistent source read

POST /reservations
    -> conditional write on authoritative stock

GET /orders/{id}
    -> session read-your-writes

GET /analytics/sales
    -> snapshot of hourly materialized view
~~~

Tất cả có thể thuộc cùng một hệ thống sản phẩm nhưng **không có cùng freshness, isolation hay availability contract**.

## 4. Read consistency: các lựa chọn phổ biến

### 4.1. Eventual consistency

Nếu không có write mới và các điều kiện truyền dữ liệu/khôi phục phù hợp được thỏa, các replica cuối cùng có thể hội tụ về cùng trạng thái. Trong lúc replication lag, một reader có thể thấy phiên bản cũ.

~~~text
T0: Replica A, B: Stock=10
T1: Client updates A: Stock=8
T2: Reader on B: Stock=10 (old)
T3: Replication reaches B
T4: Reader on B: Stock=8
~~~

**Eventual không đồng nghĩa có giới hạn trễ cụ thể**. Muốn tuyên bố “dữ liệu trễ tối đa 2 giây” cần một bảo đảm bounded staleness riêng hoặc SLO đo được, không thể suy từ chữ eventual.

### 4.2. Read-your-writes

Sau khi client A ghi thành công, những lần đọc tiếp theo của **cùng phiên làm việc** phải thấy write đó hoặc phiên bản mới hơn, theo phạm vi session guarantee.

~~~text
A: POST changeAddress -> ACK
A: GET profile -> must see new address (within guaranteed session scope)
B: GET profile -> may still see old address under weaker read mode
~~~

Để đạt guarantee này trong một hệ có replica trễ, có thể cần session token, routing, barrier hoặc chờ replica bắt kịp. Không phải mọi session trong ứng dụng tự động được DB hiểu là causal session.

### 4.3. Monotonic reads

Nếu client đã thấy version 8, lần đọc sau trong cùng phạm vi bảo đảm không được quay lại version 7. Điều này khác với read-your-writes: client có thể đã thấy write của người khác.

### 4.4. Causal consistency

Nếu thao tác B phụ thuộc nhân–quả vào A, người quan sát B theo causal model cần thấy A trong phạm vi được hứa.

~~~text
A: tạo Post P.
B: sau khi đọc P, viết Comment C liên quan P.
C: thấy Comment C nhưng chưa thấy Post P.
~~~

Trạng thái cuối có thể hợp lệ khi hệ eventual, nhưng vi phạm kỳ vọng causal visibility nếu ứng dụng yêu cầu quan hệ P → C. Causal consistency giúp bảo toàn quan hệ nhân–quả, song **không tạo thứ tự toàn phần cho mọi thao tác độc lập**.

### 4.5. Strong/linearizable read

Với linearizability, mỗi thao tác có thể được xem như xảy ra tại một thời điểm tức thời giữa invocation và response, tôn trọng thứ tự real-time của các thao tác hoàn tất. Một read hoàn tất sau khi write đã ACK phải phản ánh write đó hoặc phiên bản mới hơn, trong phạm vi object/operation được bảo đảm.

**Không phải mọi API có tên strong đều đồng nghĩa global linearizability qua mọi partition và region.** Phải xác minh scope và những yêu cầu về write concern/leader/quorum.

### 4.6. Consistent prefix

Một reader có thể nhìn một **tiền tố các write theo thứ tự được cam kết**, thay vì thấy write về sau mà thiếu write trước nó. Đây là một kiểu guarantee khác với read-your-writes hay linearizability.

### 4.7. Bounded staleness

Một chế độ có thể ràng buộc độ trễ theo thời gian hoặc số version/operation dưới điều kiện nhất định. Khi đó phải đọc rõ:

- Bound đo ở phạm vi nào?
- Điều kiện khi replica bị partition là chờ, lỗi hay trả dữ liệu cũ?
- Bound có áp dụng cross-region và mọi API không?
- Giá trị là config tối đa hay chỉ SLO vận hành?

Không dùng thuật ngữ bounded staleness nếu chỉ có monitoring latency trung bình.

## 5. Write acknowledgment khác read consistency

Một write có thể được ACK sau:

~~~text
1. Leader chấp nhận vào RAM.
2. Local log được append.
3. Local log được fsync theo durability policy.
4. Một số replica nhận write.
5. Quorum xác nhận theo protocol của hệ.
6. Replicas áp dụng write vào state machine.
7. Cross-region replicas cũng đã đồng bộ.
~~~

Không phải mọi database thực hiện hoặc công bố đủ các mốc này. Điều quan trọng là **ACK của config hiện tại xác nhận mốc nào**.

### 5.1. ACK nhanh và cửa sổ mất dữ liệu

Nếu ACK khi write mới có ở một leader, mất vĩnh viễn leader trước replication có thể làm các node còn sống thiếu write đó, tùy giao thức. Nếu hệ ACK sau quorum đã ghi bền, khả năng chịu lỗi của một node thường mạnh hơn trong topology phù hợp, nhưng latency và availability có thể thay đổi.

### 5.2. Quorum ACK không thay thế idempotency

Client có thể timeout **sau khi write đã commit**, không biết ACK. Nếu gửi lại `DECREMENT Stock by 2` như một ý định mới, tồn có thể bị trừ hai lần. Cần commandId/reservationId để đối soát hoặc deduplicate.

### 5.3. Một setting có thể ảnh hưởng durability chứ không phải isolation

Chọn journal sync hoặc wait-for-majority có thể tăng bảo đảm về việc write được lưu/replicate trước ACK. Điều đó **không tự biến các transaction snapshot thành serializable** hoặc tạo atomicity qua nhiều item.

### 5.4. Write concern và read concern phải đọc cùng nhau

Để tuyên bố read sau write luôn thấy kết quả mới, cần xem cả **write ACK semantics** lẫn **read consistency/routing**. Tăng write concern mà vẫn đọc một secondary lag trong mode eventual không tự cho read-your-writes.

## 6. Quorum R/W: một mô hình hữu ích nhưng dễ bị hiểu quá

Một mô hình phổ biến cho dữ liệu replicated là:

- \(N\): số replica của một key.
- \(R\): số replica cần tham gia một read.
- \(W\): số replica cần xác nhận một write.

Nếu dùng **tập replica tĩnh giống nhau** và quorum được chọn trên cùng membership:

\[
R + W > N
\]

thì tập replica read và write **bắt buộc giao nhau** về mặt toán học.

Ví dụ \(N=3\):

| R | W | R + W > 3? | Trực giác |
|---:|---:|---|---|
| 1 | 1 | Không | Read có thể trúng replica chưa nhận write |
| 1 | 3 | Có | Nếu write đã tới tất cả, read bất kỳ replica nào cũng giao |
| 2 | 2 | Có | Hai tập quorum 2/3 giao nhau |
| 3 | 1 | Có | Read tất cả giao write |
| 2 | 1 | Không | Read có thể không giao replica nhận write |

### 6.1. Intersection là điều kiện tổ hợp, chưa đủ để có linearizability

Từ \(R+W>N\) **không được kết luận tự động** rằng database cung cấp linearizable reads/writes. Còn phải xét:

- Concurrent writes và quy tắc chọn phiên bản thắng.
- Clock skew khi dùng last-write-wins timestamp.
- Read repair/anti-entropy.
- Replica tạm và hinted handoff.
- Topology/membership thay đổi.
- Split brain, leader/election hoặc conflict resolution.
- Mức durable ACK và recovery.
- Write ordering và cách read phối hợp các response.

Một quorum giao nhau chỉ cho biết **có ít nhất một node thuộc cả hai tập**, không bảo đảm node đó đang chứa giá trị đúng theo một thứ tự linearizable trong mọi execution.

### 6.2. Sloppy quorum làm bài toán phức tạp hơn

Trong một số thiết kế kiểu Dynamo, khi replica ưu tiên không khả dụng, hệ có thể lưu tạm write ở node khác và chuyển lại sau. Nếu read/write quorum được hình thành trên những tập vật lý khác nhau, phép tính \(R+W>N\) theo một preference list tĩnh có thể không còn đủ để suy ra overlap thực.

### 6.3. Quorum theo data center

Một cấu hình local quorum có thể yêu cầu đa số **trong region/data center hiện tại**. Nó không tương đương global quorum trên tất cả regions. Mất kết nối liên vùng có thể khiến hai trung tâm xử lý writes theo những semantics riêng.

### 6.4. Quorum càng lớn không phải luôn tốt hơn

W tăng thường đòi nhiều replica phản hồi hơn trước ACK, làm latency/availability khi lỗi khác đi. R tăng có thể nâng xác suất/khả năng tìm phiên bản mới trong một số protocol nhưng cũng cần thêm response. **Chọn R/W phải dựa vào từng hệ và workload**, không chỉ dùng công thức rồi tối đa hóa mọi tham số.

## 7. Cùng hệ: đường đọc và đường ghi có thể khác nhau

Một dịch vụ bán hàng có các nhu cầu:

~~~text
Product catalog:
    read-heavy, chấp nhận hiển thị giá cũ ngắn hạn

Inventory:
    giữ hàng không được vượt tồn

Order details:
    người dùng vừa sửa địa chỉ muốn đọc lại thấy đúng

Search:
    chịu được index lag trong giới hạn UX

Payments:
    không được thu tiền hai lần do retry
~~~

Các thao tác đó có thể đi qua cùng một product database nhưng yêu cầu khác nhau:

| Endpoint | Read/write path | Bảo đảm cần thiết |
|---|---|---|
| GET /catalog | Replica/index/cache | Eventual phù hợp nếu UX chấp nhận |
| GET /orders/{id} sau sửa | Source/session read | Read-your-writes |
| POST /inventory/reserve | Atomic conditional write | Không oversell trong owner scope |
| POST /orders | Transaction/conditional create | OrderId duy nhất, event intent không mất |
| GET /analytics | Snapshot/materialized view | Mốc dữ liệu rõ, có thể trễ |
| POST /payments/capture | External gateway | Idempotency và reconciliation riêng |

### 7.1. Chế độ đọc yếu không nhất thiết làm ghi yếu

Catalog read từ index eventual có thể hoạt động song song với một atomic reservation write trên source. Không gọi toàn database “eventual” rồi suy rằng tất cả invariants đều chỉ eventual.

### 7.2. Chế độ đọc mạnh cũng không tự làm workflow đúng

Inventory read linearizable rồi ứng dụng thực hiện `if available > 0` và **ghi không điều kiện** ở lệnh thứ hai vẫn có race. Check và write phải được nguyên tử hoặc transaction/isolation bảo vệ.

### 7.3. Search index trễ không chứng minh transaction nguồn hỏng

Một đơn đã commit tại source nhưng tìm kiếm chưa thấy ngay là một vấn đề propagation. Phải kiểm tra source transaction và read model theo **hai hợp đồng riêng**.

## 8. Phạm vi cấu hình: per-request, per-session, per-collection, per-cluster

Cùng một sản phẩm có thể đặt consistency tại những tầng khác nhau:

| Tầng | Điều thường cần xác minh |
|---|---|
| **Per API operation** | Request có tham số strong/consistent read không? |
| **Per session** | Session token hoặc causal context được giữ thế nào? |
| **Per transaction** | Read concern, isolation và write concern có đổi được không? |
| **Per collection/table** | Chỉ một số workload có transaction/index/TTL đặc thù? |
| **Per partition** | Owner/quorum, leader state hoặc hotspot khác nhau? |
| **Per account/cluster** | Default consistency, replication factor, failover policy |
| **Per region** | Read/write routing, single/multi-writer mode, latency |
| **Per index** | Secondary/global index có async propagation không? |
| **Per client/SDK** | Default options, retry, caching hoặc routing |

### 8.1. Không phải mọi setting có thể chọn tự do

Một số dịch vụ cấu hình consistency account-wide; một số cho phép client yêu cầu mức đọc yếu hơn nhưng không mạnh hơn mức account; một số áp dụng transaction isolation cố định. Phải đọc xem setting **tại tầng nào** và **có thể override ở đâu**.

### 8.2. Session token phải được giữ qua các hop

Nếu request đầu chạy qua service A và request sau qua service B, để đạt read-your-writes theo session token, context có thể cần được truyền/giữ ở đường đi phù hợp. Token nằm trong memory một instance nhưng request sau được route sang instance khác có thể làm guarantee không còn hiệu lực nếu không được truyền.

### 8.3. SDK mặc định có thể thay đổi

Một SDK có thể default eventual read, một driver khác default một cấu hình khác hoặc ứng dụng đã override. Phải kiểm tra **request options thực tế trên wire/driver logs**, không chỉ đọc README mặc định của hệ.

## 9. Ví dụ: MongoDB có nhiều cấp bảo đảm

MongoDB minh họa rõ rằng cùng deployment có thể có những lựa chọn khác nhau:

- **Read concern** (ví dụ các chế độ `local`, `majority`, `linearizable`, `snapshot` trong phạm vi được hỗ trợ) quyết định điều kiện nhìn dữ liệu của read/transaction.
- **Write concern** (ví dụ `w:1`, `w:"majority"` và các tùy chọn liên quan journaling trong cấu hình hỗ trợ) quyết định mốc xác nhận write.
- **Read preference** có thể định tuyến read đến primary hoặc secondary, với hệ quả về lag/freshness.
- **Sessions/causal consistency** có thể bảo vệ một số session guarantees theo điều kiện của sản phẩm.
- **Multi-document transactions** có atomicity/isolation riêng, không tự suy từ một `find()` thường.

Các thuật ngữ trên **không thể hoán đổi**.

### 9.1. Majority write và majority read chưa tự là linearizable

Đặt write concern majority có thể nâng cam kết về replication/độ bền so với leader-only ACK. Nhưng đọc `majority` **không mặc nhiên cùng ý nghĩa** với read concern `linearizable`; chúng có contract khác nhau về tính mới nhất và điểm kiểm tra leader.

Muốn tuyên bố “sau write được ACK, mọi read theo thứ tự real-time thấy write”, cần xem chế độ linearizable read, write concern, primary routing và những điều kiện khác trong tài liệu MongoDB.

### 9.2. Snapshot transaction không đồng nghĩa serializable mọi invariant

Một transaction dùng snapshot có thể đọc nhất quán nhiều document, song không được tự cho rằng write skew xuyên hai document khác nhau luôn bị ngăn. Muốn bảo vệ invariant “ít nhất một bác sĩ trực”, cần dùng cơ chế phù hợp như một guard document được cả hai giao dịch cập nhật trong cùng atomic boundary.

### 9.3. Secondary read là một lựa chọn có hệ quả

Một API có thể đọc từ secondary để giảm tải hoặc gần người dùng hơn, nhưng replica lag có thể khiến client thấy dữ liệu cũ. Một route từ primary không tự áp dụng cho mọi endpoint nếu driver có read preference khác.

### 9.4. Causal session có điều kiện

Một session có thể hỗ trợ causal consistency theo read/write concerns và session usage phù hợp. Nếu ứng dụng mở session mới, làm mất token hoặc đọc từ một hệ cache độc lập, không được mặc định cùng read-your-writes guarantee.

### 9.5. Một tình huống thực tế

~~~text
POST /orders/O-100/address:
    write with durability option W
    return version 8

GET /orders/O-100 (route A):
    read primary under strong mode -> may see v8

GET /orders/O-100 (route B):
    read secondary under weaker mode -> may see v7

GET /order-search?q=O-100:
    read async search projection -> may lag further
~~~

Nếu UI hiển thị v7 ngay sau khi cập nhật, vấn đề có thể nằm ở **read mode/routing** chứ không phải một transaction commit sai. Phải tách từng đường API trong quá trình điều tra.

## 10. Ví dụ: Cassandra/ScyllaDB có consistency level theo thao tác

Trong họ Cassandra/ScyllaDB, các **consistency levels** thường cho phép client chọn mức replica acknowledgment cho thao tác đọc/ghi, ví dụ `ONE`, `QUORUM`, `LOCAL_QUORUM`, `ALL` và các tùy chọn khác theo sản phẩm/phiên bản.

### 10.1. Một mô hình ghi theo local quorum

~~~text
Region A:
    Replica A1, A2, A3

Region B:
    Replica B1, B2, B3

Client writes with LOCAL_QUORUM in Region A.
~~~

Write có thể được ACK khi đạt ngưỡng local quorum theo protocol sản phẩm. Điều đó **không đồng nghĩa** toàn bộ replica ở region B đã áp dụng write hoặc read `ONE` tại B lập tức thấy giá trị mới.

### 10.2. ONE và QUORUM có tradeoff khác nhau

- `ONE` có thể giảm số replica cần phản hồi, thuận lợi hơn cho latency/availability của thao tác trong một số lỗi, nhưng có thể đọc cũ/ghi có ít replica giữ trạng thái hơn.
- `QUORUM` yêu cầu nhiều replica tham gia, tăng coordination; trong topology và failure mode phù hợp, có thể giảm cửa sổ đọc cũ.
- `ALL` đòi mọi replica theo định nghĩa level, có thể giảm availability khi một replica không phản hồi.

**Không** kết luận `QUORUM` cung cấp linearizability tổng quát chỉ từ công thức R+W>N. Việc giải quyết phiên bản, hinted handoff, repair, timestamps và loại thao tác đều quan trọng.

### 10.3. Normal write và LWT khác phạm vi

CQL có thể hỗ trợ lightweight transaction qua `IF`/conditional mutation trong phạm vi nhất định. Đây là đường xử lý khác với write bình thường dựa trên timestamp reconciliation.

~~~sql
UPDATE inventory
SET available = 3,
    version = 8
WHERE warehouse_id = 'W-1'
  AND sku = 'SKU-A'
IF version = 7;
~~~

Lệnh có điều kiện cần được đánh giá theo semantics LWT/serial consistency của sản phẩm, không lấy kết quả từ các write `ONE`/`QUORUM` thông thường để suy ra tính nguyên tử của CAS.

### 10.4. `SERIAL` và `LOCAL_SERIAL` thuộc chiều khác

Những tùy chọn serial consistency liên quan pha điều kiện/LWT không có cùng ý nghĩa với CL đọc/ghi thường. Cần hiểu kết hợp các setting theo tài liệu và phạm vi datacenter.

### 10.5. Khác key/partition, khác bất biến

Một LWT trên SKU-A không tự tạo transaction giữa SKU-A và SKU-B hoặc giữa Inventory và Order ở partition khác. “Có LWT” không phải câu trả lời đủ cho transaction cross-partition.

## 11. Ví dụ: DynamoDB phân biệt đường đọc và transaction

DynamoDB thường có lựa chọn **eventually consistent** và **strongly consistent reads** trên những API/tài nguyên hỗ trợ. Một số dạng secondary/global index hoặc đường replication có visibility khác source item; cần xác minh chính xác với dịch vụ, region mode và phiên bản hiện tại.

### 11.1. Hai loại GET không phải cùng contract

~~~text
GET Stock with eventual read:
    may return a stale value under allowed conditions.

GET Stock with supported strong read:
    aims to return current source state according to API contract.
~~~

Nhưng chỉ đọc strongly consistent rồi dùng `if available >= qty` ở application và sau đó ghi **không điều kiện** vẫn có race.

### 11.2. Conditional write mới bảo vệ invariants cục bộ

~~~text
Condition:
    available >= requestedQuantity
Update:
    available = available - requestedQuantity
~~~

Database cần kiểm tra condition và áp dụng update trong cùng thao tác item nguyên tử. Đọc mạnh có thể hữu ích cho UX, nhưng **commit-time predicate** mới là cơ chế chống oversell cho item đó.

### 11.3. Transaction API có ranh giới khác

`TransactWriteItems` và `TransactGetItems` có atomicity/isolation theo phạm vi hỗ trợ, giới hạn action/bytes và error handling riêng. Chúng không tự là một transaction trên Payment gateway hoặc mọi region cùng lúc.

### 11.4. Global replication cần xem chế độ hiện hành

Một DynamoDB table có thể được replicate qua regions với các mode/guarantees phụ thuộc cấu hình và tính năng hiện hành. Không được mặc định tất cả global table deployments cùng một conflict resolution/strong consistency contract. Cần ghi rõ **regional vs cross-region guarantees** của chính deployment.

### 11.5. Ví dụ read/write mismatch

~~~text
POST /reservations:
    conditional write on source item -> RESERVED

GET /inventory via eventual read or lagging index:
    may still display old available value
~~~

Nếu muốn client không thấy tồn cũ sau reserve, API đọc có thể cần mode khác hoặc trả state mới từ successful write response. Nhưng **ngăn oversell** vẫn phải dựa trên conditional write tại owner, không trên dữ liệu UI.

## 12. Ví dụ: Cosmos DB có nhiều consistency choices

Azure Cosmos DB for NoSQL là ví dụ về dịch vụ có nhiều **consistency levels** với những ý nghĩa khác nhau, thường được mô tả như Strong, Bounded Staleness, Session, Consistent Prefix và Eventual trong phạm vi sản phẩm hỗ trợ.

### 12.1. Tên level không đủ để chốt bảo đảm

Với mỗi level, cần đọc:

- Phạm vi account, region, partition và tài nguyên được hỗ trợ.
- Cách client chọn mức được phép theo cấu hình hiện tại.
- Session token có vai trò gì?
- Khi một replica/region không bắt kịp, read sẽ chờ, lỗi hay trả state cũ?
- Các giới hạn/đánh đổi throughput, latency, availability là gì?

### 12.2. Session consistency

Session consistency thường phù hợp UX người dùng sau khi tự sửa dữ liệu. Tuy nhiên muốn bảo vệ read-your-writes, application cần quản lý session token/context theo API, đặc biệt khi request đi qua nhiều service instance.

~~~text
Client edits Profile in Region A.
Write returns session context.
Next GET carries the required context.
System satisfies the documented session guarantee.
~~~

Nếu token bị bỏ qua hoặc query đọc từ một cache riêng, không thể mặc định bảo đảm vẫn còn.

### 12.3. Strong và bounded staleness khác nhau

Strong nhằm kiểm soát tính mới nhất theo phạm vi được hỗ trợ. Bounded staleness cho phép đọc cũ trong **một ranh giới đã định nghĩa**, với tradeoff riêng. Chọn mức mạnh hơn không phải lúc nào cũng cần thiết cho danh sách tin tức hay analytics.

### 12.4. Transactional batch theo partition

Cosmos DB for NoSQL còn có transactional batch/stored procedure trong phạm vi logical partition theo API liên quan. **Consistency level của reads** và **atomicity/isolation của batch** là hai câu hỏi khác nhau; bật strong account consistency không tự mở rộng batch sang mọi partition.

### 12.5. Multi-region routing

Với nhiều region, config single/multi-writer, automatic failover và consistency level có thể phối hợp theo cách riêng. Nếu business yêu cầu global invariant, phải xác minh hỗ trợ cụ thể của mode đang chọn chứ không chỉ dựa vào tên Strong.

## 13. Ví dụ: Redis có nhiều đường đọc/ghi và mốc bền

Redis minh họa sự khác biệt giữa **atomic command trên một primary** với **replica freshness** và **durability của persistence**.

### 13.1. Command nguyên tử trên instance

Các thao tác một command hoặc script phù hợp có thể thực hiện check-and-update atomically trên instance theo semantics Redis.

~~~lua
local key = KEYS[1]
local qty = tonumber(ARGV[1])
local available = tonumber(redis.call("GET", key) or "0")
if qty == nil or qty <= 0 then
    return {err = "INVALID_QTY"}
end
if available < qty then
    return 0
end
redis.call("DECRBY", key, qty)
return 1
~~~

Script trên **chưa idempotent**. Nếu response mất sau khi trừ, client retry có thể trừ lại, dù mỗi script atomic.

### 13.2. Read từ replica có thể cũ

Nếu replica đồng bộ bất đồng bộ, read từ replica có thể trả giá trị trước write. Một read trên primary và read trên replica vì vậy có thể có freshness khác nhau trong cùng hệ.

### 13.3. WAIT không tự là distributed commit

Một số Redis API có thể yêu cầu chờ replication acknowledgement từ replica, nhưng không nên từ đó suy ra mọi write đã được lưu bền ở mọi node hoặc có linearizable multi-node transaction khi failover. Cần xem cụ thể protocol replication, persistence, topology và fault model.

### 13.4. Persistence option ảnh hưởng RPO

RDB snapshot và AOF cùng các chế độ sync có thể tạo tradeoff độ bền/hiệu năng khác nhau. Một command trả thành công trong memory không tự bảo đảm sống sót sau mọi loại power loss. **Atomicity của command** và **durability sau crash** là hai chiều độc lập.

### 13.5. Redis Cluster có ranh giới key-slot

Các thao tác multi-key và script có điều kiện về key slot/topology. Không suy từ một Lua script trên một key rằng transaction có thể nguyên tử trên mọi key ở các shard khác nhau.

## 14. Ví dụ: etcd có nhiều chế độ đọc

Trong những KV store dùng consensus, như etcd, cùng một API đọc có thể có lựa chọn giữa **linearizable** và **serializable reads** theo semantics của sản phẩm.

### 14.1. Linearizable read

Read có thể cần phối hợp để bảo đảm không trả trạng thái trước một write đã hoàn tất theo thứ tự real-time. Khi mất quorum, node bị cô lập có thể không hoàn thành được loại read này.

### 14.2. Serializable read

Trong cách dùng thuật ngữ của etcd, một serializable read có thể được phục vụ ở local member và **có thể stale** so với trạng thái mới nhất; tên này **không được nhầm** với “serializable transaction isolation” trong lý thuyết ACID.

Đây là ví dụ đặc biệt quan trọng: **cùng từ serializable có thể xuất hiện trong những ngữ cảnh khác nhau**. Phải đọc định nghĩa API, không suy ý nghĩa từ tên gọi.

### 14.3. Một cluster, hai availability modes

Trong partition, một follower mất liên lạc có thể vẫn trả serializable local read theo contract, nhưng không thể bảo đảm linearizable read nếu cần quorum/leader coordination. Đây là cùng sản phẩm, cùng key, nhưng **mức consistency và availability thay đổi theo API option**.

### 14.4. Dùng đúng trường hợp

Leader election, configuration authority hoặc lock state thường đòi freshness/ordering mạnh. Dashboard chỉ muốn hiển thị trạng thái gần đây có thể chấp nhận read cũ. Không dùng stale read để quyết định mình có quyền sở hữu lease/leadership nếu hợp đồng yêu cầu linearizable authority.

## 15. Không được ép các sản phẩm vào một bảng “CP/AP” bất biến

Một bảng có ích hơn:

| Sản phẩm/họ | Những điểm có thể chọn/kiểm tra | Tránh suy luận |
|---|---|---|
| MongoDB | Read concern, write concern, read preference, session, transaction | Majority read = linearizable read cho mọi đường |
| Cassandra/ScyllaDB | Per-operation consistency levels, local/global scope, LWT | R+W>N tự chứng minh linearizability |
| DynamoDB | Eventual/strong read ở API được hỗ trợ, conditional write, transactions, global replication mode | Strong source read áp dụng cho mọi index và region |
| Cosmos DB | Account/client consistency, session tokens, transactional batch scope, region topology | Strong read level = cross-partition ACID transaction |
| Redis | Primary/replica read, atomic script, WATCH, persistence, replication wait | Atomic script = durable global transaction |
| etcd/consensus KV | Linearizable vs local/stale reads, quorum/leader state | Tên “serializable read” có nghĩa transaction isolation |

### 15.1. Một hệ có thể “CP cho một thao tác” và “AP-like cho thao tác khác”

Trong một partition, một hệ có thể từ chối strong write trên phía không có quorum, nhưng vẫn trả stale read local. Nói chính xác hơn là:

~~~text
Strong write under partition:
    prioritize consistency; may be unavailable.

Local stale read under partition:
    may remain available; weaker freshness guarantee.
~~~

Không cần gắn một nhãn vĩnh viễn cho toàn hệ.

### 15.2. Không phải mọi lựa chọn thuộc CAP thuần túy

Một transaction snapshot và transaction serializable có thể khác **anomalies của concurrent reads/writes**, ngay cả khi không có partition mạng. Một write concern local và majority có thể khác **durability/failover**. CAP không thay thế việc nghiên cứu các tradeoff đó.

## 16. PACELC: sự đánh đổi vẫn tồn tại khi mạng khỏe

CAP tập trung vào lựa chọn khi **partition** xảy ra. Trong vận hành bình thường, hệ vẫn đánh đổi latency, coordination và tính mới nhất.

**PACELC** là một khung suy nghĩ bổ sung:

~~~text
If Partition (P):
    trade Availability (A) vs Consistency (C).

Else (E), while network is healthy:
    trade Latency (L) vs Consistency (C).
~~~

Không phải mọi hệ buộc phải có hai lựa chọn hoàn toàn tách biệt, nhưng mô hình này nhắc rằng **đồng bộ thêm replica/region thường có chi phí độ trễ** kể cả khi mạng không bị partition.

### 16.1. Ví dụ đọc gần người dùng

Người dùng ở khu vực A muốn đọc Catalog từ replica gần nhất, latency thấp và có thể chấp nhận trễ. Nhưng trạng thái Reservation phải lấy từ nguồn có thẩm quyền hoặc có condition tại commit, dù round-trip cao hơn.

### 16.2. Ví dụ ghi chờ cross-region

Ghi đợi xác nhận từ một khu vực địa lý xa có thể tăng latency do tốc độ ánh sáng và network variability. Chọn write local rồi replicate async có thể giảm latency, nhưng rủi ro mất write/ghi xung đột khi failover thay đổi. Phải gắn lựa chọn với RPO và invariants.

### 16.3. Latency là phân phối, không phải một con số

Khi so sánh mode, cần đo:

- p50, p95, p99 read latency.
- p50, p95, p99 write/commit latency.
- Timeout rate và retry count.
- Quorum wait/failover time.
- Replica/index lag.

Chọn mode chỉ theo average latency có thể bỏ qua tail latency quan trọng của checkout.

## 17. Một thao tác có thể khác trạng thái khi lỗi

Giả sử một cluster replicated, bình thường cả ba node liên lạc:

~~~text
Normal state:
    strong read -> success
    quorum write -> success
    local stale read -> success
~~~

Khi tách mạng:

~~~text
Majority side:
    quorum write may continue
    strong read may continue

Minority side:
    quorum write may be rejected / unavailable
    linearizable read may be rejected / unavailable
    local stale read may still return a value
~~~

Đây là **mô hình minh họa**, không phải cam kết sản phẩm nào cũng có read ở minority. Có hệ chặn mọi request khi node mất role, có hệ trả lỗi ở mode khác, có hệ tự động chuyển leader hoặc chờ quorum.

### 17.1. Chỉ “có response” chưa đủ để gọi available

Trả HTTP 503 không tương đương trả kết quả thành công được định nghĩa cho thao tác. Với CAP availability, phải xem response hợp lệ trong model, không tính một từ chối bất kỳ là “vẫn available”.

### 17.2. Đọc cũ phải được biểu thị rõ nếu nguy hiểm

Nếu API cho stale read và hiển thị “Số hàng còn 10”, client có thể hiểu đó là nguồn có thẩm quyền. Với dashboard, nên có `asOf` hoặc độ trễ chỉ báo. Với quyết định ghi, phải có commit-time condition.

### 17.3. Failover là một pha riêng

Sau khi mạng hồi phục, hệ có thể phải election leader, catch up log, reconcile conflicts hoặc repair replicas. Một API hoạt động ngay trong partition chưa chứng minh state cuối đúng; phải kiểm thử **sau convergence/failover**.

## 18. Một case study: Inventory và Catalog trong cùng ứng dụng

Hệ thương mại điện tử có các dữ liệu:

~~~text
Product:
    id, title, description, priceDisplay

Inventory:
    warehouseId, sku, available, reserved, version

Reservation:
    reservationId, orderId, sku, quantity, status

Order:
    orderId, status, total, version

OrderSearch:
    denormalized read model
~~~

### 18.1. Catalog có thể dùng đọc eventual

Product title/description có thể cache, replicate hoặc index bất đồng bộ. Nếu trang hiển thị mô tả cũ một thời gian, người dùng có thể chấp nhận. Cần xác định SLO và cơ chế invalidation, không mặc định “eventual” luôn được phép trễ bao lâu cũng được.

### 18.2. Reservation phải có invariant mạnh

Nhu cầu:

~~~text
Never reserve more items than available.
~~~

Một atomic conditional update:

~~~text
Condition: available >= requestedQuantity
Mutation: available -= requestedQuantity
~~~

có thể bảo vệ invariant tại một Inventory owner nếu theo API đúng. Nếu reservationId nằm ở item khác, cần transaction hoặc idempotent reservation workflow để không trừ hàng mà mất record reservation.

### 18.3. Người dùng cần read-your-writes sau chỉnh Order

Sau khi sửa địa chỉ, UI phải thấy bản mới. Có thể dùng session read, source read mode mạnh hoặc trả version mới từ response và đợi projection phù hợp. Không vì Catalog eventual mà áp cùng read mode cho Order details.

### 18.4. Search là projection, không là nguồn phê duyệt

Một search index thấy “còn hàng” có thể không cập nhật kịp. Không dùng nó làm điều kiện cuối cùng cho checkout. Ghi phải kiểm tra tại Inventory owner.

### 18.5. Payment là workflow riêng

Database transaction của Order không tự bao gồm cổng thanh toán. Cần `paymentId`, idempotency key, trạng thái `PENDING/CONFIRMED/FAILED`, outbox và reconciliation để chống retry thu tiền hai lần.

### 18.6. Tổng hợp các mode

| Luồng | Nguồn/đường truy cập | Contract chủ yếu |
|---|---|---|
| Xem Catalog | Cache/search/replica | Eventual, lag SLO |
| Xem chi tiết Order vừa sửa | Session/source read | Read-your-writes |
| Giữ tồn | Inventory owner | Atomic conditional update |
| Ghi Order + Outbox | Supported transaction scope | Atomicity/durability |
| Tìm kiếm Order | Async projection | Eventual + ordering/dedupe |
| Thanh toán | Gateway + Payment ledger | Idempotency + reconciliation |

Đây chính là ý nghĩa thiết kế của câu **“cùng một hệ có thể có nhiều chế độ và phạm vi bảo đảm”**: quyết định ở cấp **operation và invariant**, không ở cấp logo sản phẩm.

## 19. Case study: phân vùng mạng giữa hai region

Giả sử một ứng dụng bán cùng SKU ở Region A và Region B, mỗi nơi có local replica.

~~~text
Global available stock = 10.

Region A:
    sees available=10
    wants reserve 8

Region B:
    sees available=10
    wants reserve 8

Network partition prevents regions from coordinating.
~~~

Nếu cả hai region vẫn tự chấp nhận reserve 8 dựa trên bản sao local:

~~~text
Total accepted reservations = 16 > 10.
~~~

Khi reconnect, **last-write-wins** chọn một giá trị counter có thể làm một phần reservation biến mất khỏi state cuối, nhưng khách ở hai region đã được thông báo thành công. Eventual convergence **không đồng nghĩa** invariant đã từng được giữ.

### 19.1. Single writer authority

Chọn một region làm nguồn quyết định Inventory. Region còn lại có thể hiển thị catalog và cache nhưng khi reserve phải gọi source owner. Trong partition, region không liên lạc được có thể phải **từ chối hoặc xếp hàng request reserve**, ưu tiên consistency của invariant.

### 19.2. Escrow/quota phân bổ trước

Có thể phân 10 đơn vị thành quota:

~~~text
Region A quota = 6.
Region B quota = 4.
Total quota = 10.
~~~

Mỗi region chỉ được giữ hàng trong quota của mình bằng atomic local logic. Trong partition, A không được lấy quota B nếu không coordination. Cách này có thể giữ một số write availability và invariant toàn cục, đổi lại có nguy cơ region A hết quota trong khi B còn dư.

### 19.3. Điều kiện của escrow

- Cấp quota không vượt tổng tồn.
- Chuyển quota giữa regions phải có protocol an toàn.
- Retry một reservation dùng stable reservationId.
- Nếu region chết, quota còn lại phải có quy trình thu hồi không double-spend.
- Theo dõi outstanding reservations và expired holds.

Không chia counter thành random shards rồi kỳ vọng invariant tổng tự đúng.

### 19.4. Hàng chờ trong partition không phải đã commit

Một region có thể **accept request vào queue** và trả `PENDING`, nhưng không được báo `RESERVED` nếu chưa có nguồn có thẩm quyền xác nhận. Đây là cách giữ UX/availability ở mức **tiếp nhận ý định**, không phải bảo đảm write nghiệp vụ đã commit.

## 20. API contract phải nói rõ trạng thái và consistency

Ví dụ một API giữ hàng:

~~~http
POST /reservations HTTP/1.1
Content-Type: application/json
Idempotency-Key: reserve-9001

{"sku":"SKU-A","quantity":2}
~~~

Các phản hồi có thể là:

~~~text
201 RESERVED
    đã ghi reservation theo durable/invariant contract.

202 PENDING
    đã tiếp nhận yêu cầu, chưa xác nhận giữ hàng.

409 INSUFFICIENT_STOCK
    condition không thỏa tại nguồn có thẩm quyền.

409 CONFLICT
    version/transaction conflict theo API contract.

503 AUTHORITY_UNAVAILABLE
    không thể xác minh/commit mạnh trong trạng thái lỗi.

UNKNOWN_OUTCOME
    client timeout, cần query commandId trước khi retry.
~~~

Các mã HTTP và status là **gợi ý thiết kế**, không phải mapping bắt buộc cho mọi sản phẩm.

### 20.1. Không gọi PENDING là thành công nghiệp vụ

Trả HTTP 202 có thể là thành công ở bước **tiếp nhận**, nhưng chưa được coi hàng đã giữ. UI phải trình bày đúng trạng thái thay vì giả tạo availability.

### 20.2. Có thể trả version/session token

Một response:

~~~json
{
  "orderId": "O-100",
  "status": "CONFIRMED",
  "version": 8,
  "readConsistency": "source-verified"
}
~~~

Giá trị `readConsistency` ở đây chỉ minh họa cách công bố contract. Không phát minh token cụ thể hoặc claim mạnh hơn DB. Nếu dùng vendor session token/ETag phải bảo vệ không lộ thông tin nhạy cảm và truyền đúng semantics.

### 20.3. Hợp đồng cho API read

~~~text
GET /orders/O-100:
    consistency = session/read-your-writes (if supported)
    source = Order aggregate
    may wait/retry if replica does not meet session token

GET /catalog:
    consistency = eventual
    readModelLagSLO = monitored
~~~

Điều này giúp frontend không hiểu nhầm một GET từ search index là dữ liệu giao dịch mới nhất.

## 21. Cùng một request có thể đi qua nhiều lớp consistency

Một flow:

~~~mermaid
flowchart LR
    USER["User"] --> API["API Gateway"]
    API --> CACHE["Cache (eventual)"]
    API --> SRC["Order source (stronger write/read)"]
    SRC --> OUTBOX["Outbox"]
    OUTBOX --> BUS["Broker"]
    BUS --> SEARCH["Search projection (eventual)"]
~~~

### 21.1. Cache consistency là tầng khác

Database source có thể linearizable trên một item, nhưng cache TTL 60 giây vẫn trả dữ liệu cũ. Khi đánh giá experience, phải tính cả cache invalidation, session stickiness, CDN và read model.

### 21.2. Database transaction không làm message delivery exactly once

Order và Outbox có thể commit atomically; publisher gửi event có thể trùng khi ACK message bị mất. Consumer cần idempotency theo `eventId` hoặc version.

### 21.3. Transaction mạnh ở source không bảo vệ External API

Một callback transaction không nên gọi payment gateway và giả định charge được rollback nếu DB abort. Dùng saga và payment idempotency.

### 21.4. Một user journey có nhiều điểm ACK

~~~text
HTTP ACK for command accepted
DB commit ACK
Outbox event committed
Broker publish ACK
Consumer projection applied
Cache invalidation completed
~~~

Mỗi mốc có thể tới khác thời điểm. Cần quyết định user được xem thao tác là hoàn tất ở **mốc nào**.

## 22. Consistency contract nên gắn với failure model

Một bảng quyết định:

| Operation | Điều kiện bình thường | Khi mất quorum | Khi replica lag | Khi region outage |
|---|---|---|---|---|
| Strong item read | Read theo contract | Có thể fail/chờ | Không được trả stale nếu mode cấm | Phụ thuộc failover/region mode |
| Eventual catalog read | Có thể trả cache | Có thể vẫn phục vụ cache | Có thể stale | Cache có thể tiếp tục, data age tăng |
| Quorum write | ACK sau quorum theo protocol | Không thể ACK khi thiếu quorum | Một số replica còn trễ | Phụ thuộc topology |
| Conditional inventory write | Kiểm tra tại owner | Có thể từ chối để giữ invariant | Không dùng stale read để quyết định | Chọn authority/escrow |
| Async projection read | Đọc index | Có thể trả dữ liệu cũ | Tùy lag | Tùy replica của projection |

Bảng này chỉ mô tả những hướng khả dĩ; **không dùng làm hợp đồng sản phẩm cụ thể**. Với mỗi deployment, phải điền expected outcomes từ tài liệu và test.

### 22.1. Fault model có cấp độ

- Client mất network nhưng server/cluster vẫn khỏe.
- Một replica process crash.
- Một host mất điện.
- Mất leader và phải election.
- Partition giữa đa số và thiểu số.
- Partition giữa datacenters.
- Mất cả region.
- Storage corruption hoặc mất node vĩnh viễn.

Một mode có thể giữ guarantee dưới lỗi thứ nhất nhưng không dưới lỗi cuối. Không gộp mọi trường hợp thành “khi cluster lỗi”.

### 22.2. ACK có thể bị mất dù commit đã thành công

Client timeout không kết luận write đã rollback. Cần query bằng commandId hoặc dùng idempotent protocol để tránh duplicate khi retry.

### 22.3. Hệ có thể chọn degrade có kiểm soát

Ví dụ API tìm kiếm vẫn trả cached result có nhãn staleness, trong khi API thanh toán từ chối confirm cho tới khi khôi phục quorum. Đây có thể là thiết kế **đúng**, không phải dấu hiệu hệ mâu thuẫn về CAP.

## 23. Phân biệt consistency với transaction isolation

Một hệ có thể có:

~~~text
Read:
    strong / linearizable on one item

Transaction:
    snapshot isolation on multiple items
~~~

Điều này không mâu thuẫn. Strong item read liên quan freshness/real-time ordering của một thao tác; SI liên quan **một snapshot và sự tương tác của các transaction đồng thời**.

### 23.1. Write skew dưới snapshot isolation

Hai bác sĩ đang trực:

~~~text
Doctor A: onCall=true
Doctor B: onCall=true

T1 reads A and B at snapshot S.
T2 reads A and B at snapshot S.

T1 updates Doctor A=false.
T2 updates Doctor B=false.

Both commits may succeed under SI without shared write conflict.
Final: no doctor on call.
~~~

Hệ có thể có SI đúng nhưng invariant bị phá. Cần một guard record, atomic aggregate hoặc serializable transaction đúng scope.

### 23.2. Linearizable single-key write không tự là global transaction

Mỗi Account được cập nhật linearizable riêng:

~~~text
deduct 50 from A
add 50 to B
~~~

Nếu hai thao tác không chung transaction, crash giữa hai lệnh vẫn có thể để transfer dang dở. Consistency trên từng key không thay thế atomicity của toàn transfer.

### 23.3. “Serializable read” có thể là tên API khác

Như ví dụ etcd, từ `serializable` trong một tùy chọn read có thể nghĩa đọc local có khả năng stale, không phải serializable isolation của giao dịch. Luôn đọc định nghĩa cụ thể.

### 23.4. Durability là chiều riêng

Một transaction có serializable isolation nhưng ACK trước fsync theo cấu hình yếu có thể không sống sót qua mất điện. Isolation mạnh không tự làm write durable.

## 24. Ma trận ra quyết định cho một tính năng

Một team nên điền ma trận theo từng **invariant và API**:

| Câu hỏi | Ví dụ trả lời | Cách xác minh |
|---|---|---|
| Invariant là gì? | Không giữ vượt tồn SKU | Domain spec + test |
| Nguồn có thẩm quyền? | Inventory item tại owner | Data model/routing |
| Phạm vi bảo vệ? | Một SKU/warehouse | Partition key + docs |
| Operation? | Conditional update | SDK/API |
| Read mode cho UX? | Eventual catalog, session Order | Request options |
| Write ACK yêu cầu? | Durable theo fault model đã chọn | Write concern + test |
| Khi mất quorum? | Reservation trả PENDING/503 | Partition test |
| Region mode? | Single writer hoặc escrow | Deployment topology |
| Retry thế nào? | Stable reservationId, bounded retry | Failure injection |
| Derived index? | Async, lag SLO | Metrics |
| Test nào chứng minh? | Concurrent reserve, failover, stale read | Test report |

### 24.1. Viết contract thành tài liệu có thể review

~~~yaml
feature: reserve-inventory
invariant: "total committed reservations never exceed available authority"
owner: "Inventory aggregate"
keyScope: "(warehouseId, sku)"

database:
  product: "<product>"
  version: "<version / service mode>"
  topology: "<replicas, shards, regions>"
  api: "<specific conditional write API>"

consistency:
  readModeForDecision: "<source or atomic predicate>"
  readModeForDisplay: "<eventual/session/strong as supported>"
  writeAck: "<exact configured durability/replication contract>"
  transactionScope: "<key/partition/cluster>"
  multiRegionGuarantee: "<documented behavior>"

partitionBehavior:
  majoritySide: "<expected>"
  minoritySide: "<expected>"
  degradedRead: "<allowed or forbidden>"
  pendingCommands: "<how accepted and reconciled>"

recovery:
  stableCommandId: true
  unknownCommitProcedure: "<query/reconcile>"
  idempotencyWindow: "<business policy>"

evidence:
  docsVersion: "<link/date>"
  configSnapshot: "<safe config reference>"
  testReport: "<run ID>"
~~~

Các giá trị placeholder không phải kết luận. Điền bằng thông tin được tài liệu hóa và đo trên topology phù hợp.

### 24.2. Đừng bỏ bước ghi trường hợp không hỗ trợ

Một hồ sơ tốt có mục:

~~~text
NOT GUARANTEED:
    - read on secondary is not current under this mode
    - transactional batch does not span unrelated partitions
    - global strong write is not provided by current configuration
    - broker consumer may process an event more than once
~~~

Biết **điều gì không được bảo đảm** giúp tránh những assumption nguy hiểm hơn một bảng toàn dấu tick.

## 25. Java: tách read mode khỏi business invariant

Một abstraction có thể làm rõ rằng một giá trị hiển thị cho người dùng không đồng nghĩa một giá trị an toàn để ra quyết định.

~~~java
public enum ReadMode {
    EVENTUAL_FOR_DISPLAY,
    SESSION_READ_YOUR_WRITES,
    AUTHORITATIVE_FOR_DECISION
}

public record StockView(
    String sku,
    int displayedAvailable,
    String source,
    String consistencyDescription
) {}

public record ReserveCommand(
    String commandId,
    String sku,
    int quantity
) {}

public enum ReserveOutcome {
    RESERVED,
    INSUFFICIENT_STOCK,
    PENDING,
    UNKNOWN_COMMIT
}

public interface InventoryGateway {
    StockView readStock(String sku, ReadMode mode);

    // Implementation phải dùng conditional write nguyên tử
    // trong phạm vi có thẩm quyền, không dựa vào StockView cũ.
    ReserveOutcome reserveIfAvailable(ReserveCommand command);
}
~~~

Đây là **interface minh họa**, không phải Java SDK của sản phẩm nào. Tên `AUTHORITATIVE_FOR_DECISION` là **yêu cầu nghiệp vụ**; implementation phải map tới một API đủ mạnh hoặc từ chối nếu DB không hỗ trợ, chứ không tự tuyên bố mọi source read là linearizable.

### 25.1. Ví dụ service

~~~java
public final class CheckoutService {
    private final InventoryGateway inventory;

    public CheckoutService(InventoryGateway inventory) {
        this.inventory = inventory;
    }

    public ReserveOutcome reserve(ReserveCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        // Không đọc eventual StockView rồi tính/ghi không điều kiện.
        return inventory.reserveIfAvailable(command);
    }
}
~~~

Một cách **sai**:

~~~java
StockView display = gateway.readStock(
    "SKU-A", ReadMode.EVENTUAL_FOR_DISPLAY
);
if (display.displayedAvailable() >= 2) {
    gateway.decrementWithoutCondition("SKU-A", 2);
}
~~~

Hai client có thể cùng thấy stock cũ và cùng giảm vượt tồn. Chuyển read sang strong mode thôi chưa đủ nếu **check và write tách rời**, vì hai thao tác vẫn có race.

### 25.2. Bảo vệ unknown commit

Nếu `reserveIfAvailable()` timeout sau khi commit, adapter không được tự trả `INSUFFICIENT_STOCK` hoặc tạo một reservation mới. Nó phải giữ `commandId` và có cách đối soát trạng thái của cùng command.

### 25.3. Mở rộng adapter theo capability, không theo tên sản phẩm

Có thể định nghĩa capability như `supportsStrongReadOnPrimaryItem`, `supportsCrossPartitionTransactions`, `supportsSessionTokens`. Nhưng các capability phải gắn **API/topology/version**, không phải field boolean `isCPDatabase`.

## 26. Kiểm thử các chế độ trong cùng một hệ

Thay vì một test:

~~~text
write K=V1
read K -> V1
PASS: database strongly consistent
~~~

hãy có **ma trận kiểm thử**:

| Test | Read/write mode | Fault | Điều cần quan sát |
|---|---|---|---|
| Read after acknowledged write | Strong source read | Bình thường | Giá trị mới theo contract |
| Read after write | Eventual replica read | Replication lag | Có thể cũ, phải hội tụ theo điều kiện |
| Session read-your-writes | Session token/read option | Route sang node khác | Có giữ session guarantee không? |
| Quorum write | Chế độ quorum | Một replica lỗi | ACK/timeout theo protocol |
| Strong write in minority | Strong/quorum | Partition 2–1 | Từ chối/chờ, không split-brain commit |
| Local stale read in minority | Weak/local read | Partition 2–1 | Có thể trả state cũ nếu API cho phép |
| Atomic conditional reserve | Conditional write | Hai writer cùng SKU | Không oversell |
| Multi-item transaction | Transaction API | Crash giữa thao tác | Không partial commit trong scope |
| Cross-partition negative | API chỉ hỗ trợ same partition | Khác partition | Từ chối hoặc không được tuyên bố atomic |
| Multi-region writers | Mode region thực tế | Cross-region partition | Kiểm tra conflict/invariant sau convergence |
| Search projection | Async pipeline | Consumer lag | Không dùng search như nguồn có thẩm quyền |
| Timeout at commit | Durable write | Mất ACK | Idempotency/reconciliation |

### 26.1. Kiểm thử staleness có kiểm soát

Tạo một write v2 ở source, làm chậm replication tới replica test, rồi đọc ở mode eventual và strong được hỗ trợ. Ghi rõ read chọn node nào và source commit ở thời điểm nào. Một lần eventual read trả v2 không chứng minh nó **luôn** trả mới; phải kiểm tra trường hợp lag.

### 26.2. Kiểm thử partition ở các phía

Trong cluster test:

~~~text
Before partition:
    all nodes connected.

Inject partition:
    A/B separated from C.

On A/B:
    attempt strong read/write and weak read.

On C:
    attempt strong read/write and weak read.

Heal partition:
    verify convergence and authoritative state.
~~~

Expected outcomes phải lấy từ **contract mode cụ thể**. Không mặc định mọi hệ consensus/leaderless có hành vi giống nhau.

### 26.3. Kiểm thử failover và ACK

Ghi các commandId, đánh dấu lệnh nào đã nhận successful ACK ở chế độ durability đang xét, rồi làm lỗi leader theo fault model được hỗ trợ. Sau recovery, đối soát các command đã ACK và những lệnh `UNKNOWN`. Không chỉ so số record tổng.

### 26.4. Kiểm thử transaction scope

Hai item trong cùng partition có thể commit all-or-none theo transactional batch; hai item khác partition có thể bị API từ chối. Đây là **negative control** quan trọng để team không lỡ mở rộng lời hứa của một API.

### 26.5. Kiểm thử replica lag không phải kiểm thử isolation

Reader thấy Order mới và Search index cũ có thể là projection lag. Muốn kiểm thử transaction isolation, dùng read API trong đúng transactional scope và kiểm tra lịch concurrent reads/writes. Không lẫn hai bài test.

## 27. Java JUnit: kiểm tra invariant dưới concurrent writes

Một integration-test adapter trừu tượng:

~~~java
public interface InventoryTestAdapter {
    void reset(String sku, int available);

    // Implement bằng API conditional write thực trên NoSQL đích.
    ReserveOutcome reserve(
        String commandId,
        String sku,
        int quantity
    );

    int authoritativeAvailable(String sku);
    int committedReservationQuantity(String sku);
}
~~~

Một skeleton JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class InventoryConsistencyContractTest {
    private final InventoryTestAdapter adapter =
        TestEnvironment.inventoryAdapter();

    @Test
    void concurrentReservationsDoNotOversell() throws Exception {
        String sku = "SKU-CAP-TEST";
        adapter.reset(sku, 5);

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch begin = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Callable<ReserveOutcome> a = () -> {
            ready.countDown();
            begin.await();
            return adapter.reserve("command-A", sku, 4);
        };

        Callable<ReserveOutcome> b = () -> {
            ready.countDown();
            begin.await();
            return adapter.reserve("command-B", sku, 3);
        };

        try {
            Future<ReserveOutcome> fa = pool.submit(a);
            Future<ReserveOutcome> fb = pool.submit(b);

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            begin.countDown();

            ReserveOutcome ra = fa.get(15, TimeUnit.SECONDS);
            ReserveOutcome rb = fb.get(15, TimeUnit.SECONDS);

            // UNKNOWN must be reconciled by commandId first.
            assertNotEquals(ReserveOutcome.UNKNOWN_COMMIT, ra);
            assertNotEquals(ReserveOutcome.UNKNOWN_COMMIT, rb);

            int committed = adapter.committedReservationQuantity(sku);
            int remaining = adapter.authoritativeAvailable(sku);
            assertTrue(committed <= 5);
            assertEquals(5, committed + remaining);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

`TestEnvironment` là fixture giả định do nhóm tự xây. Bài test chỉ có ý nghĩa khi adapter thật sự kết nối **cấu hình, region và API cần kiểm tra**.

### 27.1. Barrier không bảo đảm mọi thao tác cùng đọc một state

Các thread bắt đầu gần nhau nhưng network/scheduler có thể khiến request chạy lần lượt. Khi cần tái hiện race có chủ đích, dùng test hook sau bước đọc hoặc proxy/fault injector được môi trường hỗ trợ, đồng thời thu transaction history.

### 27.2. Test mode mạnh và yếu khác nhau

Test invariant reservation sử dụng **atomic conditional write**, không nên đổi sang eventual read chỉ để cố làm nó fail. Nếu muốn kiểm thử eventual read, đặt expected là có thể stale và kiểm tra policy hiển thị/tái đồng bộ, chứ không đánh giá eventual mode theo một lời hứa linearizable mà nó không đưa ra.

### 27.3. Không chạy chaos test phá hủy trên production

Partition, kill leader, lỗi disk hoặc full-disk chỉ thực hiện trong môi trường được cấp quyền và có dữ liệu test, observability, cleanup và tiêu chí dừng. Không gây rủi ro cho dữ liệu thật chỉ để trình diễn CAP.

## 28. Observability: một hệ, nhiều đường consistency

| Metric | Giúp trả lời |
|---|---|
| Read latency theo mode/route | Strong read chậm hơn local read bao nhiêu? |
| Replica lag theo region/partition | Eventual reads có thể cũ tới đâu? |
| Session token wait/failure | Read-your-writes có đạt không? |
| Write ACK latency theo concern | Sync/quorum ảnh hưởng p99 thế nào? |
| Unavailable strong operations | Khi partition/quorum mất, những API nào fail? |
| Conditional failures | Bao nhiêu business predicate không đạt? |
| CAS/transaction conflict rate | Hot key hay isolation contention |
| Unknown commit outcomes | Có cần reconciliation backlog không? |
| Leader election/failover duration | Authority không sẵn sàng bao lâu? |
| Cross-region replication backlog | Mức RPO/lag thực tế |
| Search/CDC projection lag | Read model chậm so với source |
| Invariant violations | Oversell, duplicate key, negative balance |

### 28.1. Phải phân nhóm theo mode và topology

Trung bình `GET latency = 10ms` không cho biết strong read p99 ở remote region là bao nhiêu. Metric nên có nhãn như `operation`, `consistencyMode`, `region`, `readSource`, `replicaRole`, `partitionGroup` theo cách không làm nổ cardinality.

### 28.2. Đo availability của đúng thao tác

Theo dõi:

~~~text
StrongReadSuccessRate
QuorumWriteSuccessRate
EventualReadSuccessRate
ReservationCommitRate
PendingCommandBacklog
~~~

Không báo một con số “database availability” rồi che việc Reservation không thể commit trong khi Catalog vẫn phục vụ từ cache.

### 28.3. SLO dựa trên invariant và trải nghiệm

Ví dụ:

~~~text
Catalog:
    stale data age monitored; search latency SLO.

Inventory:
    zero known oversell invariant violation.
    reserve API correctness prioritized over accepting unverified writes.

Order details:
    read-your-writes in session under supported topology.

Analytics:
    freshness asOf timestamp explicit.
~~~

SLO nên phản ánh **điều người dùng cần**, không chỉ những metric database dễ xuất.

## 29. Những ngộ nhận phổ biến

### “Database CP thì mọi thao tác luôn mạnh và sẽ không phục vụ khi partition”

Không. Hệ có thể có weak/local reads, async projections và strong writes với behavior khác nhau.

### “Database AP thì không bao giờ có giao dịch nguyên tử”

Không đúng. Một hệ có thể tiếp tục trả stale read khi partition nhưng vẫn có atomic conditional operations trong phạm vi cục bộ được hỗ trợ.

### “CAP consistency là ACID consistency”

Không. CAP nói về linearizability; ACID C nói về invariant/constraint qua transaction.

### “Quorum là đồng nghĩa linearizability”

Không. \(R+W>N\) chỉ bảo đảm giao nhau dưới giả định phù hợp; còn concurrency, membership, timestamps và reconciliation.

### “Read strongly consistent rồi ghi sau luôn tránh oversell”

Không. Check và write tách rời có race. Cần atomic predicate/transaction.

### “Write majority nghĩa là mọi read replica lập tức có dữ liệu”

Không tự động. Read routing và replica lag vẫn quan trọng.

### “Strong trên một item nghĩa là serializable nhiều item”

Không. Cần transaction đủ phạm vi và isolation.

### “Snapshot isolation không có anomaly nào”

Không. Write skew có thể xảy ra với các record không giao write set.

### “Consistency level giống nhau trên mọi region”

Không chắc. Có level local, global, session và topology restrictions.

### “Một global table luôn có cùng cross-region contract bất kể mode”

Không được mặc định. Phải xem multi-region replication/conflict mode hiện hành.

### “Eventual nghĩa là chắc chắn đồng bộ trong một số giây cố định”

Không. Muốn bound phải có guarantee hoặc SLO được định nghĩa và đo.

### “Atomic script của Redis là durable distributed transaction”

Không. Atomicity, replication và persistence là các chiều riêng.

### “Có read-your-writes session thì mọi người dùng cũng thấy write”

Không. Session guarantee có phạm vi riêng.

### “HTTP 202 PENDING nghĩa là reservation đã giữ được”

Không. Tiếp nhận ý định khác committed business action.

### “CAP chỉ xuất hiện khi mất một node”

Partition mạng có thể xảy ra khi node còn hoạt động; lost/delayed messages mới là yếu tố cốt lõi.

### “Không có partition thì không có đánh đổi”

Vẫn có latency, throughput, transaction contention, durability và chi phí phối hợp; PACELC nhấn mạnh điều đó.

### “Process kill chứng minh được power-loss durability”

Không. OS page cache và storage stack có thể vẫn hoạt động sau process kill.

### “Sản phẩm hứa Strong tức cache/search bên ngoài cũng Strong”

Không. Projection và cache có hợp đồng riêng.

### “Cứ bật mode mạnh nhất ở mọi endpoint là kiến trúc tốt”

Không nhất thiết. Có thể làm tăng latency/chi phí hoặc giảm availability không cần thiết; phải gắn lựa chọn với invariant và UX.

### “Một lần test không gặp stale read là đủ”

Không. Replication lag, partition và failover phải được mô phỏng hoặc quan sát đúng fault model.

## 30. Quy trình chọn consistency mode và phạm vi bảo đảm

1. **Liệt kê nghiệp vụ và invariant.** Dữ liệu nào được phép cũ, dữ liệu nào phải đúng tại commit?
2. **Xác định nguồn có thẩm quyền.** Đừng dùng cache/index để phê duyệt nghiệp vụ nếu chúng là projection.
3. **Vẽ ranh giới key/partition/shard/region/service.** Chỉ ra dữ liệu liên quan mỗi invariant.
4. **Liệt kê API cụ thể.** Read, write, conditional update, transaction, batch, search, stream.
5. **Đọc consistency của từng API.** Eventual, session, causal, strong, linearizable theo scope.
6. **Đọc write ACK và durability.** Local log, fsync, quorum, regional replication.
7. **Đọc isolation và atomicity.** Một key, nhiều item, partition và các anomalies còn có thể xảy ra.
8. **Đọc topology/region mode.** Single writer, multi-writer, quorum membership, failover.
9. **Xác định hành vi khi partition.** Strong operation có fail/chờ? Weak read có stale? Có pending queue?
10. **Thiết kế retry/idempotency.** Stable commandId, known abort vs unknown commit.
11. **Đặt SLA/SLO cho từng đường.** Tail latency, staleness, write success, pending backlog.
12. **Thử concurrency và fault injection.** Không chỉ kiểm tra happy path.
13. **Ghi những điều không được bảo đảm.** Không suy rộng từ một config sang mọi API.
14. **Theo dõi drift.** SDK default, deployment/region và feature version thay đổi có thể đổi contract.

### 30.1. Mẫu quyết định ngắn

~~~text
Feature: Inventory reservation
Invariant: no oversell in authoritative source
Primary owner: Stock item by (warehouseId, sku)
Decision API: atomic conditional update
Read UI mode: eventual allowed with staleness label
Read after own write: source/session as needed
Transaction scope: verify if reservation record separate
Write ACK: documented durability/replication option
Region mode: single-writer or preallocated quotas
Partition handling: strong commit may be unavailable
Unknown commit: reconcile using reservationId
Metrics: oversell audit, p99, replica lag, pending commands
Negative guarantee: search/catalog cache not source of stock truth
~~~

## 31. Bài tập thực hành

### Bài 1 — CAP đúng phạm vi

Cluster ba node A, B, C có network partition A–B và C. Hệ dùng quorum 2/3 để commit linearizable write. Mô tả thao tác nào có thể tiếp tục trên A–B và C, và vì sao một local stale read trên C có thể có availability khác strong write.

### Bài 2 — Consistency trong CAP và ACID

Giải thích vì sao một hệ có linearizable write một item nhưng vẫn có thể không bảo vệ transfer giữa hai account. Phân biệt CAP consistency, transaction atomicity/isolation và durability.

### Bài 3 — Quorum toán học

Với N=5, tính giao nhau của các cặp (R=1,W=4), (R=2,W=3), (R=3,W=3), (R=4,W=2). Sau đó giải thích vì sao overlap không đủ chứng minh linearizability khi có concurrent writes hoặc sloppy quorum.

### Bài 4 — Read-your-writes

Một client cập nhật Profile v7 thành v8 rồi đọc qua replica khác thấy v7. Thiết kế session token/routing hoặc source read theo capability của sản phẩm để đạt read-your-writes, và nêu điều gì xảy ra khi token bị mất giữa hai service instances.

### Bài 5 — MongoDB

So sánh read concern majority, linearizable, snapshot; write concern majority; read preference secondary. Chọn những câu hỏi phải tra documentation trước khi khẳng định một GET sau POST luôn thấy data mới.

### Bài 6 — Cassandra

Một cluster có hai datacenter, mỗi datacenter ba replica. So sánh một write LOCAL_QUORUM ở DC1 với read ONE ở DC2. Nêu nguy cơ stale read và vì sao LWT là một chiều khác với CL của write thường.

### Bài 7 — DynamoDB

Một API GET từ source table, một API search qua global secondary index, và một API reserve dùng conditional update. Viết consistency contract riêng cho từng endpoint; không lấy eventual index làm nguồn kiểm tra stock.

### Bài 8 — Cosmos DB

Thiết kế Profile UX dùng session consistency; chỉ ra yêu cầu bảo toàn session token. So sánh với một service cần Strong hoặc Bounded Staleness theo điều kiện sản phẩm hỗ trợ và nêu tradeoff.

### Bài 9 — Redis

Một Lua script giảm Stock chạy atomically trên primary; client đọc từ replica trễ rồi cho rằng script không hoạt động. Phân tích hai lớp bảo đảm và mô tả cách test khác nhau cho atomicity, read freshness và durability.

### Bài 10 — etcd

Giải thích tại sao “serializable read” ở một API của etcd không được đồng nghĩa với “serializable transaction isolation”. Trong minority partition, read mode nào có thể stale và mode nào có thể cần quorum?

### Bài 11 — Multi-region oversell

Hai region đều thấy stock 10 và đồng thời nhận reserve 8. Nếu cả hai chấp nhận write cục bộ, phân tích kết quả sau replication. Thiết kế single-writer hoặc escrow quotas với tổng quota không vượt 10.

### Bài 12 — API PENDING và RESERVED

Khi mất authority quorum, hệ vẫn nhận yêu cầu đặt vé vào durable queue. Hãy thiết kế response khác nhau cho `PENDING` và `RESERVED`, idempotency key và reconciliation sau khi quorum phục hồi.

### Bài 13 — Write skew

Hai bác sĩ cùng trực. Nếu transaction đọc snapshot rồi ghi hai doctor records khác nhau, cả hai có thể cho mình nghỉ và làm count bằng 0. Hãy đề xuất guard record hoặc serializable isolation đúng phạm vi.

### Bài 14 — Failure-injection matrix

Thiết kế ma trận test cho eventual read, session read, strong read và quorum write dưới các lỗi: replica lag, process kill, majority/minority partition, leader failover và cross-region outage. Ghi expected theo contract, không đoán.

### Bài 15 — PACELC

Catalog cần p99 thấp và chấp nhận lag, còn Inventory cần đúng khi reserve. Mô tả lựa chọn consistency/latency khi bình thường và behavior khi partition xảy ra, gồm các SLO phù hợp.

### Bài 16 — Review một câu khẳng định

Một tài liệu viết “Chúng ta dùng NoSQL CP nên mọi query strong, index không lag, transaction nhiều region luôn serializable và mọi write đã durable ở tất cả node.” Hãy liệt kê các thiếu sót về operation scope, index visibility, transaction boundary, durability, region topology và fault model.

### Bài 17 — Phân biệt retry với consistency

Client gửi command ReserveStock đã được commit nhưng ACK mất; sau đó retry lệnh giảm stock với request ID khác. Dù DB linearizable ở một key, có thể xảy ra lỗi gì? Thiết kế stable commandId/idempotency.

### Bài 18 — Thiết kế hỗn hợp

Một ứng dụng có Product, Cart, Order, Inventory, Payment và Search. Lập bảng cho từng aggregate: nguồn có thẩm quyền, read mode, write mode, transaction scope, behavior khi partition, staleness SLO và cách đối soát.

---

**Kết luận:** Định lý CAP không phải nhãn dán cố định lên tên một sản phẩm NoSQL. Trong cùng một hệ, **read mode, write acknowledgment, transaction isolation, atomicity, durability, read routing, partition scope, region topology và trạng thái lỗi** có thể tạo ra những bảo đảm hoàn toàn khác nhau. Một thao tác strong write có thể phải từ chối khi mất quorum trong khi một read eventual vẫn phục vụ được; một item có thể được cập nhật nguyên tử nhưng nhiều item không thuộc cùng transaction; một nguồn dữ liệu có thể đã commit trong khi search index hoặc replica còn trễ. Vì vậy, cách thiết kế đúng là **mô tả bảo đảm theo từng thao tác và bất biến, chỉ rõ phạm vi/điều kiện áp dụng, xác minh failure model, đo latency và kiểm thử cạnh tranh**, thay vì trả lời câu hỏi “database này CP hay AP?” bằng một chữ duy nhất.
