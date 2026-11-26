# Invariant liên module

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module trao đổi kết quả nghiệp vụ mà không cần gọi trực tiếp implementation của nhau. Khi một quy tắc nghiệp vụ liên quan đến nhiều module, thách thức lớn nhất là giữ cho toàn hệ thống ở trạng thái hợp lệ dù mỗi module có dữ liệu, transaction và vòng đời triển khai riêng.

**Invariant liên module** là điều kiện nghiệp vụ phải đúng khi xét dữ liệu thuộc từ hai module trở lên. Ví dụ: số lượng hàng đã giữ không được vượt quá tồn kho có thể bán; một đơn hàng chỉ được giao sau khi thanh toán được xác nhận; tổng số tiền hoàn không được vượt quá số tiền đã thu. Application events giúp truyền kết quả và kích hoạt bước tiếp theo, nhưng bản thân event không tạo ra một transaction nguyên tử xuyên qua các module.

Muốn bảo vệ invariant, trước hết phải xác định module nào có quyền quyết định điều kiện đó. Sau đó chọn cơ chế phù hợp: transaction cục bộ tại nơi sở hữu dữ liệu, reservation, command có kiểm soát, saga/process manager, outbox/inbox, hoặc một quy trình đối soát. Thiết kế tốt làm rõ trạng thái tạm thời nào được phép tồn tại, trạng thái cuối cùng nào phải đạt và cách phục hồi khi một bước thất bại.

## 1. Invariant là gì và vì sao ranh giới module quan trọng?

Invariant là điều kiện luôn phải được giữ đúng trong phạm vi mà nghiệp vụ quy định. Trong một aggregate, ví dụ số lượng đặt hàng phải lớn hơn 0 hoặc số dư không được âm, invariant có thể được kiểm tra và bảo vệ trong một transaction của module sở hữu aggregate.

Khi dữ liệu trải qua nhiều module, một transaction cơ sở dữ liệu thông thường không thể tự động bảo đảm tất cả thay đổi cùng commit. Giả sử module Order tạo đơn, module Inventory giữ hàng và module Payment thu tiền. Mỗi module có thể commit thành công hoặc thất bại độc lập. Nếu Order đã lưu đơn nhưng Inventory chưa giữ được hàng, hệ thống có thể tạm thời có một đơn hàng chưa đủ điều kiện xử lý tiếp.

Cần phân biệt hai loại điều kiện:

- **Invariant cục bộ:** phải đúng ngay trong transaction của module sở hữu dữ liệu. Ví dụ, một dòng tồn kho không được giảm xuống số âm.
- **Invariant liên module:** liên quan tới nhiều module và có thể cần một quy trình phối hợp để đạt trạng thái cuối cùng. Ví dụ, đơn hàng chỉ được hoàn tất khi hàng đã được giữ và thanh toán đã được xác nhận.

Không phải mọi trạng thái tạm thời đều là lỗi. Một đơn hàng ở trạng thái PENDING_PAYMENT có thể hợp lệ trong thời gian chờ cổng thanh toán. Điều cần xác định là trạng thái tạm thời nào được nghiệp vụ cho phép, thời gian chờ tối đa bao lâu và điều gì phải xảy ra nếu quy trình không thể tiếp tục.

## 2. Xác định module sở hữu invariant

Mỗi dữ liệu nghiệp vụ cần một module sở hữu có quyền thay đổi và áp dụng quy tắc của dữ liệu đó. Module khác có thể yêu cầu một hành động hoặc nhận event kết quả, nhưng không nên tự ghi trực tiếp vào kho dữ liệu nội bộ của module sở hữu.

Ví dụ:

| Invariant | Module sở hữu quyết định | Module khác tương tác bằng |
|---|---|---|
| Tồn kho khả dụng không âm | Inventory | ReserveInventory command, InventoryReserved event |
| Thanh toán không bị thu trùng | Payment | CapturePayment command, PaymentCaptured event |
| Đơn chỉ hoàn tất khi đủ điều kiện | Order hoặc Order Process Manager | Các event kết quả từ Inventory, Payment, Shipping |
| Số tiền hoàn không vượt số tiền đã thu | Payment | RefundPayment command, PaymentRefunded event |
| Giới hạn tín dụng của khách hàng | Credit | AuthorizeCredit command, CreditAuthorized event |

Module sở hữu invariant phải kiểm tra điều kiện tại thời điểm ghi dữ liệu, trong transaction của chính nó. Không nên chỉ kiểm tra ở module gọi trước khi gửi command, vì trạng thái có thể thay đổi giữa thời điểm kiểm tra và thời điểm module đích thực hiện hành động.

Ví dụ, Order đọc thấy còn 2 sản phẩm trong kho rồi mới gửi yêu cầu giữ 2 sản phẩm. Trong lúc đó một đơn khác có thể giữ hết số lượng. Inventory phải kiểm tra lại và cập nhật tồn kho một cách nguyên tử khi nhận command.

Process manager điều phối quy trình tổng thể nhưng không sở hữu mọi invariant cục bộ. Nó quyết định bước nào được phép tiếp tục dựa trên kết quả nhận được; Inventory vẫn chịu trách nhiệm ngăn giữ hàng vượt tồn, Payment vẫn chịu trách nhiệm ngăn thu tiền trùng.

## 3. Phân biệt strong consistency và eventual consistency

Strong consistency có nghĩa là các lần đọc quan sát được trạng thái đã commit theo mô hình nhất quán mà hệ thống cam kết. Với một transaction trong một cơ sở dữ liệu, có thể dùng constraint, khóa hoặc cập nhật có điều kiện để bảo vệ invariant cục bộ.

Eventual consistency cho phép các bản sao hoặc module liên quan cập nhật ở những thời điểm khác nhau. Sau khi các message được xử lý thành công và không còn lỗi chưa giải quyết, các phần dữ liệu liên quan sẽ hội tụ về trạng thái nhất quán theo quy tắc nghiệp vụ.

| Tiêu chí | Strong consistency trong boundary sở hữu | Eventual consistency qua module |
|---|---|---|
| Phạm vi bảo đảm | Một transaction hoặc một cơ chế phối hợp đồng bộ | Nhiều transaction độc lập |
| Khả năng quan sát trạng thái tạm thời | Hạn chế theo transaction | Có thể thấy trạng thái đang chờ hoặc chưa đồng bộ |
| Độ trễ | Thường phụ thuộc transaction hiện tại | Có thể có độ trễ event, queue và retry |
| Xử lý lỗi | Rollback transaction cục bộ | Retry, timeout, compensation và reconciliation |
| Phù hợp | Invariant không được phép vi phạm tại điểm ghi | Quy trình chấp nhận trạng thái trung gian có kiểm soát |

Eventual consistency không có nghĩa là bỏ qua invariant. Nó có nghĩa là thiết kế quy trình để invariant liên module được bảo vệ trong toàn bộ vòng đời, bao gồm trạng thái tạm thời và cách xử lý thất bại.

Nếu nghiệp vụ không cho phép bất kỳ khoảng thời gian nào mà điều kiện bị vi phạm, hãy đặt quyền quyết định tại một boundary có thể bảo vệ điều kiện nguyên tử. Có thể cần một module sở hữu duy nhất, một transaction coordinator hoặc một thao tác đồng bộ có kiểm soát. Đừng giả định phát event rồi chờ các module tự cập nhật sẽ tạo ra strong consistency.

## 4. Phân loại invariant theo mức độ nghiêm ngặt

Trước khi chọn kiến trúc, hãy hỏi điều gì xảy ra nếu điều kiện tạm thời không đúng.

**Invariant an toàn tuyệt đối:** vi phạm gây mất tiền, oversell, cấp quyền trái phép hoặc ghi nhận nghiệp vụ không thể đảo ngược. Điều kiện phải được kiểm tra tại module sở hữu trước khi commit tác dụng phụ. Ví dụ, Inventory không được xác nhận giữ hàng nếu số lượng khả dụng không đủ.

**Invariant cần hội tụ:** hệ thống có thể hiển thị trạng thái PENDING hoặc PROCESSING trong một khoảng thời gian. Ví dụ, Order chờ PaymentCaptured trước khi chuyển sang PAID. Saga có thể điều phối và bù trừ nếu bước thanh toán bị từ chối.

**Invariant mang tính chính sách hoặc giới hạn mềm:** hệ thống có thể chấp nhận sai lệch ngắn hạn nhưng cần phát hiện và điều chỉnh. Ví dụ, dashboard tổng hợp số lượng đơn theo module có thể cập nhật trễ vài giây. Đây thường là read model hoặc projection, không phải nguồn quyết định nghiệp vụ.

Đừng dùng cùng một chiến lược cho mọi invariant. Một dashboard chậm cập nhật có thể chấp nhận eventual consistency; số dư tài khoản hoặc tồn kho được xác nhận bán thì cần kiểm soát chặt hơn.

## 5. Ví dụ: bảo vệ invariant tồn kho không âm

Giả sử Inventory quản lý số lượng có thể bán của từng SKU. Hai đơn hàng đồng thời cùng yêu cầu giữ 4 sản phẩm trong khi chỉ còn 5. Nếu cả hai transaction đều đọc giá trị 5 trước khi ghi, một cách triển khai đọc rồi ghi thiếu kiểm soát có thể giữ tổng cộng 8 sản phẩm.

Hãy bảo vệ điều kiện ngay trong module Inventory bằng cập nhật có điều kiện:

~~~sql
UPDATE inventory_item
SET available_quantity = available_quantity - :quantity,
    version = version + 1
WHERE sku = :sku
  AND available_quantity >= :quantity;
~~~

Sau câu lệnh, kiểm tra số dòng được cập nhật:

- Một dòng được cập nhật: thao tác giữ hàng thành công.
- Không có dòng nào được cập nhật: SKU không tồn tại hoặc lượng khả dụng không đủ; module cần phân biệt hai trường hợp theo nghiệp vụ.

Điều kiện số lượng và phép trừ nằm trong cùng câu lệnh SQL nên hai yêu cầu đồng thời không thể cùng sử dụng một lượng hàng vượt quá số có sẵn. Cách khác là optimistic locking với version hoặc khóa hàng phù hợp; lựa chọn phụ thuộc cơ sở dữ liệu và mô hình truy cập.

Không nên để Order tự đọc bảng inventory rồi quyết định trừ số lượng. Làm vậy vừa vi phạm module boundary vừa tạo race condition vì Order không kiểm soát được những transaction khác đang cập nhật tồn kho.

## 6. Reservation thay vì giữ tài nguyên quá sớm

Với quy trình kéo dài, không nên giữ tài nguyên bằng một transaction database mở trong suốt thời gian chờ Payment hoặc Shipping. Thay vào đó, module sở hữu tài nguyên có thể tạo reservation có thời hạn.

Một reservation thường có:

- reservationId duy nhất;
- business key như orderId;
- SKU và số lượng;
- trạng thái RESERVED, CONFIRMED, RELEASED hoặc EXPIRED;
- thời điểm tạo và thời hạn hết hiệu lực;
- commandId hoặc idempotency key dùng để chống thao tác lặp.

Ví dụ luồng:

~~~mermaid
sequenceDiagram
    participant O as Order process manager
    participant I as Inventory
    participant P as Payment
    O->>I: ReserveInventory command
    I->>I: Kiểm tra và giữ số lượng trong transaction
    I-->>O: InventoryReserved event
    O->>P: CapturePayment command
    P-->>O: PaymentCaptured event
    O->>I: ConfirmReservation command
    I->>I: Chuyển reservation sang CONFIRMED
    I-->>O: ReservationConfirmed event
~~~

Nếu Payment bị từ chối hoặc timeout không thể phục hồi, process manager có thể gửi ReleaseReservation command. Nếu process manager không gửi được lệnh xác nhận hoặc giải phóng, reservation hết hạn theo chính sách của Inventory và được giải phóng bằng một tác vụ định kỳ.

Reservation cần được quản lý tại module sở hữu tài nguyên. Order chỉ biết reservationId và trạng thái được công bố qua event. Không để Order tự cập nhật bảng reservation của Inventory.

## 7. Saga và process manager điều phối invariant liên module

Saga chia một quy trình lớn thành các transaction cục bộ. Mỗi module thực hiện một bước và phát event kết quả. Process manager đọc event, kiểm tra trạng thái saga và phát command kế tiếp.

Ví dụ đặt hàng:

1. Order nhận yêu cầu và tạo đơn ở trạng thái PENDING.
2. Process manager phát ReserveInventory command.
3. Inventory kiểm tra tồn kho và phát InventoryReserved hoặc InventoryRejected.
4. Khi hàng đã được giữ, process manager phát CapturePayment command.
5. Payment phát PaymentCaptured hoặc PaymentDeclined.
6. Khi thanh toán thành công, process manager yêu cầu xác nhận reservation và tạo shipment.
7. Khi các điều kiện cuối cùng được xác nhận, Order chuyển sang trạng thái hoàn tất.
8. Nếu một bước thất bại, process manager điều phối các hành động bù trừ phù hợp.

~~~mermaid
flowchart TD
    A["Order PENDING"] --> B["Reserve inventory"]
    B --> C{"Inventory result"}
    C -->|Reserved| D["Capture payment"]
    C -->|Rejected| X["Reject order"]
    D --> E{"Payment result"}
    E -->|Captured| F["Confirm reservation / arrange shipment"]
    E -->|Declined| G["Release reservation"]
    F --> H{"Fulfillment result"}
    H -->|Success| I["Order COMPLETED"]
    H -->|Failure| J["Refund payment"]
    J --> G
~~~

Saga không rollback các transaction đã commit ở module khác. Compensation là hành động nghiệp vụ mới, ví dụ hoàn tiền hoặc giải phóng reservation. Compensation có thể thất bại và cũng cần retry, idempotency, timeout cùng quy trình xử lý thủ công.

Không nên đánh dấu Order COMPLETED ngay khi gửi command cuối cùng. Hãy chờ event xác nhận từ module chịu trách nhiệm. Trong thời gian chờ, trạng thái saga phải thể hiện rõ đang chờ bước nào.

## 8. Phát event bền vững bằng transactional outbox

Một rủi ro phổ biến là module cập nhật dữ liệu thành công nhưng event không được gửi. Ví dụ Inventory đã trừ số lượng khả dụng nhưng process dừng trước khi phát InventoryReserved. Process manager không biết hàng đã được giữ và có thể timeout hoặc phát yêu cầu khác.

Transactional outbox giúp ghi thay đổi nghiệp vụ và event cần công bố trong cùng transaction của module sở hữu:

~~~sql
BEGIN;

UPDATE inventory_item
SET available_quantity = available_quantity - :quantity
WHERE sku = :sku
  AND available_quantity >= :quantity;

INSERT INTO inventory_reservation (
    reservation_id,
    order_id,
    sku,
    quantity,
    status
) VALUES (
    :reservation_id,
    :order_id,
    :sku,
    :quantity,
    'RESERVED'
);

INSERT INTO event_outbox (
    event_id,
    event_type,
    aggregate_id,
    payload,
    created_at
) VALUES (
    :event_id,
    'InventoryReserved',
    :order_id,
    :payload,
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Đây là ví dụ cấu trúc minh họa; ứng dụng phải kiểm tra số dòng được cập nhật trước khi tạo reservation và outbox. Tất cả thao tác thuộc cùng transaction. Nếu invariant không thỏa mãn, transaction không tạo reservation thành công và không phát InventoryReserved.

Dispatcher đọc outbox và gửi event sau commit. Khi gửi thành công theo cơ chế xác nhận của transport, dispatcher đánh dấu bản ghi đã gửi. Nếu process dừng sau khi broker nhận event nhưng trước khi bản ghi được đánh dấu, event có thể được gửi lại. Vì vậy consumer vẫn cần idempotent.

Trong Spring Modulith, Event Publication Registry theo dõi publication tới transactional listeners. Registry hỗ trợ phát hiện publication chưa hoàn tất và phục hồi theo cấu hình persistence. Nó có vai trò riêng với transactional outbox của integration messaging; cần xác định adapter và cơ chế lưu publication đang dùng để tránh nhầm trạng thái registry với việc consumer bên ngoài đã hoàn thành nghiệp vụ.

## 9. Inbox và chống xử lý trùng

Event hoặc command có thể được giao lại do retry, broker redelivery, process restart hoặc mất acknowledgement. Nếu consumer xử lý cùng event nhiều lần mà không chống trùng, tác dụng phụ có thể lặp: giữ hàng hai lần, gửi hai lệnh thu tiền hoặc tạo nhiều shipment.

Inbox lưu định danh message đã được xử lý. Một bảng đơn giản:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    message_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Trong cùng transaction, consumer ghi messageId vào inbox và cập nhật dữ liệu nghiệp vụ. Unique constraint ngăn hai lần xử lý cùng message cho cùng consumer. Nếu bản ghi đã tồn tại, consumer nhận diện duplicate và không thực hiện lại tác dụng phụ.

Đối với command, có thể dùng commandId làm khóa idempotency. Đối với event, dùng eventId. Không tạo ID mới cho mỗi lần retry cùng một thông điệp.

Nếu consumer gọi API ngoài database transaction, inbox không đủ để bảo vệ tác dụng phụ bên ngoài. Hãy truyền idempotency key nếu API hỗ trợ, lưu trạng thái thao tác và đối soát kết quả khi timeout. Ví dụ cổng thanh toán đã thu tiền nhưng phản hồi bị mất; trước khi gửi capture mới, Payment phải truy vấn trạng thái giao dịch theo khóa idempotency.

## 10. Kiểm soát race condition và cập nhật đồng thời

Invariant liên module thường bị phá vỡ bởi các thao tác đồng thời hơn là bởi luồng xử lý tuần tự. Hai event có thể đến cùng lúc, hai instance process manager có thể đọc cùng trạng thái saga hoặc một command cũ có thể được xử lý sau khi quy trình đã chuyển bước.

Các cơ chế thường dùng:

- **Optimistic locking:** dùng version để phát hiện hai transaction cùng sửa một saga hoặc aggregate.
- **Pessimistic locking:** khóa bản ghi khi cần tuần tự hóa thao tác trong phạm vi nhỏ.
- **Unique constraint:** bảo vệ business key hoặc idempotency key khỏi bản ghi trùng.
- **Conditional update:** đưa điều kiện invariant vào câu lệnh cập nhật.
- **Sequence/version trong event:** giúp consumer bỏ qua hoặc cách ly event cũ.
- **Single writer:** định tuyến mọi thay đổi của một aggregate tới một owner xử lý tuần tự khi nghiệp vụ yêu cầu.

Ví dụ optimistic locking cho trạng thái saga:

~~~sql
UPDATE order_saga
SET state = :next_state,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE saga_id = :saga_id
  AND version = :expected_version;
~~~

Nếu không có dòng nào được cập nhật, một transaction khác đã thay đổi saga hoặc version không còn phù hợp. Process manager phải đọc lại trạng thái và đánh giá event theo state mới, thay vì phát command dựa trên dữ liệu cũ.

Không nên dùng distributed lock như lựa chọn mặc định cho mọi invariant. Khóa phân tán có thêm timeout, lease, failure mode và chi phí vận hành. Nếu có thể bảo vệ invariant bằng transaction hoặc constraint trong module sở hữu, cách đó thường đơn giản và đáng tin cậy hơn.

## 11. Read model và dữ liệu hiển thị chưa đồng bộ

Một module có thể xây dựng read model từ event của nhiều module để phục vụ truy vấn. Ví dụ Order Summary hiển thị trạng thái đơn, thanh toán và giao hàng. Projection có thể cập nhật chậm hơn nguồn dữ liệu vì event cần thời gian được publish và xử lý.

Read model phục vụ quan sát và truy vấn; nó không nên tự trở thành nguồn quyết định cho invariant nếu dữ liệu có thể stale. Nếu người dùng bấm thanh toán dựa trên trạng thái hiển thị cũ, module Payment vẫn phải kiểm tra trạng thái giao dịch thực tế. Nếu UI hiển thị còn hàng, Inventory vẫn phải kiểm tra lại tồn kho tại thời điểm reserve.

Nên thể hiện trạng thái chưa đồng bộ một cách rõ ràng, chẳng hạn PENDING, PROCESSING hoặc LAST_UPDATED_AT. Với nghiệp vụ cần xác nhận mới nhất, cung cấp một thao tác truy vấn trạng thái từ module sở hữu hoặc một command kiểm tra có correlation ID.

Không nên để một projection tổng hợp ghi ngược vào các module nguồn. Projection có thể được xây dựng lại từ event hoặc dữ liệu nguồn; quyền thay đổi nghiệp vụ vẫn thuộc module sở hữu.

## 12. Timeout, retry và compensation

Mỗi bước liên module cần có timeout nghiệp vụ. Timeout không đồng nghĩa bước đó chắc chắn thất bại; đôi khi handler đã thực hiện thành công nhưng event phản hồi bị chậm hoặc mất. Trước khi phát command mới, process manager cần xác định trạng thái của bước đang chờ.

Một chính sách xử lý có thể gồm:

1. Retry cùng commandId nếu lỗi được xác định là tạm thời và handler idempotent.
2. Query trạng thái module sở hữu nếu kết quả lần trước không rõ.
3. Chuyển sang compensation khi nghiệp vụ không thể tiếp tục.
4. Chuyển sang manual review nếu không thể xác định trạng thái an toàn.
5. Ghi lại event, command, attempt, deadline và kết quả để điều tra.

Compensation cần được thiết kế như một quy trình độc lập. Ví dụ, khi không thể giao hàng sau khi Payment đã capture, process manager yêu cầu refund. Nếu refund thành công, tiếp tục giải phóng reservation; nếu refund thất bại, giữ saga ở trạng thái COMPENSATING và retry hoặc chuyển manual review.

Không nên xóa event hoặc publication chưa hoàn tất chỉ để dọn backlog. Trước khi replay, phải kiểm tra event còn hợp lệ, tác dụng phụ có idempotent và module nhận đã sẵn sàng.

## 13. Reconciliation để phát hiện sai lệch kéo dài

Retry không giải quyết mọi sai lệch. Message có thể bị cấu hình sai, dữ liệu cũ có thể được nhập ngoài luồng hoặc một bug có thể làm quy trình bỏ qua event. Reconciliation là quá trình so sánh trạng thái giữa các module hoặc với hệ thống đối soát để phát hiện và xử lý chênh lệch.

Ví dụ các phép đối soát:

- Order đang chờ Payment quá thời hạn nhưng không có pending command hợp lệ.
- Payment đã capture nhưng Order vẫn ở trạng thái PENDING_PAYMENT.
- Reservation đã hết hạn nhưng Order vẫn nghĩ hàng đang được giữ.
- Số tiền refund tích lũy lớn hơn số tiền đã capture.
- Outbox có bản ghi cũ chưa gửi hoặc consumer inbox có message bị kẹt.

Reconciliation nên đọc dữ liệu qua API, event projection hoặc báo cáo được công bố bởi module sở hữu. Nếu phát hiện sai lệch, ghi lại mã đối soát, thời điểm, hai trạng thái quan sát được và hành động đề xuất. Chỉ phát command sửa trạng thái sau khi xác định rõ quy tắc nghiệp vụ và idempotency của hành động đó.

Không tự động sửa mọi chênh lệch bằng cách ghi trực tiếp vào database của module khác. Reconciliation phát hiện và điều phối xử lý; module sở hữu vẫn thực hiện thay đổi và phát event kết quả.

## 14. Quan sát invariant và quy trình liên module

Muốn biết invariant có đang được bảo vệ, cần theo dõi cả trạng thái cục bộ và tiến trình liên module.

Các tín hiệu nên có:

- Số saga theo từng state và tuổi saga lâu nhất.
- Số reservation đang RESERVED, CONFIRMED, RELEASED và EXPIRED.
- Số command pending, retry và vượt giới hạn.
- Outbox backlog và tuổi bản ghi chưa gửi lâu nhất.
- Incomplete publications trong Event Publication Registry.
- Số duplicate event/command bị loại bỏ.
- Số late event hoặc event sai thứ tự.
- Số compensation thất bại và reconciliation mismatch.
- Thời gian từ command đến result event.

Log có cấu trúc nên chứa sagaId, eventId, commandId, aggregateId, correlationId, state trước/sau và lý do chuyển trạng thái. Không đưa các định danh có cardinality cao vào metric tag; dùng log và trace để truy vấn chi tiết. Không ghi payload nhạy cảm vào log.

Cảnh báo nên gắn với deadline nghiệp vụ và mức độ rủi ro. Ví dụ, một reservation sắp hết hạn trong khi thanh toán chưa có kết quả cần được theo dõi khác với một read model chậm cập nhật vài giây.

## 15. Kiểm thử invariant liên module

Kiểm thử cần chứng minh invariant được giữ trong cả trường hợp bình thường, cạnh tranh và lỗi. Unit test cho từng module không đủ để chứng minh toàn bộ quy trình liên module hoạt động đúng.

Các kịch bản nên có:

1. **Inventory concurrent reserve:** hai yêu cầu đồng thời không thể giữ tổng số lượng vượt tồn kho.
2. **Payment duplicate command:** cùng commandId không thu tiền hai lần.
3. **Outbox atomicity:** transaction rollback thì không có event công bố cho thay đổi chưa commit.
4. **Publish retry:** event gửi lại không tạo tác dụng phụ lặp ở consumer.
5. **Saga happy path:** các result event dẫn đến đúng command và trạng thái cuối.
6. **Step rejection:** một module từ chối thì process manager phát đúng command bù trừ.
7. **Timeout ambiguity:** kết quả đến trễ không làm process manager phát hành động mâu thuẫn.
8. **Compensation failure:** saga giữ trạng thái rõ ràng và có thể tiếp tục sau retry hoặc manual review.
9. **Out-of-order event:** event sai thứ tự không làm invariant bị phá vỡ.
10. **Restart recovery:** outbox, inbox, publication và saga state tiếp tục được xử lý sau restart.
11. **Read model lag:** thao tác ghi vẫn kiểm tra invariant tại module sở hữu dù projection chưa cập nhật.
12. **Reconciliation:** phát hiện được một trạng thái lệch được tạo có chủ đích trong test.

Với Spring Modulith, có thể kiểm tra module boundary để bảo đảm module không phụ thuộc vào implementation nội bộ của module khác. Kiểm thử tích hợp nên xác nhận transaction, listener, Event Publication Registry và adapter hoạt động theo cấu hình thực tế. Với các invariant cần concurrency, dùng database và transaction thật trong môi trường kiểm thử phù hợp; mock repository không thể chứng minh khóa hoặc conditional update có hiệu lực.

## 16. Quy trình thiết kế invariant liên module

Khi bắt đầu một quy trình có nhiều module, hãy đi theo trình tự:

1. Liệt kê điều kiện nghiệp vụ phải đúng và phân loại invariant cục bộ, liên module, nghiêm ngặt hoặc có thể hội tụ.
2. Chỉ định module sở hữu từng dữ liệu và quyền quyết định invariant.
3. Xác định trạng thái trung gian được phép, deadline và trạng thái cuối mong muốn.
4. Thiết kế event mô tả kết quả và command yêu cầu hành động; mỗi message có ID ổn định.
5. Bảo vệ invariant cục bộ bằng transaction, constraint, conditional update hoặc locking tại module sở hữu.
6. Dùng reservation nếu cần giữ tài nguyên trong khi chờ các bước khác.
7. Dùng saga/process manager để điều phối command kế tiếp và compensation.
8. Ghi state transition cùng outbox trong transaction; dùng inbox để chống xử lý trùng.
9. Xác định timeout, retry, late event, reconciliation và quy trình manual review.
10. Theo dõi backlog, tuổi saga, reservation, compensation và sai lệch.
11. Kiểm thử concurrency, crash, redelivery, restart và các nhánh thất bại.

Invariant liên module được bảo vệ khi mỗi module giữ quyền kiểm soát dữ liệu của mình và process manager điều phối các kết quả qua hợp đồng rõ ràng. Transaction cục bộ bảo vệ điều kiện tại nơi sở hữu; reservation giữ tài nguyên có thời hạn; outbox/inbox giúp giao nhận có thể phục hồi; saga và compensation đưa quy trình tới trạng thái cuối hợp lệ. Khi bổ sung timeout, reconciliation, observability và kiểm thử lỗi, hệ thống có thể chấp nhận độ trễ giữa các module mà vẫn kiểm soát được tính đúng đắn của nghiệp vụ.

