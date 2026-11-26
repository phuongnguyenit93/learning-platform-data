# Command tiếp theo

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp bằng những sự kiện mô tả điều đã xảy ra. Khi một quy trình nghiệp vụ kéo dài qua nhiều module hoặc hệ thống, saga hoặc process manager cần quyết định bước kế tiếp dựa trên trạng thái hiện tại và kết quả vừa nhận được. Bước đó thường được biểu diễn bằng một **command** gửi tới module hoặc service chịu trách nhiệm thực hiện.

“Command tiếp theo” là quyết định điều phối của process manager: đọc trạng thái saga, kiểm tra event đầu vào có hợp lệ với trạng thái đó không, rồi tạo command phù hợp hoặc kết thúc quy trình. Quyết định này phải có thể phục hồi sau lỗi, chống xử lý trùng và giữ đúng ranh giới nghiệp vụ giữa các module.

## 1. Phân biệt event và command

Event và command đều có thể được truyền qua application event bus hoặc message broker, nhưng ý nghĩa của chúng khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event | Sự việc đã xảy ra; consumer có thể quan tâm | OrderPlaced, InventoryReserved |
| Command | Yêu cầu một handler thực hiện hành động | ReserveInventory, CapturePayment |
| Reply/result event | Kết quả của command được công bố | InventoryReserved, PaymentCaptured |
| Timeout signal | Cho biết một bước đã quá hạn | PaymentCaptureTimedOut |

Event thường dùng thì quá khứ vì nó mô tả một sự kiện đã xảy ra. Command thường diễn đạt hành động cần thực hiện và có một đích xử lý rõ ràng. Một command có thể bị từ chối, thất bại hoặc hoàn tất; kết quả được phản ánh bằng event hoặc reply tương ứng.

Process manager không nên phát command chỉ vì nhận được bất kỳ event nào. Nó phải xác định event có thuộc saga nào, trạng thái hiện tại có đang chờ kết quả tương ứng hay không và bước tiếp theo được phép thực hiện là gì. Event đến trễ hoặc lặp lại không được làm quy trình chạy lùi hoặc phát thêm tác dụng phụ.

## 2. Vai trò của saga và process manager

Saga là một quy trình nghiệp vụ gồm nhiều bước, mỗi bước có transaction cục bộ riêng. Khi một bước không thể tiếp tục, saga có thể phát các hành động bù trừ để đưa hệ thống về một trạng thái nghiệp vụ chấp nhận được. Saga không tạo ra một transaction ACID bao trùm nhiều service.

Process manager là thành phần điều phối quy trình. Nó lưu trạng thái tiến trình, nhận event từ các bước, quyết định command kế tiếp và theo dõi thời hạn hoặc lỗi. Trong cách triển khai orchestration, process manager chủ động quyết định bước tiếp theo. Trong choreography, các module phản ứng với event của nhau mà không có một bộ điều phối trung tâm.

Ví dụ quy trình đặt hàng:

~~~mermaid
flowchart TD
    A["OrderPlaced"] --> B["ReserveInventoryCommand"]
    B --> C{"Inventory result"}
    C -->|Reserved| D["CapturePaymentCommand"]
    C -->|Rejected| X["CancelOrderCommand"]
    X --> X2["OrderCancelled"]
    D --> E{"Payment result"}
    E -->|Captured| F["ArrangeShipmentCommand"]
    E -->|Declined| G["ReleaseInventoryCommand"]
    F --> H{"Shipment result"}
    H -->|Arranged| I["CompleteOrderCommand"]
    I --> I2["OrderCompleted"]
    H -->|Failed| J["RefundPaymentCommand"]
    J --> J2["PaymentRefunded"]
    J2 --> G
    G --> G2["InventoryReleased"]
~~~

Mỗi module sở hữu hành vi của mình. Inventory quyết định có thể giữ hàng hay không; Payment quyết định có thể thu tiền hay không; Shipping quyết định có thể tạo lô giao hàng hay không. Process manager phối hợp các kết quả này và chọn command tiếp theo mà không truy cập trực tiếp repository nội bộ của từng module.

## 3. Lưu trạng thái saga để quyết định bước tiếp theo

Process manager cần lưu ít nhất các thông tin sau:

- **sagaId:** định danh duy nhất của một lần chạy quy trình.
- **businessKey:** mã nghiệp vụ dùng để tìm saga, chẳng hạn orderId.
- **state:** trạng thái hiện tại của quy trình.
- **version:** phiên bản trạng thái để kiểm soát cập nhật đồng thời.
- **correlationId:** liên kết event và command thuộc cùng một quy trình.
- **pendingCommandId:** command đang chờ kết quả, nếu có.
- **deadline:** thời hạn của bước đang chờ.
- **createdAt / updatedAt:** thời điểm tạo và cập nhật.
- **completedAt:** thời điểm kết thúc nếu saga đã hoàn tất.
- **failureReason:** nguyên nhân lỗi hoặc lý do chuyển sang bù trừ.

Ví dụ các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| WAITING_FOR_INVENTORY | Đã yêu cầu giữ hàng, đang chờ kết quả |
| WAITING_FOR_PAYMENT | Hàng đã giữ, đang chờ kết quả thanh toán |
| WAITING_FOR_SHIPMENT | Thanh toán đã thành công, đang chờ tạo lô giao |
| WAITING_FOR_COMPLETION | Đã yêu cầu hoàn tất đơn hàng, đang chờ xác nhận |
| WAITING_FOR_CANCELLATION | Đã yêu cầu hủy đơn, đang chờ xác nhận |
| COMPENSATING | Đang thực hiện các bước bù trừ |
| COMPLETED | Quy trình hoàn tất |
| REJECTED | Quy trình bị từ chối sau khi bước hủy cần thiết đã hoàn tất |
| COMPENSATED | Các bước bù trừ đã hoàn tất |
| FAILED_MANUAL_REVIEW | Không thể tự động phục hồi, cần xử lý thủ công |

Tên trạng thái nên phản ánh điều process manager đang chờ hoặc đã xác nhận. Tránh dùng một cờ boolean chung như **done**, vì nó không thể diễn đạt rõ bước nào đã hoàn tất và bước nào còn đang chờ.

Trạng thái phải được lưu bền vững. Khi ứng dụng khởi động lại, process manager đọc lại saga đang chờ và tiếp tục từ trạng thái đã lưu. Không nên giữ toàn bộ tiến trình chỉ trong biến bộ nhớ hoặc một chuỗi callback không có dữ liệu phục hồi.

## 4. Bảng quyết định command tiếp theo

Bảng chuyển trạng thái là cách rõ ràng để review logic điều phối. Với ví dụ đặt hàng, có thể xác định:

| Trạng thái hiện tại | Event nhận được | Command hoặc hành động kế tiếp | Trạng thái mới |
|---|---|---|---|
| NEW | OrderPlaced | ReserveInventoryCommand | WAITING_FOR_INVENTORY |
| WAITING_FOR_INVENTORY | InventoryReserved | CapturePaymentCommand | WAITING_FOR_PAYMENT |
| WAITING_FOR_INVENTORY | InventoryRejected | CancelOrderCommand | WAITING_FOR_CANCELLATION |
| WAITING_FOR_CANCELLATION | OrderCancelled | Không phát command; kết thúc từ chối | REJECTED |
| WAITING_FOR_PAYMENT | PaymentCaptured | ArrangeShipmentCommand | WAITING_FOR_SHIPMENT |
| WAITING_FOR_PAYMENT | PaymentDeclined | ReleaseInventoryCommand | COMPENSATING |
| WAITING_FOR_SHIPMENT | ShipmentArranged | CompleteOrderCommand | WAITING_FOR_COMPLETION |
| WAITING_FOR_COMPLETION | OrderCompleted | Không phát command; kết thúc thành công | COMPLETED |
| WAITING_FOR_SHIPMENT | ShipmentFailed | RefundPaymentCommand | COMPENSATING |
| COMPENSATING | PaymentRefunded | ReleaseInventoryCommand | COMPENSATING |
| COMPENSATING | InventoryReleased | Không phát command; kết thúc bù trừ | COMPENSATED |
| Bất kỳ trạng thái chờ nào | StepTimedOut | Retry, query status hoặc command bù trừ theo chính sách | Tùy kết quả |

Bảng này là hợp đồng điều phối của quy trình. Mỗi hàng nên xác định rõ event nào được chấp nhận, điều kiện chuyển trạng thái, command được tạo và hành vi khi event không phù hợp. Với quy trình phức tạp, nên biểu diễn chuyển trạng thái bằng state machine thay vì nhiều nhánh if/else lồng nhau.

Không phải event nào cũng tạo command mới. Nếu event là bản sao của kết quả đã xử lý, process manager có thể bỏ qua sau khi xác nhận duplicate. Nếu event đến sai thứ tự, có thể ghi nhận để đối soát, chờ event còn thiếu hoặc chuyển sang nhánh xử lý lỗi. Không nên phát command tiếp theo chỉ dựa vào tên event mà không kiểm tra trạng thái saga.

## 5. Thiết kế command có định danh và đích nhận rõ ràng

Command nên là một DTO bất biến, mô tả hành động cần thực hiện và chứa dữ liệu tối thiểu để handler xử lý.

~~~java
public record ReserveInventoryCommand(
    UUID commandId,
    UUID sagaId,
    UUID correlationId,
    UUID causationId,
    UUID orderId,
    Instant issuedAt
) {}
~~~

Các trường định danh có vai trò riêng:

- **commandId** định danh duy nhất yêu cầu thực hiện hành động.
- **sagaId** liên kết command với tiến trình điều phối.
- **correlationId** liên kết toàn bộ chuỗi event và command.
- **causationId** tham chiếu event đã dẫn đến command này.
- **orderId** là business key của đơn hàng.
- **issuedAt** hỗ trợ theo dõi thời điểm phát command.

Command cần có recipient hoặc destination được xác định qua routing/configuration. Không gửi một command đến tất cả listener như event broadcast nếu hành động chỉ có một module chịu trách nhiệm. Nếu có nhiều handler cùng cần biết một sự việc, hãy công bố event kết quả sau khi command được xử lý.

Command ID phải ổn định qua các lần gửi lại cùng một yêu cầu. Nếu process manager tạo command mới mỗi lần retry, handler sẽ khó nhận diện cùng một ý định nghiệp vụ và có nguy cơ giữ hàng hoặc thu tiền nhiều lần. Hãy tạo command một lần khi chuyển trạng thái và lưu ID cùng bản ghi outbox hoặc pending command.

## 6. Xử lý event và phát command kế tiếp trong một transaction

Một nguyên tắc quan trọng là cập nhật trạng thái saga và ghi nhận command tiếp theo phải nguyên tử trong cùng transaction dữ liệu. Nếu process manager lưu trạng thái mới nhưng process dừng trước khi gửi command, saga có thể bị kẹt. Nếu gửi command trước rồi transaction rollback, handler có thể thực hiện một hành động mà process manager không ghi nhận.

Transactional outbox giải quyết khoảng trống này: trong cùng transaction, process manager cập nhật saga và ghi command vào outbox. Một dispatcher riêng đọc outbox và gửi command sau khi transaction commit. Sau khi broker xác nhận theo cơ chế được cấu hình, dispatcher đánh dấu bản ghi đã gửi. Nếu process dừng ở khoảng giữa gửi và đánh dấu, command có thể được gửi lại; handler vẫn phải idempotent.

~~~mermaid
sequenceDiagram
    participant E as Event listener
    participant P as Process manager
    participant DB as Database
    participant O as Outbox dispatcher
    participant B as Broker
    E->>P: InventoryReserved
    P->>DB: Đọc saga và kiểm tra state
    P->>DB: Cập nhật WAITING_FOR_PAYMENT
    P->>DB: Ghi CapturePaymentCommand vào outbox
    DB-->>P: Commit
    O->>DB: Đọc command chưa gửi
    O->>B: Publish command
    B-->>O: Publisher confirm
    O->>DB: Đánh dấu command đã gửi
~~~

Ví dụ service xử lý kết quả giữ hàng:

~~~java
@Service
class OrderSagaProcessManager {

    private final OrderSagaRepository sagas;
    private final ProcessedEventRepository processedEvents;
    private final CommandOutbox outbox;
    private final Clock clock;

    OrderSagaProcessManager(
            OrderSagaRepository sagas,
            ProcessedEventRepository processedEvents,
            CommandOutbox outbox,
            Clock clock) {
        this.sagas = sagas;
        this.processedEvents = processedEvents;
        this.outbox = outbox;
        this.clock = clock;
    }

    @Transactional
    public void onInventoryReserved(InventoryReserved event) {
        if (!processedEvents.claim(event.eventId())) {
            return;
        }

        OrderSaga saga = sagas.findById(event.sagaId())
            .orElseThrow(() -> new SagaNotFoundException(event.sagaId()));

        if (saga.state() != SagaState.WAITING_FOR_INVENTORY) {
            saga.recordUnexpectedEvent(event.eventId());
            sagas.save(saga);
            return;
        }

        UUID commandId = UUID.randomUUID();

        saga.waitForPayment(commandId, clock.instant());
        sagas.save(saga);

        outbox.append(new CapturePaymentCommand(
            commandId,
            saga.id(),
            saga.correlationId(),
            event.eventId(),
            saga.orderId(),
            clock.instant()
        ));
    }
}
~~~

Đây là mã minh họa; repository, inbox và outbox cần được triển khai sao cho cùng tham gia transaction. Phương thức claim phải dùng unique constraint hoặc cơ chế tương đương để hai consumer đồng thời không cùng nhận quyền xử lý một event. Nếu event đã được xử lý, method kết thúc mà không tạo command mới.

Nếu trạng thái saga không đúng như mong đợi, hãy áp dụng chính sách rõ ràng: ghi nhận event không mong đợi, kiểm tra duplicate, hoặc đưa quy trình vào trạng thái cần đối soát. Không nên âm thầm chuyển trạng thái hoặc phát command tiếp theo khi điều kiện chưa thỏa mãn.

## 7. Kết nối với Spring Modulith application events

Trong một ứng dụng Spring Modulith, process manager có thể nhận application event thông qua listener. Ví dụ:

~~~java
@Component
class OrderSagaEventHandler {

    private final OrderSagaProcessManager processManager;

    OrderSagaEventHandler(OrderSagaProcessManager processManager) {
        this.processManager = processManager;
    }

    @ApplicationModuleListener
    void on(InventoryReserved event) {
        processManager.onInventoryReserved(event);
    }
}
~~~

**@ApplicationModuleListener** phù hợp với xử lý module event sau khi transaction phát event commit và theo mô hình listener bất đồng bộ của Spring Modulith. Cần kiểm tra phiên bản và cấu hình transaction/async thực tế của ứng dụng. Event Publication Registry có thể theo dõi publication của transactional listener để hỗ trợ phát hiện và phục hồi publication chưa hoàn tất.

Ranh giới module nên thể hiện rõ module nào sở hữu process manager và module nào xử lý command. Process manager chỉ phụ thuộc vào hợp đồng event/command hoặc port được công bố. Không truy cập repository nội bộ của Inventory, Payment hay Shipping để tự sửa dữ liệu của module đó.

Nếu command được xử lý trong cùng ứng dụng, có thể dùng một port nội bộ để chuyển yêu cầu tới module đích sau commit. Nếu command đi qua broker hoặc tiến trình khác, outbox dispatcher gửi message tới destination đã cấu hình. Dù chọn cách nào, command vẫn cần một recipient rõ ràng, định danh ổn định và cơ chế xử lý kết quả.

Không nên phát command bằng cách gọi trực tiếp nhiều service trong cùng một transaction lớn rồi kỳ vọng đó là saga. Các bước của saga cần có transaction cục bộ và kết quả riêng để có thể retry, bù trừ hoặc phục hồi sau khi process dừng.

## 8. Xử lý event trùng lặp, đến trễ và sai thứ tự

Event có thể được giao lại do retry, broker redelivery, process restart hoặc acknowledgement bị mất. Vì vậy, process manager cần chống xử lý trùng bằng eventId. Bảng inbox hoặc bảng processed-event có unique constraint trên eventId là một cách phổ biến.

Ngoài duplicate, cần xử lý event đến sai thứ tự. Ví dụ PaymentCaptured đến khi saga vẫn ở WAITING_FOR_INVENTORY có thể do message delay, lỗi cấu hình hoặc event thuộc một saga khác. Process manager nên kiểm tra sagaId, correlationId, trạng thái mong đợi và business key trước khi chuyển trạng thái.

Các nguyên tắc:

- Chỉ chấp nhận event phù hợp với trạng thái hiện tại.
- Ghi nhận eventId đã xử lý trong cùng transaction với cập nhật saga.
- Dùng version/optimistic locking để ngăn hai event đồng thời ghi đè trạng thái.
- Với event đến sớm, có thể lưu vào inbox chờ xử lý hoặc yêu cầu đối soát theo chính sách.
- Với event cũ sau khi saga hoàn tất, ghi nhận duplicate hoặc late event và không mở lại saga tự động.
- Có cơ chế tra cứu trạng thái từ module sở hữu khi kết quả không rõ ràng.

Không nên giả định broker luôn giữ thứ tự nghiệp vụ trên mọi consumer. Partition key, queue và consumer concurrency có thể ảnh hưởng thứ tự nhận và hoàn tất. Nếu quy trình phụ thuộc thứ tự theo orderId, hãy đưa sequence/version vào event và xác thực trước khi áp dụng.

## 9. Timeout và command kế tiếp khi bước bị treo

Một command có thể không trả kết quả vì module đích gặp lỗi, message bị thất lạc hoặc dependency ngừng hoạt động. Process manager cần lưu deadline cho bước đang chờ và có cơ chế phát hiện quá hạn.

Không nên giữ thread bằng sleep để chờ timeout. Hãy lưu deadline vào trạng thái saga, sau đó dùng scheduler hoặc tác vụ định kỳ truy vấn các saga đã quá hạn. Khi phát hiện timeout, process manager cần xác định bước tiếp theo theo chính sách:

- Gửi lại command cũ nếu lỗi có thể phục hồi và command idempotent.
- Gửi query/status request để kiểm tra kết quả trước khi retry nếu không rõ handler đã thực hiện hay chưa.
- Chuyển sang command bù trừ nếu nghiệp vụ không thể tiếp tục.
- Chuyển sang FAILED_MANUAL_REVIEW nếu trạng thái bên ngoài không thể xác định an toàn.

Timeout signal nên mang sagaId, pendingCommandId và version/generation của deadline. Khi một kết quả thành công đến sau khi timeout đã được xử lý, process manager có thể nhận biết timeout thuộc bước cũ và quyết định xử lý late result theo chính sách.

Ví dụ, payment capture bị timeout nhưng cổng thanh toán có thể đã thu tiền. Không nên lập tức phát lệnh capture mới với commandId khác. Hãy query trạng thái giao dịch bằng idempotency key hoặc payment reference trước khi quyết định retry hay refund.

## 10. Retry command và idempotency ở handler

Retry là gửi lại cùng một ý định nghiệp vụ khi lỗi có khả năng phục hồi. Handler phải idempotent vì có thể nhận command nhiều lần. Với command giữ hàng, handler có thể lưu commandId hoặc sagaId cùng kết quả xử lý và trả lại kết quả cũ khi nhận lại cùng command.

Có thể dùng inbox table:

~~~sql
CREATE TABLE handled_command (
    command_id UUID PRIMARY KEY,
    handled_at TIMESTAMP NOT NULL,
    outcome VARCHAR(40) NOT NULL
);
~~~

Handler ghi nhận commandId và cập nhật dữ liệu nghiệp vụ trong cùng transaction. Nếu commandId đã tồn tại, handler không thực hiện tác dụng phụ lần nữa; nó có thể phát lại result event đã lưu để process manager tiếp tục.

Cần phân loại lỗi:

| Loại lỗi | Hành động |
|---|---|
| Timeout hoặc lỗi kết nối tạm thời | Retry cùng commandId với backoff |
| Rate limit | Chờ theo giới hạn của dependency |
| Dữ liệu command không hợp lệ | Từ chối, ghi nhận lỗi và không retry vô hạn |
| Quy tắc nghiệp vụ từ chối | Phát result event biểu thị bị từ chối |
| Kết quả không xác định | Query trạng thái trước khi tạo hành động mới |
| Vượt số lần thử | Bù trừ hoặc chuyển xử lý thủ công |

Không tạo commandId mới cho mỗi lần gửi lại cùng command. Nếu một hành động mới thực sự được quyết định sau khi saga chuyển trạng thái, đó là command mới và cần ID mới.

## 11. Compensation và command tiếp theo

Compensation là hành động nghiệp vụ đối ứng khi quy trình không thể tiếp tục. Nó không phải rollback transaction đã commit ở module khác. Ví dụ, nếu thanh toán đã thành công nhưng không thể tạo shipment, process manager có thể yêu cầu hoàn tiền và giải phóng hàng.

Một chuỗi bù trừ có thể được điều phối như sau:

~~~mermaid
flowchart TD
    A["ShipmentFailed"] --> B["RefundPaymentCommand"]
    B --> C{"Refund result"}
    C -->|Refunded| D["ReleaseInventoryCommand"]
    C -->|Refund failed| E["Retry refund / manual review"]
    D --> F{"Release result"}
    F -->|Released| G["Mark saga compensated"]
    F -->|Failed| H["Retry release / manual review"]
~~~

Compensation có thể thất bại và cũng cần retry, timeout, idempotency cùng observability. Process manager nên lưu trạng thái từng bước bù trừ để khi restart có thể tiếp tục từ command chưa hoàn tất.

Không phải lúc nào cũng có thể đảo ngược một hành động. Email đã gửi không thể thu hồi; một lô hàng đã bàn giao có thể cần quy trình trả hàng; khoản thanh toán có thể cần refund chứ không thể xóa lịch sử capture. Thiết kế compensation theo ngôn ngữ nghiệp vụ thay vì giả định mọi bước đều có phép inverse kỹ thuật.

## 12. Bảo đảm phục hồi và xử lý đồng thời

Process manager là một thành phần có trạng thái, nên cần xử lý restart, nhiều instance và event đến đồng thời.

Các biện pháp quan trọng:

- Lưu saga state, pending command và deadline trong kho bền vững.
- Dùng transaction cho inbox, state transition và outbox append.
- Dùng optimistic locking hoặc khóa phù hợp để ngăn hai instance cùng chuyển một saga.
- Đặt unique constraint cho eventId và commandId.
- Dispatcher outbox có thể chạy nhiều instance nhưng phải claim bản ghi an toàn.
- Lưu lịch sử chuyển trạng thái để điều tra và audit.
- Có cơ chế phục hồi outbox chưa gửi và saga đang chờ khi ứng dụng khởi động lại.

Nếu process manager xử lý cùng một saga từ hai event đồng thời, cả hai transaction có thể đọc cùng state và cùng quyết định command tiếp theo. Optimistic locking khiến một transaction thắng, transaction còn lại phải đọc lại trạng thái và áp dụng chính sách duplicate/late event. Không chỉ dựa vào kiểm tra state ở bộ nhớ.

Lịch sử saga nên lưu event đầu vào, state trước/sau, command được tạo, thời điểm, correlationId và kết quả. Tránh lưu payload nhạy cảm không cần thiết. Lịch sử này giúp phân tích vì sao process manager đã chọn một command cụ thể.

## 13. Quan sát quyết định điều phối

Khi quy trình bị kẹt, câu hỏi quan trọng không chỉ là command có được gửi hay không, mà còn là vì sao process manager chọn command đó. Nên ghi nhận:

- sagaId, businessKey và correlationId.
- Event đầu vào và eventId.
- State trước và sau chuyển trạng thái.
- Command type, commandId và destination.
- Lý do chọn command hoặc lý do không phát command.
- Deadline, attempt, retry và kết quả gần nhất.
- Trạng thái compensation và thời gian chờ.

Metrics hữu ích gồm số saga theo state, tuổi saga lâu nhất ở mỗi state, số pending command, outbox backlog, command retry, late event, duplicate event và compensation thất bại. Không dùng sagaId, orderId hoặc eventId làm metric tag vì cardinality cao; các định danh chi tiết thuộc log và trace.

Một dashboard có thể hiển thị số saga đang chờ Inventory, Payment hoặc Shipping, tuổi của bước chờ lâu nhất và số saga đang compensation. Cảnh báo nên gắn với deadline nghiệp vụ, chẳng hạn thanh toán chờ quá thời hạn hoặc compensation không tiến triển.

## 14. Kiểm thử command tiếp theo

Kiểm thử process manager cần xác nhận cả quyết định chuyển trạng thái và command được tạo ra. Không chỉ kiểm tra method listener đã được gọi.

Các kịch bản nên có:

1. **Happy path:** OrderPlaced dẫn tới ReserveInventory; InventoryReserved dẫn tới CapturePayment; PaymentCaptured dẫn tới ArrangeShipment; ShipmentArranged hoàn tất saga.
2. **Business rejection:** InventoryRejected dẫn tới từ chối đơn hàng hoặc command hủy theo chính sách.
3. **Payment declined:** phát ReleaseInventoryCommand và hoàn tất compensation.
4. **Shipment failure:** phát RefundPaymentCommand, sau đó ReleaseInventoryCommand khi refund thành công.
5. **Duplicate event:** cùng eventId không tạo thêm command hoặc tác dụng phụ.
6. **Out-of-order event:** event không phù hợp state được ghi nhận và không làm saga nhảy bước.
7. **Timeout:** bước quá hạn tạo đúng retry, query hoặc compensation command.
8. **Concurrent event:** hai event đồng thời không làm phát hai command mâu thuẫn.
9. **Restart recovery:** saga và outbox tiếp tục được xử lý sau khi process khởi động lại.
10. **Outbox publish ambiguity:** command có thể được gửi lại nhưng handler idempotent bảo vệ tác dụng phụ.
11. **Compensation failure:** saga giữ trạng thái rõ ràng và chuyển xử lý thủ công khi vượt giới hạn.
12. **Contract compatibility:** event và command cũ vẫn được deserialize hoặc xử lý theo chính sách versioning.

Với Spring Modulith, có thể kiểm thử module boundary để bảo đảm process manager chỉ dùng hợp đồng được công bố. Test tích hợp nên xác nhận listener, transaction, publication registry và outbox phối hợp đúng; test state machine riêng có thể bao phủ bảng chuyển trạng thái mà không cần broker thật.

## 15. Quy trình quyết định command kế tiếp

Khi xử lý một event trong saga, process manager có thể tuân theo trình tự:

1. Nhận event và xác thực event type, schema version, sagaId cùng correlation metadata.
2. Kiểm tra eventId đã được xử lý chưa.
3. Đọc saga state và version từ kho bền vững.
4. Kiểm tra event có hợp lệ với trạng thái hiện tại và pending command hay không.
5. Tính state transition và command tiếp theo theo bảng quyết định.
6. Trong cùng transaction, ghi dấu event đã xử lý, cập nhật saga state và thêm command vào outbox.
7. Sau commit, dispatcher gửi command tới recipient đã cấu hình.
8. Handler xử lý idempotent và phát result event.
9. Process manager tiếp tục cho tới khi saga COMPLETED, REJECTED hoặc được bù trừ.
10. Theo dõi timeout, retry, late event và các saga cần xử lý thủ công.

Command tiếp theo là kết quả của một quyết định nghiệp vụ dựa trên trạng thái saga, event đầu vào và chính sách phục hồi. Khi process manager lưu trạng thái bền vững, chuyển trạng thái và outbox được ghi nguyên tử, command có định danh ổn định và handler idempotent, quy trình nhiều bước có thể tiếp tục an toàn qua lỗi, retry và khởi động lại mà vẫn giữ ranh giới module rõ ràng.

