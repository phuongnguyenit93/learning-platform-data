# Dự phòng tài nguyên khi mất broker hoặc bảo trì

## Mục tiêu

Kafka cluster phải tiếp tục phục vụ workload khi một broker dừng đột ngột hoặc được đưa ra bảo trì. Replication giúp partition vẫn có replica để bầu leader, nhưng **replication không tự tạo thêm CPU, RAM, disk và network capacity** cho các broker còn sống. Khi một node mất, các broker còn lại phải nhận thêm leader traffic, phục vụ consumer fetch, tiếp tục replication và có thể lưu thêm replica trong quá trình phục hồi.

Capacity planning cho tình huống N-1 cần trả lời hai câu hỏi riêng:

1. **Service continuity:** Các broker còn sống có đủ tài nguyên để tiếp tục nhận produce/fetch và xử lý request trong khi một broker vắng mặt không?
2. **Redundancy restoration:** Cluster có đủ disk, network và thời gian để tái tạo replica bị mất, đưa partition trở lại replication factor mong muốn không?

Sau bài học này, bạn có thể:

- Xác định failure scenario: broker process, host, rack/zone hoặc maintenance.
- Tính capacity an toàn khi một broker không còn phục vụ.
- Ước lượng disk cần để phục hồi replica sau broker loss.
- Đánh giá CPU, memory, network và disk I/O headroom.
- Thiết kế replication factor, `min.insync.replicas` và rack awareness.
- Phân biệt khả năng chịu lỗi data plane và KRaft controller quorum.
- Lập kế hoạch reassignment, decommission và rolling maintenance.
- Ước lượng thời gian re-replication và tác động lên workload đang chạy.
- Kiểm thử broker failure/maintenance và xác minh RTO, ISR, throughput.

## 1. Phân biệt broker failure và broker maintenance

Hai tình huống có cùng kết quả tạm thời là một broker không phục vụ traffic, nhưng cách chuẩn bị khác nhau.

| Tình huống | Đặc điểm | Mục tiêu vận hành |
|---|---|---|
| Broker process crash | Process dừng đột ngột, không kịp chuyển partition/leader có kiểm soát | Cluster phát hiện lỗi, bầu leader từ replica hợp lệ và tiếp tục phục vụ |
| Host/power failure | Mất cả máy, disk và network của broker | Chịu được failure domain bị mất; khôi phục replica trên node khác |
| Rack/zone failure | Nhiều broker cùng mất do một failure domain | Replica và controller phải được phân bố qua rack/zone khác nhau |
| Planned restart | Dừng một broker để nâng cấp OS, JVM hoặc Kafka | Giảm gián đoạn, giữ ISR và quorum, tránh bảo trì đồng thời |
| Broker decommission | Loại broker khỏi cluster vĩnh viễn | Di chuyển toàn bộ replica khỏi broker trước khi unregister |
| Disk maintenance | Thay hoặc loại một log directory | Di chuyển replica khỏi disk/dir trước khi tháo thiết bị |

Không dùng kết quả kiểm thử một broker process crash để kết luận cluster chịu được cả rack/zone failure. Failure domain và replica placement quyết định mức chịu lỗi thực tế.

### 1.1. N-1 nghĩa là gì?

N-1 capacity là khả năng duy trì workload mục tiêu khi một trong N broker không còn khả dụng. Với cluster đồng nhất, phép tính ban đầu thường là:

\[
C_{N-1} = (N-1) \times C_{safe}
\]

Trong đó `C_safe` là throughput an toàn đã đo trên một broker trong cấu hình production-like. Đây là mô hình xấp xỉ để sàng lọc capacity. Thực tế cần xét partition leader distribution, follower replication, request routing, hot partition, network path và mức tải khác nhau giữa broker.

N-1 không chỉ là “cluster còn N-1 process”. Các broker còn lại phải đủ tài nguyên để tiếp nhận traffic chuyển từ node lỗi và giữ đủ headroom cho replication/recovery.

### 1.2. Availability và redundancy là hai trạng thái khác nhau

Sau khi một broker trong cluster RF=3 bị mất, partition có thể vẫn có leader và tiếp tục xử lý với hai replica còn lại. Tuy nhiên cluster đang ở trạng thái giảm redundancy: nếu một replica còn lại tiếp tục lỗi trước khi replica mới được tạo và bắt kịp, partition có thể mất khả năng ghi hoặc mất dữ liệu tùy cấu hình và tình trạng replica.

Vì vậy, “producer vẫn ghi được” không có nghĩa cluster đã phục hồi hoàn toàn. Chỉ kết thúc incident khi replica placement, ISR và tài nguyên đã trở về trạng thái mục tiêu.

## 2. Replication, ISR và khả năng ghi khi mất broker

Kafka lưu mỗi partition trên một tập replica. Một replica là leader; các replica đang theo kịp leader thuộc ISR (in-sync replicas). Khi broker chứa leader lỗi, controller bầu leader mới từ replica đủ điều kiện theo metadata và policy của cluster.

### 2.1. Ví dụ RF=3, min ISR=2

Giả sử topic `orders.events` có:

```text
replication.factor = 3
min.insync.replicas = 2
producer acks = all
```

| Trạng thái | ISR | Kết quả với `acks=all` |
|---|---:|---|
| Bình thường | 3 replica | Ghi thành công khi tất cả replica trong ISR xác nhận |
| Một broker lỗi | 2 replica | Vẫn có thể ghi vì ISR còn đạt min ISR |
| Thêm một replica nữa lỗi hoặc tụt khỏi ISR | 1 replica | Ghi bị từ chối vì ISR thấp hơn min ISR |
| Replica mới bắt kịp và gia nhập ISR | 3 replica | Redundancy được phục hồi |

`acks=all` có nghĩa leader chờ tất cả replica hiện nằm trong ISR xác nhận, không có nghĩa chỉ chờ đúng `min.insync.replicas`. `min.insync.replicas` là ngưỡng tối thiểu để request ghi với `acks=all` được chấp nhận. Với RF=3, min ISR=2, khi ISR còn 2 thì ghi có thể tiếp tục với hai replica; nếu ISR chỉ còn 1, producer nhận lỗi như `NotEnoughReplicas` hoặc `NotEnoughReplicasAfterAppend`. <Link url="https://kafka.apache.org/43/configuration/broker-configs/" title="Apache Kafka broker config: min.insync.replicas"/>.

### 2.2. RF và min ISR không thay thế placement

RF=3 chỉ tạo ba bản sao logic cho partition. Nếu ba replica cùng nằm trong một rack hoặc cùng storage failure domain, một sự cố rack/disk có thể làm mất nhiều replica cùng lúc.

Để chịu được lỗi rack/zone, cần:

- Gán `broker.rack` chính xác cho từng broker.
- Đảm bảo replica assignment phân tán qua các rack/zone độc lập.
- Kiểm tra replica thực tế của từng partition, không chỉ nhìn config.
- Bảo đảm controller quorum cũng không tập trung trong cùng failure domain.

Rack awareness không tự tạo rack mới. Nếu cluster chỉ có hai rack nhưng topic có RF=3, không thể đặt ba replica trên ba rack độc lập. Số rack và policy placement phải đủ cho failure scenario đã cam kết.

### 2.3. Không dựa vào unclean leader election để đạt availability

Unclean leader election có thể chọn replica không thuộc ISR khi không còn replica ISR khả dụng. Việc này có thể làm partition hoạt động trở lại nhưng có nguy cơ mất các record chưa được replica đó nhận. Với workload ưu tiên durability, không bật unclean leader election chỉ để tránh write unavailability. Định nghĩa rõ trade-off RPO/availability và kiểm thử tình huống ISR không còn replica.

## 3. Xác định SLO và failure budget

Capacity planning bắt đầu từ SLO và failure scenario, không bắt đầu bằng số broker hiện có.

Hãy định nghĩa:

- Throughput cần duy trì khi một broker mất: records/s và MiB/s.
- Produce p95/p99 latency tối đa trong lúc failover.
- Consumer lag tối đa và thời gian drain sau khi broker quay lại.
- RTO: thời gian tới khi service trở lại mức xử lý chấp nhận được.
- RPO: lượng dữ liệu có thể mất trong failure scenario được chấp nhận.
- Thời gian tối đa cluster được phép ở trạng thái giảm redundancy.
- Số lỗi đồng thời cần chịu: một broker, một host, một rack/zone hay nhiều node.

Ví dụ tiêu chí:

```text
Workload bình thường: 300 MiB/s produce, 450 MiB/s consume
Failure scenario: mất một broker bất kỳ
Throughput tối thiểu trong failover: 300 MiB/s produce, 450 MiB/s consume
Producer p99 latency: dưới 100 ms sau giai đoạn failover
Consumer lag: không tăng liên tục; drain về baseline trong 10 phút
Durability: RF=3, min.insync.replicas=2, acks=all
Redundancy recovery: tái tạo replica bị mất trong 2 giờ
```

Đây là ví dụ mục tiêu để minh họa cách viết SLO, không phải mức mặc định cho mọi Kafka cluster. RTO cần phân biệt thời gian failover data path với thời gian khôi phục đủ replication factor.

## 4. Tính throughput N-1 cho CPU và request processing

### 4.1. Đo capacity an toàn trên một broker

Không lấy throughput tối đa của benchmark làm capacity production. Đo trên cấu hình gần production:

- Replication factor và `acks` tương đương production.
- Record-size/key distribution và compression tương tự.
- Producer, consumer, TLS/SASL và quota tương tự.
- Có follower fetch và consumer fetch thực tế.
- Đo trong steady state và có background workload.
- Theo dõi p99 latency, CPU, request handler, disk và network.

Từ throughput bão hòa đã đo, đặt mức utilization mục tiêu để còn headroom. Ví dụ:

\[
C_{safe} = C_{measured} \times U_{target}
\]

Nếu broker đo được 140 MiB/s trước khi latency vượt SLO và policy chỉ cho phép sử dụng 70% mức đó trong vận hành bình thường:

\[
C_{safe} = 140 \times 0,70 = 98\text{ MiB/s}
\]

`U_target` là policy capacity do team lựa chọn dựa trên benchmark và SLO, không phải một ngưỡng Kafka cố định.

### 4.2. Ví dụ cluster 6 broker

Giả sử sáu broker có capacity an toàn tương đương 98 MiB/s/broker. Khi một broker lỗi, năm broker còn lại có tổng capacity sơ bộ:

\[
C_{N-1} = 5 \times 98 = 490\text{ MiB/s}
\]

Nếu workload cần 420 MiB/s:

\[
U_{N-1} = \frac{420}{490} \approx 85,7\%
\]

Theo phép tính tổng, cluster còn 70 MiB/s capacity dự phòng trong failure scenario. Tuy nhiên kết quả chỉ đạt nếu partition leader, replica traffic và client request được phân bố đủ đều. Nếu broker mất đang giữ các leader nóng, một broker còn lại có thể quá tải trước khi tổng capacity đạt giới hạn.

Với workload hỗn hợp produce và consume, không cộng hai chiều MiB/s thành một con số duy nhất rồi so với một benchmark chỉ đo producer. Hãy giữ ngân sách riêng cho ingress, egress và inter-broker replication, hoặc benchmark đúng tỷ lệ hỗn hợp production để `C_safe` đại diện cho cùng workload. CPU, disk và network cũng là các giới hạn đồng thời; đạt tổng MiB/s không có nghĩa mọi tài nguyên đều còn headroom.

### 4.3. Kiểm tra theo broker, không chỉ tổng cluster

Với mỗi broker, lập bảng:

| Broker | Produce leader MiB/s | Fetch egress MiB/s | Replication in/out | CPU | Disk utilization | Network utilization |
|---|---:|---:|---:|---:|---:|---:|
| B1 | Đo | Đo | Đo | Đo | Đo | Đo |
| B2 | Đo | Đo | Đo | Đo | Đo | Đo |
| B3 | Đo | Đo | Đo | Đo | Đo | Đo |
| B4 | Đo | Đo | Đo | Đo | Đo | Đo |
| B5 | Đo | Đo | Đo | Đo | Đo | Đo |
| B6 | Đo | Đo | Đo | Đo | Đo | Đo |

Mô phỏng mất lần lượt từng broker trong lab/staging hoặc dùng workload model để tính lại assignment. Broker có tải lớn nhất sau failure scenario mới là yếu tố quyết định. Không kết luận N-1 chỉ từ phép cộng capacity trung bình.

### 4.4. Capacity CPU

CPU của broker bị ảnh hưởng bởi request parsing, serialization/compression, TLS, replication, index/log management, compaction và request handler. Khi một broker mất, leader workload và replication/fetch traffic phân bố lại; CPU của node còn lại có thể tăng không đều.

Theo dõi:

- CPU utilization theo process và core.
- Request handler idle percent.
- Network processor idle percent.
- Request queue time và local/remote processing time.
- GC pause, allocation rate và heap pressure.
- Compaction/replica fetcher thread activity.

Không chỉ nhìn CPU average. Một core hoặc request handler pool bị bão hòa có thể làm p99 tăng trong khi tổng CPU còn thấp.

## 5. Tính storage headroom khi mất broker

Disk planning cần trả lời cả dung lượng giữ dữ liệu thường ngày và dung lượng để tái tạo replica sau failure.

### 5.1. Ước lượng dữ liệu retained

Với topic dùng delete retention, ước lượng dung lượng payload retained trước compression:

\[
D_{logical} = R_{payload} \times T_{retention}
\]

Trong đó:

- `R_payload`: tốc độ byte payload ghi vào topic (bytes/s).
- `T_retention`: thời gian retention (seconds).

Ước lượng disk cho toàn cluster:

\[
D_{cluster} \approx D_{logical} \times K_{compression} \times RF \times (1 + O)
\]

Trong đó `K_compression` là tỷ lệ byte sau compression so với payload ban đầu (ví dụ 0,5 nghĩa còn 50%); `RF` là replication factor; `O` là overhead dự phòng cho index, segment, batch/protocol khác biệt, retention overshoot và sai số đo.

Đây là phép ước lượng sơ bộ. Nên thay compression ratio và overhead bằng số đo disk thực tế theo topic. Topic compacted không thể tính đơn giản bằng ingress × retention vì dung lượng phụ thuộc số key còn tồn tại, tombstone, compaction lag và churn.

### 5.2. Ví dụ disk capacity

Một topic có:

- Payload ingress: 12 MiB/s.
- Delete retention: 7 ngày.
- Compression ratio đo được: 0,5.
- Replication factor: 3.
- Bỏ qua overhead để minh họa phép tính đầu tiên.

Dung lượng payload retained cho một bản sao logic:

\[
D_{logical}=12 \times 86.400 \times 7 = 7.257.600\text{ MiB}
\]

Tương đương khoảng 6,91 TiB payload. Sau compression, một replica cần khoảng 3,45 TiB; cả RF=3 cần khoảng 10,36 TiB trên toàn cluster.

Với sáu broker và replica placement cân bằng, dung lượng trung bình của topic trên mỗi broker xấp xỉ:

\[
D_{broker} \approx \frac{10,36}{6} = 1,73\text{ TiB}
\]

Khi một broker mất, cluster mất khoảng 1,73 TiB replica data của topic đó. Để tái tạo RF=3 trên năm broker còn lại, cần tổng free disk có thể phân phối đủ cho khoảng 1,73 TiB dữ liệu replica mới, cộng thêm overhead và disk reserve. Phân bố thực tế phụ thuộc assignment, rack awareness, kích thước partition và broker nào được chọn làm đích.

### 5.3. Công thức N-1 cho disk

Với cluster cân bằng gồm N broker, tổng replica storage mục tiêu `D_cluster`, dung lượng replica mất khi một broker lỗi xấp xỉ:

\[
D_{lost} \approx \frac{D_{cluster}}{N}
\]

Điều kiện sơ bộ để tái tạo RF trên N-1 broker:

\[
\sum_{i=1}^{N-1} FreeDisk_i \geq D_{lost} + D_{reserve}
\]

Đồng thời từng broker đích phải còn đủ free disk để nhận các replica được phân bổ; tổng free disk lớn nhưng dồn vào một broker không giúp reassignment cân bằng.

Nếu có spare broker riêng, có thể chuyển replica sang node dự phòng thay vì dồn tất cả lên N-1 broker. Dù vậy, spare node phải được provision sẵn, có disk/network tương ứng và có thể gia nhập cluster theo runbook.

### 5.4. Disk utilization và reserve

Không thiết kế để broker sử dụng 100% disk. Cần chừa dung lượng cho:

- Replica reassignment và recovery.
- Retention overshoot do segment rolling/delete delay.
- Compaction temporary files và cleaner activity.
- Log index, metadata, checkpoint và internal topic.
- Tăng trưởng traffic và retention trong thời gian incident.
- Disk imbalance giữa các broker.

Một policy có thể đặt ngưỡng vận hành bình thường ở 65–75% dung lượng và giữ phần còn lại làm headroom, nhưng con số cần dựa trên workload, tốc độ tăng dữ liệu, thời gian phát hiện/khắc phục và khả năng thêm disk. Không dùng 75% như một giới hạn Kafka cố định.

### 5.5. Disk throughput và IOPS

Dung lượng trống không đồng nghĩa disk đủ nhanh. Sau broker loss, broker còn lại có thể đồng thời:

- Append produce data.
- Phục vụ consumer fetch.
- Đọc/ghi replica catch-up.
- Chạy log cleaner/compaction.
- Flush metadata và index.

Benchmark phải đo throughput và latency disk dưới workload tương tự. Theo dõi IOPS, queue depth, await/latency, utilization và read/write bytes. Nếu reassignment làm disk latency tăng vượt SLO, giảm tốc độ reassignment và chia thành nhiều đợt.

## 6. Network headroom khi broker bị mất

Network cần phục vụ client ingress, consumer egress, inter-broker replication và metadata/control traffic. Khi một broker lỗi:

- Producer request chuyển tới leader mới.
- Với partition có leader chuyển đi, consumer fetch sẽ chuyển sang broker leader mới sau khi client cập nhật metadata. Consumer thường đọc từ leader; follower fetching chỉ áp dụng khi cấu hình rack-aware/follower fetching tương ứng được bật.
- Replica fetcher có thể truyền dữ liệu để khôi phục replica.
- Client có thể reconnect đồng loạt, tạo connection/request burst.
- Cross-rack/cross-zone traffic có thể tăng nếu leader/replica placement thay đổi.

### 6.1. Ước lượng băng thông rebuild

Nếu cần tái tạo `D_rebuild` byte replica trong thời gian mục tiêu `T_rebuild`:

\[
B_{rebuild} = \frac{D_{rebuild}}{T_{rebuild}}
\]

Ví dụ cần truyền 1,73 TiB trong 2 giờ:

\[
B_{rebuild} \approx \frac{1,73 \times 1024^2\text{ MiB}}{7200\text{ s}}
\approx 252\text{ MiB/s}
\]

Đây là throughput payload cần cho rebuild theo phép tính lý tưởng. Network thực tế còn có protocol overhead, replication fan-out, retry, cross-zone cost và cạnh tranh với client traffic. Cần đo effective replication throughput thay vì xem 252 MiB/s là tốc độ cấu hình chính xác.

### 6.2. Không dùng hết network cho reassignment

Reassignment quá nhanh có thể làm consumer fetch/producer request tăng latency hoặc network processor bị bão hòa. Reassignment quá chậm kéo dài thời gian cluster ở trạng thái giảm redundancy.

Lập ngân sách riêng cho:

- Client produce/consume traffic.
- Inter-broker replication steady state.
- Re-replication/reassignment burst.
- Cross-rack/cross-zone transfer.
- Operational traffic và headroom.

Theo dõi network bytes in/out theo broker, NIC utilization, packet drops/retransmits, request latency và replica lag. Nếu cần throttle reassignment, chọn tốc độ đủ phục hồi trong RTO nhưng không làm workload hiện tại vượt SLO.

## 7. Memory và page cache

Kafka dựa nhiều vào filesystem page cache. Broker cần RAM cho JVM heap, native memory, network buffers, thread stacks và page cache. Không cấp toàn bộ RAM cho JVM heap.

Khi một broker mất, broker còn lại có thể phải phục vụ thêm read traffic và replication; page cache hit ratio có thể giảm. Nếu memory pressure khiến OS reclaim page cache hoặc swap, disk read latency tăng và p99 fetch latency có thể xấu đi.

Kiểm tra:

- JVM heap usage và GC pause.
- Process RSS và native memory.
- OS available memory, page cache và swap.
- Container memory limit so với heap + native + page cache nhu cầu.
- Page fault và disk read latency trong failover.

Không đặt `-Xmx` bằng gần toàn bộ container memory. Chừa đủ cho native allocation, thread stack, direct buffer và OS page cache theo benchmark thực tế.

## 8. Partition placement và leader balance

Replica count đúng vẫn có thể tạo bottleneck nếu partition placement lệch. Một broker có thể giữ quá nhiều leader hoặc các partition có traffic lớn.

### 8.1. Replica placement

Với mỗi partition, kiểm tra:

- Replica nằm trên broker nào.
- Replica phân bố qua rack/zone nào.
- Broker nào đang giữ leader.
- Kích thước log và traffic của partition.
- ISR size và replica lag.
- Broker đích còn disk/network/CPU để nhận replica.

Không chỉ cân bằng số partition. Một broker có 200 partition nhỏ có thể nhẹ hơn broker có 50 partition nhưng mỗi partition có throughput và retention lớn.

### 8.2. Leader rebalance sau khi broker quay lại

Khi broker khởi động lại, các partition trên broker đó có thể quay lại vai trò follower trước; leader vẫn ở broker khác. Điều này có thể tạo leader imbalance và tải client khác với baseline. Theo dõi preferred replica election/leader distribution theo policy và chỉ thực hiện leader rebalance khi ISR đủ khỏe.

Không ép leader chuyển về broker vừa restart khi replica chưa bắt kịp. Ưu tiên khôi phục ISR và ổn định throughput trước khi cân bằng leader.

### 8.3. Rack awareness

Đặt `broker.rack` cho từng broker theo failure domain thật (rack, AZ hoặc zone) và kiểm tra replica assignment sau khi tạo topic/reassignment. Nếu các broker được gán nhầm cùng rack label, rack-aware assignment không bảo vệ được failure domain mong muốn.

Với RF=3 và ba rack độc lập, có thể đặt mỗi replica trên một rack. Khi một rack mất, hai replica còn lại vẫn có thể duy trì ISR=2 nếu cả hai khỏe. Nếu chỉ có hai rack, một trong hai rack có thể chứa hai replica của cùng partition; mất rack đó có thể làm partition mất cả hai bản sao.

## 9. KRaft controller quorum và broker capacity

Kafka KRaft có metadata quorum riêng. Broker replica chịu trách nhiệm data partitions; controller voters chịu trách nhiệm metadata log/quorum. Khả năng chịu lỗi data broker không tự bảo đảm controller quorum vẫn khỏe.

### 9.1. Số controller voter

Với quorum majority:

| Controller voters | Majority cần sống | Số voter có thể mất mà vẫn giữ quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |

Kafka khuyến nghị chọn 3 hoặc 5 controller tùy failure tolerance và chi phí. Ba controller có thể chịu một controller failure; năm controller có thể chịu hai. Các controller phải phân bố qua failure domain độc lập. <Link url="https://kafka.apache.org/43/operations/kraft/" title="Apache Kafka KRaft operations"/>.

### 9.2. Combined role và isolated controller

Ở combined mode, một process vừa là broker vừa là controller. Mất node có thể đồng thời làm giảm data capacity và số controller voter. Với deployment critical, tách controller role giúp bảo trì broker mà không trực tiếp làm giảm controller quorum; cần tính riêng tài nguyên và failure domain cho controller nodes.

Không bảo trì nhiều controller cùng lúc. Trước khi restart một controller, kiểm tra quorum state, leader và số voter khỏe. Sau restart, đợi node gia nhập quorum và metadata replication ổn định trước khi tiếp tục node khác.

### 9.3. Metadata quorum không phải replica của topic

KRaft controller quorum và topic partition replication là hai lớp khác nhau. RF=3 không có nghĩa metadata quorum chịu được hai controller lỗi; ba controller không có nghĩa mọi topic đều có ba replica. Capacity plan phải có hai bảng failure tolerance riêng.

## 10. N+1 và các mô hình dự phòng

### 10.1. N+1 broker

N+1 nghĩa là workload có thể chạy trên N broker capacity units và cluster provision thêm một broker dự phòng. Khi một broker lỗi, broker dự phòng hoặc capacity còn lại giúp giữ năng lực phục vụ.

Có hai cách triển khai thường gặp:

- **Hot spare:** broker đã gia nhập cluster, có tài nguyên và có thể nhận replica/assignment theo kế hoạch; không nên giả định nó tự động có đủ replica data.
- **Distributed headroom:** không có spare riêng, mỗi broker đều chạy thấp hơn capacity tối đa để N-1 broker còn lại hấp thụ tải.

Hot spare cần disk/network để nhận replica và thời gian catch-up. Distributed headroom cần mọi broker còn lại có đủ capacity sau khi một broker mất. Có thể kết hợp hai cách.

### 10.2. So sánh mô hình

| Mô hình | Ưu điểm | Chi phí/giới hạn |
|---|---|---|
| N broker không headroom | Chi phí thấp | Một broker lỗi có thể làm quá tải node còn lại |
| N-1 distributed headroom | Không cần node spare riêng | Các broker chạy dưới mức capacity tối đa thường ngày |
| N+1 hot spare | Có node để nhận replica/traffic | Tốn compute/disk và cần quy trình reassign/failover |
| Rack/zone redundancy | Chịu lỗi failure domain lớn hơn | Cần đủ rack/zone, network và replica placement đúng |

### 10.3. Không chỉ dự phòng broker count

N+1 chỉ có ý nghĩa khi spare capacity tồn tại ở tất cả tài nguyên cần thiết:

- CPU đủ xử lý leader/follower/request load.
- RAM đủ cho heap, native memory và page cache.
- Disk đủ dung lượng và throughput.
- Network đủ client và inter-broker traffic.
- Broker/partition count không vượt giới hạn vận hành.
- Controller quorum vẫn giữ majority.
- Có capacity cho consumer group/Streams task rebalance.

Nếu chỉ thêm một broker nhưng disk hoặc network vẫn bão hòa trên node còn lại, cluster chưa đạt N+1 theo SLO.

## 11. Quy trình planned maintenance cho một broker

Mục tiêu của maintenance là giảm thời gian cluster ở trạng thái giảm redundancy và tránh dừng nhiều replica của cùng partition.

### 11.1. Pre-check

Trước khi dừng broker:

1. Xác định tất cả partition replicas và leaders đang nằm trên broker.
2. Xác minh ISR đủ số lượng và không có under-replicated/offline partition kéo dài.
3. Kiểm tra broker còn lại có CPU, disk, network headroom.
4. Kiểm tra controller quorum health và failure domain.
5. Kiểm tra reassignment hoặc maintenance khác đang chạy không.
6. Lưu current replica assignment để rollback.
7. Xác định mục tiêu: restart tạm thời hay decommission vĩnh viễn.
8. Thông báo application owner và theo dõi SLO trong cửa sổ bảo trì.

Không bắt đầu nếu cluster đã có broker lỗi, ISR thiếu, disk gần đầy hoặc controller quorum đang degraded. Khi cluster đã giảm redundancy, bảo trì thêm node có thể làm partition mất quorum ghi hoặc mất leader.

### 11.2. Restart tạm thời

Với restart ngắn và broker sẽ quay lại cùng storage:

1. Xác minh replica placement và ISR khỏe.
2. Dừng broker theo quy trình graceful/controlled shutdown của phiên bản Kafka và hệ thống triển khai.
3. Theo dõi leader election, ISR và producer/consumer latency.
4. Hoàn tất nâng cấp/thay đổi OS hoặc JVM.
5. Khởi động broker và đợi mọi replica bắt kịp, gia nhập ISR.
6. Kiểm tra leader distribution và preferred replica balance theo policy.
7. Chỉ bắt đầu bảo trì broker tiếp theo khi cluster đã phục hồi trạng thái khỏe.

Không cần reassignment toàn bộ partition cho mọi lần restart ngắn nếu broker sẽ trở lại với log data còn nguyên vẹn và cluster có đủ headroom. Tuy nhiên, nếu mục tiêu là giải phóng host/rack hoặc di chuyển dữ liệu, cần reassignment/decommission có kế hoạch.

### 11.3. Decommission vĩnh viễn

Khi loại broker khỏi cluster, phải di chuyển toàn bộ replica của nó sang broker khác trước khi shutdown/unregister:

1. Liệt kê partition replica trên broker cần loại.
2. Tạo reassignment plan phân bố tới broker đích đủ disk/network.
3. Kiểm tra plan không đặt hai replica của cùng partition lên cùng broker hoặc cùng failure domain ngoài policy.
4. Lưu current assignment để rollback.
5. Execute reassignment theo batch nhỏ và throttle phù hợp.
6. Verify tiến độ; chờ replica mới bắt kịp và assignment hoàn tất.
7. Xác minh không còn replica trên broker cũ.
8. Shutdown và unregister broker theo quy trình đúng version.

Tài liệu Kafka mô tả `kafka-reassign-partitions.sh` với các mode `--generate`, `--execute` và `--verify`. Công cụ tạo candidate plan không tự đánh giá mọi hotspot/capacity constraint; operator cần review assignment trước khi execute. <Link url="https://kafka.apache.org/43/operations/basic-kafka-operations/" title="Apache Kafka basic operations: partition reassignment"/>.

### 11.4. Di chuyển replica bằng reassignment CLI

Ví dụ execute một file reassignment đã được review:

```bash
bin/kafka-reassign-partitions.sh \
  --bootstrap-server kafka-1:9092 \
  --reassignment-json-file broker-1-move.json \
  --execute
```

Kiểm tra tiến độ bằng cùng file:

```bash
bin/kafka-reassign-partitions.sh \
  --bootstrap-server kafka-1:9092 \
  --reassignment-json-file broker-1-move.json \
  --verify
```

Lưu assignment cũ được CLI trả về để có thể lập kế hoạch rollback. Không tự tạo file JSON ví dụ rồi chạy trên production; phải lấy assignment thật, review broker đích và thử trên môi trường tương đương.

### 11.5. Throttle reassignment

Reassignment tạo network, disk read/write và CPU load. Có thể đặt replication throttle để giới hạn tốc độ di chuyển, nhưng cần hiểu config theo version và xóa throttle sau khi hoàn tất.

Điều chỉnh tốc độ theo:

- Client produce/fetch latency.
- Replica lag và thời gian dự kiến phục hồi.
- Disk utilization/latency.
- Network utilization và cross-zone traffic.
- ISR shrink/expand và under-replicated partitions.

Nếu throttle quá thấp, cluster ở trạng thái giảm redundancy lâu hơn. Nếu quá cao, reassignment có thể làm client SLO suy giảm. Chọn tốc độ dựa trên đo đạc và có người theo dõi.

## 12. Decommission broker và log directory trên Kafka mới

Một số Kafka release mới hỗ trợ cơ chế cordon broker/log directory trước khi di chuyển replica và unregister broker. Ví dụ tài liệu Kafka 4.4 mô tả `cordoned.log.dirs` và quy trình decommission. Tính năng và cú pháp phụ thuộc version; không áp dụng lệnh từ tài liệu 4.4 cho cluster cũ mà chưa xác minh. <Link url="https://kafka.apache.org/44/operations/basic-kafka-operations/" title="Apache Kafka 4.4 broker and log directory decommission"/>.

Ở các version không có quy trình cordon tương ứng, dùng quy trình reassignment/maintenance được hỗ trợ cho release đó. Luôn xác minh broker đã không còn replica trước khi unregister hoặc xóa storage.

## 13. Ước lượng thời gian phục hồi replica

Khi broker lỗi, service failover và replica rebuild có thể diễn ra đồng thời nhưng là hai mục tiêu khác nhau.

### 13.1. Rebuild time

Ước lượng thời gian chuyển dữ liệu:

\[
T_{rebuild} \approx \frac{D_{rebuild}}{B_{effective}}
\]

Trong đó:

- `D_rebuild`: tổng byte replica cần tái tạo.
- `B_effective`: replication throughput hữu hiệu sau khi trừ cạnh tranh với client traffic và overhead.

Ví dụ 1,73 TiB cần rebuild với effective throughput 150 MiB/s:

\[
T \approx \frac{1,73 \times 1024^2}{150} \approx 12.400\text{ s} \approx 3,45\text{ giờ}
\]

Thời gian thực tế có thể lâu hơn do throttle, partition nhỏ/lớn không đều, disk contention, network contention, broker throttling và replica fetch scheduling. Đo tốc độ thực tế trong lab/staging.

### 13.2. Recovery không đồng nghĩa toàn bộ partition rebuild cùng lúc

Kafka di chuyển replica theo partition và giới hạn concurrency/throughput theo broker. Một số partition có thể hoàn tất sớm, một số partition lớn hoặc broker đích chậm có thể kéo dài toàn bộ maintenance window. Theo dõi reassignment từng partition và replica lag thay vì chỉ dùng tổng bytes.

### 13.3. RTO và redundancy recovery

Tách các mốc:

| Mốc | Ý nghĩa |
|---|---|
| Failure detected | Broker/host được phát hiện không khả dụng |
| Leader available | Partition có leader hợp lệ |
| Service recovered | Producer/consumer đạt SLO xử lý chấp nhận được |
| ISR stable | Replica còn lại khỏe và ISR ổn định |
| RF restored | Replica assignment trở lại replication factor mục tiêu |
| Capacity restored | CPU/disk/network headroom quay lại trạng thái dự kiến |

Incident có thể đạt service recovered trong vài giây nhưng mất nhiều phút/giờ để RF restored. Không đóng incident chỉ vì producer đã ghi thành công trở lại.

## 14. Capacity cho consumer và Streams khi broker mất

Broker loss có thể kích hoạt leader movement, consumer reconnect và group rebalance. Consumer fetch load có thể chuyển sang broker khác; consumer group cũng có thể tạm tăng lag.

Đối với consumer:

- Đo fetch throughput và processing throughput trên mỗi instance.
- Chừa CPU/network để consumer đọc từ broker leader mới.
- Kiểm tra `max.partition.fetch.bytes`, `fetch.max.bytes` và batch memory.
- Có bounded worker pool và backpressure để tránh memory spike khi backlog tăng.
- Không commit offset vượt qua record chưa xử lý nếu xử lý bất đồng bộ.

Đối với Kafka Streams:

- Tính task migration và state restore load.
- Dự phòng disk cho local state store và changelog restore.
- Dùng standby replica nếu RTO yêu cầu và có đủ instance.
- Theo dõi restore lag, standby lag, rebalance latency và processing throughput.
- Không giả định broker spare đồng nghĩa Streams instance spare.

## 15. Monitoring trong failure và maintenance

Dashboard nên có baseline trước khi bắt đầu và hiển thị riêng giai đoạn failure, maintenance, reassignment và recovery.

| Nhóm | Chỉ số | Cảnh báo |
|---|---|---|
| Availability | Offline partitions, unavailable leaders, broker up/down | Partition không có leader hoặc broker mất ngoài kế hoạch |
| Replication | Under-replicated partitions, ISR shrink/expand, replica lag | ISR dưới min ISR hoặc replica lag không giảm |
| Producer | Throughput, p95/p99 latency, error rate, throttle | Throughput giảm hoặc `NotEnoughReplicas` tăng |
| Consumer | Fetch rate, lag theo partition, processing rate, rebalance | Lag tăng liên tục hoặc một partition không drain |
| CPU | Process/core utilization, request handler idle, GC | Core/request pool bão hòa |
| Memory | Heap, RSS, page cache, swap | Swap hoặc memory pressure tăng |
| Disk | Free bytes, utilization, IOPS, latency, queue depth | Disk reserve thấp hoặc I/O wait cao |
| Network | Bytes in/out, NIC utilization, drops/retransmits | Network gần saturation hoặc replication bị nghẽn |
| KRaft | Quorum voters, leader, high watermark/lag, controller health | Mất majority hoặc metadata quorum không ổn định |
| Reassignment | Partitions in progress, bytes remaining, replication rate | Reassignment đứng yên hoặc vượt maintenance window |

Metric name cụ thể phụ thuộc Kafka version và exporter. Xác minh JMX/metrics thực tế của cluster; không hard-code dashboard dựa trên tên metric chưa kiểm tra.

### 15.1. Cảnh báo nên có trước khi sự cố xảy ra

- Broker disk free thấp hơn lượng replica cần hấp thụ khi một node mất.
- CPU/network headroom N-1 không đạt mục tiêu.
- Partition có ISR bằng đúng min ISR trong thời gian dài.
- Replica placement không phân tán qua rack/zone như policy.
- Controller voter cùng nằm trong một failure domain.
- Một broker có leader bytes/partition count cao hơn đáng kể.
- Under-replicated partitions kéo dài sau rolling maintenance.
- Reassignment throughput thấp hơn mức cần để đạt recovery RTO.

## 16. Thực hành: kiểm thử N-1 và maintenance window

Lab cần cluster tối thiểu ba broker có RF=3, topic test nhiều partition, producer `acks=all` và consumer group theo dõi lag. Nếu thử rack awareness, cần nhiều rack label và topology phù hợp.

### 16.1. Chuẩn bị baseline

1. Tạo topic test với RF=3, min ISR=2.
2. Gửi traffic có record-size/key distribution giống workload mục tiêu.
3. Chạy consumer liên tục.
4. Ghi producer throughput/latency, consumer lag, broker CPU/disk/network, ISR và leader distribution.
5. Xác minh mọi partition có đủ replica và ISR khỏe.

### 16.2. Mô phỏng broker loss

1. Chọn một broker và ghi partition/leader/replica đang nằm trên nó.
2. Dừng broker trong môi trường lab theo cách mô phỏng failure đã chọn.
3. Ghi thời gian broker được phát hiện và thời gian leader election.
4. Quan sát producer errors, p99 latency, consumer lag và ISR.
5. Xác nhận workload vẫn đạt tiêu chí service continuity.
6. Khởi động lại broker và chờ replica bắt kịp, gia nhập ISR.
7. Xác nhận leader distribution và resource usage ổn định.

Không dừng broker thứ hai khi cluster chưa phục hồi RF/ISR sau lần thử đầu.

### 16.3. Mô phỏng decommission

1. Tạo reassignment plan di chuyển replica khỏi broker thử nghiệm.
2. Kiểm tra disk headroom và rack placement của broker đích.
3. Execute từng batch nhỏ.
4. Theo dõi replica lag, disk/network và client SLO.
5. Verify reassignment hoàn tất và broker cũ không còn replica.
6. Shutdown/unregister theo version/runbook của lab.

### 16.4. Bảng kết quả

| Chỉ số | Baseline | Broker down | Recovery complete |
|---|---:|---:|---:|
| Produce MiB/s | Ghi số đo | Ghi số đo | Ghi số đo |
| Produce p99 latency | Ghi số đo | Ghi số đo | Ghi số đo |
| Consumer lag max | Ghi số đo | Ghi số đo | Ghi số đo |
| Offline partitions | Ghi số đo | Ghi số đo | Ghi số đo |
| Under-replicated partitions | Ghi số đo | Ghi số đo | Ghi số đo |
| Disk free trên broker còn lại | Ghi số đo | Ghi số đo | Ghi số đo |
| Network peak | Ghi số đo | Ghi số đo | Ghi số đo |
| Service recovery time | Không áp dụng | Ghi số đo | Không áp dụng |
| RF restoration time | Không áp dụng | Đang phục hồi | Ghi số đo |

Ghi Kafka version, broker hardware, RF, min ISR, workload và cách dừng broker. Không điền số giả định vào báo cáo lab.

## 17. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Producer nhận `NotEnoughReplicas` | ISR thấp hơn min ISR | Khôi phục broker/replica, kiểm tra disk/network và ISR; không hạ min ISR tùy tiện |
| Partition offline sau broker loss | Không còn replica đủ điều kiện làm leader | Kiểm tra replica logs/ISR và runbook phục hồi; cân nhắc RPO trước mọi lựa chọn unclean |
| Broker còn lại CPU cao sau failover | Leader traffic và request chuyển dồn | Kiểm tra leader skew, request handler và partition placement |
| Consumer lag tăng mạnh | Fetch chuyển broker, rebalance hoặc processing bottleneck | Theo dõi lag theo partition, fetch latency và downstream pool |
| Reassignment rất chậm | Throttle thấp, network/disk bận hoặc broker đích yếu | Đo effective replication rate, điều chỉnh batch/throttle và target placement |
| Disk broker đích gần đầy | Capacity plan thiếu replica rebuild reserve | Dừng batch tiếp theo, thêm disk/broker hoặc đổi target placement |
| ISR không phục hồi sau broker restart | Replica lag, log directory lỗi hoặc network không ổn định | Xem broker logs, replica fetcher và disk health |
| Broker quay lại nhưng leader không cân bằng | Leader vẫn ở replica khác hoặc preferred election chưa chạy | Kiểm tra leader distribution; rebalance có kiểm soát sau khi ISR khỏe |
| Mất quorum KRaft khi bảo trì broker | Combined role hoặc controller voter tập trung | Kiểm tra voter placement/majority; dừng maintenance tiếp theo |
| Reassignment làm client p99 tăng | Rebuild traffic tranh network/disk/request capacity | Throttle/chia batch, giảm tốc độ và theo dõi SLO |
| Một rack failure làm mất nhiều replica | Rack awareness hoặc placement không đúng | Kiểm tra `broker.rack` và assignment, thiết kế lại failure domain |

## 18. Checklist production

- [ ] Failure scenario được định nghĩa: process, host, rack/zone và maintenance.
- [ ] Có SLO throughput/latency/lag trong trạng thái N-1.
- [ ] Broker capacity được đo với RF, acks, compression và workload production-like.
- [ ] N-1 CPU/request/network capacity đủ cho workload mục tiêu.
- [ ] Disk headroom đủ chứa replica rebuild và safety reserve.
- [ ] Disk IOPS/latency đủ khi append, fetch, compaction và reassignment cùng chạy.
- [ ] Producer dùng `acks`/idempotence phù hợp; min ISR không thấp hơn durability policy.
- [ ] RF và ISR được xác minh theo partition.
- [ ] Replica placement phân tán qua rack/zone theo failure target.
- [ ] Controller quorum có majority sau một controller/node failure.
- [ ] Combined-role failure được tính cả data plane và control plane.
- [ ] Có reassignment plan, lưu assignment cũ và verify trước decommission.
- [ ] Reassignment throttle có ngân sách và người theo dõi.
- [ ] Maintenance chỉ tiến hành khi cluster khỏe; từng node một theo failure domain.
- [ ] Không bắt đầu maintenance tiếp theo khi ISR/RF chưa phục hồi.
- [ ] Có dashboard broker, replica, consumer, disk, network và KRaft quorum.
- [ ] Đã diễn tập broker loss, broker restart, rack failure phù hợp và decommission.
- [ ] Báo cáo tách service recovery time và full redundancy restoration time.

## 19. Câu hỏi tự kiểm tra

1. N-1 capacity khác với việc cluster còn N-1 broker như thế nào?
2. Vì sao producer có thể tiếp tục ghi sau khi một broker lỗi với RF=3/min ISR=2?
3. `acks=all` và `min.insync.replicas` phối hợp ra sao?
4. Vì sao service recovered không đồng nghĩa RF đã được phục hồi?
5. Cách ước lượng disk replica bị mất khi một broker trong cluster cân bằng bị lỗi?
6. Vì sao tổng free disk lớn vẫn chưa chắc đủ cho reassignment?
7. Cách ước lượng network throughput cần để rebuild replica trong một maintenance window?
8. Vì sao cần đo capacity từng broker thay vì chỉ tổng cluster?
9. `broker.rack` và rack-aware assignment bảo vệ failure domain như thế nào?
10. Controller quorum 3 và 5 voter chịu được bao nhiêu voter failure?
11. Vì sao combined broker/controller role làm maintenance phức tạp hơn?
12. Khác biệt giữa restart tạm thời và decommission vĩnh viễn?
13. Các bước chính khi dùng partition reassignment để di chuyển replica?
14. Vì sao cần throttle reassignment và theo dõi client SLO?
15. Khi nào được phép bắt đầu bảo trì broker tiếp theo?

## Tài liệu tham khảo

- [Apache Kafka — Basic Operations](https://kafka.apache.org/43/operations/basic-kafka-operations/): graceful shutdown, partition reassignment, leader balance và broker operations.
- [Apache Kafka — KRaft Operations](https://kafka.apache.org/43/operations/kraft/): controller quorum, voter majority và failure tolerance.
- [Apache Kafka — Broker Configs](https://kafka.apache.org/43/configuration/broker-configs/): `min.insync.replicas`, `broker.rack` và broker resource settings.
- [Apache Kafka — Topic Configs](https://kafka.apache.org/43/configuration/topic-configs/): replication-related và retention settings ở topic scope.
- [Apache Kafka 4.4 — Basic Operations](https://kafka.apache.org/44/operations/basic-kafka-operations/): cordon và decommission broker/log directory trên release hỗ trợ.

> Capacity planning khi mất broker phải kiểm tra đồng thời service continuity và redundancy restoration. RF/ISR giúp giữ partition khả dụng; N-1 CPU, disk, network headroom và replica placement quyết định cluster có tiếp tục đạt SLO và phục hồi đủ bản sao trước sự cố tiếp theo hay không.
