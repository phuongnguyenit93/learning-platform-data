# Gửi Message<?> qua KafkaTemplate

## Mục tiêu của bài học

Trong chương **KafkaTemplate**, bài này hướng dẫn gửi một Spring Messaging Message<?> bằng KafkaTemplate. Cách gửi này cho phép đóng gói payload cùng metadata trong headers, sau đó Spring Kafka chuyển đổi message thành Kafka ProducerRecord để producer gửi tới broker.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Trong luồng đó, KafkaTemplate là API producer phía Spring; phương thức send(Message<?>) hữu ích khi một sự kiện cần mang theo key, topic, partition, timestamp hoặc metadata phục vụ tracing và tích hợp.

Sau bài học, người học có thể:

- Phân biệt Spring Message<?> với Kafka ProducerRecord và payload nghiệp vụ.
- Tạo Message bằng MessageBuilder và đặt các Kafka headers cần thiết.
- Gửi message bằng KafkaTemplate.send(Message<?>).
- Hiểu cách Spring Kafka ánh xạ topic, key, partition, timestamp và custom headers.
- Cấu hình serializer phù hợp với kiểu payload.
- Xử lý kết quả bất đồng bộ và lỗi gửi.
- Kiểm thử cả payload lẫn metadata của Kafka record.

## 1. Message<?> là gì?

Spring Messaging định nghĩa abstraction Message<T> để đóng gói hai phần:

- **Payload:** dữ liệu chính mà ứng dụng muốn truyền.
- **Headers:** metadata đi kèm message, chẳng hạn loại nội dung, correlation ID, thông tin nguồn hoặc các thuộc tính điều khiển việc gửi.

Ví dụ một message biểu diễn sự kiện đơn hàng:

~~~text
Payload:
{
  "orderId": "order-10001",
  "customerId": "customer-20001",
  "total": 1250000
}

Headers:
topic       = commerce.order.created
key         = order-10001
trace-id    = trace-7f31
contentType = application/json
~~~

Payload mô tả sự kiện nghiệp vụ. Headers mang thông tin định tuyến hoặc metadata mà producer, consumer và hệ thống quan sát có thể sử dụng.

Message<?> là abstraction của Spring, không phải bản ghi Kafka. Khi gửi message qua KafkaTemplate, Spring Kafka chuyển đổi nó thành ProducerRecord<K, V>, sau đó Kafka producer serialize key/value và gửi record tới broker.

~~~mermaid
flowchart LR
    A["Message<?>"] --> B["MessagingMessageConverter"]
    B --> C["ProducerRecord<K, V>"]
    C --> D["Kafka Serializer"]
    D --> E["Kafka Broker"]
    A1["Payload"] --> B
    A2["Headers"] --> B
~~~

Vì vậy, cần phân biệt ba lớp:

| Thành phần | Vai trò |
|---|---|
| Spring Message<?> | Đóng gói payload và headers trong ứng dụng Spring |
| Kafka ProducerRecord<K, V> | Biểu diễn bản ghi Kafka gồm topic, partition, key, timestamp, headers và value |
| Kafka serialized record | Dữ liệu key/value đã được serializer chuyển thành byte để gửi qua Kafka protocol |

## 2. Khi nào nên dùng send(Message<?>)?

KafkaTemplate cung cấp nhiều overload để gửi record. Các overload nhận topic, key và value thường phù hợp khi chỉ cần truyền dữ liệu cơ bản:

~~~java
kafkaTemplate.send(topic, key, value);
~~~

Dùng send(Message<?>) khi muốn đóng gói thông tin gửi trong một đối tượng Spring Message:

- Muốn đưa topic và key vào headers.
- Muốn truyền correlation ID hoặc trace ID cùng sự kiện.
- Muốn gắn metadata theo chuẩn Spring Messaging.
- Muốn truyền một message qua nhiều lớp xử lý mà không phải truyền riêng payload và từng tham số metadata.
- Muốn tận dụng MessageBuilder để tạo message bất biến sau khi build.

Nếu chỉ gửi một payload đơn giản và không cần metadata, overload send(topic, key, value) thường ngắn gọn hơn. Khi cần headers hoặc tích hợp với Spring Messaging, send(Message<?>) giúp gom dữ liệu và metadata vào cùng một đối tượng.

## 3. Các Kafka headers quan trọng

Spring Kafka cung cấp các hằng số trong KafkaHeaders để ánh xạ header của Spring Message sang trường tương ứng của Kafka ProducerRecord.

| Header | Kiểu giá trị thường dùng | Ý nghĩa |
|---|---|---|
| KafkaHeaders.TOPIC | String | Tên topic đích |
| KafkaHeaders.KEY | Kiểu K của KafkaTemplate | Record key |
| KafkaHeaders.PARTITION | Integer | Partition đích được chỉ định |
| KafkaHeaders.TIMESTAMP | Long | Timestamp của record |
| Header tùy chỉnh | String, byte[] hoặc kiểu được mapper hỗ trợ | Metadata như trace ID, source hoặc correlation ID |

Với send(Message<?>), hãy cung cấp KafkaHeaders.TOPIC để xác định topic đích, trừ khi ứng dụng đã cấu hình default topic và sử dụng cơ chế gửi mặc định tương ứng.

Các header định tuyến có vai trò khác nhau:

- **TOPIC** xác định luồng dữ liệu.
- **KEY** tham gia quyết định partition theo partitioner và giúp nhóm các record liên quan.
- **PARTITION** chỉ định trực tiếp partition khi ứng dụng có lý do rõ ràng.
- **TIMESTAMP** cung cấp timestamp cho record; cách broker sử dụng timestamp còn phụ thuộc cấu hình timestamp type.

Không nhầm các header đầu ra với các header Spring Kafka dùng để mô tả record đã nhận, chẳng hạn RECEIVED_TOPIC hoặc RECEIVED_PARTITION. Các header RECEIVED_* thường được tạo ở chiều consumer.

## 4. Tạo Message bằng MessageBuilder

Spring cung cấp MessageBuilder để tạo message theo kiểu fluent API. Payload được truyền vào withPayload; metadata được thêm bằng setHeader.

Giả sử ứng dụng có event:

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {
}
~~~

Khai báo topic tập trung:

~~~java
public final class KafkaTopics {

    private KafkaTopics() {
    }

    public static final String ORDER_CREATED =
        "commerce.order.created";
}
~~~

Tạo message:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<OrderCreated> buildMessage(
        OrderCreated event,
        String traceId) {

    return MessageBuilder.withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .setHeader("trace-id", traceId)
        .build();
}
~~~

Trong ví dụ:

- Payload là OrderCreated.
- TOPIC xác định topic commerce.order.created.
- KEY dùng orderId để các event cùng đơn hàng thường được định tuyến vào cùng partition với partitioner mặc định.
- trace-id giúp liên kết log và trace giữa các dịch vụ.

MessageBuilder tạo một Message có headers được quản lý theo abstraction của Spring. Sau khi build, không nên cố thay đổi headers của message đã tạo; nếu cần thay metadata, hãy tạo message mới từ builder.

### 4.1. Thêm partition và timestamp

Nếu nghiệp vụ hoặc thiết kế partitioning yêu cầu gửi tới một partition cụ thể, có thể đặt KafkaHeaders.PARTITION:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .setHeader(KafkaHeaders.PARTITION, 2)
    .build();
~~~

Khi partition được chỉ định, producer gửi record tới partition đó thay vì để partitioner tự chọn. Chỉ làm điều này khi ứng dụng thực sự cần kiểm soát partition; hard-code partition có thể làm lệch tải hoặc phá vỡ chiến lược phân phối key khi số partition thay đổi.

Có thể cung cấp timestamp:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(KafkaHeaders.TIMESTAMP, System.currentTimeMillis())
    .build();
~~~

Timestamp của record không thay thế thời điểm nghiệp vụ trong payload. Nếu cần phân biệt thời điểm event xảy ra với thời điểm producer gửi, nên mô hình hóa rõ cả hai trong event hoặc metadata.

## 5. Gửi Message<?> bằng KafkaTemplate

Giả sử producer được cấu hình cho key String và value OrderCreated:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event,
            String traceId) {

        Message<OrderCreated> message = MessageBuilder
            .withPayload(event)
            .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
            .setHeader(KafkaHeaders.KEY, event.orderId())
            .setHeader("trace-id", traceId)
            .build();

        return kafkaTemplate.send(message);
    }
}
~~~

Phương thức send(Message<?>) nhận Spring Message và chuyển đổi nó thành Kafka record. Ứng dụng không phải tự tạo ProducerRecord trong trường hợp thông thường.

Với Spring Kafka 3.x, các phương thức send trả về CompletableFuture<SendResult<K, V>>. Các phiên bản Spring Kafka cũ hơn có thể dùng ListenableFuture; cần đối chiếu API của phiên bản đang dùng khi viết callback.

### 5.1. Điều gì xảy ra khi gọi send?

Luồng gửi có thể mô tả như sau:

~~~mermaid
sequenceDiagram
    participant A as Application
    participant T as KafkaTemplate
    participant M as Message Converter
    participant P as Kafka Producer
    participant B as Kafka Broker

    A->>T: send(Message<?>)
    T->>M: Chuyển Message thành ProducerRecord
    M-->>T: ProducerRecord<K,V>
    T->>P: send(record)
    P->>P: Serialize key và value
    P->>B: Produce request
    B-->>P: Produce response
    P-->>T: Send result / exception
    T-->>A: CompletableFuture
~~~

Các bước chính:

1. Ứng dụng tạo Message với payload và headers.
2. KafkaTemplate gọi message converter để tạo ProducerRecord.
3. Converter đọc các Kafka headers để xác định topic, key, partition và timestamp; các metadata còn lại được ánh xạ thành Kafka record headers theo cấu hình mapper.
4. Kafka producer serialize key/value thành byte.
5. Producer gửi record tới broker.
6. Kết quả gửi được hoàn thành qua future.

Nếu thiếu topic header và không có default topic phù hợp, quá trình chuyển đổi record sẽ thất bại. Nếu payload không tương thích với serializer, thao tác gửi cũng có thể thất bại.

## 6. Phân biệt Message Converter và Serializer

Đây là hai thành phần có trách nhiệm khác nhau.

### 6.1. Message Converter

Message converter chuyển Spring Message thành Kafka ProducerRecord. Nó xử lý việc đọc headers và tạo record có topic, key, partition, timestamp, headers và payload.

Với KafkaTemplate, cơ chế này giúp ứng dụng gửi Message<?> mà không phải tự ánh xạ từng header sang ProducerRecord.

### 6.2. Serializer

Serializer chuyển key và value thành byte để Kafka producer gửi qua mạng.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

Cấu hình này có nghĩa:

- Key là String và được serialize bằng StringSerializer.
- Payload OrderCreated được serialize thành JSON bằng JsonSerializer.

Nếu dùng StringSerializer cho value, payload cần là String. Nếu payload là byte[], cần serializer tương ứng. Chỉ tạo Message<?> không tự động biến object bất kỳ thành JSON; serializer của producer vẫn phải phù hợp với kiểu value.

### 6.3. Content-Type không thay thế serializer

Có thể thêm header Content-Type để mô tả định dạng:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
    .build();
~~~

Content-Type là metadata hữu ích cho hệ thống tích hợp và converter phù hợp. Nó không tự thay thế cấu hình key/value serializer của Kafka producer. Cần thống nhất định dạng thực tế giữa producer và consumer.

## 7. Custom headers và truyền metadata

Ngoài các Kafka headers dành cho định tuyến, ứng dụng có thể gắn metadata riêng:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .setHeader("trace-id", traceId)
    .setHeader("event-source", "order-service")
    .setHeader("event-type", "OrderCreated")
    .build();
~~~

Một số mục đích thường gặp:

- trace-id: liên kết log và distributed trace.
- event-source: nhận diện ứng dụng phát event.
- event-type: hỗ trợ phân loại event khi hợp đồng yêu cầu.
- correlation-id: liên kết request với kết quả hoặc các event liên quan.
- schema-version: nhận diện hợp đồng dữ liệu nếu hệ thống quy định metadata này.

Kafka record headers là tập cặp key/value dạng byte. Spring Kafka dùng KafkaHeaderMapper để ánh xạ giữa Spring Message headers và Kafka headers. Default mapper hỗ trợ các kiểu dữ liệu thông dụng theo quy tắc của nó; với kiểu tùy chỉnh, cần cấu hình mapper và quy ước serialize/deserialize rõ ràng.

Không nên đặt payload lớn trong headers. Headers phù hợp với metadata nhỏ; dữ liệu nghiệp vụ nên nằm trong payload. Tránh đưa token, mật khẩu hoặc dữ liệu nhạy cảm vào header vì metadata thường xuất hiện trong log, tracing và công cụ quản trị.

## 8. Xử lý kết quả gửi bất đồng bộ

KafkaTemplate.send(Message<?>) là thao tác bất đồng bộ. Phương thức trả về CompletableFuture<SendResult<K, V>> trong Spring Kafka 3.x.

Có thể xử lý kết quả bằng whenComplete:

~~~java
public void publish(OrderCreated event, String traceId) {
    Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .setHeader("trace-id", traceId)
        .build();

    kafkaTemplate.send(message)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                    "Cannot publish order event, orderId={}",
                    event.orderId(),
                    exception
                );
                return;
            }

            RecordMetadata metadata =
                result.getRecordMetadata();

            log.info(
                "Published order event, topic={}, partition={}, offset={}",
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
~~~

Khi gửi thành công, SendResult cung cấp ProducerRecord đã gửi và RecordMetadata do broker trả về. Metadata thường được dùng để ghi nhận topic, partition và offset của record.

Không cần chặn thread gọi bằng get() chỉ để chờ kết quả nếu luồng xử lý có thể tiếp tục bất đồng bộ. Chặn thread web hoặc thread nghiệp vụ lâu có thể làm giảm khả năng phục vụ của ứng dụng.

### 8.1. Phân biệt lỗi đồng bộ và lỗi bất đồng bộ

Một số lỗi có thể phát sinh ngay trong lúc gọi send, chẳng hạn lỗi kiểm tra tham số, chuyển đổi message hoặc lỗi producer xảy ra trước khi future được trả về. Những lỗi khác được báo qua future khi thao tác gửi hoàn tất thất bại.

Nếu cần xử lý đầy đủ, có thể kết hợp try/catch quanh lời gọi send với callback của future:

~~~java
try {
    kafkaTemplate.send(message)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                handleAsyncFailure(exception);
            } else {
                handleSuccess(result);
            }
        });
} catch (RuntimeException exception) {
    handleImmediateFailure(exception);
}
~~~

Không nên nuốt exception hoặc chỉ ghi log rồi coi event đã được phát. Nếu nghiệp vụ cần bảo đảm phát event, phải có chiến lược retry, lưu trạng thái gửi hoặc Outbox Pattern phù hợp.

## 9. Những yếu tố ảnh hưởng kết quả gửi

Gửi thành công từ góc nhìn producer phụ thuộc vào cấu hình Kafka producer và phản hồi của broker.

Một số thuộc tính thường cần quan tâm:

| Thuộc tính | Vai trò |
|---|---|
| acks | Mức xác nhận mà producer yêu cầu từ broker |
| retries | Số lần producer thử lại request lỗi có thể phục hồi |
| enable.idempotence | Bật producer idempotence để hạn chế duplicate do retry producer trong phạm vi bảo đảm của Kafka |
| delivery.timeout.ms | Giới hạn tổng thời gian chờ gửi thành công hoặc thất bại |
| request.timeout.ms | Giới hạn thời gian chờ phản hồi request |
| max.block.ms | Giới hạn thời gian các API producer có thể chặn khi chờ metadata hoặc buffer |

Ví dụ cấu hình producer:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 10
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
~~~

Giá trị cụ thể cần dựa trên phiên bản Kafka client, tải hệ thống và yêu cầu độ tin cậy. Producer idempotence giúp tránh một số bản ghi trùng do retry của producer, nhưng không bảo đảm nghiệp vụ end-to-end chỉ được thực hiện đúng một lần.

Future hoàn thành thành công nghĩa là thao tác publish đã được xác nhận theo cấu hình producer và broker. Nó không có nghĩa consumer đã nhận, xử lý hoặc commit offset của sự kiện.

## 10. Key, partition và thứ tự khi gửi Message<?>

Key thường được đặt trong KafkaHeaders.KEY:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .build();
~~~

Khi không chỉ định partition, partitioner của producer quyết định partition. Với partitioner mặc định và key có giá trị, các record cùng key thường được định tuyến tới cùng partition trong điều kiện số partition và cấu hình partitioner không đổi.

Điều này hữu ích khi cần giữ thứ tự các event của cùng một đơn hàng trong một partition. Kafka bảo đảm thứ tự trong partition; không có thứ tự toàn cục giữa nhiều partition.

Nếu đặt KafkaHeaders.PARTITION, ứng dụng chỉ định partition trực tiếp. Khi đó, hãy kiểm tra partition tồn tại và đánh giá ảnh hưởng tới phân phối tải, ordering và khả năng mở rộng.

Không dùng timestamp hoặc trace ID làm key chỉ vì chúng có sẵn. Chọn key theo thực thể nghiệp vụ cần giữ thứ tự hoặc phân phối dữ liệu.

## 11. Các lỗi thường gặp khi gửi Message<?>

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không xác định được topic | Thiếu KafkaHeaders.TOPIC và không có default topic | Kiểm tra message headers và default topic |
| Producer gửi sai key | Đặt sai tên header hoặc kiểu key không tương thích | Dùng KafkaHeaders.KEY và kiểm tra serializer |
| Record vào partition ngoài dự kiến | Key không có giá trị, partitioner khác dự kiến hoặc đã đặt partition tường minh | Kiểm tra key, partitioner và KafkaHeaders.PARTITION |
| Payload không serialize được | Value serializer không tương thích với payload | Kiểm tra kiểu value và producer configuration |
| Custom header không tới consumer | Header mapper không ánh xạ kiểu dữ liệu hoặc tên header | Kiểm tra KafkaHeaderMapper và record headers |
| Future hoàn thành lỗi | Broker, timeout, serialization hoặc lỗi producer | Kiểm tra exception, producer metrics và broker log |
| Gửi thành công nhưng consumer không xử lý | Consumer group, subscription, offset hoặc listener có vấn đề | Kiểm tra consumer group, lag và listener |
| Event bị xử lý lặp | Producer retry, consumer redelivery hoặc xử lý nghiệp vụ không idempotent | Phân biệt producer idempotence với consumer idempotency |

Một lỗi dễ gặp là đặt tên header bằng chuỗi tùy ý thay vì dùng KafkaHeaders.TOPIC hoặc KafkaHeaders.KEY. Khi đó converter có thể không nhận ra metadata định tuyến, khiến record thiếu topic hoặc key.

## 12. Kiểm thử send(Message<?>) với Kafka

Kiểm thử tích hợp nên xác nhận cả payload và metadata của record.

Các bước kiểm thử:

1. Khởi động Kafka thử nghiệm bằng EmbeddedKafka hoặc Testcontainers.
2. Tạo KafkaTemplate với serializer tương thích.
3. Tạo Message<OrderCreated> bằng MessageBuilder.
4. Gửi message và chờ future hoàn thành trong bài kiểm thử.
5. Đọc record từ topic bằng consumer kiểm thử.
6. Xác nhận payload, key, partition và custom headers.

Ví dụ minh họa phần kiểm tra record nhận được:

~~~java
ConsumerRecord<String, OrderCreated> record =
    KafkaTestUtils.getSingleRecord(
        consumer,
        KafkaTopics.ORDER_CREATED
    );

assertThat(record.key()).isEqualTo("order-10001");
assertThat(record.value().orderId()).isEqualTo("order-10001");

Header traceHeader = record.headers().lastHeader("trace-id");
assertThat(traceHeader).isNotNull();
assertThat(new String(traceHeader.value(), StandardCharsets.UTF_8))
    .isEqualTo("trace-7f31");
~~~

Cách đọc custom header phụ thuộc mapper và cách serialize header được cấu hình. Với header dạng byte[], kiểm tra nội dung byte theo đúng encoding mà producer sử dụng.

Ngoài kiểm thử thành công, nên có các trường hợp:

- Thiếu topic header.
- Payload không tương thích serializer.
- Broker không sẵn sàng.
- Custom header có kiểu không được mapper hỗ trợ.
- Key và partition được ánh xạ đúng.
- Future hoàn thành lỗi được chuyển tới cơ chế xử lý phù hợp.

Không nên chỉ kiểm tra rằng phương thức publish không ném exception. Cần xác nhận record thực sự được ghi vào topic và metadata quan trọng đã được giữ lại.

## 13. Quy trình thực hành hoàn chỉnh

Giả sử dịch vụ Order phát OrderCreated để Billing xử lý.

### Bước 1: Khai báo cấu hình producer

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
~~~

### Bước 2: Tạo event

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {
}
~~~

### Bước 3: Tạo Message với headers

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader(KafkaHeaders.TOPIC, KafkaTopics.ORDER_CREATED)
    .setHeader(KafkaHeaders.KEY, event.orderId())
    .setHeader("trace-id", traceId)
    .setHeader("event-source", "order-service")
    .build();
~~~

### Bước 4: Gửi bằng KafkaTemplate

~~~java
CompletableFuture<SendResult<String, OrderCreated>> future =
    kafkaTemplate.send(message);
~~~

### Bước 5: Quan sát kết quả

~~~java
future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.error("Publish failed for {}", event.orderId(), exception);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.info(
        "Published to {}-{} at offset {}",
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
});
~~~

### Bước 6: Xác nhận ở consumer

Consumer Billing đọc topic commerce.order.created, kiểm tra payload và các headers cần thiết cho tracing hoặc nghiệp vụ. Nếu consumer cần xử lý idempotent, event nên có event ID ổn định trong payload hoặc metadata được thống nhất trong hợp đồng.

Luồng hoàn chỉnh:

~~~mermaid
flowchart TD
    A["Order Service tạo OrderCreated"] --> B["MessageBuilder.withPayload"]
    B --> C["Thêm TOPIC, KEY và trace-id"]
    C --> D["KafkaTemplate.send(Message<?>)"]
    D --> E["Message Converter"]
    E --> F["ProducerRecord"]
    F --> G["Serializer"]
    G --> H["Kafka Broker"]
    H --> I["Billing Consumer"]
    D --> J["CompletableFuture"]
    J --> K["Ghi nhận success hoặc failure"]
~~~

## 14. Checklist trước khi sử dụng send(Message<?>)

- [ ] Payload có kiểu dữ liệu phù hợp với KafkaTemplate<K, V> không?
- [ ] Message có KafkaHeaders.TOPIC hoặc default topic phù hợp không?
- [ ] KafkaHeaders.KEY có được chọn theo chiến lược partitioning không?
- [ ] KafkaHeaders.PARTITION chỉ được đặt khi thực sự cần chỉ định partition?
- [ ] Timestamp có ý nghĩa rõ ràng và đúng đơn vị milliseconds?
- [ ] Custom headers có kích thước nhỏ và kiểu dữ liệu mapper hỗ trợ?
- [ ] Không đưa secret hoặc thông tin nhạy cảm vào headers?
- [ ] Key/value serializer tương thích với dữ liệu thực tế?
- [ ] Future được quan sát để xử lý kết quả và exception?
- [ ] Chính sách acks, retries và idempotence phù hợp yêu cầu?
- [ ] Consumer có thể đọc đúng payload và headers?
- [ ] Kiểm thử xác nhận topic, key, payload và metadata của record?

## Kết luận

KafkaTemplate.send(Message<?>) cho phép ứng dụng Spring gửi một Message gồm payload và headers. Spring Kafka chuyển Message thành ProducerRecord, ánh xạ các Kafka headers như TOPIC, KEY, PARTITION và TIMESTAMP, sau đó Kafka producer serialize key/value và gửi record tới broker.

Cách gửi này phù hợp khi event cần mang metadata phục vụ định tuyến, tracing hoặc tích hợp với Spring Messaging. Để sử dụng đúng, cần phân biệt message converter với serializer, chọn key và partition có chủ đích, quan sát CompletableFuture và kiểm thử cả payload lẫn headers. Thành công của producer được xác định theo acknowledgment đã cấu hình; consumer vẫn cần cơ chế xử lý, offset và idempotency riêng để bảo đảm luồng messaging tin cậy.
