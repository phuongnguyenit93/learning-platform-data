# Khai báo reply template

## Mục tiêu của bài học

Trong chương **Request-reply**, bài này hướng dẫn khai báo và sử dụng `ReplyingKafkaTemplate` để gửi một request tới Kafka rồi chờ response tương ứng. Spring Kafka kết hợp một producer gửi request, một consumer container lắng nghe reply topic và correlation ID để ghép response với request ban đầu.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Request-reply là một cách phối hợp giữa producer và consumer khi ứng dụng cần kết quả phản hồi, bên cạnh mô hình event-driven bất đồng bộ thông thường.

Sau bài học, người học có thể:

- Giải thích request-reply trên Kafka và các thành phần tham gia.
- Phân biệt `KafkaTemplate` với `ReplyingKafkaTemplate`.
- Khai báo producer factory cho request và consumer container cho reply.
- Cấu hình reply template và timeout.
- Gửi request bằng `sendAndReceive` và đọc response.
- Viết listener xử lý request và trả lời bằng `@SendTo`.
- Hiểu correlation ID, reply topic và reply partition.
- Thiết kế consumer group cho reply topic khi chạy nhiều instance.
- Xử lý timeout, lỗi gửi, reply đến muộn và duplicate.
- Kiểm thử toàn bộ luồng request-reply với Kafka.

## 1. Request-reply trên Kafka là gì?

Kafka được thiết kế chủ yếu cho giao tiếp bất đồng bộ qua topic. Producer gửi record mà không cần chờ consumer xử lý xong. Trong một số trường hợp, ứng dụng cần gửi yêu cầu và nhận kết quả tương ứng, chẳng hạn:

- Dịch vụ Order hỏi Pricing Service về giá hiện tại.
- API cần yêu cầu một worker kiểm tra hạn mức và chờ kết quả.
- Một ứng dụng cần tra cứu trạng thái xử lý từ service khác.
- Một command cần phản hồi chấp nhận hoặc từ chối.

Request-reply xây dựng một quy ước trên Kafka:

1. Client gửi request record vào request topic.
2. Request mang thông tin reply topic để server biết nơi gửi phản hồi.
3. Server đọc request, thực hiện nghiệp vụ và gửi response vào reply topic.
4. Client nhận response và dùng correlation ID để ghép với request đang chờ.

~~~mermaid
sequenceDiagram
    participant C as Request Client
    participant R as Request Topic
    participant S as Request Service
    participant P as Reply Topic
    C->>R: Request + reply topic + correlation ID
    R->>S: @KafkaListener nhận request
    S->>S: Xử lý nghiệp vụ
    S->>P: Response + correlation ID
    P->>C: Reply container nhận response
    C->>C: Ghép response với request
~~~

Kafka không có request-reply protocol riêng ở broker. Spring Kafka xây dựng cơ chế này bằng các topic, headers và consumer container.

## 2. KafkaTemplate và ReplyingKafkaTemplate

`KafkaTemplate<K,V>` là API gửi record tới Kafka. Lệnh gửi trả về future để theo dõi kết quả gửi tới broker, nhưng future này không đại diện cho kết quả xử lý của consumer.

`ReplyingKafkaTemplate<K,V,R>` mở rộng mô hình gửi bằng cách chờ một reply tương ứng. Ba generic type có ý nghĩa:

- `K`: kiểu key của request và reply.
- `V`: kiểu value của request.
- `R`: kiểu value của reply.

Ví dụ:

~~~java
ReplyingKafkaTemplate<String, OrderRequest, OrderReply>
~~~

Trong đó:

- Request key là `String`.
- Request payload là `OrderRequest`.
- Reply payload là `OrderReply`.

| Thành phần | Vai trò |
|---|---|
| KafkaTemplate | Gửi record và theo dõi broker acknowledgment |
| ReplyingKafkaTemplate | Gửi request và chờ reply tương ứng |
| Request topic | Nơi server nhận yêu cầu |
| Reply topic | Nơi client nhận phản hồi |
| Reply listener container | Consumer container lắng nghe reply topic |
| Correlation ID | Ghép response với request đang chờ |

Không nên dùng `KafkaTemplate.send()` rồi coi send acknowledgment là phản hồi nghiệp vụ. Broker xác nhận đã nhận record không có nghĩa service xử lý request thành công.

## 3. Thiết kế request và reply payload

Nên định nghĩa request và reply rõ ràng, có mã định danh nghiệp vụ nếu cần truy vết.

Ví dụ:

~~~java
public record OrderRequest(
    String requestId,
    String orderId,
    String customerId
) {
}
~~~

~~~java
public record OrderReply(
    String requestId,
    boolean accepted,
    String message,
    String invoiceId
) {
}
~~~

`requestId` là mã nghiệp vụ trong payload. Nó có thể hữu ích cho log, tracing và idempotency. Correlation ID của Kafka là metadata giao tiếp để Spring ghép reply với future đang chờ. Hai giá trị có thể cùng nhau nhưng phục vụ hai mục đích khác nhau.

Không nên chỉ dựa vào correlation ID để chống xử lý trùng. Nếu request được giao lại, server vẫn cần idempotency theo request ID hoặc command ID khi nghiệp vụ tạo side effect.

## 4. Các headers quan trọng

Spring Kafka sử dụng một số headers cho request-reply:

| Header | Ý nghĩa |
|---|---|
| `KafkaHeaders.CORRELATION_ID` | Mã ghép reply với request |
| `KafkaHeaders.REPLY_TOPIC` | Topic mà server cần gửi reply |
| `KafkaHeaders.REPLY_PARTITION` | Partition đích của reply nếu được chỉ định |
| `KafkaHeaders.RECEIVED_KEY` | Key của record nhận được trong message conversion |
| `KafkaHeaders.RECEIVED_TOPIC` | Topic của record đã nhận |

`ReplyingKafkaTemplate` tự tạo correlation ID nếu request chưa có header phù hợp và thêm thông tin reply destination theo cấu hình của template/container. Khi response quay lại, template dùng correlation ID để tìm future đang chờ.

Correlation ID phải được giữ nguyên từ request sang reply. Nếu server tạo message response mới nhưng làm mất header correlation ID, client không thể ghép response với request ban đầu.

Không tự ghi đè các header do template quản lý nếu không có lý do rõ ràng. Nếu ứng dụng cần correlation ID riêng, hãy thiết kế quy ước và bảo đảm cả client lẫn server tuân thủ.

## 5. Khai báo request producer và reply consumer

Một `ReplyingKafkaTemplate` cần hai thành phần chính:

- `ProducerFactory<K,V>` để gửi request.
- `GenericMessageListenerContainer<K,R>` để nhận reply.

Ví dụ giả định key là String, request là OrderRequest và reply là OrderReply.

### 5.1. ProducerFactory cho request

~~~java
@Bean
public ProducerFactory<String, OrderRequest> orderRequestProducerFactory() {
    Map<String, Object> properties = new HashMap<>();

    properties.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
    );
    properties.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
    );
    properties.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class
    );

    return new DefaultKafkaProducerFactory<>(properties);
}
~~~

Producer factory này serialize request key và request payload. Trong dự án thực tế, có thể bind bootstrap server và các producer properties từ cấu hình môi trường; ví dụ trên minh họa các thuộc tính cốt lõi để dễ thấy serializer nào được sử dụng.

### 5.2. ConsumerFactory cho reply

Reply container cần consumer factory có value deserializer dành cho `OrderReply`:

~~~java
@Bean
public ConsumerFactory<String, OrderReply> orderReplyConsumerFactory() {
    Map<String, Object> properties = new HashMap<>();

    properties.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
    );
    properties.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    properties.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class
    );
    properties.put(
        JsonDeserializer.VALUE_DEFAULT_TYPE,
        OrderReply.class.getName()
    );
    properties.put(
        JsonDeserializer.TRUSTED_PACKAGES,
        "com.example.orders"
    );

    return new DefaultKafkaConsumerFactory<>(properties);
}
~~~

Các thuộc tính JSON cần điều chỉnh theo package và cấu hình type mapping của ứng dụng. Chỉ thêm package tin cậy cần thiết; không mở rộng trusted packages một cách tùy tiện trong môi trường production.

### 5.3. Reply listener container

Tạo container lắng nghe reply topic:

~~~java
@Bean
public ConcurrentMessageListenerContainer<String, OrderReply>
        orderRepliesContainer(
                ConcurrentKafkaListenerContainerFactory<String, OrderReply>
                        orderReplyContainerFactory,
                Environment environment) {

    ConcurrentMessageListenerContainer<String, OrderReply> container =
        orderReplyContainerFactory.createContainer("commerce.order.replies");

    String replyGroupId =
        environment.getRequiredProperty("app.kafka.reply-group-id");

    container.getContainerProperties().setGroupId(replyGroupId);
    return container;
}
~~~

Container được tạo từ factory dành cho reply payload. Group ID cần được chọn theo mô hình triển khai nhiều instance; phần sau sẽ giải thích vì sao không nên tùy tiện dùng chung group ID cho mọi client instance.

Factory dùng ở đây cần được cấu hình với `orderReplyConsumerFactory`. Có thể khai báo factory chuyên biệt:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderReply>
        orderReplyContainerFactory(
                ConsumerFactory<String, OrderReply> orderReplyConsumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderReply>();

    factory.setConsumerFactory(orderReplyConsumerFactory);
    return factory;
}
~~~

### 5.4. Khai báo ReplyingKafkaTemplate

Khi đã có request producer factory và reply container, tạo template:

~~~java
@Bean
public ReplyingKafkaTemplate<String, OrderRequest, OrderReply>
        orderReplyingKafkaTemplate(
                ProducerFactory<String, OrderRequest> orderRequestProducerFactory,
                ConcurrentMessageListenerContainer<String, OrderReply>
                        orderRepliesContainer) {

    var template = new ReplyingKafkaTemplate<>(
        orderRequestProducerFactory,
        orderRepliesContainer
    );

    template.setDefaultReplyTimeout(Duration.ofSeconds(10));
    return template;
}
~~~

`setDefaultReplyTimeout` đặt thời gian chờ mặc định cho reply. Chọn timeout theo SLA của request và thời gian xử lý thực tế của service. Không nên dùng timeout quá ngắn khiến client liên tục báo lỗi dù server vẫn đang xử lý bình thường.

Reply container phải được khởi động và subscribe reply topic trước khi client gửi request. Trong Spring application, container được quản lý bởi lifecycle của bean. Có thể kiểm tra trạng thái container trong integration test và khi startup nếu cần.

## 6. Gửi request và nhận reply

Client tạo record gửi tới request topic:

~~~java
@Service
public class OrderRequestClient {

    private final ReplyingKafkaTemplate<String, OrderRequest, OrderReply>
        replyingKafkaTemplate;

    public OrderRequestClient(
            ReplyingKafkaTemplate<String, OrderRequest, OrderReply>
                    replyingKafkaTemplate) {
        this.replyingKafkaTemplate = replyingKafkaTemplate;
    }

    public OrderReply request(OrderRequest request) throws Exception {
        ProducerRecord<String, OrderRequest> record =
            new ProducerRecord<>(
                "commerce.order.requests",
                request.orderId(),
                request
            );

        RequestReplyFuture<String, OrderRequest, OrderReply> future =
            replyingKafkaTemplate.sendAndReceive(record);

        ConsumerRecord<String, OrderReply> replyRecord =
            future.get(12, TimeUnit.SECONDS);

        return replyRecord.value();
    }
}
~~~

`sendAndReceive` gửi request và trả về `RequestReplyFuture`. Future hoàn tất khi template nhận được reply có correlation ID phù hợp hoặc khi xảy ra lỗi/timeout theo cấu hình.

Có thể theo dõi riêng kết quả gửi request:

~~~java
SendResult<String, OrderRequest> sendResult =
    future.getSendFuture().get(5, TimeUnit.SECONDS);
~~~

Send future cho biết producer đã gửi request thành công tới broker theo acknowledgment configuration. Reply future cho biết response đã được nhận. Hai mốc này khác nhau.

Trong service production, nên xử lý riêng các tình huống:

- Gửi request thất bại.
- Không nhận reply trong thời gian chờ.
- Reply future hoàn tất bất thường.
- Thread bị interrupt.
- Reply có nội dung từ chối nghiệp vụ.

Không nên bắt mọi exception rồi trả về một response thành công giả. Timeout và lỗi gửi cần được biểu diễn rõ cho caller hoặc chuyển thành trạng thái nghiệp vụ thích hợp.

## 7. Khai báo reply template ở phía server

Server cần consumer factory để đọc request và producer template để gửi reply.

Consumer factory phía server phải deserialize đúng kiểu request:

~~~java
@Bean
public ConsumerFactory<String, OrderRequest> orderRequestConsumerFactory() {
    Map<String, Object> properties = new HashMap<>();

    properties.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
    );
    properties.put(
        ConsumerConfig.GROUP_ID_CONFIG,
        "order-command-service"
    );
    properties.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    properties.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class
    );
    properties.put(
        JsonDeserializer.VALUE_DEFAULT_TYPE,
        OrderRequest.class.getName()
    );
    properties.put(
        JsonDeserializer.TRUSTED_PACKAGES,
        "com.example.orders"
    );

    return new DefaultKafkaConsumerFactory<>(properties);
}
~~~

~~~java
@Bean
public ProducerFactory<String, OrderReply> orderReplyProducerFactory() {
    Map<String, Object> properties = new HashMap<>();

    properties.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
    );
    properties.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
    );
    properties.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class
    );

    return new DefaultKafkaProducerFactory<>(properties);
}

@Bean
public KafkaTemplate<String, OrderReply> orderReplyKafkaTemplate(
        ProducerFactory<String, OrderReply> orderReplyProducerFactory) {
    return new KafkaTemplate<>(orderReplyProducerFactory);
}
~~~

Listener container factory cần biết KafkaTemplate dùng để gửi response:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderRequest>
        orderRequestListenerContainerFactory(
                ConsumerFactory<String, OrderRequest> orderRequestConsumerFactory,
                KafkaTemplate<String, OrderReply> orderReplyKafkaTemplate) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderRequest>();

    factory.setConsumerFactory(orderRequestConsumerFactory);
    factory.setReplyTemplate(orderReplyKafkaTemplate);
    return factory;
}
~~~

`setReplyTemplate` cung cấp producer cho cơ chế trả lời của listener. Consumer factory phải deserialize request thành `OrderRequest`, còn reply template phải serialize response thành `OrderReply`.

## 8. Viết request listener trả reply bằng @SendTo

Listener xử lý request và trả về một object. `@SendTo` không chỉ định topic cố định sẽ yêu cầu Spring Kafka dùng reply destination trong header của request.

~~~java
@Service
public class OrderRequestListener {

    private final OrderCommandService orderCommandService;

    public OrderRequestListener(OrderCommandService orderCommandService) {
        this.orderCommandService = orderCommandService;
    }

    @KafkaListener(
        topics = "commerce.order.requests",
        groupId = "order-command-service",
        containerFactory = "orderRequestListenerContainerFactory"
    )
    @SendTo
    public OrderReply handle(OrderRequest request) {
        return orderCommandService.handle(request);
    }
}
~~~

Luồng hoạt động:

1. ReplyingKafkaTemplate gửi request kèm reply topic và correlation ID.
2. Listener nhận request.
3. Phương thức trả về OrderReply.
4. Spring Kafka dùng reply template để gửi response tới reply topic trong header.
5. Correlation ID được giữ trong response headers để client ghép kết quả.

Nếu dùng `@SendTo("commerce.order.replies")` với topic cố định, response sẽ được gửi tới destination đó. Cách này hữu ích khi mọi request đều trả về một topic cố định, nhưng cần bảo đảm client reply container đang lắng nghe đúng topic.

### 8.1. Trả về response nghiệp vụ khi request bị từ chối

Không phải mọi kết quả từ chối đều là lỗi kỹ thuật cần retry. Nếu request hợp lệ nhưng không đủ điều kiện nghiệp vụ, server có thể trả response thể hiện trạng thái từ chối:

~~~java
@KafkaListener(
    topics = "commerce.order.requests",
    groupId = "order-command-service",
    containerFactory = "orderRequestListenerContainerFactory"
)
@SendTo
public OrderReply handle(OrderRequest request) {
    if (!orderCommandService.canAccept(request)) {
        return new OrderReply(
            request.requestId(),
            false,
            "Order cannot be accepted",
            null
        );
    }

    String invoiceId = orderCommandService.createInvoice(request);

    return new OrderReply(
        request.requestId(),
        true,
        "Accepted",
        invoiceId
    );
}
~~~

Response nghiệp vụ bị từ chối vẫn là một reply hợp lệ. Nếu phương thức ném exception, Spring Kafka sẽ chuyển lỗi sang error handler của listener container; client có thể không nhận được response và cuối cùng timeout, trừ khi ứng dụng có quy ước error reply riêng.

## 9. Correlation ID ghép request và reply

Giả sử hai request đang chờ đồng thời:

~~~text
Request A -> correlation ID: 7f01
Request B -> correlation ID: 9c82

Reply B -> correlation ID: 9c82
Reply A -> correlation ID: 7f01
~~~

Reply có thể đến không theo thứ tự gửi. ReplyingKafkaTemplate dùng correlation ID để hoàn tất đúng future, không dựa vào vị trí record trong reply topic.

Không nên tự ghép response theo:

- Thứ tự gửi request.
- Offset của reply topic.
- Thời điểm response đến.
- Key của record nếu key không được định nghĩa là correlation ID.

Nếu server tạo một Message response mới, hãy bảo đảm các headers cần thiết được giữ hoặc được Spring Kafka chuyển tiếp theo cơ chế reply. Khi tự tạo ProducerRecord và publish reply thủ công, phải sao chép correlation ID và các metadata cần thiết.

### 9.1. Dùng correlation ID nghiệp vụ

Có thể đặt request ID trong payload để hỗ trợ audit và idempotency. Không nên nhầm nó với correlation header do request-reply infrastructure quản lý.

Một quy ước có thể là:

- requestId: định danh command trong nghiệp vụ.
- correlationId: định danh lần trao đổi request-reply.
- traceId: định danh trace xuyên nhiều service.

Ba giá trị có thể khác nhau. Ghi chúng vào log/trace giúp phân biệt một command được gửi lại với một lần chờ reply cụ thể.

## 10. Chạy nhiều instance và reply consumer group

Đây là điểm cấu hình rất quan trọng.

Giả sử hai instance client cùng gửi request và cùng lắng nghe một reply topic. Mỗi instance có một ReplyingKafkaTemplate và một registry future đang chờ trong bộ nhớ của chính instance đó.

Nếu hai instance dùng chung một consumer group cho reply topic, Kafka chia partition giữa chúng. Reply của request A có thể được giao cho instance B, trong khi future của request A chỉ tồn tại ở instance A. Instance B không có future tương ứng và không thể hoàn tất request của A.

Với reply topic dùng chung, mỗi client instance thường cần một group ID riêng để mỗi instance nhận được toàn bộ reply records. Mỗi ReplyingKafkaTemplate sau đó chỉ hoàn tất các future có correlation ID mà nó đang theo dõi; reply dành cho instance khác sẽ không khớp với pending request cục bộ.

Ví dụ cấu hình local:

~~~yaml
app:
  kafka:
    reply-group-id: order-reply-client-local
~~~

Trong production, group ID cần bao gồm định danh duy nhất của instance/pod. Không dùng cùng một giá trị cố định cho tất cả replica nếu chúng cùng lắng nghe reply topic dùng chung.

Nếu reply topic được chia sẻ giữa nhiều instance, có thể cấu hình template đánh dấu shared reply topic khi phiên bản Spring Kafka hỗ trợ:

~~~java
template.setSharedReplyTopic(true);
~~~

Thiết lập này biểu thị chủ đích dùng chung reply topic. Nó không thay thế yêu cầu thiết kế group ID để mỗi instance có thể nhận reply cần thiết.

### 10.1. Reply topic và partition

Reply topic cần được tạo trước hoặc được quản lý theo chính sách topic của môi trường. Khi dùng reply partition cụ thể:

- Partition phải tồn tại trong reply topic.
- Reply consumer container của client phải được subscribe/assign partition đó.
- Server phải gửi response vào đúng partition được chỉ định.
- Khi tăng số partition, cần đánh giá lại routing và cách phân phối reply.

Nếu không cần routing theo partition, có thể dùng một reply topic chung và để partitioner chọn partition. Khi dùng nhiều instance, cần kết hợp consumer group riêng như phần trên.

Không nên dùng reply topic làm nơi lưu event lâu dài cho nhiều loại consumer nếu retention, ACL và schema không được thiết kế phù hợp. Reply topic thường có vòng đời và mục đích khác với event topic.

## 11. Timeout và reply đến muộn

Request-reply luôn cần timeout vì server có thể dừng, request có thể bị lỗi, hoặc response không bao giờ đến.

Cấu hình mặc định trên template:

~~~java
template.setDefaultReplyTimeout(Duration.ofSeconds(10));
~~~

Timeout phải phản ánh thời gian xử lý bình thường, độ trễ broker và SLA của caller. Có thể đặt timeout theo từng request nếu phiên bản API đang dùng hỗ trợ overload tương ứng.

Timeout không đồng nghĩa request đã bị hủy ở Kafka. Khi client ngừng chờ:

- Request có thể vẫn nằm trong topic.
- Server có thể vẫn đang xử lý.
- Side effect có thể đã hoàn tất.
- Reply đến muộn có thể không còn future để ghép.
- Caller có thể gửi lại request và tạo duplicate nếu không có idempotency.

Vì vậy, cần có request ID ổn định và quy tắc xử lý duplicate ở server. Timeout nên được xem là “caller chưa nhận được kết quả trong thời gian cho phép”, không phải bằng chứng rằng nghiệp vụ thất bại.

### 11.1. Phân biệt timeout, send failure và business rejection

| Kết quả | Ý nghĩa | Cách xử lý |
|---|---|---|
| Send failure | Producer không gửi request thành công theo acknowledgment | Báo lỗi gửi và xem xét retry |
| Reply timeout | Không nhận được reply đúng hạn | Kiểm tra server, lag, reply topic và trạng thái request |
| Business rejection | Server trả reply hợp lệ nhưng từ chối nghiệp vụ | Trả kết quả từ chối cho caller |
| Processing exception | Server listener ném exception | Xử lý bằng error handler/DLT; caller có thể timeout |
| Late reply | Reply đến sau khi future đã timeout | Ghi nhận/quan sát, không giả định caller sẽ nhận lại |

### 11.2. Không retry request mù quáng sau timeout

Nếu client timeout rồi gửi request mới với ID khác, server có thể xử lý cả hai và tạo side effect trùng.

Nên:

- Giữ requestId ổn định khi retry cùng một command.
- Server lưu kết quả theo requestId nếu nghiệp vụ cần deduplication.
- Xác định thời hạn idempotency record.
- Cho phép caller truy vấn trạng thái request nếu cần.
- Phân biệt retry transport với tạo command nghiệp vụ mới.

## 12. Error handling ở phía server

Request listener có thể gặp lỗi deserialize, lỗi validation, lỗi database hoặc lỗi downstream.

Hãy phân loại lỗi:

- Request không hợp lệ: trả business rejection nếu đã deserialize và có thể phản hồi; hoặc cách ly record theo policy.
- Lỗi transient: retry có giới hạn theo error handler.
- Lỗi không thể phục hồi: DLT và cảnh báo.
- Lỗi publish reply: theo dõi producer send failure và xác định liệu request có thể được xử lý lại an toàn.

Nếu server thực hiện side effect thành công nhưng gửi reply thất bại, request có thể được giao lại. Idempotency theo requestId giúp tránh tạo side effect lần nữa.

Không nên nuốt exception rồi để listener kết thúc bình thường nếu response bắt buộc phải được gửi. Container có thể commit offset trong khi caller chỉ nhận timeout.

## 13. Bảo mật và kiểm soát reply destination

Reply topic có thể được gửi trong header request. Server cần cân nhắc không cho client tùy ý yêu cầu publish vào bất kỳ topic nào.

Các biện pháp:

- Chỉ cho phép reply tới danh sách topic được phép.
- Dùng ACL để giới hạn producer quyền ghi vào reply topic.
- Kiểm tra header reply topic trước khi gửi nếu hệ thống nhận request từ nhiều tenant hoặc client không tin cậy.
- Không đưa secret hoặc dữ liệu nhạy cảm vào correlation ID.
- Giới hạn kích thước request/reply.
- Kiểm tra schema và trusted packages của JSON deserializer.
- Đặt retention và quyền đọc reply topic phù hợp.

Trong môi trường nội bộ được kiểm soát, reply destination thường được cấu hình trước. Nếu nhận request từ nguồn bên ngoài, không nên tin header reply topic như một destination bất kỳ.

## 14. Kiểm thử request-reply

Kiểm thử tích hợp cần khởi động Kafka thật bằng EmbeddedKafka hoặc Testcontainers và kiểm tra cả client lẫn server.

Các trường hợp quan trọng:

1. Gửi request và nhận reply thành công.
2. Reply có đúng payload và key.
3. Correlation ID được giữ nguyên và ghép đúng khi nhiều request đồng thời.
4. Server trả business rejection.
5. Server không trả lời và client timeout.
6. Request gửi thất bại do broker hoặc producer configuration.
7. Reply đến muộn sau timeout.
8. Server xử lý request trùng nhưng không tạo side effect trùng.
9. Nhiều client instance dùng reply topic chung với group ID riêng.
10. Reply topic thiếu partition hoặc ACL không đủ.
11. Server gặp lỗi và request đi qua retry/DLT theo policy.

Ví dụ kiểm tra future:

~~~java
RequestReplyFuture<String, OrderRequest, OrderReply> future =
    replyingKafkaTemplate.sendAndReceive(requestRecord);

SendResult<String, OrderRequest> sendResult =
    future.getSendFuture().get(5, TimeUnit.SECONDS);

ConsumerRecord<String, OrderReply> reply =
    future.get(12, TimeUnit.SECONDS);

assertThat(sendResult.getRecordMetadata().topic())
    .isEqualTo("commerce.order.requests");
assertThat(reply.value().requestId())
    .isEqualTo(request.requestId());
~~~

Trong integration test, chờ reply bằng future có timeout hữu hạn. Không dùng sleep cố định để đoán khi nào response xuất hiện.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Future không nhận reply | Reply container chưa start hoặc subscribe sai topic | Kiểm tra lifecycle và topic |
| Future timeout | Server lỗi, reply topic lag hoặc reply bị gửi sai destination | Kiểm tra listener, producer và headers |
| Reply đến nhưng không ghép được | Correlation ID bị mất hoặc bị ghi đè | Kiểm tra header request và reply |
| Một số instance timeout ngẫu nhiên | Nhiều instance dùng chung reply consumer group | Dùng group ID riêng cho từng client instance |
| Reply deserialize thất bại | Consumer factory dùng sai deserializer/type mapping | Kiểm tra OrderReply deserializer |
| Server không gửi response | Thiếu reply template hoặc @SendTo | Cấu hình reply template trên listener factory |
| Send thành công nhưng caller timeout | Broker nhận request nhưng server không xử lý hoặc không reply | Phân biệt send future và reply future |
| Request xử lý hai lần | Caller retry sau timeout hoặc Kafka redelivery | Idempotency theo requestId |
| Reply topic không nhận được record | ACL, partition hoặc topic configuration sai | Kiểm tra topic và quyền producer |
| Reply đến sau timeout | Server xử lý lâu hơn SLA caller | Điều chỉnh timeout và quy trình truy vấn trạng thái |

## 16. Checklist trước khi đưa reply template vào production

- [ ] Request và reply có schema rõ ràng?
- [ ] Request ProducerFactory dùng serializer đúng?
- [ ] Reply ConsumerFactory dùng deserializer đúng?
- [ ] Reply container subscribe đúng topic và được start?
- [ ] ReplyingKafkaTemplate dùng đúng producer factory và reply container?
- [ ] Listener factory phía server có reply template?
- [ ] Request listener có @SendTo hoặc cơ chế gửi reply tương ứng?
- [ ] Correlation ID được giữ nguyên qua response?
- [ ] Reply topic có đủ partition và ACL?
- [ ] Mỗi client instance có group ID phù hợp khi dùng reply topic chung?
- [ ] Timeout phản ánh SLA và được xử lý rõ ràng?
- [ ] Timeout không bị hiểu nhầm là request đã bị hủy?
- [ ] Server idempotent theo requestId?
- [ ] Có quy tắc xử lý business rejection và processing exception?
- [ ] Có theo dõi send failure, reply timeout và late reply?
- [ ] Đã kiểm thử nhiều request đồng thời và nhiều instance?
- [ ] Đã kiểm tra bảo mật reply destination?

## Kết luận

`ReplyingKafkaTemplate<K,V,R>` kết hợp producer gửi request với consumer container lắng nghe reply topic. Template gắn correlation ID và thông tin reply destination để ghép response với request đang chờ. Ở phía server, listener có thể trả về payload bằng `@SendTo` khi listener container factory được cấu hình reply template.

Khi triển khai, cần khai báo serializer/deserializer đúng cho request và reply, khởi động reply container trước khi gửi request, đặt timeout theo SLA và thiết kế group ID đúng khi nhiều client instance dùng chung reply topic. Timeout không hủy request đã gửi; do đó server cần idempotency, còn client cần phân biệt send failure, reply timeout và business rejection. Kiểm thử cả correlation, late reply, duplicate và triển khai nhiều instance giúp request-reply hoạt động đáng tin cậy.

