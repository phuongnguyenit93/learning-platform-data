# Consumer metrics: lag, tốc độ đọc, commit và rebalance

## Mục tiêu bài học

Consumer có thể vẫn kết nối Kafka nhưng xử lý chậm, commit offset muộn hoặc liên tục rebalance. Nếu chỉ kiểm tra process còn sống, nhóm vận hành sẽ khó biết backlog đang tăng ở partition nào, consumer nào đang nghẽn, commit có chậm hay group có đang mất ổn định.

Kafka cung cấp metrics ở client và broker để theo dõi hoạt động consumer. Các chỉ số quan trọng gồm consumer lag, records/bytes consumed rate, fetch latency, poll interval, commit latency, heartbeat và rebalance. Cần đọc các metric này cùng offset, application processing time và producer ingress để hiểu đúng trạng thái của pipeline.

Bài học tập trung vào consumer group thông thường của Kafka Java Consumer API. Share group có cơ chế record acknowledgement và metrics riêng, không dùng cùng cách diễn giải committed offset trong bài này.

Sau bài học, người học có thể:

- Giải thích consumer lag và phân biệt current position với committed offset.
- Đọc CURRENT-OFFSET, LOG-END-OFFSET và LAG bằng Kafka CLI.
- Theo dõi tốc độ đọc record/byte và fetch request.
- Phân biệt fetch throughput với tốc độ xử lý nghiệp vụ.
- Theo dõi poll interval, heartbeat và assigned partitions.
- Đọc commit latency, commit rate và nhận diện commit bị chậm.
- Theo dõi rebalance count, rate, latency và nguyên nhân thường gặp.
- Thu thập Kafka client/broker metrics qua JMX và Prometheus.
- Thiết kế dashboard, alert và SLO cho consumer.
- Chẩn đoán lag tăng, commit lỗi, rebalance liên tục và partition mất assignment.

## 1. Bức tranh quan sát consumer

Một consumer pipeline cần được quan sát ở ba lớp:

1. **Kafka client**: record/byte rate, fetch latency, lag, commit, heartbeat và rebalance.
2. **Kafka broker/group coordinator**: request rate, group state, rebalance rate, coordinator queue và broker health.
3. **Ứng dụng**: thời gian xử lý record, số record thành công/thất bại, retry, lỗi downstream và thời gian event chờ trong business workflow.

~~~mermaid
flowchart TB
    P[Producer ingress] --> T[Kafka topic partitions]
    T --> C[Consumer group]
    C --> A[Application processing]
    C -.-> M1[Client metrics]
    T -.-> M2[Broker metrics]
    A -.-> M3[Business metrics]
    M1 --> O[Prometheus / Grafana]
    M2 --> O
    M3 --> O
~~~

Không một metric đơn lẻ nào cho biết toàn bộ sức khỏe của consumer. Ví dụ, records-consumed-rate có thể cao trong khi business processing đang lỗi; records-lag-max có thể thấp vì consumer đã fetch record vào memory dù ứng dụng chưa xử lý xong. Cần kết hợp nhiều tín hiệu.

## 2. Consumer lag là gì?

Consumer lag biểu diễn khoảng cách giữa vị trí consumer đã đọc/commit và vị trí mới nhất có thể đọc trong partition. Lag thường được tính theo từng topic-partition.

Với một partition:

~~~text
Lag = Log end offset - Consumer offset
~~~

Ví dụ:

| Topic-partition | Current/committed offset | Log end offset | Offset lag |
|---|---:|---:|---:|
| orders-0 | 120 | 150 | 30 |
| orders-1 | 200 | 205 | 5 |
| orders-2 | 80 | 140 | 60 |

Trong ví dụ, partition orders-2 có lag lớn nhất. Tổng offset lag của group là 95; max lag trên một partition là 60. Cả hai cách tổng hợp đều hữu ích nhưng trả lời câu hỏi khác nhau.

### 2.1. Offset lag không phải thời gian chờ

Lag bằng 10.000 record không tự nói rằng record đã chờ 10 giây hay 10 phút. Nếu producer ghi 100 record/giây, 10.000 record tương đương khoảng 100 giây ingress; nếu producer ghi 10.000 record/giây, cùng lag chỉ tương đương khoảng một giây.

Để đo độ trễ theo thời gian, cần thêm:

- Timestamp của event hoặc timestamp broker append.
- Tuổi của record chưa xử lý lâu nhất.
- Tốc độ producer và tốc độ consumer theo cùng cửa sổ thời gian.
- Processing latency ở ứng dụng.

SLO thường nên kết hợp offset lag với event age. Ví dụ, đặt ngưỡng lag theo partition và cảnh báo khi tuổi của event chưa xử lý vượt SLA.

### 2.2. Current position và committed offset khác nhau

Kafka consumer có ít nhất hai khái niệm cần phân biệt:

- **Current position**: vị trí tiếp theo consumer sẽ đọc trong partition. Position có thể tiến lên khi consumer poll/fetch record.
- **Committed offset**: checkpoint mà group đã lưu trên broker; sau restart/rebalance, consumer thường tiếp tục từ vị trí này hoặc theo reset policy.

Consumer có thể đã poll record đến offset 500 nhưng mới commit đến offset 450. Current position đã tiến xa hơn committed offset. Nếu chỉ xem client metric dựa trên current position, lag có thể trông thấp hơn lượng công việc chưa được commit.

Trong Kafka 4.4:

- Metric client records-lag-max được tính dựa trên current offset, không phải committed offset.
- Lệnh kafka-consumer-groups.sh --describe hiển thị CURRENT-OFFSET, LOG-END-OFFSET và LAG dựa trên trạng thái group đã commit.

Vì vậy, hai số lag này có thể khác nhau. Khi điều tra replay sau restart hoặc commit bị trễ, hãy kiểm tra cả client metrics lẫn committed offsets.

### 2.3. Offset distance không luôn bằng số record thực tế

Offset là vị trí tăng dần trong log, không phải một bộ đếm liên tục của mọi record còn đọc được. Topic compacted, record bị xóa theo retention, transactional control records và các khoảng offset không còn tồn tại có thể khiến offset distance khác số record thực tế consumer sẽ nhận.

Lag vẫn hữu ích để theo dõi xu hướng, nhưng không nên diễn giải như số lượng business event chính xác trong mọi trường hợp.

## 3. Đọc lag bằng Kafka CLI

### 3.1. Xem tất cả consumer group

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

### 3.2. Xem offsets và lag của một group

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service
~~~

Ví dụ kết quả:

~~~text
GROUP          TOPIC   PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG  CONSUMER-ID
orders-service orders  0          120             150             30   consumer-a
orders-service orders  1          200             205             5    consumer-b
orders-service orders  2          80              140             60   consumer-c
~~~

Đọc các cột:

- CURRENT-OFFSET: offset đã commit của group.
- LOG-END-OFFSET: vị trí cuối của log theo thông tin broker trả về.
- LAG: khoảng cách giữa log end và committed offset.
- CONSUMER-ID: member hiện đang được gán partition nếu group đang hoạt động.

Nếu CURRENT-OFFSET là dấu gạch ngang hoặc không có dữ liệu, group có thể chưa commit offset cho partition đó. Khi đó lag có thể không được tính như một số thông thường.

### 3.3. Xem member và assignment

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
~~~

Lệnh giúp xác định consumer nào đang sở hữu partition, host/client ID và assignment. Nếu group có nhiều member nhưng chỉ một vài member có partition, cần kiểm tra partition count, subscription và trạng thái rebalance.

### 3.4. Xem trạng thái group

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --state
~~~

Trạng thái Stable cho biết group đã hoàn tất assignment tại thời điểm quan sát. PreparingRebalance, CompletingRebalance hoặc trạng thái tương đương cho thấy group đang chuyển trạng thái. Tên state có thể khác giữa classic group protocol và consumer group protocol mới.

### 3.5. Lưu ý khi đọc kết quả

- CLI là ảnh chụp trạng thái tại thời điểm gọi, không phải time series.
- Chạy lại theo chu kỳ để xác định lag đang tăng, giảm hay đứng yên.
- So sánh từng partition; tổng lag có thể che khuất một partition nóng.
- Nếu consumer vừa restart, offset có thể chưa được commit hoặc assignment chưa ổn định.
- Với read_committed, transaction chưa hoàn tất có thể ảnh hưởng phần dữ liệu consumer được phép nhìn thấy.

Với consumer dùng isolation.level=read_committed, consumer không đọc vượt last stable offset (LSO) của partition. Nếu producer transaction còn mở, log end offset có thể tiến nhưng phần record phía sau transaction chưa visible với consumer read_committed. Khi lag có vẻ không giảm dù consumer vẫn fetch bình thường, hãy kiểm tra transaction đang mở và LSO thay vì chỉ nhìn log end offset.

## 4. Metrics tốc độ đọc và fetch

Kafka Java consumer phát metrics qua JMX. Các metric dưới đây có trong nhóm Consumer Fetch Metrics của Kafka 4.4; tên hoặc tập metric có thể khác theo client version.

| Metric | Ý nghĩa | Cách dùng |
|---|---|---|
| records-consumed-rate | Số record consumer nhận mỗi giây | Theo dõi throughput record |
| records-consumed-total | Tổng record đã nhận | Tính rate giữa hai lần scrape |
| bytes-consumed-rate | Số byte nhận mỗi giây | Theo dõi throughput dữ liệu |
| bytes-consumed-total | Tổng byte đã nhận | Phân tích xu hướng tải |
| fetch-rate | Số fetch request mỗi giây | Theo dõi hoạt động đọc từ broker |
| fetch-total | Tổng fetch request | Tính rate hoặc điều tra bất thường |
| fetch-size-avg | Kích thước fetch trung bình | Đánh giá batching |
| fetch-size-max | Kích thước fetch lớn nhất | Phát hiện batch lớn |
| records-per-request-avg | Số record trung bình mỗi request | Đánh giá hiệu quả fetch |
| fetch-latency-avg | Thời gian fetch trung bình | Phát hiện broker/network chậm |
| fetch-latency-max | Thời gian fetch lớn nhất | Tìm spike latency |
| fetch-throttle-time-avg | Thời gian fetch bị quota throttle trung bình | Phát hiện consumer bị giới hạn băng thông |
| fetch-throttle-time-max | Thời gian throttle lớn nhất | Điều tra spike throttle |

### 4.1. records-consumed-rate và tốc độ xử lý nghiệp vụ

records-consumed-rate là metric phía Kafka consumer client. Nó cho biết client đang nhận record với tốc độ nào; không chứng minh rằng nghiệp vụ cho từng record đã hoàn tất thành công.

Ví dụ:

- Consumer nhận 8.000 record/giây.
- Business handler chỉ xử lý thành công 5.000 record/giây.
- Phần còn lại có thể đang nằm trong batch, queue nội bộ, retry hoặc bị lỗi.

Ứng dụng nên tự ghi thêm:

- records-processed-rate: số record xử lý nghiệp vụ thành công mỗi giây.
- records-processing-error-rate: số lần xử lý lỗi mỗi giây.
- processing-duration: histogram/timer của thời gian xử lý.
- retry-rate: số record được retry.

Không gộp fetched rate với processed rate thành một metric vì hai giai đoạn có thể lệch nhau.

### 4.2. bytes-consumed-rate

Hai consumer có cùng records-consumed-rate nhưng kích thước payload khác nhau có thể tạo tải network và disk rất khác. Theo dõi cả record rate và byte rate giúp phát hiện:

- Payload tăng kích thước.
- Compression thay đổi.
- Một số topic có record lớn bất thường.
- Fetch throughput bị giới hạn bởi network hoặc broker.

### 4.3. Fetch latency và fetch size

Nếu fetch-latency tăng cùng fetch-size giảm, có thể consumer đang chờ dữ liệu, broker phản hồi chậm hoặc network gặp vấn đề. Nếu fetch-throttle-time tăng, kiểm tra quota theo user/client ID và broker.

fetch-size-avg quá nhỏ cùng fetch-rate cao có thể cho thấy request batching chưa hiệu quả. Tuy nhiên, fetch.min.bytes và fetch.max.wait.ms là trade-off giữa throughput và latency; tăng batch có thể làm consumer chờ lâu hơn trước khi nhận dữ liệu.

### 4.4. Metrics theo topic và partition

Kafka xuất một số metric theo topic và theo topic-partition. Nên giữ chiều phân tích:

- client.id để biết instance nào đang đọc.
- topic để biết workload nào có vấn đề.
- partition để tìm partition nóng hoặc bị nghẽn.

Tên MBean có thể chứa tag topic/partition. Khi scrape bằng JMX exporter, kiểm tra rule để bảo đảm dấu chấm trong tên topic được xử lý theo cách không tạo metric trùng; Kafka 4.4 khuyến nghị dùng tên topic thực thay cho metric alias thay dấu chấm bằng dấu gạch dưới đã deprecated.

## 5. Poll interval và thời gian ứng dụng xử lý

Một consumer có thể fetch nhanh nhưng xử lý chậm vì business handler, database hoặc HTTP dependency.

Các consumer metrics cần quan sát:

| Metric | Ý nghĩa | Dấu hiệu cần chú ý |
|---|---|---|
| time-between-poll-avg | Khoảng cách trung bình giữa hai lần poll | Tăng so với baseline |
| time-between-poll-max | Khoảng cách lớn nhất giữa hai lần poll | Tiến gần max.poll.interval.ms |
| last-poll-seconds-ago | Số giây từ lần poll gần nhất | Tăng bất thường |
| poll-idle-ratio-avg | Tỷ lệ thời gian poll ở trạng thái idle | Quá cao hoặc quá thấp cần đặt trong ngữ cảnh tải |

poll-idle-ratio-avg cao có thể nghĩa là consumer thường chờ record vì topic ít dữ liệu. Nó không tự động chứng minh consumer bị lỗi. Giá trị thấp có thể nghĩa là thread ứng dụng dành nhiều thời gian xử lý record giữa các lần poll.

### 5.1. max.poll.interval.ms

max.poll.interval.ms giới hạn thời gian tối đa giữa các lần gọi poll() khi consumer đã nhận record. Nếu ứng dụng xử lý một batch quá lâu rồi không poll tiếp, consumer có thể bị xem là không còn tiến triển và rời group, dẫn đến rebalance.

Ví dụ:

~~~properties
group.protocol=classic
max.poll.records=200
max.poll.interval.ms=300000
session.timeout.ms=45000
heartbeat.interval.ms=15000
~~~

Đây là cấu hình minh họa cho classic group protocol, không phải giá trị khuyến nghị cho mọi workload. Với group.protocol=consumer, heartbeat interval và session timeout được điều khiển bằng broker configs group.consumer.heartbeat.interval.ms và group.consumer.session.timeout.ms; hai client configs heartbeat.interval.ms và session.timeout.ms không được hỗ trợ trong protocol này. Cần chọn max.poll.records dựa trên p95/p99 processing time và chọn max.poll.interval.ms đủ lớn cho thời gian xử lý batch có kiểm soát.

max.poll.records chỉ giới hạn số record trả về trong một lần poll; nó không giới hạn lượng dữ liệu mà consumer fetch từ broker. Consumer có thể cache record đã fetch rồi trả dần qua các lần poll.

### 5.2. Không tăng max.poll.interval.ms để che giấu xử lý chậm

Nếu xử lý batch mất nhiều phút, chỉ tăng max.poll.interval.ms có thể làm chậm phát hiện consumer bị treo. Trước tiên hãy đo thời gian xử lý, giảm batch, tối ưu downstream hoặc thiết kế worker queue có giới hạn.

Nếu chuyển xử lý sang executor:

- Consumer thread vẫn phải poll đều đặn.
- Chỉ commit offset sau khi worker hoàn tất xử lý tương ứng.
- Queue phải có giới hạn để tránh fetch quá nhiều record chưa xử lý.
- Cần quản lý partition revocation và shutdown để không commit nhầm offset.
- Side effect phải idempotent vì record có thể được giao lại.

## 6. Commit metrics

Commit offset cho broker biết vị trí consumer group đã xác nhận xử lý. Commit quá thường xuyên làm tăng request/coordinator load; commit quá thưa làm tăng số record có thể phải đọc lại sau crash.

Kafka 4.4 consumer coordinator metrics gồm:

| Metric | Ý nghĩa |
|---|---|
| commit-latency-avg | Thời gian trung bình của commit request |
| commit-latency-max | Thời gian commit lớn nhất |
| commit-rate | Số lần gọi commit mỗi giây |
| commit-total | Tổng số lần gọi commit |

Kafka còn có committed-time-ns-total và commit-sync-time-ns-total trong consumer metrics ở các client/version hỗ trợ. Các metric này giúp đánh giá thời gian client dành cho thao tác commit.

### 6.1. Commit đồng bộ

commitSync() chờ broker trả kết quả. Nó dễ hiểu và phù hợp với một số pipeline cần checkpoint sau khi xử lý xong batch, nhưng làm consumer thread chờ nếu coordinator hoặc network chậm.

~~~java
ConsumerRecords<String, String> records =
    consumer.poll(Duration.ofMillis(1000));

for (ConsumerRecord<String, String> record : records) {
    orderService.process(record.value());
}

consumer.commitSync();
~~~

Đoạn code trên chỉ phù hợp khi xử lý đồng bộ và mọi record trong batch đã hoàn tất trước commit. Nếu process ném exception giữa batch, không nên commit toàn bộ batch như thể tất cả record đã xử lý thành công.

### 6.2. Commit bất đồng bộ

commitAsync() không chặn thread chờ response như commitSync(). Cần kiểm tra callback để phát hiện commit failure:

~~~java
consumer.commitAsync((offsets, exception) -> {
    if (exception != null) {
        log.error("Kafka offset commit failed: {}", offsets, exception);
        commitFailureCounter.increment();
    }
});
~~~

Không bỏ qua exception trong callback. Nếu commit thất bại, record có thể được xử lý lại sau restart hoặc rebalance. Side effect cần idempotent.

### 6.3. Commit offset tường minh

Khi cần commit đến offset cụ thể, truyền offset kế tiếp cần đọc:

~~~java
import java.util.Map;

import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

TopicPartition partition = new TopicPartition("orders", 0);
long lastProcessedOffset = 149L;

Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
    partition,
    new OffsetAndMetadata(lastProcessedOffset + 1)
);

consumer.commitSync(offsets);
~~~

Kafka lưu offset kế tiếp cần đọc, vì vậy sau khi xử lý record offset 149, committed offset là 150.

### 6.4. Enable auto commit

enable.auto.commit=true cho phép client tự commit offset theo auto.commit.interval.ms. Cách này đơn giản nhưng không tự biết business processing đã hoàn tất hay chưa. Nếu ứng dụng xử lý record lâu hoặc bất đồng bộ, auto commit có thể tiến offset trước khi side effect hoàn tất.

Với pipeline cần kiểm soát xử lý, thường dùng enable.auto.commit=false và commit sau khi xử lý thành công. Cấu hình phải đi cùng logic xử lý lỗi và rebalance.

### 6.5. Commit latency tăng thì kiểm tra gì?

- Network round-trip từ client đến coordinator.
- Coordinator đang load hoặc chuyển leader.
- Group liên tục rebalance.
- Broker request queue hoặc group coordinator queue bị nghẽn.
- Commit quá thường xuyên với nhiều partition.
- Application thread bị chặn bởi commitSync().
- Authentication/authorization hoặc lỗi coordinator.

Commit latency cao không đồng nghĩa chắc chắn broker disk chậm. Offset commit được xử lý qua group coordinator và internal offsets topic; cần đối chiếu broker/coordinator metrics.

## 7. Rebalance metrics

Rebalance là quá trình Kafka phân phối lại partition giữa các member của consumer group. Rebalance xảy ra khi membership, subscription hoặc topology partition thay đổi.

Các consumer coordinator metrics trong Kafka 4.4:

| Metric | Ý nghĩa |
|---|---|
| rebalance-latency-avg | Thời gian rebalance trung bình |
| rebalance-latency-max | Thời gian rebalance lớn nhất |
| rebalance-latency-total | Tổng thời gian tham gia rebalance |
| rebalance-total | Tổng số rebalance |
| rebalance-rate-per-hour | Số lần rebalance theo giờ |
| failed-rebalance-total | Tổng số rebalance thất bại |
| failed-rebalance-rate-per-hour | Tốc độ rebalance thất bại |
| last-rebalance-seconds-ago | Số giây từ lần rebalance gần nhất |
| partitions-revoked-latency-avg/max | Thời gian callback thu hồi partition |
| partitions-assigned-latency-avg/max | Thời gian callback gán partition |
| partitions-lost-latency-avg/max | Thời gian callback khi partition bị mất |

Kết hợp các metric này với assigned-partitions, heartbeat-rate, heartbeat-response-time-max, join-time-avg/max và sync-time-avg/max để hiểu group đang mất thời gian ở bước nào.

### 7.1. Nguyên nhân rebalance thường gặp

- Consumer instance mới tham gia group.
- Consumer rời group hoặc process bị kill.
- Heartbeat không đến coordinator trong session timeout.
- Ứng dụng không gọi poll trong thời gian vượt max.poll.interval.ms.
- Topic được thêm/xóa partition.
- Subscription của consumer thay đổi.
- Deployment restart nhiều instance cùng lúc.
- Consumer xử lý quá lâu trong callback rebalance.
- Coordinator hoặc broker gặp lỗi, mất kết nối.

Rebalance thỉnh thoảng là bình thường. Rebalance liên tục làm giảm thời gian xử lý hữu ích và có thể khiến lag tăng.

### 7.2. ConsumerRebalanceListener

Có thể ghi log assignment/revocation để đối chiếu với metrics:

~~~java
import java.util.Collection;
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRebalanceListener;
import org.apache.kafka.common.TopicPartition;

consumer.subscribe(
    List.of("orders"),
    new ConsumerRebalanceListener() {
        @Override
        public void onPartitionsRevoked(
                Collection<TopicPartition> partitions) {
            log.info("Partitions revoked: {}", partitions);
            commitProcessedOffsets(partitions);
        }

        @Override
        public void onPartitionsAssigned(
                Collection<TopicPartition> partitions) {
            log.info("Partitions assigned: {}", partitions);
        }

        @Override
        public void onPartitionsLost(
                Collection<TopicPartition> partitions) {
            log.warn("Partitions lost: {}", partitions);
            discardUncommittedLocalState(partitions);
        }
    }
);
~~~

commitProcessedOffsets và discardUncommittedLocalState là hàm ứng dụng minh họa. Callback cần hoàn tất nhanh; tránh gọi HTTP hoặc thao tác chậm trong callback. Chỉ commit offset đã xử lý thành công và còn thuộc quyền sở hữu của consumer.

onPartitionsLost biểu thị partition đã bị mất quyền sở hữu; không nên giả định consumer vẫn có thể commit an toàn cho các partition đó.

Các callback được gọi trên user thread trong quá trình poll(). Nếu callback ném exception, exception sẽ truyền ra lần poll đang thực thi callback. Giữ callback ngắn và không chờ service bên ngoài. Trong ví dụ, onPartitionsLost được override riêng để bỏ state cục bộ; nếu không override, implementation mặc định gọi onPartitionsRevoked.

### 7.3. Broker-side rebalance metrics

Kafka 4.4 group coordinator có metrics ở broker:

| Metric | Ý nghĩa |
|---|---|
| consumer-group-rebalance-rate | Tốc độ rebalance của consumer group |
| consumer-group-rebalance-count | Tổng số rebalance |
| consumer-group-count theo state | Số group theo Empty, Assigning, Reconciling, Stable hoặc Dead |
| event-queue-size | Số event đang chờ coordinator xử lý |
| event-queue-time-ms-p95/p99 | Thời gian event chờ trong queue |
| event-processing-time-ms-p95/p99 | Thời gian coordinator xử lý event |

Client metrics trả lời câu hỏi một consumer cụ thể đang trải qua điều gì. Broker metrics cho biết coordinator đang chịu tải ra sao và nhiều group có bị ảnh hưởng cùng lúc hay không.

## 8. JMX và Prometheus

Kafka broker và Java clients cung cấp metrics qua JMX. Client có registry metric riêng; broker sử dụng metrics registry phía server. Có thể quan sát bằng JConsole hoặc thu thập qua JMX exporter/metrics reporter.

### 8.0. Tìm đúng JMX MBean

Các nhóm MBean thường gặp trong Kafka 4.4:

| MBean object name | Metrics tiêu biểu |
|---|---|
| kafka.consumer:type=consumer-metrics,client-id={client-id} | time-between-poll-avg/max, last-poll-seconds-ago, poll-idle-ratio-avg |
| kafka.consumer:type=consumer-coordinator-metrics,client-id={client-id} | commit-latency, heartbeat, assigned-partitions, rebalance và join/sync metrics |
| kafka.consumer:type=consumer-fetch-manager-metrics,client-id={client-id} | records-consumed-rate, bytes-consumed-rate, fetch-latency, records-lag-max |
| kafka.consumer:type=consumer-fetch-manager-metrics,client-id={client-id},topic={topic},partition={partition} | records-lag, records-lag-avg/max và records-lead |
| kafka.server:type=group-coordinator-metrics,name=consumer-group-rebalance-rate | Rebalance rate ở broker |
| kafka.server:type=group-coordinator-metrics,name=consumer-group-rebalance-count | Tổng số rebalance ở broker |

MBean object name có thể thay đổi theo Kafka version và metric recording level. Khi scrape, đặt client.id riêng và ổn định cho mỗi consumer instance để phân biệt metric. Có thể gắn group, service và environment thành static labels ở cấu hình exporter; không tạo label động theo event.

### 8.1. Kiểm tra metrics bằng JConsole

Trong môi trường local:

1. Khởi chạy broker hoặc consumer Java.
2. Mở jconsole.
3. Kết nối đến process Java tương ứng.
4. Tìm MBean bắt đầu bằng kafka.consumer.
5. Mở các nhóm consumer-metrics, consumer-coordinator-metrics và consumer-fetch-manager-metrics.
6. Ghi lại metric và client-id để đối chiếu với log.

JMX remote bị tắt mặc định trong Kafka. Nếu bật remote JMX, phải cấu hình authentication, authorization/network boundary và TLS theo chính sách vận hành; không phơi cổng JMX không bảo vệ ra mạng công cộng.

### 8.2. Thu thập bằng JMX Exporter

Một kiến trúc phổ biến:

~~~text
Kafka broker / Java consumer
          |
          v
        JMX
          |
          v
  Prometheus JMX Exporter
          |
          v
     Prometheus
          |
          v
       Grafana
~~~

Exporter có thể chạy dưới dạng Java agent trong process hoặc service riêng tùy cách triển khai. Ví dụ chạy agent:

~~~bash
java \
  -javaagent:/opt/jmx_prometheus_javaagent.jar=9404:/etc/kafka/jmx-exporter.yml \
  -jar consumer-service.jar
~~~

Đây là ví dụ minh họa; đường dẫn, port và rule phải phù hợp môi trường. JMX Exporter rule quyết định cách MBean attributes được chuyển thành Prometheus metric names/labels. Vì vậy, tên Prometheus cuối cùng có thể khác tên attribute gốc của Kafka.

### 8.3. Spring Boot và Micrometer

Với Spring Boot, có thể dùng Actuator và Prometheus registry để xuất application metrics:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Kafka client native metrics vẫn có thể được thu thập qua JMX exporter. Dùng Micrometer để bổ sung metric ở tầng business như processing duration, records processed, handler errors và retry count.

Ví dụ đo thời gian xử lý một record:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.apache.kafka.clients.consumer.ConsumerRecord;

public class OrderRecordHandler {

    private final MeterRegistry meterRegistry;
    private final OrderService orderService;

    public OrderRecordHandler(
            MeterRegistry meterRegistry,
            OrderService orderService) {
        this.meterRegistry = meterRegistry;
        this.orderService = orderService;
    }

    public void handle(ConsumerRecord<String, String> record) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String result = "success";

        try {
            orderService.process(record.value());
        } catch (RuntimeException ex) {
            result = "error";
            throw ex;
        } finally {
            sample.stop(
                Timer.builder("app.kafka.consumer.processing")
                    .description("Business processing duration per record")
                    .tag("topic", record.topic())
                    .tag("result", result)
                    .register(meterRegistry)
            );
        }
    }
}
~~~

OrderService là service nghiệp vụ minh họa. Metric tag nên có cardinality thấp; topic và result thường ổn định. Không đưa orderId, customerId, key, offset hoặc exception message vào tag vì mỗi giá trị có thể tạo time series mới.

### 8.4. Bảo mật metrics

- Chỉ expose metrics endpoint trong mạng quản trị.
- Bật authentication/TLS khi scrape qua mạng không tin cậy.
- Không expose JMX remote không có authentication.
- Giới hạn metric labels để tránh rò rỉ dữ liệu nghiệp vụ.
- Không đưa payload hoặc thông tin cá nhân vào log/metric.
- Tách quyền đọc dashboard khỏi quyền quản trị Kafka.

## 9. Dashboard cho consumer group

Một dashboard thực tế nên có các hàng panel sau:

| Nhóm | Panel | Mục đích |
|---|---|---|
| Lag | Max lag theo partition | Tìm partition đang nghẽn |
| Lag | Tổng lag theo group | Theo dõi backlog toàn group |
| Lag | Oldest event age | Đo thời gian chờ gần với SLA |
| Throughput | records-consumed-rate | Tốc độ nhận record |
| Throughput | bytes-consumed-rate | Tốc độ dữ liệu |
| Throughput | records-processed-rate | Tốc độ xử lý nghiệp vụ |
| Fetch | fetch-latency và fetch-size | Phát hiện broker/network/batching |
| Commit | commit-latency-avg/max | Theo dõi checkpoint |
| Commit | commit-rate và commit failures | Phát hiện commit quá nhiều hoặc lỗi |
| Rebalance | rebalance-rate và latency | Phát hiện group không ổn định |
| Assignment | assigned-partitions theo client | Phát hiện consumer không có partition |
| Liveness | last-poll-seconds-ago | Phát hiện consumer không poll |
| Health | heartbeat-response-time-max | Phát hiện coordinator/network chậm |
| Application | processing duration/error/retry | Phân biệt fetch với business processing |

### 9.1. Chiều phân tích

Nên có filter cho:

- cluster.
- consumer group.
- client ID hoặc instance.
- topic.
- partition.
- environment.

Không đưa event ID hoặc customer ID vào dashboard metric labels. Nếu cần điều tra một event cụ thể, dùng log có cấu trúc hoặc distributed trace.

### 9.2. So sánh producer ingress và consumer throughput

Đặt producer record-send-rate cạnh consumer records-consumed-rate và application processed rate. Nếu producer ingress liên tục cao hơn consumer processing, backlog sẽ tăng. Nếu fetch rate thấp nhưng producer ingress cũng thấp, có thể chỉ là topic ít dữ liệu chứ không phải consumer bị nghẽn.

Nếu fetched rate cao nhưng processed rate thấp, kiểm tra queue nội bộ, batch processing, downstream database, retry và thread utilization.

## 10. Alert và SLO

Không có một ngưỡng lag phù hợp cho mọi topic. Topic thanh toán có thể cần lag thấp trong vài giây; topic analytics batch có thể chấp nhận lag lớn hơn nhiều.

### 10.1. Alert đề xuất

| Alert | Điều kiện gợi ý | Ý nghĩa |
|---|---|---|
| Consumer lag high | Max lag vượt ngưỡng liên tục trong 5 phút | Consumer không theo kịp |
| Lag growth | Lag tăng liên tục trong nhiều cửa sổ | Producer ingress lớn hơn processing |
| Oldest event age | Event age vượt SLO | Người dùng/business bị trễ |
| No consumption | Có producer ingress nhưng records-consumed-rate gần 0 | Consumer dừng, mất assignment hoặc fetch lỗi |
| Processing gap | Fetched rate cao nhưng processed rate thấp | Application handler/queue bị nghẽn |
| Commit latency high | commit-latency-max vượt ngân sách | Coordinator/network/commit path chậm |
| Commit failure | Application commit error counter tăng | Offset có thể không được lưu |
| Rebalance storm | rebalance-rate tăng liên tục | Group membership hoặc poll loop không ổn định |
| No assignment | assigned-partitions = 0 ngoài thời gian deploy | Consumer chưa tham gia group hoặc subscription sai |
| Poll stalled | last-poll-seconds-ago tiến gần max.poll.interval.ms | Consumer xử lý quá lâu hoặc bị treo |
| Fetch throttled | fetch-throttle-time tăng liên tục | Quota giới hạn consumer |

### 10.2. Tránh alert giả

- Dùng cửa sổ thời gian và yêu cầu tình trạng kéo dài thay vì alert từ một spike.
- Bỏ qua thời gian deploy/rebalance có kế hoạch hoặc dùng silence có thời hạn.
- Phân biệt topic ít traffic với consumer không hoạt động.
- Alert theo partition max để phát hiện hot partition, không chỉ theo tổng group.
- Kết hợp lag với event age để phản ánh tác động business.
- Không dùng một ngưỡng offset lag chung cho tất cả topic.

### 10.3. Định nghĩa SLO

Ví dụ SLO cho luồng order:

- 99% event được xử lý trong vòng 10 giây kể từ khi broker append.
- Không partition nào duy trì lag trên 5.000 record quá 5 phút.
- Commit failure rate bằng 0 trong điều kiện hoạt động bình thường.
- Rebalance không chủ đích dưới một ngưỡng theo giờ.

Đây chỉ là ví dụ. Chọn ngưỡng theo traffic, retention, business deadline và khả năng xử lý của downstream.

## 11. Chẩn đoán các tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Lag tăng đều | Consumer throughput thấp hơn producer ingress | So sánh producer rate, consumed rate và processed rate |
| Lag cao ở một partition | Hot key, partition skew hoặc consumer chậm | Xem lag từng partition, key distribution và assigned member |
| Client records-lag thấp nhưng CLI lag cao | Consumer đã fetch record nhưng chưa commit | So sánh current position với committed offset |
| records-consumed-rate cao nhưng business chậm | Queue nội bộ hoặc handler chậm | Đo processing duration, queue depth và downstream latency |
| Fetch latency cao | Broker, network, throttling hoặc fetch config | Xem fetch latency, throttle time và broker request metrics |
| Commit latency cao | Coordinator/network chậm hoặc commit quá thường xuyên | Kiểm tra commit rate, coordinator queue và network |
| Rebalance liên tục | Poll chậm, member restart, heartbeat timeout hoặc subscription thay đổi | Xem rebalance rate, poll interval, heartbeat và deployment events |
| assigned-partitions bằng 0 | Consumer chưa join, topic subscription sai hoặc group đang rebalance | Xem group state, members và topic metadata |
| Một consumer có lag cao hơn nhiều | Workload lệch partition hoặc instance yếu | So sánh assignment, CPU, processing time và throughput |
| Commit failure sau rebalance | Commit offset cho partition đã mất ownership | Kiểm tra callback revoked/lost và offset map |
| Lag chỉ tăng khi traffic spike | Capacity không đủ cho peak hoặc scale phản ứng chậm | Load test, tăng consumer/partition nếu còn khả năng song song |
| Consumer idle dù lag còn | Fetch/authorization lỗi, partition chưa assign hoặc handler bị block | Kiểm tra logs, assignment, fetch errors và poll state |

## 12. Quy trình điều tra lag tăng

Thực hiện theo thứ tự để nhanh chóng khoanh vùng:

1. Dùng kafka-consumer-groups.sh --describe để xác định group, topic và partition có lag cao.
2. Xem --members và --state để xác định consumer nào đang sở hữu partition.
3. So sánh producer ingress, records-consumed-rate và application processed rate.
4. Kiểm tra records-lag-max ở client và committed lag ở CLI.
5. Xem fetch latency, fetch throttle và bytes-consumed-rate.
6. Kiểm tra processing duration, queue depth và downstream error.
7. Xem commit latency/rate và commit failure logs.
8. Kiểm tra rebalance rate, last poll và heartbeat.
9. Xác minh broker request latency, coordinator queue và broker health.
10. Chọn hành động phù hợp rồi theo dõi lag có giảm bền vững hay không.

Không tăng consumer count ngay lập tức nếu số partition đã giới hạn concurrency hoặc downstream đang nghẽn. Thêm consumer có thể làm tăng rebalance và connection load mà không tăng throughput.

## 13. Tối ưu dựa trên metrics

### 13.1. Nếu consumer processing chậm

- Đo thời gian handler theo p50/p95/p99.
- Giảm max.poll.records nếu batch quá lớn.
- Tối ưu database query và remote call.
- Dùng batch write nếu nghiệp vụ cho phép.
- Đặt giới hạn concurrency và queue.
- Tách công việc nặng sang worker nhưng vẫn quản lý poll/commit đúng cách.

### 13.2. Nếu fetch throughput thấp

- Kiểm tra fetch-size-avg và records-per-request-avg.
- Xem fetch.min.bytes và fetch.max.wait.ms.
- Kiểm tra fetch-throttle-time.
- Xem broker network processor/request handler idle ratio.
- Kiểm tra consumer có đủ partition assignment không.

### 13.3. Nếu commit chậm

- Tránh commit sau từng record nếu không cần.
- Chọn commit theo batch đã xử lý thành công.
- Dùng commitAsync có callback khi phù hợp.
- Không bỏ qua commit errors.
- Kiểm tra coordinator và offsets topic health.

### 13.4. Nếu rebalance liên tục

- Giữ thời gian xử lý batch dưới max.poll.interval.ms.
- Điều chỉnh max.poll.records theo processing latency.
- Dùng graceful shutdown khi deploy.
- Tránh restart đồng thời toàn bộ member.
- Đặt subscription ổn định.
- Cân nhắc static membership bằng group.instance.id nếu workload phù hợp và hiểu trade-off phát hiện member chết. Static membership có thể giảm rebalance khi restart ngắn, nhưng member chết có thể giữ assignment đến khi session timeout hết hạn.
- Chọn partition assignment strategy phù hợp với yêu cầu chuyển partition và thời gian rebalance.

### 13.5. Khi nào tăng số consumer?

Chỉ tăng consumer khi:

- Group lag tăng và processing capacity là bottleneck.
- Topic có đủ partition để phân phối thêm consumer.
- Downstream còn capacity.
- Assignment hiện tại cho thấy consumer đang bận.
- Rebalance và network overhead vẫn nằm trong ngân sách.

Nếu topic có 6 partition, group có 20 consumer thì tối đa 6 consumer có thể được gán partition trong consumer group truyền thống. Thêm 14 consumer còn lại không làm tăng throughput đọc từ topic đó.

## 14. Broker metrics hỗ trợ chẩn đoán consumer

Client metrics cho biết trải nghiệm của consumer. Broker metrics giúp xác định vấn đề nằm ở broker hay coordinator.

| Broker metric | Ý nghĩa | Dấu hiệu |
|---|---|---|
| RequestMetrics ErrorsPerSec | Tỷ lệ lỗi theo request/error | Fetch/commit errors tăng |
| RequestQueueTimeMs | Thời gian request chờ trong queue | Broker quá tải |
| LocalTimeMs | Thời gian broker xử lý request | Broker xử lý chậm |
| ResponseQueueTimeMs | Thời gian chờ response queue | Network processor/queue nghẽn |
| NetworkProcessorAvgIdlePercent | Tỷ lệ network processor idle | Quá thấp có thể quá tải |
| RequestHandlerAvgIdlePercent | Tỷ lệ request handler idle | Quá thấp có thể quá tải |
| consumer-group-rebalance-rate | Tốc độ rebalance toàn cluster | Nhiều group cùng bất ổn |
| event-queue-time-ms-p95/p99 | Thời gian group coordinator event chờ xử lý | Coordinator queue nghẽn |
| partition-load-time-max | Thời gian load group metadata/offset partition | Group coordinator chậm phục hồi |

Không kết luận broker quá tải chỉ từ một metric. Đối chiếu CPU, disk I/O, network, request queue và replica health.

## 15. Bài tập thực hành

### Bài tập 1: Đọc consumer lag

1. Tạo topic orders có ba partition.
2. Chạy một consumer group và gửi 1.000 record.
3. Dùng kafka-consumer-groups.sh --describe để đọc CURRENT-OFFSET, LOG-END-OFFSET và LAG.
4. Tạm dừng consumer, tiếp tục gửi record và quan sát lag tăng.
5. Khởi động consumer lại và quan sát lag giảm.

### Bài tập 2: So sánh current position với committed offset

1. Tắt auto commit.
2. Poll một batch record.
3. Chờ trước khi xử lý hoặc commit.
4. So sánh records-lag-max với CLI lag.
5. Commit offset sau khi xử lý và quan sát hai chỉ số hội tụ.

### Bài tập 3: Theo dõi tốc độ đọc

1. Gửi record với tốc độ ổn định.
2. Thu thập records-consumed-rate và bytes-consumed-rate.
3. Thay đổi kích thước payload.
4. So sánh fetch-size-avg, records-per-request-avg và fetch-latency-avg.
5. Thêm application processing timer để phân biệt fetch với business processing.

### Bài tập 4: Theo dõi commit

1. Thử commitSync sau mỗi record.
2. Thử commitSync sau mỗi batch.
3. Thử commitAsync và xử lý callback.
4. So sánh commit-rate và commit-latency.
5. Mô phỏng commit failure trong môi trường lab và xác minh replay/idempotency.

### Bài tập 5: Tạo rebalance có chủ đích

1. Chạy hai consumer cùng group.
2. Thêm consumer thứ ba.
3. Dừng một consumer.
4. Quan sát rebalance-total, rebalance-latency-max và assigned-partitions.
5. Thử xử lý batch quá lâu để tiến gần max.poll.interval.ms.
6. Sửa poll/processing strategy và xác minh rebalance giảm.

### Bài tập 6: Dashboard và alert

1. Bật JMX metrics cho consumer trong môi trường lab.
2. Scrape bằng Prometheus/JMX exporter.
3. Tạo dashboard lag, throughput, commit và rebalance.
4. Tạo alert lag tăng liên tục và no-consumption.
5. Tạo traffic spike và kiểm tra alert có phản ánh đúng tình trạng hay không.

## 16. Câu hỏi tự kiểm tra

1. Consumer lag được tính từ những offset nào?
2. Current position khác committed offset như thế nào?
3. Vì sao records-lag-max có thể thấp trong khi CLI lag vẫn cao?
4. Vì sao offset distance không luôn bằng số record thực tế?
5. records-consumed-rate khác records-processed-rate ở điểm nào?
6. bytes-consumed-rate giúp phát hiện vấn đề gì?
7. fetch-latency và fetch-throttle-time phản ánh điều gì?
8. poll-idle-ratio-avg cao có luôn là lỗi không?
9. max.poll.interval.ms ảnh hưởng rebalance như thế nào?
10. commitSync và commitAsync khác nhau ở đâu?
11. Vì sao committed offset phải là offset kế tiếp sau record đã xử lý?
12. Những nguyên nhân nào khiến rebalance liên tục?
13. assigned-partitions bằng 0 có thể chỉ ra điều gì?
14. Client rebalance metrics và broker coordinator metrics bổ sung cho nhau thế nào?
15. Vì sao cần theo dõi cả offset lag và event age?
16. Khi nào tăng consumer count không giúp tăng throughput?
17. Vì sao JMX remote cần được bảo vệ?

## Tài liệu tham khảo

- [Apache Kafka 4.4 – Monitoring](https://kafka.apache.org/44/operations/monitoring/)
- [Apache Kafka 4.4 – Consumer and Share Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka 4.4 – Basic Kafka Operations](https://kafka.apache.org/44/operations/basic-kafka-operations/)
- [Apache Kafka 4.4 – Consumer Java API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)
- [Apache Kafka 4.4 – ConsumerRebalanceListener Java API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/ConsumerRebalanceListener.html)

Consumer metrics cần được đọc như một chuỗi: producer đưa dữ liệu vào, consumer fetch record, ứng dụng xử lý, rồi group commit offset. Lag cho biết khoảng cách offset; throughput cho biết tốc độ nhận; processing metrics cho biết tốc độ hoàn thành nghiệp vụ; commit và rebalance metrics cho biết group có duy trì tiến độ ổn định hay không.
