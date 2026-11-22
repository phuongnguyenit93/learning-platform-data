# position, committed offset và bản ghi tiếp theo sẽ đọc

Kafka consumer theo dõi tiến độ đọc bằng hai khái niệm có liên quan nhưng khác nhau: **position** và **committed offset**. Position là vị trí đọc hiện tại trong bộ nhớ của consumer, thể hiện offset tiếp theo mà consumer sẽ lấy khi tiếp tục poll partition. Committed offset là checkpoint đã được lưu cho consumer group trong Kafka; khi consumer khởi động lại hoặc partition được giao cho thành viên khác, group dùng checkpoint này để tiếp tục.

Cả hai giá trị đều biểu thị **offset tiếp theo cần đọc**, không phải offset của record cuối cùng đã xử lý. Sự khác biệt nằm ở thời điểm và nơi lưu: position thay đổi trong phiên chạy khi consumer poll/seek, còn committed offset chỉ thay đổi khi offset được commit.

Hiểu rõ hai giá trị này giúp tránh hai lỗi phổ biến: commit quá sớm làm mất record khi ứng dụng lỗi, hoặc commit quá muộn khiến record đã xử lý bị đọc lại sau restart.

## 1. Position là gì?

Mỗi consumer duy trì position riêng cho từng partition đang được giao. Position là offset tiếp theo mà consumer sẽ dùng để đọc khi gọi poll. Khi consumer nhận các record từ một partition, position tiến lên sau các record đã được trả về.

Ví dụ partition có các record:

| Offset | Nội dung |
|---:|---|
| 10 | OrderCreated |
| 11 | PaymentConfirmed |
| 12 | OrderPacked |
| 13 | OrderShipped |

Consumer bắt đầu ở position 10. Sau khi poll trả về các record offset 10, 11 và 12, position của partition tiến đến 13. Nếu ứng dụng tiếp tục poll, consumer sẽ bắt đầu từ vị trí 13.

Điểm cần nhớ: position có thể đã tiến lên ngay sau khi poll trả record, trong khi ứng dụng vẫn đang xử lý batch đó. Vì vậy, position không chứng minh rằng mọi record trước vị trí đó đã được xử lý thành công.

~~~mermaid
flowchart LR
    A["Partition log<br/>10  11  12  13  14"] --> B["poll() trả về<br/>10, 11, 12"]
    B --> C["Position trong consumer<br/>13"]
    C --> D["Ứng dụng xử lý batch"]
    D --> E["Commit offset 13"]
    E --> F["Group checkpoint<br/>next offset = 13"]
~~~

Trong sơ đồ, position tiến đến 13 sau khi poll trả record. Sau khi ứng dụng xử lý xong batch, commit offset 13 lưu checkpoint để lần chạy sau tiếp tục từ vị trí này.

## 2. Committed offset là gì?

Committed offset là tiến độ đọc đã được consumer group lưu trong Kafka. Offset này được quản lý bởi group coordinator và lưu trong topic nội bộ **__consumer_offsets**.

Committed offset dùng để khôi phục tiến độ khi:

- Consumer restart sau khi tiến trình hoặc máy chủ gặp sự cố.
- Partition được rebalance và giao cho consumer khác trong cùng group.
- Ứng dụng chủ động dừng rồi khởi động lại.

Committed offset cũng biểu thị **vị trí tiếp theo cần đọc**. Ví dụ commit offset 13 có nghĩa consumer group đã xác nhận tiến độ đến trước vị trí 13 và khi khôi phục sẽ bắt đầu từ offset 13.

Committed offset được lưu theo cặp consumer group và topic-partition. Hai consumer group khác nhau đọc cùng topic có checkpoint độc lập.

| Khái niệm | Nơi lưu | Khi thay đổi | Mục đích |
|---|---|---|---|
| Position | Trạng thái runtime của consumer | Sau poll hoặc seek | Xác định vị trí đọc tiếp theo trong phiên hiện tại |
| Committed offset | Kafka, topic __consumer_offsets | Sau commit thành công | Khôi phục tiến độ của consumer group |

Một consumer có thể có position 20 nhưng committed offset vẫn là 15. Điều này có nghĩa consumer đã poll qua một số record, nhưng checkpoint bền vững mới chỉ đến 15. Nếu tiến trình dừng trước khi commit tiến độ mới, group có thể đọc lại từ offset 15.

## 3. Offset commit là offset tiếp theo, không phải record vừa xử lý

Đây là quy tắc quan trọng nhất khi làm việc với Kafka Consumer API:

**Nếu record có offset N đã được xử lý thành công và muốn lần sau đọc từ record kế tiếp, hãy commit N + 1.**

Ví dụ:

| Record vừa xử lý | Offset của record | Offset cần commit |
|---|---:|---:|
| Record A | 10 | 11 |
| Record B | 11 | 12 |
| Record C | 12 | 13 |

Nếu commit chính offset của record cuối cùng đã xử lý, consumer có thể đọc lại record đó sau restart. Nếu commit vượt quá vị trí đã xử lý, consumer có thể bỏ qua record chưa được xử lý.

Offset là số nguyên tăng theo partition, nhưng không phải mọi giá trị offset đều nhất thiết có record mà consumer nhìn thấy. Compaction, transaction control record hoặc record bị loại khỏi kết quả đọc theo isolation level có thể tạo khoảng trống. Vì vậy, “offset tiếp theo” là checkpoint trong log, không nhất thiết là số offset của một record đang tồn tại.

## 4. position(), committed() và commitSync() trong Java

KafkaConsumer cung cấp các API để đọc position, đọc committed offset và lưu checkpoint:

| API | Chức năng |
|---|---|
| position(partition) | Trả về position hiện tại, tức offset tiếp theo sẽ đọc |
| committed(partition) | Trả về OffsetAndMetadata đã commit cho group ở partition |
| commitSync() | Commit position hiện tại của các partition được giao |
| commitSync(offsets) | Commit các offset được chỉ định |
| commitAsync() | Gửi yêu cầu commit bất đồng bộ |
| seek(partition, offset) | Thay đổi position trong phiên consumer |
| seekToBeginning(partitions) | Đặt position về đầu log hiện còn của các partition |
| seekToEnd(partitions) | Đặt position về cuối log của các partition |

Ví dụ kiểm tra position và committed offset sau khi poll:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;

Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("group.id", "order-audit");
properties.put("key.deserializer", StringDeserializer.class.getName());
properties.put("value.deserializer", StringDeserializer.class.getName());
properties.put("enable.auto.commit", false);

try (KafkaConsumer<String, String> consumer =
         new KafkaConsumer<>(properties)) {
    consumer.subscribe(List.of("orders.events"));

    ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofSeconds(1));

    for (ConsumerRecord<String, String> record : records) {
        TopicPartition partition =
            new TopicPartition(record.topic(), record.partition());

        long position = consumer.position(partition);
        var committed = consumer.committed(partition);

        System.out.printf(
            "recordOffset=%d, position=%d, committed=%s%n",
            record.offset(),
            position,
            committed == null ? "none" : committed.offset()
        );

        // Xử lý nghiệp vụ record ở đây.
    }

    consumer.commitSync();
}
~~~

Đây là ví dụ minh họa API. Trong ứng dụng chạy liên tục, cần có vòng poll lặp, xử lý shutdown và quản lý rebalance. Đoạn code trên cho thấy position có thể đã ở sau batch được poll, còn committed offset có thể chưa thay đổi.

committed(partition) có thể trả về null nếu group chưa có committed offset cho partition đó. Khi đó, vị trí bắt đầu được xác định bởi auto.offset.reset hoặc được ứng dụng đặt bằng seek.

## 5. Auto commit và rủi ro xử lý chưa hoàn tất

Kafka consumer có thể tự commit offset khi **enable.auto.commit=true**. Khoảng thời gian giữa các lần commit được điều khiển bởi **auto.commit.interval.ms**.

~~~properties
enable.auto.commit=true
auto.commit.interval.ms=5000
~~~

Auto commit tiện cho trường hợp xử lý đơn giản, nhưng cần hiểu nó commit tiến độ consumer đã poll chứ không biết ứng dụng đã hoàn tất nghiệp vụ hay chưa.

Ví dụ ứng dụng dispatch record sang worker bất đồng bộ:

1. poll() trả về record offset 10 đến 19 và position tiến đến 20.
2. Ứng dụng gửi các record sang worker; worker mới xử lý xong offset 10 đến 14.
3. Vòng poll tiếp tục chạy trong khi worker còn xử lý offset 15 đến 19.
4. Chu kỳ auto commit kế tiếp lưu position 20.
5. Consumer restart và group tiếp tục từ 20.

Trong tình huống này, record 15 đến 19 có thể bị bỏ qua dù worker chưa xử lý xong. Rủi ro cũng xuất hiện nếu ứng dụng bắt lỗi xử lý nhưng vẫn tiếp tục poll, khiến auto commit lưu position đã tiến qua các record chưa hoàn tất. Với xử lý đồng bộ, không gọi poll tiếp cho đến khi batch hiện tại hoàn tất sẽ tránh được trường hợp cụ thể này; tuy vậy manual commit vẫn phù hợp hơn khi cần kiểm soát rõ ràng tiến độ nghiệp vụ.

Auto commit không có nghĩa Kafka commit ngay sau từng record. Consumer kiểm tra và thực hiện auto commit trong quá trình poll theo chu kỳ cấu hình. Vì vậy, ứng dụng phải bảo đảm các record của poll trước đã được xử lý xong trước khi tiếp tục poll theo cách có thể commit position đã tiến qua chúng.

Với nghiệp vụ cần kiểm soát chính xác, thường đặt enable.auto.commit=false và chỉ commit sau khi công việc tương ứng hoàn tất.

## 6. Manual commit với commitSync()

commitSync() gửi yêu cầu commit và chờ kết quả. Nếu không truyền offset, consumer commit position hiện tại của các partition được giao. Cách dùng phổ biến là xử lý toàn bộ batch vừa poll rồi mới commit.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.errors.WakeupException;
import org.apache.kafka.common.serialization.StringDeserializer;

Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("group.id", "billing-service");
properties.put("key.deserializer", StringDeserializer.class.getName());
properties.put("value.deserializer", StringDeserializer.class.getName());
properties.put("enable.auto.commit", false);

KafkaConsumer<String, String> consumer =
    new KafkaConsumer<>(properties);

try {
    consumer.subscribe(List.of("orders.events"));

    while (true) {
        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, String> record : records) {
            processOrderEvent(record);
        }

        // Chỉ commit sau khi toàn bộ batch poll này xử lý thành công.
        consumer.commitSync();
    }
} catch (WakeupException exception) {
    // WakeupException được dùng để đánh thức poll khi shutdown.
} finally {
    consumer.close();
}
~~~

Trong ví dụ, nếu processOrderEvent ném lỗi trước khi commit, offset batch không được commit ở cuối vòng lặp. Sau khi consumer khởi động lại hoặc partition được giao lại, các record chưa commit có thể được đọc lại. Điều này tạo ngữ nghĩa at-least-once nếu ứng dụng không bỏ qua lỗi và có thể xử lý lại an toàn.

commitSync() có thể ném exception nếu commit thất bại. Cần ghi nhận và xử lý lỗi commit; không được coi việc gọi phương thức là bằng chứng checkpoint đã được lưu.

## 7. Commit offset cụ thể sau khi xử lý từng record

Nếu cần kiểm soát theo partition, có thể tạo map TopicPartition đến OffsetAndMetadata. Offset commit phải là offset của record kế tiếp:

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

Map<TopicPartition, OffsetAndMetadata> offsets = new HashMap<>();

for (ConsumerRecord<String, String> record : records) {
    processOrderEvent(record);

    TopicPartition partition =
        new TopicPartition(record.topic(), record.partition());

    offsets.put(
        partition,
        new OffsetAndMetadata(record.offset() + 1)
    );
}

consumer.commitSync(offsets);
~~~

Đoạn code này chỉ an toàn khi các record của từng partition được xử lý tuần tự và mọi record trước offset được commit đều đã xử lý thành công. Nếu xử lý song song, không được commit offset lớn nhất đã hoàn tất khi còn record có offset nhỏ hơn chưa hoàn tất.

Ví dụ partition 0 có các record 10, 11, 12. Nếu record 12 xử lý xong trước nhưng record 11 còn chạy, commit offset 13 có thể khiến lần khởi động sau bỏ qua record 11. Khi xử lý song song, cần theo dõi các offset hoàn tất liên tiếp từ đầu và chỉ commit sau điểm liên tục đó.

## 8. commitAsync() và các lưu ý

commitAsync() gửi commit request mà không chặn luồng consumer chờ phản hồi. Có thể dùng callback để quan sát kết quả:

~~~java
consumer.commitAsync((offsets, exception) -> {
    if (exception != null) {
        // Ghi nhận commit thất bại và theo dõi nguyên nhân.
        return;
    }

    // Commit thành công.
});
~~~

Ưu điểm là giảm thời gian chờ commit trên luồng poll. Đổi lại, ứng dụng phải xử lý lỗi commit bất đồng bộ và tránh tự retry một commit cũ sau khi commit mới hơn đã thành công, vì điều đó có thể làm checkpoint lùi.

Một chiến lược thường dùng là:

- Dùng commitAsync() trong vòng xử lý bình thường để giảm độ trễ.
- Dùng commitSync() ở điểm kết thúc/shutdown hoặc trước khi nhường partition nếu cần xác nhận checkpoint cuối.
- Không thực hiện commit offset vượt qua các record chưa xử lý.

Lựa chọn cụ thể phụ thuộc cách ứng dụng xử lý batch, rebalance và yêu cầu độ trễ.

## 9. Seek thay đổi position, không tự commit checkpoint

seek() cho phép ứng dụng thay đổi vị trí đọc tiếp theo của consumer:

~~~java
TopicPartition partition = new TopicPartition("orders.events", 0);
consumer.assign(List.of(partition));

consumer.seek(partition, 100);
System.out.println(consumer.position(partition));
~~~

Sau seek(partition, 100), position được đặt về 100 trong phiên hiện tại. Lệnh này không tự ghi committed offset mới cho group. Nếu consumer dừng trước khi commit, lần chạy sau vẫn có thể khôi phục từ committed offset cũ.

Các thao tác thường dùng:

| API | Tác dụng |
|---|---|
| seek(partition, offset) | Đọc tiếp từ offset chỉ định |
| seekToBeginning(partitions) | Đặt về log start offset hiện có |
| seekToEnd(partitions) | Đặt về log end offset |
| position(partition) | Xem vị trí đọc tiếp theo trong phiên |
| committed(partition) | Xem checkpoint group đã lưu |

Sau khi tua lại bằng seek, nếu ứng dụng muốn lần chạy sau cũng tiếp tục từ vị trí mới, cần commit offset phù hợp. Ngược lại, nếu chỉ muốn replay tạm thời trong một phiên, có thể seek mà không commit để giữ checkpoint cũ.

## 10. auto.offset.reset chỉ dùng khi không có checkpoint hợp lệ

auto.offset.reset xác định cách consumer chọn vị trí ban đầu khi group chưa có committed offset hoặc committed offset không còn hợp lệ vì nằm ngoài phạm vi log hiện tại.

| Giá trị | Hành vi |
|---|---|
| earliest | Bắt đầu từ offset sớm nhất còn được giữ trong partition |
| latest | Bắt đầu từ cuối log hiện tại; chỉ nhận record mới sau thời điểm bắt đầu |
| none | Ném lỗi nếu không có committed offset hợp lệ |

Ví dụ:

~~~properties
group.id=order-projection
enable.auto.commit=false
auto.offset.reset=earliest
~~~

Nếu group đã có committed offset hợp lệ, consumer tiếp tục từ checkpoint đó; auto.offset.reset=earliest không tự tua group về đầu mỗi lần restart. Muốn replay, cần dùng seek hoặc thay đổi group/checkpoint theo quy trình rõ ràng.

Nếu committed offset nhỏ hơn log start offset do retention hoặc compaction đã loại dữ liệu cũ, offset đó không còn hợp lệ và reset policy có thể được áp dụng. Vì vậy, earliest nghĩa là đầu log còn lại, không nhất thiết là record đầu tiên từng được ghi vào topic.

## 11. Offset và rebalance trong consumer group

Trong consumer group, partition có thể được giao cho consumer khác khi instance tham gia/rời nhóm hoặc khi có thay đổi partition assignment. Consumer cần phối hợp commit offset trước khi mất quyền xử lý partition.

Với Java Consumer API, có thể đăng ký ConsumerRebalanceListener:

~~~java
consumer.subscribe(
    List.of("orders.events"),
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
            Collection<TopicPartition> partitions
        ) {
            // Hoàn tất công việc đang xử lý và commit offset an toàn.
            consumer.commitSync();
        }

        @Override
        public void onPartitionsAssigned(
            Collection<TopicPartition> partitions
        ) {
            // Có thể kiểm tra position/committed hoặc seek theo yêu cầu.
        }
    }
);
~~~

Đây là khung minh họa. Trong ứng dụng thật, chỉ commit các partition còn thuộc quyền sở hữu và các offset đã xử lý liên tục. Không được tiếp tục xử lý hoặc commit tùy tiện sau khi partition đã bị thu hồi.

Khi rebalance, committed offset là điểm khôi phục cho consumer mới. Nếu consumer cũ xử lý xong nhưng chưa commit trước khi mất partition, consumer mới có thể đọc lại record đó. Đây là hành vi bình thường của at-least-once; hệ thống đích cần xử lý idempotent nếu việc lặp lại gây tác dụng phụ.

## 12. Spring Kafka: AckMode và thời điểm commit

Trong Spring Kafka, listener container quản lý poll loop và commit offset. Thuộc tính AckMode xác định khi nào container commit dựa trên kết quả xử lý listener.

Với container-managed offset, thường đặt enable.auto.commit=false để Spring Kafka kiểm soát commit:

~~~yaml
spring:
  kafka:
    consumer:
      bootstrap-servers: localhost:9092
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    listener:
      ack-mode: batch
~~~

Các AckMode thường gặp:

| AckMode | Thời điểm commit |
|---|---|
| RECORD | Sau khi listener xử lý xong từng record |
| BATCH | Sau khi tất cả record từ một lần poll được xử lý |
| TIME | Khi đã qua khoảng thời gian cấu hình và batch đã được xử lý |
| COUNT | Khi đạt số lượng record cấu hình và batch đã được xử lý |
| COUNT_TIME | Khi đạt ngưỡng thời gian hoặc số lượng theo cấu hình |
| MANUAL | Listener gọi acknowledge; commit được thực hiện theo semantics batch của container |
| MANUAL_IMMEDIATE | Listener gọi acknowledge để yêu cầu commit ngay nếu thực hiện trên consumer thread; nếu gọi từ thread khác, việc commit được điều phối theo container |

RECORD phù hợp khi cần commit sau từng record và listener xử lý tuần tự. BATCH giảm số lần commit nhưng nếu record cuối batch lỗi, các record trước đó có thể được đọc lại tùy error handling. MANUAL/MANUAL_IMMEDIATE dành cho ứng dụng muốn quyết định thời điểm acknowledge.

Ví dụ listener dùng manual acknowledgment:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class BillingListener {

    @KafkaListener(
        topics = "orders.events",
        groupId = "billing-service"
    )
    public void onMessage(
        String event,
        Acknowledgment acknowledgment
    ) {
        processBilling(event);
        acknowledgment.acknowledge();
    }
}
~~~

Chỉ acknowledge sau khi xử lý nghiệp vụ đã hoàn tất theo semantics mà ứng dụng mong muốn. Nếu acknowledge trước rồi xử lý thất bại, record có thể bị bỏ qua sau restart.

## 13. Chọn commit strategy theo ngữ nghĩa giao nhận

Thời điểm commit quyết định ranh giới giữa khả năng đọc lại và nguy cơ bỏ qua record:

| Chiến lược | Thời điểm commit | Hệ quả khi ứng dụng lỗi |
|---|---|---|
| Commit trước xử lý | Trước khi thực hiện nghiệp vụ | Có thể mất xử lý nếu lỗi sau commit; gần với at-most-once |
| Commit sau xử lý | Sau khi nghiệp vụ hoàn tất | Có thể xử lý lặp nếu lỗi xảy ra trước commit; gần với at-least-once |
| Kafka transaction kết hợp offset | Ghi output và offset trong cùng Kafka transaction | Có thể đạt exactly-once semantics trong phạm vi Kafka transaction và consumer isolation phù hợp |

Exactly-once trong Kafka không tự mở rộng sang database hoặc API bên ngoài. Nếu consumer cập nhật database rồi commit offset Kafka, hai thao tác không nguyên tử nếu không có cơ chế phối hợp. Cần dùng idempotent write, inbox/deduplication, outbox hoặc transaction phù hợp với hệ thống đích.

## 14. Ví dụ đọc trạng thái trước khi quyết định replay

Khi điều tra một consumer bị dừng, hãy so sánh position và committed offset trong lúc consumer còn chạy hoặc log đã ghi nhận:

| Partition | Position | Committed offset | Diễn giải |
|---|---:|---:|---|
| 0 | 250 | 250 | Runtime position trùng checkpoint |
| 1 | 420 | 415 | Đã poll tiến thêm; có thể còn record chưa commit |
| 2 | 800 | 790 | Có khoảng cách lớn hơn giữa runtime và checkpoint |

Position chỉ tồn tại trong phiên consumer đang chạy. Sau khi consumer dừng, không thể khôi phục position cũ từ Kafka; group chỉ khôi phục committed offset. Bảng trên là ảnh chụp minh họa, không phải trạng thái có thể truy vấn lại sau khi tiến trình đã tắt.

Nếu muốn biết record tiếp theo mà consumer group sẽ đọc sau restart, hãy xem committed offset của group/partition. Nếu muốn biết consumer hiện tại sẽ lấy record nào ở lần poll tiếp theo, hãy xem position trong phiên chạy đó.

## 15. Consumer lag liên quan đến committed offset như thế nào?

Consumer lag thường được tính bằng khoảng cách giữa log end offset của partition và committed offset của consumer group. Nó cho biết group còn cách cuối log bao nhiêu offset theo checkpoint đã lưu.

Ví dụ:

| Partition | Log end offset | Committed offset | Lag minh họa |
|---|---:|---:|---:|
| 0 | 300 | 250 | 50 |
| 1 | 500 | 490 | 10 |

Lệnh kiểm tra group:

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group billing-service
~~~

Trên Windows, dùng kafka-consumer-groups.bat trong bin/windows.

Lag dựa trên committed offset có thể khác với lượng công việc còn đang xử lý trong ứng dụng. Nếu consumer đã poll nhiều record nhưng chưa commit, committed lag có thể lớn hơn phần record chưa được poll. Ngược lại, nếu auto commit tiến độ poll trong khi worker bất đồng bộ chưa xử lý xong, lag có thể thấp dù công việc thực tế vẫn còn tồn đọng.

Vì vậy, dashboard nên kết hợp consumer lag với position/current offset nếu ứng dụng có thể xuất metric, số record đang xử lý, thời gian xử lý và lỗi nghiệp vụ. Không dùng một con số lag duy nhất để kết luận consumer đã hoàn tất công việc.

## 16. Checklist xử lý offset an toàn

- Đặt group.id ổn định để checkpoint thuộc đúng consumer group.
- Hiểu rằng position và committed offset đều biểu thị vị trí tiếp theo cần đọc.
- Commit record.offset() + 1, không commit offset của record cuối cùng vừa xử lý.
- Tắt auto commit nếu cần kiểm soát commit theo kết quả nghiệp vụ.
- Chỉ commit sau khi mọi record trước checkpoint đã xử lý thành công.
- Khi xử lý song song, chỉ commit offset hoàn tất liên tục theo từng partition.
- Xử lý commit exception và rebalance; không coi lời gọi commit là thành công nếu chưa nhận kết quả.
- Dùng seek có chủ đích; nhớ seek không tự cập nhật committed offset.
- Cấu hình auto.offset.reset cho group chưa có checkpoint hoặc checkpoint không còn hợp lệ.
- Thiết kế xử lý idempotent nếu record có thể được đọc lại sau restart hoặc rebalance.
- Nếu cập nhật hệ thống ngoài Kafka, phối hợp offset với transaction/checkpoint của hệ thống đích.

## Kết luận

Position là offset tiếp theo consumer sẽ đọc trong phiên hiện tại; committed offset là checkpoint bền vững của consumer group, cũng chỉ vị trí tiếp theo cần đọc. Poll có thể làm position tiến lên trước khi ứng dụng xử lý xong, nên commit phải gắn với công việc đã hoàn tất. Khi xử lý record offset N thành công, checkpoint để tiếp tục ở record kế tiếp là N+1.

Java Consumer API cung cấp position(), committed(), commitSync(), commitAsync() và seek() để kiểm soát tiến độ. Spring Kafka cung cấp AckMode để container quyết định thời điểm commit. Chọn đúng chiến lược commit, phối hợp với rebalance và xử lý idempotent sẽ giúp consumer cân bằng giữa tránh mất record và chấp nhận replay an toàn.
