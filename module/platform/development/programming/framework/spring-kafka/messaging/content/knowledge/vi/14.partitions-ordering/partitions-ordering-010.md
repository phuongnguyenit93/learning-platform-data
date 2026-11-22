# Đánh đổi ordering với throughput

Kafka được thiết kế để xử lý dữ liệu song song bằng cách chia topic thành nhiều partition. Mỗi partition là một log có thứ tự riêng. Vì thế, Kafka có thể tăng throughput bằng cách cho nhiều producer, broker và consumer xử lý các partition khác nhau đồng thời, nhưng thứ tự toàn cục giữa các partition không được bảo đảm.

Đây là một đánh đổi cốt lõi khi thiết kế messaging: càng chia nhỏ luồng dữ liệu để xử lý song song, ứng dụng càng cần xác định rõ phạm vi thứ tự nào thực sự quan trọng. Với Spring Kafka, quyết định này ảnh hưởng đến key khi gửi bằng KafkaTemplate, số partition của topic, concurrency của @KafkaListener, cách xử lý bất đồng bộ và chiến lược retry.

Mục tiêu thường không phải giữ thứ tự cho mọi record trong toàn hệ thống. Mục tiêu là giữ đúng thứ tự ở phạm vi nghiệp vụ cần thiết, ví dụ theo orderId hoặc accountId, đồng thời cho phép các thực thể độc lập được xử lý song song.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích phạm vi ordering mà Kafka bảo đảm và giới hạn của thứ tự giữa các partition.
- Chọn message key để giữ thứ tự theo aggregate hoặc thực thể nghiệp vụ.
- Phân tích tác động của partition count, consumer concurrency và hot partition đến throughput.
- Cấu hình producer batching, compression, idempotence và in-flight requests mà vẫn giữ thứ tự trong partition.
- Nhận diện việc xử lý bất đồng bộ, retry topic và replay có thể làm thay đổi thứ tự side effect.
- Thiết kế listener Spring Kafka xử lý tuần tự trong từng partition và song song giữa các partition.
- Chọn chiến lược phù hợp giữa strict ordering, per-key ordering và throughput cao.
- Kiểm thử ordering khi có retry, rebalance, nhiều producer và thay đổi số partition.

## 1. Kafka bảo đảm ordering ở đâu?

Kafka bảo đảm thứ tự record trong cùng một partition theo offset. Record được append trước có offset nhỏ hơn và được đọc trước trong partition đó.

Ví dụ topic orders có ba partition:

~~~text
Topic orders

Partition 0:  offset 10 -> Order A created
              offset 11 -> Order A paid
              offset 12 -> Order A shipped

Partition 1:  offset 20 -> Order B created
              offset 21 -> Order B cancelled

Partition 2:  offset 30 -> Order C created
              offset 31 -> Order C paid
~~~

Trong partition 0, consumer đọc offset 10 trước 11 và 12. Kafka không định nghĩa quan hệ thứ tự giữa offset 12 của partition 0 và offset 20 của partition 1. Hai partition có thể được producer ghi và consumer xử lý đồng thời.

Điều này tạo ra hai phạm vi khác nhau:

- **Ordering trong partition:** Kafka giữ thứ tự log theo offset.
- **Ordering toàn topic:** Kafka không cung cấp một thứ tự tổng thể giữa các partition.

Một record có timestamp sớm hơn ở partition 1 vẫn có thể được consumer xử lý sau record có timestamp muộn hơn ở partition 0. Timestamp không tạo ra một đồng hồ thứ tự toàn cục cho topic.

### Vì sao partition tạo ra giới hạn này?

Mỗi partition là một log độc lập. Kafka có thể phân phối các partition đến nhiều broker và consumer khác nhau. Nhờ vậy, các partition được ghi và đọc song song.

~~~mermaid
flowchart LR
    P["Producer"] --> T["Topic"]
    T --> A["Partition 0"]
    T --> B["Partition 1"]
    T --> C["Partition 2"]
    A --> CA["Consumer A"]
    B --> CB["Consumer B"]
    C --> CC["Consumer C"]
    CA --> SA["Xử lý song song"]
    CB --> SA
    CC --> SA
~~~

Nếu cần một thứ tự toàn cục cho mọi record, các record phải đi qua cùng một luồng có khả năng tuần tự hóa thứ tự, thường là một partition và một consumer xử lý tuần tự. Cách đó giới hạn khả năng song song. Phần lớn hệ thống chỉ cần thứ tự theo một thực thể hoặc một nhóm nghiệp vụ.

## 2. Chọn phạm vi thứ tự trước khi chọn partition count

Trước khi tăng partition hoặc concurrency, hãy xác định các sự kiện nào phải được xử lý theo thứ tự.

Ví dụ:

| Nghiệp vụ | Phạm vi thứ tự thường cần |
|---|---|
| Đơn hàng | Theo orderId |
| Tài khoản và số dư | Theo accountId |
| Hồ sơ khách hàng | Theo customerId |
| Trạng thái thiết bị IoT | Theo deviceId |
| Số liệu telemetry độc lập | Thường không cần thứ tự theo thực thể |
| Audit cần một chuỗi toàn cục | Cần một sequencer hoặc thiết kế thứ tự riêng; nhiều partition không tự cung cấp thứ tự toàn cục |

Nếu mọi sự kiện của một đơn hàng phải được áp dụng theo thứ tự tạo, thanh toán, giao hàng, hãy đưa các sự kiện cùng orderId vào cùng partition. Các đơn hàng khác nhau có thể ở các partition khác nhau và được xử lý song song.

Nếu chọn key quá rộng, ví dụ mọi sự kiện đều dùng một key chung, toàn bộ dữ liệu sẽ tập trung vào một partition. Thứ tự được giữ nhưng throughput bị giới hạn bởi partition đó.

Nếu chọn key quá hẹp hoặc thay đổi key giữa các sự kiện của cùng thực thể, các sự kiện có thể đi đến các partition khác nhau và mất bảo đảm thứ tự theo thực thể.

## 3. Message key giúp giữ thứ tự theo thực thể

Với partitioner mặc định, Kafka producer sử dụng key đã serialize để xác định partition. Cùng một key thường được định tuyến đến cùng partition khi partition count và thuật toán partitioning không thay đổi.

Ví dụ gửi sự kiện đơn hàng bằng orderId làm key:

Ví dụ dùng API của Spring Kafka 3.x, trong đó KafkaTemplate.send() trả về CompletableFuture:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event) {

        return kafkaTemplate.send(
                "orders",
                event.orderId(),
                event
        );
    }
}
~~~

Nếu orderId là order-100, các sự kiện của đơn hàng đó được định tuyến đến cùng partition trong điều kiện partition mapping ổn định. Consumer đọc partition theo offset nên có thể quan sát chuỗi sự kiện của đơn hàng theo thứ tự append.

Ví dụ:

~~~text
Key = order-100
        |
        v
Partitioner
        |
        v
Partition 2

Partition 2:
offset 50 -> OrderCreated(order-100)
offset 51 -> OrderPaid(order-100)
offset 52 -> OrderShipped(order-100)
~~~

Key phải ổn định và có ý nghĩa nghiệp vụ. Không dùng một key ngẫu nhiên mới cho mỗi event nếu cần ordering theo orderId. Cũng không nên dùng một key chung cho toàn bộ topic nếu không thực sự cần tuần tự hóa tất cả sự kiện.

### Key không tự tạo thứ tự nghiệp vụ giữa nhiều producer

Key chỉ quyết định nơi record được ghi. Nếu nhiều producer độc lập cùng phát sự kiện cho một orderId, Kafka append record theo thứ tự broker nhận và xử lý các request. Thứ tự gọi hàm ở hai tiến trình khác nhau không tự tạo ra một thứ tự nhân quả chung.

Nếu hai service có thể phát các version của cùng một aggregate, hãy dùng một cơ chế điều phối phù hợp, ví dụ:

- Một service sở hữu việc phát sự kiện cho aggregate đó.
- Sử dụng version hoặc sequence number tăng đơn điệu theo aggregate.
- Consumer kiểm tra version trước khi áp dụng thay đổi.
- Dùng transactional outbox để phát sự kiện theo thứ tự đã commit ở database.
- Nếu cần, dùng một sequencer hoặc hàng đợi tuần tự theo aggregate.

Key giúp các record hội tụ về cùng partition; nó không thay thế quy tắc xác định sự kiện nào phải xảy ra trước trong nghiệp vụ.

## 4. Keyless record và phân phối tải

Nếu producer gửi record không có key, các Kafka client hiện đại dùng sticky partitioning để phân phối record. Producer có thể giữ một partition trong một khoảng thời gian để gom batch hiệu quả rồi chuyển sang partition khác; hành vi cụ thể phụ thuộc phiên bản client và partitioner được cấu hình.

Cách này giúp phân phối record không có key và tận dụng batching. Tuy nhiên, nó không bảo đảm các sự kiện của cùng một thực thể đi cùng partition. Vì vậy, không dùng keyless record khi cần thứ tự theo orderId, accountId hoặc deviceId.

| Cách gửi | Mục tiêu | Ordering theo thực thể |
|---|---|---|
| Có key ổn định | Định tuyến các sự kiện cùng key vào một partition | Có, nếu mapping không đổi và producer order được kiểm soát |
| Không có key | Phân phối tải và batching | Không có bảo đảm theo thực thể |
| Một key chung | Tuần tự hóa toàn bộ record trong một partition | Có thứ tự trong partition, nhưng throughput bị giới hạn |
| Key ngẫu nhiên cho từng record | Phân tán tải | Không giữ thứ tự của cùng thực thể |

Với telemetry hoặc metric độc lập, keyless record có thể là lựa chọn hợp lý. Với event của aggregate, hãy dùng key định danh aggregate.

## 5. Partition count: tăng throughput và đánh đổi ordering

Nhiều partition cho phép nhiều consumer trong cùng group xử lý song song. Nếu topic có P partition, số consumer member có thể thực sự nhận partition trong group không vượt quá P.

Ví dụ:

~~~text
6 partitions + concurrency 3

P0, P1 -> Consumer 1
P2, P3 -> Consumer 2
P4, P5 -> Consumer 3
~~~

Khi tăng concurrency từ 1 lên 3, ba consumer có thể xử lý các partition khác nhau đồng thời. Nhưng một partition vẫn chỉ được gán cho một member trong cùng group tại một thời điểm.

Tăng partition có thể cải thiện throughput tổng thể nếu:

- Producer có đủ dữ liệu để phân phối trên các partition.
- Consumer có đủ năng lực xử lý song song.
- Broker và hệ thống đích còn tài nguyên.
- Key không bị lệch tải quá lớn vào một vài partition.

Đổi lại, nhiều partition làm tăng số log, file, metadata, replication traffic và chi phí quản lý group. Không nên tăng partition chỉ vì muốn có con số concurrency lớn.

### Tăng partition có thể ảnh hưởng ordering theo key

Với partitioner mặc định dựa trên hash của key, partition được chọn phụ thuộc partition count. Khi tăng số partition, cùng một key có thể được ánh xạ sang partition mới.

Ví dụ:

~~~text
Trước khi tăng partition:
order-100 -> P1
offset 80  -> OrderCreated
offset 81  -> OrderPaid

Sau khi tăng partition:
order-100 -> P4
P4 offset 0 -> OrderShipped
~~~

Record cũ vẫn nằm ở P1; record mới có thể đi P4. Kafka không di chuyển lịch sử của key từ partition cũ sang partition mới và không tạo thứ tự chung giữa P1 với P4.

Nếu cần giữ per-key ordering trong suốt vòng đời aggregate, không tăng partition count một cách tùy tiện. Có thể tạo topic phiên bản mới, thực hiện migration có ranh giới rõ, hoặc dùng partitioning strategy ổn định do ứng dụng quản lý. Cần kiểm thử mapping key trước và sau thay đổi.

## 6. Hot key và giới hạn throughput của một partition

Nếu một key nhận phần lớn traffic, mọi record của key đó phải đi qua cùng partition để giữ thứ tự. Partition đó trở thành hot partition.

Ví dụ:

~~~text
Topic có 8 partition

P0:  5% traffic
P1:  7% traffic
P2:  6% traffic
P3:  8% traffic
P4:  9% traffic
P5:  5% traffic
P6:  4% traffic
P7: 56% traffic  <- hot key / hot partition
~~~

Tăng concurrency không chia được một partition thành nhiều consumer trong cùng group. Các partition khác có thể rảnh trong khi P7 tăng lag.

Các cách xử lý phụ thuộc vào nghiệp vụ:

- Tối ưu xử lý của key nóng: giảm truy vấn database, giảm payload, cache hoặc batch side effect.
- Tách thực thể nếu nghiệp vụ thực sự cho phép các phần dữ liệu độc lập có key riêng.
- Phân vùng aggregate thành sub-key khi thứ tự chỉ cần giữ trong từng phần.
- Dùng một pipeline riêng cho key nóng để phân bổ tài nguyên và kiểm soát độ trễ.
- Nếu phải giữ thứ tự toàn bộ key nóng, chấp nhận giới hạn tuần tự của partition và tối ưu năng lực xử lý trên partition đó.

Không thêm hậu tố ngẫu nhiên vào key chỉ để phân tán tải nếu các sự kiện của thực thể vẫn cần thứ tự. Việc đó có thể tạo throughput cao hơn nhưng làm sai ngữ nghĩa xử lý.

## 7. Producer batching giúp tăng throughput mà không bỏ thứ tự partition

Kafka producer gom record thành batch theo partition. Các thuộc tính thường ảnh hưởng đến batching:

- batch.size: kích thước batch mục tiêu.
- linger.ms: thời gian producer chờ thêm record để batch đầy hơn.
- compression.type: thuật toán nén batch.
- buffer.memory: bộ nhớ producer dành cho các record đang chờ gửi.

Batching giúp giảm số request và chi phí mạng. Linger lớn hơn có thể tăng khả năng gom batch nhưng cũng tăng độ trễ chờ gửi. Compression có thể giảm lượng dữ liệu truyền qua mạng, đổi lại cần CPU để nén/giải nén.

Các tối ưu này không làm mất thứ tự append trong cùng partition. Chúng ảnh hưởng đến thời điểm và hiệu quả gửi, không tạo ordering giữa partition.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        "[batch.size]": 32768
        "[linger.ms]": 5
        "[compression.type]": lz4
        "[buffer.memory]": 67108864
~~~

Các giá trị trên chỉ là điểm bắt đầu minh họa. Hãy đo batch size thực tế, request latency, CPU và network trước khi điều chỉnh. Linger quá thấp có thể tạo nhiều batch nhỏ; linger quá cao có thể làm tăng latency của sự kiện ít lưu lượng.

### Batching không phải xử lý song song nghiệp vụ

Batch producer gom nhiều record trước khi gửi. Nó không có nghĩa consumer xử lý các record trong batch đồng thời hoặc đảo thứ tự. Nếu ứng dụng cần xử lý từng record theo thứ tự, listener vẫn cần tuần tự hóa công việc trong partition.

## 8. Producer idempotence, retry và in-flight requests

Producer có thể retry request khi broker tạm thời lỗi hoặc response bị mất. Nếu producer không idempotent và có nhiều request đang in-flight, retry một request cũ có thể làm thứ tự append khác với thứ tự gửi ban đầu.

Ví dụ khi idempotence tắt và có nhiều request in-flight:

~~~text
Ứng dụng gửi: A rồi B
Request A gặp lỗi tạm thời
Request B thành công trước
Retry A thành công sau

Broker có thể append: B rồi A
~~~

Producer idempotence sử dụng producer ID và sequence number để broker nhận diện retry của cùng producer. Với Kafka client hiện đại, idempotence bảo vệ thứ tự trong partition khi retry và hỗ trợ tối đa năm request in-flight trên mỗi connection theo cấu hình tương thích.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[retries]": 2147483647
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

Khi dùng Kafka client cũ hoặc tắt idempotence, giới hạn max.in.flight.requests.per.connection ở 1 là một cách giữ thứ tự khi retry, nhưng làm giảm throughput vì chỉ có một request chưa hoàn tất trên mỗi connection.

Idempotence có giới hạn:

- Nó chống duplicate do retry nội bộ của cùng producer session.
- Nó không deduplicate hai lệnh send mới từ application.
- Nó không xác định thứ tự nghiệp vụ giữa nhiều producer độc lập.
- Nó không giữ thứ tự side effect nếu consumer tự xử lý bất đồng bộ.
- Nó không tạo thứ tự toàn cục giữa các partition.

Nếu ứng dụng nhận lỗi send rồi gọi KafkaTemplate.send() lần nữa như một thao tác mới, record có thể bị duplicate nếu lần gửi đầu đã được broker ghi nhưng response bị mất. Dùng eventId ổn định và consumer idempotency để xử lý tình huống này.

### Nhiều thread cùng gửi một key

KafkaProducer thread-safe, nhưng nếu nhiều thread trong ứng dụng đồng thời gọi KafkaTemplate.send() cho cùng một key, thứ tự record phụ thuộc thứ tự các lệnh thực sự được producer tiếp nhận và gửi. Thứ tự nghiệp vụ của các thread không tự được bảo toàn chỉ vì key giống nhau.

Nếu thứ tự giữa các event cùng aggregate quan trọng, hãy serialize việc publish theo aggregate, ví dụ dùng một hàng đợi tuần tự theo orderId hoặc đảm bảo một luồng phát sự kiện duy nhất cho aggregate.

## 9. acks và ordering là hai quyết định khác nhau

acks quy định producer chờ broker xác nhận đến mức nào:

- acks=0: không chờ xác nhận.
- acks=1: chờ leader.
- acks=all: chờ các replica trong ISR.

Các giá trị này ảnh hưởng độ bền và latency ghi. Chúng không quyết định thứ tự toàn topic. Để giữ thứ tự trong partition, cần chú ý key, partitioner, producer concurrency, retry và consumer processing.

Một cấu hình phổ biến cho event nghiệp vụ là acks=all kết hợp idempotence=true. Cấu hình này tăng độ tin cậy của producer và bảo vệ retry nội bộ, nhưng vẫn cần key đúng và handler idempotent.

Không giảm acks chỉ để cải thiện throughput khi nguyên nhân thực sự là consumer xử lý chậm hoặc partition bị hot. Đo bottleneck trước khi thay đổi mức xác nhận.

## 10. Consumer concurrency và thứ tự trong Spring Kafka

Trong cùng một consumer group, mỗi partition được giao cho tối đa một consumer member tại một thời điểm. Spring Kafka tạo nhiều consumer con bằng concurrency trên ConcurrentMessageListenerContainer.

Ví dụ:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

Listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderListenerFactory"
)
public void onOrder(ConsumerRecord<String, OrderEvent> record) {
    orderService.process(record.key(), record.value());
}
~~~

Với topic có tám partition và concurrency bằng bốn, bốn consumer con có thể nhận khoảng hai partition mỗi consumer tùy assignor. Các partition được xử lý song song giữa các consumer thread.

Trong listener record đồng bộ, container gọi listener trên consumer thread. Một consumer thread không đồng thời gọi listener cho nhiều record; do đó các record của partition được xử lý tuần tự trên thread đó. Các partition khác nhau có thể xen kẽ trong vòng poll nhưng vẫn giữ thứ tự offset của từng partition.

### Concurrency không vượt qua giới hạn partition

Nếu topic có ba partition và concurrency bằng sáu, tối đa ba consumer con có thể nhận partition từ topic đó. Ba consumer còn lại không làm tăng throughput của topic.

Nếu ứng dụng có nhiều replica, tổng số consumer member là tổng concurrency của các replica cùng group. Hãy tính cả số replica và concurrency, không chỉ nhìn giá trị concurrency trong một instance.

## 11. Không tự làm mất ordering bằng xử lý bất đồng bộ

Một lỗi phổ biến là listener nhận record đúng thứ tự rồi gửi mỗi record sang executor dùng nhiều thread:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderEvent event) {
    executor.submit(() -> orderService.process(event));
}
~~~

Giả sử partition giao các event theo thứ tự A, B, C. Executor có thể hoàn thành B trước A hoặc C trước B. Kafka vẫn giữ thứ tự log, nhưng side effect nghiệp vụ đã bị đảo thứ tự.

Nếu cần ordering theo partition hoặc key:

- Không fire-and-forget công việc cần thứ tự từ listener.
- Dùng xử lý đồng bộ trong listener nếu thời gian xử lý phù hợp.
- Nếu cần song song, dùng hàng đợi tuần tự riêng cho từng partition hoặc key.
- Chỉ acknowledge/commit khi công việc tương ứng hoàn tất.
- Theo dõi các tác vụ đang chạy trước khi partition bị thu hồi.

Có thể xử lý song song giữa các partition và tuần tự trong từng partition. Ví dụ partition 0 dùng worker A, partition 1 dùng worker B; bên trong mỗi worker, record được xử lý lần lượt.

### asyncAcks không phải công cụ bảo đảm business ordering

Spring Kafka từ phiên bản 2.8 hỗ trợ asyncAcks khi listener dùng manual acknowledgement (MANUAL hoặc MANUAL_IMMEDIATE). Container có thể nhận acknowledgement theo thứ tự khác nhau trong một poll và chỉ commit khi các offset trước đã được xác nhận. Cơ chế này giúp container quản lý offset khi công việc hoàn tất không theo thứ tự.

Tuy nhiên, asyncAcks không tự đảo ngược hoặc tuần tự hóa side effect. Nếu event B cập nhật database trước event A, việc chờ acknowledgement của A không thể biến side effect đã xảy ra thành đúng thứ tự nghiệp vụ. Hãy điều phối công việc trước khi side effect được thực hiện.

## 12. Batch listener: tăng throughput nhưng phải giữ thứ tự theo partition

Batch listener nhận nhiều record trong một lần gọi. Có thể xử lý batch để giảm overhead gọi hàm hoặc gom thao tác database.

Ví dụ bật batch listener:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchOrderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(4);

    return factory;
}
~~~

Listener nhận danh sách record:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchOrderListenerFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderEvent>> records) {
    Map<TopicPartition, List<ConsumerRecord<String, OrderEvent>>> byPartition =
            records.stream().collect(Collectors.groupingBy(
                    record -> new TopicPartition(
                            record.topic(), record.partition()
                    )
            ));

    for (List<ConsumerRecord<String, OrderEvent>> partitionRecords
            : byPartition.values()) {
        partitionRecords.sort(
                Comparator.comparingLong(ConsumerRecord::offset)
        );
        orderService.processPartitionSequentially(partitionRecords);
    }
}
~~~

Đoạn code minh họa cách nhóm theo partition và xử lý tuần tự trong từng nhóm. Nếu muốn xử lý các nhóm partition song song, cần bảo đảm mỗi nhóm có một luồng xử lý tuần tự và việc commit offset không vượt qua record chưa hoàn tất.

Batch listener không tự làm record trong batch được xử lý song song. Chính code ứng dụng quyết định cách xử lý batch. Khi dùng batch, cần xác định rõ:

- Record nào đã thành công.
- Record nào lỗi.
- Có được tiếp tục record sau lỗi hay không.
- Offset an toàn để commit trên từng partition.
- Cách retry hoặc chuyển record lỗi sang DLT mà không phá vỡ thứ tự nghiệp vụ.

## 13. Retry và DLT có thể thay đổi thứ tự xử lý

Retry ảnh hưởng trực tiếp đến ordering, đặc biệt khi dùng retry topic hoặc non-blocking retry.

### Blocking retry

Với blocking retry, record lỗi được retry trên luồng xử lý hiện tại. Các record sau trong partition thường phải chờ record lỗi được xử lý hoặc được recover.

Ưu điểm:

- Giữ thứ tự xử lý trong partition dễ hơn.
- Phù hợp khi event sau phụ thuộc event trước.
- Không để record sau vượt qua một record đang chờ retry.

Đánh đổi:

- Một record lỗi có thể chặn cả partition.
- Lag tăng trong thời gian backoff.
- Lỗi kéo dài có thể ảnh hưởng throughput của partition.

### Non-blocking retry topic

Với retry topic, record lỗi được chuyển sang topic retry để xử lý sau. Consumer chính có thể tiếp tục với record tiếp theo.

Ví dụ:

~~~text
orders partition 0:
A -> B (lỗi) -> C

Luồng chính:
A -> B chuyển sang retry topic -> C tiếp tục

Luồng retry:
          B được xử lý lại sau
~~~

Trong trường hợp này, C có thể được xử lý trước B. Vì vậy, non-blocking retry có thể phá vỡ thứ tự nghiệp vụ ban đầu. Đây là một đánh đổi có chủ đích để tăng khả năng tiến triển của luồng chính.

Nếu cần strict ordering, hãy cân nhắc blocking retry, pause partition hoặc thiết kế retry có khóa theo aggregate. Với retry topic, có thể thêm version/sequence number và chỉ áp dụng event khi version trước đã hoàn tất; nếu chưa, lưu chờ hoặc retry lại theo quy tắc nghiệp vụ.

DLT cũng tạo một khoảng trống trong chuỗi xử lý. Khi record B được đưa vào DLT và consumer tiếp tục C, replay B sau này không tự đưa side effect trở lại trước C. Cần thiết kế replay có kiểm soát, hoặc dùng version guard để ngăn cập nhật trạng thái sai thứ tự.

## 14. Rebalance, in-flight work và thứ tự side effect

Khi group rebalance, partition có thể được thu hồi khỏi consumer cũ và giao cho consumer mới. Nếu listener xử lý đồng bộ, container có thể quản lý quá trình dừng/thu hồi và commit theo cấu hình.

Nếu ứng dụng đã offload công việc sang executor, một tác vụ của consumer cũ có thể vẫn chạy sau khi partition được giao cho consumer mới. Khi đó, hai worker có thể tạo side effect đồng thời hoặc sai thứ tự.

Để giảm rủi ro:

- Tránh để tác vụ nền chạy vô thời hạn sau khi listener trả về.
- Theo dõi và drain các tác vụ đang chạy khi partition bị revoke.
- Chỉ commit các offset có công việc đã hoàn tất.
- Dùng idempotency key và version/sequence guard ở database.
- Dùng fencing token hoặc ownership epoch nếu nhiều worker có thể tranh quyền ghi cùng aggregate.
- Giữ thời gian xử lý phù hợp với max.poll.interval.ms và shutdown timeout.

Rebalance không thay đổi thứ tự offset bên trong partition. Nhưng side effect bất đồng bộ bên ngoài Kafka có thể hoàn tất theo thứ tự khác, đặc biệt khi worker cũ vẫn còn tác vụ đang chạy.

## 15. Đo throughput và xác định bottleneck

Throughput của pipeline bị giới hạn bởi thành phần chậm nhất trong đường đi:

~~~text
Producer
   |
   v
Broker append + replication
   |
   v
Consumer poll + listener
   |
   v
Database / HTTP / downstream
~~~

Một topic có nhiều partition vẫn không đạt throughput cao nếu producer không đủ nhanh, broker thiếu tài nguyên hoặc database xử lý chậm.

Nên đo:

| Thành phần | Chỉ số nên quan sát | Hướng tối ưu |
|---|---|---|
| Producer | Record send rate, request latency, batch size, retry rate | Batching, compression, async send, buffer |
| Broker | Request latency, disk/network, replication lag, ISR | Tài nguyên broker, replication và phân bố partition |
| Partition | Traffic và lag từng partition | Key distribution, hot key, partition count |
| Consumer | Records consumed, listener duration, poll interval, rebalance | Concurrency, xử lý batch, tối ưu listener |
| Downstream | Database latency, pool saturation, HTTP latency | Batch write, connection pool, cache, giới hạn concurrency |

Không nên chỉ nhìn tổng consumer lag. Nếu một partition tăng lag còn các partition khác gần như bằng không, vấn đề có thể là hot key hoặc xử lý chậm trên partition đó. Thêm consumer không chia được partition đang nóng.

### Một cách ước lượng song song

Nếu một topic có P partition và consumer group có C consumer member, số consumer có thể hoạt động với topic đó tối đa là min(P, C). Đây chỉ là giới hạn số luồng đọc theo partition, không phải dự báo throughput.

Throughput thực tế còn phụ thuộc:

- Tốc độ record được producer ghi.
- Kích thước record và batch.
- Chi phí deserialize và xử lý nghiệp vụ.
- Thời gian side effect.
- Mức replication và latency broker.
- Mức độ phân bố đều của key.
- Thời gian retry và rebalance.

## 16. Chiến lược thiết kế theo yêu cầu ordering

| Yêu cầu | Thiết kế phù hợp | Đánh đổi |
|---|---|---|
| Thứ tự toàn cục cho mọi event | Một partition, một luồng xử lý tuần tự hoặc sequencer riêng | Throughput và khả năng song song thấp |
| Thứ tự theo aggregate | Key = aggregate ID, xử lý tuần tự trong partition | Một aggregate nóng bị giới hạn bởi một partition |
| Không cần thứ tự theo thực thể | Keyless hoặc key phân tán, nhiều partition | Không có ordering theo thực thể |
| Thứ tự theo partition, throughput cao | Nhiều partition và nhiều consumer; tuần tự trong từng partition | Không có thứ tự giữa partition |
| Cần retry nhưng không được cho event sau vượt event trước | Blocking retry hoặc pause partition | Một lỗi có thể chặn partition |
| Cần luồng chính tiếp tục khi event lỗi | Retry topic + version guard/resequencing | Event sau có thể hoàn tất trước event lỗi |
| Nhiều producer phát cùng aggregate | Một publisher owner hoặc sequence/version nghiệp vụ | Cần điều phối phát sự kiện |

### Ví dụ thiết kế cho order service

Một thiết kế cân bằng thường là:

1. Topic orders có số partition đủ cho mức song song dự kiến.
2. Producer dùng orderId làm key.
3. Producer bật idempotence và dùng batching/compression phù hợp.
4. Consumer group order-service có concurrency không vượt quá số partition hữu ích.
5. Listener xử lý đồng bộ theo partition hoặc dùng hàng đợi tuần tự theo orderId.
6. Retry blocking cho lỗi cần giữ thứ tự; nếu dùng retry topic thì áp dụng version guard.
7. Database cập nhật theo event version và eventId để chống duplicate hoặc event đến sai thứ tự.

Với cách này, các đơn hàng khác nhau có thể xử lý song song, trong khi các sự kiện của cùng đơn hàng được đưa về cùng partition và áp dụng theo thứ tự đã xác định.

## 17. Cấu hình Spring Kafka minh họa

Producer:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[batch.size]": 32768
        "[linger.ms]": 5
        "[compression.type]": lz4
        "[delivery.timeout.ms]": 120000
~~~

Listener container:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD
    );

    return factory;
}
~~~

Listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "orderListenerFactory"
)
public void onOrder(ConsumerRecord<String, OrderEvent> record) {
    orderService.processInOrder(
            record.key(),
            record.value(),
            record.offset()
    );
}
~~~

Cấu hình minh họa giả định topic có ít nhất sáu partition và hệ thống đích đủ khả năng xử lý sáu consumer đồng thời. Giá trị batch, linger, compression và concurrency cần được đo theo tải thực tế. Việc dùng AckMode.RECORD giúp container xác nhận sau từng lần listener xử lý thành công; nó không tự làm database side effect và Kafka offset commit thành một transaction nguyên tử.

## 18. Kiểm thử ordering và throughput

Kiểm thử cần xác nhận cả thứ tự trong partition và khả năng xử lý song song giữa partition.

Các kịch bản tích hợp hữu ích:

- Gửi nhiều event cùng key và xác nhận chúng được ghi vào cùng partition trong điều kiện partition mapping không đổi.
- Gửi event cho nhiều key khác nhau và xác nhận chúng có thể được phân phối qua nhiều partition.
- Gửi sequence 1, 2, 3 cho cùng aggregate và xác nhận listener áp dụng đúng thứ tự.
- Tạo listener xử lý chậm để đo throughput, lag và thời gian xử lý theo partition.
- Chạy concurrency bằng 1, 2, 4 và 8 để so sánh throughput khi số partition đủ.
- Tăng concurrency vượt partition count và xác nhận consumer dư không tăng throughput.
- Gửi record với producer idempotence bật, mô phỏng lỗi kết nối và kiểm tra retry nội bộ.
- Dùng nhiều thread gửi cùng key để kiểm tra ứng dụng có tuần tự hóa thứ tự phát sự kiện hay không.
- Mô phỏng hot key và quan sát lag của partition tương ứng.
- Tạo listener offload sang executor để chứng minh side effect có thể hoàn tất lệch thứ tự.
- Thử blocking retry và retry topic để quan sát event sau có vượt event lỗi hay không.
- Rebalance khi có tác vụ đang chạy và kiểm tra duplicate, version guard cùng ownership.
- Thay đổi partition count trong môi trường test để kiểm tra key mapping và kế hoạch migration.

Không dùng sleep cố định ngắn để kết luận ordering. Hãy lưu key, partition, offset, event version và thời điểm side effect hoàn tất để so sánh. Với throughput, chạy tải đủ lâu để quan sát cả steady state, rebalance và downstream saturation.

## 19. Các lỗi thiết kế thường gặp

**Dùng nhiều partition nhưng kỳ vọng thứ tự toàn topic.** Kafka chỉ bảo đảm thứ tự trong từng partition. Hãy xác định phạm vi ordering theo nghiệp vụ và dùng key phù hợp.

**Dùng key null cho event cần thứ tự theo aggregate.** Các event có thể được phân phối sang nhiều partition. Gửi business key ổn định.

**Dùng một key chung để giữ thứ tự mọi thứ.** Toàn bộ traffic dồn vào một partition và giới hạn throughput. Chỉ dùng khi thật sự cần thứ tự toàn cục.

**Tăng partition mà không đánh giá key mapping.** Event mới của cùng key có thể đi sang partition khác. Có kế hoạch migration hoặc partitioning ổn định.

**Tắt producer idempotence nhưng để nhiều request in-flight khi retry.** Có thể làm record được append lệch thứ tự trong partition. Bật idempotence hoặc giới hạn in-flight theo yêu cầu client.

**Offload mọi record sang executor nhiều thread.** Side effect có thể hoàn tất ngược thứ tự. Tuần tự hóa theo partition hoặc key.

**Dùng retry topic trong luồng cần strict ordering.** Record lỗi được xử lý sau record tiếp theo. Dùng blocking retry hoặc version guard/resequencing.

**Nhầm asyncAcks với ordering nghiệp vụ.** Cơ chế này quản lý offset acknowledgement, không tuần tự hóa side effect. Điều phối xử lý trước khi ghi dữ liệu.

**Tăng concurrency khi downstream đã bão hòa.** Lag có thể không giảm và hệ thống đích bị quá tải. Đo bottleneck rồi mới tăng.

**Cho rằng producer idempotence bảo đảm không có duplicate ở toàn hệ thống.** Application retry, nhiều producer và consumer redelivery vẫn có thể tạo duplicate side effect. Dùng eventId và idempotent consumer.

## 20. Checklist lựa chọn ordering và throughput

- [ ] Đã xác định ordering cần theo toàn topic, partition hay aggregate/key.
- [ ] Các event cần thứ tự dùng cùng key ổn định.
- [ ] Producer không phát cùng aggregate từ nhiều thread/instance mà thiếu cơ chế sequence hoặc serialization.
- [ ] Partition count đủ cho mức song song cần thiết nhưng không tăng tùy tiện.
- [ ] Đã đánh giá tác động tăng partition đến key mapping.
- [ ] Producer idempotence được bật khi cần bảo vệ retry nội bộ.
- [ ] max.in.flight phù hợp với idempotence và Kafka client version.
- [ ] Batching và compression được tuning bằng số đo thực tế.
- [ ] Consumer concurrency được chọn theo partition và năng lực downstream.
- [ ] Listener không fire-and-forget công việc cần thứ tự.
- [ ] Batch/async processing giữ offset commit theo tiền tố liên tục đã hoàn tất.
- [ ] Retry/DLT không làm event sau vượt event trước ngoài chủ đích.
- [ ] Rebalance có xử lý tác vụ in-flight và duplicate.
- [ ] Có eventId/version để bảo vệ side effect và phát hiện event sai thứ tự.
- [ ] Theo dõi lag, throughput, listener duration và phân bố tải theo partition.

## Kết luận

Kafka tăng throughput bằng cách chia dữ liệu thành nhiều partition và xử lý các partition song song. Đổi lại, Kafka chỉ bảo đảm thứ tự trong từng partition, không tạo thứ tự toàn cục giữa các partition. Muốn giữ thứ tự theo thực thể, hãy dùng business key ổn định để đưa các event cùng aggregate vào một partition và xử lý tuần tự trong partition đó. Batching, compression, producer idempotence và consumer concurrency có thể tăng throughput mà vẫn giữ ordering theo partition nếu được cấu hình đúng. Cần đặc biệt chú ý hot key, tăng partition, xử lý bất đồng bộ, retry topic và rebalance vì các cơ chế này có thể làm side effect hoàn tất sai thứ tự. Hãy bắt đầu từ yêu cầu ordering của nghiệp vụ rồi mới chọn partition count và mức song song.

