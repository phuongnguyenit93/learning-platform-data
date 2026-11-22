# MirrorMaker 2 và nền tảng Kafka Connect

MirrorMaker 2 (MM2) là công cụ sao chép dữ liệu giữa các Kafka cluster, được xây dựng trên nền Kafka Connect. MM2 thường dùng cho disaster recovery, di chuyển workload giữa cluster, phân phối dữ liệu đa vùng và xây dựng mô hình active-passive hoặc active-active. Để vận hành đúng, cần hiểu cả kiến trúc Kafka Connect lẫn các connector chuyên biệt của MM2: **MirrorSourceConnector**, **MirrorCheckpointConnector** và **MirrorHeartbeatConnector**.

MM2 không đơn giản là một lệnh copy topic. Nó đồng bộ record, duy trì metadata phục vụ theo dõi replication, tạo checkpoint để hỗ trợ dịch chuyển consumer group và cung cấp heartbeat để kiểm tra kết nối giữa các cluster. Tuy nhiên, replication topic không tự động đồng nghĩa với sao chép nguyên trạng mọi trạng thái consumer, transaction hoặc ứng dụng. Failover/failback vẫn cần kế hoạch về offset translation, duplicate, ordering, RPO/RTO và quyền ghi.

## 1. Kafka Connect là nền tảng của MirrorMaker 2

Kafka Connect là runtime tích hợp để di chuyển dữ liệu vào/ra Kafka bằng connector. Một Connect cluster thường gồm:

- **Worker:** tiến trình chạy Kafka Connect, nhận cấu hình và thực thi connector/task.
- **Connector:** quản lý một integration job, chia công việc thành task và cung cấp cấu hình.
- **Task:** đơn vị thực thi đọc từ source hoặc ghi tới sink.
- **Converters:** chuyển đổi key/value giữa Kafka Connect data model và wire format, ví dụ JSON hoặc Avro.
- **Transforms (SMT):** biến đổi record nhẹ trong pipeline.
- **Config/offset/status topics:** các internal topic lưu cấu hình connector, source offsets và trạng thái runtime.

~~~mermaid
flowchart TB
    A["Connect REST API"] --> W["Kafka Connect Workers"]
    W --> C["Connector"]
    C --> T1["Task 0"]
    C --> T2["Task 1"]
    T1 --> S["Source / Sink system"]
    T2 --> S
    W --> I1[("connect-configs")]
    W --> I2[("connect-offsets")]
    W --> I3[("connect-status")]
~~~

Connect có thể chạy ở standalone mode hoặc distributed mode. Distributed mode phù hợp production vì nhiều worker cùng tham gia một Connect cluster, phân phối task và phục hồi task khi worker gặp sự cố.

### Connect internal topics

Trong distributed mode, worker cần các topic nội bộ:

| Topic | Mục đích |
|---|---|
| Config topic | Lưu cấu hình connector và task |
| Offset topic | Lưu source offsets để source connector tiếp tục đọc đúng vị trí |
| Status topic | Lưu trạng thái connector/task và worker |

Tên trong sơ đồ là ví dụ được chọn qua các property worker `config.storage.topic`, `offset.storage.topic` và `status.storage.topic`; chúng không phải tên cố định bắt buộc. Config/offset/status topics thường dùng cleanup policy phù hợp cho dữ liệu compacted và cần replication factor/ACL phù hợp. Các topic này thuộc Kafka Connect runtime. Chúng khác với các topic MM2 tạo ra để quản lý replication như checkpoint, heartbeat và offset-sync. Khi triển khai MM2, phải cấu hình riêng cả hai nhóm internal topics và bảo vệ chúng bằng replication factor/ACL phù hợp.

Ví dụ cấu hình worker distributed:

~~~properties
bootstrap.servers=kafka-connect-1:9092,kafka-connect-2:9092
group.id=mm2-connect-workers
config.storage.topic=connect-configs
offset.storage.topic=connect-offsets
status.storage.topic=connect-status
config.storage.replication.factor=3
offset.storage.replication.factor=3
status.storage.replication.factor=3
~~~

## 2. MirrorMaker 2 gồm những thành phần nào?

MM2 cung cấp ba connector chính:

| Connector | Vai trò |
|---|---|
| MirrorSourceConnector | Đọc record từ source cluster và ghi sang target cluster |
| MirrorCheckpointConnector | Tạo checkpoint/offset mapping để hỗ trợ consumer group chuyển từ source sang target |
| MirrorHeartbeatConnector | Phát heartbeat giữa các cluster để kiểm tra đường replication và hỗ trợ quan sát topology |

MM2 cũng sử dụng các thành phần quản lý offset sync và replication policy. Tên topic mặc định thường gặp:

- `heartbeats`
- `sourceCluster.checkpoints.internal`
- Topic offset-sync mặc định thường có dạng `mm2-offset-syncs.targetCluster.internal` và được đặt trên source cluster khi `offset-syncs.topic.location=source`
- Topic được mirror với prefix mặc định `sourceCluster.topicName` nếu dùng DefaultReplicationPolicy.

Tên và vị trí chính xác của internal topic có thể thay đổi theo cấu hình MM2 và Kafka release; `offset-syncs.topic.location` có thể thay đổi cluster lưu offset-sync topic. Trước khi vận hành, kiểm tra topic thực tế được tạo trong cả source và target cluster.

~~~mermaid
flowchart LR
    subgraph SRC["Source cluster"]
        S1["orders"]
        S2["payments"]
        S3["Consumer groups"]
    end
    subgraph MM["MirrorMaker 2 / Connect"]
        MS["MirrorSource"]
        MC["MirrorCheckpoint"]
        MH["MirrorHeartbeat"]
    end
    subgraph DST["Target cluster"]
        D1["source.orders"]
        D2["source.payments"]
        D3["Checkpoint / heartbeat topics"]
    end
    S1 --> MS
    S2 --> MS
    MS --> D1
    MS --> D2
    S3 --> MC
    MC --> D3
    MH <--> SRC
    MH <--> DST
~~~

MirrorSource chịu trách nhiệm data replication. Checkpoint connector theo dõi group offsets và ghi checkpoint. Heartbeat connector tạo tín hiệu để xác nhận đường kết nối giữa các cluster đang hoạt động.

## 3. Luồng replication giữa source và target

Một replication flow cơ bản:

1. MirrorSourceConnector kết nối source cluster và subscribe các topic được chọn.
2. Task đọc record từ source theo partition.
3. Record được chuyển qua converter/SMT nếu có.
4. Producer của connector ghi record sang target topic tương ứng.
5. MM2 tạo offset-sync metadata để liên kết offset source và target.
6. MirrorCheckpointConnector đọc consumer group offsets, tạo checkpoint trên target.
7. MirrorHeartbeatConnector phát heartbeat để thể hiện source/target còn liên lạc.

MM2 thường chạy theo mô hình asynchronous replication. Source producer có thể tiếp tục ghi trong khi target đang theo kịp. Vì vậy target có thể trễ so với source và một số record mới nhất chưa được mirror khi xảy ra sự cố.

### Topic naming và ReplicationPolicy

DefaultReplicationPolicy thường thêm alias source vào đầu tên topic:

~~~text
Source cluster: orders
Target cluster: dc1.orders
~~~

Prefix giúp phân biệt dữ liệu được mirror từ cluster nào và hỗ trợ tránh vòng lặp replication. Một số môi trường dùng IdentityReplicationPolicy để giữ nguyên tên topic, nhưng cách này cần thiết kế cẩn thận để tránh loop và xung đột topic giữa các cluster.

Không tự ý đổi replication policy sau khi đã chạy replication mà chưa có migration plan. Topic names, ACL, consumer subscriptions và routing logic có thể phụ thuộc policy hiện tại.

## 4. Cấu hình MM2 bằng connect-mirror-maker.properties

MM2 có thể được cấu hình bằng file properties rồi chạy qua script connect-mirror-maker.sh. Ví dụ một chiều từ cluster primary sang dr:

~~~properties
clusters=primary,dr

primary.bootstrap.servers=kafka-primary-1:9092,kafka-primary-2:9092
dr.bootstrap.servers=kafka-dr-1:9092,kafka-dr-2:9092

primary->dr.enabled=true
primary->dr.topics=orders,payments,inventory
primary->dr.groups=order-service,payment-service

primary->dr.emit.heartbeats.enabled=true
primary->dr.emit.checkpoints.enabled=true
primary->dr.sync.group.offsets.enabled=true

replication.factor=3
tasks.max=8
refresh.topics.enabled=true
refresh.groups.enabled=true
refresh.topics.interval.seconds=60
refresh.groups.interval.seconds=60
~~~

Đây là cấu hình minh họa cho một số option phổ biến. Property được hỗ trợ và default có thể khác theo Kafka version. Hãy đối chiếu file cấu hình mẫu của đúng distribution và kiểm tra connector config sau khi deploy. Không đưa credential thật vào file properties được commit.

Chạy MM2:

~~~bash
bin/connect-mirror-maker.sh \
  config/connect-mirror-maker.properties
~~~

MM2 khởi chạy Connect runtime cùng các connector được cấu hình. Với production, nên chạy dưới process manager/container/orchestrator có health check, restart policy, resource limit và log collection.

## 5. Cấu hình bảo mật kết nối hai cluster

Source và target có thể dùng security protocol khác nhau. Mỗi alias cluster có thể khai báo cấu hình Kafka client riêng:

~~~properties
primary.security.protocol=SASL_SSL
primary.sasl.mechanism=SCRAM-SHA-512
primary.sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="mm2-primary" password="__PRIMARY_SECRET__";
primary.ssl.truststore.location=/etc/mm2/primary-truststore.p12
primary.ssl.truststore.type=PKCS12

dr.security.protocol=SASL_SSL
dr.sasl.mechanism=SCRAM-SHA-512
dr.sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="mm2-dr" password="__DR_SECRET__";
dr.ssl.truststore.location=/etc/mm2/dr-truststore.p12
dr.ssl.truststore.type=PKCS12
~~~

Các property minh họa cách phân biệt client config theo alias. Cần cấu hình password/store secret bằng secret manager hoặc Connect ConfigProvider phù hợp. Tránh để secret trong source control, command history hoặc REST response.

### Quyền cần cấp

MM2 cần quyền khác nhau trên source và target:

- Source: describe cluster/topic, read topic, read consumer group offsets và metadata cần thiết.
- Target: create/describe/write topic, tạo và ghi internal topics/checkpoint/heartbeat/offset-sync theo connector đang dùng.
- Connect internal topics: quyền đọc/ghi config, offset và status topics của worker.

Quyền chính xác phụ thuộc Kafka version, replication policy và connector config. Cấp least privilege theo danh sách topic/group được mirror; không dùng superuser lâu dài chỉ để tránh lỗi ACL.

## 6. Checkpoint, offset-sync và consumer group offset translation

Một trong những phần dễ hiểu nhầm nhất của MM2 là consumer offset. Source và target có log riêng, partition assignment riêng và offset có thể khác nhau. Vì vậy, committed offset của group trên source không thể đơn giản copy nguyên số sang target.

MM2 dùng hai lớp metadata:

- **Offset-sync:** liên kết offset source với offset tương ứng đã được ghi sang target.
- **Checkpoint:** ghi lại tiến độ consumer group tại source và offset đã dịch sang target để hỗ trợ failover.

Checkpoint thường được ghi vào topic có tên theo dạng `sourceCluster.checkpoints.internal` trên target. Offset-sync topic mặc định thường nằm trên source và có tên theo dạng `mm2-offset-syncs.targetCluster.internal`; cấu hình `offset-syncs.topic.location` có thể thay đổi vị trí. Checkpoint không có nghĩa target consumer group đã tự động commit offset mới ngay lập tức.

`sync.group.offsets.enabled` có thể yêu cầu MM2 đồng bộ translated offsets vào consumer group trên target khi điều kiện phù hợp. Việc đồng bộ thường cần target group không có member active; nếu ứng dụng đã chạy consumer trên target, connector có thể không ghi đè offset của group đó. Hành vi cụ thể phụ thuộc connector, group state, target group existence, policy và version. Cần kiểm thử trước failover.

### Offset translation là phép ánh xạ, không phải sao chép số offset

Ví dụ:

| Source partition | Source committed offset | Offset tương ứng ở target |
|---|---:|---:|
| orders-0 | 10.500 | 10.430 |
| orders-1 | 8.200 | 8.190 |

Các số chỉ minh họa. Target offset có thể khác vì replication bắt đầu từ thời điểm khác, record bị lọc/transform, control records và cách log được ghi. Khi failover, MM2 sử dụng checkpoint/offset-sync để ước lượng hoặc dịch vị trí consumer phù hợp; không giả định mapping luôn chính xác đến cùng một business event trong mọi tình huống.

Nếu group đang active trên source, MM2 có thể không cập nhật offset target theo cách mong muốn trong lúc group còn hoạt động. Quy trình DR nên dừng/đóng consumer source, chờ checkpoint mới nhất, xác nhận target offsets rồi mới khởi động consumer target theo runbook.

## 7. Active-passive và active-active

### Active-passive

Một cluster xử lý production; cluster còn lại nhận dữ liệu mirror và sẵn sàng tiếp quản khi source gặp sự cố.

~~~mermaid
flowchart LR
    P["Primary cluster"] --> M["MM2 replication"]
    M --> D["DR cluster"]
    C["Applications"] --> P
    D -. "Failover sau xác nhận" .-> A["Applications chuyển sang DR"]
~~~

Ưu điểm:

- Dễ xác định cluster nào là nguồn ghi chính.
- Giảm xung đột khi failover.
- Quy trình đối soát và failback đơn giản hơn active-active.

Hạn chế:

- Target có thể có replication lag.
- RPO phụ thuộc tốc độ mirror và thời điểm sự cố.
- Ứng dụng cần endpoint/config chuyển sang target.
- Phải kiểm thử quyền ghi và consumer offset tại DR.

### Active-active

Hai hoặc nhiều cluster cùng nhận traffic ghi. Mỗi cluster có thể mirror dữ liệu sang cluster kia.

Ưu điểm là phục vụ gần người dùng ở nhiều vùng và tăng khả năng hoạt động độc lập theo region. Tuy nhiên, cần xử lý:

- Topic naming và loop prevention.
- Xung đột khi cùng business key được ghi ở nhiều cluster.
- Duplicate event và idempotency.
- Ordering giữa các region.
- Consumer group và offset ownership.
- Quy tắc chọn nguồn authoritative khi failback.

MM2 không phải conflict-free replicated database. Nó không hợp nhất hai event khác nhau ghi đồng thời cho cùng entity thành một trạng thái nghiệp vụ nhất quán. Ứng dụng phải có conflict resolution, versioning hoặc phân vùng quyền ghi theo entity/region.

## 8. Loop prevention và replication policy

Trong topology nhiều cluster, một record có thể bị mirror đi rồi quay lại cluster ban đầu nếu connector không phân biệt nguồn. DefaultReplicationPolicy dùng alias prefix để giúp MM2 nhận biết topic đã được mirror và tránh lặp trong các topology được hỗ trợ.

IdentityReplicationPolicy giữ nguyên tên topic nên cần cấu hình source/target flow rất cẩn thận. Khi dùng nhiều chiều, phải thiết kế rõ:

- Cluster nào là nguồn authoritative cho mỗi topic.
- Connector nào được phép mirror topic nào.
- Prefix/policy nào được dùng.
- ACL nào cho phép source read và target write.
- Cách tránh một topic mirror quay lại cluster xuất phát.

Không bật hai chiều cho mọi topic chỉ bằng cách đảo alias nếu chưa kiểm tra loop prevention, topic naming và consumer subscriptions.

## 9. RPO, RTO và replication lag

Disaster recovery cần hai mục tiêu:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất theo thời gian hoặc business transaction.
- **RTO (Recovery Time Objective):** thời gian tối đa để khôi phục dịch vụ.

RPO không bằng replication factor. RF bảo vệ replica trong một cluster; MM2 replication lag quyết định target đã nhận được bao nhiêu dữ liệu từ source trước thời điểm sự cố.

Một mô hình ước lượng:

\[
RPO_{time} \approx ReplicationLag_{time} + DetectionDelay
\]

Đây chỉ là ước lượng. Cần đối chiếu offset lag, record timestamp, checkpoint freshness và business event reconciliation. Nếu source dừng đột ngột trước khi connector replicate batch cuối, các record chưa đến target có thể mất trong failover.

RTO gồm:

- Phát hiện và xác nhận sự cố.
- Quyết định failover và fencing source nếu còn khả năng ghi.
- Chuyển ứng dụng sang target.
- Xác minh topic/ACL/config và consumer offsets.
- Khởi động producer/consumer và xác nhận business flow.

Đặt SLO replication lag theo criticality của topic, ví dụ payment có ngưỡng age/lag thấp hơn analytics. Không chỉ dùng số offset vì partition có throughput và record size khác nhau.

## 10. Failover từ primary sang DR

Failover phải tránh split-brain ở tầng ứng dụng: hai cluster cùng nhận write cho một nghiệp vụ mà không có quy tắc phân quyền có thể tạo duplicate hoặc conflict.

Quy trình tham khảo:

1. Xác nhận primary thực sự unavailable hoặc đã được fencing để không tiếp tục nhận write.
2. Kiểm tra replication lag và checkpoint freshness trên DR.
3. Xác nhận các topic bắt buộc đã được mirror và ISR/leader trên DR ổn định.
4. Kiểm tra ACL, schema, topic config, retention và downstream dependency tại DR.
5. Dừng consumer group tương ứng trên primary nếu còn hoạt động.
6. Xác nhận checkpoint/translated offsets và quyết định vị trí bắt đầu ở target.
7. Chuyển bootstrap server/secret/config của ứng dụng sang DR.
8. Khởi động consumer/producer theo thứ tự dependency.
9. Chạy smoke test, đối soát event ID/business transaction và xác nhận end-to-end flow.
10. Theo dõi duplicate, missing event, lag và business SLO.

Không chỉ đổi DNS/bootstrap server rồi coi failover hoàn tất. Consumer offset, ACL, topic config, schema registry và các dependency ngoài Kafka đều cần được chuẩn bị.

### Offset cutover

Offset translation dựa trên checkpoint gần nhất. Nếu checkpoint cũ, consumer target có thể đọc lại một số record đã xử lý trên source (duplicate) hoặc bắt đầu sau một phần record chưa được xử lý nếu mapping/commit timing không được kiểm soát. Thiết kế consumer idempotent và đối soát theo event ID.

Với workload quan trọng, có thể chọn bắt đầu từ offset an toàn hơn để tránh bỏ sót, chấp nhận duplicate rồi deduplicate ở ứng dụng. Quyết định phụ thuộc semantics nghiệp vụ và RPO/RTO.

## 11. Failback từ DR về primary

Failback là một lần chuyển quyền ghi khác, không chỉ đảo chiều connector:

1. Primary được phục hồi, kiểm tra cluster health và topic configuration.
2. Chọn cluster authoritative trong giai đoạn DR.
3. Cấu hình replication từ DR về primary cho dữ liệu phát sinh trong thời gian DR active.
4. Xác nhận topic naming/policy không tạo loop và mapping được kiểm tra.
5. Chờ replication lag về ngưỡng chấp nhận.
6. Đóng băng hoặc fencing producer tại DR theo cutover plan.
7. Dừng consumer DR và tạo checkpoint/đối soát cuối.
8. Dịch offset group sang primary nếu mô hình và connector hỗ trợ.
9. Chuyển ứng dụng về primary, xác minh end-to-end.
10. Chuyển lại replication direction theo trạng thái vận hành mới.

Không cho primary và DR cùng ghi vào một logical business stream trong thời gian cutover nếu không có conflict resolution. Lưu lại source of truth cho từng khoảng thời gian để đối soát.

## 12. Exactly-once và giới hạn delivery semantics

MM2 replication thường được xem là asynchronous và không nên mặc định tạo ra exactly-once end-to-end giữa hai cluster. Trong tình huống retry, worker crash hoặc failover, record có thể được mirror lại hoặc consumer có thể đọc lại tùy checkpoint/offset state.

Các lớp cần phân biệt:

- Producer-to-source Kafka durability.
- MM2 source-to-target replication.
- Consumer processing và side effect ở target.
- Business deduplication/reconciliation.

Kafka idempotent producer và transaction có phạm vi đảm bảo riêng trong một cluster/session theo cấu hình. Chúng không tự biến toàn bộ multi-cluster replication và external side effect thành một transaction nguyên tử xuyên hai cluster.

Đối với payment/order/ledger:

- Dùng event ID duy nhất.
- Consumer xử lý idempotent với unique constraint hoặc inbox table.
- Kiểm tra aggregate version/sequence.
- Đối soát source/target theo business ID.
- Lưu audit về thời điểm failover và cluster authoritative.

## 13. Triển khai và quản lý Connect REST API

Trong distributed Connect mode, REST API cho phép quản lý connector:

~~~bash
curl -s http://connect-1:8083/connectors
~~~

Xem trạng thái:

~~~bash
curl -s http://connect-1:8083/connectors/orders-mirror-source/status
~~~

Xem cấu hình:

~~~bash
curl -s http://connect-1:8083/connectors/orders-mirror-source/config
~~~

Tạo connector theo cấu hình REST:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  --data @mirror-source.json \
  http://connect-1:8083/connectors
~~~

Tên connector và endpoint REST phụ thuộc deployment. Bảo vệ Connect REST API bằng network policy, authentication/authorization phù hợp; không mở công khai endpoint quản trị.

MM2 có thể tự quản lý các connector khi chạy bằng connect-mirror-maker. Nếu triển khai từng connector thủ công trên Connect cluster, phải quản lý config/offset/status topics và lifecycle của từng connector nhất quán.

## 14. Monitoring MirrorMaker 2

Theo dõi cả Connect runtime và replication semantics:

| Nhóm | Chỉ số cần quan sát | Ý nghĩa |
|---|---|---|
| Connect worker | Worker availability, rebalance, task state | Runtime có hoạt động không |
| MirrorSource | Record read/write rate, replication latency, errors | Dữ liệu có được mirror không |
| MirrorCheckpoint | Checkpoint age, group discovery, checkpoint write errors | Offset mapping có đủ mới không |
| MirrorHeartbeat | Heartbeat age và source-target connectivity | Đường replication có còn thông |
| Target topics | Partition count, ISR, log end offset, record age | Target có nhận và lưu dữ liệu ổn định không |
| Consumer groups | Source/target committed offsets, translated offset, lag | Cutover có thể bắt đầu an toàn không |
| Business | Missing/duplicate event, end-to-end freshness, reconciliation | Dữ liệu nghiệp vụ có đầy đủ không |

MM2 cung cấp metrics qua Kafka Connect/JMX; tên metric và MBean phụ thuộc Kafka version. Kiểm tra metric catalog của bản triển khai thay vì giả định tên giống nhau ở mọi release.

Ví dụ metric do monitoring layer tự định nghĩa:

~~~text
mm2_replication_records_total{source,target,topic}
mm2_replication_bytes_total{source,target,topic}
mm2_replication_latency_seconds{source,target,topic}
mm2_checkpoint_age_seconds{source,target,group}
mm2_heartbeat_age_seconds{source,target}
mm2_connector_task_state{connector,task}
mm2_target_oldest_record_age_seconds{source,target,topic}
~~~

Không dùng event ID hoặc group ID tùy ý có cardinality rất lớn làm metric label. Group/topic có thể được giới hạn theo allowlist hoặc tier; chi tiết từng event nên nằm trong trace/log có kiểm soát.

### Alert gợi ý

- MirrorSource task FAILED hoặc connector không RUNNING.
- Replication latency/oldest target record age vượt RPO objective.
- Heartbeat quá hạn hoặc không có heartbeat mới.
- Checkpoint age vượt ngưỡng cho phép trước failover.
- Target under-replicated/offline partitions.
- Connect worker rebalance liên tục hoặc task restart lặp.
- Source/target event reconciliation phát hiện missing/duplicate.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không thấy target topic | Topic filter sai, connector chưa RUNNING hoặc ACL thiếu | Kiểm tra MirrorSource config/status, logs và source topic selection |
| Target topic có prefix lạ | DefaultReplicationPolicy thêm source alias | Xác minh replication policy và consumer subscription |
| Replication lag tăng | Source throughput cao, target broker chậm hoặc task thiếu capacity | Kiểm tra record/byte rate, task count, network và target ISR |
| Heartbeat không cập nhật | Connector lỗi, network hoặc ACL | Kiểm tra heartbeat task, source/target connectivity và internal topic ACL |
| Checkpoint không mới | Group discovery/filter sai, group chưa commit hoặc connector lỗi | Kiểm tra group filter, source offsets và checkpoint task |
| Consumer target đọc lại nhiều record | Offset translation/checkpoint cũ hoặc failover timing | Đối soát event ID, kiểm tra offset-sync/checkpoint và idempotency |
| Connect task FAILED | Converter, SMT, serialization, ACL hoặc network lỗi | Đọc task trace/log và kiểm tra plugin/config |
| Loop replication | Hai chiều không kiểm soát hoặc identity policy không phù hợp | Dừng flow lỗi, rà source alias/policy và topic filter |
| Target có topic nhưng thiếu config/schema | MM2 chỉ mirror Kafka records/topic data theo scope; metadata bên ngoài chưa được đồng bộ | Đồng bộ topic config, ACL, schema registry và dependency riêng |

Khi sửa connector, thay đổi một nhóm cấu hình mỗi lần, quan sát task restart và xác minh target trước khi mở rộng filter. Tránh xóa checkpoint/offset-sync topics để “reset” replication khi chưa có kế hoạch phục hồi offset.

## 16. Kế hoạch kiểm thử DR

Một DR test cần kiểm tra cả data plane, control plane và business application:

1. Tạo event có event ID tăng dần trên source.
2. Xác nhận target nhận event và đo replication lag.
3. Tạo consumer group, commit offset và chờ checkpoint được ghi.
4. Dừng source consumer theo runbook.
5. Fencing source producer hoặc mô phỏng source outage.
6. Dịch consumer offset sang target và khởi động consumer target.
7. Xác nhận duplicate/missing event theo event ID.
8. Đo thời gian từ lúc incident tới khi business flow hoạt động lại (RTO).
9. Đo record cuối cùng có ở target trước sự cố (RPO).
10. Kiểm thử failback theo hướng ngược lại và đối soát dữ liệu phát sinh tại DR.

Lặp lại thử nghiệm với network partition, Connect worker failure, target broker failure và checkpoint stale. Ghi lại kết quả thực tế, không chỉ kết quả kỳ vọng.

## 17. Production checklist

- [ ] Xác định active-passive hay active-active và cluster authoritative cho từng topic.
- [ ] Chọn Kafka Connect distributed mode và đủ worker capacity.
- [ ] Cấu hình Connect config/offset/status topics với replication và ACL phù hợp.
- [ ] Phân biệt Connect internal topics với MM2 checkpoint/heartbeat/offset-sync topics.
- [ ] Cấu hình MirrorSource, MirrorCheckpoint và MirrorHeartbeat đúng scope.
- [ ] Xác nhận topic/group filters, replication policy và loop prevention.
- [ ] Cấu hình source/target security riêng và quản lý secret an toàn.
- [ ] Cấp least-privilege ACL cho source, target và Connect internal topics.
- [ ] Theo dõi replication lag, heartbeat age và checkpoint age.
- [ ] Kiểm thử offset translation; không copy committed offset số học 1:1.
- [ ] Consumer có idempotency, deduplication và business reconciliation.
- [ ] Đồng bộ riêng topic config, ACL, schema registry và dependency ngoài Kafka.
- [ ] Có RPO/RTO đo được và runbook failover/failback.
- [ ] Có cơ chế fencing để tránh hai cluster cùng ghi ngoài ý muốn.
- [ ] Kiểm thử Connect worker/task failure, network partition và target outage.
- [ ] Bảo vệ Connect REST API và giám sát task state.
- [ ] Diễn tập DR định kỳ, ghi kết quả và cập nhật quy trình.

MirrorMaker 2 dùng Kafka Connect để sao chép topic giữa cluster và cung cấp heartbeat/checkpoint/offset-sync phục vụ quan sát, dịch chuyển consumer group. Connect worker có bộ config/offset/status topics riêng; chúng không thay thế internal topics của MM2. Muốn DR hoạt động tin cậy, cần quản lý topic replication, offset translation, security, RPO/RTO, fencing và idempotency như một quy trình end-to-end, rồi kiểm chứng bằng diễn tập failover/failback thực tế.
