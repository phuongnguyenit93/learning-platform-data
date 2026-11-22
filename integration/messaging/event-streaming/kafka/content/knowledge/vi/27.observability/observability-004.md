# Under-replicated partition, offline partition và biến động ISR

Kafka lưu mỗi partition trên nhiều broker để chịu lỗi. Một partition có thể vẫn đọc/ghi được nhưng đã mất một phần replica dự phòng; cũng có thể rơi vào trạng thái không còn leader nên mọi request tới partition đó bị gián đoạn. Để vận hành cluster an toàn, cần theo dõi replica health, ISR và leader state thay vì chỉ nhìn broker process còn sống.

Ba tín hiệu quan trọng là under-replicated partition (URP), offline partition và ISR shrink/expand. URP cho biết một hay nhiều replica chưa theo kịp ISR; offline partition cho biết partition không có leader khả dụng; ISR biến động liên tục cho thấy replica đang chập chờn hoặc cluster thiếu ổn định. Chúng có mức độ ảnh hưởng khác nhau và cần runbook xử lý khác nhau.

## 1. Replication trong Kafka

Một topic được chia thành partition. Mỗi partition có một replica trên broker được chỉ định làm leader và các replica còn lại làm follower.

- **Leader replica:** nhận produce request và phục vụ fetch của consumer.
- **Follower replica:** fetch dữ liệu từ leader và duy trì bản sao của log.
- **Replica assignment:** danh sách broker lưu bản sao của partition.
- **Replication factor (RF):** số replica được chỉ định cho mỗi partition.
- **ISR (In-Sync Replicas):** tập replica được xem là đang đồng bộ với leader theo tiêu chí của Kafka.
- **Leader epoch:** số thế hệ leader dùng trong quá trình điều phối leader và bảo vệ log consistency.

Ví dụ partition có RF=3:

~~~mermaid
flowchart LR
    P[orders-0] --> L[Broker 1: Leader]
    P --> F1[Broker 2: Follower]
    P --> F2[Broker 3: Follower]
    L -->|Fetch replication| F1
    L -->|Fetch replication| F2
~~~

Nếu cả ba replica đang ở ISR, partition có ba bản sao đủ điều kiện tham gia quyết định durability theo cấu hình producer. Nếu follower tụt lại hoặc không còn đáp ứng tiêu chí đồng bộ, leader có thể loại replica đó khỏi ISR.

RF là số replica được gán; ISR là tập con replica hiện đang đồng bộ. Hai con số này không nhất thiết bằng nhau.

## 2. ISR và cách follower bắt kịp leader

Follower liên tục fetch dữ liệu từ leader. Khi follower đã theo kịp log và tiếp tục đáp ứng điều kiện hoạt động của broker, nó có thể được thêm vào ISR. Khi follower bị chậm hoặc không gửi fetch trong khoảng thời gian cho phép, leader có thể loại nó khỏi ISR.

Kafka sử dụng cấu hình broker replica.lag.time.max.ms để xác định khoảng thời gian follower có thể không tiến triển theo cơ chế replication trước khi bị xem là out of sync. Đây không phải cấu hình giới hạn số message lag như cơ chế cũ đã bị loại bỏ ở các phiên bản Kafka hiện đại.

Ví dụ:

| Replica | Broker | Vai trò | Trạng thái |
|---|---|---|---|
| Replica 0 | broker-1 | Leader | ISR |
| Replica 1 | broker-2 | Follower | ISR |
| Replica 2 | broker-3 | Follower | Out of ISR |

Trong ví dụ, RF=3 nhưng ISR chỉ có 2 replica. Partition vẫn có leader, nhưng khả năng chịu thêm một lỗi broker đã giảm.

### ISR không phải bản sao có offset bằng nhau mọi thời điểm

Follower có thể đang fetch dữ liệu và có một khoảng lag ngắn nhưng vẫn nằm trong ISR. ISR là tập replica được Kafka xem là đủ đồng bộ theo protocol và tiêu chí thời gian, không có nghĩa log end offset của mọi replica luôn bằng nhau tại từng millisecond.

Kafka dùng high watermark để xác định phần log đã được replicate đủ điều kiện cho consumer đọc theo isolation semantics. Với producer idempotent/transactional, còn có last stable offset và transaction marker. Không nên suy diễn ISR membership chỉ từ một lần đọc log end offset.

## 3. Under-replicated partition (URP)

Một partition là under-replicated khi số replica đang nằm trong ISR nhỏ hơn số replica được chỉ định cho partition.

~~~text
Replication factor = 3
Assigned replicas = [broker-1, broker-2, broker-3]
ISR              = [broker-1, broker-2]

URP = true
Leader vẫn hoạt động trên broker-1
~~~

URP thường không có nghĩa partition đã ngừng phục vụ. Leader vẫn có thể nhận request và consumer vẫn có thể đọc dữ liệu đã được commit theo high watermark. Tuy nhiên, partition đã mất một replica đồng bộ và có ít dư địa chịu lỗi hơn.

### Ảnh hưởng của URP

- Dự phòng dữ liệu giảm: còn ít bản sao trong ISR hơn replication factor.
- Nếu thêm broker/replica trong ISR gặp sự cố, partition có thể rơi dưới min ISR.
- Producer dùng acks=all có thể nhận lỗi nếu ISR thấp hơn min.insync.replicas.
- Follower lag có thể làm tăng thời gian phục hồi và độ trễ replication.
- URP kéo dài có thể báo hiệu broker, disk hoặc network có vấn đề.

URP tồn tại ngắn sau broker restart hoặc reassignment có thể là trạng thái phục hồi bình thường. URP kéo dài, tăng trên nhiều topic hoặc tập trung vào một broker cần được điều tra.

## 4. Offline partition

Partition offline là partition không có leader khả dụng. Trong output của kafka-topics --describe, leader thường được hiển thị là -1.

Ví dụ:

~~~text
Topic: payments.events
Partition: 2
Leader: -1
Replicas: 1,2,3
Isr: 2,3
~~~

Ví dụ trên cho thấy broker được chỉ định làm replica nhưng controller chưa có leader phục vụ partition. ISR có thể còn replica, nhưng việc bầu leader có thể đang chờ broker/controller phục hồi hoặc có ràng buộc khác. Nếu ISR rỗng và không cho phép unclean leader election, partition không thể tự bầu một replica ngoài ISR mà vẫn bảo toàn durability guarantee.

Offline partition nghiêm trọng hơn URP:

| Trạng thái | Có leader? | Đọc/ghi partition | Rủi ro chính |
|---|---|---|---|
| Healthy | Có | Bình thường | Dự phòng đủ theo ISR |
| URP | Có | Thường vẫn phục vụ | Giảm redundancy |
| ISR dưới min ISR | Có | Producer acks=all có thể bị từ chối; đọc vẫn có thể hoạt động | Không đủ replica cho write durability policy |
| Offline partition | Không | Không thể phục vụ bình thường | Mất availability của partition |

Offline partition có thể làm ứng dụng lỗi một phần nếu chỉ một số partition bị ảnh hưởng, hoặc làm toàn bộ topic ngừng hoạt động nếu mọi partition đều offline.

## 5. Under-min-ISR khác URP

URP so sánh ISR với replication factor. Under-min-ISR so sánh ISR với ngưỡng min.insync.replicas của topic/broker.

Ví dụ RF=3 và min.insync.replicas=2:

| ISR size | URP? | Under min ISR? | Ghi với acks=all |
|---:|---|---|---|
| 3 | Không | Không | Có thể thành công |
| 2 | Có | Không | Có thể thành công |
| 1 | Có | Có | Bị từ chối |
| 0 | Có và không có leader khả dụng | Có | Không thể ghi |

Một partition có thể là URP nhưng vẫn đáp ứng min ISR. Đây là trạng thái degraded nhưng producer acks=all vẫn có thể ghi thành công.

Ngược lại, khi ISR thấp hơn min ISR, Kafka từ chối produce với acks=all để bảo vệ durability policy. Consumer vẫn có thể đọc dữ liệu đã được commit; producer có thể nhận NotEnoughReplicas hoặc NotEnoughReplicasAfterAppend tùy thời điểm và phiên bản.

## 6. Quan hệ giữa RF, acks=all và min.insync.replicas

Ba cấu hình này phối hợp để quyết định mức durability:

- RF xác định số bản sao được chỉ định.
- acks=all yêu cầu broker chờ các replica hiện nằm trong ISR xác nhận theo semantics của producer request.
- min.insync.replicas đặt ngưỡng ISR tối thiểu để chấp nhận produce với acks=all.

Ví dụ cấu hình phổ biến cho dữ liệu cần durability:

~~~properties
# Broker hoặc topic-level configuration
default.replication.factor=3
min.insync.replicas=2

# Producer
acks=all
enable.idempotence=true
~~~

Với RF=3 và min ISR=2, cluster có thể chịu một replica rời ISR mà producer acks=all vẫn ghi được. Nếu ISR giảm còn 1, producer bị từ chối thay vì chấp nhận ghi với mức dự phòng thấp hơn policy.

min.insync.replicas không ép Kafka giữ ISR luôn có đủ số lượng. Nó là ngưỡng kiểm tra khi ghi với acks=all. ISR vẫn có thể shrink do broker lỗi; producer mới là nơi nhìn thấy write failure theo policy.

### acks=all không có nghĩa mọi replica được chỉ định đều xác nhận

acks=all chờ toàn bộ ISR tại thời điểm xử lý produce, không chờ replica đã bị loại khỏi ISR. Nếu RF=3 nhưng ISR=2 và min ISR=2, produce vẫn có thể thành công khi hai replica trong ISR xác nhận.

Do đó, theo dõi URP và under-min-ISR riêng biệt. Chỉ theo dõi lỗi producer có thể bỏ sót giai đoạn cluster đã mất redundancy nhưng vẫn ghi được.

## 7. Unclean leader election và nguy cơ mất dữ liệu

Nếu mọi replica trong ISR đều không khả dụng, Kafka có thể được cấu hình để bầu một replica ngoài ISR làm leader thông qua unclean leader election. Replica ngoài ISR có thể thiếu một phần dữ liệu đã được leader cũ xác nhận.

~~~properties
unclean.leader.election.enable=false
~~~

Khi tắt unclean election, Kafka ưu tiên durability: partition có thể ở trạng thái offline cho tới khi một replica trong ISR quay lại. Khi bật, Kafka có thể ưu tiên availability bằng cách bầu replica ngoài ISR, nhưng dữ liệu đã được xác nhận trước đó có thể bị mất.

Không bật unclean election như cách xử lý mặc định cho offline partition. Trước khi thay đổi:

1. Xác định broker nào còn dữ liệu replica.
2. Kiểm tra ISR cuối cùng và log/leader epoch.
3. Xác định mức độ chấp nhận mất dữ liệu của topic.
4. Xem xét khôi phục broker/disk gốc trước.
5. Chỉ thực hiện election ngoài ISR theo quy trình incident có phê duyệt và hiểu rõ hậu quả.

Với dữ liệu tài chính, đơn hàng hoặc event không thể tái tạo, durability thường quan trọng hơn việc đưa partition online bằng mọi giá.

## 8. ISR shrink và ISR expand

ISR shrink xảy ra khi replica bị loại khỏi ISR. ISR expand xảy ra khi replica bắt kịp và được thêm lại.

Một lần shrink sau broker restart có thể bình thường. Nhưng shrink/expand liên tục trong thời gian ngắn là dấu hiệu replica đang dao động quanh ngưỡng đồng bộ.

~~~mermaid
stateDiagram-v2
    [*] --> InSync
    InSync --> OutOfSync: Follower lag / fetch timeout
    OutOfSync --> CatchingUp: Broker hoặc network phục hồi
    CatchingUp --> InSync: Replica bắt kịp leader
    CatchingUp --> OutOfSync: Tiếp tục bị tụt lại
~~~

### Nguyên nhân ISR shrink

- Broker follower bị restart, crash hoặc mất heartbeat/fetch.
- Network packet loss, latency cao hoặc connection reset giữa leader và follower.
- Disk chậm, lỗi filesystem hoặc I/O queue tăng.
- CPU saturation, GC pause hoặc request handler bị nghẽn.
- Follower fetcher không theo kịp tốc độ ghi của leader.
- Broker bị throttling hoặc đang thực hiện partition reassignment.
- Leader có tải cao, follower không fetch đủ nhanh.
- Broker mất kết nối tới controller hoặc cluster có metadata/control-plane instability.

### Nguyên nhân ISR expand

- Broker follower khởi động lại và bắt kịp log.
- Network hoặc disk đã phục hồi.
- Reassignment/recovery hoàn tất.
- Follower fetcher xử lý hết backlog.

ISR expand là tín hiệu tốt nếu xảy ra sau phục hồi. Nếu expand rồi shrink lặp lại, cần tìm nguyên nhân gốc thay vì chỉ tăng timeout.

## 9. Replica lag và replica.lag.time.max.ms

replica.lag.time.max.ms là cấu hình broker quan trọng ảnh hưởng việc follower bị loại khỏi ISR khi không fetch tiến triển trong khoảng thời gian cho phép.

Ví dụ:

~~~properties
replica.lag.time.max.ms=30000
~~~

Giá trị trên chỉ minh họa. Không nên tăng timeout ngay khi thấy URP. Timeout quá nhỏ có thể làm replica bị loại khỏi ISR khi có jitter ngắn; timeout quá lớn có thể giữ replica không thực sự theo kịp trong ISR lâu hơn, làm ảnh hưởng thời gian phát hiện degraded replica.

Trước khi thay đổi, đo:

- Follower fetch latency và fetch rate.
- Network RTT, packet loss và retransmission.
- Disk read/write latency trên follower.
- CPU utilization và GC pause.
- Replication throughput so với produce throughput.
- Khoảng thời gian broker restart/rebalance.

Các cấu hình fetch như replica.fetch.max.bytes, replica.fetch.response.max.bytes và số replica fetcher có thể ảnh hưởng throughput, nhưng chỉ điều chỉnh sau khi xác định bottleneck. Tăng buffer không sửa được disk hỏng hoặc network mất gói.

## 10. Metric quan trọng cho replication health

Kafka broker cung cấp JMX metrics để quan sát replica và partition state. Tên ObjectName chính xác và cách export có thể phụ thuộc Kafka version/monitoring agent; cần xác minh trên broker đang chạy.

| Metric thường dùng | Ý nghĩa | Cảnh báo khi |
|---|---|---|
| UnderReplicatedPartitions | Số partition có ISR nhỏ hơn replica assignment trên broker | Tăng hoặc khác 0 kéo dài |
| OfflinePartitionsCount | Số partition offline được controller quan sát | Lớn hơn 0 |
| UnderMinIsrPartitionCount | Số partition có ISR thấp hơn min ISR | Lớn hơn 0 |
| IsrShrinksPerSec | Tốc độ ISR shrink | Tăng đột biến hoặc duy trì cao |
| IsrExpandsPerSec | Tốc độ ISR expand | Biến động cao cùng shrink |
| PartitionCount | Số partition trên broker | Phân bố lệch bất thường |
| LeaderCount | Số leader partition trên broker | Mất cân bằng hoặc thay đổi đột ngột |
| ActiveControllerCount | Broker/controller đang active | Không có đúng một active controller trong mô hình controller broker phù hợp |

Các metric thường được quan sát qua JMX ObjectName như:

~~~text
kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions
kafka.server:type=ReplicaManager,name=IsrShrinksPerSec
kafka.server:type=ReplicaManager,name=IsrExpandsPerSec
kafka.controller:type=KafkaController,name=OfflinePartitionsCount
~~~

Tên metric và scope có thể thay đổi theo release. Một số metric là per-broker gauge; khi tổng hợp cluster, không cộng tùy tiện các gauge bị lặp hoặc phản ánh cùng partition trên nhiều broker. Kiểm tra exporter mapping và xác định rõ dashboard đang hiển thị max, sum hay broker-local value.

### Đo cả nguyên nhân bên dưới

URP là triệu chứng. Cần ghép với:

- RequestHandlerAvgIdlePercent và NetworkProcessorAvgIdlePercent.
- RequestQueueSize và response queue.
- Disk latency, utilization, IOPS và free space.
- Network throughput, retransmit và connection errors.
- JVM GC pause, heap pressure và thread count.
- Replica fetcher metrics và replication byte rate.
- Broker restart, log directory failure và controller event.

Không dùng một metric URP riêng lẻ để kết luận network hoặc disk là nguyên nhân.

## 11. Alerting theo mức độ ảnh hưởng

Một alert policy nên phân biệt mất availability với giảm redundancy:

| Mức | Điều kiện ví dụ | Hành động |
|---|---|---|
| Critical | OfflinePartitionsCount > 0 | On-call xử lý ngay, xác định topic/partition và leader |
| Critical | ISR dưới min ISR kéo dài, producer nhận NotEnoughReplicas | Kiểm tra replica availability và write impact |
| Warning | URP > 0 liên tục qua nhiều lần scrape | Điều tra broker/follower gây lag |
| Warning | ISR shrink rate tăng đột biến | Kiểm tra network, disk, CPU và restart |
| Info | ISR expand sau recovery | Theo dõi đến khi URP về 0 |
| Warning | URP tập trung ở một broker/rack | Điều tra broker hoặc rack/network domain |

Ngưỡng thời gian cần dựa trên SLO và chu kỳ scrape. Offline partition nên cảnh báo gần như tức thời; URP có thể có grace ngắn để tránh alert noise trong rolling restart/reassignment có kế hoạch.

Alert nên chứa topic, partition, leader broker, replica list, ISR list, broker/rack và thời điểm bắt đầu. Nếu metric chỉ là cluster-wide gauge, dashboard cần drill-down bằng topic describe hoặc exporter có label theo partition.

## 12. Kiểm tra nhanh bằng Kafka CLI

Mô tả topic và replica state:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders.events
~~~

Output ví dụ:

~~~text
Topic: orders.events
Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
Partition: 1  Leader: 2  Replicas: 2,3,1  Isr: 2,3
Partition: 2  Leader: 3  Replicas: 3,1,2  Isr: 3,1
~~~

Partition 1 và 2 là URP vì ISR có hai broker trong khi RF=3. Chúng vẫn có leader. Nếu leader hiển thị -1, partition đang offline.

Kiểm tra cấu hình topic:

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --describe \
  --all
~~~

Xác minh min.insync.replicas có thể được đặt ở broker default hoặc override ở topic. Không chỉ đọc server.properties vì topic-level config có thể ghi đè giá trị mặc định.

### Kiểm tra broker và log directory

Kết hợp topic describe với broker logs, broker health endpoint/metrics và trạng thái disk. Cần xác định:

- Broker chứa replica có đang online không.
- Log directory có lỗi hoặc bị offline không.
- Replica fetcher có đang hoạt động không.
- Broker có vừa restart hoặc bị rolling update không.
- Leader/follower có nằm ở cùng rack hoặc failure domain không.

## 13. Phân biệt replication data-plane và KRaft metadata quorum

Trong KRaft, controller quorum dùng Raft để replicate metadata của cluster. Nó khác với ISR replication của data partition.

| Data partition replication | KRaft metadata quorum |
|---|---|
| Replicate record log của topic partition | Replicate cluster metadata log |
| Leader là partition leader | Leader là active controller trong quorum |
| Follower được theo dõi qua ISR | Voter/observer theo Raft quorum |
| URP phản ánh replica data không đủ ISR | Quorum lag/leader state phản ánh metadata replication |
| Offline partition làm một partition dữ liệu không có leader | Mất quorum có thể làm cluster không thể tiến hành thay đổi metadata |

Một cluster có thể có data partition URP nhưng metadata quorum vẫn khỏe. Ngược lại, metadata quorum có vấn đề có thể làm việc quản lý leader/partition và cấu hình cluster bị ảnh hưởng dù một số data partition hiện vẫn phục vụ.

Không dùng lệnh describe metadata quorum để thay thế topic describe khi điều tra URP. Cần theo dõi cả hai plane.

## 14. Nguyên nhân URP theo failure domain

### Broker hoặc JVM

- Process crash, OOM hoặc restart liên tục.
- GC pause kéo dài làm fetch request đến muộn.
- CPU throttling hoặc thread pool bão hòa.
- File descriptor hoặc connection limit.

### Disk và filesystem

- Disk latency cao khiến follower append chậm.
- Disk đầy, log directory offline hoặc filesystem lỗi.
- IOPS bị tranh chấp với workload khác.
- Rebuild/recovery tạo I/O lớn.

### Network

- Packet loss, retransmission hoặc latency tăng.
- Network interface saturation.
- Firewall/connection timeout hoặc routing lỗi.
- Cross-rack bandwidth không đủ.

### Cluster workload

- Produce throughput tăng đột biến.
- Một số partition có hot leader.
- Reassignment chạy đồng thời với peak traffic.
- Replication throttling đặt quá thấp hoặc không cân đối.
- Broker có quá nhiều replica/partition so với capacity.

Hãy phân loại theo phạm vi: một partition, một broker, một rack hay toàn cluster. Nếu nhiều partition có follower trên cùng broker cùng shrink, nguyên nhân có thể nằm ở broker đó thay vì từng topic.

## 15. Recovery khi URP

Mục tiêu là đưa replica về ISR mà không làm giảm thêm durability.

Quy trình:

1. Xác định partition URP và broker chứa replica bị thiếu khỏi ISR.
2. Kiểm tra broker process, log directory, disk và network.
3. Xác định follower lag do throughput hay do broker không hoạt động.
4. Khôi phục broker hoặc dependency gây lỗi.
5. Theo dõi follower fetch và ISR expand.
6. Xác minh ISR bằng topic describe và metric.
7. Chờ URP về 0 và kiểm tra producer error rate.
8. Xác minh không có partition khác bắt đầu URP do recovery làm quá tải.

Không restart đồng loạt mọi broker khi chỉ một follower bị chậm. Không xóa log directory hoặc replica data để ép follower bắt đầu lại trừ khi đã có kế hoạch recovery chính xác; thao tác sai có thể làm mất bản sao tốt nhất còn lại.

### Nếu follower bắt kịp chậm

- Giảm tải hoặc dời batch workload gây I/O contention.
- Xác minh network throughput và packet loss.
- Kiểm tra replica fetcher errors.
- Điều chỉnh replication throttling nếu đang reassignment.
- Cân nhắc capacity hoặc partition placement.
- Chỉ thay replica.lag.time.max.ms sau khi đo nguyên nhân và đánh giá trade-off.

## 16. Recovery khi offline partition

Offline partition cần xử lý như incident availability và durability.

1. Xác định partition offline, assigned replicas, ISR cuối cùng và leader epoch từ log/metadata có sẵn.
2. Kiểm tra broker nào đang chứa replica trong ISR cuối cùng.
3. Ưu tiên đưa broker/disk chứa replica trong ISR trở lại.
4. Kiểm tra controller/quorum và broker registration nếu broker đã khởi động nhưng partition chưa có leader.
5. Quan sát controller log và broker log để tìm election failure hoặc log directory error.
6. Khi broker phục hồi, xác minh leader được bầu từ ISR và partition online.
7. Nếu không còn replica ISR khả dụng, dừng và đánh giá backup/replica ngoài ISR cùng mức chấp nhận mất dữ liệu.

Không bật unclean leader election hoặc xóa dữ liệu replica chỉ để làm leader khác xuất hiện. Nếu buộc phải bầu replica ngoài ISR, cần incident owner chấp thuận, ghi lại dữ liệu có nguy cơ mất và chuẩn bị reconciliation từ nguồn nghiệp vụ.

## 17. Partition reassignment và throttling

Reassignment di chuyển replica từ broker này sang broker khác. Nó thường được dùng để:

- Thay broker lỗi.
- Cân bằng số partition/leader.
- Cân bằng disk usage.
- Thay đổi rack placement.
- Tăng hoặc giảm replication factor theo kế hoạch.

Quy trình cơ bản dùng kafka-reassign-partitions:

~~~bash
# Xem trạng thái reassignment
kafka-reassign-partitions.sh \
  --bootstrap-server kafka-1:9092 \
  --reassignment-json-file reassignment.json \
  --verify
~~~

Khi reassignment đang chạy, theo dõi replication throughput và URP. Có thể dùng throttling để tránh chiếm hết network/disk của broker, nhưng throttle quá thấp kéo dài thời gian URP; không throttle có thể làm production traffic bị ảnh hưởng.

Thực hiện reassignment:

~~~bash
kafka-reassign-partitions.sh \
  --bootstrap-server kafka-1:9092 \
  --reassignment-json-file reassignment.json \
  --execute
~~~

Đây là ví dụ cú pháp; JSON reassignment phải được tạo và review theo kế hoạch. Không tự sinh JSON chỉ từ output rút gọn. Sau khi verify hoàn tất, kiểm tra RF, replica placement, ISR và leader balance.

### Rack awareness

Nếu broker.rack được cấu hình đúng, Kafka có thể phân bố replica qua các rack/failure domain khác nhau. RF=3 trên ba broker cùng một rack không bảo vệ được khi cả rack mất điện/network.

Kiểm tra rack placement khi tạo topic và reassignment. Thay đổi broker.rack có thể ảnh hưởng placement trong các lần assignment/reassignment tiếp theo; nó không tự di chuyển replica đang tồn tại.

## 18. Tác động tới producer và consumer

### Producer

Producer acks=all có thể gặp NotEnoughReplicas hoặc NotEnoughReplicasAfterAppend khi ISR thấp hơn min.insync.replicas hoặc thay đổi trong lúc request. Producer cần retry theo policy và phân biệt lỗi transient với lỗi cấu hình/durability.

Không đổi acks từ all sang 1 để làm lỗi biến mất nếu chưa được chấp thuận thay đổi durability. acks=1 có thể xác nhận sau khi leader ghi local, trước khi follower replicate; leader crash có thể làm mất record đã được xác nhận.

### Consumer

URP không nhất thiết làm consumer dừng ngay. Consumer thường đọc từ leader và dữ liệu được phục vụ theo high watermark/isolation level. Offline partition làm consumer không thể fetch partition đó cho tới khi có leader.

Consumer lag có thể tăng trong thời gian leader unavailable hoặc broker quá tải. Khi phục hồi, lag có thể giảm chậm nếu throughput xử lý không đủ hoặc reassignment đang chiếm tài nguyên.

### Transactions

Transactional producer và read_committed consumer có thêm transaction boundary và last stable offset. URP/leader election có thể ảnh hưởng khả năng commit transaction và tiến độ consumer. Khi điều tra, xem cả producer transaction errors, coordinator health và partition replication; không quy mọi lỗi transaction về ISR.

## 19. Ví dụ dashboard và alert logic

Một dashboard replication health nên có:

| Panel | Chiều quan sát |
|---|---|
| URP count | Cluster, broker, topic |
| Offline partition count | Cluster và topic |
| Under-min-ISR count | Cluster và topic |
| ISR shrink/expand rate | Theo thời gian và broker |
| Replica fetch latency/bytes | Leader/follower broker |
| Broker disk latency/free space | Theo log directory |
| Network throughput/errors | Theo interface/rack |
| Producer NotEnoughReplicas | Theo client/topic |
| Consumer lag | Theo group/topic/partition |
| Reassignment progress | Theo partition/broker |

Ví dụ logic alert dạng mô tả:

~~~text
CRITICAL: offline_partition_count > 0
WARNING: under_replicated_partitions > 0 for 5m
CRITICAL: under_min_isr_partition_count > 0 for 1m
WARNING: isr_shrinks_per_sec elevated for 3m
WARNING: producer_not_enough_replicas rate > baseline
~~~

Đây là pseudo-rule, không phải PromQL dùng trực tiếp. Tên metric và label phụ thuộc JMX exporter/Prometheus recording rules. Khi viết rule thực tế, xác minh metric đã được export và tránh cộng trùng broker-local gauges.

## 20. Bài thực hành: tạo và phục hồi URP trong lab

Tạo cluster lab có ba broker và topic RF=3:

1. Tạo topic orders.events với ba partition, replication factor 3.
2. Dùng kafka-topics --describe để xác minh leader, replicas và ISR đủ ba broker.
3. Dừng một follower broker trong môi trường lab.
4. Quan sát ISR shrink và URP tăng trong JMX/dashboard.
5. Kiểm tra producer acks=all với min.insync.replicas=2 vẫn có thể ghi khi ISR còn hai.
6. Dừng thêm một broker để ISR còn một; quan sát producer bị NotEnoughReplicas khi min ISR là hai.
7. Khởi động broker follower và quan sát ISR expand sau khi bắt kịp.
8. Theo dõi disk/network/replica fetch metrics trong quá trình catch-up.
9. Tạo một tình huống offline partition có kiểm soát và quan sát leader=-1.
10. Khôi phục broker thuộc ISR cuối cùng; xác minh leader được bầu và partition online.
11. Chạy reassignment trong lab, quan sát throttling và URP trong quá trình copy.
12. Đối chiếu data partition state với KRaft metadata quorum state.

Chỉ thực hiện dừng broker và fault injection trên cluster lab. Không dùng lệnh dừng broker hoặc thay đổi unclean leader election trên production để tái tạo bài học.

## 21. Checklist vận hành

- Theo dõi URP, offline partitions và under-min-ISR riêng biệt.
- Theo dõi ISR shrink/expand rate và thời gian URP tồn tại.
- Đặt RF phù hợp với failure domain và rack awareness.
- Chọn min.insync.replicas theo durability requirement.
- Dùng acks=all khi cần broker xác nhận theo ISR.
- Giữ unclean.leader.election.enable=false nếu ưu tiên durability và chỉ thay đổi theo incident decision.
- Theo dõi replica fetch, disk, network, CPU, GC và broker restart.
- Kiểm tra topic-level override của min.insync.replicas.
- Có runbook khôi phục follower và offline partition.
- Không xóa replica data hoặc bật unclean election tùy tiện.
- Theo dõi reassignment/throttling và xác minh sau khi hoàn tất.
- Phân biệt data partition ISR với KRaft metadata quorum.
- Cảnh báo producer NotEnoughReplicas và consumer lag cùng replication metrics.
- Kiểm thử recovery trong lab và ghi lại thời gian catch-up thực tế.

## 22. Những nhầm lẫn thường gặp

- **URP nghĩa là partition offline:** URP vẫn có thể có leader; offline partition là không có leader khả dụng.
- **ISR luôn bằng replication factor:** ISR có thể nhỏ hơn RF khi follower bị loại khỏi tập đồng bộ.
- **acks=all chờ mọi replica được gán:** nó chờ các replica trong ISR theo semantics của request.
- **min.insync.replicas giữ ISR không bao giờ giảm:** nó đặt ngưỡng chấp nhận write với acks=all, không ngăn broker loại follower.
- **URP luôn làm producer fail:** nếu ISR vẫn đạt min ISR, producer acks=all vẫn có thể ghi.
- **Under-min-ISR giống offline:** partition có thể còn leader nhưng không đủ ISR để chấp nhận write theo policy.
- **Tăng replica.lag.time.max.ms luôn tốt:** timeout lớn hơn có thể trì hoãn phát hiện follower không theo kịp.
- **ISR expand chứng minh cluster đã ổn định:** cần quan sát shrink/expand, lag và broker resource sau phục hồi.
- **Unclean election là cách chữa offline partition an toàn:** bầu replica ngoài ISR có thể làm mất dữ liệu đã xác nhận.
- **KRaft quorum và partition ISR là một:** chúng replicate hai loại log khác nhau.
- **Consumer lag thấp nghĩa là replication khỏe:** consumer progress không thay thế replica health.
- **Chỉ cần theo dõi broker process:** broker sống vẫn có thể có disk/network/replication bottleneck.

Under-replicated partition cho biết Kafka đang mất một phần redundancy nhưng có thể vẫn phục vụ qua leader. Offline partition cho biết không có leader khả dụng và partition bị gián đoạn. ISR shrink/expand giúp nhận ra replica instability trước khi sự cố trở nên nghiêm trọng. Vận hành tốt cần kết hợp các metric này với min ISR, producer errors, disk/network health và runbook phục hồi; ưu tiên đưa replica trong ISR trở lại thay vì bầu replica ngoài ISR khi chưa đánh giá rủi ro mất dữ liệu.
