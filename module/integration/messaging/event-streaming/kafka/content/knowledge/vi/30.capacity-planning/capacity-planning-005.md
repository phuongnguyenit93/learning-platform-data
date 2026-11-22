# Lập kế hoạch partition theo tăng trưởng và giới hạn metadata

Partition là đơn vị lưu trữ, replication và phân phối công việc cơ bản của Kafka. Tăng số partition có thể tăng throughput và mức song song của consumer, nhưng mỗi partition cũng tạo thêm metadata, replica log, file/index, công việc phục hồi và trạng thái mà broker/controller phải quản lý. Vì vậy, lập kế hoạch partition phải cân bằng nhu cầu throughput, concurrency, ordering, tăng trưởng dữ liệu và năng lực metadata của cluster.

Không có một con số partition tối đa an toàn áp dụng cho mọi cluster. Giới hạn thực tế phụ thuộc Kafka version, số broker/controller, CPU, heap, disk, network, replication factor, kích thước partition, số consumer group, workload Kafka Streams/Connect và tần suất thay đổi metadata. Cách làm đúng là tính nhu cầu từ workload, benchmark trên cấu hình gần production, rồi giữ headroom cho tăng trưởng và phục hồi.

## 1. Partition giải quyết vấn đề gì?

Một topic được chia thành nhiều partition. Mỗi partition là một log có thứ tự offset riêng và có thể được đặt trên broker khác nhau. Producer ghi record vào partition; consumer group phân phối các partition cho member để xử lý song song.

~~~mermaid
flowchart LR
    P["Producers"] --> T["Topic: orders"]
    T --> P0["Partition 0"]
    T --> P1["Partition 1"]
    T --> P2["Partition 2"]
    T --> P3["Partition 3"]
    P0 --> C0["Consumer A"]
    P1 --> C1["Consumer B"]
    P2 --> C2["Consumer C"]
    P3 --> C3["Consumer D"]
~~~

Nhiều partition cho phép:

- Phân phối leader và replica trên nhiều broker.
- Ghi/đọc nhiều partition đồng thời.
- Tăng số consumer member có thể active trong một group khi group subscribe topic đó.
- Chia tải theo key và hỗ trợ scale out theo nhu cầu.

Partition cũng tạo chi phí:

- Mỗi replica cần log, index, cache và trạng thái runtime.
- Broker phải quản lý leader/follower, fetcher, segment và file handle.
- Controller phải lưu và truyền metadata assignment/ISR.
- Consumer group phải phân phối và rebalance nhiều partition.
- Kafka Streams có thể tạo task và state store tương ứng; Connect và các internal topic cũng có partition riêng.

Tăng partition chỉ giúp khi partition là giới hạn hiện tại. Nếu bottleneck nằm ở database đích, broker network, disk hoặc một key nóng, thêm partition có thể không cải thiện throughput.

## 2. Phân biệt logical partition và partition replica

Số partition của topic là số log logic. Replication factor (RF) quyết định mỗi partition có bao nhiêu replica trên cluster.

Ví dụ topic orders có 48 partition và RF=3:

- Logical partition count: 48.
- Partition replica count toàn cluster: 48 × 3 = 144.
- Mỗi partition có một leader và hai follower khi đủ RF.

Với nhiều topic, tính:

\[
P_{cluster} = \sum_{topic} P_{topic}
\]

\[
R_{cluster} = \sum_{topic}(P_{topic} \times RF_{topic})
\]

Nếu có B broker và placement tương đối đều, số replica local trung bình trên mỗi broker xấp xỉ:

\[
R_{broker,avg} \approx \frac{R_{cluster}}{B}
\]

Đây là số trung bình để lập kế hoạch, không phải cam kết phân bố thực tế. Rack awareness, broker capacity, partition size và assignment có thể làm từng broker lệch đáng kể.

Ví dụ:

| Topic | Partitions | RF | Partition replicas |
|---|---:|---:|---:|
| orders | 48 | 3 | 144 |
| payments | 24 | 3 | 72 |
| audit-events | 12 | 2 | 24 |
| **Tổng** | **84** | | **240** |

Với 6 broker, trung bình có khoảng 40 partition replica trên mỗi broker. Controller metadata quản lý assignment của 84 logical partition và danh sách replica/ISR tương ứng; mỗi broker đồng thời giữ trạng thái local cho các replica được đặt trên nó.

## 3. Thu thập workload trước khi tính partition

Không bắt đầu bằng câu hỏi “topic nên có bao nhiêu partition?”. Trước tiên hãy thu thập:

| Dữ liệu | Cần biết | Ảnh hưởng |
|---|---|---|
| Peak ingress | MiB/s và event/s ở giờ cao điểm | Throughput producer và broker |
| Record size | Trung bình, p95/p99, batch size | Byte rate, compression và network |
| Consumer rate | Event/s mỗi worker hoặc mỗi thread | Số worker/partition cần thiết |
| Processing latency | p95/p99 và thời gian xử lý tối đa | Concurrency và poll/rebalance |
| Backlog recovery | Backlog lớn nhất và thời gian drain mong muốn | Capacity dự phòng |
| Key distribution | Key cardinality, skew và ordering requirement | Hot partition và partitioner |
| Retention | Thời gian/bytes cần giữ | Disk capacity và segment count |
| Replication | RF, min.insync.replicas, rack policy | Disk/network và failure tolerance |
| Growth | Tăng event/s, byte/s và số tenant | Headroom và kế hoạch mở rộng |
| Consumer groups | Số group, số partition subscribed và tần suất rebalance | Metadata/group coordination |

Đo theo từng topic hoặc workload class. Một topic payment có yêu cầu ordering và durability khác topic analytics; không nên dùng một công thức hoặc ngưỡng cho tất cả.

## 4. Tính partition theo throughput

Benchmark để xác định throughput an toàn của một partition trong điều kiện gần production: record size, key distribution, compression, acks, RF, min.insync.replicas, số broker và consumer workload tương ứng.

Gọi:

- R_peak: peak ingress byte rate của topic.
- r_partition_safe: throughput byte rate an toàn đã benchmark cho một partition.

Ước lượng số partition theo throughput:

\[
P_{throughput} =
\left\lceil \frac{R_{peak}}{r_{partition,safe}} \right\rceil
\]

Ví dụ topic nhận 120 MiB/s ở peak. Benchmark cho thấy một partition có thể duy trì khoảng 3 MiB/s trong khi vẫn đạt latency và durability mục tiêu:

\[
P_{throughput} = \left\lceil \frac{120}{3} \right\rceil = 40
\]

40 là mức tính từ throughput đã đo. Nếu muốn 20% headroom cho burst/growth, có thể chọn 48 partition sau khi kiểm tra capacity cluster và chi phí metadata.

Không dùng throughput tối đa trong một bài benchmark ngắn làm r_partition_safe. Dùng mức ổn định dưới tải kéo dài, có replication, consumer fetch và latency tail trong giới hạn SLO.

### Dùng event rate khi kích thước record ổn định

Nếu record size tương đối ổn định, có thể tính theo event/s:

\[
P_{throughput} =
\left\lceil \frac{EventRate_{peak}}{EventsPerSecond_{partition,safe}} \right\rceil
\]

Nếu record size thay đổi mạnh, byte rate thường hữu ích hơn event rate. Một partition chứa 10.000 event nhỏ có thể nhẹ hơn nhiều so với 1.000 event lớn.

## 5. Tính partition theo consumer parallelism

Trong một consumer group chỉ subscribe một topic, một partition tại một thời điểm được gán cho tối đa một member. Vì vậy, số partition đặt giới hạn số consumer member có thể active đồng thời cho topic đó trong group.

Gọi:

- λ: peak event rate cần xử lý.
- c_worker: throughput an toàn của một consumer worker/thread.

Số worker cần để xử lý tải:

\[
N_{worker} =
\left\lceil \frac{\lambda}{c_{worker}} \right\rceil
\]

Để các worker đó có thể active đồng thời trong group đọc topic này, số partition cần ít nhất xấp xỉ:

\[
P_{consumer} \geq N_{worker}
\]

Ví dụ peak 20.000 event/s; một worker xử lý ổn định 600 event/s:

\[
P_{consumer} = \left\lceil \frac{20.000}{600} \right\rceil = 34
\]

Nếu topic chỉ có 12 partition, tăng consumer member lên 34 không tạo ra 34 luồng đọc song song cho topic đó. Nhiều member sẽ không được gán partition.

Đây là quy tắc cho một topic trong một group. Khi consumer subscribe nhiều topic, assignment được tính trên tập partition của tất cả topic và có thể phức tạp hơn. Consumer có thể được gán nhiều partition; không mặc định một member luôn chỉ có đúng một partition.

### Consumer concurrency không tự động bằng throughput

Một consumer có thể xử lý nhiều partition tuần tự hoặc dùng worker pool bất đồng bộ. Tuy nhiên, xử lý bất đồng bộ cần quản lý offset completion đúng cách để không commit vượt qua record chưa hoàn tất. Tăng số partition có thể tăng concurrency nhưng cũng làm tăng rebalance, state và file/log overhead.

## 6. Tính partition cho backlog recovery

Capacity cần đủ cho tải bình thường và khả năng drain backlog sau sự cố. Gọi:

- B: backlog event cần xử lý.
- T: thời gian drain mục tiêu.
- λ: event rate mới tiếp tục đi vào trong lúc drain.

Throughput xử lý tổng cần đạt:

\[
\mu_{required} \geq \lambda + \frac{B}{T}
\]

Nếu mỗi worker xử lý an toàn c_worker event/s:

\[
N_{worker,recovery} =
\left\lceil \frac{\mu_{required}}{c_{worker}} \right\rceil
\]

Số partition cần hỗ trợ mức concurrency này ít nhất bằng số worker cần active cho topic, nếu mỗi worker cần một partition để chạy song song.

Ví dụ:

- Backlog sau outage: 1.200.000 event.
- Thời gian drain mong muốn: 600 giây.
- Input rate tiếp tục: 20.000 event/s.
- Một worker xử lý ổn định: 600 event/s.

\[
\mu_{required} = 20.000 + \frac{1.200.000}{600} = 22.000
\]

\[
N_{worker,recovery} = \left\lceil \frac{22.000}{600} \right\rceil = 37
\]

Vậy recovery cần khoảng 37 worker hoạt động đồng thời, chưa tính headroom và phân bố tải không đều. Nếu benchmark throughput cần 40 partition và consumer parallelism cần 34 partition, recovery cần 37, thì:

\[
P_{base} = \max(40, 34, 37) = 40
\]

Có thể chọn 48 sau khi kiểm tra headroom, RF, broker capacity và metadata budget.

## 7. Công thức chọn số partition ban đầu

Với một topic, có thể dùng:

\[
P_{base} = \max(P_{throughput}, P_{consumer}, P_{recovery})
\]

Sau đó đánh giá các ràng buộc khác:

- Ordering theo key và khả năng giữ partition mapping lâu dài.
- Số broker, RF và rack/failure-domain placement.
- Disk/network/CPU capacity và số replica local mỗi broker.
- Metadata/controller budget.
- Số consumer group và state store/internal topic nếu dùng Streams.
- Tăng trưởng trong vòng đời topic.

Không nhân partition count với replication factor khi tính logical partition cần cho consumer parallelism. RF làm tăng số replica, disk và replication traffic; nó không tạo thêm partition độc lập cho consumer group.

## 8. Key distribution và yêu cầu ordering

Khi producer dùng key, partitioner thường ánh xạ cùng một key vào cùng partition để giữ thứ tự log cho key đó trong điều kiện partition mapping ổn định.

Ví dụ:

~~~text
key=order-1001 -> partition 3
key=order-1002 -> partition 1
key=order-1003 -> partition 5
~~~

Nếu một key tạo phần lớn traffic, partition chứa key đó có thể trở thành hot partition. Tăng tổng partition không tự chia nhỏ một key duy nhất nếu partitioner vẫn giữ key đó ở một partition.

Trước khi tăng partition:

- Đo phân bố byte/event theo partition, không chỉ tổng topic.
- Kiểm tra key skew và hot key.
- Xác định ordering cần theo entity nào.
- Đánh giá custom partitioner hoặc tách luồng nếu một key có tải quá lớn.

### Tăng partition có thể đổi mapping của key

Với partitioner dựa trên hash và số partition, tăng partition count có thể làm key cũ được ánh xạ sang partition mới cho các record gửi sau. Record cũ vẫn nằm ở partition cũ, record mới có thể nằm ở partition khác. Consumer không có một thứ tự tổng hợp tự nhiên giữa hai partition, nên ordering theo key có thể bị phá vỡ qua thời điểm thay đổi.

Nếu ordering là yêu cầu nghiệp vụ, cần lập kế hoạch migration: tạo topic mới với partition count đã chọn, chuyển producer/consumer theo cutover có kiểm soát, hoặc dùng partitioning strategy ổn định được thiết kế từ đầu. Không tăng partition trực tiếp chỉ để scale mà không đánh giá key mapping.

## 9. Tính replica và tải broker sau khi chọn partition

Sau khi có P logical partitions, tính replica:

\[
ReplicaCount = P \times RF
\]

Với 48 partition và RF=3:

- Logical partitions: 48.
- Total partition replicas: 144.
- Nếu cluster có 6 broker và phân bố lý tưởng: trung bình 24 replica local mỗi broker.

Đây chỉ là baseline. Phải kiểm tra:

- Replica bytes theo broker.
- Leader count và leader traffic.
- Follower replication throughput.
- Disk free/headroom theo volume.
- Rack awareness và failure-domain separation.
- Số replica một broker phải nhận nếu broker khác mất.

Một topic có nhiều partition nhưng dữ liệu rất nhỏ vẫn tạo metadata và log overhead. Một topic ít partition nhưng partition rất lớn lại có thể tạo recovery/reassignment lâu và mất cân bằng disk. Cần cân bằng cả số lượng lẫn kích thước partition.

## 10. Partition count và metadata trong Kafka

Mỗi logical partition tạo metadata mà cluster phải duy trì, ví dụ:

- Topic ID/name và partition index.
- Replica assignment và preferred replica order.
- Leader, leader epoch và ISR state.
- Partition/topic configuration liên quan.
- Trạng thái cần thiết để broker/controller phối hợp leader election và replication.

Mỗi broker cũng quản lý local replica state, log object, segment/index, fetcher và các cấu trúc runtime tương ứng với replica đặt trên broker đó.

Khi partition count tăng:

- Metadata snapshot và metadata propagation lớn hơn.
- Broker cần nạp và quản lý nhiều partition/replica state hơn.
- Startup, broker registration, controller failover và metadata replay có thể tốn thêm thời gian.
- Consumer group assignment/rebalance xử lý nhiều partition hơn.
- File handle, segment/index và page cache metadata tăng.
- Replica reassignment và recovery có nhiều đơn vị công việc hơn.

Metadata overhead không chỉ là dung lượng một metadata record. Nó còn là CPU/heap để parse, giữ state, truyền cập nhật, xử lý event và điều phối thay đổi.

### Replication factor ảnh hưởng metadata và runtime thế nào?

RF không nhân số logical partition ID. Một partition vẫn là một partition trong metadata, nhưng replica assignment/ISR có danh sách broker dài hơn và nhiều broker phải giữ local replica state hơn. Vì vậy RF tăng làm tăng tổng replica count, disk/network replication và local broker state.

Để capacity planning, theo dõi đồng thời:

- Tổng logical partition count toàn cluster.
- Tổng partition replica count.
- Replica local count theo broker.
- Kích thước metadata và tốc độ metadata change.
- Controller heap/CPU, metadata load/replay time và quorum health.

## 11. KRaft controller và giới hạn metadata

Trong KRaft, controller quorum duy trì metadata log và state của cluster. Controller leader xử lý các thay đổi metadata như tạo topic/partition, thay replica assignment, broker registration và thay đổi cấu hình.

Partition data log được replication giữa broker theo data plane; KRaft metadata log được replication giữa controller theo control plane. Đây là hai loại log khác nhau và có capacity/monitoring riêng.

Số partition lớn làm metadata state và snapshot lớn hơn; các đợt tạo topic, tăng partition hoặc reassignment hàng loạt tạo metadata change traffic. Nếu controller CPU/heap hoặc quorum latency đã cao, một thao tác tạo hàng nghìn partition có thể làm metadata operation chậm và ảnh hưởng điều phối cluster.

Theo dõi:

- Controller quorum availability và leader changes.
- Metadata log append/commit latency.
- Controller CPU, heap và GC.
- Metadata load/replay/snapshot duration.
- Broker metadata propagation và registration latency.
- Số lượng topic/partition/replica và tốc độ thay đổi.

Không suy ra metadata capacity chỉ từ disk còn trống trên broker. Control plane có thể trở thành bottleneck trước data disk.

## 12. Có giới hạn partition tối đa cố định không?

Không có một con số partition tối đa an toàn áp dụng cho mọi Kafka cluster. Một môi trường nhỏ với broker ít RAM, disk chậm và nhiều consumer group có thể gặp vấn đề ở quy mô thấp hơn cluster có controller/broker mạnh và workload đã benchmark.

Phân biệt:

- **num.partitions:** số partition mặc định cho topic được tạo mà không chỉ định rõ trong một số luồng auto-create; đây không phải hard cap tổng partition cluster và không tự thay đổi topic hiện hữu.
- **Topic partitions:** số partition cấu hình cho một topic.
- **Cluster-wide partitions:** tổng logical partition của tất cả topic, gồm cả internal topics.
- **Partition replicas:** tổng bản sao được phân bố trên broker, bằng tổng partition count nhân RF theo từng topic.
- **Metadata capacity:** năng lực controller/broker duy trì state, truyền và xử lý thay đổi; phụ thuộc phiên bản và phần cứng.

Không đặt một giới hạn giả định như “mỗi broker luôn chịu được X partition”. Hãy dùng benchmark, thử nghiệm failover và quan sát metadata load trên đúng phiên bản Kafka đang vận hành.

## 13. Tính cả internal topics và workload phát sinh

Partition budget không chỉ dành cho topic nghiệp vụ:

| Internal topic / workload | Ảnh hưởng cần tính |
|---|---|
| __consumer_offsets | Lưu committed offset và group metadata theo partition nội bộ |
| __transaction_state | Lưu trạng thái transaction và replication của internal topic |
| Kafka Streams repartition topics | Tạo partition để phân phối lại dữ liệu theo key |
| Kafka Streams changelog topics | Lưu state store changelog và replica |
| Kafka Connect config/offset/status topics | Lưu cấu hình, source offset và trạng thái connector |
| Retry/DLQ topics | Có thể nhân partition theo luồng xử lý và retry stage |

Một topology Kafka Streams có nhiều repartition/changelog topic có thể làm số partition replica thực tế cao hơn nhiều so với số partition input. Consumer group tăng cũng làm group metadata và offset workload tăng, dù không tự động tạo thêm partition cho business topic.

Các internal topic có cấu hình partition count/replication riêng. Kiểm tra cấu hình và số partition thực tế trong cluster; không mặc định chúng có cùng số partition với topic nghiệp vụ.

## 14. Tác động tới consumer group và rebalance

Mỗi partition cần được assign cho consumer member trong group. Khi số partition tăng:

- Assignment có nhiều phần tử hơn.
- Rebalance có thể cần truyền và xử lý nhiều metadata hơn.
- Consumer có thể phải mở thêm fetch state và xử lý nhiều partition.
- State store hoặc offset tracking của ứng dụng có thể tăng.
- Một số partition ít dữ liệu vẫn tạo overhead dù throughput thấp.

Tăng partition không nhất thiết làm rebalance chậm đáng kể trong mọi cluster; tác động phụ thuộc số group, member, partition assignment strategy và framework. Đo thời gian rebalance thực tế.

Với Kafka Streams, số task được tạo theo partition của source/repartition topic trong subtopology. Tăng partition có thể tăng task count và state/changelog footprint. Với Connect, số task thực tế còn phụ thuộc connector và cấu hình tasks.max; tăng topic partitions không tự động tăng task count theo tỷ lệ một-một.

## 15. Ví dụ kế hoạch partition hoàn chỉnh

Giả sử topic orders có:

- Peak ingress: 120 MiB/s.
- Peak event rate: 20.000 event/s.
- Throughput an toàn benchmark mỗi partition: 3 MiB/s.
- Một consumer worker xử lý ổn định: 600 event/s.
- Backlog recovery: 1.200.000 event trong 10 phút.
- Input tiếp tục: 20.000 event/s.
- RF=3, cluster có 6 broker.

Tính theo throughput:

\[
P_{throughput} = \left\lceil \frac{120}{3} \right\rceil = 40
\]

Tính theo consumer:

\[
P_{consumer} = \left\lceil \frac{20.000}{600} \right\rceil = 34
\]

Tính theo recovery:

\[
\mu_{required} = 20.000 + \frac{1.200.000}{600} = 22.000\ event/s
\]

\[
P_{recovery} = \left\lceil \frac{22.000}{600} \right\rceil = 37
\]

Số partition cơ sở:

\[
P_{base} = \max(40,34,37) = 40
\]

Chọn 48 partition để có khoảng 20% headroom so với throughput sizing, nếu broker/metadata budget cho phép.

Với RF=3:

\[
ReplicaCount = 48 \times 3 = 144
\]

Trên 6 broker, trung bình 24 local replicas/broker cho topic này. Cần kiểm tra rack placement, leader traffic, disk bytes và khả năng chịu mất một broker trước khi chốt.

### Bảng quyết định

| Ràng buộc | Partition yêu cầu |
|---|---:|
| Throughput | 40 |
| Consumer parallelism | 34 |
| Backlog recovery | 37 |
| Base | 40 |
| Chọn sau headroom | 48 |
| Replica với RF=3 | 144 |

Các số liệu trên chỉ là ví dụ. Thay bằng benchmark và growth forecast của workload thực tế.

## 16. Tạo topic và kiểm tra partition

Tạo topic với partition count và replication factor đã tính:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --create \
  --topic orders \
  --partitions 48 \
  --replication-factor 3
~~~

Kiểm tra assignment:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --describe \
  --topic orders
~~~

Tăng partition count cho topic hiện có:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --alter \
  --topic orders \
  --partitions 64
~~~

Lệnh alter này tăng số partition. Kafka không hỗ trợ giảm partition count trực tiếp cho topic hiện có; nếu cần giảm, thường phải tạo topic mới với partition count khác và migrate dữ liệu/producer/consumer theo kế hoạch.

Tăng partition count không tự động phân bố lại replica của các partition cũ. Partition mới được tạo theo assignment của broker/controller; nếu muốn thay đổi vị trí replica hiện hữu, cần reassignment riêng.

### Cấu hình num.partitions

Property broker num.partitions là giá trị mặc định cho một số topic được tạo mà không chỉ định partition count, đặc biệt khi auto topic creation được bật. Nó không phải giới hạn tổng partition và không thay đổi partition count của topic đã tồn tại.

Trong production, nên tạo topic có chủ đích bằng AdminClient hoặc quy trình quản trị có review; cân nhắc tắt auto.create.topics.enable để tránh topic tự phát sinh với partition count mặc định không phù hợp.

## 17. Tăng partition có thể gây thay đổi gì?

Trước khi alter:

1. Kiểm tra key ordering và partitioner.
2. Tính lại partition replica count theo RF.
3. Kiểm tra broker/controller metadata headroom.
4. Xác định consumer group và Kafka Streams state/task bị ảnh hưởng.
5. Đánh giá partition mới sẽ nhận key/traffic ra sao.
6. Chuẩn bị theo dõi rebalance, lag, ISR và disk.

Sau khi alter:

- Consumer group có thể rebalance để nhận partition mới.
- Producer có thể bắt đầu ghi record vào partition mới.
- Key mapping có thể thay đổi theo partitioner.
- Broker/controller xử lý metadata update và replica state mới.
- Kafka Streams có thể tạo thêm task hoặc thay đổi phân phối task/state.
- Internal topic/repartition strategy có thể cần đánh giá riêng.

Không tăng hàng loạt partition trên nhiều topic cùng lúc nếu chưa biết controller và broker xử lý metadata change ở tốc độ nào. Chia thành batch, quan sát ổn định rồi tiếp tục.

## 18. Tăng trưởng và partition budget

Lập forecast theo vòng đời 12–24 tháng hoặc theo chu kỳ planning của tổ chức:

| Mốc | Peak event/s | Peak MiB/s | Partitions dự kiến | RF | Replica count |
|---|---:|---:|---:|---:|---:|
| Hiện tại | 8.000 | 45 | 24 | 3 | 72 |
| +6 tháng | 12.000 | 68 | 36 | 3 | 108 |
| +12 tháng | 20.000 | 120 | 48 | 3 | 144 |
| +24 tháng | 30.000 | 180 | 72 | 3 | 216 |

Đây là ví dụ tăng trưởng; partition count không nhất thiết phải tăng ở mọi mốc. Có thể chọn số partition ban đầu đủ cho horizon dự kiến nếu metadata/disk budget cho phép và key mapping yêu cầu ổn định.

Một partition budget cấp cluster cần cộng:

- Business topics.
- Internal topics.
- Retry/DLQ topics.
- Kafka Streams repartition/changelog topics.
- Kafka Connect internal topics.
- Topic dành cho migration, replay và testing nếu dùng chung cluster.

Đặt ngưỡng cảnh báo nội bộ trước khi controller/broker chạm giới hạn đã benchmark. Ngưỡng này là policy của tổ chức, không phải một con số mặc định của Apache Kafka.

## 19. Monitoring partition và metadata

Theo dõi các nhóm metric:

| Nhóm | Metric cần quan sát | Mục tiêu |
|---|---|---|
| Partition inventory | Logical partition count, replica count, partitions per broker | Phát hiện tăng trưởng và phân bố lệch |
| Leader | Leader count, leader traffic theo broker | Phát hiện leader imbalance |
| Replication | ISR size, under-replicated/offline partitions, replication lag | Bảo vệ durability |
| Storage | Replica bytes, log directory free space, segment count | Capacity và disk headroom |
| Broker runtime | Heap/GC, CPU, request queue, network processor idle, file descriptors | Tìm overhead do nhiều partition |
| Controller | Metadata log/commit latency, heap/CPU, snapshot/replay duration, quorum health | Theo dõi metadata capacity |
| Consumer | Rebalance duration, assignment count, lag/age theo partition | Đánh giá consumer overhead |
| Streams/Connect | Task count, state restore, changelog/repartition partitions, connector tasks | Theo dõi partition phát sinh |

Metric name chính xác phụ thuộc Kafka version, JMX reporter và exporter. Xác nhận metric có trong phiên bản triển khai; không giả định một dashboard generic sẽ hiển thị metadata heap hoặc controller timing cùng tên trên mọi release.

### Cảnh báo gợi ý

- Tổng logical partitions hoặc replica local count tiến gần partition budget đã benchmark.
- Controller heap/GC hoặc metadata operation latency tăng liên tục.
- Thời gian broker startup/metadata load tăng sau mỗi đợt mở rộng.
- File descriptor hoặc segment count tiến gần giới hạn OS.
- Rebalance duration và consumer lag tăng sau khi tăng partition.
- Under-replicated partitions xuất hiện trong lúc metadata/reassignment load cao.
- Một broker có replica bytes hoặc leader traffic vượt headroom.

## 20. Benchmark và xác nhận giới hạn thực tế

Benchmark phải mô phỏng gần production:

1. Dùng record size và key distribution thực tế.
2. Bật replication factor, acks và compression giống production.
3. Có số consumer group/member và fetch workload dự kiến.
4. Tăng partition theo từng nấc, không chỉ test một cấu hình cuối.
5. Theo dõi throughput, p95/p99 latency, ISR, disk, network, heap/GC và controller.
6. Thử rolling restart, broker failure, leader election và consumer rebalance.
7. Đo thời gian metadata load/replay và thời gian phục hồi.

Không chỉ benchmark produce throughput. Cluster có thể ghi nhanh nhưng khởi động chậm, rebalance kéo dài hoặc controller bị quá tải khi metadata change lớn.

### Ma trận thử nghiệm

| Thử nghiệm | Điều cần xác nhận |
|---|---|
| Tăng partition 2x | Throughput có tăng và metadata cost thay đổi ra sao |
| Tăng RF | Disk/network/ISR và recovery time |
| Tăng consumer group/member | Rebalance và coordinator overhead |
| Tạo nhiều topic/partition | Controller metadata load và broker startup |
| Rolling restart broker | Metadata propagation, leader recovery và consumer impact |
| Broker failure | Replica placement, ISR và khả năng phục hồi |
| Kafka Streams repartition | Task count, state restore và changelog footprint |

## 21. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Thêm partition nhưng throughput không tăng | Broker hoặc downstream là bottleneck; key skew | Xem per-partition rate, broker CPU/network/disk và sink latency |
| Nhiều consumer idle | Số consumer vượt số partition có thể assign | Kiểm tra group assignment và subscription |
| Một partition luôn lag cao | Hot key hoặc traffic skew | Đo input bytes/event theo partition và key distribution |
| Broker startup chậm | Nhiều local replicas, log/segment hoặc metadata load lớn | Kiểm tra startup logs, disk, file handles, heap và metadata load |
| Controller chậm khi tạo topic | Metadata operation burst hoặc controller resource pressure | Theo dõi quorum/metadata latency và chia nhỏ batch |
| Rebalance lâu sau khi tăng partition | Assignment lớn, nhiều group hoặc framework state migration | Đo rebalance duration, group size và task restore |
| Disk tăng nhanh hơn dự tính | RF, retention, compression ratio hoặc internal topics chưa tính | Đối soát logical partitions, replica bytes và log dirs |
| Ordering theo key bị sai sau khi tăng partition | Key được ánh xạ sang partition khác sau thay đổi count | Kiểm tra partitioner và migration/cutover strategy |

## 22. Production checklist

- [ ] Có peak event/s, byte/s, record size và growth forecast cho từng topic.
- [ ] Đã benchmark throughput an toàn mỗi partition với RF/acks/compression giống production.
- [ ] Đã tính partition theo throughput, consumer parallelism và backlog recovery.
- [ ] Đã xác định ordering requirement, key skew và tác động khi tăng partition.
- [ ] Đã tính logical partition count và partition replica count riêng biệt.
- [ ] Đã tính số replica local trung bình và headroom theo từng broker/rack.
- [ ] Đã cộng internal topics, retry/DLQ, Streams repartition/changelog và Connect topics.
- [ ] Đã đánh giá metadata load, controller quorum, heap/CPU, startup/replay và metadata change rate.
- [ ] Đã kiểm tra disk, segment/index, file descriptors và page cache overhead.
- [ ] Có partition budget nội bộ dựa trên benchmark thay vì một ngưỡng chung.
- [ ] Topic được tạo với partition count có chủ đích; kiểm soát auto topic creation.
- [ ] Có kế hoạch migration nếu cần giảm partition count.
- [ ] Tăng partition theo batch và theo dõi rebalance, ISR, latency và SLO.
- [ ] Có benchmark failover, rolling restart và recovery trước khi chốt capacity.

Partition count cần đáp ứng throughput, consumer parallelism và recovery objective, nhưng mỗi partition cũng làm tăng replica, runtime state và metadata mà broker/controller phải quản lý. Hãy tính từ workload thực tế, cộng internal topics và replication factor, kiểm tra key ordering, rồi xác nhận bằng benchmark/failover trên đúng Kafka version. Một partition plan tốt vừa đáp ứng tải hiện tại, vừa có headroom tăng trưởng mà không đẩy metadata và vận hành cluster vượt capacity.
