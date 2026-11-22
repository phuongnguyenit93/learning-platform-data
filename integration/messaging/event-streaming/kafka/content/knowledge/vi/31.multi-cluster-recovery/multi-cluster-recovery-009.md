# Thứ tự, trùng dữ liệu và xung đột key khi có nhiều cụm

Khi một hệ thống Kafka có nhiều cluster, dữ liệu có thể được ghi ở nhiều nơi, replicate bất đồng bộ, consumer có thể chuyển vùng khi failover và cùng một nghiệp vụ có thể xuất hiện nhiều lần ở cluster đích. Ba vấn đề cần thiết kế rõ là thứ tự sự kiện (ordering), xử lý bản ghi trùng (duplicate) và xung đột cập nhật cùng key (conflict).

Kafka bảo đảm thứ tự trong một partition của một cluster. Kafka không tự tạo một thứ tự toàn cục giữa nhiều partition hoặc giữa các cluster độc lập. MirrorMaker 2 (MM2) sao chép record và hỗ trợ đồng bộ checkpoint/offset cho kịch bản đa cụm, nhưng replication bất đồng bộ không phải một giao dịch phân tán đồng bộ và không loại bỏ mọi duplicate. Nếu hai cluster cùng ghi một logical key, ứng dụng cần quy tắc xác định writer, version và cách hợp nhất dữ liệu.

## 1. Ba vấn đề cần tách biệt

| Vấn đề | Câu hỏi | Cơ chế xử lý chính |
|---|---|---|
| Ordering | Sự kiện nào phải được xử lý trước? | Partition key, aggregate version, single-writer hoặc sequencing |
| Duplicate | Cùng một sự kiện có thể được xử lý nhiều lần không? | Stable event ID, idempotent consumer, inbox/deduplication |
| Conflict | Hai cập nhật khác nhau cho cùng key thì cập nhật nào thắng hoặc hợp nhất ra sao? | Writer ownership, fencing epoch, version check, merge policy |

Ba vấn đề liên quan nhưng không thay thế nhau. Deduplication loại bỏ việc áp dụng lại cùng một event ID; nó không quyết định hai event khác ID nhưng cùng aggregate phải được sắp thứ tự thế nào. Ordering giữ trình tự trong một luồng; nó không tự giải quyết hai writer độc lập cùng cập nhật một key. Conflict resolution cần semantics nghiệp vụ rõ ràng.

## 2. Phạm vi ordering mà Kafka bảo đảm

Trong một topic-partition, Kafka gán offset tăng dần cho record được append. Consumer đọc partition theo thứ tự offset. Đây là ranh giới ordering cơ bản.

~~~mermaid
flowchart LR
    subgraph P0[orders.events - partition 0]
        A[offset 10] --> B[offset 11] --> C[offset 12]
    end
    subgraph P1[orders.events - partition 1]
        D[offset 7] --> E[offset 8] --> F[offset 9]
    end
~~~

Kafka không định nghĩa quan hệ trước/sau giữa offset 12 ở partition 0 và offset 7 ở partition 1. Hai partition có thể được consume song song và hoàn tất theo thứ tự khác nhau.

| Phạm vi | Có ordering không? | Ghi chú |
|---|---|---|
| Một partition | Có, theo log offset | Đây là thứ tự append trong partition |
| Nhiều partition cùng topic | Không có total order | Consumer có thể xử lý song song |
| Hai topic khác nhau | Không có total order | Không suy ra thứ tự chỉ từ timestamp |
| Hai cluster độc lập | Không có global order | Mỗi cluster có log và offset riêng |
| Hai producer cùng ghi một partition | Có thứ tự append, nhưng không tự biết causal order nghiệp vụ | Broker append order có thể khác thứ tự nghiệp vụ mong muốn |

Nếu nghiệp vụ cần thứ tự cho từng đơn hàng, tài khoản hoặc aggregate, hãy đặt các event của cùng aggregate vào cùng partition và mang version/sequence trong event. Nếu cần total order toàn hệ thống, phải có một sequencer hoặc writer duy nhất; tăng số partition hay thêm cluster không tự tạo ra total order.

## 3. Key quyết định partition và thứ tự theo aggregate

Producer thường chọn partition từ record key. Với partitioner mặc định, key được serialize thành bytes rồi hash để chọn partition. Các event cùng key thường đi vào cùng partition khi topic, partition count và partitioner không đổi.

Ví dụ:

~~~java
ProducerRecord<String, OrderEvent> record =
    new ProducerRecord<>(
        "orders.events",
        event.orderId(),
        event
    );
~~~

Nếu key là orderId, các event của cùng order có thể được đọc theo offset trong cùng partition. Không dùng trace ID hoặc random UUID làm key nếu cần ordering theo order.

### Điều kiện để ordering theo key có ý nghĩa

- Mọi producer dùng cùng quy tắc serialize key.
- Mọi producer dùng partitioning strategy tương thích.
- Partition count không thay đổi tùy tiện trong vòng đời aggregate.
- Event của cùng aggregate không bị phát song song từ nhiều writer thiếu coordination.
- Consumer xử lý record theo đúng thứ tự hoặc dùng version guard khi có concurrency.

Tăng partition count có thể làm key hash sang partition khác cho các record mới. Khi đó event cũ của aggregate có thể nằm ở partition cũ, event mới ở partition khác; Kafka không có cơ chế tự nối lại ordering giữa hai partition. Nếu cần tăng partition, cân nhắc tạo topic mới, migrate có kiểm soát hoặc dùng partitioner có mapping ổn định.

## 4. Producer retry và thứ tự trong một cluster

Producer có thể retry khi gặp lỗi mạng hoặc broker tạm thời. Idempotent producer dùng producer ID và sequence number để broker nhận diện retry của record trong phạm vi producer session/protocol.

Ví dụ cấu hình:

~~~properties
acks=all
enable.idempotence=true
retries=2147483647
~~~

Các giá trị và ràng buộc cụ thể phụ thuộc Kafka client version. Với producer idempotent, hãy giữ các cấu hình tương thích mà client yêu cầu; không tự đặt max.in.flight hoặc retries trái với contract của phiên bản đang dùng.

Idempotence giúp tránh duplicate do retry protocol của cùng producer. Nó không loại bỏ:

- Ứng dụng tự gửi lại cùng event với một producer instance/session khác.
- Hai service cùng phát một event nghiệp vụ.
- Consumer xử lý lại sau khi crash.
- MM2 replicate lại record sau restart hoặc replay.
- Một event được publish vào hai cluster độc lập.

Idempotent producer cũng không tạo thứ tự nghiệp vụ giữa hai producer độc lập. Nếu producer A tạo OrderCreated và producer B tạo OrderPaid, cần một cơ chế nghiệp vụ bảo đảm event version hoặc state transition hợp lệ.

## 5. Multi-cluster topology: active-passive và active-active

### Active-passive

Một cluster là nơi nhận ghi chính (primary); cluster còn lại nhận replication và dùng khi failover.

~~~mermaid
flowchart LR
    A[Applications] --> P[(Primary Kafka)]
    P -->|MM2 asynchronous replication| D[(DR Kafka)]
    D -->|Failover after fencing primary| C[Consumers in DR]
~~~

Ưu điểm là một nguồn ghi authoritative tại một thời điểm, giảm xung đột key và dễ xác định thứ tự. Nhược điểm là có replication lag; khi primary mất, dữ liệu chưa replicate có thể chưa tồn tại ở DR.

### Active-active

Hai cluster đều nhận ghi từ ứng dụng tại vùng của mình và replicate dữ liệu qua lại hoặc qua một tầng hợp nhất.

~~~mermaid
flowchart LR
    A[Region A apps] --> KA[(Kafka A)]
    B[Region B apps] --> KB[(Kafka B)]
    KA -->|Replicate| KB
    KB -->|Replicate| KA
    KB --> CA[Region B consumers]
    KA --> CB[Region A consumers]
~~~

Active-active giảm độ trễ ghi tại vùng gần ứng dụng nhưng đặt ra bài toán split-brain, duplicate và conflict. Nếu cả hai vùng ghi cùng aggregate, offset và timestamp cục bộ không đủ để chọn bản cập nhật đúng.

### Chọn topology theo semantics

| Yêu cầu | Mô hình thường phù hợp |
|---|---|
| Một nguồn ghi, DR standby | Active-passive |
| Mỗi tenant/aggregate có vùng sở hữu | Active-active theo shard, single-writer per key |
| Nhiều vùng cùng cập nhật cùng entity | Active-active với version/merge semantics rõ ràng |
| Cần isolation và RPO thấp | Cluster riêng kết hợp replication và failover orchestration |
| Cần total order toàn cục | Một sequencer/writer authority; không chỉ dựa vào MM2 |

Không chọn active-active chỉ vì có hai cluster. Nếu nghiệp vụ không có conflict-resolution rule, active-passive thường dễ vận hành và dễ kiểm chứng hơn.

## 6. MirrorMaker 2 và luồng replication

MirrorMaker 2 dựa trên Kafka Connect và gồm các connector chính:

- MirrorSourceConnector: đọc record từ source cluster và ghi sang target cluster.
- MirrorCheckpointConnector: phát checkpoint ánh xạ offset của consumer group giữa source và target.
- MirrorHeartbeatConnector: phát heartbeat để quan sát kết nối và replication path.

MM2 sao chép record bất đồng bộ. Source offset và target offset không nhất thiết bằng nhau; target có thể có record được ghi local, record replication khác hoặc lịch sử riêng.

Ví dụ cấu hình khái quát:

~~~properties
clusters = primary, dr

primary.bootstrap.servers = kafka-primary-1:9092,kafka-primary-2:9092
dr.bootstrap.servers = kafka-dr-1:9092,kafka-dr-2:9092

primary->dr.enabled = true
primary->dr.topics = orders[.]events|payments[.]events

replication.factor = 3
replication.policy.class = org.apache.kafka.connect.mirror.DefaultReplicationPolicy

primary->dr.emit.checkpoints.enabled = true
primary->dr.emit.heartbeats.enabled = true
~~~

Đây là ví dụ cấu hình định hướng; các thuộc tính connector, replication factor của internal topics, security và naming phải đối chiếu phiên bản Kafka/MM2 đang triển khai. Topic regex có thể được dùng thay danh sách tên; hãy review regex để tránh replicate nhầm internal hoặc topic không thuộc scope.

### Replication không phải synchronous commit

Producer nhận ACK từ primary không có nghĩa record đã được ghi ở DR. MM2 cần thời gian đọc source, chuyển qua Connect và produce sang target. Trong cửa sổ lag, failover sang DR có thể mất phần record chưa replicate.

RPO thực tế phụ thuộc:

- Replication latency và backlog.
- Throughput source/target.
- Network bandwidth và packet loss.
- Connect task availability/restarts.
- Target broker capacity, ISR và disk.
- Topic filtering và lỗi serialization/ACL.

Đo replication lag theo partition và record age; không chỉ kiểm tra connector state RUNNING.

### Ordering khi replicate một source partition

Khi MM2 đọc record từ một source partition theo thứ tự và ghi chúng lần lượt vào target partition tương ứng, thứ tự tương đối của các record trong luồng source partition đó có thể được giữ. Điều này không tạo global order giữa các source partition, cũng không sắp thứ tự record local được producer ghi trực tiếp vào target xen kẽ với record mirror.

Nếu target topic có partition count hoặc partition mapping không tương thích, hoặc một tầng aggregation phân phối lại record, không được giả định cùng aggregate vẫn nằm trên cùng partition. Với workload cần ordering, xác minh source partition được map sang target partition nào, giữ partition topology tương thích và kiểm thử thứ tự sau replication.

## 7. Remote topic naming và tránh replication loop

DefaultReplicationPolicy của MM2 thường thêm alias source vào tên topic đích, ví dụ:

~~~text
Source cluster primary:
  orders.events

Target cluster dr:
  primary.orders.events
~~~

Tên remote topic giúp nhận diện nguồn và hỗ trợ tránh replicate vòng lặp. Trong topology hai chiều, không tùy tiện thay bằng IdentityReplicationPolicy hoặc xóa prefix để mọi cluster ghi vào cùng một topic; cần thiết kế rõ loop prevention và topic ownership.

Nếu muốn hợp nhất dữ liệu từ nhiều cluster vào một logical topic, nên có bước aggregation/bridge riêng. Tầng hợp nhất phải xác định origin, event ID, key, version và conflict policy; không chỉ đổi tên topic.

Không replicate mọi topic một cách mù quáng. Internal topics, checkpoint topics, heartbeat topics, offset-sync topics và topic vận hành có semantics riêng. Cấu hình include/exclude phải được review.

## 8. Source offset, target offset và checkpoint

Offset là vị trí trong một partition của một cluster. Offset 500 ở source không có nghĩa record tương ứng nằm ở offset 500 tại target.

MM2 phát offset-sync records để ánh xạ source offset sang target offset và checkpoint để biểu diễn tiến độ consumer group. Các mapping này được dùng trong quá trình chuyển consumer sang cluster khác.

~~~mermaid
flowchart TD
    A[Source topic partition offset] --> B[MM2 replication]
    B --> C[Target topic partition offset]
    A --> D[Offset-sync mapping]
    D --> E[Checkpoint for consumer group]
    E --> F[Translate/reset target group offset]
~~~

Điểm cần nhớ:

- Không copy committed offset source sang target như một con số nguyên rồi mặc định đúng.
- Checkpoint được phát theo chu kỳ; có thể không phản ánh ngay trạng thái mới nhất.
- Mapping phụ thuộc record đã replicate và offset-sync history.
- Consumer group phải được chuyển theo quy trình phù hợp với phiên bản MM2.
- Nếu checkpoint không có hoặc quá cũ, cần quyết định replay/skip theo RPO và nghiệp vụ.

Trước failover, lưu committed offsets hiện tại và kiểm tra checkpoint age. Khi dùng sync.group.offsets.enabled, xác minh connector có quyền và group target đáp ứng điều kiện đồng bộ theo version; không bật đồng bộ offset hai chiều mà không có ownership plan.

## 9. Vì sao duplicate xuất hiện khi có nhiều cluster?

Duplicate có thể xuất hiện ở nhiều ranh giới:

1. Producer gửi record nhưng mất response; retry hoặc ứng dụng gửi lại.
2. Consumer hoàn tất side effect nhưng crash trước khi commit offset.
3. MM2 đã ghi target nhưng chưa lưu source progress; sau restart record có thể được replicate lại.
4. Failover xảy ra khi source và target cùng nhận event trong thời gian chuyển vùng.
5. Hai cluster cùng phát một logical event với event ID giống nhau.
6. Replay/backfill gửi lại record đã từng được xử lý.

~~~mermaid
sequenceDiagram
    participant S as Source Kafka
    participant M as MirrorMaker 2
    participant T as Target Kafka
    M->>S: Fetch source record R
    M->>T: Produce R
    T-->>M: ACK
    Note over M: Connector restart before source progress is recorded
    M->>S: Fetch R again
    M->>T: Produce R again
    T-->>M: ACK
    Note over T: Target may contain duplicate logical event
~~~

Đây là cửa sổ duplicate trong mô hình at-least-once. Hãy xem replication path là at-least-once trừ khi đã cấu hình, xác minh và kiểm thử rõ semantics exactly-once source phù hợp với đúng connector/version. Không coi connector RUNNING hoặc producer idempotence là bằng chứng toàn pipeline không thể có duplicate.

## 10. Phân biệt các lớp idempotence

| Cơ chế | Bảo vệ điều gì? | Không bảo vệ điều gì? |
|---|---|---|
| Idempotent producer | Retry protocol của producer trong phạm vi producer identity/sequence | Duplicate do app gửi lại, consumer replay hoặc hai cluster |
| Kafka transaction | Atomic consume-transform-produce và offset commit trong transaction được hỗ trợ trên một cluster | Atomic commit với database ngoài Kafka hoặc transaction xuyên hai cluster |
| Stable event ID | Nhận diện cùng một logical event qua retry/replication/replay | Tự ngăn duplicate nếu consumer không lưu/check ID |
| Idempotent consumer/inbox | Không áp dụng lại side effect cho event đã xử lý | Không tự giải quyết event khác ID nhưng xung đột cùng aggregate |
| Aggregate version | Phát hiện stale/out-of-order update | Không tự chọn writer khi hai vùng cùng tạo version hợp lệ giống nhau |

Exactly-once semantics của Kafka hữu ích trong pipeline Kafka-to-Kafka có transaction phù hợp và consumer dùng read_committed. Nó không biến toàn bộ hệ thống gồm database, HTTP service và hai cluster thành một distributed transaction.

## 11. Event ID phải ổn định qua replication và retry

Mỗi logical event nên có event ID được tạo một lần tại nguồn và giữ nguyên qua retry, outbox, replication và replay.

Một event envelope có thể gồm:

~~~java
public record EventEnvelope<T>(
    String eventId,
    String aggregateId,
    long aggregateVersion,
    String originCluster,
    long writerEpoch,
    Instant occurredAt,
    String eventType,
    int schemaVersion,
    T payload
) {}
~~~

Ý nghĩa:

- eventId: định danh logical event, giữ nguyên khi retry/replicate.
- aggregateId: key nghiệp vụ cần ordering.
- aggregateVersion: version tăng theo aggregate.
- originCluster: cluster phát event ban đầu.
- writerEpoch: fencing generation của writer nếu có.
- occurredAt: thời điểm nghiệp vụ, chỉ dùng như metadata; không tự coi là thứ tự tuyệt đối.
- eventType/schemaVersion: contract và khả năng tương thích.

Có thể lưu source topic/partition/offset trong metadata khi replicate để điều tra, nhưng source coordinate không thay thế event ID. Cùng một event có thể được publish lại ở offset khác; event ID vẫn nhận diện cùng logical event.

Không tạo event ID mới mỗi lần retry. Nếu mỗi lần retry có ID mới, consumer không thể nhận ra các bản sao cùng một nghiệp vụ.

## 12. Idempotent consumer bằng inbox

Nếu consumer ghi database, cách phổ biến là lưu event ID trong bảng inbox với unique constraint trong cùng transaction với thay đổi nghiệp vụ.

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    origin_cluster VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
~~~

Với PostgreSQL:

~~~sql
INSERT INTO processed_events (
    event_id,
    aggregate_id,
    aggregate_version,
    origin_cluster,
    processed_at
)
VALUES (
    :event_id,
    :aggregate_id,
    :aggregate_version,
    :origin_cluster,
    CURRENT_TIMESTAMP
)
ON CONFLICT (event_id) DO NOTHING;
~~~

Trong cùng database transaction:

1. Insert event ID vào inbox.
2. Nếu insert không tạo row mới, event đã xử lý; bỏ qua side effect trùng.
3. Nếu insert thành công, kiểm tra aggregate version.
4. Áp dụng thay đổi nghiệp vụ.
5. Commit database transaction.
6. Sau đó mới commit Kafka offset hoặc ACK theo cơ chế consumer.

Nếu process crash sau DB commit nhưng trước offset commit, record được giao lại; inbox unique constraint ngăn side effect bị áp dụng lần nữa. Nếu commit Kafka offset trước DB transaction, crash có thể làm mất side effect vì broker đã ghi nhận tiến độ.

Nếu cùng event ID xuất hiện nhưng payload hash khác nhau, không âm thầm bỏ qua. Ghi nhận integrity conflict và đưa vào luồng điều tra.

## 13. Aggregate version để phát hiện out-of-order event

Event ID xử lý duplicate; aggregate version xử lý thứ tự theo entity. Ví dụ một order phát:

~~~text
OrderCreated  version=1
OrderPaid     version=2
OrderShipped  version=3
~~~

Consumer có thể lưu version hiện tại và chỉ chấp nhận transition hợp lệ:

~~~sql
UPDATE orders
SET status = :new_status,
    version = :incoming_version
WHERE order_id = :order_id
  AND version = :incoming_version - 1;
~~~

Nếu update không thành công, có thể event bị trùng, stale hoặc thiếu version trước đó. Phải phân biệt:

- Incoming version nhỏ hơn hoặc bằng current version: duplicate/stale event; kiểm tra event ID và lịch sử.
- Incoming version lớn hơn current version + 1: thiếu event trước đó; chờ/retry/reconcile.
- Hai event khác nhau cùng aggregate version: conflict hoặc producer bug; quarantine để điều tra.

Không chỉ dùng timestamp để quyết định event mới hơn. Đồng hồ giữa cluster/host có thể lệch; timestamp có thể phản ánh thời điểm gửi chứ không phải thứ tự commit nghiệp vụ.

## 14. Ordering khi consumer xử lý song song

Kafka giữ thứ tự fetch trong partition, nhưng ứng dụng có thể làm mất thứ tự nếu dispatch từng record sang nhiều thread và cho phép hoàn tất tùy ý.

Ví dụ partition chứa version 1, 2, 3 nhưng executor hoàn tất 2, 3, 1. Nếu side effect không có version guard, state có thể bị ghi lùi.

Các lựa chọn:

- Xử lý tuần tự từng partition.
- Dùng keyed executor để cùng aggregate luôn vào cùng worker lane.
- Dùng aggregate version và compare-and-set ở database.
- Dùng bounded concurrency nhưng serialize side effect theo key.
- Commit offset chỉ sau khi các record trước đó trong partition đã hoàn tất theo đúng semantics.

Không commit offset vượt qua record chưa xử lý thành công nếu cần đảm bảo replay an toàn. Với asynchronous listener, phải hiểu rõ framework acknowledgment và commit semantics; việc listener return không nhất thiết đồng nghĩa mọi task đã hoàn tất.

## 15. Key conflict khi hai cluster cùng ghi

Giả sử cluster A và B cùng có topic orders.events, cả hai đều nhận update cho order-42:

~~~text
Cluster A:
  order-42, version=12, status=PAID

Cluster B:
  order-42, version=12, status=CANCELLED
~~~

Hai event có cùng key nhưng nội dung khác nhau. Kafka không thể tự biết nghiệp vụ nào đúng. Nếu hai luồng được hợp nhất, append order tại target có thể chỉ phản ánh thứ tự record đến target, không phản ánh quan hệ causal hoặc quyết định của business.

Một số tình huống:

- Hai vùng xử lý cùng một command do request được gửi lặp.
- Mạng chia cắt khiến mỗi vùng tiếp tục nhận ghi.
- Failover không fence primary cũ.
- Hai writer cùng phát version tiếp theo từ cùng state snapshot.
- Đồng bộ dữ liệu hai chiều khiến event bị replicate vòng lặp hoặc xử lý lại.

Giải pháp tốt nhất là giảm số writer có quyền cập nhật cùng aggregate. Nếu không thể, phải có conflict-resolution policy được domain owner chấp nhận.

## 16. Chiến lược 1: single-writer per key hoặc shard

Mỗi aggregate/key có một cluster hoặc writer authority sở hữu tại một thời điểm. Các vùng khác có thể đọc bản sao nhưng không ghi trực tiếp key đó.

Ví dụ:

~~~text
hash(aggregateId) -> ownership shard
shard 0..4999    -> cluster A
shard 5000..9999 -> cluster B
~~~

Ưu điểm:

- Ordering dễ xác định.
- Ít conflict cần merge.
- Consumer có thể dùng aggregate version tuần tự.

Nhược điểm:

- Cần routing/ownership metadata.
- Failover cần chuyển ownership và fence writer cũ.
- Một vùng mất kết nối có thể làm một số key tạm thời không ghi được.

Single-writer không nhất thiết là một cluster duy nhất cho toàn hệ thống; có thể phân vùng ownership theo tenant hoặc aggregate shard.

## 17. Chiến lược 2: fencing epoch và writer lease

Trong failover, vấn đề nguy hiểm là primary cũ phục hồi và tiếp tục ghi sau khi DR đã trở thành primary mới. Đây là split-brain.

Một writer lease có thể cấp epoch tăng dần:

~~~text
Cluster A owns order-42 at epoch 7
Failover grants cluster B epoch 8
Cluster A resumes with epoch 7 -> reject
Cluster B writes with epoch 8 -> accept
~~~

Consumer/state store kiểm tra epoch và từ chối writer epoch cũ. Epoch cần được cấp từ một authority nhất quán bên ngoài hai cluster hoặc từ cơ chế ownership có consensus; không để mỗi cluster tự tăng epoch độc lập.

Kafka transactional.id và producer fencing bảo vệ producer identity trong phạm vi một Kafka cluster. Nó không tự fence producer ở cluster khác. Cross-cluster fencing cần ownership/lease coordinator và validation ở nơi lưu state hoặc downstream.

## 18. Chiến lược 3: version check và compare-and-set

Nếu state được lưu trong database, dùng optimistic concurrency:

~~~sql
UPDATE account_balance
SET balance = :new_balance,
    version = :incoming_version
WHERE account_id = :account_id
  AND version = :expected_previous_version;
~~~

Chỉ một update có expected version phù hợp mới thành công. Event đến sai thứ tự hoặc cùng version sẽ không ghi đè state hiện tại.

Khi update không thành công:

1. Đọc current version.
2. So sánh event version và event ID.
3. Phân loại duplicate, stale event, gap hoặc true conflict.
4. Chờ/retry nếu thiếu version trước.
5. Quarantine nếu hai event khác nhau cùng version.
6. Ghi conflict record và alert cho owner nếu cần quyết định nghiệp vụ.

Version check cần version được cấp có thẩm quyền. Nếu hai cluster cùng tự tạo version 13 từ version 12, compare-and-set ở database chỉ bảo đảm một update thắng; nó chưa quyết định event nào đúng. Cần single writer, epoch hoặc merge rule.

## 19. Chiến lược 4: Last-write-wins và giới hạn của timestamp

Last-write-wins (LWW) chọn cập nhật có timestamp lớn hơn. Cách này đơn giản nhưng nguy hiểm nếu đồng hồ các vùng lệch hoặc timestamp do client tự khai báo.

Ví dụ:

~~~text
Region A clock is 4 seconds ahead:
  status=PAID, occurredAt=10:00:04

Region B:
  status=CANCELLED, occurredAt=10:00:02
~~~

Nếu chọn timestamp lớn nhất, PAID thắng dù CANCELLED có thể là hành động nghiệp vụ xảy ra sau theo causal order thật. Timestamp không chứng minh quan hệ nhân quả.

Nếu domain chấp nhận LWW:

- Dùng timestamp từ nguồn có kiểm soát.
- Quy định tie-breaker deterministic như writer ID.
- Theo dõi clock skew.
- Không dùng LWW cho state transition không giao hoán như thanh toán/hủy đơn nếu không có business rule.
- Lưu conflict history để audit.

Version/epoch hoặc domain merge thường an toàn hơn wall-clock timestamp.

## 20. Chiến lược 5: CRDT hoặc domain merge

Một số dữ liệu có thể hợp nhất theo quy tắc toán học thay vì chọn một bản ghi thắng. Ví dụ:

- G-counter cho bộ đếm chỉ tăng.
- OR-set cho tập hợp thêm/xóa có metadata.
- Một số cấu trúc map/register có merge rule deterministic.

Kafka không tự cung cấp CRDT cho application key. Ứng dụng phải định nghĩa state, merge operation, causal metadata và serialization. Không phải mọi nghiệp vụ đều phù hợp:

| Dữ liệu | Merge có thể phù hợp | Cần cẩn trọng |
|---|---|---|
| View count | Cộng delta theo source | Duplicate delta phải deduplicate |
| Set membership | OR-set hoặc observed-remove set | Tombstone/metadata có thể tăng |
| Like counter | G-counter/PN-counter | Cần event identity và replica identity |
| Số dư tài khoản | Thường không thể cộng tùy ý | Cần ledger và business invariant |
| Trạng thái đơn hàng | Domain state machine | PAID/CANCELLED có thể xung đột |

Nếu merge không có tính associative, commutative và idempotent phù hợp, kết quả có thể phụ thuộc thứ tự nhận event và không hội tụ.

## 21. Compacted topic và xung đột cùng key

Trong compacted topic, Kafka giữ trạng thái mới nhất theo key trong từng partition theo thứ tự log của partition. Compaction không biết version nghiệp vụ và không hợp nhất state từ nhiều cluster.

Nếu hai cluster cùng phát key order-42:

~~~text
Cluster A: key=order-42, version=12, status=PAID
Cluster B: key=order-42, version=13, status=CANCELLED
~~~

Nếu hai record được append vào cùng target partition theo thứ tự version 13 rồi version 12, compaction có thể giữ record version 12 là record cuối theo log. Kafka không tự nhận biết version 13 mới hơn về nghiệp vụ.

Vì vậy:

- Validate version trước khi ghi state topic.
- Dùng một writer authority cho mỗi key nếu có thể.
- Nếu cần merge nhiều nguồn, hợp nhất ở processor/service có conflict policy.
- Giữ event history riêng nếu cần audit/rebuild.
- Xử lý tombstone như một state transition có version/epoch, không chỉ là key null.

Không dùng compacted topic làm cơ chế conflict resolution phân tán.

## 22. Tránh replication loop và double processing

Trong active-active, cần phân biệt local topic và remote topic. DefaultReplicationPolicy thêm cluster alias vào remote topic; cấu hình flow và topic filter cần tránh replicate remote topic quay lại như một nguồn mới.

Nguyên tắc:

- Đặt alias cluster ổn định, dễ nhận diện.
- Chỉ replicate topic được chọn.
- Giữ remote topic prefix nếu dùng default policy.
- Không flatten hai luồng thành một topic cùng tên mà không có aggregation layer.
- Không replicate internal topic của MM2/Connect như business data.
- Đánh dấu originCluster và eventId trong event metadata.
- Theo dõi số lần một event xuất hiện ở từng cluster.

Nếu cần chuyển remote topic thành local topic, thực hiện qua pipeline có kiểm soát và bảo đảm không tạo vòng replicate ngược.

## 23. Failover: chuyển writer và consumer sang DR

Failover phải xử lý cả producer ownership, consumer offsets và dữ liệu chưa replicate. Không chỉ đổi bootstrap server.

~~~mermaid
flowchart TD
    A[Primary incident] --> B[Declare failover and choose authority]
    B --> C[Fence or stop old writers]
    C --> D[Measure replication lag / RPO]
    D --> E[Verify target topic, ISR and checkpoints]
    E --> F[Translate consumer offsets]
    F --> G[Start DR consumers with idempotency]
    G --> H[Route producers to DR]
    H --> I[Monitor duplicate, version and lag]
~~~

Quy trình:

1. Declare incident và xác định ai có quyền quyết định failover.
2. Chọn cluster authoritative cho giai đoạn DR.
3. Fence primary cũ: dừng producer, thu hồi routing/credential hoặc vô hiệu hóa writer theo ownership epoch.
4. Đo replication lag và xác định RPO thực tế; ghi lại khoảng dữ liệu có thể thiếu.
5. Xác minh target topic/partition, ISR, leader và MM2 connector health.
6. Kiểm tra checkpoint/offset-sync age cho từng consumer group.
7. Translate/reset consumer offsets theo checkpoint; không copy số offset source trực tiếp.
8. Khởi động consumer DR với inbox/deduplication và version guard.
9. Chuyển producer routing sang DR sau khi old writer đã bị fence.
10. Theo dõi duplicate, aggregate version gap, conflict, consumer lag và replication.

Nếu checkpoint thiếu hoặc stale, quyết định replay từ vị trí an toàn hơn hay chấp nhận skip phải dựa trên nghiệp vụ và RPO. Replay có thể tạo duplicate; skip có thể làm mất xử lý. Không tự chọn latest chỉ để giảm lag.

## 24. Failback và reconciliation

Failback về cluster ban đầu cũng là một migration, không phải thao tác đổi DNS đơn giản. Trong thời gian DR hoạt động, dữ liệu mới có thể chỉ tồn tại ở DR hoặc đã được replicate ngược.

Quy trình:

1. Chọn authoritative cluster trong giai đoạn failback.
2. Xác minh cluster cũ đã khỏe và đủ capacity.
3. Thiết lập replication direction có kiểm soát; tránh hai chiều không có loop prevention.
4. Fence writer tại thời điểm cutover và xác nhận không có dual writer.
5. Đợi replication catch-up theo RPO mục tiêu.
6. Reconcile event ID, aggregate version và conflict records.
7. Translate consumer offsets bằng checkpoint mới.
8. Chuyển consumer/producer theo thứ tự được runbook định nghĩa.
9. Theo dõi duplicate, stale event, version gap và lag sau cutover.
10. Chỉ gỡ replication/DR resources khi owner xác nhận hoàn tất.

### Reconciliation cần đối chiếu gì?

- Stable event ID và payload hash.
- Origin cluster và source topic/partition/offset.
- Aggregate ID và aggregate version.
- Writer epoch/ownership token.
- Event type và schema version.
- State hiện tại trong database/domain store.
- Event bị thiếu, event trùng và event có version xung đột.

Offset không phải global event identity. Hai cluster có thể có offset khác nhau cho cùng event; reconciliation nên dựa trên event ID/version và source metadata.

## 25. Monitoring cho multi-cluster correctness

Theo dõi availability của connector là chưa đủ. Cần metric phản ánh correctness và độ trễ dữ liệu:

| Metric/Signal | Mục đích |
|---|---|
| Replication record lag theo topic-partition | Biết source còn bao nhiêu record chưa tới target |
| Replication latency / oldest event age | Đo độ trễ DR và RPO gần đúng |
| Heartbeat age | Phát hiện replication path hoặc cluster connectivity lỗi |
| Checkpoint age | Biết offset translation có thể đã cũ |
| Source/target partition count mismatch | Phát hiện mapping partition không tương thích |
| Duplicate event ID rate | Đo duplicate sau replication/replay |
| Inbox dedup hit rate | Biết consumer đã bỏ qua event trùng bao nhiêu |
| Aggregate version gap/regression | Phát hiện event thiếu thứ tự hoặc stale |
| Writer epoch rejection | Phát hiện writer cũ hoặc split-brain |
| Conflict queue size/age | Theo dõi xung đột cần xử lý |
| Target URP/offline partitions | Xác minh DR cluster có thể phục vụ khi failover |
| Consumer lag theo group/partition | Theo dõi khả năng xử lý ở cluster đích |

Định nghĩa SLO cho RPO, RTO, replication lag và thời gian reconciliation. RPO phải được đo từ dữ liệu chưa replicate ở thời điểm failover, không chỉ từ trạng thái connector.

## 26. Bài thực hành: duplicate, ordering và failover

Tạo hai Kafka cluster lab A và B, cùng cấu hình topic orders.events và MM2 replication:

1. Gửi event cho order-42 với event ID cố định và aggregate version 1, 2, 3 vào cluster A.
2. Replicate sang cluster B và so sánh source/target offsets.
3. Kiểm tra remote topic naming và checkpoint/offset-sync topics.
4. Tạo consumer B dùng inbox table; replay cùng record và xác minh side effect chỉ áp dụng một lần.
5. Dừng/restart connector trong lab tại các thời điểm khác nhau; quan sát duplicate.
6. Gửi cùng aggregate key từ hai cluster với version cạnh tranh; quan sát conflict.
7. Thử version guard để từ chối stale event và phát hiện version gap.
8. Thử writer epoch: writer epoch cũ bị từ chối sau khi chuyển ownership.
9. Mô phỏng failover, fence writer A và chuyển consumer/producer sang B.
10. Mô phỏng failback, reconcile event ID/version và translate consumer offsets.
11. Thử compacted topic với hai update cùng key đến sai thứ tự; xác minh Kafka compaction không giải quyết business conflict.
12. Đo replication lag, checkpoint age, duplicate rate và thời gian phục hồi.

Chỉ dừng connector, tạo duplicate và mô phỏng split-brain trong môi trường lab. Không cố ý tạo hai writer production cho cùng key để thử conflict.

## 27. Checklist production

- Chọn active-passive, active-active theo shard hay active-active merge dựa trên nghiệp vụ.
- Xác định writer authority cho mỗi aggregate/key.
- Dùng stable event ID xuyên producer, outbox, retry, MM2 và replay.
- Dùng aggregate version/sequence để phát hiện stale hoặc gap.
- Dùng idempotent consumer/inbox cho side effect ngoài Kafka.
- Giữ Kafka key theo aggregate cần ordering.
- Không giả định ordering giữa partition hoặc cluster.
- Giữ partition count/partitioner mapping tương thích khi cần cùng-key routing.
- Dùng MM2 checkpoints/offset translation thay vì copy offset số học.
- Đo replication lag, checkpoint age và RPO.
- Giữ remote topic naming/replication policy để tránh loop.
- Không xem MM2 replication là synchronous hoặc exactly-once cross-cluster.
- Fence writer cũ trước khi kích hoạt writer DR.
- Dùng writer epoch/lease hoặc ownership control để chống split-brain.
- Định nghĩa conflict policy: reject, single-writer, version check, LWW có kiểm soát hoặc CRDT/domain merge.
- Không dựa vào wall-clock timestamp đơn lẻ để quyết định state mới nhất.
- Không dùng compaction làm conflict resolver.
- Có runbook failover, failback và reconciliation.
- Theo dõi duplicate, version gap, conflict queue và target replica health.
- Kiểm thử RPO/RTO và replay trong lab định kỳ.

## 28. Những nhầm lẫn thường gặp

- **Kafka bảo đảm thứ tự toàn topic:** thứ tự chỉ được bảo đảm trong từng partition.
- **Cùng key luôn có thứ tự giữa hai cluster:** mỗi cluster có log riêng; cần ownership/version/merge policy.
- **MM2 là synchronous replication:** MM2 bất đồng bộ và có replication lag.
- **Source offset bằng target offset:** offset thuộc partition log riêng của từng cluster; dùng checkpoint/translation.
- **Idempotent producer loại bỏ mọi duplicate:** nó xử lý retry protocol của producer, không xử lý replay/consumer/đa cluster.
- **Kafka transaction là distributed transaction:** transaction Kafka không tự bao trùm database và cluster khác.
- **Timestamp lớn hơn nghĩa là event mới hơn:** clock skew và causal order có thể làm kết luận sai.
- **Compaction giữ business version cao nhất:** compaction giữ record cuối theo log order của partition, không hiểu version nghiệp vụ.
- **Tăng partition không ảnh hưởng ordering:** key có thể được route sang partition khác sau thay đổi.
- **Failover chỉ cần đổi bootstrap server:** cần fence writer, translate offsets, đánh giá RPO và bật idempotency.
- **Connector RUNNING nghĩa là dữ liệu đã đồng bộ:** phải đo record lag/checkpoint age và kiểm tra target records.
- **Active-active không cần conflict resolution:** hai writer có thể tạo cập nhật không tương thích cho cùng key.

Trong multi-cluster Kafka, thứ tự chỉ có ý nghĩa trong ranh giới partition của từng cluster; replication không tự tạo global order và có thể tạo duplicate trong các cửa sổ restart/replay. Thiết kế vững cần stable event ID, aggregate version, idempotent consumer, ownership/fencing và conflict policy phù hợp domain. MM2 checkpoints hỗ trợ chuyển offset nhưng không thay thế reconciliation. Failover/failback phải fence writer, đo RPO, translate offsets và xác minh event/version trước khi xem cutover là hoàn tất.
