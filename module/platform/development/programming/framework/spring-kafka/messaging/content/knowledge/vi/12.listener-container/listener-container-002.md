# ConcurrentKafkaListenerContainerFactory

## Mục tiêu của bài học

Trong chương **Listener container**, bài này giải thích vai trò và cách cấu hình `ConcurrentKafkaListenerContainerFactory` trong Spring Kafka. Factory là nơi tạo listener container cho các endpoint khai báo bằng `@KafkaListener`; nó kết nối cấu hình consumer với cách listener nhận bản ghi, xử lý offset, concurrency và lỗi.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Trong kiến trúc đó, factory quyết định listener container được tạo và vận hành như thế nào.

Sau bài học, người học có thể:

- Phân biệt `ConcurrentKafkaListenerContainerFactory`, `ConcurrentMessageListenerContainer`, `KafkaMessageListenerContainer` và `ConsumerFactory`.
- Hiểu cách `@KafkaListener` được kết nối với factory.
- Cấu hình consumer factory, concurrency và acknowledgment mode.
- Tạo factory riêng cho record listener và batch listener.
- Cấu hình error handler, converter và các thuộc tính container ở đúng cấp.
- Quản lý vòng đời listener container thông qua registry.
- Chọn factory phù hợp cho từng nhóm listener và kiểm thử cấu hình.

## 1. ConcurrentKafkaListenerContainerFactory là gì?

`ConcurrentKafkaListenerContainerFactory<K, V>` là factory của Spring Kafka dùng để tạo `ConcurrentMessageListenerContainer<K, V>` cho các listener endpoint, thường được khai báo bằng `@KafkaListener`.

Factory tập hợp các thiết lập cần áp dụng khi tạo container, chẳng hạn:

- `ConsumerFactory` dùng để tạo Kafka consumer.
- Số consumer container con thông qua concurrency.
- Chế độ nhận record hoặc batch.
- Cách xác nhận và commit offset.
- Error handler dùng khi listener xử lý thất bại.
- Message converter và một số tùy chỉnh container khác.

Factory không trực tiếp poll Kafka và không phải consumer. Nó tạo container với cấu hình đã chọn; container mới quản lý vòng đời consumer và gọi phương thức listener.

~~~mermaid
flowchart TD
    A["@KafkaListener endpoint"] --> B["ConcurrentKafkaListenerContainerFactory"]
    B --> C["ConcurrentMessageListenerContainer"]
    C --> D["KafkaMessageListenerContainer 1"]
    C --> E["KafkaMessageListenerContainer 2"]
    C --> F["KafkaMessageListenerContainer 3"]
    D --> G["Kafka Consumer 1"]
    E --> H["Kafka Consumer 2"]
    F --> I["Kafka Consumer 3"]
    G --> J["Kafka Broker"]
    H --> J
    I --> J
~~~

Trong sơ đồ, factory tạo một concurrent container. Container này quản lý các container con; mỗi container con tạo và quản lý một Kafka consumer riêng.

## 2. Phân biệt các thành phần liên quan

Các lớp có tên gần giống nhau nhưng trách nhiệm khác nhau.

| Thành phần | Trách nhiệm |
|---|---|
| `ConcurrentKafkaListenerContainerFactory<K, V>` | Tạo concurrent listener container từ cấu hình |
| `ConcurrentMessageListenerContainer<K, V>` | Quản lý một hoặc nhiều child container để tiêu thụ đồng thời |
| `KafkaMessageListenerContainer<K, V>` | Quản lý một Kafka consumer và vòng lặp poll/listener |
| `ConsumerFactory<K, V>` | Tạo Kafka consumer với cấu hình, deserializer và các thiết lập tương ứng |
| `@KafkaListener` | Khai báo listener endpoint và phương thức xử lý |
| `KafkaListenerEndpointRegistry` | Quản lý vòng đời các container được tạo từ endpoint annotation |

Có thể ghi nhớ theo luồng:

1. Ứng dụng khai báo `@KafkaListener`.
2. Spring xử lý annotation và tạo listener endpoint.
3. Endpoint chọn một container factory.
4. Factory tạo concurrent message listener container.
5. Container tạo các child container theo concurrency.
6. Child container tạo Kafka consumer từ ConsumerFactory.
7. Consumer subscribe topic, tham gia group, poll record và gọi listener.

### 2.1. Factory không phải ConsumerFactory

Hai factory này phục vụ hai tầng khác nhau:

- `ConsumerFactory` tạo đối tượng Kafka consumer của Kafka client.
- `ConcurrentKafkaListenerContainerFactory` tạo Spring listener container để quản lý các consumer đó.

Một factory listener có thể sử dụng một ConsumerFactory phù hợp với kiểu key/value và cấu hình consumer. Nếu nhiều nhóm listener cần deserializer, group hoặc security khác nhau, có thể khai báo nhiều ConsumerFactory và container factory riêng.

### 2.2. Factory không phải container

Factory là đối tượng cấu hình và tạo container. Container là đối tượng chạy trong ứng dụng, thực hiện start, stop, pause, resume và quản lý consumer.

Một factory có thể tạo nhiều container cho nhiều phương thức `@KafkaListener`. Mỗi endpoint có container riêng, dù các endpoint có thể dùng chung một factory.

## 3. Vì sao Spring Kafka cần container factory?

Không có factory, mỗi listener sẽ phải tự xử lý nhiều chi tiết về consumer, polling, commit offset, lỗi và vòng đời. Container factory chuẩn hóa các thiết lập này để các listener có thể dùng chung một cấu hình.

Ví dụ một ứng dụng Billing có các listener:

- Nhận `commerce.order.created`.
- Nhận `commerce.payment.captured`.
- Nhận `commerce.order.cancelled`.

Các listener có thể cùng dùng một factory nếu chúng có cùng kiểu dữ liệu, cách deserialize, acknowledgment và chính sách lỗi. Nếu một listener cần batch, concurrency khác hoặc retry riêng, nên cân nhắc một factory khác.

Factory giúp:

- Tập trung cấu hình consumer container.
- Tái sử dụng thiết lập giữa các listener.
- Tách biệt nhóm listener theo cách xử lý.
- Giảm lặp code cấu hình.
- Kiểm soát concurrency và acknowledgment nhất quán.
- Dễ kiểm thử cấu hình endpoint.

Dùng chung factory không có nghĩa các listener dùng chung một consumer. Mỗi endpoint có container và consumer riêng. Nếu hai endpoint subscribe cùng topic và dùng cùng group ID, các consumer của chúng cùng tham gia một group và chia sẻ partition; chúng không nhận hai bản sao độc lập của mọi record. Nếu mỗi listener cần đọc toàn bộ luồng độc lập, cần dùng group ID khác nhau.

## 4. Tên factory mặc định và custom factory

Spring Kafka sử dụng tên mặc định `kafkaListenerContainerFactory` nếu thuộc tính `containerFactory` của `@KafkaListener` không được chỉ định.

Ví dụ listener dùng factory mặc định:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Nếu ứng dụng có bean factory tên `kafkaListenerContainerFactory`, endpoint có thể sử dụng factory đó theo mặc định.

Khi khai báo factory có tên riêng, chỉ định tên bằng thuộc tính `containerFactory`:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Tên trong `containerFactory` phải khớp chính xác với tên bean Spring. Nếu sai tên hoặc bean chưa được đăng ký, endpoint không thể tạo container đúng cách.

### 4.1. Spring Boot và Spring Framework

Trong cấu hình Spring Framework thuần, cần bật hạ tầng annotation listener, thường bằng `@EnableKafka`, và khai báo factory bean.

Với Spring Boot, auto-configuration có thể cung cấp consumer factory và listener container factory mặc định khi các điều kiện phù hợp. Khi khai báo bean factory tùy chỉnh, cần kiểm tra điều kiện auto-configuration và tên bean đang được dùng để tránh vô tình thay thế cấu hình mặc định.

Không nên khai báo nhiều bean cùng tên hoặc dựa vào thứ tự khởi tạo để quyết định factory. Hãy đặt tên rõ ràng và chỉ định `containerFactory` khi ứng dụng có nhiều cấu hình.

## 5. Cấu hình một ConcurrentKafkaListenerContainerFactory cơ bản

Giả sử ứng dụng nhận sự kiện `OrderCreated` từ topic `commerce.order.created`.

Khai báo event:

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {
}
~~~

Cấu hình ConsumerFactory và container factory:

~~~java
@Configuration
@EnableKafka
public class KafkaListenerConfiguration {

    @Bean
    public ConsumerFactory<String, OrderCreated> orderConsumerFactory() {
        Map<String, Object> properties = new HashMap<>();

        properties.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "billing-service"
        );
        properties.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest"
        );

        return new DefaultKafkaConsumerFactory<>(
            properties,
            new StringDeserializer(),
            new JsonDeserializer<>(OrderCreated.class, false)
        );
    }

    @Bean(name = "ordersKafkaListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> orderConsumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(orderConsumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Các điểm cần hiểu:

- `ConsumerFactory<String, OrderCreated>` tạo consumer có key kiểu String và value kiểu OrderCreated.
- `StringDeserializer` chuyển key từ byte sang String.
- `JsonDeserializer` chuyển JSON value thành OrderCreated.
- `setConsumerFactory(...)` gắn ConsumerFactory vào container factory.
- `setConcurrency(3)` yêu cầu mỗi concurrent container được tạo từ factory quản lý ba consumer container con.
- `AckMode.RECORD` chọn commit sau khi listener xử lý xong từng record theo cơ chế của container.

Ví dụ dùng JSON deserializer với kiểu value cố định. Trong ứng dụng thực tế, cần thống nhất cấu hình serializer phía producer, deserializer phía consumer, trusted packages hoặc type mapping theo cách triển khai JSON của hệ thống.

Với Spring Framework thuần, `@EnableKafka` kích hoạt xử lý `@KafkaListener`. Trong Spring Boot, kiểm tra hạ tầng annotation đã được auto-configure theo phiên bản đang dùng trước khi thêm cấu hình bật thủ công.

### 5.1. Listener chọn factory

~~~java
@Service
public class OrderEventListener {

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service",
        containerFactory = "ordersKafkaListenerContainerFactory"
    )
    public void handle(OrderCreated event) {
        // Xử lý nghiệp vụ billing.
    }
}
~~~

Khi Spring đăng ký endpoint, nó tìm bean factory có tên `ordersKafkaListenerContainerFactory`, tạo container và khởi động consumer theo lifecycle của ứng dụng.

## 6. Cấu hình concurrency

Concurrency là số child container/consumer mà một `ConcurrentMessageListenerContainer` quản lý. Mỗi child container sử dụng một Kafka consumer riêng.

Có thể đặt concurrency ở factory:

~~~java
factory.setConcurrency(3);
~~~

Khi đó, các endpoint sử dụng factory này nhận giá trị mặc định concurrency bằng 3, trừ khi có cấu hình cụ thể ở endpoint ghi đè.

Cũng có thể đặt concurrency trực tiếp trên listener:

~~~java
@KafkaListener(
    id = "order-created-listener",
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "ordersKafkaListenerContainerFactory",
    concurrency = "5"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Thuộc tính `concurrency` của annotation có kiểu chuỗi để hỗ trợ placeholder hoặc expression. Khi được khai báo, giá trị này được dùng cho endpoint tương ứng thay cho mức concurrency mặc định từ factory.

### 6.1. Concurrency bị giới hạn bởi partition

Trong cùng consumer group, một partition tại một thời điểm chỉ được gán cho tối đa một consumer.

Ví dụ topic có 4 partition:

| Concurrency | Consumer được tạo | Consumer tối đa được gán partition | Hệ quả |
|---:|---:|---:|---|
| 1 | 1 | 1 | Một consumer nhận cả 4 partition |
| 2 | 2 | 2 | Hai consumer có thể chia nhau 4 partition |
| 4 | 4 | 4 | Có thể đạt một consumer trên mỗi partition |
| 6 | 6 | 4 | Ít nhất 2 consumer không có partition |

Nếu ứng dụng chạy nhiều instance, tổng số consumer trong group bằng tổng concurrency của các instance. Ví dụ hai instance, mỗi instance concurrency 3, tạo tổng cộng 6 consumer trong group.

Tăng concurrency vượt số partition không làm tăng mức song song hữu ích của topic đó. Hãy cân nhắc thời gian xử lý, CPU, database connection pool và tải downstream trước khi tăng số consumer.

### 6.2. Concurrency và thứ tự

Kafka giữ thứ tự trong phạm vi một partition. Khi các partition được xử lý bởi các consumer khác nhau, không có thứ tự toàn cục giữa các partition.

Nếu các event của cùng một order cần xử lý theo thứ tự, producer nên dùng order ID làm key để các event liên quan được định tuyến vào cùng partition theo partitioner phù hợp.

Không nên chuyển việc xử lý record sang thread pool khác rồi acknowledge ngay nếu nghiệp vụ cần bảo toàn thứ tự và bảo đảm xử lý hoàn tất trước commit. Khi xử lý bất đồng bộ, ứng dụng phải thiết kế cơ chế đồng bộ, lỗi và acknowledgment tương ứng.

## 7. Cấu hình acknowledgment và commit offset

Container factory cung cấp nơi thiết lập `ContainerProperties`, trong đó có acknowledgment mode.

Ví dụ:

~~~java
factory.getContainerProperties()
    .setAckMode(ContainerProperties.AckMode.RECORD);
~~~

Một số AckMode phổ biến:

| AckMode | Cách hoạt động khái quát |
|---|---|
| RECORD | Commit sau khi listener xử lý xong từng record |
| BATCH | Commit sau khi xử lý xong batch của lần poll |
| TIME | Commit khi đạt khoảng thời gian cấu hình và các record liên quan đã xử lý |
| COUNT | Commit khi đạt số record cấu hình |
| COUNT_TIME | Kết hợp điều kiện thời gian và số record |
| MANUAL | Listener chủ động acknowledge; container thực hiện commit theo semantics của chế độ |
| MANUAL_IMMEDIATE | Yêu cầu commit ngay khi acknowledge được gọi trên consumer thread |

`RECORD` phù hợp với record listener. Với batch listener, cần chọn chế độ acknowledgment tương thích với batch semantics, thường là `BATCH` hoặc chế độ manual phù hợp.

Để container quản lý commit, nên cấu hình consumer `enable.auto.commit=false`. Spring Kafka listener container thường tắt auto commit theo mặc định trong các phiên bản hiện đại, nhưng cấu hình rõ ràng giúp ý định của ứng dụng dễ hiểu hơn.

### 7.1. Manual acknowledgment

Ví dụ listener nhận acknowledgment:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "manualAckListenerContainerFactory"
)
public void handle(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    billingService.process(event);

    acknowledgment.acknowledge();
}
~~~

Factory được dùng ở đây phải cấu hình AckMode.MANUAL hoặc MANUAL_IMMEDIATE tương ứng.

Chỉ acknowledge sau khi nghiệp vụ cần thiết đã hoàn tất. Nếu commit offset trước khi ghi database thành công, consumer có thể không nhận lại record sau restart. Nếu xử lý thành công nhưng chưa commit, record có thể được giao lại; vì vậy listener nên có tính idempotent.

## 8. Tạo factory cho batch listener

Mặc định, listener thường nhận từng record. Nếu muốn xử lý nhiều record trong một lần gọi listener, có thể tạo factory riêng và bật batch listener:

~~~java
@Bean(name = "batchOrdersListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchOrdersListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> orderConsumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(orderConsumerFactory);
    factory.setConcurrency(2);
    factory.setBatchListener(true);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);

    return factory;
}
~~~

Listener nhận một danh sách event:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-batch-service",
    containerFactory = "batchOrdersListenerContainerFactory"
)
public void handleBatch(List<OrderCreated> events) {
    for (OrderCreated event : events) {
        // Xử lý event trong batch.
    }
}
~~~

Batch size thực tế phụ thuộc số record mà consumer nhận trong lần poll và cấu hình như `max.poll.records`. `setBatchListener(true)` thay đổi kiểu gọi listener; nó không tự bảo đảm mỗi batch luôn có một số lượng record cố định.

### 8.1. Khi nào nên dùng batch?

Batch listener có thể phù hợp khi:

- Database hỗ trợ insert/update theo batch.
- Nhiều record có thể được xử lý bằng cùng một thao tác.
- Muốn giảm chi phí gọi listener và transaction overhead.
- Nghiệp vụ chấp nhận xử lý theo lô và có chiến lược lỗi rõ ràng.

Batch cũng làm tăng độ phức tạp khi một record trong batch lỗi. Cần xác định retry toàn batch hay chỉ phần tử lỗi, cách commit offset và cách tránh xử lý lặp các phần tử đã thành công.

Không nên dùng batch chỉ vì muốn tăng throughput. Hãy đo thời gian poll, batch size, processing time, consumer lag và tải downstream.

## 9. Cấu hình error handler cho factory

Các listener được tạo từ cùng một factory thường dùng chung error handler. Vì vậy, factory là nơi thích hợp để đặt chính sách xử lý lỗi chung cho nhóm listener có cùng yêu cầu.

Ví dụ dùng `DefaultErrorHandler` với backoff:

~~~java
@Bean
public DefaultErrorHandler kafkaListenerErrorHandler() {
    return new DefaultErrorHandler(
        new FixedBackOff(1_000L, 2L)
    );
}
~~~

Gắn handler vào factory khi tạo bean:

~~~java
@Bean(name = "ordersKafkaListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaListenerErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaListenerErrorHandler);

    return factory;
}
~~~

Ví dụ này minh họa retry có khoảng nghỉ cố định. Cần điều chỉnh số lần retry và backoff theo loại exception, thời gian xử lý và khả năng của hệ thống phụ thuộc.

Nếu cần dead-letter topic, có thể kết hợp `DefaultErrorHandler` với `DeadLetterPublishingRecoverer` và một KafkaTemplate có serializer phù hợp. Cần bảo đảm DLT tồn tại, có đủ partition tương ứng khi giữ nguyên partition nguồn và có chính sách retention, ACL cũng như quy trình xử lý lại.

### 9.1. Khi nào cần factory riêng cho error policy?

Giả sử ứng dụng có hai listener:

- Listener tạo hóa đơn cần retry ngắn và chuyển lỗi cuối cùng sang DLT.
- Listener analytics có thể bỏ qua một số record không hợp lệ theo chính sách riêng.

Nếu hai listener dùng chung factory, error handler dùng chung có thể không đáp ứng cả hai nhu cầu. Hãy tạo hai factory với error policy riêng, sau đó chỉ định factory tương ứng trong từng `@KafkaListener`.

Không nên thay đổi error handler của một factory dùng chung trong lúc container đang chạy rồi kỳ vọng mọi endpoint tự động cập nhật đồng bộ. Cấu hình nên được quyết định trước khi endpoint được tạo.

## 10. Message converter và kiểu dữ liệu listener

Consumer deserializer chuyển byte từ Kafka thành key/value Java. Message converter của Spring Kafka có thể tiếp tục chuyển đổi record thành kiểu tham số listener và ánh xạ headers.

Với JSON deserializer đã trả về `OrderCreated`, listener có thể nhận trực tiếp:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void handle(OrderCreated event) {
    // event đã được deserialize thành OrderCreated.
}
~~~

Nếu cần converter ở cấp Spring Message, có thể cấu hình record message converter trên factory:

~~~java
factory.setRecordMessageConverter(messageConverter);
~~~

Với batch listener, dùng batch message converter phù hợp nếu ứng dụng cần chuyển đổi payload/header theo batch.

Cần phân biệt:

- Deserializer làm việc ở tầng Kafka consumer, chuyển byte thành key/value.
- Message converter làm việc ở tầng Spring Kafka, chuyển record thành dạng message/argument mà listener sử dụng.

Đừng cấu hình converter để bù cho deserializer sai kiểu. Hai tầng phải tương thích với payload producer gửi.

## 11. Nhiều factory cho nhiều nhu cầu listener

Một ứng dụng có thể khai báo nhiều container factory. Ví dụ:

| Factory | Kiểu listener | Concurrency | AckMode | Error policy |
|---|---|---:|---|---|
| ordersRecordListenerContainerFactory | Record | 3 | RECORD | Retry chuẩn |
| ordersBatchListenerContainerFactory | Batch | 2 | BATCH | Retry theo batch |
| paymentsListenerContainerFactory | Record | 1 | MANUAL | Retry và DLT riêng |

Mỗi factory có thể dùng cùng hoặc khác ConsumerFactory tùy kiểu dữ liệu và cấu hình consumer.

Ví dụ hai listener chọn factory khác nhau:

~~~java
@KafkaListener(
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "ordersRecordListenerContainerFactory"
)
public void handleOrder(OrderCreated event) {
    // Xử lý từng order.
}

@KafkaListener(
    topics = "commerce.payment.captured",
    groupId = "reconciliation-service",
    containerFactory = "paymentsListenerContainerFactory"
)
public void handlePayment(PaymentCaptured event) {
    // Đối soát thanh toán.
}
~~~

Cách chia factory nên dựa trên khác biệt thật sự về deserializer, concurrency, batch, acknowledgment, transaction hoặc error handling. Không cần tạo factory mới cho mỗi listener nếu chúng có cùng chính sách và cấu hình.

## 12. Cấu hình container properties

Ngoài các thiết lập ở factory, có thể truy cập `ContainerProperties` để cấu hình hành vi của container.

Ví dụ:

~~~java
factory.getContainerProperties()
    .setAckMode(ContainerProperties.AckMode.RECORD);

factory.getContainerProperties()
    .setPollTimeout(3_000L);
~~~

Một số thuộc tính thường quan tâm:

| Thuộc tính | Mục đích |
|---|---|
| AckMode | Cách container xác nhận và commit offset |
| pollTimeout | Thời gian chờ cho một lần poll theo cấu hình container |
| syncCommits | Chọn commit đồng bộ hay bất đồng bộ trong các trường hợp container quản lý commit |
| ackCount | Số record làm điều kiện commit với AckMode.COUNT/COUNT_TIME |
| ackTime | Khoảng thời gian làm điều kiện commit với AckMode.TIME/COUNT_TIME |
| missingTopicsFatal | Quyết định ứng xử khi topic được khai báo không tồn tại, theo cấu hình và phiên bản |
| idleEventInterval | Khoảng thời gian phát idle event khi consumer không nhận dữ liệu |

Tên API và khả năng sử dụng có thể khác theo phiên bản Spring Kafka. Hãy kiểm tra Javadoc của phiên bản dependency trong dự án trước khi áp dụng thuộc tính mới hoặc API đã deprecated.

Không nên đưa toàn bộ cấu hình consumer client vào ContainerProperties. Các thuộc tính như `max.poll.interval.ms`, `max.poll.records`, deserializer và group ID thuộc cấu hình Kafka consumer; container properties điều khiển cách Spring quản lý listener container.

## 13. Quản lý vòng đời container qua registry

Các container được tạo từ `@KafkaListener` được Spring quản lý thông qua `KafkaListenerEndpointRegistry`.

Có thể gán ID cho listener:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "commerce.order.created",
    groupId = "billing-service",
    containerFactory = "ordersKafkaListenerContainerFactory"
)
public void handle(OrderCreated event) {
    // Xử lý event.
}
~~~

Sau đó truy cập container bằng registry:

~~~java
@Service
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControlService(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.stop();
        }
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.start();
        }
    }
}
~~~

Registry giúp ứng dụng điều khiển listener endpoint theo ID. Container cũng hỗ trợ pause/resume trong các tình huống cần tạm dừng tiêu thụ hoặc kiểm soát tải.

Phân biệt:

- `id` của @KafkaListener là định danh endpoint trong Spring.
- `groupId` là định danh consumer group trên Kafka.
- `clientIdPrefix` là tiền tố client ID cho Kafka consumer.

Ba giá trị có mục đích khác nhau và không nên dùng thay thế cho nhau.

## 14. Tích hợp transaction với listener container

Khi listener cần xử lý Kafka transaction, factory/container phải được cấu hình với transaction manager và producer factory hỗ trợ transaction.

Với Spring Kafka, transaction thường được thiết lập ở producer factory thông qua transaction ID prefix; container sử dụng Kafka-aware transaction manager phù hợp với phiên bản Spring Kafka.

Luồng xử lý transactional listener có thể gồm:

1. Container bắt đầu Kafka transaction.
2. Consumer nhận record và gọi listener.
3. Listener xử lý nghiệp vụ và có thể gửi record đầu ra bằng KafkaTemplate tham gia transaction.
4. Offset consumer được gửi vào transaction.
5. Transaction commit hoặc abort.

Transaction có thể giúp bảo đảm output record và offset được commit nguyên tử trong phạm vi Kafka transaction. Nó không tự tạo transaction nguyên tử giữa Kafka và database bên ngoài.

Khi cấu hình transaction, cần kiểm tra:

- ProducerFactory có transaction ID prefix phù hợp.
- Transaction ID duy nhất giữa các producer đang hoạt động.
- KafkaTemplate dùng đúng transactional producer factory.
- Container sử dụng transaction manager tương ứng.
- Listener xử lý exception theo chính sách rollback/retry phù hợp.
- Consumer downstream dùng isolation level phù hợp nếu cần chỉ đọc committed transaction.

API cấu hình transaction manager đã thay đổi giữa các thế hệ Spring Kafka. Hãy dùng đúng API của phiên bản dự án, tránh sao chép ví dụ cũ có phương thức deprecated.

## 15. Spring Boot và cấu hình application.yml

Có thể đặt các thuộc tính Kafka client trong application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.events.OrderCreated
        spring.json.trusted.packages: com.example.events
~~~

Sau đó tạo factory dùng ConsumerFactory đã được Spring Boot cấu hình hoặc tự khai báo ConsumerFactory riêng nếu cần kiểm soát sâu hơn.

Ví dụ bean factory có thể nhận ConsumerFactory từ context:

~~~java
@Bean(name = "ordersKafkaListenerContainerFactory")
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

Khi ứng dụng có nhiều kiểu value khác nhau, cần bảo đảm ConsumerFactory generic và deserializer tương ứng. Không dùng một ConsumerFactory deserialize thành OrderCreated cho listener nhận PaymentCaptured nếu chưa có converter hoặc kiểu envelope phù hợp.

## 16. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy container factory | Sai tên bean trong containerFactory hoặc bean chưa được đăng ký | Kiểm tra tên bean và annotation |
| Listener không khởi động | ConsumerFactory thiếu hoặc cấu hình consumer không hợp lệ | Kiểm tra factory wiring và log khởi động |
| ClassCastException ở listener | Generic type, deserializer hoặc listener method không khớp | Kiểm tra key/value type và converter |
| Tăng concurrency nhưng throughput không tăng | Số partition ít hoặc downstream là nút thắt | Kiểm tra assignment, lag và processing time |
| Batch listener nhận sai kiểu | Chưa bật setBatchListener hoặc method signature không tương thích | Kiểm tra factory và tham số listener |
| Offset commit không như mong muốn | AckMode hoặc auto commit không phù hợp | Kiểm tra ContainerProperties và enable.auto.commit |
| Retry không áp dụng | Error handler chưa được gắn vào factory được listener sử dụng | Kiểm tra containerFactory và common error handler |
| DLT publish thất bại | Producer template, serializer hoặc partition DLT không phù hợp | Kiểm tra DLT, serializer và số partition |
| Sửa factory nhưng container đang chạy không đổi | Container đã được tạo từ cấu hình trước đó | Dừng/tạo lại container theo quy trình phù hợp |
| Listener endpoint bị start/stop ngoài ý muốn | autoStartup hoặc lifecycle registry chưa được kiểm soát | Kiểm tra endpoint ID và registry |

## 17. Kiểm thử ConcurrentKafkaListenerContainerFactory

Kiểm thử tích hợp nên xác nhận factory tạo container đúng cấu hình và listener thực sự xử lý được record.

Các bước cơ bản:

1. Khởi tạo broker thử nghiệm bằng EmbeddedKafka hoặc Testcontainers.
2. Khai báo ConsumerFactory và ConcurrentKafkaListenerContainerFactory trong Spring context.
3. Tạo listener có ID rõ ràng và chỉ định containerFactory.
4. Gửi record tới topic.
5. Xác nhận listener nhận đúng payload.
6. Kiểm tra container được đăng ký trong KafkaListenerEndpointRegistry.
7. Kiểm tra concurrency hoặc batch behavior khi cần.
8. Kiểm tra acknowledgment, error handler và retry ở các test riêng.

Ví dụ kiểm tra container được đăng ký:

~~~java
@SpringBootTest
@EmbeddedKafka(
    partitions = 3,
    topics = "commerce.order.created"
)
class OrderListenerContainerTest {

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @Test
    void shouldRegisterOrdersListenerContainer() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        assertThat(container).isNotNull();
        assertThat(container.isRunning()).isTrue();
    }
}
~~~

Để xác nhận concurrency cụ thể, có thể kiểm tra container được tạo là `ConcurrentMessageListenerContainer` và đọc cấu hình concurrency của nó theo API phiên bản đang dùng.

Để kiểm thử batch listener, gửi nhiều record tới partition và xác nhận listener nhận collection. Không giả định batch luôn có kích thước cố định vì số record phụ thuộc poll và dữ liệu sẵn có.

Khi kiểm thử retry và DLT, cần xác nhận số lần gọi listener, record được publish tới DLT và offset được xử lý theo chính sách mong đợi. Không chỉ kiểm tra log exception.

## 18. Checklist trước khi đưa factory vào vận hành

- [ ] Factory được đăng ký thành bean với tên rõ ràng?
- [ ] @KafkaListener tham chiếu đúng containerFactory?
- [ ] ConsumerFactory có key/value generic và deserializer phù hợp?
- [ ] Concurrency phù hợp với số partition và số instance?
- [ ] Listener record hay batch được chọn đúng?
- [ ] AckMode phù hợp với kiểu listener và yêu cầu commit?
- [ ] enable.auto.commit được cấu hình phù hợp với container?
- [ ] Error handler và retry policy được gắn vào đúng factory?
- [ ] DLT có serializer, partition và retention phù hợp?
- [ ] Converter và deserializer được phân biệt đúng trách nhiệm?
- [ ] Factory riêng được tạo khi listener có chính sách khác biệt?
- [ ] Listener ID và group ID được quản lý riêng?
- [ ] Lifecycle được điều khiển qua registry khi cần?
- [ ] Transaction manager và producer factory tương thích nếu dùng transaction?
- [ ] Có kiểm thử endpoint, concurrency, batch, lỗi và offset?

## Kết luận

`ConcurrentKafkaListenerContainerFactory` là thành phần cấu hình và tạo concurrent listener container cho các endpoint `@KafkaListener`. Factory kết nối ConsumerFactory với các thiết lập như concurrency, record/batch mode, acknowledgment, error handling và message conversion. Container được tạo ra mới chịu trách nhiệm quản lý consumer, poll record và gọi listener.

Một ứng dụng có thể dùng một factory chung cho các listener có cùng yêu cầu hoặc khai báo nhiều factory cho các nhóm listener có deserializer, concurrency, batch, transaction hay error policy khác nhau. Chọn factory có chủ đích, giữ cấu hình consumer nhất quán, theo dõi partition assignment và kiểm thử vòng đời container sẽ giúp hệ thống Spring Kafka dễ mở rộng và vận hành ổn định.
