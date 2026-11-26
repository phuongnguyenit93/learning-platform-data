# Checklist độ tin cậy

Application events trong **SPRING_MODULITH_APPLICATION_EVENTS** giúp các module phản ứng với sự kiện nghiệp vụ qua contract, nhưng độ tin cậy không tự xuất hiện khi gọi publish. Một luồng event chỉ đáng tin cậy khi hệ thống xác định rõ thời điểm event được tạo, nơi publication được lưu, ai chịu trách nhiệm xử lý, cách phục hồi khi lỗi, cách ngăn tác dụng phụ trùng và cách chứng minh event đã đi tới kết quả nghiệp vụ.

**Checklist độ tin cậy** là tập hợp câu hỏi để review thiết kế, triển khai, kiểm thử, phát hành và vận hành event flow. Checklist cần được áp dụng theo rủi ro của từng luồng. Một event chỉ cập nhật analytics có thể chấp nhận xử lý trễ và rebuild projection; event liên quan thanh toán, tồn kho hoặc quyền truy cập cần kiểm soát chặt hơn về duplicate, ordering, audit và phục hồi.

Không có một cấu hình chung phù hợp cho mọi event. Hãy xác định business invariant, delivery semantics, SLO và failure recovery trước khi chọn listener, registry, outbox hoặc broker.

## 1. Xác định mục tiêu độ tin cậy

Trước khi kiểm tra implementation, hãy viết rõ điều gì phải đúng đối với event.

- Event chỉ được phát khi sự kiện nghiệp vụ thực sự xảy ra.
- Event không bị mất trong cửa sổ giữa commit dữ liệu nguồn và publish message.
- Consumer có thể phục hồi sau restart hoặc dependency outage.
- Duplicate delivery không tạo tác dụng phụ nghiệp vụ trùng.
- Event không được xử lý sai thứ tự nếu thứ tự có ý nghĩa.
- Payload được consumer hỗ trợ và có semantics ổn định.
- Lỗi permanent được cách ly để không retry vô hạn.
- Người vận hành có thể phát hiện backlog, failure và publication bị kẹt.
- Có cách replay hoặc reconcile mà không làm hỏng dữ liệu.
- Mỗi boundary có owner và runbook.

Không dùng một mục tiêu mơ hồ như “event phải exactly once”. Hãy mô tả hành vi cần đạt. Ví dụ: “Mỗi OrderConfirmed có thể được giao nhiều lần, nhưng Inventory chỉ tạo một reservation cho một event identity và có thể đối soát trạng thái sau restart.”

## 2. Chọn delivery semantics phù hợp

Delivery semantics ảnh hưởng trực tiếp tới thiết kế consumer và cách xử lý lỗi.

| Semantics | Ý nghĩa | Điều cần bảo vệ |
|---|---|---|
| At-most-once | Có thể mất event nhưng không giao lại | Chỉ dùng khi mất dữ liệu được chấp nhận |
| At-least-once | Event được giao lại cho tới khi hoàn tất theo policy | Consumer phải idempotent |
| Effectively-once business effect | Có thể giao nhiều lần nhưng tác dụng nghiệp vụ chỉ xảy ra một lần theo identity | Atomic deduplication và business state |
| Ordered processing | Event được xử lý theo thứ tự được xác định | Partition/key, sequence hoặc concurrency control |

Đừng suy ra delivery guarantee từ tên annotation hoặc việc dùng broker. Guarantee thực tế phụ thuộc producer transaction, persistence, broker confirm, consumer acknowledgement, offset commit, retry và idempotency.

Với nhiều hệ thống, at-least-once kết hợp idempotent consumer là lựa chọn thực tế. “Exactly once” ở một lớp transport không đồng nghĩa mọi side effect ngoài database cũng chỉ xảy ra một lần.

## 3. Checklist transaction ở producer

Event phải phản ánh một sự kiện nghiệp vụ đã được xác nhận. Kiểm tra ranh giới transaction giữa thay đổi nguồn và publish:

- [ ] Event chỉ được tạo sau khi domain invariant được kiểm tra.
- [ ] Payload phản ánh state hợp lệ của aggregate tại thời điểm phát.
- [ ] Event được publish trong đúng application use case.
- [ ] Transaction boundary được xác định và kiểm thử.
- [ ] Nếu transaction rollback, listener AFTER_COMMIT không thực hiện side effect.
- [ ] Không publish event thành công nghiệp vụ trước khi dữ liệu nguồn commit nếu contract yêu cầu fact đã xảy ra.
- [ ] Event ID được tạo ổn định và không đổi khi retry cùng publication.
- [ ] Không dùng entity đang được quản lý hoặc lazy object graph làm payload tích hợp.
- [ ] Thay đổi schema và transaction có migration tương thích.
- [ ] Có cách phát hiện lỗi giữa source commit và external publish.

Một lời gọi publish trong transaction không tự bảo đảm mọi consumer đã xử lý. Nó chỉ tạo điểm phát event; tính bền vững và phục hồi phụ thuộc listener/registry hoặc external messaging mechanism.

## 4. Checklist listener và transaction phase

Mỗi listener cần thể hiện rõ khi nào và trong boundary nào nó chạy.

- [ ] Listener được đăng ký trong đúng module/application context.
- [ ] Loại listener và transaction phase được chọn có chủ đích.
- [ ] Phân biệt listener đồng bộ, async và transactional listener.
- [ ] Listener AFTER_COMMIT không giả định transaction nguồn vẫn mở.
- [ ] Ghi dữ liệu ở consumer dùng transaction phù hợp của consumer.
- [ ] Exception không bị nuốt mà không có log/metric hoặc recovery path.
- [ ] Listener không gọi trực tiếp repository nội bộ của module khác.
- [ ] Listener gọi application service thuộc module sở hữu hành vi.
- [ ] Timeout cho dependency ngoài được giới hạn.
- [ ] Không thực hiện công việc quá dài trong transaction hoặc thread request nếu không cần.

Với Spring Modulith, @ApplicationModuleListener thường được dùng cho xử lý module listener theo semantics async và transactional event listener. Hãy xác nhận đúng semantics của phiên bản và cấu hình đang dùng. Không suy luận rằng mọi @EventListener đều chạy sau commit hoặc trên executor riêng.

## 5. Checklist Event Publication Registry

Nếu dùng Event Publication Registry, xác nhận registry thực sự bao phủ các listener cần phục hồi.

- [ ] Đã xác định listener nào được registry theo dõi.
- [ ] Persistence adapter và transaction manager được cấu hình đúng.
- [ ] Publication được tạo cùng transaction theo semantics mong muốn.
- [ ] Listener thành công làm publication được đánh dấu hoàn tất.
- [ ] Listener thất bại để lại trạng thái có thể quan sát.
- [ ] Publication incomplete có tuổi và listener identity để điều tra.
- [ ] Có cơ chế resubmit/retry theo policy rõ ràng.
- [ ] Resubmit không bỏ qua idempotency ở consumer.
- [ ] Có giới hạn và quy trình xử lý publication cũ.
- [ ] Cleanup completed publication tuân thủ retention và audit needs.

Registry là cơ chế theo dõi publication tới transactional listeners; nó không tự tạo distributed transaction cho mọi side effect. Nếu listener gọi external API rồi process chết trước khi publication hoàn tất, lần xử lý lại có thể gọi API lần nữa. Cần idempotency key hoặc reconciliation ở boundary ngoài.

Không xóa publication incomplete để làm sạch dashboard. Trước khi resubmit, xác định listener đã thực hiện một phần tác dụng phụ hay chưa.

## 6. Checklist transactional outbox

Khi cần phát message ra broker cùng với transaction nghiệp vụ, outbox có thể lưu message cần gửi trong cùng transaction với dữ liệu nguồn.

- [ ] Business state và outbox row được commit trong cùng database transaction.
- [ ] Outbox record chứa event identity, type, schema version và destination cần thiết.
- [ ] Dispatcher chỉ lấy record đủ điều kiện gửi.
- [ ] Claim/lease hoặc locking tránh nhiều dispatcher gửi cùng record ngoài ý muốn.
- [ ] Broker confirmation được kiểm tra theo semantics adapter.
- [ ] Trạng thái SENT chỉ được ghi khi có bằng chứng publish phù hợp.
- [ ] Dispatcher retry được khi broker unavailable.
- [ ] Oldest pending age và backlog được theo dõi.
- [ ] Duplicate publish được consumer xử lý an toàn.
- [ ] Cleanup không xóa message pending hoặc record còn cần audit.

Outbox không tự bảo đảm exactly-once. Nếu broker nhận message nhưng dispatcher dừng trước khi cập nhật SENT, lần chạy sau có thể publish lại. Consumer vẫn cần deduplication.

Không dùng outbox chỉ vì đó là pattern phổ biến. Với event nội bộ và transactional listeners, Event Publication Registry có thể đáp ứng nhu cầu theo dõi publication; với external broker, outbox thường là một lựa chọn riêng cần đánh giá theo transaction boundary.

## 7. Checklist consumer idempotency

Consumer cần an toàn khi cùng một event được giao lại. Xác định identity và phạm vi deduplication:

- [ ] Event có eventId ổn định qua retry và redelivery.
- [ ] Consumer có inbox/dedup store hoặc invariant tương đương.
- [ ] Dedup key gồm consumer identity nếu nhiều consumer xử lý cùng event.
- [ ] Claim event và ghi business effect có tính nguyên tử hoặc có recovery protocol.
- [ ] Duplicate đã hoàn tất không lặp side effect.
- [ ] Event đang PROCESSING có lease/timeout để phục hồi khi worker chết.
- [ ] External API dùng idempotency key nếu hỗ trợ.
- [ ] Kết quả không rõ sau timeout được reconcile trước khi thử lại.
- [ ] Inbox retention đủ dài so với retry và replay horizon.
- [ ] Có test cho duplicate đồng thời và redelivery sau commit.

Ví dụ một consumer có thể dùng unique constraint trên cặp consumerName và eventId. Nhưng chỉ có unique constraint là chưa đủ: cần xác định transaction nào ghi inbox, khi nào business effect commit và trạng thái nào cho phép retry.

Không dùng payload hash làm identity duy nhất nếu hai event khác nhau có thể có cùng payload. Event identity phải đại diện một lần xảy ra nghiệp vụ.

## 8. Checklist ordering và concurrency

Không phải event nào cũng cần thứ tự toàn cục. Chỉ áp đặt ordering khi domain yêu cầu và chọn phạm vi nhỏ nhất có thể.

- [ ] Xác định event nào cần thứ tự theo aggregate hoặc business key.
- [ ] Producer tạo sequence/version nếu cần phát hiện event thiếu hoặc đến muộn.
- [ ] Broker partition key hoặc queue topology phù hợp với ordering requirement.
- [ ] Consumer concurrency không phá vỡ thứ tự cần thiết.
- [ ] Duplicate và out-of-order event có policy riêng.
- [ ] Có thể phát hiện sequence gap.
- [ ] Event cũ đến sau event mới không ghi đè state mới hơn.
- [ ] Không dùng timestamp đơn lẻ làm thứ tự tuyệt đối khi clock có thể lệch.
- [ ] Hot key hoặc partition skew được theo dõi.

Nếu consumer cập nhật projection theo aggregate version, có thể từ chối hoặc bỏ qua event có version thấp hơn state hiện tại. Nếu nghiệp vụ cần xử lý tuần tự, hãy giới hạn concurrency theo key thay vì tuần tự hóa toàn bộ hệ thống.

## 9. Checklist retry và phân loại lỗi

Retry chỉ có ích khi lỗi có khả năng tự hết. Phân loại lỗi trước khi cấu hình policy.

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Transient | Timeout, connection reset, broker tạm unavailable | Retry có backoff và giới hạn |
| Throttling | HTTP 429, database capacity | Retry theo Retry-After hoặc capacity policy |
| Permanent | Payload sai contract, thiếu field bắt buộc | Quarantine/DLQ, sửa contract hoặc dữ liệu |
| Business rejection | Hết tồn kho, trạng thái không cho phép | Xử lý theo workflow nghiệp vụ, không retry mù quáng |
| Unknown outcome | API timeout sau khi có thể đã thực hiện side effect | Reconcile/idempotency trước retry |

- [ ] Có maximum attempts và maximum elapsed time.
- [ ] Backoff có jitter để tránh retry storm.
- [ ] Retry budget phù hợp SLO và dependency capacity.
- [ ] Permanent error không bị retry vô hạn.
- [ ] Retry policy được đặt ở một lớp có owner rõ.
- [ ] Không chồng nhiều retry layer ngoài ý muốn.
- [ ] Mỗi attempt có eventId, attempt number và reason trong log.
- [ ] Hết retry thì chuyển DLQ/quarantine hoặc manual review.
- [ ] Operator biết cách replay sau khi sửa nguyên nhân.

Không retry mọi RuntimeException như nhau. Một lỗi schema sẽ không tự hết sau 30 giây; một timeout có thể đã xảy ra sau khi external side effect thành công.

## 10. Checklist broker và transport

Nếu event đi qua RabbitMQ, Kafka hoặc broker khác, kiểm tra đúng semantics của transport.

**RabbitMQ/AMQP**

- [ ] Exchange, queue, binding và routing key đúng.
- [ ] Publisher confirm/return được xử lý.
- [ ] Consumer ACK/NACK/requeue có chủ đích.
- [ ] DLX/DLQ và retry queue có topology đúng.
- [ ] Prefetch và consumer concurrency không làm cạn tài nguyên.
- [ ] Queue durability, message persistence và TTL phù hợp.
- [ ] Unroutable message và redelivery được quan sát.

**Kafka**

- [ ] Topic, partition, replication và retention đúng.
- [ ] Key/partition strategy đáp ứng ordering requirement.
- [ ] Consumer group và rebalance ổn định.
- [ ] Offset commit chỉ diễn ra theo processing semantics đã chọn.
- [ ] Retry topic/DLT có quy trình và retention rõ.
- [ ] Consumer lag theo partition được theo dõi.
- [ ] Record/batch size và schema compatibility được kiểm soát.

Không dùng thuật ngữ ACK của RabbitMQ để mô tả offset commit của Kafka. Xác nhận rằng metric và runbook phản ánh đúng transport đang chạy.

## 11. Checklist schema và event contract

Contract cần ổn định đủ lâu để producer, consumer và event history cùng hoạt động.

- [ ] Event type có tên và semantics nghiệp vụ rõ.
- [ ] Field bắt buộc, optional, nullable và đơn vị được mô tả.
- [ ] Schema version được quản lý.
- [ ] Thêm field mới không làm consumer cũ fail ngoài ý muốn.
- [ ] Unknown enum/event type có policy.
- [ ] Không thay đổi ý nghĩa field cũ dưới cùng tên.
- [ ] Producer/consumer contract tests được duy trì.
- [ ] Event lịch sử có thể deserialize hoặc được upcast.
- [ ] Breaking change có expand-contract rollout.
- [ ] Consumer inventory và owner được cập nhật.

Một schema pass compatibility check không chứng minh handler hiểu đúng semantics. Kiểm tra cả deserialization và business outcome. Nếu consumer cũ bỏ qua field mới, phải chắc rằng bỏ qua field đó là an toàn.

## 12. Checklist payload và dữ liệu

Payload nên đủ để consumer thực hiện trách nhiệm nhưng không mang dữ liệu thừa.

- [ ] Chỉ chứa field cần thiết cho contract.
- [ ] Không gửi JPA entity hoặc lazy graph.
- [ ] Có eventId, occurredAt và correlation metadata phù hợp.
- [ ] Snapshot hay reference được chọn có chủ đích.
- [ ] Payload size nằm trong budget.
- [ ] Field nhạy cảm được giảm thiểu hoặc loại bỏ.
- [ ] Schema có giới hạn độ dài, kiểu và enum.
- [ ] Không phụ thuộc dữ liệu mutable ngoài event mà không có version.
- [ ] Reference có authorization và lifecycle rõ.
- [ ] Retention/deletion của payload được xác định.

Nếu dùng reference tới object storage, consumer cần kiểm tra object tồn tại, quyền truy cập, version và thời gian lưu. Một URL hết hạn không phải contract bền vững.

## 13. Checklist observability và tracing

Không thể vận hành event flow nếu chỉ có log “published” hoặc “listener started”.

- [ ] Producer và consumer log structured.
- [ ] eventId được ghi ở mọi boundary liên quan.
- [ ] correlationId/causationId nối được business flow.
- [ ] Trace context được truyền qua transport nếu hỗ trợ.
- [ ] Metric có eventType, consumer và outcome với cardinality kiểm soát.
- [ ] Publish failure và deserialize failure được đo.
- [ ] Listener processing duration và exception rate được đo.
- [ ] Publication incomplete và oldest age được theo dõi.
- [ ] Outbox pending age, queue depth hoặc Kafka lag được theo dõi.
- [ ] Retry, redelivery và DLQ count có dashboard/alert.
- [ ] Log không chứa secret hoặc payload nhạy cảm.

Các định danh eventId/orderId phù hợp với log và trace, không phù hợp làm metric label có cardinality cao. Dashboard nên giúp trả lời event đang ở đâu, consumer nào chưa xử lý và nó bị chậm bao lâu.

## 14. Checklist capacity, backpressure và payload throughput

Độ tin cậy phụ thuộc khả năng xử lý tải bình thường và tải đột biến.

- [ ] Throughput đầu vào và năng lực consumer được đo.
- [ ] Backlog có ngưỡng cảnh báo và oldest age.
- [ ] Executor queue có giới hạn.
- [ ] Consumer concurrency phù hợp database pool và downstream capacity.
- [ ] Prefetch/partition concurrency được chọn theo workload.
- [ ] Retry không khuếch đại tải khi dependency đang quá tải.
- [ ] Payload bytes và serialization CPU được theo dõi.
- [ ] Có chính sách khi backlog vượt capacity.
- [ ] Có thể scale consumer mà không phá ordering hoặc idempotency.
- [ ] Load test đại diện cho peak và recovery burst.

Tăng concurrency không phải cách xử lý mọi backlog. Nó có thể làm database pool, lock hoặc external API quá tải. Trước khi scale, xác định bottleneck và giới hạn downstream.

## 15. Checklist security và privacy

Event có thể được lưu ở registry, outbox, broker, DLQ, log và archive. Mỗi bản sao là một điểm cần bảo vệ.

- [ ] Producer chỉ publish field được phép.
- [ ] Không đưa password, token hoặc secret vào payload.
- [ ] Broker ACL giới hạn publish/subscribe.
- [ ] TLS và credential rotation được cấu hình.
- [ ] Consumer xác thực nguồn và validate payload.
- [ ] DLQ/quarantine có quyền truy cập hạn chế.
- [ ] Log/trace redaction được bật.
- [ ] Encryption at rest/in transit phù hợp policy.
- [ ] Retention và deletion áp dụng cho bản sao event.
- [ ] Audit ghi nhận thao tác replay/resubmit của operator.

Không dùng event payload như nơi truyền secret hoặc bearer token. Nếu consumer cần dữ liệu nhạy cảm, cân nhắc reference có kiểm soát truy cập hoặc truy vấn qua API được bảo vệ.

## 16. Checklist failure recovery và disaster recovery

Một hệ thống đáng tin cậy cần biết phục hồi sau process crash, database outage, broker outage và dữ liệu tồn đọng.

- [ ] Có quy trình restart consumer an toàn.
- [ ] Publication incomplete được phát hiện và phục hồi.
- [ ] Outbox pending không bị mất sau restart.
- [ ] Broker persistence/replication/backup phù hợp yêu cầu.
- [ ] DLQ được lưu và replay theo runbook.
- [ ] Inbox/dedup state được backup cùng business state.
- [ ] Có quy trình reconcile event và business database.
- [ ] Replay có giới hạn, idempotency và audit.
- [ ] RPO/RTO của event pipeline được xác định nếu nghiệp vụ cần.
- [ ] Restore drill bao gồm cả broker/store cần thiết.

Không replay trước khi biết consumer đã thực hiện side effect hay chưa. Khi trạng thái không rõ, reconcile với hệ thống đích trước. Replay hàng loạt có thể gây duplicate hoặc quá tải.

## 17. Checklist kiểm thử

Test cần chứng minh từng guarantee ở boundary nơi nó được thực thi.

| Rủi ro | Kiểm thử phù hợp |
|---|---|
| Domain tạo event sai | Unit/application service test |
| Listener không đăng ký | Spring Modulith module test |
| Dependency module sai | Architecture verification |
| AFTER_COMMIT/rollback sai | Transaction integration test |
| Registry không cập nhật | Registry persistence test |
| Outbox dispatcher lỗi | Database + adapter integration test |
| Duplicate delivery | Idempotency/inbox integration test |
| Ordering sai | Sequence/concurrency test |
| Schema không tương thích | Contract test với version cũ/mới |
| Broker ACK/routing/DLQ sai | Broker integration test |
| Backlog và throughput | Load/recovery test |
| Replay gây side effect lặp | Scenario test với dữ liệu đại diện |

- [ ] Test thành công và failure path.
- [ ] Test rollback và commit thật khi cần.
- [ ] Test listener async với điều kiện chờ có ý nghĩa.
- [ ] Test duplicate và concurrent duplicate.
- [ ] Test retry exhausted và poison message.
- [ ] Test consumer restart khi message đang xử lý.
- [ ] Test schema cũ/mới và unknown values.
- [ ] Test dữ liệu cô lập, không phụ thuộc thứ tự.
- [ ] Test replay có idempotency.
- [ ] Test có timeout và diagnostic đủ để điều tra.

Không dùng mock để tuyên bố broker, transaction hoặc registry đã hoạt động đúng. Mock chỉ xác minh boundary mà nó đại diện.

## 18. Checklist cấu hình và triển khai

Cấu hình có thể làm thay đổi semantics mà code không đổi.

- [ ] Profile và feature flags đúng môi trường.
- [ ] Executor, pool size và queue capacity được giới hạn.
- [ ] Transaction manager và propagation đúng.
- [ ] Listener phase và retry policy đúng.
- [ ] Registry/outbox persistence được migrate.
- [ ] Broker destination và credentials đúng.
- [ ] Schema Registry policy đúng nếu có.
- [ ] Consumer version tương thích producer version.
- [ ] Shutdown graceful cho phép xử lý hoặc nhả message an toàn.
- [ ] Deployment rollback/roll-forward đã được chuẩn bị.

Không đặt retry count, concurrency hoặc timeout theo mặc định mà không xét SLO và downstream capacity. Cấu hình production cần được quản lý, review và quan sát như code.

## 19. Checklist sau phát hành

Sau rollout, xác nhận luồng event thực tế thay vì chỉ nhìn trạng thái deployment.

- [ ] Release version và instance đang chạy đúng.
- [ ] Producer publish rate và failure rate trong baseline.
- [ ] Source transaction commit đúng.
- [ ] Registry incomplete count và oldest age ổn định.
- [ ] Outbox pending age không tăng bất thường.
- [ ] Broker confirm/routing/lag/queue depth bình thường.
- [ ] Consumer deserialize và handler success bình thường.
- [ ] Business outcome tăng theo input.
- [ ] Duplicate không tạo side effect trùng.
- [ ] Retry/DLQ không tăng bất thường.
- [ ] Schema mới tương thích mọi consumer còn chạy.
- [ ] p95/p99 và tài nguyên trong budget.
- [ ] Có canary hoặc smoke test an toàn.
- [ ] Quyết định continue/pause/rollback được ghi bằng evidence.

Rollback binary không thu hồi message đã commit hoặc đã vào broker. Trước rollback, xác định event đang chờ và consumer nào có thể đọc chúng.

## 20. Checklist runbook và ownership

Mỗi event flow quan trọng cần một owner có thể hành động khi lỗi xảy ra.

- [ ] Producer owner được xác định.
- [ ] Consumer owner được xác định cho từng subscription.
- [ ] Contract/schema owner được xác định.
- [ ] Dashboard và alert có link trong runbook.
- [ ] Runbook nêu cách tìm event theo eventId/correlationId.
- [ ] Có hướng dẫn phân biệt transient/permanent failure.
- [ ] Có điều kiện retry, resubmit, replay và DLQ.
- [ ] Có hướng dẫn kiểm tra side effect trước replay.
- [ ] Có quy trình escalation và người phê duyệt thao tác rủi ro.
- [ ] Có lịch review retention, schema và consumer inventory.

Không để một event “không ai sở hữu”. Producer có trách nhiệm contract và phát event; consumer có trách nhiệm xử lý và side effect; platform/operator có trách nhiệm transport và năng lực chung. Runbook phải chỉ rõ boundary khi sự cố xảy ra.

## 21. Mẫu checklist cho một event cụ thể

Có thể sao chép mẫu sau cho từng event quan trọng:

~~~text
Event:
Producer module:
Consumer(s):
Business fact:
Criticality:
Delivery semantics:
Event identity:
Schema version:
Transaction boundary:
Listener phase:
Durability mechanism:
Retry owner and policy:
Idempotency key/store:
Ordering requirement:
Maximum processing delay:
Payload/data classification:
Metrics and alerts:
Replay/reconciliation procedure:
Producer owner:
Consumer owner:
Last contract test:
Last recovery test:
~~~

Sau khi điền, review các mục còn trống. Nếu chưa xác định delivery semantics, idempotency hoặc owner, chưa đủ thông tin để tuyên bố luồng event đáng tin cậy.

## 22. Các câu hỏi release gate

Trước khi cho phép một event flow đi production hoặc mở rộng rollout, người review có thể hỏi:

1. Event đại diện fact nào và ai sở hữu fact đó?
2. Nếu producer commit rồi process chết thì event còn ở đâu?
3. Nếu consumer xử lý thành công nhưng ACK bị mất thì sao?
4. Nếu cùng event được giao đồng thời hai lần thì side effect có lặp không?
5. Nếu listener lỗi sau commit thì ai phát hiện và phục hồi?
6. Nếu payload có field hoặc enum mới thì consumer cũ làm gì?
7. Nếu broker hoặc database ngừng hoạt động trong một giờ thì backlog ra sao?
8. Nếu consumer chậm hơn producer thì backpressure ở đâu?
9. Nếu replay một ngày dữ liệu thì hệ thống có chịu được không?
10. Ai có quyền resubmit/replay và cách audit là gì?
11. Có dashboard để xác nhận business outcome không?
12. Có thể dừng rollout hoặc phục hồi mà không làm mất message không?

Câu trả lời cần dựa trên implementation, test hoặc runbook. “Framework tự xử lý” không phải bằng chứng về guarantee của toàn pipeline.

## 23. Ưu tiên theo mức độ rủi ro

Không phải event nào cũng cần cùng mức kiểm soát. Có thể phân loại theo tác động:

| Mức | Ví dụ | Trọng tâm |
|---|---|---|
| Critical | Thanh toán, quyền truy cập, tồn kho có ràng buộc | Durability, idempotency, audit, reconciliation, alert |
| Important | Workflow đơn hàng, thông báo bắt buộc | Retry bounded, backlog, consumer recovery, schema |
| Best-effort | Analytics, telemetry, projection có thể rebuild | Loss/replay policy, lag, rebuild và cost |

Mức phân loại phải theo hậu quả khi event mất, trễ hoặc xử lý trùng. Analytics có thể best-effort nếu có nguồn dữ liệu để rebuild; nếu analytics dùng cho báo cáo pháp lý hoặc đối soát tài chính, mức criticality sẽ khác.

## 24. Checklist tổng hợp để review

### Thiết kế
- [ ] Event diễn đạt fact đã xảy ra.
- [ ] Producer/consumer ownership và contract rõ.
- [ ] Delivery semantics và consistency được công bố.
- [ ] Transaction boundary và durability mechanism được xác định.
- [ ] Ordering chỉ được yêu cầu khi nghiệp vụ cần.
- [ ] Schema có version và compatibility policy.

### Triển khai
- [ ] Listener phase và async behavior đúng.
- [ ] Registry/outbox persistence hoạt động.
- [ ] Retry bounded, có backoff và phân loại lỗi.
- [ ] Consumer idempotent và xử lý duplicate.
- [ ] Payload được validate, giới hạn size và giảm thiểu dữ liệu.
- [ ] Security và retention được áp dụng.

### Kiểm thử
- [ ] Commit/rollback và listener failure được kiểm thử.
- [ ] Duplicate, retry exhausted, DLQ và replay được kiểm thử.
- [ ] Contract cũ/mới được kiểm thử.
- [ ] Broker semantics được kiểm thử ở integration boundary.
- [ ] Load, backlog recovery và concurrency được kiểm tra theo rủi ro.

### Vận hành
- [ ] Metrics, logs, traces và alert có owner.
- [ ] Backlog, oldest age, retry và DLQ được theo dõi.
- [ ] Runbook có quy trình resubmit/replay/reconcile.
- [ ] Release gate và rollback/roll-forward đã sẵn sàng.
- [ ] Recovery/restore được diễn tập khi yêu cầu nghiệp vụ cần.

## 25. Cách sử dụng checklist trong vòng đời phát triển

Dùng checklist ở bốn thời điểm:

1. **Design review:** xác định semantics, transaction, ownership, failure và recovery trước khi code.
2. **Implementation review:** xác nhận listener, registry/outbox, retry, idempotency và observability được triển khai đúng.
3. **Release review:** kiểm tra schema compatibility, canary, baseline, backlog và rollback plan.
4. **Operations review:** định kỳ xem alert, publication age, retry, DLQ, replay và recovery drill.

Không cần đánh dấu tất cả mục là áp dụng cho mọi event. Ghi NOT APPLICABLE cùng lý do và owner khi một cơ chế không liên quan. Ghi NOT CHECKED nếu chưa có bằng chứng; không chuyển thành PASS chỉ vì không thấy lỗi.

Checklist độ tin cậy có giá trị khi nó biến các giả định thành câu hỏi có thể kiểm chứng. Hãy bảo vệ transaction và publication, thiết kế consumer idempotent, giới hạn retry, quản lý schema, quan sát backlog và chuẩn bị replay/reconciliation. Với Spring Modulith, chọn Event Publication Registry, outbox và broker theo đúng boundary của luồng. Một event chỉ nên được xem là đáng tin cậy khi đội ngũ có thể chứng minh nó được lưu, giao, xử lý, phục hồi và đối soát theo yêu cầu nghiệp vụ.

