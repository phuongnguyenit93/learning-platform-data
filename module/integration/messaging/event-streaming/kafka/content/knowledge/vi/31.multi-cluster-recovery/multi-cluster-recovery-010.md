# Failover, failback và diễn tập khôi phục Kafka đa cụm

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này hướng dẫn thiết kế khôi phục thảm họa giữa nhiều Kafka cluster, vận hành failover khi cluster chính gặp sự cố, failback khi site chính phục hồi và diễn tập để chứng minh RPO/RTO có thể đạt được.

Một Kafka cluster có replication factor cao vẫn có thể mất khả năng phục vụ khi cả region, network zone hoặc control plane gặp sự cố. Replication giữa các broker trong cùng cluster bảo vệ trước một số lỗi broker; nó không thay thế disaster recovery giữa các cluster độc lập. Với kiến trúc đa cụm, dữ liệu thường được sao chép bất đồng bộ, vì vậy cluster DR có thể chậm hơn cluster nguồn. Kế hoạch failover phải biết độ trễ sao chép, mức mất dữ liệu có thể chấp nhận, cách chuyển consumer offset và cách ngăn cluster cũ tiếp tục nhận ghi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt broker replication trong một cluster với replication giữa nhiều cluster.
- Chọn mô hình active-passive, active-active hoặc multi-region theo yêu cầu nghiệp vụ.
- Định nghĩa RPO, RTO, failure domain và điều kiện kích hoạt failover.
- Giải thích MirrorMaker 2 (MM2), MirrorSourceConnector, MirrorCheckpointConnector và MirrorHeartbeatConnector.
- Cấu hình một luồng replication một chiều giữa primary và DR.
- Theo dõi heartbeat, checkpoint, replication lag và trạng thái Kafka Connect.
- Hiểu remote topic naming và consumer offset translation.
- Chuẩn bị topic, ACL, secret, schema, Connect và ứng dụng tại DR.
- Thực hiện failover có fencing để tránh split-brain.
- Chuyển producer, consumer group và downstream service sang DR.
- Thực hiện failback bằng một kế hoạch đồng bộ ngược có kiểm soát.
- Xử lý duplicate, replay, ordering và transaction boundary khi chuyển cluster.
- Diễn tập site failure, network partition, lag vượt RPO và khôi phục dịch vụ.
- Đo kết quả thực tế và cập nhật runbook sau mỗi lần diễn tập.

## 2. Vì sao cần nhiều Kafka cluster?

Replication factor và ISR bảo vệ dữ liệu trong phạm vi một Kafka cluster. Nếu broker hỏng, follower replica có thể được bầu làm leader khi thỏa điều kiện. Nhưng khi toàn bộ cluster hoặc site không thể truy cập, tất cả replica trong cluster có thể cùng mất khả năng phục vụ.

Một cluster DR ở region hoặc fault domain độc lập giúp tổ chức tiếp tục xử lý sự kiện khi primary bị gián đoạn. Để làm được điều đó, DR cần có dữ liệu đủ mới, topic và security policy tương thích, ứng dụng có thể kết nối và quy trình chuyển quyền ghi rõ ràng.

### 2.1. Các failure domain

| Failure domain | Ví dụ | Biện pháp |
|---|---|---|
| Process | Kafka broker crash | Broker restart, replica leader election |
| Host | Server hoặc disk hỏng | Replica trên broker khác |
| Rack/AZ | Mất switch hoặc availability zone | Rack-aware replica placement |
| Region/site | Mất điện, mạng hoặc cloud region | Cluster DR ở region độc lập |
| Network | Primary và DR không liên lạc được | Replication monitoring, fencing và quyết định failover |
| Identity/control plane | IAM, DNS, certificate hoặc controller dependency lỗi | DR identity, secret và management path độc lập |
| Operator error | Xóa topic, config sai, credential bị thu hồi | Backup metadata/config, audit và recovery procedure |

Multi-cluster DR chủ yếu xử lý lỗi ở mức cluster/site và một số lỗi vận hành. Nó không tự bảo vệ khỏi việc ứng dụng hợp lệ ghi dữ liệu sai rồi dữ liệu sai được replicate sang DR. Với lỗi logic hoặc xóa nhầm, cần thêm backup, retention, immutable archive hoặc quy trình phục hồi dữ liệu riêng.

## 3. Định nghĩa RPO và RTO

RPO và RTO là hai mục tiêu khác nhau:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa mà nghiệp vụ chấp nhận mất, thường biểu diễn bằng thời gian dữ liệu.
- **RTO (Recovery Time Objective):** khoảng thời gian tối đa từ lúc dịch vụ bị gián đoạn đến khi dịch vụ được khôi phục ở mức đã định.

Ví dụ:

- RPO mục tiêu: tối đa 60 giây dữ liệu.
- RTO mục tiêu: khôi phục khả năng nhận và xử lý event trong 15 phút.

Đây là mục tiêu của hệ thống, không phải cam kết mặc định của Kafka hoặc MirrorMaker 2.

### 3.1. RPO phụ thuộc replication lag

MM2 sao chép record bất đồng bộ. Khi primary ghi record và trả acknowledgement cho producer, record đó chưa chắc đã đến DR.

Vì vậy:

- acks=all xác nhận theo ISR của cluster nguồn.
- Producer idempotence bảo vệ retry producer trong phạm vi producer session/cluster semantics tương ứng.
- Transactional producer cung cấp transaction trong cluster mà producer kết nối.
- Không cơ chế nào trong các cơ chế trên tự biến MM2 thành synchronous cross-cluster replication.

Nếu replication lag là 20 giây khi primary mất, dữ liệu cuối cùng có thể chưa xuất hiện ở DR. Mức mất dữ liệu thực tế còn phụ thuộc thời điểm lỗi, tốc độ replicate, record đang in-flight và cách xác định cutover point.

### 3.2. RTO bao gồm nhiều bước

RTO không chỉ là thời gian khởi động broker. Nó có thể gồm:

1. Phát hiện và xác nhận sự cố.
2. Quyết định kích hoạt DR.
3. Fence primary hoặc xác minh primary đã bị cô lập.
4. Kiểm tra DR cluster và replication state.
5. Chuẩn bị topic, ACL, schema và application config.
6. Chuyển producer/consumer endpoint.
7. Khôi phục hoặc dịch chuyển consumer offsets.
8. Xác minh dữ liệu và downstream side effects.
9. Mở traffic và theo dõi SLO.

Cần đo thời gian từng bước trong diễn tập để biết phần nào chiếm RTO lớn nhất.

### 3.3. Ma trận mục tiêu ví dụ

| Workload | RPO mục tiêu | RTO mục tiêu | Kiểu phục hồi |
|---|---:|---:|---|
| Event thanh toán | 30 giây | 10 phút | DR ưu tiên, xác minh dữ liệu chặt |
| Order event | 60 giây | 15 phút | Active-passive |
| Audit event | 5 phút | 60 phút | DR và archive bổ sung |
| Telemetry | 15 phút | 2 giờ | Có thể chấp nhận mất một phần dữ liệu |

Giá trị phải do nghiệp vụ và chủ hệ thống thống nhất. Không dùng một RPO/RTO chung cho mọi topic nếu hậu quả mất dữ liệu khác nhau.

## 4. Chọn topology đa cụm

### 4.1. Active-passive

Primary nhận ghi và phục vụ consumer chính. DR nhận bản sao dữ liệu nhưng bình thường không phục vụ cùng luồng nghiệp vụ ghi chính.

Ưu điểm:

- Dễ xác định cluster authoritative.
- Giảm xung đột khi ghi.
- Failover/failback dễ mô hình hóa hơn.
- Phù hợp nhiều hệ thống cần một nguồn sự thật cho mỗi domain.

Đổi lại, DR có thể ít được sử dụng và cần diễn tập để bảo đảm endpoint, capacity, credential và ứng dụng luôn sẵn sàng.

~~~mermaid
flowchart LR
    APP[Producer and consumers] --> P[(Primary Kafka)]
    P -->|Async replication| MM2[MirrorMaker 2]
    MM2 --> D[(DR Kafka)]
    D -. Standby .-> DRAPP[Standby applications]
~~~

### 4.2. Active-active

Hai cluster cùng nhận ghi cho các luồng hoặc vùng dữ liệu khác nhau. Ứng dụng có thể phục vụ gần người dùng hơn hoặc tiếp tục hoạt động độc lập ở mỗi region.

Ưu điểm:

- Tận dụng cả hai region.
- Giảm độ trễ cho workload địa phương.
- Có thể tăng availability nếu domain ownership được phân chia tốt.

Rủi ro:

- Hai cluster có thể nhận event cho cùng một entity.
- Không có global ordering giữa hai cluster.
- Duplicate hoặc conflict cần xử lý ở tầng nghiệp vụ.
- Replication loop và remote topic naming phải được thiết kế rõ.
- Failover có thể là thay đổi ownership của domain thay vì chỉ đổi bootstrap server.

Nếu cần active-active, hãy phân vùng ownership theo tenant, entity hoặc region. Tránh để hai cluster độc lập cùng ghi tùy ý vào một luồng có yêu cầu ordering toàn cục.

### 4.3. Hub-and-spoke hoặc nhiều DR region

Một cluster trung tâm có thể replicate sang nhiều DR region hoặc nhiều site có mục tiêu phục hồi khác nhau. Mô hình này tăng khả năng phục hồi nhưng cũng tăng replication traffic, chi phí Connect và độ phức tạp kiểm soát vòng lặp.

Mỗi replication edge cần có owner, hướng dữ liệu, topic allowlist, group policy, lag alert và runbook.

## 5. Các thành phần MirrorMaker 2

MirrorMaker 2 là bộ công cụ replication Kafka dựa trên Kafka Connect. Nó gồm các connector phối hợp với nhau:

| Thành phần | Vai trò |
|---|---|
| MirrorSourceConnector | Đọc topic ở cluster nguồn và ghi bản sao sang cluster đích |
| MirrorCheckpointConnector | Phát checkpoint ánh xạ offset consumer group giữa source và target |
| MirrorHeartbeatConnector | Phát heartbeat để quan sát kết nối và độ trễ giữa các cluster |
| MirrorMaker process | Điều phối các connector và cấu hình replication |

MM2 thường chạy trong Kafka Connect worker. Worker cần truy cập cả source và target, có identity riêng và có capacity đủ cho source fetch, target produce, checkpoint và heartbeat.

### 5.1. Luồng source connector

MirrorSourceConnector đọc record từ source topic rồi publish sang remote topic ở target. Theo mặc định phổ biến, remote topic được đặt tên theo dạng sourceAlias.topicName, ví dụ primary.orders.

Điều này giúp phân biệt dữ liệu local và dữ liệu mirror. Consumer chuyển sang DR phải biết tên remote topic hoặc dùng replication policy đã được thiết kế trước.

### 5.2. Luồng checkpoint connector

MirrorCheckpointConnector định kỳ phát checkpoint cho consumer group. Checkpoint mô tả mối quan hệ giữa offset nguồn và offset tương ứng trên topic mirror.

Offset ở hai cluster không nhất thiết bằng nhau vì có thể có filtering, replication lag, record bị loại hoặc khác biệt trong lịch sử topic. Không copy nguyên con số offset source sang target một cách thủ công rồi giả định consumer sẽ tiếp tục đúng vị trí.

### 5.3. Luồng heartbeat connector

MirrorHeartbeatConnector tạo heartbeat topic để xác nhận replication path vẫn hoạt động và cung cấp dữ liệu cho việc đo độ trễ. Heartbeat bị stale có thể chỉ ra Connect worker dừng, network bị gián đoạn, authentication lỗi hoặc target không nhận được record.

Heartbeat thành công không chứng minh mọi topic nghiệp vụ đều đang replicate đúng. Cần theo dõi cả source connector task, target topic, record lag và checkpoint.

## 6. Cấu hình MirrorMaker 2 một chiều

Ví dụ cấu hình minh họa cho luồng primary sang dr:

~~~properties
clusters = primary, dr

primary.bootstrap.servers = primary-1.internal:9092,primary-2.internal:9092
dr.bootstrap.servers = dr-1.internal:9092,dr-2.internal:9092

primary->dr.enabled = true
primary->dr.topics = orders|payments|inventory
primary->dr.groups = orders-.*|payments-.*

replication.factor = 3
checkpoints.topic.replication.factor = 3
heartbeats.topic.replication.factor = 3
offset-syncs.topic.replication.factor = 3

primary->dr.emit.heartbeats.enabled = true
primary->dr.emit.checkpoints.enabled = true
primary->dr.sync.group.offsets.enabled = true
primary->dr.sync.group.offsets.interval.seconds = 60
~~~

Đây là cấu hình minh họa; tên thuộc tính, defaults và hỗ trợ offset sync cần được xác nhận theo phiên bản Kafka/MM2 đang triển khai. Cấu hình security, converter, producer/consumer properties và Connect internal topics phải được bổ sung theo môi trường.

### 6.1. Topic và group allowlist

Không replicate mọi topic theo mặc định nếu cluster chứa internal topic, dữ liệu test hoặc topic không cần DR.

Đặt regex rõ ràng cho:
- Topic nghiệp vụ cần bảo vệ.
- Consumer group cần chuyển khi failover.
- Topic nội bộ của MM2 và Connect.
- Topic có data classification hoặc retention riêng.

Không replicate topic nội bộ như __consumer_offsets bằng cách coi nó là topic nghiệp vụ. MM2 dùng checkpoint mechanism để xử lý offset group; không nên sao chép nội dung internal offsets topic theo cách thủ công.

### 6.2. Replication factor ở target

Target topic cần RF phù hợp với số broker, rack và durability requirement của DR. Không đặt RF=3 nếu target chỉ có hai broker. Kiểm tra min.insync.replicas, rack awareness, retention và disk headroom ở DR.

### 6.3. Security cho MM2

MM2 phải xác thực và được phân quyền trên cả hai cluster:

- Source: quyền đọc topic và group metadata cần thiết.
- Target: quyền tạo/ghi remote topic và topic nội bộ của MM2.
- Connect worker: quyền quản lý connector và internal config/offset/status topics.
- Network: cho phép kết nối từ worker đến broker listener đúng.
- TLS/SASL: certificate, truststore, mechanism và secret được bảo vệ.

Không dùng super user cho mọi connector nếu có thể cấp quyền tối thiểu. Credential của MM2 là một phần quan trọng của DR plan và phải được kiểm thử riêng.

### 6.4. Chạy MM2

Có thể chạy MirrorMaker 2 qua script của Kafka distribution:

~~~bash
connect-mirror-maker.sh mm2.properties
~~~

Trong production, thường triển khai Connect worker cluster theo mô hình phù hợp availability. Bảo vệ Connect REST API, internal topics, worker config và plugin path. Một worker process đơn lẻ có thể trở thành điểm lỗi của replication pipeline.

## 7. Remote topic naming và vòng lặp replication

Remote topic naming giúp xác định cluster nguồn của dữ liệu. Ví dụ:

~~~text
Source cluster: primary
Source topic: orders
Target cluster: dr
Remote topic: primary.orders
~~~

Khi failover, ứng dụng ở DR có thể đọc primary.orders. Nếu muốn giữ tên topic orders, cần thiết kế replication policy và cutover rõ ràng; không đổi policy tùy tiện trong lúc sự cố.

### 7.1. DefaultReplicationPolicy

Policy mặc định thường thêm source alias vào tên remote topic. Cách này giúp phân biệt local topic và remote topic, đồng thời hỗ trợ nhận diện đường replication.

### 7.2. IdentityReplicationPolicy

IdentityReplicationPolicy giữ nguyên tên topic. Nó có thể hữu ích khi ứng dụng yêu cầu tên topic không đổi, nhưng làm tăng rủi ro nhầm lẫn nguồn dữ liệu và vòng lặp trong cấu hình hai chiều.

Chỉ sử dụng khi đã thiết kế rõ:
- Cluster nào là owner của topic.
- Hướng replicate nào được phép.
- Cách ngăn record bị replicate quay ngược.
- Cách xử lý topic trùng tên tồn tại ở cả hai cluster.
- Cách cutover và cutback.

Không bật replication hai chiều cho cùng một tập topic chỉ vì muốn hai cluster “giống hệt nhau”.

## 8. Chuẩn bị DR ngoài dữ liệu topic

Replication record không tự động làm cho toàn bộ ứng dụng sẵn sàng ở DR. Cần chuẩn bị các thành phần liên quan:

| Thành phần | Việc cần làm tại DR |
|---|---|
| Topic | Tạo đúng partition count, RF, retention, cleanup và config |
| ACL | Provision principal và quyền tương ứng |
| User/credential | Tạo hoặc đồng bộ identity theo quy trình an toàn |
| TLS | Certificate, trust chain, DNS và hostname |
| Schema Registry | Replicate hoặc provision schema và compatibility policy |
| Kafka Connect | Worker, connector config, plugin và secret |
| Kafka Streams | Application config, application.id, internal topics và state restore |
| Consumer group | Checkpoint và offset translation |
| Quota | Client/user quota phù hợp DR capacity |
| Monitoring | Dashboard, alert, log pipeline và tracing |
| Application | DR bootstrap servers, endpoint config, secret và deployment |
| Downstream DB/API | Capacity, credentials, idempotency và recovery plan |

Một số phiên bản/cấu hình MM2 có thể đồng bộ một phần topic config hoặc ACL. Không giả định mọi metadata, identity, secret, schema và dịch vụ phụ trợ được replicate. Hãy kiểm tra feature hỗ trợ của phiên bản, bật rõ ràng và kiểm thử độc lập.

### 8.1. Schema Registry

Nếu event dùng Avro, Protobuf hoặc JSON Schema, consumer ở DR cần truy cập schema tương thích. Tùy sản phẩm, Schema Registry có thể có replication mode riêng hoặc cần export/import schema và cấu hình subject.

Kiểm tra:
- Subject naming strategy.
- Schema ID mapping.
- Compatibility policy.
- Authentication/authorization.
- URL được cấu hình trong producer/consumer DR.
- Khả năng đọc record cũ sau failover.

Không giả định schema ID ở registry target luôn giống source nếu chưa có cơ chế đảm bảo mapping.

### 8.2. Kafka Streams

Kafka Streams state store cục bộ không được khôi phục chỉ bằng việc mirror input topic. Changelog và repartition topics có thể được replicate nếu nằm trong scope, nhưng app cần cấu hình đúng application.id, internal topic và state restoration.

Khi chạy cùng một application.id trên cluster DR, cần bảo đảm không có hai cụm cùng xử lý cùng ownership ngoài ý muốn. Kiểm tra source topic names, internal topic names, standby task và external side effect trước khi bật traffic.

### 8.3. Kafka Connect

Connector config, task state, secret provider và plugin không tự xuất hiện ở DR chỉ vì dữ liệu Kafka đã được mirror. Provision worker cluster và connector config qua configuration management. Kiểm tra source/sink không vô tình chạy song song ở hai region và ghi trùng vào database hoặc hệ thống ngoài.

## 9. Theo dõi replication lag

Replication lag là yếu tố trực tiếp ảnh hưởng RPO. Cần theo dõi nhiều tín hiệu thay vì một metric đơn lẻ.

### 9.1. Tín hiệu cần theo dõi

- Heartbeat record age hoặc heartbeat latency.
- Source connector task state và lỗi.
- Target topic record arrival rate.
- Source/target offset mapping và checkpoint freshness.
- Consumer group checkpoint lag.
- Connect worker CPU, heap, task restart và rebalance.
- Source fetch throughput và target produce throughput.
- Network throughput, packet loss và authentication failure.
- Under-replicated/offline partition ở cả source và target.

Tên metric cụ thể phụ thuộc Kafka/MM2 version, JMX exporter và monitoring stack. Dùng metric từ đúng connector và dashboard đang triển khai.

### 9.2. Heartbeat không thay thế per-topic lag

Heartbeat có thể đến target trong khi một topic cụ thể không được include, bị lỗi ACL hoặc source connector task cho topic đó bị dừng. Vì vậy cần kiểm tra:
- Topic nằm trong allowlist.
- MirrorSourceConnector task đang RUNNING.
- Record của topic mới nhất đã đến target.
- Offset-sync/checkpoint đang cập nhật.
- Topic target không bị under-replicated.

### 9.3. Alert theo RPO

Đặt cảnh báo theo mục tiêu nghiệp vụ:

- Warning khi lag đạt một phần RPO budget.
- Critical khi lag vượt RPO hoặc heartbeat stale quá ngưỡng.
- Alert khi task FAILED/PAUSED hoặc không có source record progress.
- Alert khi target disk headroom không đủ.
- Alert khi offset checkpoint không cập nhật.

Ví dụ nếu RPO là 60 giây, có thể đặt warning ở 30 giây và critical ở 60 giây, nhưng ngưỡng thực tế phải tính cả scrape interval, clock skew và cách đo lag. Không đợi sự cố mới đo replication delay.

### 9.4. Kiểm tra nhanh bằng CLI và Connect REST

Kiểm tra remote topic trên DR:

~~~bash
kafka-topics.sh --bootstrap-server dr-1.internal:9092 --describe --topic primary.orders
~~~

Kiểm tra consumer group ở target:

~~~bash
kafka-consumer-groups.sh --bootstrap-server dr-1.internal:9092 --describe --group orders-service
~~~

Kiểm tra connector/task state qua Connect REST API:

~~~bash
curl -s http://connect-dr.internal:8083/connectors
curl -s http://connect-dr.internal:8083/connectors/<connector-name>/status
~~~

Các lệnh là ví dụ; thay alias, topic, group, endpoint và authentication theo môi trường. REST endpoint phải được bảo vệ bằng TLS/authentication và chỉ truy cập từ management network. Một lệnh describe thành công không thay thế việc đối chiếu record arrival, checkpoint freshness và business event ID.

## 10. Lập kế hoạch failover

Failover là chuyển workload từ primary sang DR khi primary không thể đáp ứng service requirement hoặc có nguy cơ mất dữ liệu vượt ngưỡng.

### 10.1. Trigger failover

Có thể kích hoạt khi:
- Primary cluster hoặc region không thể phục vụ quá thời gian cho phép.
- Offline partition hoặc controller failure ảnh hưởng nghiêm trọng.
- Network/identity outage khiến client không thể kết nối.
- Dự báo RTO sẽ vượt ngưỡng.
- Security incident buộc phải cô lập primary.
- Business continuity owner quyết định chuyển site.

Không tự động failover chỉ vì một broker restart hoặc vài request timeout. Phải phân biệt lỗi cục bộ có thể phục hồi với lỗi site-level.

### 10.2. Quyền quyết định

Runbook cần nêu rõ:
- Ai phát hiện và mở incident.
- Ai xác nhận primary không còn authoritative.
- Ai có quyền declare disaster.
- Ai thực hiện fencing.
- Ai chuyển producer/consumer.
- Ai xác nhận dữ liệu và mở traffic.
- Ai có quyền quyết định failback.

Nếu không rõ người quyết định, nhiều đội có thể cùng thao tác và tạo split-brain.

### 10.3. Trạng thái trước failover

Ghi lại:
- Thời điểm lỗi và thời điểm quyết định.
- Replication lag cuối cùng đáng tin cậy.
- Heartbeat và checkpoint freshness.
- Source/target topic assignment.
- Consumer group offsets/checkpoints.
- Producer acknowledgement policy.
- Các record đang in-flight nếu có thể xác định.
- Downstream database checkpoint và idempotency state.

Với unplanned outage, một số thông tin có thể không lấy được. Ghi rõ điều gì đã biết, điều gì là ước lượng và RPO thực tế được chấp nhận.

## 11. Fencing primary và tránh split-brain

Trước khi DR nhận ghi, phải ngăn primary cũ tiếp tục ghi hoặc xác minh nó đã bị cô lập. Nếu primary chỉ mất liên lạc với đội vận hành nhưng vẫn phục vụ một phần client, cả hai cluster có thể cùng nhận event cho một nghiệp vụ.

Fencing có thể gồm:
- Tắt producer deployment ở primary.
- Thu hồi/disable producer credential hoặc ACL Write.
- Chặn network path đến client listener.
- Cô lập primary qua firewall, routing hoặc cloud control plane.
- Dừng các connector/source task có thể phát dữ liệu.
- Dùng orchestration lock/lease hoặc control-plane ownership token.
- Ghi nhận bằng chứng primary đã bị fence.

Không chỉ đổi DNS hoặc bootstrap server trong config. Client có thể giữ connection cũ, DNS cache hoặc retry tới primary. Fencing cần kiểm soát ở cả ứng dụng, network và identity.

### 11.1. Split-brain

Split-brain xảy ra khi hai cluster được xem là authoritative cho cùng một luồng và cùng nhận ghi. Khi đó:
- Cùng entity có thể có hai chuỗi event khác nhau.
- Offset không thể so sánh trực tiếp.
- Ordering giữa hai cluster không có bảo đảm toàn cục.
- Replication hai chiều có thể tạo vòng lặp hoặc duplicate.
- Downstream database có thể nhận side effect hai lần.

Cần một nguồn sự thật cho mỗi domain trong từng giai đoạn. Nếu active-active là yêu cầu, ownership phải được phân chia rõ và conflict resolution phải thiết kế ở tầng nghiệp vụ.

## 12. Quy trình failover active-passive

Một trình tự mẫu:

~~~mermaid
flowchart TD
    A[Declare disaster] --> B[Capture lag and last known state]
    B --> C[Fence primary]
    C --> D[Verify DR cluster health]
    D --> E[Check mirrored topics and checkpoints]
    E --> F[Prepare ACL, schema, secrets and app config]
    F --> G[Translate or apply consumer offsets]
    G --> H[Switch producer and consumer traffic]
    H --> I[Validate event flow and downstream effects]
    I --> J[Monitor RPO/RTO and service SLO]
~~~

### 12.1. Bước 1: Declare disaster

Incident commander xác nhận trigger, phạm vi và quyết định RPO có thể chấp nhận. Ghi rõ thời điểm bắt đầu RTO.

### 12.2. Bước 2: Fence primary

Cô lập primary khỏi producer và connector có thể tiếp tục ghi. Nếu primary không thể truy cập, dùng network/control-plane evidence để xác nhận trạng thái. Không mở ghi ở DR khi chưa hiểu khả năng primary quay lại.

### 12.3. Bước 3: Kiểm tra DR

Xác minh:
- Broker và controller quorum healthy.
- Remote topics tồn tại và có partition/replica phù hợp.
- Không có offline partition hoặc ISR bất thường.
- Connect/MM2 không tiếp tục tạo lỗi không kiểm soát.
- Schema, ACL và secret đã sẵn sàng.
- Target disk/network còn headroom.

### 12.4. Bước 4: Chọn cutover point

Dùng replication lag, heartbeat, checkpoint và business event ID để ước lượng dữ liệu cuối cùng có ở DR. Không dùng offset source trực tiếp làm offset target.

Nếu cần RPO nghiêm ngặt hơn mức lag hiện tại, có thể phải chấp nhận downtime lâu hơn để chờ replication catch up hoặc phục hồi primary. Đây là quyết định nghiệp vụ giữa availability và data loss.

### 12.5. Bước 5: Consumer offset

MirrorCheckpointConnector phát checkpoint ánh xạ offset source sang remote topic. Nếu bật sync.group.offsets.enabled, MM2 có thể đồng bộ group offsets theo cơ chế và điều kiện của phiên bản triển khai; cần xác nhận consumer group target không đang hoạt động và kiểm thử trước.

Trước khi khởi động consumer ở DR:
- Kiểm tra checkpoint mới nhất.
- Xác định target topic name.
- Xác định offset target tương ứng.
- Xác minh group ID và subscription.
- Tránh chạy cùng group ở cả source và DR.
- Không reset offset theo số offset source nếu chưa translate.

Nếu checkpoint thiếu hoặc stale, chọn replay từ vị trí an toàn và dựa vào eventId/idempotency để xử lý duplicate. Với nghiệp vụ nhạy cảm, owner phải phê duyệt điểm bắt đầu.

### 12.6. Bước 6: Chuyển producer

Cập nhật bootstrap servers hoặc service discovery sang DR. Xác minh producer dùng đúng topic local/remote, serializer, schema registry, security principal và transaction settings.

Producer retry sau timeout có thể phát lại record mà ứng dụng không biết lần gửi trước đã được ghi ở source hay chưa. Dùng eventId/idempotency key ở tầng nghiệp vụ để downstream nhận diện duplicate.

### 12.7. Bước 7: Mở consumer và downstream

Khởi động consumer sau khi offset và topic mapping được xác minh. Kiểm tra database/API side effect, retry topic, DLT, consumer lag và event ordering theo key. Mở traffic theo canary nếu có thể trước khi chuyển toàn bộ.

## 13. Consumer offset translation và replay

Offset là vị trí trong một partition của một topic cụ thể. Khi record được mirror sang remote topic, offset target không nhất thiết bằng source offset.

### 13.1. Checkpoint

Checkpoint liên kết source offset với target offset cho một consumer group và partition. Đây là dữ liệu giúp consumer tiếp tục gần vị trí đã xử lý trước đó.

Checkpoint có thể không phản ánh chính xác mọi trạng thái business side effect. Ví dụ consumer đã commit offset sau khi gọi database nhưng transaction database chưa bền vững theo mong muốn, hoặc side effect đã thành công nhưng commit offset thất bại.

### 13.2. Reset offset có kiểm soát

Không dùng lệnh reset offset bằng số source offset một cách mù quáng. Nếu cần dùng kafka-consumer-groups.sh, hãy:
- Dừng consumer group ở DR.
- Xác định topic/partition đích.
- Xác định target offset từ checkpoint/translation hoặc replay policy.
- Dry-run nếu CLI hỗ trợ.
- Lưu offset hiện tại.
- Thực hiện với approval.
- Xác minh bằng eventId và business checkpoint.

Offset reset là thao tác có thể làm duplicate hoặc bỏ sót dữ liệu. Không dùng trong failover lần đầu nếu chưa có runbook đã diễn tập.

### 13.3. Replay và idempotency

Nếu không thể xác định checkpoint đáng tin cậy, replay từ điểm sớm hơn thường giảm nguy cơ mất dữ liệu nhưng tăng duplicate. Consumer cần idempotent handling:
- eventId duy nhất cho event logic.
- Inbox/deduplication table hoặc idempotency key.
- Unique constraint ở database khi phù hợp.
- Side effect có thể retry an toàn.
- Audit replay request và operator.

Replay không thể tự đảo ngược side effect đã xảy ra ở downstream. Cần business reconciliation cho payment, inventory hoặc notification.

## 14. Transaction và exactly-once boundary

Kafka transaction có phạm vi trong một Kafka cluster. MM2 replication không tái tạo một distributed transaction duy nhất trải qua source cluster, target cluster và database.

Cần phân biệt:
- Producer transaction commit ở primary.
- Record được MirrorSourceConnector đọc và publish sang DR.
- Target record xuất hiện ở remote topic.
- Consumer ở DR xử lý record.
- Database hoặc external system ghi side effect.

Các bước này không phải một transaction xuyên cluster. Có thể tồn tại khoảng thời gian record đã commit ở primary nhưng chưa có ở DR. Khi failover, target có thể chỉ có một phần chuỗi transaction gần nhất tùy replication behavior và cấu hình consumer isolation.

Kiểm thử read_committed, aborted transaction behavior và transaction ID khi chuyển cluster theo phiên bản MM2/Kafka. Không tuyên bố exactly-once end-to-end chỉ vì source producer dùng enable.idempotence hoặc transactional.id.

## 15. Failback khi primary phục hồi

Failback là chuyển workload từ DR về primary hoặc chọn primary cũ làm standby mới. Nó không đơn giản là đổi bootstrap server về địa chỉ cũ.

Sau failover, DR có thể đã nhận thêm event mà primary không có. Nếu chuyển traffic về primary ngay, những event mới này có thể bị mất hoặc bị xử lý lại.

### 15.1. Chọn authoritative cluster

Sau sự cố, xác định cluster nào chứa lịch sử dữ liệu được chấp nhận. Thường DR đang phục vụ sẽ trở thành authoritative cho đến khi quá trình đồng bộ ngược hoàn tất.

Không cho primary cũ nhận ghi trở lại chỉ vì broker đã khởi động. Trước tiên cần fence nó khỏi producer hoặc giữ ở chế độ standby.

### 15.2. Replicate ngược có kiểm soát

Một quy trình có thể:
1. Giữ DR tiếp tục phục vụ.
2. Kiểm tra primary cũ đã ổn định và security/config được khôi phục.
3. Cấu hình replication một chiều từ DR về primary.
4. Chọn topic và group scope rõ ràng.
5. Tránh replicate vòng lặp qua remote topic không chủ đích.
6. Theo dõi lag cho tới khi primary bắt kịp.
7. Kiểm tra dữ liệu, schema, ACL và application readiness.
8. Chọn thời điểm cutback.

Không bật đồng thời hai hướng replication trên cùng topic set nếu chưa có quy tắc loop prevention và ownership rõ. Default remote topic naming thường giúp phân biệt remote topic; vẫn cần kiểm tra đường dữ liệu thực tế.

### 15.3. Cutback

Khi primary đã bắt kịp:
- Thông báo cửa sổ chuyển đổi.
- Dừng hoặc pause producer ở DR.
- Chờ record in-flight hoàn tất hoặc xác định cutover boundary.
- Ghi lại checkpoint/offset và replication lag cuối.
- Fence DR khỏi producer mới.
- Chuyển producer sang primary.
- Chuyển consumer theo offset mapping đã kiểm chứng.
- Mở consumer và xác minh event flow.
- Theo dõi duplicate, missing event, ordering và downstream state.
- Giữ DR ở chế độ standby và cấu hình replication primary sang DR trở lại.

### 15.4. Không xóa dữ liệu DR quá sớm

Giữ snapshot, audit, log và topic DR theo retention/incident policy sau cutback. Cần thời gian quan sát để phát hiện sai lệch dữ liệu hoặc event bị bỏ sót. Không xóa remote topic chỉ vì ứng dụng đã quay lại primary.

## 16. Data validation sau failover/failback

Kiểm tra kết nối thành công chưa đủ. Phải xác minh tính toàn vẹn của event và trạng thái downstream.

Các cách kiểm tra:
- Đếm record theo topic và time bucket.
- So sánh eventId ở source/target trong phạm vi đã replicate.
- Kiểm tra key distribution và partition coverage.
- So sánh timestamp/event sequence nghiệp vụ.
- Kiểm tra duplicate và gap theo event sequence.
- Đối chiếu consumer offset/checkpoint.
- Reconcile database, payment ledger, inventory và outbox.
- Kiểm tra schema compatibility và deserialization.
- Xác minh retry/DLT và replay.
- Kiểm tra producer/consumer error rate và latency.

Offset source và target không phải thước đo trực tiếp để so sánh số record. Dùng event ID, business sequence, count theo cửa sổ hoặc checksum được tính trên tập dữ liệu tương đương.

## 17. Diễn tập khôi phục

DR plan chỉ có giá trị khi được diễn tập. Một runbook chưa từng chạy có thể thiếu quyền, secret, DNS, capacity hoặc bước offset translation.

### 17.1. Loại hình diễn tập

| Loại | Mục tiêu | Rủi ro |
|---|---|---|
| Tabletop | Kiểm tra vai trò, quyết định và communication | Thấp |
| Component drill | Dừng MM2 task hoặc làm network chậm trong lab | Thấp đến vừa |
| Planned failover | Chuyển workload có chuẩn bị từ primary sang DR | Vừa |
| Site failure simulation | Mô phỏng primary không khả dụng | Cao, cần môi trường kiểm soát |
| Failback drill | Đồng bộ ngược và cutback | Vừa |
| Full DR exercise | Kiểm tra cả ứng dụng, dữ liệu và downstream | Cao |

Không gây mất kết nối hoặc dừng broker production nếu chưa có approval, change window và rollback plan. Có thể mô phỏng phần lớn quy trình trong staging hoặc dedicated DR environment.

### 17.2. Kịch bản 1: Primary cluster outage

1. Tạo traffic event có eventId tăng dần.
2. Theo dõi MM2 replication lag.
3. Mô phỏng primary không thể truy cập.
4. Declare disaster và ghi thời điểm bắt đầu RTO.
5. Fence primary.
6. Xác minh remote topic và checkpoint.
7. Chuyển producer/consumer sang DR.
8. Đo event gap và duplicate.
9. Đo thời gian phục hồi.
10. So sánh RPO/RTO thực tế với mục tiêu.

### 17.3. Kịch bản 2: Replication lag vượt RPO

1. Tăng tải source hoặc giới hạn network replication trong môi trường test.
2. Theo dõi heartbeat và per-topic lag.
3. Xác định alert khi lag vượt warning threshold.
4. Quyết định chờ catch-up hay failover với data-loss approval.
5. Ghi nhận cutover point.
6. Kiểm tra dữ liệu cuối cùng ở DR.
7. Đề xuất capacity/network adjustment.

### 17.4. Kịch bản 3: Connect worker failure

1. Dừng một worker hoặc task MM2 trong môi trường test.
2. Xác nhận connector/task state và alert.
3. Kiểm tra heartbeat stale.
4. Khôi phục worker.
5. Xác nhận replication tiếp tục và lag giảm.
6. Kiểm tra checkpoint freshness.
7. Ghi lại RPO exposure trong khoảng task dừng.

### 17.5. Kịch bản 4: Network partition và split-brain

1. Tách network giữa primary và DR nhưng để client của mỗi phía tiếp tục hoạt động trong môi trường test.
2. Quan sát hai phía có thể nhận ghi hay không.
3. Kiểm tra fencing/ownership mechanism.
4. Xác định authoritative cluster theo runbook.
5. Khôi phục network.
6. Đánh giá conflict và duplicate.
7. Chứng minh chỉ một cluster được phép ghi cho domain đã chọn.

### 17.6. Kịch bản 5: Failback

1. Giả lập primary đã phục hồi.
2. Giữ DR làm authoritative.
3. Bật replication DR sang primary theo allowlist.
4. Chờ lag về ngưỡng chấp nhận.
5. Pause producer DR và chọn cutover point.
6. Chuyển traffic về primary.
7. Kiểm tra offsets, event IDs và downstream.
8. Khôi phục replication primary sang DR.
9. Xác nhận DR trở lại standby.

## 18. Đo kết quả diễn tập

Ghi các mốc thời gian:

| Mốc | Thời điểm |
|---|---|
| Sự cố bắt đầu | T0 |
| Alert được phát | T1 |
| Incident được xác nhận | T2 |
| Disaster được declare | T3 |
| Primary được fence | T4 |
| DR bắt đầu nhận traffic | T5 |
| Consumer xử lý ổn định | T6 |
| Business service đạt SLO | T7 |

RTO có thể đo từ T0 đến mốc dịch vụ được định nghĩa là phục hồi, ví dụ T7. Không chọn một mốc dễ đạt như broker online nếu nghiệp vụ vẫn chưa xử lý được event.

RPO thực tế cần đánh giá bằng event cuối cùng được xác nhận ở source và event cuối cùng có thể phục hồi/đọc được ở DR, có xét thời gian và business sequence. Nếu không thể xác định chính xác, báo cáo một khoảng ước lượng và nêu nguồn dữ liệu.

### 18.1. Báo cáo drill

Mỗi lần diễn tập cần ghi:
- Scenario và phạm vi.
- RPO/RTO mục tiêu.
- RPO/RTO thực tế.
- Replication lag trước/sau.
- Thời gian fencing.
- Thời gian offset recovery.
- Event duplicate/missing.
- Downstream reconciliation result.
- Bước runbook thất bại hoặc thiếu.
- Owner và deadline remediation.

## 19. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Remote topic không xuất hiện | Topic không khớp regex, source task lỗi hoặc ACL thiếu | Kiểm tra allowlist, connector state và source/target permissions |
| Heartbeat stale | MM2 task dừng, network hoặc auth lỗi | Kiểm tra worker, task log, listener và credential |
| Topic có dữ liệu nhưng checkpoint không cập nhật | Checkpoint connector lỗi hoặc group filter sai | Kiểm tra group regex và connector task |
| Consumer bắt đầu đọc sai vị trí | Offset source bị dùng trực tiếp hoặc checkpoint cũ | Dừng group, xác minh translation và replay policy |
| Target topic có tên khác | Default remote topic naming | Kiểm tra replication policy và consumer subscription |
| Replication loop | Hai chiều không có ownership/policy rõ | Tắt hướng sai, phân tích remote topic và thiết kế lại |
| DR consumer lỗi schema | Registry/subject chưa sẵn sàng | Provision schema và kiểm tra ID/compatibility |
| DR consumer bị authorization denied | ACL/principal chưa được chuẩn bị | Kiểm tra principal mapping và topic/group ACL |
| Failover tạo duplicate | Producer retry, offset replay hoặc in-flight record | Dùng eventId/idempotency và reconciliation |
| Missing event sau cutover | Replication lag hoặc checkpoint không chính xác | Xác định cutover boundary và replay an toàn |
| Primary và DR cùng ghi | Thiếu fencing hoặc ownership lock | Cô lập một phía và xử lý conflict trước khi tiếp tục |
| Failback không bắt kịp | Replication ngược thiếu capacity hoặc scope sai | Kiểm tra lag, network, topic filters và worker capacity |
| MM2 worker restart liên tục | Config, plugin, secret hoặc internal topic lỗi | Kiểm tra Connect worker logs và config |
| Target hết disk | RF/retention/replication backlog không được tính | Tăng capacity hoặc giới hạn scope có kiểm soát |
| Transaction behavior khác | Cross-cluster replication không giữ transaction boundary | Kiểm tra read_committed và thiết kế idempotent recovery |

## 20. Checklist production

### Thiết kế

1. Có topology active-passive/active-active được phê duyệt không?
2. Mỗi domain có authoritative cluster rõ ràng không?
3. RPO/RTO có owner nghiệp vụ xác nhận không?
4. Failure domain của DR có độc lập với primary không?
5. Có quy tắc chống split-brain và fencing không?
6. Có chiến lược remote topic naming và loop prevention không?

### Replication

7. MM2 source/checkpoint/heartbeat connector đã được triển khai HA chưa?
8. Topic/group allowlist có đúng không?
9. Target RF, min ISR, rack và retention đã sẵn sàng chưa?
10. Replication lag có alert theo RPO không?
11. Heartbeat và per-topic progress đều được theo dõi chưa?
12. Connect internal topics, worker config và secret đã được backup/provision chưa?

### Ứng dụng và dữ liệu

13. DR có ACL, credential, certificate và schema không?
14. Producer/consumer bootstrap config có thể chuyển đổi không?
15. Consumer offset translation đã được diễn tập chưa?
16. eventId/idempotency có xử lý duplicate không?
17. Downstream database/API có capacity và recovery plan không?
18. Kafka transaction và exactly-once boundary đã được hiểu đúng chưa?
19. Streams state store/changelog và Connect task state đã được xử lý chưa?

### Vận hành

20. Có incident commander và disaster approver không?
21. Primary fencing đã được kiểm thử chưa?
22. Có canary và validation trước khi mở toàn bộ traffic không?
23. Có quy trình failback một chiều và cutover point không?
24. Có data reconciliation và audit trail không?
25. Có diễn tập định kỳ và action item sau drill không?
26. Có xác minh RPO/RTO thực tế thay vì chỉ dựa trên tài liệu không?

## 21. Bài tập thực hành

### Bài 1: Xây dựng active-passive lab

1. Dựng hai Kafka cluster độc lập, primary và dr.
2. Dựng Kafka Connect worker cho MM2.
3. Cấu hình source, checkpoint và heartbeat connector.
4. Tạo topic orders với partition/RF phù hợp.
5. Gửi event có eventId tăng dần.
6. Quan sát remote topic và heartbeat ở DR.
7. Đo replication lag.

### Bài 2: Chuyển consumer offset

1. Tạo consumer group trên primary.
2. Xử lý và commit một số record.
3. Bật checkpoint connector.
4. Kiểm tra checkpoint ở DR.
5. Dừng consumer target.
6. Thực hiện offset sync/translation theo version đã chọn.
7. Khởi động consumer ở DR.
8. Kiểm tra duplicate và missing event bằng eventId.

### Bài 3: Diễn tập failover

1. Gửi traffic liên tục vào primary.
2. Chờ MM2 lag ở mức ổn định.
3. Mô phỏng primary outage.
4. Fence primary.
5. Chuyển producer/consumer sang DR.
6. Kiểm tra schema, ACL và downstream.
7. Đo RTO và RPO thực tế.
8. Viết báo cáo sai lệch so với mục tiêu.

### Bài 4: Diễn tập failback

1. Giữ DR tiếp tục nhận traffic.
2. Khôi phục primary.
3. Cấu hình replication ngược DR sang primary.
4. Theo dõi checkpoint và lag.
5. Pause producer DR tại cutover.
6. Chuyển traffic về primary.
7. Khôi phục hướng replication primary sang DR.
8. Xác nhận primary là authoritative và DR là standby.

### Bài 5: Mô phỏng split-brain

1. Tạo network partition giữa hai cluster.
2. Cho hai phía nhận ghi trong môi trường test.
3. Quan sát duplicate và conflict.
4. Áp dụng fencing/ownership policy.
5. Chọn authoritative cluster.
6. Reconcile event theo eventId.
7. Ghi lại cách ngăn tình huống lặp lại.

### Bài 6: Đo RPO/RTO

1. Tạo event có timestamp và sequence.
2. Ghi nhận source acknowledgement.
3. Theo dõi thời điểm record xuất hiện ở DR.
4. Kích hoạt failover.
5. Xác định event cuối cùng có thể phục hồi.
6. Tính RPO và RTO.
7. Điều chỉnh alert và capacity theo kết quả.

## 22. Câu hỏi tự kiểm tra

1. Replication factor trong một cluster khác multi-cluster replication như thế nào?
2. RPO và RTO khác nhau ra sao?
3. Vì sao acks=all không chứng minh record đã có ở DR?
4. Active-passive và active-active có trade-off gì?
5. MirrorSourceConnector làm nhiệm vụ gì?
6. MirrorCheckpointConnector dùng để làm gì?
7. MirrorHeartbeatConnector giúp phát hiện điều gì?
8. Vì sao remote topic thường có source alias trong tên?
9. IdentityReplicationPolicy cần lưu ý rủi ro nào?
10. Vì sao không replicate mọi topic một cách mù quáng?
11. MM2 có tự chuẩn bị toàn bộ ACL, secret và Schema Registry không?
12. Consumer offset source và target có nhất thiết bằng nhau không?
13. Vì sao cần checkpoint và offset translation?
14. Fencing primary ngăn rủi ro gì?
15. Split-brain gây vấn đề ordering và duplicate ra sao?
16. Vì sao transaction Kafka không phải transaction xuyên hai cluster?
17. Khi nào nên replay từ offset sớm hơn?
18. Failback khác failover như thế nào?
19. Vì sao phải replicate ngược trước khi cutback?
20. Cần đo gì trong một DR drill để chứng minh RPO/RTO?

## Kết luận

DR Kafka cần một cluster độc lập, replication pipeline được giám sát, ứng dụng có thể chuyển endpoint và runbook có thể thực thi. MirrorMaker 2 cung cấp replication topic, checkpoint offset và heartbeat giữa các cluster, nhưng dữ liệu được sao chép bất đồng bộ. Vì vậy, RPO phụ thuộc lag thực tế và failover không thể giả định mọi record đã được replicate.

Failover phải có quyết định rõ ràng, fencing primary, kiểm tra remote topic, schema, ACL, secret, consumer checkpoint và downstream state trước khi mở traffic ở DR. Offset source không được copy trực tiếp sang target; cần checkpoint/translation hoặc replay policy có idempotency. Transaction Kafka cũng không trở thành transaction xuyên cluster chỉ vì record được mirror.

Failback là một lần chuyển đổi có kiểm soát khác: xác định authoritative cluster, replicate ngược, chờ catch-up, chọn cutover point, fence DR, chuyển traffic và xác minh dữ liệu. Diễn tập định kỳ giúp đo RPO/RTO thật, tìm lỗ hổng trong identity, network, offset, schema và downstream, từ đó biến kế hoạch DR thành khả năng phục hồi có thể chứng minh.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Disaster Recovery (DR) | Khả năng khôi phục dịch vụ và dữ liệu sau sự cố lớn ở cluster/site. |
| Failover | Chuyển workload từ cluster/site đang lỗi sang cluster/site dự phòng. |
| Failback | Chuyển workload về cluster cũ hoặc site được chọn làm primary sau phục hồi. |
| RPO | Mức dữ liệu tối đa có thể chấp nhận mất khi phục hồi. |
| RTO | Thời gian tối đa chấp nhận để khôi phục dịch vụ. |
| Active-passive | Một cluster nhận ghi chính, cluster kia giữ bản sao chờ failover. |
| Active-active | Nhiều cluster cùng phục vụ ghi theo ownership/conflict policy. |
| MirrorMaker 2 | Bộ công cụ Kafka Connect để replicate topic, checkpoint và heartbeat giữa cluster. |
| MirrorSourceConnector | Connector đọc topic source và ghi remote topic ở target. |
| MirrorCheckpointConnector | Connector phát checkpoint ánh xạ consumer offset giữa source và target. |
| MirrorHeartbeatConnector | Connector phát heartbeat để quan sát replication path. |
| Remote topic | Topic mirror ở cluster đích, thường mang source alias trong tên. |
| Offset translation | Ánh xạ vị trí consumer source sang offset tương ứng trên remote topic. |
| Replication lag | Độ trễ giữa record ở source và record có thể đọc ở target. |
| Fencing | Cô lập cluster hoặc identity cũ để ngăn tiếp tục nhận ghi. |
| Split-brain | Hai cluster cùng được xem là authoritative và cùng nhận ghi cho một domain. |
| Checkpoint | Metadata liên kết source offset với offset ở remote topic. |
| Idempotency | Khả năng xử lý lặp mà không tạo side effect trùng. |
| Reconciliation | Đối chiếu và sửa sai lệch dữ liệu/trạng thái giữa các hệ thống. |
| Cutover point | Thời điểm hoặc vị trí dữ liệu được chọn làm ranh giới chuyển cluster. |
| Tabletop exercise | Diễn tập quy trình và quyết định mà không gây thay đổi kỹ thuật lớn. |
| Data validation | Kiểm tra record, event ID, sequence và downstream state sau phục hồi. |

