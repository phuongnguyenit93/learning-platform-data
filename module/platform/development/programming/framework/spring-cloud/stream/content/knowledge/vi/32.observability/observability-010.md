# Log có cấu trúc với event ID, correlation ID và metadata broker

Trong một ứng dụng Spring Cloud Stream, một sự kiện có thể đi qua nhiều function, binding, binder và broker trước khi hoàn tất nghiệp vụ. Khi xảy ra lỗi, một dòng log chỉ ghi “xử lý thất bại” thường không đủ để tìm đúng message giữa hàng triệu record. Log cần cho biết sự kiện nào đang được xử lý, thuộc luồng nghiệp vụ nào, đã đi qua broker và partition nào, được giao lại bao nhiêu lần và lỗi xuất hiện ở bước nào.

Log có cấu trúc giải quyết vấn đề này bằng các trường dữ liệu có tên và kiểu ổn định, thường được xuất dưới dạng JSON. `event-id`, `correlation-id`, `causation-id`, `trace-id` và metadata broker giúp liên kết các log theo sự kiện, theo hành trình nghiệp vụ và theo lần thực thi kỹ thuật.

Bài học này trình bày cách thiết kế hợp đồng log, truyền các ID qua message header, đưa dữ liệu vào MDC/structured logging, lấy metadata từ Kafka, RabbitMQ hoặc Pulsar và kiểm tra log trong môi trường triển khai.

## 1. Từ log văn bản sang log có cấu trúc

Log văn bản thường gộp nhiều thông tin vào một câu:

~~~text
Received order order-101 from kafka partition 2 offset 1842
~~~

Người đọc có thể hiểu câu trên, nhưng hệ thống log khó lọc chính xác nếu tên topic, partition hoặc event ID thay đổi vị trí hoặc định dạng. Log có cấu trúc biểu diễn từng giá trị thành một trường riêng:

~~~json
{
  "@timestamp": "2026-11-24T08:30:00Z",
  "log.level": "INFO",
  "service.name": "order-enricher",
  "message": "order event received",
  "event_id": "evt-01JDC8K5P3",
  "correlation_id": "checkout-7842",
  "causation_id": "evt-01JDC8JYQ1",
  "broker": "kafka",
  "destination": "orders.created",
  "partition": 2,
  "offset": 1842
}
~~~

Hệ thống log có thể lọc `event_id` bằng phép so khớp chính xác, nhóm theo `destination`, đếm lỗi theo `broker` hoặc tìm tất cả bước xử lý thuộc cùng `correlation_id`. Mỗi field có một ý nghĩa thống nhất nên dashboard, cảnh báo và truy vấn không cần phân tích chuỗi tự do.

## 2. Phân biệt các loại ID

Không nên dùng một ID cho tất cả mục đích. Các ID sau có vòng đời và ý nghĩa khác nhau:

| ID | Ý nghĩa | Vòng đời | Ví dụ |
|---|---|---|---|
| `event_id` | Định danh duy nhất của một sự kiện nghiệp vụ. | Giữ nguyên khi sự kiện được retry, gửi lại hoặc xử lý lại. | `evt-01JDC8K5P3` |
| `correlation_id` | Gom các sự kiện và bước xử lý thuộc cùng một hành trình nghiệp vụ. | Có thể tồn tại qua nhiều service và nhiều message. | `checkout-7842` |
| `causation_id` | Cho biết sự kiện hiện tại được tạo ra do sự kiện nào. | Thay đổi theo quan hệ nhân quả giữa các sự kiện. | `evt-01JDC8JYQ1` |
| `message_id` | Định danh message ở tầng vận chuyển do ứng dụng hoặc broker cung cấp. | Phụ thuộc broker và cách publish/redeliver. | Kafka record metadata, RabbitMQ message ID, Pulsar message ID. |
| `trace_id` | Định danh một distributed trace trong hệ thống tracing. | Theo trace; có thể khác với vòng đời dài của một quy trình nghiệp vụ. | W3C Trace ID dạng 32 ký tự hex. |
| `span_id` | Định danh một thao tác cụ thể trong trace. | Mỗi service hoặc thao tác tạo span riêng. | W3C Span ID dạng 16 ký tự hex. |

**Event ID** nhận diện nội dung sự kiện nghiệp vụ, ví dụ `OrderCreated`, `PaymentAuthorized` hoặc `InventoryReserved`. Producer nên tạo ID một lần khi hình thành sự kiện và giữ nguyên ID khi gửi lại cùng sự kiện. Consumer có thể dùng ID này làm khóa idempotency. Nếu tạo ID mới ở mỗi lần retry, consumer sẽ khó nhận ra các lần giao lại thuộc cùng một sự kiện.

**Correlation ID** liên kết các sự kiện có liên quan trong một hành trình dài. Một checkout có thể tạo `OrderCreated`, `PaymentRequested`, `PaymentAuthorized` và `ShipmentRequested`. Các sự kiện có event ID khác nhau nhưng cùng correlation ID. ID thường được tạo ở biên đầu tiên của nghiệp vụ; nếu message đầu vào đã có correlation ID hợp lệ thì service tiếp tục sử dụng.

**Causation ID** ghi lại sự kiện trực tiếp dẫn đến sự kiện mới. Ví dụ `PaymentAuthorized` có thể mang causation ID bằng event ID của `PaymentRequested`. Trường này giúp dựng lại chuỗi nguyên nhân khi workflow có nhiều nhánh hoặc xử lý bất đồng bộ.

**Trace ID và Span ID** thuộc distributed tracing. Một trace có thể chứa nhiều span qua HTTP, message broker và các service. Correlation ID thuộc ngữ nghĩa nghiệp vụ và thường tồn tại lâu hơn một trace; không nên thay correlation ID bằng trace ID hoặc ngược lại. Một workflow kéo dài nhiều giờ có thể tạo trace mới ở mỗi lần xử lý nhưng vẫn giữ correlation ID ban đầu.

**Message ID của broker** hoặc record position giúp xác định lần giao nhận tại broker. Kafka dùng topic, partition và offset; RabbitMQ có message ID nếu producer đặt và delivery tag trong một channel; Pulsar có message ID do broker cấp. Các giá trị này không thay thế event ID vì chúng có phạm vi và vòng đời riêng.

## 3. Quy ước header nghiệp vụ

Nên thống nhất tên header cho các service cùng trao đổi sự kiện:

| Header | Kiểu dữ liệu | Quy tắc |
|---|---|---|
| `event-id` | String | Bắt buộc với event nghiệp vụ; giữ nguyên qua retry. |
| `correlation-id` | String | Bắt buộc với workflow cần truy vết xuyên service. |
| `causation-id` | String | Có thể rỗng với sự kiện gốc; trỏ tới event gây ra sự kiện hiện tại. |
| `event-type` | String | Tên loại sự kiện, ví dụ `OrderCreated`. |
| `schema-version` | String hoặc số nguyên | Phiên bản hợp đồng payload. |
| `traceparent` | String | Trace context theo W3C khi hệ thống tracing và binder hỗ trợ truyền. |

Tên header là hợp đồng ứng dụng; hãy dùng cùng cách viết và kiểu dữ liệu ở producer lẫn consumer. Tránh đặt header tùy chỉnh là `id`, `timestamp`, `ID` hoặc `Id`: Spring Messaging có các header hệ thống cùng tên và một số binder có quy tắc ánh xạ riêng. Dùng `event-id` để phân biệt ID nghiệp vụ với message ID nội bộ của framework.

Không nhét toàn bộ object nghiệp vụ vào header. Header phù hợp với ID, loại sự kiện, version và metadata ngắn. Dữ liệu nghiệp vụ thuộc payload; broker header thường có giới hạn kích thước và cách serialize khác nhau.

## 4. Gắn ID vào message ở producer

Spring Cloud Stream cho phép producer phát `Message<T>` thay vì chỉ phát payload. Có thể đặt header tùy chỉnh bằng `MessageBuilder`:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderCreated(
        String orderId,
        String eventId,
        String correlationId,
        String causationId) {
}

@Configuration
class OrderEventConfiguration {

    @Bean
    Function<OrderCreated, Message<OrderCreated>> publishOrderCreated() {
        return event -> MessageBuilder
                .withPayload(event)
                .setHeader("event-id", event.eventId())
                .setHeader("correlation-id", event.correlationId())
                .setHeader("causation-id", event.causationId())
                .setHeader("event-type", "OrderCreated")
                .setHeader("schema-version", "1")
                .build();
    }
}
~~~

Trong ứng dụng thực tế, ID thường được tạo ở lớp phát sinh sự kiện hoặc domain event publisher. Không tạo lại event ID bên trong mỗi lần binder gửi lại message. Nếu một service phát sinh sự kiện mới sau khi xử lý event đầu vào, sự kiện mới có event ID mới và causation ID trỏ tới event ID đầu vào.

~~~text
OrderCreated
  event-id       = evt-order-101
  correlation-id = checkout-7842
  causation-id   = checkout-command-7842

PaymentRequested
  event-id       = evt-payment-202
  correlation-id = checkout-7842
  causation-id   = evt-order-101
~~~

## 5. Nhận ID và ghi log trong Consumer

Consumer có thể nhận `Message<T>` để đọc payload và header cùng lúc. Dùng SLF4J 2 fluent logging API để thêm các cặp key/value vào log event:

~~~java
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class OrderConsumerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(OrderConsumerConfiguration.class);

    @Bean
    Consumer<Message<OrderCreated>> consumeOrderCreated(OrderService service) {
        return message -> {
            String eventId =
                    message.getHeaders().get("event-id", String.class);
            String correlationId =
                    message.getHeaders().get("correlation-id", String.class);
            String causationId =
                    message.getHeaders().get("causation-id", String.class);

            try (
                    MDC.MDCCloseable eventContext =
                            eventId == null ? null
                                    : MDC.putCloseable("event_id", eventId);
                    MDC.MDCCloseable correlationContext =
                            correlationId == null ? null
                                    : MDC.putCloseable(
                                            "correlation_id", correlationId)
            ) {
                log.atInfo()
                        .addKeyValue("operation", "order.consume")
                        .addKeyValue("event_id", eventId)
                        .addKeyValue("correlation_id", correlationId)
                        .addKeyValue("causation_id", causationId)
                        .log("order event received");

                service.handle(message.getPayload());

                log.atInfo()
                        .addKeyValue("operation", "order.consume")
                        .addKeyValue("event_id", eventId)
                        .addKeyValue("correlation_id", correlationId)
                        .addKeyValue("outcome", "success")
                        .log("order event processed");
            }
            catch (RuntimeException ex) {
                log.atError()
                        .setCause(ex)
                        .addKeyValue("operation", "order.consume")
                        .addKeyValue("event_id", eventId)
                        .addKeyValue("correlation_id", correlationId)
                        .addKeyValue("outcome", "failure")
                        .addKeyValue("exception_type",
                                ex.getClass().getName())
                        .log("order event processing failed");
                throw ex;
            }
        };
    }
}
~~~

`MDC.putCloseable` giúp thêm ID vào diagnostic context của thread và tự gỡ chúng khi khối try kết thúc. Việc dọn context quan trọng vì thread của consumer thường được tái sử dụng cho message tiếp theo. Nếu giữ lại ID cũ, log của message sau có thể bị gắn nhầm correlation ID.

Ví dụ trên ghi log khi nhận, khi xử lý thành công và khi thất bại. Exception được ném lại để Spring Cloud Stream/binder thực hiện retry hoặc error handling theo cấu hình; ghi log lỗi không đồng nghĩa đã xử lý xong message.

Nếu ID bắt buộc nhưng message không có, hãy ghi một log cảnh báo có `outcome=missing_required_header`, destination và tên binding, sau đó áp dụng chính sách hợp đồng của ứng dụng. Không tự tạo event ID mới ở consumer để che giấu lỗi producer, vì điều đó làm mất khả năng idempotency và truy vết.

## 6. Bật structured logging trong Spring Boot

Spring Boot hỗ trợ xuất log JSON theo các định dạng phổ biến như ECS, GELF và Logstash ở những phiên bản có structured logging. Ví dụ dưới đây dùng ECS:

~~~yaml
spring:
  application:
    name: order-enricher

logging:
  structured:
    format:
      console: ecs
      file: ecs
    ecs:
      service:
        name: order-enricher
        version: "1.4.0"
        environment: production
~~~

Các key/value được thêm qua SLF4J fluent API và các giá trị trong MDC được đưa vào JSON output. Khi dùng custom Logback hoặc Log4j2 configuration, cần cấu hình encoder/layout tương ứng của Spring Boot để tôn trọng structured format property; chỉ đặt property mà encoder tùy chỉnh không đọc property thì log vẫn có thể ở dạng văn bản.

Nếu hệ thống log ingest yêu cầu Logstash JSON, có thể đặt:

~~~yaml
logging:
  structured:
    format:
      console: logstash
      file: logstash
~~~

Chọn một schema log nhất quán trong toàn bộ môi trường. Không để service A xuất `event_id`, service B xuất `eventId`, còn service C xuất `event-id` nếu các field cùng biểu diễn một khái niệm.

### Ví dụ log JSON

~~~json
{
  "@timestamp": "2026-11-24T08:30:00.123Z",
  "log": {
    "level": "INFO",
    "logger": "com.example.OrderConsumerConfiguration"
  },
  "service": {
    "name": "order-enricher",
    "version": "1.4.0",
    "environment": "production"
  },
  "message": "order event received",
  "event_id": "evt-order-101",
  "correlation_id": "checkout-7842",
  "causation_id": "evt-checkout-001",
  "operation": "order.consume",
  "broker": "kafka",
  "destination": "orders.created",
  "consumer_group": "order-enricher"
}
~~~

Tên field cụ thể phụ thuộc format và cấu hình rename/add/exclude. Hãy chốt schema chung cho hệ thống log trước khi xây dashboard và alert.

## 7. Trường dữ liệu nên có trong log event

Không phải mọi log đều cần toàn bộ field. Nên định nghĩa một schema chung và bổ sung metadata theo từng loại operation.

| Nhóm | Field gợi ý | Mục đích |
|---|---|---|
| Thời gian | `@timestamp`, `duration_ms` | Sắp xếp sự kiện và đo thời gian xử lý. |
| Service | `service.name`, `service.version`, `environment`, `instance_id` | Xác định service và instance phát log. |
| Operation | `operation`, `message`, `outcome`, `stage` | Biết đang publish, receive, process, retry hay dead-letter. |
| Event | `event_id`, `event_type`, `schema_version` | Xác định sự kiện nghiệp vụ và hợp đồng dữ liệu. |
| Quan hệ | `correlation_id`, `causation_id` | Liên kết workflow và quan hệ nhân quả. |
| Trace | `trace_id`, `span_id` | Mở distributed trace tương ứng. |
| Broker | `broker`, `destination`, `consumer_group` hoặc `subscription` | Xác định middleware và luồng nhận. |
| Vị trí | `partition`, `offset`, `routing_key`, `message_id` | Tìm message cụ thể trong broker. |
| Giao nhận | `redelivered`, `delivery_attempt`, `redelivery_count`, `ack_mode` | Phân tích retry và duplicate. |
| Lỗi | `exception_type`, `error_code`, `error_category` | Phân loại lỗi mà không cần parse stack trace. |

Giữ tên field nhất quán và giá trị có kiểu phù hợp. Ví dụ partition, offset và duration_ms là số; event_id, correlation_id và destination là chuỗi; redelivered là boolean.

Không ghi toàn bộ payload hoặc toàn bộ map headers vào log. Payload có thể chứa dữ liệu cá nhân, thông tin thanh toán hoặc bí mật; header có thể chứa token, credential hoặc dữ liệu định tuyến nội bộ. Chỉ chọn whitelist field phục vụ vận hành, giới hạn độ dài và mask dữ liệu nhạy cảm trước khi ghi.

## 8. Metadata broker không giống metadata nghiệp vụ

Mỗi broker có cách định danh và giao nhận riêng. Khi ghi log, giữ nguyên ý nghĩa gốc của metadata:

| Broker | Metadata hữu ích | Ý nghĩa |
|---|---|---|
| Kafka | Topic, partition, offset, record key, timestamp, consumer group | Vị trí record trong log phân vùng và nhóm consumer xử lý. |
| RabbitMQ | Exchange, routing key, queue, message ID, correlation ID, delivery tag, redelivered | Đường định tuyến và trạng thái delivery trên channel. |
| Pulsar | Topic, message ID, key, publish time, event time, producer name, redelivery count, schema version | Định danh message và thông tin phát/giao lại của subscription. |

Không giả định mọi binder đều đưa metadata broker vào cùng một Spring header name. Binder có header mapper, type conversion và property riêng. Kiểm tra header thực tế theo binder và phiên bản đang dùng trước khi xây field mapping.

## 9. Ghi metadata Kafka

Spring Kafka cung cấp các header trong `KafkaHeaders` để truy cập metadata của record nhận vào:

| Header | Dữ liệu |
|---|---|
| `KafkaHeaders.RECEIVED_TOPIC` | Topic đã nhận record. |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition của record. |
| `KafkaHeaders.OFFSET` | Offset trong partition. |
| `KafkaHeaders.RECEIVED_KEY` | Record key nếu có. |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Timestamp của record. |
| `KafkaHeaders.RECORD_METADATA` | Metadata của lần gửi thành công, khi dùng producer metadata channel. |

Ví dụ Consumer nhận `Message` và log metadata:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

void logKafkaRecord(Message<OrderCreated> message) {
    var headers = message.getHeaders();

    log.atInfo()
            .addKeyValue("broker", "kafka")
            .addKeyValue("destination",
                    headers.get(KafkaHeaders.RECEIVED_TOPIC))
            .addKeyValue("partition",
                    headers.get(KafkaHeaders.RECEIVED_PARTITION))
            .addKeyValue("offset",
                    headers.get(KafkaHeaders.OFFSET))
            .addKeyValue("record_key",
                    headers.get(KafkaHeaders.RECEIVED_KEY))
            .addKeyValue("broker_timestamp",
                    headers.get(KafkaHeaders.RECEIVED_TIMESTAMP))
            .log("kafka record received");
}
~~~

### Metadata khi publish thành công

Kafka binder hỗ trợ `recordMetadataChannel` cho output binding. Cấu hình channel nhận kết quả gửi:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrderCreated-out-0:
            producer:
              record-metadata-channel: kafkaSendResults
~~~

Channel `kafkaSendResults` phải tồn tại trong application context. Message gửi vào channel này có header `KafkaHeaders.RECORD_METADATA` chứa `RecordMetadata`, trong đó có topic, partition và offset nơi record đã được ghi.

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

void logKafkaSendResult(Message<?> result) {
    RecordMetadata metadata = result.getHeaders()
            .get(KafkaHeaders.RECORD_METADATA, RecordMetadata.class);

    if (metadata != null) {
        log.atInfo()
                .addKeyValue("broker", "kafka")
                .addKeyValue("destination", metadata.topic())
                .addKeyValue("partition", metadata.partition())
                .addKeyValue("offset", metadata.offset())
                .log("kafka record published");
    }
}
~~~

Metadata này là bằng chứng broker đã xác nhận lần ghi thành công theo producer semantics đang cấu hình. Nếu gửi thất bại, binder sử dụng producer error channel khi đã cấu hình; không ghi một record thành công chỉ vì function đã tạo message hoặc gọi send.

### Header mapper và header đặc biệt

Kafka binder ánh xạ Spring message headers sang Kafka record headers. Với phiên bản Kafka hiện đại, header tùy chỉnh thường được truyền tự nhiên; custom `KafkaHeaderMapper` hoặc `headerPatterns` có thể thay đổi những header được gửi. `id` và `timestamp` là header framework đặc biệt và không được map như header tùy chỉnh mặc định.

Vì vậy:

- Dùng `event-id` và `correlation-id` cho metadata nghiệp vụ.
- Nếu custom header mapper được cấu hình, thêm các header nghiệp vụ cần truyền vào mapper.
- Kiểm tra kiểu dữ liệu khi chuyển byte[] và String.
- Không log raw Kafka headers hoặc `ConsumerRecord` đầy đủ; chỉ trích xuất các field cần thiết.
- Ghi consumer group từ cấu hình binding hoặc context triển khai; không giả định nó luôn có mặt như một message header.

## 10. Ghi metadata RabbitMQ

RabbitMQ sử dụng exchange, routing key và queue. Spring AMQP ánh xạ các thông tin này vào các header `AmqpHeaders`:

| Header | Dữ liệu |
|---|---|
| `AmqpHeaders.RECEIVED_EXCHANGE` | Exchange nhận message. |
| `AmqpHeaders.RECEIVED_ROUTING_KEY` | Routing key được dùng để route message. |
| `AmqpHeaders.MESSAGE_ID` | Message ID nếu producer đặt. |
| `AmqpHeaders.CORRELATION_ID` | AMQP correlation ID nếu producer đặt. |
| `AmqpHeaders.DELIVERY_TAG` | Delivery tag của lần giao message trên channel. |
| `AmqpHeaders.CONSUMER_TAG` | Consumer tag nhận message. |
| `AmqpHeaders.REDELIVERED` | Cờ cho biết broker đánh dấu message đã được giao lại. |

Ví dụ:

~~~java
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.Message;

void logRabbitDelivery(Message<OrderCreated> message) {
    var headers = message.getHeaders();

    log.atInfo()
            .addKeyValue("broker", "rabbitmq")
            .addKeyValue("exchange",
                    headers.get(AmqpHeaders.RECEIVED_EXCHANGE))
            .addKeyValue("routing_key",
                    headers.get(AmqpHeaders.RECEIVED_ROUTING_KEY))
            .addKeyValue("message_id",
                    headers.get(AmqpHeaders.MESSAGE_ID))
            .addKeyValue("amqp_correlation_id",
                    headers.get(AmqpHeaders.CORRELATION_ID))
            .addKeyValue("delivery_tag",
                    headers.get(AmqpHeaders.DELIVERY_TAG))
            .addKeyValue("consumer_tag",
                    headers.get(AmqpHeaders.CONSUMER_TAG))
            .addKeyValue("redelivered",
                    headers.get(AmqpHeaders.REDELIVERED))
            .log("rabbit message delivered");
}
~~~

`delivery_tag` chỉ có ý nghĩa trong channel hiện tại và không phải ID bền vững của message. Không dùng delivery tag làm `event_id` hoặc khóa idempotency. `redelivered` là tín hiệu giao lại từ broker, không phải tổng số lần thử; nếu cần đếm chu kỳ dead-letter/requeue, có thể đọc metadata `x-death` theo cấu hình RabbitMQ và log các giá trị đã chọn.

Với RabbitMQ binder, queue và exchange được tạo theo destination/group và các thuộc tính binder. Log `destination`, group và routing key để xác định đường đi. `consumerTagPrefix` có thể giúp tên consumer dễ nhận diện trong broker; đây là cấu hình consumer, không phải ID nghiệp vụ.

Nếu ứng dụng cần biết publisher confirm, hãy ghi log từ cơ chế confirm thực tế như `confirmAckChannel` hoặc correlation data header/confirm future. Việc gọi `StreamBridge.send` hoặc tạo message không tự chứng minh broker đã xác nhận publish.

## 11. Ghi metadata Pulsar

Pulsar có message metadata và user properties. Spring for Apache Pulsar cung cấp `PulsarHeaders`; Pulsar binder chuyển đổi các metadata cần thiết giữa Pulsar message và Spring Messaging.

Các field thường hữu ích:

| Header | Dữ liệu |
|---|---|
| `PulsarHeaders.MESSAGE_ID` | Message ID do Pulsar cấp. |
| `PulsarHeaders.TOPIC_NAME` | Tên topic. |
| `PulsarHeaders.KEY` | Message key nếu có. |
| `PulsarHeaders.PUBLISH_TIME` | Thời điểm publish. |
| `PulsarHeaders.BROKER_PUBLISH_TIME` | Thời điểm broker publish nếu có. |
| `PulsarHeaders.EVENT_TIME` | Event time do producer đặt. |
| `PulsarHeaders.PRODUCER_NAME` | Tên producer. |
| `PulsarHeaders.REDELIVERY_COUNT` | Số lần redelivery được broker ghi nhận. |
| `PulsarHeaders.SCHEMA_VERSION` | Schema version của message. |
| `PulsarHeaders.SEQUENCE_ID` | Sequence ID của producer. |

Ví dụ trích xuất các giá trị để ghi log:

~~~java
import org.springframework.messaging.Message;
import org.springframework.pulsar.support.PulsarHeaders;

void logPulsarDelivery(Message<OrderCreated> message) {
    var headers = message.getHeaders();

    log.atInfo()
            .addKeyValue("broker", "pulsar")
            .addKeyValue("destination",
                    headers.get(PulsarHeaders.TOPIC_NAME))
            .addKeyValue("message_id",
                    headers.get(PulsarHeaders.MESSAGE_ID))
            .addKeyValue("message_key",
                    headers.get(PulsarHeaders.KEY))
            .addKeyValue("publish_time",
                    headers.get(PulsarHeaders.PUBLISH_TIME))
            .addKeyValue("event_time",
                    headers.get(PulsarHeaders.EVENT_TIME))
            .addKeyValue("producer_name",
                    headers.get(PulsarHeaders.PRODUCER_NAME))
            .addKeyValue("redelivery_count",
                    headers.get(PulsarHeaders.REDELIVERY_COUNT))
            .addKeyValue("schema_version",
                    headers.get(PulsarHeaders.SCHEMA_VERSION))
            .log("pulsar message delivered");
}
~~~

Tên package và tập header khả dụng phụ thuộc phiên bản Spring for Apache Pulsar/Pulsar binder. Hãy dùng `PulsarHeaders` thuộc dependency thực tế của ứng dụng và kiểm tra header mapper của binder trước khi triển khai.

Pulsar binder có `PulsarHeaderMapper` mặc định và cho phép thay bằng custom mapper. Nếu mapper chỉ cho phép một số pattern, header `event-id`, `correlation-id` hoặc `causation-id` có thể không đi qua. Khi dùng JSON header mapper, chỉ deserialize object từ package được tin cậy; không mở rộng trusted packages tùy tiện cho dữ liệu đến từ broker.

## 12. Retry, redelivery và dead-letter log

Một sự kiện có thể được giao nhiều lần do lỗi tạm thời, timeout, process restart hoặc acknowledgement chưa hoàn tất. Log cần phân biệt:

- **Attempt:** lần xử lý hiện tại của ứng dụng.
- **Redelivery:** broker giao lại một message đã từng được giao.
- **Retry:** ứng dụng hoặc binder lên lịch thử lại xử lý.
- **Dead-letter:** message được chuyển sang destination lỗi sau khi hết chính sách thử lại hoặc bị reject.

Ví dụ các operation:

| Operation | Trường nên ghi | Khi nào |
|---|---|---|
| `message.received` | `event_id`, `correlation_id`, broker metadata, attempt/redelivered | Khi consumer nhận message. |
| `message.processed` | ID, `outcome=success`, `duration_ms` | Khi nghiệp vụ hoàn tất. |
| `message.retry_scheduled` | ID, `delivery_attempt`, `retry_delay_ms`, `exception_type` | Khi xác định sẽ thử lại. |
| `message.failed` | ID, `outcome=failure`, `exception_type`, `error_code` | Khi lần xử lý hiện tại thất bại. |
| `message.dead_lettered` | ID, source destination, DLQ destination, redelivery count | Khi chuyển message sang DLQ/DLT. |
| `message.published` | ID, destination và broker publish metadata | Khi broker xác nhận publish. |

`event_id` và `correlation_id` cần giữ nguyên trong retry. `delivery_attempt` hoặc `redelivery_count` thay đổi theo cơ chế của binder/broker. Không suy ra số lần retry chỉ từ một cờ `redelivered`; RabbitMQ có `x-death` cho dead-letter cycle, Pulsar có redelivery count, còn Kafka retry/DLT có thể dùng topic/headers và metadata do binder hoặc ứng dụng cung cấp.

Khi log lỗi, ghi `exception_type`, mã lỗi, operation và ID. Stack trace có thể cần cho lỗi bất ngờ, nhưng không ghi toàn bộ payload vào exception message nếu payload có dữ liệu nhạy cảm.

## 13. Tracing và correlation trong Spring Cloud Stream

Spring Cloud Stream tích hợp observability qua Micrometer. Với imperative function, khi các dependency tracing/observation cần thiết có mặt, framework có thể tạo observation cho mỗi lần function được gọi. Với reactive function, function khởi tạo pipeline một lần và việc quan sát từng phần tử cần được đặt trong reactive chain bằng API observation phù hợp.

Các dependency thường gặp trong ứng dụng Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
~~~

Có thể dùng bridge tracing khác theo nền tảng đang triển khai. Cần cấu hình exporter/reporter nếu muốn gửi trace tới backend như Zipkin hoặc OpenTelemetry Collector.

Khi Micrometer Tracing được bật, Spring Boot đưa `traceId` và `spanId` vào MDC; structured logging có thể xuất các trường này cùng log event. Đây là thông tin của trace hiện tại, trong khi `event-id` và `correlation-id` vẫn là header nghiệp vụ do ứng dụng quản lý.

Ví dụ cấu hình baggage:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - tenant-context
      correlation:
        fields:
          - tenant-context
~~~

Baggage phù hợp với một số metadata ngắn cần đi cùng trace và được cấu hình cho phép truyền qua transport đã instrument. Không dùng baggage làm kho chứa mọi event header; đặc biệt, không đưa dữ liệu nhạy cảm, payload hoặc danh sách ID dài vào baggage. Với message broker, hãy xác nhận binder và instrumentation thực sự truyền trace context qua message headers.

Kafka binder có thuộc tính `spring.cloud.stream.kafka.binder.enableObservation` để bật observation cho các binding của binder. Giá trị mặc định và hỗ trợ observation khác nhau theo binder/version; kiểm tra tài liệu của đúng binder thay vì giả định mọi broker tự bật tracing giống nhau.

### Reactive function và context propagation

MDC thường gắn với thread. Trong reactive pipeline, callback có thể chạy trên nhiều thread khác nhau; việc gọi `MDC.put` ở một thread không đảm bảo giá trị xuất hiện ở thread khác. Dùng Micrometer Context Propagation/Observation hoặc Reactor context propagation theo cấu hình tương ứng.

Với reactive function của Spring Cloud Stream, tài liệu observability yêu cầu gắn observation vào đoạn pipeline muốn đo, chẳng hạn dùng `tap(Micrometer.observation(registry))`. Nếu không đặt observation cho từng segment, log có thể vẫn xuất hiện nhưng trace không phản ánh từng message như mong muốn.

## 14. Không để MDC làm nhiễm log message tiếp theo

MDC thường được lưu theo thread và thread consumer được tái sử dụng. Cần luôn khôi phục hoặc xóa context:

~~~java
String previousEventId = MDC.get("event_id");
try {
    MDC.put("event_id", eventId);
    process(event);
}
finally {
    if (previousEventId == null) {
        MDC.remove("event_id");
    }
    else {
        MDC.put("event_id", previousEventId);
    }
}
~~~

`MDC.putCloseable` với try-with-resources thường gọn hơn khi chỉ thêm một vài field. Nếu tự quản lý MDC map, phải khôi phục cả giá trị cũ thay vì luôn `clear()` toàn bộ context, vì tracing framework có thể đang giữ `traceId`/`spanId` trong cùng context.

Đối với `@Async`, executor tùy chỉnh hoặc callback chạy trên thread khác, cấu hình context propagation hoặc task decorator phù hợp. Không giả định MDC tự truyền qua mọi executor, scheduler hay reactive boundary.

## 15. Thiết kế log theo vòng đời message

Log quá ít sẽ khó điều tra; log mọi chi tiết ở mọi bước sẽ tăng chi phí lưu trữ và gây nhiễu. Một quy ước thực tế:

| Mức log | Sử dụng |
|---|---|
| `ERROR` | Message thất bại không thể xử lý, lỗi cấu hình, lỗi broker hoặc lỗi bất ngờ cần hành động. |
| `WARN` | Message thiếu header bắt buộc, retry vượt ngưỡng, redelivery bất thường hoặc fallback được kích hoạt. |
| `INFO` | Các chuyển trạng thái nghiệp vụ quan trọng như publish/consume hoàn tất, chuyển DLQ hoặc thay đổi trạng thái xử lý. |
| `DEBUG` | Metadata chi tiết từng message ở luồng có lưu lượng cao, khi cần điều tra. |
| `TRACE` | Chi tiết rất sâu như từng bước conversion hoặc header mapping trong thời gian chẩn đoán. |

Với hệ thống lưu lượng lớn, có thể sampling log thành công nhưng vẫn giữ log lỗi và chuyển DLQ. Sampling phải giữ được khả năng truy vấn `event_id` hoặc `correlation_id` cho các sự kiện được chọn; không sampling theo cách làm mất log của một workflow đang điều tra.

Không dùng log thay metrics. Throughput, consumer lag, retry rate, processing latency và DLQ rate nên là metrics; log giữ chi tiết của từng lần xử lý hoặc chuyển trạng thái.

## 16. Tránh log dữ liệu nhạy cảm và header không tin cậy

Message broker là ranh giới nhận dữ liệu từ hệ thống khác. Header và payload có thể do producer bên ngoài kiểm soát. Trước khi đưa chúng vào log:

- Whitelist các header được phép: event ID, correlation ID, event type, schema version và metadata broker cần thiết.
- Không log access token, authorization header, mật khẩu, cookie, API key hoặc raw credential.
- Không log payload thanh toán, thông tin cá nhân hoặc nội dung bí mật; nếu cần định danh, dùng ID nghiệp vụ không nhạy cảm.
- Giới hạn độ dài chuỗi và loại bỏ ký tự điều khiển để tránh log injection.
- Không serialize toàn bộ object header hoặc native broker record.
- Chuẩn hóa `event_type`, `destination` và `error_code` để tránh tạo cardinality quá cao.
- Không đưa `event_id`, `correlation_id`, `message_id` làm label của metrics; các ID có cardinality cao phù hợp với log/trace hơn.

Nếu dùng Pulsar custom JSON header mapper hoặc Kafka custom header mapper, chỉ ánh xạ các header đã biết và có quy tắc deserialize rõ ràng. Không deserialize class tùy ý từ message bên ngoài.

## 17. Kiểm thử log có cấu trúc

Kiểm thử log cần xác nhận cả nội dung và việc dọn context:

1. Khi nhận message hợp lệ, log có `event_id`, `correlation_id`, `operation` và destination.
2. Khi xử lý thành công, log có `outcome=success` và thời gian xử lý.
3. Khi xử lý thất bại, log có `outcome=failure`, `exception_type` và vẫn ném exception theo chính sách retry.
4. Khi message thiếu ID bắt buộc, log cảnh báo và thực hiện chính sách hợp đồng đã định.
5. Sau khi xử lý xong, MDC của thread không còn `event_id` hoặc `correlation_id` của message trước.
6. Kafka log có topic/partition/offset; RabbitMQ log có exchange/routing key/delivery metadata; Pulsar log có topic/message ID/redelivery metadata khi các header đó có mặt.
7. Log output parse được thành JSON và field giữ đúng kiểu dữ liệu.
8. Không có payload hoặc credential nhạy cảm trong log.

### Kiểm tra log JSON

Có thể chạy ứng dụng test với structured logging và đọc output bằng JSON parser trong test harness hoặc CI. Assert theo field thay vì so sánh nguyên văn cả dòng log, vì timestamp, PID, thread và trace ID có thể thay đổi giữa các lần chạy.

### Kiểm tra header round-trip

Với từng binder, gửi message có `event-id`, `correlation-id`, `causation-id`, rồi nhận ở consumer và xác nhận giá trị không đổi. Test cần chạy với binder thực nếu mục tiêu là xác minh header mapper và serialization của broker.

Với Kafka, kiểm tra cả header mapper và các header reserved. Với RabbitMQ, kiểm tra AMQP header mapping và routing metadata. Với Pulsar, kiểm tra `PulsarHeaderMapper`, schema và user properties theo phiên bản binder.

## 18. Ví dụ một record log xuyên service

Giả sử checkout tạo đơn hàng và phát `OrderCreated`. `order-enricher` nhận event, làm giàu dữ liệu rồi phát `OrderEnriched`. Các log có thể cùng correlation ID nhưng event ID khác nhau:

~~~json
{
  "@timestamp": "2026-11-24T08:30:00.100Z",
  "service.name": "order-service",
  "message": "order event published",
  "operation": "order.publish",
  "event_id": "evt-order-101",
  "correlation_id": "checkout-7842",
  "causation_id": "cmd-checkout-7842",
  "event_type": "OrderCreated",
  "broker": "kafka",
  "destination": "orders.created",
  "outcome": "success"
}
~~~

~~~json
{
  "@timestamp": "2026-11-24T08:30:00.140Z",
  "service.name": "order-enricher",
  "message": "order event received",
  "operation": "order.consume",
  "event_id": "evt-order-101",
  "correlation_id": "checkout-7842",
  "causation_id": "cmd-checkout-7842",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "broker": "kafka",
  "destination": "orders.created",
  "partition": 2,
  "offset": 1842,
  "consumer_group": "order-enricher"
}
~~~

~~~json
{
  "@timestamp": "2026-11-24T08:30:00.170Z",
  "service.name": "order-enricher",
  "message": "enriched order published",
  "operation": "order.publish",
  "event_id": "evt-order-enriched-102",
  "correlation_id": "checkout-7842",
  "causation_id": "evt-order-101",
  "event_type": "OrderEnriched",
  "broker": "kafka",
  "destination": "orders.enriched",
  "outcome": "success"
}
~~~

Khi cần điều tra checkout, tìm `correlation_id=checkout-7842` để xem các service và sự kiện liên quan. Khi điều tra duplicate của một event, tìm `event_id=evt-order-101`. Khi điều tra một record Kafka cụ thể, kết hợp topic, partition và offset.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Consumer không thấy `event-id` | Producer chưa gắn header hoặc custom header mapper loại bỏ header. | Kiểm tra producer message và mapper ở cả hai phía. |
| Header `Id` biến mất khi qua Kafka | Trùng với header `id` đặc biệt của Spring Messaging. | Dùng `event-id`; chỉ custom-map header cũ nếu hợp đồng bắt buộc. |
| Log của message sau mang correlation ID cũ | MDC không được dọn sau xử lý hoặc exception path bỏ qua cleanup. | Dùng `MDC.putCloseable` hoặc `try/finally`. |
| Trace ID có nhưng event ID không có | Tracing tự động không tạo ID nghiệp vụ. | Truyền `event-id` và `correlation-id` bằng message headers. |
| Correlation ID thay đổi sau retry | Producer hoặc retry handler tạo ID mới. | Giữ nguyên correlation ID và event ID cho cùng event. |
| Kafka log không có offset | Đang log trước khi nhận record metadata hoặc dùng nhầm header. | Đọc `KafkaHeaders.OFFSET` ở consumer; dùng `recordMetadataChannel` ở producer. |
| Rabbit delivery tag bị dùng làm event ID | Nhầm metadata channel-scoped với ID nghiệp vụ. | Giữ event ID riêng; chỉ log delivery tag để điều tra delivery hiện tại. |
| Pulsar không có redelivery count | Phiên bản binder/header mapper không cung cấp header đó hoặc message chưa redeliver. | Kiểm tra `PulsarHeaders` và mapper của phiên bản đang chạy. |
| Log JSON thiếu MDC | Custom logging encoder/layout không hỗ trợ structured format hoặc MDC. | Cấu hình encoder/layout tương ứng của Spring Boot. |
| Log quá lớn và khó truy vấn | Ghi toàn bộ payload/header hoặc quá nhiều field động. | Whitelist field, giới hạn kích thước và chuẩn hóa schema. |
| Trace không đi qua reactive pipeline | MDC/thread-local không theo Reactor context hoặc observation chưa được gắn. | Dùng Micrometer Context Propagation/Observation và instrument reactive segment. |
| Dashboard metrics có quá nhiều series | Dùng event ID, message ID hoặc correlation ID làm metric tag. | Chuyển ID có cardinality cao sang log/trace; giữ tag metrics có tập giá trị hữu hạn. |

## 20. Checklist trước khi triển khai

- [ ] Có quy ước thống nhất cho `event-id`, `correlation-id`, `causation-id`, `event-type` và `schema-version`.
- [ ] `event-id` giữ nguyên qua retry và redelivery của cùng một event.
- [ ] Correlation ID được giữ qua các service trong cùng workflow.
- [ ] Causation ID trỏ tới event trực tiếp gây ra event mới.
- [ ] Trace ID và Span ID được phân biệt với ID nghiệp vụ.
- [ ] Structured logging JSON được bật theo schema thống nhất.
- [ ] Log có service, environment, operation, outcome và timestamp.
- [ ] Log chỉ lấy whitelist header và broker metadata cần thiết.
- [ ] Kafka log có topic/partition/offset/key khi có metadata.
- [ ] RabbitMQ log có exchange/routing key/message ID/redelivery metadata khi có.
- [ ] Pulsar log có topic/message ID/key/publish time/redelivery count khi có.
- [ ] Consumer group hoặc subscription được ghi từ cấu hình/context triển khai.
- [ ] MDC được dọn sau mỗi message và được truyền đúng qua async/reactive boundary.
- [ ] Retry, failure và dead-letter log có event ID, attempt và error category.
- [ ] Payload, token, credential và dữ liệu nhạy cảm không bị ghi vào log.
- [ ] Event ID và correlation ID không được dùng làm metric label có cardinality cao.
- [ ] Đã kiểm thử JSON parse, header round-trip và MDC cleanup.

Log có cấu trúc giúp vận hành Spring Cloud Stream nhìn thấy cả hành trình nghiệp vụ lẫn vị trí message trong broker. `event-id` nhận diện một sự kiện, `correlation-id` liên kết workflow, `causation-id` mô tả quan hệ nhân quả, còn `trace-id`/`span-id` nối log với distributed trace. Khi kết hợp các ID này với metadata topic/partition/offset của Kafka, exchange/routing key của RabbitMQ hoặc message ID/redelivery count của Pulsar, đội vận hành có thể tìm đúng message, hiểu retry và xác định service gây lỗi mà không phải ghi toàn bộ payload.

## Tài liệu tham khảo

- [Spring Boot — Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Tracing and Log Correlation IDs](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Cloud Stream — Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring Integration — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html)
- [Spring Cloud Stream — RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Apache Pulsar — Message Consumption and Headers](https://pulsar.apache.org/pulsar-spring/reference/pulsar/message-consumption.html)
- [SLF4J — MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html)
