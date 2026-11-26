# Chuỗi event nghiệp vụ

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, các application event giúp module công bố sự thật nghiệp vụ để module khác phản ứng mà không cần gọi trực tiếp lẫn nhau. Một quy trình nghiệp vụ thường không kết thúc sau một event. Xác nhận đơn hàng có thể dẫn đến giữ hàng, thu tiền, lập hóa đơn và giao hàng; mỗi bước lại tạo ra event mới. Chuỗi các event đó cần được thiết kế sao cho hệ thống có thể tiếp tục sau lỗi, nhận biết công việc đã hoàn tất và xử lý các bước bù khi quy trình không thể đi tiếp.

Saga và process manager cung cấp cách tổ chức quy trình kéo dài qua nhiều transaction. Chuỗi event là phương tiện truyền đạt các kết quả giữa các bước. Để quy trình đáng tin cậy, cần xác định rõ trạng thái hiện tại, event nào được chấp nhận, bước tiếp theo là gì, khi nào hết thời gian chờ và cách phục hồi khi message bị gửi lặp hoặc đến sai thứ tự.

## 1. Chuỗi event nghiệp vụ là gì?

Chuỗi event nghiệp vụ là tập hợp các sự kiện biểu đạt những kết quả xảy ra trong một quy trình, thường qua nhiều module hoặc dịch vụ. Mỗi event mô tả một sự thật đã xảy ra, chẳng hạn:

- OrderPlaced: đơn hàng đã được tạo.
- PaymentAuthorized: khoản thanh toán đã được cấp phép.
- InventoryReserved: hàng hóa đã được giữ.
- ShipmentDispatched: lô hàng đã được gửi đi.
- OrderCompleted: quy trình đơn hàng đã hoàn tất.

Một event có thể kích hoạt listener để cập nhật trạng thái, phát event tiếp theo hoặc yêu cầu một hành động ở module khác. Các bước không nhất thiết chạy trong cùng một request hoặc transaction. Một bước có thể hoàn tất sau vài mili giây, vài phút hoặc lâu hơn.

Cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event | Sự thật đã xảy ra | PaymentAuthorized |
| Command | Yêu cầu một thành phần thực hiện hành động | ReserveInventory |
| State transition | Thay đổi trạng thái của quy trình | PAYMENT_AUTHORIZED → INVENTORY_PENDING |
| Compensation | Hành động nghiệp vụ để khắc phục bước đã hoàn tất | VoidPayment hoặc ReleaseInventory |
| Timeout | Sự kiện thời gian cho biết một bước chờ quá hạn | PaymentAuthorizationTimedOut |

Tên event nên diễn đạt kết quả đã xảy ra. Tên command nên diễn đạt hành động được yêu cầu. Không phát PaymentAuthorized trước khi cổng thanh toán thực sự xác nhận; nếu chỉ mới gửi yêu cầu, event phù hợp hơn là PaymentAuthorizationRequested hoặc một trạng thái yêu cầu tương ứng.

## 2. Khi nào cần saga hoặc process manager?

Một transaction database cục bộ phù hợp khi toàn bộ thay đổi có thể commit hoặc rollback trong cùng một ranh giới giao dịch. Khi quy trình đi qua nhiều module sở hữu dữ liệu riêng, nhiều dịch vụ hoặc nhiều hệ thống bên ngoài, không thể giả định một transaction ACID duy nhất bao phủ toàn bộ công việc.

Saga chia quy trình thành nhiều bước cục bộ. Mỗi bước commit độc lập và phát event về kết quả. Nếu một bước thất bại, saga có thể retry hoặc chạy các hành động bù cho những bước trước đó đã hoàn tất.

Process manager là thành phần giữ trạng thái và điều phối bước tiếp theo dựa trên event đã nhận. Nó trả lời các câu hỏi:

- Quy trình nào đang được xử lý?
- Quy trình đang ở trạng thái nào?
- Event vừa nhận có hợp lệ ở trạng thái này không?
- Cần phát command nào tiếp theo?
- Đã chờ quá hạn chưa?
- Nếu thất bại, cần retry, bù hay chuyển sang xử lý thủ công?

Một saga có thể được triển khai bằng choreography hoặc orchestration. Process manager thường là cách triển khai orchestration khi cần một nơi điều phối tường minh.

## 3. Chọn choreography hay orchestration

### Choreography

Trong choreography, mỗi module lắng nghe event mà nó quan tâm và tự quyết định bước tiếp theo. Không có một process manager trung tâm điều khiển toàn bộ chuỗi.

Ví dụ:

1. Order module phát OrderPlaced.
2. Payment module nhận event, xử lý thanh toán và phát PaymentAuthorized hoặc PaymentFailed.
3. Inventory module nhận PaymentAuthorized, giữ hàng và phát InventoryReserved hoặc InventoryReservationFailed.
4. Shipping module nhận InventoryReserved và tạo lô giao hàng.

Ưu điểm là các module ít phụ thuộc vào một bộ điều phối trung tâm. Cách này phù hợp với chuỗi ngắn, ít nhánh và quy tắc tương đối ổn định.

Khi quy trình có nhiều nhánh, timeout, retry, điều kiện hoàn tất và compensation, choreography có thể khiến luồng điều khiển bị phân tán. Để hiểu một quy trình, người vận hành phải lần theo nhiều listener ở nhiều module.

### Orchestration

Trong orchestration, một process manager theo dõi trạng thái quy trình và phát command yêu cầu các module thực hiện bước tiếp theo.

Ví dụ:

1. Order process manager nhận OrderPlaced.
2. Lưu trạng thái PAYMENT_PENDING và gửi AuthorizePayment.
3. Nhận PaymentAuthorized, chuyển sang INVENTORY_PENDING và gửi ReserveInventory.
4. Nhận InventoryReserved, chuyển sang SHIPPING_PENDING và gửi CreateShipment.
5. Nhận ShipmentCreated, chuyển sang COMPLETED.

Process manager làm rõ luồng điều khiển, nhánh lỗi và thời gian chờ. Đổi lại, nó trở thành một thành phần cần được lưu trạng thái, giám sát và mở rộng cẩn thận.

| Tiêu chí | Choreography | Orchestration |
|---|---|---|
| Điều khiển luồng | Phân tán trong listener của các module | Tập trung ở process manager |
| Phù hợp | Quy trình ngắn, ít nhánh | Quy trình dài, nhiều trạng thái và điều kiện |
| Khả năng quan sát | Cần lần theo nhiều event và listener | Có thể xem trạng thái quy trình tại một nơi |
| Phụ thuộc | Module phụ thuộc vào event contract | Process manager phụ thuộc vào command/event contract |
| Compensation | Các module tự phản ứng theo quy tắc đã thỏa thuận | Process manager quyết định hành động bù |
| Rủi ro chính | Luồng điều khiển khó nhìn thấy khi phức tạp | Bộ điều phối có thể trở thành điểm nghẽn hoặc nơi tập trung logic |

Không có lựa chọn đúng cho mọi hệ thống. Chọn theo độ phức tạp thực tế của quy trình và khả năng vận hành của đội ngũ.

## 4. Thiết kế trạng thái của saga

Một saga cần trạng thái bền vững để có thể tiếp tục sau khi process manager restart. Không nên chỉ giữ tiến trình trong biến bộ nhớ hoặc giữ một thread chờ phản hồi từ dịch vụ khác.

Ví dụ quy trình đặt hàng:

| Trạng thái | Event hoặc kết quả đầu vào | Hành động tiếp theo |
|---|---|---|
| STARTED | OrderPlaced | Gửi AuthorizePayment |
| PAYMENT_PENDING | PaymentAuthorized | Gửi ReserveInventory |
| PAYMENT_PENDING | PaymentFailed | Chuyển sang FAILED |
| INVENTORY_PENDING | InventoryReserved | Gửi CreateShipment |
| INVENTORY_PENDING | InventoryReservationFailed | Gửi VoidPayment |
| SHIPPING_PENDING | ShipmentCreated | Chuyển sang COMPLETED |
| COMPENSATING | PaymentVoided | Chuyển sang COMPENSATED |
| COMPENSATING | CompensationFailed | Chuyển sang MANUAL_REVIEW |

Trạng thái cần biểu đạt đủ thông tin để process manager quyết định hành động tiếp theo. Tùy quy trình, có thể lưu thêm:

- Saga ID và business/aggregate ID.
- Trạng thái hiện tại và phiên bản trạng thái.
- Các bước đã hoàn tất.
- Event ID đã xử lý.
- Thời điểm bắt đầu, cập nhật và deadline.
- Số lần thử, lỗi gần nhất và nguyên nhân thất bại.
- Dữ liệu tối thiểu cần thiết để tiếp tục hoặc bù.

Không lưu toàn bộ object graph của các module vào bản ghi saga. Chỉ lưu dữ liệu điều phối và định danh cần thiết; dữ liệu domain vẫn thuộc module sở hữu.

## 5. Xác định ranh giới và định danh của một chuỗi

Mỗi lần chạy quy trình cần một định danh ổn định, thường gọi là sagaId hoặc processId. Định danh này khác với eventId và aggregateId:

- **eventId:** nhận diện một message/event cụ thể, dùng để chống xử lý trùng.
- **sagaId:** nhận diện một lần chạy quy trình kéo dài.
- **aggregateId:** nhận diện đối tượng nghiệp vụ mà event liên quan, ví dụ orderId.
- **correlationId:** liên kết các message thuộc cùng một luồng nghiệp vụ hoặc request gốc.
- **causationId:** chỉ ra event/command nào trực tiếp gây ra message hiện tại.

Một đơn hàng có thể có nhiều saga khác nhau, chẳng hạn saga thanh toán và saga hoàn trả. Vì vậy không nên mặc định orderId luôn đủ để làm sagaId.

Ví dụ metadata của event:

~~~java
public record EventMetadata(
    UUID eventId,
    UUID sagaId,
    UUID correlationId,
    UUID causationId,
    long sequence,
    Instant occurredAt
) {}
~~~

Đây là cấu trúc minh họa. Hợp đồng thực tế có thể đặt metadata trong envelope hoặc header thay vì lặp lại trong từng event payload. Điều quan trọng là consumer có thể liên kết event với đúng quy trình và phát hiện event trùng hoặc sai thứ tự.

## 6. Quy tắc chuyển trạng thái

Process manager nên xử lý event bằng một state machine tường minh. Mỗi trạng thái chỉ chấp nhận một tập event nhất định và mỗi event hợp lệ dẫn đến một chuyển trạng thái có xác định.

Ví dụ:

~~~text
PAYMENT_PENDING + PaymentAuthorized
    -> INVENTORY_PENDING
    -> emit ReserveInventory

PAYMENT_PENDING + PaymentFailed
    -> FAILED

INVENTORY_PENDING + InventoryReserved
    -> SHIPPING_PENDING
    -> emit CreateShipment

INVENTORY_PENDING + InventoryReservationFailed
    -> COMPENSATING
    -> emit VoidPayment
~~~

Khi nhận event không hợp lệ với trạng thái hiện tại, process manager cần có chính sách rõ:

- Event đã xử lý trước đó: bỏ qua an toàn theo eventId.
- Event đến sớm hơn bước dự kiến: lưu chờ, retry hoặc yêu cầu đối soát.
- Event không liên quan saga: từ chối hoặc cách ly.
- Event hợp lệ về cấu trúc nhưng mâu thuẫn với trạng thái: ghi nhận để điều tra, không tự ý chuyển trạng thái.
- Event đến sau khi saga đã kết thúc: xử lý theo quy tắc late event đã định nghĩa.

Không nên dùng chuỗi if/else rời rạc mà không có kiểm tra trạng thái và tính nguyên tử. Nếu hai instance process manager cùng nhận event cho một saga, cả hai không được đồng thời áp dụng cùng một chuyển trạng thái và phát hai command trùng ngoài ý muốn.

## 7. Lưu trạng thái và phát command một cách nguyên tử

Một lỗi phổ biến là process manager cập nhật trạng thái trong database rồi gửi command đến broker bằng một thao tác độc lập. Nếu database commit nhưng gửi command thất bại, saga bị kẹt ở trạng thái mới mà không có bước tiếp theo. Nếu gửi command thành công nhưng database rollback, command có thể được thực hiện dù process manager vẫn nghĩ bước trước chưa hoàn tất.

Để tránh dual-write không kiểm soát, trạng thái saga và ý định phát message cần được lưu trong cùng transaction cục bộ khi có thể. Có thể dùng transactional outbox cho command/event đi ra broker; một relay gửi các bản ghi outbox sau khi transaction commit.

Trong cùng transaction, process manager có thể:

1. Khóa hoặc kiểm tra version của bản ghi saga.
2. Kiểm tra eventId đã được xử lý chưa.
3. Xác nhận event hợp lệ với trạng thái hiện tại.
4. Cập nhật trạng thái và version.
5. Ghi eventId vào inbox hoặc processed-event table.
6. Ghi command tiếp theo vào outbox.
7. Commit.

Relay có thể gửi lại command nếu không nhận được xác nhận. Vì vậy, consumer của command vẫn cần idempotency. Transactional outbox giảm rủi ro dual-write giữa database và broker, nhưng không tạo transaction phân tán giữa publisher, broker và tất cả consumer.

## 8. Chống xử lý trùng và xử lý event đến sai thứ tự

Hệ thống event thường có semantics at-least-once ở một hoặc nhiều chặng. Consumer phải giả định một event có thể được giao lại. Event ID cần được ghi nhận bền vững trong cùng transaction với thay đổi trạng thái và tác dụng phụ cần bảo vệ.

Một bảng inbox có thể lưu:

| Trường | Mục đích |
|---|---|
| event_id | Khóa duy nhất chống xử lý trùng |
| saga_id | Liên kết với quy trình |
| event_type | Phân loại event |
| received_at | Thời điểm nhận |
| processing_status | RECEIVED, PROCESSED, FAILED hoặc trạng thái tương đương |

Nếu event có sequence theo aggregate hoặc saga, process manager có thể phát hiện event đến không đúng thứ tự. Timestamp không phải lúc nào cũng đủ để xác định thứ tự vì đồng hồ giữa các hệ thống có thể lệch và message có thể được gửi lại.

Các cách xử lý event đến sai thứ tự:

- Lưu event vào inbox ở trạng thái chờ nếu bước trước chưa đến.
- Retry có giới hạn nếu độ trễ được dự kiến là ngắn.
- Yêu cầu module sở hữu cung cấp snapshot/trạng thái hiện tại để đối soát.
- Cách ly event mâu thuẫn để người vận hành xem xét.
- Dùng sequence/version để loại event cũ hoặc phát hiện khoảng trống.

Không tự động bỏ event chỉ vì nó đến muộn. Một event đến muộn có thể chứa kết quả nghiệp vụ quan trọng hoặc là tín hiệu cho thấy một bước đã hoàn tất sau timeout.

## 9. Timeout và timer bền vững

Saga thường chờ phản hồi từ dịch vụ bên ngoài. Chờ bằng cách giữ thread hoặc dùng sleep không phù hợp với quy trình kéo dài. Thay vào đó, lưu deadline vào trạng thái saga và dùng scheduler hoặc cơ chế timer bền vững để phát timeout event.

Ví dụ:

- PaymentAuthorizationRequested lúc 10:00.
- Deadline được đặt là 10:02.
- Nếu PaymentAuthorized hoặc PaymentFailed đến trước deadline, hủy timer.
- Nếu hết hạn mà chưa có kết quả, phát PaymentAuthorizationTimedOut.
- Process manager kiểm tra trạng thái hiện tại trước khi thực hiện timeout transition.

Timer cần có sagaId, bước đang chờ, deadline và token/version để timeout cũ không ảnh hưởng một lần retry mới. Một timeout event đã được lên lịch có thể đến sau khi saga đã hoàn tất; handler phải kiểm tra trạng thái và bỏ qua timeout lỗi thời một cách an toàn.

Timeout không chứng minh tác vụ ở hệ thống ngoài đã thất bại. Có thể hệ thống ngoài đã hoàn tất nhưng phản hồi bị trễ hoặc mất. Trước khi compensation, cần xác định liệu hành động gốc có thể đã thành công hay không và có API tra cứu/đối soát kết quả hay không.

## 10. Compensation: hành động bù nghiệp vụ

Saga không rollback transaction đã commit ở các hệ thống khác. Nó sử dụng hành động bù để đưa nghiệp vụ về một trạng thái chấp nhận được.

Ví dụ:

| Bước đã hoàn tất | Hành động bù có thể dùng |
|---|---|
| Đã cấp phép thanh toán | Hủy authorization |
| Đã thu tiền | Tạo refund |
| Đã giữ hàng | Giải phóng reservation |
| Đã tạo lô giao hàng | Hủy shipment nếu hãng vận chuyển cho phép |
| Đã phát hành hóa đơn | Phát hành chứng từ điều chỉnh theo quy định |

Compensation không nhất thiết đảo ngược hoàn toàn hành động ban đầu. Một khoản refund có thể mất phí hoặc cần thời gian; shipment có thể đã rời kho và không thể hủy. Vì vậy, mô hình hóa compensation như một bước nghiệp vụ độc lập với trạng thái và kết quả riêng.

Một số nguyên tắc:

- Mỗi hành động bù phải idempotent.
- Ghi nhận bước nào đã được bù và bước nào còn chờ.
- Có retry và timeout riêng cho compensation.
- Không đánh dấu saga COMPENSATED trước khi các bước bù bắt buộc hoàn tất.
- Nếu bù thất bại kéo dài, chuyển sang MANUAL_REVIEW và cung cấp dữ liệu để người vận hành xử lý.
- Lưu lại lịch sử hành động để audit và đối soát.

Không phải mọi lỗi đều cần compensation. Lỗi tạm thời có thể retry bước hiện tại. Chỉ bù khi quy tắc nghiệp vụ xác định quy trình không thể tiếp tục hoặc đã vượt giới hạn cho phép.

## 11. Ví dụ chuỗi event cho đơn hàng

Giả sử quy trình gồm thanh toán, giữ hàng và giao hàng. Process manager điều phối bằng các command; các module trả về event kết quả.

~~~mermaid
sequenceDiagram
    participant O as Order Module
    participant P as Payment Module
    participant I as Inventory Module
    participant S as Shipping Module
    participant M as Order Process Manager

    O->>M: OrderPlaced
    M->>P: AuthorizePayment
    P-->>M: PaymentAuthorized
    M->>I: ReserveInventory
    I-->>M: InventoryReserved
    M->>S: CreateShipment
    S-->>M: ShipmentCreated
    M->>O: CompleteOrder
    O-->>M: OrderCompleted
~~~

Nếu giữ hàng thất bại sau khi thanh toán được cấp phép, process manager có thể yêu cầu hủy authorization:

~~~mermaid
sequenceDiagram
    participant M as Order Process Manager
    participant I as Inventory Module
    participant P as Payment Module

    M->>I: ReserveInventory
    I-->>M: InventoryReservationFailed
    M->>P: VoidPayment
    P-->>M: PaymentVoided
    M->>M: Mark saga COMPENSATED
~~~

Hai sơ đồ là ví dụ luồng khái niệm. Tên command/event và thứ tự cụ thể cần theo chính sách nghiệp vụ. Ví dụ cũng cần định nghĩa điều gì xảy ra nếu payment void thất bại hoặc kết quả giữ hàng đến muộn.

## 12. Process manager trong ứng dụng Spring Modulith

Spring Modulith cung cấp cơ chế application event, listener và publication registry để tổ chức giao tiếp giữa các module trong cùng ứng dụng. Có thể xây dựng process manager như một module sở hữu trạng thái quy trình, lắng nghe event từ các module khác và phát command hoặc event tiếp theo.

Một cấu trúc hợp lý:

- Module Orders sở hữu trạng thái đơn hàng.
- Module Payments sở hữu thanh toán.
- Module Inventory sở hữu reservation.
- Module Shipping sở hữu shipment.
- Module Order Process sở hữu trạng thái điều phối của saga.

Process manager không nên truy cập trực tiếp repository nội bộ của Payments, Inventory hoặc Shipping. Nó giao tiếp qua event/command contract để giữ ranh giới module.

Spring Modulith không tự động cung cấp đầy đủ một saga engine cho mọi quy trình. Ứng dụng vẫn phải thiết kế state machine, lưu trạng thái process manager, timer, compensation, idempotency và cách phát command đáng tin cậy. Publication registry giúp theo dõi việc giao application event trong ứng dụng; outbox/adapter cần được thiết kế cho message đi ra broker hoặc dịch vụ bên ngoài.

Listener có thể được triển khai bằng listener Spring phù hợp với transaction model. Ví dụ sau chỉ minh họa cách một process manager nhận event; phần lưu state và phát command phải được thực hiện trong transaction có cơ chế outbox hoặc publication phù hợp:

~~~java
@Component
class OrderProcessManager {

    private final SagaRepository sagas;
    private final ApplicationEventPublisher events;

    OrderProcessManager(
        SagaRepository sagas,
        ApplicationEventPublisher events
    ) {
        this.sagas = sagas;
        this.events = events;
    }

    @Transactional
    public void on(PaymentAuthorized event) {
        OrderSaga saga = sagas.findById(event.sagaId())
            .orElseThrow();

        if (saga.isTerminal()) {
            return;
        }

        if (saga.hasProcessed(event.eventId())) {
            return;
        }

        saga.paymentAuthorized(event.eventId());
        events.publishEvent(
            new ReserveInventory(
                saga.id(),
                saga.orderId(),
                event.eventId()
            )
        );
    }
}
~~~

Đoạn mã là minh họa khái niệm, cần bổ sung cơ chế xử lý đồng thời và lưu event đã xử lý với ràng buộc duy nhất. Việc publish application event trong cùng transaction chỉ bảo đảm điều cần thiết khi listener/publication registry và transaction manager được cấu hình phù hợp. Nếu ReserveInventory cần đi ra broker, hãy bảo đảm ý định gửi được lưu bền vững cùng trạng thái saga, chẳng hạn qua outbox.

## 13. Phục hồi khi process manager restart

Process manager phải có khả năng khởi động lại và tiếp tục quy trình đang chạy. Trạng thái saga cần được lưu bền vững, không phụ thuộc bộ nhớ của instance.

Khi ứng dụng restart:

1. Đọc các saga chưa ở trạng thái terminal.
2. Khôi phục deadline hoặc timer còn hiệu lực.
3. Xác định command đã ghi vào outbox nhưng chưa được relay.
4. Tiếp tục retry các bước đến hạn theo chính sách.
5. Nhận event đến muộn và kiểm tra trạng thái trước khi áp dụng.
6. Đưa saga quá hạn hoặc mâu thuẫn vào hàng đợi điều tra.

Không cần tải tất cả saga đang hoạt động vào bộ nhớ. Có thể truy vấn theo trạng thái, deadline hoặc partition key để xử lý theo batch. Cần giới hạn concurrency để quá trình phục hồi không gây tải đột biến lên database và broker.

## 14. Quan sát và vận hành chuỗi event

Một quy trình saga cần được quan sát từ đầu đến cuối. Log riêng lẻ của từng module không đủ để hiểu một saga bị kẹt ở bước nào.

Theo dõi các chỉ số:

| Metric | Ý nghĩa |
|---|---|
| Active saga count | Số quy trình đang chạy |
| Saga age | Thời gian từ khi quy trình bắt đầu |
| Duration by outcome | Thời gian hoàn tất, thất bại hoặc bù |
| Saga by state | Số quy trình ở từng trạng thái |
| Timeout count | Số bước vượt deadline |
| Compensation success/failure | Kết quả các hành động bù |
| Duplicate event count | Tần suất event được nhận lặp |
| Out-of-order event count | Số event đến không đúng trình tự |
| Outbox/inbox backlog | Công việc đang chờ phát hoặc xử lý |
| Manual review count | Số saga cần con người can thiệp |

Mỗi log và trace nên có sagaId, correlationId, eventId, eventType, currentState và stepName. Không ghi toàn bộ payload nhạy cảm vào log.

Dashboard nên cho phép tìm một saga theo business ID và xem lịch sử chuyển trạng thái, event nhận được, command đã phát, retry, timeout và compensation. Cần có cảnh báo cho saga ở trạng thái chờ quá lâu hoặc compensation thất bại.

## 15. Kiểm thử chuỗi event và saga

Kiểm thử từng listener riêng lẻ là chưa đủ. Cần xác minh cả state machine và các tình huống lỗi xuyên suốt quy trình.

### Unit test cho state transition

Kiểm tra từng cặp trạng thái/event:

- Event hợp lệ tạo trạng thái và command tiếp theo đúng.
- Event trùng không tạo command thứ hai.
- Event không hợp lệ không làm thay đổi trạng thái.
- Saga terminal không bị event muộn mở lại ngoài quy tắc.
- Compensation chỉ chạy cho các bước đã hoàn tất.

### Integration test

Kiểm tra transaction, repository, publication registry và outbox:

- Trạng thái saga và command được ghi cùng transaction.
- Rollback không để lại trạng thái mới thiếu command.
- Relay có thể gửi lại command sau restart.
- Consumer xử lý command trùng an toàn.
- Event được giao sau commit theo cấu hình listener.

### Failure scenario test

Mô phỏng:

- Payment thành công nhưng phản hồi bị trễ.
- Inventory giữ hàng thất bại.
- Timeout xảy ra đồng thời với event kết quả.
- Process manager restart giữa hai bước.
- Broker ngừng hoạt động khi command được ghi.
- Event bị gửi lặp hoặc đến sai thứ tự.
- Compensation thất bại nhiều lần.
- Consumer xử lý tác dụng phụ nhưng ack bị mất.

### End-to-end test

Chạy một quy trình thành công và các nhánh lỗi quan trọng. Xác minh trạng thái cuối, các hành động bù, số lần phát command và lịch sử event. Không chỉ kiểm tra rằng message đã được gửi; cần xác nhận kết quả nghiệp vụ cuối cùng.

## 16. Những lỗi thiết kế thường gặp

**Giữ trạng thái saga trong bộ nhớ.** Process restart làm mất tiến trình và timer. Lưu trạng thái bền vững trong database.

**Dùng event thay cho command.** Event mô tả sự thật đã xảy ra; command yêu cầu một hành động. Phân biệt hai loại để consumer hiểu đúng trách nhiệm.

**Không có sagaId hoặc correlationId.** Không thể liên kết các event thuộc cùng một lần chạy. Tạo định danh từ đầu và truyền qua các chặng.

**Phát command trước khi lưu trạng thái.** Nếu gửi thành công rồi database rollback, quy trình bị lệch. Ghi state và outbox trong cùng transaction.

**Giả định event chỉ đến một lần.** Retry và redelivery có thể tạo bản sao. Dùng event ID cùng inbox hoặc unique constraint để chống trùng.

**Coi timeout là thất bại chắc chắn.** Hệ thống ngoài có thể đã hoàn tất nhưng phản hồi bị trễ. Đối soát trạng thái trước khi bù.

**Compensation không idempotent.** Retry hành động bù có thể tạo refund hoặc giải phóng tài nguyên nhiều lần. Mỗi bước bù cần định danh và trạng thái riêng.

**Process manager biết quá nhiều chi tiết domain.** Điều này phá vỡ ranh giới module. Process manager điều phối qua contract và để module sở hữu dữ liệu quyết định quy tắc domain của nó.

**Không có đường xử lý thủ công.** Một số lỗi không thể tự phục hồi. Cần MANUAL_REVIEW, audit trail và công cụ vận hành có kiểm soát.

## 17. Checklist thiết kế chuỗi event

- [ ] Đã xác định quy trình nghiệp vụ và điều kiện hoàn tất.
- [ ] Đã chọn choreography hay orchestration theo độ phức tạp.
- [ ] Mỗi event mô tả một sự thật đã xảy ra.
- [ ] Command và event có ngữ nghĩa riêng.
- [ ] Có sagaId, eventId, correlationId và causationId phù hợp.
- [ ] Trạng thái process manager được lưu bền vững.
- [ ] State transition kiểm tra trạng thái hiện tại và version.
- [ ] State update và ý định phát command được lưu nguyên tử.
- [ ] Inbox/processed-event chống xử lý trùng.
- [ ] Có quy tắc xử lý event đến sai thứ tự và event muộn.
- [ ] Timeout dùng timer bền vững, không giữ thread chờ.
- [ ] Compensation được định nghĩa cho các bước có thể bù.
- [ ] Retry, timeout và compensation có giới hạn và quan sát.
- [ ] Có MANUAL_REVIEW cho trường hợp không thể tự phục hồi.
- [ ] Có metric, trace và lịch sử saga để vận hành.
- [ ] Đã kiểm thử restart, redelivery, timeout và lỗi compensation.

## 18. Nguyên tắc tổ chức chuỗi event

Một chuỗi event nghiệp vụ đáng tin cậy cần mô tả rõ điều gì đã xảy ra, quy trình đang ở trạng thái nào và bước tiếp theo cần thực hiện. Với quy trình ngắn, choreography có thể giữ các module độc lập. Với quy trình dài, nhiều nhánh, timeout và compensation, process manager giúp làm rõ luồng điều phối.

Trong Spring Modulith, application event và publication registry hỗ trợ giao tiếp giữa các module và theo dõi publication. Để xây dựng saga hoàn chỉnh, ứng dụng cần bổ sung trạng thái bền vững, state machine, inbox/outbox, timer, idempotency và quy trình compensation. Khi các thành phần này được thiết kế cùng nhau, quy trình có thể tiếp tục sau restart, xử lý event trùng hoặc đến muộn và đưa nghiệp vụ về trạng thái có thể chấp nhận khi một bước thất bại.
