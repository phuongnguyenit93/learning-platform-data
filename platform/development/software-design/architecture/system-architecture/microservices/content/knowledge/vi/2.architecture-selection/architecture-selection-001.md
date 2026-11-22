# So sánh khối đơn thể, khối đơn thể mô-đun và vi dịch vụ

> **Chủ đề:** Software Design → Architecture → System Architecture → Microservices  
> **Nhóm:** Lựa chọn kiến trúc  
> **Mục tiêu:** Phân biệt ba cách tổ chức và triển khai hệ thống; hiểu sự đánh đổi về độ phức tạp, khả năng mở rộng, dữ liệu, độ tin cậy và vận hành; lựa chọn kiến trúc phù hợp với bối cảnh thực tế.

## 1. Đặt vấn đề: lựa chọn kiến trúc là lựa chọn sự đánh đổi

Giả sử xây dựng nền tảng bán hàng với các năng lực: quản lý sản phẩm, giỏ hàng, đặt hàng, tồn kho, thanh toán và thông báo. Có ít nhất ba cách tổ chức hệ thống:

1. **Khối đơn thể (monolith):** toàn bộ ứng dụng thường được xây dựng và triển khai thành một đơn vị; các thành phần có thể gọi nhau trực tiếp trong cùng tiến trình.
2. **Khối đơn thể mô-đun (modular monolith):** vẫn triển khai thành một đơn vị nhưng bên trong chia thành các mô-đun nghiệp vụ có ranh giới, giao diện và quyền sở hữu dữ liệu rõ ràng.
3. **Vi dịch vụ (microservices):** chia hệ thống thành nhiều dịch vụ độc lập theo năng lực nghiệp vụ; mỗi dịch vụ có chu kỳ triển khai riêng và giao tiếp qua mạng.

Không có kiến trúc nào mặc nhiên “hiện đại hơn nên tốt hơn”. Kiến trúc phù hợp là kiến trúc đáp ứng yêu cầu hiện tại và dự kiến, đồng thời để nhóm phát triển có thể thay đổi hệ thống với chi phí và rủi ro chấp nhận được.

**Điểm dễ nhầm:** “Monolith” mô tả chủ yếu ranh giới triển khai; “modular” mô tả chất lượng phân tách bên trong; “microservices” thêm ranh giới tiến trình, mạng, vận hành và quyền tự chủ triển khai. Một monolith được thiết kế tốt hoàn toàn có thể có cấu trúc mô-đun chặt chẽ.

## 2. Ba mô hình và sơ đồ trực quan

### 2.1. Khối đơn thể (monolith)

Một ứng dụng chứa mã xử lý giao diện/API, nghiệp vụ và truy cập dữ liệu. Các chức năng có thể chia lớp hoặc gói, nhưng không nhất thiết được cô lập theo miền nghiệp vụ. Một bản build thường tạo ra một artifact và một lần phát hành thường triển khai cả ứng dụng.

~~~mermaid
flowchart TB
    Client[Web / Mobile] --> App
    subgraph App[Ứng dụng đơn thể - một đơn vị triển khai]
        API[API / Controller] --> Catalog[Catalog]
        API --> Orders[Orders]
        API --> Stock[Inventory]
        API --> Payment[Payment]
        Orders --> Stock
        Orders --> Payment
    end
    App --> DB[(Cơ sở dữ liệu ứng dụng)]
~~~

Ví dụ: một ứng dụng Java Spring Boot gồm các package controller, service, repository, entity; tất cả chạy trong cùng JVM, dùng một cơ sở dữ liệu và được triển khai như một ứng dụng. Việc có nhiều package không tự động làm ứng dụng trở thành modular monolith nếu ranh giới nghiệp vụ không được thực thi.

**Ưu điểm:** khởi tạo nhanh, chạy và debug đơn giản, dễ dùng transaction trong một database, ít hạ tầng cần vận hành, kiểm thử end-to-end và triển khai giai đoạn đầu thuận tiện.

**Hạn chế:** khi mã và đội ngũ lớn lên, phụ thuộc chéo có thể tăng; một thay đổi nhỏ vẫn đòi hỏi build/triển khai cả ứng dụng; lỗi cạn tài nguyên ở một phần có thể ảnh hưởng phần khác; khó mở rộng một năng lực có tải đặc thù mà không nhân bản toàn bộ tiến trình.

Lưu ý: một monolith vẫn có thể chạy nhiều replica sau load balancer. “Đơn thể” không đồng nghĩa “chỉ một máy chủ”.

### 2.2. Khối đơn thể mô-đun (modular monolith)

Hệ thống vẫn là **một đơn vị chạy và triển khai**, nhưng mã được tổ chức theo các module như Catalog, Orders, Inventory, Payments. Mỗi module công bố một API/contract rõ ràng; thành phần bên ngoài không được truy cập trực tiếp lớp nội bộ hoặc bảng dữ liệu riêng của module.

~~~mermaid
flowchart TB
    Client[Web / Mobile] --> API[Ứng dụng - một lần triển khai]
    subgraph API
        subgraph Catalog[Module Catalog]
            CatalogAPI[Public API] --> CatalogCore[Logic và dữ liệu nội bộ]
        end
        subgraph Orders[Module Orders]
            OrdersAPI[Public API] --> OrdersCore[Logic và dữ liệu nội bộ]
        end
        subgraph Inventory[Module Inventory]
            InvAPI[Public API] --> InvCore[Logic và dữ liệu nội bộ]
        end
        subgraph Payments[Module Payments]
            PayAPI[Public API] --> PayCore[Logic và dữ liệu nội bộ]
        end
        OrdersAPI --> InvAPI
        OrdersAPI --> PayAPI
    end
~~~

Một modular monolith có thể dùng **chung một database vật lý** nhưng nên tách sở hữu dữ liệu bằng schema, bảng và quyền truy cập phù hợp. “Chung database” không phải giấy phép cho module Orders tự ý sửa bảng Inventory.

Gợi ý cấu trúc trong Java:

~~~text
src/main/java/com/example/shop/
  catalog/
    api/
    internal/
    persistence/
  orders/
    api/
    internal/
    persistence/
  inventory/
    api/
    internal/
    persistence/
  payments/
    api/
    internal/
    persistence/
  bootstrap/
~~~

Ở đây, các module phụ thuộc vào giao diện công khai của nhau; luật kiến trúc hoặc kiểm tra phụ thuộc có thể ngăn import trực tiếp từ package internal. Có thể triển khai module bằng Java modules, Maven/Gradle subprojects, package visibility, ArchUnit hoặc các quy ước có thể kiểm tra tự động.

**Ưu điểm:** giữ phần lớn lợi ích triển khai và transaction của monolith; làm rõ miền nghiệp vụ; giảm thay đổi lan truyền; dễ thay đổi cấu trúc nội bộ; có nền tảng tốt để tách dịch vụ khi thực sự cần.

**Hạn chế:** vẫn phải triển khai chung; không đạt cô lập lỗi ở mức tiến trình; khó mở rộng CPU/bộ nhớ riêng cho từng module; ranh giới dễ bị phá vỡ nếu nhóm không duy trì kỷ luật phụ thuộc và quyền sở hữu dữ liệu.

### 2.3. Vi dịch vụ (microservices)

Mỗi dịch vụ sở hữu một năng lực nghiệp vụ tương đối độc lập, chạy trong tiến trình riêng, có API/event contract và pipeline triển khai riêng. Dịch vụ thường sở hữu dữ liệu của nó; hệ thống dùng giao tiếp đồng bộ (HTTP/gRPC) hoặc bất đồng bộ (message/event) để phối hợp.

~~~mermaid
flowchart TB
    Client[Web / Mobile] --> Gateway[API Gateway / BFF]
    Gateway --> Catalog[Catalog Service]
    Gateway --> Orders[Order Service]
    Gateway --> Payment[Payment Service]
    Orders -->|Event / API| Inventory[Inventory Service]
    Orders -->|Event / API| Payment
    Catalog --> CDB[(Catalog DB)]
    Orders --> ODB[(Orders DB)]
    Inventory --> IDB[(Inventory DB)]
    Payment --> PDB[(Payment DB)]
~~~

Sơ đồ thể hiện **quyền sở hữu dữ liệu logic**: các DB có thể nằm trên cùng một máy chủ quản trị ở giai đoạn đầu, miễn là mỗi dịch vụ kiểm soát schema và thay đổi của mình. Một “service” dùng chung toàn bộ bảng với service khác và luôn phải release cùng nhau thường chưa có tính độc lập cần thiết.

**Ưu điểm:** có thể triển khai và mở rộng riêng từng dịch vụ; nhóm sở hữu dịch vụ có quyền quyết định và phát hành độc lập; lỗi có thể được khoanh vùng nếu thiết kế cách ly và xử lý lỗi tốt; dễ dùng công nghệ phù hợp cho từng bài toán khi chi phí quản trị cho phép.

**Hạn chế:** mạng, độ trễ, timeout, retry và lỗi từng phần trở thành vấn đề thường xuyên; giao dịch liên dịch vụ phức tạp; cần quan sát tập trung, bảo mật service-to-service, quản lý contract, CI/CD, vận hành và kiểm thử phân tán; khó debug một luồng trải qua nhiều dịch vụ.

**Điểm quyết định:** microservices có lợi khi **sự tự chủ triển khai và cô lập theo nghiệp vụ** tạo ra giá trị lớn hơn chi phí phân tán.

## 3. Bảng so sánh theo tiêu chí thiết kế và vận hành

| Tiêu chí | Monolith | Modular monolith | Microservices |
|---|---|---|---|
| Đơn vị triển khai | Một ứng dụng | Một ứng dụng | Nhiều dịch vụ, mỗi dịch vụ có thể phát hành riêng |
| Ranh giới mã nguồn | Có thể mờ hoặc rõ | Rõ theo module nghiệp vụ, nên có kiểm soát phụ thuộc | Rõ theo API/event và ownership của dịch vụ |
| Giao tiếp thường dùng | Gọi hàm trong tiến trình | Gọi qua giao diện module, có thể dùng sự kiện nội bộ | Gọi qua mạng hoặc message broker |
| Dữ liệu | Thường chung một DB, truy cập có thể đan xen | Có thể chung DB vật lý, module sở hữu bảng/schema | Khuyến nghị quyền sở hữu dữ liệu riêng của mỗi service |
| Transaction | ACID trong cùng DB tương đối thuận tiện | ACID trong cùng DB vẫn thuận tiện nếu bảo vệ ranh giới | Giao dịch qua dịch vụ thường cần saga, outbox, bù trừ |
| Độ trễ giao tiếp | Thấp, không có network hop nội bộ | Thấp cho giao tiếp nội bộ | Có độ trễ mạng, serialize, retry, queue |
| Scale | Nhân bản cả ứng dụng; có thể scale bằng nhiều replica | Nhân bản cả ứng dụng; tối ưu riêng module trong cùng runtime | Scale độc lập dịch vụ chịu tải cao |
| Phát hành tính năng | Thường release toàn ứng dụng | Release toàn ứng dụng | Có thể release riêng nếu contract và dependency cho phép |
| Cô lập lỗi | Rủi ro lỗi lan trong tiến trình | Cùng rủi ro tiến trình, nhưng mã ít đan xen hơn | Có thể cô lập tốt hơn nhưng lỗi mạng và dependency vẫn lan truyền |
| Debug và tracing | Stack trace/log tập trung hơn | Tương tự monolith; module rõ giúp điều tra | Cần distributed tracing, correlation ID, tập trung log/metrics |
| Kiểm thử | Tích hợp thường trực tiếp | Unit/module/integration; có thể kiểm tra luật module | Thêm contract testing, resilience, async integration |
| Chi phí hạ tầng/vận hành | Thường thấp ở giai đoạn đầu | Thường gần monolith | Cao hơn do nhiều runtime, pipeline, network và quan sát |
| Khả năng tự chủ của nhóm | Có thể bị phụ thuộc release chung | Phân công module tốt nhưng vẫn release chung | Cao nếu ranh giới và trách nhiệm thực sự độc lập |
| Khả năng thay đổi kiến trúc | Khó khi phụ thuộc chéo lớn | Tương đối dễ nếu module đã tách hợp lý | Dễ thay đổi nội bộ một dịch vụ; khó thay đổi contract và luồng liên dịch vụ |

Bảng mô tả **xu hướng phổ biến**, không phải bảo đảm tuyệt đối. Ví dụ, microservices thiết kế sai vẫn có thể triển khai chung và chia sẻ dữ liệu; monolith thiết kế tốt có thể phục vụ lưu lượng rất lớn bằng cache, indexing, queue và horizontal scaling.

## 4. So sánh bằng cùng một nghiệp vụ: đặt hàng

Xét thao tác **Đặt hàng** với các bước: xác thực giỏ hàng, giữ hàng trong kho, ghi đơn, thu tiền và gửi thông báo.

### 4.1. Với monolith

OrderService gọi InventoryService và PaymentService trong cùng ứng dụng. Nếu mọi cập nhật dữ liệu đều trong một DB, những phần thích hợp có thể nằm trong cùng transaction ACID. Tuy nhiên, **gọi cổng thanh toán bên ngoài** không thuộc transaction nội bộ: thanh toán thành công nhưng ứng dụng timeout vẫn có thể tạo trạng thái không nhất quán.

Luồng điển hình:

1. Kiểm tra yêu cầu và trạng thái giỏ.
2. Trong transaction DB, tạo đơn và đặt giữ tồn kho.
3. Commit dữ liệu.
4. Thực hiện thanh toán qua nhà cung cấp ngoài bằng mã idempotency.
5. Ghi nhận trạng thái thanh toán; nếu thất bại, giải phóng giữ hàng hoặc chuyển đơn sang trạng thái cần xử lý.
6. Phát sự kiện để gửi thông báo.

Đừng đặt lời gọi mạng lâu trong transaction DB chỉ để “mọi bước nguyên tử”: làm vậy giữ lock lâu và vẫn không tạo được ACID xuyên hệ thống ngoài.

### 4.2. Với modular monolith

Các bước tương tự, nhưng Orders chỉ được sử dụng giao diện công khai của Inventory và Payments:

~~~java
public interface InventoryPort {
    ReservationResult reserve(OrderId orderId, List<OrderLine> lines);
    void release(OrderId orderId);
}

public interface PaymentPort {
    PaymentRequestId requestPayment(OrderId orderId, Money amount);
}
~~~

Module Orders không sửa trực tiếp entity hoặc repository nội bộ của Inventory. Có thể dùng sự kiện nội bộ như OrderPlaced để module Notifications phản ứng. Các module cần quy định rõ sự kiện chạy **trong transaction** hay **sau khi commit**, để tránh phát thông báo cho đơn đã rollback.

Giá trị lớn nhất ở đây là **tăng tính độc lập của mã và nghiệp vụ trước khi chịu chi phí phân tán**. Nếu sau này tách Inventory thành dịch vụ riêng, giao diện InventoryPort là điểm có thể thay adapter từ gọi trong tiến trình sang HTTP/gRPC hoặc messaging. Việc tách vẫn phải xử lý dữ liệu, transaction và vận hành; nó không tự động chỉ là đổi transport.

### 4.3. Với microservices

Một triển khai bất đồng bộ có thể như sau:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Order Service
    participant I as Inventory Service
    participant P as Payment Service
    participant E as Event Broker
    C->>O: POST /orders (idempotency key)
    O->>O: Tạo đơn PENDING
    O->>E: OrderCreated (outbox)
    E->>I: OrderCreated
    I->>I: Giữ hàng, chống xử lý trùng
    I->>E: StockReserved / StockRejected
    E->>O: Kết quả kho
    O->>E: PaymentRequested (nếu giữ hàng thành công)
    E->>P: PaymentRequested
    P->>P: Gọi payment provider có idempotency
    P->>E: PaymentSucceeded / PaymentFailed
    E->>O: Kết quả thanh toán
    O->>O: CONFIRMED hoặc CANCELLED
~~~

Luồng cần một **state machine** rõ ràng: PENDING → STOCK_RESERVED → CONFIRMED, hoặc PENDING → CANCELLED, hoặc trạng thái chờ đối soát khi kết quả thanh toán chưa chắc chắn. Từng consumer phải chịu được **at-least-once delivery**, nên lưu event ID hoặc operation ID để xử lý lặp an toàn.

Nếu đã giữ hàng nhưng thu tiền thất bại, một hành động bù trừ (compensation) có thể giải phóng hàng. Nếu đã thu tiền nhưng phải hủy đơn, nghiệp vụ có thể cần hoàn tiền; không thể coi việc đó giống rollback một transaction SQL.

### 4.4. Bài học về nhất quán dữ liệu

- **Trong một DB:** transaction ACID giúp bảo toàn tính bất biến cục bộ, nhưng không giải quyết sẵn API ngoài hay message broker.
- **Giữa các dịch vụ:** chấp nhận có những khoảng thời gian trạng thái chưa đồng bộ; thiết kế eventual consistency, retry, timeout, bù trừ và quy trình đối soát.
- **Transactional outbox:** ghi trạng thái nghiệp vụ và bản ghi sự kiện vào cùng transaction DB của một dịch vụ; tiến trình chuyển tiếp đẩy sự kiện đến broker sau đó. Cách này giảm rủi ro “đã commit nhưng mất event”.
- **Idempotency:** gửi lại cùng một lệnh không tạo thêm đơn, trừ tiền hai lần hay giữ kho trùng. Cần mã duy nhất và lưu kết quả xử lý.
- **Read model:** màn hình tổng hợp dữ liệu từ nhiều dịch vụ có thể dùng API composition, projection hoặc CQRS. Tránh join trực tiếp vào DB riêng của dịch vụ khác.

Việc chọn microservices vì “DB nào cũng tách thì scale tốt” sẽ phản tác dụng nếu nghiệp vụ có hàng chục transaction xuyên ranh giới; đây có thể là dấu hiệu ranh giới dịch vụ chưa phù hợp.

## 5. Bốn góc nhìn thường quyết định thành công

### 5.1. Ranh giới nghiệp vụ quan trọng hơn số lượng service

Nên bắt đầu từ **business capability** và **bounded context**: Catalog định nghĩa sản phẩm; Inventory quản lý tồn kho và giữ hàng; Orders quản lý vòng đời đơn; Payments quản lý thanh toán. Cùng một từ có thể mang nghĩa khác nhau trong hai context (ví dụ “giá hiển thị” ở Catalog và “giá đã chốt” ở Orders).

Dấu hiệu ranh giới tốt: có trách nhiệm rõ, dữ liệu do một bên sở hữu, thay đổi nội bộ ít bắt bên khác sửa, API tương đối ổn định và có thể diễn giải được tính bất biến của miền. Một service theo mỗi bảng hoặc mỗi lớp kỹ thuật (controller service, database service) thường tạo giao tiếp chatty và coupling cao.

**Nguyên tắc:** chia theo điều cần thay đổi cùng nhau. Các thao tác liên tục cần một transaction hoặc dùng chung bất biến mạnh nên được cân nhắc ở cùng một ranh giới nhất quán.

### 5.2. Phân tán tạo ra lỗi mới

Trong cùng tiến trình, gọi một hàm thường hoặc trả về hoặc ném exception. Qua mạng, timeout có thể có nghĩa yêu cầu chưa đến nơi, đã xử lý thành công nhưng phản hồi bị mất, hoặc đang xử lý dở. Vì vậy cần:

- Timeout có giới hạn, deadline lan truyền và retry có backoff/jitter khi an toàn.
- Circuit breaker và bulkhead cho dependency có nguy cơ làm cạn tài nguyên.
- Idempotency key và định nghĩa hành vi khi client gửi lại.
- Correlation ID, distributed tracing, log có cấu trúc, metrics về latency/lỗi/queue lag.
- Contract có versioning và chính sách tương thích trước/sau khi phát hành.

Đưa ứng dụng vào nhiều container không làm lỗi tự cô lập. Nếu mọi request vẫn gọi đồng bộ chuỗi dài A → B → C → D thì một sự cố tại D có thể làm hỏng nhiều luồng phía trước.

### 5.3. Khả năng mở rộng: đo trước khi tách

Ví dụ chỉ chức năng tìm kiếm sản phẩm tiêu thụ nhiều CPU, còn tạo đơn cần transaction mạnh. Microservices cho phép scale Catalog Search lên nhiều instance mà không nhân bản Payments. Nhưng monolith cũng có thể tăng replica, thêm cache, index, read replica, worker nền hoặc tách xử lý nặng ra queue.

Trước khi tách, đo **throughput, CPU/memory, p95/p99 latency, độ dài hàng đợi, chi phí mỗi request, dữ liệu tăng trưởng và kiểu tải theo thời gian**. Nếu nút thắt là một truy vấn SQL chưa có index, chia service thường không sửa được nguyên nhân.

### 5.4. Tổ chức và vận hành

Một đội nhỏ với một repo, một pipeline và yêu cầu phát hành cùng nhịp thường hưởng lợi từ modular monolith. Nhiều đội độc lập có miền sở hữu tương đối ổn định và cần triển khai khác lịch có thể hưởng lợi từ microservices.

Tuy nhiên, “mỗi đội có một service” chỉ hiệu quả khi đội đó thực sự chịu trách nhiệm xây dựng, vận hành và xử lý sự cố. Nếu vẫn cần họp liên đội để sửa một field và deploy đồng thời năm service thì ranh giới kỹ thuật không mang lại quyền tự chủ thực tế.

Các năng lực vận hành nên có trước hoặc song hành cùng việc tách: CI/CD tự động, IaC, secrets management, service discovery hoặc định tuyến, quan sát tập trung, on-call/incident response, rollout/rollback và kiểm soát API contract.

## 6. Chọn theo bối cảnh: ví dụ thực tế

| Bối cảnh | Xu hướng phù hợp | Lý do và điều kiện |
|---|---|---|
| MVP, sản phẩm mới, một đội nhỏ, miền nghiệp vụ chưa ổn định | Modular monolith hoặc monolith có tổ chức | Chi phí triển khai thấp, thử nghiệm nhanh; cần giữ các ranh giới đủ rõ để không tích lũy coupling vô hạn |
| Sản phẩm có nhiều nghiệp vụ nhưng chung lịch release, tải vừa | Modular monolith | Cô lập thay đổi trong mã, giữ transaction và vận hành đơn giản |
| Nhiều đội sở hữu miền riêng, phát hành khác nhịp, có DevOps trưởng thành | Microservices | Tự chủ triển khai tạo giá trị rõ; phải chấp nhận chi phí điều phối và mạng |
| Một tác vụ có tải cực lớn và độc lập, ví dụ xử lý ảnh hoặc tìm kiếm | Tách riêng tác vụ/service đó khi cần | Scale phần nóng theo tài nguyên đặc thù; phần còn lại có thể vẫn là modular monolith |
| Nghiệp vụ đòi hỏi invariant xuyên nhiều thực thể và giao dịch chặt | Ưu tiên cùng ranh giới transaction | Tránh biến nghiệp vụ đơn giản thành saga phức tạp |
| Hệ thống legacy phụ thuộc chéo dày đặc | Làm rõ module trước, tách dần có đo lường | Cắt thẳng thành service dễ tạo distributed monolith |

Ví dụ cụ thể:

**Startup thương mại điện tử có 6 kỹ sư:** chọn modular monolith với các module Catalog, Orders, Inventory, Payments, một pipeline và một DB có bảng thuộc quyền từng module. Chi phí hệ thống phân tán thường vượt giá trị phát hành độc lập ở giai đoạn này.

**Nền tảng phục vụ nhiều quốc gia, 8 đội phát triển:** nếu Catalog, Checkout, Fulfillment và Billing có yêu cầu tải, tốc độ phát hành và trách nhiệm vận hành khác nhau, có thể tách các bounded context thành dịch vụ. Cần chứng minh contract ổn định, ownership rõ, event/observability và tự chủ triển khai thực tế.

**Nền tảng học trực tuyến:** quản lý khóa học, tài khoản và thanh toán có thể ở modular monolith; chuyển mã video là worker/service riêng do CPU, thời gian xử lý và retry khác biệt. Không cần biến mọi module thành microservice đồng loạt.

## 7. Khung ra quyết định có thể áp dụng

Bắt đầu bằng yêu cầu đo được:

1. **Yêu cầu sản phẩm:** số nhóm nghiệp vụ, tốc độ thay đổi, mức ổn định của miền, yêu cầu nhất quán, SLA/SLO.
2. **Quy mô đội:** số nhóm cần deploy độc lập, mức độ phối hợp giữa nhóm, năng lực on-call và quản trị production.
3. **Đặc điểm tải:** phần nào là nút thắt, mức biến động tải, nhu cầu scale khác nhau, ngân sách hạ tầng.
4. **Dữ liệu và tích hợp:** transaction nào cần nguyên tử, số API bên ngoài, cách quản lý identity, báo cáo xuyên miền.
5. **Mức trưởng thành vận hành:** tự động hóa triển khai, giám sát, tracing, rollback, kiểm soát bảo mật và schema migration.
6. **Khả năng quay đầu:** nếu chọn modular monolith, liệu có thiết kế được module boundary đủ rõ để sau này tách mà không viết lại toàn bộ?

Có thể chấm tương đối từng phương án theo thang 1–5 và gán trọng số cho từng tiêu chí. Ví dụ một nhóm nhỏ ưu tiên time-to-market và ít vận hành sẽ đặt trọng số cao cho đơn giản và tính linh hoạt nghiệp vụ; một tổ chức lớn đặt nặng tự chủ phát hành và scale từng miền. **Điểm số là công cụ làm rõ lập luận, không thay thế dữ liệu thực tế.**

### Những câu hỏi cần trả lời trước khi quyết định microservices

- Có service nào cần phát hành độc lập thường xuyên đến mức release chung tạo nút thắt có thể đo được không?
- Có miền nào cần scale tài nguyên theo một mẫu tải khác hẳn phần còn lại không?
- Ranh giới dữ liệu và ownership đã rõ chưa, hay các service sẽ cùng sửa một bảng?
- Hệ thống có chịu được eventual consistency và có quy trình bù trừ/đối soát không?
- Đội ngũ có xử lý được tracing, sự cố mạng, rollback và contract tương thích không?
- Chi phí vận hành tăng có nhỏ hơn giá trị kinh doanh thu được không?

Nếu câu trả lời cho phần lớn câu hỏi vẫn là “chưa biết”, việc giữ một modular monolith có ranh giới tốt là lựa chọn hợp lý để thu thập bằng chứng.

## 8. Lộ trình từ monolith sang modular monolith rồi tách có chọn lọc

Không cần coi ba mô hình là ba giai đoạn bắt buộc. Tuy vậy, khi hệ thống đang là monolith khó thay đổi, lộ trình tăng tính mô-đun trước thường giúp giảm rủi ro:

**Bước 1 — Lập bản đồ miền và phụ thuộc.** Xác định ai sở hữu chức năng và dữ liệu; vẽ luồng transaction, lời gọi trực tiếp, các bảng bị truy cập chéo và điểm nóng trong vận hành.

**Bước 2 — Dựng ranh giới module.** Đưa nghiệp vụ vào các package/module theo bounded context; công bố interface rõ; hạn chế import sang internal; bổ sung kiểm tra dependency tự động nếu phù hợp.

**Bước 3 — Tách quyền sở hữu dữ liệu.** Mỗi module có repository/schema/bảng riêng và không ghi sang dữ liệu của module khác. Thiết kế DTO/query interface hoặc event để cung cấp dữ liệu cần thiết. Thực hiện schema migration có kế hoạch.

**Bước 4 — Làm rõ sự kiện và transaction.** Chỉ ra thao tác cần strong consistency, thao tác có thể async và cách khôi phục nếu một bước thất bại. Thiết kế idempotency, outbox và state machine khi ranh giới có thể bị phân tán.

**Bước 5 — Tách một service có lý do định lượng.** Chọn miền ít phụ thuộc, có nhu cầu triển khai hoặc scale riêng rõ ràng; dùng Strangler Fig để chuyển dần lưu lượng qua adapter/API. Một module có nhiều join xuyên bảng thường là ứng viên tách kém.

**Bước 6 — Chạy song song, đo và điều chỉnh.** Áp dụng canary, quan sát latency, tỉ lệ lỗi, chi phí vận hành và mức độc lập release. Chỉ tách tiếp nếu lợi ích được chứng minh; giữ những phần khác trong modular monolith nếu chúng vận hành tốt.

### Những thay đổi cần dự trù khi tách dịch vụ

| Trước khi tách | Sau khi tách |
|---|---|
| Gọi hàm nội bộ | API versioned, timeout, lỗi mạng, auth service-to-service |
| Một transaction DB | Transaction cục bộ + workflow/event + bù trừ nếu cần |
| Join bảng trực tiếp | API composition, event projection hoặc read model |
| Một pipeline | Pipeline và rollout riêng, contract compatibility |
| Debug trong một tiến trình | Trace ID xuyên dịch vụ, logs/metrics phân tán |
| Một mô hình quyền truy cập DB | Mỗi service kiểm soát truy cập dữ liệu riêng |
| Refactor đồng thời một repository | Thay đổi schema/contract theo hướng tương thích tiến/lùi |

## 9. Các anti-pattern cần tránh

**Big Ball of Mud:** monolith có mọi lớp gọi trực tiếp vào nhau, dữ liệu không có owner. Vấn đề ở cấu trúc phụ thuộc; tăng số service không tự sửa được.

**Distributed monolith:** nhiều service nhưng phải deploy cùng lúc, gọi chuỗi đồng bộ dài, chia sẻ schema hoặc phá hợp đồng là làm hỏng toàn hệ thống. Hệ thống nhận toàn bộ chi phí phân tán mà thiếu lợi ích tự chủ.

**Service quá nhỏ theo bảng:** dịch vụ ProductService, PriceService, CategoryService,... liên tục gọi nhau cho một yêu cầu đơn giản. Đây là dấu hiệu chia sai theo thực thể/kỹ thuật thay vì khả năng nghiệp vụ.

**Shared database với quyền ghi chéo:** service A cập nhật thẳng bảng của B, khiến schema migration của B cần sự cho phép của A. Nên công bố contract và quản lý data ownership.

**Đồng bộ mọi thứ:** mỗi bước nghiệp vụ gọi HTTP nối tiếp, đẩy p99 latency và rủi ro timeout tăng nhanh. Chỉ đồng bộ những gì người dùng cần kết quả tức thời; cân nhắc xử lý bất đồng bộ cho bước phù hợp.

**Eventual consistency không có trạng thái:** phát event rồi giả định mọi thứ sẽ thành công, không ghi trạng thái đang chờ hoặc lỗi. Nên dùng workflow có trạng thái, retry an toàn, dead-letter handling và đối soát.

**Tách dịch vụ chỉ theo trào lưu:** không có số liệu về chi phí release chung, nút thắt tải hay ownership. Kết quả thường là tăng chi phí mà không cải thiện lead time hay độ tin cậy.

## 10. Thực hành thiết kế một hệ thống mẫu

Giả sử có yêu cầu:

- 8 kỹ sư, hai nhóm phối hợp chặt, một sản phẩm có 30.000 người dùng hoạt động mỗi ngày.
- Các module: Accounts, Catalog, Orders, Inventory, Payments, Notifications.
- Mục tiêu: thay đổi nghiệp vụ nhanh, giữ quy trình đặt hàng nhất quán, ngân sách vận hành hạn chế.
- Notifications gửi email qua nhà cung cấp ngoài, có thể trễ vài phút; Catalog đọc nhiều, Orders ghi ít hơn.

Một thiết kế khởi đầu hợp lý là **modular monolith**:

~~~text
                        [Web / Mobile]
                              |
                    [Application / API]
                              |
       +-----------+----------+-----------+-----------+
       |           |          |           |           |
    Accounts     Catalog    Orders     Inventory    Payments
                              |
                       [Domain Events]
                              |
                         Notifications
                              |
                        [Email Provider]

     Một artifact triển khai; module giữ ownership rõ.
     Có thể có queue/worker cho email mà chưa cần tách mọi module.
~~~

Gợi ý quyết định triển khai:

1. Tách package/module theo năng lực; không cho Orders truy cập trực tiếp bảng Inventory.
2. Định nghĩa transaction và invariant cho đơn hàng và giữ kho; tiền thanh toán ngoài cần idempotency và đối soát.
3. Dùng async cho email; có retry và log trạng thái gửi.
4. Tối ưu Catalog bằng index/cache, nhân bản ứng dụng nếu tải tăng; đo trước khi tạo Catalog Service riêng.
5. Theo dõi lead time thay đổi, tần suất release, lỗi triển khai, p95/p99 latency và chi phí vận hành.
6. Khi một nhóm cần phát hành Catalog thường xuyên mà không ảnh hưởng Checkout, hoặc tải Catalog khác biệt rõ, đánh giá tách Catalog/Search dựa trên bằng chứng.

**Ngược lại:** nếu hệ thống có 10 nhóm độc lập, mỗi nhóm release nhiều lần/ngày, các ranh giới nghiệp vụ ổn định và đầy đủ nền tảng vận hành, xây một số microservices theo bounded context ngay từ đầu có thể hợp lý. Không cần bắt đầu bằng một monolith “cho đúng quy trình”.

## 11. Cách đánh giá kiến trúc sau khi vận hành

Không chỉ nhìn số container/service. Hãy xem các thước đo gắn với mục tiêu:

| Mục tiêu | Tín hiệu đo lường |
|---|---|
| Thay đổi nhanh hơn | Lead time từ commit đến production; tần suất phát hành; số đội phải phối hợp cho một thay đổi |
| Độ tin cậy cao hơn | SLO đạt/không đạt; error budget; tỉ lệ lỗi request; thời gian phát hiện và phục hồi sự cố |
| Hiệu năng tốt hơn | p95/p99 latency theo hành trình người dùng; throughput; bão hòa CPU/memory/connection |
| Scale kinh tế hơn | Chi phí hạ tầng trên giao dịch; phần tài nguyên nhàn rỗi; số replica phải tăng cho mỗi tải tăng |
| Dữ liệu chính xác hơn | Số giao dịch cần đối soát; sự kiện xử lý trùng; độ trễ đồng bộ; số tình huống bù trừ thất bại |
| Quyền tự chủ thực tế | Tỉ lệ deploy độc lập; số lần thay đổi contract gây vỡ; mức độ ownership của đội |

Nếu sau khi tách dịch vụ, lead time không giảm, incident tăng và các đội vẫn phải phát hành đồng thời, hãy xem lại ranh giới và kiểu phụ thuộc thay vì tiếp tục tách nhỏ.

## 12. Kết luận và nguyên tắc ghi nhớ

- **Monolith** tối ưu cho sự đơn giản triển khai và giao tiếp nội bộ; dễ bắt đầu nhưng cần kiểm soát coupling khi hệ thống lớn.
- **Modular monolith** dùng ranh giới nghiệp vụ rõ ràng trong cùng ứng dụng; thường cân bằng tốt giữa khả năng thay đổi và độ phức tạp vận hành.
- **Microservices** phát huy giá trị ở độc lập triển khai, scale và quyền sở hữu của các nhóm; đổi lại phải giải quyết các vấn đề cố hữu của hệ thống phân tán.

Lựa chọn tốt bắt đầu từ **ranh giới nghiệp vụ, yêu cầu nhất quán, số liệu tải, cấu trúc đội ngũ và năng lực vận hành**. Hãy tối ưu sự dễ thay đổi của toàn hệ thống, không tối ưu số lượng dịch vụ. Khi chưa có bằng chứng đủ mạnh để phân tán, một modular monolith có module API, data ownership và kiểm soát phụ thuộc là nền tảng vững chắc; khi có nhu cầu rõ ràng, tách từng dịch vụ với dữ liệu và vận hành được thiết kế phù hợp.