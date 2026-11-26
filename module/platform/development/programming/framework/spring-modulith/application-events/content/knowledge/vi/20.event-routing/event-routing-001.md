# Event destination

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events là cơ chế để các module Spring Modulith giao tiếp qua những sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Publisher công bố một sự kiện mô tả điều đã xảy ra; các listener phù hợp nhận và xử lý sự kiện trong phạm vi trách nhiệm của mình.

Khi thiết kế một luồng event, cần xác định rõ **destination**: thành phần nào cần nhận sự kiện, vì sao thành phần đó quan tâm và điều kiện nào quyết định việc xử lý. Với Spring application events bên trong một ứng dụng, publisher thường không chỉ định một địa chỉ nhận cụ thể trong lệnh publishEvent. Spring tìm các listener đã đăng ký có kiểu sự kiện tương thích; một event có thể được giao cho nhiều listener. Vì vậy, destination nội bộ thường là tập hợp listener phù hợp chứ không phải một queue duy nhất.

## 1. Destination trong mô hình application events

Một event biểu diễn một sự thật nghiệp vụ, ví dụ **OrderConfirmed**. Module Order công bố sự kiện khi đơn hàng được xác nhận. Module Inventory có thể nhận để giữ hàng, còn module Notification có thể nhận để gửi thông báo. Publisher không cần biết hai module đó triển khai xử lý như thế nào.

| Thành phần | Trách nhiệm |
| --- | --- |
| Publisher | Công bố event sau khi nghiệp vụ phát sinh sự kiện đã được xác định. |
| Event type | Mô tả sự kiện và dữ liệu cần thiết cho các bên nhận. |
| Listener | Đăng ký nhận một hoặc nhiều event type và xử lý trong phạm vi module của mình. |
| Destination | Listener hoặc nhóm listener phù hợp với event và điều kiện nhận. |
| Dispatcher | Cơ chế của Spring tìm và gọi các listener đã đăng ký. |

Điểm quan trọng là publisher công bố một sự kiện có ý nghĩa nghiệp vụ; publisher không nên tự chọn implementation của module nhận bằng cách gọi trực tiếp service của module đó. Nếu publisher phải biết tên class listener, tên bean hoặc cách cập nhật database của module nhận, các module đã bị ghép nối chặt.

## 2. Spring tìm listener đích như thế nào?

Spring đăng ký các phương thức listener trong application context. Khi publisher gọi ApplicationEventPublisher.publishEvent, dispatcher tìm các listener có thể nhận kiểu event được phát. Listener khai báo nhận một kiểu cụ thể có thể nhận instance của kiểu đó và, theo quy tắc phân giải kiểu của Spring, các kiểu con tương thích.

Ví dụ, event **OrderConfirmed** có thể được nhận bởi listener khai báo tham số OrderConfirmed. Nếu một listener nhận kiểu event tổng quát hơn mà OrderConfirmed kế thừa hoặc triển khai, listener đó cũng có thể phù hợp. Do đó, việc chọn event type và quan hệ kế thừa ảnh hưởng trực tiếp đến phạm vi listener được gọi.

Một publisher đơn giản:

~~~java
public record OrderConfirmed(
    UUID orderId,
    Instant confirmedAt
) {}
~~~

~~~java
@Service
@RequiredArgsConstructor
class OrderService {

    private final ApplicationEventPublisher events;

    @Transactional
    public void confirm(UUID orderId) {
        // Cập nhật trạng thái đơn hàng trong transaction hiện tại.
        // orders.markConfirmed(orderId);

        events.publishEvent(
            new OrderConfirmed(orderId, Instant.now())
        );
    }
}
~~~

Lệnh publishEvent không nhận tham số destination. Spring sử dụng các listener đã đăng ký để xác định nơi giao event. Nếu không có listener phù hợp, event không tự động được đưa vào một hàng đợi bền vững; ứng dụng phải thiết kế cơ chế lưu và giao phù hợp với yêu cầu durability.

## 3. Một event có thể có nhiều destination

Một event thường mô tả điều đã xảy ra mà nhiều module có thể quan tâm. Ví dụ, khi đơn hàng được xác nhận, Inventory cần giữ hàng và Notification cần gửi thông báo. Hai listener độc lập có thể cùng đăng ký nhận OrderConfirmed:

~~~java
@Component
@RequiredArgsConstructor
class ReserveInventoryOnOrderConfirmed {

    private final InventoryService inventory;

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        inventory.reserveFor(event.orderId());
    }
}
~~~

~~~java
@Component
@RequiredArgsConstructor
class NotifyCustomerOnOrderConfirmed {

    private final NotificationService notifications;

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        notifications.sendOrderConfirmation(event.orderId());
    }
}
~~~

Luồng giao sự kiện:

~~~mermaid
flowchart TD
    O[OrderService] -->|publish OrderConfirmed| D[Spring event dispatcher]
    D --> I[Inventory listener]
    D --> N[Notification listener]
    I --> IR[Giữ hàng]
    N --> NR[Gửi thông báo]
~~~

Hai listener là hai destination độc lập. Việc Inventory hoàn tất không có nghĩa Notification đã hoàn tất; lỗi của một listener cũng không tự động hoàn tác tác động đã commit ở listener khác. Nếu nghiệp vụ yêu cầu chờ cả hai kết quả, cần một quy trình điều phối hoặc một mô hình trạng thái theo dõi các kết quả, thay vì giả định việc publish đồng nghĩa mọi listener đã hoàn thành.

## 4. Chọn event type để xác định destination

Event type là hợp đồng quan trọng nhất để Spring tìm listener. Hãy đặt tên theo sự thật nghiệp vụ đã xảy ra, chẳng hạn **OrderConfirmed**, **PaymentCaptured** hoặc **InventoryReserved**. Một event nên thể hiện một sự kiện rõ ràng, không nên gom nhiều ý nghĩa không liên quan vào một payload tổng quát rồi buộc từng listener tự diễn giải.

Khi các nhóm listener cần phản ứng với những sự thật khác nhau, hãy phát các event type riêng. Ví dụ:

| Sự thật nghiệp vụ | Event type gợi ý | Listener có thể quan tâm |
| --- | --- | --- |
| Đơn hàng được xác nhận | OrderConfirmed | Inventory, Notification, Analytics |
| Thanh toán được ghi nhận | PaymentCaptured | Order, Accounting, Notification |
| Đơn hàng bị hủy | OrderCancelled | Inventory, Payment, Notification |

Không nên dùng một event tên OrderChanged cho mọi thay đổi nếu listener cần phân biệt xác nhận, hủy và cập nhật địa chỉ giao hàng. Một event quá chung khiến các module phụ thuộc vào những field và quy tắc phân nhánh không thuộc trách nhiệm của chúng.

Event payload nên chứa dữ liệu ổn định và đủ để listener thực hiện công việc. Ưu tiên business identifier như orderId, paymentId hoặc reservationId; tránh đưa toàn bộ entity đang được quản lý bởi module publisher sang module nhận. Listener có thể dùng identifier để gọi API công khai của module sở hữu dữ liệu nếu cần thêm thông tin.

## 5. Lọc listener theo điều kiện nghiệp vụ

Có trường hợp nhiều listener nhận cùng event type nhưng chỉ xử lý khi một điều kiện phù hợp. Spring hỗ trợ điều kiện cho @EventListener, ví dụ:

~~~java
@Component
class PremiumOrderAuditListener {

    @EventListener(
        condition = "#event.priority() == T(com.example.Priority).HIGH"
    )
    void on(OrderSubmitted event) {
        // Ghi nhận audit cho đơn hàng ưu tiên cao.
    }
}
~~~

Điều kiện listener nên đơn giản, dễ đọc và dựa trên dữ liệu có sẵn trong event. Nếu điều kiện biểu diễn một nhánh nghiệp vụ quan trọng, thường rõ ràng hơn khi publisher phát event riêng như **HighPriorityOrderSubmitted**. Điều này làm hợp đồng sự kiện minh bạch và giúp kiểm thử destination dễ dàng.

Không dùng điều kiện listener để thay thế quyền kiểm tra nghiệp vụ. Ví dụ, listener Inventory vẫn phải xác minh reservation còn hợp lệ trước khi giữ hàng; việc event có field available=true không đảm bảo trạng thái kho chưa thay đổi kể từ lúc publisher tạo event.

## 6. Destination và ranh giới module

Trong Spring Modulith, listener nên nằm trong module sở hữu nghiệp vụ cần xử lý. Order công bố OrderConfirmed; Inventory cung cấp listener và service để giữ hàng; Notification cung cấp listener và service để gửi thông báo. Module Order không cần import service nội bộ của Inventory hoặc Notification.

Một cấu trúc trách nhiệm có thể hình dung như sau:

~~~mermaid
flowchart LR
    subgraph Order
        P[OrderService]
        E[OrderConfirmed event]
    end
    subgraph Inventory
        IL[Inventory event listener]
        IS[InventoryService]
    end
    subgraph Notification
        NL[Notification event listener]
        NS[NotificationService]
    end
    P --> E
    E -. event .-> IL
    E -. event .-> NL
    IL --> IS
    NL --> NS
~~~

Event type được dùng chung cần nằm ở package/API mà các module liên quan được phép phụ thuộc theo cấu trúc ứng dụng. Tránh để module nhận import implementation class hoặc repository của module phát. Nếu một event chỉ là chi tiết nội bộ của một module, giữ event và listener trong module đó; không biến mọi event nội bộ thành hợp đồng liên module.

Destination cũng không nên được xác định bằng cách để publisher dò tìm bean hoặc gọi ApplicationContext.getBean theo tên module. Cách đó biến định tuyến thành phụ thuộc runtime khó kiểm tra, khó quan sát và làm mờ ranh giới module. Hãy dùng cơ chế listener được khai báo rõ ràng và API sự kiện có chủ đích.

## 7. Thời điểm giao event và transaction

Destination phù hợp còn phụ thuộc thời điểm listener được gọi. @EventListener thông thường được gọi theo cơ chế dispatch của Spring trong luồng phát event. Nếu event được publish trong transaction, listener đồng bộ có thể chạy trước khi transaction commit. Nếu listener thực hiện side effect dựa trên dữ liệu đã commit, cần chọn transactional listener phù hợp.

Với @TransactionalEventListener, có thể khai báo phase, chẳng hạn TransactionPhase.AFTER_COMMIT, để listener chỉ xử lý sau khi transaction phát event commit. Nếu transaction rollback, listener ở phase AFTER_COMMIT không được gọi cho transaction đó.

Trong Spring Modulith, @ApplicationModuleListener là lựa chọn tiện dụng cho giao tiếp giữa các module. Annotation này kết hợp xử lý bất đồng bộ với transactional event listener ở phase AFTER_COMMIT và transaction riêng cho phần xử lý listener theo cấu hình của Spring Modulith. Vì listener có thể chạy bất đồng bộ, publisher không nên giả định listener đã hoàn tất khi publishEvent trả về.

| Cách khai báo | Thời điểm và đặc tính | Khi phù hợp |
| --- | --- | --- |
| @EventListener | Dispatch theo luồng xử lý event của Spring; không tự ràng buộc với commit. | Phản ứng đồng bộ không phụ thuộc transaction commit. |
| @TransactionalEventListener(AFTER_COMMIT) | Xử lý sau khi transaction phát event commit. | Listener cần dữ liệu nghiệp vụ đã commit. |
| @ApplicationModuleListener | Listener module bất đồng bộ, transactional và sau commit theo cấu hình Spring Modulith. | Giao tiếp giữa các module cần tách luồng xử lý. |

Không nên dựa vào thứ tự thực thi giữa nhiều listener bất đồng bộ. Nếu bước B chỉ được phép bắt đầu sau khi bước A thành công, hãy để A phát event kết quả và để B lắng nghe event đó, hoặc dùng một cơ chế điều phối có trạng thái. @Order không biến các listener bất đồng bộ độc lập thành một chuỗi nghiệp vụ có xác nhận hoàn tất.

## 8. Destination và Event Publication Registry

Khi một event có nhiều transactional listener, Spring Modulith Event Publication Registry theo dõi publication riêng cho từng listener. Registry ghi nhận việc giao đến các listener được theo dõi và đánh dấu publication hoàn tất khi listener xử lý thành công. Nếu một listener thất bại, publication tương ứng có thể còn incomplete để ứng dụng recovery hoặc resubmit theo cấu hình.

Điều này có nghĩa một event với hai destination có thể có hai publication record độc lập. Record của Inventory có thể completed trong khi record của Notification vẫn incomplete. Khi quan sát backlog, cần xem listener đích và tuổi của từng publication, không chỉ đếm tổng số event đã publish.

Registry hỗ trợ theo dõi độ tin cậy của việc giao event; nó không chọn destination thay cho Spring dispatcher và cũng không đảm bảo mọi side effect bên ngoài listener được thực hiện exactly-once. Listener vẫn cần idempotent để chịu được việc giao lại sau lỗi hoặc restart.

Để recovery có thể hoạt động sau khi tiến trình dừng, cần cấu hình persistent publication repository phù hợp với nền tảng lưu trữ và transaction manager. Store chỉ tồn tại trong bộ nhớ không giữ được publication chưa hoàn tất sau khi process mất. Chi tiết API và cấu hình repository phụ thuộc phiên bản Spring Modulith đang dùng.

## 9. Destination nội bộ và định tuyến ra hệ thống ngoài

Destination của application event nội bộ là listener trong application context. Việc định tuyến event sang broker, message topic hoặc hệ thống khác là một bước externalization riêng, có thêm hợp đồng tích hợp và cấu hình adapter.

Không nên nhầm việc có nhiều listener nội bộ với việc event đã được phát ra Kafka, AMQP hoặc một hệ thống bên ngoài. Một event có thể chỉ được xử lý trong ứng dụng. Nếu cần gửi ra ngoài, hãy xác định rõ destination tích hợp, định dạng payload, quy tắc versioning, bảo mật và cách retry ở biên externalization. Chỉ công bố những event có ý nghĩa như hợp đồng tích hợp; không phát tán mọi event nội bộ.

Nếu một event vừa có listener nội bộ vừa được externalize, hãy xác định riêng từng luồng giao và trách nhiệm vận hành. Event Publication Registry cho transactional listener nội bộ và cơ chế externalization có thể có trạng thái, adapter và chính sách retry khác nhau. Cần tránh hai nơi cùng chịu trách nhiệm retry một thông điệp mà không có quy tắc phối hợp.

## 10. Kiểm thử event destination

Kiểm thử destination cần chứng minh đúng listener được gọi, listener không liên quan không bị gọi và ranh giới transaction được tôn trọng. Có thể dùng unit test cho logic handler và integration test để kiểm tra event dispatch, transaction và publication registry trên cấu hình ứng dụng.

Các tình huống nên kiểm tra:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Event type cụ thể | Chỉ các listener có kiểu tương thích được gọi. |
| Nhiều listener phù hợp | Tất cả destination dự kiến đều nhận event. |
| Điều kiện listener | Listener chỉ xử lý khi điều kiện nghiệp vụ được thỏa mãn. |
| Event type không có listener | Không có side effect ngoài dự kiến; ứng dụng không giả định event được lưu bền vững. |
| Transaction commit | Listener AFTER_COMMIT được gọi sau khi transaction commit. |
| Transaction rollback | Listener AFTER_COMMIT không xử lý event của transaction rollback. |
| Listener bất đồng bộ | Publisher không giả định listener hoàn tất đồng bộ; test chờ kết quả bằng cơ chế đồng bộ hóa phù hợp. |
| Một listener thất bại | Publication của listener đó được theo dõi riêng và có thể recovery theo cấu hình. |
| Event được giao lại | Listener idempotent và không lặp side effect. |
| Ranh giới module | Module nhận chỉ phụ thuộc vào event contract/API được công khai. |

Trong test nhiều destination, hãy xác minh độc lập kết quả của từng listener. Không nên chỉ kiểm tra rằng publisher đã gọi publishEvent, vì điều đó chưa chứng minh listener nào đã nhận hoặc hoàn tất xử lý.

## 11. Quan sát và điều tra destination

Khi một event không tạo ra kết quả mong muốn, cần tìm được event type, event ID, listener dự kiến và trạng thái publication tương ứng. Log của publisher và listener nên dùng correlation ID hoặc business key chung để nối các bước. Với event có nhiều destination, thêm tên module hoặc listener ID vào log để xác định đích nào đã xử lý.

Các tín hiệu vận hành hữu ích gồm số publication incomplete theo listener, tuổi của publication lâu nhất, thời gian xử lý listener, tỷ lệ exception theo event type, số lần resubmit và độ trễ từ lúc publish đến lúc hoàn tất. Cảnh báo nên gắn với ngưỡng nghiệp vụ, ví dụ một listener giữ hàng có backlog lâu hơn thời gian cho phép.

Khi điều tra, hãy kiểm tra theo thứ tự: publisher có phát đúng event type không; listener có được đăng ký trong application context không; kiểu tham số có tương thích không; điều kiện listener có loại event ra không; transaction có commit không; listener có được gọi và ném exception không; publication registry ghi nhận trạng thái gì. Cách lần theo này giúp phân biệt lỗi định tuyến với lỗi xử lý nghiệp vụ.

Tránh ghi toàn bộ payload hoặc dữ liệu nhạy cảm vào log. Dùng event ID, business key, listener ID và thông tin lỗi đã được làm sạch để người vận hành tra cứu có kiểm soát.

## 12. Checklist thiết kế destination

- Event mô tả một sự thật nghiệp vụ rõ ràng và có tên ổn định.
- Publisher công bố event qua ApplicationEventPublisher, không tự tìm hoặc gọi implementation của module nhận.
- Destination được xác định bởi listener đăng ký với event type tương thích.
- Nhiều listener được xem là nhiều đích nhận độc lập; không giả định một listener thành công nghĩa là tất cả đã thành công.
- Listener nằm trong module sở hữu nghiệp vụ cần xử lý.
- Payload có định danh nghiệp vụ đủ dùng và không làm lộ entity nội bộ không cần thiết.
- Điều kiện listener đơn giản; nhánh nghiệp vụ quan trọng được biểu đạt bằng event type phù hợp.
- Listener cần dữ liệu đã commit dùng transactional listener phù hợp, thường là @ApplicationModuleListener hoặc @TransactionalEventListener.
- Không dựa vào thứ tự giữa các listener bất đồng bộ để điều phối quy trình.
- Event Publication Registry được cấu hình persistent store khi cần recovery sau restart.
- Externalization được thiết kế riêng với destination tích hợp và hợp đồng payload rõ ràng.
- Integration test xác minh từng destination, transaction, lỗi và retry; log có thể lần theo event đến listener.

Thiết kế destination rõ ràng giúp publisher chỉ công bố sự kiện nghiệp vụ, còn mỗi module tự đăng ký listener và xử lý phần việc thuộc trách nhiệm của mình. Kết hợp event type có ý nghĩa, ranh giới module, transaction phù hợp, publication registry và quan sát theo listener sẽ giúp định tuyến application events dễ hiểu và đáng tin cậy.
