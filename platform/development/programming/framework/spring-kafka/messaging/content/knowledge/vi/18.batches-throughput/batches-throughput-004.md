# BatchMessagingMessageConverter

Khi dùng batch listener trong Spring Kafka, một lần `poll()` có thể trả về nhiều `ConsumerRecord`. Ứng dụng có thể nhận trực tiếp danh sách record, hoặc để Spring chuyển danh sách đó thành một Spring `Message` có payload là danh sách giá trị và các header tương ứng. `BatchMessagingMessageConverter` đảm nhiệm bước chuyển đổi thứ hai.

Converter này đặc biệt hữu ích khi listener muốn nhận `List<OrderCreated>`, `Message<List<OrderCreated>>` hoặc `List<Message<OrderCreated>>` thay vì tự bóc tách từng `ConsumerRecord`. Nó cũng gom metadata như key, topic, partition, offset và timestamp thành các danh sách có cùng thứ tự với payload, giúp ứng dụng truy vết từng phần tử trong batch.

Điểm cần phân biệt: `BatchMessagingMessageConverter` chuyển đổi cách biểu diễn message trong Spring Kafka. Nó không quyết định số record được fetch, không tăng kích thước batch của Kafka producer và không tự tạo bảo đảm xử lý nguyên tử cho cả batch. Kích thước batch, tốc độ poll, commit và xử lý lỗi vẫn do consumer, listener container và chính sách ứng dụng quyết định.

## 1. BatchMessagingMessageConverter làm gì?

`BatchMessagingMessageConverter` là một implementation của `BatchMessageConverter`. Nó nhận danh sách `ConsumerRecord` từ listener container, trích value của từng record thành một collection payload, đồng thời ánh xạ metadata của từng record vào các Kafka headers trên Spring `Message`.

Ví dụ batch có ba record:

```text
ConsumerRecords trong một lần poll
  record 0: key=order-10, partition=0, offset=120, value=...
  record 1: key=order-11, partition=1, offset=88,  value=...
  record 2: key=order-12, partition=0, offset=121, value=...
                    |
                    v
       BatchMessagingMessageConverter
                    |
                    v
Message<List<OrderCreated>>
  payload: [event-10, event-11, event-12]
  RECEIVED_KEY:       [order-10, order-11, order-12]
  RECEIVED_PARTITION: [0, 1, 0]
  OFFSET:             [120, 88, 121]
```

Vị trí của một phần tử trong các header list tương ứng với vị trí của payload. Vì vậy `payload.get(1)`, `keys.get(1)`, `partitions.get(1)` và `offsets.get(1)` cùng mô tả record thứ hai trong batch.

Nếu truyền một `RecordMessageConverter` vào constructor, `BatchMessagingMessageConverter` dùng converter đó để chuyển từng record trước khi đưa value vào danh sách payload. Đây là cách hỗ trợ chữ ký như `List<OrderCreated>` khi Kafka consumer ban đầu nhận JSON dưới dạng `String`, `byte[]` hoặc `Bytes`.

## 2. Phân biệt các lớp chuyển đổi trong batch flow

Một batch message đi qua nhiều lớp. Mỗi lớp có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| Kafka `Deserializer` | Chuyển byte key/value thành kiểu Java mà consumer nhận được |
| `RecordMessageConverter` | Chuyển một `ConsumerRecord` thành Spring `Message` hoặc chuyển payload record sang kiểu đích |
| `BatchMessagingMessageConverter` | Chuyển danh sách `ConsumerRecord` thành một Spring `Message` có payload dạng collection và header dạng danh sách |
| `@KafkaListener` argument resolver | Đưa payload/header đã chuyển đổi vào tham số phương thức listener |
| Listener container | Quản lý poll, gọi listener, rebalance, acknowledgment và commit |

Ví dụ, nếu consumer dùng `StringDeserializer`, value của mỗi record là JSON string. `StringJsonMessageConverter` chuyển từng chuỗi JSON thành `OrderCreated`; `BatchMessagingMessageConverter` gom các object đó thành `List<OrderCreated>`.

```text
Kafka byte[]
    |
    v
StringDeserializer
    |
    v
String JSON trong ConsumerRecord
    |
    v
StringJsonMessageConverter (mỗi record)
    |
    v
OrderCreated
    |
    v
BatchMessagingMessageConverter (toàn batch)
    |
    v
Message<List<OrderCreated>> + batch headers
```

Nếu consumer đã dùng `JsonDeserializer<OrderCreated>` và nhận object `OrderCreated` ngay từ Kafka client, batch converter không cần parse JSON lần nữa. Khi đó có thể dùng `BatchMessagingMessageConverter` không truyền record converter để gom sẵn các value đã deserialize và header của chúng.

## 3. Bật batch listener trên container factory

Để listener nhận nhiều record trong một lần gọi, container factory phải bật batch mode bằng `setBatchListener(true)`. Sau đó cấu hình batch converter bằng `setBatchMessageConverter(...)`.

Ví dụ dưới đây dùng Spring Kafka 3.3.x, JSON được đọc thành `String` bởi Kafka client rồi chuyển thành object bằng `StringJsonMessageConverter`:

```java
@Configuration
public class KafkaBatchConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setBatchMessageConverter(
                new BatchMessagingMessageConverter(
                        new StringJsonMessageConverter()));
        factory.setConcurrency(3);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.BATCH);

        return factory;
    }
}
```

`setBatchListener(true)` quyết định listener container gọi phương thức theo batch. `setBatchMessageConverter(...)` đặt converter dùng để chuyển danh sách record thành Spring Message. `setConcurrency(3)` tạo tối đa ba consumer cho container; số consumer thực sự được gán partition còn phụ thuộc số partition và consumer group.

Nếu listener chỉ cần `List<ConsumerRecord<String, String>>`, có thể nhận trực tiếp danh sách record mà không cần batch message converter. Converter hữu ích khi muốn payload và headers theo mô hình Spring Messaging.

## 4. Cấu hình deserializer tương thích

Vì ví dụ trên dùng `StringJsonMessageConverter`, consumer cần nhận value dưới dạng `String`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-batch-reader
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        "[max.poll.records]": 300
    listener:
      type: batch
      ack-mode: batch
```

`max.poll.records` là giới hạn số record tối đa trả về trong một lần poll, không phải kích thước byte của batch. Trong cấu hình Java ở phần trước, `setBatchListener(true)` và `AckMode.BATCH` đã được đặt trực tiếp trên factory; nếu dùng cấu hình auto-configured của Spring Boot, `spring.kafka.listener.type: batch` và `ack-mode: batch` có thể dùng để cấu hình listener mặc định. Tránh cấu hình hai nơi với giá trị mâu thuẫn.

Nếu consumer dùng `JsonDeserializer<OrderCreated>` thay cho `StringDeserializer`, giá trị `ConsumerRecord` đã là `OrderCreated`. Khi đó cấu hình batch converter có thể đơn giản hơn:

```java
factory.setBatchListener(true);
factory.setBatchMessageConverter(new BatchMessagingMessageConverter());
```

Constructor không tham số của converter dùng converter record mặc định cho việc ánh xạ message (từ Spring Kafka 3.3.11); nó không tự biến một JSON string bất kỳ thành object nghiệp vụ. Muốn parse JSON từ `String`, hãy truyền `StringJsonMessageConverter` như ví dụ chính. Ở các phiên bản cũ hơn, constructor không tham số không có record converter mặc định; khi cần chuyển JSON, hãy truyền converter tường minh.

## 5. Nhận List<Foo> và các batch headers

Khi batch converter có `RecordMessageConverter`, listener có thể khai báo kiểu payload là collection có một tham số generic, ví dụ `List<OrderCreated>`. Spring dùng generic type đó làm kiểu đích cho từng record.

```java
@Component
public class OrderBatchListener {

    private final OrderService orderService;

    public OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-batch-reader",
            containerFactory = "batchKafkaListenerContainerFactory")
    public void onOrders(
            List<OrderCreated> events,
            @Header(KafkaHeaders.RECEIVED_KEY) List<String> keys,
            @Header(KafkaHeaders.RECEIVED_PARTITION) List<Integer> partitions,
            @Header(KafkaHeaders.OFFSET) List<Long> offsets) {

        for (int i = 0; i < events.size(); i++) {
            orderService.handle(
                    events.get(i), keys.get(i), partitions.get(i), offsets.get(i));
        }
    }
}
```

Các header list quan trọng:

| Header | Kiểu thường dùng trong batch listener | Ý nghĩa |
|---|---|---|
| `KafkaHeaders.RECEIVED_KEY` | `List<String>` | Key của từng record |
| `KafkaHeaders.RECEIVED_TOPIC` | `List<String>` | Topic của từng record |
| `KafkaHeaders.RECEIVED_PARTITION` | `List<Integer>` | Partition của từng record |
| `KafkaHeaders.OFFSET` | `List<Long>` | Offset của từng record |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | `List<Long>` | Timestamp của từng record |
| `KafkaHeaders.RECEIVED_TIMESTAMP_TYPE` | `List<String>` | Loại timestamp do Kafka trả về |

Các danh sách header được căn theo thứ tự payload. Hãy kiểm tra kích thước và sự hiện diện của header trước khi truy cập theo index nếu ứng dụng có custom converter hoặc header mapper. Không giả định toàn bộ record trong batch đến từ cùng một partition: một lần poll có thể chứa record từ nhiều partition.

## 6. Nhận Message<List<Foo>> để gom payload và headers

Nếu muốn nhận toàn bộ payload cùng Spring headers trong một tham số, listener có thể dùng `Message<List<OrderCreated>>`:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-reader",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrders(Message<List<OrderCreated>> message) {
    List<OrderCreated> events = message.getPayload();

    List<Long> offsets = message.getHeaders()
            .get(KafkaHeaders.OFFSET, List.class);
    List<Integer> partitions = message.getHeaders()
            .get(KafkaHeaders.RECEIVED_PARTITION, List.class);

    for (int i = 0; i < events.size(); i++) {
        process(events.get(i), partitions.get(i), offsets.get(i));
    }
}
```

Chữ ký này tiện khi cần đọc nhiều header, truy cập payload như một khối hoặc chuyển Spring Message sang tầng xử lý khác. Khi dùng kiểu generic `Message<List<OrderCreated>>`, converter vẫn cần suy ra kiểu phần tử từ generic type của payload.

## 7. Nhận List<Message<Foo>> để giữ header riêng từng record

Trong một số trường hợp, mỗi record cần được xử lý như một Spring Message độc lập, có payload và headers riêng. Có thể khai báo `List<Message<OrderCreated>>` nếu record converter hỗ trợ kiểu này:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-message-batch-reader",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrderMessages(List<Message<OrderCreated>> messages) {
    for (Message<OrderCreated> item : messages) {
        String key = item.getHeaders()
                .get(KafkaHeaders.RECEIVED_KEY, String.class);
        Integer partition = item.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = item.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);

        process(item.getPayload(), key, partition, offset);
    }
}
```

Cách này hữu ích khi từng record có header nghiệp vụ hoặc metadata khác nhau và code xử lý muốn nhận message hoàn chỉnh. Đổi lại, nó tạo thêm object `Message` cho từng record và có thể tăng chi phí cấp phát bộ nhớ so với `List<Foo>` kèm các header list.

Không nhầm `List<Message<Foo>>` với một `Message<List<Foo>>`: kiểu thứ nhất có message riêng cho từng record; kiểu thứ hai có một message duy nhất bao quanh cả batch.

## 8. Dùng RecordMessageConverter để chuyển từng record

Constructor `BatchMessagingMessageConverter(RecordMessageConverter)` cho phép chỉ định cách chuyển đổi từng record. Ví dụ JSON string sang POJO:

```java
@Bean
public BatchMessageConverter orderBatchMessageConverter() {
    RecordMessageConverter recordConverter =
            new StringJsonMessageConverter();
    return new BatchMessagingMessageConverter(recordConverter);
}
```

Khi listener khai báo `List<OrderCreated>`, converter lấy generic type `OrderCreated` rồi chuyển từng record value theo kiểu đó. Điều này giúp listener nhận object nghiệp vụ trong khi Kafka consumer vẫn dùng `StringDeserializer`.

Nếu producer gửi type header của Spring Kafka, JSON converter có thể dùng type mapper để xác định kiểu. Mặc định, kiểu đích thường được suy ra từ tham số listener (`INFERRED`). Khi cần ưu tiên type ID trong header, cấu hình type precedence thành `TYPE_ID` bằng API type mapper phù hợp với phiên bản. Cần bảo đảm type mapping/trusted packages có kiểm soát và producer/consumer thống nhất contract.

Việc suy ra kiểu từ tham số listener hoạt động rõ nhất khi `@KafkaListener` đặt trực tiếp trên method. Với class-level `@KafkaListener` kết hợp nhiều `@KafkaHandler`, Spring phải chuyển payload trước để chọn handler phù hợp; khi đó cần type metadata trong header hoặc cấu hình type mapper để chọn đúng kiểu.

Đối với Spring Kafka 4.x, các lớp JSON converter được đổi tên theo dòng Jackson 3, ví dụ `JacksonJsonMessageConverter` và các biến thể tương ứng. Các ví dụ `StringJsonMessageConverter` trong bài dùng API Spring Kafka 3.3.x. Hãy chọn converter khớp với major version của dự án.

## 9. Header mapping và raw ConsumerRecord

Batch converter ánh xạ Kafka record headers vào Spring Message headers. Nếu ứng dụng có header tùy chỉnh, có thể cấu hình `KafkaHeaderMapper` riêng:

```java
BatchMessagingMessageConverter converter =
        new BatchMessagingMessageConverter(new StringJsonMessageConverter());
converter.setHeaderMapper(new DefaultKafkaHeaderMapper());
```

Chỉ thay header mapper khi cần kiểm soát rõ loại header được truyền qua ranh giới Kafka/Spring. Một số header có thể là kiểu Java phức tạp; cần quy định mapping và serialization tương ứng để tránh lỗi khi producer và consumer khác ngôn ngữ hoặc khác phiên bản.

Nếu listener cần truy cập danh sách `ConsumerRecord` gốc sau khi converter tạo payload, bật raw record header:

```java
BatchMessagingMessageConverter converter =
        new BatchMessagingMessageConverter(new StringJsonMessageConverter());
converter.setRawRecordHeader(true);
```

Khi bật tùy chọn này, converter thêm `List<ConsumerRecord<?, ?>>` vào header `KafkaHeaders.RAW_DATA`. Listener có thể lấy header đó để đọc metadata gốc hoặc chuyển record sang một thành phần xử lý cần API Kafka. Các value/key trong `ConsumerRecord` vẫn là dữ liệu sau Kafka deserializer; raw record header không tự giữ lại byte gốc trước deserialize.

## 10. Batch converter không quyết định kích thước batch

`BatchMessagingMessageConverter` chỉ chuyển đổi các record container đã nhận từ consumer. Kích thước và nhịp batch được chi phối bởi các cấu hình Kafka consumer và tình trạng dữ liệu:

| Thuộc tính | Vai trò | Ảnh hưởng |
|---|---|---|
| `max.poll.records` | Số record tối đa trả về trong một lần poll | Giới hạn số phần tử của batch ở cấp consumer |
| `fetch.min.bytes` | Số byte broker cố gắng gom trước khi trả fetch response | Có thể tăng hiệu quả fetch ở tải cao, đổi lại thời gian chờ |
| `fetch.max.wait.ms` | Thời gian broker tối đa chờ để đáp ứng fetch khi chưa đủ dữ liệu | Ảnh hưởng độ trễ fetch khi tải thấp |
| `fetch.max.bytes` | Giới hạn byte của fetch response | Giới hạn dữ liệu fetch tổng thể |
| `max.partition.fetch.bytes` | Giới hạn byte fetch từ một partition | Ảnh hưởng lượng dữ liệu lấy từ từng partition |
| `max.poll.interval.ms` | Giới hạn khoảng cách giữa hai lần poll | Phải đủ lớn cho thời gian xử lý batch |
| `concurrency` | Số consumer của listener container | Tăng khả năng xử lý song song theo partition |

Batch có thể nhỏ hơn `max.poll.records` vì broker chưa có đủ record hoặc consumer chỉ được gán một số partition. Converter không gom thêm record từ lần poll kế tiếp và không chia một batch thành nhiều batch nhỏ.

Nếu listener xử lý một batch quá lâu, consumer có thể vượt `max.poll.interval.ms` và bị xem là không còn tiến triển. Hãy cân bằng `max.poll.records`, thời gian xử lý mỗi record, concurrency và timeout downstream. Tăng `max.poll.interval.ms` đơn thuần không giải quyết được hàng đợi bị nghẽn hoặc xử lý không giới hạn.

## 11. Batch có thể chứa nhiều partition

Một lần poll có thể trả về record của nhiều partition được gán cho cùng consumer. Các record trong mỗi partition vẫn có thứ tự offset, nhưng không có thứ tự toàn cục được bảo đảm giữa các partition.

Ví dụ batch:

```text
Index 0: partition 0, offset 10
Index 1: partition 1, offset 25
Index 2: partition 0, offset 11
Index 3: partition 2, offset 7
```

Không nên giả định offset tăng dần khi duyệt toàn batch. Nếu nghiệp vụ cần ordering theo aggregate, producer phải định tuyến các event của cùng aggregate vào cùng partition bằng key ổn định. Trong listener, dùng `RECEIVED_PARTITION` và `OFFSET` để truy vết đúng từng record.

Khi bật concurrency, mỗi child consumer xử lý tập partition được assign cho nó. Concurrency không làm cùng một partition được xử lý đồng thời bởi nhiều consumer trong cùng group. Tăng concurrency chỉ có tác dụng khi có đủ partition và downstream có khả năng chịu tải.

## 12. Xử lý lỗi chuyển đổi payload

Có nhiều loại lỗi có thể xảy ra trong batch pipeline:

| Loại lỗi | Xảy ra ở đâu? | Cách xử lý |
|---|---|---|
| Kafka deserialization error | Trước khi `poll()` trả record cho listener | Dùng `ErrorHandlingDeserializer`, kiểm tra exception header và error handler |
| Message conversion error | Khi `RecordMessageConverter` chuyển value sang kiểu listener yêu cầu | Kiểm tra `KafkaHeaders.CONVERSION_FAILURES` và xác định index lỗi |
| Business validation/processing error | Trong phương thức listener | Xác định record lỗi, ném `BatchListenerFailedException` nếu biết index, hoặc dùng chính sách retry batch phù hợp |

Khi record không chuyển đổi được bằng batch converter, phần tử tương ứng trong payload list có thể là `null`; exception được ghi nhận trong `KafkaHeaders.CONVERSION_FAILURES` theo cùng index. Listener nên kiểm tra header này trước khi xử lý payload để không nhầm `null` do lỗi conversion với tombstone hợp lệ.

Ví dụ phát hiện lỗi conversion:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-reader",
        containerFactory = "batchKafkaListenerContainerFactory")
public void onOrders(
        List<OrderCreated> events,
        @Header(KafkaHeaders.CONVERSION_FAILURES)
        List<ConversionException> conversionFailures) {

    for (int i = 0; i < events.size(); i++) {
        ConversionException failure = conversionFailures.get(i);
        if (failure != null) {
            throw new BatchListenerFailedException(
                    "Không chuyển đổi được record ở index " + i, failure, i);
        }

        process(events.get(i));
    }
}
```

`KafkaHeaders.CONVERSION_FAILURES` chứa danh sách lỗi theo từng phần tử; nếu không có lỗi ở một index, phần tử tương ứng là `null`. API này và kiểu exception cần đối chiếu phiên bản Spring Kafka đang dùng.

## 13. Deserialization error với ErrorHandlingDeserializer

Deserializer chạy trước khi listener container có thể gọi phương thức listener. Vì vậy, nếu deserializer ném exception, listener không thể bắt lỗi đó bằng `try/catch` thông thường trong vòng lặp payload.

Với batch listener, khi dùng `ErrorHandlingDeserializer`, lỗi deserialize được lưu trong record headers. Batch converter đưa các header chuyển đổi theo record vào `KafkaHeaders.BATCH_CONVERTED_HEADERS`, là danh sách map có index tương ứng với batch. Có thể kiểm tra exception header để xác định record lỗi.

Header `BATCH_CONVERTED_HEADERS` được tạo khi converter có `KafkaHeaderMapper` để ánh xạ native Kafka headers sang Spring headers. Nếu không có mapper, converter có thể giữ native headers trong `KafkaHeaders.NATIVE_HEADERS`; hãy kiểm tra cấu hình header mapper trước khi giả định `BATCH_CONVERTED_HEADERS` luôn tồn tại.

Ví dụ minh họa kiểm tra header và báo lỗi tại đúng index:

```java
@KafkaListener(topics = "orders.created", groupId = "order-batch-reader")
public void onOrders(
        List<OrderCreated> events,
        @Header(KafkaHeaders.BATCH_CONVERTED_HEADERS)
        List<Map<String, Object>> convertedHeaders) {

    for (int i = 0; i < events.size(); i++) {
        Map<String, Object> headers = convertedHeaders.get(i);
        Object deserFailure = headers.get(
                SerializationUtils.VALUE_DESERIALIZER_EXCEPTION_HEADER);

        if (deserFailure != null) {
            throw new BatchListenerFailedException(
                    "Không deserialize được record ở index " + i,
                    new IllegalStateException("Value deserialization failed"), i);
        }

        process(events.get(i));
    }
}
```

Ví dụ cấu hình consumer dùng `ErrorHandlingDeserializer` bọc `JsonDeserializer`:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.value.default.type]": com.example.orders.OrderCreated
        "[spring.json.trusted.packages]": com.example.orders
```

Trong trường hợp này Kafka client cố gắng deserialize JSON thành `OrderCreated`; nếu delegate thất bại, `ErrorHandlingDeserializer` giữ exception và raw bytes trong record headers để batch listener/error handler xử lý. Ngược lại, nếu dùng `StringDeserializer` cùng `StringJsonMessageConverter`, lỗi cú pháp JSON xảy ra ở bước message conversion và được phản ánh qua `KafkaHeaders.CONVERSION_FAILURES`.

Trong ứng dụng thực tế, nên chuyển header byte thành `DeserializationException` bằng API `SerializationUtils` tương ứng để ghi nguyên nhân và raw data vào log/DLT. Với lỗi key, kiểm tra thêm `SerializationUtils.KEY_DESERIALIZER_EXCEPTION_HEADER`. Khi dùng `DeadLetterPublishingRecoverer`, producer cần serializer xử lý được cả payload nghiệp vụ và `byte[]` gốc của record lỗi.

## 14. Xử lý một phần batch thất bại

Batch listener có thể xử lý nhiều record trong một lần gọi. Nếu record thứ ba thất bại sau khi hai record đầu đã xử lý thành công, ứng dụng cần cho container biết index nào bị lỗi để có thể retry/recover đúng phần còn lại.

Spring Kafka hỗ trợ `BatchListenerFailedException` để chỉ ra record lỗi theo index trong batch:

```java
@KafkaListener(topics = "orders.created", groupId = "order-batch-reader")
public void onOrders(List<OrderCreated> events) {
    for (int i = 0; i < events.size(); i++) {
        try {
            orderService.handle(events.get(i));
        } catch (TransientOrderException ex) {
            throw new BatchListenerFailedException(
                    "Xử lý order thất bại tại index " + i, ex, i);
        }
    }
}
```

Khi dùng batch-aware error handler như `DefaultErrorHandler`, index giúp framework xác định phần record đã xử lý và phần cần seek/retry hoặc recover. Nếu listener ném exception thông thường mà không chỉ rõ record lỗi, framework có thể phải retry toàn bộ batch theo fallback behavior. Điều này có thể làm các record trước đó được xử lý lại.

Không phải cứ ném `BatchListenerFailedException` là các side effect trước đó tự động rollback. Nếu listener đã ghi DB cho record đầu và record thứ hai rồi mới thất bại, hai thay đổi đó vẫn tồn tại trừ khi chúng nằm trong transaction phù hợp. Hãy dùng idempotency hoặc transaction cho side effect, và chỉ báo index chính xác khi ứng dụng biết record nào thất bại.

## 15. Acknowledgment và commit offset

Với batch listener, AckMode ảnh hưởng thời điểm container commit offset cho các record đã xử lý. `AckMode.BATCH` là lựa chọn phổ biến: container commit sau khi toàn bộ batch của lần poll được xử lý thành công. Nếu listener thất bại, error handler quyết định retry/recover và tiến độ commit theo chính sách batch.

Một số nguyên tắc:

- Không commit offset của cả batch trước khi xử lý xong nếu muốn tránh bỏ qua record lỗi.
- Khi dùng `MANUAL` hoặc `MANUAL_IMMEDIATE`, chỉ acknowledge sau khi batch hoặc phần công việc tương ứng đã hoàn tất theo thiết kế.
- Khi dùng `BatchListenerFailedException` cùng error handler hỗ trợ, cung cấp index đúng để framework có thể xử lý phần thành công và phần lỗi.
- Nếu listener xử lý song song, phải giữ được trạng thái hoàn tất theo partition và không commit vượt qua record còn đang chạy.

Ví dụ manual acknowledgment cho batch:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-batch-reader",
        containerFactory = "manualBatchListenerContainerFactory")
public void onOrders(
        List<OrderCreated> events,
        Acknowledgment acknowledgment) {

    orderService.handleBatchAndPersist(events);
    acknowledgment.acknowledge();
}
```

Factory của listener này cần được cấu hình AckMode `MANUAL` hoặc `MANUAL_IMMEDIATE` phù hợp. Chỉ gọi acknowledge sau khi công việc cần xác nhận đã hoàn tất. Nếu xử lý batch không nguyên tử và có thể thành công một phần, hãy xác định rõ cách lưu checkpoint và cách retry trước khi dùng manual ack.

## 16. Header list và dữ liệu null/tombstone

Trong compacted topic, record có key và value `null` có thể là tombstone để đánh dấu xóa key. Đây vẫn là record hợp lệ trong batch. Không nên bỏ mọi phần tử `null` mà không kiểm tra nguyên nhân.

Có ít nhất ba trường hợp cần phân biệt:

1. Value null có chủ đích từ producer, ví dụ tombstone.
2. Value null do `ErrorHandlingDeserializer` trả về khi deserialize thất bại, đi kèm exception header.
3. Payload null do `BatchMessagingMessageConverter` không chuyển đổi được, đi kèm `KafkaHeaders.CONVERSION_FAILURES`.

Hãy kiểm tra header lỗi trước khi quyết định cách xử lý null. Với tombstone, listener nên thực hiện nghiệp vụ xóa key; với lỗi deserialize/conversion, cần retry, DLT hoặc dừng theo chính sách lỗi.

## 17. Custom SmartMessageConverter và header mapper

Trong các phiên bản Spring Kafka hỗ trợ `setMessagingConverter(...)`, `BatchMessagingMessageConverter` có thể sử dụng `SmartMessageConverter` của Spring Messaging để chuyển payload theo content type hoặc quy tắc chuyển đổi tùy chỉnh. Tính năng này phù hợp khi ứng dụng cần chuyển đổi dựa trên `MessageHeaders.CONTENT_TYPE` hoặc muốn tái sử dụng conversion logic của Spring Messaging.

```java
BatchMessagingMessageConverter batchConverter =
        new BatchMessagingMessageConverter(new MessagingMessageConverter());
batchConverter.setMessagingConverter(mySmartMessageConverter);
factory.setBatchMessageConverter(batchConverter);
```

`setMessagingConverter` được bổ sung trong các phiên bản mới hơn (từ Spring Kafka 3.3.11). Nếu dự án dùng phiên bản cũ, hãy dùng `RecordMessageConverter` phù hợp hoặc nâng cấp thư viện trước khi gọi API này. Không cần thêm SmartMessageConverter nếu `StringJsonMessageConverter` đã đáp ứng kiểu payload.

## 18. Giới hạn ở chiều gửi

`BatchMessagingMessageConverter` được thiết kế cho chiều nhận batch listener. Dù interface `BatchMessageConverter` có phương thức `fromMessage(...)`, implementation này không hỗ trợ chuyển Spring `Message<?>` thành danh sách `ProducerRecord` và ném `UnsupportedOperationException` nếu gọi phương thức đó. Vì vậy, không dùng nó làm outbound converter cho `KafkaTemplate.send(Message<?>)`.

Nếu cần gửi nhiều record, hãy tạo từng `ProducerRecord` và gửi bằng `KafkaTemplate`/Kafka producer theo API phù hợp. Kafka producer tự gom các record theo partition thành network batch dựa trên `batch.size`, `linger.ms` và các cấu hình producer. Nếu nghiệp vụ yêu cầu nhiều record phải commit hoặc abort cùng nhau, dùng Kafka transaction; batch converter không cung cấp bảo đảm nguyên tử.

## 19. Kiểm thử BatchMessagingMessageConverter

Nên kiểm thử riêng conversion và toàn bộ batch listener flow.

### Unit test conversion

Kiểm tra converter tạo payload list đúng thứ tự, kiểu phần tử đúng, và header list có cùng số phần tử. Với JSON converter, thử payload hợp lệ, Unicode, field không tương thích và JSON hỏng. Nếu dùng custom header mapper, xác minh các header cần thiết được giữ lại.

### Integration test với Kafka thử nghiệm

Một bài kiểm thử tích hợp nên:

1. Khởi động broker thử nghiệm và tạo topic có nhiều partition.
2. Gửi nhiều record với key khác nhau để có dữ liệu ở nhiều partition.
3. Dùng batch listener factory có `setBatchListener(true)` và `BatchMessagingMessageConverter`.
4. Xác minh listener nhận một collection có payload và metadata tương ứng.
5. Kiểm tra `List<Foo>`, `Message<List<Foo>>` hoặc `List<Message<Foo>>` theo chữ ký cần dùng.
6. Gửi một record có JSON lỗi hoặc payload không deserialize được để kiểm tra conversion failure/deserialization failure.
7. Xác minh `BatchListenerFailedException` chỉ đúng index và error handler retry/recover theo thiết kế.
8. Kiểm tra commit offset sau batch thành công, batch lỗi và shutdown.

Ma trận kiểm thử gợi ý:

| Trường hợp | Kỳ vọng |
|---|---|
| Batch toàn record hợp lệ | Payload list đúng thứ tự và đủ phần tử |
| Batch có nhiều partition | Header partition/offset khớp với từng payload |
| JSON không hợp lệ | Conversion failure được nhận diện tại đúng index |
| Deserializer thất bại | Exception header/raw data được xử lý qua error handler |
| Một record nghiệp vụ thất bại | Retry/recover đúng record nếu index được cung cấp |
| Tombstone | Null có chủ đích được xử lý theo contract |
| Poll không có record | Listener container không gọi batch listener cho lần poll rỗng; không kỳ vọng nhận một `List` rỗng |
| Listener chạy concurrency | Mỗi consumer xử lý partition assignment của mình, không trộn state |

## 20. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Listener nhận từng record thay vì List | Factory chưa bật batch listener hoặc endpoint dùng factory khác | Kiểm tra `setBatchListener(true)` và `containerFactory` |
| Payload vẫn là String/byte[] | Chưa gắn `RecordMessageConverter` chuyển JSON sang kiểu đích | Cấu hình `BatchMessagingMessageConverter(new StringJsonMessageConverter())` hoặc deserializer POJO |
| Header là scalar thay vì List | Listener đang chạy record mode hoặc nhận kiểu tham số khác | Xác minh batch mode và chữ ký listener |
| Payload/header lệch index | Custom converter hoặc code xử lý tự lọc một list mà không lọc các list metadata cùng cách | Giữ quan hệ index hoặc chuyển sang `List<Message<Foo>>` |
| Một record lỗi làm retry toàn batch | Không cung cấp index lỗi hoặc error handler dùng fallback cho batch | Ném `BatchListenerFailedException` với index chính xác |
| `NullPointerException` khi xử lý phần tử null | Không phân biệt tombstone với conversion/deserialization failure | Kiểm tra `CONVERSION_FAILURES` và `BATCH_CONVERTED_HEADERS` |
| Batch quá lớn làm listener timeout | `max.poll.records` cao hoặc xử lý downstream chậm | Giảm batch, tăng năng lực xử lý hoặc điều chỉnh poll interval có căn cứ |
| Tăng concurrency nhưng không tăng throughput | Không đủ partition hoặc downstream là bottleneck | Kiểm tra assignment, lag, CPU và connection pool |

## Checklist trước khi đưa batch converter vào production

- Factory bật `setBatchListener(true)` và endpoint tham chiếu đúng factory.
- Chọn `BatchMessagingMessageConverter` cùng `RecordMessageConverter` tương thích với deserializer.
- Generic type của listener là collection có một kiểu phần tử rõ ràng.
- Header list được xử lý theo cùng index với payload.
- Hiểu batch có thể chứa record từ nhiều partition và không có thứ tự toàn cục.
- `max.poll.records`, `max.poll.interval.ms`, concurrency và thời gian xử lý được cân đối.
- Conversion failure và deserialization failure được phân biệt, có đường retry/DLT phù hợp.
- `BatchListenerFailedException` chỉ đúng index khi xử lý partial failure.
- Acknowledgment/commit chỉ diễn ra sau ranh giới xử lý đã xác định.
- Null/tombstone được phân biệt với null do lỗi conversion hoặc deserialization.
- Có metric cho batch size, thời gian xử lý, retry, DLT và consumer lag.
- Đã kiểm thử với batch nhiều partition, lỗi một phần, tombstone và nhiều consumer instance.

`BatchMessagingMessageConverter` giúp batch listener làm việc với payload và metadata theo mô hình Spring Messaging. Khi ghép đúng record converter, deserializer, header mapping và error handling, ứng dụng có thể xử lý nhiều record trong một lần gọi listener mà vẫn truy vết được từng record, kiểm soát partial failure và commit offset an toàn.
