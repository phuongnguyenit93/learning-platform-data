# Không mất message khi writer lỗi

Trong Spring Batch, một Job có thể đọc message từ Kafka, RabbitMQ, JMS hoặc một message source khác, sau đó xử lý và ghi kết quả vào database hay hệ thống bên ngoài. Một tình huống cần thiết kế cẩn thận là **writer gặp lỗi sau khi reader đã nhận message**.

Nếu message bị acknowledge, xóa khỏi queue hoặc commit offset trước khi dữ liệu đích được ghi thành công, message có thể biến mất dù chunk thất bại. Ngược lại, nếu dữ liệu đích đã commit nhưng ứng dụng dừng trước khi acknowledge message, message có thể được gửi lại và xử lý trùng.

Mục tiêu thực tế thường là **at-least-once delivery kết hợp xử lý idempotent**: không mất message khi xử lý lỗi, đồng thời cho phép redelivery mà không tạo tác động nghiệp vụ trùng.

Cần xác định rõ:

- Message được lấy từ broker bằng cơ chế nào.
- Acknowledge, delete hoặc commit offset xảy ra ở thời điểm nào.
- Writer và message source có tham gia cùng transaction không.
- Lỗi writer làm rollback chunk và kích hoạt redelivery ra sao.
- Retry, skip và dead-letter queue được dùng theo chính sách nào.
- Làm sao chống duplicate khi commit thành công nhưng ack chưa hoàn tất.
- Job restart khôi phục message position hoặc offset bằng cách nào.

## 1. Vấn đề xảy ra khi writer lỗi

Giả sử Job đọc một message yêu cầu cập nhật trạng thái đơn hàng, rồi ghi trạng thái vào database:

~~~text
Message broker
      |
      v
ItemReader nhận message M-100
      |
      v
Processor chuyển thành OrderUpdate
      |
      v
ItemWriter ghi database
      |
      +--> lỗi
~~~

Nếu reader đã acknowledge M-100 ngay khi nhận message, broker có thể coi message đã được xử lý. Khi writer lỗi, Spring Batch rollback chunk nhưng broker không còn message để gửi lại.

Kết quả: message bị mất khỏi luồng xử lý, dù database chưa được cập nhật.

Một cách khác là writer commit database trước rồi mới acknowledge broker. Khi đó nếu ứng dụng dừng giữa hai thao tác, broker gửi lại message. Đây là duplicate, nhưng có thể xử lý an toàn bằng idempotency.

| Thứ tự | Sự cố | Kết quả |
|---|---|---|
| Ack message → DB write | Writer lỗi | Có nguy cơ mất message |
| DB commit → Ack message | Process dừng trước ack | Message có thể được gửi lại |
| DB và broker cùng transaction nguyên tử | Transaction rollback | Cả hai thay đổi được hoàn tác nếu cấu hình hỗ trợ đúng |

Với đa số tích hợp database và broker, transaction nguyên tử xuyên suốt không tự có. Cần thiết kế acknowledgement, transaction coordination và idempotency theo semantics của broker.

## 2. Phân biệt inbound message và outbound message

Có hai luồng khác nhau.

**Inbound**: Job nhận message từ broker, xử lý rồi writer ghi database. Rủi ro chính là acknowledge message quá sớm.

~~~text
Broker -> Reader -> Processor -> Database Writer
~~~

**Outbound**: Job đọc database/file, xử lý rồi writer publish message tới broker. Rủi ro chính là database commit nhưng publish thất bại, hoặc publish thành công nhưng database rollback.

~~~text
Database Reader -> Processor -> Message Broker Writer
~~~

Một Job có thể làm cả hai. Cần phân tích từng ranh giới độc lập. Acknowledge inbound message và publish outbound message là hai thao tác có semantics khác nhau.

Trong bài này, phần chính tập trung vào inbound message và lỗi writer. Cuối bài cũng trình bày outbox để xử lý an toàn khi writer gửi message ra broker.

## 3. Chunk transaction không tự rollback broker

Spring Batch quản lý transaction của chunk thông qua PlatformTransactionManager được cấu hình cho Step.

~~~text
Begin chunk transaction
        |
        v
Read messages
        |
        v
Process items
        |
        v
Writer writes chunk
        |
        +--> success
        |
        +--> failure
        |
        v
Commit or rollback
~~~

Nếu writer ném exception được phân loại rollback, transaction của chunk được rollback. Database writer tham gia transaction đó có thể được hoàn tác.

Tuy nhiên, message broker chỉ rollback theo chunk nếu message acknowledgement/offset/receive operation thực sự tham gia cùng transaction hoặc được điều khiển theo một cơ chế phối hợp phù hợp.

Nếu reader đã gọi ack độc lập trước khi writer chạy, database rollback không thể khôi phục message đã ack.

Đừng giả định rằng dùng cùng một Spring ApplicationContext hoặc cùng một Step có nghĩa database và broker đã cùng transaction.

## 4. Acknowledge quá sớm gây mất message

Xét thứ tự không an toàn:

~~~text
1. Consumer nhận message M-100
2. Consumer ACK M-100
3. Spring Batch xử lý item
4. Writer ghi database
5. Writer ném exception
6. Chunk rollback
~~~

Broker đã nhận ACK ở bước 2 nên không gửi lại M-100. Database rollback ở bước 6 không thể yêu cầu broker phục hồi message.

Đây là lỗi thiết kế acknowledgement. Reader cần giữ message ở trạng thái chưa xác nhận cho tới khi chunk xử lý thành công, hoặc dùng một cơ chế transaction đảm bảo receive/ack và database write có semantics nhất quán.

Với queue có visibility timeout, việc nhận message thường chỉ làm nó tạm ẩn. Xóa message trước khi database commit có rủi ro tương tự ACK sớm.

## 5. Ack sau commit có thể tạo duplicate

Thứ tự an toàn hơn cho việc không mất message:

~~~text
1. Consumer nhận message M-100
2. Giữ message chưa ACK / chưa delete
3. Spring Batch xử lý item
4. Writer ghi database
5. Chunk transaction COMMIT
6. Consumer ACK / delete message
~~~

Nếu writer lỗi ở bước 4, chunk rollback và message vẫn chưa được ACK. Broker có thể redeliver message.

Nhưng có một cửa sổ lỗi:

~~~text
Database COMMIT thành công
          |
          v
Process crash trước ACK
          |
          v
Broker redeliver M-100
          |
          v
Database nhận lại cùng message
~~~

Đây là duplicate delivery. Với at-least-once processing, duplicate là tình huống bình thường cần được xử lý bằng idempotency, unique key hoặc inbox/deduplication table.

Không thể chỉ đổi thứ tự ack để đồng thời loại bỏ cả mất message lẫn duplicate trong mọi tình huống crash. Muốn đạt hiệu ứng exactly-once ở tầng nghiệp vụ, cần atomic transaction phù hợp hoặc deduplicate các lần giao lại.

## 6. At-most-once, at-least-once và exactly-once

Ba khái niệm mô tả mức đảm bảo giao nhận:

| Guarantee | Hành vi | Rủi ro |
|---|---|---|
| At-most-once | Message được xác nhận trước hoặc trong lúc xử lý | Có thể mất message |
| At-least-once | Chỉ xác nhận sau khi xử lý; lỗi có thể redeliver | Có thể xử lý trùng |
| Exactly-once | Mỗi message tạo hiệu ứng nghiệp vụ đúng một lần | Cần phối hợp transaction/deduplication rất chặt |

At-least-once thường là lựa chọn thực tế cho batch integration. Nó ưu tiên không mất dữ liệu và chấp nhận duplicate delivery.

"Exactly-once" của một broker thường có phạm vi cụ thể, chẳng hạn transaction trong chính broker hoặc read-process-write trong cùng hệ sinh thái. Nó không tự động bảo đảm một database bên ngoài và một broker cùng commit nguyên tử.

Cần phân biệt:

- Exactly-once delivery: message chỉ được giao một lần, điều này khó bảo đảm qua crash/network retry.
- Exactly-once effect: message có thể được giao nhiều lần nhưng tác động nghiệp vụ chỉ được áp dụng một lần nhờ idempotency/deduplication.

Thiết kế hệ thống thường hướng tới exactly-once effect hơn là giả định message chỉ tới đúng một lần.

## 7. Retry khi writer lỗi

Nếu lỗi có khả năng tạm thời, Spring Batch có thể retry chunk.

~~~java
@Bean
public Step processMessagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<IncomingMessage> reader,
        ItemProcessor<IncomingMessage, OrderUpdate> processor,
        ItemWriter<OrderUpdate> writer) {

    return new StepBuilder("processMessagesStep", jobRepository)
            .<IncomingMessage, OrderUpdate>chunk(
                    100,
                    transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
~~~

Trong ví dụ, lỗi thuộc nhóm transient có thể được thử lại theo giới hạn đã cấu hình. Exception thực tế có thể được Spring dịch hoặc bọc; cần phân loại theo exception mà Step nhận được.

Khi retry chunk, reader/processor/writer có thể được gọi lại theo fault-tolerant semantics. Writer cần chịu được việc cùng item được gửi lại, đặc biệt nếu có side effect ngoài transaction.

Retry phù hợp với:

- Database deadlock có thể thử lại.
- Lỗi kết nối tạm thời.
- Broker hoặc service tạm unavailable.
- Throttle/rate limit có retry-after rõ ràng.

Không retry vô hạn lỗi dữ liệu không hợp lệ, schema mismatch, authorization failure hoặc constraint violation không thể tự biến mất.

## 8. Retry phải có backoff và giới hạn

Retry liên tục không có delay có thể làm hệ thống quá tải hơn khi database hoặc broker đang sự cố.

Một chính sách tốt cần:

- Retry limit hữu hạn.
- Backoff tăng dần.
- Jitter nếu nhiều worker retry cùng lúc.
- Timeout cho từng lần gọi.
- Phân biệt lỗi transient và permanent.
- Metrics theo exception type và số lần retry.

Ví dụ cấu hình backoff:

~~~java
@Bean
public Step processMessagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<IncomingMessage> reader,
        ItemWriter<OrderUpdate> writer) {

    ExponentialBackOffPolicy backOff =
            new ExponentialBackOffPolicy();
    backOff.setInitialInterval(500L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(10_000L);

    return new StepBuilder("processMessagesStep", jobRepository)
            .<IncomingMessage, OrderUpdate>chunk(
                    50,
                    transactionManager)
            .reader(reader)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(4)
            .backOffPolicy(backOff)
            .build();
}
~~~

API builder và retry policy có thể khác theo Spring Batch version. Hãy xác nhận dependency của dự án và kiểm thử thời gian thực tế.

Backoff không thay thế broker visibility timeout. Với SQS hoặc queue có lease, message phải tiếp tục invisible đủ lâu hoặc được gia hạn trong khi retry.

## 9. Không skip message writer lỗi một cách vô tình

Skip có nghĩa Spring Batch quyết định bỏ qua item hoặc lỗi theo skip policy. Nếu yêu cầu nghiệp vụ là không mất message, cấu hình skip rộng có thể làm mất dữ liệu một cách hợp lệ theo framework nhưng sai với nghiệp vụ.

Ví dụ không nên:

~~~java
.faultTolerant()
.skip(Exception.class)
.skipLimit(1000)
~~~

Nếu writer thất bại vì database không khả dụng mà exception bị skip, message có thể được coi như đã xử lý dù không có dữ liệu đích.

Chỉ skip khi nghiệp vụ cho phép loại bỏ record đó và có một nơi lưu trữ bền vững cho dữ liệu lỗi. Một phương án là ghi rejected message vào dead-letter storage rồi chỉ ACK message gốc sau khi việc lưu rejected record đã thành công.

Nếu DLQ write cũng lỗi, message gốc phải tiếp tục được giữ hoặc redeliver. Không đánh dấu thành công chỉ vì đã log lỗi.

## 10. Dead-letter queue cho message không thể xử lý

Một poison message là message luôn thất bại vì dữ liệu hoặc schema không hợp lệ. Retry vô hạn sẽ chặn queue và tiêu tốn tài nguyên.

~~~text
Main queue
    |
    v
Process message
    |
    +--> thành công --> ACK
    |
    +--> lỗi tạm thời --> retry / redelivery
    |
    +--> lỗi vĩnh viễn hoặc quá giới hạn
              |
              v
        Publish to DLQ
              |
              v
        Confirm DLQ persistence
              |
              v
        ACK message gốc
~~~

Chỉ ACK message gốc sau khi DLQ đã lưu message cùng metadata cần thiết. Metadata nên gồm:

- Original message ID.
- Source topic/queue và partition nếu có.
- Payload hoặc reference tới payload.
- Exception class và error code.
- Thời điểm lỗi và số lần thử.
- JobExecution/StepExecution ID.
- Correlation ID và schema version.

DLQ cũng cần retention, alert, quyền truy cập và quy trình replay. Một message trong DLQ không nên bị coi là đã giải quyết chỉ vì nó không còn nằm trong main queue.

## 11. Reader phải giữ khả năng redelivery

Một ItemReader tích hợp với broker cần xác định rõ ai sở hữu acknowledgement.

Một số mô hình:

1. Reader chỉ đọc từ nguồn replayable và không commit offset; framework hoặc một coordinator commit sau chunk.
2. Reader nhận message trong một broker transaction được phối hợp với transaction chunk.
3. Listener/container quản lý ack sau khi listener hoặc batch unit hoàn thành.
4. Reader lưu message/offset trong một staging store trước, sau đó Step xử lý từ staging.

Không nên để reader tự ACK ngay trong read() nếu writer còn chưa chạy.

Nếu reader poll nhiều message trước khi trả từng item, phải quản lý buffer và redelivery cẩn thận. Khi chunk rollback, message trong buffer không được mất chỉ vì consumer đã tiến cursor nội bộ.

Với một reader custom, cần xác định open(), read(), update() và close() làm gì với broker state. ItemStream checkpoint phải tương thích với thời điểm broker offset/ack được commit.

## 12. ItemStream và ExecutionContext

Spring Batch dùng ExecutionContext để lưu state của reader/writer giữa các chunk và hỗ trợ restart. Một reader có thể lưu offset, sequence hoặc vị trí đã đọc.

Ví dụ khái niệm:

~~~java
public class CheckpointingMessageReader
        implements ItemStreamReader<IncomingMessage> {

    private long lastReadSequence;

    @Override
    public IncomingMessage read() {
        // Đọc message tiếp theo theo source semantics.
        return null;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("lastReadSequence", lastReadSequence);
    }

    @Override
    public void open(ExecutionContext context) {
        if (context.containsKey("lastReadSequence")) {
            lastReadSequence =
                    context.getLong("lastReadSequence");
        }
    }
}
~~~

Đây là skeleton minh họa checkpoint. Reader thật cần bảo đảm checkpoint chỉ tiến qua các item thuộc chunk đã commit, không chỉ các item đã được poll hoặc trả ra.

Nếu update ExecutionContext lưu offset đã đọc trước khi chunk commit, rồi database writer rollback, restart có thể bỏ qua message chưa được ghi. Vì vậy, reader state phải tham gia đúng transaction lifecycle hoặc được thiết kế để replay an toàn.

Tên reader phải ổn định và saveState phải được bật nếu reader hỗ trợ checkpoint. Không lưu toàn bộ payload lớn vào ExecutionContext; lưu offset/ID hoặc manifest reference.

## 13. Offset và commit trong Kafka

Kafka consumer đọc record theo partition và offset. Offset biểu thị vị trí tiếp theo cần đọc trong partition.

Nếu consumer commit offset trước khi database writer commit, một writer failure có thể làm record bị bỏ qua khi consumer khởi động lại.

~~~text
poll record offset 42
       |
       v
commit offset 43
       |
       v
database writer fails
       |
       v
restart consumer at offset 43
       |
       v
record 42 is not delivered again
~~~

Để tránh mất record, tắt auto-commit khi ứng dụng tự quản lý offset và chỉ commit offset sau khi chunk tương ứng được xử lý thành công. Với Spring Batch KafkaItemReader, cần hiểu cách reader lưu offset vào ExecutionContext và cách consumer được cấu hình; không tự giả định việc lưu checkpoint trong JobRepository đồng nghĩa broker group offset đã commit.

Cấu hình Kafka consumer thường cần enable.auto.commit=false khi offset được quản lý thủ công. Nếu dùng listener container hoặc framework integration khác, tuân theo acknowledgement mode của container đó.

## 14. KafkaItemReader và restart

Spring Batch cung cấp KafkaItemReader trong các phiên bản hỗ trợ Kafka integration. Reader nhận consumer properties, topic/partition và có thể lưu state để restart.

Ví dụ cấu hình khái niệm:

~~~java
@Bean
@StepScope
public KafkaItemReader<String, String> kafkaItemReader(
        @Value("#{jobParameters['topic']}") String topic) {

    Properties properties = new Properties();
    properties.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092");
    properties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "batch-order-import");
    properties.put(
            ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
            false);
    properties.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    properties.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);

    return new KafkaItemReaderBuilder<String, String>()
            .name("kafkaOrderReader")
            .consumerProperties(properties)
            .topic(topic)
            .partitions(0, 1)
            .saveState(true)
            .build();
}
~~~

Tên builder và các method cần khớp phiên bản Spring Batch Kafka module đang dùng. Đây là ví dụ định hướng, không thay thế cấu hình bảo mật, deserializer và partition thực tế.

KafkaItemReader có state phục vụ restart qua ExecutionContext. Cần xác minh behavior của version đang dùng về seek/offset và việc consumer group offset được commit hay không. Không bật auto-commit song song với checkpoint management nếu chưa hiểu thứ tự và hệ quả.

Nếu cần kiểm soát commit offset sau transaction chunk, có thể cần custom reader hoặc listener/container integration được thiết kế cho acknowledgement timing. Test crash sau writer commit và trước offset commit.

## 15. Kafka transaction không tự atomic với database

Kafka transaction có thể bảo đảm việc consume/produce và commit offset trong một transaction Kafka theo các pattern phù hợp. Nhưng database bên ngoài không tự tham gia transaction đó.

~~~text
Kafka transaction
   +--> produce result event
   +--> send consumed offsets to transaction
   +--> commit Kafka transaction

Database transaction
   +--> update order
   +--> commit database
~~~

Nếu hai transaction độc lập, crash giữa chúng vẫn tạo cửa sổ không nhất quán.

Một số giải pháp:

- Outbox: commit database row và event record trong cùng DB transaction, sau đó publisher gửi event.
- Inbox/deduplication: lưu message ID cùng business update trong cùng DB transaction.
- XA/JTA nếu cả resource và driver hỗ trợ đúng, đồng thời chấp nhận độ phức tạp vận hành.
- Thiết kế idempotent để xử lý lại message an toàn.

Kafka exactly-once semantics không tự động bao phủ database commit của Spring Batch.

## 16. RabbitMQ acknowledgement

RabbitMQ consumer thường nhận message và ACK khi xử lý thành công. Với manual acknowledgement, ứng dụng có thể chỉ ACK sau khi database chunk commit.

~~~text
RabbitMQ delivers message
        |
        v
Consumer processes message
        |
        v
Database chunk commits
        |
        v
ACK message
~~~

Nếu writer lỗi trước commit, không ACK message. Broker có thể requeue/redeliver theo cấu hình và channel behavior.

Nếu consumer ACK trước commit, message có thể mất khi writer lỗi. Nếu database commit xong nhưng process dừng trước ACK, message có thể được redeliver.

Khi dùng Spring AMQP, cần hiểu AcknowledgeMode, channel transaction và transaction synchronization. AUTO thường có nghĩa container tự ACK sau khi listener hoàn tất bình thường; nó không đồng nghĩa auto-ack ngay lúc nhận message. MANUAL cho phép ứng dụng quyết định thời điểm ACK.

Không gọi basicAck ngay khi poll/receive nếu chunk chưa được ghi thành công. Với batch reader, cần phối hợp ack theo chunk thay vì theo từng lần read.

## 17. Rabbit channel transaction và database transaction

RabbitMQ có transaction/confirm mechanisms riêng cho publish và acknowledgement, nhưng chúng không tự động tạo một transaction XA chung với database.

Spring AMQP có thể đồng bộ channel transaction với transaction bên ngoài trong một số cấu hình, nhưng semantics và failure window phụ thuộc container, channelTransacted và transaction manager.

Cần kiểm thử các trường hợp:

- Database rollback trước khi channel ACK commit.
- Database commit thành công nhưng channel commit/ACK thất bại.
- Connection/channel mất giữa hai thao tác.
- Redelivery sau restart.
- Nhiều message trong một chunk.

Nếu không có atomic coordination được chứng minh, hãy coi duplicate delivery là có thể xảy ra và dùng inbox/idempotency.

## 18. JMS transacted session

Với JMS, session transacted có thể nhóm receive và acknowledge/commit trong transaction của JMS session. Khi session rollback, message đã receive có thể được redeliver theo broker semantics.

Ví dụ cấu hình JMS consumer:

~~~java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConnectionFactory(connectionFactory);
container.setDestinationName("orders.in");
container.setSessionTransacted(true);
~~~

Đây là ví dụ container-level, không phải cấu hình trực tiếp một Spring Batch ItemReader. Khi kết hợp JMS receive với database write, cần xác định transaction manager quản lý JMS session và database.

Local JMS transaction chỉ quản lý JMS resource. Nếu database transaction là resource khác, hai bên không tự atomic. Có thể dùng JTA/XA nếu broker, database, driver và transaction manager hỗ trợ, hoặc dùng inbox/outbox/idempotency.

Không giả định sessionTransacted=true tự động rollback database khi database writer lỗi nếu hai resource không được phối hợp trong cùng distributed transaction.

## 19. SQS visibility timeout và delete

Amazon SQS thường giao message cho consumer và ẩn message trong một visibility timeout. Consumer phải delete message sau khi xử lý thành công.

~~~text
ReceiveMessage
      |
      v
Message invisible for visibility timeout
      |
      v
Process and write database
      |
      +--> failure: do not delete
      |
      +--> success: delete message
~~~

Nếu writer lỗi và message không bị delete, message sẽ xuất hiện lại khi visibility timeout hết hạn.

Nếu database commit xong nhưng delete chưa thành công, message cũng có thể xuất hiện lại. Vì vậy, xử lý SQS thường là at-least-once và consumer cần idempotent.

Nếu xử lý lâu hơn visibility timeout, message có thể được giao cho consumer khác khi consumer đầu vẫn đang làm việc. Cần gia hạn visibility timeout phù hợp, nhưng vẫn phải có idempotency vì extension có thể thất bại hoặc process có thể crash.

## 20. Broker redelivery và delivery count

Nhiều broker theo dõi số lần giao lại hoặc có metadata tương đương:

- RabbitMQ có redelivered flag và queue delivery/dead-letter behavior.
- JMS có delivery count và redelivery policy tùy broker.
- SQS có ApproximateReceiveCount.
- Kafka không có redelivery count chuẩn như queue; consumer có thể đọc lại cùng offset khi không commit.

Dùng metadata này để quan sát poison message và quyết định DLQ, nhưng không dựa riêng vào delivery count để nhận diện message. Dùng message ID hoặc business key ổn định.

Cần tránh cấu hình redelivery vô hạn không delay vì có thể tạo hot loop. Đặt retry delay, maximum attempts và DLQ policy theo yêu cầu nghiệp vụ.

## 21. Inbox pattern để chống xử lý trùng

Inbox pattern lưu message ID đã xử lý trong cùng database transaction với business update.

Ví dụ bảng:

~~~sql
CREATE TABLE processed_message (
    message_id VARCHAR(200) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong cùng transaction:

1. Thử insert message ID vào processed_message.
2. Nếu insert thành công, xử lý business update.
3. Commit cả inbox record và business update.
4. Nếu message ID đã tồn tại, coi message là duplicate đã xử lý và không áp dụng business update lần nữa.
5. Chỉ ACK message sau khi transaction commit.

Pseudo-code:

~~~java
@Transactional
public void handle(IncomingMessage message) {
    int inserted = jdbcTemplate.update("""
            INSERT INTO processed_message(message_id, processed_at)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT (message_id) DO NOTHING
            """,
            message.messageId());

    if (inserted == 0) {
        return; // Message đã được xử lý trước đó.
    }

    orderRepository.apply(message.toOrderUpdate());
}
~~~

Cú pháp ON CONFLICT là PostgreSQL-specific; database khác có thể dùng MERGE, insert-if-absent hoặc unique constraint exception được xử lý phù hợp.

Điều quan trọng là inbox record và business update phải commit cùng transaction. Nếu business update thất bại, inbox insert cũng rollback, để lần redelivery có thể xử lý lại.

Nếu inbox insert commit trước business update, message có thể bị đánh dấu processed dù dữ liệu nghiệp vụ chưa được ghi.

## 22. Dùng unique key làm idempotency

Nếu message có business operation ID ổn định, có thể dùng unique constraint trực tiếp trong bảng đích.

~~~sql
CREATE TABLE order_event_result (
    event_id VARCHAR(200) PRIMARY KEY,
    order_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);
~~~

Khi message được giao lại, insert event_id trùng sẽ không tạo kết quả mới. Tùy nghiệp vụ, có thể bỏ qua duplicate hoặc thực hiện upsert có điều kiện.

Không dùng payload hash làm định danh duy nhất nếu hai message khác nhau có cùng nội dung nhưng là hai sự kiện hợp lệ. Tốt nhất producer cung cấp message/event ID duy nhất và bất biến.

Idempotency key cần giữ ổn định qua retry, redelivery và Job restart. Không tạo UUID mới ở mỗi lần thử vì khi đó hệ thống không nhận diện được cùng một operation.

## 23. Outbox khi writer publish message ra broker

Nếu writer của Spring Batch gửi event ra broker sau khi cập nhật database, không nên giả định hai thao tác commit nguyên tử.

Ví dụ lỗi:

~~~text
Database update
      |
      v
DB COMMIT
      |
      v
Publish message
      |
      +--> broker unavailable
~~~

Database đã thay đổi nhưng message chưa được publish. Nếu đảo thứ tự, broker có thể nhận message rồi database rollback.

Transactional outbox giải quyết bằng cách ghi business data và event vào cùng database transaction:

~~~text
Spring Batch chunk
       |
       +--> Update order
       |
       +--> Insert outbox event
       |
       v
DB COMMIT
       |
       v
Outbox publisher
       |
       v
Broker
~~~

Nếu chunk rollback, cả order update và outbox row rollback. Nếu commit thành công nhưng publisher dừng, outbox row vẫn tồn tại để gửi lại.

Outbox publisher cần đánh dấu event đã gửi theo một cơ chế bền vững. Crash sau publish nhưng trước khi đánh dấu SENT có thể làm publish lại; consumer vẫn nên deduplicate theo event ID.

## 24. Outbox không có nghĩa publish đúng một lần

Outbox bảo đảm event không bị mất giữa database commit và việc publisher đọc event, nhưng publisher thường phải chấp nhận gửi lại khi không biết broker đã nhận message hay chưa.

~~~text
1. Publisher gửi event E-100
2. Broker nhận E-100
3. Publisher crash trước khi đánh dấu SENT
4. Publisher restart
5. E-100 được gửi lại
~~~

Vì vậy, outbox thường tạo at-least-once publishing. Consumer cần idempotency hoặc deduplication.

Có thể dùng trạng thái outbox như PENDING, IN_PROGRESS, SENT và lease để nhiều publisher không gửi cùng event đồng thời. Tuy nhiên, lease hết hạn sau crash vẫn có thể khiến event được gửi lại. Event ID ổn định vẫn là nền tảng chống duplicate.

## 25. Transaction synchronization và after-commit callback

Một lựa chọn là đăng ký callback để publish sau khi transaction commit:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                messagePublisher.publish(event);
            }
        });
~~~

Cách này tránh publish trước commit, nhưng không bảo đảm không mất message. Nếu process crash sau database commit nhưng trước khi callback chạy, event không được gửi và không có bản ghi bền vững để publisher khôi phục.

After-commit callback hữu ích cho tín hiệu hoặc thao tác phụ có thể chấp nhận mất/được retry ở nơi khác. Với message nghiệp vụ quan trọng, outbox bền vững thường đáng tin cậy hơn.

Không coi callback in-memory là thay thế cho durable outbox.

## 26. Message writer thất bại sau khi gửi một phần chunk

Một writer publish nhiều message trong một chunk có thể gửi thành công một số message rồi thất bại ở message tiếp theo.

~~~text
Chunk = [E1, E2, E3, E4]

Publish E1 -> success
Publish E2 -> success
Publish E3 -> failure
Publish E4 -> not attempted
~~~

Nếu broker không tham gia transaction có thể rollback, E1 và E2 vẫn tồn tại. Khi Spring Batch retry chunk, E1 và E2 có thể được publish lại.

Cần:

- Event ID ổn định cho từng item.
- Producer idempotence hoặc transaction nếu broker hỗ trợ và pattern phù hợp.
- Consumer deduplication.
- Ghi nhận kết quả publish theo event.
- Không giả định writer.write(chunk) là atomic chỉ vì nó là một lần gọi Java.

Nếu dùng Kafka producer transaction, cần thiết kế transaction boundary phù hợp và hiểu quan hệ với chunk/database transaction. Nếu dùng HTTP hoặc broker không transactional, outbox thường dễ phục hồi hơn.

## 27. Writer exception và chunk rollback

Khi writer ném exception, Spring Batch thường rollback transaction chunk theo rollback policy. Điều này có thể làm reader state/checkpoint không tiến qua chunk thất bại nếu reader và repository được cấu hình transactional đúng.

Tuy nhiên, có một số ngoại lệ cần xem xét:

- Exception được phân loại noRollback.
- Writer bắt exception rồi trả về bình thường.
- Side effect xảy ra ngoài transaction.
- Reader đã ACK message trước đó.
- Checkpoint được commit ở resource khác.
- Broker offset được auto-commit độc lập.
- Transaction manager không quản lý resource mà writer sử dụng.

Không chỉ kiểm tra Step FAILED. Hãy xác nhận message vẫn có thể được redeliver hoặc replay và dữ liệu đích không bị mất.

## 28. Không nuốt exception trong writer

Đoạn code sau nguy hiểm:

~~~java
public void write(Chunk<? extends OrderUpdate> chunk) {
    try {
        messagePublisher.publish(chunk.getItems());
    } catch (Exception exception) {
        log.error("Publish failed", exception);
        // Trả về bình thường.
    }
}
~~~

Composite hoặc Step có thể coi write đã thành công. Chunk có thể commit và reader có thể tiến checkpoint, dù message chưa được publish.

Nếu publish là điều kiện bắt buộc để chunk thành công, hãy truyền exception ra ngoài:

~~~java
public void write(Chunk<? extends OrderUpdate> chunk) throws Exception {
    messagePublisher.publish(chunk.getItems());
}
~~~

Nếu cần chấp nhận lỗi publish tạm thời, dùng retry hoặc outbox. Nếu nghiệp vụ cho phép bỏ qua, phải ghi nhận trạng thái pending/failed bền vững và có quy trình repair.

Log không phải nơi lưu message bền vững.

## 29. Reader và writer phải dùng transaction manager phù hợp

Một Step chỉ nhận một PlatformTransactionManager cho chunk. Nếu reader nhận message từ broker và writer ghi database, hãy xác định transaction manager đó quản lý resource nào.

Các trường hợp:

- DataSourceTransactionManager: quản lý JDBC database transaction.
- JpaTransactionManager: quản lý JPA EntityManagerFactory.
- KafkaTransactionManager: quản lý Kafka transaction.
- JmsTransactionManager: quản lý JMS Session.
- JtaTransactionManager: có thể điều phối nhiều XA resource nếu được cấu hình đầy đủ.

Không thể truyền hai transaction manager cho một chunk và kỳ vọng Spring Batch tự phối hợp mọi resource. Nếu cần XA/JTA, cả resource, driver, broker và transaction coordinator phải hỗ trợ; cần cấu hình recovery log và vận hành transaction manager đúng cách.

Nếu không dùng XA, thiết kế inbox/outbox hoặc idempotent redelivery thường đơn giản và bền vững hơn.

## 30. Transaction manager khác nhau tạo ra cửa sổ lỗi

Ví dụ database transaction và broker transaction độc lập:

~~~text
DB transaction begins
      |
      v
DB writer updates order
      |
      v
DB commit
      |
      v
Broker ACK
      |
      +--> lỗi / crash
~~~

Nếu crash sau DB commit nhưng trước ACK, message được giao lại. Inbox deduplication giúp lần sau không áp dụng business update lần nữa.

Nếu ACK trước DB commit:

~~~text
Broker ACK
      |
      v
DB writer update
      |
      +--> lỗi / rollback
~~~

Message có thể mất. Vì vậy, nếu không có transaction phối hợp, thứ tự ưu tiên là commit business state trước ACK và chấp nhận duplicate.

Nếu DB commit thành công nhưng broker ACK liên tục thất bại, cần có monitoring và deduplication. Không cố gắng "chữa" bằng cách ACK trước.

## 31. Batch size và acknowledgement granularity

Một chunk có thể chứa nhiều message. Nếu ack từng message ngay khi read() trả về, chunk rollback có thể không redeliver được các message đã ack.

Một chiến lược khác là acknowledge theo chunk sau khi writer hoàn tất và transaction commit. Khi đó cần giữ danh sách delivery tag/receipt handle/offset tương ứng với chunk.

Cần lưu ý:

- RabbitMQ delivery tag thuộc channel và cần ack đúng channel.
- SQS cần receipt handle mới nhất cho message delivery.
- Kafka offset commit thường theo partition và offset tiếp theo, không phải ack từng record như queue.
- JMS ack mode/session transaction có semantics riêng.

Chunk size lớn làm tăng số message đang pending và lượng công việc phải redeliver khi lỗi. Chunk size nhỏ giảm phạm vi rollback nhưng tăng transaction/ack overhead.

Chọn chunk size theo throughput, memory, broker limits và recovery cost. Đừng ack từng message nếu transaction semantics yêu cầu ack theo chunk.

## 32. Visibility timeout và thời gian chunk

Với SQS hoặc broker dùng lease/visibility, thời gian xử lý chunk phải phù hợp với timeout.

Nếu chunk chạy 10 phút nhưng visibility timeout là 2 phút, message có thể xuất hiện lại trước khi writer hoàn tất. Một consumer khác có thể nhận cùng message và ghi song song.

Biện pháp:

- Đặt visibility timeout lớn hơn thời gian xử lý dự kiến có biên an toàn.
- Gia hạn visibility trong khi xử lý nếu broker hỗ trợ.
- Giữ chunk size và timeout phù hợp.
- Dùng idempotency để chống concurrent duplicate.
- Có lease/lock theo business key khi cần serialization.

Visibility timeout không phải transaction lock tuyệt đối. Consumer có thể mất lease do network failure hoặc process pause.

## 33. Poison message và retry exhaustion

Khi message không hợp lệ hoặc luôn làm writer lỗi, retry limit cuối cùng sẽ hết. Cần quy định trạng thái tiếp theo.

~~~text
Receive
  |
  v
Attempt processing
  |
  +--> Success: commit then ACK
  |
  +--> Transient failure: rollback, delay, redeliver
  |
  +--> Permanent failure: persist to DLQ/rejected store
  |
  +--> Retry limit reached: quarantine / DLQ
~~~

Không ACK message chỉ vì retry limit đã hết. Trước tiên cần bảo đảm payload và metadata đã được ghi bền vững vào nơi có thể tra cứu/replay.

Nếu DLQ publish thất bại, message gốc vẫn cần được giữ hoặc redeliver. Cần tránh một vòng lặp DLQ-to-main không giới hạn.

## 34. Restart Job sau khi writer lỗi

Khi Step thất bại, restart cùng JobInstance cần giữ các identifying JobParameters và reader state phù hợp.

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", "orders-20261115-001", true)
        .addString("topic", "orders.in", true)
        .toJobParameters();
~~~

Các thông tin ảnh hưởng tập message cần giữ ổn định:

- Topic/queue hoặc subscription.
- Partition assignment hoặc partition set.
- Starting offset/sequence nếu dùng snapshot.
- Batch/window ID.
- Consumer/reader name.
- Schema version và mapping policy.
- Input manifest hoặc message range nếu có.

Nếu restart dùng consumer group offset hiện tại nhưng offset đã bị commit độc lập trước khi chunk commit, reader có thể bỏ qua message. Cần xác định offset source of truth: broker committed offset, Spring Batch ExecutionContext hay manifest/staging store.

Không thay đổi identifying parameters giữa restart nếu muốn tiếp tục cùng JobInstance.

## 35. Broker retention và replay window

Không ACK message không có nghĩa message có thể được giữ vô thời hạn trong mọi hệ thống.

- Queue có thể có message TTL.
- Kafka topic có retention theo thời gian/dung lượng.
- SQS có retention tối đa theo cấu hình dịch vụ.
- DLQ có retention riêng.
- Message có thể bị dead-letter sau số lần redelivery.

Nếu Job lỗi kéo dài hơn retention, message có thể hết hạn trước khi được xử lý lại.

Cần đặt retention theo thời gian khôi phục tối đa, vận hành DLQ và quy trình replay. Với Kafka, consumer phải đọc lại từ offset còn nằm trong retention; nếu offset đã hết dữ liệu, cần khôi phục từ archive hoặc nguồn gốc khác.

Không xem broker là kho lưu trữ vĩnh viễn nếu retention policy không bảo đảm điều đó.

## 36. Monitoring để phát hiện message có nguy cơ mất

Theo dõi cả broker và Spring Batch:

| Metric | Ý nghĩa |
|---|---|
| messages_received | Số message đã nhận |
| messages_acknowledged | Số message đã ACK/delete |
| records_processed | Số item xử lý thành công |
| writer_error_count | Số lần writer lỗi |
| retry_count | Số lần retry |
| redelivery_count | Số lần message được giao lại |
| dlq_count | Số message vào DLQ |
| consumer_lag | Khoảng cách giữa offset hiện tại và end offset |
| queue_depth | Số message đang chờ |
| oldest_message_age | Tuổi message cũ nhất |
| chunk_rollback_count | Số chunk rollback |
| duplicate_detected_count | Số message bị deduplicate |

Các metric cần có cùng khoảng thời gian và cùng định nghĩa. Không so sánh tổng received với tổng processed nếu có redelivery mà không tính unique message ID.

Log nên chứa message ID, correlation ID, source partition/offset hoặc queue, delivery attempt, JobExecution ID và StepExecution ID. Tránh log toàn bộ payload nhạy cảm.

Alert khi queue age tăng, consumer lag kéo dài, ACK tăng nhưng business write giảm, DLQ tăng hoặc writer lỗi liên tục.

## 37. Kiểm thử writer lỗi và redelivery

Một integration test quan trọng:

1. Đưa một message M-100 vào broker test.
2. Reader nhận message nhưng chưa ACK.
3. Writer được cấu hình cố ý ném exception.
4. Xác nhận chunk rollback.
5. Xác nhận message vẫn còn trong broker hoặc được redeliver.
6. Sửa writer để thành công.
7. Chạy lại và xác nhận business update được commit.
8. Xác nhận message chỉ được ACK sau khi commit thành công.

Không chỉ mock ItemReader rồi xác nhận writer được gọi. Cần test broker/consumer acknowledgement thật hoặc một test harness mô phỏng rõ lifecycle.

Dùng broker test container hoặc embedded broker phù hợp với công nghệ thực tế. Nếu behavior phụ thuộc channel/session/offset, mock đơn thuần không chứng minh được.

## 38. Kiểm thử crash sau database commit nhưng trước ACK

Đây là cửa sổ duplicate quan trọng nhất.

~~~text
1. Nhận message M-100
2. DB transaction commit business update + inbox row
3. Cố ý dừng process trước ACK
4. Khởi động consumer lại
5. Broker redeliver M-100
6. Inbox unique key phát hiện duplicate
7. Không áp dụng business update lần hai
8. ACK message
~~~

Test cần xác nhận:

- Inbox record tồn tại sau lần đầu.
- Business effect chỉ xuất hiện một lần.
- Message được redeliver.
- Duplicate được nhận diện bằng cùng message ID.
- ACK lần sau thành công.
- Job/consumer không tạo thêm side effect.

Đây là bằng chứng thực tế cho exactly-once effect thông qua at-least-once delivery và deduplication.

## 39. Kiểm thử outbox khi publish lỗi

Với outbound message writer:

1. Chunk cập nhật business table và insert outbox event.
2. Commit database thành công.
3. Làm broker unavailable.
4. Xác nhận outbox event vẫn ở trạng thái pending.
5. Khôi phục broker.
6. Publisher gửi event.
7. Giả lập crash sau publish nhưng trước khi đánh dấu SENT.
8. Publisher gửi lại event.
9. Consumer deduplicate theo event ID.

Test cần chứng minh event không mất khi publisher lỗi và duplicate không tạo business effect trùng.

Không chỉ kiểm tra outbox row được tạo. Cần test cả retry, lease, crash và duplicate publish.

## 40. Những lỗi thường gặp

### ACK ngay trong read()

Message bị xác nhận trước khi writer thành công. Chỉ ACK sau chunk commit hoặc dùng transaction phối hợp phù hợp.

### Dùng auto-commit offset khi writer còn có thể lỗi

Kafka có thể bỏ qua record đã commit offset. Tắt auto-commit nếu ứng dụng quản lý offset thủ công và xác minh commit timing.

### Nghĩ database rollback sẽ đưa message về queue

Hai resource không tự atomic. Cần broker transaction phối hợp, XA nếu phù hợp hoặc idempotent redelivery.

### ACK sau commit nhưng không chống duplicate

Crash giữa commit và ACK khiến message được giao lại. Dùng inbox table, unique key hoặc idempotency key.

### Skip mọi writer exception

Message có thể bị bỏ qua dù business update chưa thành công. Chỉ skip khi payload đã được lưu bền vững vào DLQ/rejected store.

### Retry vô hạn

Poison message tạo hot loop và chặn throughput. Dùng retry limit, backoff và DLQ.

### Nuốt exception trong writer

Step có thể commit dù publish/write thất bại. Truyền exception hoặc ghi trạng thái pending bền vững.

### Chunk ack từng message trong read()

Một chunk rollback có thể không redeliver được message đã ACK. Đồng bộ acknowledgement theo chunk semantics.

### Không gia hạn visibility timeout

Message có thể được giao cho consumer khác trong khi chunk đầu còn chạy. Đặt timeout phù hợp và dùng idempotency.

### Dùng ExecutionContext làm bằng chứng broker offset đã commit

Checkpoint local và broker committed offset là hai state khác nhau trừ khi được phối hợp rõ ràng. Xác định một source of truth.

### Dùng afterCommit callback thay cho outbox

Process crash trước callback có thể làm mất event. Dùng outbox bền vững cho message quan trọng.

### Cho rằng broker exactly-once bao phủ database

Guarantee thường chỉ có phạm vi trong broker. Dùng inbox/outbox hoặc transaction coordination cho hệ thống ngoài.

## 41. Quy trình thiết kế không mất message

Khi xây dựng Spring Batch Job xử lý message, hãy xác định:

1. Nguồn là Kafka, RabbitMQ, JMS, SQS hay hệ thống khác?
2. Message được nhận, ACK, delete hoặc commit offset ở thời điểm nào?
3. Reader có acknowledge ngay trong read() không?
4. Writer lỗi có làm chunk transaction rollback không?
5. Message có thể redeliver sau rollback không?
6. Broker và database có cùng transaction hay độc lập?
7. Nếu DB commit nhưng ACK thất bại, duplicate được xử lý thế nào?
8. Message ID hoặc idempotency key có ổn định không?
9. Inbox record có commit cùng business update không?
10. Retry policy có giới hạn và backoff không?
11. Skip có lưu message bền vững vào DLQ trước khi ACK không?
12. Outbound event có dùng transactional outbox không?
13. Offset/reader checkpoint có tiến chỉ qua chunk đã commit không?
14. Visibility timeout và broker retention có đủ dài không?
15. Restart có giữ cùng topic, partition, offset/window và schema version không?
16. Test có bao phủ writer failure, redelivery, crash-before-ack và duplicate handling không?

Để không mất message khi writer lỗi, message phải còn khả năng được broker giao lại cho tới khi chunk ghi thành công. Nếu không có transaction nguyên tử giữa broker và database, hãy ưu tiên at-least-once delivery, commit business data trước ACK, lưu message ID trong inbox cùng transaction và làm writer idempotent. Với chiều publish, ghi business data và outbox event trong cùng transaction rồi publish bằng worker có retry. Retry có giới hạn, DLQ phải lưu bền vững trước khi ACK và restart phải khôi phục đúng offset/manifest. Như vậy, writer failure có thể làm message được giao lại, nhưng không làm mất dữ liệu và không tạo hiệu ứng nghiệp vụ trùng.
