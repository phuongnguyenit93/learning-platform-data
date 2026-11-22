# Ánh xạ ngữ cảnh và quan hệ giữa các nhóm sở hữu

## 1. Mở đầu: vì sao vẽ các hộp Microservices vẫn chưa đủ?

Khi phân rã một hệ thống lớn thành Microservices, ta thường bắt đầu bằng các ô như Customer Service, Order Service, Payment Service và Inventory Service. Sơ đồ này cho thấy những thành phần dự kiến, nhưng chưa trả lời được các câu hỏi thực tế:

- **Từ “khách hàng” nghĩa là gì** trong bán hàng, thanh toán và chăm sóc khách hàng?
- Dịch vụ nào có quyền quyết định đơn đã thanh toán hay chưa, hàng đã được giữ hay chưa?
- Nhóm nào sở hữu cách tính giá; nhóm nào chỉ sử dụng kết quả đã công bố?
- Khi hai nhóm cần thay đổi API hoặc định nghĩa của một sự kiện, ai phải chủ động phối hợp?
- Nếu hệ thống cũ có khái niệm “trạng thái đơn” khác hệ thống mới, bên nào phải chuyển đổi cách hiểu?
- Một nhóm phát triển chịu trách nhiệm cho những ranh giới nào, và phải làm gì khi ranh giới đó thay đổi?

Những câu hỏi này là nội dung của **Context Mapping** trong Domain-Driven Design (DDD): hiểu các **Bounded Context** (ngữ cảnh giới hạn), chỉ rõ quan hệ giữa chúng và làm rõ quan hệ hợp tác giữa những nhóm chịu trách nhiệm.

Context Map là bản đồ **ý nghĩa nghiệp vụ, quyền sở hữu và phụ thuộc tích hợp**. Nó bổ sung cho sơ đồ container, network hay deployment. Sơ đồ hạ tầng trả lời “phần mềm chạy ở đâu và gọi nhau thế nào”; Context Map giúp trả lời “mô hình nào đúng trong phạm vi nào, ai quyết định mô hình đó và hai phạm vi tương tác ra sao”.

Sau bài này, bạn có thể:

1. Phân biệt Domain, Subdomain, Bounded Context, Microservice, Team và Context Map.
2. Vẽ bản đồ quan hệ giữa các ngữ cảnh trong một bài toán thương mại điện tử.
3. Xác định upstream/downstream và các kiểu quan hệ như Customer–Supplier, Partnership, Conformist, Anti-Corruption Layer, Shared Kernel, Open Host Service, Published Language và Separate Ways.
4. Ghi rõ nhóm sở hữu, nguồn dữ liệu có thẩm quyền, hợp đồng tích hợp và cách quản lý thay đổi.
5. Phát hiện các ranh giới làm phát sinh phụ thuộc chặt hoặc tranh chấp quyền quyết định.
6. Sử dụng Context Map để đưa ra quyết định phân rã và phối hợp phát triển phù hợp.

## 2. Các khái niệm nền tảng

### 2.1. Domain và Subdomain

**Domain** là lĩnh vực vấn đề doanh nghiệp cần giải quyết, ví dụ thương mại điện tử. **Subdomain** là phần vấn đề có đặc điểm và năng lực nghiệp vụ riêng, ví dụ quản lý danh mục, định giá, đặt hàng, thanh toán và giao vận.

Trong DDD, có thể phân loại subdomain thành:

- **Core:** năng lực mang lại khác biệt cạnh tranh cần đầu tư thiết kế cẩn thận.
- **Supporting:** hỗ trợ core nhưng thường không phải nguồn khác biệt chính.
- **Generic:** năng lực phổ biến, có thể tái sử dụng hoặc mua giải pháp ngoài nếu phù hợp.

Việc phân loại tùy **chiến lược của tổ chức**. Với một sàn giao dịch, định giá theo thời gian thực có thể là core; với cửa hàng đơn giản, khả năng đó có thể chỉ là supporting. Không gán “core” chỉ vì thành phần quan trọng hoặc phức tạp về kỹ thuật.

### 2.2. Bounded Context

**Bounded Context** là ranh giới mà bên trong đó một mô hình domain, ngôn ngữ nghiệp vụ và các quy tắc nhất quán có ý nghĩa rõ ràng. Mỗi ngữ cảnh có cách dùng thuật ngữ, bất biến, quy trình và dữ liệu phù hợp nhiệm vụ của nó.

Ví dụ cùng từ **Order**:

- Trong **Ordering Context**, Order là cam kết mua hàng, gồm dòng hàng, giá chốt, địa chỉ, trạng thái chấp nhận và hủy.
- Trong **Payment Context**, đối tượng trung tâm có thể là Payment Attempt, Charge và Refund; Order ID chỉ là tham chiếu đến yêu cầu thanh toán.
- Trong **Shipping Context**, đơn có thể được nhìn qua Shipment, Package, Waybill và Delivery Attempt. Một Order có thể tương ứng nhiều kiện hàng.

Các mô hình không cần dùng chung một class Order khổng lồ. Ngữ cảnh giới hạn cho phép mỗi nhóm dùng khái niệm chính xác trong phạm vi mình phụ trách.

### 2.3. Ubiquitous Language

**Ubiquitous Language** là ngôn ngữ chung giữa chuyên gia nghiệp vụ và nhóm kỹ thuật **trong một Bounded Context**. Từ vựng phải đủ chính xác để dùng trong thảo luận, API, event, mã nguồn và kiểm thử.

Ví dụ trong Inventory, **AvailableStock**, **ReservedStock** và **StockOnHand** không được dùng lẫn lộn. Trong Shipping, **ShipmentCreated** khác **ShipmentDelivered**. Một thuật ngữ giống nhau ở hai ngữ cảnh không có nghĩa chúng có cùng định nghĩa.

### 2.4. Context Map

**Context Map** thể hiện các Bounded Context và **kiểu quan hệ giữa chúng**. Bản đồ có thể diễn đạt bằng sơ đồ, bảng hoặc tài liệu thỏa thuận. Mỗi đường nối nên có lý do nghiệp vụ, chiều phụ thuộc và cơ chế tích hợp.

Ví dụ đường nối “Ordering sử dụng kết quả thanh toán từ Payments” chưa đủ. Cần biết Payments cung cấp trạng thái gì, Ordering chấp nhận độ trễ nào, ai sở hữu hợp đồng và điều gì xảy ra khi nhà cung cấp trả timeout.

### 2.5. Nhóm sở hữu (Owning Team)

**Nhóm sở hữu** chịu trách nhiệm lâu dài với mô hình, hợp đồng, chất lượng vận hành và tiến hóa của ngữ cảnh hoặc capability được giao. Quyền sở hữu có thể gồm:

- Quyết định định nghĩa thuật ngữ và bất biến nghiệp vụ trong phạm vi đã thống nhất.
- Phát triển, thử nghiệm, triển khai, vận hành và xử lý sự cố các thành phần do nhóm quản lý.
- Duy trì API/event schema, tài liệu, SLO và quy trình thay đổi.
- Trao đổi với các nhóm phụ thuộc khi cần mở rộng hoặc thay đổi hợp đồng.

Một Bounded Context **không bắt buộc** tương đương chính xác một Microservice hoặc một nhóm. Một context có thể tạm được triển khai trong một module của monolith, hoặc chia thành nhiều thành phần kỹ thuật. Một nhóm có thể quản lý nhiều context nhỏ. Điều quan trọng là có **ranh giới khái niệm rõ và chủ sở hữu quyết định rõ**, tránh nhiều nhóm cùng sửa dữ liệu và quy tắc của nhau không có cơ chế phối hợp.

## 3. Phân biệt các lớp bản đồ trong cùng hệ thống

| Lớp nhìn | Câu hỏi chính | Đơn vị quan sát | Ví dụ |
| --- | --- | --- | --- |
| Domain/Subdomain | Doanh nghiệp cần giải quyết năng lực nào? | Vùng vấn đề nghiệp vụ | Đặt hàng, Thanh toán, Giao vận |
| Bounded Context | Mô hình và ngôn ngữ nào đúng trong phạm vi này? | Ngữ cảnh giới hạn | Ordering, Payments, Fulfillment |
| Context Map | Các ngữ cảnh quan hệ và phụ thuộc nhau thế nào? | Cạnh quan hệ, upstream/downstream, pattern | Ordering → Payments qua hợp đồng thanh toán |
| Team Ownership | Ai quyết định, xây dựng và vận hành? | Nhóm chịu trách nhiệm | Team Commerce owns Ordering |
| Service Architecture | Thành phần phần mềm nào hiện thực hóa năng lực? | API, application, service, broker | order-service, payment-service |
| Deployment | Các thành phần đang chạy ở đâu, bao nhiêu bản? | Pod, VM, container, process | 3 replica order-service |

Không thể kết luận rằng hai service cần gộp lại chỉ vì chúng cùng gọi một database cũ; cũng không thể kết luận hai context giống nhau chỉ vì dùng chung từ “customer”. Quan hệ giữa các lớp là đầu vào để đánh giá quyết định kiến trúc, không phải quy tắc ánh xạ một-một.

Trong một dự án chuyển đổi, **Context Map mục tiêu** có thể khác **bản đồ hệ thống đang chạy**. Cần ghi rõ đâu là hiện trạng, đâu là đích dự kiến, phần nào đã được di chuyển và phần nào còn phụ thuộc legacy.

## 4. Ví dụ xuyên suốt: hệ thống bán hàng

Giả sử một doanh nghiệp vận hành cửa hàng trực tuyến. Khách chọn sản phẩm, xem giá, đặt đơn, giữ hàng, thanh toán và nhận hàng. Một bản phân rã nghiệp vụ ban đầu có thể gồm:

| Bounded Context | Mô hình và bất biến chính | Nguồn dữ liệu có thẩm quyền trong phạm vi | Nhóm sở hữu ví dụ |
| --- | --- | --- | --- |
| Identity & Customer Profile | Danh tính, hồ sơ, địa chỉ được xác thực | Customer identity/profile | Team Identity |
| Catalog | Sản phẩm, SKU, mô tả, thuộc tính bán hàng | Product catalog | Team Merchandising |
| Pricing | Quy tắc giá, khuyến mãi, điều kiện áp dụng | Price rule, quote | Team Pricing |
| Ordering | Giỏ chuyển thành đơn, giá được chốt, vòng đời đơn | Order, order line, order status | Team Commerce |
| Inventory | Số lượng khả dụng, reservation, giải phóng tồn | Stock balance, reservation | Team Inventory |
| Payments | Khoản thu, xác nhận cổng, hoàn tiền, đối soát | Payment attempt, charge, refund | Team Payments |
| Fulfillment & Shipping | Chuẩn bị kiện, vận đơn, theo dõi giao nhận | Shipment, tracking, delivery status | Team Logistics |
| Notifications | Thông báo, template, kết quả gửi | Notification job, delivery result | Team Engagement |

Tên nhóm và ranh giới trên là **ví dụ thiết kế**, không phải danh sách bắt buộc cho mọi tổ chức. Với hệ thống nhỏ, Catalog và Pricing có thể nằm trong cùng một context; với quy mô lớn, Fulfillment và Carrier Integration có thể có ranh giới riêng.

Điểm quan trọng là mỗi ô phải kèm **ý nghĩa và quyền quyết định**. Việc đặt tên “Payment Service” chưa nói rõ đó là context quản lý tiền thực nhận, một adapter tới cổng thanh toán, hay chỉ là API giao diện.

### Một Context Map minh họa

~~~mermaid
flowchart LR
    ID["Identity & Customer Profile\nTeam Identity"]
    CA["Catalog\nTeam Merchandising"]
    PR["Pricing\nTeam Pricing"]
    OR["Ordering\nTeam Commerce"]
    IN["Inventory\nTeam Inventory"]
    PA["Payments\nTeam Payments"]
    SH["Fulfillment & Shipping\nTeam Logistics"]
    NO["Notifications\nTeam Engagement"]

    OR -->|"đọc danh tính/địa chỉ hợp lệ"| ID
    OR -->|"lấy thông tin sản phẩm"| CA
    OR -->|"xin quote để chốt giá"| PR
    OR -->|"yêu cầu giữ hoặc trả hàng"| IN
    OR -->|"yêu cầu thu/hoàn tiền"| PA
    OR -->|"yêu cầu tạo shipment"| SH
    OR -->|"công bố OrderPlaced/OrderCancelled"| NO
    SH -->|"công bố ShipmentDelivered"| OR
    PA -->|"công bố PaymentSucceeded/RefundSucceeded"| OR
~~~

**Quy ước mũi tên của sơ đồ này:** mũi tên “A → B” có nghĩa **A giao tiếp với hoặc sử dụng năng lực của B**, ngoại trừ cạnh ghi rõ sự kiện do A công bố. Nó **không tự định nghĩa** upstream/downstream theo DDD. Upstream/downstream sẽ được xác định riêng theo chiều ảnh hưởng của **mô hình và hợp đồng** ở từng quan hệ.

Ví dụ, với tích hợp đọc profile, Identity có thể là upstream cung cấp hợp đồng, Ordering là downstream tiếp nhận. Với event OrderPlaced do Ordering công bố, Ordering là upstream của Notifications trong quan hệ tiêu thụ sự kiện đó. Một cặp context có thể có **nhiều tương tác**, và chiều upstream/downstream của các hợp đồng có thể khác nhau; cần mô tả từng cạnh rõ ràng.

## 5. Xác định ranh giới bằng ngôn ngữ và bất biến nghiệp vụ

Để vẽ Context Map đúng, trước tiên phải biết mỗi context sở hữu câu trả lời cho những câu hỏi nào.

### Ví dụ 1: “Giá sản phẩm” không phải một giá trị duy nhất

Catalog nói **giá niêm yết**, Pricing tính **giá sau khuyến mãi** theo thời điểm, còn Ordering lưu **giá đã chốt lúc đặt đơn**. Nếu sau này Pricing điều chỉnh bảng giá, đơn đã được chốt thường không tự thay đổi số tiền phải trả.

Một cách phân công:

- Catalog sở hữu định danh và thuộc tính SKU.
- Pricing sở hữu thuật toán, điều kiện ưu đãi và kết quả báo giá có thời hạn.
- Ordering ghi lại snapshot dòng hàng, giá, thuế/phí theo hợp đồng đã áp dụng khi đặt.
- Payments chỉ thu số tiền được xác nhận hợp lệ cho yêu cầu thanh toán, không tự tính lại chương trình khuyến mãi.

Nếu mọi nhóm cùng ghi vào một bảng price chung, không ai chịu trách nhiệm cuối cùng về lý do đơn nhận giá X thay vì Y.

### Ví dụ 2: “Còn hàng” khác “đã giữ hàng”

Inventory có thể công bố lượng hàng có thể bán, nhưng một request chỉ hỏi còn hàng không đồng nghĩa đã **reserve** thành công. Khi nhiều đơn cạnh tranh số lượng cuối cùng, Inventory phải sở hữu thao tác giữ hàng nguyên tử và cung cấp reservationId/stock status cho Ordering.

Ordering không nên trực tiếp cập nhật balance trong cơ sở dữ liệu Inventory. Ordering nhận kết quả StockReserved hoặc ReservationRejected rồi cập nhật tiến trình đơn thuộc quyền mình.

### Ví dụ 3: “Đã thanh toán” không phải “đã giao”

Payments biết giao dịch đã được cổng thanh toán xác nhận, đang chờ hoặc đã hoàn tiền. Fulfillment biết kiện hàng đã được giao cho hãng vận chuyển hay đã giao thành công. Ordering tổng hợp những dữ kiện đó thành trạng thái đơn cho khách.

Không nên đặt một enum status chung rồi ép mọi context dùng cùng cách hiểu. Có thể dùng **mapping trạng thái** ở ranh giới:

| Từ/Trạng thái ở context nguồn | Context tiếp nhận | Diễn giải bên tiếp nhận |
| --- | --- | --- |
| PaymentSucceeded | Ordering | Đơn đã có thanh toán được xác nhận cho payment attempt phù hợp |
| RefundSucceeded | Ordering | Nghĩa vụ hoàn tiền tương ứng đã được xác nhận |
| ShipmentCreated | Ordering | Đơn đã có vận đơn, chưa được coi là giao thành công |
| ShipmentDelivered | Ordering | Có bằng chứng giao nhận hợp lệ để chuyển trạng thái giao hàng |
| StockReserved | Ordering | Có reservation hợp lệ gắn với đơn và SKU được yêu cầu |

Mô hình riêng biệt giúp từng đội thay đổi quy trình nội bộ mà không bắt mọi context viết lại logic.

## 6. Upstream và Downstream: ai ảnh hưởng mô hình của ai?

Trong **một quan hệ tích hợp cụ thể**, **upstream** là phía cung cấp mô hình/hợp đồng/dữ liệu mà bên khác phụ thuộc; **downstream** là phía tiếp nhận và phải phản ứng khi mô hình/hợp đồng đó thay đổi.

Ví dụ:

~~~text
[Payments: upstream cung cấp PaymentSucceeded]
                    |
                    v
[Ordering: downstream diễn giải sự kiện và cập nhật đơn]
~~~

Khi Payments thay đổi ý nghĩa hoặc schema PaymentSucceeded, Ordering có thể bị ảnh hưởng. Vì thế, quyền phát hành hợp đồng đi kèm trách nhiệm quản lý tương thích và thông báo thay đổi.

Tuy vậy, **upstream không mặc nhiên là đội có quyền ưu tiên cao hơn**; đây là cách mô tả chiều phụ thuộc của mô hình. Một khách hàng API lớn có thể yêu cầu upstream thay đổi; upstream cũng có thể không đủ năng lực đáp ứng. Context Mapping ghi rõ **kiểu quan hệ xã hội và kỹ thuật** để hai phía phối hợp thực tế.

### Một ví dụ hai chiều về nhu cầu nhưng khác hợp đồng

Ordering gọi Payments yêu cầu thu tiền:

~~~text
Ordering -- ChargePayment(command) --> Payments
Payments -- PaymentSucceeded(event) --> Ordering
~~~

Tại hợp đồng ChargePayment, Payments sở hữu khả năng thực hiện thanh toán và quy tắc hợp lệ đầu vào. Tại PaymentSucceeded, Payments sở hữu sự thật đã được xác nhận. Ordering sở hữu quy trình nghiệp vụ “đơn nên làm gì tiếp”. Hai phía cùng phối hợp, nhưng không có nghĩa hai đội cùng sở hữu dữ liệu thanh toán.

### Bộ câu hỏi tối thiểu trên mỗi cạnh

1. Ai cung cấp contract, ai tiêu thụ?
2. Điều gì được chia sẻ: lệnh, truy vấn, sự kiện, file hay dữ liệu tham chiếu?
3. Thuật ngữ và điều kiện hợp lệ được định nghĩa theo mô hình của bên nào?
4. Có sự khác biệt ngôn ngữ cần dịch không?
5. Ai phê duyệt thay đổi tương thích/bất tương thích, công bố phiên bản và thời hạn chuyển đổi?
6. Các giả định về độ trễ, sẵn sàng, retry, idempotency và bảo mật là gì?
7. Nếu upstream lỗi hoặc đổi contract, downstream sẽ hoạt động suy giảm thế nào?

Một cạnh chỉ ghi “REST” hoặc “Kafka” mới mô tả phương tiện vận chuyển, chưa đủ để diễn tả **quan hệ Context Mapping**.

## 7. Các kiểu quan hệ Context Mapping quan trọng

DDD có nhiều pattern quan hệ. Đây là **ngôn ngữ để mô tả thực tế phụ thuộc và mức hợp tác**, không phải bộ nhãn bắt buộc dùng hết trong mọi hệ thống.

### 7.1. Partnership — hai context cùng phối hợp chặt

Hai nhóm có mục tiêu gần nhau, cần chủ động lên kế hoạch và thay đổi đồng bộ ở một số điểm. Không đội nào chỉ đơn giản công bố hợp đồng rồi bỏ mặc đội kia.

Ví dụ, Ordering và Fulfillment cùng triển khai tính năng giao nhiều đợt trong một đơn. Ordering phải thay đổi mô hình split shipment, Fulfillment phải hỗ trợ nhiều vận đơn và đối soát trạng thái. Các nhóm lên kế hoạch chung, có lịch kiểm thử tích hợp và thống nhất cách phát hành.

**Phù hợp khi:** kết quả nghiệp vụ đòi hỏi thay đổi phối hợp thường xuyên, hai phía có năng lực cam kết và tác động qua lại lớn.

**Rủi ro:** quá nhiều quyết định bắt buộc họp chung có thể làm chậm triển khai độc lập. Partnership cần giới hạn rõ phần phối hợp, không biến thành quyền sở hữu mơ hồ.

### 7.2. Customer–Supplier — downstream có tiếng nói trong contract

**Supplier (upstream)** cung cấp năng lực/hợp đồng; **customer (downstream)** nêu nhu cầu và cùng kiểm thử để upstream phục vụ tốt các use case thực tế.

Ví dụ Pricing phục vụ Ordering. Ordering cần quote có mã tham chiếu, hiệu lực và phân rã giá; Pricing thống nhất hợp đồng phục vụ việc chốt đơn. Ordering viết consumer-driven contract test hoặc ví dụ payload; Pricing kiểm tra trước khi triển khai thay đổi.

**Phù hợp khi:** có quan hệ nhà cung cấp–người dùng nội bộ rõ ràng và hai bên có thể thương lượng.

**Rủi ro:** Supplier phục vụ nhiều consumer; không thể ưu tiên mọi yêu cầu riêng nếu làm sai ranh giới hoặc khiến API quá phức tạp.

### 7.3. Conformist — downstream phải theo mô hình upstream

Downstream chấp nhận mô hình của upstream vì không có ảnh hưởng đáng kể để yêu cầu upstream chỉnh sửa, và việc chống lại cấu trúc đó không có lợi ích đủ lớn.

Ví dụ một dịch vụ báo cáo phải tiêu thụ API của một nền tảng SaaS bên ngoài với schema và định nghĩa cố định. Team báo cáo viết bộ chuyển đổi cần thiết nhưng chủ yếu tuân theo contract có sẵn.

**Phù hợp khi:** mô hình upstream có thể chấp nhận được, phạm vi phụ thuộc hẹp và chi phí xây lớp mô hình riêng không đáng.

**Rủi ro:** ngôn ngữ/giả định của vendor dễ tràn sâu vào domain nếu sử dụng trực tiếp trong mọi module.

### 7.4. Anti-Corruption Layer (ACL) — bảo vệ mô hình downstream

**ACL** là lớp chuyển đổi giữa hai ngữ cảnh có mô hình khác biệt, giúp downstream không bị buộc dùng ngôn ngữ hoặc cấu trúc dữ liệu của upstream.

Ví dụ một ERP cũ gọi “OrderStatus=90” là đã hoàn tất quy trình đối soát, còn Ordering mới cần trạng thái riêng ACCEPTED, PAID, FULFILLING, DELIVERED. Tầng adapter giải thích mã 90 theo đúng ngữ nghĩa nguồn và chuyển nó thành **một thông tin phù hợp**, không gán bừa 90 = DELIVERED.

~~~mermaid
flowchart LR
    LEG["Legacy ERP\nmã trạng thái và quy tắc cũ"] --> ACL["Anti-Corruption Layer\nadapter + translator"]
    ACL --> NEW["Ordering Context\nmodel đơn hàng mới"]
~~~

Ví dụ chuyển đổi khái niệm:

~~~java
public interface LegacyOrderGateway {
    LegacyOrderDto findByLegacyId(String legacyId);
}

// Cấu trúc minh họa; các type được định nghĩa bởi ứng dụng.
public final class LegacyOrderTranslator {
    public ExternalOrderSnapshot translate(LegacyOrderDto legacy) {
        // Mapping nghiệp vụ phải được xác nhận với chủ sở hữu ERP.
        // Không chuyển mã trạng thái không rõ nghĩa thành DELIVERED.
        return new ExternalOrderSnapshot(
            legacy.externalId(),
            legacy.totalAmount(),
            translateLegacyStatus(legacy.statusCode())
        );
    }

    private ExternalOrderState translateLegacyStatus(String code) {
        return switch (code) {
            case "10" -> ExternalOrderState.RECEIVED;
            case "20" -> ExternalOrderState.PROCESSING;
            case "90" -> ExternalOrderState.CLOSED_IN_ERP;
            default -> ExternalOrderState.UNKNOWN;
        };
    }
}
~~~

Đây là mã minh họa của lớp translator; không phải quy định rằng ERP thật sử dụng các mã 10/20/90 như trên. Lớp ACL cần tests bằng fixture thực tế do chủ sở hữu upstream xác nhận.

**Phù hợp khi:** hệ thống legacy, vendor, context của tổ chức khác hoặc hai mô hình có ngữ nghĩa khó ghép trực tiếp.

**Rủi ro:** ACL không có owner dễ trở thành một service “mọi thứ đều đi qua” chứa quy tắc nghiệp vụ lẫn lộn. Chỉ đặt chuyển đổi ở ranh giới cần thiết.

### 7.5. Open Host Service (OHS) — giao diện tích hợp công khai, ổn định

Upstream cung cấp bộ giao diện/điểm tích hợp có chủ đích cho nhiều downstream thay vì xây một API tùy biến riêng cho từng bên.

Ví dụ Payments công bố API kiểm tra trạng thái giao dịch, tạo hoàn tiền và nhận sự kiện thanh toán theo hợp đồng rõ ràng cho Ordering, Customer Support và Reconciliation.

**Phù hợp khi:** có nhiều consumer cần khả năng cốt lõi tương tự và nhóm upstream có thể duy trì contract chung.

**Rủi ro:** API chung quá rộng hoặc rò rỉ cấu trúc cơ sở dữ liệu nội bộ khiến việc thay đổi domain bị khóa chặt.

### 7.6. Published Language (PL) — ngôn ngữ trao đổi được công bố

Published Language là schema/định nghĩa dữ liệu trao đổi đã được các bên thống nhất và công bố, thường qua API schema, event schema hoặc tài liệu chuẩn. Ngôn ngữ này **không nhất thiết giống domain model nội bộ** của bất kỳ context nào.

Ví dụ Payments công bố event:

~~~json
{
  "eventId": "evt-pmt-100",
  "eventType": "PaymentSucceeded",
  "eventVersion": 1,
  "orderId": "ORD-1001",
  "paymentId": "PAY-101",
  "capturedAmount": 500000,
  "currency": "VND",
  "occurredAt": "2026-11-11T10:00:00Z"
}
~~~

Ordering dùng bản published contract này để cập nhật quy trình, không phụ thuộc trực tiếp vào bảng provider_attempt nội bộ của Payments. OHS thường kết hợp PL: **OHS** nói về bề mặt tích hợp mà upstream mở; **PL** nói về từ vựng và cấu trúc dữ liệu được dùng trong trao đổi.

**Rủi ro:** schema được công bố nhưng ý nghĩa các field, điều kiện phát event và quy tắc versioning không rõ sẽ gây tích hợp sai dù JSON parse thành công.

### 7.7. Shared Kernel — chia sẻ một phần mô hình nhỏ có chủ sở hữu chung

Hai Bounded Context phối hợp **cùng sở hữu một phần mô hình hoặc code quan trọng, có phạm vi hẹp**, và mọi thay đổi ở phần chung phải được thống nhất.

Ví dụ hai context xử lý tài chính nội bộ có thể chia sẻ một mô hình Money được kiểm soát chặt: amount, currency, rounding policy. Nhưng nếu chia sẻ cả entity Order, Payment, Shipment và toàn bộ validation, hai context sẽ không còn khả năng tiến hóa độc lập.

**Phù hợp khi:** ngôn ngữ chung thật sự ổn định, phạm vi rất nhỏ, hai nhóm có cơ chế governance rõ.

**Rủi ro:** Shared Kernel mở rộng thành “shared domain library” chứa mọi class. Cập nhật nhỏ có thể buộc nhiều team phát hành đồng thời.

### 7.8. Separate Ways — tránh tích hợp khi không cần

Hai context có thể giải quyết vấn đề tương tự bằng mô hình riêng mà **không phụ thuộc trực tiếp**, nếu lợi ích tích hợp thấp hơn chi phí phối hợp.

Ví dụ hai hệ thống phân tích nội bộ cần phân loại khách hàng theo mục tiêu khác nhau; không nhất thiết biến hai mô hình phân loại thành một enum chung nếu không có nhu cầu nghiệp vụ trao đổi.

**Phù hợp khi:** sự trùng lặp có chủ ý, chi phí đồng bộ cao và khác biệt ngôn ngữ là hợp lý.

**Rủi ro:** có thể gây dữ liệu trùng, khó quản trị hoặc trải nghiệm không nhất quán nếu lẽ ra phải có một nguồn sự thật chung.

### So sánh ngắn các pattern

| Pattern | Cách các nhóm tương tác | Tình huống minh họa | Điểm cần kiểm soát |
| --- | --- | --- | --- |
| Partnership | Phối hợp chặt, cùng lịch thay đổi | Ordering + Fulfillment triển khai giao nhiều đợt | Rõ quyền quyết định và lịch phối hợp |
| Customer–Supplier | Consumer thương lượng nhu cầu với provider | Ordering cần quote của Pricing | Contract tests và quy trình ưu tiên |
| Conformist | Consumer chấp nhận mô hình upstream | Ứng dụng đọc API SaaS cứng | Giới hạn mức lan truyền phụ thuộc |
| ACL | Consumer dịch mô hình nguồn sang mô hình riêng | ERP cũ → Ordering mới | Mapping ngữ nghĩa, lỗi không rõ mã |
| OHS | Provider mở giao diện ổn định cho nhiều consumer | Payments public internal API | Không lộ chi tiết implementation |
| Published Language | Dùng schema và thuật ngữ trao đổi đã công bố | PaymentSucceeded v1 | Version, ý nghĩa, consumer compatibility |
| Shared Kernel | Cùng quản một mô hình chung nhỏ | Value object Money chung | Scope nhỏ, ownership chia sẻ minh bạch |
| Separate Ways | Không tích hợp trực tiếp | Hai phân loại phục vụ mục đích khác nhau | Tránh trùng lặp gây lệch nghiệp vụ quan trọng |

**Lưu ý:** Một quan hệ có thể dùng nhiều pattern cùng lúc, ví dụ **Customer–Supplier + OHS + Published Language**. ACL có thể nằm ở phía downstream ngay cả khi upstream đã có API chính thức. Pattern dùng để mô tả lựa chọn kiến trúc và quan hệ tổ chức, không phải “nhãn chấm điểm trưởng thành”.

## 8. Gắn Context Map với nhóm sở hữu

Bản đồ ngữ cảnh chỉ có giá trị vận hành khi người tham gia biết **ai trả lời câu hỏi nghiệp vụ, ai sửa hợp đồng, ai nhận cảnh báo và ai chịu trách nhiệm khi tích hợp lỗi**.

Một bảng ownership thực tế nên chứa:

| Context | Accountable owner (ví dụ) | Quyền quyết định | Contract cung cấp | Phụ thuộc quan trọng |
| --- | --- | --- | --- | --- |
| Ordering | Team Commerce | Vòng đời đơn, quy tắc hủy, trạng thái tổng hợp | Order API; OrderPlaced, OrderCancelled | Pricing, Inventory, Payments, Fulfillment |
| Pricing | Team Pricing | Quote, điều kiện giá, khuyến mãi | Pricing Quote API | Catalog, dữ liệu chiến dịch |
| Inventory | Team Inventory | Reservation, tồn khả dụng, nghiệp vụ hoàn kho | ReserveStock; StockReserved/Rejected | Kho/WMS |
| Payments | Team Payments | Thu/hoàn tiền, đối soát, xử lý webhook | Payment API; PaymentSucceeded/Failed | PSP/bank |
| Fulfillment | Team Logistics | Kiện hàng, vận đơn, trạng thái giao | Shipping API; ShipmentCreated/Delivered | Hãng vận chuyển |

**Accountable owner** là một đầu mối chịu trách nhiệm cuối cùng cho thay đổi và vận hành của context. Các vai trò khác có thể cùng tham gia, nhưng quyền quyết định cần cụ thể:

- **Nghiệp vụ:** Product Owner/domain expert xác nhận ý nghĩa và quy tắc.
- **Kỹ thuật:** Owning team quản implementation, hiệu năng, bảo mật và schema.
- **Vận hành:** On-call/service owner nhận cảnh báo, xử lý sự cố và điều tra nguyên nhân.
- **Tiêu thụ:** Downstream team xác nhận yêu cầu tích hợp, tính tương thích và điều kiện dữ liệu sử dụng.

Đây không nhất thiết là bốn người hoặc bốn nhóm khác nhau. Nhiều tổ chức để một team end-to-end phụ trách phần lớn các vai trò. Quan trọng là **không bỏ trống trách nhiệm**.

### Mối quan hệ Team ↔ Context không luôn 1:1

Có các trường hợp hợp lý:

- **Một team, một context:** dễ tập trung ownership, thường tốt nếu khối lượng phù hợp.
- **Một team, nhiều context nhỏ:** phù hợp hệ thống còn nhỏ; vẫn giữ ranh giới mô hình và contract rõ.
- **Một context, nhiều nhóm thực hiện:** có thể xảy ra khi quy mô lớn; cần một cơ chế ownership/decision rõ, tránh hai nhóm phát triển hai cách hiểu mâu thuẫn.
- **Một nền tảng dùng chung, nhiều team sản phẩm:** platform team sở hữu hạ tầng/runtime; domain team vẫn sở hữu ngữ nghĩa và luật nghiệp vụ của mình.

Không nên đổi tên service theo tên phòng ban một cách máy móc. Cơ cấu tổ chức có thể thay đổi nhanh hơn mô hình domain. Context Map phải được cập nhật khi quyền sở hữu thực sự thay đổi.

## 9. Quy trình dựng Context Map từ nghiệp vụ thật

### Bước 1 — Xác định phạm vi và mục tiêu

Chọn một luồng nghiệp vụ có đầu-cuối rõ, chẳng hạn **khách đặt hàng đến lúc giao thành công**. Ghi mục tiêu hiện tại: tìm ranh giới để tách monolith, cải thiện ownership, giảm phụ thuộc phát hành hay thống nhất contract trước khi mở rộng hệ thống.

Nếu chỉ nghiên cứu luồng đặt hàng, không cần vẽ toàn bộ doanh nghiệp trong một lần. Phạm vi nhỏ giúp xác minh đúng ngôn ngữ.

### Bước 2 — Mời đúng đại diện nghiệp vụ và kỹ thuật

Nên có người hiểu quy tắc đặt hàng, quản lý kho, thanh toán, vận chuyển và hệ thống hiện tại. Mỗi người cung cấp thuật ngữ, trường hợp ngoại lệ và trách nhiệm. Tránh chỉ dựa vào sơ đồ database hoặc chia theo tên bảng.

Một buổi **Event Storming** có thể bắt đầu bằng các sự kiện nghiệp vụ:

~~~text
ProductSelected
    → PriceQuoted
    → OrderPlaced
    → StockReserved
    → PaymentSucceeded
    → ShipmentCreated
    → ShipmentDelivered
~~~

Sau đó đặt các nhánh lỗi: StockReservationRejected, PaymentFailed, RefundRequested, RefundSucceeded, ShipmentCreationFailed. Dòng sự kiện giúp phát hiện **ai biết sự thật nào** và **quyết định nghiệp vụ nào phải xảy ra**.

### Bước 3 — Gom sự kiện và thuật ngữ theo mô hình nhất quán

Hỏi từng thuật ngữ:

- “Order” có cùng ý nghĩa ở bộ phận bán hàng và vận chuyển không?
- “Paid” là tiền được authorized, captured hay settled?
- “Available stock” tính trừ reservation đã hết hạn chưa?
- “Cancel” trước và sau khi tạo vận đơn có cùng quy trình không?

Nơi có ngôn ngữ, bất biến và vòng đời khác nhau là ứng viên cho **ranh giới context**. Không dùng số lượng bảng hoặc file code làm tiêu chí duy nhất.

### Bước 4 — Xác định nguồn sự thật và quyền thay đổi

Với mỗi dữ liệu quan trọng, trả lời:

1. Context nào **tạo** dữ liệu?
2. Context nào được quyền **thay đổi trạng thái**?
3. Context khác đọc bằng API, sự kiện, projection hay bản sao?
4. Nếu dữ liệu bị lệch, **nguồn nào có thẩm quyền phân xử**?
5. Bất biến nào cần giao dịch cục bộ và nhất quán mạnh?

Ví dụ Inventory là nguồn sự thật cho reservation; Ordering có thể lưu reservationId và trạng thái nhận được nhưng không tự quyết định số lượng hàng thực tế đã được giữ.

### Bước 5 — Vẽ đường quan hệ với chiều phụ thuộc

Không chỉ nối các hộp. Mỗi cạnh phải gắn **hợp đồng cụ thể** và ghi rõ:

- Consumer/downstream và provider/upstream theo hợp đồng đó.
- Thuật ngữ nguồn và thuật ngữ đích.
- Pattern hợp tác phù hợp.
- Cách truyền: synchronous API, event, batch/file, adapter.
- Mức độ cần có ngay, độ trễ chấp nhận, retry và xử lý lỗi.
- Contract owner và contact của downstream.

Nếu hai context trao đổi nhiều loại thông tin, tách thành những cạnh có ý nghĩa khác nhau thay vì ép một quan hệ chung khó hiểu.

### Bước 6 — Gắn nhóm chịu trách nhiệm và quy trình thay đổi

Ghi một chủ sở hữu chính cho từng context và mỗi published contract. Ghi nhóm tiêu thụ quan trọng, người tham gia thiết kế và quy trình thông báo khi breaking change. Một API không rõ chủ sở hữu dễ bị thay đổi hoặc bỏ quên trong lúc đội triển khai gấp.

### Bước 7 — Kiểm tra bằng một luồng thành công và một luồng lỗi

Đi lần lượt qua đường đi của đơn ORD-1001:

- Ai chốt giá? Ai giữ hàng? Ai thu tiền?
- Nếu timeout khi Payments thu tiền, ai xác minh kết quả?
- Nếu Shipping không tạo vận đơn, ai quyết định hủy hay đổi nhà vận chuyển?
- Khi RefundSucceeded tới muộn, ai cập nhật Order và ai thông báo khách?

Nếu một quyết định phải do hai nhóm cùng cập nhật trong một transaction database “ngầm”, ranh giới cần được xem lại.

### Bước 8 — Ghi rõ mức chắc chắn và cập nhật liên tục

Đánh dấu các cạnh:

- **As-is:** quan hệ tồn tại trong hệ thống đang chạy.
- **To-be:** quan hệ thiết kế đích đã thống nhất.
- **Under discussion:** chưa rõ dữ liệu, owner hoặc điều kiện hợp đồng.
- **Legacy transition:** một phần tương tác đang được chuyển dần qua ACL hoặc adapter.

Bản đồ là tài liệu tiến hóa theo hệ thống, không phải hiện vật vẽ một lần rồi cất đi. Cập nhật khi quy tắc nghiệp vụ, ownership và hợp đồng thay đổi đáng kể.

## 10. Mẫu ghi một quan hệ Context Map

Ví dụ hợp đồng giữa Ordering và Payments:

~~~yaml
relationship:
  name: Ordering uses Payments
  upstreamContext: Payments
  downstreamContext: Ordering
  businessCapability: charge-and-refund
  relationshipPatterns:
    - Customer-Supplier
    - Open-Host-Service
    - Published-Language
  owner:
    upstreamTeam: Team Payments
    downstreamTeam: Team Commerce
  integration:
    command: ChargePayment
    events:
      - PaymentSucceeded
      - PaymentFailed
      - RefundSucceeded
    transport: asynchronous-messaging
    contractVersion: "1"
    correlationKey: orderId
    idempotencyKey: paymentOperationId
  semantics:
    paymentSucceeded: "Khoản thu tương ứng đã được xác nhận."
    timeout: "Chưa rõ kết quả; phải tra cứu hoặc đối soát."
  failurePolicy:
    retry: bounded-with-backoff
    ambiguousResult: reconciliation-required
  changeManagement:
    ownerApproval: Team Payments
    consumerReview: Team Commerce
    compatibility: backward-compatible-first
~~~

Mẫu YAML là **tài liệu thiết kế minh họa**, không phải một schema chuẩn hoặc file cấu hình phải nạp vào một framework. Cần thay giá trị bằng hợp đồng thật khi áp dụng.

Một mối quan hệ được mô tả tốt trả lời được:

- Ai phát hành PaymentSucceeded và khi nào được phép phát?
- Khoản tiền trong event là số tiền dự kiến, đã authorized, đã captured hay đã settled?
- Event có thể phát lặp hoặc đến muộn không?
- Nếu có ChargePayment cùng paymentOperationId hai lần, kết quả phải là gì?
- Ai nhận cảnh báo nếu PaymentSucceeded đã xảy ra nhưng Order vẫn PENDING quá lâu?
- Điều gì được phép thay đổi trong version 1 mà không phá consumer?

## 11. Ví dụ hợp đồng dữ liệu: cùng ý nghĩa nhưng không dùng chung model nội bộ

Giả sử Payments xử lý một khoản thu cho ORD-1001.

**Bên trong Payments**, domain model có thể gồm:

~~~text
PaymentAttempt
    attemptId
    provider
    providerTransactionId
    orderReference
    amount
    currency
    status
    failureReason
    settlementReference
~~~

**Bên trong Ordering**, mô hình cần thông tin thích hợp cho vòng đời đơn:

~~~text
OrderPaymentSummary
    orderId
    acceptedPaymentId
    confirmedAmount
    currency
    paymentState
    confirmedAt
~~~

Ordering không cần copy toàn bộ PaymentAttempt từ Payments. Hai context chỉ cần thống nhất **Published Language** ở ranh giới, ví dụ:

~~~json
{
  "eventId": "evt-100",
  "eventType": "PaymentSucceeded",
  "eventVersion": 1,
  "occurredAt": "2026-11-11T10:00:00Z",
  "correlationId": "checkout-1001",
  "orderId": "ORD-1001",
  "paymentId": "PAY-101",
  "amount": 500000,
  "currency": "VND"
}
~~~

Event mẫu chỉ ghi các trường cần cho use case. Trong hệ thống thực, cần định nghĩa chính xác **đơn vị tiền, hành vi khi partial payment, refund, phiên bản event và quy tắc bảo vệ dữ liệu nhạy cảm**.

Một consumer có thể có adapter:

~~~java
public final class PaymentEventMapper {
    public OrderPaymentUpdate toOrderUpdate(PaymentSucceededEvent event) {
        return new OrderPaymentUpdate(
            event.orderId(),
            event.paymentId(),
            event.amount(),
            event.currency(),
            PaymentState.CONFIRMED
        );
    }
}
~~~

Các record/interface/class trong ví dụ được giả định là đã định nghĩa trong module tương ứng. Ý chính là **dịch sự kiện giao tiếp sang khái niệm của Ordering**, thay vì phụ thuộc vào entity hoặc database schema nội bộ của Payments.

Khi thanh toán chuyển sang mô hình nhiều lần capture, Ordering cần thay đổi mô hình tiếp nhận một cách có chủ đích. Không thể tự gán “PaymentSucceeded” là “đơn đã được thu đủ tiền” nếu chưa có định nghĩa và điều kiện phát hợp lệ.

## 12. Context Map ảnh hưởng đến cách tích hợp như thế nào?

Mỗi cạnh có thể dẫn đến một lựa chọn kỹ thuật khác nhau.

### 12.1. API đồng bộ khi cần phản hồi ngay

Ordering có thể gọi Pricing để nhận quote trước khi chốt đơn. Kết quả cần đủ mới và có thời hạn hiệu lực rõ. API có timeout, retry phù hợp, và client không nên giữ transaction database mở trong lúc chờ một dịch vụ ngoài quá lâu.

Nếu Pricing không khả dụng, sản phẩm có thể từ chối checkout với thông báo rõ hoặc dùng quote còn hiệu lực theo chính sách đã thống nhất. Không tự lấy một giá trong cache cũ nếu chưa biết giá đó được phép dùng.

### 12.2. Event bất đồng bộ để công bố sự thật

Ordering có thể phát OrderPlaced sau khi ghi đơn; Notifications lắng nghe để gửi xác nhận. Notifications không cần quyền viết trạng thái đơn. Event giúp giảm phụ thuộc thời gian, nhưng đòi hỏi xử lý trùng, độ trễ và khả năng phát lại.

Với thay đổi database rồi phát event, **Transactional Outbox** là một cách tránh tình huống commit thành công nhưng event bị thất lạc. Consumer phải idempotent vì message có thể đến nhiều lần.

### 12.3. Command và Saga cho quy trình nhiều context

Luồng đặt hàng gồm ReserveStock, ChargePayment và CreateShipment đi qua nhiều nguồn dữ liệu. Không có rollback ACID mặc định trên tất cả context. Một Saga hoặc process manager có thể theo dõi tiến trình và thực hiện bù khi cần, ví dụ ReleaseStock hoặc RefundPayment.

**Saga điều phối quy trình**, không làm mất quyền sở hữu quyết định cục bộ: Inventory quyết định có giữ được hàng, Payments xác nhận kết quả tiền, Fulfillment xác nhận vận đơn. Ordering/Saga chọn bước kế tiếp theo chính sách checkout đã được thỏa thuận.

### 12.4. Projection để đọc dữ liệu tổng hợp

Một màn hình “Chi tiết đơn” cần tên sản phẩm, giá, trạng thái thanh toán và tracking. Không nhất thiết mở quyền truy vấn trực tiếp mọi bảng của các context khác. Có thể tổng hợp qua API hoặc lưu projection đọc riêng dựa trên sự kiện.

Projection có thể **chậm hơn nguồn**; UI cần thể hiện trạng thái cập nhật và thời điểm dữ liệu có hiệu lực. Quyền phân xử dữ liệu vẫn thuộc context sở hữu từng sự thật.

## 13. Giao dịch xuyên context và khả năng chịu lỗi

Giả sử Pricing cung cấp quote, Inventory giữ hàng, Payments thu tiền, Fulfillment tạo vận đơn. Context Map ghi rõ các hợp đồng:

~~~mermaid
sequenceDiagram
    autonumber
    actor C as Khách hàng
    participant O as Ordering
    participant P as Pricing
    participant I as Inventory
    participant M as Payments
    participant F as Fulfillment

    C->>O: Đặt hàng
    O->>P: GetPriceQuote
    P-->>O: Quote hợp lệ
    O->>O: Chốt giá và lưu Order
    O->>I: ReserveStock
    I-->>O: StockReserved
    O->>M: ChargePayment
    M-->>O: PaymentSucceeded
    O->>F: CreateShipment
    F-->>O: ShipmentCreated
    O-->>C: Đơn đang được thực hiện
~~~

Sơ đồ thể hiện thứ tự nghiệp vụ, không bắt buộc tất cả mũi tên là HTTP đồng bộ. Tùy kiến trúc, lệnh và sự kiện có thể được chuyển qua broker.

Nếu **Inventory từ chối**, Ordering không tiếp tục thu tiền. Nếu **Payments từ chối sau khi giữ hàng**, Ordering/Saga yêu cầu Inventory giải phóng reservation. Nếu **Payments xác nhận đã thu tiền nhưng Fulfillment không thể tạo vận đơn**, chính sách nghiệp vụ có thể thử nhà vận chuyển khác hoặc hủy đơn và yêu cầu hoàn tiền. Mọi bước bù phải có trạng thái theo dõi và xác nhận; timeout không được đồng nhất với “thất bại” nếu bên kia đã thực hiện thành công.

Context Map giúp xác định người trả lời từng câu hỏi:

| Sự cố | Chủ sở hữu sự thật / hành động | Bên cần phản ứng |
| --- | --- | --- |
| Giá quote không hợp lệ | Pricing xác nhận quy tắc/quote | Ordering từ chối hoặc xin quote mới |
| Không đủ tồn kho | Inventory quyết định reservation | Ordering cập nhật đơn |
| Giao dịch tài chính chưa rõ kết quả | Payments đối soát cổng thanh toán | Ordering giữ trạng thái chờ |
| Hoàn tiền quá hạn | Payments xử lý và xác nhận refund | Ordering/Saga tiếp tục theo dõi bù |
| Không tạo được vận đơn | Fulfillment xác nhận lý do | Ordering quyết định tiếp tục/hủy theo chính sách |
| Khách không nhận thông báo | Notifications kiểm tra gửi lại | Ordering không tự hoàn tác nghiệp vụ |

Việc mỗi team sở hữu một sự thật giúp tránh tình trạng nhiều hệ thống đưa ra kết luận cuối cùng trái nhau.

## 14. Contract, versioning và quản lý thay đổi giữa nhóm

Một Bounded Context tiến hóa độc lập **trong phạm vi hợp đồng đã cam kết**. Điều đó không đồng nghĩa được quyền thay đổi schema tùy ý. Khi downstream dựa vào upstream, hai nhóm phải có cơ chế bảo đảm tương thích.

### 14.1. Contract phải mô tả ngữ nghĩa, không chỉ cấu trúc

Với PaymentSucceeded, tài liệu nên giải thích:

- Điều kiện nào khiến Payments phát sự kiện?
- Một order có thể có bao nhiêu successful payment?
- Đơn vị tiền và quy tắc làm tròn?
- Có thể có partial payment, chargeback, refund hay không?
- Event có thể bị gửi trùng, trễ hoặc đảo thứ tự?
- Những field nào bắt buộc và có thể null?
- Mất callback thì nguồn có cơ chế truy vấn/đối soát nào?
- Chính sách dữ liệu nhạy cảm trong payload và log?

Hai event JSON có cùng field name nhưng khác ý nghĩa vẫn là một **breaking semantic change** đối với consumer.

### 14.2. Ví dụ thay đổi tương thích

Nếu Payments bổ sung một trường mới tùy chọn, consumer cũ bỏ qua trường không biết có thể tiếp tục hoạt động. Nhưng nếu đổi capturedAmount từ đơn vị VND sang hàng nghìn VND mà không đổi tên/schema/version, downstream có thể xử lý sai nghiêm trọng.

Các nguyên tắc thường dùng:

1. Ưu tiên thêm trường tùy chọn với default/semantics rõ khi phù hợp.
2. Không xóa/đổi nghĩa field đã có consumer đang dùng mà chưa có kế hoạch chuyển đổi.
3. Khi cần breaking change, công bố version mới, giai đoạn chạy song song và thời hạn ngừng version cũ.
4. Dùng schema validation và consumer-driven contract tests để thấy rủi ro sớm.
5. Theo dõi consumer thực tế trước khi loại bỏ hợp đồng cũ; tài liệu một mình không chứng minh còn/không còn phụ thuộc.

### 14.3. Quyền quyết định thay đổi

Bên upstream chịu trách nhiệm chất lượng và tính nhất quán của contract mình công bố. Bên downstream chịu trách nhiệm kiểm chứng giả định đang dùng. Khi làm Customer–Supplier hoặc Partnership, cần cam kết thực tế về review và phối hợp.

Một **Contract Ownership Record** có thể gồm:

~~~text
Contract: PaymentSucceeded v1
Producer: Payments / Team Payments
Consumers: Ordering, Reconciliation
Semantics owner: Payments product/domain owner
Schema owner: Payments engineering
Compatibility rule: no breaking changes within v1
Change review: consumer teams notified before release
Support: on-call Team Payments
Deprecation: announce, measure use, migrate, remove by agreed policy
~~~

Không dùng ownership để chặn mọi thay đổi; dùng để giảm bất ngờ cho các nhóm phụ thuộc và kiểm soát tiến trình đổi mới.

## 15. Khi cần đổi ranh giới context hoặc nhóm sở hữu

Context Map thường lộ ra những chỗ phân rã chưa phù hợp.

### Tình huống A — Một nghiệp vụ bị chia đôi bất thường

Giả sử quy tắc tính giá sau chiết khấu nằm một nửa trong Ordering và một nửa trong Payments. Mỗi lần thay đổi khuyến mãi phải sửa hai codebase, đồng thời dễ xuất hiện tổng tiền khác nhau. Cần đánh giá lại nguồn quyết định giá, có thể gom logic vào Pricing, để Ordering chốt quote và Payments dùng số tiền yêu cầu đã được xác nhận.

### Tình huống B — Một context quá rộng

Giả sử “Commerce Context” chứa catalog, pricing, checkout, payment và vận chuyển, với nhiều ngôn ngữ và cadence thay đổi không tương thích. Có thể chia theo invariant và luồng giá trị, nhưng phải xác định đường tích hợp mới trước khi tách runtime.

### Tình huống C — Một nguồn dữ liệu có hai chủ sửa

Cả Ordering và Inventory cùng update quantity_available. Lúc này khó biết ai đúng khi hai câu lệnh cạnh tranh. Cần chọn nguồn quyền quyết định tồn kho và chuyển đội còn lại sang API/command/event thích hợp.

### Tình huống D — Ranh giới tốt nhưng team quá tải

Một team sở hữu ba context riêng biệt vì tổ chức còn nhỏ; khi hệ thống tăng trưởng, nhóm không đáp ứng nổi SLO và thời gian thay đổi. Có thể chia team theo ownership mà vẫn giữ context boundary, không cần làm lại toàn bộ mô hình domain.

### Tình huống E — Tên nhóm thay đổi liên tục

Nếu Context Map dùng tên phòng ban làm tên domain, mỗi lần tái cơ cấu tổ chức sẽ khiến bản đồ khó hiểu. Nên giữ **tên nghiệp vụ ổn định**, đồng thời cập nhật trường owning team và contact.

### Dấu hiệu ranh giới cần xem xét lại

- Hai đội liên tục cần deploy cùng thời điểm cho thay đổi nhỏ.
- Một nghiệp vụ cần transaction cập nhật dữ liệu riêng của nhiều context.
- Một bảng có nhiều owner đều có quyền sửa.
- Event chứa nguyên entity nội bộ và consumer phụ thuộc mọi field.
- Cùng một thuật ngữ có hai nghĩa nhưng code dùng chung một class.
- Một lớp “shared” phình to, chứa logic domain của nhiều nhóm.
- Thay đổi upstream gây lỗi âm thầm ở downstream mà không có contract test.
- Không biết đội nào nhận xử lý một sự kiện bị kẹt hoặc dữ liệu bị lệch.

Các dấu hiệu này là tín hiệu **điều tra**, không tự động chứng minh phải tạo thêm Microservice. Có khi giải pháp phù hợp là một module tách biệt, ACL, hợp đồng mới hoặc tái phân công owner.

## 16. Ghi Context Map dưới dạng một bảng vận hành

Một bản đồ cần dễ kiểm tra lại. Có thể dùng mẫu như sau:

| Trường | Câu hỏi cần trả lời |
| --- | --- |
| Context | Mô hình và năng lực nghiệp vụ nào nằm trong ranh giới? |
| Owning team | Ai chịu trách nhiệm phát triển, hợp đồng và vận hành? |
| Upstream/downstream | Với hợp đồng này, ai phát hành mô hình, ai phụ thuộc? |
| Relationship pattern | Partnership, Customer–Supplier, ACL, Conformist, v.v.? |
| Contract | API/event/schema nào truyền thông tin? |
| Ownership of facts | Dữ liệu hoặc quyết định nào thuộc nguồn nào? |
| Translation | Có thuật ngữ nào khác nghĩa cần chuyển đổi? |
| Consistency | Cần đồng bộ tức thời hay chấp nhận eventual consistency? |
| Failure handling | Timeout, retry, duplicate, compensation, manual review? |
| Change policy | Cách version, kiểm thử tương thích, thông báo và ngừng hỗ trợ? |

Ví dụ rút gọn:

| Downstream | Upstream | Quan hệ | Contract | Ownership/rủi ro |
| --- | --- | --- | --- | --- |
| Ordering | Pricing | Customer–Supplier | GetPriceQuote | Pricing sở hữu quote; Ordering chốt snapshot |
| Ordering | Inventory | Customer–Supplier | ReserveStock, StockReserved | Inventory sở hữu reservation; retry idempotent |
| Ordering | Payments | Customer–Supplier + PL | ChargePayment, PaymentSucceeded | Payments sở hữu khoản thu; timeout cần đối soát |
| Ordering | Legacy ERP | ACL + Conformist | Legacy Order API | Dịch trạng thái, không để mã legacy tràn vào domain |
| Notifications | Ordering | OHS/PL ở phía Ordering | OrderPlaced | Notifications tiêu thụ, không sửa đơn |
| Support Read Model | Shipping | PL | ShipmentDelivered | Shipping là nguồn sự thật giao nhận |

Không nhất thiết mỗi cạnh chỉ có một pattern. Điều cần tránh là ghi pattern nhưng không mô tả **hậu quả kỹ thuật và cách phối hợp** của nó.

## 17. Workshop thực hành: tự lập bản đồ ngữ cảnh

Giả sử doanh nghiệp muốn triển khai tính năng **giao một đơn hàng thành nhiều đợt** vì một số sản phẩm có thể ở nhiều kho. Hãy làm theo các bước:

1. Liệt kê các thuật ngữ cần làm rõ: Order, OrderLine, Reservation, Package, Shipment, DeliveryAttempt, PaidAmount, Refund.
2. Chọn context sở hữu từng khái niệm. OrderLine thuộc Ordering; Reservation thuộc Inventory; Shipment thuộc Fulfillment.
3. Vẽ các sự kiện chính: OrderPlaced, StockPartiallyReserved, ShipmentCreated, ShipmentDelivered, ShipmentFailed.
4. Xác định liệu một Order có thể có nhiều Shipment, và trạng thái tổng hợp của Ordering khi mới giao một phần.
5. Ghi đội có quyền quyết định “đã giao đủ đơn” theo quy tắc nghiệp vụ, không nhầm với một ShipmentDelivered.
6. Xác định quan hệ Ordering–Fulfillment: tính năng mới cần Partnership hay Customer–Supplier có đủ?
7. Thiết kế hợp đồng cho số lượng giao theo dòng hàng; tránh copy nguyên entity Shipment nội bộ.
8. Ghi trường hợp lỗi: một shipment hỏng, hoàn tiền một phần, khách hủy phần chưa giao.
9. Kiểm tra tiêu chí tương thích với client cũ vốn chỉ biết một trackingCode.
10. Lập một Context Map hiện trạng và một bản đồ mục tiêu, ghi người chịu trách nhiệm cho từng thay đổi.

### Câu hỏi tự kiểm tra

**Câu 1.** Một đội quản lý hai Bounded Context khác nhau có sai nguyên tắc DDD không?

Không nhất thiết. Điều cần giữ là ranh giới ngôn ngữ, mô hình và ownership của từng context. Số team không bắt buộc bằng số context.

**Câu 2.** Ordering gọi API của Payments thì bên nào upstream?

Trong quan hệ Ordering tiêu thụ khả năng thanh toán do Payments công bố, Payments là upstream của hợp đồng đó, Ordering là downstream. Cần chỉ rõ hợp đồng cụ thể thay vì suy ra chỉ từ hướng mũi tên network.

**Câu 3.** Hai context đều có class Customer thì nên dùng một thư viện domain chung?

Chưa chắc. Trong Identity, Customer có thể là danh tính và quyền truy cập; trong Billing, Customer có thể là chủ thể thanh toán và thông tin hóa đơn. Nếu nghĩa khác nhau, hai model độc lập và mapping ở ranh giới thường đúng hơn việc ép chung class.

**Câu 4.** Có Published Language rồi có cần ACL nữa không?

Có thể có. Published Language định nghĩa schema trao đổi; ACL bảo vệ model của consumer khi ngôn ngữ nguồn khác biệt. Một event chuẩn không làm biến mất nhu cầu dịch ngữ nghĩa.

**Câu 5.** Một context có nhiều Microservices có mất ý nghĩa của Bounded Context không?

Không tự động. Bounded Context là phạm vi mô hình/ngôn ngữ. Có thể có nhiều thành phần triển khai hỗ trợ cùng một context, nhưng cần cẩn trọng tránh tách cơ sở dữ liệu và hành vi theo cách khiến bất biến nghiệp vụ bị phân mảnh.

**Câu 6.** Nếu đổi schema PaymentSucceeded nhưng consumer không báo lỗi parse thì có nghĩa thay đổi tương thích?

Không. Ý nghĩa nghiệp vụ có thể đã đổi trong khi cú pháp vẫn hợp lệ. Contract tests và tài liệu phải kiểm tra cả semantics.

**Câu 7.** Vì sao vẽ Context Map trước khi quyết định tách container?

Vì ranh giới nghiệp vụ, quyền sở hữu dữ liệu và quan hệ thay đổi quyết định cấu trúc ứng dụng và API. Tách process trước khi hiểu ranh giới thường biến lời gọi nội bộ thành mạng, nhưng vẫn giữ phụ thuộc chặt.

## 18. Một cách đọc Context Map khi review thiết kế

Khi review một bản vẽ, hãy đi theo thứ tự:

1. **Ý nghĩa:** mỗi ngữ cảnh có ngôn ngữ và bất biến đủ rõ chưa?
2. **Nguồn sự thật:** từng dữ kiện do đúng một context chịu trách nhiệm quyết định chưa?
3. **Quan hệ:** upstream/downstream và kiểu hợp tác có ghi theo từng contract chưa?
4. **Ranh giới:** consumer có phụ thuộc domain model hoặc database riêng của provider không?
5. **Độ tin cậy:** timeout, retry, duplicate, eventual consistency và compensation đã có người sở hữu chưa?
6. **Con người:** chủ sở hữu, người review contract và người trực sự cố có xác định chưa?
7. **Thay đổi:** khi schema/semantics đổi, các consumer hiện hữu có đường di chuyển an toàn chưa?

Một Context Map hữu ích khiến những câu hỏi này trả lời được bằng **đường nối, ghi chú và hợp đồng cụ thể**, chứ không chỉ bằng lời nói “các team sẽ phối hợp”.

## 19. Kết luận

**Bounded Context** giới hạn nơi một mô hình nghiệp vụ có ý nghĩa nhất quán. **Context Map** cho thấy các ngữ cảnh cần trao đổi gì, ai là upstream/downstream và quan hệ của họ nên được tổ chức ra sao. **Nhóm sở hữu** biến ranh giới khái niệm đó thành quyền quyết định, cam kết hợp đồng và trách nhiệm vận hành thực tế.

Trong kiến trúc Microservices, một sơ đồ có các hộp Order, Payment, Inventory và Shipping chỉ là điểm bắt đầu. Thiết kế trở nên đáng tin cậy khi mỗi đội biết chính xác **mình sở hữu sự thật nào, mình cung cấp hợp đồng gì, mình phụ thuộc những ai và mình phải xử lý thế nào khi ngữ cảnh bên cạnh thay đổi hoặc gặp lỗi**.
