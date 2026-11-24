# Triển khai thử, theo dõi chỉ số và lập phương án quay lại phiên bản trước

Nâng cấp một ứng dụng Spring Cloud Stream cần được triển khai theo từng bước có thể quan sát và đảo ngược. Một phiên bản mới có thể khởi động thành công nhưng vẫn xử lý sai message, tăng consumer lag, phát sinh duplicate, làm hỏng state store hoặc tạo dữ liệu mà phiên bản cũ không đọc được. Vì vậy, rollout phải có baseline, giai đoạn thử nghiệm, điều kiện tiếp tục/dừng, người chịu trách nhiệm và phương án rollback đã kiểm tra trước.

Bài học này tập trung vào ba việc: triển khai thử một phần workload, theo dõi chỉ số kỹ thuật và nghiệp vụ trong khi mở rộng, rồi quay lại phiên bản ổn định khi có tín hiệu xấu. Với Kafka, RabbitMQ và Pulsar, chiến lược canary cần tính đến consumer group, subscription, partition, queue, offset, acknowledgment và stateful processing. Chia traffic HTTP theo phần trăm không đồng nghĩa có thể chia message stream theo cùng cách.

## 1. Rollout an toàn bắt đầu từ baseline

Baseline là trạng thái đo được của phiên bản đang chạy ổn định trước khi nâng cấp. Không có baseline thì khó biết latency, throughput, error rate hoặc backlog sau rollout đã xấu đi hay chỉ dao động bình thường.

Trước khi triển khai, ghi nhận:

- Phiên bản ứng dụng, Spring Boot, Spring Cloud Stream, binder và client broker.
- Image digest hoặc artifact checksum, commit SHA và cấu hình runtime.
- Số instance, consumer concurrency, partition/queue/subscription và consumer group.
- Throughput message/s và byte/s theo từng binding.
- Processing latency p50, p95, p99 và end-to-end business latency.
- Consumer lag hoặc backlog, tuổi message lâu nhất và tốc độ backlog tăng/giảm.
- Error, retry, redelivery, DLQ và acknowledgment/commit failure.
- CPU, heap, allocation, GC pause, thread pool và connection pool.
- Broker health, replication, disk, network và request latency.
- Chỉ số nghiệp vụ như tỷ lệ đơn hàng được chấp nhận, thanh toán thành công hoặc sự kiện bị từ chối.

Baseline nên lấy trong một khoảng thời gian có cả tải bình thường và peak gần nhất. Ghi rõ cửa sổ đo, timezone, nguồn metrics và các sự kiện đặc biệt như batch job, traffic campaign hoặc broker maintenance.

### 1.1. Bảng baseline mẫu

Các số dưới đây chỉ minh họa cách ghi nhận, không phải ngưỡng chuẩn cho mọi hệ thống.

| Chỉ số | Baseline ví dụ | Cửa sổ | Ghi chú |
|---|---:|---|---|
| Throughput đầu vào | 2.000 msg/s | 30 phút | Tổng trên ba partition |
| Processing p95 | 85 ms | 30 phút | Từ lúc handler bắt đầu đến khi hoàn tất |
| Processing p99 | 210 ms | 30 phút | Loại trừ thời gian chờ ở upstream |
| Kafka consumer lag | 1.200 records | 5 phút | Không tăng liên tục |
| Tuổi message lâu nhất | 4 giây | 5 phút | Đo theo event timestamp đã chuẩn hóa |
| Handler error rate | 0,08% | 30 phút | Tính theo số lần xử lý |
| DLQ rate | 0,002% | 1 giờ | Có phân loại lỗi |
| CPU trung bình | 48% | 30 phút | Theo container limit |
| Heap sau GC | 55% | 30 phút | Không tăng dần |
| Tỷ lệ nghiệp vụ thành công | 99,7% | 1 giờ | Theo định nghĩa business event |

Không so sánh hai số liệu nếu định nghĩa khác nhau. Ví dụ handler duration không giống end-to-end latency; Kafka lag theo record count không tương đương tuổi message; số publish confirm không chứng minh downstream đã xử lý.

## 2. Chọn chiến lược triển khai

Các chiến lược thường gặp có mức độ kiểm soát và độ phức tạp khác nhau.

| Chiến lược | Cách hoạt động | Khi phù hợp | Rủi ro cần quản lý |
|---|---|---|---|
| Rolling update | Thay instance cũ dần bằng instance mới | Thay đổi tương thích ngược, workload stateless hoặc consumer group đã kiểm thử | Hai phiên bản cùng chạy; rebalance; thay đổi schema/state |
| Canary | Chạy phiên bản mới trên một phần traffic hoặc một phần workload | Cần xác minh hành vi thực tế trước khi mở rộng | Phải xác định chính xác traffic/message nào đi tới canary |
| Blue-green | Dựng môi trường mới song song rồi chuyển traffic | Cần chuyển đổi nhanh và có khả năng quay lại môi trường cũ | Hai môi trường có thể cùng tiêu thụ message hoặc cùng ghi side effect |
| Shadow | Gửi bản sao event tới phiên bản mới nhưng không cho ghi side effect chính | Kiểm tra deserialize, logic và hiệu năng | Tăng tải; dữ liệu nhạy cảm; phải ngăn publish hoặc mutation thật |

Rolling update đơn giản nhưng không tự tạo ra canary theo tỷ lệ message. Blue-green cũng không tự an toàn nếu cả hai môi trường cùng đọc một stream và cùng cập nhật database. Cần mô tả rõ ownership của message và side effect trước khi chọn cách rollout.

## 3. Rolling update với Kubernetes

Kubernetes Deployment có thể thay Pod theo rolling strategy:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-consumer
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: order-consumer
  template:
    metadata:
      labels:
        app: order-consumer
        release: v2
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: app
          image: registry.example.com/order-consumer:2.4.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: production
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
~~~

Manifest chỉ minh họa rolling strategy và readiness. Readiness endpoint phải được bật và cấu hình phù hợp trong ứng dụng. Với message consumer, readiness không tự dừng việc nhận message từ broker; hãy kết hợp quy trình graceful shutdown và lifecycle của binder.

Ý nghĩa của hai tham số:

- maxSurge: số Pod có thể chạy vượt số replica mong muốn trong lúc cập nhật.
- maxUnavailable: số Pod có thể không sẵn sàng trong lúc cập nhật.

maxUnavailable bằng 0 giữ đủ số Pod sẵn sàng theo điều kiện Deployment, nhưng không đảm bảo đủ consumer capacity nếu broker phân phối partition hoặc queue không cân bằng. maxSurge lớn có thể tạm thời tăng số consumer, làm thay đổi partition assignment hoặc tăng tải downstream.

Trước rollout, xác nhận cluster có đủ CPU, memory, broker connection và database connection cho số Pod tối đa trong giai đoạn surge. Đặt termination grace period theo thời gian drain đã đo, không dùng một giá trị tùy ý.

## 4. Canary cho HTTP và canary cho message consumer khác nhau

Với HTTP service, ingress hoặc service mesh có thể chia request theo trọng số, ví dụ 5% request tới phiên bản mới. Với broker consumer, message được phân phối theo semantics của broker:

- Kafka: consumer cùng group chia partition; một partition tại một thời điểm chỉ được assign cho một consumer trong group.
- RabbitMQ: nhiều consumer trên cùng queue nhận delivery theo prefetch, consumer capacity và trạng thái channel.
- Pulsar: consumer cùng subscription nhận message theo subscription type và dispatch policy.

Không thể giả định thêm một Pod mới sẽ nhận chính xác 5% message. Kafka phân phối theo partition assignment, không phải cân bằng từng record theo phần trăm. RabbitMQ và Pulsar cũng không đảm bảo tỷ lệ phần trăm chính xác theo số consumer.

### 4.1. Canary cùng consumer group

Khi phiên bản mới tham gia cùng consumer group/subscription và cùng đọc queue:

- Hai phiên bản chia sẻ workload theo cơ chế broker.
- Kafka có thể rebalance partition sang consumer mới.
- RabbitMQ có thể phân phối delivery cho consumer cũ hoặc mới.
- Pulsar dispatch message tới consumer theo subscription type.

Đây là cách có thể kiểm tra phiên bản mới trên message thật mà không chủ động tạo một bản sao của toàn bộ stream. Tuy nhiên, phiên bản mới có thể nhận message thuộc partition hoặc key bất kỳ; không có bảo đảm canary chỉ nhận một tỷ lệ nhỏ ổn định. Cần đảm bảo cả hai phiên bản tương thích schema, output và database trong thời gian cùng chạy.

### 4.2. Canary dùng consumer group/subscription riêng

Consumer group hoặc subscription riêng thường nhận toàn bộ stream độc lập:

- Kafka group mới đọc topic theo offset riêng.
- RabbitMQ cần queue/binding riêng để nhận bản sao message.
- Pulsar subscription độc lập nhận các message theo cursor riêng.

Cách này phù hợp cho shadow processing hoặc kiểm tra logic, nhưng có thể xử lý lại toàn bộ lịch sử tùy offset/cursor và retention. Nếu consumer mới gửi email, trừ tiền, cập nhật database hoặc publish event thật, side effect có thể bị nhân đôi.

Canary độc lập phải dùng một trong các biện pháp:

1. Chỉ chạy read-only hoặc ghi vào database/schema thử nghiệm.
2. Chặn output binding hoặc chuyển output tới destination cách ly.
3. Dùng event mirror có kiểm soát, lọc dữ liệu và giới hạn tốc độ.
4. Dùng idempotency key và side-effect gate được thiết kế rõ.
5. Không dùng offset reset về earliest trên production topic nếu chưa đánh giá tải và tác động.

### 4.3. Chọn canary theo mục tiêu

| Mục tiêu | Cách thử phù hợp |
|---|---|
| Xác minh ứng dụng khởi động và kết nối | Một instance mới với consumer intake chưa bật hoặc binding được kiểm soát |
| Xác minh deserialize/schema | Replay tập event đã ẩn dữ liệu nhạy cảm vào môi trường thử |
| Đo hiệu năng handler | Shadow consumer với output bị cách ly |
| Kiểm tra production traffic thực | Tham gia cùng group sau khi xác minh compatibility; theo dõi phân phối thực tế |
| Kiểm tra thay đổi stateful Kafka Streams | Kế hoạch migration state store riêng, có snapshot/restore và rollback được thử |

Không gọi một consumer group mới là canary 5% nếu nó đang đọc toàn bộ topic. Ghi rõ cách chọn message, cách cô lập side effect và cách dừng canary.

## 5. Các giai đoạn rollout có kiểm soát

Một rollout có thể chia thành các bước:

1. **Preflight:** xác minh artifact, config, secret, schema compatibility, capacity và rollback package.
2. **Deploy thử:** chạy smoke test, health check và kết nối broker trên một instance hoặc môi trường staging.
3. **Canary:** mở một phần workload/traffic theo cơ chế đã xác định; giữ output an toàn.
4. **Observe:** so sánh metrics với baseline và chờ đủ cửa sổ quan sát.
5. **Expand:** tăng dần số instance hoặc trọng số khi tất cả gate đều đạt.
6. **Complete:** triển khai toàn bộ, xác minh consumer group/queue/subscription ổn định và đóng release.

~~~mermaid
flowchart TD
    A["Preflight: artifact, config, schema, rollback"] --> B["Deploy thử / smoke test"]
    B --> C{"Health và contract đạt?"}
    C -- Không --> R["Dừng rollout / rollback"]
    C -- Có --> D["Canary workload"]
    D --> E["Theo dõi metrics và business SLI"]
    E --> F{"Vượt mọi rollout gate?"}
    F -- Không --> R
    F -- Có --> G["Mở rộng 25% / 50% / 100%"]
    G --> H["Xác minh toàn hệ thống"]
    H --> I["Hoàn tất release"]
    R --> J["Điều tra và phục hồi"]
~~~

Tỷ lệ 25%, 50% và 100% chỉ là ví dụ. Với Kafka, tỷ lệ consumer instance không ánh xạ tuyến tính thành tỷ lệ record. Với RabbitMQ và Pulsar, dispatch cũng chịu ảnh hưởng của queue backlog, prefetch, subscription type và consumer capacity.

## 6. Định nghĩa rollout gate trước khi deploy

Rollout gate là điều kiện định lượng để quyết định tiếp tục, tạm dừng hoặc rollback. Gate phải được xác định trước khi xem kết quả để tránh thay ngưỡng nhằm hợp thức hóa một rollout xấu.

Một gate nên có:

- Metric và định nghĩa chính xác.
- Nguồn dữ liệu và binding/service được quan sát.
- Baseline hoặc SLO so sánh.
- Cửa sổ đánh giá và số mẫu tối thiểu.
- Ngưỡng cảnh báo và ngưỡng rollback.
- Người có quyền quyết định.
- Hành động nếu metric không có dữ liệu.

### 6.1. Ví dụ rollout gate

Các ngưỡng dưới đây chỉ là ví dụ để minh họa. Hệ thống thực tế phải chọn ngưỡng theo SLO, traffic và baseline.

| Gate | Tiếp tục khi | Dừng/rollback khi |
|---|---|---|
| Instance health | Pod Ready, không restart bất thường | CrashLoop, startup failure hoặc readiness liên tục fail |
| Handler error rate | Không tăng đáng kể so với baseline | Vượt ngưỡng tuyệt đối hoặc tăng mạnh qua nhiều cửa sổ |
| Processing p99 | Nằm trong ngân sách latency | Vượt SLO liên tục và ảnh hưởng backlog |
| Consumer lag/oldest age | Ổn định hoặc giảm ở tải tương đương | Tăng liên tục, tuổi message vượt SLO |
| Retry/DLQ | Không có spike mới | Tăng bất thường hoặc xuất hiện lỗi schema/contract |
| Business success rate | Không giảm so với baseline | Tỷ lệ nghiệp vụ thành công giảm rõ rệt |
| Resource | CPU/heap/GC còn headroom | CPU throttling, OOM hoặc GC pause vượt ngân sách |
| Broker health | Không có lỗi connection/replication mới | Broker request error, queue alarm hoặc replication degradation |

Không rollback chỉ vì một mẫu latency đơn lẻ. Dùng cửa sổ đủ lớn, nhưng không chờ lâu khi có tín hiệu mất dữ liệu, duplicate side effect hoặc lỗi bảo mật. Một số điều kiện như schema incompatibility, message corruption hoặc publish sai destination cần dừng ngay.

## 7. Metrics cần theo dõi trong Spring Cloud Stream

Theo dõi theo binding, function, destination, consumer group và phiên bản release. Metrics tổng toàn ứng dụng có thể che một binding bị nghẽn trong khi các binding khác vẫn tốt.

### 7.1. Metrics ở tầng ứng dụng

- Số message nhận, xử lý thành công và xử lý thất bại.
- Processing duration p50/p95/p99.
- Số handler đang chạy và queue nội bộ.
- Retry count, retry exhaustion và DLQ count.
- Deserialization/schema validation failure.
- Số output message publish và publish failure.
- Business success/failure theo event type.
- Idempotency duplicate hit.
- Thread pool active/queued/rejected.
- Database connection wait, query latency và transaction rollback.

### 7.2. Metrics ở tầng binder và broker

| Hệ thống | Chỉ số nên theo dõi | Câu hỏi cần trả lời |
|---|---|---|
| Kafka | Consumer lag, records consumed, rebalance, commit failure, request latency, under-replicated partitions | Consumer có theo kịp partition và commit được offset không? |
| RabbitMQ | Ready/unacked messages, consumer count, publish/ack rate, redelivery, connection/channel, memory/disk alarm | Queue có tích tụ, consumer có bị block hoặc giao lại nhiều không? |
| Pulsar | Backlog, subscription/consumer count, dispatch rate, redelivery, acknowledgment, BookKeeper storage health | Subscription có xử lý kịp và storage có khỏe không? |

Chỉ số broker không thay thế metrics nghiệp vụ. Kafka lag thấp vẫn có thể xử lý sai business event; RabbitMQ queue rỗng có thể do consumer ack sớm; Pulsar backlog giảm không chứng minh message đã tạo đúng kết quả.

### 7.3. Business metrics

Chọn chỉ số phản ánh kết quả người dùng hoặc nghiệp vụ:

- Tỷ lệ đơn hàng được chấp nhận trên tổng đơn hợp lệ.
- Tỷ lệ thanh toán thành công và tỷ lệ giao dịch bị từ chối.
- Số sự kiện bị loại vì schema/business validation.
- Thời gian từ event phát sinh đến khi nghiệp vụ hoàn tất.
- Số đơn bị xử lý lặp hoặc bị bỏ qua do idempotency.
- Số bản ghi lệch giữa hệ thống nguồn và hệ thống đích.

Đặt label có kiểm soát như service, binding, event type và release version. Không dùng event ID, order ID, customer ID hoặc giá trị có cardinality rất cao làm metric label.

## 8. So sánh canary với baseline

So sánh phiên bản mới và cũ trong cùng cửa sổ tải, cùng loại event và cùng điều kiện hạ tầng. Nếu traffic thay đổi mạnh, cần chuẩn hóa theo message count hoặc byte count.

Ví dụ:

| Metric | Phiên bản cũ | Canary | Chênh lệch | Đánh giá |
|---|---:|---:|---:|---|
| Processing p95 | 85 ms | 91 ms | +7,1% | Theo dõi |
| Processing p99 | 210 ms | 285 ms | +35,7% | Vượt ngưỡng ví dụ |
| Handler error | 0,08% | 0,35% | +0,27 điểm % | Điều tra |
| CPU | 48% | 63% | +15 điểm % | Còn headroom? |
| Consumer lag | 1.200 | 4.800 | +3.600 | Kiểm tra tốc độ drain |
| Business success | 99,7% | 99,1% | -0,6 điểm % | Không đạt |

Các số liệu minh họa cho thấy canary có thể xử lý thành công phần lớn message nhưng p99 và business success đã xấu đi. Quyết định phải dựa trên gate đã định trước, không dựa vào một metric đơn lẻ.

## 9. Dashboard và cảnh báo

Dashboard rollout nên hiển thị:

1. Phiên bản, image digest, số Pod cũ/mới và thời điểm bắt đầu rollout.
2. Throughput theo binding và release version.
3. Processing latency p50/p95/p99.
4. Consumer lag hoặc backlog cùng oldest message age.
5. Error, retry, redelivery, DLQ và schema failure.
6. Business success/failure.
7. CPU, memory, GC, thread pool và connection pool.
8. Broker health, replication, disk và network.
9. Rollout gate hiện tại và quyết định tiếp tục/dừng.

Ví dụ PromQL khái niệm:

~~~promql
sum(rate(stream_handler_errors_total[5m]))
/
clamp_min(sum(rate(stream_handler_invocations_total[5m])), 1)
~~~

~~~promql
histogram_quantile(
  0.99,
  sum by (le, binding) (
    rate(stream_handler_duration_seconds_bucket[5m])
  )
)
~~~

Tên metric ở ví dụ là metric tùy ứng dụng tự instrument; Spring Cloud Stream không mặc định cung cấp đúng các tên này trong mọi phiên bản. Khi triển khai, thay bằng metric thực tế của Micrometer/binder và xác minh unit, label, counter reset và scrape interval.

Alert nên ưu tiên triệu chứng có ý nghĩa:

- Consumer lag hoặc oldest message age tăng liên tục.
- Processing p99 vượt SLO.
- Error/retry/DLQ tăng đột biến.
- Business success giảm.
- Broker connection/commit/ack failure.
- Pod restart, OOM hoặc CPU throttling.

Không tạo alert chỉ từ một counter tăng theo thời gian. Dùng rate, ratio, window và ngưỡng phù hợp để tránh cảnh báo giả.

## 10. Theo dõi Kafka trong rollout

Với Kafka, quan sát ít nhất:

- Lag theo topic, partition và consumer group.
- Offset commit rate và commit failure.
- Rebalance count/reason và thời gian partition không có consumer.
- Records lagging và tuổi record lâu nhất.
- Producer send error, retry và request latency.
- Under-replicated partition, offline partition và ISR shrink.
- Kafka Streams task/state restore nếu ứng dụng stateful.

Canary cùng group sẽ làm thay đổi partition assignment. Khi Pod mới tham gia hoặc Pod cũ rời group, rebalance có thể gây một khoảng ngừng xử lý. Theo dõi rebalance và lag trong rollout để phân biệt chi phí chuyển giao với lỗi ứng dụng.

Không chỉ nhìn tổng lag. Một partition bị nghẽn có thể bị che bởi các partition khác đang rỗng. Nếu key skew, một số partition nhận phần lớn traffic; cần xem lag theo partition và phân phối key.

## 11. Theo dõi RabbitMQ trong rollout

Với RabbitMQ, quan sát:

- Ready messages và unacknowledged messages.
- Consumer count và consumer capacity.
- Publish, deliver, ack, nack và redelivery rate.
- Queue length và oldest message age nếu có instrumentation.
- Connection/channel churn.
- Publisher confirm latency và unroutable message.
- Memory/disk alarm, flow control và node health.

Khi thêm consumer mới vào queue, message có thể được phân phối cho consumer cũ hoặc mới tùy prefetch và tải. Consumer count tăng không bảo đảm throughput tăng tương ứng nếu downstream database là bottleneck.

Khi rollback consumer, các delivery chưa ack có thể được requeue. Kiểm tra redelivery rate và idempotency. Không purge queue để làm dashboard về 0 trong quá trình xử lý sự cố.

## 12. Theo dõi Pulsar trong rollout

Với Pulsar, theo dõi:

- Backlog theo topic và subscription.
- Dispatch rate, ack rate và redelivery.
- Consumer count, subscription type và ownership.
- Unacked messages và acknowledgment timeout.
- Producer send latency/failure.
- Broker/BookKeeper health, storage latency và ledger errors.
- Partitioned topic distribution và backlog từng partition.

Khi canary dùng subscription riêng, nó có thể nhận toàn bộ message độc lập. Cần xác định subscription bắt đầu từ earliest hay latest, retention và backlog trước khi mở consumer. Một subscription mới có thể đọc lượng lớn lịch sử, làm tăng tải broker và storage.

## 13. Schema và contract trong giai đoạn hai phiên bản cùng chạy

Rolling/canary thường tạo thời gian phiên bản cũ và mới cùng tồn tại. Producer, consumer và schema phải tương thích trong toàn bộ cửa sổ này.

Các câu hỏi cần trả lời:

- Consumer cũ có đọc được message do producer mới phát không?
- Consumer mới có đọc được message cũ còn nằm trong queue/topic/backlog không?
- Field mới có default hoặc optional phù hợp không?
- Có đổi enum, number type, timestamp format hoặc meaning của field không?
- Retry topic và DLQ có giữ nguyên schema cũ không?
- Có thay đổi content type, serializer hoặc schema registry subject không?

Chiến lược expand-contract thường an toàn hơn:

1. Mở rộng schema để cả phiên bản cũ và mới đọc được.
2. Triển khai consumer mới nhưng vẫn hỗ trợ field cũ.
3. Chuyển producer sang phát field mới sau khi consumer đã tương thích.
4. Chờ hết retention/retry window của message cũ.
5. Chỉ sau đó mới xóa field hoặc contract cũ.

Không xóa field hoặc đổi type trong cùng release mà consumer cũ vẫn đang chạy. Kiểm tra schema compatibility bằng công cụ registry hoặc contract test trước rollout.

## 14. Database migration và khả năng rollback

Rollback ứng dụng không tự rollback database schema. Nếu release mới thêm cột, index hoặc bảng, phiên bản cũ phải tiếp tục chạy được trong thời gian rollback.

Áp dụng expand-contract:

- Expand: thêm cột nullable, bảng mới hoặc index tương thích.
- Deploy: phát hành code có thể đọc cả dạng cũ và mới.
- Migrate data: backfill có kiểm soát, theo dõi lock và load.
- Switch: chuyển ghi/đọc sang cấu trúc mới.
- Contract: xóa cấu trúc cũ trong release riêng sau khi hết rollback window.

Không chạy migration phá hủy dữ liệu ngay trước khi rollout canary nếu chưa có backup và restore test. Migration nên có owner, thời gian dự kiến, lock impact và lệnh kiểm tra sau khi chạy.

Rollback code có thể cần giữ schema mới. Không tự chạy down migration khi quay lại binary cũ; down migration có thể xóa dữ liệu mà phiên bản cũ không thể khôi phục.

## 15. State store và Kafka Streams

Nếu ứng dụng dùng Kafka Streams qua Spring Cloud Stream, rollout có thể ảnh hưởng state store, changelog topic, repartition topic, task assignment và restore time.

Trước khi nâng cấp:

- Xác định application.id và state store/changelog liên quan.
- Xác minh schema của state store và serialized key/value.
- Kiểm tra changelog retention và khả năng restore.
- Kiểm tra topology change có tạo repartition topic mới hay không.
- Đo thời gian task migration và state restoration.
- Xác định phiên bản mới có thể đọc state được ghi bởi phiên bản cũ và ngược lại hay không.

Không đổi application.id để "canary" một cách tùy tiện. Một application.id khác tạo nhóm xử lý/state độc lập và có thể đọc lại toàn bộ input theo offset riêng, gây duplicate side effect hoặc tăng tải. Nếu cần chạy song song, phải cách ly output và state.

Nếu state format không tương thích ngược, rollback binary cũ có thể không đọc được state mới. Cần một trong các phương án đã thử:

1. Giữ state serialization tương thích qua nhiều release.
2. Dùng state store mới có migration/backfill được kiểm soát.
3. Snapshot/backup state và thử restore với phiên bản cũ.
4. Dùng application.id/state namespace riêng khi chấp nhận replay có kiểm soát và đã cô lập side effect.

Rollback stateful application phải được diễn tập; chỉ đổi image tag không đủ.

## 16. Xác định điều kiện rollback

Rollback khi lợi ích của việc giữ phiên bản mới thấp hơn rủi ro tiếp tục chạy. Điều kiện cần phân biệt lỗi có thể tự phục hồi và lỗi gây tác động dữ liệu.

### 16.1. Rollback ngay

- Message bị mất do ack/commit sai.
- Phát duplicate side effect nghiêm trọng như trừ tiền hoặc tạo lệnh lặp.
- Schema mới làm consumer hiện tại không deserialize được.
- Publish sai destination hoặc routing key gây phát tán dữ liệu.
- Data corruption hoặc state store không thể phục hồi.
- Lỗi bảo mật hoặc lộ dữ liệu.

### 16.2. Tạm dừng rollout và điều tra

- p95/p99 tăng nhưng chưa vượt ngưỡng rollback.
- Consumer lag tăng ngắn hạn trong lúc rebalance.
- CPU tăng nhưng còn headroom.
- Một vài lỗi downstream có thể retry thành công.
- Canary chưa có đủ số mẫu để kết luận.

Nếu thiếu metrics hoặc dashboard không cập nhật, không mở rộng rollout. Tạm dừng để khôi phục khả năng quan sát.

### 16.3. Không dùng rollback để che lỗi dữ liệu

Nếu phiên bản mới đã ghi dữ liệu không tương thích hoặc tạo side effect, quay lại binary cũ không tự sửa các dữ liệu đó. Cần incident runbook riêng để xác định phạm vi, dừng producer nếu cần, đối soát, sửa dữ liệu hoặc replay có kiểm soát.

## 17. Chuẩn bị rollback trước khi triển khai

Mỗi release cần một rollback package gồm:

- Artifact/image digest của phiên bản hiện tại và phiên bản trước.
- ConfigMap/secret version hoặc cấu hình đã version hóa.
- Danh sách dependency và binder version.
- Database migration và trạng thái migration.
- Schema compatibility report.
- Kafka topic/partition/group, Rabbit vhost/exchange/queue, Pulsar topic/subscription liên quan.
- State store/changelog và hướng restore nếu có.
- Lệnh hoặc quy trình dừng rollout, deploy lại và xác minh.
- Người phê duyệt rollback và kênh liên lạc incident.

Không chỉ ghi "revert deployment". Ghi chính xác artifact nào, config nào, migration nào đã chạy và bước nào có thể đảo ngược.

### 17.1. Rollback runbook mẫu

| Bước | Hành động | Xác minh |
|---|---|---|
| 1 | Dừng mở rộng rollout; giữ lại dashboard và log | Không có Pod mới tiếp tục được tạo |
| 2 | Đánh giá có cần dừng producer hoặc binding gây lỗi | Tốc độ phát message và side effect đã được kiểm soát |
| 3 | Chọn image digest và config của bản ổn định trước | Artifact/config khớp release record |
| 4 | Triển khai lại phiên bản trước theo rolling policy | Pod Ready và consumer kết nối đúng destination |
| 5 | Kiểm tra schema, database và state store tương thích | Không có lỗi deserialize/migration/state restore |
| 6 | Theo dõi lag, queue/backlog, retry, DLQ và business SLI | Metrics trở lại trong ngưỡng |
| 7 | Đối soát message và side effect trong cửa sổ sự cố | Không còn dữ liệu lệch chưa được xử lý |
| 8 | Ghi nhận nguyên nhân, quyết định và thời điểm kết thúc | Incident/release record đầy đủ |

Đây là trình tự tham khảo; trong một số sự cố, cần pause consumer hoặc producer trước khi triển khai rollback để ngăn lỗi tiếp tục lan rộng. Quyết định đó phải dựa trên hướng dẫn vận hành của hệ thống và tác động đến backlog.

## 18. Kafka offsets khi rollback

Kafka offset là tiến độ đọc của consumer group. Khi quay lại phiên bản cũ, giữ nguyên consumer group thường giúp tiếp tục từ offset đã commit. Không reset offset về earliest hoặc latest như một bước rollback mặc định.

Trước khi thao tác offset:

- Ghi lại group ID, topic, partition và committed offset.
- Xác định record nào đã xử lý nhưng chưa commit.
- Xác định phiên bản cũ có thể đọc record mới còn tồn tại hay không.
- Kiểm tra transaction/producer output và side effect đã phát.
- Chỉ replay một khoảng offset đã xác định với quy trình idempotency và đối soát.

Reset offset có thể tạo duplicate hoặc bỏ qua dữ liệu. Nếu cần replay, thử trước trên môi trường cách ly hoặc group mới với output bị chặn; không chạy lệnh reset theo hướng dẫn chung khi chưa biết phạm vi.

## 19. RabbitMQ và Pulsar khi rollback

### RabbitMQ

- Giữ nguyên queue và message chưa được ack.
- Khi consumer cũ dừng, message unacked có thể được requeue.
- Kiểm tra consumer mới/phiên bản rollback có cùng contract, routing và permission.
- Không xóa queue, purge message hoặc đổi binding để "làm sạch" rollout nếu chưa có kế hoạch dữ liệu.
- Kiểm tra DLQ và retry queue vì message có thể đang chờ ở đó.

### Pulsar

- Ghi lại topic, subscription name, subscription type và cursor/backlog.
- Subscription durable thường giữ tiến độ độc lập với consumer process.
- Không xóa subscription hoặc reset cursor như một bước rollback mặc định.
- Xác minh phiên bản cũ đọc được message còn backlog và message đã phát trong giai đoạn canary.
- Nếu canary dùng subscription riêng, dừng subscription đó theo kế hoạch và đánh giá backlog/retention trước cleanup.

Ở cả hai hệ thống, message chưa ack có thể được giao lại. Handler phải idempotent và các output side effect cần được đối soát.

## 20. Blue-green và chuyển đổi traffic

Blue-green giữ hai môi trường:

- Blue: phiên bản hiện tại đang phục vụ.
- Green: phiên bản mới đã triển khai và qua kiểm tra.

Với HTTP, có thể chuyển Service/Ingress sang Green rồi quay lại Blue. Với message consumer, cần quyết định môi trường nào sở hữu subscription/consumer group và ai được phép ghi side effect.

Một cách an toàn hơn cho consumer là:

1. Triển khai Green nhưng chưa nhận message production hoặc chỉ chạy shadow.
2. Xác minh health, schema, state restore và dependency.
3. Dừng intake ở Blue theo quy trình drain.
4. Chuyển ownership/consumer group hoặc subscription sang Green.
5. Theo dõi backlog, redelivery và business SLI.
6. Giữ Blue sẵn sàng để rollback nhưng không cho cả hai môi trường cùng tạo side effect.

Nếu cả Blue và Green cùng consume với group/subscription riêng, cả hai có thể nhận cùng một message. Điều này chỉ phù hợp khi shadow output được cách ly hoặc nghiệp vụ được thiết kế chống lặp.

## 21. Feature flag và tắt nhanh chức năng mới

Feature flag có thể tách việc deploy code khỏi thời điểm bật hành vi mới. Khi phát hiện lỗi logic nhưng phiên bản mới vẫn ổn định về runtime, tắt flag có thể giảm tác động nhanh hơn rollback toàn bộ artifact.

Feature flag cần:

- Có giá trị mặc định an toàn.
- Được đọc từ nguồn cấu hình đáng tin cậy.
- Có audit ai bật/tắt và lúc nào.
- Có metric để biết nhánh code nào đang chạy.
- Có kế hoạch xóa flag sau khi hoàn tất migration.

Flag không giải quyết lỗi binary incompatibility, memory leak, dependency conflict, schema serialization hoặc state store. Nếu lỗi nằm ở runtime/framework, cần rollback artifact.

## 22. Kiểm thử phương án rollback

Rollback chỉ đáng tin khi đã được diễn tập. Kiểm thử trong staging với dữ liệu và topology gần production:

1. Deploy bản cũ, phát message đại diện và ghi baseline.
2. Deploy canary mới, tạo tải bình thường và peak.
3. Cố ý kích hoạt một gate lỗi như tăng latency hoặc schema validation failure.
4. Dừng rollout và triển khai lại artifact cũ.
5. Xác minh consumer group/subscription tiếp tục từ tiến độ đúng.
6. Kiểm tra message chưa ack, retry và DLQ.
7. Đối soát database, output topic/queue và business result.
8. Với Kafka Streams, kiểm tra state restore hoặc migration rollback.
9. Đo thời gian từ quyết định rollback tới khi metrics ổn định.
10. Ghi lại bước thủ công, quyền truy cập hoặc dependency còn thiếu.

Một cuộc diễn tập không cần tạo lỗi dữ liệu nguy hiểm. Dùng event test, sink cách ly và database thử nghiệm để xác minh đường đi.

### 22.1. Ma trận test theo binder

| Tình huống | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Consumer mới tham gia | Rebalance và partition assignment | Consumer count và dispatch | Subscription dispatch/ownership |
| Consumer bị dừng | Offset commit và record chưa commit | Unacked delivery/requeue | Ack state/redelivery |
| Rollback binary | Cùng group/offset, schema compatibility | Cùng queue/routing/permission | Cùng subscription/cursor |
| Replay | Offset có kiểm soát | Republish/requeue theo quy trình | Cursor/replay theo subscription |
| Stateful processing | Changelog/state store restore | Trạng thái ứng dụng bên ngoài broker | State bên ngoài hoặc application store |

## 23. Checklist trước khi mở rộng canary

- [ ] Artifact, image digest và config đã được ghi nhận.
- [ ] Baseline kỹ thuật và nghiệp vụ có cửa sổ đo rõ ràng.
- [ ] Đã chọn chiến lược rolling/canary/blue-green/shadow phù hợp.
- [ ] Đã xác định consumer group/subscription và message distribution thực tế.
- [ ] Side effect của shadow/canary riêng đã được cách ly.
- [ ] Schema và message contract tương thích với phiên bản cũ.
- [ ] Database migration theo expand-contract và rollback window còn hiệu lực.
- [ ] Kafka Streams state/changelog có phương án restore nếu sử dụng.
- [ ] Dashboard hiển thị metrics theo binding và release version.
- [ ] Rollout gate, cửa sổ đánh giá và người quyết định đã thống nhất.
- [ ] Alert cho lag/backlog, latency, error, retry, DLQ và business SLI đã hoạt động.
- [ ] Có rollback artifact/config và runbook đã thử.
- [ ] Không reset offset/cursor hoặc purge queue như bước rollback mặc định.
- [ ] Có phương án đối soát message và side effect sau rollback.
- [ ] Có người theo dõi rollout và ghi lại quyết định.

## 24. Checklist khi quyết định rollback

- [ ] Dừng mở rộng rollout và ghi lại thời điểm quyết định.
- [ ] Xác định lỗi thuộc code, config, schema, state, broker hay dependency.
- [ ] Kiểm soát producer/consumer nếu lỗi còn tiếp tục phát sinh dữ liệu.
- [ ] Chọn đúng image digest và config phiên bản ổn định.
- [ ] Kiểm tra database migration và state compatibility trước khi khởi động bản cũ.
- [ ] Giữ nguyên offset/cursor/queue trừ khi có kế hoạch replay cụ thể.
- [ ] Triển khai phiên bản cũ và xác minh readiness cùng binder connection.
- [ ] Theo dõi lag, backlog, redelivery, retry, DLQ và business success.
- [ ] Đối soát side effect, duplicate và dữ liệu phát sinh trong cửa sổ lỗi.
- [ ] Chỉ đóng incident khi metrics ổn định và backlog trở về mức chấp nhận được.

## 25. Nguyên tắc vận hành

1. Đo baseline trước rollout và so sánh cùng định nghĩa metric.
2. Tách rollout HTTP khỏi rollout message consumer; broker có semantics phân phối riêng.
3. Không gọi consumer group riêng là canary một phần nếu nó đọc toàn bộ stream.
4. Cách ly side effect khi chạy shadow hoặc replay.
5. Dùng rollout gate đã thống nhất trước khi deploy.
6. Theo dõi cả technical metrics lẫn business SLI.
7. Triển khai schema và database theo hướng tương thích ngược.
8. Có kế hoạch riêng cho Kafka Streams state store/changelog.
9. Chuẩn bị artifact, config và runbook rollback trước khi bắt đầu.
10. Không reset offset, cursor hoặc purge queue theo phản xạ.
11. Diễn tập rollback với broker và dữ liệu thử gần production.
12. Sau rollback, đối soát message và business side effect trước khi kết thúc incident.

## Tài liệu tham khảo chính thức

- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rolling update, maxSurge và maxUnavailable.
- [Kubernetes Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): readiness, termination và lifecycle.
- [Argo Rollouts](https://argo-rollouts.readthedocs.io/): canary, blue-green và analysis gates.
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/): binding, binder và consumer configuration.
- [Apache Kafka Consumer Groups](https://kafka.apache.org/documentation/#intro_consumers): partition assignment, group và offset.
- [Apache Kafka Streams Operations](https://kafka.apache.org/documentation/streams/): state store, changelog và vận hành Kafka Streams.
- [RabbitMQ Consumers](https://www.rabbitmq.com/docs/consumers): consumer dispatch, acknowledgments và prefetch.
- [RabbitMQ Queues](https://www.rabbitmq.com/docs/queues): queue behavior, durability và dead lettering.
- [Apache Pulsar Messaging](https://pulsar.apache.org/docs/next/concepts-messaging/): subscription, cursor, acknowledgment và redelivery.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): instrument metrics và observation trong ứng dụng Spring.
