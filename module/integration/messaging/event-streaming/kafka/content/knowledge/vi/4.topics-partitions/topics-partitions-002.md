# Offset chỉ có ý nghĩa trong từng partition

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, từ topic, partition, offset, producer và consumer group đến replication, KRaft, Java/Spring Kafka, retry, ordering, giao dịch, Kafka Connect/Streams và vận hành cụm. Bài học này tập trung vào một nguyên tắc nền tảng: **offset là vị trí của record bên trong một partition cụ thể, không phải số thứ tự chung của toàn bộ topic**.

Hiểu đúng phạm vi của offset giúp bạn đọc dữ liệu chính xác, theo dõi tiến độ consumer group, tính consumer lag và thiết kế xử lý theo thứ tự. Nếu nhầm offset giữa các partition như một dòng thời gian toàn cục, ứng dụng có thể đưa ra kết luận sai về thứ tự sự kiện hoặc trạng thái xử lý.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Định nghĩa offset và xác định phạm vi của một offset.
- Giải thích vì sao hai partition có thể cùng chứa record mang offset bằng nhau.
- Phân biệt thứ tự record trong một partition với thứ tự giữa nhiều partition.
- Hiểu mối quan hệ giữa topic, partition, offset và consumer group.
- Giải thích offset đã commit thường biểu thị vị trí tiếp theo mà consumer sẽ đọc.
- Phân biệt offset với số lượng record, ID nghiệp vụ và timestamp.
- Quan sát offset bằng Kafka CLI và Java Kafka Consumer API.
- Nhận biết ảnh hưởng của retention, log compaction và transaction đến các offset nhìn thấy được.

## 2. Offset là gì?

Kafka lưu record trong từng partition dưới dạng một log chỉ ghi nối tiếp. Khi một record được ghi vào partition, Kafka gán cho nó một **offset** để xác định vị trí của record trong log đó.

Offset có các đặc điểm:

- Là một số nguyên tăng theo vị trí ghi trong một partition.
- Được xác định riêng cho từng partition.
- Được dùng để consumer định vị record và lưu tiến độ đọc.
- Không đại diện cho thứ tự toàn cục giữa các partition.
- Không phải ID nghiệp vụ của event và không phải số lượng record đã xử lý.

Hãy hình dung một topic tên là **orders.events** có hai partition. Mỗi partition là một log độc lập:

~~~text
Topic: orders.events

Partition 0:
Offset 0 -> OrderCreated(ORD-1001)
Offset 1 -> PaymentAuthorized(ORD-1001)
Offset 2 -> OrderCreated(ORD-1002)

Partition 1:
Offset 0 -> OrderCreated(ORD-2001)
Offset 1 -> OrderCancelled(ORD-2001)
Offset 2 -> PaymentAuthorized(ORD-2001)
~~~

Offset 0 xuất hiện trong cả partition 0 và partition 1. Hai record này không phải cùng một record. Chúng nằm ở hai log khác nhau và có vị trí riêng trong từng log.

Vì thế, khi nói một record có offset 2, thông tin đó chưa đủ để xác định vị trí. Cần biết nó thuộc topic nào và partition nào. Có thể biểu diễn vị trí bằng bộ ba:

**(topic, partition, offset)**

Ví dụ:

- (orders.events, 0, 2)
- (orders.events, 1, 2)

Đây là hai vị trí khác nhau dù offset cùng bằng 2.

## 3. Vì sao mỗi partition có offset riêng?

Kafka chia topic thành các partition để phân phối dữ liệu và tải xử lý trên nhiều broker. Mỗi partition có log, leader và tiến độ ghi riêng. Producer có thể gửi record đến các partition khác nhau, còn consumer có thể đọc từng partition độc lập hoặc song song.

Nếu Kafka sử dụng một bộ đếm offset chung cho toàn topic, việc ghi song song vào nhiều partition sẽ cần một cơ chế điều phối thứ tự chung. Điều đó không phù hợp với mục tiêu phân tán và mở rộng của mô hình partition. Thay vào đó, Kafka quản lý vị trí record độc lập trong từng partition.

Sơ đồ dưới đây minh họa hai log riêng:

~~~mermaid
flowchart TB
    T[Topic: orders.events]
    T --> P0[Partition 0]
    T --> P1[Partition 1]
    P0 --> A0[Offset 0]
    P0 --> A1[Offset 1]
    P0 --> A2[Offset 2]
    P1 --> B0[Offset 0]
    P1 --> B1[Offset 1]
    P1 --> B2[Offset 2]
~~~

Trong sơ đồ:

- Partition 0 có thứ tự riêng: 0 → 1 → 2.
- Partition 1 cũng có thứ tự riêng: 0 → 1 → 2.
- Không có căn cứ để kết luận record ở partition 0, offset 2 xảy ra trước hoặc sau record ở partition 1, offset 1 chỉ dựa vào các con số offset.

Producer có thể gửi record đến các partition theo key hoặc partitioner. Các partition tiếp nhận record độc lập, nên offset trong partition không thể dùng để sắp xếp mọi record của topic.

## 4. Offset cho biết điều gì và không cho biết điều gì?

### 4.1. Offset cho biết vị trí trong log

Khi consumer nhận một record, metadata của record có thể cho biết topic, partition, offset, key, value, timestamp và các header.

Ví dụ một record có metadata:

| Trường | Giá trị |
|---|---|
| Topic | orders.events |
| Partition | 1 |
| Offset | 42 |
| Key | ORD-2001 |
| Value | PaymentAuthorized |
| Timestamp | 2026-11-20T10:15:30Z |

Vị trí của record là **(orders.events, 1, 42)**. Nếu cần truy vết hoặc yêu cầu consumer đọc lại vị trí này, ứng dụng cần giữ đầy đủ topic, partition và offset.

### 4.2. Offset không phải số thứ tự toàn cục

Không thể so sánh hai offset ở hai partition khác nhau để kết luận record nào được ghi trước trên toàn topic.

| Record | Partition | Offset |
|---|---:|---:|
| A: OrderCreated | 0 | 15 |
| B: PaymentAuthorized | 1 | 8 |
| C: ShipmentRequested | 0 | 16 |
| D: OrderCancelled | 1 | 15 |

Ta có thể kết luận A được ghi trước C trong partition 0, và B được ghi trước D trong partition 1. Nhưng không thể kết luận A xảy ra trước B chỉ vì 15 lớn hơn 8. Hai offset thuộc hai log độc lập.

### 4.3. Offset không phải số lượng record

Offset thường tăng theo vị trí ghi, nhưng không nên coi offset là số lượng record đang tồn tại hoặc số lượng record mà consumer đã xử lý.

Một số nguyên nhân khiến các offset quan sát được không liên tục:

- Retention xóa các segment cũ. Log start offset có thể tăng, trong khi offset của các record còn lại không được đánh lại từ 0.
- Log compaction giữ lại một số record theo key và có thể loại bỏ các record cũ hơn, tạo khoảng trống giữa những offset còn đọc được.
- Transaction bị abort hoặc các control record có thể khiến một số vị trí không xuất hiện như record dữ liệu thông thường đối với consumer.
- Consumer sử dụng chế độ chỉ đọc các transaction đã commit có thể bỏ qua record thuộc transaction bị abort.

Do đó, nếu thấy offset 10 rồi đến offset 13, không thể kết luận chắc chắn rằng hai record đã bị mất. Hãy xem trạng thái log, isolation level, retention và compaction trước khi chẩn đoán.

### 4.4. Offset không phải timestamp

Offset biểu thị vị trí trong log, còn timestamp biểu thị thời điểm gắn với record theo cấu hình timestamp của Kafka.

Hai record thuộc hai partition có timestamp gần nhau hoặc bằng nhau vẫn không tạo ra một thứ tự toàn cục đáng tin cậy. Đồng hồ của các producer có thể lệch, record có thể được gửi trễ và timestamp có thể là thời điểm tạo hoặc thời điểm broker nhận tùy cấu hình.

Nếu nghiệp vụ cần biết thời điểm sự kiện xảy ra, hãy đưa thời điểm nghiệp vụ vào event payload hoặc dùng timestamp theo hợp đồng đã thống nhất. Không suy ra thời gian thực tế từ offset.

## 5. Thứ tự được bảo đảm trong phạm vi nào?

Kafka bảo đảm thứ tự record trong một partition theo thứ tự chúng được ghi vào partition đó. Consumer đọc một partition theo thứ tự offset. Khi topic có nhiều partition, mỗi partition vẫn giữ thứ tự riêng, nhưng Kafka không cung cấp một thứ tự tổng thể tự động cho tất cả record trong topic.

Ví dụ, một đơn hàng có ba sự kiện:

1. OrderCreated
2. PaymentAuthorized
3. ShipmentRequested

Nếu cả ba record dùng cùng key là **orderId=ORD-1001** và partitioner định tuyến chúng vào cùng partition, consumer có thể đọc chúng theo thứ tự ghi trong partition đó.

Nếu các event của cùng đơn hàng bị gửi vào các partition khác nhau, consumer không thể dùng offset để xác định thứ tự giữa chúng. Ứng dụng phải có chiến lược thiết kế phù hợp nếu thứ tự nghiệp vụ là bắt buộc.

### Chọn key để giữ thứ tự theo thực thể

Với các luồng event theo đơn hàng, key thường là orderId. Với luồng theo tài khoản, key có thể là accountId. Producer dùng key để partitioner xác định partition đích.

~~~text
Key = ORD-1001
  -> Partition 0
  -> OrderCreated
  -> PaymentAuthorized
  -> ShipmentRequested

Key = ORD-2001
  -> Partition 1
  -> OrderCreated
  -> PaymentAuthorized
  -> OrderCancelled
~~~

Khi dùng partitioner mặc định và cùng cấu hình partition, các record có cùng key thường được đưa vào cùng partition. Điều này giúp giữ thứ tự theo từng thực thể.

Tuy nhiên, cần lưu ý:

- Key không bảo đảm thứ tự giữa các key khác nhau.
- Tăng số partition có thể làm thay đổi kết quả ánh xạ key sang partition đối với record mới; không giả định toàn bộ lịch sử của key vẫn nằm cùng một partition sau khi thay đổi số partition.
- Một key có lượng record quá lớn có thể tạo hot partition, làm mất cân bằng tải.
- Retry qua topic khác hoặc xử lý bất đồng bộ có thể làm thay đổi thứ tự xử lý nghiệp vụ dù thứ tự trong partition gốc vẫn được giữ.

Vì vậy, hãy chọn key theo ranh giới nghiệp vụ cần giữ thứ tự và đánh giá cả phân bố tải.

## 6. Offset của consumer group

Consumer group dùng offset để ghi nhận tiến độ đọc của nhóm. Tiến độ được quản lý theo từng cặp **consumer group và partition**.

Ví dụ topic **orders.events** có hai partition và consumer group **inventory-service**:

| Consumer group | Partition | Offset đã commit |
|---|---:|---:|
| inventory-service | 0 | 120 |
| inventory-service | 1 | 87 |

Hai con số này là hai tiến độ độc lập. Consumer group đã commit đến vị trí 120 ở partition 0 và vị trí 87 ở partition 1. Không thể cộng chúng thành một offset tổng hoặc dùng một giá trị để đại diện cho toàn topic.

Một consumer group khác, chẳng hạn **analytics-service**, có thể có tiến độ riêng:

| Consumer group | Partition | Offset đã commit |
|---|---:|---:|
| analytics-service | 0 | 95 |
| analytics-service | 1 | 87 |

Việc inventory-service đã đọc xa hơn ở partition 0 không ảnh hưởng đến tiến độ của analytics-service. Mỗi group có thể xử lý cùng topic theo tốc độ riêng.

### 6.1. Offset được commit có ý nghĩa gì?

Trong Kafka Consumer API, vị trí đọc (position) là offset của record tiếp theo mà consumer sẽ nhận. Khi commit offset, consumer thường lưu vị trí tiếp theo cần đọc sau khi khởi động lại.

Giả sử consumer đã xử lý record offset 41 và muốn tiếp tục từ record kế tiếp. Offset cần commit thường là **42**.

~~~text
Partition 0:
Offset 40 -> đã xử lý
Offset 41 -> đã xử lý
Offset 42 -> vị trí tiếp theo cần đọc

Committed offset = 42
~~~

Vì vậy, khi nhìn cột **CURRENT-OFFSET** trong kết quả mô tả consumer group, đừng mặc định đó là offset của record cuối cùng đã xử lý. Thông thường nó biểu thị vị trí tiếp theo cần đọc. Cách commit và thời điểm commit phụ thuộc cấu hình auto commit hoặc logic commit thủ công của ứng dụng.

Nếu commit trước khi xử lý xong record, ứng dụng có thể bỏ qua record khi khởi động lại. Nếu xử lý xong nhưng chưa commit rồi gặp lỗi, record có thể được đọc lại. Đây là lý do cần phối hợp offset commit với tính idempotent của consumer.

### 6.2. Offset được lưu ở đâu?

Kafka lưu offset đã commit của consumer group trong topic nội bộ **__consumer_offsets**. Ứng dụng không cần tự ghi offset vào một biến toàn cục. Kafka quản lý metadata này theo group và partition, đồng thời hỗ trợ consumer tiếp tục từ tiến độ đã commit khi khởi động lại hoặc rebalance.

Việc lưu offset không xóa record khỏi topic nghiệp vụ. Record vẫn tuân theo retention hoặc log compaction của topic chứa dữ liệu.

## 7. Log start offset và log end offset

Ngoài offset của từng record, khi quan sát partition bạn sẽ gặp hai khái niệm:

- **Log start offset:** vị trí sớm nhất còn có thể đọc trong log.
- **Log end offset:** vị trí tiếp theo mà record mới sẽ được ghi vào log theo cách biểu diễn end offset thông dụng trong Kafka.

Ví dụ:

~~~text
Partition 0:
Log start offset = 100
Record offsets còn đọc được: 100, 101, 102, 103, 104
Log end offset = 105
~~~

Log end offset là vị trí kế tiếp, không phải offset của record cuối cùng. Trong ví dụ, record cuối có offset 104, còn end offset là 105.

Khi retention xóa các segment cũ, log start offset có thể tăng:

~~~text
Trước retention:
Start = 0
Record: 0, 1, 2, 3, 4, 5
End = 6

Sau retention:
Start = 3
Record còn đọc được: 3, 4, 5
End = 6
~~~

Các record còn lại giữ nguyên offset. Kafka không đánh lại số từ 0 chỉ vì các record cũ đã bị xóa.

Với log compaction, một số record cũ theo key có thể bị loại bỏ trong khi các offset khác vẫn còn. Vì thế, log start/end offset và các record thực sự đọc được là những khái niệm cần phân biệt.

## 8. Quan sát offset bằng Kafka CLI

Bạn có thể xem tiến độ consumer group và trạng thái offset bằng các công cụ dòng lệnh của Kafka.

### 8.1. Xem consumer group

Trên Linux hoặc macOS:

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group inventory-service
~~~

Trên Windows PowerShell:

~~~powershell
.\bin\windows\kafka-consumer-groups.bat --bootstrap-server localhost:9092 --describe --group inventory-service
~~~

Kết quả thường có các cột như:

| Cột | Ý nghĩa |
|---|---|
| GROUP | Tên consumer group. |
| TOPIC | Topic đang được group đọc. |
| PARTITION | Partition tương ứng. |
| CURRENT-OFFSET | Vị trí đã commit của group; thường là offset tiếp theo cần đọc. |
| LOG-END-OFFSET | Vị trí cuối log theo cách biểu diễn end offset. |
| LAG | Khoảng cách giữa end offset và tiến độ commit, theo cách tính của công cụ. |
| CONSUMER-ID | Định danh consumer đang nhận partition. |
| HOST | Máy đang chạy consumer. |
| CLIENT-ID | Client ID của consumer. |

Nếu group chưa commit offset hoặc không có consumer đang hoạt động, một số cột có thể hiển thị giá trị trống hoặc dấu gạch ngang. Điều này không nhất thiết có nghĩa topic không có dữ liệu.

### 8.2. Đọc kết quả và hiểu consumer lag

Giả sử kết quả minh họa:

~~~text
GROUP              TOPIC         PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
inventory-service  orders.events 0          120             135             15
inventory-service  orders.events 1          87              92              5
~~~

Có thể diễn giải:

- Group inventory-service đang có tiến độ riêng trên từng partition.
- Partition 0 có khoảng cách 15 offset giữa end offset và committed offset.
- Partition 1 có khoảng cách 5 offset.
- Đây là lag theo offset, không phải lúc nào cũng tương đương chính xác số record dữ liệu đang chờ xử lý, đặc biệt khi có compaction, transaction hoặc khoảng trống offset.

Consumer lag là tín hiệu hữu ích để theo dõi khả năng bắt kịp luồng dữ liệu. Tuy nhiên, cần xem thêm tốc độ producer, throughput consumer, thời gian xử lý, trạng thái partition và cách tính lag của công cụ. Một con số lag tăng liên tục có thể cho thấy consumer xử lý chậm hơn tốc độ dữ liệu được ghi vào.

### 8.3. Kiểm tra offset theo partition

Một số bản Kafka cung cấp lệnh **kafka-get-offsets** để xem offset đầu và cuối của partition. Tên script có thể khác theo bản phân phối. Với các bản có công cụ này, ví dụ:

Linux hoặc macOS:

~~~bash
bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic orders.events --time -2
~~~

~~~bash
bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic orders.events --time -1
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-get-offsets.bat --bootstrap-server localhost:9092 --topic orders.events --time -2
~~~

~~~powershell
.\bin\windows\kafka-get-offsets.bat --bootstrap-server localhost:9092 --topic orders.events --time -1
~~~

Trong công cụ này, giá trị thời gian đặc biệt **-2** thường yêu cầu offset đầu (earliest), còn **-1** yêu cầu offset cuối (latest). Hãy kiểm tra tùy chọn của phiên bản Kafka đang cài nếu script hoặc tham số khác nhau. Nếu bản phân phối không có script này, có thể dùng lệnh mô tả consumer group hoặc Kafka Admin API để quan sát tiến độ và offset.

## 9. Đọc offset trong Java Kafka Consumer

Java Kafka Consumer API cung cấp metadata của từng record. Phương thức **partition()** trả về partition chứa record và **offset()** trả về vị trí của record trong partition đó.

Ví dụ:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

import java.time.Duration;
import java.util.List;

public class OffsetInspector {
    public static void consume(KafkaConsumer<String, String> consumer) {
        consumer.subscribe(List.of("orders.events"));

        while (true) {
            ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(500));

            for (ConsumerRecord<String, String> record : records) {
                System.out.printf(
                    "topic=%s partition=%d offset=%d key=%s value=%s%n",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    record.key(),
                    record.value()
                );
            }
        }
    }
}
~~~

Trong ví dụ, mỗi record được in kèm topic, partition và offset. Không nên chỉ lưu offset nếu cần xác định vị trí record; hãy lưu thêm topic và partition.

Đây là phần minh họa cách đọc metadata, không phải một ứng dụng hoàn chỉnh. Consumer thực tế cần khởi tạo Properties, cấu hình bootstrap server, deserializer, group ID, xử lý shutdown và quản lý exception. Nếu dùng commit thủ công, cần xác định rõ thời điểm xử lý thành công và offset kế tiếp cần commit.

### 9.1. Commit offset thủ công

Khi dùng API commit thủ công, consumer có thể commit sau khi xử lý record. Ví dụ khái niệm:

~~~java
consumer.commitSync();
~~~

Lệnh này commit vị trí hiện tại mà consumer đã đọc cho các partition được gán. Trong một ứng dụng thực tế, nếu xử lý theo batch hoặc xử lý bất đồng bộ, cần bảo đảm không commit vượt qua record chưa xử lý xong.

Nếu commit theo từng record bằng API commit offset cụ thể, offset commit cần là **record.offset() + 1** để chỉ ra vị trí tiếp theo cần đọc. Đây là điểm thường gây nhầm lẫn khi mới học Kafka.

~~~java
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

TopicPartition partition =
    new TopicPartition(record.topic(), record.partition());

consumer.commitSync(
    java.util.Map.of(
        partition,
        new OffsetAndMetadata(record.offset() + 1)
    )
);
~~~

Đoạn mã trên minh họa cách commit vị trí tiếp theo sau record vừa xử lý. Nếu nhiều record đang được xử lý song song trong cùng partition, bạn phải theo dõi record đã hoàn thành theo thứ tự để tránh commit vượt quá tiến độ xử lý an toàn.

## 10. Offset và các tình huống vận hành

### 10.1. Consumer khởi động lại

Khi consumer khởi động lại với cùng group ID, Kafka dùng offset đã commit cho từng partition để xác định vị trí tiếp tục. Nếu chưa có offset hợp lệ, hành vi bắt đầu phụ thuộc cấu hình **auto.offset.reset**, thường là **earliest** hoặc **latest**.

- **earliest:** bắt đầu từ offset sớm nhất còn có thể đọc.
- **latest:** bắt đầu từ vị trí cuối log, chỉ đọc record mới được ghi sau đó.
- **none:** báo lỗi nếu không có offset đã commit hợp lệ.

Cấu hình reset không có nghĩa là consumer luôn tua lại log. Nó chỉ được dùng khi group chưa có offset hợp lệ hoặc offset đã commit không còn khả dụng.

### 10.2. Offset đã commit nằm ngoài phạm vi dữ liệu còn lưu

Nếu consumer ngừng hoạt động lâu hơn retention, offset đã commit có thể nhỏ hơn log start offset hiện tại. Khi đó, Kafka không thể cung cấp các record đã bị xóa. Consumer phải xử lý theo chính sách reset hoặc quy trình khôi phục dữ liệu mà ứng dụng lựa chọn.

Điều này cho thấy retention cần được thiết kế dựa trên thời gian gián đoạn tối đa có thể chấp nhận và yêu cầu phát lại của consumer.

### 10.3. Rebalance và nhiều consumer trong một group

Khi consumer tham gia hoặc rời group, Kafka có thể phân công lại partition. Mỗi partition được gán cho một consumer trong group tại một thời điểm theo cơ chế assignment đang sử dụng.

Offset vẫn được quản lý theo group và partition, nên consumer mới có thể tiếp tục từ offset đã commit của partition được giao. Ứng dụng cần xử lý việc dừng xử lý, commit và giải phóng tài nguyên đúng cách khi partition bị thu hồi.

### 10.4. Retry và xử lý trùng

Nếu consumer xử lý record offset 50 thành công ở database nhưng gặp lỗi trước khi commit offset 51, sau khi khởi động lại nó có thể đọc lại record offset 50. Vì thế, offset không tự bảo đảm thao tác nghiệp vụ chỉ xảy ra một lần.

Consumer cần idempotent hoặc có cơ chế deduplication dựa trên eventId/khóa nghiệp vụ. Nếu xử lý nhiều record song song, phải quản lý commit offset theo từng partition và không commit vượt quá record đã xử lý hoàn tất.

## 11. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Offset 10 ở partition 0 luôn xảy ra trước offset 8 ở partition 1. | Không thể so sánh offset giữa hai partition để suy ra thứ tự toàn cục. |
| Offset là số lượng record của topic. | Offset là vị trí trong log của một partition; có thể có khoảng trống và log start offset có thể lớn hơn 0. |
| Commit offset 42 nghĩa là record offset 42 đã xử lý xong. | Thông thường committed offset 42 là vị trí tiếp theo cần đọc; record cuối đã xử lý có thể là offset 41. |
| Retention xóa record thì offset còn lại được đánh lại từ 0. | Offset của record còn lại giữ nguyên; log start offset tiến lên. |
| Hai consumer group dùng chung một offset. | Mỗi group quản lý tiến độ riêng theo từng partition. |
| Timestamp và offset có thể thay thế nhau. | Timestamp là thời điểm; offset là vị trí trong log. |
| Consumer lag luôn bằng số record chưa xử lý chính xác. | Lag là chênh lệch offset; compaction, transaction và khoảng trống offset có thể ảnh hưởng cách diễn giải. |

## 12. Bài tập thực hành

Tạo topic **offset-lab** với hai partition. Dùng console producer gửi nhiều record, trong đó có các record mang key khác nhau. Mở consumer group mới và bật chế độ in partition cùng offset.

Linux hoặc macOS:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic offset-lab --partitions 2 --replication-factor 1
~~~

~~~bash
bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic offset-lab --property parse.key=true --property key.separator=:
~~~

Nhập ví dụ:

~~~text
ORD-1001:OrderCreated
ORD-2001:OrderCreated
ORD-1001:PaymentAuthorized
ORD-3001:OrderCreated
ORD-2001:PaymentAuthorized
~~~

Mở consumer group mới để xem metadata:

~~~bash
bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic offset-lab --group offset-lab-reader --from-beginning --property print.key=true --property print.partition=true --property print.offset=true
~~~

Trên Windows PowerShell, thay các script **.sh** bằng file tương ứng trong **.\bin\windows**.

Hãy ghi lại kết quả và trả lời:

1. Topic có những partition nào?
2. Offset trong mỗi partition bắt đầu và tăng như thế nào?
3. Có offset nào xuất hiện ở cả hai partition không? Nếu có, hai record đó có phải cùng một record không?
4. Các record cùng key có được định tuyến vào cùng partition trong lần chạy này không?
5. Vì sao không thể sắp xếp toàn bộ record của topic chỉ bằng offset?
6. Nếu committed offset của group là 5, consumer thường sẽ đọc tiếp từ vị trí nào?
7. Nếu retention làm log start offset tăng lên 10, consumer đã commit offset 4 có thể đọc lại record cũ không?
8. Consumer lag là gì và vì sao không nên luôn coi lag là số lượng record chính xác còn chờ?

## 13. Kết luận

Offset là tọa độ của một record trong một partition. Muốn xác định vị trí cần biết topic, partition và offset; chỉ có offset thì chưa đủ. Mỗi partition có dãy offset riêng, vì vậy hai partition có thể cùng có record offset 0, 1 hoặc 100 mà không tạo ra một thứ tự toàn cục.

Consumer group cũng quản lý offset riêng cho từng partition. Offset đã commit thường là vị trí tiếp theo cần đọc, còn record vẫn được lưu theo retention hoặc log compaction. Khi vận hành, cần phân biệt log start offset, log end offset, committed offset và consumer lag để hiểu đúng tiến độ xử lý.

Nắm chắc nguyên tắc này là nền tảng để học tiếp về consumer group, rebalance, ordering, retry, idempotency và xử lý luồng sự kiện bằng Java/Spring Kafka trong module KAFKA.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Offset | Vị trí của record trong một partition. |
| Partition | Log con của topic, có thứ tự và offset riêng. |
| Committed offset | Vị trí đã lưu của consumer group cho một partition; thường là vị trí tiếp theo cần đọc. |
| Log start offset | Offset sớm nhất còn có thể đọc trong log. |
| Log end offset | Vị trí kế tiếp nơi record mới sẽ được ghi vào log. |
| Consumer lag | Chênh lệch giữa log end offset và tiến độ consumer group theo partition. |
| Retention | Chính sách giữ dữ liệu theo thời gian hoặc dung lượng. |
| Log compaction | Cơ chế giữ lại dữ liệu theo key và có thể loại bỏ các record cũ hơn. |
| Rebalance | Quá trình phân công lại partition giữa các consumer trong một group. |

