# ListenerContainerFactory làm template cấu hình

Trong Spring Kafka, `@KafkaListener` chỉ mô tả endpoint nhận message: topic nào cần nghe, consumer group nào sử dụng và phương thức nào xử lý record. Để endpoint thực sự hoạt động, Spring cần tạo một listener container. Container quản lý `KafkaConsumer`, vòng lặp `poll()`, chuyển record tới listener, xác nhận offset, xử lý rebalance và đóng consumer khi ứng dụng dừng.

`KafkaListenerContainerFactory` là thành phần tạo các listener container cho những endpoint được khai báo bằng `@KafkaListener`. Trong ứng dụng dùng concurrency, lớp thường gặp là `ConcurrentKafkaListenerContainerFactory`. Factory đóng vai trò như một template cấu hình: ta đặt `ConsumerFactory`, concurrency, AckMode, poll timeout, error handler và các tùy chọn container một lần; Spring dùng cấu hình đó để tạo container cho từng listener endpoint.

Hiểu factory giúp tránh cấu hình lặp lại trên từng listener, đồng thời cho phép một ứng dụng có nhiều nhóm listener với chính sách khác nhau, ví dụ listener xử lý từng record, listener xử lý batch hoặc listener có retry riêng.

## 1. Factory nằm ở đâu trong vòng đời @KafkaListener?

Các thành phần chính có vai trò khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `ConsumerFactory<K, V>` | Tạo Kafka consumer với bootstrap server, group, deserializer và các consumer properties |
| `KafkaListenerContainerFactory` | Tạo listener container từ cấu hình chung và endpoint metadata |
| `ConcurrentKafkaListenerContainerFactory` | Factory phổ biến hỗ trợ tạo container có một hoặc nhiều consumer |
| `KafkaMessageListenerContainer` | Container quản lý một Kafka consumer và vòng lặp poll |
| `ConcurrentMessageListenerContainer` | Container cha quản lý nhiều child container/consumer khi bật concurrency |
| `@KafkaListener` | Khai báo endpoint, topic, group ID, container factory và phương thức xử lý |

Luồng khởi tạo có thể hình dung như sau:

```text
ApplicationContext khởi động
          |
          v
Spring phát hiện phương thức @KafkaListener
          |
          v
KafkaListenerAnnotationBeanPostProcessor
          |
          v
Chọn KafkaListenerContainerFactory theo containerFactory
          |
          v
Factory kết hợp endpoint + ConsumerFactory + ContainerProperties
          |
          v
Tạo listener container
          |
          v
Container start -> tạo KafkaConsumer -> poll -> gọi listener
```

Factory không phải một Kafka consumer đang chạy. Nó là đối tượng cấu hình và tạo container. Kafka consumer thực tế được tạo khi container khởi động thông qua `ConsumerFactory`. Vì vậy, một factory có thể được dùng làm cấu hình chung cho nhiều endpoint; mỗi endpoint sẽ có container và consumer riêng theo cấu hình concurrency.

## 2. KafkaListenerContainerFactory và ConcurrentKafkaListenerContainerFactory

`KafkaListenerContainerFactory` là interface trừu tượng để Spring Kafka tạo listener container. Trong ứng dụng thông thường, `ConcurrentKafkaListenerContainerFactory<K, V>` là lựa chọn phổ biến vì có thể cấu hình số consumer chạy song song.

Hai kiểu container thường gặp:

- `KafkaMessageListenerContainer`: quản lý một Kafka consumer, phù hợp khi endpoint cần một consumer.
- `ConcurrentMessageListenerContainer`: quản lý một hoặc nhiều child `KafkaMessageListenerContainer`; số child được quyết định bởi concurrency.

Khi concurrency bằng 1, container concurrent vẫn có thể quản lý một child container. Khi concurrency lớn hơn 1, factory tạo container cha với nhiều consumer tham gia cùng group. Mỗi consumer chỉ được gán partition theo quy tắc consumer group; số consumer hữu ích không thể vượt số partition có thể được gán cho group của endpoint đó.

Ví dụ topic có 6 partition và concurrency bằng 3, tối đa ba consumer có thể cùng nhận partition. Nếu concurrency bằng 8, ít nhất hai consumer sẽ không được gán partition nếu chỉ endpoint này subscribe topic có sáu partition và không có topic khác bổ sung partition assignment.

## 3. Tạo factory cơ bản bằng Spring Boot

Spring Boot có thể tự cấu hình `ConsumerFactory` và một `ConcurrentKafkaListenerContainerFactory` mặc định tên `kafkaListenerContainerFactory` khi các điều kiện auto-configuration phù hợp. Nếu cần tùy chỉnh factory mặc định, nên dùng `ConcurrentKafkaListenerContainerFactoryConfigurer` để áp dụng các thuộc tính `spring.kafka.*` trước, sau đó mới thêm các thiết lập riêng.

Ví dụ:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean(name = "kafkaListenerContainerFactory")
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        configurer.configure(factory, consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties().setPollTimeout(1000L);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

`configurer.configure(...)` áp dụng các thiết lập consumer/listener factory do Spring Boot quản lý, bao gồm những cấu hình liên quan trong `application.yml`. Sau đó, `setConcurrency(3)` và `setPollTimeout(1000L)` ghi đè hoặc bổ sung chính sách riêng cho factory này.

Nếu tự tạo factory mà không gọi Boot configurer, hãy chủ động cung cấp đầy đủ `ConsumerFactory` và các thuộc tính container cần thiết. Nếu không, ứng dụng có thể bỏ sót những thiết lập đã khai báo trong `spring.kafka.listener` hoặc các cấu hình auto-configuration mà nhóm đang kỳ vọng.

Ví dụ cấu hình nền trong `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-worker
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    listener:
      ack-mode: record
      poll-timeout: 1s
```

Các property và kiểu biểu diễn thời lượng phụ thuộc phiên bản Spring Boot. Hãy đối chiếu cấu hình với phiên bản Boot/Spring Kafka đang dùng; nếu đặt cùng một thuộc tính ở YAML và Java, giá trị được cấu hình sau cùng trong quá trình tạo factory có thể ghi đè giá trị trước đó.

## 4. Tạo factory không dùng Boot configurer

Trong ứng dụng Spring Framework thuần hoặc khi muốn tự kiểm soát cấu hình, có thể tạo factory trực tiếp từ `ConsumerFactory`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties().setPollTimeout(1000L);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
```

Factory nhận một `ConsumerFactory<String, OrderCreated>` có key/value deserializer tương thích với dữ liệu topic. Consumer properties như `bootstrap.servers`, `group.id`, `max.poll.records` và `max.poll.interval.ms` thuộc cấu hình Kafka consumer; các thuộc tính như `pollTimeout`, `ackMode` và `shutdownTimeout` thuộc `ContainerProperties` của Spring Kafka.

Không nhầm `ConsumerFactory` với `KafkaListenerContainerFactory`: cái đầu tạo Kafka consumer; cái sau tạo listener container và kết nối container với consumer factory cùng endpoint listener.

## 5. Gắn factory vào @KafkaListener

Nếu ứng dụng có một factory mặc định tên `kafkaListenerContainerFactory`, `@KafkaListener` có thể sử dụng factory đó mà không cần khai báo `containerFactory`:

```java
@KafkaListener(topics = "orders", groupId = "orders-worker")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

Nếu có nhiều factory, chỉ rõ tên bean cần dùng:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-worker",
        containerFactory = "orderListenerContainerFactory")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

`containerFactory` tham chiếu tên bean Spring, không phải tên class. Nếu tên bean sai hoặc factory không tồn tại, endpoint không thể được tạo đúng và ứng dụng thường báo lỗi khi khởi động context.

`groupId` trong annotation có thể ghi đè group ID mặc định từ consumer factory cho endpoint đó. Nếu không khai báo group ID tại annotation và consumer factory có `group.id`, container sử dụng cấu hình group tương ứng. Hãy chọn một quy ước nhất quán để tránh endpoint vô tình tham gia sai group.

## 6. ContainerProperties: cấu hình vòng lặp poll và commit

Factory cung cấp `getContainerProperties()` để cấu hình các hành vi của container. Một số thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `pollTimeout` | Thời gian một lần poll chờ dữ liệu |
| `ackMode` | Quy tắc container xác nhận offset sau khi listener xử lý |
| `shutdownTimeout` | Thời gian container chờ khi đóng consumer |
| `idleEventInterval` | Khoảng thời gian dùng để phát sự kiện listener idle khi phù hợp |
| `ackCount` | Ngưỡng số record cho AckMode `COUNT` |
| `ackTime` | Ngưỡng thời gian cho AckMode `TIME` |
| `syncCommits` | Chọn commit đồng bộ hay bất đồng bộ khi container commit |
| `consumerRebalanceListener` | Callback khi partition được revoke/assign |

Ví dụ thiết lập một số thuộc tính:

```java
factory.getContainerProperties().setPollTimeout(1500L);
factory.getContainerProperties()
        .setAckMode(ContainerProperties.AckMode.BATCH);
factory.getContainerProperties().setShutdownTimeout(15_000L);
factory.getContainerProperties().setIdleEventInterval(30_000L);
```

`pollTimeout` không phải `max.poll.interval.ms`. Poll timeout là thời gian chờ trong một lần poll; `max.poll.interval.ms` là giới hạn giữa hai lần gọi poll của consumer. Listener xử lý một batch quá lâu vẫn có thể vượt `max.poll.interval.ms` dù poll timeout chỉ là một giây.

`ackMode` cũng không thay đổi số record trả về mỗi lần poll. Số record chịu ảnh hưởng bởi `max.poll.records` của Kafka consumer và dữ liệu sẵn có. AckMode quy định thời điểm container commit offset sau khi listener xử lý.

## 7. Chọn AckMode phù hợp với listener

Spring Kafka quản lý commit offset theo AckMode. Một số chế độ thường gặp:

| AckMode | Hành vi khái quát | Trường hợp sử dụng |
|---|---|---|
| `RECORD` | Commit sau khi từng record listener xử lý xong | Muốn xác nhận tiến độ theo từng record |
| `BATCH` | Commit sau khi xử lý xong các record trong lần poll | Phù hợp với xử lý theo batch hoặc mặc định thường gặp |
| `TIME` | Commit khi đạt khoảng thời gian cấu hình và có record được xử lý | Gom commit theo thời gian |
| `COUNT` | Commit khi đạt số record cấu hình | Giảm tần suất commit theo lượng dữ liệu |
| `COUNT_TIME` | Kết hợp điều kiện số record và thời gian | Muốn có ngưỡng theo cả lưu lượng và thời gian |
| `MANUAL` | Listener gọi `Acknowledgment.acknowledge()`; container thực hiện commit theo quy tắc manual | Nghiệp vụ chủ động chọn thời điểm xác nhận |
| `MANUAL_IMMEDIATE` | Yêu cầu commit ngay khi acknowledge được gọi trên consumer thread | Cần xác nhận ngay sau một ranh giới nghiệp vụ |

Ví dụ dùng manual acknowledgment:

```java
@KafkaListener(
        topics = "orders",
        groupId = "orders-worker",
        containerFactory = "orderListenerContainerFactory")
public void onOrder(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.handleAndPersist(event);
    acknowledgment.acknowledge();
}
```

Chỉ acknowledge sau khi nghiệp vụ đã hoàn tất hoặc công việc đã được lưu bền vững theo thiết kế. Nếu commit offset trước khi lưu kết quả nghiệp vụ, tiến trình gặp sự cố có thể làm record bị bỏ qua. Nếu xử lý thành công nhưng commit thất bại, record có thể được giao lại; consumer nên idempotent.

Chi tiết thời điểm commit, đặc biệt với acknowledgment từ thread khác, phụ thuộc AckMode và phiên bản Spring Kafka. Không gọi `acknowledge()` tùy tiện từ worker thread nếu chưa cấu hình và hiểu rõ cơ chế out-of-order commit của container.

## 8. Tạo nhiều factory cho nhiều kiểu listener

Một ứng dụng có thể có nhiều loại endpoint với nhu cầu khác nhau. Ví dụ listener xử lý từng record cần AckMode `RECORD`, còn listener batch cần nhận danh sách record và dùng batch mode. Ta có thể khai báo hai factory riêng:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderRecordFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);
        return factory;
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderBatchFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setConcurrency(2);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.BATCH);
        return factory;
    }
}
```

Record listener:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-record-worker",
        containerFactory = "orderRecordFactory")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

Batch listener:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-worker",
        containerFactory = "orderBatchFactory")
public void onOrders(List<OrderCreated> events) {
    orderService.handleBatch(events);
}
```

Hai listener dùng group ID khác nhau nên mỗi group nhận bản sao luồng record độc lập. Nếu dùng cùng group ID, chúng sẽ chia partition cho nhau thay vì mỗi listener đều nhận toàn bộ dữ liệu. Factory batch cần `setBatchListener(true)` để container gọi phương thức với batch theo cấu hình listener tương ứng.

Factory có thể dùng chung `ConsumerFactory` nếu serializer/deserializer và consumer properties phù hợp. Nếu hai nhóm cần isolation level, deserializer, group behavior hoặc security khác nhau, hãy tạo `ConsumerFactory` riêng cho từng nhóm rồi gắn vào factory tương ứng.

## 9. Cấu hình concurrency ở factory và annotation

`setConcurrency(n)` đặt số consumer mặc định cho các container được tạo từ factory đó. Với một listener cụ thể, thuộc tính `concurrency` trên `@KafkaListener` có thể ghi đè giá trị mặc định này:

```java
@KafkaListener(
        id = "paymentsListener",
        topics = "payments",
        groupId = "payments-worker",
        containerFactory = "orderRecordFactory",
        concurrency = "5")
public void onPayment(PaymentReceived event) {
    paymentService.handle(event);
}
```

Concurrency tăng số consumer và khả năng xử lý song song theo partition. Nó không làm một partition được nhiều consumer trong cùng group xử lý đồng thời. Nếu topic chỉ có ba partition, đặt concurrency bằng năm không tạo ra năm luồng tiêu thụ hữu ích cho riêng topic đó.

Khi một factory được dùng cho nhiều listener, mỗi endpoint có thể có concurrency khác nhau. Hãy cấu hình concurrency theo throughput và số partition của từng topic, đồng thời theo dõi consumer lag, CPU, DB connection pool và năng lực downstream. Tăng concurrency quá cao có thể làm downstream quá tải mà không tăng throughput thực tế.

## 10. Cấu hình CommonErrorHandler tại factory

Factory có thể gắn error handler dùng chung cho các container được tạo ra. Trong các phiên bản Spring Kafka hiện đại, `DefaultErrorHandler` là lựa chọn phổ biến để cấu hình retry và xử lý record lỗi.

```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

    var errorHandler = new DefaultErrorHandler(
            new FixedBackOff(1000L, 2L));
    factory.setCommonErrorHandler(errorHandler);

    return factory;
}
```

Ví dụ cấu hình chờ một giây giữa các lần thử lại và tối đa hai lần retry sau lần xử lý ban đầu, theo semantics của `FixedBackOff`. Khi hết retry, hành vi mặc định của error handler có thể log và xử lý offset theo cấu hình; trong production nên cân nhắc recoverer ghi record sang dead-letter topic để không làm mất ngữ cảnh lỗi.

Không phải lỗi nào cũng nên retry. Lỗi tạm thời như timeout dịch vụ có thể retry; lỗi dữ liệu không hợp lệ thường cần chuyển dead-letter hoặc dừng xử lý theo chính sách. Với batch listener, cách xác định record lỗi và commit các record đã xử lý có quy tắc riêng; hãy cấu hình error handler tương thích với listener type.

Tên API error handler thay đổi theo phiên bản Spring Kafka. `CommonErrorHandler`/`DefaultErrorHandler` là hướng hiện đại; các dự án cũ có thể dùng `ErrorHandler` hoặc `SeekToCurrentErrorHandler`. Không trộn ví dụ API của các phiên bản khác nhau trong cùng một cấu hình.

## 11. Filter record trước khi gọi listener

Factory cũng có thể cấu hình `RecordFilterStrategy` để loại bỏ record không cần chuyển tới listener. Ví dụ:

```java
factory.setRecordFilterStrategy(record ->
        record.value() == null || record.value().isBlank());
```

Predicate trả về `true` nghĩa là record bị loại bỏ. Filter phù hợp với điều kiện bỏ qua rõ ràng, ví dụ bỏ heartbeat event hoặc loại message không thuộc phạm vi nghiệp vụ. Không dùng filter để che lỗi deserialize hoặc bỏ qua dữ liệu không hợp lệ mà không có log/metric.

Khi record bị filter, cần hiểu chính sách xác nhận offset. Spring Kafka có tùy chọn liên quan đến acknowledgment của record bị loại; hãy kiểm tra `ackDiscarded` và AckMode của phiên bản đang dùng nếu cần kiểm soát chính xác. Với dữ liệu nghiệp vụ quan trọng, nên ghi nhận số record bị filter để có thể giải thích vì sao listener không xử lý chúng.

## 12. Quản lý vòng đời container

Factory tạo container, còn vòng đời start/stop của container do Spring quản lý. `@KafkaListener` thường được khởi động tự động khi application context sẵn sàng. Có thể điều khiển listener qua `KafkaListenerEndpointRegistry` nếu cần dừng hoặc khởi động một endpoint theo yêu cầu vận hành.

Ví dụ listener có ID:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-worker")
public void onOrder(OrderCreated event) {
    orderService.handle(event);
}
```

Điều khiển container:

```java
@Component
public class ListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        var container = registry.getListenerContainer("ordersListener");
        if (container != null) {
            container.pause();
        }
    }

    public void resumeOrders() {
        var container = registry.getListenerContainer("ordersListener");
        if (container != null) {
            container.resume();
        }
    }
}
```

Container pause/resume không giống stop/start. Pause tạm dừng nhận record từ partition nhưng container tiếp tục poll để duy trì group; stop dừng container và đóng consumer theo lifecycle. Dùng `registry.getListenerContainer(id)` để lấy container được tạo từ annotation. Container khai báo trực tiếp bằng bean `@Bean` có thể được quản lý như bean riêng và không nhất thiết nằm trong registry annotation.

Các thuộc tính như `autoStartup`, `phase` và `shutdownTimeout` giúp điều khiển thời điểm khởi động và thời gian dừng. Nếu listener phụ thuộc DB hoặc dịch vụ khác, cần bảo đảm dependency đã sẵn sàng trước khi container nhận record và ứng dụng có đủ thời gian graceful shutdown để hoàn tất xử lý đang chạy.

## 13. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `@KafkaListener` không tìm thấy factory | Tên `containerFactory` không khớp tên bean | Kiểm tra bean name và chỉ định đúng `containerFactory` |
| Listener không dùng cấu hình YAML | Factory tự tạo không đi qua Boot configurer hoặc bị cấu hình Java ghi đè | Gọi configurer trước khi tùy chỉnh hoặc cấu hình rõ toàn bộ thuộc tính |
| Listener nhận kiểu dữ liệu sai | ConsumerFactory dùng deserializer không tương thích | Kiểm tra generic type, key/value deserializer và JSON type mapping |
| Concurrency cao nhưng throughput không tăng | Số partition ít, downstream nghẽn hoặc consumer không được gán partition | Kiểm tra partition assignment, lag và tài nguyên downstream |
| Batch listener nhận sai tham số | Factory chưa bật batch listener hoặc method signature không tương thích | Dùng `setBatchListener(true)` và kiểu tham số batch được Spring Kafka hỗ trợ |
| Offset commit không đúng kỳ vọng | AckMode, auto commit hoặc thời điểm acknowledge không phù hợp | Xem lại container AckMode và `enable.auto.commit` |
| Retry lặp vô hạn hoặc record bị bỏ qua | Error handler/recoverer không phù hợp, batch semantics chưa được xét | Cấu hình retry hữu hạn, dead-letter và kiểm tra commit behavior |
| Listener không dừng kịp | Shutdown timeout quá ngắn hoặc xử lý downstream bị chặn | Đặt timeout cho dependency và cấu hình thời gian graceful shutdown |

## 14. Quy trình thiết kế factory cho một ứng dụng

1. Xác định các nhóm listener và yêu cầu xử lý: record hay batch, group ID, topic và số partition.
2. Chọn hoặc tạo `ConsumerFactory` cho từng nhóm theo deserializer, security và consumer properties.
3. Tạo `ConcurrentKafkaListenerContainerFactory` cho nhóm listener có cùng chính sách.
4. Dùng `ConcurrentKafkaListenerContainerFactoryConfigurer` nếu cần kế thừa cấu hình Spring Boot.
5. Đặt concurrency, poll timeout, AckMode, error handler và filter theo yêu cầu nghiệp vụ.
6. Gắn factory vào `@KafkaListener` bằng `containerFactory` khi có nhiều factory.
7. Khởi động ứng dụng và kiểm tra container, consumer group, partition assignment và log.
8. Kiểm thử record success, lỗi xử lý, retry, dead-letter, rebalance và graceful shutdown.

Một factory tốt giúp chuẩn hóa cấu hình listener và giảm khác biệt không chủ đích giữa các endpoint. Khi cần hành vi khác nhau, hãy tạo factory riêng theo nhóm chính sách thay vì nhồi mọi cấu hình vào một factory chung rồi ghi đè rải rác trên từng listener.

## Checklist trước khi đưa listener container vào production

- Có factory bean đúng tên và endpoint `@KafkaListener` tham chiếu đúng factory.
- `ConsumerFactory` dùng deserializer và consumer properties phù hợp với topic.
- Đã quyết định dùng Boot configurer hay tự cấu hình đầy đủ.
- Concurrency phù hợp với số partition và năng lực downstream.
- `pollTimeout`, `max.poll.interval.ms` và `max.poll.records` được cân đối với thời gian xử lý.
- AckMode và `enable.auto.commit` nhất quán với thời điểm nghiệp vụ hoàn tất.
- Error handler có retry hữu hạn và chính sách recover/dead-letter rõ ràng.
- Batch listener bật đúng chế độ và method signature phù hợp.
- Filter có metric/log và không âm thầm loại bỏ sự kiện quan trọng.
- Có quy trình pause/resume, graceful shutdown và theo dõi consumer lag/rebalance.

`ListenerContainerFactory` là nơi tập trung cách Spring Kafka tạo và cấu hình listener container. Kết hợp đúng `ConsumerFactory`, `ContainerProperties`, concurrency, AckMode và error handler giúp các `@KafkaListener` có hành vi nhất quán, dễ kiểm thử và phù hợp với yêu cầu vận hành của từng luồng sự kiện.
