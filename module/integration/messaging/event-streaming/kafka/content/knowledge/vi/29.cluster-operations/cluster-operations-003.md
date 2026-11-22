# Thêm broker và chuyển replica có kiểm soát

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này hướng dẫn mở rộng Kafka cluster bằng cách thêm broker mới, sau đó phân phối lại replica theo từng đợt có kiểm soát để cải thiện dung lượng, khả năng song song và cân bằng tải.

Thêm một broker chỉ làm cluster có thêm năng lực lưu trữ và xử lý request. Kafka không tự động chuyển toàn bộ replica cũ sang broker mới ngay khi broker tham gia cluster. Muốn sử dụng dung lượng mới, người vận hành cần lập kế hoạch partition reassignment, giữ nguyên replication factor theo mục tiêu, theo dõi ISR và throttle tốc độ sao chép. Một đợt mở rộng tốt phải kết thúc với replica phân bố hợp lý, không có partition offline, ISR ổn định và client vẫn đáp ứng SLO.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận biết khi nào cần thêm broker và khi nào cần xử lý bottleneck khác.
- Phân biệt broker, partition, replica, leader, follower và ISR.
- Giải thích vì sao thêm broker không tự cân bằng dữ liệu hiện có.
- Kiểm tra cluster health và capacity trước khi mở rộng.
- Chuẩn bị broker mới với node identity, listener, storage, rack và security phù hợp.
- Phân biệt broker-only node với combined broker/controller trong KRaft.
- Khởi động broker mới và xác minh broker đã đăng ký trong cluster.
- Tạo kế hoạch replica reassignment từ danh sách topic và broker mục tiêu.
- Thực hiện reassignment theo từng batch với replication throttle.
- Theo dõi ISR, under-replicated partition, disk, network và request latency.
- Kiểm tra leader distribution và rack awareness sau reassignment.
- Xử lý reassignment bị chậm, lỗi hoặc broker mất kết nối.
- Lập kế hoạch rollback và chỉ loại bỏ broker cũ khi đã di chuyển hết replica.
- Viết runbook mở rộng cluster có thể lặp lại và kiểm toán.

## 2. Khi nào nên thêm broker?

Thêm broker phù hợp khi cluster thiếu capacity bền vững hoặc cần tăng khả năng phân phối partition. Tuy nhiên, không phải mọi vấn đề hiệu năng đều giải quyết bằng cách thêm broker.

Các tín hiệu có thể cho thấy cần mở rộng:

- Disk usage trên các broker tiến gần ngưỡng vận hành.
- Ingress/egress network cao kéo dài trên một số broker hoặc rack.
- CPU và request handler saturation xuất hiện đồng thời với throughput tăng.
- Replica placement không còn đủ headroom để chịu broker failure hoặc reassignment.
- Partition leader hoặc replica bị tập trung quá nhiều trên một nhóm broker.
- Consumer/producer workload tăng và cluster không còn dư năng lực.
- Cần thêm fault domain hoặc rack để đáp ứng yêu cầu availability.

Trước khi quyết định, loại trừ các nguyên nhân khác:

| Triệu chứng | Có thể cần xử lý trước khi thêm broker |
|---|---|
| Một partition nóng, các broker khác nhàn | Key skew, partition design hoặc hot key |
| Consumer lag tăng nhưng broker còn nhiều headroom | Consumer code, downstream database/API hoặc concurrency |
| Producer p99 tăng do batch/serialization | Producer config, compression hoặc client CPU |
| Một broker đầy disk do replica placement lệch | Reassignment có thể đủ, chưa chắc cần tăng tổng số broker |
| Network cao do nhiều consumer group | Consumer traffic pattern, compression hoặc network sizing |
| Request latency tăng do GC hoặc CPU serialization | JVM, heap, compression codec và workload |
| ISR thường xuyên shrink | Disk/network instability, broker health hoặc replica fetcher |

Không thêm broker chỉ để che một bottleneck trong ứng dụng. Broker mới cũng tạo thêm chi phí vận hành, monitoring, security, patching và capacity planning.

## 3. Các khái niệm cần nắm

Một topic được chia thành partition. Mỗi partition có một bản sao leader và có thể có nhiều follower replica theo replication factor.

- **Broker:** một Kafka server tham gia cluster và lưu trữ hoặc phục vụ partition replica.
- **Partition:** đơn vị lưu trữ log, ordering và phân phối tải.
- **Replica:** bản sao của một partition trên một broker.
- **Leader replica:** replica nhận produce request và phục vụ read theo cấu hình.
- **Follower replica:** replica fetch dữ liệu từ leader để đồng bộ.
- **ISR:** tập replica đang đồng bộ đủ điều kiện được xem là in-sync.
- **Replication factor (RF):** số replica được cấu hình cho mỗi partition.
- **Preferred replica:** replica đứng đầu danh sách replica assignment, thường là ứng viên leader ưu tiên.
- **Partition reassignment:** thay đổi danh sách broker giữ replica của partition.
- **Rack awareness:** phân phối replica qua các rack hoặc fault domain để giảm rủi ro mất nhiều replica cùng lúc.

Ví dụ một partition có RF=3:

~~~text
Topic orders, partition 0
  Leader: broker 1
  Followers: broker 2, broker 3
  ISR: broker 1, broker 2, broker 3
~~~

Sau khi thêm broker 4, partition trên vẫn có thể nằm nguyên trên broker 1, 2 và 3. Broker 4 chưa giữ replica nào cho partition này cho đến khi có reassignment.

### 3.1. RF, min.insync.replicas và ISR

Replication factor xác định số replica được gán, còn ISR phản ánh replica đang theo kịp leader. Hai giá trị này không giống nhau.

Ví dụ:

- RF=3.
- min.insync.replicas=2.
- acks=all.

Trong điều kiện bình thường, producer yêu cầu acknowledgement từ toàn bộ ISR hiện tại và broker chỉ chấp nhận ghi khi số ISR đáp ứng min.insync.replicas. Nếu ISR giảm dưới ngưỡng, produce request có thể thất bại thay vì xác nhận một write không đạt durability policy.

Không giảm min.insync.replicas hoặc đổi acks chỉ để reassignment chạy nhanh hơn. Mở rộng cluster không phải lý do để hạ yêu cầu durability.

### 3.2. Reassignment không đồng nghĩa tăng partition count

Reassignment đổi broker giữ replica của các partition hiện có. Nó không tự tạo partition mới và không đổi key-to-partition mapping.

Tăng partition count là một thay đổi khác. Với keyed records, tăng partition có thể làm key được route sang partition khác trong tương lai và ảnh hưởng ordering theo key. Chỉ tăng partition khi có thiết kế riêng và đánh giá tương thích consumer.

## 4. Mở rộng cluster theo từng giai đoạn

Một quy trình an toàn có thể chia thành năm giai đoạn:

~~~mermaid
flowchart TD
    A[Đo capacity và xác định mục tiêu] --> B[Chuẩn bị broker mới]
    B --> C[Join cluster và xác minh health]
    C --> D[Lập kế hoạch replica reassignment]
    D --> E[Execute theo batch và throttle]
    E --> F[Verify ISR, disk, leader và client SLO]
    F --> G{Cluster ổn định?}
    G -->|No| H[Pause/rollback theo runbook]
    G -->|Yes| I[Đóng change và cập nhật inventory]
~~~

Không gộp thêm broker, đổi replication factor, tăng partition count và thay security config vào cùng một change nếu không cần thiết. Tách thay đổi giúp xác định nguyên nhân khi có sự cố và giảm phạm vi rollback.

## 5. Preflight: kiểm tra cluster trước khi thêm broker

Trước khi thay đổi, lưu lại trạng thái cluster và xác nhận cluster đang khỏe.

### 5.1. Kiểm tra broker và topic

Liệt kê topic:

~~~bash
kafka-topics.sh --bootstrap-server broker-1.internal:9092 --list
~~~

Mô tả topic quan trọng:

~~~bash
kafka-topics.sh --bootstrap-server broker-1.internal:9092 --describe --topic orders
~~~

Kiểm tra partition unavailable và under-replicated nếu phiên bản CLI hỗ trợ:

~~~bash
kafka-topics.sh --bootstrap-server broker-1.internal:9092 --describe --unavailable-partitions
kafka-topics.sh --bootstrap-server broker-1.internal:9092 --describe --under-replicated-partitions
~~~

Ghi nhận:

- Broker ID và trạng thái từng broker.
- Số partition leader/replica trên mỗi broker.
- Replication factor theo topic.
- ISR size và partition đang under-replicated.
- Offline partition.
- Disk usage theo log directory.
- Consumer lag, produce/fetch latency và throughput.
- Controller quorum health nếu cluster dùng KRaft.

Không bắt đầu reassignment quy mô lớn khi cluster đang có offline partition, ISR liên tục shrink hoặc disk gần đầy. Khôi phục health hiện tại trước để không cộng thêm replication traffic vào một cluster đã suy yếu.

### 5.2. Kiểm tra KRaft quorum

KRaft controller quorum chịu trách nhiệm quản lý metadata. Trước khi thêm broker, xác minh quorum đang có leader và metadata replication ổn định.

Ví dụ:

~~~bash
kafka-metadata-quorum.sh --bootstrap-server broker-1.internal:9092 describe --status
~~~

Có thể kiểm tra thêm replication state nếu CLI của phiên bản hỗ trợ:

~~~bash
kafka-metadata-quorum.sh --bootstrap-server broker-1.internal:9092 describe --replication
~~~

Tên option và output có thể khác giữa các phiên bản Kafka. Dùng CLI đi kèm đúng bản phân phối đang chạy. Không thêm broker ứng dụng bằng cách tự ý sửa membership controller quorum.

### 5.3. Lưu snapshot trước thay đổi

Trước khi reassignment:

- Xuất topic list và topic descriptions.
- Lưu replica assignment hiện tại.
- Lưu broker ID, rack, listener và log directory.
- Lưu ACL và dynamic broker/topic config liên quan.
- Lưu replication factor và min ISR của topic quan trọng.
- Lưu baseline metrics và consumer lag.
- Ghi change ticket, owner và rollback decision point.

Snapshot assignment là cơ sở để so sánh và tạo kế hoạch quay lui. Bảo vệ file snapshot vì nó chứa cấu trúc nội bộ của cluster.

## 6. Lập kế hoạch capacity và placement

Thêm broker chỉ có ý nghĩa khi broker mới có đủ tài nguyên và placement được thiết kế đúng.

### 6.1. Capacity của broker mới

Ước lượng:

- CPU cho request handling, TLS, compression và replica fetch.
- RAM và OS page cache cho workload đọc/ghi.
- Disk capacity cho replica, retention, compaction và recovery headroom.
- Disk throughput và IOPS.
- Network bandwidth cho client traffic và inter-broker replication.
- File descriptor, socket, thread và process limit.
- Năng lực rack/switch và cross-rack bandwidth.

Không lấy dung lượng disk danh nghĩa làm capacity sử dụng được. Cần chừa headroom cho segment growth, log retention, replica movement, broker failure và bảo trì.

### 6.2. Cân bằng theo replica count và dung lượng

Replica count là chỉ báo đơn giản nhưng không đủ. Hai partition có thể có kích thước khác nhau rất lớn.

Nên so sánh:

- Số replica trên mỗi broker.
- Tổng log bytes trên mỗi broker.
- Leader count và leader bytes.
- Ingress/egress bytes.
- Disk utilization và disk latency.
- Partition size distribution.
- Số replica trên từng rack.

Một broker có ít replica nhưng giữ các partition rất lớn vẫn có thể quá tải. Mục tiêu là cân bằng tài nguyên và fault domain, không phải làm cho replica count bằng nhau tuyệt đối.

### 6.3. Rack awareness

Nếu cluster dùng nhiều rack hoặc availability zone, cấu hình broker.rack chính xác trên broker mới. Replica của cùng partition nên được phân phối qua các fault domain khác nhau khi số rack và topology cho phép.

Ví dụ:

~~~text
broker 1 -> rack-a
broker 2 -> rack-b
broker 3 -> rack-c
broker 4 -> rack-a
broker 5 -> rack-b
broker 6 -> rack-c
~~~

Khi reassignment, kiểm tra replica của cùng partition không bị dồn vào cùng rack. Nếu broker.rack thiếu hoặc sai, rack-aware assignment có thể không đạt mục tiêu resilience.

## 7. Chuẩn bị broker mới

Broker mới cần cấu hình tương thích với cluster hiện tại. Không sao chép nguyên thư mục dữ liệu từ broker khác hoặc dùng lại broker identity.

### 7.1. Broker ID phải duy nhất

Trong KRaft, node.id xác định identity của Kafka server. Mỗi node phải có ID duy nhất trong cluster.

Ví dụ cluster đã có node.id 1, 2, 3; broker mới dùng node.id 4. Không dùng lại ID của broker đã tồn tại hoặc chỉ đổi hostname mà giữ identity cũ.

### 7.2. Broker-only và combined role trong KRaft

KRaft hỗ trợ các vai trò server khác nhau:

- Broker-only: process.roles=broker.
- Controller-only: process.roles=controller.
- Combined: process.roles=broker,controller.

Trong production, dedicated controller quorum và broker-only nodes thường giúp tách tài nguyên control plane khỏi data plane. Nếu cluster hiện tại dùng dedicated controllers, hãy thêm broker-only node theo đúng mô hình đó; không biến broker mới thành controller chỉ để join cluster.

Nếu cluster hiện tại dùng combined role, broker mới cần theo đúng deployment pattern và capacity policy đã chọn. Việc thêm một controller làm thay đổi membership quorum, là một quy trình riêng và không được thực hiện như một bước thêm broker thông thường.

### 7.3. Cấu hình broker-only mẫu

Ví dụ minh họa cho broker-only node trong cluster KRaft dùng static controller quorum:

~~~properties
process.roles=broker
node.id=4

controller.quorum.voters=1@controller-1.internal:9093,2@controller-2.internal:9093,3@controller-3.internal:9093
controller.listener.names=CONTROLLER

listeners=CLIENT://0.0.0.0:9092,INTERNAL://0.0.0.0:9094
advertised.listeners=CLIENT://broker-4.internal:9092,INTERNAL://broker-4.internal:9094
listener.security.protocol.map=CLIENT:SASL_SSL,INTERNAL:SASL_SSL,CONTROLLER:SSL

inter.broker.listener.name=INTERNAL
broker.rack=rack-b

log.dirs=/var/lib/kafka/data-1,/var/lib/kafka/data-2
~~~

Đây là khung minh họa. Hãy dùng đúng quorum mode, listener names, protocol map, authentication, authorizer, principal mapping, log directory và broker defaults của cluster hiện tại.

Với dynamic controller quorum, dùng cấu hình bootstrap và quy trình format tương ứng của đúng phiên bản Kafka. Không đổi một cluster static quorum sang dynamic quorum trong lúc thêm broker.

### 7.4. advertised.listeners

Client bootstrap tới một broker, sau đó nhận metadata chứa địa chỉ broker. Vì vậy advertised.listeners phải công bố hostname/port mà client trong network zone tương ứng có thể truy cập.

Kiểm tra:

- DNS resolve từ client subnet.
- Firewall cho client listener.
- Inter-broker listener chỉ mở cho broker.
- Controller listener chỉ mở cho broker/controller.
- Certificate SAN khớp hostname được quảng bá.
- Không quảng bá controller endpoint cho producer/consumer.

Sai advertised.listeners có thể khiến broker khởi động thành công nhưng client không thể kết nối sau bootstrap.

### 7.5. Security identity

Broker mới phải có identity tương thích:

- TLS certificate và trust chain.
- SASL mechanism hoặc mTLS principal.
- Broker-to-broker authentication.
- ACL/authorizer config.
- Secret provider và file permission.
- JMX/metrics endpoint được bảo vệ.

Không dùng credential producer/consumer cho inter-broker traffic. Xác minh principal mapping để broker mới được nhận diện đúng trong các hoạt động nội bộ.

### 7.6. Storage và filesystem

Trên broker mới:

- Tạo log directory riêng và gán owner/group đúng.
- Kiểm tra mount, filesystem, I/O scheduler và dung lượng.
- Kiểm tra permission, inode và file descriptor limit.
- Xác nhận disk không dùng chung với log/backup gây contention.
- Cấu hình log.dirs đúng với volume đã mount.
- Không trỏ log.dirs vào thư mục có dữ liệu Kafka cũ không rõ nguồn gốc.

Nếu dùng KRaft storage formatting, chỉ format các log directory mới, rỗng, theo đúng cluster ID và quy trình của quorum mode. Không chạy format lên data directory của broker đang tồn tại. Không tự tạo cluster ID mới khi gia nhập cluster hiện hữu.

## 8. Khởi động và xác minh broker mới

Sau khi cấu hình, triển khai binary/version tương thích, certificate, secret và service unit/container manifest. Khởi động broker theo quy trình của nền tảng.

### 8.1. Kiểm tra log khởi động

Xác nhận:

- Process không crash hoặc restart loop.
- Broker kết nối được controller quorum.
- Registration hoàn tất.
- Listener bind đúng địa chỉ/port.
- Authentication nội bộ thành công.
- Log directory mở được.
- Không có lỗi cluster ID hoặc node ID.
- Không có lỗi certificate, authorization hoặc protocol mismatch.

Không tiếp tục reassignment nếu broker mới chưa ổn định.

### 8.2. Xác minh broker được cluster nhận diện

Dùng CLI/API phù hợp phiên bản. Ví dụ kiểm tra broker API versions:

~~~bash
kafka-broker-api-versions.sh --bootstrap-server broker-4.internal:9092
~~~

Có thể dùng AdminClient.describeCluster để xem node đang được controller công bố. Ngoài ra, kiểm tra broker metrics và log để xác nhận registration.

Broker mới tham gia cluster chưa đồng nghĩa đã nhận replica. Sau khi join, số replica trên broker có thể bằng 0 cho đến khi reassignment được thực hiện.

### 8.3. Smoke test

Trước khi chuyển replica:

1. Xác nhận broker mới xuất hiện trong cluster metadata.
2. Kiểm tra client listener và inter-broker listener.
3. Kiểm tra TLS/SASL và principal.
4. Kiểm tra rack và log directory.
5. Kiểm tra disk/network/CPU baseline.
6. Kiểm tra controller quorum vẫn khỏe.
7. Xác nhận broker không có lỗi nghiêm trọng trong log.
8. Không tạo topic thử nghiệm trên production nếu chưa được phép theo change plan.

## 9. Lập kế hoạch replica reassignment

Reassignment xác định broker nào sẽ lưu replica cho từng topic partition. Cần xem xét đồng thời durability, rack, disk, network và leader placement.

### 9.1. Chọn phạm vi di chuyển

Không cần chuyển mọi partition trong một lần. Chia theo:

- Topic hoặc nhóm topic.
- Kích thước partition.
- Mức độ quan trọng.
- Tải hiện tại.
- Rack/fault domain.
- Dung lượng broker nguồn và đích.

Có thể bắt đầu bằng một nhóm nhỏ, quan sát tác động, rồi mới mở rộng batch.

### 9.2. Giữ nguyên replication factor

Ví dụ partition đang có RF=3:

~~~text
Trước:
  replicas = [1, 2, 3]

Sau:
  replicas = [1, 4, 3]
~~~

Số replica vẫn là 3. Chỉ thay broker giữ một replica. Nếu mục tiêu là tăng RF, đó là thay đổi durability và storage riêng; không trộn vào reassignment chỉ nhằm phân tải.

### 9.3. Kiểm tra ràng buộc placement

Với từng partition:

- Replica list không chứa broker ID trùng nhau.
- Mọi broker ID đều tồn tại và online.
- Replica phân tán theo rack khi có thể.
- Broker đích đủ disk/network headroom.
- Không làm mất khả năng đạt min ISR khi một broker/rack gặp sự cố.
- Broker mới không nhận quá nhiều replica lớn cùng lúc.
- Leader placement không dồn quá tải vào một broker.

Một assignment có replica count cân bằng nhưng tất cả replica cùng rack vẫn không đáp ứng rack resilience.

## 10. Tạo reassignment plan bằng CLI

Kafka cung cấp kafka-reassign-partitions.sh để generate, execute và verify replica reassignment.

### 10.1. Chuẩn bị danh sách topic

Tạo file topics-to-move.json:

~~~json
{
  "topics": [
    { "topic": "orders" },
    { "topic": "payments" }
  ],
  "version": 1
}
~~~

Chỉ liệt kê topic thuộc phạm vi change. Kiểm tra topic nội bộ, topic có yêu cầu placement đặc biệt và topic được quản lý bởi hệ thống khác trước khi đưa vào kế hoạch.

### 10.2. Generate đề xuất

Ví dụ cluster có broker 1, 2, 3 và broker mới 4:

~~~bash
kafka-reassign-partitions.sh --bootstrap-server broker-1.internal:9092 --topics-to-move-json-file topics-to-move.json --broker-list "1,2,3,4" --generate
~~~

CLI in ra current assignment và proposed assignment. Lưu proposed assignment thành file riêng, ví dụ reassignment-batch-01.json. Không execute ngay output chưa review.

### 10.3. Review proposed assignment

Kiểm tra:

- Mỗi topic partition có đúng replication factor mong muốn.
- Replica list không trùng broker.
- Broker 4 nhận lượng dữ liệu phù hợp.
- Replica không vi phạm rack placement.
- Disk headroom của broker đích đủ.
- Leader count và leader bytes sau thay đổi không bị lệch quá mức.
- Topic critical vẫn có đủ replica ở fault domain độc lập.

Generate chỉ tạo một đề xuất. Người vận hành cần review và có thể chỉnh file JSON theo kế hoạch đã phê duyệt.

### 10.4. Ví dụ reassignment JSON

~~~json
{
  "version": 1,
  "partitions": [
    {
      "topic": "orders",
      "partition": 0,
      "replicas": [1, 4, 3]
    },
    {
      "topic": "orders",
      "partition": 1,
      "replicas": [2, 4, 1]
    }
  ]
}
~~~

Ví dụ giữ RF=3 cho cả hai partition. Thứ tự broker trong replicas list có ý nghĩa đối với preferred replica. Nếu cần chỉ định log directory, một số phiên bản hỗ trợ trường log_dirs; kiểm tra schema CLI hiện tại trước khi thêm trường này.

## 11. Execute reassignment có kiểm soát

Reassignment làm follower mới copy dữ liệu từ leader. Tùy kích thước partition và năng lực disk/network, quá trình này có thể tạo tải đáng kể.

### 11.1. Bắt đầu với throttle

Ví dụ chạy batch với replication throttle 50 MiB/s:

~~~bash
kafka-reassign-partitions.sh --bootstrap-server broker-1.internal:9092 --reassignment-json-file reassignment-batch-01.json --execute --throttle 52428800
~~~

Giá trị throttle cần được chọn theo capacity thực tế và đơn vị mà CLI phiên bản đó sử dụng. Xác nhận bằng help của CLI đi kèm cluster. Không mặc định 50 MiB/s phù hợp mọi môi trường.

Throttle thấp làm reassignment lâu hơn; throttle cao có thể cạnh tranh disk/network với producer, consumer và replication traffic hiện hữu. Chọn mức khởi đầu thận trọng rồi điều chỉnh dựa trên metrics.

### 11.2. Chia batch

Một runbook có thể:

1. Di chuyển một nhóm partition nhỏ.
2. Theo dõi ISR, disk, network và client latency.
3. Chờ batch hoàn tất.
4. Xác nhận broker mới nhận replica ổn định.
5. Mở rộng sang batch kế tiếp.

Không chạy đồng thời nhiều reassignment lớn nếu chưa hiểu giới hạn network, disk và replica fetcher. Nhiều partition cùng copy có thể tạo I/O burst và làm giảm throughput của workload chính.

### 11.3. Theo dõi tiến độ

Dùng verify:

~~~bash
kafka-reassign-partitions.sh --bootstrap-server broker-1.internal:9092 --reassignment-json-file reassignment-batch-01.json --verify
~~~

Theo dõi thêm:

- UnderReplicatedPartitions.
- UnderMinIsrPartitionCount.
- OfflinePartitionsCount.
- IsrShrinksPerSec và IsrExpandsPerSec.
- ReplicaFetcherManager lag.
- Disk bytes, disk latency và disk queue depth.
- Network throughput và retransmission.
- Produce/fetch request latency.
- Consumer lag và end-to-end latency.

Nếu ISR shrink liên tục hoặc client SLO xấu đi, giảm throttle hoặc dừng mở rộng batch để điều tra.

## 12. Kiểm tra kết quả reassignment

Khi verify cho biết reassignment hoàn tất, vẫn cần xác nhận trạng thái thực tế.

### 12.1. Kiểm tra partition assignment

~~~bash
kafka-topics.sh --bootstrap-server broker-1.internal:9092 --describe --topic orders
~~~

Kiểm tra replica list, leader và ISR. Xác nhận broker mới thực sự giữ replica cho partition đã chọn và RF không thay đổi ngoài dự kiến.

### 12.2. Kiểm tra log directory

Có thể dùng kafka-log-dirs.sh để xem replica và kích thước log theo broker:

~~~bash
kafka-log-dirs.sh --bootstrap-server broker-1.internal:9092 --describe --broker-list "1,2,3,4" --topic-list "orders"
~~~

Cú pháp option có thể thay đổi theo phiên bản. Đọc help của CLI đi kèm cluster và đối chiếu output theo broker/log directory.

### 12.3. Kiểm tra ISR và min ISR

Với topic quan trọng:

- ISR đạt replication policy mong muốn.
- Không có partition offline.
- Không có under-replicated partition kéo dài.
- Không có partition dưới min ISR.
- Producer với acks=all vẫn hoạt động theo durability policy.
- Consumer fetch latency và lag trở lại baseline.

Reassignment hoàn tất không có nghĩa mọi replica đã bền vững nếu broker mới còn lỗi disk hoặc liên tục rời ISR.

## 13. Cân bằng leader sau khi di chuyển replica

Reassignment thay đổi replica placement và có thể ảnh hưởng leader placement. Một cluster có replica bytes cân bằng nhưng leader traffic vẫn tập trung vào vài broker.

Kiểm tra:

- Leader count mỗi broker.
- Leader bytes/s.
- Produce request/s.
- Fetch request/s.
- CPU/network theo broker.
- Preferred replica assignment.

Nếu cần đưa leader về preferred replica, thực hiện preferred leader election sau khi replica và ISR đã ổn định. Ví dụ:

~~~bash
kafka-leader-election.sh --bootstrap-server broker-1.internal:9092 --election-type preferred --all-topic-partitions
~~~

Đây là thao tác riêng có thể làm thay đổi leader và tạo thêm traffic. Không chạy đồng loạt trong lúc reassignment hoặc khi ISR chưa ổn định. Có thể chọn phạm vi topic/partition cụ thể nếu CLI phiên bản hỗ trợ.

Không cố cân bằng leader bằng cách chuyển liên tục giữa các broker. Mục tiêu là phân phối request và bytes phù hợp, đồng thời giữ leader placement ổn định.

## 14. Theo dõi trong và sau mở rộng

Một bảng theo dõi nên có baseline, ngưỡng cảnh báo và người chịu trách nhiệm.

| Nhóm | Chỉ số | Mục tiêu quan sát |
|---|---|---|
| Cluster health | OfflinePartitionsCount | Bằng 0 |
| Replication | UnderReplicatedPartitions | Trở về 0 sau batch |
| Durability | UnderMinIsrPartitionCount | Bằng 0 |
| ISR | ISR shrink/expand | Không dao động kéo dài |
| Broker load | CPU, heap, GC, request handler idle | Còn headroom |
| Disk | Used bytes, IOPS, latency, queue depth | Không chạm ngưỡng |
| Network | Ingress/egress, packet drop, retransmit | Không gây nghẽn |
| Leader | Leader count/bytes theo broker | Không tập trung bất thường |
| Client | Produce/fetch p95/p99 | Trong SLO |
| Consumer | Lag và end-to-end processing age | Không tăng kéo dài |
| KRaft | Quorum leader, voter lag và metadata replication | Ổn định |

Một số metric có tên khác theo exporter và phiên bản. Chuẩn hóa dashboard theo JMX source/exporter đang dùng.

### 14.1. Dừng hoặc giảm tốc khi nào?

Tạm dừng nhận thêm batch hoặc hạ throttle khi:

- ISR shrink tăng liên tục.
- Under-replicated partition tăng thay vì giảm.
- Broker đích có disk latency/queue depth cao.
- Produce p99 hoặc consumer lag vượt SLO.
- Network saturation hoặc packet loss xuất hiện.
- Controller quorum hoặc broker registration bất ổn.
- Disk headroom của broker đích không còn đủ.

Không chờ tới khi partition offline mới hành động. Chỉ số leading indicator như disk queue, replica lag và request queue giúp can thiệp sớm hơn.

## 15. Xử lý reassignment bị chậm hoặc thất bại

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Broker mới không xuất hiện | Sai node.id, cluster ID, listener hoặc controller connection | Kiểm tra config, registration và broker log |
| Broker join nhưng không có replica | Chưa chạy reassignment hoặc topic không nằm trong scope | Kiểm tra plan và assignment |
| Reassignment chạy rất chậm | Throttle thấp, disk/network bottleneck hoặc partition lớn | Kiểm tra replica lag và tăng throttle có kiểm soát |
| ISR shrink | Follower không theo kịp leader, disk/network lỗi | Giảm batch, điều tra broker/follower |
| Disk broker mới tăng nhanh | Plan đưa quá nhiều replica hoặc retention lớn | Dừng batch tiếp theo và tính lại capacity |
| Produce latency tăng | Replication traffic cạnh tranh request | Hạ throttle và giảm concurrency reassignment |
| Consumer lag tăng | Broker fetch bị chậm hoặc downstream chịu tải | Kiểm tra fetch latency và downstream |
| Rack placement sai | broker.rack thiếu/sai hoặc plan không hợp lệ | Sửa inventory và reassignment plan |
| Verify báo còn ongoing | Replica chưa catch up hoặc broker không ổn định | Kiểm tra ISR, replica fetcher và disk |
| Leader lệch sau reassignment | Preferred replica distribution hoặc election chưa phù hợp | Đánh giá leader bytes và election có chọn lọc |
| Controller quorum bất ổn | Network hoặc controller issue độc lập | Dừng change và khôi phục quorum health |
| Reassignment timeout | CLI mất response hoặc cluster đang bận | Kiểm tra trạng thái thực tế trước khi retry |

### 15.1. Timeout không có nghĩa request chưa chạy

Nếu CLI mất kết nối sau khi gửi execute, reassignment có thể đã được controller chấp nhận. Trước khi chạy lại:

1. Chạy verify với đúng file reassignment.
2. Kiểm tra partition assignment hiện tại.
3. Kiểm tra broker log và controller state.
4. Xác định reassignment đang chạy, đã hoàn tất hay thất bại.
5. Chỉ gửi lại sau khi hiểu trạng thái hiện tại.

Không lặp execute mù quáng khi chưa biết request trước có được áp dụng hay không.

## 16. Rollback và xử lý broker mới gặp sự cố

Rollback phải dựa trên snapshot assignment và trạng thái thực tế, không chỉ dựa vào file plan ban đầu.

### 16.1. Trước khi execute

Nếu plan chưa được execute, có thể sửa hoặc bỏ file plan mà không ảnh hưởng cluster. Xác minh chưa có reassignment nào đang chạy.

### 16.2. Trong khi reassignment đang chạy

Nếu phát hiện tải xấu hoặc broker mới không ổn định:

- Dừng mở rộng sang batch tiếp theo.
- Giảm throttle nếu cần.
- Thu thập trạng thái reassignment và ISR.
- Xác định replica nào đã copy xong và replica nào đang catch up.
- Chọn tiếp tục, điều chỉnh plan hoặc chuyển ngược dựa trên trạng thái thực tế.

Không xóa log directory hoặc tắt broker tùy tiện trong khi broker đang giữ replica cần thiết.

### 16.3. Reassign ngược về assignment cũ

Nếu cần quay lui, dùng snapshot assignment đã lưu để tạo reassignment ngược. Thực hiện theo batch và throttle như một lần di chuyển mới.

Quay lui cũng tạo replication traffic và có thể làm client latency tăng. Không mặc định rollback luôn nhanh hoặc không rủi ro.

### 16.4. Broker mới mất kết nối

Nếu broker mới mất kết nối sau khi nhận replica:

- Kiểm tra broker process, disk, network và controller registration.
- Xác định partition bị under-replicated hoặc dưới min ISR.
- Không xóa replica assignment ngay nếu broker có thể phục hồi nhanh.
- Khôi phục broker hoặc chuyển replica sang broker khác theo plan được kiểm soát.
- Xác minh ISR và durability trước khi tiếp tục.

Nếu broker mới đã được đưa vào replica set, cluster có thể phụ thuộc vào broker đó để duy trì RF. Tắt broker không đồng nghĩa replica tự chuyển sang nơi khác ngay lập tức.

## 17. Khi nào được phép loại bỏ broker?

Bài học tập trung vào thêm broker, nhưng một số đợt mở rộng có thể đi kèm thay thế broker cũ. Chỉ loại bỏ broker cũ khi đã di chuyển toàn bộ replica và xác minh không còn resource phụ thuộc.

Checklist trước khi decommission:

1. Không còn partition replica trên broker cần loại bỏ.
2. Không còn leader trên broker đó.
3. Reassignment verify hoàn tất.
4. ISR và min ISR ổn định.
5. Không còn log directory chứa replica đang được sử dụng.
6. Broker không còn là dependency của connector/client config.
7. Broker không thuộc controller quorum nếu chưa có quy trình riêng cho controller.
8. Inventory, monitoring và automation đã cập nhật.
9. Có rollback hoặc restore path nếu phát hiện replica còn sót.
10. Có change approval và cửa sổ bảo trì.

Dùng kafka-log-dirs và topic descriptions để xác nhận. Không chỉ dựa vào việc broker process đã dừng hoặc không còn nhận client request.

## 18. Runbook mở rộng cluster mẫu

### Giai đoạn A — Chuẩn bị

- Xác định mục tiêu capacity và broker ID mới.
- Xác nhận cluster health, KRaft quorum và baseline SLO.
- Kiểm tra rack, disk, network và security.
- Lưu snapshot replica assignment.
- Chuẩn bị config, certificate, secret và log directory.
- Xác định batch size, throttle và abort threshold.

### Giai đoạn B — Join broker

- Triển khai binary tương thích.
- Format chỉ log directory mới theo quy trình KRaft hiện hữu.
- Khởi động broker.
- Xác minh registration, listener, rack và storage.
- Theo dõi broker health trước khi reassignment.

### Giai đoạn C — Reassignment

- Tạo topics-to-move JSON.
- Generate proposed assignment.
- Review RF, rack, disk và leader placement.
- Execute batch nhỏ với throttle.
- Theo dõi ISR, disk, network, latency và lag.
- Verify xong batch trước khi chuyển batch tiếp.

### Giai đoạn D — Hoàn tất

- Kiểm tra replica assignment và log directory.
- Kiểm tra ISR, under-replicated và offline partition.
- Kiểm tra leader distribution.
- Đánh giá client SLO và capacity headroom.
- Cập nhật inventory, dashboard và runbook.
- Đóng change khi trạng thái ổn định qua khoảng quan sát đã định.

## 19. Checklist production

Trước khi thêm broker:

1. Có lý do capacity được hỗ trợ bởi metrics và workload forecast.
2. Cluster hiện tại khỏe, không có offline partition hoặc ISR instability.
3. KRaft quorum có leader và metadata replication ổn định.
4. Broker ID/node.id mới là duy nhất.
5. Quorum mode và process.roles phù hợp cluster hiện tại.
6. Listener, advertised.listeners, DNS và certificate SAN chính xác.
7. TLS/SASL, principal mapping và authorizer được cấu hình.
8. broker.rack phản ánh đúng fault domain.
9. Disk, mount, permission, IOPS và network đã được kiểm tra.
10. Storage formatting chỉ chạy trên log directory mới, rỗng.
11. Có baseline và snapshot assignment trước change.
12. Có owner, approval, maintenance window và rollback decision point.

Trước khi reassignment:

13. Chỉ chọn topic/partition nằm trong scope.
14. Giữ đúng replication factor theo mục tiêu.
15. Replica list không trùng broker và tuân thủ rack placement.
16. Broker đích có đủ disk/network headroom.
17. Batch size và throttle đã được xác định.
18. Có dashboard ISR, disk, network, latency và consumer lag.
19. Có kế hoạch xử lý timeout và broker failure.
20. Có snapshot để tạo reassignment ngược.

Sau reassignment:

21. Verify cho biết reassignment hoàn tất.
22. Replica assignment và log directory khớp plan.
23. ISR ổn định và không có under-replicated/offline partition.
24. Không có partition dưới min ISR.
25. Leader distribution hợp lý.
26. Producer/consumer SLO trở lại baseline.
27. Broker mới có capacity headroom.
28. Inventory, alert và runbook được cập nhật.

## 20. Bài tập thực hành

### Bài 1: Thêm broker-only node trong KRaft lab

1. Dựng cluster KRaft với controller quorum hiện có.
2. Chuẩn bị broker-only node có node.id mới.
3. Cấu hình controller connection, client/internal listener và rack.
4. Chuẩn bị log directory mới, rỗng.
5. Format theo cluster ID và quorum mode của lab.
6. Khởi động broker.
7. Xác minh broker registration và metadata.
8. Giải thích vì sao không thay đổi controller quorum membership khi chỉ thêm broker-only node.

### Bài 2: Generate reassignment plan

1. Tạo topic orders-lab có nhiều partition và RF=3.
2. Lưu assignment hiện tại.
3. Tạo topics-to-move.json.
4. Chạy generate với broker mới nằm trong broker list.
5. Review proposed JSON.
6. Kiểm tra RF, rack và broker load.
7. Chỉnh assignment để tránh dồn partition lớn vào một broker.

### Bài 3: Execute có throttle

1. Chọn một batch nhỏ.
2. Execute với throttle thấp trong môi trường lab.
3. Theo dõi reassignment progress.
4. Quan sát ISR và replica fetcher lag.
5. Thử tăng throttle khi cluster còn headroom.
6. So sánh throughput và latency trước/sau.
7. Verify batch hoàn tất.

### Bài 4: Mô phỏng broker mới gặp sự cố

1. Bắt đầu reassignment một nhóm partition.
2. Trong lab, làm broker mới mất kết nối.
3. Quan sát under-replicated partition và ISR.
4. Xác định partition nào bị ảnh hưởng.
5. Khôi phục broker hoặc tạo reassignment ngược.
6. Xác minh ISR và min ISR trở lại bình thường.
7. Ghi lại quyết định rollback.

### Bài 5: Đánh giá leader và rack placement

1. Tạo broker trên ba rack.
2. Tạo topic RF=3.
3. Kiểm tra replica placement.
4. Thực hiện reassignment có rack-aware assignment.
5. Kiểm tra leader count và leader bytes.
6. Chạy preferred leader election có chọn lọc nếu cần.
7. Xác nhận không làm mất ISR hoặc vi phạm durability.

### Bài 6: Viết runbook

1. Ghi preflight command và metrics.
2. Ghi broker config checklist.
3. Ghi generate/execute/verify command.
4. Đặt batch size và throttle.
5. Định nghĩa ngưỡng dừng.
6. Viết quy trình xử lý timeout và broker failure.
7. Viết rollback bằng snapshot assignment.
8. Định nghĩa tiêu chí đóng change.

## 21. Câu hỏi tự kiểm tra

1. Khi nào nên thêm broker thay vì chỉ tối ưu producer/consumer?
2. Vì sao thêm broker không tự chuyển replica hiện có?
3. Broker, partition, replica, leader và ISR khác nhau thế nào?
4. RF=3 và min.insync.replicas=2 có ý nghĩa gì khi dùng acks=all?
5. Reassignment khác tăng partition count như thế nào?
6. Vì sao node.id phải duy nhất?
7. Broker-only và combined broker/controller trong KRaft khác nhau ra sao?
8. Vì sao không nên tự ý thêm controller khi chỉ muốn thêm broker?
9. advertised.listeners ảnh hưởng kết nối client sau bootstrap thế nào?
10. broker.rack ảnh hưởng replica placement ra sao?
11. Vì sao cần snapshot assignment trước reassignment?
12. File topics-to-move.json dùng để làm gì?
13. Generate và execute có vai trò khác nhau như thế nào?
14. Vì sao cần review proposed assignment trước khi execute?
15. Throttle ảnh hưởng replication và client latency ra sao?
16. Những metric nào cho biết reassignment đang gây áp lực lên cluster?
17. Khi CLI timeout sau execute, vì sao không nên gửi lại ngay?
18. Khi nào cần preferred leader election?
19. Cần xác minh gì trước khi decommission broker cũ?
20. Rollback reassignment có thể tạo ra những chi phí và rủi ro nào?

## Kết luận

Mở rộng Kafka cluster cần tách thành hai việc: đưa broker mới vào cluster và chuyển replica sang broker đó. Broker mới phải có identity duy nhất, cấu hình KRaft đúng mô hình, listener/security phù hợp, rack chính xác và storage đã chuẩn bị. Sau khi broker được controller nhận diện, người vận hành mới lập kế hoạch reassignment cho từng nhóm topic/partition.

Reassignment cần giữ replication factor theo mục tiêu, tôn trọng rack awareness, giới hạn tốc độ bằng throttle và theo dõi ISR, disk, network, request latency cùng consumer lag. Chỉ chuyển sang batch tiếp theo khi batch hiện tại ổn định. Nếu timeout hoặc broker lỗi, kiểm tra trạng thái thực tế trước khi retry hoặc rollback bằng snapshot assignment.

Một đợt mở rộng chỉ hoàn tất khi replica placement đúng plan, ISR ổn định, không có partition offline/under-replicated kéo dài, leader traffic được phân phối hợp lý và client SLO vẫn đạt. Hãy cập nhật inventory, monitoring và runbook để cluster mới có thể vận hành lâu dài.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Broker | Kafka server lưu và phục vụ partition replica. |
| Broker ID / node.id | Định danh duy nhất của Kafka server trong cluster. |
| Partition | Đơn vị log, ordering và phân phối tải. |
| Replica | Bản sao partition trên một broker. |
| Leader replica | Replica nhận produce request và phục vụ read theo cấu hình. |
| Follower replica | Replica fetch dữ liệu từ leader. |
| ISR | Tập replica đang đồng bộ đủ điều kiện. |
| Replication factor | Số replica được gán cho mỗi partition. |
| min.insync.replicas | Số ISR tối thiểu cần có để chấp nhận write theo durability policy. |
| Reassignment | Thay đổi danh sách broker giữ replica của partition. |
| Rack awareness | Phân phối replica qua các rack/fault domain. |
| broker.rack | Thuộc tính xác định rack của broker. |
| advertised.listeners | Địa chỉ broker công bố cho client qua metadata. |
| KRaft | Kiến trúc Kafka quản lý metadata bằng controller quorum. |
| Broker-only | Server chỉ chạy vai trò broker trong KRaft. |
| Combined role | Server chạy cả broker và controller role. |
| Throttle | Giới hạn tốc độ replication/reassignment để bảo vệ workload. |
| Under-replicated partition | Partition có replica chưa theo kịp hoặc thiếu trạng thái ISR mong muốn. |
| Offline partition | Partition hiện không có leader khả dụng. |
| Preferred replica | Replica đứng đầu assignment, thường là leader ưu tiên. |
| Headroom | Năng lực tài nguyên còn dự phòng cho tải tăng và phục hồi. |

