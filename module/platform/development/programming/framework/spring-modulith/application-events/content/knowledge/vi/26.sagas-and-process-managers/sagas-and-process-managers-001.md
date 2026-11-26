# Saga là gì

Saga là một mẫu thiết kế để điều phối một quy trình nghiệp vụ gồm nhiều bước, trong đó mỗi bước có thể commit độc lập. Thay vì giữ một transaction duy nhất xuyên qua nhiều module hoặc dịch vụ, saga chia quy trình thành các local transaction. Khi một bước thất bại sau khi những bước trước đã commit, hệ thống thực hiện hành động bù trừ (compensation) hoặc một nhánh phục hồi được định nghĩa trước.

Saga thường xuất hiện trong các quy trình như đặt hàng, thanh toán, giữ tồn kho, giao hàng, đăng ký dịch vụ hoặc cấp hạn mức. Mỗi bước thuộc quyền sở hữu của một module hoặc dịch vụ. Các bước phối hợp qua application events, message hoặc lời gọi API theo một hợp đồng rõ ràng.

Trong Spring Modulith, application events cung cấp cơ chế để các module phát tín hiệu nghiệp vụ và phản ứng với tín hiệu từ module khác. Có thể dùng chúng để xây dựng choreography hoặc kết nối với một process manager. Spring Modulith hỗ trợ ranh giới module và theo dõi event publication; bản thân framework không tự tạo một saga engine, không tự lưu trạng thái toàn bộ quy trình và không tự sinh các hành động compensation.

## 1. Vì sao cần saga?

Một transaction cơ sở dữ liệu thông thường có thể bảo đảm nhiều thay đổi cùng commit hoặc rollback trong một ranh giới transaction. Nhưng một quy trình liên quan đến nhiều module hoặc dịch vụ thường vượt ra ngoài ranh giới đó.

Ví dụ, một đơn hàng cần thực hiện các bước:

1. Tạo đơn hàng.
2. Giữ tồn kho.
3. Xác nhận thanh toán.
4. Tạo yêu cầu giao hàng.
5. Đánh dấu đơn hàng sẵn sàng.

Nếu tất cả bước cùng nằm trong một cơ sở dữ liệu và một transaction, có thể cân nhắc transaction thông thường. Nhưng nếu giữ tồn kho, thanh toán và giao hàng thuộc các module hoặc dịch vụ có transaction riêng, không thể giả định một transaction ACID duy nhất sẽ rollback được tất cả.

Saga chia quy trình thành các local transaction:

- Mỗi module commit thay đổi thuộc quyền sở hữu của mình.
- Sau khi hoàn tất, module phát event mô tả kết quả nghiệp vụ.
- Bước tiếp theo được kích hoạt dựa trên event hoặc quyết định của process manager.
- Nếu quy trình không thể tiếp tục, hệ thống thực hiện compensation cho các bước đã hoàn tất theo quy tắc nghiệp vụ.

Điều này giúp quy trình tiến triển mà không cần khóa tài nguyên xuyên suốt nhiều dịch vụ. Đổi lại, hệ thống phải quản lý trạng thái trung gian, event đến trùng hoặc sai thứ tự, timeout và các hành động bù trừ.

## 2. Ví dụ saga đặt hàng

Giả sử khách hàng đặt một đơn hàng gồm giữ tồn kho, thanh toán và giao hàng. Một luồng thành công có thể như sau:

~~~mermaid
flowchart TD
    A["OrderPlaced"] --> B["Giữ tồn kho"]
    B --> C["InventoryReserved"]
    C --> D["Ủy quyền thanh toán"]
    D --> E["PaymentAuthorized"]
    E --> F["Tạo yêu cầu giao hàng"]
    F --> G["ShipmentCreated"]
    G --> H["OrderConfirmed"]
~~~

Nếu thanh toán bị từ chối sau khi tồn kho đã được giữ, hệ thống cần giải phóng phần tồn kho đó. Nếu tạo yêu cầu giao hàng thất bại sau khi thanh toán đã được ủy quyền, quy trình có thể cần hủy ủy quyền thanh toán và giải phóng tồn kho.

~~~mermaid
flowchart TD
    A["OrderPlaced"] --> B["InventoryReserved"]
    B --> C{"Payment authorized?"}
    C -->|Có| D["Create shipment"]
    C -->|Không| E["Release inventory"]
    D -->|Thành công| F["OrderConfirmed"]
    D -->|Thất bại| G["Void payment authorization"]
    G --> H["Release inventory"]
    E --> I["OrderCancelled"]
    H --> I
~~~

Các hành động bù trừ không nhất thiết khôi phục hệ thống về đúng trạng thái vật lý ban đầu. Ví dụ, một khoản thanh toán đã capture có thể cần refund thay vì xóa giao dịch; một lô hàng đã được bàn giao cho đơn vị vận chuyển có thể cần quy trình thu hồi. Compensation là một hành động nghiệp vụ mới, có kết quả và lỗi riêng.

## 3. Local transaction và compensation

Mỗi bước saga nên có một local transaction với ranh giới rõ ràng. Transaction đó cập nhật dữ liệu thuộc module và ghi nhận kết quả của bước. Khi commit, module phát event để thông báo kết quả.

| Bước | Local transaction | Compensation có thể có |
|---|---|---|
| Tạo đơn hàng | Lưu đơn ở trạng thái PENDING | Hủy đơn |
| Giữ tồn kho | Tạo reservation | Giải phóng reservation |
| Ủy quyền thanh toán | Tạo payment authorization | Void authorization |
| Capture thanh toán | Ghi nhận khoản thu | Refund theo chính sách |
| Tạo vận đơn | Tạo shipment request | Hủy hoặc yêu cầu thu hồi shipment |

Không phải mọi bước đều có compensation đối xứng. Gửi email thông báo có thể không thu hồi được. Ghi audit log không nên bị xóa. Một số bước có thể dùng forward recovery: sửa điều kiện và tiếp tục quy trình thay vì bù trừ.

Trước khi thiết kế saga, hãy xác định cho từng bước:

- Điều kiện để bắt đầu và điều kiện để hoàn tất.
- Dữ liệu nào được commit trong local transaction.
- Event nào thông báo kết quả.
- Compensation nào có thể thực hiện và có giới hạn gì.
- Hành động nào không thể hoàn tác.
- Trường hợp nào cần con người xử lý.

Không gọi compensation là rollback database. Rollback hủy các thay đổi chưa commit trong một transaction; compensation là nghiệp vụ mới để xử lý tác động của các transaction đã commit.

## 4. Choreography và orchestration

Có hai cách tổ chức luồng saga phổ biến.

**Choreography** để các participant phản ứng với event của nhau. Module Đơn hàng phát OrderPlaced; module Kho nhận event và phát InventoryReserved; module Thanh toán nhận InventoryReserved và phát PaymentAuthorized; module Giao hàng nhận PaymentAuthorized và tiếp tục.

~~~mermaid
flowchart LR
    O["Order module"] -->|"OrderPlaced"| I["Inventory module"]
    I -->|"InventoryReserved"| P["Payment module"]
    P -->|"PaymentAuthorized"| S["Shipping module"]
    S -->|"ShipmentCreated"| O
~~~

Ưu điểm của choreography là mỗi module giữ quyền sở hữu logic của mình và không cần một bộ điều phối trung tâm. Tuy nhiên, khi có nhiều nhánh, timeout và compensation, luồng điều khiển có thể khó nhìn thấy. Một module mới đăng ký event có thể làm thay đổi hành vi toàn hệ thống nếu contract và ownership không rõ.

**Orchestration** dùng một process manager hoặc saga coordinator lưu trạng thái quy trình và quyết định bước tiếp theo. Các participant thực hiện command hoặc application service và trả về event kết quả.

~~~mermaid
flowchart TD
    E["OrderPlaced"] --> M["Order Saga Manager"]
    M -->|"ReserveInventory"| I["Inventory module"]
    I -->|"InventoryReserved / InventoryRejected"| M
    M -->|"AuthorizePayment"| P["Payment module"]
    P -->|"PaymentAuthorized / PaymentRejected"| M
    M -->|"CreateShipment"| S["Shipping module"]
    S -->|"ShipmentCreated / ShipmentFailed"| M
    M -->|"Confirm / Compensate"| O["Order state"]
~~~

Orchestration làm rõ trạng thái và thứ tự bước, phù hợp với quy trình có nhiều nhánh hoặc compensation. Đổi lại, process manager trở thành nơi điều phối cần được quản lý cẩn thận. Nó không nên tự sở hữu dữ liệu nghiệp vụ của các participant hoặc thực hiện thay công việc nội bộ của chúng.

| Tiêu chí | Choreography | Orchestration |
|---|---|---|
| Điều khiển luồng | Phân tán qua event | Tập trung ở process manager |
| Dễ thấy toàn bộ quy trình | Khó hơn khi nhiều participant | Dễ theo dõi trạng thái tổng thể |
| Phụ thuộc | Participant phụ thuộc contract event | Participant nhận command và phát kết quả |
| Compensation | Mỗi participant phản ứng theo event | Process manager quyết định bước bù trừ |
| Phù hợp | Quy trình ngắn, ít nhánh | Quy trình dài, nhiều bước, timeout và nhánh lỗi |

Có thể kết hợp hai cách. Một process manager điều phối các bước lớn, còn từng module sử dụng event nội bộ để hoàn thành công việc của mình.

## 5. Process manager là gì?

Process manager là thành phần giữ trạng thái của một quy trình đang chạy và quyết định hành động tiếp theo dựa trên event nhận được. Nó liên kết nhiều bước bằng một định danh saga ổn định.

Process manager thường cần lưu:

| Trường | Mục đích |
|---|---|
| sagaId | Định danh duy nhất của một lần chạy quy trình |
| businessId | Định danh nghiệp vụ như orderId |
| state | Trạng thái hiện tại của saga |
| completedSteps | Các bước đã hoàn tất |
| pendingStep | Bước đang chờ kết quả |
| correlationId | Liên kết log và event trong cùng quy trình |
| deadline | Hạn chờ cho bước hoặc toàn quy trình |
| version | Kiểm soát cập nhật đồng thời |
| failureReason | Nguyên nhân thất bại gần nhất |
| updatedAt | Thời điểm cập nhật trạng thái |

Không nên chỉ giữ trạng thái saga trong bộ nhớ. Nếu tiến trình dừng hoặc ứng dụng được triển khai lại, process manager phải khôi phục được quy trình đang chờ từ kho lưu trữ bền vững.

Một saga state có thể dùng enum rõ ràng như STARTED, INVENTORY_PENDING, INVENTORY_RESERVED, PAYMENT_PENDING, PAYMENT_AUTHORIZED, SHIPPING_PENDING, COMPLETED, COMPENSATING, COMPENSATED và FAILED. Tên và số trạng thái phụ thuộc nghiệp vụ; quan trọng là chuyển trạng thái phải có quy tắc xác định.

## 6. Tổ chức saga trong Spring Modulith

Spring Modulith cung cấp application events để các module giao tiếp qua contract thay vì gọi trực tiếp implementation nội bộ. Một module có thể phát event sau khi local transaction commit; module khác nhận event qua listener ở ranh giới module.

Ví dụ event:

~~~java
public record OrderPlaced(
    UUID eventId,
    UUID sagaId,
    UUID orderId,
    Instant occurredAt
) {}

public record InventoryReserved(
    UUID eventId,
    UUID sagaId,
    UUID orderId,
    UUID reservationId
) {}

public record InventoryRejected(
    UUID eventId,
    UUID sagaId,
    UUID orderId,
    String reason
) {}

public record PaymentAuthorized(
    UUID eventId,
    UUID sagaId,
    UUID orderId,
    UUID authorizationId
) {}
~~~

Các event mang sagaId để process manager ghép kết quả về đúng lần chạy. eventId nhận diện lần phát event và được giữ ổn định khi retry; orderId nhận diện thực thể nghiệp vụ.

Một listener có thể dùng @ApplicationModuleListener để xử lý bất đồng bộ sau khi transaction phát event commit:

~~~java
@Component
class OrderSagaManager {

    private final SagaRepository sagas;
    private final OrderWorkflowCommands commands;

    OrderSagaManager(
            SagaRepository sagas,
            OrderWorkflowCommands commands) {
        this.sagas = sagas;
        this.commands = commands;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        if (!sagas.startIfAbsent(
                event.sagaId(),
                event.orderId(),
                event.eventId())) {
            return;
        }

        commands.reserveInventory(
            event.sagaId(),
            event.orderId()
        );
    }

    @ApplicationModuleListener
    void on(InventoryReserved event) {
        var saga = sagas.find(event.sagaId())
            .orElseThrow();

        if (!saga.acceptInventoryReserved(event.eventId())) {
            return;
        }

        commands.authorizePayment(
            event.sagaId(),
            event.orderId()
        );
    }
}
~~~

OrderWorkflowCommands và SagaRepository trong ví dụ là abstraction do ứng dụng định nghĩa, không phải API có sẵn của Spring Modulith. Lệnh có thể được gửi qua module API hoặc adapter messaging tùy kiến trúc. Khi gửi command ra broker, cần có cơ chế lưu bền vững và retry phù hợp để không mất lệnh giữa lúc cập nhật saga state và gửi command.

Ví dụ chỉ minh họa hai chuyển trạng thái đầu. Ứng dụng thực tế cần xử lý các kết quả từ chối, compensation, timeout, duplicate, event đến muộn và lỗi khi gửi command. Không nên coi đoạn code rút gọn này là một saga implementation hoàn chỉnh.

## 7. Lưu trạng thái và chuyển trạng thái an toàn

Mỗi event kết quả có thể được giao nhiều lần. Process manager phải kiểm tra trạng thái hiện tại trước khi áp dụng chuyển trạng thái. Ví dụ, nếu saga đã ở PAYMENT_AUTHORIZED thì một InventoryReserved đến trễ không được khởi động lại bước thanh toán.

Nên thực hiện cập nhật trạng thái bằng transaction và kiểm soát đồng thời. Có thể dùng optimistic locking với version hoặc khóa phù hợp khi nhiều instance cùng xử lý event của một saga.

Một chuyển trạng thái thường cần:

1. Tìm saga theo sagaId.
2. Kiểm tra event có thuộc saga và bước hiện tại hay không.
3. Kiểm tra eventId đã được xử lý chưa.
4. Xác thực trạng thái cho phép chuyển tiếp.
5. Ghi nhận event đã xử lý và trạng thái mới trong cùng transaction.
6. Lưu yêu cầu phát command tiếp theo theo cơ chế bền vững.
7. Commit và để adapter gửi command/event sau đó.

Nếu bước 5 và 6 không cùng một ranh giới lưu trữ, tiến trình có thể lưu trạng thái mới nhưng dừng trước khi gửi command. Khi khởi động lại, saga tưởng đã chuyển bước nhưng participant chưa nhận yêu cầu. Có thể dùng outbox cho command hoặc event tiếp theo để việc cập nhật saga state và ghi nhận thông điệp cần gửi cùng commit.

Không dùng một biến boolean kiểu completed để đại diện cho cả quy trình nhiều bước. Trạng thái phải đủ chi tiết để biết đã hoàn tất bước nào, đang chờ ai và cần compensation gì nếu thất bại.

## 8. Compensation và quy trình hủy

Process manager cần biết những bước nào đã hoàn tất và compensation tương ứng. Khi một bước thất bại, nó xác định các hành động bù trừ theo thứ tự phù hợp.

Ví dụ, nếu tồn kho đã giữ và thanh toán đã được ủy quyền nhưng tạo vận đơn thất bại:

1. Đánh dấu saga ở trạng thái COMPENSATING.
2. Yêu cầu void payment authorization.
3. Chờ event xác nhận đã void hoặc ghi nhận thất bại.
4. Yêu cầu release inventory reservation.
5. Chờ event xác nhận đã release.
6. Đánh dấu đơn hàng CANCELLED hoặc yêu cầu xử lý thủ công nếu một compensation không thành công.

Compensation cũng có thể thất bại. Không được đánh dấu saga COMPENSATED chỉ vì đã gửi yêu cầu bù trừ. Cần nhận kết quả của từng hành động và có retry, timeout, cảnh báo hoặc quy trình can thiệp phù hợp.

Một số nghiệp vụ không nên compensation tự động. Ví dụ, refund có thể cần phê duyệt; giao hàng đã rời kho có thể cần quy trình thu hồi. Process manager nên chuyển sang trạng thái NEEDS_ATTENTION và lưu nguyên nhân khi không thể tự khắc phục an toàn.

## 9. Timeout và bước chờ lâu

Một participant có thể không bao giờ phát event kết quả do lỗi hệ thống, message thất lạc hoặc quy trình cần chờ bên thứ ba. Saga cần deadline cho từng bước hoặc cho toàn bộ quy trình.

Khi quá hạn, process manager có thể:

- Gửi yêu cầu kiểm tra trạng thái tới participant.
- Retry command nếu command có idempotency.
- Chuyển sang nhánh compensation.
- Đánh dấu NEEDS_ATTENTION để con người xử lý.
- Phát cảnh báo nếu bước có tác động nghiệp vụ lớn.

Không coi việc không nhận event là bằng chứng participant đã thất bại. Có thể event đang chậm hoặc đang nằm trong backlog. Trước khi compensation, cần cân nhắc truy vấn trạng thái hiện tại của participant để tránh bù trừ một bước đã thành công nhưng event kết quả đến muộn.

Timeout nên được lưu bền vững cùng saga state. Một timer trong bộ nhớ không đủ cho quy trình có thể kéo dài qua lần restart. Có thể dùng scheduler quét các saga quá hạn, job bền vững hoặc dịch vụ scheduling được tổ chức vận hành.

## 10. Correlation, ordering và event đến muộn

Mọi event của saga nên mang sagaId và businessId. Correlation ID giúp nối trace qua nhiều module hoặc dịch vụ. Cần phân biệt correlation ID với event ID: một saga có nhiều event ID nhưng cùng sagaId/correlation ID.

Event có thể đến trùng hoặc sai thứ tự. Process manager cần xác định:

- Event có đúng sagaId và businessId không?
- Event có thuộc bước đang chờ không?
- Event ID đã được xử lý chưa?
- Event có version hoặc sequence number cũ hơn trạng thái hiện tại không?
- Saga đã hoàn tất hoặc bị hủy chưa?

Event không phù hợp có thể được ghi nhận là duplicate, stale hoặc unexpected. Không nên âm thầm áp dụng một chuyển trạng thái bất kỳ. Những trường hợp không thể tự phân loại cần log có cấu trúc và cảnh báo.

Nếu event đến muộn sau khi saga đã compensation, process manager phải có chính sách rõ ràng. Ví dụ, nếu InventoryReserved đến sau khi saga đã gửi ReleaseInventory, hệ thống cần kiểm tra reservation thực tế và bảo đảm cuối cùng tồn kho được giải phóng. Một event cũ không được tự động đưa saga trở lại luồng thành công.

## 11. Saga trong một ứng dụng Modulith và saga phân tán

Spring Modulith thường tổ chức nhiều module trong cùng một ứng dụng. Các module có thể dùng application events và Event Publication Registry để theo dõi việc giao event giữa các listener trong ứng dụng. Một saga nội bộ có thể điều phối nhiều module mà không cần một message broker bên ngoài.

Khi saga vượt qua nhiều ứng dụng hoặc dịch vụ, event phải được externalize qua broker hoặc adapter. Khi đó, mỗi ứng dụng sở hữu local transaction, publication và consumer acknowledgement của riêng nó. Saga coordinator có thể nằm trong một dịch vụ riêng hoặc được phân chia theo domain, tùy quy mô và ownership.

Cần phân biệt ba loại trạng thái:

- Event publication state: framework đã giao event tới listener tương ứng hay chưa.
- Message delivery state: broker đã giao message và consumer đã ack hay chưa.
- Saga business state: quy trình nghiệp vụ đang ở bước nào và cần hành động gì tiếp theo.

Event Publication Registry không thay thế saga state store. Consumer ack cũng không chứng minh toàn bộ saga đã hoàn tất. Mỗi trạng thái cần được lưu và quan sát tại đúng thành phần sở hữu.

## 12. Kiểm thử saga

Kiểm thử saga cần tập trung vào chuyển trạng thái, duplicate, lỗi giữa các bước và compensation. Không chỉ kiểm tra happy path.

Các kịch bản nên kiểm thử:

- Event khởi đầu tạo đúng saga instance và command đầu tiên.
- Event kết quả hợp lệ chuyển saga sang bước tiếp theo.
- Event trùng không tạo command hoặc side effect trùng.
- Event sai sagaId hoặc sai businessId bị từ chối có kiểm soát.
- Event đến sai thứ tự không làm saga chuyển trạng thái sai.
- Participant từ chối bước xử lý kích hoạt đúng compensation.
- Compensation thành công đưa saga đến trạng thái kết thúc phù hợp.
- Compensation thất bại chuyển saga sang NEEDS_ATTENTION.
- Timeout được phát hiện sau khi ứng dụng restart.
- Command outbox chưa gửi được tiếp tục gửi sau khi tiến trình phục hồi.
- Hai instance đồng thời xử lý cùng saga không làm mất cập nhật.
- Event kết quả đến sau khi saga đã hủy được xử lý theo chính sách event đến muộn.

Nên kiểm thử process manager bằng repository và command port giả lập ở unit test, sau đó dùng integration test với cơ chế lưu trữ publication và messaging thực tế để kiểm tra ranh giới giao tiếp. Có thể dùng test fixture mô tả chuỗi event đầu vào và trạng thái saga mong đợi sau mỗi bước.

## 13. Quan sát và vận hành saga

Một saga có thể kéo dài từ vài giây đến nhiều giờ hoặc ngày. Dashboard cần hiển thị được số saga đang chạy, bước chờ lâu nhất, tỷ lệ hoàn tất, tỷ lệ compensation và số saga cần can thiệp.

Các chỉ số hữu ích:

- Số saga theo trạng thái.
- Tuổi của saga và tuổi của bước đang chờ.
- Số timeout theo loại bước.
- Tỷ lệ thành công/thất bại của từng participant.
- Số compensation thành công và thất bại.
- Số event duplicate, stale hoặc unexpected.
- Số saga ở trạng thái NEEDS_ATTENTION.

Log nên có sagaId, businessId, eventId, eventType, currentState, nextAction, participant, correlationId và thời điểm chuyển trạng thái. Không ghi payload nhạy cảm hoặc dữ liệu bí mật vào log.

Cần có thao tác vận hành được kiểm soát để xem lịch sử, retry một bước, yêu cầu compensation hoặc đóng saga thủ công. Các thao tác này phải ghi người thực hiện, thời điểm, lý do và kết quả. Không chỉnh trực tiếp state trong database mà không có audit và quy trình phục hồi.

## 14. Lỗi thiết kế thường gặp

**Dùng một transaction cho toàn bộ quy trình phân tán.** Transaction không thể tự rollback các hệ thống độc lập. Hãy chia thành local transaction và định nghĩa compensation.

**Coi compensation là rollback.** Compensation là hành động nghiệp vụ mới, có thể thất bại hoặc không thể đảo ngược hoàn toàn. Hãy theo dõi kết quả riêng.

**Không lưu saga state bền vững.** Restart có thể làm mất quy trình đang chờ. Hãy lưu trạng thái, deadline và lịch sử chuyển trạng thái.

**Dùng choreography cho quy trình có quá nhiều nhánh mà không có tài liệu.** Luồng event trở nên khó hiểu. Hãy cân nhắc process manager khi cần điều phối tập trung.

**Để process manager sở hữu dữ liệu của participant.** Coordinator trở thành nơi chứa nghiệp vụ của nhiều module. Hãy yêu cầu participant thực hiện hành động qua module API hoặc command và trả event kết quả.

**Không có idempotency.** Event giao trùng có thể giữ tồn kho hoặc thu tiền nhiều lần. Hãy dùng event ID, sagaId và unique constraint phù hợp.

**Không xử lý timeout và event đến muộn.** Quy trình có thể chờ vô hạn hoặc compensation nhầm bước đã thành công. Hãy lưu deadline và kiểm tra trạng thái participant trước hành động không thể đảo ngược.

**Coi Event Publication Registry là saga engine.** Registry theo dõi việc giao publication; process manager phải tự quản lý state machine, compensation, timeout và quy tắc nghiệp vụ.

## Kết luận

Saga là cách tổ chức một quy trình nghiệp vụ nhiều bước bằng các local transaction độc lập và hành động compensation khi không thể tiếp tục. Choreography phân tán việc điều khiển qua event; orchestration dùng process manager lưu trạng thái và quyết định bước tiếp theo.

Trong Spring Modulith, application events và Event Publication Registry cung cấp nền tảng giao tiếp giữa module và phục hồi publication. Ứng dụng vẫn cần xây dựng saga state bền vững, idempotency, timeout, compensation, kiểm soát đồng thời và quan sát vận hành. Khi mỗi module giữ quyền sở hữu nghiệp vụ của mình và process manager chỉ điều phối tiến trình, quy trình nhiều bước có thể phục hồi rõ ràng mà không phá vỡ ranh giới module.

