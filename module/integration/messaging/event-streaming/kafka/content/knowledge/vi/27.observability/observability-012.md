# Cảnh báo theo triệu chứng, nguyên nhân và mức độ ảnh hưởng

## Mục tiêu bài học

Một hệ thống Kafka có thể phát ra hàng nghìn metric, nhưng đội vận hành chỉ cần nhận cảnh báo khi có dấu hiệu đáng tin cậy cho thấy dịch vụ hoặc dữ liệu đang bị ảnh hưởng, hay sắp vượt ngưỡng an toàn cần can thiệp. Cảnh báo tốt bắt đầu từ triệu chứng mà người dùng hoặc pipeline cảm nhận được, xác định phạm vi và mức độ ảnh hưởng, sau đó cung cấp tín hiệu để tìm nguyên nhân và một hành động tiếp theo rõ ràng.

Sau bài học, bạn có thể:

- Phân biệt triệu chứng, nguyên nhân, tín hiệu cảnh báo sớm và sự cố thực tế.
- Thiết kế alert dựa trên SLI/SLO, error budget và mức độ ảnh hưởng.
- Chọn ngưỡng cảnh báo theo baseline, thời gian kéo dài và tốc độ suy giảm.
- Xây dựng bộ alert cho Kafka broker, replication, producer, consumer, Connect và Streams.
- Viết Prometheus alert rules có nhãn, mô tả, runbook và `for` phù hợp.
- Dùng Alertmanager để group, route, silence và inhibit cảnh báo.
- Phân biệt cảnh báo cần paging ngay với cảnh báo cần ticket hoặc theo dõi.
- Viết runbook để người trực xác định tác động, kiểm tra nguyên nhân và khôi phục dịch vụ.
- Kiểm thử alert, giảm false positive, đo chất lượng cảnh báo và cải tiến sau incident.

## 1. Vì sao cần cảnh báo theo triệu chứng?

Kafka có nhiều thành phần liên quan: producer gửi record, broker lưu log và replicate, consumer đọc record, consumer group phân phối partition, Kafka Connect tích hợp hệ thống ngoài và Kafka Streams xử lý dữ liệu. Một lỗi ở một thành phần có thể tạo ra nhiều metric bất thường ở các thành phần khác.

Ví dụ, consumer xử lý chậm có thể làm lag tăng, request fetch giảm, số record in-flight tăng, heap của consumer tăng và downstream database bị quá tải. Nếu tạo một page cho từng metric, người trực nhận hàng chục cảnh báo cho cùng một sự cố. Nếu chỉ nhìn metric nguyên nhân giả định, có thể bỏ lỡ triệu chứng thật: đơn hàng chưa được xử lý đúng hạn.

Thiết kế alert theo triệu chứng giúp trả lời trước ba câu hỏi:

1. Dịch vụ hoặc dữ liệu nào đang bị ảnh hưởng?
2. Ảnh hưởng nghiêm trọng đến mức nào và có cần can thiệp ngay không?
3. Người trực cần kiểm tra tín hiệu nào để xác định nguyên nhân và hành động?

### 1.1. Triệu chứng, nguyên nhân và tín hiệu cảnh báo sớm

| Loại tín hiệu | Câu hỏi | Ví dụ Kafka | Cách sử dụng |
|---|---|---|---|
| Triệu chứng (symptom) | Điều gì đang hỏng với dịch vụ? | Event quan trọng chưa được xử lý trong SLA; publish thất bại; consumer lag tăng đến mức dữ liệu trễ | Ưu tiên làm alert chính và paging theo impact |
| Nguyên nhân (cause) | Điều gì có thể gây ra triệu chứng? | Broker disk gần đầy, replica fetch chậm, consumer handler lỗi, GC pause dài | Bổ sung context và alert chẩn đoán; page khi có hành động khẩn cấp rõ ràng |
| Tín hiệu cảnh báo sớm (leading indicator) | Điều gì cho thấy rủi ro sẽ xảy ra? | Disk tăng nhanh, request handler idle giảm, ISR shrink liên tục, producer buffer wait tăng | Cảnh báo sớm cho đội sở hữu khi có thời gian xử lý trước impact |
| Bằng chứng sau sự cố | Điều gì xác nhận sự cố đã xảy ra? | Task FAILED, broker target DOWN, record age vượt SLA, offline replica | Dùng để xác nhận, định phạm vi và điều tra |

Một metric có thể là triệu chứng trong hệ thống này nhưng chỉ là nguyên nhân trong hệ thống khác. Ví dụ consumer lag là triệu chứng với dịch vụ cần xử lý event trong 30 giây, nhưng có thể là tín hiệu chẩn đoán khi đánh giá sức khỏe broker.

### 1.2. Alert không phải là dashboard

Dashboard phục vụ khám phá và theo dõi xu hướng. Alert phải chỉ ra điều kiện cần hành động. Một panel hiển thị CPU 70% không nhất thiết cần page; một alert CPU chỉ có ý nghĩa khi CPU bão hòa kéo dài và có request latency hoặc throughput bị ảnh hưởng, hoặc khi còn rất ít headroom trước một workload đã biết.

Một alert tốt có:

- Điều kiện có thể kiểm tra bằng dữ liệu.
- Đối tượng và phạm vi rõ ràng: cluster, broker, topic, consumer group hoặc connector.
- Mức độ nghiêm trọng dựa trên impact.
- Thời gian xác nhận phù hợp để tránh spike ngắn.
- Mô tả cho biết điều gì đang xảy ra, từ khi nào và ở đâu.
- Link dashboard và runbook có bước kiểm tra/hành động cụ thể.
- Owner hoặc route nhận cảnh báo.

Nếu người nhận không biết phải làm gì sau khi đọc alert, alert đó chưa hoàn chỉnh.

## 2. Mô hình thiết kế: SLI, SLO và error budget

SLI (Service Level Indicator) là phép đo chất lượng dịch vụ mà người dùng quan tâm. SLO (Service Level Objective) là mục tiêu cho SLI trong một cửa sổ thời gian. Error budget là phần sai lệch được phép trước khi dịch vụ vi phạm SLO.

Đối với event streaming, không nên chỉ đo broker có sống hay không. Một cluster có thể trả lời TCP bình thường nhưng pipeline vẫn không đáp ứng SLA do consumer xử lý trễ hoặc event bị lỗi nghiệp vụ.

### 2.1. Các SLI thường dùng cho Kafka pipeline

| SLI | Cách đo gợi ý | Điều người dùng cảm nhận |
|---|---|---|
| Publish success ratio | Số record publish thành công / tổng số record publish được yêu cầu | Producer có gửi event thành công không? |
| Publish latency | p95/p99 thời gian từ lúc ứng dụng gửi đến lúc broker xác nhận | Event có được nhận kịp thời không? |
| Processing freshness | Tuổi event tại thời điểm xử lý hoặc thời gian từ publish đến xử lý | Dữ liệu có mới đủ để dùng không? |
| Processing success ratio | Số event xử lý thành công / tổng event đủ điều kiện xử lý | Pipeline có hoàn thành công việc không? |
| Consumer backlog | Số record chưa xử lý và/hoặc tuổi record cũ nhất | Có backlog và backlog có ảnh hưởng SLA không? |
| Data correctness | Tỷ lệ event hợp lệ, không mất, không nhân đôi ngoài semantics cho phép | Kết quả nghiệp vụ có đúng không? |
| Connector delivery | Tỷ lệ record source/sink được chuyển thành công | Dữ liệu có đến hệ thống ngoài không? |

Không phải mọi SLI đều lấy được từ broker JMX. Publish success và processing success thường cần metric từ ứng dụng; processing freshness cần event timestamp hoặc timestamp khi xử lý; data correctness có thể cần reconciliation hoặc business metric.

### 2.2. Chọn SLO có thể kiểm chứng

Ví dụ minh họa cho một pipeline đơn hàng:

- 99,9% event `OrderCreated` được publish thành công trong mỗi cửa sổ 30 ngày.
- 99% event được consumer xử lý trong vòng 60 giây kể từ thời điểm publish.
- Tỷ lệ lỗi xử lý vĩnh viễn nhỏ hơn 0,1% trên số event đủ điều kiện.
- Không có event bị mất trong luồng dữ liệu quan trọng; đối soát theo business ID.

Các con số phải xuất phát từ hợp đồng với consumer/downstream và năng lực hệ thống. Không sao chép các giá trị ví dụ thành SLA chung cho mọi topic.

### 2.3. Error budget và burn rate

Với SLO availability 99,9%, error budget ratio là 0,1% (0,001). Nếu trong một cửa sổ đo, tỷ lệ lỗi là 0,0144 (1,44%), burn rate bằng:

\[
\text{burn rate}=\frac{\text{observed error ratio}}{\text{allowed error ratio}}
\]

Ví dụ burn rate 14,4 nghĩa là dịch vụ đang tiêu thụ error budget nhanh gấp 14,4 lần tốc độ cho phép. Nếu duy trì tốc độ đó, ngân sách lỗi sẽ cạn rất nhanh.

Multi-window alert kết hợp cửa sổ ngắn và dài để phát hiện cả spike ảnh hưởng mạnh lẫn suy giảm kéo dài. Ví dụ một policy có thể dùng:

| Mức | Cửa sổ dài | Cửa sổ ngắn | Burn rate ví dụ | Mục đích |
|---|---|---|---:|---|
| Page nhanh | 1 giờ | 5 phút | 14,4 | Phát hiện lỗi nghiêm trọng đang xảy ra |
| Page kéo dài | 6 giờ | 30 phút | 6 | Phát hiện suy giảm liên tục nhưng ít đột biến |
| Ticket/điều tra | 3 ngày | 6 giờ | 1 | Theo dõi tiêu thụ budget dài hạn |

Chỉ page khi điều kiện multi-window phù hợp cùng thỏa mãn, để tránh báo động do một cửa sổ ngắn nhiễu. Chọn cửa sổ theo SLO period, tần suất event và thời gian phản ứng của đội vận hành.

### 2.4. Đo freshness tốt hơn chỉ nhìn offset lag

Offset lag là chênh lệch giữa vị trí log và vị trí consumer đã xử lý/commit theo cách exporter định nghĩa. Nó không trực tiếp cho biết event đã chờ bao nhiêu giây.

Ví dụ:

- Topic A nhận 100.000 record/giây; lag 10.000 record có thể chỉ tương đương 100 ms.
- Topic B nhận 1 record/phút; lag 10 record có thể tương đương 10 phút.

Với pipeline có SLA theo thời gian, hãy đo tuổi của record cũ nhất hoặc thời gian publish-to-process. Kết hợp lag, input rate, processing rate và event age để đánh giá backlog.

## 3. Phân loại impact và severity

Severity phản ánh mức độ ảnh hưởng và thời gian cần phản ứng, không chỉ phản ánh metric lớn hay nhỏ. Một broker có CPU cao chưa chắc nghiêm trọng nếu không có tác động; một topic quan trọng bị chậm 2 phút có thể là critical dù broker vẫn khỏe.

### 3.1. Mức độ cảnh báo mẫu

| Mức | Ý nghĩa | Kênh xử lý | Ví dụ |
|---|---|---|---|
| SEV1 / Critical | Dịch vụ trọng yếu ngừng hoặc dữ liệu quan trọng mất/trễ nghiêm trọng; cần phản ứng ngay | Page on-call, incident channel, incident commander | Mất quorum KRaft, nhiều broker không sẵn sàng, publish/consume critical path thất bại trên diện rộng |
| SEV2 / High | Một phần chức năng hoặc nhóm khách hàng bị ảnh hưởng rõ; cần xử lý khẩn trong ca trực | Page owner/on-call, theo dõi liên tục | Under-min-ISR kéo dài ở topic trọng yếu, consumer freshness vượt SLA, sink connector quan trọng FAILED |
| SEV3 / Warning | Rủi ro hoặc suy giảm có phạm vi hạn chế; có thể xử lý trong giờ làm việc | Ticket/chat cảnh báo có owner | ISR shrink tăng ngắn hạn, một task retry nhiều nhưng backlog vẫn ổn định |
| SEV4 / Info | Thông tin vận hành hoặc xu hướng cần theo dõi | Dashboard/log, ticket định kỳ nếu cần | Broker restart theo lịch, rebalance trong maintenance, thay đổi baseline |

Tên severity có thể là `critical`, `warning`, `info` trong Prometheus. Ánh xạ sang quy trình SEV1-SEV4 của tổ chức; không để hai hệ thống dùng cùng một từ nhưng khác nghĩa.

### 3.2. Bốn yếu tố xác định severity

1. **Scope:** một partition, một topic, một consumer group, một broker hay toàn cluster?
2. **Criticality:** workload có phải luồng thanh toán, đơn hàng, kiểm soát rủi ro hay chỉ telemetry phụ?
3. **Duration/trend:** ảnh hưởng đã kéo dài bao lâu, có tăng nhanh không?
4. **Recoverability:** có failover, retry, replay hoặc xử lý thủ công an toàn không?

Ví dụ, một replica offline trong topic có RF=3 có thể là warning nếu leader và min ISR vẫn khỏe. Nếu topic có RF=1 hoặc replica offline làm mất khả năng đọc/ghi, mức độ ảnh hưởng khác hẳn.

### 3.3. Page, ticket hay dashboard?

| Loại thông báo | Khi nào dùng | Yêu cầu |
|---|---|---|
| Page | Impact đang xảy ra hoặc sắp xảy ra trong thời gian ngắn; cần người phản ứng ngay | Owner trực, runbook, severity, deduplication |
| Ticket | Cần xử lý nhưng không yêu cầu đánh thức on-call | Owner, deadline, context và điều kiện đóng |
| Chat notification | Cập nhật hoặc cảnh báo có thể chờ; không thay thế paging cho SEV cao | Kênh đúng team, không spam |
| Dashboard only | Metric để quan sát xu hướng, chưa có hành động ngay | Panel và baseline rõ ràng |

Không page chỉ vì một ngưỡng CPU, heap hoặc lag bị vượt nếu không có impact hoặc một rủi ro sắp xảy ra đã được chứng minh và có hành động rõ ràng.

## 4. Nguyên tắc viết alert rule

### 4.1. Alert phải mô tả điều kiện có thể hành động

Tên alert nên nêu symptom và đối tượng, ví dụ:

- `KafkaCriticalTopicFreshnessSLOViolation`
- `KafkaUnderMinIsrPartitions`
- `KafkaBrokerExporterUnavailable`
- `KafkaConnectCriticalSinkTaskFailed`
- `KafkaStreamsProcessingLatencyHigh`

Tránh tên mơ hồ như `KafkaBad`, `HighMetric` hoặc `SomethingWrong`.

### 4.2. Chọn ngưỡng theo baseline và SLA

Không có một ngưỡng đúng cho mọi cluster. Trước khi đặt threshold:

1. Thu thập baseline trong giờ cao điểm và thấp điểm.
2. Xác định ngưỡng mà tại đó SLI bắt đầu xấu đi.
3. Xem độ biến động bình thường và lịch bảo trì.
4. Chọn thời gian `for` tương ứng với thời gian phục hồi tự nhiên.
5. Kiểm tra threshold với dữ liệu lịch sử hoặc staging.
6. Ghi lại lý do chọn ngưỡng và người sở hữu.

Ví dụ `UnderReplicatedPartitions > 0 for 5m` là ngưỡng khởi đầu thường dùng, nhưng cluster có nhiều partition và thường xuyên rolling maintenance có thể cần policy khác. Với critical topic, có thể cảnh báo sớm hơn khi ISR xuống dưới min ISR.

### 4.3. Dùng `for` để loại spike ngắn

`for` yêu cầu expression duy trì true trong một khoảng thời gian trước khi alert chuyển sang firing. Nó giúp tránh page do spike vài giây hoặc một lần scrape bất thường.

Không đặt `for` quá dài nếu sự cố cần phản ứng ngay. Ví dụ broker target down có thể cần 1-2 phút xác nhận; event freshness đã vượt SLA 10 phút có thể cần cảnh báo ngay khi điều kiện được xác nhận.

### 4.4. Hysteresis và recovery

Một metric dao động quanh threshold có thể khiến alert liên tục firing/resolved. Có thể:

- Dùng threshold khác nhau cho cảnh báo và recovery ở hệ thống hỗ trợ hysteresis.
- Dùng `for` và cửa sổ trung bình phù hợp.
- Dùng `keep_firing_for` nếu Prometheus version hỗ trợ và semantics phù hợp.
- Tránh biểu thức quá nhạy với một sample.

Không làm chậm cảnh báo critical chỉ để giảm noise. Hãy xử lý nguyên nhân dao động hoặc chọn tín hiệu ổn định hơn.

### 4.5. Label ổn định, annotation hữu ích

Labels dùng để định danh alert và route. Nên có `service`, `cluster`, `severity`, `team`, `alertname` và `instance`/`broker_id` khi phù hợp. Không đưa giá trị biến động cao như exception message, record key, user ID hoặc request ID vào label.

Annotations nên có:

- `summary`: một câu mô tả symptom.
- `description`: metric hiện tại, threshold, scope và thời gian.
- `runbook_url`: đường dẫn hướng dẫn xử lý.
- `dashboard_url`: dashboard liên quan.
- `impact`: tác động dự kiến hoặc SLO bị đe dọa.

Không nhúng toàn bộ log hoặc stack trace vào annotation. Link đến nguồn dữ liệu gốc để tránh payload cảnh báo quá lớn.

## 5. Alert cho Kafka broker và cluster

Broker alert nên phản ánh availability, khả năng nhận/gửi request, tài nguyên và sức khỏe replication. Một broker mất metrics endpoint không nhất thiết đồng nghĩa broker đã down; cần đối chiếu Kafka protocol health, process health và exporter health.

### 5.1. Broker không scrape được metrics

Triệu chứng: Prometheus không scrape được JMX Exporter endpoint. Nguyên nhân có thể là broker dừng, exporter không khởi động, network/firewall hoặc sai service discovery.

```yaml
groups:
  - name: kafka-exporter-health
    rules:
      - alert: KafkaBrokerMetricsEndpointDown
        expr: up{job="kafka-brokers"} == 0
        for: 2m
        labels:
          severity: warning
          service: kafka
          team: platform
        annotations:
          summary: "Không scrape được metrics endpoint của Kafka broker"
          description: "Prometheus không scrape được {{ $labels.instance }} trong ít nhất 2 phút. Xác minh process, exporter, port và network."
          runbook_url: "https://runbooks.example.invalid/kafka/exporter-down"
```

Đây là alert về telemetry path. Nếu scrape thất bại, metric JMX khác cũng có thể biến mất; không tự kết luận broker đã ngừng phục vụ. Kết hợp synthetic Kafka client hoặc broker health probe để xác nhận availability.

`up == 0` chỉ phát hiện target đã được Prometheus discovery nhưng scrape thất bại. Nếu broker biến mất hoàn toàn khỏi service discovery, series `up` có thể biến mất thay vì có giá trị 0. Muốn phát hiện trường hợp đó, so sánh target hiện có với inventory mong đợi hoặc dùng metric expected broker count/cluster membership.

### 5.2. Under-replicated partition

Triệu chứng: một số partition chưa có đủ replica đồng bộ. Điều này làm giảm redundancy và có thể báo trước nguy cơ mất availability nếu thêm replica/broker lỗi.

```yaml
      - alert: KafkaUnderReplicatedPartitions
        expr: kafka_server_replica_manager_underreplicatedpartitions > 0
        for: 5m
        labels:
          severity: warning
          service: kafka
          team: platform
        annotations:
          summary: "Kafka có partition chưa đủ replica đồng bộ"
          description: "Broker {{ $labels.instance }} báo {{ $value }} under-replicated partition. Kiểm tra ISR, replica fetcher, disk và network."
          runbook_url: "https://runbooks.example.invalid/kafka/under-replicated"
```

Metric custom phải khớp JMX Exporter rules. Nếu metric được xuất ở mọi broker và phản ánh partition count local, tránh `sum` có thể đếm trùng; dùng `max` hoặc query theo broker/cluster đúng semantics.

### 5.3. Partition dưới min ISR

Triệu chứng: số replica trong ISR thấp hơn `min.insync.replicas`. Producer dùng `acks=all` có thể không ghi được record khi ISR không đáp ứng điều kiện.

```yaml
      - alert: KafkaUnderMinIsrPartitions
        expr: kafka_server_replica_manager_underminisrpartitioncount > 0
        for: 1m
        labels:
          severity: critical
          service: kafka
          team: platform
        annotations:
          summary: "Partition Kafka đã xuống dưới min ISR"
          description: "Broker {{ $labels.instance }} báo {{ $value }} partition dưới min ISR. Kiểm tra write availability và replica health."
          runbook_url: "https://runbooks.example.invalid/kafka/under-min-isr"
```

Tên `kafka_server_replica_manager_underminisrpartitioncount` là ví dụ dựa trên custom JMX Exporter rule. Xác nhận tên thực tế trong `/metrics` trước khi đưa vào production. Đây là điều kiện thường nghiêm trọng hơn under-replicated thông thường.

### 5.4. Broker request latency tăng

Triệu chứng: Produce/Fetch request latency tăng, làm producer send latency và consumer fetch latency tăng theo. Nguyên nhân có thể là disk I/O, network, request queue, GC hoặc broker saturation.

```yaml
      - alert: KafkaProduceRequestP99High
        expr: kafka_network_request_total_time_ms_p99{request="Produce"} > 500
        for: 5m
        labels:
          severity: warning
          service: kafka
          team: platform
        annotations:
          summary: "Produce request p99 latency tăng cao"
          description: "P99 Produce trên {{ $labels.instance }} đang là {{ $value }} ms. Đối chiếu request queue, disk, network và GC."
          runbook_url: "https://runbooks.example.invalid/kafka/request-latency"
```

Ngưỡng 500 ms chỉ là ví dụ. Nếu metric p99 là percentile được tính riêng trên từng broker, không gộp bằng average để suy ra percentile toàn cluster.

### 5.5. Request handler hoặc network processor gần bão hòa

Idle ratio thấp kéo dài là tín hiệu saturation. Chỉ page khi có thêm request queue/latency hoặc throughput bị ảnh hưởng, trừ khi baseline chứng minh mức idle thấp tự nó đã là rủi ro cần can thiệp.

```promql
kafka_server_request_handler_avg_idle_ratio < 0.1
```

Kết hợp `kafka_network_processor_avg_idle_ratio`, request queue time và CPU. Nếu handler idle thấp nhưng request latency bình thường, có thể workload đang sử dụng tài nguyên hiệu quả mà chưa gây impact.

### 5.6. Disk gần đầy

Disk usage thường lấy từ node exporter hoặc agent của nền tảng, không chỉ từ Kafka JMX. Cần cảnh báo theo thời gian dự kiến đầy, không chỉ theo phần trăm hiện tại.

```promql
100 *
  (node_filesystem_size_bytes{mountpoint="/var/lib/kafka"}
   - node_filesystem_avail_bytes{mountpoint="/var/lib/kafka"})
  / node_filesystem_size_bytes{mountpoint="/var/lib/kafka"} > 85
```

Một alert sớm có thể dùng tốc độ tăng dung lượng để ước lượng thời gian đến khi đầy. Bảo đảm query lọc đúng filesystem Kafka data, loại filesystem ảo và xử lý mount label nhất quán.

### 5.7. JVM heap và GC pressure

Heap cao liên tục, GC time tăng và request latency tăng cùng lúc là tín hiệu mạnh hơn một metric heap đơn lẻ.

```promql
100 * jvm_memory_heap_used_bytes / jvm_memory_heap_max_bytes > 85
```

Đặt `for` 10 phút làm ví dụ. Ngưỡng phải căn cứ heap sizing, collector, workload và memory limit. Đối chiếu GC logs, process RSS, direct/native memory và page cache trước khi tăng heap.

### 5.8. KRaft quorum và controller health

Với Kafka chạy KRaft, controller quorum là thành phần điều khiển metadata. Mất quorum hoặc controller leader election kéo dài có thể ảnh hưởng thay đổi metadata, partition leadership và khả năng vận hành cluster.

Các metric JMX/raft thay đổi theo Kafka version và role. Hãy dùng metric quorum/controller được công bố trong version đang chạy và kết hợp công cụ quản trị quorum như `kafka-metadata-quorum.sh` để xác minh leader, voter và lag. Không copy rule của ZooKeeper mode sang KRaft.

Alert nên phát hiện:

- Không có leader quorum trong thời gian vượt ngưỡng.
- Voter lag tăng hoặc không theo kịp high watermark.
- Leader election xảy ra liên tục.
- Controller process mất khả năng phục vụ.

Đây là nhóm alert cần xác minh bằng cả JMX, CLI và log controller; một metric đơn lẻ không đủ kết luận quorum đã mất.

## 6. Alert cho producer

Producer có thể gặp lỗi ngay cả khi broker khỏe: serialization fail, authorization fail, metadata lỗi, timeout, buffer exhaustion hoặc downstream network không ổn định.

### 6.1. Publish error ratio

Ưu tiên metric ở application layer: số lần gửi thành công/thất bại theo topic hoặc luồng nghiệp vụ. Broker `FailedProduceRequestsPerSec` chỉ là góc nhìn request broker, không phản ánh đầy đủ lỗi serialization trước khi request đến broker.

Ví dụ biểu thức khi ứng dụng xuất counter:

```promql
sum by (service, topic) (rate(app_kafka_producer_send_errors_total[5m]))
/
clamp_min(
  sum by (service, topic) (
    rate(app_kafka_producer_send_errors_total[5m])
    + rate(app_kafka_producer_send_success_total[5m])
  ),
  1
)
```

Chỉ alert theo error ratio khi có đủ request volume. Với traffic thấp, một lỗi đơn lẻ có thể làm ratio tăng 100%; hãy kết hợp số lỗi tuyệt đối, SLO và criticality của event.

### 6.2. Producer retry và request latency

Retry tăng có thể là dấu hiệu broker/network đang chậm hoặc lỗi transient. Retry không đồng nghĩa publish thất bại; producer có thể retry rồi thành công. Alert nên kết hợp:

- Retry rate tăng liên tục.
- Send latency p95/p99 vượt SLO.
- Error ratio hoặc timeout tăng.
- Bufferpool wait ratio/time tăng.

Nếu chỉ retry tăng nhưng publish success và latency vẫn trong SLO, có thể gửi warning/ticket thay vì page.

### 6.3. Producer buffer exhaustion

Producer chờ buffer lâu có thể làm callback/send latency tăng và cuối cùng timeout khi buffer không được giải phóng. Theo dõi `bufferpool-wait-time`, `buffer-available-bytes`, `bufferpool-wait-ratio` tùy client version. Cần phân biệt producer app bị chậm do serialization với producer bị broker/network backpressure.

### 6.4. Schema/serialization errors

Nếu producer không serialize được record do schema incompatibility hoặc dữ liệu sai, broker có thể không nhận bất kỳ request lỗi nào. Đây là alert application-level. Nhóm lỗi này thường cần route về owner của schema/data contract, không tự động page broker team.

## 7. Alert cho consumer và consumer group

Consumer alert cần kết hợp backlog, event age, processing rate, error rate và rebalance. Lag tăng trong vài phút có thể là bình thường nếu có burst và consumer đang bắt kịp.

### 7.1. Consumer lag tăng

```promql
max by (cluster, group, topic) (kafka_consumergroup_lag) > 10000
```

Metric name tùy exporter; ví dụ này không phải JMX metric chuẩn có sẵn trong mọi Kafka client. Cần chọn nguồn lag đáng tin cậy và ghi rõ metric phản ánh committed offset hay position nào.

Để tránh alert sai:

- Chỉ cảnh báo group/topic thuộc workload cần theo dõi.
- Xác nhận group có active consumer và subscription hợp lệ.
- Kết hợp lag với input rate và processing rate.
- Dùng event age để đo SLA theo thời gian.
- Dùng `for` để bỏ qua backlog burst có thể tự phục hồi.

### 7.2. Event age vượt SLA

Ứng dụng có thể export gauge `app_kafka_oldest_unprocessed_event_age_seconds` hoặc histogram publish-to-process latency. Ví dụ:

```yaml
      - alert: KafkaCriticalConsumerFreshnessSLOViolation
        expr: app_kafka_oldest_unprocessed_event_age_seconds{criticality="high"} > 60
        for: 2m
        labels:
          severity: critical
          service: kafka-consumer
          team: orders
        annotations:
          summary: "Event quan trọng đang bị xử lý trễ"
          description: "Tuổi event chưa xử lý của {{ $labels.consumer_group }} trên {{ $labels.topic }} đã vượt 60 giây. Kiểm tra lag, processing rate và lỗi handler."
          runbook_url: "https://runbooks.example.invalid/kafka/consumer-freshness"
```

Đặt timestamp theo một clock source đã đồng bộ. Nếu metric chỉ đo tuổi của event cuối cùng đã xử lý, nó không tương đương tuổi của record cũ nhất đang chờ; định nghĩa metric phải rõ ràng.

### 7.3. Processing error và retry loop

Theo dõi số record lỗi, số retry, số record gửi DLT/DLQ và tỷ lệ xử lý thành công. Alert theo topic/group và loại lỗi đã phân loại. Một handler lỗi với payload vĩnh viễn có thể làm một partition bị kẹt nếu retry không giới hạn.

Không alert chỉ theo tổng exception count nếu exception là lỗi nghiệp vụ dự kiến hoặc được xử lý. Dùng error classification và metric outcome như `success`, `retryable`, `permanent_failure`.

### 7.4. Rebalance tăng bất thường

Rebalance liên tục có thể gây gián đoạn consume và làm lag tăng. Nguyên nhân có thể là member restart, heartbeat/session timeout, max poll interval, network instability hoặc deployment.

Kết hợp rebalance rate với:

- Số member active và partition assignment.
- Consumer process restart count.
- Time between poll/max poll interval.
- Processing time và GC pause.
- Lag/event age.

Một rebalance trong rolling deployment không nhất thiết là incident. Alert khi tần suất vượt baseline và gây freshness/throughput impact.

### 7.5. Consumer không còn xử lý record

Nếu input rate lớn hơn 0 nhưng processing success rate bằng 0 trong một khoảng thời gian, đây là triệu chứng mạnh. Phải xử lý trường hợp không có traffic: `rate()` có thể bằng 0 bình thường. Dùng metric heartbeat/last successful process timestamp và expected traffic window.

## 8. Alert cho Kafka Connect

Connect có worker, connector và task. Worker có thể vẫn sống nhưng một task FAILED khiến một phần dữ liệu không được source/sink.

### 8.1. Task FAILED

Triệu chứng: connector/task ở trạng thái FAILED. REST API của Connect cung cấp trạng thái chi tiết; JMX metrics có thể bổ sung error rate, record rate và task count. Metric cụ thể tùy runtime/plugin/version.

Alert task failed nên gắn `connector`, `task`, `worker` và owner connector. Không gắn stack trace hoặc exception message vào labels.

### 8.2. Source connector không poll hoặc sink connector không ghi

Source connector: poll rate bằng 0 trong khi source system có dữ liệu và lịch chạy yêu cầu poll. Sink connector: records consumed tăng nhưng records sent/committed không tăng, hoặc task error tăng.

Một connector không có dữ liệu nguồn không phải sự cố. Cần metric expected input hoặc source heartbeat để phân biệt idle hợp lệ với task bị treo.

### 8.3. Dead Letter Queue tăng

DLQ rate tăng có thể chỉ ra schema mismatch, invalid payload hoặc downstream rejection. Mức độ dựa trên tỷ lệ, số lượng tuyệt đối và criticality của dữ liệu. Một DLQ spike trên luồng thanh toán cần xử lý khác với telemetry không quan trọng.

### 8.4. Worker imbalance và restart loop

Theo dõi worker count, connector/task placement, task restart và rebalance. Một task liên tục restart có thể tạo throughput thấp dù trạng thái hiện tại báo RUNNING. Alert nên phát hiện restart rate và thời gian ở trạng thái không hoạt động.

## 9. Alert cho Kafka Streams

Kafka Streams cần theo dõi cả processing và state restoration. Application process còn sống không đảm bảo mọi task đang xử lý đúng.

### 9.1. Thread/task không ở trạng thái RUNNING

Theo dõi trạng thái application thread, task assignment và task migration. Cảnh báo khi thread chết hoặc task không được assign kéo dài ngoài cửa sổ rebalance bình thường.

### 9.2. Processing latency và throughput

Alert khi process latency p95/p99 vượt SLO hoặc input rate liên tục lớn hơn output rate, làm event age tăng. Không chỉ dựa trên throughput thấp vì input có thể đang idle.

### 9.3. State restore chậm

Khi instance restart hoặc task migrate, state store có thể cần restore từ changelog. Restore lâu kéo dài thời gian task chưa phục vụ traffic. Theo dõi restore rate, restore latency, standby lag và thời gian task ở trạng thái RESTORING.

### 9.4. Punctuation/stream-time và late records

Với topology event-time, watermark/stream-time chậm hoặc late record tăng có thể ảnh hưởng kết quả windowed aggregation. Cần metric nghiệp vụ để đo event lateness và số record bị drop/side-output theo policy. Không coi mọi late event là lỗi; phải so sánh với grace period và hợp đồng dữ liệu.

## 10. Correlation: nối alert với nhau để tránh nhiều page cho một incident

Một sự cố broker disk đầy có thể đồng thời gây:

- Disk usage high.
- Produce request latency high.
- Under-replicated partitions.
- Consumer lag tăng.
- Processing freshness vi phạm.

Đây có thể là một incident gốc với nhiều triệu chứng. Alertmanager grouping/inhibition và quy trình incident cần giúp người trực nhìn thấy tác động và một tập tín hiệu chẩn đoán thay vì nhiều page độc lập.

### 10.1. Parent symptom và diagnostic alert

| Parent alert | Diagnostic alert có thể liên quan |
|---|---|
| Consumer freshness SLO violation | Consumer lag, rebalance, processing error, broker fetch latency |
| Publish success SLO violation | Produce request failure, broker unavailable, producer buffer wait, auth/schema error |
| Replication safety degraded | Under-replicated, under-min-ISR, disk/network saturation, broker down |
| Connect delivery stopped | Task FAILED, source poll stalled, sink retry/error, REST API unavailable |
| Streams processing stalled | Thread/task not running, state restore slow, RocksDB/GC pressure |

Parent alert thường là page theo impact. Diagnostic alert có thể được group trong cùng notification hoặc chỉ gửi cho team sở hữu hạ tầng.

### 10.2. Alertmanager grouping

Ví dụ cấu hình tối giản:

```yaml
route:
  receiver: platform-chat
  group_by: [alertname, cluster, service]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="critical"
      receiver: platform-pager
      group_wait: 10s
      repeat_interval: 30m
      continue: true
    - matchers:
        - team="orders"
      receiver: orders-oncall

receivers:
  - name: platform-chat
  - name: platform-pager
  - name: orders-oncall
```

Tên receiver là placeholder; cấu hình thực cần tích hợp contact point, webhook hoặc paging service. Thứ tự route, `continue` và matcher phải được kiểm tra theo Alertmanager version.

Các đoạn `- alert:` tiếp theo trong bài là rule entry bổ sung dưới cùng `groups[].rules[]`; khi triển khai, ghép chúng vào file rule hoàn chỉnh thay vì đặt trực tiếp ở root YAML.

### 10.3. Inhibition

Inhibition ngăn alert mức thấp gửi thêm notification khi alert mức cao hơn cùng scope đã firing. Ví dụ broker down có thể inhibit một số alert phụ về request latency của chính broker đó.

```yaml
inhibit_rules:
  - source_matchers:
      - alertname="KafkaBrokerUnavailable"
      - severity="critical"
    target_matchers:
      - service="kafka"
      - severity="warning"
    equal: [cluster, instance]
```

Inhibit phải có `equal` labels đủ chặt để chỉ suppress alert cùng đối tượng. Nếu scope quá rộng, một broker down có thể che mất cảnh báo của broker khác.

### 10.4. Silence không phải là cách sửa alert

Silence phù hợp với maintenance có thời hạn, incident đang xử lý hoặc một alert đã xác định là không cần thông báo trong một khoảng cụ thể. Mọi silence cần có owner, lý do và expiry. Không tạo silence vô thời hạn để che false positive; hãy sửa rule hoặc metric.

## 11. Runbook cho alert Kafka

Runbook biến alert thành hành động lặp lại được. Mỗi runbook nên có:

1. Ý nghĩa alert và điều kiện firing.
2. Tác động có thể xảy ra với producer, consumer và dữ liệu.
3. Dashboard/metric/log/CLI cần mở.
4. Các bước xác định phạm vi.
5. Các nguyên nhân thường gặp và cách phân biệt.
6. Hành động giảm thiểu an toàn.
7. Điều kiện xác nhận recovery.
8. Khi nào cần escalate và team nào sở hữu.
9. Hành động bị hạn chế hoặc cần phê duyệt.

### 11.1. Runbook: Under-replicated partitions

**Mục tiêu:** khôi phục redundancy và xác định vì sao replica không theo kịp.

**Bước 1 — Xác định phạm vi**

- Xem số under-replicated theo broker và cluster.
- Xác định topic/partition bị ảnh hưởng bằng công cụ quản trị Kafka.
- Kiểm tra leader, replica assignment, ISR và min ISR.
- Xác định có trùng maintenance hoặc rolling restart không.

**Bước 2 — Kiểm tra nguyên nhân**

- Broker replica có đang chạy và kết nối được không?
- Disk có đầy, latency cao hoặc I/O lỗi không?
- Network giữa broker có packet loss/throughput saturation không?
- Replica fetcher có bị nghẽn hoặc throttled không?
- GC pause/CPU có làm broker không kịp fetch không?
- Có partition skew hoặc broker quá tải không?

**Bước 3 — Giảm thiểu**

- Khôi phục broker hoặc disk/network đã lỗi theo runbook hạ tầng.
- Giảm workload không thiết yếu nếu broker bị saturation.
- Xác nhận replica có thể bắt kịp và ISR tăng trở lại.
- Không tùy tiện giảm replication factor hoặc min ISR để làm alert biến mất.

**Bước 4 — Xác nhận recovery**

- Under-replicated và under-min-ISR trở về 0.
- ISR ổn định trong một khoảng quan sát.
- Produce success/latency và consumer freshness trở lại SLO.
- Không có offline replica mới phát sinh.

### 11.2. Runbook: Consumer freshness/lag

**Mục tiêu:** khôi phục thời gian xử lý event và bảo đảm backlog không tiếp tục tăng.

**Bước 1 — Xác định phạm vi**

- Xác định group/topic/partition và criticality.
- Xem oldest event age, lag, input rate và processing rate.
- Xem số member, assignment và rebalance gần nhất.
- Kiểm tra consumer có active hay đang ở trạng thái không nhận partition.

**Bước 2 — Tìm điểm nghẽn**

- Handler có exception/retry loop hoặc DLT tăng không?
- Downstream database/API có latency hoặc rate limit không?
- Consumer CPU/GC/heap/thread có bão hòa không?
- Có partition hot key hoặc phân phối key không đều không?
- Broker Fetch latency hoặc network có xấu không?
- Có deploy/rebalance/config change gần thời điểm bắt đầu không?

**Bước 3 — Giảm thiểu**

- Khôi phục downstream dependency hoặc điều chỉnh rate limit theo owner.
- Khắc phục lỗi handler và poison message theo policy.
- Tăng consumer instance chỉ khi partition parallelism, downstream capacity và ordering cho phép.
- Tăng partition chỉ sau khi đánh giá key ordering, storage, broker capacity và migration impact.
- Không reset offset về latest để làm lag về 0 nếu chưa có quyết định nghiệp vụ về việc bỏ qua dữ liệu.

**Bước 4 — Xác nhận recovery**

- Processing rate lớn hơn input rate đủ lâu để backlog giảm.
- Oldest event age trở lại trong SLA.
- Error/retry/DLQ rate về baseline.
- Consumer group ổn định, không rebalance liên tục.
- Đối soát business event nếu có nguy cơ duplicate/missing.

### 11.3. Runbook: Producer publish failures

- Xác định service/topic và tỷ lệ lỗi thực tế.
- Phân loại lỗi serialization, authorization, timeout, broker unavailable, quota hoặc schema.
- So sánh producer send latency/retry/buffer wait với broker Produce request latency.
- Kiểm tra metadata, DNS, TLS/SASL và ACL.
- Xác minh callback/error handling của producer; không coi timeout là chắc chắn record chưa được ghi.
- Khôi phục publish theo idempotency key và kiểm tra duplicate nếu cần replay.
- Xác nhận publish success ratio và end-to-end freshness trở lại SLO.

### 11.4. Runbook: Connect task FAILED

- Gọi Connect REST API để lấy trạng thái connector/task và worker.
- Xem task trace/log, connector plugin version và config change gần nhất.
- Xác minh source/sink credential, schema, network và downstream quota.
- Xem retry/DLQ và record error theo policy.
- Restart task chỉ sau khi xác định nguyên nhân hoặc theo procedure được phê duyệt.
- Xác nhận task RUNNING, throughput hồi phục và sink/source offset tiến triển.

## 12. Quy trình xử lý incident

### 12.1. Triage ban đầu

Khi nhận page:

1. Xác nhận alert đang firing và thời điểm bắt đầu.
2. Xác định service, cluster, topic/group/connector và owner.
3. Xác định impact: publish, consume, freshness, data correctness hay availability.
4. Xác định scope: một partition/broker hay toàn pipeline.
5. Kiểm tra các parent alert và diagnostic alert cùng thời điểm.
6. Mở runbook và dashboard liên quan.
7. Ghi timeline, quyết định và người thực hiện hành động.

### 12.2. Mitigation trước, root cause sau

Trong incident đang ảnh hưởng người dùng, ưu tiên khôi phục SLI bằng hành động an toàn đã có runbook. Không thực hiện thao tác thay đổi dữ liệu hoặc cấu hình có tác động rộng chỉ để xóa alert.

Ví dụ:

- Nếu sink database chậm, phối hợp owner database và kiểm soát input rate; không tùy tiện bỏ offset.
- Nếu một broker disk lỗi, chuyển sang runbook broker/disk và xác nhận replication; không giảm RF để cluster trông khỏe.
- Nếu poison message làm kẹt partition, dùng DLT/retry policy đã thiết kế và giữ lại dữ liệu cần điều tra.

### 12.3. Xác nhận recovery

Alert resolved không tự động chứng minh dịch vụ đã phục hồi. Kiểm tra SLI, event age, backlog, error rate, replication và kết quả nghiệp vụ. Với sự cố dữ liệu, cần reconciliation hoặc replay có kiểm soát.

### 12.4. Post-incident review

Sau incident, ghi lại:

- Timeline và phạm vi ảnh hưởng.
- SLI/SLO bị vi phạm và error budget đã tiêu thụ.
- Trigger ban đầu và nguyên nhân đã xác minh.
- Alert nào phát hiện đúng/sai hoặc đến quá muộn.
- Hành động giảm thiểu có hiệu quả không.
- Khoảng trống monitoring/runbook/ownership.
- Việc cần làm, owner và deadline.

Review tập trung cải thiện hệ thống và quy trình, không quy lỗi cho cá nhân trực.

## 13. Giảm false positive và alert fatigue

### 13.1. Các nguyên nhân false positive

- Threshold đặt theo cảm tính, không theo baseline.
- Alert không có `for` nên firing theo spike ngắn.
- Metric counter reset khi process restart nhưng rule không xử lý đúng.
- Query tổng hợp sai label hoặc đếm trùng broker/partition.
- Không loại maintenance window hoặc deployment đã biết.
- Consumer group không có traffic nhưng rule coi lag/throughput bằng 0 là lỗi.
- Dùng offset lag thay cho event age dù workload có traffic rất khác nhau.
- Một alert firing trên từng partition/client làm hàng trăm notification.

### 13.2. Giảm noise mà không che sự cố

- Dùng symptom metric gắn với SLO.
- Chọn `for` và cửa sổ rate phù hợp.
- Group theo cluster/service/alertname.
- Inhibit alert phụ khi parent incident đã firing.
- Dùng allowlist cho topic/group critical.
- Gắn maintenance silence có expiry.
- Tách warning/ticket khỏi critical page.
- Kiểm tra query với lịch sử thực tế.

### 13.3. Đo chất lượng alert

Theo dõi các chỉ số vận hành alert:

| Chỉ số | Ý nghĩa |
|---|---|
| Actionable alert ratio | Tỷ lệ alert dẫn đến một hành động hữu ích |
| False positive rate | Tỷ lệ alert firing nhưng không có điều kiện cần xử lý |
| Duplicate notification rate | Số notification trùng cùng một incident |
| MTTD | Thời gian trung bình phát hiện sự cố |
| MTTA | Thời gian trung bình xác nhận/nhận xử lý |
| MTTR | Thời gian trung bình khôi phục dịch vụ |
| Alert-to-incident ratio | Tỷ lệ alert thực sự trở thành incident |
| Toil per week | Thời gian đội vận hành tiêu tốn cho cảnh báo lặp lại |

Mục tiêu không phải giảm số alert bằng mọi giá. Mục tiêu là giảm alert không hành động được trong khi vẫn phát hiện sớm sự cố có impact.

## 14. Kiểm thử alert trước production

### 14.1. Kiểm thử Prometheus rules

Kiểm tra cú pháp và rule evaluation bằng `promtool`:

```bash
promtool check rules kafka-alerts.yml
promtool test rules kafka-alerts-test.yml
```

Rule test cần fixture sample cho điều kiện bình thường, vượt ngưỡng, reset counter, thiếu series và label khác nhau. Kiểm tra cả thời điểm alert chuyển pending/firing/resolved.

### 14.2. Kiểm tra Alertmanager config

```bash
amtool check-config alertmanager.yml
```

Kiểm tra route/matcher, receiver, grouping, inhibit và template. Dùng môi trường test hoặc receiver giả để xác minh notification đến đúng team.

### 14.3. Scenario test trên staging

| Scenario | Kết quả mong đợi |
|---|---|
| Dừng một exporter endpoint | Telemetry alert firing; không kết luận nhầm toàn broker service down nếu probe khác vẫn khỏe |
| Tạo replica lag có kiểm soát | Under-replicated alert firing sau `for` |
| Mô phỏng consumer chậm | Lag/event age tăng; alert theo criticality và SLO |
| Gây lỗi handler có thể retry | Retry/error metric tăng; DLQ policy đúng |
| Dừng một Connect task | Task failed alert route đến connector owner |
| Tăng Streams processing latency | Processing latency/freshness alert firing |
| Khởi động lại broker trong maintenance | Alert được group/silence đúng phạm vi, không tạo noise ngoài dự kiến |
| Khôi phục tất cả thành phần | Alert resolved và SLI trở lại baseline |

Chỉ tạo fault injection trên staging hoặc môi trường thử nghiệm được phê duyệt. Không gây mất broker, disk hoặc partition trên production chỉ để thử alert.

### 14.4. Kiểm tra end-to-end notification

Không dừng ở việc Prometheus hiển thị alert firing. Phải xác minh:

- Alertmanager nhận alert.
- Route chọn đúng receiver.
- Grouping/inhibition hoạt động như mong đợi.
- Notification có summary, scope, severity và runbook.
- On-call có thể mở dashboard/runbook.
- Recovery notification được gửi hoặc đóng ticket đúng cách.

## 15. Quy ước quản lý alert trong đội

### 15.1. Ownership

Mỗi alert cần có team sở hữu. Kafka platform team thường sở hữu broker/quorum/replication; application team sở hữu producer/consumer SLI và business processing; integration team sở hữu Connect connector; data platform team có thể sở hữu schema/data contract.

Khi alert đi qua nhiều team, chỉ định một primary owner để điều phối và các dependency owner để hỗ trợ.

### 15.2. Version control

Đặt Prometheus rules, Alertmanager routes và runbook trong Git. Mỗi thay đổi nên có:

- Lý do thay đổi và SLI/impact liên quan.
- Query/threshold mới và baseline chứng minh.
- Owner, severity và route.
- Test fixture hoặc kết quả kiểm thử.
- Dashboard/runbook link.
- Kế hoạch rollback.

### 15.3. Review định kỳ

Sau mỗi incident và theo chu kỳ (ví dụ hàng tháng/quý):

- Xem alert không firing trong thời gian dài nhưng có còn cần không.
- Xem alert có firing nhiều lần mà không có hành động.
- Kiểm tra runbook có còn đúng phiên bản Kafka/Prometheus.
- Kiểm tra owner và receiver có còn hoạt động.
- Đánh giá SLO/threshold khi workload thay đổi.
- Xóa hoặc gộp alert trùng sau khi xác nhận không làm mất coverage.

## 16. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách làm phù hợp |
|---|---|---|
| Page cho mọi metric vượt threshold | Alert fatigue, bỏ lỡ incident quan trọng | Page theo symptom/SLO, metric nguyên nhân là context |
| Chỉ cảnh báo broker UP/DOWN | Không thấy pipeline trễ hoặc event lỗi khi broker vẫn sống | Thêm publish, processing freshness và correctness SLI |
| Coi consumer lag là tuổi event | Threshold sai với workload có throughput khác nhau | Đo oldest event age/publish-to-process latency |
| Page khi CPU/heap tăng đơn lẻ | Nhiều false positive | Kết hợp saturation với latency/throughput/GC impact |
| Đặt `for` quá ngắn | Spike ngắn gây page | Chọn thời gian theo SLO và recovery behavior |
| Đặt `for` quá dài | Phát hiện sự cố muộn | Multi-window alert và severity theo impact |
| Dùng `sum` metric under-replicated ở mọi broker | Có thể đếm trùng partition | Hiểu metric scope và aggregate đúng |
| Label chứa exception, record key hoặc request ID | Cardinality bùng nổ và lộ dữ liệu | Giữ label có tập giá trị hữu hạn |
| Alert không có owner/runbook | Người trực không biết ai xử lý hoặc làm gì | Bắt buộc owner, runbook và dashboard link |
| Silence vô thời hạn | Che giấu sự cố tái diễn | Silence có lý do, owner và expiry |
| Reset consumer offset để xóa lag | Có thể bỏ qua dữ liệu nghiệp vụ | Khắc phục bottleneck, replay theo quy trình được phê duyệt |
| Restart task/broker liên tục để clear alert | Tạo thêm rebalance, duplicate hoặc outage | Tìm nguyên nhân, mitigation có kiểm soát và xác nhận recovery |
| Chỉ kiểm thử Prometheus expression | Notification có thể không đến đúng người | Test cả Alertmanager route và end-to-end delivery |
| Đóng incident khi alert resolved | Dữ liệu vẫn có thể chưa được xử lý hoặc sai lệch | Xác nhận SLI, backlog và business reconciliation |

## 17. Checklist production

- Alert chính gắn với SLI/SLO hoặc một rủi ro có hành động rõ ràng.
- Mỗi alert phân biệt symptom, cause và leading indicator.
- Severity phản ánh impact, scope, duration và recoverability.
- Ngưỡng dựa trên baseline/SLA, có tài liệu giải thích.
- `for`/multi-window phù hợp với thời gian phản ứng.
- Metric và PromQL đúng semantics counter/gauge, đơn vị và label.
- Consumer freshness không chỉ dựa trên offset lag.
- Alert broker/replication/quorum không nhầm telemetry outage với service outage.
- Producer/consumer/Connect/Streams có alert theo application impact.
- Labels ổn định, cardinality có kiểm soát.
- Annotation có summary, description, runbook và dashboard.
- Mỗi alert có owner/team và route.
- Alertmanager group/inhibit đúng scope, không suppress sự cố khác broker.
- Silence có owner, lý do và expiry.
- Runbook có bước triage, mitigation, recovery và escalation.
- Prometheus rules đã được `promtool` kiểm tra.
- Alertmanager config đã được `amtool` kiểm tra.
- Scenario test đã xác minh pending/firing/resolved và notification.
- Có quy trình review false positive và alert fatigue.
- Incident đóng sau khi SLI và business data được xác nhận phục hồi.

## 18. Câu hỏi tự kiểm tra

1. Triệu chứng khác nguyên nhân và tín hiệu cảnh báo sớm như thế nào?
2. Vì sao broker UP không chứng minh event pipeline đáp ứng SLA?
3. SLI, SLO và error budget liên quan thế nào đến alert?
4. Burn rate bằng observed error ratio chia cho đại lượng nào?
5. Vì sao consumer lag không đồng nghĩa event age?
6. Bốn yếu tố nào nên dùng để xác định severity?
7. Khi nào nên page, tạo ticket hoặc chỉ hiển thị dashboard?
8. `for` giúp giảm noise ra sao và có thể gây phát hiện muộn khi nào?
9. Vì sao alert cần owner, runbook và dashboard link?
10. Under-replicated và under-min-ISR khác nhau về impact thế nào?
11. Vì sao cần phân biệt exporter DOWN với broker DOWN?
12. Producer retry tăng có luôn đồng nghĩa publish thất bại không?
13. Làm sao phát hiện consumer backlog đang ảnh hưởng freshness SLO?
14. Vì sao Connect worker RUNNING không đảm bảo mọi task hoạt động?
15. Alertmanager grouping và inhibition khác nhau thế nào?
16. Khi nào dùng silence và vì sao silence cần expiry?
17. Những bước nào cần có trong runbook under-replicated partition?
18. Vì sao alert resolved chưa đủ để đóng incident dữ liệu?
19. `promtool test rules` và `amtool check-config` kiểm tra phần nào?
20. Làm thế nào đo chất lượng alert và giảm alert fatigue?

## 19. Tài liệu tham khảo

- Prometheus — [Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- Prometheus — [Recording rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/)
- Prometheus — [Unit testing rules with promtool](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
- Prometheus — [Alertmanager configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- Prometheus — [Alerting overview](https://prometheus.io/docs/alerting/latest/overview/)
- Google SRE Workbook — [Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- Google SRE Book — [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)
- Apache Kafka — [Monitoring](https://kafka.apache.org/documentation/#monitoring)
- Apache Kafka — [Operations and basic Kafka tools](https://kafka.apache.org/documentation/#operations)

## Kết luận

Cảnh báo hiệu quả bắt đầu từ impact mà producer, consumer hoặc người dùng cảm nhận được; metric nguyên nhân giúp người trực khoanh vùng và khôi phục. Hãy định nghĩa SLI/SLO cho publish, processing freshness, success và correctness; chọn severity theo scope, criticality, duration và khả năng phục hồi. Prometheus rules cần có threshold dựa trên baseline, `for`, labels ổn định, annotation và runbook. Alertmanager grouping/inhibition giúp gom các triệu chứng của cùng incident, còn silence chỉ dùng có thời hạn. Kiểm thử cả rule lẫn đường gửi notification, đo false positive/actionability và xác nhận SLI cùng dữ liệu nghiệp vụ phục hồi trước khi đóng incident.
