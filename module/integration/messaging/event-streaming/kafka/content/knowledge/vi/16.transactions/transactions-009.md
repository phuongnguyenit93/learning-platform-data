# transaction.timeout.ms và khôi phục sau khi ứng dụng lỗi

## Mục tiêu bài học

Kafka transaction có thể kết hợp ghi output record và commit input offset trong một thao tác nguyên tử. Nhưng transaction có thể bị bỏ dở nếu ứng dụng crash, mất mạng hoặc không gọi commit/abort đúng hạn. `transaction.timeout.ms` giới hạn thời gian một transaction được phép mở; transaction coordinator theo dõi trạng thái và xử lý transaction hết hạn. Khi ứng dụng khởi động lại, `transactional.id` giúp producer mới tiếp quản đúng danh tính, fence producer cũ và khôi phục trạng thái transaction trước đó.

Sau bài học, bạn có thể:

- Giải thích `transaction.timeout.ms` và giới hạn `transaction.max.timeout.ms` ở broker.
- Phân biệt transaction timeout với request timeout và delivery timeout.
- Mô tả vai trò của transaction coordinator và internal topic `__transaction_state`.
- Phân tích điều gì xảy ra khi ứng dụng crash trước, trong hoặc sau `commitTransaction()`.
- Dùng `transactional.id` ổn định để producer mới tiếp quản sau restart.
- Hiểu producer fencing và lỗi `ProducerFencedException`.
- Giải thích ảnh hưởng của transaction đang mở đến consumer `read_committed` và Last Stable Offset.
- Thiết kế timeout, shutdown, retry và recovery runbook phù hợp.

## 1. Vì sao transaction cần timeout?

Kafka transaction có thể ghi record vào nhiều partition/topic và cập nhật offset của consumer group. Coordinator cần biết transaction nào đang mở, transaction nào đã commit và transaction nào đã abort.

Nếu ứng dụng bắt đầu transaction rồi crash trước khi kết thúc, transaction có thể ở trạng thái đang mở. Nếu không có cơ chế hết hạn, consumer đọc theo `read_committed` có thể phải chờ mãi ở partition có transaction chưa được giải quyết.

`transaction.timeout.ms` đặt thời gian tối đa transaction được phép tồn tại trước khi broker xem nó là hết hạn và bắt đầu abort. Nó giúp dọn các transaction bị bỏ dở khi producer không còn hoạt động.

Luồng tổng quát:

```text
Application
    |
    | beginTransaction()
    v
Transaction coordinator ghi nhận transaction
    |
    | send records / send offsets
    v
Transaction đang mở
    |
    +---- commitTransaction() ----> COMMITTED
    |
    +---- abortTransaction() -----> ABORTED
    |
    +---- ứng dụng crash / quá hạn
                                  |
                                  v
                         Coordinator abort transaction
```

Timeout là cơ chế phục hồi khi transaction không được kết thúc đúng hạn. Trong ứng dụng bình thường, vẫn nên chủ động commit hoặc abort mỗi transaction.

## 2. `transaction.timeout.ms` hoạt động như thế nào?

### 2.1. Timeout của một transaction

`transaction.timeout.ms` là cấu hình producer, tính bằng mili giây, cho biết thời gian tối đa producer muốn transaction được mở trước khi coordinator xem transaction là hết hạn.

Ví dụ:

```java
props.put(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG, 120_000);
```

Giá trị trên là ví dụ 120 giây. Nó cần đủ cho toàn bộ công việc trong transaction: xử lý record, gửi output, gửi input offset và hoàn tất commit. Không nên đặt quá ngắn khiến transaction hợp lệ bị abort; cũng không nên đặt quá dài vì transaction bị bỏ dở sẽ giữ trạng thái mở lâu hơn.

### 2.2. Broker giới hạn timeout tối đa

Broker có cấu hình `transaction.max.timeout.ms` để giới hạn timeout lớn nhất mà producer được phép yêu cầu. `transaction.timeout.ms` của producer phải nhỏ hơn hoặc bằng giới hạn broker.

Ví dụ cấu hình broker:

```properties
transaction.max.timeout.ms=900000
```

Con số 900.000 ms (15 phút) là ví dụ cấu hình; giá trị mặc định và quy tắc triển khai cần được kiểm tra theo phiên bản Kafka đang chạy. Nếu producer yêu cầu timeout lớn hơn giới hạn broker, việc khởi tạo transaction có thể thất bại với lỗi cấu hình timeout, chẳng hạn `InvalidTxnTimeoutException`.

Không nên tăng `transaction.max.timeout.ms` chỉ để làm lỗi biến mất. Timeout lớn ảnh hưởng đến thời gian coordinator phải chờ transaction bị bỏ dở và có thể kéo dài thời gian consumer `read_committed` bị chặn ở partition liên quan.

### 2.3. Timeout không phải thời gian sống của producer

Producer có thể tồn tại nhiều ngày hoặc nhiều tháng, mở và kết thúc nhiều transaction. `transaction.timeout.ms` áp dụng cho từng transaction đang mở, không giới hạn tuổi thọ của đối tượng `KafkaProducer` hay thời gian ứng dụng được chạy.

Một producer có thể thực hiện hàng nghìn transaction nối tiếp:

```text
Producer lifetime
|-------------------------------------------------------->

Transaction 1: [begin -------- commit]
Transaction 2:                   [begin ---- abort]
Transaction 3:                                  [begin --- commit]
```

Mỗi transaction có vòng đời riêng và cần được hoàn tất trong timeout đã thương lượng với broker.

## 3. Phân biệt các timeout liên quan

Các timeout sau bảo vệ những giai đoạn khác nhau:

| Cấu hình | Phạm vi | Ý nghĩa |
|---|---|---|
| `transaction.timeout.ms` | Một Kafka transaction | Thời gian tối đa transaction được phép mở |
| `transaction.max.timeout.ms` | Broker | Giới hạn lớn nhất broker chấp nhận từ producer |
| `request.timeout.ms` | Một request mạng | Thời gian chờ response cho request đó |
| `delivery.timeout.ms` | Một record gửi | Tổng thời gian producer cố gắng giao record, gồm batching và retry |
| `max.block.ms` | Lời gọi ứng dụng | Giới hạn chờ metadata hoặc buffer trong các thao tác như `send()` |
| `transaction.state.log.*` | Broker | Cấu hình lưu trữ/replication trạng thái transaction nội bộ |

Ví dụ: một record có thể được gửi thành công trong `delivery.timeout.ms`, nhưng transaction tổng thể vẫn chưa commit vì ứng dụng còn xử lý record khác. Ngược lại, request có thể timeout và được retry trong khi transaction vẫn còn thời gian.

Không tăng `request.timeout.ms` hoặc `delivery.timeout.ms` để xử lý transaction bị bỏ dở. Cần xác định transaction kéo dài do xử lý nghiệp vụ, broker chậm hay ứng dụng không gọi commit/abort.

## 4. Transaction coordinator và `__transaction_state`

### 4.1. Vai trò của transaction coordinator

Kafka chọn một broker làm transaction coordinator cho mỗi `transactional.id`. Coordinator quản lý trạng thái transaction, producer ID/epoch và quá trình commit/abort.

Producer gửi các request transaction đến coordinator, ví dụ đăng ký partition tham gia transaction, gửi offset consumer group và kết thúc transaction. Coordinator phối hợp với các partition leader để ghi transaction marker commit hoặc abort.

### 4.2. Internal topic `__transaction_state`

Kafka lưu trạng thái transaction trong internal topic `__transaction_state`. Topic này được partition hóa và replication để coordinator có thể phục hồi trạng thái khi broker giữ vai trò coordinator gặp sự cố hoặc một partition chuyển leader.

Một số cấu hình broker liên quan:

| Cấu hình | Vai trò |
|---|---|
| `transaction.state.log.replication.factor` | Replication factor của transaction state topic |
| `transaction.state.log.min.isr` | Số replica đồng bộ tối thiểu cho thao tác ghi transaction state theo cấu hình broker |
| `transaction.max.timeout.ms` | Timeout transaction lớn nhất producer được yêu cầu |

Trong production, transaction state log cần replication và min ISR phù hợp với yêu cầu khả dụng. Nếu cluster có ít broker hơn replication factor cấu hình, internal topic có thể không khởi tạo được hoặc transaction không hoạt động như mong đợi. Kiểm tra các cấu hình này khi triển khai cluster nhỏ/lab và cluster production.

### 4.3. Coordinator failover

Nếu broker đang làm transaction coordinator dừng hoặc mất kết nối, coordinator mới được bầu cho partition tương ứng của `__transaction_state` có thể phục hồi trạng thái từ log đã replicate. Producer có thể gặp lỗi coordinator unavailable/not coordinator và cần retry theo cơ chế client.

Transaction state log giúp coordinator tiếp tục điều phối commit/abort sau failover. Nó không có nghĩa ứng dụng có thể bỏ qua việc xử lý exception hoặc không cần `transaction.timeout.ms`.

## 5. Điều gì xảy ra khi ứng dụng crash?

### 5.1. Crash trước `beginTransaction()`

Nếu ứng dụng crash trước khi mở transaction, không có transaction mới nào được tạo. Consumer có thể đã poll record nhưng nếu input offset chưa commit thì group sẽ đọc lại record sau khi consumer tham gia lại.

### 5.2. Crash sau `beginTransaction()` nhưng trước khi gửi record

Transaction đã bắt đầu nhưng chưa có output hoàn chỉnh. Nếu ứng dụng không thể gọi `abortTransaction()`, coordinator sẽ giải quyết transaction bị bỏ dở theo trạng thái và timeout. Ứng dụng khởi động lại với cùng `transactional.id` có thể kích hoạt quá trình fencing/recovery sớm hơn việc chỉ chờ timeout.

### 5.3. Crash sau khi gửi output nhưng trước commit

Output record đã được gửi vào transaction nhưng transaction chưa commit. Consumer dùng `read_committed` không coi output đó là dữ liệu đã commit. Khi transaction bị abort, các output record bị đánh dấu aborted và không được trả về cho consumer `read_committed`.

Nếu input offset cũng được gửi bằng `sendOffsetsToTransaction()`, offset đó nằm trong cùng transaction. Khi transaction abort, input offset không tiến lên; consumer group sẽ đọc lại input sau khi khôi phục.

### 5.4. Crash trong lúc `commitTransaction()`

Đây là trường hợp cần chú ý nhất. Ứng dụng có thể gửi yêu cầu commit đến coordinator, coordinator có thể đã ghi quyết định commit, nhưng process mất kết nối trước khi nhận response.

Ứng dụng cũ không thể suy ra kết quả chỉ từ việc không nhận được response. Transaction có thể đã commit hoặc chưa commit. Khi producer mới khởi động với cùng `transactional.id` và gọi `initTransactions()`, Kafka sẽ xử lý trạng thái transaction trước đó trước khi cho phép transaction mới bắt đầu.

- Nếu transaction trước đã commit, output và input offset vẫn được commit cùng nhau.
- Nếu transaction trước chưa commit và được abort, output transaction không được thấy bởi consumer `read_committed`, input offset không được tiến lên và input có thể được đọc lại.

Không tự tạo một producer khác với ID mới rồi giả định transaction cũ đã kết thúc. Cần dùng đúng danh tính producer để coordinator fencing và recovery.

### 5.5. Crash sau khi `commitTransaction()` trả về thành công

Khi `commitTransaction()` trả về thành công, transaction đã được commit theo giao thức Kafka. Nếu ứng dụng crash ngay sau đó, transaction không cần được thực hiện lại; consumer group đã có offset trong transaction và tiếp tục từ vị trí mới.

## 6. Vai trò của `transactional.id`

### 6.1. Định danh ổn định của logical producer

`transactional.id` định danh producer có khả năng dùng transaction. Kafka dùng ID này để liên kết producer ID, epoch và trạng thái transaction. ID cần duy nhất giữa các producer đang hoạt động đồng thời, nhưng nên ổn định qua lần restart của cùng một logical producer nếu muốn producer mới tiếp quản transaction cũ.

Ví dụ:

```java
props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
    "order-transformer-shard-0");
```

Nếu service chạy nhiều shard, mỗi shard cần một ID khác nhau:

```text
order-transformer-shard-0
order-transformer-shard-1
order-transformer-shard-2
```

Khi shard 1 restart, nó dùng lại `order-transformer-shard-1`. Không để hai process đang hoạt động cùng dùng ID đó.

### 6.2. Producer fencing

Khi producer mới khởi tạo với cùng `transactional.id`, coordinator tăng epoch và fence producer cũ. Producer cũ không còn quyền tiếp tục ghi hoặc commit transaction bằng epoch đã hết hiệu lực.

Điều này bảo vệ hệ thống khi process cũ thực tế chưa chết hoàn toàn nhưng ứng dụng đã khởi chạy instance thay thế. Nếu không fencing, hai process có thể cùng ghi dữ liệu với một danh tính transaction và làm sai tính nhất quán.

Producer cũ có thể nhận `ProducerFencedException`. Khi gặp lỗi này, ứng dụng phải dừng producer cũ và giải phóng tài nguyên; không retry transaction trên producer đã bị fence.

### 6.3. ID mới mỗi lần restart làm mất lợi ích tiếp quản

Nếu mỗi lần khởi động ứng dụng tạo một `transactional.id` ngẫu nhiên, producer mới không fence producer cũ bằng danh tính đó. Transaction cũ vẫn phải được coordinator xử lý theo timeout và có thể giữ partition ở trạng thái chờ lâu hơn.

Dùng ID ngẫu nhiên có thể phù hợp khi mỗi producer instance là một producer độc lập, không có yêu cầu tiếp quản transaction của instance cũ. Nhưng với một logical shard cần recovery sau restart, nên dùng ID ổn định và bảo đảm tính duy nhất giữa các instance đang hoạt động.

### 6.4. `transactional.id` khác `group.id`

| ID | Định danh | Phạm vi |
|---|---|---|
| `group.id` | Consumer group và tiến độ đọc | Nhiều consumer chia partition, lưu committed offset |
| `transactional.id` | Logical transactional producer | Producer ID/epoch, transaction state và fencing |

Trong consume-transform-produce, consumer và producer có cả hai ID. `group.id` được dùng khi gửi offset vào transaction; `transactional.id` được dùng để coordinator nhận diện producer transaction.

## 7. `initTransactions()` và recovery khi restart

### 7.1. Khởi tạo producer transactional

Producer transactional cần gọi `initTransactions()` trước khi bắt đầu transaction:

```java
KafkaProducer<String, String> producer = new KafkaProducer<>(props);
producer.initTransactions();
```

Lời gọi này đăng ký producer với coordinator, nhận producer ID/epoch và bảo đảm các transaction còn dang dở từ instance trước có cùng `transactional.id` được xử lý trước khi instance mới bắt đầu transaction mới.

`initTransactions()` có thể chờ coordinator phục hồi trạng thái và hoàn tất việc fencing/recovery. Không gọi nó cho mỗi batch; gọi một lần trong vòng đời khởi tạo producer.

### 7.2. Trình tự recovery chuẩn

Khi ứng dụng khởi động lại:

1. Tạo producer với `transactional.id` ổn định của logical instance.
2. Gọi `initTransactions()` và chờ quá trình recovery/fencing hoàn tất.
3. Tạo hoặc khôi phục consumer với đúng `group.id`, tắt auto commit.
4. Đăng ký topic và poll để nhận partition assignment.
5. Với mỗi batch, bắt đầu transaction mới.
6. Gửi output record và input offset vào cùng transaction.
7. Commit transaction; nếu lỗi thuộc loại có thể abort, abort trước khi tiếp tục theo chính sách ứng dụng.
8. Nếu producer bị fence hoặc transaction ở trạng thái không thể phục hồi trong instance hiện tại, dừng instance và để supervisor khởi tạo logical instance hợp lệ.

### 7.3. Transaction trước có được tiếp tục từ giữa chừng không?

Không. Producer mới không tiếp tục thực thi business code từ đúng câu lệnh nơi process cũ bị crash. Kafka chỉ phục hồi trạng thái transaction ở phía broker: transaction trước đã commit thì giữ kết quả; transaction chưa commit sẽ được abort/resolve. Nếu input offset chưa được commit, consumer đọc lại input và ứng dụng chạy logic từ đầu cho batch tương ứng.

Vì vậy, business logic vẫn phải có khả năng chạy lại. Với side effect ngoài Kafka, dùng inbox/idempotency hoặc outbox; Kafka transaction không rollback database hay HTTP service.

## 8. Ảnh hưởng của transaction đang mở đến `read_committed`

### 8.1. Last Stable Offset (LSO)

Consumer đặt `isolation.level=read_committed` chỉ nhận các record thuộc transaction đã commit và các record không transactional phù hợp. Với mỗi partition, Last Stable Offset (LSO) là ranh giới mà consumer `read_committed` có thể đọc đến; LSO không vượt qua transaction đang mở sớm nhất trên partition và cũng bị giới hạn bởi high watermark.

Ví dụ:

```text
Partition orders-0

offset:  100 101 102 103 104 105 106 107 108
         |   |   |   |   |   |   |   |   |
         C   C   O   O   O   ?   ?   N   N

C = record đã commit
O = record thuộc transaction đang mở
? = chưa thể đọc committed vượt qua transaction mở
N = record được ghi sau transaction đang mở

read_committed chỉ đọc đến trước LSO
```

Nếu transaction mở lâu, consumer `read_committed` có thể không đọc được các record mới hơn trên cùng partition dù chúng đã được append. Đây là một lý do cần giới hạn thời gian transaction và tránh thực hiện công việc bên ngoài quá lâu trong khi transaction đang mở.

### 8.2. Transaction hết hạn và LSO tiến lên

Khi transaction coordinator quyết định abort transaction hết hạn và transaction marker được ghi vào các partition liên quan, LSO có thể tiến lên. Consumer `read_committed` sau đó có thể tiếp tục đọc các record hợp lệ phía sau.

Do đó, transaction timeout quá dài có thể kéo dài thời gian consumer chờ khi ứng dụng đã crash. Timeout quá ngắn lại có thể abort một transaction hợp lệ đang xử lý chậm. Cần cân bằng giữa thời gian xử lý bình thường và thời gian phục hồi mong muốn.

### 8.3. `read_uncommitted` có hành vi khác

Consumer `read_uncommitted` có thể nhìn thấy record thuộc transaction chưa commit hoặc đã abort. Cách đọc này không phù hợp nếu downstream cần chỉ quan sát kết quả transaction đã commit.

Với pipeline transactional, cấu hình downstream:

```java
consumerProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
```

## 9. Thiết kế giá trị timeout

### 9.1. Đo thời gian transaction thực tế

Đo từ lúc `beginTransaction()` đến khi `commitTransaction()` hoặc `abortTransaction()` hoàn tất. Bao gồm:

- Thời gian transform và xử lý nghiệp vụ.
- Thời gian gửi record và chờ broker.
- Thời gian gửi input offsets.
- Thời gian coordinator hoàn tất transaction.
- Các khoảng chờ do thread scheduling, GC hoặc network.

Đặt timeout cao hơn đáng kể so với transaction duration bình thường và percentile cao trong tải đỉnh, nhưng vẫn giữ giới hạn phục hồi phù hợp với SLA.

### 9.2. Chọn timeout theo batch size

Nếu transaction chứa nhiều record hoặc gọi nhiều service bên ngoài, thời gian hoàn tất có thể tăng. Không nên mở transaction rồi thực hiện một công việc dài như gọi API đồng bộ nhiều lần, upload file hoặc chờ người dùng.

Các cách giảm transaction duration:

- Giảm số record trong mỗi transaction nếu batch quá lớn.
- Tối ưu transform và serialization.
- Tránh gọi database/HTTP bên ngoài trong khi transaction Kafka đang mở nếu có thể tách công việc.
- Dùng timeout hữu hạn cho các thao tác mạng.
- Không giữ transaction mở khi ứng dụng đang chờ queue hoặc chờ tương tác người dùng.

### 9.3. Đánh đổi khi timeout quá ngắn hoặc quá dài

| Cấu hình | Lợi ích | Rủi ro |
|---|---|---|
| Timeout quá ngắn | Transaction bỏ dở được dọn nhanh | Transaction hợp lệ bị abort khi tải cao hoặc GC/network chậm |
| Timeout quá dài | Chịu được batch xử lý lâu hơn | Transaction mồ côi giữ trạng thái mở lâu, LSO và consumer `read_committed` có thể bị chặn lâu |
| Timeout phù hợp với percentile xử lý | Cân bằng xử lý bình thường và recovery | Cần đo lại khi workload thay đổi |

### 9.4. Ví dụ cấu hình producer

```java
Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
    "order-transformer-shard-0");
props.put(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG, 120_000);

KafkaProducer<String, String> producer = new KafkaProducer<>(props);
producer.initTransactions();
```

120 giây chỉ là giá trị minh họa. Cần kiểm tra `transaction.max.timeout.ms` trên broker và đo transaction duration thực tế trước khi chọn giá trị production.

## 10. Mẫu consume-transform-produce có recovery

Ví dụ sau cho thấy cấu trúc xử lý. Producer được tạo với transactional ID ổn định, consumer tắt auto commit và input offset được gửi trong transaction.

```java
Properties consumerProps = new Properties();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "order-transformer");
consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName());
consumerProps.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
consumerProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");

Properties producerProps = new Properties();
producerProps.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
producerProps.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
producerProps.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
    StringSerializer.class.getName());
producerProps.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
    "order-transformer-shard-0");
producerProps.put(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG, 120_000);

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(consumerProps);
     KafkaProducer<String, String> producer = new KafkaProducer<>(producerProps)) {

    // Chạy một lần khi khởi động, trước beginTransaction().
    producer.initTransactions();
    consumer.subscribe(List.of("orders"));

    while (running) {
        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(500));

        if (records.isEmpty()) {
            continue;
        }

        producer.beginTransaction();

        try {
            Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();

            for (ConsumerRecord<String, String> record : records) {
                String outputValue = transform(record.value());
                producer.send(new ProducerRecord<>(
                    "order-events", record.key(), outputValue
                ));

                TopicPartition partition = new TopicPartition(
                    record.topic(), record.partition()
                );
                offsets.put(partition,
                    new OffsetAndMetadata(record.offset() + 1));
            }

            producer.sendOffsetsToTransaction(offsets, consumer.groupMetadata());
            producer.commitTransaction();
        } catch (org.apache.kafka.common.errors.TimeoutException outcomeUnknown) {
            // Không đoán transaction đã commit hay abort. Đóng producer và
            // khởi động lại logical instance với cùng transactional.id để recovery.
            throw new IllegalStateException(
                "Transaction outcome is unknown; restart with the same transactional.id",
                outcomeUnknown
            );
        } catch (ProducerFencedException fenced) {
            // Instance khác đang sở hữu transactional.id này.
            // Dừng instance hiện tại; không retry trên producer đã bị fence.
            throw new IllegalStateException("Transactional producer was fenced", fenced);
        } catch (KafkaException transactionError) {
            // Chỉ abort nếu loại exception này được Kafka client xem là abortable.
            if (isAbortable(transactionError)) {
                try {
                    producer.abortTransaction();
                } catch (KafkaException abortError) {
                    transactionError.addSuppressed(abortError);
                }
            }
            throw new IllegalStateException(
                "Transaction failed; stop or recover according to exception type",
                transactionError
            );
        }
    }
}
```

Đây là cấu trúc minh họa, cần hoàn thiện theo phiên bản client và exception taxonomy đang dùng. `isAbortable()` đại diện cho logic phân loại exception theo tài liệu client; không phải mọi `KafkaException` đều có thể xử lý bằng cách gọi `abortTransaction()`. Với lỗi fatal/fencing hoặc kết quả commit không rõ ràng do timeout/network, nên đóng producer và khởi động lại logical instance với cùng `transactional.id` để `initTransactions()` đồng bộ trạng thái trước khi xử lý tiếp.

Trong production, cần thêm:

- Phân loại exception retriable, abortable và fatal theo API Kafka client.
- Shutdown hook để ngừng nhận việc mới và hoàn tất/abort transaction đang mở.
- Đảm bảo `transactional.id` ổn định theo shard và duy nhất giữa các instance đang hoạt động.
- Theo dõi thời gian transaction và cảnh báo khi gần timeout.
- Bảo đảm offset map chỉ chứa vị trí liên tục đã xử lý thành công của mỗi partition.
- Không thực hiện side effect database/HTTP ngoài transaction Kafka rồi giả định abort Kafka sẽ rollback side effect đó.

## 11. Phục hồi theo từng tình huống

| Tình huống | Hành vi Kafka | Việc ứng dụng cần làm |
|---|---|---|
| Crash trước khi bắt đầu transaction | Không có transaction mới cần resolve | Consumer tiếp tục từ committed offset |
| Crash giữa transaction, chưa commit | Transaction chưa hoàn tất; coordinator sẽ abort/recover | Restart cùng `transactional.id`, gọi `initTransactions()`, đọc lại input nếu offset chưa commit |
| Transaction hết `transaction.timeout.ms` | Coordinator đánh dấu abort và hoàn tất transaction markers | Kiểm tra transaction duration và giảm nguyên nhân kéo dài |
| Crash sau khi commit đã được coordinator ghi nhưng trước response | Kết quả phía ứng dụng có thể chưa rõ | Khởi tạo producer mới cùng ID để resolve; không publish mù bằng ID mới |
| Producer cũ vẫn chạy khi instance mới dùng cùng ID | Producer cũ bị fence | Dừng producer cũ khi nhận `ProducerFencedException` |
| Coordinator broker restart | Coordinator mới phục hồi state từ `__transaction_state` | Cho client retry theo chính sách; kiểm tra broker và internal topic |
| Consumer `read_committed` bị chặn lâu | Có transaction mở sớm trên partition làm LSO chưa tiến | Kiểm tra transaction duration, producer health và timeout |
| Database commit xong nhưng Kafka offset chưa commit | Input có thể được giao lại | Inbox/idempotency ngăn database side effect lặp |

## 12. Quan sát và giám sát transaction

Theo dõi cả producer, broker coordinator và consumer downstream:

- Transaction duration trung bình, p95/p99 và max.
- Số transaction commit/abort mỗi giây.
- Transaction timeout và lỗi `InvalidTxnTimeoutException`.
- Lỗi fencing như `ProducerFencedException` hoặc epoch không hợp lệ.
- Request latency và lỗi coordinator như `NOT_COORDINATOR` hoặc coordinator unavailable.
- Consumer lag và khoảng cách giữa log end offset với Last Stable Offset nếu hệ thống monitoring cung cấp.
- Thời gian consumer `read_committed` không tiến triển.
- Trạng thái/replication của `__transaction_state`.
- Số lần ứng dụng restart và số lần `initTransactions()` mất nhiều thời gian.

Tên metric cụ thể thay đổi theo phiên bản Kafka, client và exporter. Kiểm tra JMX/metric thực tế trước khi tạo dashboard hoặc alert. Khi transaction timeout, đối chiếu log ứng dụng với broker coordinator theo cùng timestamp và transactional ID.

## 13. Quy trình điều tra transaction bị treo hoặc timeout

1. **Xác định transactional ID:** producer nào mở transaction và instance nào sở hữu ID đó?
2. **Xác định thời điểm:** transaction bắt đầu lúc nào, đã vượt `transaction.timeout.ms` chưa?
3. **Kiểm tra ứng dụng:** process còn sống, thread có bị block, GC pause hoặc chờ API/database không?
4. **Kiểm tra coordinator:** broker nào đang làm coordinator, có lỗi NOT_COORDINATOR hoặc coordinator unavailable không?
5. **Kiểm tra broker config:** producer timeout có vượt `transaction.max.timeout.ms` không?
6. **Kiểm tra internal topic:** `__transaction_state` có đủ ISR, leader ổn định và không có lỗi replication không?
7. **Kiểm tra LSO:** partition nào có transaction mở lâu làm consumer `read_committed` dừng tiến độ?
8. **Recovery:** khởi động đúng logical producer với cùng `transactional.id`, gọi `initTransactions()` và chờ recovery hoàn tất.
9. **Xác minh:** output đã commit hay bị abort, input offset có tiến lên không, consumer downstream có tiếp tục đọc không?
10. **Ngăn tái diễn:** điều chỉnh transaction scope, batch size, timeout hoặc thời gian xử lý theo số liệu đo được.

Không xóa hoặc chỉnh sửa trực tiếp `__transaction_state` để giải quyết một transaction bị treo. Dùng API producer và cơ chế coordinator để xử lý trạng thái transaction.

## 14. Các lỗi và anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Đặt `transaction.timeout.ms` lớn hơn broker max | Producer không khởi tạo transaction được | Kiểm tra `transaction.max.timeout.ms` trước khi triển khai |
| Timeout quá ngắn | Transaction hợp lệ bị coordinator abort | Đo duration p99 và thời gian xử lý batch |
| Timeout quá dài | Transaction bỏ dở giữ LSO lâu | Giữ transaction ngắn và đặt timeout theo SLA recovery |
| Dùng `transaction.timeout.ms` để thay `delivery.timeout.ms` | Không giải quyết đúng giai đoạn timeout | Phân biệt transaction lifetime với delivery của từng record |
| Tạo `transactional.id` ngẫu nhiên mỗi lần restart | Producer mới không tiếp quản/fence producer cũ bằng cùng ID | Dùng ID ổn định theo logical shard khi cần recovery |
| Nhiều instance đồng thời dùng cùng `transactional.id` | Producer fence lẫn nhau | Bảo đảm ID duy nhất giữa các instance đang hoạt động |
| Bỏ qua `initTransactions()` | Producer transactional không được khởi tạo đúng vòng đời | Gọi một lần trước transaction đầu tiên |
| Retry trên producer đã bị fence | Mọi thao tác transaction tiếp theo tiếp tục thất bại | Dừng producer cũ và để instance hợp lệ tiếp quản |
| Cho rằng timeout commit đồng nghĩa transaction chắc chắn abort | Có thể gửi lại output đã commit | Recovery bằng cùng ID để coordinator xác định kết quả |
| Giữ transaction mở khi gọi API ngoài lâu | LSO bị chặn và transaction dễ timeout | Rút ngắn transaction, dùng timeout hữu hạn và tách side effect ngoài Kafka |
| Dùng `read_uncommitted` cho pipeline cần transaction isolation | Consumer có thể thấy output chưa commit/đã abort | Dùng `read_committed` |

## 15. Checklist thiết kế timeout và recovery

Trước khi đưa transactional producer vào production, hãy xác nhận:

- `transaction.timeout.ms` phù hợp với transaction duration p99 và SLA phục hồi.
- Giá trị producer không vượt `transaction.max.timeout.ms` của broker.
- `request.timeout.ms` và `delivery.timeout.ms` được cấu hình theo mục tiêu riêng, không nhầm với transaction timeout.
- `transactional.id` ổn định theo logical shard và duy nhất giữa producer đang hoạt động.
- Producer gọi `initTransactions()` một lần khi khởi động.
- Có quy trình xử lý `ProducerFencedException` và lỗi fatal.
- Kết quả commit không rõ được recovery bằng cùng `transactional.id`.
- Input offsets được gửi qua `sendOffsetsToTransaction()`.
- Downstream dùng `read_committed` khi cần chỉ đọc transaction đã commit.
- `__transaction_state` có replication/min ISR phù hợp.
- Transaction không bao trùm các thao tác ngoài Kafka kéo dài không cần thiết.
- Có metric transaction duration, abort, timeout, fencing, LSO và consumer lag.
- Đã thử crash trước commit, trong commit và sau commit.
- Database/HTTP side effect có inbox/outbox hoặc idempotency riêng nếu nằm ngoài Kafka transaction.

## 16. Câu hỏi tự kiểm tra

1. `transaction.timeout.ms` giới hạn điều gì và không giới hạn điều gì?
2. Vì sao producer timeout phải nhỏ hơn hoặc bằng `transaction.max.timeout.ms` của broker?
3. `transaction.timeout.ms` khác `request.timeout.ms` và `delivery.timeout.ms` như thế nào?
4. Transaction coordinator lưu trạng thái transaction ở đâu?
5. Điều gì xảy ra nếu ứng dụng crash sau khi gửi output nhưng trước commit?
6. Nếu ứng dụng crash sau khi gửi yêu cầu commit nhưng trước khi nhận response, có thể kết luận transaction đã abort không?
7. `transactional.id` giúp producer mới tiếp quản như thế nào?
8. Vì sao hai producer đang hoạt động không được dùng cùng một `transactional.id`?
9. `ProducerFencedException` báo hiệu điều gì và ứng dụng nên phản ứng ra sao?
10. `initTransactions()` thực hiện vai trò gì khi producer restart?
11. Vì sao transaction mở lâu có thể làm consumer `read_committed` bị chặn ở LSO?
12. Transaction timeout quá ngắn và quá dài có những rủi ro gì?
13. Coordinator failover phục hồi trạng thái transaction dựa vào cơ chế nào?
14. Vì sao Kafka transaction không rollback được database hoặc HTTP side effect?

## Kết luận

`transaction.timeout.ms` giới hạn thời gian transaction Kafka được phép mở; broker áp dụng trần `transaction.max.timeout.ms` để bảo vệ coordinator và consumer downstream. Khi ứng dụng crash giữa transaction, coordinator có thể abort transaction bị bỏ dở; khi producer khởi động lại với cùng `transactional.id`, `initTransactions()` thực hiện fencing và recovery trước khi cho phép transaction mới. Cơ chế này giữ output Kafka và input offset nhất quán, còn consumer `read_committed` chỉ đọc dữ liệu đã commit sau LSO. Thiết kế tốt cần transaction ngắn, timeout dựa trên số liệu, ID ổn định theo logical producer và quy trình phục hồi rõ ràng.
