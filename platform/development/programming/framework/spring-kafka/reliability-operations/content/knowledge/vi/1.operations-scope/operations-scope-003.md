# Luồng producer, broker, consumer và listener

## 1. Bức tranh tổng thể

Trong Spring Kafka, một thông điệp đi qua bốn lớp trách nhiệm chính:

- **Producer** tạo và gửi bản ghi vào Kafka. Trong ứng dụng Spring, mã nghiệp vụ thường gửi qua `KafkaTemplate`; `ProducerFactory` quản lý việc tạo producer Kafka.
- **Broker** nhận bản ghi, ghi vào partition của topic và sao chép dữ liệu sang các replica theo cấu hình của cụm.
- **Consumer** đọc bản ghi từ partition theo offset. Các consumer có cùng group ID phối hợp chia nhau những partition của topic.
- **Listener** là phần mã ứng dụng xử lý bản ghi đã đọc. Với `@KafkaListener`, Spring quản lý consumer, vòng lặp poll, chuyển đổi dữ liệu, gọi phương thức listener và xử lý offset.

Luồng cơ bản:

1. Ứng dụng tạo event và gọi producer.
2. Producer serialize key/value, chọn partition, gom bản ghi thành batch và gửi request đến broker đang giữ vai trò leader của partition.
3. Broker ghi bản ghi vào log; các replica trong ISR nhận bản sao theo cơ chế replication.
4. Broker phản hồi producer theo cấu hình `acks`.
5. Consumer thuộc một consumer group fetch bản ghi từ partition được gán.
6. Spring listener container chuyển bản ghi đến phương thức listener.
7. Khi xử lý thành công, container commit offset theo acknowledgment mode đã cấu hình. Nếu xử lý lỗi, error handler quyết định retry hoặc chuyển bản ghi sang luồng phục hồi.

Sơ đồ sau thể hiện luồng thông thường. Việc commit offset diễn ra ở phía consumer sau khi listener xử lý, độc lập với xác nhận gửi từ producer.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant KT as KafkaTemplate
    participant P as Producer
    participant B as Broker leader
    participant R as Replica
    participant C as Consumer group
    participant LC as Listener container
    participant L as @KafkaListener

    App->>KT: send(topic, key, event)
    KT->>P: serialize và chọn partition
    P->>B: Produce request
    B->>R: Replicate record
    R-->>B: Replica response
    B-->>P: Acknowledgment theo acks
    P-->>KT: SendResult hoặc lỗi
    C->>B: Fetch từ offset hiện tại
    B-->>C: Record và offset
    C->>LC: Record đã deserialize
    LC->>L: Gọi phương thức listener
    L-->>LC: Thành công hoặc exception
    LC->>B: Commit offset khi đến thời điểm
~~~

Một điểm quan trọng: broker chỉ biết bản ghi đã được ghi và replication theo cơ chế Kafka. Broker không biết nghiệp vụ trong listener đã cập nhật cơ sở dữ liệu hay hoàn thành công việc hay chưa. Consumer offset là dấu mốc đọc của consumer group, không phải trạng thái xử lý nghiệp vụ được broker tự suy ra.

## 2. Producer: từ event trong ứng dụng đến bản ghi Kafka

### 2.1. Các thành phần Spring Kafka

`KafkaTemplate<K, V>` là API gửi thông điệp thường dùng trong mã nghiệp vụ. Nó làm việc với `ProducerFactory<K, V>` để lấy Kafka producer đã được cấu hình. Producer Kafka thực hiện serialize, partitioning, batching và giao tiếp mạng với broker.

Ví dụ gửi một event:

~~~java
@Service
@RequiredArgsConstructor
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public void publish(OrderCreated event) {
        kafkaTemplate.send("orders", event.orderId(), event)
            .whenComplete((result, error) -> {
                if (error != null) {
                    log.error("Cannot publish order event {}", event.orderId(), error);
                    return;
                }

                var metadata = result.getRecordMetadata();
                log.info(
                    "Published order {} to partition {} at offset {}",
                    event.orderId(),
                    metadata.partition(),
                    metadata.offset()
                );
            });
    }
}
~~~

Ví dụ này dùng API của Spring Kafka 3.x, trong đó kết quả gửi là `CompletableFuture`. Ở các phiên bản Spring Kafka cũ hơn, kiểu future có thể khác. Cần đối chiếu phiên bản dependency của ứng dụng khi áp dụng mã mẫu.

`send()` thường trả về ngay với một future; việc gửi thực tế diễn ra bất đồng bộ. Callback giúp ứng dụng quan sát thành công hoặc lỗi sau khi broker phản hồi. Nếu bỏ qua future, lỗi gửi có thể không được ghi nhận ở tầng nghiệp vụ. Tránh chặn thread bằng `get()` trong luồng gửi có lưu lượng cao; nếu nghiệp vụ cần xác nhận đồng bộ thì phải cân nhắc giới hạn thời gian chờ và tác động đến throughput.

### 2.2. Producer chọn nơi ghi như thế nào?

Một Kafka record có topic, partition, key, value, timestamp và headers.

- **Topic** xác định luồng dữ liệu logic, ví dụ `orders`.
- **Partition** là đơn vị lưu trữ và đọc song song. Mỗi partition có log riêng và offset tăng dần.
- **Key** thường được dùng để chọn partition. Với partitioner mặc định, cùng một key thường được định tuyến đến cùng partition khi cấu hình partition không thay đổi.
- **Value** chứa payload, chẳng hạn event JSON.
- **Headers** có thể mang correlation ID, trace ID, schema metadata hoặc thông tin phục vụ xử lý.

Nếu cần giữ thứ tự các event của cùng một đơn hàng, dùng order ID làm key để chúng được ghi vào cùng partition. Kafka chỉ đảm bảo thứ tự trong một partition; không có thứ tự tổng thể giữa các partition. Khi tăng số partition, cách ánh xạ key sang partition có thể thay đổi, vì vậy cần tính đến ảnh hưởng đối với thứ tự của một key.

Producer serialize key và value theo serializer đã cấu hình, sau đó gom record thành batch. Các batch có thể được nén trước khi gửi. `batch.size`, `linger.ms` và `compression.type` là những thiết lập thường dùng để cân bằng độ trễ, thông lượng và chi phí mạng.

### 2.3. Xác nhận gửi, retry và độ bền

Thiết lập `acks` quyết định mức xác nhận producer chờ từ broker:

| Giá trị | Ý nghĩa | Đánh đổi |
|---|---|---|
| `acks=0` | Producer không chờ broker xác nhận | Độ trễ thấp hơn nhưng khó biết record có được ghi hay không |
| `acks=1` | Chờ leader ghi record và phản hồi | Có thể mất record nếu leader lỗi trước khi replica theo kịp |
| `acks=all` | Chờ các replica hiện thuộc ISR xác nhận theo giao thức Kafka | Độ bền tốt hơn, có thể tăng độ trễ hoặc từ chối ghi khi ISR không đủ |

`acks=all` thường được kết hợp với `min.insync.replicas`. Ví dụ topic có replication factor 3 và min ISR bằng 2: producer chỉ được xác nhận khi có ít nhất hai replica trong ISR đáp ứng điều kiện ghi. Nếu ISR tụt xuống dưới ngưỡng, broker có thể từ chối yêu cầu ghi thay vì chấp nhận một record với mức replication thấp hơn chính sách.

Producer có thể retry khi gặp lỗi tạm thời. Cần phân biệt hai cơ chế:

- **Retry ở Kafka producer** xử lý các lỗi truyền tải hoặc broker tạm thời trong phiên producer.
- **Ứng dụng gửi lại event** sau timeout, restart hoặc khi không chắc lần gửi trước đã thành công hay chưa. Đây có thể là một lần gửi nghiệp vụ mới và có thể tạo bản ghi trùng.

Bật idempotent producer giúp Kafka nhận diện và loại bỏ duplicate phát sinh từ retry nội bộ của producer trong phạm vi cơ chế producer ID và sequence number. Cơ chế này không tự loại bỏ mọi lần ứng dụng gửi lại cùng một event sau khi khởi động lại, cũng không làm cho thao tác ở cơ sở dữ liệu của consumer trở thành exactly-once.

Một cấu hình producer đáng cân nhắc cho luồng cần độ bền:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
~~~

Các giá trị timeout phải phù hợp với SLA và thời gian phục hồi của hệ thống. `delivery.timeout.ms` giới hạn tổng thời gian producer chờ hoàn tất việc gửi, bao gồm các lần retry; timeout không luôn chứng minh rằng broker chưa ghi record. Khi kết quả gửi không rõ ràng, event ID ổn định và xử lý idempotent ở consumer giúp kiểm soát khả năng trùng lặp.

### 2.4. Transaction ở producer

Kafka transaction cho phép ghi một nhóm record theo cách nguyên tử trong Kafka. Consumer được cấu hình đọc theo isolation level phù hợp có thể tránh nhìn thấy các record thuộc transaction đã abort.

Transaction đặc biệt hữu ích trong luồng consume-process-produce: ứng dụng đọc record đầu vào, tạo record đầu ra và commit offset đầu vào trong cùng một Kafka transaction. Nếu transaction abort, record đầu ra không được xem là đã commit và offset đầu vào cũng không được tiến lên như một lần xử lý thành công.

Transaction Kafka không bao gồm thao tác ở database, HTTP service hoặc hệ thống bên ngoài. Nếu listener cập nhật database rồi gửi event Kafka, cần một thiết kế phối hợp như transactional outbox hoặc inbox/idempotency; chỉ bật Kafka transaction không tạo ra transaction phân tán với database.

## 3. Broker: nơi lưu log và phân phối bản ghi

### 3.1. Topic, partition, offset và replica

Một topic được chia thành một hoặc nhiều partition. Mỗi partition là một log append-only: record mới được nối vào cuối log và có offset xác định trong partition đó.

Ví dụ:

| Partition | Các offset |
|---|---|
| `orders-0` | 0, 1, 2, 3, ... |
| `orders-1` | 0, 1, 2, 3, ... |
| `orders-2` | 0, 1, 2, 3, ... |

Offset chỉ có ý nghĩa trong partition tương ứng. Offset 12 của `orders-0` không phải cùng một vị trí với offset 12 của `orders-1`.

Với replication factor lớn hơn 1, mỗi partition có một leader và các follower replica. Producer ghi vào leader; follower sao chép log từ leader. Consumer cũng fetch từ leader theo giao thức Kafka thông thường. Khi leader gặp sự cố, Kafka có thể bầu một replica đủ điều kiện trong ISR làm leader mới.

**ISR (in-sync replicas)** là tập replica đang theo kịp leader theo tiêu chí của Kafka. Sự kết hợp giữa replication factor, ISR, `acks` và `min.insync.replicas` quyết định mức chịu lỗi khi ghi. Replication factor cao tự nó chưa đủ nếu producer dùng xác nhận yếu hoặc cấu hình ISR không phù hợp.

### 3.2. Broker không xóa record khi consumer xử lý xong

Kafka lưu record theo chính sách retention, thường dựa trên thời gian hoặc dung lượng. Consumer đọc và commit offset không làm record bị xóa ngay. Nhiều consumer group có thể đọc cùng một topic độc lập, mỗi group giữ offset riêng.

Điều này cho phép:

- Một group phục vụ xử lý thanh toán.
- Một group khác xây dựng read model.
- Một group khác phục vụ analytics.

Mỗi group có tiến độ đọc riêng. Nếu một group bị chậm, record vẫn có thể còn trong Kafka miễn là chưa hết retention hoặc bị loại bỏ theo chính sách lưu trữ của topic.

### 3.3. Những thiết lập broker/topic cần xem cùng nhau

- **Replication factor**: số bản sao của mỗi partition.
- **min.insync.replicas**: số replica tối thiểu trong ISR để chấp nhận ghi với `acks=all`.
- **retention.ms / retention.bytes**: giới hạn thời gian hoặc dung lượng lưu log.
- **cleanup.policy**: chính sách dọn log, thường là `delete` hoặc `compact` tùy loại dữ liệu.
- **Số partition**: ảnh hưởng đến khả năng song song, phân phối tải, số consumer hoạt động và thứ tự theo key.

Chọn số partition cần tính đến throughput dự kiến, kích thước cụm, số consumer và yêu cầu ordering. Tạo quá nhiều partition cũng làm tăng chi phí metadata, file, memory và hoạt động replication.

## 4. Consumer: đọc partition theo consumer group

### 4.1. Consumer group và partition assignment

Consumer group là tập consumer dùng chung một group ID. Kafka phân phối các partition của topic cho các consumer trong group đó. Tại một thời điểm, một partition được gán cho tối đa một consumer trong cùng group, nhưng các group khác nhau có thể đọc cùng partition độc lập.

Ví dụ topic có 6 partition:

- Một group có 1 consumer: consumer đó có thể nhận cả 6 partition.
- Một group có 3 consumer: các partition được phân phối giữa 3 consumer.
- Một group có 8 consumer: tối đa 6 consumer có partition để đọc; những consumer còn lại có thể nhàn rỗi.

Trong Spring Kafka, thuộc tính `concurrency` của listener container có thể tạo nhiều consumer thread. Đây là số consumer trong container, không có nghĩa một record tự động được xử lý song song bởi nhiều thread. Số consumer có việc làm hữu ích còn phụ thuộc số partition được gán cho group.

Khi consumer được thêm/bớt, hoặc partition thay đổi, Kafka thực hiện rebalance. Partition có thể được thu hồi từ consumer cũ và gán cho consumer khác. Ứng dụng cần xử lý graceful shutdown, tránh công việc kéo dài không kiểm soát và chấp nhận khả năng record được giao lại trong các tình huống lỗi hoặc rebalance.

### 4.2. Poll, fetch và offset

Kafka consumer dùng vòng lặp `poll()` để lấy record từ broker. Spring listener container quản lý vòng lặp này; phương thức `@KafkaListener` không phải nơi tự gọi poll.

Mỗi consumer group lưu committed offset theo từng partition. Offset đã commit thể hiện vị trí tiếp theo group sẽ đọc. Ví dụ xử lý thành công record offset 7 thì committed offset thường là 8.

Hai cấu hình có ý nghĩa lớn:

- `enable.auto.commit=false`: để Spring listener container điều phối commit theo acknowledgment mode. Đây thường là lựa chọn phù hợp cho listener cần gắn commit với kết quả xử lý.
- `auto.offset.reset`: quyết định vị trí bắt đầu khi group chưa có committed offset hợp lệ. `earliest` bắt đầu từ record sớm nhất còn được giữ; `latest` bắt đầu từ record mới được ghi sau thời điểm khởi tạo. Thiết lập này không tự đưa một group đang có offset hợp lệ quay lại đầu topic.

Nếu bật auto commit, offset có thể được commit theo chu kỳ poll mà không phản ánh chính xác listener đã hoàn thành nghiệp vụ hay chưa. Khi ứng dụng lỗi sau khi offset được commit nhưng trước khi xử lý xong, record có thể bị bỏ qua ở lần đọc tiếp theo. Vì vậy, listener container thường được dùng cùng auto commit tắt để kiểm soát thời điểm commit.

### 4.3. Thời gian xử lý và rebalance

Consumer phải tiếp tục poll trong giới hạn cấu hình. Nếu việc xử lý record hoặc cả batch kéo dài quá `max.poll.interval.ms`, consumer có thể bị xem là không còn hoạt động đúng hạn và partition được rebalance sang consumer khác. Điều này có thể dẫn đến xử lý lặp khi record cũ chưa được commit.

Một số hướng xử lý:

- Giới hạn công việc mỗi poll bằng `max.poll.records` sao cho thời gian xử lý phù hợp.
- Đặt timeout cho lời gọi đến database hoặc service bên ngoài.
- Tránh chạy tác vụ không giới hạn thời gian trực tiếp trên listener thread.
- Điều chỉnh `max.poll.interval.ms` dựa trên thời gian xử lý thực tế, đồng thời theo dõi rebalance và consumer lag.
- Dùng concurrency phù hợp với số partition và năng lực downstream.

Không nên chỉ tăng timeout để che một listener bị nghẽn. Cần xác định phần công việc nào đang giữ poll thread quá lâu và tác động của nó đến commit, retry và thứ tự xử lý.

## 5. Listener: nơi mã nghiệp vụ nhận và xử lý record

### 5.1. Listener container và @KafkaListener

`@KafkaListener` đánh dấu phương thức nhận message. Spring tạo listener endpoint và listener container dựa trên cấu hình; container quản lý consumer, poll, chuyển đổi payload, gọi phương thức listener, áp dụng error handler và commit offset.

Ví dụ:

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
        topics = "orders",
        groupId = "billing-service"
    )
    public void onOrderCreated(
        OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset
    ) {
        log.info(
            "Received order {} from partition {} at offset {}",
            event.orderId(),
            partition,
            offset
        );

        // Validate event and execute an idempotent business operation.
    }
}
~~~

Spring có thể chuyển payload đã deserialize thành kiểu tham số của listener. Header như partition, offset, key, timestamp và topic giúp ghi log, chẩn đoán và truy vết. Nếu ứng dụng cần truy cập toàn bộ metadata hoặc tự điều khiển acknowledgment, có thể dùng các tham số listener tương ứng như `ConsumerRecord` hoặc `Acknowledgment`.

`groupId` trên annotation có thể chỉ định group cho endpoint. Nếu không chỉ định, listener có thể dùng group ID được cấu hình ở consumer factory. Khi một ứng dụng có nhiều listener, cần xác định rõ listener nào dùng chung group và listener nào cần group riêng.

### 5.2. Khi nào offset được commit?

Spring Kafka cung cấp các acknowledgment mode cho listener container. Tên và chi tiết cấu hình cần được đối chiếu với phiên bản Spring Kafka đang dùng, nhưng các ý nghĩa phổ biến là:

| Ack mode | Thời điểm commit |
|---|---|
| `RECORD` | Sau khi từng record được listener xử lý thành công |
| `BATCH` | Sau khi xử lý xong các record của một lần poll |
| `TIME` / `COUNT` / `COUNT_TIME` | Khi đạt điều kiện thời gian hoặc số lượng đã cấu hình |
| `MANUAL` | Ứng dụng gọi acknowledge; container commit theo cơ chế của mode |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge được gọi trong điều kiện thread phù hợp |

`BATCH` là mode mặc định thường gặp của listener container. `RECORD` phù hợp khi muốn gắn tiến độ commit sát với từng record và đang dùng record listener. Với batch listener, cần chọn mode phù hợp với cách listener xử lý cả batch.

Ví dụ manual acknowledgment:

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrderCreated(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    processOrder(event);
    acknowledgment.acknowledge();
}
~~~

Chỉ acknowledge sau khi công việc cần thiết đã hoàn tất. Nếu acknowledge trước khi thao tác nghiệp vụ thành công, ứng dụng có thể commit offset rồi mất cơ hội xử lý lại record. Với xử lý bất đồng bộ, cần cấu hình và dùng acknowledgment theo đúng hợp đồng thread của container; không giữ acknowledgment rồi gọi tùy tiện từ thread nền.

### 5.3. Exception và error handler

Nếu phương thức listener ném exception, container có thể chuyển lỗi đến error handler. Nếu listener bắt exception rồi bỏ qua, container thường xem lần gọi đó là thành công và tiếp tục theo acknowledgment mode. Vì vậy, chỉ catch lỗi khi mã ứng dụng có cách xử lý rõ ràng; nếu muốn retry hoặc đưa vào DLT thì cần để lỗi đến cơ chế tương ứng.

Trong Spring Kafka, `DefaultErrorHandler` thường được dùng để retry có backoff và phục hồi sau số lần thử đã định. `DeadLetterPublishingRecoverer` có thể publish record lỗi sang dead-letter topic (DLT). Cần cấu hình producer/serializer của DLT phù hợp với kiểu payload, đặc biệt khi lỗi xảy ra trong quá trình deserialize và payload gốc chỉ còn dạng byte array.

Một chiến lược phục hồi nên xác định:

1. Lỗi nào có khả năng tạm thời, ví dụ timeout database hoặc service chưa sẵn sàng.
2. Số lần retry và backoff giữa các lần thử.
3. Lỗi nào không thể khắc phục bằng retry, ví dụ payload sai schema hoặc vi phạm quy tắc dữ liệu.
4. DLT nào nhận record sau khi phục hồi thất bại.
5. Ai theo dõi, phân loại và replay record trong DLT.

Retry vô hạn có thể giữ partition không tiến lên và làm tăng consumer lag. Backoff cần có giới hạn; DLT cần có cảnh báo, retention và quy trình xử lý. Nếu recoverer gửi record sang DLT theo partition tương ứng, topic DLT cần có số partition phù hợp với cách ánh xạ đó.

### 5.4. Retry topic và thứ tự xử lý

Spring Kafka cũng hỗ trợ mô hình non-blocking retry topic, ví dụ qua `@RetryableTopic`. Record lỗi được chuyển sang topic retry với thời gian chờ phù hợp rồi được xử lý lại. Cách này giúp partition chính tiếp tục xử lý các record khác trong một số tình huống.

Đổi lại, retry topic có thể làm thay đổi thứ tự quan sát được: record phía sau có thể được xử lý trước record đang chờ retry. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo key, cần đánh giá kỹ chiến lược retry và thiết kế phân vùng trước khi chọn mô hình non-blocking.

### 5.5. Lỗi deserialize

Deserialize xảy ra trước khi listener nhận payload. Nếu JSON sai định dạng hoặc schema không tương thích, phương thức listener có thể chưa được gọi. `ErrorHandlingDeserializer` bọc delegate deserializer để đưa lỗi deserialize vào cơ chế xử lý lỗi của Spring Kafka, giúp container/error handler có thể phục hồi hoặc chuyển record sang DLT.

Với JSON, cần thống nhất serializer, deserializer và cách xác định kiểu dữ liệu. `JsonDeserializer` có thể sử dụng type header do serializer ghi vào; nếu không dùng type header thì cần cấu hình kiểu mặc định hoặc type mapping phù hợp. Chỉ tin cậy các package thực sự cần thiết thay vì mở trusted packages quá rộng.

## 6. Delivery semantics và xử lý trùng lặp

### 6.1. At-most-once, at-least-once và exactly-once

| Semantics | Cách hoạt động khái quát | Hệ quả |
|---|---|---|
| At-most-once | Commit offset trước hoặc tách khỏi xử lý nghiệp vụ | Có thể mất record nếu ứng dụng lỗi sau commit |
| At-least-once | Xử lý trước, commit offset sau khi thành công | Có thể xử lý lại nếu lỗi xảy ra sau side effect nhưng trước commit |
| Exactly-once trong Kafka | Kafka transaction phối hợp record đầu ra và offset đầu vào trong cùng transaction | Tránh để output/offset chỉ commit một nửa trong luồng Kafka-to-Kafka |

At-least-once thường là lựa chọn thực tế cho listener xử lý nghiệp vụ. Ví dụ: listener cập nhật database thành công, nhưng ứng dụng dừng trước khi commit Kafka offset. Sau khi rebalance hoặc khởi động lại, record được giao lại và thao tác database có thể chạy lần nữa.

Vì vậy, listener nên có tính idempotent. Một số cách phổ biến:

- Mỗi event có event ID ổn định; database lưu ID đã xử lý và đặt unique constraint.
- Dùng upsert hoặc cập nhật trạng thái theo điều kiện để cùng một event không tạo side effect lần thứ hai.
- Dùng inbox table để ghi nhận event đã tiếp nhận trong cùng transaction với cập nhật nghiệp vụ.
- Dùng transactional outbox khi cần cập nhật database và phát event tiếp theo mà không tạo khoảng hở giữa hai thao tác.

Producer idempotence xử lý duplicate do retry ở tầng Kafka producer. Consumer idempotency xử lý việc cùng một event được giao lại hoặc được publish lại từ tầng ứng dụng. Đây là hai lớp bảo vệ khác nhau.

### 6.2. Exactly-once khi consume và produce trong Kafka

Trong luồng Kafka-to-Kafka, Spring Kafka có thể phối hợp transaction-capable producer factory, listener container và Kafka transaction manager để gửi output record và commit input offset trong cùng transaction. Consumer phía sau thường dùng isolation level `read_committed` để chỉ đọc record thuộc transaction đã commit.

Cơ chế này phù hợp với ví dụ đọc `orders` rồi ghi `billing-events`. Nó không bao phủ cập nhật database hoặc gọi REST API. Nếu listener vừa ghi database vừa publish Kafka, cần thiết kế outbox/inbox hoặc một cơ chế phối hợp có tính idempotent để xử lý lỗi giữa hai hệ thống.

## 7. Cấu hình nền tảng minh họa

Ví dụ YAML sau minh họa một producer gửi JSON và một consumer group nhận JSON qua listener container. Cấu hình thực tế còn phụ thuộc phiên bản Spring Boot, Spring Kafka, schema và chính sách bảo mật của cụm.

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000

    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.events

    listener:
      ack-mode: record
~~~

Một số lưu ý khi áp dụng:

- `bootstrap-servers` chỉ ra địa chỉ bootstrap để client khám phá broker trong cụm; đây không nhất thiết là toàn bộ broker list.
- `acks: all` và `enable.idempotence: true` tăng độ tin cậy gửi; phía broker/topic vẫn cần replication và min ISR phù hợp.
- `enable-auto-commit: false` để container gắn commit với quá trình xử lý.
- `auto-offset-reset: earliest` chỉ có tác dụng khi group chưa có offset hợp lệ.
- `ErrorHandlingDeserializer` dùng `JsonDeserializer` làm delegate để lỗi deserialize có thể đi qua cơ chế xử lý lỗi.
- `spring.json.trusted.packages` nên giới hạn ở package chứa event được phép deserialize. Nếu producer không gửi type header hoặc các service dùng class khác nhau, cần cấu hình default type/type mapping rõ ràng.
- `ack-mode: record` giúp commit theo từng record sau khi listener thành công; nếu listener dùng batch, hãy chọn acknowledgment mode tương ứng.

Các thiết lập như replication factor và min ISR thuộc cấu hình broker hoặc topic, không được thay thế bằng cấu hình producer trong ứng dụng. Một ví dụ chính sách topic là replication factor 3 và min ISR 2, với điều kiện cụm có đủ broker và topology phù hợp.

## 8. Quan sát và chẩn đoán luồng

Để xác định vấn đề nằm ở producer, broker, consumer hay listener, theo dõi chỉ số ở từng chặng.

| Khu vực | Chỉ số hoặc thông tin cần theo dõi | Dấu hiệu cần điều tra |
|---|---|---|
| Producer | Send success/error, retry, request latency, timeout, buffer exhaustion | Tăng timeout, retry liên tục hoặc lỗi gửi |
| Broker | Offline partition, under-replicated partition, ISR shrink, disk và network | Replica tụt lại, leader thay đổi liên tục, thiếu dung lượng |
| Consumer group | Consumer lag theo partition, số lần rebalance, tốc độ fetch | Lag tăng kéo dài hoặc partition liên tục đổi owner |
| Listener | Processing duration, exception rate, retry count, DLT rate | Một loại record gây lỗi lặp hoặc listener xử lý quá lâu |
| Nghiệp vụ | Event ID, correlation ID, kết quả idempotency, trạng thái outbox/inbox | Event trùng, thiếu event hoặc side effect không nhất quán |

Consumer lag là khoảng cách giữa vị trí record mới nhất và committed offset của group; cần xem theo từng partition để tìm partition bị nghẽn. Lag tăng không tự chỉ ra nguyên nhân: producer có thể tăng tải, consumer có thể giảm tốc độ, hoặc listener đang retry một record lỗi.

Log nên có topic, partition, offset, key hoặc event ID và correlation ID để nối các bước xử lý. Tránh ghi toàn bộ payload nếu chứa dữ liệu nhạy cảm. Với DLT, cần theo dõi số record mới, loại exception, nguồn topic/partition/offset và kết quả replay.

## 9. Các tình huống vận hành thường gặp

| Tình huống | Cách luồng phản ứng | Hướng kiểm tra |
|---|---|---|
| Producer timeout | Kết quả gửi có thể chưa rõ: broker có thể đã ghi record nhưng response bị mất | Kiểm tra broker/network và retry; dùng event ID ổn định cùng consumer idempotency |
| Leader partition lỗi | Kafka bầu leader mới từ replica đủ điều kiện trong ISR | Kiểm tra replication factor, ISR, under-replicated partition và cấu hình acks |
| Listener ném exception tạm thời | Error handler retry theo backoff; có thể chuyển DLT sau khi hết lượt | Kiểm tra downstream, timeout, số lần retry và DLT |
| Payload không deserialize được | Listener có thể chưa được gọi; lỗi đi qua ErrorHandlingDeserializer/error handler | Kiểm tra serializer, schema, type header, trusted packages và payload gốc |
| Consumer xử lý quá lâu | Có thể vượt max poll interval và gây rebalance | Đo processing duration, giảm công việc mỗi poll hoặc tách tác vụ dài |
| Event được xử lý hai lần | Có thể xảy ra khi side effect thành công nhưng offset chưa commit | Dùng event ID, unique constraint, inbox hoặc thao tác idempotent |
| Consumer lag tăng | Tốc độ phát lớn hơn tốc độ xử lý hoặc một số partition bị nghẽn | So sánh producer rate, consumer throughput, lag theo partition, retry và thời gian listener |

Khi điều tra một record cụ thể, lần theo cùng một event ID qua producer log, metadata gửi thành công, topic/partition/offset, consumer group và listener log. Cách lần theo này giúp phân biệt record chưa từng được publish, record đã nằm trong broker nhưng chưa được group đọc, record đang retry, và record đã xử lý nhưng chưa commit offset.

## 10. Nguyên tắc thiết kế luồng đáng tin cậy

- Chọn key theo thực thể cần giữ thứ tự, đồng thời chọn số partition dựa trên mức song song thực tế.
- Dùng `acks=all`, idempotent producer và replication/min ISR phù hợp với mức độ quan trọng của dữ liệu.
- Tắt auto commit khi cần gắn offset với kết quả listener; chọn acknowledgment mode theo record hay batch.
- Thiết kế listener idempotent vì redelivery là tình huống bình thường trong at-least-once.
- Phân loại lỗi retry được và lỗi không retry được; đặt backoff có giới hạn, DLT có giám sát và quy trình replay.
- Giữ thời gian xử lý trong giới hạn poll, đặt timeout cho downstream và theo dõi rebalance.
- Dùng Kafka transaction cho luồng Kafka-to-Kafka cần atomicity; dùng outbox/inbox hoặc idempotency cho ranh giới database và hệ thống ngoài Kafka.
- Theo dõi producer errors, trạng thái replication, consumer lag, thời gian listener và tỷ lệ DLT như một chuỗi chỉ số liên kết.

Khi các thành phần này được cấu hình nhất quán, producer có thể biết kết quả gửi, broker có thể duy trì bản sao theo chính sách, consumer có thể theo dõi tiến độ theo partition và listener có thể phục hồi có kiểm soát khi xử lý lỗi. Độ tin cậy của toàn luồng phụ thuộc vào cách các lớp phối hợp, đặc biệt là quan hệ giữa xử lý nghiệp vụ và commit offset.
