# Xử lý consumer không có dữ liệu

Trong Kafka, consumer có thể poll nhiều lần mà không nhận được record. Đây là trạng thái bình thường khi topic chưa có dữ liệu mới, producer gửi chậm hoặc consumer đã đọc đến cuối log hiện tại. `poll()` trả về tập `ConsumerRecords` rỗng không có nghĩa consumer đã kết thúc, topic bị lỗi hay kết nối đã hỏng. Kafka là hệ thống log liên tục; khi record mới được ghi vào partition, consumer có thể nhận chúng ở những lần poll tiếp theo.

Với Spring Kafka, listener thường chỉ được gọi khi container nhận được record. Khi không có record, phương thức `@KafkaListener` không được gọi với một danh sách rỗng theo kiểu mặc định của record listener. Nếu ứng dụng cần biết listener đang idle, cần dùng cơ chế idle event của container hoặc chủ động theo dõi metric. Bài viết này giải thích cách nhận biết trạng thái không có dữ liệu, phân biệt với các lỗi cấu hình và xử lý phù hợp trong KafkaConsumer lẫn Spring Kafka.

## 1. poll() rỗng là trạng thái bình thường

Consumer đọc dữ liệu bằng cách gọi `poll(Duration)`. Lệnh này trả về các record hiện có từ những partition đã được gán cho consumer. Nếu không có record sẵn sàng trong khoảng chờ, kết quả có thể rỗng:

```java
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(1000));

if (records.isEmpty()) {
    log.debug("Chưa có record mới trong lần poll này");
} else {
    for (ConsumerRecord<String, String> record : records) {
        process(record);
    }
}
```

`isEmpty()` kiểm tra lần poll hiện tại có trả về record hay không. Nó không xác nhận topic trống vĩnh viễn, không cho biết producer đã dừng và cũng không chứng minh consumer bị mất kết nối. Một lần poll tiếp theo vẫn có thể nhận dữ liệu vừa được producer ghi vào.

Kafka không dùng một record đặc biệt để báo rằng topic đã kết thúc. Topic thường tiếp tục nhận dữ liệu và partition có thể được mở rộng theo thời gian. Khi consumer đọc đến cuối log hiện tại, nó chỉ đang ở trạng thái chờ record tiếp theo. Vì vậy, không nên thoát vòng lặp chỉ vì một lần `poll()` trả về rỗng.

## 2. Phân biệt không có record với record có value null

Hai trạng thái sau hoàn toàn khác nhau:

| Trạng thái | Kết quả quan sát | Ý nghĩa |
|---|---|---|
| Không có record | `ConsumerRecords.isEmpty()` là `true` | Lần poll hiện tại không nhận được record nào |
| Có tombstone | `isEmpty()` là `false`, một `ConsumerRecord` có key và value `null` | Kafka đã gửi một record có chủ đích, thường dùng để đánh dấu xóa key trong topic compact |
| Value rỗng | Có record, value là chuỗi rỗng hoặc mảng byte rỗng | Record tồn tại nhưng payload có độ dài bằng 0 |

Trong compacted topic, tombstone thường có key và value `null`, biểu thị key đó đã bị xóa khỏi trạng thái được compact. Đây vẫn là một record có offset và phải được xử lý theo nghiệp vụ. Không dùng điều kiện `record.value() == null` để kết luận consumer không có dữ liệu.

Ví dụ xử lý tombstone:

```java
for (ConsumerRecord<String, String> record : records) {
    if (record.value() == null) {
        handleDeletedKey(record.key());
    } else {
        processValue(record.key(), record.value());
    }
}
```

Nếu deserializer không chấp nhận dữ liệu hoặc ném lỗi, đó là lỗi deserialize cần xử lý bằng error handler hoặc `ErrorHandlingDeserializer` trong Spring Kafka. Lỗi deserialize không tương đương với một lần poll rỗng.

## 3. Một lần poll chờ dữ liệu trong bao lâu?

Tham số `Duration` của `poll()` là thời gian tối đa lần gọi poll chờ dữ liệu và xử lý các hoạt động consumer cần thiết. Ví dụ:

```java
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofSeconds(2));
```

Consumer có thể trả về sớm khi dữ liệu sẵn sàng; không nên giả định mỗi lần poll luôn chờ đủ hai giây. Nếu chưa có record, lần gọi có thể kết thúc sau khoảng chờ phù hợp với phản hồi fetch và trạng thái client. Dùng timeout bằng 0 để poll liên tục có thể tạo vòng lặp bận (busy loop), tiêu tốn CPU và tạo log quá nhiều.

Không nhầm thời gian chờ của `poll()` với `max.poll.interval.ms`:

| Thuộc tính | Điều khiển điều gì? |
|---|---|
| `poll(Duration)` hoặc `pollTimeout` trong Spring Kafka | Thời gian chờ tối đa của một lần poll |
| `max.poll.interval.ms` | Khoảng thời gian tối đa giữa hai lần gọi poll trong consumer group trước khi consumer bị xem là không còn tiến triển |
| `fetch.max.wait.ms` | Thời gian broker tối đa chờ để đáp ứng yêu cầu fetch khi chưa đủ dữ liệu theo `fetch.min.bytes` |
| `fetch.min.bytes` | Lượng dữ liệu tối thiểu broker cố gắng trả về cho một fetch response, nếu có thể |

`fetch.min.bytes` và `fetch.max.wait.ms` phối hợp để cân bằng throughput với độ trễ. Nếu đặt `fetch.min.bytes` cao, broker có thể chờ thêm dữ liệu để trả một response lớn hơn. Khi không đủ dữ liệu, broker vẫn trả về sau khi hết `fetch.max.wait.ms`. Cấu hình này có thể giảm số request ở tải cao nhưng tăng thời gian chờ khi lưu lượng thấp.

`fetch.max.bytes` giới hạn kích thước dữ liệu tối đa broker trả về trong một fetch response; `max.partition.fetch.bytes` giới hạn lượng dữ liệu fetch cho mỗi partition. Đây là các giới hạn kích thước, không phải điều kiện bảo đảm consumer luôn nhận đủ số byte đó. Record lớn và các giới hạn message phía broker còn có quy tắc riêng để consumer có thể tiến triển.

## 4. Vòng lặp consumer khi chưa có dữ liệu

Với Kafka client thuần, cách đơn giản là tiếp tục poll, kiểm tra kết quả và xử lý khi có record:

```java
KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
consumer.subscribe(List.of("orders"));

try {
    while (running) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(1000));

        if (records.isEmpty()) {
            // Có thể cập nhật metric hoặc log ở mức phù hợp.
            idlePollCount.increment();
            continue;
        }

        for (ConsumerRecord<String, String> record : records) {
            processAndPersist(record);
        }

        consumer.commitSync();
    }
} finally {
    consumer.close();
}
```

Không commit chỉ vì poll rỗng. Khi không có record, không có tiến độ xử lý mới cần xác nhận. Commit định kỳ khi không có record thường không mang lại lợi ích; nếu ứng dụng có lý do cần lưu offset cụ thể, phải dựa trên offset đã xử lý và semantics của consumer.

Không thêm `Thread.sleep()` dài sau mỗi lần poll rỗng một cách tùy tiện. Consumer cần tiếp tục gọi poll để duy trì hoạt động group. Nếu muốn giảm tần suất kiểm tra hoặc tạm ngừng tiêu thụ, hãy cân nhắc `pause()`/`resume()` và vẫn tiếp tục poll theo quy tắc Kafka. Khi xử lý mất nhiều thời gian, cần bảo đảm tổng thời gian giữa hai lần poll không vượt `max.poll.interval.ms`.

Nếu ứng dụng cần chờ lâu để tránh tiêu thụ CPU, hãy chọn poll timeout hợp lý thay vì dùng vòng lặp `poll(Duration.ZERO)`. Có thể giảm log ở mỗi lần poll rỗng và dùng bộ đếm hoặc metric tổng hợp để theo dõi idle duration.

## 5. Những nguyên nhân khiến consumer không nhận được record

Một poll rỗng có thể xuất phát từ nhiều nguyên nhân. Cần kiểm tra theo thứ tự từ trạng thái assignment đến vị trí offset và cấu hình cluster:

| Nguyên nhân | Dấu hiệu và cách kiểm tra |
|---|---|
| Producer chưa gửi record mới | Kiểm tra log producer, send future/callback và tốc độ ghi vào topic |
| Consumer đã đọc đến cuối log | So sánh committed/current offset với log end offset của từng partition |
| Consumer chưa được gán partition | Kiểm tra `assignment()`, log rebalance và số partition của topic |
| Sai topic hoặc sai cluster | Kiểm tra `bootstrap.servers`, tên topic, profile và môi trường đang chạy |
| Consumer group đã có offset ở cuối log | Kiểm tra group ID và committed offset; `latest` có thể khiến group mới bắt đầu từ cuối log |
| Record đang ở partition khác | Kiểm tra assignment và key/partition của producer; consumer chỉ đọc partition được gán |
| ACL hoặc quyền truy cập không phù hợp | Kiểm tra log client/broker và quyền `READ` trên topic, `DESCRIBE` topic, `READ` group theo chính sách cluster |
| Đang dùng `read_committed` | Record thuộc transaction chưa commit hoặc transaction đã abort sẽ chưa được trả cho consumer theo isolation này |
| Topic chưa được tạo hoặc metadata chưa cập nhật | Dùng Kafka CLI/AdminClient kiểm tra topic và partition |

Đừng vội thay `auto.offset.reset` khi consumer không nhận được dữ liệu. Thuộc tính này chỉ áp dụng khi group chưa có committed offset hợp lệ hoặc offset đã nằm ngoài phạm vi log. Nếu group có offset hợp lệ ở cuối log, `earliest` cũng không khiến consumer tự đọc lại từ đầu.

## 6. Kiểm tra assignment, offset và lag

Trong code, có thể kiểm tra partition đang được gán sau khi consumer tham gia group:

```java
consumer.poll(Duration.ofMillis(500));
Set<TopicPartition> assigned = consumer.assignment();

if (assigned.isEmpty()) {
    log.info("Consumer chưa được gán partition");
} else {
    log.info("Assigned partitions: {}", assigned);
}
```

Assignment có thể chưa sẵn sàng ngay sau `subscribe()`. Lần poll đầu giúp client tham gia group và nhận assignment; hãy kiểm tra sau khi poll và xử lý callback rebalance nếu cần. Không kết luận consumer không có dữ liệu chỉ dựa trên việc gọi `assignment()` ngay sau `subscribe()`.

Có thể dùng Kafka CLI để xem trạng thái consumer group:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-reader
```

Kết quả cho biết partition, current offset, log end offset và lag. Nếu current offset bằng log end offset, consumer có thể đang theo kịp dữ liệu. Nếu lag lớn nhưng listener vẫn không nhận record, kiểm tra assignment, trạng thái pause, lỗi deserialize, isolation level và log client. Lag là số đo tại thời điểm kiểm tra; nó có thể thay đổi liên tục khi producer tiếp tục ghi.

Mô tả topic để kiểm tra partition và leader:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Nếu topic có nhiều partition nhưng consumer chỉ được gán một tập con, điều đó có thể bình thường khi các consumer khác trong cùng group đang sở hữu partition còn lại. Một consumer chỉ nhận record từ partition được giao cho nó.

## 7. Cấu hình fetch khi lưu lượng thấp hoặc cao

Các cấu hình fetch có thể ảnh hưởng đến cách broker trả dữ liệu:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[fetch.min.bytes]": 1
        "[fetch.max.wait.ms]": 500
        "[fetch.max.bytes]": 52428800
        "[max.partition.fetch.bytes]": 1048576
```

Đây là ví dụ minh họa cấu hình Kafka client; giá trị phù hợp phụ thuộc kích thước record, số partition, throughput và giới hạn broker. Với lưu lượng thấp hoặc yêu cầu phản hồi nhanh, `fetch.min.bytes` nhỏ giúp broker không phải chờ gom nhiều dữ liệu. Với lưu lượng cao, tăng ngưỡng có thể giảm số fetch request nhưng có thể làm record chờ lâu hơn. Không tăng giới hạn fetch chỉ để xử lý poll rỗng nếu nguyên nhân thực sự là sai topic, offset hoặc assignment.

`max.poll.records` là số record tối đa mà một lần poll trả về, không phải số record tối thiểu. Đặt `max.poll.records` lớn không tạo ra dữ liệu khi topic chưa có record mới. Đặt quá thấp có thể làm giảm throughput; đặt quá cao có thể khiến thời gian xử lý batch vượt `max.poll.interval.ms`.

Nếu consumer dùng `isolation.level=read_committed`, nó chỉ đọc các record thuộc transaction đã commit. Trong một partition có transaction đang mở, phần log sau last stable offset có thể chưa được trả về, dù broker đã nhận dữ liệu. Điều này là hành vi đúng của chế độ đọc nhất quán giao dịch, không phải lỗi poll.

## 8. Xử lý trạng thái idle trong Spring Kafka

Với `@KafkaListener`, listener method thường không được gọi khi container poll mà không có record. Nếu ứng dụng cần thực hiện hành động khi không có dữ liệu trong một khoảng thời gian, Spring Kafka cung cấp `ListenerContainerIdleEvent`.

Có thể đặt thời gian phát idle event trên listener container:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {
        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setPollTimeout(1000L);
        factory.getContainerProperties().setIdleEventInterval(10_000L);
        return factory;
    }
}
```

Trong ví dụ, container poll với timeout một giây và phát idle event khi không nhận record trong khoảng idle được cấu hình. Cần đối chiếu API và cấu hình với phiên bản Spring Kafka của dự án; Spring Boot cũng có thể tự tạo listener factory, khi đó nên tùy biến factory hiện có thay vì tạo bean trùng tên.

Lắng nghe event:

```java
@Component
public class KafkaIdleMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleMonitor.class);

    @EventListener
    public void onListenerIdle(ListenerContainerIdleEvent event) {
        log.info("Listener {} idle for {} ms; partitions={}; paused={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions(),
                event.isPaused());
    }
}
```

Gắn `id` rõ ràng cho `@KafkaListener` để nhận biết listener trong log và event:

```java
@KafkaListener(id = "ordersListener", topics = "orders")
public void onMessage(String payload) {
    orderService.handle(payload);
}
```

Idle event hữu ích để ghi nhận thời gian không có dữ liệu, phát hiện luồng sự kiện ngừng bất thường hoặc kích hoạt kiểm tra health ở tầng ứng dụng. Tuy nhiên, idle không tự động có nghĩa hệ thống lỗi. Một topic ít sự kiện có thể idle nhiều giờ mà vẫn hoạt động đúng.

Event được phát từ listener container và có thể được xử lý trên thread consumer tùy cách cấu hình event multicaster. Tránh thực hiện công việc chặn lâu trong event handler vì có thể cản trở vòng lặp poll và làm consumer vượt `max.poll.interval.ms`. Nếu cần gọi dịch vụ ngoài hoặc chạy tác vụ dài, hãy chuyển công việc sang executor có giới hạn và theo dõi hàng đợi; không thao tác trực tiếp với KafkaConsumer từ thread khác.

Với listener chạy concurrency, có thể nhận event idle cho các child container. Hãy dùng listener ID, topic partitions và trạng thái paused trong event để hiểu chính xác consumer nào đang idle. Nếu container đang pause partition theo yêu cầu backpressure, trạng thái này khác với việc topic không có dữ liệu mới.

## 9. Idle, pause/resume và backpressure

`pause()` tạm dừng việc trả record từ các partition được chỉ định trong khi consumer vẫn tiếp tục poll. `resume()` cho phép consumer tiếp tục nhận record. Đây là cơ chế hữu ích khi worker pool hoặc downstream service quá tải:

```java
Set<TopicPartition> partitions = consumer.assignment();
consumer.pause(partitions);

// Tiếp tục gọi poll để duy trì hoạt động consumer group.
ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(1000));

// Khi worker hoặc downstream đã sẵn sàng:
consumer.resume(partitions);
```

Ví dụ rút gọn để minh họa API; việc gọi `pause()`/`resume()` phải nằm trên thread sở hữu consumer và cần theo dõi partition được pause. `pause()` không đồng nghĩa với `unsubscribe()` hoặc rời consumer group. Nếu pause quá lâu mà không poll, consumer vẫn có thể vượt `max.poll.interval.ms`.

Spring Kafka cũng hỗ trợ pause/resume container thông qua API của listener container. Khi dùng container, nên điều khiển qua `KafkaListenerEndpointRegistry` hoặc cơ chế được Spring Kafka hỗ trợ thay vì truy cập trực tiếp KafkaConsumer. Pause có thể tạo trạng thái idle event dù broker vẫn có record; hãy phân biệt trạng thái paused với trạng thái không có dữ liệu.

## 10. Theo dõi trạng thái idle và cảnh báo

Một consumer idle không nhất thiết là consumer lỗi. Cảnh báo nên dựa trên kỳ vọng nghiệp vụ và nhịp sự kiện bình thường. Ví dụ, topic thanh toán dự kiến có sự kiện mỗi phút có thể cần cảnh báo khi không có record trong 15 phút; topic báo cáo chỉ chạy vào cuối ngày không nên dùng cùng ngưỡng đó.

Nên theo dõi kết hợp các chỉ số:

- Thời gian từ record cuối cùng được xử lý thành công.
- Thời gian idle của listener container và số lần idle event.
- Consumer group assignment, current offset, log end offset và lag.
- Tốc độ producer gửi record và lỗi gửi ở phía producer.
- Số partition bị pause, trạng thái rebalance và lỗi deserialize.
- Trạng thái broker, leader/ISR và kết nối tới cluster.

Khi xây dựng cảnh báo, phân biệt ít nhất ba trường hợp: không có record mới vì nguồn dữ liệu không phát sinh sự kiện; consumer không được gán partition hoặc đang pause; consumer có lỗi kết nối, authorization hoặc deserialize. Mỗi trường hợp cần cách xử lý khác nhau.

## 11. Quy trình chẩn đoán khi listener không nhận message

1. Xác nhận ứng dụng đang kết nối đúng cluster và đúng tên topic theo profile đang chạy.
2. Dùng `kafka-topics --describe` để xác nhận topic có partition và leader hợp lệ.
3. Kiểm tra consumer group, member, assignment, current offset và log end offset bằng `kafka-consumer-groups --describe`.
4. Xác nhận listener không bị pause và đã hoàn tất quá trình subscribe/rebalance.
5. Kiểm tra producer send result, record key/partition và topic thực tế mà producer ghi.
6. Kiểm tra `auto.offset.reset`, committed offset và `isolation.level`; không reset offset trước khi hiểu hậu quả.
7. Đọc log client/broker để tìm lỗi ACL, metadata, TLS/SASL, deserialize hoặc transaction.
8. Nếu mọi thứ bình thường và topic đơn giản là chưa có sự kiện, xem poll rỗng/idle event là trạng thái hợp lệ và theo dõi theo ngưỡng nghiệp vụ.

## 12. Các hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| `poll()` rỗng nghĩa là consumer đã dừng | Consumer vẫn hoạt động và có thể nhận record ở lần poll tiếp theo |
| Topic không có record mới nghĩa là Kafka lỗi | Topic có thể đang idle vì producer chưa phát sinh sự kiện |
| `auto.offset.reset=earliest` luôn đọc lại từ đầu | Chỉ áp dụng khi không có committed offset hợp lệ hoặc offset nằm ngoài phạm vi log |
| `max.poll.records` là số record tối thiểu | Đây là giới hạn trên cho số record trả về mỗi lần poll |
| Record có value null nghĩa là không có record | Tombstone vẫn là record có key/offset và cần xử lý theo nghiệp vụ |
| `pollTimeout` chính là `max.poll.interval.ms` | Một giá trị là thời gian chờ mỗi poll, giá trị kia là giới hạn giữa hai lần poll |
| Tăng `fetch.min.bytes` luôn làm consumer nhanh hơn | Broker có thể chờ lâu hơn để gom dữ liệu, tăng latency khi tải thấp |
| Idle event có nghĩa listener bị lỗi | Idle event chỉ cho biết container không nhận record trong khoảng thời gian đã cấu hình |

## Checklist

- Vòng lặp consumer tiếp tục gọi `poll()` khi chưa có record; không thoát sau một lần poll rỗng.
- Không dùng `poll(Duration.ZERO)` trong vòng lặp bận và không thêm sleep dài làm gián đoạn group polling.
- Phân biệt poll rỗng với tombstone hoặc record có payload rỗng.
- Hiểu khác biệt giữa `pollTimeout`, `max.poll.interval.ms`, `fetch.min.bytes` và `fetch.max.wait.ms`.
- Đã kiểm tra topic, partition assignment, consumer group, offset và producer send result.
- Đã xem xét `isolation.level` nếu producer sử dụng Kafka transaction.
- Dùng `ListenerContainerIdleEvent` khi cần nhận biết trạng thái idle trong Spring Kafka.
- Không chạy công việc chặn lâu trên thread consumer hoặc thread phát idle event.
- Cảnh báo idle dựa trên nhịp sự kiện và yêu cầu nghiệp vụ của từng topic.

Consumer không có dữ liệu là trạng thái bình thường trong một hệ thống event-driven. Điều quan trọng là tiếp tục duy trì vòng lặp poll, theo dõi assignment và offset, đồng thời phân biệt idle thật với cấu hình sai hoặc lỗi vận hành. Spring Kafka cung cấp idle event để ứng dụng quan sát trạng thái này mà không cần gọi listener bằng một message giả.
