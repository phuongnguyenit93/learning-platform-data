# Tác động của đĩa, page cache, RAM, CPU và mạng

Hiệu năng Kafka phụ thuộc vào toàn bộ đường đi của record: producer tạo batch và gửi qua mạng, broker leader nhận và append vào log, follower replica sao chép dữ liệu, sau đó consumer fetch và xử lý. Một cluster có CPU mạnh vẫn có thể chậm vì disk latency; SSD nhanh vẫn không cứu được nếu network bão hòa hoặc broker thiếu RAM cho page cache.

Năm tài nguyên thường chi phối hiệu năng là:

- **Disk:** tốc độ append, flush, đọc segment và compaction.
- **Page cache và RAM:** giữ các segment nóng trong bộ nhớ, giảm số lần đọc disk.
- **CPU:** serialization, compression, TLS, request processing, replication, garbage collection và log compaction.
- **Network:** producer ingress, replication traffic, consumer egress, latency và packet loss.
- **Partition/task parallelism:** quyết định mức phân tán tải, số file/log và lượng metadata phải quản lý.

Không có một cấu hình phần cứng tối ưu cho mọi workload. Cần xác định bottleneck bằng metric, kiểm tra đường đi của request rồi thay đổi từng yếu tố có kiểm soát.

## 1. Theo dõi đường đi của một record

Giả sử producer gửi một batch tới topic có replication factor bằng 3:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant L as Leader broker
    participant F1 as Follower 1
    participant F2 as Follower 2
    participant C as Consumer

    P->>L: Produce batch qua network
    L->>L: Append vào log / page cache
    F1->>L: Fetch replica
    L-->>F1: Replication records
    F2->>L: Fetch replica
    L-->>F2: Replication records
    F1-->>L: Replica tiến tới high watermark
    F2-->>L: Replica tiến tới high watermark
    L-->>P: Produce response theo acks
    C->>L: Fetch records
    L-->>C: Trả batch cho consumer
~~~

Một produce request có thể chờ ở nhiều nơi:

1. Producer serialize record, gom batch và có thể nén dữ liệu.
2. Network truyền request tới broker leader.
3. Broker xử lý request, append record vào partition log.
4. Follower fetch dữ liệu từ leader và cập nhật replica.
5. Broker trả response theo cấu hình acknowledgement.
6. Consumer fetch dữ liệu và deserialize, xử lý record.

Nếu latency tăng, cần biết thời gian bị tiêu tốn ở producer, network, broker request queue, disk, replication hay consumer. Chỉ nhìn CPU tổng thể hoặc throughput tổng không đủ để xác định nguyên nhân.

### 1.1. acks=all không có nghĩa mỗi record đều fsync xuống đĩa vật lý

Với producer dùng `acks=all`, broker leader đợi các replica hiện thuộc ISR đáp ứng điều kiện acknowledgement trước khi trả thành công. Điều này tăng durability theo replication protocol.

Tuy nhiên, acknowledgement của Kafka không mặc định đồng nghĩa với việc mọi replica đã gọi fsync cho từng record và dữ liệu đã nằm bền vững trên platter/NAND. Kafka thường tận dụng filesystem page cache và flush nền. Độ bền thực tế còn phụ thuộc replication factor, ISR, broker failure model, filesystem và storage.

`min.insync.replicas` kết hợp với `acks=all` xác định mức ISR tối thiểu mà broker chấp nhận cho produce request. Nếu số ISR thấp hơn ngưỡng, request có thể thất bại thay vì ghi với durability thấp hơn yêu cầu.

## 2. Disk: Kafka ghi log tuần tự

Kafka lưu mỗi partition thành một log gồm nhiều segment. Producer append record vào cuối log; đây là mô hình ghi tuần tự, thường phù hợp với SSD/NVMe và filesystem hiện đại.

Các thao tác disk quan trọng:

- Append record vào log segment.
- Đọc record khi consumer fetch dữ liệu không còn trong page cache.
- Flush dữ liệu từ page cache xuống storage.
- Log compaction đọc và ghi lại segment.
- Xóa segment hết retention.
- Phục hồi replica hoặc state store tạo thêm hoạt động đọc/ghi.

### 2.1. Vì sao disk latency quan trọng?

Khi working set nằm trong page cache, broker có thể phục vụ nhiều fetch mà không cần đọc storage vật lý. Khi dữ liệu nóng không còn trong cache, consumer fetch phải chờ disk read.

Disk chậm hoặc có latency không ổn định có thể làm:

- Produce request xử lý lâu hơn khi append hoặc flush bị nghẽn.
- Consumer fetch latency tăng khi đọc segment từ storage.
- Log cleaner cạnh tranh I/O với traffic phục vụ.
- Replica catch-up chậm khi follower phải đọc/ghi nhiều dữ liệu.
- Request queue tăng do các request giữ request handler lâu hơn.

Đừng chỉ xem throughput tuần tự tối đa của nhà cung cấp. Kafka production cần cả latency, IOPS, throughput và độ ổn định khi có compaction, retention cleanup, recovery hoặc workload hỗn hợp.

### 2.2. SSD, NVMe và HDD

| Loại storage | Đặc điểm | Khi cân nhắc |
|---|---|---|
| HDD | Giá/GB thấp, random I/O và latency thường kém hơn | Workload ít nhạy latency, throughput tuần tự và capacity là ưu tiên |
| SATA SSD | Latency và random I/O tốt hơn HDD | Cluster vừa, workload phổ thông |
| NVMe SSD | IOPS cao, latency thấp và throughput tốt | Workload throughput/latency cao, nhiều partition và consumer fetch đồng thời |
| Network block storage | Dễ quản lý và mở rộng theo nền tảng | Cần kiểm tra latency, burst quota, IOPS và giới hạn throughput thực tế |

Chọn storage theo benchmark trên đúng workload. Một volume được quảng cáo có throughput cao có thể bị giới hạn bởi IOPS, queue depth, burst credit hoặc network của máy ảo.

### 2.3. Tách data directory và tránh tranh chấp I/O

Nếu broker có nhiều volume, có thể phân bổ partition log qua nhiều thư mục dữ liệu để tăng tổng năng lực I/O và dung lượng. Việc này cần phân bố partition hợp lý; nhiều mount point trên cùng một thiết bị vật lý không tạo thêm IOPS thực.

Cần kiểm tra:

- Các volume có thật sự nằm trên device/controller độc lập không.
- Storage có giới hạn throughput/IOPS theo instance hay theo volume không.
- Log cleaner có cạnh tranh với produce/fetch trên cùng thiết bị không.
- Disk gần đầy có làm tăng latency hoặc cản trở compaction/replica recovery không.
- Có đủ dung lượng trống cho segment rollover, reassignment và recovery không.

Không đặt Kafka data, OS logs, database khác và workload I/O nặng lên cùng một volume nếu chúng cạnh tranh tài nguyên và làm latency khó dự đoán.

### 2.4. Flush và durability

Kafka dùng page cache để ghi log hiệu quả. Broker thường flush dữ liệu theo chính sách của OS và các cấu hình flush của Kafka, thay vì fsync mỗi record.

Các cấu hình như `log.flush.interval.messages` và `log.flush.interval.ms` có thể ảnh hưởng flush policy ở broker/topic tùy phiên bản và cấu hình. Không giảm chúng một cách tùy tiện để cố đạt durability: flush quá thường xuyên có thể làm giảm throughput đáng kể, trong khi không thay thế được replication và backup.

Đối với phần lớn cluster, ưu tiên cấu hình replication/ISR đúng, storage ổn định và theo dõi flush/disk latency. Chỉ thay flush policy khi đã xác định yêu cầu durability cụ thể và đo được tác động.

## 3. Page cache: bộ nhớ đệm quan trọng của Kafka

Kafka tận dụng filesystem page cache của hệ điều hành. Khi broker append dữ liệu, dữ liệu thường đi qua page cache trước khi được flush xuống thiết bị lưu trữ. Khi consumer đọc lại dữ liệu vừa ghi, record có thể vẫn nằm trong RAM và được phục vụ nhanh.

~~~mermaid
flowchart TD
    P["Produce request"] --> K["Kafka broker"]
    K --> PC["OS page cache"]
    PC --> D["Disk / SSD"]
    C["Consumer fetch"] --> PC
    PC -->|Cache hit| C
    PC -->|Cache miss| D
    D --> PC
~~~

Page cache đặc biệt có lợi khi workload có locality: consumer thường đọc dữ liệu mới hoặc một tập segment được truy cập lặp lại.

### 3.1. Cache hit và cache miss

- **Cache hit:** dữ liệu cần đọc có trong page cache; disk không cần phục vụ read vật lý.
- **Cache miss:** dữ liệu không còn trong cache; OS phải đọc từ storage.
- **Cache churn:** working set lớn hoặc nhiều workload tranh RAM khiến page cache liên tục bị thay thế.

Nếu consumer đọc dữ liệu cũ, scan lịch sử hoặc nhiều topic có working set lớn, page cache hit ratio có thể giảm. Khi đó disk read throughput và latency trở nên quan trọng hơn.

### 3.2. Vì sao không nên dành toàn bộ RAM cho JVM heap?

RAM của broker được dùng cho nhiều mục đích:

- JVM heap: object, metadata, request state và application runtime.
- JVM non-heap/native memory: code cache, thread stack, direct buffers và thư viện native.
- OS page cache: cache log segment và index.
- Kernel/network buffers: socket buffer, filesystem metadata và kernel memory.
- Process khác: agent giám sát, exporter hoặc service chạy cùng host.

Nếu cấp heap quá lớn, hệ điều hành còn ít RAM cho page cache. Broker có thể ít garbage collection hơn nhưng consumer fetch lại đọc disk nhiều hơn.

Ngược lại, heap quá nhỏ làm tăng GC pressure, allocation failure hoặc OOM. Cần cân bằng heap với page cache, native memory và mức sử dụng thực tế.

### 3.3. Theo dõi page cache

Có thể quan sát:

- RAM available và cache/buffers của hệ điều hành.
- Major/minor page faults của broker process.
- Disk read IOPS và read latency.
- Consumer fetch latency.
- Tỷ lệ cache hit nếu nền tảng/storage agent cung cấp.
- Memory pressure và reclaim activity.

Trên Linux, các lệnh thường dùng:

~~~bash
free -h
vmstat 1
sar -B 1
iostat -xz 1
~~~

Tên field và cách tính cache có thể khác giữa kernel và công cụ. Không coi toàn bộ RAM được hệ điều hành hiển thị là used đều là memory leak; page cache có thể được thu hồi khi process cần memory.

## 4. RAM và JVM heap

Kafka broker chạy trên JVM, vì vậy RAM ảnh hưởng cả heap, GC lẫn cache của hệ điều hành.

### 4.1. Heap chứa gì?

Heap có thể chứa:

- Request/response object.
- Metadata và object liên quan tới topic/partition.
- Record batch đang xử lý.
- Buffer và object tạm.
- Connection/request state.
- Các cấu trúc quản lý broker và controller.

Kích thước heap phụ thuộc số partition, connection, request concurrency, kích thước batch, phiên bản Kafka và tải. Không nên lấy một con số heap cố định áp dụng cho mọi cluster.

### 4.2. Heap quá lớn và GC

Heap lớn có thể giảm tần suất allocation pressure trong một số workload, nhưng cũng có thể làm thời gian GC hoặc thời gian pause tăng nếu collector/cấu hình không phù hợp. Một stop-the-world pause có thể làm request xử lý chậm, heartbeat trễ hoặc client quan sát timeout/retry.

Theo dõi:

- Heap used sau GC và xu hướng tăng.
- Allocation rate.
- GC pause time và frequency.
- Old generation occupancy.
- Direct/native memory.
- Thread count và thread stack.
- OOM hoặc container memory limit.

Nếu heap liên tục tăng sau full GC, cần điều tra object retention/leak hoặc metadata growth. Nếu heap thấp nhưng host thiếu RAM, có thể native memory hoặc page cache đang chiếm phần lớn; phải kiểm tra cả process và hệ điều hành.

### 4.3. Container memory limit

Trong Kubernetes/container, giới hạn memory phải bao phủ heap và native/off-heap memory. JVM heap đặt sát memory limit có thể khiến container bị OOMKilled dù heap chưa đạt max.

Cần chừa khoảng trống cho:

- Direct byte buffers.
- Thread stacks.
- Metaspace và code cache.
- Native libraries.
- OS/container accounting.
- Monitoring agent.

Dùng container-aware JVM và kiểm tra memory limit thực tế. Không suy luận chỉ từ `-Xmx`.

## 5. CPU: serialization, compression, TLS và request processing

CPU broker và client được dùng cho nhiều công việc:

- Serialization/deserialization.
- Compression/decompression.
- Checksum và record batch validation.
- TLS encryption/decryption và SASL authentication.
- Produce/fetch request handling.
- Replication fetch và network processing.
- Log compaction và index maintenance.
- Garbage collection.
- Metrics, tracing và background tasks.

CPU saturation có thể làm request queue tăng dù disk và network vẫn còn năng lực.

### 5.1. Compression là trade-off giữa CPU và network/disk

Producer có thể nén record batch trước khi gửi. Batch đã nén thường được broker lưu dưới dạng nén và consumer giải nén khi đọc. Lợi ích là giảm byte truyền qua network và byte lưu trữ; chi phí là CPU ở producer/consumer và một phần xử lý broker.

| Codec | Đặc điểm tổng quát | Khi cân nhắc |
|---|---|---|
| `none` | Không tốn CPU nén, payload lớn hơn | Payload đã nén hoặc CPU rất hạn chế |
| `lz4` | Nén/giải nén nhanh, tỷ lệ nén vừa phải | Throughput cao, ưu tiên tốc độ |
| `snappy` | Nén nhanh, giảm dung lượng ở mức vừa | Workload cần codec đơn giản, cân bằng |
| `zstd` | Có thể nén tốt, có level điều chỉnh | Muốn tiết kiệm network/storage và có CPU phù hợp |
| `gzip` | Có thể nén tốt nhưng CPU thường cao hơn | Khi tỷ lệ nén quan trọng hơn CPU/latency |

Không có codec tốt nhất cho mọi payload. JSON lặp nhiều field thường nén tốt; dữ liệu đã nén như ảnh/video có thể giảm rất ít.

Đo đồng thời:

- Producer CPU và compression rate.
- BytesInPerSec và BytesOutPerSec.
- Disk write throughput.
- Consumer CPU và fetch/decompression latency.
- End-to-end p95/p99 latency.

### 5.2. TLS cũng dùng CPU

TLS tạo thêm chi phí handshake, mã hóa và giải mã record. Với kết nối lâu dài, chi phí handshake được phân bổ qua nhiều request; nếu client liên tục mở/đóng connection, chi phí tăng.

Cách giảm lãng phí:

- Dùng connection pool/lifecycle đúng cách, không tạo client cho từng message.
- Dùng certificate và cipher suite được hỗ trợ hiệu quả.
- Tránh cấu hình TLS cũ không cần thiết.
- Đo CPU trước và sau khi bật TLS trên workload tương đương.
- Theo dõi handshake rate, connection churn và request rate.

Không tắt TLS để xử lý CPU cao nếu đây là yêu cầu bảo mật. Hãy xác định CPU bị dùng bởi handshake, bulk encryption hay phần xử lý khác.

### 5.3. CPU broker và background work

Log compaction, reassignment, replica catch-up và request handling có thể tranh CPU. Khi chạy compaction nặng cùng lúc với produce/fetch peak, latency có thể tăng.

Theo dõi CPU theo process và core, không chỉ phần trăm trung bình toàn host. Một số thread hoặc network processor có thể bão hòa trong khi tổng CPU vẫn thấp.

Trên Linux:

~~~bash
top -H -p <broker-pid>
pidstat -u -r -d -p <broker-pid> 1
mpstat -P ALL 1
~~~

Nếu một core luôn bão hòa, kiểm tra thread nóng, request type, partition/leader skew và interrupt distribution trước khi tăng số core.

## 6. Network: ingress, replication và consumer egress

Kafka là hệ thống phân tán nên network ảnh hưởng cả throughput lẫn latency.

Mỗi record có thể đi qua nhiều luồng:

1. Producer gửi record tới leader.
2. Leader truyền dữ liệu tới follower qua replication fetch.
3. Consumer fetch record từ broker.
4. Kafka Connect, MirrorMaker hoặc cluster khác có thể sao chép record tiếp.

Với replication factor 3, một record thường cần được truyền từ leader sang hai follower ngoài lần truyền producer tới leader. Consumer egress và các luồng mirror còn tạo thêm traffic.

### 6.1. Ước lượng network traffic

Giả sử ingress sau nén là 100 MB/s, replication factor là 3 và có một consumer group đọc toàn bộ dữ liệu. Ước lượng thô trên toàn cluster:

- Producer tới leader: khoảng 100 MB/s.
- Leader tới follower: khoảng 200 MB/s replication traffic.
- Broker tới consumer group: khoảng 100 MB/s egress.

Tổng cộng khoảng 400 MB/s traffic logic trước khi tính protocol overhead, retry, imbalance và routing thực tế. Đây không phải công thức băng thông cho từng NIC: lưu lượng phân bố theo leader placement, follower placement, rack/AZ và consumer assignment.

Nếu có nhiều consumer group độc lập cùng đọc toàn bộ topic, egress có thể tăng gần theo số group. Nếu consumer chỉ đọc một phần partition, traffic sẽ thấp hơn.

### 6.2. Băng thông và latency khác nhau

- **Bandwidth:** lượng dữ liệu truyền được mỗi giây.
- **Latency/RTT:** thời gian một gói tin đi-về giữa hai endpoint.
- **Packet loss/retransmission:** làm tăng thời gian hoàn tất request và giảm throughput hiệu dụng.
- **Jitter:** latency biến động có thể làm p99 tăng dù average vẫn ổn.
- **Connection count:** nhiều connection có thể làm tăng socket, thread, buffer và TLS handshake overhead.

Produce với `acks=all` có thể bị ảnh hưởng bởi RTT giữa leader và follower, nhất là khi replica nằm khác rack/AZ. Cross-zone replication tăng khả năng chịu lỗi nhưng cũng có thể tăng latency và chi phí network.

### 6.3. Theo dõi network

Các chỉ số nên xem:

- NIC bytes/s và packets/s.
- NIC utilization so với line rate.
- Dropped packets, errors và retransmissions.
- TCP retransmission/RTT.
- Broker BytesIn/BytesOut.
- ReplicationBytesIn/ReplicationBytesOut.
- Request queue và network processor idle.
- Consumer fetch rate và lag.
- Traffic giữa rack/AZ.

Trên Linux:

~~~bash
sar -n DEV 1
sar -n TCP,ETCP 1
ss -ti
ethtool -S <interface>
~~~

Nếu broker BytesOut cao nhưng consumer throughput thấp, kiểm tra consumer assignment, network egress, deserialization và downstream processing. Không mặc định tăng NIC bandwidth nếu bottleneck thực tế nằm ở consumer database.

## 7. Partition ảnh hưởng tới cách dùng tài nguyên

Partition là đơn vị parallelism cơ bản của Kafka. Nhiều partition hơn có thể tăng khả năng phân phối leader và consumer task, nhưng cũng làm tăng metadata, file handle, segment, replica và công việc background.

| Tăng partition có thể giúp | Tăng partition cũng có thể gây |
|---|---|
| Tăng consumer parallelism | Nhiều file và segment hơn |
| Phân phối leader lên nhiều broker | Metadata và memory overhead tăng |
| Tăng khả năng xử lý song song | Nhiều replication stream hơn |
| Tách tải theo key/partition | Rebalance và quản lý topic phức tạp hơn |
| Tăng tổng throughput khi có tài nguyên | Hot partition vẫn có thể nghẽn |

Nếu một partition nhận phần lớn traffic do key skew, thêm partition tổng thể không chắc giải quyết được. Cần xem phân phối record/byte theo partition và key distribution.

### 7.1. Leader skew

Nếu nhiều partition leader tập trung trên một broker, broker đó nhận phần lớn produce traffic và chịu nhiều replication/fetch request hơn. CPU, network và disk của broker này có thể bão hòa trước các broker khác.

Kiểm tra:

- Số leader partition trên từng broker.
- BytesIn/BytesOut theo broker.
- Request rate và request latency.
- Disk throughput và utilization.
- Under-replicated partitions.
- Partition hot key hoặc traffic skew.

Cân bằng leader và replica assignment có thể cải thiện utilization. Tuy nhiên, reassignment tạo network/disk traffic bổ sung; nên thực hiện theo batch và theo dõi ISR trong quá trình chạy.

## 8. Tương tác giữa các tài nguyên

Một bottleneck có thể gây áp lực lan sang tài nguyên khác:

~~~mermaid
flowchart TD
    D["Disk latency tăng"] --> Q["Request xử lý lâu hơn"]
    Q --> L["Request queue tăng"]
    L --> T["Produce/fetch latency tăng"]
    T --> R["Client timeout và retry"]
    R --> N["Network/CPU load tăng"]
    N --> Q
    M["RAM thiếu, page cache giảm"] --> D
    C["CPU saturation"] --> Q
    W["Network loss hoặc RTT cao"] --> R
~~~

Ví dụ:

- RAM thiếu làm page cache giảm, disk read tăng, fetch latency tăng.
- CPU bão hòa làm compression chậm, request queue tăng.
- Network packet loss làm replication chậm, ISR shrink và produce latency tăng.
- Consumer chậm làm lag tăng; nếu consumer retry hoặc scan lại nhiều, broker egress tăng.
- Disk compaction nặng làm disk queue tăng và ảnh hưởng produce/fetch.

Do đó cần đo nhiều tầng cùng thời điểm và so sánh theo broker/partition.

## 9. Producer batching và compression

Producer batching giúp giảm số request và amortize network overhead.

Các cấu hình thường gặp:

~~~properties
batch.size=65536
linger.ms=5
compression.type=lz4
buffer.memory=67108864
acks=all
~~~

Đây là giá trị minh họa để thử nghiệm, không phải preset production.

| Cấu hình | Tác động chính | Trade-off |
|---|---|---|
| `batch.size` | Kích thước batch mục tiêu theo partition | Batch lớn có thể tăng hiệu quả nén nhưng cần thêm buffer và chờ gom |
| `linger.ms` | Thời gian chờ thêm record để gom batch | Tăng có thể cải thiện throughput nhưng tăng latency |
| `compression.type` | Codec nén batch | Giảm network/disk bytes nhưng dùng CPU |
| `buffer.memory` | Tổng bộ nhớ producer buffer | Quá nhỏ dễ block khi broker chậm; quá lớn tăng memory footprint |
| `acks` | Điều kiện acknowledgement | all tăng durability nhưng phụ thuộc ISR và replication latency |

Batching hiệu quả phụ thuộc số partition mà producer gửi tới. Nếu record phân tán qua rất nhiều partition nhưng mỗi partition nhận ít record, mỗi batch có thể không đầy.

Đo batch size thực tế, records per request, producer buffer availability và record queue time trước khi tăng batch/linger.

## 10. Consumer fetch và downstream processing

Consumer fetch theo batch để giảm request overhead. Một số cấu hình ảnh hưởng cách gom dữ liệu:

~~~properties
fetch.min.bytes=65536
fetch.max.wait.ms=50
max.partition.fetch.bytes=1048576
max.poll.records=500
~~~

Các giá trị này chỉ là ví dụ.

- `fetch.min.bytes`: broker có thể đợi có đủ dữ liệu trước khi trả fetch response.
- `fetch.max.wait.ms`: giới hạn thời gian broker chờ để đáp ứng fetch minimum.
- `max.partition.fetch.bytes`: giới hạn dữ liệu fetch cho mỗi partition trong một request.
- `max.poll.records`: số record tối đa trả cho một lần poll; không phải giới hạn byte của response.

Tăng fetch batch có thể cải thiện throughput nhưng làm tăng latency chờ gom, memory footprint và thời gian xử lý mỗi poll. Nếu downstream DB chậm, tăng fetch size có thể khiến consumer giữ nhiều record hơn trong bộ nhớ mà không cải thiện end-to-end throughput.

Cần đo consumer lag, fetch latency, records consumed, processing time, poll interval và thời gian commit offset.

## 11. Broker threads và request queues

Broker dùng network processor để nhận/gửi request và request handler để xử lý các request như produce/fetch. Nếu thread pool hoặc queue bị bão hòa, latency tăng dù disk/CPU tổng thể chưa đạt 100%.

Các cấu hình cần biết:

| Cấu hình | Vai trò |
|---|---|
| `num.network.threads` | Số thread xử lý network request |
| `num.io.threads` | Số thread xử lý request và công việc I/O liên quan |
| `queued.max.requests` | Giới hạn request chờ trong queue |
| `socket.send.buffer.bytes` | Socket send buffer |
| `socket.receive.buffer.bytes` | Socket receive buffer |

Không tăng các giá trị này theo cảm tính. Nhiều thread hơn có thể tăng context switching, memory và contention. Trước khi chỉnh, kiểm tra request queue time, request handler idle, network processor idle, CPU per core và request mix.

## 12. Ước lượng dung lượng và năng lực cluster

### 12.1. Ước lượng storage

Một ước lượng ban đầu:

~~~text
Storage thô ≈
  ingress bytes/second sau nén
  × retention seconds
  × replication factor
  × hệ số dự phòng
~~~

Ví dụ:

- Ingress sau nén: 20 MB/s.
- Retention: 3 ngày = 259.200 giây.
- Replication factor: 3.
- Chưa tính overhead và headroom.

Storage payload xấp xỉ:

~~~text
20 MB/s × 259.200 s × 3
= 15.552.000 MB
≈ 15,6 TB (decimal)
~~~

Cần cộng index, segment overhead, internal topics, compaction headroom, reassignment/recovery và dung lượng không nên sử dụng hết. Với topic compacted, dữ liệu thực tế phụ thuộc key cardinality và churn chứ không chỉ retention time.

### 12.2. Ước lượng network

Bắt đầu bằng ingress sau nén, sau đó cộng replication traffic, consumer egress và mirror/Connect traffic. Phân bổ theo broker leader/replica placement để tránh chỉ nhìn tổng cluster.

### 12.3. Headroom

Không sizing cluster để mọi broker luôn chạy sát 100% CPU, disk hoặc NIC. Cần headroom cho:

- Traffic burst.
- Broker restart hoặc failure.
- Partition reassignment.
- Replica catch-up.
- Log compaction và retention cleanup.
- Consumer replay.
- Rolling upgrade.

Cluster phải tiếp tục đáp ứng mục tiêu latency/throughput khi một broker hoặc một rack/AZ mất khả năng phục vụ theo failure model đã chọn.

## 13. Metrics cần theo dõi

Nên kết hợp metric Kafka JMX với metric hệ điều hành và client.

| Lớp | Metric / tín hiệu | Điều cần tìm |
|---|---|---|
| Broker traffic | BytesInPerSec, BytesOutPerSec | Ingress/egress và broker skew |
| Replication | ReplicationBytesInPerSec, ReplicationBytesOutPerSec | Replica traffic |
| ISR | UnderReplicatedPartitions, IsrShrinksPerSec | Follower chậm hoặc mất replica |
| Request | RequestQueueTimeMs, LocalTimeMs, RemoteTimeMs, TotalTimeMs | Thời gian chờ và xử lý request |
| Thread pool | RequestHandlerAvgIdlePercent | Request handler có bị bão hòa không |
| Network | NetworkProcessorAvgIdlePercent | Network processor có bị bão hòa không |
| Disk | Read/write latency, IOPS, throughput, queue depth, utilization | Storage bottleneck |
| Memory | Heap after GC, GC pause, available RAM, page cache | Heap/GC hay page-cache pressure |
| CPU | CPU per core, run queue, iowait, steal | CPU saturation hoặc host contention |
| Producer | RecordErrorRate, RequestLatency, BufferPoolWaitTime | Broker chậm hoặc producer buffer thiếu |
| Consumer | FetchLatency, records consumed, lag, processing time | Fetch hoặc downstream chậm |

Một số JMX metric name và label thay đổi theo Kafka version. Hãy đối chiếu với metric catalog của release đang triển khai; không hardcode dashboard theo tên metric của một phiên bản khác mà không kiểm tra.

## 14. Quy trình chẩn đoán bottleneck

Thực hiện theo thứ tự:

1. Xác định workload: ingress/egress, record size, partition count, replication factor, retention, số consumer group và latency target.
2. So sánh broker: leader distribution, BytesIn/Out, CPU, disk và NIC.
3. Kiểm tra request latency: queue time, local time, remote time và response send time.
4. Kiểm tra disk: await/latency, utilization, queue depth, read/write throughput và log flush.
5. Kiểm tra RAM: heap sau GC, native memory, available RAM và page cache.
6. Kiểm tra CPU: per-core, compression, TLS, GC, compaction và thread saturation.
7. Kiểm tra network: bandwidth, RTT, retransmission, packet drop và replication path.
8. Kiểm tra client: producer batching/buffer, consumer fetch/processing và retry.
9. Thay một biến cấu hình hoặc tài nguyên mỗi lần; chạy lại cùng workload và so sánh p50/p95/p99.
10. Giữ thay đổi chỉ khi cải thiện mục tiêu mà không làm giảm durability hoặc tăng rủi ro khác.

### 14.1. Công cụ hệ điều hành trên Linux

~~~bash
# CPU và thread
top -H -p <broker-pid>
pidstat -u -r -d -p <broker-pid> 1
mpstat -P ALL 1

# Memory và page fault
free -h
vmstat 1
sar -B 1

# Disk
iostat -xz 1

# Network
sar -n DEV 1
sar -n TCP,ETCP 1
ss -ti
~~~

Trong môi trường Windows, dùng Performance Monitor để quan sát CPU, Available Memory, Disk sec/Read, Disk sec/Write, Disk Queue Length, Bytes Total/sec và NIC throughput. Chọn counter tương ứng với ổ đĩa và interface đang chứa Kafka data.

## 15. Triệu chứng và hướng điều tra

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần kiểm tra |
|---|---|---|
| Produce latency tăng, disk await cao | Storage chậm hoặc I/O queue dài | iostat, disk latency, broker request local time |
| Consumer fetch chậm, page cache thấp | Working set lớn, cache miss nhiều | Available RAM, page faults, disk read |
| CPU cao nhưng disk/network thấp | Compression, TLS, serialization hoặc GC | CPU per core, profiler, GC log |
| Network NIC gần line rate | Ingress/replication/consumer egress quá cao | BytesIn/Out, replication metrics, NIC drops |
| Under-replicated partitions tăng | Follower chậm do disk, CPU hoặc network | ISR, replication lag, follower disk/network |
| Một broker nóng hơn phần còn lại | Leader/partition skew hoặc hot key | Leader count, bytes/partition, request rate |
| RequestQueueTimeMs cao | Request handler thiếu năng lực hoặc upstream burst | Handler idle, CPU, request mix |
| NetworkProcessorAvgIdlePercent thấp | Network thread bão hòa hoặc connection churn | Network processor metric, connection count |
| GC pause tăng, consumer lag tăng | Heap pressure hoặc allocation churn | GC logs, heap after GC, allocation rate |
| Thêm partition nhưng throughput không tăng | Bottleneck nằm ở disk/network/CPU hoặc key skew | Partition traffic, resource metrics, consumer parallelism |
| Tăng batch nhưng latency xấu đi | linger/batch wait quá lớn hoặc buffer pressure | Batch size, queue time, p95/p99, buffer wait |
| Rebalance/recovery làm cluster chậm | Replica reassignment và catch-up tranh tài nguyên | Replication traffic, disk queue, ISR changes |

## 16. Bài lab đo tác động từng tài nguyên

Có thể chạy một bài benchmark có kiểm soát:

1. Tạo topic thử nghiệm với partition count và replication factor cố định.
2. Dùng producer tạo payload kích thước cố định, key phân phối đều.
3. Ghi nhận throughput, p50/p95/p99 produce latency và CPU.
4. Thử `compression.type=none`, `lz4` và `zstd` trên cùng dữ liệu.
5. Thay đổi `batch.size` và `linger.ms` từng bước.
6. Chạy consumer đọc ngay dữ liệu mới để quan sát page-cache hit.
7. Chạy consumer đọc dữ liệu cũ hơn working set để tăng disk read.
8. Tăng số consumer group để quan sát network egress.
9. Chạy replication factor khác nhau trong môi trường test để quan sát replication traffic.
10. Lặp lại sau khi thay một tài nguyên hoặc cấu hình, giữ các yếu tố còn lại cố định.

Ghi lại:

| Lần chạy | Codec | Batch/linger | Producer MB/s | p99 produce | Consumer MB/s | CPU | Disk await | NIC |
|---|---|---|---:|---:|---:|---:|---:|---:|
| A | none | baseline | | | | | | |
| B | lz4 | baseline | | | | | | |
| C | zstd | baseline | | | | | | |
| D | lz4 | batch lớn hơn | | | | | | |

Không so sánh benchmark nếu record size, key distribution, replication, acks, retention, consumer count hoặc cache state khác nhau mà không ghi nhận. Một lần chạy nóng page cache có thể cho kết quả khác rất xa lần đọc cold data.

## 17. Checklist tối ưu phần cứng và hiệu năng

- [ ] Đã xác định data path producer → leader → replica → consumer.
- [ ] Đã phân biệt acknowledgement với fsync vật lý.
- [ ] Disk có đủ IOPS, throughput và latency ổn định.
- [ ] Kafka data directory không tranh chấp với workload I/O nặng khác.
- [ ] Có đủ RAM cho JVM, native memory và OS page cache.
- [ ] Heap được chọn theo GC/metadata thực tế, không chiếm gần hết RAM.
- [ ] Theo dõi page faults, cache pressure và disk read latency.
- [ ] Đã đo chi phí CPU của serialization, compression, TLS và GC.
- [ ] Chọn codec theo payload và trade-off CPU/network/storage.
- [ ] Network đủ cho producer, replication, consumer và mirror traffic.
- [ ] Theo dõi RTT, retransmission, packet drop và NIC utilization.
- [ ] Partition/leader được phân bố hợp lý, không có hot partition kéo dài.
- [ ] Producer batching và consumer fetch được tune theo latency/throughput target.
- [ ] Broker thread pool và request queue chỉ được chỉnh khi có bằng chứng saturation.
- [ ] Storage sizing tính retention, replication factor và headroom.
- [ ] Cluster còn capacity khi broker/rack failure và khi reassignment.
- [ ] Dashboard có Kafka JMX, OS metrics và client metrics đồng bộ thời gian.
- [ ] Benchmark thay đổi từng yếu tố và đo p50/p95/p99.
- [ ] Không đánh đổi durability hoặc security chỉ để cải thiện một metric đơn lẻ.

Hiệu năng Kafka là kết quả phối hợp giữa storage, page cache, RAM, CPU, network và partition placement. Disk tuần tự và page cache giúp Kafka phục vụ log hiệu quả; RAM phải đủ cho cả JVM lẫn hệ điều hành; CPU chịu chi phí nén, mã hóa và request processing; network phải gánh ingress, replication và consumer egress. Hãy đo từng tầng theo cùng một workload, tìm bottleneck thực sự rồi điều chỉnh có kiểm soát, đồng thời giữ headroom cho replication, recovery và traffic burst.
