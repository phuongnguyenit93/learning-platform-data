# Theo dõi, quản trị và kiểm thử share group

## Mục tiêu bài học

Kafka Share Groups cho phép một nhóm consumer cùng chia sẻ công việc đọc record. Khác với consumer group truyền thống, nơi mỗi partition tại một thời điểm được giao cho một consumer member, nhiều share consumer trong cùng share group có thể cùng đọc từ một partition. Broker dùng acquisition lock theo từng record để một record đang được xử lý không được giao đồng thời cho consumer khác trong thời gian lock còn hiệu lực.

Mô hình này phù hợp với workload cần chia việc theo record, xử lý song song các record trong cùng partition và chấp nhận thứ tự xử lý linh hoạt hơn. Nó đòi hỏi cách theo dõi, xác nhận xử lý, retry và quản trị khác với committed offset của consumer group thông thường.

Bài học hướng dẫn theo dõi member, state và tiến độ share group; quản trị bằng Kafka CLI; cấu hình acquisition lock, delivery limit và dead-letter queue; viết consumer bằng KafkaShareConsumer; và kiểm thử cạnh tranh, redelivery, timeout cùng lỗi xử lý.

Sau bài học, người học có thể:

- Phân biệt share group với consumer group.
- Giải thích record acquisition lock và vòng đời ACCEPT, RELEASE, REJECT, RENEW.
- Chọn implicit hoặc explicit acknowledgement phù hợp.
- Hiểu delivery count, lock duration, polling và liveness.
- Theo dõi share group bằng CLI, metrics và broker state.
- Reset share group offsets, xóa topic offsets và xóa group an toàn.
- Cấu hình retry và dead-letter queue theo feature level hỗ trợ.
- Viết consumer Java bằng KafkaShareConsumer.
- Kiểm thử nhiều consumer chia sẻ cùng partition và các tình huống redelivery.
- Nhận biết giới hạn về ordering, idempotency, transactional records và version compatibility.

## 1. Share group giải quyết bài toán nào?

Với consumer group truyền thống, Kafka phân phối partition giữa các member. Nếu topic có bốn partition và group có tám consumer, tối đa bốn consumer có thể được gán partition; các consumer còn lại không có partition để đọc. Một partition không được chia cho hai member cùng group tại cùng thời điểm.

Share group thay đổi đơn vị chia việc từ partition sang record. Nhiều consumer trong cùng group có thể cùng nhận record từ một partition, miễn là record đó chưa được một consumer khác acquire.

~~~mermaid
flowchart TB
    subgraph CG["Consumer group truyền thống"]
        T1["orders-0"] --> C1["Consumer A"]
        T2["orders-1"] --> C2["Consumer B"]
        T3["orders-2"] --> C2
    end
    subgraph SG["Share group"]
        P["orders-0"] --> R1["Consumer A"]
        P --> R2["Consumer B"]
        P --> R3["Consumer C"]
        R1 -. "Record 0, 3" .-> P
        R2 -. "Record 1" .-> P
        R3 -. "Record 2, 4" .-> P
    end
~~~

Trong share group, các consumer là một pool cùng làm việc trên tập topic đăng ký. Một record chỉ được giao cho một consumer tại một thời điểm khi acquisition lock còn hiệu lực. Khi record được ACCEPT, RELEASE, REJECT hoặc lock hết hạn, broker cập nhật trạng thái và quyết định record có thể được giao lại hay không.

### 1.1. So sánh consumer group và share group

| Tiêu chí | Consumer group | Share group |
|---|---|---|
| Đơn vị phân phối | Partition | Record |
| Một partition có thể phục vụ bao nhiêu member trong cùng group? | Một member tại một thời điểm | Nhiều member có thể cùng chia sẻ |
| Cơ chế giữ quyền xử lý | Partition assignment | Record acquisition lock có thời hạn |
| Xác nhận xử lý | Commit offset | Acknowledge trạng thái từng record |
| Retry một record | Thường dựa vào offset, seek hoặc retry topic | RELEASE hoặc để lock hết hạn |
| Loại bỏ record lỗi vĩnh viễn | DLQ/retry framework hoặc skip theo offset | REJECT; có thể cấu hình native share-group DLQ |
| Ordering | Thứ tự đọc trong partition; thường dễ giữ thứ tự xử lý nếu xử lý tuần tự | Không bảo đảm thứ tự hoàn tất giữa nhiều consumer cùng partition |
| Phù hợp | Event processing cần partition ownership và ordering | Work queue, task processing và record-level parallelism |

Share group và consumer group có thể đọc cùng một topic độc lập. Chúng không chia sẻ trạng thái tiêu thụ với nhau.

### 1.2. Share group không phải một queue riêng

Record vẫn được lưu trong Kafka topic và giữ partition/offset ban đầu. Share group lưu trạng thái delivery/acquisition riêng cho nhóm, thay vì tạo một queue vật lý mới.

Một topic có thể được nhiều share group đọc độc lập. Mỗi group có trạng thái xử lý riêng; ACCEPT trong group A không làm group B bỏ qua record đó.

## 2. Phiên bản và feature level

Share Groups là tính năng phát triển qua nhiều phiên bản Kafka. Kafka 4.0 Java API đánh dấu share consumer là API evolving/early access. Kafka 4.1 phát hành share groups ở dạng preview và không bật mặc định. Tài liệu Kafka 4.4 mô tả KafkaShareConsumer là public API và cung cấp công cụ quản trị share group, metrics và DLQ.

Không chỉ dựa vào phiên bản client JAR để kết luận cluster hỗ trợ mọi API. Client có thể kết nối broker hỗ trợ share groups nhưng nhận UnsupportedVersionException nếu gọi API chưa được broker version/feature level hỗ trợ.

Kiểm tra feature level trên cluster:

~~~bash
kafka-features.sh --bootstrap-server localhost:9092 describe
~~~

Tìm feature share.version trong kết quả. Feature level cần thiết phụ thuộc chức năng muốn dùng; ví dụ native share-group DLQ trong tài liệu Kafka 4.4 yêu cầu share.version ít nhất bằng 2.

Trước khi bật hoặc nâng feature level:

- Kiểm tra broker version và feature level hiện tại.
- Đọc release notes và hướng dẫn upgrade của đúng Kafka version.
- Xác nhận mọi broker/controller đã tương thích.
- Lập kế hoạch rollback/upgrade theo quy trình quản trị cluster.
- Thử trên staging với client version sẽ triển khai.

Không chạy lệnh nâng feature level trên production chỉ để thử một ví dụ trong bài học.

## 3. Record acquisition lock và vòng đời delivery

Khi share consumer gọi poll, broker trả về các record phù hợp với subscription. Mỗi record được acquire cho một consumer bằng lock có thời hạn. Trong thời gian lock còn hiệu lực, record đó không được giao cho consumer khác trong cùng share group.

~~~mermaid
stateDiagram-v2
    [*] --> Available
    Available --> Acquired: Consumer poll
    Acquired --> Accepted: ACCEPT
    Acquired --> Available: RELEASE
    Acquired --> Rejected: REJECT
    Acquired --> Acquired: RENEW
    Acquired --> Available: Lock expires
    Accepted --> [*]
    Rejected --> [*]
~~~

Các trạng thái:

- **Available**: record có thể được giao cho một share consumer.
- **Acquired**: record đang được một consumer giữ lock để xử lý.
- **Accepted**: consumer xác nhận xử lý thành công.
- **Released**: consumer nhả record để group có thể thử giao lại.
- **Rejected**: consumer xác nhận record không thể xử lý và không cần giao lại.
- **Renewed**: consumer gia hạn lock khi vẫn đang xử lý record.

### 3.1. Lock duration

Trong cấu hình Kafka 4.4, thời gian acquisition lock mặc định là 30 giây. Group có thể cấu hình share.record.lock.duration.ms trong giới hạn broker cho phép.

Nếu consumer không acknowledge record, lock sẽ tự hết hạn và record có thể được giao lại. Cơ chế này giúp hệ thống tiếp tục tiến triển khi process chết hoặc không còn xử lý record.

Lock timeout không chứng minh consumer cũ đã dừng. Nếu consumer cũ vẫn đang chạy nhưng xử lý quá lâu, consumer khác có thể nhận lại record sau khi lock hết hạn. Hai lần xử lý có thể chồng lấn, vì vậy side effect cần idempotent.

### 3.2. Giới hạn số record đang được acquire

Broker giới hạn số record có thể được acquire trên mỗi topic-partition trong một share group. Tài liệu Kafka 4.4 có cấu hình broker group.share.partition.max.record.locks, mặc định 2000 trong cấu hình được công bố.

Khi đạt giới hạn, fetch có thể tạm thời không trả thêm record từ partition đó cho đến khi số record đang acquire giảm xuống. Điều này bảo vệ coordinator và giới hạn lượng công việc đang chờ xác nhận.

### 3.3. Delivery count

Share group theo dõi số lần record được giao. Kafka 4.4 có broker config group.share.delivery.count.limit, mặc định 5 lần; giới hạn tối đa mà group config có thể chọn còn phụ thuộc group.share.max.delivery.count.limit.

Khi một record liên tục được giao lại, delivery count tăng. Cần theo dõi record có delivery count cao để phát hiện poison message hoặc consumer lỗi. Không giả định một record có thể được retry vô hạn.

## 4. Acknowledgement: ACCEPT, RELEASE, REJECT và RENEW

Share consumer có acknowledgement theo record:

| Acknowledge type | Ý nghĩa | Trường hợp dùng |
|---|---|---|
| ACCEPT | Xác nhận xử lý thành công | Business operation hoàn tất |
| RELEASE | Nhả record để có thể được giao lại | Lỗi tạm thời, dependency đang lỗi |
| REJECT | Từ chối record, không yêu cầu giao lại | Payload sai vĩnh viễn hoặc vi phạm contract |
| RENEW | Gia hạn acquisition lock | Xử lý lâu hơn lock duration |

Phân loại lỗi là quyết định nghiệp vụ. Không REJECT mọi exception; lỗi database timeout hoặc service tạm unavailable thường cần RELEASE để thử lại. Record sai schema hoặc vi phạm quy tắc vĩnh viễn có thể cần REJECT và DLQ/audit.

### 4.1. Implicit acknowledgement

share.acknowledgement.mode mặc định là implicit. Trong mode này, consumer không gọi acknowledge():

- Gọi poll() tiếp theo sẽ ngầm acknowledge các record đã trả ở poll trước và gửi trạng thái lên Kafka theo cơ chế bất đồng bộ.
- Gọi commitSync() hoặc commitAsync() sẽ ngầm xác nhận các record đã trả thành công.
- Gọi close() sẽ cố gắng giải phóng các record đang acquire mà chưa được xác nhận.

Implicit mode phù hợp với xử lý đơn giản, nơi toàn bộ batch được xem là thành công khi vòng xử lý hoàn tất. Nếu một record lỗi nhưng consumer vẫn poll tiếp, việc implicit acknowledge có thể xác nhận nhầm record đó.

### 4.2. Explicit acknowledgement

Đặt:

~~~properties
share.acknowledgement.mode=explicit
~~~

Trong mode này, ứng dụng phải acknowledge từng record được trả về trước lần poll kế tiếp. Nếu còn record chưa acknowledge, lần poll tiếp theo có thể ném IllegalStateException.

acknowledge(record, type) chỉ cập nhật trạng thái acknowledgement cục bộ trong consumer. Trạng thái được gửi đến Kafka khi gọi commitSync(), commitAsync() hoặc lần poll() tiếp theo sau khi đã acknowledge toàn bộ record.

Kafka áp dụng acknowledgement của các record trong một batch theo từng topic-partition một cách nguyên tử. Vì vậy, khi xử lý lỗi trong batch, hãy xác định rõ trạng thái của từng record trước khi commit; không xem mỗi lần gọi acknowledge là một request độc lập đã được broker lưu ngay.

Với xử lý nghiệp vụ có thể thất bại theo từng record, explicit mode thường dễ kiểm soát hơn.

### 4.3. Ví dụ explicit acknowledgement

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;

import org.apache.kafka.clients.consumer.AcknowledgeType;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaShareConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

public class ImageShareWorker {

    public static void main(String[] args) {
        Properties props = new Properties();
        props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "image-resize-workers");
        props.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        props.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        props.put("share.acknowledgement.mode", "explicit");
        props.put("share.acquire.mode", "record_limit");
        props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 50);
        props.put(ConsumerConfig.CLIENT_ID_CONFIG, "image-worker-1");

        try (KafkaShareConsumer<String, String> consumer =
                 new KafkaShareConsumer<>(props)) {

            consumer.subscribe(List.of("images"));

            while (!Thread.currentThread().isInterrupted()) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofMillis(1000));

                for (ConsumerRecord<String, String> record : records) {
                    try {
                        resizeImage(record.value());
                        consumer.acknowledge(
                            record,
                            AcknowledgeType.ACCEPT
                        );
                    } catch (TransientProcessingException ex) {
                        consumer.acknowledge(
                            record,
                            AcknowledgeType.RELEASE
                        );
                    } catch (InvalidImageException ex) {
                        consumer.acknowledge(
                            record,
                            AcknowledgeType.REJECT
                        );
                    } catch (Exception ex) {
                        System.err.printf(
                            "Unexpected processing error topic=%s partition=%d offset=%d: %s%n",
                            record.topic(),
                            record.partition(),
                            record.offset(),
                            ex.getMessage()
                        );
                        consumer.acknowledge(
                            record,
                            AcknowledgeType.RELEASE
                        );
                    }
                }

                consumer.commitSync();
            }
        }
    }

    private static void resizeImage(String payload) {
        // Gọi xử lý ảnh của ứng dụng.
    }
}
~~~

TransientProcessingException và InvalidImageException là exception minh họa của ứng dụng. Trong thực tế cần phân loại lỗi rõ ràng; exception không dự kiến không nên tự động REJECT nếu có khả năng đó là lỗi hạ tầng tạm thời.

### 4.4. Vì sao commitSync vẫn cần thiết?

Trong explicit mode, gọi acknowledge chưa có nghĩa broker đã lưu trạng thái. Nếu ứng dụng kết thúc trước khi commit acknowledgement, broker có thể giao lại record khi lock hết hạn hoặc consumer khác tiếp quản.

Commit acknowledgement sau khi xử lý xong giúp broker cập nhật trạng thái delivery. Nếu commit lỗi, ứng dụng cần log, metric và xử lý retry phù hợp; không được ghi nhận business operation đã được xác nhận ở Kafka khi chưa có bằng chứng commit.

Khi close consumer ở explicit mode, client cố gắng commit acknowledgement đang chờ và giải phóng các record chưa được acknowledge. Vì vậy, shutdown cần có thời gian đóng consumer hợp lý; nếu process bị kill đột ngột, lock sẽ hết hạn theo broker policy.

### 4.5. RENEW khi xử lý lâu

Nếu thời gian xử lý có thể vượt share.record.lock.duration.ms, explicit acknowledgement hỗ trợ AcknowledgeType.RENEW.

Consumer cần tiếp tục gọi poll() để duy trì membership và gửi RENEW trong vòng lặp khi record chưa hoàn tất. Record được renew thành công có thể xuất hiện lại trong kết quả poll tiếp theo. RENEW không phải cách thay thế cho việc quản lý timeout vô hạn; nó làm tăng thời gian record bị giữ và có thể ảnh hưởng tiến độ giao record khác.

Chỉ dùng RENEW cho công việc thực sự cần thời gian dài. Nếu xử lý có thể chia nhỏ, cân nhắc tách thành nhiều bước để không giữ record quá lâu.

## 5. Polling, batching và liveness

Share consumer phải tiếp tục gọi poll() để duy trì membership và nhận record. Consumer không poll trong thời gian vượt max.poll.interval.ms có thể rời share group. Session timeout và heartbeat được dùng để phát hiện consumer không còn hoạt động.

Consumer tự join group khi gọi poll lần đầu sau subscribe. Coordinator kích hoạt rebalance khi member tham gia/rời group, member bị phát hiện lỗi, số partition của topic thay đổi hoặc topic được tạo/xóa. Khi một member lỗi, partition được phân phối lại cho các member còn lại; record chưa được xác nhận có thể được giao lại sau khi acquisition lock kết thúc.

Hai cấu hình quan trọng:

| Config | Vai trò |
|---|---|
| share.acknowledgement.mode | Chọn implicit hoặc explicit ack |
| share.acquire.mode | Chọn cách broker acquire record theo batch hoặc giới hạn số record |

share.acquire.mode có hai giá trị:

- batch_optimized (mặc định): tối ưu theo ranh giới batch; số record trả về có thể vượt max.poll.records và client có thể prefetch.
- record_limit: số record mỗi poll không vượt max.poll.records, không prefetch; phù hợp khi cần kiểm soát số record và thời điểm acquisition lock bắt đầu chặt hơn.

Khi xử lý có latency biến động, record_limit giúp dự đoán số record đang giữ và thời gian xử lý mỗi batch tốt hơn, đổi lại có thể giảm throughput.

### 5.1. Tách polling khỏi xử lý nghiệp vụ

Không chặn consumer thread quá lâu nếu điều đó khiến poll interval vượt giới hạn. Nếu chuyển record sang executor:

- Phải acknowledge từng record sau khi worker hoàn tất.
- Duy trì poll để heartbeat/liveness.
- Dùng RENEW nếu lock cần được kéo dài và API/version hỗ trợ.
- Giới hạn queue để không acquire nhiều record hơn khả năng xử lý.
- Bảo đảm shutdown chờ công việc đang chạy hoặc để lock hết hạn có kiểm soát.
- Dùng idempotency vì record có thể được giao lại sau timeout.

Không acknowledge ACCEPT ngay khi vừa submit task vào executor. Điều đó xác nhận thành công trước khi nghiệp vụ thực sự hoàn tất.

### 5.2. Thread safety

KafkaShareConsumer không thread-safe. Chỉ một thread nên gọi các API consumer như poll, acknowledge, commit và subscribe. Nếu cần yêu cầu shutdown từ thread khác, có thể dùng wakeup() để đánh thức thao tác đang chờ; không chia sẻ consumer cho nhiều worker thread cùng gọi API.

## 6. Ordering và concurrency

Share group ưu tiên chia việc theo record, do đó không giữ được cùng mức ordering như consumer group xử lý tuần tự theo partition.

Kafka trả các record trong một ConsumerRecords cho một topic-partition theo thứ tự offset tăng dần. Tuy nhiên, hai share consumer khác nhau có thể cùng nhận record của partition đó và xử lý song song. Record offset lớn hơn có thể hoàn tất trước record offset nhỏ hơn.

Ví dụ:

~~~text
Partition 0:
offset 10 -> Consumer A -> xử lý 8 giây
offset 11 -> Consumer B -> xử lý 1 giây
offset 11 có thể hoàn tất trước offset 10
~~~

Nếu nghiệp vụ yêu cầu ordering theo aggregate:

- Dùng consumer group truyền thống nếu partition-level ordering là yêu cầu bắt buộc.
- Hoặc thêm sequence/version nghiệp vụ và kiểm tra thứ tự ở consumer.
- Không để hai record cùng aggregate gây side effect không thể đảo ngược khi xử lý song song.
- Dùng idempotency key và optimistic concurrency ở database.

Share group phù hợp khi record độc lập hoặc nghiệp vụ chấp nhận xử lý không theo thứ tự. Nó không phải cách tăng concurrency miễn phí cho mọi topic.

## 7. Theo dõi share group bằng Kafka CLI

Kafka cung cấp công cụ riêng kafka-share-groups.sh. Có thể dùng kafka-groups.sh để xem tất cả group type và công cụ share group để xem chi tiết.

### 7.1. Liệt kê mọi group

~~~bash
kafka-groups.sh --bootstrap-server localhost:9092 --list
~~~

Kết quả có thể hiển thị group ID và loại group, ví dụ Consumer hoặc Share.

### 7.2. Liệt kê share group

~~~bash
kafka-share-groups.sh --bootstrap-server localhost:9092 --list
~~~

Dùng lệnh này để kiểm tra share group đã tồn tại trong cluster.

### 7.3. Xem start offset và lag

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group image-resize-workers
~~~

Ví dụ kết quả:

~~~text
GROUP                 TOPIC   PARTITION  START-OFFSET  LAG
image-resize-workers  images  0          120           35
image-resize-workers  images  1          98            12
~~~

START-OFFSET của share group là offset nhỏ nhất của các record đang in-flight được đánh giá để giao cho share consumer. Một số record có offset lớn hơn start offset có thể đã xử lý xong. Vì vậy, không diễn giải start offset như committed offset tuần tự của consumer group truyền thống.

LAG cần được đọc cùng số record đang in-flight, delivery count và trạng thái consumer. Nếu có record bị giữ lock lâu, start offset có thể đứng lại dù một số record phía sau đã được xử lý.

### 7.4. Xem active members

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group image-resize-workers \
  --members
~~~

Kết quả cho biết consumer ID, host, client ID, số partition và assignment. Nhiều member có thể cùng hiển thị một partition trong assignment vì họ đang chia sẻ partition đó.

### 7.5. Xem trạng thái group

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group image-resize-workers \
  --state
~~~

Trạng thái group và số member giúp phát hiện group không có member, đang thay đổi membership hoặc gặp vấn đề coordinator. Khi dùng lệnh admin để xem share group offsets, principal cần quyền DESCRIBE trên group và các topic mà group sử dụng.

### 7.6. ACL cho share consumer và quản trị viên

Share consumer cần quyền READ trên group và các topic được subscribe. Các thao tác SHARE_FETCH và SHARE_ACK được authorize trên cả Group resource và Topic resource. Admin cần quyền DESCRIBE trên group/topic để xem trạng thái và offsets.

Ví dụ cấp quyền READ cho principal ứng dụng:

~~~bash
kafka-acls.sh --bootstrap-server localhost:9092 \
  --add --allow-principal User:image-worker \
  --operation Read --group image-resize-workers

kafka-acls.sh --bootstrap-server localhost:9092 \
  --add --allow-principal User:image-worker \
  --operation Read --topic images
~~~

Ví dụ cấp quyền DESCRIBE cho principal vận hành để xem group và topic:

~~~bash
kafka-acls.sh --bootstrap-server localhost:9092 \
  --add --allow-principal User:kafka-operator \
  --operation Describe --group image-resize-workers

kafka-acls.sh --bootstrap-server localhost:9092 \
  --add --allow-principal User:kafka-operator \
  --operation Describe --topic images
~~~

Chỉ cấp quyền trên resource cần thiết. Các lệnh reset/delete offsets và xóa group cần quyền bổ sung tương ứng với thao tác quản trị; kiểm tra authorizer và ACL thực tế của cluster.

## 8. Reset, xóa offsets và xóa share group

Đây là các thao tác quản trị có thể làm record được giao lại hoặc bỏ qua. Hãy dừng hoặc điều phối consumer theo change plan trước khi chạy.

### 8.1. Dry-run reset offsets

--dry-run cho biết offset mới mà không áp dụng:

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets \
  --group image-resize-workers \
  --topic images \
  --to-earliest \
  --dry-run
~~~

### 8.2. Thực thi reset

Chỉ chạy sau khi review kết quả dry-run:

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --reset-offsets \
  --group image-resize-workers \
  --topic images \
  --to-earliest \
  --execute
~~~

Các lựa chọn reset được hỗ trợ gồm to-earliest, to-latest, to-datetime, to-offset, to-current và from-file tùy phiên bản. Reset có thể khiến record cũ được giao lại hoặc record trước đó không còn được xét giao.

### 8.3. Xóa offsets của một topic trong group

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --delete-offsets \
  --group image-resize-workers \
  --topic images
~~~

Xóa offsets của topic làm thay đổi trạng thái tiêu thụ của group cho topic đó. Chỉ thực hiện khi đã hiểu cách group sẽ tiếp tục đọc sau thao tác.

### 8.4. Xóa share group

~~~bash
kafka-share-groups.sh \
  --bootstrap-server localhost:9092 \
  --delete \
  --group image-resize-workers
~~~

Chỉ xóa được share group không còn active members. Xóa group là thao tác quản trị có tác động đến trạng thái delivery của nhóm; không dùng như cách khắc phục lag thông thường.

## 9. Cấu hình share group

Có thể xem cấu hình group bằng:

~~~bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type groups \
  --entity-name image-resize-workers \
  --describe
~~~

Một số group config trong Kafka 4.4:

| Config | Ý nghĩa |
|---|---|
| share.record.lock.duration.ms | Thời gian acquisition lock |
| share.delivery.count.limit | Giới hạn số lần giao record |
| share.partition.max.record.locks | Số record tối đa được acquire trên mỗi partition |
| share.heartbeat.interval.ms | Chu kỳ heartbeat |
| share.session.timeout.ms | Thời gian phát hiện consumer mất kết nối |
| share.isolation.level | Cách đọc record transactional |
| share.renew.acknowledge.enable | Cho phép RENEW acknowledgement |

Giá trị mặc định và min/max có thể thay đổi theo broker version và dynamic config. Broker áp giới hạn tối đa/tối thiểu cho group config; không giả định mọi giá trị đều có thể tùy chỉnh tùy ý.

### 9.1. Điều chỉnh lock duration

Lock ngắn giúp record lỗi được giao lại nhanh khi consumer chết, nhưng có thể gây redelivery nếu xử lý bình thường lâu hơn dự kiến. Lock dài giảm redelivery giả nhưng làm chậm phục hồi khi consumer thực sự chết.

Chọn duration dựa trên p95/p99 processing time và thời gian phát hiện lỗi. Nếu công việc có thời gian xử lý rất biến động, dùng RENEW khi phù hợp thay vì đặt lock rất dài cho mọi record.

### 9.2. Delivery count limit

Giới hạn delivery count bảo vệ group khỏi một record poison được giao lại vô hạn. Đặt quá thấp có thể đẩy record lỗi tạm thời sang trạng thái không còn được retry; đặt quá cao làm tăng chi phí và thời gian xử lý poison message.

Kết hợp delivery limit với phân loại exception, RELEASE, REJECT, DLQ và quy trình replay.

## 10. Dead-letter queue cho share group

Kafka 4.4 hỗ trợ cấu hình native share-group DLQ khi share.version đạt ít nhất level 2. Tính năng và các config liên quan cần được xác minh trên broker đang chạy.

### 10.1. Gán DLQ topic cho group

~~~bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --add-config "errors.deadletterqueue.topic.name=dlq.images" \
  --entity-type groups \
  --entity-name image-resize-workers
~~~

Mặc định broker không tự tạo DLQ topic. Nếu muốn cho phép auto-create DLQ topic, cần bật broker config:

~~~bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --add-config "errors.deadletterqueue.auto.create.topics.enable=true" \
  --entity-type brokers \
  --entity-default
~~~

Nếu tự tạo DLQ topic, bật config topic phù hợp:

~~~bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --add-config "errors.deadletterqueue.group.enable=true" \
  --entity-type topics \
  --entity-name dlq.images
~~~

### 10.2. Nội dung DLQ

Theo mặc định, record được ghi vào DLQ chỉ chứa metadata nguồn như topic, partition và offset. Nếu cần copy key/value của record nguồn, bật:

~~~bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --add-config "errors.deadletterqueue.copy.record.enable=true" \
  --entity-type groups \
  --entity-name image-resize-workers
~~~

DLQ có thể chứa dữ liệu nhạy cảm. Cần cấu hình ACL, retention, encryption và quy trình truy cập phù hợp. Không bật copy payload nếu người vận hành DLQ không được phép đọc dữ liệu gốc.

### 10.3. Quy trình xử lý DLQ

Một quy trình vận hành nên gồm:

1. Alert khi DLQ rate tăng hoặc có record mới.
2. Ghi nhận source topic, partition, offset và delivery metadata.
3. Phân loại lỗi do dữ liệu, contract, dependency hay bug.
4. Sửa nguyên nhân và kiểm tra trên staging.
5. Quyết định replay record bằng công cụ có kiểm soát hoặc đánh dấu đã xử lý theo chính sách nghiệp vụ.
6. Theo dõi duplicate và side effect sau replay.

DLQ không thay thế idempotency. Record được replay có thể tạo side effect lặp nếu consumer không kiểm soát event ID. Kết hợp delivery count limit với DLQ để record vượt số lần giao được chuyển sang luồng điều tra; xác minh hành vi cụ thể trên đúng share.version và broker release đang chạy.

## 11. Transactional records và isolation level

Share group dùng group-level config share.isolation.level để quyết định cách đọc transactional records. Đây là cấu hình áp dụng cho cả share group, không phải mỗi consumer member.

- read_uncommitted: có thể đọc transactional record kể cả transaction đã abort; giới hạn đọc theo high watermark.
- read_committed: chỉ giao record non-transactional và transactional đã commit; giới hạn đọc theo last stable offset. Transaction đang mở có thể chặn tiến độ.

Không nhầm share-group acknowledgement với Kafka transaction của producer. Acknowledge record không tự tạo một distributed transaction giữa Kafka và database.

Nếu consumer thực hiện side effect ở database:

- Ghi event ID vào inbox/processed table trong cùng DB transaction với business update.
- Commit DB transaction trước khi acknowledge ACCEPT.
- Nếu DB commit thành công nhưng acknowledgement commit thất bại, record có thể được giao lại; inbox giúp tránh side effect lặp.
- Nếu DB rollback, RELEASE để record có thể được thử lại.

## 12. Theo dõi metrics và cảnh báo

Kafka 4.4 công bố metrics riêng cho share group ở broker và client. Tên MBean và metric phụ thuộc version; cần kiểm tra exporter đang dùng.

### 12.1. Broker metrics

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| TotalShareFetchRequestsPerSec | Tốc độ share fetch request | Fetch rate giảm bất thường |
| FailedShareFetchRequestsPerSec | Fetch request lỗi | Tăng liên tục |
| TotalShareAcknowledgementRequestsPerSec | Tốc độ acknowledgement request | Thấp bất thường so với xử lý |
| FailedShareAcknowledgementRequestsPerSec | Acknowledgement request lỗi | Tăng hoặc có spike |
| RecordAcknowledgementsPerSec | Rate theo ACCEPT/RELEASE/REJECT/RENEW | RELEASE/REJECT tăng đột biến |
| share-group-rebalance-rate | Tốc độ rebalance | Group thay đổi member liên tục |
| share-group-rebalance-count | Tổng số rebalance | Tăng nhanh bất thường |
| partition-load-time-max | Thời gian load share-group state partition | Coordinator state load chậm |
| partition-load-time-avg | Thời gian load trung bình | Xu hướng tăng |

### 12.2. Client metrics

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| last-poll-seconds-ago | Số giây từ lần poll gần nhất | Tăng gần max.poll.interval |
| time-between-poll-avg | Khoảng cách poll trung bình | Lớn hơn ngân sách |
| time-between-poll-max | Khoảng cách poll lớn nhất | Có spike |
| poll-idle-ratio-avg | Tỷ lệ thời gian poll chờ record | Quá cao có thể ít việc hoặc assignment/traffic bất thường |
| heartbeat-response-time-max | Thời gian phản hồi heartbeat lớn nhất | Tăng do network/coordinator |

### 12.3. Alert thực tế

- Failed share fetch hoặc acknowledgement rate vượt ngưỡng.
- RELEASE/REJECT tăng đột biến.
- RENEW tăng cao và processing time vượt SLA.
- Share group không có member trong khi backlog còn.
- Lag hoặc tuổi record in-flight vượt SLA.
- Rebalance liên tục.
- Client không poll trong thời gian gần max.poll.interval.ms.
- DLQ có record mới hoặc DLQ rate tăng.
- Share coordinator load time tăng.

Đọc metrics cùng CLI và application logs. Chỉ số start offset/lag không thể cho biết toàn bộ record đã hoàn tất vì các record có thể hoàn thành ngoài thứ tự.

## 13. Share coordinator và internal state topic

Broker duy trì trạng thái share group trong internal share-group state topic, thường có tên __share_group_state. Topic này được Kafka quản lý; không tạo, xóa hoặc thay đổi partition count bằng tay.

Một số broker configs quan trọng trong Kafka 4.4:

| Broker config | Vai trò |
|---|---|
| share.coordinator.state.topic.replication.factor | Replication factor của share-group state topic |
| share.coordinator.state.topic.min.isr | min ISR của state topic |
| share.coordinator.state.topic.num.partitions | Số partition state topic; nên giữ ổn định sau deployment |
| share.coordinator.write.timeout.ms | Timeout ghi state của coordinator |
| share.coordinator.threads | Số thread share coordinator |

Trong cấu hình Kafka 4.4 được công bố, replication factor mặc định của state topic là 3 và min ISR là 2. Cluster cần đủ broker đáp ứng replication factor trước khi share group state topic có thể được tạo.

Không chỉnh __share_group_state như một topic nghiệp vụ. Nếu state topic không khả dụng, điều tra coordinator, broker, ISR, disk và controller thay vì can thiệp trực tiếp vào nội dung topic.

## 14. Kiểm thử share group

Kiểm thử share group cần broker có hỗ trợ feature level tương ứng. Unit test có thể kiểm tra logic phân loại lỗi và acknowledgement bằng mock, nhưng chỉ integration test với Kafka broker mới xác minh được record acquisition lock, coordinator state, redelivery và CLI.

### 14.1. Unit test logic xử lý

Tách business processing khỏi Kafka consumer loop:

~~~java
public AcknowledgeType process(ImageJob job) {
    try {
        imageService.resize(job);
        return AcknowledgeType.ACCEPT;
    } catch (TransientProcessingException ex) {
        return AcknowledgeType.RELEASE;
    } catch (InvalidImageException ex) {
        return AcknowledgeType.REJECT;
    }
}
~~~

Unit test kiểm tra:

- Job hợp lệ trả ACCEPT.
- Lỗi dependency tạm thời trả RELEASE.
- Payload không hợp lệ trả REJECT.
- Exception không phân loại được không bị âm thầm coi là thành công.

Kafka 4.4 cung cấp MockShareConsumer để kiểm thử code dùng ShareConsumer mà không cần broker. Mock này không thread-safe và không mô phỏng đầy đủ coordinator, acquisition lock, rebalance hay feature level; dùng nó để kiểm tra logic client-side, còn các semantics broker phải được kiểm thử bằng integration test.

### 14.2. Integration test với hai consumer

Thiết lập:

1. Tạo topic có một partition.
2. Khởi động hai KafkaShareConsumer với cùng group.id.
3. Cả hai subscribe cùng topic.
4. Publish một batch record.
5. Quan sát hai consumer cùng nhận record từ partition đó.
6. Acknowledge từng record và commit.

Xác minh:

- Một record đang có lock không được giao đồng thời cho member khác khi lock còn hiệu lực.
- Nhiều record trong cùng partition có thể được chia cho các consumer.
- Không giả định record hoàn tất theo thứ tự offset trên toàn group.
- Một share group khác vẫn có thể đọc độc lập cùng topic.

### 14.3. Kiểm thử RELEASE và redelivery

1. Consumer A nhận record và gọi RELEASE.
2. Commit acknowledgement.
3. Consumer B hoặc A poll lại.
4. Xác minh record có thể được giao lại.
5. Kiểm tra delivery count tăng.
6. Acknowledge ACCEPT ở lần xử lý thành công.

Test nên dùng timeout hữu hạn và chờ trạng thái thực tế thay vì Thread.sleep cố định.

### 14.4. Kiểm thử lock expiration

1. Cấu hình lock duration ngắn trong môi trường test.
2. Consumer A acquire record nhưng không acknowledge.
3. Đợi lock hết hạn.
4. Consumer B poll và nhận lại record.
5. Xác minh application idempotent khi lần xử lý A vẫn có thể đang chạy.

Không dùng cấu hình lock ngắn trong production chỉ để làm test dễ hơn.

### 14.5. Kiểm thử RENEW

1. Bật explicit acknowledgement.
2. Consumer nhận record có thời gian xử lý dài hơn lock mặc định.
3. Poll đều đặn và gửi RENEW theo chu kỳ.
4. Xác minh record không bị giao lại khi renew thành công.
5. Dừng renew để kiểm tra lock hết hạn và redelivery.

### 14.6. Kiểm thử REJECT và DLQ

1. Gửi một record không hợp lệ.
2. Acknowledge REJECT.
3. Xác minh record không được giao lại theo semantics reject.
4. Bật share.version phù hợp và cấu hình DLQ.
5. Gửi record vượt điều kiện chuyển DLQ theo cấu hình.
6. Xác minh metadata nguồn và payload copy policy.

### 14.7. Kiểm thử consumer failure

- Kill consumer sau khi acquire nhưng trước ACK.
- Ngắt network khi commit acknowledgement.
- Restart broker/share coordinator trong môi trường test.
- Kiểm tra member được phát hiện mất kết nối.
- Kiểm tra lock hết hạn và record được giao lại.
- Xác minh duplicate không làm side effect lặp.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| UnsupportedVersionException | Broker hoặc feature level chưa hỗ trợ API | Kiểm tra broker version và share.version |
| Hai consumer không cùng nhận một partition | Chưa dùng KafkaShareConsumer hoặc không cùng group.id | Kiểm tra client class, group ID và CLI --members |
| Record bị giao lại nhiều lần | Consumer không ACK, RELEASE hoặc lock hết hạn | Kiểm tra lock duration, processing time và delivery count |
| Consumer B nhận record khi A vẫn xử lý | Lock A đã hết hạn hoặc A mất kết nối | Kiểm tra RENEW, poll interval và idempotency |
| Poll trả ít record hơn mong đợi | Partition lock limit đã đạt hoặc backlog ít | Kiểm tra share.partition.max.record.locks và in-flight records |
| Explicit mode ném IllegalStateException | Có record chưa được acknowledge trước poll kế tiếp | Theo dõi mọi record trong batch và đảm bảo ack đầy đủ |
| RELEASE tăng cao | Dependency lỗi hoặc business processing không ổn định | Kiểm tra downstream latency/error |
| REJECT tăng cao | Payload lỗi hoặc exception mapping sai | Kiểm tra schema, validation và exception classification |
| DLQ không có record | Feature level chưa đủ hoặc group/topic config thiếu | Kiểm tra share.version, group config và topic config |
| CLI không mô tả được group | Thiếu DESCRIBE ACL hoặc group/topic không tồn tại | Kiểm tra principal, topic subscription và group ID |
| Share coordinator state load chậm | Internal state topic hoặc broker gặp vấn đề | Kiểm tra ISR, disk, controller và coordinator metrics |
| Lag đứng nhưng record phía sau đã xử lý | Start offset là earliest in-flight, không phải sequential committed offset | Kết hợp --describe, member state và application metrics |

## 16. Checklist triển khai production

- Broker và client version hỗ trợ share groups.
- share.version được kiểm tra và nâng theo quy trình cluster.
- Chọn share group chỉ khi record-level parallelism phù hợp nghiệp vụ.
- Chọn explicit acknowledgement nếu cần phân loại thành công, retry và reject theo record.
- Mọi record trong poll batch được acknowledge trước lần poll tiếp theo ở explicit mode.
- Poll loop đáp ứng max.poll.interval.ms.
- Lock duration phù hợp p95/p99 processing time.
- Dùng RENEW cho xử lý dài và theo dõi ảnh hưởng delivery progress.
- Side effect có idempotency vì lock expiry và retry có thể gây duplicate.
- Ordering requirement được đánh giá rõ; không giả định ordering toàn partition.
- Delivery count limit, RELEASE/REJECT và DLQ có policy.
- DLQ có ACL, retention, encryption và quy trình replay.
- Share group CLI được dùng để kiểm tra member/state/start offset/lag.
- Broker/client metrics được export và có alert.
- __share_group_state có replication/min ISR phù hợp và không bị chỉnh thủ công.
- Có integration test cho redelivery, lock expiration, renew, reject, DLQ và restart.

## 17. Bài tập thực hành

### Bài tập 1: Quan sát share group

1. Tạo topic image-jobs có một partition.
2. Chạy hai share consumer cùng group ID.
3. Dùng kafka-share-groups.sh --describe --members xem assignment.
4. Xác nhận cả hai member có thể cùng share partition.
5. Dùng --state kiểm tra số member và coordinator.

### Bài tập 2: Explicit acknowledgement

1. Cấu hình share.acknowledgement.mode=explicit.
2. Gửi record hợp lệ, lỗi tạm thời và payload sai.
3. Dùng ACCEPT, RELEASE và REJECT tương ứng.
4. Commit acknowledgement.
5. Quan sát record nào được giao lại.

### Bài tập 3: Lock expiration và RENEW

1. Cấu hình lock duration phù hợp trong môi trường test.
2. Giữ một record lâu hơn lock duration.
3. Quan sát redelivery khi không renew.
4. Thử RENEW và poll đều đặn.
5. So sánh delivery count và thời gian xử lý.

### Bài tập 4: Quản trị offsets

1. Chạy --describe để xem start offset và lag.
2. Chạy reset --dry-run.
3. Review kết quả.
4. Reset --execute trong group lab.
5. Xóa offsets một topic và quan sát group.

### Bài tập 5: DLQ và metrics

1. Kiểm tra share.version.
2. Cấu hình DLQ topic cho group.
3. Gửi record lỗi và quan sát delivery attempts.
4. Kiểm tra DLQ metadata và copy payload policy.
5. Thu thập broker metrics và client metrics.

## 18. Câu hỏi tự kiểm tra

1. Share group khác consumer group ở đơn vị phân phối nào?
2. Vì sao nhiều share consumer có thể cùng đọc một partition?
3. Acquisition lock ngăn điều gì và không bảo đảm điều gì?
4. ACCEPT, RELEASE và REJECT khác nhau thế nào?
5. Vì sao explicit acknowledgement phải xử lý đủ record trước lần poll kế tiếp?
6. Khi nào nên dùng RENEW?
7. share.acquire.mode=record_limit khác batch_optimized ra sao?
8. Vì sao share group không bảo đảm thứ tự hoàn tất giữa các consumer?
9. START-OFFSET của share group có giống committed offset của consumer group không?
10. Cần quyền gì để admin mô tả share group và topic?
11. Khi nào có thể xóa share group?
12. Feature level nào được yêu cầu cho native share-group DLQ trong Kafka 4.4?
13. Vì sao consumer vẫn cần idempotency dù record đang có acquisition lock?
14. __share_group_state được dùng làm gì và vì sao không chỉnh thủ công?
15. Những metrics nào giúp phát hiện acknowledgement failure và share group rebalance?

## Tài liệu tham khảo

- [Apache Kafka 4.4 – KafkaShareConsumer Java API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaShareConsumer.html)
- [Apache Kafka 4.4 – MockShareConsumer Java API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/MockShareConsumer.html)
- [Apache Kafka 4.4 – Basic Kafka Operations, Managing Share Groups và DLQ](https://kafka.apache.org/44/operations/basic-kafka-operations/)
- [Apache Kafka 4.4 – Consumer and Share Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka 4.4 – Group Configs](https://kafka.apache.org/44/configuration/group-configs/)
- [Apache Kafka 4.4 – Broker Configs](https://kafka.apache.org/44/configuration/broker-configs/)
- [Apache Kafka 4.4 – Monitoring, Share Group Metrics](https://kafka.apache.org/44/operations/monitoring/)
- [Apache Kafka 4.4 – Authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/)

Share group là lựa chọn cho bài toán chia sẻ công việc theo record. Theo dõi đúng member, start offset, in-flight lock, acknowledgement và delivery count giúp phân biệt backlog thật với record đang được xử lý; kiểm thử lock expiry, RELEASE, RENEW và duplicate giúp bảo đảm ứng dụng phục hồi an toàn khi consumer hoặc broker gặp sự cố.
