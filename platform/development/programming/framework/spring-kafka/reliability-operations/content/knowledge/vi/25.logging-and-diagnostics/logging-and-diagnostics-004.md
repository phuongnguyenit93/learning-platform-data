# Log exception chain

Trong hệ thống Spring Kafka vận hành thật, một lỗi hiếm khi đến logger dưới dạng exception nguyên thủy. Một record không deserialize được có thể xuất hiện trong error handler với wrapper của Spring Kafka; lỗi gọi database có thể được dịch thành `DataAccessException` rồi bọc thêm exception nghiệp vụ; lỗi `KafkaTemplate.send(...)` có thể đến trong `CompletionException` hoặc `ExecutionException`; lỗi khi ghi dead-letter topic (DLT) lại có thể che khuất lỗi xử lý ban đầu. Nếu chỉ log `ex.getMessage()`, người trực sự cố rất dễ nhìn thấy dòng “Listener method failed” hoặc “Execution failed” nhưng không biết gốc rễ là JSON sai định dạng, database timeout, permission denied hay producer bị fenced.

**Log exception chain** là thực hành ghi nhận và phân tích **chuỗi quan hệ nguyên nhân của Throwable** — exception hiện tại, các `cause` lồng nhau, và khi cần các `suppressed exceptions` — kèm ngữ cảnh Kafka đủ để xác định record, giai đoạn xử lý và hành động recovery. Mục tiêu không phải in mọi stack trace ở mọi lần retry; mục tiêu là **giữ nguyên thông tin nguyên nhân, log đúng ranh giới, phân loại lỗi và bảo vệ dữ liệu nhạy cảm**.

Bài học này giải thích cơ chế exception chain trong Java, mẫu SLF4J đúng/sai, những lớp wrapper thường gặp trong Spring Kafka, cách log tại listener và error handler, lỗi deserialize trước listener, asynchronous producer, transaction, retry/DLT, structured logging, tracing, kiểm thử và runbook chẩn đoán production.

## 1. Exception chain là gì?

Java `Throwable` có một quan hệ nguyên nhân được biểu diễn bằng `getCause()`. Exception ở lớp ngoài thường mô tả **ngữ cảnh đang xử lý**, còn exception nằm sâu hơn thường mô tả **lỗi kỹ thuật ban đầu**.

Ví dụ:

~~~text
ListenerExecutionFailedException
  message: "Listener method failed"
    |
    +-- caused by: OrderProcessingException
          message: "Cannot persist order event"
            |
            +-- caused by: DataAccessResourceFailureException
                  message: "Database unavailable"
                    |
                    +-- caused by: SocketTimeoutException
                          message: "Read timed out"
~~~

Trong chuỗi trên:

- **Outer exception** cho biết lỗi xuất hiện ở ranh giới listener.
- **Business exception** cho biết hành động nghiệp vụ thất bại.
- **Data access exception** cho biết tầng database bị ảnh hưởng.
- **Root cause** cho thấy timeout trong giao tiếp network ở tầng sâu.

Nếu chỉ log:

~~~java
log.error("Kafka listener failed: {}", exception.getMessage());
~~~

người vận hành có thể chỉ nhận được “Listener method failed”, mất thông tin nguyên nhân gốc và stack trace.

### 1.1. Một Throwable có gì?

| Thành phần | Cách lấy | Ý nghĩa |
|---|---|---|
| Exception class | `getClass().getName()` | Loại lỗi ở tầng hiện tại |
| Message | `getMessage()` | Mô tả bổ sung, có thể chứa dữ liệu nhạy cảm |
| Cause | `getCause()` | Lỗi đã dẫn đến exception hiện tại |
| Stack trace | `getStackTrace()` | Đường gọi hàm tại nơi throwable được tạo |
| Suppressed | `getSuppressed()` | Lỗi phụ được gắn vào throwable, thường trong cleanup |
| Throwable toàn bộ | Đưa exception cho logger đúng cách | Logger thường in class, message, stack trace, cause và suppressed |

**Cause chain không phải thứ tự lịch sử mọi sự kiện hệ thống**. Nó chỉ biểu diễn quan hệ mà code và framework đã thiết lập qua các exception objects. Nếu một tầng nuốt lỗi hoặc tạo exception mới mà không truyền cause, chuỗi có thể bị đứt.

### 1.2. Root cause có luôn là nguyên nhân quan trọng nhất?

Không nhất thiết. Exception sâu nhất có thể chỉ là `SocketTimeoutException`, còn thông tin quan trọng để quyết định retry/recovery nằm ở lớp ngoài: timeout xảy ra khi ghi bảng thanh toán, khi gọi Schema Registry hay khi publish DLT?

Một incident report tốt thường giữ:

1. **Failure stage**: deserialize, listener, database, Kafka publish, transaction commit, DLT recovery.
2. **Outer exception class**: nơi framework bắt lỗi.
3. **Root cause class**: lỗi kỹ thuật sâu nhất có thể truy được.
4. **Cause chain**: các lớp trung gian quan trọng.
5. **Source record metadata**: topic, partition, offset, group.
6. **Recovery outcome**: sẽ retry, đã đưa DLT, recovery thất bại, hay chưa rõ.

## 2. Ví dụ bọc exception đúng cách trong Java

Một service có thể dịch lỗi kỹ thuật thành lỗi nghiệp vụ có ngữ cảnh hơn:

~~~java
public class OrderProcessingException extends RuntimeException {

    public OrderProcessingException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Tầng nghiệp vụ:

~~~java
public void processOrder(OrderEvent event) {
    try {
        orderRepository.save(toEntity(event));
    }
    catch (DataAccessException ex) {
        throw new OrderProcessingException(
                "Failed to persist order event",
                ex);
    }
}
~~~

`super(message, cause)` giữ đường dẫn từ lỗi nghiệp vụ về lỗi database. Khi Spring Kafka tiếp tục bọc exception ở ranh giới listener, root cause vẫn có khả năng được tìm thấy.

### 2.1. Cách làm đứt exception chain

~~~java
catch (DataAccessException ex) {
    throw new OrderProcessingException(
            "Database failed",
            null); // Sai: làm mất nguyên nhân gốc.
}
~~~

Hoặc:

~~~java
catch (DataAccessException ex) {
    throw new RuntimeException(ex.getMessage());
    // Sai: chỉ giữ message, không giữ cause/stack trace gốc.
}
~~~

Cả hai làm diagnostics khó hơn. Exception message có thể giống nhau ở nhiều root causes, và không thể tái tạo stack trace gốc chỉ từ chuỗi text.

### 2.2. Không nhất thiết bọc exception ở mọi tầng

Nếu mỗi helper method bọc thêm một `RuntimeException("Failed")`, chain có thể dài và khó đọc. Chỉ bọc khi lớp mới bổ sung **ngữ nghĩa, quyền sở hữu hoặc chính sách xử lý rõ ràng**, chẳng hạn phân biệt “order persistence failed” với lỗi network chung.

Một lớp mới nên:

- Có class hoặc message mang ý nghĩa.
- Giữ cause.
- Không đưa raw payload hoặc PII vào message.
- Cho phép error handler phân loại transient/permanent nếu cần.

## 3. SLF4J: log đầy đủ Throwable đúng cách

Với SLF4J, pattern phổ biến là truyền exception ở **tham số cuối** để logger nhận nó như `Throwable` và in stack trace.

~~~java
log.error(
        "Kafka record processing failed: topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset(),
        ex);
~~~

Log statement này có ba placeholders cho metadata và đối số cuối là exception. Logger có thể render stack trace cùng các mục `Caused by` mà không cần tự duyệt chain rồi nối text thủ công.

### 3.1. Những cách log dễ đánh mất thông tin

| Mẫu | Vấn đề |
|---|---|
| `log.error(ex.getMessage());` | Mất exception class, stack trace và cause |
| `log.error("Failed: {}", ex.getMessage());` | Chỉ in message |
| `log.error("Failed: " + ex);` | Có thể chỉ in `toString()` |
| `log.error("Failed {}", record.key());` | Không có throwable |
| `log.error("Failed", ex);` | Đúng để in throwable, nhưng thiếu metadata nguồn |
| `log.error("Failed for offset {}", record.offset(), ex);` | Đúng với một placeholder và Throwable cuối |

Một lời gọi ngắn nhưng hữu ích:

~~~java
log.error("Kafka processing failed", ex);
~~~

Và một lời gọi có ngữ cảnh:

~~~java
log.error(
        "Kafka processing failed: group={}, topic={}, partition={}, offset={}",
        groupId,
        record.topic(),
        record.partition(),
        record.offset(),
        ex);
~~~

### 3.2. Không dùng getStackTrace().toString()

~~~java
log.error("Stack trace: {}", ex.getStackTrace().toString());
~~~

`getStackTrace()` trả về một mảng `StackTraceElement[]`. `toString()` trên mảng không cho stack trace như mong đợi. Nếu cần stack trace, **truyền Throwable trực tiếp** vào logger.

### 3.3. Đừng log cùng Throwable ba lần trong một call stack

Nếu listener log ERROR đầy đủ rồi rethrow, `DefaultErrorHandler` có thể log lỗi tiếp. Khi recoverer gửi DLT cũng log lần nữa, hệ thống có thể tạo hàng chục stack traces cho một record.

Nên thống nhất **nơi log authoritative** cho mỗi failure stage, ví dụ:

- Listener thêm ngữ cảnh khi bọc exception, không nhất thiết log mỗi lần.
- Error handler hoặc retry listener ghi warning theo mức độ và số lần retry.
- Recovery terminal ghi ERROR khi cuối cùng thất bại/đưa DLT.
- Phần quan sát tổng hợp dùng counters, không cần một stack trace cho mọi attempt.

Không xóa hoàn toàn exception log để tránh trùng; chỉ chọn đúng tầng và log level.

## 4. Stack trace, cause chain và suppressed exceptions

Khi logger nhận một Throwable, output Java thông thường có dạng:

~~~text
ERROR Kafka record processing failed topic=orders.events partition=1 offset=420
org.springframework.kafka.listener.ListenerExecutionFailedException:
    Listener method failed
    at ...KafkaMessageListenerContainer...
Caused by: com.example.OrderProcessingException:
    Failed to persist order event
    at ...OrderService...
Caused by: org.springframework.dao.DataAccessResourceFailureException:
    Database unavailable
    at ...Repository...
Caused by: java.net.SocketTimeoutException:
    Read timed out
    at ...SocketInputStream...
~~~

Đây là output minh họa, không phải stack trace từ một hệ thống thực. Logger/layout có thể thêm timestamp, thread, MDC, trace ID và định dạng JSON.

### 4.1. Suppressed exceptions

`Throwable.getSuppressed()` biểu diễn các lỗi phụ, ví dụ một resource không đóng được trong `try-with-resources` khi phần thân đã ném exception:

~~~java
try (Resource resource = openResource()) {
    doWork(); // ném exception chính
} // close() cũng ném exception phụ
~~~

Exception chính thường được giữ làm throwable chính, còn lỗi ở `close()` trở thành **suppressed exception**. Nếu chỉ duyệt `getCause()` và bỏ qua suppressed, có thể bỏ sót tình trạng cleanup hoặc resource leak quan trọng.

### 4.2. Cause chain không chứa mọi lỗi xảy ra song song

Trong workflow bất đồng bộ, nhiều futures có thể thất bại độc lập. `getCause()` của một future không tự chứa tất cả exception từ các futures khác. Nếu cần thống kê nhiều failures, phải quản lý chúng trong state hoặc một aggregate exception có `suppressed`/metadata phù hợp.

Không tự nhồi hàng nghìn exceptions vào suppressed của một Throwable rồi log toàn bộ trong một record: log size có thể vượt hạn mức và làm hệ thống observability quá tải.

## 5. Root cause helper: dùng có kiểm soát

Đôi khi structured log cần một field `rootCauseClass` riêng cho dashboard hoặc alert. Có thể đi qua `getCause()` để tìm throwable sâu nhất:

~~~java
public final class Exceptions {

    private Exceptions() {}

    public static Throwable rootCause(Throwable throwable) {
        if (throwable == null) {
            return null;
        }

        Throwable current = throwable;
        Set<Throwable> seen =
                Collections.newSetFromMap(
                        new IdentityHashMap<Throwable, Boolean>());

        int depth = 0;
        while (current.getCause() != null && depth < 64) {
            if (!seen.add(current)
                    || seen.contains(current.getCause())) {
                break;
            }
            current = current.getCause();
            depth++;
        }
        return current;
    }
}
~~~

Giới hạn độ sâu và theo dõi identity giúp tránh vòng lặp cause bất thường hoặc chain quá dài do code lỗi. Mục đích của helper chỉ là **bổ sung một field phân loại**; không thay thế việc đưa original Throwable vào logger.

### 5.1. Không vội áp dụng policy chỉ theo exception sâu nhất

Ví dụ `SocketTimeoutException` có thể nằm dưới:

- Database query.
- HTTP request tới downstream.
- Schema Registry lookup.
- Kafka producer request.

Chính sách retry của từng stage có thể khác. Root cause class là tín hiệu, không phải classifier duy nhất. Cần xét wrapper, stage, business idempotency và trạng thái transaction.

### 5.2. Root cause message không phải metric tag an toàn

Message có thể chứa hostname, SQL, nội dung input hoặc thông tin khách hàng. Nếu đưa nguyên văn `rootCause.getMessage()` vào Prometheus label, sẽ vừa tạo high cardinality vừa có nguy cơ lộ dữ liệu.

Nên dùng class được chuẩn hóa:

~~~text
failure_stage=database
root_cause_class=SocketTimeoutException
reason=downstream_timeout
~~~

Các field có tập giá trị nhỏ phù hợp cho metrics; chi tiết message đã kiểm soát có thể đặt ở logs/traces.

## 6. Exception ở đâu trong pipeline Spring Kafka?

Hiểu vị trí lỗi giúp biết nơi có thể log exception chain.

~~~text
Kafka broker record bytes
      |
      v
KafkaConsumer.poll()
      |
      +-- key/value deserializer
      |      |
      |      +-- Serialization/Deserialization failure
      |
      v
Spring Kafka listener container
      |
      +-- message converter / adapter
      |      |
      |      +-- conversion failure
      |
      v
@KafkaListener
      |
      +-- business validation
      +-- database access
      +-- HTTP downstream
      +-- KafkaTemplate.send()
      |
      v
Listener normal return / exception
      |
      v
CommonErrorHandler / AfterRollbackProcessor
      |
      +-- retry / seek / recover
      +-- DeadLetterPublishingRecoverer
      |
      v
Offset commit / Kafka transaction commit
~~~

**Không phải exception nào cũng xuất hiện trong thân `@KafkaListener`.** Lỗi deserializer có thể phát sinh trong `KafkaConsumer.poll()` trước khi listener được gọi. Lỗi transaction commit có thể xảy ra sau khi listener đã trả về bình thường. Lỗi DLT producer có thể xuất hiện trong recovery stage.

Vì vậy, thêm `try/catch` quanh mọi listener method không đủ để thu thập toàn bộ lỗi hệ thống.

## 7. Các wrapper thường gặp trong Spring Kafka

Tên loại exception phụ thuộc Spring Kafka, Kafka client và thư viện nghiệp vụ, nhưng những pattern đáng nhận biết gồm:

| Lớp ngoại lệ | Nguồn thường gặp | Điều cần đọc tiếp |
|---|---|---|
| `ListenerExecutionFailedException` | Adapter/container khi gọi listener thất bại | Cause của listener/business method |
| `DeserializationException` của Spring Kafka | Lỗi deserialize key/value được wrapper xử lý | Cause của codec/parser và raw-data metadata |
| `RecordDeserializationException` của Kafka client ở các phiên bản hỗ trợ | KafkaConsumer không deserialize record | Topic-partition, offset và cause |
| `SerializationException` | Serialize/deserialize key/value | Delegate codec, schema, format |
| `MessageConversionException` | Chuyển đổi message giữa Kafka và listener type | Conversion cause, target type |
| `KafkaException` | Lỗi Kafka container/recovery/transaction ở nhiều vị trí | Cause, lifecycle stage |
| `DataAccessException` | Database/JPA/JDBC qua Spring | DB driver exception phía dưới |
| `CompletionException` / `ExecutionException` | Future/callback bất đồng bộ | Cause thực của Kafka send |
| `ProducerFencedException` | Transactional producer bị fenced | Transactional ID, pod collision/lifecycle |
| `TimeoutException` | Network/broker/downstream timeout | Stage và timeout được cấu hình |

**Không nên phân loại mọi exception có chữ “Kafka” là lỗi broker.** Một `ListenerExecutionFailedException` có thể che validation bug của chính ứng dụng.

### 7.1. Lỗi listener thường có wrapper

Ví dụ:

~~~text
ListenerExecutionFailedException
  -> OrderProcessingException
     -> DataIntegrityViolationException
        -> SQLException (duplicate key)
~~~

Nếu root cause là duplicate key của inbox idempotency, nó có thể là tình huống xử lý duplicate hợp lệ hoặc là lỗi dữ liệu cần phân tích, không nhất thiết là sự cố broker Kafka.

### 7.2. Spring Kafka version thay đổi hình dạng chain

Một nâng cấp library có thể thay đổi wrapper class, số lớp bọc hoặc error path. Không viết alert ràng buộc chặt vào chuỗi message “Listener method failed” mà không có kiểm thử tương thích theo version.

Để giữ ổn định dashboard, ứng dụng nên chuẩn hóa `failure_stage` và `reason` từ classification rules có chủ đích, đồng thời vẫn lưu Throwable đầy đủ trong logs chẩn đoán.

## 8. Mẫu @KafkaListener: giữ cause và metadata

Giả sử listener xử lý đơn hàng:

~~~java
@Component
public class OrderEventsListener {

    private final OrderService orderService;

    public OrderEventsListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-worker")
    public void onRecord(
            ConsumerRecord<String, OrderEvent> record) {

        try {
            orderService.processIdempotently(record.value());
        }
        catch (OrderDomainException ex) {
            throw ex; // Giữ chính exception nghiệp vụ.
        }
        catch (RuntimeException ex) {
            throw new OrderProcessingException(
                    "Failed to process Kafka order event",
                    ex);
        }
    }
}
~~~

Listener giữ cause; nó không log stack trace ở mọi retry. Spring Kafka container/error handler sẽ thấy exception được ném và quyết định retry, seek hoặc recovery.

Trong các hệ thống có policy logging tập trung, có thể không cần `try/catch` này nếu wrapper không bổ sung điều gì hữu ích. Một handler đơn giản:

~~~java
@KafkaListener(topics = "orders.events", groupId = "orders-worker")
public void onOrder(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

có thể giữ exception gốc tốt hơn việc bọc ở mọi tầng.

### 8.1. Không nuốt exception khi chưa phục hồi

~~~java
@KafkaListener(topics = "orders.events")
public void wrong(OrderEvent event) {
    try {
        orderService.process(event);
    }
    catch (Exception ex) {
        log.error("Processing failed", ex);
        // Sai nếu return nghĩa là record đã xử lý thành công.
    }
}
~~~

Với nhiều ack/commit policies, listener trả về bình thường có thể khiến offset được xác nhận. Log đầy đủ exception chain nhưng **làm mất khả năng retry** vẫn là thiết kế sai. Hãy rethrow hoặc có recovery bền vững được xác nhận trước khi đánh dấu thành công.

## 9. Log tại DefaultErrorHandler

`DefaultErrorHandler` là thành phần xử lý lỗi record phổ biến trong Spring Kafka non-transactional listener container. Nó có thể retry, backoff, seek/re-deliver và recover record qua `ConsumerRecordRecoverer` như `DeadLetterPublishingRecoverer`.

Ví dụ cấu hình:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltKafkaTemplate);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 2L));

    return handler;
}
~~~

Ví dụ chỉ minh họa wiring cơ bản. Template DLT cần serializer và partition/topic routing phù hợp với kiểu record có thể được recover. Với custom listener factory, cần chắc chắn bean error handler thực sự được gắn vào factory đang dùng; Spring Boot auto-configuration có thể khác khi app khai báo bean riêng.

### 9.1. Dùng RetryListener để log attempt có ngữ cảnh

Ở các phiên bản Spring Kafka hỗ trợ `RetryListener`:

~~~java
handler.setRetryListeners(new RetryListener() {

    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception ex,
            int deliveryAttempt) {

        Throwable root = Exceptions.rootCause(ex);

        log.warn(
                "Kafka retry attempt: topic={}, partition={}, " +
                "offset={}, attempt={}, outerClass={}, rootClass={}",
                record.topic(),
                record.partition(),
                record.offset(),
                deliveryAttempt,
                ex.getClass().getSimpleName(),
                root == null
                        ? "unknown"
                        : root.getClass().getSimpleName());
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception ex) {
        log.error(
                "Kafka record recovered after processing failure: " +
                "topic={}, partition={}, offset={}",
                record.topic(),
                record.partition(),
                record.offset(),
                ex);
    }
});
~~~

Ở đây, `failedDelivery` ghi thông tin gọn về attempt, còn `recovered` ghi Throwable đầy đủ tại thời điểm recovery. Đây là một lựa chọn giảm log volume, không phải quy tắc bắt buộc. Một recoverer có thể đưa record sang DLT thành công, vì vậy `recovered` có thể được coi là ERROR hay WARN tùy SLO và policy hệ thống; không đồng nhất recovery thành công với nghiệp vụ thành công.

**Quan trọng:** Nếu dùng `DefaultErrorHandler` cho non-transactional container, logic retry này khác với luồng after-rollback của transactional listener container. Đừng lấy code error handler rồi suy ra nó bao phủ mọi Kafka transaction failure.

### 9.2. Log một lần ở terminal boundary

Một chiến lược thực tế:

| Giai đoạn | Log gợi ý | Nội dung |
|---|---|---|
| Retry lần đầu | WARN ngắn | Reason, topic/partition/offset, attempt |
| Retry tiếp theo | DEBUG hoặc WARN có rate limit | Không lặp full stack trace vô hạn |
| Recover sang DLT thành công | WARN/ERROR tùy SLO | Original error class, DLT destination, correlation |
| Recovery thất bại | ERROR với Throwable đầy đủ | Original failure và recovery failure |
| Container dừng vì lỗi fatal | ERROR với Throwable đầy đủ | Lifecycle state, partition, group |

Chọn điểm log dựa trên ownership của service. Nếu framework đang log exception đầy đủ theo mặc định, có thể cần điều chỉnh logger categories phù hợp hoặc không thêm logger trùng.

## 10. Exception xảy ra trước khi listener được gọi

Kafka client deserialize key/value trong quá trình `poll()`. Một `JsonDeserializer` hoặc codec Avro/Protobuf có thể ném exception trước khi listener được gọi. Khi đó:

~~~text
Broker raw bytes
        |
        v
KafkaConsumer.poll()
        |
        v
Kafka deserializer
        |
        +--- exception
              |
              v
     Listener chưa được gọi
~~~

Một `try/catch` trong listener hoàn toàn không thấy lỗi này. Log chỉ ở listener sẽ bỏ sót deserialization error.

### 10.1. ErrorHandlingDeserializer

Spring Kafka cung cấp `ErrorHandlingDeserializer` để bọc delegate deserializer. Khi delegate lỗi, wrapper có thể lưu thông tin exception vào Kafka header do framework dùng để error handler/recovery làm việc với record.

Ví dụ Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-worker
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.trusted.packages]": com.example.orders.events
~~~

Ví dụ phải được điều chỉnh cho event types/serializer thật của ứng dụng. Nếu key deserializer cũng có thể thất bại, cần cấu hình xử lý lỗi key tương ứng.

### 10.2. Log đúng failure stage

Nếu `DeserializationException` được đưa tới recovery path, structured log nên nêu:

~~~text
failure_stage=deserialize_value
source_topic=orders.events
source_partition=2
source_offset=345
outer_class=DeserializationException
root_class=JsonParseException
recovery=dlt
~~~

Đây là dữ liệu minh họa. Không log raw bytes hoặc bản deserialize partial chưa được xác thực chỉ để nhìn “nội dung message”.

### 10.3. Raw payload và DLT serializer

Với lỗi deserialize, DLT có thể cần lưu raw `byte[]` thay vì domain object. Nếu DLT producer được cấu hình chỉ serialize JSON object, recovery có thể thất bại và phát sinh **exception chain thứ hai** tại DLT send.

Khi điều tra, phải phân biệt:

1. Original deserialization failure.
2. DLT publish/serialization failure.

Không thay original error bằng DLT error rồi mất bằng chứng nguyên nhân ban đầu.

## 11. Lỗi chuyển đổi message và method argument

Sau Kafka deserializer, Spring Kafka có thể còn thực hiện message conversion hoặc binding vào tham số listener. Lỗi có thể xuất hiện khi:

- Header bắt buộc không có.
- Payload type không khớp method signature.
- JSON payload parse được nhưng không map được model mong muốn.
- Validation ở tầng adapter không đạt.
- Message converter chọn kiểu mục tiêu sai.

Ví dụ:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(
        @Payload OrderCreated event,
        @Header("event-type") String eventType) {
    orderService.process(event);
}
~~~

Nếu header `event-type` bắt buộc nhưng không có, lỗi có thể phát sinh ở argument resolution trước khi business method thực sự chạy. Log cần ghi `failure_stage=listener_adapter` hoặc `message_conversion` thay vì chẩn đoán nhầm database.

### 11.1. Một cause chain có thể che lỗi validation

Ví dụ:

~~~text
ListenerExecutionFailedException
  -> MessageConversionException
     -> IllegalArgumentException
~~~

Thông điệp ở wrapper có thể chung chung; cần thấy class và message của cause thích hợp. Tuy nhiên, không dùng nguyên văn message chứa payload làm alert tags hoặc đưa ra log công khai.

## 12. Log exception chain của KafkaTemplate.send bất đồng bộ

`KafkaTemplate.send(...)` trong Spring Kafka hiện đại trả về `CompletableFuture<SendResult<K,V>>`. Lỗi gửi có thể xuất hiện khi future hoàn tất thất bại.

Ví dụ:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> future =
        kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        Throwable root = Exceptions.rootCause(exception);

        log.error(
                "Kafka publish failed: topic={}, eventType={}, " +
                "outerClass={}, rootClass={}",
                "orders.created",
                "OrderCreated",
                exception.getClass().getSimpleName(),
                root == null
                        ? "unknown"
                        : root.getClass().getSimpleName(),
                exception);
    }
});
~~~

Nếu `exception` là `CompletionException` và cause là lỗi Kafka producer, việc truyền nguyên Throwable vào logger giữ cả wrapper lẫn root cause.

### 12.1. Lỗi còn có thể ném đồng bộ

Không phải mọi lỗi producer đều chỉ xuất hiện trong future. Tạo record, convert payload hoặc một số validation/configuration có thể ném exception khi gọi API. Đường gọi publish cần bảo đảm lỗi đồng bộ cũng được truyền hoặc ghi ở boundary phù hợp.

### 12.2. join() và get() tạo wrappers khác nhau

Với Java future:

~~~java
future.join(); // có thể ném CompletionException.
future.get();  // có thể ném ExecutionException.
~~~

Khi log, truyền original wrapper Throwable để giữ chain. Khi quyết định classification/retry, có thể unwrap một số wrapper kỹ thuật đã biết, nhưng đừng liên tục unwrap tới root cause rồi mất stage/scope.

### 12.3. Không nuốt lỗi bất đồng bộ

Một callback chỉ log exception nhưng service bên ngoài đã trả “publish thành công” có thể dẫn đến dữ liệu nghiệp vụ không có event. Cần một workflow bảo đảm durability, ví dụ outbox, lưu pending state, hoặc một completion strategy cho caller.

Log đầy đủ không thay thế error propagation và retry/recovery phù hợp.

## 13. Producer send lỗi và transaction commit lỗi là hai giai đoạn

Trong Kafka transactions, một record có thể được Kafka producer gửi thành công trong transaction nhưng transaction sau đó bị abort hoặc commit thất bại.

~~~text
BEGIN Kafka transaction
       |
       v
KafkaTemplate.send(record A)
       |
       +-- broker ack thành công
       |
       v
COMMIT transaction
       |
       +-- có thể thất bại: timeout, fencing, coordinator issue
~~~

Nếu log chỉ:

~~~text
Kafka send acknowledged
~~~

thì chưa chứng minh record đã committed và downstream `read_committed` sẽ nhìn thấy nó.

Đối với transactional flow, thêm trạng thái:

- `send_acknowledged`.
- `transaction_commit_succeeded`.
- `transaction_aborted`.
- `transaction_commit_failed`.

Không giả định một producer span hoặc send result tương đương transaction commit outcome.

### 13.1. ProducerFencedException

Lỗi `ProducerFencedException` có thể phát sinh khi một transactional producer cũ bị broker thay thế bởi producer khác dùng cùng transactional ID. Log hữu ích cần chứa:

- Service instance/pod.
- Transactional ID hoặc định danh đã được kiểm soát cho diagnostics.
- Kafka transaction stage.
- Producer lifecycle/restart context.
- Exception chain đầy đủ.

Không được tiếp tục dùng producer đã bị fenced để commit. Đây là lỗi lifecycle/ownership quan trọng cần xử lý tận gốc, không chỉ retry vô hạn.

### 13.2. Transactional listener container

Với listener container có Kafka transaction manager, exception từ listener thường làm transaction rollback. Logic after-rollback và DLT recovery có cơ chế riêng, chẳng hạn `DefaultAfterRollbackProcessor`. Đừng dùng cách logging của `DefaultErrorHandler` non-transactional rồi giả định bắt được mọi exception ở commit/rollback phase.

## 14. Khi failure xảy ra trong recovery/DLT

Một record có thể có **hai lỗi độc lập**:

1. Original processing exception.
2. Recovery exception khi publish DLT hoặc cập nhật state.

Ví dụ:

~~~text
Original:
  ListenerExecutionFailedException
    -> OrderProcessingException
       -> SQLException

Recovery:
  KafkaException
    -> TimeoutException (DLT producer)
~~~

Nếu chỉ log recovery Throwable, bạn biết “DLT timeout” nhưng mất thông tin tại sao record ban đầu bị reject. Nếu chỉ log original Throwable, bạn bỏ sót việc hệ thống **không lưu được record lỗi** và có thể đang không tiến offset an toàn.

### 14.1. Một event log có thể ghi cả hai chain

Tại recovery boundary, có thể ghi hai Throwable ở **hai log entries có cùng incident/correlation key**:

~~~java
log.error(
        "Kafka DLT recovery failed: topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset(),
        recoveryFailure);

log.warn(
        "Original processing failure for same record",
        originalFailure);
~~~

Đây là ví dụ cho tình huống recovery failed thực sự, không phải gợi ý luôn log hai stack traces ở mọi retry. Chọn cách tương ứng với log volume và công cụ observability. Nếu ứng dụng có một aggregate exception với original exception được gắn làm cause/suppressed theo đúng semantics, có thể log một Throwable thay vì hai entries.

### 14.2. DLT headers và metadata

`DeadLetterPublishingRecoverer` có thể thêm metadata về topic/partition/offset gốc và exception vào DLT headers theo phiên bản/configuration. Những headers này hỗ trợ forensic replay nhưng **không thay thế original stack trace log**: DLT retention, header size, privacy policy và serializer có giới hạn riêng.

Không tự serialize toàn bộ Throwable object vào Kafka header hoặc payload nếu không có format/trust policy rõ ràng; serialization của exception có thể mang classes hoặc dữ liệu nhạy cảm không phù hợp.

### 14.3. Recovery success khác nghiệp vụ success

Khi record được đưa DLT thành công, kết quả đúng có thể là:

~~~text
recovery_status=dlt_published
business_status=not_completed
~~~

Không báo `processing_success=true` chỉ vì consumer đã qua được offset nguồn. DLT là một đường lưu lỗi để điều tra/replay, không phải hoàn tất nghiệp vụ.

## 15. Blocking retry và log storm

Với `DefaultErrorHandler` và backoff, cùng một record có thể được xử lý nhiều lần:

~~~text
offset 100
  |
  +-- attempt 1 -> DB timeout
  |
  +-- attempt 2 -> DB timeout
  |
  +-- attempt 3 -> DB timeout
  |
  +-- recover / DLT / stop theo policy
~~~

Nếu cả listener, service, repository adapter và error handler đều log ERROR full stack ở mỗi attempt, một record có thể tạo hàng chục log lớn; một outage downstream có thể biến thành **log storm**.

### 15.1. Chính sách theo attempt

Một cách thiết kế:

| Attempt / trạng thái | Severity gợi ý | Nội dung |
|---|---|---|
| Lỗi retryable lần đầu | WARN | Stage, normalized reason, record location |
| Các attempt tiếp theo | DEBUG hoặc WARN có rate limit | Attempt, backoff, root cause class |
| Retry cuối cùng không phục hồi | ERROR | Throwable đầy đủ và recovery decision |
| DLT publish thành công | WARN/ERROR theo nghiệp vụ | DLT destination, original error |
| DLT publish thất bại | ERROR/CRITICAL | Recovery Throwable và original chain |

Không có một quy tắc severity đúng cho mọi dịch vụ. Lỗi transient có thể chỉ cần metric + WARN; dữ liệu thanh toán không thể recover có thể cần ERROR và page.

### 15.2. Giới hạn log theo khóa phù hợp

Có thể rate limit theo:

- Service.
- Exception class đã chuẩn hóa.
- Failure stage.
- Topic.
- Khoảng thời gian.

Không đưa raw record key, event ID hay exception message vào metric tags. Nếu cần đối soát một record, structured log có topic/partition/offset hoặc event ID đã được bảo vệ.

### 15.3. Exponential backoff khác log rate limit

Backoff điều chỉnh **khi nào xử lý lại record**; log rate limit điều chỉnh **bao nhiêu log được xuất**. Hai cơ chế độc lập. Giảm log không sửa retry storm ở Kafka; tăng backoff cũng không bảo đảm một error handler custom không log trùng.

## 16. Non-blocking retry topics và exception chain xuyên message

Với `@RetryableTopic`, một failure có thể dẫn tới publish record sang retry topic khác:

~~~text
orders.events
       |
       v
orders.events-retry-1000
       |
       v
orders.events-retry-5000
       |
       v
orders.events-dlt
~~~

Mỗi bước có thể chạy trong một consumer invocation mới và tạo Throwable mới. Do đó **không nên giả định một Java cause chain duy nhất chạy xuyên suốt tất cả retry topics**. Các attempts nằm ở những bản record/transactions khác nhau.

Để đối soát toàn hành trình, cần:

1. Event ID ổn định qua republish.
2. Source topic/partition/offset gốc khi có.
3. Retry topic và attempt metadata.
4. Trace/correlation context nếu được propagate.
5. Log original failure và retry terminal outcome.

### 16.1. Retry headers không phải exception objects

Một Kafka record ở retry topic mang bytes và headers, không thể mang nguyên JVM stack trace live của lần trước. Framework có thể serialize metadata về lỗi, nhưng một Throwable object trong lần xử lý mới là đối tượng mới.

Không cố đối chiếu object identity hoặc Java stack frame giữa các attempts; dùng event ID và message metadata.

### 16.2. Không nhầm trace ID với event ID

Trace ID giúp nối các bước quan sát nếu context còn được giữ và sampled, nhưng có thể thay đổi khi replay sau nhiều giờ. Event ID là định danh nghiệp vụ ổn định để deduplicate và theo dõi recovery. Hai giá trị có mục tiêu khác nhau.

## 17. Một structured log tối thiểu cho lỗi Kafka

Structured logging (JSON hoặc key-value) cho phép truy vấn theo group, topic, partition và failure stage.

Ví dụ:

~~~json
{
  "level": "ERROR",
  "service": "orders-worker",
  "instance": "pod-a",
  "consumerGroup": "orders-worker",
  "topic": "orders.events",
  "partition": 2,
  "offset": 345,
  "stage": "listener_processing",
  "attempt": 3,
  "outerException": "ListenerExecutionFailedException",
  "rootCause": "SocketTimeoutException",
  "reason": "database_timeout",
  "recovery": "dlt_requested",
  "traceId": "sample-trace-id",
  "eventId": "sample-event-id"
}
~~~

Đây là dữ liệu minh họa, không phải schema bắt buộc. Stack trace có thể nằm ở field riêng do logging backend hỗ trợ. Trong ứng dụng thật, **không log traceId/eventId không được phép** và không đưa những giá trị có cardinality cao vào metrics labels.

### 17.1. Các field quan trọng

| Field | Vì sao hữu ích? |
|---|---|
| `service`, `instance` | Tìm pod/JVM xảy ra lỗi |
| `consumerGroup` | Xác định tiến độ group |
| `topic`, `partition`, `offset` | Định vị record nguồn trong log Kafka |
| `stage` | Phân biệt deserialize, business, publish, commit, recover |
| `attempt` | Phân biệt retry lần đầu và lỗi terminal |
| `outerException` | Nhìn framework boundary |
| `rootCause` | Nhìn lỗi kỹ thuật sâu nhất |
| `reason` | Nhãn chuẩn hóa để alert/dashboard |
| `recovery` | Biết retry, DLT, committed hay failed |
| `traceId`/`eventId` | Liên kết với trace và nghiệp vụ khi policy cho phép |

### 17.2. Kafka offset chỉ có ý nghĩa kèm topic và partition

Offset 345 không duy nhất trên toàn cluster. Cần ít nhất topic + partition + offset, và khi có nhiều clusters thì cần cluster/environment. Một event sau DLT có **offset mới trên DLT**, không thể lấy offset DLT thay cho offset nguồn.

### 17.3. Đừng hiển thị “Kafka recovered” mơ hồ

“Recovered” có thể có nghĩa:

- Record được publish DLT thành công.
- Listener đã retry rồi thành công.
- Sau rollback, container đã bỏ qua record theo policy.
- Workflow nghiệp vụ được compensation.

Đặt giá trị `recovery` rõ ràng, ví dụ `retry_scheduled`, `dlt_published`, `replay_completed`, `recovery_failed` để tránh lẫn trạng thái.

## 18. MDC và trace context

Các hệ thống dùng Micrometer Tracing/OpenTelemetry có thể đưa `traceId` và `spanId` vào MDC để logger tự gắn correlation fields.

Khi một Kafka record đi qua listener:

~~~text
Producer trace headers
          |
          v
Kafka ConsumerRecord
          |
          v
Spring Kafka Observation/Tracing
          |
          v
Active trace context
          |
          v
MDC traceId/spanId (nếu cấu hình bridge)
          |
          v
Structured application log
~~~

Để có điều này cần observation/tracing integration ở consumer, propagation format phù hợp và logging config tương ứng. Không giả định Kafka headers luôn được copy tự động vào MDC nếu ứng dụng chưa bật tracing.

### 18.1. Async thread có thể mất MDC

Ví dụ listener submit task sang thread pool; MDC/trace context thường không tự đi theo:

~~~java
executor.submit(() -> processInBackground(event));
~~~

Nếu cần giữ correlation, sử dụng context propagation phù hợp với Micrometer/Spring version và đóng scopes sau task. Đồng thời bảo đảm offset/ack được xử lý an toàn; một log có trace ID đúng không chứng minh background task đã hoàn tất trước commit.

### 18.2. Không tự ghi thông tin nhạy cảm vào MDC

MDC thường được đưa vào mọi log của thread. Không đặt raw payload, access token, email khách hàng hoặc dữ liệu thanh toán trong MDC. Ngoài nguy cơ rò rỉ, MDC không được cleanup có thể lẫn context giữa các requests khi thread pool tái sử dụng thread.

## 19. Log throwable an toàn: PII, secrets và kích thước

Exception message và stack trace đôi khi chứa:

- SQL câu truy vấn và tham số.
- URL có token hoặc query chứa PII.
- Hostname, internal IP hoặc endpoint nhạy cảm.
- Kafka record payload mà một custom deserializer đưa vào message.
- Username, account ID hoặc metadata tenant.
- Credentials nếu thư viện báo lỗi không an toàn.

Vì thế, “log full exception chain” không đồng nghĩa được phép đưa mọi thứ ra log công khai.

### 19.1. Giữ cấu trúc lỗi, lọc dữ liệu nhạy cảm

Các biện pháp:

1. Không nhúng raw payload vào custom exception message.
2. Không gọi `record.value().toString()` trong log lỗi nếu event chứa dữ liệu nhạy cảm.
3. Sử dụng logging encoder có masking/redaction được kiểm thử.
4. Giới hạn quyền truy cập log và retention.
5. Dùng event ID/offset để tra dữ liệu trong kho được kiểm soát.
6. Bảo vệ DLT/quarantine bằng ACL, encryption và privacy policy tương đương.

Đặc biệt với lỗi deserialize, raw bytes có thể không đáng tin hoặc chứa dữ liệu chưa được parse/validate; không chuyển chúng thẳng thành chuỗi log.

### 19.2. Giới hạn dung lượng stack trace

Một cause chain sâu hoặc các suppressed exceptions lớn có thể tạo log event vượt giới hạn collector. Cần chọn logging backend/encoder hỗ trợ giới hạn dung lượng hợp lý và có khả năng lưu full diagnostics có kiểm soát khi incident.

Đừng chỉ cắt Throwable bằng `ex.getMessage()` để giảm kích thước, vì làm mất stack trace/cause. Có thể cân nhắc:

- Full stack trace ở terminal/fatal boundary.
- Concise root/outer class ở từng retry.
- Sampling/rate limiting cho exception lặp.
- Hệ thống forensic riêng khi cần log dài.

## 20. Exception classification dựa trên chain

Error handler cần quyết định một exception có nên retry hay không. Một số lỗi tạm thời:

- Database connection timeout.
- HTTP downstream 503.
- Kafka broker unavailable tạm thời.
- Schema Registry request timeout.

Một số lỗi thường vĩnh viễn với cùng payload:

- JSON malformed.
- Schema không hợp lệ đối với contract hiện hành.
- Required header thiếu.
- Business validation không thể sửa bằng retry.

Nhưng chỉ nhìn root cause có thể sai. Ví dụ:

~~~text
ListenerExecutionFailedException
 -> RetryableBusinessException
    -> IllegalStateException
~~~

`IllegalStateException` ở gốc không nói đủ policy; wrapper nghiệp vụ có thể xác định cần retry vì dependency đang chuyển trạng thái.

Ngược lại:

~~~text
ListenerExecutionFailedException
 -> PermanentInvalidEventException
    -> IllegalArgumentException
~~~

Không nên retry vô hạn chỉ vì root cause được gọi chung chung.

### 20.1. Đừng dùng regex trên exception message để quyết định retry

Thông điệp exception có thể thay đổi theo version, locale hoặc driver. Nên phân loại qua exception types, stage và cause chain đã biết. Ghi `reason` chuẩn hóa cho observability.

### 20.2. Khi exception bị bọc nhiều tầng

Error handler của Spring Kafka có các cơ chế xem cause/wrapper theo version. Khi thêm custom exception type vào `addNotRetryableExceptions(...)` hoặc classification map, phải kiểm tra thực tế rằng wrapper/cause chain được nhận diện theo cấu hình hiện tại; không chỉ nhìn tên class ở sâu nhất rồi giả định classifier tự duyệt như mong đợi.

## 21. Khi nào chỉ log class thay vì full stack?

Không phải mọi attempt cần full stack trace. Chọn theo mục đích:

| Ngữ cảnh | Log phù hợp |
|---|---|
 Retry transient lặp nhiều lần | Structured WARN với outer/root class, attempt, stage |
| Lỗi terminal chưa giải quyết | ERROR + nguyên Throwable |
| Lỗi đẩy DLT | ERROR + recovery Throwable và original cause |
| Monitoring tổng hợp | Metrics count, reason labels, không stack |
| Audit replay thủ công | Event ID, nguồn, người thực hiện, kết quả |
| Debug có kiểm soát | Full stack khi cần và không lộ dữ liệu |

Nếu hệ thống đã có một log stack trace ở terminal boundary, các lớp service có thể chỉ ném exception giữ nguyên cause để tránh duplicate. Nếu không có tầng nào log terminal errors, cần bổ sung instrumentation ở ranh giới chịu trách nhiệm.

## 22. Error-handler logging không thay thế metrics

Một triệu lần retry cùng `SocketTimeoutException` không nên tạo một triệu full stack traces. Các chỉ số hữu ích:

| Metric | Mục đích |
|---|---|
| Exception attempts by reason/stage | Đếm retry/errors theo nhóm |
| Recoveries to DLT | Số record chuyển recovery |
| DLT publish failures | Lỗi của đường recovery |
| Listener processing duration | Thời gian hoạt động |
| Kafka consumer lag | Backlog và tiến độ |
| Oldest unprocessed record age | Tác động theo SLA |
| Producer send failures | Lỗi publish |
| Kafka transaction abort rate | Vấn đề transaction |
| Database/HTTP timeout rate | Lỗi dependency |

Metric tags nên là `service`, `topic` (tập kiểm soát), `stage`, `reason` và một vài dimensions hữu hạn khác. **Không dùng full exception message, Kafka offset, event ID hoặc trace ID làm metrics tag.**

## 23. Runbook: log chỉ có “Listener method failed”

Khi gặp dòng log quá chung chung:

1. Xác định log statement hiện tại có truyền Throwable object không.
2. Kiểm tra ứng dụng chỉ ghi `ex.getMessage()` hay có stack trace đầy đủ.
3. Tìm `Caused by` trong log event tương ứng.
4. Kiểm tra structured logger/collector có cắt stack trace không.
5. Ghi nhận topic, partition, offset, group và attempt.
6. Phân loại stage: conversion, business, database, producer.
7. Nếu chain bị đứt, kiểm tra custom exception constructor có truyền `cause` không.
8. Bổ sung log ở terminal boundary, không log trùng ở mọi tầng.
9. Sau khôi phục, dùng metrics/offset chứng minh pipeline đã tiến.

Không chỉ sửa message thành dài hơn. Cần giữ nguyên Throwable chain và record metadata.

## 24. Runbook: Kafka listener không được gọi nhưng consumer báo lỗi

1. Kiểm tra lỗi xảy ra ở `KafkaConsumer.poll()` hay listener adapter.
2. Kiểm tra key/value deserializer configuration.
3. Xác định có dùng `ErrorHandlingDeserializer` nếu cần recover raw bytes không.
4. Kiểm tra exception class: `RecordDeserializationException`, `SerializationException`, conversion failure.
5. Xác nhận topic, partition, offset và schema ID/framing khi có.
6. Không log raw payload trên production log thông thường.
7. Kiểm tra DLT producer hỗ trợ raw `byte[]`.
8. Kiểm tra offset commit sau recovery để tránh poison pill kéo dài.

Nếu lỗi phát sinh trước listener, thêm `try/catch` vào method không khắc phục được. Cần sửa deserializer/error handling path.

## 25. Runbook: nhiều ERROR logs cho cùng một record

1. Đối chiếu topic/partition/offset/event ID.
2. Kiểm tra record đang được retry hay thực sự là duplicate event.
3. Xem logs từ service method, listener, error handler và recoverer.
4. Xác định tầng nào chịu trách nhiệm terminal logging.
5. Giảm stack trace ở từng attempt nếu không cần.
6. Giữ một full throwable tại điểm recovery/fatal.
7. Dùng metrics để đo attempt count thay vì một log lớn cho mỗi attempt.
8. Kiểm tra log retention và collector throttling.

Không xóa hết logs vì một incident bị spam; cần bảo đảm vẫn có thông tin root cause và trạng thái recovery.

## 26. Runbook: DLT recovery thất bại

1. Tìm log original processing failure.
2. Tìm log recovery exception tại cùng source record identity.
3. Kiểm tra KafkaTemplate/serializer của DLT, đặc biệt raw bytes.
4. Kiểm tra DLT topic tồn tại, ACL, quotas, message size và broker health.
5. Kiểm tra transaction/offset recovery semantics.
6. Xác nhận source offset không được xem là hoàn tất khi DLT chưa publish an toàn.
7. Khôi phục DLT rồi replay/retry theo policy.
8. Đối soát event IDs để tránh DLT duplicates gây side effect trùng.

Trong báo cáo incident, ghi rõ lỗi nào là **original** và lỗi nào là **recovery**; nếu không, đội vận hành có thể chỉ sửa DLT producer mà bỏ qua lỗi dữ liệu ban đầu.

## 27. Runbook: exception class lạ sau nâng cấp Spring Kafka

1. Ghi rõ Spring Kafka/Kafka client/Boot versions trước và sau thay đổi.
2. Đọc outer class và toàn bộ cause chain.
3. So sánh failure stage và behavior retry/DLT trước/sau deploy.
4. Kiểm tra exception classification được cấu hình theo wrapper cũ.
5. Kiểm tra log parser/dashboard có phụ thuộc message literal không.
6. Xác nhận exception vẫn được rethrow và không bị swallow.
7. Chạy integration test với các lỗi cố ý.
8. Cập nhật normalized reason mapping nếu cần, giữ audit về thay đổi.

Không sửa bằng cách catch `Exception` rồi bỏ qua mọi wrapper mới; điều đó có thể làm mất error recovery.

## 28. Kiểm thử kỹ thuật cho exception chain logging

Unit test có thể xác nhận custom exception giữ cause. Integration test cần xác nhận path của Spring Kafka.

### 28.1. Test constructor giữ cause

~~~java
@Test
void preservesOriginalCause() {
    IOException root =
            new IOException("Network timeout");

    OrderProcessingException failure =
            new OrderProcessingException(
                    "Cannot process order",
                    root);

    assertThat(failure.getCause()).isSameAs(root);
    assertThat(Exceptions.rootCause(failure))
            .isSameAs(root);
}
~~~

### 28.2. Test wrapper chain

~~~java
@Test
void extractsDeepestCause() {
    Throwable root =
            new SocketTimeoutException("Read timed out");

    Throwable middle =
            new IllegalStateException("Database call failed", root);

    Throwable outer =
            new OrderProcessingException(
                    "Kafka order processing failed",
                    middle);

    assertThat(Exceptions.rootCause(outer))
            .isSameAs(root);
}
~~~

Đây là test helper thuần Java, không chứng minh Kafka listener/recoverer đang log đúng; cần integration test thực tế cho pipeline.

### 28.3. Test SLF4J appender

Với Logback trong môi trường test, có thể dùng `ListAppender<ILoggingEvent>` để bắt events và xác nhận throwable proxy tồn tại khi logger nhận Throwable:

~~~java
Logger logger =
        (Logger) LoggerFactory.getLogger(OrderEventsListener.class);

ListAppender<ILoggingEvent> appender =
        new ListAppender<>();
appender.start();
logger.addAppender(appender);

try {
    RuntimeException root =
            new RuntimeException("Root failed");

    logger.error("Listener failed: topic={}", "orders.events", root);

    assertThat(appender.list).hasSize(1);
    assertThat(appender.list.get(0).getThrowableProxy())
            .isNotNull();
}
finally {
    logger.detachAppender(appender);
    appender.stop();
}
~~~

Ví dụ test này dùng Logback classes và AssertJ, không phải API bắt buộc của mọi logging backend. Test thực tế cần cô lập logger/test context để tránh ảnh hưởng test chạy song song.

### 28.4. Test listener error handler

1. Gửi record hợp lệ nhưng business service ném exception có cause nhiều tầng.
2. Xác nhận `@KafkaListener` không swallow.
3. Xác nhận error handler nhận Throwable chain.
4. Kiểm tra số attempts theo backoff configuration.
5. Xác nhận full stack trace ở terminal boundary theo policy.
6. Xác nhận record được retry/DLT theo classification.

### 28.5. Test deserialize failure

1. Gửi payload bytes malformed cho deserializer.
2. Xác nhận listener không được gọi nếu decode lỗi trước listener.
3. Nếu dùng `ErrorHandlingDeserializer`, xác nhận recovery path có raw bytes phù hợp.
4. Xác nhận logs có failure stage và class/cause.
5. Không đưa payload nhạy cảm ra log.

### 28.6. Test producer asynchronous failure

1. Tạo failure có kiểm soát ở Kafka producer/broker.
2. Xác nhận future hoàn tất exception.
3. Xác nhận outer/inner exception được log đầy đủ.
4. Kiểm tra method/caller biết publish không thành công theo durability policy.
5. Đảm bảo không log trùng vô hạn từ callback và caller.

### 28.7. Test DLT recovery failure

1. Buộc listener ném exception non-retryable.
2. Buộc DLT producer thất bại (ví dụ ACL trong test).
3. Xác nhận original exception và recovery exception được truy vết.
4. Xác nhận source record không bị xác nhận mất dữ liệu.
5. Khôi phục DLT và đối soát state sau recovery.

## 29. Những sai lầm thường gặp

**Chỉ log `getMessage()`.** Không giữ class/cause/stack trace, rất khó xác định root cause.

**Bọc exception mà không truyền cause.** Làm đứt chain và mất stack trace ban đầu.

**Log ERROR full stack ở mọi tầng.** Một retry storm có thể thành log storm.

**Coi root cause là toàn bộ chính sách retry.** Cần stage và wrapper nghiệp vụ.

**Catch exception rồi return.** Có thể commit offset dù business operation thất bại.

**Cho rằng listener catch mọi lỗi Kafka.** Deserialize/commit/recovery có thể xảy ra ngoài listener.

**Chỉ log original failure nhưng bỏ qua DLT failure.** Không biết recovery đã mất an toàn.

**Chỉ log DLT failure nhưng quên original failure.** Không biết record lỗi vì nguyên nhân gì.

**Dùng raw payload làm log metadata.** Có nguy cơ lộ PII, secret và tạo log cực lớn.

**Dùng exception message làm metric label.** Cardinality không kiểm soát và có nguy cơ lộ dữ liệu.

**Không phân biệt send acknowledged và transaction committed.** Có thể kết luận sai về delivery.

**Cho rằng retry topic giữ nguyên Java exception chain.** Republish tạo invocation/Throwable mới; cần event ID và Kafka metadata.

**Dùng trace ID làm idempotency key.** Trace ID phục vụ quan sát, không phải định danh event ổn định.

**Không giới hạn logging ở incident lớn.** Collector có thể drop logs, làm mất tín hiệu quan trọng.

## 30. Checklist trước production

### Exception construction và propagation

- [ ] Custom exceptions dùng constructor có `cause`.
- [ ] Listener không swallow lỗi chưa được recover.
- [ ] Không bọc exception vô nghĩa ở mọi tầng.
- [ ] Có cách phân biệt original failure và recovery failure.
- [ ] Checked/runtime exceptions được xử lý đúng với transaction/rollback policy.

### Logging

- [ ] SLF4J nhận original Throwable làm tham số cuối.
- [ ] Có topic/partition/offset/group khi nguồn record xác định được.
- [ ] Có failure stage, outer class, root cause class và attempt.
- [ ] Có full stack trace ở terminal/fatal boundary.
- [ ] Retry logs có severity/rate limit phù hợp.
- [ ] Không log raw payload, credentials hoặc PII.

### Kafka error paths

- [ ] Có xử lý lỗi deserialize trước listener khi cần.
- [ ] Error handler/retry listener log đúng type và attempt.
- [ ] DLT recovery logging giữ original và recovery failures.
- [ ] Không coi DLT publish thành công là business success.
- [ ] KafkaTemplate asynchronous errors được quan sát.
- [ ] Kafka transaction commit/abort được quan sát riêng với send.

### Observability

- [ ] Structured logs có service, instance và correlation metadata phù hợp.
- [ ] MDC/trace scope không rò qua async thread pool.
- [ ] Metrics reason tags có cardinality thấp.
- [ ] Có consumer lag, retry/DLT rate và business completion signals.
- [ ] Collector xử lý log volume/stack traces theo policy.
- [ ] Có runbook cho wrapper-only logs, poison pill và DLT failure.

### Kiểm thử

- [ ] Test custom exception giữ cause.
- [ ] Test log appender nhận Throwable proxy.
- [ ] Test listener error handler nhận exception chain.
- [ ] Test deserialize error trước listener.
- [ ] Test async KafkaTemplate send failure.
- [ ] Test DLT recovery failure mà không mất source record.
- [ ] Test log không rò dữ liệu nhạy cảm theo chính sách.

## Kết luận

**Log exception chain** trong Spring Kafka là thực hành lưu giữ đầy đủ quan hệ giữa **exception ở ranh giới hiện tại**, **những cause nằm sâu bên trong** và **suppressed exceptions khi có**, đồng thời bổ sung metadata về topic, partition, offset, attempt và recovery stage. Cách cơ bản và quan trọng nhất là **không làm mất cause khi bọc exception** và **truyền original Throwable trực tiếp cho SLF4J logger**, thay vì chỉ ghi `getMessage()`.

Với Kafka reliability, cần quan sát nhiều failure boundaries: deserialize có thể lỗi trước `@KafkaListener`; listener error có thể bị Spring Kafka bọc thêm; `KafkaTemplate` có thể báo lỗi qua future; transaction commit có thể thất bại sau send; và DLT recovery có thể có exception thứ hai. Hãy chọn một điểm log đầy đủ ở giai đoạn terminal, ghi attempts bằng thông tin ngắn/metrics, tách original failure khỏi recovery failure, bảo vệ dữ liệu nhạy cảm và dùng event ID/trace context để liên hệ các lượt retry/replay. **Một stack trace rõ nguyên nhân giúp chẩn đoán, nhưng chỉ error handling, offset/transaction correctness và recovery bền vững mới bảo vệ dữ liệu thật sự.**
