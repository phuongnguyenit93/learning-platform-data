# Transient exception và permanent exception

Trong hệ thống Kafka, không phải mọi exception đều nên được xử lý bằng cùng một chính sách retry. Một số lỗi chỉ tồn tại trong thời gian ngắn, chẳng hạn broker đang bầu leader hoặc kết nối mạng vừa bị gián đoạn. Một số lỗi sẽ tiếp tục xảy ra cho đến khi ứng dụng thay đổi dữ liệu, schema, cấu hình hoặc quyền truy cập. Phân biệt hai nhóm này giúp consumer phục hồi sau sự cố tạm thời mà không lặp vô hạn trên một record không thể xử lý.

**Transient exception** là lỗi có khả năng tự hết khi điều kiện bên ngoài phục hồi hoặc sau một khoảng chờ. **Permanent exception** là lỗi không thể được khắc phục chỉ bằng cách thử lại cùng thao tác với cùng dữ liệu và điều kiện. Permanent không có nghĩa lỗi không bao giờ sửa được: dữ liệu có thể được chỉnh, schema có thể được cập nhật hoặc ACL có thể được cấp. Nó có nghĩa retry ngay lập tức mà không thay đổi nguyên nhân thường không đem lại kết quả.

Trong Spring Kafka, phân loại lỗi quyết định record được retry trên consumer thread, chuyển sang retry topic, phục hồi vào Dead Letter Topic (DLT), hay dừng luồng để can thiệp. Cách phân loại phải dựa trên nguyên nhân gốc và ngữ cảnh nghiệp vụ, không chỉ dựa vào tên exception.

## 1. Transient và permanent exception

### 1.1. Transient exception

Transient exception xuất hiện khi một thành phần tạm thời không thể hoàn thành thao tác, nhưng thao tác có thể thành công nếu thử lại sau khi hệ thống ổn định.

Ví dụ:

- Broker hoặc partition leader tạm thời không sẵn sàng trong lúc leader election.
- Kết nối mạng bị ngắt trong thời gian ngắn.
- Request timeout do broker hoặc dependency đang quá tải.
- Database tạm thời từ chối kết nối vì pool đang cạn hoặc failover.
- HTTP service trả về lỗi 503 trong một đợt triển khai hoặc phục hồi.
- Một số lỗi replica/ISR có thể hết sau khi broker trở lại và ISR được khôi phục.

Retry có thể phù hợp, nhưng phải có giới hạn thời gian, backoff và quan sát. Nếu lỗi kéo dài, retry liên tục có thể làm tăng tải lên chính dependency đang gặp sự cố.

### 1.2. Permanent exception

Permanent exception phản ánh điều kiện khiến thao tác không thể thành công nếu ứng dụng gửi lại cùng request và không thay đổi gì.

Ví dụ:

- Payload thiếu trường bắt buộc hoặc sai định dạng.
- Deserialization hoặc schema validation thất bại do dữ liệu không tương thích.
- Business rule từ chối một đơn hàng vì trạng thái không hợp lệ.
- Topic hoặc resource được cấu hình sai.
- Principal không có quyền truy cập topic hoặc consumer group.
- Record luôn vượt giới hạn kích thước đã cấu hình.
- Ứng dụng dùng kiểu dữ liệu hoặc contract không tương thích với handler.

Các lỗi này cần được sửa dữ liệu, thay đổi cấu hình/quyền hoặc chuyển vào quy trình xử lý lỗi. Retry cùng record vô hạn chỉ làm consumer lặp lại lỗi, tăng lag và trì hoãn các record khác.

### 1.3. Permanent không đồng nghĩa với không thể phục hồi

Một lỗi có thể permanent đối với lần xử lý hiện tại nhưng có thể sửa trong tương lai. Ví dụ một event dùng schema version chưa được consumer hỗ trợ sẽ tiếp tục lỗi cho đến khi consumer được cập nhật hoặc event được chuyển đổi.

Phân loại nên trả lời câu hỏi: **Nếu thử lại ngay với cùng record và cùng trạng thái hệ thống, khả năng thành công có đủ cao không?** Nếu không, retry ngay không có giá trị. Hãy lưu lỗi và cung cấp đường sửa/replay.

## 2. Phân loại theo nguyên nhân thay vì chỉ theo tên exception

Tên exception cho biết một phần thông tin, nhưng cùng một exception class có thể đại diện cho nhiều nguyên nhân khác nhau. Một timeout có thể do broker tạm thời quá tải, do DNS sai, do firewall chặn kết nối hoặc do service đích đã ngừng hoạt động.

| Nhóm nguyên nhân | Ví dụ | Phân loại thường gặp | Hành động ban đầu |
|---|---|---|---|
| Mạng và kết nối | Disconnect, connection reset, network timeout | Transient nếu hạ tầng đang phục hồi | Retry có backoff, kiểm tra network và broker |
| Broker/partition | Leader not available, not leader, coordinator unavailable | Thường transient | Cho client/container retry trong giới hạn; kiểm tra cluster nếu kéo dài |
| Replica và durability | Not enough replicas, ISR không đủ | Có thể transient hoặc kéo dài | Theo dõi ISR, replication và min.insync.replicas |
| Quota/throttling | Request bị throttle do quota | Thường có thể phục hồi sau thời gian chờ | Tôn trọng throttle/backoff, xem lại quota và tải |
| Xác thực/phân quyền | Authentication hoặc authorization failure | Permanent cho đến khi credential/ACL thay đổi | Sửa credential, principal hoặc ACL |
| Serialization/deserialization | Payload sai format, schema không tương thích | Thường permanent đối với payload hiện tại | Đưa record vào DLT, sửa producer/consumer/schema |
| Business validation | Trạng thái đơn hàng không hợp lệ, thiếu dữ liệu nghiệp vụ | Permanent đối với trạng thái hiện tại | Từ chối hoặc chuyển quy trình sửa dữ liệu |
| Giới hạn kích thước | Record/request quá lớn | Permanent nếu payload/limit không đổi | Giảm payload hoặc điều chỉnh giới hạn có kiểm soát |
| Tài nguyên ứng dụng | Thread pool đầy, connection pool cạn | Có thể transient, có thể là capacity issue kéo dài | Backpressure, giảm concurrency, tăng capacity đúng chỗ |

Không nên gắn nhãn transient cho mọi exception có từ khóa timeout hoặc permanent cho mọi lỗi 4xx/5xx. Cần đọc status code, root cause, retry-after, trạng thái dependency và hợp đồng của API.

## 3. Exception classification trong Kafka client

Kafka client có hệ thống exception riêng. Một số lỗi là subclass của **RetriableException**, biểu thị rằng thao tác có thể được thử lại trong điều kiện phù hợp. Producer client tự retry một số lỗi gửi record theo cấu hình retries, backoff và delivery timeout.

Ví dụ các lỗi thường gắn với trạng thái broker hoặc kết nối:

- **NotLeaderOrFollowerException:** broker nhận request không còn là leader phù hợp cho partition; metadata có thể cần được cập nhật.
- **LeaderNotAvailableException:** partition chưa có leader sẵn sàng.
- **NetworkException / DisconnectException:** request bị ảnh hưởng bởi lỗi kết nối.
- **RequestTimedOutException:** request không hoàn tất trong thời gian chờ.
- **NotEnoughReplicasException:** số replica trong ISR không đáp ứng điều kiện yêu cầu.

Các lỗi này thường có khả năng phục hồi, nhưng không bảo đảm rằng retry vô hạn sẽ thành công. Ví dụ ISR có thể không đủ trong thời gian dài vì broker bị hỏng; lúc đó cần khôi phục cluster thay vì tăng retry.

Một số lỗi thường không thể sửa bằng cách retry cùng request:

- **RecordTooLargeException:** payload vượt giới hạn.
- **TopicAuthorizationException:** principal thiếu quyền trên topic.
- **AuthenticationException:** thông tin xác thực hoặc cơ chế bảo mật không hợp lệ.
- **SerializationException:** serializer không thể chuyển dữ liệu thành byte hợp lệ.
- **InvalidTopicException:** tên hoặc cấu hình topic không hợp lệ.

Danh sách và inheritance có thể thay đổi theo Kafka client version. Ngoài ra, exception do ứng dụng hoặc thư viện dependency ném ra có thể không thuộc cây exception Kafka. Hãy phân loại theo root cause và hành vi thực tế thay vì chỉ kiểm tra một superclass.

## 4. Phân loại exception trong Spring Kafka

Spring Kafka cung cấp cơ chế xử lý lỗi cho listener container. Với luồng non-transactional, **DefaultErrorHandler** là một thành phần chính để cấu hình retry/backoff và recovery. Error handler nhận exception từ listener, quyết định record có được thử lại, phục hồi sang nơi khác hay dừng xử lý.

Về mặt khái niệm, quy trình là:

~~~
Listener xử lý record
        |
        +---- Thành công
        |       |
        |       v
        |    Commit theo AckMode
        |
        +---- Ném exception
                |
                v
        DefaultErrorHandler
                |
          Phân loại exception
                |
        +-------+--------+
        |                |
    Retryable         Not retryable
        |                |
        v                v
   Backoff/retry     Recoverer / DLT
        |                |
        v                v
   Thành công?       Ghi nhận lỗi
        |                |
        v                v
   Tiếp tục/commit   Commit theo recovery policy
~~~

Error handler cần biết lỗi nào có thể thử lại, số lần thử, backoff giữa các lần và hành động sau khi retry hết. Permanent exception nên được phục hồi nhanh theo chính sách, thay vì giữ partition ở một record lỗi trong thời gian dài.

## 5. Cấu hình retry và backoff với DefaultErrorHandler

Một cấu hình cơ bản có thể dùng **FixedBackOff**:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    FixedBackOff backOff = new FixedBackOff(
        1_000L,  // chờ 1 giây giữa các lần retry
        3L       // tối đa 3 lần retry
    );

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Trong ví dụ, error handler thử lại record theo backoff trước khi gọi recoverer. Cách đếm lần retry và hành vi cuối cùng cần được xác nhận theo API Spring Kafka version đang dùng. Một số phiên bản có mặc định phân loại các exception nhất định là fatal/non-retryable.

Có thể dùng **ExponentialBackOffWithMaxRetries** để tăng khoảng chờ theo cấp số nhân:

~~~java
ExponentialBackOffWithMaxRetries backOff =
    new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, backOff);
~~~

Với backoff này, khoảng chờ tăng dần nhưng bị giới hạn bởi max interval. Exponential backoff giúp giảm áp lực lên dependency đang phục hồi. Trong môi trường nhiều consumer, cân nhắc jitter nếu cơ chế retry của ứng dụng hỗ trợ để tránh các instance retry đồng loạt.

Backoff không nên được chọn tách rời khỏi max.poll.interval.ms. Nếu retry blocking trong consumer thread, tổng thời gian xử lý và chờ có thể làm consumer không poll đúng hạn. Với retry dài, cân nhắc pause container hoặc retry topic.

## 6. Đánh dấu exception retryable và non-retryable

Spring Kafka cho phép cấu hình classification cho **DefaultErrorHandler**. Có thể thêm exception không retry hoặc exception được retry theo chính sách của ứng dụng.

Ví dụ đánh dấu lỗi validation là non-retryable:

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 3L));

handler.addNotRetryableExceptions(
    InvalidOrderException.class,
    UnsupportedEventVersionException.class
);
~~~

Ví dụ đánh dấu một lỗi dependency có thể retry:

~~~java
handler.addRetryableExceptions(
    InventoryServiceUnavailableException.class,
    TemporaryDatabaseException.class
);
~~~

Tên method và quy tắc ưu tiên có thể khác theo phiên bản. Hãy kiểm tra Javadoc của Spring Kafka đang dùng. Nếu classification cần kiểm tra thêm thông tin như HTTP status, error code hoặc business state, có thể dùng cơ chế classifier/custom predicate thích hợp thay vì chỉ phân loại theo class.

Một điểm quan trọng là exception wrapper. Listener có thể ném **RuntimeException** bao quanh một **SQLException** hoặc **HttpServerErrorException**. Nếu classification chỉ nhìn lớp ngoài, nó có thể đánh giá sai. Hãy unwrap root cause hoặc tạo exception domain rõ ràng tại ranh giới gọi dependency.

### 6.1. Dùng exception riêng cho domain

Thay vì để listener phụ thuộc trực tiếp vào mọi exception từ database/HTTP client, service có thể chuyển chúng thành exception mang ý nghĩa nghiệp vụ:

~~~java
public class InventoryServiceUnavailableException
        extends RuntimeException {

    public InventoryServiceUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}

public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

Khi gọi service:

~~~java
try {
    inventoryClient.reserve(order);
}
catch (ResourceAccessException ex) {
    throw new InventoryServiceUnavailableException(
        "Inventory service is temporarily unavailable", ex);
}
catch (HttpClientErrorException.BadRequest ex) {
    throw new InvalidOrderException(
        "Order cannot be reserved: " + ex.getStatusCode());
}
~~~

Việc chuyển đổi phải dựa trên hợp đồng thực tế của dependency. Không phải mọi ResourceAccessException đều tạm thời; DNS sai hoặc cấu hình TLS sai có thể kéo dài cho tới khi sửa. Không phải mọi 4xx đều permanent; 429 thường có thể retry sau khoảng thời gian được chỉ định.

## 7. Retryable và non-retryable không phải lúc nào cũng cố định

Một exception class có thể cần phân loại khác nhau tùy ngữ cảnh.

Ví dụ **TimeoutException**:

- Timeout do broker leader vừa chuyển: có thể retry.
- Timeout do dependency quá tải trong vài giây: có thể retry với backoff.
- Timeout do endpoint cấu hình sai hoặc firewall chặn vĩnh viễn: retry không giúp ích.
- Timeout khi gọi API thanh toán mà kết quả giao dịch chưa rõ: không nên gửi lại lệnh thanh toán như một request mới nếu chưa tra cứu trạng thái bằng idempotency key.

Ví dụ **HTTP 429 Too Many Requests**:

- Có thể retry sau khoảng thời gian Retry-After.
- Nếu ứng dụng bỏ qua thời gian chờ và retry liên tục, tình trạng throttling có thể nặng hơn.
- Nếu quota bị cấu hình sai hoặc vượt giới hạn cố định, cần thay đổi quota hoặc lưu lượng.

Ví dụ **HTTP 404 Not Found**:

- Nếu resource thật sự không tồn tại, lỗi có thể permanent đối với event hiện tại.
- Nếu event được phát trước khi resource được tạo ở hệ thống khác, lỗi có thể là transient do thứ tự sự kiện hoặc eventual consistency.

Vì vậy, classification có thể cần kết hợp exception type, status code, error code, event type, retry-after và trạng thái nghiệp vụ.

## 8. Permanent exception và Dead Letter Topic

Khi một record không thể xử lý sau chính sách retry, **Dead Letter Topic (DLT)** là nơi lưu record lỗi cùng metadata để điều tra và xử lý sau.

Spring Kafka cung cấp **DeadLetterPublishingRecoverer** để publish record sang DLT. Ví dụ:

~~~java
@Bean
DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> template) {

    return new DeadLetterPublishingRecoverer(
        template,
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        )
    );
}
~~~

Ví dụ định tuyến record từ topic orders sang orders.DLT, giữ partition tương ứng nếu topic DLT có đủ partition. Cần cấu hình serializer cho cả key/value và header, cũng như bảo đảm topic DLT tồn tại và có replication/retention phù hợp.

DLT nên giữ metadata hữu ích:

- Topic, partition và offset gốc.
- Exception class và message đã được làm sạch.
- Thời điểm thất bại và số lần retry.
- Consumer group hoặc application ID.
- Event ID/business key và correlation ID.
- Schema/version nếu có.

Không đưa secret, token hoặc payload nhạy cảm vào header/log nếu không có chính sách bảo vệ tương ứng.

Khi record được publish thành công vào DLT, error handler có thể xem recovery hoàn tất và cho phép offset gốc được commit theo AckMode. Nếu publish DLT thất bại, cần xác định chính sách: tiếp tục retry recovery, dừng container hay để record được đọc lại. Không nên commit offset gốc trước khi record lỗi được lưu bền vững theo yêu cầu nghiệp vụ.

## 9. Phân biệt blocking retry và non-blocking retry

### 9.1. Blocking retry

Blocking retry thực hiện lại record trong luồng consumer/listener trước khi tiếp tục với các record tiếp theo theo semantics của container.

Ưu điểm:

- Dễ giữ thứ tự xử lý trong partition hơn.
- Không cần thêm retry topic.
- Phù hợp với lỗi transient có thời gian phục hồi ngắn.

Nhược điểm:

- Consumer thread bị giữ trong thời gian retry và backoff.
- Record lỗi có thể chặn các record phía sau trong partition.
- Retry kéo dài có thể vượt max.poll.interval.ms.
- Một record poison có thể làm lag tăng nhanh nếu chính sách không giới hạn.

### 9.2. Non-blocking retry topic

Non-blocking retry chuyển record lỗi sang một hoặc nhiều retry topic, thường có thời gian chờ khác nhau. Consumer chính có thể tiếp tục xử lý record sau đó.

Ưu điểm:

- Không giữ consumer chính chờ backoff dài.
- Có thể đặt thời gian retry khác nhau cho từng cấp.
- Tách luồng xử lý lỗi và quan sát backlog retry.

Nhược điểm:

- Có thể thay đổi thứ tự xử lý giữa các record cùng key/partition.
- Cần quản lý topic retry, retention, routing và DLT.
- Tăng số luồng vận hành và độ phức tạp replay.
- Có giới hạn khi dùng cùng transaction và một số cấu hình batch.

Spring Kafka hỗ trợ retry topic qua **@RetryableTopic** và các cấu hình tương ứng. Cơ chế này phù hợp khi nghiệp vụ chấp nhận việc record lỗi được xử lý sau các record mới hơn. Nếu thứ tự là bắt buộc, hãy cân nhắc blocking retry hoặc thiết kế luồng xử lý có kiểm soát thứ tự.

## 10. Retry và consumer transaction

Khi listener container sử dụng Kafka transaction manager, listener exception có thể làm transaction abort. Output records và offset input trong transaction không được commit, nên record đầu vào có thể được đọc lại.

Với transactional listener, Spring Kafka thường dùng **DefaultAfterRollbackProcessor** để quyết định retry và recovery sau rollback. Đây là cơ chế khác với DefaultErrorHandler ở luồng non-transactional. Khi đã vượt số lần retry, processor có thể dùng recoverer để gửi record lỗi sang DLT.

Các điểm cần xác định:

- Transaction được abort khi exception nào thoát khỏi listener?
- Record được retry bao nhiêu lần và backoff thế nào?
- Output đã gửi trong transaction có bị abort cùng offset không?
- Recovery/DLT có nằm trong transaction theo cấu hình không?
- Offset gốc được commit khi nào?
- Side effect database/HTTP ngoài Kafka có thể lặp hay không?

Không được cho rằng Kafka transaction rollback được database hoặc HTTP call. Nếu listener gọi API thành công rồi transaction abort, lần xử lý sau có thể gọi API lại. Dùng idempotency key, outbox/inbox hoặc saga cho side effect ngoài Kafka.

## 11. Xử lý lỗi serialization và deserialization

Serialization/deserialization là nhóm lỗi đặc biệt vì lỗi có thể xảy ra trước khi listener nhận được object.

### 11.1. Serialization ở producer

Producer serializer chuyển key/value thành byte trước khi gửi. Nếu payload không hợp lệ hoặc schema không tương thích, producer có thể ném **SerializationException**. Retry cùng object thường không sửa được dữ liệu.

Hướng xử lý:

1. Xác định field hoặc schema gây lỗi.
2. Ghi lại event ID và phiên bản schema.
3. Sửa producer hoặc dữ liệu nguồn.
4. Đưa event không hợp lệ vào quy trình từ chối/replay có kiểm soát.

### 11.2. Deserialization ở consumer

Nếu Kafka consumer không thể deserialize record, listener có thể không được gọi vì lỗi xảy ra trong quá trình poll. Spring Kafka cung cấp **ErrorHandlingDeserializer** để chuyển lỗi deserialization vào header của record và cho phép container/error handler xử lý.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Ví dụ chỉ minh họa cấu trúc; delegate class và trusted packages cần được cấu hình theo serializer thực tế. Với lỗi deserialization permanent, error handler thường nên phục hồi sang DLT thay vì retry cùng byte payload vô hạn.

Spring Kafka có thể xem một số exception như DeserializationException, MessageConversionException hoặc ConversionException là fatal/non-retryable theo mặc định của DefaultErrorHandler. Danh sách mặc định phụ thuộc phiên bản; kiểm tra Javadoc và cấu hình hiện tại trước khi thay đổi classification.

## 12. Poison record và tác động lên consumer group

Poison record là record liên tục gây lỗi khi xử lý, thường do payload không hợp lệ, schema không tương thích hoặc business state không thể thỏa mãn. Nếu consumer retry vô hạn và không có recovery, partition có thể bị kẹt tại record đó.

Hậu quả:

- Consumer lag tăng ở partition bị kẹt.
- Record phía sau trong partition không được xử lý theo thứ tự.
- Consumer thread bị chiếm bởi retry/backoff.
- max.poll.interval.ms có thể bị vượt nếu retry kéo dài.
- Rebalance có thể xảy ra, dẫn tới record được xử lý lại.

Permanent exception nên được đưa vào DLT hoặc quy trình xử lý lỗi tương ứng sau số lần retry phù hợp. Nếu dữ liệu có thể được sửa sau đó, cần giữ đủ metadata để replay đúng record và tránh áp dụng nghiệp vụ hai lần.

Không tự động gửi lại mọi DLT record vào topic gốc mà không kiểm tra nguyên nhân. Nếu payload vẫn sai, record sẽ trở thành poison record lần nữa và tạo vòng lặp.

## 13. Thiết kế retry budget và backoff

Retry cần có ngân sách rõ ràng. Một chính sách nên xác định:

- Số lần retry tối đa.
- Tổng thời gian tối đa cho một record.
- Khoảng chờ ban đầu và mức tăng.
- Khoảng chờ tối đa.
- Jitter nếu có nhiều consumer retry đồng thời.
- Exception nào retry được và exception nào không.
- Hành động recovery khi hết retry.
- Metric và alert cho retry/DLT.

Ví dụ một chính sách minh họa:

| Lần retry | Khoảng chờ |
|---:|---:|
| 1 | 500 ms |
| 2 | 1 giây |
| 3 | 2 giây |
| 4 | 4 giây |
| 5 | 8 giây |
| Sau lần 5 | Gửi DLT hoặc recovery theo chính sách |

Không chọn backoff chỉ dựa trên số lần. Hãy căn cứ thời gian phục hồi dự kiến của dependency và SLO xử lý record. Nếu dependency thường phục hồi trong vài giây, retry hàng chục phút sẽ giữ tài nguyên và tăng lag không cần thiết.

Đối với blocking retry, tổng backoff phải nằm trong ngân sách poll. Đối với non-blocking retry, cần theo dõi tuổi record và backlog trên từng retry topic.

## 14. Idempotency khi retry

Retry có thể làm một nghiệp vụ được thực hiện nhiều lần. Điều này đặc biệt nguy hiểm nếu listener thực hiện side effect như trừ tiền, tạo đơn, gửi email hoặc ghi database.

Một consumer idempotent có thể lưu event ID đã xử lý trong cùng database transaction với thay đổi nghiệp vụ:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Quy trình:

1. Nhận event và lấy event ID ổn định.
2. Bắt đầu database transaction.
3. Ghi event ID vào bảng processed_events với unique constraint.
4. Nếu ID đã tồn tại, không áp dụng side effect lần nữa.
5. Nếu ghi ID thành công, cập nhật dữ liệu nghiệp vụ.
6. Commit database transaction.
7. Chỉ sau khi xử lý thành công, để container commit offset theo AckMode.

Việc kiểm tra event ID và cập nhật nghiệp vụ phải cùng database transaction. Nếu chỉ kiểm tra trước rồi ghi sau, hai consumer/replay có thể cùng vượt qua bước kiểm tra.

Producer idempotence bảo vệ retry protocol của producer; consumer idempotency bảo vệ nghiệp vụ khi record được giao hoặc phát lại nhiều lần. Hai cơ chế bổ sung cho nhau.

## 15. Quan sát và cảnh báo exception classification

Theo dõi tổng số lỗi là chưa đủ. Cần phân biệt transient retry đang phục hồi với permanent exception đang tích tụ ở DLT.

Các tín hiệu hữu ích:

| Metric/tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Exception count theo class/root cause | Loại lỗi nào đang tăng? |
| Retry attempt rate | Consumer có phải retry thường xuyên không? |
| Retry success rate | Bao nhiêu lỗi transient phục hồi sau retry? |
| Retry duration | Record mất bao lâu trước khi thành công? |
| DLT publish rate | Bao nhiêu record đã được phục hồi sang DLT? |
| DLT lag/oldest record age | Lỗi permanent có đang tích tụ không? |
| Consumer lag theo partition | Partition nào bị chặn bởi record lỗi? |
| Listener processing latency | Dependency hoặc logic nào làm xử lý chậm? |
| Rebalance count | Retry có làm consumer mất nhịp poll không? |
| Recovery publish failure | DLT/recoverer có đang thất bại không? |

Log nên bao gồm exception class, root cause, topic, partition, offset, event ID, retry count và correlation ID. Không log toàn bộ payload nếu payload có dữ liệu nhạy cảm.

Đặt alert riêng cho:

- Tỷ lệ transient exception tăng kéo dài.
- Permanent exception vượt ngưỡng theo topic.
- DLT oldest record age vượt SLO.
- Retry success rate giảm.
- Recovery/DLT publishing thất bại.
- Consumer lag tăng cùng với retry hoặc rebalance.

## 16. Runbook phân loại và xử lý

Khi listener phát sinh exception, thực hiện theo trình tự:

### Bước 1: Thu thập nguyên nhân gốc

- Lấy exception class và root cause.
- Ghi nhận topic, partition, offset và event ID.
- Kiểm tra exception có bị wrapper bởi listener, framework hoặc client library không.

### Bước 2: Xác định điều kiện có thể thay đổi

- Broker, database hoặc HTTP dependency có đang phục hồi không?
- Có Retry-After hoặc mã lỗi chỉ định thời gian chờ không?
- Payload/schema có hợp lệ không?
- Credential, ACL và cấu hình có đúng không?
- Business state có thể thay đổi để thao tác trở nên hợp lệ không?

### Bước 3: Chọn classification

- Transient: retry với backoff và giới hạn.
- Permanent: phục hồi sang DLT hoặc quy trình từ chối/sửa dữ liệu.
- Unknown/ambiguous: dùng chính sách thận trọng, tránh lặp side effect; lưu đủ thông tin để điều tra.

### Bước 4: Kiểm tra delivery semantics

- Offset có chỉ được commit sau khi xử lý/recovery thành công không?
- Record có thể được replay không?
- Side effect có idempotent không?
- Nếu transactional, output và offset có nằm trong cùng transaction không?

### Bước 5: Xác nhận phục hồi

Theo dõi retry thành công, committed offset, consumer lag, DLT backlog và dependency health. Sau khi sửa nguyên nhân permanent, replay record theo quy trình có kiểm soát và giữ nguyên event ID để chống duplicate.

## 17. Các lỗi thiết kế thường gặp

| Cách làm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Retry mọi exception vô hạn | Poison record làm kẹt partition và lag tăng | Phân loại retryable/non-retryable và đặt retry budget |
| Coi mọi timeout là transient | Lỗi cấu hình hoặc endpoint sai bị retry liên tục | Kiểm tra root cause, dependency và trạng thái kết quả |
| Coi mọi 4xx là permanent | Bỏ lỡ trường hợp 429 có thể retry hoặc lỗi phụ thuộc thứ tự | Phân loại theo status/error code và hợp đồng API |
| Retry lỗi schema/deserialization không giới hạn | Cùng byte payload tiếp tục lỗi | Dùng ErrorHandlingDeserializer và DLT phù hợp |
| Dùng DLT nhưng không giám sát | Record lỗi tích tụ mà không ai xử lý | Theo dõi DLT lag, oldest age và quy trình replay |
| Retry blocking quá lâu | Consumer không poll đúng hạn và rebalance | Tính backoff vào poll budget hoặc dùng retry topic |
| Nuốt exception rồi trả về bình thường | Container có thể commit offset dù nghiệp vụ chưa hoàn tất | Để lỗi đi tới error handler hoặc đánh dấu rollback phù hợp |
| Replay DLT không có idempotency | Side effect được thực hiện lặp | Dùng event ID và consumer idempotency |
| Phân loại chỉ theo exception wrapper | Nhầm transient thành permanent hoặc ngược lại | Unwrap root cause và chuyển thành domain exception rõ ràng |

## 18. Checklist thiết kế exception classification

Trước khi triển khai retry/recovery, hãy xác định:

1. Exception gốc là gì và nó phát sinh ở bước nào của consumer lifecycle?
2. Nếu retry ngay với cùng record và cùng trạng thái, thao tác có khả năng thành công không?
3. Lỗi có thể tự hết hay cần sửa dữ liệu, schema, cấu hình, quyền hoặc business state?
4. Kafka client đã có retry nội bộ cho lỗi đó chưa?
5. Spring Kafka error handler có phân loại exception đúng không?
6. Retry count, backoff và tổng thời gian có phù hợp với max.poll.interval.ms không?
7. Khi hết retry, record được gửi DLT hay xử lý bằng recovery nào?
8. Nếu DLT publish thất bại, offset gốc có được giữ lại không?
9. Side effect có idempotent khi record được replay không?
10. Dashboard có phân biệt retry transient, permanent exception, DLT và recovery failure không?

Transient exception cần cơ hội phục hồi với backoff và giới hạn rõ ràng. Permanent exception cần được lưu lại, giải thích và đưa vào quy trình sửa hoặc từ chối. Khi Spring Kafka phân loại đúng lỗi, consumer có thể tiếp tục tiến triển qua record lỗi, giảm retry vô ích và giữ khả năng replay mà không làm side effect bị lặp.
