# Luồng minh họa đặt hàng, thanh toán và giao hàng trong kiến trúc Microservices

## 1. Bài toán và mục tiêu

Hãy hình dung một hệ thống thương mại điện tử: khách chọn sản phẩm, đặt hàng, thanh toán và chờ đơn vị vận chuyển giao hàng. Trên giao diện, người dùng thấy một hành trình liên tục; ở phía sau, nhiều dịch vụ có thể xử lý những phần việc độc lập.

Bài học này dùng **một đơn hàng mẫu** để giải thích cách các Microservices phối hợp, trạng thái được cập nhật và hệ thống xử lý lỗi khi các thao tác không thể nằm trong cùng một giao dịch cơ sở dữ liệu. Đây là luồng minh họa để học kiến trúc, không phải quy định cứng rằng mọi hệ thống thương mại điện tử phải có cùng thứ tự hoặc cùng số lượng dịch vụ.

Sau bài học, bạn có thể:

- Chỉ ra trách nhiệm của các dịch vụ Đơn hàng, Tồn kho, Thanh toán và Giao hàng.
- Theo dõi một đơn từ lúc khách bấm “Đặt hàng” đến lúc được giao.
- Phân biệt lệnh yêu cầu thực hiện công việc với sự kiện thông báo việc đã xảy ra.
- Giải thích vì sao cần xử lý nhất quán cuối cùng, giao dịch bù, xử lý trùng lặp và khả năng quan sát.
- Tự vẽ lại luồng thành công cũng như một số luồng thất bại thường gặp.

## 2. Bối cảnh: một đơn hàng cụ thể

Giả sử khách đặt **2 sản phẩm** từ một cửa hàng. Hệ thống tạo mã đơn **ORD-1001**, tổng tiền phải thanh toán là **500.000 VND**. Tồn kho có hàng, cổng thanh toán xác nhận giao dịch và đối tác vận chuyển chấp nhận tạo vận đơn.

Các khái niệm cốt lõi:

| Thành phần | Trách nhiệm chính | Dữ liệu do thành phần sở hữu |
| --- | --- | --- |
| API Gateway/BFF | Tiếp nhận yêu cầu từ web/mobile, xác thực và định tuyến | Không sở hữu trạng thái nghiệp vụ của đơn hàng |
| Order Service | Tạo đơn, lưu dòng hàng, tổng tiền, điều phối hoặc theo dõi tiến trình | Đơn hàng, trạng thái đơn, lịch sử chuyển trạng thái |
| Inventory Service | Kiểm tra và giữ trước số lượng hàng có thể bán | Số lượng khả dụng, lượng đã giữ, mã đặt giữ |
| Payment Service | Làm việc với nhà cung cấp thanh toán, ghi nhận thu tiền/hoàn tiền | Giao dịch thanh toán, trạng thái, tham chiếu cổng thanh toán |
| Shipping Service | Đặt vận chuyển, tạo mã vận đơn, theo dõi giao nhận | Shipment, mã vận đơn, trạng thái vận chuyển |
| Notification Service | Gửi email, SMS hoặc thông báo ứng dụng | Tác vụ và kết quả gửi thông báo |
| Message broker | Truyền sự kiện/lệnh bất đồng bộ giữa các dịch vụ | Message và metadata truyền tải; không thay thế cơ sở dữ liệu nghiệp vụ |

Trong ví dụ này, **Order Service hoặc một thành phần Saga Orchestrator** dẫn dắt quy trình. Mỗi dịch vụ có cơ sở dữ liệu thuộc quyền quản lý của mình. Order Service không tự cập nhật bảng tồn kho hoặc giao dịch thanh toán trong cơ sở dữ liệu của dịch vụ khác.

**Điểm phân biệt:** “Đã đặt hàng” nghĩa là yêu cầu đã được tiếp nhận và lưu thành đơn; “Đã thanh toán” nghĩa là có kết quả tài chính hợp lệ; “Đã tạo vận đơn” chỉ nghĩa là đơn đã được đối tác nhận xử lý; “Đã giao” cần tín hiệu giao hàng thành công. Không đồng nhất các mốc này.

## 3. Toàn cảnh luồng thành công

~~~mermaid
sequenceDiagram
    autonumber
    actor C as Khách hàng
    participant A as API Gateway
    participant O as Order Service / Saga
    participant I as Inventory Service
    participant P as Payment Service
    participant G as Cổng thanh toán
    participant S as Shipping Service
    participant N as Notification Service

    C->>A: POST /orders (giỏ hàng, địa chỉ, idempotencyKey)
    A->>O: Yêu cầu tạo đơn
    O->>O: Lưu ORD-1001, trạng thái PENDING
    O-->>C: 202 Accepted + orderId
    O->>I: ReserveStock(ORD-1001, 2 sản phẩm)
    I-->>O: StockReserved(reservationId)
    O->>P: ChargePayment(ORD-1001, 500000 VND)
    P->>G: Tạo/xác nhận giao dịch
    G-->>P: Thanh toán thành công
    P-->>O: PaymentSucceeded(paymentId)
    O->>S: CreateShipment(ORD-1001, địa chỉ)
    S-->>O: ShipmentCreated(trackingCode)
    O->>O: Trạng thái FULFILLING
    O->>N: Thông báo xác nhận đơn
    N-->>C: Email / thông báo
    S-->>O: ShipmentDelivered(trackingCode)
    O->>O: Trạng thái DELIVERED
    O->>N: Thông báo đã giao
~~~

Sơ đồ nhấn mạnh **quan hệ nhân quả**; các mũi tên không có nghĩa mọi lời gọi đều là HTTP đồng bộ. Trong triển khai bất đồng bộ, ReserveStock, StockReserved, PaymentSucceeded và ShipmentCreated có thể đi qua broker. Một số tích hợp với đối tác bên ngoài vẫn cần HTTP hoặc webhook.

Ở ví dụ này, hệ thống **giữ hàng trước, thu tiền sau, tạo vận đơn sau khi thanh toán**. Một doanh nghiệp khác có thể chỉ ủy quyền thanh toán (authorize) lúc đặt hàng và thu tiền (capture) khi xuất kho. Phải chọn thứ tự theo quy tắc bán hàng, tồn kho và hoàn tiền của hệ thống thực tế.

## 4. Đi từng bước qua hành trình của ORD-1001

### Bước 1 — Tiếp nhận yêu cầu và tạo đơn

Khách gửi giỏ hàng, địa chỉ và một khóa chống gửi trùng. Gateway xác thực, chuyển yêu cầu về Order Service. Order Service kiểm tra dữ liệu cơ bản, lấy giá và ưu đãi từ nguồn có thẩm quyền, tính tổng, rồi tạo đơn ở trạng thái **PENDING**.

Ví dụ yêu cầu rút gọn:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: checkout-7f21

{
  "items": [
    { "sku": "BOOK-01", "quantity": 2 }
  ],
  "shippingAddressId": "ADDR-08",
  "paymentMethodToken": "pm_token_demo"
}
~~~

Một phản hồi hợp lý khi xử lý nền:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "orderId": "ORD-1001",
  "status": "PENDING",
  "statusUrl": "/orders/ORD-1001"
}
~~~

**202 Accepted** nghĩa là tiến trình đã được chấp nhận để xử lý, chưa xác nhận đã thanh toán hay giao hàng. Một thiết kế khác có thể dùng **201 Created** khi tài nguyên đơn hàng được tạo ngay; điều quan trọng là tài liệu API mô tả rõ trạng thái thực tế.

Giá, khuyến mãi và phí vận chuyển phải được tính hoặc xác minh tại phía máy chủ. Không tin tổng tiền do trình duyệt tự gửi; payment token không phải số thẻ thô.

### Bước 2 — Giữ tồn kho, không chỉ “kiểm tra còn hàng”

Order phát lệnh **ReserveStock** với mã đơn, dòng hàng và mã yêu cầu duy nhất. Inventory Service thực hiện một giao dịch cục bộ: kiểm tra lượng có thể bán, trừ lượng khả dụng hoặc tăng lượng đang giữ, rồi ghi lại **reservationId**.

Kết quả thành công: **StockReserved**. Nếu không đủ hàng: **StockReservationRejected**, Saga kết thúc theo nhánh lỗi mà không thu tiền.

Tại sao cần “giữ” hàng? Hai khách có thể nhìn thấy cùng một sản phẩm còn 1 chiếc. Nếu cả hai chỉ gọi API kiểm tra rồi mới đặt, cả hai đều có thể tin rằng mình mua thành công. Quyết định giữ hàng cần được thực hiện **nguyên tử trong Inventory Service** bằng cơ chế phù hợp với kho dữ liệu (ví dụ update có điều kiện, khóa giao dịch hoặc kiểm soát phiên bản).

Reservation nên có thời hạn và quy tắc hết hạn. Nếu thanh toán quá lâu, lượng giữ có thể được giải phóng theo một tác vụ có kiểm soát. Không được tự ý hết hạn một reservation đang được chuyển sang bước hoàn tất mà không xét trạng thái hiện hành.

### Bước 3 — Thanh toán

Khi có **StockReserved**, Saga phát **ChargePayment**. Payment Service ghi nhận một payment attempt, sử dụng khóa idempotency khi gọi nhà cung cấp thanh toán, và lưu mối liên hệ giữa **orderId**, **paymentId** cùng tham chiếu giao dịch bên ngoài.

Nếu cổng thanh toán trả kết quả thành công, Payment Service công bố **PaymentSucceeded**. Nếu từ chối, công bố **PaymentFailed** với mã lỗi nghiệp vụ thích hợp; Order yêu cầu giải phóng phần tồn kho đã giữ.

Có tình huống cổng thanh toán phản hồi chậm hoặc mất kết nối. **Timeout không đồng nghĩa thanh toán thất bại**: giao dịch có thể đã thành công tại nhà cung cấp nhưng phản hồi bị mất. Payment Service cần tra cứu hoặc đối soát trạng thái giao dịch trước khi tạo khoản thu mới hay quyết định hoàn tiền.

Không ghi trực tiếp thông tin thẻ nhạy cảm vào log, sự kiện hoặc cơ sở dữ liệu của Order Service. Chỉ truyền token/tham chiếu cần thiết theo phạm vi trách nhiệm.

### Bước 4 — Tạo vận đơn và tiến hành giao

Sau **PaymentSucceeded**, Saga yêu cầu **CreateShipment**. Shipping Service xác thực thông tin giao hàng, gọi hệ thống giao vận (nếu có), lưu bản ghi shipment và phát **ShipmentCreated** cùng **trackingCode**.

Lúc này, đơn có thể chuyển sang **FULFILLING** hoặc **READY_TO_SHIP**, tùy ngôn ngữ trạng thái của hệ thống. Nó **chưa phải DELIVERED**. Những sự kiện tiếp theo như ShipmentPickedUp, ShipmentInTransit và ShipmentDelivered đến từ hệ thống quản lý vận chuyển hoặc webhook đã được xác minh.

Khi Shipping Service nhận **ShipmentDelivered**, Order Service cập nhật trạng thái **DELIVERED** nếu chuyển trạng thái đó hợp lệ. Notification Service có thể gửi thông báo; gửi thông báo lỗi không được tự động khiến đơn đã giao bị hoàn tác.

### Bước 5 — Khách xem tiến độ

Frontend gọi **GET /orders/ORD-1001** hoặc nhận cập nhật qua WebSocket/SSE/polling. API trả trạng thái mà hệ thống **đã xác nhận**, chẳng hạn:

~~~json
{
  "orderId": "ORD-1001",
  "paymentStatus": "SUCCEEDED",
  "inventoryStatus": "RESERVED",
  "fulfillmentStatus": "IN_TRANSIT",
  "trackingCode": "TRK-12345",
  "orderStatus": "FULFILLING"
}
~~~

Không trả trạng thái DELIVERED chỉ vì đã có trackingCode. Giao diện nên diễn đạt rõ “Đang xử lý thanh toán”, “Đang chuẩn bị hàng”, “Đang vận chuyển” hoặc “Đã giao”, tránh một nhãn “Thành công” duy nhất cho nhiều mốc khác nhau.

## 5. Lệnh, sự kiện và quyền sở hữu dữ liệu

**Command** thể hiện ý định cần một thành phần thực hiện, thường ở thì mệnh lệnh: **ReserveStock**, **ChargePayment**, **CreateShipment**, **ReleaseStock**, **RefundPayment**. Command có thể bị từ chối hoặc thất bại.

**Event** thông báo một sự thật đã xảy ra trong một bounded context, thường ở thì quá khứ: **OrderPlaced**, **StockReserved**, **PaymentSucceeded**, **ShipmentCreated**, **ShipmentDelivered**. Dịch vụ phát event chịu trách nhiệm bảo đảm dữ kiện đó là đúng theo dữ liệu mình sở hữu.

Bảng ví dụ:

| Tín hiệu | Nơi phát | Nơi tiếp nhận | Ý nghĩa |
| --- | --- | --- | --- |
| OrderPlaced | Order | Saga, Analytics | Đơn ORD-1001 đã được lưu |
| ReserveStock | Saga | Inventory | Hãy thử giữ 2 sản phẩm |
| StockReserved | Inventory | Saga | Đã giữ hàng thành công |
| ChargePayment | Saga | Payment | Hãy thực hiện/kiểm tra khoản thanh toán |
| PaymentSucceeded | Payment | Saga, Order | Khoản thanh toán đã được xác nhận |
| CreateShipment | Saga | Shipping | Hãy tạo vận đơn cho đơn |
| ShipmentCreated | Shipping | Saga, Order | Đã có bản ghi vận chuyển và mã theo dõi |
| ShipmentDelivered | Shipping | Order, Notification | Đơn vận chuyển đã được xác nhận giao |

Trong kiến trúc orchestration, Saga biết bước nào tiếp theo; các dịch vụ nghiệp vụ không cần biết toàn bộ quy trình. Trong kiến trúc choreography, mỗi dịch vụ có thể tự phản ứng với event của dịch vụ trước. Cả hai đều có thể phù hợp, nhưng **một quy trình có nhiều bước bù phức tạp thường dễ quan sát hơn khi có một nơi lưu tiến độ Saga rõ ràng**.

Sự kiện nên có metadata đủ để định tuyến và truy vết:

~~~json
{
  "eventId": "evt-87aa",
  "eventType": "PaymentSucceeded",
  "eventVersion": 1,
  "occurredAt": "2026-11-11T10:00:00Z",
  "correlationId": "checkout-7f21",
  "causationId": "cmd-charge-09",
  "orderId": "ORD-1001",
  "paymentId": "PAY-9001",
  "amountMinor": 500000,
  "currency": "VND"
}
~~~

Dữ liệu ví dụ không đại diện cho một schema chuẩn bắt buộc. **eventId** nhận diện sự kiện để xử lý trùng; **correlationId** kết nối các thao tác của một lần checkout; **causationId** chỉ ra tác nhân trực tiếp sinh ra event. Đối với VND, amountMinor ở đây là đơn vị số nguyên theo quy ước của hệ thống ví dụ; trong hệ thống thật, chuẩn hóa đơn vị tiền và quy tắc làm tròn phải nhất quán giữa các bên.

Không đưa toàn bộ hồ sơ khách hàng hoặc bí mật thanh toán vào event vì nhiều consumer có thể đọc được event đó.

## 6. Trạng thái của đơn hàng khác trạng thái của từng dịch vụ

Một mô hình trạng thái minh họa:

| Trạng thái đơn | Ý nghĩa | Thao tác tiếp theo |
| --- | --- | --- |
| PENDING | Đã nhận đơn, chờ giữ hàng | ReserveStock |
| STOCK_RESERVED | Đã giữ hàng, chờ thanh toán | ChargePayment |
| PAID | Thanh toán thành công, chưa tạo vận đơn | CreateShipment |
| FULFILLING | Vận đơn đã được tạo, đang chuẩn bị/giao | Theo dõi Shipping |
| DELIVERED | Vận chuyển xác nhận đã giao | Hoàn tất phần giao nhận |
| REJECTED | Không thể tạo đơn hợp lệ hoặc không đủ hàng trước thu tiền | Thông báo kết quả |
| COMPENSATING | Một bước đã thành công nhưng bước sau thất bại; đang xử lý bù | RefundPayment/ReleaseStock |
| CANCELLED | Hủy đã được xác nhận theo quy tắc nghiệp vụ | Kết thúc quy trình hủy |
| MANUAL_REVIEW | Cần xử lý ngoại lệ/đối soát | Nhân sự hoặc tiến trình reconciliation |

Đây là **trạng thái tổng hợp của Order**. Payment có trạng thái riêng như INITIATED, SUCCEEDED, FAILED, REFUND_PENDING, REFUNDED. Shipping có CREATED, PICKED_UP, IN_TRANSIT, DELIVERED, DELIVERY_FAILED. Không ép các trạng thái này thành một enum giống hệt nhau.

Mỗi lệnh cập nhật trạng thái cần kiểm tra **chuyển trạng thái hợp lệ**. Ví dụ, sự kiện ShipmentCreated bị gửi trùng sau ShipmentDelivered không được khiến Order lùi từ DELIVERED về FULFILLING. Với nhiều event đến không đúng thứ tự, dùng version/sequence hoặc quy tắc so sánh dựa trên trạng thái nguồn.

## 7. Các nhánh lỗi và giao dịch bù (Saga)

Trong một monolith có một database, một số thao tác có thể cùng nằm trong giao dịch ACID. Với Order, Inventory, Payment, Shipping sở hữu các database riêng, hệ thống **không nên giả định** có thể rollback mọi bước chỉ bằng một lệnh SQL.

Saga chia quy trình thành **các giao dịch cục bộ**, và khi một bước sau thất bại, phát **compensating actions** để xử lý tác động của các bước đã hoàn thành. Hành động bù là nghiệp vụ mới, không phải tua ngược thời gian: hoàn tiền có thể mất thời gian và có thể cần đối soát.

### Tình huống A — Hết hàng trước khi thanh toán

1. Order tạo đơn PENDING, gửi ReserveStock.
2. Inventory phát StockReservationRejected vì không đủ số lượng.
3. Saga chuyển Order sang REJECTED và thông báo hết hàng.
4. Không phát ChargePayment nên không có khoản thu cần hoàn.

### Tình huống B — Giữ hàng thành công nhưng thanh toán bị từ chối

1. Inventory đã phát StockReserved.
2. Payment xác nhận PaymentFailed (ví dụ nhà cung cấp từ chối).
3. Saga phát **ReleaseStock** với reservationId đã giữ.
4. Inventory xác nhận StockReleased.
5. Order chuyển sang CANCELLED/REJECTED theo chính sách; thông báo cho khách.

Nếu ReleaseStock bị timeout, Saga giữ trạng thái COMPENSATING và thử lại theo chính sách; không khẳng định đã trả hàng về kho khi chưa có bằng chứng.

### Tình huống C — Đã thu tiền nhưng không thể tạo vận đơn

1. PaymentSucceeded được xác nhận; Order ở PAID.
2. Shipping trả ShipmentCreationFailed vì địa chỉ/đối tác không khả dụng.
3. Chính sách có thể cho phép **đổi hãng vận chuyển** hoặc giữ đơn để con người xử lý. Nếu buộc phải hủy, Saga yêu cầu **RefundPayment** rồi **ReleaseStock**.
4. Payment xác nhận RefundSucceeded; Inventory xác nhận StockReleased.
5. Order chỉ chuyển sang trạng thái kết thúc phù hợp khi các bước bù bắt buộc đã hoàn thành. Nếu hoàn tiền đang chờ, giữ COMPENSATING/REFUND_PENDING thay vì hiển thị “đã hoàn tiền”.

Luồng bù của trường hợp phải hủy có thể biểu diễn:

~~~mermaid
flowchart TD
    A[PaymentSucceeded] --> B[CreateShipment]
    B --> C{Tạo vận đơn thành công?}
    C -->|Có| D[FULFILLING]
    C -->|Không| E{Có thể đổi phương án giao?}
    E -->|Có| F[Thử phương án giao khác có giới hạn]
    F --> C
    E -->|Không| G[COMPENSATING]
    G --> H[RefundPayment]
    H --> I{RefundSucceeded?}
    I -->|Không hoặc chưa rõ| J[Retry an toàn / đối soát / xử lý thủ công]
    J --> H
    I -->|Có| K[ReleaseStock]
    K --> L{StockReleased?}
    L -->|Chưa| M[Retry / xử lý thủ công]
    M --> K
    L -->|Có| N[CANCELLED]
~~~

Thứ tự hoàn tiền và giải phóng kho trong sơ đồ chỉ là một chính sách ví dụ. Thực tế có thể cho chạy các bước độc lập, nhưng phải theo dõi riêng kết quả từng bước để không thất lạc nghĩa vụ hoàn tiền hoặc không giữ hàng vô thời hạn.

### Tình huống D — Khách bấm “Đặt hàng” hai lần

Hai request có cùng **Idempotency-Key** và cùng nội dung nghiệp vụ nên trả về **cùng một orderId/kết quả**, thay vì tạo hai đơn và thu tiền hai lần. Nếu cùng khóa nhưng payload khác, API cần phản hồi xung đột hoặc yêu cầu khóa mới. Key có phạm vi theo người dùng/nghiệp vụ và thời gian lưu hợp lý.

### Tình huống E — Consumer xử lý event hai lần

Broker thường hướng đến giao nhận **at-least-once**; event có thể đến lặp lại. Consumer lưu **eventId** hoặc định danh thao tác đã xử lý trong cùng giao dịch cục bộ với thay đổi nghiệp vụ. Nhận lại PaymentSucceeded không được tạo thêm shipment hoặc tăng tổng đã trả tiền.

## 8. Nhất quán cuối cùng, Outbox và xử lý lại

Có một “khoảng trống nguy hiểm” khi service làm hai việc: (1) ghi database, (2) gửi event. Ví dụ Payment ghi SUCCEEDED rồi ứng dụng chết trước khi gửi PaymentSucceeded. Hệ thống bên ngoài có thể tưởng đơn chưa thanh toán.

**Transactional Outbox** giải quyết khoảng trống này theo mô hình:

1. Trong **một transaction cục bộ**, Payment ghi trạng thái giao dịch và một bản ghi outbox mô tả PaymentSucceeded.
2. Một publisher đọc outbox và chuyển event lên broker.
3. Publisher đánh dấu đã phát hoặc theo dõi checkpoint; nếu lỗi, gửi lại.
4. Consumer chấp nhận có event trùng và áp dụng idempotency.

Outbox tạo khả năng **ít nhất một lần** đến broker, không tự bảo đảm xử lý đúng một lần ở mọi hệ thống. Vì vậy **Outbox + consumer idempotent** là cặp giải pháp thường đi cùng nhau. Tương tự, Inventory/Shipping/Order cũng cần cơ chế không làm mất sự kiện của mình.

**Eventual consistency** nghĩa là Order có thể còn hiển thị PENDING trong thời gian ngắn sau khi Inventory đã giữ hàng. Đây là độ trễ đồng bộ trạng thái giữa nhiều nguồn, không phải lỗi mặc định. Hệ thống cần đặt giới hạn chờ, thông tin UX và cách phát hiện đơn kẹt. Không dùng việc “không thấy event trong vài giây” làm chứng cứ chắc chắn để thu tiền hoặc hoàn tiền lần nữa.

### Các nguyên tắc khi retry

- Retry với **exponential backoff + jitter** và số lần/hạn chờ rõ ràng; tránh retry vô hạn nóng.
- Phân biệt lỗi tạm thời (timeout, 503, hạn mức) và lỗi nghiệp vụ cuối cùng (hết hàng, yêu cầu không hợp lệ).
- Gọi API có tác động tài chính bằng **idempotency key ổn định cho cùng payment operation**.
- Sau khi retry cạn, chuyển message sang luồng xử lý lỗi/dead-letter queue có cảnh báo và khả năng replay có kiểm soát.
- Với tác vụ quá thời hạn, có **reconciliation job** đối soát trạng thái Order–Payment–Inventory–Shipping để sửa chênh lệch dựa trên nguồn có thẩm quyền.

### Webhook đến muộn hoặc không đúng thứ tự

Một cổng thanh toán có thể gửi webhook thành công trước phản hồi HTTP, gửi lặp nhiều lần hoặc đến sau khi UI đã hết thời gian chờ. Payment Service phải xác minh chữ ký webhook, tìm giao dịch bằng external reference và đối chiếu trạng thái. Không suy luận dựa trên thứ tự nhận callback; không nhận event chưa xác thực như bằng chứng tiền đã vào.

## 9. Ranh giới giao dịch, dữ liệu và API

Mỗi service nên thực hiện thay đổi thuộc quyền mình trong một transaction cục bộ:

- Order lưu đơn, dòng hàng, snapshot thông tin giá lúc đặt và tiến trình Saga.
- Inventory lưu reservation gắn với mã đơn và dòng SKU; có thao tác giữ, xác nhận/tiêu thụ và giải phóng.
- Payment lưu payment attempt, refund và đối soát với nhà cung cấp.
- Shipping lưu shipment, tracking và lịch sử trạng thái giao nhận.

Không dùng một database chung rồi để Order trực tiếp update bảng Payment để “tiện”. Điều đó làm mất tính độc lập của bounded context và khiến quy tắc nghiệp vụ khó kiểm soát.

Một API tối giản cho minh họa:

~~~text
POST   /orders                 Tạo đơn và nhận orderId
GET    /orders/{orderId}       Xem trạng thái tổng hợp
POST   /orders/{orderId}/cancel Yêu cầu hủy (có kiểm tra điều kiện)
GET    /orders/{orderId}/events Xem lịch sử sự kiện hiển thị cho người dùng
~~~

Đây là **API hướng khách hàng**. Các dịch vụ nội bộ có thể sử dụng command/event qua broker, gRPC hoặc HTTP. Không buộc frontend gọi trực tiếp Inventory, Payment và Shipping rồi tự ráp một giao dịch xuyên dịch vụ.

**Lưu ý bảo mật:** authorization phải bảo đảm người dùng chỉ xem/hủy đơn của mình; dữ liệu sự kiện trả về cho khách cần loại bỏ internal IDs, token, thông tin nhạy cảm và lý do lỗi nội bộ không cần thiết.

## 10. Khả năng quan sát: biết đơn đang ở bước nào

Với một đơn hàng chạy qua nhiều service, chỉ nhìn log của Order là chưa đủ. Thiết kế tối thiểu nên có:

| Tín hiệu | Ví dụ cần ghi nhận | Câu hỏi trả lời |
| --- | --- | --- |
| Structured logs | orderId, sagaId, correlationId, eventId, service, outcome | Bước nào thất bại? |
| Distributed tracing | Trace từ POST /orders qua Order, Inventory, Payment, Shipping | Chậm ở đâu, call nào gây timeout? |
| Metrics | số đơn PENDING quá hạn, tỷ lệ PaymentFailed, thời gian tạo vận đơn | Có sự cố trên diện rộng không? |
| Audit trail nghiệp vụ | thời điểm giữ hàng, thanh toán, hoàn tiền, giao hàng | Có bằng chứng nào cho trạng thái cuối? |
| Alert/reconciliation | COMPENSATING quá hạn, payment SUCCEEDED nhưng Order chưa cập nhật | Đơn nào cần can thiệp? |

Ví dụ chuỗi log đã lược bỏ thông tin nhạy cảm:

~~~text
2026-11-11T10:00:01Z order  orderId=ORD-1001 sagaId=SG-1 event=OrderPlaced
2026-11-11T10:00:02Z stock  orderId=ORD-1001 sagaId=SG-1 event=StockReserved reservationId=RES-1
2026-11-11T10:00:04Z payment orderId=ORD-1001 sagaId=SG-1 event=PaymentSucceeded paymentId=PAY-9001
2026-11-11T10:00:06Z shipping orderId=ORD-1001 sagaId=SG-1 event=ShipmentCreated trackingCode=TRK-12345
~~~

Các dòng minh họa chứng minh tiến trình đã đi tới **tạo vận đơn**, chưa chứng minh hàng đã giao. Để khẳng định đã giao, cần thêm bằng chứng ShipmentDelivered từ nguồn thích hợp.

Một bảng theo dõi Saga giúp đội vận hành thấy **bước hiện tại, bước trước đó, số lần retry, hành động bù còn chờ và thời hạn xử lý**. Đó là điều thiết yếu khi một bước bất đồng bộ kéo dài nhiều phút hoặc nhiều ngày.

## 11. Cách thử nghiệm luồng này

Khi dựng mô hình học tập, có thể dùng các service giả lập và message broker để kiểm tra các tình huống có ý nghĩa:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Có hàng, payment thành công, shipping tạo được vận đơn | PENDING → STOCK_RESERVED → PAID → FULFILLING; sau ShipmentDelivered mới DELIVERED |
| Không đủ hàng | REJECTED; không thu tiền |
| Payment bị từ chối | Giải phóng reservation; đơn không ở PAID |
| Payment thành công nhưng shipping lỗi bắt buộc hủy | Hoàn tiền + giải phóng kho; trạng thái bù được theo dõi tới khi có xác nhận |
| Gửi lại POST /orders cùng idempotency key | Không tạo đơn hoặc khoản thu thứ hai |
| Phát lại PaymentSucceeded hai lần | Chỉ áp dụng một lần tác động nghiệp vụ |
| Publisher chết sau commit nhưng trước publish | Outbox phát lại được event, Saga tiến tiếp |
| Mất phản hồi cổng thanh toán | Đối soát trạng thái thay vì mặc định thu lại |
| Webhook/ShipmentDelivered đến trễ hoặc đảo thứ tự | Không làm trạng thái đơn lùi sai |
| Notification lỗi | Ghi retry thông báo; không hoàn tác thanh toán/giao hàng |

Đối với một demo, có thể bắt đầu bằng một cơ sở dữ liệu riêng cho mỗi bounded context (hoặc mô phỏng ranh giới độc lập), một nơi lưu tiến trình Saga và một publisher/consumer sự kiện. Chọn **một luồng thành công và hai luồng lỗi** trước khi mở rộng; giá trị nằm ở việc thấy rõ chuyển trạng thái và hành động bù.

## 12. Những nhầm lẫn thường gặp

**“Microservices là gọi HTTP tuần tự từ Service A đến B đến C.”** HTTP chỉ là một cách giao tiếp. Với quy trình dài, các sự kiện bất đồng bộ và Saga giúp giảm thời gian giữ kết nối, nhưng mang thêm trách nhiệm retry, idempotency và giám sát.

**“Order đã được tạo nghĩa là mua hàng thành công.”** Đơn có thể mới PENDING. Hợp đồng API phải phân biệt “nhận yêu cầu” với “đã thu tiền” và “đã giao”.

**“Rollback sẽ tự trả tiền và trả hàng.”** Không có rollback chung giữa nhiều database và cổng thanh toán bên ngoài. Phải thiết kế nghiệp vụ bù, xác nhận kết quả và có phương án xử lý ngoại lệ.

**“Broker bảo đảm mỗi event chỉ xuất hiện đúng một lần.”** Không nên dựa vào giả định đó ở toàn bộ hệ thống. Hệ thống cần chống lặp ở mức nghiệp vụ.

**“Timeout nghĩa là bước đó thất bại.”** Timeout chỉ chứng minh không nhận được kết quả đúng hạn. Cần query trạng thái/đối soát trước khi hành động mang tính tài chính.

**“ShipmentCreated nghĩa là Delivered.”** Tạo vận đơn là bắt đầu quá trình giao nhận; chỉ xác nhận thực tế từ Shipping mới cho phép kết luận đã giao.

## 13. Tự kiểm tra hiểu bài

1. Nếu đã tạo Order nhưng Inventory báo hết hàng, bước nào chắc chắn không nên xảy ra tiếp theo trong luồng minh họa?
2. Tại sao Inventory phải *reserve* thay vì chỉ *check availability* trước khi thanh toán?
3. PaymentSucceeded đã ghi vào database nhưng event chưa tới Order. Cơ chế nào giúp sự kiện được phát lại an toàn?
4. Nếu Shipping không thể tạo vận đơn sau khi PaymentSucceeded, những hành động nghiệp vụ nào phải được theo dõi?
5. Điều gì xảy ra nếu PaymentSucceeded bị nhận hai lần? Bạn dùng định danh nào để chống xử lý trùng?
6. Khách thấy trạng thái PENDING trong khi Payment Service đã thu tiền. Bạn cần phân biệt độ trễ nhất quán với lỗi thật như thế nào?
7. Vì sao thông báo email lỗi không nên làm đơn ở trạng thái DELIVERED quay về trạng thái trước đó?

Gợi ý tự diễn đạt lại luồng bằng một câu: **Nhận đơn → giữ hàng → xác nhận thanh toán → tạo vận đơn → giao hàng; khi bước sau thất bại, xử lý bù các bước trước và đối soát đến khi trạng thái nhất quán.**

## 14. Ghi nhớ

Một checkout trong kiến trúc Microservices là **một tiến trình nghiệp vụ có nhiều trạng thái**, trải qua các dịch vụ sở hữu dữ liệu riêng. Mỗi thành phần phải công bố sự thật về công việc của chính mình; nơi điều phối ghép các sự thật đó thành hành trình đơn hàng. Để luồng này đáng tin cậy, hãy thiết kế từ đầu **idempotency, Saga/compensation, Outbox, retry có kiểm soát, xác minh callback, reconciliation và observability**. Mục tiêu không chỉ là minh họa các mũi tên giữa service, mà còn hiểu hệ thống sẽ giữ đúng dữ liệu và quyền lợi khách hàng khi một mũi tên thất bại.
