# Chi phí topic nhỏ, partition nhiều và kết nối nhiều

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này phân tích chi phí vận hành khi hệ thống tạo nhiều topic nhỏ, chia quá nhiều partition hoặc mở quá nhiều kết nối client. Mục tiêu là biết phần overhead nào tăng theo topic, phần nào tăng theo partition, phần nào tăng theo connection, sau đó ước lượng capacity và chọn cách giảm chi phí mà vẫn giữ ordering, isolation, durability và availability.

Kafka không chỉ lưu payload. Mỗi topic và partition còn cần metadata, trạng thái replication, log segment, index, file descriptor, leader/ISR tracking và công việc quản trị. Mỗi client connection tiêu thụ socket, network buffer, TLS/SASL processing và request handling. Một workload có lưu lượng dữ liệu thấp vẫn có thể gây áp lực đáng kể nếu số topic, partition, consumer group hoặc connection tăng quá nhanh.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt overhead theo topic, partition, replica, consumer group và connection.
- Giải thích vì sao nhiều topic nhỏ vẫn tạo chi phí quản trị và metadata.
- Mô tả chi phí log segment, index, file handle, leader, ISR và recovery khi partition tăng.
- Phân tích chi phí socket, TLS handshake, authentication, buffer và request queue khi connection tăng.
- Phân biệt số client process với số socket thực tế trên từng broker.
- Ước lượng replica count, disk capacity, replication traffic và connection load.
- Xác định khi nào topic riêng là cần thiết và khi nào nên dùng shared topic.
- Chọn partition count theo throughput, ordering và consumer parallelism.
- Nhận diện consumer instance dư thừa và consumer group tạo thêm traffic.
- Tái sử dụng Kafka client đúng cách trong Java/Spring.
- Đo các metric quan trọng trước khi thay đổi cấu hình.
- Lập kế hoạch giảm topic/partition/connection có kiểm soát.
- Kiểm tra tác động của thay đổi lên latency, throughput, durability và chi phí vận hành.

## 2. Ba nguồn overhead cần tách riêng

Khi capacity planning, không gom mọi chi phí vào một con số “Kafka tải cao”. Hãy tách thành ba nhóm:

| Đối tượng | Overhead chính | Tăng theo |
|---|---|---|
| Topic | Metadata, config, ACL, naming/ownership, dashboard và thao tác quản trị | Số topic |
| Partition/replica | Log/index/segment, file handle, leader/ISR, replication, recovery, rebalance và metadata | Số partition và replication factor |
| Connection | Socket, file descriptor, network buffer, TLS/SASL, request queue, heartbeat và idle state | Số connection đồng thời và tốc độ tạo connection |

Ngoài ra, consumer group, Kafka Streams application, Connect task và monitoring series có thể tạo thêm overhead riêng. Một partition có nhiều consumer group đọc độc lập sẽ tạo thêm fetch traffic; một topic có nhiều partition sẽ tạo nhiều replica; một client kết nối đến nhiều broker sẽ tạo nhiều socket.

~~~mermaid
flowchart TD
    A[Kafka workload] --> B[Topic overhead]
    A --> C[Partition and replica overhead]
    A --> D[Connection overhead]
    B --> E[Metadata, config, ACL, operations]
    C --> F[Logs, indexes, leaders, ISR, recovery]
    D --> G[Sockets, buffers, TLS, requests]
    E --> H[Broker and controller capacity]
    F --> H
    G --> H
    H --> I[CPU, RAM, disk, network, operations]
~~~

Điểm quan trọng là các đại lượng có quan hệ với nhau nhưng không thay thế nhau. Giảm số topic không nhất thiết giảm partition count nếu giữ nguyên tổng số partition. Giảm connection không tự giảm replica bytes. Giảm partition có thể làm giảm metadata và file overhead nhưng cũng giảm parallelism.

## 3. Chi phí của nhiều topic nhỏ

Topic là đơn vị đặt tên, cấu hình và quản trị luồng dữ liệu. Một topic có thể chỉ chứa ít record mỗi ngày nhưng vẫn cần được quản lý trong cluster metadata.

### 3.1. Metadata và cấu hình

Mỗi topic có metadata như:

- Tên topic và topic ID.
- Số partition.
- Replica assignment cho từng partition.
- Topic-level configuration.
- Trạng thái partition leader và ISR.
- ACL hoặc policy liên quan.
- Thông tin được các client lấy qua metadata request.

Nhiều topic làm tăng số lượng resource cần controller quản lý và client cần khám phá. Việc tạo/xóa topic, thay config, kiểm tra ACL và giám sát cũng trở nên phức tạp hơn.

Topic nhỏ không đồng nghĩa chi phí bằng không. Ngay cả khi không có record mới, topic vẫn tồn tại trong metadata và có thể có partition replica, log directory và metric series.

### 3.2. Topic nhỏ và partition tối thiểu

Mỗi topic phải có ít nhất một partition. Vì vậy, nếu tạo 5.000 topic, mỗi topic một partition và RF=3, cluster có 5.000 partition logic và 15.000 replica placement.

Một thiết kế khác có 500 topic, mỗi topic 10 partition, RF=3 cũng có 5.000 partition logic và 15.000 replica placement. Hai thiết kế có số replica bằng nhau nhưng thiết kế 5.000 topic tạo nhiều topic metadata, config object, ACL target và thao tác quản trị hơn.

| Thiết kế | Topic | Partition/topic | Tổng partition | RF | Replica placement |
|---|---:|---:|---:|---:|---:|
| A: rất nhiều topic nhỏ | 5.000 | 1 | 5.000 | 3 | 15.000 |
| B: ít topic hơn | 500 | 10 | 5.000 | 3 | 15.000 |

Đây là ví dụ so sánh overhead, không phải khuyến nghị gom tất cả topic vào một topic. Hai luồng chỉ nên dùng chung topic nếu retention, cleanup policy, schema, security, ownership và lifecycle tương thích.

### 3.3. Chi phí vận hành topic

Nhiều topic nhỏ làm tăng số việc mà đội vận hành phải quản lý:

- Provisioning, naming convention và ownership.
- ACL và service account mapping.
- Retention, cleanup policy và quota.
- Dashboard, alert và log search.
- Backup, migration và decommission.
- Topic creation/deletion audit.
- Consumer subscription và schema compatibility.
- Quy trình xử lý topic không còn owner.

Một hệ thống có hàng nghìn topic được tạo tự động theo tenant hoặc request có thể khiến việc kiểm soát vòng đời trở nên khó khăn. Topic không còn sử dụng vẫn chiếm metadata và có thể còn replica/log file cho đến khi được xóa theo quy trình.

### 3.4. Khi nào topic riêng là hợp lý?

Topic riêng có ích khi cần một hoặc nhiều điều kiện sau:

- Retention hoặc cleanup policy khác biệt đáng kể.
- Security boundary và ACL cần tách biệt.
- Schema/event contract có lifecycle riêng.
- Consumer ownership và quota khác nhau.
- Cần xóa hoặc archive dữ liệu theo một domain độc lập.
- Throughput hoặc priority cần cô lập.

Nếu các tenant có cùng schema, retention, security và lifecycle, shared topic với key chứa tenant identifier có thể giảm topic count. Tuy nhiên, phải đánh giá partitioning, noisy-neighbor, data isolation và quyền truy cập ở tầng ứng dụng.

Không gom các topic có yêu cầu bảo mật hoặc retention khác nhau chỉ để giảm số lượng topic.

## 4. Chi phí của nhiều partition

Partition là đơn vị song song hóa và lưu trữ log. Khi partition count tăng, Kafka có thêm khả năng phân phối tải, nhưng mỗi partition cũng tạo một lượng trạng thái và công việc cố định.

### 4.1. Replica count tăng theo partition

Nếu có P partition và replication factor RF:

\[
R_{total} = P \times RF
\]

Nếu cluster có B broker, số replica trung bình trên một broker xấp xỉ:

\[
R_{broker,avg} = \frac{P \times RF}{B}
\]

Ví dụ:

- 2.400 partition.
- RF=3.
- 12 broker.

Tổng replica placement là 7.200, trung bình khoảng 600 replica trên mỗi broker. Phân bố thực tế có thể lệch do partition size, rack awareness, leader placement và assignment.

Khi partition count tăng gấp đôi mà RF và broker count giữ nguyên, tổng replica placement cũng tăng gấp đôi. Điều đó làm tăng metadata, log/index state, replication work và số đối tượng cần phục hồi.

### 4.2. Log segment và index

Mỗi partition có log directory riêng trên broker đang giữ replica. Log được chia thành segment; segment đi kèm index phục vụ tìm kiếm offset và timestamp.

Số file không đơn giản bằng số partition vì còn phụ thuộc segment.bytes, retention, compaction, active segment và cách Kafka mở file. Tuy vậy, nhiều partition thường làm tăng:

- Số log directory.
- Số active segment.
- Offset/time index file.
- File descriptor và file metadata.
- Công việc segment rolling và deletion.
- Filesystem inode usage.
- Công việc log cleaner đối với compacted topic.

Các file và index cần được tính vào filesystem capacity. Không chỉ đo payload bytes.

### 4.3. RAM, page cache và heap

Partition metadata và trạng thái replication tiêu thụ bộ nhớ. Kafka còn dựa nhiều vào OS page cache để phục vụ đọc log; vì vậy không nên xem toàn bộ RAM trống là heap JVM.

Khi partition tăng:

- Broker giữ thêm metadata và replica state.
- Controller phải quản lý thêm partition/replica metadata.
- Replica fetcher và request processing có thêm work.
- Nhiều log/index file làm tăng hoạt động filesystem.
- Page cache bị phân tán trên nhiều log segment.
- Heap pressure hoặc GC có thể tăng nếu metadata/state lớn so với cấu hình.

Không có một số byte cố định cho mỗi partition áp dụng cho mọi phiên bản, workload và cấu hình. Hãy đo heap, page cache, GC, partition count và controller metadata trên cluster thực tế.

### 4.4. Leader, ISR và recovery

Mỗi partition có leader và tập ISR. Nhiều partition làm tăng số leader/follower relationship mà broker phải quản lý.

Khi broker restart hoặc failure:

- Partition leader có thể cần election.
- Follower replica cần catch up.
- Controller xử lý metadata thay đổi.
- Client nhận metadata update và có thể retry.
- Partition có thể tạm thời under-replicated.
- Reassignment hoặc recovery phải xử lý nhiều replica hơn.

Số partition quá lớn có thể kéo dài thời gian recovery và làm tăng áp lực lên controller, broker và client trong các tình huống sự cố.

### 4.5. Consumer group và rebalance

Consumer group chia partition cho các consumer member. Trong một group, một partition tại một thời điểm chỉ được assign cho một consumer member.

Nếu group có 24 partition và 40 consumer instance, tối đa 24 instance có thể nhận partition; phần còn lại không xử lý partition nhưng vẫn có thể tham gia group, heartbeat và tạo connection.

Nhiều partition cũng làm assignment/rebalance phức tạp hơn. Khi consumer member thay đổi, group coordinator và các consumer phải xử lý nhiều assignment hơn.

### 4.6. Producer batching và compression

Producer gom record thành batch theo topic-partition. Khi có quá nhiều partition với lưu lượng nhỏ, record bị phân tán trên nhiều batch.

Hệ quả có thể gồm:

- Batch nhỏ hơn và compression kém hiệu quả.
- Nhiều request nhỏ.
- Buffer memory bị phân mảnh theo partition.
- Thêm overhead metadata và callback.
- Throughput thấp hơn dù tổng byte rate không đổi.

Không phải cứ tăng partition là throughput tăng tuyến tính. Partition count phải đủ cho parallelism nhưng không quá nhiều so với volume và batch behavior.

## 5. Chi phí của nhiều connection

Một Kafka client process không nhất thiết chỉ có một TCP connection. Producer và consumer có thể mở connection đến nhiều broker tùy partition leader, fetch assignment, metadata và hoạt động quản trị.

Ngược lại, không được mặc định mọi client luôn kết nối đến mọi broker. Số socket thực tế phụ thuộc cách partition được phân bố, client activity, connection idle timeout và phiên bản client.

### 5.1. Tài nguyên cho mỗi connection

Mỗi connection có thể tiêu thụ:

- TCP socket và file descriptor.
- Kernel socket buffer.
- Kafka network connection state.
- Network processor work.
- TLS session và encryption/decryption CPU nếu dùng TLS.
- SASL authentication state và handshake khi kết nối.
- Request/response buffer khi có traffic.
- Heartbeat hoặc metadata traffic tùy client.
- Monitoring state và connection metric.

Một connection idle vẫn giữ socket và một phần state. Một connection liên tục tạo/hủy có thể gây TLS handshake, authentication và CPU churn.

### 5.2. Client count không bằng connection count

Ước lượng connection theo broker nên dùng số đo thực tế:

\[
C_b = \sum_{i=1}^{N} c_{i,b}
\]

Trong đó:

- \(N\) là số client instance.
- \(c_{i,b}\) là số connection mà client i đang mở tới broker b.
- \(C_b\) là tổng connection tại broker b.

Không dùng công thức N client × B broker như một sự thật mặc định. Đó chỉ có thể là một upper-bound thô trong trường hợp mỗi client thực sự mở kết nối tới tất cả broker.

Ví dụ minh họa: 400 client instance có trung bình 3 connection tới một broker thì broker đó có khoảng 1.200 socket từ nhóm client này. Broker khác có thể có số khác tùy leader placement và fetch pattern.

### 5.3. Connection churn

Connection churn là tốc độ tạo và đóng connection. Nó khác với số connection đồng thời.

Hai hệ thống có cùng 1.000 socket đang mở nhưng một hệ thống tạo/hủy vài connection mỗi phút, hệ thống kia tạo/hủy hàng nghìn connection mỗi phút sẽ có chi phí TLS/SASL và CPU rất khác nhau.

Nguyên nhân thường gặp:

- Tạo KafkaProducer/KafkaConsumer mới cho mỗi request.
- Container autoscaling quá nhạy.
- Health check tạo client liên tục.
- Client restart loop do authentication hoặc DNS.
- Connection idle timeout quá thấp.
- Network proxy/load balancer đóng socket không phù hợp.
- Consumer group rebalance hoặc app deploy liên tục.

### 5.4. TLS và SASL

TLS và SASL tăng chi phí CPU và handshake, nhưng không nên tắt bảo mật để giảm connection cost. Cách đúng là giảm client churn, tái sử dụng client, cấu hình connection lifecycle phù hợp và theo dõi handshake failure.

Connection pool hoặc client reuse phải tuân theo thread-safety của API. KafkaProducer thread-safe và thường được dùng lâu dài; KafkaConsumer không thread-safe và cần được sở hữu bởi một thread theo đúng contract.

## 6. Consumer group làm tăng fetch traffic

Một consumer group là một đơn vị đọc độc lập. Nếu nhiều group cùng subscribe một topic, mỗi group sẽ đọc lại dữ liệu theo offset riêng.

Ví dụ topic orders có 10 MiB/s ingress và có 8 consumer group độc lập cùng đọc toàn bộ topic. Broker có thể phải phục vụ lượng fetch egress lớn hơn nhiều so với một group, gần với tổng nhu cầu của 8 nhóm trước khi tính cache, compression, filtering và traffic pattern thực tế.

Đây là chi phí khác với partition count:

- Thêm partition tăng replica và metadata.
- Thêm consumer group có thể tăng fetch traffic và group state.
- Thêm consumer instance trong cùng group có thể tăng connection/member count nhưng không tăng parallelism vượt partition count.

Trước khi tạo group mới, hãy xác định đó là một consumer độc lập thật sự hay chỉ là nhiều instance cần scale trong cùng group.

## 7. Công thức capacity cơ bản

Công thức chỉ là mô hình ước lượng. Sizing cuối cùng phải dựa trên benchmark với payload, compression, RF, retention, consumer group và network tương tự production.

### 7.1. Số partition theo throughput

Gọi:

- \(T\): throughput mục tiêu của topic, tính bằng MiB/s.
- \(t_p\): throughput an toàn đã benchmark cho một partition, tính bằng MiB/s.
- \(P_t\): partition count theo throughput.

\[
P_t = \left\lceil \frac{T}{t_p} \right\rceil
\]

Nếu một partition chịu được 4 MiB/s trong benchmark có headroom và topic cần 20 MiB/s, mô hình throughput cho ra ít nhất 5 partition. Con số 4 MiB/s phải đến từ benchmark của workload thật, không phải một giới hạn chung của Kafka.

### 7.2. Partition theo parallelism

Nếu muốn tối đa Q consumer có thể xử lý đồng thời trong một group:

\[
P_q \ge Q
\]

Điều kiện này chỉ có ý nghĩa nếu mỗi partition có đủ work và key distribution không tạo skew. Nếu có 20 consumer nhưng chỉ 8 partition, tối đa 8 consumer có assignment trong group tại cùng thời điểm.

### 7.3. Chọn partition count cuối cùng

Một ước lượng ban đầu:

\[
P = \max(P_t, P_q)
\]

Sau đó kiểm tra ordering key, partition skew, storage per partition, broker capacity, controller overhead và recovery time. Không chọn partition count chỉ bằng một công thức.

### 7.4. Ước lượng storage

Giả sử:

- \(I_u\): ingress bytes/s trước compression.
- \(D\): retention duration theo giây.
- \(K\): compression ratio, bằng uncompressed bytes chia compressed bytes.
- \(RF\): replication factor.

Dung lượng dữ liệu replica gần đúng:

\[
S_{replica} \approx \frac{I_u \times D}{K} \times RF
\]

Ví dụ:

- Ingress chưa nén: 8 MiB/s.
- Retention: 3 ngày = 259.200 giây.
- Compression ratio đo được: 2,5.
- RF=3.

Dữ liệu chưa nén trong retention:

\[
8 \times 259.200 = 2.073.600\ MiB
\]

Dung lượng compressed cho một replica:

\[
2.073.600 / 2,5 = 829.440\ MiB
\]

Tổng dung lượng replica:

\[
829.440 \times 3 = 2.488.320\ MiB
\]

Tương đương khoảng 2.430 GiB trước index, segment, filesystem overhead và headroom. Nếu dự phòng 25% capacity cho vận hành, cần khoảng 3.038 GiB dung lượng provisioned theo mô hình đơn giản này; vẫn phải cộng hoặc xác minh overhead log/index và tính phân bố theo broker.

Nếu ingress rate đã đo sau compression thì không chia thêm cho K. Dùng đúng đơn vị và vị trí đo để tránh tính compression hai lần.

Đây là ước lượng dung lượng trung bình, chưa phản ánh thời điểm xóa segment. Retention theo thời gian thường xóa segment khi segment đủ điều kiện, nên dung lượng thực tế có thể vượt đường tính đơn giản trong một khoảng thời gian. Với topic compacted, dung lượng phụ thuộc số key còn sống, tốc độ cập nhật key, tombstone và cleaner; không nên áp dụng trực tiếp công thức retention dạng append-only mà không điều chỉnh mô hình.

### 7.5. Ước lượng replication traffic

Với leader nhận dữ liệu và follower replica fetch từ leader, lượng inter-broker replication traffic thường tăng theo RF-1, nhưng thực tế phụ thuộc leader placement, rack, compression, batching, fetch protocol và traffic locality.

Một mô hình thô:

\[
N_{replication} \approx I_c \times (RF - 1)
\]

Trong đó \(I_c\) là ingress bytes/s đã nén được leader nhận. Đây là ước lượng tổng byte follower cần nhận, không phải công thức chính xác cho từng NIC hoặc từng rack. Cần đo network ingress/egress trên từng broker.

### 7.6. Ước lượng replica trên broker

\[
R_{broker,avg} = \frac{P \times RF}{B}
\]

Dùng giá trị trung bình để kiểm tra quy mô, sau đó đánh giá phân bố thực tế theo dung lượng partition, leader bytes, rack và broker role.

## 8. Ví dụ sizing kết hợp topic, partition và connection

Giả sử một hệ thống event có:

- 600 domain/tenant.
- Mỗi domain phát khoảng 10 KiB/s.
- Tổng ingress xấp xỉ 6.000 KiB/s, khoảng 5,86 MiB/s.
- Retention 7 ngày.
- RF=3.
- 12 broker.
- 8 consumer group đọc cùng dữ liệu.
- Ban đầu mỗi tenant có một topic, mỗi topic một partition.

Thiết kế ban đầu có:

- 600 topic.
- 600 partition logic.
- 1.800 replica placement.
- Trung bình 150 replica placement trên mỗi broker nếu phân bố đều.

Nếu đổi thành 60 topic domain, mỗi topic 10 partition:

- 60 topic.
- 600 partition logic.
- 1.800 replica placement.
- Topic metadata giảm, nhưng partition overhead gần như giữ nguyên.

Nếu giảm tiếp xuống 60 topic × 4 partition:

- 240 partition logic.
- 720 replica placement.
- Ít replica hơn nhưng cần benchmark để bảo đảm throughput và consumer parallelism vẫn đủ.

Tuy nhiên, 8 consumer group độc lập vẫn có thể đọc cùng dữ liệu. Giảm partition không tự giảm số lần dữ liệu được fetch bởi các group. Cần xem xét liệu có thể hợp nhất consumer workload hoặc dùng một downstream fan-out phù hợp không.

Kết nối cũng cần được đo riêng. Nếu 300 consumer instance có trung bình 4 socket tới một broker cụ thể, broker đó có khoảng 1.200 connection từ nhóm này. Broker khác có thể có số khác. Đừng suy ra socket count chỉ từ số process hoặc số partition.

## 9. Thiết kế topic để tránh proliferation

### 9.1. Dùng topic theo domain hoặc event stream

Một topic có thể chứa nhiều event của cùng domain nếu chúng có:

- Security classification tương thích.
- Retention và cleanup policy tương thích.
- Schema evolution được quản lý.
- Consumer ownership rõ ràng.
- Partitioning strategy chung.
- Lifecycle và operational SLA tương thích.

Ví dụ có thể dùng topic orders-events với event type trong envelope/header thay vì tạo một topic cho mỗi event type nếu không cần policy riêng.

### 9.2. Khi nào không nên gom?

Không gom nếu:

- Một tenant cần retention khác theo hợp đồng.
- Một nhóm dữ liệu có quyền truy cập tách biệt nghiêm ngặt.
- Có yêu cầu xóa hoặc lưu trữ riêng.
- Một event stream có throughput cực lớn và cần cô lập.
- Consumer contract hoặc schema lifecycle khác nhau đáng kể.
- Topic cần quota hoặc priority độc lập.

### 9.3. Topic per tenant

Topic per tenant có thể phù hợp khi cần isolation mạnh, retention riêng hoặc lifecycle riêng. Nhưng hàng nghìn tenant sẽ làm tăng topic metadata, ACL, dashboards, provisioning và thao tác vận hành.

Nếu chọn topic per tenant:

- Tự động hóa create/delete và ownership.
- Có quota và giới hạn số topic.
- Có lifecycle cleanup cho tenant ngừng hoạt động.
- Đặt naming convention.
- Theo dõi topic không có producer/consumer.
- Tính partition × RF trên toàn cluster, không chỉ topic count.

## 10. Thiết kế partition count hợp lý

### 10.1. Đừng cấp partition theo số tenant một cách máy móc

Nếu 1.000 tenant đều có lưu lượng nhỏ, tạo một partition cho mỗi tenant có thể gây nhiều overhead. Shared topic có thể dùng tenantId làm một phần key để phân phối, nếu yêu cầu ordering và isolation cho phép.

### 10.2. Ordering và key distribution

Kafka chỉ đảm bảo thứ tự trong một partition. Chọn key theo entity cần ordering, ví dụ orderId hoặc accountId.

Nếu một key quá nóng, một partition có thể chịu phần lớn traffic dù tổng partition count cao. Tăng partition count không giải quyết được hot key nếu tất cả record vẫn có cùng key.

### 10.3. Consumer parallelism

Partition count quyết định mức parallelism tối đa của một consumer group. Nhưng số consumer không cần phải bằng partition count trong mọi trường hợp.

Một cách triển khai hợp lý là bắt đầu với số consumer vừa đủ xử lý throughput, sau đó scale theo lag và processing capacity. Không tạo hàng chục consumer idle chỉ để “sẵn sàng” nếu chi phí group membership và connection đáng kể.

### 10.4. Không thể giảm partition count trực tiếp

Kafka không hỗ trợ giảm số partition của một topic hiện có theo thao tác thông thường. Nếu đã tạo quá nhiều partition, phương án thường là tạo topic mới với partition count phù hợp, chuyển dữ liệu/producer/consumer theo cutover plan và xử lý offset migration.

Cutover cần đánh giá ordering, duplicate, consumer offset, retention và khả năng replay. Không xóa topic cũ ngay khi producer đã đổi đích; giữ lại trong thời gian quan sát và theo chính sách dữ liệu.

## 11. Giảm connection bằng quản lý client

### 11.1. Tái sử dụng producer

KafkaProducer thread-safe. Tạo một producer dùng lâu dài cho application hoặc dùng producer factory của Spring Kafka. Không tạo producer mới cho mỗi HTTP request hoặc mỗi event.

Ví dụ cấu hình Spring:

~~~java
import org.springframework.boot.autoconfigure.kafka.KafkaProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
public class KafkaProducerConfiguration {

    @Bean
    public ProducerFactory<String, String> producerFactory(
            KafkaProperties kafkaProperties) {
        return new DefaultKafkaProducerFactory<>(
            kafkaProperties.buildProducerProperties()
        );
    }

    @Bean
    public KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
~~~

Đây là ví dụ khung; cấu hình security, serializer, transaction và version API cần khớp Spring Boot của ứng dụng.

### 11.2. Quản lý consumer đúng cách

KafkaConsumer không thread-safe. Không chia sẻ một consumer tùy tiện giữa nhiều thread. Dùng một consumer cho một thread xử lý poll hoặc dùng listener container của Spring Kafka để quản lý lifecycle.

Tránh tạo consumer instance nhiều hơn mức cần thiết. Nếu consumer instance vượt partition count trong một group, các instance dư không tăng khả năng xử lý nhưng vẫn tạo member/connection overhead.

### 11.3. Spring Kafka concurrency

Listener container concurrency tạo consumer instance tương ứng theo cấu hình. Chọn concurrency theo partition count, processing time, downstream capacity và lag. Không đặt concurrency cao hơn partition count mà không có lý do riêng.

### 11.4. Kafka Streams và Connect

Kafka Streams threads/tasks và Connect tasks cũng là client workload. Tăng số thread/task có thể tăng connection, fetch request, producer request và internal topic traffic.

Tính cả chúng vào client inventory. Không chỉ đếm service producer/consumer nghiệp vụ.

### 11.5. Connection idle timeout

Broker/client có các cấu hình quản lý connection idle. Điều chỉnh timeout có thể giải phóng socket không hoạt động, nhưng timeout quá thấp có thể làm tăng connection churn và TLS handshake.

Chỉ thay đổi sau khi đo:
- Số connection idle.
- Connection creation/close rate.
- Authentication/handshake CPU.
- Network proxy idle timeout.
- Client reconnect behavior.

Không dùng timeout thấp để che vấn đề tạo quá nhiều client process.

## 12. Các metric cần theo dõi

| Nhóm | Metric hoặc tín hiệu | Dùng để phát hiện |
|---|---|---|
| Topic | Topic count, topic creation/deletion rate | Topic proliferation |
| Partition | Partition count, partition count per broker | Partition overhead và imbalance |
| Replica | Replica count, UnderReplicatedPartitions | Replication health |
| Leader | Leader count/bytes per broker | Leader skew |
| Storage | Log bytes, disk utilization, inode, file descriptor | Disk/file overhead |
| JVM | Heap used, GC pause, allocation rate | Metadata/state pressure |
| Controller | Metadata operation latency, quorum health | Control-plane pressure |
| Connection | Active connection count per broker/listener | Socket overhead |
| Connection churn | Connection creation/close rate | Client lifecycle problem |
| Network | Bytes in/out, packet drop, retransmission | Network saturation |
| Request | Request queue time, handler idle percent | Request processing pressure |
| Consumer | Group count, member count, rebalance rate, lag | Group and consumer overhead |
| Producer | Batch size, compression rate, request rate | Small batch and request overhead |
| Monitoring | Metric series/cardinality, log ingestion rate | Observability cost |

Metric name cụ thể phụ thuộc Kafka version, JMX exporter và monitoring stack. Chuẩn hóa dashboard theo exporter thực tế và phân biệt metric broker-wide với metric theo topic/client.

### 12.1. Dashboard theo broker

Nên có bảng so sánh broker:

- Active connections.
- Connection creation rate.
- Bytes in/out.
- CPU và request handler idle.
- Network processor idle.
- Disk used/latency.
- Partition/replica/leader count.
- Under-replicated partitions.
- JVM heap và GC.
- Request p95/p99.

### 12.2. Dashboard theo topic

Theo dõi:

- Topic count.
- Partition count.
- RF.
- Bytes in/out.
- Message rate.
- Consumer group count.
- Retention và cleanup policy.
- Partition size skew.
- Topic không có traffic trong khoảng thời gian dài.

Topic không có traffic chưa chắc là topic bỏ đi; có thể là event stream theo mùa hoặc chỉ phát khi có nghiệp vụ. Cần owner xác nhận trước khi xóa.

## 13. Quy trình giảm chi phí có kiểm soát

Không xóa topic hoặc giảm concurrency chỉ dựa trên một snapshot metrics. Thực hiện theo thứ tự:

1. Inventory topic, partition, group, client và owner.
2. Đo traffic theo ngày/tuần và nhận diện seasonal workload.
3. Phân loại topic theo retention, security, schema và lifecycle.
4. Xác định topic không dùng hoặc có thể hợp nhất.
5. Xác định partition dư so với throughput và parallelism.
6. Đo connection count và connection churn theo broker.
7. Đề xuất thay đổi nhỏ, có owner và rollback plan.
8. Thử trên staging hoặc workload canary.
9. Theo dõi throughput, p95/p99, lag, ISR và error rate.
10. Chỉ áp dụng rộng sau khi kết quả đạt SLO.
11. Cập nhật quota, dashboard, alert và runbook.

### 13.1. Hợp nhất topic

Nếu hợp nhất topic:

- Định nghĩa event envelope có eventType và schema version.
- Chọn key hỗ trợ ordering.
- Xác định retention chung.
- Thiết kế ACL và data isolation.
- Cập nhật consumer subscription.
- Xử lý migration và replay.
- Theo dõi noisy tenant hoặc hot key.

### 13.2. Giảm partition qua topic mới

Nếu topic cũ có quá nhiều partition:

1. Chọn partition count mới từ benchmark và parallelism.
2. Tạo topic mới với RF, retention và security đúng.
3. Chọn cutover strategy: dual-write, mirror/replay hoặc pause-and-switch.
4. Bảo đảm eventId/idempotency khi có dual-write.
5. Xác định mapping key/partition và ordering.
6. Migrate consumer offset hoặc xử lý replay theo business checkpoint.
7. So sánh output và lag.
8. Chuyển producer/consumer.
9. Giữ topic cũ theo thời gian rollback.
10. Xóa topic cũ chỉ sau approval và retention review.

### 13.3. Giảm connection

- Tái sử dụng KafkaProducer.
- Dùng singleton KafkaTemplate/ProducerFactory theo Spring lifecycle.
- Giảm consumer instance idle.
- Hợp nhất consumer group chỉ khi semantics cho phép.
- Tránh health check tạo Kafka client mới liên tục.
- Ổn định autoscaling để tránh churn.
- Điều chỉnh idle timeout sau khi đo.
- Dùng quota và network policy phù hợp để kiểm soát workload.

## 14. Anti-pattern thường gặp

| Anti-pattern | Hệ quả | Hướng sửa |
|---|---|---|
| Một topic cho mỗi request | Topic metadata tăng liên tục | Dùng domain topic và event ID |
| Một topic cho mỗi event type dù policy giống nhau | Quá nhiều resource quản trị | Xem xét event envelope và shared topic |
| Một partition cho mỗi tenant nhỏ | Partition/replica overhead cao | Chia sẻ topic và partition theo key nếu phù hợp |
| Tăng partition để chữa hot key | Hot key vẫn dồn vào một partition | Sửa key distribution hoặc xử lý hot entity |
| Tạo producer cho mỗi request | Connection churn và handshake | Reuse producer |
| Tạo consumer cho mỗi task nhỏ | Group/member/connection overhead | Dùng listener container hoặc worker lifecycle dài |
| Consumer instance nhiều hơn partition | Instance idle, không tăng parallelism | Sizing concurrency theo partition và throughput |
| Nhiều group đọc cùng topic không có mục đích | Fetch egress tăng | Review downstream fan-out |
| Hạ TLS để giảm CPU | Mất bảo mật | Tối ưu client reuse, hardware và TLS config |
| Đặt retention cực dài cho topic nhỏ không còn owner | Disk và metadata lifecycle kéo dài | Owner review và retention policy |
| Xóa topic ngay khi không thấy traffic | Mất dữ liệu hoặc phá consumer chậm | Xác minh owner, replay và retention trước |
| Chọn partition count theo con số truyền miệng | Không phù hợp broker/workload | Benchmark và theo dõi recovery |

## 15. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Controller metadata tăng nhanh | Topic/partition tạo liên tục | Kiểm tra topic provisioning và partition count |
| Broker heap/GC tăng khi traffic thấp | Quá nhiều partition/metadata hoặc client state | Đo heap, GC, partition/replica count |
| Disk inode hoặc file descriptor cao | Nhiều log/index/segment hoặc connection | Phân tích theo log directory và process |
| Broker có nhiều socket idle | Nhiều client hoặc idle lifecycle không phù hợp | Inventory client và đo connection per broker |
| Connection churn cao | Client tạo lại liên tục hoặc timeout quá thấp | Reuse client và xem reconnect reason |
| TLS CPU tăng | Nhiều handshake hoặc traffic mã hóa cao | Giảm churn, kiểm tra session reuse và CPU headroom |
| Request queue tăng | Connection/request burst hoặc broker saturation | Đo network processor và request handler |
| Producer batch nhỏ | Nhiều partition ít traffic | Xem batch size, linger và partition design |
| Compression ratio giảm | Batch bị phân tán hoặc payload khó nén | Đo theo topic/partition và codec |
| Consumer group rebalance thường xuyên | Nhiều member hoặc instance restart | Ổn định lifecycle và kiểm tra group protocol |
| Consumer lag cao dù nhiều consumer | Partition ít hơn consumer hoặc downstream chậm | Kiểm tra assignment và processing time |
| Một broker quá tải | Replica/leader/connection skew | Xem partition placement và leader bytes |
| Topic không traffic nhưng vẫn tốn tài nguyên | Topic còn metadata, replica và retention | Xác minh owner và lifecycle |
| Hợp nhất topic gây noisy neighbor | Workload khác nhau chia sẻ cùng resource | Tách lại theo SLA hoặc quota phù hợp |

## 16. Checklist production

Trước khi tạo topic:

1. Có owner và business purpose không?
2. Topic có cần retention, security hoặc lifecycle riêng không?
3. Có thể dùng shared topic mà vẫn giữ isolation không?
4. Partition count dựa trên throughput và parallelism benchmark chưa?
5. RF và min ISR phù hợp durability chưa?
6. Có quota và naming convention không?
7. Topic có được tự động provision và decommission không?

Trước khi tăng partition:

8. Bottleneck thực sự là partition throughput hay client/downstream?
9. Key distribution có hot key không?
10. Consumer group có cần parallelism cao hơn không?
11. Replica count và recovery time sẽ tăng bao nhiêu?
12. Broker/controller còn headroom không?
13. Đã đánh giá ordering và key remapping chưa?
14. Có kế hoạch migration nếu phải giảm partition về sau không?

Trước khi tăng client/connection:

15. Client instance có được reuse đúng cách không?
16. Consumer instance có vượt partition count không?
17. Có group độc lập trùng chức năng không?
18. Connection count và churn theo broker đã được đo chưa?
19. TLS/SASL handshake có gây CPU pressure không?
20. Timeout có làm tăng reconnect churn không?
21. File descriptor và socket buffer còn headroom không?

Sau thay đổi:

22. Topic/partition/replica count có đúng mục tiêu không?
23. Connection count và churn có giảm không?
24. Throughput và p95/p99 có đạt SLO không?
25. Consumer lag, ISR và under-replicated partition ổn định không?
26. Disk, heap, GC, network và request queue có headroom không?
27. Dashboard, quota, owner và runbook đã cập nhật chưa?

## 17. Bài tập thực hành

### Bài 1: So sánh topic proliferation

1. Thiết kế A gồm 1.000 topic, mỗi topic 1 partition, RF=3.
2. Thiết kế B gồm 100 topic, mỗi topic 10 partition, RF=3.
3. Tính tổng partition và replica placement.
4. Liệt kê overhead khác nhau ngoài replica count.
5. Nêu điều kiện dữ liệu có thể hợp nhất vào shared topic.
6. Đề xuất naming, ACL và retention policy.

### Bài 2: Tính partition count theo benchmark

1. Tạo topic lab với nhiều partition.
2. Đo throughput an toàn trên một partition.
3. Đặt throughput mục tiêu.
4. Tính partition count theo throughput.
5. Đặt consumer parallelism mục tiêu.
6. Chọn partition count cuối cùng.
7. Kiểm tra hot key và phân bố tải.

### Bài 3: Ước lượng storage và replication

1. Đo ingress bytes/s trước compression.
2. Đo compression ratio thực tế.
3. Chọn retention duration và RF.
4. Tính compressed replica storage.
5. Cộng headroom và index/segment allowance.
6. Phân bố dung lượng lên broker.
7. So sánh với disk capacity và failure headroom.

### Bài 4: Đo connection overhead

1. Chạy một producer và một consumer lâu dài.
2. Ghi connection count theo broker.
3. Tạo nhiều client instance trong lab.
4. Quan sát socket, file descriptor, TLS handshake và CPU.
5. Tạo client liên tục để mô phỏng connection churn.
6. So sánh với mô hình reuse client.
7. Kiểm tra tác động của idle timeout.

### Bài 5: Đánh giá consumer group

1. Tạo topic có 12 partition.
2. Chạy một consumer group với 6 member.
3. Tăng lên 18 member.
4. Quan sát assignment, idle member, connection và rebalance.
5. Tạo thêm group độc lập đọc cùng topic.
6. Đo broker egress và consumer lag.
7. Đề xuất số group/member phù hợp.

### Bài 6: Giảm chi phí qua migration

1. Chọn topic lab có partition count dư.
2. Thiết kế topic mới với partition count thấp hơn.
3. Xác định cutover và replay strategy.
4. Giữ eventId để chống duplicate.
5. Chuyển producer/consumer trong lab.
6. So sánh throughput, latency và connection.
7. Xóa topic cũ sau khi xác minh dữ liệu và offset.

## 18. Câu hỏi tự kiểm tra

1. Topic overhead khác partition overhead như thế nào?
2. Vì sao topic không có traffic vẫn có thể tiêu thụ tài nguyên?
3. Hai thiết kế 5.000 topic × 1 partition và 500 topic × 10 partition có cùng replica placement khi RF=3 không?
4. Tổng replica count được tính như thế nào?
5. Vì sao số file log không đơn giản bằng số partition?
6. Partition tăng ảnh hưởng RAM, page cache và controller ra sao?
7. Vì sao nhiều partition có thể kéo dài recovery và rebalance?
8. Vì sao nhiều partition ít traffic có thể làm batch nhỏ và compression kém?
9. Consumer instance vượt partition count gây ra vấn đề gì?
10. Consumer group mới có thể làm tăng broker egress ra sao?
11. Client count có bằng connection count không?
12. Vì sao không giả định mỗi client kết nối mọi broker?
13. Connection churn khác active connection count như thế nào?
14. Vì sao không nên tạo KafkaProducer cho mỗi request?
15. KafkaProducer và KafkaConsumer khác nhau về thread-safety thế nào?
16. Công thức partition count theo throughput cần dữ liệu benchmark nào?
17. Khi tính storage, vì sao phải xác định ingress rate trước hay sau compression?
18. Replication traffic thay đổi theo RF ra sao?
19. Khi nào nên dùng topic riêng cho tenant?
20. Vì sao Kafka không thể giảm partition count trực tiếp trong thao tác thông thường?
21. Metric nào giúp phát hiện topic/partition/connection overhead?
22. Vì sao không nên tắt TLS để giảm chi phí connection?
23. Khi nào nên hợp nhất consumer group?
24. Những bước nào cần có trước khi xóa topic không còn traffic?

## Kết luận

Topic, partition và connection tạo ra ba loại overhead khác nhau. Nhiều topic làm tăng metadata, config, ACL và công việc quản trị. Nhiều partition làm tăng replica placement, log/index, file descriptor, leader/ISR state, recovery và rebalance work. Nhiều connection làm tăng socket, buffer, TLS/SASL processing, request handling và connection churn. Consumer group độc lập còn có thể nhân lượng fetch traffic từ cùng một topic.

Capacity planning cần kết hợp throughput benchmark, consumer parallelism, RF, retention, compression, broker count, rack placement và connection measurements. Không có một ngưỡng topic/partition/connection cố định phù hợp mọi cluster. Hãy đo trên workload thật, dùng công thức để ước lượng ban đầu, sau đó kiểm chứng bằng metrics và failure/recovery test.

Giảm chi phí bằng cách thiết kế topic theo domain và policy, chọn partition theo throughput/ordering, tái sử dụng Kafka client, tránh consumer instance dư thừa và quản lý lifecycle rõ ràng. Mọi thay đổi cần có migration, rollback và kiểm tra SLO để tiết kiệm tài nguyên mà không đánh đổi durability hoặc isolation.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Topic overhead | Chi phí metadata, config, ACL và quản trị theo số topic. |
| Partition overhead | Chi phí log/index, replica state, leader/ISR và recovery theo partition. |
| Connection overhead | Chi phí socket, file descriptor, buffer, TLS/SASL và request processing. |
| Replica placement | Số bản sao partition được đặt trên các broker. |
| Consumer group | Nhóm consumer cùng chia partition assignment và offset namespace. |
| Connection churn | Tốc độ tạo và đóng connection trong một khoảng thời gian. |
| Client reuse | Tái sử dụng client lâu dài thay vì tạo mới liên tục. |
| Compression ratio | Tỷ lệ dữ liệu chưa nén so với dữ liệu sau nén. |
| Headroom | Capacity dự phòng cho tăng trưởng, reassignment và failure recovery. |
| Hot key | Key có lưu lượng cao làm một partition chịu tải lệch. |
| Rack awareness | Phân phối replica qua các fault domain. |
| Rebalance | Quá trình phân phối lại partition giữa consumer group members. |
| File descriptor | Handle hệ điều hành dùng để truy cập socket, file và resource. |
| Page cache | Cache của hệ điều hành dùng để tăng tốc truy cập file log. |
| Throughput benchmark | Đo lưu lượng xử lý dưới workload và cấu hình xác định. |
| Noisy neighbor | Workload dùng chung resource gây ảnh hưởng workload khác. |
| Topic proliferation | Tăng topic count không kiểm soát theo tenant, request hoặc event type. |
| Retention | Thời gian hoặc dung lượng dữ liệu Kafka giữ lại trước khi xóa theo policy. |
| Consumer lag | Khoảng cách giữa vị trí record mới nhất và vị trí consumer đã xử lý/commit. |

