# Trạng thái saga

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Khi một quy trình đi qua nhiều module và nhiều transaction, hệ thống cần biết quy trình đang ở bước nào, bước nào đã hoàn tất, bước nào đang chờ và khi nào phải chuyển sang bù trừ. **Trạng thái saga** lưu lại tiến trình nghiệp vụ đó để quy trình có thể tiếp tục sau khi event đến trễ, listener lỗi hoặc ứng dụng khởi động lại.

Saga không chỉ là chuỗi event được phát nối tiếp. Đó là một quy trình nghiệp vụ có danh tính, các bước, điều kiện chuyển tiếp và kết quả cuối cùng. Trạng thái phải được lưu bền vững và thay đổi theo quy tắc rõ ràng; nếu chỉ dựa vào biến trong bộ nhớ của listener, ứng dụng sẽ mất khả năng tiếp tục điều phối khi tiến trình dừng.

## 1. Vì sao saga cần trạng thái?

Giả sử quy trình đặt hàng gồm ba module:

1. Order tạo đơn hàng và yêu cầu Inventory giữ hàng.
2. Inventory giữ hàng rồi phát xác nhận.
3. Order yêu cầu Payment thu tiền.
4. Payment xác nhận thanh toán và Order hoàn tất đơn hàng.

Mỗi module có transaction riêng. Giữa các bước, quy trình có thể chờ vài mili giây hoặc vài phút. Một listener có thể xử lý event nhưng process bị dừng trước khi bước tiếp theo được phát; một event có thể đến hai lần; hoặc bước thanh toán có thể timeout dù nhà cung cấp đã nhận yêu cầu. Không thể suy ra trạng thái tổng thể chỉ từ một event đang nằm trong bộ nhớ.

Trạng thái saga trả lời các câu hỏi:

- Quy trình nào đang được theo dõi và thuộc về đơn hàng nào?
- Những bước nào đã được yêu cầu, đang xử lý, hoàn tất hoặc thất bại?
- Event mới nhận có hợp lệ với bước hiện tại không?
- Có thể tiếp tục bước thuận, phải retry hay cần bù trừ?
- Quy trình đã hoàn tất, đã được bù hay cần người vận hành can thiệp?

Ví dụ, sau khi Inventory xác nhận giữ hàng, saga có thể ở trạng thái WAITING_FOR_PAYMENT. Nếu PaymentFailed đến, saga chuyển sang COMPENSATING và phát yêu cầu giải phóng reservation. Khi InventoryReleased được nhận và xác nhận, saga mới chuyển sang COMPENSATED.

## 2. Phân biệt trạng thái saga và trạng thái publication

Spring Modulith Event Publication Registry theo dõi việc giao một event đến transactional listener. Saga lưu trạng thái nghiệp vụ của toàn bộ quy trình. Hai loại trạng thái có liên quan nhưng không thay thế nhau.

| Trạng thái | Phạm vi | Ví dụ |
| --- | --- | --- |
| Publication incomplete/completed | Một lần giao event đến một listener cụ thể. | Listener xử lý OrderConfirmed đã được xác nhận hoàn tất hay chưa. |
| Saga state | Toàn bộ quy trình nghiệp vụ có nhiều bước và nhiều module. | Đơn hàng đang chờ thanh toán, đang bù trừ hay đã hoàn tất. |
| Step state | Một bước cụ thể trong saga. | Reservation đã được yêu cầu, đã giữ hàng hoặc đã giải phóng. |

Một publication completed chỉ cho biết listener đã xử lý thông điệp theo cơ chế của registry. Nó không chứng minh saga đã đạt mục tiêu cuối cùng. Ví dụ, listener có thể nhận PaymentFailed, cập nhật saga sang COMPENSATING và phát yêu cầu bù; publication của PaymentFailed đã completed trong khi saga vẫn đang chờ Inventory giải phóng hàng.

Ngược lại, một publication incomplete không cho biết toàn bộ saga đang ở trạng thái nào. Đó là dấu hiệu lần giao đến listener chưa được xác nhận hoàn tất và cần điều tra hoặc recovery. Vì vậy, cần quan sát cả publication registry lẫn bảng trạng thái saga.

## 3. Mô hình trạng thái tổng thể

Không có một bộ tên trạng thái bắt buộc dùng cho mọi saga. Hãy chọn trạng thái phản ánh rõ tiến trình nghiệp vụ và phân biệt trạng thái đang chạy với kết quả cuối cùng. Một mô hình tham khảo:

| Trạng thái | Ý nghĩa | Có thể chuyển tiếp đến |
| --- | --- | --- |
| STARTED | Saga đã được tạo và bắt đầu điều phối. | WAITING_FOR_INVENTORY, FAILED |
| WAITING_FOR_INVENTORY | Đã gửi yêu cầu giữ hàng và chờ kết quả. | WAITING_FOR_PAYMENT, COMPENSATING, REQUIRES_ATTENTION |
| WAITING_FOR_PAYMENT | Hàng đã được giữ; đang chờ kết quả thanh toán. | COMPLETED, COMPENSATING, REQUIRES_ATTENTION |
| COMPENSATING | Đã quyết định dừng tiến trình thuận và đang thực hiện các hành động bù bắt buộc. | COMPENSATED, REQUIRES_ATTENTION |
| COMPLETED | Tất cả bước thuận bắt buộc đã hoàn tất. | Trạng thái cuối |
| COMPENSATED | Các hành động bù bắt buộc đã hoàn tất theo quy tắc nghiệp vụ. | Trạng thái cuối |
| FAILED | Quy trình thất bại trước khi tạo cam kết cần bù hoặc đã kết thúc theo chính sách thất bại. | Trạng thái cuối hoặc xử lý thủ công theo domain |
| REQUIRES_ATTENTION | Không thể tự tiếp tục an toàn; cần điều tra hoặc can thiệp. | COMPENSATING, COMPLETED, COMPENSATED hoặc trạng thái xử lý thủ công |

FAILED và COMPENSATED không đồng nghĩa. FAILED mô tả kết quả thất bại của quy trình; COMPENSATED mô tả việc các cam kết đã phát sinh được xử lý bằng các hành động bù cần thiết. Một saga có thể trải qua lỗi thanh toán rồi kết thúc COMPENSATED sau khi giải phóng hàng thành công.

Không nên dùng một cờ boolean completed hoặc failed cho toàn bộ quy trình. Một cờ duy nhất không thể diễn tả việc đang chờ một module, đang retry, đang bù trừ hay cần can thiệp.

## 4. Theo dõi trạng thái từng bước

Trạng thái tổng thể cho biết saga đang ở đâu, nhưng khi quy trình có nhiều bước hoặc nhiều nhánh, cần lưu trạng thái riêng của từng bước. Ví dụ:

| Bước | Trạng thái có thể có | Dữ liệu cần theo dõi |
| --- | --- | --- |
| Reserve inventory | REQUESTED, SUCCEEDED, FAILED, COMPENSATED | reservationId, eventId, thời điểm và lỗi gần nhất |
| Charge payment | REQUESTED, SUCCEEDED, FAILED, UNKNOWN | paymentTransactionId, idempotencyKey, kết quả provider |
| Release inventory | NOT_REQUIRED, REQUESTED, SUCCEEDED, FAILED | reservationId, compensationId, số lần thử |
| Refund payment | NOT_REQUIRED, REQUESTED, SUCCEEDED, FAILED, UNKNOWN | paymentTransactionId, refundId, kết quả đối soát |

Trạng thái UNKNOWN hữu ích khi kết quả từ hệ thống ngoài chưa rõ. Ví dụ, request thu tiền bị timeout; timeout không chứng minh nhà cung cấp chưa thu tiền. Không được tự động gửi một yêu cầu thu tiền mới với khóa khác chỉ vì chưa nhận được response. Hãy truy vấn trạng thái giao dịch hoặc gửi lại với cùng idempotency key theo hợp đồng của nhà cung cấp.

Mỗi step nên có định danh ổn định, trạng thái, thời điểm bắt đầu/kết thúc và thông tin lỗi cần thiết. Với các bước có thể retry, lưu số lần thử hoặc lịch sử attempt ở mức cần thiết cho vận hành. Không cần sao chép toàn bộ payload event vào bảng saga nếu chỉ cần lưu identifier và dữ liệu điều phối.

## 5. State machine và điều kiện chuyển trạng thái

Mỗi event đầu vào phải được đánh giá theo trạng thái hiện tại và điều kiện nghiệp vụ. Không nên để listener nhận event nào cũng ghi đè trạng thái saga một cách vô điều kiện.

Ví dụ các chuyển tiếp:

~~~mermaid
stateDiagram-v2
    [*] --> STARTED
    STARTED --> WAITING_FOR_INVENTORY: yêu cầu giữ hàng
    WAITING_FOR_INVENTORY --> WAITING_FOR_PAYMENT: InventoryReserved
    WAITING_FOR_INVENTORY --> COMPENSATING: không thể tiếp tục
    WAITING_FOR_PAYMENT --> COMPLETED: PaymentCaptured
    WAITING_FOR_PAYMENT --> COMPENSATING: PaymentFailed
    COMPENSATING --> COMPENSATED: mọi bước bù hoàn tất
    COMPENSATING --> REQUIRES_ATTENTION: bù trừ không thể tự phục hồi
    REQUIRES_ATTENTION --> COMPENSATING: tiếp tục bù có kiểm soát
    REQUIRES_ATTENTION --> COMPENSATED: xác nhận đã xử lý thủ công
    COMPLETED --> [*]
    COMPENSATED --> [*]
~~~

Một chuyển tiếp hợp lệ thường cần kiểm tra:

- sagaId của event có trỏ đến saga tồn tại không?
- Event type có phù hợp với bước đang chờ không?
- Event có đúng orderId, reservationId hoặc paymentTransactionId không?
- Event đã được áp dụng trước đó chưa?
- Phiên bản aggregate hoặc step có mới hơn phiên bản đã lưu không?
- Saga có đang ở trạng thái cuối hoặc đang bù trừ khiến event thuận đến muộn không?

Nếu điều kiện không thỏa, xử lý theo một chính sách có chủ đích: bỏ qua event trùng đã xử lý, ghi nhận event đến sớm để xử lý sau, đưa vào hàng chờ điều tra hoặc đánh dấu REQUIRES_ATTENTION. Không âm thầm biến một event không hợp lệ thành trạng thái thành công.

## 6. Danh tính và dữ liệu của saga

Mỗi saga cần một sagaId duy nhất và ổn định trong suốt vòng đời. Event phát sinh từ quy trình nên mang sagaId để process manager tìm đúng instance. Ngoài ra, event thường cần eventId, business key, stepId hoặc aggregateVersion để chống trùng và xác định thứ tự.

Ví dụ event:

~~~java
public record InventoryReserved(
    UUID eventId,
    UUID sagaId,
    UUID orderId,
    UUID reservationId,
    long orderVersion,
    Instant occurredAt
) {}

public record PaymentCaptured(
    UUID eventId,
    UUID sagaId,
    UUID orderId,
    UUID paymentTransactionId,
    Instant occurredAt
) {}
~~~

Một bản ghi saga có thể lưu:

| Field | Mục đích |
| --- | --- |
| sagaId | Khóa định danh của quy trình. |
| businessKey | Liên kết với orderId hoặc đối tượng nghiệp vụ chính. |
| state | Trạng thái tổng thể hiện tại. |
| stateVersion | Phiên bản để kiểm soát cập nhật đồng thời. |
| currentStep | Bước đang chờ hoặc đang điều phối. |
| startedAt, updatedAt | Theo dõi thời gian sống và độ trễ. |
| deadlineAt | Thời hạn nghiệp vụ để phát hiện quy trình bị treo. |
| lastErrorCode | Mã lỗi gần nhất phục vụ điều tra. |

Không đưa thông tin xác thực, token hoặc dữ liệu thanh toán nhạy cảm vào saga state. Chỉ lưu các định danh giao dịch cần thiết và tham chiếu đến nơi lưu dữ liệu được bảo vệ.

## 7. Process manager điều phối state machine

Process manager là thành phần giữ trạng thái quy trình và quyết định event tiếp theo cần phát. Khác với một listener chỉ xử lý một event đơn lẻ, process manager biết saga đang ở bước nào và dùng kết quả nhận được để chọn bước kế tiếp.

Ví dụ, khi InventoryReserved đến, process manager kiểm tra saga đang WAITING_FOR_INVENTORY, lưu reservationId và chuyển sang WAITING_FOR_PAYMENT. Sau đó nó phát ChargePaymentRequested. Khi PaymentCaptured đến, process manager xác nhận đúng saga và đúng payment transaction rồi chuyển sang COMPLETED.

Một listener trong Spring Modulith có thể chuyển event vào process manager:

~~~java
@Component
@RequiredArgsConstructor
class OrderSagaEventListener {

    private final OrderSagaProcessManager processManager;

    @ApplicationModuleListener
    void on(InventoryReserved event) {
        processManager.handle(event);
    }

    @ApplicationModuleListener
    void on(PaymentCaptured event) {
        processManager.handle(event);
    }
}
~~~

Process manager cập nhật trạng thái trong transaction:

~~~java
@Service
@RequiredArgsConstructor
class OrderSagaProcessManager {

    private final OrderSagaRepository sagas;
    private final ApplicationEventPublisher events;

    @Transactional
    public void handle(InventoryReserved event) {
        OrderSaga saga = sagas.findById(event.sagaId())
            .orElseThrow(() -> new SagaNotFoundException(event.sagaId()));

        if (saga.isAlreadyApplied(event.eventId())) {
            return;
        }

        if (!saga.isWaitingForInventory()
                || !saga.matchesOrder(event.orderId())) {
            saga.recordUnexpectedEvent(event.eventId());
            return;
        }

        saga.recordInventoryReservation(
            event.reservationId(),
            event.orderVersion()
        );
        saga.moveToWaitingForPayment();

        events.publishEvent(new ChargePaymentRequested(
            UUID.randomUUID(),
            saga.getSagaId(),
            saga.getOrderId()
        ));
    }
}
~~~

Các phương thức của OrderSaga và repository trong ví dụ là API minh họa, cần triển khai theo mô hình persistence của ứng dụng. Điểm cốt lõi là kiểm tra trạng thái, ghi nhận event đã áp dụng, chuyển state và phát yêu cầu bước tiếp theo trong ranh giới transaction phù hợp.

Process manager không nên cập nhật trực tiếp bảng của Inventory hoặc Payment. Nó phát command/event yêu cầu module sở hữu dữ liệu thực hiện công việc và chờ event kết quả. Nhờ đó, state machine điều phối quy trình mà vẫn giữ quyền sở hữu nghiệp vụ tại từng module.

## 8. Lưu trạng thái bền vững và xử lý đồng thời

Saga có thể tồn tại lâu hơn vòng đời của một request hoặc một instance ứng dụng. Trạng thái phải được lưu trong database hoặc một store bền vững khác. Khi ứng dụng restart, process manager đọc lại saga đang chờ và tiếp tục xử lý event đến sau đó.

Nhiều event có thể cùng lúc tác động đến một saga. Ví dụ timeout và PaymentCaptured đến gần như đồng thời. Nếu cả hai handler cùng đọc WAITING_FOR_PAYMENT rồi ghi state, một cập nhật có thể ghi đè cập nhật kia. Cần bảo vệ state transition bằng optimistic locking, transaction isolation hoặc cơ chế khóa phù hợp.

Ví dụ với JPA:

~~~java
@Entity
class OrderSaga {

    @Id
    private UUID sagaId;

    @Version
    private long stateVersion;

    @Enumerated(EnumType.STRING)
    private SagaState state;
}
~~~

@Version giúp phát hiện cập nhật cạnh tranh. Khi optimistic lock conflict xảy ra, handler có thể retry việc đọc và đánh giá lại event theo state mới. Không retry mù quáng cùng một thao tác nếu trạng thái đã thay đổi; phải chạy lại điều kiện chuyển tiếp.

Nếu dùng nhiều database hoặc nhiều process manager instance, bảo đảm mỗi cập nhật state và quyết định phát event được phối hợp bền vững. Transactional event publication của Spring Modulith có thể theo dõi việc giao event đến transactional listener nội bộ; cần cấu hình persistent publication repository và transaction manager tương thích với yêu cầu. Việc ghi state saga và publication phải nằm trong ranh giới transaction phù hợp để không tạo trạng thái đã chuyển bước nhưng mất event kế tiếp.

## 9. Duplicate, event đến sớm và event đến muộn

Trong hệ thống event-driven, event có thể được giao lại, đến sai thứ tự hoặc đến sau khi saga đã kết thúc. Process manager cần xử lý từng trường hợp rõ ràng.

| Tình huống | Cách xử lý gợi ý |
| --- | --- |
| Duplicate event đã áp dụng | Nhận diện bằng eventId hoặc step key; kết thúc idempotent. |
| Event đến sớm hơn bước đang chờ | Lưu pending event có kiểm soát hoặc retry sau khi prerequisite hoàn tất. |
| Event đến muộn sau khi saga đã COMPLETED | Không làm lùi state; ghi nhận hoặc bỏ qua theo quy tắc. |
| Event thuận đến khi saga COMPENSATING | Không tiếp tục bước thuận; xác minh xem event có tạo cam kết cần bù bổ sung không. |
| Event kết quả không khớp business key | Đưa vào điều tra; không áp dụng vào saga khác. |
| Hai kết quả xung đột | Dùng state version và quy tắc nghiệp vụ để phân xử. |

Đối với event đến sớm, không phải lúc nào cũng nên lưu toàn bộ payload để xử lý sau. Nếu event có thể được phát lại từ nguồn bền vững, có thể yêu cầu retry hoặc dùng inbox pending. Nếu lưu pending, cần có giới hạn tuổi, trạng thái và cơ chế đánh thức khi prerequisite hoàn tất.

Khi saga đã ở trạng thái cuối, event đến muộn không được tự động đưa saga trở lại IN_PROGRESS. Nếu nghiệp vụ cho phép mở một quy trình mới, hãy tạo saga mới với sagaId mới và liên kết với quy trình cũ qua business key hoặc causationId.

## 10. Timeout và deadline của saga

Một saga có thể bị treo khi module nhận không phản hồi hoặc event kết quả không bao giờ đến. Mỗi bước chờ nên có deadline phù hợp với SLA nghiệp vụ. Khi quá hạn, process manager có thể phát timeout event hoặc chạy một tác vụ quét các saga quá hạn.

Timeout không chứng minh bước bên ngoài thất bại. Ví dụ yêu cầu thanh toán đã được nhà cung cấp nhận nhưng response bị mất. Trước khi chuyển sang bù trừ hoặc gửi lại lệnh thu tiền, cần truy vấn trạng thái giao dịch hoặc dùng idempotency key ổn định.

Một quy trình timeout có thể:

1. Tìm saga đang chờ và deadline đã qua.
2. Đọc lại state version để tránh xử lý saga vừa được cập nhật.
3. Xác minh bước có thể đã hoàn tất ở module hoặc hệ thống ngoài.
4. Chuyển state sang nhánh retry, tiếp tục hoặc COMPENSATING theo quy tắc.
5. Ghi nhận timeout reason và phát event/command tiếp theo trong transaction.

Không dùng một timeout chung cho mọi bước. Giữ hàng trong kho có thể cần phản hồi nhanh hơn hoàn tiền từ cổng thanh toán. Deadline phải phản ánh đặc tính của dependency và mức chấp nhận của nghiệp vụ.

## 11. Bù trừ và trạng thái saga

Khi một bước thuận thất bại sau khi các bước trước đã tạo cam kết, process manager chuyển saga sang COMPENSATING. Trạng thái này biểu thị quy trình đang thực hiện các hành động bù; nó chưa phải kết quả cuối.

Ví dụ, nếu hàng đã được giữ nhưng thanh toán thất bại, saga có thể lưu:

| Bước | Trạng thái |
| --- | --- |
| Reserve inventory | SUCCEEDED |
| Charge payment | FAILED |
| Release inventory | REQUESTED |
| Saga tổng thể | COMPENSATING |

Khi nhận InventoryReleased, process manager đánh dấu bước bù thành công. Chỉ khi mọi hành động bù bắt buộc đã hoàn tất, saga mới chuyển COMPENSATED. Nếu giải phóng hàng thất bại không thể retry an toàn, chuyển REQUIRES_ATTENTION và giữ thông tin để người vận hành xử lý.

Không xóa lịch sử bước thuận khi bù trừ. Một giao dịch hoàn tiền hoặc giải phóng reservation là một nghiệp vụ mới có thể cần audit. Giữ dấu vết cả bước thuận lẫn bước bù giúp điều tra và đối soát.

## 12. Phục hồi sau restart và retry

Khi ứng dụng khởi động lại, process manager cần tìm các saga chưa ở trạng thái cuối, các bước đang chờ và các bước đã quá deadline. Từ trạng thái đã lưu, nó có thể tiếp tục chờ event, phát lại command an toàn hoặc chuyển sang điều tra.

Event Publication Registry hỗ trợ tìm và recovery publication chưa hoàn tất đến transactional listener theo cấu hình và API của phiên bản Spring Modulith. Registry không tự lưu state machine của saga, không thay thế bảng saga và không quyết định bước nghiệp vụ kế tiếp. Process manager vẫn phải quản lý state riêng.

Retry nên phân biệt:

- Lỗi hạ tầng tạm thời: có thể retry với backoff và giới hạn số lần.
- Lỗi nghiệp vụ có thể thay đổi theo thời gian: chờ điều kiện hoặc event mới.
- Lỗi dữ liệu/hợp đồng: cần điều tra hoặc sửa dữ liệu trước khi tiếp tục.
- Kết quả không xác định: đối soát trạng thái trước khi gửi lại thao tác có side effect.

Khi retry một command, giữ idempotency key ổn định cho cùng một hành động nghiệp vụ. Nếu mỗi lần retry tạo một command ID mới và hệ thống đích không có khóa chống trùng, một khoản thu tiền hoặc reservation có thể bị tạo nhiều lần.

## 13. Kiểm thử state machine và process manager

Kiểm thử trạng thái cần xác minh cả chuyển tiếp hợp lệ và event không hợp lệ. Unit test có thể kiểm tra state machine thuần; integration test cần xác minh transaction, event dispatch và persistence.

Các trường hợp nên bao phủ:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Bắt đầu saga | State và các bước ban đầu được lưu đúng. |
| Event thành công theo thứ tự | Saga chuyển qua các state dự kiến và phát command kế tiếp. |
| Event trùng | State và side effect không bị áp dụng lần hai. |
| Event đến sai thứ tự | Event được giữ, retry hoặc xử lý theo chính sách; không làm hỏng state. |
| Event không khớp saga | Không cập nhật nhầm quy trình. |
| Timeout và success đồng thời | Chỉ một chuyển tiếp hợp lệ được commit; conflict được xử lý. |
| Restart | Saga chưa hoàn tất vẫn được phục hồi từ persistence. |
| Bù trừ thành công | Chỉ chuyển COMPENSATED khi mọi bước bù bắt buộc đã hoàn tất. |
| Bù trừ thất bại | Saga chuyển REQUIRES_ATTENTION và giữ dữ liệu điều tra. |
| Event đến sau terminal state | Không làm saga quay về trạng thái đang chạy. |

Nên kiểm thử crash window: state và command được ghi nhận, nhưng process dừng trước khi listener được xác nhận hoàn tất. Sau recovery, command không bị mất và side effect không bị lặp. Cũng cần kiểm thử hai event cạnh tranh trên cùng saga để xác minh optimistic locking hoặc cơ chế đồng bộ thực sự bảo vệ state transition.

## 14. Quan sát và vận hành saga

Dashboard nên cho thấy số saga theo trạng thái, số saga quá deadline, thời gian ở từng bước, số lần retry và số saga cần can thiệp. Chỉ nhìn số event hoặc publication incomplete là chưa đủ để biết quy trình nghiệp vụ đang bị kẹt ở đâu.

Các chỉ số hữu ích:

- Số saga STARTED, WAITING_*, COMPENSATING, COMPLETED, COMPENSATED và REQUIRES_ATTENTION.
- Tuổi của saga đang chờ lâu nhất và tuổi của từng bước.
- Tỷ lệ hoàn tất thuận, tỷ lệ bù trừ và tỷ lệ cần can thiệp.
- Số event duplicate, event đến muộn và xung đột state version.
- Số publication incomplete theo process manager listener.
- Thời gian từ lúc bắt đầu đến khi hoàn tất hoặc bù trừ.

Log và trace nên có sagaId, businessKey, eventId, stepId, state trước/sau và correlationId. Khi điều tra, người vận hành có thể dựng lại chuỗi quyết định mà không cần ghi toàn bộ payload nhạy cảm.

Một màn hình vận hành nên cho phép xem lịch sử chuyển trạng thái, event liên quan, lỗi gần nhất và bước tiếp theo được mong đợi. Nếu có thao tác thủ công như retry, đánh dấu đã đối soát hoặc tiếp tục bù, cần ghi lại người thực hiện, lý do, thời điểm và kết quả. Không cho phép sửa state tùy ý mà không kiểm tra invariant nghiệp vụ.

## 15. Checklist thiết kế trạng thái saga

- Mỗi saga có sagaId ổn định và business key để liên kết đối tượng nghiệp vụ.
- State tổng thể phân biệt đang chạy, hoàn tất, thất bại, bù trừ và cần can thiệp.
- Mỗi bước có trạng thái, identifier, deadline và thông tin lỗi phù hợp.
- Mỗi event đầu vào được kiểm tra theo state hiện tại, sagaId và business key.
- State transition có điều kiện và được lưu trong transaction.
- Duplicate và event đến muộn không làm lặp side effect hoặc làm lùi state.
- Event đến sớm có chính sách pending/retry rõ ràng.
- Cập nhật đồng thời được bảo vệ bằng optimistic locking hoặc cơ chế phù hợp.
- Timeout không bị xem là bằng chứng chắc chắn rằng hệ thống ngoài chưa thực hiện thao tác.
- Bù trừ được theo dõi như các bước nghiệp vụ riêng; COMPENSATED chỉ khi mọi hành động bắt buộc đã hoàn tất.
- Saga state được lưu bền vững; Event Publication Registry chỉ đảm nhiệm theo dõi publication đến listener.
- Integration test bao phủ transition, duplicate, ordering, timeout, restart, concurrency và compensation.
- Dashboard và audit log có thể lần theo saga từ lúc bắt đầu đến kết quả cuối.

Trạng thái saga là nền tảng để process manager điều phối một quy trình nhiều module qua các transaction độc lập. Khi state machine được mô hình hóa rõ, lưu bền vững và chuyển trạng thái có điều kiện, ứng dụng có thể tiếp tục sau restart, xử lý event trùng hoặc đến muộn, quản lý timeout và bù trừ mà vẫn giữ được ranh giới nghiệp vụ của từng module.
