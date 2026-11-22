# Correlation ID cho request

## 1. Vì sao request cần Correlation ID?

Trong request-reply với Kafka, client gửi một request lên topic, service xử lý nhận request và gửi response về một reply topic. Hai chiều này là hai Kafka record độc lập. Chúng có thể được xử lý bất đồng bộ, xen kẽ với request khác và đến client theo thứ tự khác với thứ tự gửi.

Correlation ID là một định danh được gắn vào request và được trả lại nguyên vẹn trong response. Client dùng ID này để xác định response nào thuộc về request đang chờ.

Ví dụ client gửi đồng thời ba yêu cầu:

```text
Client
  |-- Request A (correlationId = c-101) ---->
  |-- Request B (correlationId = c-102) ---->
  |-- Request C (correlationId = c-103) ---->
                                               Request topic
                                                    |
                                                    v
                                             Service xử lý
                                                    |
  |<-- Reply C (correlationId = c-103) -----------|
  |<-- Reply A (correlationId = c-101) -----------|
  |<-- Reply B (correlationId = c-102) -----------|
  |
  +-- c-101 -> hoàn tất Future A
  +-- c-102 -> hoàn tất Future B
  +-- c-103 -> hoàn tất Future C
```

Response có thể về theo thứ tự C, A, B. Correlation ID giúp client ghép đúng response với Future tương ứng mà không phụ thuộc thứ tự record đến.

## 2. Correlation ID nằm ở đâu trong Kafka record?

Kafka record có key, value và headers. Với Spring Kafka request-reply, correlation ID thường được truyền trong header `KafkaHeaders.CORRELATION_ID`.

Ba header request-reply mặc định thường được sử dụng là:

| Header | Mục đích |
|---|---|
| `KafkaHeaders.CORRELATION_ID` | Ghép response với request tương ứng |
| `KafkaHeaders.REPLY_TOPIC` | Cho responder biết topic cần gửi response |
| `KafkaHeaders.REPLY_PARTITION` | Không bắt buộc; chỉ rõ partition cần gửi response |

Correlation ID là metadata của giao thức request-reply. Nó không phải Kafka record key và không quyết định partition của request. Record key thường phục vụ partitioning/ordering; correlation ID phục vụ ghép cặp request-response.

Trong Kafka header, giá trị được lưu dưới dạng `byte[]`. Nếu dùng chuỗi, hai phía cần thống nhất encoding, thường là UTF-8. Khi dùng `ReplyingKafkaTemplate`, Spring Kafka tự tạo correlation ID nếu request chưa có và quản lý ánh xạ giữa ID với Future đang chờ.

## 3. Phân biệt Correlation ID, Request ID, Event ID và Trace ID

Các định danh này có thể có giá trị giống nhau trong một số thiết kế, nhưng ý nghĩa khác nhau:

| Định danh | Phạm vi | Mục đích |
|---|---|---|
| Correlation ID | Một cặp request-reply hoặc một chuỗi tương tác | Ghép response với request đang chờ |
| Request ID | Một yêu cầu nghiệp vụ | Nhận diện yêu cầu khi log, audit hoặc đối soát |
| Event ID | Một sự kiện được phát ra | Deduplicate và truy vết sự kiện qua nhiều topic/service |
| Trace ID | Một distributed trace | Kết nối các span qua nhiều process và hệ thống |
| Kafka key | Partition của record | Chọn partition và giữ thứ tự theo key trong một partition |

Không dùng Correlation ID làm idempotency key nếu cùng một request có thể được gửi lại với correlation ID mới. Khi cần chống xử lý trùng, dùng `requestId` hoặc idempotency key ổn định trong payload/header nghiệp vụ và lưu trạng thái xử lý ở responder.

Correlation ID cũng không phải thông tin xác thực. Không dùng nó để chứng minh danh tính người gọi hoặc quyền truy cập; responder vẫn phải kiểm tra authorization và tenant context theo cơ chế riêng.

## 4. Request-reply với ReplyingKafkaTemplate

Spring Kafka cung cấp `ReplyingKafkaTemplate<K, V, R>` để gửi request và nhận response bất đồng bộ. Template này quản lý correlation ID và các Future đang chờ, nên ứng dụng không cần tự tạo map correlation cho trường hợp thông thường.

Client cần hai thành phần:

- `ProducerFactory` để gửi request.
- Một reply listener container subscribe reply topic để nhận response.

### Khai báo reply container và template

Ví dụ dùng topic `orders.requests` và `orders.replies`:

```java
@Configuration
public class RequestReplyConfiguration {

    @Bean
    ConcurrentMessageListenerContainer<String, OrderReply> repliesContainer(
            ConcurrentKafkaListenerContainerFactory<String, OrderReply> factory) {

        var container = factory.createContainer("orders.replies");
        container.getContainerProperties().setGroupId("order-reply-client");
        container.setAutoStartup(false);
        return container;
    }

    @Bean
    ReplyingKafkaTemplate<String, OrderRequest, OrderReply> replyingKafkaTemplate(
            ProducerFactory<String, OrderRequest> producerFactory,
            ConcurrentMessageListenerContainer<String, OrderReply> repliesContainer) {

        return new ReplyingKafkaTemplate<>(producerFactory, repliesContainer);
    }
}
```

Trong ví dụ, cấu hình deserializer của reply container phải chuyển value từ topic `orders.replies` thành `OrderReply`. Producer factory của template phải serialize request thành kiểu mà responder đọc được.

`ReplyingKafkaTemplate` quản lý vòng đời reply container. Cấu hình `autoStartup(false)` là cách thường dùng trong ví dụ cấu hình template để template kiểm soát việc khởi động container. Nếu tự quản lý lifecycle, bảo đảm reply container đã chạy và được assign partition trước khi gửi request.

### Gửi request và đợi response

```java
@Service
public class OrderQueryClient {

    private final ReplyingKafkaTemplate<String, OrderRequest, OrderReply> template;

    public OrderQueryClient(
            ReplyingKafkaTemplate<String, OrderRequest, OrderReply> template) {
        this.template = template;
    }

    public OrderReply getOrder(String orderId) throws Exception {
        var request = new OrderRequest(orderId);
        var record = new ProducerRecord<String, OrderRequest>(
                "orders.requests", orderId, request);

        RequestReplyFuture<String, OrderRequest, OrderReply> future =
                template.sendAndReceive(record, Duration.ofSeconds(8));

        // Xác nhận request đã được producer gửi thành công.
        future.getSendFuture().get(5, TimeUnit.SECONDS);

        // Chờ response có correlation ID khớp với request.
        ConsumerRecord<String, OrderReply> reply =
                future.get(8, TimeUnit.SECONDS);

        return reply.value();
    }
}
```

`sendAndReceive()` trả về `RequestReplyFuture`. Future này có hai phần:

- `getSendFuture()`: kết quả gửi request đến Kafka.
- Chính Future `get(...)`: kết quả response tương ứng hoặc exception/timeout.

Nếu producer gửi request thất bại, reply future cũng hoàn tất exceptional theo lỗi gửi, không cần chờ hết reply timeout. Nếu request gửi thành công nhưng responder không trả response, Future kết thúc khi hết reply timeout.

Trong thực tế, nên cấu hình timeout theo SLA của nghiệp vụ và xử lý riêng `TimeoutException`, `ExecutionException` và `InterruptedException`. Không để request-reply chờ vô hạn.

## 5. Chờ reply container được assign trước khi gửi

Nếu reply container dùng `auto.offset.reset=latest`, client có thể gửi request ngay lúc ứng dụng vừa khởi động, trước khi reply consumer được assign partition. Responder xử lý rất nhanh và gửi response trước khi client bắt đầu đọc reply topic; response có thể bị bỏ lỡ.

Từ Spring Kafka 2.8.8, `ReplyingKafkaTemplate` cung cấp `waitForAssignment(Duration)` để chờ reply container sẵn sàng:

```java
@Component
public class RequestReplyStartupCheck implements ApplicationRunner {

    private final ReplyingKafkaTemplate<String, OrderRequest, OrderReply> template;

    public RequestReplyStartupCheck(
            ReplyingKafkaTemplate<String, OrderRequest, OrderReply> template) {
        this.template = template;
    }

    @Override
    public void run(ApplicationArguments args) {
        boolean assigned = template.waitForAssignment(Duration.ofSeconds(10));
        if (!assigned) {
            throw new IllegalStateException("Reply container was not assigned in time");
        }
    }
}
```

Chỉ gửi request sau khi reply container đã được assign. Nếu dùng manual partition assignment, thời gian chờ cần lớn hơn `pollTimeout` vì callback thông báo assignment chỉ xảy ra sau lần poll đầu tiên.

## 6. Responder dùng @KafkaListener và @SendTo

Ở phía responder, `@KafkaListener` nhận request và trả về response. `@SendTo` chỉ định nơi gửi response.

Nếu dùng `@SendTo` không có giá trị, Spring Kafka lấy reply topic từ header `KafkaHeaders.REPLY_TOPIC` của request. Đây là cách phù hợp với `ReplyingKafkaTemplate`, vì template đã thêm reply topic header vào request.

```java
@Component
public class OrderQueryResponder {

    private final OrderQueryService orderQueryService;

    public OrderQueryResponder(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @KafkaListener(topics = "orders.requests", groupId = "order-query-service")
    @SendTo
    public OrderReply handle(OrderRequest request) {
        return orderQueryService.findOrder(request.orderId());
    }
}
```

Listener container factory phía responder cần có `KafkaTemplate` trong thuộc tính `replyTemplate` để gửi kết quả. Spring Boot thường tự cấu hình template này nếu có bean phù hợp; nếu tự tạo factory, phải gọi `factory.setReplyTemplate(kafkaTemplate)`.

Ví dụ khai báo factory tường minh:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderRequest> requestListenerFactory(
        ConsumerFactory<String, OrderRequest> consumerFactory,
        KafkaTemplate<String, OrderReply> replyTemplate) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderRequest>();
    factory.setConsumerFactory(consumerFactory);
    factory.setReplyTemplate(replyTemplate);
    return factory;
}
```

Gắn factory này vào `@KafkaListener` bằng `containerFactory = "requestListenerFactory"`. Producer factory đứng sau `replyTemplate` cần serializer cho `OrderReply`.

Spring Kafka listener infrastructure echo correlation ID từ request sang response và dùng reply topic header để định tuyến. Vì vậy client `ReplyingKafkaTemplate` có thể nhận response, đọc correlation ID và hoàn tất đúng Future.

Nếu dùng `@SendTo("orders.replies")`, responder gửi đến topic cố định. Reply container phía client phải subscribe đúng topic đó. Với request-reply nhiều client instance, topic/partition reply cần được thiết kế để response đến đúng client gửi request.

## 7. Đọc correlation ID ở responder

Thông thường, khi listener trả về payload đơn giản và dùng `@SendTo`, Spring Kafka tự echo correlation ID. Nếu cần ghi log hoặc tự kiểm soát metadata, có thể nhận header trong tham số:

```java
@KafkaListener(topics = "orders.requests", groupId = "order-query-service")
@SendTo
public OrderReply handle(
        OrderRequest request,
        @Header(KafkaHeaders.CORRELATION_ID) byte[] correlationId,
        @Header(KafkaHeaders.REPLY_TOPIC) byte[] replyTopic) {

    String correlation = new String(correlationId, StandardCharsets.UTF_8);
    String replyTopicName = new String(replyTopic, StandardCharsets.UTF_8);

    log.info("Handling orderId={}, correlationId={}, replyTopic={}",
            request.orderId(), correlation, replyTopicName);

    return orderQueryService.findOrder(request.orderId());
}
```

Trong request-reply mặc định, `KafkaHeaders.CORRELATION_ID` và `KafkaHeaders.REPLY_TOPIC` được truyền dưới dạng byte header. Nếu dùng custom header mapper hoặc custom header name, kiểu tham số và cách chuyển đổi có thể khác; cần thống nhất giữa producer và consumer.

Không cần tự tạo correlation ID mới ở responder. Response phải echo đúng correlation ID của request. Nếu thay ID, client không tìm thấy Future tương ứng và response bị xem là không khớp.

## 8. Trả về Message<?> và tự đặt reply headers

Nếu listener trả về một payload thông thường, `@SendTo` có thể tự định tuyến và echo correlation ID. Nếu listener trả về `Message<?>`, ứng dụng có thể cần thiết lập các header của response.

Ví dụ:

```java
@KafkaListener(topics = "orders.requests", groupId = "order-query-service")
@SendTo
public Message<OrderReply> handle(OrderRequest request) {
    OrderReply reply = orderQueryService.findOrder(request.orderId());

    return MessageBuilder.withPayload(reply)
            .setHeader(KafkaHeaders.KEY, request.orderId())
            .build();
}
```

Từ Spring Kafka 2.5, framework có thể tự bổ sung các header reply còn thiếu: topic lấy từ `@SendTo` hoặc `KafkaHeaders.REPLY_TOPIC` của request; correlation ID và reply partition được echo nếu có trong request. Với phiên bản cũ hơn 2.5, nếu trả `Message<?>`, ứng dụng cần chủ động đặt reply topic và correlation ID.

Nếu tự gửi response bằng `KafkaTemplate` thay vì trả về qua `@SendTo`, ứng dụng phải copy correlation ID từ request sang response và gửi đúng reply topic/partition. Không dựa vào cơ chế echo tự động của listener adapter khi tự publish bằng template riêng.

## 9. Ba header request-reply và cách định tuyến

`ReplyingKafkaTemplate` mặc định dùng ba header:

| Header | Nội dung | Cách dùng |
|---|---|---|
| `KafkaHeaders.CORRELATION_ID` | ID của request | Client dùng để tra Future đang chờ |
| `KafkaHeaders.REPLY_TOPIC` | Tên reply topic dưới dạng bytes | Responder biết topic để gửi response |
| `KafkaHeaders.REPLY_PARTITION` | Số partition dạng 4-byte integer big-endian | Responder gửi response vào partition được client yêu cầu |

Nếu reply container chỉ subscribe một topic hoặc một `TopicPartitionOffset`, template có thể phát hiện reply topic/partition từ container và tự thêm header. Nếu container subscribe nhiều topic hoặc nhiều partition phức tạp, ứng dụng cần cấu hình reply headers tường minh.

Khi dùng `KafkaHeaders.REPLY_PARTITION`, reply container phải được cấu hình đọc đúng partition. Với một số cách dùng fixed partition, container phải dùng manual partition assignment thay vì Kafka group management. Không đặt reply partition tùy ý nếu client không đọc partition đó.

## 10. Nhiều client instance và reply topic dùng chung

Nếu nhiều instance của client cùng dùng một reply topic, phải chọn chiến lược để mỗi request nhận được response đúng instance.

### Mỗi instance một reply topic riêng

Ví dụ:

```text
client-1 -> request header reply topic = replies.client-1
client-2 -> request header reply topic = replies.client-2
client-3 -> request header reply topic = replies.client-3
```

Mỗi instance chỉ đọc reply topic của chính nó. Cách này cô lập traffic nhưng cần quản lý topic và quyền truy cập theo instance.

### Một reply topic dùng chung, mỗi instance một group ID riêng

Mỗi client instance dùng một `group.id` khác nhau khi đọc cùng reply topic. Vì các group độc lập, mọi instance đều nhận tất cả response; chỉ instance có correlation ID đang chờ mới hoàn tất Future, các instance khác bỏ qua response không khớp.

Cách này đơn giản hơn về số topic nhưng tăng network và consumer traffic. Khi dùng shared reply topic, có thể bật `ReplyingKafkaTemplate.setSharedReplyTopic(true)` để các reply không khớp được log ở mức DEBUG thay vì ERROR.

### Mỗi instance một reply partition

Có thể dùng chung topic nhưng cấp một partition riêng cho từng client instance bằng `KafkaHeaders.REPLY_PARTITION`. Reply container của từng instance phải được gán cố định vào partition tương ứng. Cách này giảm việc mọi instance nhận mọi response nhưng cần quản lý partition assignment.

Không dùng cùng một group ID cho tất cả client instance khi muốn mỗi instance nhận response của request riêng. Consumer group sẽ chia partition giữa các member, dẫn đến response có thể đến một instance khác với instance đang giữ Future.

## 11. Timeout và response đến muộn

Request-reply không đảm bảo responder luôn trả response. Có thể xảy ra:

- Request không được xử lý do consumer dừng hoặc lag.
- Responder xử lý quá thời hạn client chờ.
- Responder lỗi trước khi publish response.
- Reply topic/partition cấu hình sai.
- Response đã được gửi nhưng client reply container chưa sẵn sàng.
- Client đã timeout hoặc shutdown trước khi response đến.

`ReplyingKafkaTemplate` có default reply timeout 5 giây; có thể truyền `Duration` trực tiếp vào `sendAndReceive(record, replyTimeout)` để chọn timeout cho từng request. Khi hết thời gian, Future hoàn tất với timeout exception.

Timeout ở client không hủy request đã được ghi vào Kafka và không dừng responder. Responder có thể vẫn xử lý xong và gửi response sau đó. Response đến muộn không còn Future đang chờ để hoàn tất; template xem đó là reply không mong đợi và có thể ghi log.

Vì vậy:

- Chọn timeout dựa trên SLA và thời gian xử lý p95/p99.
- Có giới hạn số request đang chờ để tránh giữ quá nhiều Future trong bộ nhớ.
- Xử lý timeout bằng trạng thái nghiệp vụ rõ ràng; không mặc định request chưa được thực hiện.
- Nếu caller retry request sau timeout, dùng request ID/idempotency key ổn định để responder tránh lặp side effect.
- Theo dõi số reply timeout và late/unmatched reply.

## 12. Xử lý lỗi response

Response có thể chứa kết quả thành công hoặc thông tin lỗi nghiệp vụ. Có thể biểu diễn lỗi trong DTO:

```java
public record OrderReply(
        String orderId,
        String status,
        String errorCode,
        String errorMessage) {

    public boolean successful() {
        return errorCode == null;
    }
}
```

Nếu muốn `ReplyingKafkaTemplate` hoàn tất Future bằng exception khi response có header báo lỗi, có thể cấu hình `replyErrorChecker` (từ Spring Kafka 2.6.7):

```java
replyingKafkaTemplate.setReplyErrorChecker(record -> {
    Header errorHeader = record.headers().lastHeader("server-error");
    if (errorHeader == null) {
        return null;
    }
    String message = new String(errorHeader.value(), StandardCharsets.UTF_8);
    return new IllegalStateException("Responder failed: " + message);
});
```

Khi checker trả về exception, Future hoàn tất exceptional. Cần thống nhất tên header và format lỗi giữa hai phía. Không đưa stack trace, token hoặc dữ liệu nhạy cảm vào header lỗi.

Nếu reply deserializer có thể thất bại, cân nhắc `ErrorHandlingDeserializer` làm wrapper. `ReplyingKafkaTemplate` có thể hoàn tất Future exceptional khi phát hiện `DeserializationException`; client cần xử lý `ExecutionException` và nguyên nhân bên trong.

## 13. Tự triển khai correlation map khi không dùng ReplyingKafkaTemplate

Trong trường hợp responder không dùng Spring Kafka hoặc giao thức reply tùy chỉnh, có thể tự quản lý map từ correlation ID đến `CompletableFuture`. Đây là phương án nâng cao; với ứng dụng Spring-to-Spring thông thường, `ReplyingKafkaTemplate` ít lỗi vòng đời hơn.

### Gửi request và đăng ký Future trước khi publish

```java
@Component
public class ManualRequestClient {

    private final KafkaTemplate<String, OrderRequest> kafkaTemplate;
    private final ConcurrentMap<String, CompletableFuture<OrderReply>> pending =
            new ConcurrentHashMap<>();

    public ManualRequestClient(KafkaTemplate<String, OrderRequest> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<OrderReply> request(OrderRequest request) {
        String correlationId = UUID.randomUUID().toString();
        var responseFuture = new CompletableFuture<OrderReply>();

        // Đăng ký trước khi gửi để tránh response nhanh đến trước khi map có entry.
        pending.put(correlationId, responseFuture);

        var record = new ProducerRecord<String, OrderRequest>(
                "orders.requests", request.orderId(), request);
        record.headers().add(new RecordHeader(
                KafkaHeaders.CORRELATION_ID,
                correlationId.getBytes(StandardCharsets.UTF_8)));
        record.headers().add(new RecordHeader(
                KafkaHeaders.REPLY_TOPIC,
                "orders.replies".getBytes(StandardCharsets.UTF_8)));

        kafkaTemplate.send(record).whenComplete((result, error) -> {
            if (error != null) {
                pending.remove(correlationId, responseFuture);
                responseFuture.completeExceptionally(error);
            }
        });

        responseFuture.orTimeout(8, TimeUnit.SECONDS)
                .whenComplete((reply, error) -> pending.remove(correlationId, responseFuture));

        return responseFuture;
    }

    @KafkaListener(topics = "orders.replies", groupId = "manual-reply-client")
    public void onReply(ConsumerRecord<String, OrderReply> record) {
        Header header = record.headers().lastHeader(KafkaHeaders.CORRELATION_ID);
        if (header == null) {
            log.warn("Reply without correlation ID: topic={}, partition={}, offset={}",
                    record.topic(), record.partition(), record.offset());
            return;
        }

        String correlationId = new String(header.value(), StandardCharsets.UTF_8);
        CompletableFuture<OrderReply> future = pending.remove(correlationId);
        if (future == null) {
            log.debug("Late or unmatched reply: correlationId={}", correlationId);
            return;
        }

        future.complete(record.value());
    }
}
```

Ví dụ minh họa các nguyên tắc quan trọng:

1. Dùng ID duy nhất cho từng request đang chờ.
2. Đăng ký Future vào map trước khi publish request.
3. Thêm correlation ID và reply topic vào header.
4. Xóa map entry khi send lỗi, timeout hoặc nhận response.
5. Nếu không tìm thấy Future, xem response là late/unmatched thay vì ghép với request khác.

Ví dụ listener dùng `groupId = "manual-reply-client"` giả định chỉ có một client instance. Nếu scale nhiều instance, mỗi instance cần group ID riêng để tất cả nhận reply và tự lọc theo map correlation, hoặc dùng reply partition/topic riêng. Dùng chung group ID sẽ chia reply giữa các instance và có thể giao response cho instance không giữ Future.

Trong code production, cần bổ sung xử lý shutdown để hoàn tất exceptional các Future còn pending, giới hạn số Future đang chờ, timeout scheduler và metric cho map size. Không để map tăng vô hạn khi responder ngừng hoạt động.

## 14. Tùy chỉnh tên correlation header

Mặc định Spring Kafka dùng `KafkaHeaders.CORRELATION_ID`. Có thể tùy chỉnh tên header trên `ReplyingKafkaTemplate` thông qua thuộc tính `correlationHeaderName` (cùng các thuộc tính reply topic/partition header) từ Spring Kafka 2.3.

Điều này hữu ích khi client giao tiếp với responder không dùng Spring hoặc đã có giao thức header riêng. Từ Spring Kafka 3.0, listener container factory cũng có thể cấu hình `correlationHeaderName` để echo custom correlation header trở lại response. Trước đó, responder phải tự copy custom header.

Khi tùy chỉnh, cả client và responder phải dùng đúng tên header và cùng quy tắc encoding. Không đổi tên header ở một phía rồi kỳ vọng phía còn lại tự nhận ra.

## 15. Correlation ID và tracing

Correlation ID giúp ghép request và reply trong giao thức Kafka. Trace ID giúp tracing backend liên kết các span giữa client, broker-facing code và responder. Hai giá trị có thể được truyền cùng nhau:

```text
Request headers:
  kafka_correlationId = "c-101"
  traceparent         = "00-<trace-id>-<span-id>-01"
  request-id          = "req-9001"

Reply headers:
  kafka_correlationId = "c-101"
  traceparent         = context của span xử lý reply
  request-id          = "req-9001" (nếu hợp đồng cần echo)
```

Không thay thế tracing instrumentation bằng correlation ID. Correlation ID thường ổn định trong một request-reply pair; trace context có thể tạo span mới cho mỗi bước và cần được propagate theo chuẩn tracing như W3C Trace Context.

Không dùng correlation ID làm metric label vì mỗi request có thể có một ID riêng, tạo cardinality rất cao. Đưa ID vào log hoặc trace; metric nên dùng topic, listener, outcome và exception class với tập giá trị hữu hạn.

## 16. Request-reply có phải RPC đồng bộ không?

`ReplyingKafkaTemplate` cung cấp API chờ response nên code client có thể trông giống gọi RPC. Tuy nhiên, Kafka vẫn là hệ thống messaging bất đồng bộ:

- Request được ghi vào log và responder xử lý khi consumer nhận được.
- Client chờ Future, nhưng responder có thể xử lý sau một khoảng thời gian.
- Timeout của client không hủy record trong Kafka.
- Client retry có thể tạo request trùng nếu responder đã xử lý request đầu tiên.
- Reply có thể đến muộn hoặc không đến.

Request-reply phù hợp với thao tác cần phản hồi trong thời gian giới hạn, ví dụ tra cứu hoặc xác nhận ngắn. Với workflow dài, cần nhiều bước, hoặc không có SLA phản hồi chặt, nên dùng event-driven workflow và phát event kết quả thay vì giữ một request thread chờ lâu.

Nếu gọi request-reply từ HTTP controller, tránh chặn servlet thread quá lâu. Có thể trả về async response hoặc dùng `CompletableFuture`/reactive boundary phù hợp. Giới hạn số request đang chờ để tránh làm cạn thread và bộ nhớ khi responder chậm.

## 17. Kiểm thử correlation ID

Kiểm thử tích hợp nên xác minh cả việc truyền header và ghép đúng Future:

1. **Một request, một reply:** xác nhận template thêm correlation ID, reply có cùng ID và Future hoàn tất với đúng payload.
2. **Nhiều request đồng thời:** gửi nhiều request với correlation ID khác nhau; cố tình trả response theo thứ tự đảo và xác nhận mỗi Future nhận đúng response.
3. **Correlation ID thiếu:** kiểm tra template tự sinh ID và listener vẫn trả reply đúng.
4. **Correlation ID tùy chỉnh:** đặt header trước khi gửi và xác nhận responder echo đúng byte value.
5. **Sai correlation ID:** responder trả một ID khác; xác nhận Future gốc không nhận nhầm response.
6. **Reply timeout:** không cho responder trả lời; xác nhận Future timeout theo cấu hình.
7. **Reply đến muộn:** cho responder trả sau timeout; xác nhận client không ghép reply đó vào request khác.
8. **Send failure:** dừng broker hoặc làm producer lỗi; xác nhận send future và reply future hoàn tất exceptional.
9. **Reply container chưa assign:** xác nhận `waitForAssignment()` ngăn gửi request trước khi consumer sẵn sàng.
10. **Nhiều client instance:** kiểm tra reply topic/group/partition strategy để response chỉ được xử lý bởi instance đang chờ.
11. **Duplicate request:** gửi lại cùng request ID và xác nhận responder idempotent.
12. **Reply deserialization/error header:** xác nhận client nhận exception thay vì treo Future.

Trong test, nên dùng `spring-kafka-test` hoặc Testcontainers Kafka. Ghi nhận correlation ID, topic, partition, offset và event/request ID để xác định response được ghép đúng. Không chỉ kiểm tra listener có được gọi; cần xác nhận đúng Future nhận đúng response.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Future timeout dù responder đã xử lý | Reply thiếu correlation ID hoặc không echo đúng ID | Kiểm tra `KafkaHeaders.CORRELATION_ID` trên request và reply |
| Response được gửi nhưng client không nhận | Reply topic/partition header sai hoặc reply container chưa assign | Kiểm tra `REPLY_TOPIC`, `REPLY_PARTITION` và `waitForAssignment()` |
| Nhiều client nhận nhầm/không nhận reply | Dùng chung group ID cho các reply consumer instance | Dùng reply topic riêng, group ID riêng trên shared topic hoặc partition riêng |
| Response đến sai Future | Correlation ID bị trùng hoặc bị thay đổi | Dùng ID duy nhất cho mỗi request đang chờ và echo nguyên vẹn |
| Request timeout nhưng nghiệp vụ vẫn chạy | Timeout không hủy request đã được publish | Dùng request ID/idempotency key để chống xử lý trùng khi caller retry |
| Future pending tăng liên tục | Không cleanup khi timeout/send failure/shutdown | Xóa map entry hoặc dùng lifecycle quản lý Future của template |
| Không có reply khi dùng `@SendTo` | Listener factory thiếu `replyTemplate` | Cấu hình `KafkaTemplate` vào `factory.setReplyTemplate(...)` |
| Listener trả `Message<?>` nhưng reply không được ghép | Reply message thiếu topic/correlation header ở phiên bản cũ hoặc custom send | Kiểm tra header; từ 2.5 framework có thể tự echo header mặc định nếu thiếu |
| Reply deserialization lỗi làm client không rõ nguyên nhân | Reply deserializer ném exception | Dùng `ErrorHandlingDeserializer` và xử lý `ExecutionException` |
| Dùng correlation ID làm Kafka key | Nhầm mục đích định tuyến với ghép cặp | Dùng key theo aggregate; giữ correlation ID trong header |

## 19. Quy trình thiết kế request-reply

1. Xác định thao tác thực sự cần response trong thời gian giới hạn; workflow dài nên dùng event.
2. Chọn `ReplyingKafkaTemplate` nếu client và responder dùng Spring Kafka; chỉ tự quản lý map khi có giao thức đặc thù.
3. Chọn correlation ID duy nhất cho từng request đang chờ; giữ nguyên ID trên response.
4. Xác định reply topic/partition và cấu hình reply listener container.
5. Chờ reply container được assign trước khi gửi request, nhất là khi dùng `auto.offset.reset=latest`.
6. Cấu hình `@KafkaListener` với `@SendTo` và reply template phù hợp.
7. Đặt timeout theo SLA và xử lý send failure, reply timeout, late reply, deserialization error.
8. Dùng request ID/idempotency key riêng nếu caller có thể gửi lại request.
9. Nếu nhiều client instance, thiết kế reply topic/group/partition để mỗi response đến đúng instance.
10. Kiểm thử nhiều request đồng thời, response đảo thứ tự, timeout, restart và duplicate.

## 20. Tổng kết

- Correlation ID là định danh để ghép response với request tương ứng khi nhiều request đang chạy đồng thời.
- Spring Kafka dùng `KafkaHeaders.CORRELATION_ID`; request-reply còn dùng `REPLY_TOPIC` và tùy chọn `REPLY_PARTITION`.
- `ReplyingKafkaTemplate` tự quản lý correlation ID và Future; `sendAndReceive()` trả `RequestReplyFuture` có send future và reply future.
- `@KafkaListener` kết hợp `@SendTo` có thể gửi response về reply topic trong request header và echo correlation ID.
- `waitForAssignment()` từ Spring Kafka 2.8.8 giúp tránh gửi request trước khi reply consumer sẵn sàng.
- Timeout không hủy request đã gửi; response muộn có thể không còn Future tương ứng.
- Correlation ID khác request ID, event ID, trace ID và Kafka key; dùng idempotency key riêng để chống xử lý trùng.
- Nhiều client instance cần thiết kế reply topic, group ID hoặc partition assignment đúng để response về đúng instance.
- Nếu tự triển khai correlation map, phải cleanup khi send lỗi, timeout, reply và shutdown.

Correlation ID là thành phần cốt lõi để request-reply hoạt động đúng khi các request được xử lý bất đồng bộ và response có thể đến không theo thứ tự gửi. Khi kết hợp `ReplyingKafkaTemplate`, reply topic, `@SendTo` và timeout rõ ràng, ứng dụng Spring Kafka có thể ghép response chính xác và kiểm soát được các trường hợp reply muộn hoặc thất lạc.

## Tài liệu tham khảo

- [Spring Kafka Reference — Sending Messages and ReplyingKafkaTemplate](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka Reference — Forwarding Listener Results using @SendTo](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/annotation-send-to.html)
- [Spring Kafka API — ReplyingKafkaTemplate](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/requestreply/ReplyingKafkaTemplate.html)
