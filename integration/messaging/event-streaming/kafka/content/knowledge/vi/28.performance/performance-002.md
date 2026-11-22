# Thiết kế benchmark có tải nền, warmup và phân bố kích thước bản ghi

## Mục tiêu

Benchmark Kafka chỉ có ý nghĩa khi workload gần với cách hệ thống chạy thật. Một bài đo chỉ gửi record có kích thước cố định vào cluster đang rảnh có thể cho kết quả throughput rất cao, nhưng không phản ánh hệ thống khi consumer đang đọc, replication đang hoạt động, page cache chưa ổn định hoặc nhiều tenant cùng chia sẻ broker.

Bài học này hướng dẫn thiết kế benchmark có kiểm soát, gồm ba yếu tố thường bị bỏ qua:

- **Tải nền (background load):** mô phỏng traffic vốn đã tồn tại trước khi workload cần đo bắt đầu.
- **Warmup:** cho client, broker, JVM, connection, cache và state đạt trạng thái ổn định trước khi lấy số đo.
- **Phân bố kích thước record:** dùng nhiều kích thước và mức compressibility thay vì chỉ một payload cố định.

Sau bài học này, bạn có thể:

- Xác định câu hỏi benchmark, SLO và biến số cần kiểm soát.
- Tách thời gian warmup, ramp-up, measurement và cooldown.
- Tạo background load có thể lặp lại và đo được.
- Thiết kế record-size distribution phản ánh dữ liệu thực tế.
- Chọn producer/consumer settings và topology phù hợp cho từng thử nghiệm.
- Đo records/s, MiB/s, latency percentile, consumer lag và broker resource usage.
- So sánh kết quả giữa các lần chạy mà không bị nhiễu bởi cache, compaction hoặc traffic khác.
- Viết báo cáo benchmark có cấu hình, dữ liệu, điều kiện và giới hạn rõ ràng.

## 1. Benchmark phải trả lời một câu hỏi cụ thể

Benchmark không phải cuộc thi tìm ra một con số throughput lớn nhất. Trước khi chạy, hãy viết rõ câu hỏi cần trả lời và quyết định đo nào sẽ chứng minh câu trả lời.

Ví dụ câu hỏi tốt:

- Cluster 3 broker, replication factor 3 và `acks=all` duy trì được bao nhiêu MiB/s khi p99 produce latency phải dưới 50 ms?
- Consumer group có 12 partition có theo kịp 40.000 record/s khi payload p95 là 16 KiB không?
- Compression `lz4` giảm network egress bao nhiêu phần trăm và làm tăng CPU bao nhiêu so với `none`?
- Khi traffic nền chiếm 40% ngân sách ingress, tenant mới còn throughput và p99 latency bao nhiêu?
- Tăng producer instance từ 2 lên 4 có tăng throughput hay broker đã bão hòa disk/network?

Ví dụ câu hỏi chưa đủ rõ: “Kafka xử lý được bao nhiêu message?”. Kết quả phụ thuộc record size, compression, partition count, replication, acknowledgment, producer batching, consumer fetch, workload nền và yêu cầu latency.

### 1.1. Xác định loại benchmark

| Loại benchmark | Đo phần nào? | Kết quả chính |
|---|---|---|
| Producer throughput | Gửi record từ producer tới broker | Records/s, MiB/s, produce latency, throttle time |
| Consumer throughput | Đọc record từ broker | Records/s, MiB/s, fetch latency, lag drain rate |
| End-to-end | Từ lúc tạo event tới lúc consumer xử lý xong | End-to-end latency, throughput hoàn tất, lỗi/duplicate |
| Saturation | Tăng tải tới khi một tài nguyên trở thành bottleneck | Capacity knee, throughput tối đa ổn định, p99 degradation |
| Scalability | Thay đổi broker/client/partition/concurrency | Hiệu quả tăng trưởng khi thêm tài nguyên |
| Resilience under load | Đo khi broker/replica/client có sự cố | Recovery time, throughput dip, lag recovery |

Không gộp các loại benchmark thành một kết luận duy nhất. Producer throughput cao không chứng minh consumer xử lý kịp; consumer fetch nhanh không chứng minh end-to-end latency thấp.

### 1.2. Viết giả thuyết và tiêu chí đạt

Ví dụ:

```text
Câu hỏi: Với RF=3, acks=all và record-size distribution đã định nghĩa,
cluster có duy trì 25.000 records/s khi background load chiếm 30% ngân sách
producer ingress hay không?

Tiêu chí đạt:
- Throughput hoàn tất >= 25.000 records/s trong measurement window.
- Producer p99 latency < 60 ms.
- Consumer lag không tăng liên tục trong giai đoạn steady state.
- Không có record mất; duplicate nằm trong chính sách và được đo.
- Không có under-replicated partition kéo dài.
- CPU, disk và network không vượt ngưỡng vận hành đã thống nhất.
```

Tiêu chí phải định nghĩa trước khi chạy. Nếu sau khi thấy kết quả mới thay ngưỡng để kết luận đạt, benchmark mất giá trị so sánh.

## 2. Xác định workload trước khi cấu hình benchmark

Kafka lưu record trong partition log. Chi phí của một workload phụ thuộc không chỉ số record mà còn số byte, số partition, key distribution, batch size, replication và cách consumer xử lý.

Mô tả workload tối thiểu bằng các thông tin:

- Topic count và partition count.
- Replication factor, `min.insync.replicas` và `acks`.
- Record rate trung bình, peak rate và thời gian peak.
- Kích thước record p50/p95/p99 và tỷ lệ record lớn.
- Key cardinality, key skew và tỷ lệ record không có key.
- Payload compressibility và serializer/converter.
- Số producer, consumer group, consumer instance và concurrency.
- Retention, cleanup policy và consumer isolation level.
- Mức xử lý downstream: deserialize, validate, DB write, HTTP call hoặc state update.

Nếu production có nhiều loại event, hãy phân nhóm theo luồng nghiệp vụ và benchmark riêng trước khi chạy hỗn hợp. Một topic event nhỏ 500 byte và một topic payload lớn 100 KiB có thể có bottleneck hoàn toàn khác.

### 2.1. Phân biệt records/s và bytes/s

Hai workload cùng 10.000 records/s nhưng record trung bình 500 byte và 20 KiB có lượng dữ liệu khác nhau rất lớn.

\[
\text{MiB/s} = \frac{\text{records/s} \times \text{average record bytes}}{1024^2}
\]

Ví dụ:

| Workload | Records/s | Record trung bình | Payload rate xấp xỉ |
|---|---:|---:|---:|
| A | 10.000 | 500 B | 4,77 MiB/s |
| B | 10.000 | 20 KiB | 195,31 MiB/s |

Đây là payload rate trước khi xét protocol overhead, headers, compression và replication. Khi báo cáo, ghi cả records/s và MiB/s; nêu rõ byte rate tính theo payload, compressed request hay broker network bytes.

### 2.2. Phân biệt payload bytes, wire bytes và disk bytes

- **Payload bytes:** kích thước value/key trước khi producer batch/compress.
- **Wire bytes:** byte thực truyền trên network, có protocol overhead và ảnh hưởng compression.
- **Log bytes:** byte broker append vào log, phụ thuộc batch/compression và record format.
- **Replicated bytes:** lượng dữ liệu được truyền tới follower replicas.

Không lấy payload rate rồi nhân replication factor để khẳng định chính xác disk/network traffic. Compression, batch grouping, headers, protocol, fetch behavior và replication path làm thay đổi số liệu thực tế. Dùng broker/client metrics để đo từng lớp.

## 3. Thiết kế record-size distribution

Benchmark chỉ dùng một `record-size` cố định rất dễ tạo kết luận sai. Trong production, record thường có kích thước phân bố: nhiều event nhỏ, một số event trung bình và một tỷ lệ nhỏ payload lớn.

### 3.1. Vì sao kích thước record quan trọng?

Record size ảnh hưởng tới:

- Số record có thể chứa trong một producer batch.
- Compression ratio và CPU dùng để nén/giải nén.
- Số byte truyền qua network và ghi xuống disk.
- Consumer fetch size, memory pressure và thời gian xử lý từng poll.
- Request count nếu batch bị chia nhỏ.
- Tail latency khi một batch chứa record lớn.
- Khả năng chạm giới hạn `max.request.size`, `message.max.bytes`, `replica.fetch.max.bytes` hoặc `max.partition.fetch.bytes`.

Một producer gửi 10.000 record 1 KiB có thể gom được nhiều record trong mỗi batch. Producer gửi 10.000 record 256 KiB tạo lượng byte lớn hơn nhiều, batch có thể chỉ chứa một vài record và có thể chạm giới hạn request/message. Hai kết quả không thể so sánh chỉ bằng records/s.

### 3.2. Xây dựng distribution từ dữ liệu thật

Nếu có production telemetry, lấy histogram kích thước record từ producer hoặc pipeline quan sát. Có thể dùng các bucket:

| Bucket | Khoảng kích thước | Tỷ lệ ví dụ |
|---|---:|---:|
| XS | 0,1–0,5 KiB | 20% |
| S | 0,5–2 KiB | 45% |
| M | 2–8 KiB | 25% |
| L | 8–64 KiB | 8% |
| XL | 64–256 KiB | 2% |

Đây chỉ là distribution minh họa, không phải mặc định của Kafka hay khuyến nghị cho mọi ứng dụng. Hãy thay tỷ lệ bằng số đo thực tế và giữ cả tail lớn nếu nó xuất hiện trong production.

Nếu không thể lấy payload thật vì PII hoặc bí mật, tạo payload tổng hợp có cùng phân bố byte, cấu trúc JSON/Avro/Protobuf tương đương và entropy gần giống dữ liệu thật. Payload toàn ký tự lặp có thể nén tốt bất thường và làm benchmark đánh giá quá cao năng lực network/disk.

### 3.3. Kích thước không đủ; cần mô phỏng compressibility

Hai record cùng 8 KiB có thể có compression ratio rất khác:

- JSON có field name lặp lại thường nén tốt.
- Chuỗi ngẫu nhiên, UUID hoặc dữ liệu đã nén có thể khó nén.
- Binary payload có cấu trúc có thể nén tốt hoặc không tùy encoding.
- Header và key cũng có thể làm thay đổi batch compression.

Tạo ít nhất hai profile payload:

1. **Compressible:** cấu trúc lặp lại giống JSON event thực tế.
2. **Low-compressibility:** byte pattern đa dạng, gần với payload đã mã hóa/nén.

Ghi rõ seed và cách sinh payload để mỗi lần chạy có thể tái lập. Không dùng một payload giống hệt nhau cho mọi record nếu production có key, ID và field thay đổi làm compression ratio khác.

### 3.4. Giữ distribution ổn định giữa các lần chạy

Custom producer nên chọn bucket theo xác suất đã định nghĩa và sinh payload theo seed cố định hoặc seed được ghi vào report. Ví dụ pseudocode:

```java
int chooseSize(Random random) {
    double p = random.nextDouble();
    if (p < 0.20) return randomSize(random, 100, 512);
    if (p < 0.65) return randomSize(random, 513, 2048);
    if (p < 0.90) return randomSize(random, 2049, 8192);
    if (p < 0.98) return randomSize(random, 8193, 65536);
    return randomSize(random, 65537, 262144);
}
```

Pseudocode chỉ minh họa chọn kích thước; custom producer cần sinh value đúng kích thước byte sau serialization, không phải độ dài ký tự Java. Nếu dùng UTF-8, số ký tự có thể khác số byte. Cần đo `serializedKeySize`/`serializedValueSize` hoặc byte array thực tế để xác nhận distribution.

## 4. Key distribution và partition skew

Key quyết định partition routing theo partitioner. Nếu benchmark chỉ dùng key ngẫu nhiên, tải có thể phân bố đều hơn production. Nếu production có một số tenant hoặc aggregate rất lớn, key skew có thể khiến một partition leader quá tải trong khi các broker khác còn rảnh.

Hãy thử ít nhất ba profile:

| Profile | Cách tạo key | Mục tiêu |
|---|---|---|
| Uniform | Chọn ngẫu nhiên từ tập key lớn | Đo trường hợp phân bố tương đối đều |
| Realistic skew | Dùng histogram tenant/aggregate lấy từ production | Mô phỏng hotspot thực tế |
| Hot key | Một key chiếm tỷ lệ cao, ví dụ 10–30% | Kiểm tra partition hotspot và ordering constraint |

Không dùng key random nếu production cần ordering theo `orderId` hoặc `customerId`. Không dùng một key duy nhất nếu mục tiêu là đo throughput phân tán, trừ khi đó là workload cần kiểm thử.

Ghi partition count, partitioner, key cardinality, null-key ratio và phân bố record theo partition. Sau khi chạy, kiểm tra bytes/records per partition để phát hiện skew.

## 5. Tải nền: benchmark trong điều kiện cluster đang bận

Tải nền là traffic được duy trì độc lập với workload chính. Nó mô phỏng các producer/consumer vốn đã chạy trên cluster khi một workload mới bắt đầu hoặc khi batch job tăng tải.

Không nên tạo background load ngẫu nhiên không kiểm soát rồi dùng kết quả để so sánh cấu hình. Tải nền phải có profile, tốc độ mục tiêu, record-size distribution, key distribution, topic và consumer behavior được ghi lại.

### 5.1. Các thành phần của tải nền

Một cluster production thường có đồng thời:

- Producer realtime ghi vào nhiều topic.
- Consumer group realtime đọc và commit offset.
- Analytics consumer đọc lịch sử.
- Kafka Connect source/sink tasks.
- Kafka Streams application ghi changelog/repartition topic.
- Replication traffic giữa leader/follower.
- Compaction, retention delete và log segment rolling.
- Metadata/control-plane requests và health checks.

Không nhất thiết phải bật tất cả thành phần trong mỗi benchmark. Chọn những thành phần có ảnh hưởng trực tiếp đến câu hỏi cần trả lời. Ví dụ benchmark producer capacity nên có follower replication và consumer fetch tương tự production; benchmark consumer capacity cần có producer traffic ổn định để duy trì input.

### 5.2. Các mức background load

Có thể định nghĩa background load theo phần trăm ngân sách throughput đã đo trong baseline cluster:

| Scenario | Tải nền mục tiêu | Câu hỏi |
|---|---:|---|
| Idle baseline | 0% (không có workload ứng dụng khác) | Trần lý tưởng trong cluster rảnh |
| Low background | 20% | Ảnh hưởng khi traffic thường ngày thấp |
| Medium background | 40% | Workload mới có chịu được giờ hoạt động bình thường? |
| High background | 60% | Còn headroom bao nhiêu trước giờ peak? |
| Near saturation | 75–85% | Điểm gãy latency và throughput ở đâu? |

Các phần trăm là mức thử nghiệm minh họa. Hãy tính trên cùng đơn vị và cùng tài nguyên (producer ingress, consumer egress hoặc request-processing capacity). Không cộng producer MiB/s với consumer MiB/s rồi gọi tổng là phần trăm một capacity duy nhất.

### 5.3. Background load phải chạy độc lập

Tách client ID, topic và metric của background workload khỏi workload đo chính. Ví dụ:

```text
Benchmark producer:  bench-main-producer
Background producer: bench-background-producer
Benchmark consumer: bench-main-consumer
Background consumer: bench-background-consumer
```

Nếu cả hai workload dùng chung client ID, việc đọc throttle/latency theo client sẽ khó phân biệt. Nếu dùng chung topic, hãy ghi rõ partition/key distribution và tránh consumer test vô tình đọc dữ liệu của background producer.

### 5.4. Cố định profile tải nền

Background generator nên chạy theo một rate target cố định (records/s hoặc bytes/s), có cùng record distribution và key skew trong mọi lần chạy. Nếu background producer tự chạy unlimited, tổng tải thay đổi theo hiệu năng broker; như vậy khi so sánh hai cấu hình, workload nền không còn giống nhau.

Ghi lại:

- Target và actual records/s, MiB/s.
- Record-size distribution và compression.
- Topic/partition count và replication factor.
- Producer settings và consumer settings.
- Consumer lag/processing rate của background group.
- Broker CPU, disk, network và request handler utilization.

Nếu background workload không đạt target rate do quota hoặc broker saturation, đánh dấu run là không đạt điều kiện tải nền. Không dùng kết quả như thể mức background load mục tiêu đã được giữ ổn định.

## 6. Warmup: không đo ngay sau khi khởi động

Warmup là giai đoạn chạy workload trước khi bắt đầu measurement window. Mục đích là để các thành phần có thời gian đạt trạng thái đại diện cho steady state.

Các yếu tố có thể thay đổi mạnh trong những phút đầu:

- JVM JIT compilation và class loading.
- DNS lookup, TCP connection, TLS handshake và metadata discovery.
- Producer metadata cache, accumulator/batch formation và compression initialization.
- Broker page cache, filesystem cache và log segment access.
- Consumer assignment, fetch session và local processing cache.
- RocksDB/state store open, block cache và compaction của Kafka Streams.
- Connection pool của database/downstream service.
- Replica catch-up và consumer group rebalance sau khi scale client.

Nếu đo ngay sau khi start, benchmark có thể báo latency cao bất thường hoặc throughput thấp do startup. Ngược lại, nếu chỉ đo sau khi cache đã warm nhưng production thường xuyên cold-start, kết quả cũng không phản ánh tình huống thật. Cần ghi rõ đang đo cold-start, warm steady-state hay recovery.

### 6.1. Chia run thành các giai đoạn

Một run có thể chia thành:

```mermaid
flowchart LR
    A[Environment check] --> B[Warmup]
    B --> C[Ramp-up]
    C --> D[Measurement window]
    D --> E[Cooldown / drain]
    E --> F[Correctness and report]
```

| Giai đoạn | Mục đích | Có đưa vào kết quả chính? |
|---|---|---|
| Environment check | Xác minh broker/client/topic/config và metrics | Không |
| Warmup | Làm nóng JVM, connection, cache và pipeline | Không, trừ khi benchmark cold-start |
| Ramp-up | Tăng tải có kiểm soát tới target | Thường không |
| Measurement | Đo khi workload và tài nguyên ổn định | Có |
| Cooldown/drain | Dừng producer, chờ consumer hoàn tất backlog | Không, nhưng dùng để kiểm tra lag/correctness |
| Report | Tổng hợp metric, lỗi và điều kiện run | Có metadata và kết quả |

### 6.2. Warmup theo tiêu chí ổn định

Không có một thời lượng warmup cố định phù hợp cho mọi cluster. Có thể bắt đầu thử với 5–10 phút cho workload đơn giản, nhưng chỉ chuyển sang measurement khi các tín hiệu đã ổn định:

- Producer throughput gần target, không còn tăng dần do batch/cache startup.
- Producer p95/p99 latency không còn xu hướng giảm mạnh.
- Broker CPU, disk I/O và network đã đạt plateau tương đối.
- Consumer group đã hoàn tất assignment và lag không tăng bất thường.
- Background load đã đạt target rate.
- Không còn rebalance hoặc restore burst do startup (trừ khi đó là điều đang đo).

Nếu workload có stateful Kafka Streams, warmup có thể cần lâu hơn vì restore state. Nếu mục tiêu là đo cold-start/recovery, không loại warmup khỏi kết quả; đo riêng thời gian tới khi service đạt SLO.

### 6.3. Warmup không được ghi vào measurement window

Tạo marker thời gian rõ ràng khi bắt đầu measurement. Không trộn sample warmup vào histogram latency chính. Nếu dùng Prometheus/Grafana, thêm label hoặc annotation `phase=warmup`, `phase=measure` hoặc ghi timestamp bắt đầu/kết thúc để lọc đúng dữ liệu.

Không reset broker page cache giữa mỗi run trừ khi benchmark cold-cache là mục tiêu cụ thể. Nếu cần so sánh cold và warm cache, chạy hai kịch bản tách biệt và ghi rõ thao tác cache. Việc drop OS cache trên production hoặc cluster dùng chung có thể gây tác động lớn; chỉ thực hiện trong môi trường kiểm thử được kiểm soát.

## 7. Ramp-up và measurement window

Ramp-up tránh tạo một spike đột ngột lớn hơn nhiều so với cách workload thực tế tăng tải. Nó cũng giúp tìm capacity knee: điểm mà throughput không tăng tương ứng khi tăng offered load, trong khi latency và queue bắt đầu tăng nhanh.

Ví dụ ramp-up:

| Thời gian | Offered load |
|---|---:|
| 0–2 phút | 10% target |
| 2–4 phút | 25% target |
| 4–6 phút | 50% target |
| 6–8 phút | 75% target |
| 8–10 phút | 100% target |

Đây là profile minh họa. Với benchmark burst hoặc cold-start, ramp-up có thể không phù hợp; khi đó ghi rõ mục tiêu là đo spike response.

### 7.1. Chọn thời lượng measurement

Measurement window phải đủ dài để tránh một vài batch ngẫu nhiên chi phối kết quả. Thử nghiệm ban đầu có thể đo 5–15 phút sau warmup; workload có compaction, segment rolling hoặc stateful processing có thể cần lâu hơn để quan sát chu kỳ vận hành.

Đừng chọn window ngắn đến mức không thấy:

- Broker log segment rolling.
- Consumer lag tích lũy rồi drain.
- Compaction/retention background I/O.
- JVM GC cycle hoặc RocksDB compaction.
- Replication catch-up và ISR thay đổi.
- Tác động của batch/job chạy theo chu kỳ.

### 7.2. Lặp lại và thứ tự run

Chạy mỗi scenario nhiều lần (ví dụ ít nhất 3 lần) và báo median cùng min/max hoặc khoảng phân vị giữa các lần. Khi so sánh cấu hình A/B, luân phiên thứ tự chạy hoặc randomize order để tránh một cấu hình luôn được chạy trên cluster đã warm hơn.

Nếu cluster dùng chung, lên lịch run trong cửa sổ kiểm thử và ghi nhận traffic ngoài dự kiến. Nếu traffic nền không nằm trong kiểm soát, run cần được đánh dấu contaminated thay vì loại bỏ số liệu tùy ý.

## 8. Thiết kế test matrix

Không nên thay nhiều biến cùng lúc. Bắt đầu từ baseline rồi thay một nhóm biến để xác định nguyên nhân.

### 8.1. Ma trận tải nền và record size

Ví dụ ma trận cơ bản:

| Run | Background load | Record distribution | Compression | Mục tiêu |
|---|---:|---|---|---|
| B0 | 0% | Fixed 1 KiB | none | Baseline kỹ thuật |
| B1 | 0% | Realistic mixed | lz4 | Ảnh hưởng distribution/compression |
| B2 | 20% | Realistic mixed | lz4 | Tải nền thấp |
| B3 | 40% | Realistic mixed | lz4 | Tải nền trung bình |
| B4 | 60% | Realistic mixed | lz4 | Tải nền cao |
| B5 | 40% | Realistic mixed, low-compressibility | lz4 | Ảnh hưởng entropy |
| B6 | 40% | Realistic mixed | zstd | Trade-off CPU/network |

`B0` là baseline để hiểu cluster khi rảnh, không phải số liệu production. Khi so sánh B2–B6, giữ nguyên broker, partition, producer concurrency, consumer workload và thời lượng.

### 8.2. Ma trận producer/consumer

| Biến | Giá trị cần thử | Lưu ý |
|---|---|---|
| Producer count | 1, 2, 4, 8 | Tìm điểm tăng concurrency không còn tăng throughput |
| `batch.size` | 16, 32, 64, 128 KiB | Tính cả memory per producer và batch fill ratio |
| `linger.ms` | 0, 5, 10, 20 ms | Latency/throughput trade-off |
| Compression | none, lz4, zstd, snappy | Dùng cùng payload distribution |
| `acks` | 1, all | Ghi rõ durability/ISR policy |
| Partition count | 3, 6, 12, 24 | Kiểm tra leader distribution và parallelism |
| Consumer concurrency | 1, 3, 6, 12 | Không vượt partition count trong consumer group truyền thống nếu muốn tất cả member active |

Không chạy toàn bộ Cartesian product nếu số scenario quá lớn. Chọn từng vòng thử nghiệm theo câu hỏi, sau đó mở rộng quanh vùng kết quả đáng chú ý.

### 8.3. Giữ cố định các yếu tố khác

Trong một phép so sánh, giữ nguyên:

- Kafka broker/client version.
- Broker count, hardware, JVM và OS.
- Topic config, partition count, replication factor.
- Producer/consumer serialization và security protocol.
- Payload distribution, key distribution và seed.
- Background workload và measurement duration.
- Retention/cleanup policy, quota và network path.

Nếu phải thay đổi một yếu tố để tránh lỗi (ví dụ tăng `max.request.size` cho record lớn), ghi rõ đó là một scenario khác; không gộp kết quả với baseline mà không giải thích.

## 9. Topic, partition và replication cho benchmark

### 9.1. Partition count

Partition count ảnh hưởng parallelism, leader placement, file handles, metadata và khả năng phân phối tải. Quá ít partition có thể làm producer/consumer không tận dụng được client concurrency. Quá nhiều partition tăng overhead metadata, open file, recovery và rebalance.

Chọn partition count gần với production trước khi benchmark capacity. Nếu đang tìm partition sizing, chạy một ma trận riêng và theo dõi per-partition throughput/skew.

### 9.2. Replication factor và acknowledgment

Benchmark với `replication.factor=1` và `acks=1` có thể cho throughput cao nhưng không đại diện cho cluster production có RF=3 và `acks=all`.

Ghi rõ:

- Replication factor.
- `min.insync.replicas`.
- Producer `acks`.
- `enable.idempotence`.
- ISR count và under-replicated partitions trong measurement window.
- Có broker/follower nào bị chậm hoặc restart không.

Nếu production cần durability, benchmark chính phải dùng policy durability tương đương. Có thể chạy benchmark RF=1 để đo trần kỹ thuật nhưng phải gắn nhãn riêng.

### 9.3. Topic cleanup policy và dữ liệu tồn đọng

Topic benchmark thường dùng `cleanup.policy=delete` với retention đủ dài cho test. Nếu production dùng compacted topic, cần chạy scenario riêng vì compaction làm thay đổi disk I/O và dữ liệu còn lại. Tránh để retention quá ngắn khiến record bị xóa trước khi consumer hoàn tất hoặc trước khi kiểm tra correctness.

Tạo topic riêng cho từng run hoặc dùng run ID trong key/value để phân biệt dữ liệu. Xóa topic ngay sau khi đo có thể tạo thêm controller/broker load; cleanup sau benchmark nên nằm ngoài measurement window.

## 10. Producer benchmark

Producer benchmark cần đo cả offered load (tốc độ ứng dụng muốn gửi) và achieved throughput (tốc độ broker thực sự chấp nhận). Nếu producer chạy unlimited, throughput có thể chỉ phản ánh giới hạn cao nhất trong điều kiện đó, không phản ánh latency ở một target rate xác định.

### 10.1. Cấu hình producer

Ví dụ cấu hình baseline:

```properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
client.id=bench-main-producer
acks=all
enable.idempotence=true
compression.type=lz4
batch.size=65536
linger.ms=5
buffer.memory=67108864
max.in.flight.requests.per.connection=5
delivery.timeout.ms=120000
request.timeout.ms=30000
```

Đây là điểm bắt đầu minh họa, không phải cấu hình tối ưu chung. Nếu đổi `batch.size` hoặc `linger.ms`, giữ nguyên distribution và offered load để so sánh. Với idempotence bật, kiểm tra các ràng buộc `acks`, retry và in-flight requests theo version Kafka client.

### 10.2. Built-in producer performance tool

`kafka-producer-perf-test.sh` hữu ích cho baseline với record size cố định:

```bash
bin/kafka-producer-perf-test.sh \
  --topic bench-producer-fixed \
  --num-records 5000000 \
  --record-size 1024 \
  --throughput 20000 \
  --producer-props \
    bootstrap.servers=localhost:9092 \
    acks=all \
    compression.type=lz4 \
    batch.size=65536 \
    linger.ms=5
```

Tool này phù hợp đo fixed-size record và offered rate cơ bản. Nó không tự tạo distribution nhiều kích thước theo histogram, key skew hoặc compressibility giống production. Muốn đo realistic mixed payload, dùng custom producer/harness có seed và log distribution thực tế.

### 10.3. Custom producer phải đo gì?

- Offered records/s và bytes/s.
- Successful send callbacks và failed sends.
- Produce latency p50/p95/p99/p99.9.
- Throttle time.
- Batch size/records per request nếu có metrics.
- Buffer pool wait/available bytes và record queue time.
- Retry/error rate.
- Actual serialized record-size histogram.

Latency producer cần xác định mốc đo: từ lúc gọi `send()` tới callback là ứng dụng quan sát send completion, bao gồm thời gian chờ accumulator/buffer, network và broker response. Nó không nhất thiết bằng thời điểm consumer xử lý xong.

## 11. Consumer benchmark

Consumer benchmark cần xác định đang đo fetch throughput hay business processing throughput. Consumer đọc record và bỏ qua payload có thể rất nhanh; consumer deserialize, validate, ghi database hoặc gọi service có throughput thấp hơn nhiều.

### 11.1. Cấu hình consumer

Ví dụ:

```properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
group.id=bench-main-consumer
client.id=bench-main-consumer-01
enable.auto.commit=false
auto.offset.reset=earliest
max.poll.records=500
fetch.min.bytes=1
fetch.max.wait.ms=100
max.partition.fetch.bytes=1048576
isolation.level=read_committed
```

Giữ `isolation.level` phù hợp với production. Nếu production dùng transactional producer và `read_committed`, benchmark consumer bằng `read_uncommitted` có thể đọc thêm aborted records và cho kết quả khác.

### 11.2. Built-in consumer performance tool

```bash
bin/kafka-consumer-perf-test.sh \
  --bootstrap-server localhost:9092 \
  --topic bench-producer-fixed \
  --messages 5000000 \
  --group bench-consumer-perf
```

Kiểm tra `--help` của đúng Kafka distribution vì các tùy chọn output/statistics có thể thay đổi theo phiên bản. Consumer performance tool phù hợp đo tốc độ fetch/consume cơ bản; nó không mô phỏng DB write, HTTP call hoặc business processing.

### 11.3. Consumer lag và drain test

Chạy producer trong một thời gian cố định rồi dừng producer. Đo thời gian consumer drain hết backlog. Ghi:

- Lag ban đầu khi producer dừng.
- Consumer records/s và MiB/s.
- Lag giảm theo thời gian.
- Thời gian tới khi lag bằng 0 hoặc đạt ngưỡng mục tiêu.
- Có rebalance, retry hoặc processing error trong lúc drain không.

Một consumer có throughput trung bình cao nhưng lag không giảm có thể đang nhận thêm dữ liệu, bị skew partition hoặc có một partition hotspot. Quan sát lag theo partition, không chỉ tổng group lag.

## 12. End-to-end latency và correctness

End-to-end benchmark đo từ thời điểm event được tạo đến thời điểm business processing hoàn tất. Để đo đúng, event cần timestamp hoặc tracing context; clock giữa producer, broker và consumer phải được đồng bộ đủ tốt.

Ví dụ event envelope:

```json
{
  "eventId": "evt-000001",
  "occurredAt": "2026-11-20T10:00:00.000Z",
  "benchmarkRunId": "run-20261120-a",
  "payload": {
    "orderId": "ORD-1001",
    "status": "CREATED"
  }
}
```

Ghi thời điểm consumer hoàn tất side effect và tính latency theo cùng clock/time basis. Không dùng timestamp do broker append và business `occurredAt` thay thế nhau nếu mục tiêu khác nhau.

### 12.1. Dùng histogram, không chỉ average

Báo cáo tối thiểu:

- p50: trải nghiệm điển hình.
- p95: tail latency mà 5% record chậm hơn.
- p99: tail latency mà 1% record chậm hơn.
- p99.9 nếu volume đủ lớn để percentile có ý nghĩa.
- Max latency để tìm outlier, nhưng không dùng max làm chỉ số duy nhất.

Average có thể đẹp dù một phần nhỏ record bị chậm nhiều. Không tính p99 bằng cách lấy trung bình p99 của từng client/instance; cần merge histogram/sketch tương thích hoặc tính từ raw sample đủ đại diện.

### 12.2. Kiểm tra correctness

Benchmark throughput cao nhưng mất record hoặc tạo duplicate không được xem là thành công. Dùng event ID/sequence để đối chiếu:

- Số event đã tạo.
- Số event broker xác nhận.
- Số event consumer nhận.
- Số event business processing thành công.
- Duplicate count.
- Failed/retried/DLT count.
- Missing ID và sequence gap.

Nếu producer và consumer cùng chạy trong measurement window, đợi consumer drain rồi mới kết luận completeness. Nếu dùng transaction, kiểm tra committed/aborted records và `read_committed` semantics.

## 13. Broker và hệ thống cần quan sát

Benchmark phải thu metric từ producer, consumer, broker và host. Nếu chỉ lấy output của perf tool, bạn biết throughput nhưng khó biết bottleneck nằm ở đâu.

| Lớp | Chỉ số cần quan sát | Dùng để phát hiện |
|---|---|---|
| Producer | record-send-rate, byte-rate, request latency, throttle, buffer wait, retries | Producer bottleneck, quota hoặc buffer pressure |
| Consumer | records-consumed-rate, bytes-consumed-rate, fetch latency, lag, commit latency | Fetch bottleneck, processing chậm, lag tăng |
| Broker request | request handler idle, request queue time, request local/total time | Request processing saturation |
| Broker network | bytes in/out, network processor idle, connection count | Network saturation hoặc client connection storm |
| Broker storage | disk utilization, IOPS, await, log flush, page cache | Disk bottleneck hoặc cache miss |
| Replication | under-replicated partitions, ISR shrink, follower lag | Replication không theo kịp |
| JVM | heap, GC pause, allocation rate, thread count | GC hoặc CPU pressure |
| OS | CPU, memory, disk, network, context switch | Host resource contention |
| Downstream | DB latency/pool wait, HTTP latency/error, queue depth | Consumer processing bottleneck ngoài Kafka |

### 13.1. Broker metrics quan trọng

Tên MBean/metric phụ thuộc version, nhưng nhóm metric thường cần:

- Request handler idle percent.
- Network processor idle percent.
- Request queue time và local/total time theo request type.
- Bytes in/out và request rate.
- Under-replicated partitions, ISR shrink/expand.
- Replica fetcher lag và replication bytes in/out.
- Log flush latency và disk I/O.
- Active controller/quorum health nếu benchmark liên quan control-plane changes.

Đặt timestamp cho metric scrape và measurement window giống nhau để so sánh. Không lấy một ảnh chụp CPU tại cuối run rồi kết luận toàn bộ run không có CPU saturation.

### 13.2. Kiểm tra broker distribution

Kiểm tra leader distribution trước khi chạy. Nếu một broker giữ phần lớn leader partition, throughput tổng có thể bị giới hạn bởi broker đó dù tổng cluster còn tài nguyên.

Ghi records/bytes per partition và per broker. Nếu một partition có key hotspot, tăng producer count không giải quyết được bottleneck leader partition. Cần xem key distribution, partitioner và thiết kế aggregate.

## 14. Tính năng nền có thể làm nhiễu kết quả

Một số hoạt động broker chạy song song với benchmark:

- Log segment rolling và retention deletion.
- Log compaction.
- Replica fetch/catch-up.
- Partition reassignment.
- Leader election.
- Broker restart và page-cache cold start.
- Controller metadata changes.
- Background backup/snapshot hoặc host maintenance.

Không nhất thiết phải tắt các hoạt động này nếu production cũng có chúng. Thay vào đó, quyết định benchmark đang đo steady-state thông thường hay một tình huống vận hành cụ thể. Ghi nhận hoạt động nền và loại run khỏi so sánh nếu điều kiện không tương đương.

Nếu muốn benchmark compaction, reassignment hoặc broker failure, đó là scenario riêng có mục tiêu và tiêu chí riêng; không gộp vào baseline throughput.

## 15. Ví dụ kế hoạch benchmark hoàn chỉnh

Giả sử cần đánh giá cluster 3 broker cho event pipeline đơn hàng.

### 15.1. Environment

```text
Kafka version: ghi version thực tế
Broker: 3
Replication factor: 3
min.insync.replicas: 2
Producer acks: all
Idempotence: enabled
Topic: orders.bench
Partitions: 12
Cleanup policy: delete
Compression: lz4
Consumer isolation: read_committed
```

Không dùng các giá trị mẫu như cấu hình bắt buộc. Hãy ghi hardware, JVM, disk type, network, broker config, client version, TLS/SASL và quota thực tế của cluster.

### 15.2. Workload

```text
Main producer target: 20.000 records/s
Background producer target: 8.000 records/s
Main consumer: 6 instances, group riêng
Background consumer: 3 instances, group riêng
Record distribution: 20% XS, 45% S, 25% M, 8% L, 2% XL
Key distribution: realistic tenant/aggregate skew
Payload profile: compressible JSON-like
Warmup: tới khi metrics ổn định
Measurement: 10 phút
Cooldown: drain consumer lag về 0
Repeat: ít nhất 3 lần
```

### 15.3. Trình tự run

1. Xác nhận broker health, ISR, disk, network, topic và quota.
2. Tạo topic benchmark riêng, kiểm tra partition leader distribution.
3. Khởi động background producer/consumer và đợi đạt target.
4. Khởi động main producer/consumer.
5. Warmup tới khi throughput/latency/resource metrics ổn định.
6. Ramp-up main producer theo profile đã định nghĩa.
7. Đánh dấu measurement start và đo đủ 10 phút.
8. Dừng main producer, tiếp tục consumer để drain.
9. Xác nhận correctness và ghi lại lag cuối.
10. Dừng background load, lưu metrics và log.
11. Lặp lại theo cùng cấu hình; đổi scenario tiếp theo sau khi cluster trở về trạng thái nền.

### 15.4. Báo cáo kết quả

| Chỉ số | Kết quả cần điền |
|---|---|
| Main producer records/s | Số đo |
| Main producer MiB/s | Số đo |
| Producer p50/p95/p99 | Số đo |
| Background achieved rate | Số đo |
| Consumer records/s và MiB/s | Số đo |
| Consumer lag max/avg theo partition | Số đo |
| End-to-end p50/p95/p99 | Số đo |
| Broker CPU/network/disk peak | Số đo |
| Request handler/network processor idle | Số đo |
| Under-replicated partitions/ISR events | Số đo |
| Duplicate/missing/error count | Số đo |
| Drain time | Số đo |

Không điền số liệu giả định vào report. Lưu raw output, metrics export, config snapshot và run ID để người khác có thể tái lập.

## 16. Công cụ và harness

### 16.1. Kafka performance tools

- `kafka-producer-perf-test.sh`: baseline producer với record size cố định.
- `kafka-consumer-perf-test.sh`: baseline consumer/fetch throughput.
- `kafka-topics.sh`: kiểm tra topic, partition và config.
- `kafka-consumer-groups.sh`: kiểm tra group lag, members và offsets.
- JMX/Prometheus/Grafana: thu metric broker/client/host.

Các perf tool hữu ích để có baseline nhanh nhưng không thay custom harness khi cần payload distribution, key skew, application processing hoặc end-to-end tracing.

### 16.2. Custom Java producer

Custom producer cần:

- Sinh record size theo histogram mục tiêu.
- Sinh key theo profile uniform/skew/hot-key.
- Dùng serializer giống production.
- Giới hạn offered load theo records/s hoặc bytes/s.
- Gắn event ID và benchmark run ID.
- Đo send callback latency bằng histogram.
- Ghi error/retry/throttle và actual payload bytes.
- Dùng seed cố định để tái lập distribution.

### 16.3. Custom consumer

Custom consumer nên thực hiện cùng loại deserialize và business work như production. Nếu benchmark chỉ đo fetch, ghi rõ handler bỏ qua payload. Nếu đo end-to-end, ghi timestamp lúc tạo và lúc side effect hoàn tất, kiểm tra duplicate và commit policy.

Không dùng cùng consumer group cho nhiều scenario nếu committed offsets cũ làm thay đổi điểm bắt đầu. Dùng group ID riêng cho từng run hoặc reset theo quy trình có dry run trong môi trường test.

## 17. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Chỉ đo khi cluster rảnh | Không phản ánh cạnh tranh tài nguyên | Có scenario background load cố định |
| Đo ngay sau startup | JIT, connection và cache chưa ổn định | Tách warmup khỏi measurement |
| Chỉ dùng record 1 KiB | Không phản ánh tail record lớn | Dùng histogram size và payload entropy |
| Payload toàn byte lặp | Compression ratio quá tốt | Dùng compressible và low-compressibility profile |
| Chỉ báo records/s | Không thấy khác biệt byte volume | Báo thêm MiB/s và record size distribution |
| Chỉ báo average latency | Tail latency bị che khuất | Báo p50/p95/p99/p99.9 |
| Chạy producer unlimited | Không biết latency tại target rate | Có offered-rate scenario và saturation scenario riêng |
| Tắt replication để benchmark production | Throughput không đại diện durability policy | Dùng RF/acks/min ISR như production |
| Tăng partition và producer cùng lúc | Không xác định yếu tố tạo cải thiện | Thay từng nhóm biến có kiểm soát |
| Không kiểm tra key skew | Một partition có thể hotspot | Đo per-partition rate và realistic key distribution |
| Không đợi consumer drain | Bỏ sót record cuối hoặc lag còn tồn | Drain và kiểm tra completeness sau run |
| Gộp warmup vào histogram | Latency đầu run làm méo kết quả steady-state | Phase marker và measurement window riêng |
| Background generator tự chạy unlimited | Tải nền thay đổi theo cấu hình đang thử | Đặt target rate độc lập, xác nhận achieved rate |
| So sánh hai run khác broker/ISR state | Điều kiện không tương đương | Snapshot environment và đánh dấu contaminated run |

## 18. Checklist trước khi chạy benchmark

- [ ] Câu hỏi benchmark và tiêu chí đạt được viết rõ.
- [ ] Xác định producer, consumer, end-to-end hay saturation benchmark.
- [ ] Ghi Kafka version, broker count, hardware và client version.
- [ ] Ghi topic, partition, RF, min ISR, acks và cleanup policy.
- [ ] Record-size distribution lấy từ telemetry hoặc được định nghĩa rõ.
- [ ] Payload compressibility và serializer giống production hoặc có lý do khác biệt.
- [ ] Key distribution, cardinality, skew và partitioner được ghi lại.
- [ ] Background load có target rate, client ID, topic và profile độc lập.
- [ ] Warmup, ramp-up, measurement và cooldown có timestamp riêng.
- [ ] Measurement chỉ lấy sample trong phase đã định nghĩa.
- [ ] Producer/consumer settings được snapshot.
- [ ] Metrics producer, consumer, broker và host đã được thu.
- [ ] Có histogram latency và per-partition lag.
- [ ] Có kiểm tra event ID, duplicate, missing và sequence gap.
- [ ] Có ít nhất vài lần lặp và ghi median/range.
- [ ] Run contaminated hoặc không đạt background target được đánh dấu rõ.
- [ ] Raw output, dashboard export và config snapshot được lưu theo run ID.

## 19. Câu hỏi tự kiểm tra

1. Vì sao benchmark cần một câu hỏi và tiêu chí đạt trước khi chạy?
2. Records/s khác MiB/s ở điểm nào?
3. Payload bytes, wire bytes và disk bytes khác nhau như thế nào?
4. Vì sao record-size distribution quan trọng hơn một fixed record size trong workload thực tế?
5. Compressibility ảnh hưởng benchmark ra sao?
6. Key skew có thể làm một broker/partition quá tải như thế nào?
7. Background load nên được cố định bằng những thông số nào?
8. Vì sao không nên để background producer chạy unlimited khi so sánh A/B?
9. Warmup cần chờ những thành phần nào ổn định?
10. Khi nào warmup phải được tính vào kết quả thay vì loại bỏ?
11. Ramp-up giúp tìm capacity knee như thế nào?
12. Vì sao cần tách producer fetch throughput khỏi business processing throughput?
13. Những metric nào giúp tìm bottleneck broker?
14. Vì sao cần drain consumer và kiểm tra correctness sau measurement?
15. Cần ghi metadata nào để benchmark có thể tái lập?

## Tài liệu tham khảo

- [Apache Kafka — Performance](https://kafka.apache.org/documentation/#performance): nguyên tắc throughput, batching, compression và performance testing.
- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): batch size, linger, compression, buffer và request settings.
- [Apache Kafka — Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs): fetch size, poll records, isolation và consumer behavior.
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring): broker/client metrics và JMX.
- [Apache Kafka — Basic Operations](https://kafka.apache.org/documentation/#basic_ops): topic, partition, consumer group và các công cụ CLI.

> Benchmark đáng tin cậy phải giữ workload và điều kiện đo có thể lặp lại. Tải nền mô phỏng cạnh tranh tài nguyên, warmup tách startup khỏi steady-state, còn record-size/key distribution giúp kết quả phản ánh gần hơn dữ liệu production.
