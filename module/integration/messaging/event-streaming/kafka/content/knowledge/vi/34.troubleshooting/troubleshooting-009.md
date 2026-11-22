# Lag tăng do consumer chậm, key lệch hoặc hệ thống đích nghẽn

Consumer lag tăng khi tốc độ record được ghi vào partition cao hơn tốc độ consumer group xử lý và commit offset. Nguyên nhân có thể nằm ở consumer application, phân phối key, số partition, cấu hình poll/fetch, rebalance hoặc hệ thống đích như database và HTTP API. Tăng số consumer hay tăng cấu hình fetch chỉ hữu ích khi đã xác định đúng nút thắt.

Bài học này hướng dẫn điều tra lag theo số liệu: xác định partition/member nào đang tụt lại, so sánh ingress với processing rate, tìm hot partition/hot key, kiểm tra thời gian xử lý và dependency downstream, sau đó áp dụng biện pháp khắc phục có kiểm soát. Mục tiêu là khôi phục tốc độ xử lý mà vẫn giữ ordering, delivery semantics và tính đúng đắn của dữ liệu.

## 1. Hiểu đúng consumer lag

Với một topic partition, consumer group có committed offset cho biết vị trí tiếp theo mà group sẽ đọc. Log end offset (LEO) là vị trí cuối của log theo cách biểu diễn offset. Một cách tính gần đúng thường dùng:

\[
Lag_{records} = LogEndOffset - CommittedOffset
\]

Ví dụ:

| Partition | Log end offset | Committed offset | Lag |
|---|---:|---:|---:|
| 0 | 1.250.000 | 1.245.000 | 5.000 |
| 1 | 980.000 | 979.900 | 100 |
| 2 | 1.100.000 | 1.080.000 | 20.000 |
| **Tổng** | | | **25.100** |

Lag là số offset chưa được commit theo quan sát của group. Nó không nhất thiết bằng số record business đang nằm trong hàng đợi xử lý: offset có thể có khoảng trống do compaction, transaction control records hoặc cách ghi nhận log. Consumer cũng có thể đã poll record nhưng chưa commit offset.

Phải phân biệt ba trạng thái:

- **Fetch progress**: consumer đã lấy record từ broker đến đâu.
- **Processing progress**: ứng dụng đã xử lý business logic đến đâu.
- **Commit progress**: offset đã được ghi nhận cho consumer group đến đâu.

Nếu ứng dụng commit sớm rồi đẩy việc xử lý sang executor nội bộ, Kafka lag có thể thấp trong khi queue nội bộ tăng và dữ liệu vẫn chưa đến hệ thống đích. Ngược lại, xử lý đã xong nhưng commit chậm có thể làm lag hiển thị cao hơn phần công việc thực sự còn lại.

Lag cũng không phải end-to-end latency. Một group có lag 0 vẫn có thể có business delay cao nếu consumer đã commit offset trước khi async request hoặc downstream work hoàn tất, hoặc nếu queue nội bộ tăng sau commit.

### Tốc độ tăng lag quan trọng hơn một con số đơn lẻ

Gọi:

- \(R_{in}\): tốc độ record được ghi vào các partition, records/second.
- \(R_{out}\): tốc độ consumer hoàn tất và commit xử lý, records/second.
- \(L(t)\): lag tại thời điểm \(t\).

Khi backlog đang tăng:

\[
\frac{dL}{dt} \approx R_{in} - R_{out}
\]

Nếu ingress là 8.000 records/s và consumer chỉ hoàn tất 6.500 records/s, backlog tăng khoảng 1.500 records/s. Khi ingress giảm, consumer cần throughput dư để catch up.

Khi hệ thống đã catch up, \(R_{out}\) phải lớn hơn \(R_{in}\) trong một khoảng thời gian để xóa backlog. Nếu throughput consumer chỉ bằng ingress, lag sẽ không giảm.

## 2. Nhận diện nguyên nhân theo luồng xử lý

Một luồng consumer điển hình:

~~~mermaid
flowchart LR
    P["Producer"] --> T["Topic partitions"]
    T --> F["Consumer fetch / poll"]
    F --> D["Deserialize"]
    D --> H["Business handler"]
    H --> Q["DB / HTTP / downstream"]
    Q --> C["Commit offset"]
    T -. "lag per partition" .-> M["Metrics"]
    F -.-> M
    H -.-> M
    Q -.-> M
    C -.-> M
~~~

Điều tra theo các điểm có thể nghẽn:

1. **Broker/fetch**: consumer không fetch đủ nhanh, network chậm, broker quá tải hoặc fetch bị giới hạn.
2. **Partition assignment**: số consumer ít hơn nhu cầu, rebalance liên tục hoặc một partition nhận quá nhiều traffic.
3. **Key distribution**: một vài key nóng dồn vào một partition trong khi partition khác rảnh.
4. **Application**: deserialize nặng, CPU cao, lock contention, GC pause, xử lý đồng bộ hoặc batch quá lớn.
5. **Downstream**: database connection pool cạn, query/lock chậm, HTTP API rate limit, timeout hoặc queue bên ngoài bị nghẽn.
6. **Commit/rebalance**: xử lý vượt max.poll.interval.ms, commit lỗi hoặc consumer liên tục rời group.

Không kết luận “Kafka chậm” chỉ từ việc lag tăng. Cần chứng minh thời gian bị tiêu tốn ở đâu.

## 3. Bắt đầu điều tra: xác định phạm vi và xu hướng

Trước khi thay cấu hình, ghi lại:

- Cluster, topic, consumer group và thời điểm bắt đầu lag.
- Lag tổng và lag từng partition qua nhiều mốc thời gian.
- Ingress records/s và bytes/s.
- Consumer records/s, fetch rate và commit rate.
- Số member hiện tại, số partition được assign cho từng member.
- Consumer error, rebalance, commit failure và downstream latency.
- Release/config change gần nhất và sự kiện traffic tăng đột biến.

Đọc lag theo chuỗi thời gian:

| Quan sát | Hướng điều tra |
|---|---|
| Tất cả partition tăng tương tự | Consumer group thiếu tổng throughput, downstream chung nghẽn hoặc traffic tăng |
| Chỉ một vài partition tăng | Key skew, partition leader/broker riêng, assignment hoặc hot shard |
| Lag tăng theo từng đợt rồi tự giảm | Burst traffic, batch schedule hoặc downstream rate limit |
| Lag tăng sau deploy | Regression trong code, serializer, thread pool, DB query hoặc cấu hình |
| Lag nhảy vọt sau rebalance | Member restart, poll timeout, deployment hoặc xử lý quá lâu |
| Kafka lag thấp nhưng business delay cao | Commit sớm, async queue nội bộ hoặc downstream xử lý sau commit |
| Lag lớn nhưng không tăng | Consumer đang catch up hoặc topic có backlog cũ; nếu CURRENT-OFFSET chưa có giá trị, group có thể chưa commit offset và cần kiểm tra auto.offset.reset |

### Kiểm tra consumer group bằng CLI

Liệt kê group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --list
~~~

Xem lag theo partition:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --describe \
  --group orders-consumer
~~~

Output thường có các cột TOPIC, PARTITION, CURRENT-OFFSET, LOG-END-OFFSET, LAG và CONSUMER-ID/HOST/CLIENT-ID tùy trạng thái và version. Lưu output cùng timestamp để so sánh sau khi thay đổi.

Một số version hỗ trợ xem member và assignment chi tiết:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --describe \
  --group orders-consumer \
  --members \
  --verbose
~~~

Kiểm tra trạng thái group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --describe \
  --group orders-consumer \
  --state
~~~

Các tùy chọn --members, --verbose và --state phụ thuộc Kafka CLI version. Nếu version đang dùng không hỗ trợ, dùng --describe cơ bản và metrics của client/coordinator.

Không chạy reset offset để làm đẹp dashboard hoặc xóa lag. Reset offset thay đổi vị trí đọc và có thể bỏ sót hoặc phát lại dữ liệu. Chỉ thực hiện khi đã có quyết định nghiệp vụ, group được dừng và có dry-run được review.

## 4. Đo ingress, processing và commit rate

Để biết consumer có thực sự chậm, so sánh các rate trong cùng khoảng thời gian:

| Nhóm | Metric gợi ý | Câu hỏi |
|---|---|---|
| Producer/topic | bytes in, messages in, records/s theo topic/partition | Lưu lượng đầu vào tăng bao nhiêu? |
| Consumer fetch | fetch rate, fetch latency, bytes consumed, records consumed | Client có lấy dữ liệu từ broker được không? |
| Application | handler duration, records processed/s, queue depth, active threads | Thời gian tiêu tốn ở logic nào? |
| Commit | commit rate, commit latency, commit failures | Offset có được commit kịp không? |
| Group | lag per partition, assigned partitions, rebalance count | Lag tập trung ở đâu, assignment có ổn định không? |
| Downstream | DB pool active/pending, query latency, HTTP 429/5xx, timeout | Hệ thống đích có nhận được tải không? |

Tên metric cụ thể phụ thuộc Kafka client, JMX exporter, Spring Boot Actuator và monitoring stack. Kafka consumer client cung cấp các nhóm metric như fetch rate/latency, records-consumed rate, records-lag và records-lag-max; kiểm tra metric catalog của client version và cách exporter đặt tên.

Nên có dashboard cùng trục thời gian cho:

- Lag tổng và lag từng partition.
- Records in/s so với records processed/s.
- p50/p95/p99 handler duration.
- Commit latency và commit failure.
- Rebalance rate và số member.
- CPU, heap, GC pause, thread pool và network.
- DB pool saturation, DB query latency, HTTP error/latency.

### Tính thời gian catch-up

Nếu lag hiện tại là \(L\), ingress là \(R_{in}\), consumer có khả năng xử lý \(R_{out}\) ổn định và \(R_{out} > R_{in}\), thời gian catch-up ước tính:

\[
T_{catchup} = \frac{L}{R_{out} - R_{in}}
\]

Ví dụ lag 600.000 records, ingress 4.000 records/s, consumer xử lý 6.000 records/s:

\[
T_{catchup} = \frac{600.000}{6.000 - 4.000} = 300s
\]

Đây là ước lượng đơn giản. Kích thước record, phân bố partition, downstream latency, rebalance và traffic burst có thể làm thời gian thực tế dài hơn. Với workload nhiều loại event, tính theo bytes hoặc thời gian xử lý business sẽ hữu ích hơn chỉ đếm records.

## 5. Phân biệt consumer chậm với broker/fetch chậm

### Dấu hiệu consumer fetch chậm

- records-consumed-rate thấp trong khi topic ingress cao.
- Fetch latency cao hoặc fetch request rate thấp bất thường.
- Network receive throughput thấp hoặc packet retransmission cao.
- Consumer CPU thấp nhưng chờ network/broker.
- Broker request queue, network processor idle/queue hoặc disk read latency tăng.

Kiểm tra:

- Broker health, request handler idle, network processor, disk utilization và request latency.
- Network path giữa consumer và broker, DNS, TLS handshake/reconnect.
- Consumer bootstrap servers, advertised listener và route.
- Fetch configuration có quá hạn chế so với kích thước record/batch không.
- Có lỗi authorization, deserialization hoặc fetch exception bị retry không.

### Dấu hiệu application handler chậm

- Fetch rate bình thường nhưng handler duration tăng.
- Consumer poll nhận batch, sau đó thời gian xử lý dài.
- CPU, GC, lock wait hoặc thread pool queue tăng.
- Commit rate giảm vì listener chưa hoàn tất.
- Một số event type có payload lớn hoặc xử lý nhiều bước hơn bình thường.

Đo thời gian riêng cho deserialize, business handler, downstream call và commit. Một metric tổng listener duration chưa đủ để chỉ ra đoạn code nào đang nghẽn.

## 6. Tìm partition nóng và key skew

Kafka chỉ đảm bảo thứ tự trong một partition. Producer thường chọn partition dựa trên key để giữ các event cùng entity trên cùng partition. Điều này tạo ordering theo key nhưng cũng khiến một key có lưu lượng rất lớn trở thành hot key.

Ví dụ:

| Partition | Ingress records/s | Consumer records/s | Lag growth/s |
|---|---:|---:|---:|
| 0 | 8.000 | 7.900 | +100 |
| 1 | 1.000 | 1.500 | -500 |
| 2 | 900 | 1.300 | -400 |
| 3 | 1.100 | 1.400 | -300 |

Tổng throughput consumer có thể gần ingress, nhưng partition 0 vẫn tụt lại. Consumer rảnh ở partition khác không tự lấy được partition 0 nếu group assignment và partition ownership không đổi.

### Kiểm tra phân bố key

- Thu thập sample key và đếm tần suất theo khoảng thời gian ngắn.
- So sánh bytes/records in và lag theo partition.
- Kiểm tra producer partitioner, key serializer và null-key ratio.
- Xem một tenant, customer, account hoặc entity có phát sinh traffic bất thường không.
- Kiểm tra thay đổi key format khiến nhiều key khác nhau hash thành cùng một giá trị.

Không log toàn bộ key nếu key chứa thông tin cá nhân hoặc dữ liệu nhạy cảm. Dùng hash hoặc aggregate counter theo nhóm để phân tích phân bố.

### Cách xử lý hot key

1. **Giảm công việc trên mỗi event**: tối ưu query, cache dữ liệu tham chiếu, bỏ tính toán lặp.
2. **Batch downstream**: gom nhiều event cùng transaction hoặc bulk API nếu business semantics cho phép.
3. **Tách workload**: đưa event nặng hoặc tenant lớn sang topic/partitioning strategy riêng khi cần.
4. **Tăng partition**: chỉ có ích khi key distribution có thể phân tán thêm; cùng một key vẫn được route vào một partition theo partitioner hiện tại.
5. **Thay đổi key có chủ đích**: thêm shard/salt chỉ khi chấp nhận thay đổi ordering hoặc có cơ chế tái lập thứ tự ở tầng ứng dụng.

Không thêm random suffix vào key một cách tùy tiện. Cách đó có thể phân tán tải nhưng phá ordering của cùng business entity. Nếu cần sharding, thiết kế sequence/version per entity, routing table và merge/order strategy trước khi triển khai.

### Tăng partition có giải quyết được không?

Tăng partition có thể tăng parallelism tối đa của consumer group và tạo thêm đơn vị phân phối tải. Tuy nhiên:

- Một key cụ thể vẫn thuộc một partition.
- Default hash partitioning có thể map key cũ sang partition khác sau khi tăng số partition, làm mất ordering liên tục giữa record cũ và mới của cùng key.
- Tăng partition không tự tăng số consumer instance hoặc downstream capacity.
- Mỗi partition bổ sung thêm overhead cho broker, file handle, replication và recovery.

Với topic có yêu cầu ordering theo key, đánh giá tác động migration trước khi tăng partition.

## 7. Consumer group thiếu parallelism

Một partition tại một thời điểm chỉ được gán cho tối đa một consumer trong cùng group. Do đó:

\[
ActiveConsumers \leq AssignedPartitions
\]

Nếu topic có 6 partition và group có 12 consumer, tối đa 6 consumer có partition để xử lý; phần còn lại idle. Ngược lại, nếu chỉ có 2 consumer cho 12 partition, mỗi consumer phải xử lý nhiều partition.

Kiểm tra:

- Số partition của topic.
- Số member đang active.
- Số partition được assign cho mỗi member.
- concurrency của Spring listener container.
- Số replica/pod thực tế sau autoscaling.
- Có member nào liên tục join/leave group không.

Ví dụ Spring Boot:

~~~yaml
spring:
  kafka:
    listener:
      concurrency: 4
    consumer:
      group-id: orders-consumer
      enable-auto-commit: false
      max-poll-records: 200
~~~

concurrency là số consumer thread do listener container quản lý trong mỗi application instance. Nếu chạy 3 pod với concurrency 4, group có thể có tối đa 12 consumer member. Số consumer thực sự hoạt động vẫn bị giới hạn bởi số partition được assign.

Scale pod hoặc concurrency khi:

- Có đủ partition để chia tải.
- CPU/DB/downstream còn headroom.
- Consumer không bị giới hạn bởi một hot partition.
- Rebalance overhead không lớn hơn lợi ích của scale.

Scale consumer trong lúc database đã quá tải có thể làm DB timeout tăng, khiến handler chậm hơn và lag tiếp tục tăng.

## 8. Tìm bottleneck trong consumer application

### CPU và deserialize

Nếu CPU cao:

- Profile handler và serializer/deserializer.
- Kiểm tra JSON parsing, schema resolution, compression/decompression và object allocation.
- Tránh tạo nhiều object tạm hoặc serialize cùng dữ liệu nhiều lần.
- Dùng batch/bulk operation khi phù hợp.
- Kiểm tra CPU throttling trong container; CPU request/limit quá thấp có thể gây throttling dù host còn tài nguyên.

Nếu CPU thấp nhưng throughput thấp, tìm thời gian chờ lock, network, database, semaphore hoặc thread pool.

### GC và heap

Payload lớn hoặc batch quá nhiều record có thể làm allocation rate và GC pause tăng:

- Theo dõi heap used, allocation rate, pause time và old-generation occupancy.
- Tránh giữ cả batch lớn trong memory khi xử lý tuần tự.
- Giới hạn kích thước payload và số record mỗi poll theo RAM.
- Kiểm tra leak do cache, map hoặc retry queue không có giới hạn.

Tăng heap không chữa được memory leak hoặc batch size quá lớn; nó có thể chỉ kéo dài thời gian trước khi sự cố xuất hiện.

### Thread pool và lock contention

Nếu listener đẩy việc sang executor:

- Theo dõi queue depth, active thread, rejected task và task duration.
- Đặt queue có giới hạn để tạo backpressure.
- Không commit offset trước khi công việc async hoàn tất nếu semantics yêu cầu xử lý xong mới commit.
- Nếu hoàn tất không theo thứ tự, quản lý offset commit theo partition để không commit vượt qua record chưa xử lý.

Một queue vô hạn có thể làm Kafka lag giảm trong khi backlog trong JVM tăng cho đến khi hết heap. Metric queue depth phải nằm cùng dashboard với Kafka lag.

## 9. Khi hệ thống đích nghẽn

Consumer có thể fetch nhanh nhưng xử lý chậm vì mỗi record cần ghi database, gọi API hoặc publish sang service khác.

### Database saturation

Dấu hiệu:

- HikariCP active connections chạm max, pending threads tăng.
- Connection acquisition timeout hoặc query timeout.
- DB CPU/IO cao, lock wait và deadlock tăng.
- p95/p99 query latency tăng cùng consumer handler duration.
- Consumer throughput giảm dù CPU ứng dụng không cao.

Điều tra:

1. Đo thời gian lấy connection riêng với thời gian query.
2. Kiểm tra slow query, execution plan và index.
3. Kiểm tra transaction giữ lock quá lâu.
4. So sánh pool size với DB connection limit và số application replica.
5. Xác minh batch insert/update có thể giảm round trip không.

Không chỉ tăng Hikari pool size. Nếu database đã hết capacity, thêm connection làm tăng contention và có thể khiến latency xấu hơn.

### HTTP/API downstream saturation

Theo dõi:

- HTTP 429, 5xx, timeout và retry rate.
- Request concurrency và connection pool pending.
- API latency p95/p99.
- Rate limit theo tenant hoặc credential.
- Circuit breaker open/half-open và bulkhead saturation.

Khi downstream trả 429/503, giảm tốc độ gửi có kiểm soát, áp dụng exponential backoff với jitter và tôn trọng Retry-After nếu API cung cấp. Không retry tức thời trong vòng lặp nóng vì sẽ khuếch đại sự cố.

### Retry có thể làm lag tăng nhanh hơn

Nếu mọi record đều retry nhiều lần khi downstream đã lỗi, consumer dành phần lớn thời gian lặp lại cùng request. Một retry policy nên:

- Phân loại lỗi transient và permanent.
- Có số lần retry tối đa.
- Có exponential backoff và jitter.
- Có timeout cho mỗi request và tổng thời gian xử lý.
- Đưa lỗi không thể phục hồi vào DLT/quarantine theo policy.
- Có circuit breaker/bulkhead để bảo vệ downstream.

Retry không được làm mất idempotency. Nếu request đã thành công ở database nhưng response bị timeout, lần retry có thể ghi trùng; dùng business key/idempotency key hoặc upsert an toàn.

## 10. Backpressure và kiểm soát tốc độ

Backpressure là cơ chế để consumer không nhận hoặc không phát sinh công việc nhanh hơn khả năng xử lý downstream.

Các cách áp dụng:

- Giảm max.poll.records để giới hạn số record trong một poll và thời gian xử lý batch.
- Giới hạn executor queue và số request đồng thời.
- Dùng semaphore/bulkhead cho dependency.
- Tạm pause partition khi queue hoặc downstream vượt ngưỡng; resume khi đã hồi phục.
- Điều chỉnh batch size và flush interval.
- Giảm concurrency khi downstream saturation.
- Dùng rate limiter theo service/tenant nếu API có quota.

Spring Kafka hỗ trợ pause/resume listener container và điều khiển flow theo tình trạng ứng dụng. Khi tự pause partition, vẫn phải đảm bảo consumer tiếp tục poll theo yêu cầu của client để duy trì group membership. Thiết kế pause/resume phải tính đến rebalance và shutdown.

Không dùng pause như cách thay thế xử lý lỗi lâu dài. Nếu downstream không hồi phục, cần alert, circuit breaker và quy trình phục hồi.

## 11. Điều chỉnh consumer configuration có mục tiêu

| Config | Tác động | Khi nào xem xét |
|---|---|---|
| max.poll.records | Số record tối đa trả về mỗi poll | Batch quá lớn hoặc thời gian xử lý vượt poll interval |
| max.poll.interval.ms | Thời gian tối đa giữa các lần poll | Một batch hợp lệ cần xử lý lâu hơn; phải đo trước |
| fetch.min.bytes | Lượng dữ liệu tối thiểu broker cố gắng gom trước khi trả fetch | Muốn tăng batching, chấp nhận thêm latency |
| fetch.max.wait.ms | Thời gian broker chờ đạt fetch.min.bytes | Cân bằng batching và latency |
| max.partition.fetch.bytes | Giới hạn dữ liệu fetch từ một partition | Record/batch lớn bị giới hạn fetch |
| fetch.max.bytes | Giới hạn dữ liệu cho một fetch response | Điều chỉnh memory/network batch tổng |
| session.timeout.ms | Thời gian coordinator chờ heartbeat | Phát hiện member mất kết nối |
| heartbeat.interval.ms | Chu kỳ heartbeat với classic group protocol | Điều chỉnh theo session timeout và protocol |

Ví dụ Spring Boot properties:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      max-poll-records: 200
      properties:
        max.poll.interval.ms: 300000
        fetch.min.bytes: 1
        fetch.max.wait.ms: 500
        max.partition.fetch.bytes: 1048576
        fetch.max.bytes: 52428800
~~~

Đây là giá trị minh họa, không phải cấu hình tối ưu chung. Kiểm tra Kafka client version và broker limit trước khi áp dụng. Kích thước fetch cần tương thích với max.message.bytes, message.max.bytes và payload thực tế; client có thể cần xử lý record batch lớn hơn mức kỳ vọng.

### Chỉnh max.poll.records

Nếu handler xử lý mỗi record trong 80 ms và max.poll.records=500, thời gian xử lý tuần tự một batch có thể lên đến khoảng 40 giây, chưa kể deserialize, DB và commit. Nếu thời gian giữa các lần poll vượt max.poll.interval.ms, consumer có thể bị xem là không còn tiến triển và group rebalance.

Giảm batch size có thể giữ thời gian xử lý dưới poll interval, nhưng tạo nhiều poll/fetch hơn và giảm hiệu quả batching. Đo thời gian xử lý p95/p99 của batch để chọn giá trị.

### Chỉnh max.poll.interval.ms

Chỉ tăng khi đã xác minh một batch hợp lệ cần thời gian xử lý dài và ứng dụng vẫn tiến triển. Tăng giá trị quá cao có thể làm group phát hiện consumer treo chậm hơn. Nếu handler bị block vô hạn, tăng poll interval chỉ trì hoãn việc phát hiện.

### Chỉnh fetch

Tăng fetch.min.bytes có thể tăng hiệu quả batch ở tải cao nhưng làm record phải đợi lâu hơn khi traffic thấp. Tăng fetch byte limits có thể giảm số round trip nhưng tăng memory footprint. Không tăng mọi thông số cùng lúc; thay từng nhóm, đo trước/sau và giữ khả năng rollback.

## 12. Rebalance và commit offset

Lag có thể tăng trong lúc rebalance vì partition tạm thời chưa được xử lý. Nguyên nhân thường gặp:

- Pod restart/deploy hoặc liveness probe kill consumer.
- GC pause dài, CPU throttling hoặc process bị suspend.
- Handler vượt max.poll.interval.ms.
- Network flap hoặc broker/coordinator không ổn định.
- Consumer group thay đổi membership liên tục.

Theo dõi rebalance rate, partition assignment/revocation, heartbeat failure và commit failure. Nếu lag tăng trùng với rebalance spike, xử lý nguyên nhân member churn trước khi scale thêm.

Với manual acknowledgment, chỉ acknowledge khi record đã hoàn tất theo delivery semantics đã chọn. Với xử lý song song trong cùng partition, không commit offset cao hơn record thấp nhất chưa hoàn tất; nếu không, crash có thể làm mất record đang xử lý.

Spring Kafka có các acknowledgment mode như RECORD, BATCH, MANUAL và MANUAL_IMMEDIATE (chi tiết phụ thuộc version/container config). Chọn mode theo cách listener xử lý và kiểm tra behavior khi exception, retry, shutdown và rebalance.

## 13. Runbook xử lý lag tăng

Thực hiện theo thứ tự để không tạo thêm tải trong lúc hệ thống đang nghẽn:

1. **Xác nhận impact**: xác định topic/group, business SLA, lag trend và liệu dữ liệu có bị mất hay chỉ chậm.
2. **Phân vùng lag**: tìm partition lag cao nhất, partition nào tăng nhanh và member đang sở hữu chúng.
3. **So sánh rates**: ingress, fetch, processed và committed records/s.
4. **Kiểm tra rebalance**: số member, assignment, restart, poll timeout, heartbeat và commit error.
5. **Kiểm tra hot key**: so sánh ingress/lag theo partition, key distribution và payload size.
6. **Kiểm tra application**: CPU, GC, handler duration, queue depth, thread pool và deserialization.
7. **Kiểm tra downstream**: DB pool/query/lock, HTTP latency/429/5xx, timeout và rate limit.
8. **Chọn biện pháp nhỏ nhất**: tối ưu query, batch, giảm retry, điều chỉnh concurrency/poll/fetch hoặc scale nếu partition và downstream còn capacity.
9. **Theo dõi catch-up**: lag growth phải giảm, processed rate phải vượt ingress trong thời gian catch-up.
10. **Xác minh business**: đối chiếu số event xử lý, duplicate, missing, thứ tự và downstream consistency.

### Khi nào cần giảm tải khẩn cấp?

Nếu DB/API downstream đang quá tải:

- Giảm concurrency hoặc giới hạn số request đồng thời.
- Pause một phần workload theo partition nếu cần, giữ consumer poll/heartbeat đúng cách.
- Tạm giảm producer ingress hoặc áp dụng quota nếu business cho phép.
- Ngừng retry nóng và áp dụng backoff/circuit breaker.
- Ưu tiên event theo business criticality nếu kiến trúc có topic/consumer group riêng.

Mục tiêu đầu tiên là ngăn downstream sụp hoàn toàn. Lag có thể tăng trong thời gian giảm tải có chủ đích; cần kiểm soát retention để đảm bảo backlog vẫn còn đủ thời gian xử lý.

## 14. Ví dụ chẩn đoán thực tế

### Tình huống A: Một partition lag tăng, các partition khác gần 0

Quan sát:

- Partition 4 tăng 2.000 records/s.
- Các partition khác giữ lag thấp.
- Consumer CPU tổng chỉ 35%.
- Một customer key chiếm phần lớn record ở partition 4.

Kết luận: nghi hot key hoặc key distribution skew. Thêm consumer không giúp nếu partition 4 vẫn chỉ được một consumer trong group xử lý. Kiểm tra business key, traffic tenant và xử lý mỗi record. Nếu cần sharding, thiết kế lại ordering/version semantics trước.

### Tình huống B: Tất cả partition lag tăng sau deploy

Quan sát:

- Ingress không đổi.
- Handler p95 tăng từ 40 ms lên 350 ms.
- DB connection pool active chạm max, pending tăng.
- Query p95 tăng mạnh.

Kết luận: regression hoặc downstream database saturation. Rollback release nếu thay đổi gây lỗi; kiểm tra query/index/transaction và pool. Không scale consumer trước khi database có headroom.

### Tình huống C: Lag tăng theo chu kỳ, sau đó giảm

Quan sát:

- Batch import tạo burst 20 phút.
- Consumer throughput cao hơn ingress sau khi import kết thúc.
- Lag giảm về baseline trong thời gian dự báo.
- Không có commit error/rebalance spike.

Kết luận: burst có thể là workload dự kiến. Kiểm tra catch-up time và retention/SLO; điều chỉnh capacity hoặc lịch batch nếu mục tiêu phục hồi không đạt.

### Tình huống D: Kafka lag thấp nhưng business delay cao

Quan sát:

- Consumer commit offset ngay sau khi đưa record vào executor.
- Executor queue tăng liên tục.
- Database write hoàn tất trễ nhiều phút.

Kết luận: backlog đã chuyển khỏi Kafka vào queue nội bộ. Thêm consumer có thể làm queue tăng nhanh hơn. Đưa queue depth/oldest task age vào alert, giới hạn queue, và chỉ commit theo semantics phù hợp với việc xử lý async.

## 15. Những hành động dễ gây sự cố hơn

| Hành động | Rủi ro | Cách làm an toàn |
|---|---|---|
| Tăng consumer replica vô điều kiện | Consumer dư idle hoặc DB/API bị quá tải | So sánh partition count và downstream headroom |
| Tăng partition ngay lập tức | Thay đổi key-to-partition mapping, ảnh hưởng ordering | Đánh giá key semantics và migration |
| Tăng max.poll.interval.ms để che handler treo | Phát hiện consumer hỏng chậm hơn | Đo batch processing và xử lý blocking |
| Tăng max.poll.records | Batch dài, memory cao, timeout/rebalance | Điều chỉnh theo p95/p99 processing |
| Tăng DB pool size | Tăng contention, vượt DB connection limit | Đo query/lock và capacity DB |
| Retry liên tục khi downstream lỗi | Khuếch đại tải và tăng lag | Backoff, jitter, circuit breaker, DLT |
| Reset offset để lag về 0 | Mất hoặc replay dữ liệu | Chỉ reset sau phê duyệt và dry-run |
| Commit trước khi async xử lý xong | Kafka lag thấp nhưng mất công việc khi crash | Quản lý commit theo completion |

## 16. Alert và SLO cho consumer lag

Không dùng một ngưỡng lag cố định cho mọi topic. Topic 10 records/s và topic 100.000 records/s có baseline khác nhau; một số pipeline cho phép backlog vài phút, số khác yêu cầu gần realtime.

Alert nên kết hợp:

- Lag tổng và lag lớn nhất theo partition.
- Tốc độ tăng lag trong cửa sổ 5/15 phút.
- Ước tính catch-up time.
- Tuổi record chưa xử lý hoặc end-to-end processing latency.
- Consumer throughput so với ingress.
- Rebalance/commit failure.
- Downstream saturation và queue age.

Ví dụ policy minh họa:

| Mức | Điều kiện ví dụ | Hành động |
|---|---|---|
| Warning | Lag tăng liên tục 10 phút hoặc catch-up time vượt mục tiêu cảnh báo | Kiểm tra dashboard và trend |
| Critical | Catch-up time vượt SLA hoặc oldest-event age sắp chạm retention/SLO | Incident response, xác định bottleneck |
| Emergency | Lag tăng nhanh, downstream lỗi lan rộng hoặc backlog sắp vượt retention | Giảm tải/fencing workload theo runbook |

Ngưỡng phải được đặt theo SLO, throughput bình thường, retention và khả năng catch-up đã đo trong load test. Alert chỉ dựa trên lag tổng có thể bỏ sót một partition nóng.

## 17. Checklist sau khi khắc phục

- [ ] Lag tổng và từng partition đã ổn định hoặc giảm theo kế hoạch.
- [ ] Consumer processed rate vượt ingress đủ lâu để catch up.
- [ ] Consumer group member và assignment ổn định.
- [ ] Không còn rebalance/commit failure bất thường.
- [ ] Handler latency, CPU, GC và thread pool trở về baseline.
- [ ] Database/API downstream hết saturation.
- [ ] Queue nội bộ không còn backlog ẩn.
- [ ] Không có duplicate/missing ngoài delivery policy.
- [ ] Ordering theo business key được giữ.
- [ ] Retention còn đủ thời gian để xử lý backlog.
- [ ] Ghi lại root cause, metric trước/sau, thay đổi cấu hình và rollback plan.

## 18. Bài tập tự kiểm tra

1. Consumer lag được tính từ những offset nào và vì sao không luôn bằng số business record chưa xử lý?
2. Vì sao cần đo fetch progress, processing progress và commit progress riêng?
3. Nếu chỉ partition 0 tăng lag, vì sao thêm consumer chưa chắc giúp?
4. Hot key ảnh hưởng throughput như thế nào?
5. Tăng partition có thể ảnh hưởng ordering của key cũ ra sao?
6. Vì sao DB connection pool cạn có thể làm Kafka lag tăng dù CPU consumer thấp?
7. Khi nào giảm max.poll.records có ích?
8. Tăng max.poll.interval.ms có thể che giấu vấn đề gì?
9. Vì sao commit offset trước khi async task hoàn tất tạo rủi ro?
10. Làm thế nào tính thời gian catch-up khi ingress vẫn tiếp tục?
11. Vì sao reset offset không phải biện pháp xử lý lag thông thường?
12. Dashboard/alert nào giúp phát hiện backlog đã chuyển sang queue nội bộ?

## Kết luận

Lag tăng là biểu hiện của mất cân bằng giữa ingress và tốc độ xử lý/commit. Điều tra phải đi từ lag tổng xuống từng partition và member, sau đó tách fetch, handler, commit và downstream latency. Nếu lag tập trung ở một partition, kiểm tra key skew/hot key; nếu mọi partition cùng tăng, tìm thiếu throughput tổng hoặc dependency chung bị nghẽn. Nếu Kafka lag thấp nhưng business delay cao, tìm queue nội bộ và async work sau commit.

Khắc phục theo nguyên nhân: tối ưu xử lý, batch và query; điều chỉnh concurrency khi có partition và downstream capacity; giới hạn retry và áp dụng backpressure; thay đổi key/partitioning chỉ sau khi đánh giá ordering. Theo dõi catch-up time và xác minh dữ liệu end-to-end sau thay đổi. Không reset offset hoặc tăng mọi cấu hình cùng lúc để làm lag biến mất trên dashboard.
