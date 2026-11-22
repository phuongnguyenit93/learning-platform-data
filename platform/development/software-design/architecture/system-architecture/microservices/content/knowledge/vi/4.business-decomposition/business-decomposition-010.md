# Thiết kế ranh giới ban đầu và kế hoạch kiểm chứng bằng thực tế

> **Chủ đề:** Software Architecture → System Architecture → Microservices  
> **Nhóm:** Phân rã nghiệp vụ

## Mục tiêu học tập

Sau bài học, người học có thể:

- Đề xuất **ranh giới dịch vụ ban đầu** dựa trên năng lực nghiệp vụ, quy tắc, dữ liệu, luồng thay đổi và nhu cầu vận hành, thay vì chia service theo bảng dữ liệu hoặc tầng kỹ thuật.
- Phân biệt **bounded context**, **aggregate**, **module** và **microservice triển khai độc lập**; hiểu khi nào nên giữ cùng một đơn vị và khi nào có cơ sở tách.
- Xây dựng bản phác thảo gồm **quyền sở hữu dữ liệu**, **contract**, **luồng liên dịch vụ**, **bất biến nghiệp vụ** và các phụ thuộc phải chấp nhận.
- Ghi rõ các **giả thuyết kiến trúc**, rủi ro, điều kiện bác bỏ và kế hoạch thu thập chứng cứ thay vì coi sơ đồ ban đầu là đáp án bất biến.
- Thiết kế một vòng kiểm chứng có thể thực hiện: baseline, quan sát, thử nghiệm nhỏ, đo lường, quyết định giữ/tách/gộp hoặc sửa boundary.
- Nhận diện tín hiệu phân rã quá nhỏ, phụ thuộc chặt và dữ liệu bị sở hữu chồng chéo; xây dựng lộ trình tiến hóa có thể rollback.

## 1. Bài toán: bắt đầu từ nghiệp vụ, chưa bắt đầu từ tên service

Giả sử một nền tảng thương mại điện tử cần:

1. Người dùng xem sản phẩm, giá đang áp dụng và số lượng có thể mua.
2. Người dùng đặt hàng gồm nhiều dòng hàng.
3. Hệ thống tính số tiền phải trả, xác định khuyến mãi và quy tắc vận chuyển.
4. Hệ thống giữ hàng để tránh bán vượt tồn.
5. Người dùng thanh toán qua một cổng thanh toán bên ngoài.
6. Hệ thống xác nhận đơn, chuẩn bị giao hàng, thông báo trạng thái.
7. Nhân viên xử lý hủy, hoàn tiền, đổi trả và đối soát.

Một cách tách vội là tạo ProductService, PriceService, DiscountService, CartService, OrderService, OrderItemService, PaymentService, PaymentStatusService, EmailService… chỉ vì có nhiều danh từ trong yêu cầu. Cách khác là lấy mỗi bảng database làm một service. Cả hai đều bỏ qua điều quan trọng: **quy tắc nào phải nhất quán với nhau, ai có quyền quyết định, những phần nào thật sự cần phát triển độc lập**.

Thiết kế ranh giới ban đầu là một **mô hình có căn cứ**, thường được xây từ kiến thức nghiệp vụ và giả thuyết kỹ thuật còn chưa kiểm chứng đầy đủ. Ta cần đủ rõ để triển khai hoặc làm thử nghiệm, đồng thời chấp nhận khả năng phải sửa khi có bằng chứng.

### 1.1. “Boundary” cụ thể là gì?

Một ranh giới tốt giúp trả lời các câu hỏi:

- **Trách nhiệm:** Năng lực nghiệp vụ nào nằm bên trong? Điều gì được coi là ngoài phạm vi?
- **Quy tắc:** Quy tắc, bất biến và quyết định cuối cùng thuộc thành phần nào?
- **Dữ liệu:** Ai là nguồn sự thật và chủ sở hữu thao tác ghi? Bên ngoài có thể đọc bằng cách nào?
- **Hợp đồng:** Những thao tác/sự kiện nào phải được công bố? Ý nghĩa nghiệp vụ của chúng là gì?
- **Triển khai:** Thành phần có thể build, deploy, scale, rollback và theo dõi ra sao?
- **Vận hành:** Đội nào nhận cảnh báo, xử lý sự cố và chịu trách nhiệm chất lượng dịch vụ?

Ví dụ: Inventory có trách nhiệm xác định **còn khả năng giữ hàng hay không**. Order có thể yêu cầu giữ hàng nhưng không được tự thay đổi cột available_quantity của Inventory để “tiết kiệm một lần gọi API”. Tách quyền quyết định như vậy giúp bảo vệ bất biến bán hàng.

### 1.2. Ranh giới logic không luôn đồng nghĩa một service vật lý

- **Business capability:** năng lực như quản lý đơn hàng hay quản lý tồn kho.
- **Bounded context (DDD):** phạm vi trong đó thuật ngữ và mô hình miền nghiệp vụ có ý nghĩa nhất quán. Cùng từ “Product” có thể mang thông tin khác nhau trong Catalog, Inventory và Pricing.
- **Aggregate (DDD):** cụm đối tượng có một ranh giới nhất quán giao dịch; ví dụ một Order cùng các OrderLine có thể nằm trong một aggregate, tùy quy tắc.
- **Module:** ranh giới trong mã nguồn, có thể được kiểm soát bằng package/API nội bộ, không đòi đường truyền mạng.
- **Microservice:** đơn vị cung cấp khả năng và có vòng đời triển khai tương đối độc lập, giao tiếp bằng contract.

Không có công thức cố định “mỗi aggregate là một microservice” hoặc “mỗi bounded context bằng một repository”. Một bounded context đôi khi được phục vụ bởi một service; đôi khi một service bao gồm nhiều module/context liên quan khi chi phí tách chưa đáng. Ngược lại một context lớn có thể được hiện thực bằng nhiều service nếu có lý do rõ ràng và ownership nhất quán.

## 2. Dữ liệu đầu vào cần thu thập trước khi vẽ ranh giới

Đừng chỉ lấy sơ đồ tổ chức hoặc bảng database hiện tại làm bằng chứng. Có thể bắt đầu với các loại thông tin sau:

| Nguồn hiểu biết | Câu hỏi | Kết quả mong muốn |
| --- | --- | --- |
| **Luồng nghiệp vụ** | Đặt hàng, hủy, thanh toán, hoàn tiền thực sự diễn ra thế nào? | Timeline và các quyết định nghiệp vụ. |
| **Ngôn ngữ nghiệp vụ** | Các nhóm dùng cùng từ “đơn”, “giá”, “đặt trước” với cùng nghĩa không? | Bảng thuật ngữ và điểm khác ngữ nghĩa. |
| **Bất biến** | Điều kiện nào không được vi phạm ngay cả khi hệ thống lỗi? | Danh sách invariant và chủ sở hữu. |
| **Dữ liệu** | Ai tạo, sửa, đọc từng nhóm dữ liệu? | Data ownership map. |
| **Thay đổi sản phẩm** | Các chức năng nào thường được sửa trong cùng ticket/release? | Change coupling map. |
| **Tải vận hành** | Chỗ nào có tải, SLO hoặc mô hình lưu trữ khác biệt? | Baseline về tải và độ trễ. |
| **Đội ngũ** | Ai sở hữu năng lực nghiệp vụ, ai trực vận hành, ai duyệt release? | Ownership và khả năng triển khai. |
| **Tích hợp ngoài** | Cổng thanh toán, vận chuyển, email có contract và giới hạn gì? | Danh sách dependency và rủi ro. |
| **Sự cố đã xảy ra** | Những thay đổi nào gây incident, deadlock hoặc deploy đồng thời? | Chứng cứ về coupling và failure mode. |

Ở giai đoạn đầu, nhiều hệ thống chưa có số liệu đầy đủ. Có thể ghi **chưa có dữ liệu** và bổ sung instrument hoặc phỏng vấn thay vì phát biểu chắc chắn rằng hai phần “cần scale độc lập” mà chưa từng đo.

### 2.1. Khai thác luồng bằng workshop

Có thể dùng **event storming** hoặc workshop khám phá miền nghiệp vụ:

1. Liệt kê sự kiện đã xảy ra trong quá khứ nghiệp vụ: OrderPlaced, StockReserved, PaymentSucceeded, OrderCancelled.
2. Sắp chúng theo dòng thời gian cho các tình huống chính và ngoại lệ.
3. Bổ sung command, tác nhân, chính sách, quy tắc, thời hạn và bước cần xác minh.
4. Tìm các chỗ nhiều thuật ngữ hoặc trách nhiệm cùng xuất hiện; đánh dấu điều kiện phải giao dịch nhất quán.
5. Phân nhóm các hành vi có tính kết dính cao thành **cụm ứng viên**, chưa vội đặt tên service.
6. Xác định chỗ các nhóm dùng khác nghĩa cho cùng một từ; đây là tín hiệu của bounded context.
7. Ghi những điều còn tranh luận thành giả thuyết hoặc câu hỏi cần đo đạc.

Một dòng nghiệp vụ đơn giản có thể là:

~~~text
Customer selects items
    |
    v
PlaceOrder command
    |
    v
OrderPlaced event
    |
    +--> ReserveStock command --> StockReserved | StockRejected
    |
    +--> RequestPayment -------> PaymentSucceeded | PaymentFailed
    |
    v
OrderConfirmed | OrderCancelled | OrderAwaitingReview
~~~

Sơ đồ trên mô tả **các hành động và sự kiện nghiệp vụ**, chưa khẳng định mỗi ô là một microservice và chưa đủ để xác định cách xử lý tiền hay thứ tự chính xác. Bản thiết kế phải tiếp tục làm rõ ai sở hữu từng quyết định.

### 2.2. Phân biệt sự kiện và ý định

- **Command:** yêu cầu một thành phần làm việc, ví dụ ReserveStock(orderId, items).
- **Domain event:** thông báo một sự kiện đã xảy ra theo nghĩa nghiệp vụ, ví dụ StockReserved.
- **Query:** hỏi dữ liệu, ví dụ GetAvailableStock(sku).

Tên event cần phản ánh điều gì đã được commit. Một event tên OrderConfirmed chỉ nên phát khi trạng thái “đã xác nhận” thực sự đạt theo contract; đừng dùng cùng tên để diễn tả “đã nhận yêu cầu xác nhận”.

## 3. Xác định những điểm phải nhất quán trong cùng ranh giới

Một tiêu chí mạnh để đặt boundary là **bất biến nghiệp vụ**. Bất biến là điều phải đúng khi giao dịch hoàn tất, kể cả khi nhiều request chạy đồng thời.

Ví dụ:

- Trong Inventory, tổng số lượng giữ hàng hợp lệ không vượt mức tồn có thể bán, trừ khi quy tắc nghiệp vụ cho phép backorder.
- Trong Order, trạng thái đơn và lịch sử transition không mâu thuẫn; đơn đã hủy không tiếp tục sang trạng thái giao hàng nếu không có quy trình phục hồi đã định nghĩa.
- Trong Payment, một logical payment attempt không tạo hai lần thu tiền cùng mục đích vì retry.
- Trong Pricing, quy tắc tính giá và snapshot số tiền được xác nhận theo thời điểm có hiệu lực nhất quán với hợp đồng bán hàng.

Nếu hai thao tác **phải giao dịch nguyên tử** để bảo vệ một invariant, chia chúng qua hai database/service sẽ phát sinh vấn đề về transaction phân tán. Khi có thể, giữ invariant trong một aggregate hoặc trong một service để kiểm soát bằng transaction cục bộ.

Không phải mọi dữ liệu trong cùng một workflow đều cần cùng transaction. Ví dụ gửi email thông báo sau khi đơn được xác nhận có thể bất đồng bộ, còn thay đổi số lượng giữ hàng phải được Inventory bảo vệ ngay ở nơi sở hữu dữ liệu.

### 3.1. Ba câu hỏi cho một invariant

1. **Ai là chủ sở hữu?** Ví dụ chỉ Inventory quyết định giữ hàng thành công.
2. **Tính nhất quán cần mạnh đến đâu?** Không bán vượt tồn có thể phải được kiểm soát đồng bộ trong Inventory; số đếm tồn hiển thị tại trang catalog có thể chậm ít giây nếu yêu cầu sản phẩm cho phép.
3. **Nếu hai bước không hoàn thành cùng lúc thì sao?** Order có thể ở PENDING_STOCK; cần deadline, retry hoặc compensation phù hợp.

Boundary nên được chọn theo ngữ nghĩa và mức nhất quán cần thiết, không chỉ theo nơi dữ liệu đang được lưu.

## 4. Thiết kế candidate boundaries cho ví dụ bán hàng

Sau khi khám phá nghiệp vụ, có thể phác thảo các ứng viên sau. Đây là **đề xuất giả định để kiểm chứng**, không phải một sơ đồ chuẩn áp dụng cho mọi hệ thống.

| Ứng viên | Trách nhiệm và quyền quyết định | Nguồn dữ liệu sở hữu | Contract tiêu biểu |
| --- | --- | --- | --- |
| **Catalog** | Mô tả sản phẩm, danh mục, hiển thị sản phẩm | Product metadata, category | GetProduct, ProductPublished |
| **Order** | Vòng đời đơn, snapshot dòng hàng, hủy/đổi trạng thái | Order, OrderLine, OrderHistory | PlaceOrder, GetOrder, OrderPlaced |
| **Inventory** | Tồn khả dụng, giữ/nhả hàng, quy tắc chống bán vượt | Stock, StockReservation | ReserveStock, ReleaseStock, StockReserved |
| **Payment** | Payment attempt, tích hợp cổng, xác minh kết quả, hoàn tiền | PaymentAttempt, Transaction | RequestPayment, GetPayment, PaymentSucceeded |
| **Fulfillment** | Chuẩn bị, đóng gói và giao hàng; đối tác logistics | FulfillmentJob, Shipment | RequestFulfillment, ShipmentDispatched |
| **Notification** | Kênh gửi email/SMS/push theo yêu cầu | DeliveryAttempt, template liên quan | SendNotification, NotificationDelivered |

Một số năng lực như **Pricing/Promotion**, **Cart** hoặc **Customer** có thể là module trong hệ thống hiện tại, bounded context riêng hoặc service độc lập sau này. Chưa cần tách riêng nếu không có đủ lý do về quyền quyết định, chu kỳ thay đổi, nhu cầu mở rộng hoặc vận hành.

### 4.1. Những ranh giới cần thảo luận trước

**Order ↔ Inventory:** Order biết khách muốn mua gì; Inventory biết có thể giữ số lượng nào. Nếu Order chỉ kiểm tra một giá trị tồn đọc từ Catalog rồi tự xác nhận, có nguy cơ bán vượt tồn trong thời gian nhiều khách cùng đặt. Inventory nên giữ quyền commit reservation.

**Order ↔ Payment:** Order quản lý trạng thái đơn; Payment quản lý nỗ lực thanh toán và giao tiếp cổng thanh toán. Một timeout từ Payment không tự động có nghĩa giao dịch chưa xảy ra. Contract cần operationId, idempotency và tra cứu kết quả.

**Catalog ↔ Pricing:** Mô tả sản phẩm và quy tắc định giá có thể do hai nhóm khác nhau sở hữu, nhưng nếu mọi thay đổi giá đều đồng thời thay đổi sản phẩm và đòi transaction chung, cần xem lại boundary. Một candidate Pricing riêng chỉ có lý do khi khả năng nghiệp vụ, sở hữu và chu kỳ thay đổi thực sự khác biệt.

**Order ↔ Fulfillment:** Order xác nhận yêu cầu mua; Fulfillment thực hiện chuẩn bị và vận chuyển. Thông tin tiến độ vận chuyển có thể đến muộn; Order chỉ nên giữ trạng thái tổng quan hoặc projection phù hợp, không tự sửa dữ liệu vận hành logistics.

**Order ↔ Notification:** Gửi email thường không được chặn transaction xác nhận đơn. Nếu email bị lỗi, đơn hàng đã xác nhận vẫn cần đúng; gửi lại email nên được xử lý có idempotency và khả năng theo dõi.

### 4.2. Quyền sở hữu dữ liệu: mô hình ghi một chủ

Ví dụ ownership tối thiểu:

~~~text
Order DB                     Inventory DB                Payment DB
---------------------        ----------------------      ------------------------
orders                       stock_items                 payment_attempts
order_lines                  stock_reservations          gateway_transactions
order_status_history         reservation_history         refund_requests
order_outbox                 inventory_outbox            payment_outbox

Order ghi order_*            Inventory ghi stock_*       Payment ghi payment_*
Không ghi trực tiếp           Không ghi trực tiếp         Không ghi trực tiếp
inventory/payment             order/payment               order/inventory
~~~

Một database vật lý có thể được chia sẻ vì giới hạn hạ tầng ban đầu, nhưng vẫn cần **ownership ở mức schema/bảng và quyền ghi**. Việc mỗi service có process riêng trong khi mọi service tự do đọc/ghi cùng các bảng không tạo ra ranh giới dữ liệu đáng tin.

**Snapshot và read model** không phải cùng quyền sở hữu: Order có thể lưu priceAtCheckout trong OrderLine để giữ lịch sử giao dịch; nó không vì vậy trở thành nguồn sự thật cho bảng giá đang có hiệu lực. Catalog có thể lưu stockAvailabilitySnapshot để hiển thị nhanh; Inventory vẫn là chủ sở hữu reservation.

## 5. Vẽ context map và các phụ thuộc cần chấp nhận

Một bản đồ phụ thuộc đơn giản cho luồng đặt hàng:

~~~text
                            +------------------+
                            |      Client      |
                            +---------+--------+
                                      |
                                      v
                               +------+------+
                               |    Order    |
                               +---+-----+---+
                                   |     |
                  ReserveStock     |     | RequestPayment
                                   v     v
                             +-----------+   +-----------+
                             | Inventory |   |  Payment  |
                             +-----------+   +-----+-----+
                                                    |
                                                    v
                                             External Gateway

              OrderConfirmed -> Fulfillment
              OrderConfirmed -> Notification
              Catalog/Stock -> Read models (chỉ theo contract)
~~~

Các cạnh cần ghi rõ hơn tên mũi tên:

| Từ → đến | Kiểu tương tác | Độ chắc chắn cần có | Xử lý khi lỗi |
| --- | --- | --- | --- |
| Client → Order | HTTP command | Biết request được nhận và có orderId | Idempotency cho PlaceOrder; tra cứu trạng thái |
| Order → Inventory | Command/response hoặc async command | Biết reservation được chấp nhận hay từ chối | Timeout → kiểm tra reservation theo operationId |
| Order → Payment | Command/async workflow | Tránh thu tiền trùng; biết kết quả cuối | Retry an toàn, webhook, reconciliation |
| Order → Fulfillment | Event/command | Chỉ thực hiện khi đơn đủ điều kiện | Outbox, tiêu thụ lặp an toàn |
| Order → Notification | Event | Không cản trở commit đơn | Retry có giới hạn, lịch sử gửi |
| Order → Catalog | Query hoặc snapshot | Thông tin sản phẩm/giá đúng với nghiệp vụ | Cache/snapshot theo chính sách, tránh chain dài |

Không phải cứ có đường mũi tên là phải dùng REST. Quyết định đồng bộ hay bất đồng bộ cần dựa vào ngữ nghĩa, deadline, mức nhất quán, khả năng chịu lỗi và độ phức tạp vận hành.

### 5.1. Contract là biên giới sử dụng, không chỉ endpoint

Một hợp đồng cần nói rõ:

- Bên gọi được yêu cầu thao tác nào và tác vụ đại diện cho ý nghĩa gì?
- Schema đầu vào/đầu ra hoặc payload sự kiện, version và các ràng buộc nghiệp vụ là gì?
- Điều kiện thành công, lỗi nghiệp vụ và kết quả chưa biết được mô tả ra sao?
- Khi timeout, consumer có thể retry không? Có idempotency key không?
- Có đảm bảo thứ tự event, delivery, thời gian hoàn tất hoặc deadline nào được công bố không?
- Ai có quyền gọi, giới hạn tốc độ và chính sách bảo mật nào áp dụng?
- Khi thay đổi contract, làm sao consumer cũ và mới cùng hoạt động?

Ví dụ minh họa cho Inventory:

~~~http
POST /v1/reservations
Idempotency-Key: order-1001-reservation-v1
Content-Type: application/json

{
  "orderId": "order-1001",
  "items": [
    {"sku": "book-01", "quantity": 2}
  ]
}
~~~

Giả sử Inventory chấp nhận giữ hàng ngay:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /v1/reservations/res-91

{
  "reservationId": "res-91",
  "orderId": "order-1001",
  "status": "RESERVED"
}
~~~

Nếu không thể xác minh tức thì, contract có thể trả 202 Accepted với operationId và endpoint truy vấn. **201/202 chỉ là ví dụ lựa chọn theo ngữ nghĩa được định nghĩa**, không bắt buộc cho mọi hệ thống.

Contract không nên lộ tên class hoặc bảng private trong Inventory. Consumer chỉ cần hiểu cách yêu cầu reservation và cách xác định kết quả.

## 6. Đánh đổi: kết dính, phụ thuộc, thay đổi và khả năng vận hành

Không có một số lượng microservice “đúng” cho mọi nền tảng. Ranh giới là đánh đổi giữa **cohesion trong boundary** và **coupling giữa boundaries**.

### 6.1. Dấu hiệu nên để cùng nhau

- Các quy tắc thay đổi cùng nhau vì một yêu cầu nghiệp vụ.
- Một invariant cần transaction cục bộ và khó đảm bảo nếu tách.
- Hai phần gần như luôn gọi nhau đồng bộ để hoàn thành hành vi nhỏ.
- Dữ liệu phải cập nhật nguyên tử và chia sẻ sâu cấu trúc domain.
- Hai phần có cùng nhóm sở hữu, cùng vòng release, cùng đặc điểm tải và không có lý do rõ ràng để tách.
- Việc tách chỉ thêm serialization, network, contract và operational overhead.

Ví dụ tạo OrderHeader và OrderLine thành hai service có thể ép một thao tác tạo đơn phải qua nhiều transaction và hợp đồng, dù cả hai thuộc một aggregate cùng vòng đời.

### 6.2. Dấu hiệu có thể tách

- Có mô hình/ngôn ngữ nghiệp vụ riêng và quyền quyết định dễ xác định.
- Phần chức năng có chu kỳ thay đổi, lịch release hoặc chủ sở hữu tương đối độc lập.
- Các bất biến được bảo vệ bên trong mỗi boundary; giao tiếp giữa chúng có thể định nghĩa rõ.
- Nhu cầu tài nguyên khác biệt đáng kể và có lợi khi scale riêng.
- Một dependency đặc thù như cổng thanh toán cần cô lập bảo mật, lỗi và kiểm soát.
- Dữ liệu và contract có thể chuyển dần mà không buộc tất cả consumer đổi cùng thời điểm.
- Có khả năng vận hành độc lập: deploy, monitor, on-call, rollback, quản lý sự cố.

Ví dụ Payment là candidate tách nếu nó quản lý nhiều cổng, cơ chế retry/đối soát phức tạp, yêu cầu bảo mật riêng và contract thanh toán đã ổn định. Nhưng nếu ứng dụng còn rất nhỏ, nó có thể bắt đầu bằng một module Payment với interface rõ ràng trong modular monolith.

### 6.3. Một ma trận đánh giá sơ bộ

Không dùng điểm số như “thuật toán tự chọn service”. Hãy dùng nó như bản ghi thảo luận:

| Tiêu chí | Câu hỏi cần chứng cứ | Nếu tách thì lợi/hại gì? |
| --- | --- | --- |
| **Business cohesion** | Các quy tắc có cùng một mục tiêu nghiệp vụ không? | Tách quá sớm có thể chia nhỏ invariant. |
| **Change coupling** | Trong 3–6 tháng qua hai phần đổi cùng ticket/commit bao nhiêu lần? | Cùng đổi thường xuyên làm tăng phối hợp release. |
| **Data ownership** | Có thể xác định một chủ ghi dữ liệu rõ ràng không? | Chồng chéo ownership dẫn đến distributed monolith. |
| **Consistency** | Có bao nhiêu invariant đòi transaction chung? | Giao dịch liên service làm tăng workflow và compensation. |
| **Runtime needs** | CPU, I/O, burst traffic và SLO khác nhau không? | Tách có thể scale riêng nhưng thêm hop/network. |
| **Team autonomy** | Đội nào thật sự có quyền triển khai và trực vận hành? | Tách service khi thiếu ownership làm tăng gánh nặng. |
| **Contract maturity** | Có thể phát biểu contract độc lập implementation không? | Contract chưa rõ dễ vỡ khi domain đổi. |
| **Failure isolation** | Khi một phần lỗi, phần khác có thể phục vụ an toàn không? | Ranh giới tốt giúp degrade; đường gọi dài vẫn có thể lan lỗi. |
| **Security/compliance** | Có dữ liệu nhạy cảm hoặc quyền truy cập cần cô lập? | Có thể biện minh cho boundary riêng và audit chặt. |

Mỗi ô nên có ba trạng thái về bằng chứng: **đã có dữ liệu**, **giả thuyết**, hoặc **chưa rõ**. Không tự tô “đạt” chỉ vì kiến trúc Microservices được ưu tiên.

## 7. Tạo bản phác thảo ranh giới ban đầu

Một boundary proposal phải đủ rõ để đội khác đọc và phản biện. Mẫu sau có thể dùng ngay trong workshop hoặc một Architecture Decision Record (ADR).

### 7.1. Boundary Canvas

~~~markdown
# Candidate Boundary: Inventory

## Mục đích
Quản lý số lượng khả dụng và reservation để đáp ứng cam kết giao hàng.

## Trong phạm vi
- Ghi nhận thay đổi tồn theo nghiệp vụ.
- Kiểm tra và giữ hàng theo một yêu cầu.
- Giải phóng reservation theo điều kiện rõ ràng.
- Cung cấp kết quả reservation và lịch sử liên quan.

## Ngoài phạm vi
- Tạo và xác nhận đơn hàng.
- Tính số tiền phải thu.
- Thu tiền, hoàn tiền.
- Soạn email gửi khách hàng.

## Invariant
- Không cho phép tổng reservation hợp lệ vượt nguồn hàng có thể giữ,
  ngoại trừ quy tắc backorder nếu được bật chính thức.

## Data ownership
- stock_items
- stock_reservations
- reservation_history

## Contract dự kiến
- ReserveStock(orderId, items, operationId)
- ReleaseStock(reservationId, operationId)
- GetReservation(operationId)
- StockReserved / StockRejected

## Dependencies
- Order gửi lệnh và nhận kết quả.
- Hệ thống kho cập nhật số liệu thực tế theo contract riêng.

## Giả thuyết
- Reservation là một năng lực riêng với quy tắc đồng thời độc lập.
- Tách Inventory giảm rủi ro ghi chéo dữ liệu tồn từ nhiều module.

## Rủi ro
- Network timeout khiến kết quả reservation không rõ.
- Đơn và reservation có thể lệch trạng thái tạm thời.

## Biện pháp
- Idempotency và tra cứu theo operationId.
- Outbox, reconciliation cho các workflow qua boundary.
- Theo dõi lỗi và độ trễ giữa Order và Inventory.

## Chứng cứ còn thiếu
- Tần suất thay đổi reservation cùng Order.
- Độ trễ và contention tại kho khi peak load.
- Sự cố dữ liệu tồn hiện tại và đội ownership.

## Quyết định dự kiến
- Giữ module rõ ràng hoặc tách thành service sau thử nghiệm.
~~~

Boundary Canvas không có giá trị nếu chỉ liệt kê tên API mà không nêu trách nhiệm và dữ liệu. Các thông tin “Ngoài phạm vi”, “Invariant”, “Rủi ro” và “Chứng cứ còn thiếu” giúp tránh mở rộng scope không kiểm soát.

### 7.2. Bản đồ quyền quyết định

Một bảng ownership thực tế cần có **một người/nhóm chịu trách nhiệm cuối** cho mỗi quyết định nghiệp vụ quan trọng.

| Quyết định | Chủ sở hữu logic | Bên cung cấp thông tin | Bằng chứng/contract |
| --- | --- | --- | --- |
| Đơn được tạo hợp lệ | Order | Catalog, Pricing, Customer tùy thiết kế | OrderCreated, snapshot đơn |
| Có đủ hàng để giữ | Inventory | Order gửi dòng hàng | Reservation result |
| Số tiền giao dịch được gửi tới cổng | Payment thực thi theo amount đã được xác nhận | Order/Pricing tạo order total hợp lệ | PaymentAttempt, order reference |
| Thanh toán thành công | Payment | Cổng thanh toán/đối soát | Payment status, event |
| Đơn được xác nhận hoàn tất | Order | Inventory, Payment | Các kết quả thỏa điều kiện |
| Đơn đã được giao thực tế | Fulfillment | Đối tác vận chuyển | Delivery proof, shipment event |
| Thông báo đã được gửi | Notification | Các event nghiệp vụ | DeliveryAttempt result |

Từ “owner” ở đây là **owner của sự thật/decision**. Một service khác vẫn có thể giữ bản sao để truy vấn và hiển thị, nhưng phải chỉ ra nguồn cập nhật và độ trễ được chấp nhận.

## 8. Thiết kế “đường may” để có thể tách sau này

Nếu bằng chứng chưa đủ để vận hành nhiều microservice, có thể bắt đầu từ **modular monolith** với boundary rõ trong mã và dữ liệu. Kiến trúc này giữ nhiều module trong một đơn vị triển khai nhưng có thể bảo vệ ownership bằng interface và kiểm soát phụ thuộc.

Ví dụ cấu trúc logic:

~~~text
commerce-app/
  order/
    api/
    application/
    domain/
    persistence/
  inventory/
    api/
    application/
    domain/
    persistence/
  payment/
    api/
    application/
    domain/
    persistence/
  integration/
    event-publication/
~~~

Tên folder chỉ minh họa. Điểm quan trọng là **mã của Order không gọi trực tiếp repository private của Inventory**. Order phụ thuộc interface/port công khai của Inventory. Khi có lý do tách process, ta có thể thay adapter gọi nội bộ bằng REST/message client trong khi giữ semantics của contract, dù vẫn cần migration và kiểm thử kỹ.

### 8.1. Những việc có thể chuẩn bị trước khi tách

- Định nghĩa boundary API/module interface với schema ổn định ở mức phù hợp.
- Gắn data ownership; giảm truy cập bảng xuyên module.
- Giữ domain model nội bộ riêng, tránh chia sẻ một “common domain model” khiến sửa một service buộc sửa tất cả.
- Định nghĩa idempotency và trạng thái bất đồng bộ ở các nghiệp vụ có side effect.
- Thêm tracing và metrics cho đường gọi logic từ sớm.
- Xác định mô hình deploy/rollback và migration dữ liệu khi tách.
- Ghi decision log: tại sao chưa tách hoặc tại sao tách, và tín hiệu cần xem lại.

Mục tiêu không phải giả định mọi module chắc chắn sẽ thành service. Một số module có thể ở chung lâu dài vì đó là ranh giới triển khai phù hợp nhất.

## 9. Kế hoạch kiểm chứng bằng thực tế: từ giả thuyết đến quyết định

Một sơ đồ chỉ mô tả ý định. Để kiểm chứng, cần chuyển ý định thành **giả thuyết có thể bác bỏ** và **chỉ số quan sát được**.

Ví dụ không đủ rõ:

> “Tách Inventory thành service sẽ tốt hơn.”

Ví dụ cụ thể hơn:

> “Nếu Inventory có quyền ghi reservation riêng và interface rõ, các thay đổi quy tắc tồn có thể được triển khai không cần đồng bộ release với Order trong phần lớn trường hợp; đồng thời tỉ lệ lỗi tạo đơn do giữ hàng và độ trễ gọi Inventory không vượt ngân sách đã thống nhất.”

Một giả thuyết tốt gồm:

1. **Giới hạn can thiệp:** chỉ thay đổi boundary liên quan và phạm vi traffic xác định.
2. **Kỳ vọng hành vi:** giảm phối hợp triển khai, cải thiện cô lập lỗi hoặc scale riêng.
3. **Chứng cứ cần thu thập:** change history, deployment records, traces, latency/error metrics, incidents, workflow correctness.
4. **Điều kiện thành công:** tiêu chí được đội kinh doanh và vận hành chấp nhận.
5. **Điều kiện bác bỏ:** tín hiệu cho thấy lợi ích không tồn tại hoặc chi phí vượt ngưỡng.
6. **Hướng đảo ngược:** trở lại module chung, đổi contract hoặc sửa sở hữu dữ liệu.

### 9.1. Lập giả thuyết cho từng boundary ứng viên

| Giả thuyết | Cách kiểm chứng | Tín hiệu giữ/tách/sửa |
| --- | --- | --- |
| Order và Inventory có chu kỳ thay đổi khác nhau | Xem ticket, commit, deployment history và phỏng vấn nhóm | Nếu liên tục phải thay đổi đồng thời, xem lại contract và phạm vi. |
| Inventory cần scale khác Order | Quan sát throughput, CPU, lock waits, queue depth dưới peak | Nếu tài nguyên chia sẻ mới là nút thắt, tách process chưa chắc giúp. |
| Payment nên cô lập lỗi cổng ngoài | Fault injection khi gateway chậm/ngắt; quan sát Order latency | Nếu Order bị block hàng loạt, thiết kế lại giao tiếp, deadline và xử lý trạng thái. |
| Notification có thể bất đồng bộ | Ngắt kênh gửi email; tạo đơn và đo kết quả | Nếu đơn vẫn chính xác và thông báo retry được, boundary có cơ sở. |
| Ownership dữ liệu giảm lỗi triển khai | Theo dõi truy cập bảng xuyên boundary và incident dữ liệu | Nếu vẫn shared writes, mục tiêu ownership chưa đạt. |
| Một số nghiệp vụ có thể gộp lại | Kiểm tra chuỗi synchronous calls và số release phải phối hợp | Nếu mỗi user request qua quá nhiều hop để cập nhật một invariant, cân nhắc gộp. |

### 9.2. Đặt baseline trước can thiệp

Số liệu sau khi tách mà không có baseline thường khó kết luận. Có thể lấy dữ liệu từ một khoảng thời gian đại diện cho tải bình thường và cao điểm:

- **Lead time for change:** từ lúc code sẵn sàng đến lúc release khả dụng.
- **Deployment frequency và coordinated deployments:** tần suất deploy và số lần phải triển khai nhiều phần cùng nhau.
- **Change failure rate/rollback:** tỉ lệ thay đổi gây lỗi theo định nghĩa nội bộ.
- **Incident isolation:** sự cố một năng lực có làm gián đoạn chức năng không liên quan không?
- **Latency theo đường giao tiếp:** P50/P95/P99, số network hop, retry, timeout.
- **Throughput và tài nguyên:** request/s, queue lag, CPU, memory, DB pool, lock contention.
- **Business correctness:** số đơn thiếu reservation, payment không đối soát, trạng thái kẹt quá hạn.
- **Chi phí vận hành:** số dashboard, alert, on-call interruption, hạ tầng và thời gian hỗ trợ.
- **Team ownership:** số bước chuyển giao, nhóm tham gia một thay đổi và các lần chờ review.

Không có ngưỡng phổ quát “P95 dưới X ms là Microservices tốt”. SLO phải dựa vào kỳ vọng của sản phẩm và capacity thực tế; hãy ghi rõ số nào là **baseline đo được** và số nào chỉ là **mục tiêu thử nghiệm**.

### 9.3. Ví dụ bảng thí nghiệm có thể chạy

| ID | Câu hỏi | Thử nghiệm có kiểm soát | Chỉ số chính | Điều kiện dừng/rollback |
| --- | --- | --- | --- | --- |
| E1 | Inventory riêng có giảm coupling dữ liệu? | Chặn Order ghi trực tiếp stock; chỉ cho gọi interface | Số truy cập ghi chéo, lỗi reservation, số thay đổi liên đội | Không giữ được invariant hoặc phải deploy đồng thời quá nhiều |
| E2 | Khi Payment chậm, Order có còn phản hồi đúng ngữ nghĩa? | Inject timeout tại payment adapter ở môi trường thử nghiệm | Tỉ lệ UNKNOWN được đối soát, duplicate charge, độ trễ Order | Có giao dịch trùng hoặc mất dấu payment |
| E3 | Notification lỗi có ảnh hưởng đặt hàng? | Ngắt provider email nhưng cho tạo đơn | Tỉ lệ đơn tạo đúng, backlog retry | Email failure làm transaction đơn thất bại ngoài ý định |
| E4 | Tách Inventory giúp scale độc lập? | Chạy cùng kịch bản tải với cấu hình module/service so sánh | Throughput, P95, CPU, DB lock và chi phí | Lỗi tính đúng hoặc tài nguyên tổng vượt ngân sách |
| E5 | Contract có chịu được release lệch phiên bản? | Chạy provider phiên bản mới và consumer cũ | Contract tests, lỗi giải mã, tỉ lệ request lỗi | Consumer cũ gặp lỗi không tương thích |

Mỗi thử nghiệm phải xác định dataset, môi trường, workload và khả năng nhiễu. So sánh hai cấu hình với số tài nguyên, lượng traffic và điều kiện khác hẳn có thể dẫn đến kết luận sai.

## 10. Kiểm chứng trên nhiều lớp: domain, contract, runtime và tổ chức

### 10.1. Kiểm chứng domain correctness

Đặt những bất biến thành kịch bản kiểm thử:

- Hai request đồng thời giữ cùng SKU không được vượt lượng tồn theo quy tắc.
- Cùng orderId và operationId gửi ReserveStock hai lần không tạo hai reservation có tác dụng lặp.
- Payment đã commit nhưng response mất không khiến Order tạo hai giao dịch thu tiền.
- Đơn đã CANCELLED không bị event cũ đưa về CONFIRMED.
- Inventory nhả reservation sau hủy theo chính sách và không nhả hai lần gây sai số.
- Snapshot giá của đơn đã chốt không bị thay đổi theo bảng giá hiện hành.

Kiểm thử bằng local transaction, integration tests và fault injection; chỉ kiểm thử happy path là không đủ để kết luận boundary có thể vận hành an toàn.

### 10.2. Kiểm chứng contract

Các kỹ thuật có thể sử dụng:

- **OpenAPI/schema validation:** đối chiếu định dạng request/response.
- **Consumer-driven contract tests:** xác nhận những kỳ vọng mà consumer đang dựa vào.
- **Schema compatibility checks:** kiểm tra thay đổi sự kiện, trường bắt buộc và version.
- **Mixed-version tests:** provider mới chạy cùng consumer cũ trong thời gian rollout.
- **Behavioral tests:** kiểm tra ý nghĩa nghiệp vụ, idempotency, lỗi và trạng thái chưa biết.

Một schema hợp lệ chưa chắc chứng minh ngữ nghĩa đúng. Ví dụ đổi cách hiểu status=PENDING từ “đang giữ hàng” sang “đã thanh toán, chờ giao” có thể phá consumer mà JSON schema vẫn không đổi.

### 10.3. Kiểm chứng chịu lỗi

Các tình huống:

| Tình huống | Cần quan sát |
| --- | --- |
| Tắt một instance Inventory | Các instance còn lại và load balancer xử lý ra sao? |
| Ngắt kết nối Order ↔ Inventory | Timeout, retry và trạng thái đặt hàng có rõ ràng không? |
| Payment commit rồi mất response | Có đối soát được, có trùng charge không? |
| Broker tạm ngừng | Outbox giữ sự kiện, backlog có được xử lý sau khôi phục không? |
| Message gửi trùng hoặc đến muộn | State machine có giữ bất biến và không lùi trạng thái không? |
| Database chậm | Pool cạn, chain timeout và cơ chế bảo vệ upstream như thế nào? |
| Rolling deployment lệch phiên bản | Các contract còn tương thích trong cửa sổ chuyển đổi không? |

Đừng thử những kịch bản phá lỗi trực tiếp trên production khi chưa có kiểm soát và phạm vi cho phép. Có thể bắt đầu ở môi trường thử nghiệm giống production về topology, semantics và workload, sau đó dùng rollout giới hạn theo chính sách vận hành.

### 10.4. Kiểm chứng quyền tự chủ của đội ngũ

Microservices được kỳ vọng giảm nhu cầu điều phối khi triển khai các năng lực khác nhau. Hãy kiểm tra thật:

- Một thay đổi Inventory có cần merge vào nhiều codebase không?
- Có cần đóng băng release của Order để Inventory deploy không?
- Có thể rollback Inventory mà Order không yêu cầu rollback đồng thời không?
- Ai trực nhận cảnh báo và ai được quyền sửa dữ liệu khi sự cố?
- API/schema có đủ ổn định để hai đội làm việc song song không?

Nếu câu trả lời thực tế đều là “phải phối hợp cùng lúc”, hệ thống có thể vẫn là **distributed monolith** dù có nhiều container.

## 11. Vòng phản hồi thực tế: đo, đối chiếu, quyết định và cập nhật

Quá trình đề xuất boundary nên lặp lại theo chu kỳ:

~~~text
Hiểu nghiệp vụ
      |
      v
Phác thảo boundary + ownership + contract
      |
      v
Ghi giả thuyết và điều kiện bác bỏ
      |
      v
Thu baseline / bổ sung instrumentation
      |
      v
Thử nghiệm nhỏ có kiểm soát
      |
      v
Đo tính đúng + vận hành + tốc độ thay đổi
      |
      +----> Dữ liệu ủng hộ ----> Giữ / mở rộng từng bước
      |
      +----> Dữ liệu phản bác --> Sửa boundary / gộp / hoãn tách
      |
      v
Cập nhật ADR, context map và backlog
~~~

### 11.1. Dùng tín hiệu có thể quan sát thay vì cảm giác

Ví dụ sau một thử nghiệm tách Payment:

- Hệ thống dễ cô lập timeout cổng thanh toán hơn.
- Độ trễ đặt hàng thay đổi vì đã thêm network hop và trạng thái bất đồng bộ.
- Phát sinh nhiều operation trạng thái VERIFYING nếu webhook chậm.
- Đội Payment có thể deploy connector mới mà không cần release Order.
- Nhưng giao diện hỗ trợ khách hàng phải xử lý trạng thái “đang xác minh”.

Đánh giá phải nhìn **tổng thể lợi ích và chi phí**, kể cả tác động sản phẩm. Việc một microservice có thể deploy riêng không đủ nếu người dùng bị treo thanh toán hoặc đội hỗ trợ không thể đối soát.

### 11.2. Ba loại quyết định sau thử nghiệm

**Giữ boundary:** khi ownership rõ, contract ổn định, các invariant được bảo vệ và lợi ích vận hành/sản phẩm xuất hiện.

**Sửa boundary:** khi phạm vi quá rộng/hẹp, thuật ngữ mâu thuẫn hoặc phụ thuộc dữ liệu khiến thay đổi liên tục lan sang nơi khác. Có thể chuyển một policy, aggregate hoặc quyền ghi sang chủ sở hữu phù hợp hơn.

**Hoãn tách hoặc gộp lại:** khi chi phí mạng, deployment, observability và coordination lớn hơn giá trị tự chủ; một modular monolith hoặc ít service hơn có thể hiệu quả hơn.

Không nên coi “gộp lại” là thất bại về kiến trúc. Ranh giới phục vụ yêu cầu sản phẩm; mục tiêu là tính đúng, tốc độ thay đổi và vận hành phù hợp.

## 12. Chiến lược chuyển đổi dần với rủi ro được kiểm soát

Trong hệ thống đã chạy, chuyển từ module/bảng cũ sang service mới nên có các giai đoạn rõ. Một kế hoạch điển hình:

### Giai đoạn 0 — Xác lập hiện trạng và quyền sở hữu

- Liệt kê chức năng, dòng dữ liệu, consumer và API hiện có.
- Tìm nơi đang có shared writes và giao dịch xuyên nhiều bảng.
- Thu baseline về tải, lỗi, độ trễ, release và bất biến nghiệp vụ.
- Ghi ADR cho candidate boundary, phạm vi, giả thuyết và lối quay lại.

### Giai đoạn 1 — Làm rõ ranh giới trong mã

- Giới hạn truy cập private module, đưa các thao tác vào interface rõ ràng.
- Định nghĩa contract và operation ID trước khi tách process.
- Kiểm thử invariant và xử lý lặp.
- Cài instrumentation cho các đường gọi, timeout, trạng thái bất thường.

Ở bước này vẫn có thể giữ chung process/deployment, giúp đo coupling nghiệp vụ trước khi gánh chi phí mạng.

### Giai đoạn 2 — Chuyển quyền sở hữu dữ liệu

- Chỉ định bên có quyền ghi chính thức cho từng dữ liệu.
- Thiết kế cơ chế đồng bộ dữ liệu đọc hoặc migration nếu cần.
- Đảm bảo consumer cũ vẫn chạy trong giai đoạn chuyển tiếp.
- Chọn chiến lược chống dual writes: outbox, CDC hoặc adapter thích hợp theo điều kiện thực tế.
- Định nghĩa thủ tục đối soát dữ liệu và phát hiện bản ghi lệch.

**Dual write** không có transaction nguyên tử chung có thể làm mất đồng bộ nếu service crash giữa hai lần ghi. Nếu sử dụng dual write tạm thời cho migration, phải có chính sách xác minh, giải quyết xung đột và rollback rõ.

### Giai đoạn 3 — Tách runtime trong phạm vi nhỏ

- Deploy service candidate với health/readiness, log, trace, dashboard và cảnh báo.
- Chạy shadow read hoặc mirror traffic ở nơi an toàn: nhánh thử nghiệm **không được tạo side effect như thu tiền thật**.
- Chuyển một nhóm thao tác/traffic có thể rollback qua route mới.
- Theo dõi latency, lỗi, invariant, retry và tác động downstream.
- Giữ tính tương thích của contract trong giai đoạn phiên bản cũ/mới cùng tồn tại.

### Giai đoạn 4 — Mở rộng và loại bỏ lối cũ

- Chỉ tăng traffic sau khi các tiêu chí tính đúng và vận hành đạt.
- Xác minh các consumer đã chuyển, các trạng thái tồn đọng được xử lý.
- Loại bỏ đường ghi và API cũ khi thật sự không còn bên phụ thuộc.
- Cập nhật sơ đồ ownership, ADR, tài liệu vận hành và hướng dẫn khôi phục.
- Tiếp tục theo dõi những tình huống ít gặp như refund, cancel sau thanh toán, high load và incident định kỳ.

### 12.1. Một ví dụ phân rã theo Strangler Pattern

Thay vì viết lại toàn hệ thống cùng lúc:

~~~text
Client → Routing Facade
           |
           +-- Đường cũ: Monolith (năng lực chưa tách)
           |
           +-- Đường mới: Inventory API
                              |
                              +-- Inventory-owned storage
~~~

Ở giai đoạn đầu, một nhóm request được chuyển sang Inventory API mới. Bên cũ có thể dùng adapter gọi Inventory thay vì ghi bảng tồn trực tiếp. Khi đã kiểm chứng, tăng phạm vi dần.

Điều quan trọng là **chỉ một nơi có quyền quyết định cuối cùng cho một hành vi ghi tại một thời điểm**, trừ khi cơ chế migration chủ động kiểm soát song song và reconciliation. Hai hệ thống cùng “là nguồn sự thật” mà không có quy tắc phân giải thường tạo lỗi khó khôi phục.

## 13. Quyết định giữa đồng bộ và bất đồng bộ theo boundary

Mỗi quan hệ giữa boundaries cần quyết định giao tiếp dựa trên yêu cầu:

| Câu hỏi | Thiên về đồng bộ | Thiên về bất đồng bộ |
| --- | --- | --- |
| Caller có cần kết quả ngay để tiếp tục? | Thường phù hợp nếu thời hạn chờ chấp nhận được | Phù hợp nếu có trạng thái PENDING và bước hoàn tất sau |
| Dependency có thể chậm hoặc gián đoạn dài? | Cần timeout và degrade rõ | Có thể lưu công việc bền vững và retry về sau |
| Có quy trình nhiều bước, timeout và compensation? | Đơn giản hơn khi rất ngắn và ít lỗi | Workflow/saga có thể dễ phục hồi hơn nếu được thiết kế đúng |
| Người dùng cần phản hồi tức thì? | Trả kết quả đồng bộ nếu có bằng chứng | Trả 202/operationId và cập nhật sau |
| Có yêu cầu thứ tự cao? | Dễ suy luận theo request đơn lẻ | Phải thiết kế partition key/sequence/idempotency |

Async không tự động làm hệ thống resilient; nó chuyển độ phức tạp sang queue, consumer, ordering, deduplication và workflow tracking. Sync không tự động là thiết kế tệ; một query ngắn, được bảo vệ bằng deadline và có SLA phù hợp có thể rất hợp lý.

### 13.1. Ví dụ thất bại không đồng thời khi tách boundary

~~~text
t0 Order gửi ReserveStock(operationId=R1)
t1 Inventory nhận và commit reservation
t2 Phản hồi mất trên mạng
t3 Order timeout, trạng thái UNKNOWN
t4 Order query GetReservation(R1)
t5 Inventory trả RESERVED
t6 Order tiếp tục RequestPayment
~~~

Khi quyết định có tách Inventory thành service, phải coi cơ chế này là **một phần chi phí boundary**. Nếu business workflow không có chỗ lưu trạng thái UNKNOWN và tra cứu R1, thiết kế ban đầu chưa đủ để chịu lỗi mạng.

## 14. Những phản mẫu cần tránh

### 14.1. Tách mỗi bảng hoặc mỗi CRUD endpoint thành service

Ví dụ OrderService, OrderLineService, OrderStatusService chỉ vì có ba bảng. Tạo đơn sẽ liên tục gọi qua mạng để thao tác cùng một invariant; cách này tăng độ khó transaction mà ít mang lại tự chủ.

**Hướng xử lý:** đặt theo quyền quyết định và vòng đời nghiệp vụ; giữ Order aggregate và các quy tắc liên quan gần nhau.

### 14.2. Shared database với nhiều chủ ghi

Hai service cùng sửa bảng stock khiến ownership mơ hồ, thay schema phải triển khai đồng thời và khó quy trách nhiệm khi lệch tồn.

**Hướng xử lý:** đưa quyền ghi về một owner; các bên khác truy cập qua contract hoặc projection có quy tắc đồng bộ.

### 14.3. Shared domain library quá lớn

Nhiều service dùng chung một thư viện chứa entity, quy tắc và model nội bộ. Mỗi thay đổi đòi nâng version hàng loạt, tạo coupling ở cấp code.

**Hướng xử lý:** chia sẻ những thành phần kỹ thuật hoặc schema contract cần thiết một cách có kiểm soát; giữ domain model nội bộ theo bounded context và mapping ở biên.

### 14.4. Một request đi qua chuỗi synchronous quá dài

~~~text
Gateway → A → B → C → D → E → DB
~~~

Một chặng chậm làm cả request chậm hoặc fail; retry ở nhiều tầng có thể khuếch đại tải. Nếu chuỗi lặp đi lặp lại cho một hành vi nhỏ, cần đánh giá lại ranh giới, hợp đồng hoặc mô hình xử lý.

**Hướng xử lý:** đo trace, xác định chặng thật sự cần đồng bộ, gộp phần có cùng invariant hoặc đưa workflow dài sang async có trạng thái rõ.

### 14.5. Chia theo sơ đồ tổ chức hiện tại

Một nhóm “frontend” có FrontendService và nhóm “database” có DatabaseService, khiến toàn bộ quy trình nghiệp vụ luôn phải qua nhiều tầng phụ thuộc.

**Hướng xử lý:** căn theo năng lực nghiệp vụ và khả năng sở hữu trọn hành vi; cấu trúc team có thể hỗ trợ nhưng không thay thế boundary domain.

### 14.6. Thiết kế contract rồi coi nó vĩnh viễn đúng

Business thay đổi, consumer mới xuất hiện, data volume tăng và thực tế có thể bác bỏ giả thuyết. Một contract chưa ổn định nhưng bị công bố quá sớm làm chi phí thay đổi tăng cao.

**Hướng xử lý:** phát triển contract tương thích, version khi cần, ghi giả thuyết và cập nhật ADR khi có chứng cứ.

### 14.7. Lấy “có thể scale độc lập” làm lý do mặc định

Tách một service mới có thể làm tăng số connection, network hop, deployment và operational burden. Nếu không có nút thắt đáng kể hoặc tải khác biệt, lợi ích scale riêng chỉ là suy đoán.

**Hướng xử lý:** đo tải và saturation. Phân biệt bottleneck ở CPU ứng dụng, database locks, I/O và bên thứ ba; thêm replica không sửa được nút thắt dùng chung.

### 14.8. Sơ đồ đẹp nhưng thiếu khả năng vận hành

Có các box và mũi tên nhưng không ai sở hữu on-call, không có trace ID, outbox hoặc playbook cho trạng thái kẹt.

**Hướng xử lý:** mỗi boundary candidate phải có owner, SLO phù hợp, dashboard, cảnh báo, cách rollback và chính sách xử lý lệch dữ liệu.

## 15. Mẫu kế hoạch kiểm chứng thực hiện được

Ví dụ dưới đây là một **mẫu điền** để nhóm chuyển proposal thành hành động. Các mốc số và thời gian cần được xác định từ yêu cầu thực tế, không dùng mặc định làm tiêu chuẩn.

~~~markdown
# Boundary Validation Plan: Inventory

## Quyết định cần kiểm chứng
Inventory có nên tách khỏi Order thành dịch vụ triển khai độc lập?

## Bối cảnh
- Order hiện thực nghiệp vụ tạo/hủy đơn.
- Inventory có các quy tắc giữ hàng và nhả hàng.
- Chưa xác minh đầy đủ nhu cầu scale và thay đổi độc lập.

## Giả thuyết
H1: Ranh giới dữ liệu Inventory cho phép thay đổi quy tắc giữ hàng
    mà không sửa trực tiếp Order.
H2: Giao tiếp qua contract giữ được tính đúng trong timeout/retry.
H3: Chi phí vận hành và độ trễ tăng thêm nằm trong ngân sách cho phép.

## Baseline cần thu
- Tần suất thay đổi Order + Inventory trong cùng ticket.
- Số lần lỗi giữ hàng và oversell được phát hiện.
- Độ trễ tạo đơn ở tải bình thường/cao điểm.
- Độ bão hòa CPU/DB và số lượng retry.

## Thử nghiệm
E1: Đóng quyền ghi trực tiếp Inventory khỏi Order.
E2: Chạy contract tests và concurrency tests cho ReserveStock.
E3: Inject timeout sau commit reservation; query lại theo operationId.
E4: Thử rollout phiên bản mới với consumer cũ.
E5: Đo latency, errors và resource khi bật boundary adapter mới.

## Tiêu chí quyết định
- Không vi phạm invariant về reservation.
- Các thao tác lặp không tạo side effect trùng.
- Có thể quan sát và khôi phục operation chưa rõ kết quả.
- Hệ quả latency, vận hành và phối hợp release được đánh giá
  theo SLO và ngân sách đã thống nhất.

## Điều kiện dừng/rollback
- Phát hiện tình huống oversell hoặc ghi sai reservation.
- Mất khả năng đối soát trạng thái đơn và reservation.
- Consumer không tương thích hoặc lỗi tăng ngoài ngưỡng đã duyệt.
- Không thể vận hành theo on-call/monitoring hiện có.

## Tài liệu bàn giao
- Boundary Canvas và context map.
- Contract, schema, sequence diagram.
- ADR nêu lý do và các lựa chọn đã xem xét.
- Dashboard/trace và báo cáo số liệu trước/sau.
- Playbook sự cố, rollback và reconciliation.
~~~

### 15.1. Nguyên tắc đặt ngưỡng

Một ngưỡng kiểm chứng cần nối với cam kết thật của hệ thống:

- **Tính đúng:** thường là điều kiện chặn, ví dụ không chấp nhận duplicate charge hoặc oversell do lỗi thiết kế.
- **Độ trễ:** so với SLO của hành trình người dùng và ngân sách các chặng; dùng phân phối P95/P99 thay vì chỉ trung bình.
- **Độ tin cậy:** đo tỉ lệ request thành công theo contract, trạng thái UNKNOWN giải quyết được, duration của các workflow.
- **Vận hành:** tính cả on-call, số incident, deploy và chi phí hạ tầng, không chỉ hiệu năng CPU.
- **Thay đổi:** theo dõi coordinated deployment, lead time và sự cố sau change trong khoảng quan sát đủ đại diện.

Nếu không đủ dữ liệu để đưa ra quyết định, kết quả hợp lệ là **“chưa kết luận, cần thu thêm chứng cứ X”**. Không bắt buộc tách chỉ vì roadmap ghi chữ “Microservices”.

## 16. Bài tập thực hành

### Bài 1 — Chọn boundary trong hệ thống đặt lịch

Một sản phẩm đặt lịch khám có các năng lực: hồ sơ bác sĩ, lịch trống, đặt lịch, gửi SMS, thanh toán trước, hủy lịch. Lịch trống và đặt lịch cần tránh hai bệnh nhân chiếm cùng một slot.

**Yêu cầu:**

1. Đề xuất tối đa ba hoặc bốn boundary ứng viên và giải thích quyền sở hữu.
2. Chỉ ra invariant phải bảo vệ khi hai người đặt cùng slot.
3. Đề xuất contract cho lệnh giữ slot và cách xử lý timeout sau commit.
4. Ghi ít nhất hai giả thuyết cần kiểm chứng trước khi tách service vật lý.

**Gợi ý suy luận:** Đặt lịch và quyền sở hữu slot có thể cần chung một boundary giao dịch; gửi SMS thường có thể bất đồng bộ. Payment cần quy trình xác minh theo operationId. Không nên chọn số service chỉ dựa vào số danh từ.

### Bài 2 — Khảo sát một monolith hiện hữu

Cho hệ thống có ba module: Orders, Stock, Email. Mọi module dùng chung database; Orders sửa trực tiếp bảng stock; một lỗi SMTP làm transaction tạo đơn rollback.

**Yêu cầu:**

- Vẽ quyền ghi hiện tại và các mũi tên coupling.
- Thiết kế bước đầu tiên để tạo boundary rõ mà chưa cần tách process.
- Nêu cách chuyển email ra khỏi transaction tạo đơn.
- Xác định các test chứng minh không oversell và email retry không tạo đơn trùng.

**Gợi ý suy luận:** Bước đầu nên đưa quyền ghi tồn về module Stock thông qua interface; chỉ commit đơn theo invariant của Order và phát ý định thông báo bằng cơ chế bền vững thích hợp. Khi tách runtime mới phải tính mạng, message và timeout.

### Bài 3 — Đọc số liệu và đề xuất quyết định

Trong bốn tuần thử nghiệm tách Inventory, đội thấy:

- Các change request thuộc Inventory ít cần sửa Order hơn.
- P95 của luồng đặt hàng tăng.
- Tỉ lệ timeout khi cao điểm tăng, nhưng database lock contention giảm.
- Hai trường hợp reservation đang UNKNOWN được giải quyết bằng đối soát.
- Số sự cố oversell không tăng trong tập kiểm thử đã chạy.

**Yêu cầu:** Kết luận ngay “nên tách” hay cần thêm điều kiện? Lập bảng lợi ích, chi phí, rủi ro và phép đo bổ sung.

**Gợi ý suy luận:** Các tín hiệu đang mâu thuẫn; chưa thể đưa ra quyết định chỉ từ một chỉ số. Cần so sánh ngưỡng SLO, lỗi khi cao điểm, tính đại diện của dữ liệu, khả năng vận hành và giải pháp giảm latency/timeout.

### Bài 4 — Sửa proposal thiếu chứng cứ

Một bản thiết kế viết: “Tách Pricing và Discount vì hai bảng khác nhau, scale được vô hạn, không có tác động đến Order”.

**Yêu cầu:** Viết lại thành ba giả thuyết có thể kiểm chứng và danh sách thông tin còn thiếu.

**Gợi ý suy luận:** Cần phân biệt ai quyết định giá cuối, invariant của khuyến mãi, tần suất thay đổi cùng nhau, tải thực tế và cách Order giữ snapshot giá giao dịch. “Scale vô hạn” không phải giả thuyết thực tế có thể chấp nhận.

### Bài 5 — Kiểm chứng tương thích khi chuyển đổi

Order Service hiện gọi phương thức nội bộ ReserveStock. Nhóm muốn chuyển sang HTTP Inventory Service trong một rollout từng phần.

**Yêu cầu:** Thiết kế route chuyển đổi, idempotency key, cách nhận biết kết quả UNKNOWN và tiêu chí rollback. Viết một test mô phỏng Inventory commit reservation rồi mất response.

**Gợi ý suy luận:** Không được tạo reservation mới khi retry cùng operation; cần tra cứu bằng idempotency key/operationId và kiểm tra dữ liệu cuối. Rollback cần giữ quyền ghi rõ ràng, tránh cả đường cũ và đường mới cùng thay đổi tồn không có kiểm soát.

## 17. Checklist làm việc cho một boundary proposal

Checklist này dành cho việc **thiết kế trước khi xây dựng**, để nhóm thấy các quyết định còn thiếu; không phải một chứng nhận tự động rằng kiến trúc đã đúng.

- [ ] Có mô tả năng lực nghiệp vụ và những điều ngoài phạm vi.
- [ ] Có định nghĩa thuật ngữ quan trọng trong bounded context.
- [ ] Có bất biến nghiệp vụ và nơi chịu trách nhiệm bảo vệ.
- [ ] Có người/chức năng sở hữu dữ liệu và đường ghi.
- [ ] Có danh sách consumer, producer và các contract chủ yếu.
- [ ] Có sequence cho luồng thành công và ít nhất các nhánh lỗi quan trọng.
- [ ] Có thiết kế timeout, retry/idempotency, trạng thái chưa biết và đối soát khi cần.
- [ ] Có thông tin về change coupling, tải, deployment và vận hành.
- [ ] Có giả thuyết, dữ liệu còn thiếu và kế hoạch đo lường.
- [ ] Có cách kiểm chứng bằng thử nghiệm nhỏ, tiêu chí dừng và phương án rollback.
- [ ] Có ADR ghi lý do giữ/tách/gộp boundary và thời điểm xem lại.
- [ ] Có chủ sở hữu vận hành, logging, tracing, metrics và hướng dẫn khôi phục phù hợp.

Nếu không thể trả lời các câu hỏi này, một sơ đồ gồm nhiều box dịch vụ vẫn chưa đủ làm cơ sở để triển khai an toàn.

## 18. Ghi nhớ

**Thiết kế boundary ban đầu là thiết kế quyền quyết định và khả năng thay đổi, sau đó mới là thiết kế số lượng tiến trình.** Hãy bắt đầu bằng luồng nghiệp vụ, thuật ngữ, invariant, data ownership và contract. Giữ các quy tắc cần nhất quán gần nhau; tách khi trách nhiệm độc lập đủ rõ và lợi ích được chứng minh.

Với mỗi boundary ứng viên, hãy ghi:

1. **Vì sao đề xuất ranh giới này?** Năng lực, bất biến, dữ liệu và consumer.
2. **Điều gì có thể làm đề xuất sai?** Shared writes, đổi cùng nhau quá thường xuyên, độ trễ, sự cố liên service và thiếu ownership.
3. **Sẽ kiểm chứng thế nào?** Baseline, test tính đúng, thử lỗi, đo tải, contract compatibility, dữ liệu triển khai và vận hành.
4. **Nếu chứng cứ phản bác thì làm gì?** Sửa phạm vi, gộp, hoãn tách hoặc quay về module có contract rõ.

Kết quả mong muốn không phải “đã tách được nhiều microservice”, mà là một kiến trúc có **ranh giới nghiệp vụ dễ hiểu, dữ liệu có chủ sở hữu, thay đổi ít gây dây chuyền, sự cố được cô lập phù hợp và quyết định được cập nhật bằng bằng chứng thực tế**.
