# Thiết kế nghiệp vụ có bước bù và điều kiện kiểm chứng

Trong một hệ thống NoSQL thực tế, một yêu cầu nghiệp vụ hiếm khi chỉ sửa đúng một bản ghi. Chức năng đặt hàng có thể phải **tạo đơn**, **giữ tồn kho**, **xin phép thanh toán**, **xác nhận kết quả** rồi **phát sự kiện** để cập nhật giao diện, kho vận và báo cáo. Các dữ liệu liên quan có thể nằm trong những document, item, partition hoặc dịch vụ độc lập. Một thao tác thành công không có nghĩa tất cả những thao tác khác cũng đã thành công.

Ví dụ, hệ thống giảm tồn kho thành công nhưng yêu cầu thanh toán thất bại. Nếu chỉ trả HTTP 500 rồi bỏ qua, ba cuốn sách có thể bị giữ mãi dù không có đơn hợp lệ. Nếu cố “rollback” bằng cách cộng lại tồn kho nhưng request giải phóng bị gửi hai lần, kho có thể được cộng dư. Nếu thanh toán đã thành công nhưng phản hồi mạng bị mất, việc hoàn tiền hoặc tính tiền lần nữa mà chưa kiểm tra kết quả cũng có thể gây thiệt hại.

Giải pháp thường không phải gom mọi việc vào một transaction khổng lồ, bởi transaction của một database không bao trùm tùy ý **database khác, cổng thanh toán, email hoặc hệ thống vận chuyển**. Thay vào đó, cần thiết kế quy trình nghiệp vụ có:

1. **Bất biến và trạng thái hợp lệ** được mô tả rõ ràng.
2. **Điều kiện trước khi thực hiện (precondition)** cho từng bước.
3. **Điều kiện kiểm chứng sau bước (postcondition)** dựa trên nguồn có thẩm quyền.
4. **Bước bù (compensating action)** khi một phần công việc đã thành công nhưng quy trình không thể hoàn tất.
5. **Điều kiện được phép bù và kiểm chứng sau bù**, tránh đảo ngược sai trạng thái hoặc bù lặp.
6. **Trạng thái quy trình bền vững, idempotency, retry và đối soát** để phục hồi khi crash, timeout hoặc sự kiện bị giao lại.

Bài này đặt các nguyên tắc trên trong chương **Giao dịch và nguyên tử** của Database No SQL, minh họa bằng Saga, reservation, MongoDB, DynamoDB, Redis, Cassandra và workflow có dịch vụ ngoài database. Cú pháp là ví dụ học tập; một triển khai production phải kiểm tra phiên bản engine, quyền truy cập, durability, isolation và hợp đồng cụ thể của từng dịch vụ.

## 1. Khi nào một transaction cục bộ không còn đủ?

Xét luồng checkout:

~~~text
Khách gửi checkoutRequestId = req-9001

Order Service:
  tạo order PENDING

Inventory Service:
  giữ 3 sách BOOK-01

Payment Service:
  yêu cầu authorize/capture theo hợp đồng provider

Order Service:
  xác nhận order

Event/Notification:
  phát OrderConfirmed và gửi thông báo
~~~

Nếu tất cả thay đổi chỉ nằm trong một document và engine hỗ trợ atomic update, một thao tác nguyên tử có thể đủ. Nhưng khi tồn kho nằm trong một item riêng, đơn ở collection khác và thanh toán là một lời gọi HTTPS, không còn một đơn vị commit toàn cục tự nhiên.

Giả sử từng bước có thể thành công hoặc thất bại:

| Bước | Có thể thành công độc lập? | Có thể xảy ra lỗi sau khi thực sự thành công? |
|---|---|---|
| Tạo order PENDING | Có | Có, ví dụ mất response sau commit |
| Giữ stock | Có | Có, worker crash sau khi giữ |
| Authorize payment | Có | Có, provider duyệt nhưng mạng timeout |
| Xác nhận order | Có | Có, ghi thành công nhưng event chưa được phát |
| Gửi thông báo | Có | Có, email đã gửi nhưng worker chưa nhận ack |

**Tính nguyên tử cục bộ** vẫn rất hữu ích cho từng bước. Nhưng muốn xử lý cả chuỗi, phải định nghĩa các trạng thái trung gian và cách khôi phục khi một bước chưa hoàn thành. Đây là lý do các hệ phân tán sử dụng **Saga** hoặc những workflow tương đương.

### Định nghĩa thực dụng

**Saga** là một chuỗi giao dịch/hành động cục bộ, trong đó tiến trình lưu trạng thái để tiếp tục, thử lại hoặc thực hiện những hành động bù tương ứng khi không đạt mục tiêu. Một Saga thường không bảo đảm isolation/atomic commit toàn cục như một database transaction. Trong thời gian chạy, các trạng thái trung gian có thể được quan sát, nên **business invariant** và quyền truy cập phải bảo vệ ngay tại từng bước.

## 2. Bước bù không phải phép đảo ngược hoàn hảo của một lệnh

Với một phép tính trên biến số, ta dễ hình dung:

~~~text
Thực hiện: balance -= 100
Đảo ngược: balance += 100
~~~

Nhưng nghiệp vụ thực tế không đơn giản như vậy:

- Khách đã nhận email; không thể thu hồi việc họ đã đọc.
- Tiền đã capture; thao tác hoàn tiền có thể tốn thời gian và để lại phí.
- Hàng đã bàn giao đơn vị vận chuyển; không thể coi “hủy order” là tự động chuyển hàng về kho.
- Ghế đã được cấp cho người khác sau khi reservation cũ hết hạn; không được lấy lại ghế chỉ bằng một lệnh SET.
- Giá khuyến mãi và tồn kho đã thay đổi; một yêu cầu checkout mới không thể khôi phục y nguyên toàn bộ môi trường trước đó.

**Compensation** là **một hành động nghiệp vụ có chủ đích nhằm xử lý hậu quả của bước trước**, không nhất thiết hoàn trả toàn bộ thế giới về trạng thái byte-for-byte ban đầu.

| Hành động tiến | Bước bù ứng viên | Vì sao không hoàn toàn là phép nghịch đảo? |
|---|---|---|
| Giữ stock 3 đơn vị | Giải phóng reservation còn HELD | Chỉ hợp lệ nếu chưa chuyển thành COMMITTED/SHIPPED |
| Tạo order PENDING | Chuyển order sang CANCELLED | Giữ dấu vết order, không xóa lịch sử vô điều kiện |
| Authorize tiền | Void/cancel authorization nếu provider hỗ trợ | Kết quả và giới hạn thời gian phụ thuộc provider |
| Capture tiền | Yêu cầu refund, theo dõi trạng thái hoàn tiền | Refund có thể asynchronous, thất bại hoặc mất phí |
| Đăng ký gửi hàng | Hủy yêu cầu nếu hãng chưa nhận xử lý | Nếu hàng đã lấy, cần quy trình hoàn trả khác |
| Gửi email xác nhận | Gửi thông báo điều chỉnh/hủy | Email ban đầu không thể “un-send” chắc chắn |
| Cập nhật read model | Xử lý event điều chỉnh/version mới | Không được ghi đè bản đã tiến xa hơn |

Một bước bù tốt phải trả lời: **bù cho chính tác động nào, dưới điều kiện gì, có định danh gì, đã bù trước đó chưa và xác nhận thành công bằng cách nào?**

## 3. Mô hình hóa quy trình bằng trạng thái, không chỉ bằng danh sách lệnh

Đầu tiên, mô tả **vòng đời order**:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> STOCK_HELD: giữ kho được kiểm chứng
    PENDING --> CANCELLED: dữ liệu/điều kiện không hợp lệ
    STOCK_HELD --> PAYMENT_AUTHORIZED: provider xác nhận
    STOCK_HELD --> RELEASE_PENDING: không thể thanh toán
    PAYMENT_AUTHORIZED --> CONFIRMED: xác nhận đơn
    PAYMENT_AUTHORIZED --> VOID_PENDING: không thể xác nhận
    RELEASE_PENDING --> CANCELLED: giải phóng được kiểm chứng
    VOID_PENDING --> RELEASE_PENDING: void authorization được xác nhận
    CONFIRMED --> REFUND_PENDING: quy trình hủy sau xác nhận
    REFUND_PENDING --> REFUNDED: refund được xác nhận
~~~

Đây là **state machine minh họa**. Không phải hệ nào cũng dùng authorize trước capture; có provider thu tiền ngay, có hệ ship rồi mới capture. Phải chọn trạng thái theo hợp đồng thanh toán thực tế. Một order **CONFIRMED** nhưng muốn hoàn/hủy thường cần quy trình sau xác nhận riêng, không được nhảy ngược về PENDING như chưa từng tồn tại.

Một Saga còn cần **trạng thái của chính tiến trình điều phối**:

~~~text
NEW
RUNNING
WAITING_EXTERNAL_CONFIRMATION
COMPENSATING
COMPLETED
COMPENSATION_PENDING
FAILED_NEEDS_REVIEW
~~~

Không nên chỉ dùng một boolean **success**. Khi worker bị kill sau khi gọi payment, trạng thái **WAITING_EXTERNAL_CONFIRMATION** quan trọng hơn việc trả “false”: nó cho biết **phải kiểm chứng ở provider trước khi gọi lại hay bù**.

### Tách trạng thái order và trạng thái Saga

~~~javascript
// Order domain state — nguồn sự thật của đơn hàng.
{
  _id: "order-9001",
  tenantId: "shop-a",
  status: "STOCK_HELD",
  checkoutRequestId: "req-9001",
  reservationId: "res-9001",
  revision: 4
}

// Saga execution state — tiến độ của workflow.
{
  _id: "saga-9001",
  tenantId: "shop-a",
  orderId: "order-9001",
  status: "RUNNING",
  nextStep: "AUTHORIZE_PAYMENT",
  attempt: 1,
  updatedAt: ISODate("2026-11-14T09:10:00Z")
}
~~~

Việc tách này cho phép một order vẫn có lịch sử nghiệp vụ ổn định trong khi worker đang retry một bước kỹ thuật. Cần xác định nguồn chính của mỗi trạng thái và cách cập nhật chúng nhất quán; không tạo hai trường “trạng thái cuối cùng” có thể tranh nhau quyền quyết định.

## 4. Viết bất biến nghiệp vụ trước khi chọn database

**Bất biến (invariant)** là điều phải luôn đúng theo những trạng thái được phép. Ví dụ:

1. **Không giữ quá tồn:** availableStock không được âm khi hệ nhận reservation.
2. **Một checkout intent không tạo hai order:** cùng tenantId + checkoutRequestId chỉ có một kết quả nghiệp vụ.
3. **Không capture tiền hai lần cho một ý định thanh toán.**
4. **Không giải phóng stock hai lần cho một reservation.**
5. **Không xác nhận order nếu reservation chưa được giữ hợp lệ hoặc không còn hiệu lực.**
6. **Không coi refund là hoàn tất chỉ vì đã gửi request refund.**
7. **Không giao hàng cho order đã hủy trước bước bàn giao theo hợp đồng.**
8. **Mọi quyết định nhạy cảm phải dùng tenant/owner đã được xác thực.**

Bất biến phải được diễn đạt đủ cụ thể để kiểm thử:

~~~text
Invariant:
  Đối với inventory BOOK-01,
  mỗi reservationId chỉ có một hiệu ứng giữ hàng hợp lệ.

Precondition giữ:
  qty là số nguyên dương
  available >= qty
  reservationId chưa tồn tại ở nguồn thẩm quyền

Postcondition giữ:
  reservation trạng thái HELD,
  quantity = qty,
  stock đã giảm/tăng reserved đúng một lần,
  có thể đối chiếu theo reservationId
~~~

Trong hệ phân tán, không phải mọi bất biến có thể được kiểm bằng một phép đọc nhất thời từ nhiều replica. Cần chọn **đơn vị ghi có điều kiện**, **transaction**, hoặc **sổ ghi nhận hiệu ứng** để có bằng chứng đủ mạnh.

## 5. Mẫu hợp đồng chuẩn cho một bước tiến và bước bù

Mỗi bước nên có một đặc tả:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| **stepId** | Đây là bước nào của Saga nào, có định danh ổn định không? |
| **precondition** | Khi nào được phép thực hiện? Dựa vào trạng thái/version nào? |
| **forward action** | Thao tác cụ thể nào tạo hiệu ứng? |
| **forward idempotency key** | Retry có tạo hiệu ứng lần hai không? |
| **success evidence** | Bằng chứng nào xác nhận bước thật sự thành công? |
| **compensation trigger** | Lỗi/ngữ cảnh nào cho phép hoặc yêu cầu bù? |
| **compensation precondition** | Hiệu ứng còn trong trạng thái có thể bù không? |
| **compensation action** | Hành động nghiệp vụ nào xử lý tác động? |
| **compensation idempotency key** | Retry bù có an toàn không? |
| **compensation evidence** | Khi nào được xem là bù xong? |
| **timeout/unknown outcome** | Nếu không biết kết quả, cần hỏi nguồn nào? |
| **escalation** | Khi nào phải chuyển sang xử lý thủ công? |

Ví dụ hợp đồng giữ kho:

~~~yaml
# Đặc tả minh họa, không phải cấu hình tự chạy
step: RESERVE_STOCK
stepId: "saga-9001:reserve:BOOK-01"
sourceOfTruth: inventory-service
identity:
  reservationId: "res-9001-BOOK-01"
  tenantId: "shop-a"
preconditions:
  - "quantity > 0"
  - "availableStock >= quantity"
  - "reservationId chưa được áp dụng, hoặc là replay cùng payload"
forward:
  operation: "conditional reserve"
  idempotencyKey: "reserve:res-9001-BOOK-01"
verifyForward:
  - "reservationId tồn tại và state = HELD"
  - "quantity và orderId trùng ý định gốc"
onFailure:
  - "known-no-stock: không cần release"
  - "unknown-result: query reservation theo reservationId"
compensation:
  precondition: "reservation state = HELD"
  operation: "transition HELD -> RELEASED và hoàn tồn đúng một lần"
  idempotencyKey: "release:res-9001-BOOK-01"
verifyCompensation:
  - "reservation state = RELEASED"
  - "effect release được ghi nhận đúng một lần"
~~~

Điểm đặc biệt: **lỗi giữ kho không đồng nghĩa phải giải phóng kho**. Nếu điều kiện không đủ tồn khiến lệnh chắc chắn không ghi gì, không có gì để bù. Nếu request bị timeout, chưa biết đã giữ hay chưa, phải **kiểm chứng** trước khi hành động.

## 6. Phân loại kết quả của mỗi bước thành ba nhóm

Một API gọi dịch vụ khác không nên chỉ trả success/failure. Ít nhất cần phân biệt:

| Kết quả | Nghĩa | Hành động tiếp theo |
|---|---|---|
| **CONFIRMED_SUCCESS** | Có bằng chứng bước đã tạo hiệu ứng | Tiến bước tiếp hoặc bù nếu Saga phải hủy |
| **CONFIRMED_NO_EFFECT** | Có bằng chứng bước không tạo hiệu ứng | Không bù bước này; xử lý lý do thất bại |
| **UNKNOWN** | Timeout, mất phản hồi, kết quả commit không rõ | Tra cứu/đối soát bằng định danh ổn định; chưa tự kết luận |

Ví dụ:

~~~text
HTTP 409 từ inventory với lý do rõ:
  reservation không thể tạo do không đủ tồn
  -> CONFIRMED_NO_EFFECT nếu hợp đồng bảo đảm

HTTP 200 kèm reservation state HELD:
  -> CONFIRMED_SUCCESS sau khi xác thực response

Timeout sau khi gửi request:
  -> UNKNOWN
  -> GET /reservations/{reservationId} hoặc truy vấn nguồn thẩm quyền
~~~

Ngay cả **HTTP 200** cũng cần được hiểu theo hợp đồng: có API trả “đã nhận yêu cầu” (accepted) nhưng công việc vẫn đang xử lý. Trường hợp đó không phải bằng chứng **business action completed**.

## 7. Ví dụ đầy đủ: tạo order, giữ kho và xử lý thanh toán

Giả sử khách đặt 3 cuốn BOOK-01 với tiền dự kiến 240.000 VND.

~~~text
Thông tin ý định:
  tenantId           shop-a
  checkoutRequestId  req-9001
  orderId            order-9001
  reservationId      res-9001
  paymentIntentId    pay-9001
  amountMinor        240000
  currency           VND
~~~

Các ID này cần được gắn với một **ý định nghiệp vụ ổn định**. Không sinh **paymentIntentId mới** mỗi khi retry sau timeout, nếu điều đó có thể khiến provider tạo nhiều khoản thu.

| Bước | Hành động tiến | Điều kiện kiểm chứng | Bù nếu cần |
|---|---|---|---|
| 1 | Tạo order PENDING | Order tồn tại, checkoutRequestId và payload fingerprint khớp | Mark CANCELLED, giữ audit trail |
| 2 | Giữ stock bằng reservationId | Reservation HELD đúng qty và orderId | Release có điều kiện nếu còn HELD |
| 3 | Authorize payment | Provider báo authorized cho đúng intent, amount/currency | Void authorization nếu hợp đồng cho phép |
| 4 | Xác nhận order | Order CONFIRMED, reservation chuyển COMMITTED | Nếu đã đến điểm không thể đơn giản đảo ngược, dùng cancellation/refund workflow riêng |
| 5 | Phát OrderConfirmed | Event outbox đã lưu và consumer xử lý có checkpoint | Event điều chỉnh/thông báo hủy nếu cần |

**Không nên coi bước 4 và 5 là cùng một lần gửi mạng chắc chắn xảy ra nguyên tử.** Có thể ghi **order CONFIRMED + outbox event** trong cùng transaction DB nếu engine và schema hỗ trợ, rồi consumer phát ra ngoài theo kiểu có thể giao lại. Người nhận cần idempotency.

### Sơ đồ chuỗi tiến

~~~mermaid
sequenceDiagram
    participant U as Client
    participant S as Saga Coordinator
    participant O as Orders
    participant I as Inventory
    participant P as Payment Provider
    U->>S: Checkout(req-9001)
    S->>O: Create PENDING (unique requestId)
    O-->>S: Order exists / verified
    S->>I: Reserve(res-9001, qty=3)
    I-->>S: HELD / verified
    S->>P: Authorize(pay-9001)
    P-->>S: AUTHORIZED / verified
    S->>O: Confirm order + outbox event
    O-->>S: CONFIRMED / verified
    S-->>U: Kết quả đã xác nhận
~~~

Sơ đồ mô tả **đường thuận lợi**; lỗi ở bất cứ vị trí nào có thể dẫn đến trạng thái **WAITING_CONFIRMATION** hoặc **COMPENSATING** thay vì kết thúc tức thì.

## 8. Bù theo thứ tự phù hợp, thường ngược đường tiến

Giả sử:

~~~text
T1: tạo order PENDING       -> thành công
T2: giữ stock               -> thành công
T3: authorize payment       -> thành công
T4: xác nhận order          -> không thể hoàn tất
~~~

Một chiến lược bù có thể là:

~~~text
C3: void payment authorization
    -> kiểm chứng provider đã void/expired hoặc không còn khả năng capture

C2: release reservation
    -> kiểm chứng reservation RELEASED và không hoàn tồn trùng

C1: đánh dấu order CANCELLED
    -> kiểm chứng order ở trạng thái cuối hợp lệ
~~~

**Thứ tự ngược** thường phù hợp khi các bước phụ thuộc nhau, nhưng không phải quy tắc cứng bất kể nghiệp vụ. Nếu thanh toán đã bị capture hoặc hàng đã gửi, bước bù tương ứng có thể cần **refund/return** và xảy ra bất đồng bộ, không thể “đảo ngược transaction” ngay.

Trong lúc bù, hệ thống phải lưu:

~~~text
Saga status: COMPENSATING
Compensation step: VOID_PAYMENT
Compensation attempt: 2
Last observed provider state: AUTHORIZED
Next retry at: ...
~~~

Khi một bước bù bị lỗi, **không được đánh dấu toàn bộ Saga là CANCELLED hoàn chỉnh** nếu vẫn còn hiệu ứng chưa xử lý.

## 9. Bước bù cũng có thể thất bại, timeout và bị gửi lại

Giả sử lệnh release stock gửi thành công nhưng worker mất phản hồi:

~~~text
Worker -> Inventory:
  Release(res-9001)

Inventory:
  HELD -> RELEASED
  available += 3
  reserved -= 3

Mạng:
  response bị mất

Worker:
  retry Release(res-9001)
~~~

Nếu release được viết như **available += 3** không kèm điều kiện, lần retry sẽ hoàn tồn lần thứ hai.

Thiết kế đúng hơn là hành động có **transition điều kiện**:

~~~text
Nếu state = HELD:
  chuyển HELD -> RELEASED
  thực hiện hiệu ứng trả tồn một lần

Nếu state = RELEASED:
  trả lại kết quả đã hoàn tất, không cộng lần nữa

Nếu state = COMMITTED:
  không release kiểu hủy reservation;
  chuyển sang quy trình return/cancellation khác

Nếu không tìm thấy:
  kiểm tra lịch sử/tombstone, không suy đoán stock chưa đổi
~~~

**Bước bù phải idempotent theo hiệu ứng nghiệp vụ**, không chỉ “API có thể gọi nhiều lần mà không ném exception”.

## 10. Bảo vệ hiệu ứng bằng định danh và trạng thái bền vững

Một bản reservation có thể có dạng:

~~~javascript
{
  _id: "res-9001",
  tenantId: "shop-a",
  orderId: "order-9001",
  sku: "BOOK-01",
  quantity: 3,
  status: "HELD",
  version: 1,
  expiresAt: ISODate("2026-11-14T09:30:00Z"),
  releasedAt: null
}
~~~

**reservationId** là khóa duy nhất của một lần giữ, không phải một ID ngẫu nhiên mới mỗi lần retry. **version** hỗ trợ compare-and-set; **status** quyết định chuyển trạng thái nào hợp lệ.

Một state machine:

~~~mermaid
stateDiagram-v2
    [*] --> HELD: reserve có điều kiện
    HELD --> COMMITTED: xác nhận tiêu thụ
    HELD --> RELEASED: bù/hết hạn
    COMMITTED --> [*]
    RELEASED --> [*]
~~~

Điểm quan trọng:

- Không cho **RELEASED → HELD** bằng cách phát lại event cũ.
- Không cho **COMMITTED → RELEASED** như thể hàng chưa từng được sử dụng.
- Nếu cần trả hàng sau COMMITTED, tạo một **return/restock workflow** có định danh riêng.
- Không gộp hai reservation khác nhau chỉ vì cùng orderId nếu nghiệp vụ cho phép giữ nhiều lần/sku; dùng khóa và ranh giới rõ ràng.

## 11. MongoDB: bảo đảm tạo reservation và giảm tồn trong một database

MongoDB có atomicity theo **một document** cho một thao tác ghi. Nếu reservation và inventory ở **hai document**, hai lệnh rời rạc không tự all-or-nothing.

Ví dụ cấu trúc:

~~~javascript
// inventory
{
  _id: "shop-a:BOOK-01",
  tenantId: "shop-a",
  sku: "BOOK-01",
  available: 10,
  reserved: 0
}

// reservations
{
  _id: "res-9001",
  tenantId: "shop-a",
  inventoryId: "shop-a:BOOK-01",
  orderId: "order-9001",
  quantity: 3,
  status: "HELD"
}
~~~

Để **tạo reservation và trừ tồn cùng thành công trong cùng database**, có thể dùng multi-document transaction ở deployment hỗ trợ:

~~~javascript
// Node.js MongoDB driver minh họa.
const session = client.startSession();
const db = client.db("shop");

try {
  await session.withTransaction(async () => {
    const reservations = db.collection("reservations");
    const inventory = db.collection("inventory");

    // _id của reservation là duy nhất. Retry cùng ID
    // không được tự tạo một reservation thứ hai.
    await reservations.insertOne(
      {
        _id: "res-9001",
        tenantId: "shop-a",
        orderId: "order-9001",
        inventoryId: "shop-a:BOOK-01",
        quantity: 3,
        status: "HELD",
        version: 1
      },
      { session }
    );

    const stock = await inventory.updateOne(
      {
        _id: "shop-a:BOOK-01",
        tenantId: "shop-a",
        available: { $gte: 3 }
      },
      {
        $inc: {
          available: -3,
          reserved: 3
        }
      },
      { session }
    );

    if (stock.modifiedCount !== 1) {
      throw new Error("NO_STOCK_OR_MISSING_ITEM");
    }
  });
} finally {
  await session.endSession();
}
~~~

Nếu stock không đủ, transaction không được commit hai thay đổi trên theo cơ chế của MongoDB. Nếu insert reservation gặp duplicate key, transaction cũng không nên được xem là một lần giữ mới hợp lệ. Ứng dụng đọc lại **res-9001** ở nguồn có thẩm quyền để xác định **retry của cùng payload** hay **request dùng lại ID với thông tin khác**.

### Những giới hạn phải nhớ

- **Mọi thao tác của transaction phải truyền session**, và driver/deployment cần được cấu hình đúng.
- Với callback có thể được driver retry, **không gọi provider thanh toán hay gửi email bên trong transaction callback**. Những side effects đó không tự rollback và có thể bị gọi lại.
- Hai inventory items ở hai document cần transaction hoặc reservation workflow phù hợp nếu order yêu cầu giữ tất cả.
- Transaction dài làm tăng tranh chấp, tài nguyên và trường hợp abort; không giữ mở trong lúc chờ người dùng hoặc gọi dịch vụ ngoài.
- Khi commit result không rõ vì lỗi mạng, phải dùng cơ chế retry commit/đối soát đúng driver, không tự tạo reservationId mới.
- Write concern/read concern và replica topology phải được chọn theo mức durability/visibility của nghiệp vụ.

## 12. MongoDB: bù giải phóng tồn bằng transaction có điều kiện

Giả sử worker muốn release **res-9001**. Chuyển trạng thái reservation và hoàn tồn cần được bảo vệ trong cùng phạm vi:

~~~javascript
const session = client.startSession();
const db = client.db("shop");

try {
  await session.withTransaction(async () => {
    const reservations = db.collection("reservations");
    const inventory = db.collection("inventory");

    const reservation = await reservations.findOne(
      {
        _id: "res-9001",
        tenantId: "shop-a",
        status: "HELD"
      },
      { session }
    );

    // Nếu không còn HELD, không hoàn tồn lần nữa.
    if (!reservation) {
      return;
    }

    const transition = await reservations.updateOne(
      {
        _id: reservation._id,
        tenantId: reservation.tenantId,
        status: "HELD",
        version: reservation.version
      },
      {
        $set: {
          status: "RELEASED",
          releasedAt: new Date()
        },
        $inc: { version: 1 }
      },
      { session }
    );

    if (transition.modifiedCount !== 1) {
      throw new Error("RESERVATION_STATE_CHANGED");
    }

    const stock = await inventory.updateOne(
      {
        _id: reservation.inventoryId,
        tenantId: reservation.tenantId,
        reserved: { $gte: reservation.quantity }
      },
      {
        $inc: {
          available: reservation.quantity,
          reserved: -reservation.quantity
        }
      },
      { session }
    );

    if (stock.modifiedCount !== 1) {
      throw new Error("INVENTORY_RECONCILIATION_REQUIRED");
    }
  });
} finally {
  await session.endSession();
}
~~~

Đây là mã **giải thích cấu trúc transaction**, không phải service hoàn chỉnh. Cần quản lý lỗi retry, tính hợp lệ của quantity/inventoryId, phiên bản driver và các trường hợp dữ liệu đã lệch trước đó. Đặc biệt:

- Bản ghi **không còn HELD** không tự có nghĩa đã RELEASED: có thể COMMITTED, thiếu do lỗi hoặc sai tenant; workflow phải **đọc, phân loại và kiểm chứng trạng thái cuối** sau transaction.
- **new Date()** trong callback có thể khác khi callback được retry; nếu cần timestamp nghiệp vụ cố định, phải thiết kế nguồn thời gian/ID thích hợp.
- Tính đúng của update còn dựa trên việc **mọi writer** tuân thủ trạng thái reservation và cách cập nhật inventory.
- Giải phóng stock ở ví dụ chỉ xử lý **một SKU**. Hệ đa kho, nhiều shipment hoặc serial-number cần bất biến phức tạp hơn.

**Điều kiện kiểm chứng cuối** không phải chỉ là “lệnh không ném lỗi”, mà là reservation có trạng thái hợp lệ và hệ thống đã ghi nhận hiệu ứng stock đúng một lần.

## 13. Khi một giao dịch DB không đủ: Saga vẫn phải nhớ bước đã thành công

Giả sử giữ kho và tạo order cùng MongoDB, nhưng authorization nằm ở payment provider. Database transaction không bao trùm provider. Ta lưu một **Saga instance bền vững**:

~~~javascript
{
  _id: "saga-9001",
  tenantId: "shop-a",
  checkoutRequestId: "req-9001",
  orderId: "order-9001",
  status: "WAITING_EXTERNAL_CONFIRMATION",
  stepStates: {
    createOrder: "VERIFIED",
    reserveStock: "VERIFIED",
    authorizePayment: "UNKNOWN",
    confirmOrder: "NOT_STARTED"
  },
  paymentIntentId: "pay-9001",
  version: 5,
  nextAttemptAt: ISODate("2026-11-14T09:12:00Z")
}
~~~

Nếu worker khởi động lại, nó **không bắt đầu từ đầu bằng IDs mới**. Nó đọc saga, kiểm tra bước payment UNKNOWN ở provider theo paymentIntentId rồi quyết định **tiếp tục, bù hoặc chờ thêm**.

Hợp đồng khôi phục:

~~~text
Nếu payment AUTHORIZED:
  tiếp tục bước confirm order

Nếu payment DECLINED với no-effect được xác minh:
  bắt đầu release stock

Nếu provider vẫn PROCESSING hoặc không truy cập được:
  giữ trạng thái UNKNOWN/WAITING,
  retry query status theo backoff;
  không tự capture lần hai

Nếu đã CAPTURED nhưng order không thể confirm:
  chuyển sang refund/exception workflow,
  không giả định void authorization còn hợp lệ
~~~

Đây là **điều kiện kiểm chứng dẫn đường cho Saga**. Không có nó, retry thường trở thành một chuỗi lệnh bù và lệnh tiến theo cảm tính.

## 14. Orchestration và choreography: hai cách điều phối Saga

### Orchestration

Một coordinator lưu trạng thái và quyết định bước kế tiếp:

~~~mermaid
flowchart TD
    S["Saga Coordinator"] --> O["Order Service"]
    S --> I["Inventory Service"]
    S --> P["Payment Service"]
    O --> S
    I --> S
    P --> S
    S --> L["Saga state + retry schedule"]
~~~

Ưu điểm:

- Một nơi thể hiện **toàn bộ luồng** và các điều kiện bù.
- Dễ quan sát Saga nào đang kẹt ở bước nào.
- Dễ triển khai retry, timeout, escalation và quy tắc thứ tự.

Đánh đổi:

- Coordinator có thể trở thành một thành phần cần độ tin cậy cao.
- Dễ tạo luồng trung tâm quá phức tạp nếu Saga ôm quá nhiều nghiệp vụ.
- Cần bảo vệ **concurrent coordinators** không cùng điều khiển một Saga sai thứ tự.

### Choreography

Mỗi service phát/nhận event và tự quyết định bước kế:

~~~mermaid
flowchart LR
    O["OrderCreated"] --> I["Inventory handler"]
    I --> H["StockReserved / StockRejected"]
    H --> P["Payment handler"]
    P --> R["PaymentAuthorized / PaymentFailed"]
    R --> C["Order state handler"]
~~~

Ưu điểm là giảm một orchestrator tập trung và mỗi service có thể sở hữu logic cục bộ. Đánh đổi là luồng tổng thể có thể khó nhìn, khó xác minh vòng lặp event, timeout hoặc các bước bù xuyên dịch vụ.

**Cả hai cách đều phải có durable state, idempotency, kiểm chứng kết quả và reconciliation.** Đổi từ API tuần tự sang event bus không tự tạo tính nguyên tử hoặc exactly-once nghiệp vụ.

## 15. Pseudocode orchestration: hành động được quyết định bởi bằng chứng

Không nên viết:

~~~text
try:
    reserve()
    pay()
    confirm()
catch:
    release()
    refund()
~~~

Vì **catch** có thể xuất hiện khi reserve chưa ghi, pay đã ghi nhưng mất response, hoặc confirm đã commit nhưng worker chưa nhận ack. Bù mù quáng có thể tạo thêm lỗi.

Một dạng pseudocode gần với yêu cầu đúng:

~~~typescript
type StepOutcome = "SUCCESS" | "NO_EFFECT" | "UNKNOWN";

async function runCheckout(sagaId: string) {
  const saga = await loadSagaAuthoritatively(sagaId);

  // Quyền điều phối dựa trên CAS/lease/fencing;
  // không cho hai worker cùng lái một Saga thiếu kiểm soát.
  await assertOrAcquireExecutionOwnership(saga);

  const reserve = await ensureStockReservation(saga);
  if (reserve === "UNKNOWN") {
    await markWaitingAndScheduleVerification(sagaId, "RESERVE");
    return;
  }
  if (reserve === "NO_EFFECT") {
    await cancelPendingOrderIfEligible(saga);
    return;
  }

  const payment = await ensurePaymentAuthorization(saga);
  if (payment === "UNKNOWN") {
    await markWaitingAndScheduleVerification(sagaId, "PAYMENT");
    return;
  }
  if (payment === "NO_EFFECT") {
    await requestReleaseWithIdempotency(saga.reservationId);
    await verifyReleaseAndCancelIfEligible(saga);
    return;
  }

  await confirmOrderWithConditionalWrite(saga);
  await verifyOrderAndPublishThroughOutbox(saga);
}
~~~

Các hàm là **hợp đồng khái niệm**, không phải SDK chạy được ngay. Phần khó nằm bên trong:

- **ensureStockReservation** phải truy vấn theo reservationId khi kết quả chưa biết.
- **ensurePaymentAuthorization** phải dùng cùng paymentIntentId/idempotency key.
- **requestReleaseWithIdempotency** phải tránh hoàn tồn hai lần.
- **verifyReleaseAndCancelIfEligible** phải phân biệt HELD, RELEASED và COMMITTED.
- **confirmOrderWithConditionalWrite** phải kiểm tra trạng thái hợp lệ và chống ghi đè phiên bản mới.
- **verifyOrderAndPublishThroughOutbox** không được phát sự kiện không có căn cứ hoặc mất event giữa commit và publish.

**Không nên giữ một mutex trong bộ nhớ rồi nghĩ đã có quyền điều phối duy nhất.** Nhiều instance, restart và lease hết hạn có thể khiến hai worker cùng chạy; dùng CAS/version hoặc fencing token đáng tin ở nguồn chính.

## 16. Điều kiện trước và sau: formal hóa đủ để kiểm thử

Với một bước tiến **T**, ta có thể mô tả:

\[
P(S) \xrightarrow{T} Q(S')
\]

Trong đó **P** là điều kiện trước trên trạng thái nguồn **S**, **Q** là điều kiện kiểm chứng trên trạng thái **S'** sau thao tác.

Với bước bù **C**:

\[
Q(S') \land E(S') \xrightarrow{C} R(S'')
\]

**E** là điều kiện cho phép bù; **R** là trạng thái sau bù hợp lệ. Không bắt buộc **S'' = S** vì thực tế có thể để lại lịch sử audit, refund record hoặc phí.

Ví dụ:

~~~text
T = ReserveStock
P = available >= 3 và reservationId chưa có
Q = reservation HELD; effect trừ 3 đã ghi nhận

C = ReleaseStock
E = reservation còn HELD và chưa COMMITTED
R = reservation RELEASED; effect hoàn 3 ghi đúng một lần
~~~

Chỉ ghi “sau bước T phải không có lỗi” không phải một **postcondition đủ mạnh**. Cần biểu diễn bằng những field/identity/versions có thể đối chiếu từ nguồn thẩm quyền.

## 17. Không được đọc replica trễ để kết luận bù được phép

Giả sử reservation đã chuyển từ **HELD → COMMITTED** nhưng một read replica đang trễ vẫn trả HELD. Worker bù đọc replica đó rồi kết luận có thể RELEASED.

Nếu lệnh release gửi không có **điều kiện trên nguồn ghi**, nó có thể hoàn tồn stock đã tiêu thụ.

Cách bảo vệ:

1. **Đọc nguồn có mức nhất quán phù hợp** để kiểm chứng, tùy engine.
2. **Quan trọng hơn, đặt precondition trong chính lệnh ghi có điều kiện**, ví dụ status = HELD và version mong đợi.
3. Nếu conditional write thất bại, đọc lại trạng thái mới và **phân loại**, không tự retry cùng hiệu ứng bất kể nguyên nhân.
4. Ghi log sự kiện, version và kết quả để phân biệt **bù đã xong** với **không còn đủ điều kiện bù**.

Một read trước khi write không bảo vệ được race nếu writer khác có thể đổi trạng thái giữa hai thao tác. **Điều kiện kiểm chứng phải dẫn đến điều kiện ghi nguyên tử ở đúng nơi ra quyết định.**

## 18. DynamoDB: bù trên nhiều item bằng transaction có điều kiện

Giả sử **Inventory** và **Reservation** là hai item trong DynamoDB. Đường giữ stock cần:

~~~text
Inventory item:
  PK = INVENTORY#shop-a#BOOK-01
  available = 10
  reserved = 0

Reservation item:
  PK = RESERVATION#res-9001
  state = HELD
  qty = 3
  inventoryKey = INVENTORY#shop-a#BOOK-01
~~~

**TransactWriteItems** là một lựa chọn khi hai item phải cập nhật cùng nhau trong phạm vi hỗ trợ:

~~~text
Reserve transaction:
  Update inventory item:
    condition available >= 3
    SET available = available - 3,
        reserved = reserved + 3

  Put reservation item:
    condition attribute_not_exists(PK)
    state = HELD
    quantity = 3
~~~

Đường bù:

~~~text
Release transaction:
  Update reservation item:
    condition state = HELD AND version = expectedVersion
    SET state = RELEASED, version = version + 1

  Update inventory item:
    condition reserved >= 3
    SET available = available + 3,
        reserved = reserved - 3
~~~

Trong DynamoDB, transaction áp dụng theo điều kiện và giới hạn sản phẩm, không phải giao dịch qua Redis hay payment provider. Nếu transaction bị từ chối do điều kiện, **không được suy rằng stock đã được hoàn**. Nếu timeout chưa rõ kết quả, xác minh reservationId trước khi tạo hiệu ứng mới.

Một thiết kế nên dùng **ClientRequestToken**/idempotency của transaction API theo giới hạn thời gian và ràng buộc payload được tài liệu sản phẩm xác nhận, đồng thời có **logical ID bền vững** ở tầng nghiệp vụ vượt quá cửa sổ token của API. Không phụ thuộc duy nhất vào idempotency ngắn hạn của SDK cho workflow tồn tại nhiều ngày.

## 19. Redis: script nguyên tử chỉ trong phạm vi Redis được hỗ trợ

Nếu inventory nằm trên một key Redis:

~~~redis
SET inventory:shop-a:BOOK-01 10
~~~

Hai client cùng chạy **GET → trừ số lượng → SET** có thể mất cập nhật. Lua/Redis Function hoặc WATCH/MULTI có thể giúp kiểm tra rồi thay đổi key trong một cơ chế không bị chen giữa theo bảo đảm Redis.

~~~lua
-- KEYS[1] = key stock
-- ARGV[1] = quantity dương nguyên
local qty = tonumber(ARGV[1])
local raw = redis.call('GET', KEYS[1])
local current = tonumber(raw)

if not qty or qty <= 0 or qty % 1 ~= 0 then
  return {err = "INVALID_QUANTITY"}
end
if not current then
  return {err = "INVALID_STOCK"}
end
if current < qty then
  return 0
end

redis.call('DECRBY', KEYS[1], qty)
return 1
~~~

Script này bảo vệ điều kiện **stock không âm** trong phạm vi key đó, nhưng **chưa giải quyết**:

- Hai lần retry cùng reservationId sẽ cùng trừ, vì script chưa lưu reservationId.
- Reservation ở MongoDB vẫn có thể chưa tạo nếu worker crash.
- Redis failover/persistence cần cấu hình độ bền phù hợp.
- Script nhiều key trong Redis Cluster có giới hạn hash slot.
- Script có lỗi runtime sau một số lệnh ghi **không có rollback kiểu SQL**.

Nếu muốn reserve/release thật sự idempotent, cần lưu **sổ reservation/transition** trong phạm vi có bảo đảm phù hợp hoặc dùng database nguồn thẩm quyền và coi Redis là cache/read model. Không nên chỉ lưu giá trị stock rồi mong một script có thể biết event nào đã áp dụng.

### TTL không phải bước bù

Giả sử key **hold:res-9001** hết TTL và bị Redis xóa. Điều đó **không tự cộng lại** stock ở MongoDB/DynamoDB, cũng không bảo đảm một hàng đã giữ ở dịch vụ khác được giải phóng. Hết hạn phải có **workflow nghiệp vụ** với trạng thái và điều kiện kiểm chứng; TTL chỉ giúp dọn dữ liệu theo cơ chế lưu trữ.

## 20. Cassandra: LWT bảo vệ một chuyển trạng thái, không tự có Saga toàn cục

Trong Cassandra, một reservation theo khóa:

~~~sql
CREATE TABLE reservations_by_id (
  tenant_id text,
  reservation_id text,
  order_id text,
  state text,
  quantity int,
  version bigint,
  PRIMARY KEY ((tenant_id, reservation_id))
);
~~~

Có thể dùng **INSERT ... IF NOT EXISTS** để chỉ tạo reservation mới khi khóa chưa tồn tại:

~~~sql
INSERT INTO reservations_by_id
  (tenant_id, reservation_id, order_id, state, quantity, version)
VALUES
  ('shop-a', 'res-9001', 'order-9001', 'HELD', 3, 1)
IF NOT EXISTS;
~~~

Bù chuyển trạng thái:

~~~sql
UPDATE reservations_by_id
SET state = 'RELEASED',
    version = 2
WHERE tenant_id = 'shop-a'
  AND reservation_id = 'res-9001'
IF state = 'HELD' AND version = 1;
~~~

Ứng dụng phải đọc kết quả **[applied]**, không tự coi câu lệnh thành công nếu điều kiện sai. LWT có chi phí phối hợp riêng; phải thử nghiệm với contention, read/write consistency và phiên bản Cassandra.

**Điều kiện chuyển HELD → RELEASED trên một row chưa tự hoàn tồn ở một bảng stock khác**. Nếu stock và reservation ở hai bảng/partition, cần thiết kế phối hợp, hạn chế hoặc workflow bù/đối soát theo bảo đảm engine. **BATCH** thông thường không được mặc định là một transaction SQL có isolation và rollback tổng quát xuyên mọi partition.

## 21. Outbox: không mất event sau khi ghi trạng thái nguồn

Lỗi kinh điển:

~~~text
1. Commit order.status = CONFIRMED thành công
2. Process crash trước khi publish OrderConfirmed
3. Shipping/notification không hề nhận event
~~~

Nếu code chỉ:

~~~text
update order
publish event
~~~

thì hai thao tác nằm ở hai hệ thống; không có cam kết nguyên tử tự nhiên.

**Transactional outbox** lưu event cần phát cùng lần commit với thay đổi nguồn, khi database hỗ trợ:

~~~javascript
// Trạng thái order, minh họa
{
  _id: "order-9001",
  status: "CONFIRMED",
  version: 8
}

// Outbox event đã được commit cùng transaction nguồn
{
  _id: "order-9001:confirmed:v8",
  aggregateId: "order-9001",
  aggregateVersion: 8,
  type: "OrderConfirmed",
  payload: { orderId: "order-9001" },
  status: "PENDING"
}
~~~

Worker đọc outbox, publish rồi đánh dấu tiến độ. Nếu worker crash sau khi publish nhưng trước khi đánh dấu, event có thể được publish lại. Vì vậy:

> **Outbox giảm nguy cơ mất event do crash giữa commit và publish, nhưng không tự bảo đảm consumer chỉ nhận đúng một lần.**

Người nhận cần một **inbox/dedup mechanism** và thao tác xử lý idempotent. Chỉ tiêu **“mỗi hiệu ứng nghiệp vụ được áp dụng đúng một lần”** đạt bằng sự kết hợp uniqueness, transaction/conditional update, dedup và reconciliation, không chỉ bằng chế độ giao nhận message.

## 22. Inbox: chống áp dụng lại event khi consumer bị retry

Giả sử consumer nhận **StockReleaseRequested** hai lần:

~~~text
eventId = "release:res-9001:v1"
reservationId = "res-9001"
~~~

Một inbox record:

~~~javascript
{
  _id: "inventory-consumer:release:res-9001:v1",
  consumer: "inventory-consumer",
  eventId: "release:res-9001:v1",
  status: "APPLIED",
  appliedAt: ISODate("2026-11-14T09:20:00Z")
}
~~~

Nhưng **ghi inbox APPLIED rồi mới hoàn tồn** là sai nếu crash giữa hai bước. Tương tự, **hoàn tồn rồi mới ghi inbox** có thể trùng khi retry.

Giải pháp phải đặt **ghi nhận event và hiệu ứng** trong một transaction/đơn vị cập nhật đủ mạnh, hoặc xây workflow có trạng thái cho phép retry và đối soát mà không áp dụng hiệu ứng hai lần. Có thể dùng **reservationId + state transition** làm cơ chế bảo vệ chính, còn inbox là lớp hỗ trợ.

Sự tồn tại của inbox record không tự chứng minh mọi side effect ở database/dịch vụ ngoài đã hoàn tất. Cần định nghĩa rõ **RECEIVED**, **PROCESSING**, **APPLIED**, **FAILED_RETRYABLE** hoặc trạng thái tương đương theo mô hình.

## 23. Event đến sai thứ tự: không để bước bù cũ phá kết quả mới

Timeline:

~~~text
Version 4: reservation HELD
Version 5: reservation COMMITTED

Event đến consumer:
  Commit v5 -> đến trước
  ReleaseRequested v4 -> đến sau
~~~

Nếu consumer chỉ ghi đè **state = RELEASED** theo event sau cùng về mặt thời gian nhận, reservation đã COMMITTED có thể bị “hồi sinh” thành đối tượng còn được phép trả tồn.

Phải dựa vào:

- **State machine**: COMMITTED không chuyển RELEASED theo quy trình bù giữ hàng.
- **Version**: update chỉ khi version còn đúng theo điều kiện.
- **Ý nghĩa event**: ReleaseRequested không đồng nghĩa ReleaseApplied.
- **Định danh hiệu ứng**: cùng reservationId không được hoàn tồn lặp.
- **Nguồn thẩm quyền**: nếu event cũ không còn hợp lệ, bỏ qua hoặc ghi trạng thái xử lý phù hợp.

Đặc biệt, không dùng **event timestamp của máy gửi** thay cho cơ chế version/thứ tự đáng tin trong mọi trường hợp. Đồng hồ giữa dịch vụ có thể lệch; một event cũ được giao chậm không nhất thiết mang timestamp nhỏ hơn chính xác theo thứ tự commit.

## 24. Thanh toán: phân biệt authorize, capture, void và refund

Thanh toán thường là nơi **bước bù không thể chỉ là phép cập nhật âm**.

| Trạng thái/thao tác | Ý nghĩa khái quát | Bước xử lý nếu checkout hủy |
|---|---|---|
| **Payment intent created** | Có định danh yêu cầu thanh toán | Hủy intent nếu provider cho phép; kiểm chứng trạng thái |
| **Authorized** | Provider chấp thuận giữ quyền thu tiền | Void/cancel authorization theo quy tắc provider |
| **Captured/settled** | Tiền đã được thu/xử lý theo chu trình thanh toán | Refund nếu hợp lệ; không gọi void tùy tiện |
| **Refund requested** | Đã yêu cầu hoàn | Theo dõi webhook/poll đến trạng thái cuối |
| **Refund succeeded** | Provider xác nhận hoàn thành theo hợp đồng | Ghi nhận ledger/trạng thái và đối soát |
| **Unknown** | Timeout hoặc dữ liệu provider mâu thuẫn | Truy vấn bằng paymentIntentId; chưa phát lệnh mới mù quáng |

Ví dụ một payment provider trả timeout sau capture. **Không gọi capture lần hai bằng ID mới** và **không tự xem là thất bại**. Phải:

1. Truy vấn trạng thái từ provider bằng ID ổn định.
2. Kiểm tra amount, currency, merchant/tenant, orderId hoặc metadata có thẩm quyền.
3. Nếu đã capture, ghi nhận hiệu ứng và tiếp tục/hủy theo quy trình sau capture.
4. Nếu chắc chắn chưa có hiệu ứng, quyết định retry bằng idempotency key đã xác nhận.
5. Nếu vẫn UNKNOWN, duy trì trạng thái chờ và cảnh báo theo thời hạn nghiệp vụ.

Refund có thể bất đồng bộ, bị giới hạn hoặc cần nhiều lần xử lý. **Bước bù payment phải có Saga con hoặc trạng thái riêng nếu tác động không kết thúc ngay.**

## 25. Những bước không thể bù trực tiếp nên đặt ở đâu?

Ví dụ:

- Gửi email hoặc SMS ra ngoài.
- Phát hành một mã chứng nhận có hiệu lực pháp lý.
- Bàn giao hàng cho đơn vị vận chuyển.
- Xóa dữ liệu cá nhân mà chính sách không cho phép khôi phục.
- Ghi bút toán kế toán đã chốt.

Các bước này có thể **không hoàn tác trực tiếp**. Một chiến lược thiết kế:

1. Hoãn tác động **không thể đảo ngược** cho đến khi những bước có thể thất bại/bù đã được kiểm chứng.
2. Dùng **trạng thái trung gian**: DRAFT, PREPARED, AUTHORIZED trước khi COMMITTED/SHIPPED.
3. Nếu đã tạo tác động, dùng **hành động sửa chữa**: notification điều chỉnh, refund, return, bút toán đối ứng; không xóa lịch sử.
4. Xác định **điểm không thể quay lại** (point of no return) để chuyển từ Saga “hủy trước xác nhận” sang **quy trình hậu mãi/hoàn trả**.
5. Ghi audit trail với actor, thời điểm, reason, references và bằng chứng.

Không thể bù không có nghĩa hệ phải chấp nhận sai. Nó có nghĩa **mục tiêu khắc phục** là một trạng thái hợp lệ mới, không phải phủ nhận tác động đã xảy ra.

## 26. Điều kiện kiểm chứng phải dùng nguồn có thẩm quyền

Một ứng dụng có thể có:

~~~text
orders             -> nguồn trạng thái order
reservations        -> nguồn quyền giữ kho
payment provider    -> nguồn trạng thái tiền
Redis cache         -> thẻ hiển thị cho khách
search index        -> tìm kiếm đơn
analytics warehouse -> báo cáo theo giờ/ngày
~~~

Nếu mục tiêu là kiểm tra **“đã thu tiền chưa?”**, một thẻ Redis ghi paymentStatus=PAID không đủ bằng chứng trong trường hợp yêu cầu có tính quyết định. Phải dùng trạng thái/payment record đã được đối soát với provider theo hợp đồng.

Nếu mục tiêu là **“đã hoàn tồn chưa?”**, cần đọc reservation transition và inventory effect từ nguồn kho, không chỉ tin một event **ReleaseRequested** đã gửi.

Nếu mục tiêu là **“đã gửi thông báo chưa?”**, phải phân biệt **message published**, **message delivered to provider** và **người dùng đã nhận/đọc**; không được tự đồng nhất chúng.

Điều kiện kiểm chứng tốt có dạng:

~~~text
Verify(reservationId):
  record thuộc đúng tenant/order
  quantity và sku trùng ý định
  status đúng theo state machine
  version/transitionId chứng minh hiệu ứng mới nhất
  nguồn đọc có mức nhất quán phù hợp
~~~

Một read replica trễ, event queue và cache có thể cung cấp tín hiệu để quan sát, nhưng **điều kiện bảo vệ ghi** vẫn phải nằm ở nơi thực hiện thay đổi với cơ chế atomic/conditional write phù hợp.

## 27. Timeout không phải điều kiện mặc định để bù

Giả sử:

~~~text
reserve stock -> HTTP timeout
~~~

Có hai khả năng:

~~~text
Khả năng A:
  request chưa được áp dụng

Khả năng B:
  request đã được áp dụng, response bị mất
~~~

Nếu ngay lập tức gửi release:

- Ở A, release có thể báo không tìm thấy, nhưng nếu ID chưa được bảo vệ có thể tạo lỗi logic.
- Ở B, release có thể hợp lệ **nếu Saga quyết định hủy**, nhưng nếu callback cũ đến muộn và Saga lại tiếp tục, ta có thể vừa xác nhận vừa release.

Một thuật toán an toàn hơn:

~~~mermaid
flowchart TD
    A["Bước tiến timeout"] --> B["Đánh dấu outcome UNKNOWN"]
    B --> C["Query authoritative state bằng stable ID"]
    C --> D{"Bằng chứng nào?"}
    D -->|"Đã áp dụng"| E["Ghi SUCCESS rồi tiếp tục hoặc bù có điều kiện"]
    D -->|"Chắc chắn không áp dụng"| F["Ghi NO_EFFECT, quyết định retry/hủy"]
    D -->|"Vẫn chưa rõ"| G["Backoff, retry verification, alert/escalate"]
    E --> H["Dùng CAS và state machine"]
    F --> H
    G --> C
~~~

**Retry verification** có thể nhiều lần vì provider eventual hoặc đang xử lý. Hệ phải có deadline/escalation, nhưng đến deadline không có nghĩa có thể tùy tiện tuyên bố **no-effect**. Những trạng thái UNKNOWN liên quan tiền cần quy trình đối soát riêng.

## 28. Tránh race giữa hủy và xác nhận

Một khách bấm **Hủy**, trong lúc payment webhook báo **AUTHORIZED**.

~~~text
Cancel worker:
  đọc order STOCK_HELD
  muốn chuyển CANCEL_PENDING

Payment worker:
  đọc order STOCK_HELD
  muốn chuyển CONFIRMED
~~~

Nếu cả hai dùng **$set status** không điều kiện, tác vụ đến sau có thể ghi đè tác vụ trước.

Một update MongoDB theo trạng thái dự kiến:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "order-9001",
    tenantId: "shop-a",
    status: "STOCK_HELD",
    revision: 4
  },
  {
    $set: {
      status: "CANCEL_PENDING"
    },
    $inc: { revision: 1 }
  }
);

if (result.matchedCount !== 1) {
  print("Trạng thái đã đổi; phải đọc lại và quyết định theo state machine");
}
~~~

Worker xác nhận cũng cần điều kiện tương ứng. **Chỉ một chuyển đổi từ revision 4 được chấp nhận**; worker thua race không được bật upsert, ghi đè hay tự chạy bù khi chưa biết trạng thái mới.

Nếu payment provider đã authorize ngoài database trước khi worker thua race, payment effect vẫn tồn tại và cần **void/compensation** theo trạng thái được kiểm chứng, không được giả vờ lệnh CAS thất bại là provider chưa làm gì.

## 29. Execution ownership: lease và fencing token

Saga có thể được xử lý bởi nhiều worker sau restart hoặc failover. Nếu chỉ dùng “worker A đang chạy” trong bộ nhớ, khi A chậm và B thay thế, cả hai có thể tiếp tục cùng Saga.

Một pattern:

~~~javascript
{
  _id: "saga-9001",
  status: "RUNNING",
  leaseOwner: "worker-b",
  leaseUntil: ISODate("2026-11-14T09:15:00Z"),
  fencingToken: NumberLong("42"),
  revision: 12
}
~~~

**Lease** có thời hạn để worker khác có thể nhận lại khi owner chết. Nhưng worker A đã mất lease có thể tỉnh dậy và vẫn gửi command cũ.

**Fencing token** là số phiên bản quyền điều phối tăng đơn điệu; các hệ đích có khả năng kiểm soát phù hợp phải từ chối yêu cầu dùng token cũ. Nếu dịch vụ đích không hiểu fencing token, chỉ có lease trong coordinator **không tự bảo vệ side effect ngoài hệ**. Khi đó cần idempotency key, version/conditional transition ở đích và kiểm chứng.

Một quy tắc:

~~~text
Worker A token 41 bị pause.
Worker B nhận token 42, xử lý và commit.
Worker A tỉnh dậy, gửi token 41.
Hệ đích phải từ chối token cũ nếu dùng fencing.
~~~

Đừng coi **lock TTL** là bằng chứng duy nhất chống double payment. Bảo đảm cuối cùng phải gắn với logical paymentIntentId và điều kiện của provider/nguồn thẩm quyền.

## 30. Version hóa Saga và tránh chuyển trạng thái “quay ngược”

Trạng thái có thể đổi:

~~~text
RUNNING v5 -> COMPENSATING v6 -> CANCELLED v7
~~~

Một event cũ báo **ReserveSucceeded** không được đưa Saga từ CANCELLED trở lại RUNNING. Bảo vệ bằng:

1. Transition table: trạng thái nào được chuyển sang trạng thái nào.
2. Compare-and-set trên **status + revision** khi ghi.
3. Stable eventId và source version để chống replay/out-of-order.
4. Lưu lịch sử transition/attempt quan trọng để điều tra.
5. Không dùng “event nhận sau thì đúng hơn” thay cho thứ tự cam kết nghiệp vụ.

Ví dụ version-aware update:

~~~javascript
db.sagas.updateOne(
  {
    _id: "saga-9001",
    status: "RUNNING",
    revision: 5
  },
  {
    $set: {
      status: "COMPENSATING",
      nextStep: "RELEASE_STOCK"
    },
    $inc: { revision: 1 }
  }
);
~~~

Nếu **matchedCount = 0**, đọc lại Saga thay vì tự tạo bản mới. Upsert trên filter status/version có thể tạo nhánh insert sai khi bản ghi tồn tại nhưng không khớp trạng thái.

## 31. Quản lý trạng thái tiến trình và lịch sử thao tác

Một Saga cần đủ dữ liệu phục hồi nhưng không nên biến thành một document vô hạn. Một cấu trúc ứng viên:

~~~javascript
// Collection sagas: trạng thái hiện tại
{
  _id: "saga-9001",
  tenantId: "shop-a",
  type: "CHECKOUT",
  status: "COMPENSATING",
  orderId: "order-9001",
  checkoutRequestId: "req-9001",
  revision: 9,
  nextStep: "RELEASE_STOCK",
  nextAttemptAt: ISODate("2026-11-14T09:25:00Z")
}

// Collection saga_attempts: lịch sử có ID riêng
{
  _id: "saga-9001:release-stock:attempt-2",
  sagaId: "saga-9001",
  step: "RELEASE_STOCK",
  effectId: "release:res-9001",
  outcome: "UNKNOWN",
  observedAt: ISODate("2026-11-14T09:20:00Z"),
  reasonCode: "NETWORK_TIMEOUT"
}
~~~

Lưu attempt riêng giúp không làm phình document Saga theo thời gian, đồng thời hỗ trợ audit, debug và đối soát. Cần quy định retention, thông tin nhạy cảm được phép log và cách truy vấn theo sagaId.

Đừng lưu **full credit-card payload**, thông tin bí mật hoặc dữ liệu cá nhân không cần thiết vào saga log. Chỉ lưu ID tham chiếu và dữ liệu tối thiểu để xác minh.

## 32. Chính sách retry: lặp đúng bước, không lặp hiệu ứng

Không phải lỗi nào cũng retry:

| Loại kết quả | Ví dụ | Hành động |
|---|---|---|
| **Tạm thời, chưa rõ** | Timeout, 503, mất kết nối | Verify outcome; retry với stable ID/backoff khi phù hợp |
| **Điều kiện ghi không đạt** | Không đủ stock, revision đổi | Không retry mù; đọc trạng thái và quyết định |
| **Payload không hợp lệ** | Quantity âm, currency sai | Từ chối/sửa dữ liệu; không retry vô hạn |
| **Trùng ID cùng payload** | Replay cùng checkoutRequestId | Trả kết quả trước đó hoặc tiếp tục Saga |
| **Trùng ID khác payload** | Cùng key nhưng amount khác | Conflict; điều tra ý định |
| **Rate limit/throttling** | Provider giới hạn request | Backoff, jitter, tôn trọng Retry-After nếu có |
| **Bù đang xử lý** | Refund PROCESSING | Poll/consume webhook, không tạo refund mới |
| **Lỗi không thể tự phục hồi** | Sai lịch sử ledger, mất mapping | Quarantine/FAILED_NEEDS_REVIEW và on-call |

Exponential backoff có jitter giúp tránh nhiều worker cùng dồn request vào service vừa hồi phục, nhưng phải đặt giới hạn và deadline theo SLA của nghiệp vụ. Ví dụ bù stock có thể cần xử lý sớm trước khi chuyển sang bán hàng, trong khi refund có thể có thời gian xử lý dài hơn nhưng cần thông tin minh bạch cho khách.

**Retry kỹ thuật** và **tạo yêu cầu nghiệp vụ mới** là hai chuyện khác nhau. Lặp cùng paymentIntentId không được biến thành hai payment intents mới.

## 33. Deadline, timeout và yêu cầu hủy

Một Saga có thể có:

~~~text
checkoutStartedAt = 09:00
reservationExpiresAt = 09:15
paymentVerificationDeadline = 09:20
manualEscalationAt = 09:30
~~~

Các mốc có ý nghĩa khác nhau:

- **reservationExpiresAt** xác định quyền giữ có còn hợp lệ không, không chỉ thời điểm key được TTL dọn.
- **paymentVerificationDeadline** là mốc đổi cách xử lý (tăng cảnh báo/đối soát), không phải bằng chứng payment thất bại.
- **manualEscalationAt** cho biết khi nào cần con người hoặc job đối soát chuyên biệt.

Một timeout không tự kích hoạt việc xóa dữ liệu hay refund. Điều kiện hủy phải xét trạng thái Saga, order, stock và payment đã được kiểm chứng theo quy tắc.

Nếu có event **late PaymentAuthorized** sau khi Saga đã bắt đầu bù, handler phải tra trạng thái mới nhất và xử lý theo hướng **void/refund hoặc khôi phục có điều kiện**, không tự đưa order trở lại CONFIRMED bất kể việc hủy đã tiến đến đâu.

## 34. Đối soát (reconciliation) là lớp an toàn bắt buộc

Ngay cả khi mọi API đều có retry và event IDs, vẫn có thể xảy ra:

- Consumer ngừng lâu hơn thời gian retention của event log.
- Lỗi lập trình khiến một số sự kiện không được tạo.
- Một hệ đích trả trạng thái UNKNOWN kéo dài.
- Bản read model bị rebuild thiếu.
- Một workflow migration bỏ qua vài record.
- Operator thực hiện thao tác thủ công không theo pipeline.

Vì vậy cần **reconciliation job** đối chiếu những trạng thái quan trọng giữa các nguồn:

~~~text
Order CONFIRMED
  -> có reservation COMMITTED đúng order/sku/quantity?
  -> có payment AUTHORIZED/CAPTURED phù hợp hợp đồng?
  -> có event xác nhận được ghi/publish?

Order CANCELLED
  -> reservation còn HELD không?
  -> có payment chưa void hoặc refund chưa hoàn tất không?

Reservation RELEASED
  -> hiệu ứng hoàn tồn đã được ghi nhận một lần?

Saga WAITING quá lâu
  -> có nguồn nào xác nhận kết quả chưa?
~~~

Reconciliation không được âm thầm “sửa” mọi mâu thuẫn bằng giá trị đoán. Với tiền, quyền hoặc tồn kho, cần **source precedence**, event log/ledger và quy tắc phê duyệt rõ.

### Kết quả đối soát nên phân loại

| Nhóm | Ý nghĩa | Ví dụ hành động |
|---|---|---|
| **CONSISTENT** | Các nguồn phù hợp bất biến | Không sửa |
| **EXPECTED_LAG** | Chưa hội tụ nhưng còn trong SLO | Theo dõi và chờ |
| **RETRYABLE_DRIFT** | Thiếu event/read model có thể dựng lại | Replay/backfill có kiểm soát |
| **REQUIRES_COMPENSATION** | Hiệu ứng thật còn tồn tại và đủ điều kiện bù | Mở/resume compensation workflow |
| **AMBIGUOUS** | Chưa xác định nguồn sự thật hoặc trạng thái tiền | Khóa tự động, điều tra |
| **VIOLATION** | Bất biến bị phá, nguy cơ tiền/tồn/quyền | Cảnh báo khẩn, khắc phục có audit |

## 35. Đo tính đúng qua metrics, không chỉ qua số HTTP 200

| Metric ứng viên | Câu hỏi |
|---|---|
| **saga_started_total** | Có bao nhiêu ý định nghiệp vụ mới? |
| **saga_completed_total** | Bao nhiêu Saga đạt trạng thái cuối hợp lệ? |
| **saga_compensating_total** | Bao nhiêu Saga đang chạy bước bù? |
| **saga_failed_needs_review_total** | Bao nhiêu cần can thiệp thủ công? |
| **step_unknown_outcome_total** | Có bao nhiêu kết quả chưa rõ cần verification? |
| **step_verification_latency** | Mất bao lâu để xác định kết quả thật? |
| **compensation_attempt_total** | Bước bù phải thử bao nhiêu lần? |
| **compensation_duplicate_suppressed_total** | Bao nhiêu retry được chặn khỏi tạo hiệu ứng mới? |
| **reservation_orphan_count** | Reservation HELD không có order sống tương ứng? |
| **confirmed_order_without_payment_count** | Có đơn xác nhận nhưng payment thiếu theo hợp đồng? |
| **payment_unknown_age** | Bao lâu vẫn chưa biết kết quả tiền? |
| **outbox_backlog / inbox_retry_count** | Event bị dồn hoặc xử lý lại bao nhiêu? |
| **reconciliation_mismatch_count** | Có bao nhiêu vi phạm/lệch trạng thái? |
| **workflow_p95/p99_completion_time** | Trải nghiệm khách và khả năng đáp ứng SLA |

Không phải engine tự có những metric này. Nhiều chỉ số cần tạo ở tầng Saga coordinator, dịch vụ kho/payment và job đối soát. Nên dùng **tenantId, sagaId, orderId, reservationId, paymentIntentId, stepId** làm trace dimensions theo chính sách bảo mật; tránh đưa thông tin nhạy cảm vào metric labels có cardinality không kiểm soát.

**Một Saga chạy xong nhanh nhưng hoàn tồn hai lần là thất bại nghiêm trọng hơn Saga chậm vài giây mà bảo toàn đúng bất biến.**

## 36. Mẫu ma trận lỗi và điều kiện xử lý

| Điểm lỗi | Bằng chứng có thể có | Điều cần làm | Không được làm |
|---|---|---|---|
| Trước khi tạo order | Chưa có order/request ID | Có thể thử create-only cùng logical ID | Tạo ID khác mỗi retry |
| Sau commit order, mất response | Order có thể đã tồn tại | Đọc theo checkoutRequestId, so payload | Insert order mới vô điều kiện |
| Reserve bị từ chối do stock | No-effect được xác nhận | Cancel order PENDING phù hợp | Release stock chưa giữ |
| Reserve timeout | Trạng thái chưa rõ | Query reservationId | Trừ stock lại bằng ID khác |
| Payment declined | No-effect/declined được xác nhận | Release reservation có điều kiện | Refund khoản chưa capture |
| Payment timeout | UNKNOWN | Query provider bằng intent ổn định | Retry charge bằng ID mới |
| Payment authorized, confirm order lỗi | Provider đã authorize | Retry confirm hoặc void nếu hủy, theo state | Giả vờ payment không có hiệu ứng |
| Order CONFIRMED, publish event lỗi | Outbox đã ghi nếu đúng thiết kế | Republish từ outbox, inbox dedup | Rollback order vì message broker chậm |
| Release timeout | Không rõ release đã áp dụng | Kiểm tra reservation state/effect | Cộng stock lần hai mù quáng |
| Refund processing lâu | Provider chưa final | Poll/webhook/reconcile, báo trạng thái | Mark REFUNDED ngay khi gửi lệnh |
| Late event cũ | Version thấp hơn state nguồn | Bỏ qua hoặc ghi nhận stale, reconcile | Ghi đè version mới |
| Worker lease hết hạn | Owner có thể đã đổi | Dừng, dùng fencing/CAS | Worker cũ tiếp tục bất kể ownership |

Ma trận này có thể chuyển thành **runbook và automated decision table**. Mỗi nhánh phải có định nghĩa “bằng chứng đủ” phù hợp từng nguồn dữ liệu.

## 37. Bảo mật, đa tenant và quyền của Saga worker

Một worker có thể có quyền mạnh: tạo order, điều chỉnh stock, void/refund và thay trạng thái. Nếu không kiểm soát, bước bù có thể trở thành đường sửa dữ liệu ngoài quyền.

Nguyên tắc:

1. **tenantId/merchantId** của Saga xuất phát từ ngữ cảnh đã được xác thực, không tin nguyên một field trong message bên ngoài.
2. Mỗi lệnh bù kiểm tra **resource thuộc đúng tenant và order**, không chỉ reservationId khớp tên.
3. **Payment intent** phải khớp merchant, amount, currency và order reference trước khi quyết định void/refund.
4. Worker chỉ có **quyền tối thiểu** cần cho bước được giao; thao tác thủ công có audit và phê duyệt theo mức rủi ro.
5. **Idempotency keys** cần tránh va chạm giữa tenant; unique constraint phản ánh scope.
6. Ghi log ID, status và reason code, hạn chế PII, token, thông tin thẻ hoặc dữ liệu bí mật.
7. Việc xóa dữ liệu cá nhân hoặc hết retention không được phá trạng thái tối thiểu cần để chống replay theo chính sách hợp lệ.

**Transaction/atomicity không tự thay thế authorization.** Một lệnh update sai tenant vẫn có thể được database thực hiện rất nguyên tử nếu filter và quyền không được kiểm tra.

## 38. Các hiểu nhầm phổ biến

| Nhầm lẫn | Vì sao nguy hiểm | Cách hiểu đúng |
|---|---|---|
| “Saga tự rollback mọi bước đã làm” | Payment/email/shipping không có phép nghịch đảo hoàn hảo | Bù là hành động nghiệp vụ riêng |
| “Hễ timeout là gọi bước bù” | Thao tác có thể chưa hoặc đã thành công | Phân loại UNKNOWN, query nguồn trước |
| “Bước bù chỉ cần cộng lại số đã trừ” | Retry có thể hoàn hai lần | Điều kiện HELD → RELEASED và effect ID |
| “Có transaction local thì toàn checkout nguyên tử” | HTTP/payment/service khác nằm ngoài transaction | Saga và reconciliation cho phần ngoài |
| “Ghi Saga SUCCESS là mọi tác động đã đúng” | Ghi trạng thái có thể đi trước hiệu ứng thật | Bằng chứng hậu điều kiện |
| “Có outbox thì consumer nhận đúng một lần” | Publish có thể lặp sau crash | Inbox/dedup và idempotent effect |
| “Inbox đã ghi là hiệu ứng đã áp dụng” | Crash giữa ghi inbox và thay đổi nghiệp vụ | Cùng transaction hoặc workflow kiểm chứng |
| “Event nhận sau luôn mới hơn” | Sự kiện có thể đến sai thứ tự | State/version/CAS |
| “Đã gọi refund là đã hoàn tiền” | Provider có thể processing/failed | Theo dõi trạng thái cuối |
| “Payment timeout nghĩa là chưa thu” | Response có thể bị mất sau capture | Query provider theo intent |
| “Đọc cache thấy HELD thì cứ release” | Cache/replica có thể trễ | Conditional transition tại nguồn |
| “TTL xóa hold sẽ tự trả tồn” | TTL dọn key, không chạy bù xuyên hệ | Reservation-expiry workflow |
| “Dùng một lock TTL sẽ không có hai worker” | Lease hết hạn và worker cũ có thể tiếp tục | Fencing/CAS/idempotency tại đích |
| “Có retry vô hạn là sẽ tự hồi phục” | Permanent error, phí và backlog có thể tăng | Phân loại lỗi, backoff, deadline, escalation |
| “Hủy order là xóa document” | Mất audit, khó refund/đối soát | Trạng thái hủy và lịch sử hiệu ứng |
| “Có thể bù COMMITTED như HELD” | Hàng/ghế có thể đã sử dụng | Quy trình return/refund riêng |
| “Mọi bước bù phải theo thứ tự đảo ngược cứng” | Phụ thuộc và trạng thái bên ngoài có thể khác | Định nghĩa thứ tự theo nghiệp vụ |
| “Chỉ cần test happy path” | Lỗi thường ở timeout/retry/đồng thời | Fault injection và invariant-based tests |

## 39. Quy trình thiết kế có thể tái sử dụng

~~~mermaid
flowchart TD
    A["Liệt kê các hiệu ứng nghiệp vụ"] --> B["Viết bất biến, nguồn sự thật, identity"]
    B --> C["Xác định boundary atomic/transaction của từng bước"]
    C --> D["Mô tả precondition và postcondition kiểm chứng"]
    D --> E["Định nghĩa state machine và điểm không thể bù"]
    E --> F["Thiết kế bù + điều kiện đủ để bù"]
    F --> G["Stable keys + CAS + idempotency"]
    G --> H["Durable Saga state + outbox/inbox"]
    H --> I["Timeout: SUCCESS / NO_EFFECT / UNKNOWN"]
    I --> J["Retry, compensation, escalation"]
    J --> K["Fault injection + reconciliation + metrics"]
~~~

Các bước thực hiện:

1. **Vẽ luồng có tác động thật:** tạo order, giữ stock, authorize/capture, tạo shipment, gửi event.
2. **Liệt kê từng nguồn thẩm quyền:** ai quyết định stock, payment, trạng thái đơn và tình trạng giao hàng.
3. **Viết bất biến kiểm chứng được:** không oversell, không double charge, không double release, không xác nhận thiếu điều kiện.
4. **Chọn atomic boundary nhỏ nhất đủ bảo vệ** cho từng bước: một document/item, conditional write, transaction nhiều item hoặc một service có idempotency.
5. **Đặt ID ổn định:** checkoutRequestId, orderId, reservationId, paymentIntentId, stepId, compensationId.
6. **Định nghĩa precondition, success evidence, trạng thái UNKNOWN** trước khi viết mã.
7. **Thiết kế compensation cho từng hiệu ứng thực sự đã áp dụng**, có condition, version và verify.
8. **Tách bước có thể bù với bước không thể đảo ngược**, xác định trạng thái refund/return/escalation.
9. **Lưu Saga/attempts/outbox/inbox bền vững**, không phụ thuộc RAM của một worker.
10. **Bảo vệ ghi đồng thời:** CAS, unique key, state machine và ownership/fencing khi phù hợp.
11. **Kiểm thử lỗi từng điểm:** crash trước/sau commit, timeout, duplicate, out-of-order, failover.
12. **Đối soát định kỳ và theo dõi metrics**, có runbook xử lý Saga kẹt.

## 40. Bài tập thực hành

### Bài tập 1 — Xác định phạm vi transaction

Một hệ có order ở MongoDB, inventory ở DynamoDB và payment qua HTTPS. Hãy xác định bước nào có thể được bảo vệ bằng transaction/conditional write cục bộ, bước nào bắt buộc có workflow liên dịch vụ. Giải thích vì sao transaction MongoDB không thể tự hoàn tiền ở provider.

### Bài tập 2 — Lập bảng bước tiến và bước bù

Với quy trình **tạo order → giữ stock → authorize payment → xác nhận order**, hãy lập bảng gồm **precondition, forward action, postcondition, compensation trigger, compensation precondition, compensation effect, verification** cho từng bước.

### Bài tập 3 — Reserve stock khi tồn ít

Inventory có available=5. Hai checkout cùng muốn 4. Thiết kế lệnh giữ kho có điều kiện và reservationId ổn định. Giải thích vì sao cách GET rồi SET hoặc hai lệnh $inc không điều kiện có thể oversell.

### Bài tập 4 — Retry release

Reservation res-101 đã được RELEASED, nhưng worker chưa nhận response và retry. Hãy viết state transition/condition khiến stock chỉ được hoàn một lần, rồi mô tả kết quả đúng với các trạng thái **HELD**, **RELEASED**, **COMMITTED** và **UNKNOWN**.

### Bài tập 5 — Payment timeout

Provider không trả lời sau khi nhận **capture(pay-9001)**. Hãy thiết kế quy trình kiểm chứng bằng paymentIntentId. Nêu những trường hợp **CAPTURED**, **DECLINED/NO_EFFECT**, **PROCESSING** và **không truy cập được provider**, cũng như khi nào được phép tạo refund.

### Bài tập 6 — Không thể đảo ngược email

Email xác nhận đã được gửi nhưng order sau đó phải hủy. Vì sao không thể coi gửi email có rollback? Đề xuất bước thông báo điều chỉnh, dấu vết audit và vị trí phù hợp của thông báo trong workflow.

### Bài tập 7 — MongoDB transaction

Thiết kế transaction tạo reservation và giảm available trong hai document. Cho biết điều gì xảy ra khi stock không đủ, khi insert reservation trùng ID và khi callback bị retry. Giải thích vì sao không gọi payment provider bên trong transaction callback.

### Bài tập 8 — DynamoDB item và compensation

Inventory và Reservation nằm ở hai items. Viết outline **TransactWriteItems** cho reserve và release với ConditionExpression phù hợp. Nếu release bị từ chối do reservation đã COMMITTED, ứng dụng phải quyết định thế nào?

### Bài tập 9 — Cassandra LWT

Một reservation có state HELD, version 3. Hãy viết CQL **UPDATE ... IF state='HELD' AND version=3** để chuyển sang RELEASED. Giải thích cách đọc [applied] và vì sao LWT trên reservation không tự hoàn tồn trong một service khác.

### Bài tập 10 — Redis script và TTL

Redis lưu available theo key, reservation ở một database khác. Viết Lua/script logic kiểm tra đủ tồn rồi trừ. Nêu hai rủi ro khi retry script và khi key reservation hết TTL, cùng cách tổ chức nguồn thẩm quyền để tránh double release.

### Bài tập 11 — Outbox crash window

Order đã COMMITTED nhưng process chết trước khi publish **OrderConfirmed**. Mô tả cách outbox lưu cùng transaction, publish với retry và consumer inbox chống áp dụng lại. Tại sao “outbox gửi ít nhất một lần” vẫn cần idempotency ở consumer?

### Bài tập 12 — Inbox crash window

Consumer đánh dấu event APPLIED trước khi cập nhật inventory, rồi crash. Hãy giải thích lỗi bỏ sót hiệu ứng. Thiết kế lại bằng transaction hoặc transition idempotent có kiểm chứng.

### Bài tập 13 — Event sai thứ tự

Consumer nhận **CommitReservation v5** rồi **ReleaseReservation v4**. Hãy định nghĩa state machine/version check để không hoàn tồn một reservation đã COMMITTED. Nếu một event chỉ là **Request**, vì sao không được tự hiểu là **Applied**?

### Bài tập 14 — Concurrent cancel và confirm

Order đang STOCK_HELD, revision 7. Worker cancel và payment webhook cùng muốn đổi trạng thái. Hãy viết hai conditional updates cạnh tranh trên revision 7 và mô tả cách xử lý của worker không match. Phần payment đã authorize ngoài DB phải xử lý thế nào?

### Bài tập 15 — Lease và fencing

Worker A có fencingToken=10, bị pause. Worker B nhận token=11 và hoàn tất bước reserve. Sau đó A tỉnh dậy. Hãy giải thích vì sao lease TTL chưa đủ, hệ đích cần kiểm tra gì và idempotency key giúp gì khi provider không hỗ trợ fencing.

### Bài tập 16 — Kiểm chứng sau bù

Saga báo order CANCELLED, nhưng inventory vẫn còn một reservation HELD và payment đang PROCESSING. Hãy lập các điều kiện **không cho phép mark Saga fully compensated** và đề xuất job đối soát.

### Bài tập 17 — Phân loại lỗi

Cho các sự kiện: stock insufficient, request timeout, provider trả 429, duplicate reservationId khác quantity, refund đang PROCESSING, MongoDB revision mismatch. Hãy phân loại **NO_EFFECT**, **UNKNOWN**, **RETRYABLE**, **CONFLICT** hoặc **REQUIRES_REVIEW** và hành động tương ứng.

### Bài tập 18 — Thiết kế trạng thái Saga

Viết schema cho **sagas** và **saga_attempts** gồm sagaId, tenantId, orderId, status, step states, effectId, revision, nextAttemptAt, lease/fencing và outcome. Cho biết field nào cần unique index hoặc conditional update, và cách tránh tạo document vô hạn.

### Bài tập 19 — Fault injection

Lập test plan cố tình gây crash ở sáu thời điểm: trước reserve, sau reserve trước response, sau payment authorize, sau order confirm trước outbox publish, sau release trước ack, trong lúc consumer nhận event trùng. Với mỗi trường hợp, viết **trạng thái cuối được phép** và **bằng chứng kiểm chứng**.

### Bài tập 20 — Thiết kế một runbook vận hành

Viết runbook cho Saga checkout bị kẹt **WAITING_EXTERNAL_CONFIRMATION** hơn 30 phút. Nội dung tối thiểu gồm truy vấn nguồn thẩm quyền, kiểm tra ID/payload, thứ tự ưu tiên bảo vệ tiền và stock, tiêu chí retry/bù/escalate, ghi nhận audit, thông báo cho khách và đối soát cuối.

---

**Kết luận:** Thiết kế nghiệp vụ có bước bù trong NoSQL không phải thêm một khối **catch → rollback** cho mọi lỗi. Đó là việc **mô hình hóa các hiệu ứng có thể tồn tại độc lập**, xác định rõ **bất biến và nguồn sự thật**, rồi bảo vệ từng thay đổi bằng **atomic/conditional write** trong ranh giới phù hợp. Khi vượt ranh giới giao dịch, Saga phải lưu trạng thái, dùng **ID ổn định, precondition, postcondition, compensation có điều kiện, idempotency, outbox/inbox và reconciliation**. Với kết quả chưa rõ, **kiểm chứng trước khi tiến hoặc bù**; với tác động không thể đảo ngược, thiết kế **refund/return/correction** thay vì giả vờ hoàn tác. Một workflow đáng tin không phải workflow không bao giờ lỗi, mà là workflow **biết mình đã làm gì, có bằng chứng cho trạng thái hiện tại, không nhân đôi hiệu ứng khi retry và có đường phục hồi về một trạng thái nghiệp vụ hợp lệ**.
