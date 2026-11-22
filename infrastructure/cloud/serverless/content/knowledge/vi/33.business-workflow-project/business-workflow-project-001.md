# Mô hình hóa quy trình đặt hàng bằng state machine

Bài học thuộc chương **Dự án workflow nghiệp vụ** trong module **CLOUD_SERVERLESS**, tập trung vào cách xây dựng và vận hành workflow đặt hàng bằng state machine trên nền tảng serverless.

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Chuyển quy trình đặt hàng từ một chuỗi xử lý khó kiểm soát thành mô hình trạng thái và sự kiện có quy tắc rõ ràng.
- Xác định trạng thái, sự kiện, điều kiện chuyển trạng thái, hành động và trạng thái kết thúc của một đơn hàng.
- Thiết kế luồng bất đồng bộ cho thanh toán, giữ hàng, xác nhận đơn và giao hàng.
- Xử lý retry, sự kiện trùng, sự kiện đến sai thứ tự, timeout và thao tác bù khi một bước thất bại.
- Chọn cách triển khai bằng workflow engine hoặc bằng các Java function kích hoạt bởi HTTP, message và event.
- Đánh giá quyền truy cập, khả năng mở rộng, cold start, khả năng quan sát và chi phí của giải pháp serverless.

## 1. Vì sao quy trình đặt hàng cần state machine?

Một yêu cầu tạo đơn hàng có thể bắt đầu bằng một HTTP request, nhưng nghiệp vụ không kết thúc khi server trả về phản hồi. Hệ thống còn phải xác thực đơn, xin cấp phép thanh toán, giữ tồn kho, thu tiền, tạo vận đơn và nhận xác nhận giao hàng. Mỗi bước có thể chạy ở một dịch vụ khác nhau và hoàn thành sau vài mili giây, vài phút hoặc lâu hơn.

Nếu viết toàn bộ quy trình trong một hàm đồng bộ, hàm đó phải chờ nhiều dịch vụ bên ngoài. Khi một dịch vụ chậm hoặc lỗi, toàn bộ request có thể timeout dù một số tác vụ đã thành công. Nếu chia thành nhiều hàm mà không có mô hình trạng thái chung, hệ thống dễ xử lý một sự kiện hai lần, bỏ sót bước tiếp theo hoặc cho phép những chuyển đổi nghiệp vụ không hợp lệ.

State machine (máy trạng thái) mô tả một đối tượng nghiệp vụ thông qua:

- **Trạng thái (state):** tình trạng hiện tại của đối tượng, ví dụ **PAYMENT_PENDING** hoặc **SHIPPED**.
- **Sự kiện (event):** điều đã xảy ra hoặc tín hiệu yêu cầu xử lý, ví dụ **PaymentAuthorized** hay **CancelRequested**.
- **Chuyển trạng thái (transition):** quy tắc xác định trạng thái tiếp theo khi một sự kiện đến.
- **Điều kiện (guard):** điều kiện phải đúng trước khi cho phép chuyển trạng thái, ví dụ số tiền thanh toán phải bằng tổng tiền đơn.
- **Hành động (action):** công việc phát sinh từ chuyển trạng thái, ví dụ gọi dịch vụ giữ hàng hoặc phát sự kiện **OrderConfirmed**.
- **Ngữ cảnh (context):** dữ liệu cần để xử lý workflow, ví dụ mã thanh toán, mã giữ hàng, hạn thanh toán và phiên bản đơn hàng.

Có thể biểu diễn quy tắc tổng quát như sau:

**trạng thái hiện tại + sự kiện + điều kiện -> trạng thái mới + hành động**

State machine giúp trả lời các câu hỏi quan trọng: đơn hàng đang ở bước nào, sự kiện nào được phép tiếp theo, bước nào cần thử lại và phải làm gì nếu không thể hoàn tất quy trình.

### Phân biệt lệnh và sự kiện

Lệnh (command) diễn tả điều một thành phần muốn hệ thống thực hiện. Ví dụ **AuthorizePayment** yêu cầu dịch vụ thanh toán cấp phép một khoản tiền. Sự kiện (event) ghi nhận điều đã xảy ra. Ví dụ **PaymentAuthorized** thông báo nhà cung cấp đã cấp phép thành công.

Phân biệt hai khái niệm này giúp tránh cập nhật trạng thái dựa trên một yêu cầu chưa được xác nhận. Việc gửi lệnh giữ hàng không có nghĩa hàng đã được giữ; chỉ khi nhận kết quả **InventoryReserved** thì workflow mới được chuyển sang bước tương ứng.

Một sự kiện nên có định danh duy nhất, loại sự kiện, mã đối tượng nghiệp vụ, thời điểm phát sinh và thông tin tương quan. Payload chỉ nên chứa dữ liệu cần thiết để xử lý, không nên mang theo dữ liệu nhạy cảm không liên quan.

## 2. Xác định phạm vi và trạng thái của đơn hàng

Trước khi viết code, hãy xác định ranh giới nghiệp vụ. Bài học này mô hình hóa vòng đời của một đơn hàng từ lúc khách gửi yêu cầu đến khi giao hàng thành công hoặc đơn bị hủy. Thanh toán, tồn kho và giao vận là các hệ thống cộng tác; mỗi hệ thống vẫn có trạng thái riêng của nó.

Không nên gộp mọi trạng thái của mọi dịch vụ vào một enum khổng lồ. Đơn hàng có trạng thái vòng đời riêng; giao dịch thanh toán có thể có trạng thái **AUTHORIZED**, **CAPTURED**, **VOIDED** hoặc **REFUNDED**; giữ hàng có thể có trạng thái **RESERVED**, **RELEASED** hoặc **EXPIRED**. Workflow của đơn hàng điều phối các hệ thống đó và lưu các mã tham chiếu cần thiết.

Một mô hình tham khảo:

| Trạng thái | Ý nghĩa | Bước tiếp theo thường gặp |
|---|---|---|
| **CREATED** | Đơn đã được ghi nhận, chưa bắt đầu xử lý thanh toán | Xin cấp phép thanh toán |
| **PAYMENT_AUTHORIZATION_PENDING** | Đang chờ kết quả cấp phép thanh toán | Giữ hàng, báo thanh toán thất bại hoặc đối soát |
| **PAYMENT_RECONCILIATION_PENDING** | Kết quả thanh toán chưa rõ do timeout hoặc mất phản hồi | Hỏi lại nhà cung cấp bằng mã giao dịch ổn định |
| **INVENTORY_RESERVATION_PENDING** | Đang chờ hệ thống tồn kho giữ hàng | Thu tiền hoặc bắt đầu bù trừ |
| **PAYMENT_CAPTURE_PENDING** | Hàng đã được giữ và đang chờ thu tiền | Xác nhận đơn hoặc bù trừ |
| **CONFIRMED** | Thanh toán đã thu và đơn được xác nhận | Bắt đầu thực hiện đơn |
| **FULFILLMENT_PENDING** | Đang chuẩn bị giao hàng | Tạo vận đơn |
| **SHIPPED** | Đơn đã được bàn giao cho đơn vị vận chuyển | Chờ xác nhận giao |
| **DELIVERED** | Đơn đã giao thành công | Kết thúc |
| **PAYMENT_FAILED** | Thanh toán bị từ chối | Kết thúc hoặc cho khách tạo yêu cầu mới |
| **EXPIRED** | Hết hạn và đã xác minh không có khoản thanh toán đang treo | Kết thúc |
| **COMPENSATION_PENDING** | Đang thực hiện các thao tác hoàn tác cho bước đã thành công | Hủy đơn hoặc chuyển xử lý thủ công |
| **CANCELLATION_PENDING** | Đang xử lý yêu cầu hủy một đơn đã xác nhận | Hủy sau khi hoàn tiền và giải phóng hàng |
| **CANCELLED** | Đơn đã hủy và các thao tác cần thiết đã hoàn tất | Kết thúc |
| **MANUAL_REVIEW** | Không thể tự động khôi phục an toàn | Nhân viên vận hành kiểm tra |

Các trạng thái kết thúc điển hình là **DELIVERED**, **PAYMENT_FAILED**, **EXPIRED** và **CANCELLED**. **MANUAL_REVIEW** là trạng thái cần can thiệp; không nên coi nó là thành công.

### Quy tắc chuyển trạng thái

Bảng dưới đây mô tả luồng chính. Tên sự kiện là tên nghiệp vụ minh họa; dự án thực tế cần thống nhất schema và cách đặt tên giữa các dịch vụ.

| Trạng thái hiện tại | Sự kiện | Trạng thái tiếp theo | Hành động hoặc điều kiện |
|---|---|---|---|
| **CREATED** | **SubmitOrder** | **PAYMENT_AUTHORIZATION_PENDING** | Kiểm tra đơn và gửi lệnh cấp phép thanh toán |
| **PAYMENT_AUTHORIZATION_PENDING** | **PaymentAuthorized** | **INVENTORY_RESERVATION_PENDING** | Xác minh mã giao dịch, số tiền và tiền tệ; yêu cầu giữ hàng |
| **PAYMENT_AUTHORIZATION_PENDING** | **PaymentDeclined** | **PAYMENT_FAILED** | Ghi nhận lý do từ chối có thể hiển thị an toàn |
| **PAYMENT_AUTHORIZATION_PENDING** | **PaymentResultUnknown** | **PAYMENT_RECONCILIATION_PENDING** | Đối soát với nhà cung cấp, không tự kết luận giao dịch thất bại |
| **INVENTORY_RESERVATION_PENDING** | **InventoryReserved** | **PAYMENT_CAPTURE_PENDING** | Lưu mã giữ hàng và yêu cầu thu tiền |
| **INVENTORY_RESERVATION_PENDING** | **InventoryRejected** | **COMPENSATION_PENDING** | Hủy cấp phép thanh toán đã tạo |
| **PAYMENT_CAPTURE_PENDING** | **PaymentCaptured** | **CONFIRMED** | Ghi nhận khoản tiền đã thu và phát **OrderConfirmed** |
| **PAYMENT_CAPTURE_PENDING** | **PaymentCaptureFailed** | **COMPENSATION_PENDING** | Giải phóng hàng và hủy cấp phép nếu còn hiệu lực |
| **PAYMENT_CAPTURE_PENDING** | **PaymentResultUnknown** | **PAYMENT_RECONCILIATION_PENDING** | Đối soát để biết khoản tiền đã được thu hay chưa |
| **CONFIRMED** | **StartFulfillment** | **FULFILLMENT_PENDING** | Gửi yêu cầu chuẩn bị giao hàng |
| **FULFILLMENT_PENDING** | **ShipmentCreated** | **SHIPPED** | Lưu mã vận đơn và thông tin theo dõi |
| **SHIPPED** | **DeliveryConfirmed** | **DELIVERED** | Ghi nhận hoàn tất giao hàng |
| **CONFIRMED** | **CancelRequested** | **CANCELLATION_PENDING** | Kiểm tra điều kiện hủy; lập kế hoạch hoàn tiền và giải phóng hàng |
| **COMPENSATION_PENDING** hoặc **CANCELLATION_PENDING** | **AllCompensationsSucceeded** | **CANCELLED** | Chỉ hủy sau khi mọi thao tác bù bắt buộc hoàn tất |
| **COMPENSATION_PENDING** hoặc **CANCELLATION_PENDING** | **CompensationFailed** | **MANUAL_REVIEW** | Lưu lỗi và tạo cảnh báo vận hành |

Kết quả đối soát thanh toán phụ thuộc vào thao tác đang chờ trong context. Nếu thao tác cấp phép đã thành công, workflow tiếp tục sang giữ hàng. Nếu thao tác thu tiền đã thành công, workflow có thể xác nhận đơn. Nếu nhà cung cấp xác nhận thao tác thất bại, workflow tiếp tục theo nhánh thất bại tương ứng. Nếu trạng thái vẫn chưa rõ, hệ thống tiếp tục đối soát có giới hạn hoặc chuyển xử lý thủ công.

Không cho phép chuyển trực tiếp từ **PAYMENT_FAILED** sang **SHIPPED**, hoặc từ **DELIVERED** về **CONFIRMED**. Nếu khách muốn mua lại, hãy tạo đơn mới với định danh mới. Nếu khách yêu cầu trả hàng sau khi đã giao, hãy mô hình hóa quy trình trả hàng riêng thay vì mở lại vòng đời đơn cũ.

### Sơ đồ luồng

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> PAYMENT_AUTHORIZATION_PENDING: SubmitOrder
    PAYMENT_AUTHORIZATION_PENDING --> INVENTORY_RESERVATION_PENDING: PaymentAuthorized
    PAYMENT_AUTHORIZATION_PENDING --> PAYMENT_FAILED: PaymentDeclined
    PAYMENT_AUTHORIZATION_PENDING --> PAYMENT_RECONCILIATION_PENDING: ResultUnknown
    PAYMENT_RECONCILIATION_PENDING --> INVENTORY_RESERVATION_PENDING: ProviderConfirmsAuthorized
    PAYMENT_RECONCILIATION_PENDING --> PAYMENT_FAILED: ProviderConfirmsDeclined
    PAYMENT_RECONCILIATION_PENDING --> EXPIRED: NoAuthorizationAndDeadlinePassed
    INVENTORY_RESERVATION_PENDING --> PAYMENT_CAPTURE_PENDING: InventoryReserved
    INVENTORY_RESERVATION_PENDING --> COMPENSATION_PENDING: InventoryRejected
    PAYMENT_CAPTURE_PENDING --> CONFIRMED: PaymentCaptured
    PAYMENT_CAPTURE_PENDING --> COMPENSATION_PENDING: PaymentCaptureFailed
    PAYMENT_CAPTURE_PENDING --> PAYMENT_RECONCILIATION_PENDING: CaptureResultUnknown
    COMPENSATION_PENDING --> CANCELLED: AllCompensationsSucceeded
    COMPENSATION_PENDING --> MANUAL_REVIEW: CompensationFailed
    CONFIRMED --> CANCELLATION_PENDING: CancelRequested
    CANCELLATION_PENDING --> CANCELLED: RefundAndReleaseSucceeded
    CANCELLATION_PENDING --> MANUAL_REVIEW: CompensationFailed
    CONFIRMED --> FULFILLMENT_PENDING: StartFulfillment
    FULFILLMENT_PENDING --> SHIPPED: ShipmentCreated
    SHIPPED --> DELIVERED: DeliveryConfirmed
    PAYMENT_FAILED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
    DELIVERED --> [*]
~~~

Sơ đồ chỉ thể hiện trạng thái vòng đời chính. Các thao tác bù, số lần thử lại, thời hạn chờ và chi tiết đối soát cần được lưu trong context hoặc lịch sử workflow.

## 3. Thiết kế sự kiện và dữ liệu workflow

Một sự kiện thanh toán thành công có thể có cấu trúc như sau:

~~~json
{
  "eventId": "evt-8d21",
  "eventType": "PaymentAuthorized",
  "orderId": "ord-1042",
  "occurredAt": "2026-11-17T10:15:30Z",
  "correlationId": "req-71ac",
  "causationId": "cmd-2f90",
  "aggregateVersion": 2,
  "payload": {
    "paymentAuthorizationId": "pay-auth-552",
    "amount": "1290000",
    "currency": "VND"
  }
}
~~~

Các trường có vai trò khác nhau:

- **eventId** nhận diện duy nhất sự kiện, dùng để phát hiện giao nhận trùng.
- **orderId** xác định đơn cần cập nhật.
- **correlationId** nối các log và trace thuộc cùng một yêu cầu nghiệp vụ.
- **causationId** cho biết sự kiện được tạo ra từ lệnh hoặc sự kiện nào.
- **aggregateVersion** cho biết phiên bản đơn hàng mà sự kiện liên quan đến.
- **occurredAt** là thời điểm sự kiện xảy ra ở nguồn phát.
- **payload** chứa dữ liệu nghiệp vụ tối thiểu để xác minh và xử lý.

Không tin mọi dữ liệu trong sự kiện chỉ vì nó đến từ message broker. Consumer cần xác thực nguồn phát, kiểm tra schema, đối chiếu **orderId**, mã thanh toán, số tiền và tiền tệ với dữ liệu đơn hàng đã lưu. Với webhook từ nhà cung cấp, cần kiểm tra chữ ký theo cơ chế của nhà cung cấp.

### Dữ liệu cần lưu

Một thiết kế cơ bản có thể dùng ba nhóm dữ liệu:

| Nhóm dữ liệu | Trường tiêu biểu | Mục đích |
|---|---|---|
| **orders** | **order_id**, **customer_id**, **status**, **version**, **total_amount**, **currency**, **created_at**, **updated_at** | Lưu trạng thái hiện tại và thông tin cốt lõi của đơn |
| **order_events** | **event_id**, **order_id**, **event_type**, **payload_ref**, **occurred_at**, **processed_at** | Lưu dấu vết sự kiện phục vụ kiểm tra và đối soát |
| **outbox** | **event_id**, **aggregate_id**, **event_type**, **payload**, **created_at**, **published_at** | Đảm bảo sự kiện cần phát được ghi nhận cùng transaction cập nhật đơn |

Có thể lưu thêm **payment_id**, **payment_authorization_id**, **inventory_reservation_id**, **shipment_id**, **workflow_id**, **deadline_at** và **pending_operation** tùy yêu cầu. Hạn chế lưu dữ liệu thẻ thanh toán hoặc thông tin cá nhân không cần thiết trong event log.

Trạng thái hiện tại giúp truy vấn nhanh. Lịch sử sự kiện giúp giải thích vì sao đơn đến trạng thái đó. Hai loại dữ liệu phục vụ mục đích khác nhau. Không nhất thiết phải áp dụng event sourcing đầy đủ chỉ vì hệ thống có event log.

## 4. Tổ chức workflow trong kiến trúc serverless

Trong kiến trúc serverless, mỗi Java function thường đảm nhiệm một bước xử lý ngắn. Function nhận trigger, xác thực dữ liệu, đọc trạng thái cần thiết, áp dụng quy tắc và ghi kết quả vào kho dữ liệu bền vững. Function có thể kết thúc sau khi phát lệnh hoặc sự kiện tiếp theo; tiến trình nghiệp vụ vẫn tiếp tục nhờ message broker, event bus hoặc workflow engine.

Một kiến trúc tham khảo:

~~~mermaid
flowchart TD
    Client[Ứng dụng khách hàng] --> API[HTTP API]
    API --> Create[Java function: CreateOrder]
    Create --> DB[(Order database)]
    Create --> Outbox[(Transactional outbox)]
    Outbox --> Publisher[Outbox publisher]
    Publisher --> Bus[Queue hoặc event bus]
    Bus --> Orchestrator[Workflow engine hoặc event handlers]
    Orchestrator --> Payment[Java function: Payment]
    Orchestrator --> Inventory[Java function: Inventory]
    Orchestrator --> Fulfillment[Java function: Fulfillment]
    Payment --> Provider[Payment provider]
    Inventory --> Stock[Inventory service]
    Fulfillment --> Shipping[Shipping provider]
    Payment --> Bus
    Inventory --> Bus
    Fulfillment --> Bus
    Orchestrator --> DB
~~~

Các trigger thường gặp:

| Trigger | Vai trò trong quy trình |
|---|---|
| **HTTP** | Nhận yêu cầu tạo đơn, truy vấn trạng thái hoặc yêu cầu hủy |
| **Message queue** | Xử lý công việc nền và kết quả từ dịch vụ khác |
| **Event bus** | Phản ứng với **PaymentAuthorized**, **InventoryReserved**, **ShipmentCreated** và các sự kiện nghiệp vụ |
| **Scheduler hoặc timer bền vững** | Kích hoạt xử lý khi đơn đến hạn thanh toán hoặc một bước vượt quá thời gian chờ |
| **Workflow engine** | Điều phối nhánh, timeout, retry, chờ kết quả và thao tác bù qua nhiều function |

### Hai cách triển khai state machine

**Dùng workflow engine có trạng thái bền vững.** Một dịch vụ điều phối quản lý execution, bước hiện tại, kết quả, timeout, retry và lịch sử. Mỗi bước gọi Java function hoặc tích hợp với một dịch vụ. Cách này phù hợp với workflow kéo dài, có nhiều nhánh và cần chờ sự kiện. Cần hiểu giới hạn về thời lượng execution, số transition, kích thước input/output, cách engine xử lý retry và chi phí theo lần chuyển trạng thái.

**Tự quản lý state machine trong ứng dụng.** Mỗi event handler đọc trạng thái trong database, kiểm tra transition, cập nhật phiên bản và phát event tiếp theo. Cách này linh hoạt, dễ gắn với mô hình dữ liệu hiện có, nhưng nhóm phát triển phải tự xây dựng cơ chế khóa hoặc optimistic concurrency, retry, timeout, lịch sử, dead-letter queue, đối soát và công cụ vận hành.

Có thể kết hợp hai cách: workflow engine điều phối các bước dài hạn, còn database nghiệp vụ vẫn là nguồn dữ liệu chính của đơn hàng. Cần xác định rõ hệ thống nào là nguồn sự thật cho từng trường. Nếu trạng thái trong engine và trạng thái trong database lệch nhau, phải có quy trình đối soát và sửa sai.

## 5. Hiện thực hóa quy tắc chuyển trạng thái bằng Java

Nên tách logic quyết định trạng thái khỏi phần gọi dịch vụ bên ngoài. Hàm quyết định transition có thể thuần, dễ kiểm thử và không thực hiện I/O. Phần điều phối sẽ thực hiện hành động sau khi đã kiểm tra transition và ghi nhận thay đổi một cách an toàn.

Ví dụ dưới đây minh họa bảng transition tối thiểu bằng Java 17:

~~~java
import java.util.Map;

enum OrderState {
    CREATED,
    PAYMENT_AUTHORIZATION_PENDING,
    INVENTORY_RESERVATION_PENDING,
    PAYMENT_CAPTURE_PENDING,
    PAYMENT_RECONCILIATION_PENDING,
    PAYMENT_FAILED,
    CONFIRMED,
    FULFILLMENT_PENDING,
    SHIPPED,
    DELIVERED,
    COMPENSATION_PENDING,
    CANCELLATION_PENDING,
    CANCELLED,
    EXPIRED,
    MANUAL_REVIEW
}

enum OrderEvent {
    SUBMIT,
    PAYMENT_AUTHORIZED,
    PAYMENT_DECLINED,
    PAYMENT_RESULT_UNKNOWN,
    INVENTORY_RESERVED,
    INVENTORY_REJECTED,
    PAYMENT_CAPTURED,
    PAYMENT_CAPTURE_FAILED,
    CANCEL_REQUESTED,
    START_FULFILLMENT,
    SHIPMENT_CREATED,
    DELIVERY_CONFIRMED,
    ALL_COMPENSATIONS_SUCCEEDED,
    COMPENSATION_FAILED
}

record TransitionKey(OrderState from, OrderEvent event) {}

final class OrderStateMachine {
    private static final Map<TransitionKey, OrderState> TRANSITIONS =
        Map.ofEntries(
            Map.entry(
                new TransitionKey(OrderState.CREATED, OrderEvent.SUBMIT),
                OrderState.PAYMENT_AUTHORIZATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.PAYMENT_AUTHORIZATION_PENDING,
                    OrderEvent.PAYMENT_AUTHORIZED
                ),
                OrderState.INVENTORY_RESERVATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.PAYMENT_AUTHORIZATION_PENDING,
                    OrderEvent.PAYMENT_DECLINED
                ),
                OrderState.PAYMENT_FAILED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.PAYMENT_AUTHORIZATION_PENDING,
                    OrderEvent.PAYMENT_RESULT_UNKNOWN
                ),
                OrderState.PAYMENT_RECONCILIATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.INVENTORY_RESERVATION_PENDING,
                    OrderEvent.INVENTORY_RESERVED
                ),
                OrderState.PAYMENT_CAPTURE_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.INVENTORY_RESERVATION_PENDING,
                    OrderEvent.INVENTORY_REJECTED
                ),
                OrderState.COMPENSATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.PAYMENT_CAPTURE_PENDING,
                    OrderEvent.PAYMENT_CAPTURED
                ),
                OrderState.CONFIRMED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.PAYMENT_CAPTURE_PENDING,
                    OrderEvent.PAYMENT_CAPTURE_FAILED
                ),
                OrderState.COMPENSATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.CONFIRMED,
                    OrderEvent.CANCEL_REQUESTED
                ),
                OrderState.CANCELLATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.CONFIRMED,
                    OrderEvent.START_FULFILLMENT
                ),
                OrderState.FULFILLMENT_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.FULFILLMENT_PENDING,
                    OrderEvent.SHIPMENT_CREATED
                ),
                OrderState.SHIPPED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.SHIPPED,
                    OrderEvent.DELIVERY_CONFIRMED
                ),
                OrderState.DELIVERED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.COMPENSATION_PENDING,
                    OrderEvent.ALL_COMPENSATIONS_SUCCEEDED
                ),
                OrderState.CANCELLED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.CANCELLATION_PENDING,
                    OrderEvent.ALL_COMPENSATIONS_SUCCEEDED
                ),
                OrderState.CANCELLED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.COMPENSATION_PENDING,
                    OrderEvent.COMPENSATION_FAILED
                ),
                OrderState.MANUAL_REVIEW
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.CANCELLATION_PENDING,
                    OrderEvent.COMPENSATION_FAILED
                ),
                OrderState.MANUAL_REVIEW
            )
        );

    static OrderState next(OrderState current, OrderEvent event) {
        OrderState next = TRANSITIONS.get(new TransitionKey(current, event));
        if (next == null) {
            throw new IllegalStateException(
                "Invalid order transition: " + current + " + " + event
            );
        }
        return next;
    }
}
~~~

Đây là phần quyết định transition, chưa phải một workflow engine hoàn chỉnh. Trong ứng dụng thực tế, cần bổ sung:

1. **Guard:** xác minh người dùng có quyền thao tác trên đơn; số tiền và tiền tệ khớp; mã thanh toán thuộc đúng đơn; đơn chưa ở trạng thái kết thúc; yêu cầu hủy còn hợp lệ.
2. **Context:** lưu mã giao dịch, mã giữ hàng, thao tác thanh toán đang đối soát, hạn xử lý và danh sách bước bù còn lại.
3. **Persistence:** lưu trạng thái mới và phiên bản trong transaction; ghi event tiếp theo vào outbox trong cùng transaction.
4. **Action handler:** gọi nhà cung cấp thanh toán, tồn kho hoặc vận chuyển bằng request có idempotency key ổn định.
5. **Error mapping:** phân biệt lỗi nghiệp vụ, lỗi tạm thời, timeout chưa rõ kết quả và lỗi cần con người xử lý.

Không gọi API thanh toán trực tiếp bên trong hàm **next**. Nếu lời gọi bên ngoài thành công nhưng function chết trước khi lưu trạng thái, lần chạy sau có thể lặp lại side effect. Hãy ghi nhận ý định xử lý và dùng idempotency key ở hệ thống đích để thao tác có thể được gửi lại an toàn.

## 6. Đảm bảo cập nhật trạng thái và phát sự kiện nhất quán

Một lỗi phổ biến là ghi database rồi phát message bằng hai thao tác độc lập:

1. Cập nhật đơn sang **CONFIRMED**.
2. Gửi **OrderConfirmed** lên event bus.

Nếu function dừng giữa hai thao tác, database đã xác nhận đơn nhưng dịch vụ giao vận không nhận được sự kiện. Nếu đảo thứ tự, consumer có thể nhận sự kiện trước khi database commit. Đây là bài toán dual-write.

Transactional outbox giải quyết vấn đề bằng cách ghi trạng thái đơn và bản ghi outbox trong cùng một transaction database. Một publisher riêng đọc các bản ghi chưa phát, gửi message rồi đánh dấu đã phát. Publisher có thể gửi trùng nếu nó dừng sau khi gửi nhưng trước khi đánh dấu; vì vậy consumer vẫn phải idempotent.

Quy trình cập nhật một transition có thể diễn ra như sau:

1. Nhận event và kiểm tra schema, chữ ký hoặc nguồn phát.
2. Bắt đầu transaction; đọc đơn cùng **version**.
3. Kiểm tra event đã xử lý chưa và transition có hợp lệ không.
4. Kiểm tra guard và xác định trạng thái tiếp theo.
5. Cập nhật đơn với điều kiện phiên bản cũ vẫn khớp.
6. Ghi event hoặc command tiếp theo vào outbox trong cùng transaction.
7. Commit; publisher phát message sau đó.

Ví dụ cập nhật có optimistic locking:

~~~sql
UPDATE orders
SET status = :next_status,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = :order_id
  AND status = :expected_status
  AND version = :expected_version;
~~~

Nếu số dòng được cập nhật bằng 0, một xử lý khác có thể đã cập nhật đơn hoặc trạng thái hiện tại đã thay đổi. Hãy đọc lại và phân loại trường hợp: event trùng, event cũ, event đến sớm hay xung đột thật sự. Không được ghi đè trạng thái mới bằng dữ liệu cũ.

## 7. Retry, idempotency và sự kiện đến sai thứ tự

Hệ thống message thường cung cấp giao nhận ít nhất một lần (at-least-once). Điều đó có nghĩa một message có thể được gửi lại khi consumer timeout hoặc không xác nhận kịp. Retry là bình thường; side effect bị lặp mới là vấn đề cần ngăn chặn.

### Thiết kế idempotency

Một thao tác idempotent có thể được thực hiện nhiều lần nhưng chỉ tạo ra một kết quả nghiệp vụ tương đương. Có thể áp dụng nhiều lớp:

- API tạo đơn nhận **Idempotency-Key** từ client và lưu khóa với phạm vi người dùng hoặc tenant. Gửi lại cùng khóa phải trả về cùng đơn đã tạo.
- Consumer lưu **eventId** đã xử lý với ràng buộc duy nhất theo consumer hoặc loại tác vụ.
- Lệnh gọi nhà cung cấp thanh toán dùng khóa ổn định, chẳng hạn **orderId:authorize** hoặc **orderId:capture**. Không tạo khóa mới cho mỗi lần retry.
- Thao tác giữ hàng, giải phóng hàng, hoàn tiền và tạo vận đơn cũng cần mã tham chiếu hoặc khóa idempotency theo nghiệp vụ.
- Cập nhật trạng thái phải có điều kiện phiên bản để hai function không cùng áp dụng một transition.

Idempotency key phải đại diện cho một thao tác nghiệp vụ ổn định. Nếu dùng mã ngẫu nhiên mới cho mỗi lần retry, nhà cung cấp có thể coi mỗi lần là một giao dịch khác nhau.

### Chính sách retry

Chỉ retry lỗi có khả năng tự phục hồi, ví dụ lỗi mạng tạm thời, giới hạn tốc độ hoặc dịch vụ tạm không sẵn sàng. Không retry vô hạn các lỗi nghiệp vụ như thẻ bị từ chối, đơn không hợp lệ hoặc không đủ tồn kho.

Một chính sách thường dùng:

- Giới hạn số lần thử.
- Tăng khoảng chờ theo exponential backoff và thêm jitter để tránh nhiều function cùng retry một lúc.
- Đặt timeout cho từng lời gọi dịch vụ.
- Phân biệt retry của function, retry của queue và retry của workflow engine để tổng số lần thử không nhân lên ngoài dự kiến.
- Sau số lần thử tối đa, chuyển message vào dead-letter queue (DLQ), ghi rõ lỗi và tạo cảnh báo.
- Chỉ redrive message từ DLQ sau khi đã xác định nguyên nhân và kiểm tra thao tác có thể lặp an toàn.

Timeout không đồng nghĩa thao tác thất bại. Ví dụ function gọi nhà cung cấp thanh toán, nhà cung cấp đã thu tiền nhưng phản hồi bị mất. Nếu coi timeout là thất bại và gửi một giao dịch mới, khách có thể bị thu tiền hai lần. Khi kết quả không rõ, chuyển sang **PAYMENT_RECONCILIATION_PENDING** và truy vấn nhà cung cấp bằng mã giao dịch hoặc idempotency key cũ.

### Sự kiện trùng và sai thứ tự

Giả sử **ShipmentCreated** đến trước khi consumer nhận được **OrderConfirmed**. Không nên tự động bỏ qua sự kiện chỉ vì trạng thái hiện tại chưa cho phép. Có thể message trước đó đang chậm hoặc hai kênh phát event có độ trễ khác nhau.

Cần phân biệt:

- **Sự kiện trùng:** **eventId** đã xử lý; có thể xác nhận message và không lặp side effect.
- **Sự kiện cũ:** **aggregateVersion** nhỏ hơn phiên bản hiện tại; lưu dấu vết và bỏ qua nếu đã được thay thế.
- **Sự kiện đến sớm:** phiên bản hoặc điều kiện tiên quyết chưa có; giữ lại để retry hoặc đưa vào hàng chờ theo đơn.
- **Xung đột:** hai transition cạnh tranh cùng cập nhật một phiên bản; chỉ một transaction được commit, transaction còn lại phải đọc lại và đánh giá.

Nếu cần thứ tự theo từng đơn, dùng partition key hoặc message group theo **orderId**, đồng thời vẫn kiểm tra **version** ở database. Không nên giả định event bus luôn giữ thứ tự toàn cục.

## 8. Timeout, thao tác bù và tính nhất quán nghiệp vụ

Workflow đặt hàng thường kéo dài hơn thời gian sống của một lần gọi function. Không giữ một function chạy và ngủ trong vài phút để đợi thanh toán hoặc giao hàng. Hãy lưu thời hạn, kết thúc invocation và dùng timer bền vững hoặc workflow wait state để tiếp tục vào đúng thời điểm.

Timeout cần được xử lý theo ngữ nghĩa nghiệp vụ:

- Hết hạn thanh toán: đối soát với nhà cung cấp trước khi đánh dấu **EXPIRED**.
- Giữ hàng quá lâu: kiểm tra trạng thái thanh toán và chính sách giữ hàng trước khi giải phóng.
- Nhà vận chuyển không trả kết quả: truy vấn theo mã vận đơn hoặc chuyển theo dõi sang quy trình xử lý ngoại lệ.
- Function vượt timeout: lần chạy sau phải xác định side effect trước đó đã xảy ra chưa.

### Saga và compensation

Một quy trình nhiều dịch vụ thường không có transaction ACID bao trùm tất cả hệ thống. Nếu thanh toán đã được cấp phép nhưng tồn kho từ chối giữ hàng, hệ thống cần hủy cấp phép. Nếu đã thu tiền rồi mới phát hiện không thể giao, có thể cần hoàn tiền và giải phóng giữ hàng.

Đây là mô hình Saga: workflow gồm nhiều bước cục bộ; mỗi bước thành công có thể có một hành động bù tương ứng khi bước sau thất bại.

| Bước đã hoàn thành | Hành động bù có thể cần |
|---|---|
| Cấp phép thanh toán | Hủy cấp phép (void authorization) |
| Giữ hàng | Giải phóng giữ hàng |
| Thu tiền | Hoàn tiền (refund) |
| Tạo vận đơn nhưng chưa bàn giao | Hủy nhãn hoặc yêu cầu hủy vận đơn nếu nhà vận chuyển hỗ trợ |

Compensation không phải rollback database tức thời. Nó là một thao tác nghiệp vụ mới, có thể thất bại, cần retry và phải idempotent. Ví dụ hoàn tiền có thể mất vài phút hoặc cần nhà cung cấp xác nhận. Vì vậy **CANCELLED** chỉ nên được ghi khi các thao tác bắt buộc theo chính sách đã hoàn tất. Nếu không thể xác minh kết quả, chuyển sang **MANUAL_REVIEW** và cảnh báo vận hành.

Một đơn đã **SHIPPED** thường không thể hủy bằng cách hoàn tác các bước trước đó. Khi đó cần một workflow trả hàng hoặc từ chối nhận hàng riêng. Quy tắc này phải được thể hiện trong guard để không có request hủy nào vô tình làm đơn đang giao quay lại **CANCELLED**.

## 9. Bảo mật và quyền truy cập

Mỗi function chỉ nên có quyền cần cho bước của nó:

- Function tạo đơn được quyền tạo đơn và ghi outbox, không cần quyền hoàn tiền.
- Function thanh toán chỉ được gọi các thao tác thanh toán cần thiết và đọc dữ liệu đơn tối thiểu.
- Function tồn kho chỉ được giữ hoặc giải phóng hàng.
- Function giao vận chỉ được tạo hoặc tra cứu vận đơn.
- Consumer chỉ nhận message từ queue hoặc topic được chỉ định.

HTTP endpoint phải xác thực người dùng và kiểm tra quyền sở hữu đơn theo customer hoặc tenant. Không dùng **orderId** do client gửi làm bằng chứng rằng client được phép xem hoặc hủy đơn. Webhook cần xác minh chữ ký, thời gian và chống phát lại theo cơ chế của nhà cung cấp. Secret và API key nên nằm trong secret manager; không ghi token, dữ liệu thẻ hoặc thông tin xác thực vào log.

Event payload phải được kiểm tra kiểu, kích thước, phiên bản schema và giới hạn dữ liệu. Với event liên tenant, consumer phải kiểm tra tenant context để tránh cập nhật nhầm đơn. Quyền truy cập database, queue, event bus và kho secret nên được cấp riêng theo function, có thể audit và thu hồi độc lập.

## 10. Quan sát và vận hành workflow

Một workflow phân tán cần cho người vận hành thấy được hành trình của một đơn hàng. Mỗi log và trace nên mang các định danh tương quan như **orderId**, **eventId**, **correlationId**, **workflowId** và tên bước. Không ghi toàn bộ payload nhạy cảm chỉ để thuận tiện debug.

Các chỉ số hữu ích gồm:

- Số đơn ở từng trạng thái và thời gian trung bình ở mỗi trạng thái.
- Tỷ lệ thanh toán bị từ chối, timeout và cần đối soát.
- Tỷ lệ giữ hàng thất bại, thu tiền thất bại và bù trừ thất bại.
- Số lần retry trên mỗi bước, độ sâu queue và số message trong DLQ.
- Số workflow vượt thời hạn hoặc ở **MANUAL_REVIEW**.
- Thời gian từ **CREATED** đến **CONFIRMED**, từ **SHIPPED** đến **DELIVERED**.
- Số transition bị từ chối do event trùng, event cũ hoặc xung đột phiên bản.

Cần có dashboard để truy vấn lịch sử của một **orderId**, hiển thị trạng thái, event đã nhận, command đã gửi, số lần thử và lỗi gần nhất. Cảnh báo nên gắn với ngưỡng nghiệp vụ, ví dụ số đơn chờ đối soát tăng đột biến hoặc compensation thất bại, thay vì chỉ cảnh báo mọi exception của function.

## 11. Cold start, mở rộng và chi phí trong môi trường serverless

FaaS phù hợp với các bước xử lý ngắn, được kích hoạt bởi HTTP, message hoặc event và có tải biến động. Nền tảng có thể tăng hoặc giảm số instance theo lượng invocation. Database, queue và nhà cung cấp bên ngoài vẫn có giới hạn riêng; tăng số function không tự động làm tăng khả năng chịu tải của các dịch vụ đó.

Java function có thể gặp cold start khi nền tảng phải tạo runtime mới, nạp class và khởi tạo dependency. Có thể giảm thời gian khởi động bằng cách giữ dependency gọn, tránh khởi tạo framework nặng không cần thiết, tái sử dụng client kết nối an toàn giữa các invocation và đặt timeout hợp lý. Không lưu trạng thái nghiệp vụ trong biến static hoặc bộ nhớ instance vì invocation có thể chạy trên instance khác, instance có thể bị thu hồi và nhiều invocation có thể chạy đồng thời.

Chi phí của workflow thường đến từ nhiều thành phần:

- Số lần invocation và thời gian chạy của từng function.
- CPU hoặc bộ nhớ được cấp cho function.
- Số lần chuyển trạng thái hoặc bước thực thi của workflow engine.
- Số message, event, lần retry và message DLQ.
- Database, lưu lịch sử workflow, log, trace và dữ liệu lưu trữ.
- Truyền dữ liệu qua mạng hoặc gọi dịch vụ bên ngoài.

Một function ngắn nhưng bị retry hàng nghìn lần vẫn có thể tạo chi phí đáng kể. Một workflow có nhiều bước nhỏ giúp cô lập lỗi nhưng làm tăng số lần invocation và transition. Hãy đo thời gian thực tế, tỷ lệ lỗi và số lần retry để cân bằng độ tin cậy với chi phí.

Với tác vụ chờ lâu, dùng trạng thái chờ bền vững và timer thay vì giữ function hoạt động. Với tải ổn định, rất cao và yêu cầu độ trễ cực thấp, cần so sánh tổng chi phí và độ phức tạp của FaaS với dịch vụ chạy liên tục. Quyết định nên dựa trên đặc điểm workload, yêu cầu vận hành và giới hạn của nền tảng.

## 12. Các tình huống lỗi cần mô hình hóa

| Tình huống | Rủi ro | Cách xử lý |
|---|---|---|
| Client gửi lại **POST /orders** sau khi timeout | Tạo hai đơn cho một lần đặt hàng | Dùng idempotency key và ràng buộc duy nhất |
| Nhà cung cấp đã thu tiền nhưng function timeout | Thu tiền hai lần nếu gửi lại giao dịch mới | Đối soát bằng khóa giao dịch cũ |
| **PaymentAuthorized** được gửi hai lần | Giữ hàng hai lần | Phát hiện **eventId** trùng và dùng idempotency key cho lệnh giữ hàng |
| **InventoryRejected** đến sau một lần retry | Hủy cấp phép nhiều lần | Transition có điều kiện và thao tác void idempotent |
| Hai function cùng xử lý yêu cầu hủy và tạo vận đơn | Đơn vừa bị hủy vừa bị giao | Optimistic locking, guard và quy tắc thứ tự theo đơn |
| Publisher phát event rồi chết trước khi đánh dấu outbox | Consumer nhận event lặp | Consumer idempotent |
| Hoàn tiền thất bại sau khi đơn đã yêu cầu hủy | Trạng thái đơn và tiền thực tế không khớp | Giữ **CANCELLATION_PENDING**, retry có giới hạn và cảnh báo |
| Message lỗi liên tục | Queue bị nghẽn hoặc mất khả năng xử lý | DLQ, phân loại lỗi và redrive sau khi khắc phục |

## 13. Kiểm thử state machine

Kiểm thử nên tập trung vào quy tắc nghiệp vụ và các tình huống phân tán:

1. **Kiểm thử transition:** với mỗi cặp trạng thái và sự kiện hợp lệ, xác nhận trạng thái tiếp theo đúng bảng. Với cặp không hợp lệ, xác nhận hệ thống từ chối.
2. **Kiểm thử guard:** người dùng khác không thể hủy đơn; số tiền hoặc tiền tệ sai không thể xác nhận thanh toán; đơn đã giao không thể hủy theo luồng thông thường.
3. **Kiểm thử idempotency:** gửi cùng event hoặc cùng API idempotency key nhiều lần nhưng chỉ tạo một side effect.
4. **Kiểm thử timeout:** mô phỏng nhà cung cấp đã xử lý nhưng phản hồi bị mất; xác nhận hệ thống đối soát thay vì tạo giao dịch mới.
5. **Kiểm thử cạnh tranh:** hai function cập nhật cùng một phiên bản; chỉ một transition được commit.
6. **Kiểm thử compensation:** giữ hàng thành công nhưng thanh toán thất bại; xác nhận hàng được giải phóng và cấp phép được hủy.
7. **Kiểm thử DLQ và redrive:** message lỗi được lưu dấu vết, cảnh báo và có thể xử lý lại an toàn sau khi sửa nguyên nhân.
8. **Kiểm thử hợp đồng sự kiện:** producer và consumer hiểu cùng schema, phiên bản và ý nghĩa của event.

Ngoài unit test, nên có integration test với queue, database và mock provider. Với quy trình quan trọng, hãy kiểm thử cả việc function bị dừng ngay sau side effect, ngay trước commit hoặc ngay sau commit để tìm ra các cửa sổ lỗi.

## 14. Quy trình triển khai một workflow đặt hàng

Có thể triển khai theo trình tự sau:

1. **Chốt quy tắc nghiệp vụ:** thống nhất trạng thái, sự kiện, guard, trạng thái kết thúc, điều kiện hủy và chính sách hoàn tiền.
2. **Thiết kế hợp đồng event:** xác định định danh, schema, version, correlation, payload và nguồn phát đáng tin cậy.
3. **Thiết kế lưu trữ:** xác định bảng đơn hàng, phiên bản, event log, outbox, idempotency key và thời hạn xử lý.
4. **Viết state machine thuần:** xây dựng bảng transition và guard; kiểm thử các cặp hợp lệ, không hợp lệ.
5. **Tạo các Java function:** tách handler HTTP, payment, inventory, fulfillment và consumer theo trách nhiệm.
6. **Thiết lập trigger và quyền:** nối HTTP API, queue, event bus, timer hoặc workflow engine; cấp quyền tối thiểu.
7. **Bổ sung retry và compensation:** đặt timeout, backoff, DLQ, đối soát và thao tác bù idempotent.
8. **Thiết lập quan sát:** log có cấu trúc, trace, metric, dashboard và cảnh báo theo trạng thái nghiệp vụ.
9. **Kiểm thử lỗi và tải:** mô phỏng event trùng, event sai thứ tự, provider chậm, concurrency và cold start.
10. **Triển khai có kiểm soát:** theo dõi tỷ lệ lỗi, thời gian xử lý, số workflow tồn đọng và chi phí sau khi phát hành.

## 15. Khi nào nên dùng state machine và FaaS?

State machine đặc biệt hữu ích khi quy trình có nhiều bước, nhiều nhánh, có thể kéo dài, phụ thuộc vào kết quả của hệ thống khác hoặc cần biết chính xác một đối tượng đang ở đâu. Quy tắc transition rõ ràng cũng giúp kiểm toán và hỗ trợ vận hành.

FaaS phù hợp khi mỗi bước có thể được đóng gói thành một xử lý ngắn, kích hoạt theo yêu cầu hoặc sự kiện, có thể mở rộng độc lập và không cần giữ trạng thái trong bộ nhớ. Kết hợp state machine với FaaS giúp tách điều phối nghiệp vụ khỏi phần tính toán của từng bước.

Hãy cân nhắc mô hình khác hoặc dịch vụ chạy liên tục nếu workload luôn hoạt động ở mức cao, cần giữ kết nối dài hạn, xử lý dữ liệu liên tục hoặc có yêu cầu độ trễ mà cold start và chi phí invocation không đáp ứng. Dù chọn nền tảng nào, trạng thái nghiệp vụ vẫn cần được lưu bền vững và transition phải được kiểm soát.

## 16. Bài tập thực hành

**Bài tập 1 — Hoàn thiện mô hình:** Thêm trạng thái **RETURN_REQUESTED** và mô tả cách xử lý yêu cầu trả hàng sau khi đơn đã **DELIVERED**. Xác định event, guard, hành động hoàn tiền và trạng thái kết thúc.

**Bài tập 2 — Xử lý thanh toán không rõ kết quả:** Nhà cung cấp thanh toán đã nhận yêu cầu nhưng HTTP function timeout trước khi nhận phản hồi. Mô tả dữ liệu cần lưu, cách đối soát và điều kiện để chuyển đơn sang **INVENTORY_RESERVATION_PENDING**, **PAYMENT_FAILED** hoặc **MANUAL_REVIEW**.

**Bài tập 3 — Chống xử lý trùng:** Một message **InventoryReserved** được giao ba lần. Chỉ ra các lớp idempotency cần có ở consumer, database và lệnh gọi dịch vụ tiếp theo.

**Bài tập 4 — Xử lý cạnh tranh:** Khách yêu cầu hủy cùng lúc worker giao vận bắt đầu tạo vận đơn. Viết guard và điều kiện cập nhật có version để chỉ một nhánh được phép tiếp tục.

**Bài tập 5 — Chọn kiến trúc:** So sánh workflow engine có trạng thái bền vững với state machine do ứng dụng tự quản lý trong database. Nêu trách nhiệm vận hành, khả năng quan sát, giới hạn và chi phí mà nhóm phải đánh giá.

Khi hoàn thành bài tập, hãy kiểm tra rằng mọi trạng thái đều có ý nghĩa rõ ràng, mọi event đều có nguồn phát, mọi transition đều có guard phù hợp và mọi side effect quan trọng đều có chiến lược idempotency hoặc compensation.

