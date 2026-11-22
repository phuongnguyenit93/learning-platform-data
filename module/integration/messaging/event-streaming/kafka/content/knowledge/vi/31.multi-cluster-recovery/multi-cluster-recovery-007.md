# Offset translation và điều kiện chuyển consumer sang cụm dự phòng

## Mục tiêu

Trong Kafka, offset là vị trí của record trong một partition và chỉ có ý nghĩa trong log của cluster chứa partition đó. Khi MirrorMaker 2 (MM2) sao chép topic từ primary sang disaster recovery (DR) cluster, record ở target thường nhận offset mới. Vì vậy, consumer không thể lấy nguyên committed offset ở primary rồi seek cùng con số trên target.

MM2 giải quyết vấn đề này bằng cách ghi các cặp offset tương ứng, tạo checkpoint cho từng consumer group và cung cấp API để dịch vị trí đọc giữa hai cluster. Tuy nhiên, replication diễn ra bất đồng bộ và offset translation có giới hạn độ chính xác. Chuyển consumer an toàn cần kiểm tra replication lag, checkpoint freshness, topic mapping, trạng thái consumer group và khả năng xử lý record được đọc lại.

Sau bài học, bạn có thể:

- Giải thích vì sao offset giữa hai cluster không giống nhau.
- Phân biệt offset-sync, checkpoint và committed offset trong __consumer_offsets.
- Mô tả cách MirrorSourceConnector và MirrorCheckpointConnector phối hợp.
- Giải thích offset translation chính xác, translation gần đúng và trường hợp chưa thể dịch.
- Cấu hình đồng bộ consumer group offsets tự động trong MM2.
- Dùng RemoteClusterUtils để dịch offset khi failover thủ công.
- Xác định điều kiện trước khi chuyển consumer sang DR cluster.
- Thực hiện planned failover và xử lý unplanned failover.
- Theo dõi replication lag, checkpoint latency và RPO/RTO.
- Tránh split-brain, mất dữ liệu và duplicate side effect trong quá trình chuyển cụm.

## 1. Vì sao cần offset translation?

### 1.1. Offset là vị trí cục bộ của partition

Offset tăng theo log của từng topic-partition trong một Kafka cluster. Offset 500 ở primary không có nghĩa là cùng business event với offset 500 ở DR.

Target có thể có offset khác vì:

- Topic được tạo ở thời điểm khác.
- Target bắt đầu nhận bản sao từ một vị trí khác với log start offset của source.
- Record được replicate và append vào log target theo tốc độ riêng.
- Source và target có retention hoặc compaction làm cho các khoảng offset không còn giống nhau.
- Có record batch, retry hoặc các lần khởi tạo replication khác nhau.

MM2 giữ thứ tự record trong từng partition được replicate và remote partition tương ứng với source partition, nhưng offset được cấp ở target là offset của target log.

### 1.2. Committed offset là vị trí tiếp theo cần đọc

Consumer commit offset N có nghĩa lần đọc tiếp theo bắt đầu tại offset N. Record cuối cùng đã xử lý thành công thường là N-1.

Ví dụ:

| Consumer group | Committed offset | Ý nghĩa |
|---|---:|---|
| orders-reader | 105 | Record tiếp theo cần đọc là offset 105 |
| orders-reader | 106 | Record offset 105 đã được xử lý và tiến độ đã commit |

Khi dịch offset, cần giữ đúng semantics của vị trí tiếp tục đọc. Không tự cộng hoặc trừ một đơn vị nếu API translation đã trả về OffsetAndMetadata tương ứng.

### 1.3. Ví dụ hai cluster có offset khác nhau

Giả sử topic orders.v1 ở primary có partition 0. Sau khi replicate, topic remote ở DR có prefix cluster alias là primary:

| Business event | Primary offset | DR offset |
|---|---:|---:|
| Order A | 100 | 90 |
| Order B | 101 | 91 |
| Order C | 102 | 92 |
| Order D | 103 | 93 |
| Order E | 104 | 94 |

Consumer ở primary đã commit offset 103. Nếu consumer ở DR seek thẳng đến 103, nó sẽ bỏ qua các record ở DR offset 93 và 94 tương ứng với những event chưa được xử lý ở primary.

Consumer cần vị trí tương ứng trên DR, được MM2 tính từ offset mappings và checkpoints. Đó là lý do cần offset translation.

## 2. Ba loại offset metadata của MM2

MM2 dùng nhiều internal topic để theo dõi replication và tiến độ consumer. Ba loại dữ liệu cần phân biệt:

| Thành phần | Nơi lưu mặc định | Nội dung | Vai trò |
|---|---|---|---|
| Offset-syncs | Source cluster | Cặp offset source và target cho từng topic-partition | Làm cơ sở dịch offset |
| Checkpoints | Target cluster | Consumer group, topic, partition, source offset và target offset | Lưu tiến độ consumer đã dịch |
| __consumer_offsets | Từng cluster | Committed offset thực tế của consumer group tại cluster đó | Vị trí consumer dùng khi khởi động |

### 2.1. Offset-syncs

MirrorSourceConnector replicate record từ source sang target. Khi biết offset record ở hai phía, connector ghi một offset-sync record vào internal topic.

Một offset-sync mapping có dạng:

| Trường | Ý nghĩa |
|---|---|
| Topic | Remote topic ở target |
| Partition | Partition tương ứng |
| Upstream offset | Offset tại source |
| Downstream offset | Offset tương ứng tại target |

Ví dụ một mapping:

~~~text
source topic: orders.v1
target topic: primary.orders.v1
partition: 0
upstream offset: 500
downstream offset: 470
~~~

Offset-syncs topic nằm ở source cluster theo mặc định. Cấu hình offset-syncs.topic.location có thể chuyển vị trí sang target. Nếu đổi vị trí, MirrorSourceConnector và MirrorCheckpointConnector cần có quyền truy cập phù hợp trên cluster chứa topic này.

### 2.2. Checkpoints

MirrorCheckpointConnector đọc offset-syncs và committed offsets của consumer groups ở source. Connector tạo checkpoint trên target cho các group/topic/partition đang được replicate.

Checkpoint gồm:

- Consumer group ID.
- Topic remote ở target.
- Partition.
- Upstream offset: committed position tại source.
- Downstream offset: position đã dịch tại target.
- Metadata và timestamp.

Checkpoint topic được log-compacted để giữ trạng thái mới nhất cho từng tổ hợp group/topic/partition. Nó là dữ liệu nội bộ phục vụ migration/failover; không phải nơi consumer ứng dụng trực tiếp commit tiến độ.

### 2.3. __consumer_offsets tại target

Checkpoint chỉ là bản ghi offset đã dịch. Muốn consumer group khởi động ở target tự nhận vị trí này, MM2 phải đồng bộ translated offsets vào __consumer_offsets của target bằng cấu hình sync.group.offsets.enabled.

Hai cơ chế khác nhau:

1. Checkpoint được phát ra ở target để có thể tra cứu/dịch lại khi cần.
2. Offset sync ghi translated offset vào __consumer_offsets để consumer group trên target tự tiếp tục.

Trong Kafka 4.4, emit.checkpoints.enabled mặc định là true, còn sync.group.offsets.enabled mặc định là false. Vì vậy, có checkpoint topic không đồng nghĩa target consumer group đã có committed offsets mới. [MirrorMaker Configs — Apache Kafka 4.4](https://kafka.apache.org/44/configuration/mirrormaker-configs/).

### 2.4. Heartbeats

MirrorHeartbeatConnector phát heartbeat để thể hiện luồng replication và kết nối giữa các cluster còn hoạt động. Heartbeat hữu ích để phát hiện đường truyền/connector mất kết nối, nhưng không chứng minh mọi partition đã replicate đủ dữ liệu hoặc checkpoint đã mới.

Không dùng heartbeat thành công làm điều kiện duy nhất để failover. Phải theo dõi thêm record age, replication latency, partition lag và checkpoint latency.

## 3. Cách offset translation hoạt động

### 3.1. Hai tiến trình chạy song song

MM2 phối hợp hai connector:

1. MirrorSourceConnector replicate record và ghi offset-sync mapping.
2. MirrorCheckpointConnector đọc mapping, giữ cache theo partition và dịch committed offset của consumer group để tạo checkpoint.

Sơ đồ:

~~~mermaid
flowchart LR
    A[Primary topic partition] --> B[MirrorSourceConnector]
    B --> C[DR remote topic partition]
    B --> D[Offset-syncs topic]
    E[Primary __consumer_offsets] --> F[MirrorCheckpointConnector]
    D --> F
    F --> G[DR checkpoints topic]
    F --> H[DR __consumer_offsets]
~~~

H chỉ được cập nhật khi sync.group.offsets.enabled được bật và điều kiện đồng bộ group thỏa mãn. Checkpoint G vẫn có thể được phát ra khi tự động commit translated offsets chưa bật.

### 3.2. Translation có thể chính xác hoặc gần đúng

MM2 không lưu mapping cho mọi record vì sẽ làm internal topic tăng quá lớn. Connector tạo mapping theo ngưỡng offset.lag.max và duy trì một cache có giới hạn cho mỗi partition.

Nếu source committed offset khớp một mapping còn trong cache, target offset có thể được dịch chính xác. Nếu không khớp, MM2 dùng target offset của mapping source gần nhất ở phía trước cộng một đơn vị để chọn vị trí an toàn, chấp nhận đọc lại một số record.

Ví dụ minh họa các mapping còn trong cache:

| Source offset | Target offset |
|---:|---:|
| 1.000 | 940 |
| 900 | 845 |
| 800 | 750 |
| 600 | 560 |

Nếu consumer commit source offset 900, mapping khớp trực tiếp và có thể dịch tới target offset 845.

Nếu consumer commit source offset 870, không có mapping chính xác. MM2 dùng mapping trước đó theo thuật toán bảo thủ; consumer có thể bắt đầu sớm hơn vị trí tương đương thực tế và xử lý lại một số record.

Ví dụ chi tiết hơn, nếu mapping gần nhất phía trước là source offset 800 sang target offset 750, source committed offset 870 có thể được dịch tới target offset 751. Consumer sẽ đọc lại các record từ 751 cho tới vị trí tương đương thực tế của source offset 870. Khoảng cách giữa các mapping càng lớn thì số record có thể phải xử lý lại càng nhiều.

Điều quan trọng là MM2 ưu tiên tránh bỏ qua dữ liệu. Offset được dịch có thể khiến consumer đọc lại record, vì vậy business handler cần idempotent hoặc có cơ chế chống duplicate.

### 3.3. Translation không bảo đảm chính xác với offset quá mới

Nếu consumer đã commit source offset mới hơn mapping gần nhất mà MirrorSourceConnector đã ghi, MM2 chưa có dữ liệu để dịch vị trí đó. Trong trường hợp này, translation không khả dụng; checkpoint logic có thể biểu diễn bằng offset -1.

Ví dụ:

- Offset-sync mới nhất của source partition là 700.
- Consumer source đã commit offset 715.
- MirrorSourceConnector chưa replicate tới vùng offset tương ứng.

MM2 không thể suy ra một target offset đáng tin cậy cho 715. Không tự chọn 715 trên target và cũng không mặc định dùng latest. Hãy đợi replication bắt kịp nếu source còn hoạt động, hoặc chọn recovery position theo RPO và runbook khi source đã mất.

### 3.4. Translation cũ giảm độ chính xác

Offset-sync cache có giới hạn. Các mapping mới được giữ dày hơn, còn mapping cũ được lưu thưa dần để kiểm soát dung lượng. Vì vậy:

- Offset gần cuối log thường được dịch chính xác hơn.
- Consumer lag lâu có thể phải reprocess nhiều record hơn khi failover.
- Offset rất cũ có thể không còn mapping phù hợp.
- Nếu checkpoint topic hoặc offset-syncs topic thiếu dữ liệu, khả năng dịch giảm.

Offset translation là ánh xạ có mất mát độ chính xác, không phải phép đổi số học giữa hai log. [Translating offsets between clusters — Red Hat](https://docs.redhat.com/en/documentation/red_hat_streams_for_apache_kafka/3.2/html/disaster_recovery_using_mirrormaker_2/con-mm2-offset-translation-str) mô tả thuật toán bảo thủ và tác động reprocessing.

## 4. Các cấu hình ảnh hưởng đến offset translation

### 4.1. Cấu hình quan trọng

| Config | Mặc định Kafka 4.4 | Tác dụng |
|---|---:|---|
| emit.offset-syncs.enabled | true | Ghi offset mapping từ MirrorSourceConnector |
| offset.lag.max | 100 | Ngưỡng downstream offset trước khi tạo offset-sync mới |
| emit.checkpoints.enabled | true | Phát checkpoint cho consumer groups |
| emit.checkpoints.interval.seconds | 60 | Chu kỳ phát checkpoint |
| sync.group.offsets.enabled | false | Ghi translated offsets vào __consumer_offsets của target |
| sync.group.offsets.interval.seconds | 60 | Chu kỳ đồng bộ offset group tới target |
| offset-syncs.topic.location | source | Vị trí offset-syncs topic |
| refresh.groups.interval.seconds | 600 | Chu kỳ phát hiện group mới |
| groups.exclude | console-consumer-.*, connect-.*, __.* | Nhóm mặc định bị loại khỏi replication |

Các giá trị trên là default trong Kafka 4.4 config reference. Một số bản phân phối hoặc cấu hình triển khai có thể override chúng. Hãy kiểm tra cấu hình runtime và đúng phiên bản MM2 đang dùng. [Kafka 4.4 MirrorMaker Configs](https://kafka.apache.org/44/configuration/mirrormaker-configs/).

### 4.2. Điều chỉnh offset.lag.max

offset.lag.max điều khiển khoảng cách downstream offset tối đa so với lần sync gần nhất trước khi MirrorSourceTask ghi offset-sync mới.

- Giá trị thấp hơn: mapping dày hơn, translation gần cuối log chính xác hơn, nhưng internal topic tăng traffic/storage và Connect task phải xử lý nhiều mapping hơn.
- Giá trị cao hơn: giảm số mapping và chi phí, nhưng có thể làm tăng số record bị đọc lại khi failover.
- Giá trị 0: yêu cầu mapping cho mọi record replicated, tăng độ chính xác nhưng có thể gây overhead lớn ở topic throughput cao.

Default Kafka 4.4 là 100. Tài liệu config mô tả ước lượng số record có thể duplicate ở failover theo Partition Count × offset.lag.max; đây là ước lượng, không phải giới hạn cứng vì thời điểm commit, lag và lịch phát mapping cũng ảnh hưởng.

Không đặt offset.lag.max bằng 0 cho toàn cluster chỉ để tối ưu một consumer group nhạy cảm. Benchmark throughput, internal topic growth và checkpoint latency trước khi thay đổi.

### 4.3. Điều chỉnh checkpoint và sync interval

emit.checkpoints.interval.seconds điều khiển tần suất checkpoint được phát ra. sync.group.offsets.interval.seconds điều khiển tần suất ghi translated offsets vào target __consumer_offsets.

Khoảng thời gian dài hơn có thể:

- Giảm số lần poll/commit metadata và tải của connector.
- Làm checkpoint trên target cũ hơn so với tiến độ consumer source.
- Tăng số record có thể reprocess hoặc tăng thời gian chờ trong planned failover.

Khoảng thời gian ngắn hơn giảm độ trễ đồng bộ nhưng không xóa được replication lag của dữ liệu. Checkpoint chỉ dịch được tới vùng record đã replicate và có offset-sync mapping phù hợp.

### 4.4. Chọn consumer groups cần replicate

Chỉ những group được GroupFilter cho phép mới được checkpoint/sync. Kiểm tra:

- groups và groups.exclude.
- Group ID có bị regex loại trừ không.
- Group có commit offset thường xuyên không.
- Topic/partition mà group đọc có nằm trong topic replication flow không.
- Group có phải group nội bộ của Connect, console hoặc ứng dụng khác không.

Default groups.exclude bỏ qua console-consumer-.*, connect-.* và __.*. Nếu lab dùng console consumer để thử offset sync, cần cấu hình include/exclude phù hợp; không mở rộng filter cho mọi group trong production mà không rà soát.

## 5. Replication policy và tên topic ở DR

### 5.1. DefaultReplicationPolicy

MM2 mặc định thêm source cluster alias vào tên remote topic. Ví dụ:

| Primary | DR |
|---|---|
| orders.v1 | primary.orders.v1 |
| payments.v1 | primary.payments.v1 |
| inventory.changed | primary.inventory.changed |

Consumer chuyển sang DR phải subscribe remote topic tương ứng. RemoteClusterUtils cũng dùng replication policy để dịch tên topic trong kết quả.

MM2 giữ partition mapping một-một: partition i của source được replicate thành partition i của remote topic. Remote topic cần cùng số partition với source để giữ mapping và thứ tự record theo partition.

### 5.2. IdentityReplicationPolicy

IdentityReplicationPolicy giữ tên topic gốc ở target, ví dụ orders.v1 vẫn là orders.v1. Cách này tiện khi ứng dụng không muốn đổi topic subscription lúc failover, nhưng phải bảo đảm:

- Target không có local topic trùng tên đang được ghi bởi workload khác.
- Flow topology không làm trộn dữ liệu từ nhiều nguồn vào cùng topic-partition.
- MirrorSourceConnector, MirrorCheckpointConnector và MirrorClient dùng cùng replication policy.
- ACL và quyền producer/consumer trên target phù hợp với tên topic không prefix.

Nếu MirrorMaker dùng DefaultReplicationPolicy mà RemoteClusterUtils được cấu hình IdentityReplicationPolicy, topic mapping sẽ không nhất quán và translation có thể không tìm đúng remote topic.

### 5.3. Chọn policy cho active/passive

Với active/passive, target không nhận write nghiệp vụ trước failover, nên có thể dùng IdentityReplicationPolicy để giữ nguyên tên topic. Sau khi dừng MM2 và chuyển DR thành primary, producer tiếp tục ghi vào cùng topic name mà consumer đang dùng. Đây là cách đơn giản hóa việc chuyển subscription, miễn là target không có local topic trùng tên và ACL được cập nhật để ứng dụng có quyền ghi sau cutover.

Nếu dùng DefaultReplicationPolicy, consumer ở DR đọc topic có prefix source alias, còn producer mới sau failover thường ghi vào local topic không prefix. Ứng dụng phải có chiến lược chuyển từ remote topic sang local topic; không mặc định rằng hai topic tạo thành một log liên tục hoặc có thứ tự toàn cục giữa chúng.

IdentityReplicationPolicy phù hợp khi chỉ có một phía active cho topic đó. Với active/active hoặc nhiều nguồn cùng replicate vào một target, DefaultReplicationPolicy giúp tách stream theo source và tránh ghi các nguồn vào cùng topic-partition.

Khi chọn IdentityReplicationPolicy, cấu hình phải nhất quán trên MirrorSourceConnector, MirrorCheckpointConnector và MirrorClient dùng để dịch offset.

### 5.4. Không ghi trực tiếp vào remote topic khi replication còn chạy

Trong lúc source vẫn active và MM2 còn replicate, remote topic được quản lý như bản sao từ source. Producer nghiệp vụ không nên ghi trực tiếp vào remote topic. Khi failover, source phải được fence và MirrorSourceConnector phải dừng trước khi target trở thành primary. Với IdentityReplicationPolicy, topic cùng tên ở DR có thể chuyển sang nhận write sau cutover; với DefaultReplicationPolicy, topic remote có prefix và topic local sau cutover là hai topic riêng.

## 6. Cấu hình MM2 cho active/passive

Ví dụ sau minh họa một replication flow một chiều từ primary sang dr. Tên và địa chỉ broker chỉ là placeholder; production phải bổ sung TLS/SASL, ACL, Connect worker settings, internal topic replication factor và dung lượng phù hợp.

~~~properties
clusters = primary, dr

primary.bootstrap.servers = primary-broker-1:9092,primary-broker-2:9092
dr.bootstrap.servers = dr-broker-1:9092,dr-broker-2:9092

primary->dr.enabled = true
dr->primary.enabled = false

primary->dr.topics = orders.*, payments.*
primary->dr.groups = orders-consumer, payments-consumer
primary->dr.replication.policy.class = org.apache.kafka.connect.mirror.IdentityReplicationPolicy

# Source connector tạo offset-sync mappings.
primary->dr.emit.offset-syncs.enabled = true
primary->dr.offset.lag.max = 100

# Checkpoint connector tạo checkpoint ở DR.
primary->dr.emit.checkpoints.enabled = true
primary->dr.emit.checkpoints.interval.seconds = 30

# Ghi translated offsets vào __consumer_offsets ở DR.
primary->dr.sync.group.offsets.enabled = true
primary->dr.sync.group.offsets.interval.seconds = 30

# Đặt vị trí offset-syncs topic mặc định ở source.
primary->dr.offset-syncs.topic.location = source
~~~

Trong dedicated MirrorMaker mode, cấu hình theo flow dùng prefix source->target. Nếu triển khai các connector riêng qua Kafka Connect REST API, tên property và phạm vi áp dụng cần theo connector config tương ứng. Không sao chép nguyên file dedicated mode sang standalone connector mà không đổi cấu trúc.

### 6.1. Những điều kiện để tự động sync group offsets

Khi bật sync.group.offsets.enabled:

1. Checkpoint connector phải đọc được offset-sync mappings.
2. Group phải được GroupFilter cho phép.
3. Topic và partition phải được replicate.
4. Translation phải có mapping đủ để tính target offset.
5. Target consumer group không được có consumer member đang hoạt động; MM2 chỉ ghi offset khi group đó không có consumer active trên target.

Điều kiện cuối giúp MM2 không ghi đè tiến độ của consumer đã chạy tại DR. Vì vậy, không khởi động consumer ở DR trước khi offset sync dự kiến hoàn tất nếu muốn consumer tự nhận checkpoint mới nhất.

### 6.2. Kiểm tra internal topics

Kiểm tra topic nội bộ và quyền truy cập:

- Offset-syncs topic trên cluster được chọn bởi offset-syncs.topic.location.
- Checkpoints topic trên target.
- Heartbeat topic.
- __consumer_offsets trên source và target.
- Kafka Connect config/offset/status topics của MM2 worker.

Đặt replication factor và retention phù hợp. Nếu offset-syncs bị xóa quá sớm hoặc checkpoint topic không đủ retention, khả năng phục hồi offset cũ sẽ suy giảm.

## 7. Hai cách đưa consumer sang DR

### 7.1. Cách A — Tự động đồng bộ vào __consumer_offsets

Phù hợp với active/passive khi muốn consumer khởi động ở DR bằng cùng group ID:

1. Bật emit.checkpoints.enabled.
2. Bật sync.group.offsets.enabled.
3. Đảm bảo group được include và topic được replicate.
4. Chờ checkpoint và offset sync chạy ổn định.
5. Khi failover, dừng consumer ở primary và bảo đảm không còn group member hoạt động ở DR.
6. Chờ ít nhất một chu kỳ sync sau committed offset cuối cùng tại source, nếu source còn truy cập được.
7. Khởi động consumer ở DR với cùng group ID và subscription tới remote topic.

Consumer sẽ lấy offset từ __consumer_offsets của target. Với DefaultReplicationPolicy, subscription phải trỏ tới topic có prefix source alias, ví dụ primary.orders.v1. Với IdentityReplicationPolicy như ví dụ active/passive ở trên, consumer tiếp tục dùng tên gốc orders.v1.

Không dùng auto offset sync như bằng chứng target có toàn bộ dữ liệu. Phải xác minh replication lag và log end offset trước khi chuyển.

### 7.2. Cách B — Dịch offset thủ công bằng RemoteClusterUtils

Phù hợp khi:

- sync.group.offsets.enabled chưa được bật.
- Cần dịch group offset trong unplanned failover.
- Muốn lấy checkpoint mới nhất từ checkpoints topic trước khi commit vào target.

RemoteClusterUtils.translateOffsets() nhận:

- Properties kết nối tới target cluster và cấu hình replication policy.
- Alias của source cluster.
- Consumer group ID ở source.
- Timeout để đọc checkpoint topic.

Ví dụ:

~~~java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.CommonClientConfigs;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.connect.mirror.IdentityReplicationPolicy;
import org.apache.kafka.connect.mirror.RemoteClusterUtils;

public final class DrOffsetMigration {

    private DrOffsetMigration() {
    }

    public static void translateAndCommit(
            String drBootstrapServers,
            String sourceAlias,
            String groupId) throws Exception {

        Map<String, Object> mirrorClientProps = new HashMap<>();
        mirrorClientProps.put(
                CommonClientConfigs.BOOTSTRAP_SERVERS_CONFIG,
                drBootstrapServers);
        mirrorClientProps.put(
                "replication.policy.class",
                IdentityReplicationPolicy.class.getName());

        Map<TopicPartition, OffsetAndMetadata> translated =
                RemoteClusterUtils.translateOffsets(
                        mirrorClientProps,
                        sourceAlias,
                        groupId,
                        Duration.ofSeconds(60));

        if (translated.isEmpty()) {
            throw new IllegalStateException(
                    "No translated offsets found for group " + groupId);
        }

        Map<String, Object> adminProps = Map.of(
                CommonClientConfigs.BOOTSTRAP_SERVERS_CONFIG,
                drBootstrapServers);

        try (Admin admin = Admin.create(adminProps)) {
            admin.alterConsumerGroupOffsets(groupId, translated)
                    .all()
                    .get(30, TimeUnit.SECONDS);
        }
    }
}
~~~

Đây là ví dụ rút gọn tương ứng với active/passive flow ở phần cấu hình, dùng IdentityReplicationPolicy để giữ nguyên topic name. Trong production, adminProps và mirrorClientProps phải có security settings, TLS/SASL, timeout và credential provider của DR cluster. Nếu dùng DefaultReplicationPolicy hoặc custom ReplicationPolicy, cấu hình cùng policy thay cho IdentityReplicationPolicy.

RemoteClusterUtils đọc checkpoints topic để tìm offset tương ứng. Thời gian timeout cần đủ lớn với kích thước checkpoint topic và số consumer groups. Không gọi API này trên request path của từng record; đây là thao tác control-plane dùng trong migration/failover.

Sau khi alterConsumerGroupOffsets thành công, khởi động consumer ở DR với cùng group ID và topic mapping phù hợp. Đảm bảo group không có member active trong lúc ghi offset.

Trước khi gọi alterConsumerGroupOffsets, hãy xác nhận group không có consumer member đang hoạt động ở DR. Admin API thay committed offsets của group; nếu consumer đang chạy, nó có thể tiếp tục commit tiến độ khác và tạo race với thao tác failover.

### 7.3. Manual assign/seek

Một lựa chọn khác là ứng dụng lấy map translated offsets rồi assign partition và seek tới vị trí tương ứng. Cách này hữu ích cho quy trình migration tùy chỉnh, nhưng ứng dụng phải tự quản lý partition assignment và commit tiến độ sau đó.

Nếu dùng subscribe/group coordinator bình thường, nên để group lấy committed offset đã được sync ở target thay vì tự trộn hai cơ chế. Không để hai instance cùng group vừa tự seek, vừa nhận assignment từ coordinator mà không có quy trình đồng bộ rõ ràng.

## 8. Điều kiện trước khi chuyển consumer

Offset translation chỉ là một phần của failover. Trước khi khởi động consumer ở DR, cần kiểm tra các điều kiện sau.

### 8.1. Dữ liệu đã được replicate đủ gần

- MirrorSourceConnector và task liên quan đang RUNNING.
- Replication lag nằm trong RPO đã chấp nhận.
- record-age-ms và replication-latency-ms không tăng bất thường.
- Các topic/partition cần thiết đã tồn tại ở target.
- Remote topic có đúng số partition.
- Log end offset target đã tiến tới vùng cần đọc.
- Không có partition replication bị kẹt hoặc filter nhầm.

### 8.2. Checkpoint đủ mới và dịch được

- Group ID được include trong groups filter.
- Consumer source đã commit offset theo chính sách của ứng dụng.
- MirrorCheckpointConnector đã phát checkpoint sau commit gần nhất.
- Offset-syncs topic còn mapping cho partition.
- Target checkpoint topic có dữ liệu và có thể đọc.
- Translation không trả về vị trí chưa khả dụng.
- Nếu cần auto sync, sync.group.offsets.enabled đã bật và group target không active.

### 8.3. Topic mapping chính xác

- Consumer biết tên remote topic tại DR.
- Replication policy giống nhau giữa MM2 và MirrorClient.
- Partition count và partition mapping tương ứng.
- Topic filter không bỏ sót topic phụ thuộc.
- Schema/serializer và converter tương thích.
- ACL của consumer principal cho phép READ topic và group ở DR.

### 8.4. Primary đã được fence hoặc dừng

Trong active/passive, cần bảo đảm chỉ một cluster nhận write cho business stream:

- Dừng producer ở primary khi planned failover.
- Với unplanned failover, xác nhận primary đã mất khả năng phục vụ hoặc được fence khỏi client.
- Chặn producer cũ reconnect về primary sau khi DR đã trở thành primary mới.
- Tránh hai cluster cùng nhận write cho một business key nếu ứng dụng không có conflict-resolution strategy.

### 8.5. Ứng dụng đã sẵn sàng kết nối DR

Kiểm tra bootstrap servers, DNS, TLS certificate, SASL credential, ACL, schema registry, database/API downstream và network route. Failover Kafka không tự chuyển database, object store hoặc dependency khác.

## 9. Planned failover — chuyển cụm có kiểm soát

Planned failover thường cho phép giảm tối đa data gap vì source còn hoạt động và có thể dừng producer để MM2 replicate phần dữ liệu còn lại.

### 9.1. Quy trình

~~~mermaid
sequenceDiagram
    participant P as Primary
    participant M as MirrorMaker 2
    participant D as DR cluster
    participant A as Applications

    A->>P: Stop producers
    M->>P: Finish reading source log
    M->>D: Replicate remaining records
    A->>P: Drain and stop source consumers
    M->>D: Emit final checkpoints
    A->>D: Start producers on DR
    A->>D: Start consumers with translated offsets
~~~

Các bước vận hành:

1. Xác nhận DR cluster khỏe mạnh, topic/partition/ACL đã đồng bộ.
2. Kiểm tra record-age-ms, replication-latency-ms và checkpoint-latency-ms.
3. Dừng tất cả producer ghi vào primary.
4. Chờ MirrorSourceConnector replicate hết phần data gap. Byte-rate/record-rate của connector cho topic cần chuyển sẽ giảm về 0 khi không còn dữ liệu mới cần copy.
5. Dừng MirrorSourceConnector theo quy trình Kafka Connect sau khi đã xác nhận replication drain hoàn tất.
6. Nếu cần failback sau này, ghi lại target Log End Offset của các remote topics.
7. Khởi động producer ghi vào local topic trên DR sau khi primary đã được fence và source replication đã drain.
8. Cho consumer ở primary xử lý tới lag 0 nếu thời gian cho phép. Việc này giúp offset translation chính xác hơn.
9. Dừng consumer ở primary. Nếu dùng tự động offset sync, chờ ít nhất một sync.group.offsets.interval.seconds để checkpoint cuối được ghi vào __consumer_offsets ở DR. Nếu không bật tự động sync, dùng RemoteClusterUtils để dịch checkpoint mới nhất và commit thủ công vào DR.
10. Dừng MirrorCheckpointConnector sau khi offset sync cuối hoàn tất hoặc sau khi đã lấy checkpoint cần dùng.
11. Khởi động consumer ở DR với cùng group ID và remote topic subscription.
12. Theo dõi end-to-end latency, consumer lag, duplicate và business invariants.

Thứ tự thực tế có thể được điều chỉnh theo ứng dụng, nhưng không khởi động consumer DR trước khi chắc chắn offset cần dùng đã được sync/translate. Nếu chạy consumer group ở DR quá sớm, active member có thể ngăn MM2 cập nhật committed offset tự động.

### 9.2. Vì sao planned failover có thể gần như không mất dữ liệu?

Khi producer primary đã dừng, MM2 có thể replicate nốt toàn bộ record còn lại. Khi consumer primary đã xử lý hết và commit offset cuối, checkpoint có thể phản ánh đúng tiến độ đó. Điều kiện này làm giảm hoặc loại bỏ vùng cần reprocess do offset mapping thưa.

Điều này không có nghĩa MM2 tự bảo đảm zero downtime hoặc zero data loss trong mọi cấu hình. Phải xác minh replication drain, checkpoint completion, source consumer commits và ứng dụng downstream.

## 10. Unplanned failover — chuyển cụm khi primary gặp sự cố

Khi primary đã mất, không thể chờ source producer/consumer commit thêm hoặc đợi MirrorMaker replicate phần dữ liệu còn lại.

### 10.1. Xác định RPO thực tế

MM2 replicate bất đồng bộ. Một record đã được producer ACK ở primary có thể chưa tới DR tại thời điểm sự cố.

RPO thực tế phụ thuộc:

- Replication lag và record age.
- Tốc độ producer trước khi sự cố.
- Connector/task health và thời gian mất kết nối.
- Network throughput giữa các cluster.
- Thời điểm cuối cùng dữ liệu được append ở target.

record-age-ms cho biết tuổi record khi được replicate. Có thể dùng byte-rate cuối cùng và thời gian lag để ước lượng lượng dữ liệu có nguy cơ chưa replicate, nhưng đó chỉ là ước lượng; không thay thế việc đối chiếu LEO và dữ liệu nghiệp vụ.

### 10.2. Quy trình

1. Xác nhận primary không còn khả năng phục vụ và quyết định failover theo DR policy.
2. Fence producer/client cũ để tránh split-brain nếu primary hồi phục.
3. Kiểm tra DR topic, partition, ACL, connector status và replication metrics cuối cùng.
4. Dừng hoặc cô lập MirrorSourceConnector/MirrorCheckpointConnector theo tình trạng source và runbook.
5. Lấy checkpoint mới nhất trên DR.
6. Dùng RemoteClusterUtils.translateOffsets() để tính offset target từ checkpoint nếu cần độ mới tốt hơn offset đã sync vào __consumer_offsets.
7. Nếu translation không có kết quả cho partition, không tự đoán offset. Chọn recovery policy rõ ràng như earliest còn giữ được, latest hoặc offset do operator xác định sau khi đối chiếu nghiệp vụ.
8. Commit translated offsets vào target group khi group chưa có member active.
9. Cập nhật bootstrap servers, topic mapping và security config của ứng dụng.
10. Khởi động consumer ở DR; theo dõi duplicate/replay và xác nhận business state.
11. Khởi động producer ở DR sau khi đã fence nguồn cũ.
12. Ghi nhận data gap, RPO thực tế, offset mỗi partition và các thao tác bù dữ liệu.

Nếu source offset mới hơn offset-sync mới nhất, MM2 không thể dịch chính xác vị trí đó. Nếu record cuối cùng chưa replicate, target không có record để consumer đọc; offset translation không thể tái tạo dữ liệu đã mất.

### 10.3. Chọn vị trí khi không thể dịch offset

| Lựa chọn | Hành vi | Khi dùng |
|---|---|---|
| Dùng checkpoint gần nhất | Tiếp tục ở vị trí đã dịch, có thể reprocess | Mặc định ưu tiên khi checkpoint còn hợp lệ |
| Seek earliest | Đọc lại từ đầu log còn retention | Cần giảm nguy cơ bỏ sót, chấp nhận replay lớn |
| Seek latest | Bắt đầu từ cuối log target | Chỉ khi nghiệp vụ cho phép bỏ qua backlog cũ |
| Offset thủ công | Operator chọn vị trí theo LEO/checkpoint/business marker | Cần điều tra và kiểm soát đặc biệt |

Không dùng latest như cách chữa lỗi translation -1 một cách mặc định. Làm vậy có thể bỏ qua record chưa được consumer xử lý.

## 11. RPO, RTO và mức độ duplicate

### 11.1. RPO

Recovery Point Objective là lượng dữ liệu tối đa có thể mất theo kế hoạch. Với MM2 bất đồng bộ, RPO không chỉ phụ thuộc checkpoint interval; nó còn phụ thuộc replication lag của data topic.

Ví dụ:

- Checkpoint được cập nhật mỗi 30 giây.
- Replication data lag đang là 5 giây.
- Primary hỏng đột ngột.

Consumer offset checkpoint có thể cũ tới một khoảng tương ứng với lịch sync, trong khi target data cũng có thể thiếu các record mới nhất chưa replicate. Cần đánh giá cả hai khoảng trễ, không chỉ một config interval.

### 11.2. RTO

Recovery Time Objective là thời gian cần để khôi phục dịch vụ. RTO bao gồm:

- Phát hiện và quyết định failover.
- Fence primary.
- Xác minh target cluster.
- Dịch/sync offset.
- Cập nhật bootstrap/security config.
- Khởi động consumer/producer và rebalance.
- Warm up dependency và xác nhận business flow.

MM2 không tự quyết định failover. Quyết định thuộc operator hoặc automation bên ngoài, còn MM2 cung cấp replication, checkpoint và heartbeat data hỗ trợ quyết định.

### 11.3. Duplicate và idempotency

Offset translation bảo thủ có thể khiến consumer đọc lại record. Duplicate có thể phát sinh:

- Do checkpoint interval.
- Do offset-sync mappings thưa.
- Do consumer source lag.
- Do failover khi replication chưa bắt kịp.
- Do consumer đã xử lý side effect nhưng chưa commit offset.

Consumer nên có event ID/idempotency key, upsert hoặc deduplication store cho side effect quan trọng. Không giả định Kafka offset translation cung cấp exactly-once business processing giữa hai cluster.

## 12. Monitoring và xác nhận readiness

### 12.1. MirrorSourceConnector metrics

| Metric | Ý nghĩa | Cách dùng |
|---|---|---|
| record-rate | Số record replicate mỗi giây | Xác nhận luồng có đang tiến triển |
| byte-rate | Byte replicate mỗi giây | Theo dõi throughput và thời điểm drain |
| record-age-ms | Tuổi record lúc replicate | Ước lượng data gap và RPO |
| replication-latency-ms | Thời gian từ source tới target ACK | Theo dõi độ trễ replication |
| record-count | Tổng số record đã replicate | Đối chiếu volume |

### 12.2. MirrorCheckpointConnector metrics

Theo dõi checkpoint-latency-ms và connector/task status. Checkpoint latency tăng có thể làm target consumer offsets chậm so với source consumer commits.

### 12.3. Kafka cluster metrics

Theo dõi:

- Log end offset và log start offset của remote partitions.
- Consumer lag theo từng partition.
- BytesInPerSec và ReplicationBytesInPerSec.
- Under-replicated partitions và offline replicas tại target.
- Broker request errors, quota throttle và network failures.
- Connect task failures, source-record-poll-rate và connector restart.
- Heartbeat freshness và replication hops nếu dùng RemoteClusterUtils.

Kafka 4.4 monitoring docs liệt kê BytesInPerSec, ReplicationBytesInPerSec và consumer records-lag-max. MM2 còn có metrics riêng cho replication và checkpoint. [Apache Kafka 4.4 Monitoring](https://kafka.apache.org/44/operations/monitoring/); [Apache Kafka 4.4 Geo-Replication](https://kafka.apache.org/44/operations/geo-replication-cross-cluster-data-mirroring/).

### 12.4. Readiness gate trước failover

Một bảng readiness nên có:

| Kiểm tra | Điều kiện chấp nhận |
|---|---|
| Source/target flow | Connector và task cần thiết RUNNING |
| Data replication lag | Nằm trong RPO |
| Checkpoint latency | Nằm trong ngưỡng runbook |
| Offset mapping | Có mapping cho từng partition/group cần chuyển |
| Target topics | Tồn tại, đúng partition count và retention |
| Target ACL | Consumer/producer principal có quyền |
| Target consumer group | Không có member active trước khi sync offset |
| Primary fencing | Không còn producer cũ ghi vào source sau cutover |
| Dependency | Schema, database, API và network sẵn sàng ở DR |

## 13. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Không có checkpoint topic | Checkpoint connector chưa chạy, emit.checkpoints bị tắt hoặc group/topic bị filter | Kiểm tra task, groups filter và connector config |
| Checkpoint có nhưng __consumer_offsets ở DR không đổi | sync.group.offsets.enabled=false hoặc target group đang active | Bật sync và dừng member target trước khi đồng bộ |
| Translation trả offset -1/không có kết quả | Source commit mới hơn latest offset-sync mapping | Đợi replication nếu source còn hoạt động; nếu source mất, áp dụng recovery position policy |
| Consumer đọc sai topic ở DR | DefaultReplicationPolicy prefix chưa được áp dụng | Subscribe remote topic hoặc thống nhất IdentityReplicationPolicy |
| Translation timeout | Checkpoint topic lớn hoặc MirrorClient không đủ quyền/timeout | Tăng timeout hợp lý, kiểm tra ACL và checkpoint topic |
| Một partition không có translated offset | Partition chưa được replicate hoặc mapping bị thiếu | Kiểm tra topic filter, partition mapping và offset-syncs |
| Consumer target không nhận offset mới | Group member đang hoạt động trên target | Dừng group member, chờ sync interval rồi kiểm tra lại |
| Duplicate nhiều sau failover | Mapping thưa, checkpoint cũ hoặc consumer source lag | Giảm offset.lag.max sau benchmark, rút ngắn interval, tăng idempotency |
| DR topic thiếu record mới | Replication bất đồng bộ chưa bắt kịp trước sự cố | Đánh giá RPO và phục hồi dữ liệu từ nguồn khác nếu có |
| MirrorMaker heartbeat vẫn có nhưng topic lag lớn | Heartbeat chỉ chứng minh một phần connectivity | Theo dõi record-age, replication latency và partition-level metrics |

## 14. Checklist trước, trong và sau failover

### Trước failover

- [ ] Đã xác định primary, DR và replication flow đúng chiều.
- [ ] Topic filters bao gồm toàn bộ topic nghiệp vụ cần phục hồi.
- [ ] Consumer group filters bao gồm group cần chuyển.
- [ ] Offset-syncs và checkpoints topic tồn tại, có replication factor/retention phù hợp.
- [ ] Replication policy thống nhất giữa MM2 và RemoteClusterUtils.
- [ ] Remote topics có đúng partition count.
- [ ] record-age-ms, replication-latency-ms và checkpoint-latency-ms nằm trong ngưỡng.
- [ ] DR ACL, security credentials và dependencies đã sẵn sàng.
- [ ] Có kế hoạch fence primary và ngăn producer ghi đồng thời.

### Trong failover

- [ ] Planned: dừng producer source và chờ replication drain.
- [ ] Planned: dừng MirrorSourceConnector sau khi đã xác nhận drain.
- [ ] Planned: dừng source consumers sau khi xử lý/commit đến vị trí đã chọn.
- [ ] Đảm bảo target consumer group không active khi ghi translated offsets.
- [ ] Dùng auto sync hoặc RemoteClusterUtils theo đúng runbook.
- [ ] Không tự đoán offset khi translation không khả dụng.
- [ ] Cập nhật bootstrap servers và remote topic mapping.
- [ ] Chỉ bật producer ở DR sau khi primary đã được fence.

### Sau failover

- [ ] Consumer group chạy ổn định và lag có xu hướng giảm.
- [ ] Không có partition bị bỏ sót hoặc offset out of range.
- [ ] Duplicate được xử lý an toàn ở business layer.
- [ ] Producer chỉ ghi vào cluster đang active.
- [ ] RPO/RTO thực tế được ghi lại.
- [ ] Có kế hoạch tái tạo DR và failback trước khi xem hệ thống đã phục hồi hoàn toàn.

## 15. Bài thực hành và tự kiểm tra

### Thực hành A — Tạo offset mappings và checkpoints

1. Dựng hai Kafka cluster lab: primary và dr.
2. Tạo topic orders.v1 với ba partition ở primary.
3. Cấu hình MM2 replicate orders.v1 từ primary sang dr.
4. Dùng IdentityReplicationPolicy như cấu hình active/passive mẫu và xác nhận topic orders.v1 xuất hiện ở DR. Nếu thử DefaultReplicationPolicy, xác nhận topic primary.orders.v1.
5. Tạo consumer group orders-consumer và commit offset trên primary.
6. Bật checkpoint connector, quan sát offset-syncs và checkpoints topics.
7. So sánh source committed offsets với target translated offsets theo từng partition.

### Thực hành B — Automatic offset sync

1. Bật emit.checkpoints.enabled và sync.group.offsets.enabled.
2. Đặt checkpoint/sync interval ngắn trong môi trường lab.
3. Đảm bảo target consumer group chưa có member active.
4. Chờ offset sync hoàn tất.
5. Dùng kafka-consumer-groups.sh --describe trên DR để kiểm tra committed offsets.
6. Khởi động consumer DR với cùng group ID và remote topic subscription.
7. Xác nhận consumer tiếp tục từ vị trí đã dịch.

### Thực hành C — Manual translation

1. Tắt sync.group.offsets.enabled nhưng vẫn phát checkpoints.
2. Commit offset ở source consumer group.
3. Chạy chương trình Java dùng RemoteClusterUtils.translateOffsets().
4. In map topic-partition và translated offset.
5. Dùng Admin.alterConsumerGroupOffsets() ghi map vào target.
6. Khởi động consumer ở DR và xác nhận vị trí tiếp tục.
7. Thử timeout thấp và kiểm tra cách xử lý lỗi.

### Thực hành D — Planned failover

1. Tạo traffic producer liên tục ở primary.
2. Quan sát record-age-ms và replication-latency-ms.
3. Dừng producer primary.
4. Chờ replication byte-rate/record-rate giảm về 0.
5. Dừng MirrorSourceConnector.
6. Cho consumer primary xử lý hết backlog và commit offset.
7. Chờ sync.group.offsets.interval.seconds.
8. Dừng checkpoint connector, chuyển consumer sang DR.
9. Kiểm tra duplicate, consumer lag và end-to-end processing.

### Thực hành E — Unplanned failover

1. Tạo workload và consumer lag ở primary.
2. Dừng primary đột ngột trước khi MM2 replicate hết dữ liệu.
3. Xác nhận record-age và checkpoint latency cuối cùng.
4. Dịch offset từ checkpoint bằng RemoteClusterUtils.
5. Xác định partition không có mapping.
6. Chọn recovery position theo policy và giải thích RPO.
7. Khởi động consumer ở DR, xác nhận không bỏ qua record đã replicate.
8. Ghi lại số record có thể mất và số record được reprocess.

### Câu hỏi tự kiểm tra

1. Vì sao offset 500 ở primary không nhất thiết tương ứng offset 500 ở DR?
2. Committed offset N có nghĩa record tiếp theo cần đọc là offset nào?
3. Offset-syncs topic và checkpoints topic khác nhau thế nào?
4. MirrorSourceConnector và MirrorCheckpointConnector chịu trách nhiệm gì?
5. Vì sao MM2 không ghi mapping cho mọi record?
6. Khi nào offset translation có thể chính xác?
7. Vì sao offset translation gần đúng có thể tạo duplicate nhưng tránh bỏ qua dữ liệu?
8. Điều gì xảy ra nếu consumer commit offset mới hơn latest offset-sync?
9. offset.lag.max ảnh hưởng precision và overhead ra sao?
10. emit.checkpoints.enabled khác sync.group.offsets.enabled thế nào?
11. Vì sao target group đang active sẽ ngăn MM2 ghi offset tự động?
12. DefaultReplicationPolicy ảnh hưởng tên topic ở DR ra sao?
13. Khi nào cần IdentityReplicationPolicy?
14. Điều kiện nào phải đạt trước planned failover?
15. Unplanned failover ảnh hưởng RPO thế nào?
16. Vì sao heartbeat thành công chưa đủ chứng minh DR sẵn sàng?
17. RemoteClusterUtils.translateOffsets() dùng checkpoint topic để làm gì?
18. Vì sao phải fence primary trước khi producer ghi vào DR?
19. Consumer cần thiết kế thế nào để xử lý record reprocessing?
20. RPO và RTO được hình thành từ những thành phần nào trong MM2 failover?

## Kết luận

Offset translation là bước cần thiết khi consumer di chuyển giữa các Kafka cluster vì mỗi cluster có log offset riêng. MM2 dùng offset-sync mappings và checkpoints để tìm vị trí tương ứng theo từng topic-partition. Translation có thể gần đúng và ưu tiên reprocess thay vì bỏ sót record; offset mới hơn vùng đã replicate có thể chưa dịch được. Có thể đồng bộ translated offsets tự động vào __consumer_offsets của DR hoặc dịch thủ công bằng RemoteClusterUtils. Trước khi chuyển consumer, cần xác nhận replication lag, checkpoint freshness, topic mapping, target group state, security và việc fence primary. Planned failover có thể giảm data gap bằng cách dừng producer và drain replication; unplanned failover phải chấp nhận RPO theo dữ liệu chưa replicate và xử lý duplicate bằng idempotency ở ứng dụng.

## Tài liệu tham khảo

- [Apache Kafka 4.4 — MirrorMaker Configs](https://kafka.apache.org/44/configuration/mirrormaker-configs/)
- [Apache Kafka 4.4 — Geo-Replication](https://kafka.apache.org/44/operations/geo-replication-cross-cluster-data-mirroring/)
- [Apache Kafka 4.4 — RemoteClusterUtils Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/connect/mirror/RemoteClusterUtils.html)
- [Apache Kafka KIP-382 — MirrorMaker 2.0](https://cwiki.apache.org/confluence/display/KAFKA/KIP-382%3A+MirrorMaker+2.0)
- [Red Hat — Translating offsets between clusters](https://docs.redhat.com/en/documentation/red_hat_streams_for_apache_kafka/3.2/html/disaster_recovery_using_mirrormaker_2/con-mm2-offset-translation-str)
- [Red Hat — Failing over to a disaster recovery cluster](https://docs.redhat.com/en/documentation/red_hat_streams_for_apache_kafka/3.2/html/disaster_recovery_using_mirrormaker_2/con-mm2-failover-str)
