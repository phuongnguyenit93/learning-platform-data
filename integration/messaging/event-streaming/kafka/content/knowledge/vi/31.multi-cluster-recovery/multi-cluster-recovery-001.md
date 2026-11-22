# Phân biệt replication trong cụm với sao chép giữa các cụm

Kafka có hai cơ chế replication với phạm vi và mục tiêu khác nhau:

- **Replication trong một cluster:** nhân bản partition từ leader sang follower broker trong cùng cluster để chịu lỗi broker.
- **Sao chép giữa các cluster:** chuyển record từ cluster nguồn sang cluster đích độc lập, thường phục vụ disaster recovery (DR), regional distribution, migration hoặc analytics.

Replication factor bằng 3 không có nghĩa dữ liệu đã được sao chép sang ba trung tâm dữ liệu độc lập. Có hai cluster cũng không tự động bảo đảm failover không mất dữ liệu hoặc consumer tiếp tục từ đúng vị trí. Cần hiểu replication protocol, offset mapping, replication lag, metadata và quy trình chuyển đổi ứng dụng.

## 1. Hai phạm vi replication

~~~mermaid
flowchart TB
    subgraph One["Một Kafka cluster"]
        P["Producer"] --> L["Partition leader"]
        L --> F1["Follower broker A"]
        L --> F2["Follower broker B"]
        C["Consumer"] --> L
    end
    subgraph Two["Hai Kafka cluster độc lập"]
        S["Source cluster"] -->|MirrorMaker 2| T["Target cluster"]
    end
~~~

Trong cùng cluster, broker phối hợp bằng Kafka replication protocol và metadata cluster. Producer gửi record tới leader; follower fetch log từ leader; ISR và high watermark xác định mức dữ liệu được coi là replicated/committed theo protocol.

Giữa hai cluster, replication thường là một ứng dụng hoặc connector đọc dữ liệu từ source rồi produce sang target. Hai cluster có metadata, controller quorum, broker ID space, consumer group state và vòng đời vận hành riêng. Cross-cluster replication thường bất đồng bộ nên target có thể chậm hơn source.

## 2. Replication trong cùng cluster hoạt động thế nào?

Một topic có nhiều partition. Mỗi partition có một leader và zero hoặc nhiều follower replica. Mọi produce request cho partition đi tới leader; follower fetch dữ liệu từ leader.

Ví dụ topic orders có replication factor bằng 3:

~~~text
orders-0:
  Leader   : broker-1
  Follower : broker-2
  Follower : broker-3
  ISR      : broker-1, broker-2, broker-3
~~~

Replication factor (RF) là số replica được cấu hình cho mỗi partition, bao gồm leader. RF=3 có nghĩa mỗi partition có một leader và hai follower, thường phân bố trên ba broker khác nhau.

### 2.1. Leader, follower và ISR

- **Leader:** nhận produce request và phục vụ client request cho partition.
- **Follower:** fetch dữ liệu từ leader để giữ bản sao log.
- **ISR (In-Sync Replicas):** tập replica đang theo kịp leader theo tiêu chí của Kafka.
- **High watermark (HW):** offset boundary mà Kafka dùng để xác định record đã replicated đủ điều kiện cho consumer đọc.
- **Leader epoch:** giúp nhận biết lịch sử leadership và xử lý log divergence khi leader thay đổi.

Follower không nhất thiết nhận record cùng lúc với leader. Có độ trễ replication nhỏ là bình thường. Nếu follower tụt quá xa hoặc mất kết nối, nó có thể bị loại khỏi ISR.

### 2.2. Producer acknowledgement và min.insync.replicas

Producer property acks quyết định mức acknowledgement:

| Giá trị | Ý nghĩa |
|---|---|
| acks=0 | Producer không đợi broker xác nhận |
| acks=1 | Leader xác nhận sau khi append vào local log |
| acks=all | Leader đợi điều kiện ISR acknowledgement theo replication protocol |

acks=all thường được kết hợp với broker/topic config min.insync.replicas.

~~~properties
acks=all
enable.idempotence=true
min.insync.replicas=2
replication.factor=3
~~~

Với RF=3 và min ISR=2, producer dùng acks=all chỉ ghi thành công khi số ISR đáp ứng tối thiểu. Nếu ISR tụt xuống 1, produce request có thể bị từ chối thay vì chấp nhận lần ghi với mức replica thấp hơn chính sách.

acks=all không đồng nghĩa từng record đã được fsync trên mọi disk. Kafka tận dụng page cache và flush nền; replication bảo vệ trước một số kiểu broker failure nhưng không thay thế backup.

### 2.3. Broker failure và leader election

Khi leader broker dừng hoạt động, controller chọn một replica phù hợp trong ISR làm leader mới. Client metadata được cập nhật và producer/consumer có thể retry hoặc refresh metadata.

Nếu partition có ISR còn khỏe, thời gian gián đoạn thường ngắn hơn và nguy cơ mất dữ liệu thấp hơn. Nếu ISR đã shrink, cluster có thể không có replica đủ điều kiện để tiếp tục phục vụ theo chính sách an toàn.

Cấu hình unclean leader election điều khiển việc có cho phép replica ngoài ISR trở thành leader khi không còn ISR khả dụng hay không. Cho phép unclean election có thể khôi phục availability nhưng có nguy cơ mất record đã được leader cũ xác nhận mà replica mới không có.

### 2.4. Rack awareness và failure domain

Để RF=3 có ý nghĩa chịu lỗi, replica cần được phân bố qua các broker và failure domain khác nhau. Nếu cả ba replica cùng nằm trên một host, một lỗi host có thể làm mất cả ba.

Dùng rack awareness để Kafka biết broker thuộc rack/AZ nào. Tuy nhiên, rack awareness trong một cluster không tự biến cluster thành multi-region DR. Nếu cả cluster dùng chung network, storage control plane hoặc region, một sự cố cấp region có thể ảnh hưởng tất cả replica.

## 3. Vì sao replication nội bộ không thay thế DR?

Replication trong cluster bảo vệ chủ yếu trước lỗi broker hoặc một số lỗi hạ tầng cục bộ. Các replica cùng chia sẻ metadata cluster và cùng phản ánh thao tác ghi/xóa của topic.

Một số sự cố mà intra-cluster replication không giải quyết được:

- Region hoặc toàn bộ datacenter mất khả năng phục vụ.
- Operator xóa nhầm topic hoặc chạy retention sai; thay đổi được phản ánh trên replica.
- Producer phát dữ liệu sai; follower vẫn sao chép record đó.
- Credential bị lộ và attacker ghi/xóa dữ liệu qua API hợp lệ.
- Cluster-wide metadata/configuration error.
- Storage/control plane hoặc network chung bị sự cố diện rộng.

Backup, immutable archive và cross-cluster replication giải quyết các failure mode khác nhau. Replication sang cluster thứ hai tạo bản sao độc lập hơn về hạ tầng, nhưng nếu thao tác xóa/sai dữ liệu được replicate ngay thì target cũng có thể nhận thay đổi đó. Vì vậy vẫn cần backup hoặc archive có retention/immutability phù hợp.

## 4. Sao chép giữa các cluster là gì?

Cross-cluster replication chuyển record từ một Kafka cluster sang một Kafka cluster khác. Cluster đích có broker, controller quorum, topic metadata và consumer group độc lập.

Các mục tiêu phổ biến:

| Mục tiêu | Mô tả |
|---|---|
| Disaster recovery | Duy trì cluster dự phòng ở region/datacenter khác |
| Regional data distribution | Cung cấp event gần ứng dụng ở nhiều khu vực |
| Migration | Chuyển workload từ cluster cũ sang cluster mới |
| Analytics | Sao chép dữ liệu sang cluster phục vụ phân tích |
| Consolidation/fan-out | Thu thập hoặc phân phối topic giữa nhiều môi trường |

Cross-cluster replication thường bất đồng bộ. Source có thể đã nhận record trong khi target vẫn đang replicate. Khoảng cách này là replication lag và quyết định RPO trong tình huống failover.

## 5. Apache Kafka MirrorMaker 2

MirrorMaker 2 (MM2) là bộ connector dựa trên Kafka Connect để replicate topic giữa các Kafka cluster. MM2 gồm ba connector chính:

- **MirrorSourceConnector:** đọc record từ source cluster và ghi vào remote topic ở target cluster; cũng có thể đồng bộ topic config tùy cấu hình/phiên bản.
- **MirrorCheckpointConnector:** phát checkpoint ánh xạ consumer group offset từ source sang target.
- **MirrorHeartbeatConnector:** phát heartbeat để theo dõi kết nối và trạng thái replication giữa các cluster.

~~~mermaid
flowchart LR
    subgraph S["Source cluster"]
        ST["orders / payments"]
        SO["Consumer group offsets"]
    end
    subgraph M["MirrorMaker 2 / Kafka Connect"]
        MS["MirrorSourceConnector"]
        MC["MirrorCheckpointConnector"]
        MH["MirrorHeartbeatConnector"]
    end
    subgraph T["Target cluster"]
        RT["primary.orders / primary.payments"]
        CP["Checkpoint topics"]
        HB["Heartbeat topic"]
    end
    ST --> MS --> RT
    SO --> MC --> CP
    MH --> HB
~~~

MM2 không tạo một bản sao byte-for-byte của toàn bộ Kafka cluster. Nó replicate record qua client protocol và tạo các topic/checkpoint cần thiết. Cần lập kế hoạch riêng cho schema, ACL, quota, Connect config, secrets, transactions và các hệ thống phụ thuộc.

### 5.1. Remote topic naming

Mặc định MM2 dùng replication policy có prefix cluster alias. Ví dụ source cluster alias là primary, topic nguồn orders có thể xuất hiện ở target dưới tên:

~~~text
primary.orders
~~~

Prefix giúp nhận biết topic đến từ cluster nào và hỗ trợ loop prevention khi cấu hình replication hai chiều. Nó cũng có nghĩa ứng dụng failover phải biết tên topic đích; không thể mặc định tên topic target giống source.

Có thể thay replication policy, nhưng dùng identity naming hoặc bỏ prefix cần hiểu rõ cách chống vòng lặp. Không thay replication policy tùy tiện trên cluster active-active.

### 5.2. Cấu hình MM2 minh họa

Ví dụ file cấu hình cho một chiều primary sang dr:

~~~properties
clusters=primary,dr

primary.bootstrap.servers=primary-1.example.net:9092,primary-2.example.net:9092
dr.bootstrap.servers=dr-1.example.net:9092,dr-2.example.net:9092

primary->dr.enabled=true
primary->dr.topics=orders, payments, inventory
primary->dr.groups=orders-processor, payments-processor

primary->dr.emit.heartbeats.enabled=true
primary->dr.emit.checkpoints.enabled=true
primary->dr.sync.group.offsets.enabled=true

replication.factor=3
tasks.max=4
~~~

Đây là ví dụ định hướng cấu hình. Cú pháp, defaults và khả năng đồng bộ config/ACL thay đổi theo Kafka release và MM2 deployment mode; đối chiếu tài liệu của đúng phiên bản. Topic/group filters có thể dùng regex, vì vậy kiểm tra pattern để không replicate nhầm hoặc bỏ sót topic.

MM2 có thể chạy bằng script MirrorMaker 2 trong Kafka distribution hoặc triển khai các connector trong Kafka Connect cluster. Với Connect distributed mode, phải quản lý worker config, internal topics, connector lifecycle và security riêng.

### 5.3. Các topic nội bộ của MM2

MM2 tạo một số topic để lưu trạng thái replication:

- Heartbeat topics dùng để quan sát đường đi và tình trạng cluster.
- Checkpoint topics lưu ánh xạ offset của consumer group.
- Offset-sync topics lưu thông tin cần thiết để dịch offset source sang offset target.
- Connect internal topics lưu connector config, offset và status nếu MM2 chạy trên Connect distributed worker.

Các topic này cần replication factor, retention, ACL và monitoring phù hợp. Không xóa chúng chỉ vì tên có vẻ là topic kỹ thuật; checkpoint/offset-sync mất đi có thể làm khó việc tiếp tục hoặc failover.

## 6. Offset ở hai cluster không giống nhau

Offset là vị trí trong một partition cụ thể của một cluster. Khi MM2 ghi record sang target, target có thể cấp offset khác source do:

- Record được replicate bất đồng bộ.
- Target đã có record hoặc topic được tạo trước.
- Filtering hoặc policy làm thay đổi tập record được replicate.
- Compaction/retention khác nhau.
- Replication được khởi động từ một offset nhất định thay vì từ đầu.

Ví dụ:

~~~text
Source orders-0:
  event A -> offset 100
  event B -> offset 101
  event C -> offset 102

Target primary.orders-0:
  event A -> offset 45
  event B -> offset 46
  event C -> offset 47
~~~

Không được lấy offset 102 từ source rồi seek consumer target tới offset 102. Offset đó không đại diện cùng một vị trí ở target.

### 6.1. Checkpoint và offset translation

MM2 dùng offset-sync và checkpoint để ánh xạ vị trí consumer group giữa source và target. Checkpoint cho biết một consumer group đã xử lý tới đâu trên source và offset tương ứng trên remote topic.

Offset translation là xấp xỉ theo các điểm đồng bộ đã quan sát, không phải phép biến đổi số học đơn giản. Khi failover, cần dùng checkpoint/translation của MM2 hoặc quy trình đã được kiểm thử để xác định vị trí bắt đầu ở target.

Không sao chép nguyên giá trị offset từ consumer offsets topic của source sang target. Consumer group state và membership là độc lập theo cluster.

### 6.2. Consumer group offset sync

MM2 có thể đồng bộ offset của consumer group sang target khi cấu hình cho phép. Việc cập nhật offset thường phụ thuộc trạng thái group ở target; group đang có consumer hoạt động có thể không được ghi đè để tránh phá consumer đang chạy.

Quy trình DR thường giữ consumer ở target inactive cho tới khi failover. Khi cần activate, xác minh checkpoint mới nhất, offset sync status và replication lag trước khi khởi động consumer.

Nếu không có checkpoint phù hợp, cần chọn rõ cách recovery: đọc từ earliest, latest, offset đã được dịch, hoặc replay theo business key/idempotency. Không dùng auto.offset.reset như một chiến lược DR ngầm định.

## 7. Replication lag và RPO

Replication lag là khoảng cách giữa dữ liệu đã commit ở source và dữ liệu đã có thể đọc ở target. Có thể đo theo:

- Thời gian trễ record từ source tới target.
- Offset lag theo partition.
- Số record/byte chưa replicate.
- Độ trễ heartbeat và checkpoint.
- Thời gian từ source produce đến target consume.

~~~mermaid
flowchart LR
    A["Source committed offset 500"] --> B["MM2 đang replicate"]
    B --> C["Target replicated offset 470"]
    C --> D["Lag khoảng 30 record"]
~~~

Ví dụ source có record đến offset 500 nhưng target mới có dữ liệu tương ứng đến offset 470. Nếu source mất đột ngột, các record mới hơn có thể chưa có ở target.

**RPO (Recovery Point Objective)** là lượng dữ liệu tối đa tổ chức chấp nhận mất khi phục hồi. Với replication bất đồng bộ, RPO phụ thuộc replication lag tại thời điểm sự cố. Không thể tuyên bố RPO=0 chỉ vì MM2 đang chạy.

**RTO (Recovery Time Objective)** là thời gian mục tiêu để dịch vụ hoạt động trở lại. RTO phụ thuộc phát hiện sự cố, xác định target đủ mới, chuyển bootstrap endpoint/config, activate consumer, xử lý duplicate và kiểm tra downstream.

Cần định nghĩa RPO/RTO theo workload và đo bằng DR drill, không chỉ dựa trên cấu hình connector.

## 8. Giữ topic và cấu hình source/target tương thích

MM2 có thể replicate record nhưng không tự đồng bộ toàn bộ metadata và hệ sinh thái ứng dụng.

| Thành phần | MM2 xử lý thế nào? | Việc cần chuẩn bị |
|---|---|---|
| Record/key/value/header | Replicate theo connector và policy | Kiểm tra serialization, ordering và filtering |
| Partition | Remote topic thường cần số partition tương ứng | Tạo/kiểm tra partition count và mapping |
| Topic config | Có thể sync một số config nếu bật và phiên bản hỗ trợ | Kiểm tra cleanup, retention, min ISR, max message size |
| Consumer group offsets | Checkpoint/offset sync có hỗ trợ | Kiểm thử offset translation và group inactive |
| ACL | Có tính năng sync tùy phiên bản/cấu hình | Review principal, authorizer và quyền target |
| Schema Registry | Không tự đồng bộ schema registry ngoài Kafka | Replicate/export schema và kiểm tra subject naming |
| Kafka Connect config | Không tự replicate connector deployment | Triển khai worker/connector config riêng |
| Quotas và user credentials | Không mặc định đồng bộ | Provision IAM/SASL/TLS/quotas tại target |
| Transactions | Không tái tạo một transaction xuyên cluster | Thiết kế idempotency và recovery semantics |
| KRaft metadata | Không replicate controller metadata log | Quản lý cluster như hệ thống độc lập |

Target cần có đủ topic, partition và capacity. Không phụ thuộc vào auto topic creation vì nó có thể tạo topic với partition count hoặc config không phù hợp.

### 8.1. Schema Registry và serialization

Nếu event dùng Avro, Protobuf hoặc JSON Schema, record trong Kafka có thể chứa schema ID. Replicate bytes sang target không đảm bảo schema ID ở target trỏ tới cùng schema.

Cần dùng schema replication/export/import hoặc chiến lược registry phù hợp, đồng thời kiểm tra subject naming strategy và compatibility policy. Nếu consumer target không resolve được schema ID, record đã replicate vẫn không deserialize được.

### 8.2. Security và identity

Certificate, SASL credentials, ACL principal và trust chain của source không tự tồn tại ở target. Cần chuẩn bị:

- TLS listener và truststore/keystore.
- SASL mechanism và credentials.
- Principal mapping.
- ACL cho MM2 worker và ứng dụng DR.
- Network/firewall giữa Connect worker và hai cluster.
- Secret management và rotation.

Không dùng credential source trên target một cách mặc định. Môi trường DR cần identity và quyền truy cập được quản lý riêng.

## 9. Ordering, duplicate và processing semantics

Trong một cluster, Kafka giữ thứ tự record theo partition. Cross-cluster replication có thể giữ thứ tự record trong từng source partition nếu topic/partition mapping phù hợp và connector xử lý đúng; không có total order giữa các partition.

Để giữ ordering khi failover:

- Duy trì partition count và mapping tương thích.
- Dùng cùng key/partitioning contract.
- Không chạy hai consumer active cùng xử lý cùng logical workload nếu không có coordination.
- Kiểm thử behavior khi replication reconnect và retry.

MM2 hoặc replication connector có thể retry sau lỗi mạng. Consumer cần idempotent vì failover/replay có thể tạo duplicate ở cấp xử lý nghiệp vụ. Dùng event ID, idempotency key, unique constraint hoặc deduplication store phù hợp.

Không giả định cross-cluster replication giữ nguyên semantics exactly-once của source transaction. Transaction boundary và producer sequence không phải một transaction xuyên hai cluster. Nếu ứng dụng cần atomic business effect, phải thiết kế outbox/inbox, idempotent sink hoặc transaction ở hệ thống đích.

## 10. Active-passive và active-active

### 10.1. Active-passive DR

Đây là mô hình đơn giản và thường dễ kiểm soát hơn:

- Source cluster nhận traffic production.
- Target cluster nhận bản sao và được theo dõi liên tục.
- Consumer ở target thường dừng hoặc không xử lý business output.
- Khi source gặp thảm họa, promote target theo runbook.

Ưu điểm là tránh hai cluster cùng xử lý một logical stream. Nhược điểm là target có thể bị lag và cần thời gian chuyển ứng dụng.

### 10.2. Active-active

Hai cluster cùng nhận traffic và có thể replicate topic qua lại. Mô hình này phù hợp khi ứng dụng cần phục vụ local ở nhiều region, nhưng phức tạp hơn nhiều.

Cần giải quyết:

- Conflict resolution khi hai region ghi cùng entity/key.
- Duplicate và loop prevention.
- Global ordering hoặc ordering theo entity.
- Idempotency và ownership theo region.
- Replication lag và partition mapping.
- Split-brain khi network partition làm hai bên nghĩ bên kia đã chết.

Default replication policy của MM2 dùng cluster alias prefix để nhận biết remote topic và hỗ trợ tránh replicate vòng lặp. Không thay bằng identity policy nếu chưa có thiết kế loop prevention rõ ràng.

Active-active cần quy tắc nghiệp vụ như single-writer per key, region ownership, version/vector metadata hoặc conflict resolution ở application layer. Kafka không tự giải quyết conflict của hai event cùng aggregate.

## 11. Migration giữa hai cluster

Cross-cluster replication cũng hữu ích khi chuyển cluster mà không muốn dừng hệ thống lâu.

Một quy trình migration có thể gồm:

1. Chuẩn bị target cluster, topic, partition, retention, ACL và schema.
2. Khởi động MM2 source-to-target và xác minh record/headers.
3. Chờ target bắt kịp, theo dõi lag theo partition.
4. Chọn một thời điểm cutover; kiểm soát producer writes để tránh hai cluster nhận cùng một luồng không phối hợp.
5. Chuyển producer bootstrap servers sang target.
6. Chuyển consumer sau khi offset translation/checkpoint được xác minh.
7. Kiểm tra business output, duplicate và lag.
8. Giữ source ở trạng thái read-only/standby trong khoảng rollback đã định.
9. Kết thúc replication sau khi xác nhận không còn dependency.

Không chỉ đổi bootstrap servers cho consumer. Consumer group ở target là group khác; phải xác định offset bắt đầu và commit state phù hợp.

## 12. Runbook failover sang DR cluster

Một failover an toàn cần người điều phối và tiêu chí rõ ràng. Ví dụ active-passive:

### Giai đoạn A: xác định source không còn phục vụ

- Xác minh sự cố thực sự ảnh hưởng source cluster.
- Kiểm tra controller/broker health, network và khả năng phục hồi source.
- Tránh quyết định failover chỉ dựa trên một alert ngắn hạn.
- Xác định có thể dừng producer/source writes hay không.

### Giai đoạn B: xác định target đủ mới

- Kiểm tra heartbeat và MM2 connector status.
- Kiểm tra replication lag theo topic/partition.
- Xác định checkpoint mới nhất của consumer group.
- So sánh target end offset với checkpoint/offset-sync.
- Ghi nhận RPO thực tế và khoảng record có thể mất.

### Giai đoạn C: promote target

- Ngăn source và target cùng xử lý một logical workload ngoài kế hoạch.
- Đảm bảo topic, schema, ACL, quotas và secrets trên target đã sẵn sàng.
- Cấu hình ứng dụng dùng target bootstrap servers và remote topic names.
- Dịch offset consumer group từ checkpoint hoặc áp dụng recovery policy đã duyệt.
- Khởi động consumer theo thứ tự phụ thuộc.
- Xác minh idempotency, duplicate, output và business invariant.

### Giai đoạn D: ổn định dịch vụ

- Theo dõi producer error/latency.
- Theo dõi consumer lag và processing throughput.
- Kiểm tra transaction, outbox/inbox và downstream database.
- Xác minh alert, dashboard và backup ở region DR.
- Ghi nhận thời điểm service phục hồi để đo RTO.

Không tuyên bố failover hoàn tất chỉ vì client kết nối được target. Cần xác nhận business processing đã tiếp tục đúng và không bỏ sót hoặc nhân đôi giao dịch ngoài chính sách.

## 13. Failback về cluster chính

Failback không đơn giản là đổi bootstrap server về source cũ. Trong thời gian DR hoạt động, target có thể đã nhận record mới mà source không có.

Quy trình cần:

1. Phục hồi source cluster như một cluster độc lập.
2. Xác định cluster nào là source of truth sau sự cố.
3. Thiết lập replication theo chiều target DR về source.
4. Kiểm tra loop prevention và remote topic naming.
5. Đồng bộ topic/config/schema/ACL cần thiết.
6. Chờ replication lag về mức chấp nhận được.
7. Chọn cutover window và kiểm soát producer writes.
8. Dịch consumer offsets hoặc khởi tạo group theo checkpoint.
9. Chuyển ứng dụng về source và kiểm tra business processing.
10. Giữ DR cluster làm standby hoặc đảo chiều replication theo thiết kế mới.

Không chạy replication hai chiều một cách ngẫu hứng để “hợp nhất” hai log. Nếu cả hai bên đã nhận write độc lập, cần xử lý conflict và duplicate ở cấp nghiệp vụ trước khi failback.

## 14. Monitoring cho multi-cluster replication

Giám sát cả connector và hai cluster:

| Nhóm | Tín hiệu | Ý nghĩa |
|---|---|---|
| Connector health | Task RUNNING/FAILED, restart count | Connector có hoạt động không |
| Replication lag | Record/byte lag, record age | Target đang chậm bao nhiêu |
| Throughput | Source read và target write rate | Có theo kịp ingress không |
| Heartbeat | Heartbeat topic và heartbeat latency | Đường replication có còn thông không |
| Checkpoint | Checkpoint latency và checkpoint age | Offset translation có đủ mới không |
| Source cluster | Under-replicated partitions, disk, request latency | Nguồn có khỏe không |
| Target cluster | Disk, ISR, topic size, produce errors | Đích có nhận và lưu được record không |
| Connect worker | CPU, heap, GC, network, task errors | Worker có là bottleneck không |
| Consumer | Lag, offset out of range, processing errors | Failover có thể tiếp tục ở vị trí đúng không |

Tên JMX metric và cách export phụ thuộc Kafka/MM2 version. Xây dashboard theo release đang triển khai và đặt alert theo RPO/RTO của từng workload, không chỉ alert task status.

Một connector có trạng thái RUNNING nhưng target vẫn lag liên tục có thể không đáp ứng RPO. Cần đo record age/lag và so sánh với ngưỡng nghiệp vụ.

## 15. Capacity và network cho cross-cluster replication

Target cần đủ capacity cho toàn bộ record được replicate và cho consumer DR sau failover.

Ước lượng sơ bộ:

~~~text
Target ingress cần thiết ≈
  source ingress sau compression
  + overhead/traffic của các topic được chọn
~~~

Cần tính thêm:

- Số topic và partition.
- Replication factor ở target.
- Retention ở target.
- Compression codec và kích thước record.
- Số cluster/region và network RTT.
- MM2 worker throughput, task count và CPU.
- Consumer egress khi DR được promote.
- Catch-up bandwidth sau khi target bị lag.

Nếu target chỉ được sizing cho replication bình thường mà không có headroom để phục vụ consumer production, failover có thể chuyển bottleneck từ source sang target.

Cross-region replication còn có chi phí network và latency. Đặt worker gần source hay target cần cân nhắc đường truyền hai chiều; benchmark theo traffic thực tế.

## 16. Bảo mật đường replication

MM2 là một Kafka client kết nối tới cả source và target. Nó cần quyền đọc topic nguồn, ghi topic đích và quản lý checkpoint/heartbeat topics. Cần bảo vệ cả hai đầu:

- TLS/SASL cho source và target.
- ACL tối thiểu cho source topics, target topics và MM2 internal topics.
- Secret riêng cho Connect worker.
- Network policy chỉ cho phép endpoint cần thiết.
- Audit connector config và REST API.
- Certificate/credential rotation không làm đứt replication.
- Mã hóa volume và backup cho worker/target nếu có dữ liệu nhạy cảm.

Không cấp quyền cluster-wide admin cho MM2 nếu chỉ cần replicate một tập topic và group. Nếu bật đồng bộ ACL/config, review chính xác resource nào được thay ở target.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Target không có topic mong muốn | Filter MM2 hoặc connector task lỗi | Kiểm tra topic pattern, connector status và permissions |
| Target topic có prefix | Default replication policy đặt cluster alias | Cập nhật bootstrap/topic mapping của ứng dụng DR |
| Consumer target đọc sai vị trí | Dùng offset source như offset target | Dùng checkpoint/offset translation |
| Replication lag tăng liên tục | Worker/network/target không đủ throughput | So sánh source read, target write, CPU, network và disk |
| Connector RUNNING nhưng target không tiến | Filter, ACL hoặc target produce errors | Kiểm tra task logs và target topic offsets |
| Checkpoint không cập nhật | Group không đủ điều kiện sync hoặc checkpoint connector lỗi | Kiểm tra group activity và checkpoint topic |
| Schema deserialize fail ở DR | Schema ID/subject không tồn tại ở registry đích | Đồng bộ schema và subject naming |
| ACL deny tại target | Principal/ACL source không tồn tại ở cluster đích | Provision identity và ACL riêng |
| Hai chiều tạo topic lặp hoặc vòng lặp | Replication policy/remote topic handling sai | Dùng policy loop-safe và test topology |
| Failover tạo duplicate | Replication retry/replay và consumer offset chưa chính xác | Idempotent processing, deduplication và checkpoint |
| Failback ghi đè dữ liệu | Hai cluster đã nhận write độc lập | Chọn source of truth và xử lý conflict trước cutover |
| DR cluster đầy disk | Target retention/RF/capacity không phù hợp | Capacity planning và retention policy riêng |

## 18. Bài lab: mô phỏng intra-cluster và cross-cluster replication

Dùng hai cluster test độc lập. Không mô phỏng failover bằng cách tắt broker production.

1. Tạo source cluster gồm ít nhất ba broker; tạo topic có RF=3.
2. Dừng một broker và quan sát leader election, ISR và produce behavior.
3. Khởi động lại broker, quan sát replica catch-up.
4. Tạo target cluster độc lập với cluster ID riêng.
5. Cấu hình MM2 replicate một topic test từ source sang target.
6. Produce event có key, header và timestamp; xác minh record ở remote topic.
7. Quan sát heartbeat, offset-sync và checkpoint topics.
8. Tạo consumer group ở source, commit offset rồi kiểm tra checkpoint ở target.
9. Tạm dừng replication trong môi trường test, produce thêm record và đo lag sau khi nối lại.
10. Dừng source theo kịch bản lab; dùng checkpoint để khởi động consumer ở target.
11. Kiểm tra duplicate, missing event, ordering theo partition và downstream state.
12. Thử failback bằng replication ngược trong một bài lab riêng và ghi lại cách xử lý remote topic/loop.

Bảng kết quả:

| Kịch bản | In-cluster ISR | Cross-cluster lag | Consumer offset | Kết quả |
|---|---|---|---|---|
| Dừng một broker | | | | |
| Follower catch-up | | | | |
| MM2 hoạt động bình thường | | | | |
| Mất network source-target | | | | |
| Replication catch-up | | | | |
| Failover consumer | | | | |
| Failback | | | | |

Đo thời gian phát hiện lỗi, thời gian target bắt kịp, RPO thực tế và RTO thực tế. Không chỉ ghi connector status.

## 19. Checklist thiết kế multi-cluster

- [ ] Đã phân biệt RF/ISR trong một cluster với replication sang cluster độc lập.
- [ ] Broker replicas được phân bố theo rack/AZ phù hợp.
- [ ] Producer acks và min.insync.replicas phù hợp durability target.
- [ ] Có cluster DR ở failure domain độc lập.
- [ ] Đã chọn active-passive hay active-active và ghi rõ source of truth.
- [ ] MM2 topic/group filters bao phủ đúng dữ liệu cần replicate.
- [ ] Remote topic naming và replication policy được xác định.
- [ ] Offset-sync/checkpoint/heartbeat topics được bảo vệ và giám sát.
- [ ] Có offset translation procedure cho consumer failover.
- [ ] Không copy nguyên source offset sang target.
- [ ] Partition count, key mapping và ordering được kiểm thử.
- [ ] Schema Registry, ACL, credentials, quotas và topic config được chuẩn bị riêng.
- [ ] Transaction và exactly-once boundary được đánh giá ở cấp ứng dụng.
- [ ] Có idempotency/deduplication cho replay và failover.
- [ ] Target đủ disk, network và CPU để nhận replication và phục vụ production traffic.
- [ ] RPO/RTO được đo bằng replication lag và DR drill.
- [ ] Có runbook failover, failback và chọn source of truth.
- [ ] Có backup/archive độc lập để bảo vệ trước thao tác xóa hoặc dữ liệu sai được replicate.
- [ ] Đã diễn tập mất broker, mất region, lag, failover và failback.

Replication trong một cluster giúp duy trì partition khi broker gặp lỗi thông qua leader, follower và ISR. Sao chép giữa các cluster tạo bản sao ở một hệ thống độc lập hơn và hỗ trợ DR, migration hoặc phân phối dữ liệu, thường qua MirrorMaker 2. Hai cơ chế không thay thế nhau: intra-cluster replication không bảo vệ trước sự cố cấp cluster/region hoặc thao tác xóa nhầm; cross-cluster replication bất đồng bộ nên có lag, offset target khác source và không tự đồng bộ toàn bộ metadata hay transaction semantics. Muốn DR đáng tin cậy, cần quản lý topic/schema/security, checkpoint và offset translation, đo RPO/RTO, thiết kế idempotency, và diễn tập failover/failback thường xuyên.
