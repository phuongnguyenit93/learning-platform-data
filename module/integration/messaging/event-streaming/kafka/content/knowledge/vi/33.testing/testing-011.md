# Load test, soak test và kiểm thử phục hồi sau backlog

Kafka có thể hoạt động ổn định ở tải bình thường nhưng vẫn gặp sự cố khi traffic tăng đột ngột, consumer dừng lâu hoặc downstream xử lý chậm. Load test, soak test và backlog recovery test kiểm tra ba năng lực khác nhau: chịu tải, duy trì ổn định dài hạn và bắt kịp dữ liệu sau gián đoạn.

Trong hệ thống KAFKA, producer ghi record vào topic-partition, broker lưu log và replication giữ replica, còn consumer group chia partition để xử lý. Khi producer tiếp tục ghi trong lúc consumer ngừng hoặc xử lý chậm, backlog tăng. Khi consumer hoạt động trở lại, hệ thống phải xử lý cả dữ liệu tồn đọng lẫn event mới. Chỉ đo messages per second trong một khoảng ngắn không chứng minh được khả năng phục hồi đó.

Bài này hướng dẫn thiết kế workload, chuẩn bị môi trường, đo throughput và latency, chạy load/soak test, tạo backlog có kiểm soát, tính tốc độ drain, đưa lỗi vào hệ thống và xác định tiêu chí nghiệm thu. Các ví dụ dùng Kafka CLI và metric phổ biến; hãy điều chỉnh theo phiên bản Kafka, client và nền tảng triển khai thực tế.

## 1. Mục tiêu của ba loại kiểm thử

### 1.1. Load test

Load test đo hành vi của Kafka và ứng dụng khi tải tăng từ mức thấp đến tải mục tiêu hoặc vượt ngưỡng thiết kế. Câu hỏi chính:

- Cluster đạt throughput bao nhiêu với message size và replication policy cụ thể?
- p95/p99 produce latency và end-to-end latency thay đổi ra sao?
- CPU, disk, network, heap, GC và request handler còn headroom không?
- Consumer group có xử lý kịp tốc độ producer không?
- Khi tăng partition hoặc consumer instance, throughput có tăng tương ứng không?
- Điểm bão hòa nằm ở producer, broker, network, disk hay downstream?

Load test cần có ramp-up, steady load, peak/burst và đôi khi overload có kiểm soát. Không chỉ chạy một mức tải cố định rồi ghi throughput trung bình.

### 1.2. Soak test

Soak test giữ workload ổn định trong thời gian dài để phát hiện vấn đề chỉ xuất hiện sau nhiều giờ hoặc nhiều chu kỳ vận hành:

- Memory leak, heap growth hoặc direct memory tăng dần.
- GC pause tăng theo thời gian.
- File descriptor, connection hoặc thread bị rò rỉ.
- Disk tăng đến ngưỡng retention hoặc log segment không được xóa như dự kiến.
- Compaction, index, page cache và filesystem làm latency thay đổi.
- Consumer lag tích lũy chậm nhưng liên tục.
- Connector task restart, Streams state restore hoặc rebalance lặp lại.
- Certificate, credential hoặc token hết hạn.
- Metric, log và alert bị mất dữ liệu do retention của hệ thống giám sát.

Soak test thường chạy nhiều giờ đến vài ngày tùy mục tiêu. Thời lượng cần đủ để quan sát chu kỳ retention, compaction, backup, batch job và peak traffic đại diện.

### 1.3. Kiểm thử phục hồi sau backlog

Backlog recovery test chủ động làm consumer chậm hoặc dừng trong một khoảng thời gian, để record tích lũy trong topic. Sau đó khôi phục consumer và đo khả năng xử lý backlog trong khi producer vẫn tiếp tục ghi.

Cần trả lời:
- Backlog tăng bao nhiêu record và bao nhiêu byte?
- Consumer cần bao lâu để bắt kịp?
- Trong lúc drain, consumer có làm tăng latency hoặc lỗi producer không?
- Hệ thống có duy trì tốc độ xử lý lớn hơn tốc độ ingest không?
- Record cũ nhất còn tồn đọng có tuổi bao nhiêu?
- Có duplicate, mất record, sai ordering hoặc side effect lặp không?
- Nếu consumer bị restart giữa lúc drain, tiến trình có tiếp tục an toàn không?

Ba loại test bổ sung cho nhau. Load test tìm giới hạn tải; soak test tìm suy giảm dài hạn; backlog recovery test chứng minh hệ thống trở lại trạng thái bình thường sau gián đoạn.

## 2. Xác định SLO và tiêu chí nghiệm thu

Trước khi chạy test, chuyển yêu cầu kinh doanh thành chỉ số đo được. Không nên chọn ngưỡng sau khi đã thấy kết quả vì dễ điều chỉnh tiêu chí để hợp thức hóa một bài test không đạt.

Một bộ SLO mẫu:

| Chỉ số | Ví dụ mục tiêu | Ý nghĩa |
|---|---:|---|
| Ingress throughput | 50.000 records/s | Tốc độ producer ghi vào cluster |
| Produce p99 latency | dưới 100 ms | Độ trễ xác nhận ghi ở producer |
| End-to-end p99 | dưới 2 s ở steady state | Thời gian từ lúc tạo event đến lúc xử lý xong |
| Consumer lag | ổn định, không tăng liên tục | Consumer theo kịp producer |
| Recovery drain rate | tối thiểu 1,5 lần ingress | Có dư năng lực xử lý backlog |
| Backlog recovery time | dưới 20 phút | Thời gian trở về ngưỡng lag mục tiêu |
| Error rate | dưới 0,1% | Tỷ lệ lỗi theo định nghĩa test |
| Data integrity | 100% event ID đối soát được | Không mất hoặc tạo sai record |

Các con số trên chỉ là ví dụ để xây dựng bài test. SLO thật phải dựa vào workload, RPO/RTO, business latency và chi phí vận hành.

### 2.1. Định nghĩa rõ latency

Cần phân biệt:
- **Produce latency:** thời gian producer gửi request đến khi nhận acknowledgement.
- **Broker request latency:** thời gian broker xử lý request theo metric.
- **Consumer processing latency:** thời gian ứng dụng xử lý record sau khi poll.
- **End-to-end latency:** thời gian từ timestamp tạo event đến khi side effect hoặc kết quả downstream hoàn tất.
- **Backlog age:** tuổi của record cũ nhất chưa được xử lý.

Không lấy broker request latency thay cho end-to-end latency. Consumer có thể poll nhanh nhưng xử lý database chậm; producer có thể ghi nhanh trong khi downstream bị tồn đọng.

### 2.2. Đặt ngưỡng theo percentile

Latency trung bình che giấu tail latency. Ghi tối thiểu p50, p95, p99 và max theo cửa sổ thời gian phù hợp.

Không gộp mọi partition vào một histogram duy nhất nếu một partition nóng có thể bị che khuất bởi các partition khỏe. Nên có phân tích theo topic, partition hoặc key range khi công cụ hỗ trợ.

### 2.3. Xác định phạm vi hệ thống

Ghi rõ test đang đo thành phần nào:
- Producer và serializer.
- Network từ load generator đến broker.
- Broker, replication và storage.
- Consumer group và application processing.
- Database hoặc HTTP service downstream.
- Kafka Connect hoặc Kafka Streams.
- Monitoring và alerting pipeline.

Nếu database là bottleneck thì không thể kết luận Kafka không đạt năng lực chỉ dựa trên end-to-end throughput. Ngược lại, không thể tuyên bố toàn hệ thống đạt SLO chỉ vì broker đạt benchmark tốt.

## 3. Thiết kế workload đại diện

### 3.1. Message size và phân bố dữ liệu

Ghi lại:
- Kích thước trung bình, p95 và tối đa của key/value/header.
- Tỷ lệ message nhỏ, vừa và lớn.
- Compression codec và compression level.
- Tỷ lệ null key, key lặp và key phân bố lệch.
- Header count và kích thước header.
- Timestamp type và cách tạo event time.

Message size ảnh hưởng trực tiếp đến bytes/s, batch size, network, disk và CPU nén/giải nén. Một test chỉ dùng record 100 byte không đại diện cho workload thực tế nếu production có payload JSON vài KB.

### 3.2. Key distribution và partition skew

Kafka chọn partition dựa trên key/partitioner. Nếu một số key chiếm phần lớn traffic, một partition có thể nóng dù tổng partition count lớn.

Workload nên có ít nhất ba profile:
1. **Uniform keys:** key phân bố đều, dùng để đo khả năng scale tổng thể.
2. **Skewed keys:** một nhóm key chiếm tỷ lệ traffic cao, dùng để phát hiện hot partition.
3. **Null/custom partitioning:** mô phỏng ứng dụng thực tế nếu không dùng key mặc định.

Đo record rate và byte rate theo partition. Tổng throughput cao nhưng một partition có lag tăng liên tục vẫn là dấu hiệu thiết kế không đạt.

### 3.3. Producer concurrency

Mô phỏng số producer instance, thread, connection và batch behavior gần production. Ghi lại:
- acks, idempotence và retry.
- batch.size và linger.ms.
- compression.type.
- max.in.flight.requests.per.connection.
- buffer.memory và max.block.ms.
- Delivery timeout và request timeout.
- Transactional ID nếu dùng transaction.

Không tối ưu benchmark bằng cách tắt durability hoặc retry nếu production yêu cầu các tính năng đó. So sánh cấu hình phải giữ cùng semantics để kết quả có ý nghĩa.

### 3.4. Consumer concurrency

Consumer group chỉ có thể gán một partition cho tối đa một consumer member tại một thời điểm trong group. Vì vậy, tăng consumer instance vượt quá partition count không nhất thiết tăng throughput.

Ghi lại:
- Partition count và consumer member count.
- max.poll.records, fetch.min.bytes, fetch.max.bytes.
- max.poll.interval.ms và session.timeout.ms.
- Số thread xử lý song song bên trong mỗi consumer.
- Batch size và thời gian xử lý mỗi record.
- Commit mode và commit interval.
- Retry, pause/resume và dead-letter behavior.

Consumer xử lý song song trong application có thể tạo reorder nếu nhiều worker hoàn thành không theo thứ tự poll. Nếu ordering là yêu cầu, test phải kiểm tra theo key/partition và cách commit offset.

### 3.5. Workload matrix

Ví dụ workload matrix cho một hệ thống đặt hàng:

| Profile | Message size | Ingress | Consumer | Mục tiêu |
|---|---:|---:|---:|---|
| Baseline | 1 KB | 5.000 records/s | 5.000 records/s | Xác minh môi trường và metric |
| Normal | 1 KB | 20.000 records/s | 20.000 records/s | Đo steady state |
| Peak | 1 KB | 50.000 records/s | 50.000 records/s | Kiểm tra SLO tải cao |
| Burst | 1 KB | 80.000 records/s trong 5 phút | 50.000 records/s | Quan sát lag tăng |
| Large payload | 32 KB | 5.000 records/s | 5.000 records/s | Kiểm tra byte throughput |
| Skewed | 1 KB | 20.000 records/s | 20.000 records/s | Tìm hot partition |
| Recovery | 1 KB | 20.000 records/s | Dừng 10 phút rồi drain | Đo backlog recovery |

Đây là ma trận minh họa. Thay giá trị bằng traffic forecast, peak factor, message distribution và SLO thực tế.

## 4. Chuẩn bị môi trường kiểm thử

### 4.1. Môi trường gần production

Cố gắng giữ tương đồng về:
- Kafka version và KRaft topology.
- Broker count, CPU, RAM và JVM.
- Disk type, IOPS, throughput và filesystem.
- Network bandwidth và latency.
- Topic partition count, replication factor và min ISR.
- Retention, cleanup policy và compression.
- Security protocol, TLS/SASL và ACL.
- Producer/consumer client version.
- Connector, Streams application và downstream database.

Nếu test trên một broker đơn lẻ nhưng production có ba broker và replication factor 3, kết quả không đại diện cho chi phí replication và network thực tế.

### 4.2. Tách load generator khỏi cluster

Không chạy tất cả producer/consumer benchmark trên chính broker host. CPU hoặc network của generator có thể cạnh tranh với Kafka và làm sai kết quả.
Dùng nhiều generator host khi cần throughput cao. Theo dõi CPU, NIC, file descriptor và process saturation của generator. Nếu generator đạt 100% CPU trước broker, đó là giới hạn của công cụ tạo tải, không phải giới hạn Kafka.

### 4.3. Cô lập dữ liệu test

- Dùng topic có tên riêng và policy retention rõ ràng.
- Không ghi test event vào topic production nếu chưa có phê duyệt và fencing.
- Đặt event ID duy nhất để đối soát.
- Xác định cách xóa topic hoặc dữ liệu test sau khi hoàn tất.
- Không dùng payload chứa thông tin cá nhân hoặc bí mật thật.
- Đảm bảo test không làm cạn disk hoặc quota của cluster dùng chung.

Nếu test trên production-like cluster, cần change window, owner, giới hạn tốc độ và tiêu chí dừng tự động.

### 4.4. Đồng bộ thời gian

Producer, broker, consumer và monitoring host cần đồng bộ NTP/chrony. Nếu đồng hồ lệch, end-to-end latency tính từ event timestamp có thể âm hoặc sai lệch.

Ghi rõ timestamp nguồn, timestamp broker và timestamp xử lý. Với test đo thời gian ở mức mili giây, clock skew phải nhỏ hơn sai số chấp nhận được.

### 4.5. Xác nhận observability trước khi tạo tải

Trước test, kiểm tra:
- Kafka broker metrics được scrape.
- Consumer lag và per-partition lag có sẵn.
- Producer metrics được thu thập.
- Host metrics gồm CPU, memory, disk và network.
- Application metrics có processing duration và error count.
- Dashboard có cùng time range và timezone.
- Alert phát hiện offline partition, ISR shrink, disk pressure và consumer lag.

Không thể phân tích một test nếu metric pipeline bị thiếu hoặc chỉ scrape mỗi phút trong khi cần phát hiện burst kéo dài 30 giây.

## 5. Các metric cần đo

### 5.1. Producer

| Nhóm | Chỉ số |
|---|---|
| Throughput | records/s, bytes/s |
| Latency | request latency p50/p95/p99, record queue time |
| Reliability | error rate, retries, record errors, timeout |
| Buffer | buffer available bytes, waiting threads |
| Batch | batch size, compression rate, requests in flight |
| Delivery | record send rate, acknowledgement rate |

Producer có thể báo throughput cao do record đang nằm trong buffer. Chỉ tính record đã được broker acknowledge khi đo throughput thành công.

### 5.2. Broker

Theo dõi:
- Bytes in/out per second.
- Messages in per second.
- Produce/Fetch request rate và latency.
- Request queue time và request handler idle.
- Network processor idle.
- Active connections và connection creation rate.
- CPU, heap, GC pause và thread count.
- Disk utilization, disk latency, queue depth và log flush.
- Page cache và memory pressure.
- Under-replicated partitions, offline partitions và ISR shrink/expand.
- Leader election và controller/quorum health.
- Replication fetcher lag và replica catch-up.

### 5.3. Consumer

| Nhóm | Chỉ số |
|---|---|
| Throughput | records/s, bytes/s |
| Lag | records behind, lag per partition |
| Age | tuổi record cũ nhất chưa xử lý |
| Processing | processing time p50/p95/p99 |
| Poll | records per poll, poll interval |
| Commit | commit latency, commit failures |
| Group | member count, rebalance count, assignment |
| Reliability | deserialization errors, retry, DLT rate |

Consumer lag là khoảng cách offset giữa log end và committed position theo cách công cụ tính. Lag bằng 0 không chứng minh end-to-end processing hoàn tất nếu ứng dụng commit offset trước khi side effect hoàn tất. Phải đối chiếu với application processing metric và event ID.

### 5.4. Downstream

Nếu consumer ghi database hoặc gọi service:
- Connection pool usage.
- Query latency và lock wait.
- HTTP request latency và error rate.
- Thread pool queue.
- Retry count và circuit breaker state.
- Database write throughput.
- Deadlock, timeout và saturation.

Một consumer group có thể đọc Kafka nhanh nhưng tạo backlog ở database queue. Đo riêng từng tầng để tìm bottleneck.

## 6. Chạy load test theo từng giai đoạn

Một bài load test nên có các phase rõ ràng và được ghi timestamp.

### 6.1. Baseline

Chạy tải thấp để xác nhận:
- Generator gửi đủ tốc độ yêu cầu.
- Record count ở source và sink khớp.
- Producer acknowledgement thành công.
- Consumer group nhận đúng partition.
- Metric và dashboard hiển thị.
- Không có lỗi serializer, ACL hoặc network.

Nếu baseline chưa ổn, không tăng tải.

### 6.2. Ramp-up

Tăng tải theo bậc, ví dụ 10%, 25%, 50%, 75%, 100% mục tiêu. Giữ mỗi bậc đủ lâu để hệ thống ổn định và metric có ý nghĩa.

Quan sát điểm mà:
- Latency bắt đầu tăng nhanh.
- Consumer lag chuyển từ ổn định sang tăng.
- CPU hoặc disk gần bão hòa.
- Request queue tăng.
- ISR bắt đầu shrink.
- Producer buffer chờ hoặc retry tăng.

Không tăng bậc tiếp theo khi hệ thống chưa đạt steady state ở bậc hiện tại.

### 6.3. Steady load

Giữ tải mục tiêu trong khoảng thời gian đủ dài để có baseline ổn định. So sánh:
- Ingress và egress records/s.
- Produce và end-to-end latency.
- Consumer lag theo partition.
- CPU, disk, network và GC.
- Error/retry rate.
- Resource headroom.

Một steady state tốt có lag dao động quanh mức thấp và không tăng dần. Nếu lag tăng đều, consumer capacity đang thấp hơn ingest dù producer throughput có thể vẫn đạt mục tiêu.

### 6.4. Peak và burst

Tạo tải cao hơn bình thường trong khoảng ngắn, sau đó trở lại normal. Mục tiêu là đo khả năng hấp thụ burst và thời gian lag quay về baseline.

Không chỉ ghi peak throughput. Ghi cả:
- Maximum lag.
- Maximum record age.
- Time to recover.
- Error rate trong burst.
- Producer throttling và backpressure.
- CPU/disk/network sau khi burst kết thúc.

### 6.5. Overload có kiểm soát

Nếu mục tiêu là tìm saturation point, tăng tải vượt capacity theo từng bước nhỏ. Đặt giới hạn tự dừng:
- Disk free space thấp hơn ngưỡng.
- Broker CPU duy trì quá cao.
- Offline partition xuất hiện.
- ISR mất an toàn.
- Error rate vượt ngưỡng.
- Producer retry storm.
- Consumer lag vượt giới hạn retention hoặc business RTO.

Overload test không cần phá cluster. Khi đã xác định saturation point, dừng tăng tải và phục hồi hệ thống về baseline.

## 7. Sử dụng Kafka performance tools

Kafka cung cấp công cụ benchmark cơ bản. Chúng hữu ích để kiểm tra broker và đường truyền, nhưng không thay thế workload của ứng dụng thực tế.

### 7.1. Producer performance test

Ví dụ chạy producer perf test với 1 KB record, 100.000 record:

~~~bash
bin/kafka-producer-perf-test.sh \
  --topic perf-load \
  --num-records 100000 \
  --record-size 1024 \
  --throughput -1 \
  --producer-props \
    bootstrap.servers=kafka-1:9092 \
    acks=all \
    compression.type=snappy
~~~

Công cụ tạo record có kích thước cố định và báo throughput/latency theo khả năng của phiên bản. Kiểm tra help của đúng Kafka release để biết đầy đủ option.

Để mô phỏng throughput giới hạn, có thể đặt --throughput thành số record mỗi giây thay vì -1. Chạy nhiều generator process nếu cần tăng concurrency, nhưng ghi lại tổng số process và tốc độ mỗi process.

### 7.2. Consumer performance test

Ví dụ đo consumer từ topic:

~~~bash
bin/kafka-consumer-perf-test.sh \
  --bootstrap-server kafka-1:9092 \
  --topic perf-load \
  --messages 100000 \
  --group perf-consumer-group
~~~

Cú pháp option có thể thay đổi giữa các release. Hãy dùng --help của binary đang chạy và kiểm tra consumer group/offset sau test.

### 7.3. Kafka Streams hoặc application benchmark

Để đo end-to-end, dùng ứng dụng gần production:
- Producer tạo event với ID, key và timestamp.
- Consumer xử lý event và ghi kết quả hoặc xác nhận vào sink.
- Ứng dụng xuất metric processing rate, processing duration và error.
- Có thể đối soát event ID ở source và sink.

Perf tool không mô phỏng transaction, custom serializer, database write, retry topic hoặc business logic nếu các tính năng đó không được cấu hình.

### 7.4. Ghi lại cấu hình chính xác

Mỗi lần chạy cần lưu:
- Kafka version và JDK.
- Client library version.
- Producer/consumer properties.
- Topic configs và partition count.
- Replication factor/min ISR.
- Message size/compression.
- Generator count/host.
- Test duration và target rate.
- Kết quả metric và thời gian bắt đầu/kết thúc.

Không so sánh hai benchmark nếu workload hoặc durability semantics khác nhau.

## 8. Soak test: kiểm tra độ ổn định dài hạn

### 8.1. Thiết kế thời lượng

Chọn thời lượng dựa vào chu kỳ cần quan sát. Ví dụ:
- 2–4 giờ để kiểm tra ổn định cơ bản.
- 12–24 giờ để quan sát daily peak và batch job.
- 48–72 giờ hoặc lâu hơn nếu cần kiểm tra retention, compaction, credential rotation hoặc memory trend.

Thời lượng phải phù hợp mục tiêu; không có một con số bắt buộc cho mọi hệ thống.

### 8.2. Giữ workload thực tế

Trong soak test, giữ throughput và key distribution gần steady production. Có thể lặp chu kỳ:
- Normal load.
- Peak window.
- Low traffic.
- Batch ingest.
- Consumer restart hoặc rolling broker maintenance nếu test scope cho phép.

Đảm bảo test không vô tình thay đổi message size hoặc producer count giữa chừng.

### 8.3. Tìm resource leak và degradation

Theo dõi trend theo thời gian:
- Heap sau GC có tăng dần không?
- Direct buffer hoặc native memory có tăng không?
- GC pause p99 có xấu dần không?
- File descriptor và connection count có tăng không?
- Thread count có tăng bất thường không?
- Disk usage có tăng đúng theo retention không?
- Consumer lag có drift tăng dù throughput trung bình cân bằng không?
- Connector task có restart lặp lại không?
- Streams state store/changelog có tăng vượt dự báo không?

Một snapshot tại cuối test không đủ. Vẽ time series với cùng cửa sổ thời gian và đánh dấu event như restart, rebalance, compaction hoặc backup.

### 8.4. Retention và disk growth

Ước lượng dung lượng log theo byte ingress và retention:

\[
Storage \approx IngressBytesPerSecond \times RetentionSeconds \times ReplicationFactor
\]

Công thức này là ước lượng sơ bộ, chưa tính compression, index, segment overhead, compaction, replication traffic và free-space reserve.

Ví dụ ingress 20 MiB/s, retention 24 giờ và replication factor 3:

\[
20 \times 86{,}400 \times 3 = 5{,}184{,}000\ MiB
\]

Tương đương khoảng 4.94 TiB trước overhead và compression. Dùng số liệu disk thực tế trong test để hiệu chỉnh capacity plan.

### 8.5. Soak test có fault injection

Nếu scope cho phép, đưa một số lỗi nhỏ và có kiểm soát:
- Restart một consumer instance.
- Restart một broker theo rolling procedure.
- Tạm ngắt một downstream dependency.
- Giảm tốc độ xử lý của một consumer.
- Làm một connector task restart.
- Thực hiện credential rotation theo lịch.

Sau mỗi fault, ghi thời gian phục hồi và xác nhận không có lỗi dữ liệu. Không đồng thời inject nhiều lỗi nếu mục tiêu là xác định tác động của từng lỗi riêng.

## 9. Tạo backlog có kiểm soát

Backlog được tạo khi tốc độ producer lớn hơn tốc độ consumer hoặc consumer tạm ngừng trong khi producer vẫn ghi.

### 9.1. Ba cách tạo backlog

**Cách A — Dừng consumer group**

Dừng các consumer instance trong một khoảng thời gian đã định, giữ producer tiếp tục ghi. Đây là cách đơn giản để mô phỏng consumer outage.

**Cách B — Giảm processing rate**

Giữ consumer chạy nhưng thêm delay hoặc giảm worker concurrency để throughput consumer thấp hơn ingress. Cách này mô phỏng downstream chậm và tránh tạo outage hoàn toàn.

**Cách C — Tạo burst ingest**

Tăng producer rate vượt consumer capacity trong thời gian ngắn. Sau burst, đưa producer về normal và đo drain.

Mỗi cách tạo ra profile backlog khác nhau. Ghi rõ cách nào được sử dụng và thời điểm bắt đầu/kết thúc.

### 9.2. Kiểm soát kích thước backlog

Ước lượng số record backlog:

\[
B_{records} = (\lambda_{in} - \mu_{out}) \times T
\]

Trong đó lambda in là tốc độ ingest records/s, mu out là tốc độ xử lý records/s trong thời gian tạo backlog, và T là thời gian tạo backlog tính bằng giây.

Nếu consumer dừng hoàn toàn, mu out bằng 0, do đó backlog xấp xỉ ingress rate nhân thời gian dừng.

Ví dụ producer ghi 20.000 records/s và consumer dừng 10 phút:

\[
B = 20{,}000 \times 600 = 12{,}000{,}000\ records
\]

Đây là ước lượng ban đầu. Phải đối chiếu log end offset, committed offset và record thực tế theo partition.

### 9.3. Ước lượng byte backlog

\[
B_{bytes} \approx B_{records} \times AverageRecordBytes
\]

Nếu có 12 triệu record, kích thước trung bình 1.5 KiB:

\[
B_{bytes} \approx 17.2\ GiB
\]

Con số thực trên disk còn phụ thuộc compression, replication factor, index và segment overhead. Cần bảo đảm retention và disk đủ chứa backlog cộng với traffic tiếp tục đến.

### 9.4. Phân bố backlog theo partition

Tổng lag có thể che giấu một partition nóng. Thu thập lag theo từng partition và tính:
- Partition lag lớn nhất.
- Median và p95 lag giữa các partition.
- Partition có record age cao nhất.
- Partition có leader hoặc replica bất thường.
- Consumer member đang sở hữu partition nào.

Nếu một key chiếm nhiều traffic, backlog có thể tập trung vào một partition. Thêm consumer instance không giải quyết được nếu partition count và key distribution không thay đổi.

## 10. Tính tốc độ drain và thời gian phục hồi

Đây là phần cốt lõi của backlog recovery test.

Gọi lambda là ingress rate hiện tại, mu là consumer processing rate trong giai đoạn drain và B là backlog tại thời điểm bắt đầu drain.

Để backlog giảm, phải có:

\[
\mu > \lambda
\]

Tốc độ drain thực là:

\[
DrainRate = \mu - \lambda
\]

Thời gian drain gần đúng:

\[
T_{drain} = \frac{B}{\mu - \lambda}
\]

Nếu mu nhỏ hơn hoặc bằng lambda, backlog không thể giảm trong khi producer tiếp tục ghi. Tăng consumer capacity hoặc giảm ingress là bắt buộc.

### 10.1. Ví dụ tính toán

Giả sử:
- Producer tiếp tục ghi 20.000 records/s.
- Consumer có thể xử lý 50.000 records/s.
- Backlog ban đầu là 12 triệu records.

Khi đó:

\[
DrainRate = 50{,}000 - 20{,}000 = 30{,}000\ records/s
\]

\[
T_{drain} = \frac{12{,}000{,}000}{30{,}000} = 400\ seconds
\]

Tức khoảng 6 phút 40 giây, chưa tính thời gian warm-up, rebalance, database throttling hoặc dao động throughput.

### 10.2. Công thức theo byte

Khi message size biến động, tính thêm theo byte:

\[
DrainBytesPerSecond = ConsumerBytesPerSecond - IngressBytesPerSecond
\]

\[
T_{drain} \approx \frac{BacklogBytes}{DrainBytesPerSecond}
\]

Sử dụng cả record rate và byte rate. Consumer có thể đạt records/s cao với message nhỏ nhưng không đạt khi payload lớn.

### 10.3. Ví dụ backlog không thể drain

Producer ghi 30.000 records/s, consumer xử lý 28.000 records/s:

\[
DrainRate = 28{,}000 - 30{,}000 = -2{,}000
\]

Backlog tiếp tục tăng 2.000 records mỗi giây. Dù consumer đã hoạt động trở lại, hệ thống chưa phục hồi.

Cần tăng processing capacity, giảm ingress có kiểm soát hoặc áp dụng backpressure ở producer. Không đánh dấu recovery thành công chỉ vì consumer group đã online.

### 10.4. Thời gian phục hồi end-to-end

Recovery time thực tế nên gồm:
1. Detection time: phát hiện consumer outage hoặc lag.
2. Decision time: xác định nguyên nhân và chọn hành động.
3. Restore time: khởi động consumer/dependency và hoàn tất rebalance.
4. Warm-up time: cache, connection pool và state store sẵn sàng.
5. Drain time: xử lý backlog.
6. Stabilization time: lag và record age trở về ngưỡng SLO.

Đo từng thành phần giúp biết cải thiện ở đâu. Chỉ đo từ lúc consumer process start sẽ bỏ qua thời gian phát hiện và xử lý incident.

## 11. Thực hiện backlog recovery test

### 11.1. Trạng thái ban đầu

Trước khi tạo backlog:
- Producer và consumer ở steady state.
- Lag gần baseline.
- Broker, ISR và KRaft quorum khỏe.
- Disk còn đủ dung lượng.
- Downstream database/service không có saturation.
- Event ID và sink reconciliation hoạt động.
- Đã ghi ingress rate và processing rate baseline.

### 11.2. Tạo backlog

1. Chọn topic và consumer group dành riêng cho test.
2. Ghi nhận committed offset và log end offset theo partition.
3. Dừng consumer hoặc giảm processing rate.
4. Tiếp tục producer ở tốc độ đã định.
5. Giữ thời gian tạo backlog theo test plan.
6. Theo dõi disk, retention, partition lag và oldest record age.
7. Dừng tạo backlog khi đạt mục tiêu hoặc chạm stop condition.

Không tạo backlog lớn hơn khả năng lưu trữ và retention. Nếu record hết retention trước khi consumer đọc, test có thể tạo data loss ngoài mục tiêu.

### 11.3. Khôi phục consumer

1. Khởi động consumer với cấu hình đã chọn.
2. Chờ group join và partition assignment hoàn tất.
3. Xác nhận consumer processing rate cao hơn ingress.
4. Theo dõi lag giảm theo từng partition.
5. Theo dõi processing latency và downstream saturation.
6. Kiểm tra retry/DLT rate và duplicate event.
7. Duy trì producer ở normal rate trong suốt quá trình drain.
8. Ghi thời điểm lag và record age trở về ngưỡng mục tiêu.

### 11.4. Kiểm tra ổn định sau drain

Sau khi backlog đã giảm:
- Giữ workload steady thêm một khoảng thời gian.
- Xác nhận lag không tăng trở lại.
- Xác nhận consumer group không rebalance liên tục.
- Kiểm tra sink count và event ID.
- Kiểm tra database connection pool và queue.
- Kiểm tra retry topic/DLT.
- Kiểm tra broker disk, ISR và request latency trở lại baseline.
- Ghi lại tài nguyên còn lại sau khi giảm consumer scale-up.

Recovery chỉ hoàn tất khi hệ thống trở lại steady state và dữ liệu được đối soát.

## 12. Kiểm thử failure và recovery

### 12.1. Consumer process failure

Kịch bản:
- Dừng một consumer instance khi group đang xử lý.
- Quan sát rebalance và thời gian partition được gán lại.
- Khởi động instance lại.
- Kiểm tra offset commit và duplicate handling.
- Đo lag và time to recover.

Nếu consumer commit offset trước khi side effect hoàn tất, crash có thể gây mất xử lý. Nếu commit sau side effect, crash có thể tạo duplicate. Ứng dụng cần idempotency hoặc transaction strategy phù hợp.

### 12.2. Broker rolling restart

Kịch bản:
- Chọn một broker có partition replica.
- Thực hiện rolling restart theo runbook.
- Theo dõi leader election, ISR và producer retry.
- Kiểm tra consumer fetch latency và lag.
- Chờ replica catch-up trước bước tiếp theo.

Không restart nhiều broker cùng lúc trong bài test cơ bản. Đảm bảo topic replication factor và min ISR đủ chịu lỗi dự kiến.

### 12.3. Network degradation

Có thể mô phỏng latency hoặc packet loss trong môi trường test riêng:
- Producer-to-broker.
- Broker-to-broker replication.
- Consumer-to-broker.
- Consumer-to-database.

Đo request timeout, retry, reconnect và lag. Chỉ áp dụng fault injection khi có cách giới hạn phạm vi và khôi phục network ngay lập tức.

### 12.4. Downstream outage

Tạm dừng hoặc giới hạn database/service mà consumer phụ thuộc:
- Kiểm tra consumer có pause hoặc retry theo thiết kế không.
- Kiểm tra retry có tạo retry storm không.
- Kiểm tra thread pool và connection pool có bị cạn không.
- Kiểm tra DLQ có nhận đúng event lỗi không.
- Khi downstream hồi phục, đo drain rate và duplicate behavior.

### 12.5. Connect và Streams

Nếu hệ thống dùng Kafka Connect:
- Dừng một worker.
- Quan sát task rebalance.
- Khôi phục worker.
- Kiểm tra connector offsets và sink/source behavior.
- Đo thời gian task trở lại RUNNING.

Nếu dùng Kafka Streams:
- Dừng một instance.
- Theo dõi rebalance và state restore từ changelog.
- Kiểm tra local state, standby replica nếu có và processing lag.
- Xác nhận output không thiếu hoặc lặp ngoài semantics đã thiết kế.

## 13. Backpressure và giới hạn recovery

Tăng consumer concurrency không phải lúc nào cũng giúp. Consumer có thể bị giới hạn bởi:
- Partition count.
- Key skew.
- CPU và serialization.
- Database throughput.
- External API rate limit.
- Thread pool và connection pool.
- Network bandwidth.
- Broker fetch capacity.
- Garbage collection.
- Retry/DLT handling.

### 13.1. Khi nào tăng consumer instance?

Có thể tăng member khi:
- Có đủ partition để phân công.
- Consumer xử lý độc lập theo partition/key.
- Broker và downstream còn capacity.
- Rebalance overhead không vượt lợi ích.
- Mỗi instance có tài nguyên đủ để xử lý workload.

Không scale member vượt partition count với kỳ vọng mọi instance đều xử lý song song. Các member thừa có thể không được gán partition.

### 13.2. Khi nào tăng partition?

Tăng partition có thể tăng parallelism nhưng ảnh hưởng:
- Key-to-partition mapping nếu dùng default partitioner.
- Ordering theo key.
- Consumer group assignment.
- File descriptor, metadata và broker overhead.
- Rebalance và storage distribution.

Không tăng partition giữa một recovery incident nếu chưa đánh giá tác động. Đây có thể là thay đổi kiến trúc cần migration và kiểm thử riêng.

### 13.3. Giảm ingress hoặc áp dụng backpressure

Nếu consumer capacity không thể tăng đủ nhanh:
- Giảm producer rate hoặc điều tiết upstream.
- Dùng quota/rate limit theo client.
- Ưu tiên event quan trọng theo business policy.
- Tạm dừng batch job không thiết yếu.
- Tăng capacity downstream trước khi scale consumer.
- Đặt giới hạn retry để tránh retry storm.

Backpressure giúp hệ thống ổn định nhưng có thể làm upstream latency tăng. Cần định nghĩa rõ hành vi khi producer bị throttled.

## 14. Data integrity và ordering trong test

Throughput cao không có ý nghĩa nếu record bị mất hoặc xử lý sai.

### 14.1. Event ID và reconciliation

Mỗi event test nên có:
- Event ID duy nhất.
- Business key.
- Sequence number theo key nếu cần kiểm tra ordering.
- Producer timestamp.
- Payload checksum hoặc deterministic value.
- Test run ID.

Sau test, đối chiếu:
- Số event producer đã được broker acknowledge.
- Số event consumer đã xử lý thành công.
- Số event đang tồn tại trong retry/DLT.
- Số event duplicate.
- Số event thiếu.
- Event ID có sai thứ tự theo key không.

Không so sánh đơn giản tổng số record trong topic với số row database nếu sink có deduplication hoặc business filtering. Định nghĩa rõ expected transformation.

### 14.2. At-least-once và duplicate

Với at-least-once processing, consumer có thể xử lý lại record sau crash hoặc khi commit offset không đồng bộ với side effect. Test phải xác nhận downstream idempotency.

Có thể dùng unique constraint trên event ID, idempotency key hoặc inbox table tùy kiến trúc. Ghi nhận duplicate count và xác minh không tạo side effect lặp.

### 14.3. Ordering

Kafka bảo đảm thứ tự trong một partition. Test ordering cần:
- Dùng key cố định để event cùng key đi cùng partition.
- Gắn sequence number tăng dần theo key.
- Kiểm tra thứ tự ở consumer và sink.
- Kiểm tra retry/DLT có làm thay đổi thứ tự xử lý không.
- Kiểm tra parallel processing trong consumer application.

Không yêu cầu total ordering giữa các partition nếu kiến trúc không cung cấp guarantee đó.

## 15. Phân tích kết quả và tìm bottleneck

### 15.1. Producer bottleneck

Dấu hiệu:
- Producer CPU cao.
- Serialization hoặc compression tốn CPU.
- Buffer pool đầy, waiting threads tăng.
- Request queue time tăng ở producer.
- Network không bão hòa nhưng throughput thấp.

Kiểm tra serializer, batch, compression, thread count và generator capacity.

### 15.2. Broker/network bottleneck

Dấu hiệu:
- Broker CPU/network/disk gần saturation.
- Produce/Fetch request latency tăng.
- Request handler idle thấp.
- Replication fetcher lag hoặc ISR shrink.
- Cross-AZ traffic tăng.
- Producer retry và timeout tăng.

Kiểm tra partition distribution, broker capacity, disk IOPS/throughput, network path và replication traffic.

### 15.3. Consumer bottleneck

Dấu hiệu:
- Producer ổn định nhưng lag tăng.
- Consumer processing duration tăng.
- Poll rate thấp hoặc batch nhỏ.
- Consumer CPU hoặc downstream wait cao.
- Một partition lag lớn hơn phần còn lại.
- Rebalance thường xuyên.

Kiểm tra partition assignment, key skew, application thread pool, database và commit strategy.

### 15.4. Backlog không giảm

Nếu lag không giảm, đo riêng ingress và processing rate theo cùng đơn vị. Xác nhận consumer có thực sự xử lý record thành công hay chỉ poll rồi retry.

Kiểm tra:
- Consumer throughput có lớn hơn ingress không?
- Có partition bị stuck do poison message không?
- Retry policy có delay quá dài không?
- Downstream có rate limit không?
- Consumer có bị rebalance liên tục không?
- Commit offset có tiến triển không?
- Retention có xóa record trước khi xử lý không?

Không chỉ scale consumer khi poison message hoặc downstream failure là nguyên nhân.

## 16. Stop conditions và an toàn test

Đặt stop condition trước khi chạy:
- Offline partition xuất hiện.
- Controller quorum không khỏe.
- ISR xuống dưới durability threshold.
- Disk free space chạm ngưỡng an toàn.
- Broker CPU hoặc network duy trì saturation quá lâu.
- Producer error rate vượt giới hạn.
- Consumer lag vượt dung lượng/retention budget.
- Downstream database có nguy cơ ảnh hưởng workload khác.
- Test generator không còn kiểm soát được rate.
- Có dấu hiệu dữ liệu test đi vào topic production ngoài phạm vi.

Khi stop:
1. Dừng tăng tải.
2. Giảm producer về baseline hoặc ngừng theo runbook.
3. Khôi phục consumer/downstream.
4. Xác nhận broker và controller quorum.
5. Theo dõi backlog drain.
6. Đối soát event ID và dữ liệu.
7. Ghi lại thời điểm và nguyên nhân dừng.

Không xóa topic hoặc reset offset trong lúc điều tra nếu chưa lưu evidence cần thiết.

## 17. Báo cáo kết quả test

Một báo cáo hữu ích phải cho người đọc biết workload nào được chạy, điều kiện nào thay đổi và kết quả có đáp ứng SLO không.

### 17.1. Thông tin test

| Trường | Giá trị |
|---|---|
| Test run ID | |
| Kafka version | |
| Cluster topology | |
| Broker count / controller count | |
| Topic / partition count | |
| Replication factor / min ISR | |
| Producer client/version | |
| Consumer client/version | |
| JDK / Spring Kafka | |
| Message size distribution | |
| Compression / acks | |
| Generator count | |
| Test duration | |
| Downstream dependency | |

### 17.2. Kết quả theo phase

| Phase | Ingress records/s | Consumer records/s | p99 latency | Max lag | Error rate |
|---|---:|---:|---:|---:|---:|
| Baseline | | | | | |
| Ramp 25% | | | | | |
| Ramp 50% | | | | | |
| Ramp 75% | | | | | |
| Target steady | | | | | |
| Peak/burst | | | | | |
| Backlog drain | | | | | |
| Stabilization | | | | | |

### 17.3. Kết quả backlog recovery

Ghi rõ:
- Backlog records/bytes tại thời điểm bắt đầu drain.
- Ingress rate trong lúc drain.
- Consumer processing rate trong lúc drain.
- Drain rate ròng.
- Thời gian rebalance/warm-up.
- Thời gian lag về ngưỡng mục tiêu.
- Tuổi record cũ nhất.
- Duplicate/missing event count.
- Error/retry/DLT count.
- Resource usage trong lúc drain.
- Recovery time tổng thể.

### 17.4. Kết luận và hành động

Mỗi finding nên có:
- Triệu chứng và metric evidence.
- Nguyên nhân đã xác nhận hoặc giả thuyết cần kiểm tra.
- Ảnh hưởng tới SLO.
- Hành động khắc phục.
- Owner và deadline.
- Test lại cần chạy để xác nhận.

Không ghi “Kafka chậm” nếu chưa chỉ ra topic/partition, metric, thời điểm và workload tương ứng.

## 18. Lab thực hành

### Lab 1 — Baseline và ramp load

1. Tạo topic test với partition và replication factor phù hợp.
2. Chạy producer perf test ở mức thấp.
3. Chạy consumer perf test và kiểm tra lag.
4. Tăng throughput theo bậc.
5. Ghi p95/p99 latency, broker CPU/disk/network và consumer lag.
6. Xác định điểm bắt đầu saturation.

Kết quả cần nộp: bảng workload, dashboard và nhận xét bottleneck.

### Lab 2 — Soak test

1. Chọn workload steady đại diện.
2. Chạy liên tục ít nhất một chu kỳ test đã định.
3. Thu thập heap, GC, disk usage, file descriptor, connection và lag.
4. Đánh dấu thời điểm restart/rebalance/compaction.
5. So sánh metric đầu, giữa và cuối test.
6. Xác định trend tăng bất thường.

Kết quả cần nộp: time-series chart và danh sách degradation/leak được phát hiện.

### Lab 3 — Backlog recovery

1. Ghi ingress và consumer rate baseline.
2. Dừng consumer trong khoảng thời gian có kiểm soát.
3. Giữ producer tiếp tục ghi.
4. Ghi backlog records/bytes theo partition.
5. Khởi động consumer với concurrency ban đầu.
6. Đo drain rate và recovery time.
7. Tăng concurrency hoặc xử lý downstream nếu drain không đạt SLO.
8. Đối soát event ID, duplicate và ordering.

Kết quả cần nộp: phép tính dự báo và recovery time thực tế.

### Lab 4 — Consumer/downstream failure

1. Giữ producer ở normal rate.
2. Tạm dừng downstream hoặc giới hạn tốc độ database.
3. Quan sát consumer retry, pause, lag và DLT.
4. Khôi phục downstream.
5. Đo thời gian drain và kiểm tra duplicate.
6. Viết runbook xử lý poison message.

Kết quả cần nộp: timeline failure/recovery và đề xuất backpressure.

## 19. Anti-pattern thường gặp

- **Chỉ đo records/s:** bỏ qua message size, latency, error và data integrity.
- **Chạy benchmark trên broker host:** generator cạnh tranh tài nguyên với broker.
- **Tắt replication hoặc acks để tăng số đẹp:** kết quả không đại diện production semantics.
- **Chỉ dùng message nhỏ:** không mô phỏng network và disk pressure thực tế.
- **Dùng key phân bố đều trong khi production bị skew:** bỏ sót hot partition.
- **Tăng consumer vô hạn:** partition count hoặc downstream vẫn là bottleneck.
- **Đo lag tổng:** không thấy một partition bị stuck.
- **Chỉ kiểm tra consumer process online:** không chứng minh offset đang tiến triển.
- **Dừng producer khi drain backlog:** đánh giá thấp khả năng phục hồi khi traffic vẫn tiếp tục.
- **Không đối soát event ID:** có thể bỏ sót mất record hoặc duplicate.
- **Chạy soak test quá ngắn:** không quan sát retention, compaction hoặc leak.
- **Không có stop condition:** test gây ảnh hưởng đến cluster hoặc workload khác.
- **Không lưu cấu hình test:** không thể tái lập và so sánh kết quả.
- **Coi throughput trung bình là SLO:** tail latency và recovery time vẫn có thể thất bại.

## 20. Production checklist

### Trước test
- [ ] SLO và acceptance criteria được định nghĩa trước.
- [ ] Workload có message size, key distribution và peak profile đại diện.
- [ ] Cluster version, topology và topic config được ghi lại.
- [ ] Generator được tách khỏi broker host.
- [ ] Topic và dữ liệu test được cô lập.
- [ ] Clock và monitoring được xác minh.
- [ ] Stop condition và người điều phối được chỉ định.

### Load test
- [ ] Baseline thành công.
- [ ] Ramp-up theo bậc và có steady window.
- [ ] Peak/burst được đo.
- [ ] Producer acknowledged throughput và p99 latency được ghi lại.
- [ ] Consumer lag theo partition được theo dõi.
- [ ] Broker CPU, disk, network, GC và ISR được theo dõi.

### Soak test
- [ ] Workload ổn định trong thời lượng đã định.
- [ ] Heap sau GC và native memory được theo dõi.
- [ ] Disk growth và retention được kiểm tra.
- [ ] Connection/thread/file descriptor được theo dõi.
- [ ] Compaction, backup, batch và maintenance được quan sát nếu thuộc scope.
- [ ] Lag không drift tăng liên tục.

### Backlog recovery
- [ ] Backlog tạo ra có kiểm soát và nằm trong retention/capacity.
- [ ] Ingress rate và processing rate được đo cùng đơn vị.
- [ ] Drain rate lớn hơn 0 và đáp ứng mục tiêu.
- [ ] Lag và oldest record age trở về ngưỡng SLO.
- [ ] Consumer rebalance và downstream saturation được theo dõi.
- [ ] Duplicate, missing event và ordering được đối soát.
- [ ] Steady state được xác nhận sau drain.

### Sau test
- [ ] Kết quả, config và metric evidence được lưu.
- [ ] Topic/test data được xử lý theo cleanup plan.
- [ ] Cluster trở về baseline.
- [ ] Finding có owner và action.
- [ ] Test có thể tái lập từ báo cáo.

## 21. Kết luận

Load test cho biết Kafka chịu được tải đến đâu; soak test cho biết hệ thống có duy trì ổn định lâu dài hay không; backlog recovery test chứng minh consumer group có thể bắt kịp dữ liệu sau gián đoạn trong khi producer tiếp tục hoạt động.

Điều kiện quan trọng nhất của backlog drain là processing rate phải lớn hơn ingress rate. Hãy tính trước drain time, đo theo từng partition, theo dõi tuổi record cũ nhất và đối soát dữ liệu bằng event ID. Nếu consumer chỉ vừa bằng hoặc thấp hơn tốc độ ingest, backlog sẽ không biến mất dù consumer process đã chạy.

Một bài test đạt yêu cầu cần chứng minh đồng thời throughput, tail latency, durability, data integrity, recovery time và resource headroom. Ghi lại workload và cấu hình đầy đủ để có thể lặp lại sau mỗi thay đổi Kafka, client, partition, broker hoặc downstream service.

## Tài liệu tham khảo

- Apache Kafka Documentation — Monitoring: https://kafka.apache.org/documentation/#monitoring
- Apache Kafka Operations — Basic Kafka Operations: https://kafka.apache.org/documentation/#basic_ops
- Apache Kafka Producer Configs: https://kafka.apache.org/documentation/#producerconfigs
- Apache Kafka Consumer Configs: https://kafka.apache.org/documentation/#consumerconfigs
- Apache Kafka Performance tools: https://kafka.apache.org/documentation/#perf
- Apache Kafka Connect Monitoring: https://kafka.apache.org/documentation/#connect_monitoring
- Apache Kafka Streams Monitoring: https://kafka.apache.org/documentation/#streams_monitoring
