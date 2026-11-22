# KafkaTemplate, CompletableFuture và xử lý kết quả gửi

Trong Spring Kafka, KafkaTemplate là API thường dùng để gửi record mà không phải tự quản lý KafkaProducer. Lệnh gửi trả về ngay một CompletableFuture để ứng dụng tiếp tục xử lý công việc khác; khi producer nhận được kết quả từ broker, Future hoàn tất với SendResult hoặc lỗi. Cách dùng này giúp service không phải chặn thread chỉ để chờ mỗi lần gửi, đồng thời vẫn có thể kiểm tra metadata, ghi nhận lỗi và phối hợp kết quả gửi với nghiệp vụ.

Tuy nhiên, gửi bất đồng bộ không có nghĩa là bỏ qua kết quả. Một service cần xác định rõ khi nào record được xem là gửi thành công, xử lý exception ở cả thời điểm gọi send và lúc Future hoàn tất, và phân biệt timeout chờ ở ứng dụng với timeout giao nhận do Kafka producer quản lý.

## 1. KafkaTemplate nằm ở đâu trong Spring Kafka?

KafkaTemplate là abstraction gửi message của Spring Kafka. Nó sử dụng ProducerFactory để tạo và quản lý Kafka producer, áp dụng serializer, transaction và các cấu hình producer đã khai báo. Ứng dụng thường inject KafkaTemplate vào service rồi tái sử dụng bean đó.

Luồng gửi cơ bản:

1. Service tạo ProducerRecord hoặc gọi một overload của KafkaTemplate.send().
2. KafkaTemplate lấy producer từ ProducerFactory và gửi record.
3. Kafka producer serialize key/value, lấy metadata nếu cần, đưa record vào accumulator và gửi Produce request.
4. Broker xử lý record rồi trả acknowledgement theo cấu hình acks.
5. Callback của producer hoàn tất CompletableFuture.
6. Ứng dụng nhận SendResult hoặc exception và thực hiện bước tiếp theo.

~~~mermaid
sequenceDiagram
    participant S as Application service
    participant T as KafkaTemplate
    participant P as KafkaProducer
    participant B as Kafka broker

    S->>T: send(topic, key, value)
    T->>P: producer.send(record, callback)
    P-->>T: Return CompletableFuture
    T-->>S: Return CompletableFuture
    P->>B: Produce request
    B-->>P: Acknowledgement
    P-->>T: Complete callback
    T-->>S: Complete SendResult / exception
~~~

Trong phần lớn trường hợp, ứng dụng không cần tự tạo hoặc đóng KafkaProducer. ProducerFactory và Spring ApplicationContext quản lý vòng đời producer. Không gọi close() trên producer nội bộ lấy từ KafkaTemplate trong một service nghiệp vụ.

## 2. KafkaTemplate.send() trả về gì?

Trong Spring Kafka 3.x, các phương thức send() trả về CompletableFuture<SendResult<K,V>>. Trước Spring Kafka 3.0, API thường trả về ListenableFuture; khi nâng cấp từ 2.x lên 3.x, cần chuyển callback theo CompletableFuture.

Một số overload thường dùng:

~~~java
// Gửi value, không chỉ định key.
kafkaTemplate.send("orders", orderEvent);

// Gửi key và value.
kafkaTemplate.send("orders", orderId, orderEvent);

// Chỉ định partition.
kafkaTemplate.send("orders", 2, orderId, orderEvent);

// Chỉ định partition và timestamp.
kafkaTemplate.send("orders", 2, timestamp, orderId, orderEvent);

// Tự tạo ProducerRecord để kiểm soát headers và các thuộc tính khác.
ProducerRecord<String, OrderEvent> record =
        new ProducerRecord<>("orders", orderId, orderEvent);
kafkaTemplate.send(record);
~~~

Chọn overload theo nhu cầu:

| Cách gửi | Khi phù hợp |
|---|---|
| Topic + value | Không cần key rõ ràng; partitioner quyết định partition |
| Topic + key + value | Muốn các record cùng key đi theo partition tương ứng để giữ ordering theo key |
| Topic + partition + key + value | Cần chỉ định partition theo logic đã thiết kế |
| ProducerRecord | Cần timestamp, headers, partition hoặc kiểm soát đầy đủ record |
| Message<?> | Tích hợp với Spring Messaging và mapping header/payload |

Chỉ định partition thủ công làm ứng dụng chịu trách nhiệm nhiều hơn về phân phối tải và ordering. Không gán partition cố định nếu chưa hiểu tác động tới throughput, số partition và khả năng mở rộng.

## 3. SendResult và RecordMetadata

Khi Future hoàn tất thành công, kết quả có kiểu SendResult<K,V>. Nó chứa ProducerRecord đã gửi và RecordMetadata broker trả về.

Các thông tin thường cần:

| Metadata | Ý nghĩa |
|---|---|
| topic() | Topic nhận record |
| partition() | Partition broker đã ghi record |
| offset() | Offset của record trong partition |
| timestamp() | Timestamp được broker/client ghi nhận theo cấu hình topic |
| serializedKeySize() | Kích thước key sau serialize |
| serializedValueSize() | Kích thước value sau serialize |

Ví dụ đọc metadata:

~~~java
kafkaTemplate.send("orders", orderId, event)
        .whenComplete((result, error) -> {
            if (error != null) {
                log.error("Send order event failed, orderId={}", orderId, error);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                    "Order event sent: topic={}, partition={}, offset={}, timestamp={}",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset(),
                    metadata.timestamp());
        });
~~~

Offset cho biết vị trí record trong một partition, không phải số thứ tự toàn cục của topic. Hai record ở hai partition có thể có cùng offset. Nếu cần trace một event, nên ghi cả topic, partition, offset và event ID.

Timestamp cần được diễn giải theo cấu hình topic. Với message timestamp type là CreateTime, metadata thường phản ánh timestamp do producer gửi; với LogAppendTime, broker thay bằng thời điểm append. Không dùng timestamp này như thời điểm nghiệp vụ nếu contract không định nghĩa rõ nguồn thời gian.

Future hoàn tất thành công có nghĩa producer nhận acknowledgement theo cấu hình acks. Nó không có nghĩa consumer downstream đã xử lý record hoặc database của consumer đã commit nghiệp vụ.

## 4. Xử lý kết quả với whenComplete()

whenComplete() chạy một action khi Future thành công hoặc thất bại. Nó phù hợp để ghi log, metric hoặc phát tín hiệu quan sát mà không thay đổi kết quả chính.

~~~java
CompletableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send("orders", orderId, event);

future.whenComplete((result, error) -> {
    if (error != null) {
        log.error("Kafka send failed for eventId={}", event.eventId(), error);
    } else {
        RecordMetadata metadata = result.getRecordMetadata();
        log.debug(
                "Kafka send acknowledged: eventId={}, partition={}, offset={}",
                event.eventId(), metadata.partition(), metadata.offset());
    }
});
~~~

whenComplete() trả về một stage mới. Nếu callback ném exception, stage được trả về có thể hoàn tất exceptional; vì vậy callback quan sát nên ngắn và không ném lỗi ngoài ý muốn. Nếu cần biến đổi kết quả, dùng thenApply(); nếu cần chuyển lỗi thành kết quả dự phòng, cân nhắc exceptionally() hoặc handle().

Không nên dùng callback để thực hiện công việc nặng như gọi nhiều HTTP API, truy vấn database chậm hoặc xử lý một batch lớn. Callback thường được thực thi trên thread hoàn tất send của producer. Một callback block có thể làm chậm việc xử lý callback khác.

## 5. thenApply(), thenAccept(), handle() và exceptionally()

CompletableFuture cung cấp nhiều cách nối tiếp công việc. Hãy chọn theo việc cần quan sát, biến đổi hay phục hồi kết quả.

| Method | Chạy khi nào | Mục đích |
|---|---|---|
| whenComplete() | Thành công hoặc thất bại | Quan sát kết quả, thường dùng log/metric |
| thenApply() | Thành công | Biến đổi SendResult thành giá trị khác |
| thenAccept() | Thành công | Tiêu thụ kết quả, không trả giá trị |
| thenCompose() | Thành công | Nối một thao tác bất đồng bộ khác trả về CompletionStage |
| exceptionally() | Khi stage trước thất bại | Chuyển lỗi thành giá trị dự phòng hoặc lỗi khác |
| handle() | Thành công hoặc thất bại | Xử lý cả hai nhánh và tạo kết quả mới |

### thenApply() để biến đổi metadata

~~~java
CompletableFuture<String> location =
        kafkaTemplate.send("orders", orderId, event)
                .thenApply(result -> {
                    RecordMetadata metadata = result.getRecordMetadata();
                    return metadata.topic() + "-"
                            + metadata.partition() + "-"
                            + metadata.offset();
                });
~~~

### exceptionally() để phục hồi có kiểm soát

~~~java
CompletableFuture<SendResult<String, OrderEvent>> recovered =
        kafkaTemplate.send("orders", orderId, event)
                .exceptionally(error -> {
                    log.error("Send failed; eventId={}", event.eventId(), error);
                    return null;
                });
~~~

Ví dụ trên chỉ minh họa cách phục hồi Future; trả về null không nên được xem là gửi thành công. Trong ứng dụng thật, hãy trả về một kiểu kết quả thể hiện rõ SUCCESS/FAILED hoặc ném lại exception để tầng gọi biết việc gửi thất bại.

### handle() để tạo kết quả thống nhất

~~~java
CompletableFuture<PublishOutcome> outcome =
        kafkaTemplate.send("orders", orderId, event)
                .handle((result, error) -> {
                    if (error != null) {
                        return PublishOutcome.failed(event.eventId(), error);
                    }

                    RecordMetadata metadata = result.getRecordMetadata();
                    return PublishOutcome.sent(
                            event.eventId(),
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset());
                });
~~~

handle() hữu ích khi service muốn chuyển cả thành công và thất bại thành một mô hình kết quả thống nhất. Cần giữ thông tin lỗi gốc để log, retry hoặc đưa vào quy trình phục hồi.

## 6. whenComplete() và whenCompleteAsync()

Các method không có hậu tố Async thường chạy action trên thread hoàn tất stage trước đó hoặc ngay trên thread đăng ký nếu stage đã hoàn tất. Với callback của Kafka send, hãy giả định callback có thể chạy trên thread producer và giữ nó ngắn.

Khi cần thực hiện tác vụ tốn thời gian, dùng whenCompleteAsync() với executor riêng:

~~~java
@Configuration
public class AsyncConfiguration {
    @Bean(destroyMethod = "shutdown")
    public ExecutorService kafkaResultExecutor() {
        return Executors.newFixedThreadPool(4);
    }
}
~~~

~~~java
future.whenCompleteAsync((result, error) -> {
    if (error != null) {
        publishFailureMetric(event.eventId(), error);
    } else {
        persistPublishAudit(event.eventId(), result.getRecordMetadata());
    }
}, kafkaResultExecutor);
~~~

Executor cần có giới hạn thread và queue phù hợp. Nếu queue đầy, ứng dụng phải có chính sách backpressure hoặc từ chối công việc; không tạo thread vô hạn. Khi shutdown, executor phải được dừng theo lifecycle và dành đủ thời gian cho task cần hoàn tất.

Không dùng chung một executor nhỏ cho callback cần giải phóng producer và tác vụ có thể block lâu. Nếu mọi thread đều bị chiếm bởi I/O chậm, callback mới có thể bị xếp hàng và gây tích tụ.

## 7. Không block thread bằng get() hoặc join() nếu không cần

CompletableFuture có thể được chờ đồng bộ:

~~~java
SendResult<String, OrderEvent> result = future.get();
SendResult<String, OrderEvent> result2 = future.join();
~~~

Hai cách này block thread cho đến khi Future hoàn tất:

- get() ném InterruptedException và ExecutionException; overload có timeout còn ném TimeoutException.
- join() ném CompletionException khi stage thất bại và không có overload timeout trực tiếp.

Trong web request thread hoặc listener thread, gọi get()/join() cho mọi lần gửi có thể làm giảm concurrency, tăng latency và giữ thread trong lúc broker chậm. Ưu tiên nối tiếp bằng whenComplete(), thenApply() hoặc trả CompletableFuture lên tầng gọi nếu framework hỗ trợ.

Blocking có thể chấp nhận trong batch job nhỏ, command-line tool hoặc một ranh giới nghiệp vụ thực sự cần chờ acknowledgement trước khi tiếp tục. Khi dùng, phải đặt timeout và xử lý interruption đúng cách.

~~~java
try {
    SendResult<String, OrderEvent> result =
            kafkaTemplate.send("orders", orderId, event)
                    .get(10, TimeUnit.SECONDS);

    log.info("Sent at offset={}", result.getRecordMetadata().offset());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted while waiting for Kafka send", e);
} catch (ExecutionException e) {
    throw new KafkaPublishException("Kafka send failed", e.getCause());
} catch (TimeoutException e) {
    // Hết thời gian chờ của thread này; chưa đủ căn cứ kết luận record không được ghi.
    throw new KafkaPublishOutcomeUnknownException(event.eventId(), e);
}
~~~

## 8. Phân biệt các loại timeout

Có nhiều timeout ở những lớp khác nhau. Nhầm chúng có thể dẫn tới retry sai và duplicate event.

| Timeout | Lớp | Ý nghĩa |
|---|---|---|
| max.block.ms | Kafka producer API | Giới hạn thời gian một số thao tác gọi send chờ metadata hoặc buffer; send() có thể block trước khi trả Future |
| request.timeout.ms | Kafka protocol/client | Giới hạn thời gian chờ phản hồi cho một request |
| delivery.timeout.ms | Kafka producer | Tổng thời gian producer cho phép giao một record, gồm batching, request và retry |
| Future.get(timeout) | Thread ứng dụng | Chỉ giới hạn thời gian thread gọi get() chờ kết quả |
| Timeout HTTP/web request | Application boundary | Giới hạn thời gian client hoặc gateway chờ request của ứng dụng |

Nếu get(timeout) ném TimeoutException, nó không hủy Kafka send và không chứng minh broker chưa ghi record. Future gốc vẫn có thể hoàn tất sau đó. Không gửi lại một event mới ngay lập tức chỉ vì thread chờ hết thời gian.

CompletableFuture.orTimeout() có thể hoàn tất Future bằng TimeoutException sau thời gian chỉ định, nhưng nó không hủy request Produce đang chạy ở Kafka client. Nếu cần giới hạn thời gian chờ ở tầng gọi, hãy tách timeout của waiter khỏi Future gốc và tiếp tục quan sát kết quả gửi thực tế.

Khi producer hết delivery.timeout.ms và Future hoàn tất lỗi, ứng dụng biết producer không xác nhận giao record trong delivery budget. Với lỗi mạng/timeout, kết quả phía broker có thể không rõ ràng trong một số cửa sổ lỗi. Dùng event ID ổn định, idempotent producer và dedup ở consumer để bảo vệ việc retry ở cấp ứng dụng.

## 9. Phân biệt lỗi đồng bộ và lỗi bất đồng bộ

Không phải mọi lỗi gửi đều xuất hiện trong whenComplete().

**Lỗi đồng bộ** có thể xảy ra ngay trong lời gọi send(), trước khi Future được trả về. Ví dụ cấu hình template/producer không hợp lệ, producer đã đóng, hoặc lỗi phát sinh ngay khi chuẩn bị/serialize record.

**Lỗi bất đồng bộ** xảy ra trong quá trình gửi sau khi lời gọi đã trả Future, chẳng hạn broker unavailable, authorization failure, record quá lớn, timeout hoặc lỗi request. Những lỗi này làm Future hoàn tất exceptional.

Vì vậy, nếu muốn bắt cả hai loại lỗi, đặt try/catch quanh lời gọi send() và đăng ký xử lý Future:

~~~java
public CompletableFuture<SendResult<String, OrderEvent>> publish(
        String orderId, OrderEvent event) {
    try {
        CompletableFuture<SendResult<String, OrderEvent>> future =
                kafkaTemplate.send("orders", orderId, event);

        return future.whenComplete((result, error) -> {
            if (error != null) {
                log.error("Asynchronous send failure: eventId={}",
                        event.eventId(), error);
            }
        });
    } catch (RuntimeException synchronousError) {
        log.error("Synchronous send failure: eventId={}",
                event.eventId(), synchronousError);
        return CompletableFuture.failedFuture(synchronousError);
    }
}
~~~

CompletableFuture.failedFuture() có từ Java 9. Với Java 8, tạo một CompletableFuture mới rồi gọi completeExceptionally(). Việc trả Future thất bại giúp caller dùng một cách xử lý thống nhất, nhưng vẫn cần phân biệt log/metric nguồn lỗi nếu muốn chẩn đoán.

Khi xử lý lỗi từ stage phụ thuộc, exception có thể được bọc trong CompletionException hoặc ExecutionException. Nếu cần phân loại lỗi Kafka cụ thể, hãy lần theo getCause() đến nguyên nhân gốc trước khi quyết định retry; không phân loại chỉ dựa vào lớp wrapper.

## 10. Phân loại lỗi và quyết định retry

Không nên retry mọi lỗi giống nhau. Producer Kafka đã có retry nội bộ cho lỗi retriable theo cấu hình; ứng dụng chỉ nên retry ở tầng nghiệp vụ khi đã hiểu delivery outcome và giới hạn retry.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi cấu hình/serialization | Serializer sai, payload không hợp lệ | Sửa contract/config; không retry nguyên trạng vô hạn |
| Authorization | Không có quyền ghi topic | Sửa ACL/credential; retry dồn dập không giúp ích |
| Record quá lớn | RecordTooLargeException | Giảm payload hoặc điều chỉnh giới hạn có kiểm soát |
| Broker tạm unavailable | NotEnoughReplicas, network interruption | Producer có thể retry nội bộ; quan sát Future và delivery timeout |
| Lỗi ứng dụng đồng bộ | Template chưa sẵn sàng hoặc producer lifecycle sai | Sửa lifecycle/cấu hình; không coi là broker retry |
| Timeout không rõ kết quả | Response bị mất hoặc hết thời gian chờ | Không tạo event mới; dùng event ID ổn định và dedup |

Producer idempotence bảo vệ retry Produce request do Kafka client thực hiện trong phạm vi producer protocol. Nó không deduplicate hai lần gọi send() riêng biệt từ ứng dụng với cùng payload, đặc biệt sau khi process restart hoặc một producer instance mới được tạo. Nếu ứng dụng retry một nghiệp vụ, cần giữ event ID/command ID ổn định và thiết kế consumer idempotent.

## 11. Cấu hình Producer trong Spring Boot

Một cấu hình minh họa cho producer gửi JSON:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - broker-1:9092
      - broker-2:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        linger.ms: 5
~~~

Tên property và khả năng bind cần được kiểm tra theo Spring Boot/Spring Kafka version của dự án. Với Schema Registry hoặc serializer chuyên biệt, thay serializer và cấu hình tương ứng; JSON serializer không tự thay thế một data contract có schema governance.

Một số cấu hình quan trọng:

| Property | Vai trò |
|---|---|
| acks | Điều kiện broker acknowledgement; all chờ ISR theo semantics Kafka |
| enable.idempotence | Giúp producer xử lý retry mà không tạo duplicate do retry protocol trong phạm vi hỗ trợ |
| delivery.timeout.ms | Tổng deadline giao record ở producer |
| request.timeout.ms | Deadline cho một request broker |
| linger.ms | Thời gian gom batch trước khi gửi khi batch chưa đầy |
| batch.size | Kích thước batch mục tiêu theo partition |
| max.block.ms | Giới hạn chờ metadata/buffer trong một số thao tác đồng bộ của producer |

Không đặt timeout tùy ý mà không xem latency, throughput, replication và SLA. delivery.timeout.ms phải tương thích với request.timeout.ms và linger.ms theo yêu cầu của Kafka client version.

## 12. Một service gửi event có xử lý kết quả rõ ràng

Ví dụ service dưới đây trả Future cho tầng gọi, ghi nhận metadata khi thành công và giữ lỗi để tầng gọi quyết định retry hoặc báo thất bại:

~~~java
@Service
public class OrderEventPublisher {
    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<PublishReceipt> publish(OrderEvent event) {
        try {
            return kafkaTemplate.send("orders", event.orderId(), event)
                    .thenApply(result -> {
                        RecordMetadata metadata = result.getRecordMetadata();
                        log.info(
                                "Published eventId={} topic={} partition={} offset={}",
                                event.eventId(),
                                metadata.topic(),
                                metadata.partition(),
                                metadata.offset());

                        return new PublishReceipt(
                                event.eventId(),
                                metadata.topic(),
                                metadata.partition(),
                                metadata.offset());
                    })
                    .whenComplete((receipt, error) -> {
                        if (error != null) {
                            log.error("Publish failed for eventId={}",
                                    event.eventId(), error);
                        }
                    });
        } catch (RuntimeException e) {
            log.error("Could not start publish for eventId={}", event.eventId(), e);
            return CompletableFuture.failedFuture(e);
        }
    }
}
~~~

Ví dụ giả định OrderEvent có orderId() và eventId(), còn PublishReceipt là DTO do ứng dụng định nghĩa. Trong dự án Java 8, thay failedFuture() bằng cách tạo Future và completeExceptionally().

Tầng gọi có thể nối tiếp mà không block:

~~~java
publisher.publish(event)
        .thenAccept(receipt -> metrics.markPublished(receipt.eventId()))
        .exceptionally(error -> {
            metrics.markPublishFailed(event.eventId());
            return null;
        });
~~~

Nếu service chỉ cần ghi metric, callback nên ngắn. Nếu cần ghi audit vào database, hãy xác định rõ semantics khi database write thất bại sau khi Kafka đã ack; việc ghi audit không nên làm ứng dụng phát lại event như thể Kafka chưa nhận record nếu điều đó tạo duplicate nghiệp vụ.

## 13. Không xem Future success là hoàn tất nghiệp vụ đầu-cuối

Future thành công xác nhận producer nhận acknowledgement theo cấu hình Kafka. Nó không chứng minh:

- Consumer group đã nhận record.
- Consumer đã deserialize và xử lý thành công.
- Database hoặc HTTP side effect downstream đã commit.
- Event đã được xử lý đúng thứ tự nghiệp vụ.
- Một workflow nhiều dịch vụ đã hoàn tất.

Nếu API HTTP trả thành công sau khi Kafka ack, không có transaction mặc định bao trùm cả hai. Nếu yêu cầu nghiệp vụ là chỉ trả thành công sau khi hệ thống downstream xử lý, cần thiết kế acknowledgement event, request/reply hoặc workflow status riêng; đừng diễn giải RecordMetadata như kết quả nghiệp vụ cuối cùng.

Với nghiệp vụ cần không mất event giữa database và Kafka, cân nhắc transactional outbox. Với consumer cần chống duplicate khi replay, dùng inbox/idempotency key. KafkaTemplate và CompletableFuture chỉ quản lý kết quả gửi ở phía producer.

## 14. Ordering, batching và flush

KafkaTemplate sử dụng producer batching và accumulator của KafkaProducer. Gửi bất đồng bộ giúp producer gom nhiều record theo partition, cải thiện throughput. Gọi flush() sau từng send() thường phá batching và làm tăng số request nhỏ.

Ordering được bảo đảm trong phạm vi một partition theo thứ tự record được broker append. Nếu cần ordering theo orderId, dùng orderId làm key và bảo đảm partitioning strategy ổn định. Không suy ra ordering toàn cục từ thứ tự Future hoàn tất: callback của các partition khác nhau có thể hoàn tất theo thứ tự khác nhau.

Chỉ gọi flush() khi có ranh giới cần chờ các send đã được đưa vào producer hoàn tất, ví dụ trước khi kết thúc một batch job. Trong service dài hạn, để ProducerFactory quản lý producer và batching; khi shutdown, Spring lifecycle đóng producer theo cấu hình.

## 15. Observability cho kết quả gửi

Để điều tra lỗi gửi, nên theo dõi:

| Metric/log | Mục đích |
|---|---|
| Send success/failure count | Tỷ lệ gửi thành công và lỗi |
| Send latency | Thời gian từ lúc gọi send tới lúc Future hoàn tất |
| Timeout và retriable error rate | Phân biệt broker/network issue với lỗi dữ liệu |
| Topic/partition/offset | Truy vết vị trí record đã được ack |
| Event ID/correlation ID | Đối chiếu producer với consumer và hệ thống ngoài |
| Buffer pool wait / producer metrics | Phát hiện producer bị backpressure |
| Record size | Phát hiện payload quá lớn hoặc tăng bất thường |

Không log toàn bộ payload nếu có PII, token hoặc dữ liệu thanh toán. Dùng event ID và correlation ID để trace; metadata Kafka đủ để xác định vị trí record mà không cần ghi nội dung nhạy cảm.

## 16. Những lỗi thường gặp

- **Bỏ qua Future:** lỗi bất đồng bộ không được quan sát và event có thể không được broker xác nhận.
- **Chỉ bắt exception quanh callback:** lỗi đồng bộ ngay lúc gọi send() có thể thoát ra trước khi Future được trả về.
- **Gọi get() trong mọi request:** thread web bị block, giảm throughput và tăng tail latency.
- **Retry ngay khi get(timeout) hết hạn:** Future gốc có thể vẫn hoàn tất; request thứ hai có thể tạo duplicate application-level send.
- **Cho rằng Future success nghĩa là consumer xử lý xong:** metadata chỉ phản ánh acknowledgement của producer.
- **Callback làm việc nặng:** có thể block thread hoàn tất send và làm chậm callback khác.
- **Dùng exceptionally() trả null rồi báo thành công:** che giấu lỗi gửi và làm mất khả năng retry/alert.
- **Gọi flush sau mỗi record:** làm giảm batching và throughput.
- **Đóng producer nội bộ của KafkaTemplate:** phá vòng đời producer do ProducerFactory quản lý.
- **Nhầm producer idempotence với business deduplication:** hai lần gọi send() từ ứng dụng vẫn có thể tạo hai record riêng biệt.

## 17. Checklist triển khai

- [ ] Dùng KafkaTemplate được Spring quản lý và tái sử dụng.
- [ ] Chọn overload send() phù hợp với key, partition, timestamp và headers.
- [ ] Quan sát CompletableFuture; không bỏ qua kết quả gửi.
- [ ] Bắt cả lỗi đồng bộ quanh send() và lỗi bất đồng bộ trong Future.
- [ ] Đọc RecordMetadata để trace topic, partition, offset và timestamp.
- [ ] Giữ callback ngắn; dùng whenCompleteAsync() với bounded executor cho tác vụ nặng.
- [ ] Tránh get()/join() trên request thread nếu không thực sự cần chờ.
- [ ] Phân biệt max.block.ms, request.timeout.ms, delivery.timeout.ms và timeout của Future waiter.
- [ ] Không coi TimeoutException từ get(timeout) là bằng chứng record chưa được ghi.
- [ ] Retry có phân loại, backoff và event ID ổn định; không tạo key mới cho cùng nghiệp vụ.
- [ ] Cấu hình acks, idempotence, batch và timeout theo SLA.
- [ ] Không đóng producer nội bộ; để ProducerFactory/Spring quản lý lifecycle.
- [ ] Theo dõi send latency, failure rate, retry, producer buffer và record size.
- [ ] Kiểm thử broker unavailable, serialization error, timeout và shutdown.

KafkaTemplate cung cấp API gửi phù hợp với ứng dụng Spring; CompletableFuture cho phép xử lý kết quả mà không phải block thread. Khi kết hợp đúng callback, metadata, error handling và timeout semantics, service có thể biết record nào đã được broker xác nhận và phản ứng phù hợp khi gửi lỗi. Hãy nhớ rằng Future success là acknowledgement ở phía producer; các cam kết nghiệp vụ sau Kafka cần được thiết kế và theo dõi riêng.
