# Retry message processing

Trong Spring Batch, message processing có thể bao gồm đọc message từ broker, chuyển đổi/kiểm tra payload rồi gửi message tới một destination khác. Khi broker tạm thời không sẵn sàng, network timeout, acknowledgement bị trễ hoặc consumer gặp lỗi phụ thuộc hạ tầng, job cần có cơ chế thử lại có kiểm soát.

Retry giúp xử lý lỗi có khả năng phục hồi mà không phải dừng job ngay lập tức. Tuy nhiên, retry message có rủi ro riêng: một lần gửi có thể đã được broker chấp nhận nhưng client chưa nhận được acknowledgement; khi thử lại, cùng message có thể được gửi lần thứ hai. Tương tự, consumer có thể xử lý business update thành công nhưng lỗi trước khi acknowledgement được xác nhận, khiến broker phát lại message.

Vì vậy, thiết kế retry phải giải quyết đồng thời bốn câu hỏi:

- Lỗi nào có khả năng phục hồi và được phép retry?
- Retry ở tầng nào: broker client, Spring Batch step hay cơ chế broker/consumer?
- Khi nào một lần xử lý được xem là thành công để checkpoint hoặc acknowledge?
- Làm sao để duplicate do retry không tạo business effect trùng?

Trong Spring Batch, retry thường được cấu hình ở chunk-oriented step bằng fault-tolerant processing. Với message producer, writer phải truyền lỗi gửi lên step sau khi chờ kết quả theo policy. Với message consumer, cần phối hợp checkpoint của batch với acknowledgement/visibility timeout của broker để không mất message và có thể xử lý lại an toàn.

## Retry trong message processing là gì?

Retry là việc thực hiện lại một thao tác thất bại sau khi xác định lỗi có thể tạm thời. Trong pipeline message, thao tác có thể là:

- Đọc message hoặc payload từ nguồn.
- Gọi service để enrich/validate message.
- Gửi message tới Kafka, JMS hoặc RabbitMQ.
- Ghi trạng thái xử lý hoặc kết quả vào database.
- Acknowledge message với broker sau khi business processing hoàn tất.

Ví dụ, một batch step đọc các event đang pending trong outbox rồi publish lên Kafka. Nếu Kafka tạm thời mất kết nối, writer có thể ném exception. Spring Batch rollback chunk theo transaction manager và retry theo policy đã cấu hình. Nếu producer thực tế đã gửi record trước khi connection đứt, lần retry có thể gửi duplicate. Consumer cần nhận diện event ID để không thực hiện business action hai lần.

Retry không sửa được lỗi dữ liệu hoặc cấu hình cố định. Payload sai schema, topic không tồn tại, credential sai hay serialization error thường cần fail/reject/quarantine thay vì thử lại vô hạn.

## Phân biệt các tầng retry

Một hệ thống message có thể retry ở nhiều tầng. Các tầng này giải quyết những failure window khác nhau và có thể nhân số lần thử nếu không phối hợp.

| Tầng | Thành phần thực hiện | Ví dụ |
| --- | --- | --- |
| Client retry | Kafka producer, JMS provider hoặc AMQP client | Gửi lại request khi network tạm thời lỗi |
| Step retry | Spring Batch fault-tolerant step | Gọi lại xử lý khi writer ném exception |
| Broker redelivery | Broker/consumer container | Phát lại message chưa được acknowledge |
| Application retry | Service hoặc `RetryTemplate` | Thử lại một API call phụ thuộc hạ tầng |
| Recovery/DLQ | Broker hoặc ứng dụng | Chuyển message không thể xử lý sang nơi cách ly |

Ví dụ một lần `KafkaTemplate.send()` có thể được producer retry nội bộ nhiều lần. Nếu future vẫn thất bại và writer ném exception, Spring Batch có thể retry writer/chunk. Nếu lần gửi đầu đã được broker ghi nhưng acknowledgement bị mất, batch retry có thể gửi lại event. Consumer cũng có thể retry khi handler lỗi và broker redeliver nếu message chưa được ack.

Hãy tính retry budget tổng thể. Không đặt 10 lần ở client, 5 lần ở step và 10 lần ở consumer mà không có giới hạn thời gian; một thao tác có thể bị thử rất nhiều lần, kéo dài job và tạo retry storm.

## Phân loại lỗi trước khi retry

Điều kiện quan trọng nhất là phân biệt lỗi transient và permanent.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Transient infrastructure | Broker tạm unavailable, network reset, timeout ngắn, leader election | Retry có giới hạn và backoff |
| Throttling/quota | Broker trả về rate limit hoặc quá tải tạm thời | Backoff, giảm concurrency hoặc điều tiết throughput |
| Authentication/configuration | Credential sai, ACL thiếu, destination không tồn tại | Fail nhanh và sửa cấu hình |
| Serialization/schema | Payload không serialize được, schema không tương thích | Reject/quarantine hoặc fail; retry thường không giúp |
| Business validation | Thiếu business key, trạng thái không hợp lệ | Reject/skip theo quy tắc nghiệp vụ |
| Duplicate/conflict | Event ID đã xử lý, unique constraint conflict | Xử lý idempotent; không retry mù quáng |
| Permanent resource failure | Queue/topic bị xóa, payload vượt giới hạn | Fail hoặc chuyển quy trình recovery phù hợp |

Không phân loại lỗi chỉ theo class exception cấp ngoài cùng nếu framework bọc exception. Hãy xem cause chain và exception cụ thể của broker/client. Ví dụ `MessagingException` có thể bọc timeout tạm thời hoặc lỗi serialization vĩnh viễn.

### Retryable và non-retryable exception

Với Spring Batch, có thể khai báo exception được retry và exception không được retry:

```java
return new StepBuilder("publishEventsStep", jobRepository)
        .<OutboxEvent, OutboxEvent>chunk(100, transactionManager)
        .reader(outboxReader)
        .writer(messageWriter)
        .faultTolerant()
        .retry(TransientBrokerException.class)
        .retryLimit(3)
        .noRetry(MessageSerializationException.class)
        .build();
```

`TransientBrokerException` và `MessageSerializationException` là exception do ứng dụng định nghĩa trong ví dụ. Trong production, map exception từ Kafka/JMS/AMQP client sang nhóm exception có ý nghĩa thay vì retry toàn bộ `Exception`.

Một số exception có thể là lỗi hạ tầng nhưng không nên retry ngay, ví dụ authentication failure hoặc topic authorization. Retry liên tục chỉ tạo log noise và kéo dài thời gian fail.

### Không retry mọi Exception

Ví dụ sau quá rộng:

```java
.faultTolerant()
.retry(Exception.class)
.retryLimit(20)
```

Nó có thể retry cả lỗi lập trình, validation, schema và cấu hình. Hãy chỉ định loại lỗi transient và giới hạn số lần thử. Nếu cần xử lý một số exception theo cách khác, dùng `noRetry`, skip policy hoặc exception classifier theo API của Spring Batch version đang dùng.

## Cấu hình retry trong Spring Batch

Chunk step hỗ trợ fault tolerance qua `faultTolerant()`. Retry policy xác định exception nào được thử lại và giới hạn số lần thử.

Ví dụ cơ bản:

```java
@Bean
Step publishEventsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OutboxEvent> eventReader,
        ItemWriter<OutboxEvent> messageWriter) {

    return new StepBuilder("publishEventsStep", jobRepository)
            .<OutboxEvent, OutboxEvent>chunk(100, transactionManager)
            .reader(eventReader)
            .writer(messageWriter)
            .faultTolerant()
            .retry(TransientBrokerException.class)
            .retryLimit(3)
            .build();
}
```

Trong API Spring Batch 5, `retryLimit(3)` biểu diễn giới hạn retry được cấu hình cho exception đã chỉ định; cần hiểu cách đếm lần xử lý ban đầu và số lần retry theo tài liệu version đang dùng. Đừng coi con số này là tổng số request broker nếu client cũng có retry nội bộ.

Nếu lỗi vượt giới hạn retry và không có skip policy phù hợp, step sẽ fail. Đây thường là lựa chọn đúng với event bắt buộc phải publish: fail để vận hành điều tra và restart/replay, thay vì âm thầm bỏ message.

### Retry kết hợp skip

Retry và skip có mục đích khác nhau:

- Retry: thử lại cùng thao tác vì lỗi có thể phục hồi.
- Skip: chấp nhận bỏ qua một item lỗi theo policy và ghi nhận nó.

Ví dụ chỉ skip lỗi dữ liệu không hợp lệ, còn lỗi broker transient được retry:

```java
.faultTolerant()
.retry(TransientBrokerException.class)
.retryLimit(3)
.skip(InvalidEventException.class)
.skipLimit(50)
```

Không cấu hình skip lỗi broker chỉ để job hoàn tất. Nếu event bị bỏ qua mà không có outbox/reject persistence, hệ thống có thể mất sự kiện vĩnh viễn.

## Backoff giữa các lần retry

Retry liên tục không có khoảng nghỉ có thể làm broker đang quá tải càng quá tải hơn. Backoff tạo khoảng chờ giữa các lần thử.

Các chiến lược phổ biến:

- **Fixed backoff:** khoảng nghỉ cố định giữa các lần thử.
- **Exponential backoff:** thời gian nghỉ tăng dần sau mỗi lần thất bại.
- **Exponential backoff with jitter:** thêm độ ngẫu nhiên để nhiều worker không retry cùng thời điểm.
- **Capped backoff:** giới hạn thời gian chờ tối đa.

Ví dụ exponential backoff:

```java
ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

return new StepBuilder("publishEventsStep", jobRepository)
        .<OutboxEvent, OutboxEvent>chunk(100, transactionManager)
        .reader(eventReader)
        .writer(messageWriter)
        .faultTolerant()
        .retry(TransientBrokerException.class)
        .retryLimit(4)
        .backOffPolicy(backOff)
        .build();
```

Ví dụ dùng `ExponentialBackOffPolicy` của Spring Retry. Import/package và API cấu hình phải khớp version Spring Batch/Spring Retry của dự án. Một số version cung cấp builder hoặc cách cấu hình retry khác; nguyên tắc vẫn là backoff có giới hạn.

Nếu thời gian ban đầu là 500 ms và multiplier là 2, các khoảng nghỉ tăng xấp xỉ 0.5 s, 1 s, 2 s, 4 s, sau đó bị giới hạn bởi max interval. Tổng thời gian chờ phải nằm trong SLA và broker delivery timeout.

### Jitter tránh retry đồng loạt

Nếu 100 worker cùng gặp broker outage và đều retry sau đúng 1 giây, chúng có thể tạo một đợt tải lớn cùng lúc. Jitter phân tán thời điểm retry để giảm đồng bộ.

Có thể dùng backoff policy có jitter nếu version thư viện hỗ trợ, hoặc một policy tùy chỉnh. Không tự thêm random delay không giới hạn; vẫn cần max interval và tổng deadline.

## Retry ở producer client và retry ở Spring Batch

Producer client có thể tự retry một lần gửi trước khi trả kết quả cuối cùng cho ứng dụng. Ví dụ Kafka producer dùng `retries` và `delivery.timeout.ms`; AMQP/JMS client cũng có các cơ chế reconnect/recovery riêng.

Step retry bắt đầu sau khi writer nhận lỗi cuối cùng và ném exception. Do đó, tổng thời gian và số lần thử là kết hợp của hai tầng:

```text
Spring Batch retry attempt 1
    |
    +--> Producer client send
    |       +--> internal retry
    |       +--> internal retry
    |       +--> final failure
    |
    +--> writer throws TransientBrokerException
    |
    +--> backoff của step
    |
Spring Batch retry attempt 2
    |
    +--> Producer client send lại
            ...
```

Hãy đặt timeout và retry budget theo tổng thời gian. Ví dụ, producer có thể mất tới 30 giây cho một record; step retry 3 lần có thể khiến một chunk chờ lâu hơn 90 giây cộng backoff. Transaction chunk có thể giữ lock trong thời gian đó.

Với lỗi broker kéo dài, outbox publisher step riêng thường giúp business transaction ban đầu không phải giữ lâu trong lúc chờ broker hồi phục.

## Retry trong writer gửi message

Writer phải báo lỗi đúng thời điểm để Spring Batch quyết định retry. Nếu gửi bất đồng bộ, không được trả về ngay khi chưa biết kết quả theo policy.

Ví dụ writer Kafka chờ kết quả:

```java
public class KafkaEventWriter implements ItemWriter<OutboxEvent> {

    private final KafkaTemplate<String, EventPayload> kafkaTemplate;

    @Override
    public void write(Chunk<? extends OutboxEvent> chunk) throws Exception {
        List<CompletableFuture<SendResult<String, EventPayload>>> futures =
                new ArrayList<>();

        for (OutboxEvent event : chunk) {
            EventPayload payload = toPayload(event);
            futures.add(kafkaTemplate.send(
                    "domain-events",
                    event.aggregateId(),
                    payload));
        }

        for (CompletableFuture<SendResult<String, EventPayload>> future : futures) {
            future.get(30, TimeUnit.SECONDS);
        }
    }
}
```

Ví dụ dùng Spring Kafka 3.x. Với version cũ, kiểu future có thể khác. Trong code thực tế, cần chuyển exception của future thành exception transient/permanent phù hợp và giữ event ID ổn định.

Nếu một future thất bại sau khi một số future khác đã thành công, writer ném exception có thể làm chunk rollback nhưng các message đã được broker nhận vẫn tồn tại. Khi Spring Batch retry chunk, chúng có thể được gửi lại. Đây là lý do consumer phải idempotent và event ID phải ổn định qua retry.

### Không nuốt lỗi send

Không nên viết:

```java
try {
    kafkaTemplate.send(topic, key, payload);
} catch (Exception ex) {
    log.warn("Could not send", ex);
    // tiếp tục và trả về như thành công
}
```

Đoạn code này còn không chờ future, và nếu lỗi được báo bất đồng bộ thì catch cũng không bắt được. Step có thể commit checkpoint dù message chưa được gửi.

Hãy chờ kết quả, phân loại exception và ném lỗi lên khi thao tác bắt buộc thất bại.

## Retry khi đọc message từ broker

Một batch step có thể đọc message từ broker hoặc từ một staging/inbox table. Với message broker, cần phối hợp việc lấy message, xử lý chunk và acknowledge.

Mô hình tổng quát:

```text
Broker / queue
    |
    v
Message reader / adapter
    |
    v
Processor
    |
    v
Writer (database or next broker)
    |
    v
Commit business result
    |
    v
Broker acknowledgement
```

Điểm quyết định là acknowledgement xảy ra trước hay sau khi business result được commit. Nếu ack trước rồi database rollback, message có thể mất. Nếu commit database trước rồi ack thất bại, broker có thể redeliver và message được xử lý lại.

Với JMS, consumer acknowledgement/session transaction có semantics phụ thuộc listener/container và transaction manager. Với Kafka, consumer offset commit là mốc xác nhận tiến độ; commit offset trước business transaction có thể mất message, commit sau có thể dẫn tới duplicate nếu crash ở giữa. Với RabbitMQ, consumer ack sau xử lý là cách phổ biến để broker redeliver khi worker chết trước ack.

Spring Batch không tự biết cách acknowledge mọi broker. Adapter/reader hoặc một integration layer phải quản lý acknowledgement theo contract của broker. Nếu yêu cầu retry/redelivery phức tạp, cần dùng cơ chế tích hợp được hỗ trợ và test trên broker thật.

### Message visibility timeout và lease

Một số queue service dùng visibility timeout hoặc lease. Nếu xử lý message lâu hơn timeout, broker có thể phát message cho worker khác trong khi worker đầu vẫn chạy. Gia hạn visibility/lease hoặc chọn timeout đủ dài; consumer vẫn cần idempotency vì timeout và crash có thể tạo concurrent duplicate.

### Không acknowledge message trước commit

Nếu message đã ack trước khi database commit, lỗi sau đó có thể làm message mất khỏi queue dù business work chưa lưu. Thông thường nên ack sau khi business processing thành công theo transaction semantics của integration layer. Tuy nhiên, việc phối hợp transaction cụ thể phụ thuộc broker và framework; không áp dụng một quy tắc code chung cho mọi adapter.

## Retry processor và service phụ trợ

Không phải mọi lỗi message đều xảy ra ở writer. Processor có thể gọi service ngoài để kiểm tra fraud, lấy tỷ giá hoặc enrich metadata. Nếu service tạm unavailable, retry có thể phù hợp.

```java
return new StepBuilder("enrichEventsStep", jobRepository)
        .<RawEvent, EnrichedEvent>chunk(100, transactionManager)
        .reader(eventReader)
        .processor(enrichmentProcessor)
        .writer(eventWriter)
        .faultTolerant()
        .retry(TransientServiceException.class)
        .retryLimit(3)
        .build();
```

Nếu processor gọi API có side effect, retry có thể thực hiện hành động nhiều lần. Với operation không idempotent, dùng idempotency key hoặc thiết kế API theo kiểu query/read-only. Tốt nhất, processor nên tạo kết quả xác định từ input và dependency có thể retry an toàn.

## Stateful và stateless retry

Retry có thể được thực hiện trong cùng một call flow (stateless) hoặc lưu trạng thái retry giữa các lần gọi (stateful), tùy framework/policy.

- **Stateless retry:** thao tác được thử lại ngay trong cùng execution context cho tới khi thành công hoặc hết limit.
- **Stateful retry:** giữ retry state gắn với một key/item qua các lần gọi, hữu ích khi lỗi yêu cầu rollback rồi thử lại ở một transaction mới.

Trong chunk step, Spring Batch quản lý retry context và item identity theo cơ chế fault-tolerant step. Không tự lưu bộ đếm retry trong singleton field của writer vì nhiều item/execution có thể dùng chung writer và restart sẽ làm mất state đó.

Nếu cần retry bền vững qua job restart hoặc giữa các lần schedule, hãy lưu trạng thái attempt/deadline trong database/outbox hoặc dùng broker redelivery policy. Retry in-memory của một step không phải hàng đợi retry bền vững vô hạn.

## Retry và transaction của chunk

Chunk transaction có thể rollback khi writer ném exception. Spring Batch sau đó có thể retry theo policy. Tuy nhiên, rollback database không thể thu hồi message đã được broker nhận nếu broker không tham gia transaction chung.

Ví dụ:

```text
Chunk attempt 1
    |
    +--> publish event A -> broker confirms
    +--> publish event B -> timeout (unknown outcome)
    +--> writer throws
    +--> database transaction rolls back
    |
Chunk retry
    |
    +--> publish event A again
    +--> publish event B again
```

Event A có thể được gửi hai lần. Event B có thể đã được broker nhận dù client timeout. Không thể phân biệt chắc chắn chỉ bằng timeout. Consumer phải deduplicate theo event ID hoặc publisher cần một giao thức bền vững như outbox cộng idempotent consumer.

### Không giữ transaction lâu trong backoff

Nếu retry diễn ra bên trong chunk transaction, transaction/connection có thể bị giữ trong thời gian chờ, tùy retry placement và transaction boundary. Điều này có thể giữ lock, chiếm connection pool và làm giảm throughput.

Đặt timeout/backoff phù hợp, tránh retry lâu cho broker outage. Nếu broker thường xuyên gián đoạn hoặc cần retry trong nhiều phút/giờ, tách publish thành outbox publisher job/step có transaction ngắn thường dễ vận hành hơn.

## Transactional outbox cho retry bền vững

Transactional outbox lưu ý định phát message trong cùng transaction database với thay đổi nghiệp vụ. Một publisher riêng đọc các outbox row pending và gửi tới broker.

```text
Business chunk transaction
    |
    +--> update business row
    +--> insert outbox row (PENDING)
    +--> COMMIT
             |
             v
       Outbox publisher step
             |
             +--> claim pending row
             +--> publish message
             +--> wait for acknowledgement
             +--> mark published
```

Nếu broker unavailable, outbox row vẫn tồn tại để publisher thử lại ở lần chạy sau. Business transaction không cần giữ mở trong thời gian broker phục hồi.

### Retry outbox publisher

Publisher có thể dùng Spring Batch retry cho lỗi transient trong một execution và trạng thái outbox để thử lại ở execution sau. Ví dụ:

```java
.faultTolerant()
.retry(TransientBrokerException.class)
.retryLimit(5)
.backOffPolicy(backOffPolicy)
```

Sau khi hết retry, không xóa outbox row. Có thể giữ `PENDING`, chuyển sang `RETRY` với `next_attempt_at`, hoặc chuyển `FAILED`/`DEAD` sau ngưỡng vận hành để operator xử lý. Trạng thái cụ thể phải phản ánh việc publisher có chắc chắn broker chưa nhận message hay outcome còn unknown.

### Claim và lease

Nhiều publisher không được cùng gửi một outbox row đồng thời nếu muốn giảm duplicate. Có thể claim row bằng status/lease:

```sql
UPDATE outbox_event
SET status = 'PROCESSING',
    lease_owner = :workerId,
    lease_until = :leaseUntil
WHERE event_id = :eventId
  AND (status = 'PENDING' OR lease_until < :now)
```

Đây là ví dụ khái niệm; cần dùng locking/conditional update phù hợp database và kiểm tra số row bị update. Lease phải đủ dài hoặc được gia hạn khi publish lâu. Nếu worker chết sau khi broker nhận message nhưng trước khi mark published, lease hết hạn và event có thể được gửi lại. Event ID và consumer idempotency vẫn cần thiết.

## Idempotency: điều kiện quan trọng khi retry message

Idempotency nghĩa là cùng một thao tác được thực hiện nhiều lần nhưng kết quả nghiệp vụ cuối cùng tương đương một lần. Với message, consumer nên nhận diện message đã xử lý bằng ID ổn định.

Ví dụ bảng inbox:

```sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Consumer xử lý trong một transaction:

1. Insert `(consumer_name, event_id)` vào inbox.
2. Nếu insert thành công, thực hiện business update.
3. Commit business update và inbox record cùng nhau.
4. Nếu unique key đã tồn tại, coi message là duplicate đã xử lý và acknowledge theo policy.

Nếu business update thất bại, transaction rollback cả inbox insert; broker có thể redeliver và consumer thử lại. Nếu inbox commit tách khỏi business update, có thể đánh dấu đã xử lý dù business operation thất bại.

### Event ID phải ổn định qua retry

Không tạo UUID mới mỗi lần writer gửi lại cùng một logical event. Tạo event ID trước, lưu cùng outbox/item và dùng lại trong mọi lần retry/restart. Nếu mỗi lần retry có ID khác, consumer không thể deduplicate.

Producer idempotence của Kafka giúp giảm duplicate do retry ở producer session, nhưng không giải quyết trường hợp Spring Batch restart và gửi lại cùng event bằng một producer operation mới. Event ID và consumer inbox vẫn có vai trò riêng.

## Retry, dead-letter và recovery

Sau khi hết retry, message cần một trạng thái recovery rõ ràng. Tùy loại lỗi, có thể:

- Fail step để operator sửa broker/configuration rồi restart.
- Giữ outbox row ở trạng thái retryable để publisher xử lý sau.
- Chuyển payload không hợp lệ sang reject store/DLQ.
- Đánh dấu permanent failure và tạo cảnh báo/incident.
- Replay từ nguồn bền vững sau khi sửa lỗi.

Không chuyển mọi lỗi hết retry sang DLQ một cách tự động. Lỗi broker outage có thể không phải lỗi của message; đẩy tất cả event vào DLQ làm mất thứ tự và tăng thao tác replay. Ngược lại, poison message không thể xử lý mãi trong main queue có thể cần dead-letter.

### Poison message

Poison message là message luôn thất bại do payload hoặc điều kiện cố định, ví dụ schema sai, required field thiếu hoặc consumer code không hỗ trợ event version. Retry không sửa được lỗi đó và có thể chặn các message sau nếu broker giữ ordering.

Đối với poison message:

1. Xác định lỗi permanent qua validation/schema.
2. Ghi payload/reference, event ID và nguyên nhân vào reject/DLQ an toàn.
3. Acknowledge hoặc chuyển message theo policy sau khi reject được lưu bền vững.
4. Cảnh báo operator và theo dõi tỷ lệ reject.
5. Chỉ replay sau khi payload/consumer đã được sửa.

Không log secret hoặc toàn bộ dữ liệu nhạy cảm trong DLQ metadata. Cần có retention và access control phù hợp.

## Circuit breaker và giới hạn retry

Khi broker hoặc dependency hỏng kéo dài, retry liên tục không còn hữu ích. Circuit breaker có thể ngăn gọi dependency trong một khoảng thời gian sau khi vượt ngưỡng lỗi, sau đó cho phép một số probe để kiểm tra phục hồi.

Retry và circuit breaker khác nhau:

- Retry thử lại một operation sau lỗi.
- Circuit breaker tạm ngừng gọi dependency đang có tỷ lệ lỗi cao.
- Rate limiter giới hạn tốc độ request.
- Bulkhead giới hạn tài nguyên/concurrency dành cho dependency.

Có thể dùng Spring Retry/Resilience4j hoặc cơ chế broker client phù hợp, nhưng tránh lồng nhiều retry/circuit breaker mà không có budget chung. Khi circuit open, writer nên ném exception được phân loại để step fail hoặc hoãn execution theo kế hoạch; không giả vờ thành công.

## Ordering và retry

Retry có thể ảnh hưởng thứ tự message. Ví dụ event A gửi timeout, event B gửi thành công, sau đó A được retry. Consumer có thể nhận B trước A.

Để xử lý ordering:

- Dùng partition key/aggregate key ổn định.
- Tránh cho phép message sau vượt message trước nếu business invariant yêu cầu tuần tự.
- Dùng sequence number/version trên aggregate.
- Consumer kiểm tra version và xử lý event out-of-order theo policy.
- Nếu cần ordering chặt, serialize publish theo key và thiết kế retry/parking-lot queue có kiểm soát.

Kafka ordering chỉ có phạm vi partition; RabbitMQ/JMS ordering cũng phụ thuộc queue, consumer concurrency, redelivery và broker configuration. Không giả định retry luôn giữ nguyên thứ tự ban đầu.

## Observability cho retry

Retry cần được quan sát như một tín hiệu vận hành, không chỉ là log exception.

Metrics nên có:

- Số lần retry theo step, exception type và destination.
- Số lần gửi thành công/thất bại.
- Thời gian acknowledgement và backoff.
- Số message pending/retry/failed trong outbox.
- Số message redelivered hoặc duplicate được deduplicate.
- Số message vào DLQ/reject store.
- Số chunk rollback và step restart.
- Age của message/outbox oldest pending.
- Broker availability, producer errors và consumer lag.

Log nên gắn `eventId`, `correlationId`, `JobExecutionId`, `StepExecutionId`, destination và attempt number. Không log payload nhạy cảm đầy đủ.

Một alert hữu ích có thể dựa trên age của pending outbox hoặc tỷ lệ retry vượt ngưỡng, thay vì chỉ alert mỗi lần một request retry. Điều này giúp phân biệt lỗi transient ngắn với outage kéo dài.

## Ví dụ cấu hình retry hoàn chỉnh

Ví dụ kết hợp reader outbox, writer gửi message, retry transient exception, backoff và skip dữ liệu invalid:

```java
@Bean
Step publishOutboxStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OutboxEvent> outboxReader,
        ItemProcessor<OutboxEvent, OutboxEvent> eventValidator,
        ItemWriter<OutboxEvent> kafkaWriter) {

    ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
    backOff.setInitialInterval(500L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(8_000L);

    return new StepBuilder("publishOutboxStep", jobRepository)
            .<OutboxEvent, OutboxEvent>chunk(50, transactionManager)
            .reader(outboxReader)
            .processor(eventValidator)
            .writer(kafkaWriter)
            .faultTolerant()
            .retry(TransientBrokerException.class)
            .retryLimit(4)
            .noRetry(MessageSerializationException.class)
            .skip(InvalidEventException.class)
            .skipLimit(20)
            .backOffPolicy(backOff)
            .build();
}
```

Ví dụ thể hiện cấu trúc cấu hình, không phải một cấu hình production hoàn chỉnh cho mọi broker. Cần xác định writer chờ acknowledgement, outbox row được claim/mark ở transaction nào, và event ID có ổn định hay không. Nếu skip `InvalidEventException`, phải có reject/audit persistence; nếu không, item có thể biến mất khỏi pipeline mà không có dấu vết.

## Kiểm thử retry message processing

Nên kiểm thử retry ở nhiều lớp: unit test writer, step integration test và broker integration test. Mock chỉ chứng minh code gọi đúng API; broker test mới chứng minh acknowledgement/redelivery/transaction semantics.

### Unit test retryable exception

Tạo writer test double thất bại hai lần rồi thành công. Chạy step và xác nhận số lần gọi theo retry policy, job hoàn tất và output đúng.

```java
AtomicInteger attempts = new AtomicInteger();

ItemWriter<OutboxEvent> flakyWriter = chunk -> {
    if (attempts.incrementAndGet() < 3) {
        throw new TransientBrokerException("temporary failure");
    }
};
```

Với cấu hình retry limit phù hợp, test xác nhận step thử lại và sau đó thành công. Dùng transaction manager/test repository thật cho step integration thay vì chỉ gọi `write()` trực tiếp.

### Unit test permanent exception

Cho writer ném `MessageSerializationException`. Xác nhận exception không bị retry theo policy và step fail hoặc skip đúng theo cấu hình. Đếm attempt để chứng minh lỗi permanent không tạo retry vô ích.

### Kiểm thử backoff

Không cần chờ thời gian dài trong unit test. Có thể inject policy/clock hoặc dùng backoff ngắn cho test; xác nhận số lần thử, thứ tự và tổng thời gian nằm trong giới hạn. Không làm test flaky bằng sleep dài.

### Kiểm thử future failure

Với Kafka writer, tạo future hoàn tất exceptionally và xác nhận `write()` chờ rồi ném exception. Kiểm tra future timeout và lỗi gửi sau khi một số future khác đã thành công. Xác nhận writer không trả về thành công trước khi các send bắt buộc hoàn tất.

### Kiểm thử duplicate window

Mô phỏng broker đã nhận event nhưng client timeout trước acknowledgement. Step retry và gửi lại cùng event ID. Consumer test phải chỉ thực hiện business effect một lần nhờ inbox/idempotency. Đây là test quan trọng để xác nhận at-least-once behavior.

### Kiểm thử transaction rollback

Cho một chunk gửi một số message rồi gặp lỗi. Xác nhận database transaction rollback đúng; kiểm tra message nào đã tồn tại ở broker. Test phải chứng minh side effect ngoài transaction không tự rollback.

### Kiểm thử consumer acknowledgement/redelivery

Với broker test, để consumer xử lý business update rồi mô phỏng crash trước ack. Broker có thể redeliver. Xác nhận consumer inbox ngăn duplicate và message cuối cùng được acknowledge sau khi business result commit.

### Kiểm thử outbox recovery

Mô phỏng các tình huống:

1. Business transaction rollback: không có outbox row.
2. Business transaction commit, broker unavailable: outbox vẫn pending.
3. Broker nhận event, publisher chết trước mark-published: publisher gửi lại sau lease expiry.
4. Consumer nhận duplicate: business effect chỉ xảy ra một lần.
5. Permanent payload error: row chuyển reject/dead theo policy và có audit.

### Kiểm thử retry storm và circuit breaker

Mô phỏng broker unavailable trong thời gian dài, xác nhận retry có giới hạn, backoff/jitter hoạt động và circuit breaker/rate limit ngăn tải tăng vô hạn. Theo dõi số connection/thread và transaction duration.

## Lỗi thường gặp

### Retry mọi loại exception

Lỗi schema, validation hoặc authorization không phục hồi bằng retry. Phân loại transient/permanent.

### Không giới hạn retry

Job có thể giữ transaction/connection vô thời hạn và tạo retry storm. Đặt retry limit, deadline và backoff cap.

### Lồng retry nhiều tầng mà không tính budget

Client, step và broker redelivery có thể nhân số lần thử. Tính tổng thời gian và số lần request.

### Gửi async nhưng không chờ acknowledgement

Writer có thể trả về thành công trước khi biết send failure. Await/flush theo contract và truyền lỗi lên step.

### Nghĩ rollback thu hồi message đã publish

Database và broker là hai resource độc lập nếu không có transaction coordination. Dùng outbox hoặc idempotency.

### Event ID thay đổi mỗi lần retry

Consumer không nhận ra duplicate. Giữ event ID ổn định qua retry/restart.

### Retry broker outage bằng skip

Skip có thể làm mất event. Retry/fail hoặc giữ outbox pending.

### Ack message trước business commit

Crash sau ack có thể làm mất message dù business update chưa commit. Phối hợp ack sau commit theo semantics broker.

### Consumer không idempotent

Redelivery hoặc publisher retry có thể tạo business effect trùng. Dùng inbox/unique event ID và transaction.

### Không xử lý poison message

Message lỗi vĩnh viễn có thể lặp vô hạn và chặn queue. Reject/DLQ có audit và quy trình replay.

### Không có backoff/jitter

Nhiều worker retry đồng thời làm broker quá tải thêm. Dùng backoff có cap và jitter.

### Giữ chunk transaction quá lâu

Backoff dài có thể giữ lock và connection. Tách outbox publisher hoặc giảm retry budget trong transaction.

### Không quan sát attempt và event ID

Khó xác định message nào đã gửi, retry bao nhiêu lần và cần replay gì. Gắn correlation/event ID và metrics.

## Nguyên tắc thiết kế

Khi thiết kế retry cho message processing, hãy xác định:

1. Thao tác cần retry là read, process, publish hay acknowledge?
2. Retry nằm ở client, Spring Batch, broker hay application service?
3. Exception nào transient và exception nào permanent?
4. Retry limit, backoff, jitter và deadline tổng là bao nhiêu?
5. Client retry nội bộ có được tính vào retry budget chung không?
6. Writer có chờ acknowledgement trước khi trả về không?
7. Database chunk và broker transaction có thực sự được phối hợp không?
8. Nếu outcome gửi không xác định, event ID có giữ ổn định để deduplicate không?
9. Consumer có inbox/idempotency và ack sau business commit không?
10. Outbox có cần thiết để giữ ý định publish bền vững không?
11. Poison message được reject/DLQ và replay theo quy trình nào?
12. Ordering có thể thay đổi khi retry hoặc redelivery không?
13. Monitoring có attempt, latency, pending age, duplicate và DLQ metrics không?
14. Integration test đã mô phỏng broker outage, ack timeout, duplicate, rollback, restart và recovery chưa?

Retry message processing cần được thiết kế như một cơ chế phục hồi có giới hạn. Dùng Spring Batch retry cho exception transient trong step, backoff để giảm áp lực broker và phân loại permanent failure để fail/reject đúng cách. Writer phải chờ kết quả gửi theo policy; consumer phải acknowledge theo transaction semantics và idempotent khi redelivery. Khi database update và publish phải nhất quán, transactional outbox cùng consumer inbox thường cung cấp recovery rõ ràng hơn publish trực tiếp. Luôn giữ event ID ổn định, tính retry budget qua mọi tầng và kiểm thử các cửa sổ lỗi giữa broker acknowledgement, database commit và restart.

## Ghi nhớ

Retry message processing là thử lại thao tác đọc, xử lý, publish hoặc acknowledge khi lỗi có khả năng phục hồi. Phân biệt client retry, Spring Batch step retry, broker redelivery và application retry; giới hạn tổng số lần/thời gian để tránh retry storm. Dùng `.faultTolerant().retry(...).retryLimit(...)` cho exception transient, `noRetry` cho lỗi permanent, skip chỉ khi item được reject/audit bền vững, và backoff có cap/jitter. Message writer phải chờ acknowledgement theo policy trước khi trả về; send timeout có thể có outcome không xác định nên retry có thể tạo duplicate. Database rollback không thu hồi message broker nếu hai resource không cùng transaction. Giữ event ID ổn định, consumer idempotency/inbox và ack sau business commit. Transactional outbox giúp lưu ý định publish cùng business update; publisher vẫn có thể gửi lại nên consumer phải deduplicate. Theo dõi attempt, event ID, pending age, redelivery và DLQ; kiểm thử broker outage, ack timeout, duplicate, rollback, restart và recovery trên broker tương đương production.
