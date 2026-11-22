# Xác nhận record đã được recover

## 1. Vì sao phải xác nhận recovery?

Trong hệ thống Spring Kafka, khi một record được chuyển vào luồng xử lý lỗi, mục tiêu không chỉ là **ngừng retry** mà còn phải bảo đảm record đã đi đến một trạng thái có thể kiểm soát được: xử lý thành công, được ghi bền vững vào dead-letter topic (DLT), hoặc được lưu vào một nơi phục hồi có thể tra cứu và replay.

Một record bị lỗi có thể đi qua nhiều bước:

1. Listener nhận record từ topic nguồn.
2. Listener xử lý thất bại; error handler retry theo chính sách.
3. Hết lượt retry, error handler gọi một `ConsumerRecordRecoverer`.
4. Recoverer thực hiện hành động phục hồi, chẳng hạn gửi record sang DLT.
5. Error handler và container xử lý kết quả recovery rồi quyết định tiến offset nguồn theo acknowledgment mode.
6. Một hệ thống hoặc người vận hành có thể kiểm tra DLT, xử lý lại record và xác nhận kết quả nghiệp vụ về sau.

Mỗi bước có điều kiện thành công riêng. Đặc biệt:

- **Recoverer đã được gọi** không đồng nghĩa recovery thành công.
- **Producer được gọi để gửi DLT** không đồng nghĩa broker đã xác nhận nhận DLT record.
- **Record đã được ghi sang DLT** không đồng nghĩa offset nguồn đã được commit.
- **Offset nguồn đã commit** không đồng nghĩa record DLT đã được người vận hành hoặc DLT consumer giải quyết.

Đó là lý do cần thiết kế **xác nhận recovery** ở nhiều lớp, tránh việc hệ thống âm thầm bỏ qua record ngay khi đường phục hồi gặp lỗi.

## 2. Định nghĩa chính xác trạng thái recovered

Ở tầng `DefaultErrorHandler`, một record được coi là đã được **recover** khi recoverer hoàn tất bình thường theo hợp đồng của error handler. Nếu recoverer ném exception, recovery chưa được coi là hoàn tất; error handler tiếp tục xử lý lỗi trong những lần delivery tiếp theo.

Tuy nhiên, kết quả **recoverer return bình thường** chỉ đáng tin bằng chính implementation của recoverer. Ví dụ:

~~~java
ConsumerRecordRecoverer unsafeRecoverer = (record, error) -> {
    kafkaTemplate.send(
        "orders.DLT",
        record.key(),
        record.value()
    );
    // Trả về ngay, không quan sát kết quả gửi bất đồng bộ.
};
~~~

Đoạn trên minh họa một trường hợp cần thận trọng: callback của `KafkaTemplate.send()` có thể thất bại **sau khi** recoverer đã trả về. Nếu không có cơ chế xác nhận thích hợp, container có thể xem record đã recover dù DLT publish chưa thành công.

Một hợp đồng recovery đáng tin cậy thường cần các điều kiện:

- Destination được xác định đúng và có thể ghi.
- Dữ liệu, headers và metadata cần điều tra được giữ lại.
- Hành động recovery được **xác nhận** theo bảo đảm đã chọn, ví dụ broker acknowledgment hoặc durable database commit.
- Nếu recovery không thành công, recoverer phải ném exception để error handler không đánh dấu record thành công.
- Sau recovery thành công, offset nguồn được xử lý theo ack mode và commit policy tương ứng.
- Có observability để phân biệt đã recover, commit thất bại và xử lý DLT về sau.

## 3. Các mốc kết quả cần phân biệt

| Mốc | Tín hiệu quan sát | Có thể kết luận | Chưa thể kết luận |
|---|---|---|---|
| Listener ném exception | Exception từ `@KafkaListener` | Xử lý lần này thất bại | Record sẽ mất hoặc được DLT nhận |
| Hết retry | `BackOff` hết lượt | Đã đến bước recoverer | Recoverer đã hoàn tất |
| Recoverer return bình thường | Error handler coi recoverer đã xử lý | Recovery hoàn tất theo hợp đồng recoverer | Đích đã bền vững nếu recoverer không xác nhận I/O |
| DLT send future success | `RecordMetadata` từ broker | Producer nhận xác nhận gửi theo `acks` | Consumer DLT đã xử lý |
| Offset nguồn commit thành công | Committed offset của group | Consumer group đã lưu vị trí đọc tiếp theo | Business issue đã được sửa |
| DLT consumer xử lý thành công | Log/DB trạng thái nghiệp vụ | Bước xử lý DLT đã hoàn tất theo hợp đồng | Những side effect ngoài transaction chắc chắn exactly-once |

Một hệ thống vận hành tốt nên có metric hoặc log riêng cho ít nhất ba mốc: **recovery attempt**, **recovery success/failure**, **source offset advancement**. Nếu có DLT consumer, cần theo dõi thêm **DLT processing success/failure**.

## 4. Luồng DefaultErrorHandler đến recoverer

Trong luồng record listener thông thường, `DefaultErrorHandler` chịu trách nhiệm điều phối retry và recovery. Một cách mô tả tổng quát:

~~~mermaid
sequenceDiagram
    participant K as Kafka source topic
    participant C as Listener container
    participant L as Application listener
    participant E as DefaultErrorHandler
    participant R as Recoverer
    participant D as DLT broker

    K-->>C: Poll record offset 42
    C->>L: Process record
    L-->>C: Exception
    C->>E: Handle failed record
    E->>E: BackOff, retry until exhausted
    E->>R: Recover(record, exception)
    R->>D: Publish DLT record
    D-->>R: Ack hoặc send error
    alt DLT publish confirmed
        R-->>E: Return normally
        E-->>C: Record handled
        C->>K: Offset commit theo AckMode và policy
    else Recovery failed
        R-->>E: Throw exception
        E-->>C: Not recovered
        C->>C: Redelivery hoặc tiếp tục xử lý lỗi
    end
~~~

Chi tiết commit offset, seek/retain và transaction phụ thuộc phiên bản Spring Kafka, kiểu listener và cấu hình container. Sơ đồ nhằm nhấn mạnh ranh giới **recoverer hoàn tất** khác với **commit offset nguồn**.

Một ví dụ nghiệp vụ:

- Topic nguồn: `orders`.
- Group: `billing-service`.
- Record lỗi: partition 2, offset 42, event ID `evt-93`.
- Listener đã retry ba lần nhưng không xử lý được.
- Recoverer gửi record đến topic `orders.DLT`.
- Khi producer xác nhận gửi thành công và recoverer return bình thường, record có thể được coi là đã recover.
- Container tiếp tục xử lý offset 43 trở đi theo chính sách commit.
- DLT consumer hoặc operator xử lý `evt-93` sau đó.

Nếu việc publish DLT không được xác nhận, hệ thống phải giữ khả năng giao lại `orders-2@42` hoặc tiếp tục recovery theo chính sách, không tự động coi event đã được bàn giao an toàn.

## 5. Recoverer mặc định và custom recoverer

### 5.1. ConsumerRecordRecoverer

`ConsumerRecordRecoverer` là abstraction nhận record và exception để ứng dụng thực hiện một thao tác phục hồi:

~~~java
ConsumerRecordRecoverer recoverer = (record, exception) -> {
    log.error(
        "Record failed: topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset(),
        exception
    );
};
~~~

Một recoverer chỉ ghi log như ví dụ sẽ **return bình thường** nếu log thành công. Vì vậy error handler có thể coi record là recovered, dù chưa có bản sao bền vững ở nơi khác. Điều đó chỉ phù hợp nếu chính sách nghiệp vụ cho phép bỏ qua record sau khi đã ghi log.

Nếu phải lưu record để replay, recoverer cần ghi vào DLT, database, object storage hoặc durable queue và xác nhận kết quả trước khi trả về.

### 5.2. DeadLetterPublishingRecoverer

`DeadLetterPublishingRecoverer` là implementation chuyên dùng để publish record lỗi vào DLT bằng `KafkaTemplate`. Nó có thể bổ sung headers phục vụ điều tra lỗi gốc và metadata record nguồn.

Một destination resolver tường minh giúp tránh phụ thuộc quy ước đặt tên topic của môi trường:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(
        kafkaTemplate,
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        )
    );
~~~

Với resolver trên, cần tạo DLT topic có ít nhất số partition cần thiết để ánh xạ cùng partition index với topic nguồn. Đây là quy ước của **ví dụ**; ứng dụng có thể chọn topic/partition khác bằng resolver riêng.

## 6. Xác nhận kết quả gửi DLT

### 6.1. Vì sao chỉ gọi send là chưa đủ?

`KafkaTemplate.send()` là API bất đồng bộ. Lời gọi send có thể trả về một future khi record chưa được broker xác nhận. Kết quả thực tế đến sau, hoặc có thể lỗi do broker không sẵn sàng, authorization, serializer hay timeout.

Nếu recoverer đánh dấu hoàn tất ngay sau khi bắt đầu send, có một cửa sổ lỗi:

~~~text
Listener lỗi -> recoverer gọi send(DLT)
                    |
                    v
Recoverer return bình thường
                    |
                    v
Container tiến offset nguồn
                    |
                    +-- DLT send thất bại sau đó
                        => Có nguy cơ mất đường replay của record.
~~~

Vì vậy, recovery có yêu cầu độ bền phải đợi kết quả theo hợp đồng thích hợp hoặc sử dụng transaction phối hợp phù hợp.

### 6.2. DeadLetterPublishingRecoverer kiểm tra send result

`DeadLetterPublishingRecoverer` hỗ trợ cấu hình kiểm tra kết quả gửi để không coi publish DLT lỗi là recovery thành công:

~~~java
DeadLetterPublishingRecoverer recoverer =
    new DeadLetterPublishingRecoverer(
        kafkaTemplate,
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        )
    );

recoverer.setFailIfSendResultIsError(true);
recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));
~~~

Ý nghĩa:

- `setFailIfSendResultIsError(true)` yêu cầu recoverer phát sinh lỗi khi kết quả gửi DLT báo thất bại.
- `setWaitForSendResultTimeout(...)` giới hạn thời gian chờ kết quả gửi trong những phiên bản có API này.
- Khi recoverer ném exception, error handler không nên xem record đã recover thành công.

Chi tiết timeout và việc chờ future phụ thuộc Spring Kafka version và cấu hình producer. Thời hạn chờ không nên quá ngắn so với `delivery.timeout.ms`, network latency và trạng thái broker thông thường. Việc có timeout vẫn cần được hiểu cẩn thận: timeout không chứng minh record chưa được broker ghi.

### 6.3. Broker acknowledgment và cấu hình producer

Muốn xác nhận DLT publish có ý nghĩa về độ bền, cần hiểu Kafka producer `acks`:

| Cấu hình | Ý nghĩa success |
|---|---|
| `acks=0` | Producer không chờ broker xác nhận; không thích hợp khi cần bằng chứng DLT đã được ghi |
| `acks=1` | Leader đã xác nhận ghi theo giao thức; chưa đồng nghĩa replica khác đã theo kịp |
| `acks=all` | Broker xác nhận theo điều kiện replica đồng bộ (ISR), kết hợp `min.insync.replicas` và replication factor |

Ví dụ cấu hình producer dành cho đường phục hồi:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
~~~

Đây là cấu hình minh họa. Phải bảo đảm topic DLT có replication factor và `min.insync.replicas` phù hợp. `acks=all` không tự bảo đảm toàn bộ quy trình end-to-end exactly-once; nó chỉ nâng mức xác nhận ở phía producer/broker.

## 7. Ví dụ cấu hình DefaultErrorHandler có xác nhận recovery

Một cấu hình gắn `DeadLetterPublishingRecoverer` vào `DefaultErrorHandler`:

~~~java
@Configuration
public class OrderKafkaRecoveryConfiguration {

    @Bean
    public DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> recoveryKafkaTemplate
    ) {
        DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                recoveryKafkaTemplate,
                (record, exception) -> new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
            );

        recoverer.setFailIfSendResultIsError(true);
        recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));

        FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

        DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

        handler.setAckAfterHandle(true);
        handler.setResetStateOnRecoveryFailure(true);

        return handler;
    }

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
}
~~~

Điểm chính:

- `FixedBackOff(1_000L, 2L)` cho phép hai lần retry sau lần xử lý đầu tiên, mỗi lần cách một giây.
- `DeadLetterPublishingRecoverer` định tuyến record lỗi sang DLT.
- Kiểm tra send result giúp phát hiện publish DLT thất bại.
- `setAckAfterHandle(true)` cho phép container commit offset đối với lỗi đã được handler xử lý trong các chế độ phù hợp. Thuộc tính này không phải yêu cầu commit ngay tức thì trong mọi ack mode.
- `setResetStateOnRecoveryFailure(true)` reset trạng thái BackOff khi recoverer thất bại, cho phép record đi qua chu kỳ retry mới ở lần giao lại tiếp theo.
- Factory phải được listener thực sự sử dụng; khai báo handler bean riêng nhưng không gắn đúng factory sẽ không đổi cách xử lý lỗi.

Ví dụ listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    containerFactory = "orderKafkaListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    billingService.applyIdempotently(event);
}
~~~

Một record xử lý lỗi sẽ đi qua `DefaultErrorHandler` và recovery policy. Nếu DLT publisher bị lỗi, recoverer phát sinh exception và record chưa được coi là recover xong.

## 8. Xác nhận recovered khác với commit offset

### 8.1. Offset là tiến độ của consumer group

Kafka lưu committed offset theo group ID, topic và partition. Giá trị commit là **offset tiếp theo cần đọc**.

Nếu record `orders-2@42` đã được xử lý hoặc recover, tiến độ có thể là:

~~~text
Topic orders, partition 2

...  40  41  42  43  44 ...
            ^
            record 42 thất bại

Sau recovery và commit offset 43:
lần consumer đọc tiếp từ vị trí 43
~~~

Commit offset 43 chứng minh group đã lưu tiến độ bỏ qua record 42 ở lần tiêu thụ thông thường tiếp theo. Nếu DLT publish không thực sự bền vững trước commit, hệ thống có thể mất khả năng xử lý lại record 42 một cách tự động.

### 8.2. AckMode.RECORD

Với record listener và `AckMode.RECORD`, container thường commit offset sau khi listener hoàn tất thành công từng record. Khi record lỗi và error handler recover thành công, commit behavior phụ thuộc vào việc handler xử lý xong, `ackAfterHandle` và cơ chế container.

Không nên kết luận “recoverer đã return, chắc chắn offset commit thành công”. Commit offset có thể thất bại do rebalance, broker/coordinator không sẵn sàng hoặc lỗi network sau khi recovery hoàn tất.

### 8.3. AckMode.BATCH

Với `AckMode.BATCH`, container thường commit tiến độ sau khi xử lý các record thuộc một poll theo policy. Khi có record lỗi ở giữa một tập record, error handler có thể tách phần đã xử lý trước lỗi và phần cần retry/recovery.

Đừng dùng một offset duy nhất cho toàn batch. Mỗi topic-partition có committed offset riêng và không được tiến qua record chưa hoàn tất.

### 8.4. Manual acknowledgment

Nếu listener dùng `AckMode.MANUAL` hoặc `MANUAL_IMMEDIATE`, application có thể gọi `Acknowledgment.acknowledge()` sau khi công việc hoàn tất. Tuy nhiên, record đã rơi vào error handler không tự trở thành “acknowledged” chỉ vì listener đã ném exception.

Phải hiểu chính sách ack mode của container và cách error handler commit recovered record. Tránh tự gọi acknowledge trước khi recoverer bảo đảm lưu record lỗi bền vững.

## 9. commitRecovered và MANUAL_IMMEDIATE

`DefaultErrorHandler` có thuộc tính `commitRecovered` để yêu cầu commit offset của record đã recover trong tình huống áp dụng. Tài liệu Spring Kafka yêu cầu container dùng `AckMode.MANUAL_IMMEDIATE` cho chức năng này.

Ví dụ:

~~~java
DefaultErrorHandler handler =
    new DefaultErrorHandler(
        recoverer,
        new FixedBackOff(1_000L, 2L)
    );

handler.setCommitRecovered(true);
~~~

Cấu hình container tương ứng:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        manualRecoveryContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler errorHandler
        ) {
    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
        ContainerProperties.AckMode.MANUAL_IMMEDIATE
    );
    factory.setCommonErrorHandler(errorHandler);

    return factory;
}
~~~

Listener có thể acknowledge record bình thường sau khi xử lý thành công:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    containerFactory = "manualRecoveryContainerFactory"
)
public void onOrder(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    billingService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
~~~

Khi lỗi khiến listener ném exception, `DefaultErrorHandler` điều phối retry/recovery; nếu recoverer thành công và cấu hình `commitRecovered=true` phù hợp, handler có thể commit offset của record recover theo semantics của nó. Không gọi acknowledge trong nhánh listener lỗi trước khi error handler chạy.

Phân biệt hai thuộc tính:

| Thuộc tính | Vai trò |
|---|---|
| `ackAfterHandle` | Điều khiển việc container commit offset đối với lỗi đã được error handler xử lý theo cơ chế container |
| `commitRecovered` | Yêu cầu handler commit offset của record đã recover trong chế độ có hỗ trợ, đặc biệt MANUAL_IMMEDIATE |

Hai thuộc tính không thay thế nhau. Cần đối chiếu Javadoc của phiên bản Spring Kafka triển khai, nhất là với batch listener, transaction và commit async.

## 10. Dùng RetryListener để nhận tín hiệu recovered

Spring Kafka cung cấp `RetryListener` để quan sát tiến trình retry và recovery. Các callback thường dùng cho record:

- `failedDelivery(...)`: một lần delivery đến listener thất bại.
- `recovered(...)`: error handler xác nhận recoverer đã hoàn tất theo hợp đồng.
- `recoveryFailed(...)`: recoverer ném exception.

Ví dụ:

~~~java
public class RecoveryMetricsListener implements RetryListener {

    private final MeterRegistry meterRegistry;

    public RecoveryMetricsListener(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public void failedDelivery(
        ConsumerRecord<?, ?> record,
        Exception exception,
        int deliveryAttempt
    ) {
        meterRegistry.counter(
            "app.kafka.listener.delivery.failed",
            "topic", record.topic()
        ).increment();
    }

    @Override
    public void recovered(
        ConsumerRecord<?, ?> record,
        Exception exception
    ) {
        meterRegistry.counter(
            "app.kafka.record.recovered",
            "topic", record.topic()
        ).increment();
    }

    @Override
    public void recoveryFailed(
        ConsumerRecord<?, ?> record,
        Exception original,
        Exception failure
    ) {
        meterRegistry.counter(
            "app.kafka.record.recovery.failed",
            "topic", record.topic()
        ).increment();
    }
}
~~~

Đăng ký trên handler:

~~~java
handler.setRetryListeners(
    new RecoveryMetricsListener(meterRegistry)
);
~~~

Callback `recovered` là tín hiệu recovery ở tầng error handler. Nếu recoverer không kiểm tra kết quả gửi DLT, callback này vẫn không phải bằng chứng DLT đã được broker ghi. Vì vậy, hãy cấu hình recoverer để hợp đồng hoàn tất của nó có ý nghĩa về độ bền trước khi dựa vào callback.

Nếu ứng dụng quan sát callback nhưng muốn biết offset nguồn đã commit hay chưa, phải đối chiếu committed offset hoặc cơ chế commit callback/monitoring của consumer. `RetryListener.recovered` không thay thế tín hiệu commit offset.

## 11. Nếu recovery thất bại thì record đi đâu?

Khi recoverer ném exception, `DefaultErrorHandler` không coi record đã recover thành công. Với cấu hình thông thường, record sẽ được đưa trở lại đường xử lý lỗi ở lần delivery sau, theo cơ chế seek/fetch lại hoặc retain/resubmit.

Ví dụ:

~~~text
Listener thất bại
      |
      v
Hết BackOff
      |
      v
Recoverer publish DLT
      |
      +-- Success -> recovered -> commit theo policy
      |
      +-- Failure -> exception -> record chưa recovered
                                         |
                                         v
                                 Redelivery/recovery lại
~~~

Trong Spring Kafka, `resetStateOnRecoveryFailure` tác động đến BackOff tracker khi recoverer thất bại:

- `true` (hành vi mặc định ở các phiên bản hỗ trợ): reset BackOff, lần delivery tiếp theo có thể đi lại qua chu kỳ retry listener.
- `false`: giữ BackOff đã hết, lần delivery tiếp theo có thể tiến nhanh đến recoverer thay vì chạy lại toàn bộ chu kỳ retry.

Ví dụ:

~~~java
handler.setResetStateOnRecoveryFailure(false);
~~~

Chọn `false` khi lỗi không thể tự giải quyết bằng việc chạy lại listener, nhưng hệ thống DLT/recovery có thể hồi phục sau một thời gian. Chọn `true` khi muốn listener có thêm cơ hội hoàn tất nghiệp vụ ở chu kỳ sau.

Không chọn theo mục tiêu “bớt log lỗi”; hãy chọn theo chi phí retry, side effect và khả năng phục hồi. Nếu listener đã tạo side effect bên ngoài Kafka trước khi thất bại, chạy lại cần idempotency.

## 12. Timeout DLT và trạng thái không rõ ràng

Một timeout khi đợi DLT send result có thể xảy ra sau khi broker đã ghi record nhưng response bị mất hoặc đến quá muộn. Do đó, sau timeout có hai khả năng:

1. DLT record chưa được broker ghi.
2. DLT record đã được ghi nhưng producer/recoverer không nhận được xác nhận.

Nếu error handler thử recovery lại, DLT có thể chứa **duplicate**. Không nên coi duplicate DLT tự động là lỗi của Spring Kafka; đây là một tình huống phân tán cần được thiết kế phòng ngừa.

Giải pháp:

- Giữ **event ID** ổn định xuyên qua topic nguồn, retry topic và DLT.
- Giữ metadata gốc gồm source topic, partition, offset và consumer group nếu có.
- DLT consumer dùng unique constraint, inbox hoặc thao tác idempotent.
- Nếu cần replay thủ công, ghi nhận cả nguồn gốc và lịch sử attempt.
- Theo dõi DLT publish failure/timeout riêng với source listener failure.

Không dùng mỗi DLT offset làm khóa idempotency cho event nghiệp vụ. Record được publish lại vào DLT sẽ nhận offset mới dù nội dung và event ID có thể là cùng một lần xử lý thất bại.

## 13. Xác nhận nguồn gốc record ở DLT

Khi record được gửi vào DLT, người vận hành cần biết **nó đến từ đâu và vì sao thất bại**. `DeadLetterPublishingRecoverer` có thể bổ sung headers như:

- Original topic.
- Original partition.
- Original offset.
- Original consumer group, khi có thông tin tương ứng.
- Exception class và message.
- Stack trace hoặc thông tin lỗi theo cấu hình.
- Metadata retry/delivery attempt tùy cơ chế retry.

Tên hằng số tương ứng trong Spring Kafka thường nằm ở `KafkaHeaders`, như nhóm `DLT_ORIGINAL_*` và `DLT_EXCEPTION_*`. Các headers sẵn có có thể thay đổi theo phiên bản; cần xác nhận đúng dependency đang chạy.

Ví dụ một schema lưu trữ nghiệp vụ cho DLT:

~~~json
{
  "eventId": "evt-93",
  "sourceTopic": "orders",
  "sourcePartition": 2,
  "sourceOffset": 42,
  "recoveryDestination": "orders.DLT",
  "status": "PENDING_REVIEW",
  "reason": "DatabaseTimeoutException"
}
~~~

Đây chỉ là ví dụ về metadata ngoài payload; không phải định dạng bắt buộc do Spring Kafka tạo ra.

Khi log, không ghi toàn bộ payload hoặc stack trace chứa dữ liệu nhạy cảm một cách không kiểm soát. Event ID, topic/partition/offset và nhóm exception thường đủ để liên kết với hệ thống truy vết có quyền truy cập thích hợp.

## 14. Xác nhận record đã recover bằng log và metric

Một log recovery hữu ích nên ghi **kết quả** thay vì chỉ ghi “đang gửi DLT”.

Ví dụ:

~~~text
RECOVERY_ATTEMPT eventId=evt-93 source=orders-2@42 destination=orders.DLT
RECOVERY_CONFIRMED eventId=evt-93 destination=orders.DLT partition=2 offset=105
SOURCE_OFFSET_COMMITTED group=billing-service source=orders-2 nextOffset=43
~~~

Trong trường hợp lỗi:

~~~text
RECOVERY_FAILED eventId=evt-93 source=orders-2@42
failure=TimeoutException result=UNKNOWN
SOURCE_OFFSET_NOT_CONFIRMED group=billing-service source=orders-2
~~~

Không ghi `RECOVERY_CONFIRMED` trước khi cơ chế xác nhận của recoverer báo thành công. Không ghi `SOURCE_OFFSET_COMMITTED` chỉ vì handler đã return; cần lấy tín hiệu commit thực tế hoặc ghi rõ rằng việc commit đang chờ.

Bảng metric vận hành:

| Metric / chỉ số | Vai trò |
|---|---|
| Listener failed deliveries | Bao nhiêu lần listener xử lý lỗi |
| Retry attempts | Mức độ retry trước recovery |
| Recovery attempts | Số lần recoverer được gọi |
| Recovered count | Số lần recoverer xác nhận hoàn tất |
| Recovery failure count | Số lần recoverer thất bại |
| DLT publish latency/error | Độ trễ và độ tin cậy của producer gửi DLT |
| Consumer committed offset | Tiến độ bền vững của group nguồn |
| Source consumer lag | Đánh giá việc lỗi record làm chậm group |
| DLT consumer lag | Số record lỗi đang chờ xử lý |
| DLT oldest age | Độ tuổi lớn nhất của record chưa giải quyết |
| DLT replay success/failure | Kết quả khôi phục nghiệp vụ về sau |

Metric labels nên có cardinality thấp: topic, outcome và exception category. Không gắn event ID, order ID hay offset vào metric labels vì số lượng series có thể tăng không giới hạn. Các định danh chi tiết nên nằm trong log hoặc trace.

## 15. Recovery trong non-blocking retry

Với `@RetryableTopic`, record lỗi được chuyển qua các retry topic rồi có thể đi đến DLT khi hết lượt. Đường đi không giống `DefaultErrorHandler` xử lý blocking retry tại topic nguồn.

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 2_000L)
)
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrder(OrderCreated event) {
    billingService.applyIdempotently(event);
}

@DltHandler
public void onDlt(OrderCreated event) {
    dltReviewService.recordForReview(event);
}
~~~

Ví dụ biểu thị ý tưởng; cách định tuyến và cấu hình DLT/retry topic phụ thuộc phiên bản Spring Kafka. `@RetryableTopic` dành cho record listener, không được Spring Kafka hỗ trợ trực tiếp với batch listener.

Có ít nhất hai mốc cần phân biệt:

1. **Chuyển record vào DLT**: retry infrastructure đã publish record sau khi hết lượt hoặc theo chính sách.
2. **Xử lý record từ DLT**: `@DltHandler` hoặc một DLT consumer đã thực hiện công việc sau đó.

Nếu `@DltHandler` chỉ log rồi return, hệ thống không nên tự gọi trạng thái nghiệp vụ là “resolved”. Nếu cần xử lý lại có kiểm soát, phải lưu state và tạo workflow replay/approval phù hợp.

Trong non-blocking retry, cũng cần theo dõi việc publish giữa các topic. Timeout có thể tạo duplicate; retry topic/DTL retention phải đủ để vận hành và điều tra.

## 16. Recovery bằng database hoặc hệ thống ngoài Kafka

Không phải ứng dụng nào cũng dùng DLT. Một custom recoverer có thể lưu record lỗi vào bảng để người vận hành xử lý lại.

Ví dụ khái quát:

~~~java
public class DatabaseRecoverer implements ConsumerRecordRecoverer {

    private final FailedEventRepository failedEventRepository;

    public DatabaseRecoverer(
        FailedEventRepository failedEventRepository
    ) {
        this.failedEventRepository = failedEventRepository;
    }

    @Override
    public void accept(
        ConsumerRecord<?, ?> record,
        Exception exception
    ) {
        failedEventRepository.saveAndFlush(
            FailedEvent.from(record, exception)
        );
    }
}
~~~

Trong ví dụ thực tế, method `saveAndFlush` chưa tự đảm bảo transaction database đã commit bền vững. Nếu method tham gia một transaction bên ngoài còn đang mở, recoverer có thể return trước khi transaction commit và rollback sau đó.

Vì vậy, cần xác định ranh giới transaction và điểm recovery có thể coi là durable:

- Ghi record lỗi trong transaction độc lập có commit thành công trước khi recoverer return, hoặc
- Dùng một cơ chế transaction/outbox phối hợp rõ ràng, hoặc
- Chấp nhận chính sách at-least-once và xử lý duplicate an toàn nếu kết quả ghi và offset commit không nguyên tử.

Nếu recoverer không thể ghi bền vững, nó phải báo lỗi để offset nguồn không tiến qua record chưa được xử lý theo cách mất dữ liệu.

## 17. Kafka transaction và recovery

Trong luồng Kafka-to-Kafka, Spring Kafka có thể kết hợp transaction của producer với consumer offset để output record và offset nguồn cùng tham gia một Kafka transaction. Đây là một con đường khác để liên kết việc publish output (bao gồm DLT trong một số thiết kế) với offset advancement.

Với listener container transactional, cơ chế lỗi thường phối hợp với `DefaultAfterRollbackProcessor` hoặc transaction-aware recovery, không đơn giản là sao chép cấu hình `DefaultErrorHandler` non-transactional.

Các điểm cần hiểu:

- Chỉ những Kafka record/offset tham gia cùng Kafka transaction mới được commit/abort cùng nhau.
- Consumer downstream dùng `isolation.level=read_committed` để không đọc record từ transaction đã abort.
- Kafka transaction không tự bao gồm database, email hoặc REST request.
- DLT publisher và offset commit phải tham gia đúng transaction nếu thiết kế yêu cầu atomicity Kafka-to-Kafka.
- API và ràng buộc cấu hình transactional recovery khác theo phiên bản; cần xem tài liệu Spring Kafka đúng phiên bản trước khi áp dụng.

Đừng suy ra rằng bật `spring.kafka.producer.transaction-id-prefix` là đủ để mọi recoverer tự dùng một transaction phù hợp. Kiểm tra producer factory, container transaction manager, recovery processor và kết quả commit/abort thực tế.

## 18. Recovery thành công nhưng offset commit thất bại

Đây là tình huống rất quan trọng:

~~~text
Record orders-2@42 bị lỗi
    |
    v
Publish orders.DLT -> broker xác nhận thành công
    |
    v
Recoverer return bình thường
    |
    v
Commit offset 43 -> FAILED (rebalance/network)
    |
    v
Consumer restart, đọc lại orders-2@42
    |
    v
Có thể publish orders.DLT lần nữa
~~~

Mặc dù recovery lần đầu đã thành công, tiến độ nguồn chưa được lưu. Redelivery sau đó là hành vi có thể xảy ra với at-least-once semantics.

Giải pháp gồm:

- DLT consumer idempotent dựa trên event ID hoặc định danh nguồn.
- Lưu recovery record theo unique key phù hợp.
- Theo dõi lỗi commit offset riêng với lỗi recoverer.
- Nếu hệ thống yêu cầu atomicity Kafka-to-Kafka, đánh giá transactional recovery.
- Không xóa DLT record bản đầu chỉ vì một bản trùng xuất hiện, trước khi xác minh xử lý nghiệp vụ.

Xác nhận recovery và xác nhận source commit phải là hai tín hiệu khác nhau trong dashboard và báo cáo.

## 19. Recovery thất bại nhưng DLT đã nhận record

Tình huống ngược lại cũng có thể xảy ra:

~~~text
Recoverer publish DLT
    |
    v
Broker ghi record
    |
    X  response bị mất hoặc timeout
    |
    v
Recoverer báo lỗi / trạng thái không rõ
    |
    v
Retry recovery
    |
    v
DLT có thể nhận record trùng
~~~

Không được khẳng định record đã mất chỉ vì future timeout. Tại thời điểm lỗi, trạng thái gửi có thể **không rõ ràng**.

Khi điều tra, có thể tìm theo:

- Event ID.
- Original topic/partition/offset.
- Correlation ID.
- Recovery destination.
- Khoảng thời gian gửi dự kiến.

Nếu DLT đã có record trước khi retry, cần xác nhận các bản trùng và xử lý idempotent. Nếu DLT chưa có, retry giúp bổ sung bản ghi phục hồi. Cả hai đường đi phải không tạo side effect sai.

## 20. Batch listener và recovered record

Khi dùng batch listener, lỗi có thể nằm ở một index cụ thể hoặc ở cả batch. Spring Kafka hỗ trợ `BatchListenerFailedException` để chỉ ra phần tử lỗi và `DefaultErrorHandler`/batch retry tương ứng.

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void onOrders(
    List<ConsumerRecord<String, OrderCreated>> records
) {
    for (int i = 0; i < records.size(); i++) {
        try {
            billingService.applyIdempotently(records.get(i).value());
        } catch (Exception ex) {
            throw new BatchListenerFailedException(
                "Failed record in batch",
                ex,
                i
            );
        }
    }
}
~~~

Khi recover một record trong batch, cần biết:

- Phần tử nào đã xử lý xong.
- Phần tử nào lỗi và đã được recover.
- Các phần tử nào chưa được xử lý.
- Offset tiến độ hợp lệ của từng topic-partition.
- Batch có side effect nguyên tử hay đã ghi từng phần.

Nếu không biết record lỗi, fallback batch recovery có thể phải retry cả batch; bản ghi đã thực hiện side effect có thể được giao lại. Idempotency là yêu cầu quan trọng.

Non-blocking retry qua `@RetryableTopic` không hỗ trợ batch listener. Không dùng annotation đó như cách tự động xác nhận recovered cho một phần tử của batch.

## 21. Những sai lầm thường gặp

**Cho rằng recoverer được gọi là thành công:** recoverer có thể ném exception hoặc bắt đầu một I/O bất đồng bộ thất bại sau đó.

**Chỉ log record lỗi rồi coi là recover an toàn:** nếu nghiệp vụ cần replay, log không thay thế DLT hoặc durable failure store.

**Không kiểm tra DLT send result:** offset nguồn có thể tiến trước khi biết DLT publish thất bại.

**Coi callback `recovered` là offset commit success:** callback báo recoverer hoàn tất, không chứng minh group coordinator đã lưu offset.

**Acknowledge trước khi recovery bền vững:** nếu process crash hoặc DLT publish lỗi, record có thể bị bỏ qua.

**Không xử lý timeout không rõ trạng thái:** có thể tạo duplicate khi recovery được thử lại.

**Không phân biệt DLT enqueue và DLT processing:** record vào DLT chưa có nghĩa đã sửa lỗi nghiệp vụ.

**Quên yêu cầu MANUAL_IMMEDIATE của commitRecovered:** handler có thể không commit recovered record như mong muốn nếu cấu hình ack mode không phù hợp.

**Không theo dõi recoveryFailed:** dashboard chỉ đếm listener failure sẽ không phát hiện DLT publisher đang hỏng.

**Ghi metric theo event ID:** cardinality rất lớn, tăng chi phí và có thể làm hệ thống metric không ổn định.

**Không bảo đảm DLT có đủ partition:** nếu resolver chọn cùng partition index nguồn, DLT phải có partition tương ứng.

**Tăng retry vô hạn khi DLT luôn lỗi:** poison record có thể giữ partition, consumer lag tăng, không có tiến triển. Cần sửa nguyên nhân gốc, phân loại exception và đặt cảnh báo.

## 22. Quy trình điều tra một record chưa chắc đã recovered

Khi log ghi “Recovery started” nhưng record không xuất hiện trong DLT hoặc source lag tăng, lần theo từng mốc:

1. Xác nhận đúng group ID, source topic, partition, offset và event ID.
2. Kiểm tra listener exception gốc và số lần retry.
3. Xác định error handler/recoverer thực sự gắn với listener container.
4. Xác nhận recoverer đã được gọi; ghi nhận exception nếu recoverer thất bại.
5. Nếu dùng DLT publisher, kiểm tra destination topic/partition, ACL, serializer và producer configuration.
6. Xem future/send result hoặc kết quả xác nhận mà recoverer đã đợi.
7. Nếu timeout, tìm record trong DLT theo metadata nguồn/event ID trước khi kết luận chưa ghi.
8. Xem callback `recovered` hay `recoveryFailed` có được gọi hay không.
9. Kiểm tra committed offset nguồn; phân biệt recovery success với commit failure.
10. Đối chiếu DLT consumer lag và trạng thái xử lý DLT.
11. Kiểm tra duplicate và idempotency nếu có retry recovery.
12. Sau khi sửa lỗi, xác nhận luồng recovery, tiến offset và downstream DLT hoạt động đúng.

Ví dụ kết quả điều tra:

~~~text
Source record: orders-2@42
Listener result: exhausted after configured retries
Recovery attempt: orders.DLT
DLT producer result: success at orders.DLT-2@105
Recoverer result: success
Source group committed offset: 43
DLT processing: pending manual review
~~~

Đây là trường hợp record đã được recover **vào DLT**, offset nguồn đã được ghi nhận, nhưng lỗi nghiệp vụ vẫn chờ xử lý.

## 23. Kịch bản kiểm thử cơ chế xác nhận recovery

Để chứng minh thiết kế hoạt động đúng, có thể dùng một cụm Kafka test riêng, topic nguồn và DLT đã provision, cùng một consumer group thử nghiệm.

### 23.1. Recovery thành công

1. Gửi một record với event ID xác định.
2. Cho listener luôn ném exception retryable.
3. Chờ hết số lần retry đã cấu hình.
4. Xác nhận recoverer publish record sang DLT.
5. Xác nhận producer nhận kết quả gửi thành công.
6. Xác nhận `RetryListener.recovered` được gọi.
7. Xác nhận committed offset nguồn tiến qua record lỗi theo ack mode.
8. Xác nhận DLT record giữ metadata nguồn cần thiết.

### 23.2. Recovery publisher thất bại

1. Cấu hình DLT topic không thể ghi trên môi trường test hoặc dùng producer lỗi có kiểm soát.
2. Bật `setFailIfSendResultIsError(true)`.
3. Cho listener thất bại đến giai đoạn recovery.
4. Xác nhận recoverer báo lỗi.
5. Xác nhận callback `recoveryFailed` được gọi.
6. Xác nhận record nguồn chưa bị bỏ qua do commit không phù hợp.
7. Khôi phục producer/DLT, cho hệ thống thử recovery lại và quan sát kết quả.

### 23.3. Publish DLT thành công nhưng commit source thất bại

1. Cho recoverer publish DLT thành công.
2. Tạo lỗi commit offset nguồn theo cách có kiểm soát.
3. Cho consumer khởi động lại với cùng group ID.
4. Xác nhận record nguồn có thể được giao lại.
5. Xác nhận idempotency xử lý record DLT nếu nó được publish lần thứ hai.
6. Xác nhận metric/log phân biệt recovered với offset commit failed.

### 23.4. Timeout và duplicate

1. Tạo tình huống producer không nhận xác nhận trước timeout nhưng broker vẫn có thể đã ghi.
2. Cho recovery retry.
3. Tìm các DLT record cùng event ID và original topic/partition/offset.
4. Xác nhận DLT consumer/inbox không lặp side effect.
5. Đối chiếu số recovery attempts với số record DLT thật sự tồn tại.

Không chỉ kiểm tra số lần listener được gọi. Kiểm thử recovery phải quan sát được record trong DLT, trạng thái commit nguồn, exception của recoverer và cơ chế chống duplicate.

## 24. Nguyên tắc vận hành trong production

- Định nghĩa rõ “recovered” theo **đích phục hồi**, không chỉ theo việc recoverer đã được gọi.
- Với DLT, cấu hình recoverer kiểm tra kết quả gửi và dùng producer `acks` phù hợp với yêu cầu độ bền.
- Bảo đảm DLT topic, partition, replication, ACL và serializer đã được provision.
- Tách metric/log recovery attempt, recovery success, recovery failure và source offset commit.
- Không coi timeout là bằng chứng record chưa được ghi; thiết kế DLT consumer idempotent.
- Dùng `RetryListener` để quan sát recovered và recoveryFailed.
- Hiểu `ackAfterHandle`, `commitRecovered` và acknowledgment mode trước khi thay đổi cách commit.
- Với `commitRecovered=true`, kiểm tra yêu cầu `MANUAL_IMMEDIATE` của phiên bản Spring Kafka đang dùng.
- Giữ event ID và metadata gốc để tra cứu, replay và chống duplicate.
- Phân biệt DLT publish thành công với việc một DLT handler đã giải quyết được lỗi nghiệp vụ.
- Nếu dùng Kafka transaction, bảo đảm recovery record và source offset thực sự tham gia transaction theo thiết kế.
- Với batch listener, quản lý partial success, offset từng partition và recovery theo cơ chế batch được hỗ trợ.
- Kiểm thử failure tại ranh giới giữa listener, recoverer, Kafka producer và source offset commit.

**Xác nhận record đã được recover** nghĩa là có bằng chứng hành động phục hồi đã hoàn tất theo hợp đồng đáng tin cậy, đồng thời hiểu rõ tiến độ offset nguồn đã được lưu hay chưa. Recovery vào DLT có thể thành công trong khi lỗi nghiệp vụ vẫn chưa được giải quyết; offset commit cũng có thể thất bại dù DLT đã nhận record. Khi tách bạch các mốc này và thiết kế idempotency cho những trường hợp kết quả không rõ ràng, hệ thống Spring Kafka sẽ tránh được việc bỏ sót event và có đủ dữ liệu để phục hồi một cách có kiểm soát.
