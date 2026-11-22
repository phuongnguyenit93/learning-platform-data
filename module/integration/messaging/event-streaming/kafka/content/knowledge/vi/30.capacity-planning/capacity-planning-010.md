# Đánh giá tổng chi phí và tiêu chí mở rộng cụm

Hoạch định năng lực Kafka không dừng ở việc chọn số broker hoặc số partition. Một cluster phải đáp ứng throughput ở giờ cao điểm, lưu đủ dữ liệu trong retention, duy trì replication khi có lỗi, phục vụ các consumer group, đồng thời có ngân sách cho network, backup, quan sát và vận hành. Nếu chỉ tính chi phí máy chủ mà bỏ qua các phần này, dự toán ban đầu thường thấp hơn đáng kể so với tổng chi phí thực tế.

Capacity planning cần trả lời ba câu hỏi:

1. Workload hiện tại và dự báo tăng trưởng cần bao nhiêu tài nguyên?
2. Chi phí toàn vòng đời của phương án triển khai là bao nhiêu?
3. Ngưỡng đo lường nào cho biết cần scale up, scale out, tái phân phối partition hoặc tối ưu workload?

Bài học này xây dựng cách tính từ workload đến storage, broker, network và chi phí vận hành; sau đó chuyển các phép tính thành tiêu chí mở rộng có thể theo dõi.

## 1. Phạm vi của một capacity plan

Một capacity plan nên bao phủ toàn bộ hệ thống event streaming:

| Lớp | Thành phần cần tính |
|---|---|
| Kafka cluster | Broker, CPU, RAM, disk, network, partition, replica |
| Data lifecycle | Retention, compaction, tiered storage nếu sử dụng, backup và disaster recovery |
| Client | Producer, consumer group, Kafka Streams, Kafka Connect |
| Hạ tầng | VM/instance, volume, load balancer, DNS, rack/AZ, network transfer |
| Vận hành | Monitoring, logging, alerting, security, upgrade, on-call và diễn tập phục hồi |
| Môi trường | Production, staging, development, performance test và DR |

Chi phí cần được đánh giá theo cùng một đơn vị thời gian, thường là tháng hoặc năm. Không so sánh giá broker theo tháng với chi phí network theo GB hoặc chi phí nhân sự theo năm mà không quy đổi.

### Phân biệt capacity và cost

- **Capacity** là khả năng phục vụ workload trong các giới hạn throughput, latency, storage, availability và recovery.
- **Cost** là nguồn lực tài chính để mua, thuê, vận hành và duy trì capacity đó.
- **Efficiency** là lượng workload/SLO đạt được trên mỗi đơn vị chi phí.

Cluster rẻ nhất chưa chắc có tổng chi phí thấp nhất. Nếu cluster thiếu headroom, mỗi lần peak hoặc broker failure có thể gây lag, incident và công việc vận hành bổ sung. Ngược lại, provision quá dư gây lãng phí compute, disk và network trong thời gian dài.

## 2. Thu thập workload trước khi tính tài nguyên

Không bắt đầu bằng số broker mong muốn. Trước tiên, mô tả workload theo dữ liệu đo được hoặc giả định đã được xác nhận:

| Đầu vào | Cần ghi nhận |
|---|---|
| Event rate | Average, peak, burst và thời lượng peak (records/s) |
| Event size | Kích thước trung bình, p95/p99 và phân bố kích thước |
| Ingress | Byte/s producer gửi vào cluster |
| Consumer groups | Số group độc lập, throughput và số lần đọc dữ liệu |
| Retention | Thời gian giữ dữ liệu theo topic |
| Cleanup policy | delete, compact hoặc compact,delete |
| Replication | Replication factor và min.insync.replicas |
| Availability | Số broker/AZ có thể mất mà vẫn đáp ứng SLO |
| Processing | Kafka Streams state, Connect tasks, retry và DLQ |
| Growth | Tăng trưởng dữ liệu và traffic theo tháng/quý/năm |
| Latency | p95/p99 produce, consume và end-to-end |

Phân loại topic theo workload. Topic sự kiện giao dịch có thể cần retention dài và RF cao; topic telemetry có thể có record rate lớn nhưng retention ngắn; compacted topic thường giữ trạng thái mới nhất theo key nên không thể tính dung lượng chỉ từ tổng event rate nhân retention như topic delete-only.

### Dùng peak có thời lượng, không chỉ peak tức thời

Một đợt peak 2 phút và một đợt peak kéo dài 6 giờ có ảnh hưởng khác nhau:

- Peak ngắn có thể được hấp thụ bằng producer buffer, broker headroom và consumer catch-up.
- Peak dài làm tăng disk growth, network utilization và consumer lag nếu downstream không theo kịp.
- Burst lặp lại thường xuyên có thể cần capacity thường trực hoặc cơ chế admission control.

Ghi cả peak rate lẫn thời lượng và tần suất. Nếu chỉ lấy trung bình ngày, dự toán có thể bỏ sót giờ cao điểm; nếu lấy peak tức thời làm tải liên tục, dự toán có thể quá dư.

## 3. Tính ingress và dữ liệu lưu trữ

Gọi:

- R: số record mỗi giây.
- S: kích thước trung bình của record trước compression, byte.
- C: tỷ lệ kích thước sau compression so với trước compression; ví dụ 0,45 nghĩa là còn 45%.
- T: retention tính bằng giây.
- RF: replication factor.
- F: hệ số dự phòng cho index, segment, metadata, compaction và dao động workload.
- U: tỷ lệ dung lượng disk tối đa dự kiến sử dụng, ví dụ 0,70.

Ingress trước compression:

\[
B_{raw} = R \times S
\]

Ingress sau compression ước tính:

\[
B_{compressed} = R \times S \times C
\]

Dung lượng một bản sao dữ liệu theo retention:

\[
D_{leader} = B_{compressed} \times T
\]

Dung lượng vật lý ước tính cho các replica:

\[
D_{physical} = D_{leader} \times RF \times F
\]

Dung lượng disk cần provision:

\[
D_{provisioned} = \frac{D_{physical}}{U}
\]

Đây là mô hình sizing sơ bộ cho topic có cleanup policy delete. Thực tế cần cộng internal topics, state/changelog, DLQ, segment/index overhead, dữ liệu tạm khi reassignment và compaction. Không dùng công thức này nguyên xi cho compacted topic hoặc tiered storage.

### Ví dụ tính storage

Giả sử một topic có:

- 50.000 record/s ở peak kéo dài.
- Record trung bình 2 KiB (2.048 byte).
- Compression ratio đo được là 0,45.
- Retention 7 ngày.
- Replication factor 3.
- Hệ số dự phòng F=1,2.
- Mục tiêu disk utilization U=0,70.

Để tạo phép tính bảo thủ, ví dụ giả định peak 50.000 record/s được duy trì liên tục trong toàn bộ 7 ngày retention. Nếu peak chỉ kéo dài vài giờ, hãy dùng biểu đồ ingress theo thời gian hoặc average có trọng số cho từng khoảng thay vì nhân peak rate với toàn bộ retention.

Ingress trước compression:

\[
50.000 \times 2.048 = 102.400.000\ byte/s
\]

Tương đương khoảng 102,4 MB/s theo đơn vị thập phân.

Ingress sau compression:

\[
102,4 \times 0,45 = 46,08\ MB/s
\]

Dung lượng một bản sao trong 7 ngày:

\[
46,08 \times 86.400 \times 7 \approx 27,87\ TB
\]

Nhân replication factor và hệ số dự phòng:

\[
27,87 \times 3 \times 1,2 \approx 100,33\ TB
\]

Chia cho mức utilization mục tiêu 70%:

\[
D_{provisioned} = 100,33 / 0,70 \approx 143,33\ TB
\]

Như vậy, riêng topic này cần khoảng 143 TB dung lượng disk provision theo giả định trên. Nếu phân bố đều trên 6 broker, trung bình gần 23,9 TB disk provision cho mỗi broker. Đây mới là sizing storage; chưa chứng minh 6 broker đủ CPU, network hoặc throughput.

### Cẩn thận với compression ratio

Compression ratio phụ thuộc loại dữ liệu, codec, batch size và cách producer gom record. JSON lặp field có thể nén tốt; payload đã nén hoặc mã hóa có thể gần như không giảm thêm. Dùng kết quả benchmark trên dữ liệu đại diện thay vì lấy tỷ lệ quảng cáo của codec.

Kafka nén theo batch. Nếu producer gửi các batch quá nhỏ, compression ratio có thể kém hơn benchmark với batch lớn. Tăng compression cũng tiêu tốn CPU; cần đo cả network/disk tiết kiệm được và CPU tăng thêm.

## 4. Retention, compaction và dữ liệu không thể tính bằng một công thức

### Topic dùng cleanup.policy=delete

Với topic delete-only, dữ liệu được giữ theo retention time/size và xóa theo segment. Dung lượng gần đúng có thể tính từ ingress sau compression nhân retention. Tuy nhiên, segment hiện tại, thời điểm cleanup và cấu hình retention tạo ra độ lệch so với phép tính liên tục.

### Topic dùng cleanup.policy=compact

Compaction giữ giá trị mới nhất theo key và có thể giữ tombstone trong khoảng delete retention. Dung lượng phụ thuộc:

- Số key duy nhất.
- Kích thước value mới nhất của mỗi key.
- Tần suất cập nhật key.
- Tombstone và delete retention.
- Tốc độ log cleaner và lượng dữ liệu chờ compact.

Không lấy toàn bộ event rate nhân retention để ước lượng compacted topic như thể mọi phiên bản đều được giữ. Ngược lại, cũng không giả định compaction xóa dữ liệu ngay khi có update; các segment cũ chỉ được dọn khi cleaner xử lý.

### Topic dùng compact,delete

Topic có thể kết hợp giữ trạng thái mới nhất theo key với giới hạn retention. Hãy mô hình riêng cả số key, update rate, tombstone retention và retention theo thời gian/dung lượng. Xác nhận semantics có phù hợp với consumer cần khôi phục state hay không.

### Internal topics và state store

Capacity plan cần cộng:

- Kafka Streams changelog topics.
- Repartition topics.
- Kafka Connect config, offset, status topics.
- Retry topics và DLQ.
- Transaction state/metadata overhead.
- Topic schema history hoặc topic nội bộ riêng của connector plugin.

Với Kafka Streams, local state store trên từng instance cũng cần disk riêng; changelog topic trên broker có replication factor và retention/compaction riêng. Không tính changelog là thay thế cho local disk hoặc cộng hai dung lượng vào cùng một filesystem.

## 5. Tính số broker từ storage, throughput và fault tolerance

Số broker tối thiểu cần xét nhiều ràng buộc:

\[
N_{brokers} \geq \max(N_{storage}, N_{throughput}, N_{failure})
\]

Trong đó:

- N_storage: số broker cần để chứa replica trong giới hạn disk utilization.
- N_throughput: số broker cần để chịu tải network/CPU/disk đã benchmark.
- N_failure: số broker cần để cluster còn đáp ứng SLO khi mất broker/AZ theo mục tiêu availability.

### Ước lượng theo storage

Nếu tổng dung lượng provision cần là D_provisioned, disk provision khả dụng mỗi broker là D_broker:

\[
N_{storage} =
\left\lceil
\frac{D_{provisioned}}{D_{broker}}
\right\rceil
\]

Ví dụ cần 143,3 TB và mỗi broker có 24 TB disk provision:

\[
N_{storage} = \lceil 143,3 / 24 \rceil = 6
\]

Sáu broker là mức tối thiểu theo phép chia dung lượng. Nếu cần chịu lỗi một broker mà vẫn giữ utilization dưới ngưỡng, phải tính lại với dung lượng của broker còn lại sau failure:

\[
D_{available,N-1} = (N-1)\times D_{broker}
\]

Với mục tiêu vẫn chứa đủ dung lượng đã tính sau khi mất một broker, số broker cần ít nhất:

\[
N_{storage,N-1} =
\left\lceil \frac{D_{provisioned}}{D_{broker}} \right\rceil + 1
\]

Trong ví dụ 143,3 TB và 24 TB/broker, cần 7 broker nếu muốn sau khi mất một broker vẫn còn 6 broker với tổng 144 TB provision. Sáu broker ban đầu chỉ đáp ứng storage khi tất cả broker đều khỏe. Đây vẫn là phép chia dung lượng tổng; cần kiểm tra replica placement, AZ/rack, disk headroom và lượng dữ liệu phải rebuild sau failure.

### Ước lượng theo throughput

Benchmark một broker trong điều kiện production-like để xác định throughput bền vững ở latency SLO. Gọi:

- B_cluster: tổng byte/s cần broker phục vụ, tính cả write, fetch và replication traffic theo mô hình đo.
- B_broker: throughput bền vững của một broker ở cấu hình tương đương.
- H: headroom cho peak, skew và recovery.

Ước lượng:

\[
N_{throughput} =
\left\lceil
\frac{B_{cluster}\times H}{B_{broker}}
\right\rceil
\]

Không cộng trùng traffic. Ví dụ nếu benchmark B_broker đã bao gồm replication và consumer fetch với đúng replication factor, không nhân replication lần nữa trong B_cluster. Ghi rõ throughput đo là ingress, egress, tổng NIC hay disk throughput để phép tính có ý nghĩa.

### Kiểm tra fault tolerance

Nếu cần chịu mất một broker, cluster còn đủ broker và replica để:

- Duy trì leader cho mọi partition.
- Đạt min.insync.replicas của topic quan trọng.
- Phục vụ producer/consumer ở mức SLO đã chọn.
- Đồng bộ lại replica sau khi broker quay lại hoặc được thay thế.

Replication factor 3 không tự bảo đảm chịu mọi lỗi. Nếu ba replica của partition cùng nằm trong một AZ hoặc cùng một failure domain, mất AZ có thể làm partition offline. Dùng rack awareness và phân bố replica qua các failure domain theo thiết kế.

## 6. Network capacity và chi phí truyền dữ liệu

Network thường bị đánh giá thấp vì chỉ nhìn producer ingress. Một cluster còn phải truyền:

- Producer đến partition leader.
- Leader đến follower để replication.
- Broker đến các consumer group.
- Broker đến Kafka Streams/Connect client.
- Cross-AZ traffic nếu leader, follower, consumer hoặc storage ở các zone khác nhau.
- Reassignment, recovery và restore traffic.

Một mô hình tổng quát:

\[
B_{network} =
B_{produce} + B_{replication} + B_{consume} + B_{recovery}
\]

Đây là tổng traffic theo hướng cần tính cho NIC/đường truyền; phải tránh đếm trùng cùng một byte ingress/egress khi đo theo một interface hoặc toàn cluster.

Với RF=3, mỗi record được ghi vào leader và được follower fetch để duy trì hai replica còn lại. Vì vậy replication tạo thêm traffic nội bộ đáng kể. Khi nhiều consumer group độc lập đọc cùng topic, dữ liệu có thể được fetch nhiều lần; số group tăng có thể làm broker egress tăng dù ingress không đổi.

### Cross-AZ transfer

Nếu replica nằm ở AZ khác leader, replication traffic có thể phát sinh chi phí liên vùng theo pricing của cloud. Consumer đọc từ broker ở AZ khác cũng có thể tạo cross-AZ transfer. Chi phí phụ thuộc topology mạng, routing, rack-aware replica assignment, follower fetching và nhà cung cấp cloud.

Để giảm chi phí:

- Đặt producer/consumer gần broker hoặc trong cùng region khi phù hợp.
- Bật rack awareness và thiết kế replica distribution theo AZ.
- Đánh giá follower fetching nếu workload và phiên bản hỗ trợ.
- Tránh consumer group dư thừa đọc toàn bộ topic nếu không cần.
- Dùng compression và batching để giảm byte truyền.
- Theo dõi network egress/cross-zone theo topic, broker và consumer group.

Không hy sinh durability hoặc availability chỉ để giảm cross-AZ traffic. Phân bố replica trong cùng một AZ có thể rẻ hơn nhưng làm tăng blast radius khi AZ lỗi.

## 7. CPU, RAM và disk I/O

### CPU

CPU broker tiêu thụ cho:

- Network request handling.
- TLS/SASL authentication và encryption.
- Compression/decompression.
- Replication và request scheduling.
- Log cleaning, compaction và index maintenance.

CPU client tiêu thụ cho serialization, compression, deserialization, validation và xử lý nghiệp vụ. Kafka Streams/Connect cần thêm CPU cho processor task, connector task và chuyển đổi dữ liệu.

### RAM

RAM được dùng cho:

- JVM heap và object/request buffers.
- Page cache của hệ điều hành.
- Network buffers.
- Producer accumulator và consumer fetch buffers.
- Kafka Streams cache và RocksDB block cache.
- Kafka Connect converter, SMT và connector buffers.

Không cấp gần hết RAM vật lý cho JVM heap. Kafka broker dựa nhiều vào page cache của hệ điều hành để phục vụ log segment. JVM heap quá lớn có thể làm giảm page cache và tăng thời gian GC.

### Disk I/O

Disk phải chịu:

- Append log của leader.
- Fetch/replication của follower.
- Consumer read.
- Index/segment rolling và retention cleanup.
- Log compaction.
- Reassignment và recovery.

SSD/NVMe có thể cải thiện IOPS/latency nhưng chi phí cao hơn. HDD dung lượng lớn có thể phù hợp workload throughput tuần tự, nhưng cần benchmark random read, compaction và latency p99. Không chọn storage chỉ dựa trên MB/s tuần tự được công bố.

## 8. Tính tổng chi phí sở hữu (TCO)

TCO của Kafka nên tính cả hạ tầng và vận hành:

\[
TCO =
C_{compute} + C_{disk} + C_{network} + C_{managed}
+ C_{observability} + C_{backup/DR} + C_{operations}
\]

Trong đó:

| Khoản mục | Thành phần chi phí |
|---|---|
| Compute | Broker VM/instance, controller, Connect worker, Streams application |
| Disk | Data volume, IOPS/throughput tier, snapshot và dung lượng dự phòng |
| Network | Ingress/egress, cross-AZ, cross-region, NAT, private connectivity |
| Managed service | Phí dịch vụ Kafka managed nếu dùng, storage/throughput tier và support plan |
| Observability | Metrics, logs, traces, retention của telemetry và alerting |
| Backup/DR | Backup, object storage, replication liên vùng, cluster dự phòng và diễn tập |
| Operations | Nhân sự on-call, upgrade, patch, capacity review, security và incident response |
| Non-production | Dev, staging, performance test, integration test và môi trường thử nâng cấp |

Apache Kafka mã nguồn mở không có nghĩa chi phí vận hành bằng 0. Với self-managed, chi phí phần mềm có thể thấp nhưng tổ chức chịu trách nhiệm provisioning, patching, monitoring, scaling, backup, security và incident response. Với managed Kafka, một phần công việc chuyển sang nhà cung cấp nhưng vẫn cần tính phí dịch vụ, network, storage, client, DR và giới hạn tính năng.

### Bảng dự toán theo tháng

Tạo bảng theo từng môi trường và từng loại tài nguyên:

| Hạng mục | Số lượng | Đơn giá/tháng | Thành tiền/tháng |
|---|---:|---:|---:|
| Broker compute | N broker | Giá/instance | N × giá |
| Controller/metadata nodes | N controller | Giá/instance | N × giá |
| Broker data disk | TB provision | Giá/TB | TB × giá |
| IOPS/throughput add-on | Theo volume | Giá tier | Theo báo giá |
| Cross-AZ/network egress | GB/tháng | Giá/GB | GB × giá |
| Connect/Streams compute | Instance/task capacity | Giá/instance | Theo cấu hình |
| Metrics/log retention | GB/tháng | Giá/GB | Theo ingest và retention |
| Backup/DR | Storage + transfer | Giá tương ứng | Theo chính sách |
| Operations | Giờ/người-tháng | Cost nội bộ | Theo phân bổ |

Tổng chi phí tháng:

\[
C_{monthly} = \sum_i Quantity_i \times UnitCost_i
\]

Chi phí năm:

\[
C_{annual} = 12 \times C_{monthly} + C_{one\_time}
\]

C_one_time có thể gồm migration, setup, load test, đào tạo, xây dựng automation và chuyển đổi dữ liệu. Không đưa các khoản one-time vào monthly run rate rồi nhân 12 nếu muốn so sánh TCO chính xác.

### Đo hiệu quả chi phí

TCO tuyệt đối giúp lập ngân sách, nhưng để so sánh các phương án có quy mô khác nhau nên tính thêm đơn giá workload:

\[
CostPerMillionEvents =
\frac{C_{monthly}}{Events_{monthly}/1.000.000}
\]

Hoặc:

\[
CostPerGBMonth =
\frac{C_{monthly}}{AverageStoredGB}
\]

Chỉ so sánh hai chỉ số này khi retention, replication, SLO, availability và phạm vi chi phí được tính giống nhau. Một cluster có cost/GB-month thấp hơn nhưng không đáp ứng RPO/RTO không phải phương án tương đương.

### Self-managed và managed Kafka

| Tiêu chí | Self-managed | Managed Kafka |
|---|---|---|
| Compute/storage | Tự chọn và quản lý | Theo tier/instance/throughput của nhà cung cấp |
| Patching/upgrade | Đội vận hành chịu trách nhiệm | Nhà cung cấp hỗ trợ hoặc quản lý một phần |
| Scaling | Tự lập kế hoạch và reassignment | Có thể có cơ chế scale, vẫn cần đánh giá giới hạn |
| Network | Tự chịu chi phí cloud/network | Có thể tính riêng egress, cross-zone hoặc private link |
| Observability | Tự triển khai hoặc mua dịch vụ | Có dashboard tích hợp, có thể tính phí telemetry |
| Recovery | Tự thiết kế và diễn tập | SLA/DR phụ thuộc gói dịch vụ và cấu hình |
| Flexibility | Kiểm soát sâu cấu hình | Có giới hạn theo dịch vụ |
| Operations | Nhiều trách nhiệm nội bộ | Giảm một phần việc quản trị cluster |

So sánh bằng cùng workload, SLO, retention, RF/availability và DR target. Không so giá một cụm managed nhỏ với self-managed cluster có thêm DR, monitoring và nhân sự trực vận hành.

## 9. Chi phí của headroom và khả năng chịu lỗi

Headroom là capacity chưa dùng hết để hấp thụ peak, tăng trưởng và sự cố. Headroom quá thấp làm cluster dễ chạm ngưỡng; headroom quá cao làm chi phí idle tăng.

Một số headroom cần tính riêng:

- Disk headroom để retention không lấp đầy volume và compaction có chỗ tạo file tạm.
- Network headroom để replication, recovery và consumer fetch không bão hòa NIC.
- CPU headroom để chịu compression, TLS, log cleaner và request burst.
- Broker headroom để một broker mất mà các broker còn lại không vượt SLO.
- Consumer headroom để xử lý peak hoặc downstream phục hồi sau outage.

Không dùng một tỷ lệ headroom cho tất cả tài nguyên. Disk utilization 70% có thể là mục tiêu dự phòng hợp lý trong một môi trường, trong khi CPU hoặc network cần ngưỡng khác dựa trên benchmark và burst profile.

### N+1 capacity

Nếu yêu cầu cluster tiếp tục phục vụ sau khi mất một broker, sizing phải chứng minh N-1 broker còn lại chịu được workload cần thiết. Nếu chỉ đủ tải khi tất cả N broker đều khỏe, hệ thống không có headroom cho failure.

Một kiểm tra đơn giản:

\[
LoadPerBroker_{N-1} =
\frac{ClusterLoad}{N-1}
\]

Đây là trung bình lý tưởng. Thực tế phải xét leader/replica assignment, rack, key skew và broker bị mất đang giữ partition nào. Cần kiểm thử failure thực tế trong môi trường tương đương production.

## 10. Tiêu chí mở rộng cụm

Không scale chỉ vì một metric vượt ngưỡng trong vài giây. Dùng ngưỡng cảnh báo, ngưỡng hành động và thời gian duy trì để tránh phản ứng quá mức với burst ngắn.

| Tín hiệu | Cảnh báo sớm | Cần đánh giá scale khi |
|---|---|---|
| Disk utilization | Tăng đều, còn ít headroom | Dự báo chạm ngưỡng trước lần capacity review tiếp theo hoặc compaction/recovery không còn chỗ |
| Broker CPU | Cao kéo dài | Request queue/latency tăng và CPU là bottleneck đã xác nhận |
| Network | NIC bão hòa theo chu kỳ | Produce/fetch/replication latency tăng do network |
| Request latency | p95/p99 xấu dần | Vượt SLO liên tục dù client/batch đã tối ưu |
| Under-replicated partitions | Tăng bất thường | Replica không catch up và durability margin suy giảm |
| Consumer lag | Tăng liên tục | Consumer throughput thấp hơn ingress trong khoảng thời gian dài |
| Partition skew | Một vài partition nóng | Hot partition làm lag/latency vượt SLO trong khi phần còn lại rảnh |
| Recovery time | Restore/reassignment kéo dài | RTO mục tiêu không đạt hoặc recovery cạnh tranh tải production |
| Growth forecast | Tốc độ tăng vượt dự báo | Dự báo capacity hết trước lead time mua/provision |

### Dự báo thời điểm hết dung lượng

Nếu disk usage hiện tại là D_now, tốc độ tăng trung bình là G byte/ngày và giới hạn vận hành là D_limit:

\[
DaysToLimit =
\frac{D_{limit} - D_{now}}{G}
\]

Ví dụ disk đang dùng 18 TB, giới hạn vận hành là 24 TB, tăng 0,2 TB/ngày:

\[
DaysToLimit = (24-18)/0,2 = 30\ ngày
\]

Nếu lead time mua/provision disk là 21 ngày, không nên đợi đến ngày thứ 29 mới bắt đầu mở rộng. Cần trigger theo forecast và buffer cho peak, maintenance, reassignment.

### Định nghĩa ngưỡng có thể hành động

Một alert tốt phải trả lời:

- Metric nào vượt ngưỡng?
- Scope là cluster, broker, topic, partition hay consumer group?
- Vượt trong bao lâu?
- SLO hoặc durability nào bị đe dọa?
- Người trực cần kiểm tra gì trước khi scale?
- Scale theo chiều nào và có tác động ordering/reassignment không?

Alert “CPU > 80%” đơn lẻ không đủ để quyết định thêm broker. Cần đối chiếu request latency, queue, disk, network và throughput để xác định bottleneck.

## 11. Chọn scale up hay scale out

### Scale up

Tăng CPU, RAM, disk IOPS hoặc network của broker hiện tại.

Phù hợp khi:

- Broker đang thiếu CPU nhưng partition distribution tương đối tốt.
- Disk throughput/IOPS là bottleneck và có thể nâng volume.
- Network interface hoặc instance bandwidth quá thấp.
- Muốn tăng capacity mà không tăng số broker/replica assignment.

Giới hạn:

- Có thể phải restart broker.
- Một broker lớn hơn vẫn là một failure domain.
- Không giải quyết hot key đơn lẻ nếu partition leader vẫn là bottleneck.
- Chi phí instance lớn có thể tăng phi tuyến.

### Scale out

Thêm broker để tăng tổng compute, disk và network capacity.

Phù hợp khi:

- Nhiều broker đồng thời chạm giới hạn.
- Storage cần mở rộng vượt dung lượng hợp lý của một broker.
- Cần phân phối replica/leader trên nhiều failure domain.
- Có đủ partition để tận dụng broker mới.

Lưu ý: thêm broker không tự động di chuyển mọi partition replica hiện có sang broker mới. Cần partition reassignment hoặc công cụ cân bằng tương ứng; quá trình di chuyển tạo thêm network và disk I/O.

### Tăng partition

Tăng partition giúp tạo thêm đơn vị song song cho consumer group và một số workload. Tuy nhiên, tăng partition count không tự phân phối lại record cũ. Với keyed record, partition mapping mới có thể khác mapping cũ và ảnh hưởng ordering theo key.

Trước khi tăng partition:

- Xác nhận consumer/task thực sự thiếu parallelism.
- Kiểm tra key skew và ordering requirement.
- Đánh giá số replica, file segment, metadata và recovery.
- Lập kế hoạch migration nếu cần giữ ordering theo entity.

Không dùng tăng partition như biện pháp thay thế cho thêm broker khi bottleneck thực tế là disk hoặc network của broker hiện tại.

## 12. Dự báo tăng trưởng và lead time

Capacity plan phải nhìn xa hơn thời điểm hiện tại. Ghi lại:

- Tăng trưởng event rate theo business forecast.
- Tăng trưởng record size do schema/payload mới.
- Số consumer group mới dự kiến.
- Retention mới do compliance hoặc nghiệp vụ.
- Thay đổi RF, min ISR hoặc DR topology.
- Số connector/Streams application và state store mới.
- Lead time đặt instance, volume, IP, quota và phê duyệt cloud.

Nếu data volume tăng 8% mỗi tháng, không nên cộng 8% dung lượng tuyến tính cho cả năm. Tăng trưởng lũy kế:

\[
D_n = D_0 \times (1+g)^n
\]

Trong đó g là tỷ lệ tăng mỗi kỳ và n là số kỳ. Với tăng trưởng 8%/tháng trong 12 tháng:

\[
(1,08)^{12} \approx 2,52
\]

Dung lượng có thể tăng khoảng 2,5 lần nếu tốc độ tăng duy trì. Đây là lý do cần forecast và review định kỳ thay vì chờ disk gần đầy.

## 13. Tối ưu chi phí mà không làm suy giảm SLO

Các đòn bẩy nên xem xét:

1. **Compression và batching**: giảm network/disk bytes; đo CPU và latency đi kèm.
2. **Retention đúng nhu cầu**: không giữ mọi topic lâu như nhau.
3. **Cleanup policy đúng semantics**: delete cho event history, compact cho latest state, hoặc kết hợp khi phù hợp.
4. **Giảm consumer group dư thừa**: mỗi group độc lập có thể tạo thêm broker egress.
5. **Tối ưu payload**: bỏ field không cần, schema gọn, tránh payload lặp.
6. **Tách workload**: topic/cluster riêng cho workload có SLO hoặc retention rất khác nhau nếu có lợi.
7. **Tận dụng tiered storage**: nếu phiên bản Kafka/dịch vụ hỗ trợ và workload phù hợp, cân nhắc chuyển segment cũ sang object storage.
8. **Giảm cross-AZ transfer**: bố trí client/replica hợp lý nhưng vẫn giữ failure-domain requirement.
9. **Tắt môi trường không cần thiết**: giảm số broker/dev cluster chạy ngoài giờ nếu quy trình cho phép.
10. **Tự động hóa reassignment và capacity review**: giảm công sức vận hành lặp lại.

Tiered storage không có nghĩa mọi dữ liệu đều miễn phí trên object storage. Cần tính phí object storage, request, retrieval, cache/local tier, network và giới hạn tính năng. Với Kafka managed, khả năng tiering và giá phụ thuộc dịch vụ cụ thể.

Không giảm RF, retention hoặc min ISR chỉ để đạt mục tiêu chi phí khi chưa đánh giá durability, compliance và RPO/RTO.

## 14. Kịch bản lập capacity plan mẫu

Giả sử hệ thống có:

- Peak 50.000 event/s, trung bình 20.000 event/s.
- Record trung bình 2 KiB.
- Compression ratio đo được 0,45.
- Retention 7 ngày cho topic chính.
- RF=3, min.insync.replicas=2.
- 4 consumer group đọc topic chính.
- Yêu cầu chịu mất một broker và duy trì produce/consume trong SLO.

Quy trình:

1. Tính ingress trung bình và peak trước/sau compression.
2. Tính dung lượng một replica theo retention 7 ngày.
3. Nhân RF và hệ số dự phòng; chia utilization target để ra disk provision.
4. Cộng internal topics, retry/DLQ, Streams changelog và Connect topics.
5. Benchmark throughput broker với RF=3, acks=all, compression và consumer pattern tương ứng.
6. Tính broker count theo storage và throughput; kiểm tra N-1 capacity.
7. Chọn partition count từ throughput/partition benchmark, consumer parallelism và ordering requirement.
8. Phân bố replica qua AZ/rack theo failure-domain policy.
9. Tính network ingress, replication, consumer egress và cross-AZ transfer.
10. Dự toán compute, disk, network, observability, DR và operations theo tháng/năm.
11. Đặt alert cho disk forecast, p99 latency, under-replicated partitions, lag và broker saturation.
12. Chạy performance test và failure drill trước khi chốt cấu hình.

Kết quả capacity plan phải ghi rõ giả định. Nếu compression ratio, retention hoặc consumer group count thay đổi, cần tính lại storage/network/cost thay vì chỉ thêm broker theo cảm tính.

## 15. Mẫu bảng capacity review

| Nhóm | Baseline | Hiện tại | Forecast 3 tháng | Ngưỡng hành động | Owner |
|---|---:|---:|---:|---|---|
| Peak ingress (MB/s) |  |  |  |  |  |
| Average ingress (MB/s) |  |  |  |  |  |
| Disk used (TB) |  |  |  |  |  |
| Disk growth (TB/day) |  |  |  |  |  |
| Broker CPU p95 |  |  |  |  |  |
| Network utilization p95 |  |  |  |  |  |
| Under-replicated partitions |  |  |  |  |  |
| Consumer lag p95/max |  |  |  |  |  |
| Produce latency p99 |  |  |  |  |  |
| Cross-AZ transfer (GB) |  |  |  |  |  |
| Monthly TCO |  |  |  |  |  |

Review hàng tháng hoặc theo chu kỳ release lớn. Với workload biến động mạnh, dùng dashboard theo ngày/tuần và cập nhật forecast khi có campaign, mùa cao điểm hoặc thay đổi schema.

## 16. Những lỗi hoạch định thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ tính dung lượng một replica | Thiếu disk do bỏ RF | Nhân replication factor và tính cả headroom |
| Dùng record size trước compression nhưng quên compression ratio | Dự toán storage/network sai | Đo ratio bằng payload thực tế |
| Lấy average thay peak kéo dài | Cluster quá tải khi burst | Mô hình hóa peak rate và thời lượng |
| Bỏ qua consumer groups | Thiếu network egress và broker fetch capacity | Tính số group và read throughput |
| Bỏ qua cross-AZ transfer | TCO cloud thấp giả tạo | Tính replication/fetch liên vùng |
| Chỉ tính broker, quên Connect/Streams | Thiếu compute và state disk | Cộng client workloads và internal topics |
| Không tính N-1 | Cluster không đạt SLO khi broker lỗi | Benchmark và capacity test khi mất broker |
| Thêm broker nhưng không reassignment | Broker mới rảnh, broker cũ vẫn nóng | Lập kế hoạch di chuyển replica |
| Tăng partition không xét key | Ordering theo entity bị ảnh hưởng | Migration/partition strategy có kiểm soát |
| Dùng một ngưỡng CPU để scale | Scale sai bottleneck | Kết hợp latency, queue, disk, network và lag |
| Không tính lead time | Mở rộng quá muộn | Dùng DaysToLimit và forecast |

## 17. Bài tập tự kiểm tra

1. Tại sao capacity plan cần tính cả producer ingress và consumer egress?
2. Replication factor ảnh hưởng storage và network như thế nào?
3. Vì sao compacted topic không thể sizing chỉ bằng ingress × retention?
4. Phân biệt dung lượng replica logic, dung lượng physical và dung lượng disk provision.
5. Vì sao cần tính N-1 capacity?
6. Cross-AZ traffic phát sinh ở những luồng nào?
7. TCO của self-managed Kafka khác managed Kafka ở các nhóm chi phí nào?
8. Khi nào scale up phù hợp hơn scale out?
9. Vì sao thêm broker không tự động cân bằng partition hiện tại?
10. Dùng DaysToLimit và lead time như thế nào để đặt ngưỡng mở rộng?

## Kết luận

Đánh giá tổng chi phí và tiêu chí mở rộng cụm Kafka phải xuất phát từ workload thực tế: event rate, record size, compression, retention, consumer groups, replication và yêu cầu chịu lỗi. Từ đó tính storage, broker throughput, network, CPU/RAM, rồi cộng chi phí compute, disk, transfer, observability, DR và operations thành TCO theo tháng/năm.

Scale khi số liệu cho thấy một giới hạn sẽ ảnh hưởng SLO trước lần review/provision tiếp theo. Dùng forecast disk growth, p99 latency, consumer lag, broker saturation, ISR và recovery time để quyết định scale up, scale out, reassignment hoặc tối ưu workload. Một capacity plan tốt phải ghi rõ giả định, headroom, failure scenario, lead time và kết quả benchmark để có thể cập nhật khi traffic hoặc kiến trúc thay đổi.
