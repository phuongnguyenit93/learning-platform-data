# Adapter giữa Kafka record và Spring Message

Spring Kafka kết nối hai mô hình dữ liệu: **Kafka record** ở tầng giao tiếp với broker và **Spring Message** ở tầng ứng dụng Spring. Adapter chuyển đổi giữa hai mô hình này để ứng dụng có thể làm việc với payload cùng metadata bằng API quen thuộc của Spring Messaging, trong khi Kafka vẫn nhận và phát các record theo giao thức của nó.

Hiểu ranh giới này giúp chọn đúng kiểu tham số cho `@KafkaListener`, gửi message bằng `KafkaTemplate`, truyền key và metadata, đồng thời phân biệt lỗi serialization với lỗi chuyển đổi message.

## 1. Vì sao cần adapter?

Kafka producer và consumer làm việc với record. Một record có key, value, headers, timestamp và thông tin vị trí như topic, partition, offset. Ứng dụng Spring thường muốn truyền một đối tượng nghiệp vụ cùng các header như correlation ID, event type hoặc thông tin định tuyến.

Spring Messaging biểu diễn dữ liệu dưới dạng `Message<T>` gồm hai phần:

- `payload`: nội dung chính, ví dụ một đối tượng `OrderCreated`.
- `headers`: metadata đi kèm payload, ví dụ topic, key, correlation ID hoặc thông tin truy vết.

Spring Kafka cung cấp adapter và bộ chuyển đổi để đưa dữ liệu qua lại giữa hai mô hình:

```mermaid
flowchart LR
    A[Ứng dụng Spring] --> B[Message payload + headers]
    B --> C[KafkaTemplate + RecordMessageConverter]
    C --> D[ProducerRecord]
    D --> E[Kafka Serializer]
    E --> F[Kafka Broker]
    F --> G[Kafka Deserializer]
    G --> H[ConsumerRecord]
    H --> I[RecordMessageConverter]
    I --> J[Spring Message]
    J --> K[@KafkaListener]
```

Ở chiều gửi, adapter tạo `ProducerRecord` từ `Message<?>` trước khi Kafka serializer chuyển key/value thành byte. Ở chiều nhận, Kafka deserializer tạo key/value từ byte trước; sau đó adapter có thể tạo `Message<?>` để listener xử lý. Adapter vì vậy là ranh giới tích hợp giữa Kafka API và Spring Messaging.

## 2. Phân biệt Kafka record và Spring Message

Hai kiểu dữ liệu có mục đích gần nhau nhưng không đồng nhất.

| Khái niệm | Kafka record | Spring Message |
|---|---|---|
| Nội dung | `value` | `payload` |
| Khóa định tuyến | `key` | Thường biểu diễn bằng header `KafkaHeaders.KEY` khi gửi |
| Metadata tùy chỉnh | Kafka `Headers` | `MessageHeaders` |
| Topic/partition | Thuộc tính của record | Có thể được biểu diễn qua các header Kafka chuyên dụng |
| Offset | Vị trí record trong partition | Header nhận như `KafkaHeaders.OFFSET` |
| Kiểu dữ liệu | `ProducerRecord<K,V>` hoặc `ConsumerRecord<K,V>` | `Message<T>` |

`ConsumerRecord<K,V>` còn cung cấp thông tin gốc như topic, partition, offset, timestamp, key, value và Kafka headers. `Message<T>` là envelope ở tầng Spring: payload có kiểu ứng dụng và metadata được truy cập qua `MessageHeaders`.

Kafka headers và Spring message headers cũng có khác biệt quan trọng. Kafka lưu header dưới dạng cặp tên và byte array; một record có thể có nhiều header trùng tên. `MessageHeaders` là một map theo tên header, giá trị có thể là đối tượng Java và mỗi tên chỉ có một giá trị. Vì thế, việc chuyển đổi header cần một chính sách ánh xạ; không thể giả định hai cấu trúc giữ nguyên mọi đặc tính của nhau.

## 3. Các thành phần thực hiện chuyển đổi

Spring Kafka có một số thành phần liên quan:

| Thành phần | Trách nhiệm |
|---|---|
| `KafkaTemplate<K,V>` | API gửi dữ liệu tới Kafka; hỗ trợ gửi record và gửi Spring `Message<?>` |
| `ProducerRecord<K,V>` | Record mà Kafka producer gửi tới broker |
| `ConsumerRecord<K,V>` | Record mà Kafka consumer nhận từ broker |
| `RecordMessageConverter` | Chuyển đổi giữa `Message<?>` và record Kafka ở cấp record |
| `MessagingMessageConverter` | Bộ chuyển đổi tích hợp Spring Messaging với Kafka record, bao gồm payload và header |
| `KafkaHeaderMapper` | Ánh xạ header giữa `MessageHeaders` và Kafka `Headers` |
| `KafkaHeaders` | Tập hợp tên header chuyên dụng mà Spring Kafka dùng cho metadata Kafka |

Với listener theo batch, Spring Kafka còn có `BatchMessageConverter` để chuyển đổi tập record thành message có payload dạng danh sách và metadata tương ứng.

`MessagingMessageConverter` là lựa chọn tích hợp thông thường khi ứng dụng muốn dùng Spring Message. Nếu cấu trúc payload hoặc metadata có quy tắc riêng, có thể cung cấp converter hoặc header mapper tùy chỉnh. Việc tùy chỉnh nên bắt đầu từ yêu cầu chuyển đổi cụ thể, chẳng hạn một định dạng payload đặc biệt hoặc quy tắc truyền correlation header giữa các dịch vụ.

## 4. Chiều nhận: ConsumerRecord thành Spring Message

Luồng nhận dữ liệu thường diễn ra theo thứ tự:

1. Kafka broker trả các byte của record cho consumer.
2. Kafka deserializer chuyển byte của key và value thành kiểu Java đã cấu hình.
3. Kafka client tạo `ConsumerRecord<K,V>` chứa payload đã deserialize cùng metadata của record.
4. Spring Kafka dùng `RecordMessageConverter` để tạo `Message<?>` nếu listener cần mô hình Spring Messaging.
5. Listener adapter phân giải payload và header thành tham số của phương thức `@KafkaListener`.

Ví dụ listener nhận toàn bộ Spring Message:

```java
@Component
public class OrderEventListener {

    @KafkaListener(
            topics = "orders",
            groupId = "order-read-model"
    )
    public void handle(Message<OrderCreated> message) {
        OrderCreated event = message.getPayload();

        String topic = message.getHeaders().get(
                KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders().get(
                KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders().get(
                KafkaHeaders.OFFSET, Long.class);
        Object key = message.getHeaders().get(KafkaHeaders.RECEIVED_KEY);

        // Xử lý event và dùng metadata để log/truy vết khi cần.
    }
}
```

Payload là `OrderCreated`; các thông tin định tuyến và vị trí được đọc qua header. Những header nhận thường dùng gồm:

| Header | Ý nghĩa |
|---|---|
| `KafkaHeaders.RECEIVED_TOPIC` | Topic chứa record vừa nhận |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition chứa record |
| `KafkaHeaders.OFFSET` | Offset của record |
| `KafkaHeaders.RECEIVED_KEY` | Key của record nhận được, nếu có |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp của record nhận được |

Tên và kiểu header nên được lấy từ hằng số `KafkaHeaders` của phiên bản Spring Kafka mà dự án đang dùng. Giá trị key có thể vắng mặt nếu producer gửi record không có key; listener nên xử lý trường hợp đó nếu key là tùy chọn.

### Chỉ nhận payload và các header cần thiết

Không phải listener nào cũng cần giữ cả đối tượng `Message<?>`. Có thể khai báo trực tiếp payload và các header cần dùng:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-audit"
)
public void audit(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset,
        @Header(name = KafkaHeaders.RECEIVED_KEY, required = false) String key) {

    // Ghi nhận event cùng tọa độ topic/partition/offset.
}
```

Kiểu này phù hợp khi phương thức chỉ cần một số trường metadata rõ ràng. `@Payload` chỉ ra dữ liệu nghiệp vụ; `@Header` yêu cầu Spring phân giải một header cụ thể. Nếu header có thể không tồn tại, đặt `required = false` hoặc dùng kiểu dữ liệu cho phép null.

### Khi cần ConsumerRecord gốc

Nếu listener cần thao tác trực tiếp với API Kafka hoặc cần nhiều thông tin record ở dạng gốc, có thể nhận `ConsumerRecord`:

```java
@KafkaListener(topics = "orders", groupId = "order-diagnostics")
public void inspect(ConsumerRecord<String, OrderCreated> record) {
    String topic = record.topic();
    int partition = record.partition();
    long offset = record.offset();
    String key = record.key();
    OrderCreated value = record.value();

    // Có thể đọc thêm timestamp và record.headers().
}
```

Chọn `Message<T>` khi ứng dụng muốn làm việc với payload và metadata theo mô hình Spring. Chọn `ConsumerRecord<K,V>` khi cần API Kafka đầy đủ hoặc cần xử lý header gốc. Hai cách nhận phục vụ những nhu cầu khác nhau; không nên chuyển qua `Message<?>` chỉ để lấy thêm một trường mà listener không dùng.

## 5. Chiều gửi: Spring Message thành ProducerRecord

`KafkaTemplate` hỗ trợ gửi một Spring `Message<?>`. Converter đọc payload và các header Kafka chuyên dụng để tạo `ProducerRecord`.

Ví dụ gửi một sự kiện đơn hàng:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event, String correlationId) {
        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader(KafkaHeaders.TOPIC, "orders")
                .setHeader(KafkaHeaders.KEY, event.orderId())
                .setHeader("correlationId", correlationId)
                .build();

        kafkaTemplate.send(message);
    }
}
```

Trong ví dụ:

- `KafkaHeaders.TOPIC` xác định topic đích.
- `KafkaHeaders.KEY` xác định key của record, dùng cho partitioner.
- `correlationId` là header nghiệp vụ do ứng dụng thêm vào để liên kết các thao tác qua nhiều dịch vụ.
- Payload `OrderCreated` trở thành value của `ProducerRecord` sau khi converter xử lý.

Có thể đặt thêm `KafkaHeaders.PARTITION` khi ứng dụng cần chỉ định partition cụ thể và đã có lý do nghiệp vụ hoặc vận hành rõ ràng. Nếu không chỉ định, partitioner của producer quyết định partition theo cấu hình và key. Không nên tự tính partition ở tầng nghiệp vụ nếu có thể để partitioner quản lý quy tắc định tuyến.

`KafkaTemplate` cũng có các overload gửi trực tiếp như `send(topic, key, value)`. Dùng overload này khi chỉ cần gửi payload, topic và key. Dùng `send(Message<?>)` khi muốn đóng gói payload cùng nhiều metadata trong một đối tượng Spring Message hoặc muốn tích hợp với các thành phần Spring Messaging khác.

## 6. Phân biệt converter với serializer và deserializer

Đây là điểm dễ nhầm khi cấu hình Spring Kafka. Converter và serializer/deserializer nằm ở hai ranh giới khác nhau.

| Thành phần | Chuyển đổi | Thời điểm |
|---|---|---|
| `RecordMessageConverter` | Spring `Message<?>` ↔ Kafka `ProducerRecord`/`ConsumerRecord` | Ở adapter Spring Kafka |
| Kafka `Serializer<K>` | Key hoặc value Java → byte | Trước khi producer gửi record |
| Kafka `Deserializer<K>` | Byte → key hoặc value Java | Sau khi consumer nhận record |
| `KafkaHeaderMapper` | Spring `MessageHeaders` ↔ Kafka `Headers` | Khi adapter ánh xạ metadata |

Ví dụ, nếu consumer đã cấu hình `JsonDeserializer<OrderCreated>`, value trong `ConsumerRecord` đã là đối tượng `OrderCreated`. `MessagingMessageConverter` có thể đưa đối tượng đó vào payload của `Message<OrderCreated>`. Converter không cần tự giải mã JSON lần nữa.

Nếu consumer dùng `StringDeserializer` hoặc `ByteArrayDeserializer`, payload sau bước Kafka deserialization vẫn là `String` hoặc `byte[]`. Muốn biến JSON trong payload thành `OrderCreated`, ứng dụng cần thêm một bước chuyển đổi JSON phù hợp, ví dụ một JSON message converter hoặc converter tùy chỉnh. Chỉ đổi kiểu tham số listener thành `Message<OrderCreated>` không tự bảo đảm byte/string được giải mã thành đúng POJO.

Chiều gửi cũng tương tự: `RecordMessageConverter` chuẩn bị record có key/value Java; Kafka serializer mới chuyển key/value thành byte. Vì vậy, cấu hình `KafkaTemplate<String, OrderCreated>` phải tương thích với producer serializer, còn kiểu key/value mà listener nhận phải tương thích với consumer deserializer.

Ví dụ cấu hình theo hướng dùng JSON serializer/deserializer của Spring Kafka:

```yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: "com.example.orders"
        spring.json.value.default.type: "com.example.orders.OrderCreated"
```

Đây là cấu hình minh họa cho một kiểu value cụ thể. Trong hệ thống có nhiều loại event, cần thiết kế type mapping hoặc cấu hình deserializer phù hợp thay vì mặc định mọi record đều là `OrderCreated`. Chỉ khai báo trusted packages cho các package mà ứng dụng thực sự tin cậy.

## 7. Ánh xạ header và truyền metadata

Header giúp mang theo thông tin phục vụ định tuyến, truy vết hoặc xử lý mà không cần nhúng mọi thứ vào payload. Ví dụ một event có thể có `correlationId`, `traceparent`, `tenantId` hoặc `eventType`.

Kafka lưu các header dưới dạng tên và byte array. Spring Message cho phép header mang giá trị Java. `KafkaHeaderMapper` chịu trách nhiệm chuyển đổi giữa hai biểu diễn. Spring Kafka thường dùng `DefaultKafkaHeaderMapper` cho việc ánh xạ header theo mô hình Spring Messaging.

Ví dụ ứng dụng gửi correlation ID:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, "orders")
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .setHeader("correlationId", correlationId)
        .setHeader("eventType", "OrderCreated")
        .build();

kafkaTemplate.send(message);
```

Listener nhận có thể đọc header nghiệp vụ:

```java
@KafkaListener(topics = "orders", groupId = "order-audit")
public void handle(Message<OrderCreated> message) {
    String correlationId = message.getHeaders().get(
            "correlationId", String.class);
    String eventType = message.getHeaders().get(
            "eventType", String.class);

    // Xử lý payload và metadata đã được ánh xạ.
}
```

Một số điểm cần nhớ khi thiết kế header:

- `KafkaHeaders.TOPIC`, `KEY`, `PARTITION` và `TIMESTAMP` là các header điều khiển mà converter dùng để tạo metadata của record. Chúng không đơn giản là header nghiệp vụ tùy chỉnh.
- `KafkaHeaders.RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `RECEIVED_KEY` và `OFFSET` là các header Spring Kafka cung cấp khi nhận record.
- Header tùy chỉnh như `correlationId` được ánh xạ sang Kafka headers theo cấu hình header mapper.
- Kafka cho phép nhiều header trùng tên; Spring `MessageHeaders` là map nên không thể biểu diễn đầy đủ nhiều giá trị cùng tên theo cùng cách.
- Không phải mọi header nội bộ của Spring đều nên truyền qua broker. Các header framework có thể được tạo lại ở phía nhận hoặc bị loại theo quy tắc mapper.

Nếu cần thay đổi cách ánh xạ, có thể cấu hình `KafkaHeaderMapper` tùy chỉnh hoặc điều chỉnh quy tắc của `DefaultKafkaHeaderMapper`. Hãy thống nhất tên, kiểu dữ liệu và định dạng header giữa producer và consumer, nhất là khi hai phía được viết bằng ngôn ngữ hoặc framework khác nhau. Với hệ thống đa ngôn ngữ, quy ước giá trị dạng byte/string hoặc JSON rõ ràng thường dễ liên thông hơn việc phụ thuộc vào metadata kiểu Java riêng của Spring.

## 8. Cấu hình converter cho listener container

Listener container có thể dùng `RecordMessageConverter` để chuyển đổi record nhận được thành Spring Message. Khi cần cấu hình rõ ràng, có thể gắn converter vào `ConcurrentKafkaListenerContainerFactory`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            orderKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setRecordMessageConverter(new MessagingMessageConverter());
        return factory;
    }
}
```

Listener dùng factory có tên tương ứng:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-read-model",
        containerFactory = "orderKafkaListenerContainerFactory"
)
public void handle(Message<OrderCreated> message) {
    // Xử lý Spring Message.
}
```

Để gửi `Message<?>`, có thể gắn converter tương ứng vào `KafkaTemplate` nếu ứng dụng muốn cấu hình rõ ràng:

```java
@Bean
KafkaTemplate<String, OrderCreated> orderKafkaTemplate(
        ProducerFactory<String, OrderCreated> producerFactory) {

    var template = new KafkaTemplate<>(producerFactory);
    template.setMessageConverter(new MessagingMessageConverter());
    return template;
}
```

Trong ứng dụng Spring Boot, hãy kiểm tra cách auto-configuration tạo `KafkaTemplate` và listener container trước khi khai báo bean riêng. Nếu chỉ cần hành vi mặc định, không cần tạo thêm factory hoặc template. Nếu đã có cấu hình factory riêng, bảo đảm listener trỏ đúng `containerFactory`; nếu không, converter vừa cấu hình có thể không được sử dụng.

## 9. Listener theo batch và header dạng danh sách

Với batch listener, một lần poll có thể trả nhiều record. Batch converter có thể chuyển chúng thành message có payload là danh sách:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-batch-reader",
        containerFactory = "batchKafkaListenerContainerFactory"
)
public void handleBatch(Message<List<OrderCreated>> message) {
    List<OrderCreated> events = message.getPayload();

    // Xử lý các event trong batch.
}
```

Metadata tương ứng với từng record có thể được biểu diễn bằng các danh sách header, tùy cấu hình và batch converter. Không nên đọc một header dạng đơn như thể nó luôn đại diện cho toàn bộ batch. Khi cần xử lý chính xác từng record cùng partition, offset hoặc key, hãy dùng cấu trúc header dạng danh sách được converter cung cấp hoặc nhận trực tiếp `List<ConsumerRecord<K,V>>` nếu cần dữ liệu record gốc.

Batch listener phù hợp khi muốn gom công việc hoặc tối ưu thao tác theo lô. Đổi lại, mã xử lý phải quản lý lỗi và tiến độ ở mức batch; một record lỗi có thể ảnh hưởng cách commit hoặc retry của cả batch theo cấu hình container và error handler.

## 10. Các lỗi thường gặp ở ranh giới adapter

**Thiếu topic khi gửi `Message<?>`:** converter cần biết topic đích từ header `KafkaHeaders.TOPIC` hoặc cấu hình topic mặc định của template. Kiểm tra cấu hình nếu lời gọi gửi không xác định được topic.

**Dùng nhầm header key ở chiều nhận:** khi gửi dùng `KafkaHeaders.KEY`; khi nhận nên đọc `KafkaHeaders.RECEIVED_KEY`. Dùng nhầm tên header có thể khiến listener nhận `null` dù record có key.

**Nhầm converter với deserializer:** converter không thay thế Kafka deserializer. Nếu consumer nhận `byte[]` hoặc `String`, hãy kiểm tra value deserializer trước khi điều tra converter.

**Payload không đúng kiểu:** generic `Message<OrderCreated>` không tự biến payload thành `OrderCreated`. Kiểm tra serializer/deserializer và bước chuyển đổi JSON nếu có.

**Header tùy chỉnh không tới được consumer:** kiểm tra header mapper, quy tắc lọc header và kiểu dữ liệu có thể chuyển thành byte hay không. Đồng thời kiểm tra tên header ở cả producer và consumer.

**Mất thông tin header trùng tên:** Kafka cho phép nhiều header cùng tên nhưng map Spring chỉ giữ một giá trị cho mỗi tên. Nếu nghiệp vụ cần nhiều giá trị, cần một quy ước biểu diễn khác hoặc đọc Kafka headers từ `ConsumerRecord`.

**Dùng sai metadata topic/partition/offset:** metadata nhận được là `RECEIVED_TOPIC`, `RECEIVED_PARTITION` và `OFFSET`. Các giá trị này mô tả record đã nhận, không phải metadata của lần gửi tiếp theo.

**Chuyển đổi thất bại trước khi vào listener:** lỗi deserialize hoặc message conversion có thể xảy ra trước khi phương thức listener được gọi. Khi điều tra, hãy tách log và metric theo giai đoạn: Kafka deserialization, record conversion, argument binding và xử lý nghiệp vụ.

## 11. Chọn cách nhận message phù hợp

| Cách nhận trong `@KafkaListener` | Khi nên dùng | Đặc điểm |
|---|---|---|
| `OrderCreated` | Chỉ cần dữ liệu nghiệp vụ | Gọn, ít phụ thuộc metadata Kafka |
| `Message<OrderCreated>` | Cần payload cùng nhiều header | Theo mô hình Spring Messaging |
| `@Payload` kết hợp `@Header` | Cần một số metadata xác định | Thể hiện rõ dependency của phương thức |
| `ConsumerRecord<String, OrderCreated>` | Cần Kafka record gốc | Truy cập trực tiếp topic, partition, offset, key và headers |
| `Message<List<OrderCreated>>` | Xử lý batch theo mô hình Spring Message | Payload là danh sách; header có thể là dữ liệu theo từng record |

Không có kiểu tham số tốt nhất cho mọi listener. Hãy bắt đầu từ thông tin mà nghiệp vụ thực sự cần. Nếu logic không phụ thuộc Kafka, nhận payload giúp phương thức dễ tái sử dụng và kiểm thử. Nếu logic cần correlation ID hoặc vị trí record, dùng `Message<T>` hoặc `@Header`. Chỉ giữ `ConsumerRecord` khi cần khả năng truy cập ở tầng Kafka.

## 12. Ví dụ luồng end-to-end

Giả sử dịch vụ đơn hàng phát `OrderCreated` và dịch vụ read model cập nhật màn hình đơn hàng. Producer gửi `orderId` làm key và `correlationId` làm header. Consumer nhận Spring Message để đọc payload, topic, partition, offset và correlation ID.

```java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event, String correlationId) {
        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader(KafkaHeaders.TOPIC, "orders")
                .setHeader(KafkaHeaders.KEY, event.orderId())
                .setHeader("correlationId", correlationId)
                .build();

        kafkaTemplate.send(message);
    }
}

@Component
public class OrderProjectionListener {

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void onMessage(Message<OrderCreated> message) {
        OrderCreated event = message.getPayload();
        String correlationId = message.getHeaders().get(
                "correlationId", String.class);
        String topic = message.getHeaders().get(
                KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders().get(
                KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders().get(
                KafkaHeaders.OFFSET, Long.class);

        // Cập nhật read model theo event.
        // Ghi log correlationId và tọa độ record để truy vết.
    }
}
```

Luồng dữ liệu có thể tóm tắt như sau:

1. Producer tạo Spring Message từ event và metadata.
2. `KafkaTemplate` cùng converter tạo `ProducerRecord`.
3. Kafka serializer chuyển key/value thành byte và producer gửi record.
4. Consumer nhận record; deserializer tạo key/value Java.
5. Spring Kafka chuyển record thành Spring Message cho listener.
6. Listener đọc payload và header để xử lý nghiệp vụ, log hoặc truy vết.

Ví dụ giả định producer và consumer thống nhất kiểu dữ liệu `OrderCreated` và cấu hình JSON serializer/deserializer tương thích. Trong hệ thống thực tế, hãy thống nhất schema, version event và định dạng header giữa các dịch vụ.

## 13. Checklist khi thiết kế adapter

- Payload Java được serializer/deserializer hai phía hỗ trợ và có schema tương thích.
- Phân biệt rõ converter, serializer, deserializer và header mapper.
- Producer đặt `KafkaHeaders.TOPIC` và `KafkaHeaders.KEY` đúng mục đích khi gửi `Message<?>`.
- Consumer đọc metadata nhận qua `RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `RECEIVED_KEY` và `OFFSET`.
- Header nghiệp vụ có tên, kiểu và định dạng thống nhất giữa các dịch vụ.
- Quy tắc header mapper được kiểm tra khi cần truyền correlation ID, trace context hoặc metadata tùy chỉnh.
- Listener chỉ nhận `ConsumerRecord` khi thực sự cần API Kafka ở mức thấp.
- Batch listener xử lý header theo từng record và hiểu rõ phạm vi commit/retry của batch.
- Có log hoặc metric để phân biệt lỗi deserialize, lỗi conversion, lỗi binding và lỗi nghiệp vụ.

Adapter giữa Kafka record và Spring Message cho phép ứng dụng dùng mô hình payload/header nhất quán trong hệ sinh thái Spring. Khi nắm rõ ranh giới chuyển đổi, nhóm phát triển có thể chọn đúng kiểu API, cấu hình đúng serializer và converter, đồng thời truyền metadata qua các dịch vụ một cách có kiểm soát.
