# Thiết kế hành động bù trừ theo ý nghĩa nghiệp vụ trong giao dịch phân tán

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Giao dịch phân tán.
>
> **Mục tiêu học tập:** hiểu compensating action trong Saga, phân biệt bù trừ nghiệp vụ với rollback transaction, thiết kế hành động bù cho các bước đã commit ở nhiều service, bảo vệ invariant, xử lý hành động không thể đảo ngược, tránh bù trùng và có cơ chế retry, đối soát, điều tra khi kết quả không chắc chắn.

## 1. Vì sao có hành động bù trừ?

Trong một database transaction cục bộ, hệ quản trị dữ liệu có thể rollback những thay đổi chưa commit. Nhưng trong microservices, mỗi service thường sở hữu database và transaction riêng:

~~~text
Order Service       -> tạo đơn PENDING
Inventory Service   -> reserve stock
Payment Service     -> authorize/capture tiền
Shipping Service    -> tạo vận đơn
Notification        -> gửi xác nhận
~~~

Giả sử Inventory đã reserve thành công và Payment đã capture tiền. Sau đó Shipping từ chối vận chuyển. Nếu Order chạy ROLLBACK trên database của mình, transaction tại Inventory và Payment đã commit **không tự quay về trạng thái ban đầu**. Một rollback thông thường không đi qua ranh giới của nhiều database, mạng và dịch vụ bên ngoài.

Saga giải quyết bài toán phối hợp bằng một chuỗi các **transaction cục bộ**. Khi toàn quy trình không thể hoàn tất theo nhánh thành công, hệ tiến hành một hoặc nhiều **compensating actions** có ý nghĩa nghiệp vụ:

- ReleaseReservation để giải phóng hàng đã giữ.
- VoidAuthorization khi tiền mới được ủy quyền nhưng chưa capture.
- RefundCapture khi đã thực sự thu tiền.
- CancelShipment nếu bên vận chuyển chưa bắt đầu xử lý.
- RequestReturn nếu hàng đã rời kho, không thể xóa sự kiện vận chuyển.
- SendCorrection nếu thông báo trước đó đã đến khách.

**Compensation không phải “undo bằng SQL” hay một phép đảo mọi side effect.** Nó là một hành động mới, thực hiện trong transaction của owner có thẩm quyền, nhằm đưa nghiệp vụ đến một trạng thái cuối được chấp nhận.

### 1.1. Ví dụ sơ đồ

~~~text
Saga checkout:
    T1: Order.CreatePending
     |
    T2: Inventory.ReserveStock
     |
    T3: Payment.Authorize
     |
    T4: Shipping.CreateBooking  ----> FAILED
                                      |
Bù theo business logic:               |
    C3: Payment.VoidAuthorization <---+
     |
    C2: Inventory.ReleaseReservation
     |
    C1: Order.MarkCancelled
~~~

Không phải cứ đảo số thứ tự từ T4 về T1 là luôn đúng. Thứ tự compensation phụ thuộc vào những bước thực sự đã hoàn tất và quan hệ nghiệp vụ giữa chúng. Có những bước bù có thể song song, nhưng cũng có những bước phải chờ kết quả của bước khác.

## 2. Rollback kỹ thuật khác bù trừ nghiệp vụ ra sao?

| Tiêu chí | Rollback transaction cục bộ | Bù trừ trong Saga |
| --- | --- | --- |
| Phạm vi | Dữ liệu thuộc một transaction trước commit | Những bước đã commit trong nhiều owner |
| Cơ chế | DB engine khôi phục transaction | Lệnh nghiệp vụ mới |
| Tính nguyên tử | Có trong transaction boundary | Không mặc định atomic trên toàn Saga |
| Lịch sử | Thay đổi chưa commit không trở thành kết quả chính thức | Bước gốc và bước bù đều có thể được audit |
| Tốc độ | Thường cùng phiên xử lý | Có thể kéo dài giây, phút hoặc ngày |
| Thất bại của bước đảo | DB engine hỗ trợ trong phạm vi cục bộ | Compensation có thể timeout, bị từ chối, cần retry |
| Side effect ngoài DB | Không thể rollback tác động bên ngoài | Cần void, refund, return, correction hoặc xử lý thủ công |
| Trạng thái cuối | Như chưa commit transaction | Nhất quán nghiệp vụ, không nhất thiết trùng snapshot cũ |

Ví dụ một giao dịch thanh toán capture 500.000 VND rồi refund 500.000 VND. Kết quả tiền ròng có thể trở về 0, nhưng ledger có cả capture và refund; phí gateway có thể vẫn tồn tại, thời gian settlement có thể khác và lịch sử không thể bị xóa vì yêu cầu kiểm toán.

Ví dụ Inventory ban đầu có 10 đơn vị, reserve 2 cho đơn A, sau đó reserve 3 cho đơn B. Nếu đơn A hủy, không được đặt quantity về số 10 cũ vì như vậy làm mất reservation của B. Phải release **đúng reservation ID của A** và để Inventory tính trạng thái hiện tại theo invariant của nó.

## 3. Mục tiêu: business consistency, không phải byte-for-byte restoration

Thiết kế bù trừ nên hỏi:

1. Người dùng cuối có cam kết gì?
2. Dữ liệu hoặc tài sản nào đã bị giữ, chuyển quyền, thu tiền, công bố hoặc tiêu thụ?
3. Trạng thái nào phải được ngăn không cho xảy ra sau khi hủy?
4. Bước gốc đã commit chắc chắn chưa?
5. Cần hành động nào để nghiệp vụ đạt một kết quả hợp lệ?
6. Có chi phí, lệ phí, nghĩa vụ pháp lý hoặc thông báo đi kèm không?
7. Ai là service có thẩm quyền thực hiện hành động đó?

Một đơn có thể kết thúc ở trạng thái CANCELLED với reservation RELEASED và refund REFUNDED. Nhưng Payment vẫn giữ lịch sử capture và refund; Shipping vẫn giữ lịch sử đặt/hủy; Notification có thể giữ bản ghi thông báo đã gửi. Đó có thể là **nhất quán nghiệp vụ đúng đắn** dù không quay lại chính xác trạng thái vật lý trước khi Saga bắt đầu.

### 3.1. Invariant trước khi chọn command

Một số invariant:

- Inventory không được xác nhận reservation vượt lượng hàng khả dụng theo policy.
- Không cho cùng ý định refund sinh ra nhiều khoản hoàn tiền.
- Không xác nhận Order thành công khi chưa có bằng chứng về các điều kiện bắt buộc.
- Không hủy quyền vào cửa của vé đã được sử dụng bằng một lệnh revoke vô hiệu.
- Không chuyển Shipment thành CANCELLED chỉ vì đã gửi yêu cầu cancel mà chưa có phản hồi.
- Không cho event cũ đưa một Saga đã CANCELLED trở lại CONFIRMED trái state machine.
- Mọi correction có bằng chứng audit và owner phù hợp.

Compensation phải tôn trọng invariant của **service đang sở hữu resource**, không để coordinator tự UPDATE các bảng thuộc service khác.

## 4. Phân loại bước tiến trước khi thiết kế compensation

### 4.1. Bước compensatable

Các bước có thể được bù một cách có nghĩa khi resource vẫn ở trạng thái phù hợp:

- HoldSeat → ReleaseSeatHold.
- ReserveStock → ReleaseReservation.
- AuthorizePayment → VoidAuthorization nếu chưa capture và provider cho phép.
- ReserveShippingSlot → CancelBooking nếu hãng chưa xử lý.
- CreateDraftDocument → VoidDraft nếu chưa phát hành chính thức.

Hành động bù không nhất thiết thành công ở mọi thời điểm. ReserveStock có thể đã chuyển sang CONSUMED; shipment có thể đã PICKED_UP; authorization có thể đã hết hiệu lực hoặc được capture.

### 4.2. Bước retryable

Một bước có thể thử lại theo **cùng một ý định**, chẳng hạn xác nhận trạng thái operation, cập nhật projection theo event ID hoặc một command có idempotency key được provider hỗ trợ. Retryable không đồng nghĩa mọi POST đều an toàn khi gửi lại với key mới.

### 4.3. Pivot transaction

Đó là một điểm cam kết sau đó hệ nên ưu tiên **forward recovery**, vì bù trực tiếp khó hoặc không còn đúng. Ví dụ:

- Bàn giao hàng cho carrier.
- Vé đã được quét qua cổng.
- Tài sản đã được chuyển quyền.
- Một loại chứng từ đã được phát hành chính thức.
- Thanh toán đã settle và bước đảo cần refund riêng thay vì void.

Pivot không phải công thức cứng áp dụng cho mọi nghiệp vụ. Điểm nào là pivot phụ thuộc vào chính sách, hợp đồng đối tác và trạng thái thực tế. Nên đặt những side effect khó đảo vào giai đoạn sau khi đã chắc chắn về các điều kiện có thể kiểm tra trước, nhưng vẫn phải có đường xử lý lỗi sau pivot.

### 4.4. Bước irreversible

Email đã gửi, dữ liệu đã công bố, hàng đã giao hoặc vé đã sử dụng không thể bị “xóa khỏi quá khứ”. Có thể cần thông báo đính chính, thu hồi theo quy trình riêng, hoàn hàng, hoàn tiền, hỗ trợ khách hàng hoặc xử lý sự cố. Đừng mô hình hóa chúng bằng một thao tác DELETE có tên Undo.

## 5. Bảng ánh xạ forward action và compensation

| Forward action | Bằng chứng thành công | Hành động bù | Điều kiện và giới hạn |
| --- | --- | --- | --- |
| ReserveStock | Reservation ID và trạng thái RESERVED | ReleaseReservation | Chưa consume hoặc fulfill |
| HoldSeat | Seat hold ID, expiry | ReleaseSeatHold | Chưa cấp/quét vé, hold còn hiệu lực |
| AuthorizePayment | Authorization ID | VoidAuthorization | Chưa capture; gateway cho phép void |
| CapturePayment | Capture ID, amount và currency | RefundCapture | Kiểm tra refundable amount, phí và policy |
| CreateShipment | Booking/shipment ID | CancelShipment | Carrier chưa pickup hoặc chưa xử lý |
| HandOverParcel | Bằng chứng carrier nhận hàng | RequestIntercept/Return | Có thể mất phí, không đảm bảo đảo ngay |
| IssueTicket | Ticket ID/entitlement | RevokeTicket | Vé chưa được dùng và policy cho phép |
| SendEmail | Message accepted/delivered | SendCorrection | Không thể thu hồi email đã đến |
| PublishInvoice | Invoice number, trạng thái phát hành | Adjustment/Void hợp pháp | Phụ thuộc quy định thuế và chứng từ |
| GrantAccess | Access grant ID | RevokeAccess | Không thu hồi dữ liệu người dùng đã xem |

Một điểm quan trọng là Payment có thể cần **VoidAuthorization** hoặc **RefundCapture**, tùy trạng thái. Một hàm cancelPayment chung cho tất cả các trường hợp rất dễ mang semantics mơ hồ.

## 6. Bắt đầu bằng state machine

Bù trừ có thể kéo dài và gặp lỗi. Không nên chỉ có boolean success/failed.

~~~text
Order
   NEW
    |
    v
  PENDING
   |   \
   |    \--- Forward step failed
   |                |
   v                v
CONFIRMED       COMPENSATING
                    |
          +---------+-----------+
          |                     |
          v                     v
       CANCELLED         COMPENSATION_FAILED
                                |
                                v
                           MANUAL_REVIEW
~~~

Có thể có các trạng thái chi tiết:

- CANCEL_REQUESTED: khách hoặc hệ yêu cầu hủy.
- CANCELLING: các compensations đang chạy.
- CANCELLATION_PENDING: một service đã nhận lệnh nhưng chưa hoàn thành.
- CANCELLED: các nghĩa vụ yêu cầu để hủy đã có bằng chứng hoàn tất.
- REFUND_PENDING: tiền đang chờ hoàn, không nên gọi REFUNDED.
- COMPENSATION_UNKNOWN: request timeout hoặc không chắc đã được xử lý.
- MANUAL_REVIEW: cần con người điều tra hoặc quyết định phương án khác.

### 6.1. Cấm transition trái nghĩa

Ví dụ nếu Order đã CANCELLED, một event PaymentAuthorized đến trễ không được tự chuyển Order sang CONFIRMED. Transition phải dựa trên sagaVersion/expectedState và business rules, không chỉ dựa vào thứ tự message đến.

### 6.2. Tách trạng thái của từng owner

Order có thể CANCELLING trong khi:

~~~text
Inventory.Reservation = RELEASED
Payment.Refund        = PENDING
Shipping.Booking      = CANCELLED
~~~

Order chưa thể tuyên bố “hoàn tiền xong” cho đến khi Payment có bằng chứng phù hợp. Một status endpoint nên trình bày rõ những phần việc đang chờ, không gom mọi loại trạng thái thành một giá trị CANCELLED thiếu chính xác.

## 7. Inventory: ReleaseReservation, không cộng lại stock một cách mù quáng

Một reservation nên có:

- reservationId độc lập.
- orderId và chủ thể có quyền thao tác.
- SKU, quantity và policy.
- Trạng thái RESERVED, CONFIRMED, CONSUMED, RELEASED, EXPIRED.
- Timestamps, expiry, version và audit metadata.

Ví dụ:

~~~text
RESERVED
   | \
   |  \-- ReleaseReservation --> RELEASED
   |
   +-- ConfirmReservation --> CONFIRMED --> CONSUMED
~~~

Khi Order thất bại trước khi fulfillment, coordinator gọi ReleaseReservation với reservationId gốc. Inventory xác nhận transition hợp lệ và chỉ trả lại lượng giữ một lần.

### 7.1. Chống release trùng

~~~text
Request 1: Release(res-8)
  RESERVED -> RELEASED
  Hiệu lực release một lần

Request 2: Release(res-8), cùng key
  RELEASED -> RELEASED
  Trả trạng thái đã hoàn tất, không tăng tồn lần hai
~~~

Nếu reservation đã CONSUMED, không được coi release là thành công bình thường. Có thể phải mở quy trình ReturnToStock sau khi hàng hoàn lại, tùy nghiệp vụ.

### 7.2. Không dùng snapshot cũ

Sai:

~~~sql
UPDATE stock SET available = 10 WHERE sku = 'SKU-7';
~~~

Nếu những đơn khác đã đặt trong lúc Saga chạy, lệnh trên phá trạng thái hiện tại. Đúng hơn là release resource sở hữu theo reservation ID, trong transaction cục bộ của Inventory và giữ đúng các invariant.

## 8. Payment: void khác refund

Ví dụ trạng thái:

~~~text
INITIATED
   |
   v
AUTHORIZED -------- VoidAuthorization ------> VOIDED
   |
   v
CAPTURED ---------- RefundCapture ----------> REFUND_PENDING
                                                    |
                                      +-------------+------------+
                                      |                          |
                                      v                          v
                                   REFUNDED                 REFUND_FAILED
~~~

Void thường phù hợp với authorization chưa capture, nếu provider hỗ trợ. Refund xử lý khoản tiền đã capture và có thể bất đồng bộ, phát sinh fees, partial refund hoặc yêu cầu đối soát.

### 8.1. Refund phải tham chiếu giao dịch gốc

Một refund command có thể gồm:

~~~json
{
  "refundId": "refund-order-729-v1",
  "captureId": "capture-729",
  "orderId": "order-729",
  "amount": "400000",
  "currency": "VND",
  "reason": "ORDER_CANCELLED"
}
~~~

Ví dụ amount là chuỗi biểu diễn VND theo hợp đồng giả định. Trong production, định nghĩa chính xác đơn vị tiền, làm tròn, scale và tương tác gateway; không tự dùng cùng một quy tắc tiền tệ cho mọi currency.

Payment phải xác minh captureId thuộc order đúng, phần tiền còn refundable và tổng refund đã thực hiện. Nếu hai yêu cầu refund cùng đến, cần concurrency control để không vượt amount.

### 8.2. Refund không xóa capture

Trong ledger:

~~~text
T1: Capture +500000
T2: Refund  -400000
Kết quả ròng = +100000 theo mô hình minh họa
~~~

Không DELETE dòng capture để hoàn tiền. Báo cáo, đối soát và audit phải có bằng chứng về từng giao dịch và fees liên quan.

### 8.3. REFUND_ACCEPTED khác REFUNDED

Gateway có thể báo ACCEPTED/PENDING, nhưng tiền chưa về tài khoản khách. API và UI phải phân biệt yêu cầu được chấp nhận với hoàn tiền hoàn tất. Khi callback mất, Payment phải query/reconcile với provider.

## 9. Shipping: hủy booking khác thu hồi hàng đã vận chuyển

Shipping có thể có trạng thái:

~~~text
DRAFT -> BOOKED -> PICKUP_SCHEDULED -> PICKED_UP -> IN_TRANSIT -> DELIVERED
           |            |
           +-- CANCEL --+
                                    |
                                    +--> RequestIntercept/Return
~~~

Lệnh CancelShipment có thể thành công khi chưa pickup, nhưng bị từ chối khi carrier đã nhận kiện. Sau PICKED_UP, thao tác bù có nghĩa là yêu cầu chặn vận chuyển, hoàn trả hoặc mở case hỗ trợ. Hệ có thể phải ghi nhận chi phí phát sinh và kết quả chưa chắc chắn.

### 9.1. Không đánh dấu CANCELLED chỉ vì HTTP 202

Carrier có thể nhận request và xử lý sau. Nên mô hình:

~~~text
CANCEL_REQUESTED -> CANCELLING
   |                    |
   |              +-----+------+
   |              |            |
   v              v            v
PENDING        CANCELLED    CANCEL_REJECTED
~~~

Timeout sau request cancel có thể nghĩa request đã được nhận nhưng phản hồi bị mất. Cần query theo operation ID hoặc chờ webhook/event.

## 10. Ticket, notification và các side effect không thể thu hồi

### 10.1. Vé sự kiện

HoldSeat có thể release khi chưa phát vé. TicketIssued có thể revoke theo policy khi chưa quét; nhưng khi vé đã được dùng, lệnh revoke không đảo việc tham gia sự kiện. Khi đó quy trình khắc phục có thể gồm hoàn tiền một phần hoặc khiếu nại.

### 10.2. Email, SMS và push

Một email đã tới người nhận không thể bị xóa bằng cách xóa record Notification. Nếu sai thông tin, cần SendCorrection với nội dung rõ. Nên trì hoãn gửi “OrderConfirmed” cho đến khi Saga đã qua các điều kiện thành công cần thiết, hoặc gửi thông điệp “đơn đang xử lý” nếu kết quả chưa chắc chắn.

### 10.3. Chứng từ và pháp lý

Hóa đơn hoặc hồ sơ đã phát hành có thể yêu cầu chứng từ điều chỉnh/hủy theo quy định áp dụng. Không “undo” bằng DELETE row vì có thể vi phạm yêu cầu audit. Business semantics của điều chỉnh phải do bounded context có thẩm quyền quyết định.

### 10.4. Provisioning

Thu hồi một resource cloud đã tạo có thể được, nhưng chi phí phát sinh hoặc dữ liệu đã truy cập không tự biến mất. Có thể cần revoke access, ghi nhận usage, hoàn credit và xóa dữ liệu theo policy.

## 11. Bù trừ theo thứ tự nào?

Thông thường bù các bước hoàn tất theo thứ tự ngược:

~~~text
T1 ReserveStock
T2 AuthorizePayment
T3 BookShipping -> FAIL

C2 VoidAuthorization
C1 ReleaseReservation
~~~

Nhưng thứ tự ngược chỉ là **heuristic**. Hãy lập dependency graph:

- Cần hủy shipment trước khi giải phóng reservation nếu carrier có thể đến lấy hàng.
- Không refund trước khi xác minh số tiền capture.
- Nếu các compensations độc lập và idempotent, có thể chạy song song.
- Nếu một service chỉ ACCEPTED nhưng chưa COMPLETED, phải theo dõi trước khi xác định bước tiếp theo.
- Với các nhánh chạy song song, có thể có nhiều forward steps đang PENDING khi lỗi xuất hiện.

### 11.1. Bù theo trạng thái thực, không theo danh sách lệnh đã gửi

Gửi CapturePayment rồi timeout **không đồng nghĩa capture thất bại**. Có thể:

1. Request chưa đến Payment.
2. Payment đang xử lý.
3. Payment đã capture nhưng response mất.
4. Payment đã từ chối nhưng response mất.

Coordinator phải hỏi Payment theo operation ID, hoặc chờ event đã được kiểm chứng. Chỉ sau khi biết trạng thái thực mới chọn void/refund/không làm gì.

## 12. Compensation phải idempotent

Message có thể gửi lại, HTTP retry có thể trùng, coordinator có thể crash và khởi động lại. Hành động bù phải có hiệu lực tối đa một lần với **cùng ý định**, dù được nhận nhiều lần.

Một key ổn định:

~~~text
sagaId           = saga-order-729
forwardStepId    = reserve-stock
reservationId    = res-729
compensationId   = saga-order-729-release-stock-v1
~~~

Không tạo một UUID mới mỗi lần retry. Key phải gắn với operation gốc và có chính sách retention/unique đủ dài cho cửa sổ retry, replay và phục hồi.

### 12.1. Dedupe lưu bền vững

Có thể dùng bảng:

~~~sql
CREATE TABLE processed_compensation (
    compensation_id VARCHAR(160) PRIMARY KEY,
    resource_id VARCHAR(160) NOT NULL,
    result_state VARCHAR(50) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL
);
~~~

Đây là schema minh họa. Trong code thực tế, việc ghi processed_compensation và thay đổi reservation phải diễn ra trong cùng transaction cục bộ, hoặc một cơ chế atomic tương đương. Nếu đánh dấu đã xử lý rồi crash trước khi release, retry sẽ bị bỏ qua sai.

### 12.2. Đã đạt trạng thái đích

Nếu ReleaseReservation đã trả RELEASED, lần gọi lại có thể trả ALREADY_RELEASED với evidence. Coordinator có thể xem đó là hoàn tất nếu resource và original intent khớp.

Nếu trả CONSUMED hoặc RESOURCE_MISMATCH, không nên coi là thành công; phải chuyển sang đường thay thế hoặc manual review.

## 13. Timeout và unknown outcome

Phải phân biệt lỗi transport với kết quả nghiệp vụ.

~~~text
Coordinator
   |
   | POST ReleaseReservation(key=K)
   v
Inventory
   | commit RELEASED
   X response lost

Coordinator thấy timeout:
   Không được suy luận "chưa release".
   Query status hoặc retry cùng key K.
~~~

Một quy trình:

~~~text
COMPENSATION_UNKNOWN
       |
       v
QueryOwner(resourceId/operationId)
       |
       +-- RELEASED ---------> COMPLETED
       |
       +-- RESERVED ---------> retry K nếu policy cho phép
       |
       +-- CONSUMED ---------> alternative workflow/manual review
       |
       +-- UNKNOWN/PENDING --> tiếp tục đối soát có giới hạn
~~~

NOT_FOUND không luôn nghĩa “chưa tạo resource”. Nó có thể nghĩa resource đã expire/xóa, hoặc ID sai. Contract phải nói rõ semantics.

### 13.1. Không retry một refund mới vì HTTP timeout

Nếu Payment refund đã commit nhưng response bị mất, gửi lại cùng refundId/idempotency key và query trạng thái. Sinh refundId mới có thể dẫn đến hoàn tiền hai lần nếu payment provider không dedupe theo original intent.

## 14. Retry, backoff và giới hạn thời gian

Một lỗi 503 hoặc timeout có thể do downtime tạm. Compensation nên retry có kiểm soát:

- Max attempts hoặc thời gian xử lý tối đa theo loại operation.
- Exponential backoff với jitter để nhiều Saga không retry cùng lúc.
- Tôn trọng Retry-After khi có ý nghĩa.
- Rate limit/bulkhead để không làm service đang hỏng càng quá tải.
- Lưu nextRetryAt/attempt count bền vững để không quên sau restart.
- Theo dõi tổng thời gian bù so với business SLA.

Không nên retry vô hạn với:

- Policy từ chối hoàn tiền.
- Resource đã bị CONSUMED hoặc ticket đã USED.
- Carrier đã PICKED_UP và không chấp nhận cancel.
- Invalid currency/amount hoặc resource ID không thuộc Saga.
- Schema mismatch hoặc thiếu quyền vĩnh viễn.

Với lỗi terminal, chuyển sang phương án bù khác hoặc MANUAL_REVIEW.

### 14.1. HTTP deadline khác thời hạn hoàn tất Saga

Người dùng có thể chỉ chờ API 2 giây nhưng refund mất nhiều giờ. Không giữ HTTP connection mở trong suốt compensation. Trả trạng thái như CANCELLATION_IN_PROGRESS và tracking ID, cho phép query hoặc nhận thông báo kết quả.

~~~json
{
  "orderId": "order-729",
  "status": "CANCELLATION_IN_PROGRESS",
  "refundStatus": "PENDING",
  "trackingId": "saga-order-729"
}
~~~

## 15. Race condition và bảo vệ state transition

Giả sử Inventory có reservation RESERVED. Hai lệnh đồng thời:

~~~text
Worker A: ConfirmReservation
Worker B: ReleaseReservation
~~~

Nếu không có concurrency control, hệ có thể vừa xác nhận vừa giải phóng cùng một lượng hàng. Owner cần transition guard theo trạng thái hoặc version.

~~~sql
UPDATE reservations
SET status = 'RELEASED',
    version = version + 1
WHERE id = :reservation_id
  AND status = 'RESERVED'
  AND version = :expected_version;
~~~

Phải kiểm tra rows affected, đọc trạng thái khi không cập nhật được và chọn xử lý phù hợp. Zero rows không tự động có nghĩa hoàn tất: resource có thể đã CONSUMED.

### 15.1. Late events

PaymentAuthorized có thể đến sau khi Saga chuyển COMPENSATING. Nếu coordinator chỉ dựa vào event mới nhận, Order có thể bị xác nhận lại dù đã hủy. Dùng sagaVersion/expectedState và quyết định theo invariant.

### 15.2. Fencing

Khi nhiều coordinator instances hoặc lease bị hết hạn, một worker cũ có thể gửi command chậm. Với workflow có rủi ro race lớn, owner có thể yêu cầu epoch/fencing token hoặc sequence để từ chối command cũ. Mục tiêu là không cho tiến trình stale thay đổi trạng thái đã được coordinator mới quyết định.

## 16. Choreography và orchestration

### 16.1. Orchestration

Một coordinator lưu tiến độ Saga, quyết định forward và compensation commands:

~~~text
             Checkout Saga Coordinator
                |       |       |
                v       v       v
           Inventory Payment Shipping
                \       |       /
                 \------v------/
                   Saga state
~~~

Ưu điểm: dễ xác định owner của workflow, theo dõi trạng thái và điều kiện bù, retry, timeout và manual intervention.

Đổi lại: coordinator phải được quản trị khả dụng, lưu trạng thái bền vững, versioning và có khả năng phục hồi. Nó không có quyền tự sửa dữ liệu của các service khác.

### 16.2. Choreography

Các service phát và tiêu thụ events:

~~~text
OrderCreated
    -> Inventory Reserves
        -> StockReserved
            -> Payment Authorizes
                -> PaymentDeclined
                    -> Inventory Releases
                    -> Order Cancelled
~~~

Không có một service thực hiện tất cả command, nhưng phải có định nghĩa rõ **ai chịu trách nhiệm phát hiện workflow kẹt**, kích hoạt bù khi event thiếu, tổng hợp kết quả và giữ audit. Luồng nhiều nhánh có thể khó quan sát nếu mọi service tự nghe rồi phát event không theo giao thức thống nhất.

### 16.3. Tránh hai bên cùng ra lệnh bù

Nếu Payment và Order đồng thời thấy payment failed rồi cùng ra lệnh release Stock, idempotency giúp ngăn double release, nhưng kiến trúc vẫn nên quy định ai có thẩm quyền ra quyết định bù và correlation nào gắn với một Saga.

## 17. Lưu trạng thái Saga và phát command tin cậy

Coordinator có thể crash ngay sau khi lưu COMPENSATING nhưng trước khi gửi ReleaseReservation. Ngược lại, nó có thể gửi command thành công nhưng chưa ghi nhận đã gửi.

Một cách thường dùng là **transactional outbox**:

~~~text
Transaction cục bộ tại Coordinator:
    update Saga -> COMPENSATING
    insert outbox command -> ReleaseReservation(key=K)
COMMIT

Dispatcher -> Inventory
Inventory xử lý idempotent
Inventory phát response/event
Coordinator cập nhật Saga state
~~~

Outbox giúp state và ý định gửi message được ghi cùng transaction cục bộ. Nó không bảo đảm command chỉ được giao một lần; dispatcher có thể retry, vì thế consumer phải dedupe hoặc thực thi idempotent.

### 17.1. Inbox và handled-operation record

Inventory có thể lưu commandId và kết quả xử lý trong local transaction cùng reservation update. Khi nhận message trùng, trả lại kết quả hoặc trạng thái hiện tại theo contract.

### 17.2. Correlation metadata

Nên có:

- sagaId, stepId và compensationId.
- originalOperationId và resourceId.
- causationId, eventId và schemaVersion nếu qua broker.
- aggregateVersion/expectedState hoặc fencing token khi cần.
- ReasonCode có ý nghĩa và trace context.

Không đưa toàn bộ dữ liệu khách hàng/secret vào message chỉ vì tiện debug. Cần bảo mật payload và audit retention.

## 18. API bù trừ theo ý nghĩa nghiệp vụ

Một API nên thể hiện hành động rõ:

~~~http
POST /inventory/reservations/res-729/release
Idempotency-Key: saga-729-release-v1
Content-Type: application/json

{
  "orderId": "order-729",
  "reason": "PAYMENT_DECLINED"
}
~~~

Kết quả:

~~~json
{
  "reservationId": "res-729",
  "state": "RELEASED",
  "operationId": "release-op-729"
}
~~~

Cần document:

| Kết quả | Coordinator nên làm gì? |
| --- | --- |
| RELEASED | Ghi bù hoàn tất |
| ALREADY_RELEASED | Hoàn tất nếu đúng operation/resource |
| ACCEPTED/PENDING | Theo dõi, không tuyên bố xong |
| TEMPORARILY_UNAVAILABLE | Retry cùng key có giới hạn |
| CONSUMED/TOO_LATE | Đổi hướng hoặc manual review |
| NOT_FOUND | Xác minh nghĩa contract và operation gốc |
| UNKNOWN | Query status/reconcile, không đoán |
| WRONG_OWNER/INVALID_STATE | Không retry mù; sửa trạng thái hoặc điều tra |

Cần xác thực caller và resource ownership; không cho một Saga giả mạo release resource hoặc refund giao dịch của người khác.

## 19. Ví dụ Java: giao diện và kết quả bù trừ

~~~java
public record ReleaseReservationCommand(
    String sagaId,
    String compensationId,
    String orderId,
    String reservationId,
    String reason
) {}

public enum CompensationState {
    COMPLETED,
    PENDING,
    RETRYABLE_FAILURE,
    REQUIRES_ALTERNATIVE,
    MANUAL_REVIEW
}

public record CompensationOutcome(
    CompensationState state,
    String operationId,
    String explanation
) {}
~~~

Gateway có thể khai báo:

~~~java
public interface InventoryCompensationGateway {
    CompensationOutcome releaseReservation(
        ReleaseReservationCommand command
    );

    CompensationOutcome queryReleaseStatus(
        String compensationId
    );
}
~~~

Một coordinator minh họa (pseudocode application layer):

~~~java
public void resumeCompensation(Saga saga) {
    if (!saga.isCompensating()) return;

    var cmd = new ReleaseReservationCommand(
        saga.id(),
        saga.releaseCompensationId(),
        saga.orderId(),
        saga.reservationId(),
        "PAYMENT_DECLINED"
    );

    var outcome = inventory.releaseReservation(cmd);

    switch (outcome.state()) {
        case COMPLETED -> saga.markInventoryReleased();
        case PENDING -> saga.scheduleStatusCheck(outcome.operationId());
        case RETRYABLE_FAILURE -> saga.retryLaterWithSameKey();
        case REQUIRES_ALTERNATIVE -> saga.openAlternativeWorkflow();
        case MANUAL_REVIEW -> saga.flagForOperations();
    }

    sagaStore.saveWithExpectedVersion(saga);
}
~~~

Đây là mã minh họa cấu trúc, chưa phải implementation có thể dùng nguyên trong production. Trên thực tế cần transaction/outbox khi lưu state và gửi command, recovery khi crash, concurrency control, kiểm tra quyền, timeout, retry và integration tests. Không được coi việc gọi release qua mạng rồi save state là atomic.

## 20. Compensation của hóa đơn và kế toán

Một giao dịch tài chính thường cần vết chứng từ và quy tắc tuân thủ. Ví dụ một invoice đã phát hành không thể xử lý như xóa một draft chưa công bố.

Các trạng thái có thể là:

~~~text
DRAFT -> ISSUED -> ADJUSTMENT_REQUIRED -> ADJUSTED
   |       |
  VOID    (bút toán hoặc chứng từ điều chỉnh
            theo quy định áp dụng)
~~~

Hành động bù có thể là VoidDraft, CreateCreditNote, IssueAdjustmentDocument hoặc tạo một entry trong ledger; không có một phép DELETE chung cho mọi loại chứng từ. Vì yêu cầu luật thuế và chuẩn kế toán khác theo quốc gia/ngành, service Billing phải sở hữu policy cụ thể và cập nhật theo quy định hiện hành.

## 21. Hành động bù không thể thành công: forward recovery

Khi side effect đã đi quá điểm cho phép đảo trực tiếp, nên thiết kế bước tiến để giải quyết:

- Hàng đang IN_TRANSIT → RequestIntercept hoặc Return Merchandise Authorization.
- Vé đã USED → xử lý khiếu nại/hoàn tiền theo chính sách, không giả vờ revoke sự kiện sử dụng.
- Email đã DELIVERED → SendCorrection, không xóa record và coi như chưa gửi.
- Tiền đã SETTLED → Refund hoặc adjustment, không void kiểu authorization.
- Một tài nguyên đã tiêu thụ → thu hồi quyền còn lại và điều chỉnh nghĩa vụ/credit hợp lệ.

Điều này có thể làm hệ mất phí hoặc phải chờ con người. Mục tiêu kiến trúc là **minh bạch về những nghĩa vụ đang tồn tại** và đưa hệ đến một kết quả đúng luật/quy tắc, không phải tạo ảo giác all-or-nothing.

## 22. Khi nào nên giữ transaction cục bộ thay vì dùng Saga?

Nếu hai bảng cùng bảo vệ một invariant ngay lập tức, chẳng hạn StockBalance và Reservation, tách chúng thành hai microservices rồi bắt Saga bù đi bù lại có thể làm vấn đề khó hơn. Có thể nên giữ trong cùng Inventory owner/transaction.

Hãy tự hỏi:

1. Các hành động cần atomic commit để bảo vệ invariant nào?
2. Có thể đặt chúng trong cùng bounded context không?
3. Sự cố mạng giữa hai phần có thể gây oversell/overcharge không?
4. Có business compensation hợp lệ và chấp nhận được không?
5. Có thể chuyển sang trạng thái PENDING mà không phá lời hứa với người dùng không?
6. Chi phí workflow engine, observability và reconciliation có đáng trả để đổi lấy deploy/scale độc lập không?

Saga phù hợp khi các local transactions thuộc những business capabilities khác nhau, không thể hoặc không nên gộp chung ownership, và business process có thể xử lý partial progress theo trạng thái rõ ràng.

## 23. Quan sát và vận hành compensation

Một Saga có thể đang bù sau khi HTTP request ban đầu đã kết thúc, nên cần metrics/audit riêng:

| Nhóm | Thông tin | Giá trị |
| --- | --- | --- |
| Saga lifecycle | STARTED, COMPLETED, COMPENSATING, COMPENSATED | Biết workflow thực sự ở đâu |
| Duration | Tuổi Saga, tuổi compensation PENDING | Phát hiện kẹt |
| Attempts | Retry count, nextRetryAt, last error | Kiểm soát retry |
| Unknown outcome | Các operation không xác định | Kích hoạt reconciliation |
| Terminal errors | TOO_LATE, POLICY_REJECTED, INVALID_STATE | Chọn đường thay thế |
| Payment | Capture/refund amount, refund pending | Tránh hoàn/thu trùng |
| Inventory | Reservation stuck, release rate | Bảo vệ tài nguyên giữ |
| Event pipeline | Outbox backlog, consumer lag, DLQ | Phát hiện message kẹt |
| Manual review | Cases mở, độ tuổi, SLA | Bảo đảm có owner |
| Customer impact | Refund delayed, cancellation delayed | Thông tin minh bạch |

Hãy kết nối log/tracing qua sagaId, operationId và causationId. Không gắn orderId, paymentId hay email trực tiếp vào metric labels với cardinality không giới hạn. Dữ liệu audit cần phân quyền, ẩn PII và có retention thích hợp.

### 23.1. Reconciliation là phần thiết yếu

Có thể quét các Saga quá thời hạn:

~~~text
Scheduler:
    Find Saga WHERE state IN (COMPENSATING, UNKNOWN)
       AND next_check_at <= now
    -> Query Inventory/Payment/Shipping theo operation ID
    -> Cập nhật trạng thái có version guard
    -> Retry/alternative/manual review
~~~

Không tạo command bù mới với key mới chỉ vì worker trước bị timeout. Phải tra cứu kết quả và dùng lại ý định gốc.

## 24. Manual intervention không có nghĩa bỏ qua nguyên tắc

Một số cases cần operator xác nhận carrier đã pickup, payment đã settle hoặc khách đã nhận hàng. Manual workflow nên có:

- Danh sách forward/compensation đã hoàn tất.
- Operation IDs và bằng chứng xác minh.
- Các trạng thái chủ nguồn mới nhất.
- Lần thử, lỗi và retry schedule.
- Lựa chọn command theo domain, có permission check.
- Audit ai quyết định, khi nào, vì sao.
- Cảnh báo còn nghĩa vụ chưa hoàn tất.
- Tránh việc một worker tự động retry sau khi operator đã bù theo lệnh khác.

Không nên cho operator sửa trực tiếp stock quantity hoặc tạo refund mới bằng SQL nếu vẫn có một compensation PENDING. Dùng admin API cùng idempotency và state guards để tránh double effect.

## 25. Quy trình thiết kế từng bước

### Bước 1 — Định nghĩa cam kết cuối cùng

Ví dụ: khi checkout thất bại, không giữ hàng vô hạn, không thu trùng tiền, khách được thông báo trạng thái chính xác và có quy trình hoàn tiền hợp lệ.

### Bước 2 — Liệt kê forward steps và transaction owner

Với mỗi bước, ghi command, service owner, resource ID, thời điểm commit, trạng thái trung gian và bằng chứng thành công.

### Bước 3 — Phân loại khả năng đảo

Compensatable, retryable, pivot hoặc irreversible. Định nghĩa giới hạn thời gian, trạng thái và chi phí.

### Bước 4 — Chọn compensation theo business semantics

ReleaseReservation, VoidAuthorization, RefundCapture, CancelShipment, RequestReturn, RevokeTicket hoặc SendCorrection.

### Bước 5 — Thiết kế state machine

Có PENDING, COMPLETED, UNKNOWN, COMPENSATING, COMPENSATED, MANUAL_REVIEW và những transition được phép. Tránh boolean success cho tác vụ dài.

### Bước 6 — Thiết kế idempotency/correlation

Key ổn định trên từng bước, operation status query, dedupe bền vững, version/fencing nếu có race.

### Bước 7 — Chọn thứ tự và phương án song song

Theo dependency graph của business, không đảo ngược máy móc. Chỉ song song khi không phá invariant.

### Bước 8 — Chọn orchestration/choreography

Quy định owner của quyết định cuối, thời gian chờ, trách nhiệm phát hiện workflow kẹt.

### Bước 9 — Persist state và phát command tin cậy

Dùng transactional outbox/inbox hoặc workflow engine có semantics tương đương. Chấp nhận duplicate và xử lý idempotently.

### Bước 10 — Thiết kế retry, reconciliation và manual review

Phân biệt transient errors với terminal business errors, có runbook khi không thể bù.

### Bước 11 — Thiết kế user-visible status

CANCELLING khác CANCELLED; REFUND_PENDING khác REFUNDED; response ACCEPTED khác tác vụ COMPLETED.

### Bước 12 — Kiểm thử khi mạng và downstream có lỗi

Bao gồm response lost after commit, duplicate, out-of-order, crash/restart, đồng thời confirm/release, pivot và manual operation.

## 26. Bài tập thực hành: đặt vé sự kiện

Một quy trình:

~~~text
T1 HoldSeat
T2 AuthorizePayment
T3 IssueTicket
T4 CapturePayment
T5 SendTicketEmail
T6 Ticket được scan tại cổng
~~~

**Bài 1:** Lập bảng forward/compensation. Với T2, dùng Void hay Refund? Điều gì thay đổi sau T4? T5 và T6 có thể đảo được không?

**Bài 2:** T3 thất bại sau khi T2 thành công. Thiết kế thứ tự VoidAuthorization và ReleaseSeatHold, key ổn định và trạng thái booking hiển thị.

**Bài 3:** T4 capture thành công nhưng response mất. Coordinator nên query đâu, xử lý trạng thái UNKNOWN thế nào và khi nào mới refund?

**Bài 4:** Ticket đã ISSUED và đang có một lệnh revoke; cùng lúc máy check-in báo USED. Thiết kế state guards để không báo revoke thành công sai.

**Bài 5:** Người dùng mua ba vé rồi hủy một vé. Thiết kế partial refund, amount, ticket entitlement và điều kiện chống refund trùng.

**Bài 6:** Một external payment provider không phản hồi suốt 24 giờ. Xác định retry policy, escalation, dashboard, liên hệ khách và reconciliation.

Kết quả mong đợi là sơ đồ trạng thái, bảng lệnh bù, contract IDs, điều kiện retry/không retry, phương án khôi phục và test plan.

## 27. Kịch bản kiểm thử quan trọng

### 27.1. Forward commit, response lost

Inventory đã reserve nhưng coordinator timeout. Xác minh hệ query được trạng thái trước khi quyết định release.

### 27.2. Compensation commit, response lost

ReleaseReservation đã commit nhưng response mất. Retry cùng key không làm tồn kho tăng lần nữa.

### 27.3. Duplicate command

Hai workers nhận cùng ReleaseReservation. Unique operation ID và state transition guard chỉ cho hiệu lực một lần.

### 27.4. Out-of-order event

PaymentAuthorized đến sau khi Saga COMPENSATING. Không cho chuyển Order về CONFIRMED trái policy.

### 27.5. Confirm vs release race

Một worker ConfirmReservation và worker khác ReleaseReservation cùng lúc. Kiểm chứng chỉ một transition được commit.

### 27.6. Pivot đã xảy ra

Shipment PICKED_UP. CancelShipment bị từ chối, workflow mở Return/Intercept thay vì đánh dấu bù thành công.

### 27.7. Partial refund

Có hai refund requests đồng thời. Tổng refund không vượt khoản được phép; idempotency gắn đúng từng ý định.

### 27.8. Coordinator restart

Crash giữa lưu state và dispatch compensation. Outbox phục hồi, không mất command, dù có thể gửi lặp.

### 27.9. Broker outage

Event hoặc result delayed. Coordinator vẫn nhận diện PENDING/UNKNOWN, không mặc định thất bại vĩnh viễn.

### 27.10. Manual vs automatic retry

Operator xử lý compensation trong khi scheduled retry đang chạy. Cả hai dùng state guard/idempotency nên không tạo tác động hai lần.

### 27.11. Retry storm

Hàng nghìn Saga thất bại đồng thời do Payment outage. Retry có backoff, jitter và rate limit để không đánh sập các service khác.

### 27.12. User-facing correctness

Khách thấy trạng thái “đang hoàn tiền” trong lúc Payment PENDING; chỉ khi có bằng chứng REFUNDED mới hiển thị đã hoàn tất.

## 28. Những sai lầm phổ biến

### Sai lầm 1 — Compensation là phép SQL ngược

Sai. Nó phải dựa trên resource, state và invariant hiện tại. Không ghi đè dữ liệu bằng snapshot cũ.

### Sai lầm 2 — DELETE record là hoàn tác nghiệp vụ

Sai. Xóa ledger/invoice/shipment không xóa tác động ngoài hệ. Cần reversal, refund, return hoặc correction.

### Sai lầm 3 — Timeout nghĩa là giao dịch thất bại

Sai. Có thể server đã commit. Cần query theo operation ID và dùng idempotency.

### Sai lầm 4 — Mọi bước có lệnh Cancel bất kể trạng thái

Sai. Một shipment đã pickup hoặc vé đã dùng có thể không còn hủy trực tiếp được.

### Sai lầm 5 — Compensation chỉ chạy một lần

Sai. Network, broker và coordinator có thể gửi lặp; bù phải idempotent và durable.

### Sai lầm 6 — Có outbox là exactly-once toàn hệ

Sai. Outbox bảo đảm ý định gửi cùng transaction cục bộ; duplicate delivery vẫn cần xử lý.

### Sai lầm 7 — Đảo ngược thứ tự máy móc

Sai. Business dependency graph quyết định thứ tự và khả năng chạy song song.

### Sai lầm 8 — Hoàn tiền đồng nghĩa xóa lịch sử charge

Sai. Capture/refund có lịch sử, phí, settlement và obligations riêng.

### Sai lầm 9 — Một lỗi vĩnh viễn cứ retry vô hạn

Sai. Cần alternative workflow hoặc manual review.

### Sai lầm 10 — Đánh dấu CANCELLED trước khi các nghĩa vụ xong

Sai. Tách trạng thái request/processing/completed; truyền thông trung thực với người dùng.

### Sai lầm 11 — Chia mọi invariant thành nhiều microservices rồi Saga vá

Sai. Invariant nguyên tử có thể cần cùng một owner/transaction; Saga không thay thế thiết kế boundary.

## 29. Checklist trước khi production

| Câu hỏi | Cần trả lời |
| --- | --- |
| Forward step đã commit chưa? | Evidence/operation status |
| Ai là owner? | Service và transaction boundary |
| Hành động bù có nghĩa gì? | Release, void, refund, return, correction |
| Bù có điều kiện trạng thái nào? | State guards, expiry, policy |
| Có pivot không? | Điểm không thể đảo trực tiếp |
| Resource ID có ổn định? | Original operation/resource reference |
| Bù idempotent chưa? | Durable key và dedupe |
| Unknown outcome xử lý thế nào? | Status query và reconciliation |
| Retry có giới hạn? | Backoff, jitter, terminal errors |
| Có race/out-of-order? | Version, optimistic locking, fencing |
| Có owner của Saga? | Orchestrator/choreography responsibility |
| State/message có bền vững? | Outbox, inbox hoặc workflow engine |
| UI có trung thực? | PENDING khác COMPLETED |
| Có manual recovery? | Role, action, audit và SLA |
| Có metrics/test? | Pending, retries, refund, fault injection |

## 30. Câu hỏi tự kiểm tra

1. Vì sao compensation không giống transaction rollback?
2. Bù trừ khác “trở về snapshot cũ” như thế nào?
3. Tại sao không được SET quantity của kho về giá trị trước reservation?
4. Khi nào dùng VoidAuthorization và khi nào dùng RefundCapture?
5. Vì sao email đã gửi không thể bù bằng DELETE notification?
6. Pivot transaction thay đổi hướng xử lý khi thất bại thế nào?
7. Nếu Payment capture timeout, có thể kết luận chưa thu tiền không?
8. Cần lưu những ID nào để retry bù trừ an toàn?
9. Vì sao idempotency key mới mỗi lần retry là nguy hiểm?
10. Một event đến trễ có thể phá state machine như thế nào?
11. Khi hai workers cùng release reservation, phải kiểm soát concurrency ra sao?
12. Vì sao một refund PENDING không được hiển thị thành REFUNDED?
13. Outbox giải quyết sự cố nào và không giải quyết điều gì?
14. Bù trừ có nhất thiết chạy theo đúng thứ tự ngược không?
15. Khi compensation bị policy từ chối vĩnh viễn, hệ nên xử lý thế nào?
16. Những case nào nên giữ trong một local transaction thay vì dùng Saga?
17. Cần theo dõi những metrics nào để biết Saga đang kẹt?
18. Vì sao thao tác manual cần đi qua command idempotent thay vì SQL trực tiếp?
19. Tại sao hồi phục hàng đã giao là một nghiệp vụ return, không phải rollback?
20. Business consistency có thể đạt được khi còn lịch sử capture/refund và notification đã gửi không?

## 31. Tóm tắt

- **Bù trừ là lệnh nghiệp vụ mới**, không phải SQL rollback của service khác hay xóa vết lịch sử.
- **Thiết kế theo invariant, state machine và resource gốc.** ReleaseReservation, VoidAuthorization, RefundCapture và RequestReturn không phải các thao tác thay thế tùy ý.
- **Không phải mọi side effect đều đảo được.** Sau pivot cần forward recovery, correction hoặc manual review.
- **Timeout không chứng minh server chưa commit.** Query status/reconcile trước khi kết luận và dùng lại idempotency key ổn định.
- **Compensation cũng có thể thất bại**; cần retry có giới hạn, terminal error handling và escalation.
- **Thứ tự bù phụ thuộc business dependencies**, thường đảo ngược những bước đã hoàn tất nhưng không máy móc.
- **Dùng outbox/inbox hoặc cơ chế bền vững tương đương** để không mất tiến độ khi crash, vẫn xử lý duplicate.
- **Bảo vệ race và event đến muộn** bằng expected state, version/fencing và owner rõ.
- **Phân biệt trạng thái khách nhìn thấy:** cancellation requested khác cancelled, refund pending khác refunded.
- **Quan sát và kiểm thử failure modes thật**: duplicate, lost response, coordinator restart, payment uncertainty, shipment too late, manual conflict.

**Câu hỏi chốt:** Khi Payment đã thu tiền, Shipping đã nhận kiện hàng và email xác nhận đã gửi, hệ phải làm gì nếu khách yêu cầu hủy? Một thiết kế đúng trả lời bằng refund/return/correction theo chính sách, bằng chứng và trạng thái có thể theo dõi — không phải bằng một câu “rollback mọi thứ”.
