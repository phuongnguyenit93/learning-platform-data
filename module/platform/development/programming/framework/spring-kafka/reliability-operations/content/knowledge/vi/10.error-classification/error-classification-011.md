# Exception thay đổi giữa các lần retry

Trong Spring Kafka, cùng một record có thể thất bại với những loại exception khác nhau ở các lần giao lại. Ví dụ, lần đầu listener gặp lỗi truy cập database tạm thời, lần tiếp theo gặp timeout khi gọi service, và lần sau nữa gặp một exception được bọc trong exception khác. Sự thay đổi này có thể ảnh hưởng đến cách error handler phân loại lỗi, chọn retry hay recovery, và tiếp tục hoặc khởi động lại chuỗi backoff.

Khi dùng blocking retry với **DefaultErrorHandler**, Spring Kafka theo dõi trạng thái thất bại của record và dùng **BackOff** để quyết định thời điểm giao lại. Thuộc tính **resetStateOnExceptionChange** cho phép điều khiển việc reset trạng thái backoff khi loại exception thay đổi. Hiểu rõ hành vi này giúp tránh retry quá lâu, recovery quá sớm hoặc xử lý nhầm lỗi không thể retry.

## 1. Vì sao exception có thể thay đổi giữa các lần retry?

Retry không đảm bảo lần xử lý tiếp theo sẽ gặp đúng exception trước đó. Mỗi lần listener được gọi lại, code chạy lại trong một trạng thái hệ thống khác:

- Database có thể chuyển từ lỗi kết nối sang lỗi lock hoặc timeout.
- REST API có thể trả lỗi timeout ở lần đầu và lỗi rate limit ở lần sau.
- Một service downstream có thể phục hồi, nhưng bước tiếp theo trong listener lại thất bại.
- Exception nghiệp vụ có thể được bọc bởi exception của framework hoặc adapter.
- Dữ liệu hoặc trạng thái bên ngoài có thể thay đổi giữa các lần giao lại.

Ví dụ:

~~~text
Record: orders-2, offset 105

Lần xử lý đầu:
  Listener -> TransientDataAccessException

Lần retry 1:
  Listener -> SocketTimeoutException

Lần retry 2:
  Listener -> TransientDataAccessException

Lần retry 3:
  Listener -> xử lý thành công
~~~

Các exception khác nhau có thể biểu thị mức độ nghiêm trọng khác nhau. Một lỗi kết nối tạm thời có thể retry, trong khi lỗi dữ liệu không hợp lệ có thể không bao giờ tự phục hồi. Vì vậy, error handler cần xét cả loại exception hiện tại và trạng thái retry đã tích lũy.

## 2. Spring Kafka theo dõi retry state như thế nào?

Với blocking retry, **DefaultErrorHandler** xử lý lỗi sau khi listener thất bại. Handler dùng **BackOff** để xác định khoảng chờ giữa các lần thử lại và theo dõi tiến trình thất bại của từng record.

Có thể hình dung luồng xử lý:

~~~text
Consumer poll record
       |
       v
Listener xử lý record
       |
       +------ Thành công ------> xử lý tiếp
       |
       v
Listener ném exception
       |
       v
DefaultErrorHandler
       |
       v
Phân loại exception
       |
       +------ Không retry ------> Recovery / DLT
       |
       v
Lấy bước tiếp theo của BackOff
       |
       +------ Còn retry -------> giao lại record
       |
       v
BackOff hết bước
       |
       v
Recovery / DLT
~~~

Retry state được theo dõi theo record thất bại, gắn với định danh của record trong partition, chẳng hạn topic, partition và offset. Vì vậy, trạng thái backoff của một record không nên được hiểu là một bộ đếm chung cho toàn bộ consumer group.

Ở lần thất bại tiếp theo, handler có thể so sánh exception hiện tại với exception của lần thất bại trước. Nếu loại exception thay đổi và **resetStateOnExceptionChange** được bật, trạng thái backoff của record được reset để bắt đầu lại chuỗi backoff. Nếu không reset, handler tiếp tục chuỗi backoff đang có, trừ khi exception mới được phân loại là không retryable hoặc có một điều kiện recovery khác.

Retry state của **DefaultErrorHandler** là trạng thái trong bộ nhớ của consumer process. Sau khi ứng dụng restart, record chưa được commit có thể được đọc lại và retry state trong bộ nhớ được tạo lại. Nếu cần lưu lịch sử retry bền vững qua restart, ứng dụng cần một cơ chế lưu trạng thái riêng hoặc dùng một kiến trúc retry phù hợp.

## 3. resetStateOnExceptionChange điều khiển điều gì?

**resetStateOnExceptionChange** là thuộc tính của nhóm xử lý thất bại record trong Spring Kafka. Thuộc tính này quyết định có khởi động lại trạng thái **BackOff** khi exception class thay đổi giữa các lần thất bại của cùng record hay không.

| Cấu hình | Khi exception class thay đổi | Hệ quả |
|---|---|---|
| false | Giữ nguyên tiến trình backoff hiện tại | Số lần retry và các khoảng chờ tiếp tục theo chuỗi đã bắt đầu. |
| true | Reset trạng thái backoff của record | Chuỗi backoff bắt đầu lại từ bước đầu cho exception class mới. |

Ví dụ dùng **FixedBackOff(1000L, 2L)**: chuỗi backoff có hai lần retry, mỗi lần cách nhau một giây. Nếu exception class đổi và reset được bật, bộ đếm backoff bắt đầu lại theo chính sách này. Nếu reset tắt, lần thất bại tiếp theo tiếp tục tiến trình hiện tại.

Hãy đặt thuộc tính tường minh thay vì dựa vào giá trị mặc định không được kiểm tra. Giá trị mặc định và khả năng cấu hình có thể phụ thuộc phiên bản Spring Kafka; cần đối chiếu API của phiên bản đang dùng.

### Khi giữ nguyên backoff state

Chọn không reset khi muốn giới hạn tổng số lần retry theo một chuỗi thất bại của record, kể cả exception thay đổi. Cách này giúp tránh việc exception luân phiên làm bộ đếm backoff liên tục quay về đầu.

Ví dụ:

~~~text
FixedBackOff: 1 giây, tối đa 3 lần retry

Thất bại 1: TimeoutException
  -> chờ 1 giây
Thất bại 2: TransientDataAccessException
  -> chờ 1 giây
Thất bại 3: SocketTimeoutException
  -> chờ 1 giây
Thất bại 4: TimeoutException
  -> hết retry, gọi recoverer
~~~

Ví dụ minh họa chuỗi backoff tiếp tục dù exception class thay đổi. Nếu exception mới thuộc nhóm không retryable, việc phân loại có thể đưa record đến recovery sớm hơn.

### Khi reset backoff state

Chọn reset khi mỗi loại exception mới thể hiện một giai đoạn lỗi khác và ứng dụng muốn cho loại lỗi đó một chuỗi retry riêng.

~~~text
FixedBackOff: 1 giây, tối đa 3 lần retry

Thất bại 1: TimeoutException
  -> bắt đầu chuỗi backoff
Thất bại 2: TimeoutException
  -> tiếp tục chuỗi hiện tại
Thất bại 3: TransientDataAccessException
  -> exception class đổi, reset backoff
  -> bắt đầu lại từ bước đầu
Thất bại 4: TransientDataAccessException
  -> tiếp tục chuỗi mới
~~~

Reset hữu ích nếu exception class mới biểu thị một điều kiện phục hồi khác. Nhưng nếu exception thay đổi liên tục, chuỗi retry có thể bị khởi động lại nhiều lần và kéo dài thời gian xử lý record. Vì vậy, cần có giới hạn thời gian tổng thể, giám sát số lần retry và recovery rõ ràng.

## 4. Exception classification vẫn quyết định retry hay recovery

Reset backoff và phân loại exception là hai quyết định khác nhau:

- **Classification** quyết định exception có được retry hay phải recovery ngay.
- **BackOff state** quyết định nếu retry thì chờ bao lâu và còn bao nhiêu bước trong chuỗi hiện tại.
- **Recovery** quyết định phải làm gì khi không retry nữa, chẳng hạn publish record sang dead-letter topic.

**DefaultErrorHandler** có danh sách một số exception mặc định được xem là fatal/non-retryable, ví dụ các lỗi liên quan đến deserialize, message conversion, method argument resolution, thiếu method và class cast. Các lỗi dữ liệu hoặc cấu hình thường không tự hết khi chờ, nên retry có thể không hữu ích.

Có thể bổ sung phân loại riêng:

~~~java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 3L));

errorHandler.addNotRetryableExceptions(
        IllegalArgumentException.class,
        InvalidOrderException.class);

errorHandler.addRetryableExceptions(
        TransientDataAccessException.class,
        DownstreamTimeoutException.class);
~~~

Đoạn mã minh họa việc cấu hình exception có thể retry và exception không nên retry. Cần import các exception thực tế của ứng dụng và kiểm tra API phù hợp với phiên bản Spring Kafka.

Nếu exception class đổi từ một lỗi retryable sang lỗi non-retryable, error handler có thể chuyển sang recovery ngay theo classification. Việc bật **resetStateOnExceptionChange** không biến một exception non-retryable thành retryable và không ghi đè quy tắc phân loại.

Ngược lại, nếu exception class đổi từ non-retryable sang retryable, quyết định thực tế phụ thuộc exception được ném ra ở lần giao hiện tại và quy tắc classifier. Không nên giả định trạng thái của exception trước sẽ quyết định mọi lần retry tiếp theo.

## 5. Cấu hình DefaultErrorHandler trong Spring Kafka

Ví dụ dưới đây cấu hình blocking retry, dead-letter recovery, phân loại lỗi và reset backoff khi exception class thay đổi:

~~~java
@Configuration
public class KafkaErrorHandlingConfiguration {

    @Bean
    public DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

        DefaultErrorHandler errorHandler =
                new DefaultErrorHandler(recoverer, backOff);

        errorHandler.addNotRetryableExceptions(
                IllegalArgumentException.class,
                InvalidOrderException.class);

        errorHandler.addRetryableExceptions(
                TransientDataAccessException.class,
                SocketTimeoutException.class);

        errorHandler.setResetStateOnExceptionChange(true);

        return errorHandler;
    }
}
~~~

Đăng ký handler cho listener container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Trong ví dụ:

- **FixedBackOff(1_000L, 3L)** định nghĩa khoảng chờ một giây và tối đa ba lần retry trong một chuỗi backoff.
- **addNotRetryableExceptions()** đánh dấu lỗi dữ liệu/nghiệp vụ không cần retry.
- **addRetryableExceptions()** bổ sung lỗi hạ tầng có thể phục hồi.
- **setResetStateOnExceptionChange(true)** khởi động lại chuỗi backoff nếu exception class của cùng record thay đổi.
- **DeadLetterPublishingRecoverer** là recovery callback gửi record không thể xử lý sang dead-letter topic theo quy tắc định tuyến của recoverer.

Kiểu **KafkaTemplate** phải phù hợp với key/value serializer và cấu hình của ứng dụng. Ví dụ dùng **KafkaTemplate<Object, Object>** để minh họa; không sao chép nguyên kiểu này nếu producer factory của dự án dùng kiểu khác.

Nếu muốn tiếp tục backoff khi exception class thay đổi, đặt:

~~~java
errorHandler.setResetStateOnExceptionChange(false);
~~~

Nên ghi rõ quyết định này trong cấu hình vì nó ảnh hưởng đến tổng thời gian record có thể nằm trong retry loop.

## 6. Wrapper exception và cause chain

Một nguyên nhân dễ gây nhầm lẫn là exception bên ngoài có thể thay đổi dù nguyên nhân gốc gần như giống nhau. Framework, serializer, converter hoặc adapter có thể bọc exception gốc trong một exception khác.

Ví dụ:

~~~text
Lần 1:
  ListenerExecutionFailedException
      caused by SocketTimeoutException

Lần 2:
  ListenerExecutionFailedException
      caused by ResourceAccessException
          caused by SocketTimeoutException
~~~

Ở đây exception bên ngoài vẫn là **ListenerExecutionFailedException**, nhưng cause chain thay đổi. Trường hợp khác, exception ngoài có thể chuyển từ một wrapper sang wrapper khác trong khi root cause vẫn là timeout.

Khi điều tra, hãy ghi nhận:

- Exception class ở lớp ngoài cùng.
- Root cause hoặc cause chain.
- Topic, partition và offset của record.
- Delivery attempt hiện tại.
- Thời gian từ lần thất bại trước.
- Listener và dependency đang thực hiện.

Không nên chỉ dựa vào thông báo exception hoặc chuỗi message để quyết định retry. Message text có thể thay đổi giữa phiên bản thư viện, ngôn ngữ hoặc request. Hãy phân loại theo loại exception và ý nghĩa lỗi; nếu wrapper không ổn định, chuẩn hóa exception ở ranh giới adapter hoặc cấu hình classifier phù hợp với cause chain.

Việc phân loại theo exception class cần được kiểm chứng với cách Spring Kafka phiên bản hiện tại duyệt cause chain. Nếu ứng dụng dùng nhiều wrapper, hãy kiểm thử trường hợp wrapper thay đổi nhưng root cause giữ nguyên để biết classifier và **resetStateOnExceptionChange** đang quan sát lớp exception nào.

## 7. Thiết kế exception hierarchy cho retry

Một hệ thống có nhiều loại lỗi nên có exception hierarchy thể hiện rõ khả năng phục hồi:

~~~text
ApplicationException
  |
  +-- RetryableApplicationException
  |      |
  |      +-- TemporaryDatabaseException
  |      +-- DownstreamTimeoutException
  |      +-- TemporaryRateLimitException
  |
  +-- NonRetryableApplicationException
         |
         +-- InvalidOrderException
         +-- UnsupportedEventVersionException
         +-- BusinessRuleViolationException
~~~

Ví dụ:

~~~java
public abstract class RetryableApplicationException
        extends RuntimeException {

    protected RetryableApplicationException(
            String message, Throwable cause) {
        super(message, cause);
    }
}

public class DownstreamTimeoutException
        extends RetryableApplicationException {

    public DownstreamTimeoutException(
            String message, Throwable cause) {
        super(message, cause);
    }
}

public abstract class NonRetryableApplicationException
        extends RuntimeException {

    protected NonRetryableApplicationException(String message) {
        super(message);
    }
}

public class InvalidOrderException
        extends NonRetryableApplicationException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

Listener hoặc adapter nên chuyển lỗi thư viện thành exception của ứng dụng tại ranh giới phù hợp:

~~~java
public void process(OrderEvent event) {
    try {
        paymentClient.authorize(event);
    }
    catch (SocketTimeoutException ex) {
        throw new DownstreamTimeoutException(
                "Payment authorization timed out", ex);
    }
}
~~~

Chuẩn hóa exception giúp error handler không phụ thuộc quá nhiều vào class nội bộ của thư viện HTTP hoặc database. Tuy nhiên, không bọc tất cả lỗi thành một exception retryable chung. Nếu lỗi dữ liệu hoặc lỗi nghiệp vụ bị bọc thành lỗi tạm thời, hệ thống có thể retry vô ích và làm tăng backlog.

## 8. Backoff, số lần retry và nguy cơ reset lặp

Backoff xác định khoảng chờ giữa các lần giao lại. Spring Kafka hỗ trợ các implementation của Spring Framework như **FixedBackOff** và các chiến lược exponential backoff.

Ví dụ exponential backoff:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(5);
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(recoverer, backOff);
~~~

Khoảng chờ tăng dần giúp tránh gọi dependency đang lỗi liên tục. **maxInterval** giới hạn thời gian chờ mỗi lần retry, còn số retry giới hạn độ dài chuỗi backoff.

Khi **resetStateOnExceptionChange=true**, mỗi lần exception class thay đổi, chuỗi backoff có thể bắt đầu lại. Nếu lỗi luân phiên giữa nhiều class:

~~~text
TimeoutException
  -> retry
ResourceAccessException
  -> reset, retry
DataAccessException
  -> reset, retry
TimeoutException
  -> reset, retry
~~~

Một chuỗi backoff hữu hạn có thể bị khởi động lại nhiều lần nếu exception class liên tục thay đổi. Do đó, không nên chỉ dựa vào số retry trong một chuỗi để giới hạn tổng thời gian xử lý record khi bật reset. Hãy bổ sung một giới hạn thời gian tổng thể, theo dõi delivery attempt và bảo đảm cuối cùng có recovery hoặc quy trình xử lý thủ công.

Nếu yêu cầu nghiệp vụ là record chỉ được retry tối đa một khoảng thời gian xác định, hãy chọn chính sách giới hạn theo thời gian hoặc lưu retry deadline bền vững. Có thể cần một lớp kiểm soát riêng nếu backoff reset theo exception làm vượt giới hạn thời gian nghiệp vụ.

## 9. Retry listener và quan sát exception thay đổi

Khi exception thay đổi giữa các lần retry, log chỉ ghi thông báo "listener failed" là chưa đủ. Cần quan sát record identity, delivery attempt và exception type để hiểu vì sao backoff tiếp tục hoặc reset.

Spring Kafka cung cấp **RetryListener** để nhận thông tin về lần giao thất bại, recovery thành công và recovery thất bại. Ví dụ:

~~~java
errorHandler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        log.warn(
                "Kafka delivery failed: topic={}, partition={}, offset={}, " +
                "attempt={}, exception={}",
                record.topic(),
                record.partition(),
                record.offset(),
                deliveryAttempt,
                exception.getClass().getName());
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {

        log.info(
                "Kafka record recovered: topic={}, partition={}, offset={}, exception={}",
                record.topic(),
                record.partition(),
                record.offset(),
                exception.getClass().getName());
    }
});
~~~

Các callback và chữ ký method có thể khác theo phiên bản Spring Kafka. Hãy dùng interface của đúng phiên bản dependency trong dự án.

Nên thu thập các thông tin sau:

- Số lần delivery attempt trên mỗi record.
- Exception class và root cause.
- Số lần exception class thay đổi.
- Số lần backoff được reset nếu ứng dụng có thể quan sát sự kiện này.
- Tổng thời gian từ lần thất bại đầu đến recovery.
- Số record được publish sang DLT.
- Số lần recovery thất bại.

Không dùng topic, partition và offset làm metric label có cardinality cao. Các thông tin này phù hợp với log hoặc trace; metric nên dùng nhãn có tập giá trị giới hạn như listener ID, exception category và outcome.

## 10. Recovery và dead-letter topic

Khi hết retry hoặc exception được phân loại non-retryable, **DefaultErrorHandler** gọi recoverer. Recoverer có thể bỏ qua record theo chính sách, ghi log, hoặc publish record sang dead-letter topic (DLT).

**DeadLetterPublishingRecoverer** thường được dùng để gửi record lỗi đến topic đích. Quy tắc mặc định thường tạo topic có hậu tố DLT và giữ partition tương ứng khi topic đích có đủ partition. Trong production, cần cấu hình rõ routing, serializer, quyền ghi và số partition của DLT.

Recovery phải được quan sát như một bước riêng. Việc handler đã hết retry không có nghĩa record đã được xử lý thành công. Nếu publish DLT thất bại, ứng dụng cần chính sách cho recovery failure. Spring Kafka có thuộc tính **resetStateOnRecoveryFailure** để điều khiển trạng thái backoff khi recovery thất bại; đây là quyết định riêng với **resetStateOnExceptionChange**.

Không nên đánh đồng:

- Exception class thay đổi giữa các lần xử lý.
- Recovery callback ném exception.
- Record publish DLT thành công.

Ba sự kiện này có ảnh hưởng khác nhau đến retry state và kết quả cuối cùng. Hãy log và theo dõi riêng để tránh báo cáo nhầm record đã được recover khi thực tế DLT publish thất bại.

## 11. Blocking retry và non-blocking retry

**resetStateOnExceptionChange** liên quan đến state backoff của cơ chế blocking retry trong error handler như **DefaultErrorHandler**.

Với non-blocking retry dùng **@RetryableTopic**, record lỗi được chuyển tiếp sang retry topic theo các khoảng delay và số lần thử được cấu hình. Luồng này tạo các topic retry riêng, và mỗi lần tiêu thụ lại là một lần record được chuyển qua topology retry. Không nên giả định **resetStateOnExceptionChange** điều khiển lịch retry topic theo cùng cách với **DefaultErrorHandler**.

Ví dụ:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000))
@KafkaListener(
        topics = "orders",
        groupId = "orders-service")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Non-blocking retry phù hợp khi không muốn một partition bị chặn lâu bởi một record lỗi và có thể chấp nhận việc record retry được xử lý theo topology riêng. Tuy nhiên, nó có tác động đến thứ tự: record tiếp theo ở topic gốc có thể được xử lý trước khi record trước đó hoàn tất ở retry topic. Nếu nghiệp vụ cần thứ tự nghiêm ngặt, cần cân nhắc blocking retry hoặc thiết kế lại luồng xử lý.

Hãy chọn một mô hình retry phù hợp với yêu cầu ordering, throughput và khả năng vận hành. Không cấu hình nhiều cơ chế retry chồng lên nhau mà không hiểu số lần thử tổng thể và thời gian tối đa record có thể tồn tại.

## 12. Kiểm thử exception thay đổi giữa các lần retry

Nên kiểm thử hành vi của error handler với cùng một record và các exception class khác nhau. Có thể dùng listener giả lập số lần thất bại:

~~~java
AtomicInteger attempts = new AtomicInteger();

@KafkaListener(topics = "orders", groupId = "orders-test")
public void handle(OrderEvent event) {
    int attempt = attempts.incrementAndGet();

    if (attempt == 1) {
        throw new DownstreamTimeoutException(
                "first attempt", new SocketTimeoutException("timeout"));
    }
    if (attempt == 2) {
        throw new TransientDataAccessException("second attempt") { };
    }

    process(event);
}
~~~

Đây là ví dụ minh họa hành vi listener; trong test thực tế nên cô lập bộ đếm theo event ID và không dùng một **AtomicInteger** toàn cục nếu nhiều record được xử lý đồng thời.

Các tình huống nên kiểm thử:

1. Cùng một exception class ở mọi lần retry: backoff tiếp tục theo chuỗi.
2. Exception class đổi, reset tắt: backoff tiếp tục theo chuỗi cũ.
3. Exception class đổi, reset bật: backoff bắt đầu lại theo chính sách.
4. Exception đổi sang loại non-retryable: handler chuyển recovery theo classification.
5. Exception được bọc trong wrapper khác: xác nhận classifier xử lý cause chain theo cấu hình.
6. Recovery callback thất bại: kiểm tra chính sách reset recovery và hành vi giao lại.
7. Ứng dụng restart giữa các lần retry: xác nhận record được đọc lại và retry state trong bộ nhớ được tạo lại.
8. Exception class luân phiên: kiểm tra giới hạn thời gian tổng thể và số lần recovery.

Để kiểm tra thời gian backoff, có thể dùng **BackOff** có khoảng chờ ngắn trong test hoặc spy vào recoverer và retry listener. Tránh kiểm thử bằng sleep dài; nên dùng cơ chế đồng bộ hóa và timeout có giới hạn để test ổn định.

## 13. Những hiểu nhầm thường gặp

**Exception đổi class thì Spring Kafka luôn bắt đầu lại retry.** Không nên giả định như vậy. Hành vi phụ thuộc **resetStateOnExceptionChange** và phiên bản Spring Kafka. Hãy cấu hình tường minh và kiểm thử.

**Reset backoff làm exception mới trở thành retryable.** Không đúng. Classification vẫn quyết định lỗi có được retry hay phải recovery.

**Chỉ cần nhìn root cause là đủ.** Không đúng. Error handler có thể quan sát exception wrapper; cause chain và classifier có hành vi riêng. Cần ghi nhận cả outer exception lẫn root cause.

**Số lần retry trong FixedBackOff luôn là tổng số lần thử tối đa của record.** Không đúng khi trạng thái backoff có thể được reset nhiều lần do exception class thay đổi hoặc recovery failure. Cần xét chính sách reset và giới hạn thời gian tổng thể.

**Retry listener và recoverer là cùng một callback.** Không đúng. Retry listener quan sát các lần thất bại và recovery; recoverer thực hiện hành động xử lý record sau khi retry kết thúc hoặc bị bỏ qua.

**Publish sang DLT nghĩa là nghiệp vụ đã thành công.** Không đúng. DLT chỉ xác nhận record được chuyển sang luồng xử lý lỗi nếu publish thành công. Nghiệp vụ vẫn cần được điều tra và replay hoặc xử lý thủ công.

**Non-blocking retry topic chịu cùng quy tắc backoff state với DefaultErrorHandler.** Không đúng. Retry topic sử dụng topology và lịch chuyển tiếp riêng; cần đánh giá exception và ordering theo mô hình đó.

## 14. Hướng dẫn lựa chọn chính sách

Khi thiết kế retry cho listener Spring Kafka, hãy phân biệt lỗi tạm thời với lỗi không thể tự phục hồi, sau đó quyết định exception class thay đổi có nên khởi động lại backoff hay không.

Một quy trình cấu hình có thể bắt đầu như sau:

1. Xác định exception thực tế listener có thể ném ra, gồm wrapper và cause chain.
2. Chuẩn hóa exception ở ranh giới ứng dụng để phân biệt lỗi tạm thời và lỗi nghiệp vụ.
3. Cấu hình classification cho retryable và non-retryable exception.
4. Chọn **BackOff** có số lần retry, khoảng chờ và giới hạn phù hợp.
5. Quyết định **resetStateOnExceptionChange** dựa trên ý nghĩa của exception mới.
6. Nếu bật reset, đặt thêm giới hạn thời gian tổng thể và giám sát exception luân phiên.
7. Cấu hình recoverer và DLT routing rõ ràng.
8. Theo dõi delivery attempt, exception class, root cause, recovery outcome và tổng thời gian xử lý.
9. Kiểm thử exception thay đổi, wrapper thay đổi, recovery failure và restart.
10. Ghi rõ chính sách retry để vận hành biết khi nào record sẽ được giao lại, khi nào được đưa vào DLT và khi nào cần can thiệp.

Exception thay đổi giữa các lần retry là một phần bình thường của hệ thống phân tán. **resetStateOnExceptionChange** chỉ điều khiển việc bắt đầu lại backoff khi loại exception thay đổi; nó không thay thế phân loại lỗi, giới hạn thời gian, recovery hoặc idempotency. Một chính sách đáng tin cậy phải kiểm soát cả loại lỗi hiện tại, tiến trình retry và hành động cuối cùng với record.
