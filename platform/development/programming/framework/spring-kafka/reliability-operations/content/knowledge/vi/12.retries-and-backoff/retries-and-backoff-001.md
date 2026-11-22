# Blocking retry

Trong Spring Kafka, blocking retry là cách xử lý lỗi bằng việc thử lại record ngay trong luồng tiêu thụ của consumer listener container. Khi listener ném exception, error handler chờ theo chính sách backoff rồi giao lại record để xử lý. Consumer chưa chuyển hẳn record lỗi sang một retry topic riêng; record vẫn thuộc luồng xử lý của consumer group ban đầu.

Blocking retry phù hợp với lỗi tạm thời có khả năng phục hồi sau một khoảng chờ ngắn, đặc biệt khi ứng dụng cần giữ thứ tự xử lý trong partition. Đổi lại, consumer thread phải dành thời gian cho record lỗi. Nếu retry kéo dài, các partition khác được giao cho cùng consumer cũng có thể bị chậm, consumer lag tăng và group có nguy cơ rebalance nếu thời gian xử lý vượt giới hạn cấu hình.

## 1. Blocking retry hoạt động như thế nào?

Trong Spring Kafka, listener container gọi listener để xử lý record. Nếu listener hoàn tất bình thường, container tiếp tục xử lý theo cơ chế poll và commit offset đã cấu hình. Nếu listener ném exception, error handler nhận lỗi và quyết định có retry hay recovery.

Với record listener và cơ chế seek mặc định của DefaultErrorHandler, luồng khái quát như sau:

~~~text
Kafka consumer poll
        |
        v
Listener nhận record
        |
        +------ Thành công ------> tiếp tục xử lý
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
BackOff chờ
        |
        v
Consumer giao lại record
        |
        +------ Thành công ------> tiếp tục xử lý
        |
        +------ Thất bại -------> lặp theo BackOff
                                      |
                                      v
                                Hết retry
                                      |
                                      v
                                Recovery / DLT
~~~

Blocking có nghĩa là luồng tiêu thụ phải chờ quá trình retry của record được giải quyết theo error handler. Với cách xử lý đồng bộ thông thường, listener thread không tiếp tục xử lý công việc tiếp theo trong thời gian chờ backoff.

Trong cấu hình seek mặc định, error handler đưa offset của record lỗi và các record còn lại cần xử lý lại về vị trí thích hợp để consumer có thể giao lại chúng trong các lần poll tiếp theo. Vì vậy, record lỗi có thể được thử lại mà không cần tạo một bản sao ở topic khác.

Spring Kafka cũng hỗ trợ cách giữ record trong bộ nhớ thay vì seek thông qua cấu hình seek-after-error phù hợp. Dù dùng cách nào, đây vẫn là blocking retry nếu listener container phải chờ record lỗi được retry hoặc recovery trước khi tiến trình xử lý tiếp tục theo chính sách.

## 2. DefaultErrorHandler và BackOff

Với các phiên bản Spring Kafka hiện đại, DefaultErrorHandler là error handler phổ biến cho listener container không dùng transaction. Handler nhận một BackOff để xác định khoảng chờ và số lần retry, cùng một recoverer để xử lý record khi không retry nữa.

Hai thành phần quan trọng:

- **BackOff**: xác định thời gian chờ giữa các lần giao lại và thời điểm chuỗi retry kết thúc.
- **ConsumerRecordRecoverer**: thực hiện hành động sau khi retry hết hoặc lỗi được phân loại là không retryable, ví dụ ghi log hoặc publish record sang dead-letter topic.

Ví dụ dùng FixedBackOff:

~~~java
FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(backOff);
~~~

Trong ví dụ, khoảng chờ là một giây và có tối đa hai lần retry bổ sung sau lần xử lý ban đầu. Tổng cộng listener có thể được gọi ba lần cho record nếu cả ba lần đều thất bại theo cùng chuỗi backoff và exception vẫn được phép retry.

Không nhầm số lần retry với tổng số lần giao. Với FixedBackOff, tham số maxAttempts biểu thị số lần thử lại sau lần đầu. Ví dụ maxAttempts bằng 2 nghĩa là một lần ban đầu cộng hai lần retry.

Có thể dùng exponential backoff để tăng dần khoảng chờ:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(backOff);
~~~

Với cấu hình minh họa, khoảng chờ bắt đầu từ 500 ms, tăng theo hệ số 2 và không vượt quá 10 giây. Exponential backoff giúp giảm áp lực lên dependency đang gặp sự cố, vì các lần retry không dồn dập với cùng một tần suất.

Nếu không cung cấp recoverer, handler có thể dùng hành vi mặc định để ghi nhận record đã hết retry. Trong production, nên cấu hình hành động recovery rõ ràng để biết record được xử lý tiếp ra sao.

## 3. Cấu hình blocking retry trong Spring Kafka

Ví dụ dưới đây dùng FixedBackOff, phân loại exception và dead-letter recovery:

~~~java
@Configuration
public class KafkaErrorHandlerConfiguration {

    @Bean
    public DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

        DefaultErrorHandler errorHandler =
                new DefaultErrorHandler(recoverer, backOff);

        errorHandler.addNotRetryableExceptions(
                IllegalArgumentException.class,
                InvalidOrderException.class);

        errorHandler.addRetryableExceptions(
                SocketTimeoutException.class,
                TransientDataAccessException.class);

        return errorHandler;
    }
}
~~~

Đăng ký error handler với listener container factory:

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

Listener sử dụng factory:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "kafkaListenerContainerFactory")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Trong ví dụ:

- FixedBackOff chờ một giây giữa các lần thử và cho phép hai lần retry sau lần đầu.
- SocketTimeoutException và TransientDataAccessException được xem là lỗi có thể retry.
- IllegalArgumentException và InvalidOrderException không retry vì thường biểu thị dữ liệu hoặc nghiệp vụ không hợp lệ.
- DeadLetterPublishingRecoverer chuyển record sang dead-letter topic khi handler recovery record.
- setCommonErrorHandler áp dụng handler cho các listener dùng container factory này.

Các kiểu KafkaTemplate, serializer, deserializer và exception phải phù hợp với ứng dụng. Đoạn mã minh họa cấu trúc cấu hình; cần bổ sung import và các bean hạ tầng tương ứng trong dự án.

### Cấu hình trong application.yml

Một số thuộc tính consumer cơ bản có thể được khai báo bằng Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      properties:
        "[max.poll.interval.ms]": 300000
        "[max.poll.records]": 100
    listener:
      ack-mode: record
~~~

Cấu hình trên minh họa group ID, tắt auto commit để container quản lý commit, giới hạn số record mỗi poll và chọn ack mode. Chính sách blocking retry cụ thể vẫn được cấu hình trong DefaultErrorHandler hoặc error handler tương ứng, không phải chỉ bằng các thuộc tính này.

## 4. Exception classification: lỗi nào được retry?

Không phải mọi exception đều nên retry. Retry hữu ích khi nguyên nhân có khả năng tự phục hồi, chẳng hạn network timeout ngắn hoặc database tạm thời không nhận kết nối. Với lỗi dữ liệu, lỗi schema, lỗi phân quyền hoặc vi phạm quy tắc nghiệp vụ, retry thường chỉ làm chậm partition.

DefaultErrorHandler có cơ chế phân loại exception. Một số exception như lỗi deserialize, message conversion hoặc lỗi gọi method không hợp lệ thường được xem là fatal/non-retryable theo mặc định. Ứng dụng có thể bổ sung quy tắc:

~~~java
errorHandler.addNotRetryableExceptions(
        InvalidOrderException.class,
        UnsupportedEventVersionException.class);

errorHandler.addRetryableExceptions(
        TemporaryDatabaseException.class,
        DownstreamTimeoutException.class);
~~~

Nên xây dựng exception hierarchy thể hiện khả năng phục hồi:

~~~text
ApplicationException
  |
  +-- RetryableException
  |      +-- TemporaryDatabaseException
  |      +-- DownstreamTimeoutException
  |
  +-- NonRetryableException
         +-- InvalidOrderException
         +-- UnsupportedEventVersionException
~~~

Adapter của database hoặc HTTP client có thể chuyển exception thư viện thành exception ứng dụng. Việc chuẩn hóa giúp error handler không phụ thuộc quá nhiều vào implementation cụ thể của dependency.

Không bọc mọi exception thành RetryableException. Nếu lỗi nghiệp vụ không thể phục hồi bị phân loại nhầm là retryable, một record xấu có thể giữ partition quá lâu và làm consumer lag tăng.

## 5. Blocking retry ảnh hưởng đến partition như thế nào?

Một consumer có thể sở hữu nhiều partition. Khi listener xử lý đồng bộ và một record trong một partition thất bại, consumer thread phải xử lý retry và backoff. Trong khoảng chờ, thread đó không thể tiếp tục thực thi listener cho các partition khác được giao cho cùng consumer.

Ví dụ consumer A sở hữu P0, P1 và P2:

~~~text
Consumer A
  |
  +-- P0: record lỗi -> retry chờ 10 giây
  |
  +-- P1: record mới -> chờ consumer thread
  |
  +-- P2: record mới -> chờ consumer thread
~~~

Trong ví dụ, P1 và P2 có thể bị trì hoãn dù bản thân chúng không có lỗi. Đây là tác động quan trọng của blocking retry: thời gian chờ của một record có thể ảnh hưởng đến mọi partition dùng chung consumer thread.

Nếu topic có nhiều partition và consumer concurrency thấp, một consumer thường sở hữu nhiều partition. Khi đó, một record lỗi có thể làm nhiều partition cùng bị chậm. Tăng concurrency có thể giảm số partition trên mỗi consumer nếu vẫn còn partition chưa được khai thác, nhưng tạo thêm thread cũng làm tăng tài nguyên và rebalance.

Không thể chia một partition cho nhiều consumer trong cùng group chỉ bằng cách tăng concurrency. Nếu một partition bị giữ bởi record lỗi, thêm consumer member không giúp consumer khác nhận cùng partition để bỏ qua record đó.

## 6. Blocking retry và thứ tự record

Kafka bảo đảm thứ tự record trong một partition. Blocking retry thường phù hợp khi cần giữ thứ tự này, vì record lỗi được xử lý lại trước khi consumer tiếp tục tiến qua các record sau của partition theo cơ chế container.

Ví dụ:

~~~text
Partition P0:
  offset 10: OrderCreated
  offset 11: OrderPaid
  offset 12: OrderShipped

offset 10 thất bại:
  retry offset 10
  retry offset 10
  xử lý thành công offset 10

Sau đó mới tiếp tục offset 11 và 12
~~~

Điều này quan trọng khi event sau phụ thuộc trạng thái do event trước tạo ra. Nếu chuyển record lỗi sang retry topic và tiếp tục xử lý topic gốc, record ở offset sau có thể được xử lý trước record lỗi. Đây là trade-off chính giữa blocking retry và non-blocking retry.

Tuy nhiên, blocking retry không tự bảo đảm side effect chỉ chạy một lần. Listener có thể đã ghi database hoặc gọi API thành công rồi mới ném exception ở bước tiếp theo. Khi retry, side effect đầu tiên có thể được thực hiện lần nữa. Vì vậy, các thao tác nghiệp vụ vẫn cần idempotency key, event ID hoặc transaction phù hợp.

## 7. Backoff và thời gian chờ

Backoff quyết định khoảng thời gian giữa các lần thử. Chọn backoff dựa trên thời gian dependency cần phục hồi và giới hạn latency mà nghiệp vụ chấp nhận.

| Chiến lược | Hành vi | Trường hợp sử dụng |
|---|---|---|
| FixedBackOff | Chờ một khoảng cố định giữa các lần retry | Lỗi ngắn, thời gian phục hồi tương đối ổn định |
| Exponential backoff | Tăng khoảng chờ sau mỗi lần thất bại | Dependency có thể cần thời gian phục hồi tăng dần |
| Exponential backoff có max interval | Tăng dần nhưng giới hạn thời gian chờ mỗi lần | Muốn giảm áp lực nhưng vẫn giới hạn độ trễ |
| Custom BackOff | Tự xác định lịch retry | Chính sách nghiệp vụ hoặc thời gian retry đặc thù |

Ví dụ FixedBackOff:

~~~java
new FixedBackOff(2_000L, 3L);
~~~

Ví dụ này có khoảng chờ hai giây và tối đa ba lần retry bổ sung. Nếu cả ba lần retry đều thất bại và exception vẫn được phép retry, handler gọi recoverer sau khi backoff hết.

Không nên đặt thời gian chờ quá dài chỉ để tăng xác suất thành công. Trong thời gian đó, consumer thread có thể bị giữ lại, lag tiếp tục tăng và các partition khác cùng consumer bị trì hoãn.

## 8. Thread sleep và ContainerPausingBackOffHandler

Với blocking retry, handler cần thực hiện backoff. Cách đơn giản là chờ trên consumer thread. Nếu thời gian chờ dài, thread không gọi poll trong thời gian đó; điều này có thể tương tác xấu với max.poll.interval.ms và khiến consumer bị loại khỏi group.

Spring Kafka cung cấp ContainerPausingBackOffHandler để dùng pause/resume listener container trong lúc chờ backoff dài. Container tiếp tục thực hiện poll theo cơ chế cần thiết trong thời gian pause, giúp tránh việc consumer bị coi là không poll đúng hạn chỉ vì đang chờ retry.

Để sử dụng, cấu hình một instance ContainerPausingBackOffHandler làm BackOffHandler cho DefaultErrorHandler, cùng một BackOff có khoảng chờ phù hợp. Cách khởi tạo và wiring cụ thể cần theo API của phiên bản Spring Kafka đang dùng; hãy kiểm tra constructor và overload DefaultErrorHandler trong dependency của dự án trước khi sao chép cấu hình.

Với backoff dài, đây là lựa chọn cần cân nhắc thay cho việc giữ consumer thread trong một khoảng sleep dài.

Pause container không làm record được xử lý nhanh hơn và cũng không loại bỏ thời gian chờ. Nó chỉ thay đổi cách container chờ, duy trì vòng poll và phối hợp pause/resume. Cần đo thời gian pause thực tế và bảo đảm listener container có thể tiếp tục xử lý đúng lịch.

## 9. max.poll.interval.ms và blocking retry

max.poll.interval.ms giới hạn khoảng thời gian tối đa giữa các lần gọi poll của consumer trong classic consumer group protocol. Nếu thời gian xử lý record và backoff khiến consumer không gọi poll trong giới hạn này, consumer có thể bị xem là không tiến triển và rời group.

Ví dụ:

~~~text
max.poll.interval.ms = 60 giây

Listener xử lý:       10 giây
Blocking backoff:     40 giây
Retry xử lý:          15 giây
--------------------------------
Tổng:                 65 giây
~~~

Trong ví dụ, tổng thời gian giữa các lần poll có thể vượt 60 giây. Consumer có nguy cơ bị loại khỏi group và partition được giao cho member khác.

Khi đánh giá cấu hình, cần tính cả:

- Thời gian xử lý listener bình thường.
- Tổng thời gian backoff của các lần retry.
- Thời gian xử lý lại record sau mỗi lần backoff.
- Thời gian xử lý các record còn lại trong poll batch.
- Thời gian callback hoặc thao tác đồng bộ liên quan.

Tăng max.poll.interval.ms có thể phù hợp nếu thời gian xử lý dài là yêu cầu hợp lệ, nhưng nó chỉ tăng ngưỡng chờ trước khi consumer bị xem là không tiến triển. Nó không cải thiện throughput và không xử lý nguyên nhân dependency chậm. Với backoff dài, cân nhắc ContainerPausingBackOffHandler hoặc non-blocking retry.

## 10. Recovery sau khi hết retry

Khi BackOff hết bước hoặc exception được phân loại non-retryable, error handler gọi recoverer. Một số lựa chọn:

- Ghi log và bỏ qua record theo chính sách được chấp thuận.
- Publish record cùng metadata lỗi sang dead-letter topic.
- Ghi record vào kho lỗi để người vận hành điều tra.
- Gọi một recovery service có idempotency và audit.

Ví dụ dùng DeadLetterPublishingRecoverer:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L));
~~~

Theo cấu hình mặc định phổ biến, recoverer có thể định tuyến record sang topic có hậu tố DLT và partition tương ứng. Trong production, cần xác định rõ:

- DLT topic có tồn tại và đủ partition hay không.
- Producer có serializer phù hợp với key/value và header hay không.
- Ứng dụng có quyền ghi vào DLT không.
- Metadata exception, original topic, partition, offset và timestamp có được giữ lại để điều tra không.
- Nếu publish DLT thất bại, record sẽ được xử lý lại như thế nào.

Không được xem việc gọi recoverer là bằng chứng DLT đã ghi thành công. Cần quan sát kết quả publish và cấu hình recovery failure theo phiên bản Spring Kafka.

## 11. Ack mode và commit offset

Blocking retry liên quan trực tiếp đến thời điểm offset được commit. Nếu listener thất bại, container không nên commit offset vượt qua record chưa được xử lý hoặc chưa được recovery thành công.

Spring Kafka hỗ trợ nhiều ack mode, chẳng hạn RECORD, BATCH, TIME, COUNT, COUNT_TIME, MANUAL và MANUAL_IMMEDIATE. Mỗi mode có quy tắc commit riêng. Cần hiểu mode của container và cách error handler xử lý record recovered.

Với xử lý record thông thường:

1. Consumer poll record.
2. Listener xử lý record.
3. Nếu thành công, container đánh dấu offset theo ack mode.
4. Nếu thất bại, error handler retry hoặc recovery.
5. Khi record được recovery thành công, container xử lý commit offset theo cấu hình của handler và container.

Nếu ứng dụng dùng MANUAL hoặc MANUAL_IMMEDIATE, cần kiểm tra cách acknowledge tương tác với error handler. Thuộc tính như ackAfterHandle và commitRecovered có ý nghĩa trong một số cấu hình; không nên bật commitRecovered tùy tiện khi ack mode không hỗ trợ cách commit đó.

Nếu listener gọi side effect bên ngoài Kafka rồi thất bại trước commit, record có thể được giao lại. Thiết kế idempotent là cần thiết để tránh lặp giao dịch hoặc tạo dữ liệu trùng.

## 12. Batch listener và blocking retry

Với record listener, error handler biết record nào thất bại. Với batch listener, một lần gọi listener có thể nhận nhiều record, vì vậy cần xác định record hoặc vị trí nào gây lỗi.

Nếu batch listener ném exception chung mà không chỉ ra record lỗi, handler có thể phải retry cả batch hoặc áp dụng chính sách xử lý batch tương ứng. Điều này có thể khiến các record đã xử lý thành công trong batch bị xử lý lại.

Spring Kafka hỗ trợ BatchListenerFailedException để chỉ ra record hoặc index bị lỗi trong batch. Khi dùng exception này, error handler có thể xử lý phần trước và retry từ vị trí thất bại theo semantics được hỗ trợ.

Ví dụ minh họa:

~~~java
@KafkaListener(topics = "orders", groupId = "orders-service")
public void handle(List<ConsumerRecord<String, OrderEvent>> records) {
    for (int i = 0; i < records.size(); i++) {
        try {
            process(records.get(i).value());
        }
        catch (RuntimeException ex) {
            throw new BatchListenerFailedException(
                    "Cannot process record in batch", ex, i);
        }
    }
}
~~~

Chữ ký constructor và API batch listener cần khớp phiên bản Spring Kafka. Nếu batch chứa nhiều record từ nhiều partition, hãy kiểm tra kỹ cách container xác định offset và phần batch cần retry. Listener nên tránh side effect lặp cho các record đã xử lý trước khi batch thất bại.

## 13. Blocking retry trong transactional listener

Khi listener container dùng Kafka transaction, exception từ listener thường làm transaction hiện tại rollback. Quy trình retry sau rollback được điều phối bởi AfterRollbackProcessor, thường là DefaultAfterRollbackProcessor, thay vì áp dụng nguyên xi cấu hình DefaultErrorHandler cho listener không transaction.

DefaultAfterRollbackProcessor có thể dùng BackOff và recoverer để thử lại record sau rollback, rồi recovery khi hết retry. Nếu cần gửi DLT trong transaction, cấu hình transaction và commit offset cần được thiết kế phù hợp để output recovery và offset có semantics nguyên tử trong phạm vi Kafka.

Không nên lấy ví dụ DefaultErrorHandler không transaction rồi gắn vào transactional listener mà không xem xét transaction manager và after-rollback processing. Cần xác định transaction bao phủ thao tác nào và side effect database bên ngoài có nằm trong transaction đó hay không.

Kafka transaction không tự rollback một REST API hoặc database không tham gia transaction. Nếu listener cập nhật database và sau đó transaction Kafka rollback, side effect database có thể vẫn tồn tại. Dùng outbox, idempotency hoặc một thiết kế phối hợp transaction phù hợp.

## 14. Blocking retry và non-blocking retry

Spring Kafka hỗ trợ non-blocking retry thông qua @RetryableTopic. Khi listener thất bại, record được chuyển đến retry topic với delay được cấu hình. Consumer của topic gốc có thể tiếp tục xử lý các record khác thay vì chờ record lỗi hoàn tất retry.

| Tiêu chí | Blocking retry | Non-blocking retry |
|---|---|---|
| Nơi retry | Trong luồng consumer listener container ban đầu | Qua các retry topic |
| Consumer thread | Chờ backoff và xử lý lại record | Có thể tiếp tục xử lý topic gốc sau khi record được chuyển đi |
| Thứ tự | Phù hợp hơn khi cần giữ thứ tự trong partition | Record sau có thể được xử lý trước record đang chờ ở retry topic |
| Topic bổ sung | Không cần retry topic riêng | Cần retry topic và cấu hình routing |
| Lỗi phù hợp | Lỗi tạm thời, thời gian chờ ngắn, ordering quan trọng | Lỗi cần delay dài hoặc không muốn chặn luồng chính |
| Vận hành | Theo dõi backoff, retry state và consumer thread | Theo dõi retry topic, số lần chuyển tiếp và DLT |

Ví dụ non-blocking retry:

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

Non-blocking retry giải phóng luồng xử lý topic gốc, nhưng thay đổi thứ tự quan sát được giữa record lỗi và record đến sau. Nó không phải phiên bản nhanh hơn trong mọi trường hợp. Chọn theo yêu cầu ordering, latency và khả năng vận hành.

Không cấu hình blocking retry và non-blocking retry chồng lên nhau mà không tính tổng số lần thử, thời gian chờ và nơi record có thể được định tuyến. Cần kiểm tra giới hạn tương thích của phiên bản Spring Kafka và mô hình listener đang sử dụng.

## 15. Quan sát và vận hành blocking retry

Khi blocking retry hoạt động, cần theo dõi cả lỗi listener và ảnh hưởng đến consumer group.

Các thông tin nên ghi nhận trong log:

- Topic, partition và offset.
- Group ID và listener ID.
- Exception class và root cause.
- Delivery attempt.
- Backoff interval.
- Thời gian từ lần lỗi đầu đến recovery.
- Kết quả publish DLT nếu có.

Các metric nên theo dõi:

- Số lần listener thất bại và số lần retry.
- Số record được recovery và số recovery thất bại.
- Consumer lag theo partition.
- Listener processing time và p95/p99 latency.
- Khoảng thời gian giữa các lần poll.
- Rebalance count và rebalance duration.
- Commit latency và commit error rate.
- DLT publish rate.

Không dùng topic, partition và offset làm metric label có cardinality cao. Những thông tin chi tiết này phù hợp với log hoặc trace; metric nên dùng nhãn có số lượng giá trị giới hạn như listener, exception category và outcome.

Khi điều tra một partition bị lag:

1. Kiểm tra record hiện tại có đang retry hay không.
2. Xem exception và backoff interval.
3. Xác định consumer đó còn sở hữu những partition nào.
4. Kiểm tra các partition khác có cùng consumer cũng bị chậm hay không.
5. Đo listener latency và downstream latency.
6. Kiểm tra max.poll.interval.ms và rebalance.
7. Xác định recovery hoặc DLT có đang thất bại không.

Nếu mọi partition do cùng consumer sở hữu đều chậm cùng lúc, blocking retry hoặc một listener operation kéo dài có thể là nguyên nhân. Nếu chỉ một partition lag cao và các partition khác vẫn ổn định, hãy điều tra hot partition, key skew hoặc record cụ thể đang lỗi.

## 16. Những hiểu nhầm thường gặp

**Blocking retry tạo một retry topic.** Không đúng. Blocking retry xử lý lại record trong luồng consumer ban đầu; retry topic là cơ chế non-blocking retry.

**Chỉ partition có record lỗi bị ảnh hưởng.** Không đúng trong mọi trường hợp. Nếu consumer thread đang chờ backoff đồng bộ, các partition khác được giao cho cùng consumer cũng có thể bị trì hoãn.

**Tăng concurrency giúp chia một partition đang lỗi cho nhiều consumer.** Không đúng. Một partition chỉ có một owner trong cùng group tại một thời điểm ổn định.

**Retry nhiều lần sẽ bảo đảm record cuối cùng thành công.** Không đúng. BackOff có giới hạn và lỗi dữ liệu hoặc lỗi cấu hình có thể không tự phục hồi. Khi hết retry, handler phải recovery theo chính sách.

**Listener thất bại nghĩa là không có side effect nào đã xảy ra.** Không đúng. Listener có thể đã ghi database hoặc gọi API trước khi ném exception. Retry có thể thực hiện lại side effect đó; cần idempotency.

**Tăng max.poll.interval.ms làm retry nhanh hơn.** Không đúng. Nó chỉ thay đổi giới hạn thời gian giữa các lần poll. Thời gian backoff và tốc độ dependency vẫn không đổi.

**DLT publish thành công nghĩa là nghiệp vụ đã được xử lý.** Không đúng. Record chỉ được chuyển sang luồng lỗi để điều tra hoặc replay.

**Non-blocking retry luôn tốt hơn blocking retry.** Không đúng. Non-blocking retry có thể làm thay đổi thứ tự giữa record lỗi và record đến sau. Blocking retry phù hợp khi ordering trong partition là ưu tiên.

## 17. Quy trình chọn và cấu hình blocking retry

Khi thiết kế blocking retry cho một listener, hãy xác định loại lỗi, thời gian phục hồi dự kiến và hậu quả nếu partition bị chặn.

Một quy trình thực tế:

1. Liệt kê exception có thể phát sinh từ listener và các dependency.
2. Phân loại lỗi tạm thời và lỗi không thể retry.
3. Chọn FixedBackOff hoặc exponential backoff với số lần retry có giới hạn.
4. Cấu hình DefaultErrorHandler và recoverer cho listener container không transaction.
5. Nếu dùng transaction, cấu hình AfterRollbackProcessor và transaction manager phù hợp.
6. Đánh giá tổng thời gian xử lý so với max.poll.interval.ms.
7. Cân nhắc ContainerPausingBackOffHandler nếu backoff dài.
8. Kiểm tra số partition trên mỗi consumer để hiểu phạm vi ảnh hưởng khi một thread bị block.
9. Thiết kế side effect idempotent và xác định chính sách commit offset.
10. Cấu hình DLT, quan sát retry và recovery, rồi kiểm thử tình huống dependency phục hồi và không phục hồi.

Blocking retry là lựa chọn hữu ích khi lỗi có khả năng tự phục hồi trong thời gian ngắn và thứ tự record trong partition cần được duy trì. Cần giới hạn số lần retry và thời gian chờ, phân loại exception rõ ràng, theo dõi tác động lên consumer thread và có recovery cụ thể khi record không thể xử lý. Nếu thời gian retry dài hoặc việc chặn partition làm ảnh hưởng SLO, hãy cân nhắc container pausing hoặc non-blocking retry với trade-off về ordering đã được chấp nhận.
