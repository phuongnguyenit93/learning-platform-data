# Lựa chọn ranh giới microservice từ nhu cầu độc lập thực tế

Chia một hệ thống thành microservice là quyết định về quyền sở hữu, thay đổi và vận hành. Ranh giới tốt giúp một nhóm có thể phát triển, triển khai và vận hành một năng lực nghiệp vụ mà không phải phối hợp chặt chẽ với mọi nhóm khác. Ranh giới kém tạo ra nhiều service nhỏ nhưng vẫn phải cùng sửa, cùng phát hành và gọi nhau qua mạng cho những thao tác vốn cần nhất quán tức thời.

Domain-Driven Design (DDD) cung cấp ngôn ngữ để khám phá ranh giới nghiệp vụ qua subdomain, Bounded Context, Aggregate và Context Map. Tuy nhiên, Bounded Context không tự động đồng nghĩa với một microservice. Ranh giới mô hình là cơ sở quan trọng để thảo luận; ranh giới triển khai còn phải đáp ứng nhu cầu độc lập thực tế như nhịp thay đổi, quyền sở hữu dữ liệu, tải, độ sẵn sàng, bảo mật, tổ chức nhóm và chi phí vận hành.

Bài học này trình bày cách chọn ranh giới service từ các năng lực nghiệp vụ và bằng chứng về nhu cầu độc lập. Bạn sẽ học cách đánh giá một ứng viên service, nhận biết dấu hiệu của distributed monolith, so sánh microservice với modular monolith và lập lộ trình tách service an toàn.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt ranh giới miền, Bounded Context, module và deployable service.
- Bắt đầu tìm service boundary từ business capability và subdomain.
- Dùng Aggregate và invariant để xác định dữ liệu cần nhất quán cục bộ.
- Đánh giá nhu cầu độc lập về thay đổi, triển khai, scale, bảo mật và failure isolation.
- Nhận biết coupling qua database, API, event và quy trình release.
- Phân tích chi phí giao tiếp mạng, eventual consistency và vận hành.
- So sánh các phương án gộp, tách hoặc giữ trong modular monolith.
- Dùng change scenario và decision matrix để kiểm chứng boundary hypothesis.
- Tách một phần hệ thống hiện hữu theo lộ trình có thể quan sát và rollback.

## 1. Ranh giới microservice thực sự quyết định điều gì?

Microservice là một đơn vị phần mềm có thể được phát triển, triển khai và vận hành tương đối độc lập, thường sở hữu một năng lực nghiệp vụ cùng dữ liệu và hành vi liên quan. “Tương đối độc lập” có nghĩa service có hợp đồng rõ với phần còn lại và có thể thay đổi nội bộ mà không yêu cầu các service khác cùng triển khai cho mọi thay đổi thông thường.

Một ranh giới service quyết định:

- Năng lực nghiệp vụ nào được service chịu trách nhiệm.
- Dữ liệu nào service có quyền đọc và ghi như nguồn sự thật.
- Quy tắc nào service phải bảo vệ.
- Những API hoặc event nào được công bố cho bên ngoài.
- Nhóm nào chịu trách nhiệm phát triển và vận hành.
- Service có thể được triển khai, scale và phục hồi độc lập đến mức nào.

Một service không chỉ là một tiến trình hoặc một container. Nếu hai service luôn phải được phát hành cùng lúc, truy cập cùng bảng dữ liệu và gọi nhau liên tục để hoàn thành một thao tác đơn giản, việc tách tiến trình có thể chỉ tạo thêm chi phí mạng và vận hành.

### Phân biệt các loại ranh giới

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Subdomain | Năng lực nghiệp vụ nào tồn tại trong bài toán? | Sales, Inventory, Billing |
| Bounded Context | Một mô hình và ngôn ngữ nhất quán có hiệu lực ở đâu? | Sales Context, Inventory Context |
| Module | Code và dependency được tổ chức thế nào trong một codebase? | sales, inventory, billing packages |
| Microservice | Đơn vị nào có thể được phát triển, triển khai và vận hành độc lập? | sales-service, inventory-service |

Các ranh giới này có liên quan nhưng không bắt buộc trùng nhau. Một Bounded Context có thể được triển khai trong một module của modular monolith. Một deployable service có thể chứa nhiều module hoặc nhiều phần mô hình nếu chúng chưa cần phát hành độc lập. Một Bounded Context lớn đôi khi được chia thành nhiều service khi xuất hiện các nhu cầu độc lập có căn cứ, nhưng việc chia đó cần giữ được quyền sở hữu và ngôn ngữ của context.

### Bounded Context là đầu vào, không phải công thức ánh xạ

DDD giúp tìm nơi một mô hình có ý nghĩa và nơi các thuật ngữ đổi nghĩa. Đó là điểm bắt đầu mạnh để tìm service boundary. Nhưng một context có thể chưa cần tách vật lý nếu cùng nhóm sở hữu, cùng nhịp phát hành, cùng yêu cầu scale và có thể dùng chung transaction cục bộ.

Ngược lại, một context có thể cần nhiều đơn vị triển khai khi có các thành phần thật sự khác nhau về tải, độ sẵn sàng, bảo mật hoặc quyền sở hữu. Đừng tách chỉ vì có thể; hãy tách khi lợi ích độc lập đủ lớn để bù chi phí phân tán.

## 2. Bắt đầu từ business capability và subdomain

Một cách tìm ứng viên service là lập bản đồ năng lực nghiệp vụ thay vì bắt đầu từ bảng database hoặc danh sách Entity.

Ví dụ hệ thống thương mại điện tử có các năng lực:

- Catalog quản lý thông tin sản phẩm và cách sản phẩm được trình bày.
- Sales tiếp nhận yêu cầu mua và quản lý vòng đời Order.
- Inventory quản lý số lượng có thể phân bổ và Reservation.
- Billing/Payments quản lý authorization, capture, refund và đối soát.
- Delivery quản lý shipment, hãng vận chuyển và trạng thái giao hàng.
- Customer Management quản lý hồ sơ và quan hệ khách hàng.

Mỗi năng lực có mục tiêu, quy tắc, dữ liệu và nhịp thay đổi khác nhau. Hãy tìm hiểu:

- Kết quả nghiệp vụ mà năng lực tạo ra là gì?
- Ai chịu trách nhiệm về kết quả?
- Những quyết định nào chỉ năng lực này có quyền đưa ra?
- Những dữ liệu nào là nguồn sự thật của nó?
- Nó phối hợp với năng lực nào và qua hợp đồng gì?
- Khi quy tắc thay đổi, nhóm nào cần tham gia?

### Dùng Event Storming và workflow để nhìn thấy ranh giới

Một workflow như đặt hàng có thể được mô tả qua các sự kiện:

~~~mermaid
flowchart LR
    A["OrderPlaced"] --> B["InventoryReserved"]
    B --> C["PaymentAuthorized"]
    C --> D["OrderConfirmed"]
    D --> E["ShipmentCreated"]
    E --> F["OrderDelivered"]
    B -->|Unavailable| X["OrderRejected"]
    C -->|Declined| Y["ReservationReleased"]
~~~

Sơ đồ sự kiện giúp thấy những năng lực tham gia và điểm chuyển giao. Nó chưa chứng minh mỗi event phải tương ứng một service. Hãy xác định context nào sở hữu sự kiện, quyết định và dữ liệu tạo ra nó.

### Phân biệt năng lực với bước kỹ thuật

“Gửi email”, “ghi log”, “chuyển JSON” hoặc “gọi database” thường là hoạt động kỹ thuật, không nhất thiết là business capability. Một Notification Service có thể là service độc lập nếu thông báo là năng lực sản phẩm có chính sách, kênh, lịch gửi, retry và quyền sở hữu riêng. Nếu chỉ là một adapter nhỏ phục vụ một ứng dụng, module nội bộ có thể đủ.

## 3. Quyền sở hữu dữ liệu và quy tắc là nền tảng của boundary

Một service nên sở hữu dữ liệu mà nó chịu trách nhiệm duy trì và các quy tắc làm cho dữ liệu đó hợp lệ. Bên ngoài tương tác qua API, command hoặc event đã công bố.

Ví dụ:

| Dữ liệu/quyết định | Chủ sở hữu gợi ý | Bên khác nên nhận |
| --- | --- | --- |
| Giá bán được chấp nhận trong Order | Sales | Order line snapshot, tổng tiền |
| Trạng thái và dòng hàng của Order | Sales | Order view hoặc Order events |
| Số lượng có thể phân bổ | Inventory | Kết quả availability/reservation |
| Payment authorization/capture | Payments | Payment status và reference |
| Shipment và trạng thái giao | Delivery | Shipment reference và delivery events |
| Mô tả sản phẩm hiện hành | Catalog | Product view hoặc catalog contract |

### Không chia sẻ database như một hợp đồng

Nếu Sales và Inventory cùng cập nhật bảng Stock, không bên nào thực sự sở hữu quy tắc tồn kho. Một nhóm có thể đổi schema và làm hỏng service kia mà không có thay đổi API nào để phát hiện.

Dấu hiệu boundary chưa rõ:

- Service A ghi trực tiếp bảng do Service B quản lý.
- Nhiều service cùng cập nhật một record nghiệp vụ.
- Consumer cần join bảng nội bộ của nhiều service để trả một query.
- Migration database buộc nhiều nhóm triển khai đồng thời.
- Không biết service nào có quyền quyết định trạng thái cuối cùng.

Một service có thể cung cấp read API hoặc phát projection/event để bên khác dùng. Bên nhận có thể lưu bản sao phục vụ đọc, nhưng không được coi bản sao đó là nguồn sự thật để ghi ngược vào owner.

### Data duplication có chủ đích

Một Order có thể lưu snapshot tên sản phẩm, đơn giá, địa chỉ giao hàng và tên người nhận tại thời điểm đặt. Điều đó không biến Sales thành chủ sở hữu Catalog hoặc Customer. Snapshot giữ lại ngữ cảnh của giao dịch đã xảy ra và tránh làm lịch sử Order thay đổi khi dữ liệu nguồn được chỉnh sửa.

Sao chép dữ liệu để đọc và giải thích giao dịch có thể hợp lý. Sao chép rồi cho nhiều service cùng sửa một sự thật là vấn đề ownership.

## 4. Dùng Aggregate và invariant để xác định consistency boundary

Aggregate giúp nhận diện những thay đổi phải nhất quán trong một lần xử lý nghiệp vụ. Đây là bằng chứng quan trọng khi quyết định có nên tách dữ liệu ra hai service hay không.

Ví dụ, Order và OrderLine thường cần được kiểm tra cùng nhau:

- Order phải có ít nhất một dòng hợp lệ trước khi xác nhận.
- Tổng tiền phải khớp với các dòng hàng và chính sách giá đã chấp nhận.
- Không được sửa dòng hàng theo cách làm sai trạng thái đã xác nhận.

Nếu Order và OrderLine bị tách thành hai service nhưng mỗi lần xác nhận phải gọi qua mạng để kiểm tra và cập nhật cả hai, ranh giới có thể đã chia cắt một invariant cục bộ. Hãy cân nhắc giữ chúng trong cùng Aggregate và cùng consistency boundary.

Ngược lại, Inventory có quy tắc phân bổ riêng. Sales không thể tự đảm bảo tồn kho chỉ bằng cách đọc số lượng khả dụng trước đó. Inventory cần nhận command ReserveStock và đưa ra quyết định trong transaction của nó.

### Hỏi ba câu về mỗi quy tắc

1. Quy tắc phải đúng ngay tại thời điểm nào?
2. Context hoặc Aggregate nào có đủ dữ liệu và quyền để bảo vệ nó?
3. Nếu dữ liệu liên quan nằm ở hai service, có thể chấp nhận trạng thái trung gian và quy trình bù trừ không?

Nếu câu trả lời là “phải nguyên tử ngay” và dữ liệu thường xuyên thay đổi cùng nhau, đó là dấu hiệu nên đặt chúng trong cùng boundary hoặc thiết kế lại mô hình. Nếu có thể dùng reservation, authorization, deadline và Saga, việc tách context có thể phù hợp hơn.

### Không dùng distributed transaction để che boundary kém

Một transaction phân tán có thể làm nhiều resource commit cùng nhau trong một số kiến trúc, nhưng nó kéo theo phụ thuộc về coordinator, locking, availability và failure recovery. Đừng tách các dữ liệu luôn phải thay đổi nguyên tử rồi trông chờ distributed transaction giải quyết mọi vấn đề. Trước hết hãy xem xét liệu chúng có cùng một năng lực và cùng chủ sở hữu nghiệp vụ hay không.

## 5. Đánh giá nhu cầu độc lập thực tế

Một ứng viên service nên được đánh giá qua những nhu cầu cụ thể, không chỉ qua mong muốn “chia nhỏ để dễ scale”.

### Độc lập về thay đổi và phát hành

Hãy xem các thay đổi gần đây hoặc kịch bản sắp tới:

- Quy tắc giá thay đổi thường xuyên nhưng vòng đời Order ổn định?
- Chính sách vận chuyển thay đổi mà không cần sửa Sales?
- Một nhóm cần triển khai hàng ngày trong khi nhóm khác phát hành theo chu kỳ?
- Thay đổi nội bộ có thể được che sau API/event contract ổn định?

Nếu hai phần luôn thay đổi cùng nhau và cần phát hành cùng nhau, tách chúng có thể không tạo autonomy.

### Độc lập về scale

Có workload khác biệt đáng kể không?

- Catalog search có tải đọc lớn và cần search index.
- Checkout có tải theo đợt và cần latency thấp.
- Billing chạy tác vụ đối soát theo batch.
- Image processing cần CPU hoặc storage riêng.

Khác biệt tải có thể là lý do tách, nhưng cần xem liệu phần đó có thể scale bằng module, worker pool hoặc thành phần hạ tầng riêng mà không cần tạo một microservice nghiệp vụ mới.

### Độc lập về availability và failure isolation

Nếu một năng lực tạm thời không khả dụng, phần còn lại có thể tiếp tục ở trạng thái hợp lệ nào?

- Catalog search lỗi có thể vẫn cho phép xem Order đã đặt.
- Notification lỗi không nên làm rollback đơn hàng.
- Inventory chưa phản hồi có thể khiến Order ở trạng thái PENDING.
- Payment provider timeout có thể cần truy vấn trạng thái trước khi retry.

Nếu service A gọi service B đồng bộ trong mọi request và không có fallback hoặc trạng thái chờ, failure của B có thể lan sang A. Tách tiến trình nhưng không thiết kế resilience không tự tạo fault isolation.

### Độc lập về bảo mật và tuân thủ

Dữ liệu thanh toán, thông tin định danh hoặc dữ liệu thuộc phạm vi kiểm soát khác có thể cần boundary riêng về quyền truy cập, secret, audit và vận hành. Hãy xác định yêu cầu thật từ chính sách bảo mật và chủ sở hữu dữ liệu; đừng dùng “compliance” như lý do chung chung để chia mọi thứ.

### Độc lập về quyền sở hữu nhóm

Một nhóm có thể chịu trách nhiệm trọn vòng đời của một năng lực: backlog, thiết kế, code, triển khai, cảnh báo và hỗ trợ production. Ranh giới tốt giảm số lần cần phối hợp để thay đổi bình thường.

Nếu service không có owner rõ ràng hoặc mọi thay đổi đều cần một nhóm nền tảng can thiệp, service đó chưa đạt autonomy như mục tiêu.

## 6. Kiểm tra coupling bằng change scenario

Thay vì tranh luận trừu tượng, hãy đưa ra các thay đổi có khả năng xảy ra và theo dõi số thành phần phải sửa.

Ví dụ:

| Change scenario | Nếu boundary tốt | Dấu hiệu boundary yếu |
| --- | --- | --- |
| Thêm phương thức thanh toán | Payments đổi adapter/contract nội bộ | Sales, Inventory và Delivery cùng sửa |
| Thay cách tính giá | Pricing/Sales thay đổi theo ownership | Nhiều service đọc chung bảng PriceRule |
| Thay hãng vận chuyển | Delivery đổi tích hợp | Checkout phải hiểu API riêng của từng hãng |
| Thêm trạng thái Order | Sales quản lý state transition | Nhiều service cùng ghi Order.status |
| Thay schema Customer | Customer công bố contract/version | Tất cả service phụ thuộc trực tiếp schema database |

Một boundary tốt không có nghĩa không bao giờ phải thay đổi contract. Nó có nghĩa thay đổi thường xuyên bên trong service được cô lập; khi contract thay đổi, có kế hoạch tương thích và consumer có thời gian chuyển đổi.

### Đo coordinated change

Hãy quan sát:

- Một thay đổi nghiệp vụ thường sửa bao nhiêu repository/service?
- Bao nhiêu lần cần release đồng bộ?
- Có bao nhiêu API call xuyên boundary trong một workflow?
- Một schema migration ảnh hưởng bao nhiêu nhóm?
- Bao nhiêu incident lan từ một service sang các service khác?
- Có bao nhiêu exception phải xử lý vì một consumer hiểu khác contract?

Đây là bằng chứng để điều chỉnh boundary sau khi hệ thống vận hành.

## 7. Ví dụ thực tế: chọn boundary cho quy trình đặt hàng

Giả sử nhóm đang thiết kế một nền tảng bán hàng. Các ứng viên gồm Catalog, Sales, Inventory, Payments và Delivery.

### Sales: giữ Order và OrderLine cùng nhau

Order và OrderLine thường thay đổi trong cùng hành vi: thêm hàng, tính tổng, áp dụng chính sách bán và xác nhận. Chúng có invariant chung và cùng vòng đời trong ngữ cảnh bán hàng. Vì vậy, chúng nên thuộc cùng Aggregate hoặc cùng write boundary của Sales.

Không cần tạo OrderLine Service chỉ vì OrderLine là một Entity riêng. Entity là khái niệm mô hình miền; nó không tự động là đơn vị triển khai.

### Inventory: tách khi quyền sở hữu và nhu cầu độc lập đủ rõ

Inventory quản lý lượng hàng có thể giữ, Reservation, expiry và chính sách phân bổ. Nó có consistency boundary riêng, có thể được nhiều kênh bán sử dụng và có tải hoặc lịch thay đổi khác Sales.

Sales gửi command ReserveStock; Inventory quyết định và trả reservationId hoặc kết quả từ chối. Sales lưu reference và trạng thái workflow. Khi đơn bị hủy, Sales yêu cầu ReleaseReservation. Đây là một ranh giới có thể kiểm chứng qua ownership và hành vi.

### Payments: tách khi tích hợp và kiểm soát thanh toán cần autonomy

Payments quản lý authorization, capture, refund, provider integration, idempotency và đối soát. Nó có yêu cầu bảo mật, audit và failure handling riêng. Sales không nên lưu hoặc thao tác trực tiếp dữ liệu nhạy cảm của provider.

Sales có thể giữ payment reference và kết quả nghiệp vụ cần thiết. Payments là nơi quyết định trạng thái giao dịch thanh toán.

### Delivery: tách khi vòng đời giao hàng có năng lực riêng

Delivery quản lý shipment, carrier, tracking và ngoại lệ giao nhận. Nó có thể phục vụ nhiều loại đơn hoặc kênh. Nếu đây là năng lực độc lập với nhóm và quy tắc riêng, service boundary có cơ sở.

### Catalog: không phải lúc nào cũng cần một service riêng

Nếu Catalog chỉ là danh sách sản phẩm nhỏ do cùng nhóm Sales quản lý, có thể giữ như module. Nếu Catalog có search, merchandising, media, giá hiển thị và nhịp phát hành riêng, một service riêng có thể đem lại lợi ích.

Một phương án hợp lý cho hệ thống đã có nhu cầu độc lập rõ:

~~~mermaid
flowchart TB
    Client["Web / Mobile / Partner"] --> Sales["Sales Service"]
    Sales -->|ReserveStock command| Inventory["Inventory Service"]
    Sales -->|AuthorizePayment command| Payments["Payments Service"]
    Sales -->|CreateShipment command| Delivery["Delivery Service"]
    Client -->|Product queries| Catalog["Catalog Service"]
    Inventory -->|Reservation events| Sales
    Payments -->|Payment events| Sales
    Delivery -->|Shipment events| Sales
~~~

Sơ đồ chỉ là boundary hypothesis. Nó không nói mọi request phải gọi tuần tự tất cả service hoặc mọi service phải được tạo ngay từ ngày đầu. Workflow cần timeout, idempotency, trạng thái trung gian và compensation phù hợp.

## 8. Boundary sai thường tạo distributed monolith

Distributed monolith là hệ thống có nhiều deployable service nhưng các service vẫn phụ thuộc chặt chẽ như một ứng dụng nguyên khối. Nó có chi phí của phân tán mà không có lợi ích autonomy tương xứng.

Dấu hiệu thường gặp:

- Mọi service phải triển khai cùng lúc.
- Một request đi qua nhiều service chỉ để thực hiện một thao tác đơn giản.
- Nhiều service cùng ghi một database hoặc schema.
- Contract thay đổi liên tục và consumer không có thời gian tương thích.
- Một service không thể khởi động hoặc hoạt động nếu service khác tạm ngừng.
- Team phải phối hợp liên tục để sửa một quy tắc.
- Logic nghiệp vụ bị chia giữa nhiều service và không có owner quyết định cuối.
- Retry lồng nhau tạo tải tăng cấp khi một dependency chậm.
- Một lỗi nhỏ lan thành outage trên toàn hệ thống.

### Chatty communication

Nếu một màn hình cần 20 lời gọi đồng bộ đến 6 service để hiển thị dữ liệu, boundary hoặc read strategy có thể chưa hợp lý. Có thể dùng read model tổng hợp, API composition hoặc BFF để phục vụ truy vấn, miễn là không chuyển quyền sở hữu ghi sang thành phần tổng hợp.

### Shared database

Dùng chung database có thể là giai đoạn chuyển tiếp, nhưng nếu nhiều service cùng sở hữu và cập nhật schema, chúng vẫn bị ràng buộc qua storage. Khi tách, cần chuyển dần quyền ghi về owner, công bố contract và loại bỏ truy cập chéo theo lộ trình.

### Service theo Entity hoặc theo technical layer

Các service như CustomerNameService, OrderLineService, AddressService hoặc ValidationService thường không thể hiện một năng lực nghiệp vụ trọn vẹn. Chúng dễ tạo ra nhiều lời gọi mạng cho một thao tác và làm quy tắc bị phân tán.

## 9. Microservice hay modular monolith?

Không phải mọi Bounded Context đều cần một deployable service ngay lập tức. Modular monolith có thể giữ nhiều module trong một tiến trình nhưng vẫn thực thi boundary bằng package, interface, dependency rule và quyền sở hữu dữ liệu logic.

| Tiêu chí | Modular monolith | Microservices |
| --- | --- | --- |
| Triển khai | Một đơn vị | Nhiều đơn vị độc lập |
| Giao tiếp | In-process/module API | Network API/message |
| Transaction | Có thể dùng transaction chung nếu cùng database | Thường transaction cục bộ và phối hợp workflow |
| Scale | Thường scale toàn ứng dụng | Có thể scale từng service |
| Failure isolation | Process chung | Có thể cô lập theo service nếu thiết kế đúng |
| Vận hành | Ít thành phần hơn | Cần discovery, observability, deployment, resilience |
| Phù hợp | Boundary đã rõ nhưng chưa cần deploy độc lập | Có nhu cầu độc lập đã được chứng minh |

### Modular monolith là nơi kiểm chứng boundary

Bạn có thể tổ chức:

- sales sở hữu Order và quy tắc bán.
- inventory sở hữu Stock và Reservation.
- payments sở hữu Payment.
- delivery sở hữu Shipment.

Các module chỉ giao tiếp qua interface hoặc event nội bộ đã định nghĩa. Cấm truy cập repository hoặc bảng nội bộ của module khác. Khi một module cần scale, release hoặc cách ly riêng, có thể trích xuất nó thành service mà ít phải khám phá lại ownership.

Modular monolith không phải microservice thất bại. Nó là một cách giữ boundary rõ ràng trong khi tránh trả chi phí phân tán trước khi có nhu cầu.

## 10. Decision matrix: so sánh ứng viên boundary

Có thể dùng bảng sau để so sánh các phương án. Đây là công cụ thảo luận, không phải công thức điểm số phổ quát.

| Tiêu chí | Bằng chứng ủng hộ tách | Bằng chứng ủng hộ gộp |
| --- | --- | --- |
| Business capability | Mục tiêu và quyết định riêng | Chỉ là một bước kỹ thuật nhỏ |
| Data ownership | Có nguồn sự thật và owner rõ | Nhiều phần cùng sửa một dữ liệu |
| Invariants | Có thể bảo vệ cục bộ | Cần atomic update thường xuyên với phần kia |
| Change cadence | Thay đổi độc lập | Luôn thay đổi cùng nhau |
| Deployment | Cần release riêng | Phải release đồng thời |
| Scale | Workload khác biệt rõ | Tải tương tự, scale cùng nhau |
| Availability | Có thể tiếp tục với trạng thái chờ/fallback | Phụ thuộc đồng bộ chặt ở mọi request |
| Security | Ranh giới truy cập/secret/audit riêng | Không có yêu cầu tách biệt |
| Team ownership | Một team chịu trách nhiệm end-to-end | Nhiều team cùng sửa một quy tắc |
| Operations | Có năng lực giám sát và on-call | Chưa có năng lực vận hành phân tán |

### Cách sử dụng

1. Liệt kê 2–3 phương án boundary cho cùng một năng lực.
2. Ghi bằng chứng thực tế vào từng tiêu chí, tránh chỉ ghi mong muốn.
3. Đánh dấu các invariant không thể phân tán hoặc yêu cầu đồng bộ bắt buộc.
4. Ước lượng chi phí mới: network calls, retry, observability, deployment, data migration và on-call.
5. Chọn phương án đáp ứng nhu cầu độc lập với số boundary nhỏ nhất có thể.
6. Ghi rõ giả định nào cần kiểm chứng sau khi triển khai.

Không cộng điểm máy móc để kết luận một service “đủ điều kiện”. Một invariant quan trọng bị chia cắt hoặc không có owner dữ liệu có thể là vấn đề lớn dù nhiều tiêu chí khác ủng hộ tách.

## 11. Lộ trình tách service từ hệ thống hiện hữu

Khi hệ thống đang là monolith, không nên bắt đầu bằng việc di chuyển toàn bộ code và database cùng lúc. Hãy chọn một năng lực có boundary tương đối rõ, sau đó tách dần quyền sở hữu.

### Bước 1: lập baseline và chọn candidate

Đo thay đổi, tải, lỗi, release coordination và dependency hiện tại. Chọn một candidate có lợi ích rõ, owner sẵn sàng và rủi ro chuyển đổi có thể kiểm soát.

### Bước 2: tạo module boundary trong monolith

Đưa code về module sở hữu, định nghĩa interface, cấm dependency ngược và chuyển các truy cập database chéo thành lời gọi qua module API. Việc này giúp lộ ra coupling trước khi có network.

### Bước 3: xác định contract

Thiết kế API/command/event theo ngôn ngữ của owner. Quy định version, error semantics, idempotency, authorization, timeout và compatibility. Consumer không phụ thuộc class nội bộ hoặc schema database của owner.

### Bước 4: chuyển quyền ghi dữ liệu

Xác định source of truth, backfill dữ liệu và chuyển write path theo từng bước. Tránh dual-write tùy tiện từ hai service. Nếu cần đồng bộ trong thời gian chuyển tiếp, phải có reconciliation và cách xử lý conflict rõ ràng.

### Bước 5: dùng Strangler Fig hoặc Branch by Abstraction

Định tuyến một phần traffic sang service mới qua facade/gateway. Có thể bắt đầu với read path hoặc một use case ít rủi ro, sau đó chuyển write ownership khi đã xác minh.

### Bước 6: thiết kế workflow phân tán

Nếu thao tác trước đây dùng transaction chung, xác định invariant nào vẫn cục bộ và cam kết nào cần Saga, reservation, outbox hoặc compensation. Không sao chép transaction monolith thành chuỗi HTTP call đồng bộ.

### Bước 7: quan sát, so sánh và loại bỏ đường cũ

Theo dõi latency, error rate, duplicate, data drift, event lag và chi phí vận hành. Chỉ bỏ đường cũ sau khi dữ liệu và hành vi đã được đối soát, có phương án rollback và consumer đã chuyển sang contract mới.

### Expand-and-contract cho schema/API

Khi contract thay đổi:

1. Thêm field hoặc endpoint mới theo hướng tương thích.
2. Deploy producer hỗ trợ cả cũ và mới.
3. Chuyển consumer sang contract mới.
4. Theo dõi consumer cũ và loại bỏ khi không còn sử dụng.
5. Xóa field/endpoint cũ ở một release riêng.

Cách này tránh yêu cầu mọi service phải nâng cấp cùng một thời điểm.

## 12. Các chi phí phải tính trước khi tách

Một microservice mới kéo theo chi phí không xuất hiện hoặc ít rõ hơn trong một module nội bộ:

- Build, deploy, rollback và quản lý cấu hình riêng.
- Service discovery, routing, TLS và quản lý secret.
- Timeout, retry, circuit breaker, bulkhead và rate limit.
- Message broker, schema registry hoặc cơ chế contract.
- Distributed tracing, correlation ID và log tập trung.
- Dashboard, alert, SLO và on-call.
- Database migration, backup, restore và data retention.
- Xử lý duplicate, event ordering, eventual consistency và reconciliation.
- Kiểm thử contract, integration và failure mode.
- Quản lý quyền truy cập và audit theo từng service.

### Retry có thể khuếch đại sự cố

Nếu Sales retry Inventory 3 lần, API gateway retry 3 lần và client cũng retry 3 lần, một thao tác có thể tạo nhiều request hơn dự kiến. Retry cần có giới hạn, backoff, jitter, deadline tổng thể và idempotency key. Không retry mọi lỗi giống nhau.

### Network call có latency và failure riêng

Một lời gọi in-process thường có semantics khác với lời gọi qua mạng. Request có thể timeout dù service đích đã xử lý thành công. Caller không biết chắc tác động đã xảy ra hay chưa; cần idempotency hoặc truy vấn trạng thái. Điều này ảnh hưởng trực tiếp tới cách thiết kế command và workflow.

## 13. Đo lường xem boundary có đang hoạt động tốt không

Ranh giới không phải quyết định một lần rồi bỏ qua. Sau khi triển khai, cần xem service có thực sự độc lập hơn không.

Các chỉ số hữu ích:

- Tỷ lệ thay đổi chỉ cần deploy một service.
- Số coordinated release mỗi tháng.
- Lead time từ commit đến production theo service.
- Tỷ lệ thay đổi phải sửa nhiều service.
- Số lời gọi đồng bộ xuyên service trong một workflow.
- Latency p95/p99 và timeout giữa các dependency.
- Số incident lan qua boundary.
- Event lag, retry, dead-letter và data drift.
- Tỷ lệ deployment rollback và change failure rate.
- Mức độ rõ ràng của ownership và thời gian xử lý sự cố.

Không tối ưu một metric riêng lẻ. Giảm số dòng code trong mỗi service nhưng tăng số coordinated deployment có thể là dấu hiệu boundary xấu. Tăng số service nhưng không cải thiện autonomy cũng không phải thành công.

## 14. Những sai lầm thường gặp

- **Một Bounded Context luôn bằng một microservice:** bỏ qua nhu cầu deploy và vận hành thực tế.
- **Một Entity bằng một service:** chia cắt Aggregate và invariant.
- **Chia theo technical layer:** tạo service controller, repository hoặc validation dùng chung qua mạng.
- **Tách chỉ để scale:** chưa chứng minh workload khác biệt và chưa tính chi phí giao tiếp.
- **Chia sẻ database:** làm mất quyền sở hữu dữ liệu và buộc release đồng bộ.
- **Service gọi nhau quá nhiều:** tạo chatty communication và latency cộng dồn.
- **Dùng synchronous call cho mọi bước:** failure của dependency lan thành outage.
- **Không có owner end-to-end:** không ai chịu trách nhiệm cho một năng lực khi production lỗi.
- **Tạo service dùng chung quá tổng quát:** một thay đổi nhỏ buộc nhiều domain phụ thuộc vào cùng release.
- **Đưa mọi workflow vào một orchestrator khổng lồ:** coordinator trở thành nơi chứa logic của nhiều domain.
- **Dùng event để thay API cho mọi truy vấn:** consumer phải tự dựng projection phức tạp và khó lấy dữ liệu cần ngay.
- **Dual-write database và broker không có Outbox:** có thể mất hoặc phát event sai trạng thái.
- **Tách quá nhiều trước khi có năng lực vận hành:** tăng số điểm lỗi và gánh nặng on-call.
- **Không có lộ trình loại bỏ monolith path:** hai nguồn ghi cùng tồn tại vô thời hạn.

## 15. Quy trình lựa chọn ranh giới microservice

Khi đề xuất một boundary, hãy thực hiện theo thứ tự:

1. **Mô tả năng lực nghiệp vụ.** Viết rõ kết quả, người dùng, quyết định và owner.
2. **Xác định subdomain/Bounded Context.** Tìm ngôn ngữ và mô hình có hiệu lực.
3. **Liệt kê Aggregate và invariant.** Đánh dấu thay đổi nào phải nguyên tử.
4. **Xác định source of truth.** Chỉ rõ service/module nào sở hữu từng dữ liệu.
5. **Thu thập change scenario.** Xem thay đổi nào cần phát hành cùng nhau và thay đổi nào độc lập.
6. **Đánh giá scale, availability, security và team ownership.** Dùng bằng chứng workload, SLO, quyền truy cập và trách nhiệm.
7. **Kiểm tra giao tiếp.** Ước lượng API calls, event, latency, retry, timeout và eventual consistency.
8. **So sánh modular monolith với microservice.** Chọn phương án đơn giản đáp ứng nhu cầu.
9. **Ghi boundary hypothesis.** Nêu lý do, giả định, contract, owner và failure mode.
10. **Thử nghiệm ở phạm vi nhỏ.** Tách một workflow hoặc một read/write path có thể đo lường.
11. **Quan sát kết quả.** So sánh autonomy, lead time, incident và chi phí vận hành.
12. **Điều chỉnh khi có bằng chứng mới.** Boundary là mô hình có thể tiến hóa theo năng lực và tổ chức.

Checklist review:

- [ ] Service đại diện cho một năng lực nghiệp vụ có mục tiêu rõ?
- [ ] Bounded Context và service boundary được phân biệt?
- [ ] Có một owner chịu trách nhiệm cho dữ liệu và quyết định?
- [ ] Aggregate/invariant không bị chia cắt tùy tiện?
- [ ] Các thay đổi thường xuyên có thể phát hành độc lập?
- [ ] Nhu cầu scale, availability hoặc security có bằng chứng?
- [ ] Contract không phơi bày schema và class nội bộ?
- [ ] Không có service nào ghi trực tiếp database của service khác?
- [ ] Workflow có timeout, retry, idempotency và compensation khi cần?
- [ ] Team có khả năng deploy, quan sát và on-call cho service mới?
- [ ] Đã so sánh với modular monolith?
- [ ] Có kế hoạch migration, rollback và loại bỏ đường cũ?
- [ ] Có metric để kiểm tra boundary sau khi triển khai?

## Kết luận

Ranh giới microservice nên xuất phát từ năng lực nghiệp vụ và nhu cầu độc lập có thể quan sát: quyền sở hữu dữ liệu, nhịp thay đổi, triển khai, scale, bảo mật, availability và trách nhiệm của nhóm. DDD giúp khám phá mô hình và Bounded Context; Aggregate cùng invariant cho biết những thay đổi nào cần nhất quán cục bộ. Các yếu tố này tạo cơ sở để hình thành boundary hypothesis, nhưng không tự động quyết định số lượng service.

Một boundary tốt cho phép phần bên trong thay đổi độc lập qua hợp đồng ổn định, đồng thời giữ các quy tắc nghiệp vụ ở đúng owner. Nếu việc tách khiến nhiều service phải cùng phát hành, cùng ghi database hoặc gọi nhau liên tục, hãy xem lại ranh giới. Modular monolith là lựa chọn phù hợp khi boundary đã rõ nhưng nhu cầu deploy độc lập chưa đủ mạnh. Hãy tách từng bước, đo lợi ích và chi phí, rồi điều chỉnh theo bằng chứng từ production.
