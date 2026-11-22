# Commit thủ công theo use case

Consumer đọc record từ Kafka và cần ghi nhận vị trí có thể tiếp tục đọc sau khi tiến trình restart. Vị trí này được lưu dưới dạng committed offset theo từng consumer group và partition. Với commit thủ công, ứng dụng quyết định thời điểm xác nhận tiến độ thay vì để Kafka consumer tự commit theo lịch.

Commit thủ công hữu ích khi ranh giới xử lý cần được kiểm soát rõ, chẳng hạn chỉ xác nhận sau khi ghi database, sau khi xử lý xong một batch hoặc sau khi hoàn tất một tác vụ bất đồng bộ. Tuy nhiên, commit quá sớm có thể làm mất xử lý; commit quá muộn có thể khiến record được giao lại. Vì vậy, lựa chọn cách commit phải xuất phát từ yêu cầu nghiệp vụ và khả năng chịu duplicate của handler.

Trong Spring Kafka, phần lớn ứng dụng nên dùng acknowledgement do listener container quản lý. Với Kafka Consumer API thuần, ứng dụng có thể gọi commitSync() hoặc commitAsync() trực tiếp. Hai cách tiếp cận có liên quan nhưng không nên trộn lẫn trong cùng một luồng xử lý mà không xác định rõ ai sở hữu offset.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích committed offset là vị trí đọc tiếp theo của một consumer group trên một partition.
- Phân biệt auto commit, container-managed acknowledgement và manual offset commit.
- Chọn commitSync() hoặc commitAsync() theo yêu cầu độ trễ và độ chắc chắn.
- Commit offset sau khi xử lý thành công bằng Kafka Consumer API.
- Sử dụng Acknowledgment và AckMode.MANUAL hoặc MANUAL_IMMEDIATE trong Spring Kafka.
- Xử lý partial batch, xử lý song song và các tình huống record được giao lại.
- Phối hợp commit với database, retry, dead-letter và Kafka transaction.
- Kiểm thử các cửa sổ lỗi giữa xử lý nghiệp vụ và commit offset.

## 1. Offset được commit là offset nào?

Kafka gán mỗi record một offset trong partition. Khi consumer commit tiến độ, nó lưu **offset của record tiếp theo cần đọc**, không phải offset của record cuối cùng đã xử lý.

Ví dụ consumer xử lý thành công record offset 40:

~~~text
Partition orders-0

offset 40  -> OrderCreated  (đã xử lý thành công)
offset 41  -> PaymentPaid   (record tiếp theo)
offset 42  -> OrderShipped

Committed offset = 41
~~~

Khi consumer khởi động lại và group có committed offset hợp lệ, consumer tiếp tục từ offset 41.

Offset được lưu theo cặp consumer group và topic-partition trong internal topic __consumer_offsets. Vì mỗi group có tiến độ riêng, group billing có thể đang ở offset 41 trong khi group analytics đã ở offset 90 trên cùng partition.

Một số điểm cần nhớ:

- Commit offset 41 nghĩa là consumer xác nhận đã xử lý đến trước vị trí 41.
- Commit không xóa record khỏi topic.
- Commit không xác nhận side effect trong database hoặc HTTP API đã được commit cùng Kafka.
- Consumer có thể đọc lại record nếu xử lý xong nhưng chưa commit trước khi tiến trình lỗi.
- Nếu commit trước khi xử lý xong, record có thể bị bỏ qua sau restart.

Đây là lý do thời điểm commit ảnh hưởng trực tiếp đến ngữ nghĩa giao nhận.

## 2. Ba cách quản lý commit

Có ba cách thường gặp:

| Cách | Ai quyết định thời điểm commit? | Cơ chế |
|---|---|---|
| Auto commit | Kafka consumer theo lịch cấu hình | enable.auto.commit và auto.commit.interval.ms |
| Container-managed | Spring Kafka listener container | AckMode.RECORD, BATCH, TIME, COUNT... |
| Manual commit | Mã ứng dụng hoặc listener chủ động xác nhận | commitSync(), commitAsync(), Acknowledgment |

Với Spring Kafka, listener container thường quản lý commit và mặc định tắt Kafka auto commit nếu ứng dụng không chủ động bật lại. Cách này giúp container gắn commit với kết quả listener và error handler.

Manual commit không phải lúc nào cũng tốt hơn. Nếu listener chỉ xử lý từng record đồng bộ, AckMode.RECORD hoặc BATCH thường đủ rõ ràng. Chỉ chọn manual khi ứng dụng có lý do cần quyết định chính xác lúc xác nhận.

## 3. Khi nào nên commit thủ công?

Một số use case phổ biến:

| Use case | Cách thường phù hợp | Lý do |
|---|---|---|
| Xử lý từng record đồng bộ | AckMode.RECORD hoặc container-managed | Container commit sau khi listener xử lý thành công |
| Ghi database rồi mới xác nhận | MANUAL hoặc MANUAL_IMMEDIATE | Chỉ acknowledge sau khi transaction database hoàn tất |
| Xử lý batch và commit sau toàn batch | BATCH hoặc MANUAL | Xác nhận sau khi mọi record cần thiết trong batch đã xử lý |
| Consumer API thuần cần commit vị trí cụ thể | commitSync(offsets) | Kiểm soát chính xác offset của từng partition |
| Throughput cao, chấp nhận replay khi commit thất bại | commitAsync() | Không chặn consumer thread chờ response commit |
| Consume-transform-produce trong Kafka transaction | Transaction của Spring Kafka | Commit output Kafka và offset đầu vào trong cùng transaction |
| Replay/backfill độc lập | Group ID riêng và commit tiến độ của job | Không làm thay đổi offset production |

Câu hỏi cần trả lời trước khi chọn cách commit là: nếu tiến trình lỗi ngay sau bước xử lý nhưng trước commit, điều gì sẽ xảy ra? Nếu record được giao lại, handler có tạo thêm side effect hay không?

## 4. Manual commit với Kafka Consumer API

Khi tự viết vòng lặp Kafka Consumer, tắt auto commit và chỉ commit sau khi xử lý xong record đã nhận.

Ví dụ xử lý toàn bộ batch rồi commit:

~~~java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-worker");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        OrderEventDeserializer.class);
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

KafkaConsumer<String, OrderEvent> consumer =
        new KafkaConsumer<>(props);

try {
    consumer.subscribe(List.of("orders"));

    while (running) {
        ConsumerRecords<String, OrderEvent> records =
                consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, OrderEvent> record : records) {
            orderService.processIdempotently(record.value());
        }

        // Chỉ commit khi toàn bộ record trong batch đã xử lý thành công.
        consumer.commitSync();
    }
} finally {
    consumer.close();
}
~~~

Trong ví dụ, commitSync() được gọi sau vòng for. Nếu bất kỳ lần xử lý nào ném exception và luồng thoát trước commit, batch chưa được xác nhận và có thể được giao lại.

Điều này tạo ngữ nghĩa at-least-once: ưu tiên không bỏ qua record, nhưng chấp nhận khả năng xử lý lặp. Hàm processIdempotently cần bảo vệ side effect khỏi duplicate.

### Cảnh báo về vị trí consumer

Kafka Consumer có thể đã cập nhật position đến sau các record được trả về từ poll(), trước khi ứng dụng xử lý xong từng record. Vì vậy, không gọi commitSync() sau khi chỉ xử lý một phần batch nếu dùng overload không tham số: consumer có thể commit position vượt qua record chưa xử lý.

Nếu xử lý cả batch theo thứ tự và chỉ commit khi mọi record thành công, commitSync() không tham số là cách đơn giản. Nếu cần commit một phần, hãy tự xây dựng offset map chỉ chứa vị trí tiếp theo của các record đã xử lý liên tục trên từng partition.

## 5. Commit offset cụ thể cho từng partition

Kafka cho phép truyền map TopicPartition sang OffsetAndMetadata để commit vị trí mong muốn.

Ví dụ xử lý record tuần tự và ghi nhận offset tiếp theo đã hoàn tất:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();

for (ConsumerRecord<String, OrderEvent> record : records) {
    orderService.processIdempotently(record.value());

    TopicPartition partition =
            new TopicPartition(record.topic(), record.partition());

    // Commit vị trí tiếp theo, không phải offset của record hiện tại.
    offsets.put(
        partition,
        new OffsetAndMetadata(record.offset() + 1)
    );
}

if (!offsets.isEmpty()) {
    consumer.commitSync(offsets);
}
~~~

Ví dụ này giả định ứng dụng xử lý tuần tự các record trong batch và dừng xử lý khi có exception. Nếu partition có offset 10, 11, 12 và record 11 chưa xử lý xong, không được commit 13 chỉ vì record 12 đã hoàn tất trước. Commit phải đại diện cho **tiền tố liên tục đã xử lý thành công** của partition.

Khi một batch có nhiều partition, có thể commit tiến độ độc lập cho từng partition. Nếu xử lý lỗi ở partition A nhưng partition B đã hoàn tất các record của nó, ứng dụng có thể commit partition B mà không tiến offset partition A.

Không nên tự tính offset bằng cách cộng số record đã nhận nếu log có khoảng trống offset. Dùng offset thực tế của record và commit offset tiếp theo của record cuối cùng trong đoạn liên tục đã hoàn tất.

## 6. commitSync(): chờ broker xác nhận commit

commitSync() gửi offset lên coordinator và chờ kết quả trước khi tiếp tục. Đây là lựa chọn dễ hiểu khi cần biết commit đã được broker xác nhận trước khi thực hiện bước tiếp theo.

Ví dụ:

~~~java
try {
    processBatch(records);
    consumer.commitSync();
} catch (RuntimeException ex) {
    // Không commit batch nếu xử lý chưa hoàn tất.
    handleProcessingFailure(ex);
    throw ex; // Không poll batch tiếp theo trước khi batch lỗi được xử lý/recover.
}
~~~

Ưu điểm:

- Luồng xử lý biết commit thành công hay thất bại.
- Dễ tổ chức thứ tự process rồi commit.
- Phù hợp với consumer cần ranh giới xác nhận rõ hoặc commit trước shutdown.

Đánh đổi:

- Consumer thread bị chặn trong lúc chờ coordinator.
- Commit thường xuyên có thể làm giảm throughput.
- Commit có thể thất bại nếu consumer đã mất quyền sở hữu partition, group đang rebalance hoặc coordinator không sẵn sàng.

Với consumer group, hãy xử lý các exception phù hợp như CommitFailedException và tình huống rebalance. Không coi việc gọi commitSync() là luôn thành công; cần quyết định retry, dừng xử lý hay để record được giao lại.

### Khi nào nên dùng commitSync()?

- Batch nhỏ hoặc vừa, cần xác nhận commit trước khi poll tiếp.
- Tác vụ migration/backfill cần ghi nhận tiến độ rõ.
- Consumer cần commit offset cụ thể sau khi hoàn thành side effect.
- Giai đoạn shutdown cần hoàn tất commit cuối cùng sau khi dừng nhận record mới.

Nếu commitSync() lỗi sau khi side effect đã thành công, record có thể được giao lại. Idempotency vẫn cần thiết.

## 7. commitAsync(): gửi commit không chặn

commitAsync() gửi yêu cầu commit và trả quyền điều khiển ngay cho ứng dụng. Kết quả được nhận qua callback.

Ví dụ:

~~~java
consumer.commitAsync((offsets, exception) -> {
    if (exception != null) {
        log.warn("Offset commit failed: {}", offsets, exception);
        metrics.incrementCommitFailure();
        return;
    }

    log.debug("Committed offsets: {}", offsets);
});
~~~

Ưu điểm:

- Không chặn consumer thread chờ response.
- Có thể giảm overhead khi commit thường xuyên.
- Phù hợp với luồng có throughput cao và chấp nhận việc record có thể được replay nếu commit thất bại.

Đánh đổi:

- Ứng dụng không nhận kết quả ngay tại dòng gọi.
- Nếu commit thất bại, offset có thể chưa được lưu.
- Khi tiến trình lỗi trước callback hoặc trước khi broker xác nhận, record đã xử lý có thể được giao lại.
- Việc retry một commit cũ sau khi đã gửi commit mới có thể làm offset bị lùi nếu không kiểm soát thứ tự.

### Không retry mù một commitAsync cũ

Giả sử ứng dụng gửi commit offset 100, sau đó gửi commit offset 150. Callback của commit 100 báo lỗi trong khi request commit 150 đã được gửi. Nếu callback tự gửi lại offset 100, request retry có thể được xử lý sau commit 150 và làm group lùi về vị trí cũ, khiến nhiều record bị đọc lại.

Kafka client giữ thứ tự callback theo thứ tự request commit được gửi, nhưng ứng dụng vẫn không nên retry một offset cũ khi đã có commit mới hơn. Nếu cần bảo đảm commit cuối cùng, có thể dừng gửi commit bất đồng bộ mới và thực hiện commitSync() với vị trí mới nhất trong quy trình shutdown hoặc phục hồi.

### Khi nào nên dùng commitAsync()?

- Consumer xử lý số lượng record lớn và muốn giảm thời gian chờ commit.
- Replay một số record sau lỗi là chấp nhận được.
- Ứng dụng có cơ chế giám sát callback và kiểm soát thứ tự commit.
- Có quy trình commitSync() cuối cùng khi đóng consumer nếu cần bảo đảm tiến độ đã được xác nhận.

Không dùng commitAsync() chỉ để tránh xử lý exception. Callback phải ghi nhận lỗi và hệ thống cần chấp nhận khả năng replay khi commit không thành công.

## 8. Kết hợp commitSync và commitAsync

Một mẫu phổ biến là dùng commitAsync() trong luồng poll thông thường để giảm thời gian chờ, rồi dùng commitSync() khi đóng consumer để xác nhận vị trí mới nhất.

Luồng minh họa:

~~~text
Poll batch
   |
Process records
   |
commitAsync()  ----> tiếp tục vòng poll
   |
   | nhiều batch tiếp theo
   v
Shutdown requested
   |
Dừng nhận record mới
   |
Hoàn tất hoặc xử lý công việc đang chạy
   |
commitSync() với vị trí mới nhất
   |
close consumer
~~~

Mẫu này cần được triển khai cẩn thận:

- Chỉ commit offset đã xử lý liên tục.
- Không để commitAsync cũ ghi đè tiến độ mới hơn.
- Không đóng consumer trước khi hoàn tất callback/commit cần thiết.
- Khi rebalance, chỉ commit partition mà consumer còn có quyền sở hữu theo group protocol.
- Nếu xử lý song song, phải theo dõi record nào đã hoàn tất trước khi tạo offset map.

Đừng dùng commitSync() và commitAsync() tùy tiện xen kẽ ở nhiều thread. KafkaConsumer không thread-safe; mọi thao tác consumer phải được điều phối theo consumer thread.

## 9. Manual acknowledgement trong Spring Kafka

Với @KafkaListener, Spring Kafka cung cấp Acknowledgment để listener chủ động xác nhận sau khi xử lý.

Ví dụ listener dùng manual acknowledgement:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "order-service",
    containerFactory = "manualAckListenerContainerFactory"
)
public void handle(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(event);

    // Xác nhận sau khi nghiệp vụ hoàn tất.
    acknowledgment.acknowledge();
}
~~~

Factory phải dùng acknowledgement mode phù hợp:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        manualAckListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL
    );

    return factory;
}
~~~

Khi dùng MANUAL, listener gọi acknowledge() để đưa record vào hàng đợi xác nhận của container. Container commit offset theo ranh giới batch/poll sau khi các record được trả về trong poll đã được xử lý và xác nhận theo quy tắc của mode này.

Với MANUAL_IMMEDIATE, container cố gắng commit ngay khi acknowledge() được gọi trên consumer thread. Nếu acknowledge được gọi từ thread khác, việc xác nhận được xếp hàng để container xử lý theo vòng đời consumer. Vì vậy, nếu cần commit ngay, hãy gọi acknowledge trên listener thread và kiểm tra cấu hình syncCommits của container.

### Chọn MANUAL hay MANUAL_IMMEDIATE?

| Mode | Hành vi | Use case |
|---|---|---|
| MANUAL | Acknowledgement được xếp hàng; commit theo ranh giới xử lý batch/poll | Muốn tự quyết định record nào đã xong nhưng vẫn gom commit |
| MANUAL_IMMEDIATE | Có thể commit ngay khi acknowledge trên consumer thread | Cần xác nhận ngay sau một side effect hoặc record cụ thể |

Cả hai mode đều không tự làm side effect bên ngoài Kafka trở thành nguyên tử với offset. Nếu database đã commit nhưng tiến trình dừng trước khi Kafka offset được commit, record có thể được giao lại.

## 10. Commit sau khi ghi database

Một use case phổ biến là consumer nhận sự kiện, cập nhật database rồi mới acknowledge Kafka.

Luồng:

~~~text
Kafka record
     |
     v
Listener xử lý nghiệp vụ
     |
     v
Database transaction
     |
     +---- rollback / exception ----> Không acknowledge
     |
     v
Database commit thành công
     |
     v
Acknowledgment.acknowledge()
     |
     v
Kafka offset commit
~~~

Ví dụ:

~~~java
@KafkaListener(
    topics = "payments",
    groupId = "payment-service",
    containerFactory = "manualAckListenerContainerFactory"
)
public void handle(
        PaymentRequested event,
        Acknowledgment acknowledgment) {

    paymentService.applyInDatabaseTransaction(event);

    acknowledgment.acknowledge();
}
~~~

Nếu paymentService hoàn tất transaction database nhưng tiến trình chết trước acknowledge/offset commit, Kafka sẽ giao lại record. Consumer cần idempotency key như eventId và unique constraint/inbox table để lần xử lý thứ hai không tạo thêm khoản thanh toán.

Một thiết kế thường dùng là ghi eventId đã xử lý và cập nhật dữ liệu nghiệp vụ trong cùng transaction database:

~~~sql
BEGIN;

INSERT INTO processed_events(event_id)
VALUES ('evt-123');

UPDATE payments
SET status = 'APPLIED'
WHERE payment_id = 'pay-456';

COMMIT;
~~~

Trong thực tế, unique constraint trên processed_events.event_id giúp ngăn hai lần xử lý đồng thời cùng event. Nếu insert bị duplicate, ứng dụng nhận biết event đã được xử lý và có thể acknowledge record theo quy tắc nghiệp vụ.

Không tách việc ghi dấu event đã xử lý và cập nhật dữ liệu thành hai transaction database độc lập, vì lỗi giữa hai bước có thể làm dữ liệu và inbox không nhất quán.

## 11. Xử lý batch và partial success

Với batch listener, một lần gọi nhận nhiều record. Có hai chiến lược phổ biến:

- Xử lý toàn batch trong một transaction rồi acknowledge sau khi toàn bộ batch thành công.
- Xử lý từng record, theo dõi record nào thành công và dùng cơ chế partial batch/offset phù hợp với phiên bản Spring Kafka.

Nếu dùng MANUAL và chỉ gọi acknowledge sau khi mọi record trong batch thành công, cách triển khai đơn giản hơn. Nếu một record lỗi, không acknowledge batch; error handler sẽ quyết định retry hoặc recover.

Với Kafka Consumer API thuần, có thể commit offset riêng cho từng partition nếu đã xử lý một tiền tố liên tục. Không được commit vượt qua record lỗi chỉ vì các record sau đã hoàn tất trước.

Ví dụ một partition:

~~~text
P0: offset 10  -> thành công
P0: offset 11  -> thất bại
P0: offset 12  -> thành công

Offset an toàn để commit: 11
Không commit: 13
~~~

Offset 11 là vị trí tiếp theo cần đọc, vì record 10 đã hoàn tất còn record 11 chưa hoàn tất. Record 12 đã xử lý xong vẫn không cho phép commit vượt qua khoảng trống 11.

Nếu muốn tiếp tục xử lý các record sau record lỗi, cần có chiến lược retry/DLT và quản lý offset phù hợp. Đừng tự bỏ qua record lỗi rồi commit offset cao hơn nếu nghiệp vụ yêu cầu không mất dữ liệu.

## 12. Xử lý song song và acknowledgement lệch thứ tự

Một số ứng dụng chuyển việc xử lý record sang executor để tăng throughput. Khi record của cùng poll được hoàn tất không theo thứ tự, việc acknowledge record phía sau trước record phía trước có thể làm offset commit vượt qua công việc chưa xong nếu không có cơ chế theo dõi.

Spring Kafka từ phiên bản 2.8 có thuộc tính asyncAcks, cho phép acknowledgement của các record trong một poll được gửi không theo thứ tự. Container theo dõi các acknowledgement còn thiếu và tạm dừng consumer cho đến khi các offset trước đó được xác nhận đầy đủ. Có thể bật trên container factory:

~~~java
factory.getContainerProperties().setAsyncAcks(true);
~~~

Ví dụ:

~~~text
Poll trả về:       offset 20, 21, 22
Hoàn tất:          20, 22
Chưa hoàn tất:     21

Container chưa thể commit vượt qua 21.
Consumer có thể bị pause cho đến khi ack 21.
Khi 21 hoàn tất, container mới có thể tiến commit.
~~~

Cơ chế này giúp tránh commit vượt qua record chưa hoàn tất, nhưng không tự bảo đảm side effect chỉ xảy ra một lần. Nếu tiến trình lỗi trước khi tất cả acknowledgement được hoàn tất, record có thể được giao lại.

Khi dùng asyncAcks:

- Xác nhận từng record đúng một lần sau khi xử lý xong.
- Không acknowledge trước khi tác vụ nền hoàn tất.
- Theo dõi thời gian một acknowledgement bị treo.
- Chấp nhận rằng consumer có thể pause và lag tăng khi một record chậm.
- Giữ xử lý nghiệp vụ idempotent vì record đã xử lý có thể được giao lại sau lỗi.

Nếu không cần xử lý bất đồng bộ, giữ listener xử lý tuần tự theo partition thường đơn giản và dễ bảo đảm thứ tự hơn.

## 13. Retry, dead-letter và thời điểm commit

Khi listener ném exception, Spring Kafka error handler quyết định retry, recover hoặc gửi record đến dead-letter topic. Offset chỉ nên tiến qua record khi chính sách xử lý đã xác định rõ record đó được xử lý thành công hoặc được recover theo quy tắc đã chọn.

Một luồng xử lý thường gặp:

~~~text
Listener nhận record
       |
       v
Xử lý nghiệp vụ
       |
       +---- thành công ----> acknowledge / commit
       |
       +---- thất bại
                |
                v
          Retry theo backoff
                |
          +-----+------+
          |            |
       thành công    hết retry
          |            |
          v            v
      commit       publish DLT
                       |
                 recover thành công
                       |
                 commit theo error handler
~~~

Khi gửi DLT thành công, ứng dụng đã chuyển record sang luồng xử lý lỗi theo chính sách. Điều đó không có nghĩa nghiệp vụ ban đầu thành công; cần theo dõi DLT và quy trình replay.

Không tự acknowledge trong catch block chỉ để tránh retry. Nếu exception biểu thị side effect chưa hoàn tất, commit offset sẽ làm record bị bỏ qua. Nếu lỗi không thể retry, hãy dùng recoverer/DLT và chỉ commit theo kết quả recover được xác nhận.

## 14. Kafka transaction và offset commit

Trong luồng consume-transform-produce, Kafka transaction có thể commit output record và offset đầu vào như một đơn vị nguyên tử.

Ví dụ:

~~~text
Consume input offset 50
        |
Transform
        |
Begin Kafka transaction
        |
Produce output record(s)
        |
Add input offset 51 to transaction
        |
Commit transaction
        |
Output và input offset cùng được commit
~~~

Với Spring Kafka, listener container có thể tham gia Kafka transaction thông qua KafkaTransactionManager và transactional producer factory. Offset của record đầu vào được gửi vào transaction cùng các record đầu ra theo cấu hình container.

Khi dùng transaction cho consume-transform-produce, không nên tự gọi commitSync() hoặc acknowledge theo cách tách rời transaction nếu mục tiêu là exactly-once trong Kafka. Hãy để transaction manager/container điều phối việc gửi offset vào transaction.

Consumer đọc output transactional cần isolation.level=read_committed để chỉ thấy record thuộc transaction đã commit.

Kafka transaction không bao phủ mặc định database hoặc HTTP API. Nếu listener ghi database rồi Kafka transaction abort, side effect database vẫn có thể tồn tại. Cần inbox/outbox, idempotency hoặc cơ chế phối hợp nghiệp vụ để xử lý ranh giới đó.

## 15. Commit khi rebalance và shutdown

Khi consumer group rebalance, partition có thể bị thu hồi khỏi member hiện tại. Consumer cần hoàn tất công việc đang xử lý và commit tiến độ an toàn trước khi nhường partition nếu có thể.

Với Kafka Consumer API, có thể đăng ký ConsumerRebalanceListener để xử lý thời điểm partition bị thu hồi:

~~~java
consumer.subscribe(
    List.of("orders"),
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                Collection<TopicPartition> partitions) {
            // Commit phần offset đã xử lý liên tục trước khi nhường partition.
            commitProcessedOffsets(partitions);
        }

        @Override
        public void onPartitionsAssigned(
                Collection<TopicPartition> partitions) {
            // Có thể seek nếu use case yêu cầu vị trí bắt đầu cụ thể.
        }
    }
);
~~~

Đây là ví dụ khái quát; commitProcessedOffsets cần dùng offset map của các record đã hoàn tất và chỉ commit partition còn thuộc quyền sở hữu của consumer.

Trong Spring Kafka, listener container quản lý rebalance callback và offset commit theo acknowledgement mode. Nếu cần logic tùy chỉnh, có thể dùng ConsumerAwareRebalanceListener hoặc cơ chế hỗ trợ tương ứng của phiên bản Spring Kafka. Tránh gọi consumer API từ thread khác với consumer thread của container.

Khi shutdown:

1. Ngừng nhận công việc mới hoặc yêu cầu container dừng.
2. Chờ xử lý đang chạy trong giới hạn shutdown timeout.
3. Commit phần tiến độ đã hoàn tất.
4. Đóng consumer và giải phóng tài nguyên.

Nếu tiến trình bị kill -9 hoặc máy chủ mất điện, shutdown hook không chạy. Vì vậy, thiết kế vẫn phải chịu được record được giao lại sau restart.

## 16. Bảng chọn cách commit theo use case

| Tình huống | Lựa chọn | Lưu ý |
|---|---|---|
| Listener xử lý đồng bộ từng record | AckMode.RECORD | Container commit sau từng record thành công |
| Listener xử lý batch và muốn giảm commit | AckMode.BATCH | Chỉ commit sau khi batch được xử lý |
| Ghi DB rồi xác nhận | MANUAL hoặc MANUAL_IMMEDIATE | DB transaction và Kafka offset không nguyên tử mặc định |
| Consumer API thuần, cần xác nhận rõ | commitSync() | Chặn để chờ broker trả kết quả |
| Consumer throughput cao | commitAsync() | Có thể replay khi commit lỗi; kiểm soát callback và thứ tự |
| Xử lý record song song lệch thứ tự | asyncAcks nếu phiên bản hỗ trợ | Consumer có thể pause chờ acknowledgement còn thiếu |
| Consume-transform-produce Kafka-to-Kafka | Kafka transaction | Offset và output phải nằm trong cùng transaction |
| Replay/backfill | Group ID riêng, commit tiến độ riêng | Tránh ghi đè offset production |

## 17. Các lỗi thường gặp

**Commit trước khi side effect hoàn tất.** Nếu database/API thất bại sau commit, Kafka sẽ không giao lại record theo offset đó. Chỉ commit sau khi công việc cần thiết hoàn tất.

**Commit cả batch sau khi chỉ xử lý một phần.** commitSync() không tham số có thể commit position đã tiến qua toàn bộ poll. Nếu cần partial success, hãy commit offset map của tiền tố liên tục đã xử lý.

**Nhầm offset record cuối với offset tiếp theo.** Xử lý record 40 thì commit 41. Commit 40 có thể khiến record 40 được đọc lại.

**Retry commitAsync cũ sau khi commit mới đã gửi.** Có thể làm committed offset lùi. Theo dõi callback và không retry mù một offset cũ.

**Gọi KafkaConsumer từ nhiều thread.** Consumer không thread-safe. Điều phối poll, commit, seek và close trên consumer thread.

**Acknowledge từ tác vụ nền trước khi hoàn tất.** Side effect có thể chưa xong khi offset đã tiến. Chỉ acknowledge sau khi future/tác vụ thực sự hoàn tất.

**Cho rằng manual ack tạo exactly-once với database.** Database commit và Kafka offset commit là hai hệ thống riêng. Dùng inbox, unique constraint hoặc outbox phù hợp.

**Dùng manual commit trong listener container mà không xác định ai quản lý offset.** Có thể gây commit trùng, commit sai thời điểm hoặc xung đột với container. Trong @KafkaListener, ưu tiên Acknowledgment và AckMode.

## 18. Kiểm thử commit thủ công

Các bài kiểm thử tích hợp nên mô phỏng lỗi đúng tại ranh giới giữa xử lý và commit:

- Xử lý record thành công rồi commit; restart consumer và xác nhận nó tiếp tục ở offset tiếp theo.
- Làm listener thất bại trước acknowledge; xác nhận record được giao lại.
- Ghi database thành công rồi dừng tiến trình trước commit; xác nhận lần giao lại không tạo side effect thứ hai.
- Xử lý batch có một record lỗi; xác nhận committed offset không vượt qua record lỗi.
- Gửi commitAsync rồi mô phỏng lỗi callback; xác nhận metric và chính sách phục hồi hoạt động.
- Gửi commit offset thấp sau commit offset cao trong test kiểm soát để chứng minh nguy cơ lùi offset.
- Xử lý bất đồng bộ với asyncAcks và xác nhận container không commit vượt qua acknowledgement còn thiếu.
- Rebalance khi đang xử lý; xác nhận chỉ commit phần offset thuộc partition đã hoàn tất.
- Consume-transform-produce trong Kafka transaction rồi abort; xác nhận output và offset cùng rollback trong phạm vi Kafka transaction.

Không chỉ mock Acknowledgment hoặc Consumer để kiểm tra lời gọi method. Dùng broker tích hợp hoặc Testcontainers để xác nhận committed offset, record được giao lại và trạng thái consumer group.

## 19. Quan sát commit trong môi trường chạy thật

Các tín hiệu nên theo dõi:

- Commit success/failure và thời gian commit.
- Số lần commit theo consumer group.
- Consumer lag theo partition.
- Số record được giao lại hoặc xử lý trùng.
- Thời gian từ khi poll đến khi xử lý xong và acknowledge.
- Số acknowledgement còn chờ khi dùng asyncAcks.
- CommitFailedException, rebalance và lỗi coordinator.
- Số record retry, recover và dead-letter.

Có thể dùng Kafka CLI để xem committed offset và lag:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-service
~~~

Khi lag tăng, hãy kiểm tra cả thời gian xử lý và commit. Một listener xử lý nhanh nhưng commit quá thường xuyên có thể chịu overhead; ngược lại, gom batch quá lớn có thể tăng thời gian replay nếu lỗi xảy ra trước commit.

## Checklist thiết kế commit

- [ ] Đã xác định ai sở hữu việc commit: Kafka client, Spring container hay mã ứng dụng.
- [ ] Auto commit đã tắt nếu ứng dụng tự kiểm soát commit.
- [ ] Hiểu committed offset là vị trí đọc tiếp theo.
- [ ] Chỉ commit sau khi các record trước offset đó đã xử lý thành công liên tục.
- [ ] Chọn commitSync hoặc commitAsync theo latency và yêu cầu xác nhận.
- [ ] Callback commitAsync có ghi nhận lỗi và không retry offset cũ mù quáng.
- [ ] Với Spring Kafka, chọn AckMode phù hợp và acknowledge sau side effect.
- [ ] Xử lý database có idempotency/inbox để chịu được record giao lại.
- [ ] Batch/async processing không commit vượt qua record chưa hoàn tất.
- [ ] Retry, DLT, rebalance và shutdown có quy tắc commit rõ.
- [ ] Kafka transaction được dùng khi cần nguyên tử giữa output Kafka và input offset.
- [ ] Đã kiểm thử restart, partial failure, commit failure và duplicate.

## Kết luận

Commit thủ công cho phép ứng dụng kiểm soát chính xác lúc consumer xác nhận tiến độ. Với Kafka Consumer API, commitSync() chờ kết quả còn commitAsync() không chặn nhưng cần quản lý callback và thứ tự offset. Với Spring Kafka, Acknowledgment kết hợp MANUAL hoặc MANUAL_IMMEDIATE là cách tích hợp phù hợp để listener xác nhận sau khi xử lý. Trong mọi trường hợp, chỉ commit qua một tiền tố liên tục đã hoàn tất trên từng partition; thiết kế idempotent để chịu được lỗi sau side effect nhưng trước commit. Khi cần nguyên tử giữa output Kafka và offset đầu vào, hãy dùng Kafka transaction thay vì tách commit thủ công khỏi transaction.

