# Định tuyến reply theo request

Trong mô hình request/reply trên Kafka, requester gửi một request và chờ response tương ứng. Khi có nhiều request đồng thời, nhiều requester instance hoặc nhiều partition, responder phải biết response cần được gửi về đâu. Spring Kafka dùng các header reply cùng correlation ID để thực hiện việc định tuyến này.

`ReplyingKafkaTemplate` có thể tự bổ sung thông tin reply topic và reply partition vào request khi reply container được cấu hình với đúng một topic hoặc đúng một `TopicPartitionOffset`. Với container phức tạp hơn, requester phải cung cấp reply headers. Listener phía responder đọc các header đó và gửi response về đúng topic/partition. Reply listener container ở phía requester nhận response, đối chiếu correlation ID rồi hoàn tất future đang chờ. Nhờ vậy, một reply topic có thể phục vụ nhiều request đang chờ mà không cần requester phải tự dò response bằng cách quét payload.

Định tuyến reply chỉ hoạt động đúng khi requester đã khởi động reply container, container được subscribe/assign đúng topic hoặc partition cần nhận, request giữ nguyên reply headers và responder gửi response theo các header đó. Nếu header bị mất, reply topic sai hoặc response đi vào partition mà requester không đọc, future sẽ timeout dù nghiệp vụ phía responder có thể đã xử lý xong.

## 1. Các thành phần của định tuyến request/reply

Một luồng request/reply có các thành phần:

| Thành phần | Vai trò |
|---|---|
| Requester | Gửi request bằng `ReplyingKafkaTemplate` và chờ future |
| Request topic | Topic chứa request do requester gửi |
| Responder listener | Nhận request, xử lý và tạo response |
| Reply topic | Topic nhận response |
| Reply partition | Partition cụ thể nhận response cho requester hoặc request tương ứng |
| Correlation ID | Ghép response với future của request ban đầu |
| Reply listener container | Consumer container nhận response và chuyển về `ReplyingKafkaTemplate` |

Luồng tổng quát:

```text
Requester A
  ReplyingKafkaTemplate
  reply container đọc replies partition 0
       |
       | request + REPLY_TOPIC + REPLY_PARTITION + CORRELATION_ID
       v
Kafka request topic
       |
       v
Responder @KafkaListener
       |
       | đọc reply headers
       v
Reply template gửi response tới đúng topic/partition
       |
       v
Kafka reply topic, partition 0
       |
       v
Reply container của Requester A
       |
       | correlation ID khớp
       v
Future của request được hoàn tất
```

Trong ví dụ, requester A dùng partition 0. Nếu requester B dùng partition 1, responder gửi response của B tới partition 1. Reply containers phải được cấu hình để mỗi requester nhận được partition đã được chỉ định cho nó.

## 2. Các header dùng để định tuyến reply

Spring Kafka cung cấp các header quan trọng trong `KafkaHeaders`:

| Header | Ý nghĩa |
|---|---|
| `KafkaHeaders.REPLY_TOPIC` | Tên reply topic mà responder cần gửi response tới |
| `KafkaHeaders.REPLY_PARTITION` | Partition đích trong reply topic; có thể không có nếu dùng định tuyến theo key/partitioner |
| `KafkaHeaders.CORRELATION_ID` | ID liên kết response với request đang chờ |
| `KafkaHeaders.TOPIC` | Topic đích của request khi gửi bằng Spring `Message<?>` |
| `KafkaHeaders.MESSAGE_KEY` | Key của request Kafka record |

`ReplyingKafkaTemplate` thường tự thêm reply topic, reply partition (khi có cấu hình partition cụ thể) và correlation ID. Ứng dụng không cần tự tạo correlation ID nếu dùng cơ chế mặc định. Responder phải giữ lại các header request/reply và phản chiếu correlation ID vào response.

Không nhầm `KafkaHeaders.REPLY_TOPIC` với `KafkaHeaders.TOPIC`: header đầu tiên chỉ nơi nhận response; header thứ hai xác định nơi gửi request. Tương tự, `KafkaHeaders.REPLY_PARTITION` là partition của response, không phải partition của request.

## 3. ReplyingKafkaTemplate và reply container

`ReplyingKafkaTemplate<K, V, R>` kết hợp một `ProducerFactory` để gửi request với một listener container để nhận response. Có hai cách cấu hình reply container thường gặp: subscribe một reply topic và dùng group ID riêng cho từng requester (mô hình fan-out), hoặc gán cố định một `TopicPartitionOffset` cho từng requester (mô hình partition riêng, không dùng group management).

Ví dụ dưới đây dùng mô hình fan-out trên một reply topic. Mỗi requester instance phải có group ID riêng; mọi instance sẽ nhận mọi response, nhưng template chỉ hoàn tất future có correlation ID khớp:

```java
@Configuration
public class RequestReplyConfiguration {

    @Bean
    public ConcurrentMessageListenerContainer<String, String> repliesContainer(
            ConsumerFactory<String, String> consumerFactory,
            @Value("${app.kafka.reply-group-id}") String replyGroupId) {

        ContainerProperties properties = new ContainerProperties("orders.replies");
        properties.setGroupId(replyGroupId);
        Properties consumerProperties = new Properties();
        consumerProperties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
        properties.setKafkaConsumerProperties(consumerProperties);
        return new ConcurrentMessageListenerContainer<>(
                consumerFactory, properties);
    }

    @Bean
    public ReplyingKafkaTemplate<String, String, String> replyingKafkaTemplate(
            ProducerFactory<String, String> producerFactory,
            ConcurrentMessageListenerContainer<String, String> repliesContainer) {

        var template = new ReplyingKafkaTemplate<>(producerFactory, repliesContainer);
        template.setSharedReplyTopic(true);
        return template;
    }
}
```

`app.kafka.reply-group-id` phải là group ID duy nhất cho từng requester instance, ví dụ `order-reply-client-${INSTANCE_ID}`. `latest` giúp group mới bắt đầu từ cuối log để không đọc lại các reply cũ đã tồn tại trước khi instance khởi động. `setSharedReplyTopic(true)` cho template biết reply topic được chia sẻ; các response không có correlation ID đang chờ sẽ được log ở mức DEBUG thay vì ERROR. Mô hình này tạo fan-out: mỗi response được đọc bởi mọi requester group, dù chỉ một instance hoàn tất future tương ứng.

`setSharedReplyTopic(true)` có từ Spring Kafka 2.3. Nếu dùng phiên bản cũ hơn, kiểm tra API tương ứng và điều chỉnh log level cho các response không khớp correlation ID theo cách phiên bản đó hỗ trợ.

Reply container cần được start và nhận assignment trước khi gửi request. Có thể chờ bằng:

```java
if (!replyingKafkaTemplate.waitForAssignment(Duration.ofSeconds(10))) {
    throw new IllegalStateException("Reply container chưa được assign partition");
}
```

Nếu gửi request trước khi reply container sẵn sàng, response có thể được ghi vào topic nhưng không được consumer nhận đúng lúc; với cấu hình offset `latest`, một số tình huống khởi động muộn có thể khiến response đã ghi trước assignment bị bỏ qua.

## 4. Cách ReplyingKafkaTemplate chọn reply destination

Từ Spring Kafka 2.2, template cố gắng suy ra reply headers từ cấu hình reply container:

- Nếu container subscribe đúng một topic, template có thể tự đặt `REPLY_TOPIC`; nó không tự chọn một partition cụ thể chỉ vì topic có nhiều partition.
- Nếu container được cấu hình với đúng một `TopicPartitionOffset`, template có thể tự đặt cả `REPLY_TOPIC` và `REPLY_PARTITION`.
- Nếu container nghe nhiều topic, dùng pattern hoặc có cấu hình phức tạp hơn, ứng dụng phải cung cấp reply headers phù hợp.

Vì vậy, chỉ gọi `waitForAssignment()` không có nghĩa template đã biết partition đích. Với mô hình partition riêng, phải cấu hình container bằng đúng một `TopicPartitionOffset` cố định. Với mô hình fan-out theo group riêng, chỉ cần một reply topic và mỗi requester dùng group ID riêng.

Không hard-code reply partition trong responder. Responder nên dùng header của từng request vì mỗi request có thể thuộc requester instance hoặc partition khác nhau.

## 5. Responder đọc reply headers và gửi response

Với `@KafkaListener`, Spring Kafka có thể tự gửi giá trị trả về của listener nếu container factory được cấu hình reply template. Khi dùng `@SendTo` không chỉ định topic cố định, framework sử dụng reply destination trong header của request.

```java
@Configuration
public class OrderResponderConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            requestListenerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    KafkaTemplate<String, String> replyTemplate) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setReplyTemplate(replyTemplate);
        return factory;
    }
}
```

Listener:

```java
@Component
public class OrderQueryListener {

    @KafkaListener(
            topics = "orders.requests",
            groupId = "orders-service",
            containerFactory = "requestListenerFactory")
    @SendTo
    public OrderReply handle(OrderRequest request) {
        return orderService.find(request.orderId());
    }
}
```

Với `@SendTo` không có destination cố định, Spring Kafka lấy reply topic và partition từ request headers. Reply template gửi response và framework sao chép correlation ID từ request sang response. Nếu thiếu reply destination header, listener không thể tự biết response cần đi đâu; request/reply có thể thất bại hoặc phát sinh lỗi tùy cấu hình.

Nếu cần kiểm soát trực tiếp header hoặc gửi nhiều response, có thể nhận `Message<?>`/`ConsumerRecord` và gửi response qua `KafkaTemplate`. Khi tự tạo response, phải copy correlation ID và đặt đúng reply topic/partition; tránh vô tình gửi response bằng một topic cố định không tương ứng requester.

## 6. Định tuyến bằng reply partition cố định

Giả sử reply topic `orders.replies` có hai partition. Requester A được cấu hình nghe cố định partition 0, requester B nghe cố định partition 1. Đây là manual assignment bằng `TopicPartitionOffset`, không phải assignment do consumer group coordinator quản lý.

Ví dụ tạo container cho một requester instance:

```java
@Bean
public ConcurrentMessageListenerContainer<String, String> repliesContainer(
        ConsumerFactory<String, String> consumerFactory,
        @Value("${app.kafka.reply-partition}") int replyPartition) {

    ContainerProperties properties = new ContainerProperties(
            new TopicPartitionOffset("orders.replies", replyPartition));
    // Không đặt group.id: container được gán partition trực tiếp.
    return new ConcurrentMessageListenerContainer<>(consumerFactory, properties);
}
```

Mỗi instance phải nhận một `reply-partition` khác nhau và partition đó phải tồn tại. Không dùng consumer group management trong mô hình này; nếu cấu hình group ID và subscribe theo group, Kafka có thể phân phối partition theo assignment strategy thay vì giữ partition cố định như yêu cầu.

```text
Requester A                         Requester B
reply partition = 0                reply partition = 1
      |                                   |
      | request A                         | request B
      | REPLY_PARTITION=0                 | REPLY_PARTITION=1
      +----------------+------------------+
                       v
                orders.requests
                       |
                       v
                 Responder
                 /        \
                /          \
      response A            response B
      partition 0           partition 1
          |                     |
          v                     v
    Requester A             Requester B
```

Responder gửi response theo partition header. Mỗi requester chỉ consume partition đã được gán cố định cho nó để nhận response của các request do nó gửi. Cách này tránh việc tất cả requester phải đọc toàn bộ reply topic.

Định tuyến partition chỉ hoạt động khi reply topic có partition hợp lệ và requester đang thực sự được assign partition đó. Nếu header chỉ định partition không tồn tại, producer send response sẽ thất bại. Hãy bảo đảm số partition của reply topic đủ cho số requester instance hoặc chiến lược chia sẻ partition đã chọn.

## 7. Mô hình nhiều requester instance

Có ba mô hình thường gặp:

| Mô hình | Cách hoạt động | Ưu điểm/đánh đổi |
|---|---|---|
| Reply topic riêng cho từng instance | Mỗi requester có topic riêng và reply container chỉ đọc topic đó | Cách ly đơn giản; tăng số topic và cần quản lý vòng đời topic |
| Reply topic chung, partition riêng cho mỗi instance | Mỗi requester dùng `TopicPartitionOffset` để manual-assign một partition; request mang reply partition header | Ít topic, định tuyến rõ; không dùng group management và phải quản lý partition/instance |
| Reply topic chung, group ID riêng cho từng instance | Mỗi group nhận mọi response; template chỉ hoàn tất future có correlation ID khớp và bỏ qua response khác | Dễ triển khai; mỗi response được fan-out tới mọi instance, tăng traffic và chi phí consumer |

Không dùng một consumer group chung cho mọi requester nếu reply topic được chia partition theo group assignment thông thường. Kafka sẽ phân phối mỗi partition cho một member trong group; response dành cho requester A có thể đến consumer B, nơi không có future tương ứng.

### Mô hình partition riêng

Đây thường là lựa chọn hiệu quả khi số requester instance có giới hạn và có thể quản lý partition. Mỗi instance tạo reply container với đúng một `TopicPartitionOffset`, ví dụ instance A dùng partition 0 và instance B dùng partition 1. Nếu reply topic có P partition thì tối đa P instance có thể có một partition riêng theo cách này. Khi scale, cần cấp partition và bảo đảm không có hai requester cùng consume một reply partition nếu yêu cầu cách ly.

`ReplyingKafkaTemplate` nhận biết partition từ cấu hình đơn `TopicPartitionOffset`. Hãy đợi `waitForAssignment()` trước khi cho instance nhận traffic. Không giả định partition number luôn bằng ordinal của pod nếu cấu hình triển khai không bảo đảm ánh xạ đó.

### Mô hình group riêng trên reply topic chung

Nếu mỗi requester dùng group ID riêng trên cùng reply topic, Kafka coi mỗi group là một subscriber độc lập và gửi bản sao của mọi response tới từng group. Template ở mỗi instance kiểm tra correlation ID; response không có future tương ứng sẽ bị bỏ qua. Đặt `sharedReplyTopic=true` để các response không khớp được log ở mức DEBUG.

Cách này đơn giản về định tuyến nhưng nhân số lượng dữ liệu phải đọc theo số requester instance. Với N requester instance, một response có thể được đọc N lần. Không nên dùng khi reply throughput lớn hoặc có nhiều instance nếu chi phí fan-out không chấp nhận được.

## 8. Gửi request bằng Message<?> và headers

Khi dùng Spring `Message<?>`, requester có thể đặt topic và key bằng headers. `ReplyingKafkaTemplate` bổ sung reply metadata:

```java
Message<OrderRequest> request = MessageBuilder
        .withPayload(new OrderRequest("order-42"))
        .setHeader(KafkaHeaders.TOPIC, "orders.requests")
        .setHeader(KafkaHeaders.MESSAGE_KEY, "order-42")
        .build();

RequestReplyMessageFuture<String, String, String> future =
        replyingKafkaTemplate.sendAndReceive(request);

Message<?> reply = future.get(10, TimeUnit.SECONDS);
OrderReply result = (OrderReply) reply.getPayload();
```

Trong ví dụ, `KafkaHeaders.TOPIC` là request topic và `KafkaHeaders.MESSAGE_KEY` là key của request. Reply topic/partition/correlation ID được template thêm theo cấu hình reply container. Converter được cấu hình trên template sẽ chuyển payload object sang kiểu mà Kafka serializer hỗ trợ.

Nếu reply container được cấu hình với một topic hoặc một `TopicPartitionOffset`, `ReplyingKafkaTemplate` có thể tự suy ra reply headers. Nếu container có cấu hình khác, requester phải tự đặt `KafkaHeaders.REPLY_TOPIC` và có thể cả `KafkaHeaders.REPLY_PARTITION`. Các header này phải hợp lệ và tương ứng với reply container đang chạy. Thông thường nên để template quản lý khi cấu hình container cho phép, tránh cấu hình sai hoặc bị giả mạo từ message đầu vào.

## 9. Đọc và kiểm tra reply headers trong responder

Để debug định tuyến, responder có thể nhận `ConsumerRecord` và log reply headers:

```java
@KafkaListener(topics = "orders.requests", groupId = "orders-service")
public void inspectRequest(ConsumerRecord<String, String> record) {
    Header replyTopic = record.headers().lastHeader(KafkaHeaders.REPLY_TOPIC);
    Header replyPartition = record.headers().lastHeader(KafkaHeaders.REPLY_PARTITION);
    Header correlationId = record.headers().lastHeader(KafkaHeaders.CORRELATION_ID);

    log.info("request topic={}, partition={}, offset={}, replyTopic={}, replyPartitionHeaderBytes={}, correlationIdPresent={}",
            record.topic(), record.partition(), record.offset(),
            replyTopic == null ? null : new String(replyTopic.value(), StandardCharsets.UTF_8),
            replyPartition == null ? null : replyPartition.value().length,
            correlationId != null);
}
```

Header partition được mã hóa dưới dạng byte; khi cần parse số, dùng cách encode/decode mà Spring Kafka của phiên bản đang chạy quy định. Không giả định mọi header đều là UTF-8 text. Ví dụ log trên chỉ minh họa kiểm tra sự hiện diện; không dùng `new String(...)` để diễn giải header số trong logic định tuyến.

`KafkaHeaders.REPLY_PARTITION` dùng một số nguyên 4 byte theo thứ tự big-endian. Có thể giải mã bằng `ByteBuffer`:

```java
private Integer decodeReplyPartition(Header header) {
    if (header == null) {
        return null;
    }
    byte[] value = header.value();
    if (value.length != Integer.BYTES) {
        throw new IllegalArgumentException("REPLY_PARTITION phải có 4 byte");
    }
    return ByteBuffer.wrap(value).getInt();
}
```

Nếu responder tự gửi reply:

```java
void sendReply(ConsumerRecord<String, String> request, String replyJson) {
    Header replyTopicHeader = request.headers()
            .lastHeader(KafkaHeaders.REPLY_TOPIC);
    Header replyPartitionHeader = request.headers()
            .lastHeader(KafkaHeaders.REPLY_PARTITION);
    Header correlationHeader = request.headers()
            .lastHeader(KafkaHeaders.CORRELATION_ID);

    if (replyTopicHeader == null || correlationHeader == null) {
        throw new IllegalArgumentException("Request thiếu reply/correlation header");
    }

    String replyTopic = new String(
            replyTopicHeader.value(), StandardCharsets.UTF_8);
    Integer partition = decodeReplyPartition(replyPartitionHeader);

    ProducerRecord<String, String> reply = new ProducerRecord<>(
            replyTopic, partition, null, request.key(), replyJson);
    reply.headers().add(
            KafkaHeaders.CORRELATION_ID,
            correlationHeader.value().clone());

    kafkaTemplate.send(reply);
}
```

`decodeReplyPartition(...)` trả `null` nếu request không chỉ định partition. Điều này chỉ phù hợp với mô hình reply topic chung/fan-out, nơi mọi requester group đều đọc toàn bộ partition và correlation ID chọn đúng future. Với mô hình partition riêng, header bắt buộc phải có; nếu thiếu hoặc parse lỗi, từ chối request thay vì để producer tự chọn partition.

Trong phần lớn trường hợp, dùng `@SendTo` và reply template của listener container an toàn hơn tự dựng `ProducerRecord`, vì Spring xử lý việc sao chép correlation ID và reply destination. Chỉ tự gửi khi cần routing tùy chỉnh hoặc nhiều response.

## 10. Correlation ID bảo đảm ghép đúng response

Một requester có thể gửi nhiều request trước khi nhận response. `ReplyingKafkaTemplate` giữ mapping correlation ID tới future. Khi response quay lại, template tìm correlation ID và hoàn tất đúng future.

```text
Request A: correlationId = a1
Request B: correlationId = b2
Request C: correlationId = c3

Response B đến trước -> hoàn tất future b2
Response A đến sau  -> hoàn tất future a1
Response C đến cuối -> hoàn tất future c3
```

Response không cần về đúng thứ tự request gửi. Correlation ID giúp ghép đúng response ngay cả khi responder xử lý song song hoặc các request có thời gian xử lý khác nhau.

Responder phải phản chiếu đúng correlation ID của request. Nếu response thiếu ID hoặc dùng ID khác, template không thể ghép response với future tương ứng; request sẽ timeout. Không tạo correlation ID mới ở responder nếu không có quy tắc mapping riêng được cả hai phía thống nhất.

## 11. Reply partition và ordering

Reply partition có thể giúp giữ thứ tự response trong phạm vi partition, nhưng request/reply thường không cần response về theo thứ tự request gửi. Correlation ID cho phép response hoàn tất độc lập.

Nếu nghiệp vụ yêu cầu response theo thứ tự, cần thiết kế responder xử lý tuần tự theo key hoặc partition và tránh async completion đảo thứ tự. Việc gửi tất cả response về cùng reply partition không tự bảo đảm thứ tự nếu responder xử lý request song song và hoàn tất không theo thứ tự.

Khi nhiều requester chia sẻ một reply partition, các response có thể xen kẽ. Correlation ID vẫn ghép đúng future, nhưng thứ tự record trong partition phản ánh thứ tự responder append response chứ không nhất thiết là thứ tự request ban đầu.

## 12. Bảo mật reply destination

Reply topic/partition được truyền qua request headers. Nếu requester không đáng tin có thể tự chỉ định reply topic tùy ý, responder có nguy cơ bị lợi dụng để publish vào topic ngoài dự kiến. Trong hệ thống nhiều tenant hoặc có producer bên ngoài, không nên tin mọi reply destination header mà không kiểm tra.

Các biện pháp phù hợp:

- Dùng allowlist reply topic được phép.
- Kiểm tra partition nằm trong phạm vi topic và requester được cấp quyền.
- Giới hạn ACL của responder chỉ cho phép ghi vào các reply topic cần thiết.
- Không cho requester tự do chỉ định topic hệ thống nhạy cảm.
- Có thể dùng reply topic theo tenant/instance được tạo từ danh tính đã xác thực thay vì nhận chuỗi tùy ý.
- Ghi log requester identity, reply destination và correlation ID theo chính sách bảo mật.

Ví dụ kiểm tra allowlist trước khi gửi reply:

```java
private static final Set<String> ALLOWED_REPLY_TOPICS =
        Set.of("orders.replies", "orders.replies.internal");

void validateReplyTopic(String replyTopic) {
    if (!ALLOWED_REPLY_TOPICS.contains(replyTopic)) {
        throw new SecurityException("Reply topic không được phép: " + replyTopic);
    }
}
```

Trong production, allowlist nên đến từ cấu hình quản trị và được kiểm tra cùng ACL broker. Kiểm tra trong code không thay thế authorization của Kafka broker.

Khi dùng `@SendTo` tự động, framework lấy reply destination từ header request. Nếu cần allowlist, hãy kiểm tra request headers trước khi trả kết quả hoặc dùng listener/reply flow tùy chỉnh có bước validate rõ ràng; không cho rằng `@SendTo` tự áp dụng allowlist nghiệp vụ.

## 13. Timeout và response gửi sai partition

Nếu response được gửi tới partition mà reply container không đọc, requester sẽ không nhận được response và future timeout. Các nguyên nhân thường gặp:

- `REPLY_PARTITION` không khớp partition được gán cho requester.
- Reply topic chưa tồn tại hoặc số partition không đủ.
- Reply container chưa được assign khi request được gửi.
- Responder bỏ qua hoặc parse sai reply partition header.
- Correlation ID không được sao chép sang response.
- Reply consumer group phân phối response sang instance khác.

Timeout chỉ cho biết requester chưa nhận được response hợp lệ trong thời gian chờ. Nó không chứng minh responder chưa xử lý request. Nếu requester retry sau timeout, nghiệp vụ có thể được thực hiện hai lần. Hãy dùng request ID/idempotency key ổn định ở tầng nghiệp vụ.

## 14. Xử lý nhiều response hoặc response bất đồng bộ

Một request thường mong đợi một response. Nếu responder cần gửi nhiều response cho một request, `ReplyingKafkaTemplate` với future đơn lẻ không phải mô hình streaming response tự nhiên. Có thể thiết kế response topic riêng, dùng correlation ID để nhóm các response, hoặc dùng Kafka Streams/reactive consumer để xử lý luồng kết quả.

Nếu listener trả về `CompletableFuture`/`Mono` hoặc xử lý bất đồng bộ, cần kiểm tra API Spring Kafka của phiên bản đang dùng và bảo đảm reply vẫn mang đúng request headers. Không trả về response trước khi nghiệp vụ hoàn tất nếu kết quả chưa sẵn sàng.

## 15. Kiểm thử định tuyến reply

Nên kiểm thử với broker thật hoặc Testcontainers/Embedded Kafka và nhiều requester instance. Unit test chỉ kiểm tra helper parse header không chứng minh được partition assignment hoặc consumer group routing.

Các tình huống cần kiểm thử:

| Tình huống | Kỳ vọng |
|---|---|
| Một requester, một reply partition | Request nhận đúng response |
| Hai requester, hai reply partition | Response A về A, response B về B |
| Hai request đồng thời, response đảo thứ tự | Correlation ID hoàn tất đúng future |
| Thiếu `REPLY_TOPIC` | Responder phát hiện request không hợp lệ; không gửi reply tùy tiện |
| Thiếu `CORRELATION_ID` | Request bị từ chối hoặc xử lý theo contract; future không bị ghép sai |
| `REPLY_PARTITION` không tồn tại | Producer send thất bại rõ ràng và có log |
| Reply container chưa assignment | `waitForAssignment()` timeout và requester không gửi request |
| Nhiều requester dùng chung group không đúng | Test phát hiện response có thể đến sai instance |
| Reply topic ngoài allowlist | Responder từ chối định tuyến |
| Timeout sau khi responder xử lý | Retry không tạo side effect trùng nhờ idempotency |

Khi test nhiều requester, xác minh assignment bằng `KafkaMessageListenerContainer`/container properties và kiểm tra response thực tế ở từng instance. Không chỉ xác minh response xuất hiện trên topic vì điều đó chưa chứng minh đúng requester nhận được nó.

## 16. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| `REPLY_TOPIC` là request topic | Đây là topic nhận response; request topic được cấu hình riêng |
| `REPLY_PARTITION` là partition của request | Đây là partition đích cho response |
| Correlation ID định tuyến response tới partition | Correlation ID ghép response với future; reply topic/partition mới xác định nơi ghi |
| Chỉ cần cùng group ID cho mọi requester | Group chung chia partition; response có thể đến instance không giữ future |
| Cùng reply topic thì mọi requester đều nhận response | Consumer group dùng chung phân phối record, không broadcast cho từng member |
| `@SendTo` luôn gửi tới một topic cố định | `@SendTo` không destination có thể dùng reply destination trong request headers |
| Future timeout nghĩa là nghiệp vụ chưa chạy | Responder có thể đã xử lý nhưng reply thất lạc, sai partition hoặc đến muộn |
| Gửi response về đúng partition là đủ | Cần giữ correlation ID để template ghép đúng future |
| Reply headers từ requester luôn đáng tin | Cần allowlist và ACL để tránh responder bị lợi dụng publish tùy ý |

## Checklist trước khi triển khai request/reply

- Reply listener container đã start và được assign trước khi requester gửi request.
- Reply topic/partition được chọn theo chiến lược một instance, nhiều instance hoặc fan-out rõ ràng.
- `REPLY_TOPIC`, `REPLY_PARTITION` và `CORRELATION_ID` được giữ qua responder.
- Responder dùng reply template hoặc `@SendTo` đúng cách.
- Nhiều requester không chia sẻ group theo cách làm response tới sai instance.
- Reply topic có đủ partition và ACL cho requester/responder.
- Correlation ID được phản chiếu nguyên vẹn; không tạo ID mới tùy tiện.
- Reply destination được kiểm tra allowlist khi requester không hoàn toàn tin cậy.
- Timeout được xử lý như trạng thái không nhận được response, không kết luận request chưa chạy.
- Có idempotency key cho nghiệp vụ có thể bị thực hiện lại sau timeout.
- Integration test xác minh response tới đúng requester instance, không chỉ xuất hiện trên topic.

Định tuyến reply trong Spring Kafka dựa trên reply topic/partition headers, còn correlation ID dùng để ghép response với request đang chờ. Khi reply container được assign đúng, responder giữ nguyên các header và topology consumer group được thiết kế cho nhiều instance, `ReplyingKafkaTemplate` có thể xử lý nhiều request đồng thời mà response vẫn quay về đúng requester. Hãy kiểm thử partition routing, timeout và quyền truy cập reply destination trước khi đưa mô hình này vào production.

## Tài liệu tham khảo

- [Spring for Apache Kafka – Sending Messages and ReplyingKafkaTemplate](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [ReplyingKafkaTemplate API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/requestreply/ReplyingKafkaTemplate.html)
