# MirrorSourceConnector, MirrorCheckpointConnector và MirrorHeartbeatConnector

## Mục tiêu bài học

Một Kafka cluster có thể chịu lỗi broker nhờ replication trong cùng cluster, nhưng replication nội bộ không bảo vệ hệ thống trước sự cố toàn bộ data center, region hoặc cluster. Khi cần disaster recovery, migration hoặc chia sẻ dữ liệu giữa nhiều môi trường, Kafka có thể dùng MirrorMaker 2 (MM2) để sao chép dữ liệu giữa các cluster.

MirrorMaker 2 chạy trên Kafka Connect và sử dụng ba connector chính:

- **MirrorSourceConnector** đọc record từ source cluster và ghi sang target cluster, đồng thời quản lý remote topics, topic configs, ACLs và offset-sync metadata.
- **MirrorCheckpointConnector** tạo checkpoint cho consumer group, dịch offset từ source topic sang remote topic và tùy chọn đồng bộ translated offsets vào consumer group ở target.
- **MirrorHeartbeatConnector** phát heartbeat để xác nhận replication flow còn hoạt động và hỗ trợ đo độ trễ giữa các cluster.

Ba connector giải quyết ba phần khác nhau của replication. MirrorSource sao chép dữ liệu; MirrorCheckpoint giúp khôi phục vị trí đọc của consumer; MirrorHeartbeat giúp quan sát đường đi giữa các cluster. Một hệ thống DR cần cả ba phần, cùng quy trình fencing, chuyển traffic và kiểm thử recovery.

Sau bài học, người học có thể:

- Phân biệt replication nội bộ Kafka với geo-replication giữa các cluster.
- Giải thích vai trò và luồng dữ liệu của ba MM2 connectors.
- Hiểu remote topic naming, offset-sync topics, checkpoints và heartbeat topics.
- Cấu hình replication flow một chiều và hai chiều.
- Chọn topic/group filters và replication factor cho target.
- Hiểu cách dịch consumer offsets và giới hạn độ chính xác khi failover.
- Theo dõi replication latency, record age, checkpoint latency và task status.
- Bảo vệ replication flow bằng TLS/SASL và ACL.
- Thực hiện failover/failback theo runbook có fencing.
- Kiểm thử connector, lag, duplicate và khả năng phục hồi trước khi đưa vào production.

## 1. Multi-cluster replication giải quyết bài toán nào?

Replication factor của Kafka bảo vệ partition khi một broker trong cùng cluster gặp lỗi. Các replicas cùng thuộc một cluster, dùng cùng metadata và controller quorum. Nếu cả cluster hoặc region không còn truy cập được, các replicas trong cluster đó cũng có thể không dùng được.

Multi-cluster replication sao chép record từ một Kafka cluster sang cluster khác. Hai cluster có broker, controller, metadata, storage và consumer groups riêng. MM2 kết nối source và target qua Kafka clients, đọc từ source rồi produce vào target.

~~~mermaid
flowchart LR
    subgraph A["Source cluster: primary"]
        P["Producer"] --> T["orders"]
        T --> S["MirrorSourceConnector"]
        G["Consumer group"]
        CP["MirrorCheckpointConnector"]
        HB["MirrorHeartbeatConnector"]
    end
    subgraph M["MirrorMaker 2 / Kafka Connect"]
        MS["Source tasks"]
        MC["Checkpoint task"]
        MH["Heartbeat task"]
    end
    subgraph B["Target cluster: secondary"]
        RT["primary.orders"]
        CK["primary.checkpoints.internal"]
        HT["heartbeats"]
        C["Standby consumer"]
    end
    S --> MS
    MS --> RT
    CP --> MC
    MC --> CK
    HB --> MH
    MH --> HT
    RT --> C
~~~

Các use case phổ biến:

- Active/passive disaster recovery.
- Active/active giữa hai data centers.
- Cloud migration hoặc hybrid cloud.
- Tập trung dữ liệu từ nhiều cluster vào một cluster analytics.
- Fan-out dữ liệu từ một cluster đến nhiều vùng.
- Tách biệt môi trường production, testing hoặc compliance.

### 1.1. Replication nội bộ và geo-replication

| Tiêu chí | Replication trong cluster | MirrorMaker 2 giữa cluster |
|---|---|---|
| Phạm vi | Broker replicas của cùng partition trong một cluster | Record từ topic source sang remote topic ở cluster khác |
| Metadata | Dùng chung cluster metadata | Mỗi cluster có metadata riêng |
| Offset | Replica giữ cùng log offset/partition identity | Offset ở target có thể khác source |
| Leader | Kafka controller chọn leader trong cluster | Target có leader riêng cho remote topic |
| Failure domain | Broker/rack/zone trong cluster | Data center/region/cluster |
| Consumer group | Group offsets được quản lý tại cluster | Checkpoint và offset translation hỗ trợ chuyển group |
| Mục tiêu | Availability và durability trong cluster | Geo-replication, migration và DR |

MM2 không phải cơ chế đồng bộ disk replica giữa hai cluster. Nó consume records ở source và produce records mới ở target. Vì vậy offset, timestamp, replication factor, topic name và consumer offsets cần được quản lý theo semantics của MM2.

### 1.2. RPO và RTO

Hai mục tiêu cần thống nhất trước khi thiết kế:

- **RPO (Recovery Point Objective)**: lượng dữ liệu tối đa có thể mất khi chuyển sang cluster dự phòng.
- **RTO (Recovery Time Objective)**: thời gian tối đa để khôi phục dịch vụ sau sự cố.

MM2 replication là luồng bất đồng bộ. Nếu source cluster mất đột ngột, các record chưa kịp replicate sang target có thể không có ở target. RPO phụ thuộc replication lag, throughput, network và thời điểm failure.

RTO không chỉ là thời gian bật consumer ở target. Nó còn bao gồm phát hiện sự cố, fencing source, xác minh remote topics, khôi phục group offsets, chuyển producer/consumer traffic và kiểm tra business correctness.

Heartbeat đến target không chứng minh mọi record nghiệp vụ đã được replicate. Cần theo dõi cả replication latency, record age, lag và checkpoint state.

## 2. Kiến trúc MirrorMaker 2

MM2 được xây dựng trên Kafka Connect. Trong dedicated mode, tiến trình được khởi chạy bằng `connect-mirror-maker.sh` và cấu hình trong `connect-mirror-maker.properties`.

MM2 sử dụng:

- Kafka consumer để đọc source cluster.
- Kafka producer để ghi target cluster.
- Admin client để khám phá topic, partition, configs và ACLs.
- Kafka Connect worker/task lifecycle để phân phối và phục hồi connector tasks.
- Internal topics để lưu offset mappings, checkpoints và heartbeat records.

Một replication flow có hướng:

~~~text
source-cluster -> target-cluster
~~~

Ví dụ `primary->secondary` chỉ có nghĩa dữ liệu đi từ primary sang secondary. Nếu cần hai chiều, phải bật cả hai flow.

### 2.1. Các thành phần và nhiệm vụ

| Thành phần | Đọc từ | Ghi vào | Nhiệm vụ |
|---|---|---|---|
| MirrorSourceConnector | Source topics | Remote topics ở target; offset-sync metadata | Replicate records và topic metadata |
| MirrorCheckpointConnector | Source consumer group offsets và offset-sync metadata | Checkpoint topic ở target; tùy chọn target `__consumer_offsets` | Hỗ trợ chuyển consumer group |
| MirrorHeartbeatConnector | Cấu hình/alias của replication flow | Heartbeat topic ở target | Kiểm tra kết nối và replication path |

Ba connector có thể được cấu hình trong cùng một MM2 flow. Nếu tắt heartbeat hoặc checkpoint, record replication vẫn có thể chạy nhưng khả năng quan sát và phục hồi consumer sẽ giảm.

### 2.2. Dedicated mode và Kafka Connect worker

Kafka hỗ trợ chạy MM2 như một dedicated cluster hoặc chạy connector trong Kafka Connect deployment phù hợp. Cấu hình và tên thuộc tính có thể khác giữa các deployment mode.

Ví dụ bài học dùng dedicated mode:

~~~bash
bin/connect-mirror-maker.sh connect-mirror-maker.properties
~~~

Không dùng lẫn file cấu hình của dedicated MirrorMaker với connector JSON REST API mà không kiểm tra deployment mode. Các ví dụ trong bài theo cú pháp `connect-mirror-maker.properties` của dedicated mode.

### 2.3. Replication flow là directional

~~~mermaid
flowchart LR
    A["Cluster A"] --> B["Cluster B"]
    B --> A
~~~

Hai mũi tên là hai replication flows độc lập. Bật `A->B` không tự bật `B->A`. Trong active/passive, chỉ một hướng được bật để target làm standby. Trong active/active, cần bật cả hai và có chiến lược rõ ràng cho nơi ghi dữ liệu.

## 3. MirrorSourceConnector: sao chép topic và record

MirrorSourceConnector là thành phần chính để replicate dữ liệu nghiệp vụ. Nó tạo source tasks đọc topic/partition ở source, sau đó ghi record vào remote topic ở target.

Các trách nhiệm chính:

- Khám phá topic mới và partition mới.
- Chọn topic theo include/exclude filters.
- Tạo remote topics trên target khi cần.
- Consume source records và produce sang target.
- Giữ partition mapping phù hợp với source topic.
- Đồng bộ topic configs và ACLs nếu được bật và có quyền.
- Phát offset-sync records để ánh xạ source offset sang target offset.

### 3.1. Remote topic naming

Mặc định `DefaultReplicationPolicy` thêm source cluster alias vào tên topic ở target:

~~~text
Source cluster: primary
Source topic:   orders
Target cluster: secondary
Remote topic:   primary.orders
~~~

Prefix giúp phân biệt record đến từ các cluster khác nhau và giảm nguy cơ hai flow ghi vào cùng một topic-partition.

Ví dụ:

| Source cluster | Source topic | Target topic |
|---|---|---|
| primary | orders | primary.orders |
| primary | payments | primary.payments |
| secondary | orders | secondary.orders |

Trong active/active, hai cluster có thể cùng có topic `orders` và replicate qua lại mà remote topics vẫn phân biệt nguồn.

### 3.2. ReplicationPolicy

`ReplicationPolicy` quyết định tên remote topic và cách MM2 nhận diện topic nguồn, topic remote và internal topics.

Các policy thường gặp:

- `DefaultReplicationPolicy`: thêm source alias vào tên remote topic; phù hợp với multi-cluster replication và ngăn collision.
- `IdentityReplicationPolicy`: giữ nguyên tên topic; chỉ dùng khi kiến trúc đã có quy tắc naming và loop prevention rõ ràng.
- Custom policy: triển khai khi cần naming convention riêng.

Không đổi policy tùy tiện sau khi đã replicate dữ liệu. Nếu đổi từ prefix naming sang identity naming, ứng dụng có thể đọc nhầm topic, tạo duplicate hoặc mất khả năng nhận diện upstream topic.

### 3.3. Partition mapping

MM2 giữ partition mapping của source topic trong remote topic để record cùng source partition tiếp tục nằm ở partition tương ứng ở target. Tuy nhiên:

- Offset của record ở target không nhất thiết bằng offset source.
- Target topic cần có partition count tương thích.
- Partition count thay đổi ở source cần được phát hiện và xử lý theo refresh interval.
- Không tự tạo remote topic cùng tên rồi cấu hình partition count khác với chủ đích của MM2.

Kafka partition ordering được giữ trong phạm vi cách source task đọc và target producer ghi theo partition. Không giả định thứ tự toàn cục giữa các partition.

### 3.4. Topic configuration và ACL sync

MirrorSourceConnector có thể đồng bộ topic configs và ACLs:

| Config | Ý nghĩa |
|---|---|
| `sync.topic.configs.enabled` | Đồng bộ topic configs từ source sang remote topic |
| `sync.topic.configs.interval.seconds` | Chu kỳ đồng bộ config |
| `sync.topic.acls.enabled` | Đồng bộ ACLs của topic |
| `sync.topic.acls.interval.seconds` | Chu kỳ đồng bộ ACL |
| `config.properties.exclude` | Loại trừ một số topic configs không nên copy |
| `topics` | Topic include filter |
| `topics.exclude` | Topic exclude filter; exclude có ưu tiên |

Một số config được loại trừ mặc định vì có ý nghĩa riêng ở cluster đích, ví dụ `min.insync.replicas` và các throttling properties. Hãy kiểm tra config filter trước khi cho rằng target topic có toàn bộ cấu hình giống source.

Target cần đủ broker và replication factor phù hợp. Replication factor mặc định của remote topics trong Kafka 4.4 là 2; production nên cấu hình theo số broker, zone và durability requirement của target.

### 3.5. Topic filters

Ví dụ chỉ replicate các topic nghiệp vụ:

~~~properties
primary->secondary.topics=orders.*,payments.*
primary->secondary.topics.exclude=orders.internal,orders.debug
~~~

Exclude có ưu tiên hơn include. Regex cần được kiểm tra trên topic name thực tế; một pattern quá rộng có thể replicate cả topic nội bộ hoặc dữ liệu không thuộc scope.

Default filter loại trừ một số internal topics, topic replica và topic bắt đầu bằng `__`. Không thay filter mặc định nếu chưa hiểu MM2 internal topics.

## 4. Offset-sync topic: ánh xạ offset giữa hai cluster

Do MM2 consume record ở source và produce record mới ở target, offset hai bên có thể khác nhau. MirrorCheckpointConnector không thể chỉ copy số offset source sang target.

MirrorSourceConnector phát offset-sync records để mô tả quan hệ:

~~~text
source topic-partition + source offset
                |
                v
target remote topic-partition + target offset
~~~

Offset-sync topic lưu mapping giữa source offset và target offset. Theo cấu hình mặc định của Kafka 4.4, offset-sync topic đặt ở source cluster; có thể đổi vị trí bằng `offset-syncs.topic.location`.

### 4.1. Vì sao cần offset mapping?

Ví dụ:

| Record | Source offset | Target offset |
|---|---:|---:|
| Event A | 100 | 80 |
| Event B | 101 | 81 |
| Event C | 102 | 82 |

Consumer group ở source đã commit offset 102. Nếu target consumer bắt đầu từ offset 102, nó sẽ bỏ qua một số record vì target offset chỉ mới đến 82.

Offset-sync mapping giúp dịch vị trí đọc từ source log sang target remote topic.

### 4.2. emit.offset-syncs.enabled

`emit.offset-syncs.enabled` điều khiển việc ghi offset-sync metadata. Giá trị mặc định là true.

Không tắt setting này nếu đang dùng:

- `emit.checkpoints.enabled=true`, hoặc
- `sync.group.offsets.enabled=true`.

Nếu offset-sync records không được tạo, MirrorCheckpointConnector không thể dịch group offsets chính xác.

### 4.3. offset.lag.max

`offset.lag.max` điều khiển ngưỡng chênh lệch downstream offset so với lần sync trước để MirrorSourceTask tạo offset-sync record mới.

Trong Kafka 4.4, giá trị mặc định là 100:

- Giá trị thấp hơn tạo mapping thường xuyên hơn, checkpoint chính xác hơn.
- Giá trị cao hơn giảm lượng offset-sync metadata nhưng có thể làm tăng số record phải xử lý lại khi failover.
- Giá trị 0 buộc tạo offset-sync cho mọi replicated record, tăng độ chính xác nhưng làm tăng overhead.

Ước lượng sơ bộ trong tài liệu Kafka:

~~~text
Approximate duplicate records
    ~ partition count * offset.lag.max
~~~

Đây chỉ là ước lượng. Số duplicate thực tế còn phụ thuộc thời điểm checkpoint, consumer lag, replication timing và trạng thái từng partition.

## 5. MirrorCheckpointConnector: checkpoint và consumer offset recovery

MirrorCheckpointConnector theo dõi consumer groups ở source cluster và phát checkpoint records sang target cluster. Checkpoint cho biết group đã đọc đến đâu ở source và vị trí tương ứng trong remote topic.

Nó giúp chuyển consumer workload sang target mà không phải đoán offset bằng tay.

### 5.1. Checkpoint record

Checkpoint gắn với:

- Consumer group ID.
- Source topic và partition.
- Source consumer offset.
- Target remote topic và partition.
- Target offset đã được dịch qua offset-sync mapping.

Checkpoint được ghi vào internal checkpoints topic ở target cluster. Topic name do ReplicationPolicy quyết định; thường có dạng:

~~~text
primary.checkpoints.internal
~~~

Đây là metadata nội bộ của MM2, không phải topic nghiệp vụ để ứng dụng consume trực tiếp.

### 5.2. emit.checkpoints.enabled

`emit.checkpoints.enabled` bật/tắt việc phát checkpoint. Trong Kafka 4.4, mặc định là true.

`emit.checkpoints.interval.seconds` quyết định chu kỳ phát checkpoint; mặc định là 60 giây. Khoảng thời gian càng ngắn thì checkpoint cập nhật thường xuyên hơn, nhưng tăng hoạt động metadata và connector workload.

Checkpoint interval không phải cam kết RPO tuyệt đối. Nếu source consumer đã xử lý nhiều record nhưng chưa commit, checkpoint chỉ có thể phản ánh offset đã commit. Nếu source replication chưa catch up, offset mapping có thể chưa có đủ dữ liệu.

### 5.3. Group filters

`groups` chọn consumer groups cần replicate. `groups.exclude` loại trừ các group không cần checkpoint.

Default exclude thường bao gồm:

- `console-consumer-.*`
- `connect-.*`
- `__.*`

Các group thử nghiệm tạo bằng `kafka-console-consumer.sh` có thể bị loại trừ. Khi test, cần kiểm tra filter hoặc dùng group ID ứng dụng rõ ràng.

Không replicate mọi group một cách mù quáng. Chỉ chọn group của ứng dụng cần chuyển vùng; các group nội bộ, monitoring hoặc Connect workers có thể không nên đồng bộ.

### 5.4. sync.group.offsets.enabled

Phát checkpoint và ghi translated offsets vào target `__consumer_offsets` là hai thao tác khác nhau.

| Setting | Tác dụng |
|---|---|
| `emit.checkpoints.enabled` | Ghi checkpoint metadata sang target |
| `sync.group.offsets.enabled` | Ghi translated offsets vào consumer group ở target |
| `sync.group.offsets.interval.seconds` | Chu kỳ đồng bộ group offsets |

Trong Kafka 4.4, `sync.group.offsets.enabled` mặc định false. Khi bật, MM2 chỉ ghi translated offsets vào `__consumer_offsets` của target nếu group đó không có consumer đang hoạt động trên target cluster.

Điều kiện này tránh việc MM2 ghi đè offset của một group đang thực sự chạy ở target.

Không khởi chạy consumer standby với cùng group ID trên target trước khi hiểu hành vi đồng bộ offset. Nếu group đã active, MM2 sẽ không sync offsets vào `__consumer_offsets` theo setting này.

### 5.5. MirrorClient và RemoteClusterUtils

Kafka cung cấp RemoteClusterUtils và MirrorClient để truy vấn, dịch remote consumer offsets dựa trên checkpoint metadata. Javadoc khuyến nghị dùng RemoteClusterUtils khi có thể vì đây là lớp tiện ích bao MirrorClient.

Ví dụ Java minh họa:

~~~java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.connect.mirror.RemoteClusterUtils;

public class ReadRemoteOffsets {

    public static void main(String[] args) throws Exception {
        Map<String, Object> props = new HashMap<>();
        props.put(
            "bootstrap.servers",
            "secondary-broker-1:9092"
        );
        // Bổ sung security settings phù hợp với target cluster.

        Map<TopicPartition, OffsetAndMetadata> offsets =
            RemoteClusterUtils.translateOffsets(
                props,
                "primary",
                "orders-service",
                Duration.ofSeconds(10)
            );

        offsets.forEach((partition, offset) ->
            System.out.printf(
                "%s -> %d%n",
                partition,
                offset.offset()
            )
        );
    }
}
~~~

Đây là ví dụ API minh họa theo Kafka client version; cần bổ sung dependency Kafka mirror package tương thích và security settings cho target cluster. RemoteClusterUtils sử dụng các client nội bộ để đọc checkpoint metadata. Nếu không có checkpoint hoặc offset-sync metadata mới nhất, kết quả có thể không phản ánh chính xác vị trí xử lý cuối cùng.

## 6. MirrorHeartbeatConnector: heartbeat và khả năng quan sát

MirrorHeartbeatConnector phát heartbeat records để xác nhận replication flow còn hoạt động và hỗ trợ theo dõi độ trễ giữa source và target.

Heartbeat không phải business event. Nó giúp trả lời:

- MM2 có còn kết nối và phát tín hiệu đến target không?
- Replication flow có đang chuyển record qua cluster không?
- Đường replication có bị gián đoạn hoặc trễ bất thường không?
- Trong topology nhiều cluster, dữ liệu có thể đi qua các hop nào?

### 6.1. Heartbeat topic

Heartbeat records được phát vào heartbeat topic theo ReplicationPolicy. Với DefaultReplicationPolicy, heartbeat topic có tên đặc biệt để phân biệt cluster alias và remote flow.

Không hard-code heartbeat topic name trong ứng dụng. Dùng policy/version của MM2 để xác định topic thực tế và kiểm tra bằng Kafka CLI.

### 6.2. Heartbeat settings

| Config | Ý nghĩa |
|---|---|
| `emit.heartbeats.enabled` | Bật/tắt phát heartbeat |
| `emit.heartbeats.interval.seconds` | Chu kỳ heartbeat |
| `heartbeats.topic.replication.factor` | Replication factor của heartbeat topic |
| `heartbeats.replication.enabled` | Cho phép replicate heartbeat topic kể cả khi topic filter không include |

Trong Kafka 4.4:

- `emit.heartbeats.enabled` mặc định true.
- `emit.heartbeats.interval.seconds` mặc định 1 giây.
- `heartbeats.topic.replication.factor` mặc định 3.
- `heartbeats.replication.enabled` mặc định true.

Nếu target cluster chỉ có một hoặc hai broker, phải điều chỉnh internal topic replication factor phù hợp. Nếu replication factor lớn hơn số broker, topic creation có thể thất bại.

Các internal topic replication factors trong Kafka 4.4 có mặc định:

| Config | Topic | Default |
|---|---|---:|
| `offset-syncs.topic.replication.factor` | Offset-sync topic | 3 |
| `checkpoints.topic.replication.factor` | Checkpoint topic | 3 |
| `heartbeats.topic.replication.factor` | Heartbeat topic | 3 |
| `replication.factor` | Remote business topics mới tạo | 2 |

Đặt các giá trị này theo số broker và durability policy của từng cluster. Offset-sync topic mặc định nằm ở source cluster; checkpoint và heartbeat topics được ghi ở target theo replication flow.

### 6.3. Heartbeat không thay thế replication metrics

Heartbeat có thể vẫn tới target dù một topic cụ thể bị filter hoặc task cho topic đó gặp lỗi. Vì vậy:

- Dùng heartbeat để kiểm tra connectivity/path.
- Dùng `replication-latency-ms` và `record-age-ms` để theo dõi data flow.
- Dùng task status và error logs để phát hiện connector failures.
- Dùng target topic offsets/lag để xác minh dữ liệu nghiệp vụ thực sự đã tới.

Không tuyên bố cluster đã sẵn sàng failover chỉ vì heartbeat mới nhất còn xuất hiện.

## 7. Ba connector phối hợp như thế nào?

~~~mermaid
sequenceDiagram
    participant S as Source cluster
    participant MS as MirrorSourceConnector
    participant T as Target cluster
    participant MC as MirrorCheckpointConnector
    participant MH as MirrorHeartbeatConnector
    participant C as Standby consumer

    MS->>S: Poll source topic partitions
    S-->>MS: Records + source offsets
    MS->>T: Produce remote topic records
    MS->>S: Write offset-sync mapping
    MC->>S: Read committed group offsets
    MC->>S: Read offset-sync mapping
    MC->>T: Write checkpoint records
    MH->>T: Emit heartbeat
    Note over T,C: Target stores remote topics and MM2 metadata
    C->>T: Start after failover with translated offsets
~~~

Một chu kỳ bình thường:

1. MirrorSourceTask đọc record ở source partition.
2. Task produce record vào remote topic ở target.
3. Task ghi offset-sync mapping để liên kết source và target offsets.
4. MirrorCheckpointTask đọc committed offsets của consumer groups và offset-sync metadata.
5. Checkpoint được phát vào target internal topic.
6. MirrorHeartbeatTask phát heartbeat để kiểm tra replication flow.
7. Monitoring đối chiếu replication latency, checkpoint latency và heartbeat age.

Các connector chạy độc lập theo task lifecycle. Source replication có thể tiếp tục trong khi checkpoint task lỗi; khi đó data đã đến target nhưng consumer offset recovery có thể không cập nhật.

## 8. Cấu hình active/passive một chiều

Active/passive là mẫu phổ biến cho disaster recovery:

~~~text
Primary (active)  ----MM2---->  Secondary (standby)
Producer/Consumer               Chưa nhận traffic nghiệp vụ
~~~

Ví dụ file `connect-mirror-maker.properties`:

~~~properties
# Cluster aliases and bootstrap servers
clusters=primary,secondary
primary.bootstrap.servers=primary-1:9092,primary-2:9092
secondary.bootstrap.servers=secondary-1:9092,secondary-2:9092

# Enable one-way replication
primary->secondary.enabled=true
secondary->primary.enabled=false

# Business topics and consumer groups to mirror
primary->secondary.topics=orders.*,payments.*
primary->secondary.groups=orders-service,payments-service

# Checkpoint and heartbeat
primary->secondary.emit.checkpoints.enabled=true
primary->secondary.emit.checkpoints.interval.seconds=30
primary->secondary.sync.group.offsets.enabled=false
primary->secondary.emit.heartbeats.enabled=true
primary->secondary.emit.heartbeats.interval.seconds=1

# Offset mapping precision
primary->secondary.emit.offset-syncs.enabled=true
primary->secondary.offset.lag.max=50

# Target topic defaults
primary->secondary.replication.factor=3

# Kafka Connect worker capacity
tasks.max=6

# Read only committed transactional records from source
primary.consumer.isolation.level=read_committed
~~~

`emit.offset-syncs.enabled` là tên config chuẩn, có dấu gạch nối. Nếu tắt setting này, MirrorCheckpointConnector không thể dịch offsets khi checkpoints hoặc group offset sync đang được bật.

`tasks.max` cần được chọn theo số topic-partitions, worker resources và throughput. Thêm worker/task có thể tăng khả năng song song nhưng cũng tăng kết nối, network load và áp lực lên broker.

### 8.1. Security settings

Mỗi cluster alias có thể có security configuration riêng. Ví dụ TLS:

~~~properties
primary.security.protocol=SSL
primary.ssl.truststore.location=/etc/kafka/secrets/primary.truststore.p12
primary.ssl.truststore.type=PKCS12
primary.ssl.keystore.location=/etc/kafka/secrets/primary.keystore.p12
primary.ssl.keystore.type=PKCS12

secondary.security.protocol=SSL
secondary.ssl.truststore.location=/etc/kafka/secrets/secondary.truststore.p12
secondary.ssl.truststore.type=PKCS12
secondary.ssl.keystore.location=/etc/kafka/secrets/secondary.keystore.p12
secondary.ssl.keystore.type=PKCS12
~~~

Đường dẫn file là placeholder. Với SASL/SCRAM hoặc OAuth, cấu hình mechanism và JAAS/OAuth properties theo security policy của từng cluster. Không commit plaintext passwords hoặc private keys vào source control; dùng Kafka Connect ConfigProvider hoặc secret management của nền tảng.

### 8.2. Consumer/producer client overrides

MM2 sử dụng consumer, producer và admin clients riêng:

~~~properties
primary.consumer.fetch.max.bytes=52428800
primary.consumer.max.partition.fetch.bytes=1048576
primary.consumer.isolation.level=read_committed

secondary.producer.compression.type=zstd
secondary.producer.acks=all
secondary.producer.enable.idempotence=true
~~~

Các giá trị là ví dụ. Đo network latency, record size, compression CPU, target broker capacity và durability requirements trước khi tuning.

## 9. Cấu hình active/active hai chiều

Active/active bật cả hai replication flows:

~~~properties
clusters=west,east
west.bootstrap.servers=west-1:9092,west-2:9092
east.bootstrap.servers=east-1:9092,east-2:9092

west->east.enabled=true
east->west.enabled=true

west->east.topics=orders.*,payments.*
east->west.topics=orders.*,payments.*

west->east.emit.checkpoints.enabled=true
east->west.emit.checkpoints.enabled=true

west->east.emit.heartbeats.enabled=true
east->west.emit.heartbeats.enabled=true
~~~

### 9.1. Topic naming tránh collision

Với DefaultReplicationPolicy:

~~~text
west.orders  = records được replicate từ west sang east
east.orders  = records được replicate từ east sang west
orders       = topic local của cluster hiện tại
~~~

Ứng dụng ở mỗi cluster nên ghi vào local topic và đọc remote topics theo yêu cầu business. Không để hai region cùng ghi vào một topic local rồi mong MM2 tự hợp nhất record.

### 9.2. Replication loop

Khi hai chiều được cấu hình trong cùng MM2 configuration, DefaultReplicationPolicy nhận diện remote topics và ngăn replicate vòng lặp của chính dữ liệu đã được mirror. Nếu chạy các MM2 processes với cấu hình khác nhau hoặc dùng IdentityReplicationPolicy, nguy cơ loop/collision cần được đánh giá riêng.

### 9.3. Active/active không tự giải quyết conflict nghiệp vụ

MM2 không cung cấp conflict resolution cho hai producer cùng ghi cùng một logical entity ở hai cluster. Nếu cùng order ID được cập nhật đồng thời ở hai region:

- Cần quy tắc ownership theo tenant/region hoặc partition key.
- Hoặc dùng version/vector clock/business timestamp và logic conflict resolution ở ứng dụng.
- Dùng idempotency key để chống duplicate.
- Không dựa vào arrival order của MM2 để xác định event nào thắng.

Active/active tăng khả năng phục vụ local traffic nhưng yêu cầu thiết kế dữ liệu và ownership rõ ràng.

## 10. Consumer offset recovery khi failover

Consumer offsets không thể copy nguyên số từ source sang target vì target remote topic có offset space riêng.

### 10.1. Quy trình chuyển group

Một flow cơ bản:

1. Source consumer group commit offsets bình thường.
2. MirrorCheckpointConnector đọc committed offsets.
3. Offset-sync mapping dịch source offsets sang target offsets.
4. MirrorCheckpointConnector phát checkpoint records.
5. Nếu bật `sync.group.offsets.enabled`, MM2 ghi translated offsets vào target `__consumer_offsets` khi target group không active.
6. Nếu không bật, ứng dụng hoặc runbook dùng MirrorClient/RemoteClusterUtils để lấy translated offsets rồi khởi tạo consumer ở target.

### 10.2. Checkpoint interval và duplicate

Giả sử:

- Source group đã commit offset 10.000.
- Checkpoint mới nhất phản ánh offset 9.950.
- Offset-sync mapping mới nhất chỉ tới target offset 8.300.

Khi failover, consumer có thể bắt đầu từ checkpoint cũ hơn và xử lý lại một số record. Đây là hành vi có thể xảy ra với asynchronous replication.

Thiết kế consumer idempotent:

- Ghi event ID vào inbox/processed table.
- Dùng unique constraint cho business event ID.
- Thực hiện business update và ghi processed marker trong cùng DB transaction.
- Không giả định MM2 tạo exactly-once end-to-end cho Kafka và database.

### 10.3. Không chạy active consumer trước khi offset sync

Nếu `sync.group.offsets.enabled=true`, target group phải không có active consumers để MM2 ghi translated offsets. Nếu target group đã active, offset sync sẽ không ghi đè group offsets của nó.

Runbook nên:

- Giữ standby consumers dừng cho tới khi offset recovery hoàn tất.
- Kiểm tra group state trên target.
- Xác minh offset mapping và checkpoint timestamp.
- Chỉ sau đó mới khởi động consumer với group ID và offset policy đã chọn.

## 11. Failover runbook active/passive

Failover cần có người chịu trách nhiệm quyết định và fencing. MM2 không tự động bầu primary mới và không thay thế orchestration của ứng dụng, DNS, load balancer hoặc hệ thống control plane.

~~~mermaid
flowchart TD
    A["Phát hiện primary failure"] --> B["Xác minh phạm vi và quyết định DR"]
    B --> C["Fence primary: chặn writes/traffic"]
    C --> D["Kiểm tra remote topics và replication lag"]
    D --> E["Khôi phục consumer offsets từ checkpoint"]
    E --> F["Chuyển producers/consumers sang secondary"]
    F --> G["Xác minh business invariants và duplicate"]
    G --> H["Theo dõi secondary như primary mới"]
~~~

### 11.1. Trước sự cố

- Duy trì replication flow và kiểm tra heartbeat.
- Đặt RPO/RTO cho từng nhóm topic.
- Đảm bảo target có đủ partitions, replication factor và storage.
- Bảo đảm checkpoint được phát cho các consumer groups cần recovery.
- Kiểm thử translated offsets bằng consumer test group.
- Chuẩn bị DNS/connection configuration cho producers và consumers.
- Có fencing mechanism để ngăn primary cũ tiếp tục nhận writes.

### 11.2. Khi primary mất

1. Xác nhận primary thực sự không thể phục vụ hoặc đã bị cô lập.
2. Fence primary: thu hồi producer credentials, chặn network/listener hoặc dùng cơ chế control plane phù hợp.
3. Kiểm tra heartbeat cuối cùng và replication latency cuối cùng đã ghi nhận.
4. Kiểm tra remote topics ở secondary và các partition còn thiếu dữ liệu.
5. Kiểm tra checkpoint topic và source/target offset mapping.
6. Khôi phục translated offsets vào target group hoặc dùng MirrorClient.
7. Chuyển producers sang secondary và sử dụng local topics theo naming policy.
8. Khởi động consumers và xác minh idempotency/duplicate.
9. Theo dõi lag, business errors và throughput.

Không chuyển traffic chỉ vì heartbeat còn mới. Nếu MirrorSourceTask đang lỗi hoặc lag lớn, target có thể thiếu dữ liệu gần nhất.

### 11.3. RPO thực tế

Nếu source cluster mất trước khi record cuối cùng được mirror, các record đó có thể mất ở target. RPO thực tế phải được ước lượng từ:

- `replication-latency-ms`.
- `record-age-ms`.
- Source-to-target lag theo partition.
- Network availability.
- MirrorSource task state.
- Checkpoint freshness cho consumer groups.

Checkpoint freshness ảnh hưởng vị trí consumer resume, còn replication freshness ảnh hưởng dữ liệu nào có mặt ở target. Hai loại freshness khác nhau.

### 11.4. Sau khi failover

- Ghi nhận secondary đang là cluster active.
- Không tự bật lại primary cũ khi chưa có plan failback.
- Cập nhật ownership và producer routing.
- Theo dõi remote topics, local topics và replication direction.
- Ghi nhận khoảng dữ liệu có thể duplicate hoặc missing.
- Đối soát business data với nguồn backup/database nếu cần.

## 12. Failback về cluster ban đầu

Failback là một migration có kiểm soát, không chỉ đổi DNS về primary cũ.

Quy trình tham khảo:

1. Chọn cluster đang active làm nguồn dữ liệu chuẩn.
2. Xác định primary cũ đã được phục hồi và được fence khỏi producers.
3. Cấu hình replication từ cluster active sang cluster sẽ nhận lại vai trò primary.
4. Chọn topic naming và mapping phù hợp; kiểm tra remote topics hiện có.
5. Replicate và catch up dữ liệu.
6. Xác minh partition counts, configs, ACLs, replication lag và consumer checkpoints.
7. Dừng writes ở cluster active theo maintenance window.
8. Fencing cluster active để không có hai nơi nhận writes.
9. Khôi phục consumer offsets tại cluster đích.
10. Chuyển producer/consumer traffic.
11. Giữ replication một chiều theo hướng mới cho tới khi kế hoạch tiếp theo được phê duyệt.

Không chạy hai hướng replication cho cùng logical data mà không hiểu remote topic names và conflict policy. Tránh failback trong lúc hai cluster vẫn có writers độc lập.

## 13. Exactly-once và transaction

MirrorMaker 2 có hỗ trợ exactly-once semantics cho dedicated MirrorMaker clusters từ Kafka 3.5.0 khi cấu hình đúng. Đây là tính năng có điều kiện, không phải mặc định cho mọi deployment.

Với dedicated mode:

- Cấu hình `exactly.once.source.support=enabled` trên target cluster được ghi.
- Với cluster MM2 đã tồn tại, quy trình upgrade EOS cần bước `preparing` trước rồi mới `enabled`.
- Cần bật internal REST communication giữa MirrorMaker nodes theo hướng dẫn Kafka.
- Source consumer nên dùng `isolation.level=read_committed` để không replicate records từ aborted transactions.

Ví dụ:

~~~properties
secondary.exactly.once.source.support=enabled
dedicated.mode.enable.internal.rest=true
listeners=http://localhost:8080
primary.consumer.isolation.level=read_committed
~~~

Đây là cấu hình minh họa cho dedicated mode và cần kiểm tra đúng Kafka version, security và Connect REST configuration. Nếu bật REST nội bộ ở production, phải bảo vệ endpoint bằng authentication/TLS/network policy.

Exactly-once trong MM2 không biến toàn bộ pipeline source Kafka → target Kafka → database thành một distributed transaction duy nhất. Consumer vẫn cần idempotency và transaction boundary phù hợp.

## 14. Monitoring ba connector

MM2 kế thừa Kafka Connect metrics và phát metrics riêng trong metric group `kafka.connect.mirror`. Tên MBean có thể thay đổi theo metric naming mode và Kafka version.

### 14.1. MirrorSourceConnector metrics

| Metric | Ý nghĩa |
|---|---|
| `record-count` | Tổng số record được replicate source → target |
| `record-rate` | Tốc độ record replicate mỗi giây |
| `record-age-ms` | Tuổi record khi được replicate |
| `record-age-ms-min/max/avg` | Phân phối tuổi record ở dạng min/max/avg |
| `replication-latency-ms` | Thời gian record truyền từ source sang target |
| `replication-latency-ms-min/max/avg` | Min/max/avg replication latency |
| `byte-rate` | Tốc độ byte replicate |
| `byte-count` | Tổng byte replicate |

### 14.2. MirrorCheckpointConnector metrics

| Metric | Ý nghĩa |
|---|---|
| `checkpoint-latency-ms` | Thời gian replicate consumer offsets/checkpoints |
| `checkpoint-latency-ms-min/max/avg` | Min/max/avg checkpoint latency |

Checkpoint latency cao có thể khiến consumer offset ở target cũ hơn source. Cần theo dõi cùng checkpoint topic, group filters và offset-sync freshness.

### 14.3. MirrorHeartbeatConnector

Heartbeat connector cần được theo dõi qua:

- Connector/task state.
- Heartbeat topic có record mới hay không.
- Tuổi heartbeat cuối cùng ở target.
- Heartbeat flow theo từng source/target alias.
- Network/authentication errors trong Connect logs.

Không chỉ kiểm tra process MirrorMaker còn sống; một task có thể FAILED trong khi worker process vẫn RUNNING.

### 14.4. Kafka Connect metrics và task status

Theo dõi thêm:

- `source-record-poll-rate`.
- Connector/task status.
- Task restart count.
- Connect worker rebalance.
- Producer send errors và retries.
- Consumer poll/fetch errors.
- Dead-letter/error handling nếu được cấu hình.

Kafka Connect REST API có thể dùng để kiểm tra status trong deployment mode có REST endpoint:

~~~bash
curl http://connect-worker:8083/connectors
curl http://connect-worker:8083/connectors/<connector-name>/status
~~~

Trong dedicated mode, endpoint và cách đặt tên connector có thể do MM2 quản lý. Dùng status endpoint và logs đúng theo deployment hiện tại, không giả định connector name luôn giống ví dụ.

### 14.5. Dashboard và alert

Dashboard nên hiển thị:

- Replication latency theo source/target/topic/partition.
- Record age và record rate.
- Byte rate và throughput.
- Checkpoint latency theo group/topic/partition.
- Heartbeat age.
- Connector/task state và error count.
- Consumer lag ở target sau failover.

Alert gợi ý:

- Source connector hoặc task FAILED.
- Heartbeat không cập nhật trong ngưỡng cho phép.
- Replication latency/record age vượt RPO budget.
- Checkpoint latency vượt checkpoint interval nhiều lần.
- Target topic partition không được replicate.
- Connector retry/error tăng liên tục.
- Consumer group offset sync không chạy do target group đang active.

## 15. Tuning và capacity planning

### 15.1. tasks.max

MM2 dùng Kafka Connect tasks để phân phối công việc. Tăng `tasks.max` có thể tăng số task tối đa nhưng connector chỉ tạo task theo số partition và khả năng song song của nó.

Tăng task không tự động tăng throughput nếu:

- Source topic có ít partition.
- Network giữa các region là bottleneck.
- Target broker bị throttling.
- Worker CPU/memory thiếu.
- Target producer retry nhiều.
- Source consumer bị lag.

### 15.2. Consumer và producer tuning

Source consumer settings:

- `fetch.max.bytes`.
- `max.partition.fetch.bytes`.
- `fetch.min.bytes`.
- `fetch.max.wait.ms`.
- `isolation.level`.

Target producer settings:

- `compression.type`.
- `batch.size`.
- `linger.ms`.
- `buffer.memory`.
- `acks`.
- `enable.idempotence`.

Tuning phải giữ đúng durability requirements và kiểm tra end-to-end replication latency. Không giảm acks chỉ để dashboard replication latency đẹp hơn.

### 15.3. Network placement

Kafka docs khuyến nghị đặt MM2 process gần target cluster vì producer thường nhạy hơn với network latency và độ tin cậy của đường kết nối. Có thể dùng:

~~~bash
bin/connect-mirror-maker.sh connect-mirror-maker.properties --clusters secondary
~~~

`--clusters secondary` chỉ ra cluster gần với MM2 process. Điều này giúp MM2 produce đến target local và giảm producer lag qua WAN.

### 15.4. Throttling

Khi initial replication hoặc migration lớn, MM2 có thể cạnh tranh network/disk với workload production. Cần:

- Đo source/target broker throughput.
- Kiểm soát replication rate.
- Dùng replication throttling nếu cần.
- Theo dõi consumer lag và producer request latency.
- Chạy migration ngoài peak hours nếu phù hợp.
- Tránh replicate tất cả topic nếu chỉ một phần cần DR.

## 16. Bảo mật và quyền truy cập

MM2 là một client có quyền truy cập hai cluster. Tách principal theo từng cluster và chỉ cấp quyền cần thiết.

### 16.1. Source cluster permissions

MM2 cần quyền để:

- Describe cluster và topic metadata.
- Read các source topics được replicate.
- Describe/Read consumer group offsets cần checkpoint.
- Đọc topic configs và ACL metadata nếu đồng bộ.
- Ghi offset-sync metadata vào vị trí cấu hình.

### 16.2. Target cluster permissions

MM2 cần quyền để:

- Create/Write remote topics.
- Alter topic configs nếu bật config sync.
- Alter ACLs nếu bật ACL sync.
- Create/Write checkpoint và heartbeat topics.
- Ghi target `__consumer_offsets` nếu bật `sync.group.offsets.enabled`.

Quyền chính xác phụ thuộc authorizer, ACL model, deployment mode và các tính năng bật trong flow.

### 16.3. TLS/SASL và secret management

- Dùng TLS cho kết nối cross-region.
- Dùng SASL/SCRAM hoặc OAuth theo identity policy.
- Kiểm tra certificate SAN/hostname và trust chain.
- Không ghi passwords/private keys trong file config lưu Git.
- Dùng ConfigProvider hoặc secret manager.
- Rotate credentials và kiểm thử trước khi hết hạn.
- Giới hạn network access giữa MM2 workers và broker listeners.

### 16.4. Data governance

Không phải mọi topic đều nên được replicate sang mọi region. Kiểm tra:

- Data residency và legal constraints.
- PII/sensitive payload.
- Retention và deletion policies.
- ACL principal mapping.
- Encryption at rest và in transit.
- Quy trình xóa dữ liệu đồng bộ giữa các cluster.

## 17. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không có remote topic | Flow chưa enable, topic filter loại trừ, ACL thiếu | Kiểm tra flow config, topics/exclude và Connect logs |
| Connector RUNNING nhưng record không tăng | Source topic rỗng, task chưa assign hoặc filter sai | Kiểm tra source offsets, task status và record-rate |
| Target topic không đủ partition | Topic đã tồn tại với partition count không tương thích | So sánh source/target topic metadata |
| Replication latency tăng | WAN chậm, target throttling, task backlog | Xem record-age, replication-latency, producer retry |
| Checkpoint không xuất hiện | Group bị exclude hoặc offset-syncs bị tắt | Kiểm tra groups, groups.exclude, emit.offset-syncs.enabled |
| Target group offset không cập nhật | sync.group.offsets.enabled=false hoặc group đang active ở target | Kiểm tra config và target group members |
| Offset resume sai | Mapping cũ, offset.lag.max cao, checkpoint cũ | Kiểm tra offset-sync topic, checkpoint age và duplicate |
| Heartbeat không tới target | Heartbeat connector lỗi, filter hoặc ACL | Kiểm tra task status, heartbeats.replication.enabled và topic |
| Replication loop | Policy/config flow không nhất quán hoặc IdentityReplicationPolicy | Kiểm tra remote topic naming và replication flows |
| Nhiều MM2 process có kết quả khác nhau | Config không đồng nhất cho cùng target cluster | Dùng chung một config được version-control |
| SASL authentication failed | Credential/mechanism/JAAS sai hoặc hết hạn | Kiểm tra alias-specific security config |
| SSL handshake failed | Truststore, certificate SAN hoặc clock/cert validity | Kiểm tra TLS chain và listener endpoint |
| Task liên tục restart | Source/target request errors hoặc Connect worker issue | Đọc task trace, broker logs và worker health |
| Initial replication quá chậm | Quá nhiều topic/partition hoặc network không đủ | Tăng task/worker có kiểm soát, throttle và đo throughput |

## 18. Kiểm thử multi-cluster replication

Kiểm thử cần ít nhất hai Kafka clusters độc lập. Không coi hai broker trong cùng cluster là hai cluster khác nhau.

### 18.1. Chuẩn bị

1. Tạo cluster `primary` và `secondary`.
2. Tạo topic `orders` ở primary với nhiều partitions.
3. Tạo MM2 properties file.
4. Enable flow `primary->secondary`.
5. Bật source, checkpoint và heartbeat connectors.
6. Khởi chạy MM2 worker.

### 18.2. Kiểm thử MirrorSourceConnector

1. Produce record với key xác định vào `primary.orders`.
2. Chờ remote topic `primary.orders` xuất hiện ở secondary.
3. Consume record từ remote topic.
4. So sánh key/value/header và partition.
5. Kiểm tra topic configs và ACL sync nếu được bật.
6. Tạo topic mới ở primary và kiểm tra refresh.

### 18.3. Kiểm thử MirrorCheckpointConnector

1. Chạy consumer group `orders-service` trên primary.
2. Bật `emit.checkpoints.enabled`.
3. Kiểm tra `primary.checkpoints.internal`.
4. Tắt consumer trên secondary.
5. Bật `sync.group.offsets.enabled` trong lab hoặc dùng MirrorClient.
6. Khởi động group ở secondary và xác minh vị trí resume.

Không dùng `console-consumer-*` group để test checkpoint mặc định nếu chưa điều chỉnh groups.exclude.

### 18.4. Kiểm thử MirrorHeartbeatConnector

1. Xác minh heartbeat topic ở target.
2. Quan sát timestamp/age của heartbeat records.
3. Chặn network giữa MM2 và target trong lab.
4. Quan sát heartbeat age tăng và connector errors.
5. Khôi phục network và xác minh heartbeat tiếp tục.

### 18.5. Kiểm thử failover

1. Để primary replicate ổn định trong một khoảng thời gian.
2. Ghi nhận replication lag và checkpoint age.
3. Fence primary trong môi trường lab.
4. Chuyển producer/consumer sang secondary.
5. Khôi phục consumer offsets.
6. Xác minh duplicate, ordering và business state.
7. Chạy failback theo quy trình riêng.

### 18.6. Kiểm thử failure injection

- Dừng một MM2 worker.
- Dừng một connector task.
- Ngắt kết nối WAN.
- Thu hồi credential của một cluster.
- Làm target broker unavailable.
- Tạo topic mới khi replication đang chạy.
- Tăng traffic để tạo replication lag.
- Restart MM2 worker sau khi có checkpoint.

Sau mỗi thử nghiệm, xác minh task recovery, remote topic consistency, offset checkpoints và business idempotency.

## 19. Checklist production

- Hai Kafka clusters có cluster IDs và metadata độc lập.
- Replication flow source→target được định nghĩa rõ.
- Topics/groups filters chỉ bao gồm workload cần thiết.
- Remote topic naming policy được giữ ổn định.
- Source connector tasks và target topics được giám sát.
- Offset-sync metadata được bật nếu cần checkpoint.
- Checkpoint interval và offset.lag.max phù hợp RPO.
- Target group offset sync chỉ bật khi hiểu điều kiện group inactive.
- Heartbeat topic có replication factor phù hợp target.
- MirrorSource/Checkpoint/Heartbeat tasks đều có alert.
- TLS/SASL và ACL được cấu hình riêng cho source/target.
- Secret không nằm trong plaintext config hoặc Git.
- Replication lag và checkpoint age nằm trong RPO budget.
- Consumer có idempotency và xử lý duplicate.
- Có fencing mechanism để ngăn split-brain.
- Failover và failback runbook đã được diễn tập.
- Active/active có ownership và conflict resolution rõ.
- Topic configs, ACLs, partition counts và retention được kiểm tra.
- Có capacity plan cho initial replication và network outage recovery.

## 20. Bài tập thực hành

### Bài tập 1: Mirror source topics

1. Tạo hai Kafka clusters độc lập.
2. Cấu hình primary→secondary.
3. Chỉ replicate topic `orders.*`.
4. Produce record vào primary.
5. Xác minh remote topic `primary.orders`.
6. Kiểm tra record count, partition mapping và replication latency.

### Bài tập 2: Checkpoint consumer offsets

1. Chạy group `orders-service` trên primary.
2. Bật `emit.checkpoints.enabled`.
3. Kiểm tra `primary.checkpoints.internal`.
4. Tắt consumer trên secondary.
5. Bật `sync.group.offsets.enabled` trong lab hoặc dùng MirrorClient.
6. Khởi động group ở secondary và xác minh vị trí resume.

### Bài tập 3: Heartbeat monitoring

1. Bật `emit.heartbeats.enabled`.
2. Quan sát heartbeat topic trên secondary.
3. Ngắt network tạm thời.
4. Đo thời gian heartbeat ngừng cập nhật.
5. Khôi phục network và xác minh connector phục hồi.

### Bài tập 4: Active/passive failover

1. Replicate dữ liệu từ primary sang secondary.
2. Theo dõi replication latency và checkpoint latency.
3. Fence primary trong lab.
4. Khôi phục consumer offsets ở secondary.
5. Chuyển traffic.
6. Đo RTO và lượng record duplicate.

### Bài tập 5: Active/active và naming

1. Bật A→B và B→A.
2. Ghi dữ liệu local ở mỗi cluster.
3. Quan sát remote topic prefixes.
4. Kiểm tra replication loop prevention.
5. Tạo cùng entity ID ở hai region và đề xuất conflict resolution.

## 21. Câu hỏi tự kiểm tra

1. Vì sao replication factor trong một cluster không thay thế multi-cluster replication?
2. MirrorSourceConnector làm những việc gì?
3. MirrorCheckpointConnector cần offset-sync metadata để làm gì?
4. MirrorHeartbeatConnector kiểm tra điều gì?
5. Vì sao remote topic mặc định có source cluster alias prefix?
6. Offset source và target có luôn giống nhau không?
7. `emit.offset-syncs.enabled` ảnh hưởng checkpoint như thế nào?
8. `offset.lag.max` ảnh hưởng độ chính xác offset recovery ra sao?
9. Checkpoint topic khác target `__consumer_offsets` thế nào?
10. Vì sao `sync.group.offsets.enabled` mặc định false?
11. Khi nào MM2 ghi translated offsets vào target group?
12. Vì sao không nên khởi chạy target consumer trước khi offset recovery hoàn tất?
13. Heartbeat mới có chứng minh mọi business record đã replicate không?
14. Active/passive khác active/active ở replication flows như thế nào?
15. Vì sao active/active vẫn cần conflict resolution?
16. Những metrics nào giúp đo replication lag?
17. RPO và RTO chịu ảnh hưởng bởi thành phần nào?
18. Vì sao phải fence primary trước khi chuyển traffic?
19. Vì sao failback là một migration riêng?
20. Exactly-once của MM2 có đồng nghĩa end-to-end database exactly-once không?

## Tài liệu tham khảo

- [Apache Kafka 4.4 – Geo-Replication (Cross-Cluster Data Mirroring)](https://kafka.apache.org/44/operations/geo-replication-cross-cluster-data-mirroring/)
- [Apache Kafka 4.4 – MirrorMaker Configs](https://kafka.apache.org/44/configuration/mirrormaker-configs/)
- [Apache Kafka 4.4 – MirrorMaker API package](https://kafka.apache.org/44/javadoc/org/apache/kafka/connect/mirror/package-summary.html)
- [Apache Kafka 4.4 – MirrorClient Java API](https://kafka.apache.org/44/javadoc/org/apache/kafka/connect/mirror/MirrorClient.html)
- [Apache Kafka 4.4 – ReplicationPolicy Java API](https://kafka.apache.org/44/javadoc/org/apache/kafka/connect/mirror/ReplicationPolicy.html)
- [Apache Kafka 4.4 – DefaultReplicationPolicy Java API](https://kafka.apache.org/44/javadoc/org/apache/kafka/connect/mirror/DefaultReplicationPolicy.html)
- [Apache Kafka 4.4 – Kafka Connect Administration](https://kafka.apache.org/44/kafka-connect/user-guide/)

MirrorSourceConnector bảo đảm record có thể đi sang cluster khác; MirrorCheckpointConnector giúp consumer resume gần vị trí source đã commit; MirrorHeartbeatConnector giúp phát hiện replication path bị gián đoạn. Để multi-cluster recovery đáng tin cậy, phải theo dõi cả ba connector, hiểu offset translation và duplicate window, đồng thời thực hiện fencing và chuyển traffic theo runbook đã diễn tập.
