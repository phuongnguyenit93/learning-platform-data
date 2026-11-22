# Reset state khi exception thay đổi

Trong Spring Kafka, retry không chỉ là gọi lại listener một số lần. `DefaultErrorHandler` còn phải theo dõi **trạng thái retry của record đang thất bại**: lỗi nào đã xảy ra, `BackOff` đang ở lần chờ thứ mấy, khi nào dừng retry và khi nào chuyển record sang recoverer. Khi exception thay đổi trong những lần xử lý cùng một record, việc tiếp tục sử dụng trạng thái retry cũ có thể khiến ứng dụng bỏ lỡ cơ hội phục hồi hoặc áp dụng sai chính sách phân loại lỗi.

`resetStateOnExceptionChange` là tùy chọn cho phép **khởi tạo lại trạng thái `BackOff` khi loại exception thay đổi giữa các lần thất bại**. Trong các phiên bản Spring Kafka hiện đại, `DefaultErrorHandler` hỗ trợ tùy chọn này qua `setResetStateOnExceptionChange(boolean)`. Spring Kafka 2.9 trở đi sử dụng giá trị mặc định `true`; có thể khai báo tường minh để thể hiện chủ đích của ứng dụng. Với phiên bản cũ, cần đối chiếu API và giá trị mặc định thực tế.

Tính năng này thuộc tầng retry của listener container. Nó không xóa committed offset của consumer group, không gọi `seekToBeginning()`, không đặt lại topic, và không làm một record trở thành record mới trong Kafka. Đối tượng bị reset là **trạng thái theo dõi lỗi và lịch `BackOff` của record trong error handler**.

## 1. Retry state trong `DefaultErrorHandler` là gì?

Khi listener gặp lỗi, Spring Kafka cần nhớ những lần xử lý thất bại để quyết định có thử lại hay không. Với record listener, hệ thống theo dõi lỗi gắn với record đang xử lý và ngữ cảnh topic, partition, offset. `BackOff` quyết định khoảng chờ giữa các lần thử và thời điểm retry đã hết hạn.

Ví dụ:

```java
BackOff backOff = new FixedBackOff(1_000L, 2L);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(recoverer, backOff);
```

`FixedBackOff(1_000L, 2L)` nghĩa là **tối đa hai lần retry sau lần delivery đầu tiên**, mỗi khoảng chờ là 1.000 mili giây. Nếu lỗi vẫn tiếp diễn và không có thay đổi nào làm reset trạng thái, recoverer được gọi sau khi retry hết. `recoverer` là hành động xử lý record sau khi không thể hoàn tất bằng listener, ví dụ chuyển record sang Dead Letter Topic (DLT).

```text
Lần delivery 1: lỗi A
                  |
                  v
            chờ 1.000 ms
                  |
                  v
Lần delivery 2: lỗi A
                  |
                  v
            chờ 1.000 ms
                  |
                  v
Lần delivery 3: lỗi A
                  |
                  v
             recoverer
```

Các lần retry là các lần gọi listener lại theo cơ chế của error handler, không phải producer gửi lại record lên Kafka. Nên phân biệt số lần delivery của listener với số lần producer retry request ghi lên broker.

Trạng thái theo dõi retry nằm ở phía ứng dụng/container, không phải thông tin được Kafka lưu bền vững cùng committed offset. Nếu tiến trình dừng, record chưa được commit có thể được consumer group giao lại sau restart và bắt đầu một chu kỳ retry mới. Vì vậy, retry budget trong bộ nhớ không phải giới hạn toàn cục tồn tại xuyên qua mọi lần khởi động.

## 2. Khi exception đổi loại, điều gì cần xảy ra?

Một record có thể thất bại vì nhiều lý do trong các lần delivery khác nhau. Chẳng hạn lần đầu gọi database bị timeout; lần sau database đã phản hồi nhưng service phát hiện event vi phạm business invariant. Nguyên nhân mới cần một quyết định mới.

| Lần xử lý | Exception | Diễn giải |
|---:|---|---|
| 1 | `InventoryTimeoutException` | Dịch vụ tồn kho tạm không trả lời |
| 2 | `InventoryTimeoutException` | Lỗi cũ vẫn tiếp diễn |
| 3 | `InvalidReservationException` | Kết nối đã phục hồi nhưng dữ liệu đặt chỗ không hợp lệ |

Nếu giữ trạng thái của `InventoryTimeoutException`, error handler có thể đang ở cuối retry budget khi nhận `InvalidReservationException`. Nhưng hai loại lỗi có tính chất khác nhau: một lỗi có thể retry, lỗi còn lại có thể phải đưa thẳng vào DLT.

Khi bật `resetStateOnExceptionChange`, một thay đổi về loại exception làm **bắt đầu lại chuỗi `BackOff` cho loại lỗi mới**. Khi kết hợp với exception classification, error handler có thể áp dụng quyết định retry/recover phù hợp với loại lỗi mới. Nếu exception mới được phân loại là not-retryable, ứng dụng không nên trì hoãn bằng những lần retry không có ích.

Sơ đồ khái niệm:

```text
Record orders-0, offset 205
           |
           v
Listener thất bại: exception A
           |
           v
BackOff đang theo dõi lỗi A
           |
           v
Listener thất bại lần sau
           |
           v
Exception hiện tại có cùng loại A?
           |
     +-----+------+
     |            |
    Có           Không
     |            |
     v            v
Tiếp tục     Reset trạng thái
BackOff       BackOff cho lỗi mới
     |            |
     +-----+------+
           |
           v
    Retry hoặc recover
    theo classification
```

“Thay đổi exception” ở đây nói về **loại exception** được cơ chế theo dõi lỗi sử dụng; không phải chỉ thay đổi câu chữ trong `getMessage()` hoặc tạo instance mới cùng class. Khi lỗi được wrap qua nhiều lớp exception, cần kiểm tra cơ chế truy xuất cause của phiên bản Spring Kafka đang dùng để bảo đảm loại exception quan trọng thực sự được nhận diện.

## 3. Bật `resetStateOnExceptionChange` bằng Java configuration

Ví dụ một ứng dụng xử lý sự kiện đặt hàng có hai nhóm lỗi: lỗi dependency tạm thời có thể retry và lỗi dữ liệu xác định không thể retry. Error handler sử dụng retry hữu hạn, đưa record lỗi sang DLT và reset trạng thái khi loại exception đổi.

```java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltKafkaTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    // Recovery phải báo lỗi nếu publish DLT thất bại.
    recoverer.setFailIfSendResultIsError(true);

    // Lần gọi ban đầu + tối đa 2 lần retry, cách nhau 1 giây.
    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderPayloadException.class,
            UnsupportedEventVersionException.class);

    handler.setResetStateOnExceptionChange(true);

    return handler;
}
```

Đoạn cấu hình dùng các exception domain tự định nghĩa. Các class exception phải tồn tại trong ứng dụng. `DeadLetterPublishingRecoverer` dùng template có serializer phù hợp với key/value, topic DLT phải có partition được resolver trỏ tới, và producer cần quyền ghi. `setFailIfSendResultIsError(true)` giúp lỗi publish DLT được báo ngược cho error handler trong các phiên bản hỗ trợ API này.

Đăng ký error handler với container factory mà listener thực sự sử dụng:

```java
@Bean(name = "orderKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultErrorHandler orderErrorHandler) {

    ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}
```

Listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-processing-service",
        containerFactory = "orderKafkaListenerContainerFactory")
public void handle(OrderCreated event) {
    orderService.processIdempotently(event);
}
```

Trong ví dụ này, `AckMode.RECORD` commit offset sau khi listener hoàn tất record thành công theo cơ chế của container. Khi listener ném exception, `DefaultErrorHandler` quản lý retry và recovery. Việc reset `BackOff` khi exception đổi loại **không tự thay đổi ack mode** hoặc thời điểm commit offset.

Nếu ứng dụng có nhiều factory, cần kiểm tra đúng `containerFactory` trên mỗi `@KafkaListener`. Việc khai báo error handler thành bean không đủ để bảo đảm mọi listener đều đang dùng handler đó.

## 4. Ví dụ diễn tiến: hai loại exception đều retryable

Giả sử một record ban đầu không gọi được hệ thống tồn kho. Sau một lần retry, tồn kho đã phản hồi nhưng kết nối tới database lại timeout. Cả hai exception đều được coi là tạm thời và có thể retry.

Với `FixedBackOff(1_000L, 2L)` và `resetStateOnExceptionChange=true`, diễn tiến minh họa:

| Delivery | Exception | Quyết định |
|---:|---|---|
| 1 | `InventoryTimeoutException` | Bắt đầu retry state cho loại lỗi này, chờ 1 giây |
| 2 | `InventoryTimeoutException` | Tiêu thụ lần retry tiếp theo của cùng loại lỗi |
| 3 | `DatabaseTimeoutException` | Loại exception thay đổi; reset `BackOff` để bắt đầu chuỗi retry cho lỗi mới |
| 4 | `DatabaseTimeoutException` | Retry tiếp theo của lỗi database |
| 5 | `DatabaseTimeoutException` | Hết budget của lỗi hiện tại; gọi recoverer nếu vẫn thất bại |

Số lần delivery trong bảng nhằm minh họa chuỗi reset khi đổi exception. Hành vi chính xác còn phụ thuộc loại `BackOff`, việc exception được phân loại như thế nào và các lần xử lý trước đó đã thành công hay chưa.

Điểm cần hiểu: **retry count của một record có thể vượt số retry được đặt cho một chuỗi `BackOff` đơn lẻ nếu loại exception tiếp tục thay đổi**. Điều này có ích khi lỗi chuyển từ một trạng thái tạm thời sang một trạng thái tạm thời khác, nhưng cũng có thể kéo dài thời gian xử lý record.

### Rủi ro khi exception luân phiên

Nếu cùng một record liên tục luân phiên giữa `InventoryTimeoutException` và `DatabaseTimeoutException`, trạng thái `BackOff` có thể bị reset nhiều lần. Record sẽ được giữ lại lâu hơn dự kiến so với một chuỗi retry cố định.

```text
A -> B -> A -> B -> A -> B -> ...
     ^     ^     ^
     |     |     |
  đổi loại exception, có thể reset BackOff
```

Nếu ứng dụng cần giới hạn tổng số lần xử lý hoặc tổng thời gian từ lần delivery đầu tiên, hãy bổ sung chính sách độc lập ở mức nghiệp vụ/vận hành, chẳng hạn event deadline, số lần delivery được ghi nhận bền vững, hoặc ngưỡng chuyển sang quarantine. Không dựa vào một `FixedBackOff` trong bộ nhớ như rào chắn toàn cục khi bật reset theo exception change.

## 5. Ví dụ diễn tiến: exception mới là not-retryable

Một tình huống khác là sau khi dependency phục hồi, listener phát hiện dữ liệu vĩnh viễn không hợp lệ.

```text
Delivery 1:
  InventoryTimeoutException   -> retry

Delivery 2:
  InventoryTimeoutException   -> retry

Delivery 3:
  InvalidOrderPayloadException -> loại lỗi thay đổi
                                -> không retry theo classification
                                -> recoverer / DLT
```

Trong cấu hình ở phần trước, `InvalidOrderPayloadException` nằm trong danh sách `addNotRetryableExceptions(...)`. Nó phải được xử lý theo chính sách không retry, kể cả khi record trước đó gặp lỗi tạm thời.

Khi exception đổi loại, việc đánh giá classification theo loại lỗi mới rất quan trọng. Cần kiểm tra hành vi của đúng phiên bản Spring Kafka, đặc biệt nếu ứng dụng bọc exception hoặc tùy biến classifier. Nếu muốn đưa record trực tiếp tới DLT, ứng dụng cần bảo đảm exception thực tế mà handler nhận được có thể được phân loại là not-retryable.

Không nên dùng exception tổng quát như `RuntimeException` làm not-retryable chỉ vì một vài lỗi dữ liệu được wrap vào đó. Một classification quá rộng có thể khiến lỗi database tạm thời cũng bị đưa thẳng tới DLT. Nên giữ exception domain cụ thể và bảo tồn cause chain.

## 6. Phân biệt reset khi exception đổi với reset sau recovery failure

`DefaultErrorHandler` có hai cơ chế reset liên quan nhưng mang ý nghĩa khác nhau:

| Thuộc tính | Điều kiện kích hoạt | Tác động |
|---|---|---|
| `resetStateOnExceptionChange` | Loại exception ở những lần xử lý cùng record thay đổi | Tạo lại chuỗi `BackOff` cho loại lỗi mới |
| `resetStateOnRecoveryFailure` | Recoverer đã được gọi nhưng chính quá trình recovery thất bại | Quyết định có khởi động lại chuỗi `BackOff` khi record cần được xử lý tiếp hay không |

Hai tình huống khác nhau hoàn toàn:

**Tình huống A — Exception đổi:** listener thất bại lần đầu bởi timeout, lần sau bởi lỗi xác thực. Handler theo dõi thay đổi loại exception của listener và reset state theo cấu hình.

**Tình huống B — Recovery thất bại:** listener vẫn ném cùng một exception, các lần retry đã hết, nhưng `DeadLetterPublishingRecoverer` không thể ghi DLT do thiếu ACL. Lỗi xảy ra trong recoverer; `resetStateOnRecoveryFailure` điều khiển việc reset `BackOff` trong nhánh này.

Ví dụ cấu hình tường minh cả hai:

```java
DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));

handler.setResetStateOnExceptionChange(true);
handler.setResetStateOnRecoveryFailure(true);
```

Hai thuộc tính không thay thế nhau. Có thể bật một, cả hai hoặc điều chỉnh theo yêu cầu. Khi recovery liên tục thất bại, cần quan sát DLT publish errors, backoff và consumer lag; reset trạng thái không chữa được lỗi ACL, serializer hay broker bị mất kết nối.

## 7. Exception wrapper và cause chain

Trong ứng dụng Spring, exception gốc không phải lúc nào cũng là đối tượng nằm ở lớp ngoài cùng. Listener method có thể ném `InvalidOrderPayloadException`, nhưng Spring Kafka hoặc tầng ứng dụng bọc nó trong một exception khác:

```text
ListenerExecutionFailedException
       |
       +-- cause: OrderProcessingException
                       |
                       +-- cause: InvalidOrderPayloadException
```

Nếu các lần lỗi đều xuất hiện dưới cùng một wrapper nhưng root cause thay đổi, cách đánh giá “exception type change” phụ thuộc cơ chế unwrap và cause traversal của phiên bản Spring Kafka. Hãy cấu hình, thử nghiệm trên chính các wrapper xuất hiện trong ứng dụng và quan sát exception được recoverer nhận.

Giữ cause gốc khi wrap exception:

```java
try {
    reservationService.reserve(order);
}
catch (InvalidOrderPayloadException ex) {
    throw new OrderProcessingException("Invalid order event", ex);
}
```

Không tạo exception mới rồi bỏ mất cause:

```java
catch (InvalidOrderPayloadException ex) {
    throw new OrderProcessingException("Cannot process event");
}
```

Trong trường hợp thứ hai, error handler không còn đủ thông tin để nhận diện lỗi gốc. Nếu cần classification chính xác, có thể để domain exception truyền ra trực tiếp hoặc cấu hình classifier cho exception wrapper và cách traverse causes phù hợp.

Không nên dùng sự thay đổi thông điệp exception làm tín hiệu để reset retry. Hai `TimeoutException` có message khác nhau vẫn có thể thuộc cùng một lỗi tạm thời; ngược lại, hai loại exception khác nhau có thể đại diện cho hai nguyên nhân cần chính sách khác nhau.

## 8. Ảnh hưởng tới ordering, lag và throughput

Khi một record liên tục được retry, container có thể chưa chuyển sang những record kế tiếp trong partition, tùy chiến lược error handler và listener mode. Bật reset theo exception change có thể kéo dài số lần xử lý trước khi recover, khiến consumer lag và tuổi record chưa xử lý tăng lên.

Ví dụ topic `payment-events` cần hoàn tất một record trước khi xử lý record tiếp theo theo cùng key. Một record có lỗi A rồi B rồi A có thể giữ luồng xử lý lâu hơn cấu hình retry đơn thuần. Những record đến sau cùng partition có thể bị trì hoãn dù chúng hợp lệ.

Khi vận hành, cần cân bằng:

- Lợi ích của việc cấp lại retry budget khi nguyên nhân mới có thể tự phục hồi.
- Yêu cầu về thời gian xử lý tối đa của sự kiện.
- Chi phí gọi lại database và API downstream.
- Độ trễ tăng lên của các record ở phía sau.
- Khả năng đưa record lỗi sang DLT sớm để cô lập và xử lý sau.

Nếu thứ tự theo key là điều kiện bắt buộc, cần cân nhắc tác động của DLT và retry topic tới việc một record được xử lý trước hay sau record khác. `resetStateOnExceptionChange` chỉ kiểm soát trạng thái retry; nó không giải quyết toàn bộ bài toán ordering giữa nhiều topic hoặc partition.

## 9. Quan hệ với `seekAfterError` và ack mode

Một số cấu hình dễ bị nhầm với reset retry state:

| Cấu hình | Trách nhiệm |
|---|---|
| `setResetStateOnExceptionChange(true)` | Đặt lại lịch `BackOff` khi loại exception đổi |
| `setSeekAfterError(false)` | Cho phép container giữ và resubmit các record chưa xử lý thay vì seek partition để fetch lại |
| `setCommitRecovered(true)` | Yêu cầu commit offset của record sau khi recoverer hoàn tất theo điều kiện ack mode tương ứng |
| `AckMode.RECORD` | Commit tiến độ sau khi listener xử lý thành công từng record |
| `AckMode.MANUAL_IMMEDIATE` | Cho phép acknowledgment trực tiếp theo cơ chế manual immediate của container |

`seekAfterError=false` quyết định cách record được redeliver, còn `resetStateOnExceptionChange=true` quyết định cách retry budget được theo dõi khi lỗi đổi loại. Hai cấu hình có thể cùng xuất hiện nhưng không phụ thuộc trực tiếp vào nhau.

`commitRecovered` là câu chuyện khác: sau khi recover thành công, consumer group có ghi nhận offset đã xử lý hay không. Reset state **không** tự commit offset, và một lần listener retry thành công **không** làm các side effect bên ngoài Kafka trở nên exactly-once. Với side effect như cập nhật database hoặc gửi yêu cầu thanh toán, hãy thiết kế idempotency.

## 10. Container transaction và `DefaultAfterRollbackProcessor`

Khi listener container chạy với Kafka transaction, exception có thể khiến transaction hiện tại rollback. Spring Kafka sử dụng `DefaultAfterRollbackProcessor` để xử lý việc retry hoặc recover record sau rollback trong mô hình transactional.

`DefaultAfterRollbackProcessor` cũng có hỗ trợ reset trạng thái theo thay đổi loại exception trong các phiên bản Spring Kafka tương ứng. Khi cần hành vi này, hãy cấu hình processor trên đúng transactional listener container, thay vì chỉ đặt trên một `DefaultErrorHandler` dành cho luồng non-transactional.

Ví dụ mô tả:

```java
DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
                recoverer,
                new FixedBackOff(1_000L, 2L));

processor.setResetStateOnExceptionChange(true);
```

Đoạn code giả định `recoverer` có kiểu `ConsumerRecordRecoverer` tương thích và phiên bản Spring Kafka hỗ trợ setter này. Việc đưa processor vào container factory, cấu hình Kafka transaction manager và DLT transactional publisher vẫn phải được thực hiện theo thiết kế giao dịch của ứng dụng.

Trong transactional recovery, quyết định commit offset của record recovered có thể sử dụng một transaction mới theo cấu hình processor. Reset retry state không tự bật transactional recovery. Cần tách rõ retry, rollback, recovery và commit để tránh nhận định sai rằng thay đổi exception sẽ tự khởi tạo hoặc commit một Kafka transaction.

## 11. Theo dõi retry khi exception thay đổi

Để chẩn đoán, log và metric cần thể hiện **record nào**, **exception nào**, **delivery thứ mấy** và **handler đã retry hay recover**. Các trường thường hữu ích:

| Trường | Mục đích |
|---|---|
| Topic, partition, offset | Xác định record đang bị retry |
| Group ID và listener/container ID | Phân biệt consumer thực thi |
| Exception class và root cause class | Nhận diện trường hợp đổi loại lỗi |
| Delivery attempt | Quan sát số lần gọi listener trong vòng xử lý hiện tại |
| Kết quả retry/recovery | Biết record được thử lại hay đã chuyển DLT |
| Duration từ lần lỗi đầu | Phát hiện record bị giữ quá lâu do retry reset nhiều lần |

Spring Kafka cung cấp `RetryListener` để nhận thông tin các lần failed delivery, recovered và recovery failed ở những phiên bản hỗ trợ. Có thể đăng ký listener quan sát trên `DefaultErrorHandler`:

```java
handler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception ex,
            int deliveryAttempt) {
        // Ghi metric/log nhẹ theo topic, exception class và attempt.
    }
});
```

Đây là callback quan sát, không phải nơi gọi lại listener hoặc cập nhật database nghiệp vụ. Không làm I/O chặn luồng tiêu thụ trong callback. Khi theo dõi chuyển đổi exception, có thể bổ sung counter tăng khi class của lỗi mới khác class đã thấy trước đó cho cùng record trong một cửa sổ xử lý có giới hạn.

Không dùng event ID, offset hoặc exception message làm label metric vì cardinality có thể quá lớn. Giữ thông tin định danh chi tiết trong log/tracing; dùng metric với nhãn được giới hạn như service, topic, exception class và kết quả.

## 12. Tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Record được retry nhiều hơn `maxAttempts` dự kiến | Loại exception thay đổi liên tiếp, khiến BackOff reset | Quan sát exception sequence, đặt deadline hoặc giới hạn tổng thời gian xử lý |
| Exception not-retryable vẫn được retry | Exception bị wrap; classifier chưa nhận diện đúng loại lỗi mới; listener đang dùng handler khác | Kiểm tra cause chain, classification và container factory thực tế |
| Cấu hình setter nhưng không có tác dụng | Listener dùng factory/error handler khác hoặc phiên bản không hỗ trợ API tương ứng | Xác nhận dependency version và bean được gắn bằng `setCommonErrorHandler` |
| Recoverer được gọi quá sớm | Không reset khi exception đổi hoặc exception mới là fatal | Xem loại exception từng delivery, backoff state và classifier |
| Record đã sang DLT nhưng xuất hiện lại | Publish DLT và commit offset nguồn không nguyên tử; restart/commit failure | Kiểm tra offset, idempotency của DLT/replay và thiết kế transaction nếu cần |
| Consumer lag tăng kéo dài | Retry budget được reset nhiều lần, downstream lỗi liên tục | Giới hạn retries, deadline và theo dõi throughput/độ tuổi record |
| Error handler xử lý sai loại lỗi | Nhiều lỗi bị bọc thành một `RuntimeException` chung hoặc mất cause | Dùng exception domain cụ thể và giữ cause gốc |

Khi điều tra, ưu tiên dựng lại chuỗi exception theo cùng topic-partition-offset. Chỉ nhìn exception cuối cùng có thể dẫn tới kết luận sai: record có thể đã tiêu thụ nhiều retry budget của loại lỗi trước đó rồi mới đổi loại.

## 13. Các kịch bản kiểm thử cần có khi áp dụng

Một kiểm thử tích hợp cho retry state nên kiểm soát được exception được ném ở từng lần delivery và quan sát retry/recovery. Các trường hợp có giá trị gồm:

1. **Cùng loại lỗi liên tục:** listener ném exception A ở mọi lần; xác nhận số retry theo `FixedBackOff` và recovery sau khi exhausted.
2. **Loại lỗi thay đổi:** lần đầu ném A, lần sau ném B; xác nhận `BackOff` reset và lịch retry áp dụng cho B.
3. **Lỗi đổi sang not-retryable:** A retryable rồi B not-retryable; xác nhận handler đi tới recoverer theo classification mới.
4. **Cùng class nhưng message thay đổi:** xác nhận không xem đây là exception-type change.
5. **Exception bọc nhiều lớp:** xác nhận classifier nhận đúng root cause/wrapper theo cấu hình.
6. **Recovery thất bại:** giả lập DLT publish lỗi để phân biệt `resetStateOnRecoveryFailure` với reset do exception thay đổi.
7. **Restart giữa retry:** xác nhận committed offset và idempotency; không kỳ vọng trạng thái `BackOff` trong bộ nhớ sống qua restart.
8. **Loại lỗi luân phiên:** A/B/A/B; xác nhận giới hạn thời gian hoặc số attempt cấp ứng dụng nếu nghiệp vụ có ràng buộc này.

Với mỗi trường hợp, nên ghi nhận số lần gọi listener, exception class theo attempt, số lần gọi recoverer, record thực tế trong DLT và committed offset. Đừng chỉ khẳng định reset hoạt động dựa trên việc listener được gọi nhiều lần: số lần gọi tăng còn có thể đến từ restart, rebalance hoặc retry ở tầng khác.

## 14. Lựa chọn cấu hình cho production

Khi đưa `resetStateOnExceptionChange` vào hệ thống, cần xác định mục tiêu hành vi trước:

- Nếu loại exception mới thường đại diện cho một điều kiện tạm thời mới, reset retry state giúp loại lỗi đó có cơ hội phục hồi theo budget riêng.
- Nếu luồng có deadline xử lý nghiêm ngặt, việc reset nhiều lần có thể khiến record giữ partition quá lâu; nên đặt rào chắn thời gian độc lập.
- Nếu exception mới là lỗi dữ liệu xác định, hãy phân loại not-retryable và thiết kế recoverer bền vững.
- Nếu dùng nhiều wrapper, cần giữ cause và xác nhận classifier phù hợp với exception thực tế của listener.
- Nếu DLT publish có thể thất bại, recoverer phải báo lỗi và cần quan sát recovery failure.
- Nếu dùng Kafka transactions, xác nhận retry state nằm trong processor đúng với luồng rollback đang chạy.

Các điểm cần duy trì trong runbook vận hành là: tìm đúng group/partition/offset, đọc chuỗi exception theo attempt, xác định thời gian record đã bị giữ, kiểm tra DLT và offset, sau đó quyết định sửa lỗi downstream, cập nhật exception classification hoặc điều chỉnh retry budget. Không reset consumer offset thủ công chỉ để che đi hiện tượng retry lặp; reset tiến lên có thể bỏ qua bản ghi, còn reset lùi có thể tạo side effect trùng.

`resetStateOnExceptionChange` giải quyết một tình huống cụ thể trong retry: **một record chuyển từ loại lỗi này sang loại lỗi khác khi được xử lý lại**. Khi hiểu nó như cơ chế reset trạng thái `BackOff` và kết hợp với exception classification, recovery, idempotency và quan sát theo record, đội vận hành có thể tránh retry vô ích mà vẫn dành đủ cơ hội phục hồi cho lỗi tạm thời mới phát sinh.
