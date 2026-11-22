# Tìm offset theo timestamp bằng offsetsForTimes

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này hướng dẫn tìm vị trí đọc theo thời gian bằng Java Kafka Consumer API **offsetsForTimes()**.

Khi cần phát lại dữ liệu từ một thời điểm, bạn thường không biết trước offset tương ứng. offsetsForTimes() cho phép gửi timestamp mục tiêu cho từng partition và nhận về offset đầu tiên có timestamp lớn hơn hoặc bằng mốc yêu cầu theo cơ chế tra cứu của Kafka. Sau đó, ứng dụng dùng seek() để đặt vị trí đọc cho consumer.

Cần phân biệt hai thao tác: **offsetsForTimes() tra cứu vị trí**, còn **seek() thay đổi vị trí đọc của consumer**. Chỉ gọi offsetsForTimes() không làm consumer tự nhảy đến thời điểm đó và cũng không commit offset mới cho consumer group.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao replay theo thời gian cần tra cứu offset riêng cho từng partition.
- Sử dụng offsetsForTimes() với timestamp tính bằng milliseconds từ Unix epoch.
- Đọc và xử lý kết quả OffsetAndTimestamp, bao gồm trường hợp không tìm thấy kết quả.
- Dùng seek() để bắt đầu đọc từ offset tìm được.
- Phân biệt timestamp của Kafka record với thời gian nghiệp vụ nằm trong payload.
- Hiểu ảnh hưởng của CreateTime, LogAppendTime, retention, compaction và transaction.
- Kết hợp offsetsForTimes(), beginningOffsets() và endOffsets() để chọn chính sách khi không có kết quả.
- Thực hiện replay cho một topic có nhiều partition và kiểm soát commit offset.
- Nhận biết giới hạn khi cần truy vấn một khoảng thời gian hoặc cần thứ tự thời gian toàn cục.

## 2. Vì sao cần tìm offset theo timestamp?

Kafka định vị record bằng offset trong từng partition. Offset là số thứ tự vị trí trong log, còn timestamp biểu thị thời điểm gắn với record.

Giả sử topic **orders** có ba partition:

~~~text
orders-0:
  offset 100 -> timestamp 10:00
  offset 101 -> timestamp 10:02
  offset 102 -> timestamp 10:04

orders-1:
  offset 80  -> timestamp 10:01
  offset 81  -> timestamp 10:03
  offset 82  -> timestamp 10:05

orders-2:
  offset 40  -> timestamp 09:59
  offset 41  -> timestamp 10:02
  offset 42  -> timestamp 10:06
~~~

Nếu cần phát lại dữ liệu từ 10:02, offset bắt đầu của mỗi partition khác nhau:

| Partition | Timestamp mục tiêu | Offset bắt đầu |
|---|---|---:|
| orders-0 | 10:02 | 101 |
| orders-1 | 10:02 | 81 |
| orders-2 | 10:02 | 41 |

Không thể tìm một offset duy nhất rồi áp dụng cho mọi partition. Mỗi partition có log và dãy offset riêng.

Nếu dùng một group đã có tiến độ trước đó, consumer có thể đang ở offset 500 của partition 0 và offset 200 của partition 1. Muốn replay từ thời điểm khác, ứng dụng cần tra cứu offset mục tiêu cho từng partition rồi seek riêng từng partition.

## 3. offsetsForTimes() hoạt động như thế nào?

Java Kafka Consumer cung cấp phương thức:

~~~java
Map<TopicPartition, OffsetAndTimestamp> offsetsForTimes(
    Map<TopicPartition, Long> timestampsToSearch
);
~~~

Tham số là map gồm:

- Key: TopicPartition cần tra cứu.
- Value: timestamp mục tiêu tính bằng milliseconds từ Unix epoch.

Với mỗi partition, Kafka trả về OffsetAndTimestamp tương ứng với offset sớm nhất có timestamp lớn hơn hoặc bằng timestamp mục tiêu theo quy tắc timestamp lookup của Kafka.

Kết quả có các thông tin chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| TopicPartition | Partition được tra cứu, lấy từ key của map đầu vào. |
| OffsetAndTimestamp.offset() | Offset được tìm thấy. |
| OffsetAndTimestamp.timestamp() | Timestamp của record tại offset tìm được. |
| OffsetAndTimestamp.leaderEpoch() | Leader epoch gắn với kết quả, nếu client/broker version cung cấp. |

Nếu không tìm thấy offset phù hợp, giá trị tương ứng trong map kết quả là **null**. Ví dụ có thể xảy ra khi timestamp mục tiêu nằm sau timestamp của toàn bộ record hiện có trong partition.

Phương thức này là lời gọi đồng bộ: consumer chờ broker trả kết quả tra cứu. API có overload nhận Duration timeout trong các phiên bản client hỗ trợ.

**Consumer không cần được assign partition để gọi offsetsForTimes().** API tra cứu metadata offset trực tiếp theo TopicPartition. Tuy nhiên, để gọi seek() và poll dữ liệu từ partition, consumer phải sở hữu partition đó qua assign() hoặc subscribe() đã hoàn tất assignment.

Lời gọi có thể phát sinh lỗi nếu timestamp âm, request hết timeout, client không được cấp quyền đọc topic hoặc broker không hỗ trợ timestamp lookup. Các broker rất cũ có thể trả UnsupportedVersionException; record dùng message format cũ không có timestamp có thể cho kết quả null.

### 3.1. Timestamp phải là milliseconds

Java Instant biểu diễn thời gian rõ ràng và có thể chuyển sang epoch milliseconds:

~~~java
Instant targetTime = Instant.parse("2026-11-20T10:00:00Z");
long targetTimestamp = targetTime.toEpochMilli();
~~~

Không truyền trực tiếp:

- Unix seconds.
- Giá trị nano giây.
- Chuỗi ngày giờ chưa chuyển đổi.
- Số offset của partition.

Nếu truyền timestamp theo seconds thay vì milliseconds, giá trị thường nhỏ hơn mục tiêu hàng nghìn lần và kết quả lookup sẽ sai.

Nên dùng ISO-8601 với múi giờ rõ ràng, thường là UTC có hậu tố Z. Nếu thời gian đầu vào là giờ địa phương, hãy chuyển đổi đúng ZoneId trước khi gọi toEpochMilli().

### 3.2. Tra cứu không thay đổi vị trí đọc

Giả sử consumer đang ở position 500 trên partition orders-0. Bạn gọi offsetsForTimes() và nhận offset 120.

Vị trí đọc hiện tại không tự động trở thành 120. Phải gọi:

~~~java
consumer.seek(new TopicPartition("orders", 0), 120);
~~~

Sau seek(), lần poll tiếp theo sẽ bắt đầu đọc từ vị trí đã đặt, tùy trạng thái log và isolation level.

## 4. Kafka timestamp là thời gian nào?

offsetsForTimes() tra cứu theo timestamp của Kafka record. Đây không mặc định là thời điểm nghiệp vụ xảy ra trong hệ thống.

Kafka có hai loại timestamp thường gặp:

### 4.1. CreateTime

Với **CreateTime**, timestamp được gắn bởi producer khi tạo record. Thông thường nó gần với thời điểm producer phát sinh hoặc gửi event.

Ví dụ:

~~~java
ProducerRecord<String, String> record =
    new ProducerRecord<>(
        "orders",
        null,
        System.currentTimeMillis(),
        "ORD-1001",
        "OrderCreated"
    );
~~~

Ứng dụng có thể tự cung cấp timestamp khi tạo ProducerRecord.

CreateTime hữu ích khi cần tìm record theo thời gian producer tạo event. Tuy nhiên, cần chú ý:

- Đồng hồ giữa các producer có thể lệch.
- Producer có thể gửi record trễ.
- Một record được retry hoặc phát lại có thể mang timestamp cũ.
- Timestamp của record có thể không tăng đơn điệu theo offset.

### 4.2. LogAppendTime

Với **LogAppendTime**, broker gắn timestamp khi append record vào log. Timestamp phản ánh thời điểm broker nhận/ghi record theo cấu hình Kafka.

Loại timestamp này hữu ích khi cần truy vấn gần với thời điểm record đi vào Kafka. Nó không nhất thiết bằng thời điểm nghiệp vụ xảy ra hoặc thời điểm producer tạo event.

### 4.3. Chọn timestamp theo yêu cầu

| Yêu cầu | Timestamp nên xem xét |
|---|---|
| Tìm event theo thời điểm producer tạo/gửi | CreateTime |
| Tìm event theo thời điểm broker nhận record | LogAppendTime |
| Tìm event theo thời điểm nghiệp vụ xảy ra | Timestamp nghiệp vụ trong payload hoặc header được chuẩn hóa |
| Điều tra sự kiện gửi trễ | So sánh event time, CreateTime và LogAppendTime nếu hệ thống lưu đủ thông tin |

Nếu nghiệp vụ yêu cầu tìm theo eventTime nằm trong JSON hoặc Avro payload, offsetsForTimes() không tự đọc và tìm trường đó. API chỉ tra cứu timestamp metadata của Kafka record. Muốn tìm theo payload, cần có index riêng, Kafka Streams state/index, hệ thống lưu trữ truy vấn hoặc đọc và lọc dữ liệu.

## 5. Ví dụ Java: tìm offset cho một partition

Ví dụ dưới đây minh họa việc tra cứu timestamp cho partition orders-0:

~~~java
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndTimestamp;
import org.apache.kafka.common.TopicPartition;

import java.time.Instant;
import java.util.Map;

public class FindOffsetByTimestamp {

    public static void find(KafkaConsumer<String, String> consumer) {
        TopicPartition partition =
            new TopicPartition("orders", 0);

        long targetTimestamp =
            Instant.parse("2026-11-20T10:00:00Z").toEpochMilli();

        Map<TopicPartition, Long> request =
            Map.of(partition, targetTimestamp);

        Map<TopicPartition, OffsetAndTimestamp> result =
            consumer.offsetsForTimes(request);

        OffsetAndTimestamp match = result.get(partition);

        if (match == null) {
            System.out.println(
                "No record found at or after the requested timestamp"
            );
            return;
        }

        System.out.printf(
            "partition=%d offset=%d timestamp=%d%n",
            partition.partition(),
            match.offset(),
            match.timestamp()
        );
    }
}
~~~

Đoạn mã chỉ tra cứu offset. Nó không tự gán partition cho consumer và không thay đổi position. Nếu muốn gọi seek(), partition phải thuộc assignment hiện tại của consumer.

## 6. Ví dụ Java: replay từ timestamp trên nhiều partition

Trong ứng dụng replay, thường cần tra cứu cùng một timestamp trên tất cả partition của topic.

Ví dụ hoàn chỉnh dưới đây sử dụng assign() để chỉ định rõ partition. Cách này giúp tập trung vào offsetsForTimes() và seek() mà không cần chờ consumer group rebalance.

~~~java
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndTimestamp;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;

import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;

public class ReplayOrdersFromTimestamp {

    public static void main(String[] args) {
        Properties properties = new Properties();

        properties.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-replay-2026-11-20"
        );
        properties.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        properties.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        properties.put(
            ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
            false
        );
        properties.put(
            ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
            "earliest"
        );

        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(properties)) {

            List<TopicPartition> partitions = List.of(
                new TopicPartition("orders", 0),
                new TopicPartition("orders", 1),
                new TopicPartition("orders", 2)
            );

            // Gán partition thủ công để có thể seek trực tiếp.
            consumer.assign(partitions);

            long targetTimestamp =
                Instant.parse("2026-11-20T10:00:00Z").toEpochMilli();

            Map<TopicPartition, Long> timestampsToSearch =
                new HashMap<>();

            for (TopicPartition partition : partitions) {
                timestampsToSearch.put(
                    partition,
                    targetTimestamp
                );
            }

            Map<TopicPartition, OffsetAndTimestamp> matches =
                consumer.offsetsForTimes(timestampsToSearch);

            Map<TopicPartition, Long> endOffsets =
                consumer.endOffsets(partitions);

            for (TopicPartition partition : partitions) {
                OffsetAndTimestamp match = matches.get(partition);

                if (match == null) {
                    // Chính sách ví dụ: không có record phù hợp thì bắt đầu ở cuối log.
                    long endOffset = endOffsets.get(partition);
                    consumer.seek(partition, endOffset);

                    System.out.printf(
                        "%s-%d: no match; seek to end offset %d%n",
                        partition.topic(),
                        partition.partition(),
                        endOffset
                    );
                    continue;
                }

                consumer.seek(partition, match.offset());

                System.out.printf(
                    "%s-%d: seek offset=%d actualTimestamp=%d%n",
                    partition.topic(),
                    partition.partition(),
                    match.offset(),
                    match.timestamp()
                );
            }

            while (true) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofSeconds(1));

                for (ConsumerRecord<String, String> record : records) {
                    process(record);
                }

                if (!records.isEmpty()) {
                    // Commit sau khi batch đã được xử lý thành công.
                    consumer.commitSync();
                }
            }
        }
    }

    private static void process(
        ConsumerRecord<String, String> record
    ) {
        System.out.printf(
            "topic=%s partition=%d offset=%d timestamp=%d key=%s value=%s%n",
            record.topic(),
            record.partition(),
            record.offset(),
            record.timestamp(),
            record.key(),
            record.value()
        );

        // Thực hiện xử lý nghiệp vụ hoặc ghi sang hệ thống đích.
    }
}
~~~

Các điểm quan trọng:

- Mỗi partition có một entry timestamp trong map tra cứu.
- Timestamp mục tiêu giống nhau nhưng offset trả về có thể khác nhau.
- Nếu kết quả null, ví dụ chọn seek đến end offset để chờ dữ liệu mới.
- seek() đặt position cho từng partition.
- Auto commit bị tắt để ứng dụng kiểm soát tiến độ.
- commitSync() chỉ chạy sau khi batch xử lý thành công.

Đây là mẫu minh họa cho replay. Ứng dụng production cần bổ sung shutdown, retry, xử lý lỗi từng record, giới hạn thời gian replay và chính sách commit phù hợp. Với dữ liệu quan trọng, nên dùng một group ID riêng cho job replay để tránh thay đổi tiến độ của consumer group đang phục vụ luồng chính.

## 7. Dùng subscribe() thay cho assign()

Trong ứng dụng consumer group thông thường, bạn thường gọi subscribe() để Kafka tự phân phối partition.

Vì assignment được hoàn tất bất đồng bộ qua group coordination, cần poll để nhận partition trước khi seek:

~~~java
import java.util.Set;

consumer.subscribe(List.of("orders"));

while (consumer.assignment().isEmpty()) {
    consumer.poll(Duration.ofMillis(100));
}

Set<TopicPartition> assigned = consumer.assignment();
~~~

Sau khi có assignment:

1. Tạo map timestamp cho các partition được gán.
2. Gọi offsetsForTimes().
3. Gọi seek() cho từng partition có kết quả.
4. Tiếp tục poll để đọc từ vị trí mới.

Cần chú ý poll trong giai đoạn chờ assignment có thể trả về record. Nếu ứng dụng chỉ dùng poll để hoàn tất assignment, hãy thiết kế rõ cách xử lý các record trả về trước khi seek. Với một job replay cần kiểm soát hoàn toàn điểm bắt đầu, có thể dùng assign() hoặc ConsumerRebalanceListener để áp dụng timestamp seek khi partition được gán.

### 7.1. Seek lại sau rebalance

Khi dùng subscribe(), partition có thể bị thu hồi rồi giao lại. Nếu yêu cầu của ứng dụng là mỗi lần nhận partition đều bắt đầu từ timestamp mục tiêu, hãy lưu timestamp mục tiêu và thực hiện offsetsForTimes() rồi seek() trong logic xử lý assignment mới.

Không nên giả định vị trí seek trước rebalance luôn được giữ sau khi partition được giao lại. Consumer có thể khôi phục position theo committed offset hoặc reset policy khi nhận assignment mới.

Nếu chỉ muốn replay một lần rồi tiếp tục theo committed offset bình thường, cần xác định rõ thời điểm chuyển từ replay position sang tiến độ group và commit offset sau khi xử lý thành công.

## 8. Xử lý khi offsetsForTimes() trả về null

Giá trị null không nên bị bỏ qua tùy tiện. Ứng dụng phải chọn chính sách rõ ràng theo mục tiêu replay.

Một số tình huống:

- Timestamp mục tiêu nằm sau timestamp của tất cả record hiện có.
- Partition chưa có record.
- Dữ liệu còn lại không có timestamp phù hợp.
- Timestamp mục tiêu vượt qua phạm vi dữ liệu mà partition đang giữ.

Có ba lựa chọn phổ biến:

| Chính sách | Hành động | Khi phù hợp |
|---|---|---|
| Bắt đầu ở cuối log | seek(endOffsets.get(partition)) | Chỉ muốn nhận record mới từ thời điểm hiện tại trở đi. |
| Bắt đầu từ đầu dữ liệu còn giữ | seek(beginningOffsets.get(partition)) | Muốn xử lý toàn bộ dữ liệu còn tồn tại trong partition. |
| Báo lỗi hoặc bỏ qua partition | Không seek và ghi nhận trạng thái | Job replay cần kết quả chính xác, không được tự quyết định thay người vận hành. |

Ngoài trường hợp không có record nào đạt timestamp mục tiêu, kết quả null cũng có thể xuất hiện khi partition chứa message format cũ không có timestamp hoặc broker/client không thể cung cấp timestamp lookup theo phiên bản đang chạy. Hãy phân biệt kết quả null với exception do timeout, xác thực hoặc broker không hỗ trợ API.

Ví dụ lấy beginning và end offset:

~~~java
Map<TopicPartition, Long> beginnings =
    consumer.beginningOffsets(partitions);

Map<TopicPartition, Long> ends =
    consumer.endOffsets(partitions);
~~~

- beginningOffsets() trả về vị trí sớm nhất còn có thể đọc.
- endOffsets() trả về vị trí cuối theo cách biểu diễn exclusive, tức offset kế tiếp nơi record mới có thể được ghi.

Nếu chọn replay toàn bộ dữ liệu còn giữ, seek đến beginning offset. Nếu chọn bỏ qua lịch sử và đợi dữ liệu mới, seek đến end offset.

Không dùng offset 0 như một giá trị mặc định cho mọi partition. Retention có thể làm beginning offset lớn hơn 0.

## 9. Retention và giới hạn của replay theo thời gian

Kafka chỉ có thể phát lại record còn tồn tại trong log. Nếu retention đã xóa các segment cũ, offsetsForTimes() không thể khôi phục dữ liệu đã bị xóa.

Ví dụ:

~~~text
Trước retention:
  offset 0 -> 08:00
  offset 1 -> 08:10
  offset 2 -> 08:20
  offset 3 -> 08:30

Sau retention:
  beginning offset = 2
  offset 2 -> 08:20
  offset 3 -> 08:30
~~~

Nếu yêu cầu replay từ 08:05, record offset 1 đã bị xóa. Kafka chỉ có thể trả về vị trí phù hợp trong phần log còn tồn tại. Kết quả có thể bắt đầu tại offset 2; không thể lấy lại offset 1 từ Kafka.

Để đánh giá phạm vi dữ liệu còn giữ, nên kết hợp:

- beginningOffsets() của từng partition.
- Kết quả offsetsForTimes().
- Timestamp thực tế của record đầu tiên có thể đọc.
- Chính sách retention và trạng thái compaction của topic.

Nếu kết quả lookup trùng beginning offset và timestamp record đầu tiên lớn hơn timestamp yêu cầu, đó là dấu hiệu không có record cũ hơn trong log hiện tại. Tuy nhiên, điều đó không tự chứng minh retention đã xóa dữ liệu; có thể đơn giản là không có event nào được ghi trong khoảng thời gian đó.

## 10. Log compaction và timestamp lookup

Với topic bật log compaction, Kafka có thể loại bỏ các record cũ hơn theo key trong quá trình compaction. Offset của record còn lại không được đánh lại từ 0.

Vì vậy:

- Một số offset có thể không còn record dữ liệu tương ứng.
- offsetsForTimes() chỉ có thể tìm trong log hiện tại.
- Replay không thể khôi phục phiên bản cũ của key đã bị compaction loại bỏ.
- Nếu cần lịch sử đầy đủ của mọi thay đổi, topic compacted đơn thuần có thể không đáp ứng yêu cầu đó.

Topic dùng delete retention, compact hoặc compact,delete có đặc tính lưu trữ khác nhau. Hãy xác định retention policy trước khi hứa hẹn khả năng replay theo thời gian.

## 11. Timestamp không tạo thứ tự toàn cục

offsetsForTimes() tra cứu độc lập theo từng partition. Nếu cùng timestamp được gửi cho ba partition, mỗi partition có thể trả về một offset khác nhau.

Không thể so sánh các offset đó để kết luận record nào xảy ra trước trên toàn topic.

Ngoài ra, timestamp record có thể không tăng đơn điệu theo offset, đặc biệt khi dùng CreateTime:

- Đồng hồ producer lệch nhau.
- Event đến Kafka không theo thứ tự thời gian nghiệp vụ.
- Producer gửi lại event cũ.
- Event được tạo từ nhiều hệ thống khác nhau.

Nếu cần sắp xếp theo event time trên toàn topic, consumer cần đọc dữ liệu từ các partition rồi áp dụng chiến lược merge theo timestamp, watermark hoặc quy tắc nghiệp vụ. Không thể dựa vào offset giữa các partition để tạo thứ tự toàn cục.

Với truy vấn một khoảng thời gian, hãy cẩn thận khi dừng đọc ở record đầu tiên có timestamp vượt quá thời điểm kết thúc. Điều đó chỉ an toàn nếu hệ thống bảo đảm timestamp theo offset không giảm trong partition. Nếu timestamp có thể đi lùi, cần tiếp tục scan theo chính sách phù hợp và lọc theo event time, hoặc duy trì index riêng.

## 12. Replay một khoảng thời gian

Giả sử muốn đọc event trong khoảng:

~~~text
[startTime, endTime)
~~~

Một cách triển khai là tra cứu offset tại startTime cho từng partition, seek đến các vị trí đó rồi đọc và lọc record theo timestamp cho đến khi đạt điều kiện kết thúc.

Với từng partition:

1. Gọi offsetsForTimes(startTime).
2. Nếu có kết quả, seek đến offset tìm được.
3. Poll record.
4. Kiểm tra record.timestamp().
5. Chỉ xử lý record nằm trong khoảng thời gian mong muốn.
6. Dừng partition theo quy tắc kết thúc đã xác định.

Nếu timestamp trong partition được bảo đảm không giảm theo offset, có thể dùng offsetsForTimes(endTime) như ranh giới offset kết thúc cho partition. Nếu timestamp không đơn điệu, không nên giả định một offset kết thúc duy nhất bao phủ mọi record có timestamp nhỏ hơn endTime. Cần scan và lọc theo chính sách dữ liệu hoặc thiết kế index theo event time.

Đặc biệt, nếu timestamp nghiệp vụ nằm trong payload, phải deserialize và lọc trường nghiệp vụ đó. Timestamp metadata của Kafka không thay thế timestamp nghiệp vụ.

## 13. CLI: tra cứu offset theo timestamp

Một số bản Kafka cung cấp script **kafka-get-offsets** để tra cứu offset theo thời gian.

Ví dụ dùng epoch milliseconds:

Linux hoặc macOS:

~~~bash
bin/kafka-get-offsets.sh \
  --bootstrap-server localhost:9092 \
  --topic orders \
  --time 1795168800000
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-get-offsets.bat --bootstrap-server localhost:9092 --topic orders --time 1795168800000
~~~

Giá trị --time là timestamp milliseconds. Các giá trị đặc biệt -1 và -2 thường lần lượt yêu cầu latest và earliest offset; hãy kiểm tra trợ giúp của script trong phiên bản Kafka đang sử dụng.

CLI hữu ích để kiểm tra nhanh kết quả lookup. Trong ứng dụng Java, offsetsForTimes() cho phép lấy kết quả cho nhiều partition và kết hợp trực tiếp với seek().

Không nhầm kết quả latest offset với offset của record cuối cùng. End offset là vị trí kế tiếp, nên nếu record cuối có offset 100 thì end offset thường là 101.

## 14. Commit offset sau khi replay

Sau khi seek đến offset theo timestamp, consumer đang có position mới trong bộ nhớ client. Vị trí đó không tự động thay đổi committed offset của group.

Ví dụ:

~~~text
Committed offset trước replay = 500
Timestamp lookup trả về offset = 120
consumer.seek(partition, 120)

Consumer bắt đầu đọc từ offset 120.
Committed offset vẫn có thể là 500 cho đến khi ứng dụng commit tiến độ mới.
~~~

Nếu consumer restart trước khi commit, group có thể tiếp tục từ committed offset cũ thay vì offset replay 120.

Các lựa chọn thiết kế:

- Dùng group ID riêng cho job replay để không ảnh hưởng consumer group chính.
- Dùng group hiện tại và commit tiến độ replay có chủ đích.
- Lưu checkpoint replay ở hệ thống quản lý job riêng.
- Sau replay, quyết định rõ có tiếp tục từ vị trí replay hay quay lại luồng chính.

Không chạy replay trên cùng group đang phục vụ production mà không hiểu tác động lên committed offsets. Một job replay có thể làm thay đổi vị trí đọc của group và khiến consumer đang hoạt động đọc lại hoặc bỏ qua dữ liệu tùy cách phối hợp.

## 15. Isolation level khi replay dữ liệu transactional

Nếu topic có record được ghi bằng Kafka transaction, consumer cần chọn isolation level phù hợp.

- **read_uncommitted:** có thể đọc record thuộc transaction chưa hoàn tất hoặc đã abort, trong phạm vi dữ liệu broker cho phép.
- **read_committed:** chỉ trả về record không thuộc transaction hoặc thuộc transaction đã commit; bỏ qua record thuộc transaction bị abort và không đọc vượt qua Last Stable Offset.

Nếu mục tiêu replay là tái tạo các sự kiện nghiệp vụ đã commit, thường nên dùng read_committed.

Timestamp lookup và isolation level là hai khái niệm riêng. offsetsForTimes() tìm vị trí theo timestamp; isolation.level quyết định record transactional nào được trả về khi poll.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| offsetsForTimes() trả về null | Không có record phù hợp ở hoặc sau timestamp yêu cầu. | Chọn rõ chính sách end, beginning hoặc báo lỗi. |
| Kết quả lệch hàng nghìn lần | Truyền epoch seconds thay vì milliseconds. | Dùng Instant.toEpochMilli(). |
| seek() báo partition chưa được gán | Consumer chưa assign hoặc subscribe chưa hoàn tất rebalance. | Gọi assign() hoặc poll đến khi có assignment rồi seek(). |
| Restart xong không replay từ timestamp | Chỉ gọi seek() nhưng chưa commit hoặc không dùng group riêng. | Thiết kế checkpoint và committed offset rõ ràng. |
| Replay thiếu dữ liệu cũ | Retention hoặc compaction đã loại bỏ record. | Kiểm tra beginning offset, timestamp record và retention policy. |
| Replay sai thời gian nghiệp vụ | Kafka record timestamp khác eventTime trong payload. | Dùng event time đã chuẩn hóa và lọc payload hoặc index riêng. |
| Thứ tự record không đúng theo thời gian | CreateTime không đơn điệu hoặc event đến trễ. | Không suy ra thứ tự toàn cục từ offset; áp dụng merge/watermark phù hợp. |
| Consumer đọc record transactional chưa commit | Consumer dùng read_uncommitted. | Dùng read_committed nếu chỉ cần dữ liệu đã commit. |
| Consumer group chính bị thay đổi tiến độ | Job replay dùng chung group ID và commit offset. | Dùng group ID riêng hoặc phối hợp checkpoint có kiểm soát. |

## 17. Checklist triển khai replay theo timestamp

Trước khi chạy replay, hãy xác nhận:

1. Timestamp đầu vào đã chuyển sang epoch milliseconds chưa?
2. Múi giờ và nguồn thời gian đã được xác định chưa?
3. Kafka record đang dùng CreateTime hay LogAppendTime?
4. Yêu cầu dựa trên Kafka timestamp hay event time trong payload?
5. Đã lấy đầy đủ danh sách partition của topic chưa?
6. Đã gọi offsetsForTimes() riêng cho từng partition chưa?
7. Đã định nghĩa chính sách khi kết quả null chưa?
8. Đã kiểm tra beginning offset và retention chưa?
9. Đã quyết định read_committed hay read_uncommitted chưa?
10. Đã dùng group ID riêng nếu replay không được phép ảnh hưởng group chính chưa?
11. Đã xác định cách commit checkpoint và resume sau lỗi chưa?
12. Đã tính đến timestamp không đơn điệu và event đến trễ chưa?
13. Đã giới hạn tốc độ replay để không gây quá tải hệ thống đích chưa?
14. Đã ghi log timestamp yêu cầu, partition, offset tìm được và timestamp thực tế chưa?

## 18. Bài tập thực hành

### Bài 1: Tra cứu offset trên từng partition

Tạo topic **orders-replay-lab** có ba partition. Gửi record với timestamp khác nhau vào từng partition.

1. Ghi lại timestamp mục tiêu theo ISO-8601.
2. Chuyển timestamp sang epoch milliseconds.
3. Tạo map TopicPartition -> timestamp.
4. Gọi offsetsForTimes().
5. In partition, offset và timestamp trả về.
6. So sánh offset giữa ba partition.
7. Giải thích vì sao không thể dùng một offset chung cho cả topic.

### Bài 2: Seek và replay

1. Gán ba partition cho consumer bằng assign().
2. Gọi offsetsForTimes() với timestamp mục tiêu.
3. Gọi seek() cho từng partition có kết quả.
4. Poll và in record.
5. Tắt auto commit.
6. Xử lý một batch và commitSync() sau khi hoàn tất.
7. Khởi động lại consumer và quan sát vị trí đọc theo committed offset.

### Bài 3: Xử lý kết quả null

Thử ba timestamp:

- Một timestamp trước record cũ nhất còn giữ.
- Một timestamp nằm giữa các record.
- Một timestamp sau record mới nhất.

Ghi lại kết quả offsetsForTimes() và so sánh với beginningOffsets() và endOffsets(). Đề xuất chính sách phù hợp cho từng trường hợp.

### Bài 4: CreateTime và LogAppendTime

1. Tạo hai topic lab với timestamp policy khác nhau nếu môi trường cho phép.
2. Gửi record có timestamp producer được kiểm soát.
3. Đọc record và in record.timestamp().
4. Gọi offsetsForTimes() cùng một timestamp mục tiêu.
5. So sánh kết quả và giải thích sự khác nhau giữa thời điểm producer tạo record và thời điểm broker append.

### Bài 5: Replay có giới hạn thời gian

1. Chọn startTime và endTime.
2. Tra cứu offset bắt đầu trên mỗi partition.
3. Seek đến offset bắt đầu.
4. Đọc record và lọc timestamp.
5. Thử tạo event có CreateTime đi lùi để thấy vì sao không thể luôn dừng ở record đầu tiên vượt endTime.
6. Đề xuất cách scan hoặc index phù hợp với yêu cầu nghiệp vụ.

## 19. Câu hỏi tự kiểm tra

1. offsetsForTimes() nhận map có kiểu dữ liệu gì?
2. Timestamp đầu vào phải tính theo đơn vị nào?
3. OffsetAndTimestamp chứa những thông tin chính nào?
4. Vì sao kết quả offsetsForTimes() có thể là null?
5. offsetsForTimes() có tự thay đổi consumer position không?
6. Vì sao cần gọi seek() sau khi tìm được offset?
7. Tại sao mỗi partition phải được tra cứu riêng?
8. CreateTime và LogAppendTime khác nhau như thế nào?
9. Vì sao timestamp Kafka không nhất thiết bằng event time trong payload?
10. Retention ảnh hưởng khả năng replay như thế nào?
11. Vì sao committed offset không tự thay đổi sau seek()?
12. Dùng group ID riêng có lợi ích gì khi chạy replay?
13. read_committed ảnh hưởng dữ liệu poll như thế nào?
14. Vì sao timestamp không đơn điệu làm replay một khoảng thời gian phức tạp hơn?
15. Khi không tìm thấy offset, ứng dụng nên chọn chính sách nào?

## Kết luận

offsetsForTimes() giúp tìm offset bắt đầu theo timestamp của Kafka record trên từng partition. Timestamp phải được truyền bằng epoch milliseconds; kết quả là OffsetAndTimestamp hoặc null nếu không tìm thấy vị trí phù hợp. Sau khi tra cứu, ứng dụng cần gọi seek() để thay đổi vị trí đọc.

Replay theo timestamp chỉ có thể đọc dữ liệu còn tồn tại trong log và phụ thuộc loại timestamp của record. CreateTime có thể lệch do đồng hồ producer hoặc event đến trễ; LogAppendTime phản ánh thời điểm broker append. Timestamp trong payload nghiệp vụ không tự động được offsetsForTimes() tra cứu.

Khi triển khai replay, hãy xử lý null rõ ràng, kiểm tra retention, chọn isolation level, dùng group ID phù hợp và commit checkpoint có chủ đích. Với nhiều partition, mỗi partition có offset riêng; không thể suy ra thứ tự toàn cục chỉ từ offset hoặc timestamp.

## Tài liệu tham khảo

- [Apache Kafka 4.2 Java API — KafkaConsumer](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| offsetsForTimes() | Tra cứu offset theo timestamp cho từng TopicPartition. |
| TopicPartition | Định danh một partition bằng topic và partition number. |
| OffsetAndTimestamp | Kết quả gồm offset và timestamp của record tìm được. |
| Epoch milliseconds | Số milliseconds tính từ Unix epoch. |
| CreateTime | Timestamp do producer gắn vào record. |
| LogAppendTime | Timestamp do broker gắn khi append record. |
| seek() | Đặt vị trí đọc tiếp theo của consumer cho một partition đã được gán. |
| beginningOffsets() | Lấy vị trí sớm nhất còn có thể đọc của partition. |
| endOffsets() | Lấy vị trí cuối exclusive của partition. |
| Retention | Chính sách giữ và xóa dữ liệu log. |
| Log compaction | Cơ chế giữ dữ liệu theo key và có thể loại bỏ record cũ. |
| Replay | Đọc lại dữ liệu từ một vị trí hoặc thời điểm đã xác định. |
| read_committed | Chỉ trả về record ngoài transaction hoặc thuộc transaction đã commit. |
| Event time | Thời điểm nghiệp vụ mà sự kiện thực sự xảy ra. |

