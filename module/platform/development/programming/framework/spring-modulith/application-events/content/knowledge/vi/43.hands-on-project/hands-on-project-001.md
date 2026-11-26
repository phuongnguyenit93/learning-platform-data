# Chọn miền nghiệp vụ

*Xác định bài toán thực hành đủ thực tế để thể hiện giao tiếp giữa các module bằng Spring Modulith application events*

Một dự án thực hành về application events cần có nhiều phần nghiệp vụ độc lập, mỗi phần sở hữu dữ liệu và quy tắc riêng, nhưng vẫn phối hợp để hoàn thành một hành trình chung. Nếu chọn bài toán quá nhỏ, event chỉ trở thành cách gọi vòng vèo giữa vài class. Nếu chọn hệ thống quá lớn, người học dễ dành phần lớn thời gian cho đăng nhập, giao diện, thanh toán thật hoặc hạ tầng thay vì hiểu ranh giới module và vòng đời event.

Miền nghiệp vụ được chọn cho dự án này là **quy trình xử lý đơn hàng của một cửa hàng trực tuyến quy mô nhỏ**. Bài toán có các năng lực đặt hàng, giữ tồn kho, thanh toán, giao hàng, thông báo và báo cáo. Mỗi năng lực có thể trở thành một module Spring Modulith, phát ra sự kiện mô tả sự thật nghiệp vụ và phản ứng với sự kiện do module khác sở hữu.

## 1. Mục tiêu của việc chọn miền nghiệp vụ

Miền nghiệp vụ cần tạo ra đủ tình huống để thực hành:

- Xác định module nào sở hữu aggregate, dữ liệu và quy tắc nghiệp vụ.
- Phát application event sau khi thay đổi nghiệp vụ được commit.
- Xử lý event bằng listener ở module khác mà không truy cập repository của module nguồn.
- Phân biệt command yêu cầu hành động với event thông báo sự thật đã xảy ra.
- Chấp nhận eventual consistency ở những phần không cần cập nhật đồng bộ trong cùng transaction.
- Xử lý duplicate, retry, lỗi listener và publication chưa hoàn tất.
- Kiểm thử chuỗi event, trạng thái read model và ranh giới module.
- Quan sát lưu lượng, độ trễ, backlog và lỗi giao sự kiện.

Một miền phù hợp phải khiến các câu hỏi trên xuất hiện tự nhiên từ yêu cầu nghiệp vụ. Không nên thêm event chỉ để có thêm event hoặc tách module chỉ để tăng số lượng package.

## 2. Tiêu chí đánh giá ứng viên

Trước khi quyết định, đánh giá các miền ứng viên theo những tiêu chí sau:

| Tiêu chí | Câu hỏi cần trả lời | Dấu hiệu phù hợp |
|---|---|---|
| Nhiều năng lực nghiệp vụ | Có những phần nào sở hữu quy tắc và dữ liệu riêng? | Có ít nhất ba năng lực có ranh giới rõ |
| Sự kiện tự nhiên | Có những sự thật nào xảy ra và cần module khác biết? | Event có tên quá khứ, có ý nghĩa nghiệp vụ |
| Tính độc lập | Các phần có thể thay đổi hoặc triển khai theo nhịp khác nhau không? | Có thể xử lý bất đồng bộ ở một số bước |
| Tính nhất quán | Phần nào cần transaction ngay, phần nào chấp nhận trễ? | Có invariant rõ và read model eventual consistent |
| Khả năng kiểm thử | Có thể mô phỏng thành công, lỗi và retry không? | Có kịch bản xác định, dữ liệu test tái lập |
| Phạm vi thực hiện | Có thể hoàn thành một lát cắt nhỏ mà vẫn thể hiện event flow không? | Có MVP rõ, không cần dịch vụ bên ngoài thật |
| Giá trị học tập | Bài toán có bộc lộ coupling, duplicate và failure handling không? | Có nhiều consumer và một số nhánh lỗi thực tế |

Một miền có nhiều event chưa chắc đã phù hợp. Cần có lý do nghiệp vụ để các module phát và tiêu thụ event, đồng thời phải xác định được nơi nào cần giao dịch đồng bộ và nơi nào có thể xử lý sau commit.

## 3. So sánh một số miền ứng viên

| Miền nghiệp vụ | Ưu điểm cho thực hành | Hạn chế | Đánh giá |
|---|---|---|---|
| Danh sách việc cần làm | Dễ hiểu, nhanh dựng CRUD | Ít ranh giới nghiệp vụ; event thường chỉ là thông báo thay đổi đơn giản | Quá nhỏ cho dự án chính |
| Xử lý đơn hàng trực tuyến | Có đặt hàng, tồn kho, thanh toán, giao hàng, thông báo và báo cáo | Cần giới hạn phạm vi để tránh thành hệ thống thương mại điện tử đầy đủ | Phù hợp nhất |
| Chuyển tiền ngân hàng | Invariant và idempotency rõ; nhiều tình huống lỗi | Rủi ro học sai quy tắc tài chính; yêu cầu đối soát và bảo mật cao | Phù hợp cho bài chuyên sâu riêng |
| Đặt lịch khám | Có lịch, bệnh nhân, nhắc hẹn và thanh toán | Dữ liệu nhạy cảm và quy tắc lịch phức tạp | Có thể dùng nếu có miền chuyên môn rõ |
| Quản lý nội dung | Có soạn thảo, xuất bản, tìm kiếm và thông báo | Event flow thường ít ràng buộc xuyên module hơn | Phù hợp cho dự án nhỏ |

**Quyết định:** chọn xử lý đơn hàng trực tuyến. Miền này thể hiện rõ sự phối hợp giữa các module nhưng vẫn có thể xây dựng bằng dữ liệu giả lập, không cần cổng thanh toán hoặc hãng vận chuyển thật.

## 4. Bối cảnh nghiệp vụ được chọn

Một cửa hàng trực tuyến bán các sản phẩm có số lượng tồn kho hữu hạn. Khách hàng tạo đơn hàng gồm một hoặc nhiều dòng sản phẩm. Hệ thống kiểm tra thông tin đơn, giữ tồn kho, mô phỏng việc xác nhận thanh toán và tạo yêu cầu giao hàng. Khách hàng có thể theo dõi trạng thái đơn qua một read model.

Các vai trò chính:

- **Khách hàng:** tạo đơn, xem trạng thái và nhận thông báo.
- **Nhân viên vận hành:** xem đơn bị từ chối, lỗi hoặc cần xử lý thủ công.
- **Module nghiệp vụ:** sở hữu một phần quy tắc và dữ liệu.
- **Hệ thống ngoài giả lập:** đại diện cho cổng thanh toán hoặc dịch vụ giao hàng trong phạm vi học tập.

Hành trình chính:

1. Khách hàng gửi yêu cầu đặt đơn.
2. Module đơn hàng kiểm tra dữ liệu và tạo đơn ở trạng thái chờ giữ tồn kho.
3. Module tồn kho nhận sự kiện đơn được tạo và thử giữ số lượng.
4. Nếu giữ hàng thành công, quy trình yêu cầu module thanh toán xác nhận giao dịch.
5. Khi thanh toán được xác nhận, module giao hàng tạo lô giao.
6. Các module thông báo và báo cáo cập nhật dữ liệu riêng từ các sự kiện phù hợp.
7. Nếu một bước thất bại, quy trình phát sự kiện kết quả và thực hiện hành động bù trừ cần thiết.

## 5. Ranh giới module đề xuất

Không chia module theo bảng database hoặc theo tầng kỹ thuật như controller/service/repository. Chia theo năng lực nghiệp vụ và quyền sở hữu dữ liệu:

| Module | Trách nhiệm | Dữ liệu sở hữu | Ví dụ sự kiện phát ra |
|---|---|---|---|
| ordering | Tạo đơn, quản lý vòng đời và trạng thái đơn | Order, order line, order status | OrderPlaced, OrderCancelled, OrderCompleted |
| inventory | Quản lý số lượng và reservation | StockItem, InventoryReservation | InventoryReserved, InventoryReservationRejected, InventoryReleased |
| payments | Quản lý yêu cầu và kết quả thanh toán | Payment, payment status | PaymentAuthorized, PaymentRejected, PaymentRefunded |
| fulfillment | Chuẩn bị và theo dõi giao hàng | Shipment, shipment status | ShipmentCreated, ShipmentDispatched, ShipmentDelivered |
| notifications | Gửi thông báo theo các sự kiện đã đăng ký | Notification delivery/status | NotificationFailed nếu đó là sự thật cần module khác quan tâm |
| reporting | Xây dựng read model phục vụ tra cứu và thống kê | OrderSummary, SalesProjection | Thường tiêu thụ event; chỉ phát event khi có kết quả nghiệp vụ riêng |

Mỗi module sở hữu repository và mô hình nội bộ của mình. Module khác không truy cập repository hoặc bảng nội bộ để đọc dữ liệu. Khi cần phối hợp, module nguồn công bố event contract hoặc API module được phép sử dụng.

notifications và reporting là consumer điển hình: chúng phản ứng với sự kiện mà không trở thành chủ sở hữu dữ liệu đơn hàng, tồn kho hay thanh toán.

## 6. Phân biệt command và event trong quy trình

Command yêu cầu một module thực hiện hành động; event thông báo một sự thật đã xảy ra. Phân biệt hai khái niệm giúp tránh biến event bus thành một RPC bus khó kiểm soát.

| Nội dung | Loại | Ví dụ |
|---|---|---|
| Yêu cầu giữ 2 sản phẩm cho đơn hàng | Command | ReserveInventory |
| Tồn kho đã được giữ thành công | Event | InventoryReserved |
| Yêu cầu xác nhận thanh toán | Command | AuthorizePayment |
| Thanh toán đã được xác nhận | Event | PaymentAuthorized |
| Yêu cầu tạo lô giao | Command | CreateShipment |
| Lô giao đã được tạo | Event | ShipmentCreated |

Command có người nhận và kết quả xử lý cần được xác định. Event là dữ kiện bất biến mà các consumer quan tâm có thể xử lý độc lập. Có thể dùng API module để gửi command và dùng application event để công bố kết quả. Không đặt tên một yêu cầu như PaymentAuthorizationRequested rồi coi nó là event đã xảy ra nếu thực chất nó vẫn là lệnh phải thực thi.

## 7. Event contract cho lát cắt đầu tiên

Các event ban đầu nên nhỏ, bất biến và chứa dữ liệu đủ để consumer thực hiện công việc mà không cần đọc bảng nội bộ của module nguồn.

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
    UUID eventId,
    UUID orderId,
    UUID customerId,
    Instant occurredAt
) {}

public record InventoryReserved(
    UUID eventId,
    UUID orderId,
    UUID reservationId,
    Instant occurredAt
) {}

public record InventoryReservationRejected(
    UUID eventId,
    UUID orderId,
    String reasonCode,
    Instant occurredAt
) {}

public record PaymentAuthorized(
    UUID eventId,
    UUID orderId,
    UUID paymentId,
    Instant occurredAt
) {}
~~~

Các record chỉ là hợp đồng minh họa cho dự án. Trong code thực tế, đặt event contract ở package/API mà consumer được phép phụ thuộc theo cấu trúc module. Không đưa entity JPA, lazy relation, secret, thông tin thẻ hoặc toàn bộ aggregate vào payload.

eventId định danh một lần phát event và phải giữ nguyên khi retry/resubmit. orderId liên kết các sự kiện thuộc cùng quy trình. occurredAt là thời điểm sự thật nghiệp vụ xảy ra, không phải thời điểm consumer xử lý.

## 8. Luồng event chính

Một lát cắt có thể triển khai theo chuỗi sau:

~~~mermaid
sequenceDiagram
    participant API as API
    participant O as ordering
    participant I as inventory
    participant P as payments
    participant F as fulfillment
    participant N as notifications
    participant R as reporting

    API->>O: PlaceOrder
    O->>O: Commit Order
    O-->>I: OrderPlaced
    I->>I: Reserve stock
    I-->>O: InventoryReserved
    O->>P: AuthorizePayment
    P->>P: Commit Payment
    P-->>O: PaymentAuthorized
    O->>F: CreateShipment
    F->>F: Commit Shipment
    F-->>N: ShipmentCreated
    F-->>R: ShipmentCreated
    O-->>R: OrderCompleted
~~~

Sơ đồ mô tả quan hệ nghiệp vụ, không bắt buộc mọi lời gọi command đều đi qua event. ordering có thể điều phối các bước bằng application service/process manager: nhận event kết quả, cập nhật trạng thái đơn trong transaction và gọi API module đích cho command tiếp theo. Các module vẫn phát event riêng sau khi dữ liệu của chúng commit.

Không cần triển khai toàn bộ chuỗi ngay từ đầu. Hãy bắt đầu bằng OrderPlaced → InventoryReserved và một projection đơn giản, sau đó thêm thanh toán và giao hàng.

## 9. Quy tắc nghiệp vụ và invariant

Một miền thực hành cần quy tắc đủ cụ thể để test. Các invariant đề xuất:

- Đơn hàng phải có ít nhất một dòng sản phẩm và số lượng mỗi dòng lớn hơn 0.
- Một reservation không được giữ số lượng vượt quá tồn kho khả dụng.
- Cùng một orderId không được tạo reservation đang hoạt động trùng lặp.
- Chỉ đơn đã giữ được hàng mới được chuyển sang bước xác nhận thanh toán.
- Chỉ payment đã được xác nhận mới cho phép tạo shipment.
- Một shipment không được chuyển sang trạng thái đã giao trước khi được tạo và xuất kho.
- Event duplicate không được làm tăng số lượng giữ hàng hoặc tạo thêm payment/shipment.
- Event đến sai thứ tự phải được từ chối, trì hoãn hoặc xử lý theo version/state rule rõ ràng.

Invariant thuộc module sở hữu dữ liệu. Ví dụ, chỉ inventory quyết định có đủ hàng và tạo reservation; ordering không tự đọc bảng stock để kết luận. payments quyết định kết quả thanh toán; ordering chỉ phản ứng với PaymentAuthorized hoặc PaymentRejected.

## 10. Eventual consistency và trạng thái đơn hàng

Không phải mọi read model đều cập nhật ngay trong transaction đặt đơn. Sau khi OrderPlaced commit, projection có thể mất một khoảng ngắn để nhận event và hiển thị trạng thái mới. Giao diện hoặc API cần biểu diễn các trạng thái trung gian như:

- PENDING_INVENTORY
- PENDING_PAYMENT
- READY_FOR_FULFILLMENT
- SHIPPED
- COMPLETED
- CANCELLED
- REQUIRES_ATTENTION

Đây là trạng thái của quy trình đơn hàng, không nhất thiết là enum dùng chung cho mọi module. Inventory, payment và fulfillment có state machine riêng. Không ép các module dùng chung một bảng trạng thái tổng hợp vì điều đó làm mờ quyền sở hữu.

Read model trong reporting có thể cập nhật sau khi nhận event. Người dùng cần biết trạng thái là cuối cùng hay đang chờ; API có thể trả 202 Accepted cho quy trình bất đồng bộ và cung cấp endpoint tra cứu theo orderId.

## 11. Xử lý nhánh thất bại và hành động bù trừ

Luồng nghiệp vụ không chỉ có đường thành công. Ví dụ:

| Tình huống | Sự kiện/kết quả | Hành động tiếp theo |
|---|---|---|
| Không đủ tồn kho | InventoryReservationRejected | Đơn bị từ chối hoặc hủy |
| Thanh toán bị từ chối | PaymentRejected | Yêu cầu inventory giải phóng reservation |
| Tạo shipment thất bại tạm thời | Publication/listener chưa hoàn tất | Retry có giới hạn và quan sát |
| Khách hủy trước khi thanh toán | OrderCancelled | Giải phóng reservation nếu đang giữ |
| Notification provider lỗi | NotificationFailed hoặc trạng thái delivery lỗi | Retry thông báo độc lập, không rollback đơn hàng |

Hành động bù trừ là một nghiệp vụ mới, ví dụ ReleaseInventory, không phải xóa lịch sử event cũ. Khi payment đã được capture, việc hoàn tiền cần một quy trình riêng và có event như PaymentRefunded.

Không để lỗi gửi email làm transaction đặt hàng thất bại nếu email không phải điều kiện bắt buộc để chấp nhận đơn. Mức độ quan trọng của từng consumer cần được xác định bởi nghiệp vụ.

## 12. Phạm vi MVP và phần để sau

Để dự án có thể hoàn thành theo từng bước, chia phạm vi thành các lát cắt:

**MVP**

- Tạo đơn hàng và phát OrderPlaced.
- Inventory nhận event, giữ hàng hoặc phát InventoryReservationRejected.
- Ordering cập nhật trạng thái theo kết quả inventory.
- Reporting tạo projection trạng thái đơn.
- Dùng @ApplicationModuleListener cho listener phù hợp và kiểm tra xử lý sau commit.
- Kiểm thử duplicate, listener failure và publication chưa hoàn tất.

**Mở rộng**

- Thêm payment giả lập và shipment.
- Thêm notification consumer.
- Externalize một event đến broker để kiểm thử adapter.
- Bổ sung retry có giới hạn, DLQ/quarantine và resubmission.
- Bổ sung event versioning, idempotency inbox và observability.
- Dựng projection generation mới và replay dữ liệu thử nghiệm.

**Ngoài phạm vi ban đầu**

- Cổng thanh toán thật hoặc lưu dữ liệu thẻ.
- Tích hợp hãng vận chuyển thật.
- Thuế, hóa đơn điện tử và kế toán đầy đủ.
- Multi-warehouse, pricing engine và promotion engine phức tạp.
- Hệ thống phân quyền doanh nghiệp hoặc giao diện thương mại hoàn chỉnh.

Giới hạn này giữ trọng tâm ở application events và ranh giới module. Có thể dùng adapter giả lập cho payment/shipping để kiểm thử các kết quả mà không phụ thuộc dịch vụ bên ngoài.

## 13. Cấu trúc module trong Spring Modulith

Một cấu trúc package khái niệm:

~~~text
com.example.shop
├── ordering
│   ├── Order.java
│   ├── OrderRepository.java
│   ├── PlaceOrder.java
│   ├── OrderEventListener.java
│   └── events
├── inventory
│   ├── StockItem.java
│   ├── InventoryReservation.java
│   ├── InventoryService.java
│   └── events
├── payments
│   ├── Payment.java
│   ├── PaymentService.java
│   └── events
├── fulfillment
│   ├── Shipment.java
│   ├── FulfillmentService.java
│   └── events
├── notifications
│   └── NotificationListener.java
└── reporting
    ├── OrderSummary.java
    └── OrderProjectionListener.java
~~~

Tên package và cách đặt event contract có thể thay đổi theo quy ước dự án. Nguyên tắc là API/event contract được công bố có chủ đích; implementation và repository nội bộ vẫn thuộc module sở hữu.

Có thể dùng ApplicationEventPublisher để phát event trong use case và @ApplicationModuleListener để xử lý bất đồng bộ sau commit:

~~~java
@Service
class PlaceOrder {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    @Transactional
    OrderId handle(PlaceOrderCommand command) {
        Order order = Order.place(command);
        orders.save(order);
        events.publishEvent(order.toOrderPlacedEvent());
        return order.getId();
    }
}
~~~

Ví dụ chỉ thể hiện ý tưởng. Event phải được ghi nhận trong đúng transaction publisher; listener được cấu hình theo semantics mong muốn. Không publish event từ code chạy ngoài transaction rồi giả định registry có thể khôi phục một thay đổi nghiệp vụ chưa được commit.

## 14. Ranh giới dữ liệu và quyền sở hữu

Mỗi module là nguồn sự thật cho dữ liệu của mình:

- ordering không cập nhật trực tiếp tồn kho.
- inventory không sửa trạng thái đơn hàng.
- payments không truy cập repository đơn hàng để quyết định trạng thái thanh toán.
- fulfillment không đọc bảng payment nội bộ.
- reporting chỉ duy trì projection phục vụ truy vấn, không trở thành nguồn sự thật thay thế.
- notifications không quyết định đơn hàng thành công chỉ vì gửi được email.

Nếu một module cần dữ liệu từ module khác, dùng event contract hoặc API công khai phù hợp. Tránh chia sẻ entity hoặc repository vì điều đó tạo coupling thời gian chạy và làm thay đổi schema nội bộ có thể phá module consumer.

## 15. Dữ liệu và tính riêng tư

Dự án học tập nên dùng dữ liệu giả lập. Event chỉ mang thông tin cần cho consumer:

- ID khách hàng và đơn hàng thay vì thông tin định danh đầy đủ.
- Mã sản phẩm, số lượng và giá trị cần thiết theo hợp đồng.
- Không đưa mật khẩu, token, số thẻ hoặc thông tin xác thực vào event.
- Hạn chế địa chỉ giao hàng và thông tin cá nhân trong event dùng cho reporting.
- Log event ID, event type và correlation ID; không log toàn bộ payload.

Khi thêm externalization, xác định rõ consumer nào được phép nhận từng trường. Message broker và publication registry cũng là nơi lưu dữ liệu cần được kiểm soát quyền truy cập và retention.

## 16. Kịch bản nghiệm thu miền nghiệp vụ

Trước khi chuyển sang thiết kế chi tiết, xác nhận miền đã chọn đáp ứng được các kịch bản:

1. Đơn hợp lệ được tạo và phát đúng một OrderPlaced sau commit.
2. Inventory giữ được hàng và phát InventoryReserved.
3. Inventory không đủ hàng thì phát kết quả từ chối và đơn không chuyển sang thanh toán.
4. Listener reporting cập nhật read model sau khi nhận event.
5. Listener lỗi không làm mất publication và có thể phục hồi theo chính sách.
6. Giao lại cùng event không tạo reservation hoặc projection duplicate.
7. Event đến sai thứ tự không làm aggregate chuyển trạng thái bất hợp lệ.
8. Một consumer lỗi không ngăn consumer độc lập khác xử lý event của nó.
9. Có thể quan sát số event, listener failure, backlog và thời gian xử lý.
10. Có thể kiểm thử luồng bằng Spring Modulith test support mà không cần dịch vụ thanh toán/giao hàng thật.

Nếu các kịch bản này chưa thể mô tả bằng dữ liệu và kết quả kiểm tra cụ thể, cần làm rõ miền nghiệp vụ trước khi viết code.

## 17. Kế hoạch triển khai dự án

Một thứ tự triển khai hợp lý:

1. Viết glossary và quy tắc nghiệp vụ của đơn hàng, tồn kho và thanh toán giả lập.
2. Xác định aggregate, trạng thái và invariant do từng module sở hữu.
3. Tạo các module ordering, inventory và reporting với API rõ ràng.
4. Phát OrderPlaced trong transaction của use case đặt đơn.
5. Xử lý event bằng listener và phát kết quả inventory.
6. Cập nhật trạng thái đơn qua event kết quả, không truy cập repository inventory.
7. Xây dựng projection trong reporting và kiểm thử eventual consistency.
8. Bổ sung inbox/idempotency, retry và kiểm thử lỗi.
9. Thêm payment/fulfillment giả lập và hành động bù trừ.
10. Bổ sung externalization, broker integration, metric, alert và runbook khi lát cắt nội bộ đã ổn định.

Mỗi bước nên có test chứng minh hợp đồng module và hành vi event trước khi mở rộng sang bước tiếp theo.

## 18. Những điểm cần nhớ

- Chọn quy trình xử lý đơn hàng trực tuyến vì có nhiều năng lực nghiệp vụ độc lập và event phát sinh tự nhiên.
- Chia module theo quyền sở hữu dữ liệu và quy tắc nghiệp vụ, không chia theo bảng hoặc tầng kỹ thuật.
- Dùng event để thông báo sự thật đã xảy ra; dùng command/API module để yêu cầu hành động.
- Bắt đầu với lát cắt OrderPlaced → inventory reservation → projection, sau đó mở rộng payment và fulfillment.
- Xác định invariant, trạng thái trung gian, eventual consistency và hành động bù trừ trước khi viết listener.
- Event contract cần ID ổn định, payload tối thiểu và không phụ thuộc entity nội bộ.
- Thiết kế test cho thành công, thất bại, duplicate, sai thứ tự và publication chưa hoàn tất.
- Giữ payment/shipping ở dạng giả lập trong MVP để trọng tâm vẫn là Spring Modulith application events.

Miền xử lý đơn hàng cung cấp một bài toán đủ thực tế để thực hành giao tiếp giữa các module mà vẫn có thể giới hạn thành các lát cắt nhỏ. Khi ranh giới nghiệp vụ, event contract và invariant được xác định trước, các phần tiếp theo của dự án có thể tập trung vào publisher, listener, transaction, registry, retry, kiểm thử và quan sát một cách nhất quán.
