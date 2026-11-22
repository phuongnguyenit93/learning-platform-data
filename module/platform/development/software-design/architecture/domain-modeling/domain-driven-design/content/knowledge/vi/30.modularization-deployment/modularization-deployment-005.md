# Chi phí vận hành và phối hợp khi tách triển khai

Một hệ thống bán hàng ban đầu có thể được tổ chức thành các module Sales, Inventory, Payment và Fulfillment trong cùng một ứng dụng. Khi cần mở rộng, đội phát triển cân nhắc tách mỗi module thành một service và triển khai độc lập. Cách làm này có thể giúp từng năng lực nghiệp vụ mở rộng, phát hành và được sở hữu độc lập. Nhưng ngay khi các module chạy ở những tiến trình khác nhau, một lời gọi nội bộ trở thành giao tiếp qua mạng; một transaction cục bộ có thể trở thành quy trình nhiều bước; việc debug một request cần theo dõi qua nhiều service; và một thay đổi contract có thể cần phối hợp nhiều nhóm.

**Tách triển khai làm tăng quyền tự chủ ở một số ranh giới, đồng thời tạo thêm chi phí vận hành và phối hợp.** Vì vậy, quyết định tách service phải dựa trên lợi ích có thể đo được như tốc độ phát hành, khả năng mở rộng độc lập, cô lập lỗi, quyền sở hữu dữ liệu và sự phù hợp với cấu trúc team. Chỉ chia code thành nhiều repository hoặc container không tự động tạo ra các service độc lập.

Trong Domain-Driven Design (DDD), Bounded Context giúp xác định ranh giới mô hình và ngôn ngữ nghiệp vụ; modularization biến ranh giới đó thành module có API và quyền sở hữu rõ; deployment topology quyết định module nào chạy cùng tiến trình, module nào được triển khai riêng. Ba quyết định này liên quan nhưng không đồng nhất. Một Bounded Context có thể bắt đầu trong modular monolith và chỉ tách triển khai khi có lý do đủ mạnh.

Sau bài học này, bạn có thể:

- Phân biệt module boundary, Bounded Context, process boundary và deployment boundary.
- Giải thích các chi phí phát sinh khi chuyển từ modular monolith sang distributed services.
- Đánh giá lợi ích của triển khai độc lập so với chi phí hạ tầng, quan sát, bảo mật và hỗ trợ vận hành.
- Nhận diện network latency, partial failure, distributed transaction và eventual consistency.
- Thiết kế data ownership và contract để các service có thể tiến hóa độc lập.
- Ước lượng chi phí phối hợp giữa các team và ảnh hưởng của team topology.
- Xác định tín hiệu cho thấy một module nên được tách thành service.
- Lập lộ trình tách service từng bước và kiểm tra readiness trước production.

## 1. Phân biệt module, Bounded Context và service triển khai

Các khái niệm này thường bị dùng thay thế cho nhau, nhưng chúng mô tả những ranh giới khác nhau.

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Module | Mã nguồn và trách nhiệm nào được nhóm lại? | Package hoặc Gradle module Sales |
| Bounded Context | Mô hình và ngôn ngữ nghiệp vụ nào có hiệu lực trong ranh giới này? | Sales quản lý Order; Inventory quản lý Stock |
| Process boundary | Thành phần nào chạy trong cùng tiến trình? | Một JVM chạy Sales và Inventory |
| Deployment boundary | Thành phần nào được build, phát hành, cấu hình và rollback độc lập? | sales-service và inventory-service |
| Team ownership boundary | Nhóm nào chịu trách nhiệm thiết kế, phát hành và vận hành? | Sales team, Inventory team |

Một modular monolith có thể có nhiều Bounded Context và module nội bộ, nhưng tất cả vẫn được build và triển khai như một ứng dụng. Một microservice thường là một đơn vị triển khai độc lập, có dữ liệu và trách nhiệm vận hành riêng. Tuy nhiên, một service không tự động tương ứng chính xác với một Bounded Context; đôi khi một service phục vụ nhiều module nhỏ, hoặc một Bounded Context lớn cần nhiều process vì lý do kỹ thuật.

### Vì sao nên tách ranh giới theo từng bước?

Nếu code chưa có module boundary rõ, việc tách process sẽ mang nguyên trạng dependency rối sang mạng. Khi đó, thay vì gọi một class nội bộ, service A gọi service B qua HTTP nhưng vẫn phải biết nhiều chi tiết nội bộ của B. Hệ thống có thêm network, deployment và failure mode mà chưa có quyền tự chủ thực sự.

Một lộ trình thường hợp lý:

~~~text
Monolith khó phân chia
        |
        v
Modular Monolith
  - module ownership rõ
  - public API nội bộ
  - data access có chủ
        |
        v
Service Boundary được kiểm chứng
  - contract ổn định
  - data ownership
  - failure behavior
        |
        v
Independent Deployment
  - pipeline riêng
  - observability
  - on-call và vận hành
~~~

Modular monolith là một lựa chọn kiến trúc có chủ đích, không phải giai đoạn tạm bợ bắt buộc phải loại bỏ. Nó có thể đáp ứng lâu dài nếu nhu cầu mở rộng và phát hành không đòi hỏi tách process.

## 2. Tách triển khai đem lại lợi ích gì?

Tách service có thể tạo ra các lợi ích sau, nhưng mỗi lợi ích cần gắn với một vấn đề thực tế.

### Mở rộng độc lập

Nếu Inventory nhận tải lớn vào mùa khuyến mại còn Reporting ít tải, có thể cấp thêm tài nguyên cho Inventory mà không phải scale toàn bộ ứng dụng. Lợi ích rõ nhất khi workload, tài nguyên hoặc profile hiệu năng của các năng lực khác nhau đáng kể.

### Phát hành độc lập

Một thay đổi trong Payment có thể được build, kiểm thử và phát hành mà không phải triển khai lại Sales nếu contract tương thích. Điều này hữu ích khi các năng lực có nhịp phát hành khác nhau và team đủ khả năng sở hữu pipeline riêng.

### Cô lập lỗi và giới hạn tài nguyên

Process boundary giúp đặt giới hạn CPU, memory, thread pool và restart policy riêng. Một memory leak trong Reporting không nhất thiết làm sập toàn bộ Sales nếu hệ thống được thiết kế để xử lý phụ thuộc bị lỗi.

Tuy nhiên, cô lập process không tự tạo ra resilience. Nếu Sales đồng bộ gọi Reporting trong mọi request, Reporting ngừng hoạt động vẫn có thể làm Sales thất bại.

### Quyền sở hữu dữ liệu và công nghệ

Service có thể sở hữu schema, database và lựa chọn công nghệ phù hợp với workload của mình. Ví dụ, Transaction History có thể dùng storage tối ưu đọc lịch sử, trong khi Inventory dùng relational database với transaction và locking.

Lợi ích này chỉ xuất hiện khi quyền sở hữu thực sự rõ. Nếu nhiều service vẫn ghi trực tiếp vào cùng database, deployment độc lập chỉ là hình thức.

### Phù hợp với cấu trúc team

Một team có thể sở hữu một năng lực nghiệp vụ từ thiết kế đến vận hành, giảm việc chờ team khác sửa code hoặc phát hành. Nhưng nếu tổ chức có quá nhiều service nhỏ so với số team, chi phí phối hợp có thể tăng thay vì giảm.

## 3. Chi phí ẩn của mỗi deployment boundary

Một service độc lập cần nhiều thứ hơn một project build được. Nó cần cấu hình runtime, triển khai, mạng, bảo mật, quan sát, backup, cảnh báo, tài liệu vận hành và người chịu trách nhiệm khi xảy ra sự cố.

| Nhóm chi phí | Khi chạy cùng tiến trình | Khi tách triển khai |
|---|---|---|
| Giao tiếp | Method call hoặc in-process messaging | HTTP/gRPC/message broker, serialization và network |
| Dữ liệu | Có thể cùng transaction resource | Database ownership, replication và consistency |
| Deployment | Một pipeline và một release unit | Pipeline, artifact, config và rollback riêng |
| Observability | Log/trace trong một process | Correlation và tracing xuyên service |
| Security | Boundary trong ứng dụng | Service identity, token, TLS, secret và policy mạng |
| Reliability | Một số lỗi cùng process | Timeout, retry, circuit breaker, partial failure |
| Testing | Test trong một runtime | Contract, integration và distributed test |
| On-call | Một ứng dụng và nhóm hỗ trợ | Nhiều SLO, dashboard, alert và runbook |
| Phối hợp team | Có thể sửa cùng codebase | Contract, lịch phát hành và ownership liên nhóm |
| Hạ tầng | Ít runtime unit hơn | Container, orchestration, network và telemetry tăng |

Chi phí không chỉ là tiền cloud. Nó còn gồm thời gian kỹ sư, thời gian điều tra incident, số cuộc phối hợp, độ trễ phát hành và rủi ro khi thay đổi contract.

### Một service nhỏ vẫn có chi phí nền

Service chỉ có một endpoint và rất ít traffic vẫn cần:

- Build và dependency management.
- Image/container và runtime configuration.
- Health/readiness checks.
- Authentication và authorization.
- Logging, metrics, tracing.
- Deployment, rollback và secret rotation.
- Backup/restore nếu có dữ liệu.
- Alert, dashboard và runbook.
- Owner chịu trách nhiệm.

Nếu chi phí nền lớn hơn lợi ích độc lập, module nên tiếp tục chạy trong modular monolith.

## 4. Network call thay thế method call

Trong cùng JVM, một method call thường có latency nhỏ, truyền object trực tiếp và có thể chia sẻ transaction/context. Khi tách service, giao tiếp cần serialize request, đi qua network, được xác thực, xử lý ở process khác rồi serialize response.

~~~text
In-process:
  OrderService -> InventoryModule.reserve()

Distributed:
  OrderService
      -> DNS / service discovery
      -> connection pool
      -> network
      -> authentication
      -> InventoryService
      -> database
      -> response over network
~~~

Một network call có thể thất bại vì DNS, connection timeout, TLS, load balancer, process restart, network partition hoặc service quá tải. Caller không thể giả định rằng request đã gửi thì callee chắc chắn nhận, hoặc timeout nghĩa là callee chưa thực hiện.

### Latency cộng dồn

Giả sử một request đồng bộ gọi lần lượt Sales, Inventory, Pricing và Payment. Thời gian tổng có thể gần bằng tổng latency của từng bước, cộng serialization, network và queueing.

~~~text
Client
  |
  v
Sales (20 ms)
  |
  v
Inventory (45 ms)
  |
  v
Pricing (35 ms)
  |
  v
Payment (120 ms)

Approximate critical path = 220 ms + network/queue overhead
~~~

Nếu các call chạy tuần tự, một dependency chậm có thể kéo dài toàn bộ request. Nếu chạy song song, latency có thể giảm nhưng việc timeout, hủy tác vụ và xử lý partial result phức tạp hơn.

Không nên đặt một chuỗi dài synchronous calls trong đường request quan trọng nếu nghiệp vụ có thể chuyển thành workflow bất đồng bộ.

### Tail latency

Latency trung bình có thể trông tốt nhưng một tỷ lệ nhỏ request rất chậm. Khi một request phụ thuộc nhiều service, xác suất gặp một dependency ở tail latency tăng lên. Hãy đo percentile như p50, p95 và p99 cho từng hop và cho toàn hành trình, không chỉ nhìn average.

## 5. Partial failure và timeout

Trong distributed system, một phần hệ thống có thể hoạt động trong khi phần khác gặp lỗi. Đây là partial failure.

Ví dụ:

- Sales ghi Order thành công nhưng Inventory không phản hồi.
- Payment provider đã capture tiền nhưng response bị mất.
- Broker nhận message nhưng publisher không nhận được xác nhận.
- Service đã deploy phiên bản mới nhưng một số instance cũ vẫn đang chạy.

Timeout chỉ cho biết caller không nhận response trong thời hạn. Nó không chứng minh thao tác ở phía server chưa xảy ra.

### Đặt timeout cho mọi network dependency

Không nên để request chờ vô hạn. Cần timeout kết nối, timeout đọc và deadline tổng cho use case. Timeout của các hop nên phù hợp với deadline của caller; nếu caller chỉ còn 500 ms thì không nên gửi một request downstream có timeout 5 giây.

### Retry có điều kiện

Retry có thể giúp với lỗi tạm thời, nhưng retry không an toàn có thể tạo tác dụng phụ lặp:

- Charge thẻ hai lần.
- Tạo hai Order.
- Giữ hàng hai lần.
- Gửi hai email.

Retry cần idempotency key, giới hạn số lần, exponential backoff, jitter và phân loại lỗi. Với unknown outcome, cần tra cứu trạng thái hoặc dùng cùng idempotency key thay vì tạo command mới.

### Circuit breaker và bulkhead

Circuit breaker tạm ngừng gọi dependency đang thất bại liên tục, giúp tránh làm cạn thread/connection pool. Bulkhead giới hạn tài nguyên dành cho từng dependency để một service chậm không chiếm hết tài nguyên của caller.

Đây là cơ chế bảo vệ kỹ thuật; chúng không thay thế quyết định nghiệp vụ về việc có thể tiếp tục ở trạng thái Pending hay phải từ chối.

## 6. Distributed transaction và ranh giới nhất quán

Trong modular monolith, một transaction database có thể cập nhật Order và Reservation nếu chúng cùng transactional resource. Khi tách Sales và Inventory thành hai service có database riêng, không còn một transaction cục bộ bao trùm cả hai.

~~~text
One database transaction:
  update Order
  update Reservation
  COMMIT

Two independent services:
  Sales DB: OrderPlaced
       |
       v
  Inventory DB: ReserveStock
       |
       v
  StockReserved / StockUnavailable
~~~

Nếu Sales commit Order rồi Inventory không giữ được hàng, hệ thống phải xử lý trạng thái trung gian. Có thể giữ Order ở PendingInventory, phát lệnh reserve, chờ kết quả rồi chuyển sang Accepted hoặc Rejected.

### Saga và compensation

Saga mô hình hóa quy trình nhiều bước, mỗi bước commit trong transaction cục bộ của service sở hữu. Khi một bước thất bại, workflow có thể thực hiện compensation cho các bước đã thành công.

Ví dụ:

1. Sales tạo Order ở trạng thái Pending.
2. Inventory giữ hàng.
3. Payment authorize thanh toán.
4. Sales chuyển Order sang Confirmed.
5. Nếu Payment thất bại, Inventory giải phóng reservation và Sales hủy Order theo policy.

Compensation là một hành động nghiệp vụ mới, ví dụ StockReservationReleased hoặc PaymentVoided. Nó không phải rollback vật lý một transaction đã commit từ service khác.

### Eventual consistency

Sau khi một service phát event, read model hoặc service khác có thể cập nhật trễ. UI có thể tạm thời hiển thị trạng thái cũ. Thiết kế phải quyết định:

- Trạng thái trung gian nào được phép xuất hiện?
- Caller được thông báo đã nhận yêu cầu hay đã hoàn tất?
- Người dùng có thể retry hoặc hủy không?
- Bao lâu thì workflow được coi là quá hạn?
- Ai xử lý message thất bại hoặc quy trình bị kẹt?

Không nên hứa với người dùng rằng đơn đã xác nhận nếu mới chỉ lưu yêu cầu đặt hàng.

## 7. Data ownership khi tách service

Một service cần sở hữu dữ liệu mà nó chịu trách nhiệm bảo vệ. Ví dụ:

| Context/service | Dữ liệu sở hữu | Quy tắc sở hữu |
|---|---|---|
| Sales | Order, OrderLine, trạng thái chấp nhận đơn | Khi nào Order được tạo, sửa, xác nhận hoặc hủy |
| Inventory | Stock, Reservation | Số lượng khả dụng và quy tắc giữ/giải phóng hàng |
| Payment | PaymentAttempt, Authorization, Capture | Trạng thái thanh toán và đối soát provider |
| Fulfillment | Shipment, Pick/Pack, Delivery | Quy trình chuẩn bị và giao hàng |

Các service khác không nên ghi trực tiếp vào bảng nội bộ của owner. Nếu Sales cần biết Reservation đã thành công, nó gọi contract của Inventory hoặc nhận event StockReserved.

### Database per service là một nguyên tắc ownership

Database per service không nhất thiết có nghĩa mỗi service phải có một máy database riêng. Nhiều service có thể dùng chung một database cluster hoặc instance vật lý, nhưng schema/credential/quyền ghi cần bảo vệ ownership. Mục tiêu là không để service khác phụ thuộc vào cấu trúc lưu trữ nội bộ.

### Không dùng shared database để né contract

Nếu Reporting đọc trực tiếp mọi bảng, schema migration của Sales có thể làm Reporting hỏng. Hãy cung cấp read model, event stream hoặc data pipeline có contract rõ. Với báo cáo phân tích, có thể xây data warehouse/lakehouse được quản lý riêng thay vì biến database giao dịch thành API công khai.

### Dữ liệu trùng lặp có thể là lựa chọn hợp lý

Một service có thể lưu bản sao tên khách hàng hoặc địa chỉ giao hàng để phục vụ nghiệp vụ của mình. Điều đó tạo duplication nhưng giảm coupling runtime. Cần xác định bản sao là snapshot tại thời điểm nào, nguồn sự thật ở đâu và khi dữ liệu thay đổi có cần đồng bộ hay không.

Đừng đồng bộ mọi field chỉ vì có thể. Chỉ sao chép dữ liệu cần cho use case và định nghĩa semantics của snapshot.

## 8. API và event contract trở thành sản phẩm nội bộ

Khi một module được triển khai độc lập, contract của nó là ranh giới giữa các team. Contract cần được thiết kế và quản lý như một sản phẩm:

- Có owner.
- Có tài liệu và ví dụ.
- Có schema/type rõ ràng.
- Có semantics, error behavior và retry policy.
- Có compatibility policy.
- Có quy trình deprecation.
- Có contract test hoặc consumer-driven test phù hợp.

### Contract không nên phơi bày domain object nội bộ

Không trả toàn bộ ORM entity hoặc Aggregate qua REST. Tạo request/response DTO hoặc Integration Event chỉ chứa thông tin consumer cần. Nếu consumer phụ thuộc vào object graph nội bộ, thay đổi persistence hoặc domain model sẽ làm contract vỡ.

### Versioning

Thêm field tùy chọn thường có thể tương thích nếu consumer cũ bỏ qua được. Đổi ý nghĩa field, đổi đơn vị, xóa field hoặc thay enum có thể là breaking change.

Một quy trình thay đổi contract:

1. Xác định consumer đang dùng contract.
2. Đánh giá tương thích với consumer cũ.
3. Thêm field hoặc version mới nếu cần.
4. Triển khai consumer hỗ trợ cả hai dạng.
5. Triển khai producer theo thứ tự tương thích.
6. Theo dõi usage và lỗi.
7. Chỉ ngừng contract cũ khi đã xác nhận không còn consumer.

Trong môi trường rolling deployment, phiên bản cũ và mới có thể cùng chạy. Contract cần hỗ trợ giai đoạn chuyển tiếp này.

## 9. Chi phí của event-driven integration

Event giúp producer không cần biết trực tiếp từng consumer, nhưng tạo thêm trách nhiệm:

- Message có thể được giao nhiều lần.
- Consumer có thể xử lý chậm hoặc ngừng hoạt động.
- Event có thể đến trễ hoặc sai thứ tự.
- Schema có thể thay đổi.
- Queue có thể tích tụ backlog.
- Poison message có thể làm consumer kẹt.
- Cần dead-letter queue và quy trình replay.
- Cần correlation ID và tracing xuyên message.

### Outbox

Nếu service cập nhật database rồi publish event qua broker, có khoảng trống giữa hai thao tác. Database commit thành công nhưng publish thất bại có thể làm mất event. Transactional Outbox ghi thay đổi domain và outbox record trong cùng transaction; relay gửi message sau đó.

~~~text
Local transaction:
  update Order
  insert OutboxMessage
  COMMIT
       |
       v
Outbox Relay
  -> publish to broker
  -> mark delivered / checkpoint
       |
       v
Consumer (idempotent)
~~~

Outbox không bảo đảm consumer xử lý đúng một lần. Relay có thể publish lại nếu crash sau khi broker nhận message nhưng trước khi ghi nhận đã gửi. Consumer vẫn cần idempotency/deduplication.

### Theo dõi backlog và dead letter

Đừng chỉ giám sát broker còn sống hay không. Cần theo dõi message age, queue depth, retry count, dead-letter count và thời gian xử lý. Một queue có thể đang hoạt động nhưng backlog tăng liên tục khiến nghiệp vụ không hoàn tất đúng hạn.

## 10. Observability tăng theo số process

Trong một ứng dụng, log và stack trace thường nằm trong cùng process. Khi một request đi qua Sales, Inventory, Payment và Fulfillment, việc tìm nguyên nhân cần nối các dấu vết qua nhiều hệ thống.

Ba trụ cột thường dùng:

- **Logs:** sự kiện có ngữ cảnh, error code, service, correlation/trace ID.
- **Metrics:** latency, throughput, error rate, saturation, queue backlog.
- **Distributed traces:** các span thể hiện request đi qua những service nào và mất thời gian ở đâu.

~~~text
Client request
  traceId = T-123
      |
      v
Sales span
      |
      +--> Inventory span
      |
      +--> Payment span
                 |
                 +--> Provider HTTP span
~~~

Không nên log toàn bộ payload nếu có thông tin cá nhân hoặc thanh toán. Hãy chuẩn hóa field, redaction và retention. Trace context cần được truyền qua HTTP và message headers nếu công cụ hỗ trợ.

### Mỗi service cần dashboard và alert có ý nghĩa

Ví dụ:

| Service | Metric quan trọng |
|---|---|
| Sales | Order acceptance latency, tỷ lệ Order Pending quá hạn |
| Inventory | Reservation success rate, conflict, stock update latency |
| Payment | Authorization/capture success, unknown outcome, reconciliation backlog |
| Fulfillment | Shipment creation delay, pick/pack backlog, delivery exception |

Một alert tốt gắn với ảnh hưởng nghiệp vụ và có runbook. Cảnh báo CPU tăng nhưng không có tác động user có thể không cần đánh thức on-call.

## 11. Reliability và SLO

Khi có nhiều service, độ sẵn sàng của một hành trình nghiệp vụ phụ thuộc vào các dependency. Nếu tất cả service phải cùng sẵn sàng trong một request đồng bộ, availability của hành trình có thể thấp hơn từng service riêng.

Ví dụ minh họa: nếu ba dependency độc lập đều có availability 99,9% và request bắt buộc cả ba cùng thành công, availability lý thuyết của critical path xấp xỉ:

~~~text
0.999 × 0.999 × 0.999 ≈ 0.997
~~~

Tức khoảng 99,7% trước khi tính lỗi của caller và các yếu tố khác. Giả định độc lập thường không hoàn toàn đúng trong thực tế, nhưng phép tính cho thấy thêm dependency bắt buộc có thể làm giảm độ tin cậy của hành trình.

### Đặt SLI/SLO theo hành trình nghiệp vụ

Không chỉ đặt SLO cho từng service. Hãy xác định:

- Tỷ lệ khách tạo được Order hợp lệ.
- Thời gian từ PlaceOrder đến Confirmed.
- Tỷ lệ payment được xác định kết quả trong thời hạn.
- Tỷ lệ reservation hoàn tất hoặc được giải phóng đúng hạn.
- Số workflow ở trạng thái Pending quá SLA.

SLO cần phản ánh điều người dùng cần. Một service có uptime 99,99% nhưng mọi Order vẫn mắc kẹt do consumer backlog không phải kết quả tốt.

### Error budget và release

Nếu service liên tục vi phạm SLO, team cần dành thời gian cải thiện reliability trước khi tăng tốc phát hành tính năng. Error budget giúp thảo luận dựa trên dữ liệu thay vì chỉ tranh luận giữa tốc độ và ổn định.

## 12. Bảo mật và quản lý quyền truy cập

Trong monolith, một số lời gọi nội bộ có thể dựa vào trust trong process. Khi tách service, mỗi request qua mạng cần identity và policy rõ.

Các việc phát sinh:

- Service-to-service authentication.
- TLS và certificate rotation.
- Token audience/scope.
- Authorization theo capability.
- Secret management.
- Network policy và ingress/egress control.
- Audit log cho hành động nhạy cảm.
- Quản lý quyền truy cập database riêng.

Không nên dùng một credential dùng chung cho mọi service. Nếu một service bị xâm nhập, quyền của nó nên bị giới hạn ở đúng dữ liệu và API cần thiết.

### Trust boundary thay đổi

Ngay cả trong cùng cluster, request từ service khác vẫn cần xác thực và kiểm tra quyền. Không nên coi network nội bộ là đáng tin tuyệt đối. Cần tránh để API quản trị hoặc endpoint debug mở ra ngoài phạm vi cho phép.

## 13. Deployment pipeline và release coordination

Triển khai độc lập có thể giảm phạm vi release, nhưng mỗi service cần pipeline riêng:

~~~text
Source
  -> Build
  -> Unit tests
  -> Integration/contract tests
  -> Security/dependency scan
  -> Container image
  -> Deploy staging
  -> Smoke/health checks
  -> Progressive rollout
  -> Monitor SLO
~~~

Các chiến lược rollout:

- Rolling deployment: thay instance dần.
- Blue/green: chuyển traffic giữa hai môi trường.
- Canary: gửi một phần traffic vào phiên bản mới trước khi mở rộng.
- Feature flag: bật hành vi mới theo nhóm hoặc điều kiện.

Mỗi cách có chi phí và yêu cầu hạ tầng khác nhau. Quan trọng là service phải hỗ trợ coexistence giữa phiên bản cũ và mới khi cần.

### Database migration phải tương thích với rolling deployment

Nếu phiên bản cũ vẫn chạy trong lúc phiên bản mới đã deploy, migration phá vỡ schema có thể làm phiên bản cũ lỗi. Mẫu expand-and-contract thường gồm:

1. Expand: thêm cột/bảng mới theo cách code cũ vẫn chạy.
2. Deploy code mới có thể đọc/ghi dạng cũ và mới.
3. Backfill dữ liệu.
4. Chuyển hoàn toàn sang cấu trúc mới.
5. Contract: xóa field cũ sau khi mọi instance/consumer đã chuyển.

Không nên gộp đổi schema phá vỡ tương thích và deploy code mới vào một bước không có đường rollback.

## 14. Rollback khó hơn khi có side effect

Trong monolith, rollback binary có thể tương đối đơn giản nếu database schema tương thích. Trong distributed system, một phiên bản có thể đã:

- Phát event mới mà consumer cũ không hiểu.
- Ghi dữ liệu theo schema mới.
- Gọi payment provider hoặc gửi email.
- Kích hoạt workflow ở service khác.

Rollback binary không thể thu hồi side effect đã xảy ra. Cần forward fix, compensation hoặc xử lý dữ liệu có kiểm soát.

Thiết kế release nên ưu tiên backward/forward compatibility, feature flag và rollout từng bước. Với event schema, giữ consumer có thể đọc event cũ và mới trong giai đoạn chuyển tiếp.

## 15. Chi phí kiểm thử distributed system

Một modular monolith có thể test module bằng unit test và integration test trong một runtime. Khi tách service, phạm vi test mở rộng:

| Loại test | Mục tiêu |
|---|---|
| Unit test | Domain rule và logic cục bộ |
| Module test | Public API và module boundary |
| Adapter integration test | Database, broker, HTTP adapter |
| Contract test | Producer và consumer tương thích |
| Component test | Service chạy cùng dependency giả lập/thật |
| End-to-end test | Hành trình qua nhiều service |
| Resilience test | Timeout, retry, dependency unavailable |
| Migration test | Nâng schema khi phiên bản cũ/mới cùng tồn tại |

Không nên dùng end-to-end test để kiểm tra mọi nhánh. Chúng chậm, dễ flaky và khó xác định lỗi thuộc service nào. Hãy giữ phần lớn quy tắc trong unit test, kiểm tra adapter/contract ở boundary và chỉ dùng một số end-to-end test cho hành trình quan trọng.

### Contract test giảm rủi ro phối hợp

Consumer-driven contract test ghi nhận cách consumer sử dụng API của provider. Provider chạy kiểm tra để xác nhận thay đổi vẫn đáp ứng contract. Điều này giúp phát hiện breaking change trước khi deploy production.

Với event, cần test schema và semantics, không chỉ JSON parse thành công. Hai field có cùng kiểu string vẫn có thể khác nghĩa nghiệp vụ.

## 16. Chi phí phối hợp giữa các team

Tách service thường đi kèm việc tách ownership. Nếu nhiều team cùng sửa một luồng, cần phối hợp:

- Thiết kế và thay đổi API/event contract.
- Lịch deploy và thứ tự rollout.
- Quyền truy cập môi trường và dữ liệu.
- Incident response xuyên service.
- Thay đổi schema và backfill.
- SLO và trách nhiệm xử lý backlog.
- Version compatibility và deprecation.

Nếu một thay đổi thường xuyên phải sửa đồng thời Sales, Inventory và Payment, có thể ranh giới chưa đúng hoặc workflow cần được thiết kế lại. Nếu một team sở hữu quá nhiều service, họ có thể mất thời gian vận hành hơn là phát triển năng lực nghiệp vụ.

### Team topology

Một ranh giới service tốt thường có một team đủ năng lực sở hữu từ đầu đến cuối: code, pipeline, dashboard, alert và on-call. Platform team có thể cung cấp nền tảng chung như deployment templates, logging, secrets và observability để giảm việc mỗi team tự xây lại.

Platform team không nên trở thành bottleneck phải phê duyệt mọi thay đổi nhỏ. Nền tảng tốt tạo self-service với guardrail rõ.

### Conway's Law

Kiến trúc giao tiếp thường phản ánh cấu trúc giao tiếp của tổ chức. Nếu team bị chia theo technical layer như database, backend, frontend và operations, mỗi thay đổi nghiệp vụ có thể phải đi qua nhiều handoff. Team theo năng lực nghiệp vụ có thể giảm phối hợp, nhưng chỉ khi họ có quyền quyết định và khả năng vận hành thực tế.

Không nên tách service chỉ để vẽ sơ đồ team. Ranh giới cần phù hợp với domain, ownership và nhu cầu triển khai.

## 17. Chi phí trực tiếp và chi phí cơ hội

Khi đánh giá tách service, hãy tính cả chi phí trực tiếp và thời gian bị lấy khỏi hoạt động phát triển sản phẩm.

| Chi phí | Ví dụ cần tính |
|---|---|
| Compute | CPU, memory, replica, autoscaling |
| Network | Load balancer, egress, service mesh, DNS |
| Storage | Database, backup, log, trace, metric retention |
| Platform | Kubernetes/containers, registry, secrets, CI/CD |
| Reliability | On-call, incident, disaster recovery, SLO work |
| Security | Identity, certificate, scanning, policy, audit |
| Engineering | Contract, integration, test, migration |
| Coordination | Review liên team, release scheduling, incident handoff |
| Cognitive load | Số codebase, pipeline, dashboard và runtime cần hiểu |

Chi phí cơ hội là phần quan trọng: thời gian xây dashboard, xử lý certificate, nâng cluster hoặc điều tra distributed trace là thời gian chưa dành cho quy tắc nghiệp vụ mới.

### Ước lượng chi phí theo service

Không có một con số cố định cho mọi tổ chức. Có thể tạo bảng ước lượng theo tháng hoặc theo quý:

| Hạng mục | Câu hỏi |
|---|---|
| Runtime | Có bao nhiêu replica tối thiểu, peak và staging? |
| Database | Có cần database riêng hay schema/credential riêng là đủ? |
| Telemetry | Bao nhiêu log, trace và metric cần giữ? |
| On-call | Ai nhận alert ngoài giờ và có runbook chưa? |
| Pipeline | Có template tự phục vụ hay phải tạo thủ công? |
| Integration | Có bao nhiêu upstream/downstream và contract cần duy trì? |
| Change coordination | Một thay đổi thường cần bao nhiêu team? |
| Failure handling | Ai chịu trách nhiệm khi workflow bị kẹt? |

Ước lượng nên dùng số liệu hiện tại hoặc giả định được ghi rõ. Không nên quyết định chỉ bằng số container hoặc chi phí CPU.

## 18. Khi nào nên giữ modular monolith?

Modular monolith thường phù hợp khi:

- Domain và ranh giới module vẫn đang được khám phá.
- Các module thay đổi cùng nhau thường xuyên.
- Nhu cầu scale chưa khác biệt đáng kể.
- Một team hoặc một nhóm nhỏ có thể sở hữu toàn ứng dụng.
- Transaction xuyên module cần tính nhất quán mạnh.
- Hạ tầng distributed operation chưa sẵn sàng.
- Chi phí vận hành service độc lập lớn hơn lợi ích hiện tại.

Có thể tăng khả năng thay đổi bằng:

- Package/module theo Bounded Context.
- Public API nội bộ.
- Không truy cập trực tiếp bảng của module khác.
- Dependency rule và architecture tests.
- Module ownership và code review.
- Outbox nội bộ hoặc event dispatcher khi cần tách tác vụ.
- Pipeline và cấu hình có thể tách sau này.

Giữ cùng process không có nghĩa là bỏ qua ranh giới.

## 19. Khi nào một module đáng được tách?

Một module có thể đáng tách khi nhiều tín hiệu cùng xuất hiện:

- Có nhu cầu scale khác biệt và đo được.
- Cần phát hành độc lập thường xuyên.
- Có team owner ổn định, đủ năng lực on-call.
- Dữ liệu và invariant có thể sở hữu trong một boundary.
- Contract giữa module đã tương đối ổn định.
- Có thể chấp nhận consistency model sau khi tách.
- Failure behavior và workflow đã được thiết kế.
- Có observability, security và deployment automation.
- Chi phí coupling hiện tại lớn hơn chi phí distributed operation.

Một lý do đơn lẻ như muốn dùng microservices hoặc codebase lớn chưa đủ. Codebase lớn có thể cần modularization, refactor hoặc build optimization mà không cần tách process.

### Một ma trận đánh giá

Chấm từng tiêu chí theo mức thấp/trung bình/cao và ghi bằng chứng:

| Tiêu chí | Câu hỏi cần trả lời |
|---|---|
| Business autonomy | Năng lực có vòng đời và quyết định riêng không? |
| Change independence | Có thường xuyên phát hành mà không cần module khác không? |
| Scale independence | Workload có khác biệt đủ lớn để scale riêng không? |
| Data ownership | Có thể sở hữu dữ liệu và invariant riêng không? |
| Consistency tolerance | Nghiệp vụ có chấp nhận trạng thái trung gian không? |
| Operational readiness | Có monitoring, SLO, runbook và on-call không? |
| Team ownership | Có team đủ năng lực chịu trách nhiệm không? |
| Cost benefit | Lợi ích dự kiến có vượt chi phí runtime và phối hợp không? |

Nếu nhiều câu trả lời còn mơ hồ, hãy tiếp tục modularize trong cùng process và thu thập dữ liệu trước khi tách.

## 20. Tránh distributed monolith

Distributed monolith là hệ thống có nhiều service nhưng vẫn phụ thuộc chặt:

- Một request phải gọi đồng bộ qua nhiều service.
- Một thay đổi yêu cầu deploy nhiều service cùng lúc.
- Các service dùng chung database và sửa bảng của nhau.
- Không có contract compatibility.
- Service không thể hoạt động khi một dependency nhỏ bị lỗi.
- Team không thể release độc lập dù có pipeline riêng.

~~~text
Service A <--> Service B <--> Service C
    ^              |              |
    +--------------+--------------+
       shared database / shared release assumptions
~~~

Hệ thống có chi phí distributed nhưng không nhận được autonomy tương ứng. Hãy giảm dependency cycle, làm rõ ownership, thiết kế contract và loại bỏ synchronous call chain không cần thiết.

## 21. Lộ trình tách service từng bước

Một quy trình an toàn thường bắt đầu từ một năng lực có ranh giới tốt và ít rủi ro hơn.

**Bước 1: Chọn động lực cụ thể.** Ví dụ Inventory cần scale riêng vì lượng reservation tăng mạnh, hoặc Payment cần team và release cadence độc lập.

**Bước 2: Xác nhận Bounded Context và ownership.** Xác định model, Aggregate, dữ liệu và quy tắc nào thuộc module được chọn.

**Bước 3: Làm sạch module boundary.** Tách public API, loại bỏ import nội bộ và truy cập database chéo.

**Bước 4: Xác định contract giao tiếp.** Chọn API hoặc event, định nghĩa schema, error, timeout, idempotency và compatibility.

**Bước 5: Chọn data migration strategy.** Quyết định ai là owner dữ liệu, cách backfill, dual-read/dual-write nếu thật sự cần và thời điểm chuyển nguồn sự thật.

**Bước 6: Thiết kế consistency và failure handling.** Xác định trạng thái Pending, retry, compensation, reconciliation và dead-letter.

**Bước 7: Chuẩn bị vận hành.** Pipeline, secrets, TLS, dashboard, tracing, SLO, alert, runbook, backup và on-call.

**Bước 8: Tách bằng Strangler pattern.** Chuyển một luồng hoặc endpoint sang service mới, giữ đường cũ có kiểm soát trong giai đoạn chuyển đổi.

**Bước 9: Chuyển dữ liệu và traffic có kiểm chứng.** So sánh kết quả, theo dõi lỗi và có cách dừng rollout.

**Bước 10: Xóa đường cũ.** Chỉ khi đã xác nhận traffic và dữ liệu không còn phụ thuộc implementation cũ.

Không nên dual-write tùy tiện vào hai database vì lỗi giữa hai lần ghi có thể làm dữ liệu lệch. Nếu cần migration phức tạp, hãy thiết kế source of truth, outbox/CDC và reconciliation trước khi thực hiện.

## 22. Strangler pattern và chuyển traffic

Strangler pattern cho phép thay thế từng phần của hệ thống cũ bằng service mới. Một gateway hoặc routing layer chuyển các request được chọn sang implementation mới.

~~~text
Client
  |
  v
API Gateway / Router
  |
  +--> Legacy Application (existing capabilities)
  |
  +--> New Inventory Service (extracted capability)
~~~

Giai đoạn đầu có thể chỉ chuyển một endpoint hoặc một nhóm tenant. Cần xác định rõ dữ liệu nào là nguồn sự thật ở mỗi giai đoạn, tránh cả legacy và service mới cùng ghi một nghiệp vụ.

Một số kỹ thuật:

- Route theo endpoint hoặc capability.
- Route theo tenant/percentage có kiểm soát.
- Shadow traffic để so sánh read result, không thực hiện side effect hai lần.
- Backfill dữ liệu trước khi chuyển write owner.
- Reconciliation để phát hiện sai lệch.
- Rollback route nếu metric vượt ngưỡng.

Shadow traffic chỉ phù hợp cho request an toàn hoặc được thiết kế để không gây tác dụng phụ. Không gửi lệnh charge/cancel thật hai lần chỉ để so sánh.

## 23. Ví dụ quyết định tách Inventory

Một nền tảng thương mại điện tử có bốn module:

| Module | Tải | Nhịp thay đổi | Đặc điểm |
|---|---|---|---|
| Sales | Cao | Nhiều thay đổi nghiệp vụ | Điều phối Order |
| Inventory | Rất cao vào chiến dịch | Quy tắc reservation riêng | Cần concurrency và scale theo SKU |
| Payment | Trung bình | Phụ thuộc provider | Yêu cầu bảo mật, đối soát |
| Reporting | Batch/read-heavy | Phát hành ít hơn | Có thể chạy tác vụ dài |

Inventory có lý do đáng xem xét tách vì workload reservation khác biệt, cần tối ưu concurrency và có team sở hữu. Nhưng trước khi tách, cần giải quyết:

- Sales không còn cập nhật bảng stock.
- Inventory có API/command giữ hàng và event kết quả.
- Reservation có idempotency reference để retry an toàn.
- Sales có trạng thái PendingInventory.
- Có timeout và quy trình giải phóng reservation hết hạn.
- Event được publish đáng tin cậy.
- Dashboard đo reservation latency, conflict và backlog.
- Team Inventory có on-call và runbook.

Nếu các điều kiện này chưa sẵn sàng, hãy trước hết làm Inventory thành module nội bộ có API rõ trong modular monolith. Sau khi đo tải và xác nhận boundary, việc tách process sẽ ít rủi ro hơn.

## 24. Các câu hỏi vận hành cần trả lời trước production

Một service chưa sẵn sàng chỉ vì container chạy được. Trước khi tách triển khai, cần có câu trả lời:

### Ownership

- Team nào chịu trách nhiệm?
- Ai nhận alert ngoài giờ?
- Ai phê duyệt contract và migration?
- Ai xử lý dữ liệu sai hoặc workflow bị kẹt?

### Deployment

- Có pipeline độc lập và artifact bất biến không?
- Có health/readiness/liveness probe phù hợp không?
- Có rollout và rollback strategy không?
- Phiên bản cũ/mới có thể chạy đồng thời không?

### Data

- Service sở hữu schema/table nào?
- Backup và restore đã được thử chưa?
- Có migration và backfill plan không?
- Có retention và privacy policy không?

### Reliability

- Timeout/deadline đã đặt chưa?
- Retry có idempotent và có giới hạn không?
- Có circuit breaker/bulkhead khi cần không?
- Partial failure được biểu diễn bằng trạng thái nghiệp vụ nào?

### Observability

- Có structured logs và trace propagation không?
- Có metric theo hành trình nghiệp vụ không?
- Alert có owner và runbook không?
- Có dashboard cho dependency và backlog không?

### Security

- Service identity và secret rotation đã sẵn sàng chưa?
- TLS và authorization policy có rõ không?
- Credential database có giới hạn quyền không?
- Payload/log có được redaction không?

## 25. Những sai lầm thường gặp

**Tách service theo class hoặc package.** Một class không phải đơn vị triển khai. Hãy tách theo năng lực, ownership và nhu cầu độc lập.

**Coi mỗi Bounded Context bắt buộc là một microservice.** Bounded Context là ranh giới mô hình; nó có thể cùng process với context khác.

**Tách trước khi có module boundary.** Dependency rối sẽ chuyển thành network call và shared database coupling.

**Đếm container như thước đo tiến bộ.** Nhiều container không đồng nghĩa autonomy, khả năng mở rộng hay tốc độ phát hành tốt hơn.

**Dùng shared database để giữ transaction cũ.** Service vẫn phụ thuộc schema và ownership của nhau. Hãy quyết định consistency và data ownership một cách có chủ đích.

**Giữ synchronous call chain dài.** Một dependency chậm hoặc lỗi có thể kéo sập toàn hành trình.

**Retry mọi timeout.** Timeout có thể là unknown outcome; side effect có thể đã xảy ra.

**Giả định exactly-once message delivery.** Consumer cần idempotency và xử lý duplicate.

**Phát event trước khi dữ liệu commit.** Consumer có thể nhận sự việc chưa được ghi nhận. Dùng outbox hoặc subscription bền vững.

**Không có contract compatibility.** Rolling deployment có thể làm phiên bản cũ và mới không tương thích.

**Không tính chi phí on-call.** Service cần người chịu trách nhiệm, dashboard, alert và runbook.

**Tách service nhưng team vẫn phải phối hợp cho mọi thay đổi.** Có thể ranh giới ownership hoặc contract chưa đúng.

**Dùng microservices để né modularization.** Chia process không sửa được domain model, dependency cycle hoặc trách nhiệm không rõ.

## 26. Checklist quyết định và readiness

- [ ] Có lý do kinh doanh/kỹ thuật cụ thể để tách.
- [ ] Lợi ích độc lập được mô tả và có thể đo.
- [ ] Module có cohesion cao và public API rõ.
- [ ] Bounded Context, Aggregate và data ownership được xác định.
- [ ] Không có ghi trực tiếp vào dữ liệu nội bộ của service khác.
- [ ] Contract có semantics, version và compatibility policy.
- [ ] Timeout, retry, idempotency và unknown outcome được thiết kế.
- [ ] Consistency model và trạng thái trung gian được chấp nhận bởi nghiệp vụ.
- [ ] Saga/compensation có owner nếu workflow đi qua nhiều service.
- [ ] Outbox hoặc cơ chế publish bền vững đã được chọn.
- [ ] Logs, metrics, traces và correlation được thiết lập.
- [ ] SLO, alert, dashboard và runbook đã có.
- [ ] Service identity, secret, TLS và authorization đã sẵn sàng.
- [ ] CI/CD, migration, rollout và rollback được tự động hóa.
- [ ] Team owner có khả năng hỗ trợ production.
- [ ] Chi phí hạ tầng, phối hợp và cognitive load đã được ước lượng.
- [ ] Có kế hoạch chuyển traffic/dữ liệu và loại bỏ đường cũ.
- [ ] Đã cân nhắc giữ modular monolith như một phương án hợp lệ.

## 27. Bài tập tự kiểm tra

Một công ty đang vận hành modular monolith gồm Sales, Inventory, Payment và Reporting. Ban lãnh đạo đề xuất tách cả bốn thành microservice trong một quý. Hiện trạng:

- Sales và Inventory cùng ghi bảng Stock.
- Payment được gọi đồng bộ trong request tạo Order.
- Reporting truy vấn trực tiếp tất cả bảng.
- Một team gồm sáu người đang phát triển và on-call toàn hệ thống.
- Inventory có tải tăng đột biến trong các chiến dịch.
- Mọi release hiện tại đều cần deploy toàn ứng dụng.

Hãy phân tích:

1. Những lợi ích nào có thể đạt được khi tách Inventory?
2. Những chi phí và rủi ro nào sẽ xuất hiện ngay?
3. Có nên tách cả bốn module cùng lúc không? Vì sao?
4. Trước khi tách, cần thay đổi ownership của bảng Stock thế nào?
5. Nếu Payment timeout sau khi provider đã capture tiền, Sales cần biểu diễn kết quả ra sao?
6. Reporting nên lấy dữ liệu bằng cách nào để tránh coupling vào schema nội bộ?
7. Team sáu người có thể sở hữu bốn service độc lập và on-call hiệu quả không?
8. Metric nào chứng minh việc tách Inventory đem lại lợi ích?
9. Lộ trình nào giảm rủi ro nhất?
10. Điều kiện nào cho thấy nên dừng ở modular monolith?

Gợi ý:

| Vấn đề | Hướng phân tích |
|---|---|
| Inventory scale | Có tín hiệu workload khác biệt; đo reservation throughput, latency và saturation |
| Shared Stock table | Inventory trở thành owner; Sales dùng reservation contract |
| Payment timeout | Unknown outcome; dùng idempotency/reference và reconciliation, không tạo payment mới mù quáng |
| Reporting | Read model/data pipeline riêng với contract và retention rõ |
| Team ownership | Sáu người có thể chưa đủ để vận hành bốn service cùng lúc; đánh giá on-call và cognitive load |
| Thứ tự tách | Modularize và làm rõ ownership trước; ưu tiên Inventory nếu lợi ích được đo; giữ các module khác trong monolith |
| Đo lợi ích | Tần suất deploy độc lập, reservation p95/p99, scale cost, incident blast radius, thời gian chờ team khác |
| Dừng tách | Nếu workload/ownership chưa khác biệt hoặc chi phí distributed operation vượt lợi ích, giữ modular monolith |

## Kết luận

Tách triển khai có thể tạo khả năng scale, release, cô lập lỗi và ownership độc lập. Đổi lại, hệ thống phải trả chi phí network, partial failure, distributed consistency, contract versioning, observability, security, deployment automation, on-call và phối hợp team. Các chi phí này xuất hiện ngay cả với service nhỏ và ít traffic.

DDD giúp tìm ranh giới mô hình và trách nhiệm; modularization làm ranh giới đó rõ trong code; chỉ khi có nhu cầu độc lập đủ mạnh mới nên chuyển thành deployment boundary. Hãy bắt đầu bằng modular monolith có module ownership rõ, đo vấn đề thực tế, chuẩn bị contract và vận hành, rồi tách từng năng lực theo lộ trình kiểm chứng được. Một hệ thống ít service nhưng có ranh giới tốt thường dễ tiến hóa hơn một distributed monolith có nhiều process nhưng vẫn phụ thuộc chặt.
