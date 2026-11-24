# So sánh với Spring for Apache Kafka, Spring AMQP và Kafka Streams

Spring Cloud Stream, Spring for Apache Kafka, Spring AMQP và Kafka Streams đều có thể xuất hiện trong một hệ thống Spring xử lý sự kiện, nhưng chúng giải quyết những bài toán ở các lớp khác nhau. Spring Cloud Stream cung cấp mô hình hàm và lớp binding/binder để kết nối ứng dụng với nhiều broker. Spring for Apache Kafka và Spring AMQP cung cấp API tích hợp trực tiếp với Kafka hoặc AMQP. Kafka Streams là thư viện xử lý luồng dữ liệu có trạng thái trên Kafka.

Hiểu đúng ranh giới này giúp chọn công nghệ theo yêu cầu về broker, mô hình xử lý, khả năng kiểm soát và vận hành. Các công nghệ có thể phối hợp trong cùng hệ thống; chúng không phải bốn lựa chọn thay thế hoàn toàn cho nhau.

## 1. Xác định lớp công nghệ của từng giải pháp

### Spring Cloud Stream

Spring Cloud Stream là framework xây dựng ứng dụng hướng sự kiện. Ứng dụng khai báo các hàm nghiệp vụ bằng mô hình của Spring Cloud Function:

- `Supplier<T>` tạo và phát sinh dữ liệu.
- `Function<T, R>` nhận dữ liệu, xử lý rồi tạo kết quả.
- `Consumer<T>` nhận dữ liệu và thực hiện tác vụ, không phát đầu ra.

Spring Cloud Stream tạo binding cho đầu vào và đầu ra của hàm. Binding là tên logic trong ứng dụng; binder kết nối binding đó với tài nguyên cụ thể của broker, chẳng hạn topic Kafka, exchange và queue RabbitMQ hoặc topic/subscription của Pulsar. Nhờ vậy, phần lớn mã nghiệp vụ có thể giữ nguyên khi thay đổi broker, trong khi cấu hình binder và một số hành vi vận hành vẫn phải điều chỉnh.

Ví dụ, một hàm `Consumer<OrderCreated>` có thể nhận sự kiện đơn hàng từ Kafka hoặc RabbitMQ. Tên binding, destination và consumer group được cấu hình bên ngoài mã xử lý. Với một binder cụ thể, ứng dụng vẫn có thể sử dụng các thuộc tính riêng của broker khi cần.

### Spring for Apache Kafka

Spring for Apache Kafka, thường được dùng qua dependency `spring-kafka`, là lớp tích hợp trực tiếp giữa Spring và Apache Kafka. Nó cung cấp các API như `KafkaTemplate` để gửi bản tin, `@KafkaListener` để nhận bản tin, listener container, cấu hình consumer/producer, xử lý lỗi và hỗ trợ giao dịch Kafka.

Ứng dụng làm việc trực tiếp với khái niệm của Kafka: topic, partition, offset, key, consumer group và record. Đây là lựa chọn phù hợp khi hệ thống đã xác định dùng Kafka và cần kiểm soát chi tiết hành vi của client.

### Spring AMQP

Spring AMQP cung cấp mô hình lập trình Spring cho giao thức AMQP; trong ứng dụng Spring Boot, cách dùng phổ biến là kết hợp với RabbitMQ thông qua `spring-rabbit`. Các thành phần quen thuộc gồm `RabbitTemplate` để gửi, `@RabbitListener` để nhận, listener container và các cơ chế xác nhận bản tin.

Mô hình định tuyến của RabbitMQ xoay quanh exchange, queue và binding. Producer gửi bản tin tới exchange kèm routing key; exchange định tuyến bản tin tới một hoặc nhiều queue theo binding. Vì vậy, cách tổ chức luồng và bảo đảm giao nhận của RabbitMQ khác với mô hình log phân vùng của Kafka.

### Kafka Streams

Kafka Streams là thư viện xử lý luồng dữ liệu chạy trong ứng dụng Java và sử dụng Kafka làm nguồn, đích dữ liệu. Thư viện cung cấp các abstraction như `KStream`, `KTable`, phép biến đổi, lọc, tổng hợp, cửa sổ thời gian, join và state store.

Kafka Streams hướng tới xử lý liên tục, thường có trạng thái, trên các topic Kafka. Nó không phải một binder đa broker. Một ứng dụng Kafka Streams có thể được tích hợp với Spring Cloud Stream thông qua Kafka Streams binder, nhưng topology và API xử lý vẫn là đặc thù của Kafka Streams.

## 2. Spring Cloud Stream: hàm nghiệp vụ và binding

Giả sử dịch vụ kho cần nhận sự kiện đơn hàng mới và yêu cầu hệ thống giữ hàng:

```java
@Configuration
class InventoryFunctions {

    @Bean
    Consumer<OrderCreated> reserveInventory(InventoryService inventory) {
        return event ->
            inventory.reserve(event.orderId(), event.items());
    }
}
```

Với hàm `reserveInventory`, Spring Cloud Stream tạo binding đầu vào có tên `reserveInventory-in-0`. Có thể cấu hình binding như sau:

```yaml
spring:
  cloud:
    function:
      definition: reserveInventory
    stream:
      bindings:
        reserveInventory-in-0:
          destination: orders.created
          group: inventory-service
          content-type: application/json
          consumer:
            max-attempts: 3
```

Trong ví dụ này:

- `destination` chỉ tài nguyên đích trên broker. Tài nguyên cụ thể được binder diễn giải theo broker đang dùng.
- `group` xác định nhóm nhận có danh tính ổn định. Với Kafka binder, giá trị này được ánh xạ sang Kafka consumer group. Với Rabbit binder, nó tham gia xác định queue dành cho nhóm đăng ký.
- `content-type` hỗ trợ cơ chế chuyển đổi payload của Spring Cloud Stream. Nó không tự thay thế quy trình quản lý và kiểm tra phiên bản schema.
- `max-attempts` cấu hình số lần thử xử lý theo cơ chế retry của binding. Cách đưa bản tin lỗi vào dead-letter queue vẫn phụ thuộc binder và cấu hình broker.

Nếu dùng một binder khác, hàm nghiệp vụ có thể không cần thay đổi, nhưng destination, bảo đảm giao nhận, cấu hình retry, dead-letter, phân vùng và các giới hạn của broker vẫn cần được xem xét. Tính di động của binder là tính di động ở mức tích hợp và cấu hình chung, không có nghĩa mọi broker có cùng ngữ nghĩa.

## 3. Spring for Apache Kafka: kiểm soát trực tiếp Kafka

Khi cần làm việc trực tiếp với Kafka, có thể dùng listener và template:

```java
@Component
class InventoryKafkaListener {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    InventoryKafkaListener(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "inventory-service"
    )
    void onOrderCreated(OrderCreated event) {
        // Gọi nghiệp vụ giữ hàng
    }

    void publish(OrderCreated event) {
        kafkaTemplate.send(
            "orders.created",
            event.orderId(),
            event
        );
    }
}
```

Ở đây, mã ứng dụng chỉ rõ topic và consumer group. Producer truyền `orderId` làm key để Kafka có thể dùng key đó khi chọn partition theo cấu hình partitioner. Các bản tin có cùng key thường đi vào cùng partition, nhờ đó có thể giữ thứ tự tương đối trong partition.

Spring for Apache Kafka phù hợp khi cần:

- Chọn chế độ xác nhận offset, xử lý record hoặc batch và điều khiển listener container.
- Tùy chỉnh deserializer, serializer, partition assignment, concurrency và error handler.
- Dùng Kafka transactions, retry topic, dead-letter topic hoặc các khả năng Kafka cụ thể.
- Tích hợp sâu với Kafka mà không cần lớp binding đa broker.

Đổi lại, ứng dụng gắn chặt với Kafka. Nếu chuyển sang RabbitMQ hoặc Pulsar, phần producer, consumer và cấu hình liên quan phải được thiết kế lại theo API và ngữ nghĩa của broker mới.

## 4. Spring AMQP: định tuyến qua exchange và queue

Với RabbitMQ, producer thường gửi qua exchange và routing key. Consumer lắng nghe một queue đã được khai báo và liên kết với exchange:

```java
@Component
class InventoryRabbitListener {

    @RabbitListener(queues = "inventory.orders")
    void onOrderCreated(OrderCreated event) {
        // Gọi nghiệp vụ giữ hàng
    }
}

// Ví dụ gửi từ một thành phần có RabbitTemplate:
rabbitTemplate.convertAndSend(
    "orders",
    "order.created",
    event
);
```

Trong ví dụ, `orders` là exchange, `order.created` là routing key và `inventory.orders` là queue. Queue cần được khai báo và binding với exchange theo quy tắc định tuyến phù hợp. Nếu dùng Spring AMQP, đội phát triển có thể kiểm soát rõ exchange type, queue, binding, acknowledgement, prefetch, publisher confirm/return và dead-letter exchange.

Điểm khác biệt quan trọng là RabbitMQ thường phân phối bản tin từ queue tới các consumer đang đăng ký. Kafka lưu bản ghi trong partition và consumer đọc theo offset. Một queue RabbitMQ không tương đương trực tiếp với một Kafka topic hoặc partition; cách lưu giữ, đọc lại, định tuyến và mở rộng cũng khác nhau.

Spring AMQP phù hợp khi nghiệp vụ cần định tuyến linh hoạt qua exchange, nhiều queue nhận cùng một sự kiện, hoặc cần tận dụng mô hình hàng đợi của RabbitMQ. Nếu ứng dụng cần xử lý log sự kiện có khả năng đọc lại theo offset và phân vùng, Kafka thường phù hợp hơn.

## 5. Kafka Streams: xử lý luồng có trạng thái

Kafka Streams phù hợp với tác vụ cần biến đổi hoặc tổng hợp liên tục trên dữ liệu Kafka. Ví dụ, đếm số đơn hàng theo khách hàng:

```java
@Bean
Function<KStream<String, Order>,
         KStream<String, Long>> countOrdersByCustomer() {
    return orders -> orders
        .selectKey((key, order) -> order.customerId())
        .groupByKey()
        .count()
        .toStream();
}
```

Đoạn mã đổi key của mỗi record thành mã khách hàng, nhóm theo key, rồi tính số lượng. `count()` tạo một `KTable` biểu diễn kết quả tổng hợp; `toStream()` chuyển các thay đổi của bảng thành luồng đầu ra.

Một topology Kafka Streams có thể cần state store để lưu trạng thái tổng hợp, cửa sổ thời gian hoặc dữ liệu phục vụ join. Trạng thái có thể được phục hồi từ changelog topic do Kafka Streams quản lý. Ứng dụng cần cấu hình application id, Serde phù hợp cho key/value, số partition và tài nguyên Kafka. Số partition cùng cách chọn key ảnh hưởng trực tiếp tới khả năng song song hóa và tính đúng đắn của phép tổng hợp.

Nếu sử dụng Spring Cloud Stream Kafka Streams binder, có thể khai báo hàm nhận và trả về `KStream`, đồng thời cấu hình binding như các ứng dụng Spring Cloud Stream khác:

```yaml
spring:
  cloud:
    function:
      definition: countOrdersByCustomer
    stream:
      bindings:
        countOrdersByCustomer-in-0:
          destination: orders
        countOrdersByCustomer-out-0:
          destination: customer-order-counts
      kafka:
        streams:
          binder:
            application-id: order-analytics
```

Binder này giúp tích hợp topology với cơ chế binding và vòng đời ứng dụng Spring. Nó không biến Kafka Streams thành công cụ xử lý đa broker: topology vẫn dựa trên Kafka, KStream/KTable, Serde và state store. Cần phân biệt Kafka Streams binder với Kafka message-channel binder thông thường của Spring Cloud Stream. Binder thông thường chuyển bản tin vào/ra hàm; Kafka Streams binder đưa các kiểu và topology của Kafka Streams vào mô hình hàm.

## 6. Bảng so sánh

| Tiêu chí | Spring Cloud Stream | Spring for Apache Kafka | Spring AMQP | Kafka Streams |
|---|---|---|---|---|
| Vai trò chính | Framework hướng sự kiện, binding và binder | Tích hợp trực tiếp với Kafka | Tích hợp Spring với AMQP, thường là RabbitMQ | Thư viện xử lý luồng dữ liệu trên Kafka |
| Mô hình lập trình | Supplier, Function, Consumer và binding | KafkaTemplate, @KafkaListener, listener container | RabbitTemplate, @RabbitListener, exchange/queue | KStream, KTable, topology và state store |
| Broker | Có binder cho Kafka, RabbitMQ, Pulsar và các hệ được hỗ trợ | Kafka | Broker AMQP được adapter hỗ trợ; phổ biến nhất là RabbitMQ | Kafka |
| Mức độ phụ thuộc broker | Thấp hơn ở lớp nghiệp vụ; cấu hình và ngữ nghĩa vẫn phụ thuộc binder | Cao | Cao với mô hình AMQP và cấu hình broker | Rất cao, đặc thù Kafka |
| Xử lý trạng thái và cửa sổ | Không phải trọng tâm của binding thông thường | Có thể tự xây dựng hoặc kết hợp công cụ khác | Không phải trọng tâm | Tích hợp trực tiếp |
| Kiểm soát broker | Qua API chung và thuộc tính riêng của binder | Chi tiết Kafka | Chi tiết AMQP/RabbitMQ | Chi tiết xử lý luồng Kafka |
| Trường hợp phù hợp | Microservice cần mô hình hàm và khả năng đổi binder | Producer/consumer Kafka cần kiểm soát sâu | Ứng dụng cần định tuyến qua exchange và queue | Tổng hợp, join, window và xử lý sự kiện có trạng thái |

## 7. Những khác biệt cần kiểm tra khi triển khai

### Consumer group, queue và partition

Với Kafka, các consumer thuộc cùng một group chia nhau đọc partition. Tại một thời điểm, mỗi partition được gán cho tối đa một consumer trong group đó. Vì vậy, số partition giới hạn mức song song hữu ích của một group. Nhiều group khác nhau có thể đọc độc lập cùng một topic, mỗi group có offset riêng. Key và partitioning strategy quyết định bản tin được phân phối ra sao; thứ tự được bảo đảm trong phạm vi một partition.

Với RabbitMQ, exchange định tuyến bản tin tới queue; nhiều consumer cùng đọc một queue sẽ cạnh tranh nhận bản tin. Acknowledgement, prefetch, requeue và số consumer ảnh hưởng tới tốc độ cũng như thứ tự quan sát được. Tăng số consumer không tương đương tăng partition Kafka. Với Pulsar, subscription type như Exclusive, Failover, Shared hoặc Key_Shared tạo ra các quy tắc phân phối khác nhau. Do đó, thuộc tính `group` chung của Spring Cloud Stream không làm cho ngữ nghĩa nhóm nhận giữa các binder trở nên giống nhau.

### Message schema và chuyển đổi dữ liệu

Spring Cloud Stream có thể dùng `content-type` và message converter để chuyển payload giữa dạng byte và kiểu Java. Spring Kafka dùng serializer/deserializer hoặc message converter; Kafka Streams dùng Serde cho key và value; Spring AMQP dùng message converter cho payload AMQP.

Các cơ chế chuyển đổi này không tự giải quyết toàn bộ quản trị schema. Trong hệ thống nhiều dịch vụ, cần xác định schema cho sự kiện, quy tắc tương thích khi thêm hoặc đổi trường, cách xử lý dữ liệu cũ và cách triển khai phiên bản producer/consumer. Nếu dùng Avro, Protobuf hoặc JSON Schema, hãy cấu hình serializer/converter và schema registry phù hợp với broker, binder và phiên bản thư viện đang dùng. Không nên giả định rằng đặt `content-type: application/json` đã cung cấp kiểm tra schema hoặc bảo đảm tương thích phiên bản.

### Retry, dead-letter và xử lý lỗi

Spring Cloud Stream cung cấp một số cấu hình retry chung ở cấp binding, chẳng hạn số lần thử và backoff. Việc chuyển bản tin thất bại vào DLQ/DLT thường cần cấu hình riêng của binder. Spring for Apache Kafka có thể dùng error handler, retry topic và dead-letter topic. Với RabbitMQ, có thể cấu hình dead-letter exchange/queue và chính sách requeue. Kafka Streams có cơ chế xử lý lỗi riêng trong quá trình xây dựng topology và xử lý record.

Cần xác định rõ lỗi nào được retry, retry trong bao lâu, bản tin có bị chặn xử lý các bản tin sau hay không, và khi nào bản tin được đưa vào nơi lưu lỗi. Retry có thể làm một thao tác được thực hiện nhiều lần. Consumer nên có tính idempotent, ví dụ lưu event id đã xử lý hoặc dùng khóa nghiệp vụ duy nhất để tránh tạo đơn hàng hay trừ tồn kho lặp lại. DLQ cần có quy trình giám sát, phân loại nguyên nhân và phát lại có kiểm soát.

### Bảo đảm giao nhận và tính nhất quán

Một hệ thống event-driven thường phải thiết kế cho khả năng bản tin được giao lại. Kafka có offset và transaction; Spring for Apache Kafka hỗ trợ tích hợp transaction Kafka; Kafka Streams hỗ trợ chế độ xử lý exactly-once cho luồng đọc, xử lý và ghi trong phạm vi Kafka khi được cấu hình đúng. RabbitMQ có acknowledgement và publisher confirms để xác nhận các chặng giao nhận. Các cơ chế này có phạm vi và điều kiện khác nhau.

Không nên suy luận rằng bật một tùy chọn exactly-once sẽ làm cho Kafka, cơ sở dữ liệu và mọi API bên ngoài cùng nằm trong một giao dịch nguyên tử. Nếu consumer cập nhật cơ sở dữ liệu rồi mới xác nhận bản tin, sự cố giữa hai bước có thể khiến bản tin được giao lại. Các mẫu như transactional outbox, inbox/deduplication và xử lý idempotent giúp kiểm soát ranh giới giữa broker và cơ sở dữ liệu. Với Spring Cloud Stream, cần kiểm tra khả năng transaction và cấu hình thực tế của binder đang dùng; abstraction chung không tạo ra cùng một bảo đảm trên mọi broker.

### Kiểm thử

Nên chia kiểm thử thành nhiều lớp:

1. Unit test cho hàm nghiệp vụ, kiểm tra đầu vào, đầu ra, lỗi và tính idempotent.
2. Kiểm thử binding hoặc luồng hàm bằng Spring Cloud Stream Test Binder khi phù hợp. Cách này hữu ích để kiểm tra wiring và xử lý message ở mức ứng dụng, nhưng không chứng minh broker thật có cùng hành vi.
3. Integration test với broker thật thông qua Testcontainers hoặc môi trường kiểm thử tương đương để xác minh serialization, partition, acknowledgement, retry, DLQ và cấu hình bảo mật.
4. Với topology Kafka Streams, dùng `TopologyTestDriver` để kiểm tra phép biến đổi, window, join và state store; bổ sung kiểm thử tích hợp với Kafka khi cần xác minh hành vi triển khai.

## 8. Chọn giải pháp theo yêu cầu

- Chọn **Spring Cloud Stream** khi muốn chuẩn hóa ứng dụng thành các hàm Supplier/Function/Consumer, quản lý binding tập trung và có nhu cầu hỗ trợ nhiều broker. Trước khi chuyển binder, hãy rà soát các tính năng phụ thuộc broker như partition, DLQ, retry, transaction và schema.
- Chọn **Spring for Apache Kafka** khi Kafka là nền tảng đã xác định và ứng dụng cần kiểm soát listener, offset, transaction, retry hoặc cấu hình producer/consumer ở mức chi tiết.
- Chọn **Spring AMQP** khi hệ thống dùng RabbitMQ/AMQP và nghiệp vụ cần exchange, routing key, queue, acknowledgement, publisher confirm hoặc dead-letter exchange.
- Chọn **Kafka Streams** khi cần xử lý liên tục có trạng thái trên dữ liệu Kafka, chẳng hạn tổng hợp theo key, join luồng, window theo thời gian hoặc duy trì state store.

Có thể kết hợp các công nghệ theo ranh giới trách nhiệm. Ví dụ, các dịch vụ nghiệp vụ dùng Spring Cloud Stream để chuẩn hóa cách nhận và phát sự kiện; một dịch vụ cần cấu hình Kafka đặc thù dùng Spring for Apache Kafka; pipeline tổng hợp thời gian thực dùng Kafka Streams; một hệ thống tích hợp RabbitMQ dùng Spring AMQP. Điều quan trọng là mỗi luồng dữ liệu phải có chủ sở hữu rõ ràng cho schema, key, retry, DLQ, giao dịch, quan sát và phát lại sự kiện.

## 9. Checklist trước khi đưa vào production

- Xác định broker, phiên bản binder/client và phiên bản Spring Boot/Spring Cloud tương thích.
- Đặt tên destination, binding, consumer group hoặc queue nhất quán với trách nhiệm dịch vụ.
- Chọn key và số partition theo yêu cầu thứ tự, phân phối tải và khả năng mở rộng.
- Chuẩn hóa schema, quy tắc tương thích và chiến lược nâng cấp producer/consumer.
- Cấu hình retry, backoff, DLQ/DLT, cảnh báo và quy trình phát lại.
- Thiết kế consumer idempotent; xác định ranh giới transaction với cơ sở dữ liệu và dịch vụ ngoài.
- Kiểm thử với broker thật cho các hành vi phụ thuộc broker; theo dõi lag/offset của Kafka hoặc queue depth/unacked của RabbitMQ.
- Với Kafka Streams, kiểm tra application id, Serde, state store, changelog, partitioning và khả năng phục hồi sau khi instance khởi động lại.

Khi đánh giá một giải pháp, hãy bắt đầu từ mô hình dữ liệu và cách sự kiện cần được xử lý. Nếu chỉ cần chuyển sự kiện giữa các microservice, một binding với hàm Consumer hoặc Function có thể đủ. Nếu cần kiểm soát sâu broker, dùng API tích hợp trực tiếp. Nếu cần tính toán trạng thái liên tục trên log sự kiện, chọn Kafka Streams. Quyết định ở đúng lớp giúp giảm cấu hình thừa và làm rõ trách nhiệm vận hành của từng thành phần.

