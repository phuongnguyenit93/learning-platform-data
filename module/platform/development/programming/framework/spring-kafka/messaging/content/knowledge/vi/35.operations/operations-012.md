# Runbook cho sự cố messaging

Một sự cố Kafka có thể biểu hiện ở nhiều nơi: producer không gửi được record, broker từ chối request, consumer group mất partition assignment, listener xử lý chậm, offset không tiến, retry tăng hoặc dead-letter topic tích tụ. Nếu chỉ nhìn một log lỗi rồi thay đổi cấu hình ngay, đội vận hành có thể làm mất dữ liệu, tạo duplicate hoặc khiến phạm vi ảnh hưởng rộng hơn.

Runbook là quy trình giúp đội vận hành phản ứng có thứ tự: xác nhận tác động, khoanh vùng thành phần lỗi, thu thập bằng chứng, chọn biện pháp giảm ảnh hưởng, khôi phục luồng và xác minh kết quả. Với Spring Kafka, cần xem cả Kafka client, listener container, error handler, serializer/deserializer, transaction và dependency nghiệp vụ.

Bài học thuộc chương **Vận hành** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách xây dựng và sử dụng runbook cho sự cố messaging trong ứng dụng Spring Kafka.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Phân loại sự cố theo producer, broker, topic/partition, consumer, listener và dependency.
- Xác định mức độ ảnh hưởng và phạm vi sự cố.
- Thu thập log, metric, topic metadata, consumer group và offset trước khi thay đổi hệ thống.
- Chẩn đoán producer send failure, consumer lag, rebalance, serialization error và DLT backlog.
- Chọn biện pháp mitigation an toàn, có thể đảo ngược.
- Tránh reset offset, xóa topic hoặc replay hàng loạt khi chưa đánh giá tác động.
- Khôi phục consumer group và xác minh luồng dữ liệu đã ổn định.
- Xử lý dead-letter record và replay có kiểm soát.
- Biết khi nào cần escalation tới đội Kafka platform, network, security hoặc nghiệp vụ.
- Ghi nhận timeline, quyết định và bài học sau sự cố.

## 1. Runbook và phạm vi của nó

Runbook là hướng dẫn thao tác cụ thể cho một tình huống vận hành. Một runbook tốt phải cho người trực biết:

1. Dấu hiệu nào kích hoạt quy trình.
2. Dữ liệu nào cần kiểm tra trước.
3. Lệnh hoặc dashboard nào giúp khoanh vùng.
4. Điều kiện nào xác nhận giả thuyết.
5. Biện pháp nào được phép thực hiện.
6. Điều kiện dừng hoặc escalation.
7. Cách xác minh sau khôi phục.
8. Ai chịu trách nhiệm và cần ghi nhận điều gì.

Runbook không thay thế kiến thức hệ thống hoặc quyền phê duyệt. Với thao tác có thể làm mất dữ liệu, thay đổi semantics hoặc ảnh hưởng nhiều consumer, người trực cần theo change/incident policy của tổ chức.

Phạm vi bài này là pipeline Spring Kafka điển hình:

~~~text
Producer service
      |
      v
Kafka broker / topic / partition
      |
      v
Consumer group / listener container
      |
      v
Business service / database / downstream
      |
      +---- retry / recovery / DLT
~~~

Một sự cố có thể nằm ở một thành phần hoặc lan qua nhiều thành phần. Ví dụ database chậm làm listener kéo dài, consumer lag tăng, poll loop bị ảnh hưởng và retry bắt đầu xuất hiện.

## 2. Bắt đầu incident: xác nhận tác động trước khi sửa

Khi nhận cảnh báo hoặc báo cáo từ người dùng, trước tiên xác định:

- Service nào bị ảnh hưởng.
- Topic và consumer group liên quan.
- Sự cố bắt đầu lúc nào.
- Có bao nhiêu record bị chậm, lỗi hoặc không được xử lý.
- Có mất dữ liệu được xác nhận hay mới chỉ là backlog.
- Tác động nghiệp vụ: đơn hàng chậm, tồn kho không cập nhật, thông báo không gửi, hay audit bị thiếu.
- Sự cố ảnh hưởng một partition, một topic hay toàn cluster.
- Có thay đổi triển khai, cấu hình, secret, ACL hoặc hạ tầng gần thời điểm bắt đầu không.

Không kết luận “mất message” chỉ từ việc consumer lag tăng. Lag thường cho biết consumer chưa xử lý/commit tới log end offset; record có thể vẫn nằm trong retention và có thể được tiêu thụ sau khi phục hồi.

Tạo một incident timeline với mốc thời gian, quan sát, thao tác và kết quả. Ghi lại timezone thống nhất (thường UTC) để đối chiếu log producer, broker và consumer.

## 3. Phân loại mức độ nghiêm trọng

Có thể dùng ma trận mức độ sau và điều chỉnh theo chính sách tổ chức:

| Mức | Tình huống tham khảo | Hành động |
|---|---|---|
| SEV-1 | Mất khả năng gửi/nhận trên diện rộng, partition offline diện rộng, nghi ngờ mất dữ liệu hoặc ảnh hưởng nghiệp vụ nghiêm trọng | Kích hoạt incident process, chỉ định incident lead, escalation ngay. |
| SEV-2 | Một luồng nghiệp vụ quan trọng ngừng xử lý, lag tăng nhanh, DLT/retry tăng mạnh | Điều phối owner service và Kafka platform, giảm tác động sớm. |
| SEV-3 | Một số partition hoặc tenant bị ảnh hưởng, throughput giảm nhưng có workaround | Theo dõi, xử lý theo runbook và cập nhật owner. |
| SEV-4 | Cảnh báo nhỏ, lỗi đơn lẻ hoặc vấn đề chưa ảnh hưởng nghiệp vụ | Ghi nhận, điều tra theo lịch và theo dõi xu hướng. |

Mức độ phải dựa trên tác động nghiệp vụ, phạm vi, thời gian phục hồi dự kiến và rủi ro dữ liệu; không chỉ dựa vào số lượng log lỗi.

## 4. Quy trình triage tổng quát

~~~mermaid
flowchart TD
    A[Alert or incident report] --> B[Confirm service, topic, group and business impact]
    B --> C[Capture logs, metrics and timestamps]
    C --> D{Where is the failure?}
    D -->|Producer| E[Check send errors, broker reachability and ACL]
    D -->|Broker/topic| F[Check partitions, leaders, ISR and broker health]
    D -->|Consumer| G[Check group state, assignment, lag and listener]
    D -->|Payload| H[Check serializer, schema and headers]
    D -->|Recovery| I[Check retry, DLT and recoverer]
    E --> J[Choose reversible mitigation]
    F --> J
    G --> J
    H --> J
    I --> J
    J --> K[Verify processing and business outcome]
    K --> L[Monitor stability and close incident]
~~~

Thứ tự quan trọng:

1. Thu thập bằng chứng trước khi restart hoặc thay đổi cấu hình.
2. Xác định lỗi có tái diễn hay chỉ là sự kiện tạm thời.
3. Kiểm tra phạm vi bằng topic, partition, group và event ID.
4. Chọn mitigation nhỏ nhất có thể giảm tác động.
5. Sau mỗi thay đổi, đo lại metric và xác minh nghiệp vụ.
6. Nếu chưa có bằng chứng hoặc thao tác vượt quyền, escalation thay vì thử ngẫu nhiên.

## 5. Bộ thông tin tối thiểu cần thu thập

Trước khi chẩn đoán, ghi lại:

| Nhóm | Thông tin |
|---|---|
| Ứng dụng | Service name, version, instance/pod, deployment time. |
| Kafka | Cluster, bootstrap endpoint, broker version nếu biết. |
| Luồng | Topic, partition, consumer group, transactional ID nếu có. |
| Record | Event ID/correlation ID, key đã mask, timestamp, source offset nếu biết. |
| Thời gian | Thời điểm bắt đầu, lần lỗi gần nhất, timezone. |
| Producer | Send rate, ack latency, error/timeout rate. |
| Consumer | Assignment, lag theo partition, processing latency, retry count. |
| Recovery | DLT backlog, exception class, số record chờ xử lý. |
| Hạ tầng | CPU, memory, GC, disk, network, database/downstream health. |
| Thay đổi gần đây | Release, config, ACL, secret rotation, broker maintenance. |

Bảo vệ dữ liệu nhạy cảm. Không đính kèm password, JAAS config đầy đủ, bearer token, payload chứa dữ liệu cá nhân hoặc private key vào incident ticket.

## 6. Các dashboard và metric cần xem đầu tiên

Một dashboard messaging cơ bản nên có:

- Producer acknowledged rate, failed rate và send latency p95/p99.
- Producer request latency, retries và buffer pool wait.
- Consumer records consumed rate và listener processing p95/p99.
- Consumer lag theo topic/partition/group.
- Consumer group member count và partition assignment.
- Rebalance rate hoặc số lần partition revoke/assign.
- Listener error, retry và recovery rate.
- DLT incoming rate, backlog và consumer lag.
- Broker offline partitions, under-replicated partitions và ISR shrink.
- CPU, heap, GC, network và disk của application/broker.
- Database connection pool, query latency và downstream HTTP error/latency.

Đối chiếu cùng một time window. Nếu lag bắt đầu tăng đúng lúc database latency tăng, dependency có thể là nguyên nhân gốc; restart consumer có thể chỉ làm gián đoạn thêm mà không khắc phục bottleneck.

## 7. Runbook A: Producer không gửi được record

**Triệu chứng**

- `KafkaTemplate.send()` future hoàn tất exceptionally.
- Producer timeout hoặc retry tăng.
- Log có `TimeoutException`, `NotLeaderOrFollowerException`, `RecordTooLargeException`, `TopicAuthorizationException` hoặc lỗi serialization.

**Kiểm tra**

1. Xác nhận bootstrap server và DNS/network từ đúng application instance.
2. Kiểm tra broker có hoạt động và listener đúng port/protocol.
3. Xác minh topic tồn tại, partition có leader.
4. Kiểm tra SASL/TLS authentication và ACL WRITE/DESCRIBE.
5. Kiểm tra serializer, payload size và broker/topic message size limit.
6. Kiểm tra producer acks, retry, delivery timeout và buffer wait.
7. Đối chiếu broker log và producer exception theo cùng timestamp.

Lệnh kiểm tra topic:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --describe --topic orders.created
~~~

**Mitigation**

- Nếu broker/network outage: chuyển incident cho Kafka/network owner và giữ producer retry trong giới hạn cấu hình.
- Nếu ACL sai: cấp đúng quyền cho principal theo quy trình security.
- Nếu topic không tồn tại: xác minh cluster và provisioning trước khi tạo.
- Nếu payload quá lớn: xác minh contract và giới hạn trước khi thay đổi message size; cân nhắc lưu payload lớn ngoài Kafka và gửi reference.
- Nếu serialization lỗi: rollback release hoặc khôi phục serializer/contract tương thích.

Không tăng retry hoặc delivery timeout vô hạn để che lỗi broker. Retry kéo dài có thể giữ buffer và làm tăng latency toàn service.

**Xác minh**

- Send future hoàn tất thành công.
- Broker ghi nhận record ở topic/partition mong đợi.
- Producer error rate trở về baseline.
- Consumer xử lý được record theo event ID.
- Không tạo duplicate nghiệp vụ khi producer retry.

## 8. Runbook B: Consumer lag tăng

**Triệu chứng**

- Lag của một hoặc nhiều partition tăng liên tục.
- Consumer throughput thấp hơn producer throughput.
- Business event đến downstream chậm.
- Listener processing latency hoặc dependency latency tăng.

**Kiểm tra**

~~~bash
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 --describe --group orders-fulfillment
~~~

Kiểm tra:

1. Group có member active không.
2. Mỗi partition được assign cho consumer nào.
3. Lag tăng ở tất cả partition hay chỉ một partition.
4. Listener có exception, retry hoặc bị block không.
5. Database/HTTP dependency có chậm hoặc hết connection pool không.
6. Consumer concurrency có phù hợp partition count không.
7. Có rebalance liên tục hoặc poll timeout không.
8. Consumer có commit offset sau khi xử lý không.

**Cách diễn giải**

- Lag tăng đều trên mọi partition: consumer capacity hoặc downstream có thể không đủ.
- Một partition lag vượt trội: kiểm tra hot key, xử lý lâu hoặc partition-specific issue.
- Consumer member không có assignment: kiểm tra subscription, group protocol, concurrency và rebalance.
- Lag tăng cùng retry/DLT: điều tra record lỗi hoặc dependency.
- Lag tăng nhưng listener timer thấp: kiểm tra thời gian chờ trước listener, fetch, commit, rebalance và metric coverage.

**Mitigation**

- Khôi phục dependency đang chậm trước khi tăng consumer concurrency.
- Tăng replica/instance hoặc concurrency chỉ khi còn partition và downstream capacity.
- Tạm giảm tốc producer nếu hệ thống upstream hỗ trợ backpressure.
- Tạm pause luồng có kiểm soát nếu downstream đang gặp sự cố và retention còn đủ.
- Nếu một key nóng, xử lý nguyên nhân phân bố key; không đổi partitioning tùy tiện trong incident.

**Xác minh**

- Lag giảm theo xu hướng bền vững.
- Consumer throughput đạt hoặc vượt tốc độ sản xuất trong giai đoạn drain.
- Không còn rebalance bất thường.
- Business state được cập nhật và không có duplicate side effect.

## 9. Runbook C: Consumer group rebalance liên tục

**Triệu chứng**

- Partition thường xuyên bị revoke rồi assign lại.
- Consumer log có `CommitFailedException`, `RebalanceInProgressException`, `FencedInstanceIdException` hoặc thông báo heartbeat/session timeout.
- Lag tăng trong khi throughput giảm.

**Kiểm tra**

- Instance/pod có restart, crash hoặc OOM không.
- Listener xử lý lâu hơn `max.poll.interval.ms` không.
- Consumer có gọi dependency blocking trong poll thread không.
- `session.timeout.ms`, `heartbeat.interval.ms` và `max.poll.interval.ms` có tương thích không.
- Có nhiều consumer instance dùng cùng static membership identity không.
- Có deployment/scale event hoặc network flap không.
- Partition assignment có thay đổi do topic/subscription update không.

**Mitigation**

- Khắc phục crash, OOM, network instability hoặc dependency block.
- Nếu processing time thực sự dài, xem lại batch size, concurrency và thiết kế xử lý; chỉ điều chỉnh max poll interval sau khi hiểu tác động.
- Loại bỏ static member ID trùng hoặc cấu hình identity theo instance đúng cách.
- Triển khai rollout theo chiến lược giảm gián đoạn nếu rebalance bắt nguồn từ deploy.

Không tăng session timeout/max poll interval một cách tùy tiện. Cấu hình quá lớn có thể kéo dài thời gian phát hiện consumer chết hoặc che việc listener bị treo.

**Xác minh**

- Group membership ổn định.
- Số lần rebalance giảm về baseline.
- Assignment không dao động liên tục.
- Lag và processing latency phục hồi.

## 10. Runbook D: Serialization hoặc deserialization failure

**Triệu chứng**

- Producer báo serialization exception.
- Consumer không tạo được object từ record.
- Listener không được gọi dù record vẫn nằm trong topic.
- Error handler hoặc DLT nhận record lỗi.
- Log có lỗi JSON parse, class resolution, schema mismatch hoặc type mapping.

**Kiểm tra**

1. Xác định lỗi xảy ra ở producer serializer hay consumer deserializer.
2. Lấy topic, partition, offset và event ID.
3. Kiểm tra serializer/deserializer đang được cấu hình trên đúng factory.
4. Kiểm tra payload bytes, content type, type header và schema/version.
5. Kiểm tra class/package mapping, trusted packages và default target type.
6. Xác định producer/consumer version đã rollout gần thời điểm lỗi.
7. Nếu có DLT, giữ raw key/value và headers để điều tra.

**Mitigation**

- Nếu release mới phát payload không tương thích: rollback producer hoặc phát lại contract tương thích.
- Nếu consumer thiếu mapping/type: triển khai consumer hỗ trợ token/type mới trước khi producer tiếp tục phát.
- Nếu payload hỏng: cách ly record, không sửa bytes theo suy đoán.
- Nếu lỗi schema: kiểm tra backward/forward compatibility và kế hoạch rollout.
- Dùng DLT/recovery theo chính sách thay vì bỏ qua poison pill.

Không deserialize thủ công một payload không rõ nguồn bằng class tùy ý. Type header là metadata do producer gửi, không phải bằng chứng tin cậy để load bất kỳ class nào.

**Xác minh**

- Consumer deserialize được record thử nghiệm.
- Error rate và DLT incoming rate trở về baseline.
- Raw record lỗi vẫn được bảo toàn cho audit.
- Consumer cũ/mới tương thích với payload trong thời gian rollout.

## 11. Runbook E: Retry tăng hoặc listener xử lý thất bại

**Triệu chứng**

- Listener exception tăng.
- Retry/backoff kéo dài.
- Processing throughput giảm.
- Consumer lag tăng.
- Cùng event ID xuất hiện nhiều attempt.

**Kiểm tra**

- Exception class và root cause.
- Record có lỗi dữ liệu cố định hay dependency tạm thời.
- Retryable/non-retryable classification có đúng không.
- Retry topic hay blocking retry đang được dùng.
- Database transaction có rollback đúng không.
- Listener có side effect idempotent không.
- Error handler có đang recover quá sớm hoặc retry vô hạn không.

**Mitigation**

- Dependency tạm thời: khôi phục dependency, giữ retry có giới hạn.
- Payload/validation lỗi cố định: chuyển DLT và xử lý theo workflow.
- Lỗi code sau release: rollback hoặc deploy fix tương thích.
- Retry storm: giảm tốc hoặc dừng luồng có kiểm soát theo runbook để bảo vệ downstream.
- Bảo đảm side effect idempotent trước khi redelivery/replay.

Không tăng số lần retry cho lỗi không thể phục hồi như schema không tương thích hoặc validation vĩnh viễn. Điều đó chỉ làm tăng backlog và kéo dài thời gian xử lý.

**Xác minh**

- Retry rate trở về baseline.
- Listener success rate phục hồi.
- DLT backlog không tăng ngoài dự kiến.
- Event ID không tạo side effect trùng.

## 12. Runbook F: Dead-letter topic backlog tăng

**Triệu chứng**

- DLT incoming rate tăng.
- DLT consumer lag hoặc backlog tăng.
- Exception class tập trung vào một loại lỗi.
- Record cũ chưa được phân loại hoặc chưa có owner.

**Kiểm tra**

1. Xác định source topic, partition và original offset qua DLT headers.
2. Phân loại exception và thời điểm bắt đầu.
3. Kiểm tra raw payload có thể deserialize không.
4. Tìm nguyên nhân gốc: code, schema, dependency, config hay business rule.
5. Xác định event có side effect đã thực hiện một phần chưa.
6. Kiểm tra DLT retention, storage và consumer group.
7. Xác định owner và trạng thái từng case.

**Mitigation**

- Sửa nguyên nhân trước khi replay.
- Lưu raw payload và headers vào kho quarantine có kiểm soát.
- Replay thử một record hoặc batch nhỏ.
- Giữ event ID, correlation ID và key cần thiết.
- Gắn replay ID và audit trail.
- Dùng idempotency để tránh lặp side effect.
- Giới hạn tốc độ và số lượng record replay.

Không replay toàn bộ DLT khi nguyên nhân chưa được sửa. Không xóa DLT để giảm backlog; việc đó có thể làm mất bằng chứng và dữ liệu cần khôi phục.

**Xác minh**

- Record thử nghiệm xử lý thành công.
- DLT incoming rate giảm.
- Backlog được xử lý theo kế hoạch.
- Source metadata và replay audit được lưu.
- Business state được đối chiếu trước/sau replay.

## 13. Runbook G: Partition offline hoặc under-replicated

**Triệu chứng**

- Producer timeout hoặc lỗi leader unavailable.
- Topic describe cho thấy leader là -1/không có leader.
- ISR nhỏ hơn replication factor.
- Broker cảnh báo disk, network hoặc log directory.

**Kiểm tra**

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --describe --topic orders.created
~~~

Kiểm tra:

- Broker nào offline hoặc vừa restart.
- Leader/replica/ISR của từng partition.
- Disk usage, I/O error và log directory.
- Network broker-to-broker.
- Controller/quorum health.
- Reassignment hoặc recovery đang chạy.
- Producer acks và min.insync.replicas.

**Mitigation**

- Chuyển incident cho Kafka platform owner nếu cluster health bị ảnh hưởng.
- Khôi phục broker/disk/network theo quy trình platform.
- Theo dõi follower bắt kịp và ISR phục hồi.
- Không tự ép leader election hoặc thay min ISR để che tình trạng.
- Không bật unclean leader election nếu chưa đánh giá rõ nguy cơ mất dữ liệu và có quyền phê duyệt.

**Xác minh**

- Partition có leader hợp lệ.
- ISR phục hồi theo replication factor mong muốn.
- Offline/under-replicated metrics trở về baseline.
- Producer/consumer request thành công và lag ổn định.

## 14. Runbook H: Authentication, authorization hoặc TLS failure

**Triệu chứng**

- Client không kết nối được broker.
- Log có `SaslAuthenticationException`, `SSLHandshakeException`, `TopicAuthorizationException` hoặc `GroupAuthorizationException`.

**Kiểm tra**

- Bootstrap endpoint và listener protocol.
- SASL mechanism, username, password/token và JAAS config.
- Secret vừa rotation hay hết hạn không.
- Broker certificate, truststore và hostname verification.
- Principal thực tế của client.
- ACL trên topic, consumer group, transactional ID hoặc cluster operation.

**Mitigation**

- Khôi phục secret hợp lệ qua secret manager.
- Nếu certificate hết hạn, thay certificate theo quy trình platform.
- Cấp đúng ACL tối thiểu cho principal.
- Restart/recreate client nếu mechanism yêu cầu reload credential.
- Không tắt TLS hostname verification hoặc chuyển sang PLAINTEXT để né lỗi production.

**Xác minh**

- Producer/consumer/AdminClient xác thực bằng principal đúng.
- Topic/group operation được cấp quyền hoạt động.
- Negative test vẫn bị từ chối khi principal không có quyền.
- Secret không xuất hiện trong log hoặc incident ticket.

## 15. Runbook I: Transaction abort, fencing hoặc commit failure

**Triệu chứng**

- Transaction commit/abort rate tăng.
- Log có `ProducerFencedException`, transaction timeout hoặc coordinator error.
- Consumer redelivery sau rollback.
- Output không xuất hiện với consumer read_committed.

**Kiểm tra**

- Transactional ID/prefix có duy nhất theo application instance không.
- Có pod cũ và pod mới cùng sử dụng transactional ID không.
- Transaction duration có vượt timeout không.
- Listener có thực hiện công việc chậm trong transaction không.
- KafkaTransactionManager và KafkaTemplate có cùng tham gia transaction không.
- Consumer downstream có `isolation.level=read_committed` khi cần không.

**Mitigation**

- Loại bỏ instance cũ hoặc transactional ID collision theo lifecycle deployment.
- Khắc phục transaction kéo dài; không chỉ tăng timeout.
- Rollback release nếu cấu hình transaction manager sai.
- Cho phép after-rollback/retry theo chính sách.
- Kiểm tra external side effect riêng vì Kafka transaction không rollback database hoặc HTTP.

**Xác minh**

- Transaction commit/abort rate trở về bình thường.
- Producer fencing không tái diễn.
- Output và input offset nhất quán trong Kafka transaction.
- Side effect ngoài Kafka được đối chiếu và idempotent.

## 16. Runbook J: Consumer không commit offset

**Triệu chứng**

- Listener đã chạy nhưng committed offset không tiến.
- Record bị giao lại sau restart.
- Lag không giảm dù listener log có xử lý thành công.

**Kiểm tra**

- AckMode đang dùng: RECORD, BATCH, MANUAL hoặc MANUAL_IMMEDIATE.
- Listener có gọi acknowledgment trong manual mode không.
- Error handler có seek/redeliver hoặc recovery không.
- Transaction có commit hay rollback.
- Auto commit có bị bật ngoài dự kiến không.
- Consumer group có rebalance hoặc mất ownership partition không.
- Offset commit có bị ACL từ chối không.

**Mitigation**

- Sửa acknowledgment flow hoặc cấu hình container.
- Khôi phục quyền commit/group nếu ACL sai.
- Sửa transaction manager/producer fencing nếu transaction abort.
- Đảm bảo listener side effect idempotent trước khi để record redeliver.

Không reset offset để làm lag về zero nếu chưa xác định record nào chưa xử lý. Reset có thể bỏ qua dữ liệu hoặc tạo duplicate lớn.

**Xác minh**

- Committed offset tiến đúng theo partition.
- Listener không còn redelivery ngoài dự kiến.
- Business side effect khớp với event ID đã xử lý.
- Consumer lag giảm về baseline.

## 17. Các thao tác cần kiểm soát đặc biệt

Những thao tác sau có thể làm thay đổi dữ liệu hoặc semantics đáng kể:

| Thao tác | Rủi ro | Điều kiện trước khi thực hiện |
|---|---|---|
| Reset consumer group offset | Bỏ qua hoặc đọc lại record | Xác định offset mục tiêu, phạm vi partition, backup/approval và replay plan. |
| Xóa topic | Mất dữ liệu và thay đổi offset/history | Có phê duyệt, xác nhận retention/archive và kế hoạch migration. |
| Replay toàn bộ DLT | Duplicate side effect, đảo thứ tự | Sửa root cause, idempotency, batch limit, audit và owner. |
| Tăng partition | Thay đổi key-to-partition mapping và ordering | Đánh giá key/order contract và consumer capacity. |
| Giảm min ISR | Giảm durability | Đánh giá mất broker và phê duyệt risk. |
| Bật unclean leader election | Có thể mất record chưa replicate | Chỉ theo quyết định platform có hiểu rõ trade-off. |
| Tăng retry/backoff | Tăng thời gian backlog và tải dependency | Xác định lỗi retryable và capacity. |
| Tắt TLS/ACL | Mở rộng rủi ro bảo mật | Không dùng như workaround production. |

Runbook phải nêu rõ ai được thực hiện, ai phê duyệt và cách rollback. Nếu không có quyền hoặc thiếu bằng chứng, dừng tại bước thu thập thông tin và escalation.

## 18. Xác minh phục hồi sau mitigation

Không đóng incident chỉ vì log lỗi ngừng xuất hiện. Cần kiểm tra nhiều lớp:

1. **Broker health**: broker hoạt động, partition có leader, ISR ổn định.
2. **Producer**: send acknowledgement thành công, error/timeout giảm.
3. **Consumer group**: member ổn định, partition assignment đúng.
4. **Throughput/lag**: consumer xử lý theo kịp tải, backlog giảm bền vững.
5. **Listener**: processing success tăng, retry/error giảm.
6. **DLT**: incoming rate ổn định, backlog có owner và kế hoạch.
7. **Business state**: database/downstream phản ánh đúng event đã xử lý.
8. **Data integrity**: kiểm tra duplicate, missing event và ordering theo event ID/aggregate.
9. **Security**: principal/ACL/TLS được khôi phục đúng.
10. **Monitoring**: dashboard và alert trở về baseline trong khoảng quan sát đã thống nhất.

Nếu producer rate thấp vì upstream đang dừng, lag giảm về zero không chứng minh consumer đã phục hồi capacity. Hãy xác minh bằng tải bình thường hoặc replay canary được kiểm soát.

## 19. Escalation và quyền sở hữu

Một sự cố messaging thường cần nhiều owner:

| Nhóm | Khi cần escalation |
|---|---|
| Application owner | Listener code, serializer, business validation, release regression. |
| Kafka platform | Broker offline, partition leader, ISR, controller/quorum, reassignment. |
| Network/platform | DNS, routing, firewall, packet loss, connection reset. |
| Security/IAM | SASL, TLS certificate, secret rotation, ACL. |
| Database/downstream | Connection pool, query latency, dependency outage. |
| Business owner | Quyết định replay, bỏ record, bù trừ hoặc xử lý trạng thái nghiệp vụ. |

Khi escalation, gửi thông tin có thể hành động:

- Incident ID và severity.
- Service/version/instance.
- Cluster, topic, partition, group.
- UTC time window.
- Error class và message đã loại secret.
- Metrics/screenshot/dashboard link theo chính sách.
- Các thao tác đã thực hiện và kết quả.
- Tác động nghiệp vụ và quyết định đang cần.

Không gửi raw payload hoặc credential vào kênh không được phép.

## 20. Mẫu incident timeline và handoff

Có thể dùng mẫu sau trong incident ticket:

~~~text
Incident ID:
Severity:
Incident lead:
Service / version:
Kafka cluster:
Topic / partition:
Consumer group:
First observed (UTC):
Business impact:

Timeline:
- HH:MM UTC - Alert fired:
- HH:MM UTC - Scope confirmed:
- HH:MM UTC - Evidence collected:
- HH:MM UTC - Mitigation applied:
- HH:MM UTC - Recovery verified:

Current metrics:
- Producer error rate:
- Consumer throughput:
- Consumer lag by partition:
- Listener p95/p99:
- Retry / DLT backlog:
- Broker offline / under-replicated partitions:

Root cause (known / suspected):
Actions taken:
Data integrity checks:
Outstanding risks:
Escalation owner:
Next update:
~~~

Trong quá trình incident, cập nhật timeline theo thời gian thực. Phân biệt rõ dữ kiện đã xác minh với giả thuyết. Khi bàn giao ca trực, nêu trạng thái hiện tại, thao tác đang chạy, điểm cần theo dõi và người chịu trách nhiệm tiếp theo.

## 21. Post-incident review

Sau khi hệ thống phục hồi, thực hiện review để giảm khả năng tái diễn:

- Viết timeline chính xác và phạm vi ảnh hưởng.
- Xác định root cause và các yếu tố góp phần.
- Đánh giá phát hiện: alert có đủ sớm không, dashboard có đủ dữ liệu không.
- Xem mitigation nào hiệu quả và thao tác nào làm tăng rủi ro.
- Kiểm tra data integrity: missing, duplicate, ordering và DLT.
- Cập nhật runbook, dashboard, alert threshold và owner.
- Tạo action item có người phụ trách và deadline.
- Bổ sung integration/load/failure test cho tình huống đã xảy ra.
- Kiểm tra quy trình secret rotation, deploy hoặc topic provisioning nếu liên quan.

Review nên tập trung vào hệ thống và quy trình, không quy lỗi cho cá nhân. Mục tiêu là làm cho lần sau phát hiện sớm hơn và phục hồi an toàn hơn.

## 22. Bài tập tổng hợp: diễn tập sự cố Order Messaging

Giả sử Order Service gửi vào `orders.created`; Fulfillment consumer xử lý rồi ghi database. Trong diễn tập, consumer lag tăng, listener retry và DLT bắt đầu có record.

Yêu cầu:

1. Tạo incident ticket với severity, owner và UTC timeline.
2. Ghi nhận service version, topic, partition và group ID.
3. Thu thập producer send error/latency, consumer throughput/lag và listener processing latency.
4. Dùng Kafka CLI kiểm tra topic partition, leader, replicas và ISR.
5. Dùng consumer group describe để xác định partition lag cao.
6. Kiểm tra listener exception, database latency và connection pool.
7. Phân loại record lỗi là transient, permanent hay data/schema issue.
8. Xác định record nào được retry và record nào vào DLT.
9. Đề xuất mitigation nhỏ nhất, có thể đảo ngược.
10. Chỉ replay một record canary sau khi root cause đã được sửa.
11. Xác minh event ID, idempotency và business state.
12. Theo dõi lag, retry, DLT và throughput trong khoảng ổn định.
13. Viết handoff cho ca trực tiếp theo.
14. Tổ chức post-incident review và tạo action item.

Bài tập hoàn thành khi đội vận hành có thể xác định phạm vi, khoanh vùng nguyên nhân, giảm tác động, phục hồi luồng và chứng minh dữ liệu nghiệp vụ không bị mất hoặc xử lý trùng ngoài dự kiến.

## 23. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Incident basics | Severity, impact, timeline | Mô tả đúng tác động và phạm vi. |
| 2. Evidence | Logs, metrics, topic/group metadata | Thu thập đủ dữ kiện trước khi sửa. |
| 3. Producer | Send failure, timeout, ACL, serializer | Khoanh vùng lỗi publish. |
| 4. Consumer | Lag, assignment, rebalance, offset | Xác định partition và group bị ảnh hưởng. |
| 5. Payload | Serialization, schema, type headers | Xử lý poison pill và compatibility. |
| 6. Recovery | Retry, DLT, replay | Replay có kiểm soát và idempotent. |
| 7. Broker | Leader, ISR, offline partition | Phối hợp platform khôi phục cluster. |
| 8. Security/transaction | SASL, TLS, ACL, fencing | Phân biệt auth, authorization và transaction errors. |
| 9. Mitigation | Safe actions and escalation | Chọn hành động nhỏ, có thể đảo ngược. |
| 10. Verification | Throughput, lag, business integrity | Chứng minh luồng và dữ liệu đã phục hồi. |
| 11. Review | Timeline, root cause, action items | Cập nhật runbook và phòng ngừa tái diễn. |

Bài học hoàn thành khi bạn có thể dùng runbook để xử lý một sự cố từ lúc nhận alert tới khi xác minh phục hồi: biết thu thập bằng chứng, phân biệt lỗi producer/broker/consumer, xử lý retry và DLT, chọn mitigation an toàn, escalation đúng owner và kiểm tra tính toàn vẹn dữ liệu.

Một runbook tốt giúp đội vận hành hành động nhất quán dưới áp lực. Hãy xác nhận tác động, thu thập dữ liệu trước khi thay đổi, khôi phục theo từng bước nhỏ và chỉ đóng incident khi cả Kafka pipeline lẫn kết quả nghiệp vụ đều đã được xác minh.

