# Phân biệt khóa phân vùng của Stream với khóa bản ghi Kafka

Trong Spring Cloud Stream và Kafka, thuật ngữ “key” có thể chỉ hai khái niệm khác nhau. **Partition key của Spring Cloud Stream** là giá trị mà binder dùng để tính ra partition đích theo cấu hình phân vùng của framework. **Kafka record key** là trường key thực sự của một record Kafka, được lưu cùng value và được Kafka producer sử dụng khi chọn partition theo cơ chế native.

Hai giá trị này có thể cùng lấy từ `customerId`, nhưng chúng không tự động là một. Một message có thể dùng partition key để chọn partition mà không mang Kafka record key; ngược lại, message có Kafka record key nhưng không bật binder partitioning thì Kafka tự chọn partition. Hiểu rõ ranh giới này giúp giữ thứ tự theo khóa, hỗ trợ log compaction và tránh giả định sai khi đổi binder hoặc thay thuật toán phân vùng.

## 1. Hai loại key giải quyết hai việc khác nhau

### Partition key của Spring Cloud Stream

Spring Cloud Stream cung cấp cơ chế phân vùng chung cho output binding. Producer có thể khai báo `partitionKeyExpression` để trích một giá trị từ message. Framework dùng giá trị đó cùng `partitionCount` và partition selector để tính chỉ số partition đích.

Ví dụ, với các sự kiện đơn hàng, ứng dụng muốn mọi sự kiện của cùng khách hàng đi vào cùng một partition. Có thể trích `customerId` từ payload hoặc header:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: payload.customerId
            partition-count: 12
```

Khi bật binder partitioning, Spring Cloud Stream tính partition index trong khoảng từ `0` đến `partitionCount - 1`. Mặc định, framework sử dụng phép tính dựa trên `key.hashCode() % partitionCount`; có thể tùy chỉnh bằng `partitionSelectorExpression` hoặc bean triển khai `PartitionSelectorStrategy`.

Partition key ở đây là đầu vào cho thuật toán chọn partition. Nó không nhất thiết được ghi thành Kafka record key. Đây là abstraction của Spring Cloud Stream, được thiết kế để hỗ trợ mô hình partitioning chung cho các binder, kể cả middleware không có cơ chế partition native giống Kafka.

### Kafka record key

Kafka record có ba thành phần chính: topic, key và value, cùng metadata như partition, offset và timestamp. Record key là dữ liệu thực được lưu trong record. Kafka producer mặc định dùng key đã serialize để chọn partition khi ứng dụng không chỉ định partition cụ thể; record cùng key thường được định tuyến tới cùng partition theo partitioner đang cấu hình.

Trong Spring Cloud Stream Kafka binder, có thể đặt Kafka record key bằng header `KafkaHeaders.KEY`:

```java
Message<OrderPlaced> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.KEY, event.customerId())
    .build();
```

Kafka binder lấy header này làm key của Kafka record. Nếu không đặt record key và cũng không chỉ định partition, Kafka dùng partitioner mặc định của producer để chọn partition. Record key còn có ý nghĩa đối với consumer, các phép xử lý theo key và log compaction khi topic được cấu hình cleanup policy phù hợp.

Kafka record key là khái niệm đặc thù Kafka. Khi đổi sang RabbitMQ hoặc Pulsar, không thể giả định header `KafkaHeaders.KEY` có cùng ý nghĩa hoặc được binder khác sử dụng.

## 2. Bảng phân biệt nhanh

| Tiêu chí | Spring Cloud Stream partition key | Kafka record key |
|---|---|---|
| Thuộc lớp nào? | Abstraction phân vùng của Spring Cloud Stream | Mô hình record của Kafka |
| Dùng để làm gì? | Tính partition index thông qua partition selector | Lưu key trong record và tham gia chọn partition native |
| Cấu hình phổ biến | `partition-key-expression`, `partition-count` | `KafkaHeaders.KEY` hoặc Kafka binder `message-key-expression` |
| Có được lưu như key của Kafka record không? | Không tự động | Có |
| Phạm vi sử dụng | Có thể áp dụng qua nhiều binder, tùy khả năng binder | Chỉ có ý nghĩa với Kafka |
| Thuật toán mặc định | Spring Cloud Stream dùng hash của key theo partition count | Kafka producer dùng partitioner native trên key đã serialize |
| Ảnh hưởng đến log compaction | Không trực tiếp | Record key là yếu tố quan trọng cho compaction |
| Khi không cấu hình | Không bật binder partitioning | Kafka tự chọn partition; nếu không có key, partitioner xử lý record không key |

Không nên đặt tên một header tùy chỉnh là `partitionKey` rồi mặc định cho rằng Kafka sẽ lưu header đó làm record key. Muốn record có key, hãy thiết lập `KafkaHeaders.KEY` hoặc cấu hình Kafka binder `messageKeyExpression`.

## 3. Trường hợp A: chỉ dùng partition key của Spring Cloud Stream

Giả sử ứng dụng phát sự kiện đơn hàng và cần giữ các sự kiện của cùng khách hàng trên cùng partition. Tạo message có header riêng cho partition key:

```java
@Bean
Supplier<Message<OrderPlaced>> publishOrder() {
    return () -> {
        OrderPlaced event = nextOrderEvent();

        return MessageBuilder
            .withPayload(event)
            .setHeader("partitionKey", event.customerId())
            .build();
    };
}
```

Cấu hình output binding:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: headers['partitionKey']
            partition-count: 12
```

Framework đọc header `partitionKey`, tính partition index rồi binder gửi record tới partition đó. Trong ví dụ này, header `partitionKey` quyết định vị trí ghi. Nó không tự trở thành Kafka record key.

Với Kafka binder, nếu không cung cấp Kafka record key, record vẫn có thể được ghi vào partition do binder đã chọn, nhưng key của record có thể là `null`. Khi đó:

- Các sự kiện có cùng `partitionKey` có thể được binder định tuyến tới cùng partition theo thuật toán và số partition đã cấu hình.
- Consumer đọc được record từ partition đó.
- Ứng dụng không có Kafka record key tương ứng để dùng trực tiếp cho log compaction hoặc các xử lý downstream dựa trên record key.

Đây là một khác biệt quan trọng: chọn đúng partition không đồng nghĩa record đã có key.

## 4. Trường hợp B: chỉ dùng Kafka record key và partitioning native

Nếu chỉ triển khai trên Kafka, thường có thể để Kafka tự chọn partition bằng record key. Không khai báo `partition-key-expression`; thay vào đó, đặt `KafkaHeaders.KEY`:

```java
@Bean
Supplier<Message<OrderPlaced>> publishOrder() {
    return () -> {
        OrderPlaced event = nextOrderEvent();

        return MessageBuilder
            .withPayload(event)
            .setHeader(KafkaHeaders.KEY, event.customerId())
            .build();
    };
}
```

Kafka binder gửi `customerId` làm record key. Kafka producer partitioner chọn partition dựa trên key đã serialize và số partition hiện có của topic. Cấu hình này sử dụng partitioning native của Kafka.

Có thể dùng thuộc tính Kafka binder `messageKeyExpression` thay cho header key mặc định nếu muốn lấy key từ một header hoặc biểu thức khác:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              message-key-expression: headers['kafkaKey']
```

Khi dùng cách này, message cần có header `kafkaKey` với giá trị phù hợp. Nếu đã đặt `KafkaHeaders.KEY` theo quy ước của binder, thường không cần thêm `messageKeyExpression`. Tên constant có thể khác giữa các thế hệ Spring Kafka; hãy dùng constant được tài liệu của phiên bản dependency đang dùng chỉ định.

Với Kafka native partitioning:

- Kafka record key được lưu trong record.
- Kafka producer chọn partition theo partitioner đang cấu hình.
- Các record cùng key thường vào cùng partition khi số partition và thuật toán không đổi.
- Consumer group nhận partition theo cơ chế assignment của Kafka; không cần cấu hình binder partitioning riêng chỉ để Kafka sử dụng record key.

## 5. Trường hợp C: dùng cả hai key

Có thể cần đồng thời hai hành vi:

1. Spring Cloud Stream quyết định chính xác partition index bằng thuật toán chung của ứng dụng.
2. Kafka record vẫn mang key nghiệp vụ để consumer và log compaction sử dụng.

Khi đó, đặt cả header partition key và Kafka record key:

```java
@Bean
Supplier<Message<OrderPlaced>> publishOrder() {
    return () -> {
        OrderPlaced event = nextOrderEvent();
        String customerId = event.customerId();

        return MessageBuilder
            .withPayload(event)
            .setHeader("partitionKey", customerId)
            .setHeader(KafkaHeaders.KEY, customerId)
            .build();
    };
}
```

Cấu hình binder partitioning:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            partition-key-expression: headers['partitionKey']
            partition-count: 12
```

Trong trường hợp này:

- Spring Cloud Stream dùng `partitionKey` để tính partition index.
- Kafka binder gửi record tới partition được chỉ định bởi kết quả binder partitioning.
- `KafkaHeaders.KEY` cung cấp key thực của record Kafka.

Khi partition đã được chỉ định tường minh, Kafka không cần tự chọn partition bằng record key cho record đó. Record key vẫn được lưu và có thể được dùng bởi consumer hoặc log compaction. Nếu hai giá trị khác nhau, record vẫn có thể được ghi tới partition do partition key quyết định trong khi record key lưu một giá trị khác. Chỉ làm vậy khi có lý do rõ ràng; thông thường nên dùng cùng một khóa nghiệp vụ để tránh gây khó hiểu.

## 6. Vì sao cùng một giá trị có thể ra partition khác nhau?

Giả sử cả hai chế độ đều dùng chuỗi `customer-42` và topic có 12 partition.

Với Spring Cloud Stream binder partitioning, phép tính mặc định dựa trên `key.hashCode() % partitionCount`. Với Kafka native partitioning, Kafka producer dùng partitioner của Kafka trên key đã serialize. Hai thuật toán không được bảo đảm giống nhau. Vì vậy, cùng chuỗi key có thể được ghi vào partition khác nhau khi ứng dụng chuyển giữa hai chế độ.

Điều này đặc biệt quan trọng khi:

- Hai producer khác nhau cùng ghi một topic nhưng một producer dùng binder partitioning, producer kia dùng Kafka native partitioning.
- Một ứng dụng chuyển từ Spring Cloud Stream binder partitioning sang Kafka Streams hoặc KafkaTemplate.
- Hệ thống dùng nhiều producer viết bằng Java, Python hoặc ngôn ngữ khác.
- Ứng dụng cần bảo đảm các sự kiện của cùng aggregate được xử lý theo một thứ tự nhất quán.

Nếu nhiều producer cần đưa cùng một key vào cùng partition, hãy thống nhất cơ chế phân vùng: dùng Kafka native partitioning với cùng kiểu key, serializer và partitioner, hoặc chủ động cấu hình một thuật toán chung. Không chỉ thống nhất chuỗi key rồi mặc định partition sẽ giống nhau.

## 7. Số partition và ảnh hưởng đến thứ tự

Partition key chỉ có ý nghĩa trong tương quan với thuật toán chọn partition và số partition. Khi số partition thay đổi, phép tính modulo hoặc partitioner native có thể định tuyến key sang partition khác.

Ví dụ, một khóa có thể được đưa vào partition 2 khi topic có 6 partition nhưng chuyển sang partition khác khi topic được mở rộng lên 12 partition. Các record cũ vẫn nằm ở partition cũ; record mới có thể nằm ở partition mới. Do đó, thứ tự theo key qua thời điểm mở rộng partition không còn được bảo đảm như một chuỗi duy nhất trên cùng partition.

Trước khi tăng số partition, hãy đánh giá:

- Yêu cầu thứ tự theo customer, order hoặc aggregate ID.
- Khả năng consumer xử lý dữ liệu cùng aggregate từ nhiều partition.
- Kế hoạch chuyển đổi hoặc chấp nhận ranh giới thứ tự.
- Tương thích giữa thuật toán partition của tất cả producer.

Trong Kafka, thứ tự chỉ được bảo đảm trong phạm vi một partition. Cùng key được định tuyến ổn định vào cùng partition là cách phổ biến để duy trì thứ tự theo thực thể, nhưng không tạo ra thứ tự toàn cục giữa tất cả partition.

## 8. Partition key và record key trong các binder khác

Spring Cloud Stream cung cấp partitioning abstraction để ứng dụng có thể diễn đạt cách phân phối message mà không phụ thuộc hoàn toàn vào một broker. `partitionKeyExpression` có thể dùng cho Kafka, RabbitMQ hoặc binder khác nếu binder hỗ trợ partitioning.

Kafka record key lại gắn với `ProducerRecord` và partitioner của Kafka. Header `KafkaHeaders.KEY` và thuộc tính Kafka binder `messageKeyExpression` không phải cấu hình chung cho RabbitMQ hoặc Pulsar.

| Nền tảng | Partitioning abstraction của Stream | Key native của broker |
|---|---|---|
| Kafka | Binder có thể tính partition index từ `partitionKeyExpression`; Kafka cũng có partitioning native | Kafka record key |
| RabbitMQ | Binder có thể ánh xạ partition sang queue hoặc cấu trúc tương ứng theo binder | Không có Kafka-style record key; exchange/routing key và queue binding đảm nhiệm định tuyến |
| Pulsar | Binder có thể ánh xạ phân vùng theo khả năng hỗ trợ | Message key của Pulsar, dùng cho routing/ordering theo cấu hình Pulsar |

Khi viết ứng dụng đa broker, nên đặt tên header chung như `partitionKey` cho ý định phân vùng ở lớp ứng dụng. Phần adapter hoặc binder-specific configuration chịu trách nhiệm ánh xạ nó sang khả năng của broker. Tránh để service nghiệp vụ phụ thuộc trực tiếp vào `KafkaHeaders.KEY` nếu service đó cần chạy trên nhiều broker.

## 9. Kiểm tra partition và record key ở consumer

Để xác minh hành vi, consumer Kafka có thể đọc metadata partition nhận được:

```java
@Bean
Consumer<Message<OrderPlaced>> inspectOrder() {
    return message -> {
        OrderPlaced event = message.getPayload();

        Integer partition = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);

        log.info(
            "Order {} for customer {} arrived on partition {}",
            event.orderId(),
            event.customerId(),
            partition
        );
    };
}
```

Header `KafkaHeaders.RECEIVED_PARTITION` cho biết partition record được đọc. Đây là metadata nhận từ Kafka binder, không phải partition key gốc của Spring Cloud Stream. Nếu cần kiểm tra record key, hãy đọc key theo API/header mà phiên bản Spring Kafka binder hỗ trợ hoặc dùng Kafka consumer client trong integration test.

Một chiến lược kiểm thử hữu ích:

1. Unit test biểu thức hoặc bean trích partition key, xác minh các message cùng customer có cùng giá trị key.
2. Test cấu hình output binding có đúng `partition-key-expression` và `partition-count`.
3. Integration test với Kafka thật, phát nhiều record cùng key và đọc lại partition metadata.
4. Kiểm tra Kafka record key riêng biệt, không suy ra record key từ partition index.
5. Thử producer thứ hai dùng Kafka native partitioning để xác minh sự khác nhau nếu hệ thống có nhiều kiểu producer.

Spring Cloud Stream Test Binder có thể kiểm tra function và binding trong bộ nhớ, nhưng không mô phỏng chính xác partitioner native của Kafka. Để xác minh record key và partition thực tế, cần integration test với Kafka hoặc môi trường tương đương.

## 10. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ đặt header `partitionKey` và kỳ vọng Kafka record có key | Record có thể được ghi đúng partition nhưng key vẫn null | Đặt thêm `KafkaHeaders.KEY` hoặc `messageKeyExpression` |
| Chỉ đặt `KafkaHeaders.KEY` nhưng kỳ vọng Spring binder partition selector chạy | Kafka tự chọn partition; không áp dụng thuật toán partition selector của Stream | Cấu hình `partition-key-expression` và `partition-count` nếu cần binder partitioning |
| Dùng `partitionCount` mà không kiểm tra số partition thật của topic | Binder có thể không provision đủ partition hoặc cấu hình không khớp | Quản lý topic và xác minh số partition trước khi triển khai |
| Dùng thuật toán khác nhau ở các producer | Cùng key có thể rơi vào các partition khác nhau | Thống nhất partitioner, serializer và cấu hình |
| Tăng số partition mà không đánh giá thứ tự | Sự kiện cùng aggregate có thể được ghi vào partition khác sau thay đổi | Lập kế hoạch thay đổi partition và kiểm thử thứ tự |
| Dùng Kafka-specific header trong service đa broker | Mã nghiệp vụ phụ thuộc Kafka | Dùng metadata chung ở lớp ứng dụng và ánh xạ tại adapter |

## 11. Checklist lựa chọn

- Xác định mục tiêu là chọn partition, lưu record key, hay cần cả hai.
- Nếu cần Spring Cloud Stream binder partitioning, cấu hình `partition-key-expression` hoặc `partition-key-extractor-name` cùng `partition-count`.
- Nếu cần Kafka native partitioning, không bật binder partition expression và đặt Kafka record key bằng `KafkaHeaders.KEY` hoặc `message-key-expression`.
- Nếu cần cả hai, cấu hình riêng từng giá trị và thống nhất chúng khi cùng đại diện một aggregate/customer.
- Không giả định thuật toán hash của Spring Cloud Stream giống Kafka producer partitioner.
- Giữ số partition và thuật toán nhất quán giữa các producer.
- Xem xét tác động của việc tăng partition tới thứ tự theo key.
- Kiểm tra partition metadata và record key bằng Kafka integration test.
- Giữ mã nghiệp vụ độc lập với Kafka-specific headers khi cần hỗ trợ nhiều binder.

## 12. Tài liệu tham khảo

- [Spring Cloud Stream Reference — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html), phần cấu hình output binding và partition selector.
- [Spring Cloud Stream Kafka Binder — Partitioning with the Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html), phần phân biệt binder partitioning với Kafka native partitioning và `KafkaHeaders.KEY`.
- [Spring Cloud Stream Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html), phần producer properties `partitionKeyExpression`, `partitionCount` và partition selector.

Partition key của Spring Cloud Stream quyết định cách framework tính partition đích; Kafka record key là key thực được lưu trong record và tham gia cơ chế phân vùng native của Kafka. Khi cần tính di động giữa broker, dùng abstraction partitioning của Stream. Khi cần các khả năng đặc thù Kafka như record key và log compaction, cấu hình Kafka record key riêng. Nếu dùng cả hai, hãy xác định rõ giá trị nào quyết định partition và giá trị nào được lưu trong record để producer, consumer và hệ thống vận hành có cùng cách hiểu.

