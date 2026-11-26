# Diễn giải test failure

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, kiểm thử giúp xác nhận application event được phát, định tuyến, xử lý và phục hồi đúng theo hợp đồng giữa các module. Khi một test thất bại, dòng báo đỏ chỉ cho biết một điều kiện mong đợi không được đáp ứng. Nó chưa tự nói nguyên nhân nằm ở logic nghiệp vụ, cấu hình Spring, transaction, bất đồng bộ, database, broker hay chính test.

**Diễn giải test failure** là quá trình chuyển từ tín hiệu thất bại sang một giả thuyết có bằng chứng, xác định boundary có vấn đề và chọn bước kiểm tra tiếp theo. Mục tiêu là hiểu test đang chứng minh điều gì, thực tế đã xảy ra điều gì, hai điều đó khác nhau ở đâu và bằng chứng nào phân biệt được các nguyên nhân có thể.

Một cách điều tra tốt bắt đầu từ failure đầu tiên, đọc assertion cùng stack trace, dựng lại timeline của test và kiểm tra đúng phạm vi phụ thuộc. Không nên sửa ngay assertion hoặc tăng timeout chỉ để làm test xanh khi chưa hiểu hành vi nào đã thay đổi.

## 1. Một test failure thực sự nói lên điều gì?

Test failure có thể đến từ nhiều loại tín hiệu:

- **Assertion failure:** kết quả thực tế khác kết quả mong đợi.
- **Exception:** test hoặc code được gọi ném lỗi ngoài dự kiến.
- **Timeout:** điều kiện chưa đạt trong khoảng thời gian cho phép.
- **Context/bootstrap failure:** Spring không tạo được ApplicationContext hoặc bean.
- **Infrastructure failure:** database, broker, HTTP service hoặc container không sẵn sàng.
- **Test discovery/execution failure:** test không được phát hiện, bị bỏ qua hoặc runner không thực thi như dự kiến.
- **Flaky failure:** cùng code và dữ liệu nhưng kết quả thay đổi giữa các lần chạy.

Cần phân biệt test failure với test error theo cách test runner hiển thị. Assertion thường cho biết một kỳ vọng cụ thể sai; exception có thể khiến test dừng trước khi tới assertion. Tuy nhiên, tên phân loại của runner không đủ để kết luận nguyên nhân. Một assertion có thể thất bại do môi trường, còn exception có thể là bug nghiệp vụ.

Ví dụ, test chờ InventoryReserved nhưng timeout. Điều đó chỉ chứng minh event chưa được quan sát trong thời hạn test. Nó chưa chứng minh publisher không phát event: listener có thể chưa được đăng ký, transaction chưa commit, executor bị nghẽn, database ghi thất bại hoặc test đang chờ sai điều kiện.

## 2. Đọc failure theo thứ tự

Khi test thất bại, hãy thu thập thông tin theo thứ tự để tránh bị cuốn vào các dòng log thứ yếu:

1. Tên test, class, module và test runner.
2. Failure đầu tiên theo thời gian, không chỉ failure cuối cùng trong báo cáo.
3. Loại failure: assertion, exception, timeout, bootstrap hay infrastructure.
4. Expected và actual value, nếu có.
5. Exception type, message và nguyên nhân lồng bên trong (root cause).
6. Stack trace tại frame đầu tiên thuộc code của dự án.
7. Log và event timeline ngay trước thời điểm thất bại.
8. Trạng thái database, queue, publication hoặc test fixture liên quan.

Ví dụ assertion:

~~~text
org.opentest4j.AssertionFailedError:
expected: <COMPLETED>
 but was: <WAITING_FOR_PAYMENT>
    at OrderScenarioTests.paymentCapturedCompletesOrder(OrderScenarioTests.java:84)
~~~

Điều có thể kết luận ngay là test quan sát saga ở trạng thái WAITING_FOR_PAYMENT tại thời điểm assertion, trong khi kỳ vọng COMPLETED. Chưa thể kết luận Payment listener không chạy. Cần xem event PaymentCaptured đã được phát chưa, process manager đã nhận chưa, command tiếp theo có được ghi outbox không và test đã chờ đúng trạng thái cuối chưa.

Không chỉ đọc dòng cuối stack trace. Các frame của framework cho biết đường đi qua Spring, JUnit hoặc broker client; frame đầu tiên trong code ứng dụng thường chỉ ra nơi exception được ném hoặc assertion được thực hiện.

## 3. Phân biệt expected, actual và điều kiện quan sát

Assertion luôn có ba phần cần hiểu:

- **Expected:** hợp đồng hoặc trạng thái test cho rằng phải xảy ra.
- **Actual:** giá trị test thực sự quan sát được.
- **Observation point:** thời điểm và cách test đọc giá trị đó.

Một expected đúng về nghiệp vụ vẫn có thể được kiểm tra quá sớm. Ví dụ, listener chạy bất đồng bộ và test đọc repository ngay sau khi publish event. Actual là trạng thái cũ vì consumer chưa hoàn tất, không nhất thiết vì logic sai.

Ngược lại, một test có thể chờ quá lâu và vô tình che giấu độ trễ vượt SLO. Hãy xác định timeout có phải giới hạn kỹ thuật của test hay phản ánh yêu cầu nghiệp vụ.

Khi assertion thất bại, viết lại thành câu rõ ràng: “Tại thời điểm T, test đọc trạng thái S, trong khi hành vi yêu cầu trạng thái E sau điều kiện C.” Câu này buộc việc điều tra xem xét cả dữ liệu, timeline và điều kiện kích hoạt.

## 4. Tìm failure đầu tiên và phân biệt lỗi dây chuyền

Một test suite có thể hiển thị hàng chục lỗi sau một nguyên nhân gốc. Ví dụ, Spring context không khởi động được khiến mọi test dùng context đó đều lỗi. Nếu chỉ sửa từng assertion phía sau, sẽ mất thời gian mà không giải quyết nguyên nhân.

Hãy tìm lỗi đầu tiên theo trình tự thực thi:

- Lỗi tạo context có thể làm các test sau cùng context thất bại.
- Database không khởi động có thể gây hàng loạt connection timeout.
- Một test không cleanup queue có thể làm test tiếp theo nhận message cũ.
- Một migration thất bại có thể khiến repository test lỗi vì schema không đúng.
- Một event handler ném exception có thể khiến nhiều assertion downstream cùng timeout.

Nhóm các failure theo cùng root cause, exception type, context hoặc dependency. Nếu nhiều test có cùng lỗi đầu tiên, điều tra failure chung trước khi đọc từng assertion còn lại.

Tuy nhiên, không mặc định mọi lỗi xuất hiện sau là hệ quả. Một lần chạy có thể có nhiều failure độc lập. Sau khi sửa nguyên nhân gốc, chạy lại phạm vi phù hợp để xem failure nào còn tồn tại.

## 5. Phân loại nguyên nhân theo boundary

Một cách hữu ích là gắn failure với boundary có thể tạo ra nó:

| Nhóm | Dấu hiệu thường gặp | Bằng chứng cần tìm |
|---|---|---|
| Domain/application logic | Kết quả nghiệp vụ hoặc state transition sai | Input, state trước/sau, nhánh quyết định |
| Module wiring | Bean hoặc listener không được tạo/đăng ký | ApplicationContext, component scan, module boundary |
| Transaction | Hành vi phụ thuộc commit/rollback sai | Transaction timeline, transaction manager, database state |
| Async execution | Timeout hoặc kết quả đến muộn | Executor, thread, queue task, completion condition |
| Event publication | Publication thiếu hoặc chưa hoàn tất | Event ID, registry state, listener outcome |
| Broker/transport | Routing, ACK, redelivery hoặc serialization lỗi | Queue/topic, headers, broker log, consumer log |
| Test fixture/isolation | Dữ liệu cũ, test phụ thuộc thứ tự | Seed data, cleanup, namespace, execution order |
| Infrastructure | Connection refused, resource unavailable | Health, endpoint, container logs, credentials |
| Test expectation | Assertion dựa vào implementation hoặc thời điểm sai | Contract, observation point, setup và assertion |

Đây là cách phân loại để định hướng, không phải cây quyết định tuyệt đối. Một lỗi transaction có thể biểu hiện thành timeout async; một lỗi fixture có thể làm domain assertion sai. Hãy dùng bằng chứng để thu hẹp phạm vi.

## 6. Đọc stack trace và root cause

Stack trace thường có nhiều lớp exception. Exception ngoài cùng có thể là **ListenerExecutionFailedException**, trong khi nguyên nhân bên trong là constraint violation, conversion error hoặc lỗi nghiệp vụ.

Cách đọc:

1. Bắt đầu từ exception ngoài cùng để hiểu framework đang báo lỗi ở giai đoạn nào.
2. Đi qua các chuỗi **Caused by** tới nguyên nhân sâu nhất có ý nghĩa.
3. Tìm frame đầu tiên thuộc code ứng dụng.
4. Xác định input hoặc message liên quan tới frame đó.
5. Đối chiếu với log cùng correlationId/eventId.

Ví dụ:

~~~text
ListenerExecutionFailedException: Listener method failed
Caused by: DataIntegrityViolationException
Caused by: SQLIntegrityConstraintViolationException:
duplicate key value violates unique constraint "uq_event_id"
    at InboxRepository.insert(InboxRepository.java:52)
    at InventoryEventHandler.handle(InventoryEventHandler.java:41)
~~~

Đoạn này gợi ý insert inbox gặp duplicate key. Có thể đây là duplicate delivery bình thường nhưng repository chưa xử lý insert-if-absent; cũng có thể test dùng eventId trùng ngoài dự kiến. Cần kiểm tra consumer scope, fixture và transaction semantics trước khi sửa unique constraint.

Không bỏ qua exception đầu tiên trong log nếu một listener retry nhiều lần. Lỗi ở lần đầu có thể khác lỗi cuối cùng sau khi retry hoặc sau khi message được dead-letter.

## 7. Diễn giải lỗi khởi tạo Spring context

Nếu test fail trước khi method test chạy, hãy xem đây là lỗi bootstrap cho tới khi có bằng chứng khác. Những nguyên nhân phổ biến:

- Bean không được tìm thấy hoặc có nhiều candidate.
- Configuration chỉ được bật ở profile khác.
- Dependency ngoài bị tạo trong context nhưng không có endpoint test.
- Module bootstrap mode không bao gồm dependency cần thiết.
- Bean test double không được đăng ký hoặc bị trùng với bean thật.
- Circular dependency hoặc module dependency không hợp lệ.
- Property bắt buộc bị thiếu hoặc sai kiểu.

Với **@ApplicationModuleTest**, kiểm tra module test đang nằm trong package nào và bootstrap mode có phù hợp không. **STANDALONE**, **DIRECT_DEPENDENCIES** và **ALL_DEPENDENCIES** tạo phạm vi context khác nhau. Một test chạy ở mode hẹp có thể thiếu bean mà mode rộng hơn có; điều đó không tự động có nghĩa phải tăng mode. Hãy xác định dependency đó có thuộc hợp đồng module cần kiểm tra hay nên được thay bằng test double.

Đọc phần đầu của context failure và **Caused by** đầu tiên có liên quan. Các lỗi “ApplicationContext failure threshold exceeded” ở test sau có thể chỉ là hậu quả của lần khởi tạo đầu tiên thất bại.

## 8. Diễn giải lỗi event không tới listener

Khi test publish event nhưng listener không tạo ra kết quả, hãy dựng lại chuỗi:

1. Use case có thực sự được gọi không?
2. Publisher có được gọi với event đúng type và payload không?
3. Event được publish trong transaction nào?
4. Listener có được Spring đăng ký trong context test không?
5. Listener có điều kiện filter, profile hoặc qualifier nào không?
6. Event có được phát sau commit hay bị rollback?
7. Listener có chạy bất đồng bộ không?
8. Listener có ném exception hoặc retry không?
9. Test đang quan sát kết quả ở đâu và sau bao lâu?

Không dùng một mock publisher để kết luận event bus thật đã dispatch. Nếu mục tiêu là kiểm tra listener registration, hãy publish event qua Spring mechanism trong module test. Nếu mục tiêu chỉ là logic handler, gọi application service trực tiếp là phạm vi unit test phù hợp.

Với Spring Modulith, kiểm tra annotation listener, package/module placement, bootstrap configuration và loại listener được dùng. Listener thông thường, transactional listener và **@ApplicationModuleListener** có semantics khác nhau; đừng giả định mọi listener đều chạy ở cùng thời điểm hoặc cùng thread.

## 9. Diễn giải lỗi transaction và AFTER_COMMIT

Một test có thể thất bại vì event được phát khi transaction chưa commit, hoặc vì test không commit transaction nên listener AFTER_COMMIT không được kích hoạt.

Hãy lập timeline:

~~~text
T1  Bắt đầu transaction
T2  Use case thay đổi dữ liệu
T3  Application event được publish
T4  Transaction commit hoặc rollback
T5  Transactional listener đủ điều kiện được kích hoạt
T6  Listener xử lý và ghi dữ liệu đích
T7  Test quan sát trạng thái
~~~

Nếu test method tự động rollback khi kết thúc, T4 có thể là rollback thay vì commit. Khi đó listener AFTER_COMMIT không chạy theo kỳ vọng. Nếu listener async, T7 có thể xảy ra trước T6.

Để diễn giải chính xác, xác nhận transaction manager, propagation, phase của listener, test transaction và cách test chờ. Kiểm tra dữ liệu nguồn và đích sau commit. Không chỉ verify method publisher đã được gọi, vì publish event và listener hoàn tất là hai mốc khác nhau.

Nếu assertion yêu cầu listener không chạy khi rollback, test cần thực hiện rollback có chủ đích và quan sát tác dụng phụ ở module nhận. Nếu yêu cầu listener chạy sau commit, phải có một commit thực sự trong kịch bản test.

## 10. Diễn giải lỗi bất đồng bộ và timeout

Timeout cho biết điều kiện chưa đạt trong thời gian chờ. Với listener bất đồng bộ, có thể có nhiều nguyên nhân:

- Executor chưa chạy task hoặc thread pool đã bão hòa.
- Listener đang chờ database connection hoặc dependency ngoài.
- Task bị chặn bởi lock hoặc deadlock.
- Event chưa được commit nên listener chưa được kích hoạt.
- Test chờ sai trạng thái hoặc dùng ID khác với event đã phát.
- Listener đã thất bại nhưng exception chỉ được ghi log ở thread khác.
- Timeout của test ngắn hơn độ trễ hợp lệ trong môi trường CI.

Hãy kiểm tra log theo eventId/correlationId, executor metrics, thread dump nếu có, thời gian query và trạng thái database. Với Awaitility, điều kiện chờ nên quan sát kết quả nghiệp vụ:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(orderRepository.findStatus(orderId))
            .isEqualTo(OrderStatus.COMPLETED)
    );
~~~

Không tăng timeout một cách máy móc. Trước tiên xác định thời gian thực tế và yêu cầu nghiệp vụ. Nếu listener hoàn tất trong 8 giây trong khi test cho 2 giây, cần tìm xem đó là môi trường chậm, executor nghẽn hay regression hiệu năng. Timeout dài hơn có thể giảm flaky nhưng cũng che giấu lỗi tiến độ.

## 11. Diễn giải lỗi Event Publication Registry

Event Publication Registry theo dõi publication tới transactional listeners. Khi test báo publication incomplete hoặc resubmit không cho kết quả, cần phân biệt:

- Listener chưa được kích hoạt do transaction chưa commit.
- Listener đã chạy nhưng ném exception.
- Publication persistence không được cấu hình như test kỳ vọng.
- Listener hoàn tất nhưng trạng thái publication chưa được cập nhật.
- Test đọc registry trước khi listener async kết thúc.
- Resubmit không chọn publication hoặc listener phù hợp.
- Test đang dùng persistence/context khác với nơi event được publish.

Hãy ghi nhận event type, listener identifier, publication state, thời điểm tạo, thời điểm hoàn tất và exception cuối. Kiểm tra trạng thái qua API được hỗ trợ của phiên bản Spring Modulith thay vì phụ thuộc trực tiếp vào bảng nội bộ nếu không cần.

Một publication incomplete không tự chứng minh event đã mất. Nó cho biết publication chưa được ghi nhận hoàn tất theo cơ chế registry. Điều tra listener outcome và transaction trước khi resubmit, đặc biệt khi handler có tác dụng phụ ngoài database. Consumer cần idempotency để resubmit không tạo tác dụng phụ lặp.

## 12. Diễn giải lỗi broker và transport

Khi event đi qua RabbitMQ hoặc Kafka, cần tách lỗi ở producer, broker, consumer và adapter.

**Producer:** serialization fail, publish exception, routing key sai, broker confirm không đến hoặc outbox không được dispatch.

**Broker:** exchange/queue/topic chưa tồn tại, binding sai, permission thiếu, message hết TTL, partition/queue unavailable hoặc broker resource alarm.

**Consumer:** deserialize fail, listener exception, ACK/NACK sai, offset không commit hoặc consumer group không nhận partition.

**Adapter:** header mapping, converter, retry interceptor, error handler hoặc destination configuration không khớp.

Đối chiếu eventId, routing key/topic, partition, delivery tag/offset, correlation ID và timestamp giữa các log. Kiểm tra queue depth, unacknowledged count, redelivery, DLQ hoặc consumer lag. Không kết luận publisher không gửi chỉ vì listener chưa xử lý; message có thể đã tới broker nhưng consumer không nhận hoặc không deserialize được.

Test dùng fake broker không chứng minh protocol semantics. Nếu failure liên quan ACK, redelivery, routing hoặc broker limits, cần kiểm tra bằng broker integration test trong môi trường cô lập.

## 13. Phân biệt lỗi code với lỗi môi trường

Một lỗi môi trường thường có dấu hiệu dependency không sẵn sàng, DNS/connection failure, thiếu tài nguyên, credentials hoặc container startup. Một lỗi code thường có input hợp lệ nhưng kết quả sai lặp lại, exception từ logic hoặc contract mismatch.

Tuy nhiên, môi trường có thể làm lộ bug code: database chậm khiến race condition xuất hiện; CI chạy song song làm lộ test dùng dữ liệu chung; clock khác timezone làm sai deadline; broker restart làm lộ consumer không idempotent.

Để phân biệt, so sánh:

- Cùng commit và test có fail local lẫn CI không?
- Cùng fixture và cấu hình có cho kết quả ổn định không?
- Dependency health có bình thường ở thời điểm fail không?
- Failure có liên quan tới thời gian, concurrency hoặc thứ tự test không?
- Có thay đổi profile, environment variable, timezone, locale hoặc version service không?
- Khi chạy riêng test, failure có biến mất không?

“Chạy lại thấy pass” chỉ chứng minh failure không tái hiện ở lần đó. Nó không chứng minh nguyên nhân là môi trường hoặc flaky test đã được khắc phục.

## 14. Nhận diện flaky test và race condition

Flaky test là test có thể pass hoặc fail mà không có thay đổi đáng kể ở code hay input được kiểm soát. Các nguyên nhân phổ biến:

- Dựa vào Thread.sleep() và timing không ổn định.
- Dùng Instant.now() trực tiếp thay vì Clock được kiểm soát.
- Chia sẻ static state, database row, queue hoặc port giữa test.
- Test chạy song song và ghi cùng business key.
- Không cleanup message hoặc background task.
- Dựa vào thứ tự event khi hệ thống không bảo đảm ordering.
- Dùng random data không ghi lại seed.
- Chờ một điều kiện không đại diện cho hoàn tất nghiệp vụ.

Để điều tra, lưu seed, test order, thread/executor context, eventId và timestamp. Chạy riêng test và chạy trong suite có thể giúp phát hiện phụ thuộc thứ tự; chạy lặp lại có kiểm soát giúp xác định tần suất. Không biến việc chạy lặp thành bằng chứng rằng test đã được sửa.

Cách khắc phục thường là cô lập dữ liệu, dùng Clock cố định, chờ điều kiện có ý nghĩa, đồng bộ thread đúng cách, thiết lập namespace riêng và tránh chia sẻ mutable state. Không chỉ tăng retry cho test runner nếu lỗi phản ánh race condition thật.

## 15. Diễn giải assertion sai do test fixture

Fixture có thể tạo trạng thái khác với giả định của test. Ví dụ, test mong listener xử lý OrderConfirmed nhưng fixture lại tạo event có schemaVersion cũ, orderId trùng hoặc state saga đã ở WAITING_FOR_PAYMENT.

Kiểm tra fixture theo các lớp:

- Dữ liệu ban đầu trong database và cache.
- Event type, eventId, schemaVersion và payload.
- CorrelationId, causationId và aggregate version.
- Trạng thái publication, inbox và outbox.
- Queue/topic có message từ test trước không.
- Clock, timezone và deadline.
- Mock/stub có trả đúng kết quả theo nhánh test không.

Fixture nên nhỏ, rõ và khai báo trực tiếp những field ảnh hưởng tới hành vi. Tránh factory tạo nhiều mặc định ẩn khiến người đọc khó biết state thực tế. Khi failure xảy ra, in hoặc log metadata cần thiết để tái tạo, nhưng không ghi payload nhạy cảm.

## 16. Đọc diff và thay đổi gần nhất

Khi test bắt đầu fail sau một thay đổi, đối chiếu failure với diff có liên quan:

- DTO/event schema hoặc serializer vừa thay đổi?
- Transaction boundary hoặc annotation listener thay đổi?
- Package/module placement ảnh hưởng component scanning?
- Profile hoặc property đổi bootstrap mode?
- Retry/acknowledgement configuration thay đổi?
- Migration làm thay đổi constraint hoặc column?
- Test fixture, seed hoặc cleanup bị sửa?
- Version broker/client/framework thay đổi?

Tập trung vào thay đổi có quan hệ nhân quả với failure. Không đọc hoặc revert toàn bộ diff một cách máy móc. Một failure mới sau commit không chứng minh dòng code cuối cùng là nguyên nhân; có thể commit chỉ làm lộ một vấn đề tồn tại từ trước.

Nếu không có diff gần đây, vẫn có thể failure do dependency ngoài thay đổi, dữ liệu test tồn dư hoặc hạ tầng. Ghi nhận version và trạng thái dependency để tránh kết luận chỉ từ lịch sử Git.

## 17. Quy trình tái hiện và thu hẹp phạm vi

Sau khi có giả thuyết ban đầu, tái hiện theo phạm vi tăng dần:

1. Chạy đúng test đang fail với cùng cấu hình và fixture.
2. Chạy class hoặc nhóm test liên quan để phát hiện shared state.
3. Chạy module test với bootstrap mode đã xác định.
4. Thêm database hoặc broker thật nếu giả thuyết liên quan tới semantics của chúng.
5. Chạy suite rộng hơn để kiểm tra tương tác và thứ tự.
6. So sánh kết quả trước/sau khi thay đổi một yếu tố.

Mỗi lần thử chỉ thay đổi một yếu tố quan trọng: transaction commit, event payload, executor, broker, test data hoặc timeout. Nếu cùng lúc đổi nhiều cấu hình, kết quả pass không chỉ ra yếu tố nào đã giải quyết lỗi.

Ghi lại command, profile, test name, seed, dependency version và kết quả. Nếu failure chỉ xảy ra trong CI, so sánh môi trường và concurrency trước khi thêm điều kiện đặc biệt cho CI.

## 18. Sửa nguyên nhân và giữ assertion có ý nghĩa

Sau khi xác định nguyên nhân, sửa tại boundary sở hữu hành vi:

- Domain state sai: sửa quy tắc hoặc transition.
- Listener không đăng ký: sửa wiring/module placement.
- Commit phase sai: sửa transaction boundary hoặc test setup.
- Duplicate side effect: sửa idempotency/inbox.
- Routing sai: sửa adapter/destination configuration.
- Fixture bẩn: sửa setup/cleanup và isolation.
- Timeout do nghẽn thật: xử lý bottleneck hoặc điều chỉnh capacity theo SLO.

Không làm test pass bằng cách xóa assertion, bỏ qua exception, tăng timeout tùy tiện hoặc mock chính thành phần cần kiểm tra. Nếu expected không còn phù hợp vì contract đã thay đổi có chủ đích, cập nhật assertion cùng contract và giải thích thay đổi nghiệp vụ.

Một test tốt nên thất bại khi hành vi bị phá vỡ và pass khi hợp đồng được đáp ứng. Assertion cần kiểm tra điều có ý nghĩa với người dùng hoặc module consumer, không phụ thuộc quá mức vào thứ tự gọi method hay chi tiết nội bộ.

## 19. Viết báo cáo test failure có thể hành động

Một báo cáo hữu ích cần ngắn gọn nhưng đủ bằng chứng để người khác tiếp tục điều tra:

| Trường | Nội dung |
|---|---|
| Test | Class, method, module và profile |
| Kết quả | Assertion, exception, timeout hoặc bootstrap |
| Expected/actual | Giá trị mong đợi và quan sát |
| Root cause hiện tại | Đã xác nhận hay mới là giả thuyết |
| Evidence | Stack frame, event ID, log, state hoặc broker metric |
| Boundary | Domain, module, transaction, async, registry, broker hay fixture |
| Reproduction | Command và điều kiện để tái hiện |
| Thay đổi đề xuất | Sửa ở đâu và vì sao |
| Validation còn thiếu | Kịch bản nào chưa được xác nhận |

Phân biệt rõ **đã xác nhận**, **nghi ngờ** và **chưa biết**. Không gọi một giả thuyết là root cause khi chưa có bằng chứng phân biệt. Nếu test fail vì dependency ngoài không sẵn sàng, báo cáo đúng là infrastructure blocker; không ghi thành bug nghiệp vụ.

Ví dụ báo cáo:

~~~text
Test: OrderScenarioTests.paymentCapturedCompletesOrder
Failure: timeout waiting for COMPLETED
Observed: saga remains WAITING_FOR_PAYMENT
Evidence: PaymentCaptured event exists; no ArrangeShipment command in outbox
Hypothesis: process manager did not accept the event for the current saga state
Next check: compare event sagaId/correlationId and persisted saga version
Status: hypothesis, not yet confirmed
~~~

Báo cáo này cho biết bằng chứng và bước tiếp theo mà không khẳng định quá sớm listener hoặc broker là nguyên nhân.

## 20. Quy trình diễn giải test failure

Khi nhận một test failure, thực hiện theo trình tự:

1. Xác định test, môi trường, profile và thời điểm xảy ra.
2. Tìm failure đầu tiên và phân loại assertion, exception, timeout, bootstrap hay infrastructure.
3. Đọc expected, actual, observation point và root cause trong stack trace.
4. Xác định boundary có thể tạo ra sai lệch.
5. Dựng timeline của publish, transaction, listener, registry, broker và assertion.
6. Đối chiếu eventId/correlationId cùng state ở nguồn và đích.
7. Kiểm tra fixture, test isolation, async và dependency health.
8. Tạo một giả thuyết có thể kiểm chứng.
9. Tái hiện với phạm vi nhỏ nhất rồi mở rộng khi cần.
10. Sửa nguyên nhân tại boundary sở hữu và giữ assertion theo contract.
11. Chạy lại test liên quan, sau đó chạy phạm vi suite phù hợp.
12. Ghi kết luận, bằng chứng còn thiếu và rủi ro chưa được kiểm tra.

Diễn giải test failure là kỹ năng nối assertion với hành vi thực tế và timeline của hệ thống. Khi phân biệt expected/actual, tìm failure đầu tiên, đọc root cause, xác định module và transaction boundary, rồi kiểm tra event cùng correlation metadata, đội phát triển có thể tránh sửa triệu chứng. Báo cáo cần tách bằng chứng khỏi giả thuyết và nêu bước tái hiện cụ thể để việc xử lý failure có thể tiếp tục một cách nhất quán.

