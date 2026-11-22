# RPO, RTO và các kịch bản thảm họa

Kafka replication trong một cluster bảo vệ partition khi broker gặp lỗi, nhưng không đủ để bảo vệ toàn bộ hệ thống khi mất region, mất cluster, lỗi thao tác hoặc dữ liệu bị xóa nhầm. Muốn phục hồi sau thảm họa, cần có cluster thứ hai ở failure domain độc lập, cơ chế sao chép dữ liệu, cách chuyển producer/consumer, quy trình ngăn hai nơi cùng ghi và kế hoạch kiểm thử định kỳ.

Hai chỉ số quyết định thiết kế Disaster Recovery (DR) là **RPO** và **RTO**. RPO cho biết tổ chức chấp nhận mất tối đa bao nhiêu dữ liệu tính theo thời gian; RTO cho biết dịch vụ phải được khôi phục trong bao lâu. Chúng không phải hai con số chỉ ghi trong tài liệu: kiến trúc replication, retention, capacity, offset translation, DNS, credential và quy trình failover đều phải được thiết kế để đáp ứng mục tiêu này.

Bài này xây dựng mô hình DR cho Apache Kafka, so sánh active-passive và active-active, giải thích MirrorMaker 2, cách đo replication lag, cách failover/failback an toàn và các kịch bản broker failure, cluster/region outage, data corruption, accidental deletion và credential compromise.

## 1. RPO và RTO là gì?

**Recovery Point Objective (RPO)** là lượng dữ liệu tối đa có thể mất sau một sự cố, thường biểu diễn bằng thời gian. Nếu RPO là 5 phút, sau khi khôi phục, hệ thống có thể thiếu tối đa khoảng 5 phút dữ liệu mới nhất so với trạng thái trước sự cố.

**Recovery Time Objective (RTO)** là thời gian tối đa cho phép để khôi phục dịch vụ về mức hoạt động đã cam kết. RTO không chỉ tính thời gian broker khởi động; nó còn gồm phát hiện sự cố, quyết định failover, fencing cluster cũ, chuyển endpoint, khôi phục consumer position, kiểm tra luồng nghiệp vụ và mở lại traffic.

Ví dụ:

| Mục tiêu | Giá trị | Ý nghĩa |
|---|---:|---|
| RPO | 5 phút | Chấp nhận mất tối đa 5 phút dữ liệu mới nhất trong tình huống DR |
| RTO | 30 phút | Dịch vụ phải xử lý event trở lại trong 30 phút theo cách đo đã thống nhất |
| Availability target | Theo SLA | Mức sẵn sàng tổng thể, không đồng nghĩa với RPO/RTO |

RPO và RTO phải được định nghĩa theo từng luồng nghiệp vụ. Topic thanh toán có thể cần RPO/RTO chặt hơn topic analytics. Không nên gán một mục tiêu chung cho mọi topic nếu giá trị dữ liệu, tốc độ phát sinh và khả năng xử lý lại khác nhau.

## 2. Tính RPO và RTO

### 2.1. Tính RPO

Một cách đo thực tế là so sánh thời điểm của record mới nhất đã được xác nhận bền vững ở primary với record mới nhất đã được xác nhận có thể đọc ở DR:

~~~text
RPO_observed = T_primary_durable - T_DR_durable
~~~

Timestamp ứng dụng có thể sai lệch giữa host, bị gửi trễ hoặc không phản ánh thứ tự append. Vì vậy nên kết hợp:

- Event có eventId duy nhất và timestamp nghiệp vụ được đồng bộ.
- Canary/sentinel record được phát định kỳ vào từng topic quan trọng.
- Replication latency và lag theo partition.
- Offset-sync/checkpoint của cơ chế mirroring.
- Đối chiếu số lượng event hoặc high-watermark nghiệp vụ khi failover.

Đánh giá theo từng topic-partition và lấy partition có độ trễ xấu nhất. Cần xác định phần log liên tục đã replicate tới đâu; chỉ nhìn timestamp của record mới nhất trên toàn cluster có thể che giấu một partition đang bị kẹt hoặc bị lọc.

Mốc primary phải dựa trên record producer đã nhận acknowledgement theo durability policy của topic. Với producer dùng acks=1, leader có thể trả lời trước khi follower replicate; record đó vẫn có nguy cơ mất khi leader gặp sự cố. Vì vậy cần ghi rõ acks, min.insync.replicas và replication factor khi công bố RPO.

Offset ở hai cluster không nhất thiết bằng nhau. Không lấy LEO_primary trừ LEO_DR làm RPO nếu chưa có phép ánh xạ offset giữa hai log.

### 2.2. Tính RTO

RTO quan sát được có thể tách thành:

~~~text
RTO = T_detect + T_decision + T_fence
    + T_promote + T_cutover + T_validate
~~~

| Thành phần | Nội dung |
|---|---|
| Detect | Phát hiện lỗi và xác định phạm vi |
| Decision | Incident commander quyết định kích hoạt DR |
| Fence | Ngăn primary cũ tiếp tục nhận ghi |
| Promote | Xác nhận DR đủ dữ liệu và sẵn sàng làm nơi phục vụ |
| Cutover | Chuyển producer, consumer, connector và endpoint |
| Validate | Kiểm tra event đầu cuối và mở lại traffic |

Đo RTO từ thời điểm incident theo định nghĩa của SLA tới thời điểm dịch vụ thực sự xử lý thành công event, không dừng đồng hồ ở lúc broker process chạy.

## 3. RPO/RTO quyết định kiến trúc DR

RPO càng thấp thì replication càng phải liên tục, độ trễ càng nhỏ và quy trình failover càng cần tự động hóa. RTO càng thấp thì DR cluster, network, credential, schema, connector, capacity và runbook càng phải sẵn sàng trước sự cố.

| Mục tiêu | Kiến trúc thường cân nhắc | Đánh đổi |
|---|---|---|
| RPO vài giờ, RTO nhiều giờ | Backup/restore, cluster dự phòng lạnh | Chi phí thấp hơn, phục hồi chậm |
| RPO vài phút, RTO hàng chục phút | Warm standby + asynchronous mirroring | Có thể mất dữ liệu chưa replicate |
| RPO rất thấp, RTO vài phút | Hot standby, replication liên tục, tự động hóa cutover | Chi phí và độ phức tạp cao |
| Gần zero RPO | Cơ chế đồng bộ có xác nhận ở nhiều failure domain hoặc thiết kế ứng dụng riêng | Latency cao, cần giải quyết consistency và partial failure |

Apache Kafka replication nội bộ giữa broker trong một cluster và MirrorMaker 2 giữa hai cluster là hai cơ chế khác nhau. MirrorMaker 2 thường hoạt động bất đồng bộ; nó không tự cung cấp cam kết zero data loss khi primary đột ngột mất trước khi record được replicate.

Không tuyên bố zero RPO chỉ vì đã cấu hình replication factor 3 hoặc có MirrorMaker 2. Replication factor bảo vệ replica trong cùng cluster; RPO đa cụm phải được đo ở cluster đích.

Muốn tiến gần zero RPO, ứng dụng có thể chỉ xác nhận event sau khi dữ liệu đã được ghi bền vững ở nhiều failure domain. Tuy nhiên, dual-write vào hai Kafka clusters không phải một transaction atomic: một cluster có thể commit trong khi cluster kia timeout. Thiết kế này cần idempotency, reconciliation, fencing và quy tắc xử lý partial success; không được gọi là zero RPO chỉ vì producer gửi hai lần.

## 4. Failure domain và kiến trúc hai cluster

Hai cluster DR chỉ có giá trị khi chúng không cùng phụ thuộc vào một failure domain duy nhất. Nếu cả hai cluster dùng cùng region, network backbone, identity provider, KMS hoặc storage control plane, một sự cố khu vực có thể làm cả hai không hoạt động.

~~~mermaid
flowchart LR
    subgraph RegionA[Region A - Primary]
        P[Producers] --> K1[Kafka Cluster A]
        K1 --> C1[Consumers A]
        K1 --> MM[MirrorMaker 2]
    end
    MM -->|Async replication| K2[Kafka Cluster B]
    subgraph RegionB[Region B - DR]
        K2 --> C2[Standby Consumers]
        K2 --> S[Schema / Connect / Streams dependencies]
    end
    DNS[Traffic routing / service endpoint] -. failover .-> P
~~~

Các thành phần cần tính vào DR:

- Kafka brokers và KRaft controller quorum ở region độc lập.
- MirrorMaker 2 hoặc cơ chế replication được hỗ trợ.
- Topic, partition count, replication factor, cleanup policy và retention tương thích.
- Schema Registry hoặc schema service cùng schema subject/compatibility.
- ACL, principal, certificate, secret và KMS key policy.
- Producer/consumer configuration và endpoint discovery.
- Kafka Connect connector config, offsets, status và external systems.
- Kafka Streams application ID, changelog/repartition topics và state recovery.
- Monitoring, alerting, DNS/service discovery, CI/CD và runbook.

Không copy nguyên log directory hoặc metadata directory của primary sang DR như một cách tạo cluster thứ hai. Cluster độc lập có cluster identity và storage riêng; dữ liệu được chuyển qua replication hoặc quy trình backup/restore phù hợp.

## 5. Chọn active-passive hay active-active

### 5.1. Active-passive

Primary nhận ghi và xử lý production. DR nhận bản sao topic, duy trì consumer offset/checkpoint cần thiết và chờ được promote.

Ưu điểm:

- Dễ xác định một nơi là nguồn ghi chính.
- Giảm xung đột event và đơn giản hóa ordering theo key.
- Failover có thể được kiểm soát theo một quy trình rõ.
- Phù hợp với hệ thống cần RPO thấp nhưng chấp nhận DR standby.

Đánh đổi:

- DR capacity có thể nhàn rỗi khi bình thường.
- Cần kiểm thử promote, consumer offset và dependency trước khi sự cố xảy ra.
- RPO phụ thuộc replication lag tại thời điểm primary mất.

### 5.2. Active-active

Hai region cùng nhận ghi. Ứng dụng cần quy tắc định tuyến event, ownership dữ liệu, xử lý conflict và chống vòng lặp replication.

Ưu điểm:

- Có thể phục vụ người dùng gần nhiều region.
- Có khả năng tiếp tục nhận event ở region còn sống.
- Tận dụng hạ tầng cả hai nơi.

Đánh đổi:

- Cùng một entity có thể được cập nhật đồng thời ở hai nơi.
- Thứ tự toàn cục không được đảm bảo giữa cluster.
- Replication loop và duplicate event cần được xử lý.
- Conflict resolution thường phải nằm ở tầng nghiệp vụ.
- Failback phức tạp hơn vì cả hai phía có thể đã nhận dữ liệu mới.

Active-active không tự tạo một Kafka log toàn cục. Kafka đảm bảo ordering trong một partition của một cluster; nó không cung cấp total ordering xuyên hai cluster độc lập.

| Tiêu chí | Active-passive | Active-active |
|---|---|---|
| Nơi ghi chính | Một cluster | Nhiều cluster |
| Conflict | Ít hơn, dễ kiểm soát | Cần giải quyết ở nghiệp vụ |
| Ordering | Dễ giữ theo key tại primary | Không có thứ tự toàn cục |
| Failover | Promote DR và fence primary | Chuyển routing và xử lý hai luồng dữ liệu |
| Vận hành | Đơn giản hơn | Phức tạp hơn |
| Use case | Core transaction, order, payment event | Global ingestion, telemetry, regional workloads |

Nếu nghiệp vụ chưa có conflict resolution rõ ràng, active-passive thường là lựa chọn dễ vận hành và chứng minh RPO/RTO hơn.

## 6. Replication giữa cluster bằng MirrorMaker 2

MirrorMaker 2 (MM2) là bộ công cụ dựa trên Kafka Connect để replicate topic giữa Kafka clusters. Nó bao gồm connector cho source, checkpoint và heartbeat; có thể replicate record, theo dõi consumer group checkpoint và cung cấp thông tin phục vụ offset translation.

| Thành phần | Vai trò |
|---|---|
| MirrorSourceConnector | Đọc topic nguồn và ghi record sang cluster đích |
| MirrorCheckpointConnector | Phát checkpoint ánh xạ consumer group offset |
| MirrorHeartbeatConnector | Phát heartbeat để theo dõi kết nối/replication |
| Offset-syncs topic | Lưu ánh xạ offset nguồn sang offset đích |
| Checkpoints topic | Lưu checkpoint của consumer group |
| Heartbeat topic | Chứng minh luồng replication còn hoạt động |

MM2 replicate record theo partition và có thể giữ topic name theo replication policy. Default replication policy thường thêm alias cluster nguồn vào tên topic đích, ví dụ primary.orders.events. Điều này giúp phân biệt nguồn và giảm nguy cơ vòng lặp. Nếu dùng IdentityReplicationPolicy để giữ tên topic giống nhau, phải thiết kế routing và loop prevention rất cẩn thận.

### 6.1. Ví dụ cấu hình MM2 active-passive

Ví dụ connect-mirror-maker.properties tối giản cho một hướng primary sang dr:

~~~properties
clusters = primary, dr

primary.bootstrap.servers = kafka-a1.example.internal:9093,kafka-a2.example.internal:9093
dr.bootstrap.servers = kafka-b1.example.internal:9093,kafka-b2.example.internal:9093

primary->dr.enabled = true
primary->dr.topics = orders.events,payments.events,inventory.events
primary->dr.groups = orders-service,payments-service

replication.factor = 3
checkpoints.topic.replication.factor = 3
heartbeats.topic.replication.factor = 3
offset-syncs.topic.replication.factor = 3

primary->dr.emit.heartbeats.enabled = true
primary->dr.emit.checkpoints.enabled = true
primary->dr.sync.group.offsets.enabled = true
~~~

Đây là mẫu để học cấu trúc, không phải file production hoàn chỉnh. Cần bổ sung security properties cho từng cluster, connector worker, converter, topic filters, replication policy, task parallelism, config topic và version-specific settings. Tên property và hành vi đồng bộ group offset cần được xác minh theo đúng Kafka version đang triển khai.

Khi bật sync.group.offsets, MM2 chỉ có thể đồng bộ offset của group theo các điều kiện hoạt động của connector; group đang active ở target có thể không được ghi đè. Checkpoint vẫn là dữ liệu để dịch offset, không phải bằng chứng rằng mọi record trước offset đó đã được replicate. Luôn kiểm tra behavior của version đang chạy và không dùng tính năng này thay cho quy trình offset recovery đã diễn tập.

Chạy MM2 bằng script đi kèm Kafka distribution:

~~~bash
connect-mirror-maker.sh connect-mirror-maker.properties
~~~

Triển khai MM2 worker trên failure domain phù hợp, theo dõi connector/task state, replication throughput, lag và lỗi source/target. MM2 không tự replicate toàn bộ cluster configuration, ACL, broker setting, KRaft metadata hoặc mọi dependency ứng dụng.

## 7. Offset translation và consumer recovery

Offset là vị trí trong log của một partition thuộc một cluster. Khi MM2 replicate record, cluster đích có log riêng và offset đích có thể khác offset nguồn do record bị lọc, topic được tạo khác thời điểm hoặc replication bắt đầu từ một offset nhất định.

Không lấy consumer offset của primary rồi dùng nguyên số đó làm offset của DR. Ví dụ consumer group đã commit offset 12000 ở primary không có nghĩa offset 12000 ở DR đại diện cho cùng record.

MM2 dùng offset-syncs và checkpoint để ánh xạ offset nguồn/đích. Trong DR:

1. Xác định checkpoint mới nhất của group trên cluster đích.
2. Kiểm tra group có active member ở cluster đích hay không.
3. Chuyển đổi source offset sang target offset bằng cơ chế checkpoint/translation phù hợp.
4. Xác nhận offset đích không vượt log end offset và nằm trong retention window.
5. Ghi nhận khả năng duplicate hoặc gap tại biên replication.
6. Chỉ khởi động consumer production sau khi cutover được phê duyệt.

Nếu không có offset mapping đáng tin cậy, chọn reset policy có chủ đích. earliest có thể replay nhiều record và tạo duplicate; latest có thể bỏ qua record đang tồn tại trước lúc consumer khởi động. Không để auto.offset.reset quyết định thay cho DR plan.

Checkpoint thường được phát theo chu kỳ, vì vậy consumer position ở DR có thể cũ hơn trạng thái primary. RPO dữ liệu và RPO consumer progress là hai vấn đề liên quan nhưng khác nhau: record có thể đã đến DR nhưng group checkpoint chưa được đồng bộ.

Nếu phải reset thủ công, offset nhập vào lệnh quản trị phải là offset của topic/partition trên cluster đích sau khi đã dịch, không phải offset primary. Kiểm tra target topic name theo replication policy; ví dụ topic có thể mang prefix primary. Thực hiện reset ở staging trước, lưu offset cũ và chỉ chạy trên group đã dừng.

## 8. Đo replication lag và xác nhận RPO

Không chỉ kiểm tra MM2 connector có trạng thái RUNNING. Connector chạy nhưng vẫn có thể lag nhiều phút hoặc không replicate một số topic do filter, ACL hay lỗi serialize.

Theo dõi:

- Source record rate và target record rate theo topic/partition.
- Replication latency/record age.
- Offset-sync/checkpoint freshness.
- Heartbeat age.
- Connector/task state và error count.
- Target topic partition count, leader, ISR và log end offset.
- Canary event end-to-end từ source tới target.

Tên JMX metric phụ thuộc Kafka version, connector và monitoring reporter. Hãy dùng metric reference đúng phiên bản; dashboard nên có cả lag theo số record/offset và lag theo thời gian tuổi của record.

Ví dụ quy tắc cảnh báo:

| Tín hiệu | Cảnh báo | Hành động |
|---|---|---|
| Heartbeat không tới DR | Quá ngưỡng đã định | Kiểm tra network, connector và broker |
| Replication record age | Vượt ngân sách RPO | Tăng ưu tiên xử lý lag; đánh giá có tiếp tục ghi primary không |
| Checkpoint quá cũ | Vượt ngưỡng consumer recovery | Chuẩn bị offset translation/replay |
| Target ISR không đủ | Replica DR chưa an toàn | Khắc phục DR cluster trước khi tuyên bố sẵn sàng |
| Connector task FAILED | Có topic/partition không replicate | Kiểm tra lỗi cụ thể và xác nhận phạm vi dữ liệu bị ảnh hưởng |

Ví dụ: mục tiêu RPO 5 phút nhưng tuổi record mới nhất ở DR đã 4 phút 30 giây. Hệ thống chỉ còn 30 giây ngân sách RPO; đây nên là cảnh báo nghiêm trọng, không đợi đến khi lag vượt 5 phút mới hành động.

## 9. Những gì cần chuẩn bị ở DR cluster

Trước khi có sự cố, target cluster phải được provision và kiểm tra:

- Broker/controller đủ capacity để nhận production traffic.
- Topic có partition count, replication factor, cleanup policy và retention phù hợp.
- Topic nội bộ cần thiết cho ứng dụng được tạo và bảo vệ đúng.
- ACL, service principal, SCRAM/OAuth credential, certificate và truststore sẵn sàng.
- Schema Registry/schema subjects và compatibility mode đồng bộ.
- Nếu payload chứa schema ID trong wire format, schema và ID mapping phải có thể resolve ở DR; chỉ replicate Kafka record là chưa đủ.
- Consumer group offset/checkpoint có thể dịch sang target offsets.
- Kafka Connect connector plugin, config, secret và external endpoint sẵn sàng.
- Kafka Streams state/changelog/repartition topics có thể phục hồi.
- Monitoring, alert, dashboard và incident channel hoạt động độc lập với primary region.
- DNS/service endpoint và network policy cho phép cutover.

Không giả định MM2 sẽ sao chép các thành phần trên. Đặc biệt, schema registry, ACL, quota, broker config, connector secrets và KRaft metadata cần kế hoạch riêng.

## 10. Kịch bản 1: một broker bị lỗi

Nếu một broker trong primary cluster bị lỗi nhưng cluster vẫn còn controller quorum và replica ISR:

1. Kiểm tra broker failure và partition leader election.
2. Xác nhận không có offline partition hoặc mất ISR ngoài dự kiến.
3. Chờ replica catch up hoặc thay broker theo runbook cluster operations.
4. Kiểm tra producer error/retry, consumer lag và under-replicated partitions.
5. Xác nhận MM2 vẫn replicate sang DR.

Đây thường không phải lý do để failover sang DR. Failover đa cụm có blast radius lớn hơn và có thể làm phức tạp dữ liệu đang được primary xử lý bình thường.

Nếu broker lỗi làm partition offline do replication factor 1 hoặc mọi replica cùng failure domain, đánh giá mức độ sự cố và phục hồi cluster theo runbook. DR chỉ được promote khi primary thực sự không thể phục hồi trong RTO hoặc có quyết định incident commander.

## 11. Kịch bản 2: mất toàn bộ primary cluster hoặc region

Đây là tình huống DR active-passive điển hình.

### Quy trình failover

1. **Declare incident:** xác nhận mất cluster/region và kích hoạt DR theo quyền hạn.
2. **Assess replication point:** kiểm tra heartbeat, replication lag, checkpoint và record mới nhất ở DR.
3. **Fence primary:** ngăn producer, consumer và operator ghi/đọc theo luồng primary cũ; cô lập network/credential hoặc dùng cơ chế fencing được chuẩn bị.
4. **Promote DR:** xác nhận target topic, partition, ISR, ACL, schema và dependency đủ khỏe.
5. **Translate offsets:** xác định offset đích cho từng consumer group; ghi lại reset plan.
6. **Cut over producers:** cập nhật bootstrap endpoint/secret/config để producer chỉ ghi DR.
7. **Start consumers:** khởi động consumer theo thứ tự phụ thuộc, bắt đầu với nhóm quan trọng nhất.
8. **Validate:** kiểm tra canary event, business invariants, duplicate/gap và downstream side effects.
9. **Scale:** tăng consumer/broker capacity theo tải production.
10. **Communicate:** ghi nhận RPO/RTO thực tế và thông báo trạng thái dịch vụ.

### Điều kiện không được bỏ qua

- Không promote DR khi chưa biết primary còn nhận ghi hay không.
- Không cho producer gửi đồng thời vào cả primary cũ và DR trong mô hình active-passive.
- Không khởi động consumer trước khi offset strategy được quyết định.
- Không tuyên bố RPO đạt chỉ dựa trên heartbeat; cần kiểm tra record/offset evidence.
- Không quên database, schema service, Connect sink và dịch vụ downstream.

## 12. Fencing và split-brain prevention

Fencing là biện pháp ngăn cluster cũ tiếp tục nhận ghi sau khi DR được promote. Nếu primary cũ chỉ mất kết nối từ operator nhưng vẫn reachable với một số producer, cả hai cluster có thể cùng nhận event và tạo split-brain ở tầng nghiệp vụ.

Các lớp fencing có thể phối hợp:

- Network isolation: chặn producer và consumer tới primary cũ.
- Credential fencing: thu hồi hoặc disable principal cũ; dùng credential riêng cho DR.
- Endpoint fencing: cập nhật service discovery/DNS nhưng không coi DNS là biện pháp duy nhất.
- Application fencing: producer kiểm tra active-cluster lease/epoch trước khi ghi.
- Operational fencing: incident commander ghi rõ cluster nào là writable và khóa quyền promote ngoài quy trình.

Một thiết kế nâng cao có thể dùng epoch/leader token do hệ thống điều phối độc lập cấp. Producer chỉ được ghi khi epoch còn hiệu lực; epoch cũ bị từ chối sau failover. Kafka cluster tự thân không cung cấp một global writer lease xuyên nhiều cluster độc lập.

Fencing phải được kiểm tra thực tế. DNS cutover có thể bị cache; process producer đang chạy có thể giữ bootstrap metadata; credential cũ có thể chưa bị thu hồi. Hãy xác minh không còn write traffic tới primary trước khi mở DR cho production.

Sau khi promote DR, dừng hoặc vô hiệu hóa hướng MM2 primary → DR cũ theo runbook để tránh connector cũ tiếp tục chạy ngoài dự kiến. Chỉ bật hướng DR → primary trong giai đoạn failback khi đã có kế hoạch loop prevention và source of truth rõ ràng.

## 13. Kịch bản 3: xóa nhầm topic hoặc record

MirrorMaker 2 replicate thay đổi dữ liệu từ source sang target. Nếu một operator xóa topic hoặc một producer phát tombstone/delete event sai, thay đổi có thể được replicate sang DR. Vì vậy DR mirror không thay thế backup.

Quy trình:

1. Dừng thao tác xóa hoặc producer gây lỗi.
2. Xác định topic/partition, thời điểm, phạm vi và loại dữ liệu bị ảnh hưởng.
3. Kiểm tra dữ liệu còn trong retention, backup, object storage hoặc immutable archive.
4. Tạm dừng replication liên quan nếu runbook đã định nghĩa và có thể làm an toàn; tránh phát tán thêm thao tác phá hoại.
5. Restore vào topic mới hoặc cluster cách ly để kiểm tra.
6. Xác minh record count, schema, key, offset và business invariant.
7. Lập kế hoạch replay/migrate sang topic phục vụ.
8. Chỉ mở lại producer/consumer sau khi xác nhận nguồn dữ liệu chuẩn.

Không phục hồi bằng cách tạo topic cùng tên và giả định offset cũ sẽ tiếp tục. Topic mới có log/offset riêng; consumer offset, ordering và idempotency cần được xử lý rõ.

## 14. Kịch bản 4: dữ liệu bị corruption hoặc event sai nghiệp vụ

Replication sao chép bytes hợp lệ theo Kafka protocol, không biết event có đúng nghiệp vụ hay không. Nếu producer phát event sai, payload lỗi hoặc dữ liệu bị mã hóa bằng key sai, DR có thể nhận cùng dữ liệu lỗi.

Biện pháp:

- Schema validation và compatibility checks trước production.
- Event ID duy nhất và idempotency key để nhận diện duplicate/replay.
- Business validation và invariant checks ở consumer.
- Quarantine topic hoặc DLT có ACL/retention riêng.
- Immutable backup hoặc archive tách khỏi quyền ghi của application.
- Khả năng replay từ nguồn chuẩn sau khi sửa logic.
- Audit producer deployment và schema changes.

Nếu corruption đã được replicate, failover sang DR không sửa được dữ liệu. Cần xác định thời điểm cuối cùng còn tốt và phục hồi từ backup/immutable archive hoặc tái tạo event từ source of truth.

## 15. Kịch bản 5: credential compromise hoặc ransomware

Nếu credential của operator hoặc service bị lộ, attacker có thể xóa topic, thay ACL, phát dữ liệu giả hoặc làm gián đoạn replication. Nếu primary và DR dùng chung credential/quyền admin, attacker có thể phá cả hai nơi.

Thiết kế giảm blast radius:

- Principal riêng cho MM2 source và target; quyền chỉ đủ đọc nguồn/ghi đích.
- Application principal không có quyền quản trị cluster hoặc xóa topic.
- DR admin credential lưu trong secret manager độc lập.
- Backup/immutable archive không cho principal ứng dụng ghi/xóa.
- ACL thay đổi có audit và cảnh báo.
- KMS key và certificate có quyền riêng, không dùng chung secret không cần thiết.
- Tách network path quản trị khỏi data plane.

Khi nghi ngờ compromise:

1. Kích hoạt security incident và xác định principal/credential bị ảnh hưởng.
2. Fence credential và session bị lộ.
3. Đánh giá ACL, topic config, deletion, producer event và replication changes.
4. Bảo toàn audit log và evidence.
5. Cô lập DR/backup khỏi principal bị compromise.
6. Chọn recovery point cuối cùng được xác minh sạch.
7. Rotate credential, validate cluster và mới cho phép traffic.

Không promote một bản mirror nếu chưa xác minh dữ liệu đích không bị attacker replicate thay đổi phá hoại.

## 16. Kịch bản 6: MM2 hoặc network replication bị gián đoạn

Nếu primary vẫn hoạt động nhưng MM2 dừng, primary tiếp tục nhận record trong khi DR bị tụt lại. Không nên tự động failover sang DR vì nó có thể vi phạm RPO.

Trình tự:

1. Kiểm tra Connect worker, connector/task state và log.
2. Kiểm tra network, DNS, TLS/SASL, ACL source/target và quota.
3. Kiểm tra source/target topic tồn tại, partition mapping và storage.
4. Khôi phục connector/task và quan sát replication lag giảm.
5. Xác minh checkpoint và offset-sync tiếp tục cập nhật.
6. Phát canary event và xác nhận tới DR.
7. Chỉ đóng incident khi lag về trong ngân sách RPO.

Nếu lag vượt RPO trong thời gian dài, ghi nhận RPO breach và quyết định có throttle/pause producer, giảm scope ghi hoặc chấp nhận rủi ro theo business policy. Không tự động dừng toàn bộ production producer trừ khi policy yêu cầu.

## 17. Failback: quay về primary sau khi phục hồi

Failback thường khó hơn failover. Sau khi DR được promote, DR có thể đã nhận event mới mà primary cũ không có. Không thể đơn giản bật lại primary và chuyển DNS về.

Quy trình active-passive:

1. Giữ DR là nơi ghi chính sau khi dịch vụ được phục hồi.
2. Khôi phục primary cũ như một cluster độc lập, không cho producer ghi.
3. Kiểm tra metadata, version, broker capacity, topic configs, ACL, schema và dependencies.
4. Chọn hướng replicate dữ liệu mới từ DR về primary đã phục hồi.
5. Đảm bảo không có vòng lặp replication; cấu hình connector/filter/policy phù hợp.
6. Chờ dữ liệu và checkpoint bắt kịp, kiểm tra duplicate/gap.
7. Diễn tập consumer offset translation và xác minh target offsets.
8. Lập maintenance window, fence writer ở DR tại cutover point.
9. Chuyển producer sang primary đã đồng bộ.
10. Khởi động consumer, xác minh event đầu cuối rồi mới đánh dấu primary hoạt động bình thường.
11. Khôi phục hướng replication primary → DR và xác minh lại.

Không xóa dữ liệu DR hoặc đổi hướng replication trước khi xác định rõ source of truth. Nếu không cần quay về primary cũ, có thể giữ DR làm primary mới lâu dài và tái tạo cluster dự phòng khác.

## 18. Consumer offset, duplicate và exactly-once

Kafka exactly-once semantics có phạm vi trong một cluster và các transaction/partition được Kafka quản lý. MirrorMaker 2 không tạo một transaction atomic xuyên hai cluster. Khi failover, có thể xuất hiện duplicate hoặc một khoảng record cần replay do replication và checkpoint không đồng bộ đúng thời điểm.

Thiết kế consumer để chịu được replay:

- Dùng event ID ổn định xuyên replication.
- Ghi idempotency key vào database/outbox hoặc deduplication store.
- Commit offset sau khi side effect nghiệp vụ được xác nhận.
- Có thể replay một khoảng offset đã xác định.
- Theo dõi duplicate rate và business invariant.
- Với transaction consumer/producer, xác định lại transactional.id và producer identity ở DR; không chia sẻ identity đang active giữa hai cluster.

Không cam kết exactly-once end-to-end xuyên cluster chỉ bằng cách bật enable.idempotence=true hoặc processing.guarantee=exactly_once_v2. Đây là những cơ chế có phạm vi cụ thể, không phải giao dịch phân tán giữa hai Kafka clusters.

## 19. Kafka Connect và Kafka Streams trong DR

### Kafka Connect

Connector cần:

- Plugin/JAR tương thích và cùng version.
- Connector config, secret và external endpoint.
- Config, offset và status backing topics theo thiết kế triển khai.
- Quy trình ngăn hai connector cùng ghi side effect trùng trong failover.
- Offset/source position phù hợp với hệ thống ngoài Kafka.

Không tự động khởi chạy source connector ở cả primary và DR nếu source system không hỗ trợ active-active hoặc không có cơ chế deduplication. Với sink connector, tránh hai cluster cùng ghi một đích nếu không có idempotent sink.

Config/offset/status backing topics của Kafka Connect gắn với worker cluster và không nên được xem là đã được DR-ready chỉ vì MM2 đang replicate business topics. Chuẩn bị worker cluster, connector config, secret và source offsets theo quy trình riêng; không khởi động cùng một source connector ở hai nơi nếu có nguy cơ đọc trùng hoặc ghi side effect lặp.

### Kafka Streams

Kafka Streams có thể phục hồi state bằng cách đọc lại input và changelog/repartition topics. Trong DR:

- Replicate input topics và các changelog/repartition topics cần thiết theo thiết kế.
- Kiểm tra application.id, state directory và topology version.
- Xác định state store có thể rebuild hay cần snapshot riêng.
- Không để hai cluster cùng chạy cùng logical application và ghi side effect vào một database mà thiếu fencing/idempotency.
- Đo thời gian restore state để đưa vào RTO.

State store local không tự được MirrorMaker 2 sao chép. Changelog topic là nguồn phục hồi quan trọng nhưng không thay thế mọi yêu cầu backup của stateful application.

## 20. Bảo vệ DR cluster và backup

DR cluster cần bảo mật tương đương production:

- TLS/SASL và ACL least privilege.
- MM2 principal chỉ đọc topic nguồn và ghi resource đích cần thiết.
- Credential target tách khỏi primary admin credential.
- Audit log và alert độc lập.
- Disk encryption, backup và retention được kiểm tra.
- DR endpoint không public nếu không cần.
- Schema, KMS và secret có bản sao/khả năng truy cập ở region DR.

Backup khác replication:

| Replication | Backup |
|---|---|
| Giữ dữ liệu gần thời gian thực | Giữ bản sao theo thời điểm |
| Phục vụ failover nhanh | Phục vụ phục hồi lịch sử |
| Có thể replicate deletion/corruption | Có thể giữ bản sạch trước sự cố |
| Thường cùng schema và topic lifecycle | Có thể immutable/offline và retention dài |
| RPO phụ thuộc replication lag | RPO phụ thuộc lịch backup/archive |

Thiết kế DR tốt thường cần cả replication lẫn backup/immutable archive, đặc biệt với accidental deletion, ransomware và logical corruption.

## 21. DR drill và kiểm thử định kỳ

Không thể biết RPO/RTO thực tế chỉ từ sơ đồ kiến trúc. Cần diễn tập có đo thời gian và kiểm tra dữ liệu.

Các bài drill:

1. Tắt một broker và xác minh đây là sự cố nội bộ cluster, không failover nhầm.
2. Dừng MM2 connector có kiểm soát, đo lag tăng và thời gian bắt kịp.
3. Mô phỏng mất network giữa primary và DR.
4. Promote DR trong môi trường staging, kiểm tra offset translation và duplicate.
5. Fencing primary và chứng minh không còn write traffic.
6. Failback theo quy trình đã định.
7. Khôi phục topic đã xóa từ backup/immutable archive.
8. Kiểm tra credential compromise tabletop exercise.
9. Khởi chạy Kafka Connect/Streams ở DR và đo state recovery.

Mỗi drill phải ghi:

- RPO target và RPO observed.
- RTO target và RTO observed.
- Replication lag tại thời điểm failover.
- Số event duplicate, missing hoặc replayed.
- Consumer offset mapping accuracy.
- Business validation result.
- Các bước thủ công gây chậm và hành động tự động hóa.
- Owner và deadline cho gap được phát hiện.

## 22. Ví dụ tính ngân sách RPO và RTO

Giả sử hệ thống đặt:

- RPO target: 5 phút.
- RTO target: 30 phút.
- Heartbeat interval: 1 phút.
- Alert replication lag: 2 phút.

Trong một buổi drill, record mới nhất ở DR chậm hơn primary 90 giây khi sự cố bắt đầu. Thời gian xử lý:

| Giai đoạn | Thời gian |
|---|---:|
| Detect | 2 phút |
| Decision | 3 phút |
| Fence primary | 4 phút |
| Promote và kiểm tra DR | 5 phút |
| Offset translation và client cutover | 6 phút |
| Business validation | 4 phút |
| **Tổng RTO** | **24 phút** |

Kết quả drill:

- RPO observed: 90 giây, đạt mục tiêu 5 phút.
- RTO observed: 24 phút, đạt mục tiêu 30 phút.
- RTO còn 6 phút headroom; cần giữ lại cho biến động thực tế.

Đây là số minh họa cho cách tính, không phải hiệu năng mặc định của Kafka hoặc MirrorMaker 2. Mỗi tổ chức phải đo trên topology, tải và quy trình của mình.

## 23. Lab: dựng DR active-passive và diễn tập failover

### Bước 1: chuẩn bị hai cluster

Tạo primary và DR ở hai môi trường độc lập. Mỗi cluster có KRaft quorum, broker đủ capacity, listener bảo mật và topic orders.events. Không dùng chung storage directory hoặc cluster identity.

### Bước 2: tạo dữ liệu kiểm thử

Producer gửi event có eventId, occurredAt và sequence nghiệp vụ. Lưu một bản ghi nhận số event đã xác nhận ở primary để đối chiếu.

### Bước 3: cấu hình MM2

Chạy MM2 primary → DR. Theo dõi heartbeat, source/target record rate, checkpoint và replication lag. Xác nhận event canary xuất hiện ở DR.

### Bước 4: chạy consumer ở primary

Consumer group đọc topic primary và commit offset. Bật checkpoint/offset sync. Kiểm tra target có checkpoint tương ứng và ghi nhận độ trễ.

### Bước 5: mô phỏng outage

Dừng producer traffic tới primary và mô phỏng primary không còn khả dụng. Không để primary và DR cùng nhận ghi. Ghi lại record mới nhất đã replicate.

### Bước 6: promote DR

Fencing primary, dịch consumer offset sang target offset bằng checkpoint phù hợp, cập nhật producer endpoint và khởi động consumer trên DR. Gửi event canary mới và xác minh end-to-end.

### Bước 7: đo RPO/RTO

So sánh sequence/event ID cuối cùng ở primary và DR trước outage; đo thời gian từ incident start tới khi DR xử lý thành công event mới. Ghi duplicate, missing và replay.

### Bước 8: failback

Giữ DR là writer trong khi phục hồi primary. Replicate DR → primary, chờ bắt kịp, fencing DR tại cutover, chuyển endpoint và kiểm tra consumer offset.

### Bước 9: viết báo cáo drill

Ghi RPO/RTO thực tế, lag, lỗi offset translation, dependency chưa sẵn sàng và các cải tiến cần làm.

## 24. Checklist thiết kế và vận hành DR

### Thiết kế

- Có RPO/RTO riêng theo luồng nghiệp vụ.
- Primary và DR nằm trong failure domain độc lập.
- Có active-passive hoặc active-active decision rõ ràng.
- Replication scope bao phủ đúng topic và partition cần thiết.
- Topic config, schema, ACL, credential và dependency được chuẩn bị ở DR.
- Consumer offset translation có chiến lược và kiểm thử.
- Có fencing chống split-brain.
- Có backup/immutable archive ngoài replication.
- Có capacity để DR nhận production load.

### Khi vận hành bình thường

- MM2/replication connector/task khỏe.
- Replication lag nằm trong ngân sách RPO.
- Heartbeat và checkpoint được cập nhật.
- Target ISR và disk capacity đạt yêu cầu.
- Có alert khi lag, task failure, target unavailable hoặc checkpoint stale.
- Backup được kiểm tra restore định kỳ.

### Khi failover

- Incident được declare đúng thẩm quyền.
- RPO tại thời điểm sự cố đã được ước lượng.
- Primary được fence trước khi DR nhận ghi.
- Offset được translate, không copy số offset thô.
- Producer/consumer/Connect/Streams chuyển sang DR.
- Event canary và business invariant được xác minh.
- RPO/RTO thực tế được ghi lại.

### Khi failback

- DR tiếp tục là source of truth trong lúc primary phục hồi.
- Có replication ngược và loop prevention.
- Offset và dữ liệu đã bắt kịp.
- Có cutover point và fencing rõ ràng.
- Consumer, connector và stream state được xác minh.
- Hướng replication chuẩn được thiết lập lại sau cutover.

## 25. Ghi nhớ

| Khái niệm | Cần nhớ |
|---|---|
| RPO | Mức dữ liệu tối đa có thể mất |
| RTO | Thời gian tối đa để dịch vụ phục hồi |
| Active-passive | Một nơi ghi chính, DR standby |
| Active-active | Nhiều nơi ghi, cần conflict resolution |
| MirrorMaker 2 | Replicate record và checkpoint giữa Kafka clusters |
| Offset translation | Ánh xạ vị trí log, không copy raw offset |
| Fencing | Ngăn primary cũ tiếp tục ghi sau failover |
| Failback | Đồng bộ dữ liệu ngược và chuyển writer có kiểm soát |
| Backup | Bảo vệ trước logical deletion/corruption mà mirror có thể sao chép |
| DR drill | Đo RPO/RTO thực tế và phát hiện gap |

RPO/RTO chỉ có ý nghĩa khi được đo và diễn tập. MirrorMaker 2 giúp duy trì bản sao gần thời gian thực nhưng không thay thế fencing, offset translation, backup hay quy trình failover/failback. Hãy chọn kiến trúc theo giá trị dữ liệu, xác định source of truth tại mọi thời điểm và kiểm tra cả cluster lẫn luồng nghiệp vụ trước khi tuyên bố DR đã sẵn sàng.

## 26. Tài liệu tham khảo

- Apache Kafka – [MirrorMaker 2](https://kafka.apache.org/42/documentation/#georeplication)
- Apache Kafka – [MirrorMaker 2 Configuration](https://kafka.apache.org/42/documentation/#georeplication)
- Apache Kafka – [Kafka Connect](https://kafka.apache.org/42/documentation/#connect)
- Apache Kafka – [Consumer Configs](https://kafka.apache.org/42/configuration/consumer-configs/)
- Apache Kafka – [Operations and Monitoring](https://kafka.apache.org/42/operations/monitoring/)
