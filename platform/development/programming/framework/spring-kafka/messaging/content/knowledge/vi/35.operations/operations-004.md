# Đọc current offset và log end offset

Khi vận hành Kafka, hai giá trị cần xem thường xuyên là **current offset** của consumer group và **log end offset** của từng partition. Current offset cho biết vị trí mà consumer group đã commit để tiếp tục đọc; log end offset cho biết vị trí cuối của log. Hiệu giữa hai giá trị là cơ sở phổ biến để tính **consumer lag**.

Có thể đọc các giá trị này bằng `kafka-consumer-groups.sh` hoặc Kafka `AdminClient`. Lệnh mô tả consumer group chỉ đọc metadata và offset; nó không di chuyển offset. Đây là cách kiểm tra an toàn trước khi quyết định có cần scale consumer, điều tra lỗi xử lý hay thực hiện một thao tác recovery.

## 1. Offset được đánh số theo từng partition

Kafka không cấp một dãy offset chung cho toàn topic. Mỗi partition có log và dãy offset riêng. Record đầu tiên của một partition thường bắt đầu ở offset `0`; record tiếp theo nhận offset tăng dần trong partition đó.

Ví dụ topic `orders.events` có ba partition:

```text
orders.events-0: 0, 1, 2, 3, 4, ...
orders.events-1: 0, 1, 2, 3, ...
orders.events-2: 0, 1, 2, 3, 4, 5, ...
```

Consumer group lưu tiến độ riêng cho từng cặp topic-partition. Vì vậy, khi kiểm tra offset, cần xem từng partition; một giá trị tổng hợp của topic có thể che giấu partition đang bị chậm.

Offset là vị trí trong log, không phải ID nghiệp vụ. Nó không có ý nghĩa toàn cục giữa các partition hoặc giữa các topic.

## 2. Phân biệt current offset, log end offset và lag

### 2.1. Current offset là offset đã commit

Trong output của `kafka-consumer-groups --describe`, cột `CURRENT-OFFSET` thể hiện committed offset mà Kafka lưu cho consumer group và partition. Giá trị này thường là **vị trí tiếp theo consumer group sẽ đọc sau khi khôi phục từ committed offset**.

Nếu consumer đã xử lý record offset `99` và commit tiến độ sau record đó, committed offset thường là `100`. Khi consumer khởi động lại, nó tiếp tục từ offset `100`.

Do đó, committed offset không phải offset của record cuối cùng đã xử lý. Nó là vị trí kế tiếp.

### 2.2. Log end offset là điểm cuối của log

Log end offset là mốc offset ở cuối vùng log mà công cụ đang truy vấn. Leader log end offset (LEO) là vị trí kế tiếp sẽ được gán cho record mới; nếu partition có các offset từ `0` đến `999`, LEO là `1000`. Trong output CLI, `LOG-END-OFFSET` là end marker do Kafka API trả về để tính lag; khi có replication hoặc transaction, không nên mặc định marker này luôn bằng raw LEO của leader.

LEO là giá trị biên cuối, không phải offset của record cuối cùng. Nếu partition chưa có record, LEO thường là `0`.

### 2.3. Consumer lag

Với một partition có committed offset hợp lệ:

\[
lag = logEndOffset - committedOffset
\]

Ví dụ:

```text
CURRENT-OFFSET = 100
LOG-END-OFFSET = 125
LAG            = 25
```

Consumer group đã commit vị trí `100`, trong khi log có thể tiếp tục đọc đến vị trí `124`. Chênh lệch offset là `25`.

Ví dụ trực quan: các record có offset từ 0 đến 124, còn committed offset đang ở vị trí 100.

```text
Record offsets:  ... 96  97  98  99 | 100 101 102 ... 124
                                      ^                 ^
                              committed offset       log end = 125

Lag = 125 - 100 = 25 offsets
```

Lag là số đơn vị offset chênh lệch, không phải lúc nào cũng bằng chính xác số record còn tồn tại để xử lý. Compaction, transaction và offset gaps có thể khiến hai khái niệm này khác nhau.

## 3. Đừng nhầm committed offset với vị trí consumer đang đọc

Một consumer đang chạy có thể đã poll và xử lý record xa hơn committed offset. Nếu commit được thực hiện theo batch, theo thời gian hoặc sau acknowledgment, `CURRENT-OFFSET` có thể chậm hơn tiến độ trong bộ nhớ của consumer.

Ví dụ:

```text
Consumer position trong bộ nhớ:  150
Committed offset trên broker:    120
Log end offset:                  200
```

Consumer đã tiến đến vị trí `150` nhưng mới commit `120`. Nếu process dừng đột ngột trước lần commit tiếp theo, consumer có thể đọc lại một phần record từ `120`. Đây là một nguồn tạo redelivery/duplicate trong mô hình xử lý at-least-once.

Các yếu tố ảnh hưởng thời điểm commit gồm:

- `enable.auto.commit` và chu kỳ auto commit nếu dùng Kafka consumer auto commit.
- Spring Kafka `AckMode` như `RECORD`, `BATCH`, `TIME`, `COUNT`, `MANUAL` hoặc `MANUAL_IMMEDIATE`.
- Listener xử lý thành công hay ném exception.
- Error handler, retry và recovery policy.
- Consumer rebalance hoặc process restart.

Khi điều tra lag, hãy xem cả committed offset, consumer position/records-lag metrics, listener processing time và thời điểm commit gần nhất. Không kết luận consumer đang đứng yên chỉ từ một snapshot `CURRENT-OFFSET`.

## 4. Đọc offset bằng kafka-consumer-groups

Lệnh thường dùng nhất:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service
```

Trên Windows, tên script có thể là `kafka-consumer-groups.bat`; trên Linux/macOS thường là `kafka-consumer-groups.sh`. Chạy lệnh từ thư mục `bin` của Kafka hoặc dùng đường dẫn đầy đủ đến script.

Ví dụ output:

```text
GROUP         TOPIC         PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG  CONSUMER-ID
orders-service orders.events 0          100             125             25   consumer-1
orders-service orders.events 1          210             220             10   consumer-2
orders-service orders.events 2          80              80              0    consumer-3
```

Ý nghĩa các cột chính:

| Cột | Ý nghĩa |
| --- | --- |
| `GROUP` | Tên consumer group |
| `TOPIC` | Topic mà group đang có offset |
| `PARTITION` | Partition cụ thể |
| `CURRENT-OFFSET` | Committed offset, tức vị trí tiếp theo sau lần commit gần nhất |
| `LOG-END-OFFSET` | Điểm cuối log được công cụ truy vấn cho partition |
| `LAG` | Chênh lệch giữa log end offset và committed offset |
| `CONSUMER-ID` | Consumer member đang được gán partition, nếu group đang hoạt động |

Output có thể thêm `HOST` và `CLIENT-ID`. Tên cột/định dạng chi tiết thay đổi theo phiên bản Kafka, nhưng cách đọc ba cột offset vẫn tương tự.

## 5. Kiểm tra một topic cụ thể

Có thể giới hạn output vào một topic:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --topic orders.events
```

Điều này hữu ích khi một consumer group subscribe nhiều topic và cần điều tra riêng `orders.events`.

Nếu không biết group ID, liệt kê các group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
```

Nếu cần xem trạng thái group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --state
```

Để xem member và partition assignment:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
```

Các tùy chọn `--state`, `--members` và `--verbose` phụ thuộc phiên bản Kafka CLI. Nếu phiên bản đang dùng không hỗ trợ một tùy chọn, đọc `kafka-consumer-groups.sh --help` của đúng bản phân phối.

## 6. Kết nối cluster có bảo mật

Với cluster bật TLS hoặc SASL, cung cấp file client properties bằng `--command-config`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.internal:9093 \
  --command-config client.properties \
  --describe \
  --group orders-service
```

Ví dụ `client.properties` cho SASL_SSL/SCRAM:

```properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="ops-reader" password="<injected-secret>";
ssl.truststore.location=/etc/kafka/secrets/ops.truststore.p12
ssl.truststore.password=<injected-secret>
ssl.truststore.type=PKCS12
```

`<injected-secret>` là placeholder, cần được thay bằng secret qua secret manager hoặc file tạm có quyền truy cập giới hạn trước khi chạy CLI. Kafka CLI không tự nội suy biến môi trường theo cú pháp `${KAFKA_OPS_PASSWORD}` trong file properties. Không commit password thật vào repository hoặc chia sẻ file client properties có credential qua kênh không bảo vệ.

Principal dùng để chạy lệnh cần quyền mô tả consumer group và đọc metadata/offset phù hợp. Nếu gặp `GroupAuthorizationException` hoặc lỗi ACL, nhờ quản trị Kafka cấp quyền read/describe cần thiết cho group; không đổi offset để né lỗi authorization.

## 7. Hiểu output khi chưa có committed offset

Một group mới có thể chưa commit offset cho partition. Khi đó `CURRENT-OFFSET` và `LAG` có thể hiển thị `-` thay vì một số.

Điều này không nhất thiết là lỗi. Có thể xảy ra khi:

- Group chưa từng consume partition đó.
- Consumer chưa đọc hoặc chưa commit record nào.
- Auto commit đang tắt và listener chưa commit.
- Group vừa được tạo hoặc đang trong quá trình assignment.

Khi chưa có committed offset, vị trí bắt đầu thực tế phụ thuộc `auto.offset.reset` (`earliest`, `latest` hoặc `none`) và tình trạng offset hiện có. `earliest`/`latest` chỉ được dùng khi không có offset hợp lệ theo semantics của consumer; nó không tự ghi committed offset ngay khi cấu hình được đặt.

Hãy kiểm tra group state, consumer logs, `auto.offset.reset` và thời điểm listener bắt đầu chạy trước khi kết luận group bị mất offset.

## 8. LEO, high watermark và last stable offset

Trong vận hành nâng cao, cần phân biệt ba mốc của partition:

| Mốc | Ý nghĩa |
| --- | --- |
| Log End Offset (LEO) | Vị trí kế tiếp trong log của leader; offset kế tiếp sẽ được gán |
| High Watermark (HW) | Ranh giới dữ liệu đã được replicate đủ điều kiện để consumer đọc theo chế độ thông thường |
| Last Stable Offset (LSO) | Ranh giới đọc ổn định cho consumer `read_committed`, không vượt qua transaction chưa hoàn tất |

Trong cluster có transaction, LEO, HW và LSO có thể khác nhau. Consumer `read_uncommitted` có thể đọc đến high watermark và nhìn thấy record transactional chưa commit; consumer `read_committed` chỉ đọc đến LSO để không thấy record thuộc transaction chưa kết thúc. Kafka CLI/Admin API và exporter có thể dùng isolation boundary khác nhau khi lấy end offset.

Do đó, lag được hiển thị bởi CLI hoặc exporter phụ thuộc cách công cụ truy vấn end offset và isolation level. Khi so sánh với consumer `isolation.level=read_committed`, hãy kiểm tra metric/exporter có dùng ranh giới phù hợp hay không. Đừng mặc định mọi giá trị có nhãn `end offset` đều là cùng một mốc trong mọi công cụ.

## 9. Offset gaps và compacted topic

Offset tăng theo thứ tự ghi nhưng không đảm bảo mọi số offset đều còn tương ứng với một record có thể đọc được.

Offset gap có thể xuất hiện khi:

- Topic dùng log compaction và record cũ bị loại bỏ.
- Transaction bị abort; record thuộc transaction không được trả cho consumer `read_committed`.
- Retention xóa các segment cũ.
- Các thao tác nội bộ của log làm offset không còn liên tục theo tập record consumer nhìn thấy.

Ví dụ partition có các offset còn đọc được `10`, `12`, `15`; committed offset là `10`, end offset là `16`. Chênh lệch offset là `6`, nhưng không có nghĩa chắc chắn có đúng sáu record còn chờ.

Vì vậy, lag là chỉ báo tiến độ theo offset. Để biết throughput và số record thực sự được xử lý, kết hợp với `records-consumed-rate`, application counters và metrics theo partition.

## 10. Đọc committed offset và log end offset bằng AdminClient

Trong ứng dụng vận hành hoặc công cụ nội bộ, có thể dùng Kafka `AdminClient` thay vì gọi CLI. AdminClient có thể truy vấn committed offsets của group và log end offsets của các partition tương ứng.

Ví dụ sau lấy các partition đã có committed offset của group `orders-service`, rồi truy vấn log end offset:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.ListOffsetsResult;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

public class ConsumerOffsetInspector {

    public static void main(String[] args) throws Exception {
        Map<String, Object> properties = new HashMap<>();
        properties.put(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );

        try (AdminClient admin = AdminClient.create(properties)) {
            String groupId = "orders-service";

            Map<TopicPartition, OffsetAndMetadata> committed = admin
                    .listConsumerGroupOffsets(groupId)
                    .partitionsToOffsetAndMetadata()
                    .get(10, TimeUnit.SECONDS);

            Map<TopicPartition, OffsetSpec> requests = new HashMap<>();
            committed.keySet().forEach(partition ->
                    requests.put(partition, OffsetSpec.latest())
            );

            Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> ends =
                    admin.listOffsets(requests)
                            .all()
                            .get(10, TimeUnit.SECONDS);

            committed.forEach((partition, metadata) -> {
                long currentOffset = metadata.offset();
                var endInfo = ends.get(partition);

                if (endInfo == null) {
                    System.out.printf(
                            "%s: không đọc được log end offset%n",
                            partition
                    );
                    return;
                }

                long logEndOffset = endInfo.offset();
                long lag = logEndOffset - currentOffset;

                System.out.printf(
                        "%s current=%d end=%d lag=%d%n",
                        partition,
                        currentOffset,
                        logEndOffset,
                        lag
                );
            });
        }
    }
}
```

Đoạn code là ví dụ tối thiểu; trong ứng dụng thực tế, đưa bootstrap servers và security properties vào cấu hình, không hardcode credential. `AdminClient` phải có quyền mô tả group và truy vấn offset của topic.

Các API chính:

- `listConsumerGroupOffsets(groupId)` lấy committed offset theo topic-partition.
- `partitionsToOffsetAndMetadata()` trả map partition → committed offset metadata.
- `listOffsets(requests)` truy vấn mốc offset theo từng partition.
- `OffsetSpec.latest()` yêu cầu mốc cuối log theo semantics của Kafka client/API đang dùng.

Ví dụ chỉ in những partition đã có committed offset. Partition chưa từng commit không có trong map; nếu cần kiểm tra mọi partition của topic, phải lấy metadata topic/partition rồi truy vấn `OffsetSpec.latest()` cho toàn bộ partition.

Nếu `lag` âm, không nên âm thầm ép về `0`. Hãy điều tra topic bị xóa/tạo lại, offset metadata cũ, log truncation hoặc sự khác nhau giữa các mốc offset đang so sánh.

## 11. Lấy beginning offset để kiểm tra retention

Log start/beginning offset là offset nhỏ nhất còn có thể đọc trong partition. Nó có ích khi kiểm tra committed offset có còn nằm trong vùng dữ liệu được giữ hay không.

Ví dụ dùng `OffsetSpec.earliest()`:

Giả sử `partitions` là tập `TopicPartition` đã lấy từ metadata của topic cần kiểm tra:

```java
Map<TopicPartition, OffsetSpec> beginningRequests = new HashMap<>();
partitions.forEach(partition ->
        beginningRequests.put(partition, OffsetSpec.earliest())
);

Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> beginnings =
        admin.listOffsets(beginningRequests)
                .all()
                .get(10, TimeUnit.SECONDS);
```

Nếu committed offset nhỏ hơn beginning offset, dữ liệu từ vị trí consumer muốn tiếp tục có thể đã bị retention xóa. Consumer có thể gặp `OffsetOutOfRangeException` và phải áp dụng `auto.offset.reset` hoặc chính sách recovery đã thiết kế.

Nếu committed offset lớn hơn log end offset, cần điều tra metadata offset không còn khớp với log hiện tại. Không tự reset offset chỉ dựa trên một snapshot; xác minh topic identity, partition và trạng thái cluster trước.

## 12. Tổng hợp lag cho cả group

Lag thường được tính riêng từng partition. Tổng lag group có thể tính bằng:

\[
groupLag = \sum_{p \in partitions} lag_p
\]

Ví dụ:

| Partition | Current offset | Log end offset | Lag |
| ---: | ---: | ---: | ---: |
| 0 | 100 | 125 | 25 |
| 1 | 210 | 220 | 10 |
| 2 | 80 | 80 | 0 |
| **Tổng** |  |  | **35** |

Tổng lag `35` cho biết group đang cách cuối log 35 offset theo phép tính này. Tuy nhiên, partition `0` có lag lớn hơn các partition còn lại; nên kiểm tra riêng consumer member đang nhận partition đó.

Tổng lag hữu ích cho dashboard tổng quan nhưng không thay thế lag theo partition. Một partition nóng có thể bị chậm trong khi tổng lag vẫn có vẻ nhỏ.

## 13. Đọc lag cùng consumer group state và assignment

Khi group đang rebalance, partition assignment có thể thay đổi trong lúc công cụ truy vấn. Snapshot offset có thể không đại diện cho trạng thái ổn định.

Kiểm tra group state và member:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --state

kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
```

Quan sát:

- Group có `Stable` hay đang `PreparingRebalance`/`CompletingRebalance`.
- Có bao nhiêu member đang hoạt động.
- Partition nào được gán cho từng member.
- Có partition không có member nhận hay không.
- Member có thay đổi liên tục do restart, timeout hoặc lỗi heartbeat hay không.

Nếu lag tăng cùng với rebalance liên tục, kiểm tra `max.poll.interval.ms`, thời gian xử lý listener, `session.timeout.ms`, `heartbeat.interval.ms` và lỗi network. Đừng chỉ tăng concurrency trước khi xác định nguyên nhân rebalance.

## 14. Cách diễn giải các tình huống phổ biến

| Dấu hiệu | Khả năng | Hướng điều tra |
| --- | --- | --- |
| Lag bằng 0 ổn định | Group đã commit sát cuối log | Theo dõi thêm throughput và error rate |
| Lag tăng liên tục | Producer nhanh hơn consumer hoặc listener/downstream chậm | Đo processing time, consumer rate, partition skew và dependency latency |
| Lag tăng rồi giảm | Traffic burst hoặc consumer vừa bắt kịp | Xem thời gian phục hồi và mức lag đỉnh |
| Một partition lag cao | Key skew, dữ liệu nóng hoặc consumer member gặp vấn đề | Xem partition assignment, key distribution và member logs |
| Current offset đứng yên, end offset tăng | Consumer không commit, listener treo, rebalance hoặc commit lỗi | Kiểm tra consumer state, logs, AckMode và error handler |
| Current offset đứng yên, end offset cũng đứng yên | Topic không có traffic hoặc consumer chưa xử lý tiếp | Kiểm tra producer rate và listener health |
| Current offset là `-` | Group chưa commit offset cho partition | Kiểm tra group mới, auto.offset.reset và lần xử lý đầu |
| Lag âm | Offset metadata và log hiện tại không đồng nhất hoặc khác mốc đo | Kiểm tra topic recreation, truncation và isolation semantics |
| Lag lớn sau thời gian downtime | Consumer cần xử lý backlog tích lũy | Ước lượng tốc độ drain và downstream capacity |
| Lag thấp nhưng xử lý nghiệp vụ chậm | Consumer đã poll/commit nhưng side effect hoặc queue nội bộ chậm | Đo business latency, pending work và commit boundary |

## 15. Ước lượng thời gian drain backlog

Nếu biết lag hiện tại và tốc độ xử lý ròng, có thể ước lượng thời gian consumer cần để bắt kịp producer.

Giả sử:

- Lag hiện tại là `120.000` offsets.
- Consumer xử lý trung bình `1.500` records/giây.
- Producer tiếp tục ghi `1.000` records/giây.

Tốc độ giảm lag là `1.500 - 1.000 = 500` records/giây. Thời gian drain ước lượng:

\[
120000 / 500 = 240\ seconds
\]

Tức khoảng bốn phút nếu tốc độ ổn định và offset chênh lệch phản ánh gần đúng số record cần xử lý. Với compacted topic, offset gaps hoặc transaction, đây chỉ là ước lượng thô. Hãy đo throughput thực tế theo partition và theo dõi xu hướng lag sau khi scale.

Nếu consumer throughput nhỏ hơn hoặc bằng producer throughput, backlog sẽ không giảm. Khi đó cần tăng khả năng xử lý, giảm tải producer, tối ưu listener/downstream hoặc điều chỉnh partitioning nếu workload cho phép.

## 16. Các nguyên nhân khiến lag tăng

Lag tăng có thể đến từ nhiều tầng:

**Producer và partitioning:** producer tăng throughput đột ngột; key phân phối lệch khiến một partition nhận phần lớn record; số partition không đủ cho mức song song cần thiết.

**Consumer:** concurrency thấp, số replica ít, rebalance liên tục, `max.poll.records` không phù hợp hoặc consumer không nhận được partition.

**Listener:** xử lý đồng bộ quá lâu, gọi HTTP/database chậm, lock contention, thread pool cạn hoặc batch quá lớn.

**Retry và lỗi:** record lỗi bị retry nhiều lần, blocking backoff giữ partition, DLT publish gặp lỗi hoặc downstream liên tục trả lỗi.

**Broker/network:** fetch latency cao, broker quá tải, network chập chờn, disk I/O chậm hoặc partition leader thay đổi.

Đối chiếu lag với producer send rate, consumer records rate, listener duration, error/retry rate, rebalance count và broker health để khoanh vùng.

## 17. Cẩn thận khi diễn giải lag với transaction

Nếu producer dùng Kafka transaction và consumer đặt `isolation.level=read_committed`, consumer không đọc record thuộc transaction chưa commit. Một transaction mở lâu có thể giữ LSO ở phía trước, làm consumer `read_committed` chờ dù LEO tiếp tục tăng.

Trong trường hợp này, chênh lệch `LEO - committedOffset` có thể lớn hơn phần record hiện đang hiển thị cho consumer `read_committed`. Hãy xem transaction duration, LSO/HW nếu công cụ hỗ trợ và isolation level của consumer.

Đừng thay đổi `isolation.level` trong production chỉ để làm lag dashboard giảm. Thay đổi này có thể khiến consumer nhìn thấy dữ liệu transactional chưa commit và làm sai semantics nghiệp vụ.

## 18. Quan sát lag bằng metrics và monitoring

Ngoài CLI, nên thu thập lag định kỳ qua Kafka exporter, JMX exporter hoặc công cụ monitoring của Kafka platform. Metrics ứng dụng có thể bổ sung:

- Records consumed rate.
- Listener processing duration p95/p99.
- Commit latency và commit failure.
- Rebalance total/rate.
- Assigned partition count.
- Retry rate và DLT publish rate.
- Downstream database/HTTP latency.

Dashboard nên có cả tổng lag và lag theo partition. Alert nên xét thời gian lag duy trì, tốc độ tăng và SLA xử lý, thay vì chỉ cảnh báo khi lag khác `0`.

Một rule alert cần cân nhắc:

```text
consumer group lag > ngưỡng trong N phút
AND consumer throughput < producer throughput
```

Ngưỡng và thời gian duy trì phụ thuộc throughput, SLA và khả năng drain backlog của từng luồng. Một topic audit có thể chấp nhận lag cao hơn một topic xử lý thanh toán.

## 19. Các thao tác offset có thể gây ảnh hưởng dữ liệu

`kafka-consumer-groups --describe` là thao tác đọc. Các tùy chọn như `--reset-offsets` có thể thay đổi tiến độ group và khiến record bị đọc lại hoặc bị bỏ qua tùy vị trí mới.

Trước khi reset offset, cần có kế hoạch riêng:

1. Xác nhận đúng cluster, group, topic và partition.
2. Ghi lại committed offset hiện tại và log start/end offset.
3. Xác định mục tiêu nghiệp vụ: đọc lại, bỏ qua backlog hay khôi phục sau retention.
4. Dừng consumer group hoặc bảo đảm group không hoạt động theo yêu cầu của CLI/phiên bản.
5. Chạy chế độ preview/dry-run nếu phiên bản hỗ trợ và review kết quả.
6. Có phê duyệt vận hành, backup/record offset và kế hoạch rollback.
7. Chỉ thực thi khi hiểu rõ duplicate hoặc data loss có thể xảy ra.

Không chạy `--reset-offsets --execute` chỉ vì thấy lag cao. Lag là tín hiệu cần điều tra; reset offset là thay đổi semantics xử lý dữ liệu.

## 20. Checklist điều tra current offset và log end offset

Khi một consumer group bị báo lag, hãy đi theo trình tự:

1. Xác định đúng bootstrap server, security config và group ID.
2. Chạy `kafka-consumer-groups --describe --group ...` để lấy offset từng partition.
3. Kiểm tra `CURRENT-OFFSET`, `LOG-END-OFFSET` và `LAG`.
4. Xác minh group state, member count và partition assignment.
5. Xem committed offset có tồn tại hay hiển thị `-`.
6. So sánh snapshot nhiều thời điểm để xác định lag tăng, giảm hay đứng yên.
7. Kiểm tra producer throughput, consumer rate và listener processing duration.
8. Kiểm tra retry, DLT, commit failure và rebalance.
9. Nếu offset bất thường, kiểm tra beginning offset, retention, topic recreation và transaction isolation.
10. Chỉ xem xét reset offset sau khi có kế hoạch recovery và đánh giá tác động dữ liệu.

Current offset trong consumer group là tiến độ đã commit, còn log end offset là điểm cuối log của partition. Chênh lệch giữa chúng là chỉ báo lag hữu ích, nhưng cần đọc cùng consumer position, commit policy, group state, partition assignment và transaction semantics. Dùng CLI để kiểm tra nhanh, AdminClient để tích hợp công cụ vận hành và metrics để theo dõi xu hướng liên tục.

## 21. Tự kiểm tra

1. Vì sao offset của Kafka được theo dõi riêng cho từng partition?
2. `CURRENT-OFFSET` trong `kafka-consumer-groups --describe` biểu thị vị trí nào?
3. Vì sao committed offset thường là vị trí kế tiếp chứ không phải record cuối cùng đã xử lý?
4. Công thức tính lag theo partition là gì?
5. Vì sao current offset có thể thấp hơn vị trí consumer đang xử lý trong bộ nhớ?
6. Khi nào `CURRENT-OFFSET` có thể hiển thị `-`?
7. LEO, high watermark và last stable offset khác nhau như thế nào?
8. Vì sao lag không luôn bằng chính xác số record còn chờ trong compacted topic?
9. Cần dùng những API AdminClient nào để đọc committed offset và log end offset?
10. Vì sao không nên reset offset chỉ dựa trên một snapshot lag cao?
