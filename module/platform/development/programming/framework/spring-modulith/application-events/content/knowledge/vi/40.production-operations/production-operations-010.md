# Kiểm tra sau phát hành

Sau khi phát hành một phiên bản của module **SPRING_MODULITH_APPLICATION_EVENTS**, việc deployment thành công mới xác nhận artifact đã được triển khai. Nó chưa chứng minh application events đang được publish, listener nhận đúng event, transaction được xử lý đúng phase hoặc message đã tới consumer. Một release có thể trả HTTP 200 nhưng publication vẫn incomplete, outbox tăng backlog, consumer lag kéo dài hoặc event mới không tương thích với phiên bản consumer đang chạy.

**Kiểm tra sau phát hành** là quy trình xác nhận phiên bản mới hoạt động đúng trong môi trường production sau khi rollout. Quy trình phải kiểm tra cả sức khỏe kỹ thuật và kết quả nghiệp vụ theo từng boundary: producer, transaction, publication registry, externalization, broker, consumer và hệ thống đích. Mỗi kết luận cần dựa trên số liệu, trace hoặc một hành vi có thể quan sát.

Mục tiêu là phát hiện sớm regression, xác định phạm vi ảnh hưởng và quyết định tiếp tục rollout, dừng rollout, rollback hay sửa tiến. Các ngưỡng cần lấy từ SLO, baseline và chính sách vận hành của hệ thống; không dùng một con số chung cho mọi ứng dụng hoặc broker.

## 1. Xác định mục tiêu và phạm vi release

Trước khi kiểm tra, xác định chính xác phiên bản vừa phát hành và những luồng event bị ảnh hưởng:

- Artifact, image digest, commit hoặc release identifier.
- Module/service producer và consumer đã được nâng cấp.
- Event type, schema version hoặc listener thay đổi.
- Transaction phase, executor, retry policy hoặc registry configuration thay đổi.
- Adapter, exchange, queue, topic, routing key hoặc consumer group liên quan.
- Migration database, outbox/inbox hoặc publication persistence.
- Feature flag và cấu hình được bật/tắt trong release.

Không kiểm tra toàn bộ hệ thống một cách không định hướng. Hãy chọn các luồng nghiệp vụ quan trọng và boundary thay đổi trong release. Nếu chỉ thay đổi serializer của OrderConfirmed, ưu tiên kiểm tra producer serialization, externalization, consumer deserialization và event history liên quan.

Một release có thể ảnh hưởng tới nhiều producer hoặc consumer cùng đọc một contract. Liệt kê các bên liên quan để không bỏ sót consumer độc lập, instance cũ trong rolling deployment hoặc luồng replay từ DLQ/archive.

## 2. Chuẩn bị baseline trước khi rollout

Để biết hệ thống có regression hay không, cần có số liệu trước release hoặc từ một khoảng thời gian ổn định gần nhất.

Baseline nên bao gồm:

| Nhóm | Số liệu cần lưu |
|---|---|
| Application | instance count, startup, readiness, error rate |
| Producer | số event publish, publish failure, latency |
| Publication registry | incomplete count, publication age, listener failure |
| Outbox | pending count, oldest pending age, dispatch rate |
| Broker | queue depth/consumer lag, redelivery, publish confirm, DLQ |
| Consumer | throughput, processing latency, exception rate |
| Database | connection pool, transaction latency, lock wait, replication lag |
| JVM | heap, allocation, GC pause, thread/executor saturation |
| Business | số đơn xác nhận, reservation thành công, notification hoàn tất |

Dùng cùng cách lọc theo event type, destination, consumer và time window trước/sau release. Khi có thể, so sánh canary với instance hoặc nhóm consumer chưa nâng cấp. Nếu không có baseline, ghi rõ giới hạn và dựa vào SLO, xu hướng lịch sử hoặc ngưỡng cảnh báo đã được phê duyệt.

Không chỉ so sánh trung bình. p95/p99, maximum, backlog age và tỷ lệ lỗi thường bộc lộ regression rõ hơn. Một lượng event nhỏ có thể khiến average latency trông bình thường trong khi một nhóm consumer bị treo.

## 3. Kiểm tra rollout và phiên bản đang chạy

Xác nhận phiên bản mới đã chạy ở đúng môi trường, đúng số instance và đúng cấu hình dự kiến:

- Release identifier hoặc image digest khớp với bản được duyệt.
- Instance mới đã khởi động và readiness thành công.
- Không còn instance cũ ngoài kế hoạch rollout.
- Profile, environment variables và feature flags đúng.
- Secret, credential và certificate cần cho broker/database đã được nạp.
- Database migration hoàn tất và schema ở trạng thái tương thích.
- Consumer group hoặc queue subscription vẫn hoạt động.
- Không có restart loop, crash hoặc OOM sau startup.

Trong rolling deployment, có thể tồn tại producer mới và consumer cũ cùng lúc. Xác nhận contract tương thích với tất cả phiên bản còn nhận event. Đừng bắt đầu phát schema mới chỉ vì một instance consumer mới đã sẵn sàng; phải biết toàn bộ consumer liên quan đã đáp ứng điều kiện rollout.

Readiness chỉ xác nhận những dependency và điều kiện được cấu hình trong health check. Nó không tự chứng minh một event cụ thể đã đi qua toàn pipeline.

## 4. Kiểm tra health, readiness và dependency

Kiểm tra sức khỏe ứng dụng theo cơ chế health check đang dùng. Xác nhận application context khởi tạo thành công, database connection pool có thể phục vụ, broker connection/channel hoạt động và executor cần thiết không bị bão hòa.

Phân biệt:

- **Liveness:** process còn sống và không ở trạng thái cần restart.
- **Readiness:** instance có thể nhận traffic hoặc công việc theo điều kiện cấu hình.
- **Dependency health:** database, broker, schema registry hoặc service ngoài có thể truy cập.
- **Business health:** các luồng event thực sự tạo được kết quả nghiệp vụ.

Một dependency tạm thời không sẵn sàng có thể không nên làm toàn bộ ứng dụng mất readiness nếu hệ thống có outbox hoặc cơ chế lưu bền vững để tiếp tục xử lý sau. Ngược lại, nếu consumer không thể nhận message và backlog đang tăng vượt khả năng phục hồi, cần phản ánh rủi ro đó trong trạng thái vận hành.

Không đánh dấu ứng dụng healthy chỉ vì endpoint health trả UP. Hãy kết hợp health với publication state, broker metrics và business outcome.

## 5. Kiểm tra luồng event end-to-end

Chọn một hoặc vài luồng nghiệp vụ đại diện cho thay đổi vừa phát hành. Với mỗi luồng, lần theo event từ producer tới kết quả cuối.

~~~mermaid
sequenceDiagram
    participant P as Producer module
    participant DB as Producer database
    participant R as Publication registry/outbox
    participant B as Broker
    participant C as Consumer
    participant D as Consumer database
    P->>DB: Commit business change
    P->>R: Persist publication/message
    R->>B: Externalize event
    B-->>R: Confirm delivery
    B->>C: Deliver event
    C->>D: Apply business effect
    D-->>C: Commit
    C-->>B: ACK/offset commit
~~~

Sơ đồ là khung tham chiếu; ứng dụng có thể dùng registry, outbox hoặc một cơ chế khác. Hãy thay các participant theo kiến trúc thật.

Với từng event, kiểm tra:

1. Producer tạo đúng event type và schema version.
2. Payload có eventId, aggregateId và metadata cần thiết.
3. Event được publish tại thời điểm transaction đúng.
4. Publication/outbox được ghi theo thiết kế.
5. Externalization hoặc broker nhận message.
6. Consumer nhận và deserialize thành công.
7. Handler thực hiện đúng use case.
8. Database đích commit kết quả.
9. ACK/offset hoặc publication state được cập nhật.
10. Trace/correlation liên kết được các bước.

Không kết luận end-to-end thành công chỉ từ log “published”. Producer publish thành công và consumer hoàn tất là hai mốc khác nhau.

## 6. Kiểm tra transaction và AFTER_COMMIT

Nếu release thay đổi listener transaction phase hoặc cách publish event, xác nhận transaction behavior trong môi trường thực tế.

Kiểm tra:

- Event được publish trong đúng transaction nghiệp vụ.
- Listener AFTER_COMMIT chỉ xử lý sau commit thành công.
- Rollback không tạo tác dụng phụ ở consumer theo thiết kế.
- Listener không giả định transaction nguồn vẫn còn mở sau commit.
- Các thao tác ghi của listener có transaction riêng phù hợp.
- Async listener không đọc dữ liệu trước khi dữ liệu nguồn sẵn sàng.
- Không có self-invocation hoặc cấu hình proxy làm mất semantics mong đợi.

Một luồng điển hình:

~~~mermaid
sequenceDiagram
    participant U as Use case
    participant DB as Source DB
    participant E as Event
    participant L as AFTER_COMMIT listener
    participant T as Target DB
    U->>DB: Begin transaction
    U->>DB: Save business state
    U->>E: Publish event
    U->>DB: Commit
    DB-->>U: Commit success
    E->>L: Invoke eligible listener
    L->>T: Apply target change
    T-->>L: Commit target transaction
~~~

Trong production, xác nhận bằng trace, log có correlation ID và trạng thái dữ liệu đích. Nếu listener chạy bất đồng bộ, theo dõi thời gian từ source commit tới target commit; không dùng thời điểm publish làm đại diện cho thời điểm hoàn tất.

## 7. Kiểm tra Event Publication Registry

Nếu ứng dụng dùng Spring Modulith Event Publication Registry, kiểm tra publication state theo listener và event type sau release.

Các tín hiệu cần theo dõi:

- Số publication incomplete.
- Tuổi của publication incomplete lâu nhất.
- Tốc độ publication được đánh dấu completed.
- Listener có exception mới hoặc failure lặp lại không.
- Publication có bị giữ lại do listener không được đăng ký hoặc context không phù hợp không.
- Resubmit có làm publication tiến triển không.
- Publication completed có được retention/cleanup theo chính sách không.

So sánh với baseline. Một vài publication incomplete trong khoảng thời gian ngắn có thể là bình thường trong lúc xử lý. Backlog tăng liên tục hoặc publication cũ vượt retry/SLO window là dấu hiệu cần điều tra.

Không xóa publication incomplete để làm dashboard sạch. Trước khi resubmit, xác định listener đã thực hiện tác dụng phụ hay chưa và consumer có idempotent không. Việc resubmit có thể chạy lại listener; thao tác không idempotent có thể tạo kết quả lặp.

API quan sát và tên trạng thái cụ thể phụ thuộc phiên bản Spring Modulith cùng persistence adapter. Dùng API/endpoint được hỗ trợ trong phiên bản ứng dụng; không phụ thuộc trực tiếp vào schema nội bộ nếu không cần.

## 8. Kiểm tra transactional outbox và dispatcher

Nếu release dùng outbox, xác nhận message được ghi cùng transaction nghiệp vụ và dispatcher gửi được message pending.

Theo dõi:

- Pending count và oldest pending age.
- Tốc độ insert so với tốc độ dispatch.
- Số lần publish thất bại.
- Thời gian từ outbox commit tới broker confirm.
- Số bản ghi bị claim quá lâu hoặc lease hết hạn.
- Số bản ghi SENT và cleanup theo retention.
- Database I/O, lock wait và replication lag.

Nếu pending backlog tăng, xác định producer đang tạo event nhanh hơn dispatcher, broker đang unavailable hay dispatcher gặp lỗi mapping/serialization. Không xóa pending row để giảm dung lượng. Không đánh dấu SENT khi chưa có xác nhận publish theo semantics của adapter.

Có cửa sổ lỗi khi broker đã nhận message nhưng dispatcher chưa kịp đánh dấu outbox SENT. Khi restart, message có thể được gửi lại. Kiểm tra consumer deduplication và event identity trước khi replay hoặc resubmit.

## 9. Kiểm tra broker và transport

Broker là boundary riêng với producer và consumer. Sau release, kiểm tra các tín hiệu phù hợp với transport đang dùng.

**RabbitMQ/AMQP:**

- Connection, channel và publisher confirm.
- Exchange, queue, binding và routing key.
- Message unroutable/returned nếu có cấu hình.
- Queue depth, unacknowledged messages và consumer count.
- Redelivery, NACK/requeue và dead-letter routing.
- Memory/disk alarm và connection churn.

**Kafka:**

- Producer error và broker availability.
- Topic, partition và replication health.
- Consumer group membership và rebalance.
- Consumer lag theo partition.
- Offset commit và processing failure.
- Record/batch size cùng schema compatibility.

Không dùng thuật ngữ ACK của RabbitMQ để mô tả chính xác offset commit của Kafka. Mỗi transport có semantics khác nhau; dashboard và runbook cần dùng tên metric đúng với broker.

Nếu publish confirm thất bại, kiểm tra xem message có thể đã được broker nhận hay không trước khi gửi lại. Consumer cần idempotency để xử lý tình huống kết quả publish không rõ ràng.

## 10. Kiểm tra consumer và tác dụng nghiệp vụ

Consumer có thể nhận message nhưng không tạo được kết quả nghiệp vụ. Vì vậy, kiểm tra cả transport delivery và handler outcome.

Với từng consumer:

- Instance đang hoạt động và tham gia đúng queue/topic hoặc consumer group.
- Event type/schema version được hỗ trợ.
- Deserialize và validation thành công.
- Handler hoàn tất trong thời gian dự kiến.
- Database transaction commit.
- Inbox/dedup state được cập nhật đúng.
- ACK/offset chỉ được commit theo chính sách sau khi xử lý đạt điều kiện.
- Không có duplicate side effect hoặc event bị bỏ qua ngoài dự kiến.

Theo dõi throughput và processing latency theo event type/consumer. Nếu broker queue depth thấp nhưng business outcome không tăng, có thể consumer đang ACK quá sớm, bỏ qua message hoặc xử lý sai nhánh. Nếu consumer lag tăng, xem concurrency, database pool, lock contention và dependency ngoài.

Một smoke test chỉ nên dùng event an toàn, có định danh riêng và tác dụng được kiểm soát. Không tạo giao dịch giả có thể gửi email, thanh toán hoặc thay đổi tồn kho thật nếu chưa có quy trình sandbox/canary tương ứng.

## 11. Kiểm tra retry, redelivery và DLQ

Sau release, retry rate tăng có thể chỉ ra dependency chập chờn, timeout mới, exception handler hoặc thay đổi payload. Cần phân biệt lỗi tạm thời với lỗi vĩnh viễn.

Kiểm tra:

- Số lần retry theo event type và consumer.
- Backoff/delay có hoạt động đúng.
- Redelivery có tăng đột biến.
- Poison message có bị retry vô hạn không.
- DLQ/quarantine có message mới không.
- Retry exhausted có tạo alert hoặc ticket theo runbook không.
- Operator replay có giữ eventId/correlation metadata và bảo đảm idempotency không.

Không replay toàn bộ DLQ chỉ để kiểm tra hệ thống sau release. Chọn message đã hiểu nguyên nhân, xác nhận consumer đã được sửa và chạy thử với một nhóm nhỏ. Theo dõi tác dụng nghiệp vụ trước khi mở rộng replay.

Nếu lỗi là schema incompatibility hoặc validation permanent, retry liên tục thường không giúp. Chuyển quarantine/DLQ theo policy và nâng cấp consumer hoặc adapter trước khi replay.

## 12. Kiểm tra duplicate và idempotency

Trong giao nhận at-least-once, duplicate có thể xuất hiện sau timeout, mất ACK, restart consumer hoặc resubmit publication. Sau release, cần xác nhận một event được giao nhiều lần không tạo nhiều tác dụng phụ.

Kiểm tra:

- eventId ổn định qua retry/redelivery.
- Inbox/dedup key có đúng scope consumer không.
- Unique constraint hoặc atomic claim hoạt động.
- Inbox state và business effect được commit nhất quán.
- Duplicate đã COMPLETED được ACK/skip an toàn.
- PROCESSING/lease cũ được recovery theo chính sách.
- External side effect có idempotency key hoặc reconciliation.

Nếu consumer xử lý thanh toán, gửi thông báo hoặc gọi API ngoài, kiểm tra idempotency ở chính hệ thống đích. Inbox database không tự bảo đảm external API chỉ thực hiện một lần nếu process dừng sau khi API thành công nhưng trước khi lưu trạng thái hoàn tất.

Không tạo duplicate test bằng cách replay event production tùy tiện. Dùng fixture hoặc canary đã được phê duyệt để xác minh behavior.

## 13. Kiểm tra schema và tương thích phiên bản

Trong rolling deployment, producer và consumer có thể chạy các version khác nhau. Sau release, xác nhận:

- Producer phát đúng eventType và schemaVersion.
- Consumer đang chạy hỗ trợ schema mới.
- Field mới có default/optional semantics đúng.
- Unknown enum hoặc event type được xử lý theo policy.
- Serializer/deserializer dùng cùng encoding và schema rules.
- Event lịch sử vẫn đọc được nếu có replay.
- Publication chưa hoàn tất từ version cũ có thể deserialize sau upgrade.
- Schema Registry compatibility check đã pass nếu sử dụng.

Không coi deploy thành công là bằng chứng contract tương thích. Hãy quan sát deserialize failure, quarantine/DLQ và handler fallback theo version. Nếu consumer cũ không đọc được event mới, dừng mở rộng producer rollout hoặc route event version mới tới consumer tương thích.

Khi thay đổi breaking, dùng expand-contract: nâng cấp consumer để đọc cả schema cũ và mới, xác nhận toàn bộ instance sẵn sàng, rồi mới cho producer phát schema mới.

## 14. Kiểm tra hiệu năng và capacity sau release

So sánh hệ thống với baseline để phát hiện regression:

- Publish latency và serialization time.
- Consumer processing p50/p95/p99.
- Event throughput và backlog growth.
- Queue depth hoặc Kafka lag.
- Outbox/registry storage growth.
- Database transaction time, lock wait và connection pool usage.
- JVM heap, allocation rate, GC pause và executor queue.
- Network bytes và payload size.
- Retry/redelivery rate.

Một release có thể tăng payload size hoặc thêm listener khiến latency và heap usage tăng dù error rate vẫn thấp. Hãy kiểm tra cả xu hướng và mức sử dụng tài nguyên khi tải tăng.

Nếu throughput đầu vào lớn hơn throughput xử lý trong thời gian kéo dài, backlog sẽ tăng. Xác định bottleneck trước khi tăng concurrency: database pool, broker partition, lock, executor hoặc external API có thể là giới hạn. Tăng concurrency không kiểm soát có thể làm hệ thống nghẽn nặng hơn.

## 15. Kiểm tra bảo mật và dữ liệu

Event có thể chứa dữ liệu nghiệp vụ nhạy cảm và được sao chép sang broker, log, trace, DLQ hoặc archive. Sau release, xác nhận:

- Producer chỉ phát field cần thiết.
- Không có token, password hoặc secret trong payload.
- Broker ACL/credential và TLS đúng.
- Consumer chỉ subscribe destination được phép.
- Log/trace không ghi toàn bộ payload nhạy cảm.
- DLQ và publication store có quyền truy cập phù hợp.
- Encryption và key configuration hoạt động.
- Retention/cleanup không bị thay đổi ngoài ý muốn.
- Event mới không làm lộ field nội bộ hoặc PII ngoài contract.

Nếu release thay đổi schema, kiểm tra field mới trong log, metric và trace. Không dùng eventId hoặc customerId làm metric tag có cardinality cao. Nếu phát hiện dữ liệu nhạy cảm bị công bố sai, xử lý như incident dữ liệu theo quy trình tổ chức; dừng phát event bị ảnh hưởng và xác định bản sao cần thu hồi/xóa.

## 16. Canary và smoke test an toàn

Canary cho phép xác nhận phiên bản mới trên một phần traffic hoặc một tập consumer nhỏ trước khi rollout toàn bộ. Chọn luồng có thể quan sát và giới hạn tác dụng.

Một smoke test an toàn nên:

1. Dùng business key hoặc tenant được dành riêng cho kiểm tra.
2. Dùng event type đã có consumer tương thích.
3. Có eventId và correlationId riêng.
4. Không kích hoạt thanh toán, gửi thông báo thật hoặc side effect không thể đảo ngược nếu chưa có phê duyệt.
5. Có tiêu chí kết quả rõ: source commit, consumer outcome và target state.
6. Có thời hạn cleanup dữ liệu kiểm tra.
7. Không dùng payload giả không hợp lệ với contract production.

Nếu không thể tạo canary nghiệp vụ an toàn, dùng trace/metric của traffic thật và kiểm tra log đã được kiểm soát. Không tạo event trực tiếp vào broker nếu cách đó bỏ qua producer contract hoặc transaction behavior mà release cần xác minh.

## 17. Quyết định tiếp tục, dừng hoặc rollback

Đặt release gate trước khi rollout để tránh quyết định theo cảm tính. Ví dụ tiêu chí:

| Tín hiệu | Tiếp tục | Dừng rollout/điều tra |
|---|---|---|
| Application readiness | Ổn định theo yêu cầu | Instance crash/restart hoặc thiếu dependency |
| Producer errors | Trong baseline/SLO | Tăng bất thường hoặc publish thất bại |
| Publication/outbox | Backlog ổn định, tuổi trong giới hạn | Incomplete/pending tăng liên tục |
| Broker | Queue/lag ổn định | Unroutable, lag hoặc redelivery tăng |
| Consumer | Throughput và business outcome bình thường | Deserialize/handler failure hoặc outcome giảm |
| DLQ | Không tăng bất thường | Có message mới thuộc luồng trọng yếu |
| Performance | p95/p99 và resource trong budget | Latency, heap hoặc database load vượt ngưỡng |
| Data integrity | Không duplicate/loss ngoài policy | Tác dụng phụ lặp hoặc thiếu dữ liệu |

**Tiếp tục** khi các chỉ số nằm trong ngưỡng đã định và canary xác nhận kết quả nghiệp vụ.

**Dừng rollout** khi có tín hiệu bất thường chưa rõ nguyên nhân. Giữ phạm vi ảnh hưởng nhỏ, thu thập trace và kiểm tra boundary.

**Rollback** khi phiên bản mới gây lỗi có thể khắc phục bằng cách quay lại và rollback an toàn. Trước khi rollback, kiểm tra schema/database migration, event đã phát và consumer version. Rollback binary không xóa message mới đã vào broker và không tự đảo ngược tác dụng nghiệp vụ đã commit.

**Roll-forward** có thể phù hợp hơn khi event mới đã được phát hoặc migration không thể đảo ngược. Khi đó, phát hành consumer/adapter tương thích và xử lý backlog theo runbook.

## 18. Quy trình rollback và phục hồi dữ liệu event

Rollback phải xét cả producer, consumer, contract và message đang tồn tại:

- Dừng hoặc giới hạn producer phát schema mới nếu consumer cũ không tương thích.
- Xác định message mới đã nằm trong broker, outbox, registry hoặc DLQ.
- Giữ lại event cần xử lý; không purge để làm sạch backlog.
- Xác nhận consumer cũ có thể đọc event đang chờ.
- Nếu không tương thích, route/quarantine message theo policy.
- Kiểm tra database migration có rollback an toàn không.
- Đối chiếu business effect đã commit trước khi chạy lại.
- Dùng idempotency khi replay hoặc resubmit.
- Sau khi sửa, chạy canary nhỏ rồi mới mở rộng rollout.

Nếu source transaction đã commit nhưng consumer chưa xử lý, rollback producer không tự hủy event đã lưu. Nếu consumer đã tạo tác dụng phụ, cần compensation nghiệp vụ khi thích hợp. Không dùng replay như một cách thay thế cho reconciliation.

## 19. Alert và runbook sau phát hành

Alert nên gắn với triệu chứng ảnh hưởng tới khả năng giao event và kết quả nghiệp vụ, không chỉ CPU hoặc memory.

Các alert có thể gồm:

- Publication incomplete vượt tuổi cho phép.
- Outbox oldest pending age tăng.
- Broker queue depth hoặc consumer lag tăng liên tục.
- Consumer error/deserialization failure tăng.
- DLQ có message mới thuộc event type trọng yếu.
- Publish confirm hoặc routing failure tăng.
- Consumer throughput giảm trong khi input rate không giảm.
- p95/p99 processing latency vượt SLO.
- Database connection pool, lock wait hoặc executor queue bão hòa.
- Business outcome rate giảm so với baseline.

Runbook cho mỗi alert cần nêu owner, dashboard, log/trace query, bước xác định phạm vi, điều kiện retry/replay, điều kiện rollback và cách xác nhận phục hồi. Tránh alert theo một spike đơn lẻ nếu không có ý nghĩa; dùng cửa sổ thời gian và ngưỡng theo SLO để giảm noise.

## 20. Ghi nhận bằng chứng kiểm tra sau phát hành

Mỗi release nên có một record ngắn để biết đã kiểm tra gì và ai chịu trách nhiệm:

| Trường | Nội dung |
|---|---|
| Release | Version, commit/image digest và thời điểm |
| Scope | Module, producer, consumer, event type và schema version |
| Baseline | Khoảng thời gian và dashboard dùng để so sánh |
| Health | Readiness, dependency và instance status |
| Event flow | EventId/correlationId hoặc canary reference |
| Publication | Registry/outbox state và backlog age |
| Broker | Queue/topic, confirm, lag, redelivery, DLQ |
| Consumer | Deserialize, handler result và target state |
| Performance | p95/p99, throughput, heap, database |
| Decision | Continue, pause, rollback hoặc roll-forward |
| Follow-up | Owner, action, deadline và rủi ro còn lại |

Phân biệt rõ PASS, FAIL, NOT CHECKED và NOT APPLICABLE. Không đánh dấu PASS khi chỉ có log publish mà chưa quan sát consumer outcome. Nếu một hệ thống ngoài không thể truy cập trong cửa sổ kiểm tra, ghi NOT CHECKED cùng rủi ro và owner xử lý.

Không đưa payload hoặc dữ liệu cá nhân vào release record. Dùng eventId/correlationId có kiểm soát và liên kết tới log/trace theo quyền truy cập.

## 21. Checklist kiểm tra sau phát hành

### Trước khi bắt đầu kiểm tra

- [ ] Xác định release identifier và các module liên quan.
- [ ] Ghi baseline và SLO cho luồng event.
- [ ] Xác nhận consumer/version/schema tương thích.
- [ ] Xác nhận dashboard, log, trace và alert hoạt động.
- [ ] Xác định canary hoặc smoke test an toàn.

### Sau rollout

- [ ] Instance mới healthy và ready theo cấu hình.
- [ ] Database migration và dependency connection thành công.
- [ ] Producer phát đúng event type/schema version.
- [ ] Transaction commit/rollback đúng semantics.
- [ ] Registry/outbox không có backlog bất thường.
- [ ] Broker routing, confirm, queue/lag và DLQ bình thường.
- [ ] Consumer deserialize và xử lý event thành công.
- [ ] Business effect được commit và ACK/offset phù hợp.
- [ ] Retry, duplicate và idempotency hoạt động đúng.
- [ ] p95/p99, throughput, heap, GC và database trong budget.
- [ ] Security, payload minimization và retention không bị ảnh hưởng.
- [ ] Quyết định rollout được ghi nhận cùng bằng chứng.

## 22. Quy trình kiểm tra sau phát hành theo thứ tự

Một quy trình có thể áp dụng cho mỗi release:

1. Chốt release version, phạm vi event và owner.
2. So sánh baseline trước/sau với cùng time window và filter.
3. Xác nhận rollout, instance version, configuration và migration.
4. Kiểm tra health/readiness cùng dependency.
5. Kiểm tra một luồng event đại diện từ source commit tới target commit.
6. Đối chiếu publication registry hoặc outbox.
7. Kiểm tra broker delivery, routing, lag và consumer membership.
8. Kiểm tra consumer result, inbox/dedup và business outcome.
9. Kiểm tra retry, redelivery, DLQ và publication incomplete.
10. Kiểm tra schema compatibility và event lịch sử cần replay.
11. So sánh latency, throughput, payload, database và JVM resource.
12. Kiểm tra security/data handling và retention.
13. Áp dụng release gate: tiếp tục, dừng, rollback hoặc roll-forward.
14. Ghi bằng chứng, owner và follow-up.
15. Tiếp tục theo dõi backlog và business outcome trong cửa sổ ổn định sau release.

Kiểm tra sau phát hành chỉ hoàn tất khi phiên bản mới không chỉ khởi động thành công mà còn duy trì được luồng event và kết quả nghiệp vụ theo SLO. Hãy lần theo từng boundary từ producer tới consumer, đối chiếu registry/outbox và broker, kiểm tra duplicate/retry/schema, rồi so sánh hiệu năng với baseline. Quyết định rollout cần dựa trên bằng chứng và có tính đến event đã commit hoặc đang chờ, vì rollback ứng dụng không tự đảo ngược dữ liệu và message đã phát.

