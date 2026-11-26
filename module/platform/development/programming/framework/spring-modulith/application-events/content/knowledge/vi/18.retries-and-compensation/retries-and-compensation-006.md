# Bù trừ nghiệp vụ

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith phối hợp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Publisher công bố điều đã xảy ra; listener phản ứng với sự kiện trong phạm vi module của mình. Khi một quy trình trải qua nhiều module và nhiều transaction, có những tình huống một bước đã hoàn tất nhưng bước tiếp theo thất bại. Khi đó, transaction database ban đầu không thể rollback toàn bộ các thay đổi đã commit ở những module khác.

**Bù trừ nghiệp vụ** là cách đưa quy trình phân tán về một trạng thái nghiệp vụ chấp nhận được bằng những hành động mới có ý nghĩa riêng. Ví dụ, nếu đơn hàng đã giữ hàng nhưng thanh toán không thành công, hệ thống có thể yêu cầu giải phóng phần hàng đã giữ và chuyển đơn hàng sang trạng thái cần xử lý. Hành động giải phóng hàng là một nghiệp vụ mới, có thể thất bại và cần được theo dõi như mọi bước khác.

## 1. Bù trừ giải quyết vấn đề gì?

Một transaction cục bộ có thể đảm bảo nhiều thay đổi trong cùng database cùng commit hoặc cùng rollback. Nhưng một quy trình qua Order, Inventory và Payment thường gồm nhiều transaction độc lập:

1. Order tạo đơn hàng và phát sự kiện yêu cầu giữ hàng.
2. Inventory giữ hàng và phát sự kiện xác nhận.
3. Payment thực hiện thu tiền.
4. Order chuyển đơn hàng sang trạng thái đã thanh toán.

Giả sử bước 2 thành công nhưng bước 3 thất bại. Transaction tạo đơn hàng và transaction giữ hàng có thể đã commit. Không có lệnh rollback database nào có thể tự động đảo ngược hai transaction đó như thể chúng chưa từng xảy ra. Hệ thống cần phát sinh các hành động nghiệp vụ để giải phóng hàng và cập nhật trạng thái đơn hàng.

Đây là tình huống thường được xử lý bằng mô hình **Saga**. Mỗi bước của saga thực hiện trong transaction cục bộ của module sở hữu dữ liệu. Nếu quy trình không thể tiếp tục, các bước bù trừ được thực hiện để đưa hệ thống về một trạng thái cuối cùng phù hợp.

| Khái niệm | Ý nghĩa |
| --- | --- |
| Transaction cục bộ | Đơn vị commit hoặc rollback trong một module hoặc một resource transaction. |
| Saga | Chuỗi bước nghiệp vụ được phối hợp qua nhiều transaction cục bộ. |
| Hành động bù trừ | Một thao tác nghiệp vụ mới nhằm xử lý hậu quả của bước đã hoàn tất. |
| Sự kiện bù trừ | Thông điệp cho biết cần thực hiện hoặc đã hoàn tất một hành động bù. |
| Trạng thái saga | Trạng thái tổng thể của quy trình, bao gồm tiến trình thuận và tiến trình bù trừ. |

Bù trừ không phải là khôi phục dữ liệu về đúng ảnh chụp trước đó. Ví dụ, một khoản hoàn tiền không xóa sự kiện đã thu tiền; nó tạo thêm một giao dịch tài chính có thể kiểm toán. Một lần giải phóng hàng không xóa lịch sử giữ hàng; nó ghi nhận hàng đã được trả về khả dụng.

## 2. Chọn hành động bù theo ý nghĩa nghiệp vụ

Hành động bù phải do module sở hữu nghiệp vụ quyết định. Module Order không nên tự cập nhật trực tiếp bảng reservation của Inventory hoặc bảng giao dịch của Payment. Order chỉ phát yêu cầu hoặc sự kiện phù hợp; Inventory và Payment kiểm tra điều kiện rồi thực hiện thao tác trên dữ liệu do mình quản lý.

Ví dụ về các cặp thao tác thuận và bù:

| Bước thuận | Hành động bù có thể có | Điểm cần lưu ý |
| --- | --- | --- |
| Giữ hàng | Giải phóng reservation | Chỉ giải phóng reservation thuộc đúng đơn hàng và đúng lần giữ hàng. |
| Thu tiền | Hoàn tiền | Hoàn tiền có thể cần quy trình riêng và không nhất thiết hoàn tất tức thì. |
| Tạo lịch giao | Hủy lịch giao | Nếu lịch đã được thực hiện, có thể cần quy trình trả hàng thay vì hủy. |
| Cấp quyền truy cập | Thu hồi quyền | Cần xem xét các tác động đã phát sinh trong thời gian quyền còn hiệu lực. |
| Phát hành phiếu | Hủy hoặc điều chỉnh phiếu | Có thể phải tạo chứng từ điều chỉnh để giữ dấu vết kiểm toán. |

Không phải mọi hành động đều có thể đảo ngược hoàn toàn. Một email đã gửi không thể thu hồi khỏi hộp thư người nhận; một thông báo đã hiển thị không thể làm người dùng quên nội dung đó. Trong các trường hợp này, bù trừ có thể là gửi thông báo đính chính, ghi nhận sai sót hoặc yêu cầu một quy trình hỗ trợ khác.

Trước khi triển khai, hãy trả lời ba câu hỏi: hành động thuận đã tạo ra cam kết nghiệp vụ nào; module nào có thẩm quyền thay đổi cam kết đó; và hành động bù nào đưa quy trình về trạng thái hợp lệ? Câu trả lời nên được thể hiện trong mô hình trạng thái và API sự kiện, không chỉ trong một đoạn xử lý exception.

## 3. Phối hợp bù trừ bằng application events

Với cách phối hợp theo sự kiện (choreography), mỗi module phản ứng với event và công bố event tiếp theo. Order không gọi trực tiếp Inventory hoặc Payment; các module tham gia giao tiếp qua hợp đồng sự kiện.

Một luồng minh họa:

~~~mermaid
sequenceDiagram
    participant O as Order
    participant I as Inventory
    participant P as Payment

    O->>I: ReserveInventoryRequested
    I->>I: Giữ hàng trong transaction cục bộ
    I-->>O: InventoryReserved
    O->>P: ChargePaymentRequested
    P->>P: Thực hiện thu tiền
    P-->>O: PaymentFailed
    O->>O: Đánh dấu quy trình đang bù trừ
    O-->>I: ReleaseInventoryRequested
    I->>I: Giải phóng reservation
    I-->>O: InventoryReleased
    O->>O: Đánh dấu đơn hàng đã được bù trừ
~~~

Sự kiện PaymentFailed không trực tiếp sửa dữ liệu Inventory. Order quyết định quy trình cần bù trừ và phát ReleaseInventoryRequested. Inventory kiểm tra yêu cầu, giải phóng reservation của chính nó rồi phát InventoryReleased. Khi nhận xác nhận, Order cập nhật trạng thái tổng thể.

Trong một quy trình có nhiều bước đã hoàn tất, các hành động bù thường được thực hiện theo thứ tự ngược với các phụ thuộc của bước thuận. Nếu bước C phụ thuộc kết quả của B, và B phụ thuộc A, việc bù trừ thường bắt đầu từ C rồi đến B và A. Tuy nhiên, thứ tự chính xác phải dựa trên quy tắc nghiệp vụ: có hành động bù nào cần chạy song song, có hành động nào phải chờ kết quả khác, và điều gì xảy ra nếu một bước bù thất bại?

Với choreography, mỗi listener cần hiểu rõ event nào có thể đến trước, đến sau hoặc lặp lại. Khi quy trình có nhiều nhánh, nhiều điều kiện và nhiều bước bù, một module điều phối (orchestration) có thể quản lý trạng thái saga và phát command/event cho các module. Dù chọn choreography hay orchestration, quyền sở hữu dữ liệu vẫn thuộc module thực hiện nghiệp vụ.

## 4. Thiết kế hợp đồng sự kiện cho bù trừ

Sự kiện nên mang định danh đủ để liên kết bước thuận, bước bù và toàn bộ saga. Ví dụ:

~~~java
public record ReleaseInventoryRequested(
    UUID eventId,
    UUID sagaId,
    UUID orderId,
    UUID reservationId,
    String reason
) {}

public record InventoryReleased(
    UUID eventId,
    UUID sagaId,
    UUID orderId,
    UUID reservationId
) {}
~~~

Trong đó:

- **eventId** nhận diện một thông điệp cụ thể và hỗ trợ chống xử lý trùng.
- **sagaId** liên kết các bước của cùng một quy trình phân tán.
- **orderId** là khóa nghiệp vụ để tra cứu đơn hàng.
- **reservationId** chỉ rõ reservation cần giải phóng, tránh giải phóng nhầm một lần giữ hàng khác.
- **reason** ghi nhận nguyên nhân bù trừ ở mức đủ dùng cho xử lý và kiểm toán.

Nếu một đơn hàng có thể giữ hàng nhiều lần, chỉ dùng orderId là chưa đủ để xác định đối tượng bù. Hợp đồng cần có reservationId hoặc một định danh tương đương. Nếu một hành động bù cần tham chiếu đến giao dịch thanh toán, hãy dùng paymentTransactionId thay vì chỉ truyền số tiền.

Tên sự kiện nên mô tả điều đã xảy ra hoặc yêu cầu nghiệp vụ rõ ràng. Có thể phân biệt event thông báo kết quả như InventoryReleased với command yêu cầu thực hiện như ReleaseInventoryRequested. Sự phân biệt này giúp người đọc biết listener đang phản ứng với một sự thật đã xảy ra hay đang nhận nhiệm vụ cần thực hiện.

## 5. Thực hiện handler bù trừ trong Spring Modulith

Module Inventory sở hữu reservation và cung cấp listener xử lý yêu cầu giải phóng. Listener chỉ thay đổi dữ liệu của Inventory, sau đó công bố kết quả. Ví dụ dưới đây lược bỏ import và chi tiết repository:

~~~java
@Component
@RequiredArgsConstructor
class ReleaseInventoryHandler {

    private final InventoryService inventory;
    private final ApplicationEventPublisher events;

    @ApplicationModuleListener
    void on(ReleaseInventoryRequested request) {
        inventory.releaseReservation(
            request.reservationId(),
            request.orderId(),
            request.sagaId()
        );

        events.publishEvent(new InventoryReleased(
            UUID.randomUUID(),
            request.sagaId(),
            request.orderId(),
            request.reservationId()
        ));
    }
}
~~~

Service thực hiện kiểm tra và thay đổi reservation trong transaction cục bộ. Một cách triển khai có thể kiểm tra reservation đã được giải phóng chưa, xác minh reservation thuộc đúng orderId và cập nhật trạng thái theo một chuyển đổi hợp lệ. Nếu reservation đã được giải phóng bởi chính yêu cầu này, lần gọi lại có thể kết thúc thành công mà không tạo thêm tác động.

~~~java
@Service
@RequiredArgsConstructor
class InventoryService {

    private final ReservationRepository reservations;

    @Transactional
    public void releaseReservation(
            UUID reservationId,
            UUID orderId,
            UUID sagaId) {

        Reservation reservation = reservations.findById(reservationId)
            .orElseThrow(() -> new ReservationNotFoundException(reservationId));

        if (!reservation.belongsTo(orderId)) {
            throw new ReservationOwnershipMismatchException(reservationId);
        }

        if (reservation.isReleasedFor(sagaId)) {
            return;
        }

        if (!reservation.canBeReleased()) {
            throw new ReservationCannotBeReleasedException(reservationId);
        }

        reservation.releaseFor(sagaId);
    }
}
~~~

Trong ví dụ, nếu reservation không tồn tại, thuộc đơn hàng khác hoặc không thể giải phóng do trạng thái nghiệp vụ, service ném exception chuyên biệt. Hệ thống cần phân loại lỗi này: lỗi hạ tầng tạm thời có thể retry; lỗi dữ liệu hoặc xung đột nghiệp vụ có thể cần can thiệp hoặc một nhánh xử lý khác. Không nên biến mọi exception thành retry vô hạn.

**@ApplicationModuleListener** là cách thuận tiện để xử lý event giữa các module với listener bất đồng bộ và transaction riêng theo cơ chế Spring Modulith. Nếu dùng **@TransactionalEventListener** trực tiếp, hãy chọn transaction phase phù hợp, chẳng hạn AFTER_COMMIT, và xác định rõ transaction của phần xử lý bù. Cần kiểm thử trên cấu hình thực tế để xác nhận ranh giới commit và cách publication được hoàn tất.

## 6. Trạng thái của saga và bước bù trừ

Không nên chỉ lưu một cờ boolean kiểu failed. Một quy trình cần phân biệt thất bại ở bước thuận, đang yêu cầu bù, đã hoàn tất bù và bù trừ thất bại cần xử lý. Ví dụ, trạng thái tổng thể của đơn hàng có thể gồm:

| Trạng thái | Ý nghĩa |
| --- | --- |
| IN_PROGRESS | Các bước thuận đang được thực hiện. |
| COMPENSATING | Quy trình đã quyết định bù trừ; một hoặc nhiều hành động bù đang chờ xử lý. |
| COMPENSATED | Các hành động bù bắt buộc đã hoàn tất theo quy tắc nghiệp vụ. |
| COMPENSATION_FAILED | Có hành động bù không thể tiếp tục tự động và cần điều tra hoặc can thiệp. |
| COMPLETED | Quy trình thuận đã hoàn tất thành công. |

Trạng thái của từng bước cũng cần được theo dõi. Ví dụ, một saga có thể đã giải phóng hàng nhưng vẫn đang chờ hoàn tiền. Khi đó, trạng thái tổng thể chưa thể là COMPENSATED nếu nghiệp vụ yêu cầu cả hai hành động bù phải hoàn tất.

Việc chuyển trạng thái cần có điều kiện rõ ràng. Chẳng hạn, chỉ chuyển từ COMPENSATING sang COMPENSATED khi tất cả hành động bù bắt buộc đã được xác nhận. Một event đến trễ không được phép đưa saga đã hoàn tất quay về trạng thái cũ. Nên lưu phiên bản trạng thái hoặc kiểm soát chuyển trạng thái trong transaction để xử lý cạnh tranh giữa các listener.

## 7. Retry hành động bù và xử lý lỗi

Bù trừ cũng là một bước nghiệp vụ có thể thất bại. Inventory có thể không truy cập được database; Payment có thể tạm thời từ chối kết nối khi hoàn tiền; dịch vụ vận chuyển có thể chưa nhận được yêu cầu hủy. Vì vậy, không thể giả định rằng phát một event bù là quy trình đã được khôi phục.

Hãy phân biệt ít nhất ba nhóm kết quả:

1. **Thành công:** hành động bù đã commit và listener có thể xác nhận hoàn tất.
2. **Lỗi tạm thời:** dependency mất kết nối, timeout hoặc lỗi hạ tầng; có thể retry sau khoảng chờ.
3. **Lỗi nghiệp vụ hoặc dữ liệu:** reservation đã ở trạng thái không thể giải phóng, giao dịch không tồn tại hoặc yêu cầu không khớp; cần nhánh xử lý nghiệp vụ hay can thiệp.

Một chính sách retry nên có giới hạn số lần, khoảng chờ tăng dần, jitter khi phù hợp và cảnh báo khi vượt ngưỡng. Khi retry không còn phù hợp, chuyển bước bù sang trạng thái cần điều tra và lưu thông tin lỗi đủ để người vận hành xử lý. Không nên xóa yêu cầu bù thất bại vì đó là dấu vết của nghĩa vụ nghiệp vụ chưa hoàn tất.

Spring Modulith Event Publication Registry giúp theo dõi publication đến transactional listener và nhận diện publication chưa được đánh dấu hoàn tất. Khi listener thất bại do exception, publication có thể còn incomplete để được recovery hoặc resubmit theo cấu hình và API của phiên bản đang dùng. Registry hỗ trợ việc giao lại event; nó không tự quyết định một lỗi nghiệp vụ cần bù theo cách nào, không thay thế trạng thái saga và cũng không cung cấp toàn bộ chính sách retry nghiệp vụ.

Một điểm quan trọng: nếu listener xử lý thành công về mặt kỹ thuật nhưng phát hiện yêu cầu bù không hợp lệ, listener không nên âm thầm kết thúc như thể bù đã hoàn tất. Hãy ghi nhận kết quả nghiệp vụ rõ ràng, phát event báo lỗi bù hoặc cập nhật trạng thái bước bù để saga chuyển sang nhánh xử lý phù hợp. Việc hoàn tất publication chỉ xác nhận listener đã xử lý thông điệp; nó không tự chứng minh toàn bộ mục tiêu nghiệp vụ của saga đã đạt.

## 8. Idempotency và xử lý event đến lặp

Publication có thể được giao lại sau timeout, lỗi listener hoặc restart. Một hành động bù vì thế phải idempotent: nhận cùng một yêu cầu nhiều lần vẫn tạo ra cùng kết quả nghiệp vụ như xử lý một lần.

Các biện pháp thường dùng:

- Dùng eventId hoặc một business key ổn định để nhận diện yêu cầu bù.
- Lưu dấu vết đã xử lý trong cùng transaction với thay đổi nghiệp vụ.
- Đặt unique constraint cho cặp định danh như sagaId và compensationStepId.
- Kiểm tra trạng thái hiện tại trước khi thay đổi, ví dụ reservation đã giải phóng cho saga này hay chưa.
- Với nhà cung cấp bên ngoài, truyền idempotency key nếu API hỗ trợ và lưu mã giao dịch trả về.

Ví dụ, nếu yêu cầu ReleaseInventoryRequested được giao hai lần, Inventory không được cộng lại số lượng khả dụng hai lần. Một unique key cho reservationId và loại hành động bù, hoặc một chuyển đổi trạng thái có điều kiện, có thể ngăn tác động lặp.

Không nên chỉ dựa vào bộ nhớ của tiến trình để ghi nhận event đã xử lý. Sau restart, bộ nhớ mất đi và event có thể được giao lại. Dấu vết chống trùng cần được lưu bền vững trong cùng ranh giới transaction với thay đổi dữ liệu mà nó bảo vệ.

## 9. Bảo đảm tính nhất quán khi phát sự kiện bù

Một lỗi phổ biến là cập nhật trạng thái saga thành COMPENSATING rồi phát event bù trong hai thao tác không nguyên tử. Nếu database commit nhưng ứng dụng dừng trước khi publish, saga bị kẹt mà module nhận không biết cần làm gì. Nếu publish trước khi commit, listener có thể nhận một yêu cầu dựa trên trạng thái chưa được lưu.

Hãy dùng cơ chế phát event có ranh giới transaction phù hợp. Với Spring Modulith, Event Publication Registry theo dõi publication của transactional listener và hỗ trợ lưu trạng thái giao sự kiện theo persistent publication repository được cấu hình. Cần cấu hình store và transaction manager tương thích để việc ghi nhận publication phối hợp đúng với transaction phát sinh.

Nếu ứng dụng dùng outbox riêng, hãy xác định rõ outbox chịu trách nhiệm phát thông điệp ra ngoài hay registry chịu trách nhiệm theo dõi listener nội bộ. Tránh tạo hai cơ chế ghi và retry chồng lấn mà không có quy tắc ownership, vì chúng có thể khiến cùng một hành động bù được phát nhiều lần hoặc khó xác định nơi cần recovery.

Sự kiện bù nên được phát từ transaction cập nhật trạng thái saga hoặc từ một bước điều phối đã lưu bền vững. Sau khi publication được ghi nhận, listener có thể xử lý bất đồng bộ; khi hoàn tất, event kết quả sẽ đưa saga tiến đến trạng thái tiếp theo.

## 10. Kiểm thử quy trình bù trừ

Unit test cho service bù giúp kiểm tra các quy tắc như quyền sở hữu reservation, điều kiện giải phóng và xử lý yêu cầu lặp. Integration test cần xác minh transaction, event dispatch và publication registry phối hợp đúng trong cấu hình ứng dụng.

Các tình huống nên bao phủ:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Bước thuận thành công | Saga chuyển sang bước tiếp theo và event kết quả được công bố. |
| Bước thuận thất bại sau khi có bước đã commit | Saga chuyển sang COMPENSATING và phát đúng yêu cầu bù. |
| Bù trừ thành công | Dữ liệu của module sở hữu được cập nhật; event xác nhận được phát. |
| Bù trừ nhận event trùng | Không tạo tác động nghiệp vụ lần thứ hai. |
| Bù trừ lỗi tạm thời | Publication hoặc bước bù còn khả năng recovery theo chính sách. |
| Bù trừ lỗi nghiệp vụ | Saga ghi nhận trạng thái cần điều tra, không báo COMPENSATED sai. |
| Event đến sai thứ tự | Chuyển trạng thái không vi phạm quy tắc nghiệp vụ. |
| Tiến trình restart | Saga và các bước bù chưa hoàn tất vẫn có thể được tìm thấy. |
| Nhiều hành động bù | Saga chỉ hoàn tất khi các hành động bắt buộc đều có kết quả phù hợp. |

Một bài test quan trọng là mô phỏng handler đã thực hiện thay đổi nghiệp vụ nhưng tiến trình gặp lỗi trước khi publication được xác nhận completed. Khi event được giao lại, test phải chứng minh listener idempotent và không lặp side effect.

## 11. Quan sát và điều tra bù trừ

Trong môi trường vận hành, cần quan sát cả publication và trạng thái nghiệp vụ. Một publication completed có thể chỉ cho biết listener đã xử lý yêu cầu và ghi nhận rằng nghiệp vụ không thể bù tự động. Ngược lại, một publication incomplete có thể là lỗi giao event dù hành động bù chưa hề bắt đầu.

Các chỉ số hữu ích gồm:

- Số saga đang ở trạng thái COMPENSATING và COMPENSATION_FAILED.
- Số bước bù đang chờ, đang retry và đã hoàn tất.
- Tuổi của yêu cầu bù lâu nhất chưa được xác nhận.
- Tỷ lệ thành công của hành động bù theo module và loại nghiệp vụ.
- Số publication incomplete cùng listener đích và thời gian tồn tại.
- Số lần xử lý trùng được phát hiện và số trường hợp cần can thiệp thủ công.

Log và trace nên mang sagaId, eventId, orderId hoặc business key, compensationStepId và correlationId. Các định danh này giúp nối sự kiện thuận, lỗi phát sinh, yêu cầu bù và kết quả bù. Tránh ghi toàn bộ payload hay dữ liệu thanh toán nhạy cảm vào log.

Khi điều tra một saga bị kẹt, hãy xác định bước thuận cuối cùng đã commit, những cam kết nghiệp vụ đã phát sinh, các hành động bù bắt buộc, publication tương ứng và kết quả của từng listener. Chỉ resubmit sau khi xác định retry có an toàn và listener đã có cơ chế chống tác động lặp. Nếu cần thao tác thủ công, hãy ghi nhận người thực hiện, lý do, thời điểm và kết quả để giữ lịch sử kiểm toán.

## 12. Checklist thiết kế

- Mỗi bước thuận và hành động bù có chủ sở hữu module rõ ràng.
- Hành động bù được mô tả như nghiệp vụ mới, có điều kiện và trạng thái riêng.
- Saga lưu được trạng thái tổng thể và trạng thái từng bước bù.
- Hợp đồng event mang sagaId cùng định danh tài nguyên cần bù.
- Module nhận chỉ cập nhật dữ liệu thuộc quyền sở hữu của nó.
- Hành động bù idempotent và có dấu vết chống xử lý trùng bền vững.
- Retry phân biệt lỗi tạm thời với lỗi nghiệp vụ, có giới hạn và cảnh báo.
- Event publication dùng persistent store và transaction manager phù hợp với yêu cầu durability.
- Không đánh dấu saga COMPENSATED khi còn hành động bù bắt buộc chưa hoàn tất.
- Integration test bao phủ commit, rollback, duplicate, lỗi, restart và nhiều bước bù.
- Dashboard và log có thể lần theo saga từ bước thuận đến kết quả bù.

Bù trừ nghiệp vụ giúp các module phối hợp khôi phục quy trình phân tán mà vẫn giữ quyền sở hữu dữ liệu riêng. Khi hành động bù được thiết kế như một bước nghiệp vụ có trạng thái, event contract rõ ràng, retry có kiểm soát, idempotency và quan sát đầy đủ, hệ thống có thể xử lý cả lỗi tạm thời lẫn những trường hợp cần can thiệp mà không giả định rằng nhiều transaction độc lập có thể rollback như một transaction duy nhất.
