# Theo dõi request latency, error rate và throughput của broker

Một Kafka cluster có thể vẫn trả lời health check nhưng đang phục vụ request chậm, tăng lỗi hoặc không đạt throughput như kỳ vọng. Để nhận ra vấn đề trước khi producer timeout hay consumer lag tăng mạnh, cần quan sát ba nhóm tín hiệu chính: **request latency**, **error rate** và **throughput** của từng broker.

Ba nhóm này phải được đọc cùng nhau và theo từng loại request. Latency cao có thể do request queue bị nghẽn, xử lý local chậm, chờ replica hoặc network gửi response. Error rate cao có thể là lỗi xác thực, quota, leader change hoặc broker quá tải. Throughput thấp có thể do ít traffic, producer bị throttling, consumer không fetch hoặc một broker trở thành bottleneck. Một con số tổng hợp toàn cluster thường che khuất broker hoặc request type đang gặp vấn đề.

## 1. Phân biệt latency, error rate và throughput

| Chỉ số | Câu hỏi cần trả lời | Đơn vị thường dùng |
|---|---|---|
| Request latency | Broker mất bao lâu để xử lý một request? | ms hoặc seconds |
| Error rate | Bao nhiêu request thất bại trong một khoảng thời gian? | errors/s hoặc % |
| Throughput | Broker nhận/gửi bao nhiêu dữ liệu và phục vụ bao nhiêu request? | bytes/s, records/s, requests/s |

Không nên gộp các khái niệm sau:

- **Broker request latency** đo thời gian xử lý request trong broker, thường được phân tách theo API request type như Produce, FetchConsumer hoặc FetchFollower.
- **Client request latency** đo thời gian client chờ phản hồi từ broker, có thể bao gồm network round trip, retry và các lần chuyển broker.
- **End-to-end processing latency** đo thời gian từ lúc event được tạo đến khi consumer hoặc hệ thống đích xử lý xong.

Một broker có request latency thấp không đồng nghĩa ứng dụng có end-to-end latency thấp. Consumer có thể đang chờ xử lý backlog, producer có thể retry nhiều lần hoặc downstream database có thể chậm.

## 2. Theo dõi request latency theo từng request type

Kafka broker xuất các metric trong nhóm `kafka.network:type=RequestMetrics`. Các metric thường được gắn với request type, ví dụ `Produce`, `FetchConsumer`, `FetchFollower`, `Metadata` hoặc request API khác.

Các thành phần latency quan trọng:

| Metric | Ý nghĩa | Khi tăng cao nên kiểm tra |
|---|---|---|
| `RequestQueueTimeMs` | Thời gian request chờ trong queue trước khi được request handler xử lý | Request handler thiếu thread, CPU bận, burst traffic |
| `LocalTimeMs` | Thời gian broker xử lý phần công việc local của request | Disk I/O, page cache, CPU, partition leader và workload local |
| `RemoteTimeMs` | Thời gian request chờ công việc/response từ broker khác trong luồng xử lý có liên quan | Replication, follower chậm, network broker-to-broker |
| `ResponseQueueTimeMs` | Thời gian response chờ được network processor gửi đi | Network processor bận hoặc response queue tăng |
| `ResponseSendTimeMs` | Thời gian gửi response qua socket | Network congestion, client đọc chậm, socket buffer |
| `TotalTimeMs` | Tổng thời gian request ở phía broker theo các giai đoạn đo của Kafka | Dùng làm chỉ báo tổng thể rồi drill-down vào từng thành phần |

Tên metric và tập request type có thể thay đổi theo phiên bản Kafka. Khi triển khai dashboard, hãy kiểm tra MBean thực tế của phiên bản broker thay vì giả định mọi request type đều có đủ mọi metric.

### Mean không đủ để đánh giá latency

Mean latency có thể che giấu một nhóm request rất chậm. Ví dụ 99 request mất 5 ms và một request mất 2 giây thì trung bình vẫn có thể trông chấp nhận được, trong khi người dùng bị ảnh hưởng bởi tail latency.

Nên quan sát ít nhất:

- p50: latency của request ở giữa phân bố.
- p95: 95% request có latency bằng hoặc thấp hơn mức này.
- p99: tail latency ảnh hưởng đến các request chậm nhất.
- Max: hữu ích để phát hiện spike, nhưng nhạy với một mẫu đơn lẻ.

Đối chiếu p50/p95/p99 theo broker và request type. Nếu p99 của Produce tăng ở một broker trong khi các broker khác ổn định, hãy kiểm tra leader partition, disk và request queue trên broker đó.

## 3. Các JMX MBean cần thu thập

Kafka broker công bố metric qua JMX. Hai nhóm thường dùng nhất để theo dõi request và traffic là `RequestMetrics` và `BrokerTopicMetrics`.

### RequestMetrics

Một số MBean tiêu biểu:

```text
kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce
kafka.network:type=RequestMetrics,name=RequestQueueTimeMs,request=Produce
kafka.network:type=RequestMetrics,name=LocalTimeMs,request=Produce
kafka.network:type=RequestMetrics,name=RemoteTimeMs,request=Produce
kafka.network:type=RequestMetrics,name=ResponseQueueTimeMs,request=Produce
kafka.network:type=RequestMetrics,name=ResponseSendTimeMs,request=Produce
kafka.network:type=RequestMetrics,name=RequestsPerSec,request=Produce
kafka.network:type=RequestMetrics,name=ErrorsPerSec,request=Produce
```

Với metric thời gian, JMX thường cung cấp các thuộc tính thống kê như `Mean`, `Max`, `50thPercentile`, `95thPercentile` và `99thPercentile` tùy metric/version. Với meter rate, các thuộc tính có thể gồm `Count`, `MeanRate`, `OneMinuteRate`, `FiveMinuteRate` và `FifteenMinuteRate`.

### BrokerTopicMetrics

Nhóm `kafka.server:type=BrokerTopicMetrics` đo traffic của broker. Các metric phổ biến:

| Metric | Ý nghĩa |
|---|---|
| `BytesInPerSec` | Số byte broker nhận vào mỗi giây |
| `BytesOutPerSec` | Số byte broker gửi ra mỗi giây |
| `MessagesInPerSec` | Số message broker nhận vào mỗi giây |
| `ReplicationBytesInPerSec` | Byte nhận từ các follower/replication traffic |
| `ReplicationBytesOutPerSec` | Byte gửi cho follower/replication traffic |
| `TotalProduceRequestsPerSec` | Tốc độ request Produce |
| `TotalFetchRequestsPerSec` | Tốc độ request Fetch |
| `FailedProduceRequestsPerSec` | Tốc độ request Produce thất bại |
| `FailedFetchRequestsPerSec` | Tốc độ request Fetch thất bại |

Một số metric có thể được xuất cả ở mức broker và mức topic. Cần kiểm tra tag `topic`/MBean thực tế trước khi cộng tổng để tránh đếm trùng broker-level với topic-level.

### Tài nguyên xử lý request

Hai metric idle thường hữu ích khi latency tăng:

```text
kafka.server:type=KafkaRequestHandlerPool,name=RequestHandlerAvgIdlePercent
kafka.network:type=SocketServer,name=NetworkProcessorAvgIdlePercent
```

Giá trị idle giảm kéo dài cho thấy request handler hoặc network processor đang bận. Đây là tín hiệu bối cảnh, không phải kết luận duy nhất về bottleneck. Cần kết hợp queue time, CPU, network, disk và traffic để xác định nguyên nhân.

## 4. Error rate: đo tỷ lệ request thất bại

Error rate cần được tính trên cùng một phạm vi thời gian và cùng loại request:

\[
\text{Error Rate (\%)} =
\frac{\text{Failed Requests}}{\text{Total Requests}} \times 100
\]

Ví dụ trong 5 phút:

- Broker xử lý 120.000 request Produce.
- Có 240 request Produce thất bại.
- Error rate là `240 / 120000 × 100 = 0,2%`.

Nên theo dõi cả số lỗi tuyệt đối và tỷ lệ lỗi. Khi traffic gần bằng 0, một vài lỗi có thể làm tỷ lệ phần trăm tăng rất cao; ngược lại, ở traffic lớn, tỷ lệ nhỏ vẫn có thể tương ứng hàng nghìn request lỗi.

### Phân biệt lỗi theo request và nguyên nhân

Metric `ErrorsPerSec` theo request type cho biết request có lỗi, nhưng chưa chắc giải thích đầy đủ nguyên nhân. Cần kết hợp broker log, client error, error code và các metric liên quan để phân loại:

- `NOT_LEADER_OR_FOLLOWER`, `NOT_LEADER` hoặc lỗi leader epoch: metadata cũ, leader election hoặc partition chuyển leader.
- `REQUEST_TIMED_OUT`: broker xử lý quá thời hạn hoặc client không nhận phản hồi kịp.
- `NOT_ENOUGH_REPLICAS` và `NOT_ENOUGH_REPLICAS_AFTER_APPEND`: ISR không đáp ứng yêu cầu replication/acks.
- `THROTTLING_QUOTA_EXCEEDED`: client bị quota throttle.
- `SASL_AUTHENTICATION_FAILED` hoặc authorization failure: credential, mechanism hoặc ACL sai.
- Network timeout/disconnect: route, firewall, TLS, broker quá tải hoặc client không đọc response kịp.

Không phải mọi lỗi trả về cho client đều là lỗi broker. Ví dụ lỗi authorization có thể phản ánh cấu hình quyền; lỗi invalid request có thể do client gửi request không hợp lệ. Dashboard nên phân biệt broker-side failure, client-side failure, throttling và lỗi do cấu hình.

## 5. Throughput: đo cả byte, message và request

Throughput có nhiều góc nhìn:

- **Bytes in/out per second:** dung lượng dữ liệu broker nhận và gửi.
- **Messages in per second:** số record broker nhận.
- **Produce/Fetch requests per second:** số request API được phục vụ.
- **Replication bytes per second:** traffic sao chép giữa leader và follower.

Các chỉ số này không thể thay thế cho nhau. Một producer gửi batch lớn có thể tạo ít request nhưng nhiều message và byte. Một consumer fetch rỗng thường xuyên có thể tạo request rate cao trong khi bytes out thấp.

Ví dụ:

| Tình huống | Bytes/s | Messages/s | Requests/s | Diễn giải |
|---|---:|---:|---:|---|
| Batch lớn | Cao | Cao | Trung bình | Batching giảm số request trên mỗi message |
| Record nhỏ, gửi lẻ | Thấp | Trung bình | Cao | Overhead request có thể đáng kể |
| Consumer fetch rỗng | Thấp | Thấp | Cao | Có thể do poll/fetch cadence hoặc không có dữ liệu |
| Replication backlog | Replication bytes tăng/dao động | Không nhất thiết tăng | Không nhất thiết tăng | Cần kiểm tra follower và ISR |

Nên hiển thị throughput theo broker, topic và hướng traffic. Tổng toàn cluster giúp nhìn quy mô, còn per-broker view giúp phát hiện một broker nhận nhiều leader partition hoặc traffic mất cân bằng.

## 6. Thu thập metric bằng JMX Exporter và Prometheus

Kafka broker xuất JMX metric trong JVM. Một cách triển khai phổ biến là gắn Prometheus JMX Exporter Java agent vào từng broker, sau đó để Prometheus scrape endpoint HTTP của exporter.

Ví dụ khởi chạy broker với agent:

```bash
KAFKA_OPTS="-javaagent:/opt/jmx/jmx_prometheus_javaagent.jar=9404:/etc/kafka/jmx-exporter.yml"
```

Ví dụ cấu hình scrape Prometheus:

```yaml
scrape_configs:
  - job_name: kafka-brokers
    static_configs:
      - targets:
          - broker-1.internal:9404
          - broker-2.internal:9404
          - broker-3.internal:9404
```

Tên metric Prometheus được tạo ra phụ thuộc rule của JMX Exporter và phiên bản exporter. Không giả định tên metric sau export luôn giống tên MBean. Nên chuẩn hóa naming, labels `cluster`, `broker`, `request` và `topic` trong exporter config; tránh đưa label có cardinality quá cao như client ID hoặc exception message vào mọi metric.

JMX Exporter có thể xuất các percentile JMX dưới dạng gauge riêng. Nếu chỉ có `95thPercentile` gauge, không dùng `histogram_quantile()` trực tiếp như thể đó là histogram. Muốn dùng `histogram_quantile()`, cần metric histogram có `_bucket`, `_sum`, `_count` được instrument/export đúng cách.

Nếu cluster đã có nền tảng metrics hoặc Kafka operator, có thể dùng cơ chế scrape tích hợp của nền tảng đó. Điều quan trọng là mỗi broker có identity ổn định và dashboard giữ được chiều phân tích theo broker/request type.

## 7. Ví dụ PromQL để tính rate và error percentage

Các tên metric dưới đây là tên chuẩn hóa giả định trong JMX Exporter rules của hệ thống, không phải tên bắt buộc mà mọi exporter tự sinh. Ví dụ quy ước:

- `kafka_request_total{request="Produce"}` là counter tổng request theo loại.
- `kafka_request_errors_total{request="Produce"}` là counter request lỗi.
- `kafka_broker_bytes_in_total` và `kafka_broker_bytes_out_total` là counter byte.
- `kafka_broker_messages_in_total` là counter message.

Request rate theo broker và request type:

```promql
sum by (cluster, broker, request) (
  rate(kafka_request_total[5m])
)
```

Error percentage theo request type:

```promql
100 *
sum by (cluster, broker, request) (rate(kafka_request_errors_total[5m]))
/
clamp_min(
  sum by (cluster, broker, request) (rate(kafka_request_total[5m])),
  1e-9
)
```

Broker ingress/egress:

```promql
sum by (cluster, broker) (rate(kafka_broker_bytes_in_total[5m]))
```

```promql
sum by (cluster, broker) (rate(kafka_broker_bytes_out_total[5m]))
```

Message throughput:

```promql
sum by (cluster, broker) (rate(kafka_broker_messages_in_total[5m]))
```

Nếu exporter xuất `ErrorsPerSec` dưới dạng meter rate thay vì counter, dùng trực tiếp rate được exporter cung cấp và không áp dụng `rate()` lần nữa. Cần hiểu loại metric (counter, gauge hay meter) trước khi viết query để tránh tính sai.

## 8. Theo dõi latency phía client

Broker metrics không thể cho biết đầy đủ thời gian client thực sự chờ. Producer và consumer cũng có các metric riêng.

Producer client thường cung cấp các metric như:

- `request-latency-avg` và `request-latency-max`: thời gian request phía producer.
- `request-rate`: tốc độ gửi request.
- `record-send-rate`: tốc độ gửi record.
- `record-error-rate`: tốc độ record gửi lỗi.
- `record-retry-rate`: tốc độ retry record.

Consumer client thường có:

- `fetch-latency-avg` và `fetch-rate`.
- `records-consumed-rate`.
- `records-lag-max` và các metric lag theo partition khi client cung cấp.
- `commit-latency-avg` và `commit-rate`.

Kết hợp client và broker metrics giúp khoanh vùng:

- Broker `TotalTimeMs` tăng và producer `request-latency-avg` tăng: broker hoặc đường mạng có thể là nguyên nhân.
- Producer request latency cao nhưng broker request latency thấp: kiểm tra network RTT, retry, metadata refresh, DNS và TLS.
- Broker Fetch latency thấp nhưng consumer processing lag cao: kiểm tra logic xử lý, thread pool và downstream thay vì chỉ tăng broker capacity.
- Record retry/error tăng nhưng broker error thấp: kiểm tra timeout/exception ở client, serialization hoặc logic gửi.

## 9. Xây dựng dashboard theo broker và request type

Một dashboard vận hành nên có các hàng panel:

| Hàng dashboard | Panel nên có | Mục tiêu |
|---|---|---|
| Request latency | p50/p95/p99 `TotalTimeMs` theo Produce/Fetch/Metadata và từng broker | Phát hiện tail latency và broker lệch |
| Latency breakdown | RequestQueue, Local, Remote, ResponseQueue, ResponseSend | Xác định giai đoạn gây chậm |
| Error | Request rate, ErrorsPerSec, error percentage theo request type | Phát hiện lỗi tăng và loại request bị ảnh hưởng |
| Throughput | BytesIn/Out, MessagesIn, Produce/Fetch requests, replication bytes | Theo dõi traffic và mức sử dụng broker |
| Saturation | RequestHandlerAvgIdlePercent, NetworkProcessorAvgIdlePercent, CPU, disk, network | Xác định broker gần giới hạn tài nguyên |
| Replication | ISR, under-replicated partitions, replication bytes, follower lag | Phát hiện ảnh hưởng đến acks và độ bền |
| Client view | Producer latency/retry/error, consumer fetch/lag | Nối metric broker với trải nghiệm ứng dụng |

Mỗi panel nên cho phép lọc theo cluster, broker, request type và topic khi metric hỗ trợ. Dùng cùng time range để đối chiếu latency, error, throughput và saturation.

## 10. Cảnh báo theo SLO và baseline

Không có một ngưỡng latency hoặc throughput phù hợp với mọi Kafka cluster. Ngưỡng cần dựa trên SLO, tải bình thường, loại storage, số partition, replication factor và workload.

Một số điều kiện cảnh báo có giá trị:

- p99 Produce hoặc Fetch latency vượt SLO trong nhiều cửa sổ liên tiếp.
- Error percentage tăng đồng thời với request rate đáng kể.
- `RequestQueueTimeMs` tăng và `RequestHandlerAvgIdlePercent` giảm kéo dài.
- `NetworkProcessorAvgIdlePercent` giảm cùng response send time tăng.
- BytesIn/BytesOut hoặc MessagesIn giảm đột ngột so với baseline trong khi ứng dụng vẫn dự kiến có traffic.
- Một broker có throughput hoặc latency lệch rõ rệt so với các broker còn lại.
- Replication throughput bất thường đi kèm ISR shrink hoặc under-replicated partitions.

Nên dùng alert có thời gian duy trì (for duration) và kết hợp điều kiện traffic tối thiểu. Ví dụ error percentage 100% khi request rate gần 0 không nên tự động tạo cùng mức độ ưu tiên như 100% lỗi ở hàng nghìn request/giây.

## 11. Điều tra theo triệu chứng

| Triệu chứng | Metric đầu tiên cần xem | Hướng điều tra tiếp |
|---|---|---|
| Produce latency tăng | Produce `TotalTimeMs`, `RequestQueueTimeMs`, `LocalTimeMs` | Disk, leader distribution, acks, ISR, replication và request handler idle |
| Fetch latency tăng | FetchConsumer `TotalTimeMs`, `RemoteTimeMs`, `ResponseSendTimeMs` | Follower/leader, network, disk read, consumer fetch pattern |
| Queue time tăng | `RequestQueueTimeMs`, request handler idle | CPU, handler thread pool, traffic burst và request size |
| Remote time tăng | `RemoteTimeMs`, replication bytes, ISR | Broker-to-broker network, follower lag, replication fetcher |
| Response send time tăng | `ResponseSendTimeMs`, network processor idle | Network egress, socket buffer và client đọc chậm |
| Error rate tăng | ErrorsPerSec theo request, broker/client logs | Error code, quota, auth/ACL, leader election và timeout |
| Throughput giảm trên một broker | BytesIn/Out, MessagesIn, request rate per broker | Partition leader imbalance, broker offline, client routing |
| Throughput toàn cluster giảm | BytesIn/Out và client send/fetch rates | Producer traffic, consumer demand, upstream/downstream và quota |

Không tăng thread hoặc quota ngay khi thấy latency cao. Trước tiên xác định latency nằm ở queue, local processing, remote wait hay response send. Tăng thread khi bottleneck là disk hoặc network có thể làm contention nặng hơn.

## 12. Một quy trình kiểm tra thực tế

Khi nhận cảnh báo p99 Produce latency tăng:

1. Chọn broker và request type cụ thể; xác nhận cảnh báo có đủ request volume.
2. So sánh p50/p95/p99 `TotalTimeMs` của Produce giữa các broker.
3. Xem breakdown: queue time, local time, remote time, response queue và send time.
4. Đối chiếu `RequestHandlerAvgIdlePercent`, `NetworkProcessorAvgIdlePercent`, CPU, disk latency và network.
5. Kiểm tra `BytesInPerSec`, `MessagesInPerSec`, replication bytes, ISR và partition leader distribution.
6. So sánh producer `request-latency-avg`, retry rate và record error rate để xác định vấn đề phía client hay broker.
7. Xem broker log theo thời điểm xảy ra spike và tìm error code/leader change/quota event.
8. Sau khi thay đổi, xác nhận p99, error rate và throughput trở lại baseline; tránh chỉ dựa vào việc alert tự hết.

## 13. Các lỗi khi đọc metric

- **Chỉ xem cluster average:** có thể che giấu một broker nóng hoặc một request type chậm.
- **Chỉ xem mean latency:** tail latency có thể gây timeout dù mean thấp.
- **Nhầm throughput byte với message:** kích thước record và batch thay đổi làm hai metric lệch nhau.
- **Nhầm request rate với record rate:** một request có thể mang nhiều record hoặc không có record.
- **Cộng broker-level và topic-level metric:** có thể đếm cùng traffic hai lần.
- **Dùng `rate()` trên gauge hoặc meter rate:** tạo kết quả sai vì không đúng loại metric.
- **Dùng histogram query trên percentile gauge:** `histogram_quantile()` chỉ phù hợp với histogram bucket.
- **Bỏ qua client metrics:** broker request latency không đại diện toàn bộ network/retry/end-to-end latency.
- **Alert theo phần trăm mà không xét volume:** tạo cảnh báo nhiễu khi traffic thấp.

## 14. Checklist observability cho Kafka broker

- Thu thập `RequestMetrics` theo broker và request type.
- Theo dõi p50/p95/p99 `TotalTimeMs` và breakdown từng giai đoạn.
- Thu thập `RequestsPerSec`, `ErrorsPerSec` và tính error percentage đúng loại metric.
- Theo dõi `BytesInPerSec`, `BytesOutPerSec`, `MessagesInPerSec` và replication throughput.
- Theo dõi request handler idle và network processor idle.
- Thu thập producer/consumer client metrics để đo trải nghiệm ứng dụng.
- Giữ labels cluster, broker, request type và topic ở mức cardinality kiểm soát được.
- Phân biệt counter, gauge, meter và histogram trước khi viết PromQL.
- Thiết kế dashboard per-broker, per-request và so sánh giữa broker.
- Đặt alert dựa trên SLO/baseline, request volume và thời gian duy trì.
- Khi điều tra, kiểm tra latency breakdown trước khi tăng tài nguyên hoặc thay đổi cấu hình.

Theo dõi request latency, error rate và throughput hiệu quả đòi hỏi nhìn đồng thời broker, request type và client. `RequestMetrics` giúp phân rã thời gian xử lý; `BrokerTopicMetrics` cho biết traffic byte/message/request; client metrics cho biết thời gian ứng dụng thực sự chờ. Khi kết hợp các tín hiệu này với tài nguyên và replication, đội vận hành có thể phát hiện broker lệch tải, định vị bottleneck và xử lý sự cố dựa trên bằng chứng thay vì chỉ nhìn một con số trung bình.
