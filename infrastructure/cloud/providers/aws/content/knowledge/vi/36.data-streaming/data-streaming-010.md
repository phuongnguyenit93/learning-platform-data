# Backpressure, replay và quan sát độ trễ xử lý streaming

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích backpressure, consumer lag, backlog và end-to-end latency trong pipeline streaming.
- Phân biệt overload ở producer, broker/stream, processor và sink.
- Thiết kế flow control bằng bounded buffer, rate limiting, batching, pause/resume và retry có backoff.
- Theo dõi Kinesis Data Streams bằng iterator age, throughput throttling và KCL metrics.
- Theo dõi Amazon MSK bằng offset lag, time lag, consumer group health và partition metrics.
- Phân tích Managed Service for Apache Flink bằng source lag, operator throughput, CPU/memory và checkpoint metrics.
- Theo dõi delivery freshness, retry và backup của Amazon Data Firehose.
- Thiết kế replay từ Kinesis retention, Kafka offsets, Flink checkpoints/snapshots và S3 archive.
- Bảo đảm replay an toàn bằng idempotency, deduplication, event identity và kiểm soát side effects.
- Xây dựng latency SLI/SLO, CloudWatch dashboards, alarms và runbooks có thể hành động.

## 1. Vì sao streaming cần backpressure và replay?

Một pipeline streaming nhận dữ liệu liên tục từ ứng dụng, thiết bị, log hoặc hệ thống giao dịch. Dữ liệu đi qua broker, processor rồi đến database, search index, data lake hoặc downstream API.

~~~mermaid
flowchart LR
    P["Producers"] --> S["Kinesis / MSK"]
    S --> F["Flink / Lambda consumers"]
    F --> Q["Enrichment / rules"]
    Q --> D["Database / S3 / OpenSearch"]
    D --> U["Dashboard / downstream apps"]
~~~

Trong điều kiện bình thường, tốc độ xử lý gần bằng tốc độ nhận dữ liệu. Khi traffic tăng hoặc một dependency chậm, dữ liệu chưa xử lý tích lũy. Consumer đọc chậm hơn producer, lag tăng, latency kéo dài và cuối cùng có thể chạm giới hạn retention.

Hai năng lực vận hành quan trọng:

- **Backpressure control:** điều tiết tốc độ để hệ thống không nhận hoặc giữ nhiều dữ liệu hơn mức có thể xử lý an toàn.
- **Replay:** đọc lại dữ liệu đã lưu để phục hồi sau lỗi, sửa logic xử lý hoặc tái tạo kết quả.

Backpressure giúp hệ thống sống sót khi tải tăng. Replay giúp phục hồi khi đã xảy ra lỗi hoặc cần xử lý lại dữ liệu. Cả hai cần observability; nếu không đo backlog và tuổi dữ liệu, đội vận hành không biết khi nào phải giảm tải, tăng capacity hoặc bắt đầu replay.

## 2. Phân biệt backpressure, lag và latency

| Khái niệm | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Backpressure | Downstream không tiêu thụ dữ liệu đủ nhanh, khiến upstream phải chậm lại | Operator hoặc sink nào đang làm nghẽn pipeline? |
| Consumer lag | Khoảng cách giữa vị trí dữ liệu mới nhất và vị trí consumer đã xử lý/commit | Consumer đang chậm bao nhiêu record hoặc bao nhiêu thời gian? |
| End-to-end latency | Thời gian từ lúc event phát sinh đến lúc kết quả được ghi nhận ở đích | Người dùng phải chờ bao lâu? |
| Backlog | Số lượng hoặc dung lượng dữ liệu đang chờ xử lý | Có bao nhiêu dữ liệu tồn đọng? |
| Throughput | Tốc độ dữ liệu đi qua một boundary | Hệ thống xử lý bao nhiêu record/byte mỗi giây? |
| Freshness | Độ mới của dữ liệu tại một điểm trong pipeline | Record cũ nhất chưa đến đích đã tồn tại bao lâu? |

Consumer lag không luôn tương đương latency. Kafka có thể có offset lag lớn nhưng record mới nhỏ; một số record có thể đã tồn tại lâu. Kinesis iterator age đo tuổi record cuối cùng consumer đọc được so với hiện tại, nhưng chưa phản ánh thời gian từ lúc event được tạo ở ứng dụng đến lúc sink commit.

Một hệ thống có thể có backpressure ở một operator nhưng chưa có end-to-end latency cao nếu buffer còn đủ. Ngược lại, sink có thể chậm sau khi consumer đã commit offset, khiến lag thấp nhưng dữ liệu chưa xuất hiện ở nơi người dùng truy vấn. Cần đo từng stage và cả hành trình end-to-end.

## 3. Backpressure hình thành như thế nào?

Backpressure xuất hiện khi tốc độ đầu vào lớn hơn khả năng xử lý ở một hoặc nhiều thành phần.

Giả sử producer tạo 80.000 records/giây, processor xử lý 70.000 records/giây và sink ghi được 60.000 records/giây. Sink là nút thắt. Pipeline end-to-end chỉ hoàn tất khoảng 60.000 records/giây. Nếu producer vẫn gửi 80.000 records/giây, backlog tăng khoảng 20.000 records/giây.

~~~mermaid
flowchart LR
    P["Producer<br/>80k records/s"] --> B["Broker / stream"]
    B --> W["Processor<br/>70k records/s"]
    W --> S["Sink<br/>60k records/s"]
    S -. "ACK chậm" .-> W
    W -. "Buffer đầy" .-> B
    B -. "Lag tăng" .-> P
~~~

Backlog thay đổi theo:

\[
\Delta B = \lambda_{in} - \lambda_{out}
\]

Trong đó B là backlog, λin là tốc độ record đi vào và λout là tốc độ record được xử lý, ghi thành công ở đích. Nếu λin lớn hơn λout, backlog tăng. Nếu λout lớn hơn λin, hệ thống có thể drain backlog.

Thời gian drain ước tính:

\[
T_{drain} \approx \frac{B}{\lambda_{out} - \lambda_{in}}
\]

Công thức chỉ có ý nghĩa khi throughput xử lý lớn hơn tốc độ nhận và tương đối ổn định.

### 3.1 Little's Law

Với hệ thống ổn định:

\[
L = \lambda W
\]

L là số item trung bình đang nằm trong hệ thống, λ là throughput trung bình, W là thời gian trung bình một item nằm trong hệ thống.

Ví dụ, pipeline xử lý 10.000 events/giây và có trung bình 50.000 events đang chờ hoặc đang xử lý. Thời gian lưu trung bình xấp xỉ 5 giây. Không dùng công thức này để dự báo khi tải tăng không giới hạn hoặc throughput biến động mạnh.

## 4. Xác định vị trí gây nghẽn

| Vị trí | Dấu hiệu | Nguyên nhân thường gặp |
|---|---|---|
| Producer | Retry/throttle tăng, send latency cao | Ghi quá nhanh, hot partition, broker thiếu capacity |
| Broker/stream | Write throttling hoặc request latency tăng | Shard/partition thiếu capacity, disk/network bão hòa |
| Consumer fetch | Poll/fetch chậm, read throttling | Chia sẻ throughput, quá nhiều consumers |
| Processor | CPU/busy time tăng, input lag tăng | Logic nặng, serialization, state lớn, skew |
| External dependency | Timeout, retry, connection pool cạn | Database, API hoặc search cluster chậm |
| Sink | ACK latency, delivery freshness và retry tăng | Destination hết capacity, batch không phù hợp |
| Checkpoint/state | Checkpoint kéo dài hoặc thất bại | State lớn, barrier alignment, storage chậm |

Không nên bắt đầu bằng cách tăng số worker. Nếu bottleneck là database, tăng consumer parallelism có thể làm database quá tải hơn. Nếu bottleneck là một partition nóng, thêm consumer không chia được một partition thành nhiều luồng độc lập.

## 5. Flow control ở từng boundary

### 5.1 Bounded buffer

Buffer phải có giới hạn. Unbounded queue có thể làm heap tăng đến OOM khi consumer chậm. Buffer hữu hạn giúp áp lực truyền ngược về upstream hoặc buộc producer giảm tốc.

Theo dõi số record, dung lượng bytes, thời gian nằm trong buffer và số lần buffer đầy.

### 5.2 Rate limiting và admission control

Rate limiter giới hạn tốc độ producer. Admission control có thể từ chối hoặc trì hoãn workload ít quan trọng khi hệ thống gần quá tải.

Các lựa chọn:

- Token bucket hoặc leaky bucket ở application gateway.
- Giới hạn concurrency ở consumer.
- Giới hạn tốc độ ghi vào database.
- Ưu tiên event critical và trì hoãn telemetry/batch ít quan trọng.
- Dùng queue để hấp thụ burst trong khoảng thời gian đã tính trước.

Không drop dữ liệu giao dịch chỉ để giữ latency thấp. Nếu phải drop, cần chính sách rõ về loại dữ liệu, audit và khả năng khôi phục.

### 5.3 Batching

Batching giảm số request và overhead. Batch quá nhỏ làm tăng request rate; batch quá lớn làm tăng latency, memory và phạm vi retry. Chọn batch theo payload size, processing time, API limits, latency SLO và transaction size của sink.

### 5.4 Retry có kiểm soát

Retry phù hợp với lỗi tạm thời như throttling, timeout hoặc network reset. Dùng exponential backoff và jitter để nhiều producer không retry cùng lúc.

\[
delay_n = random(0,\min(cap,base \times 2^n))
\]

Cần giới hạn attempts hoặc retry duration. Lỗi dữ liệu không hợp lệ, schema không hỗ trợ hoặc permission denied thường không tự biến mất sau retry; chuyển record sang quarantine/DLQ.

### 5.5 Pause và resume

Kafka consumer có thể pause partitions khi downstream đầy và resume khi capacity hồi phục. Consumer vẫn phải poll theo nhịp phù hợp để giữ membership và tránh rebalance do vượt max.poll.interval.ms.

Trong Flink, backpressure truyền qua network buffers từ downstream về upstream. Khi sink chậm, operator trước đó nhận ít buffer hơn và giảm tốc độ phát record. Đây là cơ chế bảo vệ pipeline, nhưng nếu kéo dài thì source lag tăng.

## 6. Backpressure với Amazon Kinesis Data Streams

Kinesis Data Streams lưu records theo shard. Producer ghi bằng PutRecord/PutRecords; consumer đọc bằng GetRecords hoặc Enhanced Fan-Out SubscribeToShard.

### 6.1 Producer-side throttling

Dấu hiệu gồm WriteProvisionedThroughputExceeded tăng, PutRecord/PutRecords latency tăng hoặc ProvisionedThroughputExceededException xuất hiện.

Nguyên nhân phổ biến:

- Số shard không đủ với write throughput.
- Partition key phân bố không đều, tạo hot shard.
- Một tenant/entity tạo phần lớn traffic.
- Burst ngắn vượt capacity.
- Producer retry quá nhanh làm tải tăng thêm.

Cách xử lý:

1. Phân tích throughput theo shard nếu đã bật enhanced shard-level metrics.
2. Kiểm tra partition key distribution.
3. Dùng partition key có cardinality và phân bố phù hợp.
4. Tăng shard count hoặc chuyển sang On-demand mode khi workload phù hợp.
5. Dùng retry có backoff và jitter.
6. Kiểm tra FailedRecordCount và lỗi từng record trong PutRecords; HTTP success không có nghĩa mọi record đều thành công.

### 6.2 Consumer-side throttling

Với shared-throughput consumer, nhiều consumers dùng chung read capacity của shard. Các lựa chọn:

- Tối ưu GetRecords batch size và thời gian xử lý.
- Tăng số shard nếu workload và key distribution cho phép.
- Dùng Enhanced Fan-Out (EFO) khi nhiều consumer cần throughput độc lập.
- Giảm consumers không cần thiết.
- Tách workload quan trọng sang stream riêng nếu cần isolation.

EFO cấp throughput đọc riêng lên tới 2 MB/giây cho mỗi shard trên mỗi consumer đã đăng ký và push records qua HTTP/2 SubscribeToShard. Shared throughput có tổng giới hạn đọc theo shard và consumers phải chia sẻ.

### 6.3 Kinesis và Lambda event source mapping

Khi Lambda đọc Kinesis, event source mapping poll stream và gửi batch đến function. Các cấu hình quan trọng:

- BatchSize và MaximumBatchingWindowInSeconds.
- ParallelizationFactor.
- MaximumRetryAttempts và MaximumRecordAgeInSeconds.
- BisectBatchOnFunctionError.
- FunctionResponseTypes với ReportBatchItemFailures.
- DestinationConfig cho records bị loại bỏ sau retry theo cấu hình.

Tăng parallelization có thể tăng concurrency nhưng cũng tăng áp lực lên database hoặc API downstream. Theo dõi Duration, Errors, Throttles và IteratorAgeMilliseconds cùng lúc. Đánh giá ordering semantics trước khi tăng xử lý song song.

## 7. Backpressure với Amazon MSK và Apache Kafka

Kafka chia topic thành partitions. Một consumer group xử lý mỗi partition bằng tối đa một consumer member tại một thời điểm. Số consumer active trong một group không thể vượt quá số partitions có dữ liệu cần xử lý.

### 7.1 Consumer lag

Offset lag là chênh lệch giữa offset mới nhất của partition và offset mà consumer group đã commit. Time lag ước lượng thời gian cần để drain offset lag theo tốc độ hiện tại.

| Metric MSK | Ý nghĩa |
|---|---|
| MaxOffsetLag | Lag lớn nhất giữa các partitions của topic |
| OffsetLag | Lag theo partition |
| SumOffsetLag | Tổng lag của các partitions |
| EstimatedTimeLag | Ước tính thời gian drain lag |
| EstimatedMaxTimeLag | Ước tính thời gian drain partition chậm nhất |
| RollingEstimatedTimeLagMax | Xu hướng maximum time lag trong cửa sổ rolling |

MSK consumer-lag metrics có điều kiện xuất hiện: consumer group cần ở trạng thái STABLE hoặc EMPTY; group phải có committed offsets; tên group không được chứa dấu hai chấm; dùng ký tự ASCII để CloudWatch dimensions được ghi nhận. Nếu metrics biến mất, kiểm tra rebalance/group state và offset commit trước khi kết luận consumer đã khỏe.

### 7.2 Consumer poll loop

Consumer cần gọi poll thường xuyên để nhận records và tham gia group protocol. Nếu xử lý một batch quá lâu trong cùng thread, consumer có thể vượt max.poll.interval.ms, bị xem là không còn hoạt động và gây rebalance.

Một pattern an toàn:

1. Poll records.
2. Đưa records vào bounded worker queue.
3. Worker xử lý và ghi sink.
4. Chỉ commit offsets sau khi xử lý/ghi sink thành công.
5. Pause partitions khi queue đầy.
6. Resume khi queue giảm.
7. Giữ poll loop hoạt động theo cấu hình phù hợp.

Commit offset trước khi sink ghi thành công có thể làm mất record sau crash. Commit sau sink nhưng crash trước commit có thể khiến record được xử lý lại. Vì vậy, idempotency và transaction semantics quan trọng hơn việc chỉ chọn auto-commit hay manual commit.

### 7.3 Tăng partitions và consumer parallelism

Thêm partitions có thể tăng parallelism, nhưng cần xem xét:

- Một consumer group không xử lý một partition đồng thời bằng nhiều consumers.
- Key ordering chỉ được đảm bảo trong partition.
- Thêm partitions có thể làm thay đổi mapping key-to-partition cho records mới.
- Hot key vẫn có thể tạo skew.
- Rebalance có thể tạm thời giảm throughput.
- Tăng partition count làm tăng metadata và vận hành.

### 7.4 Kafka pause/resume

Khi sink chậm, pause partitions phù hợp, giới hạn số records trong worker queue, giảm max.poll.records nếu batch quá lớn, dùng bounded executor và tránh retry blocking vô hạn trong poll thread.

## 8. Backpressure trong Managed Service for Apache Flink

Flink xử lý streaming theo operator graph. Mỗi operator nhận records, biến đổi và gửi kết quả sang operator kế tiếp. Khi downstream không xử lý kịp, network buffers dần đầy và backpressure truyền ngược upstream.

~~~mermaid
flowchart LR
    A["Source"] --> B["Parse"]
    B --> C["Enrich"]
    C --> D["Aggregate"]
    D --> E["Sink"]
    E -. "Sink chậm" .-> D
    D -. "Buffer đầy" .-> C
    C -. "Backpressure" .-> B
~~~

### 8.1 Xác định operator gây nghẽn

Một operator có thể bị nghẽn do:

- I/O đồng bộ gọi API ngoài.
- Một key có quá nhiều records.
- State lookup hoặc RocksDB quá nặng.
- Serialization/deserialization tốn CPU.
- Sink commit chậm.
- Checkpoint barrier phải chờ upstream.
- Một subtask có dữ liệu lớn hơn nhiều subtask khác.

Theo dõi throughput input/output theo operator, parallelism, CPU, container memory/disk, source lag và checkpoint duration.

### 8.2 Tối ưu operator

- Tăng parallelism cho operator có thể scale độc lập.
- Dùng async I/O cho external calls với giới hạn concurrency.
- Batch sink writes.
- Tránh gọi remote service tuần tự cho từng record.
- Giảm state không cần thiết và tối ưu state key.
- Xử lý hot keys bằng key salting hoặc tách workload nếu semantics cho phép.
- Đặt timeout cho external calls.
- Giới hạn in-flight requests để không làm downstream quá tải.

### 8.3 Metrics và phiên bản Flink

Managed Service for Apache Flink có metric backPressuredTimeMsPerSecond và busyTimeMsPerSecond trong tài liệu cho runtime Flink 1.13. Không nên giả định hai metric này có trên mọi runtime hiện hành.

Với runtime mới, dùng metrics được hỗ trợ theo phiên bản, ví dụ:

- records_lag_max cho Kafka source.
- millisbehindLatest cho Kinesis source.
- Operator.numRecordsInPerSecond và Operator.numRecordsOutPerSecond.
- cpuUtilization, containerCPUUtilization và containerMemoryUtilization.
- lastCheckpointDuration, lastCheckpointSize và numberOfFailedCheckpoints.
- numRestarts và state metrics theo runtime.

Flink 2.2 có thay đổi metric: fullRestarts bị loại bỏ và dùng numRestarts; uptime/downtime bị deprecated; một số connector metrics cũng thay đổi. Khi nâng runtime, rà soát CloudWatch alarms và dashboard.

## 9. Checkpoint, snapshot và replay trong Flink

| Cơ chế | Mục tiêu | Cách dùng |
|---|---|---|
| Checkpoint | Backup state định kỳ để phục hồi khi job lỗi | Flink tự tạo theo interval |
| Snapshot/Savepoint | Backup state do người dùng hoặc service trigger | Update, migration, rollback hoặc restore có chủ đích |
| Source offset state | Vị trí đã đọc trong Kinesis/Kafka | Được lưu cùng state trong checkpoint khi connector hỗ trợ |

Managed Service for Apache Flink dùng checkpoint để phục hồi sau sự cố. Snapshot giúp khởi động ứng dụng từ state đã lưu. Khi bật snapshot configuration, dịch vụ có thể tạo system snapshots trong update, scale hoặc stop để duy trì semantics theo tài liệu AWS.

Checkpoint không phải bản sao toàn bộ raw stream. Nó chứa state và source positions của ứng dụng. Nếu cần xử lý lại dữ liệu lịch sử từ đầu, cần thiết kế replay ở source và xác định cách khởi tạo state mới hoặc tương thích.

### 9.1 Checkpoint chậm tạo thêm lag

Checkpoint cần snapshot state, đồng bộ barriers và ghi state ra storage. Nếu checkpoint kéo dài, operator dành nhiều thời gian cho checkpoint, source tiếp tục tích lũy records và checkpoint tiếp theo có thể bị trì hoãn.

Theo dõi lastCheckpointDuration, lastCheckpointSize và numberOfFailedCheckpoints. Checkpoint quá thường xuyên tăng overhead; checkpoint quá thưa làm tăng lượng công việc cần khôi phục.

### 9.2 Exactly-once cần end-to-end design

Flink checkpointing có thể bảo toàn state và source positions, nhưng end-to-end exactly-once còn phụ thuộc sink. Sink phải hỗ trợ transactional commit hoặc idempotent writes. Nếu gọi external API không có idempotency, retry sau failure có thể tạo side effect trùng.

## 10. Backpressure và delivery trong Amazon Data Firehose

Amazon Data Firehose là dịch vụ delivery managed. Nó buffer records rồi giao đến S3, Redshift, OpenSearch, Splunk, HTTP endpoint và các destination được hỗ trợ.

Buffer lớn hơn thường tạo object/batch lớn hơn và giảm số request, nhưng làm tăng delivery latency. Buffer nhỏ giúp dữ liệu đến nhanh hơn nhưng tăng request/overhead.

Khi destination chậm hoặc lỗi:

- Firehose retry theo retry policy của destination.
- Data freshness tăng khi record cũ nhất chưa được giao.
- Delivery errors có thể xuất hiện trong CloudWatch Logs.
- Với DirectPut source, dữ liệu được giữ tối đa 24 giờ.
- Nếu source là Kinesis Data Streams hoặc MSK, khả năng retry phụ thuộc retention của source stream/topic.
- Cần cấu hình S3 backup cho failed records hoặc all records theo yêu cầu.

Không nên giả định S3 backup tự động chứa mọi record bị lỗi delivery. Backup behavior phụ thuộc destination, transformation và cấu hình backup mode.

### 10.1 Metrics cần theo dõi

- IncomingBytes và IncomingRecords.
- ThrottledRecords.
- DeliveryToS3.DataFreshness hoặc metric DataFreshness tương ứng với destination.
- Delivery success/failure metrics của OpenSearch, Redshift, Splunk hoặc HTTP endpoint.
- BackupToS3.DataFreshness khi bật backup all records.
- ActivePartitionsLimit và PartitionCountExceeded khi dùng dynamic partitioning.

DataFreshness là tuổi record cũ nhất trong Firehose. Nếu metric tăng liên tục, delivery đang tụt lại. Nếu metric không phát sinh, có thể stream không có incoming data hoặc delivery đang bị chặn; kiểm tra đồng thời incoming metrics và destination logs.

## 11. Replay là gì và khi nào cần?

Replay là đọc lại records đã lưu để tái tạo kết quả. Các tình huống:

- Consumer bị dừng lâu và cần xử lý backlog.
- Bug trong code đã tạo kết quả sai.
- Thay đổi schema hoặc enrichment logic.
- Tạo lại bảng analytics hoặc search index.
- Phục hồi sau sink outage.
- Điều tra sự cố hoặc đối soát dữ liệu.
- Chạy consumer mới cho use case mới.

Replay có thể đọc từ source stream, Kafka topic, S3 archive hoặc DLQ. Mỗi nguồn có giới hạn retention, ordering và semantics riêng.

### 11.1 Replay không phải retry

| Retry | Replay |
|---|---|
| Thử lại operation hoặc record thất bại | Đọc lại tập dữ liệu từ vị trí xác định |
| Thường diễn ra tự động | Thường là thao tác vận hành có chủ đích |
| Dùng backoff và retry policy | Dùng offset, sequence number, timestamp hoặc archive |
| Mục tiêu là hoàn tất lần xử lý hiện tại | Mục tiêu là tái xử lý hoặc tái tạo kết quả |

Replay phải có scope, start/end boundary, tốc độ, destination và chính sách dedup rõ ràng. Không replay toàn bộ production stream khi chưa xác định side effects.

## 12. Replay từ Amazon Kinesis Data Streams

Kinesis giữ records theo retention period:

- Mặc định 24 giờ.
- Có thể tăng tối đa 365 ngày.
- Retention trên 24 giờ phát sinh phí bổ sung.
- Tăng retention không khôi phục records đã hết hạn theo retention cũ.

Các starting positions:

| Position | Ý nghĩa |
|---|---|
| LATEST | Bắt đầu từ records mới đến sau thời điểm consumer bắt đầu |
| TRIM_HORIZON | Bắt đầu từ record cũ nhất còn trong retention |
| AT_TIMESTAMP | Bắt đầu từ thời điểm Unix timestamp chỉ định |
| AT_SEQUENCE_NUMBER | Bắt đầu tại sequence number cụ thể |
| AFTER_SEQUENCE_NUMBER | Bắt đầu sau sequence number cụ thể |

### 12.1 Replay bằng consumer mới

Cách an toàn để kiểm thử replay là tạo consumer application mới với checkpoint/lease namespace riêng. Consumer mới có thể đọc từ TRIM_HORIZON hoặc AT_TIMESTAMP trong phạm vi dữ liệu còn retention.

Nếu dùng KCL, checkpoint được lưu trong lease table. Việc đổi InitialPositionInStream không tự động ghi đè checkpoint đã tồn tại. Dùng application name/lease table mới cho replay hoặc thực hiện reset checkpoint theo runbook đã kiểm thử.

### 12.2 Replay có kiểm soát

- Chọn timestamp hoặc sequence boundary.
- Ghi nhận shard IDs và source retention.
- Đọc bằng consumer riêng.
- Giới hạn tốc độ replay để không làm sink quá tải.
- Ghi kết quả vào replay destination hoặc staging table.
- So sánh counts/checksums trước khi merge.
- Dùng event ID để deduplicate.
- Ghi audit log về thời điểm, owner và scope.

Nếu replay cùng stream vào production sink, cần phân biệt event replay với event realtime để không ghi đè dữ liệu mới hơn bằng kết quả cũ.

## 13. Replay từ Amazon MSK/Kafka

Kafka lưu records theo topic partitions và retention policy. Consumer group lưu committed offsets; replay thường thực hiện bằng cách bắt đầu từ offset cũ hơn.

Các lựa chọn reset offset:

- --to-earliest: bắt đầu từ offset sớm nhất còn giữ.
- --to-latest: bỏ qua backlog hiện tại và đọc từ cuối.
- --to-offset: bắt đầu từ offset cụ thể.
- --to-datetime: bắt đầu từ timestamp tương ứng.
- --shift-by: dịch chuyển offset theo số lượng record.

Ví dụ dry-run reset group về earliest:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server b-1.example.kafka.ap-southeast-1.amazonaws.com:9098 \
  --group orders-processor-replay \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Sau khi kiểm tra kết quả, chạy lại với --execute. Consumer group phải dừng hoặc không có consumer active trước khi reset offsets.

### 13.1 Dùng consumer group riêng

Với replay lớn, thường an toàn hơn khi tạo consumer group mới. Group mới có offset riêng và không làm thay đổi tiến độ của consumer production. Tuy nhiên, cần tính thêm broker read load và sink capacity.

### 13.2 Retention và log compaction

- Delete retention xóa segments theo thời gian hoặc dung lượng.
- Log compaction giữ giá trị mới nhất theo key và có thể loại bỏ record cũ hơn.
- Topic compacted không phải archive đầy đủ mọi sự kiện đã phát sinh.

Nếu cần replay toàn bộ lịch sử nghiệp vụ, hãy dùng topic retention phù hợp hoặc archive raw events sang S3 trước khi compaction làm mất phiên bản cũ.

## 14. Replay với Lambda event source mapping

Lambda có thể đọc Kinesis hoặc MSK thông qua event source mapping. Các cấu hình ảnh hưởng retry/replay gồm StartingPosition, MaximumRecordAgeInSeconds, MaximumRetryAttempts, BisectBatchOnFunctionError, FunctionResponseTypes, DestinationConfig và ParallelizationFactor.

Nếu retry vô hạn, record có thể tiếp tục được thử cho đến khi hết retention. Nếu đặt maximum record age hoặc attempts, records quá hạn có thể bị loại bỏ theo policy và gửi tới destination nếu cấu hình.

Không nên chỉ enable lại mapping rồi hy vọng nó đọc lại từ đầu. Starting position áp dụng lúc tạo mapping; mapping đã tồn tại có checkpoint tiến độ riêng. Hãy tạo mapping/consumer riêng hoặc làm theo quy trình reset đã kiểm thử.

## 15. Replay và phục hồi với Flink

Flink lưu state của operators và source offsets trong checkpoint/snapshot. Khi khởi động lại từ snapshot, ứng dụng tiếp tục từ state và source position đã lưu.

Ba mục tiêu khác nhau:

1. **Recover sau crash:** dùng checkpoint mới nhất để tiếp tục gần vị trí trước sự cố.
2. **Rollback code/config:** restore snapshot tương thích với version trước.
3. **Reprocess historical data:** đọc lại từ source offset/timestamp cũ và khởi tạo state theo logic replay.

Mục tiêu thứ ba cần thiết kế riêng. Nếu reset source offset nhưng giữ state aggregation cũ, kết quả có thể double-count. Nếu restore state cũ nhưng source offsets mới, có thể bỏ qua dữ liệu. Hãy phối hợp state snapshot, source position và sink transaction.

Trước khi replay:

- Xác định snapshot có tương thích operator UIDs và state schema không.
- Chọn source offsets/timestamp.
- Quyết định state bắt đầu từ rỗng hay restore.
- Dùng sink staging hoặc transactional sink.
- Kiểm tra duplicate và late events.
- Đo tốc độ replay và giới hạn tải production.
- Lập kế hoạch cutover từ replay output sang live output.

## 16. Dead-letter queue và quarantine

Poison record là record liên tục gây lỗi do payload, schema, business rule hoặc dependency. Nếu một record lỗi chặn cả partition/batch, throughput của records phía sau sẽ giảm.

Quy trình:

1. Xác định lỗi có thể retry hay không.
2. Nếu lỗi dữ liệu vĩnh viễn, chuyển record sang quarantine/DLQ.
3. Lưu payload gốc, event ID, source position, error code và timestamp.
4. Tiếp tục xử lý records khác nếu semantics cho phép.
5. Sửa dữ liệu hoặc consumer logic.
6. Replay DLQ qua pipeline có kiểm soát.
7. Theo dõi duplicate và xác nhận kết quả.

Không ghi toàn bộ payload nhạy cảm vào log. Quarantine bucket/queue cần encryption, retention, access control và audit.

### 16.1 Partial batch failure

Với Lambda Kinesis/SQS event source mappings, partial batch response cho phép function báo cụ thể item nào thất bại. Điều này tránh retry cả batch khi chỉ một record lỗi. Với Kinesis, cần chú ý ordering: một record thất bại có thể ảnh hưởng cách xử lý sequence numbers phía sau tùy cấu hình.

## 17. Định nghĩa latency cho streaming

Một event có thể mang các timestamp:

- eventCreatedAt: thời điểm nghiệp vụ phát sinh.
- producedAt: thời điểm producer gửi event.
- brokerIngestedAt: thời điểm stream/broker nhận record.
- consumerReceivedAt: thời điểm processor đọc record.
- processingStartedAt: thời điểm bắt đầu xử lý.
- processingCompletedAt: thời điểm logic hoàn tất.
- sinkCommittedAt: thời điểm đích xác nhận ghi.

| Latency | Công thức | Mục đích |
|---|---|---|
| Producer latency | producedAt - eventCreatedAt | Thời gian chuẩn bị/gửi từ ứng dụng |
| Ingestion latency | brokerIngestedAt - producedAt | Thời gian đưa dữ liệu vào broker |
| Queue/consumer lag age | consumerReceivedAt - brokerIngestedAt | Thời gian record chờ trước khi consumer đọc |
| Processing latency | processingCompletedAt - processingStartedAt | Thời gian xử lý logic |
| Sink latency | sinkCommittedAt - processingCompletedAt | Thời gian ghi/commit kết quả |
| End-to-end latency | sinkCommittedAt - eventCreatedAt | Thời gian từ nghiệp vụ đến kết quả |

Đồng bộ clock giữa hosts bằng NTP/chrony. Nếu clock lệch, phép trừ timestamp có thể âm hoặc sai. Với event-time processing, timestamp nghiệp vụ và watermark quan trọng hơn processing time.

## 18. Event time, processing time và watermark

- **Event time:** thời điểm sự kiện thực sự xảy ra trong hệ thống nguồn.
- **Ingestion time:** thời điểm sự kiện đi vào stream processor.
- **Processing time:** thời điểm processor thực thi logic.
- **Watermark:** ước lượng rằng hệ thống đã nhận phần lớn events có event time nhỏ hơn một mốc.

Watermark giúp xử lý out-of-order events và window aggregation. Watermark đi chậm có thể do source idle, partition chậm hoặc events đến trễ. Một window chưa phát kết quả không nhất thiết do CPU chậm; có thể do watermark chưa vượt qua window end.

Cần tách processing lag, event-time lag, late event rate và sink commit lag. Không dùng một metric lag duy nhất để đại diện mọi dạng latency.

## 19. Quan sát end-to-end pipeline

~~~mermaid
flowchart TD
    A["Producer metrics"] --> B["Broker metrics"]
    B --> C["Consumer lag"]
    C --> D["Processor metrics"]
    D --> E["Sink delivery metrics"]
    E --> F["Business freshness / E2E latency"]
    A -. "trace/event ID" .-> F
~~~

| Nhóm | Metrics cần theo dõi |
|---|---|
| Producer | Incoming records/bytes, send latency, errors, throttling, retry count |
| Broker/stream | Shard/partition utilization, request latency, write throttling, disk/network |
| Consumer | Iterator age, offset lag, time lag, records consumed, poll/fetch latency |
| Processor | Input/output records per second, processing duration, CPU, memory, busy/backpressured time nếu runtime hỗ trợ |
| State/checkpoint | Checkpoint duration/size, failed checkpoints, restart count |
| Sink | Write/ACK latency, retries, error rate, throttling, freshness |
| Business | Events created, events committed, duplicate count, missing event count, p95/p99 latency |

### 19.1 Event identity và correlation

Mỗi event nên có eventId duy nhất, eventType, schemaVersion, entityId/partition key, eventCreatedAt, producer name và correlationId/traceId.

Không đưa eventId, orderId hoặc customerId làm CloudWatch metric dimension nếu cardinality quá cao. Ghi chúng trong logs/traces; metrics nên dùng dimensions có cardinality kiểm soát như service, stream, topic, consumer group hoặc environment.

## 20. CloudWatch metrics cho Kinesis Data Streams

Kinesis gửi metrics trong namespace AWS/Kinesis. Stream-level metrics cơ bản được gửi mỗi phút; enhanced shard-level metrics cần bật và có thể phát sinh chi phí bổ sung. Dữ liệu metric tiêu chuẩn được giữ theo retention của CloudWatch metrics.

| Metric | Ý nghĩa | Cách dùng |
|---|---|---|
| GetRecords.IteratorAgeMilliseconds | Tuổi record cuối cùng được đọc trong GetRecords | Theo dõi consumer có tụt lại hay không |
| IteratorAgeMilliseconds | Shard-level iterator age | Tìm shard nóng hoặc consumer chậm |
| ReadProvisionedThroughputExceeded | Read throttling | Xác định thiếu read capacity |
| WriteProvisionedThroughputExceeded | Write throttling | Xác định thiếu write capacity |
| IncomingBytes / IncomingRecords | Dữ liệu producer gửi vào | Phát hiện burst và hot shard |
| OutgoingBytes / OutgoingRecords | Dữ liệu consumer đọc ra | Đo read throughput |
| GetRecords.Latency | Thời gian API GetRecords | Phát hiện read path chậm |
| SubscribeToShardEvent.MillisBehindLatest | Độ trễ của EFO consumer | Theo dõi consumer push |

AWS khuyến nghị alarm trên Maximum statistic của IteratorAgeMilliseconds. Khi iterator age vượt khoảng 50% retention period, xem đó là tín hiệu nguy cơ records hết hạn nếu consumer chưa bắt kịp. Ngưỡng cảnh báo thực tế nên thấp hơn nhiều tùy RPO và recovery time.

## 21. CloudWatch metrics cho MSK

MSK có broker metrics và consumer lag metrics. Monitoring levels chi tiết hơn có thể phát sinh chi phí. Dùng PER_TOPIC_PER_PARTITION khi cần điều tra lag theo partition; dùng mức mặc định cho vận hành tổng quát.

| Metric | Ý nghĩa |
|---|---|
| MaxOffsetLag | Lag lớn nhất của topic |
| OffsetLag | Lag theo partition |
| SumOffsetLag | Tổng backlog offsets |
| EstimatedTimeLag | Ước lượng thời gian drain |
| EstimatedMaxTimeLag | Thời gian drain partition chậm nhất |
| KafkaDataLogsDiskUsed | Disk usage |
| RequestTime | Thời gian broker xử lý request |
| TrafficShaping | Packet bị shape/drop/queue |

Consumer lag metrics không phải lúc nào cũng có. Khi group đang rebalance, không có committed offsets hoặc group name không hợp lệ cho CloudWatch dimensions, metrics có thể vắng mặt. Bổ sung client-side metrics và logs để không tạo false healthy state.

## 22. Metrics cho Managed Service for Apache Flink

| Metric | Ý nghĩa |
|---|---|
| records_lag_max | Lag lớn nhất theo record với Kafka source |
| millisbehindLatest | Milliseconds consumer bị chậm so với Kinesis head |
| Operator.numRecordsInPerSecond | Input throughput của operator |
| Operator.numRecordsOutPerSecond | Output throughput của operator |
| cpuUtilization | CPU JVM task manager |
| containerCPUUtilization | CPU toàn container |
| containerMemoryUtilization | Memory toàn container |
| lastCheckpointDuration | Thời gian checkpoint gần nhất |
| lastCheckpointSize | Kích thước checkpoint |
| numberOfFailedCheckpoints | Số checkpoint thất bại |
| numRestarts | Số lần restart theo runtime mới |

Đối chiếu metric với version Flink và connector. Ví dụ, backPressuredTimeMsPerSecond chỉ được AWS công bố cho Managed Service for Apache Flink runtime 1.13; với Flink 2.2, dùng metrics và connector measurements tương ứng thay vì tạo alarm trên metric không còn phát.

## 23. Metrics cho Amazon Data Firehose

Firehose gửi metrics trong namespace AWS/Firehose theo chu kỳ một phút. Burst chỉ kéo dài vài giây có thể không xuất hiện đầy đủ trong metric một phút.

| Metric | Ý nghĩa |
|---|---|
| IncomingBytes / IncomingRecords | Lưu lượng ingestion |
| ThrottledRecords | Records bị throttling |
| DeliveryToS3.DataFreshness | Tuổi record cũ nhất trong buffer trước khi giao S3 |
| DeliveryToOpenSearchService.DataFreshness | Tuổi record cũ nhất trước khi giao OpenSearch |
| DeliveryToRedshift.DataFreshness | Tuổi record cũ nhất trước khi giao Redshift |
| DeliveryToHttpEndpoint.DataFreshness | Tuổi record cũ nhất trước khi giao HTTP endpoint |
| DeliveryToS3.Success | Số lần put thành công |
| BackupToS3.DataFreshness | Freshness của dữ liệu backup nếu cấu hình phù hợp |
| PartitionCountExceeded | Vượt giới hạn active partitions khi dynamic partitioning |

DataFreshness tăng liên tục thường chỉ ra destination không xử lý kịp, destination trả lỗi, buffering hints quá thấp hoặc delivery retries kéo dài. Xem cả error logs và destination metrics để phân biệt.

## 24. Xây dựng latency SLI/SLO và alarms

SLO nên mô tả outcome của business, không chỉ CPU hoặc queue depth.

Ví dụ:

- 99% events được ghi vào sink trong vòng 3 giây.
- 99,9% records không vượt quá 60 giây consumer lag.
- Backlog sau burst được drain trong vòng 10 phút.
- Không có record quan trọng tiến gần retention expiry.
- Failed checkpoint rate không tăng liên tục.
- DLQ không có record tồn đọng quá 15 phút.

Các ngưỡng trên chỉ là ví dụ. Xác định theo workload, retention, business criticality và recovery objective.

### 24.1 Alarm theo nhiều tín hiệu

Một alarm hữu ích có thể kết hợp:

- IteratorAgeMilliseconds tăng liên tục.
- ReadProvisionedThroughputExceeded lớn hơn 0.
- IncomingRecords lớn hơn OutgoingRecords trong nhiều chu kỳ.
- Consumer CPU hoặc memory cao.
- Sink ACK latency tăng.
- Error/retry rate tăng.

Lag cao có thể do producer burst hợp lệ. CPU cao có thể không gây latency nếu throughput vẫn đủ. Kết hợp metric để tránh cảnh báo sai.

### 24.2 Ví dụ CloudWatch alarm cho Kinesis iterator age

~~~bash
aws cloudwatch put-metric-alarm \
  --alarm-name orders-stream-iterator-age-high \
  --namespace AWS/Kinesis \
  --metric-name GetRecords.IteratorAgeMilliseconds \
  --dimensions Name=StreamName,Value=orders-events \
  --statistic Maximum \
  --period 60 \
  --evaluation-periods 3 \
  --datapoints-to-alarm 2 \
  --threshold 30000 \
  --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching
~~~

Ngưỡng 30.000 ms trong ví dụ là 30 giây, không phải mặc định cho mọi hệ thống. Chỉnh theo SLO và retention. notBreaching chỉ là lựa chọn minh họa; nếu metric biến mất có thể là consumer ngừng hoạt động, vì vậy production nên có alarm riêng cho heartbeat/consumer availability.

### 24.3 p95 và p99

Latency trung bình có thể che giấu tail latency. Dùng histogram hoặc metric distribution để xem p50, p95 và p99. Nếu 95% events mất 100 ms nhưng 5% events mất 20 giây, average không thể hiện đúng trải nghiệm phần đuôi.

## 25. Quy trình chẩn đoán khi lag tăng

~~~mermaid
flowchart TD
    A["Lag / freshness alarm"] --> B{"Producer rate có tăng?"}
    B -->|Có| C["Kiểm tra burst, partition key, write throttling"]
    B -->|Không| D{"Consumer throughput có giảm?"}
    D -->|Có| E["Kiểm tra CPU, memory, processing time, rebalance"]
    D -->|Không| F{"Sink ACK có chậm?"}
    F -->|Có| G["Kiểm tra database/API, retries, connections"]
    F -->|Không| H["Kiểm tra checkpoint, network, metric gaps"]
    C --> I["Mitigate + theo dõi drain ETA"]
    E --> I
    G --> I
    H --> I
~~~

Thực hiện theo thứ tự:

1. Xác nhận source vẫn nhận records.
2. So sánh incoming và outgoing throughput.
3. Xem lag theo shard/partition, không chỉ tổng.
4. Kiểm tra throttling và broker/stream capacity.
5. Kiểm tra consumer group state/rebalance.
6. Kiểm tra operator input/output rate và CPU/memory.
7. Kiểm tra sink latency, retry và connection pool.
8. Kiểm tra checkpoint duration và failed checkpoints.
9. Ước lượng thời gian drain và retention risk.
10. Chọn hành động: giảm producer, scale consumer, tăng capacity, pause workload hoặc chuyển dữ liệu lỗi sang quarantine.

Không thay đổi nhiều biến cùng lúc. Ghi lại thời điểm và tác động từng mitigation để xác định nguyên nhân thật.

## 26. Case study: pipeline đơn hàng bị trễ sau flash sale

Một ứng dụng thương mại điện tử phát event OrderCreated vào Kinesis Data Streams. Managed Service for Apache Flink enrich event, tính tổng doanh thu theo cửa hàng và ghi kết quả vào Aurora. Trong flash sale, lượng event tăng gấp bốn lần.

### Triệu chứng

- IncomingRecords tăng mạnh.
- IteratorAgeMilliseconds tăng từ 200 ms lên 45 giây.
- Flink millisbehindLatest tăng.
- CPU Flink ở mức 55%, nhưng sink ACK latency tăng từ 40 ms lên 2 giây.
- lastCheckpointDuration tăng.
- Aurora connection pool gần cạn.

### Phân tích

CPU không phải bottleneck chính. Flink bị backpressure từ sink vì Aurora xử lý chậm. Khi sink chậm, operator aggregate gửi ít records hơn, source lag tăng và checkpoint mất nhiều thời gian hơn do pipeline tiến triển chậm.

### Hành động

1. Giới hạn concurrency của sink writes.
2. Batch upsert để giảm round trips.
3. Tăng connection capacity có kiểm soát và kiểm tra query plans.
4. Tạm giảm workload analytics không critical.
5. Theo dõi checkpoint duration và source lag.
6. Sau khi sink ổn định, tăng Flink parallelism nếu throughput operator vẫn thiếu.
7. Tính drain ETA trước khi retention risk xuất hiện.
8. Xác nhận order counts và totals sau khi backlog được xử lý.

Tăng Flink parallelism ngay từ đầu có thể làm Aurora quá tải nặng hơn. Hãy xác định sink là bottleneck và điều tiết concurrency trước.

## 27. Lab: tạo Kinesis stream, quan sát lag và replay

Lab dùng AWS sandbox. Không chạy trên production stream.

### Bước 1: tạo stream On-demand

~~~bash
aws kinesis create-stream \
  --stream-name orders-events-lab \
  --stream-mode-details StreamMode=ON_DEMAND \
  --region ap-southeast-1
~~~

Đợi stream ở trạng thái ACTIVE:

~~~bash
aws kinesis describe-stream-summary \
  --stream-name orders-events-lab \
  --region ap-southeast-1
~~~

### Bước 2: tăng retention cho lab

~~~bash
aws kinesis increase-stream-retention-period \
  --stream-name orders-events-lab \
  --retention-period-hours 72 \
  --region ap-southeast-1
~~~

Retention 72 giờ là ví dụ. Retention trên 24 giờ có thể phát sinh phí.

### Bước 3: gửi record

Tạo file event.json:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "orderId": "order-1001",
  "amount": 125000,
  "eventCreatedAt": "2026-11-20T10:00:00Z"
}
~~~

Gửi record bằng fileb:

~~~bash
aws kinesis put-record \
  --stream-name orders-events-lab \
  --partition-key order-1001 \
  --data fileb://event.json \
  --region ap-southeast-1
~~~

Gửi nhiều records với các partition keys khác nhau để tạo tải và quan sát phân bố.

### Bước 4: đọc từ TRIM_HORIZON

Lấy shard ID:

~~~bash
aws kinesis list-shards \
  --stream-name orders-events-lab \
  --region ap-southeast-1
~~~

Tạo iterator:

~~~bash
aws kinesis get-shard-iterator \
  --stream-name orders-events-lab \
  --shard-id shardId-000000000000 \
  --shard-iterator-type TRIM_HORIZON \
  --region ap-southeast-1
~~~

Dùng ShardIterator trả về để gọi GetRecords. Data trong response được base64 encode; decode trước khi đọc JSON.

### Bước 5: thử replay từ timestamp

~~~bash
aws kinesis get-shard-iterator \
  --stream-name orders-events-lab \
  --shard-id shardId-000000000000 \
  --shard-iterator-type AT_TIMESTAMP \
  --timestamp 1795168800 \
  --region ap-southeast-1
~~~

Timestamp là Unix epoch seconds; chọn thời điểm nằm trong retention. Nếu timestamp cũ hơn trim horizon, Kinesis chỉ trả từ record cũ nhất còn giữ.

### Bước 6: quan sát CloudWatch

Theo dõi namespace AWS/Kinesis:

- GetRecords.IteratorAgeMilliseconds.
- IncomingRecords và IncomingBytes.
- ReadProvisionedThroughputExceeded.
- WriteProvisionedThroughputExceeded.

Tạo test consumer xử lý chậm để quan sát iterator age tăng, sau đó tăng tốc xử lý và đo drain time.

### Bước 7: xác minh replay an toàn

- Ghi eventId vào sink.
- Gửi cùng một record hai lần.
- Xác nhận sink chỉ tạo một business effect.
- Replay từ timestamp cũ.
- Đối chiếu event counts và business totals.
- Ghi lại số records replay và thời gian hoàn tất.

### Bước 8: cleanup

~~~bash
aws kinesis delete-stream \
  --stream-name orders-events-lab \
  --enforce-consumer-deletion \
  --region ap-southeast-1
~~~

Chỉ xóa stream sau khi lab hoàn tất và không còn consumer cần dữ liệu.

## 28. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Kinesis IteratorAge tăng đều | Consumer xử lý chậm hơn ingestion | Kiểm tra process time, sink latency, CPU/memory và shard lag |
| Kinesis write throttling | Shard thiếu capacity hoặc hot partition key | Phân tích key distribution, tăng shards hoặc đánh giá On-demand |
| Kinesis read throttling | Consumers chia sẻ throughput | Dùng EFO, giảm consumers hoặc tăng capacity |
| KCL MillisBehindLatest cao | Record processor chậm hoặc downstream block | Xem processRecords.Time, Success và dependency calls |
| MSK MaxOffsetLag tăng | Consumer group không theo kịp | Kiểm tra partition skew, consumer throughput và rebalance |
| MSK lag metrics biến mất | Group unstable, chưa commit offsets hoặc dimension không hợp lệ | Kiểm tra group state, ASCII name và committed offsets |
| Kafka rebalance liên tục | Poll loop block hoặc max.poll.interval.ms quá thấp | Tách processing khỏi poll thread, kiểm tra heartbeat và processing time |
| Flink millisbehindLatest tăng | Source không được xử lý đủ nhanh | Xem operator throughput, CPU, memory và sink |
| Flink output rate thấp | Operator hoặc sink bottleneck | So sánh input/output rate theo operator và dependency |
| Flink checkpoint duration tăng | State lớn, barrier alignment hoặc storage chậm | Xem checkpoint stages, state size và operator progress |
| Flink checkpoint fail liên tục | Timeout, resource pressure hoặc snapshot incompatibility | Kiểm tra failed checkpoints, logs và state compatibility |
| Firehose DataFreshness tăng | Destination chậm hoặc retry kéo dài | Kiểm tra destination capacity, retry policy và error logs |
| Firehose ThrottledRecords tăng | Ingestion vượt quota | Kiểm tra IncomingBytes/Records và request limits |
| Firehose không có DataFreshness | Không có active delivery hoặc metric không được phát theo cấu hình | Kiểm tra incoming metrics, backup settings và destination metrics |
| Replay tạo duplicate | Sink không idempotent hoặc commit sai thời điểm | Dùng event ID, deduplication và commit sau sink success |
| Replay không có records cũ | Retention hết hạn hoặc compaction đã loại record | Kiểm tra retention, archive và offset boundary |
| Lag thấp nhưng dashboard vẫn cũ | Consumer commit trước sink hoặc sink pipeline chậm | Đo sink commit time và end-to-end freshness |
| Backpressure chỉ xảy ra ở một key | Hot key/partition hoặc skew | Phân tích key distribution, salting hoặc tách workload |
| Backlog không giảm dù scale consumer | Sink hoặc broker là bottleneck | Xác định throughput end-to-end trước khi scale thêm |
| Latency tăng nhưng throughput không đổi | Tail latency hoặc một partition chậm | Theo dõi p95/p99 và lag theo partition/shard |

## 29. Best practices

### Backpressure và flow control

- Dùng bounded queues và giới hạn in-flight requests.
- Retry có exponential backoff và jitter.
- Đặt timeout cho mọi external dependency.
- Tách critical và non-critical consumers.
- Không scale consumer vượt capacity của sink.
- Theo dõi lag theo shard/partition và key distribution.
- Pause/resume hoặc rate limit khi downstream quá tải.
- Ưu tiên xử lý record quan trọng theo business policy.

### Replay và recovery

- Chọn retention theo RTO và thời gian sửa lỗi tối đa.
- Archive raw events vào S3 khi cần lịch sử dài hơn stream retention.
- Dùng consumer group riêng cho replay lớn.
- Không reset production offsets khi consumer còn chạy.
- Lưu checkpoint/snapshot và kiểm tra restore compatibility.
- Dùng event ID và idempotent sink.
- Tách replay output vào staging trước khi merge.
- Lưu audit trail cho mỗi replay execution.
- Không coi retention increase là khôi phục dữ liệu đã hết hạn.

### Observability

- Đo end-to-end latency, không chỉ processor duration.
- Dùng p50/p95/p99 và maximum lag.
- Đặt alarm trước khi backlog tiến gần retention expiry.
- Theo dõi input, processing, checkpoint và sink.
- Dùng correlation ID và event ID trong logs/traces.
- Hạn chế high-cardinality metric dimensions.
- Rà soát dashboard/alarms sau khi nâng runtime hoặc connector.
- Kiểm tra điều kiện phát metric trước khi coi missing data là healthy.

### Reliability và data correctness

- Commit offset sau khi sink commit thành công.
- Dùng transactional sink hoặc idempotency khi có side effects.
- Quarantine poison records thay vì retry vô hạn.
- Thiết kế schema evolution và compatibility.
- Kiểm tra duplicate, late events và out-of-order events.
- Diễn tập replay, checkpoint restore và sink outage.
- Giữ source retention đủ dài để recovery hoàn tất.

## 30. Bài tập tự luyện

1. Backpressure khác consumer lag như thế nào?
2. Vì sao consumer lag thấp chưa chắc end-to-end latency thấp?
3. Nếu producer gửi 80.000 records/s và sink xử lý 60.000 records/s, backlog tăng bao nhiêu mỗi giây?
4. Khi nào Little's Law có thể dùng để ước lượng latency?
5. Vì sao bounded buffer an toàn hơn unbounded queue?
6. Khi nào nên dùng rate limiting thay vì scale consumer?
7. Kinesis IteratorAgeMilliseconds phản ánh điều gì?
8. Vì sao Kinesis retention cần được tính theo recovery time?
9. Kinesis retention mặc định và tối đa hiện nay là bao nhiêu?
10. Enhanced Fan-Out giải quyết loại contention nào?
11. Tại sao thêm shards không chắc giải quyết sink bottleneck?
12. Kinesis TRIM_HORIZON, LATEST và AT_TIMESTAMP khác nhau thế nào?
13. Vì sao tăng retention không khôi phục records đã hết hạn?
14. MSK MaxOffsetLag và EstimatedTimeLag khác nhau thế nào?
15. Vì sao consumer group rebalance có thể làm lag tăng?
16. Tại sao poll loop không nên bị block bởi xử lý downstream dài?
17. Vì sao thêm Kafka partitions có thể thay đổi key-to-partition mapping?
18. Flink backpressure truyền ngược từ sink về source như thế nào?
19. Checkpoint và snapshot khác nhau ra sao?
20. Vì sao Flink checkpoint duration tăng có thể làm source lag tăng?
21. Tại sao exactly-once ở processor không tự bảo đảm exactly-once cho external API?
22. Firehose DataFreshness đo điều gì?
23. DirectPut Firehose giữ dữ liệu tối đa bao lâu khi destination unavailable?
24. Vì sao replay cần idempotent sink?
25. Vì sao replay từ Kafka compacted topic không đảm bảo khôi phục toàn bộ event history?
26. Event time khác processing time thế nào?
27. Watermark chậm có thể làm window output trễ dù CPU thấp không?
28. Nên theo dõi metric nào để biết sink đang gây backpressure?
29. Vì sao nên dùng p95/p99 thay cho chỉ average latency?
30. Cần xác minh điều gì trước khi reset production consumer offsets?

### Gợi ý đáp án

1. Backpressure là tín hiệu flow control do downstream chậm; lag là khoảng cách tiến độ consumer so với dữ liệu mới nhất.
2. Consumer có thể commit offset trước khi sink hoàn tất hoặc sink có queue riêng.
3. Tăng 20.000 records/s.
4. Khi hệ thống ổn định và throughput tương đối đều.
5. Bounded buffer giới hạn memory và tạo flow control; unbounded queue có thể làm OOM.
6. Khi producer burst vượt capacity ngắn hạn hoặc downstream cần bảo vệ.
7. Tuổi record cuối cùng consumer đọc được so với thời điểm hiện tại.
8. Vì dữ liệu hết hạn sẽ không thể replay từ stream.
9. 24 giờ mặc định, tối đa 365 ngày.
10. Nó cấp read throughput riêng cho từng registered consumer trên mỗi shard.
11. Vì sink vẫn chỉ ghi được ở tốc độ cũ.
12. TRIM_HORIZON đọc record cũ nhất còn giữ; LATEST đọc record mới; AT_TIMESTAMP đọc từ timestamp chỉ định.
13. Record đã bị trim khỏi stream không thể truy cập lại chỉ bằng cách tăng retention.
14. MaxOffsetLag là số offset lớn nhất; EstimatedTimeLag là thời gian ước tính để drain.
15. Consumer ownership thay đổi, một số partition tạm ngừng xử lý và metrics có thể không được phát trong lúc group unstable.
16. Consumer có thể vượt max.poll.interval.ms, bị loại khỏi group và gây rebalance.
17. Partition mapping của keys cho records mới có thể thay đổi khi số partition tăng.
18. Network buffers downstream đầy, khiến upstream không thể phát thêm records và phải giảm tốc.
19. Checkpoint tự động phục hồi state; snapshot/savepoint là backup được trigger/quản lý để restore có chủ đích.
20. Job dành nhiều thời gian snapshot và ít thời gian xử lý, source lag tăng.
21. External API có thể nhận request rồi timeout trước khi response về; retry có thể tạo side effect trùng.
22. Tuổi record cũ nhất đang chờ delivery trong Firehose.
23. 24 giờ.
24. Replay có thể gửi lại cùng event nhiều lần.
25. Compaction có thể loại bỏ các phiên bản cũ theo key.
26. Event time là thời điểm nghiệp vụ xảy ra; processing time là thời điểm processor chạy logic.
27. Có. Window có thể chờ watermark tiến qua window boundary.
28. Sink ACK latency, retry/error rate, write throughput và processor output rate.
29. Average che giấu tail latency của một phần records.
30. Consumer đã dừng, offset boundary, retention, sink idempotency, expected duplicate và rollback plan.

## 31. Câu hỏi phỏng vấn

### Backpressure có phải lúc nào cũng là lỗi không?

Không. Backpressure là cơ chế bảo vệ để downstream không bị quá tải. Vấn đề là backpressure kéo dài làm tăng lag và latency. Cần xác định nguyên nhân và xem hệ thống có drain backlog trong SLO hay không.

### Vì sao tăng consumer count có thể làm hệ thống chậm hơn?

Consumer mới có thể tranh throughput broker, gây rebalance, tăng concurrent writes vào sink và tạo nhiều kết nối hơn. Nếu sink là bottleneck, thêm consumer chỉ làm pressure tăng.

### Kinesis EFO giải quyết vấn đề gì?

EFO cấp throughput đọc riêng cho registered consumers, tránh nhiều consumers chia sẻ cùng read throughput trên shard. Nó không tăng sink capacity và có chi phí riêng.

### Vì sao MSK consumer lag metrics có thể không xuất hiện?

Group có thể unstable, chưa commit offsets hoặc consumer group name không đáp ứng điều kiện CloudWatch dimensions. Cần kiểm tra group health và client metrics.

### Làm sao xác định operator nào gây backpressure trong Flink?

So sánh input/output throughput, parallelism, busy/CPU, container memory, source lag, sink ACK và checkpoint duration theo operator/task. Xem cả skew theo subtask.

### Checkpoint có phải cơ chế replay lịch sử không?

Không. Checkpoint phục hồi state và source position gần thời điểm đã lưu. Replay lịch sử cần đọc lại records từ source offsets/timestamp hoặc archive.

### Làm sao tránh duplicate khi replay?

Dùng event ID ổn định, idempotent writes, deduplication store hoặc transactional sink. Ghi audit replay ID và kiểm tra source/sink commit semantics.

### Vì sao end-to-end latency cần timestamp ở sink?

Consumer lag chỉ nói consumer đọc đến đâu. Sink có thể chậm hoặc commit sau khi consumer đã đọc/commit offset. Timestamp sink commit cho biết khi nào kết quả thực sự có thể sử dụng.

### Khi nào nên archive stream sang S3?

Khi cần replay lâu hơn retention của Kinesis/MSK, audit lịch sử hoặc tái tạo dataset mà không gây tải lớn lên production stream.

### Làm sao chọn retention?

Dựa trên thời gian phát hiện sự cố, thời gian sửa code/dependency, thời gian drain backlog, RTO và chi phí. Retention phải dài hơn tổng thời gian cần để khôi phục và xử lý lại.

## 32. Checklist trước khi đưa streaming pipeline vào production

### Capacity và backpressure

- [ ] Throughput baseline và peak đã được đo.
- [ ] Partition key/shard distribution không tạo hot spots nghiêm trọng.
- [ ] Consumer parallelism phù hợp với shards/partitions.
- [ ] Sink capacity và connection limits đã được xác nhận.
- [ ] Buffer có giới hạn và có flow-control policy.
- [ ] Retry có backoff, jitter, timeout và max attempts.
- [ ] Có cơ chế pause/resume hoặc admission control.

### Replay và data correctness

- [ ] Retention đủ dài theo recovery objectives.
- [ ] Có archive nếu cần lịch sử dài hạn.
- [ ] Replay boundary được xác định bằng timestamp/offset/sequence.
- [ ] Có consumer group hoặc lease namespace riêng cho replay.
- [ ] Sink idempotency và deduplication đã được kiểm thử.
- [ ] Checkpoint/snapshot được bật và restore đã diễn tập.
- [ ] DLQ/quarantine có owner, retention và replay process.
- [ ] Schema evolution và late/out-of-order events đã được kiểm tra.

### Observability và latency

- [ ] Có source ingest, consumer lag, processor throughput và sink freshness.
- [ ] Có end-to-end timestamps và correlation IDs.
- [ ] Có p95/p99 latency SLI.
- [ ] Có alarms trước khi records tiến gần retention expiry.
- [ ] Có dashboard theo stream/topic/shard/partition/operator.
- [ ] Có alarm cho checkpoint duration/failure và sink retry.
- [ ] Metric support đã được xác minh theo runtime/connector version.
- [ ] Missing metrics không bị coi mặc định là healthy.

### Operations

- [ ] Runbook cho lag spike, sink outage, replay và offset reset.
- [ ] Có quy trình change/approval cho production replay.
- [ ] Có cách giới hạn replay rate.
- [ ] Có reconciliation sau replay.
- [ ] CloudWatch alarms có owner và escalation path.
- [ ] Chi phí enhanced metrics, EFO, retention và archive đã được dự toán.
- [ ] Đã diễn tập failure và recovery với tải gần production.

## 33. Tài liệu tham khảo chính thức

- [Monitor Amazon Kinesis Data Streams with CloudWatch](https://docs.aws.amazon.com/streams/latest/dev/monitoring-with-cloudwatch.html)
- [Troubleshoot Kinesis Data Streams consumers](https://docs.aws.amazon.com/streams/latest/dev/troubleshooting-consumers.html)
- [Change the Kinesis Data Streams retention period](https://docs.aws.amazon.com/streams/latest/dev/kinesis-extended-retention.html)
- [Kinesis Data Streams starting positions](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_StartingPosition.html)
- [Develop enhanced fan-out consumers](https://docs.aws.amazon.com/streams/latest/dev/enhanced-consumers.html)
- [Monitor the Kinesis Client Library with CloudWatch](https://docs.aws.amazon.com/streams/latest/dev/monitoring-with-kcl.html)
- [Handle Kinesis consumer startup, shutdown, and throttling](https://docs.aws.amazon.com/streams/latest/dev/kinesis-record-processor-additional-considerations.html)
- [Lambda parameters for Kinesis event source mappings](https://docs.aws.amazon.com/lambda/latest/dg/services-kinesis-parameters.html)
- [Monitor consumer lags in Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/consumer-lag.html)
- [Amazon MSK metrics for CloudWatch](https://docs.aws.amazon.com/msk/latest/developerguide/metrics-details.html)
- [Amazon MSK consumer groups](https://docs.aws.amazon.com/msk/latest/developerguide/msk-consumer-groups.html)
- [Amazon MSK topic configuration](https://docs.aws.amazon.com/msk/latest/developerguide/msk-configuration-properties.html)
- [Monitoring Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/latest/java/monitoring.html)
- [Metrics and dimensions in Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/latest/java/metrics-dimensions.html)
- [Use CloudWatch alarms with Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/latest/java/monitoring-metrics-alarms.html)
- [Implement fault tolerance in Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/latest/java/how-fault.html)
- [Manage application backups using Flink snapshots](https://docs.aws.amazon.com/managed-flink/latest/java/how-snapshots.html)
- [Troubleshoot Flink checkpoints](https://docs.aws.amazon.com/managed-flink/latest/java/troubleshooting-checkpoints.html)
- [Best practices for Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/latest/java/best-practices.html)
- [Monitor Amazon Data Firehose with CloudWatch metrics](https://docs.aws.amazon.com/firehose/latest/dev/monitoring-with-cloudwatch-metrics.html)
- [Troubleshoot errors in Amazon Data Firehose](https://docs.aws.amazon.com/firehose/latest/dev/troubleshooting.html)
- [Handle data delivery failures in Amazon Data Firehose](https://docs.aws.amazon.com/firehose/latest/dev/retry.html)
- [Amazon Data Firehose quotas and limits](https://docs.aws.amazon.com/firehose/latest/dev/limits.html)
- [Pause and resume Amazon Data Firehose delivery](https://docs.aws.amazon.com/firehose/latest/dev/pause-restart-stream.html)


