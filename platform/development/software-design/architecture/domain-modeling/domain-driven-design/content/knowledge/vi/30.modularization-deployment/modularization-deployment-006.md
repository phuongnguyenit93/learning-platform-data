# Tránh hệ thống nguyên khối phân tán với phụ thuộc gọi chéo dày đặc

Một hệ thống có nhiều service chưa chắc đã có kiến trúc phân tán tốt. Nếu một thao tác nghiệp vụ đơn giản phải gọi tuần tự qua nhiều service, các service cùng đọc ghi một database, thay đổi của một context buộc nhiều context khác phải sửa theo, hoặc toàn bộ hệ thống phải triển khai cùng lúc, kiến trúc đó có thể đã trở thành **distributed monolith** — hệ thống nguyên khối được chia thành nhiều tiến trình.

Trong Domain-Driven Design (DDD), ranh giới Bounded Context giúp xác định nơi một mô hình và ngôn ngữ nghiệp vụ có ý nghĩa. Nhưng tách code thành service theo tên module hoặc theo bảng database không tự tạo ra ranh giới độc lập. Một ranh giới chỉ có giá trị khi nó giữ được quyền sở hữu mô hình, dữ liệu, quy tắc và quyết định triển khai trong một phạm vi rõ ràng.

Bài học này giải thích cách nhận diện phụ thuộc gọi chéo dày đặc, tìm nguyên nhân trong thiết kế domain và integration, chọn ranh giới phù hợp, giảm giao tiếp đồng bộ không cần thiết và tiến hóa hệ thống theo hướng có thể thay đổi từng phần.

## 1. Distributed Monolith là gì?

Distributed Monolith là một hệ thống được triển khai thành nhiều service hoặc process nhưng vẫn phụ thuộc chặt chẽ như một ứng dụng nguyên khối.

Các service có thể chạy trên nhiều máy, dùng container riêng và có endpoint riêng. Tuy nhiên, một thay đổi hoặc sự cố ở một service dễ buộc nhiều service khác phải thay đổi, triển khai hoặc ngừng hoạt động theo.

Ví dụ, một yêu cầu xác nhận đơn hàng phải đi qua chuỗi:

    API Gateway
        |
        v
    Order Service
        |
        v
    Customer Service
        |
        v
    Pricing Service
        |
        v
    Inventory Service
        |
        v
    Shipping Service
        |
        v
    Billing Service

Nếu mỗi bước đều là synchronous request và bước sau phải đợi bước trước, một thao tác của Order phụ thuộc vào thời gian phản hồi và availability của tất cả service trong chuỗi. Nếu Shipping chỉ cần nhận thông tin đơn sau khi đơn đã được xác nhận, việc gọi Shipping đồng bộ ngay trong request có thể tạo coupling không cần thiết.

Một hệ thống như vậy mang chi phí vận hành của microservices nhưng vẫn giữ coupling và phạm vi lỗi của monolith.

### Phân biệt các khái niệm

| Kiểu kiến trúc | Đặc điểm chính | Rủi ro thường gặp |
|---|---|---|
| Monolith có module rõ | Một deployment unit, module có ranh giới nội bộ | Module có thể dần phụ thuộc chéo nếu không kiểm soát |
| Modular Monolith | Một deployment unit nhưng module có ownership và API nội bộ rõ | Cần kỷ luật kiến trúc để giữ ranh giới |
| Microservices | Nhiều deployment unit, mỗi service có trách nhiệm và dữ liệu riêng | Chi phí vận hành, giao tiếp và consistency |
| Distributed Monolith | Nhiều deployment unit nhưng phụ thuộc dày đặc và phải thay đổi cùng nhau | Latency, cascading failure, release coupling và khó kiểm thử |

Distributed monolith không phải một công nghệ cụ thể. Nó là kết quả của những ranh giới và quan hệ phụ thuộc không phù hợp.

## 2. Dấu hiệu nhận biết phụ thuộc gọi chéo dày đặc

Không nên kết luận một hệ thống là distributed monolith chỉ vì có nhiều lời gọi HTTP. Cần nhìn vào mức độ phụ thuộc về thay đổi, dữ liệu, runtime và vận hành.

Một số dấu hiệu đáng chú ý:

- Một request nghiệp vụ thường gọi tuần tự qua nhiều service.
- Một service không thể hoàn thành use case nếu một nhóm service khác tạm thời không sẵn sàng, dù nghiệp vụ không thực sự cần chúng ngay lúc đó.
- Các service thường xuyên gọi ngược lại nhau.
- Một thay đổi schema hoặc field của service này buộc nhiều consumer phải sửa cùng lúc.
- Nhiều service cùng đọc hoặc ghi một database/schema.
- Các service dùng chung domain entity hoặc thư viện chứa business rules mutable.
- Một service không thể triển khai độc lập vì phải chờ các service khác cùng release.
- Một sự cố nhỏ tạo ra chuỗi timeout và retry lan rộng.
- Test end-to-end cần khởi động gần như toàn bộ hệ thống mới chạy được.
- Đội ngũ không thể chỉ ra service nào sở hữu một quyết định hoặc dữ liệu nghiệp vụ cụ thể.

### Dấu hiệu từ quy trình phát hành

Nếu thay đổi một field response của Pricing khiến Order, Checkout, Promotion, Invoice và Reporting phải phát hành cùng đợt, contract giữa các context có thể đang quá chặt.

Nếu tất cả service đều phải nâng version đồng thời vì dùng chung một domain library, mô hình nội bộ đã bị chia sẻ qua ranh giới deployment.

### Dấu hiệu từ sự cố vận hành

Nếu Customer Service chậm khiến Order chậm, điều đó có thể hợp lý khi Order cần xác thực một quyết định của Customer. Nhưng nếu một trang báo cáo Order cũng bị treo chỉ vì Customer Service không sẵn sàng, có thể reporting đang phụ thuộc runtime vào dữ liệu mà nó nên sở hữu dưới dạng projection.

Cần xem từng dependency theo use case và hậu quả nghiệp vụ, không áp dụng một quy tắc chung cho mọi lời gọi.

## 3. Phân biệt coupling cần thiết và coupling không cần thiết

Một hệ thống nghiệp vụ luôn có quan hệ giữa các khái niệm. Không thể và cũng không cần loại bỏ mọi dependency.

Ví dụ:

- Order cần xác nhận giá trước khi chốt giao dịch.
- Inventory cần quyết định có thể giữ hàng hay không.
- Billing cần biết khoản phải thu đã được xác lập.
- Shipping cần biết địa chỉ giao hàng đã được xác nhận.

Đó là các quan hệ nghiệp vụ có thật. Câu hỏi là context nào đưa ra quyết định, khi nào quyết định phải được xác nhận, và context khác cần biết kết quả bằng cách nào.

### Coupling cần thiết

Coupling có thể chấp nhận khi:

- Một use case cần quyết định hiện tại từ context sở hữu.
- Một invariant cần được bảo vệ tại nguồn có thẩm quyền.
- Một command yêu cầu một context khác thực hiện hành vi.
- Hai context có quan hệ nghiệp vụ rõ và contract ổn định.
- Độ trễ và khả năng phụ thuộc đã được chấp nhận trong SLA của use case.

### Coupling không cần thiết

Coupling thường có thể giảm khi:

- Consumer gọi service khác chỉ để lấy field hiển thị.
- Một request truy vấn tuần tự nhiều context dù dữ liệu có thể được materialize.
- Một context đọc trực tiếp bảng của context khác.
- Consumer phụ thuộc vào class, enum hoặc persistence schema nội bộ của provider.
- Mỗi thay đổi nhỏ đều yêu cầu đồng bộ release.
- Một event hoặc snapshot có thể đáp ứng nhu cầu nhưng hệ thống vẫn gọi API theo từng dòng dữ liệu.

Mục tiêu không phải là xóa mọi giao tiếp, mà là chỉ giữ những dependency có ý nghĩa và làm rõ mức cam kết của chúng.

## 4. Đo độ dày của dependency bằng call graph

Một cách hữu ích để hiểu coupling là vẽ đồ thị lời gọi giữa service.

- Node biểu diễn service hoặc bounded context.
- Directed edge biểu diễn một lời gọi hoặc phụ thuộc.
- Edge có thể được gắn nhãn synchronous, asynchronous, read hoặc command.
- Edge có thể ghi tần suất, latency, timeout và mức độ quan trọng.

Ví dụ một call graph nhiều đường chéo:

    Order ------> Customer
      |  \          |
      |   \         v
      v    ------> Pricing
    Inventory <----|
      |  \          |
      v   \         v
    Shipping ----> Billing
       ^              |
       |              v
       +------------ Order

Các vòng gọi và đường phụ thuộc ngược khiến việc thay đổi hoặc xử lý sự cố khó dự đoán.

### Những chỉ số nên quan sát

| Chỉ số | Ý nghĩa | Câu hỏi thiết kế |
|---|---|---|
| Số dependency trực tiếp | Một service phụ thuộc bao nhiêu service khác? | Có quá nhiều trách nhiệm bên ngoài không? |
| Fan-out | Một request tạo bao nhiêu lời gọi downstream? | Có thể gom hoặc materialize dữ liệu không? |
| Call depth | Chuỗi lời gọi dài bao nhiêu tầng? | Có thể bỏ bước đồng bộ không cần thiết không? |
| Synchronous critical path | Bao nhiêu lời gọi nằm trên đường phản hồi? | Có thể chuyển một phần sang async không? |
| Cross-context cycle | Có vòng dependency giữa context không? | Ownership hoặc integration direction có sai không? |
| Change coupling | Một thay đổi ảnh hưởng bao nhiêu service? | Contract có ổn định và độc lập không? |
| Release coupling | Bao nhiêu service phải triển khai cùng lúc? | Có đang chia sẻ implementation thay vì contract không? |

Không có ngưỡng số lượng service hoặc call depth phù hợp cho mọi hệ thống. Các chỉ số giúp tìm nơi cần điều tra; quyết định cuối cùng phải dựa trên use case, latency budget, failure semantics và ownership.

## 5. DDD giúp xác định ranh giới ở đâu?

DDD bắt đầu từ mô hình nghiệp vụ, không bắt đầu từ số lượng service mong muốn.

Một Bounded Context là ranh giới trong đó một mô hình và ngôn ngữ nhất quán được sử dụng. Cùng một từ có thể có ý nghĩa khác nhau giữa các context.

Ví dụ:

- Trong Sales, Customer có thể là đối tượng khách hàng tiềm năng và thông tin liên hệ.
- Trong Billing, Customer có thể là bên chịu trách nhiệm thanh toán và thông tin thuế.
- Trong Shipping, Recipient có thể là người nhận hàng tại một địa chỉ cụ thể.

Không nhất thiết phải có một Customer service cung cấp một Customer model chung cho tất cả.

### Tìm ranh giới qua trách nhiệm nghiệp vụ

Hãy hỏi:

- Context chịu trách nhiệm cho quyết định nghiệp vụ nào?
- Nó sở hữu những invariant nào?
- Nó dùng ngôn ngữ nào để mô tả các khái niệm?
- Nó thay đổi vì những lý do nghiệp vụ nào?
- Nó cần dữ liệu nào từ context khác?
- Nó có thể thực hiện use case của mình mà không truy cập database nội bộ của context khác không?
- Ai chịu trách nhiệm phát triển và vận hành nó?

Một ranh giới tốt thường gom những hành vi và dữ liệu thay đổi cùng nhau, đồng thời giảm nhu cầu phối hợp với phần còn lại.

### Bounded Context không tự động bằng một microservice

Một bounded context có thể được triển khai:

- Như một module trong modular monolith.
- Như một service riêng.
- Như một nhóm service nhỏ nếu có lý do rõ.
- Như một phần của hệ thống legacy được bao quanh bằng adapter.

Quyết định deployment cần xét đến khả năng vận hành, tải, bảo mật, quyền sở hữu đội ngũ và nhu cầu triển khai độc lập.

## 6. Bắt đầu bằng Modular Monolith khi ranh giới chưa ổn định

Nếu domain model và ownership chưa rõ, modular monolith thường là bước khởi đầu phù hợp.

Một ứng dụng có thể có các module:

    application
      sales
      order
      inventory
      billing
      shipping

Mỗi module sở hữu:

- Domain model riêng.
- Application use case riêng.
- Persistence adapter riêng.
- Public API nội bộ rõ ràng.
- Event hoặc integration contract khi cần trao đổi.

Các module có thể chạy trong cùng process và dùng chung hạ tầng deployment, nhưng không truy cập tùy tiện vào package hoặc bảng nội bộ của nhau.

### Lợi ích

- Gọi nội bộ không có network latency.
- Có thể dùng local transaction khi phù hợp.
- Dễ debug và test.
- Chưa phải vận hành nhiều service, broker và pipeline.
- Có thể thay đổi ranh giới khi hiểu biết nghiệp vụ tăng lên.
- Tạo nền tảng để tách deployment sau này nếu có nhu cầu thực.

### Modular Monolith không phải monolith tùy tiện

Nếu mọi module đều truy cập repository và entity của nhau, chỉ có package folder thì chưa có modularity.

Cần kiểm soát:

- Dependency direction.
- Public API của module.
- Package visibility.
- Ownership của dữ liệu.
- Không import implementation nội bộ.
- Architecture test để phát hiện dependency trái phép.

## 7. Thiết kế module API theo use case

Module khác nên tương tác với module sở hữu qua public API diễn đạt ý định nghiệp vụ.

Ví dụ, Order cần giữ hàng. Thay vì truy cập InventoryRepository hoặc sửa InventoryEntity trực tiếp, Order gọi một port hoặc application API:

~~~java
public interface InventoryReservation {
    ReservationResult reserve(
            ProductId productId,
            WarehouseId warehouseId,
            Quantity quantity,
            OrderId orderId
    );
}
~~~

Implementation của port thuộc Inventory module. Order chỉ biết contract cần thiết để hoàn thành use case.

Nếu module nằm trong cùng process, lời gọi có thể là method call. Nếu sau này tách deployment, contract có thể được triển khai qua HTTP hoặc message mà không cần đưa model nội bộ của Inventory sang Order.

### Contract nên nhỏ và ổn định

Không expose toàn bộ Aggregate hoặc persistence entity ra public API. Chỉ cung cấp:

- Command có ý nghĩa.
- Query có mục đích rõ.
- Result hoặc error contract.
- Event đã được chọn lọc.
- Identity và version cần thiết.

Một API kiểu getEverythingForOrder() trả một object lớn chứa Customer, Product, Inventory, Payment và Shipping thường là dấu hiệu các context chưa xác định đúng nhu cầu trao đổi.

## 8. Tránh dependency vòng giữa các module

Dependency vòng làm ranh giới mất ý nghĩa.

Ví dụ:

    Order -> Inventory
    Inventory -> Order

Nếu Order cần Inventory để giữ hàng và Inventory lại gọi Order để hỏi đơn có hợp lệ hay không, hai module bị khóa chặt vào nhau.

Có thể xử lý bằng cách:

- Để Order gửi command reserve tới Inventory.
- Inventory xác thực các điều kiện thuộc quyền sở hữu của nó.
- Inventory phát kết quả ReservationAccepted hoặc ReservationRejected.
- Order cập nhật trạng thái theo kết quả.
- Nếu cần thông tin Order, gửi dữ liệu tối thiểu trong command hoặc dùng contract đã thống nhất.

Không nên để Inventory tải Order Aggregate từ Order database. Nếu Inventory cần dữ liệu để ra quyết định, hãy xác định chính xác dữ liệu đó và nguồn có thẩm quyền.

### Dependency inversion

Module cấp cao có thể định nghĩa port diễn đạt nhu cầu của use case. Adapter cụ thể thực hiện giao tiếp với module khác hoặc hệ thống ngoài.

Điều này giúp application/domain không phụ thuộc trực tiếp vào HTTP client, broker hoặc persistence schema của provider.

Tuy nhiên, interface không tự làm coupling biến mất. Nếu contract chứa toàn bộ object graph của module kia, dependency ngữ nghĩa vẫn còn.

## 9. Không dùng Shared Database làm integration contract

Một dấu hiệu mạnh của distributed monolith là nhiều service cùng đọc và ghi một schema database.

Các vấn đề thường gặp:

- Một service đổi column làm service khác lỗi.
- Không biết service nào sở hữu invariant.
- Hai service cùng cập nhật một record theo các quy tắc khác nhau.
- Migration phải phối hợp nhiều release.
- Business logic bị chia giữa nhiều codebase.
- Test riêng từng service không phản ánh hành vi thực khi ghi đồng thời.

Mỗi bounded context nên sở hữu dữ liệu và schema persistence của mình. Context khác truy cập qua API, command, event hoặc projection được tạo có chủ đích.

### Shared database có thể tồn tại trong giai đoạn chuyển đổi

Với hệ thống legacy, có thể chưa tách database ngay. Khi đó cần:

- Xác định owner cho từng bảng hoặc nhóm dữ liệu.
- Chỉ owner được ghi dữ liệu chính thức.
- Consumer dùng view/read replica hoặc adapter có kiểm soát.
- Ghi nhận các truy cập ngoài ownership.
- Từng bước chuyển consumer sang contract.
- Đặt kế hoạch loại bỏ shared writes.

Điều quan trọng là không để shared database trở thành contract lâu dài không được quản lý.

## 10. Chọn synchronous call khi use case thật sự cần câu trả lời ngay

Synchronous request phù hợp khi bên gọi cần kết quả để tiếp tục quyết định trong cùng một interaction.

Ví dụ:

- Pricing xác nhận quote còn hiệu lực trước khi Order được xác nhận.
- Inventory quyết định reservation có thành công hay không.
- Payment provider trả kết quả authorize khi checkout đang chờ.
- Credit Management quyết định giao dịch có vượt hạn mức không.

Trong các trường hợp này, cần định nghĩa:

- Timeout.
- Error semantics.
- Retry policy.
- Idempotency.
- Latency budget.
- Hành vi khi provider không sẵn sàng.
- Ai có quyền đưa ra quyết định cuối cùng.

### Giữ đường đồng bộ ngắn

Nếu một request cần gọi tuần tự A → B → C → D, latency tổng có thể gần bằng tổng latency của từng bước, chưa tính queueing và retry.

Một chuỗi dài cũng tạo nhiều điểm có thể timeout hoặc lỗi. Hãy xem bước nào thực sự cần hoàn tất trước khi trả response và bước nào có thể chạy sau commit.

## 11. Chuyển side effect và cập nhật phụ sang asynchronous integration event

Nhiều hành động không cần nằm trong đường phản hồi đồng bộ.

Ví dụ, sau khi Order được xác nhận:

- Gửi email xác nhận.
- Cập nhật customer activity.
- Đẩy dữ liệu sang analytics.
- Tạo tác vụ fulfillment.
- Cập nhật search projection.

Order có thể commit trạng thái Confirmed và phát event OrderConfirmed. Consumer xử lý phần việc của mình độc lập.

    Order
      |
      | commit + outbox
      v
    OrderConfirmed
      |
      +------> Notification
      |
      +------> Analytics
      |
      +------> Fulfillment
      |
      +------> Customer Activity

Cách này giảm số lời gọi đồng bộ và giúp producer không cần biết mọi consumer.

### Event phải diễn tả sự kiện đã xảy ra

Event OrderConfirmed có nghĩa Order đã được xác nhận. Nó không nên chỉ là một command yêu cầu consumer tự suy đoán điều cần làm.

Nếu cần yêu cầu một context thực hiện hành vi, gửi command có đích đến rõ ràng. Nếu thông báo một fact đã xảy ra, phát event.

## 12. Không thay mọi API bằng Event

Asynchronous messaging không phải giải pháp cho mọi coupling.

Event có thể làm quy trình khó theo dõi hơn nếu:

- Consumer không rõ ownership.
- Event payload không có semantics ổn định.
- Không có idempotency hoặc replay.
- Không có cách theo dõi workflow.
- Một use case cần quyết định ngay nhưng hệ thống chỉ phát event rồi giả định thành công.
- Quá nhiều event nhỏ tạo thành một distributed workflow khó hiểu.

Hãy chọn theo semantics:

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Yêu cầu một context thực hiện hành vi và cần kết quả ngay | Synchronous command/API |
| Thông báo fact đã xảy ra | Integration event |
| Đọc dữ liệu thường xuyên, chấp nhận eventual consistency | Local projection/read model |
| Truy vấn tổng hợp nhiều context | Query composition hoặc projection |
| Tác vụ dài, nhiều bước và có trạng thái | Process Manager/Saga |
| Dữ liệu ít thay đổi | Batch hoặc cache có policy |

## 13. Tránh chatty API và N+1 service calls

Một API chatty yêu cầu caller thực hiện nhiều request nhỏ để hoàn thành một use case.

Ví dụ, Order gọi Product Service cho từng dòng hàng:

    for each orderLine:
        productService.getProduct(productId)

Một đơn 40 dòng có thể tạo 40 network calls. Nếu mỗi call có latency riêng, request trở nên chậm và dễ lỗi.

Có thể cải thiện bằng:

- Batch query theo danh sách ID.
- Projection cục bộ cho dữ liệu hiển thị.
- API có response shape theo use case.
- Cache có TTL và invalidation policy.
- Chỉ lấy field cần thiết.
- Tách dữ liệu cần xác nhận đồng bộ khỏi dữ liệu chỉ để hiển thị.

Không nên tạo API tổng hợp khổng lồ làm lộ toàn bộ mô hình nội bộ. Batch endpoint vẫn cần có contract nhỏ và rõ.

## 14. Local Read Model giảm phụ thuộc runtime

Một context có thể cần dữ liệu của context khác để tìm kiếm hoặc hiển thị. Thay vì gọi API trên từng request, consumer có thể giữ projection cục bộ.

Ví dụ Sales cần tìm khách hàng theo tên và hạng thành viên. Customer Management phát CustomerProfileChanged. Sales cập nhật CustomerSearchProjection với những field cần thiết.

Projection không trở thành nguồn có thẩm quyền. Nếu Sales muốn khóa tài khoản, nó vẫn phải gửi command đến Customer Management.

### Chấp nhận eventual consistency có chủ đích

Cần định nghĩa:

- Projection được phép trễ bao lâu?
- Dữ liệu quá cũ sẽ hiển thị ra sao?
- Use case nào được phép dùng stale data?
- Use case nào phải xác minh nguồn?
- Làm thế nào phát hiện consumer lag hoặc mất event?

Một màn hình tìm kiếm có thể chấp nhận trễ vài phút. Quyết định tín dụng hoặc giữ hàng thường cần xác nhận tại context sở hữu.

## 15. Dữ liệu và invariant phải thuộc một owner rõ ràng

Nếu nhiều service cùng ghi một business fact, không có nơi duy nhất bảo vệ invariant.

Ví dụ Order và Inventory đều giữ số lượng tồn rồi cùng cập nhật theo logic riêng. Khi hai đơn cạnh tranh, các bản sao có thể cho kết quả khác nhau.

Inventory nên sở hữu:

- On-hand quantity.
- Reserved quantity.
- Reservation lifecycle.
- Quy tắc không giữ vượt số lượng khả dụng.

Order sở hữu:

- Đơn hàng.
- Dòng hàng.
- Trạng thái nghiệp vụ của đơn.
- Quyết định xác nhận đơn dựa trên kết quả reservation.

Hai context trao đổi bằng command và event. Inventory không cần chia sẻ Aggregate nội bộ cho Order.

### Quy tắc thực hành

- Một business fact có một nguồn có thẩm quyền.
- Context khác có thể giữ reference hoặc projection.
- Consumer không sửa dữ liệu chính thức của owner.
- Invariant được bảo vệ tại context sở hữu.
- Snapshot lịch sử được lưu ở nơi cần tái hiện giao dịch.

## 16. Dùng Context Map để làm rõ quan hệ giữa các context

Context Map mô tả cách các Bounded Context tích hợp và ảnh hưởng lẫn nhau.

Một số quan hệ thường gặp:

| Quan hệ | Ý nghĩa | Điều cần chú ý |
|---|---|---|
| Customer/Supplier | Một context cung cấp dữ liệu hoặc capability cho context khác | Contract và quyền ưu tiên thay đổi |
| Conformist | Consumer chấp nhận mô hình provider | Coupling ngữ nghĩa cần được nhận biết |
| Anti-Corruption Layer | Consumer dịch mô hình ngoài sang mô hình nội bộ | Ngăn ngôn ngữ bên ngoài lan vào domain |
| Open Host Service | Provider công bố một protocol/contract rõ | Contract ổn định cho nhiều consumer |
| Published Language | Ngôn ngữ trao đổi được công bố và quản lý | Versioning và compatibility |
| Partnership | Hai nhóm phối hợp chặt vì mục tiêu chung | Cần phối hợp thay đổi có chủ đích |
| Shared Kernel | Một phần mô hình được hai context thống nhất chia sẻ | Phạm vi nhỏ và quản trị thay đổi nghiêm ngặt |

Không nên chọn quan hệ chỉ dựa trên công nghệ. Context Map phải phản ánh ownership, quyền thay đổi và mức độ phụ thuộc thực tế.

### Anti-Corruption Layer giảm coupling ngữ nghĩa

Nếu provider trả về status code theo legacy system, consumer không nên đưa nguyên enum đó vào domain model. Adapter có thể chuyển sang khái niệm nội bộ.

    Legacy API
        |
        v
    ACL / Translator
        |
        v
    Local Domain Language

ACL giúp thay provider hoặc schema bên ngoài mà không phải sửa mọi domain behavior.

## 17. Quản lý contract để service có thể tiến hóa độc lập

Một contract tốt không expose chi tiết triển khai của provider.

Nên xác định:

- Field bắt buộc và tùy chọn.
- Identity và version.
- Ngữ nghĩa timestamp.
- Error codes.
- Idempotency key khi có command ghi.
- Schema version.
- Quy tắc unknown enum/value.
- Tương thích ngược.
- Deprecation policy.

Tránh thay đổi nghĩa của field mà không đổi version hoặc thông báo consumer. Thêm field tùy chọn thường dễ tương thích hơn đổi type hoặc xóa field đang được dùng.

### Không chia sẻ domain class như contract

Dùng chung một Java library chứa Order, Customer, Money hoặc JPA entity giữa các service khiến mỗi thay đổi nội bộ có thể buộc nhiều service nâng version.

Có thể chia sẻ schema contract, generated client hoặc serializer ở mức kỹ thuật, nhưng consumer vẫn nên ánh xạ vào model nội bộ của mình.

## 18. Transaction và Saga khi một use case trải qua nhiều context

Một giao dịch nghiệp vụ có thể cần nhiều context cùng tham gia. Ví dụ checkout:

1. Pricing xác nhận quote.
2. Inventory giữ hàng.
3. Payment authorize.
4. Order xác nhận.
5. Fulfillment bắt đầu xử lý.

Không nên giả định có một database transaction duy nhất bao trùm mọi service. Mỗi context thường commit local transaction riêng.

Saga hoặc Process Manager điều phối tiến trình:

    CheckoutRequested
          |
          v
    Validate Quote
          |
          v
    Reserve Inventory
          |
          v
    Authorize Payment
          |
          v
    Confirm Order
          |
          v
    Checkout Completed

Nếu Payment authorize thất bại sau khi Inventory đã giữ hàng, workflow có thể gửi ReleaseReservation. Đây là compensation có ý nghĩa nghiệp vụ.

### Phân biệt trạng thái trung gian và hoàn tất

Order có thể ở trạng thái PendingConfirmation trong khi chờ reservation và payment. Không nên hiển thị Confirmed trước khi các điều kiện bắt buộc hoàn tất.

Workflow cần có:

- Correlation ID.
- Trạng thái từng bước.
- Timeout và deadline.
- Retry có giới hạn.
- Idempotency.
- Compensation.
- Manual review cho trường hợp không thể tự phục hồi.

## 19. Chọn Orchestration hay Choreography

Hai kiểu phối hợp thường gặp:

- **Orchestration:** một Process Manager điều phối bước tiếp theo và theo dõi trạng thái.
- **Choreography:** mỗi context phản ứng với event và phát event tiếp theo.

| Tiêu chí | Orchestration | Choreography |
|---|---|---|
| Luồng nghiệp vụ | Tập trung tại workflow | Phân tán qua event |
| Theo dõi trạng thái | Dễ thấy tại Process Manager | Cần correlation và observability tốt |
| Coupling | Consumer biết command/step của workflow | Consumer phụ thuộc event semantics |
| Phù hợp | Quy trình dài, nhiều nhánh và compensation | Phản ứng độc lập, ít bước |
| Rủi ro | Orchestrator trở thành trung tâm quá lớn | Luồng ẩn, khó debug và vòng event |

Không nên tạo một orchestrator khổng lồ biết mọi chi tiết domain. Nó chỉ nên quản lý tiến trình và điều kiện chuyển bước. Quyết định nghiệp vụ vẫn thuộc context sở hữu.

Choreography cũng cần giới hạn. Nếu phải đọc nhiều event mới hiểu một use case, có thể workflow nên được mô hình hóa rõ hơn bằng Process Manager.

## 20. Xử lý lỗi để tránh cascading failure

Một dependency đồng bộ có thể làm lỗi lan sang caller nếu không có giới hạn.

Các cơ chế thường cần:

- Timeout ngắn và phù hợp latency budget.
- Retry chỉ với lỗi transient và có giới hạn.
- Exponential backoff với jitter.
- Circuit breaker.
- Bulkhead để cô lập tài nguyên.
- Rate limit.
- Fallback theo policy nghiệp vụ.
- Idempotency cho command có side effect.

Không retry vô hạn. Retry có thể làm tăng tải khi provider đang quá tải và tạo retry storm.

### Timeout phải được thiết kế theo toàn bộ request budget

Nếu API có deadline 2 giây, không thể để mỗi downstream call timeout 2 giây rồi gọi tuần tự nhiều service. Cần chia latency budget cho các bước và truyền deadline/cancellation nếu hạ tầng hỗ trợ.

### Circuit breaker không thay thế thiết kế ranh giới

Circuit breaker giảm tác động khi provider lỗi. Nó không làm một dependency không cần thiết trở nên hợp lý. Nếu một màn hình chỉ cần projection, tốt hơn là không gọi provider trên request đó.

## 21. Observability cho dependency giữa các service

Khi một request đi qua nhiều service, cần khả năng lần theo toàn bộ hành trình.

Nên có:

- Distributed trace với trace ID xuyên service.
- Correlation ID cho workflow.
- Structured log với service, operation và outcome.
- Metric latency theo dependency.
- Error rate và timeout rate.
- Consumer lag và event age.
- Saga duration và số workflow bị kẹt.
- Dashboard cho các dependency quan trọng.

Một trace có thể cho thấy Order mất 1,8 giây, trong đó Pricing mất 100 ms, Customer mất 1,2 giây và Inventory mất 300 ms. Dữ liệu đó giúp xác định critical path thực tế.

Tránh log payload nhạy cảm hoặc toàn bộ dữ liệu khách hàng. Trace cần đủ metadata để điều tra mà không làm lộ dữ liệu.

## 22. Kiểm thử để phát hiện distributed monolith

Kiểm thử kiến trúc nên xác nhận module boundaries và integration contracts.

Một số dạng test hữu ích:

| Test | Điều cần xác nhận |
|---|---|
| Architecture test | Module không import package nội bộ của module khác |
| Module contract test | Public API chỉ expose command/query/result đã định |
| Consumer contract test | Consumer tương thích với event/API provider |
| Integration test | Transaction và outbox/inbox hoạt động đúng |
| Failure test | Provider timeout không làm hỏng use case không cần provider |
| Resilience test | Retry/circuit breaker không tạo side effect trùng |
| Workflow test | Saga xử lý success, timeout, rejection và compensation |
| Deployment test | Service có thể build/deploy độc lập theo contract |

Một test quan trọng là mô phỏng provider không sẵn sàng. Nếu chức năng chỉ hiển thị projection vẫn thất bại do một service nguồn offline, dependency runtime có thể không cần thiết.

### Kiểm tra release independence

Thử thay đổi một implementation nội bộ mà không đổi contract. Nếu consumer phải sửa code hoặc phát hành cùng lúc, coupling có thể đang rò qua contract.

Không nhất thiết mọi service phải deploy bất cứ lúc nào mà không phối hợp. Nhưng việc phối hợp phải đến từ thay đổi nghiệp vụ hoặc contract thực sự, không phải do chia sẻ class và database tùy tiện.

## 23. Refactor từ distributed monolith

Không nên tách hoặc gộp hàng loạt service trong một lần. Hãy xác định dependency có tác động lớn nhất và xử lý theo use case.

Một lộ trình có thể là:

1. **Lập dependency map:** ghi nhận call graph, shared database, shared library và release dependency.
2. **Xác định ownership:** chỉ ra context sở hữu từng business fact và invariant.
3. **Chọn use case đau nhất:** latency cao, failure lan rộng hoặc release coupling.
4. **Phân loại dependency:** synchronous decision, read-only lookup, event notification hay workflow.
5. **Thiết kế contract:** command/query/event tối thiểu và có version.
6. **Tạo local projection:** với dữ liệu đọc nhiều và chấp nhận eventual consistency.
7. **Chuyển quyền ghi:** chỉ owner cập nhật dữ liệu chính thức.
8. **Loại bỏ shared model/database writes:** chuyển consumer sang adapter/contract.
9. **Giảm call depth:** chuyển side effect sang event hoặc workflow.
10. **Thêm resilience và observability:** timeout, idempotency, tracing, lag và reconciliation.
11. **Kiểm thử độc lập:** contract, failure và deployment.
12. **Đánh giá lại ranh giới:** dựa trên thay đổi và vận hành thực tế.

### Strangler pattern

Với hệ thống legacy, có thể thay từng capability:

    Existing Monolith
       |        |
       |        +----> Legacy capability
       |
       +----> New bounded context
                  |
                  v
             New data owner

Gateway hoặc adapter định tuyến một phần use case sang capability mới. Dần dần chuyển quyền sở hữu dữ liệu và traffic, sau đó loại bỏ đường cũ.

Không nên để hai hệ thống cùng ghi dữ liệu chính thức trong thời gian dài. Nếu phải dual-write tạm thời, cần có chiến lược reconciliation, thời hạn kết thúc và owner rõ ràng.

## 24. Khi nào nên tách một module thành service?

Một module không cần trở thành service chỉ vì nó có package hoặc database riêng.

Có thể cân nhắc tách deployment khi có nhu cầu thực:

- Cần scale độc lập do profile tải khác biệt rõ.
- Cần cô lập bảo mật hoặc compliance.
- Có ownership và đội ngũ vận hành riêng.
- Cần lịch triển khai độc lập.
- Có yêu cầu availability riêng.
- Có thể giữ contract và data ownership ổn định.
- Chi phí vận hành phân tán được bù bằng lợi ích cụ thể.

Không nên tách chỉ vì:

- Module có nhiều class.
- Một team muốn dùng framework khác.
- Muốn mỗi domain object có một service.
- Số lượng microservice được xem như thước đo trưởng thành.
- Muốn tránh refactor nội bộ.
- Một service đang có code khó hiểu nhưng ranh giới nghiệp vụ chưa được xác định.

Tách deployment làm tăng chi phí network, observability, security, deployment, data consistency và incident response. Cần có lý do đủ mạnh.

## 25. Ví dụ thiết kế lại luồng xác nhận đơn hàng

### Thiết kế nhiều call chéo

    Checkout API
       |
       v
    Order Service
       |
       +--> Customer Service (get profile)
       |
       +--> Pricing Service (get price per line)
       |
       +--> Inventory Service (get available per line)
       |
       +--> Shipping Service (get options)
       |
       +--> Billing Service (create invoice)
       |
       v
    Return success

Các vấn đề:

- Gọi lặp theo từng dòng hàng.
- Nhiều service nằm trên critical path.
- Shipping và Billing có thể chỉ cần biết sau khi order được xác nhận.
- Dữ liệu hiển thị và quyết định bị trộn.
- Không có trạng thái trung gian rõ.
- Một lỗi downstream có thể khiến toàn bộ request thất bại.

### Thiết kế theo ownership và workflow

    Checkout
       |
       v
    Order Application
       |
       +--> Pricing: validate quote
       |
       +--> Inventory: reserve stock
       |
       +--> Payment: authorize
       |
       v
    Order: confirm and commit
       |
       +--> OrderConfirmed event
                 |
                 +--> Fulfillment
                 +--> Billing
                 +--> Notification
                 +--> Analytics

Customer profile và product display data có thể được lấy từ projection nếu use case cho phép. Quote và reservation là quyết định cần xác nhận ở context sở hữu. Billing và Notification có thể xử lý sau commit nếu nghiệp vụ cho phép.

Nếu Payment authorize thành công nhưng Order commit thất bại, workflow cần xử lý authorization theo policy, chẳng hạn void authorization. Nếu Inventory reservation thành công nhưng Payment bị từ chối, workflow gửi release reservation.

Kết quả là đường đồng bộ ngắn hơn và các bước sau commit có thể tiến hành độc lập. Đây vẫn là một workflow phân tán, nên cần idempotency, correlation, timeout và theo dõi trạng thái.

## 26. Checklist tránh Distributed Monolith

Trước khi tạo hoặc tách service, hãy kiểm tra:

- Ranh giới Bounded Context dựa trên ngôn ngữ và trách nhiệm nghiệp vụ chưa?
- Mỗi business fact có một owner rõ chưa?
- Invariant được bảo vệ ở context có thẩm quyền chưa?
- Service có public API nhỏ và ổn định không?
- Có dependency vòng giữa các context không?
- Một request có gọi tuần tự quá nhiều service không?
- Read-only data có thể được projection hoặc batch query không?
- Quyết định quan trọng có được xác nhận ở nguồn sở hữu không?
- Có shared database writes hoặc shared domain model không?
- Contract có versioning và compatibility policy không?
- Command và event có semantics rõ ràng không?
- Event consumer có idempotent và có replay/reconciliation không?
- Workflow dài có Process Manager/Saga phù hợp không?
- Timeout, retry, circuit breaker và bulkhead có được thiết kế theo use case không?
- Có distributed tracing và correlation ID không?
- Service có thể build và deploy độc lập khi contract không đổi không?
- Test có mô phỏng provider timeout và partial failure không?
- Có lý do vận hành cụ thể cho mỗi deployment boundary không?
- Có lộ trình loại bỏ shared writes hoặc dual-write tạm thời không?

## 27. Kết luận

Distributed monolith xuất hiện khi hệ thống được chia thành nhiều service nhưng vẫn phụ thuộc chặt về call graph, dữ liệu, contract và release. Nhiều deployment unit không tự tạo ra tính độc lập. Nếu một thay đổi nhỏ hoặc sự cố ở một context buộc nhiều context khác dừng theo, ranh giới hiện tại cần được xem xét.

DDD giúp tìm ranh giới qua Bounded Context, ngôn ngữ nghiệp vụ, ownership và invariant. Modular Monolith có thể là bước phù hợp khi ranh giới chưa ổn định. Khi cần tách deployment, mỗi service phải sở hữu quyết định và dữ liệu rõ ràng, giao tiếp qua contract nhỏ, đồng thời dùng synchronous call cho quyết định cần kết quả ngay và event/projection cho nhu cầu đọc hoặc side effect có thể xử lý sau.

Hãy đo call graph, latency, failure và change coupling; giảm chatty API và shared writes; dùng Saga cho quy trình nhiều context; bổ sung idempotency, resilience và observability. Tiến hóa từng use case dựa trên bằng chứng vận hành giúp hệ thống đạt được ranh giới độc lập thực sự mà không tạo thêm phân tán chỉ vì hình thức.
