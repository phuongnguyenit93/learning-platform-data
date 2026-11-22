# Zombie fencing

Trong kiến trúc Kafka sử dụng transaction, **zombie** là producer hoặc consumer instance đã mất quyền sở hữu một công việc nhưng vẫn còn hoạt động, hoặc bất ngờ tiếp tục chạy sau khi bị treo, mất mạng hay tạm dừng quá lâu. Nếu zombie vẫn được phép ghi kết quả và commit offset cũ, hai tiến trình có thể cùng hoàn thành một record, làm sai tiến độ consumer group và tạo duplicate.

**Zombie fencing** là cơ chế ngăn một instance đã lỗi thời hoàn tất thao tác không còn hợp lệ. Kafka có hai lớp cơ chế đáng phân biệt: **producer fencing** dùng `transactional.id` cùng producer epoch, và **consumer zombie fencing** dùng thông tin membership của consumer group khi offset được gửi vào Kafka transaction. Chúng giúp xây dựng *exactly-once processing semantics* (EOS) cho luồng đọc Kafka rồi ghi kết quả trở lại Kafka.

Trong Spring Kafka, các cơ chế này phát huy hiệu quả khi producer factory, Kafka transaction manager, transactional listener container và consumer downstream được cấu hình đúng. Chúng không làm side effect ngoài Kafka như ghi database, gọi HTTP hay gửi email trở thành exactly-once. Bài học này giải thích ranh giới, cấu hình và cách điều tra các sự cố zombie trong production.

## 1. Zombie xuất hiện như thế nào?

Giả sử topic `payments.commands` có partition 0 được gán cho consumer A trong group `payment-worker`. A nhận offset 100 rồi bắt đầu xử lý. Do stop-the-world GC hoặc một HTTP call bị treo, A không thể tiếp tục poll theo đúng deadline.

Coordinator phát hiện A không còn tiến triển; sau quá trình thay đổi membership, partition 0 được giao cho consumer B. B đọc record chưa commit và bắt đầu xử lý. Khi A hồi phục, code cũ vẫn có thể tiếp tục chạy, mặc dù coordinator không còn coi A là chủ sở hữu partition.

~~~text
T1: Partition 0 -> consumer A, generation G1
    A poll offset 100, bắt đầu xử lý

T2: A bị treo hoặc không poll đúng hạn
    Group rebalance -> partition 0 sang B, generation G2
    B xử lý offset 100 từ committed offset còn hiệu lực

T3: A hồi phục
    A cố publish output rồi commit offset nguồn bằng ngữ cảnh cũ
    A là zombie: đã mất quyền nhưng vẫn thực hiện code
~~~

Các tình huống thường tạo zombie:

- Consumer vượt `max.poll.interval.ms` vì xử lý lâu, backoff blocking hoặc deadlock.
- JVM bị pause dài rồi hồi phục sau khi group đã rebalance.
- Network partition khiến tiến trình cũ chưa kịp biết quyền sở hữu partition đã thay đổi.
- Rolling deployment khởi động process mới trước khi process cũ dừng hoàn toàn.
- Producer cũ mất kết nối rồi tiếp tục sử dụng transactional identity đã được một producer mới thay thế.
- Xử lý bất đồng bộ giữ công việc cũ trong thread pool sau khi container đã revoke partition.

Kafka group coordinator có thể quản lý một owner hợp lệ tại một thời điểm, nhưng không thể ngay lập tức dừng mọi CPU thread của ứng dụng cũ. Fencing tạo hàng rào an toàn ở **bước giao thức commit**, nơi tiến trình buộc phải chứng minh transaction/membership còn hợp lệ.

## 2. Ba loại fencing dễ bị nhầm

| Cơ chế | Căn cứ kiểm tra | Vấn đề giải quyết |
|---|---|---|
| Producer epoch fencing | `transactional.id` cùng producer ID/epoch | Producer cũ cố ghi/commit khi producer mới đã thay thế cùng identity. |
| Consumer zombie fencing trong EOS | Consumer group metadata khi offsets tham gia Kafka transaction | Consumer đã mất membership/generation cố commit kết quả của assignment cũ. |
| Static member fencing | `group.instance.id` trong consumer group | Hai consumer cùng tuyên bố một static instance ID. |

Các thuộc tính này có phạm vi khác nhau:

- `transactional.id` định danh **producer transactional** với Kafka transaction coordinator.
- `transactionIdPrefix` là namespace để Spring Kafka producer factory tạo các `transactional.id` thực tế.
- `group.id` định danh consumer group.
- `group.instance.id` định danh một *static consumer member* trong group.
- Consumer group generation/member metadata biểu diễn quyền tham gia group tại thời điểm giao thức commit offsets.

Không thể chỉ đặt `group.instance.id` rồi cho rằng đã có exactly-once Kafka transaction. Cũng không thể lấy `transactionIdPrefix` thay thế group metadata để phát hiện mọi zombie sau rebalance.

## 3. Producer fencing: transactional.id và producer epoch

Kafka producer transactional khởi tạo qua `initTransactions()` với một `transactional.id`. Transaction coordinator quản lý producer ID và epoch của danh tính đó. Khi một producer mới khởi tạo hợp lệ cùng transactional ID, broker có thể tăng epoch và làm producer đời cũ không còn quyền thao tác transaction.

~~~mermaid
sequenceDiagram
    participant P1 as Producer P1 cũ
    participant K as Kafka Transaction Coordinator
    participant P2 as Producer P2 mới
    P1->>K: initTransactions (transactional.id=X)
    K-->>P1: Producer epoch E1
    P1->>K: beginTransaction
    Note over P1: P1 bị treo
    P2->>K: initTransactions (transactional.id=X)
    K-->>P2: Producer epoch E2
    Note over K: Epoch E1 không còn hợp lệ
    P1->>K: commitTransaction với E1
    K-->>P1: Producer fenced / epoch invalid
    P2->>K: commit transaction theo E2
~~~

Sơ đồ chỉ mô tả nguyên tắc; chi tiết producer ID, epoch và trạng thái transaction do Kafka client/broker điều phối. P1 có thể nhận `ProducerFencedException` hoặc một lỗi về producer epoch tùy thao tác và phiên bản.

Fencing hữu ích khi producer mới **thay thế producer logic cũ**. Nhưng nếu hai replica hợp lệ hoạt động độc lập mà bị cấu hình cùng một transactional ID, chúng có thể liên tục fence nhau. Đó là lỗi identity chứ không phải một chiến lược scale.

### Không dùng chung prefix giữa các instance

Spring Kafka thường ghép `transactionIdPrefix` và suffix do `DefaultKafkaProducerFactory` quản lý. Nếu hai instance cùng dùng một prefix và cùng sinh suffix tương ứng, transactional ID thực tế có thể trùng.

~~~text
Sai khi chạy đồng thời:
  Pod A: transactionIdPrefix = orders-tx-
  Pod B: transactionIdPrefix = orders-tx-

Đúng hơn:
  Pod A: transactionIdPrefix = prod-orders-pod-a-tx-
  Pod B: transactionIdPrefix = prod-orders-pod-b-tx-
~~~

Với môi trường nhiều replica, prefix nên bao gồm service, environment và instance identity đủ duy nhất. Không đặt prefix mới cho từng message; để producer factory quản lý suffix/cache theo vòng đời của nó.

**Quan trọng:** trong EOS V2, khi A và B dùng transactional ID khác nhau, producer epoch fencing giữa hai ID này **không tự** ngăn A commit offset cũ. Cần cơ chế group metadata ở phần tiếp theo.

## 4. Zombie consumer sau rebalance

Trong luồng *consume–transform–produce*, một consumer nhận input record, publish kết quả Kafka rồi commit input offset. Nếu offset được commit độc lập với output, một sự cố có thể tạo duplicate hoặc khiến kết quả bị bỏ qua.

Với transactional listener container, Spring Kafka có thể đưa output Kafka và input offset vào cùng transaction. Khi gửi offset vào transaction, Kafka cần biết **consumer group metadata** để xác định member có còn hợp lệ không.

Ví dụ, A sở hữu partition 0 ở generation G1. Trong lúc A bị treo, B nhận partition sau rebalance ở G2. Nếu A cố kết thúc transaction với group metadata đã lỗi thời, Kafka có thể từ chối transactional offset commit; output thuộc transaction thất bại không được xem là committed.

~~~mermaid
sequenceDiagram
    participant A as Consumer A, generation G1
    participant G as Group Coordinator
    participant B as Consumer B, generation G2
    participant T as Transaction Coordinator
    A->>G: JoinGroup, nhận partition 0
    A->>A: Poll offset 100, bắt đầu xử lý
    Note over A: Dừng poll quá lâu
    G-->>B: Rebalance, gán partition 0
    B->>B: Xử lý offset 100 trong transaction mới
    A->>T: sendOffsetsToTransaction với metadata G1
    T->>G: Kiểm tra quyền commit của group member
    G-->>T: A/G1 không còn hợp lệ
    T-->>A: Từ chối transactional commit
    B->>T: Commit với metadata G2 hợp lệ
~~~

Đây là sơ đồ logic; thông điệp nội bộ giữa coordinators tùy phiên bản Kafka. Điều quan trọng là **offset được xác thực theo membership**, chứ không chỉ dựa trên tên group hoặc một giá trị offset.

### Fencing không nhất thiết ngăn code cũ chạy

A có thể vẫn hoàn tất một phép tính hoặc một cuộc gọi API trước khi nhận lỗi fencing. Kafka chỉ bảo vệ những thao tác thuộc giao thức Kafka transaction/membership. Vì vậy, không được dùng fencing làm cơ chế ngăn mọi tác động bên ngoài.

## 5. EOS V2 và KIP-447

KIP-447 mở rộng giao thức Kafka để transactional offset commit sử dụng consumer group metadata và hỗ trợ fencing các consumer zombie sau rebalance. Spring Kafka hỗ trợ EOS V2 ở những phiên bản tương ứng; từ Spring Kafka 3.0, chỉ còn EOS V2 thay cho EOS V1 của các phiên bản cũ. EOS V2 cần broker Kafka đủ mới để hỗ trợ cơ chế này (Kafka 2.5 trở lên).

Điểm thiết kế quan trọng:

1. Producer transaction vẫn có `transactional.id` và epoch.
2. Consumer group cung cấp metadata về member/generation.
3. Transactional producer gửi offsets vào transaction cùng metadata group.
4. Coordinator xác thực tính hợp lệ của membership trước khi cho transaction commit offset.
5. Một zombie với metadata cũ không thể được mặc nhiên coi là member còn quyền commit.

EOS V2 cho phép sử dụng mô hình transactional ID theo instance thay vì cần một định danh producer riêng cho từng group/topic/partition như một số cách triển khai cũ. Trong Spring Kafka, mỗi application instance vẫn cần namespace `transactionIdPrefix` độc lập khi các producer có thể hoạt động cùng lúc.

Không hiểu EOS V2 là \"Kafka sẽ không bao giờ giao lại record\". Kafka có thể giao lại khi transaction abort, rebalance hoặc process crash. EOS ở đây liên quan đến **kết quả Kafka committed** và **offset phối hợp**, không phải số lần method listener đã được gọi.

## 6. Luồng commit đúng trong Spring Kafka

Một transactional listener cho bài toán đọc lệnh rồi phát sự kiện kết quả hoạt động theo trình tự:

~~~mermaid
flowchart TD
    A[Container poll input record] --> B[Bắt đầu Kafka transaction]
    B --> C[Listener xử lý]
    C --> D[KafkaTemplate publish output trong transaction]
    D --> E{Listener hoàn tất thành công?}
    E -->|Có| F[Container gửi input offsets và group metadata vào transaction]
    F --> G{Offset commit hợp lệ?}
    G -->|Có| H[Commit Kafka transaction]
    G -->|Không| I[Abort / transaction failure]
    E -->|Không| I
    I --> J[AfterRollbackProcessor retry hoặc recovery]
~~~

Transaction có thể bao gồm output record từ nhiều partition/topic. Khi transaction commit, consumer downstream có `isolation.level=read_committed` sẽ nhìn thấy những output đã commit. Khi transaction abort, downstream ở chế độ `read_committed` không được xử lý record output như một transaction thành công.

Consumer `read_uncommitted` không có bảo đảm này: có thể thấy transactional records chưa commit hoặc đã abort theo ngữ nghĩa Kafka. Vì vậy, một pipeline tuy có producer transaction nhưng downstream đọc `read_uncommitted` sẽ không đạt bảo đảm kết quả committed như kỳ vọng.

### Offset được commit là vị trí tiếp theo

Nếu record offset 100 đã xử lý thành công, container đưa offset 101 vào transaction cho partition đó. Không nhầm record offset với committed offset tiếp theo.

Nếu transaction abort, offset 101 không được commit như một giao dịch thành công. Khi member hợp lệ tiếp tục, record nguồn có thể được giao lại từ committed offset trước đó.

## 7. Cấu hình transaction trong Spring Boot

Ví dụ một service Spring Kafka dùng transactional producer và listener:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.internal:9092
    producer:
      transaction-id-prefix: prod-orders-INSTANCE_ID-tx-
      properties:
        "[acks]": all
    consumer:
      group-id: orders-transformer
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
    listener:
      ack-mode: record
      concurrency: 3
~~~

`INSTANCE_ID` là placeholder cần được thay bằng identity thật, duy nhất trên các application instance/producer factory có thể hoạt động đồng thời. Không dùng nguyên một prefix cố định cho tất cả replica.

Khi các điều kiện auto-configuration phù hợp, Spring Boot có thể cấu hình `KafkaTransactionManager` từ producer factory transactional. Tuy nhiên, cần xác nhận **listener container factory hiệu lực** thực sự sử dụng manager đó. Nếu có custom factory, không được suy luận rằng prefix tự làm mọi listener transactional.

Ví dụ listener:

~~~java
@KafkaListener(
        topics = "orders.commands",
        groupId = "orders-transformer",
        containerFactory = "transactionalListenerFactory")
public void transform(ConsumerRecord<String, OrderCommand> record) {
    OrderResultEvent result =
            orderTransformer.transform(record.value());

    resultKafkaTemplate.send(
            "orders.results",
            record.key(),
            result);
}
~~~

Đoạn code giả định:

- Bean `transactionalListenerFactory` đã được cấu hình Kafka transaction manager phù hợp.
- `resultKafkaTemplate` sử dụng producer factory có khả năng tham gia transaction của container.
- Key/value serializers, topic và ACL được cấu hình đúng.
- Listener ném exception ra container khi một bước bắt buộc thất bại.

Container quản lý việc đưa offset vào transaction; không tự gọi `commitSync()` từ listener hoặc từ worker thread khác để cố vượt qua lỗi.

### Cấu hình producer factory bằng Java

Nếu ứng dụng không dựa hoàn toàn vào auto-configuration:

~~~java
@Bean
ProducerFactory<String, OrderResultEvent> resultProducerFactory() {
    Map<String, Object> config = new HashMap<>();
    config.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "kafka-1.example.internal:9092");
    config.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);
    config.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class);

    DefaultKafkaProducerFactory<String, OrderResultEvent> factory =
            new DefaultKafkaProducerFactory<>(config);
    factory.setTransactionIdPrefix("prod-orders-INSTANCE_ID-tx-");
    return factory;
}
~~~

Ở production, prefix và bootstrap servers phải lấy từ cấu hình triển khai. Producer factory chỉ là một thành phần; cần tạo Kafka transaction manager và gắn vào container factory bằng API phù hợp với phiên bản Spring Kafka.

## 8. Những cấu hình không thay thế zombie fencing

| Cấu hình | Vai trò | Điều không được suy diễn |
|---|---|---|
| `enable.auto.commit=false` | Tắt Kafka consumer auto commit để container kiểm soát offsets | Chưa tạo transaction output + offset. |
| `ack-mode: record` | Quy tắc acknowledge của listener container khi phù hợp | Chưa bảo đảm offset nằm trong cùng transaction với output. |
| `group.instance.id` | Nhận diện static consumer member qua restart | Không phải Kafka producer `transactional.id`. |
| `max.poll.interval.ms` | Deadline giữa các lần poll | Tăng timeout không giải quyết mọi zombie hoặc deadlock. |
| `transactionIdPrefix` | Namespace producer transactional IDs | Không chứng minh consumer còn sở hữu partition ở group generation hiện tại. |
| `isolation.level=read_committed` | Chỉ đọc Kafka transactional records đã commit | Không ngăn method listener bị gọi lại hay HTTP request trùng. |

Không thể dùng một tham số đơn lẻ để thay thế việc xác định transaction boundary đúng.

## 9. Phân biệt ProducerFencedException và FencedInstanceIdException

`ProducerFencedException` thường liên quan quyền của transactional producer sử dụng một `transactional.id`/epoch. `FencedInstanceIdException` lại liên quan việc static consumer member dùng `group.instance.id` không hợp lệ hoặc bị một member khác cùng ID thay thế.

Nếu hai pod có:

~~~text
Pod A:
  group.instance.id = orders-consumer-0
  transactionIdPrefix = orders-tx-a-

Pod B:
  group.instance.id = orders-consumer-0
  transactionIdPrefix = orders-tx-b-
~~~

Thì lỗi trùng static member identity có thể xuất hiện dù producer prefixes khác nhau. Ngược lại, hai pod dùng static member IDs khác nhau nhưng cùng producer prefix vẫn có nguy cơ producer fencing.

Việc phân biệt giúp tránh khắc phục sai: đổi `group.instance.id` không tự sửa được collision của transactional ID; đổi producer prefix không sửa được hai static members cùng ID.

## 10. Retry, rollback và after-rollback recovery

Trong Kafka transactional listener container, khi listener ném exception, Kafka transaction được rollback/abort. Spring Kafka có cơ chế xử lý sau rollback như `DefaultAfterRollbackProcessor` để seek/retry record hoặc recovery khi hết số lần thử.

Không áp dụng mặc nhiên cách xử lý offset của listener không transaction cho transactional listener. Một số chi tiết error handler và API thay đổi theo phiên bản Spring Kafka.

Khi zombie bị fence:

1. Không cố tiếp tục commit transaction cũ.
2. Không giữ và tái sử dụng producer đã bị fence.
3. Để container/framework xử lý rollback hoặc dừng theo loại lỗi.
4. Cho consumer hợp lệ đọc lại từ committed offset khi cần.
5. Bảo đảm listener idempotent với mọi side effect ngoài Kafka.

Nếu cần đưa record không thể xử lý sang DLT, recovery phải xác nhận việc publish DLT và commit recovered offset theo chính sách transaction tương ứng. Không coi publish DLT thất bại là một recovery thành công.

Trong Spring Kafka, non-blocking retry tiêu chuẩn qua `@RetryableTopic` **không được hỗ trợ kết hợp trực tiếp với Kafka container transactions**. Khi cần delay dài, hãy cân nhắc điều chỉnh retry trong mô hình rollback hoặc tách workflow/retry topology phù hợp; đừng trộn hai cơ chế rồi coi là exactly-once.

## 11. max.poll.interval.ms và transaction.timeout.ms

Zombie có thể xuất hiện khi listener bị chặn quá lâu. Hai deadline cần theo dõi:

| Thuộc tính | Kiểm soát | Rủi ro nếu vượt |
|---|---|---|
| `max.poll.interval.ms` | Khoảng tối đa giữa các lần consumer gọi `poll()` | Consumer có thể mất membership, partition rebalance và thành zombie khi hồi phục. |
| `transaction.timeout.ms` | Tuổi tối đa của Kafka transaction theo giới hạn broker | Coordinator có thể abort transaction quá hạn. |
| `session.timeout.ms` | Thời gian chờ heartbeat | Ảnh hưởng phát hiện member mất kết nối và phân phối lại partition. |

Ví dụ:

~~~text
max.poll.interval.ms = 300000 (5 phút)
transaction.timeout.ms = 60000 (1 phút)

T=00:00 A poll record và bắt đầu transaction
T=00:05 A gọi dịch vụ ngoài, bị treo
T=01:xx Transaction có thể timeout và bị abort
T=05:xx Consumer có thể mất quyền trong group
T=06:00 B nhận partition và xử lý record
T=07:00 A hồi phục, cố commit transaction cũ
         -> thất bại do transaction/identity/membership không hợp lệ
~~~

Thời điểm chính xác phụ thuộc broker/client, heartbeat, static membership, group protocol và phần mềm. Mục đích ví dụ là cho thấy timeout của transaction và timeout poll độc lập.

Không tăng hai timeout vô hạn chỉ để che giấu listener chậm. Nên giới hạn thời gian HTTP/DB, giảm `max.poll.records` nếu batch quá lớn, dùng retry có backoff phù hợp và tránh giữ transaction mở trong công việc dài hàng phút.

## 12. Static membership và zombie fencing

`group.instance.id` cho phép một consumer group nhận diện static member qua restart. Cơ chế này có thể giảm rebalance khi instance quay lại trước khi session timeout hết hạn. Nhưng static membership không thay thế Kafka transaction.

Khi static member vượt `max.poll.interval.ms`, client có thể ngừng heartbeat và coordinator chờ đến session timeout trước khi phân phối lại partition. Điều này có thể làm partition bị giữ lâu hơn. Khi quá trình chuyển quyền hoàn tất, transactional consumer group metadata vẫn quan trọng để ngăn tiến trình cũ commit offset như chủ sở hữu hiện tại.

Vì vậy, cần quản lý hai namespace:

- `group.instance.id`: duy nhất cho static member trong consumer group.
- `transactionIdPrefix` / `transactional.id`: duy nhất cho transactional producer phù hợp trong Kafka cluster.

Không đặt hai trường giống hệt nhau trên mọi replica chỉ vì chúng cùng diễn đạt "instance".

## 13. Kafka EOS không bao trùm database và HTTP

Giả sử listener A xử lý `PaymentRequested`:

~~~text
Consumer A:
  - Nhận event evt-17
  - Ghi database thành công
  - Bị treo trước khi Kafka transaction commit

Consumer B:
  - Nhận lại evt-17 sau rebalance
  - Ghi database thêm lần nữa nếu không có deduplication

Consumer A:
  - Hồi phục và bị Kafka zombie fencing
~~~

Kafka có thể ngăn output transaction của A được commit sai, nhưng database vẫn có thể đã bị ghi tại bước của A hoặc B. Producer fencing không rollback database transaction.

Các biện pháp quan trọng:

- Dùng `eventId` ổn định và unique constraint/inbox trong cùng transaction database với cập nhật nghiệp vụ.
- Khi cần DB update rồi phát Kafka event, dùng transactional outbox nếu phù hợp.
- Gọi API bên ngoài với idempotency key được đối tác hỗ trợ.
- Phân biệt kết quả Kafka committed và kết quả nghiệp vụ thực tế.
- Không ack/commit sớm khi công việc bất đồng bộ chưa hoàn tất.

| Tác động | Kafka transaction/fencing bảo vệ? | Bổ sung cần thiết |
|---|---|---|
| Kafka output trong cùng transaction | Có, theo commit/abort và `read_committed` | Wiring đúng template/container và producer transaction. |
| Offset nguồn trong cùng transaction | Có, với group metadata hợp lệ | Không tự commit offset ngoài transaction. |
| Database update riêng | Không | Transaction DB, deduplication/inbox. |
| HTTP request hoặc payment call | Không | Idempotency key và trạng thái kết quả. |
| Email/SMS | Không | Outbox, dedupe hoặc chính sách gửi lại. |

Chỉ nói **exactly-once trong phạm vi Kafka transaction** khi mô tả pipeline; tránh khẳng định "toàn bộ hệ thống không bao giờ lặp".

## 14. Kiểm thử zombie fencing bằng fault injection

Nên kiểm thử các cửa sổ lỗi trên môi trường staging/integration có Kafka broker phù hợp; không tạo producer collision cố ý trong production.

### Thử nghiệm A: producer epoch fencing

1. Khởi tạo transactional producer P1 với ID `test-zombie-X`.
2. Bắt đầu transaction và gửi một record nhưng chưa commit.
3. Khởi tạo producer P2 với **cùng transactional ID**.
4. Cho P2 hoàn tất khởi tạo transactional identity hợp lệ.
5. Cho P1 tiếp tục commit transaction cũ.
6. Kiểm tra P1 không còn quyền commit hoặc nhận lỗi fencing/epoch.
7. Đọc output với `read_committed` để xác nhận record thuộc transaction không commit không hiển thị như kết quả hợp lệ.

### Thử nghiệm B: consumer group fencing sau rebalance

1. Chạy transactional listener A xử lý partition 0.
2. Giữ A ở một bước có thể kiểm soát và cho group thay đổi assignment.
3. Chạy listener B để B được giao partition 0 và xử lý từ committed offset.
4. Cho A tiếp tục gửi output/commit transaction theo ngữ cảnh group cũ.
5. Kiểm tra transaction của A không thể commit offset như member hợp lệ.
6. Đọc output bằng consumer `read_committed` và so sánh với committed offsets.
7. Kiểm tra B có thể hoàn thành transaction đúng và không có output committed trái phép từ A.

### Thử nghiệm C: side effect vẫn có thể trùng

1. Cho A ghi database thành công nhưng dừng trước commit Kafka.
2. Cho B đọc lại event sau rebalance.
3. Quan sát database có thể bị cập nhật lần hai nếu thiếu idempotency.
4. Thêm inbox/unique event ID và chạy lại.
5. Xác nhận chỉ một tác động database được áp dụng dù listener có thể gọi nhiều lần.

Trong mỗi thử nghiệm, ghi thời gian poll, group generation/assignment, transaction begin/abort/commit, event ID và kết quả output. Không chỉ dựa vào một exception để tuyên bố toàn bộ EOS đã được xác nhận.

## 15. Monitoring và chẩn đoán

| Tín hiệu | Mục đích quan sát |
|---|---|
| `ProducerFencedException` / producer epoch errors | Phát hiện producer cũ hoặc collision transactional ID. |
| Transaction begin/commit/abort | Theo dõi transaction thành công và rollback. |
| Transaction duration p95/p99 | Phát hiện transaction gần timeout. |
| Consumer rebalance, partition revoked/assigned | Xác định khi quyền sở hữu partition thay đổi. |
| Listener processing duration và poll interval | Phát hiện nguy cơ vượt `max.poll.interval.ms`. |
| Consumer group generation/member metadata khi hệ thống xuất ra | Liên hệ tiến trình cũ với thời điểm mất membership. |
| Committed offsets và read-committed output | Kiểm tra kết quả Kafka committed hợp lệ. |
| External idempotency collisions | Phát hiện side effect có nguy cơ duplicate. |
| DLT/recovery status | Xác nhận record lỗi được xử lý sau abort/retry. |

Log có cấu trúc nên chứa application instance, group ID, listener ID, topic, partition, offset, event ID, exception class, transaction status và thời điểm rebalance. Không đưa event ID hoặc transactional ID thay đổi liên tục làm metric label gây cardinality cao. Không log token, secret hay payload nhạy cảm.

Một lần fencing khi producer cũ được thay thế có thể phù hợp thiết kế. **Fencing lặp liên tục trên các instance đang chạy hợp lệ** là tín hiệu sự cố cần xử lý, thường liên quan prefix trùng hoặc vòng đời producer sai.

## 16. Runbook khi ProducerFencedException liên tục

1. Ghi nhận cluster, service, environment, pod/VM, producer factory và transactional ID nếu có.
2. Tìm tất cả instance có thể sinh transactional ID đó, kể cả process cũ trong rolling deployment.
3. Kiểm tra `transactionIdPrefix` hiệu lực, suffix strategy và cách lấy instance ID.
4. Xác định fencing là producer cũ bị thay thế đúng quy trình hay hai instance hợp lệ fence nhau.
5. Nếu collision, cấp prefix duy nhất cho từng instance/factory có thể chạy đồng thời.
6. Không tái sử dụng producer đã bị fence; để framework đóng/discard producer và xử lý transaction thất bại.
7. Kiểm tra input offsets, output Kafka và side effect ngoài Kafka của transaction bị abort.
8. Giám sát abort/fencing và consumer lag sau khi sửa deployment.

Không tắt Kafka transaction hoặc sinh một transactional ID ngẫu nhiên mới cho mỗi record chỉ để tránh exception. Những cách đó có thể làm mất ranh giới bảo vệ đang cần.

## 17. Runbook khi consumer hồi phục sau rebalance

1. Xác định topic/partition/offset và consumer A bắt đầu xử lý thời điểm nào.
2. Đọc rebalance logs: A bị revoke khi nào, B được assigned khi nào.
3. Đối chiếu `max.poll.interval.ms`, `session.timeout.ms`, transaction timeout và thời gian listener.
4. Kiểm tra container có thật sự gửi offsets cùng group metadata vào Kafka transaction.
5. Xác định lỗi commit của A là group membership fencing, producer epoch fencing hay transaction timeout.
6. Kiểm tra `read_committed` ở downstream; xác nhận output của transaction A thất bại không được xử lý như committed.
7. Xác nhận B đã xử lý/commit record hợp lệ.
8. Với database/HTTP, kiểm tra idempotency và xử lý bù nếu đã có side effect trùng.
9. Giảm thời gian xử lý/blocking retry và thử lại tình huống rebalance trong staging.

Không reset offset tùy tiện để "đồng bộ" với một zombie. Reset sai có thể bỏ qua record chưa xử lý hoặc gây replay không mong muốn.

## 18. Runbook khi static member bị fence

1. Kiểm tra exception có thực sự là `FencedInstanceIdException` hay không.
2. Xác định `group.id` và `group.instance.id` của các member đang chạy.
3. Tìm pod/VM trùng static ID; kiểm tra ordinal, rollout overlap và instance identity.
4. Dừng process sai mapping và khôi phục static membership theo quy trình.
5. Kiểm tra **riêng** `transactionIdPrefix` để loại trừ collision Kafka producer.
6. Xác minh group assignment, committed offsets và Kafka transaction outcome.

Static membership fencing và producer fencing có thể đồng thời xuất hiện trong một deployment lỗi, nhưng không được nhập nhằng nguyên nhân của hai exception.

## 19. Bảng kiểm soát Zombie fencing

| Điểm kiểm soát | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Producer identity | Transactional producers độc lập có ID đầy đủ riêng không? | Prefix/suffix và replica inventory. |
| EOS protocol | Broker/client/Spring Kafka có hỗ trợ EOS V2 group metadata không? | Phiên bản, transaction mode và integration tests. |
| Container transaction | Input offsets và Kafka output có nằm trong cùng transaction không? | KafkaTemplate, producer factory và transaction manager wiring. |
| Group membership | Consumer zombie có bị từ chối commit offset sau rebalance không? | Group generation, logs và lỗi transactional offset commit. |
| Output visibility | Consumer downstream cần EOS có `read_committed` không? | Consumer effective config. |
| Poll budget | Listener có poll đúng nhịp không? | `max.poll.interval.ms` và listener duration p99. |
| Transaction timeout | Transaction có hoàn tất trước deadline không? | `transaction.timeout.ms` và transaction duration. |
| Static membership | `group.instance.id` có duy nhất trong group không? | Instance mapping và fencing logs. |
| External idempotency | Database/API có an toàn khi A/B cùng chạy logic không? | Unique event ID, inbox/outbox và fault-injection. |
| Recovery | Transaction abort có dẫn đến retry/recovery đúng không? | AfterRollbackProcessor, DLT và committed offsets. |

**Kết luận:** Zombie fencing ngăn producer hoặc consumer đã mất quyền hoàn tất Kafka transaction theo một ngữ cảnh lỗi thời. Kafka dùng `transactional.id` và producer epoch để fence producer cũ; trong EOS V2, consumer group metadata cho phép từ chối commit offset của zombie sau rebalance, kể cả khi các instance có producer IDs khác nhau. Spring Kafka tận dụng cơ chế này khi transactional listener container, KafkaTemplate và transaction manager được phối hợp đúng. Để vận hành đáng tin cậy, cần thêm prefix duy nhất, deadline poll/transaction hợp lý, downstream `read_committed` và idempotency cho mọi tác động ngoài Kafka.
