# Rollback, AfterRollbackProcessor và thử lại sau rollback

Kafka consumer có thể xử lý message trong một transaction để kết hợp việc đọc record, cập nhật trạng thái và phát message đầu ra theo một ranh giới giao dịch. Khi listener phát sinh lỗi, transaction bị rollback. Ứng dụng cần hiểu điều gì xảy ra với offset, record đã đọc và các side effect để quyết định cách thử lại.

Trong Spring for Apache Kafka, AfterRollbackProcessor là thành phần được container gọi sau khi transaction của listener rollback. Processor mặc định là DefaultAfterRollbackProcessor; nó định vị lại consumer để record chưa xử lý được đọc lại. Có thể cấu hình backoff, recoverer và dead-letter publishing để kiểm soát số lần thử và cách xử lý record lỗi lâu dài.

Spring Cloud Stream Kafka binder hỗ trợ transaction thông qua Spring Kafka. Khi binder được cấu hình transactional, listener container bắt đầu transaction; các record được gửi trên consumer thread có thể tham gia transaction đó. Khi listener kết thúc bình thường, container gửi offset vào transaction và commit. Khi listener ném exception, transaction rollback và DefaultAfterRollbackProcessor điều khiển retry/recovery. Bài học này trình bày rollback, seek/redelivery, retry sau rollback, recovery, DLT và cách cấu hình trong Spring Cloud Stream.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích transaction listener và lý do listener exception dẫn tới rollback.
- Phân biệt rollback Kafka transaction với rollback transaction database.
- Hiểu offset và record được xử lý lại thế nào sau rollback.
- Mô tả vai trò của AfterRollbackProcessor và DefaultAfterRollbackProcessor.
- Cấu hình retry/backoff sau rollback và recoverer khi hết số lần thử.
- Hiểu commitRecovered, KafkaTemplate và transaction mới cho thao tác recovery.
- Tích hợp transaction và rollback với Spring Cloud Stream Kafka binder.
- Thiết kế DLT, idempotency và kiểm thử failure/recovery.

## 1. Transaction trong Kafka consumer

Kafka transaction cho phép producer ghi nhiều record vào Kafka theo một đơn vị nguyên tử. Consumer có thể đọc các record đã commit theo isolation level phù hợp. Trong mô hình consume-process-produce, listener có thể đọc record, xử lý, gửi record đầu ra và commit offset trong cùng transaction Kafka.

Ví dụ một dịch vụ nhận OrderCreated, tạo OrderValidated rồi gửi kết quả tới topic khác:

~~~text
Consumer đọc OrderCreated
       |
       v
Container bắt đầu Kafka transaction
       |
       v
Listener xử lý nghiệp vụ
       |
       v
Gửi OrderValidated
       |
       v
Gửi offset input vào transaction
       |
       v
Commit transaction
~~~

Nếu transaction commit, record đầu ra và offset đầu vào được commit như một đơn vị. Nếu transaction rollback, record đầu ra trong transaction bị loại bỏ và offset đầu vào không được tiến lên theo transaction đó; record có thể được đọc lại.

### 1.1. Transactional listener

Trong Spring Kafka, container có thể được cấu hình với KafkaTransactionManager. Khi đó listener được gọi trong transaction Kafka do container bắt đầu. Nếu listener ném exception ra ngoài, container rollback transaction.

Ví dụ listener theo mô hình Spring Kafka:

~~~java
@KafkaListener(topics = "orders", groupId = "order-validator")
public void validate(OrderCreated event) {
    OrderValidated result = orderService.validate(event);
    kafkaTemplate.send("orders.validated", event.orderId(), result);
}
~~~

Đoạn code chỉ thể hiện luồng nghiệp vụ. Để listener thực sự transactional, container factory phải được cấu hình với KafkaTransactionManager tương thích. Khi dùng Spring Cloud Stream, binder có thể cấu hình transaction cho binding và listener container; không nên sao chép cấu hình Spring Kafka thuần vào ứng dụng binder mà chưa kiểm tra cơ chế cấu hình của phiên bản đang chạy.

### 1.2. Transaction Kafka không tự bao gồm database

Kafka transaction chỉ bao phủ các thao tác Kafka tham gia transaction đó. Nó không tự động rollback một transaction JPA/JDBC đã commit.

Ví dụ:

1. Listener cập nhật database.
2. Listener gửi record tới Kafka.
3. Kafka transaction rollback.

Nếu database đã commit độc lập, dữ liệu database vẫn còn trong khi record Kafka đầu ra bị rollback. Cần phối hợp transaction manager, dùng outbox/inbox hoặc thiết kế idempotency khi nghiệp vụ trải qua cả database và Kafka.

## 2. Điều gì xảy ra khi listener rollback?

Khi listener transactional ném exception, container rollback transaction. Consumer cần tiếp tục từ record chưa được xử lý thành công.

Với record listener, Spring Kafka mặc định seek partition về record thất bại và các record chưa xử lý, để lần poll tiếp theo giao lại chúng. Với batch listener, toàn bộ batch được giao lại vì container không biết chính xác record nào trong batch gây lỗi. AfterRollbackProcessor chịu trách nhiệm điều khiển hành vi này.

~~~mermaid
flowchart TD
    A[Container bắt đầu Kafka transaction] --> B[Poll và giao record cho listener]
    B --> C[Listener xử lý và gửi output]
    C --> D{Listener thành công?}
    D -->|Có| E[Commit transaction và offset]
    D -->|Không| F[Rollback transaction]
    F --> G[AfterRollbackProcessor]
    G --> H[Seek về record cần thử lại]
    H --> I[Poll tiếp theo giao lại record]
    I --> B
~~~

Rollback không có nghĩa broker xóa record đầu vào. Record vẫn tồn tại trong log; consumer group chưa hoàn tất offset tương ứng nên có thể đọc lại.

### 2.1. Offset chưa commit

Kafka lưu tiến độ consumer bằng offset theo partition. Trong transactional listener, offset được gửi vào transaction cùng record đầu ra. Nếu transaction rollback, offset không được commit như một phần của transaction đó.

Điều này giúp tránh tình huống output đã commit nhưng input offset cũng bị tiến lên trong một transaction thất bại. Khi retry, ứng dụng cần sẵn sàng nhận lại cùng record.

### 2.2. Side effect bên ngoài Kafka

Nếu listener gọi HTTP service, gửi email hoặc commit database độc lập trước khi ném exception, rollback Kafka không thu hồi side effect đó. Khi record được giao lại, side effect có thể lặp.

Hãy dùng idempotency key, inbox/outbox, transaction database phù hợp hoặc một quy trình bù trừ cho side effect bên ngoài Kafka. Không đồng nhất Kafka transaction với exactly-once cho toàn bộ hệ thống phân tán.

## 3. AfterRollbackProcessor là gì?

AfterRollbackProcessor là extension point của Spring Kafka được gọi sau khi transaction của listener rollback. Processor quyết định consumer cần seek lại vị trí nào, có tiếp tục thử lại hay chuyển record sang bước recovery.

Implementation mặc định là:

~~~java
org.springframework.kafka.listener.DefaultAfterRollbackProcessor
~~~

Trong trường hợp cơ bản, processor seek partition về record chưa được xử lý để lần poll tiếp theo có thể giao lại. Đây là retry sau rollback, khác với retry ngay trong listener method.

### 3.1. Retry trong listener và retry sau rollback

| Cơ chế | Thời điểm | Đặc điểm |
|---|---|---|
| Retry trong listener | Gọi lại xử lý trước khi listener trả quyền điều khiển cho container | Có thể vẫn nằm trong cùng transaction; các lần thử không tạo ranh giới rollback riêng |
| Retry sau rollback | Listener ném lỗi, transaction rollback, processor điều khiển lần giao tiếp theo | Mỗi lần giao lại đi qua chu kỳ container/transaction mới |
| Retry topic | Record được chuyển sang topic retry để xử lý sau | Là một pipeline khác, không phải seek đơn thuần |
| DLT recovery | Record lỗi được chuyển tới dead-letter destination sau khi hết retry | Cần phối hợp publish và commit offset recovery |

Với transactional listener, retry sau rollback thường dễ diễn giải hơn: mỗi lần listener thất bại, transaction được rollback và processor quyết định thời điểm record được giao lại.

### 3.2. DefaultAfterRollbackProcessor

Processor mặc định có thể cấu hình:

- BackOff để đặt khoảng chờ giữa các lần thử.
- ConsumerRecordRecoverer để xử lý record khi hết retry.
- KafkaTemplate và commitRecovered để publish record đã recover, sau đó commit offset trong transaction recovery mới khi cấu hình phù hợp.
- Các tùy chọn liên quan đến batch và transaction theo phiên bản Spring Kafka.

Spring Kafka mặc định retry record thất bại; sau số lần thất bại mặc định, recoverer mặc định ghi log record lỗi. Có thể thay đổi số lần thử và cung cấp recoverer riêng. Hành vi đếm lần giao ban đầu và số lần retry cần được xác minh theo BackOff đang dùng.

## 4. Cấu hình retry/backoff sau rollback

BackOff xác định thời gian chờ giữa các lần retry. Ví dụ dùng FixedBackOff:

~~~java
import org.springframework.kafka.listener.DefaultAfterRollbackProcessor;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.util.backoff.FixedBackOff;

ConsumerRecordRecoverer recoverer = (record, exception) -> {
    log.error(
            "Recovering record topic={} partition={} offset={}",
            record.topic(),
            record.partition(),
            record.offset(),
            exception);
};

DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
                recoverer,
                new FixedBackOff(1_000L, 2L));
~~~

Ví dụ minh họa recoverer được gọi sau khi retry policy không còn cho phép thử lại. FixedBackOff nhận khoảng nghỉ và số lần retry; số lần giao ban đầu không được tính là một lần retry. Hãy kiểm tra API của phiên bản Spring Kafka đang dùng và xác minh số lần gọi listener bằng test.

BackOff có thể là fixed hoặc exponential. Exponential backoff phù hợp khi dependency cần thời gian phục hồi; jitter có thể giúp tránh nhiều consumer cùng retry tại một thời điểm. Tránh backoff quá dài nếu partition cần phục vụ độ trễ thấp.

### 4.1. Retry hữu hạn và vô hạn

Retry hữu hạn giúp một record lỗi lâu dài không chiếm partition mãi mãi. Sau khi hết retry, recoverer có thể:

- Gửi record tới DLT.
- Ghi nhận lỗi và lưu payload vào kho cách ly.
- Gọi một quy trình nghiệp vụ sửa dữ liệu.
- Dừng xử lý và yêu cầu vận hành can thiệp.

Retry vô hạn có thể phù hợp với lỗi tạm thời rất hiếm khi cần bỏ qua, nhưng có thể chặn toàn bộ partition nếu record lỗi không thể phục hồi. Hãy chọn chính sách theo loại lỗi và yêu cầu thứ tự.

### 4.2. Phân loại exception

Không phải mọi exception đều nên có cùng số lần retry:

| Loại lỗi | Ví dụ | Hành động gợi ý |
|---|---|---|
| Tạm thời | Timeout, broker/dependency ngắt ngắn hạn | Retry với backoff |
| Quá tải | HTTP 429, database connection pool cạn | Backoff, giảm tốc độ |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, schema sai | Ít hoặc không retry; chuyển DLT |
| Lỗi cấu hình | Credentials sai, topic không tồn tại | Cảnh báo, sửa cấu hình |
| Lỗi lập trình | Bug logic, null bất ngờ | Giới hạn retry và điều tra |

Spring Kafka hỗ trợ phân loại exception trong các retry/recovery component. Với Spring Cloud Stream transactional binder, có thể cấu hình defaultRetryable và retryableExceptions theo binding. Các exception cụ thể được đánh dấu retryable hoặc non-retryable sẽ được áp dụng trong DefaultAfterRollbackProcessor.

## 5. Recoverer và dead-letter topic

Khi retry hết, recoverer được gọi để xử lý record không thể xử lý bình thường. Một lựa chọn phổ biến là DeadLetterPublishingRecoverer, gửi record lỗi sang dead-letter topic (DLT).

Ví dụ minh họa với Spring Kafka:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

DefaultAfterRollbackProcessor<String, OrderCreated> processor =
        new DefaultAfterRollbackProcessor<>(
                recoverer,
                new FixedBackOff(1_000L, 2L));
~~~

Trong triển khai thực tế, destination DLT cần tồn tại hoặc được provision đúng. Cần kiểm tra chiến lược chọn DLT, ví dụ thêm hậu tố DLT vào tên topic gốc, cùng partition tương ứng nếu chiến lược định tuyến yêu cầu.

### 5.1. Header và metadata của DLT

DeadLetterPublishingRecoverer có thể bổ sung metadata về topic, partition, offset và exception gốc vào header của record được gửi sang DLT. Những metadata này giúp điều tra và replay.

DLT nên lưu:

- Payload gốc.
- Topic, partition và offset nguồn.
- Exception hoặc nguyên nhân recovery.
- Thời điểm phát hiện lỗi.
- Event ID/correlation ID nếu có.
- Số lần thử hoặc thông tin delivery attempt nếu được cung cấp.

Không ghi thông tin bí mật hoặc toàn bộ stack trace vào header mà không đánh giá kích thước và chính sách bảo mật.

### 5.2. Recovery thành công và commit offset

Trong transactional listener, việc gửi record sang DLT và commit offset của record đã recover cần được phối hợp. DefaultAfterRollbackProcessor hỗ trợ chế độ commitRecovered khi được cấu hình cùng KafkaTemplate thích hợp. Khi bật đúng cách, processor có thể gửi recovered record trong một transaction mới rồi gửi offset đã xử lý vào transaction đó.

Nếu publish DLT thành công nhưng offset không được commit, record gốc có thể được giao lại và DLT có thể nhận bản trùng. Nếu offset được commit mà publish DLT chưa thành công, record có thể bị mất khỏi luồng retry. Vì vậy, cấu hình transaction recovery phải được kiểm thử.

### 5.3. Không đồng nhất DLT với retry topic

DLT thường dành cho record đã hết retry hoặc không thể xử lý. Retry topic là một kiến trúc đưa record sang topic khác để thử lại sau một khoảng thời gian. Retry topic có thể cho phép các record sau tiếp tục, nhưng có thể làm thay đổi thứ tự theo key.

AfterRollbackProcessor với seek/redelivery giữ record trong luồng partition gốc. Nó không tự tạo retry topic.

## 6. Cấu hình recovery trong container factory

Trong ứng dụng Spring Kafka thuần, có thể gắn processor vào listener container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        DefaultAfterRollbackProcessor<String, OrderCreated> processor,
        KafkaTransactionManager<String, OrderCreated> transactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setAfterRollbackProcessor(processor);
    factory.getContainerProperties().setKafkaAwareTransactionManager(transactionManager);
    return factory;
}
~~~

Đây là ví dụ theo mô hình Spring Kafka; chữ ký setter và generic type cần khớp phiên bản Spring Kafka của dự án. Transaction manager phải dùng cùng ProducerFactory mà KafkaTemplate sử dụng để các thao tác gửi tham gia transaction tương ứng.

Khi dùng Spring Cloud Stream Kafka binder, listener container do binder tạo và quản lý. Có thể tùy biến container bằng ListenerContainerCustomizer trong các phiên bản hỗ trợ. Không tạo một KafkaListener container factory riêng rồi giả định binder sẽ tự sử dụng nó.

## 7. Transaction trong Spring Cloud Stream Kafka binder

Để bật transaction trong Kafka binder, đặt transaction ID prefix khác rỗng:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: tx-orders-instance-a-
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
        processOrder-out-0:
          destination: orders.validated
~~~

transaction-id-prefix phải duy nhất giữa các instance ứng dụng chạy đồng thời. Trong processor application, consumer bắt đầu transaction; các record được gửi trên consumer thread tham gia transaction đó. Khi listener kết thúc bình thường, container gửi offset vào transaction và commit. Các producer binding dùng producer factory chung được cấu hình dưới transaction.producer; một số producer properties riêng của binding sẽ không còn được áp dụng như khi binder không transactional.

### 7.1. Retry behavior của transactional binder

Khi bật transaction, không dùng normal binder retry và dead-letter như cách non-transactional. Các retry thông thường có thể chạy trong transaction ban đầu; nếu transaction rollback thì các record retry/DLT được publish trong transaction đó cũng rollback.

Thay vào đó, khi retry được bật qua maxAttempts, Kafka binder cấu hình retry ở cấp container bằng DefaultAfterRollbackProcessor. Có thể cấu hình exception-specific retry:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            max-attempts: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              default-retryable: false
              retryable-exceptions:
                java.lang.IllegalStateException: true
                java.lang.IllegalArgumentException: false
~~~

Trong ví dụ, IllegalStateException được thử lại, còn IllegalArgumentException không được thử lại. Các loại exception phải là lớp con của Exception. Cấu hình retryableExceptions chỉ điều khiển exception classification; số lần thử và backoff còn phụ thuộc thuộc tính retry của binding và phiên bản binder.

Không bật retry trong listener method cùng với retry sau rollback mà không hiểu rõ transaction boundary. Cần xác định chính sách duy nhất cho từng loại lỗi.

### 7.2. Commit offset sau recovery

Kafka binder cung cấp thuộc tính txCommitRecovered cho consumer binding. Với transactional binder, offset của record đã được recover, ví dụ sau khi gửi tới DLT, mặc định được commit qua một transaction mới. Đặt txCommitRecovered thành false sẽ tắt việc commit offset recovered theo cơ chế này.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              tx-commit-recovered: true
~~~

Hãy xác minh cấu hình DLT và recovery thực tế trong binder version đang dùng. Không giả định rằng recoverer được gọi đồng nghĩa offset đã commit; phải kiểm tra kết quả transaction recovery.

### 7.3. Tùy biến listener container do binder tạo

Khi cần gắn processor tùy chỉnh hoặc thay đổi backoff/recoverer ngoài cấu hình binder, có thể dùng ListenerContainerCustomizer nếu phiên bản hỗ trợ. Với transactional binder, có thể lấy transactional ProducerFactory từ Kafka binder, tạo KafkaTemplate từ factory đó rồi cấu hình DefaultAfterRollbackProcessor với recoverer, BackOff, template và commitRecovered.

Ví dụ khung cấu hình theo API binder:

~~~java
@Bean
ListenerContainerCustomizer<AbstractMessageListenerContainer<?, ?>> rollbackCustomizer(
        BinderFactory binderFactory) {

    KafkaMessageChannelBinder binder =
            (KafkaMessageChannelBinder) binderFactory.getBinder(
                    null, MessageChannel.class);
    ProducerFactory<byte[], byte[]> producerFactory =
            binder.getTransactionalProducerFactory();
    KafkaTemplate<byte[], byte[]> template = new KafkaTemplate<>(producerFactory);

    DefaultAfterRollbackProcessor<byte[], byte[]> processor =
            new DefaultAfterRollbackProcessor<>(
                    new DeadLetterPublishingRecoverer(template),
                    new FixedBackOff(2_000L, 2L),
                    template,
                    true);

    return (container, destination, group) ->
            container.setAfterRollbackProcessor(processor);
}
~~~

Đây là khung minh họa cho một binder Kafka duy nhất. Nếu ứng dụng có nhiều binder, phải chọn đúng binder name thay vì truyền null. Cần xác minh generic type, API customizer và cách provision DLT theo phiên bản thư viện. Không dùng chung một processor cho mọi binding nếu mỗi binding cần chính sách retry hoặc DLT khác nhau.

## 8. Retry sau rollback và thứ tự partition

Khi một record trong partition thất bại và processor seek về record đó, các record sau trong partition có thể phải chờ record lỗi được xử lý hoặc recover, tùy chế độ listener và batch. Điều này giữ thứ tự nhưng có thể tạo head-of-line blocking.

Ví dụ:

~~~text
Partition 2:
offset 100: OrderCreated       -> thành công
offset 101: PaymentAuthorized -> lỗi, rollback
offset 102: OrderShipped       -> chờ record 101
~~~

Nếu retry record 101 nhiều lần, offset 102 có thể bị trì hoãn. Đây là trade-off khi ưu tiên thứ tự trong partition.

Nếu dùng DLT hoặc retry topic và bỏ qua record 101 để tiếp tục 102, thứ tự nghiệp vụ có thể bị phá vỡ. Hãy xác định:

- Có cần giữ thứ tự nghiêm ngặt theo aggregate không?
- Record lỗi có thể được cách ly trong khi record sau tiếp tục không?
- Consumer có thể xử lý version out-of-order không?
- Có cần kiểm tra aggregate version để phát hiện khoảng trống?

Kafka chỉ bảo đảm thứ tự trong một partition. Nếu các sự kiện cùng aggregate cần tuần tự, producer phải dùng key ổn định và consumer phải kiểm soát xử lý bất đồng bộ.

### 8.1. Batch listener

Với batch listener, nếu transaction rollback, toàn bộ batch thường được giao lại vì container không biết record nào trong batch gây lỗi. DefaultAfterRollbackProcessor không thể tự phục hồi chính xác một record riêng lẻ nếu không có thông tin record thất bại.

Nếu cần xử lý lỗi theo từng record trong batch, có thể dùng BatchToRecordAdapter để container gọi listener từng record trong khi vẫn duy trì cấu trúc batch. Cần kiểm tra API và khả năng hỗ trợ trong phiên bản Spring Kafka đang dùng.

## 9. Transaction recovery và commitRecovered

Một trường hợp quan trọng là record đã hết retry và được recover sang DLT. Ứng dụng cần hai thao tác nhất quán:

1. Publish record gốc sang DLT.
2. Commit offset đầu vào để record không tiếp tục được giao lại.

Trong DefaultAfterRollbackProcessor, commitRecovered cùng KafkaTemplate cho phép recovery thực hiện trong một transaction mới khi cấu hình transactional phù hợp. Transaction recovery này khác transaction listener ban đầu đã rollback.

~~~text
Listener transaction T1
  - xử lý record
  - thất bại
  - rollback T1

AfterRollbackProcessor
  - retry theo BackOff
  - hết retry
  - gọi recoverer

Recovery transaction T2
  - publish record tới DLT
  - gửi offset recovered
  - commit T2
~~~

Nếu T2 commit, DLT record và offset recovered được commit cùng nhau. Nếu T2 rollback, record nguồn có thể được giao lại để recovery thử lần nữa.

Tên setter và chi tiết cấu hình có thể khác theo phiên bản Spring Kafka. Hãy dùng tài liệu API đúng phiên bản và kiểm thử hành vi transaction recovery, không chỉ kiểm tra log recoverer được gọi.

## 10. Kiểm thử rollback và retry

Kiểm thử cần chứng minh transaction thực sự rollback, record được giao lại và recovery chỉ tiến offset sau khi thao tác recovery đạt điều kiện.

### 10.1. Kiểm thử listener rollback

Một listener có thể được cấu hình để thất bại ở lần đầu và thành công ở lần sau:

~~~java
AtomicInteger attempts = new AtomicInteger();

@KafkaListener(topics = "orders", groupId = "order-test")
public void process(OrderCreated event) {
    if (attempts.incrementAndGet() == 1) {
        throw new IllegalStateException("temporary failure");
    }
    orderService.process(event);
}
~~~

Với transactional container và AfterRollbackProcessor được cấu hình, test có thể xác minh listener được gọi lại và nghiệp vụ chỉ hoàn tất khi lần thử thành công. Đây là ví dụ mô tả hành vi; test cần dùng container transactional thực tế, không chỉ gọi trực tiếp method.

### 10.2. Kiểm thử backoff và số lần thử

Dùng FixedBackOff hoặc một BackOff test có thể quan sát để xác minh:

- Listener được gọi lại theo số lần mong muốn.
- Thời gian chờ giữa các lần thử nằm trong giới hạn.
- Recoverer chỉ được gọi sau khi retry policy hết.
- Record không bị đánh dấu hoàn tất khi handler thất bại và recovery chưa thành công.

Để test nhanh, có thể dùng backoff ngắn hoặc cơ chế thời gian phù hợp nếu API phiên bản hỗ trợ. Tránh test phụ thuộc sleep dài không cần thiết.

### 10.3. Kiểm thử DLT và offset recovery

Với Kafka test broker hoặc Testcontainers:

1. Tạo topic input và DLT.
2. Gửi một record có event ID ổn định.
3. Cấu hình listener luôn thất bại để kích hoạt recoverer.
4. Xác minh record được gửi tới DLT cùng metadata nguồn.
5. Xác minh offset input được commit theo cấu hình recovery.
6. Khởi động lại consumer và xác minh record không bị xử lý lại ngoài dự kiến.
7. Làm DLT publish thất bại và xác minh offset input chưa được commit sai.

### 10.4. Kiểm thử transaction output

Trong một listener consume-process-produce:

- Khi listener thành công, xác minh output record và input offset cùng commit.
- Khi listener ném exception, xác minh output record trong transaction bị rollback và input record được giao lại.
- Khi listener gửi nhiều output rồi thất bại, xác minh không có output một phần được commit.

Consumer kiểm thử cần dùng isolation level phù hợp, ví dụ read_committed, nếu muốn chỉ nhìn thấy record transactional đã commit.

## 11. Quan sát và vận hành

Retry sau rollback có thể làm một partition bị chặn lâu hoặc liên tục chuyển record vào DLT. Theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Listener failure count | Số lần listener phát sinh lỗi |
| Rollback count | Số transaction listener rollback |
| Retry attempt count | Số lần thử lại sau rollback |
| Recovery count | Số record được recover |
| DLT publish success/failure | Kết quả gửi record lỗi |
| Consumer lag theo partition | Backlog tăng ở partition nào |
| Time between attempts | Khoảng cách giữa các lần retry |
| Transaction duration | Thời gian transaction listener/recovery |
| Rebalance count | Group thay đổi assignment do consumer chậm hoặc dừng |

Nếu một partition lag tăng trong khi các partition khác bình thường, điều tra record lỗi và thời gian retry. Một record lỗi có thể chặn toàn bộ record phía sau trong partition đó.

### 11.1. Cảnh báo

Nên cảnh báo khi:

- Rollback tăng đột biến.
- Retry liên tục vượt ngưỡng.
- DLT nhận record tăng bất thường.
- DLT publish thất bại.
- Consumer lag tăng trong thời gian dài.
- Transaction timeout hoặc rebalance lặp lại.

Không cảnh báo chỉ vì một lần rollback đơn lẻ nếu retry thành công nhanh và không ảnh hưởng SLA.

## 12. Những lỗi thường gặp

1. **Cho rằng rollback Kafka cũng rollback database**: Kafka transaction không tự bao trùm database transaction độc lập. Hãy dùng outbox/inbox hoặc cơ chế phối hợp rõ ràng.
2. **Bắt exception rồi không ném lại**: container có thể commit transaction dù nghiệp vụ chưa thành công. Hãy truyền lỗi ra hoặc xử lý theo chính sách được định nghĩa.
3. **Nhầm retry trong listener với retry sau rollback**: hai cơ chế có vòng đời transaction khác nhau. Hãy chọn cơ chế phù hợp với listener transactional.
4. **Không cấu hình processor sau rollback**: ứng dụng dùng hành vi mặc định mà không hiểu số lần retry/recovery. Hãy xác định BackOff và recoverer.
5. **Retry vô hạn một record lỗi dữ liệu**: partition có thể bị chặn mãi. Hãy phân loại exception và dùng retry hữu hạn cho lỗi không phục hồi.
6. **Đánh dấu offset trước khi DLT publish thành công**: record có thể biến mất khỏi luồng mà không có bản DLT. Hãy phối hợp recovery và commit offset trong transaction mới.
7. **Cho rằng gọi recoverer nghĩa là offset đã commit**: recovery callback và commit offset là hai thao tác cần cấu hình phối hợp. Hãy kiểm thử commitRecovered.
8. **Dùng KafkaTemplate không tham gia transaction hiện tại**: output có thể commit độc lập với listener. Hãy xác minh producer factory và transaction manager.
9. **Coi DLT và retry topic là một**: DLT cách ly record lỗi; retry topic là một pipeline thử lại khác. Hãy thiết kế semantics riêng.
10. **Không xử lý duplicate sau crash**: broker có thể đã nhận output trước khi listener biết kết quả. Hãy dùng event ID và idempotency.
11. **Không xem xét thứ tự partition**: retry topic hoặc recovery có thể khiến record sau vượt record lỗi. Hãy xác định thứ tự theo aggregate.
12. **Chỉ test method listener trực tiếp**: test đó không kiểm tra transaction, seek, offset hoặc recovery. Hãy integration test với Kafka thật.

## 13. Quy trình triển khai rollback và retry

Khi triển khai transactional Kafka consumer:

1. Xác định các thao tác Kafka cần nằm trong cùng transaction.
2. Bật transaction cho Kafka binder bằng transaction ID prefix duy nhất theo instance.
3. Xác định lỗi nào làm listener rollback và không nuốt exception.
4. Chọn DefaultAfterRollbackProcessor hoặc processor tùy chỉnh.
5. Cấu hình BackOff và số lần retry theo loại lỗi.
6. Chọn recoverer và DLT cho record không thể xử lý.
7. Nếu dùng transactional binder, xác định retry behavior qua maxAttempts và exception classification.
8. Kiểm tra txCommitRecovered và transaction mới cho offset của record đã recover.
9. Kiểm tra partition key và yêu cầu thứ tự khi retry hoặc chuyển DLT.
10. Kiểm thử rollback, redelivery, DLT, offset và transaction output bằng Kafka test broker.
11. Theo dõi rollback, retry, recovery, DLT và consumer lag sau triển khai.

## Kết luận

Khi transactional Kafka listener thất bại, container rollback transaction và AfterRollbackProcessor điều khiển việc seek, thử lại hoặc recover record. DefaultAfterRollbackProcessor hỗ trợ backoff và recoverer; khi hết retry, record có thể được gửi tới DLT. Trong cấu hình transactional phù hợp, commitRecovered cùng KafkaTemplate cho phép publish recovered record và commit offset trong một transaction recovery mới.

Spring Cloud Stream Kafka binder cấu hình retry sau rollback ở cấp container khi transaction được bật; normal binder retry/DLT không hoạt động theo cùng cách non-transactional vì các lần publish trong transaction đã rollback cũng bị rollback. Cần dùng transaction ID prefix duy nhất theo instance và xác minh retry, recovery cùng offset commit theo phiên bản binder đang triển khai.

Rollback chỉ bao phủ các thao tác tham gia Kafka transaction. Database, HTTP hoặc side effect bên ngoài cần cơ chế riêng như outbox, inbox và idempotency. Muốn giao nhận tin cậy, phải kiểm thử cả listener transaction, redelivery, recovery transaction, DLT publish và offset commit trên broker thực tế.

## Tài liệu tham khảo

- [Spring for Apache Kafka — After Rollback Processor](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Cloud Stream — Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/transactional.html)
