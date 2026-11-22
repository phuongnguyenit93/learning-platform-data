# Message listener container

Trong Spring Kafka, **message listener container** là thành phần điều phối việc nhận và chuyển record từ Kafka đến listener của ứng dụng. Container quản lý vòng lặp poll(), consumer, thread thực thi, offset, acknowledgement, lỗi, rebalance và vòng đời chạy. Nhờ đó, listener tập trung vào xử lý nghiệp vụ trong khi container đảm nhiệm phần lớn công việc tích hợp với Kafka Consumer API.

Khi dùng @KafkaListener, Spring Kafka tạo listener endpoint và dùng một container factory để tạo container tương ứng. Hiểu quan hệ giữa listener, factory và container giúp cấu hình đúng mức song song, commit offset, xử lý lỗi và dừng ứng dụng an toàn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của listener container trong kiến trúc Spring Kafka.
- Phân biệt KafkaMessageListenerContainer và ConcurrentMessageListenerContainer.
- Mô tả luồng poll, dispatch, xử lý record và commit offset.
- Cấu hình container factory cho record listener, batch listener và mức concurrency.
- Chọn acknowledgement mode phù hợp và hiểu ảnh hưởng của nó đến giao nhận.
- Quản lý lỗi, retry, dead-letter, lifecycle và hoạt động của consumer thread.
- Nhận diện các giới hạn liên quan đến partition assignment, max.poll.interval.ms và xử lý đồng thời.

## 1. Listener và container khác nhau thế nào?

Listener là điểm gọi mã nghiệp vụ khi có record. Container là thành phần vận hành consumer và gọi listener. Container factory là nơi định nghĩa cách tạo container cho các listener endpoint.

| Thành phần | Trách nhiệm |
|---|---|
| ConsumerFactory | Tạo Kafka Consumer với bootstrap servers, deserializer và consumer properties |
| Listener | Xử lý record hoặc batch record theo nghiệp vụ |
| Listener container | Chạy consumer loop, gọi listener, quản lý acknowledgement, commit, lỗi và rebalance |
| Listener container factory | Tạo và cấu hình container cho các endpoint, thường được khai báo bằng @KafkaListener |
| KafkaListenerEndpointRegistry | Quản lý các container được tạo từ annotation endpoint và cung cấp API lifecycle |

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["@KafkaListener endpoint"] --> B["Listener container factory"]
    B --> C["Listener container"]
    C --> D["ConsumerFactory"]
    D --> E["Kafka Consumer"]
    E --> F["poll()"]
    F --> G["Gọi listener"]
    G --> H["Xử lý nghiệp vụ"]
    H --> I["Acknowledgement / commit offset"]
    I --> F
    G --> J["Exception"]
    J --> K["CommonErrorHandler / recoverer"]
    K --> L["Retry, recover hoặc giữ offset theo cấu hình"]
    L --> F
~~~

Container không thay thế Kafka broker hoặc consumer group. Broker vẫn lưu record, quản lý partition và điều phối group membership. Container điều khiển consumer trong tiến trình Spring của ứng dụng và phối hợp với broker thông qua Kafka Consumer API.

## 2. Hai loại listener container

Spring Kafka cung cấp hai loại container chính.

### KafkaMessageListenerContainer

KafkaMessageListenerContainer vận hành một Kafka Consumer trên một consumer thread. Nó phù hợp khi cần một consumer đơn, tự tạo container hoặc muốn kiểm soát lifecycle ở mức thấp.

Một container có thể được broker gán nhiều partition. Consumer đọc các partition đó trong cùng vòng lặp poll; vì vậy “một container” không có nghĩa là “một partition”.

### ConcurrentMessageListenerContainer

ConcurrentMessageListenerContainer là container điều phối nhiều KafkaMessageListenerContainer con. Mỗi container con có consumer và thread riêng. Đây là lựa chọn thường gặp khi muốn tăng mức song song cho @KafkaListener.

Ví dụ, cấu hình concurrency bằng 3 tạo tối đa ba consumer con cho listener endpoint:

~~~text
ConcurrentMessageListenerContainer
    |
    +-- KafkaMessageListenerContainer #1 -> Consumer thread 1
    |
    +-- KafkaMessageListenerContainer #2 -> Consumer thread 2
    |
    +-- KafkaMessageListenerContainer #3 -> Consumer thread 3
~~~

Broker phân phối partition cho các consumer thuộc cùng group. Nếu topic chỉ có hai partition mà concurrency là 3, tối đa hai consumer có thể được gán partition; consumer còn lại không có partition để đọc. Tăng concurrency vượt số partition không tự làm tăng throughput.

Một consumer có thể nhận nhiều partition. Do đó, số consumer thực sự hoạt động và số partition phải được xem cùng nhau, thay vì mặc định mỗi consumer chỉ xử lý một partition.

## 3. Tạo container từ @KafkaListener

Trong ứng dụng Spring, cách phổ biến là bật annotation support và khai báo ConcurrentKafkaListenerContainerFactory.

Ví dụ cấu hình:

~~~java
@Configuration
@EnableKafka
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            ordersListenerContainerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties().setAckMode(
                ContainerProperties.AckMode.RECORD
        );

        return factory;
    }
}
~~~

Factory trên định nghĩa:

- Consumer được tạo từ ConsumerFactory đã cấu hình key/value deserializer.
- Container dùng concurrency bằng 3.
- Với record listener, container commit offset sau khi listener xử lý xong từng record theo AckMode.RECORD.

Listener có thể chọn factory bằng tên:

~~~java
@Component
public class OrderListener {

    @KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        containerFactory = "ordersListenerContainerFactory"
    )
    public void onOrder(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent event = record.value();

        orderService.process(event);
    }
}
~~~

Nếu không chỉ định containerFactory, Spring Kafka dùng factory mặc định có tên kafkaListenerContainerFactory nếu ứng dụng đã khai báo factory đó. Trong ứng dụng Spring Boot, auto-configuration có thể cung cấp factory mặc định; khi cần cấu hình riêng, hãy đặt tên factory rõ ràng và tham chiếu chính xác từ annotation.

@KafkaListener khai báo endpoint và listener method. Factory quyết định cấu hình container. Container được registry quản lý trong thời gian chạy. Ba thành phần này liên quan với nhau nhưng không phải cùng một đối tượng.

## 4. Vòng đời xử lý record

Một container thường thực hiện vòng lặp sau:

1. Khởi tạo consumer từ ConsumerFactory.
2. Subscribe topic hoặc sử dụng partition assignment được cấu hình.
3. Gọi poll() để lấy các record hiện có.
4. Chuyển record cho listener theo kiểu record hoặc batch.
5. Theo dõi kết quả xử lý, acknowledgement và lỗi.
6. Commit offset theo acknowledgement mode và transaction đang dùng.
7. Tiếp tục poll cho đến khi container được yêu cầu dừng.

Điểm quan trọng là listener thường được gọi trên consumer thread của container. Khi listener đang chạy đồng bộ, consumer đó chưa quay lại poll() để lấy batch tiếp theo. Nếu xử lý quá lâu, consumer có thể vi phạm max.poll.interval.ms và bị xem là không còn hoạt động trong consumer group.

Container chịu trách nhiệm gọi listener và điều phối commit, nhưng không tự biến side effect bên ngoài Kafka thành một phần của Kafka transaction. Nếu listener ghi database rồi lỗi trước khi offset commit, record có thể được giao lại; xử lý nghiệp vụ cần idempotent.

## 5. Record listener và batch listener

Container có thể chuyển record cho listener từng cái một hoặc chuyển cả batch được lấy từ một lần poll.

### Record listener

Record listener nhận một record cho mỗi lần gọi:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    containerFactory = "ordersListenerContainerFactory"
)
public void onOrder(ConsumerRecord<String, OrderEvent> record) {
    orderService.process(record.value());
}
~~~

Kiểu này phù hợp khi mỗi sự kiện có quy trình xử lý riêng, cần phân loại lỗi theo record hoặc cần commit sau mỗi record.

### Batch listener

Để dùng batch listener, cấu hình factory với setBatchListener(true):

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        batchOrdersListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(3);

    return factory;
}
~~~

Listener nhận danh sách record:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchOrdersListenerContainerFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderEvent>> records) {
    orderService.processBatch(records);
}
~~~

Batch listener có thể giảm chi phí gọi hàm và tận dụng xử lý theo lô của database hoặc dịch vụ đích. Đổi lại, ứng dụng cần xác định cách xử lý khi chỉ một record trong batch lỗi. Nếu xử lý cả batch trong một transaction database, cần bảo đảm transaction đó thực sự bao phủ các thay đổi cần nguyên tử.

max.poll.records giới hạn số record trả về trong một lần poll. Đây là thuộc tính consumer; nó ảnh hưởng kích thước batch nhưng không phải số partition và cũng không phải concurrency của container.

## 6. Acknowledgement mode và commit offset

Container theo dõi khi nào record đã được xử lý để commit offset. Spring Kafka cung cấp các acknowledgement mode trong ContainerProperties.AckMode.

| Mode | Thời điểm commit |
|---|---|
| RECORD | Sau khi listener xử lý xong từng record |
| BATCH | Sau khi xử lý xong tất cả record trong batch trả về từ một lần poll |
| TIME | Sau batch khi thời gian acknowledgement đã đạt ngưỡng cấu hình |
| COUNT | Sau batch khi số record đã xử lý đạt ngưỡng cấu hình |
| COUNT_TIME | Sau batch khi đạt ngưỡng số lượng hoặc thời gian |
| MANUAL | Listener gọi acknowledge; container commit theo ranh giới batch |
| MANUAL_IMMEDIATE | Commit ngay khi acknowledge được gọi trên consumer thread; nếu gọi từ thread khác, acknowledgement được xử lý theo cơ chế container |

Với record listener, RECORD hữu ích khi muốn offset tiến sau từng record. BATCH thường giảm số lần commit nhưng nếu một record trong batch lỗi, hành vi retry và commit cần được hiểu cùng error handler.

Ví dụ chọn BATCH:

~~~java
factory.getContainerProperties().setAckMode(
    ContainerProperties.AckMode.BATCH
);
~~~

### Manual acknowledgement

Khi nghiệp vụ cần chủ động xác định lúc xác nhận record, có thể dùng MANUAL hoặc MANUAL_IMMEDIATE và nhận Acknowledgment trong listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service-manual",
    containerFactory = "manualOrdersListenerContainerFactory"
)
public void onOrder(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(event);

    acknowledgment.acknowledge();
}
~~~

Factory tương ứng cần được cấu hình với acknowledgement mode manual:

~~~java
factory.getContainerProperties().setAckMode(
    ContainerProperties.AckMode.MANUAL
);
~~~

Chỉ acknowledge sau khi công việc cần thiết đã hoàn tất. Nếu database commit thành công nhưng tiến trình dừng trước khi offset Kafka được commit, record vẫn có thể được giao lại. Vì vậy, manual acknowledgement không loại bỏ yêu cầu idempotency.

Spring Kafka quản lý commit offset của container; trong các phiên bản hiện đại, container mặc định tắt Kafka auto-commit nếu ứng dụng không chủ động cấu hình khác. Hãy tránh bật enable.auto.commit khi muốn container điều khiển acknowledgement một cách nhất quán.

Khi Kafka transaction được cấu hình cho listener container, offset có thể được gửi vào transaction cùng output Kafka. Khi đó cần xem acknowledgement, transaction manager và listener container như một cấu hình thống nhất; không suy luận rằng acknowledge() đồng nghĩa database hoặc API bên ngoài đã commit.

## 7. Concurrency, partition và thứ tự xử lý

Concurrency quyết định số consumer thread mà một concurrent container có thể vận hành. Partition assignment quyết định mỗi consumer thực tế nhận những partition nào.

Ví dụ topic có sáu partition và listener concurrency bằng ba:

~~~text
Topic orders: P0  P1  P2  P3  P4  P5

Consumer 1:   P0  P1
Consumer 2:   P2  P3
Consumer 3:   P4  P5
~~~

Đây chỉ là minh họa một cách phân phối; assignment thực tế phụ thuộc partition assignor, số consumer trong group và các member đang hoạt động.

Các nguyên tắc cần nhớ:

- Concurrency lớn hơn số partition không tạo thêm khả năng xử lý song song cho topic đó.
- Một consumer có thể xử lý nhiều partition.
- Trong cùng một consumer thread, listener được gọi theo thứ tự record container nhận từ poll; thứ tự của record trong từng partition được Kafka giữ theo offset.
- Các partition khác nhau không có thứ tự toàn cục với nhau.
- Nếu listener tự gửi công việc sang executor hoặc xử lý bất đồng bộ, thứ tự hoàn tất side effect có thể khác thứ tự record đã nhận.
- Với concurrent container, cùng một listener bean có thể được nhiều thread gọi đồng thời; bean cần stateless hoặc bảo đảm thread-safe.

Chọn concurrency theo số partition, tài nguyên xử lý và thời gian xử lý trung bình. Đặt concurrency quá cao có thể tạo thêm thread và consumer nhưng không tăng throughput nếu partition không đủ hoặc hệ thống đích đã bão hòa.

## 8. Giữ poll loop khỏe mạnh

Kafka consumer cần gọi poll() đều đặn. Một listener xử lý đồng bộ quá lâu có thể khiến thời gian giữa hai lần poll vượt max.poll.interval.ms. Khi đó broker có thể loại consumer khỏi group và phân phối lại partition.

Các tham số thường cần xem cùng nhau:

| Thuộc tính | Ý nghĩa |
|---|---|
| max.poll.interval.ms | Thời gian tối đa giữa các lần poll trước khi consumer bị xem là không còn tiến triển |
| max.poll.records | Số record tối đa trả về trong một lần poll |
| session.timeout.ms | Thời gian broker chờ heartbeat của consumer trước khi xem member đã mất |
| heartbeat.interval.ms | Chu kỳ heartbeat trong cơ chế consumer group |
| pollTimeout | Thời gian container chờ trong lời gọi poll |

Nếu batch có nhiều record hoặc một record xử lý rất lâu, hãy đánh giá tổng thời gian xử lý của batch so với max.poll.interval.ms. Có thể giảm max.poll.records, tối ưu listener hoặc tăng khoảng thời gian phù hợp sau khi hiểu tác động đến rebalance. Không nên chỉ tăng timeout để che giấu một listener bị treo.

Nếu cần offload công việc sang thread khác, phải thiết kế rõ cách giữ thứ tự, truyền kết quả lỗi về container, và chỉ acknowledge khi side effect đã hoàn tất. Không sử dụng Kafka Consumer từ thread tùy ý vì Kafka Consumer không thread-safe. Các cơ chế async acknowledgement cần được cấu hình và hiểu rõ vì offset có thể phải chờ các record trước đó hoàn tất.

## 9. Xử lý lỗi trong container

Khi listener ném exception, container chuyển lỗi đến error handler. Error handler quyết định retry, bỏ qua, phục hồi hoặc chuyển record sang nơi khác. Trong các phiên bản Spring Kafka hiện đại, CommonErrorHandler là điểm cấu hình chung cho lỗi của record listener và batch listener.

Ví dụ dùng DefaultErrorHandler cùng dead-letter publisher:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        ordersWithErrorHandlingContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                KafkaTemplate<String, OrderEvent> kafkaTemplate) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
    var backOff = new FixedBackOff(1_000L, 2L);

    factory.setCommonErrorHandler(
        new DefaultErrorHandler(recoverer, backOff)
    );

    return factory;
}
~~~

Ví dụ này minh họa retry với backoff và chuyển record đến dead-letter khi hết lần thử. Cần cấu hình producer serializer phù hợp cho cả record gốc lẫn record lỗi; nếu DLT cần giữ partition tương ứng, topic đích phải có partition phù hợp và recoverer phải được cấu hình đúng cho topology đó.

Một số điểm cần lưu ý:

- Retry chặn trên listener container có thể giữ record lỗi ở đầu luồng và làm record sau phải chờ.
- Error handler có thể seek hoặc quản lý offset để record được giao lại; kết quả cụ thể phụ thuộc cấu hình handler và acknowledgement mode.
- Batch listener có ngữ nghĩa lỗi khác record listener vì một lần gọi chứa nhiều record. Nếu cần retry một phần batch, hãy dùng cơ chế batch error handler phù hợp và hiểu rõ record nào đã xử lý.
- DLT là nơi lưu record lỗi để điều tra hoặc replay; việc publish vào DLT không đồng nghĩa nghiệp vụ đã hoàn tất.
- Handler nên phân biệt lỗi tạm thời có thể retry và lỗi dữ liệu không thể khắc phục bằng retry.

## 10. Lifecycle và điều khiển container

Container có lifecycle riêng: start, stop, pause và resume. Với các listener được khai báo bằng @KafkaListener, KafkaListenerEndpointRegistry quản lý container được tạo từ endpoint.

Ví dụ tìm container theo id đã khai báo trong annotation:

~~~java
@Component
public class ListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

pause() và resume() là yêu cầu điều khiển container; trạng thái pause được áp dụng trong vòng poll của consumer. Chúng hữu ích khi cần tạm dừng nhận thêm record để bảo trì hoặc giảm tải. Cần theo dõi consumer lag trong thời gian pause vì record vẫn có thể tiếp tục được producer ghi vào topic.

Các thuộc tính lifecycle thường gặp:

- autoStartup: quyết định container có tự khởi động cùng application context hay không.
- id của @KafkaListener: định danh endpoint để registry tìm đúng container.
- start() và stop(): điều khiển vòng đời container.
- pause() và resume(): tạm dừng hoặc tiếp tục việc nhận record.
- KafkaListenerEndpointRegistry: quản lý các container được tạo từ annotation.

Container khai báo trực tiếp dưới dạng bean và container do annotation tạo ra có cách quản lý lifecycle khác nhau. Với annotation endpoint, hãy dùng registry để truy cập container thay vì giả định nó luôn là một bean độc lập có thể inject theo tên.

Khi ứng dụng shutdown, container cần có cơ hội dừng consumer và hoàn tất phần xử lý đang chạy theo cấu hình shutdown. Listener nên có thời gian xử lý hữu hạn, xử lý lỗi rõ ràng và không giữ thread vô thời hạn.

## 11. Theo dõi trạng thái và sự kiện container

Container có thể phát các application event hữu ích cho vận hành, chẳng hạn sự kiện listener idle khi không nhận record trong một khoảng thời gian đã cấu hình. Với concurrent container, sự kiện có thể phát từ từng container con; khi xử lý event, cần xác định đúng listener/container phát ra sự kiện.

Các tín hiệu nên quan sát:

- Consumer lag theo group và partition.
- Số lần rebalance và thời gian hoàn tất rebalance.
- Số record xử lý thành công, lỗi, retry và dead-letter.
- Thời gian xử lý listener và thời gian giữa các lần poll.
- Số consumer hoạt động so với số partition được cấp.
- Trạng thái pause, resume và thời gian container không có record.

Idle không nhất thiết là lỗi: topic có thể không có sự kiện mới. Ngược lại, container đang chạy cũng không chứng minh record được xử lý thành công. Cần kết hợp trạng thái container với lag, lỗi listener và kết quả ở hệ thống đích.

## 12. Lựa chọn cấu hình theo tình huống

| Nhu cầu | Cấu hình hoặc cơ chế | Lưu ý |
|---|---|---|
| Xử lý từng record và commit sau mỗi record | Record listener + AckMode.RECORD | Phù hợp khi cần ranh giới xử lý rõ theo record |
| Xử lý nhiều record theo lô | Batch listener + setBatchListener(true) | Cần thiết kế xử lý lỗi trong batch |
| Tăng số consumer cho một endpoint | Concurrent container + setConcurrency(n) | Bị giới hạn bởi số partition được cấp |
| Chủ động xác nhận sau side effect | Manual acknowledgement | Handler vẫn cần idempotent |
| Retry và gửi record lỗi sang DLT | CommonErrorHandler, DefaultErrorHandler, recoverer | Cấu hình serializer và topology DLT |
| Tạm dừng listener khi bảo trì | Registry lấy container rồi gọi pause()/resume() | Theo dõi lag trong thời gian pause |
| Listener xử lý lâu | Điều chỉnh batch size, poll interval, tối ưu handler | Tránh vượt max.poll.interval.ms |

Không có một cấu hình container phù hợp cho mọi listener. Hãy lựa chọn theo yêu cầu về thứ tự, độ trễ, throughput, độ bền, kiểu listener và thời gian xử lý nghiệp vụ.

## 13. Các lỗi thiết kế thường gặp

**Đặt concurrency cao hơn số partition rồi kỳ vọng throughput tăng tuyến tính.** Consumer thừa không được gán partition. Hãy xác định số partition và consumer member thực tế trước khi tăng concurrency.

**Chạy công việc lâu trên consumer thread.** Listener chiếm thời gian giữa hai lần poll, có thể vượt max.poll.interval.ms và kích hoạt rebalance. Hãy giới hạn thời gian xử lý và điều chỉnh batch/poll theo tải thực tế.

**Dùng listener bean có trạng thái mutable nhưng không đồng bộ.** Concurrent container có thể gọi cùng bean từ nhiều thread. Dùng biến cục bộ, stateless service hoặc cơ chế đồng bộ phù hợp.

**Acknowledge trước khi side effect hoàn tất.** Nếu commit offset trước khi ghi database thành công, record có thể bị bỏ qua sau lỗi. Chỉ acknowledge sau công việc cần thiết và làm side effect idempotent.

**Cho rằng retry hoặc DLT tự đảm bảo không mất dữ liệu.** Retry có thể thất bại, DLT có thể không publish được, hoặc replay có thể áp dụng lại event cũ. Cần theo dõi, lưu dấu event và kiểm thử quy trình phục hồi.

**Offload xử lý sang executor nhưng commit offset ngay.** Công việc nền có thể chưa hoàn tất khi offset đã commit. Chỉ acknowledge sau khi hoàn thành hoặc dùng một thiết kế async acknowledgement có kiểm soát.

## 14. Checklist trước khi đưa listener vào vận hành

- [ ] Listener endpoint sử dụng đúng container factory và consumer group.
- [ ] Record listener hay batch listener đã được chọn theo cách xử lý nghiệp vụ.
- [ ] Concurrency phù hợp với số partition và năng lực hệ thống đích.
- [ ] Acknowledgement mode phản ánh đúng thời điểm side effect hoàn tất.
- [ ] max.poll.records và max.poll.interval.ms phù hợp với thời gian xử lý.
- [ ] Listener bean an toàn khi nhiều consumer thread gọi đồng thời.
- [ ] Error handler, retry, backoff và DLT có hành vi đã được kiểm thử.
- [ ] Container có lifecycle phù hợp và có thể pause/resume khi vận hành.
- [ ] Có metric hoặc cảnh báo cho lag, rebalance, lỗi, retry và DLT.
- [ ] Side effect ngoài Kafka có idempotency để chịu được record được giao lại.

## Kết luận

Message listener container là lớp vận hành nối Kafka Consumer với listener của Spring. Container điều phối poll loop, consumer thread, partition assignment, acknowledgement, commit offset, xử lý lỗi và lifecycle. KafkaMessageListenerContainer phù hợp cho một consumer; ConcurrentMessageListenerContainer tạo nhiều consumer con để xử lý song song theo partition. Khi cấu hình container, cần phối hợp concurrency, batch/record listener, acknowledgement mode, error handler và poll interval với yêu cầu nghiệp vụ. Listener vẫn phải chịu được retry và xử lý lặp, đặc biệt khi side effect nằm ngoài Kafka.

