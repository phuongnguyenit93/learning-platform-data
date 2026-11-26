# Kiểm thử saga

Saga là một quy trình nghiệp vụ kéo dài qua nhiều transaction và thường đi qua nhiều module hoặc service. Mỗi bước commit độc lập; nếu một bước sau thất bại, hệ thống thực hiện các hành động bù để đưa quy trình về một trạng thái nghiệp vụ chấp nhận được. Vì không có một transaction ACID bao trùm toàn bộ quy trình, kiểm thử saga phải xác minh cả đường thành công, các nhánh lỗi, trạng thái trung gian, retry, duplicate, timeout và khả năng phục hồi sau khi tiến trình dừng.

Trong Spring Modulith, application events giúp các module giao tiếp qua hợp đồng nghiệp vụ và bảo vệ ranh giới module. Một process manager có thể điều phối các bước bằng cách nhận event, lưu trạng thái quy trình và phát command hoặc event tiếp theo. Spring Modulith cung cấp cơ chế event publication và hỗ trợ kiểm thử ranh giới module; nó không tự cung cấp một saga engine hoàn chỉnh. State machine, persistence, timeout, compensation và chính sách retry vẫn cần được thiết kế trong ứng dụng.

Bài này xây dựng chiến lược kiểm thử saga/process manager theo từng lớp, từ transition đơn lẻ tới luồng tích hợp có persistence và broker. Các ví dụ dùng quy trình đặt hàng gồm giữ hàng, thanh toán và giao vận.

## 1. Saga cần được kiểm thử như một quy trình nhiều transaction

Giả sử một đơn hàng cần thực hiện các bước:

1. Tạo đơn hàng và bắt đầu saga.
2. Yêu cầu kho giữ hàng.
3. Yêu cầu cổng thanh toán xác thực hoặc thu tiền.
4. Yêu cầu đơn vị vận chuyển tạo lệnh giao hàng.
5. Đánh dấu đơn hàng hoàn tất.

Mỗi bước có thể commit ở một module hoặc hệ thống khác. Nếu thanh toán thành công nhưng tạo vận đơn thất bại, không thể rollback transaction thanh toán bằng cách rollback transaction của Order. Saga cần phát một hành động bù, ví dụ yêu cầu hoàn tiền hoặc hủy authorization.

~~~mermaid
sequenceDiagram
    participant O as Order
    participant S as Order Saga
    participant I as Inventory
    participant P as Payment
    participant H as Shipping

    O->>S: OrderPlaced
    S->>I: ReserveInventory
    I-->>S: InventoryReserved
    S->>P: AuthorizePayment
    P-->>S: PaymentAuthorized
    S->>H: CreateShipment
    H-->>S: ShipmentCreated
    S->>O: OrderFulfillmentCompleted
~~~

Nhánh lỗi có thể đi theo chiều bù:

~~~mermaid
sequenceDiagram
    participant S as Order Saga
    participant I as Inventory
    participant P as Payment
    participant H as Shipping

    S->>I: ReserveInventory
    I-->>S: InventoryReserved
    S->>P: AuthorizePayment
    P-->>S: PaymentAuthorized
    S->>H: CreateShipment
    H-->>S: ShipmentRejected
    S->>P: RefundPayment
    P-->>S: PaymentRefunded
    S->>I: ReleaseInventory
    I-->>S: InventoryReleased
    S->>S: Mark compensation completed
~~~

Đây là quy trình minh họa. Thứ tự compensation phải phản ánh quy tắc nghiệp vụ thực tế. Nếu payment chỉ được authorize chứ chưa capture, hành động bù có thể là void authorization thay vì refund. Không nên dùng một tên chung cho các hành động có ý nghĩa tài chính khác nhau.

Một test saga tốt xác minh không chỉ event cuối cùng mà còn các transition và side effect đã xảy ra trên toàn bộ quy trình.

## 2. Xác định mô hình saga trước khi viết test

### 2.1. Orchestration và choreography

Hai cách tổ chức saga dẫn tới trọng tâm kiểm thử khác nhau.

| Kiểu | Cách hoạt động | Trọng tâm kiểm thử |
|---|---|---|
| Orchestration | Một process manager/saga coordinator quyết định bước tiếp theo | State transition, command được phát, timeout, compensation và phục hồi coordinator |
| Choreography | Mỗi module phản ứng với event và phát event tiếp theo | Hợp đồng event, chuỗi phản ứng, vòng lặp event, điều kiện kết thúc và trạng thái tổng thể |

Với orchestration, có thể kiểm thử process manager như một state machine thuần: đưa vào trạng thái hiện tại và event mới, rồi xác minh trạng thái mới cùng command cần phát.

Với choreography, không có một nơi duy nhất biết toàn bộ quy trình. Cần kiểm thử từng consumer và thêm integration test xác minh chuỗi event kết hợp tạo ra kết quả nghiệp vụ đúng.

Không nên trộn hai kiểu một cách tùy tiện. Dù chọn kiểu nào, hệ thống vẫn cần định danh saga, trạng thái bền vững, chính sách duplicate, timeout và cách xử lý event đến muộn.

### 2.2. Xác định state machine

Trước khi viết test, liệt kê trạng thái và sự kiện hợp lệ. Ví dụ:

| Trạng thái hiện tại | Event nhận được | Trạng thái tiếp theo | Hành động |
|---|---|---|---|
| STARTED | InventoryReserved | WAITING_FOR_PAYMENT | AuthorizePayment |
| STARTED | InventoryRejected | COMPENSATING | Mark order rejected |
| WAITING_FOR_PAYMENT | PaymentAuthorized | WAITING_FOR_SHIPMENT | CreateShipment |
| WAITING_FOR_PAYMENT | PaymentRejected | COMPENSATING | ReleaseInventory |
| WAITING_FOR_SHIPMENT | ShipmentCreated | COMPLETED | Complete order |
| WAITING_FOR_SHIPMENT | ShipmentRejected | COMPENSATING | RefundPayment |
| COMPENSATING | CompensationCompleted | COMPENSATING hoặc COMPENSATED | Chạy bước bù kế tiếp hoặc kết thúc |
| COMPENSATING | CompensationFailed | COMPENSATION_FAILED | Retry/cảnh báo |

Bảng là mô hình tham khảo. Một saga thực tế có thể có nhiều bước, nhiều loại compensation và trạng thái chờ retry.

Mỗi transition nên xác định:

- Event nào được chấp nhận.
- Điều kiện nghiệp vụ cần thỏa.
- Trạng thái được lưu.
- Command/event tiếp theo được phát.
- Hành động nào không được phép lặp.
- Cách xử lý event duplicate, muộn hoặc không hợp lệ.

Từ bảng transition có thể sinh ra bộ test có cấu trúc, tránh chỉ kiểm tra happy path.

## 3. Kiểm thử state machine/process manager bằng unit test

Process manager nên tách quyết định nghiệp vụ khỏi cơ chế vận chuyển message. Một cách thiết kế là hàm quyết định nhận state và event, trả về state mới cùng danh sách action. Hàm này có thể kiểm thử không cần Spring context hoặc broker.

Ví dụ model:

~~~java
public enum OrderSagaStatus {
    STARTED,
    WAITING_FOR_PAYMENT,
    WAITING_FOR_SHIPMENT,
    COMPENSATING,
    COMPLETED,
    COMPENSATED,
    COMPENSATION_FAILED
}

public record OrderSagaState(
        UUID sagaId,
        UUID orderId,
        OrderSagaStatus status,
        boolean inventoryReserved,
        boolean paymentAuthorized,
        boolean shipmentCreated,
        long version
) {}
~~~

Kết quả xử lý có thể được biểu diễn bằng decision:

~~~java
public record SagaDecision(
        OrderSagaState state,
        List<Object> outgoingMessages
) {}
~~~

Ví dụ xử lý kết quả giữ hàng:

~~~java
public SagaDecision onInventoryReserved(
        OrderSagaState current,
        InventoryReserved event
) {
    if (current.status() != OrderSagaStatus.STARTED) {
        return duplicateOrReject(current, event);
    }

    OrderSagaState next = new OrderSagaState(
            current.sagaId(),
            current.orderId(),
            OrderSagaStatus.WAITING_FOR_PAYMENT,
            true,
            false,
            false,
            current.version() + 1
    );

    return new SagaDecision(
            next,
            List.of(new AuthorizePayment(
                    current.sagaId(),
                    current.orderId()
            ))
    );
}
~~~

Unit test tập trung vào hành vi:

~~~java
@Test
void inventoryReservedRequestsPaymentAuthorization() {
    OrderSagaState current = startedSaga();
    InventoryReserved event = inventoryReservedFor(current);

    SagaDecision decision = processManager.onInventoryReserved(
            current,
            event
    );

    assertThat(decision.state().status())
            .isEqualTo(OrderSagaStatus.WAITING_FOR_PAYMENT);
    assertThat(decision.state().inventoryReserved()).isTrue();
    assertThat(decision.outgoingMessages())
            .containsExactly(new AuthorizePayment(
                    current.sagaId(),
                    current.orderId()
            ));
}
~~~

Test này không cần mock RabbitMQ, database hoặc Spring. Nó xác minh quyết định của state machine một cách nhanh và ổn định.

### 3.1. Kiểm thử transition hợp lệ và không hợp lệ

Với mỗi transition, cần có test cho:

- Event hợp lệ ở đúng trạng thái.
- Event cùng loại nhưng tới sai trạng thái.
- Event có sagaId hoặc aggregateId không khớp.
- Event có version cũ.
- Event duplicate.
- Event đến sau khi saga đã kết thúc.
- Event thiếu dữ liệu bắt buộc.

Ví dụ PaymentAuthorized chỉ được chấp nhận khi saga đang WAITING_FOR_PAYMENT. Nếu nhận PaymentAuthorized khi saga đang STARTED, process manager không nên âm thầm chuyển trạng thái. Có thể ghi nhận event không hợp lệ, đưa vào quarantine hoặc áp dụng quy tắc phục hồi cụ thể.

### 3.2. Kiểm thử bất biến nghiệp vụ

Ngoài trạng thái cụ thể, xác minh invariant luôn đúng:

- Không tạo shipment nếu payment chưa được authorize/capture theo yêu cầu.
- Không hoàn tiền nếu chưa có khoản thanh toán tương ứng.
- Không release inventory nếu chưa giữ hàng thành công.
- Saga COMPLETED không được phát compensation ngoài chính sách.
- Saga COMPENSATED không được quay lại trạng thái xử lý bình thường.
- Một saga không được hoàn tất hai lần.
- Mọi outgoing action phải gắn với đúng sagaId và orderId.

Invariant thường phát hiện lỗi mà test từng method riêng lẻ bỏ sót.

## 4. Kiểm thử happy path end-to-end

Happy path xác minh toàn bộ chuỗi event/command đi qua các module và kết thúc ở trạng thái đúng.

Một test tích hợp có thể khởi tạo đơn hàng, chờ các module xử lý và kiểm tra:

- Order được tạo.
- Inventory có reservation tương ứng.
- Payment có trạng thái authorized/captured phù hợp.
- Shipping có shipment.
- Saga chuyển sang COMPLETED.
- Không có compensation được phát.
- Không còn message hoặc publication chưa xử lý trong phạm vi test.

Với Spring Modulith, có thể dùng test context theo module hoặc Spring Boot integration test để nạp các bean liên quan. Nếu kiểm thử ranh giới module, test nên chỉ mở module cần thiết và xác minh event được giao tới listener được công bố.

Không nên chỉ assert rằng publisher đã được gọi. Cần xác minh side effect ở module nhận và trạng thái saga cuối cùng.

### 4.1. Kiểm thử transaction và event publication

Nếu event được publish trong transaction nguồn, test cần xác minh:

- Transaction commit tạo dữ liệu nghiệp vụ và publication.
- Transaction rollback không để lại dữ liệu hoặc publication của event.
- Listener chạy sau commit theo cấu hình.
- Listener thất bại để lại publication chưa hoàn tất khi dùng registry bền vững.

Một lưu ý quan trọng: test method có transaction mặc định rollback khi kết thúc có thể không kích hoạt listener AFTER_COMMIT như mong đợi. Hãy chủ động commit transaction trong test hoặc dùng TransactionTemplate/TestTransaction để kiểm tra đúng pha commit.

Nếu listener bất đồng bộ, không dùng sleep cố định. Dùng Awaitility, latch hoặc điều kiện đồng bộ để đợi trạng thái cuối với timeout hữu hạn.

## 5. Kiểm thử compensation

Compensation là hành động nghiệp vụ mới, không phải rollback database xuyên nhiều module. Vì vậy mỗi bước bù cần được kiểm thử như một transition riêng và trong chuỗi saga.

Ví dụ: giữ hàng thành công, payment authorization thành công, nhưng shipping bị từ chối. Saga cần void/refund payment rồi release inventory theo chính sách.

Bộ test nên xác minh:

1. ShipmentRejected làm saga chuyển sang COMPENSATING.
2. Saga phát đúng yêu cầu compensation cho payment.
3. PaymentVoided/PaymentRefunded được nhận và lưu kết quả.
4. Chỉ sau khi bước payment bù thành công, saga mới phát ReleaseInventory nếu thứ tự nghiệp vụ yêu cầu như vậy.
5. InventoryReleased đưa saga tới COMPENSATED.
6. Order có trạng thái thất bại/hủy phù hợp.
7. Không phát lại bước bù đã hoàn tất khi event bị giao trùng.

Nếu compensation thất bại, saga phải giữ trạng thái chưa hoàn tất và có thể retry hoặc chuyển sang xử lý thủ công. Không đánh dấu COMPENSATED chỉ vì đã phát command bù.

### 5.1. Compensation không luôn đảo ngược hoàn toàn

Một số hành động bên ngoài không thể hoàn tác tuyệt đối. Email đã gửi không thể thu hồi; hàng đã giao có thể cần quy trình trả hàng; khoản tiền đã capture có thể cần refund bất đồng bộ.

Test cần xác minh kết quả nghiệp vụ chấp nhận được thay vì giả định trạng thái vật lý trở lại chính xác ban đầu. Ví dụ, refund pending có thể là trạng thái trung gian hợp lệ nếu hệ thống đã ghi nhận yêu cầu bù và đang chờ cổng thanh toán xác nhận.

### 5.2. Kiểm thử nhiều bước bù

Nếu saga có nhiều side effect, compensation thường chạy theo thứ tự ngược hoặc theo dependency graph của các bước đã hoàn thành. Hãy tạo test cho từng điểm lỗi có thể xảy ra:

| Điểm lỗi | Các bước đã hoàn tất | Hành động bù cần xác minh |
|---|---|---|
| Inventory reserve thất bại | Chưa có side effect downstream | Đánh dấu order không thể xử lý |
| Payment authorization thất bại | Inventory đã giữ | Release inventory |
| Shipment tạo thất bại | Inventory và payment đã hoàn tất | Void/refund payment, release inventory |
| Refund thất bại | Inventory và payment trước đó đã hoàn tất | Giữ saga ở trạng thái compensation pending/failed, retry refund |
| Release inventory thất bại | Refund đã thành công | Giữ trạng thái chưa bù xong, retry release |

Không chạy compensation cho bước chưa từng thành công. Lưu cờ/record kết quả từng bước để process manager biết hành động nào cần bù.

## 6. Kiểm thử retry, timeout và event đến muộn

Saga thường chờ phản hồi từ module khác hoặc hệ thống bên ngoài. Mỗi bước cần timeout và chính sách retry rõ ràng.

### 6.1. Retry có giới hạn

Test retry cần xác minh:

- Lỗi tạm thời làm tăng attempt count.
- Delay/backoff được tính đúng.
- Retry giữ nguyên commandId hoặc idempotency key.
- Hết số lần thử thì chuyển sang trạng thái cần can thiệp.
- Lỗi vĩnh viễn không bị retry vô hạn.
- Một lần retry thành công kết thúc đúng bước và không phát lặp command trước đó.

Không dùng Thread.sleep để kiểm tra backoff. Trừu tượng hóa scheduler/clock để test có thể kích hoạt thời điểm retry một cách xác định.

### 6.2. Timeout

Dùng Clock hoặc abstraction thời gian để tạo test xác định:

- Khi chưa tới deadline, saga vẫn chờ.
- Khi deadline hết, saga chuyển sang nhánh timeout.
- Timeout của bước giữ hàng có thể hủy saga mà không gọi refund.
- Timeout sau payment authorization phải kích hoạt hành động bù tương ứng.
- Event thành công đến sau timeout được xử lý theo chính sách rõ ràng.

Event đến sau timeout có thể là kết quả thật của một thao tác bên ngoài đã hoàn tất. Không được mặc định bỏ qua nó nếu bỏ qua sẽ làm rò rỉ reservation hoặc khoản thanh toán. Có thể cần ghi nhận kết quả muộn và phát compensation bổ sung.

### 6.3. Fake clock và scheduler

Ví dụ một test dùng Clock cố định:

~~~java
@Test
void sagaTimesOutAfterDeadline() {
    Clock clock = Clock.fixed(
            Instant.parse("2026-11-25T10:00:00Z"),
            ZoneOffset.UTC
    );

    OrderSagaState state = waitingForPayment(
            clock.instant(),
            Duration.ofMinutes(5)
    );

    SagaDecision beforeDeadline = processManager.onTimeoutCheck(
            state,
            clock.instant().plus(Duration.ofMinutes(4))
    );

    assertThat(beforeDeadline.state().status())
            .isEqualTo(OrderSagaStatus.WAITING_FOR_PAYMENT);

    SagaDecision afterDeadline = processManager.onTimeoutCheck(
            state,
            clock.instant().plus(Duration.ofMinutes(6))
    );

    assertThat(afterDeadline.state().status())
            .isEqualTo(OrderSagaStatus.COMPENSATING);
}
~~~

Ví dụ minh họa ý tưởng kiểm soát thời gian; API process manager thực tế tùy implementation. Điều quan trọng là test truyền thời điểm vào logic thay vì chờ đồng hồ thật.

## 7. Kiểm thử duplicate, ordering và idempotency

Event broker hoặc publication registry có thể giao lại event. Process manager phải xử lý duplicate an toàn.

Dùng sagaId + eventId hoặc một khóa nghiệp vụ phù hợp để nhận diện event đã áp dụng. Việc ghi nhận event và cập nhật trạng thái saga phải cùng transaction.

Test nên gửi cùng một event hai lần và xác minh:

- Trạng thái saga chỉ chuyển một lần.
- Command tiếp theo chỉ được tạo một lần về mặt nghiệp vụ.
- Không tạo thêm reservation, payment hoặc shipment.
- Event duplicate được ghi nhận/đếm nếu cần quan sát.

Với event tới sai thứ tự, ví dụ PaymentAuthorized đến trước InventoryReserved, hãy xác minh process manager xử lý theo một trong các chính sách:

- Từ chối/quarantine event sai trạng thái.
- Lưu event vào inbox chờ và áp dụng khi điều kiện trước đó hoàn tất.
- Tra cứu trạng thái nguồn để hòa giải.
- Dùng sequence/version để phát hiện gap và phục hồi.

Không nên để một event sai thứ tự làm saga nhảy qua bước nghiệp vụ bắt buộc.

### 7.1. Race condition

Hai event có thể tới gần như đồng thời, hoặc hai instance process manager cùng đọc một saga state. Test concurrency cần xác minh chỉ một transition được commit.

Các biện pháp thường dùng:

- Optimistic locking bằng version của saga state.
- Pessimistic row lock theo sagaId.
- Unique constraint cho event đã xử lý và command đã phát.
- Transactional outbox để lưu state transition cùng outgoing message.

Test chạy song song hai event có thể kiểm tra một trong hai kết quả hợp lệ, nhưng invariant cuối phải giữ và không được tạo side effect trùng.

## 8. Kiểm thử persistence và phục hồi sau restart

Process manager cần lưu trạng thái bền vững nếu saga có thể kéo dài qua nhiều request hoặc nhiều giờ/ngày. Test persistence không chỉ xác minh save/load object mà còn kiểm tra các failure window.

Một kịch bản restart:

1. Bắt đầu saga và xử lý InventoryReserved.
2. Lưu trạng thái WAITING_FOR_PAYMENT cùng command AuthorizePayment.
3. Dừng hoặc tạo lại application context.
4. Khởi động lại process manager.
5. Gửi PaymentAuthorized.
6. Xác minh saga tiếp tục từ trạng thái đã lưu và kết thúc đúng.

Các điều cần xác minh:

- State, current step, attempt count và deadline được lưu.
- Outgoing command/event được lưu cùng transaction với state transition.
- Restart không phát lại command đã hoàn tất ngoài chính sách.
- Lease/lock cũ được phục hồi hoặc hết hạn đúng cách.
- Saga không bị mất khi process manager instance thay đổi.

Nếu state commit nhưng outgoing command không được lưu, saga có thể bị kẹt. Nếu command gửi đi nhưng state chưa commit, command có thể bị phát lại. Transactional outbox hoặc cơ chế persistence tương đương giúp giải quyết khoảng trống này.

### 8.1. Kiểm thử outbox atomically

Trong test tích hợp, kiểm tra state transition và outbox record cùng transaction:

- Commit thành công: saga state và outgoing command cùng tồn tại.
- Rollback: cả state transition và outbox record cùng rollback.
- Relay gửi thành công: record được đánh dấu SENT sau publisher confirm.
- Relay dừng sau broker confirm nhưng trước mark SENT: message có thể gửi lại và consumer idempotent.

Nếu dùng Spring Modulith Event Publication Registry cho listener nội bộ, kiểm tra publication state riêng. Registry không thay thế outbox cho mọi integration message tới broker.

## 9. Kiểm thử theo từng lớp trong Spring Modulith

Một chiến lược kiểm thử hiệu quả thường có nhiều lớp với mục tiêu khác nhau.

| Lớp test | Phạm vi | Công cụ phù hợp | Điều chứng minh |
|---|---|---|---|
| Unit test | State machine, policy, compensation decision | JUnit, AssertJ, Mockito khi cần | Transition và invariant đúng |
| Module integration test | Listener, repository, application event trong một module | Spring Modulith test support, Spring Test | Module nhận event và cập nhật trạng thái đúng |
| Application integration test | Nhiều module phối hợp trong cùng ứng dụng | Spring Boot test/context phù hợp | Chuỗi event nội bộ tạo kết quả đúng |
| Persistence/recovery test | DB, outbox, publication registry, restart | Testcontainers DB, Spring Test | Transaction, checkpoint và phục hồi bền vững |
| Broker integration test | Exchange/queue, confirm, redelivery, DLQ | Testcontainers RabbitMQ hoặc broker tương ứng | Semantics vận chuyển thực tế |
| Contract test | Payload/version và adapter boundary | JSON fixtures, schema validation | Consumer tương thích với event contract |

Spring Modulith cung cấp công cụ kiểm thử module và xác minh cấu trúc module. Kiểm tra cấu trúc như ApplicationModules.verify() trả lời câu hỏi module có vi phạm dependency rule hay không; nó không thay thế test hành vi saga.

Có thể dùng @ApplicationModuleTest để kiểm thử một module với context phù hợp. Với quy trình xuyên nhiều module, cần application-level integration test để xác minh event thực sự được giao qua các listener liên quan.

Không cần dùng broker thật cho mọi unit test. Chỉ đưa broker vào integration test khi mục tiêu là xác minh routing, acknowledgement, redelivery hoặc topology.

## 10. Kiểm thử listener và transaction boundary

Listener của process manager thường nhận event rồi cập nhật saga state và phát command tiếp theo. Test cần xác minh state transition và outgoing action có cùng transaction.

Ví dụ minh họa:

~~~java
@ApplicationModuleListener
void on(InventoryReserved event) {
    sagaApplicationService.inventoryReserved(event);
}
~~~

Service xử lý có thể được transaction hóa:

~~~java
@Transactional
public void inventoryReserved(InventoryReserved event) {
    if (!processedEvents.tryRegister(event.eventId())) {
        return;
    }

    SagaDecision decision = processManager.onInventoryReserved(
            sagaRepository.get(event.sagaId()),
            event
    );

    sagaRepository.save(decision.state());
    outbox.appendAll(decision.outgoingMessages());
}
~~~

Integration test nên xác minh:

- Event hợp lệ được listener nhận.
- State mới được lưu.
- Outbox command tiếp theo được ghi.
- Duplicate không tạo thêm command.
- Nếu outbox insert thất bại, state transition cũng rollback.
- Nếu transaction rollback, publication/listener có thể được phục hồi theo cấu hình.

Không để listener bắt exception rồi return bình thường nếu state chưa được cập nhật. Điều đó có thể khiến publication bị đánh dấu hoàn tất trong khi saga đang dở dang.

## 11. Kiểm thử hợp đồng event giữa các module

Các module cần thống nhất event type, định danh, schema version và semantics. Test contract nên xác minh:

- Event có eventId, sagaId, aggregateId/correlationId cần thiết.
- Tên và ý nghĩa event không thay đổi ngoài ý muốn.
- Schema version được consumer hỗ trợ.
- Trường bắt buộc không bị null hoặc mất khi serialize.
- Adapter mapping không làm sai amount, currency, timestamp hoặc trạng thái.
- Event nội bộ không vô tình phơi bày entity hoặc dữ liệu nhạy cảm.

Dùng fixture JSON được version hóa để kiểm thử deserialize payload cũ. Nếu thay đổi contract không tương thích, cần version mới hoặc upcaster/adapter có kiểm soát.

Với choreography, contract test đặc biệt quan trọng vì một event có thể kích hoạt nhiều consumer độc lập. Với orchestration, test tập trung vào command được phát và event response mà coordinator chờ đợi.

## 12. Kiểm thử timeout, scheduler và công việc nền

Saga có thể có timer cho timeout, retry hoặc deadline nghiệp vụ. Không để test phụ thuộc thời gian thực.

Hãy tách scheduler thành abstraction có thể điều khiển trong test, hoặc truyền Clock vào logic xác định deadline. Test có thể:

- Tạo saga với deadline cố định.
- Kích hoạt callback timer giả lập.
- Xác minh trạng thái chuyển đúng.
- Xác minh timer bị hủy khi bước hoàn tất.
- Xác minh callback cũ không làm thay đổi saga đã kết thúc.
- Xác minh restart khôi phục timer từ deadline lưu bền vững.

Nếu dùng Spring scheduling, test logic lập lịch riêng và test integration cho việc đăng ký job ở mức tối thiểu. Tránh chờ vài phút trong test suite chỉ để chứng minh timeout.

## 13. Observability là một phần của khả năng kiểm thử

Saga khó điều tra nếu log chỉ ghi từng message rời rạc. Mọi bước nên gắn với sagaId, orderId, eventId, commandId, correlationId và step name.

Metric hữu ích:

- Số saga theo trạng thái.
- Số saga ở trạng thái chờ lâu hơn SLA.
- Số lần retry theo step.
- Số compensation thành công/thất bại.
- Số event duplicate hoặc đến sai thứ tự.
- Số saga phục hồi sau restart.
- Độ trễ từ bước bắt đầu tới bước kết thúc.
- Số outbox record hoặc publication chưa hoàn tất.

Test có thể xác minh metric/counter quan trọng được tăng khi một nhánh lỗi xảy ra. Không cần assert mọi dòng log; hãy tập trung vào tín hiệu vận hành có giá trị.

Một dashboard nên giúp trả lời: saga nào đang kẹt, đang chờ ai, bước nào thất bại, compensation nào còn pending và lần retry tiếp theo khi nào.

## 14. Bộ test matrix tối thiểu cho một saga

Trước khi phát hành saga mới, lập ma trận theo từng bước và từng failure window. Ví dụ:

| Nhóm | Kịch bản tối thiểu |
|---|---|
| Happy path | Tất cả bước thành công, saga COMPLETED |
| Business rejection | Inventory/Payment/Shipping từ chối và nhánh bù đúng |
| Technical failure | Dependency timeout, retry có giới hạn |
| Compensation | Bù thành công, bù thất bại, retry bù |
| Duplicate | Cùng event/command giao nhiều lần |
| Ordering | Event đến sai thứ tự hoặc thiếu sequence |
| Timeout | Deadline hết, event phản hồi đến muộn |
| Concurrency | Hai event cùng cập nhật một saga |
| Persistence | Restart giữa hai bước |
| Atomicity | State và outbox cùng commit/rollback |
| Contract | Payload cũ, version mới, dữ liệu thiếu |
| Operations | Saga bị kẹt, cảnh báo và quy trình can thiệp |

Ma trận này không thay thế phân tích rủi ro nghiệp vụ. Với thanh toán, tồn kho hoặc giao hàng, cần thêm các tình huống theo semantics thật của nhà cung cấp và các trạng thái trung gian như authorization pending, capture pending, refund pending.

## 15. Lỗi thường gặp khi kiểm thử saga

**Chỉ test happy path.** Phần khó của saga nằm ở failure và compensation. Tạo test cho từng điểm có thể thất bại sau một side effect đã commit.

**Mock toàn bộ module.** Test chỉ xác minh coordinator gọi mock đúng thứ tự, không chứng minh event contract, transaction hoặc persistence hoạt động. Bổ sung integration test có chọn lọc.

**Dùng sleep để chờ listener.** Test chậm và không ổn định. Dùng await condition có timeout hoặc latch.

**Không test duplicate.** Broker và publication registry có thể giao lại. Test phải chứng minh side effect idempotent.

**Không test event đến muộn.** Timeout không làm kết quả từ hệ thống ngoài biến mất. Xác định và test chính sách xử lý kết quả muộn.

**Đánh dấu saga hoàn tất khi mới phát command compensation.** Phải chờ kết quả bù thành công hoặc trạng thái nghiệp vụ terminal được định nghĩa rõ.

**Không test restart.** Saga bền vững phải tiếp tục được sau khi application context hoặc process manager instance khởi động lại.

**Chỉ kiểm tra state, không kiểm tra outgoing message.** Sai command có thể đưa saga vào trạng thái có vẻ đúng nhưng không tiến triển. Assert cả state và command/event phát ra.

**Không kiểm tra atomicity.** State commit nhưng command mất hoặc ngược lại có thể làm quy trình kẹt. Test state và outbox cùng transaction.

## 16. Quy trình xây dựng bộ test saga

Khi phát triển một saga trong Spring Modulith, có thể đi theo trình tự:

1. Viết state machine và bảng transition trước khi triển khai.
2. Xác định invariant và điều kiện kết thúc thành công/thất bại.
3. Viết unit test cho từng transition hợp lệ, không hợp lệ và duplicate.
4. Viết test cho từng nhánh compensation và thứ tự bù.
5. Dùng Clock/scheduler giả lập để kiểm thử timeout và retry.
6. Viết module integration test cho listener và transaction.
7. Viết application integration test cho happy path và business rejection.
8. Kiểm thử persistence, outbox, restart và recovery.
9. Kiểm thử broker/contract khi có giao tiếp ngoài tiến trình.
10. Đối chiếu metric và audit để đảm bảo saga có thể vận hành.

Một saga đáng tin cậy là saga có state transition xác định, mỗi side effect được bảo vệ bằng idempotency, trạng thái và outgoing action được lưu bền vững, và mọi nhánh lỗi đều có kết quả được theo dõi. Spring Modulith giúp tổ chức module và giao event nội bộ qua ranh giới rõ ràng; bộ test cần chứng minh process manager phối hợp các module đúng cả khi mọi thứ thành công lẫn khi transaction, listener, broker hoặc hệ thống bên ngoài gặp lỗi.
