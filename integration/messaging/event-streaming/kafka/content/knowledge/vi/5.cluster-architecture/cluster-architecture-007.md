# Transaction coordinator và trạng thái giao dịch

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, từ topic, partition, offset, producer và consumer group đến replication, KRaft, Java/Spring Kafka, retry, ordering, giao dịch, Kafka Connect/Streams và vận hành cụm. Bài học này giải thích cách Kafka điều phối giao dịch qua **transaction coordinator**, cách trạng thái giao dịch được lưu bền vững và cách các broker hoàn tất commit hoặc abort trên nhiều partition.

Transaction coordinator là thành phần giúp Kafka đưa ra một quyết định giao dịch nhất quán dù các record được ghi vào nhiều partition. Nắm được vai trò và state machine của coordinator giúp bạn hiểu transactional producer, producer fencing, transaction marker, read_committed và giới hạn của exactly-once processing.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao Kafka cần transaction coordinator.
- Xác định broker nào đang giữ vai trò coordinator cho một transactional.id.
- Mô tả mối quan hệ giữa transaction coordinator, producer ID, producer epoch và các partition tham gia giao dịch.
- Trình bày các trạng thái chính của một giao dịch từ Ongoing đến CompleteCommit hoặc CompleteAbort.
- Giải thích cách coordinator ghi trạng thái vào topic nội bộ __transaction_state.
- Mô tả quá trình commit, abort, ghi transaction marker và khôi phục khi coordinator gặp sự cố.
- Phân biệt idempotent producer với transactional producer.
- Giải thích cách giao dịch kết hợp output records và consumer offsets để hỗ trợ consume-transform-produce.
- Nhận diện giới hạn của Kafka transaction khi nghiệp vụ còn cập nhật database hoặc hệ thống bên ngoài.

## 2. Vì sao Kafka cần transaction coordinator?

Một producer có thể gửi record đến nhiều partition, thậm chí nhiều topic. Giả sử Order Processor nhận một sự kiện thanh toán và cần thực hiện hai thay đổi:

1. Ghi event PaymentCompleted vào topic payment.events.
2. Ghi event OrderReadyToShip vào topic orders.events.

Nếu gửi hai record như hai thao tác độc lập, có thể xảy ra tình huống record thứ nhất được ghi thành công nhưng record thứ hai thất bại. Consumer downstream sẽ nhìn thấy một phần kết quả, trong khi nghiệp vụ mong muốn hai thay đổi cùng thành công hoặc cùng bị hủy.

Giao dịch Kafka cung cấp cơ chế để producer nhóm nhiều thao tác ghi thành một đơn vị commit/abort. Kafka cần một thành phần điều phối để biết:

- Giao dịch nào đang hoạt động.
- Producer nào sở hữu giao dịch.
- Những partition nào đã tham gia.
- Giao dịch đã được quyết định commit hay abort.
- Những partition nào đã nhận transaction marker.
- Phải tiếp tục khôi phục ra sao nếu broker điều phối dừng giữa chừng.

Thành phần quản lý các thông tin và quyết định này là **transaction coordinator**.

Coordinator không trực tiếp chuyển toàn bộ payload event qua nó. Producer vẫn gửi record đến leader của từng partition. Coordinator quản lý metadata giao dịch, ghi nhận quyết định và yêu cầu các partition liên quan hoàn tất quyết định đó.

## 3. Transaction coordinator nằm ở đâu trong cluster?

Kafka không có một transaction coordinator duy nhất cho toàn bộ cluster. Vai trò coordinator được phân phối giữa các broker.

Kafka dùng topic nội bộ **__transaction_state** để lưu metadata giao dịch. Topic này được chia thành nhiều partition và được cấu hình replication. Mỗi transactional.id được ánh xạ đến một partition của topic này; broker đang là leader của partition tương ứng đảm nhận vai trò transaction coordinator cho transactional.id đó.

Có thể hình dung luồng định tuyến như sau:

~~~mermaid
flowchart TD
    P[Transactional Producer] -->|transactional.id| M[Hash transactional.id]
    M --> TP[Partition của __transaction_state]
    TP --> TC[Broker leader: Transaction Coordinator]
    P -->|Gửi record| L1[Partition leader: orders.events-0]
    P -->|Gửi record| L2[Partition leader: payments.events-1]
    TC -->|WriteTxnMarkers| L1
    TC -->|WriteTxnMarkers| L2
    TC --> S[(__transaction_state)]
~~~

Các điểm cần nhớ:

- Coordinator được xác định theo transactional.id, không phải theo từng record.
- Leader của partition trong __transaction_state giữ trạng thái coordinator tương ứng.
- Khi partition của __transaction_state chuyển leader, broker mới có thể tiếp quản vai trò coordinator sau khi khôi phục state.
- Mỗi partition dữ liệu vẫn có leader riêng để nhận record từ producer và ghi transaction marker.
- Nhiều transactional.id có thể được điều phối bởi các broker khác nhau, giúp phân tán tải điều phối giao dịch.

### 3.1. Phân biệt các vai trò coordinator và leader

Tên gọi trong Kafka khá gần nhau, nhưng mỗi vai trò quản lý một phạm vi khác nhau:

| Thành phần | Trách nhiệm chính |
|---|---|
| Controller | Quản lý metadata và trạng thái điều khiển của cluster, như broker, topic, partition và replica assignment. |
| Partition leader | Nhận request ghi/đọc cho một partition và điều phối replication của partition đó. |
| Group coordinator | Quản lý thành viên consumer group, assignment, heartbeat và tiến độ offset của group. |
| Transaction coordinator | Quản lý vòng đời giao dịch theo transactional.id, quyết định commit/abort và phát transaction marker. |

Transaction coordinator không thay thế controller, group coordinator hoặc partition leader. Một broker có thể đồng thời đảm nhận nhiều vai trò trên các partition hoặc group khác nhau.

## 4. Các định danh và metadata trong giao dịch

Kafka dùng một số thông tin để liên kết producer với giao dịch và ngăn producer cũ tiếp tục ghi dữ liệu.

### 4.1. transactional.id

**transactional.id** là định danh logic ổn định của một producer có giao dịch. Producer dùng định danh này khi khởi tạo giao dịch thông qua initTransactions().

Ví dụ:

- orders-producer-instance-1
- payments-producer-instance-1
- inventory-producer-instance-2

Transactional ID giúp coordinator tìm đúng trạng thái giao dịch khi producer khởi động lại. Nó cần ổn định cho cùng một logical producer qua các lần restart, nhưng phải khác nhau giữa các producer instance đang hoạt động độc lập.

Nếu hai producer đang chạy đồng thời dùng cùng transactional.id, producer khởi tạo mới có thể làm producer cũ bị fence. Đây là hành vi bảo vệ để tránh hai phiên producer cùng điều khiển một luồng giao dịch.

Không nên tạo transactional.id ngẫu nhiên mỗi lần khởi động nếu muốn khôi phục đúng danh tính logical producer qua restart. Cũng không nên dùng cùng một ID cho nhiều instance đồng thời nếu chúng thực sự là các producer độc lập.

### 4.2. Producer ID và producer epoch

Khi producer gọi initTransactions(), Kafka cấp hoặc khôi phục một **producer ID (PID)** cùng **producer epoch**.

- Producer ID nhận diện phiên producer ở cấp giao thức.
- Producer epoch là số thế hệ giúp coordinator và partition nhận biết phiên producer mới hơn.
- Khi cùng transactional.id được khởi tạo lại, epoch có thể tăng để vô hiệu hóa producer cũ.
- Partition có thể từ chối request từ producer có epoch cũ.

Cơ chế này gọi là **producer fencing**. Nó ngăn một tiến trình cũ, bị treo hoặc mất kết nối, tiếp tục ghi dữ liệu sau khi một tiến trình mới đã tiếp quản transactional.id.

Producer ID và epoch cũng tham gia vào cơ chế idempotent producer để phát hiện request gửi lại và bảo vệ thứ tự sequence trong partition.

### 4.3. Metadata mà coordinator theo dõi

Coordinator cần duy trì các thông tin như:

- transactional.id và producer ID.
- Producer epoch hiện tại.
- Timeout của giao dịch.
- Trạng thái giao dịch.
- Danh sách topic-partition đã tham gia.
- Consumer group và offsets được gửi kèm giao dịch, nếu có.
- Quyết định commit/abort đang được hoàn tất.

Metadata này được ghi vào __transaction_state để có thể phục hồi sau khi coordinator broker gặp sự cố.

## 5. Topic nội bộ __transaction_state

__transaction_state là topic nội bộ lưu trạng thái giao dịch. Đây là log metadata của transaction coordinator, khác với topic nghiệp vụ chứa event của ứng dụng.

Coordinator ghi các thay đổi trạng thái vào topic này để quyết định giao dịch có thể được khôi phục sau khi broker restart hoặc partition leader thay đổi.

Một số đặc điểm quan trọng:

- Đây là topic nội bộ do Kafka quản lý.
- Các record chứa metadata giao dịch, không phải payload event nghiệp vụ.
- Topic được cấu hình theo mô hình log compaction để giữ trạng thái mới nhất theo transactional.id.
- Các partition của topic được replication để tăng khả năng phục hồi.
- Leader của từng partition là broker điều phối các transactional.id được ánh xạ vào partition đó.

Một số cấu hình broker liên quan:

| Cấu hình | Vai trò |
|---|---|
| transaction.state.log.replication.factor | Replication factor cho các partition của __transaction_state. |
| transaction.state.log.min.isr | Số replica đồng bộ tối thiểu cần thiết để ghi metadata giao dịch theo cấu hình. |
| transaction.max.timeout.ms | Giới hạn trên cho timeout giao dịch mà producer có thể yêu cầu. |
| transactional.id.expiration.ms | Thời gian Kafka giữ metadata transactional.id không hoạt động trước khi đủ điều kiện hết hạn. |

Giá trị cụ thể cần được lựa chọn theo số broker, yêu cầu sẵn sàng và phiên bản Kafka. Trong production, không nên tùy tiện giảm replication hoặc min ISR của transaction state log vì coordinator cần lưu trạng thái bền vững để xử lý giao dịch chính xác sau sự cố.

## 6. State machine của một giao dịch

Transaction coordinator quản lý giao dịch theo state machine. Có thể mô tả vòng đời chính bằng các trạng thái:

- **Empty:** transactional.id đã được biết nhưng chưa có giao dịch đang hoạt động.
- **Ongoing:** giao dịch đang diễn ra và có thể tiếp tục đăng ký partition, ghi record hoặc bổ sung offsets.
- **PrepareCommit:** producer yêu cầu commit; coordinator đã ghi nhận quyết định commit và đang hoàn tất marker trên các partition tham gia.
- **PrepareAbort:** producer yêu cầu abort hoặc coordinator quyết định hủy; coordinator đang hoàn tất marker abort.
- **CompleteCommit:** các partition đã được thông báo commit và giao dịch hoàn tất.
- **CompleteAbort:** các partition đã được thông báo abort và giao dịch hoàn tất.
- **Dead:** metadata giao dịch không còn được sử dụng và có thể được dọn dẹp theo vòng đời của transactional.id.

Một vòng đời đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> Empty
    Empty --> Ongoing: Partition đầu tiên được đăng ký
    Ongoing --> PrepareCommit: EndTxn commit
    Ongoing --> PrepareAbort: EndTxn abort
    PrepareCommit --> CompleteCommit: Commit markers hoàn tất
    PrepareAbort --> CompleteAbort: Abort markers hoàn tất
    CompleteCommit --> Ongoing: Giao dịch kế tiếp
    CompleteAbort --> Ongoing: Giao dịch kế tiếp
    CompleteCommit --> Dead: Hết hạn / cleanup
    CompleteAbort --> Dead: Hết hạn / cleanup
~~~

Sơ đồ là mô hình khái niệm cho các trạng thái chính; chi tiết chuyển trạng thái và retry nội bộ phụ thuộc phiên bản Kafka. Điều quan trọng là coordinator phải ghi nhận quyết định commit/abort trước khi hoàn tất marker trên các partition, nhờ đó quyết định có thể được tiếp tục sau failover.

### 6.1. Ongoing

Khi producer bắt đầu giao dịch và gửi record, các partition đích cần được đăng ký với coordinator. Coordinator chuyển trạng thái giao dịch sang Ongoing và theo dõi tập partition tham gia.

Producer có thể gửi nhiều record vào nhiều partition trong cùng giao dịch. Khi gửi tới một partition mới, producer/client thông báo cho coordinator để partition đó được đưa vào transaction metadata.

### 6.2. PrepareCommit và PrepareAbort

Khi producer gọi commitTransaction(), coordinator nhận yêu cầu kết thúc giao dịch theo hướng commit. Coordinator ghi trạng thái PrepareCommit vào transaction state log trước khi yêu cầu các partition ghi commit marker.

Khi producer gọi abortTransaction(), hoặc giao dịch cần bị hủy do timeout hay lỗi, coordinator ghi trạng thái PrepareAbort rồi yêu cầu các partition ghi abort marker.

Hai trạng thái Prepare cho biết quyết định đã được đưa ra nhưng công việc hoàn tất trên mọi partition vẫn có thể đang diễn ra.

### 6.3. CompleteCommit và CompleteAbort

Sau khi các partition liên quan đã nhận marker tương ứng, coordinator cập nhật trạng thái thành CompleteCommit hoặc CompleteAbort.

- CompleteCommit nghĩa là giao dịch được xác nhận thành công.
- CompleteAbort nghĩa là các record thuộc giao dịch bị hủy và không được consumer read_committed coi là dữ liệu đã commit.

Khi producer bắt đầu một giao dịch tiếp theo, coordinator tiếp tục quản lý vòng đời mới cho transactional.id đó.

## 7. Luồng commit transaction diễn ra như thế nào?

Giả sử producer gửi hai record trong một giao dịch:

- PaymentCompleted vào payment.events partition 0.
- OrderReadyToShip vào orders.events partition 1.

Luồng khái niệm:

1. Producer gọi initTransactions() để đăng ký hoặc khôi phục transactional.id.
2. Producer gọi beginTransaction() để bắt đầu giao dịch.
3. Khi gửi record, producer đăng ký các partition tham gia với transaction coordinator.
4. Producer gửi record trực tiếp đến leader của từng partition. Record mang metadata producer ID, epoch và thông tin transaction.
5. Producer gọi commitTransaction(), client gửi yêu cầu EndTxn với kết quả commit.
6. Coordinator ghi PrepareCommit vào __transaction_state.
7. Coordinator gửi yêu cầu WriteTxnMarkers đến leader của từng partition tham gia.
8. Mỗi partition ghi commit marker vào log của mình.
9. Khi marker đã được hoàn tất, coordinator ghi CompleteCommit.
10. Consumer cấu hình read_committed có thể đọc các record thuộc giao dịch đã commit khi chúng nằm trong phạm vi có thể đọc ổn định.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant TC as Transaction Coordinator
    participant TS as __transaction_state
    participant L1 as payment.events-0 leader
    participant L2 as orders.events-1 leader

    P->>TC: initTransactions / transactional.id
    P->>P: beginTransaction
    P->>TC: AddPartitionsToTxn
    TC->>TS: Ongoing + participating partitions
    P->>L1: Ghi PaymentCompleted
    P->>L2: Ghi OrderReadyToShip
    P->>TC: EndTxn(commit)
    TC->>TS: PrepareCommit
    TC->>L1: WriteTxnMarkers(COMMIT)
    TC->>L2: WriteTxnMarkers(COMMIT)
    L1-->>TC: Marker được ghi
    L2-->>TC: Marker được ghi
    TC->>TS: CompleteCommit
    TC-->>P: Commit hoàn tất
~~~

Coordinator không cần gom payload của hai record về một broker trung tâm. Mỗi partition leader vẫn lưu record của mình. Coordinator chỉ điều phối metadata và quyết định chung để các partition biết giao dịch đã commit.

## 8. Luồng abort transaction

Nếu producer gặp lỗi trước khi commit hoặc nghiệp vụ quyết định hủy, producer gọi abortTransaction().

Luồng khái niệm:

1. Producer gửi EndTxn với kết quả abort.
2. Coordinator ghi PrepareAbort vào __transaction_state.
3. Coordinator gửi WriteTxnMarkers với loại ABORT đến từng partition tham gia.
4. Các partition ghi abort marker.
5. Coordinator cập nhật CompleteAbort.
6. Consumer read_committed bỏ qua các record thuộc giao dịch đã abort.

Record đã được ghi vào partition trước khi abort không nhất thiết bị xóa vật lý khỏi log ngay lập tức. Kafka dùng marker và metadata transaction để xác định record nào thuộc giao dịch đã bị hủy. Consumer read_uncommitted có thể nhìn thấy dữ liệu transactional chưa commit hoặc đã abort. Consumer read_committed vẫn đọc record không thuộc transaction và record thuộc transaction đã commit, nhưng loại bỏ record của transaction bị abort và không đọc vượt qua LSO khi còn transaction chưa hoàn tất.

Đây là lý do không nên dùng read_uncommitted nếu ứng dụng cần chỉ xử lý kết quả giao dịch đã xác nhận.

## 9. Transaction marker và Last Stable Offset

Mỗi partition tham gia giao dịch cần biết kết quả giao dịch. Coordinator gửi transaction marker để partition ghi nhận commit hoặc abort.

Marker là control record đặc biệt trong log, không phải event nghiệp vụ mà ứng dụng đọc như một record thông thường.

Một khái niệm quan trọng liên quan đến consumer read_committed là **Last Stable Offset (LSO)**. LSO biểu thị ranh giới mà consumer read_committed có thể đọc an toàn khi còn giao dịch chưa hoàn tất trong partition.

Nếu partition có một giao dịch đang mở ở offset 100, consumer read_committed không thể đọc vượt qua ranh giới giao dịch đó cho đến khi giao dịch được commit hoặc abort. Điều này ngăn consumer nhìn thấy các record phía sau trong một trạng thái chưa ổn định so với giao dịch đang mở.

Có thể hình dung:

~~~text
Partition 0:
Offset 98  -> Record đã commit
Offset 99  -> Record đã commit
Offset 100 -> Record thuộc transaction T1 đang mở
Offset 101 -> Record khác
Offset 102 -> Record khác

LSO = 100
~~~

Trong ví dụ khái niệm, consumer read_committed chỉ đọc đến trước ranh giới LSO. Khi T1 được commit hoặc abort và marker được ghi, LSO có thể tiến lên để consumer tiếp tục đọc các record phía sau.

Giao dịch kéo dài quá lâu vì thế có thể làm tăng độ trễ quan sát dữ liệu của consumer read_committed trên partition liên quan. Cần giữ thời gian transaction ngắn và theo dõi transaction timeout.

## 10. Producer fencing và vai trò của epoch

Giả sử một ứng dụng producer bị treo nhưng vẫn còn khả năng gửi request sau khi mất kết nối. Một instance mới khởi động với cùng transactional.id và tiếp quản luồng xử lý.

Nếu Kafka chấp nhận cả hai producer, chúng có thể ghi dữ liệu cạnh tranh trong cùng một danh tính giao dịch. Producer epoch giải quyết tình huống này:

1. Instance mới gọi initTransactions() với cùng transactional.id.
2. Coordinator cấp hoặc khôi phục producer ID và tăng epoch.
3. Request từ producer cũ mang epoch thấp hơn bị từ chối.
4. Producer cũ nhận lỗi fencing và không thể tiếp tục giao dịch.

Một số lỗi thường liên quan:

- **ProducerFencedException:** producer đã bị một producer khác với cùng transactional.id thay thế.
- **InvalidProducerEpochException:** epoch không còn hợp lệ đối với trạng thái partition/coordinator.
- **TimeoutException:** giao dịch hoặc request vượt quá thời gian chờ.
- **NotEnoughReplicasException:** không đủ replica đồng bộ để đáp ứng điều kiện ghi theo cấu hình.
- **CoordinatorNotAvailableException:** coordinator tạm thời không thể phục vụ request.

Ứng dụng cần phân loại lỗi có thể retry và lỗi fatal. Khi producer đã bị fence, không nên tiếp tục dùng instance đó; hãy đóng nó và tạo producer mới với danh tính phù hợp.

## 11. Coordinator failover và phục hồi trạng thái

Transaction coordinator là vai trò gắn với leader của một partition trong __transaction_state. Nếu broker đang làm coordinator dừng hoạt động, Kafka có thể bầu leader mới cho partition metadata đó nếu còn đủ replica đáp ứng điều kiện.

Broker mới tiếp quản thực hiện các bước khái quát:

1. Nhận leadership của partition __transaction_state tương ứng.
2. Đọc lại các record metadata giao dịch từ transaction state log.
3. Khôi phục trạng thái transactional.id, producer ID, epoch và danh sách partition tham gia.
4. Xác định giao dịch đang ở trạng thái nào.
5. Nếu giao dịch ở PrepareCommit hoặc PrepareAbort, tiếp tục hoàn tất transaction marker tương ứng.
6. Phục vụ request mới sau khi coordinator sẵn sàng.

Nếu coordinator gặp sự cố sau khi đã ghi PrepareCommit nhưng chưa gửi marker đến tất cả partition, coordinator mới có thể tiếp tục quyết định commit đã được ghi bền vững. Tương tự với PrepareAbort.

Producer có thể nhận lỗi coordinator tạm thời và cần làm mới metadata hoặc gửi lại request theo cơ chế retry của Kafka client. Không nên tự suy luận rằng transaction đã commit chỉ vì một số record đã được gửi thành công; trạng thái cuối cùng phụ thuộc kết quả giao dịch.

Khả năng phục hồi phụ thuộc replication và ISR của __transaction_state cũng như các partition dữ liệu tham gia. Nếu metadata transaction không còn đủ replica hợp lệ hoặc partition dữ liệu mất khả năng ghi, giao dịch có thể bị trì hoãn hoặc thất bại.

## 12. Idempotent producer khác transactional producer như thế nào?

Hai tính năng này liên quan nhưng giải quyết phạm vi khác nhau.

| Cơ chế | Mục đích | Phạm vi |
|---|---|---|
| Idempotent producer | Phát hiện retry trùng từ producer và tránh ghi trùng do request được gửi lại. | Theo producer ID, epoch, sequence và partition. |
| Transactional producer | Nhóm nhiều lần ghi và có thể kết hợp consumer offsets thành một đơn vị commit/abort. | Nhiều partition và topic trong một transaction. |

Idempotent producer giúp tránh duplicate do retry ở tầng producer. Nó không tự làm cho nhiều record trên nhiều partition trở thành một giao dịch nguyên tử.

Transactional producer sử dụng transaction coordinator, transaction marker và metadata giao dịch để consumer read_committed nhìn thấy kết quả commit/abort phù hợp.

Khi cấu hình transactional.id, Kafka producer sử dụng cơ chế idempotence phù hợp. Trong ứng dụng hiện đại, nên cấu hình rõ enable.idempotence và các thuộc tính producer liên quan theo tài liệu phiên bản đang dùng.

## 13. Kết hợp output records và consumer offsets

Một trường hợp quan trọng là consume-transform-produce:

- Consumer đọc event đầu vào từ orders.events.
- Ứng dụng tính toán hoặc biến đổi dữ liệu.
- Producer ghi event kết quả vào shipments.events.
- Consumer group cần commit offset đầu vào để không xử lý lại event đã hoàn thành.

Nếu output được commit nhưng input offset chưa commit, consumer restart có thể đọc lại input và tạo output trùng. Nếu input offset được commit trước khi output commit, ứng dụng có thể mất output sau restart.

Kafka transaction hỗ trợ đưa output records và input offsets vào cùng một transaction:

1. Consumer đọc một batch input và xác định offset tiếp theo cho từng partition.
2. Producer bắt đầu transaction.
3. Producer ghi output records.
4. Producer gửi offsets của consumer group vào transaction bằng sendOffsetsToTransaction().
5. Producer commit transaction.
6. Kafka hoàn tất output records và consumer offsets như một đơn vị giao dịch.

Mã minh họa với Java Kafka Client:

~~~java
producer.beginTransaction();

try {
    producer.send(
        new ProducerRecord<>(
            "shipments.events",
            orderId,
            shipmentEvent
        )
    );

    producer.sendOffsetsToTransaction(
        offsetsToCommit,
        consumer.groupMetadata()
    );

    producer.commitTransaction();
} catch (Exception exception) {
    producer.abortTransaction();
    throw new RuntimeException("Transaction failed", exception);
}
~~~

Trong ví dụ, offsetsToCommit là Map<TopicPartition, OffsetAndMetadata> chứa offset tiếp theo cần đọc của từng partition, không phải offset của record cuối cùng đã xử lý.

Để consumer chỉ nhận output của giao dịch đã commit, cấu hình isolation.level là read_committed. Nếu consumer dùng read_uncommitted, nó có thể đọc cả output thuộc transaction bị abort.

Cơ chế này tạo ra exactly-once processing trong phạm vi luồng dữ liệu Kafka được tham gia transaction. Nó không tự bao gồm thao tác cập nhật database hoặc gọi HTTP API bên ngoài Kafka.

## 14. Ví dụ transactional producer bằng Java

Ví dụ dưới đây gửi hai record đến hai topic trong cùng một transaction. Nếu mọi thao tác thành công, producer commit; nếu có lỗi, producer yêu cầu abort.

~~~java
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.KafkaException;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

public class TransactionalOrderPublisher {

    public static void main(String[] args) {
        Properties properties = new Properties();

        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(
            ProducerConfig.TRANSACTIONAL_ID_CONFIG,
            "orders-publisher-instance-1"
        );
        properties.put(
            ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
            "true"
        );

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(properties)) {

            producer.initTransactions();
            producer.beginTransaction();

            try {
                producer.send(
                    new ProducerRecord<>(
                        "payment.events",
                        "ORD-1001",
                        "PaymentCompleted"
                    )
                ).get();

                producer.send(
                    new ProducerRecord<>(
                        "orders.events",
                        "ORD-1001",
                        "OrderReadyToShip"
                    )
                ).get();

                producer.commitTransaction();

            } catch (Exception exception) {
                try {
                    producer.abortTransaction();
                } catch (KafkaException abortException) {
                    exception.addSuppressed(abortException);
                }

                throw new RuntimeException(
                    "Could not complete Kafka transaction",
                    exception
                );
            }
        } catch (Exception exception) {
            exception.printStackTrace();
        }
    }
}
~~~

Các bước quan trọng:

- transactional.id được cấu hình ổn định cho logical producer instance.
- initTransactions() đăng ký producer với coordinator và khôi phục trạng thái cần thiết.
- beginTransaction() mở transaction mới.
- send() ghi các record vào partition tương ứng.
- commitTransaction() yêu cầu coordinator commit toàn bộ giao dịch.
- abortTransaction() yêu cầu coordinator hủy giao dịch nếu xử lý thất bại.

Đây là ví dụ học tập. Ứng dụng production cần phân loại lỗi fatal như producer fencing, quản lý retry, timeout, shutdown và trạng thái producer sau khi abort. Không được tiếp tục dùng producer đã bị fence. Việc gọi get() trong ví dụ giúp minh họa lỗi gửi có thể được phát hiện trước khi commit; chiến lược xử lý thực tế cần cân nhắc throughput và batch.

## 15. Sử dụng transaction trong Spring Kafka

Spring Kafka cung cấp cơ chế transaction thông qua ProducerFactory, KafkaTemplate và KafkaTransactionManager.

Một ProducerFactory có thể được cấu hình transaction ID prefix. Với nhiều producer instance đồng thời, factory cần tạo suffix duy nhất cho từng producer để tránh trùng transactional.id.

Ví dụ ý tưởng cấu hình:

~~~java
@Bean
public ProducerFactory<String, String> producerFactory() {
    Map<String, Object> properties = new HashMap<>();

    properties.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
    );
    properties.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
    );
    properties.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
    );

    DefaultKafkaProducerFactory<String, String> factory =
        new DefaultKafkaProducerFactory<>(properties);

    factory.setTransactionIdPrefix("orders-tx-");
    return factory;
}
~~~

KafkaTemplate có thể thực hiện một nhóm lệnh gửi trong transaction:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send(
        "payment.events",
        "ORD-1001",
        "PaymentCompleted"
    );

    operations.send(
        "orders.events",
        "ORD-1001",
        "OrderReadyToShip"
    );

    return true;
});
~~~

Spring Kafka sẽ quản lý vòng đời transaction cho callback này. Nếu callback hoàn thành bình thường, transaction được commit; nếu callback ném exception, transaction được rollback/abort theo cơ chế framework.

Với listener container chạy transaction, Spring Kafka có thể kết hợp việc xử lý record và commit consumer offsets vào transaction Kafka. Cần cấu hình đúng transaction manager và listener container theo phiên bản Spring Kafka đang sử dụng. Không nên chỉ thêm annotation @Transactional mà không hiểu transaction manager nào đang quản lý tài nguyên.

## 16. Timeout và các giới hạn vận hành

Một transaction không nên kéo dài tùy ý. Kafka có các giới hạn timeout để coordinator có thể xử lý giao dịch bị treo.

Các thuộc tính cần quan tâm:

- **transaction.timeout.ms:** thời gian producer yêu cầu cho một transaction.
- **transaction.max.timeout.ms:** giới hạn trên mà broker cho phép.
- **transactional.id.expiration.ms:** thời gian metadata transactional.id không hoạt động trước khi đủ điều kiện hết hạn.
- **request.timeout.ms:** thời gian chờ một request client.
- **delivery.timeout.ms:** giới hạn tổng thời gian gửi record trước khi producer báo lỗi delivery.

Nếu transaction mở quá lâu, coordinator có thể abort giao dịch theo timeout. Các record thuộc transaction chưa hoàn tất có thể làm LSO đứng lại, khiến consumer read_committed chậm nhìn thấy record phía sau trong partition.

Một số nguyên tắc vận hành:

1. Giữ transaction ngắn, tránh thực hiện công việc ngoài Kafka lâu bên trong transaction.
2. Không gọi dịch vụ HTTP chậm hoặc chờ thao tác người dùng giữa beginTransaction và commitTransaction.
3. Chọn timeout phù hợp với batch size, độ trễ broker và thời gian xử lý.
4. Dùng transactional.id ổn định và duy nhất giữa các producer instance đồng thời.
5. Theo dõi tỷ lệ transaction abort, transaction timeout và coordinator errors.
6. Bảo đảm __transaction_state có replication và ISR phù hợp.
7. Theo dõi LSO và consumer lag khi dùng read_committed.
8. Phân loại lỗi retriable và fatal; producer bị fence phải được thay thế.

## 17. Những điều Kafka transaction không tự giải quyết

Kafka transaction bảo đảm tính nguyên tử trong phạm vi các thao tác Kafka được đưa vào transaction. Nó không tự mở rộng thành một distributed transaction cho mọi hệ thống bên ngoài.

Ví dụ, ứng dụng:

1. Ghi một đơn hàng vào PostgreSQL.
2. Gửi event OrderCreated đến Kafka.
3. Commit Kafka transaction.

Nếu database commit thành công nhưng Kafka transaction thất bại, hai hệ thống vẫn có thể lệch nhau. Kafka coordinator không thể rollback transaction database thông thường.

Với bài toán ghi database và phát event, hãy cân nhắc transactional outbox hoặc CDC:

- Ghi dữ liệu nghiệp vụ và outbox record trong cùng transaction database.
- Một relay hoặc CDC connector đọc outbox và phát event lên Kafka.
- Consumer xử lý event idempotent để chịu được việc relay gửi lại.

Tương tự, nếu consumer gọi HTTP API hoặc cập nhật một hệ thống ngoài Kafka, thao tác đó không tự động nằm trong transaction Kafka. Cần dùng idempotency key, outbox/inbox, saga hoặc cơ chế phối hợp nghiệp vụ phù hợp.

## 18. Chẩn đoán transaction coordinator

Khi giao dịch lỗi, hãy xác định lỗi nằm ở producer, coordinator, transaction state log hay partition dữ liệu.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| CoordinatorNotAvailableException | Coordinator đang chuyển leader hoặc chưa sẵn sàng sau failover. | Kiểm tra broker, leader của __transaction_state và log coordinator. |
| ProducerFencedException | Một producer khác đã khởi tạo cùng transactional.id và tăng epoch. | Kiểm tra transactional.id có bị dùng trùng giữa các instance không. |
| Transaction timed out | Producer giữ transaction quá lâu hoặc bị treo giữa các thao tác. | Kiểm tra transaction.timeout.ms, thời gian xử lý và các request bị chậm. |
| NotEnoughReplicasException | Partition dữ liệu hoặc transaction state log không đủ ISR theo yêu cầu ghi. | Kiểm tra replica, ISR, broker availability và min ISR. |
| Consumer read_committed bị chậm | Giao dịch chưa kết thúc đang giữ LSO ở partition. | Kiểm tra transaction duration, producer lỗi và trạng thái coordinator. |
| Commit/abort retry nhiều lần | Coordinator hoặc partition leader đang gặp lỗi tạm thời. | Kiểm tra broker log, network, leader changes và transaction metrics. |

Các tín hiệu quan sát hữu ích gồm:

- Số lượng transaction bắt đầu, commit và abort.
- Transaction duration và số transaction timeout.
- Coordinator request latency và lỗi coordinator.
- Tình trạng leader/ISR của các partition thuộc __transaction_state.
- Under-replicated partitions và offline partitions.
- Consumer lag và Last Stable Offset khi sử dụng read_committed.
- Producer fencing hoặc lỗi epoch.

Khi coordinator failover, cần cho client đủ thời gian làm mới metadata và retry theo chính sách của Kafka client. Không nên tự động tạo transactional.id mới cho mỗi lần lỗi vì điều đó có thể làm mất liên kết với trạng thái logical producer cũ.

## 19. Bài tập thực hành

### Bài 1: Gửi nhiều record trong một transaction

Tạo hai topic payment.events và orders.events. Viết một transactional producer gửi một record đến mỗi topic trong cùng một transaction.

- Chạy producer và xác nhận hai record được commit.
- Thử tạo lỗi trước commit và gọi abortTransaction().
- Dùng hai consumer group có isolation.level=read_committed để đọc hai topic.
- Xác nhận consumer không nhìn thấy record thuộc transaction đã abort.

### Bài 2: Quan sát read_committed và read_uncommitted

Tạo một producer mở transaction, gửi một record rồi giữ transaction ở trạng thái chưa commit.

- Mở consumer với isolation.level=read_uncommitted.
- Mở consumer khác với isolation.level=read_committed.
- Quan sát khác biệt trong dữ liệu mà hai consumer đọc được.
- Commit hoặc abort transaction và quan sát consumer read_committed tiếp tục đọc.

### Bài 3: Producer fencing

- Khởi động một producer với transactional.id cố định.
- Khởi động instance thứ hai dùng cùng transactional.id.
- Quan sát instance đầu tiên nhận lỗi fencing khi tiếp tục thao tác.
- Giải thích vai trò của producer epoch trong việc bảo vệ transaction.

### Bài 4: Consume-transform-produce

- Consumer đọc event từ orders.events.
- Producer ghi event kết quả sang shipments.events.
- Đưa offset input vào transaction bằng sendOffsetsToTransaction().
- Cấu hình consumer downstream với read_committed.
- Kiểm tra rằng output và offset input được commit như một đơn vị Kafka transaction.

## 20. Câu hỏi tự kiểm tra

1. Transaction coordinator được xác định dựa trên thông tin nào?
2. Vì sao Kafka lưu transaction metadata trong __transaction_state?
3. Producer ID và producer epoch có vai trò gì?
4. Producer fencing bảo vệ hệ thống khỏi tình huống nào?
5. Coordinator làm gì khi nhận EndTxn(commit)?
6. Vì sao cần các trạng thái PrepareCommit và PrepareAbort?
7. Transaction marker được ghi ở đâu và có phải event nghiệp vụ không?
8. Last Stable Offset ảnh hưởng thế nào đến consumer read_committed?
9. Idempotent producer khác transactional producer ở phạm vi bảo đảm nào?
10. Làm sao đưa output records và consumer offsets vào cùng transaction?
11. Coordinator failover khôi phục giao dịch đang ở PrepareCommit như thế nào?
12. Vì sao Kafka transaction không tự bảo đảm atomicity giữa Kafka và PostgreSQL?

## Kết luận

Transaction coordinator là thành phần quản lý vòng đời giao dịch Kafka theo transactional.id. Coordinator lưu trạng thái vào __transaction_state, theo dõi producer ID/epoch và các partition tham gia, sau đó điều phối commit hoặc abort bằng transaction marker.

State machine với Ongoing, PrepareCommit, PrepareAbort, CompleteCommit và CompleteAbort giúp coordinator có thể phục hồi quyết định giao dịch khi broker gặp sự cố. Producer fencing ngăn phiên producer cũ tiếp tục ghi, còn read_committed và Last Stable Offset giúp consumer chỉ quan sát dữ liệu giao dịch đã commit theo ranh giới ổn định.

Kafka transaction có thể kết hợp output records và consumer offsets để hỗ trợ consume-transform-produce exactly-once trong phạm vi Kafka. Khi nghiệp vụ còn cập nhật database hoặc gọi hệ thống ngoài, cần thêm outbox, inbox, idempotency hoặc saga để phối hợp nhất quán.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Transaction coordinator | Broker quản lý metadata và quyết định commit/abort cho transactional.id. |
| transactional.id | Định danh ổn định của logical transactional producer. |
| Producer ID | Định danh producer ở cấp giao thức Kafka. |
| Producer epoch | Thế hệ producer dùng để fence phiên cũ. |
| __transaction_state | Topic nội bộ lưu metadata và trạng thái giao dịch. |
| Ongoing | Giao dịch đang hoạt động. |
| PrepareCommit | Đã quyết định commit và đang ghi commit marker. |
| PrepareAbort | Đã quyết định abort và đang ghi abort marker. |
| Transaction marker | Control record đánh dấu kết quả commit/abort trên partition. |
| Last Stable Offset | Ranh giới đọc ổn định của consumer read_committed. |
| Producer fencing | Cơ chế vô hiệu hóa producer cũ có epoch thấp hơn. |
| read_committed | Isolation level trả về record không thuộc transaction hoặc thuộc transaction đã commit; loại bỏ record thuộc transaction bị abort. |
| sendOffsetsToTransaction | Đưa consumer offsets vào cùng Kafka transaction với output records. |

