# Reset state khi recovery thất bại

## 1. Recovery failure trong Spring Kafka

Trong Spring Kafka, `DefaultErrorHandler` xử lý exception phát sinh khi listener nhận và xử lý record. Một luồng xử lý lỗi thường có hai giai đoạn:

1. **Retry delivery**: listener được gọi lại theo chính sách `BackOff` khi record xử lý thất bại.
2. **Recovery**: sau khi hết lượt retry, error handler gọi recoverer để xử lý record không thể hoàn tất, ví dụ ghi log, lưu vào hệ thống lỗi hoặc publish sang dead-letter topic (DLT).

Recovery cũng có thể thất bại. Ví dụ, listener không xử lý được event sau nhiều lần thử và `DeadLetterPublishingRecoverer` cố publish record sang DLT, nhưng broker đích không khả dụng hoặc producer không nhận được xác nhận gửi thành công. Khi recoverer ném exception, record chưa được phục hồi theo chính sách đã định.

`resetStateOnRecoveryFailure` điều khiển cách `DefaultErrorHandler` xử lý trạng thái BackOff sau khi recoverer thất bại:

- Mặc định là `true`: reset BackOff state. Khi record được giao lại, nó bắt đầu lại chu kỳ retry từ đầu trước khi recoverer được gọi lần nữa.
- Đặt `false`: không reset BackOff state. Lần giao lại tiếp theo bỏ qua chu kỳ retry đã hết và thử recovery lại ngay, theo hành vi BackOff đã cạn lượt.

Thiết lập này quyết định nhịp retry sau một lần recovery thất bại. Nó không reset committed offset, không đưa consumer group về đầu topic và không xóa dữ liệu nghiệp vụ.

## 2. Phân biệt listener failure và recovery failure

Hai lỗi xảy ra ở hai giai đoạn khác nhau và cần được chẩn đoán riêng.

### 2.1. Listener failure

Listener failure xảy ra khi phương thức listener ném exception trong lúc xử lý record.

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrder(OrderCreated event) {
    billingService.process(event); // Có thể ném exception
}
~~~

Nếu `billingService.process()` ném exception, `DefaultErrorHandler` nhận lỗi và áp dụng BackOff. Khi còn lượt retry, record được giao lại theo cơ chế error handler.

### 2.2. Recovery failure

Recovery failure xảy ra sau khi error handler đã quyết định recover record, nhưng chính recoverer không hoàn thành được công việc phục hồi.

Ví dụ recoverer publish DLT:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(kafkaTemplate);
~~~

Nếu thao tác publish DLT thất bại và recoverer ném exception, error handler không thể coi record đã được chuyển sang DLT thành công. Record phải quay lại luồng redelivery để có cơ hội recovery lần nữa.

### 2.3. Luồng tổng quát

~~~mermaid
flowchart TD
    A[Consumer nhận record] --> B[Listener xử lý]
    B -->|Thành công| C[Container commit theo AckMode]
    B -->|Exception| D[DefaultErrorHandler áp dụng BackOff]
    D --> E{Còn lượt retry?}
    E -->|Có| F[Redelivery đến listener]
    F --> B
    E -->|Không| G[Gọi recoverer]
    G --> H{Recovery thành công?}
    H -->|Có| I[Đánh dấu recovered và tiến offset theo policy]
    H -->|Không| J[Recovery failure]
    J --> K{resetStateOnRecoveryFailure}
    K -->|true| L[Reset BackOff state]
    K -->|false| M[Giữ BackOff state đã hết]
    L --> N[Redelivery: retry cycle bắt đầu lại]
    M --> O[Redelivery: thử recovery lại mà không chạy retry cycle mới]
    N --> B
    O --> G
~~~

Sơ đồ mô tả ý nghĩa của hai nhánh reset. Thời điểm commit thực tế còn phụ thuộc acknowledgment mode, error handler, recoverer và trạng thái consumer group.

## 3. Vì sao phải reset BackOff khi recovery thất bại?

Giả sử cấu hình có hai lần retry sau lần gọi đầu tiên, với khoảng chờ một giây:

~~~java
BackOff backOff = new FixedBackOff(1_000L, 2L);
DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, backOff);
~~~

Một record có thể đi qua trình tự:

1. Listener nhận record và thất bại.
2. Error handler chờ một giây rồi retry.
3. Listener tiếp tục thất bại.
4. Error handler chờ thêm một giây rồi retry lần cuối.
5. Listener vẫn thất bại.
6. Error handler gọi recoverer.
7. Recoverer cũng thất bại, ví dụ publish DLT không thành công.

Đến đây có hai chính sách hợp lý.

**Reset state (`true`)**: khi record được giao lại, BackOff bắt đầu từ đầu. Listener có cơ hội được thử lại theo chu kỳ ban đầu. Nếu downstream đã phục hồi, listener có thể xử lý thành công và không cần recovery nữa. Nếu listener vẫn thất bại, recoverer được gọi lại sau khi hết retry.

**Giữ state (`false`)**: BackOff vẫn ở trạng thái đã hết lượt. Khi record được giao lại, error handler không chạy thêm chu kỳ retry listener mới mà thử gọi recoverer lại. Cách này hữu ích khi lỗi chính nằm ở hệ thống recovery, còn việc chạy lại listener không có giá trị hoặc tạo thêm side effect.

## 4. Giá trị mặc định và khác biệt phiên bản

Từ Spring Kafka 2.5.5, khi recoverer thất bại, BackOff được reset mặc định. Có thể đặt `resetStateOnRecoveryFailure=false` để quay lại hành vi trước đó, trong đó BackOff không được reset và recovery được thử lại ở lần delivery tiếp theo mà không chạy lại chu kỳ retry.

| Phiên bản / cấu hình | Hành vi khi recoverer ném exception |
|---|---|
| Trước Spring Kafka 2.5.5 | BackOff không reset theo hành vi mặc định cũ |
| Spring Kafka 2.5.5 trở lên, mặc định | BackOff reset; redelivery đi qua retry sequence từ đầu |
| Spring Kafka 2.5.5 trở lên, đặt `resetStateOnRecoveryFailure=false` | Giữ BackOff đã hết; lần delivery sau thử recovery lại mà không chạy chu kỳ retry mới |

Đừng nhầm thiết lập này với `resetStateOnExceptionChange`. Hai thuộc tính xử lý hai sự kiện khác nhau:

- `resetStateOnRecoveryFailure` xử lý trường hợp recoverer ném exception.
- `resetStateOnExceptionChange` điều khiển việc khởi động lại retry sequence khi loại exception của listener thay đổi giữa các lần delivery.

Từ Spring Kafka 2.9, `resetStateOnExceptionChange` mặc định là `true`. Khi nâng cấp, cần xem lại cả hai thuộc tính thay vì cho rằng chúng có cùng tác dụng.

## 5. Cấu hình reset state trong DefaultErrorHandler

### 5.1. Giữ hành vi mặc định

Nếu không gọi setter, `DefaultErrorHandler` sử dụng hành vi reset BackOff khi recovery thất bại trong các phiên bản Spring Kafka có hỗ trợ hành vi mặc định này (từ 2.5.5).

~~~java
@Bean
public DefaultErrorHandler orderErrorHandler(
    KafkaTemplate<Object, Object> kafkaTemplate
) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Trong trường hợp này, nếu recoverer ném exception, record được đưa lại vào luồng xử lý và BackOff được reset. Lần delivery sau có thể đi qua các lần gọi listener và khoảng chờ như chu kỳ ban đầu.

Đây thường là lựa chọn phù hợp khi hệ thống downstream có thể phục hồi theo thời gian và listener có cơ hội xử lý thành công ở lần sau.

### 5.2. Tắt reset state khi recovery thất bại

Nếu muốn bỏ qua retry listener sau khi recoverer thất bại, đặt thuộc tính thành `false`:

~~~java
@Bean
public DefaultErrorHandler orderErrorHandler(
    KafkaTemplate<Object, Object> kafkaTemplate
) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    DefaultErrorHandler handler =
        new DefaultErrorHandler(recoverer, backOff);

    handler.setResetStateOnRecoveryFailure(false);

    return handler;
}
~~~

Sau khi recovery thất bại, lần giao lại tiếp theo không bắt đầu một chu kỳ retry listener mới. Handler tiếp tục ở trạng thái BackOff đã hết và thử recovery lại.

Chỉ dùng lựa chọn này khi việc chạy lại listener không cần thiết hoặc không an toàn. Ví dụ listener đã thất bại vì payload không hợp lệ và recovery service đang tạm thời lỗi; gọi listener thêm nhiều lần có thể không giúp ích, trong khi việc thử publish DLT lại là mục tiêu chính.

### 5.3. Gắn handler vào đúng listener container factory

Khai báo bean chưa đủ nếu listener sử dụng một factory khác. Hãy gắn handler vào factory mà endpoint thực sự dùng:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        orderKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler orderErrorHandler
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(orderErrorHandler);

    return factory;
}
~~~

Nếu ứng dụng có nhiều factory, mỗi factory có thể cần chính sách riêng. Không nên giả định mọi `@KafkaListener` tự động sử dụng cùng một handler khi ứng dụng đã tạo các factory tùy chỉnh.

## 6. DeadLetterPublishingRecoverer và lỗi gửi DLT

Một tình huống recovery failure phổ biến là publish DLT thất bại. Cần cấu hình recoverer để lỗi gửi được phát hiện và ném ra thay vì âm thầm xem thao tác gửi là hoàn tất.

### 6.1. Bật kiểm tra kết quả gửi

Từ Spring Kafka 2.7, `DeadLetterPublishingRecoverer` hỗ trợ `setFailIfSendResultIsError(true)` để ném exception khi kết quả gửi DLT báo lỗi.

~~~java
@Bean
public DefaultErrorHandler orderErrorHandler(
    KafkaTemplate<Object, Object> kafkaTemplate
) {
    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

    recoverer.setFailIfSendResultIsError(true);
    recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );

    handler.setResetStateOnRecoveryFailure(true);
    return handler;
}
~~~

Thời gian chờ xác nhận gửi cần phù hợp với timeout producer và SLA. Nếu timeout xác nhận quá ngắn, recoverer có thể báo lỗi dù broker đã ghi record nhưng response chưa đến kịp. Điều này có thể dẫn đến publish DLT lặp ở lần recovery sau; vì vậy cần thiết kế quy trình DLT chịu được duplicate.

### 6.2. Vì sao cần xác nhận DLT publish?

Nếu ứng dụng coi recovery thành công ngay khi bắt đầu gọi send, record nguồn có thể được xem là recovered trước khi biết DLT đã nhận record hay chưa. Khi gửi bất đồng bộ, việc xác nhận kết quả giúp phát hiện lỗi producer/broker và giữ record nguồn trong luồng phục hồi khi DLT publish thất bại.

Cần xác định rõ:

- Producer có nhận được broker acknowledgment hay không.
- DLT topic có tồn tại và đủ partition hay không.
- Serializer có thể serialize cả payload bình thường và payload lỗi hay không.
- Producer có quyền ghi DLT hay không.
- Timeout xác nhận có phù hợp với độ trễ thực tế hay không.

### 6.3. Kiểm tra cấu hình DLT topic

Theo resolver mặc định, record thường được gửi đến topic có hậu tố `-dlt` và partition tương ứng với partition nguồn. Khi dùng cách định tuyến mặc định, DLT topic cần có ít nhất số partition bằng topic nguồn.

Nếu dùng resolver tùy chỉnh, có thể định tuyến đến topic hoặc partition khác:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(
        kafkaTemplate,
        (record, exception) ->
            new TopicPartition(record.topic() + "-dlt", record.partition())
    );
~~~

Cần bảo đảm destination thực sự tồn tại, partition hợp lệ và ACL cho phép producer ghi. Nếu DLT publish thất bại do cấu hình đích sai, reset BackOff chỉ khiến hệ thống lặp lại cùng một lỗi cho đến khi cấu hình được sửa.

## 7. Chọn true hay false theo tình huống

Không có một giá trị phù hợp cho mọi ứng dụng. Quyết định phụ thuộc việc listener có nên được chạy lại sau khi recovery thất bại hay không.

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| DLT broker tạm thời không khả dụng, listener có thể xử lý thành công khi thử lại | `true` | Cho phép toàn bộ chu kỳ xử lý bắt đầu lại |
| Downstream listener tạm thời lỗi, DLT cũng đang không khả dụng | `true` | Listener có thêm cơ hội thành công sau thời gian chờ |
| Payload không hợp lệ, listener retry không thể sửa dữ liệu | `false` có thể phù hợp | Tránh lặp lại các lần xử lý vô ích; thử recovery lại |
| Recovery service có thể phục hồi, nhưng listener có side effect khó lặp | Cân nhắc `false` | Tránh gọi lại listener khi recovery mới là phần đang lỗi |
| DLT destination sai cấu hình | Không giá trị nào tự sửa được lỗi | Sửa topic, partition, ACL hoặc serializer trước |
| Cần chạy lại toàn bộ nghiệp vụ sau mỗi recovery failure | `true` | Reset BackOff để listener có chu kỳ retry mới |

Đặc biệt, `false` không có nghĩa bỏ record hoặc commit offset ngay. Nó chỉ giữ trạng thái BackOff đã hết để lần delivery kế tiếp tiếp tục thử recovery mà không chạy một chu kỳ retry listener mới. Record vẫn cần được phục hồi thành công hoặc được xử lý theo một chính sách quản trị khác trước khi tiến offset.

## 8. Retry listener để quan sát recovery failure

Spring Kafka cung cấp `RetryListener` để nhận thông báo về retry và recovery. Từ Spring Kafka 2.8.10, các callback cho batch listener cũng được bổ sung.

Các callback record quan trọng:

- `failedDelivery(record, exception, deliveryAttempt)`: listener delivery thất bại.
- `recovered(record, exception)`: record đã được recover thành công.
- `recoveryFailed(record, original, failure)`: recoverer thất bại; tham số đầu là exception ban đầu của listener và tham số cuối là exception phát sinh trong recovery.

Ví dụ:

~~~java
public class OrderRetryListener implements RetryListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderRetryListener.class);

    @Override
    public void failedDelivery(
        ConsumerRecord<?, ?> record,
        Exception exception,
        int deliveryAttempt
    ) {
        log.warn(
            "Listener delivery failed: topic={}, partition={}, offset={}, attempt={}",
            record.topic(),
            record.partition(),
            record.offset(),
            deliveryAttempt,
            exception
        );
    }

    @Override
    public void recovered(
        ConsumerRecord<?, ?> record,
        Exception exception
    ) {
        log.info(
            "Record recovered: topic={}, partition={}, offset={}",
            record.topic(),
            record.partition(),
            record.offset()
        );
    }

    @Override
    public void recoveryFailed(
        ConsumerRecord<?, ?> record,
        Exception original,
        Exception failure
    ) {
        log.error(
            "Recovery failed: topic={}, partition={}, offset={}",
            record.topic(),
            record.partition(),
            record.offset(),
            failure
        );
        log.error("Original listener failure", original);
    }
}
~~~

Đăng ký listener với error handler:

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));

handler.setResetStateOnRecoveryFailure(true);
handler.setRetryListeners(new OrderRetryListener());
~~~

Chữ ký callback và API đăng ký cần khớp phiên bản Spring Kafka đang dùng. Nếu xử lý batch, hãy kiểm tra các overload nhận `ConsumerRecords` trong Javadoc.

`recoveryFailed` là tín hiệu quan trọng để tách lỗi listener khỏi lỗi DLT/recoverer. Nếu chỉ theo dõi số lần listener thất bại, đội vận hành có thể bỏ sót việc DLT đang không ghi được.

## 9. Reset state không phải reset offset

Tên gọi `resetStateOnRecoveryFailure` dễ gây nhầm rằng consumer sẽ reset offset. Thực tế nó chỉ điều khiển trạng thái BackOff của error handler.

| Thành phần | Có bị thay đổi bởi resetStateOnRecoveryFailure không? |
|---|---|
| BackOff retry state của record đang lỗi | Có |
| Committed offset của consumer group | Không trực tiếp |
| Log start/end offset của partition | Không |
| Nội dung record trong Kafka | Không |
| Consumer group ID | Không |
| Business state trong database | Không |
| Listener payload | Không |
| Destination DLT | Không |

Nếu cần replay record đã commit, phải dùng quy trình reset offset có chủ đích hoặc một group mới. Không dùng `resetStateOnRecoveryFailure` cho mục tiêu đó.

Tương tự, nếu cần khôi phục trạng thái database, phải dùng transaction, compensation hoặc quy trình nghiệp vụ riêng. Error handler không tự rollback side effect đã commit ở hệ thống ngoài Kafka.

## 10. Recovery failure và acknowledgment/commit offset

Khi recoverer ném exception, record chưa được xem là recovered thành công. Với hành vi tiêu chuẩn, record được đưa lại vào luồng redelivery (seek trong chế độ seek thông thường, hoặc retained/resubmitted nếu cấu hình `seekAfterError=false`).

Điều này giúp record không bị bỏ qua chỉ vì DLT publish thất bại. Tuy nhiên, tiến độ commit cụ thể còn phụ thuộc:

- Listener dùng `AckMode.RECORD` hay `AckMode.BATCH`.
- Listener xử lý record hay batch.
- Error handler đã commit offset của các record trước record lỗi hay chưa.
- Recoverer có hoàn tất thành công ở lần tiếp theo hay không.
- Các thuộc tính như `ackAfterHandle` và `commitRecovered`.
- Consumer có bị rebalance hoặc restart trong lúc recovery hay không.

Không được giả định rằng một exception từ recoverer luôn dẫn đến cùng một offset commit trong mọi ack mode. Khi triển khai, hãy kiểm tra committed offset thực tế theo từng partition.

Nếu recoverer thành công, handler có thể coi record đã được xử lý theo chính sách recovery và tiến offset tương ứng. Nếu recoverer thất bại, record phải tiếp tục được xử lý lại, không commit vượt qua nó theo cách làm mất record.

## 11. Tương tác với seekAfterError=false

Từ Spring Kafka 2.9, `DefaultErrorHandler` có thể giữ các record chưa xử lý trong listener container và resubmit chúng thay vì seek partition để fetch lại. Có thể bật bằng:

~~~java
handler.setSeekAfterError(false);
~~~

Thiết lập này thay đổi cách container lấy lại record chưa xử lý, nhưng không thay đổi ý nghĩa của `resetStateOnRecoveryFailure`.

Khi recovery thất bại:

- Record lỗi vẫn phải quay lại luồng delivery/recovery.
- BackOff state được reset hay giữ nguyên theo `resetStateOnRecoveryFailure`.
- Nếu record được retained/resubmitted, trạng thái retained nằm trong bộ nhớ và không bền vững qua process restart.
- Nếu consumer dừng, Kafka khôi phục từ committed offset và record chưa commit có thể được giao lại.

Hai thiết lập giải quyết hai câu hỏi riêng:

| Thuộc tính | Câu hỏi |
|---|---|
| `seekAfterError` | Record chưa xử lý được lấy lại bằng seek/fetch hay retain/resubmit? |
| `resetStateOnRecoveryFailure` | Sau khi recoverer thất bại, BackOff state được reset hay tiếp tục ở trạng thái đã hết? |

Không nên thay đổi đồng thời hai thuộc tính nếu chưa hiểu riêng tác động của từng cái.

## 12. Những nguyên nhân recovery thất bại thường gặp

### 12.1. DLT broker hoặc partition không khả dụng

Broker đích có thể mất kết nối, leader partition đang bầu lại hoặc topic DLT chưa được tạo. Producer không thể ghi record nên recoverer ném exception.

Kiểm tra broker availability, partition leader, replication và topic metadata. Nếu dùng partition resolver mặc định, kiểm tra DLT có đủ partition tương ứng.

### 12.2. Authorization

Producer có thể đọc topic nguồn nhưng không có quyền ghi topic DLT. Khi đó listener đã thất bại và recovery cũng thất bại do ACL.

Kiểm tra principal của producer, quyền WRITE/DESCRIBE trên topic DLT và cấu hình security của producer factory dùng bởi recoverer.

### 12.3. Serialization

Payload có thể là object nghiệp vụ, byte array hoặc một kiểu khác sau lỗi deserialize. Nếu KafkaTemplate dùng serializer không hỗ trợ kiểu dữ liệu được recover, DLT publish sẽ thất bại.

Có thể cần cấu hình nhiều serializer hoặc một template có thể xử lý cả payload bình thường và payload lỗi. Cần kiểm tra cả key, value và headers.

### 12.4. Kích thước record

Record nguồn có thể gần giới hạn kích thước broker. Khi thêm exception headers hoặc metadata, DLT record có thể lớn hơn và bị broker từ chối.

Kiểm tra kích thước record sau khi thêm headers, giới hạn producer/broker/topic và thiết kế payload. Không tăng giới hạn một cách tùy tiện nếu payload quá lớn; có thể cần giảm dữ liệu lưu trong record lỗi hoặc lưu payload ở storage khác.

### 12.5. Timeout và kết quả không rõ ràng

Producer có thể gửi record thành công nhưng không nhận được response trong timeout. Recoverer coi lần gửi thất bại và thử lại ở lần delivery tiếp theo. Nếu record DLT đã được ghi, lần recovery sau có thể tạo bản sao DLT.

Vì vậy, DLT consumer nên có event ID hoặc khóa idempotency để phát hiện record trùng. Timeout không chứng minh broker chưa ghi record.

## 13. Quy trình điều tra recovery failure

Khi thấy callback `recoveryFailed` hoặc log recoverer exception, làm theo trình tự:

1. Ghi nhận topic, partition, offset, key và event ID của record nguồn.
2. Ghi nhận exception ban đầu của listener và exception mới từ recoverer.
3. Xác định recoverer nào được gọi, ví dụ DLT publisher hay custom recoverer.
4. Kiểm tra DLT destination, partition, leader và ACL.
5. Kiểm tra serializer, record size và headers.
6. Kiểm tra producer send result, retry, request timeout và delivery timeout.
7. Xác nhận `setFailIfSendResultIsError(true)` đã được bật nếu cần recoverer phát hiện lỗi gửi DLT.
8. Kiểm tra `resetStateOnRecoveryFailure` để biết lần redelivery tiếp theo có chạy lại listener retry cycle hay thử recovery ngay.
9. Đối chiếu committed offset trước/sau recovery failure.
10. Sau khi sửa nguyên nhân, xác nhận record được publish DLT thành công hoặc listener xử lý thành công.
11. Kiểm tra duplicate DLT nếu lần gửi trước timeout nhưng có thể đã được broker ghi.

Không chỉ nhìn exception cuối cùng. Exception ban đầu giải thích vì sao listener không xử lý được; exception recovery giải thích vì sao record không được đưa vào luồng phục hồi dự kiến.

## 14. Kiểm thử reset state khi recovery thất bại

Nên kiểm thử trên Kafka test broker hoặc môi trường tích hợp riêng với topic nguồn, topic DLT và consumer group thử nghiệm.

### 14.1. Kiểm thử mặc định reset state

1. Cấu hình `DefaultErrorHandler` với `FixedBackOff` có số retry nhỏ.
2. Cho listener luôn ném exception.
3. Cho recoverer ném exception ở lần gọi đầu.
4. Xác nhận callback `recoveryFailed` được gọi.
5. Cho recoverer thành công ở lần tiếp theo.
6. Ghi nhận listener được gọi lại theo một chu kỳ BackOff mới khi `resetStateOnRecoveryFailure` là true.
7. Kiểm tra record chỉ được xem là recovered khi recoverer hoàn tất thành công.
8. Kiểm tra committed offset của partition nguồn.

### 14.2. Kiểm thử tắt reset state

1. Dùng cùng BackOff và listener.
2. Cấu hình `setResetStateOnRecoveryFailure(false)`.
3. Cho listener thất bại đến khi BackOff hết.
4. Cho recoverer thất bại.
5. Khởi động lần delivery tiếp theo.
6. Xác nhận handler thử recovery lại mà không chạy thêm chu kỳ retry listener mới.
7. Cho recoverer thành công và xác nhận tiến độ offset theo ack mode.

### 14.3. Kiểm thử DLT publish timeout

1. Tạo tình huống producer không nhận được kết quả xác nhận DLT trong thời hạn.
2. Bật `setFailIfSendResultIsError(true)`.
3. Ghi nhận recovery failure.
4. Xác minh liệu DLT record đã tồn tại hay chưa bằng event ID.
5. Cho lần recovery tiếp theo chạy và kiểm tra duplicate.
6. Xác nhận DLT consumer có thể xử lý idempotent.

### 14.4. Kiểm thử restart và rebalance

1. Cho recoverer thất bại trong khi record chưa được commit.
2. Dừng consumer hoặc gây rebalance có kiểm soát.
3. Khởi động lại cùng group ID.
4. Xác nhận record được giao lại từ committed offset.
5. Xác nhận BackOff state trong bộ nhớ có thể được khởi tạo lại sau restart.
6. Xác nhận recovery không bỏ qua record và duplicate side effect được kiểm soát.

Kiểm thử phải quan sát cả listener invocation, recoverer invocation, DLT content và committed offset. Chỉ kiểm tra số lần log exception là chưa đủ để chứng minh state được reset đúng.

## 15. Metrics và cảnh báo

Nên tách metric listener failure và recovery failure vì hai loại lỗi có nguyên nhân và người xử lý khác nhau.

| Chỉ số | Mục đích |
|---|---|
| Listener delivery failure count | Theo dõi lỗi nghiệp vụ hoặc downstream trong listener |
| Retry attempt count | Theo dõi số lần delivery retry |
| Recovery attempt count | Theo dõi số lần gọi recoverer |
| Recovery failure count | Phát hiện DLT/custom recoverer không hoạt động |
| DLT send success/error | Xác nhận luồng publish dead-letter |
| Time from first failure to recovery | Đo thời gian một record ở trong luồng lỗi |
| Consumer lag | Theo dõi tác động của retry/recovery đến tiến độ group |
| DLT topic lag | Phát hiện DLT có record chưa được xử lý |
| Duplicate DLT event count | Phát hiện gửi lại sau timeout không rõ kết quả |

Có thể dùng `RetryListener` để ghi log và metric theo từng record. Metric label nên có cardinality thấp, ví dụ topic, exception class hoặc outcome. Không dùng event ID, order ID hoặc key làm label metric vì số lượng giá trị có thể tăng không giới hạn.

Cảnh báo nên phân biệt:

- Listener failure tăng nhưng recovery vẫn thành công.
- Recovery failure tăng do DLT broker/ACL/serializer.
- Recovery failure kéo dài khiến consumer lag tăng.
- DLT publish thành công nhưng DLT consumer không xử lý.
- Một record lặp lại recovery failure nhiều lần.

## 16. Các lỗi thiết kế thường gặp

**Nhầm reset BackOff với reset offset:** `resetStateOnRecoveryFailure` không tua consumer group về đầu topic.

**Không kiểm tra kết quả publish DLT:** recoverer có thể không phát hiện lỗi gửi nếu không cấu hình xác nhận phù hợp.

**Đặt false chỉ để giảm retry:** lần delivery tiếp theo sẽ thử recovery lại mà không chạy retry listener cycle mới. Nếu listener cần thời gian phục hồi, cấu hình này có thể không phù hợp.

**Đặt true trong khi listener có side effect không idempotent:** recovery failure có thể khiến listener chạy lại và tạo side effect trùng.

**Không phân biệt exception gốc và exception recovery:** chỉ log exception recoverer sẽ làm mất nguyên nhân ban đầu khiến listener thất bại.

**Không kiểm tra DLT partition count:** resolver mặc định có thể gửi cùng partition index với record nguồn, nên DLT cần đủ partition.

**Coi timeout là chắc chắn chưa gửi:** DLT có thể đã được ghi nhưng response bị mất; lần recovery sau có thể tạo duplicate.

**Không theo dõi callback recoveryFailed:** dashboard chỉ có listener failure sẽ bỏ sót sự cố ở DLT hoặc hệ thống recovery.

**Dùng custom recoverer chỉ ghi log:** nếu log là toàn bộ recovery action, record có thể bị coi là recovered và offset tiến lên dù không có bản lưu bền vững.

**Không kiểm thử process restart:** BackOff tracker không phải kho trạng thái bền vững; restart có thể làm chu kỳ delivery bắt đầu lại theo trạng thái consumer và offset.

## 17. Nguyên tắc vận hành trong production

- Hiểu rõ sự khác nhau giữa listener failure và recovery failure.
- Dùng mặc định `resetStateOnRecoveryFailure=true` khi muốn record có thêm chu kỳ retry listener sau một lần recoverer thất bại.
- Chọn `false` khi muốn lần redelivery tiếp theo thử recovery ngay, không chạy lại chu kỳ retry đã hết.
- Kiểm tra phiên bản Spring Kafka; hành vi reset mặc định thay đổi từ 2.5.5.
- Cấu hình DLT publisher để phát hiện lỗi gửi và đặt timeout xác nhận phù hợp.
- Bảo đảm DLT topic, partition, ACL và serializer sẵn sàng.
- Dùng RetryListener để phân biệt failed delivery, recovered và recoveryFailed.
- Giữ event ID ổn định và làm DLT consumer idempotent để chịu được publish lặp.
- Theo dõi committed offset, consumer lag và DLT lag cùng với recovery failure count.
- Không dùng reset state để thay đổi offset hoặc rollback database.
- Kiểm thử cả hai giá trị true/false, lỗi publish DLT, timeout và process restart trước khi triển khai rộng.

`resetStateOnRecoveryFailure` quyết định cách BackOff tiếp tục sau khi recoverer thất bại. Giá trị mặc định reset chu kỳ để record được thử lại theo chính sách ban đầu; giá trị false bỏ qua chu kỳ retry mới và thử recovery lại ở lần delivery tiếp theo. Lựa chọn cần dựa trên việc listener có nên chạy lại hay recovery mới là phần cần được thử lại, đồng thời phải bảo vệ side effect và xác nhận DLT publish thực sự thành công.
