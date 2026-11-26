# Checklist kiểm thử

Kiểm thử application events cần xác minh toàn bộ đường đi của một sự kiện: publisher tạo đúng event, transaction hoàn tất đúng thời điểm, listener của module nhận xử lý đúng, publication được theo dõi và phục hồi khi lỗi, còn adapter/broker giữ nguyên hợp đồng khi event đi ra ngoài ứng dụng. Một test chỉ kiểm tra rằng phương thức publish đã được gọi chưa đủ để chứng minh luồng event đáng tin cậy.

Checklist trong bài này giúp lập kế hoạch kiểm thử theo từng lớp và theo rủi ro. Có thể dùng nó khi xây dựng module mới, thay đổi event contract, nâng cấp Spring Modulith hoặc chuẩn bị triển khai production. Mỗi mục cần được chọn theo kiến trúc thực tế; không phải hệ thống nào cũng cần broker, outbox, saga hay schema registry.

## 1. Xác định phạm vi và mục tiêu kiểm thử

Trước khi viết test, xác định event flow cần bảo vệ:

- Module nào phát event?
- Event type và payload contract là gì?
- Listener nào nhận event?
- Listener chạy đồng bộ, sau commit hay bất đồng bộ?
- Event có đi qua Event Publication Registry, outbox hoặc broker không?
- Side effect nào phải xảy ra?
- Có yêu cầu thứ tự, idempotency hoặc eventual consistency không?
- SLA xử lý và thời gian phục hồi được kỳ vọng là bao lâu?

Vẽ một đường đi cụ thể thay vì kiểm thử một khái niệm chung như “event hoạt động”. Ví dụ:

~~~text
PlaceOrder
    |
    v
Order module transaction
    |
    | commit
    v
OrderPlaced
    |
    +--> Inventory listener --> InventoryReserved
    |
    +--> Notification listener --> email request
    |
    +--> Outbox adapter --> broker --> external consumer
~~~

Mỗi nhánh có semantics và điểm lỗi riêng. Test cần chứng minh đúng trách nhiệm của từng nhánh, tránh một test end-to-end lớn khiến lỗi khó xác định.

Một mục tiêu kiểm thử nên mô tả được hành vi quan sát được, ví dụ: “Khi Order commit, listener Inventory nhận OrderPlaced đúng một lần về mặt side effect và reservation được tạo cho đúng orderId.” Tránh mục tiêu mơ hồ như “kiểm tra event chạy”.

## 2. Checklist hợp đồng event

Event là hợp đồng giao tiếp giữa publisher và consumer. Kiểm tra cấu trúc lẫn ý nghĩa của payload.

- [ ] Tên event mô tả sự kiện nghiệp vụ đã xảy ra, không phải lệnh yêu cầu consumer thực hiện.
- [ ] Event type ổn định và được công bố ở package/API phù hợp.
- [ ] Payload chỉ chứa dữ liệu cần thiết cho consumer.
- [ ] Không đưa JPA entity, lazy proxy hoặc object graph nội bộ vào event.
- [ ] Field có kiểu dữ liệu, đơn vị, timezone và semantics rõ ràng.
- [ ] Trường bắt buộc không bị null hoặc thiếu.
- [ ] Null, missing và empty được phân biệt theo contract.
- [ ] Event ID, correlation ID, causation ID hoặc aggregate version được thêm khi use case cần.
- [ ] Consumer xử lý được unknown field hoặc unknown enum theo chính sách đã thống nhất.
- [ ] Schema version được kiểm tra nếu payload tồn tại qua nhiều lần deploy hoặc đi qua broker.

Test contract nên dùng fixture payload độc lập với class producer để tránh hai phía vô tình thay đổi cùng lúc mà test vẫn xanh. Với event nội bộ được build/deploy đồng bộ, có thể kiểm tra compile-time và module integration; với integration event qua broker, nên có contract test rõ ràng hơn.

## 3. Checklist publisher

Publisher chịu trách nhiệm phát đúng event tại đúng thời điểm, với dữ liệu phản ánh kết quả nghiệp vụ đã được xác lập.

- [ ] Event chỉ được publish khi điều kiện nghiệp vụ tương ứng đã đạt.
- [ ] Payload lấy từ kết quả nghiệp vụ đã được xác thực.
- [ ] ID và metadata được tạo hoặc truyền theo quy tắc nhất quán.
- [ ] Event không được phát khi validation thất bại.
- [ ] Event không được phát nếu transaction nguồn rollback khi contract yêu cầu publish sau commit.
- [ ] Một thao tác nghiệp vụ không vô tình publish event hai lần.
- [ ] Các nhánh lỗi không để event mô tả một trạng thái chưa commit.
- [ ] Thay đổi publisher giữ tương thích với listener hiện có hoặc có kế hoạch migration.

Ví dụ kiểm thử publisher bằng cách gọi application service:

~~~java
@Test
void publishesOrderPlacedAfterOrderCreation() {
    UUID orderId = UUID.randomUUID();
    PlaceOrderCommand command = validCommand();

    orderManagement.placeOrder(command);

    // Assert event được publish và chứa dữ liệu tương ứng.
}
~~~

Nếu dùng Spring Modulith Scenario, có thể dùng stimulate để gọi component công khai và chờ event mong đợi. Nếu mục tiêu chỉ là kiểm tra mapping thuần, unit test mapper riêng sẽ nhanh và dễ chẩn đoán hơn.

Không chỉ verify mock ApplicationEventPublisher được gọi. Cần ít nhất một test ở mức Spring context/module để chứng minh event được dispatch tới listener thực sự.

## 4. Checklist listener

Listener là nơi thực thi phản ứng của module nhận. Kiểm tra cả logic nghiệp vụ và cách listener tham gia vào transaction.

- [ ] Listener được đăng ký trong ApplicationContext.
- [ ] Listener nhận đúng event type.
- [ ] Listener nằm trong module sở hữu hành vi xử lý.
- [ ] Listener gọi application service của module mình thay vì thao tác trực tiếp dữ liệu module khác.
- [ ] Payload được kiểm tra trước khi dùng.
- [ ] Side effect đúng với event và aggregate tương ứng.
- [ ] Listener không thực hiện thêm hành vi ngoài contract.
- [ ] Exception được truyền ra hoặc phân loại theo retry policy; không bị nuốt âm thầm.
- [ ] Listener xử lý được duplicate theo chính sách idempotency.
- [ ] Log và metric xác định được listener, event type và kết quả.

Với listener có nhiều nhánh nghiệp vụ, viết unit test cho từng nhánh và một module integration test cho wiring thực tế. Mock các dependency ngoài module khi mục tiêu không phải kiểm tra tích hợp với chúng.

## 5. Checklist transaction phase

Transaction là phần dễ bị kiểm thử sai vì test framework có thể tự mở transaction và rollback sau test.

- [ ] Xác định listener là synchronous, AFTER_COMMIT, BEFORE_COMMIT hay asynchronous.
- [ ] Test tạo transaction theo đúng đường gọi production.
- [ ] Có test chứng minh AFTER_COMMIT listener chỉ chạy sau commit.
- [ ] Có test chứng minh rollback không kích hoạt listener AFTER_COMMIT.
- [ ] Có test cho trường hợp publisher chạy ngoài transaction nếu ứng dụng cho phép.
- [ ] Xác minh fallbackExecution nếu có được bật có chủ đích.
- [ ] Listener ghi dữ liệu dùng transaction manager phù hợp.
- [ ] Không giả định nhiều datasource tự động commit nguyên tử.
- [ ] Test phân biệt exception trước commit và exception sau commit.
- [ ] Cleanup dữ liệu test theo transaction boundary thực tế.

Đối với @TransactionalEventListener, test method có @Transactional và mặc định rollback có thể khiến AFTER_COMMIT không chạy. Hãy commit transaction stimulus thực sự hoặc dùng công cụ điều khiển transaction thích hợp.

Đối với @ApplicationModuleListener, xác minh listener được kích hoạt theo semantics sau commit và transaction riêng của listener. Đừng assert ngay sau khi publisher trả về nếu listener bất đồng bộ.

## 6. Checklist kiểm thử ranh giới module

Spring Modulith giúp kiểm tra cấu trúc module và giao tiếp giữa module qua API được công bố.

- [ ] Test được đặt trong package module phù hợp.
- [ ] Bootstrap scope chỉ nạp module cần thiết cho mục tiêu test.
- [ ] Module publisher chỉ phụ thuộc API công khai của module khác.
- [ ] Listener thuộc module nhận và không làm lộ implementation nội bộ.
- [ ] Event class nằm ở package mà consumer được phép phụ thuộc.
- [ ] Không có dependency vòng giữa các module.
- [ ] ApplicationModuleTest kiểm tra được wiring của module liên quan.
- [ ] Module verification phát hiện dependency vi phạm khi cấu trúc thay đổi.
- [ ] Test không phải nạp toàn bộ ứng dụng nếu chỉ cần kiểm tra một module và các dependency trực tiếp.

Dùng bootstrap mode phù hợp với mục tiêu. Test module độc lập có thể chạy ở scope hẹp; test giao tiếp giữa hai module cần nạp các module liên quan. Việc nạp toàn bộ ứng dụng cho mọi test làm test chậm và có thể che giấu dependency không rõ ràng.

## 7. Checklist Scenario và asynchronous expectation

Với event bất đồng bộ, Scenario giúp đợi kết quả theo điều kiện thay vì dùng sleep cố định.

- [ ] Stimulus dùng publish khi kiểm tra listener phản ứng với event đầu vào.
- [ ] Stimulus dùng stimulate khi kiểm tra service phát event sau hành động nghiệp vụ.
- [ ] Kỳ vọng event đúng type.
- [ ] matching predicate lọc theo ID ổn định như orderId hoặc eventId.
- [ ] Assertion kiểm tra payload và invariant quan trọng.
- [ ] Timeout hữu hạn và phù hợp với môi trường test.
- [ ] Negative expectation chỉ dùng khi sự vắng mặt là hợp đồng cần kiểm tra.
- [ ] State-change expectation được dùng khi trạng thái cuối quan trọng hơn event trung gian.
- [ ] Cleanup chạy kể cả khi expectation thất bại.
- [ ] Test không phụ thuộc vào thứ tự chạy của test khác.

Ví dụ:

~~~java
@Test
void publishesInventoryReserved(Scenario scenario) {
    UUID orderId = UUID.randomUUID();

    scenario.publish(new OrderPlaced(orderId))
            .andWaitForEventOfType(InventoryReserved.class)
            .matching(event -> event.orderId().equals(orderId))
            .toArriveAndVerify(event -> {
                assertThat(event.orderId()).isEqualTo(orderId);
                assertThat(event.reservationId()).isNotNull();
            });
}
~~~

Tên method và overload Scenario có thể khác theo phiên bản Spring Modulith. Dùng API đúng với dependency của dự án. Không thay Scenario bằng Thread.sleep vì sleep không chứng minh điều kiện đã xảy ra và thường làm test chậm, chập chờn.

## 8. Checklist Event Publication Registry

Nếu dùng Event Publication Registry, kiểm tra khả năng ghi nhận, hoàn tất và phục hồi publication.

- [ ] Persistence implementation phù hợp đã được cấu hình.
- [ ] Schema/migration của registry có mặt ở môi trường test tích hợp.
- [ ] Publication được ghi cho listener cần theo dõi.
- [ ] Listener thành công làm publication được đánh dấu hoàn tất.
- [ ] Listener thất bại để lại trạng thái chưa hoàn tất theo semantics framework.
- [ ] Publication được gắn đúng listener.
- [ ] Có test phục hồi/resubmit sau khi nguyên nhân lỗi đã được sửa.
- [ ] Resubmit không tạo side effect lặp.
- [ ] Publication của listener khác đã hoàn tất không bị xử lý lại ngoài ý muốn.
- [ ] Không dùng SQL tự sửa trạng thái registry để làm test xanh.

Nên có test cho cửa sổ lỗi quan trọng: listener đã thực hiện side effect nhưng tiến trình lỗi trước khi publication được đánh dấu hoàn tất. Khi resubmit, listener có thể chạy lại; idempotency phải bảo vệ nghiệp vụ.

Registry theo dõi publication tới listener. Nó không tự thay thế event store dài hạn, transactional outbox hoặc xác nhận consumer bên ngoài đã xử lý message.

## 9. Checklist idempotency, duplicate và ordering

Event có thể được xử lý lại do retry, redelivery, resubmit hoặc replay.

- [ ] Mỗi event có định danh ổn định khi cần deduplicate.
- [ ] Consumer ghi nhận processed event bằng khóa phù hợp.
- [ ] Deduplication record và side effect được commit cùng transaction khi có thể.
- [ ] Cùng một event được giao lại không tạo thêm side effect.
- [ ] Hai payload version đại diện cùng logical event được nhận diện theo cùng identity policy.
- [ ] Event mới có event ID mới.
- [ ] Retry cùng event giữ event ID gốc.
- [ ] Aggregate version/sequence được kiểm tra khi thứ tự quan trọng.
- [ ] Event đến muộn hoặc thiếu sequence có chính sách chờ, bỏ qua hoặc reconcile rõ ràng.
- [ ] Test song song không chia sẻ static mutable state.

Test duplicate phải xác minh trạng thái cuối hoặc số side effect, không chỉ verify listener được gọi bao nhiêu lần. Một listener có thể được gọi hai lần nhưng vẫn idempotent nếu side effect chỉ xảy ra một lần.

## 10. Checklist retry, failure và DLQ

Retry chỉ phù hợp với lỗi có khả năng tự phục hồi. Lỗi contract hoặc dữ liệu cố định cần được xử lý riêng.

- [ ] Phân loại lỗi tạm thời và lỗi không thể phục hồi.
- [ ] Retry có giới hạn số lần hoặc thời gian.
- [ ] Backoff và jitter tránh retry đồng loạt.
- [ ] Timeout của dependency được cấu hình.
- [ ] Requeue không tạo vòng lặp nóng.
- [ ] Poison message được chuyển vào DLQ/quarantine.
- [ ] DLQ giữ event ID, schema version, correlation ID và nguyên nhân.
- [ ] Replay DLQ có quy trình chọn batch và xác minh side effect.
- [ ] Listener idempotent trước khi bật resubmit/retry.
- [ ] Test chứng minh lỗi cố định không retry vô hạn.

Test failure nên kiểm tra trạng thái publication/outbox/message sau lỗi, số lần thử và log/metric quan trọng. Tránh chỉ assert rằng exception được ném ra mà không xác minh trạng thái phục hồi.

## 11. Checklist transactional outbox và broker

Nếu event được externalize, cần test transport riêng với application event nội bộ.

**Transactional outbox**

- [ ] Outbox record được ghi cùng transaction nghiệp vụ.
- [ ] Rollback nghiệp vụ không để lại record cần gửi.
- [ ] Relay chỉ đánh dấu SENT theo semantics confirm/return của transport.
- [ ] Relay có thể phục hồi sau restart.
- [ ] Gửi thành công nhưng cập nhật trạng thái thất bại không làm mất message.
- [ ] Duplicate do relay retry được consumer xử lý idempotent.
- [ ] Record PENDING/FAILED được quan sát và cảnh báo.

**RabbitMQ/AMQP**

- [ ] Exchange, queue và binding đúng.
- [ ] Routing key đưa message tới queue mong muốn.
- [ ] Publisher confirm và returned message được xử lý.
- [ ] Consumer acknowledgement diễn ra sau side effect theo thiết kế.
- [ ] Retry queue, DLX và dead-letter routing hoạt động.
- [ ] Credential và permission tối thiểu đủ cho publish/consume.
- [ ] Redelivery không tạo side effect trùng.

**Kafka**

- [ ] Topic, partition và key được cấu hình đúng.
- [ ] Consumer group đọc đúng topic.
- [ ] Offset commit phù hợp với transaction/side effect.
- [ ] Retry topic hoặc DLT có routing đúng.
- [ ] Rebalance không làm mất xử lý hoặc tạo duplicate ngoài khả năng idempotency.
- [ ] Ordering theo partition key được kiểm tra.
- [ ] Lag và retention được theo dõi.

Mock broker chỉ xác minh code gọi adapter. Cần integration test với broker thật hoặc môi trường tương thích để kiểm tra topology, acknowledgement, confirm và redelivery.

## 12. Checklist serialization và schema version

Payload có thể được đọc bởi consumer chạy phiên bản code khác hoặc được replay sau nhiều lần deploy.

- [ ] Serializer/deserializer dùng đúng content type và encoding.
- [ ] Envelope có event type và schema version khi cần.
- [ ] Consumer hỗ trợ mọi version còn trong retention/replay window.
- [ ] Unknown field được xử lý theo tolerant-reader policy.
- [ ] Missing required field bị từ chối rõ ràng.
- [ ] Unknown enum có fallback an toàn hoặc quarantine.
- [ ] Thay đổi kiểu dữ liệu/semantics được version hóa.
- [ ] Upcaster có tính xác định và giữ nguyên payload gốc.
- [ ] Fixture của version cũ được giữ trong source control.
- [ ] Unsupported version không retry vô hạn.

Contract test nên chạy cả hai chiều cần thiết: consumer mới đọc payload cũ, và consumer cũ đọc payload mới nếu rollout yêu cầu forward compatibility. Đừng chỉ test payload do producer hiện tại tạo ra.

## 13. Checklist correlation, logging và observability

Khi test thất bại, đội phát triển phải nối được log của publisher, listener và broker.

- [ ] Log có event type, event ID và listener/consumer name.
- [ ] Correlation ID được truyền qua event metadata khi cần.
- [ ] Trace context được quản lý riêng theo instrumentation.
- [ ] MDC được thiết lập và dọn trong finally.
- [ ] Context không rò giữa các task trên thread pool.
- [ ] Log không chứa secret hoặc payload nhạy cảm.
- [ ] Metric có event type/listener/outcome với cardinality kiểm soát.
- [ ] Không dùng event ID/correlation ID làm metric label.
- [ ] Có metric publication chưa hoàn tất, backlog age và processing latency.
- [ ] Có alert cho retry, DLQ và backlog vượt SLA.

Test logging không nhất thiết phải kiểm tra từng câu log. Ưu tiên xác minh field có cấu trúc hoặc instrumentation được cấu hình đúng ở boundary quan trọng.

## 14. Checklist concurrency và tải

Một test đơn lẻ không phát hiện được race condition hoặc bottleneck khi event tăng nhanh.

- [ ] Nhiều event độc lập được xử lý song song đúng.
- [ ] Event của cùng aggregate giữ invariant và ordering nếu cần.
- [ ] Database lock và optimistic conflict được xử lý.
- [ ] Executor queue có giới hạn.
- [ ] Rejection policy không âm thầm bỏ công việc quan trọng.
- [ ] Prefetch/concurrency không vượt capacity downstream.
- [ ] Arrival rate và completion rate được đo.
- [ ] Backlog age không tăng liên tục dưới tải dự kiến.
- [ ] Retry storm không làm cạn connection pool.
- [ ] Shutdown/restart không làm mất publication/message đang xử lý.

Performance test cần dữ liệu và concurrency gần với production. Không dùng một benchmark nhỏ để kết luận hệ thống chịu được tải cao.

## 15. Checklist test data và cleanup

Test event thường tạo dữ liệu ở nhiều module và có thể chạy bất đồng bộ sau khi test method kết thúc.

- [ ] Mỗi test dùng ID riêng cho aggregate/event/correlation.
- [ ] Test không phụ thuộc thứ tự chạy.
- [ ] Cleanup xử lý dữ liệu do stimulus tạo ra.
- [ ] Cleanup được gọi cả khi assertion thất bại.
- [ ] Queue/topic test được cô lập hoặc reset có kiểm soát.
- [ ] Không purge tài nguyên dùng chung khi test chạy song song.
- [ ] Scheduled job không chạy ngoài ý muốn trong test.
- [ ] Clock có thể kiểm soát khi test timestamp/timeout.
- [ ] Async task đã hoàn tất trước khi test kết thúc hoặc được quản lý rõ.
- [ ] Fixture payload được giữ độc lập với implementation hiện tại.

Với Scenario, chú ý transaction của stimulus có thể độc lập với transaction của test method. Dùng cleanup callback hoặc test fixture phù hợp thay vì giả định rollback của test sẽ dọn mọi thứ.

## 16. Checklist CI và môi trường kiểm thử

Tổ chức test theo tầng để có phản hồi nhanh và vẫn kiểm tra được các ranh giới quan trọng.

| Tầng test | Nội dung | Khi chạy |
|---|---|---|
| Unit | Mapping, validation, handler logic, upcaster | Mỗi thay đổi liên quan |
| Module integration | Publisher/listener, transaction, module boundary | CI thường xuyên |
| Scenario | Async event/state expectation | CI thường xuyên |
| Persistence integration | Registry/outbox, schema, retry state | CI hoặc pipeline tích hợp |
| Broker integration | Routing, confirm, ack, redelivery, DLQ | CI có container/service phù hợp |
| Contract compatibility | Fixture và schema version cũ/mới | Khi event contract thay đổi |
| Load/resilience | Throughput, backlog, restart, failure injection | Pipeline chuyên biệt hoặc trước release |

- [ ] Test không phụ thuộc broker/database developer đang chạy trên máy cá nhân.
- [ ] Test container có phiên bản rõ và cấu hình tương thích production.
- [ ] CI không in secret hoặc payload nhạy cảm.
- [ ] Migration/schema được áp dụng trong test tích hợp.
- [ ] Test bất đồng bộ có timeout hữu hạn.
- [ ] Flaky test được điều tra, không chỉ tăng timeout.
- [ ] Có báo cáo test theo module và event flow.
- [ ] Test contract chạy khi event DTO hoặc schema thay đổi.

Không cần chạy toàn bộ test broker cho mỗi unit change nếu pipeline đã phân tầng hợp lý. Nhưng thay đổi topology, converter hoặc acknowledgement phải kích hoạt integration test tương ứng.

## 17. Ma trận tình huống tối thiểu

Ma trận sau là bộ tình huống nền để đánh giá một event flow quan trọng:

| Tình huống | Kết quả mong đợi |
|---|---|
| Publisher thành công | Event đúng type và payload được phát |
| Validation thất bại | Không phát event mô tả nghiệp vụ chưa xảy ra |
| Transaction commit | Listener AFTER_COMMIT được kích hoạt |
| Transaction rollback | Listener AFTER_COMMIT không chạy |
| Listener thành công | Side effect và publication state hoàn tất |
| Listener ném exception | Transaction listener rollback; lỗi quan sát được |
| Listener được resubmit | Side effect không bị nhân đôi |
| Duplicate event | Idempotency giữ trạng thái nghiệp vụ đúng |
| Event sai version | Từ chối/quarantine có kiểm soát |
| Broker không sẵn sàng | Outbox giữ công việc để gửi lại |
| Consumer restart | Message/publication được phục hồi theo semantics |
| Backlog tăng | Metric và alert phản ánh tuổi, tốc độ và số lượng |
| Event đến sai thứ tự | Sequence/invariant phát hiện và xử lý |
| Shutdown khi đang xử lý | Không mất công việc đã được persistence bảo vệ |

Không phải mọi event cần toàn bộ ma trận. Chọn test theo mức độ quan trọng, nhưng các luồng có side effect tài chính, tồn kho hoặc trạng thái đơn hàng cần bao phủ failure và duplicate chặt chẽ.

## 18. Quy trình dùng checklist trong code review

Khi review thay đổi event, có thể đi theo thứ tự:

1. Đọc event contract và xác định producer/consumer bị ảnh hưởng.
2. Kiểm tra transaction phase và sync/async semantics.
3. Kiểm tra module dependency và package API.
4. Xem unit test cho mapping/handler.
5. Xem module/Scenario test cho event dispatch.
6. Xem failure, retry, registry và idempotency test.
7. Nếu có transport, xem outbox/broker integration test.
8. Xem fixture/schema compatibility nếu payload thay đổi.
9. Xem log, metric và alert cho đường mới.
10. Xác nhận cleanup và test chạy ổn định trong CI.

Một thay đổi chỉ thêm field có thể cần contract fixture; thay đổi listener async cần Scenario và failure test; thay đổi exchange hoặc routing cần broker integration test. Chọn kiểm thử theo ranh giới bị tác động.

## 19. Lỗi thường gặp khi kiểm thử application events

**Chỉ verify publishEvent được gọi.** Điều đó không chứng minh listener được đăng ký hoặc side effect đúng. Bổ sung module integration/Scenario test.

**Assert async ngay sau khi publish.** Listener chưa chắc đã chạy. Chờ event hoặc state với timeout hữu hạn.

**Dùng @Transactional test mặc định rollback để kiểm tra AFTER_COMMIT.** Transaction không commit nên listener không chạy. Điều khiển transaction stimulus rõ ràng.

**Dùng Thread.sleep.** Test chậm và không xác định. Dùng Scenario, Awaitility hoặc latch.

**Mock toàn bộ ApplicationContext.** Có thể bỏ qua wiring, module boundary và transaction behavior. Giữ một số test tích hợp thật.

**Không test duplicate và retry.** Side effect có thể lặp khi resubmit hoặc redelivery. Kiểm tra idempotency ở mức trạng thái nghiệp vụ.

**Chỉ test broker bằng mock.** Không chứng minh routing, confirm, acknowledgement hoặc DLQ. Dùng broker integration test.

**Không giữ fixture schema cũ.** Consumer mới có thể không đọc được backlog/replay. Test tất cả version còn hỗ trợ.

**Cleanup không quản lý async task.** Test sau có thể nhận event từ test trước. Dùng ID riêng, cleanup và chờ hoàn tất.

**Đánh đồng registry với event store.** Test cần xác minh đúng chức năng publication tracking và dùng storage riêng cho replay dài hạn nếu cần.

## 20. Checklist trước release

- [ ] Event contract và owner đã được xác định.
- [ ] Publisher test bao phủ success và validation/rollback.
- [ ] Listener test bao phủ hành vi nghiệp vụ chính.
- [ ] Transaction phase được kiểm tra.
- [ ] Module boundary và dependency rule được xác minh.
- [ ] Async Scenario test có predicate và timeout.
- [ ] Registry/outbox persistence được kiểm tra nếu sử dụng.
- [ ] Retry, DLQ và resubmit được kiểm tra.
- [ ] Idempotency và ordering được kiểm tra theo yêu cầu.
- [ ] Broker routing/confirm/ack được kiểm tra nếu có.
- [ ] Schema compatibility và fixture cũ được kiểm tra.
- [ ] Correlation/log/metric có thể truy vết.
- [ ] Load/backpressure phù hợp với SLA.
- [ ] Test data và async cleanup ổn định.
- [ ] CI chạy đúng các tầng test bị ảnh hưởng.
- [ ] Runbook và cảnh báo phục hồi đã sẵn sàng.

Checklist kiểm thử application events không nhằm buộc mọi event phải có cùng một bộ test. Nó giúp chọn đúng bằng chứng cho từng ranh giới: publisher, transaction, listener, registry, broker và nghiệp vụ downstream. Khi test cả đường thành công lẫn lỗi, duplicate, replay và tải, hệ thống Spring Modulith có thể thay đổi an toàn hơn và đội vận hành có căn cứ rõ ràng để tin vào giao tiếp giữa các module.
