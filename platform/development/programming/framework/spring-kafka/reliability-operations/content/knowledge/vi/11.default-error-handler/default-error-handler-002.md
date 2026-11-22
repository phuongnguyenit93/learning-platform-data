# Cấu hình CommonErrorHandler

Trong Spring Kafka, listener container quản lý việc gọi listener, xử lý exception và quyết định record sẽ được thử lại, phục hồi hay chuyển sang dead-letter topic (DLT). Từ Spring Kafka 2.8, cơ chế xử lý lỗi dùng chung cho record listener và batch listener được chuẩn hóa qua interface **CommonErrorHandler**. Khi cấu hình handler cho container, ứng dụng có thể kiểm soát retry, phân loại exception, phục hồi record và ghi nhận lỗi theo một chính sách nhất quán.

**DefaultErrorHandler** là implementation thường dùng nhất. Nó hỗ trợ backoff, retry có giới hạn, recoverer, phân loại lỗi retryable/non-retryable và callback quan sát lần thử. CommonErrorHandler là abstraction được container sử dụng; DefaultErrorHandler cung cấp phần lớn hành vi phổ biến. Chỉ nên tự triển khai interface khi chính sách đặc biệt không thể biểu đạt bằng implementation có sẵn.

## 1. Vai trò của CommonErrorHandler

Một listener có thể thất bại vì lỗi nghiệp vụ, database timeout, lỗi deserialize hoặc dịch vụ phụ thuộc tạm thời không sẵn sàng. Nếu exception thoát khỏi listener, container cần quyết định bước tiếp theo. Error handler có thể:

- Thử lại record sau một khoảng nghỉ.
- Phân loại lỗi để bỏ qua retry với lỗi không thể tự khắc phục.
- Gọi recoverer khi hết số lần thử.
- Chuyển record sang DLT để điều tra hoặc xử lý lại sau này.
- Ghi log, metric và thông tin delivery attempt.
- Quyết định container có thể tiếp tục sau khi record được xử lý lỗi hay cần dừng.

CommonErrorHandler định nghĩa hợp đồng xử lý lỗi chung mà listener container gọi tới. Nó thay thế mô hình cũ gồm các interface riêng cho record error handler và batch error handler. Nhờ đó, một cấu hình có thể áp dụng cho nhiều kiểu listener.

Luồng xử lý khái quát:

    Consumer poll
        |
        v
    Listener xử lý record hoặc batch
        |
        +---- thành công ----------------> Ack / commit theo AckMode
        |
        +---- exception
                 |
                 v
          CommonErrorHandler
                 |
          +------+------------------+
          |                         |
          v                         v
       Retry                    Không retry
          |                         |
          v                         |
      Hết backoff?                  |
       |                            |
       +-- chưa --> Listener thử lại|
       |                            |
       +-- rồi ---------------------+
                    |
                    v
                 Recoverer
                    |
          +---------+----------+
          |                    |
          v                    v
        DLT                Phục hồi khác
                    |
                    v
           Container tiếp tục hoặc
           dừng theo chính sách

Error handler kiểm soát cách container phản ứng với lỗi tiêu thụ. Nó không thay thế xử lý lỗi producer khi gọi KafkaTemplate.send(), không tự rollback database transaction và không bảo đảm side effect bên ngoài Kafka là exactly-once.

## 2. CommonErrorHandler và DefaultErrorHandler

CommonErrorHandler là interface. DefaultErrorHandler là implementation Spring Kafka cung cấp để xử lý lỗi phổ biến với retry và recovery.

| Thành phần | Vai trò |
|---|---|
| CommonErrorHandler | Hợp đồng xử lý exception dùng chung cho listener container |
| DefaultErrorHandler | Retry record/batch theo BackOff và gọi recoverer khi hết retry |
| BackOff | Quy định khoảng nghỉ và số lần thử lại |
| ConsumerRecordRecoverer | Thực hiện hành động khi record đã hết retry |
| DeadLetterPublishingRecoverer | Publish record lỗi sang DLT |
| RetryListener | Quan sát delivery thất bại và kết quả recovery |
| ContainerProperties | Cấu hình error handler, commit và hành vi listener container |

DefaultErrorHandler được giới thiệu trong Spring Kafka 2.8 và thay thế các error handler cũ như SeekToCurrentErrorHandler trong các cấu hình mới. Khi nâng cấp, chuyển cách cấu hình sang setCommonErrorHandler() trên listener container factory.

Một cấu hình tối thiểu có thể dùng DefaultErrorHandler với FixedBackOff:

~~~java
@Bean
CommonErrorHandler commonErrorHandler() {
    return new DefaultErrorHandler(
        new FixedBackOff(1_000L, 2L)
    );
}
~~~

Cấu hình trên dùng recoverer mặc định của DefaultErrorHandler sau khi các lần retry được sử dụng hết. Trong production, nên chỉ định recoverer rõ ràng để quyết định record lỗi sẽ được lưu hoặc xử lý như thế nào.

## 3. Gắn CommonErrorHandler vào listener container factory

Khai báo bean CommonErrorHandler chưa đủ để bảo đảm mọi listener đều sử dụng bean đó. Hãy gắn handler vào ConcurrentKafkaListenerContainerFactory thông qua setCommonErrorHandler().

Ví dụ:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    CommonErrorHandler commonErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 3L)
                );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            CommonErrorHandler commonErrorHandler) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(commonErrorHandler);

        return factory;
    }
}
~~~

Listener dùng factory này:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "kafkaListenerContainerFactory"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Mỗi container được tạo từ factory sẽ dùng CommonErrorHandler đã cấu hình. Nếu ứng dụng có nhiều factory cho các nhóm listener khác nhau, hãy gắn handler phù hợp vào từng factory. Ví dụ listener xử lý thanh toán có thể cần retry và DLT riêng so với listener cập nhật thống kê.

Khi dùng Spring Boot, kiểm tra factory mà @KafkaListener thực sự tham chiếu. Không giả định chỉ khai báo một bean CommonErrorHandler thì mọi factory tùy chỉnh đều tự động nhận bean đó.

## 4. Cấu hình retry với BackOff

BackOff quyết định khoảng thời gian chờ giữa các lần thử. DefaultErrorHandler nhận một đối tượng BackOff trong constructor.

### 4.1. FixedBackOff

FixedBackOff dùng khoảng nghỉ cố định:

~~~java
BackOff backOff = new FixedBackOff(1_000L, 3L);

DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);
~~~

Trong ví dụ, container chờ một giây giữa các lần retry và cho phép ba lần retry sau lần xử lý đầu tiên thất bại. Tổng số lần listener có thể được gọi là lần đầu cộng các lần retry được cấu hình. Hãy ghi rõ cách đếm trong tài liệu vận hành để tránh nhầm attempts với retries.

FixedBackOff phù hợp khi lỗi tạm thời thường được khắc phục trong khoảng thời gian ổn định, hoặc khi cần cấu hình đơn giản và dễ dự đoán.

### 4.2. Exponential backoff

Nếu dịch vụ phụ thuộc đang quá tải, nhiều consumer cùng retry theo một khoảng cố định có thể tạo retry storm. Exponential backoff tăng thời gian nghỉ giữa các lần thử, giúp hệ thống phụ thuộc có thời gian phục hồi.

Spring Kafka cung cấp ExponentialBackOffWithMaxRetries:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);
~~~

Khoảng nghỉ tăng theo hệ số nhân nhưng không vượt quá max interval. Số retry vẫn hữu hạn. Chọn initial interval, multiplier, max interval và số lần thử dựa trên SLA, thời gian phục hồi dependency và thời gian record được phép nằm trong hệ thống.

Backoff không thay thế timeout của HTTP client hoặc database. Nếu một lần gọi dịch vụ có thể treo vô thời hạn, listener có thể không trả exception để error handler bắt đầu retry. Đặt timeout cho thao tác phụ thuộc để retry policy hoạt động đúng.

### 4.3. Chọn chính sách theo loại lỗi

| Tình huống | Chính sách gợi ý |
|---|---|
| Database tạm timeout | Retry hữu hạn với exponential backoff |
| API phụ thuộc trả 503 | Retry với khoảng nghỉ và giới hạn |
| Payload sai schema | Không retry vô hạn; chuyển DLT |
| Thiếu trường bắt buộc | Không retry nếu dữ liệu không thể tự sửa |
| Credential sai | Cảnh báo và sửa cấu hình; retry liên tục không giải quyết nguyên nhân |
| Rate limit | Backoff đủ dài và giới hạn concurrency |
| Lỗi cạnh tranh có thể hết | Retry ngắn nếu thao tác idempotent |

Retry chỉ phù hợp khi nguyên nhân có khả năng biến mất theo thời gian. Một lỗi validation cố định sẽ tiếp tục thất bại dù thử lại nhiều lần.

## 5. Cấu hình recoverer và Dead Letter Topic

Khi hết retry, DefaultErrorHandler gọi recoverer. Recoverer nhận record và exception cuối cùng, sau đó quyết định hành động tiếp theo. Một lựa chọn phổ biến là DeadLetterPublishingRecoverer để chuyển record sang DLT.

~~~java
@Bean
CommonErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 3L)
            );

    return handler;
}
~~~

Với cấu hình mặc định thông dụng, record từ topic nguồn được chuyển sang topic có hậu tố .DLT và giữ partition tương ứng. Ví dụ record từ orders partition 2 sẽ được định tuyến tới orders.DLT partition 2. Vì vậy, DLT cần có số partition phù hợp với cách định tuyến. Hãy tạo DLT trước trong môi trường production hoặc cấu hình resolver để kiểm soát việc tạo và định tuyến topic.

DLT nên giữ lại thông tin cần cho điều tra:

- Payload và key gốc.
- Topic, partition và offset nguồn.
- Event ID và correlation ID nếu có.
- Timestamp và headers.
- Exception cuối cùng và thông tin delivery attempt.
- Thời điểm record được chuyển sang DLT.

Không coi việc publish DLT là thành công chỉ vì recoverer đã được gọi. Cần cấu hình và theo dõi kết quả gửi DLT. Nếu broker không nhận được DLT record, hệ thống phải giữ khả năng phục hồi và phát cảnh báo thay vì âm thầm đánh dấu record nguồn đã được xử lý.

### 5.1. Tùy chỉnh đích DLT

Có thể cung cấp DestinationResolver để định tuyến theo topic hoặc loại record:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) -> new TopicPartition(
                record.topic() + ".DLT",
                record.partition()
            )
        );
~~~

Ví dụ này định tuyến tới DLT cùng tên nguồn cộng hậu tố .DLT, giữ partition nguồn. Nếu muốn chia DLT theo loại exception hoặc topic, hãy triển khai resolver có quy tắc rõ ràng và bảo đảm topic đích có partition hợp lệ.

Không đưa payload nhạy cảm vào tên topic hoặc headers. DLT là một phần của hệ thống lưu trữ và vận hành, nên áp dụng retention, quyền truy cập, mã hóa và giám sát phù hợp.

## 6. Phân loại exception retryable và non-retryable

Không phải exception nào cũng nên retry. DefaultErrorHandler hỗ trợ phân loại exception để quyết định lỗi nào có thể thử lại.

Ví dụ bỏ qua retry cho IllegalArgumentException:

~~~java
DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 3L));

handler.addNotRetryableExceptions(
    IllegalArgumentException.class
);
~~~

Với lỗi dữ liệu không hợp lệ, retry thường không thay đổi kết quả. Handler có thể chuyển record tới recoverer ngay. Ngược lại, lỗi tạm thời như timeout có thể retry theo backoff.

Có thể thêm loại exception được retry:

~~~java
handler.addRetryableExceptions(
    TransientDataAccessException.class,
    SocketTimeoutException.class
);
~~~

DefaultErrorHandler có sẵn một số phân loại mặc định cho các lỗi thường không thể retry, đặc biệt các lỗi chuyển đổi, deserialize hoặc phân giải tham số listener. Danh sách và hành vi cụ thể phụ thuộc phiên bản Spring Kafka. Khi thêm classification, kiểm tra xem cấu hình mới có ghi đè hay bổ sung phân loại mặc định theo API được dùng.

Với chính sách phức tạp, có thể dùng setClassifications() để khai báo map exception class tới trạng thái retryable và default classification. Chỉ dùng khi addRetryableExceptions() và addNotRetryableExceptions() không đủ, vì cấu hình classification tổng thể dễ bỏ sót loại exception.

### 6.1. Bảng phân loại mẫu

| Exception hoặc nhóm lỗi | Retry? | Lý do |
|---|---|---|
| SocketTimeoutException | Có giới hạn | Dịch vụ hoặc mạng có thể phục hồi |
| TransientDataAccessException | Có giới hạn | Database có thể tạm thời không sẵn sàng |
| IllegalArgumentException | Thường không | Dữ liệu hoặc tham số không hợp lệ |
| MessageConversionException | Thường không | Payload không khớp kiểu đích |
| DeserializationException | Thường không | Dữ liệu không thể deserialize theo cấu hình |
| AuthorizationException | Không retry liên tục | Cần sửa quyền hoặc credential |
| RecordTooLargeException | Không retry liên tục | Cần sửa kích thước record hoặc cấu hình |

Đây là phân loại tham khảo. Exception có thể được wrap trong cause chain, nên hãy kiểm tra exception thực tế mà handler nhận được và quy tắc classification của phiên bản thư viện đang dùng.

## 7. Quan sát retry bằng RetryListener

RetryListener cho phép ghi nhận từng lần delivery thất bại, kết quả recover và lỗi xảy ra trong quá trình recovery. Đây là điểm tốt để bổ sung metric và log có cấu trúc.

~~~java
handler.setRetryListeners((record, exception, deliveryAttempt) -> {
    log.warn(
        "Kafka delivery failed topic={} partition={} offset={} attempt={}",
        record.topic(),
        record.partition(),
        record.offset(),
        deliveryAttempt,
        exception
    );
});
~~~

Thông tin deliveryAttempt giúp biết record đã được thử bao nhiêu lần theo listener retry policy. Log nên có eventId nếu lấy được từ header hoặc payload, nhưng tránh ghi toàn bộ payload nhạy cảm.

RetryListener nên nhẹ. Không gọi database hoặc HTTP service blocking từ callback nếu điều đó làm chậm consumer thread. Dùng metric counter để thống kê số lần retry, số lần recovery thành công và số lần recovery thất bại.

Các tín hiệu cần theo dõi:

- Số lần listener thất bại theo exception class.
- Số retry trên mỗi topic/partition.
- Thời gian từ lần thất bại đầu tiên tới lần xử lý thành công.
- Số record được recover sang DLT.
- Số lỗi khi publish DLT.
- Tuổi record trong DLT và tốc độ DLT tăng.

## 8. Record listener và batch listener

CommonErrorHandler hỗ trợ cả record listener và batch listener, nhưng cách xác định record lỗi trong batch có ảnh hưởng lớn tới retry.

### 8.1. Record listener

Với record listener, container gọi listener cho từng record. Khi một record thất bại, DefaultErrorHandler có thể seek partition để giao lại record lỗi và các record sau đó theo chiến lược retry.

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Nếu process() ném exception, handler áp dụng backoff và retry. Khi hết retry, recoverer được gọi. Với DLT recoverer, record lỗi được chuyển sang topic đích. Các record tiếp theo có thể tiếp tục sau khi container hoàn tất recovery theo chính sách handler.

### 8.2. Batch listener

Với batch listener, một lần gọi listener nhận nhiều record. Nếu một record trong batch thất bại, handler cần biết record nào gây lỗi để tránh retry toàn bộ batch không cần thiết.

Spring Kafka cung cấp BatchListenerFailedException để listener chỉ ra record hoặc index gây lỗi:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-batch-service",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderEvent>> records) {

    for (int index = 0; index < records.size(); index++) {
        ConsumerRecord<String, OrderEvent> record = records.get(index);

        try {
            orderService.process(record.value());
        }
        catch (Exception exception) {
            throw new BatchListenerFailedException(
                "Could not process batch record",
                record
            );
        }
    }
}
~~~

Khi handler nhận BatchListenerFailedException, nó có thể commit các record trước record lỗi đã xử lý thành công, rồi retry record lỗi và phần còn lại. Điều này giảm việc chạy lại side effect của toàn bộ batch.

Nếu batch listener ném exception không xác định được record lỗi, handler có thể dùng fallback strategy để retry toàn bộ batch. Khi batch lớn, retry cả batch có thể gây chi phí cao và duplicate side effect. Nếu có thể xác định record lỗi, hãy dùng BatchListenerFailedException với đúng record hoặc index.

Batch listener cần thiết kế transaction và idempotency phù hợp. Việc một record trước đó trong batch đã ghi database thành công không có nghĩa lần retry toàn batch sẽ an toàn nếu side effect không idempotent.

## 9. Lỗi deserialize và ErrorHandlingDeserializer

Lỗi deserialize xảy ra trước khi listener nhận được object. Nếu Kafka deserializer ném exception trực tiếp trong poll(), listener không có cơ hội bắt lỗi theo cách thông thường. Để đưa lỗi deserialize vào luồng xử lý của Spring Kafka, thường dùng ErrorHandlingDeserializer bọc deserializer thực tế.

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: "com.example.events"
~~~

ErrorHandlingDeserializer lưu thông tin exception vào header của record để container/error handler có thể xử lý. Cấu hình delegate deserializer phải phù hợp với kiểu key/value và chiến lược type mapping của ứng dụng.

Nếu dùng JSON type header, kiểm tra trusted packages, default type và mapping theo phiên bản Spring Kafka. Không mở trusted packages quá rộng trong hệ thống có payload không đáng tin cậy.

DefaultErrorHandler có thể phân loại lỗi deserialize và chuyển record lỗi sang DLT. Tuy nhiên, nếu deserializer không giữ được payload hoặc header cần thiết do cấu hình sai, việc điều tra DLT sẽ khó khăn. Hãy kiểm thử record sai schema thực tế trước khi triển khai.

## 10. Acknowledgment và commit sau recovery

Sau khi error handler xử lý xong lỗi, container cần quyết định offset có được commit hay không. DefaultErrorHandler có thuộc tính ackAfterHandle để điều khiển việc commit sau khi exception đã được xử lý và handler trả về bình thường.

Theo hành vi mặc định, record được recover thành công có thể được xem là đã xử lý để container tiếp tục và commit theo chính sách container. Nếu thay đổi ackAfterHandle, hãy hiểu rõ ảnh hưởng tới redelivery. Nếu handler trả về bình thường nhưng offset không được commit theo cấu hình, record có thể được giao lại.

DefaultErrorHandler cũng hỗ trợ commitRecovered trong một số chế độ acknowledgment. Khi bật commitRecovered, cần dùng AckMode.MANUAL_IMMEDIATE theo yêu cầu của API:

~~~java
handler.setCommitRecovered(true);
~~~

Cấu hình này không nên bật chỉ để “chắc chắn hơn” nếu chưa hiểu cách container đang commit. Hãy xác định rõ:

- Listener đang dùng AckMode nào.
- Error handler xử lý lỗi theo record hay batch.
- Recoverer có hoàn tất thành công hay ném exception.
- Offset được commit bởi container hay handler.
- Consumer group có thể nhận lại record sau restart hay không.

Nếu database đã commit nhưng offset chưa commit, record có thể được giao lại. Dùng eventId và idempotent business operation để side effect không bị nhân đôi.

## 11. Seek behavior và xử lý sau lỗi

DefaultErrorHandler thường dùng seek để consumer đọc lại record lỗi và các record chưa được xử lý trong partition. Đây là cách blocking retry: record lỗi giữ luồng partition cho tới khi retry hoặc recovery hoàn tất.

Ở các phiên bản Spring Kafka mới, có thể cấu hình hành vi seekAfterError để giữ record chưa xử lý trong container thay vì thực hiện seek theo cách mặc định. Khi dùng chế độ này, container có thể tạm pause consumer và poll để duy trì group membership rồi giao lại các record còn lại. Chi tiết và cấu hình phụ thuộc phiên bản thư viện.

Blocking retry có ưu điểm là giữ thứ tự trong partition dễ dự đoán hơn. Nhược điểm là một record lỗi có thể làm chậm các record sau trong cùng partition. Nếu backoff dài, cần xem xét poll interval, heartbeat và container pausing backoff handler.

Không dùng retry blocking dài như một cơ chế trì hoãn hàng giờ. Với khoảng nghỉ dài hoặc cần tách record lỗi khỏi luồng chính, retry topic có thể phù hợp hơn.

## 12. Phân biệt CommonErrorHandler với retry topic

CommonErrorHandler và @RetryableTopic phục vụ hai chiến lược khác nhau:

| Cơ chế | Cách hoạt động | Phù hợp khi |
|---|---|---|
| DefaultErrorHandler | Retry record trong luồng consumer hiện tại theo backoff | Lỗi tạm thời, cần giữ thứ tự partition |
| @RetryableTopic | Chuyển record sang topic retry và giao lại sau | Cần trì hoãn dài hơn hoặc không muốn block partition chính |
| DLT | Lưu record đã hết retry hoặc không thể xử lý | Điều tra và phục hồi có kiểm soát |

Retry topic có thể làm thay đổi thứ tự sự kiện: record A được chuyển sang retry topic trong khi record B phía sau được xử lý trên topic chính. Nếu nghiệp vụ cần thứ tự nghiêm ngặt theo key, hãy cân nhắc điều này trước khi dùng non-blocking retry.

Không cấu hình đồng thời blocking retry và retry topic cho cùng một lỗi mà không xác định tổng số lần thử. Nếu hai tầng retry cùng hoạt động, số lần gọi dịch vụ có thể nhân lên và làm tăng thời gian xử lý ngoài dự kiến.

## 13. DLT recovery thất bại

Recoverer cũng có thể thất bại. Ví dụ DLT topic không tồn tại, broker không sẵn sàng, producer không serialize được record hoặc publish timeout. Trong trường hợp này, không nên coi record gốc đã được phục hồi thành công.

DefaultErrorHandler có cơ chế xử lý khi recoverer ném exception. Khi recovery thất bại, trạng thái retry có thể được reset để record được thử lại theo backoff trong lần giao tiếp theo. Hành vi reset và cách cấu hình phụ thuộc phiên bản. Cần theo dõi recovery failure riêng với listener failure.

Các điểm vận hành:

- DLT topic phải tồn tại hoặc broker được phép tạo topic theo chính sách đã kiểm soát.
- Serializer của producer DLT phải xử lý được payload lỗi và kiểu dữ liệu tương ứng.
- DLT cần đủ partition nếu resolver giữ partition nguồn.
- Publish DLT phải được quan sát qua callback/metric và lỗi gửi phải được phát hiện.
- Không xóa hoặc commit offset record gốc khi chưa bảo đảm record lỗi đã được lưu theo chính sách recovery.
- Có quy trình re-drive và giữ eventId gốc để consumer idempotent nhận diện bản phát lại.

## 14. Xử lý exception theo cause chain

Exception trong listener thường bị bọc bởi các exception khác. Ví dụ lỗi database có thể được bọc trong ListenerExecutionFailedException. Nếu classification chỉ nhìn exception ngoài cùng mà không xét cause, handler có thể phân loại sai.

DefaultErrorHandler và các thành phần hỗ trợ có quy tắc tìm exception trong cause chain. Tuy nhiên, hãy kiểm tra exception thực tế trong log và phiên bản thư viện đang dùng. Khi ứng dụng tự wrap exception, nên giữ cause gốc:

~~~java
try {
    repository.save(entity);
}
catch (DataAccessException exception) {
    throw new OrderPersistenceException(
        "Could not persist order",
        exception
    );
}
~~~

Nếu cause gốc bị mất, error handler khó nhận diện loại lỗi tạm thời. Tránh tạo một exception chung cho mọi tình huống nếu retry policy cần phân biệt timeout, validation và lỗi quyền.

## 15. Custom CommonErrorHandler khi cần chính sách riêng

DefaultErrorHandler đáp ứng phần lớn nhu cầu phổ biến. Chỉ nên triển khai CommonErrorHandler trực tiếp khi cần điều khiển đặc biệt, chẳng hạn chuyển lỗi tới hệ thống điều phối riêng hoặc áp dụng quy tắc không thể mô tả bằng BackOff và recoverer.

Một custom handler cần hiểu các điểm hợp đồng:

- Xử lý một record lỗi với handleOne() nếu chiến lược có thể xử lý record mà không cần seek các record còn lại.
- Xử lý record và các record còn lại bằng handleRemaining() khi cần tự điều khiển seek.
- Xử lý batch bằng handleBatch().
- Xử lý exception phát sinh ngoài listener invocation bằng handleOtherException().
- Khai báo seeksAfterHandling() chính xác để container biết handler đã tự seek hay chưa.
- Xác định isAckAfterHandle() để container biết có thể commit sau khi handler xử lý thành công hay không.
- Khai báo deliveryAttemptHeader() nếu handler hỗ trợ header delivery attempt.

Các method signature và contract có thể thay đổi theo phiên bản Spring Kafka. Đọc Javadoc của phiên bản dependency trước khi implement. Sai sót trong seek hoặc acknowledgment có thể làm mất record hoặc gây giao lặp không giới hạn.

Nếu chỉ cần thêm log, metric hoặc một classification, hãy cấu hình DefaultErrorHandler thay vì viết lại toàn bộ contract. Custom handler phải có kiểm thử tích hợp cho record listener, batch listener, rebalance và commit.

## 16. Cấu hình đầy đủ có DLT và phân loại lỗi

Ví dụ sau kết hợp DLT, retry hữu hạn, lỗi không retry và callback theo dõi:

~~~java
@Configuration
public class KafkaErrorConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaErrorConfiguration.class);

    @Bean
    CommonErrorHandler commonErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 3L)
                );

        handler.addNotRetryableExceptions(
            IllegalArgumentException.class,
            MessageConversionException.class
        );

        handler.setRetryListeners((record, exception, deliveryAttempt) -> {
            log.warn(
                "Kafka retry topic={} partition={} offset={} attempt={}",
                record.topic(),
                record.partition(),
                record.offset(),
                deliveryAttempt,
                exception
            );
        });

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            CommonErrorHandler commonErrorHandler) {

        ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(commonErrorHandler);

        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }
}
~~~

Các import chính cần thiết tùy cấu hình ứng dụng:

~~~java
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.util.backoff.FixedBackOff;
~~~

Ví dụ có thể cần thêm import cho MessageConversionException, Logger và LoggerFactory. Kiểu generic của KafkaTemplate, ConsumerFactory và listener phải khớp với serializer/deserializer của ứng dụng. Nếu dự án dùng các phiên bản Spring Kafka khác nhau, xác nhận API RetryListener và các method cấu hình trong Javadoc tương ứng.

## 17. Spring Boot và nhiều listener factory

Ứng dụng có thể có nhiều listener với yêu cầu lỗi khác nhau. Ví dụ:

- orders listener: retry ngắn và DLT riêng.
- payments listener: retry có giới hạn, cảnh báo ngay khi lỗi.
- analytics listener: có thể bỏ qua một số lỗi dữ liệu và lưu DLT để phân tích.
- batch listener: cần BatchListenerFailedException để xác định record lỗi.

Có thể tạo nhiều factory và gắn CommonErrorHandler phù hợp cho từng factory. Mỗi factory nên có tên rõ ràng, concurrency và AckMode phù hợp.

Không nên dùng một error handler có cấu hình retry dài cho mọi listener nếu thời gian xử lý và yêu cầu thứ tự khác nhau. Chính sách lỗi nên gắn với SLA và hậu quả nghiệp vụ của từng loại event.

Nếu ứng dụng có bean factory mặc định do Spring Boot tạo và factory tùy chỉnh, hãy kiểm tra bean nào được @KafkaListener sử dụng. Cấu hình bean không được tham chiếu sẽ không có tác dụng với listener đó.

## 18. Quản lý retry storm và thứ tự xử lý

Retry storm xảy ra khi nhiều record cùng thất bại và consumer thử lại quá thường xuyên. Nó có thể làm dịch vụ phụ thuộc quá tải hơn, kéo dài lag và khiến nhiều partition cùng bị nghẽn.

Để giảm rủi ro:

- Dùng backoff tăng dần và giới hạn số lần thử.
- Đặt timeout cho database và HTTP client.
- Phân loại lỗi cố định để không retry vô ích.
- Giới hạn concurrency tới dịch vụ phụ thuộc.
- Theo dõi tỷ lệ retry theo exception và dependency.
- Chuyển record lỗi không thể phục hồi sang DLT.
- Dùng circuit breaker hoặc bulkhead nếu phù hợp với dependency.

Với blocking retry, record lỗi có thể giữ partition cho tới khi xử lý xong hoặc được recover. Điều này giữ thứ tự trong partition dễ dự đoán nhưng làm record phía sau chờ. Với retry topic, luồng chính có thể tiếp tục nhưng thứ tự event có thể thay đổi. Chọn cơ chế dựa trên yêu cầu ordering, không chỉ dựa trên tốc độ.

## 19. Kiểm thử CommonErrorHandler

Kiểm thử cần xác nhận cả hành vi listener, retry, recovery và offset. Không chỉ kiểm tra bean được tạo thành công.

Các kịch bản nên có:

1. Listener thất bại lần đầu rồi thành công ở lần retry: xác nhận số lần thử và backoff.
2. Listener luôn thất bại: xác nhận recoverer được gọi sau khi hết retry.
3. Exception non-retryable: xác nhận handler chuyển thẳng sang recovery theo classification.
4. DLT không khả dụng: xác nhận recovery failure được ghi nhận và record không bị âm thầm bỏ qua.
5. Batch listener ném BatchListenerFailedException: xác nhận record trước lỗi không bị xử lý lại ngoài dự kiến.
6. Batch listener ném exception chung: xác nhận fallback batch retry đúng như cấu hình.
7. Deserialization lỗi: xác nhận ErrorHandlingDeserializer đưa lỗi tới handler.
8. Consumer rebalance trong lúc retry: xác nhận offset và record có thể được phục hồi an toàn.
9. Recovery thành công: xác nhận offset được commit theo AckMode và ackAfterHandle.
10. Side effect thành công nhưng offset chưa commit: xác nhận consumer idempotent khi record được giao lại.
11. Retry rate tăng đột biến: xác nhận metric, cảnh báo và giới hạn tải.
12. Re-drive từ DLT: xác nhận eventId được giữ nguyên và nghiệp vụ không bị áp dụng hai lần.

Dùng EmbeddedKafka hoặc broker test phù hợp với stack của dự án để kiểm tra hành vi thực tế. Unit test cho classification và recoverer hữu ích, nhưng không thay thế tích hợp vì seek, poll, commit và rebalance do container cùng Kafka client phối hợp.

## 20. Quan sát trong production

Một cấu hình CommonErrorHandler tốt phải cung cấp đủ dữ liệu để đội vận hành hiểu record đang ở trạng thái nào.

**Retry**

- Retry count theo topic, partition và exception class.
- Thời gian chờ backoff.
- Tỷ lệ retry thành công.
- Số record đã hết retry.

**Recovery và DLT**

- Số record được chuyển DLT.
- Tuổi record cũ nhất trong DLT.
- Số lần publish DLT thất bại.
- Số record được re-drive và kết quả re-drive.

**Container**

- Listener error rate.
- Consumer lag.
- Rebalance count và duration.
- Commit latency và commit failure.
- Thời gian xử lý record p95/p99.

Log nên có eventId, topic, partition, offset, consumer group, delivery attempt và exception class. Tránh log toàn bộ payload có thông tin cá nhân hoặc dữ liệu nhạy cảm. Dùng correlation ID để nối log producer, listener, dependency và DLT.

Khi lag tăng, cần phân biệt record đang chờ xử lý lần đầu với record bị giữ trong retry. Khi DLT tăng, cần biết nguyên nhân là dữ liệu lỗi, dependency hay cấu hình. Metric retry và recovery giúp phân biệt các tình huống này.

## 21. Những lỗi cấu hình thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Chỉ khai báo bean CommonErrorHandler | Factory tùy chỉnh có thể không dùng bean đó | Gọi setCommonErrorHandler() trên factory |
| Retry mọi exception | Lỗi dữ liệu hoặc cấu hình lặp vô ích | Phân loại retryable/non-retryable |
| Backoff không giới hạn | Record có thể giữ partition quá lâu | Giới hạn số lần thử và có DLT |
| DLT thiếu partition | Recoverer giữ partition nguồn có thể không publish được | Tạo DLT đủ partition hoặc custom resolver |
| Bỏ qua lỗi publish DLT | Record gốc có thể bị mất khỏi luồng phục hồi | Theo dõi recovery failure và không coi recover là thành công |
| Batch listener không chỉ ra record lỗi | Handler có thể retry cả batch | Ném BatchListenerFailedException với record/index phù hợp |
| Dùng retry topic cùng blocking retry không tính tổng lần thử | Số lần gọi dependency có thể nhân lên | Thiết kế một ngân sách retry tổng thể |
| Commit offset trước side effect | Có thể mất tác vụ nghiệp vụ | Commit sau xử lý bền vững |
| Side effect không idempotent | Record được giao lại có thể gây duplicate | Dùng eventId, inbox hoặc idempotency key |
| Dùng API cũ sau nâng cấp | Cấu hình không còn tương thích | Chuyển sang CommonErrorHandler và kiểm tra version |

## 22. Nguyên tắc lựa chọn trong production

- Dùng CommonErrorHandler làm hợp đồng xử lý lỗi chung cho listener container.
- Ưu tiên DefaultErrorHandler khi cần retry, backoff và recovery phổ biến.
- Gắn handler rõ ràng vào từng ConcurrentKafkaListenerContainerFactory.
- Chọn backoff hữu hạn dựa trên SLA và thời gian phục hồi dependency.
- Phân loại exception để lỗi cố định không retry vô ích.
- Dùng recoverer và DLT cho record không thể xử lý tự động.
- Đảm bảo DLT có partition, serializer, retention và quyền truy cập phù hợp.
- Dùng BatchListenerFailedException để chỉ ra record lỗi trong batch listener.
- Tắt auto commit khi container quản lý offset và chọn AckMode phù hợp.
- Phân biệt blocking retry với retry topic, đặc biệt khi nghiệp vụ cần thứ tự.
- Làm side effect idempotent vì retry, recovery và rebalance có thể tạo redelivery.
- Theo dõi retry, recovery failure, DLT, lag và commit.
- Kiểm thử cả trường hợp listener lỗi, DLT lỗi và offset chưa commit.
- Kiểm tra API theo đúng phiên bản Spring Kafka của ứng dụng.

CommonErrorHandler cung cấp một điểm cấu hình thống nhất cho lỗi trong listener container. Khi kết hợp DefaultErrorHandler, BackOff, exception classification và recoverer phù hợp, ứng dụng có thể thử lại lỗi tạm thời, cô lập record không thể xử lý và tiếp tục tiêu thụ có kiểm soát. Độ tin cậy cuối cùng vẫn phụ thuộc vào việc commit offset đúng thời điểm, giữ side effect idempotent và vận hành DLT như một luồng phục hồi có giám sát.
