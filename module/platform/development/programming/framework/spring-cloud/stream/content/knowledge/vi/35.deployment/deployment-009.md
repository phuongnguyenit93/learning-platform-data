# Phục hồi khi mất broker, mất instance hoặc đầy đĩa

## 1. Phục hồi là một phần của thiết kế triển khai

Ứng dụng Spring Cloud Stream xử lý sự kiện thông qua các hàm Supplier, Function và Consumer được nối tới Kafka, RabbitMQ hoặc Pulsar bằng binding và binder. Khi triển khai production, mất kết nối broker, mất một instance đang xử lý message hoặc cạn dung lượng đĩa là các sự cố bình thường cần có kế hoạch từ trước, không phải tình huống chỉ xử lý sau khi xảy ra.

Khả năng phục hồi không chỉ là chạy lại container. Một hệ thống chỉ được coi là đã phục hồi khi:

- Đường kết nối tới broker và các dependency quan trọng hoạt động trở lại.
- Producer gửi và được xác nhận theo mức bảo đảm đã thiết kế.
- Consumer tiếp tục đọc được message từ đúng offset, queue hoặc subscription.
- Những message chưa hoàn thành được xử lý lại hoặc chuyển tới trạng thái lỗi được quản lý.
- Không có dữ liệu bị mất ngoài RPO đã chấp nhận; duplicate được nhận diện và xử lý an toàn.
- Backlog được thu hẹp trong thời gian mục tiêu và chỉ số vận hành trở lại bình thường.

Ba loại sự cố được học trong bài có ranh giới rất khác nhau: **broker outage** tác động đến hạ tầng lưu trữ và phân phối message; **instance outage** tác động đến consumer/producer của ứng dụng; **disk full** có thể xảy ra trên broker, node lưu trữ hoặc chính ứng dụng.

~~~mermaid
flowchart LR
    P[Producer / Supplier] --> B[(Kafka / RabbitMQ / Pulsar)]
    B --> C1[Consumer instance A]
    B --> C2[Consumer instance B]
    C1 --> D[(Database / downstream)]
    C2 --> D
    B -. Broker unavailable .-> F1[Broker recovery]
    C1 -. Pod crash .-> F2[Instance recovery]
    B -. Storage full .-> F3[Disk capacity recovery]
    F1 --> R[Verify offsets, backlog and outcomes]
    F2 --> R
    F3 --> R
~~~

Trong môi trường production, luôn cân nhắc độ bền dữ liệu, tính nhất quán nghiệp vụ và tính sẵn sàng cùng lúc. Không vì muốn hết cảnh báo mà xóa log, hạ durability hoặc tắt xác thực một cách tùy tiện.

## 2. Phân biệt availability, RTO và RPO

Một runbook phục hồi cần có định nghĩa kết quả đo được:

| Khái niệm | Diễn giải | Ví dụ mục tiêu giả định |
|---|---|---|
| Availability | Hệ thống có thể nhận/xử lý request hoặc message theo cam kết | Có ít nhất một đường xử lý hợp lệ |
| RTO (Recovery Time Objective) | Thời gian mục tiêu để khôi phục dịch vụ sau sự cố | Dưới 15 phút |
| RPO (Recovery Point Objective) | Khoảng mất dữ liệu tối đa chấp nhận được, đo theo thời gian | 0 đối với event đã được broker xác nhận, nếu cấu hình durability đáp ứng |
| Recovery backlog | Message tích lũy trong lúc gián đoạn | Không vượt ngưỡng lưu trữ và xử lý |
| Backlog drain time | Thời gian giảm backlog về ngưỡng sau khi hệ thống khỏe | Dưới 20 phút |
| Delivery guarantee | At-most-once, at-least-once hoặc semantics cụ thể của pipeline | At-least-once với idempotent side effect |

Các số trong bảng là **ví dụ thiết kế**, không phải cam kết mặc định của broker hoặc binder. RPO bằng 0 chỉ có thể tuyên bố sau khi kiểm chứng cấu hình replication, acknowledgement, durability và phạm vi sự cố. Với side effect qua database hoặc dịch vụ khác, một broker bền vững không tự bảo đảm transaction toàn pipeline.

Phải tách thời điểm **broker có thể kết nối lại** khỏi thời điểm **backlog đã được xử lý hết**. Một cảnh báo có thể hết ngay khi network phục hồi nhưng SLA nghiệp vụ vẫn bị vi phạm do message age quá cao.

## 3. Mô hình lỗi: điểm nào có thể hỏng?

Một message thường đi qua các bước:

1. Producer tạo event và gửi tới broker.
2. Broker lưu trữ và xác nhận theo cấu hình durability.
3. Consumer nhận event và bắt đầu xử lý.
4. Handler ghi database hoặc gọi downstream.
5. Handler hoàn tất, producer phát output nếu có.
6. Offset được commit hoặc message được acknowledge.

Lỗi có thể xảy ra giữa bất kỳ hai bước. Vì vậy, cần hỏi **message hiện đang ở trạng thái nào?** trước khi cho chạy lại:

| Vị trí lỗi | Hệ quả có thể có | Bằng chứng cần thu thập |
|---|---|---|
| Trước broker ack | Producer không biết message có được lưu hay không | Producer exception, sequence/event ID, broker log |
| Sau broker ack, trước consumer xử lý | Message còn backlog | Offset/queue/subscription cursor |
| Sau side effect, trước consumer ack | Message có thể được giao lại; side effect trùng | Transaction nghiệp vụ, event ID, ack/commit |
| Khi publish output | Output có thể chưa phát hoặc đã phát nhưng ack bị mất | Output topic/queue, producer ack, correlation ID |
| Trong retry hoặc DLQ | Message có thể tắc ở retry/DLQ | Retry attempts, DLT record, consumer health |

Quy trình phục hồi phải giữ được khả năng đối soát các trạng thái đó. Đừng xóa consumer group, queue, state directory hoặc log segment trước khi biết chúng có chứa dữ liệu cần phục hồi hay không.

## 4. Ba nhóm sự cố và phương án ưu tiên

| Sự cố | Triệu chứng phổ biến | Hành động đầu tiên |
|---|---|---|
| Mất một Kafka broker | Partition leader thay đổi, producer timeout, lag tăng | Xem replication/ISR, tình trạng leader, phạm vi cluster |
| RabbitMQ node mất | AMQP reconnect, quorum leader chuyển, queue có thể không khả dụng | Xem cluster health, quorum majority và queue state |
| Pulsar broker mất | Client reconnect, lookup/producer/consumer lỗi ngắn hạn | Xem broker ownership, BookKeeper và metadata |
| Mất application instance | Pod restart, rebalance, unacked redelivery | Kiểm tra instance còn lại, assignment và handler idempotency |
| Broker hết đĩa | Write lỗi, message publish bị chặn, ledger không tạo được | Xác định node/filesystem, ngừng tăng tải và khôi phục capacity an toàn |
| Application hết đĩa | Log lỗi, Kafka Streams state restore thất bại | Kiểm tra state/log volume và thao tác ghi hiện tại |

Chẩn đoán ban đầu phải xác định có **sự cố một thành phần** hay **mất đa số/quorum**. “Một broker down” trong cluster có replica đầy đủ không tương đương với việc toàn cluster mất khả năng phục vụ.

## 5. Các tín hiệu giám sát cần có trước khi xảy ra sự cố

Không thể phục hồi đáng tin cậy nếu không biết chính xác nơi xử lý dừng lại. Nên thu thập và cảnh báo:

- **Broker:** node availability, partition/queue/ledger health, leader/quorum, write latency, throttling, disk utilization, free bytes và disk I/O latency.
- **Kafka:** offline partitions, under-replicated partitions, ISR shrink, controller/leader changes, producer error và consumer lag theo partition/group.
- **RabbitMQ:** disk/memory alarms, blocked connections, ready/unacked messages, quorum queue member/leader state, publisher confirms và consumer count.
- **Pulsar:** broker connectivity, BookKeeper bookie health, ledger write errors, backlog, subscription dispatch/redelivery và storage free space.
- **Application:** binding state, producer send failures, handler latency, error rate, JVM GC/heap, restart count và readiness.
- **Nghiệp vụ:** eventId được xử lý thành công, duplicate side effect, DLQ, độ tuổi message và thời gian end-to-end.

Phân biệt **lỗi tạm thời được client tự retry** với **sự cố kéo dài cần can thiệp** bằng các ngưỡng thời gian và xu hướng. Số message lỗi tăng vọt trong vài giây có thể đi kèm leader election; backlog tăng liên tục trong nhiều phút có thể cho thấy capacity không đủ.

## 6. Runbook chung: phát hiện, cô lập, phục hồi, xác minh

Runbook theo thứ tự sau giúp giảm nguy cơ chữa sai:

~~~mermaid
flowchart TD
    A[Alert: broker / pod / disk] --> B[Identify scope and last-known-good]
    B --> C[Preserve evidence, check data durability]
    C --> D{Risk of further data loss?}
    D -->|Yes| E[Throttle ingress / pause unsafe writes]
    D -->|No| F[Prepare supported recovery action]
    E --> F
    F --> G[Recover quorum / process / capacity]
    G --> H[Verify producer and consumer continuity]
    H --> I[Reconcile event IDs and drain backlog]
    I --> J[Observe SLO and close incident]
~~~

Thực hiện tuần tự:

1. Ghi nhận thời điểm, alert, broker/instance/volume bị ảnh hưởng và phạm vi topic/queue.
2. Xác định tình trạng replication, quorum, dữ liệu chưa ack và retention/backlog.
3. Nếu còn nguy cơ mất dữ liệu hoặc đầy đĩa lan rộng, giảm ingress hoặc cô lập luồng lỗi; không tự xóa dữ liệu.
4. Chọn thao tác phục hồi **được hỗ trợ** bởi broker, orchestrator và storage platform.
5. Kiểm tra việc kết nối, producer confirmation, consumer assignment và xử lý message.
6. Đo backlog drain, kiểm tra DLQ/retry và đối soát eventId.
7. Chỉ đóng incident khi dữ liệu, hiệu năng và khả năng phục vụ đều đạt tiêu chí.

Không cần restart toàn bộ cluster để chữa một pod bị lỗi nếu chưa có bằng chứng cho thấy các thành phần còn lại cũng có vấn đề.

## 7. Kafka: mất một broker khi dữ liệu có replication

Kafka topic có thể có nhiều replica trên các broker. Với replication factor lớn hơn một, mất broker có thể khiến leader được chọn từ replica còn sống và producer/consumer tự kết nối tới leader mới.

Ví dụ cấu hình độ bền điển hình:

~~~text
replication.factor = 3
min.insync.replicas = 2
producer acks = all
unclean.leader.election.enable = false
~~~

Các giá trị trên mô tả ý đồ: chỉ xác nhận ghi khi đáp ứng ISR tối thiểu; không chọn replica không đồng bộ làm leader chỉ để tăng availability. Đây không phải công thức bảo đảm chống mọi sự cố, đặc biệt nếu các replica nằm chung node/zone hoặc bị lỗi tương quan.

Khi một broker dừng:

- Kiểm tra partition leader và số replica còn ở ISR.
- Kiểm tra producer đang gửi lại khi leader thay đổi hay đang timeout kéo dài.
- Kiểm tra consumer group rebalancing và lag theo partition.
- Đảm bảo broker còn lại không bị disk/network bão hòa do gánh thêm tải.
- Khởi động broker hỏng qua quy trình vận hành và theo dõi replica catch-up trước khi coi cluster phục hồi hoàn toàn.

Không hạ min.insync.replicas hoặc bật unclean leader election chỉ để bỏ lỗi producer mà không chấp nhận rõ ràng nguy cơ mất dữ liệu.

## 8. Kafka: khi mất quá nhiều replica hoặc leader

Nếu ISR không đủ min.insync.replicas, producer với acks=all có thể nhận lỗi như NotEnoughReplicas hoặc NotEnoughReplicasAfterAppend. Điều đó thường phản ánh broker đang từ chối xác nhận một ghi không đạt ngưỡng durability.

Hướng xử lý:

1. Xác định partition bị ảnh hưởng, ISR hiện tại và các broker chứa replica.
2. Kiểm tra broker down do network, disk, JVM crash, TLS hoặc storage failure.
3. Khôi phục replica/broker lành trước khi tăng tải.
4. Nếu vẫn không đủ replica, giữ write degraded hoặc tạm giảm ingress theo runbook.
5. Khi ISR phục hồi, xác minh producer có thể ghi và nhận acknowledgement trở lại.

Trong một số tình huống thảm họa, tổ chức có thể phải cân nhắc thao tác recovery mang nguy cơ mất dữ liệu. Quyết định như vậy cần quy trình phê duyệt, xác định RPO và phương án đối soát; không coi đó là bước troubleshooting mặc định.

## 9. Kafka: producer retry không đồng nghĩa xử lý đúng một lần

Kafka producer có thể gửi lại khi network hoặc leader thay đổi. Producer idempotence, sequence number và cấu hình delivery giúp giảm duplicate khi retry trong phạm vi cơ chế producer hỗ trợ.

Tuy nhiên:

- Producer không nhận ack có thể không biết chắc message trước đó đã được broker lưu.
- Khi application tự gửi lại một **event nghiệp vụ** sau restart, đó có thể là event mới theo quan điểm producer idempotence dù có cùng payload.
- Consumer sau crash có thể xử lý lại message chưa commit offset.
- Side effect ngoài Kafka như ghi database, gọi REST API hoặc gửi email không tự được bảo vệ bởi Kafka transaction.

Vì vậy, gắn eventId ổn định; consumer xử lý lặp an toàn bằng unique constraint, inbox/deduplication hoặc business key phù hợp. Đối với pipeline Kafka-to-Kafka có giao dịch, cấu hình và kiểm thử transaction/offset commit theo chính xác phiên bản binder và topology đang triển khai.

## 10. Kafka consumer: mất instance và rebalancing

Ví dụ có topic 6 partition, group có 3 instance; mỗi instance đang xử lý hai partition. Khi một instance chết, Kafka group coordinator gán lại các partition còn lại cho instance sống.

~~~mermaid
flowchart LR
    T[(orders.events: six partitions)] --> G[Consumer group]
    G --> A[Instance A]
    G --> B[Instance B]
    G --> C[Instance C]
    B -. Crash .-> R[Rebalance]
    R --> A
    R --> C
~~~

Trong lúc chuyển assignment, processing có thể dừng ngắn hạn. Message đã xử lý nhưng chưa commit offset sẽ được đọc lại sau rebalance. Message chưa xử lý vẫn còn trong log Kafka nếu retention chưa loại bỏ.

Để phục hồi an toàn:

- Có nhiều instance cho availability; đừng đặt mọi instance trên cùng một node.
- Thiết kế handler idempotent.
- Commit offset sau khi hoàn tất phần xử lý cần được bảo vệ, theo semantics binder.
- Giới hạn thời gian handler và quản lý poll/session timeouts phù hợp.
- Theo dõi rebalance duration, lag và duplicate side effect.

Tăng consumer replica có thể giúp xử lý backlog nếu partition và downstream còn headroom; thêm replica vượt số partition trong cùng group không tăng parallelism tuyến tính.

## 11. RabbitMQ: broker node mất và vai trò của quorum queue

RabbitMQ có exchange, queue, publisher confirm và consumer acknowledgement. Với một queue thông thường chỉ có một bản sao trên node, node đó mất có thể làm queue không khả dụng; độ bền còn phụ thuộc queue type, storage và cấu hình vận hành.

Quorum queue sử dụng một nhóm replica và cơ chế đồng thuận để duy trì trạng thái. Khi một member mất nhưng đa số vẫn hoạt động, queue có thể tiếp tục phục vụ sau khi leader được bầu/chuyển phù hợp. Khi mất đa số, không thể giả định queue vẫn có thể xử lý ghi bình thường.

Khi node lỗi:

1. Kiểm tra RabbitMQ cluster health và node membership.
2. Xác định queue type, replica membership, quorum majority và leader status.
3. Kiểm tra connections/channels có reconnect không.
4. Kiểm tra publisher confirms, ready/unacked messages và redelivery.
5. Khôi phục node hoặc thay member theo quy trình quorum queue được hỗ trợ.

Không xóa queue hoặc ép tái tạo cluster khi chưa xác định trạng thái majority và dữ liệu còn giữ ở replica nào.

## 12. RabbitMQ: publisher confirm và consumer ack khi restart

Persistent message trong durable queue giúp tăng độ bền nhưng không thay thế việc dùng publisher confirms, đặc biệt khi cần biết broker đã nhận trách nhiệm lưu trữ message tới đâu.

Tình huống quan trọng:

| Tình huống | Hệ quả có thể xảy ra |
|---|---|
| Producer publish rồi mất kết nối trước confirm | Không biết chắc publish đã được xác nhận; cần kiểm tra và retry an toàn |
| Consumer nhận message nhưng chưa ack rồi crash | Broker có thể redeliver cho consumer khác |
| Consumer ghi database thành công nhưng ack chưa tới broker | Message có thể được giao lại và tạo side effect trùng |
| Quorum queue mất majority | Queue có thể không khả dụng để nhận hoặc xử lý theo chế độ cần quorum |

Consumer phải xử lý lặp; producer/bridge cần đối soát bằng message ID. Khi sử dụng Spring Cloud Stream Rabbit binder, xác nhận publish confirmation và retry/error handling đang dùng thực sự phù hợp với delivery guarantee của nghiệp vụ.

## 13. Pulsar: broker mất khác với BookKeeper mất

Pulsar tách broker phục vụ producer/consumer khỏi hệ thống lưu trữ bền vững BookKeeper (bookie). Mất một Pulsar broker có thể làm topic ownership di chuyển, client lookup/reconnect tới broker khác và tiếp tục đọc/ghi nếu metadata và storage còn khỏe.

Ngược lại, mất quá nhiều bookie hoặc lỗi ledger/write quorum có thể khiến dữ liệu không còn được ghi an toàn. Không suy ra “còn broker thì topic vẫn ghi được”.

Khi xử lý Pulsar outage:

- Phân biệt lỗi broker service, metadata/coordination và BookKeeper.
- Xem broker ownership, client lookup/reconnect, topic backlog và subscription cursor.
- Xác nhận bookie còn đủ writable nodes và write/ack quorum theo cấu hình thực tế.
- Kiểm tra message đã broker xác nhận có thể đọc lại sau khi restore.
- Theo dõi redelivery và timeout; không bỏ qua việc xử lý message trùng.

Phục hồi phải đi theo tài liệu vận hành của cụm Pulsar/BookKeeper tương ứng, nhất là khi thay bookie, phục hồi ledger hoặc xử lý ổ đĩa lỗi.

## 14. Mất application instance: ba cửa sổ lỗi cần biết

Khi một Spring Cloud Stream Consumer bị kill, restart hoặc bị orchestrator di chuyển, có ba thời điểm thường gặp:

1. **Trước khi bắt đầu side effect:** message chưa được xử lý; consumer mới cần nhận lại.
2. **Sau khi side effect thành công nhưng trước offset commit/ack:** message có thể được giao lại, tạo duplicate nếu thiếu idempotency.
3. **Sau commit/ack nhưng trước khi gửi một output khác:** nếu hai thao tác không có transaction chung, có thể xuất hiện kết quả thiếu ở downstream.

Ví dụ, Consumer nhận OrderPaid, ghi database là Paid, sau đó crash trước Kafka offset commit. Sau rebalance, cùng event được xử lý lại. Nếu bảng thanh toán có unique constraint theo paymentEventId, lần thứ hai có thể được nhận diện thay vì trừ tiền hai lần.

Điểm mấu chốt: restart chỉ khôi phục worker process; **event state và business consistency** phải được bảo vệ bởi thiết kế pipeline.

## 15. Liveness, readiness và startup probe trong Kubernetes

Kubernetes có ba probe phục vụ mục đích khác nhau:

- **Liveness:** process còn sống về mặt cục bộ hay đã bị kẹt nghiêm trọng cần restart.
- **Readiness:** pod có sẵn sàng tiếp nhận traffic hay tham gia thành phần cần điều phối không.
- **Startup:** cho phép ứng dụng cần thời gian khởi động/khôi phục lâu hoàn tất trước khi liveness bắt đầu áp dụng.

Không dùng broker outage ngắn hạn làm điều kiện liveness thất bại hàng loạt: nếu mọi pod đều restart vì cùng một broker đang lỗi, có thể tạo vòng lặp restart khiến recovery tệ hơn. Kiểm tra việc dùng readiness như thế nào cho message listener; readiness Kubernetes chủ yếu điều khiển Service endpoint, không tự ngừng consumer ở mọi binder.

Ví dụ cấu hình probe HTTP theo Actuator:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Kubernetes manifest minh họa, cần đặt trong container của Deployment tương ứng:

~~~yaml
terminationGracePeriodSeconds: 75
containers:
  - name: order-processor
    image: registry.example/order-processor:1.0.0
    ports:
      - containerPort: 8080
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 5
      failureThreshold: 30
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 10
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
~~~

Cần bật và expose endpoint tương ứng theo bảo mật môi trường. Thời hạn startup, shutdown và probe là ví dụ; đo thời gian restore/teardown thực tế để chọn giá trị, tránh kill process trước khi hoàn tất xử lý message.

## 16. Graceful shutdown để giảm redelivery

Khi nhận SIGTERM trong rolling update hoặc scale down, ứng dụng nên:

1. Ngừng nhận hoặc phát sinh công việc mới theo khả năng binder/consumer.
2. Cho các message đang xử lý kết thúc trong một khoảng thời gian hữu hạn.
3. Ack/commit những message đã hoàn tất theo cơ chế đang dùng.
4. Đóng producer/consumer, connection và resource được quản lý.
5. Bàn giao partition hoặc để broker redeliver message chưa hoàn tất.

Timeout shutdown phải phù hợp thời gian handler, backoff và broker client close; đừng kỳ vọng mọi callback có thể dừng sạch ngay lập tức. Nếu process bị SIGKILL vì hết grace period, message chưa ack/commit có thể được xử lý lại.

PodDisruptionBudget và rolling update strategy giúp giảm số pod mất đồng thời, nhưng không thay thế replication, idempotency hoặc khả năng phục hồi của broker.

## 17. Kafka Streams: mất instance có state store

Ứng dụng Kafka Streams dùng KTable, aggregate hoặc window duy trì state store cục bộ và changelog/repartition topic trong Kafka. Khi pod mất, các task được chuyển sang instance khác; state store phải được khôi phục trước khi task sẵn sàng xử lý đúng.

Phân biệt:

- **Local state directory:** bản sao/trạng thái phục vụ xử lý tại instance, có thể bị mất khi pod bị thay thế.
- **Changelog topic:** nguồn phục hồi state theo cơ chế Kafka Streams khi cấu hình và retention đúng.
- **Standby tasks:** có thể giảm thời gian phục hồi trong điều kiện phù hợp nhưng tiêu tốn tài nguyên và cần được cấu hình, kiểm thử.

Nếu sử dụng ephemeral volume cho state, task có thể phải restore lượng dữ liệu lớn sau mỗi restart. Nếu dùng persistent volume, phải quản lý ownership của state, tránh mount đồng thời cùng state directory vào nhiều task/instance. Không xóa state store chỉ vì startup chậm; xác định trước store có thể khôi phục từ changelog không.

Các chỉ số quan trọng là restore bytes/records, restore duration, rebalance duration, changelog lag, disk I/O và thời gian từ restart đến trạng thái xử lý ổn định.

## 18. Khi đầy đĩa: xác định chính xác lớp lưu trữ

“Đĩa đầy” có thể là:

| Nơi đầy | Ví dụ nguyên nhân | Tác động |
|---|---|---|
| Kafka broker data volume | Topic retention, replication catch-up, log segment tăng | Producer write lỗi, partition không phục vụ ổn định |
| RabbitMQ broker volume | Queue backlog, quorum queue log, message store | Disk alarm, publisher bị chặn hoặc queue không ghi được |
| Pulsar BookKeeper volume | Ledger/data journal tăng, bookie capacity cạn | Ledger writes hoặc ensemble placement lỗi |
| Kafka Streams state directory | Changelog restore, RocksDB, state lớn | Task restore/chạy lỗi, pod restart |
| Application root/log filesystem | Log chi tiết, temp files, heap dumps | JVM/file operations lỗi, container không ổn định |
| Monitoring/logging sidecar | Log buffer không được rotate | Node disk pressure, eviction |

Không dùng một lệnh xóa file chung cho mọi tình huống. Broker quản lý các cấu trúc log, ledger và index có quan hệ nội bộ; xóa thủ công có thể gây mất dữ liệu hoặc hỏng metadata.

## 19. Đánh giá mức nguy cấp của disk pressure

Thu thập ít nhất:

- Filesystem nào đầy, free bytes và inode còn bao nhiêu.
- Tốc độ tăng theo giờ và thời gian dự kiến tới ngưỡng nguy hiểm.
- Thành phần nào đang ghi và loại dữ liệu nào tăng.
- Replication/quorum/retention hiện có còn bảo vệ dữ liệu không.
- Có thể giảm ingress hoặc tạm dừng workload ít ưu tiên mà không làm mất message không.
- Có khả năng mở rộng volume theo quy trình được hỗ trợ không.

Một volume còn 5% trống nhưng có tốc độ tăng 50 GiB/phút có thể cấp bách hơn volume còn 1% trống nhưng không tăng và có đủ vùng đệm hoạt động, tùy yêu cầu hệ thống.

Ưu tiên khôi phục capacity và hạn chế sinh dữ liệu mới. Không bỏ qua cảnh báo chỉ vì JVM vẫn còn chạy hoặc port của broker còn mở.

## 20. Kafka: đầy đĩa trên broker

Khi Kafka data directory thiếu dung lượng, broker có thể không ghi thêm được log, ảnh hưởng partition leader/follower và producer. Nếu replica không theo kịp, ISR có thể thu hẹp, làm producer acks=all không còn đạt ngưỡng ghi.

Runbook an toàn:

1. Xác nhận broker, log directory, free bytes và partition đang bị ảnh hưởng.
2. Kiểm tra broker error log, failed log dirs, under-replicated/offline partitions.
3. Hạn chế producer ingress theo cơ chế ứng dụng hoặc rate limit được duyệt.
4. Mở rộng storage hoặc xử lý partition placement/balancing bằng công cụ quản trị được hỗ trợ.
5. Kiểm tra retention/cleanup policy có đúng thiết kế, nhưng không thay retention tùy tiện khiến dữ liệu chưa được tiêu thụ biến mất.
6. Sau khi có headroom, để broker bắt kịp replica rồi xác minh ISR và producer acknowledgement.
7. Theo dõi consumer lag và xác nhận không có khoảng dữ liệu bị mất hoặc bị bỏ qua.

**Không xóa trực tiếp file trong thư mục Kafka log.dirs** để giải phóng chỗ. Không đổi retention xuống cực thấp trong sự cố khi chưa xác định khả năng replay và tiến độ consumer.

## 21. RabbitMQ: disk alarm và publisher bị chặn

RabbitMQ có cơ chế disk free alarm. Khi disk free giảm dưới ngưỡng cấu hình, broker/cluster có thể chặn publishers để hạn chế tăng lưu trữ, trong khi consumer vẫn có thể tiếp tục nhận và xử lý message để giảm backlog nếu điều kiện khác cho phép.

Ví dụ lưu lượng:

~~~mermaid
flowchart LR
    P[Publishers] -. Blocked by disk alarm .-> R[(RabbitMQ)]
    R --> Q[(Durable / quorum queues)]
    Q --> C[Consumers drain backlog]
    C --> DB[(Business side effects)]
~~~

Cần kiểm tra alarm đang xảy ra ở node nào, dung lượng thực tế và queue nào tích lũy message. Các biện pháp ưu tiên là tăng dung lượng, giảm ingress, cho consumer khỏe xử lý backlog và giải quyết nguyên nhân khiến backlog không được rút bớt.

Không hạ disk_free_limit xuống mức không an toàn hoặc xóa trực tiếp file message store/quorum queue chỉ để publishers hết bị chặn. Đừng thay đổi policies giữa lúc mất quorum nếu chưa hiểu tác động.

## 22. Pulsar/BookKeeper: bookie đầy đĩa

BookKeeper ghi ledger dữ liệu cho Pulsar. Một bookie hết đĩa có thể ngừng nhận ghi mới hoặc gặp lỗi journal/entry log; nếu không còn đủ bookie có thể ghi đáp ứng ensemble/write quorum, producer cũng có thể thất bại dù broker vẫn sống.

Hướng xử lý cần theo quy trình vận hành Pulsar/BookKeeper:

- Xem bookie writable/read-only state, journal và ledger directories.
- Xem disk free, entry log compaction/garbage collection và ledger replication health.
- Giảm ingress hoặc chuyển workload theo chính sách được hỗ trợ nếu thiếu writable bookies.
- Tăng capacity hoặc bổ sung bookie, cho hệ thống cân bằng/khôi phục ledger theo công cụ chính thức.
- Xác nhận các namespace/topic có thể produce/consume và subscription backlog được xử lý lại.

Không xóa thủ công ledger/index files. Không coi Pulsar broker restart là biện pháp chính nếu gốc vấn đề là storage layer BookKeeper.

## 23. Application hoặc Kafka Streams state disk đầy

Disk của application có thể đầy do log, temp files, heap dump hoặc RocksDB state của Kafka Streams. Tác động khác nhau:

- Log root filesystem đầy: application có thể tiếp tục xử lý một phần nhưng mất khả năng ghi log, dump hoặc file tạm.
- Kafka Streams state volume đầy: state store/restore có thể thất bại, task chuyển trạng thái lỗi.
- Node ephemeral storage pressure: Kubernetes có thể evict pod và làm consumer rebalance lặp lại.

Runbook:

1. Tìm đúng filesystem gây lỗi và loại dữ liệu tăng nhanh.
2. Kiểm tra workload có thể dừng/giảm tạm thời để tránh ghi thêm không.
3. Xử lý log rotation và bổ sung quota/capacity theo tiêu chuẩn hạ tầng.
4. Nếu state store cần dựng lại, xác nhận changelog và replication còn đầy đủ trước khi cân nhắc tái tạo local state.
5. Sau restart, chờ state restore/readiness; theo dõi I/O và khối lượng tải trở lại.

Đừng xóa state directory của pod đang chạy hoặc xóa volume chứa dữ liệu không thể tái tạo. Nếu khôi phục state từ changelog, tính toán trước thời gian restore và khoảng retention cần thiết.

## 24. Backpressure và điều tiết ingress trong khi phục hồi

Nếu đầu vào tiếp tục tăng khi consumer giảm capacity, backlog có thể vượt storage và kéo theo sự cố đĩa. Cần có cơ chế điều tiết được phê duyệt:

- Giảm tốc độ publisher không quan trọng hoặc tạm ngừng batch import.
- Rate-limit upstream API/producer theo tenant, priority hoặc event type.
- Giới hạn concurrent processing nếu downstream quá tải; tránh tăng retry nóng.
- Dùng retry với exponential backoff và jitter phù hợp để tránh nhiều instance đồng loạt retry.
- Giữ lại message trong broker/storage có đủ retention thay vì bỏ qua dữ liệu âm thầm.

Giảm tải không đồng nghĩa được phép đánh rơi event đã chấp nhận. Nếu upstream không thể tạm giữ, hệ thống cần khả năng từ chối yêu cầu có tín hiệu rõ ràng hoặc durable buffer/outbox trong phạm vi hợp đồng nghiệp vụ.

## 25. Retry, DLQ và poison message khi hệ thống khôi phục

Sau khi broker quay lại, rất nhiều message có thể được giao cùng lúc. Nếu một số message luôn gây lỗi, retry không giới hạn sẽ giữ partition/consumer trong vòng lặp, tạo lại disk pressure và làm trễ message khỏe.

Thiết kế an toàn:

1. Phân loại lỗi transient và non-retryable.
2. Đặt retry tối đa, backoff và lỗi đủ điều kiện retry.
3. Đưa poison message tới DLQ theo chính sách; cảnh báo nếu DLQ publish thất bại.
4. Gắn eventId, original topic/queue, lý do lỗi, số lần xử lý và thời điểm vào dữ liệu lỗi.
5. Reprocess DLQ qua một quy trình có phê duyệt và có idempotency, không đẩy trả lại hàng loạt vô hạn.

DLQ không phải “thùng rác” thay cho việc sửa schema/logic. Khi disk full, cần tính cả lưu lượng từ retry và DLQ vì chúng cũng tiêu thụ storage.

## 26. Cấu hình minh họa cho Spring Cloud Stream Kafka binder

Ví dụ một consumer xử lý order event, cố định group, không tự tạo topic và có giới hạn thời gian shutdown. Cấu hình dùng một root spring duy nhất:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          consumer:
            maxAttempts: 3
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          autoCreateTopics: false
          autoAddPartitions: false
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.events.dlt
server:
  shutdown: graceful
~~~

Đây là cấu hình minh họa, không phải chứng minh rằng retry, DLQ hoặc transaction đã được kiểm thử. Cần tạo DLQ, quyền publish, chính sách consumer và producer trước. Thuộc tính cụ thể phụ thuộc Spring Cloud Stream/Kafka binder version; khi dùng batch mode, transactional binder hoặc native decoding, cơ chế error handling có thể khác.

## 27. Cấu hình Rabbit binder và DLQ theo workload

Với RabbitMQ, destination thường được ánh xạ vào exchange và group consumer liên quan queue. Cấu hình ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              prefetch: 20
~~~

Khi production đã pre-provision queue/exchange và hạn chế runtime principal, cần phối hợp autoBindDlq/provisioning đúng thực tế. Prefetch quá lớn có thể tăng unacked messages và thời gian redelivery khi instance chết; prefetch quá nhỏ có thể làm giảm throughput.

Không mặc định rằng bật DLQ là xử lý được mọi lỗi. Kiểm tra dead-letter exchange/queue, permission của publisher/consumer, retry policy và việc message lỗi có đi tới DLQ hay không.

## 28. Phục hồi Pulsar binder: subscription và acknowledgement

Spring Cloud Stream Pulsar binder dùng topic/subscription, khác Kafka group offset và Rabbit queue acknowledgement:

- **Exclusive/Failover:** phù hợp khi chỉ một consumer active theo phạm vi tương ứng; failover có thể chuyển consumer.
- **Shared:** nhiều consumer chia tải; redelivery có thể đến consumer khác, không bảo toàn thứ tự toàn subscription.
- **Key_Shared:** phân phối theo key để giữ affinity theo key trong điều kiện bình thường; cần producer key/batching tương thích.

Khi Pulsar broker hoặc consumer instance mất, đối chiếu subscription cursor, unacked messages, redelivery và backlog. Cần xác nhận deadline ack, negative ack, retry letter/DLQ và các tham số binder được hỗ trợ đúng theo phiên bản đang dùng.

Nếu yêu cầu thứ tự theo orderId hoặc accountId, đừng chuyển subscription type sang Shared trong sự cố chỉ để tăng concurrency mà không đánh giá semantics nghiệp vụ.

## 29. Mô hình dữ liệu để xử lý lặp an toàn

Một ví dụ business handler có eventId ổn định:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPaid(String eventId, String orderId, long amountCents) {}

interface PaymentService {
    void applyOnce(String eventId, String orderId, long amountCents);
}

@Configuration
class PaymentFunctions {

    @Bean
    Consumer<OrderPaid> processPayment(PaymentService paymentService) {
        return event -> paymentService.applyOnce(
            event.eventId(), event.orderId(), event.amountCents()
        );
    }
}
~~~

Hàm applyOnce phải được cài đặt thật bằng transaction/unique constraint hoặc inbox phù hợp, không chỉ kiểm tra một map trong bộ nhớ. Một implementation khả dụng có thể:

1. Mở transaction database.
2. Insert eventId vào bảng processed_events có unique constraint.
3. Nếu eventId đã tồn tại, bỏ qua side effect trùng.
4. Nếu insert mới, cập nhật trạng thái/thanh toán trong cùng transaction.
5. Commit transaction; sau đó mới để consumer ack/commit theo semantics đã cấu hình.

Nếu message redeliver khi mất instance hoặc broker, eventId bảo vệ side effect khỏi chạy hai lần. Điều này không tự thay thế idempotency cho các HTTP API ngoài database; cần idempotency key hoặc outbox nếu gọi dịch vụ bên ngoài.

## 30. Đo thời gian drain backlog sau phục hồi

Khi broker hoạt động lại, ingestion có thể tiếp tục ngay lập tức nhưng backlog vẫn tăng nếu throughput xử lý không vượt tốc độ đầu vào.

Giả sử:

~~~text
backlog after outage = 90,000 events
new incoming rate     = 600 events/s
processing capacity   = 1,100 events/s
net drain rate        = 500 events/s
estimated drain time  = 90,000 / 500 = 180 s
~~~

Đây là mô hình tuyến tính đơn giản. Retry, hot key, payload lớn và database bottleneck có thể làm tốc độ xử lý giảm theo thời gian. Nếu capacity chỉ bằng hoặc nhỏ hơn ingress, backlog sẽ không tự hết.

Đo backlog age cùng backlog count, p95/p99 end-to-end latency, retry attempts và CPU/disk I/O trong recovery. Đừng tăng consumer replica một cách mù quáng khi bottleneck là một partition nóng hoặc downstream đang bị giới hạn connection pool.

## 31. Bảng thử nghiệm sự cố trong staging

Trước production, diễn tập trong môi trường có broker topology, replication, volume, retention và tính năng retry gần giống thực tế:

| Mã | Thao tác trong staging | Kỳ vọng chính | Bằng chứng cần thu |
|---|---|---|---|
| F01 | Dừng một Kafka broker khi có tải | Leader failover, không mất message được bảo vệ | ISR, producer errors, eventId đối soát |
| F02 | Dừng một consumer pod | Partition được gán lại, backlog giảm sau khi phục hồi | Rebalance, lag, duplicate prevented |
| F03 | Kill pod sau DB commit, trước ack (fault hook) | Redelivery không gây side effect trùng | Unique eventId và database state |
| F04 | Mất một RabbitMQ node trong quorum queue | Queue duy trì phục vụ nếu majority còn | Quorum status, publisher confirm |
| F05 | Mất Pulsar broker | Client reconnect và đọc/ghi tiếp khi storage khỏe | Topic ownership, backlog, redelivery |
| F06 | Giới hạn disk của broker test tới ngưỡng cảnh báo | Alert, chặn/giảm write theo broker, không mất dữ liệu | Disk alarm, logs, free bytes |
| F07 | Điền local state volume của test pod theo cách cô lập | Task lỗi có kiểm soát rồi restore | Restore time, state correctness |
| F08 | Mô phỏng downstream 503 và poison message | Retry giới hạn, DLQ đúng | Retry count, DLQ ID, no infinite loop |
| F09 | Khôi phục broker sau 5 phút mất kết nối | Backlog drain trong RTO mục tiêu | Drain graph, last event age |

Các thao tác phá hỏng có kiểm soát chỉ dùng tài nguyên test được phê duyệt. Với disk full, ưu tiên quota/volume test cô lập; không đổ dữ liệu vô hạn vào filesystem dùng chung của cluster hoặc máy cá nhân.

## 32. Đối soát sự kiện sau một sự cố

Tạo eventId/correlationId ngay từ producer. Sau khi phục hồi, tổng hợp theo **tập event ID duy nhất**:

~~~text
broker-acknowledged input IDs
    = unique successfully completed IDs
    + unique business-rejected IDs
    + unique DLQ IDs
    + unique still-pending/unknown IDs
~~~

Điều kiện: các nhóm outcome phải **loại trừ nhau**, hoặc verifier cần cảnh báo ID xuất hiện đồng thời ở hai nhóm. Chỉ đếm message count có thể che duplicate và missing IDs.

Kiểm tra thêm:

- Có bao nhiêu message được xử lý lại nhưng không gây duplicate side effect?
- Có message nào đã broker ack nhưng không tìm thấy tại outcome nào sau recovery deadline?
- Có event nào ở DLQ do lỗi transient đáng lẽ được xử lý thành công?
- Độ trễ lớn nhất của event cũ nhất còn tồn đọng là bao nhiêu?
- Kafka Streams store có khôi phục lại kết quả tương ứng với changelog không?

Một run không đạt nếu còn unknown outcome quá deadline, dù service health endpoint trả UP.

## 33. Hành động nguy hiểm cần tránh

- Không xóa Kafka log segment, RabbitMQ message store hoặc BookKeeper ledger trực tiếp khỏi filesystem.
- Không xóa queue/DLQ hoặc reset consumer offset hàng loạt khi chưa có kế hoạch đối soát và phê duyệt.
- Không bật unclean Kafka leader election hoặc hạ min ISR mặc định trong sự cố mà chưa đánh giá mất dữ liệu.
- Không tắt publisher confirm hoặc giảm durability chỉ để benchmark có throughput cao hơn.
- Không dùng liveness probe phụ thuộc broker khiến toàn bộ pod restart liên tục khi broker lỗi.
- Không xóa Kafka Streams local state store nếu chưa chắc changelog có thể dựng lại.
- Không xử lý poison message bằng retry vô hạn hoặc reprocess DLQ không giới hạn.
- Không scale consumer vượt capacity downstream, tạo retry storm và áp lực đĩa lớn hơn.
- Không đóng incident khi chỉ thấy application pod RUNNING mà lag vẫn tăng.

Mọi thao tác làm giảm durability hoặc nguy cơ mất dữ liệu phải được coi là thay đổi vận hành rủi ro cao, có owner phê duyệt và ghi nhận rõ giới hạn RPO.

## 34. Checklist trước khi go-live

- [ ] Có replication/quorum phù hợp cho Kafka, RabbitMQ hoặc Pulsar/BookKeeper.
- [ ] Broker data volumes có cảnh báo capacity và tốc độ tăng trước khi đầy.
- [ ] Có ít nhất một instance dự phòng hoặc chiến lược phục hồi rõ ràng cho workload quan trọng.
- [ ] Readiness/liveness/startup probe không gây restart storm khi broker mất.
- [ ] Graceful shutdown và termination grace period đã được thử nghiệm.
- [ ] Offset/ack chỉ tiến sau khi phần xử lý cần thiết hoàn tất, theo delivery semantics.
- [ ] Consumer handler có idempotency cho duplicate/redelivery.
- [ ] Retry hữu hạn, backoff và DLQ được kiểm tra end-to-end.
- [ ] Có dashboard producer errors, consumer lag, queue backlog age, DLQ và disk free.
- [ ] Changelog/state restore Kafka Streams đã được diễn tập nếu có xử lý stateful.
- [ ] Có phương án giảm ingress mà không âm thầm bỏ event.
- [ ] Có runbook riêng cho broker outage, pod loss và disk pressure.
- [ ] Có bài thử nghiệm fault trong staging với eventId đối soát được.
- [ ] Đã đo RTO/RPO và backlog drain so với SLO nghiệp vụ.

## 35. Tóm tắt quy trình phản ứng

Khi mất broker: **kiểm tra replication/quorum trước, phục hồi node và xác minh producer/consumer tiếp tục theo đúng durability**. Khi mất instance: **để orchestration/broker phân phối lại workload, bảo vệ side effect bằng idempotency và chờ state restore khi cần**. Khi đầy đĩa: **xác định chính xác tầng lưu trữ, hạn chế nguồn sinh tải, mở rộng hoặc giải phóng capacity bằng cơ chế được hỗ trợ; không xóa file broker tùy tiện**.

Điểm kết thúc của mọi sự cố phải là một kết luận có bằng chứng: topic/queue phục vụ trở lại, dữ liệu đã được broker xác nhận vẫn có outcome hợp lệ, message bị lỗi được cô lập có kiểm soát, backlog đang giảm và các chỉ số RTO/RPO/SLO được đáp ứng. Như vậy, Spring Cloud Stream không chỉ tự kết nối lại mà còn thực sự phục hồi khả năng xử lý sự kiện và trạng thái nghiệp vụ.

## Tài liệu tham khảo

- [Spring Cloud Stream — Reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Spring Cloud Stream Kafka Binder — Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream Rabbit Binder — Reference](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Apache Kafka — Operations and Replication](https://kafka.apache.org/documentation/)
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [RabbitMQ — Disk Alarms](https://www.rabbitmq.com/docs/disk-alarms)
- [Apache Pulsar — Architecture](https://pulsar.apache.org/docs/concepts-architecture-overview/)
- [Apache BookKeeper — Overview](https://bookkeeper.apache.org/docs/overview/)

