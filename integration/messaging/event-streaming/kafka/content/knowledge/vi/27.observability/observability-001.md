# Thiết kế SLI, SLO theo luồng sự kiện và mục tiêu nghiệp vụ

Một hệ thống Kafka có thể có broker khỏe, producer gửi record thành công và consumer lag thấp nhưng người dùng vẫn không nhận được kết quả đúng hạn. Ví dụ, API tạo đơn hàng đã nhận ACK từ Kafka nhưng dịch vụ thanh toán chưa xử lý event, hoặc notification bị kẹt ở một partition. Vì vậy, quan sát hệ thống event streaming cần bắt đầu từ hành trình nghiệp vụ và đo xem event có đến đúng nơi, đúng thời điểm, được xử lý thành công hay không.

**SLI (Service Level Indicator)** là chỉ số đo chất lượng dịch vụ; **SLO (Service Level Objective)** là mục tiêu đặt cho SLI trong một cửa sổ thời gian; **SLA (Service Level Agreement)** là cam kết với khách hàng, có thể kèm điều khoản và hệ quả khi vi phạm. SLO vận hành thường là công cụ quản trị độ tin cậy nội bộ, không tự động trở thành SLA.

## 1. Bắt đầu từ hành trình nghiệp vụ

Không nên đặt SLO chỉ theo số liệu hạ tầng như CPU broker, request latency hoặc consumer lag. Những metric đó giải thích hệ thống đang hoạt động ra sao, nhưng cần nối chúng với kết quả nghiệp vụ.

Ví dụ hành trình đặt hàng:

~~~mermaid
flowchart LR
    A["Order API accepts request"] --> B["orders topic"]
    B --> C["Payment consumer"]
    C --> D["payments topic"]
    D --> E["Order projection / database"]
    E --> F["Notification service"]
    F --> G["Customer sees confirmation"]
~~~

Các câu hỏi nghiệp vụ cần trả lời:

- Bao nhiêu phần trăm đơn hàng hợp lệ được xử lý hoàn tất?
- Từ lúc chấp nhận đơn đến lúc trạng thái thanh toán được cập nhật mất bao lâu?
- Bao nhiêu event bị thất lạc, xử lý trùng hoặc đưa vào DLQ?
- Khi downstream ngừng hoạt động, backlog có được xử lý lại trong thời gian cam kết không?
- Một khách hàng hoặc tenant có bị ảnh hưởng riêng do partition nóng không?

Hãy lập bản đồ producer, topic, consumer group, stateful processor, sink và hệ thống đích cho từng luồng nghiệp vụ quan trọng. Xác định điểm bắt đầu và điểm kết thúc có ý nghĩa với người dùng trước khi chọn metric.

## 2. Phân biệt SLI, SLO và SLA

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| SLI | Giá trị đo được, có công thức và nguồn dữ liệu rõ ràng | 99,95% đơn hàng được thanh toán hoặc chuyển trạng thái cuối trong 2 phút |
| SLO | Mục tiêu cho SLI trong một cửa sổ thời gian | SLI trên đạt ít nhất 99,9% trong mỗi 30 ngày |
| SLA | Cam kết chính thức với khách hàng/đối tác | Nếu availability dưới mức cam kết, áp dụng service credit theo hợp đồng |

Một SLI tốt phải có:

1. **Đối tượng đo:** request, event, transaction, tenant hoặc luồng nghiệp vụ.
2. **Điều kiện đạt:** định nghĩa rõ thành công, đúng hạn và hợp lệ.
3. **Tử số/mẫu số:** cách tính tỷ lệ không mơ hồ.
4. **Nguồn dữ liệu:** metric, event timestamp, trace, audit log hoặc bảng đối soát.
5. **Phạm vi và cửa sổ:** topic, consumer group, tenant, region và khoảng thời gian.

Không dùng từ “available” hoặc “processed successfully” nếu chưa định nghĩa thế nào là một lần thành công. Producer nhận acks=all là một tín hiệu về durability ở Kafka theo cấu hình replication/ISR, không đồng nghĩa downstream đã hoàn thành nghiệp vụ.

## 3. Các nhóm SLI quan trọng cho event streaming

Một bộ SLI thường gồm nhiều chiều. Không cần biến mọi metric thành SLO; chỉ chọn những chỉ số đại diện trực tiếp cho trải nghiệm hoặc rủi ro nghiệp vụ.

| Nhóm SLI | Câu hỏi cần trả lời | Ví dụ chỉ số |
|---|---|---|
| Availability | Producer/consumer có thể thực hiện chức năng cần thiết không? | Tỷ lệ request publish thành công; tỷ lệ consumer task hoạt động |
| Freshness / latency | Event đến đích có kịp thời không? | Thời gian từ event accepted đến business completion |
| Processing success | Event hợp lệ có được xử lý đúng không? | Tỷ lệ event kết thúc ở trạng thái thành công |
| Durability / completeness | Event có bị mất hoặc bỏ sót không? | Tỷ lệ event đầu vào có kết quả cuối; số event chưa đối soát |
| Throughput / capacity | Hệ thống có xử lý đủ tải không? | Event/s, byte/s và khả năng xử lý backlog |
| Ordering / correctness | Trạng thái có đúng thứ tự và đúng quy tắc không? | Số vi phạm sequence/version theo aggregate |
| Recovery | Sau sự cố, backlog được xử lý lại trong bao lâu? | Thời gian drain backlog sau khi dependency phục hồi |

CPU, heap, disk usage, network, under-replicated partitions, request latency và broker health thường là **diagnostic metrics**. Chúng rất cần để tìm nguyên nhân, nhưng không nên thay thế SLI nghiệp vụ nếu người dùng không trực tiếp cảm nhận chúng.

## 4. Thiết kế SLI availability

Availability của một API publish event có thể đo bằng tỷ lệ request hợp lệ được chấp nhận thành công:

\[
SLI_{publish} =
\frac{\text{Số publish request hợp lệ thành công}}
{\text{Tổng publish request hợp lệ}}
\times 100\%
\]

Định nghĩa “thành công” phải bao gồm điều kiện producer nhận kết quả phù hợp với contract, ví dụ broker ACK theo acks đã chọn. Loại trừ request sai schema hoặc bị từ chối do lỗi validation chỉ khi contract nói rõ chúng không thuộc tập request hợp lệ; không loại bỏ lỗi hệ thống bằng cách gắn nhãn chúng thành invalid.

Chọn rõ đơn vị đếm là một lần gọi API hay một yêu cầu nghiệp vụ logic. Nếu client retry cùng một yêu cầu do timeout, request-level SLI có thể đếm từng lần thử, còn event-level SLI nên đếm một lần theo idempotency key/event ID. Ghi rõ lựa chọn này để retry không vô tình làm phình mẫu số hoặc tạo nhiều event success cho cùng một nghiệp vụ.

Đối với consumer, có thể đo tỷ lệ event đủ điều kiện được xử lý thành công:

\[
SLI_{processing} =
\frac{\text{Event hợp lệ đạt trạng thái terminal success}}
{\text{Tổng event hợp lệ đã đến hạn xử lý}}
\times 100\%
\]

Không dùng số record consumer poll thành công làm mẫu số nếu record có thể được poll nhiều lần do retry/rebalance. Hãy đếm theo event ID hoặc business transaction ID, đồng thời định nghĩa trạng thái terminal success, retrying, rejected và quarantined.

### Availability theo từng chặng

Một hành trình gồm nhiều service có thể có SLI riêng:

- Producer API accepted.
- Record được ghi bền vững vào Kafka theo durability policy.
- Consumer hoàn tất xử lý.
- Kết quả được ghi vào database hoặc hệ thống đích.
- Người dùng nhận được kết quả cuối.

Đo riêng từng chặng giúp xác định nơi xảy ra lỗi. Một SLO end-to-end nên được đo thêm ở điểm cuối nghiệp vụ để không bỏ sót lỗi giữa các chặng.

## 5. Thiết kế SLI latency và freshness

Đối với event streaming, độ trễ quan trọng thường là thời gian từ lúc event được chấp nhận đến lúc kết quả nghiệp vụ sẵn sàng. Gọi:

- t0: thời điểm ứng dụng chấp nhận nghiệp vụ hoặc tạo event theo contract.
- t1: thời điểm producer nhận ACK từ Kafka.
- t2: thời điểm consumer bắt đầu xử lý.
- t3: thời điểm side effect ở hệ thống đích được commit.
- t4: thời điểm người dùng/đối tác có thể quan sát kết quả.

Các khoảng đo:

| Khoảng | Ý nghĩa |
|---|---|
| t1 - t0 | Publish latency |
| t2 - t1 | Queueing/consumption delay gần đúng |
| t3 - t2 | Processing duration |
| t4 - t0 | End-to-end business latency |

CreateTime, LogAppendTime và timestamp do ứng dụng ghi có semantics khác nhau. Nếu dùng event timestamp để đo freshness, phải xác định nguồn đồng hồ, timezone, độ lệch clock và thời điểm chính xác mà timestamp đại diện. Đồng hồ producer và consumer lệch nhau có thể làm phép trừ timestamp sai hoặc âm.

### SLI latency theo ngưỡng

Thay vì chỉ dùng average latency, hãy đặt ngưỡng nghiệp vụ:

\[
SLI_{latency} =
\frac{\text{Event hoàn tất trong ngưỡng } T}
{\text{Tổng event đủ điều kiện}}
\times 100\%
\]

Ví dụ: 99% đơn hàng được cập nhật trạng thái thanh toán trong 120 giây. Chỉ số này đo trực tiếp tỷ lệ event đúng hạn; p95/p99 latency vẫn hữu ích để chẩn đoán tail latency.

Đo cả histogram/percentile và tỷ lệ đáp ứng threshold. Average có thể che giấu một nhóm nhỏ event bị trễ hàng chục phút, trong khi người dùng của nhóm đó chịu ảnh hưởng lớn.

### Freshness khác consumer lag

Consumer lag thường biểu diễn khoảng cách offset giữa log end và vị trí consumer đã xử lý/commit, hoặc một phép quy đổi thành số record. Nó không trực tiếp cho biết event cũ nhất đang chờ bao lâu:

- 10.000 record lag có thể chỉ mất vài giây nếu throughput cao.
- 100 record lag có thể đã chờ nhiều giờ nếu partition không có consumer hoạt động.
- Một partition có thể lag nghiêm trọng trong khi tổng lag toàn group vẫn thấp.
- Offset lag không phản ánh processing duration hoặc thời điểm kết quả đến hệ thống đích.

Vì vậy, kết hợp consumer lag với record age/freshness, processing latency và end-to-end latency.

## 6. Thiết kế SLI completeness, durability và correctness

Đối với event quan trọng như payment, inventory hoặc ledger, chỉ đo availability và latency là chưa đủ. Hệ thống cần biết event có được xử lý đầy đủ và đúng semantics không.

### Completeness

Định nghĩa tập event đã được chấp nhận và tập event đã đạt terminal state:

\[
Completeness =
\frac{\text{Event đã đạt terminal state hợp lệ}}
{\text{Event đầu vào đã đến hạn xử lý}}
\times 100\%
\]

Terminal state có thể gồm success và một số trạng thái business reject hợp lệ. Không tính một event bị mất hoặc nằm trong DLQ chưa được xử lý là thành công chỉ để tăng tỷ lệ completeness.

Chỉ đưa event vào mẫu số khi đã qua deadline xử lý đã quy định. Event mới đến nhưng vẫn còn trong thời hạn xử lý phải ở trạng thái pending, không được tính là failure quá sớm.

### Durability

Durability phụ thuộc replication factor, min.insync.replicas, producer acks, ISR health và cấu hình broker. Ví dụ acks=all yêu cầu leader chờ các replica hiện đang trong ISR xác nhận theo protocol; mức bảo vệ thực tế còn phụ thuộc min.insync.replicas và trạng thái ISR. Nó không chứng minh record đã được consumer xử lý.

Đo durability qua:

- Tỷ lệ publish request được ACK theo durability policy.
- Số lần NotEnoughReplicas/NotEnoughReplicasAfterAppend.
- Under-replicated partitions và offline partitions.
- Đối soát event ID giữa nguồn nghiệp vụ và topic/đích.

Không suy ra “không mất event” chỉ từ việc broker không báo lỗi. Với event tài chính, nên có reconciliation độc lập theo business ID hoặc sequence.

### Correctness và ordering

Correctness thường cần kiểm tra ở tầng domain:

- Tổng tiền, số dư hoặc tồn kho sau xử lý có khớp invariant không?
- Event version có tăng tuần tự theo aggregate không?
- Có transition không hợp lệ như PAID trước CREATED không?
- Có duplicate event ID hoặc xử lý side effect lặp không?

Kafka đảm bảo thứ tự log trong một partition, không đảm bảo thứ tự nghiệp vụ xuyên nhiều partition hoặc thứ tự side effect của ứng dụng xử lý song song. Nếu nghiệp vụ yêu cầu ordering theo entity, dùng key ổn định, kiểm tra sequence/version và thiết kế consumer không hoàn tất sai thứ tự.

## 7. Chọn SLO phù hợp với mức độ quan trọng của luồng

Không phải mọi topic cần cùng SLO. Phân loại theo tác động khi event trễ hoặc mất:

| Tier | Ví dụ | Mục tiêu cần ưu tiên |
|---|---|---|
| Critical | Payment, ledger, inventory reservation | Completeness, correctness, durability, bounded latency và recovery |
| High | Order status, shipment, customer notification trigger | End-to-end freshness, success rate và backlog recovery |
| Standard | Search indexing, analytics enrichment | Eventual freshness, throughput và chi phí vận hành |
| Batch / best effort | Telemetry phụ, báo cáo không realtime | Hoàn tất trong batch window và khả năng replay |

Đặt mục tiêu dựa trên nhu cầu người dùng và khả năng kỹ thuật đã đo được. Không chọn 99,999% chỉ vì con số trông tốt; mục tiêu quá cao có thể tạo chi phí lớn mà không cải thiện trải nghiệm tương ứng.

## 8. Ví dụ SLI/SLO cho luồng Order-to-Payment

Giả sử contract nghiệp vụ là: đơn hàng hợp lệ được chấp nhận, event được publish vào Kafka, payment service xử lý và cập nhật trạng thái trong hệ thống order.

Một bộ mục tiêu minh họa:

| SLI | Cách tính | SLO ví dụ / 30 ngày |
|---|---|---|
| Publish availability | Publish request hợp lệ nhận ACK / tổng request hợp lệ | ≥ 99,95% |
| Payment completion | Order hợp lệ đạt terminal payment state / order đến hạn xử lý | ≥ 99,9% |
| End-to-end freshness | Order có trạng thái thanh toán trong 120 giây / order đủ điều kiện | ≥ 99% |
| Data correctness | Event có state transition hợp lệ / event đã xử lý | ≥ 99,99% |
| Backlog recovery | Backlog sau sự cố được drain trong thời gian mục tiêu | ≤ 20 phút với backlog và tải đã định nghĩa |

Các con số trên là ví dụ để minh họa cách viết SLO, không phải mặc định cho mọi hệ thống. Trước khi áp dụng, đo baseline, thống nhất business deadline, xác định giờ cao điểm, tải cực đại và khả năng downstream.

Một SLO latency phải quy định event nào nằm trong mẫu số. Ví dụ event bị hủy hợp lệ trước khi cần payment có thể được loại khỏi payment completion; event timeout do hệ thống payment unavailable phải được tính là chưa đạt. Quy tắc loại trừ phải được ghi rõ và có thể audit.

## 9. Error budget và quyết định vận hành

Error budget là phần lỗi/không đạt mục tiêu cho phép trong cửa sổ SLO:

\[
ErrorBudget = 1 - SLO
\]

Nếu SLO availability là 99,9% trong 30 ngày, error budget là 0,1% số request hợp lệ trong cửa sổ đó.

Với 1.000.000 request hợp lệ trong kỳ:

\[
AllowedFailures = 1.000.000 \times 0,001 = 1.000
\]

Error budget giúp nhóm cân bằng tốc độ phát hành và độ tin cậy:

- Budget còn nhiều: có thể tiếp tục phát hành theo quy trình kiểm soát.
- Budget tiêu nhanh: giảm rủi ro thay đổi, ưu tiên reliability work.
- Budget cạn: áp dụng release freeze hoặc chỉ cho phép thay đổi phục hồi, tùy policy đã thống nhất.

Error budget phải gắn với SLI/SLO có dữ liệu đáng tin cậy. Nếu metric mất dữ liệu hoặc instrumentation lỗi, không nên mặc định mọi request đều thành công.

## 10. Cửa sổ SLO và cảnh báo burn rate

Có thể dùng rolling window 30 ngày để báo cáo SLO. Cảnh báo vận hành nên phát hiện tốc độ tiêu error budget, không chỉ một ngưỡng metric cố định.

Burn rate được hiểu là tốc độ tiêu budget so với tốc độ cho phép:

\[
BurnRate =
\frac{\text{Tỷ lệ lỗi quan sát trong cửa sổ}}
{\text{Tỷ lệ lỗi cho phép theo SLO}}
\]

Ví dụ SLO 99,9% có error allowance 0,1%. Nếu trong một cửa sổ ngắn tỷ lệ lỗi là 1%, burn rate bằng 10 lần tốc độ cho phép.

Thực tế thường kết hợp cửa sổ dài và ngắn:

- Cửa sổ ngắn phát hiện sự cố đang gây ảnh hưởng mạnh.
- Cửa sổ dài tránh cảnh báo do một spike rất ngắn nhưng không đáng kể.
- Alert nghiêm trọng khi cả hai cửa sổ đều cho thấy budget đang bị tiêu nhanh.

Không chỉ alert khi consumer lag vượt một số record cố định. Chọn ngưỡng theo tốc độ tạo event, deadline nghiệp vụ, thời gian phục hồi và tier của topic.

## 11. Instrumentation: đo event xuyên suốt pipeline

Để đo end-to-end, cần correlation ID hoặc event ID xuyên suốt các service. Một event envelope có thể mang:

~~~json
{
  "eventId": "evt-01J...",
  "correlationId": "order-8472",
  "eventType": "PaymentRequested",
  "aggregateId": "order-8472",
  "aggregateVersion": 4,
  "occurredAt": "2026-11-20T10:15:30.125Z",
  "schemaVersion": 2,
  "payload": {
    "orderId": "order-8472",
    "amountMinor": 259900
  }
}
~~~

Event ID giúp deduplicate và đối soát. Correlation ID nối các event thuộc cùng hành trình. Aggregate version hỗ trợ kiểm tra ordering/state transition. occurredAt là thời điểm nghiệp vụ xảy ra; nên lưu riêng timestamp publish, broker append và processing completion nếu cần đo từng chặng.

Không đưa customer email, token hoặc dữ liệu nhạy cảm vào metric label. Payload có thể chứa PII; trace/log cần masking, access control và retention phù hợp.

### Ví dụ metric instrumentation

Tên metric dưới đây là ví dụ do ứng dụng định nghĩa, không phải metric built-in của Kafka:

~~~text
event_publish_total{topic,result}
event_publish_duration_seconds{topic}
event_processing_total{consumer_group,event_type,result}
event_processing_duration_seconds{consumer_group,event_type}
event_end_to_end_duration_seconds{flow}
event_oldest_unprocessed_age_seconds{topic,consumer_group}
event_dlq_total{topic,reason}
event_duplicate_total{consumer_group,event_type}
event_business_completion_total{flow,result}
~~~

Dùng counter cho số lượng tích lũy, histogram cho latency, gauge cho trạng thái hiện tại như oldest unprocessed age hoặc in-flight count. Với histogram, chọn bucket quanh các deadline nghiệp vụ (ví dụ 1s, 5s, 30s, 120s) để tính tỷ lệ đạt threshold chính xác hơn.

Tránh label có cardinality cao như event ID, order ID, customer ID, offset hoặc exception message. Những giá trị đó phù hợp hơn trong trace/log có sampling và retention phù hợp. Label nên giới hạn ở topic/group/service/region/result hoặc tier có số lượng hữu hạn.

Nếu cần phân tích theo tenant, ưu tiên nhóm tenant theo tier hoặc dùng allowlist có giới hạn. Không gắn mọi tenant ID vào metric label vì số series có thể tăng theo số khách hàng và làm chính hệ thống monitoring quá tải.

## 12. Kafka metrics giúp giải thích SLI

Kafka broker/client metrics là tín hiệu chẩn đoán để tìm nguyên nhân SLO bị ảnh hưởng.

| Thành phần | Metric/nhóm metric cần theo dõi | Liên hệ tới SLO |
|---|---|---|
| Producer | record send rate, request latency, record error rate, retry rate, buffer availability | Publish availability và latency |
| Broker | request handler idle, request queue, network processor idle, request latency, disk I/O | Khả năng phục vụ publish/fetch |
| Replication | under-replicated partitions, ISR shrink/expand, offline partitions, produce errors | Durability và availability |
| Consumer | records consumed rate, fetch latency, commit latency, lag theo partition | Freshness và processing capacity |
| Kafka Streams | process latency, punctuate latency, task/thread state, restore rate, rebalance | End-to-end processing và recovery |
| Kafka Connect | connector/task state, source/sink record rate, task errors, sink lag, DLQ rate | Freshness và completeness của integration |

Tên metric chính xác phụ thuộc Kafka version, client, JMX reporter và framework. Kiểm tra metric catalog của phiên bản triển khai; không copy dashboard từ release khác mà không xác nhận metric có tồn tại và giữ cùng semantics.

Consumer lag cần được phân tách theo partition và group. Tổng lag có thể che giấu một partition nóng hoặc một task bị treo. Với topic quan trọng, theo dõi oldest record age và max lag theo partition cùng với p95/p99 processing latency.

## 13. Dashboard theo câu hỏi vận hành

Một dashboard tốt nên trả lời câu hỏi, không chỉ liệt kê hàng chục metric:

| Dashboard | Câu hỏi | Nội dung chính |
|---|---|---|
| Business SLO | Người dùng có đang nhận kết quả đúng hạn không? | Success ratio, end-to-end latency, completeness, error budget |
| Pipeline health | Event đang tắc ở chặng nào? | Publish rate, consumer lag, oldest age, processing rate, DLQ |
| Kafka cluster | Broker/replication có giới hạn throughput không? | Request latency, ISR, disk, network, controller/metadata health |
| Consumer capacity | Consumer có xử lý kịp tải không? | Per-partition lag, process latency, rebalance, task/thread utilization |
| Data quality | Event có đúng contract không? | Schema errors, invalid transitions, duplicate, missing event |

Luôn hiển thị cửa sổ thời gian, đơn vị, aggregation và phân vùng dữ liệu. Không so sánh latency trung bình với p99 hoặc offset lag của hai consumer group có workload khác nhau.

## 14. Alerting và runbook

Alert nên dựa trên ảnh hưởng SLO hoặc nguy cơ ảnh hưởng sắp tới:

- End-to-end success ratio giảm và burn rate cao.
- Tỷ lệ event vượt deadline tăng.
- Oldest unprocessed age tiến gần business deadline.
- Một partition lag tăng liên tục trong khi các partition khác bình thường.
- DLQ tăng đột biến hoặc poison record lặp lại.
- Under-replicated/offline partitions ảnh hưởng durability.
- Consumer group/Streams application rebalance liên tục hoặc task FAILED.
- Connector FAILED hoặc sink lag vượt khả năng recovery.

Mỗi alert cần có owner, severity, dashboard liên quan, runbook và điều kiện đóng. Alert chỉ dựa trên CPU 80% có thể gây nhiễu nếu chưa có tác động tới SLI; ngược lại, business freshness có thể đã vi phạm dù CPU thấp.

### Ví dụ runbook khi freshness giảm

1. Xác định flow, topic, consumer group và tenant bị ảnh hưởng.
2. Kiểm tra oldest record age, lag theo partition và tốc độ publish/consume.
3. Xác định bottleneck: broker, consumer processing, external database/API hay rebalance.
4. Kiểm tra DLQ, retry rate, exception và schema errors.
5. Nếu downstream chậm, áp dụng rate limit/backpressure để tránh làm hệ thống đích quá tải.
6. Khôi phục consumer/task hoặc dependency theo runbook; không reset offset tùy tiện.
7. Theo dõi backlog drain và xác nhận event đã đạt terminal state.
8. Đối soát event ID/business ID để xác nhận completeness và duplicate.
9. Ghi nhận thời gian ảnh hưởng và cập nhật error budget.

Không tăng consumer vô hạn khi database đích đã bão hòa. Tăng concurrency có thể làm sự cố downstream nặng hơn và kéo dài thời gian phục hồi.

## 15. Đặt mục tiêu backlog recovery

Backlog recovery là một SLI/SLO quan trọng khi downstream outage xảy ra. Giả sử:

- Tốc độ event mới: λ event/giây.
- Tốc độ xử lý ổn định sau phục hồi: μ event/giây.
- Backlog tại thời điểm phục hồi: B event.

Nếu μ > λ, thời gian drain backlog xấp xỉ:

\[
T_{drain} \approx \frac{B}{\mu - \lambda}
\]

Ví dụ backlog 120.000 event, hệ thống tiếp tục nhận 200 event/s và sau phục hồi xử lý được 1.000 event/s:

\[
T_{drain} \approx \frac{120.000}{1.000 - 200} = 150\text{ giây}
\]

Đây là ước lượng lý tưởng; thực tế cần tính partition skew, retry, batch size, rate limit, processing time variance và capacity downstream. Nếu μ ≤ λ, backlog không thể giảm trong điều kiện hiện tại; cần tăng capacity, giảm ingress hoặc áp dụng backpressure.

Đặt recovery SLO theo tier và kích thước backlog cụ thể, ví dụ “sau outage tối đa 10 phút, oldest unprocessed age trở lại dưới 60 giây với backlog không quá 100.000 event và ingress không vượt 500 event/s”. Không ghi recovery objective thiếu điều kiện tải.

## 16. Ownership và review SLO

Mỗi SLO cần một owner chịu trách nhiệm:

- Product/business owner xác nhận deadline và tác động người dùng.
- Service owner định nghĩa SLI, instrumentation và runbook.
- Platform/Kafka owner cung cấp metric broker, replication, capacity và reliability.
- Data owner xác nhận completeness, schema và correctness.
- On-call owner phản ứng khi burn rate/alert vượt ngưỡng.

Review SLO theo chu kỳ và sau thay đổi lớn:

1. Kiểm tra SLI có phản ánh trải nghiệm thật không.
2. Xem baseline, error budget và sự cố trong kỳ.
3. Đánh giá false positive/false negative của instrumentation.
4. Kiểm tra workload, retention, partition count và downstream capacity thay đổi.
5. Điều chỉnh target hoặc architecture dựa trên dữ liệu, không chỉ dựa vào mong muốn.

SLO cần ổn định đủ lâu để so sánh xu hướng; không thay đổi ngưỡng giữa sự cố chỉ để biến trạng thái đỏ thành xanh. Nếu business contract thay đổi, ghi version và ngày hiệu lực của SLO mới.

## 17. Những hiểu nhầm thường gặp

- **“Broker khỏe nghĩa là event pipeline khỏe.”** Consumer, connector, database đích hoặc logic nghiệp vụ vẫn có thể lỗi.
- **“Producer nhận ACK nghĩa là nghiệp vụ hoàn tất.”** ACK chỉ xác nhận điều kiện publish theo cấu hình; downstream có thể chưa xử lý.
- **“Consumer lag thấp nghĩa là event mới.”** Lag theo offset không phản ánh tuổi record hoặc end-to-end freshness.
- **“Average latency đủ để làm SLO.”** Tail latency và tỷ lệ vượt deadline có thể bị che khuất.
- **“99,9% availability là SLA.”** SLO nội bộ và SLA hợp đồng có mục đích, phạm vi và hệ quả khác nhau.
- **“Tăng consumer luôn giảm lag.”** Downstream bottleneck, partition skew hoặc rebalance có thể làm throughput không tăng.
- **“DLQ là event đã xử lý xong.”** DLQ là trạng thái cần theo dõi và có quy trình replay/quarantine.
- **“Một SLO áp dụng cho mọi topic.”** Critical payment và analytics batch có mức độ quan trọng khác nhau.
- **“CPU/disk là SLI nghiệp vụ.”** Đây thường là diagnostic metrics; cần liên hệ chúng với success, freshness hoặc completeness.
- **“Không có alert nghĩa là không có lỗi.”** Thiếu instrumentation hoặc event bị mất trước khi metric ghi nhận có thể tạo khoảng trống quan sát.

## 18. Checklist thiết kế SLI/SLO production

- [ ] Vẽ hành trình nghiệp vụ từ producer đến điểm kết quả người dùng/đối tác quan sát được.
- [ ] Xác định event ID, correlation ID, aggregate key/version và timestamp semantics.
- [ ] Phân loại topic/flow theo tier và tác động nghiệp vụ.
- [ ] Định nghĩa SLI với tử số, mẫu số, điều kiện hợp lệ và trạng thái terminal.
- [ ] Đo cả publish ACK và end-to-end business completion.
- [ ] Có freshness/latency threshold và histogram cho tail latency.
- [ ] Kết hợp consumer lag với oldest record age và processing latency theo partition.
- [ ] Có completeness/reconciliation cho event quan trọng.
- [ ] Đặt durability policy qua acks, replication factor, min.insync.replicas và theo dõi ISR.
- [ ] Định nghĩa SLO window, target, exclusions và error budget.
- [ ] Có burn-rate alert với cửa sổ ngắn/dài và owner/runbook.
- [ ] Instrumentation có cardinality giới hạn; không dùng ID duy nhất làm metric label.
- [ ] Dashboard nối business SLI với producer, broker, consumer, Streams/Connect và downstream metrics.
- [ ] Có backlog recovery objective kèm điều kiện tải và kích thước backlog.
- [ ] Đã kiểm thử mất broker, consumer, downstream outage, retry storm, poison record và partition skew.
- [ ] Có owner và lịch review SLO; thay đổi target phải có version/effective date.

Thiết kế SLI/SLO cho Kafka cần đo kết quả của luồng nghiệp vụ, không dừng ở sức khỏe broker. Kết hợp publish availability, end-to-end freshness, processing success, completeness, correctness và backlog recovery; dùng consumer lag, ISR, request latency và task state để giải thích nguyên nhân. Khi mọi chỉ số có định nghĩa, nguồn dữ liệu, owner và runbook rõ ràng, SLO trở thành công cụ quyết định ưu tiên reliability thay vì chỉ là con số trên dashboard.
