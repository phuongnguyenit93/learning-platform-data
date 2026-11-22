# Consumer exception và vòng đời container trong Spring Kafka

Trong Spring Kafka, một exception phát sinh trong listener ảnh hưởng trực tiếp đến cách container xử lý record, commit offset, retry và tiếp tục poll. Container quản lý consumer thread, việc gọi listener, acknowledgement, error handler và vòng đời kết nối với broker. Vì vậy, hiểu exception và lifecycle cùng nhau là điều cần thiết để tránh mất record, xử lý trùng hoặc làm consumer dừng ngoài dự kiến.

Một nguyên tắc quan trọng: **container chỉ biết listener xử lý thành công khi lời gọi listener kết thúc bình thường hoặc lỗi đã được error handler xử lý theo chính sách được cấu hình**. Nếu code bắt exception rồi bỏ qua, container thường xem lời gọi đó là thành công và tiếp tục quy trình commit theo acknowledgement mode. Nếu muốn Kafka giao lại record, lỗi cần được truyền tới cơ chế xử lý lỗi hoặc được xử lý bằng một chính sách phục hồi có chủ đích.

## 1. Container đảm nhiệm những việc gì?

Spring Kafka cung cấp hai loại listener container thường gặp:

- **KafkaMessageListenerContainer** quản lý một Kafka consumer và xử lý record trên một consumer thread.
- **ConcurrentMessageListenerContainer** quản lý nhiều child KafkaMessageListenerContainer để tăng concurrency. Mỗi child có consumer và thread riêng.

Khi ứng dụng dùng @KafkaListener, Spring tạo endpoint và đăng ký container tương ứng thông qua KafkaListenerEndpointRegistry. Container thường được tạo từ ConcurrentKafkaListenerContainerFactory hoặc KafkaListenerContainerFactory đã cấu hình.

Luồng xử lý cơ bản:

~~~text
Spring Application
      |
      v
KafkaListenerEndpointRegistry
      |
      v
Listener Container
      |
      +--> Tạo KafkaConsumer
      |
      +--> Subscribe / nhận partition assignment
      |
      +--> poll()
      |
      +--> Chuyển record cho listener adapter
      |         |
      |         v
      |     @KafkaListener method
      |         |
      |         +--> trả về bình thường
      |         |        |
      |         |        v
      |         |     acknowledgement / commit
      |         |
      |         +--> ném exception
      |                  |
      |                  v
      |             CommonErrorHandler
      |                  |
      |                  +--> retry / seek / recover / DLT
      |
      +--> poll tiếp theo
      |
      v
Consumer đóng khi container dừng
~~~

Container điều phối consumer và listener; Kafka broker lưu record và offset. Container không tự động biết một cập nhật database hoặc lời gọi HTTP đã thành công về mặt nghiệp vụ. Nếu listener gọi hệ thống bên ngoài, ứng dụng phải xử lý tính idempotent và ranh giới transaction của hệ thống đó.

## 2. Vòng đời của listener container

Một container có thể được nhìn theo các giai đoạn sau:

1. **Được tạo và cấu hình:** factory áp dụng consumer factory, listener, concurrency, acknowledgement mode, error handler và các thuộc tính container.
2. **Được khởi động:** container tạo consumer, đăng ký với broker và tham gia group hoặc nhận partition assignment.
3. **Đang chạy:** consumer poll record, gọi listener, xử lý acknowledgement và tiếp tục poll.
4. **Tạm dừng:** container hoặc consumer có thể pause theo yêu cầu ứng dụng, rebalance hoặc điều kiện vận hành.
5. **Dừng:** container ngừng nhận công việc mới, hoàn tất phần xử lý đang chạy theo giới hạn shutdown, commit nếu chính sách cho phép và đóng consumer.
6. **Khởi động lại:** container có thể được start lại; consumer sẽ tham gia group và lấy vị trí đọc theo offset đã commit cùng trạng thái group.

Vòng đời ở mức khái niệm:

~~~text
CREATED
   |
   | start()
   v
STARTING
   |
   | consumer sẵn sàng
   v
RUNNING <------ resume()
   |  ^
   |  |
   |  +------ PAUSED
   |             ^
   |             |
   +---------- pause()
   |
   | stop()
   v
STOPPING
   |
   | consumer đóng
   v
STOPPED
~~~

Đây là sơ đồ trạng thái để giải thích hành vi. Trạng thái nội bộ và event cụ thể phụ thuộc phiên bản Spring Kafka và loại container.

### Container được khởi động như thế nào?

Container được quản lý bởi Spring lifecycle. Theo cấu hình, listener container có thể tự khởi động cùng application context hoặc được ứng dụng khởi động thủ công. Với endpoint được khai báo bằng @KafkaListener, có thể đặt autoStartup=false để kiểm soát thời điểm bắt đầu.

~~~java
@Component
public class OrderListener {

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "order-service",
            autoStartup = "false"
    )
    public void onOrder(OrderCreated event) {
        process(event);
    }

    private void process(OrderCreated event) {
        // Xử lý nghiệp vụ.
    }
}
~~~

Container của endpoint được truy cập qua KafkaListenerEndpointRegistry:

~~~java
@Service
public class ListenerLifecycleService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerLifecycleService(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container != null && !container.isRunning()) {
            container.start();
        }
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
~~~

ID trong registry phải khớp với thuộc tính id của @KafkaListener. Không nên giả định container được tạo từ annotation là một bean có thể inject trực tiếp bằng tên method. Registry là điểm truy cập phù hợp cho các endpoint do annotation đăng ký.

### Dừng container có kiểm soát

Dừng consumer là một phần của vận hành, ví dụ khi bảo trì, triển khai phiên bản mới hoặc tạm ngưng xử lý. Container có phương thức stop với callback để ứng dụng biết khi việc dừng hoàn tất:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && container.isRunning()) {
    container.stop(() -> log.info("Orders listener stopped"));
}
~~~

Callback được gọi khi container đã dừng. Ứng dụng có thể dùng nó để điều phối bước tiếp theo trong quá trình shutdown hoặc bảo trì. Thời gian chờ shutdown cần hữu hạn; không nên giữ ứng dụng sống vô thời hạn chỉ để chờ một listener bị treo.

Nếu listener đang xử lý record khi shutdown, hành vi commit và xử lý phần còn lại phụ thuộc acknowledgement mode, transaction và container configuration. Record chưa được commit có thể được giao lại khi consumer group tiếp tục. Vì vậy, listener nên có thời gian xử lý hữu hạn và có thể phục hồi khi chạy lại.

## 3. Exception từ listener được truyền đi như thế nào?

Khi method @KafkaListener ném exception, exception đi từ listener adapter tới container. Container chuyển lỗi cho CommonErrorHandler được cấu hình. Error handler quyết định có retry, seek offset, recover record, gửi DLT hoặc kết thúc xử lý theo chính sách nào.

~~~text
KafkaConsumer.poll()
       |
       v
Listener adapter
       |
       v
@KafkaListener
       |
       +--> xử lý xong
       |       |
       |       v
       |   ack / commit theo mode
       |
       +--> throw RuntimeException
               |
               v
        CommonErrorHandler
               |
               +--> retry listener
               |
               +--> seek để đọc lại
               |
               +--> recover / publish DLT
               |
               +--> exception tiếp tục được truyền
~~~

Điều quan trọng là exception không tự động đồng nghĩa record sẽ được đọc lại trong mọi cấu hình. Error handler, acknowledgement mode, transaction và chính sách recovery quyết định offset cuối cùng.

### Đừng nuốt exception ngoài ý muốn

Ví dụ sau có thể gây mất cơ hội retry:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Could not process order", ex);
        // Không ném lại exception.
    }
}
~~~

Method đã kết thúc bình thường theo góc nhìn container. Container có thể commit offset theo acknowledgement mode, dù nghiệp vụ thất bại.

Nếu muốn error handler của container xử lý lỗi, hãy để exception truyền ra:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Nếu cần bổ sung ngữ cảnh log, có thể log rồi ném lại exception:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Order processing failed, orderId={}", event.id(), ex);
        throw ex;
    }
}
~~~

Chỉ nên bắt và xử lý exception tại listener khi ứng dụng thật sự muốn coi record là đã được xử lý hoặc có một quy trình phục hồi riêng đã hoàn tất. Việc ghi log đơn thuần không phải là recovery.

## 4. Phân loại lỗi để quyết định retry hay recovery

Không phải lỗi nào cũng có thể giải quyết bằng retry.

| Loại lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Lỗi tạm thời | Database tạm mất kết nối, dịch vụ ngoài trả 503 | Retry với backoff và deadline |
| Lỗi dữ liệu | Thiếu trường bắt buộc, giá trị không hợp lệ | Không retry nguyên trạng; chuyển DLT hoặc trạng thái cần xử lý |
| Lỗi cấu hình | Sai topic, sai serializer, thiếu quyền | Sửa cấu hình hoặc quyền; cảnh báo vận hành |
| Lỗi nghiệp vụ có thể thay đổi theo thời gian | Đơn hàng chưa đủ điều kiện vì một dependency chưa cập nhật | Xác định retry có giới hạn hoặc quy trình chờ riêng |
| Lỗi lập trình | NullPointerException do bug | Cảnh báo, giới hạn retry và giữ record để điều tra |

Retry một lỗi cố định không làm lỗi tự biến mất. Nếu record có payload không hợp lệ, retry hàng trăm lần chỉ làm tăng consumer lag và giữ partition bị chặn lâu hơn.

Nên phân loại exception rõ ràng và ghi nhận event ID, topic, partition, offset, key cùng nguyên nhân gốc để vận hành có thể truy vết.

## 5. Cấu hình CommonErrorHandler và DefaultErrorHandler

Spring Kafka cung cấp CommonErrorHandler cho việc xử lý lỗi của listener container. DefaultErrorHandler là một lựa chọn phổ biến cho record listener: nó hỗ trợ retry, backoff và recovery sau khi hết số lần thử.

Ví dụ cấu hình factory với hai lần retry sau lần gọi đầu tiên:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    DefaultErrorHandler commonErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1000L, 2L);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(recoverer, backOff);

        handler.addNotRetryableExceptions(
                IllegalArgumentException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, String> consumerFactory,
            DefaultErrorHandler commonErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(commonErrorHandler);
        factory.setConcurrency(3);

        return factory;
    }
}
~~~

Các generic type của KafkaTemplate cần khớp với ProducerFactory và serializer thực tế trong ứng dụng. Ví dụ dùng Object để minh họa một template có thể publish payload DLT; trong dự án thực tế có thể inject template chuyên dụng cho kiểu dữ liệu của DLT.

Với FixedBackOff(1000L, 2L):

- Lần đầu listener được gọi ngay.
- Nếu thất bại, error handler chờ khoảng một giây rồi thử lại.
- Có thêm tối đa hai lần retry sau lần gọi đầu.
- Khi hết retry, recoverer được gọi để xử lý record, trong ví dụ là publish sang dead-letter topic.

Tổng số lần gọi listener trong trường hợp này tối đa là ba nếu mọi lần đều thất bại. Số lần và backoff phải được thiết kế theo thời gian xử lý, deadline nghiệp vụ và khả năng chịu tải của dependency.

### Đánh dấu lỗi không retry

Có thể khai báo exception không được retry bằng addNotRetryableExceptions. Ví dụ IllegalArgumentException thường đại diện dữ liệu đầu vào không hợp lệ trong ứng dụng này. Việc phân loại phải dựa trên ý nghĩa exception trong domain; cùng một class exception có thể mang ý nghĩa khác nhau ở các ứng dụng.

Cũng có thể phân loại các exception retryable và non-retryable qua cấu hình classification của DefaultErrorHandler. Tránh phân loại quá rộng khiến lỗi tạm thời bị đưa thẳng sang DLT hoặc lỗi cố định bị retry liên tục.

### Dead-letter topic

DeadLetterPublishingRecoverer gửi record không phục hồi được sang topic DLT. Mặc định, tên topic thường được tạo bằng cách thêm hậu tố .DLT vào tên topic nguồn; có thể cấu hình destination resolver riêng để đổi tên topic hoặc partition.

Ví dụ:

~~~text
orders
   |
   +--> listener thất bại
           |
           +--> retry theo backoff
                    |
                    +--> thành công: tiếp tục
                    |
                    +--> hết retry: orders.DLT
~~~

Khi định tuyến DLT theo cùng partition với topic gốc, topic DLT cần đủ số partition tương ứng. Cần cấu hình serializer phù hợp cho cả record gốc và exception/header. DLT phải được giám sát và có quy trình sửa lỗi, phát lại hoặc xử lý thủ công; publish vào DLT không có nghĩa nghiệp vụ đã thành công.

## 6. Blocking retry, retry topic và thứ tự partition

Spring Kafka hỗ trợ nhiều chiến lược retry.

### Blocking retry bằng DefaultErrorHandler

Blocking retry giữ việc xử lý ở luồng consumer cho đến khi retry hoặc recovery hoàn tất. Với cơ chế seek, record lỗi được đọc lại theo offset; các record sau trong partition có thể phải chờ. Điều này hữu ích khi cần giữ thứ tự nghiêm ngặt nhưng có thể làm partition bị chặn trong thời gian backoff.

Dùng blocking retry khi lỗi thường ngắn, số lần thử nhỏ và giữ thứ tự là ưu tiên.

### Non-blocking retry bằng @RetryableTopic

@RetryableTopic đưa record lỗi sang các retry topic có thời gian chờ riêng, rồi chuyển tiếp tới listener sau khoảng delay. Cách này cho phép consumer tiếp tục xử lý record khác trong topic chính, nhưng có thể làm thay đổi thứ tự quan sát theo nghiệp vụ.

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1000,
                multiplier = 2.0,
                maxDelay = 10000
        ),
        dltTopicSuffix = "-dlt"
)
@KafkaListener(topics = "orders", groupId = "order-service")
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Ví dụ minh họa bốn lần thử tổng cộng theo cấu hình retry topic. Cần xác nhận semantics của attempts và các tùy chọn theo phiên bản Spring Kafka đang dùng. Non-blocking retry có giới hạn với container transaction và một số loại listener; kiểm tra tài liệu phiên bản trước khi kết hợp.

Không nên cấu hình đồng thời nhiều cơ chế retry mà không xác định rõ số lần tổng cộng. Ví dụ, nếu listener có retry topic bốn lần và mỗi lần lại có blocking retry ba lần, tổng số lần thực thi có thể lớn hơn dự kiến.

### Chọn theo yêu cầu thứ tự

| Nhu cầu | Hướng xử lý |
|---|---|
| Giữ thứ tự nghiêm ngặt trong partition | Blocking retry và backoff ngắn, có giới hạn |
| Cho phép record sau tiếp tục trong khi record lỗi đang chờ | Retry topic, chấp nhận khả năng đổi thứ tự |
| Lỗi dữ liệu cố định | Recovery/DLT sớm |
| Dependency thường mất vài giây | Blocking retry ngắn hoặc retry topic theo deadline |
| Dependency có thể mất hàng giờ | Lưu trạng thái bền vững và quy trình retry dài hạn; không giữ consumer thread chờ |

## 7. Acknowledgement mode và commit offset khi listener lỗi

Acknowledgement mode xác định khi nào container commit offset. Nó ảnh hưởng trực tiếp tới việc record được đọc lại sau exception.

| Ack mode | Hành vi khái quát | Tác động khi listener lỗi |
|---|---|---|
| RECORD | Commit sau khi listener xử lý thành công từng record | Record lỗi được xử lý theo error handler; offset phụ thuộc recovery |
| BATCH | Commit sau khi xử lý xong batch trả về từ poll | Lỗi trong batch ảnh hưởng commit và xử lý các record còn lại theo handler |
| MANUAL | Listener gọi acknowledge; container thực hiện commit theo batch semantics | Ứng dụng phải xác định rõ lúc acknowledge và cách error handler xử lý |
| MANUAL_IMMEDIATE | Acknowledge trên consumer thread có thể commit ngay | Commit trước khi nghiệp vụ hoàn tất có thể làm mất cơ hội đọc lại |

Với record listener, RECORD thường dễ hiểu khi muốn commit sau mỗi record. BATCH có thể hiệu quả hơn nhưng cần hiểu rằng nhiều record từ một poll có thể cùng nằm trong một đơn vị commit.

Nếu listener ném exception trước khi acknowledge, error handler có thể retry hoặc recover. Nếu listener đã acknowledge rồi mới ném exception, offset có thể đã được commit tùy mode và thread thực thi. Vì vậy, không acknowledge trước khi công việc cần được bảo vệ đã hoàn tất.

Ví dụ cấu hình record mode:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
      concurrency: 3
~~~

Spring Kafka listener container thường quản lý commit và tắt auto commit theo cấu hình mặc định của container. Hãy xác nhận cấu hình consumer thực tế, nhất là khi tự tạo ConsumerFactory hoặc thay đổi listener container factory.

### Batch listener

Với batch listener, method nhận nhiều record cùng lúc. Một exception có thể làm cả batch bị xem là thất bại. Nếu cần xác định record nào lỗi, có thể dùng BatchListenerFailedException để chỉ ra record gây lỗi, từ đó DefaultErrorHandler có thể xử lý phần trước và phần sau theo chính sách batch.

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch",
        containerFactory = "batchFactory"
)
public void onOrders(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int i = 0; i < records.size(); i++) {
        try {
            orderService.process(records.get(i).value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                    "Could not process order",
                    ex,
                    i
            );
        }
    }
}
~~~

Chỉ dùng ví dụ này khi factory được cấu hình batch listener. Nếu listener batch không xác định record lỗi, error handler có thể phải retry toàn batch hoặc áp dụng chính sách khác, khiến record đã xử lý trước đó bị thực thi lại. Nghiệp vụ vẫn nên idempotent.

## 8. Exception trong Kafka transaction

Khi listener container sử dụng Kafka transaction manager, container bắt đầu transaction trước khi gọi listener. Nếu listener hoàn tất bình thường, container đưa offset vào transaction và commit. Nếu listener ném exception, transaction bị rollback/abort và record có thể được đọc lại theo quy trình phục hồi.

Với transactional listener, AfterRollbackProcessor đảm nhiệm xử lý record sau rollback. Đây là cơ chế cần hiểu khi dùng transaction; không nên giả định DefaultErrorHandler sẽ thay thế mọi hành vi rollback/recovery của transactional container.

~~~text
Container bắt đầu Kafka transaction
          |
          v
       Listener
          |
          +--> thành công
          |       |
          |       v
          |   Gửi offset vào transaction
          |       |
          |       v
          |   Commit transaction
          |
          +--> exception
                  |
                  v
              Abort transaction
                  |
                  v
          AfterRollbackProcessor
                  |
                  +--> redelivery
                  |
                  +--> recover / DLT
~~~

Nếu listener cập nhật database trong khi Kafka transaction đang chạy, database không tự động tham gia Kafka transaction. Cần dùng transaction manager phù hợp hoặc mô hình inbox/outbox và idempotency để tránh trạng thái lệch giữa hai hệ thống.

## 9. Lỗi xảy ra trước khi listener được gọi

Không phải exception nào cũng xuất phát từ method @KafkaListener. Một số lỗi xảy ra khi poll, deserialize, chuyển đổi message hoặc khi consumer tương tác với broker.

### Deserialization exception

Nếu deserializer ném exception, listener có thể không nhận được payload để xử lý. Spring Kafka cung cấp ErrorHandlingDeserializer để bắt lỗi deserialize và chuyển thông tin lỗi vào header của record, cho phép container error handler hoặc recoverer xử lý.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Cấu hình delegate cụ thể phụ thuộc kiểu key/value và serializer của producer. Với JSON, cần cấu hình trusted packages/type mapping theo chính sách bảo mật và mô hình dữ liệu của ứng dụng. Không nên cho phép deserialize class tùy ý từ dữ liệu không tin cậy.

### Poll và consumer exception

Lỗi kết nối broker, coordinator hoặc rebalance có thể phát sinh trong poll hoặc khi container quản lý consumer. Không phải tất cả lỗi này đều được xử lý giống exception từ listener. Container có cơ chế xử lý các lỗi consumer và lifecycle riêng; theo dõi log, event và metric để phân biệt lỗi poll, lỗi listener và lỗi commit.

Nếu consumer không phản hồi trong thời gian dài, cần xem xét thời gian xử lý listener, poll interval, heartbeat và rebalance. Tăng timeout một cách máy móc có thể che giấu listener bị treo và kéo dài thời gian phát hiện sự cố.

## 10. KafkaListenerErrorHandler và CommonErrorHandler khác nhau thế nào?

Spring Kafka có thể khai báo error handler ở mức annotation và ở mức container. Hai cơ chế này có phạm vi khác nhau.

**KafkaListenerErrorHandler** được gắn vào @KafkaListener thông qua thuộc tính errorHandler. Nó xử lý exception ở mức listener endpoint và có thể dùng để tạo phản hồi hoặc bổ sung logic cho một listener cụ thể.

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        errorHandler = "ordersListenerErrorHandler"
)
public OrderResult onOrder(OrderCreated event) {
    return orderService.process(event);
}

@Bean
KafkaListenerErrorHandler ordersListenerErrorHandler() {
    return (message, exception) -> {
        log.error("Listener endpoint failed: {}", message, exception);
        throw exception;
    };
}
~~~

Trong ví dụ, handler log lỗi rồi ném lại để container tiếp tục xử lý qua error handling của container. Nếu handler trả về bình thường và nuốt lỗi, container có thể xem việc gọi listener đã được xử lý xong theo luồng endpoint.

**CommonErrorHandler** được cấu hình cho container và kiểm soát hành vi xử lý lỗi ở cấp container, như retry, seek, recovery và DLT. Đây là nơi thường đặt DefaultErrorHandler cho record/batch listener.

Không nên dùng listener error handler để thay thế hoàn toàn container error handler nếu mục tiêu là quản lý offset và redelivery. Hãy xác định rõ nơi exception được xử lý và liệu nó còn được truyền tới container hay không.

## 11. Quản lý concurrency, pause và resume

ConcurrentMessageListenerContainer có thể tạo nhiều child container để xử lý nhiều partition đồng thời. Concurrency không nhất thiết bằng số thread thực sự hữu ích: số partition được gán cho consumer group giới hạn mức song song có thể đạt được.

Ví dụ:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 3
~~~

Nếu topic có sáu partition và concurrency là ba, mỗi consumer có thể nhận khoảng hai partition tùy assignment strategy. Nếu chỉ có một partition, tăng concurrency lên mười không tạo ra mười luồng xử lý song song cho partition đó.

Container có thể pause và resume để điều tiết tải:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && container.isRunning()) {
    container.pause();
}

// Sau khi dependency hoặc hệ thống phục hồi:
if (container != null && container.isRunning()) {
    container.resume();
}
~~~

Pause dừng việc giao record mới cho listener theo cơ chế container, nhưng consumer vẫn tiếp tục poll để giữ membership trong group. Điều này khác với stop, vốn đóng consumer và rời vòng đời đang chạy. Hãy dùng pause/resume cho backpressure hoặc bảo trì ngắn; dùng stop khi cần đóng hẳn container.

Khi pause do ứng dụng, cần có điều kiện resume rõ ràng và metric để phát hiện container bị pause quá lâu. Không nên pause vô thời hạn mà không có cảnh báo.

## 12. Theo dõi lifecycle qua container events

Spring Kafka phát các application event giúp quan sát vòng đời consumer và container. Một số event thường hữu ích:

| Event | Ý nghĩa |
|---|---|
| ConsumerStartingEvent | Consumer sắp được tạo/khởi động |
| ConsumerStartedEvent | Consumer đã khởi động |
| ConsumerFailedToStartEvent | Consumer không khởi động được |
| ConsumerStoppingEvent | Consumer đang dừng |
| ConsumerStoppedEvent | Consumer đã dừng; event có thông tin nguyên nhân dừng |
| ListenerContainerIdleEvent | Container không nhận record trong khoảng idle đã cấu hình |
| NonResponsiveConsumerEvent | Consumer có dấu hiệu không phản hồi trong khoảng theo dõi |
| ConsumerPausedEvent | Consumer/container đã pause |
| ConsumerResumedEvent | Consumer/container đã resume |

Tên event và chi tiết payload phụ thuộc phiên bản Spring Kafka. Event thường được phát từ consumer/container thread; nếu listener event thực hiện công việc lâu, nó có thể ảnh hưởng đến luồng consumer. Hãy xử lý nhanh hoặc chuyển việc nặng sang executor riêng.

Có thể lắng nghe event bằng @EventListener:

~~~java
@Component
public class KafkaContainerMonitor {

    @EventListener
    public void onConsumerStopped(ConsumerStoppedEvent event) {
        log.warn(
                "Kafka consumer stopped: reason={}",
                event.getReason()
        );
    }

    @EventListener
    public void onConsumerStarted(ConsumerStartedEvent event) {
        log.info("Kafka consumer started: {}", event.getSource());
    }
}
~~~

Các kiểu event và getter có thể thay đổi theo phiên bản. Hãy dùng đúng API của dependency đang triển khai. Event lifecycle bổ sung thông tin cho monitoring; nó không thay thế metric consumer lag, log exception và health check của ứng dụng.

## 13. Các tình huống vận hành thường gặp

### Listener ném exception liên tục

Kiểm tra exception gốc và xác định lỗi tạm thời hay lỗi dữ liệu. Nếu lỗi cố định, phân loại non-retryable hoặc chuyển DLT sớm. Nếu dependency tạm thời lỗi, dùng backoff có giới hạn và theo dõi consumer lag.

### Consumer group bị lag tăng nhanh

Một record bị retry blocking lâu có thể giữ partition và khiến record phía sau chờ. Kiểm tra thời gian listener, backoff, số lần retry và trạng thái dependency. Nếu chấp nhận thay đổi thứ tự, cân nhắc retry topic; nếu cần thứ tự, tối ưu xử lý và giới hạn thời gian retry.

### Container dừng sau một exception

Xem log và ConsumerStoppedEvent để biết nguyên nhân dừng. Phân biệt exception của listener với lỗi khởi tạo consumer, authorization, deserialization hoặc lỗi ứng dụng trong lifecycle. Xác định container có được cấu hình auto restart hay cần operator/application chủ động start lại.

### Record xuất hiện nhiều lần

Kiểm tra thời điểm commit offset, acknowledgement mode, shutdown/rebalance và lỗi xảy ra sau khi nghiệp vụ đã hoàn tất. Nếu database commit thành công nhưng offset chưa commit, record có thể được giao lại. Dùng event ID và inbox/unique constraint để chống hiệu ứng lặp.

### Consumer không dừng khi deploy

Kiểm tra listener đang chờ dependency hoặc future blocking, thời gian shutdown, callback stop và cấu hình transaction timeout. Không chờ vô hạn; hãy đặt deadline và để record chưa commit được xử lý lại sau restart.

### Poison pill làm partition không tiến lên

Record không thể deserialize hoặc luôn gây lỗi có thể khiến consumer retry cùng vị trí. Dùng ErrorHandlingDeserializer, phân loại lỗi và DLT để giữ record lỗi mà cho partition tiếp tục theo chính sách đã định. Giữ payload/header cần thiết để điều tra.

## 14. Checklist vận hành listener container

Khi triển khai một consumer Spring Kafka, hãy xác định:

- Container được tự động start hay được điều khiển bằng KafkaListenerEndpointRegistry?
- Listener có để exception truyền tới error handler khi cần retry không?
- Exception nào retry được và exception nào chuyển recovery/DLT?
- DefaultErrorHandler có số lần retry và backoff hữu hạn không?
- DLT có serializer, partition và quy trình xử lý lại phù hợp không?
- Ack mode có phù hợp với record listener hay batch listener không?
- Offset được commit sau khi nghiệp vụ hoàn tất không?
- Listener có idempotent để chịu được redelivery sau crash hoặc rebalance không?
- Nếu dùng transaction, AfterRollbackProcessor và transaction manager được cấu hình đúng không?
- Deserialization exception có được ErrorHandlingDeserializer xử lý không?
- Concurrency có phù hợp với số partition và năng lực dependency không?
- Pause/resume có điều kiện và cảnh báo rõ ràng không?
- Shutdown có deadline, callback và cách xử lý record chưa commit không?
- Lifecycle events, consumer lag, retry rate, DLT count và lỗi listener có được theo dõi không?

## 15. Mẫu cấu hình consumer cơ bản

Ví dụ sau kết hợp record acknowledgement, concurrency và error handler có retry hữu hạn:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      enable-auto-commit: false
      group-id: order-service
      auto-offset-reset: earliest
    listener:
      ack-mode: record
      concurrency: 3
      auto-startup: true
~~~

Factory và error handler có thể được cấu hình bằng Java như phần trên. Cần bảo đảm factory thực tế được endpoint sử dụng. Nếu dùng nhiều factory, chỉ định rõ containerFactory trên @KafkaListener.

Một listener đơn giản:

~~~java
@Component
public class OrderConsumer {

    private final OrderService orderService;

    public OrderConsumer(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "order-service",
            containerFactory = "kafkaListenerContainerFactory"
    )
    public void onOrder(OrderCreated event) {
        orderService.process(event);
    }
}
~~~

Nếu orderService.process ném exception, container chuyển lỗi tới DefaultErrorHandler. Handler retry theo backoff đã cấu hình; khi hết retry, recoverer chuyển record sang DLT. Nếu gửi DLT thành công và recovery được xem là hoàn tất, container có thể tiến offset theo chính sách error handler. Nếu recovery thất bại, lỗi có thể tiếp tục được truyền và record có thể được xử lý lại.

Trong thực tế, hãy kết hợp chính sách container với transaction database, idempotency và monitoring. Container quản lý việc tiêu thụ và vòng đời Kafka consumer; ứng dụng chịu trách nhiệm bảo vệ hiệu ứng nghiệp vụ qua retry, redelivery, shutdown và restart.
