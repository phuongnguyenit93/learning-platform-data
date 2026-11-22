# Theo dõi độ trễ hàng đợi, bản chiếu và tiến trình saga

> **Chủ đề:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Quan sát hệ thống (Observability)  
> **Mục tiêu:** Biết cách phát hiện công việc bất đồng bộ bị chậm, xác định độ mới của bản chiếu dữ liệu và nhận diện saga không tiến triển; kết hợp metric, log, trace và trạng thái bền vững để điều tra và phục hồi an toàn.

## 1. Vì sao API thành công chưa có nghĩa quy trình đã hoàn tất?

Trong microservices, API đặt hàng có thể chỉ xác nhận đã nhận lệnh và ghi dữ liệu nguồn. Những việc còn lại chạy qua outbox, message broker, các consumer và một hoặc nhiều saga. HTTP 202 hay 200 ở một bước không nhất thiết chứng minh dữ liệu trên màn hình đã cập nhật, thanh toán đã hoàn tất hoặc hàng đã được giữ.

~~~text
Client
  |
  | POST /orders
  v
Order API
  |
  | Transaction: Order + Outbox
  v
Order DB
  |
  +-- Outbox Relay --> Broker / Queue
                         |
             +-----------+-------------+
             |                         |
             v                         v
      Order Projection          Saga Coordinator
             |                         |
             v                         +--> Reserve Inventory
        Read Model                     +--> Authorize Payment
             |                         +--> Confirm Order
             v                         \--> Compensate nếu lỗi
        GET /orders/{id}
~~~

Ví dụ OrderCreated đã commit, nhưng outbox relay ngừng phát sự kiện. Queue ở broker có thể không có lag vì **event chưa từng đến broker**. Người dùng đọc Order Read Model thấy dữ liệu cũ. Cùng lúc, saga vẫn chờ thông điệp để chuyển bước. Nếu chỉ nhìn CPU, HTTP status hoặc số message trong một queue, đội vận hành có thể bỏ qua nguyên nhân.

Một luồng cần trả lời ba câu hỏi độc lập:

- **Queue:** có bao nhiêu thông điệp đang đợi, chúng đã đợi bao lâu, consumer xử lý nhanh hay chậm?
- **Projection:** thay đổi nguồn đã được phản ánh vào mô hình đọc từ lúc nào và có đầy đủ/đúng đắn không?
- **Saga:** phiên xử lý nghiệp vụ hiện ở trạng thái nào, đã chuyển bước hợp lệ chưa, và có kết thúc đúng deadline không?

Ba loại tiến độ có thể đi khác nhau. Queue trống không đảm bảo read model đúng; bản chiếu mới không đảm bảo Payment đã xác nhận; một saga nhận heartbeat liên tục không có nghĩa công việc nghiệp vụ đã tiến triển.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Đơn vị/tín hiệu điển hình |
|---|---|---|
| Queue backlog | Số thông điệp đang tồn đọng hoặc chưa được xác nhận hoàn tất theo quy ước | message |
| Consumer offset lag | Khoảng cách giữa vị trí cuối của partition và checkpoint consumer group | record/offset |
| Queue waiting time | Khoảng từ khi broker nhận message đến khi consumer bắt đầu xử lý | ms, giây |
| Processing time | Khoảng consumer thực thi nghiệp vụ trên một message | ms, giây |
| Oldest pending age | Tuổi của message lâu nhất chưa hoàn tất | giây, phút |
| Outbox publication lag | Khoảng từ giao dịch nguồn commit đến khi outbox event được publish | ms, giây |
| Projection lag | Độ trễ từ thay đổi nguồn đến lúc kết quả được áp dụng/nhìn thấy ở read model | giây |
| Projection checkpoint | Vị trí hoặc phiên bản sự kiện cuối đã áp dụng bền vững | offset, version, sequence |
| Saga progress | Trạng thái và lịch sử chuyển bước được ghi bền vững | state, version, transition |
| Saga age/step age | Thời gian kể từ lúc saga hoặc bước hiện tại bắt đầu | giây, phút |
| Saga terminal duration | Thời gian từ lúc saga bắt đầu đến trạng thái kết thúc | giây, phút |

Cùng một chữ “lag” có thể chỉ đơn vị rất khác. Dashboard ghi “lag=200” mà không cho biết 200 message, 200 ms hay 200 phiên bản là nguồn gây hiểu nhầm. Tên metric, mô tả, đơn vị và ranh giới hoàn tất phải thống nhất giữa nhóm phát triển và vận hành.

## 3. Đặt mốc thời gian cho đường đi của một sự kiện

Một event có thể trải qua:

~~~text
T0  Source transaction committed
T1  Outbox relay published event
T2  Broker accepted message
T3  Consumer started handling message
T4  Projection/business side effect committed
T5  Broker acknowledgment/checkpoint committed
T6  Read API/cache/index shows the new state
T7  Saga reaches a terminal state, nếu có
~~~

Từ các mốc này:

- Outbox delay = T1 − T0.
- Broker queue wait = T3 − T2.
- Consumer processing duration = T4 − T3.
- Checkpoint/ack delay = T5 − T4.
- Projection end-to-end visibility delay = T6 − T0.
- Saga terminal duration = T7 − saga.startedAt.

Không cộng cơ học các khoảng thời gian nếu các nhánh chạy song song hoặc cache/index cập nhật qua đường riêng. Cần ghi rõ T4 nghĩa là **đã commit bền vững**, không phải “đã gọi hàm save”; T6 nghĩa là người dùng hoặc API mục tiêu thực sự truy vấn được dữ liệu mới.

**Đồng hồ cũng là một dependency quan sát.** Duration đo bên trong một process nên sử dụng đồng hồ đơn điệu khi có thể. Chênh lệch giữa service cần timestamp đáng tin và đồng bộ thời gian. Nếu nguồn và consumer lệch đồng hồ, latency có thể âm hoặc cao giả. Khi clamp giá trị âm về 0 để giữ histogram hợp lệ, cũng phải ghi số lần clock-skew bất thường để tránh che giấu lỗi đo.

## 4. Hàng đợi: theo dõi cả số lượng, tuổi và tốc độ

### 4.1. Offset lag trong Kafka

Với mỗi partition p của một consumer group, gần đúng:

~~~text
lag(p) = endOffset(p) − committedOffset(group, p)

totalLag = SUM(lag(p))
worstPartitionLag = MAX(lag(p))
~~~

Semantics chính xác phụ thuộc API/công cụ đang lấy offset và cách consumer commit. Một số hệ thống cập nhật offset khi nhận message, số khác sau khi xử lý; cần biết checkpoint biểu thị điều gì. Với Kafka, consumer commit offset không tự bảo đảm thay đổi ở database đã bền vững. Nếu ack/commit trước khi ghi projection, lag có thể bằng 0 trong khi dữ liệu bị mất khi process chết.

**Đừng chỉ dùng total lag.** Nếu topic có 12 partition và 90% backlog nằm ở partition 7, việc tăng worker không giải quyết nguyên nhân nếu phân vùng đó vẫn do một luồng xử lý tuần tự đảm nhiệm. Cần soi key skew, message độc, DB row nóng và thời gian xử lý riêng của partition.

### 4.2. Backlog khác độ trễ tính bằng giây

Giả sử queue có 18.000 message đang chờ, consumer xử lý được 500 message/giây khi không có đầu vào mới:

~~~text
Ideal drain time = 18.000 / 500 = 36 giây
~~~

Nếu producer tiếp tục gửi 400 message/giây, tốc độ làm giảm backlog chỉ còn 100 message/giây:

~~~text
Estimated drain time = 18.000 / (500 − 400) = 180 giây
~~~

Đây là ước tính với tốc độ ổn định, bỏ qua retry, sự lệch partition, tắc nghẽn DB và thay đổi tải. Khi producer rate lớn hơn hoặc bằng successful consumer rate, backlog không thể tự giảm trong điều kiện hiện tại.

Queue chỉ có 5 message nhưng message đầu tiên đã chờ 20 phút có thể nghiêm trọng hơn queue có 10.000 message được xử lý trong vài giây. Đo **oldest pending age**, queue wait p95/p99, incoming rate và successful processing rate bên cạnh backlog.

### 4.3. Tín hiệu kỹ thuật nên thu thập

| Metric logic | Ý nghĩa |
|---|---|
| incoming_messages_total | Số message được broker nhận, dùng rate |
| successful_messages_total | Số event đã được xử lý/commit hợp lệ |
| delivery_attempts_total | Số lần consumer thử nhận/xử lý, bao gồm retry |
| queue_backlog_messages | Công việc còn tồn |
| queue_oldest_pending_age_seconds | Tuổi message chưa xử lý lâu nhất |
| queue_wait_seconds | Phân phối thời gian chờ |
| consumer_processing_seconds | Phân phối thời gian thực thi |
| consumer_inflight_messages | Số message đang xử lý |
| retry_attempts_total | Lần thử lại và loại lỗi |
| dead_letter_messages | Message không thể xử lý theo retry policy |
| consumer_rebalance_total | Tần suất thay đổi phân bổ partition |
| checkpoint_commit_failures_total | Lỗi ghi nhận tiến độ/ack |

Đếm delivery attempts khác đếm **event nghiệp vụ độc nhất đã commit**. Message retry ba lần không có nghĩa đã hoàn thành ba thao tác nghiệp vụ. Có thể dùng event ID/dedup marker trong dữ liệu hoặc luồng transition được ghi chắc chắn.

### 4.4. Những trường hợp dễ đọc nhầm

- **Không có event mới:** lag=0 dù consumer đã chết. Cần heartbeat hoặc tín hiệu có nguồn mới để chứng minh pipeline sẵn sàng.
- **Outbox chưa publish:** broker lag=0, nhưng dữ liệu nguồn đã mới hơn read model.
- **Ack sớm:** offset tiến lên trước khi write DB bền vững; metric nhìn đẹp nhưng correctness bị phá vỡ.
- **Poison message:** một message không parse được bị retry vô hạn, chặn các message sau trên partition.
- **Retry queue riêng:** lag ở queue chính giảm nhưng công việc chuyển sang retry queue; trạng thái nghiệp vụ vẫn chưa xong.
- **DLQ:** message có thể được xem là “đã xử lý” ở tầng broker, nhưng cần người vận hành hoặc cơ chế reconciliation để kết thúc nghiệp vụ.
- **Key skew:** partition nóng tăng backlog, các partition khác trống.
- **Backpressure:** broker không có lag lớn nhưng producer đã bị chặn trước broker; cần quan sát cả upstream.

## 5. Bản chiếu (projection): quan sát độ mới và độ đúng

Projection tạo một dạng dữ liệu phục vụ đọc từ nguồn sự kiện hoặc dữ liệu chuẩn. Ví dụ Order DB là nguồn ghi; Order Read Model phục vụ màn hình tra cứu. Trong CQRS, nguồn và bản chiếu có thể chỉ **nhất quán cuối cùng**.

~~~text
Order DB (source of truth)
  |
  | OrderCreated v1
  | PaymentAuthorized v2
  | OrderConfirmed v3
  v
Outbox / Broker
  |
  v
Projection Consumer
  |
  +-- Validate event
  +-- Deduplicate
  +-- Apply in valid order
  +-- Store checkpoint
  v
Order Read Model
  |
  v
Read API + Cache / Search index
~~~

Bốn chiều quan sát quan trọng:

1. **Freshness:** dữ liệu được đọc mới đến đâu so với cập nhật nguồn?
2. **Progress:** bản chiếu đã áp dụng tới checkpoint/version nào?
3. **Completeness:** event nào chưa tới, bị skip, vào retry hoặc DLQ?
4. **Correctness:** trạng thái và trường nghiệp vụ có đúng với quy tắc chuyển đổi không?

Một projection có offset cuối cùng bằng broker end offset vẫn có thể sai nếu code bỏ qua event hoặc áp dụng out-of-order.

### 5.1. End-to-end projection freshness

Một thước đo gần trải nghiệm người dùng:

~~~text
visibilityDelay(event)
  = time_when_read_API_returns_state_from_event
    − source_commit_time(event)
~~~

Ví dụ minh họa:

| Mốc | Thời điểm |
|---|---:|
| Order DB commit | 12:00:00.000 |
| Outbox publish | 12:00:00.100 |
| Broker accepts | 12:00:00.120 |
| Projection consumer starts | 12:00:01.500 |
| Read Model commits | 12:00:01.620 |
| Cache invalidates / API sees new state | 12:00:01.900 |

Độ trễ commit của read model là 1,62 giây; độ trễ hiển thị qua API là 1,90 giây. Chỉ đo thời gian xử lý consumer 120 ms sẽ bỏ qua phần lớn sự chậm trễ. Đặt tên metric phân biệt **apply lag** và **visibility lag**.

Trong một số kiến trúc search index chỉ queryable sau refresh hoặc cache còn TTL, T6 quan trọng hơn thời điểm write DB trả success.

### 5.2. Source watermark và projection checkpoint

Để biết projection còn nợ gì, cần nguồn so sánh.

~~~text
Source watermark:  newest committed source event/sequence
Applied checkpoint: newest safely applied event/sequence
Checkpoint gap:     difference in the same scope
~~~

Scope là yếu tố quyết định: partition, stream, shard hoặc aggregate có trật tự riêng. Không cộng/trừ version của các aggregate khác nhau như chúng cùng một sequence toàn cục.

Nếu nguồn không phát event mới, timestamp last applied có thể cũ mà projection hoàn toàn bắt kịp. Cảnh báo “now − last applied” một mình sẽ tạo false positive. Kết hợp watermark, heartbeat có ý nghĩa và lưu lượng kỳ vọng để phân biệt **nguồn im lặng** với **projection không tiến**.

### 5.3. Idempotency, thứ tự và checkpoint

Các sự kiện có thể được gửi ít nhất một lần. Consumer phải xử lý duplicate an toàn, thường bằng event ID hoặc aggregate version phù hợp, và bảo đảm không lùi read model về trạng thái cũ.

Khi viết projection và cập nhật checkpoint, cố gắng giữ cùng transaction hoặc thiết kế recovery nếu chúng nằm ở hai hệ thống. Ack broker chỉ sau ranh giới durable thích hợp. Nếu crash sau commit nhưng trước ack, event có thể được giao lại; projection phải idempotent.

Đừng tự động coi nhận event version=5 là đã có version=4. Tùy hợp đồng, phải buffer, retry, reconciliation hoặc xây lại aggregate từ nguồn.

### 5.4. Rebuild, replay và backfill

Khi xây lại projection từ sự kiện lịch sử, timestamp event có thể cách hiện tại nhiều tháng; metric “now − event timestamp” tăng rất lớn dù replay đang chạy đúng.

Phân biệt rõ mode:

- **Live:** xử lý luồng hiện tại phục vụ người dùng.
- **Rebuild:** tạo read model mới từ lịch sử.
- **Backfill:** bổ sung hoặc sửa dữ liệu cũ.
- **Catch-up:** projection mới đang đuổi theo nguồn trước khi cutover.

Theo dõi rebuild epoch, checkpoint start/current/target, remaining events, processing rate, mismatch count và thời điểm bản chiếu mới được phép phục vụ traffic. Không gộp SLI replay với SLI độ mới live.

## 6. Saga: theo dõi tiến trình có trạng thái

Saga phối hợp chuỗi giao dịch cục bộ qua nhiều service. Trong orchestration, coordinator quyết định bước kế tiếp; trong choreography, các service phản ứng bằng event. Dù kiểu nào, hệ thống vẫn cần xác định quy trình nào đang chạy, đã hoàn thành bước nào và có thể phục hồi ra sao.

Ví dụ saga đặt hàng:

~~~text
CREATED
   |
   v
RESERVING_INVENTORY
   |
   v
WAITING_FOR_PAYMENT
   |                   \
   | success            \ failure / timeout
   v                     v
CONFIRMING_ORDER      COMPENSATING
   |                     |
   v                     +--> Release Inventory
COMPLETED                 +--> Void Payment Authorization (nếu cần)
                         |
                         +--> COMPENSATED
                         \--> MANUAL_INTERVENTION_REQUIRED
~~~

**State transition có ý nghĩa nghiệp vụ khác heartbeat kỹ thuật.** Một worker vẫn log “đang retry” nhưng saga kẹt ở WAITING_FOR_PAYMENT trong 30 phút. Một command “AuthorizePayment sent” chỉ chứng minh đã gửi lệnh, chưa chứng minh bên Payment đã xác nhận hoặc side effect đã được commit.

### 6.1. Bản ghi saga bền vững

Ví dụ schema khái niệm:

~~~json
{
  "sagaId": "saga-7f24",
  "sagaType": "ORDER_PLACEMENT",
  "businessReference": "order-123",
  "state": "WAITING_FOR_PAYMENT",
  "stateVersion": 7,
  "startedAt": "2026-11-12T01:00:00Z",
  "stateEnteredAt": "2026-11-12T01:00:02Z",
  "lastTransitionAt": "2026-11-12T01:00:02Z",
  "deadlineAt": "2026-11-12T01:00:30Z",
  "retryCount": 1,
  "terminal": false,
  "lastErrorClass": null,
  "correlationId": "correlation-abc"
}
~~~

Các field có thể khác tùy nền tảng, nhưng cần tối thiểu: saga identity, loại saga, trạng thái, thứ tự/version chuyển trạng thái, mốc bắt đầu, mốc chuyển bước cuối, deadline, kết quả terminal và thông tin đủ cho retry/reconciliation. Hạn chế chứa PII và secret trong record/log.

### 6.2. Ba mức tiến độ

| Mức | Câu hỏi | Bằng chứng |
|---|---|---|
| Infrastructure progress | Consumer/coordinator còn chạy? | Heartbeat, poll count, process health |
| Workflow progress | Saga đã chuyển bước hợp lệ? | Durable transition, stateVersion tăng |
| Business completion | Kết quả cuối đã đúng? | Completed, rejected, compensated hoặc manual action |

Không suy ra business completion từ infrastructure progress. Một workflow có thể liên tục retry và vẫn chưa đi đến bất kỳ trạng thái có ý nghĩa nào.

### 6.3. Stuck saga, deadline và trạng thái terminal

Các đại lượng:

~~~text
sagaAge = now − startedAt
stepAge = now − stateEnteredAt
timeSinceTransition = now − lastTransitionAt
timeToDeadline = deadlineAt − now
terminalDuration = terminalAt − startedAt
~~~

Một saga có thể đang chờ callback bên thứ ba theo chính sách hợp lệ trong 20 phút, trong khi bước DB nội bộ chỉ nên tốn vài giây. Đặt timeout/alert theo sagaType và state, không dùng một giá trị chung cho mọi bước.

Trạng thái terminal phải được đặc tả rõ:

- **COMPLETED:** kết thúc nghiệp vụ thành công.
- **REJECTED/FAILED:** kết thúc không thành công, hậu quả đã được xử lý theo hợp đồng.
- **COMPENSATED:** các side effect trung gian cần hoàn trả đã được bù trừ.
- **MANUAL_INTERVENTION_REQUIRED:** cần thao tác được quản lý và có owner/SLA.

Không đánh dấu terminal giả chỉ để giảm số saga active. Nếu compensation đang chờ xác nhận, phải giữ trạng thái và quan sát riêng.

### 6.4. Cạnh tranh và sự kiện đến trễ

Hai worker có thể cùng nhận callback hoặc timer; cần optimistic locking, compare-and-set/version hoặc transaction phù hợp để chỉ một transition hợp lệ được ghi.

Một PaymentAuthorized callback đến sau khi saga đã chuyển COMPENSATING không tự động đảo ngược trạng thái sang COMPLETED. Cần chính sách reconciliation, xử lý callback trễ và bù trừ dựa trên side effect thực tế. Với payment, tránh retry mù khi request timeout mà chưa biết bên thứ ba đã thực hiện thành công hay chưa.

## 7. Kết nối metric, log, trace và trạng thái bền vững

| Nguồn | Mạnh về | Giới hạn |
|---|---|---|
| Metrics | Xu hướng, dashboard, alert, throughput, distribution | Không lưu chi tiết mỗi event/saga |
| Distributed traces | Đường đi qua service và khoảng chờ | Sampling, retention; async có thể tách trace |
| Structured logs | Chẩn đoán từng event/step/lỗi | Tốn lưu trữ, rủi ro lộ dữ liệu |
| Durable state/checkpoint | Tiến trình chính xác để replay hoặc tiếp tục | Cần thiết kế transaction, schema và quyền truy cập |
| Reconciliation | Phát hiện sai lệch nguồn và read model/side effect | Có thể tốn chi phí và không chạy tức thời |

Không dùng trace làm nguồn sự thật duy nhất cho saga kéo dài nhiều giờ. Trace có thể hết hạn hoặc được sampling; saga phải có persisted state và quy tắc phục hồi.

### 7.1. Correlation và causation

Một event envelope có thể chứa:

~~~json
{
  "eventId": "evt-b81",
  "eventType": "OrderConfirmed",
  "aggregateId": "order-123",
  "aggregateVersion": 3,
  "sourceCommittedAt": "2026-11-12T01:00:00Z",
  "correlationId": "request-456",
  "causationId": "evt-previous",
  "sagaId": "saga-7f24",
  "schemaVersion": 1
}
~~~

- **eventId:** giúp deduplicate và nhận biết một event.
- **correlationId:** liên kết các bước của cùng ngữ cảnh/request nghiệp vụ.
- **causationId:** chỉ event/lệnh dẫn đến event mới.
- **sagaId:** liên kết với state machine của workflow.
- **aggregateVersion:** giúp đánh giá thứ tự trong phạm vi aggregate.

Có thể truyền trace context theo header của message để tạo span/link cho publish và consume. Trong workflow bất đồng bộ dài, span link thường thể hiện quan hệ tốt hơn giữ một span cha mở rất lâu. Không đưa access token, PII hoặc payload nhạy cảm vào trace baggage hay span attributes.

### 7.2. Logging có cấu trúc

Ví dụ log transition có ích:

~~~json
{
  "event": "saga_state_transition",
  "sagaType": "ORDER_PLACEMENT",
  "sagaId": "saga-7f24",
  "fromState": "RESERVING_INVENTORY",
  "toState": "WAITING_FOR_PAYMENT",
  "stateVersion": 7,
  "correlationId": "request-456",
  "outcome": "committed"
}
~~~

Log nên phân biệt attempted/committed/rejected transition. Không in token, password, payment card, private event payload hay chi tiết khách hàng không cần thiết. Retention, phân quyền và redaction phải được định nghĩa.

## 8. Bộ metric tối thiểu

| Metric logic | Kiểu | Phân nhóm phù hợp |
|---|---|---|
| outbox_pending_messages | Gauge | producer, environment |
| outbox_oldest_pending_age_seconds | Gauge | producer |
| queue_backlog_messages | Gauge | queue, consumer_group |
| queue_worst_partition_lag | Gauge | topic, consumer_group |
| queue_oldest_pending_age_seconds | Gauge | queue, consumer_group |
| queue_wait_seconds | Histogram | consumer_type |
| consumer_processing_seconds | Histogram | consumer_type, result |
| consumer_processed_total | Counter | consumer_type, result |
| consumer_retry_attempts_total | Counter | consumer_type, error_class |
| dead_letter_messages | Gauge/Counter theo semantics | queue, error_class |
| projection_checkpoint_gap | Gauge | projection, shard |
| projection_visibility_delay_seconds | Histogram | projection, operation_class |
| projection_reconciliation_mismatch | Gauge/Counter | projection, environment |
| saga_active | Gauge | saga_type, state |
| saga_transition_total | Counter | saga_type, from_state, to_state |
| saga_step_age_seconds | Gauge/Histogram theo phương thức đo | saga_type, state |
| saga_terminal_duration_seconds | Histogram | saga_type, outcome |
| saga_compensation_failures_total | Counter | saga_type, step |

Gauge phản ánh mức hiện tại, counter tăng theo sự kiện, histogram giữ phân phối phục vụ p95/p99. Đặt tên, đơn vị và cách cập nhật theo stack telemetry đang dùng, tránh định nghĩa mơ hồ.

**Cardinality quan trọng:** label nên là giá trị có tập hữu hạn như service, environment, queue, saga_type, state, result hoặc nhóm lỗi. Không đặt orderId, eventId, sagaId, userId, traceId, raw URL hay email thành metric label: số time series sẽ tăng mạnh và có thể rò rỉ thông tin. Định danh chi tiết thuộc log/trace/truy vấn an toàn.

### 8.1. Đo progress đúng

Một pipeline có processed_total tăng nhưng lag vẫn tăng: consumer đang làm việc, nhưng **chậm hơn nguồn**. Processed_total đứng yên trong khi source watermark và oldest age tăng: pipeline có dấu hiệu ngừng tiến. Active saga count tăng mà terminal rate vẫn ổn có thể đơn giản là lưu lượng tăng; phải xem cả tuổi cũ nhất và step age.

Với metric theo partition, không đưa vô số ID động; partition ID nằm trong tập hữu hạn của một topic nhưng vẫn phải cân nhắc số time series nếu có hàng nghìn partition.

## 9. Ví dụ Java/Micrometer: đặt điểm đo sau commit

Một cách tiếp cận là đo queue wait lúc nhận message, đo processing duration trong handler, rồi chỉ ghi “success” sau khi read model đã commit và checkpoint được cập nhật theo hợp đồng.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class OrderProjectionConsumer {
    private final MeterRegistry metrics;
    private final Clock clock;
    private final ProjectionStore projectionStore;

    public OrderProjectionConsumer(
            MeterRegistry metrics,
            Clock clock,
            ProjectionStore projectionStore
    ) {
        this.metrics = metrics;
        this.clock = clock;
        this.projectionStore = projectionStore;
    }

    public void handle(OrderEvent event, Ack ack) {
        Instant started = clock.instant();
        Duration wait = Duration.between(
                event.brokerAcceptedAt(), started
        );

        // Không dùng eventId hay orderId làm metric label.
        metrics.timer(
                "async.queue.wait",
                "consumer", "order_projection"
        ).record(wait.isNegative() ? Duration.ZERO : wait);

        Timer.Sample sample = Timer.start(metrics);
        String outcome = "failure";

        try {
            // Transaction phải xử lý duplicate và checkpoint
            // cùng ranh giới durability phù hợp.
            projectionStore.applyIdempotentlyAndCommit(event);
            ack.acknowledge(); // Chỉ sau durable commit.
            outcome = "success";
        } finally {
            sample.stop(metrics.timer(
                    "async.processing",
                    "consumer", "order_projection",
                    "outcome", outcome
            ));
            metrics.counter(
                    "async.processed",
                    "consumer", "order_projection",
                    "outcome", outcome
            ).increment();
        }
    }
}
~~~

Các kiểu OrderEvent, ProjectionStore và Ack là interface giả định để giải thích ý tưởng, không phải API Spring có sẵn. Thiết kế thật cần giải quyết transaction khi broker và DB không chia sẻ cùng commit, đặc biệt trường hợp DB đã ghi thành công nhưng process chết trước ack: event sẽ được gửi lại và consumer phải idempotent.

Trong ví dụ, brokerAcceptedAt và Clock cần được đánh giá độ tin cậy. Nếu lấy hai timestamp trên các host lệch giờ, queue wait không còn chính xác. Với processing duration trong một process, Micrometer Timer dùng nguồn thời gian đo phù hợp của thư viện.

### 9.1. Đếm transition sau khi lưu trạng thái saga

~~~java
void recordCommittedTransition(
        MeterRegistry registry,
        SagaType type,
        SagaState from,
        SagaState to
) {
    registry.counter(
            "saga.transitions",
            "type", type.metricName(),
            "from", from.metricName(),
            "to", to.metricName()
    ).increment();
}
~~~

Chỉ gọi sau durable state transition. Nếu event transition có thể được xử lý lại làm metric bị đếm nhiều, cần cơ chế dedup hoặc định nghĩa rõ counter đang đếm attempts. Đếm chính xác số saga hoàn thành nên đối chiếu với trạng thái terminal bền vững.

### 9.2. Truy vấn saga active bị quá hạn

Ví dụ ý tưởng SQL:

~~~sql
SELECT saga_type,
       state,
       COUNT(*) AS active_count,
       MAX(EXTRACT(EPOCH FROM
           (CURRENT_TIMESTAMP - state_entered_at)))
           AS oldest_step_age_seconds
FROM saga_instance
WHERE terminal = FALSE
GROUP BY saga_type, state;
~~~

Với bảng rất lớn, không chạy full scan theo mỗi lần scrape metric. Sử dụng index theo state/time, bảng tổng hợp, batch scan hoặc materialized counters có độ nhất quán phù hợp. Dùng kết quả thống kê cho cảnh báo, còn quyết định khôi phục cụ thể phải đọc record saga và side effect thực tế.

## 10. SLI/SLO theo kết quả người dùng

**SLI** đo chất lượng; **SLO** đặt mục tiêu trên SLI. Chọn thước đo từ trải nghiệm/đúng đắn nghiệp vụ thay vì chỉ chọn metric dễ lấy.

### 10.1. Projection SLI

Ví dụ:

~~~text
freshnessSuccessRatio
  = số thay đổi nguồn đủ điều kiện nhìn thấy qua Read API trong <= 5 giây
    / tổng số thay đổi nguồn đủ điều kiện
~~~

Một SLO minh họa: “99% OrderCreated/OrderConfirmed được phản ánh tại Order Read API trong 5 giây, tính trên cửa sổ 28 ngày”. Đây chỉ là ví dụ; chọn ngưỡng theo nhu cầu sản phẩm, chế độ live/rebuild và điều kiện đồng hồ.

### 10.2. Queue processing SLI

~~~text
processingWithinBudgetRatio
  = số distinct valid events commit xử lý thành công trong <= 10 giây từ broker accept
    / số distinct valid events được nhận và đủ tuổi để đánh giá
~~~

Không tính message chuyển DLQ là nghiệp vụ thành công nếu chưa giải quyết side effect. Định nghĩa mẫu số theo cohort đủ tuổi để tránh loại các event đang kẹt khỏi thống kê.

### 10.3. Saga terminal SLI

~~~text
terminalWithinBudgetRatio
  = số saga đủ điều kiện kết thúc terminal hợp lệ trong <= 30 giây
    / tổng saga bắt đầu và đã đủ tuổi để đánh giá
~~~

Không chỉ tính duration của saga đã kết thúc: saga treo vĩnh viễn sẽ biến mất khỏi thống kê và tạo **survivorship bias**. Tách “kết thúc kỹ thuật đúng hợp đồng” khỏi “nghiệp vụ thành công”. Một saga REJECTED đúng chính sách vẫn có thể là kết thúc hợp lệ, nhưng tỷ lệ đặt hàng thành công là SLI nghiệp vụ khác.

### 10.4. Cảnh báo có thể hành động

- Queue oldest age và backlog đều tăng nhiều phút: phân biệt consumer chết, processing chậm và producer tăng tải.
- Outbox pending tăng trong khi broker lag bằng 0: kiểm tra relay publish.
- Projection source watermark tiến nhưng applied checkpoint không tiến hoặc visibility p99 vượt SLO: xem consumer, DB và cache.
- Saga active ở một state vượt deadline: tra step/side effect, không replay mù.
- Compensation failure hoặc manual intervention backlog tăng: ưu tiên điều tra nghiệp vụ.
- Thay đổi phiên bản config/release trùng thời điểm lag tăng: kiểm tra retry, concurrency, timeout và sự tương thích schema.

Áp dụng ngưỡng, cửa sổ thời gian và burn-rate phù hợp lưu lượng, tránh cảnh báo từ một spike ngắn không đáng kể. Với traffic nhỏ hoặc hoàn toàn im lặng, cần kết hợp heartbeat/synthetic event hoặc nguồn watermark đáng tin.

## 11. Dashboard đề xuất

Một dashboard cấp workflow có thể chia thành bốn nhóm:

**Nhóm 1 — Ingestion & Outbox:** source commit rate, outbox pending/oldest age, publish failures, broker accept rate, config revision.

**Nhóm 2 — Queue & Consumer:** incoming rate, processing success/error rate, total lag, worst partition lag, oldest pending age, processing p95/p99, retries, DLQ, rebalances.

**Nhóm 3 — Projection:** source watermark, applied checkpoint, checkpoint gap, visibility p95/p99, live/rebuild mode, reconciliation mismatch, cache/index refresh lag.

**Nhóm 4 — Saga:** started/terminal rate, active count theo state, step age, overdue count, compensation rate/failure, dependency errors và liên kết tra cứu theo sagaId được phân quyền.

Có thể lọc theo environment, region, service và workflow type. Nếu hệ thống multi-tenant, cân nhắc phân nhóm tier hoặc những tenant trọng yếu được phép thay vì tạo một label cho từng tenant.

Các dashboard cần liên kết được với log/trace thông qua correlationId; UI operator có thể tra sagaId hay orderId trong công cụ truy vấn có quyền truy cập, nhưng không biến chúng thành series label của metrics.

## 12. Runbook: khi người dùng nói “đơn hàng vẫn đang xử lý”

**Bước 1 — Xác minh triệu chứng:** xác định order type, số lượng người dùng, tenant, vùng, khoảng thời gian và trạng thái nguồn. Kiểm tra API trả 202 nghĩa là “accepted” hay “completed” theo hợp đồng.

**Bước 2 — Kiểm tra nguồn và outbox:** Order DB đã commit chưa? Outbox event có pending không? Nếu pending tăng, nghi relay, serialization, broker permission hoặc kết nối.

**Bước 3 — Kiểm tra broker:** event đã đến topic/partition chưa? Consumer group lag bao nhiêu? Tập trung partition nóng và oldest age thay vì chỉ tổng backlog.

**Bước 4 — Kiểm tra consumer và DLQ:** throughput thành công, processing p99, retry class, poison event, rebalance, dependency latency, checkpoint/ack. Nếu message chuyển DLQ, đảm bảo có người chịu trách nhiệm xử lý nghiệp vụ.

**Bước 5 — Kiểm tra projection:** checkpoint đã áp dụng event chưa? DB read model mới chưa? Nếu mới nhưng API trả cũ, kiểm tra search index, cache invalidation, read replica và routing.

**Bước 6 — Kiểm tra saga:** durable state là gì? Bước nào vượt deadline? Payment/Inventory side effect đã thực sự commit chưa? Callback có đến trễ/duplicate không? Compensation đã bắt đầu và có đang thất bại không?

**Bước 7 — Khôi phục có kiểm soát:** sửa dependency, giảm tải, tách poison event, retry/backoff hợp lệ, redrive DLQ có dedup, replay/rebuild projection hoặc reconcile saga. Với Payment và thao tác không thể tự động hoàn tác, phải kiểm tra idempotency và trạng thái thực tế trước khi thử lại.

**Bước 8 — Xác nhận kết quả:** backlog giảm, projection bắt kịp source và cho dữ liệu đúng, saga kết thúc hợp lệ, không còn overdue/compensation bất thường và không có giao dịch trùng.

## 13. Các tình huống dễ gây nhầm

| Triệu chứng | Queue | Projection | Saga | Giả thuyết cần kiểm tra |
|---|---|---|---|---|
| Outbox relay chết | Broker lag có thể 0 | Read model stale | Thiếu event để tiến bước | Pending outbox, publish failure |
| Projection consumer chậm | Lag/oldest age tăng | Freshness giảm | Có thể bình thường | DB write, pool, partition skew |
| Cache không invalidated | Queue bình thường | API thấy bản cũ | Có thể completed | Cache, index, replica lag |
| Một poison message | Một partition không tiến | Một tập aggregate stale | Một số saga stuck | Contract, retry, DLQ |
| Callback Payment mất | Queue có thể bình thường | Có thể đã mới | WAITING_PAYMENT quá hạn | Callback routing, reconciliation |
| Compensation thất bại | Retry tăng | Trạng thái trung gian | COMPENSATING kéo dài | Side effect, idempotency |
| Rebuild projection | Lag so với lịch sử lớn | Read model mới chưa ready | Live saga có thể bình thường | Rebuild epoch và cutover |
| Đồng hồ bị lệch | Duration âm/bất thường | SLI sai lệch | Age tính sai | NTP, timestamp ownership |
| Consumer tự ack trước commit | Lag thấp | Có thể thiếu event | Có thể chờ lâu | Durability, ordering |

Bảng này chỉ gợi ý hướng điều tra, không dùng như ánh xạ một-một từ metric sang nguyên nhân. Cần kết hợp checkpoint, traces và trạng thái nguồn để xác minh.

## 14. Thử nghiệm quan sát và phục hồi

| Fault injection có kiểm soát | Tín hiệu cần xuất hiện | Tính đúng đắn cần xác minh |
|---|---|---|
| Dừng consumer tạm thời | Lag và oldest age tăng, processed rate giảm | Không mất event sau phục hồi |
| Giảm tốc xử lý consumer | Producer rate vượt consumer rate | Backlog rút được khi nâng capacity |
| Tạm dừng outbox relay | Outbox age tăng, broker lag có thể không đổi | Không mất source event |
| Làm DB projection chậm | Processing p99 và checkpoint gap tăng | Read model vẫn nhất quán |
| Gửi duplicate event | Duplicate signal tăng | Không tạo bản ghi/tác động trùng |
| Đảo thứ tự các version | Version mismatch/buffer/retry | Không lùi trạng thái aggregate |
| Gửi poison message | Retry có giới hạn và DLQ | Không chặn mãi partition |
| Bật rebuild | Replay progress riêng | Live freshness không bị hiểu nhầm |
| Mất callback thanh toán | Saga step age vượt deadline | Reconciliation/compensation đúng |
| Cho hai worker cập nhật cùng saga | Conflict/version signal | Chỉ một transition hợp lệ được commit |
| Tạo clock skew ở môi trường test | Negative-duration/clock-skew metric | SLO không bị làm đẹp giả |

Các thử nghiệm tác động tới thanh toán hoặc dữ liệu thực phải dùng môi trường cách ly hoặc phạm vi đã được kiểm soát và phê duyệt. Fault injection thành công khi quan sát được hậu quả đúng, cảnh báo hợp lý và đường phục hồi an toàn.

## 15. Những anti-pattern nên tránh

**“Consumer lag = 0, hệ thống chắc chắn khỏe.”** Event có thể đang kẹt trước broker, trong retry/DLQ, hoặc đã ack mà chưa commit read model.

**“Dùng một lastProcessedAt để biết dữ liệu stale.”** Khi không có event mới, timestamp cũ là bình thường. Cần đối chiếu source watermark và lưu lượng kỳ vọng.

**“Đo saga duration chỉ bằng completed records.”** Saga treo không có duration kết thúc, tạo thống kê quá lạc quan. Cần active/overdue count và step age.

**“Có log là đủ lưu tiến độ saga.”** Log có thể bị sampling, mất hoặc hết hạn. Durable state mới cho phép phục hồi một workflow dài.

**“Message đã vào DLQ nghĩa là công việc hoàn tất.”** DLQ là trạng thái xử lý lỗi kỹ thuật, nghiệp vụ vẫn có thể chưa được bù trừ hoặc thông báo.

**“Thêm consumer luôn giải quyết backlog.”** Partition count, hot key, DB connection quota hoặc downstream saturation có thể là giới hạn thật. Scale mù còn làm hỏng dependency.

**“Retry là vô hại.”** Retry Payment hoặc command có side effect khi chưa xác định kết quả trước đó có thể tạo giao dịch lặp. Cần idempotency, state reconciliation và quy tắc retry.

**“Đưa từng orderId/sagaId vào label metric giúp debug.”** Cardinality sẽ bùng nổ; dùng log/trace được phân quyền.

**“Queue latency và projection latency là cùng một con số.”** Projection còn bao gồm source publish delay, consumer xử lý, DB commit, cache/index visibility.

## 16. Bài tập tình huống

Hệ thống Order có Gateway → Order API → Outbox → Kafka → Projection và Saga Coordinator. SLO: 99% thay đổi Order đọc thấy trong 5 giây; 99% saga thông thường đến terminal trong 30 giây.

Tại một thời điểm quan sát:

~~~text
Outbox oldest age:             0,2 giây
Kafka total lag:             9.000 record
Worst partition lag:        7.000 record
Projection processing p99:     40 ms
Projection visibility p99:     22 giây
Saga WAITING_PAYMENT:       1.100 phiên
Oldest WAITING_PAYMENT age:    95 giây
Payment error rate:            tăng
~~~

**Câu hỏi:**

1. Vì sao p99 xử lý projection chỉ 40 ms nhưng visibility p99 tới 22 giây?
2. Vì sao worst partition lag giúp điều tra tốt hơn chỉ total lag?
3. Outbox age thấp nói được gì và chưa nói được gì?
4. Saga WAITING_PAYMENT nhiều có đủ chứng minh Payment đã thất bại không? Cần kiểm chứng nguồn sự thật nào?
5. Cảnh báo nào nên dùng để bảo vệ SLO projection và saga?
6. Có thể khôi phục như thế nào mà không tạo duplicate thanh toán?

**Gợi ý:** kiểm tra tuổi message và thời gian chờ trên partition nóng, so sánh source watermark với applied checkpoint và cache visibility. Với saga, tra durable transitions, Payment transaction status, timeout và callback. Điều chỉnh concurrency khi bottleneck cho phép, sửa dependency và replay theo cơ chế idempotency/reconciliation; không tự phát lại Payment command chỉ vì hệ thống nhìn thấy timeout.

## 17. Checklist triển khai

1. Định nghĩa ranh giới hoàn tất của mỗi bước: broker accept, consumer start, DB commit, checkpoint hay API thấy dữ liệu.
2. Ghi timestamp/source watermark và phân biệt nguồn im lặng với pipeline không tiến.
3. Đo queue backlog, oldest age, wait, processing, arrival/success rate và worst partition.
4. Bao phủ cả outbox, retry queue, DLQ, projection apply và cache/index visibility.
5. Giữ checkpoint theo đúng stream/shard/aggregate; không giả định có thứ tự toàn cục.
6. Bảo đảm idempotency, xử lý duplicate, out-of-order và recovery sau crash.
7. Lưu saga state, stateVersion, startedAt, stateEnteredAt, deadline, terminal result và transition history bền vững.
8. Quan sát saga active, overdue, time in state, terminal duration và compensation failures.
9. Kết nối correlationId, causationId, eventId và sagaId qua log/trace an toàn.
10. Chỉ dùng label metric có cardinality kiểm soát; không đưa ID nghiệp vụ/PII vào label.
11. Đặt SLI/SLO theo tính đúng đắn và độ trễ người dùng thấy, không chỉ HTTP 200.
12. Thiết kế alert dẫn tới hành động cụ thể, dashboard có liên kết điều tra.
13. Thử dừng consumer, poison event, duplicate, callback mất và replay/rebuild.
14. Viết runbook có bước kiểm tra side effect trước khi retry giao dịch quan trọng.
15. Khi phục hồi, xác minh cả backlog, read model correctness và terminal outcomes.

## 18. Ghi nhớ cốt lõi

- **Queue lag** đo công việc chưa theo kịp checkpoint; **projection lag** đo sự chậm trễ đưa thay đổi nguồn vào dữ liệu đọc; **saga progress** đo trạng thái nghiệp vụ được ghi bền vững.
- Một metric đơn lẻ không đủ: cần **số lượng, tuổi, tốc độ, checkpoint, lỗi và tín hiệu hoàn tất thực sự**.
- Projection phải được đo từ **source commit đến trạng thái đọc được**, và phải phân biệt rebuild với live, nguồn im lặng với consumer bị kẹt.
- Saga cần durable state, deadline, step age, terminal/compensation outcome và cơ chế khôi phục an toàn. Log “đã gửi lệnh” không chứng minh side effect thành công.
- Metrics phát hiện xu hướng, traces/logs tìm nguyên nhân, còn checkpoint và business state bảo đảm **phục hồi có căn cứ**.
- Quan sát tốt phải giúp trả lời: **điều gì đang chậm, chậm ở đâu, đã ảnh hưởng người dùng nào, và có thể khôi phục mà không phá tính đúng đắn nghiệp vụ hay không?**
