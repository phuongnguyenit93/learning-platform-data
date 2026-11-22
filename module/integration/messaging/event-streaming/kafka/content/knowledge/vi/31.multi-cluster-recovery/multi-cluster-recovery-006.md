# Đồng bộ cấu hình, quyền truy cập và các giới hạn cần kiểm tra

Khi vận hành nhiều Kafka cluster, việc sao chép record mới chỉ là một phần của bài toán. Cluster đích còn cần topic có cấu hình phù hợp, principal có quyền truy cập, consumer group có offset đủ chính xác để tiếp tục xử lý và các ứng dụng phải biết cách chuyển sang bootstrap endpoint mới.

Apache Kafka MirrorMaker 2 (MM2) hỗ trợ sao chép dữ liệu, topic configuration, một phần ACL và checkpoint offset giữa các cluster. Tuy nhiên, MM2 không biến hai cluster thành một cluster duy nhất và không sao chép toàn bộ metadata, identity hoặc cấu hình broker. Các thao tác đồng bộ diễn ra bất đồng bộ, có bộ lọc và có giới hạn theo từng loại tài nguyên.

Bài này tập trung vào việc xác định chính xác thứ gì được đồng bộ, thứ gì phải quản lý riêng, cách cấu hình MM2 và các kiểm tra cần hoàn tất trước khi failover hoặc migration. Nội dung phù hợp với hệ thống KAFKA dùng topic, partition, offset, producer, consumer group, replication và KRaft, đặc biệt khi ứng dụng Java/Spring Kafka, Kafka Connect hoặc Kafka Streams cần chuyển giữa các cluster.

## 1. Phân biệt replication trong cluster và giữa các cluster

Kafka có hai lớp replication khác nhau:

| Loại | Phạm vi | Mục đích |
|---|---|---|
| Intra-cluster replication | Giữa các broker trong cùng cluster | Duy trì replica của partition, chịu lỗi broker và hỗ trợ ISR |
| Cross-cluster replication | Giữa hai hoặc nhiều Kafka cluster | Geo-replication, disaster recovery, migration, aggregation hoặc fan-out |

Replication factor của topic trong một cluster quyết định số bản sao partition trên các broker của cluster đó. MirrorMaker 2 đọc record từ cluster nguồn rồi produce record sang cluster đích. Nó không sao chép trực tiếp log segment hay replica protocol của cluster nguồn.

Vì hai cluster có broker, controller, metadata log, offset và chính sách riêng, không được giả định:
- Offset của một partition ở nguồn bằng offset của partition tương ứng ở đích.
- Replication factor của nguồn tự động trở thành replication factor của đích.
- ACL, user, quota và broker configuration được sao chép toàn bộ.
- Một lần ghi thành công ở nguồn đồng nghĩa record đã có ở đích.
- Failover có thể thực hiện mà không cần kiểm tra consumer group và ứng dụng.

### 1.1. Kiến trúc MirrorMaker 2

MirrorMaker 2 được xây dựng trên Kafka Connect và thường dùng ba connector:

- **MirrorSourceConnector:** đọc record từ source, ghi sang target; phát offset-sync records và có thể đồng bộ topic configs cùng topic ACL.
- **MirrorCheckpointConnector:** tạo checkpoint ánh xạ offset và hỗ trợ chuyển consumer group sang target.
- **MirrorHeartbeatConnector:** phát heartbeat để quan sát kết nối và độ trễ giữa các cluster.

~~~mermaid
flowchart LR
    subgraph SOURCE["Kafka cluster nguồn"]
        ST["Topic và partition"]
        SG["Consumer groups và offsets"]
        SA["Topic ACL và topic configs"]
    end
    subgraph MM2["MirrorMaker 2 / Kafka Connect"]
        MS["MirrorSourceConnector"]
        MC["MirrorCheckpointConnector"]
        MH["MirrorHeartbeatConnector"]
        OS["Offset-sync mapping"]
    end
    subgraph TARGET["Kafka cluster đích"]
        TT["Remote topics và partitions"]
        TG["Checkpoint / translated offsets"]
        TA["Topic ACL và topic configs"]
    end
    ST --> MS
    MS --> TT
    MS --> OS
    SG --> MC
    OS --> MC
    MC --> TG
    SA --> MS
    MS --> TA
    MH --> TARGET
    MH --> SOURCE
~~~

Các connector hoạt động theo từng replication flow có hướng, ví dụ primary sang secondary. Nếu cần hai chiều, phải khai báo cả hai flow. Một flow một chiều không tự động tạo flow ngược lại.

### 1.2. Các topology thường gặp

| Mô hình | Replication flow | Mục đích |
|---|---|---|
| Active/passive | A -> B | B làm cluster dự phòng, chỉ nhận dữ liệu |
| Active/active | A -> B và B -> A | Hai site cùng nhận dữ liệu, cần quy tắc tránh ghi xung đột |
| Aggregation | A -> C, B -> C | Gom dữ liệu từ nhiều cluster |
| Fan-out | A -> B, A -> C | Phân phối dữ liệu sang nhiều site |
| Forwarding | A -> B -> C | Chuyển tiếp qua nhiều vùng |

Trong mô hình active/passive, cần quy định rõ thời điểm chuyển producer và consumer sang B. Trong active/active, phải có quy tắc ownership của dữ liệu và cách xử lý xung đột. MM2 không hợp nhất hai event có cùng business key thành một state duy nhất.

## 2. Những gì MM2 đồng bộ và không đồng bộ

Bảng này là điểm bắt đầu cho mọi kế hoạch migration hoặc disaster recovery.

| Thành phần | MM2 hỗ trợ | Điều cần kiểm tra |
|---|---|---|
| Record của topic | Có | Filter topic, partition count, replication lag, remote topic name |
| Topic configuration | Có, theo property filter | Một số config bị loại mặc định; target policy có thể khác |
| Topic ACL | Có, nếu dùng cơ chế authorization tương thích | Chỉ topic ACL; principal và quyền khác phải được chuẩn bị |
| Consumer group checkpoint | Có | Checkpoint là offset mapping, không phải bản sao offset tuyệt đối |
| Ghi translated offset vào target group | Có thể bật riêng | Mặc định tắt; chỉ ghi khi group không có consumer active ở target |
| Heartbeat | Có | Dùng để đánh giá flow connectivity và liveness |
| Broker configuration | Không phải chức năng đồng bộ tổng quát của MM2 | Quản lý bằng IaC/config management riêng |
| KRaft metadata quorum và metadata log | Không | Mỗi cluster có quorum và metadata log độc lập |
| User, password, SCRAM credential, keytab hoặc OAuth client | Không | Provision identity riêng ở target |
| ACL cho mọi resource type | Không | Group, Cluster, TransactionalId và resource khác cần quản lý riêng |
| Quota và broker-level policy | Không phải đồng bộ tổng quát | Đồng bộ/kiểm tra bằng quy trình riêng |
| Schema Registry subjects và compatibility | Không thuộc MM2 core | Replicate/migrate bằng công cụ schema riêng |
| Kafka Connect connector config và offsets | Không phải toàn bộ Connect deployment | Provision worker, connector, secrets và offsets riêng |
| Kafka Streams local state | Không | Phục hồi từ changelog hoặc rebuild theo runbook ứng dụng |

MM2 làm việc qua Kafka APIs và connector, không copy metadata log của KRaft từ cluster này sang cluster kia. Với KRaft, mỗi cluster có controller quorum và metadata riêng. ACL được lưu trong metadata của từng cluster; MM2 chỉ dùng API để tạo các ACL mà tính năng sync hỗ trợ.

## 3. Đồng bộ topic và partition

### 3.1. Topic filter quyết định dữ liệu nào được sao chép

MM2 có thể dùng danh sách topic hoặc regular expression để chọn topic. Một flow thường có cấu hình:
- topics: topic hoặc regex được phép replicate.
- topics.exclude: pattern loại trừ; exclude có độ ưu tiên cao hơn include.
- refresh.topics.enabled: có định kỳ tìm topic và partition mới hay không.
- refresh.topics.interval.seconds: chu kỳ refresh.

Mặc định MM2 loại một số topic nội bộ, topic replica và topic bắt đầu bằng hai dấu gạch dưới. Không nên bỏ các filter mặc định nếu chưa hiểu tác động đến internal topics.

Hãy lập danh sách topic thuộc ứng dụng, topic nội bộ, topic test và topic có dữ liệu nhạy cảm. Không dùng pattern quá rộng chỉ vì muốn chắc chắn không bỏ sót dữ liệu.

### 3.2. Tên remote topic

Với DefaultReplicationPolicy, topic ở target thường được thêm alias của cluster nguồn vào tên. Ví dụ:

~~~text
Source cluster: primary
Source topic:   orders
Target cluster: secondary
Target topic:   primary.orders
~~~

Tên có prefix giúp phân biệt dữ liệu đến từ nguồn nào và hạn chế việc hai cluster ghi cùng tên topic-partition khi replication hai chiều.

Có thể thay separator hoặc dùng custom ReplicationPolicy nếu cần quy tắc tên riêng. Nếu thay policy, phải thống nhất policy trên tất cả MM2 process liên quan và kiểm thử loop prevention trước khi bật hai chiều.

### 3.3. Partition count và key mapping

MM2 bảo toàn partitioning của topic được replicate theo thiết kế replication flow. Topic đích cần có partition tương thích để dữ liệu được ánh xạ đúng.

Trước khi failover, kiểm tra:
- Số partition ở nguồn và remote topic.
- Key serializer/deserializer của client.
- Partitioner tùy chỉnh có cùng logic ở cả hai môi trường không.
- Consumer group có concurrency phù hợp với partition count đích không.
- Có ai đã tăng partition của remote topic thủ công hay không.

Tăng partition count ở target không phải cách giải quyết replication lag. Nếu source và target có partition topology không tương thích, cần sửa thiết kế và kiểm thử trước khi chuyển ứng dụng.

### 3.4. Replication factor là cấu hình riêng

Replication factor của topic mới tạo ở target được điều khiển bằng cấu hình MM2 riêng, thường là replication.factor. Trong Kafka 4.4, giá trị mặc định được tài liệu hóa cho remote topic mới là 2.

Không giả định topic đích tự nhận replication factor của nguồn. Hãy chọn target replication factor theo số broker, fault domains, availability và capacity của target cluster.

Ví dụ, target có ba broker ở ba availability zone có thể dùng replication factor 3 nếu storage/network capacity và policy phù hợp. Một cluster nhỏ hơn có thể cần giá trị khác. Cần bảo đảm target đủ broker trước khi tạo remote topic với replication factor lớn.

## 4. Đồng bộ topic configuration

MM2 có thể định kỳ cấu hình remote topic để khớp topic nguồn. Các cấu hình quan trọng:

| Property | Ý nghĩa | Mặc định Kafka 4.4 |
|---|---|---|
| sync.topic.configs.enabled | Bật đồng bộ topic config | true |
| sync.topic.configs.interval.seconds | Chu kỳ đồng bộ config | 600 giây |
| config.property.filter.class | Chọn topic config property được phép đồng bộ | DefaultConfigPropertyFilter |
| config.properties.exclude | Danh sách config bị loại khỏi sync | Có danh sách mặc định |
| replication.factor | Replication factor cho remote topic mới | 2 |

Đây là đồng bộ định kỳ, không phải transaction nguyên tử giữa hai cluster. Khi topic config thay đổi ở nguồn, target có thể chỉ nhận thay đổi ở lần sync tiếp theo. Một số thuộc tính còn bị loại theo filter.

### 4.1. Những config bị loại mặc định

Kafka 4.4 mặc định loại một số topic config khỏi quá trình đồng bộ, gồm:

- follower.replication.throttled.replicas
- leader.replication.throttled.replicas
- message.timestamp.difference.max.ms
- log.message.timestamp.before.max.ms
- log.message.timestamp.after.max.ms
- message.timestamp.type
- unclean.leader.election.enable
- min.insync.replicas

Danh sách chính xác phụ thuộc phiên bản Kafka và DefaultConfigPropertyFilter. Hãy kiểm tra tài liệu config của đúng phiên bản trước khi dựa vào một giá trị mặc định.

### 4.2. Vì sao min.insync.replicas cần quyết định riêng?

min.insync.replicas là một phần durability policy của topic. Giá trị phù hợp ở nguồn có thể không phù hợp ở target nếu:
- Target có ít broker hơn.
- Replication factor target khác.
- Target có topology hoặc failure domain khác.
- Target đang trong giai đoạn migration và chưa đủ capacity.
- Target cần chính sách ghi nghiêm ngặt hơn hoặc khác theo compliance.

Ví dụ, source dùng replication factor 3 và min.insync.replicas 2. Nếu target chỉ có hai broker nhưng giữ min.insync.replicas bằng 2, producer với acks=all có thể không ghi được khi một replica unavailable. Nếu tự giảm min.insync.replicas mà không đánh giá durability, target có thể chấp nhận ghi với mức bảo vệ thấp hơn.

Do đó, hãy thiết kế riêng:
- Replication factor của target.
- min.insync.replicas.
- Producer acks và delivery timeout.
- Unclean leader election policy.
- Storage headroom và rack/AZ placement.

Không ép target giống nguồn khi năng lực và fault domains khác nhau.

### 4.3. Topic config không phải broker config

MM2 topic config sync không sao chép toàn bộ broker properties như listener, advertised.listeners, log directories, thread counts, quotas, KRaft controller settings hoặc security configuration.

Các cấu hình cluster-level cần được quản lý bằng:
- Infrastructure as Code.
- Ansible, Terraform hoặc hệ thống config management.
- GitOps và review change.
- Quy trình đối chiếu cấu hình nguồn/đích.
- Checklist theo Kafka version và môi trường.

Tạo một inventory riêng cho broker defaults, dynamic broker configs, listener, quotas, log retention defaults, authorizer, TLS/SASL và KRaft. Sau khi dựng target, so sánh inventory với thiết kế target đã được phê duyệt.

### 4.4. Config drift và conflict

Nếu operator hoặc admin target thay đổi config trong khi MM2 đang đồng bộ, target có thể bị ghi đè theo nguồn ở lần sync tiếp theo. Ngược lại, nếu sync tắt, config nguồn có thể thay đổi mà target không nhận.

Cần chỉ định source of truth cho mỗi config:
- Topic config nào phải theo source.
- Topic config nào phải giữ policy riêng tại target.
- Broker config nào được quản lý qua IaC.
- Ai có quyền thay đổi topic config ở mỗi cluster.
- Cách phát hiện drift và cách xử lý khi có conflict.

Không để hai hệ thống automation cùng quản lý một config mà không có precedence rõ ràng.

## 5. Đồng bộ ACL và quyền truy cập

### 5.1. MM2 ACL sync làm gì?

MM2 có property sync.topic.acls.enabled để định kỳ cấu hình ACL của remote topic theo topic tương ứng ở nguồn. Trong Kafka 4.4:
- sync.topic.acls.enabled mặc định là true.
- sync.topic.acls.interval.seconds mặc định là 600 giây.

Tính năng này tập trung vào ACL gắn với topic. Nó không đồng nghĩa toàn bộ authorization model của hai cluster đã giống nhau.

Ví dụ, nếu producer ở nguồn có quyền Write trên topic orders, MM2 có thể sao chép topic ACL tương ứng cho remote topic primary.orders. Nhưng consumer ở target còn có thể cần quyền Read trên consumer group, và transactional producer có thể cần quyền trên TransactionalId. Các quyền này phải được thiết kế riêng.

### 5.2. Các giới hạn ACL quan trọng

Khi dùng simple ACL-based authorization, cần lưu ý:

- ACL topic có thể được sao chép sang remote topic tương ứng.
- ACL dạng ALLOW ALL cho topic không được sao chép theo hướng dẫn Strimzi.
- ACL topic được sao chép không đảm bảo đủ quyền cho mọi API operation.
- Consumer group, transactional ID và các resource type khác có thể cần ACL riêng.
- Nếu target dùng principal name khác nguồn, ACL copy có thể tham chiếu principal không tồn tại hoặc không đại diện đúng workload.
- Khi dùng OAuth 2.0 authorization, setting sync.topic.acls.enabled không có tác dụng theo hướng dẫn Strimzi.
- Khi dùng Strimzi User Operator, ACL sync của MM2 không tương thích; cần đặt sync.topic.acls.enabled=false và quản lý user/ACL theo cơ chế của operator.

### 5.3. Principal phải được chuẩn bị ở target

Giả sử source có principal User:orders-writer và User:orders-reader. Nếu target cũng dùng simple ACL với cùng principal names, việc ánh xạ ACL topic có thể thuận lợi hơn.

Nếu target dùng:
- IAM role khác.
- OAuth subject/client ID khác.
- Kerberos realm khác.
- Username hoặc principal mapping khác.
- User Operator quản lý ACL.

thì phải lập bảng ánh xạ identity và cấp quyền ở target bằng quy trình riêng. Không sao chép ACL mù quáng giữa hai identity domain.

### 5.4. KRaft và StandardAuthorizer

Trong KRaft, StandardAuthorizer lưu ACL trong metadata log của cluster. Hai cluster có metadata log và controller quorum độc lập. MM2 không sao chép nguyên metadata log của KRaft.

ACL sync là thao tác API-level để tạo ACL được hỗ trợ ở cluster đích. Vì vậy, sau khi đồng bộ vẫn cần kiểm tra principal, resource type, operation, host restriction và pattern type tại target.

### 5.5. Quy trình quản lý quyền khuyến nghị

1. Tạo service identity ở target.
2. Xác minh authentication bằng TLS/SASL/IAM/OAuth.
3. Cấp ACL tối thiểu cho remote topic.
4. Cấp quyền Read cho consumer group.
5. Cấp quyền transactional ID nếu producer dùng transaction.
6. Cấp quyền cho Connect/Streams internal topics nếu workload cần.
7. Kiểm thử producer, consumer, AdminClient và transactional flow.
8. Ghi nhận owner, principal mapping và thời hạn credential.
9. Kiểm tra quyền sau mỗi lần ACL sync.
10. Thu hồi quyền không còn sử dụng sau cutover.

## 6. Đồng bộ consumer group và offset

Offset là vị trí đọc của consumer group trong một partition. Offset của source và target không nhất thiết bằng nhau vì:
- Target có log riêng.
- Remote topic thường có tên khác.
- MM2 có thể bỏ qua một số topic.
- Replication là bất đồng bộ.
- Record có thể được ghi vào target ở offset khác với source.

Vì vậy, MM2 không thể chỉ copy số offset source sang target. Nó tạo mapping giữa source offset và target offset.

### 6.1. Offset-sync và checkpoint hoạt động ra sao?

MirrorSourceConnector phát offset-sync records để ánh xạ offset nguồn sang offset đích. MirrorCheckpointConnector đọc committed offsets của consumer group và tạo checkpoint đã dịch.

Checkpoint cho biết một consumer group đã xử lý đến vị trí nào ở source và vị trí tương ứng ở target. Khi failover, ứng dụng hoặc quy trình cutover có thể dùng checkpoint để tiếp tục gần với vị trí cũ.

Các property quan trọng:

| Property | Ý nghĩa | Mặc định Kafka 4.4 |
|---|---|---|
| emit.offset-syncs.enabled | Ghi mapping offset của record replicate | true |
| emit.checkpoints.enabled | Phát checkpoint consumer group | true |
| emit.checkpoints.interval.seconds | Chu kỳ checkpoint | 60 giây |
| sync.group.offsets.enabled | Ghi translated offset vào target group | false |
| sync.group.offsets.interval.seconds | Chu kỳ ghi offset vào target | 60 giây |
| offset.lag.max | Ngưỡng tạo offset-sync mapping | 100 |
| groups / groups.exclude | Lọc consumer group được theo dõi | Mặc định có group exclude |

### 6.2. Checkpoint không tự động có nghĩa target group đã commit offset

emit.checkpoints.enabled tạo checkpoint records. Việc ghi translated offsets trực tiếp vào __consumer_offsets của target được điều khiển riêng bằng sync.group.offsets.enabled.

Trong Kafka 4.4, sync.group.offsets.enabled mặc định là false. Khi bật, MM2 chỉ định kỳ ghi translated offset vào target khi không có consumer active của group đó kết nối với target cluster.

Điều kiện này giúp tránh ghi đè vị trí đọc của một group đang hoạt động tại target. Khi chuẩn bị cutover, phải:
1. Dừng consumer group ở target.
2. Xác nhận group không còn consumer active.
3. Cho MM2 hoàn tất checkpoint/offset sync.
4. Kiểm tra translated offsets ở target.
5. Chỉ sau đó mới khởi động consumer ở target.

### 6.3. offset.lag.max và khả năng phát lại record

offset.lag.max điều khiển khoảng cách tối đa giữa downstream offset và offset-sync mapping gần nhất trước khi MM2 tạo mapping mới. Giá trị mặc định Kafka 4.4 là 100.

Giá trị thấp:
- Mapping chính xác hơn.
- Checkpoint có thể gần vị trí consumer hơn.
- Tăng số record trong offset-sync topic và overhead replication.

Giá trị cao:
- Ít mapping hơn.
- Giảm storage/network overhead.
- Có thể làm consumer đọc lại nhiều record hơn sau failover.

Tài liệu Kafka đưa ra một ước lượng thô: số partition nhân với offset.lag.max có thể xấp xỉ số record bị xử lý lặp lại. Con số thực tế có thể thấp hơn hoặc cao hơn tùy timing và consumer lag.

Ví dụ, topic có 24 partition và offset.lag.max là 100. Có thể dùng 24 x 100 = 2.400 record làm ước lượng ban đầu cho lượng reprocessing, không phải cam kết hoặc giới hạn cứng.

### 6.4. Consumer group filter

MM2 hỗ trợ groups và groups.exclude để chọn group cần checkpoint. Mặc định thường loại các group như console-consumer-.*, connect-.* và group nội bộ bắt đầu bằng hai dấu gạch dưới.

Hãy khai báo rõ:
- Group production nào cần failover.
- Group nào chỉ dùng debug/test.
- Group của Kafka Connect có cần migration hay được tái tạo riêng.
- Group của Kafka Streams có state/changelog cần xử lý theo runbook riêng không.

Không mở filter tất cả group nếu target không cần những group đó. Checkpoint cho một group không thay thế việc kiểm tra application state hoặc side effect bên ngoài Kafka.

## 7. Cấu hình MirrorMaker 2 mẫu

Ví dụ dưới đây dùng dedicated MirrorMaker 2 config file để replicate từ primary sang secondary. Các tên property cần đối chiếu với Kafka version và deployment mode đang dùng.

~~~properties
# Cluster aliases and bootstrap endpoints
clusters=primary,secondary
primary.bootstrap.servers=primary-1:9092,primary-2:9092
secondary.bootstrap.servers=secondary-1:9092,secondary-2:9092

# One-way active/passive replication
primary->secondary.enabled=true
secondary->primary.enabled=false

# Replicate only application topics and consumer groups
primary->secondary.topics=orders,customers,inventory-events
primary->secondary.groups=orders-service,inventory-service

# Discover new topics and groups periodically
primary->secondary.refresh.topics.enabled=true
primary->secondary.refresh.topics.interval.seconds=600
primary->secondary.refresh.groups.enabled=true
primary->secondary.refresh.groups.interval.seconds=600

# Topic configs and ACLs
primary->secondary.sync.topic.configs.enabled=true
primary->secondary.sync.topic.configs.interval.seconds=600
primary->secondary.sync.topic.acls.enabled=false

# Target topic replication factor
primary->secondary.replication.factor=3

# Consumer offset checkpoints
primary->secondary.emit.offset-syncs.enabled=true
primary->secondary.emit.checkpoints.enabled=true
primary->secondary.emit.checkpoints.interval.seconds=60
primary->secondary.sync.group.offsets.enabled=false
primary->secondary.offset.lag.max=100

# Kafka Connect worker capacity
tasks.max=5
~~~

Trong ví dụ, ACL sync được tắt để target team quản lý principal mapping và quyền theo identity policy riêng. Nếu cả hai cluster dùng simple ACL, principal tương thích và không dùng Strimzi User Operator, có thể bật sync.topic.acls.enabled sau khi review phạm vi ACL.

### 7.1. Bảo vệ kết nối giữa MM2 và từng cluster

MM2 sử dụng Kafka consumer, producer và admin clients. Có thể cấu hình security riêng cho mỗi cluster alias. Ví dụ minh họa:

~~~properties
primary.security.protocol=SASL_SSL
primary.sasl.mechanism=SCRAM-SHA-512
primary.sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="mm2-reader" password="SOURCE_SECRET_FROM_SECRET_STORE";

secondary.security.protocol=SASL_SSL
secondary.sasl.mechanism=SCRAM-SHA-512
secondary.sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="mm2-writer" password="TARGET_SECRET_FROM_SECRET_STORE";
~~~

Chuỗi secret trong ví dụ là placeholder. Production phải lấy credential từ secret manager hoặc ConfigProvider, không commit password vào Git hay log.

MM2 cần quyền đọc topic và metadata ở source, đồng thời quyền tạo/ghi topic, đọc/ghi config và quản lý tài nguyên được bật ở target. Nếu bật ACL sync hoặc offset sync, principal MM2 còn cần quyền tương ứng trên ACL, checkpoint và internal topics.

Tạo principal riêng cho MM2 ở mỗi cluster. Không dùng credential admin của ứng dụng hoặc credential superuser cho connector nếu không cần thiết.

### 7.2. Khởi động MM2

~~~bash
bin/connect-mirror-maker.sh connect-mirror-maker.properties
~~~

MM2 có thể chạy nhiều process để phân tải connector tasks. Việc tăng process không tự động giải quyết network bottleneck hoặc thiếu partition capacity. Hãy benchmark throughput, task count, source consumer lag, target producer latency và network egress.

Tài liệu Kafka khuyến nghị đặt MM2 process gần target cluster để producer ghi dữ liệu qua mạng ổn định hơn. Nếu process ở xa target, producer lag và data transfer cost có thể tăng.

## 8. Những giới hạn cần kiểm tra trước khi cutover

### 8.1. Replication là bất đồng bộ

Record có thể đã được commit ở source nhưng chưa đến target. RPO thực tế phụ thuộc:
- Replication throughput.
- Network latency và packet loss.
- MM2 task availability.
- Source/target broker health.
- Topic partition count.
- Producer/consumer traffic burst.
- Target throttling và storage performance.

Không tuyên bố RPO bằng 0 chỉ vì MM2 connector đang RUNNING. Cần đo replication latency và lag ở thời điểm chuyển cụm.

### 8.2. Offset khác nhau và có thể xử lý lặp

Offset mapping không tạo một transaction xuyên hai cluster. Sau failover, consumer có thể đọc lại record đã xử lý ở source nhưng chưa có checkpoint chính xác ở target.

Ứng dụng cần idempotency:
- Event có business event ID ổn định.
- Database có unique constraint hoặc deduplication key.
- Consumer xử lý retry an toàn.
- Side effect bên ngoài có cơ chế chống ghi lặp.
- Có quy trình đối soát record sau failover.

Exactly-once trong một Kafka cluster không tự động trở thành exactly-once end-to-end qua hai cluster.

### 8.3. Exactly-once của MM2 có điều kiện

Kafka 4.4 hỗ trợ exactly-once semantics cho dedicated MirrorMaker cluster từ Kafka 3.5.0 với cấu hình và điều kiện bổ sung, gồm bật exactly-once source support, internal REST communication giữa MM2 nodes và cấu hình consumer source phù hợp.

Nếu cần loại bỏ record từ transaction bị abort, consumer đọc source cần isolation.level=read_committed. Hãy kiểm tra hướng dẫn nâng cấp/cấu hình cho dedicated MM2 mode.

Tính năng này không có nghĩa ứng dụng và database downstream được bao phủ bởi một transaction xuyên cluster. Vẫn phải thiết kế idempotency, offset handoff và side-effect recovery.

### 8.4. Config sync có filter và interval

Topic config sync có chu kỳ, filter và danh sách exclude. Những giá trị như min.insync.replicas có thể phải đặt theo target capacity. Đừng xem config sync là bản sao toàn bộ topic config không điều kiện.

### 8.5. ACL sync chỉ bao phủ một phần quyền

Topic ACL sync không tạo toàn bộ identity và authorization model. Phải kiểm tra group, transactional ID, cluster-level permissions, principal mapping và user provisioning.

Nếu target dùng OAuth 2.0 authorization hoặc Strimzi User Operator, kiểm tra giới hạn tương ứng và quản lý ACL bằng hệ thống đích.

### 8.6. Schema và application state nằm ngoài MM2 core

Nếu payload dùng Avro, Protobuf hoặc JSON Schema, target cần Schema Registry và subject compatibility phù hợp. Việc replicate topic record không tự tạo schema subject ở Registry đích.

Kafka Streams có state store và changelog/repartition topics. Cần quyết định:
- Replicate các topic cần thiết hay rebuild state ở target.
- Application ID và internal topic naming có tương thích không.
- State restore có hoàn tất trước khi nhận traffic không.
- Interactive Queries và external dependencies có được chuyển không.

Kafka Connect cũng cần connector config, secrets, offsets và plugin availability riêng. Không chỉ copy data topics rồi giả định Connect/Streams application đã sẵn sàng.

### 8.7. Active-active không tự giải quyết conflict

Nếu hai cluster cùng nhận write cho một logical stream, MM2 không giải quyết conflict theo business key. Cần:
- Quy định cluster/region nào sở hữu từng key hoặc partition.
- Dùng remote topic naming để phân biệt nguồn.
- Chống replication loop bằng cùng replication policy/config.
- Tránh hai producer cùng ghi một logical entity ở hai nơi nếu chưa có conflict strategy.
- Thiết kế event ID, timestamp, version và conflict resolution ở tầng ứng dụng.

## 9. Quy trình failover từ primary sang secondary

Một quy trình failover nên có health gate rõ ràng.

### 9.1. Trước incident

1. Xác định danh sách topic và group cần replicate.
2. Cấu hình source/target bootstrap, TLS/SASL và ACL cho MM2.
3. Kiểm tra remote topic được tạo đúng tên và partition count.
4. So sánh topic configs quan trọng với policy target.
5. Kiểm tra topic ACL và target principal mapping.
6. Theo dõi replication latency và checkpoint latency.
7. Kiểm thử producer/consumer ở target trong môi trường staging.
8. Diễn tập failover/failback và ghi lại RPO/RTO.

### 9.2. Khi quyết định failover

1. Xác định primary có còn nhận write hay không.
2. Nếu còn khả năng điều khiển, dừng hoặc fence producer ở primary để tránh split-brain.
3. Đánh giá replication lag và record cuối cùng đã đến target.
4. Kiểm tra remote topic, partition và target ISR.
5. Kiểm tra topic config quan trọng như retention, cleanup policy, replication factor và min.insync.replicas.
6. Kiểm tra ACL, identity, secret và network access ở target.
7. Dừng consumer target nếu đang chạy.
8. Chờ checkpoint/translated offset sync hoàn tất theo quy trình.
9. Kiểm tra group offsets và quyết định offset bắt đầu.
10. Cập nhật bootstrap endpoint/secret của producer và consumer.
11. Khởi động ứng dụng ở target theo từng nhóm.
12. Theo dõi duplicate processing, consumer lag, produce errors và business reconciliation.

Nếu primary đã mất hoàn toàn, có thể không kịp đồng bộ các record cuối cùng. Ghi nhận data-loss window và đối soát với nguồn nghiệp vụ nếu RPO không bằng 0.

### 9.3. Failback

Failback không đơn giản là bật lại flow ngược và đổi bootstrap server. Cần:
1. Xác định cluster nào đang là source of truth.
2. Kiểm tra dữ liệu mới chỉ được ghi ở target hay có ghi song song.
3. Đồng bộ dữ liệu và cấu hình cần thiết về cluster phục hồi.
4. Kiểm tra offset mapping theo chiều ngược.
5. Dừng consumer/producer theo trình tự.
6. Chuyển ownership và endpoint có kiểm soát.
7. Xác nhận không có hai cluster cùng ghi một logical stream ngoài thiết kế.
8. Diễn tập failback riêng trước khi xem đây là quy trình production-ready.

## 10. Monitoring đồng bộ đa cụm

MM2 có metric từ Kafka Connect và metric riêng trong nhóm kafka.connect.mirror. Nên theo dõi theo source, target, topic và partition.

| Metric | Ý nghĩa | Cách sử dụng |
|---|---|---|
| record-rate | Số record replicate mỗi giây | So với source ingress |
| record-count | Tổng record đã replicate | Kiểm tra tiến độ |
| byte-rate | Tốc độ byte replicate | So với network capacity |
| record-age-ms | Tuổi record tại thời điểm replicate | Quan sát dữ liệu trễ |
| replication-latency-ms | Độ trễ source-to-target | Theo dõi RPO gần đúng |
| checkpoint-latency-ms | Độ trễ replicate consumer offset checkpoint | Đánh giá offset readiness |
| source-record-poll-rate | Tốc độ poll record từ source | Kiểm tra connector source |
| Connector/task state | RUNNING, FAILED, PAUSED | Phát hiện task lỗi |

Ngoài metric MM2, cần theo dõi:
- Source/target broker availability.
- Under-replicated và offline partitions ở target.
- Target disk usage, ISR và produce latency.
- Consumer group lag và rebalance.
- Topic config drift.
- ACL authorization failures.
- Heartbeat topic và heartbeat age.
- Schema Registry availability.
- Connect worker REST, task restart và internal topics.
- Cross-region network throughput, packet loss và cost.

Một connector RUNNING không chứng minh dữ liệu đang replicate kịp. Hãy kiểm tra record-rate, replication-latency-ms và record-age-ms theo từng topic-partition.

## 11. Troubleshooting

### 11.1. Topic không xuất hiện ở target

Kiểm tra:
1. Flow source->target có được enable không?
2. Topic có khớp topics filter không?
3. Topic có bị topics.exclude loại không?
4. refresh.topics.enabled có bật không?
5. MM2 admin client có quyền Describe/Create không?
6. Connector task có lỗi khi tạo remote topic không?
7. Target có quota hoặc policy chặn tạo topic không?

### 11.2. Topic có dữ liệu nhưng config khác nguồn

Kiểm tra:
- sync.topic.configs.enabled.
- sync.topic.configs.interval.seconds.
- config.property.filter.class.
- config.properties.exclude.
- Target có policy riêng hay operator ghi đè không.
- Các config bị loại như min.insync.replicas có được quản lý bằng IaC không.

### 11.3. Consumer không được phép đọc target topic

Kiểm tra:
- Principal thực tế sau authentication.
- ACL của remote topic.
- ACL group tương ứng.
- Principal mapping và realm/issuer/client ID.
- Target authorizer và policy của operator.
- Nếu dùng OAuth 2.0 hoặc User Operator, ACL sync của MM2 có áp dụng không.

### 11.4. Consumer bắt đầu lại quá xa hoặc đọc trùng nhiều

Kiểm tra:
- Checkpoint connector có RUNNING không.
- emit.offset-syncs.enabled có bật không.
- emit.checkpoints.enabled có bật không.
- sync.group.offsets.enabled có được cấu hình đúng thời điểm không.
- Consumer target có còn active khi MM2 ghi translated offset không.
- offset.lag.max và checkpoint interval.
- Group có nằm trong groups/groups.exclude không.
- Topic partition và remote topic naming có khớp không.

### 11.5. Replication lag tăng

Kiểm tra:
- Source consumer throughput và lag.
- Target producer request latency/errors.
- MM2 task count và worker CPU/memory.
- Network bandwidth, latency và packet loss.
- Target broker disk/ISR/quotas.
- Message size, compression và burst traffic.
- Connector retry và task restart.

Không chỉ tăng tasks.max nếu bottleneck là network hoặc target broker. Scale MM2 phải đi kèm capacity của source, target và đường truyền.

### 11.6. ACL sync gây lỗi hoặc quyền không đúng

Kiểm tra:
- MM2 có quyền DescribeAcls/CreateAcls ở cluster tương ứng không.
- Source và target có dùng cùng authorization model không.
- Principal có tồn tại và mapping đúng ở target không.
- User Operator có quản lý ACL không.
- OAuth 2.0 authorization có được sử dụng không.
- Có ACL group/transactional ID cần tạo riêng không.
- ALLOW ALL có bị loại khỏi replication không.

## 12. Production checklist

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Replication flow | Hướng source/target có được định nghĩa rõ không? |
| Topic filter | Topic include/exclude có chính xác không? |
| Topic naming | Remote topic prefix và replication policy có nhất quán không? |
| Partition | Số partition và key mapping ở target có phù hợp không? |
| Replication factor | Target RF có đủ broker và fault domains không? |
| Topic configs | Sync enabled, interval và property filter đã được review chưa? |
| min.insync.replicas | Đã đặt theo durability/capacity của target chưa? |
| Broker config | Có IaC/config inventory để dựng target không? |
| ACL | Topic ACL sync có phù hợp authorization model không? |
| Principal | User, SCRAM, Kerberos, OAuth/IAM và mapping đã sẵn sàng chưa? |
| Group ACL | Quyền consumer group đã được cấp riêng chưa? |
| Transactional ACL | Producer transaction có quyền trên target không? |
| Offset mapping | Offset-sync và checkpoint connector đang hoạt động không? |
| Group offset write | Target group có consumer active khi sync không? |
| Schema | Schema Registry/subjects/compatibility đã được đồng bộ chưa? |
| Connect/Streams | Connector config, secrets, offsets và state recovery đã có kế hoạch chưa? |
| Security | MM2 dùng credential riêng và TLS/SASL cho cả hai cluster chưa? |
| Monitoring | Replication latency, record age và checkpoint latency có alert không? |
| RPO/RTO | Đã đo bằng diễn tập failover chưa? |
| Failback | Có quy trình reverse replication và chống split-brain không? |
| Reconciliation | Có kiểm tra record count, business key và duplicate sau cutover không? |

## 13. Anti-pattern thường gặp

- **Cho rằng MM2 sao chép toàn bộ cluster:** MM2 đồng bộ một số loại resource qua API, không sao chép KRaft metadata log hoặc mọi broker config.
- **Cho rằng topic config sync là đầy đủ:** property filter và exclude list có thể bỏ qua config quan trọng.
- **Giữ nguyên min.insync.replicas mà không xét target:** producer có thể không ghi được hoặc durability giảm ngoài dự kiến.
- **Bật ACL sync mà không kiểm tra identity:** ACL có thể trỏ tới principal không tồn tại ở target.
- **Chỉ đồng bộ topic ACL:** consumer group và transactional ID vẫn có thể thiếu quyền.
- **Coi checkpoint là offset tuyệt đối:** source và target offset khác nhau; checkpoint là mapping và có thể có sai số.
- **Bật sync.group.offsets khi target đang có consumer:** có thể xung đột với offset của group đang chạy.
- **Bỏ qua topic/group filter:** replicate nhầm internal topic hoặc bỏ sót group production.
- **Chạy active-active không có ownership:** hai nơi cùng ghi một logical stream có thể tạo conflict.
- **Đặt MM2 xa target:** tăng producer latency và chi phí cross-region.
- **Không kiểm tra Schema Registry và Connect:** record đã tới target nhưng application vẫn không chạy được.
- **Không diễn tập failback:** hệ thống chỉ có thể chuyển đi mà không có đường quay lại an toàn.

## 14. Quy trình thiết kế đồng bộ trước khi triển khai

1. Liệt kê cluster, alias, region và replication flow.
2. Chọn topic/group cần replicate; ghi rõ internal topics cần loại.
3. Chốt naming policy và ownership của dữ liệu.
4. So sánh partition count, replication factor và target capacity.
5. Lập bảng topic config: sync, exclude hay target-specific.
6. Chọn ACL strategy: MM2 topic ACL sync hay quản lý riêng.
7. Ánh xạ principal, user, credential và resource ACL ở target.
8. Bật offset-sync/checkpoint và chọn offset.lag.max theo RPO/reprocessing budget.
9. Đồng bộ schema, Connect config, Streams state và secret ngoài MM2.
10. Bật TLS/SASL và cấp quyền tối thiểu cho MM2.
11. Chạy POC, đo replication latency và kiểm tra config/ACL/offset.
12. Diễn tập failover/failback, ghi RPO/RTO và cập nhật runbook.
13. Theo dõi drift và review định kỳ sau mỗi thay đổi policy.

## 15. Kết luận

MirrorMaker 2 giúp Kafka replicate record, topic configuration, topic ACL và consumer group checkpoint giữa các cluster. Nhưng mỗi loại đồng bộ có phạm vi, filter và chu kỳ riêng. Topic config sync không sao chép mọi broker config; ACL sync chủ yếu áp dụng cho topic ACL và phụ thuộc authorization model; checkpoint là mapping offset chứ không phải bản sao số offset nguyên trạng.

Để chuyển cluster an toàn, hãy thiết kế riêng target replication factor và durability policy, quản lý principal/ACL theo identity domain đích, kiểm tra schema và Connect/Streams state, đồng thời đo replication latency và checkpoint latency. Consumer phải được dừng đúng lúc khi translated offsets được ghi vào target, và ứng dụng cần idempotency để xử lý record có thể được phát lại.

Không đánh giá DR chỉ bằng trạng thái connector. Hãy diễn tập failover và failback với producer, consumer group, ACL, schema, Connect, Streams và dữ liệu nghiệp vụ. Chỉ khi toàn bộ quy trình đã được đo và kiểm chứng, cluster đích mới sẵn sàng thay thế cluster nguồn.

## Tài liệu tham khảo

- Apache Kafka 4.4 — Geo-Replication (Cross-Cluster Data Mirroring): https://kafka.apache.org/44/operations/geo-replication-cross-cluster-data-mirroring/
- Apache Kafka 4.4 — MirrorMaker Configs: https://kafka.apache.org/44/configuration/mirrormaker-configs/
- Apache Kafka 4.4 — Authorization and ACLs: https://kafka.apache.org/44/security/authorization-and-acls/
- Apache Kafka 4.4 — Security Model: https://kafka.apache.org/44/security/security-model/
- Strimzi 0.50.1 — Deploying and Managing, Synchronizing ACL rules: https://strimzi.io/docs/operators/0.50.1/full/deploying.html
