# Đọc hợp đồng giao dịch của sản phẩm và kiểm thử đúng phạm vi

Trong các hệ NoSQL, câu hỏi **“database này có transaction không?”** thường dẫn đến câu trả lời quá đơn giản. Một hệ có thể cho phép cập nhật nguyên tử một document, transaction nhiều item cùng logical partition, transaction qua nhiều shard trong một cluster hoặc một biến thể giao dịch với điều kiện khác. Một hệ khác có thể hỗ trợ conditional write mạnh, nhưng batch gửi nhiều câu lệnh lại không có các bảo đảm isolation mà ứng dụng kỳ vọng.

Nếu chỉ đọc dòng quảng bá “ACID transactions supported” rồi triển khai chức năng chuyển tiền, giữ hàng, xác nhận đơn hoặc đổi quyền truy cập, hệ thống có thể gặp lỗi khi nhiều writer tranh chấp, khi replica đọc trễ, khi commit timeout, hoặc khi triển khai sang nhiều region.

Kỹ năng quan trọng là **đọc hợp đồng giao dịch (transaction contract)** dưới dạng những phát biểu có thể kiểm chứng, và **kiểm thử đúng ranh giới bảo đảm** thay vì thử một giao dịch happy path rồi tuyên bố an toàn.

Bài này đi theo một quy trình:

1. Xác định **bất biến nghiệp vụ** và failure model cần bảo vệ.
2. Đọc tài liệu sản phẩm để làm rõ **đơn vị nguyên tử, isolation, durability, phạm vi phân vùng/region và các giới hạn**.
3. Biến mỗi cam kết thành **assertion và kịch bản kiểm thử**.
4. Chạy thử **cạnh tranh, timeout, crash, failover, replica lag và retry** trong môi trường có topology tương đương triển khai thật.
5. Ghi lại bằng chứng, ngoại lệ và **quyết định kiến trúc**: dùng transaction, atomic conditional write, thay đổi aggregate, saga hay outbox.

> **Giới hạn của bài:** Các sản phẩm MongoDB, DynamoDB, Firestore, Cosmos DB, Cassandra/ScyllaDB, Redis và một số hệ transactional key–value được dùng làm ví dụ về những câu hỏi cần hỏi. Tính năng, quota, error code, chế độ đồng bộ và giới hạn số lượng có thể khác theo phiên bản, SDK, edition, region hoặc topology. Bài không khẳng định một thông số cố định là đúng cho tất cả bản phát hành; hãy đối chiếu tài liệu và cấu hình đang chạy.

## 1. “Hợp đồng giao dịch” là gì?

Hợp đồng giao dịch không chỉ là chữ ký của một API `beginTransaction()` hay một bảng liệt kê các thuộc tính ACID. Nó là tập hợp các **bảo đảm có điều kiện** mà application được phép dựa vào khi thực hiện thao tác đọc/ghi.

Ví dụ một phát biểu chưa đủ:

> Hệ thống hỗ trợ atomic transaction.

Những câu hỏi còn thiếu:

- Atomicity áp dụng cho **một item, nhiều item cùng partition, nhiều shard hay tất cả database**?
- Những item được chọn có thể thuộc **nhiều collection/table/container** không?
- Có được **đọc rồi ghi trên cùng một snapshot** trong transaction không?
- Trong lúc hai transaction chạy đồng thời, engine bảo vệ **lost update, write skew, phantom, uniqueness** đến mức nào?
- **Commit ACK** nghĩa là log đã được lưu bền ở đâu: leader, replica, quorum hay memory?
- Có support **multi-region writer**, hoặc commit chỉ có nghĩa trong một region?
- Khi **timeout tại commit**, giao dịch có thể đã commit không?
- Driver **có tự chạy lại transaction callback** không?
- Có giới hạn về **số item, thời gian, bytes, partition, index, loại thao tác và contention** không?
- Khi phiên bản sản phẩm hoặc cấu hình thay đổi, hợp đồng có thay đổi theo không?

Một hợp đồng tốt phải trả lời những câu hỏi đó bằng phát biểu có phạm vi và có thể trích dẫn tài liệu sản phẩm nội bộ của nhóm.

### 1.1. Biến khẩu hiệu thành điều kiện

Phát biểu không thể kiểm chứng:

~~~text
Database hỗ trợ transaction mạnh.
~~~

Phát biểu có thể kiểm chứng:

~~~text
Trong deployment D, phiên bản V và cấu hình C:
  - API TransactionWrite bảo đảm atomicity cho tập item S
    nếu chúng thỏa ràng buộc partition/topology của sản phẩm.
  - Khi một điều kiện ghi thất bại, toàn bộ transaction S
    không được commit.
  - Sau successful commit acknowledgement với durability option W,
    hệ giữ kết quả trong fault model F.
  - Những read dùng chế độ R quan sát kết quả theo consistency K.
  - SDK có thể retry callback, nên callback không chứa
    side effect ngoài database.
~~~

Những ký hiệu V, C, S, W, F, R và K phải được điền bằng thông tin thật. Nếu chưa có bằng chứng, đánh dấu **chưa xác nhận**, không tự điền từ kinh nghiệm về sản phẩm khác.

### 1.2. Hợp đồng có nhiều lớp

~~~mermaid
flowchart TD
    B["Bất biến nghiệp vụ"] --> API["Hợp đồng API / SDK"]
    API --> ENG["Storage engine transaction semantics"]
    ENG --> DIST["Partition / replication / consensus"]
    DIST --> CFG["Topology, version, durability config"]
    CFG --> FAULT["Fault model và kiểm thử"]
    FAULT --> EVID["Bằng chứng triển khai"]
~~~

Một lệnh được gọi là `transaction()` ở SDK chỉ là điểm bắt đầu. Nếu callback có retry tự động, nếu transaction bị giới hạn một partition, hoặc nếu ACK không đảm bảo dữ liệu sống sót sau mất node theo yêu cầu, **hợp đồng ứng dụng** phải phản ánh những điều đó.

## 2. Bắt đầu bằng bất biến, không bắt đầu bằng tính năng database

**Bất biến (invariant)** là điều phải đúng tại những ranh giới nghiệp vụ đã xác định.

Ví dụ:

| Nghiệp vụ | Bất biến | Đơn vị dữ liệu liên quan |
|---|---|---|
| Giữ hàng | Tổng lượng được cấp không vượt tồn có thẩm quyền | Inventory và Reservation |
| Chuyển tiền | Không tự tạo hoặc làm mất giá trị trong một transfer đã settle | Account/ledger/transfer |
| Tạo username | Một canonical username thuộc tối đa một tài khoản trong phạm vi cho phép | Username registry |
| Xác nhận Order | Không chuyển từ CANCELED sang CONFIRMED bởi event cũ | Order state/version |
| Ghi Order + Outbox | Một OrderConfirmed đã commit phải có ý định phát event bền | Order và Outbox |
| Cập nhật nhiều dòng trong một Order | Total khớp snapshot của các line item khi commit | Order aggregate |

**Không phải mọi bất biến đều cần transaction nhiều record.** Một điều kiện `available >= quantity` và phép trừ trong **một item có thẩm quyền** có thể bảo vệ tồn kho. Ngược lại, nếu tổng tiền được chia qua nhiều account độc lập, chỉ CAS từng account có thể không bảo vệ toàn bộ transfer.

### 2.1. Mô tả trạng thái nào được phép quan sát

Đừng chỉ viết “không sai dữ liệu”. Hãy nêu:

~~~text
Trước transaction:
    A.balance = 200
    B.balance = 100

Transfer 50:
    Trạng thái commit hợp lệ: A=150, B=150
    Trạng thái rollback hợp lệ: A=200, B=100

Không hợp lệ sau transaction:
    A=150, B=100
    A=200, B=150
~~~

Cũng cần hỏi: **một reader đang chạy đồng thời được phép thấy trạng thái nào?** Một transaction atomic ở commit chưa đủ trả lời về tất cả read consistency, snapshot, secondary index hay replica lag.

### 2.2. Phân biệt invariant tại commit và tiến độ cuối cùng

Trong saga qua nhiều service, có thể chấp nhận Order tạm ở `PAYMENT_PENDING`, miễn workflow không hiển thị là `CONFIRMED` khi tiền chưa được xác nhận. Đây là bất biến theo **state machine**. Nếu nhóm yêu cầu mọi trạng thái trung gian đều vô hình, saga có thể không đáp ứng; cần chọn transaction đúng phạm vi hoặc đổi mô hình nghiệp vụ.

### 2.3. Viết fault model trước khi test

Mỗi mức độ bền cần gắn với lỗi cụ thể:

- Một request timeout.
- Process crash.
- Host reboot đột ngột.
- Disk error hoặc mất node vĩnh viễn.
- Network partition giữa các node.
- Replica chậm và leader failover.
- Sự cố một availability zone.
- Sự cố vùng triển khai (region).

Một test kill process **không tự chứng minh** dữ liệu chịu được mất điện hoặc mất toàn bộ region.

## 3. Bản đồ phạm vi: item → partition → cluster → region → service

Một nhà cung cấp có thể dùng chữ “transaction” cho một phạm vi nhỏ hơn ứng dụng cần.

~~~mermaid
flowchart TD
    ONE["Một item / document"] --> PART["Nhiều item cùng logical partition"]
    PART --> SHARD["Nhiều partition / shard trong cluster"]
    SHARD --> REG["Nhiều region"]
    REG --> SYS["Nhiều database hoặc external service"]
~~~

Không suy rằng **hỗ trợ phạm vi trên** mặc nhiên hỗ trợ tất cả phạm vi dưới.

### 3.1. Một item/document

Một document Order có thể chứa các line item bounded và total, được cập nhật atomically theo version. Khi đó không cần mở một transaction nhiều document chỉ để sửa dữ liệu thuộc cùng aggregate.

### 3.2. Logical partition

Một số hệ document phân vùng cung cấp transaction chỉ trong **một logical partition key**. Hai item có cùng tenantId chưa chắc đã cùng logical partition nếu partition key thực tế còn chứa orderId. Ngược lại, nhồi mọi dữ liệu tenant vào một partition để “có transaction” có thể tạo hotspot và giới hạn kích thước.

### 3.3. Nhiều partition/shard

Giao dịch phải phối hợp nhiều chủ sở hữu dữ liệu. Cần kiểm tra engine có hỗ trợ không, với commit protocol nào, mức isolation nào và giới hạn time/size ra sao.

### 3.4. Nhiều region

Một transaction tại region A không mặc nhiên chống hai writer đồng thời ghi cùng entity tại region B. Nếu multi-region dùng reconciliation/last-write-wins, một invariant có thể bị vi phạm dù từng request cục bộ đều được ACK.

### 3.5. Nhiều service

Database transaction không tự rollback email đã gửi, charge ở payment gateway hay object upload. Nếu không có giao thức distributed commit thực sự với những participant đó, phải dùng **idempotent workflow, saga, outbox và đối soát**.

## 4. Bảng đọc tài liệu sản phẩm: tìm thông tin gì?

Khi tra tài liệu chính thức, nên ghi lại **đường dẫn trang, phiên bản, ngày xem, SDK, cấu hình và câu/đoạn làm bằng chứng** trong hồ sơ thiết kế. Không chỉ chụp một đoạn marketing.

| Nhóm | Cần tìm trong tài liệu | Câu hỏi cụ thể |
|---|---|---|
| **API** | Transaction, batch, conditional write | API nào thực sự cho atomic commit? |
| **Phạm vi dữ liệu** | Partition, collection, table, key restrictions | Các record của tính năng có cùng phạm vi hỗ trợ? |
| **Topology** | Standalone, replica set, sharded, serverless | Môi trường production có đáp ứng điều kiện? |
| **Atomicity** | Commit/rollback/error semantics | Một thao tác fail thì cả nhóm ra sao? |
| **Isolation** | Snapshot/serializable/conflict rules | Writer và reader thấy những anomaly nào? |
| **Visibility** | Read concern/read consistency | Sau commit, reader nào thấy state mới? |
| **Durability** | Write concern, fsync, majority/quorum | ACK sống sót qua lỗi node/host nào? |
| **Commit outcome** | Timeout, unknown commit, retry commit | Client xác định transaction đã commit bằng cách nào? |
| **SDK** | Callback retry, session/transaction object | Callback có bị thực hiện lại không? |
| **Giới hạn** | Count, bytes, runtime, query/index rules | Giao dịch có fit cùng headroom không? |
| **Replica/region** | Replication mode, conflict resolution | Có phải transaction xuyên region hay chỉ cục bộ? |
| **Chi phí** | Capacity, billing, latency, contention | P99 và throughput có phù hợp SLO? |
| **Quan sát** | Metrics, logs, error codes | Khi vi phạm contract làm sao phát hiện? |

### 4.1. Từ khóa nên tra cứu

Không phải mọi trang liên quan nằm dưới heading “Transactions”. Các từ khóa thường hữu ích:

~~~text
atomicity
transaction isolation
snapshot isolation
serializable
conditional write / compare-and-set
transaction scope
logical partition key
write concern / durability
read concern / strong consistency
transaction conflict
commit retry / unknown commit result
transaction size and time limits
batch semantics
global table / multi-region conflict
SDK transaction callback retry
failover and recovery
~~~

### 4.2. Đọc điều kiện của phát biểu

Ví dụ nhà cung cấp viết:

~~~text
Transaction X is atomic within a logical partition.
~~~

Từ quan trọng là **within**. Hãy ánh xạ mọi item của lệnh vào partition key thật. Nếu một item nằm ngoài ranh giới đó, không được áp dụng kết luận atomicity của X cho toàn workflow.

Ví dụ khác:

~~~text
Committed reads are strongly consistent under option R.
~~~

Cần xác định **option R có được bật ở mọi đường đọc, secondary index và replica không**. Nếu một endpoint UI đọc từ cache/search projection, cam kết của DB primary có thể không áp dụng.

### 4.3. Đọc ngoại lệ trước ví dụ code

Những câu thường quan trọng hơn code sample:

- Không hỗ trợ cross-partition hoặc cross-region transaction.
- Một số lệnh không được dùng trong transaction.
- Có deadline/lifetime tối đa.
- Callback có thể được thử lại sau xung đột.
- Một số query/index có consistency khác nguồn.
- Certain topology/SDK/edition không hỗ trợ tính năng.
- Commit có thể có kết quả không rõ khi mất kết nối.

Đừng bỏ qua một chú thích vì ví dụ “chạy thành công trên máy dev”.

## 5. Điền hồ sơ hợp đồng cho một workload

Hồ sơ nên là một artifact kỹ thuật dễ cập nhật cùng code và deployment configuration.

~~~yaml
workload: checkout-order-with-stock
invariants:
  - "no oversell for one inventory authority"
  - "committed order has durable outbox intent"

deployment:
  product: "<product and service mode>"
  version: "<exact engine/API/SDK versions>"
  topology: "<standalone / replicated / sharded / regional>"
  regionMode: "<single writer / multi writer>"

transaction:
  api: "<named API>"
  scope: "<exact set of supported records>"
  isolation: "<documented level and caveats>"
  readConsistency: "<read path and mode>"
  durability: "<write concern / sync or quorum setting>"
  commitAcknowledgment: "<what ACK confirms>"
  maxItems: "<from product docs for this version>"
  maxBytes: "<from product docs for this version>"
  maxDuration: "<from product docs for this version>"
  unsupportedOperations: "<list>"
  callbackRetry: "<yes/no/conditions>"
  unknownCommitProcedure: "<documented recovery route>"

evidence:
  documentationLinks: ["<versioned product links>"]
  configSnapshot: "<saved deployment config reference>"
  testReport: "<run ID / environment / result>"
  owner: "<team>"
  reviewedAt: "<date>"
~~~

Đây là **mẫu minh họa** với giá trị placeholder; không sao chép các chuỗi này vào production như một hợp đồng đã được xác minh.

### 5.1. Phân biệt “được tài liệu hứa”, “được test thấy” và “được suy luận”

| Cột hồ sơ | Ý nghĩa |
|---|---|
| Documented guarantee | Hứa hẹn có điều kiện của nhà cung cấp |
| Configuration evidence | Thông tin triển khai chứng tỏ điều kiện đang bật |
| Observed behavior | Điều bài test đã thấy trong fault model cụ thể |
| Assumption | Điều nhóm đang giả định nhưng chưa có bằng chứng |
| Gap | Điều cần làm rõ hoặc không được phép dựa vào |

Một test chạy 1.000 lần không chứng minh tuyệt đối một thuộc tính phân tán. Test cho **bằng chứng quan sát và phát hiện phản ví dụ**; contract và cơ chế hệ thống vẫn phải được đọc cùng nhau.

## 6. ACID cần được chuyển thành testable assertions

### 6.1. Atomicity

Assertion:

~~~text
Với transaction gồm update A và update B,
trong mọi kết quả commit/abort hợp lệ của API:
    hoặc cả A, B ở trạng thái sau transaction,
    hoặc không cái nào có thay đổi của transaction.
~~~

**Test:** chèn lỗi/abort tại các bước được hỗ trợ; sau khi outcome xác định, đọc từ nguồn có thẩm quyền và đối chiếu cặp giá trị.

**Không được kết luận:** test atomicity hai item cũng chứng minh mọi read replica hoặc external email nhìn thấy trạng thái đồng thời.

### 6.2. Consistency theo invariant nghiệp vụ

Assertion:

~~~text
Available(stock) >= 0
Tổng reservation thành công <= lượng có thẩm quyền
Một canonical username được gán tối đa một account
~~~

**Test:** chạy cạnh tranh, kiểm tra kết quả cuối và kiểm tra mọi successful command. Nếu một mutation đúng nhưng business invariant sai, có thể contract DB vẫn đúng; lỗi nằm ở phạm vi transaction hoặc cách ứng dụng thực thi predicate.

### 6.3. Isolation

Assertion phụ thuộc mode cụ thể:

~~~text
Trong isolation mode M:
    - dirty read có được cho phép không?
    - snapshot của một transaction có ổn định không?
    - write skew có thể xảy ra không?
    - phantom/predicate write có được bảo vệ không?
~~~

**Test:** xây lịch thực thi (history) cụ thể, dùng barrier để ép hai transaction đọc cùng trạng thái, rồi cho commit cạnh tranh.

### 6.4. Durability

Assertion:

~~~text
Sau ACK thành công với setting W,
mọi thay đổi đã commit phải còn sau loại lỗi F
theo bảo đảm đã công bố.
~~~

**Test:** ghi có command ID và ACK trace; chủ động tạo crash/failover trong môi trường kiểm thử thích hợp, rồi phục hồi và đối soát. Cần phân biệt process kill, host power loss, mất node vĩnh viễn và mất region.

## 7. Isolation không thể rút gọn về một chữ “transaction”

Các anomaly phổ biến:

| Hiện tượng | Ví dụ | Câu hỏi cần xác minh |
|---|---|---|
| Dirty read | T2 thấy thay đổi T1 chưa commit, T1 rollback | Read API có cho phép đọc dirty không? |
| Non-repeatable read | T1 đọc cùng item hai lần ra giá trị khác | Transaction đọc snapshot cố định hay giá trị mới? |
| Phantom | T1 query một tập; T2 insert record mới; T1 query lại thấy thêm | Predicate/range có được bảo vệ? |
| Lost update | Hai writer ghi từ cùng version cũ | DB phát hiện conflict hay dùng last-write-wins? |
| Write skew | Hai transaction sửa hai record khác nhau dựa trên cùng điều kiện | Isolation có serializable hoặc cơ chế chung không? |
| Read skew | Reader thấy một phần cặp A/B ở các phiên bản không tương ứng | Multi-record snapshot/read API ra sao? |

### 7.1. Test lost update

Giả sử Counter = 0:

~~~text
T1: READ counter = 0
T2: READ counter = 0
T1: WRITE counter = 1
T2: WRITE counter = 1
~~~

Nếu ứng dụng cần mỗi increment được tính, phải dùng atomic increment/CAS hoặc transaction với conflict detection phù hợp. Hai lần `SET 1` thành công không nhất thiết mâu thuẫn với một contract chỉ hỗ trợ last-write-wins trên item.

### 7.2. Test write skew

Hai bác sĩ A, B đều trực. Quy tắc yêu cầu ít nhất một người trực:

~~~text
T1: READ A=true, B=true
T2: READ A=true, B=true
T1: UPDATE A=false
T2: UPDATE B=false
T1: COMMIT
T2: COMMIT
~~~

Nếu cả hai commit thì invariant bị phá. Điều này có thể xảy ra dưới một số hình thức snapshot isolation dù mỗi transaction atomically commit record của mình.

**Test phải được thiết kế theo mức isolation mà sản phẩm thực sự hứa**, không mặc định mọi sản phẩm hứa serializable. Nếu không hứa ngăn write skew, ứng dụng phải thay đổi mô hình hoặc đặt một điểm cạnh tranh chung.

### 7.3. Test phantom và uniqueness

Hai transaction cùng query:

~~~text
Không có usernameKey = "an123".
~~~

Rồi mỗi transaction tạo một account khác nhau. Nếu không có unique index, conditional create trên key chung hoặc serializable predicate protection, cả hai có thể thành công.

Đặc biệt với NoSQL dùng read model/index cập nhật bất đồng bộ, query “không tìm thấy” ở index không được dùng như bằng chứng chắc chắn chưa có key.

### 7.4. Test read skew

Transaction chuyển 50 từ A sang B. Một reader đọc A trước commit, rồi B sau commit:

~~~text
Read A = 200
Commit transfer
Read B = 150
~~~

Tổng hai read có thể thành 350, dù transaction source không bao giờ tồn tại trạng thái đó. Nếu ứng dụng cần snapshot nhất quán của A và B, reader phải dùng API/read transaction/consistency cho đúng phạm vi. Không nên kết luận transaction ghi hỏng chỉ từ hai read không có snapshot.

## 8. Quan sát lịch thực thi (history) thay vì chỉ nhìn một response

Một bài kiểm thử cạnh tranh nên ghi lại:

~~~text
operationId
clientId
startTimestamp
endTimestamp
transactionId / commandId
readSet (keys, versions)
writeSet (keys, intended values)
commitOutcome
errorCode
readConsistency
deploymentRegion / node
observedFinalState
~~~

Đối với dữ liệu nhạy cảm, log chỉ ID/hash/metadata cần thiết theo chính sách; không lưu payload bí mật đầy đủ.

### 8.1. Một history phải được diễn giải theo contract

Ví dụ:

~~~text
T1 starts
T1 reads A=10
T2 starts
T2 writes A=20; commits
T1 writes B=15; commits
~~~

History này có vi phạm hay không tùy T1 có đọc A trên snapshot, invariant giữa A và B, và mức isolation được hứa. **Không gắn nhãn anomaly chỉ dựa trên việc transaction giao nhau về thời gian.**

### 8.2. Thời gian wall clock không thay thế ordering do DB xác nhận

Hai client ở máy khác có clock skew. Để phân tích linearizability, cần phân biệt thời điểm invocation/response theo đồng hồ có thể tin trong test harness hoặc dùng barrier/tracing phù hợp. Sequence/commit index hoặc server version nếu được công bố thường hữu ích hơn một timestamp client tùy ý.

### 8.3. Không chứng minh serializability chỉ bằng một truy vấn tổng

Kiểm tra `sum(balance)` cuối cùng có thể bỏ sót giao dịch trùng, rollback sai hoặc trạng thái không hợp lệ chỉ xuất hiện ngắn trong quá trình. Cần kiểm thử các invariant, read histories và lỗi qua nhiều lịch chạy.

## 9. Thiết kế ma trận kiểm thử đúng phạm vi

Một ma trận giúp tránh test thiếu chiều:

| Dimension | Giá trị cần thử | Lý do |
|---|---|---|
| Số record | 1, 2, nhiều record | Khác phạm vi atomicity |
| Partition | Cùng key, khác key | Phát hiện điều kiện same-partition |
| Collection/table | Cùng và khác | Kiểm tra phạm vi transaction |
| Writer | 1, 2, 10, nhiều | Conflict và throughput |
| Read path | Primary, replica, index, cache | Visibility và lag |
| Isolation | Các mode được cấu hình | Anomaly khác nhau |
| Write concern | Các setting hỗ trợ | Durability/ACK |
| Failure phase | Trước commit, trong commit, sau commit | Atomicity và unknown outcome |
| Node fault | Process, host, replica, leader | Fault tolerance |
| Region | Cùng region, nhiều region | Cross-region consistency |
| Payload | Nhỏ, sát quota, vượt quota | Giới hạn size |
| Transaction time | Ngắn, sát timeout, vượt | Lock/abort/timeout |
| Client retry | Không retry, retry cùng ID, retry sai ID | Idempotency |

Không cần lấy tích Descartes của tất cả chiều thành hàng triệu bài test. Chọn **case ưu tiên theo bất biến và rủi ro**, còn các giới hạn được thử theo nhóm có ý nghĩa. Ghi rõ những chiều chưa được kiểm thử.

### 9.1. Test case có cấu trúc

~~~yaml
testId: same-partition-two-records
requirement: "atomicity for supported transaction scope"
deployment: "<version/topology/configuration>"
preconditions:
  - "A and B share the required logical partition"
  - "A=10, B=20"
actions:
  - "BEGIN transaction"
  - "write A=11"
  - "inject failure before final commit"
  - "attempt write B=21"
expected:
  - "after confirmed abort: A=10, B=20"
  - "after confirmed commit: A=11, B=21"
  - "if outcome unknown: reconcile before asserting final category"
observations:
  - "transaction response and error category"
  - "authoritative read after recovery"
  - "fault injection marker"
~~~

Ví dụ này chỉ là **test specification**. Khi một API không cho phép chèn lỗi chính xác giữa các thao tác, phải dùng cơ chế test hook/proxy của môi trường kiểm thử hoặc mô tả hạn chế thay vì tuyên bố đã kiểm chứng.

## 10. Phải có test âm tính ngoài phạm vi hứa

Điểm dễ bỏ sót: một hợp đồng nói “transaction cùng partition” nhưng nhóm chỉ test hai item cùng partition rồi suy ra nhiều partition cũng được bảo vệ.

Hãy thiết kế **negative control**:

~~~text
Test A:
    Item X, Y cùng logical partition.
    Dùng transactional batch.
    Kỳ vọng atomicity theo contract.

Test B:
    Item X, Y thuộc hai logical partition khác nhau.
    Cố dùng cùng API.
    Kỳ vọng API từ chối / không hỗ trợ theo contract,
    KHÔNG tự cho rằng commit nguyên tử.
~~~

Nếu API từ chối, đó có thể là hành vi đúng. Đừng sửa test để “cho qua” bằng cách chia thành hai batch rồi vẫn đặt tên thao tác là một transaction.

### 10.1. Negative control khác thử phá giới hạn sản phẩm

Mục tiêu là xác minh một giới hạn đã được tài liệu hóa. Không cần gây tải hoặc thử lỗi trên production. Dùng môi trường test với quota, quyền và fault injection phù hợp.

### 10.2. Không đánh đồng “không hỗ trợ” với “đã thử và an toàn”

Nếu một API không cho cross-partition transaction, kết luận phải là **không thể dựa vào API này để bảo vệ invariant cross-partition**. Dù hai lần ghi riêng từng thử nghiệm “đều thành công”, chúng vẫn không có hợp đồng nguyên tử chung.

## 11. Kiểm thử commit, abort và unknown outcome

Một lỗi điển hình:

~~~text
Client -> COMMIT
Database commits
Network drops ACK
Client sees timeout
~~~

Client không biết chắc commit đã xảy ra. **Timeout không phải rollback**.

### 11.1. Phân loại outcome

| Outcome | Có thể khẳng định điều gì? | Hành động |
|---|---|---|
| Successful commit ACK | Commit thành công theo contract của API/config | Trả kết quả và version/ID |
| Confirmed abort | Transaction không commit | Cho phép đánh giá lại |
| Business precondition failure | Predicate nghiệp vụ không đạt | Không retry vô điều kiện |
| Serialization conflict | Engine từ chối một lịch cạnh tranh | Retry từ state mới nếu command an toàn |
| Retryable infrastructure error | Lỗi tạm thời được API phân loại | Retry có backoff và giới hạn |
| Unknown commit result | Chưa xác định commit hay abort | Query/idempotency/retry commit theo protocol sản phẩm |

### 11.2. Business commandId

Một checkout:

~~~json
{
  "commandId": "checkout-7281",
  "orderId": "O-100",
  "sku": "SKU-A",
  "quantity": 2
}
~~~

Nếu transaction commit thành công nhưng HTTP response mất, retry với cùng `commandId` phải nhận ra kết quả cũ. Một số API có client transaction token, nhưng **thời hạn/phạm vi hiệu lực của token đó có thể giới hạn**; business idempotency bền lâu cần thiết kế riêng.

### 11.3. Tránh duplicate side effects

Không gọi payment gateway, gửi email hay phát webhook không idempotent trong transaction callback có thể tự retry. Nếu callback chạy lại, side effect có thể xảy ra nhiều lần dù DB cuối cùng chỉ commit một transaction.

### 11.4. Test điểm cắt kết nối

Một suite nên thử:

1. Timeout **trước khi request đến server**.
2. Timeout sau khi server nhận nhưng **trước commit**.
3. Timeout sau khi **commit đã xảy ra**, trước ACK.
4. Client retry cùng commandId.
5. Client gửi commandId mới cho cùng ý định (negative case).

Kết quả mong muốn phụ thuộc API, nhưng application phải **không tạo hiệu ứng nghiệp vụ trùng** chỉ vì không biết commit outcome.

## 12. Mẫu Java cho contract test nhiều writer

Để tách domain invariant khỏi SDK cụ thể, có thể định nghĩa một adapter. Đây là **test harness skeleton**: nhóm cần triển khai adapter cho database đang kiểm thử, không dùng trực tiếp như một engine NoSQL.

~~~java
public interface InventoryTransactionAdapter {

    void reset(String sku, int available);

    // Trả RESERVED nếu reservation được commit,
    // INSUFFICIENT nếu predicate không đạt.
    // UNKNOWN khi không thể xác định commit outcome.
    ReserveOutcome reserve(
        String sku,
        String reservationId,
        int quantity
    );

    int availableFromAuthoritativeRead(String sku);

    int totalCommittedReservations(String sku);
}

public enum ReserveOutcome {
    RESERVED,
    INSUFFICIENT,
    UNKNOWN
}
~~~

### 12.1. Test tranh chấp bằng barrier

Ví dụ JUnit 5, dùng `ExecutorService` để hai writer bắt đầu gần như đồng thời:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class InventoryContractTest {

    private final InventoryTransactionAdapter adapter =
        TestEnvironment.inventoryAdapter();

    @Test
    void concurrentReservationsMustNotOversell() throws Exception {
        String sku = "SKU-RACE-1";
        adapter.reset(sku, 5);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<ReserveOutcome> a = () -> {
            ready.countDown();
            start.await();
            return adapter.reserve(sku, "reserve-A", 4);
        };
        Callable<ReserveOutcome> b = () -> {
            ready.countDown();
            start.await();
            return adapter.reserve(sku, "reserve-B", 3);
        };

        try {
            Future<ReserveOutcome> fa = pool.submit(a);
            Future<ReserveOutcome> fb = pool.submit(b);

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            ReserveOutcome oa = fa.get(10, TimeUnit.SECONDS);
            ReserveOutcome ob = fb.get(10, TimeUnit.SECONDS);

            // Với outcome UNKNOWN phải đối soát theo reservationId,
            // không thể chỉ đếm response như một quyết định cuối.
            assertNotEquals(ReserveOutcome.UNKNOWN, oa);
            assertNotEquals(ReserveOutcome.UNKNOWN, ob);

            assertEquals(1,
                (oa == ReserveOutcome.RESERVED ? 1 : 0)
                + (ob == ReserveOutcome.RESERVED ? 1 : 0));

            int reserved = adapter.totalCommittedReservations(sku);
            int remaining = adapter.availableFromAuthoritativeRead(sku);

            assertTrue(reserved <= 5);
            assertEquals(5, reserved + remaining);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

`TestEnvironment` là **fixture giả định** mà nhóm phải cung cấp, với dữ liệu test độc lập và adapter thật. Test này **không phải bằng chứng về engine** cho tới khi chạy trên đúng deployment và kiểm tra điều kiện đua thật sự đã xuất hiện.

### 12.2. Barrier không đảm bảo hai commit đồng thời tuyệt đối

Latch chỉ đồng bộ thời điểm các task bắt đầu gọi adapter. Scheduling, network và engine còn có thể làm các lệnh chạy lệch nhau. Để tăng sức phát hiện lỗi:

- Chạy nhiều lần với dữ liệu độc lập.
- Dùng test hook/barrier bên trong transaction sau lần đọc, nếu môi trường cho phép.
- Thu thập read/write history.
- Thử nhiều mức contention.
- Kiểm tra invariant tại nguồn sau khi tất cả outcome đã được đối soát.

### 12.3. Không ép UNKNOWN thành thất bại hoặc thành công

Trong fault injection, một response timeout là một kết quả cần phân loại riêng. Phải tra `reservationId` hoặc áp dụng protocol recovery trước khi kết luận transaction đã commit/abort.

## 13. Test write skew bằng lịch chạy chủ động

Thiết kế test:

~~~text
Ban đầu:
    A.onCall=true
    B.onCall=true

Transaction T1:
    read A, B
    wait at barrier
    update A=false
    commit

Transaction T2:
    read A, B
    wait at barrier
    update B=false
    commit
~~~

Kết quả cần đối chiếu **theo isolation contract**:

- Nếu sản phẩm và mode đã hứa **serializable** cho giao dịch thuộc phạm vi đó, hai commit tạo `A=false, B=false` là phản ví dụ cần điều tra.
- Nếu sản phẩm chỉ hứa một mức snapshot isolation cho phép write skew, test có thể quan sát cả hai commit; lỗi thiết kế là **đặt invariant ngoài mức bảo vệ**.
- Nếu hai item không thuộc cùng transaction scope, test không chứng minh gì về transaction toàn cục; phải đổi data model hoặc protocol.

### 13.1. Buộc cạnh tranh tại thời điểm thích hợp

Đặt barrier **sau khi cả hai transaction đã đọc** nhưng trước khi chúng ghi giúp tăng khả năng kiểm tra write skew. Cần xem SDK có timeout/automatic retry callback khiến barrier không thể dùng trực tiếp trong lần thử lại; test hook phải phù hợp với retry semantics để không gây deadlock giả.

### 13.2. Serializable có thể abort một transaction

Đừng thiết kế expected là “hai lệnh đều commit và kết quả vẫn đúng”. Một hệ serializable có thể từ chối một giao dịch vì conflict. Assertion cần là **không có lịch commit vi phạm invariant**, không phải “không bao giờ báo conflict”.

## 14. Test atomicity khi xảy ra lỗi giữa transaction

Một kịch bản:

~~~text
T1 BEGIN
T1 update A: 200 -> 150
T1 update B: 100 -> 150
T1 COMMIT
~~~

Điểm fault injection:

~~~text
F1: sau BEGIN, trước write A
F2: sau write A, trước write B
F3: sau write B, trước commit
F4: trong quá trình commit
F5: sau commit, trước khi client nhận ACK
~~~

Sau khi hệ có kết quả rõ ràng:

| Outcome | A | B |
|---|---:|---:|
| Commit | 150 | 150 |
| Abort | 200 | 100 |
| Unknown tại client | Chưa kết luận | Phải đối soát trước |

Một số API không cho phép tạo `F2` đúng byte-level bằng code ứng dụng; có thể dùng proxy, crash hooks hoặc integration test runner. Không giả định dừng thread client bằng một lệnh `sleep()` đã chèn lỗi vào transaction storage.

### 14.1. Kiểm thử thiếu một lệnh trong batch

Nếu thao tác thứ hai có constraint failure, nhóm cần biết transaction hủy tất cả hay chỉ một phần. Điều đó đặc biệt quan trọng khi so sánh **transactional batch** với một API batch chỉ nhóm request.

### 14.2. Không kết luận từ một read replica trễ

Sau commit, nếu đọc A ở leader và B ở một replica lag, có thể thấy tổ hợp “nửa cũ, nửa mới” dù source transaction atomic. Phải dùng read mode/nguồn có khả năng kiểm chứng đúng hợp đồng trước khi báo database vi phạm atomicity.

## 15. Durability: test theo đúng điểm ACK

Một transaction có thể được commit nguyên tử nhưng mất sau một lỗi mà deployment không hứa chịu được.

### 15.1. Đọc write concern và durability option

Cần ghi:

~~~text
Khi server gửi successful commit response:
    mutation đã ở RAM?
    đã append vào WAL?
    đã fsync/journal local?
    có replica nào xác nhận?
    các replica xác nhận đã bền hay chỉ đã nhận?
    có quorum/consensus commit theo protocol?
~~~

Đừng coi `ACK=success` là bằng chứng dữ liệu tồn tại vĩnh viễn qua mọi loại crash.

### 15.2. Test process kill

Ghi một nhóm transaction có commandId. Ghi lại những transaction **đã ACK**. Kill tiến trình, restart, đọc tại nguồn có thẩm quyền và đối soát. Test này chỉ chứng minh hành vi quan sát được với **process failure**, không thay thế power-loss testing.

### 15.3. Test leader failover

Với replicated cluster, commit các transaction theo cấu hình production, rồi gây lỗi node/leader có kiểm soát. Sau failover, xác minh các transaction phải được giữ theo fault model tương ứng. Không được tự giả định một ACK local đảm bảo tồn tại khi leader mất vĩnh viễn.

### 15.4. Test region failover

Chỉ thực hiện khi sản phẩm và hệ thống có **contract rõ về cross-region durability và RPO**. Nếu replication bất đồng bộ giữa region, dữ liệu đã ACK ở region A vẫn có thể chưa tới B khi A mất. Kết luận phải nêu đúng mức chấp nhận mất dữ liệu, không tô kết quả thành transaction toàn cầu.

## 16. Read consistency, read-your-writes và projection

Giao dịch ghi đã commit không đồng nghĩa mọi read API ở mọi nơi lập tức thấy toàn bộ kết quả.

### 16.1. Đọc từ nguồn có thẩm quyền

Với test atomicity, ưu tiên đọc theo consistency/read concern được tài liệu hóa là đủ mạnh để đối chiếu commit ở phạm vi đã kiểm thử.

### 16.2. Read replica

Replica có thể chậm, khiến một client vừa commit Order CONFIRMED nhưng GET từ replica trả PENDING. Đây có thể là hành vi được cho phép bởi read mode. Phải xác định ứng dụng cần **read-your-writes, monotonic reads hay strong reads**, và chọn API/session/routing tương ứng.

### 16.3. Global secondary index và search index

Một index hoặc projection có thể cập nhật theo pipeline riêng. Không kết luận transaction thất bại vì search chưa thấy event mới ngay sau commit. Thay vào đó, kiểm tra index lag, outbox status và eventual convergence theo SLO.

### 16.4. Kiểm tra hai lớp

~~~text
Layer 1: Source-of-truth transaction correctness
    -> atomicity, isolation, durability

Layer 2: Derived read model consistency
    -> ordering, idempotency, lag, cache invalidation
~~~

Nếu cả hai bị gom thành một test “đọc endpoint sau ghi”, sẽ khó tìm đúng nơi hỏng.

## 17. Cách đọc hợp đồng theo từng họ sản phẩm

Dưới đây không phải bảng tuyên bố giới hạn số lượng cố định. Mục tiêu là chỉ ra **những mệnh đề cần kiểm tra và các bài test nên viết**.

| Sản phẩm / họ | Tính năng cần tra | Test phạm vi nổi bật |
|---|---|---|
| **MongoDB** | Session, multi-document transaction, read/write concern, topology | Hai collection, nhiều shard, commit timeout, driver callback retry |
| **DynamoDB** | Transaction API, conditional write, action/size limits, region | Multi-item atomicity, contention, client token, global-table boundary |
| **Firestore** | Transaction callback, read-before-write, retry và rules | Two-document conflict, callback retry, latency/size limits |
| **Cosmos DB for NoSQL** | Transactional batch/stored procedure, logical partition, ETag | Same partition vs cross-partition negative control |
| **Couchbase** | SDK transactions, staging/cleanup, durability và topology | Abort/retry, cleanup sau crash, nhiều document |
| **Cassandra/ScyllaDB** | IF/LWT, batch semantics, partition scope | LWT contention, logged batch khác serializable transaction |
| **Redis** | WATCH/MULTI/EXEC, Lua, key-slot, persistence | Watch conflict, runtime error semantics, failover/durability |
| **Transactional KV (ví dụ FoundationDB)** | Read/write conflict ranges, transaction limits, retry | Serializable conflict, range/predicate, size/time |

### 17.1. MongoDB

Khi tài liệu nói multi-document transactions, cần xem deployment có thuộc topology được hỗ trợ, liệu các collection/shard thực tế có tham gia, các setting readConcern/writeConcern và giao thức xử lý **TransientTransactionError / UnknownTransactionCommitResult** theo driver đang dùng.

Các test nên có:

- Update hai document trong cùng collection.
- Update document ở hai collection và nhiều shard nếu topology hỗ trợ.
- Concurrent update cùng Inventory item.
- Lỗi sau thao tác ghi đầu tiên nhưng trước commit.
- Timeout khi commit và đối soát bằng business commandId.
- Callback có side effect: negative case để chứng minh không được đưa gateway/email vào đó.

Không suy rằng localhost standalone có cùng tính năng với replica set/sharded cluster.

### 17.2. DynamoDB

Phân biệt **UpdateItem có ConditionExpression** với **TransactWriteItems**. Một thao tác conditional item không bảo vệ tự động Order và Outbox ở các item khác. Transaction API có giới hạn action/bytes và phạm vi theo dịch vụ; một số chế độ replication multi-region có semantics khác commit của transaction local.

Test:

- Update Inventory với condition đủ tồn.
- Put Order và Outbox trong một transaction được hỗ trợ.
- Một condition failed: kiểm tra không có partial transaction.
- Cùng request token/payload retry theo quy tắc documented.
- Retry sau unknown outcome ngoài thời hạn token: xử lý bằng business commandId.
- Hai region writer cạnh tranh: xác nhận rõ giới hạn của global deployment.

### 17.3. Firestore

Đọc tài liệu **transaction callback có thể chạy lại**, phạm vi nhiều document, nguyên tắc đọc trước ghi, security rules và giới hạn kích thước/thời gian. Không cho network side effects vào callback có thể bị retry.

Test:

- Hai transaction cùng đọc một document rồi update.
- Callback bị retry khi conflict và domain không phát event trùng.
- Đọc nhiều document từ transaction theo API hỗ trợ.
- Transaction gần timeout hoặc vượt giới hạn.
- Khác biệt giữa transaction và batched writes.

### 17.4. Cosmos DB for NoSQL

Đọc thật kỹ **logical partition key** cho transactional batch/stored procedure. Không lấy việc hai item có cùng `tenantId` làm kết luận nếu partition key thực tế khác.

Test:

- Hai item cùng logical partition: một thao tác lỗi làm cả batch không commit.
- Hai item khác logical partition: API phải được dùng đúng ràng buộc và kết quả “không hỗ trợ” phải được ghi nhận.
- ETag/If-Match khi hai client sửa cùng item.
- Multi-region mode: kiểm tra contract replication và nơi cho phép ghi.

### 17.5. Couchbase

SDK transaction có cơ chế staging, commit/cleanup và durability riêng. Tài liệu có thể yêu cầu cấu hình bucket/cluster và hướng dẫn xử lý attempt retries.

Test:

- Abort khi một phần thao tác đã staged.
- Conflict giữa hai transaction trên document chung.
- Crash trong thời điểm commit/cleanup và đọc state sau recovery.
- Driver callback được chạy lại nhưng không gọi external side effect.

### 17.6. Cassandra/ScyllaDB

Phân biệt **logged batch**, **unlogged batch**, thao tác **IF/LWT** và transaction kiểu nhiều record. Logged batch không mặc nhiên cung cấp serializable isolation xuyên arbitrary partitions.

Test:

- Cạnh tranh LWT trên một key hoặc partition được hỗ trợ.
- Batch chứa nhiều mutation và chèn lỗi theo API.
- Reader đồng thời có thể thấy trạng thái nào theo contract?
- Conditional batch vượt partition scope: negative control.
- Latency và throughput khi LWT chạy trên hot partition.

### 17.7. Redis

`MULTI/EXEC` cho chuỗi lệnh theo semantics Redis, nhưng không cung cấp rollback mọi lệnh đã thực hiện khi có runtime error như transaction SQL. `WATCH` là cơ chế OCC; script Lua/Function có tính nguyên tử trong phạm vi hỗ trợ nhưng cần kiểm soát side effect và durability.

Test:

- Hai client WATCH cùng key, một client thay đổi trước EXEC.
- Lệnh trong MULTI gây lỗi runtime: quan sát các lệnh khác theo contract.
- Các key thuộc nhiều slot Redis Cluster: xác minh hỗ trợ/không hỗ trợ.
- Failover sau ACK và AOF/replication settings.
- Retry một command decrement có idempotency key.

### 17.8. Transactional key–value store

Với hệ hỗ trợ transaction nhiều key/range như FoundationDB, cần đọc **conflict range**, thời hạn transaction, size limit, retry semantics và cách transaction trả kết quả. Thử write skew, read/write conflicts và range predicate; không dùng “NoSQL” để suy rằng mọi transaction đều chỉ một item.

## 18. Test giới hạn không phải chỉ tìm con số tối đa

Khi tài liệu cho giới hạn, hãy kiểm tra cả **hành vi khi đến giới hạn**:

### 18.1. Transaction quá nhiều item

Kỳ vọng: API từ chối rõ ràng hoặc có outcome documented. Không được tự tách thành hai transaction rồi ghi “đã commit tất cả” khi một transaction thành công và transaction kia thất bại.

### 18.2. Tổng payload quá lớn

Một Order có nhiều item, metadata và index updates có thể vượt giới hạn mặc dù từng item riêng vẫn hợp lệ. Thử gần ngưỡng và vượt ngưỡng trong test environment.

### 18.3. Transaction quá dài

Một callback gọi API mạng 30 giây hoặc chờ người dùng có thể làm transaction timeout, tăng contention và pin snapshot. Test cần phân biệt thời gian ứng dụng chờ với **transaction lifetime do server tính**.

### 18.4. Transaction trên partition nóng

Cùng SKU nhận hàng nghìn request. Thử load tăng dần, đo conflict rate, retry cost và p99. Ngay cả khi tính đúng vẫn được giữ, hệ có thể không đạt throughput SLO.

### 18.5. Chạy dưới phiên bản/edition khác

Một deployment dev emulator hoặc local cluster có thể không biểu diễn cùng topology hoặc quota production. Ghi rõ version, tier, feature flag và mode deployment cho mỗi test report.

## 19. Không kiểm thử production bằng phá hoại không kiểm soát

Fault injection có thể gồm kill node, chặn network, làm chậm disk hoặc lỗi nhân tạo tại commit. Những thao tác này phải:

- Chạy trên **môi trường thử nghiệm** hoặc một môi trường chaos được cấp quyền rõ ràng.
- Có dữ liệu giả và namespace cô lập.
- Có giới hạn tài nguyên và khả năng rollback/rebuild.
- Có cơ chế xác định và dừng test khi ảnh hưởng vượt ngưỡng.
- Có telemetry để xác định đúng điểm fault.

Không dùng production database của người dùng thật để kiểm thử “mất region” hoặc “disk full” trừ khi có quy trình vận hành và phạm vi được phê duyệt đặc biệt.

### 19.1. Process crash và power loss khác nhau

Kill process có thể để OS page cache còn sống. Mất điện kiểm tra một lớp khác. Không tuyên bố đã kiểm chứng durable fsync chỉ từ process kill.

### 19.2. Chaos test không chứng minh mọi trường hợp

Một hệ chạy qua 100 lần failover không chứng minh mọi lịch phân tán có thể xảy ra. Kết hợp test với tài liệu protocol, model checking/linearizability analysis khi thích hợp và đối soát invariant thường xuyên.

## 20. Tính đúng đắn khi transaction callback tự retry

Một số SDK cho phép:

~~~text
runTransaction(callback)
~~~

Nếu có write conflict, SDK có thể thực hiện callback lại theo chính sách. Khi đó:

~~~text
callback:
    read Inventory
    update Inventory
    callPaymentGateway()  // NGUY HIỂM
~~~

Gateway có thể được gọi hai lần dù chỉ một attempt transaction cuối cùng commit.

### 20.1. Những gì nên để trong callback

- Đọc state từ DB trong transaction.
- Kiểm tra predicate nghiệp vụ.
- Tính toán thuần, không phụ thuộc thời gian ngoài nếu cần deterministic.
- Ghi item thuộc transaction scope.
- Ghi outbox/intent nếu nằm cùng atomic boundary.

### 20.2. Những gì nên tách ra

- Gửi email.
- Gọi payment gateway không có idempotency.
- Gửi webhook.
- Upload file lớn.
- Ghi vào database thứ hai ngoài transaction.
- Gọi dịch vụ có latency lớn.

Các bước này đi qua workflow bền, với idempotency key, trạng thái và đối soát.

### 20.3. Cẩn trọng với callback có biến mutable bên ngoài

Nếu callback chạy lại mà code tăng một counter hoặc thêm một item vào list ngoài transaction, số lần thử có thể ảnh hưởng kết quả. Đừng dùng side effect trong bộ nhớ làm bằng chứng “lệnh đã commit”. Kết quả commit phải được xác nhận từ API/database.

## 21. Test idempotency ở tầng nghiệp vụ

**Transaction atomicity** và **idempotency** giải quyết hai vấn đề khác nhau:

~~~text
Atomicity:
    Có tất cả thay đổi trong một transaction, hoặc không có.

Idempotency:
    Cùng một ý định gửi lại nhiều lần không tạo
    thêm hiệu ứng nghiệp vụ.
~~~

Ví dụ:

~~~text
checkout(commandId = C-100) -> Order O-100, Payment P-100
retry checkout(commandId = C-100) -> cùng kết quả logic
~~~

### 21.1. Test request bị gửi lặp

Chạy đồng thời hai request **cùng commandId**. Kỳ vọng chỉ có một kết quả nghiệp vụ có thẩm quyền và mọi caller được trả response nhất quán hoặc trạng thái có thể đối soát.

### 21.2. Test hai commandId khác nhau

Hai ID khác nhau nhưng cùng tác động một resource phải tuân thủ invariant (tồn kho, uniqueness...). Không dùng idempotency để thay thế conflict detection.

### 21.3. Test retry sau crash

Đưa hệ vào trạng thái đã commit source nhưng chưa ACK. Restart client và gửi lại cùng ID. Kỳ vọng không tạo duplicate Order, không thu tiền lần nữa và không phát outbox event logic mới ngoài policy.

## 22. Test transactional outbox

Một nguồn Order có thể ghi:

~~~text
Transaction:
    Order.status = CONFIRMED
    Outbox(eventId = E-100, type = OrderConfirmed)
Commit
~~~

Nếu contract transaction bao phủ **cả Order và Outbox**, invariant là: khi Order CONFIRMED đã commit theo workflow, intent phát event phải được lưu bền.

### 22.1. Test commit/abort

- Cố ý làm insert Outbox thất bại: Order không được CONFIRMED nếu cả hai là một transaction thực.
- Cố ý làm update Order không thỏa version: Outbox không được ghi như event đã xác nhận.
- Kill publisher sau khi publish nhưng trước khi đánh dấu event đã gửi: consumer không được áp hiệu ứng trùng.

### 22.2. Trường hợp khác partition

Nếu Order và Outbox ở hai partition nhưng hệ chỉ hỗ trợ single-partition atomicity, phải **đổi thiết kế** hoặc dùng cơ chế khác; không kết luận “outbox transactional” chỉ vì hai write nằm cùng request.

### 22.3. Event order

Event Order version 9 đến consumer trước version 8. Projection không được ghi đè state mới bằng event cũ. Transaction đảm bảo dữ liệu nguồn, còn ordering/dedupe downstream cần được thiết kế và test riêng.

## 23. Khi nào dùng saga hoặc chuyển invariant về một record?

Nếu hợp đồng sản phẩm không bao phủ đúng phạm vi, có ba lựa chọn lớn:

1. **Đổi mô hình dữ liệu:** chuyển invariant vào một aggregate/item phù hợp, bounded.
2. **Chọn cơ chế transaction khác:** sản phẩm/topology hỗ trợ cross-record transaction cần thiết.
3. **Đổi quy trình nghiệp vụ:** dùng saga, reservation, outbox và compensation với trạng thái trung gian được định nghĩa.

### 23.1. Dùng một aggregate

Một Order có số dòng nhỏ và total tính từ items có thể được lưu nguyên tử trong một document; không cần cross-document transaction cho invariant nội bộ. Nhưng không nhúng lịch sử vô hạn hoặc mọi đơn của customer vào một document nóng.

### 23.2. Dùng saga

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RESERVING: Reserve Inventory
    RESERVING --> RESERVED: Succeeded
    RESERVING --> CANCELING: Failed
    RESERVED --> PAYING: Payment request
    PAYING --> CONFIRMED: Payment confirmed
    PAYING --> CANCELING: Payment failed
    CANCELING --> CANCELED: Compensation completed
    CONFIRMED --> [*]
    CANCELED --> [*]
~~~

Saga không phải rollback thực sự của mọi hiệu ứng: email đã gửi không thể thu hồi, payment cần refund/cancel có trạng thái riêng, compensation có thể thất bại. Mỗi bước cục bộ vẫn phải giữ invariant bằng conditional write/transaction thích hợp.

### 23.3. Đừng lấy eventual consistency làm lý do bỏ invariant

Cho phép read model chậm là một chuyện; cho phép Inventory cấp vượt số hàng thật là chuyện khác. Dù workflow eventual, những invariant bắt buộc phải đúng tức thời tại **owner aggregate** vẫn phải được bảo vệ.

## 24. Hồ sơ test được phép kết luận điều gì?

Một báo cáo tốt cần tách:

### Được phép kết luận

> Trên deployment D, phiên bản V, cấu hình C, với các item cùng logical partition, trong N lần chạy và fault model F, test không quan sát partial commit; kết quả phù hợp với hợp đồng atomicity được tài liệu hóa.

### Không được phép kết luận

> Database này luôn ACID mọi trường hợp, mọi region, mọi service và không thể mất dữ liệu.

### 24.1. Khi test phát hiện phản ví dụ

Nếu thấy invariant bị phá:

1. Kiểm tra test có dùng đúng API và cấu hình hứa bảo đảm không.
2. Kiểm tra các record có ở đúng transaction scope không.
3. Kiểm tra read consistency của phép đối chiếu.
4. Kiểm tra các writer khác có bypass contract không.
5. Kiểm tra driver retry/unknown outcome có được xử lý đúng không.
6. Chỉ sau đó mới xác định lỗi từ application, test harness hoặc DB.

Không vội quy lỗi sản phẩm khi application đã sử dụng API ngoài phạm vi.

### 24.2. Khi test pass

Điều này là bằng chứng hữu ích nhưng không tuyệt đối. Ghi N, môi trường, cấu hình, seed, lịch thực thi và hạn chế. Sau mỗi thay đổi topology/version/SDK hoặc partition strategy, cần xem lại những assertion liên quan.

## 25. Các bài test quan trọng theo lỗi thực tế

| Test | Bất biến/thuộc tính | Phát hiện |
|---|---|---|
| Hai writer cùng expectedVersion | OCC | Lost update / stale write |
| Hai reservation tổng vượt tồn | Business predicate | Oversell |
| Cặp A/B, chèn lỗi giữa write | Atomicity | Partial commit |
| Hai bác sĩ cùng nghỉ | Isolation | Write skew |
| Query username rồi insert | Predicate uniqueness | Phantom/duplicate |
| Đọc cặp A/B trên snapshot | Read isolation | Read skew |
| Commit ACK mất | Idempotency | Duplicate command |
| Client callback retry | SDK behavior | Duplicate side effects |
| Cross-partition negative test | Transaction scope | Nhầm phạm vi |
| Replica lag sau commit | Visibility | Stale reads |
| Kill leader sau ACK | Durability/failover | Mất committed writes theo fault model |
| Multi-region simultaneous writes | Region scope | Lost updates/conflict resolution |
| Batch gần giới hạn | Capacity/size | Oversize/timeout |
| Hot key contention | Performance | Retry storm |
| Outbox publisher crash | Event delivery | Lost/duplicate events |

## 26. Observability cho transaction production

| Metric | Ý nghĩa |
|---|---|
| Transaction success/abort | Tỷ lệ commit/abort |
| Serialization/condition conflict | Mức tranh chấp và việc bảo vệ invariant |
| p95/p99 transaction duration | Transaction quá dài hoặc contention |
| Number of items/bytes per transaction | Có tiến sát hạn API không |
| Retried callbacks/attempts | SDK có chạy lại logic không |
| Unknown commit outcomes | Bao nhiêu giao dịch cần đối soát |
| Duplicate command suppression | Hiệu quả idempotency |
| Hot partition/key | Nơi tạo bottleneck |
| Lock/snapshot/intent pressure | Tài nguyên bị giữ bởi transaction |
| Replica/index lag | Khác biệt source và đường đọc |
| Outbox publish lag | Downstream cập nhật chậm |
| Stuck saga/compensation | Workflow bị kẹt |
| Invariant mismatch | Oversell, negative balance, duplicate username |

### 26.1. Phân loại lỗi, không chỉ đếm “transaction failed”

Một `INSUFFICIENT_STOCK` là từ chối nghiệp vụ bình thường; một `VERSION_CONFLICT` có thể cần refresh; `TRANSACTION_TOO_LARGE` là vấn đề thiết kế; `THROTTLED` cần backoff/capacity; `UNKNOWN_COMMIT` cần đối soát. Gộp chúng thành một mã lỗi rồi tự retry tất cả có thể làm hệ không ổn định.

### 26.2. Thử thách ngoài happy path

Một service có 99% transaction thành công nhưng tất cả 1% còn lại nằm trên SKU flash sale có thể vẫn không đáp ứng sản phẩm. Cần phân tích theo **key, tenant, region, payload size, isolation mode và error class**, không chỉ aggregate trung bình.

## 27. Anti-pattern khi đọc và kiểm thử contract

### “Có chữ ACID là đủ”

Không. ACID có phạm vi, isolation và durability settings cần ghi rõ.

### “Hỗ trợ transaction một partition thì transaction xuyên partition cũng được”

Không. Cần test negative control và không vượt phạm vi tài liệu.

### “Hai write trong một request là transaction”

Batch không mặc nhiên atomic/isolation như transaction.

### “Process kill pass nên chắc chắn chịu power loss”

Không. Fault model khác nhau.

### “Timeout commit nghĩa là rollback”

Không. Commit có thể đã xảy ra trước khi ACK bị mất.

### “Callback SDK chạy đúng một lần”

Nhiều API có retry callback. Side effects ngoài DB phải tách ra.

### “Snapshot isolation luôn chặn write skew”

Không. Cần đọc isolation contract và test anomaly cụ thể.

### “Một read từ replica thấy thiếu item tức transaction đã commit một nửa”

Chưa chắc. Read lag/consistency có thể tạo cảm nhận đó.

### “Chỉ cần test khi không có writer khác”

Không đủ. Lỗi transaction thường xuất hiện do cạnh tranh.

### “Test pass một lần ở local đủ xác nhận production”

Không. Topology, version, region và fault model có thể khác.

### “Không có transaction cross-service thì cứ commit tuần tự là xong”

Không. Cần idempotency, compensation, durable workflow và đối soát.

### “Transaction giải quyết luôn duplicate request”

Không. Idempotency là contract riêng cho cùng nghiệp vụ được gửi lại.

### “Outbox transactional dù ở hai partition không cùng transaction scope”

Không. Hai write tách rời vẫn có khe lỗi.

### “Chạy nhiều hơn là chứng minh mọi history đúng”

Test tăng độ tin cậy và phát hiện phản ví dụ, không thay thế hiểu protocol và contract.

## 28. Quy trình review hợp đồng giao dịch của một sản phẩm mới

### Bước 1: Viết invariant bằng ngôn ngữ nghiệp vụ

Ví dụ: `available >= 0`; một `orderId` duy nhất; event đã commit phải có intent phát bền. Gắn từng invariant với owner và điểm commit.

### Bước 2: Vẽ bản đồ dữ liệu thật

Liệt kê item/document, partition key, collection/table, shard, region và service của mỗi command. Đừng chỉ vẽ đối tượng domain.

### Bước 3: Xác định API sẽ dùng

Conditional update, transaction callback, transactional batch, stored procedure, LWT hay workflow. Ghi rõ API không hỗ trợ điều gì.

### Bước 4: Tra tài liệu phiên bản triển khai

Đọc atomicity, isolation, durability, limits, retry và topology. Chụp lại cấu hình production thực tế (không gồm secret).

### Bước 5: Biến contract thành assertion

Ví dụ: “hai item cùng partition commit all-or-none”; “status không được thay nếu expectedVersion cũ”; “ACK quorum theo chế độ W giữ dữ liệu khi mất node theo fault model F”.

### Bước 6: Thiết kế positive và negative controls

Test trong phạm vi được hứa, test rõ nơi API từ chối. Không để một negative case chạy thành công do app đã tách thành hai thao tác.

### Bước 7: Chạy concurrency tests

Sử dụng barrier, nhiều worker, log history, kiểm tra kết quả cuối và các anomaly như lost update/write skew.

### Bước 8: Chạy fault injection

Kiểm thử crash và network timeout trước, trong và sau commit. Chỉ chạy trong môi trường được phép.

### Bước 9: Kiểm tra retry và idempotency

SDK có retry callback không? Business commandId có được giữ qua lần gửi lặp không? Unknown outcome được đối soát bằng cách nào?

### Bước 10: Đo performance và giới hạn

Test size/time bounds, hot key, p99, throughput, conflicts, read consistency và failover.

### Bước 11: Lưu test evidence

Ghi sản phẩm, version, SDK, config, topology, command history, test seeds, số lần chạy, các lỗi quan sát, ranh giới được kiểm chứng và chưa kiểm chứng.

### Bước 12: Chọn hoặc điều chỉnh kiến trúc

Nếu contract không bao phủ invariant, không cố diễn giải rộng. Chọn aggregate khác, transaction engine khác hoặc workflow có saga/outbox/compensation được thiết kế rõ.

## 29. Bài tập thực hành

### Bài 1 — Phát biểu có điều kiện

Tài liệu ghi “atomic batch within a logical partition”. Hãy viết lại thành mệnh đề có version, topology, API, partition key, commit outcome và expected evidence. Nêu điều **không được suy ra**.

### Bài 2 — Same-partition và cross-partition

Ba document A, B, C; A và B cùng partition, C thuộc partition khác. Hệ chỉ hỗ trợ transactional batch cùng partition. Thiết kế test positive cho A/B, negative cho A/C và cách xử lý nghiệp vụ nếu cần atomicity cả ba.

### Bài 3 — Write skew

Hai bác sĩ đều trực, hai transaction cùng đọc người còn lại rồi tự nghỉ. Xây history, nêu expected với serializable so với snapshot isolation có thể cho write skew. Đề xuất thay mô hình dữ liệu nếu cần.

### Bài 4 — Unknown commit

Một checkout commit thành công nhưng ACK mất. Thiết kế commandId, cách đối soát, business uniqueness và retry để không tạo đơn/thanh toán trùng.

### Bài 5 — SDK retry callback

Trong callback Firestore hoặc một SDK transactional khác, code gửi email ngay sau khi ghi Order. Chứng minh một kịch bản conflict làm callback chạy lại, và đề xuất outbox/email consumer idempotent.

### Bài 6 — Durability theo fault model

So sánh process crash, host power loss, mất leader vĩnh viễn và mất region. Viết câu hỏi về write concern/ACK cần hỏi trước khi tuyên bố transaction đã durable.

### Bài 7 — DynamoDB hoặc hệ tương đương

Một transaction có Update Inventory, Put Order và Put Outbox. Thiết kế test một condition fail, retry cùng token và test gần giới hạn item/bytes mà không sử dụng số giới hạn chưa được xác minh.

### Bài 8 — Cassandra batch

Một logged batch ghi hai account ở hai partition. Hãy xác định các bảo đảm cần tra cứu và giải thích vì sao không được coi đó là serializable transfer transaction chỉ vì batch tên là logged.

### Bài 9 — Redis MULTI/EXEC

Thiết kế test một command báo runtime error trong EXEC. Kết quả đó giúp phân biệt điều gì với transaction rollback kiểu SQL? Bổ sung WATCH conflict và failover test.

### Bài 10 — Read consistency

Transaction đổi A và B rồi commit, UI đọc A ở primary và B từ replica trễ. Nếu thấy A mới/B cũ, có thể kết luận DB phá atomicity không? Thiết kế phép đọc để xác minh nguồn có thẩm quyền.

### Bài 11 — Outbox khác partition

Order và Outbox được thiết kế ở hai logical partition, nhưng DB chỉ hỗ trợ atomic batch một partition. Nêu ba phương án thay đổi thiết kế và test tương ứng.

### Bài 12 — Hot SKU

Inventory SKU-A còn 100, 5.000 request cùng reserve một đơn vị. Hãy đo conflict, retries, p99, outstanding transactions và so sánh transaction trực tiếp với quota/queue.

### Bài 13 — Multi-region writers

Hai region cùng xác nhận reservation trên cùng SKU trong lúc replication trễ. Viết contract cần xác minh, test simultaneous writes, và phương án single-writer hoặc quota theo region nếu invariant toàn cầu không được bảo vệ.

### Bài 14 — Hồ sơ quyết định

Soạn một transaction contract record với các trường product/version/SDK, topology, isolation, durability, partition scope, limits, error classes, evidence và open risks cho một sản phẩm bạn đang sử dụng. Không điền giá trị dự đoán nếu chưa có tài liệu.

### Bài 15 — Đánh giá bằng chứng

Một báo cáo viết “chạy 50 transaction song song trên laptop, không thấy lỗi, vậy database bảo đảm serializable toàn cầu”. Hãy chỉ ra các lỗ hổng về fault model, read consistency, topology, history, negative controls và giới hạn kết luận.

---

**Kết luận:** Đọc hợp đồng giao dịch của NoSQL là kỹ năng chuyển một tuyên bố chung thành **bảo đảm cụ thể có phạm vi, cấu hình, lỗi và giới hạn rõ ràng**. Một transaction được gọi là “ACID” không tự bảo vệ mọi item, mọi partition, mọi region hoặc mọi dịch vụ. Muốn ứng dụng đúng, cần bắt đầu từ **bất biến**, tìm **đơn vị dữ liệu có thẩm quyền**, đọc kỹ **atomicity/isolation/durability/commit semantics**, rồi thiết kế **positive test, negative control, concurrent history, fault injection, retry/idempotency và đối soát** trên topology thật. Kết quả kiểm thử là bằng chứng có điều kiện, không phải giấy phép mở rộng hợp đồng của sản phẩm. Khi phạm vi được bảo đảm không đủ, giải pháp đúng là **đổi aggregate, dùng cơ chế transactional khác hoặc thiết kế workflow/saga/outbox**, không phải chỉ đổi tên một nhóm lệnh thành transaction.
