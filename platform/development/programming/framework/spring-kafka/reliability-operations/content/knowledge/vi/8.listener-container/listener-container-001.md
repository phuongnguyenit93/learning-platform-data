# KafkaMessageListenerContainer

Trong Spring Kafka, **KafkaMessageListenerContainer** là thành phần quản lý vòng đời và vòng lặp đọc dữ liệu của một Kafka consumer. Container tạo consumer thông qua ConsumerFactory, subscribe hoặc assign partition theo cấu hình, gọi listener khi poll nhận được record, quản lý offset, phối hợp rebalance và dừng consumer có kiểm soát.

Đây là lớp nền tảng của mô hình listener container trong Spring Kafka. Một KafkaMessageListenerContainer quản lý **một Kafka Consumer** và xử lý các poll trên một consumer thread. Khi cần nhiều consumer song song, Spring Kafka cung cấp **ConcurrentMessageListenerContainer**, lớp điều phối nhiều KafkaMessageListenerContainer con.

Hiểu đúng vai trò của KafkaMessageListenerContainer giúp thiết kế concurrency, commit offset, xử lý lỗi và lifecycle rõ ràng. Nó cũng giúp phân biệt container do ứng dụng tạo trực tiếp với container được tạo tự động từ @KafkaListener.

## 1. Vị trí của KafkaMessageListenerContainer trong kiến trúc Spring Kafka

Kafka Java client cung cấp KafkaConsumer với các thao tác như subscribe, poll, commitSync, commitAsync, pause và resume. Nếu ứng dụng tự dùng KafkaConsumer, ứng dụng phải tự quản lý vòng lặp poll, lifecycle, thread, rebalance và nhiều chi tiết vận hành.

Spring Kafka đặt một lớp quản lý phía trên KafkaConsumer. KafkaMessageListenerContainer nhận cấu hình từ ContainerProperties, lấy consumer từ ConsumerFactory và điều phối quá trình đọc message.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Spring application"] --> B["KafkaMessageListenerContainer"]
    B --> C["ConsumerFactory"]
    C --> D["KafkaConsumer"]
    D --> E["subscribe / assign"]
    E --> F["poll loop"]
    F --> G["MessageListener"]
    G --> H["Business processing"]
    H --> I["Offset acknowledgment / commit"]
    B --> J["Lifecycle, pause/resume, events"]
    B --> K["Error handling and rebalance coordination"]
~~~

Các trách nhiệm chính của container:

- Tạo và đóng KafkaConsumer thông qua ConsumerFactory.
- Quản lý subscribe theo topic, topic pattern hoặc assignment theo partition.
- Chạy vòng lặp poll trên consumer thread.
- Chuyển record hoặc batch record tới listener đã cấu hình.
- Phối hợp ack mode và việc commit offset.
- Xử lý các callback liên quan đến rebalance.
- Phối hợp error handler và transaction manager khi được cấu hình.
- Cung cấp lifecycle start/stop, pause/resume và các tín hiệu vận hành.

Container không phải broker, không lưu dữ liệu và không tự quyết định nghiệp vụ của message. Nó quản lý cách ứng dụng lấy record từ Kafka và bàn giao record cho listener.

## 2. KafkaMessageListenerContainer quản lý một consumer

Điểm quan trọng nhất của lớp này là quan hệ một container với một KafkaConsumer. Consumer đó có thể được gán một hoặc nhiều partition, nhưng các lần poll và việc gọi listener của container diễn ra trên consumer thread tương ứng.

Ví dụ, topic orders có sáu partition. Một KafkaMessageListenerContainer trong group có thể nhận cả sáu partition nếu không có member nào khác trong group. Container vẫn chỉ dùng một consumer để xử lý các partition được gán.

~~~mermaid
flowchart TD
    G["Consumer group: orders-reader"] --> C["KafkaMessageListenerContainer"]
    C --> K["One KafkaConsumer"]
    K --> P0["Partition 0"]
    K --> P1["Partition 1"]
    K --> P2["Partition 2"]
    K --> P3["Partition 3"]
    K --> P4["Partition 4"]
    K --> P5["Partition 5"]
~~~

Một consumer có thể xử lý nhiều partition, nhưng trong cùng consumer, thứ tự xử lý được điều phối bởi vòng lặp poll và listener. Nếu listener xử lý record chậm, các record khác được poll trên cùng consumer có thể phải chờ xử lý.

Container không tạo một thread riêng cho từng partition. Muốn tăng mức song song, cần tăng số consumer trong group bằng nhiều container hoặc dùng ConcurrentMessageListenerContainer với concurrency phù hợp.

### 2.1 Phân biệt với ConcurrentMessageListenerContainer

Hai lớp thường được nhắc cùng nhau:

| Đặc điểm | KafkaMessageListenerContainer | ConcurrentMessageListenerContainer |
|---|---|---|
| Số consumer | Một consumer | Một hoặc nhiều consumer con |
| Cách chạy | Một consumer thread | Mỗi child container có consumer thread riêng |
| Phân phối partition | Consumer được group coordinator gán partition | Nhiều consumer cùng group chia partition |
| Mục đích | Quản lý một consumer | Điều phối concurrency trong một endpoint |
| Cấu hình listener | ContainerProperties | ContainerProperties được dùng cho các child container |

ConcurrentMessageListenerContainer không thay thế KafkaMessageListenerContainer ở tầng thấp. Nó tạo và quản lý nhiều KafkaMessageListenerContainer con.

Nếu concurrency bằng 3, wrapper thường tạo ba child container, mỗi child sở hữu một KafkaConsumer. Các consumer này tham gia cùng group id và Kafka phân phối partition giữa chúng.

~~~mermaid
flowchart TD
    P["ConcurrentMessageListenerContainer<br/>concurrency = 3"] --> C1["KafkaMessageListenerContainer 1"]
    P --> C2["KafkaMessageListenerContainer 2"]
    P --> C3["KafkaMessageListenerContainer 3"]
    C1 --> K1["KafkaConsumer 1"]
    C2 --> K2["KafkaConsumer 2"]
    C3 --> K3["KafkaConsumer 3"]
~~~

Nếu có bốn pod và mỗi pod có concurrency 3, một logical consumer group có thể có tối đa 12 consumer. Số consumer thực sự nhận partition vẫn bị giới hạn bởi số partition được subscribe. Nếu topic có sáu partition, tối đa sáu consumer có thể được gán partition tại một thời điểm; các consumer còn lại không nhận partition.

### 2.2 Quan hệ với @KafkaListener

Trong ứng dụng Spring, phần lớn listener được khai báo bằng @KafkaListener. Spring Kafka tạo endpoint và container thông qua KafkaListenerContainerFactory.

Factory mặc định thường tạo ConcurrentMessageListenerContainer, ngay cả khi concurrency là 1. Khi đó wrapper có một KafkaMessageListenerContainer con. Vì vậy, khi đọc log hoặc debug runtime, có thể thấy cả tên container cấp endpoint lẫn các child container.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-reader",
    concurrency = "3"
)
public void handle(String payload) {
    orderService.process(payload);
}
~~~

Đoạn annotation khai báo listener ở tầng endpoint. Ứng dụng không trực tiếp gọi constructor KafkaMessageListenerContainer. Factory tạo wrapper và child container, sau đó quản lý lifecycle cho chúng.

Dùng KafkaMessageListenerContainer trực tiếp phù hợp khi cần kiểm soát container ở cấp thấp, tạo subscription động hoặc tích hợp một listener ngoài mô hình annotation. Với ứng dụng thông thường, @KafkaListener và container factory giúp giảm phần lifecycle code phải tự quản lý.

## 3. Các cách chỉ định topic và partition

KafkaMessageListenerContainer nhận ContainerProperties để biết consumer cần đọc ở đâu và xử lý thế nào. Có ba cách cấu hình nguồn dữ liệu thường gặp.

### 3.1 Subscribe theo tên topic

Dùng danh sách topic khi consumer group cần tham gia cơ chế assignment do Kafka quản lý:

~~~java
ContainerProperties properties =
    new ContainerProperties("orders", "order-updates");
~~~

Consumer subscribe các topic này. Group coordinator phối hợp các member trong group để gán partition. Khi member gia nhập hoặc rời group, Kafka có thể thực hiện rebalance.

Cách này phù hợp với consumer group có nhiều instance, cần tự động phân phối partition và muốn Kafka quản lý membership.

### 3.2 Subscribe theo topic pattern

Có thể dùng Pattern để subscribe các topic khớp biểu thức chính quy:

~~~java
Pattern topicPattern = Pattern.compile("orders-.*");
ContainerProperties properties =
    new ContainerProperties(topicPattern);
~~~

Cách này hữu ích khi topic được tạo theo quy ước và consumer cần theo dõi một tập topic động. Consumer định kỳ cập nhật metadata theo cơ chế của Kafka client và có thể phát hiện topic mới khớp pattern.

Cần kiểm soát pattern chặt chẽ. Một biểu thức quá rộng có thể khiến consumer vô tình subscribe topic ngoài phạm vi nghiệp vụ hoặc nhận dữ liệu từ môi trường khác nếu dùng chung cluster.

### 3.3 Gán partition cụ thể

Nếu ứng dụng cần kiểm soát partition assignment, có thể cấu hình TopicPartitionInitialOffset:

~~~java
ContainerProperties properties =
    new ContainerProperties(
        new TopicPartitionInitialOffset("orders", 0),
        new TopicPartitionInitialOffset("orders", 1)
    );
~~~

Trong chế độ chỉ định partition trực tiếp, ứng dụng chịu trách nhiệm xác định partition nào thuộc container. Cách này khác với subscribe theo group: consumer không dựa vào group coordinator để chia assignment tự động theo cùng cách.

Có thể dùng khi một ứng dụng sở hữu partition cụ thể hoặc khi triển khai luồng đọc có kiểm soát. Phải tránh để nhiều consumer cùng assign một partition mà không có cơ chế phối hợp, vì chúng có thể đọc trùng và commit offset cạnh tranh.

Các overload của TopicPartitionInitialOffset cho phép chỉ định offset ban đầu hoặc timestamp theo phiên bản Spring Kafka. Khi dùng initial offset, cần hiểu rõ semantics của absolute offset, relative offset và việc offset đã commit của group có được ưu tiên hay không theo cấu hình cụ thể.

### 3.4 Chọn cách subscribe phù hợp

| Nhu cầu | Cách cấu hình |
|---|---|
| Một logical group đọc topic cố định | Danh sách topic |
| Theo dõi topic mới theo quy tắc tên | Topic pattern |
| Chỉ đọc một số partition đã xác định | TopicPartitionInitialOffset |
| Scale consumer tự động theo group | Subscribe theo topic hoặc pattern |
| Assignment do ứng dụng tự quản lý | Gán partition cụ thể, kèm runbook rõ ràng |

Không chọn direct partition assignment chỉ để tránh rebalance nếu hệ thống vẫn cần group coordination. Assignment thủ công chuyển thêm trách nhiệm phân phối, failover và tránh trùng partition sang ứng dụng.

## 4. ContainerProperties: cấu hình hoạt động của container

ContainerProperties là đối tượng cấu hình trung tâm của KafkaMessageListenerContainer. Nó mô tả subscription, listener và nhiều tham số điều khiển vòng lặp poll, ack, transaction và lifecycle.

Các nhóm cấu hình thường gặp:

| Nhóm | Ví dụ thuộc tính | Vai trò |
|---|---|---|
| Subscription | topics, topicPattern, topicPartitions | Xác định nguồn record |
| Listener | messageListener | Listener được container gọi |
| Polling | pollTimeout | Thời gian chờ trong poll |
| Offset | ackMode, syncCommits | Cách xác nhận và commit offset |
| Rebalance | consumerRebalanceListener | Callback khi partition được revoke/assign |
| Lifecycle | shutdownTimeout, idleEventInterval | Dừng container và phát hiện trạng thái idle |
| Transaction | Kafka-aware transaction manager | Phối hợp transaction và offset |
| Monitoring | monitorInterval, noPollThreshold | Phát hiện consumer không poll đúng kỳ vọng |

Tên và khả năng của một số thuộc tính có thể khác giữa các phiên bản Spring Kafka. Khi cấu hình dự án thật, cần đối chiếu API của phiên bản đang dùng.

### 4.1 Listener

Listener là phần xử lý record do container poll được. Spring Kafka hỗ trợ các loại listener theo record hoặc batch, có thể nhận acknowledgment hoặc consumer tùy interface.

Các interface thường gặp:

- MessageListener: nhận từng ConsumerRecord.
- AcknowledgingMessageListener: nhận record cùng Acknowledgment để xác nhận thủ công.
- ConsumerAwareMessageListener: nhận thêm Kafka Consumer khi listener cần thông tin consumer.
- BatchMessageListener: nhận một danh sách record từ một lần poll.
- BatchAcknowledgingMessageListener: xử lý batch và có acknowledgment.
- BatchConsumerAwareMessageListener: nhận batch và consumer.

Chọn listener interface phù hợp với mô hình xử lý. Không cấu hình một listener dạng batch rồi xử lý như record listener hoặc ngược lại.

### 4.2 Poll timeout

Poll timeout xác định thời gian consumer chờ trong một lần poll khi chưa có record. Đây là một phần của nhịp đọc, nhưng không thay thế max.poll.interval.ms của Kafka client.

Hai khái niệm khác nhau:

- pollTimeout là thời gian một lời gọi poll chờ dữ liệu.
- max.poll.interval.ms là giới hạn giữa các lần poll tiếp theo trước khi consumer có thể bị xem là không tiến triển và rời group.

Nếu listener xử lý batch quá lâu, container có thể không gọi poll kịp giới hạn max.poll.interval.ms. Cần điều chỉnh max.poll.records, thời gian xử lý, concurrency và timeout downstream thay vì chỉ tăng poll timeout.

### 4.3 Shutdown timeout

Khi ứng dụng dừng, container cần ngừng nhận thêm công việc và đóng consumer có kiểm soát. Shutdown timeout đặt giới hạn thời gian chờ cho quá trình dừng tùy cơ chế lifecycle và phiên bản.

Nếu listener đang xử lý một record lâu, shutdown có thể chờ listener hoàn tất trong giới hạn cấu hình. Khi hết thời gian, việc dừng có thể dẫn đến record chưa commit được đọc lại sau đó.

Vì vậy, shutdown timeout phải phối hợp với thời gian xử lý tối đa, thời gian commit và orchestration termination grace period. Không nên đặt timeout quá ngắn khiến mỗi lần deploy đều tạo nhiều lần xử lý lại; cũng không nên để container chờ vô hạn.

## 5. Tạo KafkaMessageListenerContainer trực tiếp

Trong trường hợp cần tạo container bằng Java, trước hết cần có ConsumerFactory. Factory chịu trách nhiệm tạo KafkaConsumer với bootstrap servers, group id, deserializer, security và các client properties.

Ví dụ dưới đây minh họa consumer đọc chuỗi từ topic orders:

~~~java
@Bean
ConsumerFactory<String, String> ordersConsumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "kafka-1:9092,kafka-2:9092,kafka-3:9092"
    );
    props.put(
        ConsumerConfig.GROUP_ID_CONFIG,
        "orders-reader"
    );
    props.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    props.put(
        ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
        false
    );

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

Sau đó tạo ContainerProperties và KafkaMessageListenerContainer:

~~~java
@Bean
KafkaMessageListenerContainer<String, String> ordersListenerContainer(
        ConsumerFactory<String, String> ordersConsumerFactory) {

    ContainerProperties containerProperties =
        new ContainerProperties("orders");

    containerProperties.setPollTimeout(1500);
    containerProperties.setAckMode(
        ContainerProperties.AckMode.RECORD
    );

    containerProperties.setMessageListener(
        (MessageListener<String, String>) record -> {
            System.out.printf(
                "topic=%s partition=%d offset=%d key=%s value=%s%n",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                record.value()
            );
        }
    );

    return new KafkaMessageListenerContainer<>(
        ordersConsumerFactory,
        containerProperties
    );
}
~~~

Trong ví dụ:

- ConsumerFactory tạo consumer với group id orders-reader.
- ContainerProperties subscribe topic orders.
- MessageListener nhận từng ConsumerRecord.
- AckMode.RECORD yêu cầu commit sau khi listener xử lý từng record theo cơ chế container.
- KafkaMessageListenerContainer quản lý consumer thread và lifecycle.

Khi container được khai báo thành bean Spring, lifecycle của container thường được ApplicationContext quản lý theo SmartLifecycle và auto-startup. Không cần gọi start thủ công trong phương thức tạo bean nếu Spring đang quản lý lifecycle mặc định. Nếu tạo container ngoài ApplicationContext, ứng dụng phải gọi start và stop đúng lúc.

### 5.1 Tạo và quản lý container ngoài Spring lifecycle

Ví dụ khi một thành phần tự quản lý container:

~~~java
ContainerProperties properties =
    new ContainerProperties("orders");

properties.setMessageListener(
    (MessageListener<String, String>) record ->
        orderService.process(record.value())
);

KafkaMessageListenerContainer<String, String> container =
    new KafkaMessageListenerContainer<>(
        consumerFactory,
        properties
    );

container.start();

// Khi thành phần sở hữu container cần dừng:
container.stop();
~~~

Trong ứng dụng thật, không gọi start/stop tùy tiện từ nhiều nơi. Cần một owner rõ ràng, bảo đảm container chỉ được khởi động một lần và dừng khi application component đóng. Nếu dùng Spring bean, ưu tiên để Spring quản lý lifecycle.

### 5.2 Cấu hình listener sau khi tạo container

Có thể cấu hình listener trước khi container start thông qua ContainerProperties. Không nên thay đổi listener hoặc consumer configuration tùy tiện khi container đang chạy.

Nếu cần thay listener hoặc subscription, hãy dừng container theo lifecycle, cập nhật cấu hình được hỗ trợ rồi khởi động lại. Với thay đổi động thường xuyên, cân nhắc factory và registry của Spring Kafka thay vì tự sửa object đang xử lý poll.

## 6. Vòng đời của container

KafkaMessageListenerContainer quản lý vòng đời từ lúc khởi động đến lúc đóng consumer. Các trạng thái vận hành cần hiểu gồm tạo, start, poll, pause/resume, rebalance, stop và close.

### 6.1 Khởi động

Khi container start:

1. Container kiểm tra cấu hình và listener.
2. Container yêu cầu ConsumerFactory tạo KafkaConsumer.
3. Consumer subscribe topic, pattern hoặc nhận partition assignment theo cấu hình.
4. Kafka client tham gia group nếu dùng subscribe.
5. Container chạy vòng lặp poll.
6. Khi poll có record, container gọi listener.
7. Sau khi xử lý, container áp dụng ack/commit và tiếp tục poll.

Consumer được tạo và sử dụng trong lifecycle do container quản lý. Ứng dụng không nên lấy consumer nội bộ rồi gọi API từ thread tùy ý vì KafkaConsumer không thread-safe.

### 6.2 Poll loop

Vòng lặp poll là trung tâm hoạt động của container. Nó liên tục lấy record từ broker, xử lý record hoặc batch, thực hiện các thao tác cần thiết rồi tiếp tục poll.

~~~mermaid
flowchart TD
    A["Container started"] --> B["Create KafkaConsumer"]
    B --> C["Subscribe / assign"]
    C --> D["Poll"]
    D --> E{"Có record?"}
    E -->|Có| F["Invoke listener"]
    F --> G["Ack / commit according to mode"]
    G --> D
    E -->|Không| H["Idle / wait"]
    H --> D
    D --> I["Stop requested"]
    I --> J["Finish current work and close consumer"]
~~~

Nếu listener chạy đồng bộ trên consumer thread, thời gian xử lý listener ảnh hưởng trực tiếp thời điểm poll tiếp theo. Một listener bị block lâu có thể làm consumer vượt max.poll.interval.ms và bị group coordinator loại khỏi group.

Vì vậy, cần đo processing time, đặt timeout cho downstream, giới hạn số record mỗi poll và cân nhắc batch size.

### 6.3 Dừng container

Khi stop được yêu cầu, container ngừng vòng lặp poll và đóng consumer theo lifecycle. Việc đóng consumer cho phép Kafka client rời group và giải phóng tài nguyên.

Nếu listener đang xử lý record, container cần hoàn tất hoặc dừng theo cơ chế shutdown và timeout cấu hình. Record chưa commit có thể được giao lại cho member khác sau rebalance hoặc khi container khởi động lại.

Dừng container không có nghĩa record đã được xử lý thành công. Chỉ offset được commit mới xác định vị trí tiếp tục của group. Business side effect cần được bảo vệ bằng idempotency nếu có khả năng xử lý lại.

### 6.4 Pause và resume

Container hỗ trợ pause/resume để tạm dừng nhận record trong khi vẫn giữ lifecycle của consumer. Điều này hữu ích khi downstream tạm thời quá tải hoặc ứng dụng cần điều tiết xử lý.

Pause khác stop:

- Pause yêu cầu consumer tạm ngừng nhận record từ partition đã được gán, nhưng consumer vẫn duy trì membership và tiếp tục poll để giữ group participation.
- Stop đóng consumer và rời group; partition có thể được gán cho member khác.
- Resume cho phép container tiếp tục nhận record sau khi điều kiện phục hồi.

Không nên gọi trực tiếp KafkaConsumer.pause từ thread khác. Hãy dùng API container phù hợp với phiên bản Spring Kafka để container phối hợp thao tác trên consumer thread.

Pause không làm giảm backlog trong Kafka. Nó chỉ ngừng hoặc giảm tốc độ tiêu thụ. Nếu pause kéo dài, lag và tuổi record tăng; cần theo dõi và có ngưỡng resume hoặc scale phù hợp.

## 7. Offset acknowledgment và commit trong container

KafkaMessageListenerContainer phối hợp listener với cơ chế xác nhận offset. Spring Kafka cung cấp AckMode để xác định thời điểm container commit offset đã xử lý.

Nếu dựa vào auto commit của Kafka client, offset có thể được commit theo lịch riêng và không phản ánh chính xác thời điểm business processing hoàn tất. Spring Kafka thường quản lý auto commit ở phía container trong cấu hình hiện đại; cần kiểm tra consumer properties thực tế và không bật auto commit tùy tiện.

### 7.1 Các AckMode chính

| AckMode | Thời điểm commit | Cách dùng |
|---|---|---|
| RECORD | Sau khi từng record được listener xử lý thành công | Record listener cần commit theo từng record |
| BATCH | Sau khi xử lý xong các record từ một lần poll | Mặc định thường dùng cho container |
| TIME | Khi đủ thời gian kể từ lần commit trước | Gom commit theo thời gian |
| COUNT | Khi đủ số record đã xử lý | Gom commit theo số lượng |
| COUNT_TIME | Khi đạt điều kiện thời gian hoặc số lượng | Cân bằng commit frequency |
| MANUAL | Listener gọi acknowledge; commit theo batch semantics của container | Cần ứng dụng kiểm soát xác nhận |
| MANUAL_IMMEDIATE | Commit ngay khi acknowledge trên consumer thread; nếu gọi từ thread khác, xử lý theo cơ chế queue của container | Cần xác nhận tức thời theo ngữ cảnh hỗ trợ |

AckMode.RECORD chỉ phù hợp với record listener, không dùng cho batch listener. AckMode mặc định thường là BATCH nếu ứng dụng không cấu hình khác.

### 7.2 Record listener và batch listener

Record listener xử lý từng record:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-reader"
)
public void handle(String value) {
    orderService.process(value);
}
~~~

Batch listener nhận danh sách record từ một poll:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-batch-reader"
)
public void handleBatch(List<String> values) {
    orderService.processBatch(values);
}
~~~

Batch listener có thể tăng throughput khi nghiệp vụ hỗ trợ xử lý theo lô, nhưng một lỗi trong batch cần chính sách retry/rollback phù hợp. Nếu một record lỗi làm batch thất bại, cần xác định record nào đã tạo side effect và cách xử lý lại an toàn.

### 7.3 Manual acknowledgment

Với AcknowledgingMessageListener hoặc @KafkaListener có tham số Acknowledgment, ứng dụng có thể quyết định thời điểm xác nhận:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-manual-reader"
)
public void handle(
        ConsumerRecord<String, String> record,
        Acknowledgment acknowledgment) {

    orderService.process(record.value());

    acknowledgment.acknowledge();
}
~~~

Trong ví dụ, acknowledge được gọi sau business processing. Nếu process chết trước khi acknowledge, record có thể được đọc lại. Nếu acknowledge trước khi business effect hoàn tất, có nguy cơ offset tiến lên trong khi nghiệp vụ chưa hoàn thành.

Manual ack tăng quyền kiểm soát nhưng cũng tăng trách nhiệm. Không gọi acknowledge chỉ vì listener đã nhận được record; phải xác định chính xác điều kiện nghiệp vụ được xem là hoàn tất.

### 7.4 Commit sync và async

Container có thể dùng sync hoặc async commit theo cấu hình. Sync commit chờ broker phản hồi, giúp biết kết quả commit ngay nhưng có thể tăng latency. Async commit không chờ hoàn tất trên đường xử lý chính nhưng lỗi commit cần được quan sát và xử lý phù hợp.

Chọn commit mode dựa trên throughput, yêu cầu xử lý lại và khả năng chịu duplicate. Dù dùng mode nào, business operation vẫn nên idempotent vì rebalance, process crash hoặc commit failure có thể dẫn đến record được xử lý lại.

### 7.5 Offset khi có transaction

Khi container được cấu hình với Kafka transaction manager, offset của record đã xử lý có thể được gửi vào cùng Kafka transaction với output record. Transaction commit sẽ làm output record và offset input được commit như một đơn vị trong phạm vi Kafka.

Khi transaction abort, output record không được consumer read_committed nhìn thấy và offset input không được cập nhật bởi transaction đó. Input có thể được xử lý lại. Cơ chế này là nền tảng cho consume-transform-produce exactly-once trong phạm vi Kafka.

Transaction không tự bao gồm database hoặc HTTP side effect. Nếu listener ghi database rồi Kafka transaction abort, database commit không tự rollback. Cần outbox/inbox, idempotency hoặc compensation cho các hệ thống ngoài Kafka.

## 8. Xử lý lỗi trong KafkaMessageListenerContainer

Container gọi listener và phối hợp error handling khi listener ném exception. Cách xử lý cụ thể phụ thuộc listener type, CommonErrorHandler, transaction setup và phiên bản Spring Kafka.

Các nhóm lỗi thường gặp:

- Lỗi tạm thời: timeout, network interruption hoặc downstream service tạm thời không khả dụng.
- Lỗi dữ liệu: deserialize thất bại, payload không hợp lệ hoặc schema không tương thích.
- Lỗi nghiệp vụ: vi phạm điều kiện xử lý hoặc dữ liệu không thể áp dụng.
- Lỗi hạ tầng: broker unavailable, authentication failure hoặc authorization failure.

### 8.1 CommonErrorHandler

Trong các phiên bản Spring Kafka hiện đại, CommonErrorHandler là abstraction chung cho xử lý lỗi record và batch. DefaultErrorHandler thường được dùng để retry có backoff và phục hồi record sau số lần thử phù hợp.

Có thể cấu hình error handler thông qua container factory để các container được tạo từ factory sử dụng cùng chính sách. Với container được tạo trực tiếp, cấu hình error handler trên container theo API của phiên bản đang dùng.

Chính sách cần xác định:

- Exception nào được retry.
- Số lần thử và backoff.
- Exception nào không retry.
- Khi nào recover hoặc publish vào DLT.
- Offset được commit thế nào sau recovery.
- Recovery có chạy trong transaction riêng hay không.

Không retry vô hạn lỗi dữ liệu không thể tự phục hồi. Cũng không đưa mọi lỗi database vào non-retryable nếu dependency có thể phục hồi.

### 8.2 Poison message và DLT

Một poison message là record luôn làm listener thất bại. Nếu retry tại cùng partition mà không có giới hạn, record đó có thể giữ partition không tiến triển.

Dead Letter Topic (DLT) cho phép chuyển record không phục hồi được sang nơi điều tra và replay. DLT cần có retention, replication, ACL, giám sát và runbook. Publish vào DLT cũng có thể thất bại; phải theo dõi kết quả recovery.

Khi replay, cần giữ event id, topic/partition/offset gốc và exception metadata để tránh tạo side effect trùng hoặc làm mất nguồn gốc record.

### 8.3 Lỗi deserialize

Nếu deserializer lỗi trước khi listener nhận được record, listener không thể tự xử lý exception theo cách thông thường. Spring Kafka cung cấp ErrorHandlingDeserializer để chuyển thông tin lỗi qua header và cho phép error handler xử lý.

Cần phân biệt lỗi deserialize với lỗi business logic. Nếu payload không thể parse, không nên retry vô hạn cùng một byte sequence. Dùng DLT hoặc quy trình sửa dữ liệu/replay phù hợp.

### 8.4 Listener bị treo hoặc xử lý quá lâu

Một listener đồng bộ bị block có thể ngăn consumer poll tiếp. Dấu hiệu gồm processing latency tăng, poll gap lớn, rebalance hoặc consumer bị loại khỏi group do max.poll.interval.ms.

Cách giảm rủi ro:

- Đặt timeout cho HTTP, database và các lời gọi phụ thuộc.
- Giới hạn số record mỗi poll bằng max.poll.records phù hợp.
- Tách workload có thời gian xử lý rất khác nhau.
- Dùng concurrency trong giới hạn partition và downstream capacity.
- Theo dõi consumer lag và thời gian xử lý từng record/batch.
- Không dùng một thread pool không giới hạn để chuyển mọi việc khỏi consumer thread mà không thiết kế acknowledgment và ordering.

## 9. Rebalance và partition assignment

Khi container subscribe theo topic, Kafka group coordinator quản lý membership và partition assignment. Rebalance xảy ra khi thành viên thay đổi, subscription thay đổi hoặc group cần phân phối lại partition.

Các sự kiện thường dẫn đến rebalance:

- Container start hoặc stop.
- Pod restart hoặc deploy.
- Consumer heartbeat mất.
- Listener xử lý lâu vượt max.poll.interval.ms.
- Topic partition count thay đổi.
- Member bị fencing hoặc network interruption.
- Subscription pattern phát hiện topic mới.

Trong rebalance, partition có thể bị revoke khỏi consumer cũ và assign cho consumer mới. Container phối hợp callback để ứng dụng có thể hoàn tất công việc đang dở, commit offset phù hợp hoặc giải phóng tài nguyên theo partition.

### 9.1 ConsumerRebalanceListener

ContainerProperties có thể nhận ConsumerRebalanceListener. Listener này cho phép ứng dụng phản ứng khi partition được gán hoặc thu hồi.

Ví dụ minh họa:

~~~java
containerProperties.setConsumerRebalanceListener(
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                Collection<TopicPartition> partitions) {
            log.info("Revoked partitions: {}", partitions);
        }

        @Override
        public void onPartitionsAssigned(
                Collection<TopicPartition> partitions) {
            log.info("Assigned partitions: {}", partitions);
        }
    }
);
~~~

Callback revoked hữu ích để flush state theo partition hoặc ghi nhận công việc đang dở. Callback assigned hữu ích để khởi tạo state gắn với partition.

Không thực hiện công việc blocking lâu trong callback. Rebalance có deadline và các member khác đang chờ group hoàn tất. Nếu ứng dụng cần commit offset, phải tuân theo semantics container và tránh commit vị trí vượt quá record đã xử lý thành công.

### 9.2 Rebalance và xử lý trùng

Nếu record đã tạo business side effect nhưng offset chưa commit, partition có thể được gán cho consumer khác và record được đọc lại. Đây là hành vi at-least-once phổ biến.

Consumer nên dùng idempotency key, unique constraint hoặc inbox table để đảm bảo lần xử lý lại không tạo side effect trùng. Container giúp quản lý offset và assignment, nhưng không thể tự biết database đã ghi nghiệp vụ thành công hay chưa.

## 10. Pause, resume và điều tiết tải

KafkaMessageListenerContainer cung cấp lifecycle control để ứng dụng tạm dừng và tiếp tục consumer. Pause/resume hữu ích khi cần điều tiết tải hoặc bảo trì downstream.

### 10.1 Khi nào pause?

Một số trường hợp:

- Database đang quá tải và ứng dụng cần giảm tốc độ đọc.
- Downstream service bị rate limit.
- Cần chờ tài nguyên hoặc dependency phục hồi.
- Ứng dụng đang drain một luồng trước khi bảo trì.
- Một partition cần tạm ngừng xử lý theo quyết định vận hành.

Pause không xóa record và không commit offset thay cho listener. Record tiếp tục tồn tại trong Kafka, lag có thể tăng. Cần có ngưỡng thời gian pause và điều kiện resume.

### 10.2 Pause khác stop

| Hành động | Consumer membership | Nhận record | Partition assignment |
|---|---|---|---|
| pause | Thường tiếp tục duy trì group membership | Tạm ngừng nhận record từ partition được pause | Giữ assignment |
| resume | Tiếp tục như trước | Nhận record trở lại | Giữ assignment nếu group không rebalance |
| stop | Consumer đóng và rời group | Không nhận record | Partition có thể được gán cho member khác |

Pause/resume không thay thế backpressure toàn hệ thống. Nếu producer tiếp tục ghi nhanh hơn consumer, backlog sẽ tăng. Cần theo dõi lag, tuổi record và capacity khi quyết định pause.

### 10.3 Pause partition

Một số API Spring Kafka cho phép pause/resume partition cụ thể thay vì toàn container. Điều này hữu ích khi chỉ một partition hoặc một nhóm key gặp vấn đề. Khả năng và tên API phụ thuộc phiên bản; hãy dùng API container thay vì truy cập KafkaConsumer từ thread ngoài.

Khi pause một partition, các partition khác do cùng consumer quản lý vẫn có thể tiếp tục xử lý. Tuy nhiên, nếu listener thread đang bị block bởi record của partition khác, pause một partition không giải quyết được thread starvation.

## 11. Events và observability của container

Spring Kafka phát các application event giúp quan sát lifecycle và tình trạng consumer. Event cụ thể tùy phiên bản, nhưng một số nhóm thường gặp gồm:

- ConsumerStartingEvent và ConsumerStartedEvent.
- ConsumerStoppedEvent.
- ListenerContainerIdleEvent.
- NonResponsiveConsumerEvent.
- ConsumerPausedEvent và ConsumerResumedEvent.
- ConsumerPartitionPausedEvent và ConsumerPartitionResumedEvent.
- ContainerStoppedEvent, ContainerPausedEvent và ContainerResumedEvent.

Event listener có thể dùng để ghi log, cập nhật trạng thái vận hành hoặc phát cảnh báo. Không nên dùng event callback để chạy công việc blocking dài trên thread phát event.

### 11.1 Idle event

Idle event có thể được phát khi container không nhận record trong khoảng thời gian cấu hình. Idle không nhất thiết là lỗi. Topic có thể không có dữ liệu hoặc producer đang dừng.

Cần kết hợp idle event với expected traffic, producer rate và consumer lag. Nếu topic được kỳ vọng có dữ liệu liên tục nhưng container idle trong khi lag tăng, đó là dấu hiệu cần điều tra.

### 11.2 Non-responsive consumer

NonResponsiveConsumerEvent có thể giúp phát hiện consumer không poll trong thời gian bất thường. Nguyên nhân có thể là listener bị treo, JVM pause, thread starvation hoặc downstream call không có timeout.

Khi nhận event, kiểm tra thread dump, processing latency, downstream metrics và max.poll.interval.ms. Không tự động restart container khi chưa hiểu nguyên nhân; restart có thể tạo rebalance liên tục và làm sự cố nặng hơn.

### 11.3 Metrics

Theo dõi các chỉ số theo container, client, group, topic và partition:

| Phạm vi | Metrics/tín hiệu |
|---|---|
| Container | Running state, pause state, idle duration, consumer thread activity |
| Consumer client | Poll latency, heartbeat, commit latency, assigned partitions |
| Group | Member count, rebalance count, assignment stability |
| Processing | Record processing time, batch duration, listener error rate |
| Offset | Committed offset, current position, lag theo partition |
| Downstream | Database pool, HTTP latency, timeout, queue depth |
| Recovery | Retry count, rollback count, DLT publish count |

Tên metric và cách gắn tag phụ thuộc Spring Kafka, Kafka client, Micrometer và exporter version. Cần xác nhận metric thực tế được export trước khi viết alert.

## 12. Tích hợp transaction với listener container

KafkaMessageListenerContainer có thể phối hợp với transaction manager để mỗi lần xử lý listener chạy trong Kafka transaction. Khi cấu hình đúng, container bắt đầu transaction trước khi gọi listener, cho phép KafkaTemplate gửi output vào transaction đó và đưa offset input vào cùng transaction.

Luồng consume-transform-produce:

~~~mermaid
sequenceDiagram
    participant C as KafkaMessageListenerContainer
    participant K as Kafka
    participant A as Application listener
    C->>K: poll input
    K-->>C: input record
    C->>K: begin Kafka transaction
    C->>A: invoke listener
    A->>K: send output record
    C->>K: send input offset to transaction
    C->>K: commit transaction
    K-->>C: commit result
~~~

Nếu listener ném exception và transaction rollback, output record không được consumer read_committed nhìn thấy và offset input không được commit bởi transaction đó. Record input có thể được đọc lại.

Cần phân biệt Kafka transaction với database transaction. Nếu listener cập nhật database trước khi Kafka transaction commit, database side effect không tự rollback khi Kafka transaction abort. Dùng outbox/inbox hoặc idempotency cho side effect ngoài Kafka.

## 13. Spring Kafka container factory và KafkaListenerEndpointRegistry

Trong mô hình @KafkaListener, ứng dụng thường không trực tiếp quản lý từng KafkaMessageListenerContainer. Container được tạo từ KafkaListenerContainerFactory và được quản lý qua KafkaListenerEndpointRegistry.

Các thành phần:

- ConcurrentKafkaListenerContainerFactory cấu hình container cho endpoint.
- @KafkaListener khai báo listener endpoint.
- KafkaListenerEndpointRegistry giữ các listener container được tạo từ annotation.
- ConcurrentMessageListenerContainer điều phối child KafkaMessageListenerContainer.
- KafkaMessageListenerContainer quản lý một KafkaConsumer.

Có thể lấy container theo id để điều khiển lifecycle:

~~~java
@Component
class ListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    ListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void resumeOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
~~~

Ví dụ dùng id được khai báo trong @KafkaListener. Nếu endpoint dùng ConcurrentMessageListenerContainer, registry trả về wrapper. Pause/resume trên wrapper được điều phối tới các child container.

Không nên lưu tham chiếu đến KafkaConsumer nội bộ để thao tác trực tiếp. Dùng MessageListenerContainer interface hoặc API được Spring Kafka hỗ trợ để giữ lifecycle nhất quán.

### 13.1 Cấu hình factory

Một factory có thể cấu hình concurrency, ack mode, error handler và record/batch behavior:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, String> factory =
        new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

Listener có thể chọn factory:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "orders-reader",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void handle(String value) {
    orderService.process(value);
}
~~~

Factory tạo ConcurrentMessageListenerContainer với concurrency 3; wrapper quản lý ba KafkaMessageListenerContainer con. Mỗi child có một consumer và thread riêng.

### 13.2 Khi nào dùng trực tiếp KafkaMessageListenerContainer?

Dùng trực tiếp khi:

- Một component cần sở hữu một consumer với lifecycle rõ ràng.
- Subscription được tạo động theo cấu hình runtime.
- Cần một container độc lập không đi qua annotation endpoint.
- Đang xây dựng framework nội bộ hoặc adapter cần kiểm soát container.

Dùng @KafkaListener và factory khi:

- Listener là một phần của Spring application thông thường.
- Cần dependency injection, method listener và annotation metadata.
- Cần concurrency và lifecycle được quản lý bởi endpoint registry.
- Muốn dùng chung cấu hình error handler, converter, interceptor và transaction.

Không tạo trực tiếp container chỉ để tránh hiểu cấu hình factory. Làm vậy có thể khiến ứng dụng phải tự quản lý lifecycle, shutdown, metrics và error handling.

## 14. Các lỗi vận hành thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Container không start | ConsumerFactory, deserializer, security hoặc topic config lỗi | Đọc startup exception và effective consumer properties |
| Container chạy nhưng không nhận record | Sai topic/group, offset ở cuối, partition không được assign hoặc topic rỗng | Kiểm tra assignment, committed offset, log end và auto.offset.reset |
| Rebalance liên tục | Poll quá chậm, heartbeat/network lỗi hoặc pod restart | Đo listener duration, poll interval và member lifecycle |
| Lag tăng dù consumer còn sống | Downstream chậm, listener block, partition hot hoặc transaction kéo dài | So sánh processing latency, partition lag và transaction state |
| Record xử lý lặp | Offset chưa commit trước crash/rebalance hoặc retry | Kiểm tra ack mode, commit failures và idempotency |
| Record bị mất khỏi góc nhìn ứng dụng | Offset commit quá sớm, sai group id hoặc dùng latest cho group mới | Đối chiếu group offset và business side effect |
| Listener không được gọi | Deserialize error hoặc error handler giữ record | Kiểm tra deserializer, error handler và DLT |
| Stop ứng dụng kéo dài | Listener blocking hoặc shutdown timeout lớn | Kiểm tra thread dump, downstream timeout và shutdown config |
| Pause nhưng lag tiếp tục tăng | Producer vẫn ghi trong lúc consumer pause | Theo dõi produce rate, lag và thời gian pause |
| Nhiều consumer idle | Concurrency lớn hơn số partition | So sánh consumer count và partition count |

## 15. Quy trình điều tra container không xử lý record

Khi container đang chạy nhưng không có tiến triển, đi theo thứ tự:

1. Xác nhận listener container id, group id, topic subscription và ConsumerFactory thực tế.
2. Kiểm tra container có running hay đang pause.
3. Kiểm tra consumer có được assign partition hay không.
4. So sánh committed offset, current position và log end offset theo từng partition.
5. Xác nhận auto.offset.reset và group offset có phù hợp.
6. Kiểm tra poll loop, poll interval, processing duration và thread state.
7. Kiểm tra deserializer, listener exception, CommonErrorHandler và DLT.
8. Kiểm tra downstream database, HTTP, thread pool và connection pool.
9. Kiểm tra rebalance, broker availability, network và transaction state nếu có.
10. Sau khi sửa, xác nhận listener nhận record, offset tiến triển và business side effect hoàn tất đúng một lần theo idempotency policy.

Không tăng concurrency hoặc reset offset trước khi xác định container đang thiếu assignment, bị pause, bị block hay đang chờ dependency. Mỗi nguyên nhân cần cách phục hồi khác nhau.

## 16. Checklist cấu hình và vận hành

**Container và listener**

- [ ] Biết mỗi KafkaMessageListenerContainer quản lý một consumer.
- [ ] Listener type phù hợp record hoặc batch.
- [ ] ContainerProperties xác định đúng topic, pattern hoặc partition.
- [ ] Poll timeout và max.poll.interval.ms được cân đối với thời gian xử lý.
- [ ] Listener không block vô hạn trên downstream.
- [ ] Consumer chỉ được thao tác qua lifecycle/API container được hỗ trợ.

**Offset và lỗi**

- [ ] AckMode phù hợp với listener và yêu cầu nghiệp vụ.
- [ ] Auto commit được kiểm tra và container quản lý offset như dự kiến.
- [ ] Manual acknowledgment chỉ gọi sau khi business effect đạt điều kiện hoàn tất.
- [ ] CommonErrorHandler có retry hữu hạn và phân loại exception.
- [ ] Poison message có DLT/recovery policy và quy trình replay.
- [ ] Business processing có idempotency khi record được giao lại.

**Concurrency và lifecycle**

- [ ] Phân biệt KafkaMessageListenerContainer với ConcurrentMessageListenerContainer.
- [ ] Concurrency không vượt quá nhu cầu partition/downstream capacity.
- [ ] Start/stop được quản lý bởi Spring lifecycle hoặc một owner duy nhất.
- [ ] Shutdown timeout phù hợp với termination grace period.
- [ ] Pause/resume có điều kiện và thời gian giới hạn.
- [ ] Rebalance callback không thực hiện công việc blocking dài.

**Quan sát và phục hồi**

- [ ] Có log container id, group id, topic, partition và offset.
- [ ] Theo dõi lag, assignment, rebalance và processing latency.
- [ ] Có cảnh báo container không poll hoặc idle bất thường.
- [ ] Theo dõi downstream saturation và lỗi deserialization.
- [ ] Có runbook cho container stopped, paused, rebalance loop và DLT.
- [ ] Đã kiểm thử restart, scale, shutdown và xử lý lỗi trong môi trường phù hợp.

KafkaMessageListenerContainer là lớp quản lý một KafkaConsumer trong Spring Kafka. Nó biến các thao tác poll, listener invocation, acknowledgment, rebalance và lifecycle thành một đơn vị vận hành có cấu hình. Khi cần concurrency, ConcurrentMessageListenerContainer tạo nhiều container con; khi cần listener thông thường, @KafkaListener và container factory giúp Spring quản lý chúng. Thiết kế tốt cần gắn đúng subscription, offset policy, error handling và shutdown behavior với yêu cầu xử lý của nghiệp vụ.

