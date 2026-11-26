# Ẩn luồng nghiệp vụ

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp module công bố sự thật nghiệp vụ và cho phép các module khác phản ứng mà không cần gọi trực tiếp implementation của nhau. Cách giao tiếp này giảm coupling ở thời điểm compile, nhưng nếu một quy trình được chia thành quá nhiều listener và event nối tiếp mà không có mô hình điều phối rõ ràng, luồng nghiệp vụ có thể trở nên vô hình.

Đây là anti-pattern **ẩn luồng nghiệp vụ**: người đọc nhìn thấy các event và listener riêng lẻ nhưng không thể trả lời quy trình bắt đầu ở đâu, bước nào phải xảy ra tiếp theo, điều kiện hoàn tất là gì và ai chịu trách nhiệm khi một bước thất bại. Hệ thống vẫn có thể chạy đúng trong điều kiện bình thường, nhưng khó giải thích, kiểm thử, vận hành và thay đổi khi quy trình phát triển.

Mục tiêu không phải loại bỏ event choreography. Mục tiêu là giữ sự độc lập giữa module đồng thời làm cho workflow đủ rõ để người phát triển và người vận hành có thể hiểu và kiểm soát nó.

## 1. Luồng nghiệp vụ bị ẩn là gì?

Một workflow nghiệp vụ thường có nhiều bước phụ thuộc về mặt kết quả. Ví dụ, hoàn tất một đơn hàng có thể cần:

1. Xác nhận đơn hàng.
2. Cấp phép hoặc thu tiền.
3. Giữ hàng.
4. Tạo lô giao hàng.
5. Gửi thông báo.
6. Cập nhật read model.

Nếu các bước này được triển khai bằng các listener phát event nối tiếp, mỗi module chỉ biết event mình nhận và event mình phát. Không có nơi nào thể hiện toàn bộ chuỗi, điều kiện rẽ nhánh, timeout, compensation hoặc trạng thái cuối.

Một người mới đọc code có thể thấy `OrderConfirmed`, `PaymentAuthorized`, `InventoryReserved`, `ShipmentCreated` và hàng loạt listener, nhưng phải tìm kiếm qua nhiều package để dựng lại luồng. Một thay đổi nhỏ ở listener có thể vô tình kích hoạt một chuỗi tác dụng phụ mà caller ban đầu không biết.

Luồng bị ẩn thường xuất hiện khi:

- Event được dùng để nối nhiều bước phụ thuộc chặt chẽ mà không có workflow model.
- Tên event không thể hiện rõ kết quả nghiệp vụ hoặc thứ tự mong đợi.
- Listener vừa xử lý domain vừa phát nhiều event tiếp theo.
- Không có process ID/correlation ID để liên kết các bước.
- Không có nơi thể hiện trạng thái tổng thể và điều kiện hoàn tất.
- Tài liệu chỉ mô tả từng event mà không mô tả quy trình.
- Lỗi ở một bước không cho biết workflow đang dừng ở đâu.

## 2. Vì sao anti-pattern này nguy hiểm?

Khi workflow bị phân tán, coupling không biến mất; nó chuyển từ dependency compile-time sang dependency runtime khó nhìn thấy. Module A có thể không import module B, nhưng event do A phát lại là điều kiện bắt buộc để B chạy. B có thể phát event mà C cần, rồi C lại kích hoạt D. Chuỗi này tạo thành một đồ thị phụ thuộc hành vi.

Các hệ quả thường gặp:

- **Khó hiểu:** không có một điểm để xem toàn bộ quy trình.
- **Khó thay đổi:** thêm listener có thể tạo side effect mới ngoài dự kiến.
- **Khó kiểm thử:** test từng listener xanh nhưng toàn workflow vẫn sai.
- **Khó điều tra:** log rời rạc không cho biết một business operation đang ở bước nào.
- **Khó phục hồi:** không rõ bước nào đã hoàn tất và bước nào cần retry hoặc compensation.
- **Khó dự báo latency:** thời gian hoàn tất phụ thuộc vào nhiều listener và queue.
- **Khó kiểm soát ownership:** nhiều module cùng ngầm quyết định tiến trình của một workflow.

Một hệ thống có thể dùng event rất nhiều nhưng vẫn có kiến trúc dễ hiểu nếu workflow được mô tả và điều phối phù hợp. Vấn đề nằm ở sự thiếu minh bạch về luồng và trách nhiệm, không nằm ở số lượng event tự thân.

## 3. Choreography tốt và choreography bị lạm dụng

Trong choreography, mỗi module lắng nghe event mà nó quan tâm, thực hiện trách nhiệm của mình rồi phát event kết quả. Không có bộ điều phối trung tâm ra lệnh cho từng bước.

Choreography phù hợp khi:

- Các phản ứng tương đối độc lập.
- Không cần một trạng thái workflow tổng thể.
- Các nhánh có thể chạy song song.
- Thất bại của một consumer không làm thay đổi quyết định của các consumer khác.
- Quy trình ngắn và dễ hiểu qua các event contract.
- Mỗi module có thể tự phục hồi trong phạm vi trách nhiệm của nó.

Choreography trở thành vấn đề khi các event nối tiếp biểu đạt một state machine phức tạp nhưng state machine đó không được mô hình hóa. Ví dụ, PaymentAuthorized chỉ được phát khi OrderConfirmed; InventoryReserved chỉ được phát khi PaymentAuthorized; ShipmentCreated chỉ được phát khi InventoryReserved; nếu InventoryReservationFailed thì phải VoidPayment; nếu VoidPayment timeout thì chuyển sang manual review. Đây là workflow có trạng thái, nhánh và compensation, dù code chỉ gồm các listener rời rạc.

Không nên kết luận choreography là sai. Cần nhận diện khi workflow đã đủ phức tạp để cần một process manager hoặc một mô hình điều phối tường minh.

## 4. Event chain làm ẩn dependency như thế nào?

Một event chain là chuỗi các listener phát event khác để kích hoạt listener tiếp theo.

~~~mermaid
flowchart LR
    A[OrderPlaced] --> B[PaymentListener]
    B --> C[PaymentAuthorized]
    C --> D[InventoryListener]
    D --> E[InventoryReserved]
    E --> F[ShippingListener]
    F --> G[ShipmentCreated]
    G --> H[NotificationListener]
~~~

Nhìn riêng từng listener, mỗi module chỉ có một trách nhiệm nhỏ. Nhưng tổng thể tạo ra một workflow tuần tự. Nếu không có tài liệu hoặc process model, không dễ nhận biết:

- Có phải mọi bước đều bắt buộc?
- Bước nào có thể chạy song song?
- Event nào là kết quả cuối cùng?
- Nếu Inventory thất bại thì Payment có cần được bù không?
- Nếu ShipmentCreated đến muộn thì Order đang ở trạng thái nào?
- Ai quyết định workflow đã hoàn tất?

Khi một event có nhiều listener, nhánh xử lý còn phân tán hơn. Một listener có thể gửi email, một listener cập nhật projection, một listener phát command tiếp theo. Các tác dụng phụ có thể không có cùng mức quan trọng nhưng đều được kích hoạt bởi một event.

Hãy lập đồ thị event flow cho các quy trình quan trọng. Đồ thị cần thể hiện event, producer, listener, side effect, nhánh lỗi và điểm kết thúc; không chỉ liệt kê tên class.

## 5. Phân biệt event, command và workflow state

Một nguyên nhân khiến luồng bị ẩn là dùng event để biểu đạt cả sự thật đã xảy ra lẫn yêu cầu thực hiện bước tiếp theo.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event | Sự thật đã xảy ra | PaymentAuthorized |
| Command | Yêu cầu một module thực hiện hành động | ReserveInventory |
| Workflow state | Vị trí hiện tại của quy trình | INVENTORY_PENDING |
| Outcome | Kết quả của một bước | InventoryReserved hoặc InventoryReservationFailed |
| Compensation | Hành động bù cho bước đã hoàn tất | VoidPayment |

`PaymentAuthorized` không nên được phát chỉ để yêu cầu Inventory bắt đầu giữ hàng. Nó là sự thật thanh toán đã được cấp phép. Nếu cần yêu cầu Inventory thực hiện, đó là command hoặc một lời gọi API tới module sở hữu Inventory.

Trong ứng dụng modular monolith, command có thể được gọi qua API module công khai; event được dùng để thông báo kết quả cho các module quan tâm. Khi externalize command qua broker, cần xác định rõ semantics request/reply, retry và idempotency.

Phân biệt rõ các khái niệm làm cho luồng dễ đọc: ai yêu cầu, ai sở hữu hành động, event nào xác nhận kết quả và state nào đang chờ.

## 6. Dấu hiệu cần process manager

Một workflow có thể cần process manager khi có một hoặc nhiều đặc điểm:

- Nhiều bước phải hoàn tất theo thứ tự.
- Có nhánh thành công và thất bại khác nhau.
- Một bước phải chờ phản hồi từ module hoặc dịch vụ ngoài.
- Có timeout và retry theo từng bước.
- Có compensation khi bước sau thất bại.
- Cần biết workflow đang ở trạng thái nào sau restart.
- Có điều kiện hoàn tất phụ thuộc nhiều kết quả.
- Cần một nơi để vận hành, tra cứu và can thiệp workflow.

Process manager lưu trạng thái tiến trình và quyết định bước tiếp theo dựa trên event/outcome nhận được. Nó làm rõ luồng điều khiển mà không cần sở hữu dữ liệu domain của các module tham gia.

Ví dụ, Order Process Manager có thể giữ `sagaId`, `orderId`, trạng thái hiện tại và các bước đã hoàn tất. Nó phát command `AuthorizePayment`, chờ `PaymentAuthorized`, rồi mới yêu cầu `ReserveInventory`.

Process manager không nên truy cập repository nội bộ của Payments hoặc Inventory. Mỗi module vẫn sở hữu domain model và dữ liệu của mình.

## 7. Chọn choreography hay orchestration theo độ phức tạp

| Tiêu chí | Choreography | Orchestration/process manager |
|---|---|---|
| Luồng ngắn, ít nhánh | Phù hợp | Có thể quá mức cần thiết |
| Nhiều bước tuần tự | Khó nhìn toàn cục | Dễ thể hiện thứ tự |
| Timeout/compensation | Quy tắc phân tán | Có thể quản lý tập trung |
| Trạng thái workflow | Có thể không cần | Được lưu tường minh |
| Tính độc lập module | Cao ở mức điều phối | Module vẫn độc lập qua contract |
| Vận hành | Phải ghép log/event | Có thể tra cứu theo process ID |
| Rủi ro | Workflow vô hình | Process manager phình to thành domain god object |

Không cần chuyển mọi event flow sang orchestration. Một event như `CustomerProfileChanged` có thể được nhiều module độc lập lắng nghe để cập nhật cache, search index hoặc analytics. Những phản ứng này không nhất thiết thuộc cùng một workflow.

Ngược lại, một quy trình thanh toán–giữ hàng–giao hàng có điều kiện bù và timeout thường cần state machine rõ ràng. Hãy chọn mô hình theo quy tắc nghiệp vụ và nhu cầu vận hành.

## 8. Làm rõ ownership của workflow

Mỗi workflow quan trọng cần có owner chịu trách nhiệm về:

- Mục tiêu và điều kiện hoàn tất.
- Trạng thái tổng thể và các bước.
- Điều kiện chuyển trạng thái.
- Timeout, retry và compensation.
- Cách xử lý event đến muộn hoặc sai thứ tự.
- Quy trình manual review.
- Metrics, dashboard và runbook.

Owner workflow không nhất thiết sở hữu mọi dữ liệu tham gia. Ví dụ Order Process Manager có thể điều phối thanh toán, tồn kho và giao hàng nhưng Payments vẫn sở hữu payment record; Inventory vẫn sở hữu reservation; Shipping vẫn sở hữu shipment.

Tài liệu cần phân biệt workflow owner với domain owner. Nếu không, process manager dễ bị biến thành nơi chứa toàn bộ quy tắc của các module khác.

## 9. Mô hình hóa state machine thay vì dựa vào chuỗi listener ngầm

State machine mô tả trạng thái hợp lệ và event/outcome được chấp nhận ở mỗi trạng thái.

Ví dụ workflow đặt hàng:

| Trạng thái hiện tại | Event nhận được | Trạng thái tiếp theo | Hành động |
|---|---|---|---|
| STARTED | OrderPlaced | PAYMENT_PENDING | Gửi AuthorizePayment |
| PAYMENT_PENDING | PaymentAuthorized | INVENTORY_PENDING | Gửi ReserveInventory |
| PAYMENT_PENDING | PaymentFailed | FAILED | Kết thúc nhánh lỗi |
| INVENTORY_PENDING | InventoryReserved | SHIPPING_PENDING | Gửi CreateShipment |
| INVENTORY_PENDING | InventoryReservationFailed | COMPENSATING | Gửi VoidPayment |
| SHIPPING_PENDING | ShipmentCreated | COMPLETED | Ghi nhận hoàn tất |
| COMPENSATING | PaymentVoided | COMPENSATED | Kết thúc bù |
| COMPENSATING | CompensationFailed | MANUAL_REVIEW | Yêu cầu can thiệp |

Mỗi chuyển trạng thái nên có điều kiện rõ ràng và được lưu bền vững. Khi process manager nhận event, nó kiểm tra trạng thái hiện tại và xác định event có hợp lệ không.

Không để một listener tự phát event tiếp theo mà không kiểm tra workflow state nếu bước đó là một phần của quy trình có điều phối. Một event đến trùng hoặc sai thứ tự có thể làm chuỗi tiến lên không hợp lệ.

## 10. Không biến event thành lời gọi hàm gián tiếp

Một số hệ thống phát event nhưng thực tế dùng nó như một lời gọi hàm bất đồng bộ để che giấu dependency. Caller phát event rồi giả định một listener cụ thể sẽ thực hiện ngay hành động cần thiết.

Ví dụ, API xác nhận đơn phát `OrderConfirmed` và trả thành công, trong khi nghiệp vụ thực sự yêu cầu Inventory phải giữ hàng thành công trước khi đơn được xem là CONFIRMED. Nếu Inventory chỉ là listener bất đồng bộ, response có thể trả thành công trước khi điều kiện quan trọng được đáp ứng.

Hãy hỏi:

- Caller có cần kết quả của module nhận ngay để quyết định không?
- Nếu listener không chạy hoặc thất bại, command ban đầu có được xem là thành công không?
- Kết quả được trả qua API, event outcome hay process status?
- Người dùng có thể kiểm tra trạng thái tiến trình ở đâu?

Nếu kết quả là điều kiện bắt buộc để command thành công, cân nhắc API module đồng bộ hoặc workflow có trạng thái pending và outcome rõ. Event phù hợp khi producer thông báo sự thật đã xảy ra và consumer có thể phản ứng độc lập.

## 11. Giữ listener nhỏ và dễ hiểu

Listener nên làm rõ ba việc: nhận event nào, thực hiện trách nhiệm gì và có phát outcome nào không. Tránh listener vừa điều phối nhiều module, vừa thực hiện truy vấn chéo, vừa chứa logic bù, vừa gửi notification.

Ví dụ listener có trách nhiệm cục bộ:

~~~java
@Component
class InventoryReservationListener {

    private final InventoryService inventory;

    InventoryReservationListener(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        inventory.reserve(
            event.orderId(),
            event.items()
        );
    }
}
~~~

Listener này chuyển event thành hành động thuộc module Inventory. Quy tắc giữ hàng nằm trong InventoryService; listener không truy cập repository của Orders hoặc tự quyết định toàn bộ workflow.

Nếu listener phải phát nhiều event tiếp theo, kiểm tra xem nó đang xử lý một phản ứng độc lập hay đang điều phối một state machine. Với trường hợp thứ hai, chuyển phần điều phối sang process manager để trách nhiệm được nhìn thấy.

## 12. Đặt tên event thể hiện sự thật nghiệp vụ

Tên event mơ hồ khiến người đọc không biết điều gì đã xảy ra hoặc bước nào được phép tiếp tục.

Tên như `ProcessOrder`, `HandleCheckout`, `NextStep` hoặc `UpdateData` thường mô tả hành động chung, không phải sự thật cụ thể. Ưu tiên tên quá khứ hoặc trạng thái đã đạt như:

- `OrderPlaced`
- `PaymentAuthorized`
- `InventoryReserved`
- `ShipmentDispatched`
- `PaymentVoided`

Tên event nên trả lời “điều gì đã xảy ra?”. Command nên trả lời “cần làm gì?”. Event không nên phụ thuộc vào thứ tự listener hoặc tên class nội bộ của consumer.

Payload cần có định danh đủ để consumer hiểu ngữ cảnh: event ID, aggregate ID, correlation ID, causation ID, version và các dữ liệu domain tối thiểu. Không nhồi toàn bộ object graph để tránh coupling vào model nội bộ.

## 13. Tạo correlation và process ID xuyên suốt luồng

Khi workflow phân tán qua nhiều listener, log theo từng event riêng lẻ khó dựng lại câu chuyện. Mỗi workflow nên có định danh ổn định, ví dụ `processId` hoặc `sagaId`. Event mang correlation ID để liên kết các bước; causation ID cho biết message nào trực tiếp tạo ra event hiện tại.

Phân biệt:

| ID | Vai trò |
|---|---|
| eventId | Nhận diện một event cụ thể |
| processId/sagaId | Nhận diện một lần chạy workflow |
| correlationId | Liên kết các message trong cùng luồng |
| causationId | Liên kết nguyên nhân trực tiếp |
| aggregateId | Nhận diện đối tượng domain |

Không dùng một orderId làm processId nếu cùng một đơn có nhiều workflow độc lập như fulfillment, refund và return. Định danh workflow cần phân biệt các lần chạy hoặc loại quy trình khác nhau.

Dùng các ID này trong structured log và trace. Không đưa ID có cardinality cao vào metric labels; metrics nên phân nhóm theo event type, listener, state và outcome.

## 14. Tài liệu hóa event flow thay vì chỉ tài liệu hóa event

Mỗi event contract nên có schema, semantics và producer/consumer. Với workflow quan trọng, cần thêm tài liệu flow:

- Trigger bắt đầu quy trình.
- Các bước theo thứ tự hoặc các nhánh song song.
- Module sở hữu từng bước.
- Event/command giữa các bước.
- Trạng thái và điều kiện chuyển trạng thái.
- Timeout, retry và compensation.
- Điều kiện hoàn tất và trạng thái lỗi.
- Process ID/correlation ID.
- Metrics và runbook.

Sơ đồ sequence hoặc state diagram giúp người đọc hiểu nhanh hơn một danh sách listener. Tuy nhiên, sơ đồ phải được cập nhật cùng code. Nếu tài liệu thủ công dễ lỗi thời, hãy giữ nó ở gần module sở hữu workflow và đưa việc review vào pull request.

## 15. Quan sát workflow end-to-end

Để vận hành workflow, cần nhìn được tiến trình ở cấp business operation, không chỉ từng listener.

Nên theo dõi:

- Số workflow đang chạy theo state.
- Tuổi của workflow lâu nhất.
- Thời gian hoàn tất theo outcome.
- Số workflow timeout.
- Retry theo bước.
- Compensation thành công/thất bại.
- Số workflow ở MANUAL_REVIEW.
- Event trùng hoặc đến sai thứ tự.
- Publication backlog theo listener.
- Outbox/broker backlog ở từng chặng.

Một dashboard có thể cho phép tra cứu process ID và xem timeline: event nhận, command phát, state transition, retry, timeout và compensation. Khi không có process manager, vẫn nên có correlation ID và tracing đủ để nối các event liên quan.

Event Publication Registry của Spring Modulith theo dõi publication đến từng listener trong ứng dụng. Registry không tự biểu diễn toàn bộ workflow hoặc trạng thái business process. Hãy kết hợp registry với process state, logs, traces và metrics phù hợp.

## 16. Retry, timeout và compensation cần có nơi sở hữu

Nếu mỗi listener tự retry theo cách riêng mà không có quy tắc workflow, một bước có thể lặp vô hạn trong khi các bước khác đã tiến xa. Nếu timeout không được liên kết với process state, một timeout cũ có thể kích hoạt compensation sau khi workflow đã hoàn tất.

Với workflow có điều phối, process manager cần biết:

- Bước nào đang chờ.
- Deadline của bước.
- Số lần thử và thời điểm retry tiếp theo.
- Event outcome đã được xử lý hay chưa.
- Bước nào đã hoàn tất và có thể cần compensation.
- Workflow đã terminal hay chưa.

Mỗi consumer vẫn phải idempotent. Process manager không thay thế inbox/outbox, publication registry hoặc cơ chế đảm bảo giao message. Nó điều phối trạng thái nghiệp vụ; độ tin cậy transport vẫn cần được thiết kế riêng.

## 17. Transaction và side effect không được che giấu

Một event chain có thể tạo ra nhiều transaction độc lập. Không nên giả định toàn bộ workflow nằm trong một transaction database. Khi một bước đã commit, lỗi ở bước sau không thể rollback thay đổi trước đó bằng transaction thông thường.

Cần phân biệt:
- Transaction cục bộ của producer.
- Publication của application event.
- Transaction của từng listener.
- Ghi outbox và relay ra broker.
- Transaction của consumer bên ngoài.
- Compensation ở cấp nghiệp vụ.

Nếu process manager cập nhật state và phát command tiếp theo, hãy bảo đảm state transition và ý định phát command được lưu nguyên tử, thường bằng outbox. Consumer dùng inbox để chống xử lý trùng. Không để code điều phối tạo dual-write không kiểm soát.

## 18. Kiểm thử để phát hiện luồng bị ẩn

Unit test từng listener có thể xanh nhưng không chứng minh workflow end-to-end đúng. Cần test ở nhiều cấp:

**Architecture/module tests**
- Module chỉ phụ thuộc event contract hoặc API được công bố.
- Không có truy cập repository nội bộ của module khác.
- Dependency cycle được phát hiện.

**Event contract tests**
- Event biểu đạt đúng sự thật nghiệp vụ.
- Payload có định danh và version cần thiết.
- Producer không phát event trước khi domain transition hợp lệ.

**Workflow/scenario tests**
- Luồng thành công đi qua đúng các bước.
- Nhánh thất bại dẫn đến trạng thái và compensation đúng.
- Timeout, retry và event đến muộn không làm workflow sai.
- Event trùng không tạo tác dụng kép.
- Workflow có thể tiếp tục sau process restart nếu yêu cầu.

**Operational tests**
- Có thể tra cứu workflow theo process ID.
- Alert phát hiện workflow quá hạn.
- Manual review có runbook.
- Replay không lặp side effect ngoài ý muốn.

Test nên xác minh trạng thái cuối và các chuyển trạng thái quan trọng, không chỉ xác minh một event đã được publish.

## 19. Ví dụ: từ event chain ngầm sang workflow rõ ràng

Luồng choreography ban đầu:

~~~mermaid
flowchart TD
    A[OrderPlaced] --> B[PaymentListener]
    B --> C[PaymentAuthorized]
    C --> D[InventoryListener]
    D --> E[InventoryReserved]
    E --> F[ShippingListener]
    F --> G[ShipmentCreated]
    G --> H[OrderCompletedListener]
~~~

Nếu Inventory thất bại, logic bù có thể nằm trong một listener khác lắng nghe `InventoryReservationFailed`. Nếu VoidPayment thất bại, một listener khác lại phát `PaymentVoidRetryRequested`. Quy trình ngày càng khó hiểu vì mỗi nhánh được thêm vào như một phản ứng độc lập.

Luồng điều phối rõ hơn:

~~~mermaid
sequenceDiagram
    participant O as Orders
    participant M as Order Process Manager
    participant P as Payments
    participant I as Inventory
    participant S as Shipping

    O->>M: OrderPlaced
    M->>P: AuthorizePayment
    P-->>M: PaymentAuthorized
    M->>I: ReserveInventory
    I-->>M: InventoryReserved
    M->>S: CreateShipment
    S-->>M: ShipmentCreated
    M->>M: Mark COMPLETED
~~~

Nhánh thất bại có thể được thể hiện rõ:

~~~mermaid
sequenceDiagram
    participant M as Order Process Manager
    participant I as Inventory
    participant P as Payments

    M->>I: ReserveInventory
    I-->>M: InventoryReservationFailed
    M->>M: Mark COMPENSATING
    M->>P: VoidPayment
    P-->>M: PaymentVoided
    M->>M: Mark COMPENSATED
~~~

Process manager không sở hữu nghiệp vụ thanh toán hoặc tồn kho. Nó chỉ quyết định bước nào tiếp theo dựa trên outcome và lưu tiến trình để có thể quan sát, retry và phục hồi.

## 20. Lộ trình sửa anti-pattern

Không cần viết lại toàn bộ event architecture cùng lúc. Có thể giảm mức độ ẩn theo từng workflow:

1. Chọn một quy trình gây khó hiểu hoặc thường xuyên có sự cố.
2. Dựng event flow hiện tại từ producer, listener và downstream.
3. Xác định các bước bắt buộc, nhánh, timeout và compensation.
4. Ghi nhận module owner và side effect của từng bước.
5. Thêm correlation/process ID và log có cấu trúc.
6. Viết scenario test cho luồng thành công và thất bại.
7. Nếu workflow phức tạp, đưa state machine và process manager vào một module sở hữu rõ.
8. Chuyển từng bước sang command/outcome contract phù hợp.
9. Thêm persistence/outbox/inbox và idempotency theo yêu cầu tin cậy.
10. Cập nhật sơ đồ, runbook và metrics.
11. Loại bỏ listener/event chain cũ khi luồng mới đã được xác minh.

Giữ phạm vi thay đổi nhỏ giúp giảm rủi ro. Có thể bắt đầu bằng việc tài liệu hóa và thêm test trước khi thay đổi cấu trúc điều phối.

## 21. Những sai lầm khi khắc phục

**Chuyển mọi event sang orchestration.** Điều này tạo process manager không cần thiết cho các phản ứng độc lập.

**Tạo một process manager khổng lồ.** Một thành phần điều phối không nên sở hữu toàn bộ domain rule của Payments, Inventory và Shipping. Chia workflow theo ranh giới nghiệp vụ.

**Dùng event để gửi command nhưng đặt tên như sự thật.** Consumer không phân biệt được yêu cầu và kết quả.

**Dùng correlation ID thay cho state persistence.** Correlation giúp truy vết nhưng không cho biết bước nào đã commit hoặc cần tiếp tục sau restart.

**Chỉ thêm dashboard.** Quan sát tốt không thay thế mô hình workflow và ownership.

**Giữ logic điều phối trong listener.** Khi nhánh và compensation tăng, listener trở nên khó kiểm thử và dễ có side effect ngầm.

**Cho process manager truy cập repository module khác.** Điều này phá vỡ encapsulation và tạo coupling mới.

**Bỏ qua idempotency.** Orchestration không ngăn broker redelivery hoặc listener retry.

## 22. Checklist tránh ẩn luồng nghiệp vụ

- [ ] Mỗi workflow quan trọng có trigger và điều kiện hoàn tất rõ.
- [ ] Event biểu đạt sự thật đã xảy ra; command biểu đạt yêu cầu hành động.
- [ ] Producer, consumer và module owner được ghi rõ.
- [ ] Có sơ đồ event flow hoặc state machine cho workflow phức tạp.
- [ ] Các bước tuần tự, song song và nhánh lỗi được thể hiện.
- [ ] Timeout, retry và compensation có owner.
- [ ] Có process ID/correlation ID để liên kết các bước.
- [ ] Trạng thái workflow được lưu bền vững nếu cần phục hồi sau restart.
- [ ] Listener tập trung vào trách nhiệm của module sở hữu.
- [ ] Process manager không truy cập repository nội bộ của module khác.
- [ ] State transition và command tiếp theo được ghi nhận đáng tin cậy.
- [ ] Inbox/outbox và idempotency bảo vệ redelivery/side effect.
- [ ] Metrics và runbook cho phép tìm workflow bị kẹt.
- [ ] Scenario tests bao phủ thành công, thất bại, timeout và event đến muộn.
- [ ] Tài liệu được cập nhật cùng thay đổi event contract và workflow.

## 23. Nguyên tắc giữ workflow minh bạch

Application events giúp giảm phụ thuộc trực tiếp giữa module, nhưng chuỗi listener có thể che giấu một workflow nếu không có ownership, state và tài liệu rõ ràng. Choreography phù hợp với các phản ứng độc lập; workflow nhiều bước, nhiều nhánh, timeout hoặc compensation thường cần process manager để biểu diễn điều phối tường minh.

Trong Spring Modulith, hãy giữ event contract ở API được công bố của module, để mỗi module sở hữu dữ liệu và hành động của mình, và dùng process manager khi cần theo dõi tiến trình tổng thể. Kết hợp state machine, process/correlation ID, publication observability, idempotency, scenario tests và runbook sẽ giúp luồng nghiệp vụ dễ hiểu, dễ thay đổi và có thể phục hồi khi một bước thất bại.
