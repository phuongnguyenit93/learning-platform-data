# Container factory dùng chung và cô lập cấu hình

Trong Spring Kafka, `KafkaListenerContainerFactory` là nơi định nghĩa cách listener container được tạo và vận hành. Một factory có thể được dùng chung cho nhiều phương thức `@KafkaListener` khi chúng có cùng chính sách xử lý. Khi một listener cần batch mode, acknowledgment mode, concurrency hoặc error handling khác, ứng dụng có thể tạo một factory chuyên biệt để cô lập cấu hình.

Điểm cần phân biệt là **container factory không phải Kafka consumer đang chạy**. Factory là đối tượng cấu hình và tạo container. Mỗi endpoint `@KafkaListener` được Spring đăng ký sẽ có listener container riêng; container đó tạo và quản lý Kafka consumer riêng theo số lượng concurrency. Nhiều listener có thể dùng chung một factory mà không chia sẻ cùng một đối tượng `KafkaConsumer`.

## 1. Ba thành phần cần phân biệt

Một cấu hình listener thường có ba lớp:

1. `ConsumerFactory`: tạo Kafka consumer và cung cấp các thuộc tính cấp Kafka client như deserializer, security, `max.poll.records`, `auto.offset.reset` và `isolation.level`.
2. `ConcurrentKafkaListenerContainerFactory`: định nghĩa cách Spring tạo listener container, ví dụ concurrency, acknowledgment mode, record/batch listener, error handler và các container properties.
3. Listener container: thành phần thực thi một endpoint `@KafkaListener`, gọi `poll()`, chuyển record tới listener method, phối hợp retry và commit offset.

```text
Spring application context
       |
       +------------------------------+
       |                              |
       v                              v
ConsumerFactory                 Container factory
       |                              |
       | tạo KafkaConsumer            | tạo listener container
       |                              |
       +---------------+--------------+
                       |
                       v
              Listener container
                       |
                       v
                Kafka consumer
                       |
                       v
                 @KafkaListener
```

Trong thực tế, container factory nhận một `ConsumerFactory` để tạo consumer. Một container có thể quản lý một consumer hoặc nhiều consumer thread tùy cấu hình concurrency. Khi nhiều endpoint dùng cùng factory, Spring tạo container riêng cho từng endpoint và mỗi container quản lý consumer riêng.

## 2. Khi nào nên dùng chung container factory?

Nên dùng một factory chung khi các listener có cùng yêu cầu vận hành, chẳng hạn:

- Cùng kiểu record listener hoặc cùng batch listener mode.
- Cùng acknowledgment mode và chính sách commit offset.
- Cùng retry/backoff và error handler.
- Cùng concurrency mặc định và các container properties.
- Cùng chính sách transaction nếu sử dụng Kafka transaction.

Ví dụ, các listener xử lý `orders`, `payments` và `shipments` đều nhận từng record, xử lý nghiệp vụ đồng bộ, commit theo record và dùng cùng error handler. Một factory mặc định có thể tạo container cho cả ba listener.

Spring Boot thường tự cấu hình một factory mặc định có tên `kafkaListenerContainerFactory` nếu ứng dụng có cấu hình Kafka phù hợp và chưa khai báo factory tương ứng. Listener có thể dùng factory mặc định mà không cần ghi thuộc tính `containerFactory`:

```java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrder(OrderCreated event) {
    billingService.process(event);
}

@KafkaListener(topics = "payments", groupId = "payment-service")
public void onPayment(PaymentRequested event) {
    paymentService.process(event);
}
```

Hai listener có group ID riêng nên có tiến độ đọc riêng. Chúng vẫn có thể dùng cùng container factory nếu các chính sách container phù hợp. `group.id` có thể được đặt ở endpoint hoặc cấu hình consumer; việc dùng chung factory không có nghĩa hai listener phải dùng chung consumer group.

## 3. Cấu hình factory mặc định trong Spring Boot

Nếu cần tùy chỉnh factory mặc định nhưng vẫn muốn giữ các thiết lập do Spring Boot áp dụng, có thể dùng `ConcurrentKafkaListenerContainerFactoryConfigurer`. Configurer áp dụng cấu hình từ `spring.kafka.*` vào factory và consumer factory được truyền vào.

```java
@Configuration
@EnableKafka
public class KafkaListenerConfiguration {

    @Bean(name = "kafkaListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<Object, Object>
    kafkaListenerContainerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<Object, Object> kafkaConsumerFactory) {

        ConcurrentKafkaListenerContainerFactory<Object, Object> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        configurer.configure(factory, kafkaConsumerFactory);
        return factory;
    }
}
```

Factory trên giữ cấu hình chung do Spring Boot cung cấp. Các thuộc tính cơ bản có thể đặt trong `application.properties`:

```properties
spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.consumer.group-id=default-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events

spring.kafka.listener.ack-mode=record
spring.kafka.listener.concurrency=2
```

Các giá trị trên là ví dụ cho một môi trường phát triển. Với production, bootstrap servers, security, trusted packages, group ID và offset reset cần được chọn theo môi trường và luồng nghiệp vụ. Không mở rộng trusted packages quá mức cần thiết khi dùng JSON deserialization.

Nếu ứng dụng không cần tùy chỉnh factory, có thể để Spring Boot tạo factory mặc định. Khi khai báo bean cùng tên `kafkaListenerContainerFactory`, ứng dụng đang chủ động cung cấp factory thay cho bean auto-configured; vì vậy nên dùng configurer hoặc cấu hình đầy đủ các thuộc tính cần thiết để không vô tình bỏ sót thiết lập Boot.

## 4. Tạo factory chuyên biệt cho listener cần chính sách khác

Khi một nhóm listener cần chính sách riêng, hãy tạo thêm một bean `ConcurrentKafkaListenerContainerFactory` với tên rõ ràng. Ví dụ, listener audit xử lý từng record, dùng concurrency cao hơn và error handler riêng:

```java
@Bean(name = "auditKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<Object, Object>
auditKafkaListenerContainerFactory(
        ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
        ConsumerFactory<Object, Object> kafkaConsumerFactory,
        DefaultErrorHandler auditErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<Object, Object> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    // Kế thừa cấu hình Kafka chung từ Spring Boot.
    configurer.configure(factory, kafkaConsumerFactory);

    // Chỉ ghi đè các chính sách riêng của nhóm audit.
    factory.setConcurrency(4);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);
    factory.setCommonErrorHandler(auditErrorHandler);

    return factory;
}
```

Listener chọn factory này bằng tên bean:

```java
@KafkaListener(
        topics = "audit-events",
        groupId = "audit-archive",
        containerFactory = "auditKafkaListenerContainerFactory")
public void archive(AuditEvent event) {
    auditArchive.store(event);
}
```

Listener khác vẫn dùng factory mặc định:

```java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        containerFactory = "kafkaListenerContainerFactory")
public void bill(OrderCreated event) {
    billingService.process(event);
}
```

`containerFactory` trỏ tới tên bean trong Spring context. Tên phải khớp chính xác. Nếu chỉ có một factory mặc định, thuộc tính này thường có thể bỏ qua; khi có nhiều factory, khai báo rõ ràng giúp người đọc thấy listener dùng chính sách nào và tránh chọn nhầm factory.

Trong ví dụ, hai factory dùng chung `ConsumerFactory` vì cùng cấu hình kết nối và deserializer. Chúng chỉ khác concurrency, acknowledgment mode và error handler ở cấp container. Đây là cách cô lập phù hợp khi khác biệt nằm ở cách container vận hành.

## 5. Khi nào cần tách cả ConsumerFactory?

Không phải mọi khác biệt đều thuộc container factory. Một số thuộc tính là cấu hình của Kafka consumer client. Nếu hai nhóm listener cần các thiết lập client khác nhau, có thể cần các `ConsumerFactory` riêng và gắn từng factory vào container factory tương ứng.

| Cấu hình | Thuộc thành phần | Ví dụ lý do cần tách |
|---|---|---|
| Key/value deserializer | `ConsumerFactory` | Một topic dùng JSON, topic khác dùng Avro hoặc byte array |
| `auto.offset.reset` | `ConsumerFactory` | Một group mới cần `earliest`, luồng khác cần `latest` |
| `max.poll.records` | `ConsumerFactory` | Batch xử lý lớn cần giới hạn poll riêng |
| `max.poll.interval.ms` | `ConsumerFactory` | Một loại công việc có thời gian xử lý dài hơn |
| `isolation.level` | `ConsumerFactory` | Luồng cần chỉ đọc dữ liệu transaction đã commit |
| Security, client ID và network settings | `ConsumerFactory` | Nhóm listener kết nối cluster hoặc danh tính bảo mật khác |
| Concurrency | Container factory/container | Nhóm listener cần số consumer thread khác nhau |
| Ack mode | Container factory/container | Nhóm listener có yêu cầu commit offset khác nhau |
| Batch listener mode | Container factory | Một listener nhận từng record, listener khác nhận cả batch |
| Common error handler | Container factory/container | Retry, backoff và recovery khác nhau |

Ví dụ một factory riêng cho luồng archive cần đọc dữ liệu cũ, poll ít record và dùng deserializer riêng:

```java
@Bean
ConsumerFactory<String, AuditEvent> auditConsumerFactory(
        @Value("${app.kafka.archive.bootstrap-servers}") String bootstrapServers) {

    Map<String, Object> props = new HashMap<>();
    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "audit-archive");
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 50);
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            JsonDeserializer.class);
    props.put(JsonDeserializer.TRUSTED_PACKAGES, "com.example.audit");

    return new DefaultKafkaConsumerFactory<>(props);
}
```

Gắn consumer factory riêng vào container factory:

```java
@Bean(name = "archiveKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
archiveKafkaListenerContainerFactory(
        ConsumerFactory<String, AuditEvent> auditConsumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, AuditEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(auditConsumerFactory);
    factory.setConcurrency(2);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}
```

Đây là cấu hình minh họa. Trong ứng dụng thực tế, cần thêm các thiết lập bảo mật, schema/deserializer, trust configuration và bootstrap server phù hợp. Nếu muốn kế thừa cấu hình Spring Boot cho consumer factory riêng, có thể xây dựng factory từ `KafkaProperties` hoặc cấu hình tập trung của ứng dụng; tránh sao chép thiếu các thiết lập quan trọng như TLS/SASL, metrics, client ID và interceptors.

Một `ConsumerFactory` có thể được dùng chung để tạo nhiều Kafka consumer vì factory quản lý việc tạo client, không phải một consumer đang đọc dữ liệu. Nếu khác biệt chỉ là `group.id` của từng endpoint, `@KafkaListener(groupId = "...")` thường đủ; không cần tạo một `ConsumerFactory` mới chỉ để đổi group ID.

## 6. Cô lập batch listener và record listener

Một khác biệt quan trọng ở cấp container là listener nhận từng record hay nhận cả batch từ một lần poll.

Record listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "billing-service",
        containerFactory = "kafkaListenerContainerFactory")
public void handle(OrderCreated event) {
    billingService.process(event);
}
```

Batch listener:

```java
@KafkaListener(
        topics = "audit-events",
        groupId = "audit-archive",
        containerFactory = "auditBatchKafkaListenerContainerFactory")
public void handleBatch(List<ConsumerRecord<String, AuditEvent>> records) {
    auditArchive.storeBatch(records);
}
```

Factory cho batch listener phải bật batch mode:

```java
@Bean(name = "auditBatchKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
auditBatchKafkaListenerContainerFactory(
        ConsumerFactory<String, AuditEvent> auditConsumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, AuditEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(auditConsumerFactory);
    factory.setBatchListener(true);
    factory.setConcurrency(2);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.BATCH);

    return factory;
}
```

Không nên dùng cùng một factory cho record listener và batch listener nếu cấu hình `batchListener` khiến adapter gọi listener với hình dạng tham số khác nhau. Tạo factory riêng giúp kiểu listener và chính sách commit dễ hiểu hơn. Batch listener cũng cần thiết kế rõ cách xử lý khi một record trong batch lỗi: retry cả batch, xử lý một phần hay chuyển record lỗi sang DLT. Không được mặc định rằng batch listener có cùng semantics với record listener.

## 7. Cô lập error handler và recovery policy

Các luồng nghiệp vụ có thể cần retry policy khác nhau. Ví dụ, lỗi tạm thời khi ghi đơn hàng có thể retry với backoff ngắn; lỗi từ hệ thống archive có thể dùng backoff dài hơn; lỗi dữ liệu không hợp lệ cần chuyển DLT sớm.

Có thể tạo error handler riêng cho từng factory:

```java
@Bean
DefaultErrorHandler billingErrorHandler(
        DeadLetterPublishingRecoverer billingRecoverer) {
    return new DefaultErrorHandler(
            billingRecoverer,
            new FixedBackOff(500L, 3L));
}

@Bean
DefaultErrorHandler archiveErrorHandler(
        DeadLetterPublishingRecoverer archiveRecoverer) {
    return new DefaultErrorHandler(
            archiveRecoverer,
            new FixedBackOff(5_000L, 5L));
}
```

Gắn đúng handler vào đúng container factory. Không dùng một handler chung nếu nó cần state hoặc retry/recovery policy khác nhau theo luồng. Khi chia sẻ một handler, cần chắc chắn handler và recoverer được thiết kế an toàn khi nhiều container gọi đồng thời.

Error handler không thay thế việc phân loại exception. Nên cấu hình exception không retry cho các lỗi dữ liệu không thể khắc phục bằng cách thử lại, đồng thời giới hạn retry cho lỗi tạm thời. Nếu dùng DLT, cần đảm bảo publish result được kiểm tra, DLT có đủ partition và có quy trình replay.

## 8. Factory và concurrency

`setConcurrency(n)` xác định số consumer thread mà mỗi listener container có thể sử dụng. Với `ConcurrentMessageListenerContainer`, Spring tạo các child container để quản lý consumer riêng. Số consumer hoạt động thực tế còn phụ thuộc partition assignment và group membership.

Ví dụ một topic có sáu partition và hai endpoint cùng dùng factory concurrency 3. Mỗi endpoint có container riêng, mỗi container có thể tạo ba consumer. Nếu hai endpoint tham gia hai group khác nhau, tổng số consumer client có thể là sáu và mỗi group tự phân phối sáu partition của topic. Nếu hai endpoint cùng group, chúng là các member trong cùng group và chia nhau partition theo assignment của group đó.

Khi tăng concurrency, cần kiểm tra:

- Số partition có thể gán cho group.
- CPU, memory và số thread của ứng dụng.
- Số kết nối và tải trên broker.
- Connection pool, throughput và giới hạn của database hoặc API downstream.
- Thời gian xử lý record/batch và `max.poll.interval.ms`.
- Số lần rebalance khi rolling deployment hoặc autoscaling.

Concurrency cao hơn không tự động tạo throughput cao hơn. Nếu downstream đã bão hòa, thêm consumer có thể làm tăng contention và retry. Hãy đo processing rate và độ trễ trước khi thay đổi.

## 9. Quản lý tên bean và nhiều factory

Khi ứng dụng có nhiều container factory, đặt tên theo mục đích thay vì tên chung chung như `factory1`, `factory2`. Ví dụ:

| Bean name | Mục đích |
|---|---|
| `kafkaListenerContainerFactory` | Factory mặc định cho record listener thông thường |
| `auditKafkaListenerContainerFactory` | Listener audit với retry và concurrency riêng |
| `auditBatchKafkaListenerContainerFactory` | Batch listener cho archive |
| `transactionalKafkaListenerContainerFactory` | Listener sử dụng Kafka transaction |

Mỗi `@KafkaListener` nên chỉ rõ `containerFactory` khi cần dùng factory chuyên biệt. Nếu một bean phụ thuộc vào nhiều `ConsumerFactory` cùng kiểu generic, dùng `@Qualifier` để Spring inject đúng bean. Chỉ dùng `@Primary` khi có một factory mặc định thực sự phù hợp cho phần lớn ứng dụng; không dựa vào thứ tự khai báo bean để chọn factory.

Ví dụ dùng qualifier:

```java
@Bean(name = "archiveKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
archiveFactory(
        @Qualifier("auditConsumerFactory")
        ConsumerFactory<String, AuditEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, AuditEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();
    factory.setConsumerFactory(consumerFactory);
    return factory;
}
```

Đặt tên bean và tham chiếu nhất quán giúp giảm lỗi runtime như không tìm thấy container factory, inject nhầm consumer factory hoặc listener chạy với cấu hình mặc định ngoài dự kiến.

## 10. Những cấu hình không nên vô tình chia sẻ

Chia sẻ factory giúp tránh lặp cấu hình, nhưng chỉ nên chia sẻ những chính sách thực sự giống nhau. Một số khác biệt cần được tách có chủ đích:

| Khác biệt | Hướng thiết kế |
|---|---|
| Một listener xử lý record, listener khác xử lý batch | Tạo container factory riêng với `setBatchListener` tương ứng |
| Một luồng cần `RECORD`, luồng khác cần `MANUAL_IMMEDIATE` | Tách container factory để acknowledgment mode không ảnh hưởng chéo |
| Retry/backoff và DLT khác nhau | Dùng error handler/recoverer riêng và gắn vào factory phù hợp |
| Consumer dùng deserializer hoặc schema khác | Tách `ConsumerFactory` và container factory tương ứng |
| `isolation.level`, `max.poll.records` hoặc `max.poll.interval.ms` khác nhau | Tách cấu hình Kafka client ở `ConsumerFactory` |
| Kết nối tới cluster hoặc security principal khác | Tách `ConsumerFactory` với cấu hình kết nối và bảo mật riêng |
| Transactional và non-transactional listener | Tách factory, transaction manager và producer/consumer configuration theo mô hình giao dịch |

Không thay đổi thuộc tính trên một factory dùng chung sau khi các listener container đã khởi tạo rồi kỳ vọng mọi container đang chạy tự cập nhật đồng bộ. Cấu hình factory nên được hoàn tất trước khi endpoint được khởi động. Thay đổi runtime cần dùng cơ chế quản lý container có kiểm soát và xác minh hành vi của phiên bản Spring Kafka.

## 11. Quan sát factory và listener container

Khi một listener chạy sai chính sách, hãy quan sát từ endpoint về factory và consumer factory:

1. Xác nhận tên `containerFactory` trên `@KafkaListener`.
2. Xác nhận bean factory thực tế được Spring đăng ký dưới tên đó.
3. Xác nhận factory được gắn đúng `ConsumerFactory`.
4. Kiểm tra `batchListener`, concurrency, acknowledgment mode, error handler và transaction configuration.
5. Kiểm tra group ID, topic subscription, deserializer và các Kafka consumer properties.
6. Đối chiếu log container startup, partition assignment, rebalance và committed offset.

Metric cần theo dõi gồm số consumer theo group, số partition được gán, consumer lag, rebalance count, poll latency, processing latency, commit failure, retry rate và DLT publish rate. Gắn tag có giới hạn như application, listener ID, group ID và topic; tránh dùng event ID làm metric label.

Một factory dùng chung có thể tạo nhiều container, nên log nên nhận diện được listener ID hoặc container ID. Nếu chỉ log group ID mà nhiều listener dùng chung group, việc xác định container gây lỗi sẽ khó hơn. Có thể đặt `id` rõ ràng trong `@KafkaListener` để tăng khả năng truy vết.

## 12. Lỗi thường gặp khi cấu hình nhiều factory

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `NoSuchBeanDefinitionException` cho container factory | Tên trong `containerFactory` không khớp bean name | Kiểm tra tên `@Bean` và annotation |
| Listener dùng sai concurrency | Listener đang dùng factory mặc định hoặc factory khác | Khai báo rõ `containerFactory`, kiểm tra `setConcurrency` |
| Batch listener nhận sai kiểu tham số | Factory chưa bật batch mode hoặc listener được gắn nhầm factory | Tạo factory batch riêng và kiểm tra method signature |
| Hai luồng dùng nhầm group | Group ID mặc định dùng chung ngoài ý muốn | Đặt `groupId` rõ ràng ở từng listener |
| Deserialization exception ở một topic | ConsumerFactory dùng deserializer không phù hợp | Tạo ConsumerFactory riêng hoặc cấu hình deserializer hỗ trợ các kiểu cần thiết |
| Error handler áp dụng sai listener | Nhiều factory cùng dùng handler không phù hợp | Tách handler/recoverer và gắn đúng factory |
| Spring không biết chọn ConsumerFactory nào | Có nhiều bean cùng kiểu và không có qualifier | Dùng `@Qualifier` hoặc xác định bean `@Primary` hợp lý |
| Tăng concurrency nhưng lag không giảm | Partition không đủ hoặc downstream đã bão hòa | Kiểm tra partition assignment và năng lực downstream trước khi tăng tiếp |

Khi thêm factory mới, hãy kiểm tra tất cả listener có liên quan và cấu hình bean dependency. Một factory riêng không có tác dụng nếu listener vẫn trỏ tới tên factory mặc định.

## 13. Quy trình triển khai cấu hình mới

Khi tách một nhóm listener khỏi factory dùng chung, nên thực hiện theo các bước:

1. Xác định chính xác điểm khác biệt: container behavior hay Kafka consumer client properties.
2. Nếu khác biệt chỉ nằm ở concurrency, ack mode, batch mode hoặc error handler, tạo container factory mới và có thể dùng lại ConsumerFactory.
3. Nếu khác biệt nằm ở deserializer, security, isolation level hoặc consumer poll settings, tạo ConsumerFactory riêng.
4. Đặt tên bean theo chức năng và dùng `@Qualifier` khi cần inject nhiều factory cùng kiểu.
5. Chỉ định `containerFactory` trên từng listener cần cấu hình chuyên biệt.
6. Kiểm thử record/batch signature, commit offset, retry, DLT, rebalance và startup/shutdown.
7. Triển khai từng bước, quan sát lag, throughput, poll interval và lỗi consumer.
8. Giữ cấu hình rollback để listener có thể quay về factory trước nếu thay đổi gây ảnh hưởng.

Việc tách factory nên phản ánh một yêu cầu vận hành có thật. Không cần tạo factory riêng cho mọi listener nếu chúng có cùng chính sách; quá nhiều factory trùng lặp sẽ làm cấu hình khó theo dõi và tăng nguy cơ lệch thiết lập.

## 14. Nguyên tắc thiết kế production

Một cấu trúc container factory dễ vận hành thường tuân theo các nguyên tắc:

1. Dùng `kafkaListenerContainerFactory` làm factory mặc định cho các listener có chính sách chung.
2. Tạo factory chuyên biệt khi có khác biệt rõ về batch, ack mode, concurrency, error handling hoặc transaction.
3. Chia sẻ `ConsumerFactory` khi các Kafka client properties tương thích; tách khi deserializer, security, cluster hoặc poll behavior khác nhau.
4. Nhớ rằng mỗi listener endpoint có container riêng; dùng chung factory không có nghĩa dùng chung Kafka consumer.
5. Đặt tên bean rõ ràng và tham chiếu chính xác bằng `containerFactory`.
6. Dùng `@Qualifier` khi có nhiều bean cùng kiểu; tránh dựa vào thứ tự khai báo.
7. Không tăng concurrency vượt số partition có thể gán hoặc năng lực downstream.
8. Kiểm thử commit offset, retry, DLT và rebalance trên đúng factory thực tế.
9. Quan sát từng listener/container riêng để khoanh vùng lỗi.
10. Hoàn tất cấu hình trước khi container khởi động và thay đổi runtime theo quy trình có kiểm soát.

Container factory dùng chung giúp tập trung các chính sách listener giống nhau. Factory chuyên biệt tạo ranh giới rõ ràng cho các luồng có yêu cầu khác nhau. Khi phân chia đúng giữa container factory và ConsumerFactory, ứng dụng Spring Kafka có thể giữ cấu hình nhất quán mà vẫn cô lập được hành vi vận hành của từng nhóm consumer.
