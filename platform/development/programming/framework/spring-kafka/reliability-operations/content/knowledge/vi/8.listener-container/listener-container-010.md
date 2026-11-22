# stopContainerWhenFenced

Trong Spring Kafka, `stopContainerWhenFenced` là thuộc tính của listener container dùng để dừng container khi transactional producer bị Kafka fencing và phát sinh `ProducerFencedException`. Fencing xảy ra khi broker xác định một producer cũ không còn quyền sử dụng cùng `transactional.id`, thường vì một producer khác đã khởi tạo với định danh đó và nhận producer epoch mới.

Khi producer đã bị fenced, producer cũ không thể tiếp tục hoàn tất transaction một cách hợp lệ. Nếu listener container vẫn tiếp tục nhận record và thử mở transaction bằng producer đã mất quyền, các lần xử lý tiếp theo có thể tiếp tục thất bại. Bật `stopContainerWhenFenced` giúp container dừng lại để hệ thống phát hiện sự cố và xử lý nguyên nhân trước khi cho consumer chạy tiếp.

## 1. Producer fencing là gì?

Kafka dùng `transactional.id` để nhận diện một transactional producer qua các lần khởi tạo. Khi producer khởi tạo transaction bằng `initTransactions()`, broker quản lý producer epoch gắn với transactional ID. Epoch giúp broker phân biệt producer hiện tại với một producer cũ có thể vẫn còn chạy do restart, network partition hoặc lỗi điều phối.

Giả sử producer A đang sử dụng `transactional.id=orders-instance-1`. Sau đó một producer B khởi tạo với cùng transactional ID. Broker cấp epoch mới cho B và fence A. Những thao tác transactional tiếp theo của A có thể thất bại với `ProducerFencedException` vì A đã trở thành producer cũ.

```text
Producer A khởi tạo transactional.id=orders-1
        |
        v
Broker cấp producer epoch cho A
        |
        v
Producer B khởi tạo cùng transactional.id=orders-1
        |
        v
Broker cấp epoch mới cho B và fence A
        |
        +------------------------------+
        |                              |
        v                              v
Producer B tiếp tục             Producer A đã bị fence
với epoch mới                   thao tác transaction thất bại
```

Fencing là cơ chế bảo vệ tính đúng đắn của transaction. Nó ngăn một producer cũ tiếp tục ghi dữ liệu sau khi một producer mới đã tiếp quản cùng transactional identity. Vì vậy, `ProducerFencedException` là dấu hiệu producer hiện tại đã mất quyền sở hữu transactional ID, không phải một lỗi mạng tạm thời có thể giải quyết bằng cách lặp lại nguyên thao tác trên cùng producer.

## 2. Vì sao listener container cần dừng khi bị fenced?

Với transactional listener container, Spring Kafka bắt đầu một Kafka transaction cho lần xử lý listener theo cấu hình. Record listener thường xử lý từng record trong transaction riêng; batch listener xử lý batch trong một transaction. Khi listener hoàn tất, container commit transaction. Nếu listener ném exception hoặc transaction thất bại, container thực hiện quy trình rollback và xử lý lỗi theo cấu hình.

Nếu producer dùng trong transaction bị fenced, container không thể dùng producer đó để commit transaction. `stopContainerWhenFenced=true` yêu cầu listener container dừng khi nhận `ProducerFencedException`. Việc dừng giúp ngăn container tiếp tục poll và xử lý thêm record trong khi transactional producer đã không còn hợp lệ.

Ví dụ luồng xử lý:

```text
Listener container bắt đầu transaction
        |
        v
Listener xử lý record hoặc batch
        |
        v
Producer gửi dữ liệu transactional / commit transaction
        |
        v
Broker phát hiện producer epoch đã cũ
        |
        v
ProducerFencedException
        |
        v
stopContainerWhenFenced=true
        |
        v
Listener container dừng
```

Đây là hành vi ở cấp listener container. Nó không nhất thiết dừng toàn bộ JVM, pod hoặc các listener container khác trong ứng dụng. Một ứng dụng có thể có nhiều listener endpoint; cần theo dõi container cụ thể đã bị dừng và trạng thái các endpoint còn lại.

Thuộc tính này đặc biệt hữu ích khi dùng transactional producer để thực hiện exactly-once semantics cho luồng Kafka-to-Kafka. Khi producer bị fenced, container dừng giúp sự cố lộ rõ trong vận hành thay vì tiếp tục chạy với producer đã mất quyền.

## 3. Cấu hình stopContainerWhenFenced

Thuộc tính được cấu hình trên `ContainerProperties` của listener container factory. Ví dụ:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                KafkaAwareTransactionManager<String, Object> transactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    ContainerProperties container = factory.getContainerProperties();
    container.setKafkaAwareTransactionManager(transactionManager);
    container.setStopContainerWhenFenced(true);

    return factory;
}
```

`KafkaAwareTransactionManager` ở ví dụ là transaction manager Kafka đã được cấu hình với transactional `ProducerFactory`. Nếu ứng dụng đã gắn transaction manager cho factory, chỉ cần đặt thuộc tính:

```java
factory.getContainerProperties().setStopContainerWhenFenced(true);
```

Listener endpoint sử dụng factory đó:

```java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    containerFactory = "kafkaListenerContainerFactory"
)
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

Đảm bảo listener container thực sự chạy với transaction manager và producer factory transactional. Chỉ đặt `stopContainerWhenFenced` không tự biến một listener thông thường thành transactional listener và không tự tạo `transactional.id`.

## 4. Transactional producer cần transactional.id phù hợp

Spring Kafka hỗ trợ transactional producer thông qua `DefaultKafkaProducerFactory` với `transactionIdPrefix`. Factory tạo các transactional ID từ prefix và suffix do factory quản lý. Prefix phải phân biệt các application instance đang chạy đồng thời để những instance độc lập không vô tình dùng cùng transactional ID.

Ví dụ tạo producer factory:

```java
DefaultKafkaProducerFactory<String, Object> producerFactory =
        new DefaultKafkaProducerFactory<>(producerProperties);

// appInstanceId phải duy nhất giữa các instance đang hoạt động.
producerFactory.setTransactionIdPrefix(appInstanceId + "-orders-");
```

Nếu dùng Spring Boot, transactional prefix có thể được khai báo bằng cấu hình producer tương ứng của phiên bản Boot đang chạy:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${APP_INSTANCE_ID}-orders-
```

`APP_INSTANCE_ID` phải có giá trị phù hợp với cách triển khai. Không đặt cùng một prefix cố định cho nhiều replica chạy đồng thời nếu chúng dùng chung broker và có thể tạo ra cùng transactional ID. Khi hai instance tạo producer với cùng transactional ID, instance khởi tạo sau có thể fence producer của instance còn lại.

Mặt khác, transactional ID cũng có vai trò nhận diện producer cũ khi một instance được khởi động lại. Việc dùng lại định danh của cùng logical instance có thể giúp producer mới fence một producer cũ còn sót lại. Do đó, cần thiết kế định danh theo vòng đời triển khai: duy nhất giữa các instance hoạt động đồng thời, đồng thời có tính ổn định phù hợp với chiến lược restart và fencing của hệ thống.

Với `DefaultKafkaProducerFactory`, suffix được quản lý để tạo transactional producer cho các luồng hoặc container. Không tự ghép một suffix tùy tiện ở nhiều nơi mà không hiểu cơ chế cache và quản lý producer của factory; hãy để factory quản lý suffix hoặc dùng cấu hình được Spring Kafka hỗ trợ cho phiên bản ứng dụng.

## 5. stopContainerWhenFenced không phải cơ chế retry

Khi container dừng vì producer bị fenced, `stopContainerWhenFenced` không tự sửa transactional ID, không tạo lại transaction manager và cũng không bảo đảm container tự khởi động lại. Nó là một hành động bảo vệ vòng đời container khi phát hiện producer mất quyền.

Các bước xử lý nên theo trình tự:

1. Xác định listener container nào đã dừng và ghi nhận exception gốc.
2. Tìm producer hoặc application instance khác đang sử dụng cùng transactional ID.
3. Kiểm tra `transactionIdPrefix`, cách tạo suffix, số replica và concurrency.
4. Xác nhận producer cũ đã được dừng hoặc loại bỏ nguyên nhân tạo xung đột.
5. Đảm bảo producer factory có thể tạo transactional producer hợp lệ.
6. Chỉ khởi động lại listener container sau khi nguyên nhân fencing đã được xử lý.

Nếu chỉ restart container trong khi một instance khác vẫn dùng cùng transactional ID, producer mới có thể tiếp tục bị fence. Hệ thống sẽ lặp lại chu kỳ start, nhận record, lỗi transaction và stop. Cần sửa nguyên nhân xung đột trước khi phục hồi.

## 6. Phân biệt producer fencing với các lỗi khác

Không phải mọi lỗi liên quan đến consumer group hoặc transaction đều là `ProducerFencedException`.

| Lỗi hoặc tình huống | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `ProducerFencedException` | Transactional producer đã mất quyền sử dụng transactional ID do producer epoch mới hơn. | Kiểm tra xung đột transactional ID và dừng container theo cấu hình. |
| `InvalidProducerEpochException` | Producer epoch không hợp lệ cho thao tác đang thực hiện. | Kiểm tra trạng thái producer, transaction và nguyên nhân epoch bị thay đổi. |
| `FencedInstanceIdException` | Consumer static member ID bị xung đột trong group. | Kiểm tra `group.instance.id` và định danh consumer member. |
| `CommitFailedException` | Consumer không thể commit offset, thường liên quan đến group membership hoặc quyền sở hữu partition đã thay đổi. | Kiểm tra rebalance, poll loop và trạng thái group. |
| Transaction timeout hoặc lỗi broker tạm thời | Transaction không hoàn tất trong thời hạn hoặc broker/network gặp sự cố. | Kiểm tra timeout, broker, kết nối và retry/error handling. |

`stopContainerWhenFenced` tập trung vào trường hợp producer transactional bị fence. Không dùng nó như một công tắc chung để xử lý mọi lỗi consumer, lỗi commit hoặc lỗi transaction.

## 7. Quan hệ với rollback và error handler

Trong transactional listener, exception xảy ra trong lúc xử lý thường khiến transaction rollback. Spring Kafka có thể dùng `AfterRollbackProcessor` để xử lý record sau rollback, ví dụ seek để đọc lại hoặc phục hồi record sau số lần thử nhất định. Với transactional producer đã bị fenced, producer không còn hợp lệ để thực hiện các thao tác transaction tiếp theo.

Vì vậy, khi nhận `ProducerFencedException`, việc dừng container có ý nghĩa khác với retry một record nghiệp vụ thông thường. Retry có thể phù hợp khi database tạm thời không khả dụng hoặc lỗi xử lý có thể khắc phục; fencing cho biết producer identity đã bị thay thế. Tiếp tục dùng producer cũ không giải quyết được tình trạng này.

Nếu ứng dụng có dead-letter topic hoặc quy trình phục hồi, cần phân biệt lỗi record với lỗi hạ tầng transactional producer. Không nên chuyển một record sang dead-letter topic chỉ vì producer đã bị fenced nếu thao tác publish dead-letter cũng phụ thuộc transactional producer đã mất quyền. Trước hết cần khôi phục khả năng transaction hợp lệ, sau đó để quy trình xử lý lỗi thực hiện theo chính sách đã thiết kế.

## 8. Theo dõi listener container đã dừng

Ứng dụng cần quan sát trạng thái listener container và ghi nhận lý do dừng. Có thể dùng `KafkaListenerEndpointRegistry` để truy cập container theo ID và kiểm tra trạng thái:

```java
@Component
public class ListenerContainerStatus {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerContainerStatus(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isOrdersListenerRunning() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        return container != null && container.isRunning();
    }
}
```

Đoạn mã trên minh họa cách truy vấn trạng thái, không thay thế việc thu thập nguyên nhân dừng. Khi vận hành, nên ghi log exception fencing cùng application instance ID, transactional ID/prefix, listener ID và thời điểm xảy ra. Nếu dùng nhiều container con, cần xác định rõ container nào bị ảnh hưởng và trạng thái của các consumer còn lại.

Spring Kafka phát các application event liên quan đến vòng đời consumer và container. Có thể đăng ký listener cho các event phù hợp với phiên bản đang sử dụng để ghi nhận thời điểm consumer dừng, bắt đầu hoặc container thay đổi trạng thái. Hãy kiểm tra tên event và metadata của phiên bản Spring Kafka cụ thể; không suy đoán nguyên nhân chỉ từ một event dừng chung.

Metric hữu ích gồm:

- Số lần `ProducerFencedException` theo listener và application instance.
- Số listener container đang chạy và đã dừng.
- Số lần restart container sau sự cố fencing.
- Consumer lag và thời gian container ngừng xử lý.
- Số transaction abort/commit failure và lỗi producer liên quan.
- Số replica đang chạy cùng transactional ID prefix hoặc cấu hình instance ID bị trùng.

## 9. Phục hồi container có kiểm soát

Sau khi sửa nguyên nhân, có thể khởi động lại listener container thông qua registry. Ví dụ:

```java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && !container.isRunning()) {
    container.start();
}
```

Chỉ gọi `start()` sau khi transactional producer có thể được tạo hợp lệ và xung đột transactional ID đã được giải quyết. Nếu khởi động lại quá sớm, container có thể gặp cùng lỗi fencing ngay khi bắt đầu transaction tiếp theo.

Trong production, việc phục hồi có thể được thực hiện bởi operator hoặc một quy trình điều phối có kiểm soát. Nếu tự động restart, cần có backoff, giới hạn số lần thử, metric cảnh báo và điều kiện xác nhận nguyên nhân đã hết. Không tạo vòng lặp restart nhanh vô hạn vì nó có thể làm tăng rebalance, log noise và tải broker.

## 10. Những tình huống triển khai dễ gây fencing

### Nhiều replica dùng cùng transactional prefix

Nếu hai replica dùng cùng `transactionIdPrefix` và factory tạo ra cùng các transactional ID suffix, producer của replica này có thể fence producer của replica kia. Đây là lỗi cấu hình phổ biến khi chuyển ứng dụng transactional từ một instance sang nhiều replica mà vẫn giữ prefix cố định.

Giải pháp là cấp prefix duy nhất cho từng instance đang hoạt động và kiểm tra cách suffix được sinh ra. Đừng dùng tên môi trường chung như `orders-` làm prefix cho mọi pod nếu các pod chạy đồng thời.

### Restart trong lúc instance cũ chưa dừng hẳn

Trong một số tình huống rollout hoặc network partition, instance mới có thể bắt đầu trước khi producer cũ thực sự kết thúc. Nếu hai instance dùng cùng identity, producer mới fence producer cũ. Fencing bảo vệ tính đúng đắn của transaction, nhưng container của instance cũ cần dừng và hệ thống cần xác định instance nào được quyền tiếp tục.

### Concurrency và producer factory

Một listener container có thể có nhiều consumer thread khi dùng concurrency. Producer factory transactional của Spring Kafka quản lý producer và suffix theo cơ chế riêng. Cần để factory tạo transactional ID phù hợp cho từng producer; tránh tự tái sử dụng một producer transactional không thread-safe hoặc tự gán cùng transactional ID cho nhiều producer đồng thời.

### Dùng nhầm static member ID

`group.instance.id` thuộc về consumer group membership, còn `transactional.id` thuộc về producer transaction. Hai định danh phục vụ hai cơ chế khác nhau. Trùng `group.instance.id` có thể gây lỗi fencing consumer member; trùng `transactional.id` có thể fence producer. Cần kiểm tra đúng loại exception trước khi điều chỉnh cấu hình.

## 11. Checklist vận hành khi gặp ProducerFencedException

1. Lấy exception gốc và xác nhận đây là `ProducerFencedException`.
2. Ghi nhận listener ID, application instance, transactional ID/prefix và thời điểm lỗi.
3. Kiểm tra số replica, rollout và concurrency tại thời điểm xảy ra fencing.
4. Xác định có producer khác đang khởi tạo cùng transactional ID hay không.
5. Kiểm tra `transactionIdPrefix` có duy nhất giữa các instance đang hoạt động hay không.
6. Kiểm tra cấu hình `DefaultKafkaProducerFactory` và cách factory quản lý suffix.
7. Xác nhận listener container đã dừng nếu `stopContainerWhenFenced=true`.
8. Xử lý instance hoặc cấu hình gây xung đột trước khi restart container.
9. Theo dõi transaction commit/abort, container state, consumer lag và rebalance sau phục hồi.
10. Xác nhận các record có thể được giao lại được xử lý idempotent.

## 12. Nguyên tắc sử dụng

- Bật `stopContainerWhenFenced` trên listener container transactional khi muốn dừng container ngay khi producer bị fence.
- Cấu hình transaction manager và transactional producer đúng cách; thuộc tính này không tự bật transaction.
- Đảm bảo transactional ID/prefix không bị trùng giữa các application instance hoạt động đồng thời.
- Hiểu fencing là dấu hiệu producer cũ đã mất quyền, không phải lỗi tạm thời để retry liên tục trên cùng producer.
- Phân biệt `ProducerFencedException` với lỗi consumer static membership, lỗi commit offset và lỗi transaction khác.
- Theo dõi container state và exception để phát hiện listener đã dừng.
- Chỉ restart sau khi xử lý nguyên nhân xung đột; có backoff và giới hạn nếu tự động phục hồi.
- Thiết kế nghiệp vụ idempotent để chịu được record được giao lại sau rollback, restart hoặc rebalance.

`stopContainerWhenFenced` giúp Spring Kafka dừng listener container khi transactional producer đã bị Kafka fence. Kết hợp cấu hình transactional ID duy nhất, giám sát container và quy trình phục hồi có kiểm soát, ứng dụng có thể phát hiện sớm xung đột producer và tránh tiếp tục xử lý bằng một producer không còn quyền commit transaction.
