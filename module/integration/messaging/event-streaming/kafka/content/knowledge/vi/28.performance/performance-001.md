# Xác định mục tiêu throughput, latency và giới hạn tài nguyên

## Mục tiêu

Tối ưu Kafka bắt đầu bằng việc xác định hệ thống cần phục vụ bao nhiêu sự kiện, trong thời gian bao lâu và với độ trễ nào. Một cluster có throughput trung bình cao vẫn có thể không đạt yêu cầu nếu latency p99 tăng mạnh vào giờ cao điểm, consumer lag không giảm sau burst hoặc broker cạn disk/network headroom.

Bài học này xây dựng cách đặt mục tiêu hiệu năng, mô tả workload, ước lượng tài nguyên, đo baseline, chạy benchmark và tìm nút thắt trước khi thay đổi cấu hình. Các ví dụ dùng Kafka 4.4 làm mốc tham chiếu; hãy kiểm tra config reference của đúng phiên bản broker/client đang chạy vì default và khả năng dynamic update có thể thay đổi.

Sau bài học, bạn có thể:

- Phân biệt throughput, latency, lag, saturation và headroom.
- Chuyển yêu cầu nghiệp vụ thành SLI/SLO có thể đo.
- Mô tả workload bằng record size, key distribution, partition, replication và processing cost.
- Ước lượng storage, network, CPU và mức song song cần thiết.
- Thiết lập benchmark producer/consumer có thể lặp lại.
- Điều chỉnh producer batching, compression, buffer và acknowledgement.
- Điều chỉnh consumer fetch, poll và concurrency.
- Đọc broker metrics để nhận biết CPU, disk, network, request queue và replication bottleneck.
- Chọn thay đổi theo số liệu và kiểm chứng tác động tới độ trễ, độ bền dữ liệu và chi phí.

## 1. Ba mục tiêu hiệu năng

### 1.1. Throughput

Throughput là lượng công việc hệ thống xử lý trong một đơn vị thời gian. Với Kafka, nên đo ít nhất:

- Records per second (records/s): số record được producer ghi hoặc consumer xử lý mỗi giây.
- Bytes per second (MiB/s hoặc GiB/s): lưu lượng dữ liệu thực tế.
- Throughput theo topic, partition, broker và toàn cluster.
- Throughput của từng consumer group và từng ứng dụng downstream.

Records/s và bytes/s bổ sung cho nhau. 100.000 record/s với record 100 byte có tải mạng rất khác 100.000 record/s với record 20 KiB. Luôn ghi kèm kích thước record và cách tính byte (trước hay sau compression).

Phân biệt:

- **Sustained throughput:** tốc độ duy trì trong thời gian đủ dài để disk, page cache, replication và consumer đều đi vào trạng thái ổn định.
- **Burst throughput:** tốc độ trong một khoảng ngắn khi có đợt traffic tăng.
- **Catch-up throughput:** tốc độ consumer cần đạt để xử lý backlog sau khi dependency phục hồi.

Một benchmark chạy 30 giây có thể đo được burst nhưng chưa chắc phản ánh khả năng duy trì trong vài giờ.

### 1.2. Latency

Latency là thời gian từ một mốc bắt đầu tới một mốc kết thúc. Cần định nghĩa rõ hai mốc đo:

| Loại latency | Điểm bắt đầu và kết thúc | Dùng để đánh giá |
|---|---|---|
| Producer send latency | Ứng dụng gọi send đến khi callback/future hoàn tất | Producer, broker acknowledgement và mạng |
| Broker request latency | Broker nhận request đến khi gửi response | Queue, xử lý request, replication và response |
| Consumer fetch latency | Client gửi fetch đến khi nhận dữ liệu | Fetch wait, batching và broker response |
| Processing latency | Consumer nhận record đến khi business handler hoàn tất | CPU, database/API downstream và code ứng dụng |
| End-to-end latency | Event được tạo tại nguồn đến khi side effect đích hoàn tất | Toàn bộ event pipeline |

Đừng dùng producer callback latency thay cho end-to-end latency. Producer có thể nhận ACK rất nhanh trong khi consumer đang lag nhiều phút.

Latency thường có phân phối lệch. Hãy theo dõi percentile:

- **p50:** trải nghiệm của record ở giữa phân phối.
- **p95:** 95% record có latency không vượt ngưỡng này.
- **p99:** phản ánh tail latency và các trường hợp chậm đáng kể.
- **p99.9:** hữu ích cho workload nhạy cảm, nhưng cần đủ mẫu và histogram tốt.

Average có thể che khuất một nhóm request rất chậm. Khi đặt SLO, thường dùng p95/p99 và error rate thay vì chỉ dùng trung bình.

### 1.3. Resource limit và headroom

Resource limit là giới hạn thực tế của CPU, RAM, disk, network, file descriptor, thread pool hoặc dependency bên ngoài. **Saturation** xảy ra khi một tài nguyên gần hoặc đã chạm giới hạn khiến queue tăng và latency phình ra.

**Headroom** là phần năng lực còn dự phòng khi tải tăng hoặc node gặp sự cố. Không thiết kế cluster chạy liên tục sát 100% CPU, network hoặc disk throughput; khi leader chuyển, replica phục hồi hoặc consumer catch up, tải có thể tăng đột ngột.

Các tài nguyên cần theo dõi:

| Tài nguyên | Dấu hiệu gần bão hòa | Hệ quả |
|---|---|---|
| CPU | CPU usage cao kéo dài, run queue tăng, throttling | Compression, TLS, request handler và ứng dụng chậm |
| Heap/GC | GC pause dài, allocation rate cao, heap pressure | Request latency tăng, process có thể mất liveness |
| RAM/page cache | Page cache bị thu hẹp, memory pressure, swap | Đọc log phải chờ disk, latency tăng |
| Disk | IOPS/throughput đạt trần, await/queue depth tăng | Produce, fetch và replica recovery chậm |
| Network | NIC gần line rate, retransmit/drop, socket queue | Broker response và replication bị trễ |
| Threads | Request queue tăng, idle percent giảm | Request chờ trước khi được xử lý |
| Dependency | Database/API pool cạn, timeout tăng | Consumer xử lý chậm và lag tăng |

## 2. Chuyển yêu cầu nghiệp vụ thành SLI/SLO

Không bắt đầu bằng câu “Kafka cần nhanh”. Hãy xác định workload và mức dịch vụ mong muốn.

Ví dụ một hệ thống nhận đơn hàng:

| Yêu cầu | SLI đo lường | Ví dụ SLO |
|---|---|---|
| Nhận event ổn định | Producer accepted records/s | Duy trì 20.000 records/s trong giờ cao điểm |
| Phản hồi nhanh | Producer send latency p99 | p99 dưới 100 ms trong workload chuẩn |
| Consumer xử lý kịp | End-to-end latency p99 | p99 từ lúc tạo event đến khi inventory cập nhật dưới 2 giây |
| Không tích backlog kéo dài | Consumer lag theo thời gian | Lag không tăng liên tục khi tải nằm trong profile đã cam kết |
| Phục hồi sau burst | Backlog drain time | Xử lý hết backlog 5 phút trong vòng 10 phút sau burst |
| Có khả năng chịu lỗi | Error rate và availability | Không mất event đã được xác nhận theo durability policy |

Các con số trên chỉ là ví dụ để minh họa cách viết SLO, không phải benchmark hay cam kết mặc định của Kafka. Mỗi hệ thống cần đo trên hạ tầng, payload và yêu cầu nghiệp vụ thật.

### 2.1. Xác định ranh giới SLO

Một SLO cần trả lời:

1. Đo trên topic, cluster hay toàn bộ pipeline?
2. Đo record được producer gửi, broker ACK hay side effect cuối cùng?
3. Có tính thời gian retry và thời gian chờ dependency không?
4. Tải được đo theo trung bình, peak hay burst?
5. SLO áp dụng khi một broker mất hay chỉ khi cluster khỏe mạnh?
6. Có loại trừ maintenance, replay hoặc backfill không?

Nếu không xác định ranh giới, hai nhóm có thể báo cáo hai latency khác nhau nhưng cùng gọi là “Kafka latency”.

### 2.2. Định nghĩa workload profile

Ghi lại ít nhất:

- Record size trung bình, p95 và lớn nhất.
- Records/s và bytes/s ở giờ bình thường, peak và burst.
- Số topic, partition/topic và replication factor.
- Phân phối key: đều, lệch, hot key hay nhiều key null.
- Tỷ lệ producer đồng bộ/bất đồng bộ.
- acks, idempotence, transaction và compression.
- Số consumer group, số member và processing cost mỗi record.
- Retention, compaction, replay và tốc độ catch-up.
- TLS/SASL, quota, schema serialization và interceptor có bật không.
- Tỷ lệ lỗi, retry, record lớn và downstream call.

Workload profile là điều kiện đầu vào cho benchmark. Benchmark dùng record 1 KiB, key phân phối đều và không có consumer sẽ không đại diện cho hệ thống thực nếu production dùng record 20 KiB, hot key, ba consumer group và TLS.

## 3. Ước lượng tài nguyên trước khi benchmark

Ước lượng không thay thế benchmark, nhưng giúp phát hiện cấu hình không khả thi và xác định giới hạn cần đo.

### 3.1. Lưu lượng dữ liệu

Nếu:

- R là số record mỗi giây.
- S là kích thước payload trung bình tính bằng byte.

Thì lưu lượng payload thô xấp xỉ:

\[
Ingress_{raw} = R \times S
\]

Ví dụ 20.000 records/s, mỗi record trung bình 2 KiB:

\[
20.000 \times 2.048 = 40.960.000\ bytes/s
\]

Tương đương khoảng 39,1 MiB/s payload thô trước overhead và compression.

Con số thực tế còn phụ thuộc record headers, key, batch framing, protocol overhead, compression ratio và phân phối kích thước record.

### 3.2. Ước lượng storage

Với:

- I là ingress byte/s sau khi chọn cách tính nhất quán.
- T là retention tính bằng giây.
- RF là replication factor.

Dung lượng dữ liệu logic cần giữ trên toàn cluster có thể ước lượng sơ bộ:

\[
Storage \approx I \times T \times RF
\]

Ví dụ 40 MiB/s, retention 3 ngày và replication factor 3:

\[
40 \times 86.400 \times 3 = 10.368.000\ MiB
\]

Tương đương khoảng 9,89 TiB dữ liệu logic nhân replication trên toàn cluster. Phép tính này chưa bao gồm index, segment, metadata, filesystem overhead, compaction, retention overlap, unclean shutdown, replica movement và headroom vận hành.

Nếu I là payload thô, công thức cho ước lượng dung lượng chưa nén. Hãy benchmark compression trên batch thực tế để ước lượng bytes lưu trên disk, không áp dụng một compression ratio giả định cho mọi topic. Với topic compacted, dung lượng còn phụ thuộc số key còn sống, tombstone retention và tốc độ log cleaner.

### 3.3. Ước lượng network

Network cần phục vụ nhiều luồng:

- Producer gửi record tới leader.
- Leader replicate record tới follower replicas.
- Consumer fetch dữ liệu từ broker.
- Broker/controller trao đổi metadata và điều phối.
- Replica reassignment, recovery và catch-up.

Replication factor 3 không có nghĩa mọi broker đều gửi ba bản sao tới mọi node. Tuy nhiên, khi leader nhận dữ liệu, follower replicas phải fetch dữ liệu đó; tổng lưu lượng inter-broker tăng theo số replica và phân bố leader/follower.

Consumer group thứ hai hoặc thứ ba đọc cùng topic sẽ tạo thêm egress traffic. Khi tính network, cộng cả replication traffic, consumer traffic, cross-rack/cross-zone transfer và traffic nền; kiểm tra từng NIC và từng rack thay vì chỉ nhìn tổng băng thông cluster.

### 3.4. Partition và khả năng song song

Partition là đơn vị song song quan trọng của Kafka. Một consumer group truyền thống không thể có nhiều consumer active xử lý cùng một partition tại cùng thời điểm.

Có thể ước lượng số partition ban đầu:

\[
P \geq \left\lceil\max\left(
\frac{RequiredThroughput}{MeasuredThroughputPerPartition},
RequiredConsumerParallelism
\right)\right\rceil
\]

Trong đó MeasuredThroughputPerPartition phải lấy từ benchmark với record size, replication, acks, compression và consumer behavior tương tự production. Công thức làm tròn P lên số nguyên tiếp theo; đây chỉ là mức khởi điểm để thử tải, không phải partition count tối ưu tự động.

Đây chỉ là ước lượng ban đầu. Partition quá nhiều làm tăng metadata, file handles, leader/replica management, recovery time và chi phí rebalance. Partition quá ít giới hạn parallelism và có thể tạo hot partition nếu key distribution lệch.

Kiểm tra key distribution:

- Key nào chiếm tỷ lệ record lớn?
- Có hot customer/order/device không?
- Partition có phân phối byte và record đều không?
- Có key null khiến producer dùng sticky partitioning; batch có phân phối đủ đều qua thời gian không?
- Có thể thay key hoặc tách workload theo topic không?

Đừng tăng partition chỉ để “tăng throughput” khi bottleneck thực tế là một hot key hoặc database downstream.

## 4. Thiết lập baseline và benchmark có thể lặp lại

Một benchmark có ích phải có thể chạy lại và so sánh trước/sau.

### 4.1. Chuẩn bị môi trường

Trước khi đo:

1. Dùng cluster có broker, disk, network và replication gần với production.
2. Tạo topic benchmark riêng, không ghi đè dữ liệu nghiệp vụ.
3. Cố định partition count, replication factor, min ISR và retention.
4. Ghi phiên bản Kafka, JVM, OS, filesystem và client.
5. Ghi lại producer/consumer configs và record schema.
6. Đồng bộ clock giữa các máy nếu đo end-to-end latency.
7. Kiểm tra cluster khỏe mạnh, ISR đủ và không có rebalance/reassignment ngoài kế hoạch.
8. Chạy warm-up trước khi lấy số liệu.

Nếu benchmark trên một broker với replication factor 1, không suy ra hiệu năng hoặc durability của cluster production có nhiều broker và RF=3.

### 4.2. Chạy producer performance test

Kafka phân phối công cụ kafka-producer-perf-test.sh để đo tốc độ ghi với record có kích thước cố định. Từ Kafka 4.2, các công cụ performance test có các option nhất quán hơn; ví dụ dưới đây dùng --bootstrap-server và --command-config theo CLI Kafka 4.4:

~~~bash
bin/kafka-producer-perf-test.sh \
  --bootstrap-server broker-1:9092 \
  --topic perf-events \
  --num-records 1000000 \
  --record-size 1024 \
  --throughput -1 \
  --command-config producer-perf.properties
~~~

Nội dung file producer-perf.properties:

~~~properties
acks=all
enable.idempotence=true
compression.type=lz4
batch.size=65536
linger.ms=5
~~~

Ví dụ này chạy không giới hạn rate ở phía test tool (throughput=-1) để tìm mức producer có thể đạt trong điều kiện đã chọn. Cần kiểm tra cú pháp và options của script trong đúng bản Kafka đang cài.

Chạy nhiều vòng với cùng điều kiện:

- Baseline với cấu hình mặc định phù hợp.
- Thay một biến như compression hoặc linger.
- So sánh records/s, MiB/s, average record size, request latency và broker resource.
- Lặp lại để tránh kết luận từ một lần chạy may mắn.

Perf test dùng record size cố định không thay thế benchmark với phân phối payload production. Công cụ này hữu ích để đo throughput và latency tổng hợp mà tool cung cấp; nếu cần p95/p99 theo record, hãy thu histogram từ ứng dụng/client hoặc tracing riêng vì average/max của một công cụ benchmark không thay thế percentile histogram.

Kafka 4.4 còn hỗ trợ các option producer performance test để kiểm soát key distribution như record-key-range, key-distribution (range hoặc random) và random-seed. Dùng chúng để tạo workload key lặp lại được hoặc mô phỏng phân phối key lệch; đừng chỉ benchmark với key phân phối đều nếu production có hot key.

### 4.3. Chạy consumer performance test

Ví dụ đo tốc độ đọc:

~~~bash
bin/kafka-consumer-perf-test.sh \
  --bootstrap-server broker-1:9092 \
  --topic perf-events \
  --num-records 1000000 \
  --command-config consumer-perf.properties
~~~

Nội dung file consumer-perf.properties:

~~~properties
group.id=perf-consumer
~~~

Trong Kafka 4.4, --messages đã được deprecated để thống nhất thành --num-records. Consumer perf test giúp đo khả năng fetch/deserialize ở workload đơn giản. Nó không bao gồm chi phí business handler, database, API call, commit policy hoặc serialization downstream. Muốn biết consumer application có theo kịp production hay không, cần benchmark end-to-end với handler thật hoặc workload mô phỏng sát thực tế.

### 4.4. Benchmark end-to-end

Với ứng dụng thực:

1. Tạo event có event ID và timestamp nguồn.
2. Producer ghi event với cấu hình production.
3. Consumer xử lý và ghi timestamp hoàn tất.
4. Tính end-to-end latency từ timestamp nguồn đến side effect.
5. Thu thập p50, p95, p99, throughput, error rate và consumer lag.
6. Chạy steady load, peak load và burst.
7. Thử khi một broker restart hoặc consumer bị rebalance nếu đó là tình huống SLO phải chịu được.

Đồng hồ giữa máy nguồn và máy consumer phải được đồng bộ; nếu clock skew lớn hơn latency đang đo, kết quả end-to-end không đáng tin cậy. Có thể đo duration bằng monotonic clock trong cùng process cho từng chặng, rồi truyền trace context để liên kết các span.

### 4.5. Ma trận thử nghiệm

| Lần thử | Thay đổi | Điều cần quan sát |
|---|---|---|
| A | Cấu hình baseline | Throughput, p99, CPU, disk, network |
| B | Tăng batch.size | Batch fullness, request rate, memory, p99 |
| C | Tăng linger.ms | Batch size, request rate, producer latency |
| D | Đổi compression codec | CPU, bytes trên wire/disk, throughput |
| E | Điều chỉnh fetch.min.bytes | Consumer throughput và fetch latency |
| F | Tăng partition/consumer | Parallelism, skew, broker overhead |
| G | Tăng replication factor hoặc bật acks=all | Durability, replication latency, network |
| H | Tăng processing cost | Consumer lag và catch-up rate |

Chỉ thay một biến hoặc một nhóm biến có quan hệ trực tiếp mỗi lần. Nếu đồng thời tăng batch, partition, thread, buffer và disk, bạn sẽ không biết thay đổi nào tạo ra kết quả.

## 5. Đọc throughput-latency curve

Khi tăng tải từ thấp lên cao, throughput thường tăng gần tuyến tính ở giai đoạn đầu. Đến một điểm, throughput bắt đầu tăng chậm trong khi latency tăng nhanh. Đây là vùng saturation knee.

~~~mermaid
flowchart LR
    A[Low load] --> B[Linear region]
    B --> C[Saturation knee]
    C --> D[Queue growth]
    D --> E[Latency spike / timeout]
~~~

Mục tiêu vận hành là chọn tải mục tiêu nằm dưới saturation knee với headroom đủ cho burst, failover và catch-up. Không chọn điểm cao nhất mà benchmark có thể đạt trong vài giây nếu latency p99 đã tăng mạnh hoặc error rate bắt đầu xuất hiện.

Một kết quả benchmark cần trình bày ít nhất:

| Chỉ số | Baseline | Candidate | Mục tiêu |
|---|---:|---:|---|
| Producer records/s | Đo thực tế | Đo thực tế | Đạt workload |
| Producer p99 | Đo thực tế | Đo thực tế | Không vượt SLO |
| Consumer records/s | Đo thực tế | Đo thực tế | Cao hơn ingress khi catch up |
| End-to-end p99 | Đo thực tế | Đo thực tế | Không vượt SLO |
| CPU broker | Đo thực tế | Đo thực tế | Còn headroom |
| Disk latency/queue | Đo thực tế | Đo thực tế | Không bão hòa |
| Network throughput | Đo thực tế | Đo thực tế | Không chạm NIC limit |
| Error/throttle rate | Đo thực tế | Đo thực tế | Không tăng bất thường |

Không so sánh throughput nếu điều kiện durability khác nhau. Ví dụ acks=1 và acks=all không phải hai cấu hình tương đương về guarantee.

## 6. Tối ưu producer

Producer hiệu quả thường gom nhiều record thành batch, nén theo batch và gửi nhiều request song song trong giới hạn an toàn.

### 6.1. Batching: batch.size và linger.ms

- batch.size là giới hạn kích thước batch theo partition. Batch lớn hơn có thể giảm số request và tăng hiệu quả compression, nhưng dùng thêm buffer memory.
- linger.ms là thời gian producer chờ thêm record để gom batch nếu batch chưa đầy.
- Batch được tạo riêng theo partition; nhiều partition hoạt động đồng thời cần nhiều batch buffer.

Trong Kafka 4.4, linger.ms mặc định là 5 ms; default đổi từ 0 lên 5 ms ở Kafka 4.0 vì batch lớn thường cải thiện hiệu suất với latency tương đương hoặc thấp hơn trong nhiều workload. Không áp dụng con số này như SLO; hãy đo với tốc độ event và số partition của ứng dụng.

Ví dụ cấu hình thử nghiệm:

~~~properties
batch.size=65536
linger.ms=5
buffer.memory=67108864
~~~

Nếu producer gửi record thưa, tăng linger có thể làm latency tăng mà batch vẫn nhỏ. Nếu producer có traffic dày trên nhiều partition, batch lớn hơn có thể giảm request rate. Theo dõi batch-size-avg, records-per-request-avg và request rate để xác nhận.

### 6.2. Compression

Kafka producer nén toàn batch. Codec phổ biến:

| Codec | Đặc điểm |
|---|---|
| none | Không tốn CPU nén nhưng tốn network và disk hơn |
| gzip | Compression ratio thường tốt nhưng CPU cost cao hơn |
| snappy | Tập trung tốc độ nén/giải nén |
| lz4 | Thường có độ trễ thấp và throughput tốt |
| zstd | Có thể đạt compression ratio cao, tùy level và CPU |

Compression hiệu quả hơn khi batch có nhiều record tương tự. Hãy so sánh:

- CPU producer và broker.
- Bytes/s trên network.
- Disk write rate và storage footprint.
- Compression ratio thực tế.
- Producer/consumer latency.

Chọn codec theo tổng chi phí, không chỉ theo compression ratio. Nếu producer đã CPU-bound, codec nặng có thể làm throughput giảm dù network bytes giảm.

### 6.3. Acknowledgement và idempotence

Ví dụ cấu hình ưu tiên durability:

~~~properties
acks=all
enable.idempotence=true
max.in.flight.requests.per.connection=5
compression.type=lz4
~~~

acks=all yêu cầu leader chờ các replica trong ISR theo semantics của Kafka. Kết hợp min.insync.replicas ở topic/broker để xác định số replica tối thiểu phải có trước khi write được chấp nhận.

Idempotent producer giúp tránh duplicate do retry của cùng producer session. Nó không loại bỏ duplicate do ứng dụng gửi lại cùng business event trong một producer session mới hoặc do retry ở tầng nghiệp vụ. Dùng event ID/idempotency ở downstream nếu nghiệp vụ cần.

Kafka producer hiện đại bật idempotence mặc định nếu không có cấu hình xung đột. Khi bật rõ ràng, các ràng buộc quan trọng gồm acks=all, retries lớn hơn 0 và max.in.flight.requests.per.connection không vượt 5.

Không giảm acks hoặc tắt idempotence chỉ để tăng benchmark throughput nếu durability/ordering là yêu cầu của production.

### 6.4. Buffer và backpressure

buffer.memory là ngân sách buffer record chờ gửi. Đây không phải giới hạn cứng tổng memory của producer; compression và request in-flight có thể dùng thêm memory.

Khi producer gửi nhanh hơn tốc độ broker nhận, buffer đầy. send() có thể block tối đa max.block.ms rồi ném exception. Đây là backpressure có chủ đích, không nên che bằng cách tăng buffer vô hạn.

Theo dõi:

- buffer-available-bytes.
- bufferpool-wait-time.
- buffer-exhausted-rate và buffer-exhausted-total.
- waiting-threads.
- request latency và retry rate.

Nếu buffer cạn, hãy tìm nguyên nhân broker/network chậm hoặc producer quá tải trước khi tăng memory. Tăng buffer chỉ kéo dài thời gian trước khi ứng dụng chịu backpressure.

### 6.5. Gửi bất đồng bộ

Tránh gọi get() ngay sau từng send() nếu không cần đồng bộ từng record. Cách đó biến producer thành tuần tự và giảm batching/in-flight concurrency.

Ví dụ:

~~~java
ProducerRecord<String, String> record =
        new ProducerRecord<>("orders.v1", orderId, payload);

producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        metrics.recordSendFailure();
        logger.error("Kafka send failed for event {}", eventId, exception);
    } else {
        metrics.recordSendSuccess(metadata.topic(), metadata.partition());
    }
});
~~~

Callback cần ngắn và không thực hiện database/API call chậm. Nếu callback làm công việc nặng, chuyển sang executor có giới hạn và quản lý backpressure.

## 7. Tối ưu consumer

Consumer fetch theo batch và có thể lấy dữ liệu từ nhiều partition trong một request. Tối ưu fetch cần cân bằng throughput, latency, memory và thời gian xử lý trước lần poll tiếp theo.

### 7.1. fetch.min.bytes và fetch.max.wait.ms

- fetch.min.bytes: số byte tối thiểu broker nên trả về; nếu chưa đủ, broker có thể đợi thêm dữ liệu.
- fetch.max.wait.ms: thời gian tối đa broker chờ để đạt fetch.min.bytes trước khi trả response.

Default fetch.min.bytes=1 và fetch.max.wait.ms=500 ưu tiên trả dữ liệu sớm khi có record, nhưng server có thể đợi tối đa thời gian fetch wait nếu chưa đạt fetch.min.bytes. fetch.max.wait.ms áp dụng cho local log fetch; remote fetch có cấu hình wait riêng. Tăng fetch.min.bytes có thể tăng throughput khi traffic dày nhưng tăng latency khi traffic thưa.

Ví dụ workload ưu tiên batch:

~~~properties
fetch.min.bytes=65536
fetch.max.wait.ms=50
~~~

Đây là điểm thử nghiệm, không phải cấu hình chung cho mọi consumer. Nếu consumer cần event gần realtime, tăng fetch wait có thể làm p99 end-to-end xấu đi.

### 7.2. Giới hạn kích thước fetch

- max.partition.fetch.bytes: lượng dữ liệu tối đa broker trả về cho mỗi partition trong fetch.
- fetch.max.bytes: giới hạn tổng dữ liệu cho một fetch request.
- max.poll.records: số record tối đa trả về trong một lần poll().

Trong Kafka 4.4, default max.partition.fetch.bytes là 1 MiB, fetch.max.bytes là 50 MiB và max.poll.records là 500. Fetch limit không phải hard cap tuyệt đối nếu batch đầu tiên cần được trả để consumer có thể tiến triển.

max.poll.records chỉ giới hạn số record được trả về trong một lần poll; nó không thay đổi underlying fetch behavior. Consumer có thể đã cache record từ fetch request trước và trả dần qua nhiều lần poll.

Nếu record batch lớn hơn per-partition fetch limit, cần kiểm tra cả broker/topic message.max.bytes hoặc max.message.bytes và khả năng memory của consumer. Không tăng giới hạn tùy tiện vì một record batch lớn có thể làm tăng peak memory.

### 7.3. Poll, xử lý và commit

Consumer phải gọi poll() đều đặn. Nếu business processing trong một batch quá lâu, consumer có thể vượt max.poll.interval.ms, bị xem là không còn tiến triển và dẫn tới rebalance.

Hướng xử lý:

- Giảm max.poll.records để giới hạn công việc mỗi batch.
- Tối ưu business handler và downstream pool.
- Dùng pause/resume khi cần kiểm soát partition đang bị nghẽn.
- Chỉ tăng max.poll.interval.ms sau khi hiểu thời gian xử lý p99 và tác động tới recovery.
- Nếu xử lý song song, giữ thứ tự commit offset theo partition; không commit vượt qua record chưa hoàn tất.

Không gọi commitSync() sau mỗi record nếu không cần guarantee đó; commit quá thường xuyên tạo thêm request và latency. Ngược lại, commit quá thưa làm tăng lượng record có thể phải xử lý lại sau crash. Chọn commit interval/batch theo durability và idempotency của consumer.

### 7.4. Consumer concurrency và partition

Trong consumer group truyền thống, số consumer active song song bị giới hạn bởi số partition được assign. Nếu topic có 8 partition và chạy 20 consumer member, một số member sẽ idle.

Tăng số partition có thể tăng parallelism nhưng cần đánh giá:

- Key ordering và partition mapping.
- Metadata, file handles và replica overhead.
- Rebalance duration.
- Khả năng xử lý của broker.
- Hot key và downstream contention.

Nếu consumer lag chỉ tăng ở một partition, tăng consumer count không giải quyết được hot partition. Kiểm tra key distribution, record processing time và downstream contention.

## 8. Tối ưu broker và hạ tầng

### 8.1. Disk và page cache

Kafka dựa nhiều vào filesystem page cache để phục vụ log reads. RAM dành cho page cache có thể quan trọng không kém heap JVM.

Các điểm cần kiểm tra:

- Disk latency, throughput, IOPS và queue depth.
- Có bị noisy neighbor hoặc volume throttling không?
- Dữ liệu log có nằm trên volume nhanh, ổn định không?
- Có đủ dung lượng cho retention, replica recovery và reassignment không?
- Có swap hoặc memory pressure làm giảm page cache không?
- Có đang flush đồng bộ quá thường xuyên do cấu hình hoặc workload không?

Không đặt log.flush.interval.ms rất thấp chỉ để cố tăng durability mà chưa hiểu fsync cost. Kafka dựa vào replication và OS page cache; durability cần được thiết kế bằng replication, acks, ISR, storage và failure model phù hợp. flush không thay thế replication.

### 8.2. CPU, network và thread pools

Broker có thread pools cho network request và I/O processing. Trong Kafka 4.4, các cấu hình phổ biến gồm:

- num.network.threads: thread nhận request từ network và gửi response; mỗi listener (trừ controller listener) có pool riêng.
- num.io.threads: thread xử lý request, có thể bao gồm disk I/O.
- num.replica.fetchers: số fetcher threads dùng cho replication.

Default không phải khuyến nghị sizing cho mọi cluster. Tăng thread có thể cải thiện parallelism khi pool thực sự là bottleneck, nhưng cũng tăng context switching, memory và CPU contention. Theo dõi request queue và idle percent trước khi điều chỉnh.

Kafka cho phép cập nhật động một số thread pool configs trong giới hạn nhất định của phiên bản. Đọc cột Update Mode trong broker config reference; không giả định mọi cấu hình đều dynamic hoặc thay đổi có hiệu lực ngay.

### 8.3. Replication và durability

Replication tăng độ bền dữ liệu nhưng tiêu thụ network, disk và CPU. Khi producer dùng acks=all, latency có thể phụ thuộc follower replication và ISR health.

Theo dõi:

- Under-replicated partitions.
- Under-min-ISR partitions.
- ISR shrink/expand.
- Replica fetch lag.
- Produce request remote time.
- Leader distribution giữa broker.

Không giảm replication factor hoặc min.insync.replicas chỉ để cải thiện benchmark. Nếu broker chậm vì replica fetcher hoặc network inter-broker, cần xử lý đúng bottleneck.

### 8.4. Compression ở broker và topic

Topic-level compression.type=producer giữ codec producer đã chọn; broker có thể được cấu hình để recompress theo codec topic. Recompression làm tăng CPU broker và có thể ảnh hưởng throughput. Chỉ thay đổi khi có lý do lưu trữ hoặc tương thích rõ ràng.

Đo compression ratio và CPU ở producer, broker và consumer. Codec tốt nhất phụ thuộc payload, batch size, hardware và tỷ lệ nén.

### 8.5. Quota và noisy neighbor

Quota theo user/client-id có thể giới hạn producer/consumer bandwidth hoặc request rate. Quota bảo vệ cluster khỏi một client chiếm hết tài nguyên nhưng có thể tạo throttle time.

Theo dõi throttle-time và byte-rate theo principal/client-id. Nếu chỉ một service bị chậm, kiểm tra quota trước khi tăng tài nguyên toàn cluster.

## 9. Đọc metrics để tìm bottleneck

Không tối ưu bằng cảm giác. Ghép metrics của client, broker, OS và dependency theo cùng một khoảng thời gian.

### 9.1. Producer metrics

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| record-send-rate | Tốc độ gửi record | Thấp hơn workload trong khi app vẫn tạo event |
| request-latency-avg / request-latency-max | Thời gian request producer | Tăng cùng broker/network saturation |
| batch-size-avg | Kích thước batch trung bình | Quá nhỏ so với batch.size khi traffic dày |
| records-per-request-avg | Số record mỗi request | Thấp có thể tạo nhiều request overhead |
| compression-rate-avg | Tỷ lệ kích thước batch đã nén trên kích thước trước nén | Giá trị thấp hơn thường biểu thị batch nén nhỏ hơn |
| buffer-available-bytes | Buffer còn trống | Giảm liên tục khi broker không theo kịp |
| bufferpool-wait-time | Thời gian chờ buffer | Tăng nghĩa là producer chịu backpressure |
| buffer-exhausted-rate | Tần suất cạn buffer | Tăng là dấu hiệu nghiêm trọng |
| waiting-threads | Số thread ứng dụng chờ buffer | Tăng khi buffer pool bị nghẽn |
| record-error-rate / retry rate | Lỗi và retry | Có thể do broker, network, timeout hoặc quota |

### 9.2. Consumer metrics

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| records-consumed-rate | Tốc độ nhận record | Thấp hơn producer ingress |
| bytes-consumed-rate | Tốc độ byte nhận | So với network và fetch batch |
| fetch-latency-avg / max | Latency fetch request | Cao có thể do broker hoặc fetch wait |
| fetch-size-avg | Kích thước fetch trung bình | Quá nhỏ khi traffic dày |
| records-lag-avg / records-lag-max | Lag trung bình/lớn nhất theo partition | Theo dõi xu hướng và phát hiện partition nóng |
| commit-latency-avg | Thời gian commit offset | Tăng khi coordinator/network chậm |
| poll-idle-ratio-avg | Tỷ lệ thời gian consumer idle giữa các poll | Giá trị thấp có thể cho thấy app bận xử lý |

Tên metric JMX có thể khác giữa client version và exporter. Dùng metric catalog của phiên bản đang chạy và kiểm tra MBean thực tế.

### 9.3. Broker request metrics

Request latency của broker có thể phân rã thành:

- RequestQueueTimeMs: thời gian request chờ trong queue.
- LocalTimeMs: thời gian broker xử lý request tại node.
- RemoteTimeMs: thời gian chờ remote/follower trong một số request như produce với acks=all.
- ResponseSendTimeMs: thời gian gửi response về client.
- TotalTimeMs: tổng thời gian request.

Một số pattern:

| Pattern | Khả năng cần kiểm tra |
|---|---|
| QueueTime tăng, LocalTime thấp | Request handler/network pool hoặc burst queue |
| LocalTime tăng, CPU cao | Serialization, compression, request processing hoặc CPU contention |
| RemoteTime tăng với produce acks=all | Follower lag, inter-broker network hoặc disk follower |
| ResponseSendTime tăng | Network egress, socket buffer hoặc client chậm đọc |
| Fetch latency tăng cùng disk await | Disk read/page cache pressure |
| Throttle time tăng | Quota đang áp dụng |

### 9.4. Broker idle metrics

Hai metric quan trọng:

- NetworkProcessorAvgIdlePercent: tỷ lệ thời gian network processor idle.
- RequestHandlerAvgIdlePercent: tỷ lệ thời gian request handler thread idle.

Nếu idle percent giảm kéo dài đồng thời queue và latency tăng, pool tương ứng có thể đang bão hòa. Không dùng một ngưỡng cố định cho mọi cluster; so sánh với baseline và các metric khác.

### 9.5. OS và JVM metrics

Quan sát:

- CPU user/system, run queue, CPU throttling.
- Disk read/write latency, utilization, queue depth và throughput.
- Network bytes, packet drop, retransmit, connection count.
- Heap used/committed, allocation rate, GC pause và safepoint.
- Page cache, swap, major page faults và memory pressure.
- File descriptors và socket backlog.

Nếu broker metrics bình thường nhưng end-to-end latency tăng, kiểm tra application thread pool, serialization, database/API downstream và network giữa các zone.

## 10. Chẩn đoán theo triệu chứng

### 10.1. Producer throughput thấp, CPU thấp

Kiểm tra:

1. linger.ms và batch size có khiến request quá nhỏ không?
2. Producer có gọi get() đồng bộ sau từng send không?
3. Có quá nhiều partition ít traffic khiến batch không đầy không?
4. Network latency hoặc quota có đang giới hạn không?
5. Producer có buffer wait hoặc retry không?
6. Broker có queue/remote time tăng không?

### 10.2. Producer throughput thấp, CPU cao

Kiểm tra compression codec/level, serializer, interceptor, TLS, garbage collection và record transformation. Thử codec khác trên cùng workload và so sánh CPU với network/disk savings.

### 10.3. Consumer lag tăng liên tục

Tính:

\[
LagGrowthRate = ProduceRate - ConsumeRate
\]

Nếu producer duy trì 30.000 records/s nhưng consumer chỉ xử lý 24.000 records/s, backlog tăng khoảng 6.000 records mỗi giây trong điều kiện đơn giản.

Kiểm tra partition nóng, processing time, downstream pool, commit behavior, rebalance và quota. Tăng consumer count chỉ có tác dụng nếu còn partition/task có thể phân phối và downstream còn capacity.

### 10.4. Latency p99 tăng nhưng throughput không đổi

Đây thường là dấu hiệu queueing hoặc tail latency ở một thành phần:

- Broker request queue hoặc disk latency tăng.
- Một partition/leader bị nóng.
- GC pause hoặc CPU throttling.
- Downstream dependency có latency tail cao.
- Retry/backoff tạo đuôi latency.
- Quota throttle.

Phân rã end-to-end trace theo producer, broker, fetch, processing và downstream để tìm chặng tăng.

### 10.5. Sau khi tăng partition, hiệu năng giảm

Kiểm tra:

- Metadata và leader count tăng.
- File descriptors và replica count tăng.
- Rebalance hoặc replica reassignment đang chạy.
- Key distribution không đều.
- Consumer concurrency vượt khả năng database/API.
- Partition nhỏ làm batch producer khó đầy hơn.

Tăng partition không phải lúc nào cũng tăng throughput.

## 11. Capacity planning cho burst và catch-up

### 11.1. Backlog trong burst

Nếu ingress rate lớn hơn consumer processing rate, backlog tăng:

\[
Backlog(t) = (IngressRate - ConsumeRate) \times t
\]

Ví dụ producer nhận 25.000 records/s trong 10 phút, consumer xử lý 20.000 records/s:

\[
(25.000 - 20.000) \times 600 = 3.000.000\ records
\]

Sau burst, nếu producer trở về 15.000 records/s và consumer có thể xử lý 25.000 records/s, tốc độ drain backlog là 10.000 records/s. Thời gian xử lý backlog:

\[
3.000.000 / 10.000 = 300\ seconds
\]

Tức khoảng 5 phút, giả sử không có giới hạn khác và processing rate ổn định.

### 11.2. Consumer catch-up

Consumer cần có capacity lớn hơn ingress trong giai đoạn drain:

\[
CatchUpRate = ConsumeRate - IngressRate
\]

Nếu catch-up rate bằng 0 hoặc âm, backlog không giảm. Nếu workload downstream không cho phép tăng concurrency, cần điều chỉnh SLO recovery hoặc giới hạn burst ở producer.

### 11.3. Node failure và headroom

Capacity planning cần kiểm tra cluster khi mất một broker:

- Leader partitions có được phân phối lại không?
- Network còn đủ để replica catch up không?
- Disk còn đủ để nhận replica và retention không?
- Consumer có bị rebalance đồng thời không?
- Controller quorum còn khỏe mạnh không?
- Broker còn lại có đủ CPU/network để nhận traffic không?

Đừng chỉ benchmark cluster ở trạng thái tất cả node khỏe mạnh nếu SLO yêu cầu chịu được một broker failure.

## 12. Quy trình tối ưu có kiểm soát

Thực hiện theo thứ tự:

1. **Định nghĩa SLO:** throughput, latency percentile, error rate, backlog và recovery time.
2. **Chụp workload:** record size, key distribution, partition, replication, acks, compression, consumer groups.
3. **Đo baseline:** client, broker, OS, disk, network và dependency.
4. **Xác định bottleneck:** CPU, disk, network, thread, partition skew hay downstream.
5. **Chọn một thay đổi:** chỉ thay một biến hoặc một nhóm biến có quan hệ trực tiếp.
6. **Chạy lại cùng benchmark:** giữ nguyên data shape và thời lượng.
7. **So sánh trade-off:** throughput, p99, error, durability, resource và chi phí.
8. **Canary production:** áp dụng trên phạm vi nhỏ, quan sát trước khi rollout rộng.
9. **Rollback:** có ngưỡng dừng và cấu hình cũ sẵn sàng.
10. **Ghi lại kết quả:** version, config diff, workload, thời điểm và số liệu.

### 12.1. Bảng quyết định nhanh

| Nút thắt đã xác nhận | Thử nghiệm có thể thực hiện | Rủi ro cần theo dõi |
|---|---|---|
| Batch nhỏ, request rate cao | Tăng linger/batch hoặc cải thiện async send | Producer p99 và buffer memory |
| Network bandwidth cao | Thử compression và kiểm tra consumer egress | CPU compression, consumer CPU |
| Producer buffer cạn | Tìm broker/network bottleneck, sau đó sizing buffer | Memory và thời gian backpressure |
| Consumer fetch batch nhỏ | Điều chỉnh fetch.min.bytes/wait và fetch limits | End-to-end latency và memory |
| Consumer processing chậm | Tối ưu handler, bounded concurrency, partition capacity | Ordering, database pool, rebalance |
| Broker request queue tăng | Kiểm tra network threads, client burst và connection pattern | Context switching, thread contention |
| Broker LocalTime tăng | Kiểm tra CPU, disk, compression và request workload | CPU/IO saturation |
| RemoteTime/replica lag tăng | Kiểm tra follower disk/network và replica fetchers | ISR shrink và durability |
| Một partition nóng | Kiểm tra key skew và partitioner strategy | Ordering và key migration |
| Quota throttle | Điều chỉnh quota theo capacity và fairness | Noisy neighbor, tenant isolation |

Không áp dụng bảng như công thức tự động. Mỗi thay đổi phải được kiểm chứng trên workload cụ thể và đúng version.

## 13. Những lỗi tối ưu thường gặp

- Chỉ đo records/s: bỏ qua kích thước payload và byte throughput.
- Chỉ nhìn average latency: không phát hiện p99/p99.9 tăng.
- Benchmark trên một broker: không đại diện replication và failover production.
- Tăng batch quá lớn: tăng memory và latency khi traffic thưa.
- Tăng buffer vô hạn: trì hoãn backpressure thay vì sửa bottleneck.
- Tắt compression: có thể làm network/disk trở thành bottleneck.
- Giảm acks hoặc replication: đổi durability lấy throughput mà không đánh giá rủi ro.
- Tăng partition liên tục: làm tăng overhead và có thể không giải quyết hot key.
- Tăng số consumer member vượt số partition: tạo member idle mà không tăng parallelism hữu ích.
- Tăng max.poll.interval để che handler chậm: kéo dài thời gian phát hiện consumer không tiến triển.
- Thay nhiều config cùng lúc: không biết biến nào tạo ra kết quả.
- Dùng benchmark ngắn: bỏ qua page cache, GC, compaction, retention và backlog dài hạn.
- Không ghi lại config/version: không thể tái lập hoặc rollback kết quả.

## 14. Bài thực hành và tự kiểm tra

### Thực hành A — Xác định SLO

1. Chọn một workload như order events hoặc telemetry.
2. Ghi records/s, bytes/s, record size p50/p95, peak và burst.
3. Đặt producer p99 và end-to-end p99.
4. Xác định consumer lag tối đa và backlog drain time.
5. Ghi durability policy: replication factor, min ISR, acks và idempotence.
6. Viết workload profile để nhóm khác có thể chạy lại benchmark.

### Thực hành B — Producer benchmark

1. Tạo topic perf-events với partition và replication factor đã định.
2. Chạy kafka-producer-perf-test.sh với record size cố định.
3. Ghi baseline records/s, MiB/s và broker resource.
4. Thử thay batch.size và linger.ms.
5. Thử lz4 và zstd trên cùng workload.
6. So sánh p99, CPU, network và disk.
7. Giữ lại cấu hình có trade-off phù hợp SLO thay vì chọn throughput cao nhất.

### Thực hành C — Consumer benchmark

1. Tạo đủ dữ liệu trên topic benchmark.
2. Chạy kafka-consumer-perf-test.sh và đo bytes/s, records/s.
3. Chạy consumer application có business handler mô phỏng.
4. Thử fetch.min.bytes và fetch.max.wait.ms.
5. Thử max.poll.records và số consumer member.
6. Quan sát lag theo từng partition và thời gian drain backlog.
7. Tạo một hot key để thấy tác động của partition skew.

### Thực hành D — Tìm bottleneck

1. Thu producer, consumer, broker JMX và OS metrics cùng thời điểm.
2. Tạo tải tăng dần từ thấp tới peak.
3. Quan sát thời điểm throughput không tăng nhưng p99 bắt đầu tăng.
4. Đối chiếu RequestQueueTimeMs, LocalTimeMs, RemoteTimeMs và ResponseSendTimeMs.
5. Kiểm tra CPU, disk latency, network và quota.
6. Đưa ra một giả thuyết bottleneck và một thay đổi kiểm chứng.
7. Chạy lại benchmark và ghi kết quả trước/sau.

### Câu hỏi tự kiểm tra

1. Throughput records/s khác bytes/s như thế nào?
2. Vì sao p99 có thể xấu dù average latency vẫn thấp?
3. SLO producer ACK có khác end-to-end SLO không?
4. Workload profile cần chứa những thuộc tính nào?
5. Công thức sơ bộ ước lượng storage có những biến nào và thiếu những overhead gì?
6. Vì sao replication factor làm tăng network và storage cost?
7. Làm thế nào ước lượng số partition ban đầu?
8. Vì sao hot key không được giải quyết chỉ bằng tăng consumer count?
9. batch.size và linger.ms ảnh hưởng throughput/latency ra sao?
10. Vì sao compression ratio cao chưa chắc là lựa chọn tốt nhất?
11. acks=all và idempotence bảo vệ điều gì?
12. max.poll.records có thay đổi underlying fetch behavior không?
13. Consumer lag tăng liên tục cho biết điều gì?
14. RequestQueueTimeMs và RemoteTimeMs giúp phân biệt bottleneck nào?
15. Vì sao benchmark cần chạy đủ lâu và giữ workload giống production?
16. Saturation knee là gì và nên chọn operating point ở đâu?

## Kết luận

Hiệu năng Kafka cần được quản lý bằng SLO và workload profile có thể đo. Throughput cho biết lượng dữ liệu xử lý, latency percentile phản ánh trải nghiệm và tail behavior, còn resource metrics cho thấy cluster còn headroom hay đang bão hòa. Hãy ước lượng storage/network/partition trước, đo baseline bằng benchmark lặp lại, sau đó điều chỉnh producer batching/compression, consumer fetch/poll và broker resource theo bottleneck đã xác nhận. Mọi tối ưu phải giữ đúng durability, ordering và recovery requirement; cấu hình nhanh nhất trong một bài test ngắn chưa chắc là cấu hình phù hợp cho production.

## Tài liệu tham khảo

- [Apache Kafka 4.4 — Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka 4.4 — Consumer and Share Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka 4.4 — Broker Configs](https://kafka.apache.org/44/configuration/broker-configs/)
- [Apache Kafka 4.4 — Monitoring](https://kafka.apache.org/44/operations/monitoring/)
- [Apache Kafka 4.4 — Hardware and OS](https://kafka.apache.org/44/operations/hardware-and-os/)
- [Apache Kafka 4.4 — Basic Kafka Operations](https://kafka.apache.org/44/operations/basic-kafka-operations/)
- [Apache Kafka 4.4 — Upgrade Guide](https://kafka.apache.org/44/getting-started/upgrade/)
