# ConcurrentMessageListenerContainer

## Mục tiêu của bài học

Trong chương **Kiến trúc Spring Kafka**, bài này tập trung vào `ConcurrentMessageListenerContainer`: container điều phối nhiều consumer để một listener có thể xử lý các partition Kafka song song trong cùng một consumer group.

**SPRING_KAFKA_MESSAGING** hướng dẫn xây dựng ứng dụng gửi và nhận sự kiện bằng Spring Kafka, sử dụng KafkaTemplate và @KafkaListener, đồng thời hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, concurrency và kiểm thử. Trong phạm vi đó, `ConcurrentMessageListenerContainer` là thành phần quan trọng ở phía consumer: nó quyết định cách Spring Kafka tạo, quản lý và phối hợp nhiều consumer để tăng khả năng xử lý song song.

Sau bài học, người học có thể:

- Phân biệt `ConcurrentMessageListenerContainer`, `KafkaMessageListenerContainer` và `ConcurrentKafkaListenerContainerFactory`.
- Mô tả mối quan hệ giữa concurrency, consumer, partition và consumer group.
- Cấu hình concurrency cho listener bằng Spring Kafka.
- Giải thích cách container quản lý vòng đời, offset, rebalance và lỗi khi có nhiều consumer.
- Chọn mức concurrency phù hợp với số partition, tải xử lý và năng lực của hệ thống phụ thuộc.
- Nhận diện các tình huống khiến tăng concurrency không cải thiện thông lượng.

## 1. Vì sao cần ConcurrentMessageListenerContainer?

Một Kafka consumer thường xử lý các bản ghi từ những partition được gán cho nó. Nếu ứng dụng chỉ dùng một consumer cho một listener, các partition mà consumer đó sở hữu được xử lý thông qua một luồng tiêu thụ. Khi tải tăng, một consumer có thể trở thành giới hạn về khả năng xử lý.

Spring Kafka cung cấp `ConcurrentMessageListenerContainer` để quản lý nhiều consumer trong cùng một listener container. Mỗi consumer được chạy bởi một `KafkaMessageListenerContainer` con. Các consumer tham gia consumer group và nhận partition theo cơ chế phân phối của Kafka.

Ví dụ, topic `orders.created` có 6 partition. Một ứng dụng Billing chạy listener với concurrency bằng 3. Spring Kafka tạo 3 consumer container con. Kafka phân phối 6 partition cho 3 consumer đó; mỗi consumer có thể nhận nhiều partition và xử lý các bản ghi thuộc những partition được giao.

~~~mermaid
flowchart TB
    A["ConcurrentMessageListenerContainer"] --> B["KafkaMessageListenerContainer 1"]
    A --> C["KafkaMessageListenerContainer 2"]
    A --> D["KafkaMessageListenerContainer 3"]
    B --> E["Kafka Consumer 1"]
    C --> F["Kafka Consumer 2"]
    D --> G["Kafka Consumer 3"]
    E --> H["Các partition được gán"]
    F --> I["Các partition được gán"]
    G --> J["Các partition được gán"]
~~~

Container cha chịu trách nhiệm điều phối các container con. Các consumer thực tế vẫn tuân theo giao thức consumer group của Kafka. Vì vậy, Spring Kafka không tự tạo ra partition hoặc thay đổi quy tắc phân phối partition của broker.

## 2. Phân biệt các thành phần liên quan

Tên các lớp khá giống nhau, nhưng chúng giữ những vai trò khác nhau.

| Thành phần | Vai trò |
|---|---|
| `ConcurrentMessageListenerContainer<K, V>` | Container quản lý nhiều listener container con để xử lý đồng thời |
| `KafkaMessageListenerContainer<K, V>` | Container quản lý một Kafka consumer và gọi listener cho các bản ghi consumer nhận được |
| `ConcurrentKafkaListenerContainerFactory<K, V>` | Factory tạo `ConcurrentMessageListenerContainer` cho các phương thức `@KafkaListener` |
| `ConsumerFactory<K, V>` | Tạo Kafka consumer với cấu hình và deserializer tương ứng |
| `ContainerProperties` | Chứa cấu hình container như topic, partition, acknowledgment mode, timeout và listener liên quan |
| `@KafkaListener` | Khai báo phương thức ứng dụng nhận bản ghi; listener container thực thi phương thức đó |

Mối quan hệ khái quát:

~~~mermaid
flowchart TD
    A["@KafkaListener"] --> B["KafkaListenerAnnotationBeanPostProcessor"]
    B --> C["ConcurrentKafkaListenerContainerFactory"]
    C --> D["ConcurrentMessageListenerContainer"]
    D --> E["KafkaMessageListenerContainer"]
    E --> F["ConsumerFactory"]
    F --> G["KafkaConsumer"]
    G --> H["Kafka Broker"]
~~~

Khi ứng dụng khởi động, Spring xử lý annotation `@KafkaListener`, tìm factory được chỉ định và tạo container tương ứng. Nếu factory có concurrency lớn hơn 1, container quản lý nhiều container con. Mỗi container con tạo và quản lý một Kafka consumer.

Một cách nhớ hữu ích:

- Factory là nơi định nghĩa cách tạo container.
- Concurrent container là bộ điều phối các consumer container con.
- Kafka message listener container quản lý một consumer.
- Listener là mã nghiệp vụ được gọi khi có bản ghi.

## 3. Mô hình concurrency và partition

### 3.1. Concurrency có nghĩa gì?

Concurrency là số consumer container con mà một `ConcurrentMessageListenerContainer` quản lý. Mỗi container con có consumer riêng và chạy công việc tiêu thụ trên luồng riêng.

Nếu cấu hình:

`concurrency = 3`

thì container có thể tạo 3 consumer cho cùng listener và cùng consumer group. Ba consumer này có thể xử lý các partition khác nhau đồng thời.

Concurrency không phải số thread tùy ý chạy cùng một consumer. Kafka consumer không an toàn khi được nhiều thread gọi đồng thời. Spring Kafka giữ mỗi consumer trong phạm vi container và luồng xử lý do container quản lý.

### 3.2. Partition giới hạn mức song song

Trong cùng một consumer group, một partition tại một thời điểm chỉ được gán cho tối đa một consumer. Vì vậy, số consumer đang thực sự nhận partition không thể vượt quá số partition được gán cho group.

Ví dụ với một topic có 4 partition:

| Concurrency của một instance | Consumer được tạo | Consumer có thể nhận partition | Hệ quả |
|---:|---:|---:|---|
| 1 | 1 | 1 | Một consumer xử lý cả 4 partition |
| 2 | 2 | Tối đa 2 | Mỗi consumer có thể xử lý 2 partition |
| 4 | 4 | Tối đa 4 | Có thể có một consumer trên mỗi partition |
| 6 | 6 | Tối đa 4 | Ít nhất 2 consumer không được gán partition |

Consumer không được gán partition vẫn có thể tham gia group và chờ thay đổi assignment, nhưng không tạo thêm khả năng xử lý bản ghi tại thời điểm đó.

Quy tắc trên áp dụng cho tổng số consumer trong group, không chỉ một tiến trình. Nếu có nhiều instance ứng dụng, tổng số consumer là tổng concurrency của các instance đang hoạt động. Chẳng hạn, 2 instance cùng cấu hình concurrency bằng 3 tạo tổng cộng 6 consumer trong group.

### 3.3. Ví dụ phân phối partition

Giả sử topic có 6 partition và một instance có concurrency bằng 3. Một assignment có thể trông như sau:

~~~mermaid
flowchart TB
    T["orders.created: 6 partitions"]
    T --> P0["Partition 0"]
    T --> P1["Partition 1"]
    T --> P2["Partition 2"]
    T --> P3["Partition 3"]
    T --> P4["Partition 4"]
    T --> P5["Partition 5"]
    P0 --> C1["Consumer 1"]
    P3 --> C1
    P1 --> C2["Consumer 2"]
    P4 --> C2
    P2 --> C3["Consumer 3"]
    P5 --> C3
~~~

Đây chỉ là sơ đồ minh họa. Assignment thực tế phụ thuộc partition assignor, số consumer trong group, số topic, số partition và các consumer đang hoạt động. Không nên dựa vào sơ đồ để giả định partition luôn được chia đều trong mọi cấu hình.

### 3.4. Consumer group và nhiều instance

Các container con thường dùng chung group id được cấu hình cho listener. Kafka xem mỗi consumer con như một thành viên riêng của group. Nếu ứng dụng có nhiều instance, consumer từ các instance cùng tham gia group và broker phân phối partition trên toàn bộ thành viên.

Ví dụ:

| Instance | Concurrency | Số consumer |
|---|---:|---:|
| Billing-1 | 2 | 2 |
| Billing-2 | 2 | 2 |
| Billing-3 | 2 | 2 |
| **Tổng** | | **6** |

Với 6 partition, group có thể phân phối mỗi partition cho một consumer. Nếu tăng lên 9 consumer mà topic vẫn chỉ có 6 partition, tối đa 6 consumer nhận partition tại cùng thời điểm.

Nếu hai ứng dụng có mục đích nhận độc lập cùng một sự kiện, chúng thường cần group id khác nhau. Nếu chúng dùng chung group id, Kafka phân phối partition giữa các consumer trong group thay vì gửi toàn bộ bản ghi tới mỗi ứng dụng.

## 4. Cấu hình ConcurrentMessageListenerContainer

Trong ứng dụng Spring, cách phổ biến là cấu hình `ConcurrentKafkaListenerContainerFactory`. Factory tạo `ConcurrentMessageListenerContainer` khi Spring đăng ký listener.

Ví dụ sau tạo factory có concurrency bằng 3:

~~~java
@Configuration
@EnableKafka
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersListenerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Các điểm cần hiểu:

- `setConsumerFactory(...)` cung cấp cách tạo Kafka consumer và cấu hình key/value deserializer.
- `setConcurrency(3)` yêu cầu container được tạo từ factory quản lý 3 consumer container con.
- `setAckMode(RECORD)` chọn cách xác nhận offset sau khi xử lý từng bản ghi thành công theo cơ chế container.
- `@EnableKafka` kích hoạt hạ tầng annotation trong cấu hình Spring thuần. Với Spring Boot, hạ tầng listener thường được cấu hình tự động; khi khai báo cấu hình riêng, cần kiểm tra cấu hình ứng dụng và factory đang được sử dụng.

Listener có thể chỉ định factory vừa khai báo:

~~~java
@Service
public class OrderCreatedListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "billing-service",
        containerFactory = "ordersListenerFactory"
    )
    public void handle(OrderCreated event) {
        // Xử lý nghiệp vụ billing.
    }
}
~~~

Spring tạo container cho phương thức listener và áp dụng concurrency từ factory. Nếu ứng dụng có nhiều nhóm listener với yêu cầu xử lý khác nhau, có thể khai báo nhiều factory với cấu hình riêng, ví dụ một factory cho xử lý đơn hàng và một factory cho cập nhật tồn kho.

### 4.1. Cấu hình batch listener

Nếu nghiệp vụ phù hợp với xử lý theo lô, factory có thể bật batch listener:

~~~java
factory.setBatchListener(true);
~~~

Phương thức listener khi đó nhận một tập bản ghi thay vì một bản ghi đơn:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-batch",
    containerFactory = "batchListenerFactory"
)
public void handleBatch(List<ConsumerRecord<String, OrderCreated>> records) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        // Xử lý từng bản ghi trong batch.
    }
}
~~~

Batch listener có thể giảm chi phí gọi listener và phù hợp với thao tác ghi theo lô. Tuy nhiên, một batch xử lý lâu làm tăng thời gian giữa các lần poll; cần đánh giá `max.poll.interval.ms`, kích thước batch và khả năng chịu tải của hệ thống phụ thuộc.

Không nên bật batch chỉ để tăng throughput nếu nghiệp vụ cần xác nhận từng bản ghi hoặc cần xử lý lỗi riêng lẻ. Cách retry và commit cần được thiết kế cùng với batch semantics.

### 4.2. Chọn concurrency riêng cho từng listener

Mỗi listener có thể dùng một factory riêng để đặt concurrency theo đặc tính tải. Ví dụ:

- Listener nhận sự kiện đơn hàng có thể cần concurrency cao vì xử lý nhẹ và topic có nhiều partition.
- Listener tạo hóa đơn có thể cần concurrency thấp hơn vì database là giới hạn tải.
- Listener xử lý sự kiện theo thứ tự của một số key có thể cần giữ partition và concurrency phù hợp với yêu cầu thứ tự.

Concurrency nên là quyết định dựa trên phép đo và cấu trúc partition, không phải một giá trị giống nhau cho mọi listener.

## 5. Vòng đời của container và consumer

### 5.1. Khởi tạo và khởi động

Khi Spring khởi tạo listener endpoint, factory tạo `ConcurrentMessageListenerContainer`. Container cha tạo các `KafkaMessageListenerContainer` con theo concurrency. Mỗi container con tạo consumer từ `ConsumerFactory`, đăng ký tham gia group hoặc áp dụng assignment được cấu hình, sau đó bắt đầu vòng lặp poll.

Luồng khởi tạo:

~~~mermaid
sequenceDiagram
    participant S as Spring Context
    participant F as Container Factory
    participant P as Concurrent Container
    participant C as Child Container
    participant K as Kafka Cluster

    S->>F: Tạo listener endpoint
    F->>P: Tạo ConcurrentMessageListenerContainer
    P->>C: Tạo các container con theo concurrency
    C->>K: Tạo consumer và tham gia group
    K-->>C: Phân phối partition
    C->>K: Poll bản ghi
~~~

### 5.2. Poll và gọi listener

Mỗi consumer container con chạy vòng lặp tiêu thụ độc lập. Consumer poll Kafka, container chuyển bản ghi sang listener adapter và adapter gọi phương thức ứng dụng.

~~~mermaid
sequenceDiagram
    participant K as Kafka Broker
    participant C as Consumer Thread
    participant A as Spring Listener Adapter
    participant L as @KafkaListener Method

    C->>K: poll()
    K-->>C: ConsumerRecords
    C->>A: Chuyển bản ghi
    A->>L: Gọi listener
    L-->>A: Hoàn tất xử lý
    A-->>C: Kết quả xử lý
    C->>K: Commit offset theo cấu hình
~~~

Một listener bean thường là singleton trong Spring. Khi concurrency lớn hơn 1, cùng một phương thức có thể được gọi đồng thời từ nhiều thread. Nếu listener dùng field mutable, bộ đếm, collection hoặc đối tượng không thread-safe, cần đồng bộ hoặc thay đổi thiết kế để tránh race condition.

Không giữ tham chiếu tới Kafka consumer để gọi từ thread nghiệp vụ khác. Kafka consumer không thread-safe; hãy dùng API của listener container và cơ chế tương tác được Spring Kafka hỗ trợ.

### 5.3. Dừng container

Container cha quản lý vòng đời của các container con. Khi Spring context dừng hoặc container nhận lệnh stop, Spring Kafka điều phối việc dừng consumer, kết thúc vòng lặp poll và giải phóng tài nguyên. Ứng dụng nên cho container đủ thời gian hoàn tất xử lý đang diễn ra theo cấu hình shutdown và timeout phù hợp.

Nếu listener xử lý quá lâu, quá trình dừng có thể cần thời gian chờ. Cần tránh tác vụ nghiệp vụ không giới hạn thời gian hoặc không có cơ chế hủy/timeout, vì chúng có thể làm chậm quá trình shutdown và deployment.

### 5.4. Tạm dừng và tiếp tục

Spring Kafka cung cấp API pause/resume ở cấp listener container và partition. Chúng hữu ích khi cần giảm tải tạm thời, bảo trì hệ thống phụ thuộc hoặc kiểm soát backpressure.

Pause consumer không đồng nghĩa xóa assignment hoặc rời consumer group. Consumer vẫn phải duy trì hoạt động phù hợp để tránh bị xem là không còn sống. Khi resume, consumer tiếp tục tiêu thụ theo assignment hiện tại nếu group chưa rebalance.

## 6. Phân phối partition và partition assignor

Kafka quyết định cách partition được phân phối cho consumer trong group thông qua partition assignor. Spring Kafka quản lý consumer và listener container; quy tắc assignment được thực hiện bởi Kafka client và group coordinator.

Một số chiến lược phổ biến:

- **RangeAssignor:** phân phối các partition theo phạm vi cho từng consumer trên từng topic. Khi có nhiều topic, phân phối có thể không đều giữa các consumer.
- **RoundRobinAssignor:** phân phối partition luân phiên giữa các consumer, thường giúp phân bổ đều hơn khi nhiều topic có partition tương tự.
- **StickyAssignor:** cố gắng cân bằng assignment đồng thời giảm số partition phải chuyển khi group thay đổi.
- **CooperativeStickyAssignor:** sử dụng cơ chế cooperative rebalance để giảm việc thu hồi toàn bộ partition trong một lần rebalance.

Chiến lược thực tế phụ thuộc phiên bản Kafka client và cấu hình `partition.assignment.strategy`. Hãy kiểm tra cấu hình consumer đang chạy trước khi kết luận partition được chia theo cách nào.

Ví dụ về tình huống mất cân bằng: ứng dụng subscribe hai topic, mỗi topic có 3 partition, group có 6 consumer. Một assignor kiểu Range có thể phân phối partition theo từng topic khiến một số consumer nhận partition từ cả hai topic trong khi các consumer khác không có partition. Một assignor kiểu Round Robin có thể phân tán sáu partition đều hơn trong tình huống đó.

Không phải mọi trường hợp đều cần đổi assignor. Hãy đo assignment, số consumer rảnh, consumer lag và throughput trước khi điều chỉnh.

## 7. Concurrency, thứ tự và xử lý offset

### 7.1. Thứ tự bản ghi

Kafka duy trì thứ tự trong phạm vi một partition. Một consumer trong group được gán partition đó sẽ đọc các bản ghi theo thứ tự offset. Với concurrency, các partition khác nhau có thể được xử lý song song bởi các consumer khác nhau.

Nếu các sự kiện của cùng một thực thể cần giữ thứ tự, producer thường dùng cùng key để các sự kiện đó được định tuyến vào cùng partition. Consumer group sau đó xử lý partition theo thứ tự Kafka cung cấp.

Concurrency không tạo ra thứ tự toàn cục giữa nhiều partition. Nếu listener gửi công việc sang thread pool khác và trả về trước khi công việc hoàn tất, thứ tự hoàn tất nghiệp vụ cũng có thể khác thứ tự nhận. Khi offload xử lý bất đồng bộ, ứng dụng phải tự kiểm soát ordering và acknowledgment.

### 7.2. Acknowledgment và commit offset

Mỗi consumer theo dõi offset cho các partition được gán. Container quản lý acknowledgment và commit dựa trên `ContainerProperties.AckMode` cùng cấu hình consumer.

Các chế độ thường gặp:

| Ack mode | Cách xác nhận |
|---|---|
| `RECORD` | Xác nhận sau khi listener xử lý xong từng bản ghi |
| `BATCH` | Xác nhận các bản ghi của lần poll sau khi listener xử lý xong batch tương ứng |
| `MANUAL` | Listener gọi `Acknowledgment.acknowledge()`; container áp dụng commit theo semantics của chế độ |
| `MANUAL_IMMEDIATE` | Commit ngay khi acknowledge được gọi trên consumer thread; nếu gọi từ thread khác, yêu cầu commit được chuyển về consumer thread để xử lý |

Concurrency không thay thế chính sách offset. Mỗi consumer container con quản lý các partition mà nó sở hữu; ứng dụng cần chọn ack mode phù hợp với tác dụng phụ nghiệp vụ và chiến lược xử lý lỗi.

Nếu commit offset trước khi nghiệp vụ hoàn tất, sự cố có thể khiến bản ghi bị bỏ qua. Nếu xử lý hoàn tất nhưng offset chưa được commit, bản ghi có thể được giao lại sau restart hoặc rebalance. Vì vậy, consumer nên được thiết kế idempotent.

### 7.3. Rebalance khi số consumer thay đổi

Khi instance ứng dụng tăng/giảm, consumer khởi động/dừng hoặc subscription thay đổi, Kafka có thể thực hiện rebalance để phân phối lại partition. Trong quá trình đó:

1. Consumer có thể được yêu cầu thu hồi partition đang sở hữu.
2. Container hoàn tất các callback liên quan tới revoke/assign theo cơ chế cấu hình.
3. Group coordinator tính assignment mới.
4. Consumer tiếp tục poll với các partition được giao.

Rebalance có thể làm gián đoạn ngắn hoạt động tiêu thụ. Nếu rebalance diễn ra thường xuyên, cần kiểm tra thời gian xử lý listener, cấu hình poll/heartbeat, tình trạng mạng, việc triển khai instance và chiến lược assignment.

Các callback rebalance có thể được dùng cho những tác vụ cần chuẩn bị hoặc dọn dẹp trạng thái theo partition. Không nên dùng callback như một nơi thực hiện nghiệp vụ kéo dài, vì điều đó có thể làm chậm quá trình rebalance.

## 8. Chọn concurrency phù hợp

Không có một giá trị concurrency tối ưu cho mọi hệ thống. Cần xem xét đồng thời partition, số instance, thời gian xử lý, tài nguyên và hệ thống phụ thuộc.

### 8.1. Bắt đầu từ số partition

Với một group, tổng số consumer đang hoạt động có ích bị giới hạn bởi tổng số partition được gán. Nếu topic có 8 partition và ứng dụng có một instance, concurrency 8 là điểm thử nghiệm hợp lý để đánh giá mức song song tối đa theo partition. Nếu ứng dụng chạy 2 instance, mỗi instance concurrency 4 cũng tạo tổng cộng 8 consumer.

Đây chỉ là điểm bắt đầu. Nếu xử lý nhẹ, consumer có thể xử lý nhiều partition; nếu xử lý nặng hoặc cần cách ly tải, có thể cần cấu hình khác.

### 8.2. Đo thời gian xử lý và năng lực downstream

Tăng consumer có thể tăng số yêu cầu đồng thời tới database, REST API hoặc hệ thống lưu trữ. Nếu hệ thống phụ thuộc chỉ chịu được 10 thao tác đồng thời, đặt concurrency tổng cộng 40 có thể làm tăng timeout và retry thay vì tăng throughput.

Cần đo:

- Thời gian xử lý trung bình và percentile cao của listener.
- Số bản ghi xử lý mỗi giây trên mỗi consumer.
- Consumer lag theo partition.
- Pool connection, CPU, memory và I/O.
- Tỷ lệ lỗi, timeout và số lần retry.
- Mức độ phân bố key và tải giữa các partition.

### 8.3. Tránh hot partition

Ngay cả khi topic có nhiều partition, một key có tần suất rất cao có thể khiến partition chứa key đó trở thành điểm nóng. Tăng concurrency không thể chia một partition cho nhiều consumer trong cùng group.

Có thể cần xem lại key strategy, partition count hoặc cách chia nhỏ tác vụ nghiệp vụ. Việc thay đổi key có thể ảnh hưởng thứ tự và cách consumer xử lý, nên cần đánh giá hợp đồng dữ liệu trước khi triển khai.

### 8.4. Cân nhắc poll và thời gian xử lý

Consumer phải tiếp tục poll theo giới hạn cấu hình. Nếu xử lý giữa các lần poll kéo dài vượt `max.poll.interval.ms`, Kafka có thể xem consumer không còn đáp ứng và kích hoạt rebalance. Batch lớn, listener xử lý chậm hoặc downstream timeout đều có thể góp phần gây ra tình huống này.

Tăng concurrency không tự sửa được listener xử lý quá lâu. Hãy xem xét giảm batch size, tối ưu nghiệp vụ, tăng timeout có chủ đích hoặc tách công việc dài thành một luồng xử lý có kiểm soát.

## 9. Xử lý lỗi trong môi trường concurrent

Mỗi container con có consumer riêng, nhưng chính sách xử lý lỗi thường được cấu hình ở factory hoặc container. Spring Kafka hỗ trợ error handler, retry, backoff và dead-letter recovery.

Khi nhiều consumer chạy đồng thời, cần chú ý:

- Exception của một listener invocation phải được xử lý theo error handler tương ứng.
- Retry blocking có thể làm consumer đang xử lý partition đó chậm lại; các partition khác do consumer khác quản lý vẫn có thể tiếp tục.
- Retry topic chuyển bản ghi sang luồng retry khác, có thể thay đổi thứ tự quan sát giữa các event cùng key.
- Khi một consumer rời group hoặc bị lỗi, partition có thể được gán cho consumer khác; bản ghi chưa commit có thể được giao lại.
- DLT và log cần có topic, partition, offset, key và thông tin lỗi để hỗ trợ điều tra.

Concurrency cao có thể khiến lỗi downstream lan rộng nhanh hơn do có nhiều consumer cùng retry hoặc gọi dịch vụ phụ thuộc. Giới hạn retry, backoff, circuit breaker ở lớp phù hợp và năng lực downstream cần được xem xét cùng nhau.

## 10. Quan sát và vận hành

Để biết concurrency có đem lại hiệu quả hay không, cần quan sát cả container lẫn Kafka group.

Các tín hiệu quan trọng:

| Tín hiệu | Ý nghĩa |
|---|---|
| Consumer count và assignment | Số consumer đang hoạt động và partition được gán cho từng consumer |
| Consumer lag theo partition | Mức chậm của từng partition, giúp phát hiện hot partition |
| Listener processing time | Thời gian xử lý bản ghi hoặc batch |
| Records consumed rate | Thông lượng thực tế của consumer |
| Rebalance count và duration | Mức ổn định của group |
| Retry/DLT count | Chất lượng xử lý lỗi và dữ liệu không hợp lệ |
| Consumer pause state | Consumer hoặc partition có đang tạm dừng hay không |
| CPU, memory, connection pool | Giới hạn tài nguyên của ứng dụng và hệ thống phụ thuộc |

Spring Kafka phát ra các application event liên quan đến listener container, consumer idle, pause/resume và trạng thái partition. Có thể kết hợp chúng với metric của Kafka client và hệ thống quan sát của Spring để xây dựng cảnh báo.

Khi kiểm tra một listener bị chậm, không chỉ nhìn tổng consumer lag. Hãy so sánh lag từng partition với assignment để xác định một partition bị nóng hay toàn bộ consumer đều xử lý chậm.

## 11. Kiểm thử ConcurrentMessageListenerContainer

Kiểm thử nên xác nhận cả hành vi nghiệp vụ lẫn cách listener được cấu hình.

Các hướng tiếp cận:

1. Dùng EmbeddedKafka trong Spring Kafka Test để chạy broker phục vụ kiểm thử tích hợp.
2. Dùng Testcontainers khi cần môi trường Kafka gần với môi trường triển khai.
3. Gửi nhiều bản ghi tới các partition khác nhau và xác nhận listener nhận đủ dữ liệu.
4. Kiểm tra cấu hình container/factory để xác nhận concurrency được áp dụng đúng.
5. Kiểm tra listener bean có an toàn khi được gọi từ nhiều thread hay không.
6. Kiểm tra xử lý khi consumer dừng, khởi động lại hoặc group rebalance.
7. Kiểm tra lỗi, retry, DLT và việc xử lý lại bản ghi chưa commit.

Khi kiểm thử tính song song, không nên chỉ gửi nhiều bản ghi vào một partition rồi kỳ vọng chúng được xử lý đồng thời. Một partition trong cùng group chỉ được gán cho một consumer tại một thời điểm. Muốn kiểm tra nhiều consumer cùng hoạt động, cần có đủ partition và dữ liệu được phân phối qua các partition đó.

## 12. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Tăng concurrency nhưng throughput không đổi | Số partition ít, downstream là nút thắt hoặc key phân bố lệch | Kiểm tra assignment, lag từng partition và thời gian xử lý |
| Có consumer không nhận bản ghi | Số consumer lớn hơn số partition được gán hoặc assignment không đều | Kiểm tra consumer group và partition assignor |
| Listener bị gọi đồng thời gây sai trạng thái | Listener bean dùng state mutable không thread-safe | Loại bỏ state chia sẻ hoặc bảo vệ truy cập |
| Rebalance xảy ra liên tục | Xử lý quá lâu, poll timeout, mạng hoặc instance liên tục restart | Kiểm tra max.poll.interval.ms, thời gian listener và log consumer |
| Bản ghi bị xử lý lặp | Offset chưa commit trước khi consumer dừng hoặc rebalance | Kiểm tra ack mode và thiết kế idempotency |
| Tăng concurrency làm database quá tải | Nhiều consumer đồng thời vượt năng lực connection pool hoặc database | Giảm concurrency, giới hạn tải và đo downstream |
| Thứ tự nghiệp vụ không như mong đợi | Sự kiện liên quan nằm ở nhiều partition hoặc xử lý async không kiểm soát | Xem lại key, partitioning và cách xác nhận hoàn tất |

## 13. Checklist trước khi đưa vào vận hành

- [ ] Xác định topic, số partition và consumer group của listener.
- [ ] Chọn concurrency dựa trên tổng số consumer của tất cả instance.
- [ ] Kiểm tra partition assignment thực tế và partition assignor.
- [ ] Đảm bảo listener bean an toàn khi nhiều thread cùng gọi.
- [ ] Chọn record listener hay batch listener theo yêu cầu nghiệp vụ.
- [ ] Cấu hình acknowledgment và commit offset phù hợp.
- [ ] Thiết kế xử lý idempotent khi bản ghi được giao lại.
- [ ] Đặt giới hạn retry, backoff và chiến lược DLT.
- [ ] Đánh giá `max.poll.interval.ms` với thời gian xử lý thực tế.
- [ ] Đo consumer lag, throughput, processing time và tải downstream.
- [ ] Kiểm thử khi scale instance, rebalance, restart và shutdown.
- [ ] Có cảnh báo khi consumer không hoạt động, lag tăng hoặc DLT phát sinh bất thường.

## Kết luận

`ConcurrentMessageListenerContainer` là container điều phối nhiều `KafkaMessageListenerContainer` con để một listener có thể tiêu thụ các partition song song. Mỗi container con quản lý một Kafka consumer; các consumer tham gia consumer group và nhận partition theo assignment của Kafka. Mức concurrency hữu ích vì thế phụ thuộc vào số partition được gán, tổng số instance, cách phân phối partition và năng lực xử lý của ứng dụng.

Cấu hình concurrency chỉ là một phần của thiết kế consumer. Để luồng messaging vận hành tin cậy, cần kết hợp partitioning phù hợp, listener thread-safe, acknowledgment/offset đúng, xử lý lỗi có giới hạn, idempotency, quan sát consumer lag và kiểm thử các tình huống rebalance.
