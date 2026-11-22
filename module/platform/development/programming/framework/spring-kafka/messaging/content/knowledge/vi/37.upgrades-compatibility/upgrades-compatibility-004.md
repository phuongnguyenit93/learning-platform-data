# Thay đổi error handler qua các phiên bản

Spring Kafka đã thay đổi cách container xử lý lỗi listener qua nhiều phiên bản. Ở các phiên bản cũ, record listener và batch listener dùng hai họ interface riêng là `ErrorHandler` và `BatchErrorHandler`. Từ Spring Kafka 2.8, framework giới thiệu `CommonErrorHandler` để thống nhất hai luồng này; `DefaultErrorHandler` trở thành lựa chọn thay thế cho phần lớn handler cũ. Từ 2.9, API của `CommonErrorHandler` tiếp tục được chỉnh để mô tả rõ hơn việc handler xử lý riêng record lỗi hay tự seek các record còn lại.

Khi nâng cấp, không chỉ đổi tên class. Cần kiểm tra lại retry count, backoff, seek, offset commit, batch semantics, recoverer, DLT và transaction rollback. Một handler mới có thể biên dịch thành công nhưng vẫn làm thay đổi số lần giao lại hoặc thời điểm commit offset nếu cấu hình cũ được chuyển không chính xác.

## 1. Phân biệt listener error handler và container error handler

Spring Kafka có hai tầng xử lý lỗi khác nhau:

| Tầng | Cấu hình | Phạm vi |
|---|---|---|
| Listener-level | `@KafkaListener(errorHandler = "...")` và `KafkaListenerErrorHandler` | Xử lý lỗi gắn với một listener method, nhận `Message<?>` đã convert và `ListenerExecutionFailedException` |
| Container-level | `CommonErrorHandler` trên listener container/factory | Điều khiển retry, redelivery, seek, recover, commit offset và lỗi phát sinh ngoài listener invocation |

Listener-level error handler có từ Spring Kafka 2.0. Nó phù hợp khi một listener cần tạo failure response, bổ sung log hoặc áp dụng logic riêng ở tầng message đã convert. Handler này không thay thế container error handler. Nếu muốn container retry hoặc gửi DLT theo cơ chế chuẩn, listener-level handler cần ném lại exception để container xử lý.

Container-level error handler chịu trách nhiệm điều phối consumer. Đây là phần API thay đổi đáng chú ý giữa các phiên bản 2.x, 3.x và 4.x.

## 2. Dòng thời gian thay đổi chính

| Phiên bản Spring Kafka | Thay đổi liên quan error handling |
|---|---|
| 2.0 | Bổ sung `errorHandler` trên `@KafkaListener` để dùng `KafkaListenerErrorHandler` |
| 2.2 | Bổ sung `DeadLetterPublishingRecoverer`, mở rộng khả năng publish record lỗi sang dead-letter topic |
| 2.5 | `DefaultAfterRollbackProcessor`/error handler hỗ trợ delivery attempt metadata; `RecoveringBatchErrorHandler` là một lựa chọn cho batch listener |
| 2.7 | Có non-blocking retry bằng retry topics; converter có thể đưa raw record vào `KafkaHeaders.RAW_DATA` từ 2.7 |
| 2.8 | Giới thiệu `CommonErrorHandler`, `DefaultErrorHandler` và các handler chung cho record/batch; setter factory legacy được deprecated, interface cũ vẫn được giữ để tương thích |
| 2.9 | Bổ sung `seekAfterError=false`, `BackOffHandler`; đổi API custom handler từ `handleRecord`/`remainingRecords` sang `handleOne`/`seeksAfterHandling` và đặt một số default retry-state mới |
| 3.x | Tiếp tục dùng `CommonErrorHandler`; các API legacy bị đánh dấu deprecated for removal; bổ sung khả năng retry listener cho batch và các cải tiến observation/lifecycle theo từng minor |
| 4.x | Vẫn dùng `CommonErrorHandler`/`DefaultErrorHandler` cho listener container thông thường; kiểm tra migration guide và API của minor version trước khi nâng cấp |

Các mốc trên là những thay đổi tiêu biểu, không phải danh sách đầy đủ mọi thay đổi của từng minor release. Luôn đối chiếu đúng phiên bản Spring Kafka thực tế mà Spring Boot dependency management đang chọn.

## 3. Cách xử lý lỗi trong các phiên bản trước 2.8

Trước 2.8, Spring Kafka tách handler theo kiểu listener. Record listener dùng `ErrorHandler` và các sub-interface như `ConsumerAwareErrorHandler`; batch listener dùng `BatchErrorHandler` cùng các biến thể consumer-aware/container-aware.

Một số class thường gặp:

| Handler cũ | Mục đích |
|---|---|
| `LoggingErrorHandler` | Ghi log lỗi record và tiếp tục theo hành vi container |
| `BatchLoggingErrorHandler` | Ghi log lỗi batch |
| `SeekToCurrentErrorHandler` | Seek về record lỗi để giao lại sau retry |
| `SeekToCurrentBatchErrorHandler` | Retry batch bằng seek |
| `RecoveringBatchErrorHandler` | Retry batch và gọi recoverer khi hết retry |
| `RetryingBatchErrorHandler` | Retry batch theo chiến lược riêng |
| `ContainerStoppingErrorHandler` | Dừng listener container khi có lỗi |
| `ConditionalDelegatingErrorHandler` | Chọn handler theo loại exception |

Ở các bản cũ, factory có thể được cấu hình bằng `setErrorHandler(...)` cho record listener và `setBatchErrorHandler(...)` cho batch listener. Hai cấu hình riêng khiến việc dùng chung một factory cho cả record và batch listener khó thống nhất.

Ví dụ cấu hình kiểu cũ:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setErrorHandler(
            new SeekToCurrentErrorHandler(new FixedBackOff(1_000L, 2L)));
    return factory;
}
```

Đây là ví dụ cho codebase cũ; `SeekToCurrentErrorHandler` không còn là lựa chọn nên dùng khi nâng cấp lên 2.8+. Cần chuyển sang `DefaultErrorHandler` và `setCommonErrorHandler(...)`.

## 4. Từ 2.8: CommonErrorHandler thống nhất record và batch

Spring Kafka 2.8 giới thiệu `CommonErrorHandler`, thay thế hai interface `ErrorHandler` và `BatchErrorHandler` cho listener container. Một factory có thể dùng cùng một common handler cho record listener và batch listener.

Các implementation được cung cấp gồm:

| Common handler | Vai trò |
|---|---|
| `DefaultErrorHandler` | Retry record/batch, seek hoặc redeliver, gọi recoverer khi hết retry |
| `CommonLoggingErrorHandler` | Chỉ ghi log lỗi; các record còn lại được xử lý theo semantics của handler |
| `CommonContainerStoppingErrorHandler` | Dừng container khi listener lỗi |
| `CommonDelegatingErrorHandler` | Chọn handler delegate theo loại exception |
| `CommonMixedErrorHandler` | Dùng một handler cho record listener và handler khác cho batch listener |

Trong 2.8, các interface legacy vẫn được giữ để tương thích; các setter factory như `setErrorHandler(...)` và `setBatchErrorHandler(...)` đã được deprecated để chuyển sang `setCommonErrorHandler(...)`. Từ 3.0, các interface legacy như `ErrorHandler` và `BatchErrorHandler` được đánh dấu deprecated for removal. Khi viết code mới hoặc refactor để nâng cấp, nên dùng `CommonErrorHandler`.

## 5. Chuyển SeekToCurrentErrorHandler sang DefaultErrorHandler

`DefaultErrorHandler` là thay thế trực tiếp phổ biến nhất cho `SeekToCurrentErrorHandler`. Nó kế thừa cơ chế retry/recovery của failed record processor và hỗ trợ cả record listener lẫn batch listener.

Ví dụ cấu hình mới:

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    return factory;
}
```

`FixedBackOff(1_000L, 2L)` có nghĩa chờ 1 giây giữa các lần thử và cho phép 2 lần retry sau lần giao đầu tiên: tổng cộng tối đa 3 lần listener nhận record trước khi recover. Tham số thứ hai là số lần retry thêm, không phải tổng số delivery attempt.

Nếu chỉ dùng `new DefaultErrorHandler()` thì default backoff hiện hành tương ứng 9 lần retry, không delay, sau lần giao đầu tiên; record được recover bằng cách log khi hết retry. Đừng mặc định rằng cấu hình không tham số tương đương với retry policy nghiệp vụ của ứng dụng.

## 6. Bảng chuyển đổi handler legacy

Các thay thế được Spring Kafka tài liệu hóa:

| Legacy handler | Handler thay thế |
|---|---|
| `LoggingErrorHandler` | `CommonLoggingErrorHandler` |
| `BatchLoggingErrorHandler` | `CommonLoggingErrorHandler` |
| `ConditionalDelegatingErrorHandler` | `CommonDelegatingErrorHandler` |
| `ConditionalDelegatingBatchErrorHandler` | `CommonDelegatingErrorHandler` |
| `ContainerStoppingErrorHandler` | `CommonContainerStoppingErrorHandler` |
| `ContainerStoppingBatchErrorHandler` | `CommonContainerStoppingErrorHandler` |
| `SeekToCurrentErrorHandler` | `DefaultErrorHandler` |
| `RecoveringBatchErrorHandler` | `DefaultErrorHandler` |
| `SeekToCurrentBatchErrorHandler` | Không có class thay thế trực tiếp; dùng `DefaultErrorHandler` với infinite `BackOff` nếu muốn retry không giới hạn |
| `RetryingBatchErrorHandler` | Không có class thay thế trực tiếp; dùng `DefaultErrorHandler` và ném exception khác `BatchListenerFailedException` để kích hoạt retry toàn batch |

Không thay tên class một cách máy móc. Ví dụ `RetryingBatchErrorHandler` có thể đã retry toàn bộ batch theo semantics riêng; `DefaultErrorHandler` phân biệt `BatchListenerFailedException` (biết record lỗi) với exception khác (fallback retry complete batch). Phải kiểm tra lại listener code để chọn đúng semantics.

## 7. Chuyển cấu hình factory sang setCommonErrorHandler

Với code tự tạo listener container factory, thay setter cũ bằng `setCommonErrorHandler(...)`:

```java
// Cũ: Spring Kafka trước 2.8
factory.setErrorHandler(oldRecordErrorHandler);
factory.setBatchErrorHandler(oldBatchErrorHandler);

// Mới: Spring Kafka 2.8+
factory.setCommonErrorHandler(defaultErrorHandler);
```

Khi có cả record và batch listener dùng chung factory, `DefaultErrorHandler` có thể xử lý cả hai. Nếu hai loại listener cần chiến lược khác nhau, dùng `CommonMixedErrorHandler` hoặc tách listener container factory theo mục đích.

Không cấu hình đồng thời các setter legacy và common handler trên cùng factory rồi kỳ vọng chúng cộng dồn. Khi migration, loại bỏ cấu hình cũ sau khi common handler đã được gắn và kiểm thử.

## 8. Spring Boot auto-configuration và custom factory

Nếu dùng listener factory do Spring Boot auto-configure, có thể khai báo một bean `CommonErrorHandler`; Boot sẽ gắn bean đó vào factory auto-configured theo cơ chế hỗ trợ của Spring Kafka.

```java
@Bean
CommonErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
    var handler = new DefaultErrorHandler(
            recoverer, new FixedBackOff(500L, 3L));
    handler.addNotRetryableExceptions(InvalidOrderException.class);
    return handler;
}
```

Nếu ứng dụng tự khai báo `ConcurrentKafkaListenerContainerFactory`, hãy gọi `factory.setCommonErrorHandler(handler)` trực tiếp như phần trước. Không giả định bean error handler tự được gắn vào mọi factory tùy chỉnh.

Với nhiều factory, nên đặt tên bean rõ ràng và cấu hình handler theo từng factory. Một factory dành cho event có thể cần retry ngắn; factory khác cho batch import có thể cần retry toàn batch hoặc dừng container để bảo toàn dữ liệu.

## 9. Khác biệt API custom CommonErrorHandler giữa 2.8 và 2.9+

Đây là thay đổi dễ gây lỗi source compatibility khi nâng từ 2.8 lên 2.9 hoặc 3.x.

### Spring Kafka 2.8

Trong API 2.8, custom `CommonErrorHandler` có các method:

- `handleRecord(...)`: xử lý riêng record lỗi khi `remainingRecords()` trả về `false`.
- `handleRemaining(...)`: xử lý record lỗi cùng các record còn lại của poll khi `remainingRecords()` trả về `true`.
- `remainingRecords()`: cho biết handler nhận riêng record lỗi hay toàn bộ phần còn lại.
- `handleBatch(...)`: xử lý lỗi batch listener.
- `handleOtherException(...)`: xử lý lỗi không gắn với một record cụ thể, ví dụ exception phát sinh trong `poll()`.

### Spring Kafka 2.9 trở lên

Từ 2.9, API được đổi tên để diễn tả semantics rõ hơn:

| API 2.8 | API 2.9+ | Ý nghĩa |
|---|---|---|
| `handleRecord(...)` | `handleOne(...)` | Xử lý riêng record lỗi |
| `remainingRecords()` | `seeksAfterHandling()` | Handler có tự seek record lỗi/record còn lại hay không |
| `handleRemaining(...)` | `handleRemaining(...)` | Vẫn dùng khi handler tự xử lý danh sách record còn lại |
| `handleBatch(...)` | `handleBatch(...)` | Xử lý lỗi batch |
| `handleOtherException(...)` | `handleOtherException(...)` | Xử lý lỗi không có record |

Các method cũ `handleRecord()` và `remainingRecords()` được deprecated từ 2.9, thay bằng `handleOne()` và `seeksAfterHandling()`. Vì vậy, custom handler viết cho 2.8 có thể vẫn compile trong một số bản 2.9 nhờ method deprecated, nhưng nên được chuyển sang API mới trước khi nâng tiếp.

## 10. Chuyển custom ErrorHandler record-only

Nếu custom handler cũ implement `ErrorHandler` hoặc `ConsumerAwareErrorHandler`, migration trong 2.8 thường là implement `handleRecord(...)` và `handleOtherException(...)`. Nếu handler chỉ xử lý record lỗi, `remainingRecords()` giữ `false` (mặc định).

Ví dụ khung cho API 2.8:

```java
class AuditCommonErrorHandler implements CommonErrorHandler {

    @Override
    public void handleRecord(
            Exception exception,
            ConsumerRecord<?, ?> record,
            Consumer<?, ?> consumer,
            MessageListenerContainer container) {

        auditService.recordFailure(record, exception);
        throw new KafkaException("Record chưa được recover", exception);
    }

    @Override
    public void handleOtherException(
            Exception exception,
            Consumer<?, ?> consumer,
            MessageListenerContainer container,
            boolean batchListener) {

        throw new KafkaException("Lỗi consumer ngoài listener", exception);
    }
}
```

Đây là khung minh họa cho nhánh 2.8; `auditService` là dependency cần inject trong ứng dụng thật. Handler ghi audit rồi ném exception để container không xem record là đã xử lý thành công. Nếu muốn recover/skip record, cần có quy tắc commit/recovery rõ ràng, không chỉ log rồi return.

Trong 2.9+, thay `handleRecord(...)` bằng `handleOne(...)` và trả `false` nếu muốn container gửi lại record lỗi cho listener sau khi handler kết thúc, hoặc `true` nếu handler đã xử lý/recover record. Ví dụ khung API mới:

```java
class AuditCommonErrorHandler implements CommonErrorHandler {

    @Override
    public boolean handleOne(
            Exception exception,
            ConsumerRecord<?, ?> record,
            Consumer<?, ?> consumer,
            MessageListenerContainer container) {

        auditService.recordFailure(record, exception);
        return false; // container sẽ resubmit record lỗi
    }

    @Override
    public void handleOtherException(
            Exception exception,
            Consumer<?, ?> consumer,
            MessageListenerContainer container,
            boolean batchListener) {

        throw new KafkaException("Lỗi consumer ngoài listener", exception);
    }
}
```

Không dùng hai đoạn code này như một class duy nhất đa version: signature và semantics return khác nhau. Hãy biên dịch với đúng Spring Kafka dependency của nhánh đang nâng cấp.

## 11. Chuyển RemainingRecordsErrorHandler

Legacy `RemainingRecordsErrorHandler` nhận danh sách record chưa xử lý và thường tự seek để những record đó được poll lại.

Trong API 2.8:

- Implement `handleRemaining(...)`.
- Override `remainingRecords()` trả `true`.
- Implement `handleOtherException(...)` cho lỗi không có record.

Trong API 2.9+:

- Tiếp tục implement `handleRemaining(...)`.
- Override `seeksAfterHandling()` trả `true` vì handler tự thực hiện seek.
- Implement `handleOtherException(...)`.

Nếu handler không tự seek mà muốn container quản lý redelivery, hãy dùng semantics record-only (`handleRecord`/`handleOne`) thay vì khai báo sai rằng handler tự seek. Việc báo sai semantics có thể khiến record bị bỏ qua hoặc bị giao lại sai thứ tự.

## 12. Chuyển custom BatchErrorHandler

Custom `BatchErrorHandler` được chuyển sang `CommonErrorHandler` bằng cách implement `handleBatch(...)` và `handleOtherException(...)`. Batch handler nhận toàn bộ `ConsumerRecords` từ một lần poll; nếu muốn retry một record cụ thể, nên dùng `BatchListenerFailedException` ở listener và để `DefaultErrorHandler` xử lý.

Nếu tự implement `handleBatch`, cần xác định rõ:

- Có seek các partition về offset nào?
- Có retry toàn bộ batch hay chỉ phần còn lại?
- Khi recover record lỗi, offset record đó được commit ở đâu?
- Nếu publish DLT thất bại, record có được giao lại không?
- Consumer có được pause/resume đúng cách trong backoff không?
- Batch listener có đang chạy transaction không?

Không tự gọi seek trong listener-level `KafkaListenerErrorHandler`; container không biết seek đã xảy ra. Với container-level `CommonErrorHandler`, nếu tự điều khiển seek thì phải khai báo đúng `seeksAfterHandling()` và xử lý cả record còn lại.

## 13. DefaultErrorHandler và seekAfterError

Mặc định, `DefaultErrorHandler` dùng seek để yêu cầu consumer đọc lại record lỗi và các record còn lại cần redeliver. Từ Spring Kafka 2.9, có thể đặt `seekAfterError=false`.

Khi `seekAfterError=false`:

1. Container giữ lại các record chưa xử lý.
2. Error handler xác định record nào cần gửi lại listener.
3. Container thực hiện một lần poll có pause để giữ consumer/group sống.
4. Các record còn lại được gửi lại listener mà không seek consumer tới offset cũ.

Chế độ này có thể hữu ích khi không muốn thay đổi consumer position bằng seek, nhưng nó không làm mất chi phí retry và không tự giải quyết duplicate side effect. Hãy kiểm thử cả record listener, batch listener và thời gian pause trước khi bật.

```java
DefaultErrorHandler handler =
        new DefaultErrorHandler(new FixedBackOff(500L, 2L));
handler.setSeekAfterError(false); // Spring Kafka 2.9+
```

Không copy `setSeekAfterError(false)` vào code 2.8; thuộc tính này được bổ sung từ 2.9.

## 14. BackOffHandler và retry delay dài

Trước 2.9, error handler thường chờ backoff trên consumer thread. Từ 2.9, có thể cấu hình `BackOffHandler`; framework cung cấp `ContainerPausingBackOffHandler` để pause container trong khoảng backoff thay vì giữ thread ngủ toàn bộ thời gian.

```java
@Bean
ListenerContainerPauseService listenerContainerPauseService(
        ListenerContainerRegistry registry,
        TaskScheduler taskScheduler) {

    return new ListenerContainerPauseService(registry, taskScheduler);
}

@Bean
DefaultErrorHandler longBackOffErrorHandler(
        ConsumerRecordRecoverer recoverer,
        ListenerContainerPauseService pauseService) {

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(60_000L, 2L),
            new ContainerPausingBackOffHandler(pauseService));
}
```

Đây là ví dụ cho backoff dài 60 giây. `ListenerContainerPauseService` cần một `TaskScheduler` và registry listener container; hãy bảo đảm ứng dụng có scheduler phù hợp. Thời gian pause thực tế có độ phân giải phụ thuộc `pollTimeout`; container cần tiếp tục poll phù hợp để duy trì membership. `ContainerPausingBackOffHandler` hữu ích khi delay dài hơn `max.poll.interval.ms`, nhưng phải kiểm tra thời gian xử lý, heartbeat và rebalance trong môi trường thật.

## 15. Thay đổi retry state khi exception type thay đổi

Retry state được theo dõi theo record/partition/offset. Từ Spring Kafka 2.9, `resetStateOnExceptionChange` mặc định là `true` cho failed record processor: nếu loại exception thay đổi giữa các lần delivery, retry sequence được khởi động lại và có thể chọn backoff mới.

Trong các phiên bản trước 2.9, exception type không được xét theo mặc định. Nếu nâng cấp mà ứng dụng dựa vào việc retry counter tiếp tục bất kể exception type, hãy kiểm tra lại hành vi và cân nhắc đặt rõ:

```java
handler.setResetStateOnExceptionChange(false);
```

Đối với batch processor, default có thể khác failed record processor ở một số phiên bản mới hơn để giữ backward compatibility. Kiểm tra Javadoc và change history của version cụ thể trước khi kỳ vọng cùng một default cho record và batch.

## 16. Phân loại exception retryable và non-retryable

`DefaultErrorHandler` mặc định xem một số lỗi là fatal vì retry thường không sửa được dữ liệu sai hoặc contract không khớp. Các exception mặc định không retry gồm:

- `DeserializationException`
- `MessageConversionException`
- `ConversionException`
- `MethodArgumentResolutionException`
- `NoSuchMethodException`
- `ClassCastException`

Với các lỗi này, recoverer được gọi ngay trong lần thất bại đầu tiên. Có thể bổ sung exception nghiệp vụ vào nhóm không retry:

```java
DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 3L));

handler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class);
```

Nếu muốn định nghĩa toàn bộ classification, dùng `setClassifications(...)` với map và default classification phù hợp. Tránh cấu hình mọi exception thành retryable: lỗi validation vĩnh viễn sẽ giữ partition bận và làm tăng lag.

Phân biệt exception kỹ thuật tạm thời (database timeout, service unavailable) với lỗi dữ liệu/contract (field thiếu, event version không hỗ trợ). Retry chỉ có ích với loại lỗi có khả năng tự hết sau một khoảng thời gian.

## 17. Retry count và default behavior

Đọc đúng ý nghĩa tham số `BackOff` khi nâng cấp:

| Cấu hình | Tổng số lần listener có thể nhận record |
|---|---:|
| `new FixedBackOff(0L, 0L)` | 1 lần, không retry |
| `new FixedBackOff(1_000L, 2L)` | 3 lần: 1 lần đầu + 2 retry |
| `new FixedBackOff(1_000L, 5L)` | 6 lần: 1 lần đầu + 5 retry |
| `FixedBackOff.UNLIMITED_ATTEMPTS` | Retry không giới hạn |

Khi hết retry, recoverer được gọi. Nếu dùng constructor không tham số của `DefaultErrorHandler`, default backoff trong các phiên bản hiện hành thường là 9 retry, không delay, rồi gọi recoverer mặc định để log record.

Nếu trước đây `SeekToCurrentErrorHandler` được cấu hình max failures, hãy quy đổi sang số retry thêm chứ không copy số nguyên trực tiếp mà không xác định cách tính của constructor cũ.

## 18. Recoverer và DeadLetterPublishingRecoverer

Khi retry hết, recoverer quyết định record lỗi sẽ đi đâu. `DefaultErrorHandler` có thể nhận `ConsumerRecordRecoverer`, ví dụ `DeadLetterPublishingRecoverer` để publish record sang dead-letter topic.

```java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate,
                (record, exception) ->
                        new TopicPartition(
                                record.topic() + ".dlt",
                                record.partition()));

DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L));
```

Resolver ở trên đưa record vào `<source-topic>.dlt` cùng partition với source. Nếu dùng cách định tuyến mặc định của `DeadLetterPublishingRecoverer`, tên topic mặc định là `<source-topic>-dlt` và partition đích là partition nguồn. Vì vậy, DLT cần có ít nhất số partition bằng topic nguồn khi giữ nguyên partition number.

Record DLT thường mang metadata nguồn như original topic, partition, offset, timestamp và exception headers. Giữ các header này để điều tra, replay hoặc sửa dữ liệu. Nếu DLT topic dùng partition count nhỏ hơn source mà resolver yêu cầu cùng partition, publish sẽ thất bại.

## 19. Recovery thất bại cũng phải được tính vào migration

Nếu recoverer ném exception, record lỗi không được xem là recovered thành công. Record sẽ được đưa vào đường redelivery/seek theo handler. Từ 2.5.5, khi recovery thất bại, backoff state được reset mặc định để các lần delivery tiếp theo lại đi qua backoff trước khi thử recovery.

Để quay lại behavior cũ (không reset backoff sau recovery failure), có thể cấu hình:

```java
handler.setResetStateOnRecoveryFailure(false);
```

Không đánh dấu offset đã xử lý chỉ vì recoverer đã được gọi. Hãy kiểm tra kết quả gửi DLT và chính sách commit offset sau khi publish thành công.

## 20. AckAfterHandle và commitRecovered

Hai thuộc tính này giải quyết hai câu hỏi khác nhau:

- `ackAfterHandle`: container có commit offset khi error handler return bình thường (đã xem lỗi là handled) hay không. Mặc định là `true`.
- `commitRecovered`: cho phép commit offset của record đã recover khi dùng `AckMode.MANUAL_IMMEDIATE`; cần cấu hình rõ khi dùng manual immediate.

Ví dụ:

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(1_000L, 2L));
handler.setAckAfterHandle(true);
handler.setCommitRecovered(true);
```

Không bật `commitRecovered` chỉ vì listener dùng `MANUAL`; thuộc tính này được dùng cho `MANUAL_IMMEDIATE`. Nếu handler không ném exception sau khi recover, offset commit còn phụ thuộc `ackAfterHandle` và container AckMode. Hãy test committed offset, không chỉ test rằng recoverer đã được gọi.

## 21. Batch listener: BatchListenerFailedException

Với batch listener, framework không tự biết record nào trong batch làm listener thất bại nếu listener chỉ ném exception chung. Để `DefaultErrorHandler` xử lý từng record, listener nên ném `BatchListenerFailedException` kèm record lỗi hoặc index của record lỗi.

```java
@KafkaListener(topics = "orders", containerFactory = "batchFactory")
public void listen(List<ConsumerRecord<String, OrderEvent>> records) {
    for (ConsumerRecord<String, OrderEvent> record : records) {
        try {
            orderService.process(record.value());
        }
        catch (Exception ex) {
            throw new BatchListenerFailedException(
                    "Không xử lý được order", ex, record);
        }
    }
}
```

Khi xác định được record lỗi, `DefaultErrorHandler` có thể commit các record trước đó, retry record lỗi và phần còn lại; khi hết retry, recover record lỗi rồi tiếp tục với record phía sau. Với POJO batch listener không có `ConsumerRecord`, truyền index record lỗi vào `BatchListenerFailedException`.

Nếu batch listener ném exception khác `BatchListenerFailedException`, handler dùng fallback retry complete batch. Batch được giữ trong memory và listener được gọi lại; không đảm bảo batch redelivery có cùng số record hoặc cùng thứ tự trong mọi trường hợp khi đọc lại từ broker.

## 22. Khác biệt retry toàn batch và retry một record

| Cách listener báo lỗi | Hành vi `DefaultErrorHandler` |
|---|---|
| Ném `BatchListenerFailedException` có record/index | Xác định điểm lỗi; commit phần trước, retry phần lỗi/còn lại, recover record lỗi khi hết retry |
| Ném exception khác | Fallback retry complete batch trong memory; khi hết retry, recover các record của batch |
| Recoverer thất bại | Không xem record là recovered; batch/record được giao lại theo error handler |

Fallback batch handler pause consumer, tiếp tục poll để giữ consumer sống trong backoff và gọi lại listener với batch đang giữ. Cơ chế retry complete batch này không dùng được với transaction. Nếu ứng dụng cần transaction, hãy thiết kế rollback/retry qua `AfterRollbackProcessor`.

## 23. Delivery attempt header

Từ Spring Kafka 2.5, error handler hỗ trợ delivery attempt metadata qua `KafkaHeaders.DELIVERY_ATTEMPT`. Header này tăng dần từ 1 và chỉ được thêm khi container property `deliveryAttemptHeader` được bật.

Với raw `ConsumerRecord`, giá trị header được mã hóa thành 4 byte; có thể đọc bằng:

```java
int attempt = ByteBuffer.wrap(record.headers()
        .lastHeader(KafkaHeaders.DELIVERY_ATTEMPT).value())
        .getInt();
```

Với `@KafkaListener`, nếu header mapper hỗ trợ, có thể inject:

```java
public void listen(
        OrderEvent event,
        @Header(KafkaHeaders.DELIVERY_ATTEMPT) int attempt) {
    // log attempt hoặc bổ sung metric
}
```

Từ 3.3, batch listener muốn đưa delivery attempt vào `ConsumerRecord` cần đăng ký `DeliveryAttemptAwareRetryListener` làm retry listener của `DefaultErrorHandler`. Không giả định batch listener nhận header theo cùng cách record listener ở các version cũ.

## 24. Retry listener và quan sát recovery

`RetryListener` nhận thông báo khi record/batch thất bại, được recovered hoặc recovery thất bại. Từ 2.8.10, các callback cho batch listener cũng được bổ sung.

```java
DefaultErrorHandler handler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(1_000L, 2L));

handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {
        metrics.retryFailed(record.topic(), exception.getClass().getSimpleName());
    }

    @Override
    public void recovered(ConsumerRecord<?, ?> record, Exception exception) {
        metrics.recovered(record.topic());
    }

    @Override
    public void recoveryFailed(
            ConsumerRecord<?, ?> record,
            Exception original,
            Exception recoveryFailure) {
        metrics.recoveryFailed(record.topic());
    }
});
```

Ví dụ minh họa; `metrics` là service ứng dụng. Khi nâng cấp, kiểm tra interface của version vì callback batch được thêm từ 2.8.10 và các minor sau có thể mở rộng thêm API.

## 25. Retry blocking và non-blocking retry topics

`DefaultErrorHandler` thực hiện retry trong luồng xử lý consumer; thường gọi là blocking retry. Consumer/partition bị ảnh hưởng bởi thời gian backoff và retry. Non-blocking retry được giới thiệu từ Spring Kafka 2.7 qua `@RetryableTopic`/retry topics: record được publish sang retry topic có delay rồi được xử lý lại bởi listener khác.

Hai cơ chế giải quyết các bài toán khác nhau:

| Đặc điểm | `DefaultErrorHandler` | `@RetryableTopic` |
|---|---|---|
| Retry | Trong consumer flow của topic hiện tại | Publish sang retry topic rồi consume lại sau delay |
| Ordering | Có thể giữ thứ tự partition khi retry blocking | Có thể thay đổi thứ tự giữa các event cùng key |
| Tác động partition | Partition có thể bị giữ lại trong retry | Event lỗi được tách sang topic khác |
| Dùng batch listener | Có | Không hỗ trợ batch listener |
| Phù hợp | Lỗi ngắn, cần giữ ordering | Delay dài, chấp nhận non-blocking và ordering thay đổi |

Không chuyển toàn bộ `DefaultErrorHandler` sang `@RetryableTopic` chỉ để tránh block. Hãy đánh giá thứ tự event, retry topic topology, retention, DLT, số consumer và khả năng replay.

## 26. Transaction và AfterRollbackProcessor

Khi listener container dùng Kafka transaction, mặc định Spring Kafka không cấu hình container error handler để nuốt exception; exception được ném ra để transaction rollback. Việc xử lý sau rollback thuộc `AfterRollbackProcessor`, thường là `DefaultAfterRollbackProcessor`.

Nếu gắn custom `CommonErrorHandler` vào transactional container và handler return bình thường, container có thể coi lỗi đã được xử lý và transaction không rollback như mong muốn. Nếu muốn rollback, custom handler phải ném exception ra ngoài.

Luồng cơ bản:

```text
Listener xử lý record
       |
       +-- thành công --> commit transaction và offset
       |
       +-- exception --> rollback transaction
                         |
                         v
                  AfterRollbackProcessor
                         |
                         +--> redelivery/retry
                         |
                         +--> recover/DLT khi hết retry
```

Không dùng retry fallback batch in-memory như một cơ chế thay thế transaction rollback; tài liệu Spring Kafka nêu rõ fallback batch retry không dùng được với transactions.

## 27. Listener-level KafkaListenerErrorHandler

`KafkaListenerErrorHandler` không bị thay thế bởi `CommonErrorHandler`. Nó vẫn là handler cấp method và được chọn qua thuộc tính `errorHandler` trên `@KafkaListener`.

```java
@Component
public class OrderListenerErrorHandler implements KafkaListenerErrorHandler {

    @Override
    public Object handleError(
            Message<?> message,
            ListenerExecutionFailedException exception) throws Exception {

        // Ghi context ở tầng application rồi để container retry/recover.
        throw exception;
    }
}

@KafkaListener(
        topics = "orders",
        errorHandler = "orderListenerErrorHandler")
public void listen(OrderEvent event) {
    orderService.process(event);
}
```

Nếu listener-level handler trả về bình thường thay vì ném lỗi, exception có thể không tiếp tục tới container; khi đó container không thực hiện retry theo cách bạn mong đợi. Giá trị return của `KafkaListenerErrorHandler` bị bỏ qua; handler thường dùng để ném exception gốc hoặc exception mới.

Không gọi `consumer.seek(...)` trong `KafkaListenerErrorHandler` hoặc các biến thể consumer-aware của nó. Container không biết seek được thực hiện bên trong handler và có thể quản lý offset sai.

## 28. Poll-level exception và handleOtherException

Không phải mọi lỗi đều gắn với một `ConsumerRecord`. Ví dụ consumer `poll()` có thể ném exception trước khi trả về record. `CommonErrorHandler.handleOtherException(...)` xử lý nhóm lỗi này.

Khi migrate custom handler, không chỉ implement `handleOne()`/`handleRemaining()`/`handleBatch()` rồi bỏ `handleOtherException()`. Cần có chính sách cho lỗi consumer-level: log và dừng container, ném exception để container dừng, hoặc xử lý theo khả năng phục hồi cụ thể.

Nếu không có record, không thể gửi record cụ thể sang DLT theo cách recoverer thông thường. Hãy phân biệt lỗi poll/network/authorization với lỗi listener trên một record.

## 29. Deserialization failure và ErrorHandlingDeserializer

Deserialization có thể thất bại trước khi listener nhận được payload. Nếu muốn error handler có thể xử lý record lỗi và publish DLT, thường cần bọc deserializer thật bằng `ErrorHandlingDeserializer` để exception được đưa vào header thay vì làm `poll()` dừng mà không có record bình thường.

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
```

Ví dụ cấu hình minh họa cho JSON value; cần thêm type mapping/trusted package theo model thực tế. `DefaultErrorHandler` xem các exception deserialization/conversion là fatal mặc định vì retry thường không làm payload sai trở nên hợp lệ. Khi dùng batch listener, ứng dụng cần kiểm tra conversion/deserialization failure header và ném `BatchListenerFailedException` đúng index để handler biết record lỗi.

## 30. Dùng CommonDelegatingErrorHandler sau migration

Nếu trước đây dùng conditional delegating handler, có thể chuyển sang `CommonDelegatingErrorHandler`. Nó chọn handler theo loại exception. Các delegate cần có thuộc tính tương thích như `ackAfterHandle` và `seekAfterError`.

```java
DefaultErrorHandler retryHandler = new DefaultErrorHandler(
        recoverer, new FixedBackOff(500L, 3L));

CommonContainerStoppingErrorHandler stopHandler =
        new CommonContainerStoppingErrorHandler();

Map<Class<? extends Throwable>, CommonErrorHandler> delegates =
        new LinkedHashMap<>();
delegates.put(FatalInfrastructureException.class, stopHandler);

CommonDelegatingErrorHandler handler =
        new CommonDelegatingErrorHandler(retryHandler);
handler.setErrorHandlers(delegates);
```

Ví dụ chọn dừng container cho lỗi hạ tầng nghiêm trọng và dùng retry/recover cho lỗi thông thường. `LinkedHashMap` giúp thứ tự tìm delegate rõ ràng. Hãy đảm bảo các handler có semantics ack/seek tương thích; không ghép handler tự seek với handler không seek mà không hiểu tác động.

## 31. CommonMixedErrorHandler cho record và batch

Nếu cùng một factory phải hỗ trợ record listener và batch listener nhưng mỗi loại cần handler riêng, dùng `CommonMixedErrorHandler`:

```java
CommonErrorHandler recordHandler =
        new DefaultErrorHandler(recordRecoverer, new FixedBackOff(500L, 2L));

CommonErrorHandler batchHandler =
        new DefaultErrorHandler(batchRecoverer, new FixedBackOff(1_000L, 1L));

factory.setCommonErrorHandler(
        new CommonMixedErrorHandler(recordHandler, batchHandler));
```

Hai handler có thể dùng backoff/recoverer khác nhau, nhưng vẫn phải kiểm tra tương thích các thuộc tính chung và behavior của batch listener. Nếu khác biệt quá lớn, tách factory thường dễ vận hành và quan sát hơn.

## 32. Những thay đổi cần rà soát khi nâng 2.7 lên 2.8

Checklist chuyển từ legacy handler sang common handler:

1. Tìm mọi class implement `ErrorHandler`, `BatchErrorHandler` và sub-interface.
2. Tìm nơi gọi `setErrorHandler(...)` hoặc `setBatchErrorHandler(...)`.
3. Thay các handler chuẩn bằng class tương ứng trong bảng migration.
4. Chuyển custom handler sang `CommonErrorHandler`.
5. Implement `handleOtherException(...)` cho lỗi poll/consumer.
6. Kiểm tra handler có xử lý riêng record lỗi hay toàn bộ record còn lại.
7. Kiểm tra `ackAfterHandle` và commit offset sau recovery.
8. Kiểm thử record listener và batch listener riêng.
9. Nếu dùng transaction, xác minh exception vẫn rollback transaction.
10. Chạy test DLT và xác minh partition destination.

## 33. Những thay đổi cần rà soát khi nâng 2.8 lên 2.9/3.x

1. Thay `handleRecord(...)` bằng `handleOne(...)` trong custom handler.
2. Thay `remainingRecords()` bằng `seeksAfterHandling()`.
3. Xem lại `seekAfterError` và quyết định có dùng mode không seek hay không.
4. Kiểm tra `resetStateOnExceptionChange` vì default thay đổi từ 2.9.
5. Nếu backoff dài, cân nhắc `ContainerPausingBackOffHandler`.
6. Kiểm tra `RetryListener` batch callback nếu cần observability.
7. Kiểm tra retry count: số lần retry thêm và tổng delivery attempt.
8. Kiểm tra batch listener có ném `BatchListenerFailedException` đúng record/index.
9. Kiểm tra listener-level error handler không vô tình swallow exception.
10. Chạy lại integration test với broker để xác minh seek/commit thực tế.

## 34. Những thay đổi cần rà soát khi nâng 3.x lên 4.x

Với listener error handling thông thường, `CommonErrorHandler` và `DefaultErrorHandler` vẫn là trọng tâm trong Spring Kafka 4.x. Không nên coi nâng 4.x là lý do để quay lại legacy `ErrorHandler`/`BatchErrorHandler`. Tuy vậy, 4.x đi cùng các thay đổi nền tảng của Spring Framework, Spring Boot, Java và Kafka client; cần nâng theo ma trận tương thích của ứng dụng.

Khi kiểm tra error handling ở 4.x:

- Xác nhận version Spring Kafka được Spring Boot BOM quản lý.
- Biên dịch lại custom `CommonErrorHandler` với API 4.x.
- Kiểm tra các class deprecated/removed trong deprecated list đúng minor version.
- Kiểm tra serializer/deserializer và dependency liên quan vì Jackson 3 là thay đổi đáng chú ý trong dòng 4.x.
- Kiểm tra integration test với broker version tương thích.
- Xác minh transaction rollback, DLT publishing, retry topics và consumer group behavior sau nâng cấp.

Không suy ra API cụ thể đã bị xóa chỉ từ số major. Dùng Javadoc/deprecated list của artifact thực tế để xác định method/class còn tồn tại.

## 35. Ma trận kiểm thử sau migration

| Ca kiểm thử | Điều phải xác minh |
|---|---|
| Record listener thành công | Offset commit theo AckMode hiện tại |
| Record listener lỗi tạm thời | Retry đúng số lần và backoff |
| Exception non-retryable | Recover ngay theo classification |
| Retry hết | Recoverer được gọi đúng một lần cho lần recovery thành công |
| DLT publish thành công | Record có đủ original topic/partition/offset/exception headers |
| DLT publish thất bại | Record chưa bị đánh dấu recovered và được giao lại theo policy |
| BatchListenerFailedException | Commit phần trước, retry/recover record lỗi và phần còn lại |
| Batch exception chung | Fallback retry complete batch đúng semantics |
| `seekAfterError=false` | Record chưa xử lý được resubmit đúng và consumer tiếp tục poll |
| Poll-level exception | `handleOtherException` được gọi và container có behavior dự kiến |
| Manual immediate ack | `commitRecovered` hoạt động đúng nếu bật |
| Transaction rollback | Exception không bị handler nuốt và transaction rollback |
| Listener-level handler | Ném lại exception thì container retry; không seek consumer trực tiếp |
| Retry topic | Thứ tự, delay, retry topic và DLT đúng contract |
| Restart/rebalance | Không mất record; duplicate được xử lý idempotent |

## 36. Lỗi migration thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không compile sau nâng 2.9 | Custom handler còn dùng `handleRecord`/`remainingRecords` | Chuyển sang `handleOne`/`seeksAfterHandling` |
| Factory không nhận handler mới | Vẫn gọi setter legacy hoặc cấu hình nhầm factory | Dùng `setCommonErrorHandler` trên factory thực sự được listener dùng |
| Record bị skip sau khi handler log lỗi | Handler return bình thường, offset được ack sau handle | Chỉ return khi đã recover; nếu chưa xử lý, ném exception hoặc trả semantics resubmit |
| Retry nhiều hơn dự kiến | Nhầm retry count với tổng delivery attempt | Tính lần đầu + số retry thêm |
| DLT publish thất bại liên tục | Topic/partition/serializer/ACL không hợp lệ | Kiểm tra destination resolver, partition count, serializer và quyền WRITE |
| Batch bị retry toàn bộ ngoài ý muốn | Listener ném exception chung thay vì `BatchListenerFailedException` | Chỉ rõ record/index lỗi nếu muốn retry từ record đó |
| Transaction không rollback | Custom handler đã nuốt exception | Ném exception ra để transaction rollback |
| Consumer không nhận lại record sau retry | Khai báo sai seek semantics hoặc commit offset quá sớm | Kiểm tra `seeksAfterHandling`, AckMode và committed offset |
| Retry delay dài gây rebalance | Consumer thread bị giữ trong backoff | Xem `ContainerPausingBackOffHandler`, `max.poll.interval.ms` và poll timeout |
| Listener-level handler không retry | Handler không ném lại exception | Propagate exception tới container-level handler |

## 37. Quy trình migration an toàn

1. Ghi lại Spring Boot, Spring Kafka và Kafka client version hiện tại.
2. Tìm tất cả legacy handler, factory setter và listener-level handler.
3. Liệt kê retry count, backoff, exception classification, recoverer, DLT và AckMode hiện tại.
4. Chọn `DefaultErrorHandler` hoặc common handler tương ứng.
5. Chuyển custom handler theo đúng API của version đích.
6. Cấu hình handler vào đúng factory hoặc bean auto-configured.
7. Kiểm tra transaction và `AfterRollbackProcessor`.
8. Chạy integration test record, batch, DLT, offset và recovery failure.
9. Deploy thử nghiệm với metric retry, DLT, consumer lag và container state.
10. Chỉ loại bỏ dependency/API legacy sau khi xác nhận mọi listener dùng common handler.

## 38. Checklist trước khi hoàn tất nâng cấp

- Đã xác định đúng Spring Kafka version được resolve từ dependency management.
- Không còn custom code phụ thuộc API legacy đã deprecated mà chưa có kế hoạch chuyển đổi.
- Record và batch listener có handler phù hợp.
- Retry count được hiểu là số lần retry thêm sau lần giao đầu.
- `handleOtherException` xử lý lỗi consumer/poll không có record.
- Custom handler dùng đúng API version: 2.8 hay 2.9+.
- Seek behavior và `seekAfterError` đã được kiểm tra.
- Offset commit, `ackAfterHandle` và `commitRecovered` đúng mục đích.
- DLT có đủ partition, serializer và ACL phù hợp.
- Recovery failure không làm mất record.
- Transaction rollback vẫn hoạt động khi listener ném exception.
- Listener-level error handler không vô tình nuốt exception cần retry.
- Batch listener xác định đúng record lỗi bằng `BatchListenerFailedException` nếu cần.
- Retry topics chỉ được dùng khi chấp nhận semantics non-blocking và ordering tương ứng.
- Integration tests xác minh redelivery, offset, DLT và rebalance.
- Có metric/log cho failed delivery, recovered, recovery failed và DLT publish failure.

Thay đổi quan trọng nhất là từ hai họ handler record/batch riêng sang `CommonErrorHandler` kể từ 2.8, sau đó đổi API custom handler từ `handleRecord`/`remainingRecords` sang `handleOne`/`seeksAfterHandling` từ 2.9. Khi nâng cấp, hãy giữ nguyên semantics retry, seek, offset commit, batch và transaction bằng integration test; chỉ đổi class hoặc method sau khi đã xác định chính xác hành vi mà code cũ đang thực hiện.

## Tài liệu tham khảo

- [Spring Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka 2.8 – CommonErrorHandler API](https://docs.spring.io/spring-kafka/docs/2.8.x/api/org/springframework/kafka/listener/CommonErrorHandler.html)
- [Spring Kafka 2.9 – DefaultErrorHandler API](https://docs.spring.io/spring-kafka/docs/2.9.5/api/org/springframework/kafka/listener/DefaultErrorHandler.html)
- [Spring Kafka 3.0 – CommonErrorHandler API](https://docs.spring.io/spring-kafka/docs/3.0.x/api/org/springframework/kafka/listener/CommonErrorHandler.html)
- [Spring Kafka – Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
