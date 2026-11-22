# Spring for Apache Kafka và mô hình nhật ký phân vùng

Spring for Apache Kafka đưa các abstraction của Spring vào hệ thống Apache Kafka: KafkaTemplate để gửi record, @KafkaListener và listener container để nhận record, cùng các cơ chế quản lý offset, transaction, retry và chuyển đổi dữ liệu. Để dùng đúng các API này, trước hết cần hiểu Kafka tổ chức dữ liệu thành topic và partition như thế nào.

Kafka không hoạt động giống một queue đơn giản trong đó một message được lấy khỏi hàng đợi sau khi consumer xử lý. Mỗi topic gồm một hoặc nhiều partition; mỗi partition là một log có thứ tự, nơi record được append vào cuối. Consumer đọc log theo offset và lưu tiến độ của mình theo consumer group. Một record đã được đọc thường vẫn còn trong log theo chính sách retention hoặc compaction của topic.

Mô hình partition quyết định thứ tự, khả năng mở rộng, phân phối tải và cách Spring Kafka chạy consumer song song. Chọn key, số partition và group ID là các quyết định kiến trúc ảnh hưởng trực tiếp đến hành vi nghiệp vụ.

## 1. Topic, partition và log

### 1.1. Topic là luồng dữ liệu logic

Topic là tên logic để producer ghi record và consumer đăng ký đọc. Ví dụ một hệ thống thương mại điện tử có thể dùng các topic:

- orders: sự kiện đơn hàng.
- payments: sự kiện thanh toán.
- inventory: thay đổi tồn kho.
- shipment: cập nhật giao vận.

Topic xác định một loại dữ liệu hoặc luồng sự kiện. Bên trong topic, Kafka chia dữ liệu thành các partition để phân phối lưu trữ và xử lý.

### 1.2. Partition là một commit log có thứ tự

Một partition là một chuỗi record được append theo thứ tự. Mỗi record trong partition được gán một offset tăng dần theo vị trí trong log.

Ví dụ topic orders có ba partition:

~~~text
orders
  partition 0: offset 0 -> 1 -> 2 -> 3 -> ...
  partition 1: offset 0 -> 1 -> 2 -> 3 -> ...
  partition 2: offset 0 -> 1 -> 2 -> 3 -> ...
~~~

Offset chỉ có ý nghĩa trong phạm vi một partition. Partition 0 offset 12 và partition 1 offset 12 là hai vị trí khác nhau. Không có một offset toàn cục để sắp xếp mọi record của toàn topic.

Kafka bảo đảm thứ tự đọc trong một topic-partition theo thứ tự record được ghi vào partition đó. Kafka không bảo đảm thứ tự tổng thể giữa các partition. Nếu hai producer ghi đồng thời vào hai partition khác nhau, consumer không thể suy ra thứ tự nghiệp vụ toàn cục chỉ từ offset.

### 1.3. Log khác với queue truyền thống

Trong queue truyền thống, message thường được xóa hoặc chuyển khỏi queue sau khi được acknowledge. Trong Kafka, consumer commit offset để lưu tiến độ đọc; việc commit offset không xóa record khỏi partition.

Record được giữ theo cấu hình retention, chẳng hạn thời gian hoặc dung lượng. Topic compacted có thể giữ record mới nhất theo key và loại bỏ một số phiên bản cũ, nhưng việc compaction không thay đổi thứ tự offset của những record còn lại.

Điều này cho phép nhiều consumer group đọc cùng một topic độc lập. Một group có thể xử lý dữ liệu gần thời gian thực; group khác có thể đọc lại log để dựng lại projection hoặc chạy báo cáo.

## 2. Partition key quyết định nơi lưu record

### 2.1. Vì sao cần key?

Producer gửi record có thể gồm:

- Topic: tên luồng dữ liệu.
- Key: khóa dùng để định tuyến và phân vùng.
- Value: payload của sự kiện.
- Headers: metadata bổ sung.
- Timestamp: thời điểm gắn với record.

Khi producer gửi các record có cùng key, partitioner mặc định thường chọn cùng một partition cho key đó trong cùng cấu hình topic/partitioner. Nhờ vậy, các record của cùng một thực thể nghiệp vụ có thể được đọc theo thứ tự trong một partition.

Ví dụ, dùng orderId làm key:

| Record | Key | Partition |
|---|---|---:|
| OrderCreated | order-42 | 1 |
| PaymentAuthorized | order-42 | 1 |
| OrderPacked | order-42 | 1 |
| OrderShipped | order-42 | 1 |
| OrderCreated | order-77 | 0 |

Nếu các record của order-42 được ghi tuần tự tới cùng partition, consumer đọc partition đó sẽ thấy chúng theo thứ tự ghi.

### 2.2. Chọn key theo aggregate hoặc entity

Chọn key dựa trên đơn vị mà hệ thống cần giữ thứ tự:

- orderId nếu cần thứ tự sự kiện của một đơn hàng.
- accountId nếu cần thứ tự thay đổi trên cùng tài khoản.
- customerId nếu cần thứ tự hoạt động của một khách hàng.
- deviceId nếu cần thứ tự telemetry của một thiết bị.

Tránh dùng key ngẫu nhiên cho những sự kiện cần thứ tự theo thực thể. Nếu key là null, producer có thể phân phối record theo chiến lược sticky/batching; các record cùng một thực thể khi đó không nhất thiết vào cùng partition.

Không nên dùng timestamp làm key nếu mục tiêu là giữ thứ tự theo thực thể. Timestamp có thể trùng, lệch đồng hồ hoặc đến muộn; nó không thay thế một khóa định danh ổn định.

### 2.3. Key không tạo ra thứ tự nghiệp vụ nếu producer gửi sai thứ tự

Partition chỉ giữ thứ tự append. Nếu hai service gửi event cho cùng orderId đồng thời, record nào tới broker trước có thể được append trước. Kafka không tự hiểu rằng OrderCreated phải đứng trước OrderShipped.

Nếu cần thứ tự nghiệp vụ chặt chẽ, ứng dụng phải đảm bảo thứ tự phát hành, ví dụ serialize việc publish theo aggregate, dùng transactional outbox theo thứ tự sequence, hoặc lưu aggregate version để consumer phát hiện sự kiện đến sai thứ tự.

### 2.4. Thay đổi số partition có thể thay đổi mapping của key

Nếu số partition thay đổi, thuật toán phân vùng có thể đưa cùng key sang partition khác. Những record cũ vẫn nằm ở partition cũ; record mới có thể nằm ở partition mới. Khi đó, consumer không còn một log duy nhất chứa toàn bộ lịch sử của key.

Vì vậy, tăng partition không phải thao tác hoàn toàn trung tính với thứ tự theo key. Trước khi tăng partition, hãy đánh giá:

- Có cần giữ thứ tự theo aggregate trong toàn bộ lịch sử không?
- Có consumer nào dựa trên partition assignment cố định không?
- Có thể chấp nhận một giai đoạn dữ liệu cũ và mới của cùng key nằm ở hai partition không?
- Có cần version, sequence number hoặc migration/repartition topic không?

## 3. Replication, leader và tính sẵn sàng

Mỗi partition có một replica leader và có thể có các replica follower trên các broker khác nhau. Producer ghi vào leader; follower sao chép log từ leader. Consumer thường đọc từ leader, trừ khi cấu hình và client hỗ trợ cơ chế đọc replica khác.

Replication factor là số bản sao của partition. Ví dụ replication factor 3 có nghĩa một partition có ba replica trên các broker phù hợp. Replica không tạo thêm ba bản ghi logic cho consumer; chúng là bản sao để phục hồi khi broker gặp sự cố.

Một số cấu hình quan trọng:

- replication.factor: số replica khi topic được tạo.
- min.insync.replicas: số replica tối thiểu cần ở trạng thái in-sync cho một số điều kiện ghi.
- acks: mức xác nhận producer yêu cầu.
- enable.idempotence: hỗ trợ producer gửi lại an toàn hơn trước một số lỗi retry ở tầng protocol.

Ví dụ, với acks=all và min.insync.replicas=2, broker chỉ xác nhận write khi các điều kiện ISR tương ứng được đáp ứng. Nếu số replica in-sync giảm dưới ngưỡng, producer có thể nhận lỗi thay vì được xác nhận một write có độ bền thấp hơn. Cần thiết kế replication factor, min.insync.replicas và acks cùng nhau theo mục tiêu durability và availability.

Replication không thay thế backup, schema governance hoặc chiến lược phục hồi thảm họa. Nó bảo vệ partition khỏi một số lỗi broker, nhưng không bảo vệ khỏi producer gửi sai dữ liệu hoặc ứng dụng xử lý sai nghiệp vụ.

## 4. Consumer group và phân phối partition

### 4.1. Consumer group là một nhóm cùng chia việc

Consumer group có group.id. Các consumer trong cùng group chia các partition của topic để mỗi partition được giao cho tối đa một consumer trong group tại một thời điểm.

Nếu topic có sáu partition và group có ba consumer, mỗi consumer có thể nhận khoảng hai partition. Nếu group có tám consumer nhưng topic chỉ có sáu partition, ít nhất hai consumer sẽ không có partition nào để đọc từ topic đó.

Một partition không được hai consumer trong cùng group đồng thời xử lý theo assignment thông thường. Tuy nhiên, hai group khác nhau có thể đọc cùng partition độc lập, mỗi group có offset riêng.

~~~text
Topic: orders (6 partitions)

Consumer group: order-projection
  consumer A <- P0, P1
  consumer B <- P2, P3
  consumer C <- P4, P5

Consumer group: analytics
  consumer X <- P0, P1, P2
  consumer Y <- P3, P4, P5
~~~

Group order-projection và group analytics đều đọc cùng topic nhưng tiến độ và mục đích riêng.

### 4.2. Số consumer song song bị giới hạn bởi số partition

Trong một consumer group chỉ đọc một topic, số consumer có thể thực sự đọc song song bị giới hạn bởi số partition được giao. Tăng concurrency lớn hơn partition count không tự tạo thêm partition hoặc tăng khả năng đọc song song.

Ví dụ, topic có bốn partition:
- concurrency=1: một consumer đọc cả bốn partition.
- concurrency=2: hai consumer chia bốn partition.
- concurrency=4: tối đa bốn consumer cùng đọc, mỗi consumer một partition.
- concurrency=8: tối đa bốn consumer có assignment; các consumer còn lại idle cho topic này.

Nếu listener subscribe nhiều topic, assignment phụ thuộc tổng tập partition và chiến lược assignor. Hãy kiểm tra assignment thực tế thay vì chỉ nhìn concurrency đã cấu hình.

### 4.3. Rebalance

Khi consumer tham gia hoặc rời group, hoặc partition/topic thay đổi, Kafka có thể thực hiện rebalance để tính lại assignment. Trong quá trình rebalance, việc xử lý có thể tạm dừng hoặc partition được chuyển sang consumer khác.

Rebalance có thể xảy ra khi:
- Instance ứng dụng khởi động hoặc dừng.
- Consumer mất heartbeat hoặc không poll kịp.
- Concurrency thay đổi.
- Topic có partition mới.
- Membership hoặc subscription của group thay đổi.

Xử lý quá lâu trong listener có thể khiến consumer không poll kịp và bị xem là không còn hoạt động. Cần cấu hình max.poll.interval.ms, max.poll.records và concurrency theo thời gian xử lý thực tế. Không tăng max.poll.interval.ms một cách mù quáng; hãy xem xét xử lý theo batch, giảm thời gian xử lý hoặc chuyển công việc nặng sang pipeline có kiểm soát.

## 5. Offset và tiến độ xử lý

### 5.1. Offset là vị trí đọc, không phải message ID toàn cục

Consumer theo dõi offset riêng cho từng topic-partition. Offset commit thể hiện tiến độ mà group đã lưu để có thể tiếp tục sau restart hoặc rebalance.

Nếu consumer group đã commit offset 120 cho partition 2, lần đọc tiếp theo thường bắt đầu từ vị trí tiếp theo theo semantics của Kafka consumer. Offset được commit không có nghĩa mọi record trước đó chắc chắn đã hoàn thành side effect nghiệp vụ nếu ứng dụng commit quá sớm.

### 5.2. auto.offset.reset

auto.offset.reset chỉ được áp dụng khi group không có offset hợp lệ đã commit cho partition, hoặc offset đã commit không còn khả dụng theo retention. Các giá trị thường gặp:

- earliest: bắt đầu từ record sớm nhất còn lại trong log.
- latest: bắt đầu từ cuối log hiện tại, bỏ qua backlog cũ chưa có offset.
- none: ném lỗi nếu không tìm thấy offset hợp lệ.

Không nhầm auto.offset.reset với việc reset offset cho một group đã có tiến độ. Muốn replay có chủ đích, hãy dùng công cụ quản trị hoặc ConsumerSeekAware/seek API phù hợp, có kế hoạch về duplicate và side effect.

### 5.3. Commit offset và duplicate

Nếu consumer thực hiện side effect rồi mới commit offset, ứng dụng có thể xử lý lại record nếu tiến trình dừng sau side effect nhưng trước commit. Đây là một nguyên nhân phổ biến tạo duplicate trong mô hình at-least-once.

Nếu commit offset trước khi side effect hoàn tất, record có thể bị bỏ qua khi consumer restart. Vì vậy, thứ tự commit và xử lý phải được chọn theo semantics mong muốn.

Thiết kế consumer idempotent bằng message ID hoặc business key, dùng transaction phù hợp và lưu checkpoint nghiệp vụ nếu cần. Không suy ra exactly-once cho database bên ngoài chỉ từ Kafka offset commit.

## 6. Gửi record bằng KafkaTemplate

KafkaTemplate là abstraction Spring cấp cao bao quanh Kafka producer. Các phương thức send trả về CompletableFuture<SendResult<K,V>>, cho phép xử lý kết quả bất đồng bộ.

### 6.1. Gửi với key để giữ record cùng aggregate trên một partition

Ví dụ dưới đây là service fragment sử dụng KafkaTemplate<String, String>:

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    CompletableFuture<SendResult<String, String>> publish(
            String orderId,
            String eventPayload) {

        return this.kafkaTemplate.send(
                "orders",
                orderId,
                eventPayload);
    }
}
~~~

orderId là record key. Với partitioner mặc định và cùng partition topology, các record có cùng key được định tuyến cùng partition, nhờ đó có thứ tự append trong partition cho aggregate đó.

### 6.2. Kiểm tra kết quả gửi

~~~java
publisher.publish("order-42", "OrderCreated")
        .whenComplete((result, error) -> {
            if (error != null) {
                // Ghi nhận lỗi gửi và xử lý theo retry policy.
                return;
            }

            var metadata = result.getRecordMetadata();

            System.out.printf(
                    "topic=%s partition=%d offset=%d%n",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset());
        });
~~~

Kết quả gửi cho biết broker metadata của record đã được gửi thành công theo cấu hình producer. Topic, partition và offset là thông tin quan trọng để truy vết record.

Không coi việc gọi send() là bằng chứng broker đã xác nhận. Với thao tác quan trọng, xử lý CompletableFuture và failure path rõ ràng. Tránh block vô hạn bằng get(); nếu cần chờ đồng bộ, dùng timeout phù hợp và tính tới trường hợp timeout mơ hồ khi broker có thể đã nhận record.

### 6.3. Gửi chỉ định partition

KafkaTemplate hỗ trợ gửi với partition cụ thể:

~~~java
kafkaTemplate.send("orders", 2, "order-42", "OrderCreated");
~~~

Dùng explicit partition khi ứng dụng thực sự sở hữu quy tắc phân vùng hoặc có yêu cầu vận hành cụ thể. Nếu chỉ muốn giữ thứ tự theo entity, thường nên dùng key và partitioner thay vì hard-code số partition. Explicit partition khiến ứng dụng gắn chặt với topology topic.

## 7. Nhận record bằng @KafkaListener

### 7.1. Listener cơ bản

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-projection",
            concurrency = "3")
    public void onOrder(ConsumerRecord<String, String> record) {
        String orderId = record.key();
        String payload = record.value();

        int partition = record.partition();
        long offset = record.offset();

        // Cập nhật projection theo orderId.
    }
}
~~~

Listener nhận ConsumerRecord để truy cập key, value, topic, partition, offset, timestamp và headers gốc. Nếu chỉ cần payload, có thể khai báo phương thức nhận String hoặc kiểu domain tương ứng sau khi cấu hình deserializer/message converter.

concurrency=3 yêu cầu listener container tạo ba consumer instance trong cùng group. Số partition thực tế được giao quyết định bao nhiêu consumer có thể hoạt động đồng thời.

### 7.2. Cấu hình container factory

Nếu cần cấu hình rõ concurrency và poll timeout, có thể tạo ConcurrentKafkaListenerContainerFactory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, String> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties().setPollTimeout(3000);

    return factory;
}
~~~

Đây là cấu hình fragment trong một lớp @Configuration. Khi dùng Spring Boot, Boot thường tự cấu hình consumer factory và listener container factory; chỉ tạo factory riêng khi cần chính sách khác hoặc muốn điều khiển rõ ràng một listener cụ thể.

### 7.3. Nhận metadata qua header

Spring Kafka ánh xạ metadata record vào message headers. Các header thường dùng gồm:

- KafkaHeaders.RECEIVED_TOPIC.
- KafkaHeaders.RECEIVED_PARTITION.
- KafkaHeaders.OFFSET.
- KafkaHeaders.RECEIVED_KEY.
- KafkaHeaders.RECEIVED_TIMESTAMP.

Có thể nhận các giá trị này bằng @Header hoặc nhận ConsumerRecord/ConsumerRecordMetadata. Với xử lý cần log và truy vết, topic + partition + offset là một định danh vị trí hữu ích; kết hợp thêm message ID nghiệp vụ để truy vết xuyên hệ thống.

## 8. Tạo topic và chọn số partition

Có thể khai báo topic bằng NewTopic bean và TopicBuilder:

~~~java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
~~~

Đây là cấu hình mẫu yêu cầu KafkaAdmin và broker có đủ broker phù hợp để đặt ba replica. TopicBuilder khai báo số partition và replication factor khi topic được tạo. Việc thay đổi cấu hình topic đã tồn tại phụ thuộc thao tác admin và khả năng thay đổi của Kafka; không giả định tạo bean sẽ giảm số partition hoặc tự di chuyển record cũ.

### 8.1. Chọn số partition

Số partition ảnh hưởng:
- Mức song song tối đa trong một consumer group.
- Số replica và phân bổ dữ liệu trên broker.
- Số file segment, metadata và overhead quản trị.
- Khả năng tăng throughput khi thêm consumer.
- Mapping key và semantics thứ tự theo aggregate.

Đừng chọn số partition chỉ theo số instance ứng dụng hiện tại. Hãy ước lượng throughput, kích thước record, số consumer group, tốc độ tăng trưởng và mục tiêu mở rộng. Quá ít partition hạn chế parallelism; quá nhiều partition làm tăng metadata, file segment và overhead rebalance.

### 8.2. Partition count và consumer concurrency

Concurrency của Spring Kafka là số consumer được tạo cho listener container, còn partition count là số đơn vị dữ liệu có thể được phân phối trong group. Concurrency nên được chọn dựa trên số partition, năng lực xử lý và downstream capacity.

Nếu topic có sáu partition, concurrency 3 thường cho phép ba consumer chia tải. Nếu concurrency 12, ít nhất sáu consumer sẽ không có partition từ topic đó. Với nhiều topic, kết quả assignment phụ thuộc tổng partition của subscription.

## 9. Partition assignment và listener chuyên biệt

Mặc định, khi @KafkaListener khai báo topics hoặc topicPattern, Kafka consumer group sẽ phân phối partition tự động theo partition assignor.

Nếu cần gán rõ partition cho listener, Spring Kafka hỗ trợ topicPartitions:

~~~java
@KafkaListener(
        id = "priority-orders",
        topicPartitions = @TopicPartition(
                topic = "orders",
                partitions = { "0", "1" }))
public void listenPriorityOrders(ConsumerRecord<String, String> record) {
    // Xử lý partition 0 và 1.
}
~~~

Manual assignment hữu ích cho workload chuyên biệt, nhưng làm thay đổi cách quản lý partition và không nên dùng chỉ để cố định consumer vào partition nếu group management đã đáp ứng yêu cầu.

Nếu dùng ConsumerSeekAware hoặc seek API, hãy xác định rõ initial offset, replay range và tác động duplicate. Seek là thay đổi vị trí đọc; nó không xóa hoặc sửa log.

## 10. Transaction và exactly-once trong Kafka

Spring Kafka hỗ trợ Kafka transaction thông qua transactional producer factory, KafkaTransactionManager và transactional listener container.

Để bật transaction, cấu hình DefaultKafkaProducerFactory với transactionIdPrefix. Spring sẽ quản lý transactional producer. Khi listener container khởi tạo transaction, việc consume-process-produce có thể được phối hợp để output record và offset được commit trong cùng Kafka transaction.

Điều này hỗ trợ exactly-once semantics trong phạm vi Kafka read-process-write. Tuy nhiên, nó không tự động bao gồm database bên ngoài, HTTP API hoặc side effect ngoài Kafka. Với database và Kafka cùng tham gia nghiệp vụ, cần thiết kế outbox/inbox, transaction synchronization hoặc quy trình bù trừ theo yêu cầu consistency.

Non-blocking retry topics không kết hợp được với container transactions trong Spring Kafka theo cơ chế được tài liệu mô tả. Khi chọn retry topology, cần quyết định rõ giữa blocking retry, retry topic và transaction semantics; không ghép các tính năng mà không kiểm tra giới hạn của phiên bản đang dùng.

## 11. Retry, DLT và thứ tự partition

Khi listener lỗi, có hai hướng phổ biến:

- Blocking retry: listener container thử lại record trước khi tiếp tục theo error handler/backoff policy. Cách này có thể giữ partition bị chặn trong thời gian retry.
- Non-blocking retry: record được chuyển sang retry topic với thời gian chờ; consumer khác xử lý sau. Khi hết attempts, record có thể được chuyển vào Dead Letter Topic (DLT).

Spring Kafka cung cấp @RetryableTopic và @DltHandler để cấu hình retry topic/DLT cho listener. Non-blocking retry tạo thêm topic và listener container. Một điểm quan trọng: khi dùng retry topic, thứ tự của topic gốc không còn được bảo toàn như trước vì record lỗi có thể được xử lý sau những record tiếp theo.

Nếu thứ tự theo aggregate là bắt buộc, hãy cân nhắc blocking retry, tách luồng xử lý theo key hoặc lưu sequence/version để consumer phát hiện gap. Không chỉ nhìn thấy retry thành công mà bỏ qua hệ quả về thứ tự.

## 12. Lỗi thường gặp và cách chẩn đoán

### 12.1. Các event cùng entity xử lý sai thứ tự

Kiểm tra producer có dùng key ổn định không, partitioner có nhất quán không, producer có publish đồng thời không, số partition có thay đổi không và retry topic có làm lệch thứ tự không. Kafka chỉ giữ thứ tự append trong một partition.

### 12.2. Tăng concurrency nhưng throughput không tăng

Kiểm tra số partition và assignment. Nếu consumer đã có một partition riêng hoặc downstream đã bão hòa, thêm consumer không giúp tăng throughput. Xem thêm poll duration, processing time, executor queue và rebalance.

### 12.3. Consumer đọc lại record

Kiểm tra group.id, offset commit, acknowledgment mode, auto.offset.reset và việc listener có bị restart/rebalance không. Nếu side effect hoàn thành nhưng offset chưa commit, record có thể được giao lại. Consumer cần idempotent.

### 12.4. Consumer bỏ qua backlog sau khi tạo group mới

Nếu group chưa có offset và auto.offset.reset=latest, consumer bắt đầu từ cuối log hiện tại. Nếu muốn đọc các record còn được giữ từ đầu, cấu hình earliest cho group mới hoặc reset offset có chủ đích.

### 12.5. Partition bị nóng

Nếu một key tạo phần lớn traffic, tất cả record của key đó phải đi qua một partition để giữ thứ tự. Partition đó có thể trở thành hot partition dù các partition khác còn ít tải. Xem phân bố record theo partition và thiết kế key. Không chia nhỏ key tùy tiện nếu việc đó phá vỡ thứ tự nghiệp vụ.

### 12.6. Record được gửi nhưng consumer không nhận

Kiểm tra topic, key, partition, serializer/deserializer, group.id, ACL, offset, retention, subscription và consumer lag. Xem producer future để biết send thành công hay lỗi; xem consumer assignment và committed offset để xác định record đang ở đâu.

## 13. Kiểm thử với Spring Kafka

Spring Kafka cung cấp spring-kafka-test để hỗ trợ kiểm thử. Tùy mục tiêu, có thể dùng EmbeddedKafkaBroker hoặc Testcontainers chạy broker thật.

Nên có các nhóm test:
1. Producer gửi record có key và xác nhận metadata partition/offset.
2. Hai record cùng key được ghi vào cùng partition trong cấu hình test.
3. Listener nhận đúng key, value, topic, partition và offset.
4. Consumer group đọc lại từ committed offset sau restart.
5. Nhiều listener consumer chia partition theo concurrency.
6. Rebalance khi thêm hoặc dừng consumer.
7. Lỗi xử lý kích hoạt retry/DLT đúng cấu hình.
8. Transaction rollback không để output record và offset ở trạng thái không nhất quán.
9. Consumer idempotent khi cùng record được giao lại.

Không nên kiểm tra rằng hai record khác key luôn nằm ở hai partition khác nhau; hash có thể va chạm và Kafka không cam kết phân phối đều từng cặp key. Hãy kiểm tra thuộc tính cần bảo đảm: cùng key trong cùng topology/partitioner được định tuyến ổn định, còn thứ tự được quan sát trong partition đó.

## 14. Checklist thiết kế production

- [ ] Topic được đặt tên theo luồng dữ liệu hoặc domain event rõ ràng.
- [ ] Partition count dựa trên throughput, parallelism, tăng trưởng và chi phí vận hành.
- [ ] Key đại diện cho aggregate/entity cần giữ thứ tự.
- [ ] Producer không gửi cùng aggregate song song nếu cần thứ tự phát hành chặt chẽ.
- [ ] Replication factor, min.insync.replicas và acks được thiết kế cùng nhau.
- [ ] Consumer group ID ổn định theo ứng dụng và mục đích xử lý.
- [ ] Concurrency không vượt quá nhu cầu partition/downstream.
- [ ] max.poll.interval.ms và max.poll.records phù hợp với thời gian xử lý.
- [ ] Offset commit/acknowledgment phù hợp với side effect và idempotency.
- [ ] Retry topic/DLT được chọn có ý thức về thứ tự.
- [ ] Transaction semantics được hiểu trong phạm vi Kafka và hệ thống ngoài Kafka.
- [ ] Theo dõi lag, throughput, processing latency, rebalance, failed send và DLT.
- [ ] Có kế hoạch khi tăng partition, thay đổi key hoặc migrate topic.
- [ ] Có integration test với broker cho assignment, offset, retry và transaction.

## Tài liệu tham khảo

- Spring for Apache Kafka Reference — Introduction, version compatibility and features: https://spring.io/projects/spring-kafka/
- Spring Kafka Reference — Sending Messages and KafkaTemplate: https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html
- Spring Kafka Reference — @KafkaListener, partition assignment, concurrency and record metadata: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html
- Spring Kafka Reference — Transactions: https://docs.spring.io/spring-kafka/reference/kafka/transactions.html
- Apache Kafka Documentation — Topics, partitions, records and ordering: https://kafka.apache.org/documentation/
- Apache Kafka Protocol — Partitioning and ordered commit logs: https://kafka.apache.org/protocol.html
