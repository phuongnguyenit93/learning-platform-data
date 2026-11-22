# Kiến trúc vi dịch vụ (Microservices) là gì?

## 1. Khái niệm

**Microservices (kiến trúc vi dịch vụ)** là cách tổ chức một hệ thống phần mềm thành nhiều dịch vụ tương đối nhỏ, mỗi dịch vụ đảm nhiệm một **năng lực nghiệp vụ rõ ràng**, có thể phát triển, triển khai và vận hành độc lập ở mức phù hợp. Các dịch vụ hợp tác qua những hợp đồng giao tiếp được công bố, thường là API đồng bộ hoặc thông điệp/sự kiện bất đồng bộ.

Chữ “micro” không quy định một con số dòng code, số lớp Java hay số endpoint. Điểm cốt lõi là **ranh giới trách nhiệm và mức độ độc lập**: một thay đổi thuộc quản lý đơn hàng lý tưởng không buộc phải sửa, build và triển khai toàn bộ hệ thống thanh toán, danh mục sản phẩm hay thông báo.

Một dịch vụ trong kiến trúc này thường có:

- **Trách nhiệm nghiệp vụ riêng**: ví dụ quản lý đơn hàng, thanh toán, tồn kho, định danh khách hàng.
- **Hợp đồng giao tiếp rõ ràng**: REST, gRPC, message/event hoặc cách tương đương; người dùng dịch vụ phụ thuộc vào hợp đồng thay vì cấu trúc code nội bộ.
- **Quyền sở hữu dữ liệu và quy tắc nghiệp vụ**: dịch vụ khác không tự ý đọc/ghi bảng dữ liệu nội bộ của nó.
- **Vòng đời triển khai tương đối độc lập**: có pipeline, version, khả năng mở rộng và rollback riêng khi tổ chức, hạ tầng cho phép.
- **Khả năng quan sát và ứng phó lỗi**: log, metrics, tracing, timeout, retry và các biện pháp an toàn vì giao tiếp giờ vượt ranh giới tiến trình.

Microservices là một **lựa chọn kiến trúc phân tán**. Chia thành nhiều ứng dụng chạy riêng chỉ là biểu hiện bên ngoài; nếu mọi ứng dụng vẫn dùng chung schema, triển khai đồng thời và thay đổi dây chuyền thì hệ thống có thể chỉ là **distributed monolith** (đơn khối bị phân tán).

## 2. Hình dung qua một hệ thống bán hàng

Giả sử một nền tảng thương mại điện tử có bốn năng lực chính:

| Dịch vụ | Trách nhiệm chính | Ví dụ dữ liệu sở hữu |
| --- | --- | --- |
| Catalog Service | Công bố thông tin sản phẩm, danh mục, giá niêm yết | Sản phẩm, danh mục, thuộc tính hiển thị |
| Order Service | Tiếp nhận đơn, quản lý trạng thái và quy tắc đơn hàng | Đơn hàng, dòng hàng, lịch sử trạng thái |
| Inventory Service | Kiểm tra, giữ chỗ và giải phóng tồn kho | Tồn kho, lượng đã giữ, giao dịch kho |
| Payment Service | Tạo yêu cầu thanh toán, ghi nhận kết quả và hoàn tiền | Giao dịch thanh toán, trạng thái xử lý |

Mỗi dịch vụ có thể là một ứng dụng riêng. Giao diện web/mobile chỉ gọi các API cần thiết, thường thông qua một API Gateway hoặc lớp Backend for Frontend (BFF). Một message broker có thể chuyển các sự kiện giữa dịch vụ.

~~~mermaid
flowchart LR
    UI["Web / Mobile"] --> GW["API Gateway / BFF"]
    GW --> CAT["Catalog Service"]
    GW --> ORD["Order Service"]
    ORD <-->|"API theo hợp đồng"| INV["Inventory Service"]
    ORD -->|"OrderCreated"| BUS[("Event Broker")]
    BUS --> PAY["Payment Service"]
    ORD --> ODB[("Order DB")]
    INV --> IDB[("Inventory DB")]
    PAY --> PDB[("Payment DB")]
    CAT --> CDB[("Catalog DB")]
~~~

Đây là **sơ đồ minh họa**, không phải mẫu cố định. Một hệ thống thực tế có thể dùng giao tiếp bất đồng bộ cho đặt chỗ tồn kho, dùng một workflow coordinator, hoặc gộp một số năng lực khi quy mô còn nhỏ. Không phải mọi lời gọi đều cần đi qua gateway và không phải mỗi dịch vụ phải có một máy chủ vật lý.

### Một hành trình đặt hàng

Một luồng đơn giản có thể diễn ra như sau:

1. Khách gửi yêu cầu tạo đơn đến Order Service; Order Service tạo đơn ở trạng thái **PENDING** và trả về mã đơn.
2. Order Service yêu cầu Inventory Service **giữ chỗ tồn kho** cho mã đơn. Inventory Service kiểm tra và cập nhật tồn kho trong giao dịch nội bộ của chính nó.
3. Khi giữ chỗ thành công, hệ thống khởi tạo thanh toán qua Payment Service. Payment Service ghi nhận kết quả từ nhà cung cấp thanh toán theo cách có thể xử lý callback lặp.
4. Nếu thanh toán thành công, Order Service chuyển đơn sang **CONFIRMED**. Nếu không thành công hoặc hết hạn, quy trình yêu cầu giải phóng phần tồn kho đã giữ và chuyển đơn sang trạng thái thất bại phù hợp.

Quy trình đi qua nhiều dịch vụ nên không thể coi như một giao dịch SQL duy nhất. Nếu bước thanh toán thất bại sau khi giữ chỗ tồn kho thành công, hệ thống cần một **hành động bù trừ** và theo dõi trạng thái trung gian. Đây là một trong những lý do microservices đòi hỏi thiết kế vận hành kỹ hơn ứng dụng đơn khối.

## 3. “Service” là một ranh giới nghiệp vụ, không phải một lớp code

Một hiểu nhầm phổ biến là cứ tách mỗi entity, mỗi bảng hoặc mỗi controller thành một microservice. Cách chia như vậy dễ tạo nhiều lời gọi mạng cho một thao tác vốn chỉ cần một giao dịch nội bộ.

Hướng thiết kế tốt hơn là xét **business capability** và **bounded context**:

- **Business capability**: tổ chức cần làm được việc gì, chẳng hạn tính phí vận chuyển, xử lý thanh toán hay quản lý tồn kho.
- **Bounded context**: phạm vi trong đó một mô hình nghiệp vụ và thuật ngữ có nghĩa nhất quán. “Sản phẩm” trong Catalog có thể là thông tin bán hàng, nhưng trong Inventory chủ yếu là SKU và số lượng sẵn có.
- **Độ kết dính cao (high cohesion)**: các quy tắc thay đổi cùng nhau nên nằm gần nhau, trong cùng dịch vụ khi phù hợp.
- **Mức phụ thuộc thấp (low coupling)**: một thay đổi nội bộ của dịch vụ A không làm dịch vụ B phải sửa theo nếu hợp đồng vẫn ổn định.

Ví dụ, **Order Service** có thể lưu một bản chụp tên sản phẩm và giá đã chốt tại thời điểm mua để giữ lịch sử hóa đơn. Nó không cần gọi Catalog Service mỗi khi hiển thị đơn hàng cũ, và không nên sửa bảng Catalog để “đồng bộ” giá giao dịch.

Một hệ thống mới không nhất thiết tìm được ranh giới chính xác ngay từ đầu. Nên theo dõi nơi các yêu cầu thường thay đổi cùng nhau, ai sở hữu quy tắc, giao dịch nào cần tính nguyên tử, và lời gọi giữa các phần nào có tần suất cao trước khi quyết định tách.

## 4. Các đặc tính đặc trưng

| Khía cạnh | Ý nghĩa thực tế | Điều cần chú ý |
| --- | --- | --- |
| Triển khai độc lập | Có thể phát hành Order Service mà không triển khai lại Catalog Service khi hợp đồng không đổi | Pipeline, versioning, migration và tương thích ngược phải đáng tin cậy |
| Sở hữu dữ liệu | Mỗi dịch vụ kiểm soát dữ liệu và invariant của mình | Không join trực tiếp qua database dịch vụ khác; cần API, event hoặc read model |
| Giao tiếp qua hợp đồng | Các nhóm trao đổi bằng API và schema sự kiện đã thống nhất | Quản lý tương thích, timeout, lỗi và thay đổi schema |
| Mở rộng theo nhu cầu | Tăng số instance của dịch vụ chịu tải cao | Bottleneck có thể nằm ở database, broker hoặc dịch vụ phụ thuộc |
| Khoanh vùng lỗi | Sự cố của một dịch vụ có thể không kéo toàn hệ thống xuống | Phải thiết kế timeout, bulkhead, degraded mode và giới hạn tài nguyên |
| Tự chủ của nhóm | Một nhóm có thể chịu trách nhiệm xuyên suốt cho một hoặc vài dịch vụ | Cần chuẩn chung về bảo mật, logging, vận hành và sở hữu on-call |
| Đa dạng công nghệ có kiểm soát | Mỗi dịch vụ có thể chọn storage/runtime thích hợp | Quá nhiều stack gây tăng chi phí kỹ năng và vận hành |

**Độc lập là mục tiêu về mức độ, không phải lời bảo đảm tuyệt đối.** Một thay đổi lớn ở hợp đồng giữa dịch vụ vẫn có thể cần phối hợp, và một hệ thống có dependency đồng bộ chằng chịt vẫn có thể gặp sự cố dây chuyền.

## 5. Giao tiếp giữa các microservice

### 5.1. Đồng bộ: request/response

Ví dụ Order Service gọi Inventory Service qua HTTP hoặc gRPC để giữ hàng:

~~~http
POST /v1/reservations
Content-Type: application/json
Idempotency-Key: reserve-order-8421

{
  "orderId": "8421",
  "items": [
    { "sku": "BK-01", "quantity": 2 }
  ]
}
~~~

Một phản hồi thành công có thể chứa mã đặt chỗ và hạn giữ hàng. Phản hồi hết hàng nên là một kết quả nghiệp vụ rõ nghĩa; timeout mạng lại là trạng thái **chưa biết chắc kết quả**. Khi timeout, phía gọi không nên mặc định “chưa xử lý” rồi tạo một đặt chỗ khác.

Ưu điểm của giao tiếp đồng bộ là dễ hiểu và thuận tiện khi cần kết quả ngay. Nhược điểm là thời gian phản hồi và độ sẵn sàng phụ thuộc vào dịch vụ được gọi. Một chuỗi A → B → C → D khiến request đầu vào chịu rủi ro latency và lỗi của cả chuỗi.

Các nguyên tắc thiết yếu: đặt **timeout**, dùng retry có giới hạn và backoff khi thích hợp, hỗ trợ idempotency, không retry bừa mọi lỗi, giới hạn tài nguyên chờ và có cách trả trạng thái tạm thời khi dependency không sẵn sàng.

### 5.2. Bất đồng bộ: message/event

Một dịch vụ có thể công bố sự kiện biểu thị **sự thật đã xảy ra**:

~~~json
{
  "eventId": "evt-391",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-01-15T10:30:00Z",
  "orderId": "8421",
  "customerId": "c-17",
  "totalAmount": 250000,
  "currency": "VND"
}
~~~

Shipping Service hoặc Notification Service có thể nhận sự kiện và thực hiện phần việc của mình. Bên phát không cần chờ tất cả consumer xử lý trước khi trả lời cho khách hàng.

Ưu điểm: giảm phụ thuộc thời điểm chạy, hấp thụ tải theo hàng đợi, hỗ trợ workflow dài. Đổi lại, hệ thống phải xử lý thông điệp trễ, trùng, lệch thứ tự, thất bại, retry, dead-letter queue và schema version. **“At least once” thường dẫn đến khả năng xử lý lặp**, vì vậy consumer nên idempotent; không dựa vào giả định mỗi event chỉ tới đúng một lần.

Cần phân biệt:

- **Command**: yêu cầu một bên thực hiện hành động, chẳng hạn “ReserveInventory”.
- **Event**: thông báo điều đã xảy ra, chẳng hạn “InventoryReserved”.
- **Query**: lấy dữ liệu hoặc trạng thái, không hàm ý tạo tác dụng phụ.

Không có quy tắc mọi giao tiếp đều phải dùng message broker. Chọn đồng bộ khi cần phản hồi trực tiếp, bất đồng bộ khi phù hợp với xử lý tách thời điểm, và tránh tạo pipeline sự kiện chỉ để truyền dữ liệu đơn giản.

## 6. Dữ liệu và tính nhất quán

### 6.1. Database per service là nguyên tắc sở hữu, không nhất thiết một server riêng

Mỗi dịch vụ là nơi duy nhất được quyền thay đổi dữ liệu mà nó sở hữu. Hai dịch vụ **có thể cùng dùng một hạ tầng database** trong giai đoạn đầu, nhưng nên tách schema/quyền truy cập và cấm phụ thuộc trực tiếp vào bảng nội bộ của nhau. Sở hữu dữ liệu không nhất thiết đồng nghĩa mỗi dịch vụ có một máy chủ database riêng.

Ví dụ Order Service không tự chạy truy vấn SQL vào bảng tồn kho của Inventory Service. Nếu cần số lượng tồn hiện tại, nó gọi API của Inventory; nếu cần báo cáo tổng hợp nhanh, hệ thống có thể xây read model từ các event.

### 6.2. Không còn một giao dịch ACID xuyên toàn bộ quy trình

Trong một monolith với một database, nhiều bước có thể chạy trong một transaction. Trong microservices, mỗi dịch vụ thường commit giao dịch của riêng mình. Kết quả toàn hệ thống có thể **nhất quán cuối cùng (eventual consistency)**: thông tin cập nhật ở các dịch vụ khác nhau tại những thời điểm khác nhau.

Điều này đòi hỏi nói rõ:

- Trạng thái nào được xem là **đã xác nhận** với người dùng, trạng thái nào còn đang xử lý?
- Nếu sự kiện đã phát nhưng chưa được consumer nhận thì màn hình trả về điều gì?
- Hệ thống kiểm tra và sửa lệch dữ liệu như thế nào?
- Những bất biến nào bắt buộc được giữ **ngay trong một giao dịch cục bộ**, ví dụ không giữ số lượng âm?

Tránh hiển thị “Thanh toán thành công” chỉ vì đã gửi yêu cầu thanh toán; cần dựa vào kết quả được xác nhận và lưu bền vững.

### 6.3. Saga, Outbox và idempotency

**Saga** quản lý chuỗi giao dịch cục bộ với các bước tiếp theo và hành động bù trừ khi lỗi. Có thể tổ chức bằng *orchestration* (một coordinator điều khiển workflow) hoặc *choreography* (các bên phản ứng theo sự kiện). Saga **không tự động rollback được mọi tác dụng ngoài đời thực**; hoàn tiền, gửi email và giao hàng có ràng buộc nghiệp vụ riêng.

**Transactional Outbox** giảm rủi ro tình huống “đã commit dữ liệu nhưng quên phát sự kiện”: dịch vụ ghi thay đổi nghiệp vụ và bản ghi outbox trong **cùng transaction cục bộ**, sau đó một publisher đọc outbox để gửi broker. Vẫn cần chống event trùng ở consumer.

**Idempotency** nghĩa là xử lý lặp cùng một yêu cầu không tạo thêm tác dụng ngoài ý muốn. Ví dụ hai request thanh toán cùng một idempotency key phải tham chiếu cùng kết quả nghiệp vụ, thay vì trừ tiền hai lần. Cần thiết kế khóa, phạm vi lưu, thời hạn, trạng thái đang xử lý và cách trả kết quả lặp một cách rõ ràng.

Ba kỹ thuật trên giải quyết những vấn đề khác nhau, thường được kết hợp khi giao dịch đi qua nhiều dịch vụ.

## 7. Triển khai và vận hành một hệ thống phân tán

Microservices chuyển một phần độ phức tạp từ code trong một tiến trình sang **mạng, hạ tầng và quy trình vận hành**. Để khai thác lợi ích triển khai độc lập, tổ chức thường cần:

1. **Build và CI/CD riêng cho từng dịch vụ**: kiểm thử tự động, version artifact, migration an toàn, chiến lược rollback, staging/canary khi cần.
2. **Quản lý cấu hình và bí mật**: tách config khỏi binary, cấp secret theo quyền tối thiểu; không hardcode mật khẩu hay token trong source.
3. **Service discovery/routing**: các instance có thể thay đổi địa chỉ; client cần cơ chế tìm hoặc truy cập qua endpoint ổn định.
4. **Health checks**: phân biệt ứng dụng còn chạy với việc nó sẵn sàng nhận traffic; readiness không nên phụ thuộc cứng vào mọi hệ thống bên ngoài.
5. **Giám sát tổng thể**: quan sát cả đường đi từ request đầu vào qua các dịch vụ, không chỉ CPU của một container.
6. **Quản trị hợp đồng**: API versioning, contract test, chính sách loại bỏ trường cũ, tương thích giữa producer và consumer.
7. **Quản lý sự cố**: phân quyền sở hữu, cảnh báo dựa trên triệu chứng, hướng dẫn khắc phục và cơ chế rollback/giảm chức năng.

Container, Kubernetes, service mesh, API gateway và message broker **có thể hỗ trợ** nhưng không phải điều kiện định nghĩa microservices. Một hệ thống có hàng chục container mà vẫn phải deploy đồng loạt có thể không đạt lợi ích kiến trúc mong muốn.

### 7.1. Bốn nhóm tín hiệu quan sát

- **Logs có cấu trúc**: hành động, kết quả, nguyên nhân, service và correlation/trace ID; không ghi token, mật khẩu hay thông tin nhạy cảm không cần thiết.
- **Metrics**: request rate, latency, error rate, queue lag, saturation, số lượng retry, tỷ lệ workflow thất bại.
- **Distributed tracing**: nối các span qua nhiều dịch vụ để biết request chậm ở đâu; chuyển trace context qua HTTP và thông điệp.
- **Business metrics**: đơn PENDING quá hạn, tiền đã thu nhưng đơn chưa CONFIRMED, lượng giữ kho chưa giải phóng.

Ví dụ: một request đặt hàng trả chậm không nhất thiết vì Order Service xử lý lâu; trace có thể cho thấy Payment Service chờ một API bên ngoài. Metrics và trace giúp định vị độ trễ, còn business metrics giúp phát hiện hệ thống “trả HTTP 200 nhưng nghiệp vụ chưa hoàn tất”.

### 7.2. Resilience: hạn chế hiệu ứng domino

Khi Inventory Service chậm, Order Service phải tránh giữ vô hạn thread/connection. Các kỹ thuật hay dùng gồm **timeout**, **circuit breaker**, **bulkhead**, **rate limiting**, **load shedding**, retry có backoff và jitter, dead-letter queue, cùng khả năng xử lý lại có kiểm soát.

Cần đặc biệt lưu ý: retry dễ làm tăng tải đúng lúc hệ thống yếu nhất. Retry một POST có tác dụng phụ khi chưa có idempotency key có thể tạo đơn hoặc giao dịch trùng. Circuit breaker không thay thế xử lý lỗi nghiệp vụ; nó chỉ giúp quyết định tạm ngừng gửi request tới dependency đang gặp sự cố.

### 7.3. Bảo mật giữa các dịch vụ

Ngoài xác thực người dùng tại biên, cần xác định **service identity**, xác thực và phân quyền giữa dịch vụ, mã hóa kết nối, kiểm tra input, xác minh nguồn event và quản lý secret. Không xem mạng nội bộ là mặc nhiên đáng tin cậy. Token/claims nên mang vừa đủ quyền và thời hạn; ghi log phải tránh lộ dữ liệu nhạy cảm.

## 8. Microservices khác monolith và modular monolith thế nào?

| Tiêu chí | Monolith | Modular monolith | Microservices |
| --- | --- | --- | --- |
| Đơn vị triển khai | Thường một ứng dụng | Một ứng dụng có module tách rõ | Nhiều dịch vụ có thể triển khai riêng |
| Giao tiếp nội bộ | Gọi hàm trong cùng tiến trình | Gọi qua ranh giới module nội bộ | Chủ yếu qua mạng/message |
| Ranh giới code | Có thể lẫn lộn nếu thiếu kỷ luật | Có contract và encapsulation giữa module | Mỗi dịch vụ có codebase/runtime boundary |
| Dữ liệu | Thường một database, nhiều phần cùng truy cập | Có thể chung database nhưng tách quyền theo module | Dịch vụ sở hữu dữ liệu riêng |
| Transaction xuyên tính năng | Thuận lợi hơn nếu chung database | Thuận lợi trong ranh giới app | Cần điều phối nhiều giao dịch cục bộ |
| Triển khai và scale | Thường theo cả ứng dụng | Thường theo cả ứng dụng | Có thể chọn dịch vụ cần scale/deploy |
| Chi phí vận hành ban đầu | Thường thấp hơn | Thường thấp đến trung bình | Thường cao hơn do tính phân tán |

**Monolith không đồng nghĩa thiết kế kém.** Một monolith được tổ chức tốt, kiểm thử được và có module rõ ràng có thể là lựa chọn tối ưu trong thời gian dài. **Modular monolith** đặc biệt hữu ích khi nghiệp vụ đang thay đổi nhanh, đội ngũ nhỏ và chưa cần scale/triển khai theo từng năng lực; các ranh giới module tốt cũng tạo tiền đề cho việc tách dịch vụ sau này.

Microservices có lợi thế khi một tổ chức thật sự cần tự chủ về phát hành, quy mô và sở hữu nghiệp vụ ở nhiều nhóm. Tuy nhiên, việc tách dịch vụ luôn phải cân đối với latency, độ phức tạp dữ liệu, chi phí vận hành và kỹ năng đội ngũ.

## 9. Khi nào nên và chưa nên chọn microservices?

**Dấu hiệu nên cân nhắc:**

- Hệ thống có nhiều năng lực nghiệp vụ đủ rõ và tương đối độc lập, mỗi năng lực có nhịp thay đổi khác nhau.
- Nhiều nhóm phát triển cần phát hành song song, giảm xung đột trong một pipeline triển khai chung.
- Một số thành phần có nhu cầu mở rộng hoặc yêu cầu cô lập tài nguyên rất khác phần còn lại.
- Tổ chức có năng lực CI/CD, quan sát, bảo mật, vận hành sự cố và kiểm thử hợp đồng.
- Chi phí phối hợp của kiến trúc hiện tại đã cao hơn chi phí tăng thêm khi phân tán.

**Dấu hiệu nên thận trọng:**

- Sản phẩm mới, mô hình nghiệp vụ còn biến động liên tục, chưa xác định được ranh giới ổn định.
- Nhóm nhỏ, ít người vận hành; một ứng dụng có module tốt đáp ứng đủ yêu cầu.
- Giao dịch nghiệp vụ cần tính nguyên tử trên nhiều phần và chưa có giải pháp nhất quán phù hợp.
- Mọi thay đổi thường chạm đồng thời tất cả “service”, hoặc hệ thống chỉ hoạt động khi tất cả service đều sẵn sàng.
- Hạ tầng quan sát và tự động hóa chưa đủ, làm mỗi lỗi mạng trở thành sự cố khó chẩn đoán.

Câu hỏi quyết định nên là: **vấn đề cụ thể nào mà việc triển khai độc lập và tách quyền sở hữu giải quyết được, và liệu lợi ích đó có lớn hơn chi phí phân tán?** “Công ty lớn dùng microservices” hoặc “muốn dùng Kubernetes” tự nó chưa phải lý do kiến trúc.

## 10. Những sai lầm phổ biến

1. **Tách theo bảng/entity**: tạo Product Service, ProductImage Service, ProductPrice Service dù chúng luôn thay đổi và giao dịch cùng nhau. Kết quả là nhiều lời gọi mạng, khó giữ nhất quán.
2. **Chia quá nhỏ quá sớm**: phải điều phối hàng chục bản deploy khi sản phẩm chưa rõ nghiệp vụ. Hãy đo mức độ độc lập thực tế trước khi tách.
3. **Dùng chung database như API ngầm**: một dịch vụ sửa schema làm nhiều dịch vụ khác hỏng. Tách quyền sở hữu, cung cấp contract rõ ràng.
4. **Gọi đồng bộ dây chuyền**: một API cần chờ nhiều dependency, tăng latency và nguy cơ lỗi lan truyền. Xem xét tổng hợp dữ liệu, cache/read model, event hoặc thiết kế lại ranh giới.
5. **Nhầm “deploy độc lập” với “không cần tương thích”**: thay đổi breaking API làm consumer cũ thất bại. Áp dụng backward compatibility và contract testing.
6. **Bỏ qua idempotency và thông điệp trùng**: retry gây thanh toán hoặc giữ hàng hai lần. Thiết kế xử lý lặp như trường hợp bình thường.
7. **Không có tracing/correlation ID**: sự cố đi qua nhiều dịch vụ nhưng không thể lần ra luồng. Đầu tư khả năng quan sát trước khi số dịch vụ tăng mạnh.
8. **Tự xây hạ tầng phức tạp không cần thiết**: thêm broker, mesh, orchestrator khi chưa có nhu cầu rõ. Mỗi thành phần là một hệ thống phải vận hành, giám sát và bảo mật.
9. **Không có chủ sở hữu dịch vụ**: không ai chịu trách nhiệm từ code đến production. Cần ownership và quy trình sự cố minh bạch.
10. **Cho rằng bất đồng bộ luôn là eventual consistency chấp nhận được**: một số bất biến vẫn phải giữ tức thời trong phạm vi dịch vụ, và trải nghiệm người dùng cần mô tả chính xác trạng thái.

## 11. Cách tiếp cận thực tế khi bắt đầu

Thay vì tách ngay toàn bộ hệ thống, có thể đi theo các bước có chủ đích:

**Bước 1 — Vẽ năng lực nghiệp vụ và ranh giới.** Phân tích use case, thuật ngữ, dữ liệu chủ sở hữu, những phần thay đổi cùng nhau. Nhận diện transaction cần nguyên tử và đường đi request quan trọng.

**Bước 2 — Tạo module rõ ràng.** Ngay cả khi tất cả còn chạy trong một ứng dụng, áp dụng API nội bộ, che giấu chi tiết lưu trữ và kiểm thử hợp đồng giữa module. Mục tiêu là giảm coupling trước khi đưa mạng vào giữa.

**Bước 3 — Chọn một ứng viên tách có giá trị rõ.** Ví dụ dịch vụ thông báo, tìm kiếm hoặc xử lý ảnh thường có nhu cầu scale/lifecycle khác. Ứng viên tốt có quyền sở hữu dữ liệu rõ và ít giao dịch đồng bộ với lõi.

**Bước 4 — Thiết lập nền tảng tối thiểu.** Có pipeline deploy, health check, logs/metrics/tracing, secret management, timeout, versioning, rollback và quy trình ứng cứu.

**Bước 5 — Tách bằng hợp đồng ổn định.** Xác định API/event, chiến lược migration dữ liệu, xử lý lỗi, idempotency. Có thể dùng *strangler pattern*: chuyển dần từng luồng sang dịch vụ mới thay vì viết lại đồng loạt.

**Bước 6 — Đo kết quả và điều chỉnh.** Theo dõi deployment frequency, thời gian đưa thay đổi lên production, tỷ lệ lỗi phát hành, lead time, latency, sự cố liên dịch vụ và chi phí vận hành. Nếu tách xong vẫn phải release đồng loạt, cần xem lại ranh giới.

### Minh họa ranh giới code với Spring Boot

Trong hệ thống Java/Spring Boot, hai ứng dụng chạy riêng có thể là Order Service và Inventory Service. Order Service định nghĩa một interface nghiệp vụ, còn adapter HTTP thực hiện lời gọi; logic đặt hàng không phụ thuộc trực tiếp vào HTTP client:

~~~java
public interface InventoryReservationPort {
    ReservationResult reserve(String orderId, List<OrderItem> items);
}
~~~

Implementation có thể dùng REST client, gRPC hoặc thông điệp; thay đổi adapter không nên làm hỏng quy tắc nghiệp vụ của Order Service. Ở Inventory Service, một endpoint tiếp nhận yêu cầu, kiểm tra quyền, idempotency và gọi application service để thực hiện transaction cục bộ.

Điều cần học ở ví dụ này là **separation of concerns và ownership**; việc thêm annotation Spring, Dockerfile hay Kubernetes Deployment **không tự động** biến thiết kế thành microservices tốt. Quy mô triển khai cụ thể phụ thuộc các yêu cầu phi chức năng.

## 12. Checklist trước khi tách một microservice

Trước khi đưa một ranh giới qua mạng, nên trả lời được các câu hỏi sau:

- Dịch vụ chịu trách nhiệm cho **năng lực nghiệp vụ** nào, ai là chủ sở hữu?
- Những dữ liệu và invariant nào thuộc dịch vụ? Có chỗ nào phải join hoặc ghi chéo database hay không?
- Hợp đồng API/event là gì? Làm sao thay đổi mà consumer cũ vẫn hoạt động?
- Dependency nào bắt buộc đồng bộ, dependency nào có thể xử lý bất đồng bộ?
- Nếu gọi timeout hoặc message bị lặp/trễ thì nghiệp vụ ra sao? Đã có idempotency và bù trừ chưa?
- Trạng thái trung gian nào người dùng có thể nhìn thấy? SLA/latency và yêu cầu nhất quán là gì?
- Khi dịch vụ hỏng, hệ thống giảm chức năng thế nào để không gây lỗi dây chuyền?
- Nhóm có thể deploy, quan sát, rollback và xử lý sự cố dịch vụ riêng mà không cần phối hợp với toàn bộ hệ thống không?

Nếu phần lớn câu trả lời còn mơ hồ, việc giữ ranh giới dưới dạng module trước có thể an toàn và kinh tế hơn.

## 13. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Service boundary | Ranh giới trách nhiệm và dữ liệu của dịch vụ |
| Bounded context | Phạm vi một mô hình/thuật ngữ nghiệp vụ có nghĩa nhất quán |
| API contract | Hợp đồng đầu vào, đầu ra, hành vi lỗi và tương thích |
| Service discovery | Cơ chế tìm endpoint của service instance |
| API Gateway / BFF | Lớp truy cập từ client, có thể làm routing, auth hoặc tổng hợp dữ liệu |
| Message broker | Thành phần chuyển và lưu hàng đợi/thông điệp giữa producer và consumer |
| Eventual consistency | Các bản sao hoặc góc nhìn dữ liệu có thể lệch tạm thời rồi hội tụ |
| Saga | Chuỗi giao dịch cục bộ và hành động bù trừ cho workflow phân tán |
| Transactional Outbox | Ghi sự kiện chờ phát cùng transaction của thay đổi nghiệp vụ |
| Idempotency | Xử lý lặp yêu cầu mà không nhân đôi tác dụng nghiệp vụ |
| Distributed tracing | Theo dõi một request qua nhiều tiến trình/dịch vụ |
| Distributed monolith | Hệ thống phân tán khi triển khai nhưng vẫn phụ thuộc chặt và khó phát hành độc lập |

## 14. Tự kiểm tra hiểu biết

1. Nếu một hệ thống có 10 ứng dụng Spring Boot nhưng dùng chung schema và luôn phải deploy cùng nhau, điều gì khiến nó chưa đạt mục tiêu của microservices?
2. Vì sao một dịch vụ Order nên sở hữu trạng thái đơn hàng, còn Inventory sở hữu số lượng tồn và logic giữ chỗ?
3. Khi Order Service gọi Payment Service bị timeout, vì sao retry ngay có thể nguy hiểm? Cần bảo vệ bằng kỹ thuật gì?
4. Event “OrderConfirmed” phát thành công hai lần thì Notification Service và Shipping Service nên xử lý thế nào?
5. Trong một sản phẩm mới có ba lập trình viên, khi nào modular monolith có thể phù hợp hơn việc tách năm dịch vụ?
6. Hãy nêu một metric kỹ thuật và một metric nghiệp vụ giúp phát hiện luồng đặt hàng gặp lỗi dù API vẫn trả phản hồi thành công.

## 15. Kết luận

Microservices là kiến trúc tổ chức hệ thống quanh **năng lực nghiệp vụ, ranh giới dữ liệu và hợp đồng giao tiếp**, nhằm tạo **mức độc lập phù hợp** cho phát triển, triển khai và mở rộng. Lợi ích có thể rất lớn khi quy mô sản phẩm và tổ chức cần sự tự chủ đó. Đổi lại, hệ thống phải giải quyết bài toán phân tán: lỗi mạng, quan sát xuyên dịch vụ, nhất quán dữ liệu, thay đổi hợp đồng, bảo mật và chi phí vận hành.

Điểm cần ghi nhớ: **một dịch vụ tốt có trách nhiệm rõ ràng và ít phụ thuộc; nhiều dịch vụ chưa chắc tạo nên kiến trúc tốt**. Hãy chọn microservices vì một nhu cầu thực tế đã được nhận diện, không vì số lượng container hoặc xu hướng công nghệ.
