# Cảnh báo backlog, mất consumer, resource alarm và thông điệp poison

Trong một hệ thống dùng **RabbitMQ và Spring AMQP**, producer có thể vẫn gọi `RabbitTemplate.convertAndSend()` mà không có lỗi rõ ràng, nhưng các sự kiện nằm chờ quá lâu trong queue. Một ứng dụng khác có `@RabbitListener` được cấu hình đúng nhưng consumer biến mất sau khi mạng đứt. Cũng có lúc RabbitMQ chủ động chặn publisher vì thiếu bộ nhớ/đĩa, hoặc chỉ một message không hợp lệ bị giao lại hàng nghìn lần và kéo chậm cả luồng nghiệp vụ.

**Quan sát hệ thống (observability)** cần trả lời không chỉ “broker có đang chạy không?”, mà còn “message được gửi vào đâu, có ai xử lý, có tiến triển không, broker có đang backpressure, và message lỗi có nơi điều tra an toàn không?”. Trong chương **Quan sát hệ thống** của module **SPRING_AMQP**, bài này xây phương pháp **cảnh báo backlog, mất consumer, resource alarm và thông điệp poison**, liên kết exchange–queue–binding, publisher confirms/returns, consumer ACK, retry, dead-letter, giao dịch và idempotency.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `messages_ready`, `messages_unacknowledged`, tổng queue depth, delivery/ACK rate, redelivery và độ tuổi message.
2. Đặt ngưỡng backlog theo **SLO, tốc độ tăng, khả năng xả lô và business age**, không chỉ theo độ sâu tuyệt đối.
3. Phát hiện consumer bị mất, consumer còn đăng ký nhưng không ACK, hoặc consumer bị nghẽn ở database/downstream.
4. Giải thích memory alarm và disk alarm của RabbitMQ, bao gồm ảnh hưởng publisher blocking trong cluster.
5. Phân loại poison message, lỗi transient và duplicate delivery; hiểu vai trò của `x-death`, quorum delivery limit và DLQ.
6. Dùng Spring AMQP retry hữu hạn, ACK sau commit và idempotent consumer để hạn chế vòng retry và tác dụng trùng.
7. Viết PromQL, thiết kế severity, alert grouping và runbook cho bốn nhóm sự cố.
8. Kiểm thử alert bằng failure injection, kể cả khi **metric biến mất** do exporter bị hỏng.

## 2. Bốn nhóm sự cố và các triệu chứng dễ nhầm

| Nhóm | Dấu hiệu phổ biến | Rủi ro nghiệp vụ | Câu hỏi đầu tiên |
| --- | --- | --- | --- |
| **Backlog** | Queue ready và event age tăng | Xử lý chậm, vượt deadline | Tốc độ publish có vượt tốc độ commit/ACK không? |
| **Mất consumer** | Consumer count=0, hoặc ACK ngừng dù count>0 | Không có người xử lý message | Listener có đăng ký và đang tiến triển không? |
| **Resource alarm** | Memory/disk alarm, publisher blocked, confirm timeout | Nhiều producer bị backpressure, outbox dồn | Broker thiếu tài nguyên nào, trên node nào? |
| **Poison message** | Cùng ID lỗi liên tiếp, redelivery/DLQ tăng | Retry storm, kẹt message hợp lệ | Lỗi transient hay không thể phục hồi? |

Các nguyên nhân có thể nối tiếp nhau:

~~~mermaid
flowchart LR
    P["RabbitTemplate / producer"] --> E["Exchange và binding"]
    E --> Q["Work queue"]
    Q --> C["@RabbitListener"]
    C --> DB["Business DB"]
    C -. "Reject/retry" .-> R["DLX / DLQ"]
    C -. "Mất consumer" .-> A1["Ready tăng"]
    A1 -. "Dữ liệu tồn quá lớn" .-> A2["Memory/disk pressure"]
    A2 -. "Broker chặn publish" .-> P
    R -. "Poison tăng" .-> A3["DLQ alert"]
~~~

Không nên tạo một cảnh báo duy nhất “RabbitMQ lỗi”. Một lỗi consumer có thể gây cùng lúc backlog, chậm xử lý và DLQ. Alert phải giúp người trực nhận ra **nguyên nhân gốc và tác động**, không chỉ tạo nhiều thông báo trùng nhau.

## 3. Nguồn metrics và phạm vi đo

Hệ thống cần ít nhất **hai tầng quan sát**:

- **Broker:** queue ready/unacked, consumer count, publish/delivery/ACK/redelivery, connection/channel, memory/disk alarm.
- **Ứng dụng:** publisher confirm/return, outbox pending, handler success/failure, thời gian DB commit, business event age và số duplicate đã bỏ qua.

Broker không thể xác minh một transaction database ngoài broker đã commit. Ngược lại, consumer chưa được gọi không tự biết publish sai exchange hay queue bị block. Muốn truy vết đầu cuối cần `eventId`, vhost, queue, routing key và log có cấu trúc.

### 3.1. RabbitMQ Prometheus và Management API

RabbitMQ cung cấp plugin `rabbitmq_prometheus`, thường mở cổng **15692**, cùng `rabbitmq_management` cho UI/HTTP API. Có ba kiểu scrape thường gặp:

| Endpoint | Phạm vi | Lưu ý |
| --- | --- | --- |
| `/metrics` | Mặc định tổng hợp theo tên metric | Chi phí thấp, nhưng không mặc định có đủ label từng queue |
| `/metrics/per-object` | Per-object metrics cho nhiều loại đối tượng | Có thể tạo payload và overhead lớn khi queue/channel nhiều |
| `/metrics/detailed` | Chỉ những metric family được chỉ định | Phù hợp lấy queue coarse, consumer count và delivery metrics có chọn lọc |

Ví dụ scrape Prometheus cho metric từng queue:

~~~yaml
scrape_configs:
  - job_name: rabbitmq-detailed
    scrape_interval: 15s
    metrics_path: /metrics/detailed
    params:
      family:
        - queue_coarse_metrics
        - queue_consumer_count
        - queue_delivery_metrics
    static_configs:
      - targets:
          - rabbit-1.internal:15692
          - rabbit-2.internal:15692
          - rabbit-3.internal:15692
~~~

Cần cấu hình TLS/quyền truy cập và service discovery phù hợp; không phơi metric endpoint ra Internet. Nếu cần metrics per queue, **đừng mặc định** rằng `/metrics` aggregated đủ dữ liệu để xây alert theo `queue` và `vhost`.

### 3.2. Những metrics quan trọng

Ví dụ từ `/metrics/detailed`:

| Metric | Ý nghĩa |
| --- | --- |
| `rabbitmq_detailed_queue_messages_ready` | Số message đang chờ giao |
| `rabbitmq_detailed_queue_messages_unacked` | Số message đã giao nhưng chưa ACK |
| `rabbitmq_detailed_queue_messages` | Tổng ready và unacked |
| `rabbitmq_detailed_queue_consumers` | Số consumer đăng ký trên queue |
| `rabbitmq_detailed_queue_messages_acked_total` | Tổng message được ACK |
| `rabbitmq_detailed_queue_messages_redelivered_total` | Tổng delivery được giao lại |
| `rabbitmq_detailed_queue_messages_delivered_ack_total` | Tổng message giao đến consumer ở chế độ có manual ACK |
| `rabbitmq_detailed_queue_head_message_timestamp` | Timestamp message đầu queue, khi được thu thập từ nhóm queue_metrics |
| `rabbitmq_detailed_queue_messages_ready_bytes` | Số byte phần message ready trong nhóm queue_metrics |

Metric `...queue_head_message_timestamp` và `...messages_ready_bytes` không thuộc ba family cơ bản trong cấu hình scrape phía trên; cần thêm `queue_metrics` khi thực sự dùng. Phải cân nhắc chi phí vì nhóm chi tiết có thể đắt trên cluster có nhiều queue.

Tên và labels trong exporter khác nhau theo phiên bản/cấu hình. Hãy xác minh output thực tế trước khi áp dụng PromQL. Khi tổng hợp cluster, tránh cộng trùng các số liệu mang phạm vi **cluster-wide** từ mọi node.

### 3.3. RabbitMQ Management API

Management API cung cấp các trường queue như:

~~~text
messages               = messages_ready + messages_unacknowledged
messages_ready         = số đang chờ giao
messages_unacknowledged = số đã giao nhưng chưa ACK
consumers              = số consumer đăng ký
~~~

Node API có những trường phục vụ điều tra như `mem_used`, `mem_limit`, `mem_alarm`, `disk_free`, `disk_free_limit` và `disk_free_alarm` tùy endpoint/phiên bản. Giao diện management thuận tiện khi điều tra trực tiếp, nhưng không thay cho lưu trữ metric và cảnh báo dài hạn.

## 4. Backlog: ready khác unacked

Giả sử có ba queue:

| Queue | Ready | Unacked | Tổng | Nhận định |
| --- | ---: | ---: | ---: | --- |
| A | 9.000 | 0 | 9.000 | Dữ liệu chờ; có thể consumer=0 |
| B | 100 | 2.000 | 2.100 | Consumer đã nhận nhiều nhưng có thể bị kẹt chưa ACK |
| C | 0 | 0 | 0 | Queue trống, chưa chắc producer route đúng |

Nếu chỉ nhìn `messages_ready`, tình huống B có vẻ khỏe trong khi thực tế nhiều transaction bị kẹt. Nếu chỉ nhìn tổng queue depth, không biết đang thiếu consumer hay downstream xử lý chậm.

### 4.1. Độ sâu thay đổi theo lưu lượng

Một mô hình ước lượng:

\[
\frac{dB}{dt}\approx\lambda-\mu
\]

Trong đó `B` là backlog, `λ` là tốc độ message đến queue và `μ` là tốc độ xử lý thành công ra khỏi queue. Ví dụ producer gửi `1.200 message/s`, consumer ACK `900 message/s`: queue tăng ròng khoảng **300 message/s**, hay **18.000 message/phút**.

Lưu ý: đây là ước lượng đơn giản. Requeue, reject, TTL, DLX, transaction và loại queue có thể làm counters lệch mô hình. Delivery rate cao không phải **business throughput** nếu một poison message được giao lại liên tục.

### 4.2. Thời gian xả tồn đọng

Nếu producer và consumer có tốc độ ổn định và `μ>λ`:

\[
T_{\mathrm{drain}}\approx\frac{B}{\mu-\lambda}
\]

Ví dụ queue ready `12.000`, input `200/s`, consumer xử lý `400/s`: thời gian lý tưởng để xả tồn là khoảng **60 giây**. Khi `μ≤λ`, queue không thể hết backlog nếu tải giữ nguyên.

Chọn ngưỡng không chỉ dựa trên số message, mà dựa trên **SLO và tốc độ xả thực tế**. Queue analytics có thể chấp nhận 100.000 message chờ batch, nhưng queue thanh toán có 100 message chờ 10 phút đã có thể vi phạm nghiệp vụ.

### 4.3. Theo dõi tuổi event

Queue depth có thể giảm nhưng event cuối cùng vẫn xử lý chậm. Nên đo:

- **Head-of-queue age** nếu broker/exporter hỗ trợ metric phù hợp.
- **Business event age**: từ `occurredAt`/thời điểm lưu outbox đến lúc commit ở consumer.
- **Time to first successful commit** sau khi consumer khôi phục.
- **Oldest unprocessed event** theo nguồn bền vững, ví dụ outbox hoặc bảng chờ.

Timestamps từ producer và consumer cần được đồng bộ; một event age âm là dấu hiệu lệch clock hoặc sai nguồn thời gian. Không sử dụng timestamp broker một cách mơ hồ để thay thế thời gian nghiệp vụ.

## 5. Chọn ngưỡng backlog theo loại queue

| Loại queue | Tiêu chí phù hợp | Điều không nên làm |
| --- | --- | --- |
| Thanh toán/command quan trọng | Event age và ACK/commit latency chặt | Dùng ngưỡng depth rất cao như analytics |
| Notification | Ready và backlog growth trong vài phút | Page on-call vì một burst vài giây |
| Batch analytics | Thời gian xả trước deadline, dung lượng | Coi mọi queue lớn là incident |
| Delay retry queue | Số message chờ, tuổi và retry budget | Coi không có consumer trực tiếp là lỗi |
| Terminal DLQ | Số message mới và tuổi message chưa triage | Cho rằng DLQ không có consumer là consumer lost |

Có thể chia:

- **Warning** khi backlog tăng kéo dài hoặc vượt baseline.
- **Critical** khi business age vượt SLO, không còn commit hoặc nguy cơ queue chạm giới hạn tài nguyên.
- **Info** cho burst có kế hoạch đang xả đúng hạn.

Giá trị ngưỡng phải xác định dựa trên tải p95/p99, kích thước message, số consumer và năng lực downstream; không nên dùng một cấu hình giống nhau cho mọi queue.

## 6. PromQL minh họa cho backlog

Giả sử `/metrics/detailed` đã trả metrics cho `vhost="/orders"` và `queue="orders.work.queue"`.

### 6.1. Ready vượt ngưỡng liên tục

~~~yaml
groups:
  - name: rabbitmq-queue-alerts
    rules:
      - alert: RabbitMQQueueBacklogHigh
        expr: |
          rabbitmq_detailed_queue_messages_ready{
            vhost="/orders",queue="orders.work.queue"
          } > 2000
        for: 5m
        labels:
          severity: warning
          service: orders
        annotations:
          summary: "Backlog ready cao ở orders.work.queue"
          description: "Kiểm tra consumer, ACK rate, event age."
~~~

`for: 5m` giúp tránh burst ngắn; nhưng với queue giao dịch cực nhạy, ngưỡng thời gian phải dựa trên SLO thực. Nếu metric biến mất, biểu thức so sánh có thể không trả series; cần alert telemetry riêng.

### 6.2. Xu hướng backlog tăng

~~~promql
deriv(
  rabbitmq_detailed_queue_messages_ready{
    vhost="/orders",queue="orders.work.queue"
  }[10m]
) > 2
~~~

`deriv()` tính độ dốc của gauge theo giây. Trên đây kiểm tra backlog đang tăng xu hướng khoảng hơn 2 message/s trong 10 phút, không phải tốc độ publish chính xác.

### 6.3. Có ready message nhưng không có ACK

~~~promql
(
  rabbitmq_detailed_queue_messages_ready{
    vhost="/orders",queue="orders.work.queue"
  } > 0
)
and on (vhost,queue)
(
  rate(
    rabbitmq_detailed_queue_messages_acked_total{
      vhost="/orders",queue="orders.work.queue"
    }[5m]
  ) == 0
)
~~~

Biểu thức này là tín hiệu **không có tiến triển ACK** trong cửa sổ quan sát, nhưng không tự chỉ ra nguyên nhân. Nếu queue dùng consumer no-ack, hoặc metric không được scrape, phải chọn thước đo khác. Với luồng quan trọng, kết hợp timer/metric **DB commit** của ứng dụng thay vì chỉ dựa vào ACK của broker.

## 7. Mất consumer: phân biệt không đăng ký và không tiến triển

“Mất consumer” có thể bao gồm:

1. **Consumer count bằng 0**: broker không còn consumer đăng ký tại queue.
2. **Consumer count vẫn dương nhưng ACK/commit dừng**: listener có thể kẹt DB, HTTP timeout, deadlock hoặc xử lý batch quá lâu.
3. **Consumer đăng ký nhưng không active**: với queue dùng Single Active Consumer (SAC), có thể nhiều standby nhưng chỉ một active nhận delivery.

### 7.1. Consumer count bằng 0

Các nguyên nhân thường gặp:

- Pod crash hoặc OOMKilled, chưa được scheduler phục hồi.
- Listener container không khởi động vì lỗi cấu hình, không tìm thấy queue hoặc quyền `read` thiếu.
- Credential thay đổi hoặc TLS fail khiến `CachingConnectionFactory` không reconnect được.
- Queue bị xóa/đổi tên, listener trỏ nhầm vhost/broker.
- `@RabbitListener` dùng sai `containerFactory` ở hệ thống nhiều broker.
- Ứng dụng đang bảo trì theo kế hoạch.

Ví dụ alert cho work queue cần consumer thường trực:

~~~yaml
- alert: RabbitMQConsumerMissing
  expr: |
    rabbitmq_detailed_queue_consumers{
      vhost="/orders",queue="orders.work.queue"
    } == 0
  for: 2m
  labels:
    severity: critical
    service: orders
  annotations:
    summary: "Không còn consumer đăng ký cho orders.work.queue"
    description: "Kiểm tra pod, listener, authentication, vhost và queue."
~~~

Không dùng rule này cho mọi queue: DLQ chờ triage hoặc retry delay queue có thể **chủ đích** không có consumer trực tiếp.

### 7.2. Consumer count>0 nhưng không xử lý

Ví dụ:

~~~text
queue=orders.work.queue
ready=5,000
unacked=100
consumers=5
ack_rate=0/s
~~~

Có thể tất cả consumer đã nhận message nhưng đang chờ database lock, timeout hoặc thread pool bị nghẽn. Nếu prefetch đã đầy, broker không giao thêm cho các consumer đó.

Runbook cần xem đồng thời:

- Consumer registration và `messages_unacked`.
- Prefetch, concurrency, batch size và acknowledgment mode.
- Handler duration p95/p99, số thread đang làm việc, pool connection DB.
- Lỗi downstream HTTP/JDBC, retry advice, DLQ và redelivery.
- Liệu listener có tạo tác vụ bất đồng bộ rồi return sớm không.

**Tăng số consumer không tự giải quyết** một DB lock hoặc downstream outage; nó có thể khiến các tài nguyên phụ thuộc chịu tải nặng hơn.

### 7.3. Single Active Consumer khác chia tải thông thường

Nếu queue có `x-single-active-consumer=true`, broker chỉ chọn **một active consumer** trên queue dù số consumer đăng ký lớn hơn 1. Vì vậy `consumers=3` không có nghĩa 3 worker cùng xử lý. Việc tăng số pod standby cũng không tăng throughput của queue SAC.

Nếu thứ tự chỉ cần giữ theo `orderId`, có thể phân vùng thành nhiều queue theo key ổn định, mỗi queue có SAC. Khi đó cần metrics/alert theo từng partition, bảo đảm cùng key vào cùng queue và xử lý việc đổi số partition có kế hoạch.

### 7.4. Alert khi telemetry biến mất

Một rule `consumers == 0` có thể **không fire** khi queue bị xóa, exporter tắt hoặc scrape lỗi vì **series không tồn tại**. Cần có:

~~~yaml
- alert: RabbitMQCriticalQueueMetricAbsent
  expr: |
    absent(
      rabbitmq_detailed_queue_consumers{
        vhost="/orders",queue="orders.work.queue"
      }
    )
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Thiếu metric consumer của work queue quan trọng"
    description: "Kiểm tra queue, Prometheus target và RabbitMQ exporter."
~~~

Đồng thời alert `up == 0` đối với scrape target dự kiến. **Metric absent không chứng minh queue đã bị xóa**: queue leader có thể chuyển node, labels hoặc endpoint scrape có thể thay đổi. Phải kiểm tra broker/vhost trực tiếp trước khi kết luận.

## 8. Resource alarm: RabbitMQ chủ động tạo backpressure

RabbitMQ có hai cơ chế bảo vệ tài nguyên đặc biệt quan trọng:

- **Memory alarm** khi node vượt memory watermark.
- **Disk alarm** khi disk free dưới mức tối thiểu.

Khi alarm kích hoạt, RabbitMQ có thể **chặn các connection đang publish** bằng cách ngừng đọc dữ liệu từ publisher, tạo TCP backpressure. Những connection **chỉ consume** thường vẫn có thể nhận delivery và ACK để giảm áp lực. Trong một RabbitMQ cluster, alarm của một node có thể tác động **toàn cluster**.

**Resource alarm không có nghĩa broker đã chết.** Ứng dụng có thể còn thấy TCP connection nhưng publisher bị block hoặc timeout. Với connection vừa publish vừa consume, hiện tượng có thể khó quan sát hơn; khi kiến trúc cho phép, nên tách connection cho publisher và consumer.

~~~mermaid
sequenceDiagram
    participant P as RabbitTemplate
    participant B as RabbitMQ broker
    participant C as @RabbitListener

    P->>B: Publish liên tục
    Note over B: Memory hoặc disk vượt watermark
    B-->>P: connection.blocked / TCP backpressure
    Note over P: Confirm chậm, timeout hoặc publish chờ
    B->>C: Tiếp tục giao message tồn
    C-->>B: ACK sau business commit
    Note over B: Tài nguyên phục hồi
    B-->>P: connection.unblocked / publish tiếp tục
~~~

### 8.1. Memory alarm

Cần xem:

- `mem_used` và memory watermark/`mem_limit` thực tế.
- Memory của queue processes, connection/channel, runtime và plugins.
- Queue ready/unacked **bytes**, không chỉ số message.
- Prefetch/concurrency quá cao, nhiều message chưa ACK.
- Container memory limit, host memory và OOM logs.

Không nên tăng memory watermark bừa bãi để alert biến mất: có thể đẩy RabbitMQ tới OOM. Điều tra nguồn dùng memory, payload outlier, queue backlog, publish rate và giới hạn tài nguyên trước.

### 8.2. Disk alarm

Cần xem:

- `disk_free` và `disk_free_limit` trên node.
- Volume chứa dữ liệu RabbitMQ, dung lượng filesystem và chính sách lưu trữ.
- Persistent messages, queue/stream retention, quorum logs và DLQ.
- Tốc độ tăng disk so với tốc độ xử lý/compact/cleanup hợp lệ.
- Cảnh báo từ hệ điều hành về disk và inode.

Không **purge production work queue** hoặc xóa DLQ chỉ để giải phóng disk. Điều đó có thể xóa dữ liệu nghiệp vụ chưa xử lý. Ưu tiên giảm lưu lượng nguồn, tăng capacity và xử lý retention theo quy trình được phép.

### 8.3. Kiểm tra trực tiếp trên broker

Các lệnh chẩn đoán trên host/node được phép vận hành:

~~~sh
rabbitmq-diagnostics alarms
rabbitmq-diagnostics memory_breakdown
rabbitmq-diagnostics status
~~~

Management API có các trường như `mem_alarm`, `disk_free_alarm`, `mem_used`, `mem_limit`, `disk_free`, `disk_free_limit` tùy endpoint/version. Nếu hệ thống metrics không có sẵn một gauge alarm mong muốn, có thể chuẩn hóa một metric từ API hoặc exporter riêng.

Ví dụ **metric tùy biến do đội vận hành định nghĩa**, **không** mặc định là metric built-in:

~~~text
app_rabbitmq_resource_alarm_active{
  broker="orders",node="rabbit-1",kind="memory"
} 1

app_rabbitmq_resource_alarm_active{
  broker="orders",node="rabbit-1",kind="disk"
} 0
~~~

Tương ứng, một alert có thể là:

~~~yaml
- alert: RabbitMQResourceAlarmActive
  expr: app_rabbitmq_resource_alarm_active == 1
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "RabbitMQ resource alarm trên {{ $labels.node }}"
    description: "Kiểm tra memory/disk, cluster và publisher blocked."
~~~

Metric `app_rabbitmq_resource_alarm_active` ở đây cần một collector có dữ liệu cập nhật đáng tin cậy. Không chép nguyên rule nếu hệ thống chưa xuất metric đó.

## 9. Resource alarm và publisher confirmations

Khi broker chặn publish:

1. `RabbitTemplate` có thể chờ, ném exception hoặc gặp timeout tùy client/transport.
2. Một số publish đang chờ **chưa nhận publisher confirm**.
3. Producer không thể kết luận chắc chắn broker đã nhận hay chưa nếu connection đóng giữa chừng.
4. Outbox có thể tích nhiều event chưa được xác nhận phát hành.
5. Consumer vẫn có thể tiếp tục nhận/ACK nếu có nguồn tài nguyên phù hợp.

Các biện pháp bảo vệ:

- Bật `publisher-confirm-type: correlated` khi dùng Spring AMQP tương ứng.
- Bật `publisher-returns` và `mandatory` để nhận biết trường hợp không route được.
- Giữ event nguồn trong **transactional outbox** cho tới khi có xác nhận publish phù hợp.
- Retry có backoff, **giữ nguyên eventId** và không tạo busy loop khi alarm đang active.
- Quan sát confirm latency, confirm timeout, publisher returns, outbox pending age và connection blocked state.

**Không tạo hàng trăm connection mới để cố vượt cơ chế block publisher.** Đó là backpressure có chủ đích để bảo vệ broker. Hãy khắc phục root cause tài nguyên, giảm rate producer và đảm bảo consumer có thể drain.

## 10. Poison message và vòng requeue

Một **poison message** là message liên tục không thể xử lý thành công, chẳng hạn:

- JSON sai hoặc schema version không tương thích.
- Trường bắt buộc thiếu, dữ liệu không hợp lệ.
- Vi phạm business invariant mà retry không thể sửa.
- Code bug lặp lại với cùng dữ liệu.
- Một sự kiện không thể áp dụng khi thiếu prerequisite/version.
- Lỗi downstream tạm thời bị phân loại sai thành permanent hoặc ngược lại.

Nếu handler ném exception rồi broker requeue ngay lập tức, cùng message có thể lặp lại với tần suất rất cao:

~~~mermaid
flowchart LR
    Q["Work queue"] --> L["@RabbitListener"]
    L --> D{"Xử lý thành công?"}
    D -->|"Có"| ACK["ACK"]
    D -->|"Không và requeue"| Q
    D -->|"Hết retry budget"| X["Reject không requeue"]
    X --> DLX["DLX"]
    DLX --> DLQ["Terminal DLQ"]
~~~

Triệu chứng:

- Cùng `eventId` xuất hiện trong log với exception tương tự.
- `messages_redelivered_total` tăng nhanh.
- Delivery rate cao nhưng số business commit thấp.
- Consumer CPU/log tăng, các message hợp lệ bị chậm.
- DLQ tăng nếu cấu hình đã chuyển message sau retry budget.

**Không mặc định mọi redelivery là poison.** Consumer có thể commit DB rồi chết trước ACK, khiến broker giao lại một message hoàn toàn hợp lệ. Cần phân biệt lỗi lặp thực sự với delivery trùng đã được idempotency xử lý an toàn.

### 10.1. Phân loại trước khi quyết định retry

| Tình huống | Chính sách phù hợp |
| --- | --- |
| DB tạm thời không kết nối được | Retry có backoff hữu hạn |
| Downstream HTTP 429 | Trì hoãn retry, tránh làm hệ thống phụ thuộc quá tải |
| JSON/schema không thể parse | Không requeue vô hạn; cách ly/DLQ để điều tra |
| Event đã xử lý trước đó | Bỏ qua side effect, xác nhận thành công |
| Version đến sai thứ tự | Version guard và workflow chờ gap có giới hạn |
| Consumer chết do lỗi hạ tầng | Connection recovery, redelivery và idempotency |

### 10.2. `redelivered`, `x-death` và `x-delivery-count`

- **Redelivered flag:** dấu hiệu delivery đã được giao trước đó, không phải bộ đếm số lần business handler thất bại.
- **`x-death`:** chứa lịch sử **dead-lettering** theo cơ chế RabbitMQ, không phải số lần Spring Retry thử lại trong một lần listener invocation.
- **`x-delivery-count`:** xuất hiện với **quorum queue** trong các trường hợp được hỗ trợ, phục vụ cơ chế delivery limit.

Lưu ý quan trọng về **phiên bản RabbitMQ**:

1. Từ **RabbitMQ 4.0**, quorum queue có **default delivery limit 20** nếu không được điều chỉnh.
2. Trong những phiên bản trước **4.3**, một số thao tác requeue như `basic.nack` có thể tham gia cách tính giới hạn.
3. Từ **RabbitMQ 4.3**, `basic.nack` không được tính là một **failed delivery** trong `delivery-count`; `basic.reject` và một số tình huống failure khác có cách tính khác. `x-acquired-count` có thể giúp thấy số lần message được gán cho consumer.
4. Vì vậy trên **4.3**, một vòng `basic.nack(requeue=true)` có thể tiếp tục mà **không làm tăng delivery-count đến giới hạn**.

Nếu vượt delivery limit, message có thể bị **drop** hoặc dead-letter nếu queue có DLX hợp lệ. **Không dựa độc lập vào quorum delivery limit để chống mọi vòng retry**; phải thiết kế retry budget tại ứng dụng, DLQ có điểm dừng và kiểm thử đúng version.

### 10.3. DLQ không phải công tắc chữa lỗi

DLQ giữ các message cần điều tra, nhưng có thể mất tác dụng khi:

- DLX không tồn tại, binding hoặc dead-letter routing key sai.
- Queue đích bị xóa, không bền vững hoặc permission/topology lỗi.
- Chính sách TTL/retry DLX tạo vòng quay lại queue nguồn.
- Message bị drop sau delivery limit mà không có đường DLQ.
- Người vận hành purge DLQ trước khi phân loại lỗi.

Một hệ thống tốt cần **terminal DLQ**, alert khi có message mới và runbook replay từng event với `eventId` ổn định.

## 11. Đo poison và nghiệp vụ bằng metrics ứng dụng

Broker metrics không thể cho biết event nào vi phạm invariant. Cần bổ sung các chỉ số ứng dụng:

| Metric quy ước | Ý nghĩa |
| --- | --- |
| `app_amqp_handler_completed_total` | Xử lý thành công sau commit |
| `app_amqp_handler_failed_total` | Lỗi phân theo loại nhỏ, ổn định |
| `app_amqp_handler_duration_seconds` | Thời gian chạy handler |
| `app_amqp_event_age_seconds` | Từ lúc event tạo tới khi commit |
| `app_amqp_duplicate_suppressed_total` | Số bản sao bị chặn bằng idempotency |
| `app_amqp_retry_attempts_total` | Số lần retry có thể quan sát từ application |
| `app_outbox_pending_events` | Event nguồn chưa xác nhận publish |

Những tên bắt đầu `app_` là **quy ước ví dụ**, không phải metric RabbitMQ/Spring Boot chắc chắn đã xuất sẵn.

### 11.1. Label tốt và label xấu

Không đưa `eventId` hoặc toàn bộ exception message vào Prometheus label vì cardinality có thể tăng vô hạn:

~~~text
# Không nên:
app_amqp_handler_failed_total{
  eventId="UUID-khác-nhau-mỗi-lần",exception="SQL timeout at ... "
}

# Nên:
app_amqp_handler_failed_total{
  service="orders",queue="orders.work.queue",errorClass="db_timeout"
}
~~~

`eventId` nên đưa vào **structured log/trace**, kèm queue, message ID, routing key, attempt type và kết quả transaction. Không log password, token hoặc payload chứa dữ liệu nhạy cảm.

## 12. Tương quan alert, nguyên nhân và SLO

Một lỗi consumer crash có thể đồng thời gây:

- `RabbitMQConsumerMissing`.
- `RabbitMQQueueBacklogHigh`.
- `RabbitMQNoAckProgress`.
- `EventAgeSloBreached`.

Sử dụng Alertmanager grouping theo `service`/`queue`/`broker`, cùng inhibition có kiểm soát để tránh on-call bị đánh thức bốn lần bởi một nguyên nhân. Tuy vậy không che mất resource alarm hoặc DLQ critical nếu cần luồng xử lý khác.

| Alert | Mức độ gợi ý | Ai xử lý |
| --- | --- | --- |
| Resource alarm active | Critical | Platform/RabbitMQ on-call phối hợp service owner |
| Work queue quan trọng consumer=0 | Critical | Service on-call |
| Event age vượt SLO | Critical | Service owner và downstream liên quan |
| Backlog tăng chưa vi phạm SLO | Warning | Service owner điều tra trước |
| DLQ có message mới | Warning/Critical tùy nghiệp vụ | Service owner, người phụ trách dữ liệu |
| Redelivery tăng nhưng commit vẫn tốt | Warning | Kiểm tra crash/ACK lost |
| Scrape bị mất | Monitoring critical | Monitoring/Platform on-call |

Trình tự đánh giá khi nhiều alert đến cùng lúc: **broker alarms → telemetry health → consumer state → progress rate → DLQ/poison → outbox/routing → business SLO**. Không chỉ nhìn queue depth rồi scale consumer ngay.

## 13. Ví dụ Spring AMQP: đường xử lý có DLQ và retry hữu hạn

Để cảnh báo có ý nghĩa, trước hết phải có **đường xử lý đáng tin cậy**. Ví dụ sau dùng RabbitMQ durable exchange/queue, binding, terminal DLQ, listener retry hữu hạn và ACK khi hoàn tất.

### 13.1. Topology cho work queue và terminal DLQ

~~~java
package com.example.rabbitmq.observability;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderTopology {

    public static final String EXCHANGE = "orders.events.exchange";
    public static final String ROUTING_KEY = "order.changed";
    public static final String QUEUE = "orders.work.queue";

    public static final String DLX = "orders.events.dlx";
    public static final String DEAD_ROUTING_KEY = "order.failed";
    public static final String DLQ = "orders.work.dlq";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DEAD_ROUTING_KEY)
                .build();
    }

    @Bean
    Binding ordersBinding() {
        return BindingBuilder.bind(ordersQueue())
                .to(ordersExchange())
                .with(ROUTING_KEY);
    }

    @Bean
    DirectExchange ordersDlx() {
        return new DirectExchange(DLX, true, false);
    }

    @Bean
    Queue ordersDlq() {
        // Không đặt DLX quay về work queue: terminal DLQ.
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    Binding ordersDlqBinding() {
        return BindingBuilder.bind(ordersDlq())
                .to(ordersDlx())
                .with(DEAD_ROUTING_KEY);
    }
}
~~~

Topology này giúp xử lý **message đã đến work queue** nhưng không thể hoàn thành. Nó **không** giải quyết sự kiện chưa được publish từ source DB; phần đó cần outbox. Với production dùng quorum queue hoặc policy-based DLX, hãy kiểm tra loại queue và cấu hình thực tế. Không đổi queue arguments của queue đang tồn tại mà không có migration plan.

### 13.2. Listener container với retry hữu hạn

~~~java
package com.example.rabbitmq.observability;

import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ListenerConfiguration {

    @Bean
    Jackson2JsonMessageConverter rabbitJsonConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    SimpleRabbitListenerContainerFactory observedListenerFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter rabbitJsonConverter) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(rabbitJsonConverter);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setConcurrentConsumers(2);
        factory.setMaxConcurrentConsumers(4);
        factory.setPrefetchCount(20);

        factory.setAdviceChain(
                RetryInterceptorBuilder.stateless()
                        .maxAttempts(3)
                        .backOffOptions(500L, 2.0, 2_000L)
                        .recoverer(new RejectAndDontRequeueRecoverer())
                        .build());

        factory.setDefaultRequeueRejected(false);
        return factory;
    }
}
~~~

`maxAttempts(3)` gồm **lần đầu và hai lần retry** trong cùng một chu kỳ listener, không phải ba lần redelivery bền vững qua nhiều lần broker reconnect. `RejectAndDontRequeueRecoverer` khiến message bị từ chối không requeue khi đã hết retry; nếu DLX/binding đúng, message có thể tới DLQ để điều tra.

Phải thử cả lỗi xảy ra **trước khi listener được gọi** (ví dụ JSON converter không đọc được body). Cơ chế error handler mặc định và loại fatal exception có thể khiến đường xử lý khác với exception từ service. Không suy luận rằng mọi lỗi đều chắc chắn được thử lại đúng ba lần.

### 13.3. DTO và listener commit trước ACK

~~~java
package com.example.rabbitmq.observability;

import java.time.Instant;
import java.util.UUID;

public record OrderChanged(
        UUID eventId,
        String orderId,
        long version,
        String status,
        Instant occurredAt
) {}
~~~

~~~java
package com.example.rabbitmq.observability;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderChangedListener {

    private final ObservedOrderService service;

    public OrderChangedListener(ObservedOrderService service) {
        this.service = service;
    }

    @RabbitListener(
            queues = OrderTopology.QUEUE,
            containerFactory = "observedListenerFactory")
    public void onMessage(OrderChanged event) {
        service.applyOnceAndRecord(event);
        // Chỉ return sau khi transaction nghiệp vụ hoàn tất.
    }
}
~~~

Ví dụ dùng `AcknowledgeMode.AUTO`: listener xử lý thành công mới được container ACK. **AUTO của Spring AMQP không phải auto-ack vô điều kiện của RabbitMQ Java client**. Nếu application dispatch vào thread pool rồi return ngay, container có thể ACK trước khi side effect thật sự hoàn tất.

### 13.4. Idempotency với unique constraint

Khi consumer DB đã commit nhưng ACK bị mất, broker có thể redeliver. Một inbox marker nên nằm trong **cùng DB transaction** với cập nhật nghiệp vụ:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_projection (
    order_id VARCHAR(64) PRIMARY KEY,
    version  BIGINT NOT NULL,
    status   VARCHAR(32) NOT NULL
);
~~~

Ví dụ service dùng PostgreSQL và `JdbcTemplate`:

~~~java
package com.example.rabbitmq.observability;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdempotentOrderWriter {

    private final JdbcTemplate jdbc;

    public IdempotentOrderWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean applyOnce(OrderChanged event) {
        int inserted = jdbc.update("""
                INSERT INTO processed_events (consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """, "order-projection", event.eventId());

        if (inserted == 0) {
            return false; // duplicate, side effect đã hoàn tất trước đó
        }

        jdbc.update("""
                INSERT INTO order_projection(order_id, version, status)
                VALUES (?, ?, ?)
                ON CONFLICT (order_id) DO UPDATE
                  SET version = EXCLUDED.version,
                      status = EXCLUDED.status
                WHERE order_projection.version < EXCLUDED.version
                """,
                event.orderId(), event.version(), event.status());
        return true;
    }
}
~~~

`@Transactional` chỉ bảo đảm nguyên tử khi marker và projection nằm trong **cùng database/transaction manager**. `IdempotentOrderWriter.applyOnce()` cần được gọi qua Spring proxy để transaction thực sự được áp dụng. Có thể bổ sung xử lý lỗi missing version nếu nghiệp vụ cần xử lý *mọi bước*, không chỉ projection trạng thái mới nhất.

### 13.5. Nên đo gì ở service?

`ObservedOrderService` có thể gọi writer, rồi ghi:

- `app_amqp_handler_completed_total` sau khi writer return/transaction commit.
- `app_amqp_duplicate_suppressed_total` nếu writer trả false.
- `app_amqp_handler_failed_total` theo errorClass cố định khi ném exception.
- `app_amqp_event_age_seconds` bằng thời điểm commit trừ `occurredAt`.
- `app_amqp_handler_duration_seconds` cho thời gian xử lý.

Không đưa `eventId` hoặc `orderId` vào **metric labels** vì cardinality lớn. Giữ chúng trong structured logs và traces khi cần truy tìm từng sự kiện.

## 14. Producer: quan sát publish trước cả khi vào queue

Nếu một queue có `ready=0`, vẫn chưa thể kết luận producer không có vấn đề. Message có thể chưa từng rời source DB, publish tới exchange không tồn tại, không route vào queue hoặc bị chặn bởi resource alarm.

Trong Spring Boot, có thể bật:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Phân biệt ba loại bằng chứng:

| Tín hiệu | Kết luận có thể rút ra | Điều chưa bảo đảm |
| --- | --- | --- |
| `RabbitTemplate.convertAndSend()` không lỗi | Client đã thực hiện thao tác gửi theo API | Broker đã lưu/route/consumer đã xử lý |
| Publisher confirm ACK | Broker đã xác nhận publish ở chặng producer → broker | Consumer đã commit DB |
| Publisher return vì unroutable | Message không route được trong điều kiện mandatory | Đường sửa topology/replay đã hoàn tất |

Khi mất kết nối trước confirm, kết quả có thể **unknown**: broker đã nhận hoặc chưa. Để không mất event nguồn, lưu cùng `eventId` trong **transactional outbox**, chỉ mark published khi có kết quả publish/routing phù hợp, retry với **ID ổn định** và bảo vệ consumer bằng idempotency.

Những metrics cần bổ sung:

- `app_outbox_pending_events` và tuổi outbox lớn nhất.
- Publisher confirm ACK/NACK/timeout theo exchange/destination.
- Publisher returns/unroutable và lỗi channel/connection.
- Tốc độ event được nguồn tạo so với tốc độ broker xác nhận.
- End-to-end thời gian từ event created đến business commit.

Không coi backlog bằng 0 là khỏe nếu outbox tăng liên tục vì RabbitMQ đang block publisher.

## 15. Runbook: backlog tăng liên tục

**Tín hiệu:** ready vượt baseline, độ dốc dương hoặc event age tăng.

Thứ tự kiểm tra:

1. Xác định đúng broker, virtual host, queue, queue type và service owner.
2. Kiểm tra có **memory/disk resource alarm** không; nếu có, xử lý nguyên nhân tài nguyên trước.
3. Kiểm tra consumer count/active state và handler commit rate.
4. So sánh publish rate, ACK/commit rate và backlog growth.
5. Kiểm tra unacked, prefetch, concurrency, thời gian xử lý và DB/HTTP downstream.
6. Xem có campaign, cron, import hoặc peak traffic được dự báo không.
7. Kiểm tra redelivery, retry loop và DLQ để tránh coi giao lại liên tục là throughput.
8. Ước lượng thời gian drain với năng lực hiện tại và thời hạn SLO.
9. Nếu cần scale, kiểm tra downstream chịu được tải và yêu cầu ordering cho phép.
10. Xác minh **event age trở lại mục tiêu**, không chỉ queue depth giảm.

**Tránh:** purge queue, bật no-ack để xóa unacked, tăng prefetch vô hạn, tăng consumer khi DB đang nghẽn.

## 16. Runbook: mất consumer hoặc consumer không ACK

**Tín hiệu:** `consumers=0` hoặc `consumers>0` nhưng ACK/commit không tiến triển.

1. Kiểm tra mục tiêu scrape còn hoạt động không; `absent` khác `0`.
2. Kiểm tra queue có tồn tại trên đúng vhost/broker không.
3. Xem pod/deployment/job lifecycle, crash, OOM, restart count.
4. Xem listener startup, queue declaration, exception và `PRECONDITION_FAILED`.
5. Kiểm tra authentication, authorization, TLS và connection recovery.
6. Nếu count>0, kiểm tra unacked, prefetch, thread dump, DB locks, HTTP timeouts.
7. Với SAC, xác định consumer nào active, tránh nhầm standby với worker thực.
8. Khôi phục listener với số lượng phù hợp, không tạo reconnect storm.
9. Theo dõi redelivery và idempotency sau restart.
10. Xác minh có **business commit mới** và queue age giảm.

**Tránh:** tắt ACK để làm queue trông trống, bỏ qua lỗi auth vì connection cũ còn sống, scale bừa khi downstream đang lỗi.

## 17. Runbook: memory/disk alarm

**Tín hiệu:** RabbitMQ báo alarm, publisher blocked, confirm latency tăng.

1. Xác nhận loại alarm bằng broker metrics/logs hoặc `rabbitmq-diagnostics alarms`.
2. Xác định node gây alarm và phạm vi ảnh hưởng cluster.
3. Giảm rate publisher hoặc bật backpressure ứng dụng; giữ event chưa xác nhận trong outbox.
4. Kiểm tra consumer có thể tiếp tục ACK/dọn backlog hợp lệ không.
5. Memory: xem queue bytes, số connection/channel, prefetch, message outlier và OOM risk.
6. Disk: xem volume, disk free/limit, queue/stream retention, DLQ và dữ liệu tăng bất thường.
7. Mở rộng capacity hoặc cleanup **đúng retention và quy trình dữ liệu**, không purge tùy tiện.
8. Theo dõi khi alarm clear và publisher được unblocked.
9. Cho outbox retry an toàn, giữ eventId, quan sát confirms/returns.
10. Kiểm tra backlog drain và đối soát dữ liệu nguồn–đích.

**Tránh:** tăng watermark cho qua, tạo thêm connection để “lách” blocked state hoặc coi publish timeout là một NACK chắc chắn.

## 18. Runbook: poison message và DLQ

**Tín hiệu:** cùng eventId thất bại liên tiếp, redelivery tăng, DLQ có message mới.

1. Lấy `eventId`, queue, exchange/key, errorClass và thời điểm lỗi.
2. Phân loại transient/permanent/duplicate/out-of-order.
3. Kiểm tra retry advice, `defaultRequeueRejected`, recoverer và code ném exception.
4. Xem classic hay quorum queue, RabbitMQ version và ngữ nghĩa delivery limit.
5. Kiểm tra `x-death`/`x-delivery-count` đúng theo cơ chế; không coi chúng là số lần mọi retry.
6. Nếu retry storm, giảm tốc độ và chặn vòng requeue vô hạn.
7. Bảo đảm message lỗi ở terminal DLQ/quarantine bền vững, không drop âm thầm.
8. Sửa schema/code/data hoặc hệ thống phụ thuộc trước khi replay.
9. Replay có chọn lọc, tốc độ giới hạn, **giữ eventId gốc** và kiểm tra idempotency.
10. Theo dõi DLQ oldest age, redelivery rate và handler success sau khôi phục.

**Tránh:** xóa DLQ cho dashboard đẹp, replay toàn bộ không phân loại, đổi ID mỗi lần phát lại, để vòng DLX quay mãi.

## 19. Diễn tập cảnh báo bằng failure injection

Các bài thử dưới đây chỉ nên chạy trên **staging**, có broker/queue và message giả lập riêng. Phải đo được cả metric, alert firing/resolution, eventId trong log và kết quả nghiệp vụ.

### Kịch bản A — Backlog do producer nhanh hơn consumer

1. Khởi tạo work queue và consumer có thời gian xử lý có kiểm soát.
2. Gửi message nhanh hơn tốc độ ACK trong 5–10 phút.
3. Đo `messages_ready`, `deriv(ready[10m])` và event age.
4. Xác minh alert backlog fire sau khoảng `for` đã chọn.
5. Giảm publish rate thấp hơn ACK rate.
6. Theo dõi thời gian drain, alert resolve và business age bình thường trở lại.

**Kỳ vọng:** cảnh báo phát hiện mất cân bằng kéo dài, không chỉ một burst nhỏ.

### Kịch bản B — Mất toàn bộ consumer

1. Producer tiếp tục publish vào queue thử.
2. Dừng tất cả listener đang đăng ký với queue.
3. Quan sát consumer count về 0, ready tăng.
4. Xác minh consumer-lost alert fire đúng severity.
5. Khởi động listener lại; đo time-to-first-delivery và time-to-first-commit.
6. Theo dõi backlog drain và redelivery an toàn.

**Kỳ vọng:** biết được nguyên nhân gốc là consumer biến mất, không chỉ queue depth cao.

### Kịch bản C — Consumer còn đăng ký nhưng không ACK

1. Giữ connection và listener hoạt động.
2. Cho business service chờ một downstream giả lập hoặc DB lock.
3. Theo dõi `consumers>0`, `messages_unacked`, ACK rate và thread state.
4. Khôi phục downstream.
5. Xác minh transaction commit/ACK tiếp tục.

**Kỳ vọng:** dashboard không coi consumer count dương là đã đủ khỏe.

### Kịch bản D — Mất endpoint metrics

1. Chặn Prometheus scrape `/metrics/detailed` hoặc dừng exporter ở staging.
2. Xác minh alert `up==0` và `absent(queue metric)` theo cấu hình.
3. Kiểm tra alert backlog không tự hiển thị như một queue có depth bằng 0.
4. Khôi phục scrape và xác minh metric series trở lại.

**Kỳ vọng:** không xuất hiện khoảng mù giám sát âm thầm.

### Kịch bản E — Memory alarm có kiểm soát

1. Sử dụng một RabbitMQ test node có giới hạn tài nguyên an toàn.
2. Thiết lập watermark thử nghiệm và tạo tải đủ gây memory alarm nhưng không làm host OOM.
3. Quan sát publisher blocked, confirm delay/timeout.
4. Xác minh consumer connection tách biệt vẫn có thể xử lý message khi có điều kiện.
5. Giảm tải/giải phóng tài nguyên hợp lệ.
6. Kiểm tra alarm clear và outbox relay phục hồi publish.

**Kỳ vọng:** nhận biết broker backpressure thay vì chẩn đoán nhầm là mạng lỗi.

### Kịch bản F — Disk alarm có kiểm soát

1. Dùng test volume riêng, thiết lập ngưỡng disk an toàn.
2. Tăng lượng dữ liệu thử có kiểm soát tới ngưỡng.
3. Quan sát disk alarm và publisher blocked.
4. Giải phóng tài nguyên test hoặc tăng disk capacity; không xóa dữ liệu nguồn cần giữ.
5. Xác minh alarm clear, queue integrity và publisher confirm hoạt động trở lại.

**Kỳ vọng:** runbook tài nguyên không yêu cầu purge queue production.

### Kịch bản G — Poison message tới terminal DLQ

1. Publish một JSON sai schema hoặc event vi phạm business invariant.
2. Để listener xử lý theo retry budget `maxAttempts(3)`.
3. Quan sát handler failure count và loại exception.
4. Xác minh message bị reject không requeue, đi vào DLQ qua DLX/binding.
5. Sửa lỗi hoặc chuẩn hóa dữ liệu và replay có chọn lọc bằng `eventId` gốc.
6. Theo dõi business commit, redelivery và DLQ count.

**Kỳ vọng:** không có vòng requeue vô hạn và có bằng chứng điều tra.

### Kịch bản H — Quorum queue delivery limit khác phiên bản

1. Tạo quorum queue riêng trên RabbitMQ version cần kiểm tra.
2. Ghi nhận `delivery-limit` và dead-letter policy.
3. Thử `basic.reject` và `basic.nack(requeue=true)` có kiểm soát.
4. Đọc `x-delivery-count` và, khi phiên bản hỗ trợ, `x-acquired-count`.
5. So sánh với tài liệu version đang chạy, đặc biệt hành vi từ 4.3.
6. Xác minh message vượt limit đến DLQ thay vì bị drop nếu cần bảo toàn dữ liệu.

**Kỳ vọng:** không giả định basic.nack luôn làm tăng failed-delivery count.

### Kịch bản I — Publisher confirm thất lạc

1. Tạo `E42` trong transactional outbox.
2. Cho relay publish rồi ngắt connection trước khi nhận confirm.
3. Giữ E42 ở trạng thái có thể retry, không tự kết luận broker chưa nhận.
4. Cho relay phát lại E42 **cùng eventId**.
5. Kiểm tra consumer inbox chặn side effect trùng.
6. Đối chiếu metric outbox age, confirm timeout, dedup hits và queue activity.

**Kỳ vọng:** theo dõi được event từ source, kể cả trước khi broker xác nhận publish.

### Kịch bản J — Consumer commit xong nhưng ACK thất lạc

1. Consumer nhận `E43` và commit DB cùng marker inbox.
2. Mô phỏng ngắt connection trước khi ACK đến broker.
3. Để E43 redeliver sau recovery.
4. Kiểm tra marker ngăn áp dụng business effect lần hai.
5. Xác minh ACK được gửi sau lần nhận lại.

**Kỳ vọng:** redelivery không bị chẩn đoán nhầm thành poison, và không tạo duplicate effect.

### Kịch bản K — Sai binding khiến queue không có backlog

1. Tạm bỏ binding của queue thử trong môi trường staging.
2. Publish tới exchange với `mandatory=true` và publisher returns bật.
3. Quan sát queue ready vẫn bằng 0 dù source/outbox có event.
4. Xác minh returned message hoặc routing failure được ghi nhận.
5. Khôi phục binding rồi retry cùng eventId.

**Kỳ vọng:** queue trống không đánh lừa monitoring khi message chưa route đến queue.

## 20. Những sai lầm cảnh báo phổ biến

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng một ngưỡng `ready>N` cho mọi queue | Burst hợp lệ báo giả; luồng quan trọng báo muộn | Ngưỡng theo SLO và workload |
| Chỉ xem `messages_ready` | Không thấy 2.000 delivery unacked đang kẹt | Theo dõi ready, unacked, ACK/commit |
| Xem `messages=0` là toàn hệ thống khỏe | Outbox có thể dồn hoặc message unroutable | Publisher confirms/returns, outbox age |
| Xem consumer count>0 là đang xử lý | Consumer có thể kẹt DB hoặc SAC standby | ACK rate, handler duration, active consumer |
| Không có `absent`/`up` alert | Exporter chết khiến alert không trả series | Giám sát cả nguồn telemetry |
| Coi resource alarm là network outage | Publisher bị broker chủ động block | Kiểm tra node memory/disk alarm |
| Tăng watermark hoặc purge queue để hết alert | OOM hoặc mất message nghiệp vụ | Capacity, retention và backpressure đúng cách |
| Xem mọi redelivery là poison | ACK thất lạc sau commit cũng tạo bản sao | EventId, exception và idempotency |
| Dựa hoàn toàn vào `x-death` | Spring Retry trong process không được đếm | App retry metrics + DLQ events |
| Dựa vào quorum limit để chặn mọi `basic.nack` trên RabbitMQ 4.3 | Có thể tiếp tục requeue vô hạn | Retry budget riêng, kiểm tra version |
| Bỏ DLX/DLQ hoặc tạo vòng DLX | Message lỗi có thể drop hoặc loop | Terminal DLQ, test route |
| Dùng eventId làm Prometheus label | Cardinality cực lớn | EventId trong structured log/trace |
| Chỉ page alert mà không có runbook | On-call không biết phân loại/root cause | Owner, dashboard link, cách điều tra và khôi phục |

## 21. Checklist triển khai production

- [ ] Mỗi work queue có owner, business SLO, queue type và mức cảnh báo.
- [ ] Có metric ready, unacked, consumer count, ACK rate, redelivery và event age.
- [ ] Scrape per-queue metrics đúng endpoint/families; có cảnh báo exporter down/metric absent.
- [ ] Có backlog alert theo cả độ sâu, xu hướng và thời gian xử lý.
- [ ] Có consumer=0 alert phù hợp; không alert nhầm DLQ/delay queue vốn không có consumer thường trực.
- [ ] Có alert consumer bị kẹt dù consumer count>0.
- [ ] Với SAC, hiểu registered count khác active consumer và giới hạn throughput.
- [ ] Memory/disk resource alarms được cảnh báo theo node và ảnh hưởng cluster.
- [ ] Publisher có confirms/returns; outbox giữ event chưa được xác nhận.
- [ ] Handler chỉ ACK sau commit; idempotency chịu được redelivery.
- [ ] Retry có giới hạn; message không phục hồi được đến terminal DLQ.
- [ ] Quorum delivery limit và cách tính `x-delivery-count` được kiểm tra theo RabbitMQ version.
- [ ] Có metric app handler failure, duration, duplicate suppression và age sau commit.
- [ ] Không log secret hoặc đưa eventId vào metric labels.
- [ ] Alertmanager group theo service/queue/broker, có severity, owner, runbook và silence có hạn.
- [ ] Đã diễn tập backlog, consumer lost/stuck, alarms, poison, confirm lost và ACK lost.
- [ ] Đã xác minh hệ thống phục hồi bằng business commit và backlog drain, không chỉ “connection open”.

## 22. Tài liệu đối chiếu và tổng kết

Tài liệu RabbitMQ chính thức cần đối chiếu với **phiên bản đang sử dụng**:

- [RabbitMQ Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [RabbitMQ — Monitoring with Prometheus and Grafana](https://www.rabbitmq.com/docs/prometheus)
- [RabbitMQ — Memory and Disk Alarms](https://www.rabbitmq.com/docs/alarms)
- [RabbitMQ — Quorum Queues và poison message handling](https://www.rabbitmq.com/docs/quorum-queues)
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)

**Backlog** đo tiến độ xử lý so với đầu vào. **Mất consumer** đo khả năng tiêu thụ hoặc tình trạng không còn ACK. **Resource alarm** là cơ chế tự bảo vệ broker gây backpressure lên publisher. **Poison message** là lỗi của dữ liệu hoặc xử lý có thể tạo redelivery loop và DLQ. Bốn nhóm sự cố có thể cùng xuất hiện, nên cần alert tách được **nguyên nhân, triệu chứng và tác động nghiệp vụ**.

Trong **SPRING_AMQP**, một hệ thống quan sát tốt không dừng ở queue depth. Nó phải xác định được message đã publish và route đúng chưa; consumer có đang xử lý và commit không; ACK có đến broker không; một message lỗi được retry bao nhiêu lần, đi đâu sau khi hết ngân sách và có thể replay an toàn không.

Khi metrics, logs, traces và runbook cùng trả lời được những câu hỏi trên, sự cố RabbitMQ trở thành tình huống **phát hiện sớm, chẩn đoán đúng và phục hồi có kiểm chứng**, thay vì chỉ là một hàng đợi lớn trên dashboard.



