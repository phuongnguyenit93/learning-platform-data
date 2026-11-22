# Sync commit và async commit

Kafka consumer phải ghi nhận offset để xác định vị trí sẽ đọc tiếp sau khi tiến trình khởi động lại hoặc consumer group rebalance. Thao tác commit có hai cách phổ biến: **synchronous commit** với commitSync() và **asynchronous commit** với commitAsync(). Cả hai đều lưu offset của consumer group lên Kafka broker, nhưng khác nhau về thời gian chờ, cách nhận lỗi và cách phối hợp nhiều lần commit.

Trong Spring Kafka, listener container thường quản lý việc commit theo AckMode. Container có thể dùng commitSync() hoặc commitAsync() tùy cấu hình syncCommits. Khi hiểu hành vi của Kafka Consumer API, người vận hành có thể chọn đúng chế độ cho throughput, độ trễ và mức an toàn dữ liệu.

## 1. Offset được commit là vị trí đọc tiếp theo

Mỗi record trong partition có một offset tăng dần. Khi consumer xử lý record có offset 41 thành công, offset cần commit thường là **42**, tức vị trí tiếp theo sẽ đọc. Giá trị committed offset không phải offset cuối cùng đã xử lý; nó là vị trí tiếp tục tiêu thụ.

Ví dụ:

    Partition orders-0

    Offset:       40       41       42       43
                  |        |        |        |
    Record:       A        B        C        D

    Consumer xử lý A và B thành công
    Commit offset = 42
    Restart -> đọc tiếp từ offset 42 (record C)

Kafka có thể có khoảng trống offset do compaction, transaction hoặc record không hiển thị với consumer read_committed. Vì vậy, offset không phải số lượng record đã xử lý. Khi commit một record cụ thể, dùng offset của record đó cộng một theo quy ước vị trí tiếp theo.

Commit offset là một thao tác độc lập với xử lý nghiệp vụ. Nếu consumer commit trước khi database hoặc side effect hoàn tất, record có thể bị bỏ qua sau restart. Nếu xử lý nghiệp vụ thành công nhưng commit chưa hoàn tất, record có thể được giao lại. Đây là lý do hệ thống thường chọn at-least-once và làm consumer idempotent.

## 2. Tắt auto commit khi cần kiểm soát thời điểm commit

Kafka consumer có thuộc tính enable.auto.commit. Khi bật, client tự commit offset theo lịch, không nhất thiết đồng bộ với thời điểm ứng dụng hoàn tất xử lý record.

Ví dụ rủi ro:

1. Consumer poll một batch gồm các record 100 đến 109.
2. Consumer bắt đầu xử lý record 100.
3. Auto commit ghi offset 110.
4. Ứng dụng dừng khi mới xử lý được một phần batch.
5. Sau restart, consumer tiếp tục từ 110 và các record còn lại trong batch có thể bị bỏ qua.

Với xử lý nghiệp vụ cần kiểm soát chặt chẽ, tắt auto commit và để ứng dụng hoặc Spring Kafka container commit sau khi xử lý thành công:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
~~~

Khi dùng Kafka Consumer API trực tiếp:

~~~java
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
~~~

Tắt auto commit không tự động bảo đảm xử lý an toàn. Ứng dụng vẫn phải chọn thời điểm commit hợp lý, theo dõi lỗi commit và xử lý khả năng duplicate. Trong Spring Kafka, listener container thường tắt auto commit khi tự quản lý offset; cấu hình rõ ràng giúp tránh phụ thuộc vào giá trị mặc định hoặc cấu hình khác trong môi trường.

## 3. Synchronous commit với commitSync()

commitSync() gửi yêu cầu commit offset và chặn thread gọi cho tới khi commit hoàn tất hoặc một lỗi không thể phục hồi được báo ra. Đây là cách đơn giản để biết kết quả commit trước khi tiếp tục.

Các dạng API thường dùng:

~~~java
consumer.commitSync();

consumer.commitSync(Duration.ofSeconds(10));

consumer.commitSync(offsets);

consumer.commitSync(offsets, Duration.ofSeconds(10));
~~~

Không truyền map thì consumer commit các vị trí hiện tại của những partition đang được assign. Truyền map cho phép chỉ định offset cụ thể theo từng TopicPartition. Dạng có Duration đặt giới hạn thời gian chờ cho thao tác commit.

Ví dụ xử lý toàn bộ batch trước rồi mới commit:

~~~java
while (running) {
    ConsumerRecords<String, OrderEvent> records =
            consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, OrderEvent> record : records) {
        orderService.process(record.value());
    }

    // Chỉ commit sau khi toàn bộ batch đã xử lý thành công.
    consumer.commitSync();
}
~~~

Trong ví dụ này, nếu một record ném exception, vòng lặp không tới lệnh commitSync(). Những record chưa xử lý có thể được giao lại sau khi consumer phục hồi. Các record đã xử lý trước lỗi cũng có thể được giao lại; consumer cần idempotency để tránh lặp side effect.

### 3.1. Ưu điểm và chi phí của commitSync()

Ưu điểm chính là luồng xử lý biết commit đã thành công hay thất bại trước khi tiếp tục. Với lỗi tạm thời có thể retry, Kafka client có thể thử lại commitSync() cho tới khi thành công hoặc tới giới hạn timeout; các lỗi không thể phục hồi sẽ được ném ra cho ứng dụng.

Nhược điểm là thread bị chặn trong thời gian broker xử lý commit. Nếu commit thường xuyên, độ trễ này có thể làm giảm throughput và ảnh hưởng nhịp poll. Khi broker hoặc coordinator chậm, consumer dành nhiều thời gian chờ commit thay vì xử lý record.

commitSync() phù hợp khi:

- Cần biết chắc kết quả commit trước khi tiếp tục một bước quan trọng.
- Đang kết thúc consumer hoặc cần flush offset cuối cùng.
- Đang xử lý partition rebalance và cần commit các offset an toàn trước khi nhường partition.
- Tải không quá nhạy với độ trễ commit và sự đơn giản quan trọng hơn tối ưu throughput.

Không nên gọi commitSync() từ một thread tùy ý. KafkaConsumer không thread-safe; các thao tác consumer phải được điều phối trên thread sở hữu consumer. Trong Spring Kafka, để container thực hiện commit theo AckMode thường an toàn và nhất quán hơn việc tự gọi consumer API từ listener.

### 3.2. Commit offset cụ thể

Khi chỉ xử lý được một phần batch, commitSync() không tham số có thể commit vị trí hiện tại của consumer, vốn đã tiến tới cuối dữ liệu được poll. Điều này có thể bỏ qua record chưa xử lý. Hãy truyền map chứa offset đã xử lý an toàn.

Ví dụ xử lý một record và commit ngay sau khi side effect thành công:

~~~java
TopicPartition partition =
        new TopicPartition(record.topic(), record.partition());

long nextOffset = record.offset() + 1;

Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
        partition,
        new OffsetAndMetadata(nextOffset)
);

orderService.process(record.value());
consumer.commitSync(offsets, Duration.ofSeconds(10));
~~~

Thứ tự rất quan trọng: chỉ cập nhật và commit offset sau khi orderService.process() hoàn tất thành công. Nếu process() thất bại, không thực hiện commit.

Với nhiều record trong cùng partition, chỉ commit tới vị trí liên tục cao nhất mà mọi record trước đó đã xử lý thành công. Không được commit offset cao hơn qua một record bị lỗi, vì Kafka sẽ tiếp tục từ offset đã commit và bỏ qua record chưa xử lý đó.

## 4. Asynchronous commit với commitAsync()

commitAsync() gửi yêu cầu commit nhưng trả về ngay, không chặn thread chờ broker xác nhận. Kết quả được thông báo qua OffsetCommitCallback.

Ví dụ:

~~~java
consumer.commitAsync((offsets, exception) -> {
    if (exception != null) {
        log.error("Offset commit failed: {}", offsets, exception);
        return;
    }

    log.debug("Offset commit succeeded: {}", offsets);
});
~~~

Có thể truyền map offset cụ thể:

~~~java
consumer.commitAsync(offsets, (committedOffsets, exception) -> {
    if (exception != null) {
        log.error("Async commit failed: {}", committedOffsets, exception);
    }
});
~~~

Callback nhận map offset đã yêu cầu commit và exception nếu thao tác thất bại. Khi thành công, exception là null. Callback giúp ghi log, metric và phát cảnh báo mà không phải chặn luồng chính để chờ phản hồi.

### 4.1. Ưu điểm và giới hạn

commitAsync() giảm thời gian chờ trong vòng lặp poll và thường phù hợp cho commit định kỳ trên luồng tiêu thụ có throughput cao. Ứng dụng có thể tiếp tục xử lý sau khi gửi yêu cầu commit.

Tuy nhiên, commitAsync() không tự retry khi commit thất bại. Ứng dụng nhận lỗi trong callback và phải quyết định cách xử lý. Một lần commit thất bại cũng có thể có trạng thái không chắc chắn: broker có thể đã áp dụng commit nhưng phản hồi bị mất trên đường truyền.

Không nên tự động gửi lại mọi commit thất bại mà không xét thứ tự. Giả sử commit offset 120 thất bại, sau đó commit offset 150 đã thành công. Nếu ứng dụng retry yêu cầu cũ 120 sau đó, committed offset có thể bị lùi về 120 và khiến consumer đọc lại nhiều record hơn. Đây là một lý do Kafka client không tự retry commitAsync() như commitSync().

### 4.2. Callback cần nhẹ và không chặn

Callback nên thực hiện những việc ngắn như ghi log, tăng counter hoặc cập nhật trạng thái quan sát được. Tránh gọi dịch vụ từ xa, chờ database hoặc thực hiện xử lý nặng trong callback. Với Kafka Consumer API, callback được thực thi trong luồng điều khiển của consumer; công việc blocking có thể làm chậm vòng poll.

Không gọi commitAsync() đệ quy từ callback để retry ngay lập tức. Nếu muốn retry ở tầng ứng dụng, cần có chính sách tuần tự hóa, kiểm tra offset mới nhất và bảo đảm một commit cũ không thể ghi đè tiến độ mới. Trong nhiều hệ thống, ghi nhận lỗi rồi dùng commitSync() ở điểm kết thúc hoặc điểm đồng bộ phù hợp sẽ đơn giản và an toàn hơn.

## 5. So sánh commitSync() và commitAsync()

| Tiêu chí | commitSync() | commitAsync() |
|---|---|---|
| Cách hoạt động | Chờ kết quả commit | Gửi yêu cầu và tiếp tục |
| Ảnh hưởng thread | Chặn thread gọi | Không chờ broker trong lời gọi |
| Nhận lỗi | Exception được ném ra | Exception được chuyển qua callback |
| Retry mặc định | Retry các lỗi có thể phục hồi cho tới khi thành công hoặc hết thời gian | Không tự retry |
| Độ trễ vòng poll | Có thể tăng do chờ commit | Thường thấp hơn |
| Độ phức tạp | Dễ suy luận hơn | Cần quản lý callback và thứ tự |
| Điểm phù hợp | Shutdown, rebalance, commit cần xác nhận | Commit định kỳ ở luồng xử lý throughput cao |

Hai phương thức có thể được phối hợp. Một mẫu phổ biến là dùng commitAsync() sau các batch đã xử lý thành công để giảm thời gian chờ, rồi dùng commitSync() tại điểm kết thúc có kiểm soát để bảo đảm các offset cuối cùng đã được commit trước khi đóng consumer.

## 6. Mẫu kết hợp async trong vòng lặp và sync khi kết thúc

Mẫu dưới đây minh họa consumer xử lý batch thành công rồi gửi async commit. Khi dừng có kiểm soát, consumer thực hiện sync commit cuối cùng trước khi đóng.

~~~java
try {
    while (running) {
        ConsumerRecords<String, OrderEvent> records =
                consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, OrderEvent> record : records) {
            orderService.process(record.value());
        }

        consumer.commitAsync((offsets, exception) -> {
            if (exception != null) {
                log.error("Async offset commit failed", exception);
            }
        });
    }
}
finally {
    try {
        // Chỉ an toàn nếu mọi record trong batch cuối đã được xử lý.
        consumer.commitSync(Duration.ofSeconds(10));
    }
    finally {
        consumer.close();
    }
}
~~~

Điều kiện quan trọng của ví dụ là vòng lặp chỉ gọi commitAsync() sau khi xử lý toàn bộ batch thành công, và đường thoát bình thường chỉ xảy ra ở ranh giới batch đã hoàn tất. Nếu xử lý record có thể dừng giữa batch, không được gọi commitSync() không tham số trong finally vì nó có thể commit cả vị trí poll đã tiến qua những record chưa xử lý.

Với ứng dụng cần xử lý lỗi giữa batch, hãy lưu offset an toàn theo từng partition và dùng overload nhận map. Khi shutdown, chỉ commit map offset đã xử lý liên tục. Nếu không còn offset nào an toàn, bỏ qua commit cuối và để Kafka giao lại record sau restart.

## 7. Theo dõi offset an toàn theo partition

Một poll có thể trả record từ nhiều partition. Mỗi partition có tiến độ riêng. Khi xử lý thành công một record, ứng dụng có thể lưu offset tiếp theo của partition đó. Map này chỉ được tiến lên sau khi side effect của record đã hoàn tất.

Ví dụ:

~~~java
Map<TopicPartition, OffsetAndMetadata> safeOffsets =
        new HashMap<>();

for (ConsumerRecord<String, OrderEvent> record : records) {
    orderService.process(record.value());

    TopicPartition partition =
            new TopicPartition(record.topic(), record.partition());

    safeOffsets.put(
        partition,
        new OffsetAndMetadata(record.offset() + 1)
    );
}

if (!safeOffsets.isEmpty()) {
    consumer.commitAsync(
        new HashMap<>(safeOffsets),
        (offsets, exception) -> {
            if (exception != null) {
                log.error("Commit failed for {}", offsets, exception);
            }
        }
    );
}
~~~

Ví dụ trên giả định vòng xử lý dừng ngay khi một record lỗi và không tiếp tục xử lý record phía sau trong cùng partition. Nếu ứng dụng xử lý song song nhiều record cùng partition, cần theo dõi tập hợp kết quả và chỉ commit offset sau record liên tục cuối cùng đã hoàn tất. Không thể chỉ lấy offset lớn nhất trong số các task đã xong.

Ví dụ minh họa:

    Partition orders-0

    Offset:       10       11       12       13
    Kết quả:      OK       FAIL     OK       OK

    Offset 10 đã xử lý
    Offset 11 chưa xử lý thành công
    Offset 12 và 13 đã xong nhưng không thể commit vượt qua 11

    Offset an toàn để commit = 11

Nếu commit 14, consumer sẽ bắt đầu từ 14 khi khởi động lại và bỏ qua record 11. Với xử lý song song, cần có cơ chế lưu trạng thái từng record và tính watermark liên tục theo partition.

## 8. Rebalance và commit cuối trước khi nhường partition

Consumer group có thể rebalance khi consumer tham gia/rời group, session timeout, max poll interval bị vượt hoặc số partition thay đổi. Khi partition sắp được thu hồi, consumer nên commit các offset đã xử lý thành công trước khi nhường quyền sở hữu.

Với Kafka Consumer API, có thể dùng ConsumerRebalanceListener:

~~~java
consumer.subscribe(
    List.of("orders"),
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                Collection<TopicPartition> partitions) {

            Map<TopicPartition, OffsetAndMetadata> offsets =
                    processedOffsetsFor(partitions);

            if (!offsets.isEmpty()) {
                consumer.commitSync(offsets, Duration.ofSeconds(10));
            }
        }

        @Override
        public void onPartitionsAssigned(
                Collection<TopicPartition> partitions) {
            // Khởi tạo trạng thái xử lý cho partition mới.
        }
    }
);
~~~

processedOffsetsFor() là hàm ứng dụng cần triển khai để trả về offset tiếp theo đã xử lý an toàn, chỉ gồm các partition sắp bị thu hồi. Không nên commit toàn bộ vị trí hiện tại nếu có record chưa xử lý.

Một số phiên bản Kafka có callback onPartitionsLost() để báo partition đã mất quyền sở hữu. Khi partition đã bị mất, consumer không còn chắc chắn có thể commit offset của partition đó; không cố commit như thể vẫn còn quyền sở hữu. Hãy xử lý việc mất partition và để consumer mới tiếp tục từ offset đã commit gần nhất.

Trong Spring Kafka, listener container quản lý rebalance và offset commit. Không tự gọi KafkaConsumer.commitSync() từ một listener callback bất kỳ; hãy dùng AckMode, Acknowledgment và các hook container phù hợp với phiên bản thư viện.

## 9. Spring Kafka: container commit đồng bộ hay bất đồng bộ?

Spring Kafka listener container quản lý việc commit offset sau khi listener hoàn tất theo AckMode. Thuộc tính ContainerProperties.syncCommits quyết định cách container gửi commit:

- syncCommits=true: container dùng commitSync(). Đây là mặc định phổ biến.
- syncCommits=false: container dùng commitAsync() và có thể gọi commit callback để báo kết quả.

Ví dụ cấu hình listener container:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
kafkaListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);

    ContainerProperties properties = factory.getContainerProperties();
    properties.setAckMode(ContainerProperties.AckMode.RECORD);
    properties.setSyncCommits(true);
    properties.setSyncCommitTimeout(Duration.ofSeconds(10));

    return factory;
}
~~~

Với RECORD, container commit offset sau khi từng record được listener xử lý thành công. Với BATCH, container commit sau khi toàn bộ batch được trả về từ poll xử lý thành công. Việc commit thực tế vẫn phụ thuộc cấu hình container và transaction đang sử dụng.

Để dùng async commit:

~~~java
ContainerProperties properties = factory.getContainerProperties();

properties.setAckMode(ContainerProperties.AckMode.RECORD);
properties.setSyncCommits(false);
properties.setCommitCallback((offsets, exception) -> {
    if (exception != null) {
        log.error("Spring Kafka async commit failed: {}", offsets, exception);
    }
    else {
        log.debug("Spring Kafka async commit succeeded: {}", offsets);
    }
});
~~~

Commit callback nhận các offset mà container yêu cầu commit và exception nếu commit thất bại. Giữ callback ngắn, tránh thực hiện công việc blocking. Nếu callback chỉ ghi log mà không có cảnh báo hoặc metric, lỗi commit có thể khó phát hiện khi vận hành.

Tên và chữ ký API có thể khác theo phiên bản Spring Kafka. Kiểm tra dependency thực tế trước khi áp dụng cấu hình hoặc import.

## 10. AckMode và manual acknowledgment

AckMode xác định khi nào Spring Kafka container xem record đã sẵn sàng commit. Những chế độ thường gặp:

| AckMode | Thời điểm commit |
|---|---|
| RECORD | Sau khi listener xử lý thành công từng record |
| BATCH | Sau khi tất cả record của poll batch xử lý thành công |
| TIME | Khi khoảng thời gian cấu hình đã trôi qua và điều kiện xử lý phù hợp được đáp ứng |
| COUNT | Khi đủ số record đã xử lý theo ngưỡng cấu hình |
| COUNT_TIME | Khi đạt ngưỡng count hoặc time |
| MANUAL | Listener gọi acknowledge(); container thực hiện commit theo ranh giới batch |
| MANUAL_IMMEDIATE | Listener gọi acknowledge(); container commit ngay nếu lời gọi diễn ra trên consumer thread |

MANUAL và MANUAL_IMMEDIATE đều yêu cầu listener xác nhận rõ ràng. Khác biệt là thời điểm container áp dụng acknowledgment. Với MANUAL_IMMEDIATE, gọi acknowledge() trên consumer thread cho phép container xử lý commit ngay; nếu gọi từ thread khác, acknowledgment được chuyển về luồng container và không còn cùng ý nghĩa “ngay lập tức”. Không trộn lẫn cách gọi trên consumer thread và thread khác trong cùng listener nếu chưa hiểu thứ tự xử lý của container.

Ví dụ manual acknowledgment:

~~~java
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.process(record.value());

    // Chỉ acknowledge sau khi xử lý nghiệp vụ thành công.
    acknowledgment.acknowledge();
}
~~~

Có thể chọn MANUAL_IMMEDIATE và để container dùng sync commit:

~~~java
ContainerProperties properties = factory.getContainerProperties();
properties.setAckMode(ContainerProperties.AckMode.MANUAL_IMMEDIATE);
properties.setSyncCommits(true);
~~~

Nếu chuyển syncCommits=false, acknowledgment sẽ được commit bằng đường async của container. Listener không nhận kết quả commit ngay tại lời gọi acknowledge(); cần theo dõi callback commit của container và thiết kế retry/idempotency cho trường hợp commit thất bại hoặc phản hồi không rõ ràng.

## 11. Quan hệ giữa database transaction và offset commit

Một consumer thường thực hiện side effect ở database rồi mới commit offset Kafka. Thứ tự này tránh đánh dấu record hoàn tất trước khi dữ liệu nghiệp vụ bền vững.

    Poll record
       |
       v
    Bắt đầu database transaction
       |
       v
    Cập nhật dữ liệu nghiệp vụ
       |
       v
    Database commit
       |
       v
    Kafka offset commit

Nếu ứng dụng dừng sau database commit nhưng trước offset commit, Kafka giao lại record. Điều này tạo duplicate ở lần xử lý tiếp theo. Consumer nên dùng eventId và bảng inbox/processed_event trong cùng database transaction với thay đổi nghiệp vụ.

Nếu commit offset trước database commit rồi database rollback, record có thể bị bỏ qua. Vì vậy, đừng commit trước khi side effect đã bền vững trừ khi nghiệp vụ chấp nhận at-most-once.

Kafka transaction có thể kết hợp việc ghi record đầu ra và offset consumer trong cùng transaction Kafka. Nó không tự tạo transaction nguyên tử với database độc lập. Với luồng ghi database và phát Kafka event, cân nhắc Transactional Outbox; với luồng nhận Kafka và ghi database, cân nhắc Inbox hoặc idempotent update.

## 12. Timeout, poll và lỗi commit

Commit cần thời gian trao đổi với group coordinator. Khi coordinator không sẵn sàng, network chậm hoặc group đang rebalance, commit có thể thất bại hoặc timeout.

Các cấu hình và điều kiện cần xem xét:

- request.timeout.ms: thời gian chờ phản hồi cho một request.
- default.api.timeout.ms: giới hạn mặc định cho các API có timeout.
- max.poll.interval.ms: giới hạn thời gian giữa các lần poll trước khi consumer có thể bị xem là không còn tiến triển.
- session.timeout.ms và heartbeat.interval.ms: ảnh hưởng đến việc phát hiện consumer mất kết nối.
- syncCommitTimeout của Spring Kafka: thời gian chờ commit đồng bộ do container sử dụng.

Đừng tăng timeout một cách máy móc để che giấu consumer xử lý quá lâu. Nếu listener xử lý một batch lâu hơn max.poll.interval.ms, group có thể rebalance và commit của consumer cũ có thể thất bại. Hãy kiểm tra thời gian xử lý, số record mỗi poll, concurrency và cách phân chia batch.

Khi commit thất bại:

1. Ghi nhận consumer group, topic, partition và offset yêu cầu commit.
2. Phân loại lỗi: timeout, coordinator unavailable, rebalance, authorization hoặc lỗi cấu hình.
3. Xác định record nghiệp vụ đã xử lý tới đâu.
4. Không giả định commit thất bại đồng nghĩa broker chắc chắn chưa lưu offset.
5. Để record có thể được giao lại và dựa vào idempotency nếu trạng thái commit không chắc chắn.

## 13. Quan sát commit trong production

Nên theo dõi cả hoạt động xử lý record và hoạt động commit offset:

**Chỉ số commit**

- Số lần commitSync và commitAsync.
- Tỷ lệ commit thành công/thất bại.
- Độ trễ commit và số lần timeout.
- Exception theo nhóm: rebalance, coordinator, network, authorization.
- Offset commit được yêu cầu theo topic và partition.

**Chỉ số consumer**

- Consumer lag theo group và partition.
- Tốc độ poll và xử lý record.
- Thời gian xử lý batch và từng record.
- Số lần rebalance và partition bị thu hồi/mất.
- Số record được giao lại hoặc bị xử lý trùng.

**Log và trace**

Log commit nên có group ID, topic, partition, offset, chế độ commit và nguyên nhân lỗi. Kết hợp eventId với log nghiệp vụ để xác định record đã được xử lý trước khi commit hay chưa. Tránh chỉ ghi một thông báo chung “commit failed” mà không có offset liên quan.

Consumer lag thấp không tự chứng minh không mất message. Offset có thể đã bị commit sớm trước khi side effect hoàn tất. Cần đối chiếu offset với kết quả nghiệp vụ, số event đầu vào và trạng thái xử lý.

## 14. Kiểm thử hành vi commit

Trong môi trường kiểm thử, hãy mô phỏng các cửa sổ lỗi quan trọng:

1. Consumer xử lý record xong rồi dừng trước commit: record có thể được giao lại, nhưng side effect không được nhân đôi.
2. Consumer dừng giữa batch: offset không được vượt qua record chưa xử lý.
3. Broker coordinator tạm thời không sẵn sàng: commitSync phải báo lỗi hoặc hết timeout; commitAsync phải gọi callback với trạng thái lỗi nếu request thất bại.
4. Async commit thất bại rồi có commit mới hơn: không retry mù offset cũ làm lùi tiến độ.
5. Consumer rebalance trong lúc xử lý: chỉ commit offset an toàn của partition sắp nhường.
6. Callback commit phát sinh lỗi: metric và log phải ghi lại group, partition, offset và exception.
7. Listener xử lý database thành công nhưng commit offset thất bại: lần giao lại phải an toàn nhờ idempotency.
8. Dừng ứng dụng có kiểm soát: commit cuối chỉ chứa offset đã xử lý hoàn tất.

Các bài kiểm thử này giúp xác nhận chính sách commit theo hành vi thực tế, đặc biệt ở những thời điểm ứng dụng và broker có thể mất kết nối.

## 15. Chọn chế độ commit theo tình huống

| Tình huống | Cách chọn phù hợp |
|---|---|
| Consumer tải vừa, cần đơn giản và biết kết quả commit | commitSync() |
| Consumer xử lý liên tục, commit định kỳ và nhạy với độ trễ | commitAsync() kèm callback và quan sát lỗi |
| Consumer đang shutdown có kiểm soát | commitSync() cho offset cuối đã xử lý an toàn |
| Partition sắp được thu hồi khi rebalance | CommitSync map offset đã xử lý của các partition bị thu hồi |
| Chỉ xử lý thành công từng record trong Spring Kafka | AckMode.RECORD |
| Xử lý theo batch trong Spring Kafka | AckMode.BATCH |
| Listener cần tự xác nhận sau side effect | MANUAL hoặc MANUAL_IMMEDIATE |
| Listener cần callback báo lỗi async commit | syncCommits=false và commit callback |
| Xử lý song song trong cùng partition | Chỉ commit watermark liên tục của các record đã hoàn tất |

Sync commit và async commit là hai cách ghi nhận tiến độ của cùng một consumer group. Sync commit phù hợp tại những điểm cần chờ kết quả và đồng bộ trạng thái; async commit giúp giảm thời gian chờ trong vòng poll nhưng đòi hỏi callback, theo dõi lỗi và kỷ luật thứ tự. Dù chọn cách nào, chỉ commit offset sau khi các record trước nó đã xử lý thành công, giữ khả năng giao lại khi kết quả không chắc chắn và thiết kế side effect idempotent để consumer phục hồi an toàn.