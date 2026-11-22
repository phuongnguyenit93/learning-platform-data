# Log delivery attempt

Trong Spring Kafka Reliability Operations, **log delivery attempt** là cách ghi nhận **record Kafka đang được giao cho listener ở lần thử xử lý thứ mấy**. Thông tin này giúp phân biệt lần xử lý đầu tiên với những lần giao lại do retry, hỗ trợ chẩn đoán một record liên tục thất bại, đo tác động của backoff, giải thích vì sao consumer lag tăng và truy vết đường đi tới Dead Letter Topic (DLT).

Một dòng log chỉ có nội dung "Failed to process record" thường không đủ cho production. Operator cần biết **record nào**, **consumer group nào**, **topic/partition/offset nào**, **attempt thứ mấy**, **vì sao retry**, **còn retry không**, và **kết quả cuối cùng là thành công, recovery sang DLT hay lỗi hạ tầng**.

Spring Kafka có cơ chế **delivery attempt header** và các callback trong error handling để lấy attempt count. Tuy nhiên, **attempt count không phải một bộ đếm toàn cục, vĩnh viễn cho mọi lần xử lý của cùng event**. Giá trị có thể được tính trong phạm vi một error handler/container, thay đổi khi consumer restart, rebalance, đổi retry topic, hoặc operator replay dữ liệu. Để điều tra xuyên suốt, cần kết hợp attempt với định danh Kafka record, event ID, trace ID và kết quả xử lý.

Bài học này tập trung vào logging và chẩn đoán, không biến log delivery attempt thành cơ chế retry. **Retry policy quyết định có giao lại hay không; logging chỉ giúp quan sát quyết định và hậu quả đó.**

## 1. Delivery attempt nghĩa là gì?

Giả sử listener nhận event:

~~~text
topic: orders.created
partition: 2
offset: 105
key: order-1001
~~~

Lần đầu listener được gọi, một dependency bị timeout. Spring Kafka error handler quyết định retry và giao lại record. Nếu retry hai lần:

~~~text
Delivery 1:
  orders.created/P2@105
  -> listener -> timeout

Backoff 1 giây

Delivery 2:
  orders.created/P2@105
  -> listener -> timeout

Backoff 1 giây

Delivery 3:
  orders.created/P2@105
  -> listener -> success
~~~

Nếu attempt count bắt đầu từ 1, ba lần listener nhận cùng record lần lượt có attempt **1, 2 và 3**.

Điều này khác ba khái niệm dễ bị nhầm:

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Delivery attempt** | Lần thứ mấy record được giao cho listener trong một ngữ cảnh retry |
| **Retry count** | Số lần thử lại sau lần xử lý đầu tiên; thường bằng attempt trừ 1 trong một chuỗi liên tục |
| **Backoff interval** | Thời gian chờ trước lần retry kế tiếp |
| **Committed offset** | Vị trí tiếp theo mà consumer group lưu để đọc khi phục hồi |
| **Event ID** | Định danh nghiệp vụ của event, có thể tồn tại xuyên nhiều topic hoặc lần publish |

Một record có delivery attempt = 3 không có nghĩa chắc chắn cùng business operation mới chỉ chạy ba lần trong toàn hệ thống. Event ấy có thể từng được replay, copy sang topic khác hoặc xử lý bởi consumer group khác.

## 2. Vì sao phải log attempt?

Khi gặp sự cố:

~~~text
ERROR payment-service failed to process PaymentRequested
~~~

Operator không biết đó là lần thử đầu tiên, lỗi tạm thời hay poison message đã thất bại hàng chục lần.

Một log có cấu trúc hữu ích hơn:

~~~text
event=kafka_record_processing_failed
listener=payment-requested-listener
group=payment-service
topic=payments.requested
partition=1
offset=482
delivery_attempt=3
retry_policy=blocking
error_category=downstream_timeout
retryable=true
record_event_id=evt-482
~~~

Thông tin attempt giúp trả lời:

1. Record có bị xử lý lại không?
2. Lỗi có tự phục hồi ở attempt tiếp theo không?
3. Backoff có đang làm consumer chậm tiến độ không?
4. Một record có đang chiếm partition trong thời gian dài không?
5. Khi nào lỗi chuyển sang DLT?
6. Có nhiều records cùng thất bại một lần hay một record thất bại lặp đi lặp lại?
7. Incident đến từ dữ liệu lỗi, dependency tạm thời hay lỗi cấu hình?

Đây là lý do attempt nên xuất hiện trong **structured logs và trace context**, nhưng không nên trở thành một tag metric có số giá trị không giới hạn.

## 3. Delivery attempt được tính ở tầng nào?

Trong listener container, lỗi từ listener được đưa tới error handling. Với mô hình **blocking retry**, CommonErrorHandler như **DefaultErrorHandler** có thể quản lý số lần giao record và quyết định retry hoặc recovery.

~~~text
KafkaConsumer.poll()
      |
      v
Listener container
      |
      +-- delivery attempt context
      |
      v
@KafkaListener
      |
      +-- thành công -> tiến trình commit theo AckMode
      |
      +-- ném exception
                  |
                  v
           DefaultErrorHandler
                  |
                  +-- retry với BackOff
                  |
                  +-- hết retry -> recoverer / DLT
~~~

Spring Kafka hỗ trợ cơ chế **DeliveryAttemptAware** ở các error handler/after-rollback processor tương ứng, để container có thể gắn attempt vào record.

Quan trọng:

- Kafka broker **không tự thêm KafkaHeaders.DELIVERY_ATTEMPT** cho mọi message.
- Attempt trong cơ chế blocking retry thường do **Spring Kafka container/error handler** xác định.
- Nếu error handler không hỗ trợ delivery attempt, cấu hình không bật header hoặc ứng dụng không chạy theo path phù hợp, header có thể vắng mặt.
- Cách tính attempt có thể khác giữa blocking retry, non-blocking retry topics, batch processing và custom handler.

Không viết code mặc định mọi Kafka record đều luôn có header attempt.

## 4. KafkaHeaders.DELIVERY_ATTEMPT

Spring Kafka có hằng **KafkaHeaders.DELIVERY_ATTEMPT** dùng để truy cập header biểu diễn delivery attempt trong những cấu hình hỗ trợ.

~~~java
KafkaHeaders.DELIVERY_ATTEMPT
~~~

Trong ngữ cảnh raw Kafka ConsumerRecord, header Kafka là **byte[]**. Đối với delivery attempt do Spring Kafka container thêm theo cơ chế tương ứng, dạng raw thường là số nguyên 4 byte theo quy ước của framework.

Trong ngữ cảnh Spring Messaging và @KafkaListener parameter binding, framework có thể chuyển đổi header thành **Integer** để truyền vào method listener.

Hai góc nhìn cần phân biệt:

~~~text
ConsumerRecord.headers():
  Kafka Header -> byte[]

@Header(KafkaHeaders.DELIVERY_ATTEMPT):
  Spring Messaging conversion -> Integer
~~~

Không tự ép header byte[] sang String UTF-8 rồi parse bằng Integer.parseInt(). Với raw header 4 byte, cách đó sẽ cho kết quả sai.

Giá trị attempt trong tài liệu thường được tính từ **1** cho lần delivery đầu tiên. Tuy nhiên, khi header thiếu hoặc dùng một custom error handler, nên biểu diễn **unknown** thay vì tự khẳng định một lịch sử retry không được quan sát.

## 5. Bật delivery attempt header trên container

Với một listener container factory:

~~~java
@Configuration
public class KafkaListenerLoggingConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            orderListenerFactory(
                    ConsumerFactory<String, OrderEvent> consumerFactory,
                    DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);

        // Yêu cầu container đưa delivery attempt vào record header
        // khi error handler hỗ trợ cơ chế này.
        factory.getContainerProperties()
                .setDeliveryAttemptHeader(true);

        return factory;
    }
}
~~~

Đây là ví dụ theo API Spring Kafka hỗ trợ **setDeliveryAttemptHeader**. Cần kiểm tra đúng phiên bản dependency hiện tại, vì API, hành vi mặc định và phạm vi áp dụng đã thay đổi qua các release.

Điều kiện quan trọng:

1. Factory này phải là factory **thực sự** được @KafkaListener sử dụng.
2. Error handler đang gắn với factory phải hỗ trợ cơ chế delivery attempt.
3. Không giả định chỉ bật property thì mọi record từ mọi listener đều có header.
4. Với batch listener hoặc đường xử lý lỗi khác, cần xác nhận mức hỗ trợ của phiên bản.
5. Nếu có nhiều listener factories, cấu hình từng factory đúng chủ đích thay vì chỉ một factory không được dùng.

Một ứng dụng có thể dùng Spring Boot auto-configuration. Khi đó vẫn cần xác minh đúng listener container đang được cấu hình, không chỉ kiểm tra bean có tồn tại.

## 6. Tạo DefaultErrorHandler với retry hữu hạn

Một ví dụ blocking retry dùng BackOff:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    // 1 giây giữa các lần thử lại, tối đa hai lần retry.
    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Trong ví dụ này, với một lỗi đủ điều kiện retry và không bị thay đổi bởi exception classification:

~~~text
Attempt 1 -> failure
  wait 1 giây
Attempt 2 -> failure
  wait 1 giây
Attempt 3 -> failure
  recoverer / DLT
~~~

**FixedBackOff(1000, 2) có hai lần retry sau lần đầu**, không phải tổng cộng hai lần delivery.

Các điểm cần xét khi triển khai thật:

- KafkaTemplate của DLT cần serializer phù hợp với key/value thực tế.
- DLT topic, partition, permissions và producer acknowledgements phải hợp lệ.
- Một số exceptions có thể được phân loại non-retryable và recovery ngay.
- Recoverer có thể thất bại; không tự coi record đã được xử lý thành công chỉ vì đã gọi recoverer.
- Nếu error handler có chính sách reset state, attempt count có thể thay đổi khi exception type thay đổi.

Ví dụ không đặt toàn bộ reliability vào việc log attempt; cần kiểm thử recovery và commit offset.

## 7. Lấy attempt từ @KafkaListener parameter

Với listener method có Spring header binding:

~~~java
@KafkaListener(
        id = "orders-created-listener",
        topics = "orders.created",
        groupId = "orders-service",
        containerFactory = "orderListenerFactory")
public void listen(
        ConsumerRecord<String, OrderEvent> record,
        @Header(
            name = KafkaHeaders.DELIVERY_ATTEMPT,
            required = false
        ) Integer deliveryAttempt) {

    String attemptText =
            deliveryAttempt == null
                    ? "unknown"
                    : deliveryAttempt.toString();

    log.info(
            "Kafka record received; topic={}, partition={}, " +
            "offset={}, deliveryAttempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            attemptText);

    orderService.process(record.value());
}
~~~

Đặt **required = false** giúp listener không thất bại chỉ vì header vắng mặt trong cấu hình không hỗ trợ hoặc chưa bật delivery attempt.

Đối với một số converter/container paths, @Header có thể được chuyển sang Integer tự động; cần kiểm thử listener method với phiên bản Spring Kafka và kiểu message thực tế. Nếu muốn tránh phụ thuộc vào conversion, có thể đọc raw ConsumerRecord headers và giải mã theo kiểu byte[].

Không dùng **deliveryAttempt == null ? 1 : deliveryAttempt** trong logging audit quan trọng mà không giải thích. Header không có nghĩa là **không quan sát được attempt**, chứ không tự chứng minh đây là lần đầu trong toàn hệ thống.

## 8. Đọc raw delivery attempt header

Khi listener nhận ConsumerRecord, có thể đọc header trực tiếp:

~~~java
import java.nio.ByteBuffer;
import java.util.OptionalInt;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.support.KafkaHeaders;

public final class DeliveryAttemptHeaders {

    private DeliveryAttemptHeaders() {
    }

    public static OptionalInt readAttempt(
            ConsumerRecord<?, ?> record) {

        Header header = record.headers()
                .lastHeader(KafkaHeaders.DELIVERY_ATTEMPT);

        if (header == null
                || header.value() == null
                || header.value().length != Integer.BYTES) {
            return OptionalInt.empty();
        }

        int attempt = ByteBuffer.wrap(header.value()).getInt();

        return attempt > 0
                ? OptionalInt.of(attempt)
                : OptionalInt.empty();
    }
}
~~~

Ví dụ sử dụng **byte[4]** cho raw delivery attempt header mà Spring Kafka tạo theo cơ chế thường gặp. Nếu ứng dụng tự tạo headers khác định dạng, cần chuẩn hóa format; đừng áp dụng hàm này cho mọi loại header retry.

Tại sao dùng **lastHeader**?

Kafka Headers cho phép nhiều header có cùng key. Với một record được forward/copy qua nhiều topic hoặc thư viện khác nhau, có thể xuất hiện header trùng tên. Việc chọn header cuối giúp tránh vô tình đọc một giá trị cũ hơn, nhưng **không phải bằng chứng mọi hệ thống đều thống nhất định dạng**.

Nếu header thiếu hoặc malformed, trả về OptionalInt.empty(), ghi nhận unknown và tiếp tục xử lý theo policy nghiệp vụ. Không nên làm consumer lỗi chỉ vì logging không giải mã được attempt.

## 9. Log như thế nào khi header không tồn tại?

Ba tình huống cần phân biệt:

| Tình huống | Giá trị quan sát | Cách ghi log |
|---|---|---|
| Header tồn tại, giá trị hợp lệ | 1, 2, 3... | delivery_attempt là số nguyên |
| Header không tồn tại | Không biết | delivery_attempt=unknown |
| Header sai định dạng | Không hợp lệ | delivery_attempt=unknown và counter/log kỹ thuật có giới hạn |

Ví dụ:

~~~text
event=kafka_record_received
topic=orders.created
partition=2
offset=105
delivery_attempt=unknown
delivery_attempt_source=not_available
~~~

Không nên ghi:

~~~text
delivery_attempt=0
~~~

rồi khiến dashboard hiểu đó là attempt thứ 0, vì Kafka delivery attempt theo cách đếm thông dụng bắt đầu từ 1.

Đồng thời, không nên đưa nguyên byte[] lỗi vào metric tag. Nếu cần chẩn đoán header malformed, log độ dài byte array hoặc một mã lỗi giới hạn, tránh dump payload nhạy cảm.

## 10. Ghi log ngay đầu listener

Một log đầu listener hữu ích:

~~~java
@KafkaListener(
        id = "orders-created-listener",
        topics = "orders.created",
        containerFactory = "orderListenerFactory")
public void handle(ConsumerRecord<String, OrderEvent> record) {
    OptionalInt attempt = DeliveryAttemptHeaders.readAttempt(record);

    log.debug(
            "Kafka delivery started: topic={}, partition={}, " +
            "offset={}, attempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            attempt.isPresent() ? attempt.getAsInt() : "unknown");

    orderService.process(record.value());
}
~~~

Tuy nhiên, **log INFO cho mọi record ở throughput cao có thể tạo chi phí rất lớn**. Nếu hệ thống xử lý hàng trăm nghìn records/giây, log mỗi delivery có thể làm tăng CPU, I/O, ingest cost và khó tìm logs quan trọng khi incident.

Một chính sách thực tế:

- **DEBUG** cho thông tin mỗi delivery, bật có giới hạn khi điều tra.
- **WARN** khi một attempt thất bại nhưng vẫn sẽ retry.
- **ERROR** khi recovery cuối cùng thất bại hoặc lỗi hạ tầng nghiêm trọng.
- **INFO** cho những lifecycle transitions hoặc recovery thành công quan trọng, không nhất thiết cho từng record ở lưu lượng cao.

Cần thống nhất logging policy giữa listener, error handler và recoverer để tránh **ghi cùng lỗi ba lần** với stack trace y hệt.

## 11. Dùng RetryListener để log lỗi theo attempt

Thay vì chỉ log attempt ở đầu listener, Spring Kafka **DefaultErrorHandler** có thể đăng ký **RetryListener** để quan sát lần xử lý thất bại và recovery.

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    var handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));

    handler.setRetryListeners(new RetryListener() {

        @Override
        public void failedDelivery(
                ConsumerRecord<?, ?> record,
                Exception exception,
                int deliveryAttempt) {

            log.warn(
                    "Kafka delivery failed: topic={}, partition={}, " +
                    "offset={}, attempt={}, errorType={}",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    deliveryAttempt,
                    exception.getClass().getSimpleName());
        }

        @Override
        public void recovered(
                ConsumerRecord<?, ?> record,
                Exception exception) {

            log.info(
                    "Kafka record recovered: topic={}, partition={}, offset={}",
                    record.topic(),
                    record.partition(),
                    record.offset());
        }
    });

    return handler;
}
~~~

Các RetryListener overloads và callback signatures phụ thuộc phiên bản Spring Kafka; ví dụ trình bày record-oriented RetryListener được hỗ trợ trong các release tương ứng. Batch retry có callbacks riêng ở các phiên bản hỗ trợ.

**RetryListener.failedDelivery** rất phù hợp để log attempt lúc failure vì error handler có ngữ cảnh retry mà một business listener thông thường có thể không biết. Nhưng cần phân biệt **callback báo đã thất bại** với **quyết định chắc chắn sẽ retry**: attempt cuối cùng cũng có thể đi qua failedDelivery trước khi recoverer được gọi.

## 12. Timeline minh họa RetryListener

Giả sử backoff 1 giây, hai retries và recoverer DLT:

~~~text
t=00.000s   listener attempt 1
            -> TimeoutException
            -> RetryListener.failedDelivery(attempt=1)

t=01.000s   listener attempt 2
            -> TimeoutException
            -> RetryListener.failedDelivery(attempt=2)

t=02.000s   listener attempt 3
            -> ValidationException
            -> RetryListener.failedDelivery(attempt=3)
            -> policy quyết định recovery

t=02.050s   recoverer xử lý DLT
            -> RetryListener.recovered(...)
~~~

Timeline chỉ minh họa; exception type thay đổi có thể khiến error handler reset trạng thái backoff/attempt tùy cấu hình và phiên bản. Thời gian thực tế còn chịu ảnh hưởng của poll loop, broker, scheduler và listener processing latency.

Một log tốt cần hỗ trợ dựng lại chuỗi:

~~~text
recordId = orders.created/P2@105
  attempt 1 -> timeout
  attempt 2 -> timeout
  attempt 3 -> validation
  recovery -> DLT
~~~

Không chỉ dựa vào deliveryAttempt để ghép logs của các records khác nhau, vì rất nhiều records có attempt=1 hoặc attempt=2.

## 13. Recovery failed khác recovered

Trong error handler, cần phân biệt ba kết quả:

1. Listener thất bại ở một attempt.
2. Recoverer xử lý record thành công theo semantics của recoverer.
3. Recoverer thất bại và record có thể tiếp tục được xử lý lại.

Một số phiên bản Spring Kafka có RetryListener callback **recoveryFailed(...)** bên cạnh **recovered(...)**. Đây là điểm hữu ích để ghi log:

~~~text
event=kafka_recovery_failed
topic=orders.created
partition=2
offset=105
attempt=3
recovery_target=orders.created.DLT
error_category=dlt_publish
~~~

**Không coi việc recoverer được gọi là bằng chứng DLT publish đã được Kafka broker chấp nhận và offset đã commit.** Kết quả còn phụ thuộc cấu hình DeadLetterPublishingRecoverer, producer acknowledgements, verify send result, transaction/recovery boundary và cách container xử lý lỗi.

Khi log recovery outcome, nên ghi trạng thái theo khả năng xác nhận:

- recovery_started
- recovery_succeeded
- recovery_failed
- commit_pending
- commit_failed_or_unknown

Không ghi dlt_published_successfully ngay từ đầu method recoverer nếu kết quả publish chưa được xác nhận.

## 14. Khi nào delivery attempt bị reset?

Một người vận hành có thể nhìn thấy:

~~~text
12:00:00 attempt=1
12:00:01 attempt=2
12:00:02 attempt=3

12:01:00 consumer restart

12:01:05 attempt=1
~~~

Đây **không nhất thiết là lỗi**. Attempt count trong blocking retry thường được theo dõi bởi container/error handler trong bộ nhớ. Khi process restart, consumer group rebalance hoặc error handler state được reset, record chưa commit có thể được giao lại với attempt=1 trong một chuỗi mới.

Các yếu tố làm attempt không liên tục:

- Process hoặc pod restart.
- Partition bị revoke rồi assign cho consumer khác.
- Error handler reset retry state.
- Record được publish lại vào topic khác.
- Retry topic tạo bước xử lý mới.
- Operator replay từ committed offset hoặc seek lùi.
- Custom listener/recoverer thay đổi headers.

**Attempt count không phải durable global retry counter.**

Nếu nghiệp vụ cần giới hạn tổng số lần xử lý xuyên restart, phải dùng một state store bền vững, một retry orchestration có metadata rõ hoặc cơ chế giới hạn khác. Chỉ log KafkaHeaders.DELIVERY_ATTEMPT không đủ.

## 15. Phân biệt attempt trong blocking retry và non-blocking retry

Spring Kafka có hai nhóm retry phổ biến:

### Blocking retry

Record được giao lại qua container/error handler, có thể sau BackOff. Một partition thường bị ảnh hưởng trong thời gian record đang retry, tùy cơ chế seek/retain/pause.

~~~text
orders.created/P2@105
    |
    +-- attempt 1
    +-- attempt 2
    +-- attempt 3
    |
    v
Success hoặc DLT
~~~

### Non-blocking retry topics

Một record thất bại được forward sang topic retry và sẽ được một listener container của retry topology tiêu thụ khi đến thời điểm:

~~~text
orders.created
      |
      +-- lỗi -> orders.created-retry-1000
      |                  |
      |                  +-- lỗi -> orders.created-retry-5000
      |                                      |
      |                                      +-- lỗi -> DLT
      |
      v
original consumer có thể tiếp tục xử lý records khác
~~~

Tên topics và topology là minh họa. Trong retry-topic flow, **record gốc đã được publish lại sang một topic khác**. Topic/partition/offset hiện tại sẽ khác với original topic/partition/offset.

Vì vậy, không mặc định KafkaHeaders.DELIVERY_ATTEMPT của blocking retry phản ánh tổng số lần thử trên mọi retry topics.

## 16. RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS

Trong retry-topic infrastructure, Spring Kafka có metadata riêng cho lần thử lại, trong đó có hằng **RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS** ở những phiên bản hỗ trợ.

~~~java
RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS
~~~

Đây là **khái niệm tách biệt** với KafkaHeaders.DELIVERY_ATTEMPT, và cách header được thêm/đọc qua framework có thể khác nhau theo phiên bản Spring Kafka.

Khi logging một ứng dụng có @RetryableTopic:

1. Xác định attempt trong **blocking retry nội bộ container** hay attempt trong **retry-topic topology**.
2. Không cộng hai con số một cách mù quáng.
3. Không giả định hai headers luôn tồn tại và có cùng binary encoding.
4. Theo dõi current topic và original source metadata.
5. Dùng event ID/correlation ID để ghép các hops.

Ví dụ logging:

~~~text
event=kafka_delivery_failed
current_topic=orders.created-retry-5000
current_partition=1
current_offset=92
retry_topology_stage=retry_5s
blocking_attempt=1
retry_topic_attempt=3
original_topic=orders.created
original_partition=2
original_offset=105
~~~

Các trường là schema log ứng dụng minh họa; giá trị từng attempt chỉ được ghi khi thực sự lấy được từ framework hoặc metadata mà ứng dụng quản lý.

## 17. Original location và current location

Một record di chuyển qua retry topic hoặc DLT có thể có hai vị trí khác nhau:

~~~text
Original location:
  orders.created/P2@105

Current location:
  orders.created-retry-5000/P1@92
~~~

Để chẩn đoán:

- **Current topic/partition/offset** giúp tìm record đang được consumer hiện tại xử lý.
- **Original topic/partition/offset** giúp tìm record ban đầu.
- **Event ID** giúp liên kết nghiệp vụ khi record được copy/republish.
- **Attempt** giúp hiểu số lần giao trong một retry context.

Spring Kafka Dead Letter Publishing Recoverer hỗ trợ original location headers, ví dụ **KafkaHeaders.DLT_ORIGINAL_TOPIC**, **KafkaHeaders.DLT_ORIGINAL_PARTITION**, **KafkaHeaders.DLT_ORIGINAL_OFFSET** trong các luồng DLT tương ứng.

Không mặc định mọi retry topic đều có đầy đủ DLT headers hoặc mọi producer tự thêm original offset. Cần kiểm tra topology thực tế và chỉ log các fields có metadata hỗ trợ.

**Current offset không bao giờ là bằng chứng record đã xử lý bao nhiêu lần.** Mỗi lần republish sang topic khác là một Kafka record mới với offset mới.

## 18. DLT và delivery attempt

DLT thường là nơi lưu record sau khi retry policy quyết định không tiếp tục xử lý trên luồng chính.

~~~text
Original consumer:
  orders.created/P2@105
  attempts 1, 2, 3 -> fail

Recoverer:
  publish sang orders.created.DLT

DLT consumer:
  current DLT offset = 44
~~~

Khi DLT consumer xử lý record, delivery attempt của **DLT consumer** có thể bắt đầu từ 1. Đó là attempt của một consumer/retry context khác, không phải continuation hiển nhiên của attempt=3 từ original consumer.

Vì vậy schema log nên tránh một field mơ hồ như attempt được hiểu toàn hệ thống:

~~~text
delivery_attempt=1
delivery_attempt_scope=dlt_consumer
original_processing_attempts=3   # Chỉ khi metadata đáng tin cậy
~~~

Nếu không lưu được original attempt count bền vững, đừng suy ra từ DLT offset hoặc số Kafka headers.

DLT triage cần thêm:

- Original topic/partition/offset.
- Exception class/category cuối cùng.
- Timestamp recover.
- Schema/version của payload khi phù hợp.
- Correlation ID/event ID đã được kiểm soát bảo mật.
- Kết quả replay và số lần replay thủ công.

## 19. Rebalance có thể tạo delivery trùng

Giả sử Consumer A xử lý offset 105 nhưng chưa commit. Consumer group rebalance và partition chuyển sang Consumer B:

~~~text
Consumer A:
  P2@105 delivered, attempt=1
  ghi database
  chưa commit offset

Rebalance:
  P2 chuyển sang Consumer B

Consumer B:
  đọc lại P2@105
  attempt=1 trong retry state mới
~~~

Hai log đều có attempt=1 nhưng cùng record gốc đã **được giao ít nhất hai lần**.

Đây là lý do cần phân biệt:

1. **Delivery attempt do Spring Kafka ghi nhận trong một retry cycle**.
2. **Redelivery thực tế do consumer restart/rebalance/offset chưa commit**.
3. **Số lần side effect nghiệp vụ đã thực thi**.

Nếu phải biết số lần nghiệp vụ đã chạy xuyên owner changes, hãy lưu event ID và idempotency state ngoài retry state của listener.

Không coi duplicate attempt=1 là bằng chứng event không bị retry.

## 20. Kafka transactions và delivery attempt

Với consumer-initiated Kafka transaction, listener container có thể gộp output Kafka và consumed offset vào cùng transaction.

~~~text
Kafka transaction T1:
  consume P2@105
  delivery attempt 1
  produce output X
  exception -> ABORT

Kafka transaction T2:
  consume lại P2@105
  delivery attempt 2 (trong retry context)
  produce output X
  send offset 106 to transaction
  COMMIT
~~~

Downstream consumer dùng **read_committed** không thấy output X của transaction đã abort.

Nhưng listener có thể đã gọi database/API bên ngoài Kafka trong cả hai attempts. Transaction Kafka không tự rollback những side effects đó.

Log nên thể hiện hai chiều:

~~~text
delivery_attempt=2
kafka_transaction_outcome=committed
db_side_effect_status=already_applied
~~~

Không dùng delivery attempt như một quyết định để bỏ qua idempotency. Attempt=1 không bảo đảm event chưa từng được xử lý, attempt=2 không bảo đảm lần trước chưa tạo database state.

Với transactional listener, error handling có thể dùng **DefaultAfterRollbackProcessor** thay vì đường DefaultErrorHandler thông thường; cách cung cấp delivery attempt và callback cần kiểm tra theo version.

## 21. Batch listeners và attempt semantics

Batch listener nhận nhiều ConsumerRecords trong một lần callback:

~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "batchListenerFactory")
public void handleBatch(
        List<ConsumerRecord<String, OrderEvent>> records) {

    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.process(record.value());
    }
}
~~~

Khi một record giữa batch thất bại, framework có thể xử lý lại toàn bộ hoặc một phần batch theo cấu hình và exception type (ví dụ BatchListenerFailedException). **Không tự giả định mỗi record trong batch luôn có header KafkaHeaders.DELIVERY_ATTEMPT giống record listener**.

Trong một số phiên bản Spring Kafka, delivery attempt header gắn với **record listener** và không được hỗ trợ hoặc có semantics khác cho batch listener.

Vì vậy, logging batch nên phân biệt:

- **Batch invocation number** (nếu ứng dụng tự theo dõi).
- **Record offset trong batch**.
- **Index record lỗi** khi xác định được.
- **RetryListener batch callbacks** khi framework hỗ trợ.
- **Consumer group/assignment** tại thời điểm retry.

Nếu không có nguồn đáng tin cậy cho per-record attempt trong batch, ghi unknown, không tạo số giả dựa trên index của record.

## 22. Deserialization failure xảy ra trước business listener

Nếu Kafka key hoặc value deserialize thất bại, business listener có thể **không được gọi**. Vì thế log attempt chỉ bên trong @KafkaListener sẽ không quan sát được lỗi này.

Spring Kafka hỗ trợ **ErrorHandlingDeserializer** để chuyển thông tin lỗi deserialize vào record/header và đưa lỗi tới error handling/recovery thay vì làm poll loop thất bại theo cách khó phục hồi.

~~~text
KafkaConsumer.poll()
       |
       v
Deserializer
       |
       +-- deserialize OK -> business listener
       |
       +-- deserialize error
                   |
                   v
              error handler / recovery
                   |
                   +-- retry
                   +-- DLT
~~~

Trong log chẩn đoán cần:

~~~text
event=kafka_deserialization_failed
topic=orders.created
partition=2
offset=105
delivery_attempt=unknown_or_observed_value
error_category=deserialization
business_listener_invoked=false
~~~

Không lấy raw payload bytes rồi ghi đầy đủ vào logs để "tìm dữ liệu lỗi" nếu payload có PII. DLT có thể lưu raw bytes theo cấu hình phù hợp; logs chỉ cần correlation metadata và lỗi đã redaction.

Khi lỗi xảy ra trước listener, RetryListener hoặc framework error logging thường là điểm quan sát phù hợp hơn business listener log.

## 23. Khi nào nên ghi attempt ở listener, khi nào ở error handler?

| Điểm ghi log | Biết record được giao? | Biết lỗi? | Điểm mạnh |
|---|---|---|---|
| Đầu @KafkaListener | Có | Chưa | Đo delivery start, trace context |
| Catch block trong listener | Có | Có | Business context, phân loại nghiệp vụ |
| RetryListener.failedDelivery | Có | Có | Attempt do error handler cung cấp |
| Recoverer/DLT publishing | Có | Có | Recovery target/outcome |
| ConsumerStoppedEvent | Không gắn 1 record cụ thể | Có lifecycle reason | Phân biệt stop do fencing/auth/no-offset |
| NonResponsiveConsumerEvent | Không chắc gắn 1 record | Có poll liveness context | Chẩn đoán consumer thread bị block |

Một kiến trúc logging tốt thường kết hợp:

1. Listener start log ở DEBUG với correlation context.
2. RetryListener failedDelivery log ở WARN và phân loại lỗi.
3. Recovery success/failure log theo outcome.
4. Consumer lifecycle logs riêng để phân biệt hạ tầng và record failures.

Không nhất thiết ghi exception stack trace ở tất cả các điểm.

## 24. Structured log schema khuyến nghị

Ví dụ JSON log:

~~~json
{
  "event": "kafka_delivery_failed",
  "service": "orders-service",
  "listener": "orders-created-listener",
  "consumer_group": "orders-service",
  "topic": "orders.created",
  "partition": 2,
  "offset": 105,
  "delivery_attempt": 2,
  "delivery_attempt_scope": "blocking_retry",
  "event_id": "evt-1001",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "error_category": "downstream_timeout",
  "error_type": "TimeoutException",
  "retry_decision": "retry_pending",
  "processing_duration_ms": 240,
  "outcome": "failed"
}
~~~

Các field và giá trị là **schema log ứng dụng minh họa**; Spring Kafka không mặc định tự tạo toàn bộ JSON này.

Nhóm thông tin nên chuẩn hóa:

| Nhóm | Fields |
|---|---|
| Nguồn | service, environment, listener, consumer_group |
| Kafka location | topic, partition, offset |
| Correlation | event_id, trace_id, original location khi có |
| Retry | delivery_attempt, scope, retry_decision, retry_policy |
| Error | error_category, error_type, root_cause |
| Outcome | success, failed, recovered, recovery_failed |
| Performance | duration_ms, backoff_ms nếu thực sự biết |

Không đưa vào log một field như **retry_decision=retry_pending** nếu callback thực tế chỉ thông báo delivery failed và chưa chắc policy sẽ retry. Nếu chưa biết quyết định cuối, dùng **retry_decision=unknown** hoặc ghi sau khi decision rõ ràng.

## 25. Không dùng record offset làm business ID

Topic/partition/offset là định vị Kafka record trong một topic-partition:

~~~text
orders.created/P2@105
~~~

Nó hữu ích cho debug và xác định record. Nhưng:

- Một event được republish sang retry topic có offset mới.
- Một event được replay từ DLT sang topic nguồn có offset mới.
- Một message có thể được nhiều consumer groups xử lý riêng.
- Topic có thể bị xóa và tạo lại, làm offset cũ không còn mang ý nghĩa duy nhất trên toàn lịch sử.

Vì vậy, dùng thêm **event ID ổn định** hoặc business idempotency key nếu cần nhận diện nghiệp vụ qua nhiều lần publish.

Một log correlation có thể dùng:

~~~text
event_id=evt-1001
original_location=orders.created/P2@105
current_location=orders.created-retry-5000/P1@92
delivery_attempt=1
~~~

Đây không mâu thuẫn: cùng event ID nhưng Kafka record hiện tại và retry context khác nhau.

## 26. MDC để tự động gắn context cho logs

SLF4J MDC có thể gắn context theo thread, giúp logs của các service methods trong cùng listener invocation có topic/partition/offset/attempt mà không phải truyền thủ công vào mọi log call.

~~~java
@KafkaListener(
        topics = "orders.created",
        containerFactory = "orderListenerFactory")
public void handle(ConsumerRecord<String, OrderEvent> record) {

    String attempt = DeliveryAttemptHeaders.readAttempt(record)
            .isPresent()
            ? Integer.toString(
                    DeliveryAttemptHeaders.readAttempt(record).getAsInt())
            : "unknown";

    try (MDC.MDCCloseable topic =
                 MDC.putCloseable("kafka.topic", record.topic());
         MDC.MDCCloseable partition =
                 MDC.putCloseable("kafka.partition",
                         Integer.toString(record.partition()));
         MDC.MDCCloseable offset =
                 MDC.putCloseable("kafka.offset",
                         Long.toString(record.offset()));
         MDC.MDCCloseable delivery =
                 MDC.putCloseable("kafka.delivery_attempt", attempt)) {

        orderService.process(record.value());
    }
}
~~~

Ví dụ dùng **MDC.putCloseable** để tự dọn các keys sau callback. Có thể tính OptionalInt một lần rồi dùng lại để đơn giản hóa code; đoạn trên tập trung minh họa lifecycle cleanup.

**Dọn MDC trong finally hoặc try-with-resources là bắt buộc về mặt vận hành.** Listener container tái sử dụng consumer thread để xử lý nhiều records. Nếu MDC của offset 105 còn tồn tại khi offset 106 chạy, logs có thể gắn nhầm record.

MDC thường là ThreadLocal: nếu listener tạo asynchronous tasks trên thread khác, context **không tự lan truyền đúng**. Khi cần propagate, dùng cơ chế context propagation của framework với giới hạn và cleanup rõ ràng.

## 27. MDC leak dẫn tới chẩn đoán sai

Một anti-pattern:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(ConsumerRecord<String, OrderEvent> record) {
    MDC.put("kafka.offset", Long.toString(record.offset()));

    orderService.process(record.value());

    // Không MDC.remove/clear -> context có thể rò sang record khác.
}
~~~

Nếu exception xảy ra trước cleanup, hậu quả càng dễ xuất hiện:

~~~text
Record 105:
  MDC kafka.offset=105
  exception -> method thoát

Record 106:
  MDC vẫn kafka.offset=105
  log mới bị ghi nhầm offset 105
~~~

Điều này làm operator tin rằng record 105 được retry nhiều lần, trong khi log thực ra thuộc record 106.

Với logging delivery attempt, **đúng correlation context quan trọng không kém giá trị attempt**. Luôn cleanup các MDC keys do listener đặt. Nếu code nền cũng dùng MDC, tránh gọi MDC.clear() bừa bãi làm mất context của framework; ưu tiên restore/remove đúng những keys thuộc sở hữu của code.

## 28. Cẩn thận với @Async và CompletableFuture

Một listener:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderEvent event) {
    workerPool.execute(() -> orderService.process(event));
}
~~~

có thể trả về trước khi business work hoàn tất. Trong trường hợp đó:

- Delivery attempt phản ánh lần container **gọi listener**, không chắc business worker đã xử lý xong.
- Nếu consumer offset được commit khi listener return, record có thể bị coi là processed trước khi worker hoàn tất.
- Khi retry/rebalance, cùng business event có thể chạy đồng thời trên nhiều workers.
- MDC từ consumer thread không tự động có mặt trong worker thread.

Để an toàn, cần một mô hình async acknowledgment/ownership được Spring Kafka hỗ trợ, theo dõi completion của tasks và idempotency cho external side effects.

Không giải quyết thiếu sót về acknowledgment bằng cách tăng delivery attempt logging. Logs chỉ phơi bày vấn đề, không sửa semantics.

Nếu propagate MDC qua executor, cần capture context, set ở worker và restore/clear sau khi task hoàn tất, tránh rò context giữa thread pool jobs.

## 29. Correlation ID và tracing

Để ghép Kafka delivery với HTTP/database operations, có thể sử dụng trace ID hoặc event correlation ID:

~~~text
Kafka input:
  event_id=evt-1001
  trace_id=abc123

Listener attempt 2:
  trace_id=abc123
  delivery_attempt=2

Downstream HTTP:
  trace_id=abc123

Database operation log:
  trace_id=abc123
~~~

Trong hệ thống tracing, mỗi lần xử lý lại có thể tạo một span mới. Các spans này có thể liên quan qua propagated trace context hoặc span links tùy thiết kế instrumentation.

Không giả định trace ID luôn giống nhau qua DLT/manual replay; một operator có thể tạo một trace mới. Vì vậy cần **event ID ổn định** hoặc explicit correlation link giữa original và replay.

Trường **delivery_attempt** có thể được gắn vào span attribute nếu phù hợp. Nhưng tránh ghi record payload, customer secrets hoặc full exception messages chứa dữ liệu nhạy cảm vào traces.

Một log delivery tốt giúp drill down từ dashboard lỗi sang trace của lần thử cụ thể, thay vì tạo metric riêng cho mỗi trace ID.

## 30. Log level và retry storm

Giả sử một downstream API ngừng hoạt động, 5.000 records cùng retry ba lần. Nếu mỗi attempt log full stack trace ở ERROR:

~~~text
5.000 records
  × 3 failed attempts
= 15.000 error stack traces
~~~

Nếu log pipeline có throughput giới hạn, incident sẽ tạo **logging storm**, làm tăng tài nguyên và khiến logs quan trọng tới chậm.

Một chính sách hợp lý:

| Tình huống | Log level gợi ý | Nội dung |
|---|---|---|
| Delivery bắt đầu | DEBUG | Kafka location, attempt, correlation |
| Attempt thất bại nhưng còn retry | WARN hoặc DEBUG tùy volume | Error category, attempt, backoff context |
| Recovery sang DLT thành công | INFO/WARN tùy policy | Original location, recovery target, category |
| Recovery thất bại | ERROR | Error class, cause, Kafka location |
| Producer fencing/transaction failure nghiêm trọng | ERROR | Container/transaction context |
| Consumer rebalance bình thường | INFO/DEBUG | Assignment lifecycle |

Không có một log level bắt buộc cho mọi hệ thống. Mục tiêu là đủ thông tin để điều tra nhưng không ghi cùng một exception stack ở nhiều lớp.

Có thể dùng sampling hoặc rate limiting **cho log thành công hoặc lỗi lặp**, nhưng vẫn giữ durable DLT/audit state cho các trường hợp nghiệp vụ bắt buộc.

## 31. Số lần thất bại nên đo bằng metrics thế nào?

Delivery attempt có thể xuất hiện trong log và một metric. Tuy nhiên không nên dùng một tag động như raw attempt count nếu giá trị không giới hạn.

Ví dụ counter:

~~~java
registry.counter(
        "app.kafka.delivery.failures",
        "listener", "orders-created",
        "outcome", "retryable",
        "error_category", "downstream_timeout")
    .increment();
~~~

Nếu muốn phân tích attempt distribution, có thể dùng **bounded buckets**:

~~~text
attempt_bucket = first
attempt_bucket = second
attempt_bucket = third_to_fifth
attempt_bucket = more_than_five
attempt_bucket = unknown
~~~

Hoặc dùng một DistributionSummary/Timer phù hợp, tùy monitoring stack và metric semantics.

**Không dùng event_id, record key, original offset, exception message hoặc trace_id làm metric labels**. Đó là dữ liệu high cardinality và có thể làm Prometheus/Micrometer quá tải.

Metrics giải đáp xu hướng aggregate; logs/traces giúp tìm từng record.

## 32. Ví dụ map attempt thành bucket có giới hạn

~~~java
public final class AttemptBuckets {

    private AttemptBuckets() {
    }

    public static String from(Integer attempt) {
        if (attempt == null || attempt <= 0) {
            return "unknown";
        }
        if (attempt == 1) {
            return "first";
        }
        if (attempt == 2) {
            return "second";
        }
        if (attempt <= 5) {
            return "third_to_fifth";
        }
        return "more_than_five";
    }
}
~~~

Ví dụ metric:

~~~java
registry.counter(
        "app.kafka.delivery.attempts",
        "listener", "orders-created",
        "attempt_bucket", AttemptBuckets.from(deliveryAttempt),
        "outcome", "failure")
    .increment();
~~~

Ở đây số kết hợp labels được giới hạn. Nếu hệ thống có một error handler reset attempt khi rebalance, metric vẫn có thể cho thấy **distribution của observed attempts**, nhưng không phải tổng số business executions.

Cần đặt tên metric và mô tả rõ là đếm **delivery failures per observed attempt bucket**, không phải đếm số unique records.

## 33. Ngân sách log và PII

Delivery logging thường chứa key, headers, payload, error message. Những trường này có thể mang dữ liệu nhạy cảm:

~~~text
record.key() = customer email
record.value() = địa chỉ và thông tin đơn hàng
exception.message = URL có access token
headers = authorization token
~~~

Không nên log:

~~~java
log.error(
        "Failed: record={}, headers={}",
        record,
        record.headers(),
        exception);
~~~

nếu không biết formatter sẽ in ra những gì.

Thiết kế phù hợp:

- Chỉ ghi **topic, partition, offset, attempt**, error category và correlation ID được phép.
- Redact/mask record key nếu key có PII.
- Không ghi nguyên payload chỉ vì debug retry.
- Không in raw exception message nếu nó có thể chứa token/SQL/customer data.
- Giới hạn log length và stack trace sampling.
- Dùng quyền truy cập log/trace phù hợp với dữ liệu nghiệp vụ.

Hash record key không làm nó trở thành một metric tag low-cardinality. Hash có thể giảm khả năng đọc trực tiếp nhưng vẫn giữ số lượng giá trị gần như cũ.

## 34. Idempotency không thể dựa vào attempt=1

Một anti-pattern nguy hiểm:

~~~java
if (deliveryAttempt == 1) {
    paymentClient.charge(payment);
}
~~~

Ý định của code có thể là "chỉ charge lần đầu, retry thì không charge". Nhưng:

1. Consumer restart có thể khiến attempt về 1.
2. Same business event có thể đi sang consumer group khác.
3. Retry topic có retry state khác.
4. Event được manual replay có thể bắt đầu một lần delivery mới.
5. Header có thể thiếu hoặc bị thay đổi.

Vì vậy **attempt không phải idempotency key**.

Một hướng thiết kế tốt hơn:

~~~java
paymentClient.charge(
        payment,
        payment.eventId()); // idempotency key do API hỗ trợ
~~~

Hoặc dùng database unique constraint/processed_event table để chặn side effect lặp. Kafka transaction chỉ bảo vệ output Kafka và consumed offsets thuộc transaction tương ứng; database/API cần tính idempotent riêng.

## 35. Phân biệt retry vì lỗi dữ liệu và vì hạ tầng

Hai records có attempt=3 nhưng nguyên nhân rất khác:

~~~text
Record A:
  ValidationException
  payload sai nghiệp vụ
  attempt=3

Record B:
  TimeoutException
  database connection pool hết
  attempt=3
~~~

Record A có thể nên đi DLT sớm, không retry nhiều. Record B có thể phục hồi sau backoff hoặc circuit breaker.

Delivery log nên có error category:

~~~text
validation
deserialization
downstream_timeout
infrastructure
transaction
authorization
unknown
~~~

Error category phải là danh sách hữu hạn, ổn định qua deployments. Không tạo error category bằng nguyên văn exception message.

Khi phân loại không chính xác, attempt log có thể cho thấy một pattern retry nhưng không giải thích được tại sao policy đang retry một lỗi vốn không thể phục hồi.

## 36. Reset retry state khi exception thay đổi

Spring Kafka error handling có các chính sách về việc reset backoff/retry state khi exception thay đổi, tùy phiên bản và cấu hình (ví dụ **resetStateOnExceptionChange**).

Xét record:

~~~text
Attempt 1 -> TimeoutException
Attempt 2 -> TimeoutException
Attempt 3 -> ValidationException
~~~

Nếu handler reset state khi exception type thay đổi, chuỗi retry kế tiếp có thể bắt đầu một state/backoff mới. Khi đó log delivery attempts có thể không còn một dãy 1,2,3,4... liên tục như operator kỳ vọng.

Điều cần làm:

- Ghi exception category/type ở mỗi failed attempt.
- Ghi retry policy/version/configuration trong tài liệu vận hành.
- Không suy ra số retry còn lại chỉ từ attempt nếu policy có reset.
- Kiểm tra exception classification và recoverer behavior.
- Test tình huống root cause thay đổi giữa các lần retry.

**Attempt count là tín hiệu của error-handler state**, không phải một phép đo đơn giản của tổng số exceptions trong toàn hệ thống.

## 37. RetryListener có thể trùng logs với listener catch

Ví dụ business listener:

~~~java
try {
    orderService.process(record.value());
}
catch (RuntimeException ex) {
    log.error("Process failed", ex);
    throw ex;
}
~~~

Sau đó DefaultErrorHandler cũng:

~~~text
RetryListener.failedDelivery -> log.warn(..., ex)
~~~

Và recoverer:

~~~text
DLT published / recovery -> log.error(..., ex)
~~~

Một attempt có thể tạo 2–3 stack traces giống nhau. Trong incident, số logs tăng theo cấp số nhân với số retries.

Giải pháp:

1. Dùng listener catch chủ yếu để thêm business context hoặc chuyển loại exception.
2. Giao attempt failure logging cho RetryListener như một nơi thống nhất.
3. Chỉ log full stack trace ở error handler/recovery hoặc theo sampling policy.
4. Log recovery outcome riêng, tránh log cùng một failure như lỗi mới.
5. Dùng trace ID/event ID để ghép logs thay vì nhân bản nội dung.

**Một log cho mỗi lần failed delivery** thường dễ điều tra hơn ba logs cùng chỉ về một exception.

## 38. Attempt không nói hết backoff duration

Một record:

~~~text
attempt=3
~~~

không đủ để biết đã chờ bao lâu giữa attempts. Một policy có thể là:

- Fixed backoff 1 giây.
- Exponential backoff.
- Backoff có jitter.
- Retry topic với delay 5 phút.
- Tạm dừng container do downstream overload.

Nếu cần đo latency:

~~~text
failure_time
next_delivery_time
backoff_configured
actual_wait_time
~~~

Đừng ghi **actual_wait_ms** bằng cách lấy trực tiếp giá trị cấu hình nếu worker thread, rebalance hoặc broker scheduling làm thời gian thực khác.

Đối với retry topics, một message có thể đến hạn nhưng consumer chưa xử lý ngay vì partition backlog hoặc container pause. Cần phân biệt **configured retry delay** và **observed retry latency**.

## 39. Correlate attempt qua logs như thế nào?

Một truy vấn điều tra có thể bắt đầu từ:

~~~text
service = orders-service
topic = orders.created
partition = 2
offset = 105
~~~

Sau đó sắp xếp logs theo timestamp:

~~~text
12:00:00.100 attempt=1 outcome=failed error=timeout
12:00:01.200 attempt=2 outcome=failed error=timeout
12:00:02.350 attempt=3 outcome=success
~~~

Nếu có records chuyển sang retry topic, tìm theo **event_id** hoặc original location metadata:

~~~text
12:00:00 original orders.created/P2@105
12:00:01 retry orders.created-retry-1000/P1@92
12:00:06 retry orders.created-retry-5000/P1@115
~~~

Không ghép chỉ theo key khi key không unique hoặc đã được tái sử dụng cho nhiều business events. Nên dùng event ID nếu có.

Khi thấy attempt giảm từ 3 về 1, kiểm tra timestamp của restart, rebalance, retry topology hop hoặc replay trước khi kết luận hệ thống đếm sai.

## 40. Log search queries và dashboard

Tùy log backend, cú pháp truy vấn sẽ khác nhau. Một truy vấn theo ý tưởng:

~~~text
event = kafka_delivery_failed
AND listener = orders-created-listener
AND delivery_attempt >= 3
AND error_category = downstream_timeout
~~~

Dashboard có thể hiển thị:

- Failed deliveries per minute.
- Tỷ lệ records thành công ngay attempt 1.
- Tỷ lệ records cần >= 2 attempts.
- Số unique records tới DLT.
- P95 thời gian từ attempt đầu đến recovered.
- Retry storm theo listener/topic family.
- Producer fencing và consumer rebalance rates.
- Consumer lag, đặc biệt với blocking retry.

Lưu ý khi tính **unique records**: số log failed deliveries không bằng số unique Kafka records. Một record retry 10 lần tạo 10 thất bại nhưng vẫn chỉ là một source record.

Nếu muốn đếm unique event IDs, cần một log query aggregation hoặc state store phù hợp, có cân nhắc chi phí và dữ liệu nhạy cảm. Không tạo một Prometheus time series cho mỗi event ID để lấy unique count.

## 41. Logging và consumer lag

Blocking retry có thể giữ một partition chưa tiến offset vì một record lỗi:

~~~text
P2:
  offset 105 -> retrying
  offset 106 -> waiting
  offset 107 -> waiting

Consumer lag trên P2 tăng.
~~~

Nếu log có:

~~~text
topic=orders.created
partition=2
offset=105
delivery_attempt=8
error_category=timeout
~~~

thì operator có căn cứ để liên kết lag với record đang retry.

Ngược lại, lag tăng mà **không có delivery attempt failure logs** có thể do:

- Consumer thread bị block trước listener.
- Poll/rebalance problem.
- Deserialization failure không đi qua listener.
- Downstream throughput thấp.
- Consumer paused.
- Transaction read_committed chờ open transaction.
- Logging chưa được cấu hình hoặc đã bị sampling/drop.

Không suy luận mọi consumer lag đều do một poison record, và không tăng retries vô hạn chỉ vì muốn tránh DLT.

## 42. Lỗi thường gặp khi dùng RetryListener

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| RetryListener không log gì | Bean handler không được gắn đúng factory | Kiểm tra containerFactory và CommonErrorHandler |
| Attempt header luôn thiếu | Chưa bật deliveryAttemptHeader hoặc handler không hỗ trợ | Kiểm tra ContainerProperties và version |
| Listener log attempt=1 liên tục | Process restart/rebalance hoặc retry state reset | Đối chiếu consumer group/lifecycle logs |
| Attempt tăng khác số lần gọi listener | Retry context khác, exception state reset hoặc batch handling | Kiểm tra error handler semantics |
| DLT consumer thấy attempt=1 | Retry context mới | Log original/current location và scope |
| Log attempt không có ở lỗi deserialize | Listener chưa được gọi | Quan sát ErrorHandlingDeserializer/error handler |
| Header decoding ra số âm hoặc vô lý | Đọc sai bytes/format | Kiểm tra 4-byte int, ByteBuffer và header name |
| Cùng một failure xuất hiện ba lần | Log lặp ở listener, RetryListener và recoverer | Quy định ownership của error logging |
| WARN tăng rất nhanh khi broker lỗi | Retry storm/logging storm | Rate limiting, bounded retries, alert |
| Commit offset thành công dù listener log lỗi | Exception bị nuốt hoặc error handler recover trả bình thường | Kiểm tra exception flow, ack/transaction policy |

Không sửa lỗi logging bằng cách tự thay Kafka consumer position hay commit offsets khi chưa hiểu root cause.

## 43. Khi exception bị nuốt trong listener

Code:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderEvent event) {
    try {
        orderService.process(event);
    }
    catch (RuntimeException ex) {
        log.error("Processing failed", ex);
        // Không throw tiếp.
    }
}
~~~

Nếu listener trả về bình thường, container có thể coi record là đã xử lý theo AckMode/transaction policy. **DefaultErrorHandler không nhất thiết được gọi** và attempt không tăng như kỳ vọng.

Khi cần retry:

~~~java
catch (RuntimeException ex) {
    log.warn("Processing failed; handing exception to container");
    throw ex;
}
~~~

Tuy nhiên, không phải mọi lỗi đều nên retry. Với non-retryable business validation, error handler có thể recover sớm bằng DLT. Quan trọng là **exception được giao đúng policy**, thay vì chỉ log rồi nuốt.

Nếu business logic đã có side effect ngoài Kafka trước khi exception, lần delivery tiếp theo có thể lặp side effect đó; cần idempotency.

## 44. Khi producer send trả Future nhưng listener trả về sớm

KafkaTemplate.send(...) có thể trả CompletableFuture. Một anti-pattern:

~~~java
@KafkaListener(topics = "orders.created")
public void handle(OrderEvent event) {
    kafkaTemplate.send("orders.normalized", transform(event));
    // Không chờ/kiểm tra lỗi send.
}
~~~

Nếu send thất bại sau khi listener return, exception có thể không được container thấy đúng thời điểm. Với transactional Kafka listener, cần bảo đảm send failure/transaction error được xử lý trong transaction boundary phù hợp.

Ví dụ đồng bộ hóa để lỗi xuất hiện trước khi return:

~~~java
kafkaTemplate.send("orders.normalized", transform(event)).join();
~~~

Đây là ví dụ đơn giản, không phải lời khuyên luôn block trên từng send trong pipeline throughput cao. Có thể gom futures rồi chờ có kiểm soát.

**Delivery attempt logging chỉ phản ánh các lần container giao record**, không tự phát hiện một lỗi producer bị bỏ qua hoàn toàn trong asynchronous callback.

## 45. Recovered nhưng chưa chắc business thành công

Khi DefaultErrorHandler chuyển record sang DLT, RetryListener.recovered có thể được gọi theo semantics recovery.

~~~text
Record business processing -> failed
Error handler -> recovered to DLT
~~~

Trong log cần phân biệt:

~~~text
business_outcome=failed
recovery_outcome=success
~~~

Không ghi:

~~~text
business_outcome=success
~~~

chỉ vì record đã được đưa sang DLT và listener container có thể tiếp tục xử lý offsets kế tiếp.

DLT là nơi giữ record để phân tích hoặc replay, không phải bằng chứng business requirement đã được hoàn thành. Nếu operator replay DLT, đó là một workflow mới với attempt context mới.

## 46. Kịch bản log khi consumer restart giữa retries

Timeline:

~~~text
Pod A:
  10:00:00 attempt=1 -> timeout
  10:00:01 attempt=2 -> timeout

Pod A bị kill

Pod B:
  10:00:30 assignment P2
  10:00:31 attempt=1 -> success
~~~

Nếu chỉ nhìn attempt, có thể tưởng record chưa từng lỗi. Khi thêm pod/consumer lifecycle:

~~~text
instance=pod-A consumer_session=A attempt=2
instance=pod-B consumer_session=B attempt=1
~~~

và cùng original location, operator hiểu record đã trải qua nhiều process lifecycles.

**Consumer session ID** ở đây là một trường logging ứng dụng tự định nghĩa hoặc nguồn metadata tương ứng, không phải Kafka header tự sinh. Nếu tạo session ID bằng UUID, đặt trong log/tracing; không làm metric label.

## 47. Kịch bản log với DLT publish thất bại

Timeline:

~~~text
Attempt 1 -> validation failure
Attempt 2 -> validation failure
Recovery -> publish DLT
DLT broker/serializer/ACL error
Recovery -> failed
~~~

Những gì operator cần:

~~~text
source=orders.created/P2@105
attempt=2
error_category=validation
recovery_target=orders.created.DLT
recovery_outcome=failed
recovery_error_category=kafka_publish
~~~

Nếu DLT publish lỗi, source record không nên bị coi là đã recovery thành công khi yêu cầu vận hành là phải lưu được bản ghi lỗi. Thiết kế recoverer và error handler phải xử lý failure theo semantics phiên bản/cấu hình thực tế.

Một log "sent to DLT" ngay trước khi gọi KafkaTemplate.send không đủ để chứng minh đã publish thành công.

## 48. Kịch bản log khi transaction bị fenced

Transactional producer có thể bị **ProducerFencedException**, chẳng hạn do trùng transactional.id giữa active instances hoặc lifecycle issue.

~~~text
consumer processing attempt=1
producer transaction commit -> fenced
container stop reason=FENCED (khi cấu hình)
~~~

Đây là **infrastructure/lifecycle failure**, không phải chắc chắn payload sai.

Log nên gồm:

~~~text
event=kafka_transaction_failed
failure_category=producer_fenced
listener=orders-created
input=orders.created/P2@105
delivery_attempt=1
transaction_outcome=failed_or_unknown
container_action=stop
~~~

Không tự retry vô hạn một ProducerFencedException trên producer đã bị fenced. Cần producer/container lifecycle recovery và xác định nguyên nhân trùng transactional ID hoặc loss of ownership.

Attempt count không nói lên nguyên nhân fencing; phải kết hợp transaction logs và consumer group events.

## 49. Tình huống log từ idle hoặc non-responsive consumer

Một consumer có thể idle vì topic trống hoặc đang chờ dữ liệu. Khi đó **không có delivery mới** để tăng attempt.

Một consumer không poll đúng hạn có thể phát **NonResponsiveConsumerEvent** theo monitoring settings. Nếu listener đang block trong database call, attempt log đầu listener có thể đã được ghi nhưng không có success/failure log cuối.

~~~text
12:00:00 delivery_started attempt=1
12:00:30 non_responsive_poll_warning
12:01:00 db_timeout
12:01:01 delivery_failed attempt=1
~~~

Một schema tốt kết hợp:

- delivery_started
- delivery_failed hoặc delivery_completed
- consumer_non_responsive
- consumer_stopped/rebalance

Đừng tự tăng attempt khi idle event hoặc non-responsive event xuất hiện. Attempt đo **delivery tới listener**, không đo số poll hoặc số lần monitoring phát cảnh báo.

## 50. Test: lần đầu và retry hai lần

Nên kiểm thử với Kafka broker test như **EmbeddedKafka** hoặc **Testcontainers Kafka** để quan sát xử lý thực tế.

### Setup

1. Cấu hình DefaultErrorHandler với FixedBackOff(1000, 2).
2. Bật deliveryAttemptHeader trên listener container.
3. Tạo listener cố ý thất bại hai lần rồi thành công.
4. Thu thập attempts trong một test-safe list/queue.
5. Chờ listener hoàn tất bằng CountDownLatch hoặc điều kiện có timeout.

Kết quả kỳ vọng trong mô hình hỗ trợ record delivery header:

~~~text
Observed attempts:
  [1, 2, 3]

Business listener invoked:
  3 lần

DLT recovery:
  không được gọi vì attempt 3 thành công
~~~

Không dùng sleep cố định rồi coi retry đã hoàn tất. Chờ điều kiện có timeout và kiểm tra record identity để tránh trộn với các records khác.

## 51. Test: exhausted retries tới DLT

1. Listener luôn ném exception được phân loại retryable.
2. BackOff cho số lần retry hữu hạn.
3. Xác nhận failedDelivery callbacks có attempt phù hợp.
4. Xác nhận recoverer được gọi sau khi hết retries.
5. Xác nhận DLT record tồn tại bằng consumer riêng.
6. Xác nhận original location metadata.
7. Xác nhận listener/source group tiến theo recovery commit semantics được cấu hình.

Đặc biệt, dùng consumer DLT với serializer/deserializer phù hợp, và kiểm tra raw payload khi input lỗi deserialize.

Không chỉ assert "RetryListener.recovered được gọi" rồi coi DLT publish đã thành công trong mọi producer/recovery configuration.

## 52. Test: missing attempt header

Một test cần xử lý trường hợp header vắng mặt:

~~~text
Record không có KafkaHeaders.DELIVERY_ATTEMPT
    |
    v
DeliveryAttemptHeaders.readAttempt(...)
    |
    v
OptionalInt.empty()
    |
    v
Log delivery_attempt=unknown
    |
    v
Business listener tiếp tục xử lý
~~~

Nếu logging helper ném NullPointerException vì header không có, chính instrumentation đã trở thành nguyên nhân gây retry.

Test thêm các trường hợp:

- Header thiếu.
- Header dài 0 byte.
- Header chỉ có 2 byte.
- Header có 4 byte nhưng số âm hoặc 0.
- Nhiều headers cùng tên.

Instrumentation cần bền vững với dữ liệu không hợp lệ.

## 53. Test: restart làm attempt quay lại 1

1. Gửi record và cho listener thất bại hai lần.
2. Đóng container/process trước khi source offset commit.
3. Khởi động consumer mới cùng group.
4. Quan sát record được xử lý lại.
5. Xác nhận logging ghi rõ instance/session mới.
6. Không assert attempt phải tiếp tục 3 sau restart.
7. Kiểm tra idempotency của business side effects.

Test này chứng minh **deliveryAttempt không phải durable counter**.

Nếu cần hành vi total-attempt limit xuyên restart, thiết kế một state store riêng và test store đó, không cố kéo dài ý nghĩa của header Spring Kafka ra ngoài phạm vi nó quản lý.

## 54. Test: retry topic và current location

1. Cấu hình @RetryableTopic theo phiên bản hỗ trợ.
2. Gửi một event có event ID cố định.
3. Cố ý làm listener lỗi để forward sang retry topic.
4. Thu thập current topic/partition/offset trên từng hop.
5. Thu thập retry-topic attempt metadata khi framework cung cấp.
6. Nếu có blocking retry bên trong hop, ghi riêng blocking attempt.
7. Xác nhận logs có thể ghép bằng event ID/original location.
8. Xác nhận không tự cộng hoặc diễn giải nhầm hai attempt sources.

Một ví dụ log:

~~~text
event_id=evt-1001
current_topic=orders.created-retry-1000
retry_topic_attempt=2
blocking_attempt=1
~~~

Các giá trị chỉ minh họa; test phải dựa vào actual retry topic names/headers của phiên bản Spring Kafka.

## 55. Test: batch, deserialize và transactional listener

Ba đường xử lý quan trọng cần test riêng:

**Batch listener:** một record trong batch ném lỗi. Xác nhận retry callbacks và cách log batch index; không kỳ vọng per-record header nếu phiên bản không hỗ trợ.

**Deserialization failure:** producer gửi bytes sai schema. Xác nhận business listener có thể không được gọi, error handler/recovery vẫn có logs về record location và lỗi.

**Transactional listener:** listener produce output rồi ném exception. Xác nhận transaction abort, downstream read_committed không thấy output đã abort, retry có log context phù hợp; không commit offset thủ công để "hoàn thành" lỗi.

Các test cần độc lập, tránh dùng chung consumer group làm nhiễu attempt/rebalance state giữa test cases.

## 56. Công thức đối chiếu log count

Giả sử hệ thống xử lý:

~~~text
100 unique source records

80 records:
  success ở attempt 1

15 records:
  success ở attempt 2

5 records:
  fail cả 3 attempts rồi recovery
~~~

Số listener deliveries trong một chuỗi retry không restart:

~~~text
80 × 1
15 × 2
 5 × 3
------
125 delivery invocations
~~~

Số unique source records vẫn là 100, và số recovered records là 5.

Nếu dashboard đếm **listener invocations**, nó có thể hiển thị 125. Nếu dashboard đếm **unique source records**, nó hiển thị 100. Nếu dashboard đếm **DLT recoveries**, nó hiển thị 5.

Không so sánh trực tiếp các counters này mà không hiểu semantics. Đặc biệt, logs bị sampling hoặc dropped có thể khiến số lines nhỏ hơn số attempts thực tế.

## 57. Một quy trình điều tra incident theo delivery attempt

Khi nhận alert "Kafka consumer lag tăng" hoặc "DLT rate tăng":

1. Xác định service, listener và consumer group.
2. Xem lag theo topic-partition để tìm partition bị ảnh hưởng.
3. Tìm failed delivery logs theo current topic/partition/offset.
4. Sắp xếp attempts và exception categories theo thời gian.
5. Kiểm tra log có consumer restart, rebalance hoặc producer fencing không.
6. Xác định blocking retry hay non-blocking retry topics.
7. Nếu record đã chuyển topic, tìm bằng original location hoặc event ID.
8. Kiểm tra DLT publish/recovery outcome, không chỉ recovery request.
9. Đối chiếu database/API side effects khi record có thể được xử lý lại.
10. Quyết định retry, DLT replay, fix schema hoặc xử lý dependency.
11. Sau khắc phục, theo dõi consumer lag, success rate và số records còn trong DLT.
12. Lưu postmortem: retry policy có hợp lý và logs có đủ correlation không.

Không dùng số attempt để tự động quyết định xóa record lỗi. Những records này có thể chứa sự kiện nghiệp vụ quan trọng và cần quy trình recovery kiểm toán được.

## 58. Những hiểu nhầm thường gặp

**Delivery attempt là số lần Kafka broker đã gửi record trong toàn lịch sử.** Không đúng. Thường là attempt trong error-handler/container retry context của Spring Kafka.

**Attempt=1 chứng minh business event chưa từng được xử lý.** Không đúng. Restart, rebalance và replay có thể tạo attempt=1 mới.

**Attempt=3 nghĩa là Kafka đã retry 3 lần.** Không đúng theo cách đếm từ 1: thông thường là một lần đầu và hai lần retry.

**Kafka broker tự đặt KafkaHeaders.DELIVERY_ATTEMPT trên mọi record.** Không đúng. Header liên quan Spring Kafka error-handling configuration.

**Bật setDeliveryAttemptHeader(true) là đủ trong mọi listener.** Không chắc. Handler phải hỗ trợ, container factory phải đúng và batch/path có thể khác.

**Raw header là chuỗi UTF-8 có giá trị "3".** Không đúng cho header attempt 4-byte integer do container thường tạo.

**Header thiếu thì cứ mặc định attempt=1.** Không phù hợp nếu logging cần phân biệt giá trị quan sát và suy đoán.

**RetryListener.failedDelivery luôn có nghĩa record sẽ tiếp tục retry.** Không đúng. Lần thất bại cuối có thể đi thẳng tới recovery.

**RetryTopicHeaders.DEFAULT_HEADER_ATTEMPTS và KafkaHeaders.DELIVERY_ATTEMPT là một.** Không đúng. Chúng thuộc các cơ chế retry khác nhau.

**Record chuyển sang retry topic vẫn có original offset như cũ.** Không đúng. Record mới trên topic đích có current offset mới.

**DLT consumer attempt=1 nghĩa source chỉ fail một lần.** Không đúng. DLT consumer có processing context mới.

**Recovered đồng nghĩa business success.** Không đúng. Record có thể chỉ được lưu DLT để xử lý sau.

**Log attempt ở @KafkaListener sẽ bắt mọi lỗi deserialize.** Không đúng. Lỗi có thể xảy ra trước business listener.

**Kafka transaction ngăn listener bị gọi lại.** Không đúng. Nó bảo vệ Kafka outputs/consumed offsets được commit nguyên tử theo transaction.

**Delivery attempt là idempotency key.** Không đúng. Dùng event ID và idempotent side effects.

**Gắn event ID vào metric label là cách tốt để drill-down.** Không đúng. Event ID có cardinality cao; sử dụng logs/traces.

**Ghi full stack trace ở mọi retry là luôn tốt.** Không đúng. Nó có thể tạo logging storm và tăng chi phí đáng kể.

## 59. Quy tắc triển khai production

Khi xây dựng logging cho Spring Kafka delivery attempts:

1. Xác định rõ retry model: blocking retry, non-blocking retry topic, transactional after-rollback hoặc custom handler.
2. Chỉ bật delivery attempt header trên những listener factories và paths có hỗ trợ.
3. Đọc attempt bằng @Header phù hợp hoặc raw Kafka header có giải mã byte[] đúng định dạng.
4. Ghi **unknown** khi header thiếu hoặc malformed, không tạo attempt giả.
5. Dùng RetryListener hoặc hook error-handling tương ứng để log failedDelivery/recovery outcomes.
6. Phân biệt lần delivery đầu với số lần retry: attempt 3 thường tương đương hai retries trong một chuỗi liên tục.
7. Luôn ghi current topic/partition/offset và listener/group; bổ sung original location khi record đã đi qua retry topic/DLT.
8. Dùng event ID/correlation ID để ghép records qua hops/restarts, không dùng attempt làm khóa.
9. Ghi attempt scope và nguồn dữ liệu để không nhầm blocking với retry-topic attempts.
10. Không log đầy đủ payload, headers nhạy cảm hoặc exception message không được kiểm soát.
11. Dùng MDC với try/finally/closeable, tránh rò context giữa consumer thread và async workers.
12. Không ghi cùng stack trace ở listener, RetryListener và recoverer nhiều lần không cần thiết.
13. Dùng metrics có tag values hữu hạn cho outcome/error category, không tag theo event ID/offset.
14. Theo dõi consumer lag, retry storm, DLT publish outcome và lifecycle events cùng attempt logs.
15. Bảo vệ external side effects bằng idempotency; attempt count không ngăn duplicate processing.
16. Kiểm thử first delivery, multiple retries, exhausted recovery, missing header, restart, rebalance, retry topic, deserialize failure và transaction abort.

**Log delivery attempt** là một công cụ chẩn đoán rất hữu ích khi Spring Kafka phải đối phó với lỗi tạm thời, poison records và sự cố lifecycle. Giá trị của nó đến từ việc **biết attempt đang đo cái gì và trong phạm vi nào**, kết hợp thông tin Kafka location, error category, recovery outcome và correlation ID. Một hệ thống logging tốt có thể chỉ ra record nào đang retry, tại sao retry, kết quả cuối cùng là gì và điều gì đã xảy ra khi consumer restart hoặc rebalance — mà không làm logging pipeline quá tải hoặc biến số lần delivery thành một giả định sai về tính exactly-once của nghiệp vụ.
