# Chọn số broker, controller và miền sự cố

Hoạch định số node Kafka cần bắt đầu từ workload và failure scenario, sau đó mới chọn topology triển khai. **Broker** lưu partition replica và phục vụ produce/fetch traffic; **KRaft controller voter** quản lý metadata quorum và điều phối trạng thái cluster. Hai nhóm node có tải, tài nguyên và yêu cầu sẵn sàng khác nhau, vì vậy số broker không quyết định trực tiếp số controller.

Một cluster đủ dung lượng ở trạng thái bình thường vẫn có thể thiếu năng lực khi mất một broker hoặc cả Availability Zone (AZ). Capacity plan cần tính cả retention, replication factor, throughput, partition count, headroom phục hồi replica và phân bố failure domain. Bài này trình bày cách ước lượng số broker, chọn ba hay năm controller voter, bố trí broker/controller qua rack/AZ và kiểm chứng thiết kế trước khi đưa vào production.

## 1. Phân biệt broker, controller và failure domain

Kafka có hai vai trò chính trong kiến trúc KRaft:

| Vai trò | Trách nhiệm | Tài nguyên chính |
|---|---|---|
| Broker | Lưu topic-partition replica, nhận produce/fetch, phục vụ client và replica fetcher | Disk, network, CPU, memory, page cache |
| Controller | Quản lý metadata log/quorum, broker registration, topic/partition metadata, ACL và thay đổi cluster | CPU, memory, disk metadata, network ổn định và latency thấp |

Broker chịu tải dữ liệu theo byte, record, request và partition. Controller chịu tải metadata theo số topic/partition, broker, ACL, cấu hình và tốc độ thay đổi metadata. Controller không lưu toàn bộ dữ liệu topic và không thay thế broker.

**Failure domain** là phạm vi hạ tầng có thể gặp sự cố chung:

- Process/node: một tiến trình hoặc máy chủ bị lỗi.
- Rack: nguồn điện, switch hoặc top-of-rack network switch của một rack gặp sự cố.
- Availability Zone (AZ): một vùng hạ tầng độc lập trong cloud hoặc data center.
- Region/site: một vùng địa lý hoặc trung tâm dữ liệu lớn hơn.

Nếu các replica của cùng partition hoặc các controller voter cùng nằm trong một failure domain, một sự cố chung có thể làm mất nhiều bản sao hoặc mất quorum cùng lúc. Thiết kế phải phân bố replica và voter theo failure domain mà hệ thống cam kết chịu được.

## 2. Những câu hỏi cần trả lời trước khi đếm node

Đừng bắt đầu bằng câu hỏi “cần bao nhiêu broker cho Kafka?”. Trước hết cần xác định:

1. Ingress throughput trung bình, đỉnh và burst là bao nhiêu byte/giây hoặc record/giây?
2. Payload trung bình, p95/p99 size và tỷ lệ nén thực tế ra sao?
3. Retention theo thời gian/dung lượng là bao lâu? Topic dùng delete retention hay compaction?
4. Replication factor và `min.insync.replicas` cần bao nhiêu?
5. Consumer đọc bao nhiêu lần, có nhiều consumer group cùng đọc một dữ liệu không?
6. Số partition hiện tại và số partition dự kiến trong vòng đời cluster?
7. Mục tiêu chịu lỗi là một broker, một rack hay một AZ?
8. Sau khi mất failure domain, hệ thống có cần tiếp tục ghi và khôi phục đủ replication factor không?
9. SLO về produce/fetch latency, throughput và thời gian phục hồi là gì?
10. Có Kafka Connect, Kafka Streams, tiered storage, cross-region replication hoặc workload quản trị bổ sung không?

Các con số phải được đo trên payload và cấu hình production gần nhất có thể. Một bài benchmark chỉ dùng record nhỏ, không bật TLS, replication hoặc compression sẽ không phản ánh đúng năng lực cluster thực.

## 3. Chọn số broker theo nhiều giới hạn

Số broker cần thỏa đồng thời nhiều dimension:

| Dimension | Câu hỏi | Dấu hiệu giới hạn |
|---|---|---|
| Storage | Có đủ disk cho dữ liệu giữ lại, replica và recovery không? | Disk utilization cao, log directory sắp đầy |
| Write throughput | Broker có nhận produce và replica write đủ nhanh không? | Produce latency, request queue, disk/network saturation |
| Read throughput | Broker có phục vụ consumer fetch và follower fetch đủ nhanh không? | Fetch latency, network egress, page cache miss |
| CPU | Có đủ CPU cho request, compression, TLS, checksum và background task không? | CPU saturation, request handler idle thấp, GC pressure |
| Memory/page cache | Có đủ cache cho hot segment/index không? | Disk read tăng, page cache hit giảm, GC/heap pressure |
| Partition capacity | Có thể quản lý số partition và leader phân bố hợp lý không? | Metadata/replica overhead, file descriptors, startup/recovery chậm |
| Failure headroom | Sau khi mất broker/rack/AZ, phần còn lại có gánh được tải và phục hồi replica không? | N-1 hoặc AZ-loss scenario vượt capacity |

Số broker cuối cùng phải là giá trị lớn nhất trong các ước lượng theo storage, throughput, CPU, partition và failure scenario, sau đó kiểm chứng bằng benchmark. Chỉ tính storage thường cho kết quả thiếu vì Kafka có thể đầy CPU hoặc network trước khi disk đầy.

Có một mức sàn về placement: nếu replication factor là `RF`, cần ít nhất `RF` broker khác nhau để đặt các replica của một partition trên broker riêng biệt. Nếu yêu cầu mỗi replica nằm ở một AZ độc lập, cần ít nhất `RF` AZ độc lập. Đây chỉ là điều kiện topology tối thiểu, không phải số broker đủ capacity.

## 4. Ước lượng số broker theo storage

Với topic dùng retention theo thời gian, có thể ước lượng dung lượng log logic trước replication:

\[
L = W \times T
\]

Trong đó:

- `W`: tốc độ dữ liệu thực sự ghi vào log sau compression, tính bằng byte/giây.
- `T`: thời gian retention, tính bằng giây.
- `L`: dung lượng log logic của một bản sao trong khoảng retention.

Tổng dung lượng replica vật lý gần đúng:

\[
P = L \times RF \times G
\]

Trong đó:

- `RF`: replication factor.
- `G`: hệ số tăng trưởng/dự phòng cho tăng traffic, retention drift, segment/index overhead và sai số ước lượng.
- `P`: dung lượng dữ liệu replica cần chứa trên toàn cluster.

Nếu throughput đầu vào đo từ payload chưa nén, cần nhân với compression ratio thực tế trước khi tính storage. Ví dụ compression ratio 0,4 nghĩa là log bytes sau nén xấp xỉ 40% payload bytes trước nén; tỷ lệ này phụ thuộc codec, batch size và dữ liệu.

### Dung lượng usable trên mỗi broker

Không nên dùng 100% dung lượng disk danh nghĩa làm capacity cho log. Cần chừa khoảng trống cho:

- Reassignment và phục hồi replica sau sự cố.
- Segment mới, index, checkpoint và file tạm.
- Compaction và log cleanup.
- Tăng trưởng ngoài dự báo.
- Mất cân bằng partition/replica giữa broker.
- Thời gian vận hành để xử lý disk gần đầy mà không phải di chuyển dữ liệu khẩn cấp.

Gọi:

- `C`: dung lượng log directory khả dụng trên một broker sau khi trừ OS/system reserve.
- `U`: mức sử dụng disk mục tiêu tối đa trong trạng thái phục hồi đã tính đến, ví dụ 0,65.
- `F`: số broker dự kiến có thể mất trong failure scenario.

Số broker tối thiểu theo storage gần đúng:

\[
N_{storage} = \left\lceil\frac{P}{C \times U}\right\rceil + F
\]

Công thức cộng `F` để phần broker còn lại vẫn có thể chứa tổng replica sau khi mất `F` broker và tái tạo các bản sao bị mất. Đây là mô hình cân bằng đơn giản; với AZ/rack failure cần thay `F` bằng số broker mất trong failure domain lớn nhất hoặc kiểm tra trực tiếp số broker còn lại.

Nếu chỉ cần capacity steady-state và chấp nhận chưa khôi phục đủ replication factor ngay sau sự cố, có thể tính thêm một con số không có `+F`, nhưng production plan nên nêu rõ thời gian chấp nhận chạy dưới replication factor mục tiêu.

### Ví dụ tính storage cho broker

Giả sử:

| Thông số | Giá trị giả định |
|---|---:|
| Ingress sau compression | 100 MB/s |
| Retention | 7 ngày |
| Replication factor | 3 |
| Growth/reserve factor | 1,2 |
| Log disk khả dụng mỗi broker | 12 TB |
| Target utilization | 65% |
| Failure scenario | Mất 1 broker |

Các đơn vị MB/TB trong ví dụ dùng hệ thập phân (1 TB = 1.000 GB); nếu dùng MiB/TiB, hãy đổi nhất quán trong toàn bộ phép tính.

Dung lượng logic giữ lại:

\[
L = 100\ MB/s \times 604{,}800\ s = 60.48\ TB
\]

Dung lượng replica toàn cluster có tính growth factor:

\[
P = 60.48 \times 3 \times 1.2 = 217.728\ TB
\]

Usable target mỗi broker:

\[
C \times U = 12 \times 0.65 = 7.8\ TB
\]

Số broker cần để chịu mất một broker:

\[
N_{storage} = \left\lceil\frac{217.728}{7.8}\right\rceil + 1
            = 28 + 1 = 29\ brokers
\]

Với 29 broker, nếu mất một broker và phân phối lại replica đều trên 28 broker còn lại, tổng dung lượng target là `28 × 7,8 = 218,4 TB`, vừa đủ cho 217,728 TB theo giả định. Thực tế cần thêm headroom nếu partition size lệch nhiều, compaction tạo write amplification hoặc thời gian retention dao động.

Đây mới là kết quả theo storage và failure của một broker. Nếu cần chịu mất cả AZ chứa nhiều broker, phải tính lại theo số broker còn lại sau khi mất AZ; không thể dùng kết quả 29 broker này làm cam kết chịu lỗi AZ.

## 5. Tính storage cho topic compacted

Với topic có `cleanup.policy=compact`, phép tính `ingress × retention time` có thể phóng đại dung lượng live state vì Kafka giữ phiên bản mới nhất theo key và dọn các phiên bản cũ theo tiến trình compaction.

Ước lượng cần dựa trên:

- Số key duy nhất và kích thước value/header trung bình.
- Tỷ lệ key update mỗi ngày.
- Tốc độ tombstone và `delete.retention.ms`.
- Compaction lag, segment size và thời gian cleanup.
- Các segment chưa được compact và dung lượng tạm thời trong lúc compaction.
- Replication factor và recovery headroom.

Với compacted topic, cần đo kích thước log thực sau các chu kỳ compaction trong môi trường đại diện. Không giả định compaction giữ đúng một record nhỏ cho mỗi key ngay lập tức; dữ liệu cũ có thể vẫn còn trong segment chưa compact.

Topic dùng `compact,delete` cần tính cả retention time/size và compaction behavior. Topic tiered storage cũng cần tách local disk cache khỏi remote object storage capacity/cost; dữ liệu remote không biến mất khỏi bài toán retention và recovery.

## 6. Ước lượng broker theo write throughput

Gọi `W` là ingress bytes/giây đã được đo ở định dạng broker log, `RF` là replication factor. Một ước lượng aggregate đơn giản:

- Leader append khoảng `W` byte/giây.
- Follower replica append thêm khoảng `W × (RF - 1)` byte/giây trên toàn cluster.
- Tổng disk write do replication xấp xỉ `W × RF`, chưa tính compaction, index, checkpoint và write amplification.

Với ví dụ `W = 100 MB/s`, `RF = 3`, aggregate disk write xấp xỉ 300 MB/s. Nếu phân phối đều trên 29 broker thì trung bình lý thuyết khoảng 10,3 MB/s/broker. Con số trung bình này không phản ánh hotspot, partition leader skew, replication placement hoặc peak traffic.

### Capacity theo throughput và N-1

Gọi `D_w` là tổng disk-write demand toàn cluster trong failure scenario. Ở trạng thái bình thường, nó xấp xỉ `W × RF`; nếu cần phục hồi replica trong thời hạn `RTO`, cộng thêm throughput tái tạo replica `D_recovery` (dung lượng replica bị mất chia cho thời gian phục hồi mục tiêu), cùng các write amplification khác. Gọi `S_w` là disk-write throughput an toàn đã benchmark của một broker trong cấu hình thực tế (đã bật TLS, replication, compression, acks và workload tương tự production). Nếu cần chịu mất `F` broker, số broker cần thỏa:

\[
N_{write} \geq \left\lceil\frac{D_w}{S_w}\right\rceil + F
\]

Đây là ước lượng tổng hợp, không phải bảo đảm tuyến tính. Leader distribution và follower fetch có thể khiến một broker chịu tải cao hơn trung bình; nên kiểm tra max broker utilization trong benchmark và mô phỏng broker failure.

### Network không chỉ có ingress

Mỗi broker có thể đồng thời:

- Nhận produce traffic từ producer tới partition leader.
- Gửi replica data tới follower broker.
- Nhận replica data từ leader nếu đang là follower.
- Gửi fetch data tới consumer group.
- Nhận request metadata, admin và coordinator traffic.
- Phục vụ cross-cluster replication hoặc tiered storage nếu có.

Aggregate inter-broker replication bytes ở mức cluster có thể ước lượng khoảng `W × (RF - 1)` cho luồng append mới, nhưng network interface của từng broker vừa gửi vừa nhận. Cần cộng consumer egress và các luồng khác, đồng thời benchmark full-duplex bandwidth, packet rate, TLS CPU và network latency.

Không lấy ingress trung bình chia số broker làm network capacity. Broker đang giữ nhiều leader hoặc follower của partition lớn có thể có network load cao hơn nhiều.

## 7. Tính read throughput và số consumer

Consumer đọc từ leader hoặc follower tùy cấu hình/version và cơ chế fetch. Một topic được nhiều consumer group đọc sẽ tạo nhiều lượt egress; retention không nhân lên theo số group nhưng network/disk read có thể tăng đáng kể.

Ước lượng read demand:

\[
R_{total} \approx W \times G_c \times A
\]

Trong đó:

- `G_c`: số consumer group độc lập đọc toàn bộ luồng.
- `A`: hệ số đọc lại/replay hoặc amplification do consumer đọc lại nhiều lần.

Đây là ước lượng đơn giản cho workload mà mỗi group đọc gần như toàn bộ dữ liệu. Nếu consumer filter hoặc chỉ đọc một phần partition, dùng số byte fetch thực tế thay thế.

Nếu `S_r` là read egress throughput an toàn đã benchmark trên một broker, có thể ước lượng thêm:

\[
N_{read} \geq \left\lceil\frac{R_{total}}{S_r}\right\rceil + F
\]

`S_r` phải được đo với số consumer group, TLS, compression, page-cache behavior và fetch pattern gần production. Nếu consumer đọc follower hoặc có rack-aware/follower fetching, phân bố read load sẽ khác so với chỉ đọc leader.

Tính capacity broker theo network egress và disk/page-cache read, không chỉ theo write. Consumer chậm có thể tạo lag lớn nhưng không nhất thiết làm broker CPU cao; nhiều group đọc cùng topic có thể làm network egress tăng mạnh.

## 8. Số partition ảnh hưởng số broker thế nào?

Partition quyết định đơn vị song song của Kafka. Số partition ảnh hưởng:

- Số task/consumer có thể xử lý song song.
- Số leader và replica phân phối lên broker.
- Số log segment, index, file descriptor và metadata.
- Thời gian leader election, reassignment, recovery và startup.
- Memory và CPU overhead trên broker/controller.

Không có một con số partition-per-broker cố định đúng cho mọi phiên bản và workload. Một broker mạnh có thể xử lý nhiều partition nhỏ; một broker có partition lớn, nhiều connection hoặc compaction nặng có thể chạm giới hạn sớm hơn.

### Tính partition theo consumer parallelism

Với consumer group truyền thống, một partition chỉ được assign cho tối đa một consumer member tại một thời điểm. Nếu cần tối đa `C` consumer active để xử lý một topic, số partition của topic thường cần ít nhất `C`, nếu workload phân phối đều và consumer có đủ capacity.

Ví dụ cần 12 consumer worker active cho `orders.events`, topic có thể cần ít nhất 12 partition. Nhưng nếu mỗi partition throughput quá lớn hoặc key skew nặng, 12 partition chưa chắc đủ throughput. Nếu chỉ có 4 partition, tăng consumer member lên 12 không tạo thêm parallelism cho topic đó.

Với Kafka Share Groups, nhiều consumer có thể xử lý record trong cùng partition theo record lock, nhưng vẫn phải sizing partition, broker và lock/in-flight capacity theo semantics riêng. Không áp dụng máy móc quy tắc consumer group truyền thống cho share group.

### Partition không phải nút tăng tốc miễn phí

Tăng partition có thể tăng parallelism nhưng cũng tăng:

- Metadata và controller workload.
- Số replica log, segment, index và file handle.
- Reassignment/recovery work.
- Số batch/connection/leader distribution cần producer quản lý.
- Overhead consumer assignment và state store/task nếu dùng Kafka Streams.

Chọn partition count theo throughput cần thiết, consumer parallelism, ordering/key cardinality và operational budget. Không tạo hàng chục nghìn partition chỉ để “dự phòng” nếu chưa có benchmark và kế hoạch vận hành.

## 9. Tính số broker theo failure headroom

Capacity phải được kiểm tra ở cả hai trạng thái:

1. Cluster bình thường, mọi broker hoạt động.
2. Cluster mất một broker hoặc một failure domain nhưng workload vẫn cần đáp ứng SLO đã cam kết.

Nếu mỗi broker có safe capacity `S`, tổng demand là `D`, cần chịu mất `F` broker và phân phối đều, điều kiện đơn giản:

\[
N \geq \left\lceil\frac{D}{S}\right\rceil + F
\]

Ví dụ demand cần 8 broker ở mức safe utilization; nếu phải chịu mất một broker mà vẫn giữ capacity, cần tối thiểu 9 broker theo mô hình tuyến tính. Nếu chịu mất ba broker cùng một AZ, cần cộng số broker bị mất trong AZ đó, không chỉ cộng 1.

Đây là điều kiện về capacity, không tự bảo đảm partition có leader/replica khả dụng. Replica assignment, rack awareness, ISR, `min.insync.replicas` và controller quorum phải được thiết kế riêng.

### Normal utilization phải thấp hơn giới hạn sau sự cố

Nếu cluster có (N) broker và mất một broker, demand vốn phân bố trên (N) node sẽ dồn lên (N-1) node. Mức sử dụng trung bình tăng theo hệ số:

\[
\text{Failover multiplier} = \frac{N}{N-1}
\]

Ví dụ 6 broker, khi mất một broker, tải trung bình trên mỗi broker còn lại tăng khoảng 20% so với trạng thái bình thường (`6/5 = 1,2`). Vì vậy, nếu safe utilization tối đa là 70% trong trạng thái failover, normal utilization nên không vượt khoảng `70% × 5/6 = 58,3%` theo giả định phân bố đều.

Thực tế có partition leader và key skew không đồng đều. Cần kiểm tra broker chịu tải cao nhất, không chỉ average utilization.

## 10. Chọn ba hay năm controller voter?

KRaft dùng Raft quorum để replicate metadata log. Số voter cần là số lẻ để tối ưu số node có thể mất mà vẫn giữ majority.

Với `V` voter:

\[
\text{Majority} = \left\lfloor\frac{V}{2}\right\rfloor + 1
\]

\[
\text{Tolerated voter failures} = \left\lfloor\frac{V-1}{2}\right\rfloor
\]

| Controller voter | Majority cần | Số voter có thể mất mà vẫn còn quorum |
|---:|---:|---:|
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

### Ba controller voter

Ba voter là lựa chọn production phổ biến:

- Chịu được một voter/node lỗi mà vẫn còn majority.
- Có thể bố trí một voter trên mỗi AZ trong triển khai ba AZ.
- Chi phí hạ tầng và metadata replication thấp hơn năm voter.
- Phù hợp với phần lớn cluster có metadata workload thông thường.

Nếu một voter bị mất trong cluster ba voter, hai voter còn lại vẫn tạo được majority. Nếu mất hai voter, quorum không thể commit metadata mới.

Một voter chỉ phù hợp cho development/test hoặc môi trường không yêu cầu HA; mất node duy nhất đồng nghĩa mất quorum metadata.

### Năm controller voter

Năm voter tăng khả năng chịu lỗi node lên hai voter và có thể phù hợp khi yêu cầu availability cao hơn hoặc failure domain phức tạp. Đổi lại:

- Thêm node, network và chi phí vận hành.
- Metadata replication phải duy trì thêm follower.
- Quorum cần ba voter để commit.
- Không tự tăng throughput produce/fetch vì controller không phục vụ partition data.

Không tăng lên năm voter chỉ vì cluster có nhiều broker. Quyết định dựa trên failure requirement, metadata workload, latency và topology failure domain.

### Vì sao không chọn thật nhiều controller?

Thêm voter không làm quorum “khỏe hơn” vô hạn. Majority tăng, số follower cần replicate tăng và metadata commit chịu thêm phụ thuộc vào mạng/độ trễ quorum. Thực tế thường dùng ba hoặc năm voter; hơn năm cần lý do rõ ràng và benchmark theo release/kiến trúc cụ thể.

## 11. Controller count không phụ thuộc trực tiếp vào broker count

Một cluster có 6 broker hoặc 60 broker vẫn có thể dùng 3 controller voter nếu metadata workload và failure requirement phù hợp. Số controller không phải phép chia số broker cho một tỷ lệ cố định.

Controller sizing cần xét:

- Số topic và partition.
- Số broker và tốc độ broker registration/fencing.
- Số ACL, quota và dynamic configuration.
- Tần suất tạo/xóa topic, tăng partition, thay assignment và config.
- Kích thước metadata log/snapshot.
- Thời gian startup/recovery và tốc độ replay metadata.
- CPU, heap/GC và network latency giữa voter.

Nếu metadata workload tăng mạnh, cần xem controller CPU/memory, commit/election latency, metadata log và startup time. Thêm broker không phải cách trực tiếp giải quyết controller bottleneck; thêm controller voter cũng không nhất thiết cải thiện metadata latency nếu nguyên nhân là disk/network hoặc controller process quá tải.

## 12. Dedicated controller hay combined broker/controller?

KRaft hỗ trợ các node chạy role riêng hoặc kết hợp:

| Mô hình | Cấu hình role | Ưu điểm | Hạn chế |
|---|---|---|---|
| Dedicated broker | `process.roles=broker` | Tách data-plane khỏi control-plane | Cần node riêng cho controller |
| Dedicated controller | `process.roles=controller` | Controller không tranh disk/network data với broker | Thêm hạ tầng và vận hành |
| Combined node | `process.roles=broker,controller` | Ít node, đơn giản cho dev/test hoặc cluster nhỏ | Broker load có thể ảnh hưởng quorum; khó scale role độc lập |

### Production nên tách role khi có yêu cầu sẵn sàng cao

Dedicated controller có các lợi ích:

- Broker CPU/disk/network spike ít ảnh hưởng controller quorum.
- Có thể scale broker theo data throughput mà không tăng voter count.
- Có thể bảo trì broker mà không tác động trực tiếp controller process.
- Dễ đặt controller voter vào các AZ/failure domain riêng.

Combined mode vẫn được hỗ trợ và có thể phù hợp lab, development hoặc deployment nhỏ có giới hạn. Với production lớn/quan trọng, dedicated controller thường giúp tách failure và resource contention tốt hơn.

Việc chuyển từ combined sang dedicated không nên coi là chỉ đổi `process.roles` rồi restart. Đây là thay đổi topology cluster cần quy trình migration/upgrade phù hợp với Kafka version, quorum type và storage metadata hiện tại.

## 13. Kích thước phần cứng controller

Controller không lưu partition data nên disk thường nhỏ hơn broker nhiều, nhưng không có nghĩa có thể chạy trên máy yếu hoặc storage tạm thời.

Ưu tiên:

- CPU đủ cho metadata request, Raft, snapshot và recovery.
- Memory/heap đủ để giữ metadata image và tránh GC pause kéo dài.
- SSD bền vững, latency thấp cho metadata log và snapshot.
- Network ổn định, latency thấp giữa controller voter và broker.
- Đồng hồ đồng bộ và process được giám sát.
- Disk/metadata directory không nằm trên ephemeral storage nếu mất node đồng nghĩa mất trạng thái cần phục hồi.

Không dùng controller để chạy workload ứng dụng nặng, batch job hoặc monitoring stack có thể làm CPU/disk/network giật cục. Sizing vCPU/RAM cụ thể phụ thuộc số partition/broker và metadata churn; benchmark/soak test theo scale mục tiêu thay vì dùng một cấu hình cố định cho mọi cluster.

## 14. Bố trí controller voter qua ba Availability Zone

Với ba voter và ba AZ, cách bố trí đơn giản là một voter mỗi AZ:

```text
AZ-a                 AZ-b                 AZ-c
Controller 100       Controller 101       Controller 102
     voter                voter                voter
```

Khi một AZ mất, còn hai voter trong hai AZ khác, vẫn có majority 2/3. Khi mất hai AZ, chỉ còn một voter và quorum không thể commit metadata.

Không đặt hai trong ba voter cùng một AZ nếu mục tiêu là chịu được bất kỳ một AZ outage. Nếu hai voter nằm cùng AZ, mất AZ đó sẽ làm mất majority ngay cả khi AZ còn lại vẫn hoạt động.

### Năm voter trên ba AZ

Một phân bố có thể là 2-2-1:

```text
AZ-a: 2 voters
AZ-b: 2 voters
AZ-c: 1 voter
```

Mất bất kỳ một AZ trong bố trí này vẫn còn ít nhất ba voter và giữ majority 3/5. Tuy nhiên, mất hai AZ có thể để lại chỉ một hoặc hai voter, không đủ majority. Năm voter tăng khả năng chịu lỗi node nhưng không tự động đồng nghĩa chịu được hai AZ outage; điều đó phụ thuộc cách phân bố voter và số AZ độc lập.

## 15. Bố trí broker replica qua rack/AZ

Broker nên được phân bố qua các failure domain và cấu hình rack identity bằng `broker.rack` khi dùng rack-aware replica assignment.

Ví dụ ba AZ, replication factor 3:

```text
Topic: orders.events, partition 0, RF=3

AZ-a / rack-a: broker 1 -> replica 0 (leader)
AZ-b / rack-b: broker 5 -> replica 1
AZ-c / rack-c: broker 9 -> replica 2
```

Một AZ outage làm một replica unavailable, nhưng hai replica ở hai AZ còn lại vẫn có thể duy trì partition nếu ISR và controller/broker health đáp ứng.

### `broker.rack` và replica placement

Ví dụ broker config:

```properties
# broker 1
broker.rack=az-a

# broker 5
broker.rack=az-b

# broker 9
broker.rack=az-c
```

Trong production, chọn `broker.rack` theo failure domain cần bảo vệ. Nếu mục tiêu chính là chịu AZ outage, dùng một giá trị chung cho tất cả broker trong cùng AZ để Kafka coi AZ là rack failure domain. Nếu cần bảo vệ đồng thời cả AZ và rack vật lý bên trong AZ, một giá trị rack đơn không biểu diễn đầy đủ hai tầng failure domain; cần thiết kế assignment có chủ đích và xác minh từng partition sau create/reassignment.

Nếu số replica lớn hơn số rack, một số rack sẽ chứa nhiều replica của cùng partition. Khi đó cần đánh giá failure model và không tuyên bố chịu được outage của rack mà thực tế có thể làm mất quá nhiều ISR.

## 16. Kết hợp replication factor và `min.insync.replicas`

Ví dụ thường gặp cho workload cần durability cao:

```bash
# Tạo topic với replication factor 3
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create --topic orders.events --partitions 24 --replication-factor 3

# Topic-level durability policy
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name orders.events \
  --alter --add-config min.insync.replicas=2
```

Producer:

```properties
acks=all
enable.idempotence=true
```

Với RF=3 và min ISR=2:

- Bình thường có ba replica trong ISR.
- Mất một broker/AZ làm một replica unavailable, hai replica còn lại vẫn có thể đáp ứng min ISR.
- Nếu thêm một replica nữa rời ISR và ISR giảm còn một, producer `acks=all` không thể tiếp tục ghi theo min ISR policy.
- Khi replica quay lại ISR, khả năng ghi được phục hồi.

Đây là đánh đổi availability/durability. Không đặt `min.insync.replicas=1` chỉ để tránh produce error khi mất replica nếu yêu cầu durability cần ít nhất hai bản sao xác nhận.

`acks=all` xác nhận theo tập ISR hiện tại; nó không có nghĩa chờ mọi replica trong replication factor nếu replica đã bị loại khỏi ISR. `min.insync.replicas` đặt số replica tối thiểu để chấp nhận ghi.

## 17. Tính số broker khi cần chịu một AZ outage

Failure scenario theo AZ mạnh hơn mất một broker vì một AZ có thể chứa nhiều broker. Giả sử:

- Có `A` AZ.
- Broker phân bố tương đối đều.
- Mất AZ lớn nhất làm mất `F_AZ` broker.
- Mỗi broker có usable target capacity `C × U`.

Điều kiện storage sau khi mất AZ:

\[
P \leq (N - F_{AZ}) \times C \times U
\]

Với ba AZ phân bố đều, `F_AZ` xấp xỉ `ceil(N/3)`. Cần tìm số nguyên `N` nhỏ nhất thỏa:

\[
N - \left\lceil\frac{N}{3}\right\rceil
\geq \left\lceil\frac{P}{C \times U}\right\rceil
\]

### Tiếp tục ví dụ storage

Ở ví dụ trước, cần ít nhất 28 broker còn sống để chứa dữ liệu và phục hồi RF ở target utilization 65%. Nếu muốn chịu mất bất kỳ một trong ba AZ, phân bố đều và giữ đủ capacity sau khi mất AZ:

- 42 broker chia thành 14 broker/AZ.
- Mất một AZ còn 28 broker.
- 28 broker × 7,8 TB usable target = 218,4 TB.
- Dung lượng cần chứa là 217,728 TB.

Theo mô hình đơn giản, cần khoảng 42 broker để vừa đủ capacity sau một AZ outage và tái tạo replica. Cần bổ sung headroom nếu partition size lệch, một AZ có nhiều leader nóng hoặc cần phục hồi trong thời gian ngắn.

Điều này cho thấy “đủ disk khi cluster khỏe” và “đủ disk sau AZ outage” là hai tiêu chí rất khác nhau. Nếu không cần tự động phục hồi đầy đủ RF trong lúc AZ mất, có thể chọn policy khác, nhưng phải ghi rõ thời gian chấp nhận degraded replication và kế hoạch khôi phục.

## 18. Ví dụ topology production ba AZ

Một mô hình minh họa cho cluster quan trọng:

| Thành phần | AZ-a | AZ-b | AZ-c | Tổng |
|---|---:|---:|---:|---:|
| Broker | 14 | 14 | 14 | 42 |
| Controller voter | 1 | 1 | 1 | 3 |
| Replica mỗi partition (RF=3) | 1 | 1 | 1 | 3 |

Trong mô hình này:

- Ba controller voter có thể chịu mất một AZ và vẫn còn majority.
- Mỗi partition RF=3 được bố trí một replica mỗi AZ.
- Capacity broker đã được tính để còn 28 broker sau khi mất một AZ.
- `min.insync.replicas=2` cho phép ghi với hai replica còn trong ISR nếu các điều kiện khác bình thường.
- Reassignment/re-replication sau sự cố cần được throttle và theo dõi để không làm quá tải hai AZ còn lại.

Đây là ví dụ số học, không phải sizing khuyến nghị chung. Với workload nhỏ hơn, có thể cần ít broker hơn; với throughput lớn hoặc AZ capacity không đồng đều, có thể cần nhiều hơn. Phải benchmark và kiểm tra placement thật.

## 19. Ví dụ cluster nhỏ hơn: 9 broker và 3 controller

Một cluster nhỏ hơn có thể bố trí:

| Thành phần | AZ-a | AZ-b | AZ-c | Tổng |
|---|---:|---:|---:|---:|
| Broker | 3 | 3 | 3 | 9 |
| Dedicated controller voter | 1 | 1 | 1 | 3 |

Với RF=3, mỗi partition có thể có một replica ở mỗi AZ. Cluster chịu được một broker hoặc một AZ outage về mặt quorum/replica availability nếu assignment đúng. Tuy nhiên, 9 broker chỉ đủ capacity khi throughput, storage và consumer egress nằm trong safe capacity của 8 broker còn lại sau một broker failure hoặc 6 broker sau một AZ failure.

Không kết luận 9 broker là đủ chỉ vì RF=3 và có ba AZ. Nếu storage/throughput formula yêu cầu 15 broker hoặc 24 broker, phải tăng broker count hoặc thay đổi workload/retention/throughput requirement.

## 20. Static và dynamic KRaft quorum theo Kafka version

KRaft đã có thay đổi về cách bootstrap và quản lý controller quorum qua các phiên bản Kafka. Các cluster dùng static quorum có thể khai báo `controller.quorum.voters`; các phiên bản hỗ trợ dynamic quorum dùng bootstrap server list và cơ chế quản lý membership khác. Không trộn cấu hình của hai mô hình.

Ví dụ minh họa node role trong mô hình dedicated:

```properties
# Broker node
process.roles=broker
node.id=1
controller.listener.names=CONTROLLER
```

```properties
# Controller node
process.roles=controller
node.id=100
controller.listener.names=CONTROLLER
```

Danh sách endpoint/bootstrap và cấu hình quorum phải theo đúng Kafka version và kiểu quorum đã chọn. Trước khi triển khai, dùng tài liệu KRaft của đúng release để xác định property bắt buộc, controller listener, security protocol map, metadata directory và quy trình bootstrap/membership. Không sao chép một `controller.quorum.voters` config từ cluster cũ sang cluster dynamic quorum mà chưa kiểm tra.

## 21. Controller và broker cần failure policy khác nhau

Khi mất broker:

- Partition leader có thể được bầu từ ISR nếu còn replica phù hợp.
- Consumer/producer có thể gặp leader change và retry.
- Replica bị mất cần được tái tạo để khôi phục RF.
- Broker còn lại phải có capacity cho traffic và re-replication.

Khi mất controller voter:

- Nếu vẫn còn majority, quorum có thể tiếp tục commit metadata.
- Nếu mất majority, metadata changes không thể được commit; thao tác quản trị và một số trạng thái cluster bị ảnh hưởng.
- Data-plane hiện hữu có thể tiếp tục một số hoạt động trong khi controller quorum không có majority, nhưng không được xem là cluster khỏe; broker failure/metadata change tiếp theo có thể khó xử lý.

Không dùng broker count để suy ra controller quorum chịu lỗi. Hai nhóm cần health check và runbook riêng.

## 22. Các chỉ số xác minh capacity và failure domain

### Broker metrics

- Disk utilization/free space theo từng log directory.
- Bytes in/out và network throughput theo broker.
- Produce/fetch request rate và p95/p99 latency.
- Request handler/network processor idle.
- CPU, heap/GC, page cache và file descriptor.
- Under-replicated/offline partitions, ISR shrink/expand.
- Replica fetcher lag và reassignment throughput.
- Leader/partition count theo broker.

### Controller metrics

- Current leader/epoch và số voter/observer.
- Metadata quorum high watermark và follower lag.
- Commit/election latency và leader change rate.
- Controller CPU, heap/GC, disk latency và network.
- Metadata log/snapshot size, startup/recovery time.
- Broker registration, heartbeat timeout và fencing.

### Failure-domain metrics

- Broker/voter count theo rack/AZ.
- Số replica của mỗi partition theo failure domain.
- Số controller voter còn lại sau khi loại một rack/AZ khỏi mô hình.
- Disk/network capacity còn lại sau failure scenario.
- Số partition còn leader và số ISR sau khi mô phỏng outage.

Dashboard cần drill-down theo broker, topic-partition và AZ. Cluster average có thể che giấu một AZ đang có nhiều broker nóng hoặc một partition có replica tập trung sai failure domain.

## 23. Quy trình capacity planning từ yêu cầu tới node count

Một quy trình thực tế:

1. Thu thập ingress/egress, peak factor, payload distribution, retention và compression ratio.
2. Phân loại topic: delete retention, compacted, compact+delete, transactional hoặc tiered.
3. Chọn RF, `min.insync.replicas` và durability semantics.
4. Tính storage replica và growth factor.
5. Tính broker count cho steady-state và failure scenario (broker/rack/AZ).
6. Benchmark write/read throughput mỗi broker với cấu hình giống production.
7. Tính broker count theo CPU/network/disk throughput và consumer egress.
8. Xác định partition count theo throughput, ordering và consumer parallelism.
9. Chọn controller voter count (thường 3 hoặc 5) theo failure requirement.
10. Bố trí controller voter và broker replica qua rack/AZ.
11. Kiểm tra leader distribution, disk distribution và rack-aware assignment.
12. Mô phỏng mất broker, mất rack/AZ và đo thời gian recovery.
13. Thêm headroom cho growth, maintenance, reassignment và peak traffic.
14. Ghi lại assumptions, công thức, benchmark result và trigger mở rộng cluster.

Capacity plan cần được cập nhật khi traffic, retention, replication factor, số consumer group hoặc partition count thay đổi đáng kể.

## 24. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách tránh |
|---|---|---|
| Chọn broker count chỉ theo dung lượng disk | CPU/network hoặc partition overhead chạm giới hạn trước disk | Tính storage, write/read throughput, CPU và partition song song |
| Dùng disk 100% trong capacity model | Không còn chỗ phục hồi/reassignment và segment growth | Chọn target utilization và reserve rõ ràng |
| Chỉ tính mất một broker trong cluster ba AZ | AZ outage có thể làm mất nhiều broker cùng lúc | Tính số broker còn lại sau khi mất AZ lớn nhất |
| Cho ba controller voter cùng một AZ | Mất AZ có thể mất quorum | Đặt voter ở ba failure domain độc lập |
| Tăng controller count để tăng produce throughput | Không giải quyết broker data-plane bottleneck | Scale broker và partition placement theo throughput |
| Coi observer là voter | Tính sai majority/failure tolerance | Chỉ tính voter trong quorum majority |
| Chạy combined role cho cluster lớn mà không đánh giá | Broker load có thể ảnh hưởng controller | Dùng dedicated controller khi cần isolation/sẵn sàng cao |
| Tăng partition không giới hạn | Metadata, file, recovery và rebalance overhead tăng | Chọn partition theo parallelism/throughput và kiểm tra giới hạn |
| RF=3 nhưng replica cùng rack | Một rack outage có thể làm mất nhiều replica | Dùng rack awareness và xác minh assignment |
| `min.insync.replicas=1` chỉ để tránh lỗi ghi | Giảm durability khi replica khác đã rời ISR | Chọn min ISR theo yêu cầu dữ liệu và failure model |
| Dùng benchmark không bật TLS/replication | Ước lượng throughput quá lạc quan | Benchmark với security, acks, RF, compression và payload production |
| Chỉ kiểm tra average utilization | Broker/AZ nóng bị che giấu | Theo dõi max broker và partition skew |

## 25. Checklist thiết kế production

**Broker capacity:**

- [ ] Có số liệu ingress/egress trung bình, peak và burst.
- [ ] Retention, compression ratio, RF và growth factor được tính rõ.
- [ ] Disk capacity có headroom cho failure/re-replication.
- [ ] Throughput benchmark gồm TLS, compression, replication và `acks` production.
- [ ] CPU, network, disk, page cache và partition count đều được xem xét.
- [ ] Capacity được kiểm tra sau khi mất broker và failure domain mục tiêu.

**Controller quorum:**

- [ ] Chọn 3 hoặc 5 voter theo failure requirement.
- [ ] Majority được tính từ voter, không tính observer.
- [ ] Voter được phân bố qua rack/AZ độc lập.
- [ ] Dedicated controller được cân nhắc cho production quan trọng.
- [ ] Metadata storage bền vững, disk/network/CPU đủ và có monitoring.
- [ ] Static/dynamic quorum config đúng với Kafka release.

**Failure domain và replication:**

- [ ] `broker.rack` phản ánh failure domain thực.
- [ ] Replica của cùng partition được phân bố theo RF/rack policy.
- [ ] RF và `min.insync.replicas` khớp durability requirement.
- [ ] Producer `acks`/idempotence phù hợp policy.
- [ ] Có mô phỏng mất broker, rack và AZ.
- [ ] Có runbook reassignment/re-replication và throttle.

**Vận hành:**

- [ ] Có baseline utilization và ngưỡng scale-out.
- [ ] Có cảnh báo disk, network, CPU, ISR, offline partition và controller quorum.
- [ ] Có kế hoạch mở rộng broker/controller không gây thay đổi quorum tùy tiện.
- [ ] Lưu assumptions và benchmark để tái tính capacity khi workload thay đổi.

## 26. Ghi nhớ

Broker count được quyết định bởi storage, write/read throughput, CPU, network, partition overhead và failure headroom. Tính dung lượng replica theo retention × ingress sau compression × replication factor, cộng growth/reserve; sau đó kiểm tra số broker còn lại sau khi mất broker/rack/AZ có đủ capacity để tiếp tục phục vụ và tái tạo replica hay không. Benchmark phải giống workload production, không dùng một con số partition-per-broker hoặc MB/s/broker cố định cho mọi cluster.

Controller count là quyết định riêng. KRaft thường dùng ba voter để chịu một voter failure hoặc năm voter để chịu hai voter failure; majority chỉ tính voter, không tính observer. Đặt voter ở các failure domain độc lập: ba voter trên ba AZ giúp chịu một AZ outage. Năm voter trên ba AZ có thể chịu một AZ outage nếu phân bố hợp lý, nhưng không tự động chịu hai AZ outage.

Với production quan trọng, dedicated broker và dedicated controller giúp cô lập data-plane khỏi control-plane. Dùng `broker.rack`, replica assignment và `min.insync.replicas` để biến mục tiêu failure-domain thành placement thực tế. Capacity plan chỉ hoàn chỉnh khi đã mô phỏng mất broker/AZ, đo recovery, xác minh ISR/quorum và ghi rõ những failure scenario hệ thống thực sự chịu được.

## Tài liệu tham khảo

- [Apache Kafka – KRaft](https://kafka.apache.org/documentation/#kraft)
- [Apache Kafka – Broker Configs](https://kafka.apache.org/documentation/#brokerconfigs)
- [Apache Kafka – Replication](https://kafka.apache.org/documentation/#replication)
- [Apache Kafka – Operations](https://kafka.apache.org/documentation/#operations)
- [Apache Kafka – Monitoring](https://kafka.apache.org/documentation/#monitoring)
- [Apache Kafka – Rack-aware replica assignment](https://kafka.apache.org/documentation/#brokerconfigs_rack.awareness)
